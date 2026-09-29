#!/usr/bin/env python3
"""Create and atomically update typed project state for the V14 controller."""

from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path
from typing import Any

from lib_v10 import (
    STATE_REL, ContractError, Draft202012Validator, FormatChecker,
    build_workspace_manifest, dump_json, json_output, load_json, now_iso,
    relative_safe, sha256_file, sha256_text,
)
from state_v11 import (
    STATE_SCHEMA_VERSION, artifact_is_current_formal, artifact_is_protected,
    clear_invalid_artifact_validations, evidence_binding_hash,
    invalidate_components, load_state, stale_exact_artifact_evidence,
    validate_artifact_proposal, validate_evidence,
    validate_state_semantics,
)


INITIAL_STATES = {"question": "S0", "shared_data": "D0", "artifact": "A0"}


def state_path(project_root: Path) -> Path:
    return project_root / STATE_REL


def require_state(project_root: Path, check_files: bool = False) -> dict[str, Any]:
    state, load_errors = load_state(project_root)
    errors = [] if load_errors == ["state_missing"] else list(load_errors)
    if state is None:
        raise ContractError("state unavailable: " + "; ".join(load_errors))
    errors.extend(validate_state_semantics(state, project_root, check_files=check_files))
    if errors:
        raise ContractError("state invalid: " + "; ".join(sorted(set(errors))))
    return state


def commit(project_root: Path, state: dict[str, Any], event: str, subject: str, details: dict[str, Any]) -> dict[str, Any]:
    state["revision"] += 1
    timestamp = now_iso()
    state["project"]["updated_at"] = timestamp
    if subject in state.get("components", {}):
        state["components"][subject]["updated_at"] = timestamp
    state["history"].append({
        "revision": state["revision"], "event": event, "at": timestamp,
        "subject": subject, "details": details,
    })
    # A G1 commit validates the control graph and typed records, not every live
    # file in the project. Protected identities are checked at G2/G3/recovery.
    errors = validate_state_semantics(state, project_root, check_files=False)
    if errors:
        raise ContractError("refusing invalid state commit: " + "; ".join(errors))
    dump_json(state_path(project_root), state)
    return state


