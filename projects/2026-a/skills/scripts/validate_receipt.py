#!/usr/bin/env python3
"""Validate V11 G2/G3 receipts against a semantic plan and exact state facts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from lib_v10 import (
    Draft202012Validator,
    FormatChecker,
    load_json,
    relative_safe,
    sha256_file,
    sha256_text,
)
from lib_v11 import canonical_json, resolve, schema_errors
from state_v11 import (
    artifact_is_current_formal,
    evidence_binding_hash,
    load_state,
    validate_evidence,
    validate_state_semantics,
)


CHECKPOINT_TIERS = {"G2_CHECKPOINT", "G3_RELEASE"}
RECOVERY_PROTOCOLS = {"14.0", "16.0"}


def checkpoint_pair_hash(execution: dict[str, Any]) -> str:
    """Bind both receipts to one formal step and its immutable start point."""
    payload = {
        "execution_id": execution.get("id"),
        "plan_hash": execution.get("plan_hash"),
        "step_id": (execution.get("step_ids") or [None])[0],
        "start_revision": execution.get("start_revision"),
    }
    protocol = execution.get("recovery_protocol_version")
    if protocol in RECOVERY_PROTOCOLS:
        payload.update({
            "recovery_protocol_version": protocol,
            "window_context": execution.get("window_context"),
            "recovery": execution.get("recovery"),
            "recovery_run_id": execution.get("recovery_run_id"),
            "recovery_receipt_hash": execution.get("recovery_receipt_hash"),
            "recovery_assessment_hash": execution.get("recovery_assessment_hash"),
            "checkpoint_revision": execution.get("checkpoint_revision"),
        })
        if protocol == "16.0":
            payload.update({
                "recovery_decision_id": execution.get("recovery_decision_id"),
                "workspace_manifest_before_sha256": execution.get(
                    "workspace_manifest_before_sha256"
                ),
            })
    return sha256_text(canonical_json(payload))


def shape_errors(receipt: Any) -> list[str]:
    if not isinstance(receipt, dict):
        return ["receipt_not_object"]
    errors: list[str] = []
    if receipt.get("schema_version") != "11.0":
        errors.append("schema_version_invalid")
    if Draft202012Validator is None or FormatChecker is None:
        errors.append("jsonschema_dependency_missing")
    else:
        schema = load_json(Path(__file__).resolve().parents[1] / "references/receipt.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for violation in validator.iter_errors(receipt):
            location = "/".join(str(item) for item in violation.absolute_path) or "$"
            errors.append(f"schema:{location}:{violation.validator}:{violation.message}")
    plan = receipt.get("semantic_plan")
    if isinstance(plan, dict):
        errors.extend("semantic_plan:" + item for item in schema_errors(plan))
    else:
        errors.append("semantic_plan_not_object")
    return sorted(set(errors))


def expected_runtime(receipt: dict[str, Any]) -> tuple[dict[str, Any], Path | None]:
    project_root = Path(receipt["project_root"]).resolve() if receipt.get("project_root") else None
    return resolve(receipt["semantic_plan"], project_root), project_root


def resolved_step(receipt: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (item for item in resolution.get("steps", []) if item.get("id") == receipt.get("step_id")),
        None,
    )


def declared_step(receipt: dict[str, Any]) -> dict[str, Any] | None:
    """Return the immutable plan step named by a receipt.

    End receipts deliberately bind this declaration to the execution ledger
    recorded at the start revision.  They must not route the plan again after
    the step has changed authoritative state (for example S6 -> S7).
    """
    plan = receipt.get("semantic_plan")
    if not isinstance(plan, dict):
        return None
    return next(
        (
            item for item in plan.get("steps", [])
            if isinstance(item, dict) and item.get("id") == receipt.get("step_id")
        ),
        None,
    )


def compare_plan_binding(receipt: dict[str, Any]) -> list[str]:
    """Validate receipt fields that are immutable in the submitted plan."""
    errors: list[str] = []
    plan = receipt["semantic_plan"]
    step = declared_step(receipt)
    if receipt.get("request") != plan.get("request"):
        errors.append("request_plan_mismatch")
    if receipt.get("request_hash") != sha256_text(str(receipt.get("request", ""))):
        errors.append("request_hash_mismatch")
    recomputed_plan_hash = sha256_text(canonical_json(plan))
    if receipt.get("plan_hash") != recomputed_plan_hash:
        errors.append("plan_hash_mismatch")
    if step is None:
        return errors + ["step_not_in_semantic_plan"]
    if receipt.get("tier") != step.get("tier"):
        errors.append("tier_mismatch")
    if receipt.get("mode") != step.get("mode"):
        errors.append("mode_mismatch")
    declared_change_set = step.get("change_set") or {
        "paths": [], "facets": [], "claim_refs": [],
    }
    if receipt.get("change_set") != declared_change_set:
        errors.append("change_set_mismatch")
    if receipt.get("tier") not in CHECKPOINT_TIERS:
        errors.append("receipt_not_checkpoint_or_release")
    return sorted(set(errors))


def compare_common(receipt: dict[str, Any], resolution: dict[str, Any]) -> list[str]:
    """Compare a start receipt with the route resolved at its start state."""
    errors = compare_plan_binding(receipt)
    step = resolved_step(receipt, resolution)
    recomputed_plan_hash = sha256_text(canonical_json(receipt["semantic_plan"]))
    if resolution.get("plan_hash") != recomputed_plan_hash:
        errors.append("plan_hash_recomputation_mismatch")
    if step is None:
        return sorted(set(errors + ["step_not_in_start_resolution"]))
    if receipt.get("route_ids") != [step.get("route_id")]:
        errors.append("route_ids_mismatch")
    if receipt.get("rule_ids") != step.get("rule_ids"):
        errors.append("rule_ids_mismatch")
    if sorted(receipt.get("component_ids", [])) != sorted(step.get("component_ids", [])):
        errors.append("component_ids_mismatch")
    step_recovery = step.get("recovery")
    expected_recovery = (
        step_recovery.get("level") if isinstance(step_recovery, dict) else None
    )
    if receipt.get("recovery") != expected_recovery:
        errors.append("recovery_resolution_mismatch")
    return sorted(set(errors))


def _identity_current(
    identity: dict[str, Any],
    state: dict[str, Any],
    project_root: Path | None = None,
    *,
    formal_only: bool = False,
) -> bool:
    if identity.get("kind") != "artifact":
        return False
    artifact = state.get("artifacts", {}).get(identity.get("id"))
    if not isinstance(artifact, dict) or artifact.get("sha256") != identity.get("identity"):
        return False
    if artifact.get("status") == "superseded":
        return False
    if formal_only and not artifact_is_current_formal(artifact):
        return False
    if project_root is not None:
        try:
            path, normalized = relative_safe(project_root, str(identity.get("id", "")))
        except Exception:
            return False
        if normalized != identity.get("id") or not path.is_file():
            return False
        if sha256_file(path) != identity.get("identity"):
            return False
    return True


def _artifact_identity(path: str, artifact: dict[str, Any]) -> dict[str, str]:
    return {
        "kind": "artifact",
        "id": path,
        "identity": str(artifact.get("sha256", "")),
        "facet": "content",
    }


def _canonical_identities(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: (
        str(item.get("kind", "")), str(item.get("id", "")),
        str(item.get("identity", "")), str(item.get("facet", "")),
    ))


def _formal_scope_paths(
    state: dict[str, Any], step: dict[str, Any], tier: str
) -> list[str]:
    """Match execution/checkpoint recovery scope, including G3 delivery assets."""
    from assess_recovery import scope_paths_for_step

    paths = set(scope_paths_for_step(state, step))
    if tier == "G3_RELEASE":
        paths.update(
            path for path, artifact in state.get("artifacts", {}).items()
            if artifact_is_current_formal(artifact) and (
                artifact.get("role") == "delivery"
                or artifact.get("class") == "delivery"
                or artifact.get("identity_class") == "final"
            )
        )
    return sorted(paths)


def _expected_required_identities(
    receipt: dict[str, Any], state: dict[str, Any], step: dict[str, Any] | None
) -> list[dict[str, str]]:
    paths = set(_formal_scope_paths(
        state, step or {}, str(receipt.get("tier", ""))
    ))
    return _canonical_identities([
        _artifact_identity(path, artifact)
        for path, artifact in state.get("artifacts", {}).items()
        if path in paths and artifact_is_current_formal(artifact)
    ])


def _changed_identity_facts(
    state: dict[str, Any], before: int, after: int
) -> tuple[list[dict[str, str]], list[str]]:
    paths: set[str] = set()
    for entry in state.get("history", []):
        if not before < entry.get("revision", -1) <= after:
            continue
        if entry.get("event") in {"artifact_registered", "artifact_refreshed"}:
            subject = entry.get("subject")
            if isinstance(subject, str) and subject:
                paths.add(subject)
        elif entry.get("event") == "compatible_change_reconciled":
            for identity in entry.get("details", {}).get("refreshed_identities", []):
                path = identity.get("id") if isinstance(identity, dict) else None
                if isinstance(path, str) and path:
                    paths.add(path)
    identities = [
        _artifact_identity(path, state["artifacts"][path])
        for path in sorted(paths)
        if path in state.get("artifacts", {})
        and state["artifacts"][path].get("status") != "superseded"
    ]
    return _canonical_identities(identities), sorted(paths)


def _execution_errors(
    receipt: dict[str, Any], resolution: dict[str, Any] | None,
    state: dict[str, Any]
) -> list[str]:
    execution_id = receipt.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id:
        return ["formal_receipt_execution_id_required"]
    execution = state.get("executions", {}).get(execution_id)
    if not isinstance(execution, dict):
        return ["execution_not_registered"]
    errors: list[str] = []
    if execution.get("status") != "open":
        errors.append("execution_not_open")
    if execution.get("request_hash") != receipt.get("request_hash"):
        errors.append("execution_request_hash_mismatch")
    if execution.get("request") != receipt.get("request"):
        errors.append("execution_request_mismatch")
    if execution.get("plan_hash") != receipt.get("plan_hash"):
        errors.append("execution_plan_hash_mismatch")
    if execution.get("change_set") is not None and execution.get("change_set") != receipt.get("change_set"):
        errors.append("execution_change_set_mismatch")
    if receipt.get("step_id") not in execution.get("step_ids", []):
        errors.append("execution_step_mismatch")
    if execution.get("step_ids") != [receipt.get("step_id")]:
        errors.append("execution_not_step_local")
    if execution.get("start_revision") != execution.get("resolved_revision", -1) + 1:
        errors.append("execution_start_revision_not_bound_to_resolution")
    if execution.get("route_ids") != receipt.get("route_ids"):
        errors.append("execution_route_ids_mismatch")
    if execution.get("rule_ids") != receipt.get("rule_ids"):
        errors.append("execution_rule_ids_mismatch")
    if execution.get("mode") != receipt.get("mode"):
        errors.append("execution_mode_mismatch")
    if execution.get("component_ids") != sorted(receipt.get("component_ids", [])):
        errors.append("execution_component_ids_mismatch")
    if "recovery" in receipt and execution.get("recovery") != receipt.get("recovery"):
        errors.append("execution_recovery_mismatch")
    plan_step = declared_step(receipt)
    if plan_step is not None:
        if execution.get("step_modes", {}).get(receipt.get("step_id")) != plan_step.get("mode"):
            errors.append("execution_step_mode_mismatch")
        if execution.get("component_selector") != plan_step.get("component_id"):
            errors.append("execution_component_selector_mismatch")
    if resolution is not None:
        step = resolved_step(receipt, resolution)
        if step is None:
            errors.append("execution_step_missing_from_start_resolution")
        else:
            if execution.get("route_ids") != [step.get("route_id")]:
                errors.append("execution_start_route_ids_mismatch")
            if execution.get("rule_ids") != step.get("rule_ids"):
                errors.append("execution_start_rule_ids_mismatch")
            if execution.get("mode") != step.get("mode"):
                errors.append("execution_start_mode_mismatch")
            if execution.get("component_ids") != sorted(step.get("component_ids", [])):
                errors.append("execution_start_component_ids_mismatch")
    start_entries = [
        entry for entry in state.get("history", [])
        if entry.get("revision") == execution.get("start_revision")
        and entry.get("event") == "execution_started"
        and entry.get("subject") == execution_id
    ]
    if len(start_entries) != 1:
        errors.append("execution_start_history_missing_or_ambiguous")
    else:
        details = start_entries[0].get("details", {})
        if details.get("plan_hash") != execution.get("plan_hash"):
            errors.append("execution_start_history_plan_hash_mismatch")
        if details.get("request_hash") != execution.get("request_hash"):
            errors.append("execution_start_history_request_hash_mismatch")
        if details.get("route_ids") != execution.get("route_ids"):
            errors.append("execution_start_history_route_ids_mismatch")
        if details.get("step_ids") != execution.get("step_ids"):
            errors.append("execution_start_history_step_ids_mismatch")
        if details.get("recovery") != execution.get("recovery"):
            errors.append("execution_start_history_recovery_mismatch")
        if execution.get("recovery_protocol_version") in RECOVERY_PROTOCOLS:
            for field in (
                "recovery_protocol_version", "window_context", "recovery_run_id",
                "recovery_receipt_hash", "recovery_assessment_hash",
                "checkpoint_revision",
            ):
                if details.get(field) != execution.get(field):
                    errors.append("execution_start_history_" + field + "_mismatch")
            if execution.get("recovery_protocol_version") == "16.0":
                for field in (
                    "recovery_decision_id", "workspace_manifest_before_sha256",
                ):
                    if details.get(field) != execution.get(field):
                        errors.append(
                            "execution_start_history_" + field + "_mismatch"
                        )
    if execution.get("recovery_protocol_version") in RECOVERY_PROTOCOLS:
        checkpoint_revision = execution.get("checkpoint_revision")
        checkpoint_entries = [
            entry for entry in state.get("history", [])
            if entry.get("revision") == checkpoint_revision
            and entry.get("event") == "identity_checkpoint"
        ]
        if len(checkpoint_entries) != 1:
            errors.append("execution_checkpoint_history_missing_or_ambiguous")
        else:
            details = checkpoint_entries[0].get("details", {})
            expected = {
                "plan_hash": execution.get("plan_hash"),
                "step_id": (execution.get("step_ids") or [None])[0],
                "recovery_level": execution.get("recovery"),
                "window_context": execution.get("window_context"),
                "recovery_run_id": execution.get("recovery_run_id"),
                "recovery_assessment_hash": execution.get("recovery_assessment_hash"),
            }
            if execution.get("recovery_protocol_version") == "16.0":
                expected.update({
                    "recovery_decision_id": execution.get("recovery_decision_id"),
                    "recovery_receipt_hash": execution.get("recovery_receipt_hash"),
                })
            for field, value in expected.items():
                if details.get(field) != value:
                    errors.append("execution_checkpoint_" + field + "_mismatch")
    if receipt.get("pair_hash") != checkpoint_pair_hash(execution):
        errors.append("receipt_pair_hash_mismatch")
    return errors


def validate_start(
    receipt: dict[str, Any], resolution: dict[str, Any], project_root: Path | None
) -> list[str]:
    errors = compare_common(receipt, resolution)
    if project_root is None:
        return sorted(set(errors + ["checkpoint_receipt_requires_project_root"]))
    state, load_errors = load_state(project_root)
    if state is None:
        return sorted(set(errors + ["start_state_unavailable:" + ";".join(load_errors)]))
    errors.extend(validate_state_semantics(state, project_root, check_files=False))
    errors.extend(_execution_errors(receipt, resolution, state))
    execution = state.get("executions", {}).get(receipt.get("execution_id"), {})
    if receipt.get("state_revision") != execution.get("start_revision"):
        errors.append("state_revision_not_execution_start")
    if receipt.get("state_revision") != state.get("revision"):
        errors.append("state_revision_mismatch")
    step = resolved_step(receipt, resolution)
    expected_blocked = step is None or step.get("status") != "resolved"
    if receipt.get("blocked") != expected_blocked:
        errors.append("blocked_status_mismatch")
    step_recovery = step.get("recovery") if isinstance(step, dict) else None
    expected_recovery = (
        step_recovery.get("level") if isinstance(step_recovery, dict) else None
    )
    if receipt.get("recovery") != expected_recovery:
        errors.append("recovery_mismatch")
    identities = _canonical_identities(receipt.get("required_identities", []))
    expected_identities = _expected_required_identities(receipt, state, step)
    if identities != expected_identities:
        errors.append("required_identities_mismatch")
    for index, identity in enumerate(identities):
        if not _identity_current(
            identity, state, project_root, formal_only=True
        ):
            errors.append(f"required_identity_not_current:{index}")
    return sorted(set(errors))


def transition_facts(
    state: dict[str, Any], before: int, after: int
) -> list[dict[str, str]]:
    facts: list[dict[str, str]] = []
    for entry in state.get("history", []):
        if not before < entry.get("revision", -1) <= after:
            continue
        if entry.get("event") not in {"component_transition", "project_transition"}:
            continue
        details = entry.get("details", {})
        facts.append({
            "component_id": entry.get("subject", ""),
            "from": details.get("from", ""),
            "to": details.get("to", ""),
        })
    return facts


def _validation_errors(
    item: dict[str, Any],
    state: dict[str, Any],
    project_root: Path,
    index: int,
    tier: str,
) -> list[str]:
    errors: list[str] = []
    expected = evidence_binding_hash(
        item.get("component_id", ""),
        item.get("level", ""),
        item.get("input_refs", []),
        item.get("claim_refs", []),
    )
    if item.get("binding_hash") != expected:
        errors.append(f"validation_binding_hash_mismatch:{index}")
    component = state.get("components", {}).get(item.get("component_id"))
    stored = None
    if isinstance(component, dict):
        matches = [
            record for record in component.get("evidence", [])
            if record.get("id") == item.get("id")
        ]
        if len(matches) == 1:
            stored = matches[0]
    if stored is None:
        errors.append(f"validation_evidence_not_registered:{index}")
    else:
        expected_ref = (
            f"state:components/{item.get('component_id')}/evidence/{item.get('id')}"
        )
        if item.get("evidence_ref") != expected_ref:
            errors.append(f"validation_evidence_ref_mismatch:{index}")
        for field in ("level", "status", "input_refs", "claim_refs", "binding_hash"):
            if item.get(field) != stored.get(field):
                errors.append(f"validation_state_evidence_mismatch:{index}:{field}")
        if stored.get("status") != "pass":
            errors.append(f"validation_evidence_not_pass:{index}")
        stored_errors = validate_evidence(
            stored,
            project_root,
            check_files=True,
            state=state,
            component_id=str(item.get("component_id", "")),
            stored=True,
        )
        errors.extend(
            f"validation_state_evidence_invalid:{index}:{error}"
            for error in stored_errors
        )
    for identity in item.get("input_refs", []):
        if identity.get("kind") == "artifact" and not _identity_current(
            identity,
            state,
            project_root,
            formal_only=tier == "G3_RELEASE",
        ):
            errors.append(f"validation_input_not_current:{index}")
    return errors


def _transition_validation_errors(
    transitions: list[dict[str, str]], validations: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[str]:
    """Require the exact evidence levels used by component transitions.

    State mutation already enforces these requirements.  Requiring the same
    current records in the end receipt prevents a structurally valid receipt
    from substituting an unrelated passing validation.
    """
    machine = load_json(Path(__file__).resolve().parents[1] / "references/state-machine.json")
    observed = {
        (item.get("component_id"), item.get("level"))
        for item in validations
        if item.get("status") == "pass"
    }
    errors: list[str] = []
    for transition in transitions:
        component_id = transition.get("component_id")
        component = state.get("components", {}).get(component_id)
        if not isinstance(component, dict):
            # Project transitions use the project id and aggregate readiness;
            # their exact component evidence is checked by state transition
            # logic and delivery validation rather than guessed here.
            continue
        contract = next(
            (
                item for item in machine.get("transitions", {}).get(component.get("type"), [])
                if item.get("from") == transition.get("from")
                and item.get("to") == transition.get("to")
            ),
            None,
        )
        if contract is None:
            errors.append(
                f"receipt_transition_not_in_state_machine:{component_id}:"
                f"{transition.get('from')}:{transition.get('to')}"
            )
            continue
        for level in contract.get("requires", []):
            if (component_id, level) not in observed:
                errors.append(f"transition_validation_missing:{component_id}:{level}")
    return errors


def _compatible_change_validation_errors(
    execution: dict[str, Any], validations: list[dict[str, Any]],
    state: dict[str, Any],
) -> list[str]:
    change = execution.get("compatible_change")
    if not isinstance(change, dict):
        return []
    errors: list[str] = []
    reconciled_revision = execution.get("compatible_change_reconciled_revision")
    if not isinstance(reconciled_revision, int):
        errors.append("compatible_change_not_reconciled")
        return errors
    entries = [
        entry for entry in state.get("history", [])
        if entry.get("revision") == reconciled_revision
        and entry.get("event") == "compatible_change_reconciled"
        and entry.get("subject") == change.get("id")
    ]
    if len(entries) != 1:
        errors.append("compatible_change_reconciliation_history_missing_or_ambiguous")
    interval_events = [
        (entry.get("revision"), entry.get("event"))
        for entry in state.get("history", [])
        if execution.get("start_revision", 0)
        <= entry.get("revision", -1)
        <= reconciled_revision
    ]
    if interval_events != [
        (execution.get("start_revision"), "execution_started"),
        (reconciled_revision, "compatible_change_reconciled"),
    ]:
        errors.append("compatible_change_execution_not_atomic")
    required = {
        (effect.get("component_id"), level)
        for effect in change.get("effects", []) if isinstance(effect, dict)
        for level in effect.get("affected_levels", [])
    }
    observed = {
        (item.get("component_id"), item.get("level"))
        for item in validations if item.get("status") == "pass"
    }
    for component_id, level in sorted(required - observed):
        errors.append(f"compatible_change_validation_missing:{component_id}:{level}")
    snapshots = execution.get("component_snapshots", {})
    for component_id, snapshot in sorted(snapshots.items()):
        component = state.get("components", {}).get(component_id)
        observed = {
            "state": component.get("state") if isinstance(component, dict) else None,
            "status": component.get("status") if isinstance(component, dict) else None,
            "invalidated_at_revision": (
                component.get("invalidated_at_revision")
                if isinstance(component, dict) else None
            ),
        }
        if observed != snapshot:
            errors.append("compatible_change_component_validity_changed:" + component_id)
    for item in validations:
        pair = (item.get("component_id"), item.get("level"))
        if pair not in required:
            continue
        component = state.get("components", {}).get(item.get("component_id"), {})
        record = next(
            (
                candidate for candidate in component.get("evidence", [])
                if candidate.get("id") == item.get("id")
            ),
            None,
        )
        if not isinstance(record, dict) or record.get("recorded_revision", 0) <= execution.get("start_revision", 0):
            errors.append(
                "compatible_change_validation_not_fresh:"
                + str(item.get("component_id")) + ":" + str(item.get("level"))
            )
    return errors


def validate_end(
    receipt: dict[str, Any], resolution: dict[str, Any] | None,
    project_root: Path | None
) -> list[str]:
    # Never route an end receipt against after-state.  The route/rule/state
    # binding was sealed in the open execution ledger at start_revision.
    errors = compare_plan_binding(receipt)
    if project_root is None:
        return sorted(set(errors + ["checkpoint_receipt_requires_project_root"]))
    state, load_errors = load_state(project_root)
    if state is None:
        return sorted(set(errors + ["end_state_unavailable:" + ";".join(load_errors)]))
    errors.extend(validate_state_semantics(state, project_root, check_files=False))
    errors.extend(_execution_errors(receipt, None, state))
    execution = state.get("executions", {}).get(receipt.get("execution_id"), {})
    before = receipt.get("before_revision")
    after = receipt.get("after_revision")
    if not isinstance(before, int) or not isinstance(after, int) or before > after:
        errors.append("revision_order_invalid")
    else:
        if before != execution.get("start_revision"):
            errors.append("before_revision_not_execution_start")
        if after != state.get("revision"):
            errors.append("after_revision_mismatch")
        if receipt.get("state_transitions") != transition_facts(state, before, after):
            errors.append("state_transitions_mismatch")
    changed = _canonical_identities(receipt.get("changed_identities", []))
    change_paths = set(receipt.get("change_set", {}).get("paths", []))
    expected_changed: list[dict[str, Any]] = []
    changed_paths: list[str] = []
    if isinstance(before, int) and isinstance(after, int) and before <= after:
        expected_changed, changed_paths = _changed_identity_facts(state, before, after)
        if changed != expected_changed:
            errors.append("changed_identities_mismatch")
        outside = sorted(set(changed_paths) - change_paths)
        if outside:
            errors.append("registered_identity_delta_outside_change_set:" + ",".join(outside))
    for index, identity in enumerate(changed):
        if identity.get("id") not in change_paths:
            errors.append(f"changed_identity_outside_change_set:{index}")
        if not _identity_current(
            identity,
            state,
            project_root,
            formal_only=receipt.get("tier") == "G3_RELEASE",
        ):
            errors.append(f"changed_identity_not_current:{index}")
    validations = receipt.get("validations", [])
    if not validations:
        errors.append("checkpoint_validations_empty")
    for index, item in enumerate(validations):
        errors.extend(_validation_errors(
            item, state, project_root, index, str(receipt.get("tier"))
        ))
    if isinstance(before, int) and isinstance(after, int) and before <= after:
        errors.extend(_transition_validation_errors(
            transition_facts(state, before, after), validations, state
        ))
    errors.extend(_compatible_change_validation_errors(
        execution, validations, state
    ))
    actual_issues = sorted(
        item.get("id", "")
        for item in state.get("open_decisions", [])
        if item.get("status") == "open"
    )
    if receipt.get("open_issues") != actual_issues:
        errors.append("open_issues_mismatch")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = load_json(args.receipt)
    errors = shape_errors(receipt)
    if not errors:
        if receipt["receipt_type"] == "start":
            resolution, project_root = expected_runtime(receipt)
            errors.extend(validate_start(receipt, resolution, project_root))
        else:
            project_root = (
                Path(receipt["project_root"]).resolve()
                if receipt.get("project_root") else None
            )
            errors.extend(validate_end(receipt, None, project_root))
    report = {
        "schema_version": "11.0",
        "status": "pass" if not errors else "fail",
        "receipt_type": receipt.get("receipt_type") if isinstance(receipt, dict) else None,
        "errors": sorted(set(errors)),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
