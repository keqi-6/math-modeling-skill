#!/usr/bin/env python3
"""Validate the focused V14 cross-contract invariants seen in real projects."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    errors: list[str] = []

    ownership = load(root / "references/ownership-contract.json")
    platform = load(root / "references/project-platform-contract.json")
    artifact = load(root / "references/artifact-contract.json")
    state_schema = load(root / "references/state.schema.json")
    recovery_receipt_schema = load(root / "references/recovery-receipt.schema.json")
    state_machine = load(root / "references/state-machine.json")
    plan_schema = load(root / "references/semantic-plan.schema.json")
    routes = load(root / "references/route-contract.json")
    release_policy = load(root / "references/release-policy.json")
    release_plan = load(root / "evals/release/release-plan.json")

    platform_owner = ownership.get("classes", {}).get("project_platform_contract", {})
    if platform_owner.get("owner") != "references/project-platform-contract.json":
        errors.append("platform_owner_missing")
    roles = platform.get("roles", {})
    artifact_roles = set(artifact.get("properties", {}).get("platform_role", {}).get("enum", []))
    if set(roles) != artifact_roles:
        errors.append("artifact_platform_role_enum_drift")
    for role, contract in roles.items():
        for pattern in contract.get("path_patterns", []):
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"platform_path_regex_invalid:{role}:{exc}")

    transition_route = next(
        (item for item in routes.get("routes", []) if item.get("id") == "RT.STATE.TRANSITION"),
        {},
    )
    transition_action = routes.get("action_contracts", {}).get("RT.STATE.TRANSITION", {}).get("transition", {})
    allowed_events = set(
        routes.get("event_policy", {}).get("route_allowed_events", {}).get("RT.STATE.TRANSITION", [])
    )
    if transition_route.get("object") != "state" or transition_route.get("modes") != ["promote"]:
        errors.append("state_transition_route_missing_or_not_promote")
    if transition_action.get("requires_state_effect") is not True or "state_transition" not in allowed_events:
        errors.append("state_transition_action_contract_incomplete")
    route_types = set(transition_route.get("component_types", []))
    route_states = set(transition_route.get("states", []))
    for component_type, transitions in state_machine.get("transitions", {}).items():
        for edge in transitions:
            if component_type not in route_types or edge.get("from") not in route_states:
                errors.append(
                    f"transition_without_route_witness:{component_type}:{edge.get('from')}:{edge.get('to')}"
                )

    step_object_enum = set(
        plan_schema.get("$defs", {}).get("step", {}).get("properties", {})
        .get("object", {}).get("enum", [])
    )
    if "state" not in step_object_enum:
        errors.append("semantic_plan_state_object_missing")
    recovery_state_adapter = routes.get("legacy_scope_adapters", {}).get(
        "recovery_state_object", {}
    )
    if recovery_state_adapter != {
        "actual_object": "state",
        "frozen_scope_token": "project",
        "route_selector": "@recovery",
        "required_event": "recovery_assessment",
        "provenance": "state_transition_is_a_project_recovery_control_surface",
    }:
        errors.append("recovery_state_object_scope_adapter_missing")

    execution_schema = state_schema.get("$defs", {}).get("execution", {})
    statuses = set(execution_schema.get("properties", {}).get("status", {}).get("enum", []))
    if statuses != {"open", "closed", "void"}:
        errors.append("execution_lifecycle_incomplete")
    if "change_set" not in execution_schema.get("properties", {}):
        errors.append("execution_change_set_not_sealed")
    execution_properties = execution_schema.get("properties", {})
    for field in (
        "recovery_protocol_version", "window_context", "recovery_run_id",
        "recovery_receipt_hash", "recovery_assessment_hash", "checkpoint_revision",
    ):
        if field not in execution_properties:
            errors.append("execution_recovery_binding_missing:" + field)
    if "recoveries" not in state_schema.get("properties", {}):
        errors.append("r1_recovery_registry_missing")
    if recovery_receipt_schema.get("properties", {}).get("receipt_type", {}).get("const") != "r1_targeted_recovery":
        errors.append("r1_recovery_receipt_contract_missing")
    recovery_owner = ownership.get("classes", {}).get("recovery_receipt_machine_contract", {})
    if recovery_owner.get("owner") != "references/recovery-receipt.schema.json":
        errors.append("r1_recovery_receipt_owner_missing")
    manager_source = (root / "scripts/state_manager.py").read_text(encoding="utf-8")
    receipt_source = (root / "scripts/validate_receipt.py").read_text(encoding="utf-8")
    for token in (
        "require_identity_change_execution", "do_void_execution", "open execution conflict",
        "do_begin_recovery", "do_close_recovery", "closed_recovery_errors",
        "baseline requires a closed ready recovery",
    ):
        if token not in manager_source:
            errors.append("state_manager_contract_missing:" + token)
    if "execution_change_set_mismatch" not in receipt_source:
        errors.append("receipt_change_set_binding_missing")
    for token in ("recovery_resolution_mismatch", "execution_recovery_mismatch"):
        if token not in receipt_source:
            errors.append("receipt_recovery_binding_missing:" + token)

    if "skill_authorization" not in plan_schema.get("properties", {}):
        errors.append("skill_authorization_schema_missing")
    resolver_source = (root / "scripts/lib_v11.py").read_text(encoding="utf-8")
    for token in (
        "skill_maintenance_must_be_isolated_plan", "validate_project_platform_paths",
        "formal_project_step_requires_recovery_assessment",
    ):
        if token not in resolver_source:
            errors.append("resolver_guard_missing:" + token)

    policy_drivers = [item.get("id") for item in release_policy.get("active_drivers", [])]
    plan_drivers = release_plan.get("required_drivers", [])
    if policy_drivers != ["package", "contracts", "scenarios"] or plan_drivers != policy_drivers:
        errors.append("release_driver_contract_drift")
    required_cases = [
        "SCENARIO.PLATFORM.PLAN_PREFLIGHT",
        "SCENARIO.STATE.D0_D1_ROUNDTRIP",
        "SCENARIO.IDENTITY.PREFLIGHT_AND_VOID",
        "SCENARIO.RECOVERY.R1_NEW_WINDOW_ROUNDTRIP",
        "SCENARIO.SKILL.EXPLICIT_AUTHORIZATION",
        "SCENARIO.STATE.ALL_EDGES_RESOLVE",
    ]
    if (
        release_policy.get("required_case_ids") != required_cases
        or release_plan.get("required_case_ids") != required_cases
    ):
        errors.append("release_required_case_contract_drift")
    recovery_source = (root / "scripts/recovery_v14.py").read_text(encoding="utf-8")
    assess_source = (root / "scripts/assess_recovery.py").read_text(encoding="utf-8")
    for token in ("official_input", "frozen_process", "authoritative_state", "evidence_source"):
        if token not in recovery_source:
            errors.append("r1_required_read_role_missing:" + token)
    if "new_window: bool = True" not in assess_source:
        errors.append("recovery_default_not_fail_safe")

    result = {
        "schema_version": "14.0",
        "driver": "contracts",
        "status": "pass" if not errors else "fail",
        "checks": [
            "CONTRACT.PLATFORM_ADMISSION", "CONTRACT.TRANSITION_TOTALITY",
            "CONTRACT.IDENTITY_PREFLIGHT", "CONTRACT.EXECUTION_LIFECYCLE",
            "CONTRACT.R1_READ_RECEIPT", "CONTRACT.RECOVERY_BINDING",
            "CONTRACT.SKILL_AUTHORIZATION", "CONTRACT.RELEASE_DRIVERS",
        ],
        "evidence": {
            "platform_roles": len(roles),
            "state_edges": sum(len(items) for items in state_machine.get("transitions", {}).values()),
            "release_drivers": len(policy_drivers),
        },
        "errors": sorted(set(errors)),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
