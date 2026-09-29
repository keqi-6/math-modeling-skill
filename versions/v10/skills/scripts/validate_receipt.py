#!/usr/bin/env python3
"""Validate receipt shape and recompute every security-relevant runtime field."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from assess_recovery import assess
from lib_v10 import (
    Draft202012Validator, FormatChecker, build_workspace_manifest, json_output,
    load_json, load_state, relative_safe, sha256_file, sha256_text,
    validate_artifact_proposal, validate_state_semantics,
)
from resolve_route import resolve


MODES = {"advisory_readonly", "project_readonly", "mutate", "promote", "skill_maintenance"}


def shape_errors(receipt: Any) -> list[str]:
    if not isinstance(receipt, dict):
        return ["receipt_not_object"]
    common = {"receipt_type", "schema_version", "request", "request_hash", "project_root", "execution_id", "component_id", "component_map", "mode", "route_ids", "rule_ids", "component_ids"}
    if receipt.get("receipt_type") == "start":
        required = common | {"state_revision", "recovery", "planned_artifacts", "blocked"}
    elif receipt.get("receipt_type") == "end":
        required = common | {"before_revision", "after_revision", "changed_artifacts", "validations", "state_transitions", "open_issues", "next_actions"}
    else:
        return ["receipt_type_invalid"]
    errors = []
    missing = required - receipt.keys()
    extra = receipt.keys() - required
    if missing:
        errors.append("missing_fields:" + ",".join(sorted(missing)))
    if extra:
        errors.append("extra_fields:" + ",".join(sorted(extra)))
    if receipt.get("schema_version") != "10.0":
        errors.append("schema_version_invalid")
    if Draft202012Validator is None or FormatChecker is None:
        errors.append("jsonschema_dependency_missing")
    else:
        schema = load_json(Path(__file__).resolve().parents[1] / "references/receipt.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for violation in validator.iter_errors(receipt):
            location = "/".join(str(item) for item in violation.absolute_path) or "$"
            errors.append(f"schema:{location}:{violation.validator}")
    if receipt.get("mode") not in MODES:
        errors.append("mode_invalid")
    for field in ("route_ids", "rule_ids", "component_ids"):
        if not isinstance(receipt.get(field), list) or len(receipt.get(field, [])) != len(set(receipt.get(field, []))):
            errors.append(field + "_invalid")
    component_map = receipt.get("component_map")
    if not isinstance(component_map, dict) or any(
        not isinstance(key, str) or not isinstance(value, str) for key, value in component_map.items()
    ):
        errors.append("component_map_invalid")
    return errors


def expected_runtime(receipt: dict[str, Any]) -> tuple[dict[str, Any], Path | None]:
    project_root = Path(receipt["project_root"]).resolve() if receipt.get("project_root") else None
    resolution = resolve(receipt["request"], project_root, receipt.get("component_id"), receipt.get("component_map", {}))
    return resolution, project_root


def compare_common(receipt: dict[str, Any], resolution: dict[str, Any], allow_post_state: bool) -> list[str]:
    errors: list[str] = []
    if receipt["request_hash"] != sha256_text(receipt["request"]):
        errors.append("request_hash_mismatch")
    if receipt["mode"] != resolution["mode"]:
        errors.append("mode_mismatch")
    if not allow_post_state:
        if receipt["route_ids"] != resolution["route_ids"]:
            errors.append("route_ids_mismatch")
        if receipt["rule_ids"] != resolution["rule_ids"]:
            errors.append("rule_ids_mismatch")
        expected_components = sorted({item for node in resolution["route_nodes"] for item in node["component_ids"]})
        if sorted(receipt["component_ids"]) != expected_components:
            errors.append("component_ids_mismatch")
    return errors


def validate_start(receipt: dict[str, Any], resolution: dict[str, Any], project_root: Path | None) -> list[str]:
    errors = compare_common(receipt, resolution, allow_post_state=False)
    state = None
    execution = None
    stateless_readonly = False
    if project_root is not None:
        state, load_errors = load_state(project_root)
        if state is None:
            errors.append("start_state_unavailable:" + ";".join(load_errors))
        elif not receipt.get("execution_id"):
            if receipt["mode"] not in {"advisory_readonly", "project_readonly"}:
                errors.append("execution_id_required_for_writable_project")
            elif receipt["state_revision"] != state["revision"]:
                errors.append("readonly_state_revision_mismatch")
        else:
            execution = state.get("executions", {}).get(receipt["execution_id"])
            if execution is None:
                errors.append("execution_not_registered")
            elif execution.get("status") != "open":
                errors.append("execution_not_open")
            else:
                expected = {
                    "request": receipt["request"], "request_hash": receipt["request_hash"],
                    "mode": receipt["mode"], "component_selector": receipt.get("component_id"),
                    "component_map": dict(sorted(receipt.get("component_map", {}).items())),
                    "component_ids": sorted(receipt["component_ids"]),
                    "route_ids": receipt["route_ids"], "rule_ids": receipt["rule_ids"],
                }
                for field, value in expected.items():
                    if execution.get(field) != value:
                        errors.append("execution_" + field + "_mismatch")
                if receipt["state_revision"] != execution.get("start_revision"):
                    errors.append("state_revision_mismatch")
    elif receipt.get("execution_id") is not None:
        errors.append("rootless_execution_id_must_be_null")
    elif receipt["state_revision"] is not None:
        errors.append("rootless_state_revision_must_be_null")
    expected_blocked = resolution["status"] != "resolved" or (
        execution is not None and receipt["mode"] in {"mutate", "promote", "skill_maintenance"}
        and not execution.get("write_authorized")
    )
    if receipt["blocked"] != expected_blocked:
        errors.append("blocked_status_mismatch")
    recovery_needed = any(
        node["id"] not in {"RT.PROJECT.INIT", "RT.SKILL.AUDIT", "RT.SKILL.CHANGE", "RT.PROJECT.ADVISE"}
        for node in resolution["route_nodes"]
    ) and project_root is not None
    expected_recovery = execution.get("recovery") if execution is not None else (
        assess(project_root)["level"] if recovery_needed else "not_applicable"
    )
    if receipt["recovery"] != expected_recovery:
        errors.append("recovery_mismatch")
    if not isinstance(receipt["planned_artifacts"], list):
        errors.append("planned_artifacts_not_list")
    elif receipt["planned_artifacts"]:
        if receipt["mode"] in {"advisory_readonly", "project_readonly"}:
            errors.append("readonly_planned_artifacts_forbidden")
        if execution is not None and not execution.get("write_authorized"):
            errors.append("execution_does_not_authorize_artifacts")
        if project_root is None:
            errors.append("planned_artifacts_without_project_root")
        else:
            state, _ = load_state(project_root)
            for index, proposal in enumerate(receipt["planned_artifacts"]):
                for error in validate_artifact_proposal(proposal, project_root, state):
                    errors.append(f"planned_artifact:{index}:{error}")
    return errors


def transition_facts(state: dict[str, Any], before: int | None, after: int | None) -> list[dict[str, str]]:
    facts: list[dict[str, str]] = []
    if before is None or after is None:
        return facts
    for entry in state.get("history", []):
        if not (before < entry.get("revision", -1) <= after):
            continue
        if entry.get("event") not in {"component_transition", "project_transition"}:
            continue
        details = entry.get("details", {})
        facts.append({"component_id": entry.get("subject", ""), "from": details.get("from", ""), "to": details.get("to", "")})
    return facts


def artifact_delta(start: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path in sorted(set(start) | set(current)):
        if path not in start:
            result.append({"path": path, "sha256": current[path]["sha256"], "status": "created"})
        elif path not in current:
            result.append({"path": path, "sha256": None, "status": "deleted"})
        elif start[path] != current[path]:
            result.append({"path": path, "sha256": current[path]["sha256"], "status": "modified"})
    return result


def validation_facts(state: dict[str, Any], before: int, after: int) -> list[dict[str, Any]]:
    return [
        {
            "id": entry.get("details", {}).get("evidence_id", ""),
            "status": entry.get("details", {}).get("status", ""),
            "kind": entry.get("details", {}).get("kind", ""),
            "evidence_ref": entry.get("details", {}).get("evidence_id", ""),
        }
        for entry in state.get("history", [])
        if before < entry.get("revision", -1) <= after and entry.get("event") == "evidence_recorded"
    ]


def validate_end(receipt: dict[str, Any], resolution: dict[str, Any], project_root: Path | None) -> list[str]:
    errors: list[str] = []
    if receipt["request_hash"] != sha256_text(receipt["request"]):
        errors.append("request_hash_mismatch")
    state = None
    execution = None
    if project_root is None:
        errors.extend(compare_common(receipt, resolution, allow_post_state=False))
        if receipt.get("execution_id") is not None:
            errors.append("rootless_execution_id_must_be_null")
        if receipt["before_revision"] is not None or receipt["after_revision"] is not None:
            errors.append("revision_without_project")
        if receipt["changed_artifacts"] or receipt["validations"] or receipt["state_transitions"]:
            errors.append("rootless_end_cannot_claim_stateful_facts")
    else:
        state, load_errors = load_state(project_root)
        if state is None:
            errors.append("end_state_unavailable:" + ";".join(load_errors))
        else:
            errors.extend("end_state:" + item for item in validate_state_semantics(state, project_root, check_files=True))
            execution_id = receipt.get("execution_id")
            if not execution_id:
                if receipt["mode"] not in {"advisory_readonly", "project_readonly"}:
                    errors.append("execution_id_required_for_writable_project")
                else:
                    stateless_readonly = True
                    errors.extend(compare_common(receipt, resolution, allow_post_state=False))
                    if receipt["before_revision"] != state["revision"] or receipt["after_revision"] != state["revision"]:
                        errors.append("readonly_revision_changed")
                    if receipt["changed_artifacts"] or receipt["validations"] or receipt["state_transitions"]:
                        errors.append("readonly_receipt_claims_stateful_delta")
                    recovery = assess(project_root)
                    if recovery.get("level") != "R0_CONTINUE":
                        errors.append("readonly_workspace_not_r0")
            else:
                execution = state.get("executions", {}).get(execution_id)
                if execution is None:
                    errors.append("execution_not_registered")
                elif execution.get("status") != "open":
                    errors.append("execution_already_closed")
                else:
                    expected = {
                        "request": receipt["request"], "request_hash": receipt["request_hash"],
                        "mode": receipt["mode"], "component_selector": receipt.get("component_id"),
                        "component_map": dict(sorted(receipt.get("component_map", {}).items())),
                        "component_ids": sorted(receipt["component_ids"]),
                        "route_ids": receipt["route_ids"], "rule_ids": receipt["rule_ids"],
                    }
                    for field, value in expected.items():
                        if execution.get(field) != value:
                            errors.append("execution_" + field + "_mismatch")
                    if receipt["before_revision"] != execution.get("start_revision"):
                        errors.append("before_revision_mismatch")
                    if receipt["after_revision"] != state["revision"]:
                        errors.append("after_revision_mismatch")
                    if receipt["before_revision"] > receipt["after_revision"]:
                        errors.append("revision_order_invalid")
                    actual_transitions = transition_facts(state, receipt["before_revision"], receipt["after_revision"])
                    if receipt["state_transitions"] != actual_transitions:
                        errors.append("state_transitions_mismatch")
                    try:
                        live_manifest = build_workspace_manifest(project_root, state["watch_roots"])
                        actual_changes = artifact_delta(execution["start_manifest"], live_manifest)
                        if receipt["changed_artifacts"] != actual_changes:
                            errors.append("changed_artifacts_mismatch")
                        for index, item in enumerate(actual_changes):
                            if item["status"] != "deleted" and item["path"] not in state.get("artifacts", {}):
                                errors.append(f"changed_artifact:{index}:not_registered")
                    except Exception as exc:
                        errors.append("manifest_reconstruction_failed:" + str(exc))
                    actual_validations = validation_facts(state, receipt["before_revision"], receipt["after_revision"])
                    if receipt["validations"] != actual_validations:
                        errors.append("validations_mismatch")
                    if not execution.get("write_authorized") and (
                        receipt["after_revision"] != execution.get("start_revision")
                        or receipt["changed_artifacts"]
                        or receipt["state_transitions"]
                        or receipt["validations"]
                    ):
                        errors.append("unauthorized_execution_has_delta")
                    if execution["mode"] in {"advisory_readonly", "project_readonly"}:
                        post_start_events = [
                            entry for entry in state.get("history", [])
                            if receipt["before_revision"] < entry.get("revision", -1) <= receipt["after_revision"]
                        ]
                        if post_start_events or actual_changes:
                            errors.append("readonly_execution_has_delta")

    if not isinstance(receipt.get("open_issues"), list) or any(not isinstance(item, str) for item in receipt.get("open_issues", [])):
        errors.append("open_issues_invalid")
    if not isinstance(receipt.get("next_actions"), list) or any(not isinstance(item, str) for item in receipt.get("next_actions", [])):
        errors.append("next_actions_invalid")
    if state is not None and (execution is not None or stateless_readonly):
        actual_issues = sorted(item.get("id", "") for item in state.get("open_decisions", []) if item.get("status") == "open")
        if receipt["open_issues"] != actual_issues:
            errors.append("open_issues_mismatch")
        actual_next = sorted(item.get("id", "") for item in state.get("next_actions", []))
        if receipt["next_actions"] != actual_next:
            errors.append("next_actions_mismatch")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    receipt = load_json(args.receipt)
    errors = shape_errors(receipt)
    if not errors:
        resolution, project_root = expected_runtime(receipt)
        if receipt["receipt_type"] == "start":
            errors.extend(validate_start(receipt, resolution, project_root))
        else:
            errors.extend(validate_end(receipt, resolution, project_root))
    result = {"schema_version": "10.0", "status": "pass" if not errors else "fail", "receipt_type": receipt.get("receipt_type"), "errors": sorted(set(errors))}
    json_output(result)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
