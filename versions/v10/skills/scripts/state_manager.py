#!/usr/bin/env python3
"""Create and atomically update V10 typed project state."""

from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
from typing import Any

from lib_v10 import (
    STATE_REL, ContractError, build_workspace_manifest, component_subject_hash, dump_json,
    json_output, load_json, load_state, manifest_sha256, now_iso, relative_safe,
    root_fingerprint, sha256_file, transitive_consumers, validate_artifact_proposal,
    validate_evidence, validate_state_semantics,
)


INITIAL_STATES = {"question": "S0", "shared_data": "D0", "artifact": "A0"}


def state_path(project_root: Path) -> Path:
    return project_root / STATE_REL


def require_state(project_root: Path, check_files: bool = True) -> dict[str, Any]:
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
    errors = validate_state_semantics(state, project_root, check_files=True)
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
    for raw_root in watch_roots:
        watched, _ = relative_safe(project_root, raw_root)
        if not watched.exists():
            raise ContractError(f"watch root does not exist: {raw_root}")
    state: dict[str, Any] = {
        "schema_version": "10.0",
        "revision": 1,
        "project": {
            "id": args.project_id,
            "state": "P0",
            "root_fingerprint": root_fingerprint(project_root),
            "required_components": [],
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        "components": {},
        "artifacts": {},
        "open_decisions": [],
        "next_actions": [],
        "last_route": None,
        "executions": {},
        "watch_roots": watch_roots,
        "workspace_manifest": build_workspace_manifest(project_root, watch_roots),
        "history": [{
            "revision": 1, "event": "project_initialized", "at": timestamp,
            "subject": args.project_id, "details": {"watch_roots": watch_roots}
        }],
    }
    errors = validate_state_semantics(state, project_root, check_files=True)
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
        "evidence_epoch_revision": 0,
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
        if evidence.get("level") not in reopen_levels:
            raise ContractError("closed component accepts only fresh evidence or a reason required for a declared reopen")
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
    affected: list[str] = []
    project_before = state["project"]["state"]
    if evidence.get("status") == "fail" and evidence.get("level") in closed_failure_levels:
        revision = state["revision"] + 1
        affected = [
            item for item in transitive_consumers(state["components"], [args.component_id])
            if item != args.component_id
        ]
        for component_id in affected:
            consumer = state["components"][component_id]
            consumer["status"] = "invalidated"
            consumer["invalidated_at_revision"] = revision
            consumer["evidence_epoch_revision"] = revision
            for record in consumer.get("evidence", []):
                if record.get("status") == "pass":
                    record["status"] = "stale"
        component["status"] = "invalidated"
        component["invalidated_at_revision"] = revision
        component["evidence_epoch_revision"] = revision
        for record in component.get("evidence", []):
            if record.get("status") == "pass":
                record["status"] = "stale"
        if project_before in {"P1", "P2"}:
            state["project"]["state"] = "P0"
    return commit(
        args.project_root, state, "evidence_recorded", args.component_id,
        {
            "evidence_id": evidence["id"], "level": evidence["level"],
            "status": evidence["status"], "kind": evidence["kind"],
            "replaced": existing is not None, "affected_components": affected,
            "project_from": project_before, "project_to": state["project"]["state"],
        },
    )


def current_evidence_levels(state: dict[str, Any], component_id: str) -> set[str]:
    component = state["components"][component_id]
    current_hash = component_subject_hash(state, component_id)
    epoch = component["evidence_epoch_revision"]
    latest: dict[str, dict[str, Any]] = {}
    for item in component.get("evidence", []):
        level = item.get("level")
        if (
            isinstance(level, str)
            and item.get("recorded_revision", -1) >= epoch
            and item.get("subject_id") == component_id
            and item.get("subject_hash") == current_hash
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
        if state["open_decisions"] and any(item.get("status") == "open" for item in state["open_decisions"]):
            errors.append("open_decisions")
        return errors
    if current == "P1" and target == "P2":
        readiness = project_transition_requirements({**state, "project": {**state["project"], "state": "P0"}}, "P0", "P1")
        if readiness:
            return ["readiness:" + item for item in readiness]
        levels = {
            evidence.get("level")
            for component in state["components"].values()
            for evidence in component.get("evidence", [])
            if evidence.get("status") == "pass"
        }
        return [] if "delivery_acceptance" in levels else ["delivery_acceptance"]
    return []


def do_transition(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if args.project:
        current = state["project"]["state"]
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
            affected = [
                item for item in transitive_consumers(state["components"], [args.component_id])
                if item != args.component_id
            ]
            for component_id in affected:
                consumer = state["components"][component_id]
                consumer["status"] = "invalidated"
                consumer["invalidated_at_revision"] = revision
                consumer["evidence_epoch_revision"] = revision
                for record in consumer.get("evidence", []):
                    if record.get("status") == "pass":
                        record["status"] = "stale"
            if project_before in {"P1", "P2"}:
                state["project"]["state"] = "P0"
        component["status"] = "active"
        component["evidence_epoch_revision"] = state["revision"] + 1
        component["invalidated_at_revision"] = None
        for record in component["evidence"]:
            if record.get("status") == "pass":
                record["status"] = "stale"
    component["state"] = args.to
    if args.to in {"S7", "D3", "A3"}:
        component["status"] = "closed"
    return commit(
        args.project_root, state, "component_transition", args.component_id,
        {
            "from": current, "to": args.to, "required": transition.get("requires", []),
            "reason_evidence_id": args.reason_evidence_id, "affected_components": affected,
            "project_from": project_before, "project_to": state["project"]["state"],
        },
    )


def do_register_artifact(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    proposal = load_json(args.proposal)
    errors = validate_artifact_proposal(proposal, args.project_root, state)
    if errors:
        raise ContractError("artifact proposal rejected: " + "; ".join(errors))
    path, rel = relative_safe(args.project_root, proposal["path"])
    if not path.is_file() or path.stat().st_size < 1:
        raise ContractError("artifact file missing or empty")
    if rel in state["artifacts"]:
        raise ContractError("artifact already registered; use refresh-artifact")
    if args.producer not in state["components"] and args.producer != state["project"]["id"]:
        raise ContractError("unknown producer")
    allowed_roles = {
        "source": {"source"}, "code": {"source", "intermediate"},
        "data": {"source", "intermediate", "result"}, "result": {"result"},
        "manuscript": {"manuscript"}, "visual": {"visual"},
        "delivery": {"delivery"}, "control": {"control"},
    }
    if args.role not in allowed_roles[proposal["class"]]:
        raise ContractError("proposal class and registered role are inconsistent")
    consumers = proposal["consumer_ids"]
    digest = sha256_file(path)
    replacement = proposal.get("replaces")
    if replacement is not None:
        state["artifacts"][replacement]["status"] = "superseded"
    state["artifacts"][rel] = {
        "sha256": digest,
        "size": path.stat().st_size,
        "media_type": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "role": args.role,
        "lifecycle": proposal["lifecycle"],
        "producer": args.producer,
        "consumers": consumers,
        "status": "registered",
        "validated_at": None,
        "validation_evidence_id": None,
        "supersedes": replacement,
    }
    seeds = [args.producer] if args.producer in state["components"] else []
    seeds.extend(item for item in consumers if item in state["components"])
    affected = transitive_consumers(state["components"], seeds)
    invalidated = []
    for component_id in affected:
        component = state["components"][component_id]
        if component["evidence"] or component["state"] != INITIAL_STATES[component["type"]]:
            component["status"] = "invalidated"
            component["invalidated_at_revision"] = state["revision"] + 1
            component["evidence_epoch_revision"] = state["revision"] + 1
            for record in component["evidence"]:
                if record.get("status") == "pass":
                    record["status"] = "stale"
            invalidated.append(component_id)
    project_before = state["project"]["state"]
    if invalidated and project_before in {"P1", "P2"}:
        state["project"]["state"] = "P0"
    state["workspace_manifest"][rel] = {"sha256": digest, "size": path.stat().st_size}
    return commit(args.project_root, state, "artifact_registered", rel, {"sha256": digest, "producer": args.producer, "consumers": consumers, "affected_components": invalidated, "project_from": project_before, "project_to": state["project"]["state"]})


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
    if artifact["sha256"] != args.expected_old_sha256:
        raise ContractError("expected old hash does not match registry")
    path, rel = relative_safe(args.project_root, args.path)
    if not path.is_file() or path.stat().st_size < 1:
        raise ContractError("refreshed artifact missing or empty")
    new_hash = sha256_file(path)
    if new_hash == artifact["sha256"]:
        raise ContractError("artifact content has not changed")
    producer = artifact["producer"]
    seeds = [producer] if producer in state["components"] else []
    seeds.extend(item for item in artifact["consumers"] if item in state["components"])
    affected = transitive_consumers(state["components"], seeds)
    for component_id in affected:
        state["components"][component_id]["status"] = "invalidated"
        state["components"][component_id]["invalidated_at_revision"] = state["revision"] + 1
        state["components"][component_id]["evidence_epoch_revision"] = state["revision"] + 1
        for record in state["components"][component_id]["evidence"]:
            if record.get("status") == "pass":
                record["status"] = "stale"
    project_before = state["project"]["state"]
    if project_before in {"P1", "P2"}:
        state["project"]["state"] = "P0"
    old_hash = artifact["sha256"]
    artifact.update({
        "sha256": new_hash,
        "size": path.stat().st_size,
        "status": "registered",
        "validated_at": None,
        "validation_evidence_id": None,
    })
    state["workspace_manifest"][rel] = {"sha256": new_hash, "size": path.stat().st_size}
    return commit(
        args.project_root, state, "artifact_refreshed", rel,
        {"old_sha256": old_hash, "new_sha256": new_hash, "affected_components": affected, "project_from": project_before, "project_to": state["project"]["state"]},
    )


def do_checkpoint(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root, check_files=True)
    if args.expected_revision != state["revision"]:
        raise ContractError("checkpoint expected revision mismatch")
    old_hash = manifest_sha256(state["workspace_manifest"])
    if args.expected_manifest_sha256 != old_hash:
        raise ContractError("checkpoint expected manifest hash mismatch")
    from assess_recovery import assess
    recovery = assess(args.project_root)
    if recovery["level"] != "R0_CONTINUE":
        raise ContractError("checkpoint requires R0 with no unclassified diff")
    current = build_workspace_manifest(args.project_root, state["watch_roots"])
    new_hash = manifest_sha256(current)
    state["workspace_manifest"] = current
    return commit(
        args.project_root, state, "workspace_checkpoint", state["project"]["id"],
        {"old_manifest_sha256": old_hash, "new_manifest_sha256": new_hash, "manifest_diff": recovery.get("manifest_diff", {}), "file_count": len(current)},
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
        raise ContractError("revalidation missing fresh evidence: " + ",".join(missing))
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
    affected = transitive_consumers(state["components"], [args.component_id])
    for component_id in affected:
        state["components"][component_id]["status"] = "invalidated"
        state["components"][component_id]["invalidated_at_revision"] = state["revision"] + 1
        state["components"][component_id]["evidence_epoch_revision"] = state["revision"] + 1
        for record in state["components"][component_id]["evidence"]:
            if record.get("status") == "pass":
                record["status"] = "stale"
    return commit(
        args.project_root, state, "dependencies_changed", args.component_id,
        {"old": old, "new": requested, "affected_components": affected},
    )


def do_record_route(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if args.execution_id in state["executions"]:
        raise ContractError("execution id already exists")
    from resolve_route import resolve
    raw_component_map = getattr(args, "component_map", None)
    try:
        component_map = json.loads(raw_component_map) if raw_component_map else {}
    except json.JSONDecodeError as exc:
        raise ContractError(f"component map is not valid JSON: {exc}") from exc
    if not isinstance(component_map, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in component_map.items()
    ):
        raise ContractError("component map must be an object of string keys and component IDs")
    resolution = resolve(args.request, args.project_root, args.component_id, component_map)
    if resolution.get("status") != "resolved":
        raise ContractError("cannot record unresolved route")
    if resolution.get("mode") in {"advisory_readonly", "project_readonly"}:
        raise ContractError("readonly route recording would mutate project state; use a stateless validated receipt")
    if resolution.get("state_revision") != state["revision"]:
        raise ContractError("resolution state revision is stale")
    component_ids = sorted({item for node in resolution["route_nodes"] for item in node["component_ids"]})
    recovery_needed = any(node["id"] not in {"RT.PROJECT.INIT", "RT.PROJECT.ADVISE"} for node in resolution["route_nodes"])
    if recovery_needed:
        from assess_recovery import assess
        recovery = resolution.get("runtime_facts", {}).get("recovery_level") or assess(args.project_root)["level"]
    else:
        recovery = "not_applicable"
    write_mode = resolution["mode"] in {"mutate", "promote", "skill_maintenance"}
    recovery_action = any(
        route_id in {"RT.PROJECT.RESUME", "RT.PROJECT.RECOVER.MISSING"}
        for route_id in resolution["route_ids"]
    )
    explicit_full_recovery = bool(
        resolution.get("runtime_facts", {}).get("request_explicit_full_recovery")
    )
    write_authorized = write_mode and (
        recovery in {"R0_CONTINUE", "not_applicable"}
        or (recovery == "R1_TARGETED" and recovery_action)
        or (recovery == "R2_FULL" and recovery_action and explicit_full_recovery)
    )
    start_revision = state["revision"] + 1
    state["last_route"] = {
        "request_hash": resolution["request_hash"],
        "route_ids": resolution["route_ids"],
        "rule_ids": resolution["rule_ids"],
        "component_ids": component_ids,
        "resolved_at": now_iso(),
    }
    state["executions"][args.execution_id] = {
        "id": args.execution_id,
        "status": "open",
        "request": args.request,
        "request_hash": resolution["request_hash"],
        "mode": resolution["mode"],
        "component_selector": args.component_id,
        "component_map": dict(sorted(component_map.items())),
        "component_ids": component_ids,
        "route_ids": resolution["route_ids"],
        "rule_ids": resolution["rule_ids"],
        "resolved_revision": state["revision"],
        "start_revision": start_revision,
        "start_manifest": state["workspace_manifest"],
        "start_manifest_sha256": manifest_sha256(state["workspace_manifest"]),
        "recovery": recovery,
        "write_authorized": write_authorized,
        "started_at": now_iso(),
        "end_revision": None,
        "ended_at": None,
    }
    return commit(
        args.project_root, state, "execution_started", args.execution_id,
        {"request_hash": resolution["request_hash"], "route_ids": resolution["route_ids"], "component_selector": args.component_id, "component_map": dict(sorted(component_map.items())), "recovery": recovery, "write_authorized": write_authorized},
    )


def do_close_execution(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    receipt = load_json(args.receipt)
    from validate_receipt import expected_runtime, shape_errors, validate_end
    errors = shape_errors(receipt)
    if not errors:
        resolution, receipt_root = expected_runtime(receipt)
        if receipt_root != args.project_root.resolve():
            errors.append("receipt project root does not match command root")
        else:
            errors.extend(validate_end(receipt, resolution, receipt_root))
    if errors:
        raise ContractError("end receipt rejected: " + "; ".join(sorted(set(errors))))
    execution_id = receipt["execution_id"]
    execution = state["executions"][execution_id]
    execution["status"] = "closed"
    execution["end_revision"] = state["revision"] + 1
    execution["ended_at"] = now_iso()
    return commit(
        args.project_root, state, "execution_closed", execution_id,
        {"before_revision": receipt["before_revision"], "after_revision": receipt["after_revision"]},
    )


def do_set_next(args: argparse.Namespace) -> dict[str, Any]:
    state = require_state(args.project_root)
    if args.component_id not in state["components"]:
        raise ContractError("unknown component")
    record = {"id": args.action_id, "component_id": args.component_id, "action": args.action, "blocked_by": sorted(set(args.blocked_by))}
    state["next_actions"] = [item for item in state["next_actions"] if item["id"] != args.action_id]
    state["next_actions"].append(record)
    return commit(args.project_root, state, "next_action_set", args.component_id, record)


def do_validate(args: argparse.Namespace) -> dict[str, Any]:
    state, load_errors = load_state(args.project_root)
    errors = list(load_errors)
    if state is not None:
        errors = validate_state_semantics(state, args.project_root, check_files=True)
    return {"schema_version": "10.0", "status": "pass" if not errors else "fail", "revision": state.get("revision") if state else None, "errors": errors}


def do_inspect(args: argparse.Namespace) -> dict[str, Any]:
    """Expose the current CAS and evidence-binding values without mutation."""
    state, load_errors = load_state(args.project_root)
    if state is None or load_errors:
        return {
            "schema_version": "10.0", "status": "fail", "revision": None,
            "errors": load_errors, "project_state": None,
        }
    from assess_recovery import assess
    return {
        "schema_version": "10.0", "status": "pass", "revision": state["revision"],
        "project_state": state["project"]["state"],
        "workspace_manifest_sha256": manifest_sha256(state["workspace_manifest"]),
        "recovery": assess(args.project_root),
        "component_subject_hashes": {
            component_id: component_subject_hash(state, component_id)
            for component_id in sorted(state["components"])
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

    register = sub.add_parser("register-artifact")
    register.add_argument("--project-root", type=Path, required=True)
    register.add_argument("--proposal", type=Path, required=True)
    register.add_argument("--producer", required=True)
    register.add_argument("--role", choices=["source", "intermediate", "result", "manuscript", "visual", "delivery", "control"], required=True)

    validate_artifact = sub.add_parser("validate-artifact")
    validate_artifact.add_argument("--project-root", type=Path, required=True)
    validate_artifact.add_argument("--path", required=True)
    validate_artifact.add_argument("--evidence-id", required=True)

    refresh = sub.add_parser("refresh-artifact")
    refresh.add_argument("--project-root", type=Path, required=True)
    refresh.add_argument("--path", required=True)
    refresh.add_argument("--expected-old-sha256", required=True)

    checkpoint = sub.add_parser("checkpoint")
    checkpoint.add_argument("--project-root", type=Path, required=True)
    checkpoint.add_argument("--expected-revision", type=int, required=True)
    checkpoint.add_argument("--expected-manifest-sha256", required=True)

    revalidate = sub.add_parser("revalidate-component")
    revalidate.add_argument("--project-root", type=Path, required=True)
    revalidate.add_argument("--component-id", required=True)

    dependencies = sub.add_parser("set-dependencies")
    dependencies.add_argument("--project-root", type=Path, required=True)
    dependencies.add_argument("--component-id", required=True)
    dependencies.add_argument("--dependency", action="append", default=[])

    route = sub.add_parser("record-route")
    route.add_argument("--project-root", type=Path, required=True)
    route.add_argument("--request", required=True)
    route.add_argument("--execution-id", required=True)
    route.add_argument("--component-id")
    route.add_argument("--component-map", help="JSON object mapping a route ID or object to a component ID")

    close_execution = sub.add_parser("close-execution")
    close_execution.add_argument("--project-root", type=Path, required=True)
    close_execution.add_argument("--receipt", type=Path, required=True)

    next_action = sub.add_parser("set-next")
    next_action.add_argument("--project-root", type=Path, required=True)
    next_action.add_argument("--action-id", required=True)
    next_action.add_argument("--component-id", required=True)
    next_action.add_argument("--action", required=True)
    next_action.add_argument("--blocked-by", action="append", default=[])

    validate = sub.add_parser("validate")
    validate.add_argument("--project-root", type=Path, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--project-root", type=Path, required=True)
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
            "set-next": do_set_next, "validate": do_validate, "inspect": do_inspect,
        }
        result = handlers[args.command](args)
        status = result.get("status") if args.command in {"validate", "inspect"} else "pass"
        output = result if args.command in {"validate", "inspect"} else {
            "schema_version": "10.0", "status": status, "command": args.command,
            "revision": result["revision"], "project_state": result["project"]["state"]
        }
        json_output(output)
        return 0 if status == "pass" else 2
    except ContractError as exc:
        json_output({"schema_version": "10.0", "status": "fail", "command": args.command, "errors": [str(exc)]})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
