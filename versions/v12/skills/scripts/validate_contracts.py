#!/usr/bin/env python3
"""Validate the frozen atom corpus and V11 semantic-plan contracts.

This validator is deliberately static.  It proves that every route has at
least one structured action/mode/tier/state witness; it never interprets route
regexes and never broadcasts potential route events to make rules reachable.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from lib_v10 import (
    Draft202012Validator,
    FormatChecker,
    SKILL_ROOT,
    json_output,
    load_json,
    load_rules,
    rule_matches_route,
)


EXPECTED_ACTIVE_RULES = 206
TIERS = ("G0_ADVISORY", "G1_WORKING", "G2_CHECKPOINT", "G3_RELEASE")
TIER_RANK = {tier: index for index, tier in enumerate(TIERS)}
MODES = {
    "advisory_readonly", "project_readonly", "mutate", "promote", "skill_maintenance"
}
OBJECTS = {
    "project", "literature", "data", "model", "verification",
    "manuscript", "visual", "delivery", "skill",
}
COMPONENT_TYPES = {"project", "question", "shared_data", "artifact", "skill", "none"}
ROUTE_SELECTORS = {"*", "@write", "@recovery"}
REQUIRED_OWNER_CLASSES = {
    "controller_protocol", "policy_atom", "runtime_policy_contract",
    "semantic_plan_contract", "route_machine_contract", "state_machine_contract",
    "artifact_machine_contract", "receipt_machine_contract", "change_machine_contract",
}


def _schema_errors(schema: dict[str, Any], value: Any, label: str) -> list[str]:
    if Draft202012Validator is None or FormatChecker is None:
        return ["jsonschema_dependency_missing"]
    errors: list[str] = []
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:  # jsonschema exposes several schema subclasses
        return [f"{label}:invalid_schema:{exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for violation in validator.iter_errors(value):
        location = "/".join(str(item) for item in violation.absolute_path) or "$"
        errors.append(f"{label}:{location}:{violation.validator}:{violation.message}")
    return sorted(errors)


def _strings(value: Any, label: str, *, nonempty: bool = True) -> tuple[list[str], list[str]]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        return [], [f"{label}:must_be_string_array"]
    if nonempty and not value:
        return [], [f"{label}:must_not_be_empty"]
    if len(value) != len(set(value)):
        return value, [f"{label}:duplicates"]
    return value, []


def collect_test_ids(root: Path) -> tuple[set[str], dict[str, list[str]], list[str]]:
    ids: set[str] = set()
    occurrences: dict[str, list[str]] = {}
    errors: list[str] = []
    for path in sorted((root / "evals").rglob("*.json")):
        try:
            payload = load_json(path)
        except (OSError, ValueError) as exc:
            errors.append(f"eval_registry_invalid:{path.relative_to(root)}:{exc}")
            continue
        if not isinstance(payload, dict):
            continue
        cases = payload.get("cases")
        if cases is None:
            continue
        if not isinstance(cases, list):
            errors.append(f"eval_registry_cases_not_array:{path.relative_to(root)}")
            continue
        for case in cases:
            if not isinstance(case, dict) or not isinstance(case.get("id"), str):
                errors.append(f"eval_case_missing_id:{path.relative_to(root)}")
                continue
            identifier = case["id"]
            ids.add(identifier)
            occurrences.setdefault(identifier, []).append(path.relative_to(root).as_posix())
    return ids, occurrences, errors


def validate_semantic_plan_schema(
    root: Path,
) -> tuple[dict[str, Any], Draft202012Validator | None, list[str]]:
    errors: list[str] = []
    schema = load_json(root / "references/semantic-plan.schema.json")
    if Draft202012Validator is None or FormatChecker is None:
        return schema, None, ["jsonschema_dependency_missing"]
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return schema, None, [f"semantic_plan_schema_invalid:{exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    if schema.get("properties", {}).get("schema_version", {}).get("const") != "11.0":
        errors.append("semantic_plan_schema_version_not_v11")
    if set(schema.get("required", [])) != {"schema_version", "request", "steps"}:
        errors.append("semantic_plan_top_required_fields")
    step = schema.get("$defs", {}).get("step", {})
    required_step = {
        "id", "tier", "mode", "object", "action", "component_id",
        "events", "facts", "depends_on",
    }
    if set(step.get("required", [])) != required_step:
        errors.append("semantic_plan_step_required_fields")
    properties = step.get("properties", {})
    if set(properties.get("tier", {}).get("enum", [])) != set(TIERS):
        errors.append("semantic_plan_tier_vocabulary")
    if set(properties.get("mode", {}).get("enum", [])) != MODES:
        errors.append("semantic_plan_mode_vocabulary")
    if set(properties.get("object", {}).get("enum", [])) != OBJECTS:
        errors.append("semantic_plan_object_vocabulary")
    working = properties.get("working_context", {})
    if set(working.get("required", [])) != {"component_type", "state"}:
        errors.append("semantic_plan_working_context_shape")
    change_set = schema.get("$defs", {}).get("change_set", {})
    if set(change_set.get("required", [])) != {"paths", "facets", "claim_refs"}:
        errors.append("semantic_plan_change_set_shape")

    witness = {
        "schema_version": "11.0",
        "request": "原请求仅供 Agent 语义理解，机器验证结构。",
        "steps": [{
            "id": "advice", "tier": "G0_ADVISORY", "mode": "advisory_readonly",
            "object": "project", "action": "advise", "component_id": None,
            "events": [], "facts": {}, "depends_on": [],
        }],
    }
    for violation in validator.iter_errors(witness):
        location = "/".join(str(item) for item in violation.absolute_path) or "$"
        errors.append(f"semantic_plan_positive_witness:{location}:{violation.message}")
    return schema, validator, sorted(errors)


def validate_runtime_policy(root: Path) -> tuple[dict[str, Any], list[str]]:
    policy = load_json(root / "references/runtime-policy.json")
    errors: list[str] = []
    required = {
        "schema_version", "owner", "principle", "rule_semantics", "activation",
        "decomposed_request_semantics", "window_recovery_policy", "tiers",
        "minimum_tiers", "closure", "natural_pause", "recovery_execution_barrier",
        "dangerous_runtime_actions", "hard_blocks", "not_hard_blocks",
    }
    if not isinstance(policy, dict) or not required.issubset(policy):
        return policy, ["runtime_policy_top_shape"]
    if policy.get("schema_version") != "11.0" or policy.get("owner") != "references/runtime-policy.json":
        errors.append("runtime_policy_identity")
    if set(policy.get("tiers", {})) != set(TIERS):
        errors.append("runtime_policy_tier_vocabulary")
    tier_fields = {
        "purpose", "project_state", "recovery", "receipt", "artifact_policy",
        "evidence_persistence", "identity_check_scope",
    }
    for tier, details in policy.get("tiers", {}).items():
        if not isinstance(details, dict) or not tier_fields.issubset(details):
            errors.append(f"runtime_policy_tier_shape:{tier}")
    if policy.get("tiers", {}).get("G1_WORKING", {}).get("multi_file_changes") is not True:
        errors.append("runtime_policy_g1_multifile_not_enabled")
    minimum = policy.get("minimum_tiers", {})
    expected_minimum = {
        "advisory_readonly": "G0_ADVISORY", "project_readonly": "G0_ADVISORY",
        "mutate": "G1_WORKING", "promote": "G2_CHECKPOINT",
        "skill_maintenance": "G1_WORKING", "final_delivery": "G3_RELEASE",
        "skill_release": "G3_RELEASE",
    }
    if minimum != expected_minimum:
        errors.append("runtime_policy_minimum_tiers")
    activation = policy.get("activation", {})
    if activation.get("authority") != "agent_semantic_plan_then_contract_validation":
        errors.append("runtime_policy_activation_authority")
    if activation.get("request_text_role") != "audit_input_only":
        errors.append("runtime_policy_request_text_role")
    forbidden = set(activation.get("forbidden_synthetic_events", []))
    if forbidden != {
        "global_events_for_every_request", "all_writable_events_for_every_write",
        "all_possible_route_events_before_action",
    }:
        errors.append("runtime_policy_forbidden_synthetic_events")
    decomposed = policy.get("decomposed_request_semantics", {})
    if set(decomposed) != {
        "raw_request", "mode_uniqueness", "write_route_uniqueness", "authorization",
        "multi_step_continuation", "no_one_step_gate",
    }:
        errors.append("runtime_policy_decomposed_request_shape")
    pause = policy.get("natural_pause", {})
    if (
        pause.get("tier") != "G1_WORKING"
        or pause.get("route") != "RT.PROJECT.RESUME"
        or pause.get("action") != "pause"
        or pause.get("events") != ["handoff"]
        or not isinstance(pause.get("does_not_imply"), list)
    ):
        errors.append("runtime_policy_natural_pause")
    window_policy = policy.get("window_recovery_policy", {})
    if not isinstance(window_policy, dict) or window_policy.get("new_window_minimum_level") != "R1_TARGETED":
        errors.append("runtime_policy_window_recovery_new_window_not_r1")
    if window_policy.get("unknown_default") != "new_window":
        errors.append("runtime_policy_window_recovery_unknown_default_not_new_window")
    if window_policy.get("r0_allowed_only_when") != "window_context=same_window and protected_registered_identities_consistent":
        errors.append("runtime_policy_window_recovery_r0_boundary")
    barrier = policy.get("recovery_execution_barrier", {})
    barrier_fields = {
        "open_when", "safe_readonly_routes", "recovery_write_route",
        "allowed_write_paths", "allowed_write_prefixes", "blocked_events",
        "identity_reconstruction", "closure",
    }
    if not isinstance(barrier, dict) or not barrier_fields.issubset(barrier):
        errors.append("runtime_policy_recovery_barrier_shape")
    else:
        if barrier.get("recovery_write_route") != "RT.PROJECT.RECOVER.MISSING":
            errors.append("runtime_policy_recovery_write_route")
        allowed = barrier.get("allowed_write_paths", []) + barrier.get("allowed_write_prefixes", [])
        if any(not isinstance(path, str) or not path.startswith(".modeling/") or ".." in Path(path).parts for path in allowed):
            errors.append("runtime_policy_recovery_write_scope")
        identity = barrier.get("identity_reconstruction", {})
        if not isinstance(identity, dict) or identity.get("recomputation_authorized") is not False:
            errors.append("runtime_policy_r2_recomputation_boundary")
    dangerous = policy.get("dangerous_runtime_actions", {})
    if (
        not isinstance(dangerous, dict)
        or dangerous.get("ordinary_g1_affected") is not False
        or dangerous.get("execution_entry") != "scripts/run_authorized_action.py"
        or dangerous.get("grant_persistence_at_g1") != "none"
    ):
        errors.append("runtime_policy_dangerous_action_scope")
    for field in ("hard_blocks", "not_hard_blocks"):
        if not isinstance(policy.get(field), list) or not policy[field]:
            errors.append(f"runtime_policy_{field}_shape")
    return policy, sorted(errors)


def _minimum_tier(route: dict[str, Any], action: str, mode: str, policy: dict[str, Any]) -> str:
    minimum = policy.get("minimum_tiers", {})
    if route.get("id") == "RT.DELIVERY.FINAL":
        return minimum.get("final_delivery", "G3_RELEASE")
    if route.get("id") == "RT.SKILL.CHANGE" and action == "release":
        return minimum.get("skill_release", "G3_RELEASE")
    return minimum.get(mode, "G0_ADVISORY")


def validate_route_contract(
    root: Path, runtime_policy: dict[str, Any]
) -> tuple[dict[str, Any], set[str], set[str], list[dict[str, str]], list[str]]:
    contract = load_json(root / "references/route-contract.json")
    errors: list[str] = []
    witnesses: list[dict[str, str]] = []
    if contract.get("schema_version") != "11.0":
        errors.append("route_contract_schema_version")
    if contract.get("semantic_plan_schema") != "references/semantic-plan.schema.json":
        errors.append("route_contract_semantic_plan_ref")
    if "classification" in contract:
        errors.append("route_contract_raw_classification_forbidden")
    selection = contract.get("selection_policy", {})
    if selection.get("input") != "agent_semantic_plan":
        errors.append("route_contract_input_not_semantic_plan")
    if selection.get("raw_request_classification") is not False:
        errors.append("route_contract_machine_raw_classification_enabled")
    if selection.get("single_global_mode") is not False:
        errors.append("route_contract_single_global_mode_enabled")
    semantic_policy = contract.get("semantic_plan_policy", {})
    ignored = set(semantic_policy.get("legacy_route_fields_ignored", []))
    if not {"patterns", "exclude_patterns"}.issubset(ignored):
        errors.append("route_contract_historical_patterns_not_marked_ignored")
    window_policy = semantic_policy.get("window_context", {})
    if (
        not isinstance(window_policy, dict)
        or window_policy.get("required_for_recovery_assessment") is not True
        or window_policy.get("missing_or_unknown_default") != "new_window"
        or window_policy.get("r0_allowed_only_for") != "same_window"
    ):
        errors.append("route_contract_window_context_policy")

    runtime_actions = contract.get("runtime_action_policy", {})
    guarded = set(runtime_actions.get("guarded_kinds", []))
    kind_events = runtime_actions.get("kind_events", {})
    if (
        not isinstance(kind_events, dict)
        or guarded != set(kind_events)
        or runtime_actions.get("ordinary_work_requires_runtime_action") is not False
        or runtime_actions.get("execution_entry") != "scripts/run_authorized_action.py"
        or not (root / "scripts/run_authorized_action.py").is_file()
    ):
        errors.append("route_runtime_action_policy_shape")

    tier_policy = contract.get("tier_policy", {})
    if set(tier_policy) != set(TIERS):
        errors.append("route_contract_tier_policy_keys")
    for tier, modes in tier_policy.items():
        values, shape_errors = _strings(modes, f"route_contract:tier:{tier}")
        errors.extend(shape_errors)
        unknown = set(values) - MODES
        if unknown:
            errors.append(f"route_contract:tier:{tier}:unknown_modes:" + ",".join(sorted(unknown)))

    event_policy = contract.get("event_policy", {})
    known_list, known_errors = _strings(event_policy.get("known_events"), "route_known_events")
    errors.extend(known_errors)
    known_events = set(known_list)
    if event_policy.get("source") != "semantic_plan.steps[].events" or event_policy.get("broadcast") is not False:
        errors.append("route_event_source_or_broadcast")
    controller = event_policy.get("controller_events", {})
    controller_events = set(controller.get("per_step", [])) | set(controller.get("before_writable_step", []))
    if (
        controller.get("scope") != "one_semantic_step"
        or controller.get("rule_domain") != "all_domains_by_declared_trigger"
    ):
        errors.append("route_controller_event_scope")
    if controller_events - known_events:
        errors.append("route_controller_unknown_events:" + ",".join(sorted(controller_events - known_events)))

    routes = contract.get("routes")
    if not isinstance(routes, list) or not routes:
        return contract, set(), known_events, witnesses, errors + ["route_contract_routes_shape"]
    route_ids = {route.get("id") for route in routes if isinstance(route, dict) and isinstance(route.get("id"), str)}
    if len(route_ids) != len(routes):
        errors.append("route_contract_duplicate_or_missing_ids")
    allowed_by_route = event_policy.get("route_allowed_events", {})
    if not isinstance(allowed_by_route, dict) or set(allowed_by_route) != route_ids:
        errors.append("route_contract_route_event_keyset")
    action_contracts = contract.get("action_contracts", {})
    if not isinstance(action_contracts, dict) or set(action_contracts) != route_ids:
        errors.append("route_action_contract_keyset")
        action_contracts = {}
    prerequisites = contract.get("event_prerequisites", {})
    controller_only = set(prerequisites.get("controller_only_events", []))
    if controller_only - known_events:
        errors.append("route_controller_only_unknown_events")
    prerequisite_events = prerequisites.get("events", {})
    if not isinstance(prerequisite_events, dict) or set(prerequisite_events) - known_events:
        errors.append("route_event_prerequisite_vocabulary")
        prerequisite_events = {}
    for event, requirement in prerequisite_events.items():
        if not isinstance(requirement, dict):
            errors.append(f"route_event_prerequisite_shape:{event}")
            continue
        minimum = requirement.get("minimum_tier")
        if minimum is not None and minimum not in TIERS:
            errors.append(f"route_event_prerequisite_tier:{event}")
        maximum = requirement.get("maximum_tier")
        if maximum is not None and maximum not in TIERS:
            errors.append(f"route_event_prerequisite_maximum_tier:{event}")
        if minimum in TIER_RANK and maximum in TIER_RANK and TIER_RANK[minimum] > TIER_RANK[maximum]:
            errors.append(f"route_event_prerequisite_tier_interval:{event}")
        mode = requirement.get("required_mode")
        if mode is not None and mode not in MODES:
            errors.append(f"route_event_prerequisite_mode:{event}")

    for route in routes:
        route_id = str(route.get("id", "<missing>"))
        required = {
            "id", "object", "intents", "modes", "component_types", "states",
            "write_policy", "expected_outputs", "exclusions", "context_refs",
        }
        if not required.issubset(route):
            errors.append(f"route:{route_id}:missing_fields")
            continue
        if route.get("object") not in OBJECTS:
            errors.append(f"route:{route_id}:unknown_object")
        actions, action_errors = _strings(route.get("intents"), f"route:{route_id}:actions")
        modes, mode_errors = _strings(route.get("modes"), f"route:{route_id}:modes")
        types, type_errors = _strings(route.get("component_types"), f"route:{route_id}:component_types")
        states, state_errors = _strings(route.get("states"), f"route:{route_id}:states")
        errors.extend(action_errors + mode_errors + type_errors + state_errors)
        if set(modes) - MODES:
            errors.append(f"route:{route_id}:unknown_modes")
        if set(types) - COMPONENT_TYPES:
            errors.append(f"route:{route_id}:unknown_component_types")
        route_events, route_event_errors = _strings(
            allowed_by_route.get(route_id), f"route:{route_id}:allowed_events", nonempty=False
        )
        errors.extend(route_event_errors)
        if set(route_events) - known_events:
            errors.append(f"route:{route_id}:unknown_allowed_events")
        per_action = action_contracts.get(route_id, {})
        if not isinstance(per_action, dict) or set(per_action) != set(actions):
            errors.append(f"route:{route_id}:action_contract_intent_keyset")
            per_action = {}
        for action in actions:
            requirement = per_action.get(action, {})
            if not isinstance(requirement, dict):
                errors.append(f"route:{route_id}:action_contract_shape:{action}")
                continue
            all_events = requirement.get("required_all_events", [])
            any_events = requirement.get("required_any_events", [])
            for name, values in (("all", all_events), ("any", any_events)):
                parsed, shape = _strings(
                    values, f"route:{route_id}:action:{action}:required_{name}", nonempty=False
                )
                errors.extend(shape)
                unknown = set(parsed) - known_events
                if unknown:
                    errors.append(
                        f"route:{route_id}:action:{action}:unknown_required_events:"
                        + ",".join(sorted(unknown))
                    )
                disallowed = set(parsed) - set(route_events) - set(event_policy.get("control_events", []))
                if disallowed:
                    errors.append(
                        f"route:{route_id}:action:{action}:required_events_not_allowed:"
                        + ",".join(sorted(disallowed))
                    )
            if "required_all_events" not in requirement and "required_any_events" not in requirement:
                errors.append(f"route:{route_id}:action:{action}:required_event_clause_missing")
            minimum = requirement.get("minimum_tier")
            if minimum is not None and minimum not in TIERS:
                errors.append(f"route:{route_id}:action:{action}:minimum_tier")
            maximum = requirement.get("maximum_tier")
            if maximum is not None and maximum not in TIERS:
                errors.append(f"route:{route_id}:action:{action}:maximum_tier")
            if minimum in TIER_RANK and maximum in TIER_RANK and TIER_RANK[minimum] > TIER_RANK[maximum]:
                errors.append(f"route:{route_id}:action:{action}:tier_interval")
            required_mode = requirement.get("required_mode")
            if required_mode is not None and required_mode not in modes:
                errors.append(f"route:{route_id}:action:{action}:required_mode_not_on_route")
        witness: dict[str, str] | None = None
        for action in actions:
            for mode in modes:
                minimum = _minimum_tier(route, action, mode, runtime_policy)
                action_minimum = per_action.get(action, {}).get("minimum_tier")
                if action_minimum in TIER_RANK and TIER_RANK[action_minimum] > TIER_RANK[minimum]:
                    minimum = action_minimum
                action_maximum = per_action.get(action, {}).get("maximum_tier")
                required_mode = per_action.get(action, {}).get("required_mode")
                if required_mode is not None and mode != required_mode:
                    continue
                for tier in TIERS:
                    if TIER_RANK[tier] < TIER_RANK.get(minimum, 0):
                        continue
                    if action_maximum in TIER_RANK and TIER_RANK[tier] > TIER_RANK[action_maximum]:
                        continue
                    if mode not in tier_policy.get(tier, []):
                        continue
                    if types and states:
                        witness = {
                            "route_id": route_id, "action": action, "mode": mode,
                            "tier": tier, "component_type": types[0], "state": states[0],
                        }
                        break
                if witness:
                    break
            if witness:
                break
        if witness is None:
            errors.append(f"route:{route_id}:no_static_action_mode_tier_state_witness")
        else:
            witnesses.append(witness)
    runtime_event_union = {
        event for events in kind_events.values() if isinstance(events, list) for event in events
    }
    if runtime_event_union - known_events:
        errors.append(
            "route_runtime_action_unknown_events:"
            + ",".join(sorted(runtime_event_union - known_events))
        )
    pause = action_contracts.get("RT.PROJECT.RESUME", {}).get("pause", {})
    if (
        pause.get("minimum_tier") != "G1_WORKING"
        or pause.get("maximum_tier") != "G1_WORKING"
        or pause.get("required_mode") != "mutate"
        or pause.get("required_all_events") != ["handoff"]
    ):
        errors.append("route_pause_contract_missing")
    return contract, route_ids, known_events, witnesses, sorted(errors)


def validate_ownership(root: Path) -> list[str]:
    ownership = load_json(root / "references/ownership-contract.json")
    errors: list[str] = []
    if ownership.get("schema_version") != "11.0":
        errors.append("ownership_schema_version")
    classes = ownership.get("classes")
    if not isinstance(classes, dict) or not REQUIRED_OWNER_CLASSES.issubset(classes):
        return errors + ["ownership_required_classes"]
    if classes.get("policy_atom", {}).get("owner_pattern") != "rules/*.json#RULE.ID":
        errors.append("ownership_policy_atom_pattern")
    if classes.get("policy_atom", {}).get("selection_contract") != "references/runtime-policy.json":
        errors.append("ownership_policy_selection_contract")
    if classes.get("policy_atom", {}).get("selection_driver") != "scripts/resolve_route.py":
        errors.append("ownership_policy_selection_driver")
    if classes.get("runtime_policy_contract", {}).get("shape_owner") != "references/semantic-plan.schema.json":
        errors.append("ownership_runtime_shape_owner")
    if classes.get("semantic_plan_contract", {}).get("interpreter") != "scripts/resolve_route.py":
        errors.append("ownership_semantic_plan_interpreter")
    references: set[str] = set()
    for details in classes.values():
        if not isinstance(details, dict):
            errors.append("ownership_class_not_object")
            continue
        for key, value in details.items():
            if key in {"owner", "shape_owner", "selection_contract", "selection_driver", "interpreter", "semantic_interpreter"} and isinstance(value, str):
                references.add(value)
            elif key in {"interpreters", "semantic_interpreters"} and isinstance(value, list):
                references.update(item for item in value if isinstance(item, str))
    for reference in sorted(references):
        if "*" in reference:
            continue
        rel = reference.split("#", 1)[0]
        if not (root / rel).is_file():
            errors.append(f"ownership_missing_reference:{reference}")
    return sorted(errors)


def validate_rule_corpus(
    root: Path,
    route_ids: set[str],
    known_events: set[str],
    test_ids: set[str],
) -> tuple[dict[str, int], list[str]]:
    errors: list[str] = []
    schema = load_json(root / "references/rule-atom.schema.json")
    if Draft202012Validator is None or FormatChecker is None:
        return {}, ["jsonschema_dependency_missing"]
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return {}, [f"rule_atom_schema_invalid:{exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    rules: list[tuple[str, dict[str, Any]]] = []
    for path in sorted((root / "rules").glob("*.json")):
        payload = load_json(path)
        relative = path.relative_to(root).as_posix()
        for violation in validator.iter_errors(payload):
            location = "/".join(str(item) for item in violation.absolute_path) or "$"
            errors.append(f"atom_schema:{relative}:{location}:{violation.validator}")
        if payload.get("domain") is None or not isinstance(payload.get("rules"), list):
            continue
        for rule in payload["rules"]:
            if not isinstance(rule, dict):
                continue
            rules.append((relative, rule))
            rid = str(rule.get("id", "<missing>"))
            if rule.get("domain") != payload.get("domain"):
                errors.append(f"rule:{rid}:bundle_domain_mismatch")
            expected_owner = f"{relative}#{rid}"
            if rule.get("owner") != expected_owner:
                errors.append(f"rule:{rid}:owner_mismatch:{rule.get('owner')}!={expected_owner}")
            unknown_events = set(rule.get("trigger", {}).get("events", [])) - known_events
            if unknown_events:
                errors.append(f"rule:{rid}:unknown_trigger_events:" + ",".join(sorted(unknown_events)))
            unknown_routes = set(rule.get("routes", [])) - route_ids - ROUTE_SELECTORS
            if unknown_routes:
                errors.append(f"rule:{rid}:unknown_routes:" + ",".join(sorted(unknown_routes)))
            missing_tests = set(rule.get("tests", [])) - test_ids
            if missing_tests:
                errors.append(f"rule:{rid}:missing_test_backrefs:" + ",".join(sorted(missing_tests)))
            if rule.get("status") == "active" and f"ATOM.{rid}" not in rule.get("tests", []):
                errors.append(f"rule:{rid}:missing_atomic_test_backref")
            enforcement = rule.get("enforcement", {})
            expected_assurance = (
                "behavior_verified" if enforcement.get("kind") == "runtime_guard"
                else "selection_verified"
            )
            if enforcement.get("assurance") != expected_assurance:
                errors.append(f"rule:{rid}:enforcement_assurance_mismatch")
            for reference in enforcement.get("refs", []):
                rel = str(reference).split("#", 1)[0]
                if not (root / rel).is_file():
                    errors.append(f"rule:{rid}:missing_enforcement_ref:{reference}")

    ids = [str(rule.get("id")) for _, rule in rules]
    duplicates = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicates:
        errors.append("duplicate_rule_ids:" + ",".join(duplicates))
    active = [rule for _, rule in rules if rule.get("status") == "active"]
    if len(active) != EXPECTED_ACTIVE_RULES:
        errors.append(f"active_rule_count:{len(active)}!={EXPECTED_ACTIVE_RULES}")
    atom_events = {
        event for rule in active for event in rule.get("trigger", {}).get("events", [])
    }
    if atom_events != known_events:
        errors.append(
            "trigger_event_vocabulary_mismatch:missing="
            + ",".join(sorted(known_events - atom_events))
            + ":extra=" + ",".join(sorted(atom_events - known_events))
        )
    known_rule_ids = set(ids)
    for _, rule in rules:
        rid = str(rule.get("id"))
        for field in ("conflicts_with", "refines", "depends_on"):
            unknown = set(rule.get(field, [])) - known_rule_ids
            if unknown:
                errors.append(f"rule:{rid}:{field}_unknown:" + ",".join(sorted(unknown)))
    metrics = {
        "rules": len(rules),
        "active_rules": len(active),
        "retired_rules": len(rules) - len(active),
        "trigger_events": len(atom_events),
    }
    return metrics, sorted(set(errors))


def validate_active_rule_reachability(
    root: Path,
    contract: dict[str, Any],
    runtime_policy: dict[str, Any],
) -> tuple[int, list[str]]:
    """Prove every active frozen atom has a V11 route/action/event witness.

    This is a contract-level reachability proof, complemented by executable
    forward cases for the legacy state and trigger adapters.  It deliberately
    does not broadcast all events at runtime.
    """
    rules, _ = load_rules(root)
    routes = contract.get("routes", [])
    allowed_by_route = contract.get("event_policy", {}).get("route_allowed_events", {})
    control_events = set(contract.get("event_policy", {}).get("control_events", []))
    controller = contract.get("event_policy", {}).get("controller_events", {})
    controller_events = (
        set(controller.get("per_step", []))
        | set(controller.get("before_writable_step", []))
        | {"before_file_creation"}
    )
    prerequisites = contract.get("event_prerequisites", {}).get("events", {})
    action_contracts = contract.get("action_contracts", {})
    scope_adapters = contract.get("legacy_scope_adapters", {})
    trigger_adapters = contract.get("legacy_trigger_adapters", {})

    def tier_possible(route: dict[str, Any], action: str, mode: str, events: set[str]) -> bool:
        action_requirement = action_contracts.get(route["id"], {}).get(action, {})
        required_mode = action_requirement.get("required_mode")
        if required_mode is not None and mode != required_mode:
            return False
        minimum = _minimum_tier(route, action, mode, runtime_policy)
        action_minimum = action_requirement.get("minimum_tier")
        if action_minimum in TIER_RANK and TIER_RANK[action_minimum] > TIER_RANK[minimum]:
            minimum = action_minimum
        maximum = action_requirement.get("maximum_tier")
        for event in events:
            event_minimum = prerequisites.get(event, {}).get("minimum_tier")
            if event_minimum in TIER_RANK and TIER_RANK[event_minimum] > TIER_RANK[minimum]:
                minimum = event_minimum
            event_mode = prerequisites.get(event, {}).get("required_mode")
            if event_mode is not None and event_mode != mode:
                return False
            event_maximum = prerequisites.get(event, {}).get("maximum_tier")
            if event_maximum in TIER_RANK and (
                maximum not in TIER_RANK or TIER_RANK[event_maximum] < TIER_RANK[maximum]
            ):
                maximum = event_maximum
        return any(
            TIER_RANK[tier] >= TIER_RANK[minimum]
            and (maximum not in TIER_RANK or TIER_RANK[tier] <= TIER_RANK[maximum])
            and mode in contract.get("tier_policy", {}).get(tier, [])
            for tier in TIERS
        )

    unreachable: list[str] = []
    active = [rule for rule in rules if rule.get("status") == "active"]
    for rule in active:
        witness = False
        scope = rule.get("scope", {})
        for route in routes:
            if route.get("object") not in set(scope.get("objects", [])) | ({route.get("object")} if "*" in scope.get("objects", []) else set()):
                continue
            for mode in route.get("modes", []):
                if not rule_matches_route(rule, route, mode):
                    continue
                rule_types = set(scope.get("component_types", []))
                type_ok = "none" in rule_types or bool(rule_types & set(route.get("component_types", [])))
                if not type_ok:
                    continue
                rule_states = set(scope.get("states", []))
                route_states = set(route.get("states", []))
                state_ok = "*" in rule_states or bool(rule_states & route_states)
                if not state_ok:
                    adapter = scope_adapters.get("skill_state", {})
                    state_ok = (
                        rule.get("domain") == adapter.get("domain")
                        and route.get("object") == "skill"
                        and adapter.get("actual_state") in route_states
                        and adapter.get("frozen_scope_token") in rule_states
                    )
                if not state_ok:
                    continue
                available = set(allowed_by_route.get(route["id"], [])) | control_events | controller_events
                target_events = set(rule.get("trigger", {}).get("events", [])) & available
                if not target_events:
                    continue
                adapter = trigger_adapters.get(rule.get("id"))
                if isinstance(adapter, dict):
                    coarse = adapter.get("coarse_controller_event")
                    if coarse in target_events:
                        # An explicit semantic fact is a valid witness even if no
                        # listed domain event is present on this particular route.
                        if not adapter.get("when_fact_true") and not (
                            set(adapter.get("when_any_actual_event", []))
                            & set(allowed_by_route.get(route["id"], []))
                        ):
                            target_events.discard(coarse)
                if not target_events:
                    continue
                for action in route.get("intents", []):
                    requirement = action_contracts.get(route["id"], {}).get(action, {})
                    required = set(requirement.get("required_all_events", []))
                    any_events = set(requirement.get("required_any_events", []))
                    if any_events:
                        required.add(next(iter(sorted(any_events))))
                    required.add(next(iter(sorted(target_events))))
                    if required - available:
                        continue
                    if tier_possible(route, action, mode, required):
                        witness = True
                        break
                if witness:
                    break
            if witness:
                break
        if not witness:
            unreachable.append(str(rule.get("id")))
    return len(active) - len(unreachable), [
        "active_rule_unreachable:" + rule_id for rule_id in sorted(unreachable)
    ]


def validate_behavior_registry(
    root: Path,
    plan_validator: Draft202012Validator | None,
    legacy_ids: set[str],
) -> tuple[int, list[str]]:
    path = root / "evals/behavior-cases.json"
    payload = load_json(path)
    errors: list[str] = []
    if payload.get("schema_version") != "11.0":
        errors.append("behavior_registry_schema_version")
    cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        return 0, errors + ["behavior_registry_cases_shape"]
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    if len(ids) != len(cases) or len(ids) != len(set(ids)):
        errors.append("behavior_registry_duplicate_or_missing_ids")
    reused = sorted(set(ids) & legacy_ids)
    if reused:
        errors.append("behavior_registry_reuses_v10_ids:" + ",".join(reused))
    for case in cases:
        identifier = str(case.get("id", "<missing>"))
        if not identifier.startswith("BEH.V11.CORE."):
            errors.append(f"behavior:{identifier}:id_prefix")
        if case.get("kind") != "semantic_plan":
            errors.append(f"behavior:{identifier}:kind_not_semantic_plan")
        plan = case.get("plan")
        if not isinstance(plan, dict):
            errors.append(f"behavior:{identifier}:plan_missing")
        elif plan_validator is not None:
            for violation in plan_validator.iter_errors(plan):
                location = "/".join(str(item) for item in violation.absolute_path) or "$"
                errors.append(f"behavior:{identifier}:plan_schema:{location}:{violation.validator}")
        expected = case.get("expected")
        if not isinstance(expected, dict) or set(expected) != {"required", "forbidden", "exact", "budgets"}:
            errors.append(f"behavior:{identifier}:expectation_sections")
        elif any(not isinstance(expected.get(section), dict) or not expected[section] for section in expected):
            errors.append(f"behavior:{identifier}:empty_expectation_section")
    return len(cases), sorted(errors)


def validate(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    test_ids, occurrences, test_errors = collect_test_ids(root)
    errors.extend(test_errors)
    semantic_schema, plan_validator, semantic_errors = validate_semantic_plan_schema(root)
    del semantic_schema
    errors.extend(semantic_errors)
    runtime_policy, runtime_errors = validate_runtime_policy(root)
    errors.extend(runtime_errors)
    route_contract, route_ids, known_events, witnesses, route_errors = validate_route_contract(
        root, runtime_policy
    )
    errors.extend(route_errors)
    errors.extend(validate_ownership(root))
    rule_metrics, rule_errors = validate_rule_corpus(
        root, route_ids, known_events, test_ids
    )
    errors.extend(rule_errors)
    reachable_rules, reachability_errors = validate_active_rule_reachability(
        root, route_contract, runtime_policy
    )
    rule_metrics["reachable_active_rules"] = reachable_rules
    errors.extend(reachability_errors)
    legacy_payload = load_json(root / "evals/v10-behavior-oracles.json")
    legacy_ids = {
        case.get("id") for case in legacy_payload.get("cases", [])
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }
    behavior_count, behavior_errors = validate_behavior_registry(root, plan_validator, legacy_ids)
    errors.extend(behavior_errors)
    duplicate_test_ids = {
        identifier: paths for identifier, paths in occurrences.items() if len(paths) > 1
    }
    if duplicate_test_ids:
        errors.extend(
            f"duplicate_test_id:{identifier}:" + ",".join(paths)
            for identifier, paths in sorted(duplicate_test_ids.items())
        )
    errors = sorted(set(errors))
    return {
        "schema_version": "11.0",
        "status": "pass" if not errors else "fail",
        "metrics": {
            **rule_metrics,
            "routes": len(route_ids),
            "route_witnesses": len(witnesses),
            "test_ids": len(test_ids),
            "behavior_cases": behavior_count,
            "known_events": len(known_events),
        },
        "route_witnesses": witnesses,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    args = parser.parse_args()
    result = validate(args.root.resolve())
    json_output(result)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