def do_init(args: argparse.Namespace) -> dict[str, Any]:
    project_root = args.project_root.resolve()
    if state_path(project_root).exists():
        raise ContractError("state already exists")
    project_root.mkdir(parents=True, exist_ok=True)
    timestamp = now_iso()
    watch_roots = sorted(set(args.watch_root or ["."]))
    state: dict[str, Any] = {
        "schema_version": STATE_SCHEMA_VERSION,
        "revision": 1,
        "project": {
            "id": args.project_id,
            "state": "P0",
            "required_components": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        "components": {},
        "artifacts": {},
        "open_decisions": [],
        "next_actions": [],
        "recoveries": {},
        "watch_roots": watch_roots,
        "workspace_baseline": build_workspace_manifest(project_root, watch_roots),
        "history": [{
            "revision": 1, "event": "project_initialized", "at": timestamp,
            "subject": args.project_id, "details": {"gate": "G1"}
        }],
    }
    errors = validate_state_semantics(state, project_root, check_files=False)
    if errors:
        raise ContractError("initial state invalid: " + "; ".join(errors))
    dump_json(state_path(project_root), state)
    return state


def do_add_component(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if state["project"]["state"] != "P0":
        raise ContractError("components can be added only while project is P0")
    if args.component_id in state["components"]:
        raise ContractError("component already exists")
    missing = [item for item in args.dependency if item not in state["components"]]
    if missing:
        raise ContractError("unknown dependencies: " + ",".join(missing))
    timestamp = now_iso()
    state["components"][args.component_id] = {
        "type": args.type,
        "state": INITIAL_STATES[args.type],
        "status": "active",
        "dependencies": sorted(set(args.dependency)),
        "consumers": [],
        "evidence": [],
        "decisions": [],
        "invalidated_at_revision": None,
        "updated_at": timestamp,
    }
    for dependency in args.dependency:
        consumers = state["components"][dependency]["consumers"]
        if args.component_id not in consumers:
            consumers.append(args.component_id)
            consumers.sort()
    if not args.optional:
        state["project"]["required_components"] = sorted(set(state["project"]["required_components"]) | {args.component_id})
    return commit(
        args.project_root, state, "component_added", args.component_id,
        {"type": args.type, "dependencies": sorted(set(args.dependency))},
    )


def do_record_evidence(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if args.component_id not in state["components"]:
        raise ContractError("unknown component")
    component = state["components"][args.component_id]
    evidence = load_json(args.evidence)
    closed_failure_levels: set[str] = set()
    if component["status"] == "closed":
        machine = load_json(Path(__file__).resolve().parents[1] / "references/state-machine.json")
        reopen_transitions = [
            item for item in machine["transitions"][component["type"]]
            if item["from"] == component["state"] and item.get("kind") == "reopen"
        ]
        reopen_levels = {
            level
            for item in reopen_transitions
            for level in item.get("requires", []) + item.get("reason_levels", [])
        }
        closed_failure_levels = {
            level
            for item in reopen_transitions
            if "fail" in item.get("reason_statuses", [])
            for level in item.get("reason_levels", [])
        }
        current_path_levels = cumulative_requirements(component["type"], component["state"])
        post_closure_levels = {"delivery_acceptance"}
        if evidence.get("level") not in (
            reopen_levels | current_path_levels | post_closure_levels
        ):
            raise ContractError(
                "closed component accepts only current-path, delivery-gate, or declared reopen evidence"
            )
    errors = validate_evidence(
        evidence, args.project_root, check_files=True, state=state,
        component_id=args.component_id, stored=False,
    )
    if errors:
        raise ContractError("invalid evidence: " + "; ".join(errors))
    for owner_id, owner in state["components"].items():
        if owner_id != args.component_id and any(item.get("id") == evidence["id"] for item in owner.get("evidence", []) if isinstance(item, dict)):
            raise ContractError("evidence id already belongs to another component")
    records = state["components"][args.component_id]["evidence"]
    existing = next((index for index, item in enumerate(records) if item.get("id") == evidence["id"]), None)
    if existing is not None and not args.replace:
        raise ContractError("evidence id already exists; use --replace")
    stored_evidence = dict(evidence)
    stored_evidence["recorded_revision"] = state["revision"] + 1
    if existing is None:
        records.append(stored_evidence)
    else:
        records[existing] = stored_evidence
    cleared_validations = clear_invalid_artifact_validations(state)
    # A failing observation blocks the matching evidence level, but it does not
    # silently reset the whole component graph. Protected identity changes and
    # explicit checkpoint/reopen actions own component invalidation in V11.
    affected: list[str] = []
    project_before = state["project"]["state"]
    affected_levels: set[tuple[str, str]] = set()
    if evidence.get("status") != "pass":
        affected_levels.add((args.component_id, str(evidence.get("level"))))
        reconcile_project_binding_change(
            state,
            {args.component_id},
            affected_levels=affected_levels,
        )
    checkpoint_review = bool(
        evidence.get("status") == "fail"
        and evidence.get("level") in closed_failure_levels
    )
    return commit(
        args.project_root, state, "evidence_recorded", args.component_id,
        {
            "evidence_id": evidence["id"], "level": evidence["level"],
            "status": evidence["status"], "kind": evidence["kind"],
            "replaced": existing is not None, "affected_components": affected,
            "affected_evidence_levels": [
                {"component_id": component_id, "level": level}
                for component_id, level in sorted(affected_levels)
            ],
            "cleared_artifact_validations": cleared_validations,
            "checkpoint_review_required": checkpoint_review,
            "project_from": project_before, "project_to": state["project"]["state"],
        },
    )


def current_evidence_levels(state: dict[str, Any], component_id: str) -> set[str]:
    component = state["components"][component_id]
    latest: dict[str, dict[str, Any]] = {}
    for item in component.get("evidence", []):
        level = item.get("level")
        if (
            isinstance(level, str)
            and item.get("subject_id") == component_id
            and item.get("binding_hash") == evidence_binding_hash(
                component_id, level, item.get("input_refs", []), item.get("claim_refs", [])
            )
            and not validate_evidence(
                item, None, check_files=False, state=state,
                component_id=component_id, stored=True,
            )
            and item.get("recorded_revision", -1) > latest.get(level, {}).get("recorded_revision", -1)
        ):
            latest[level] = item
    return {level for level, item in latest.items() if item.get("status") == "pass"}


def evidence_record_revision(state: dict[str, Any], component_id: str, evidence_id: str) -> int | None:
    component = state["components"][component_id]
    record = next((item for item in component.get("evidence", []) if item.get("id") == evidence_id), None)
    return record.get("recorded_revision") if isinstance(record, dict) else None


def latest_transition_revision(state: dict[str, Any], subject: str, target: str) -> int:
    revisions = [
        item["revision"] for item in state.get("history", [])
        if item.get("event") in {"component_transition", "project_transition"}
        and item.get("subject") == subject and item.get("details", {}).get("to") == target
    ]
    return max(revisions, default=0)


def find_transition(component_type: str, current: str, target: str) -> dict[str, Any] | None:
    machine = load_json(Path(__file__).resolve().parents[1] / "references/state-machine.json")
    for transition in machine["transitions"][component_type]:
        if transition["from"] == current and transition["to"] == target:
            return transition
    return None


def project_transition_requirements(state: dict[str, Any], current: str, target: str) -> list[str]:
    if current == "P0" and target == "P1":
        errors = []
        expected = {"question": "S7", "shared_data": "D3", "artifact": "A3"}
        required_ids = state["project"].get("required_components", [])
        if not required_ids:
            errors.append("required_components_empty")
        for component_id in required_ids:
            component = state["components"][component_id]
            if component["status"] in {"blocked", "invalidated"}:
                errors.append(f"{component_id}:status:{component['status']}")
            if component["state"] != expected[component["type"]] or component["status"] != "closed":
                errors.append(f"{component_id}:not_ready:{component['state']}:{component['status']}")
            missing_levels = sorted(
                cumulative_requirements(component["type"], component["state"])
                - current_evidence_levels(state, component_id)
            )
            if missing_levels:
                errors.append(
                    f"{component_id}:missing_current_evidence:" + ",".join(missing_levels)
                )
        if state["open_decisions"] and any(item.get("status") == "open" for item in state["open_decisions"]):
            errors.append("open_decisions")
        return errors
    if current == "P1" and target == "P2":
        readiness = project_transition_requirements({**state, "project": {**state["project"], "state": "P0"}}, "P0", "P1")
        if readiness:
            return ["readiness:" + item for item in readiness]
        levels = {
            level
            for component_id, component in state["components"].items()
            if component.get("status") not in {"blocked", "invalidated"}
            for level in current_evidence_levels(state, component_id)
        }
        return [] if "delivery_acceptance" in levels else ["delivery_acceptance"]
    return []


def _component_ready_for_project(state: dict[str, Any], component_id: str) -> bool:
    component = state.get("components", {}).get(component_id)
    if not isinstance(component, dict):
        return False
    terminal = {"question": "S7", "shared_data": "D3", "artifact": "A3"}
    if (
        component.get("state") != terminal.get(component.get("type"))
        or component.get("status") != "closed"
    ):
        return False
    required = cumulative_requirements(component["type"], component["state"])
    return required.issubset(current_evidence_levels(state, component_id))


def _component_has_delivery_binding(
    state: dict[str, Any], component_ids: set[str]
) -> bool:
    if not component_ids:
        return False
    for component_id in component_ids:
        component = state.get("components", {}).get(component_id, {})
        if "delivery_acceptance" in current_evidence_levels(state, component_id):
            return True
    for artifact in state.get("artifacts", {}).values():
        if not isinstance(artifact, dict):
            continue
        owners = {artifact.get("producer"), *artifact.get("consumers", [])}
        if artifact.get("status") != "superseded" and component_ids.intersection(owners) and (
            artifact.get("role") == "delivery"
            or artifact.get("class") == "delivery"
            or artifact.get("identity_class") == "final"
        ):
            return True
    return False


def _evidence_levels_by_id(
    state: dict[str, Any], evidence_ids: list[str]
) -> set[tuple[str, str]]:
    wanted = set(evidence_ids)
    return {
        (component_id, str(record.get("level")))
        for component_id, component in state.get("components", {}).items()
        for record in component.get("evidence", [])
        if isinstance(record, dict) and record.get("id") in wanted
    }


def reconcile_project_binding_change(
    state: dict[str, Any],
    affected_components: list[str] | set[str],
    *,
    affected_levels: set[tuple[str, str]] | None = None,
    delivery_identity_changed: bool = False,
    delivery_component_changed: bool = False,
) -> str:
    """Downgrade P1/P2 only when a gate's exact binding was affected.

    A required-component readiness loss returns the project to P0.  If only a
    delivery binding changed, a released P2 project returns to P1 while its
    still-current component readiness is preserved.  Optional unrelated work
    never changes the project gate.
    """
    current = state.get("project", {}).get("state")
    if current not in {"P1", "P2"}:
        return str(current)
    affected = set(affected_components)
    required = set(state.get("project", {}).get("required_components", []))
    touched_required = affected & required
    if any(not _component_ready_for_project(state, item) for item in touched_required):
        state["project"]["state"] = "P0"
        return "P0"
    levels = affected_levels or set()
    delivery_evidence_changed = any(
        level == "delivery_acceptance" for _, level in levels
    )
    if current == "P2" and (
        delivery_identity_changed
        or delivery_evidence_changed
        or delivery_component_changed
    ):
        state["project"]["state"] = "P1"
        return "P1"
    return str(current)


def require_transition_execution(
    state: dict[str, Any], execution_id: str, component_id: str, current: str, target: str
) -> dict[str, Any]:
    execution = state.get("executions", {}).get(execution_id)
    if not isinstance(execution, dict) or execution.get("status") != "open":
        raise ContractError("transition execution is not registered and open")
    if execution.get("mode") != "promote" or not execution.get("write_authorized"):
        raise ContractError("transition execution is not promotion-authorized")
    if execution.get("recovery_protocol_version") != "14.0":
        raise ContractError("legacy open execution must be voided and restarted under V14 recovery binding")
    if not isinstance(execution.get("checkpoint_revision"), int):
        raise ContractError("transition execution has no matching identity checkpoint")
    effect = execution.get("state_effect")
    expected = {"component_id": component_id, "from": current, "to": target}
    if effect != expected:
        raise ContractError("transition does not match the state effect sealed at execution start")
    return execution


def do_transition(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if args.project:
        current = state["project"]["state"]
        require_transition_execution(
            state, args.execution_id, state["project"]["id"], current, args.to
        )
        transition = find_transition("project", current, args.to)
        if transition is None:
            raise ContractError(f"illegal project transition {current}->{args.to}")
        missing = project_transition_requirements(state, current, args.to)
        if missing:
            raise ContractError("project transition blocked: " + "; ".join(missing))
        if transition.get("kind") == "reopen":
            if not args.reason or not args.reason_evidence_id:
                raise ContractError("project reopen requires --reason and --reason-evidence-id")
            terminal_revision = latest_transition_revision(state, state["project"]["id"], current)
            candidates = [
                (component_id, item)
                for component_id, component in state["components"].items()
                for item in component.get("evidence", [])
                if item.get("id") == args.reason_evidence_id
            ]
            if len(candidates) != 1:
                raise ContractError("project reopen reason evidence missing or ambiguous")
            _, reason_record = candidates[0]
            if reason_record.get("level") != "selection_rationale" or reason_record.get("status") != "pass" or reason_record.get("recorded_revision", 0) <= terminal_revision:
                raise ContractError("project reopen reason must be a fresh passing selection_rationale")
        state["project"]["state"] = args.to
        return commit(args.project_root, state, "project_transition", state["project"]["id"], {"from": current, "to": args.to, "reason": args.reason, "reason_evidence_id": args.reason_evidence_id})
    if not args.component_id or args.component_id not in state["components"]:
        raise ContractError("valid --component-id required")
    component = state["components"][args.component_id]
    current = component["state"]
    require_transition_execution(
        state, args.execution_id, args.component_id, current, args.to
    )
    transition = find_transition(component["type"], current, args.to)
    if transition is None:
        raise ContractError(f"illegal {component['type']} transition {current}->{args.to}")
    levels = current_evidence_levels(state, args.component_id)
    missing = sorted(set(transition.get("requires", [])) - levels)
    if missing:
        raise ContractError("transition missing passing evidence: " + ",".join(missing))
    if component["status"] in {"blocked", "invalidated"} and transition.get("kind") != "reopen":
        raise ContractError("invalidated or blocked component cannot be promoted")
    affected: list[str] = []
    project_before = state["project"]["state"]
    if transition.get("kind") == "reopen":
        if not args.reason_evidence_id:
            raise ContractError("reopen transition requires --reason-evidence-id")
        reason_record = next((item for item in component["evidence"] if item["id"] == args.reason_evidence_id), None)
        allowed_levels = set(transition.get("reason_levels", []))
        allowed_statuses = set(transition.get("reason_statuses", ["pass"]))
        if (
            reason_record is None
            or reason_record.get("status") not in allowed_statuses
            or (allowed_levels and reason_record.get("level") not in allowed_levels)
        ):
            raise ContractError("reopen reason evidence has the wrong level or status")
        terminal_revision = latest_transition_revision(state, args.component_id, current)
        if reason_record.get("recorded_revision", 0) <= terminal_revision:
            raise ContractError("reopen reason evidence is stale")
        if transition.get("invalidate_consumers"):
            revision = state["revision"] + 1
            affected = [item for item in invalidate_components(
                state, [args.component_id], revision
            ) if item != args.component_id]
        component["status"] = "active"
        component["invalidated_at_revision"] = None
    component["state"] = args.to
    if args.to in {"S7", "D3", "A3"}:
        component["status"] = "closed"
    if transition.get("kind") == "reopen":
        changed_components = {args.component_id, *affected}
        reconcile_project_binding_change(
            state,
            changed_components,
            delivery_component_changed=_component_has_delivery_binding(
                state, changed_components
            ),
        )
    return commit(
        args.project_root, state, "component_transition", args.component_id,
        {
            "from": current, "to": args.to, "required": transition.get("requires", []),
            "reason_evidence_id": args.reason_evidence_id, "affected_components": affected,
            "project_from": project_before, "project_to": state["project"]["state"],
        },
    )


def require_identity_change_execution(
    state: dict[str, Any], execution_id: str, path: str
) -> dict[str, Any]:
    """Bind formal identity mutation to the ChangeSet sealed at execution start."""
    execution = state.get("executions", {}).get(execution_id)
    if not isinstance(execution, dict):
        raise ContractError("identity change execution is not registered")
    if execution.get("status") != "open":
        raise ContractError("identity change execution is not open")
    if not execution.get("write_authorized"):
        raise ContractError("identity change execution is not write authorized")
    change_set = execution.get("change_set")
    if not isinstance(change_set, dict):
        raise ContractError("legacy execution has no sealed ChangeSet; void it and start a corrected execution")
    if path not in set(change_set.get("paths", [])):
        raise ContractError("identity path outside sealed ChangeSet: " + path)
    return execution


def do_register_artifact(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    proposal = load_json(args.proposal)
    errors = validate_artifact_proposal(proposal, args.project_root, state)
    if errors:
        raise ContractError("artifact proposal rejected: " + "; ".join(errors))
    path, rel = relative_safe(args.project_root, proposal["path"])
    require_identity_change_execution(state, args.execution_id, rel)
    if not path.is_file() or path.stat().st_size < 1:
        raise ContractError("artifact file missing or empty")
    if rel in state["artifacts"]:
        raise ContractError("artifact already registered; use refresh-artifact")
    if args.producer not in state["components"] and args.producer != state["project"]["id"]:
        raise ContractError("unknown producer")
    consumers = proposal["consumer_ids"]
    digest = sha256_file(path)
    replacement = proposal.get("replaces")
    if replacement is not None:
        state["artifacts"][replacement]["status"] = "superseded"
    state["artifacts"][rel] = {
        "sha256": digest,
        "size": path.stat().st_size,
        "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "role": proposal["platform_role"],
        "class": proposal["class"],
        "purpose": proposal["purpose"],
        "authorization_basis": proposal["authorization_basis"],
        "lifecycle": proposal["lifecycle"],
        "identity_class": proposal["identity_class"],
        "producer": args.producer,
        "consumers": consumers,
        "status": "registered",
        "validated_at": None,
        "validation_evidence_id": None,
        "supersedes": replacement,
    }
    project_before = state["project"]["state"]
    delivery_identity_changed = (
        proposal["platform_role"] == "delivery"
        or proposal.get("class") == "delivery"
        or proposal.get("identity_class") == "final"
    )
    reconcile_project_binding_change(
        state,
        set(),
        delivery_identity_changed=delivery_identity_changed,
    )
    return commit(
        args.project_root, state, "artifact_registered", rel,
        {
            "sha256": digest, "producer": args.producer, "consumers": consumers,
            "identity_class": proposal["identity_class"],
            "delivery_binding_changed": delivery_identity_changed,
            "affected_components": [], "project_from": project_before,
            "project_to": state["project"]["state"],
            "execution_id": args.execution_id,
        },
    )


def do_validate_artifact(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if args.path not in state["artifacts"]:
        raise ContractError("artifact not registered")
    artifact = state["artifacts"][args.path]
    if artifact["status"] == "superseded":
        raise ContractError("superseded artifact cannot be validated")
    matches = [
        evidence
        for component in state["components"].values()
        for evidence in component.get("evidence", [])
        if evidence.get("id") == args.evidence_id
    ]
    if len(matches) != 1:
        raise ContractError("validation evidence missing or ambiguous")
    evidence = matches[0]
    if evidence.get("level") != "artifact_validation" or evidence.get("status") != "pass":
        raise ContractError("artifact validation requires passing artifact_validation evidence")
    locator = evidence.get("locator", {})
    identity_matches = (
        evidence.get("kind") == "file"
        and locator.get("path") == args.path
        and locator.get("sha256") == artifact["sha256"]
    ) or (
        evidence.get("kind") == "command"
        and locator.get("output_ref") == args.path
        and locator.get("output_sha256") == artifact["sha256"]
        and locator.get("exit_code") == 0
    )
    if not identity_matches:
        raise ContractError("validation evidence is not bound to current artifact identity")
    artifact["status"] = "validated"
    artifact["validated_at"] = now_iso()
    artifact["validation_evidence_id"] = args.evidence_id
    return commit(args.project_root, state, "artifact_validated", args.path, {"evidence_id": args.evidence_id, "sha256": artifact["sha256"]})


def do_refresh_artifact(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root, check_files=False)
    if args.path not in state["artifacts"]:
        raise ContractError("artifact not registered")
    artifact = state["artifacts"][args.path]
    if artifact.get("status") == "superseded":
        raise ContractError("superseded artifact cannot be refreshed")
    if artifact["sha256"] != args.expected_old_sha256:
        raise ContractError("expected old hash does not match registry")
    path, rel = relative_safe(args.project_root, args.path)
    require_identity_change_execution(state, args.execution_id, rel)
    if not path.is_file() or path.stat().st_size < 1:
        raise ContractError("refreshed artifact missing or empty")
    new_hash = sha256_file(path)
    if new_hash == artifact["sha256"]:
        raise ContractError("artifact content has not changed")
    old_hash = artifact["sha256"]
    direct_components, stale_evidence, stale_claims = stale_exact_artifact_evidence(
        state, rel, old_hash
    )
    cleared_validations = clear_invalid_artifact_validations(state)
    producer = artifact["producer"]
    protected_change = artifact_is_protected(artifact)
    seeds: list[str] = []
    affected: list[str] = []
    if protected_change:
        if producer in state["components"]:
            seeds.append(producer)
        seeds.extend(item for item in artifact["consumers"] if item in state["components"])
        affected = invalidate_components(state, seeds, state["revision"] + 1)
    project_before = state["project"]["state"]
    changed_components = set(direct_components) | set(affected)
    affected_levels = _evidence_levels_by_id(state, stale_evidence)
    delivery_identity_changed = (
        artifact.get("role") == "delivery"
        or artifact.get("class") == "delivery"
        or artifact.get("identity_class") == "final"
    )
    reconcile_project_binding_change(
        state,
        changed_components,
        affected_levels=affected_levels,
        delivery_identity_changed=delivery_identity_changed,
        delivery_component_changed=_component_has_delivery_binding(
            state, set(affected)
        ),
    )
    artifact.update({
        "sha256": new_hash,
        "size": path.stat().st_size,
        "status": "registered",
        "validated_at": None,
        "validation_evidence_id": None,
    })
    return commit(
        args.project_root, state, "artifact_refreshed", rel,
        {
            "old_sha256": old_hash, "new_sha256": new_hash,
            "identity_class": artifact["identity_class"],
            "protected_change": protected_change,
            "direct_evidence_components": direct_components,
            "affected_evidence_levels": [
                {"component_id": component_id, "level": level}
                for component_id, level in sorted(affected_levels)
            ],
            "stale_evidence_ids": stale_evidence,
            "stale_claim_ids": stale_claims,
            "cleared_artifact_validations": cleared_validations,
            "affected_components": affected, "project_from": project_before,
            "project_to": state["project"]["state"],
            "execution_id": args.execution_id,
        },
    )


def _formal_scope_paths_for_step(
    state: dict[str, Any], step: dict[str, Any]
) -> list[str]:
    """Return one step's protected closure, plus the full G3 delivery closure."""
    from assess_recovery import scope_paths_for_step

    paths = set(scope_paths_for_step(state, step))
    if step.get("tier") == "G3_RELEASE":
        paths.update(
            path for path, artifact in state.get("artifacts", {}).items()
            if artifact_is_current_formal(artifact) and (
                artifact.get("role") == "delivery"
                or artifact.get("class") == "delivery"
                or artifact.get("identity_class") == "final"
            )
        )
    return sorted(paths)


def _resolved_formal_step(
    project_root: Path, plan_path: Path, step_id: str
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    from lib_v11 import resolve

    plan = load_json(plan_path)
    resolution = resolve(plan, project_root)
    step = next(
        (item for item in resolution.get("steps", []) if item.get("id") == step_id),
        None,
    )
    if step is None:
        raise ContractError("formal step is not present in semantic plan")
    if step.get("status") != "resolved":
        raise ContractError(
            "formal step is blocked: " + "; ".join(step.get("reasons", []))
        )
    return plan, resolution, step


def _gate_for_step(step: dict[str, Any]) -> str:
    return {
        "G1_WORKING": "G1", "G2_CHECKPOINT": "G2", "G3_RELEASE": "G3",
    }.get(str(step.get("tier")), "G1")


def do_begin_recovery(args: argparse.Namespace) -> dict[str, Any]:
    """Open one R1 run and seal its important-file read set."""
    state = require_state(args.project_root, check_files=False)
    recoveries = state.setdefault("recoveries", {})
    if args.recovery_id in recoveries:
        raise ContractError("recovery id already exists")
    open_ids = [
        identifier for identifier, item in recoveries.items()
        if isinstance(item, dict) and item.get("status") == "open"
    ]
    if open_ids:
        raise ContractError("open recovery conflict: " + ",".join(sorted(open_ids)))
    _, resolution, step = _resolved_formal_step(
        args.project_root, args.plan, args.step_id
    )
    from recovery_v14 import (
        assessment_sha256, manifest_sha256, recovery_assessment,
        required_recovery_reads,
    )

    assessment = recovery_assessment(step)
    if assessment.get("level") != "R1_TARGETED":
        raise ContractError("begin-recovery requires a resolved R1_TARGETED step")
    window = step.get("facts", {}).get("window_context")
    if window not in {"same_window", "new_window", "unknown"}:
        raise ContractError("R1 recovery run has an invalid window context")
    required_reads = required_recovery_reads(
        args.project_root, state, step, assessment
    )
    workspace_manifest = build_workspace_manifest(
        args.project_root.resolve(), state.get("watch_roots") or ["."]
    )
    workspace_diff = assessment.get("workspace_diff") or {}
    baseline_paths = sorted(set(
        (list(workspace_manifest) if assessment.get("workspace_baseline_missing") else [])
        + list(workspace_diff.get("added", []))
        + list(workspace_diff.get("deleted", []))
        + list(workspace_diff.get("modified", []))
    ))
    start_revision = state["revision"] + 1
    recoveries[args.recovery_id] = {
        "id": args.recovery_id,
        "status": "open",
        "request_hash": resolution["request_hash"],
        "plan_hash": resolution["plan_hash"],
        "step_id": step["id"],
        "window_context": window,
        "recovery_level": "R1_TARGETED",
        "gate": _gate_for_step(step),
        "component_ids": sorted(step.get("component_ids", [])),
        "scope_paths": _formal_scope_paths_for_step(state, step),
        "assessment": assessment,
        "assessment_sha256": assessment_sha256(assessment),
        "required_reads": required_reads,
        "workspace_manifest_sha256": manifest_sha256(workspace_manifest),
        "resolved_revision": state["revision"],
        "start_revision": start_revision,
        "started_at": now_iso(),
        "end_revision": None,
        "ended_at": None,
        "outcome": "pending",
        "read_receipts": [],
        "reviewed_manifest_sha256": None,
        "recovery_receipt_sha256": None,
        "baseline_required": bool(baseline_paths),
        "baseline_paths": baseline_paths,
        "baseline_revision": None,
        "checkpoint_revision": None,
        "consumed_by_execution": None,
        "void_reason": None,
        "void_failure_code": None,
    }
    return commit(
        args.project_root, state, "recovery_opened", args.recovery_id,
        {
            "plan_hash": resolution["plan_hash"], "step_id": step["id"],
            "window_context": window, "assessment_sha256": assessment_sha256(assessment),
            "required_read_paths": [item["path"] for item in required_reads],
            "baseline_paths": baseline_paths,
        },
    )


def do_close_recovery(args: argparse.Namespace) -> dict[str, Any]:
    """Validate semantic read declarations and close one R1 run."""
    state = require_state(args.project_root, check_files=False)
    receipt = load_json(args.receipt)
    errors: list[str] = []
    schema_path = Path(__file__).resolve().parents[1] / "references/recovery-receipt.schema.json"
    if Draft202012Validator is None or FormatChecker is None:
        errors.append("jsonschema_dependency_missing")
    else:
        validator = Draft202012Validator(
            load_json(schema_path), format_checker=FormatChecker()
        )
        for violation in validator.iter_errors(receipt):
            location = "/".join(str(item) for item in violation.absolute_path) or "$"
            errors.append(f"schema:{location}:{violation.validator}")
    recovery_id = receipt.get("recovery_id")
    record = state.get("recoveries", {}).get(recovery_id)
    if not isinstance(record, dict):
        errors.append("recovery_not_registered")
    elif record.get("status") != "open":
        errors.append("recovery_not_open")
    else:
        if state.get("revision") != record.get("start_revision"):
            errors.append("recovery_state_changed_during_review")
        if Path(str(receipt.get("project_root", ""))).resolve() != args.project_root.resolve():
            errors.append("recovery_receipt_project_root_mismatch")
        if receipt.get("changed_paths") != record.get("assessment", {}).get("changed_paths", []):
            errors.append("recovery_changed_paths_mismatch")
        if receipt.get("affected_components") != record.get("assessment", {}).get("affected_components", []):
            errors.append("recovery_affected_components_mismatch")
        from recovery_v14 import manifest_sha256, validate_read_receipts

        errors.extend(validate_read_receipts(
            args.project_root, record.get("required_reads", []),
            receipt.get("read_receipts"),
        ))
        current_manifest = build_workspace_manifest(
            args.project_root.resolve(), state.get("watch_roots") or ["."]
        )
        if manifest_sha256(current_manifest) != record.get("workspace_manifest_sha256"):
            errors.append("recovery_workspace_changed_during_review")
        conclusion = receipt.get("conclusion", {})
        ready = conclusion.get("status") == "ready"
        non_consistent = [
            item.get("path") for item in receipt.get("read_receipts", [])
            if isinstance(item, dict) and item.get("review_result") != "consistent"
        ]
        if ready and non_consistent:
            errors.append("ready_recovery_has_nonconsistent_reads:" + ",".join(sorted(non_consistent)))
        if ready and conclusion.get("inconsistencies"):
            errors.append("ready_recovery_has_inconsistencies")
        if ready and "protected_registered_identity_changed" in record.get("assessment", {}).get("reasons", []):
            errors.append("changed_protected_identity_cannot_be_recovered_as_ready")
    if errors:
        raise ContractError("recovery receipt rejected: " + "; ".join(sorted(set(errors))))

    from lib_v11 import canonical_json
    from recovery_v14 import manifest_sha256

    current_manifest = build_workspace_manifest(
        args.project_root.resolve(), state.get("watch_roots") or ["."]
    )
    conclusion = receipt["conclusion"]
    record["status"] = "closed"
    record["outcome"] = conclusion["status"]
    record["read_receipts"] = receipt["read_receipts"]
    record["reviewed_manifest_sha256"] = manifest_sha256(current_manifest)
    record["recovery_receipt_sha256"] = sha256_text(canonical_json(receipt))
    record["end_revision"] = state["revision"] + 1
    record["ended_at"] = now_iso()
    return commit(
        args.project_root, state, "recovery_closed", recovery_id,
        {
            "outcome": conclusion["status"],
            "recovery_receipt_sha256": record["recovery_receipt_sha256"],
            "read_paths": [item["path"] for item in receipt["read_receipts"]],
            "next_legal_action": conclusion["next_legal_action"],
            "inconsistencies": conclusion["inconsistencies"],
        },
    )


def do_void_recovery(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root, check_files=False)
    record = state.get("recoveries", {}).get(args.recovery_id)
    if not isinstance(record, dict):
        raise ContractError("recovery is not registered")
    if record.get("status") != "open":
        raise ContractError("only an open recovery can be voided")
    record["status"] = "void"
    record["outcome"] = "void"
    record["end_revision"] = state["revision"] + 1
    record["ended_at"] = now_iso()
    record["void_reason"] = args.reason
    record["void_failure_code"] = args.failure_code
    return commit(
        args.project_root, state, "recovery_voided", args.recovery_id,
        {"failure_code": args.failure_code, "reason": args.reason},
    )


def do_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root, check_files=False)
    if args.expected_revision != state["revision"]:
        raise ContractError("checkpoint expected revision mismatch")
    gate = getattr(args, "gate", "G2")
    if not args.plan or not args.step_id:
        raise ContractError("V14 checkpoint requires --plan and --step-id")
    _, resolution, step = _resolved_formal_step(
        args.project_root, args.plan, args.step_id
    )
    expected_tier = "G3_RELEASE" if gate == "G3" else "G2_CHECKPOINT"
    if step.get("tier") != expected_tier:
        raise ContractError("checkpoint gate and semantic-plan tier mismatch")
    from recovery_v14 import (
        assessment_sha256, closed_recovery_errors, recovery_assessment,
    )

    assessment = recovery_assessment(step)
    recovery_level = assessment["level"]
    recovery_id = getattr(args, "recovery_id", None)
    if recovery_level == "R2_FULL":
        raise ContractError("checkpoint forbidden while R2 recovery barrier is open")
    if recovery_level == "R1_TARGETED":
        recovery_errors = closed_recovery_errors(
            args.project_root, state, resolution, step, recovery_id,
            allow_checkpoint_revision=False,
        )
        if recovery_errors:
            raise ContractError("checkpoint R1 binding rejected: " + "; ".join(recovery_errors))
        recovery_record = state["recoveries"][recovery_id]
        recovery_record["checkpoint_revision"] = state["revision"] + 1
        recovery_hash = recovery_record["assessment_sha256"]
    else:
        if recovery_id:
            raise ContractError("R0 checkpoint must not claim an R1 recovery id")
        recovery_hash = assessment_sha256(assessment)
    normalized_scope = _formal_scope_paths_for_step(state, step)
    return commit(
        args.project_root, state, "identity_checkpoint", state["project"]["id"],
        {
            "gate": gate, "recovery_level": recovery_level,
            "window_context": step.get("facts", {}).get("window_context"),
            "recovery_run_id": recovery_id,
            "recovery_assessment_hash": recovery_hash,
            "plan_hash": resolution["plan_hash"], "step_id": step["id"],
            "scope_paths": normalized_scope,
            "checked_identity_classes": ["milestone", "frozen", "final"],
            "changed_paths": assessment.get("changed_paths", []),
        },
    )


def cumulative_requirements(component_type: str, target: str) -> set[str]:
    machine = load_json(Path(__file__).resolve().parents[1] / "references/state-machine.json")
    initial = INITIAL_STATES[component_type]
    current = initial
    required: set[str] = set()
    seen: set[str] = set()
    while current != target:
        if current in seen:
            raise ContractError("state machine has no acyclic forward path")
        seen.add(current)
        options = [
            item for item in machine["transitions"][component_type]
            if item["from"] == current and item.get("kind") != "reopen"
        ]
        if len(options) != 1:
            raise ContractError(f"cannot derive revalidation path for {component_type}:{target}")
        step = options[0]
        required.update(step.get("requires", []))
        current = step["to"]
    return required


def do_revalidate_component(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if args.component_id not in state["components"]:
        raise ContractError("unknown component")
    component = state["components"][args.component_id]
    if component["status"] != "invalidated":
        raise ContractError("component is not invalidated")
    required = cumulative_requirements(component["type"], component["state"])
    missing = sorted(required - current_evidence_levels(state, args.component_id))
    if missing:
        raise ContractError("revalidation missing current evidence: " + ",".join(missing))
    component["status"] = "closed" if component["state"] in {"S7", "D3", "A3"} else "active"
    component["invalidated_at_revision"] = None
    return commit(
        args.project_root, state, "component_revalidated", args.component_id,
        {"state": component["state"], "required": sorted(required)},
    )


def do_set_dependencies(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if state["project"]["state"] != "P0":
        raise ContractError("dependencies can change only while project is P0")
    if args.component_id not in state["components"]:
        raise ContractError("unknown component")
    requested = sorted(set(args.dependency))
    if args.component_id in requested:
        raise ContractError("component cannot depend on itself")
    unknown = set(requested) - set(state["components"])
    if unknown:
        raise ContractError("unknown dependencies: " + ",".join(sorted(unknown)))
    component = state["components"][args.component_id]
    old = list(component["dependencies"])
    if old == requested:
        raise ContractError("dependencies have not changed")
    for dependency in old:
        state["components"][dependency]["consumers"] = [item for item in state["components"][dependency]["consumers"] if item != args.component_id]
    component["dependencies"] = requested
    for dependency in requested:
        state["components"][dependency]["consumers"] = sorted(set(state["components"][dependency]["consumers"]) | {args.component_id})
    # Changing a declared dependency is an interface change. Invalidate the
    # edited component and its real downstream consumers, never its upstream
    # dependencies, and preserve evidence that does not cite a changed input.
    affected = invalidate_components(
        state, [args.component_id], state["revision"] + 1
    )
    return commit(
        args.project_root, state, "dependencies_changed", args.component_id,
        {"old": old, "new": requested, "affected_components": affected},
    )


def do_record_route(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    executions = state.setdefault("executions", {})
    if args.execution_id in executions:
        raise ContractError("execution id already exists")
    from lib_v11 import resolve
    plan = load_json(args.plan)
    resolution = resolve(plan, args.project_root)
    step = next(
        (item for item in resolution.get("steps", []) if item.get("id") == args.step_id),
        None,
    )
    if step is None:
        raise ContractError("formal execution step is not present in semantic plan")
    if step.get("status") != "resolved":
        raise ContractError("cannot record a blocked formal execution step")
    if step.get("tier") not in {"G2_CHECKPOINT", "G3_RELEASE"}:
        raise ContractError("execution ledger is reserved for G2/G3 formal steps")
    if step.get("mode") not in {"project_readonly", "mutate", "promote", "skill_maintenance"}:
        raise ContractError("formal execution mode is not receipt-capable")
    if step.get("facts", {}).get("state_revision", state["revision"]) != state["revision"]:
        raise ContractError("semantic plan resolution state revision is stale")
    component_ids = sorted(step.get("component_ids", []))
    for existing_id, existing in executions.items():
        if existing.get("status") != "open":
            continue
        overlaps = set(existing.get("component_ids", [])) & set(component_ids)
        same_selector = (
            step.get("component_id") is not None
            and existing.get("component_selector") == step.get("component_id")
        )
        if overlaps or same_selector:
            raise ContractError("open execution conflict: " + existing_id)
    route_ids = [step["route_id"]]
    mode = step["mode"]
    gate = "G3" if step["tier"] == "G3_RELEASE" else "G2"
    from recovery_v14 import (
        assessment_sha256, closed_recovery_errors, manifest_sha256,
        recovery_assessment,
    )

    assessment = recovery_assessment(step)
    recovery = assessment["level"]
    window = step.get("facts", {}).get("window_context")
    recovery_id = getattr(args, "recovery_id", None)
    recovery_receipt_hash = None
    if recovery == "R2_FULL":
        raise ContractError("formal execution forbidden while R2 recovery barrier is open")
    if recovery == "R1_TARGETED":
        recovery_errors = closed_recovery_errors(
            args.project_root, state, resolution, step, recovery_id
        )
        if recovery_errors:
            raise ContractError("formal R1 execution rejected: " + "; ".join(recovery_errors))
        recovery_record = state["recoveries"][recovery_id]
        recovery_hash = recovery_record["assessment_sha256"]
        recovery_receipt_hash = recovery_record["recovery_receipt_sha256"]
    else:
        if recovery_id:
            raise ContractError("R0 execution must not claim an R1 recovery id")
        recovery_record = None
        recovery_hash = assessment_sha256(assessment)

    normalized_scope = _formal_scope_paths_for_step(state, step)
    if not state.get("history"):
        raise ContractError("formal execution requires an immediately preceding identity checkpoint")
    checkpoint = state["history"][-1]
    checkpoint_details = checkpoint.get("details", {}) if isinstance(checkpoint, dict) else {}
    expected_checkpoint = {
        "gate": gate,
        "recovery_level": recovery,
        "window_context": window,
        "recovery_run_id": recovery_id,
        "recovery_assessment_hash": recovery_hash,
        "plan_hash": resolution["plan_hash"],
        "step_id": step["id"],
        "scope_paths": normalized_scope,
    }
    if checkpoint.get("event") != "identity_checkpoint":
        raise ContractError("formal execution requires an immediately preceding identity checkpoint")
    for field, expected in expected_checkpoint.items():
        if checkpoint_details.get(field) != expected:
            raise ContractError("identity checkpoint binding mismatch: " + field)
    checkpoint_revision = checkpoint.get("revision")

    write_authorized = mode in {"mutate", "promote", "skill_maintenance"}
    start_revision = state["revision"] + 1
    if recovery_record is not None:
        current_manifest = build_workspace_manifest(
            args.project_root.resolve(), state.get("watch_roots") or ["."]
        )
        if manifest_sha256(current_manifest) != recovery_record.get("reviewed_manifest_sha256"):
            raise ContractError("reviewed workspace changed before execution start")
        if recovery_record.get("baseline_required") and recovery_record.get("baseline_revision") is None:
            baseline = dict(state.get("workspace_baseline") or {})
            for path in recovery_record.get("baseline_paths", []):
                if path in current_manifest:
                    baseline[path] = current_manifest[path]
                else:
                    baseline.pop(path, None)
            state["workspace_baseline"] = baseline
            recovery_record["baseline_revision"] = start_revision
        recovery_record["consumed_by_execution"] = args.execution_id
    state["last_route"] = {
        "request_hash": resolution["request_hash"],
        "route_ids": route_ids,
        "rule_ids": step["rule_ids"],
        "component_ids": component_ids,
        "resolved_at": now_iso(),
    }
    executions[args.execution_id] = {
        "id": args.execution_id,
        "status": "open",
        "request": resolution["request"],
        "request_hash": resolution["request_hash"],
        "plan_id": resolution.get("plan_id"),
        "plan_hash": resolution["plan_hash"],
        "change_set": step.get("change_set") or {"paths": [], "facets": [], "claim_refs": []},
        "state_effect": step.get("state_effect"),
        "step_ids": [step["id"]],
        "step_modes": {step["id"]: step["mode"]},
        "mode": mode,
        "component_selector": step.get("component_id"),
        "component_map": (
            {step["id"]: step["component_id"]}
            if step.get("component_id") is not None else {}
        ),
        "component_ids": component_ids,
        "route_ids": route_ids,
        "rule_ids": step["rule_ids"],
        "resolved_revision": state["revision"],
        "start_revision": start_revision,
        "recovery_protocol_version": "14.0",
        "recovery": recovery,
        "window_context": window,
        "recovery_run_id": recovery_id,
        "recovery_receipt_hash": recovery_receipt_hash,
        "recovery_assessment_hash": recovery_hash,
        "checkpoint_revision": checkpoint_revision,
        "write_authorized": write_authorized,
        "started_at": now_iso(),
        "end_revision": None,
        "ended_at": None,
        "void_reason": None,
        "void_failure_code": None,
    }
    return commit(
        args.project_root, state, "execution_started", args.execution_id,
        {
            "plan_hash": resolution["plan_hash"],
            "request_hash": resolution["request_hash"],
            "route_ids": route_ids, "step_ids": [step["id"]],
            "recovery_protocol_version": "14.0",
            "recovery": recovery, "window_context": window,
            "recovery_run_id": recovery_id,
            "recovery_receipt_hash": recovery_receipt_hash,
            "recovery_assessment_hash": recovery_hash,
            "checkpoint_revision": checkpoint_revision,
            "write_authorized": write_authorized,
        },
    )


def do_close_execution(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    receipt = load_json(args.receipt)
    from validate_receipt import shape_errors, validate_end
    errors = shape_errors(receipt)
    if not errors:
        receipt_root = (
            Path(receipt["project_root"]).resolve()
            if receipt.get("project_root") else None
        )
        if receipt_root != args.project_root.resolve():
            errors.append("receipt project root does not match command root")
        else:
            errors.extend(validate_end(receipt, None, receipt_root))
    if errors:
        raise ContractError("end receipt rejected: " + "; ".join(sorted(set(errors))))
    execution_id = receipt["execution_id"]
    execution = state.get("executions", {}).get(execution_id)
    if execution is None:
        raise ContractError("receipt execution is not registered")
    if execution.get("status") != "open":
        raise ContractError("receipt execution is not open")
    execution["status"] = "closed"
    execution["end_revision"] = state["revision"] + 1
    execution["ended_at"] = now_iso()
    return commit(
        args.project_root, state, "execution_closed", execution_id,
        {"before_revision": receipt["before_revision"], "after_revision": receipt["after_revision"]},
    )


def do_void_execution(args: argparse.Namespace) -> dict[str, Any]:
    """Terminally close an unfinishable execution without rewriting its history."""
    state = require_state(args.project_root, check_files=False)
    execution = state.get("executions", {}).get(args.execution_id)
    if not isinstance(execution, dict):
        raise ContractError("execution is not registered")
    if execution.get("status") != "open":
        raise ContractError("only an open execution can be voided")
    execution["status"] = "void"
    execution["end_revision"] = state["revision"] + 1
    execution["ended_at"] = now_iso()
    execution["void_reason"] = args.reason
    execution["void_failure_code"] = args.failure_code
    return commit(
        args.project_root, state, "execution_voided", args.execution_id,
        {
            "plan_hash": execution.get("plan_hash"),
            "start_revision": execution.get("start_revision"),
            "failure_code": args.failure_code,
            "reason": args.reason,
        },
    )


def do_set_next(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if args.component_id not in state["components"]:
        raise ContractError("unknown component")
    record = {"id": args.action_id, "component_id": args.component_id, "action": args.action, "blocked_by": sorted(set(args.blocked_by))}
    state["next_actions"] = [item for item in state["next_actions"] if item["id"] != args.action_id]
    state["next_actions"].append(record)
    return commit(args.project_root, state, "next_action_set", args.component_id, record)


def do_add_open_decision(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if any(item.get("id") == args.decision_id for item in state["open_decisions"]):
        raise ContractError("open decision id already exists")
    options = sorted(set(args.option))
    if len(options) < 2:
        raise ContractError("open decision requires at least two options")
    decision = {
        "id": args.decision_id,
        "subject": args.subject,
        "options": options,
        "status": "open",
        "opened_at": now_iso(),
        "resolved_at": None,
        "selected": None,
        "affects": sorted(set(args.affects)),
    }
    state["open_decisions"].append(decision)
    return commit(
        args.project_root, state, "open_decision_added", args.decision_id,
        {"subject": args.subject, "options": options, "affects": decision["affects"]},
    )


def do_resolve_open_decision(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    decision = next(
        (item for item in state["open_decisions"] if item.get("id") == args.decision_id),
        None,
    )
    if decision is None:
        raise ContractError("open decision not found")
    if decision.get("status") != "open":
        raise ContractError("open decision is not open")
    if args.selected not in decision.get("options", []):
        raise ContractError("selected option is not in decision options")
    decision["status"] = "resolved"
    decision["resolved_at"] = now_iso()
    decision["selected"] = args.selected
    return commit(
        args.project_root, state, "open_decision_resolved", args.decision_id,
        {"selected": args.selected},
    )


def do_checkpoint_before_interrupt(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    return commit(
        args.project_root, state, "control_checkpoint_before_interrupt",
        state["project"]["id"],
        {
            "reason": args.reason or "context_compression_or_interruption_boundary",
            "next_action_count": len(state["next_actions"]),
            "open_decision_count": len(state["open_decisions"]),
            "revision": state["revision"] + 1,
        },
    )


def do_update_baseline(args: argparse.Namespace) -> dict[str, Any]:
    """Merge only paths sealed by a closed R1 read receipt."""
    state = require_state(args.project_root, check_files=False)
    if args.expected_revision != state["revision"]:
        raise ContractError("baseline expected revision mismatch")
    record = state.get("recoveries", {}).get(args.recovery_id)
    if not isinstance(record, dict):
        raise ContractError("baseline recovery is not registered")
    if record.get("status") != "closed" or record.get("outcome") != "ready":
        raise ContractError("baseline requires a closed ready recovery")
    if record.get("consumed_by_execution") is not None:
        raise ContractError("baseline recovery was already consumed")
    if state["revision"] not in {
        record.get("end_revision"), record.get("baseline_revision")
    }:
        raise ContractError("baseline recovery state revision advanced")
    if record.get("baseline_revision") is not None:
        raise ContractError("reviewed baseline was already applied")
    watch_roots = state.get("watch_roots") or ["."]
    current_manifest = build_workspace_manifest(args.project_root.resolve(), watch_roots)
    from recovery_v14 import manifest_sha256

    if manifest_sha256(current_manifest) != record.get("reviewed_manifest_sha256"):
        raise ContractError("workspace changed after recovery review")
    baseline = dict(state.get("workspace_baseline") or {})
    for path in record.get("baseline_paths", []):
        if path in current_manifest:
            baseline[path] = current_manifest[path]
        else:
            baseline.pop(path, None)
    state["workspace_baseline"] = baseline
    record["baseline_revision"] = state["revision"] + 1
    return commit(
        args.project_root, state, "workspace_baseline_updated",
        state["project"]["id"],
        {
            "recovery_run_id": args.recovery_id,
            "recovery_receipt_sha256": record.get("recovery_receipt_sha256"),
            "reviewed_paths": record.get("baseline_paths", []),
            "baseline_file_count": len(state["workspace_baseline"]),
        },
    )


def do_validate(args: argparse.Namespace) -> dict[str, Any]:
    state, load_errors = load_state(args.project_root)
    errors = list(load_errors)
    if state is not None:
        errors = validate_state_semantics(
            state, args.project_root, check_files=args.gate in {"G2", "G3"}
        )
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "status": "pass" if not errors else "fail",
        "gate": args.gate,
        "revision": state.get("revision") if state else None,
        "errors": errors,
    }


def do_inspect(args: argparse.Namespace) -> dict[str, Any]:
    """Expose current exact identities and evidence bindings without mutation."""
    state, load_errors = load_state(args.project_root)
    if state is None or load_errors:
        return {
            "schema_version": STATE_SCHEMA_VERSION, "status": "fail", "revision": None,
            "errors": load_errors, "project_state": None,
        }
    from assess_recovery import assess
    return {
        "schema_version": STATE_SCHEMA_VERSION, "status": "pass", "revision": state["revision"],
        "project_state": state["project"]["state"],
        "recovery": assess(
            args.project_root, gate="G1",
            new_window=args.window_context != "same_window",
        ),
        "protected_artifact_identities": {
            path: artifact["sha256"]
            for path, artifact in sorted(state["artifacts"].items())
            if artifact_is_current_formal(artifact)
        },
        "evidence_bindings": {
            component_id: {
                record["id"]: record["binding_hash"]
                for record in component.get("evidence", [])
            }
            for component_id, component in sorted(state["components"].items())
        },
        "errors": [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--project-root", type=Path, required=True)
    init.add_argument("--project-id", required=True)
    init.add_argument("--watch-root", action="append", default=[])

    add = sub.add_parser("add-component")
    add.add_argument("--project-root", type=Path, required=True)
    add.add_argument("--component-id", required=True)
    add.add_argument("--type", choices=sorted(INITIAL_STATES), required=True)
    add.add_argument("--dependency", action="append", default=[])
    add.add_argument("--optional", action="store_true")

    evidence = sub.add_parser("record-evidence")
    evidence.add_argument("--project-root", type=Path, required=True)
    evidence.add_argument("--component-id", required=True)
    evidence.add_argument("--evidence", type=Path, required=True)
    evidence.add_argument("--replace", action="store_true")

    transition = sub.add_parser("transition")
    transition.add_argument("--project-root", type=Path, required=True)
    target = transition.add_mutually_exclusive_group(required=True)
    target.add_argument("--component-id")
    target.add_argument("--project", action="store_true")
    transition.add_argument("--to", required=True)
    transition.add_argument("--reason")
    transition.add_argument("--reason-evidence-id")
    transition.add_argument("--execution-id", required=True)

    register = sub.add_parser("register-artifact")
    register.add_argument("--project-root", type=Path, required=True)
    register.add_argument("--proposal", type=Path, required=True)
    register.add_argument("--producer", required=True)
    register.add_argument("--execution-id", required=True)

    validate_artifact = sub.add_parser("validate-artifact")
    validate_artifact.add_argument("--project-root", type=Path, required=True)
    validate_artifact.add_argument("--path", required=True)
    validate_artifact.add_argument("--evidence-id", required=True)

    refresh = sub.add_parser("refresh-artifact")
    refresh.add_argument("--project-root", type=Path, required=True)
    refresh.add_argument("--path", required=True)
    refresh.add_argument("--expected-old-sha256", required=True)
    refresh.add_argument("--execution-id", required=True)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--project-root", type=Path, required=True)
    checkpoint.add_argument("--expected-revision", type=int, required=True)
    checkpoint.add_argument("--gate", choices=["G2", "G3"], default="G2")
    checkpoint.add_argument("--plan", type=Path)
    checkpoint.add_argument("--step-id")
    checkpoint.add_argument("--recovery-id")
    checkpoint.add_argument(
        "--expected-manifest-sha256",
        help="deprecated V10 compatibility argument; ignored by V12",
    )

    revalidate = sub.add_parser("revalidate-component")
    revalidate.add_argument("--project-root", type=Path, required=True)
    revalidate.add_argument("--component-id", required=True)

    dependencies = sub.add_parser("set-dependencies")
    dependencies.add_argument("--project-root", type=Path, required=True)
    dependencies.add_argument("--component-id", required=True)
    dependencies.add_argument("--dependency", action="append", default=[])

    route = sub.add_parser("record-route")
    route.add_argument("--project-root", type=Path, required=True)
    route.add_argument("--plan", type=Path, required=True)
    route.add_argument("--step-id", required=True)
    route.add_argument("--execution-id", required=True)
    route.add_argument("--recovery-id")

    begin_recovery = sub.add_parser("begin-recovery")
    begin_recovery.add_argument("--project-root", type=Path, required=True)
    begin_recovery.add_argument("--plan", type=Path, required=True)
    begin_recovery.add_argument("--step-id", required=True)
    begin_recovery.add_argument("--recovery-id", required=True)

    close_recovery = sub.add_parser("close-recovery")
    close_recovery.add_argument("--project-root", type=Path, required=True)
    close_recovery.add_argument("--receipt", type=Path, required=True)

    void_recovery = sub.add_parser("void-recovery")
    void_recovery.add_argument("--project-root", type=Path, required=True)
    void_recovery.add_argument("--recovery-id", required=True)
    void_recovery.add_argument("--failure-code", required=True)
    void_recovery.add_argument("--reason", required=True)

    close_execution = sub.add_parser("close-execution")
    close_execution.add_argument("--project-root", type=Path, required=True)
    close_execution.add_argument("--receipt", type=Path, required=True)

    void_execution = sub.add_parser("void-execution")
    void_execution.add_argument("--project-root", type=Path, required=True)
    void_execution.add_argument("--execution-id", required=True)
    void_execution.add_argument("--failure-code", required=True)
    void_execution.add_argument("--reason", required=True)

    next_action = sub.add_parser("set-next")
    next_action.add_argument("--project-root", type=Path, required=True)
    next_action.add_argument("--action-id", required=True)
    next_action.add_argument("--component-id", required=True)
    next_action.add_argument("--action", required=True)
    next_action.add_argument("--blocked-by", action="append", default=[])

    open_add = sub.add_parser("add-open-decision")
    open_add.add_argument("--project-root", type=Path, required=True)
    open_add.add_argument("--decision-id", required=True)
    open_add.add_argument("--subject", required=True)
    open_add.add_argument("--option", action="append", required=True)
    open_add.add_argument("--affects", action="append", default=[])

    open_resolve = sub.add_parser("resolve-open-decision")
    open_resolve.add_argument("--project-root", type=Path, required=True)
    open_resolve.add_argument("--decision-id", required=True)
    open_resolve.add_argument("--selected", required=True)

    interrupt = sub.add_parser("checkpoint-before-interrupt")
    interrupt.add_argument("--project-root", type=Path, required=True)
    interrupt.add_argument("--reason", default=None)

    baseline = sub.add_parser("update-baseline")
    baseline.add_argument("--project-root", type=Path, required=True)
    baseline.add_argument("--recovery-id", required=True)
    baseline.add_argument("--expected-revision", type=int, required=True)

    validate = sub.add_parser("validate")
    validate.add_argument("--project-root", type=Path, required=True)
    validate.add_argument("--gate", choices=["G1", "G2", "G3"], default="G1")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--project-root", type=Path, required=True)
    inspect.add_argument(
        "--window-context", choices=["same_window", "new_window", "unknown"],
        default="new_window",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        handlers = {
            "init": do_init, "add-component": do_add_component, "record-evidence": do_record_evidence,
            "transition": do_transition, "register-artifact": do_register_artifact,
            "validate-artifact": do_validate_artifact, "refresh-artifact": do_refresh_artifact,
            "checkpoint": do_checkpoint, "revalidate-component": do_revalidate_component,
            "set-dependencies": do_set_dependencies,
            "record-route": do_record_route, "close-execution": do_close_execution,
            "void-execution": do_void_execution,
            "begin-recovery": do_begin_recovery,
            "close-recovery": do_close_recovery,
            "void-recovery": do_void_recovery,
            "set-next": do_set_next, "update-baseline": do_update_baseline,
            "add-open-decision": do_add_open_decision,
            "resolve-open-decision": do_resolve_open_decision,
            "checkpoint-before-interrupt": do_checkpoint_before_interrupt,
            "validate": do_validate, "inspect": do_inspect,
        }
        result = handlers[args.command](args)
        status = result.get("status") if args.command in {"validate", "inspect"} else "pass"
        output = result if args.command in {"validate", "inspect"} else {
            "schema_version": STATE_SCHEMA_VERSION, "status": status, "command": args.command,
            "revision": result["revision"], "project_state": result["project"]["state"]
        }
        if args.command == "begin-recovery":
            record = result.get("recoveries", {}).get(args.recovery_id, {})
            output["recovery"] = {
                "id": record.get("id"), "status": record.get("status"),
                "assessment_sha256": record.get("assessment_sha256"),
                "required_reads": record.get("required_reads", []),
                "baseline_paths": record.get("baseline_paths", []),
            }
        elif args.command == "close-recovery":
            record = result.get("recoveries", {}).get(
                load_json(args.receipt).get("recovery_id"), {}
            )
            output["recovery"] = {
                "id": record.get("id"), "status": record.get("status"),
                "outcome": record.get("outcome"),
                "receipt_sha256": record.get("recovery_receipt_sha256"),
            }
        json_output(output)
        return 0 if status == "pass" else 2
    except ContractError as exc:
        json_output({"schema_version": STATE_SCHEMA_VERSION, "status": "fail", "command": args.command, "errors": [str(exc)]})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
