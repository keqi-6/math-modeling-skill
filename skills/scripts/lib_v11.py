#!/usr/bin/env python3
"""V11 semantic-plan routing and minimal atomic-rule selection.

The planner, not this module, interprets user language.  This module accepts
declared steps, validates their exact action/event/state contracts, and keeps
failures local to the affected dependency branch.
"""

from __future__ import annotations

import json
import re
from collections import deque
from copy import deepcopy
from pathlib import Path, PurePosixPath
from typing import Any

from lib_v10 import (
    ContractError,
    Draft202012Validator,
    EVIDENCE_LEVELS,
    FormatChecker,
    SKILL_ROOT,
    load_json,
    load_rules,
    rule_applicability,
    rule_matches_route,
    sha256_file,
    sha256_text,
)

try:
    from state_v11 import current_evidence_levels, load_state
except ImportError:  # pragma: no cover - surfaced as a step-local state error
    load_state = None  # type: ignore[assignment]
    current_evidence_levels = None  # type: ignore[assignment]


TIERS = ("G0_ADVISORY", "G1_WORKING", "G2_CHECKPOINT", "G3_RELEASE")
TIER_RANK = {tier: index for index, tier in enumerate(TIERS)}
CHECKPOINT_TIERS = {"G2_CHECKPOINT", "G3_RELEASE"}
WRITABLE_MODES = {"mutate", "promote", "skill_maintenance"}
RECOVERY_EVENT = "recovery_assessment"
RECOVERY_CONTROL_ACTIONS = {"resume", "recover", "handoff"}
RECOVERY_MISSING_ROUTE = "RT.PROJECT.RECOVER.MISSING"
R2_BLOCK_REASON = "r2_recovery_open:fresh_post_recovery_resolution_required"
R2_CLOSED_BLOCK_REASON = (
    "r2_recovery_closed_blocked:known_gap_resolution_required"
)
MANUSCRIPT_CLOSURE_REF = "references/manuscript-change-closure.json"
MANDATORY_RUNTIME_ACTION_EVENTS = {
    "model_execution",
    "implementation_verification",
    "numerical_verification",
    "constraint_verification",
    "invariant_verification",
    "limit_verification",
    "counterexample_verification",
    "sensitivity_verification",
    "reality_verification",
    "robustness_analysis",
    "uncertainty_analysis",
    "release_candidate_validation",
}
RECOVERY_PROJECT_ACTIONS = {"resume", "recover", "handoff"}
COMPATIBLE_CHANGE_ROUTE = "RT.PROJECT.COMPATIBLE_CHANGE"
COMPATIBLE_CHANGE_ACTIONS = {"propagate_compatible", "reconcile_compatible"}
COMPATIBLE_CHANGE_LEVELS = {
    "implementation_ref", "result_claims", "E1_IMPLEMENTATION", "E2_NUMERICAL",
    "E3_STRUCTURAL", "E4_REALITY", "uncertainty", "robustness",
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def public_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """Return the complete frozen semantic envelope without loader metadata."""
    return {key: value for key, value in rule.items() if not key.startswith("_")}


def runtime_rule_projection(rule: dict[str, Any]) -> dict[str, Any]:
    """Deliver the operative semantics without test/lineage routing baggage."""
    public = public_rule(rule)
    fields = (
        "id", "strength", "domain", "owner", "instruction_gloss", "effect",
        "evidence", "outcomes", "exceptions", "conflicts_with", "depends_on",
        "failure_example", "enforcement",
    )
    return {field: public[field] for field in fields if field in public}


def schema_errors(plan: Any, root: Path = SKILL_ROOT) -> list[str]:
    if Draft202012Validator is None or FormatChecker is None:
        return ["jsonschema_dependency_missing"]
    schema = load_json(root / "references/semantic-plan.schema.json")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: list[str] = []
    for violation in validator.iter_errors(plan):
        location = "/".join(str(item) for item in violation.absolute_path) or "$"
        errors.append(f"schema:{location}:{violation.validator}:{violation.message}")
    return sorted(errors)


def dependency_order(steps: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """Validate and topologically order explicit dependencies."""
    errors: list[str] = []
    ids = [step["id"] for step in steps]
    if len(ids) != len(set(ids)):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        errors.append("duplicate_step_ids:" + ",".join(duplicates))
        return [], errors
    known = set(ids)
    successors = {identifier: [] for identifier in ids}
    indegree = {identifier: 0 for identifier in ids}
    for step in steps:
        for dependency in step["depends_on"]:
            if dependency == step["id"]:
                errors.append(f"self_dependency:{step['id']}")
            elif dependency not in known:
                errors.append(f"unknown_dependency:{step['id']}:{dependency}")
            else:
                successors[dependency].append(step["id"])
                indegree[step["id"]] += 1
    if errors:
        return [], sorted(errors)
    position = {identifier: index for index, identifier in enumerate(ids)}
    ready = deque(sorted((item for item in ids if indegree[item] == 0), key=position.get))
    ordered: list[str] = []
    while ready:
        current = ready.popleft()
        ordered.append(current)
        for child in sorted(successors[current], key=position.get):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
    if len(ordered) != len(ids):
        cycle = sorted(item for item in ids if indegree[item] > 0)
        errors.append("dependency_cycle:" + ",".join(cycle))
    return ordered, errors


def _working_context_node(
    route: dict[str, Any], step: dict[str, Any]
) -> tuple[dict[str, Any] | None, list[str]]:
    context = step.get("working_context")
    if step["tier"] in CHECKPOINT_TIERS:
        return None, ["authoritative_state_required_for_checkpoint"]
    if context is None:
        types = set(route.get("component_types", [])) - {"none"}
        states = set(route.get("states", [])) - {"*"}
        if len(types) != 1 or len(states) != 1:
            return None, ["working_context_required_for_ambiguous_route_state"]
        context = {"component_type": next(iter(types)), "state": next(iter(states))}
    component_type = context["component_type"]
    state = context["state"]
    allowed_types = set(route.get("component_types", []))
    allowed_states = set(route.get("states", []))
    errors: list[str] = []
    if component_type not in allowed_types and "none" not in allowed_types:
        errors.append(f"working_context_component_type_mismatch:{component_type}")
    if state not in allowed_states and "*" not in allowed_states:
        errors.append(f"working_context_state_mismatch:{state}")
    if errors:
        return None, errors
    return {
        "route": route,
        "state": state,
        "component_type": component_type,
        "component_ids": [step["component_id"]] if step["component_id"] else [],
        "component_selector": step["component_id"],
        "state_source": "declared_working_context",
    }, []


def bind_route_state(
    route: dict[str, Any],
    step: dict[str, Any],
    state: dict[str, Any] | None,
    state_errors: list[str],
    projected_states: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """Bind one route to state without forcing recovery on ordinary G0/G1 work."""
    tier = step["tier"]
    component_id = step["component_id"]
    warnings: list[str] = []
    if tier in CHECKPOINT_TIERS and step.get("working_context") is not None:
        return None, ["working_context_cannot_replace_authoritative_checkpoint_state"], warnings
    if route["object"] == "skill":
        node = {
            "route": route,
            "state": "V11",
            "component_type": "skill",
            "component_ids": [],
            "component_selector": component_id,
            "state_source": "skill_release",
        }
        return node, [], warnings

    if state_errors and route.get("id") == RECOVERY_MISSING_ROUTE:
        # Missing, corrupt, or legacy state is itself the authoritative reason
        # for this route.  A declared working_context must not disguise it as a
        # normal resume against invented P0/P1/P2 state.
        source = (
            "state_absence" if state is None or "state_missing" in state_errors
            else "incompatible_authoritative_state"
        )
        if step.get("working_context") is not None:
            warnings.append("working_context_ignored_during_r2_binding")
        return {
            "route": route,
            "state": "UNINITIALIZED",
            "component_type": "project",
            "component_ids": [],
            "component_selector": component_id,
            "state_source": source,
        }, [], warnings

    if state_errors:
        if tier in CHECKPOINT_TIERS:
            return None, ["authoritative_state_invalid:" + ",".join(state_errors)], warnings
        warnings.extend("state_warning:" + item for item in state_errors)
        state = None

    if state is None:
        if step.get("working_context") is not None:
            node, reasons = _working_context_node(route, step)
            return node, reasons, warnings
        if "UNINITIALIZED" in route.get("states", []) and "project" in route.get("component_types", []):
            node = {
                "route": route,
                "state": "UNINITIALIZED",
                "component_type": "project",
                "component_ids": [],
                "component_selector": component_id,
                "state_source": "state_absence",
            }
            return node, [], warnings
        if tier in CHECKPOINT_TIERS:
            return None, ["authoritative_state_required_for_checkpoint"], warnings
        node, reasons = _working_context_node(route, step)
        return node, reasons, warnings

    components = state.get("components", {})
    if component_id is not None:
        project_target = (
            "project" in route.get("component_types", [])
            and component_id == state.get("project", {}).get("id")
        )
        if project_target:
            node = {
                "route": route,
                "state": state.get("project", {}).get("state"),
                "component_type": "project",
                "component_ids": [],
                "component_selector": component_id,
                "state_source": "authoritative_project",
            }
        else:
            component = components.get(component_id)
            if component is None:
                if tier in CHECKPOINT_TIERS:
                    return None, [f"unknown_component_id:{component_id}"], warnings
                warnings.append(f"component_not_registered:{component_id}")
                node, reasons = _working_context_node(route, step)
                return node, reasons, warnings
            component_type = component.get("type")
            if component_type not in route.get("component_types", []):
                return None, [f"component_type_mismatch:{component_type}"], warnings
            node = {
                "route": route,
                "state": component.get("state"),
                "component_type": component_type,
                "component_ids": [component_id],
                "component_selector": component_id,
                "state_source": "authoritative_component",
            }
    elif "project" in route.get("component_types", []):
        node = {
            "route": route,
            "state": state.get("project", {}).get("state"),
            "component_type": "project",
            "component_ids": [],
            "component_selector": None,
            "state_source": "authoritative_project",
        }
    else:
        allowed_types = set(route.get("component_types", []))
        matches = [
            (identifier, component)
            for identifier, component in components.items()
            if component.get("type") in allowed_types
        ]
        if not matches:
            if tier in CHECKPOINT_TIERS:
                return None, ["matching_component_required_for_checkpoint"], warnings
            node, reasons = _working_context_node(route, step)
            return node, reasons, warnings
        states = {component.get("state") for _, component in matches}
        types = {component.get("type") for _, component in matches}
        if len(states) != 1:
            return None, ["component_id_required_for_mixed_states"], warnings
        node = {
            "route": route,
            "state": next(iter(states)),
            "component_type": next(iter(types)) if len(types) == 1 else "multiple",
            "component_ids": sorted(identifier for identifier, _ in matches),
            "component_selector": None,
            "state_source": "authoritative_component_set",
        }

    projection = projected_states or {}
    if component_id is not None and component_id in projection:
        node["state"] = projection[component_id]
        node["state_source"] = "planned_dependency_effect"

    context = step.get("working_context")
    if context is not None and node["state_source"].startswith("authoritative"):
        if context["component_type"] != node["component_type"] or context["state"] != node["state"]:
            return None, ["working_context_conflicts_with_authoritative_state"], warnings
    allowed_states = set(route.get("states", []))
    if "*" not in allowed_states and node["state"] not in allowed_states:
        return None, [
            f"route_state_mismatch:{node['state']}:expected=" + ",".join(sorted(allowed_states))
        ], warnings
    return node, [], warnings


def route_for_step(
    step: dict[str, Any],
    contract: dict[str, Any],
    state: dict[str, Any] | None,
    state_errors: list[str],
    projected_states: dict[str, str] | None = None,
) -> tuple[dict[str, Any] | None, list[str], list[str]]:
    """Match exact semantic fields; raw request text is deliberately absent."""
    if step["mode"] not in contract.get("tier_policy", {}).get(step["tier"], []):
        return None, [f"mode_not_allowed_at_tier:{step['mode']}:{step['tier']}"], []
    candidates = [
        route for route in contract.get("routes", [])
        if route.get("object") == step["object"]
        and step["action"] in route.get("intents", [])
        and step["mode"] in route.get("modes", [])
    ]
    if not candidates:
        return None, [
            f"no_exact_route:{step['object']}:{step['action']}:{step['mode']}"
        ], []
    force_missing_recovery = bool(
        state_errors
        and step.get("object") == "project"
        and step.get("action") in RECOVERY_CONTROL_ACTIONS
    )
    if force_missing_recovery:
        candidates = [
            route for route in candidates if route.get("id") == RECOVERY_MISSING_ROUTE
        ]
        if not candidates:
            return None, ["invalid_state_requires_missing_state_recovery_route"], []
    eligible: list[dict[str, Any]] = []
    rejected: list[str] = []
    warnings: list[str] = []
    for original in candidates:
        route = dict(original)
        route["recovery"] = RECOVERY_EVENT in step["events"]
        node, reasons, node_warnings = bind_route_state(
            route, step, state, state_errors, projected_states
        )
        warnings.extend(node_warnings)
        if node is None:
            rejected.extend(f"{route['id']}:{reason}" for reason in reasons)
        else:
            eligible.append(node)
    if not eligible:
        return None, rejected or ["no_state_compatible_route"], sorted(set(warnings))
    # State absence intentionally selects the explicit missing-state recovery/init
    # route instead of treating every compatible route as equally plausible.
    concrete = [item for item in eligible if item["state"] != "UNBOUND_ADVISORY"]
    if len(concrete) == 1:
        return concrete[0], [], sorted(set(warnings))
    if len(eligible) != 1:
        return None, ["ambiguous_exact_routes:" + ",".join(sorted(item["route"]["id"] for item in eligible))], sorted(set(warnings))
    return eligible[0], [], sorted(set(warnings))


def validate_step_events(
    step: dict[str, Any], node: dict[str, Any], contract: dict[str, Any]
) -> list[str]:
    policy = contract.get("event_policy", {})
    known = set(policy.get("known_events", []))
    events = set(step["events"])
    errors = ["unknown_event:" + item for item in sorted(events - known)]
    route_events = set(policy.get("route_allowed_events", {}).get(node["route"]["id"], []))
    control_events = set(policy.get("control_events", []))
    errors.extend("event_not_allowed_for_route:" + item for item in sorted(events - route_events - control_events))
    prerequisites = contract.get("event_prerequisites", {})
    controller_only = set(prerequisites.get("controller_only_events", []))
    errors.extend("controller_event_must_not_be_declared:" + item for item in sorted(events & controller_only))

    action_contract = (
        contract.get("action_contracts", {})
        .get(node["route"]["id"], {})
        .get(step["action"])
    )
    if not isinstance(action_contract, dict):
        errors.append(f"action_contract_missing:{node['route']['id']}:{step['action']}")
    else:
        required_all = set(action_contract.get("required_all_events", []))
        required_any = set(action_contract.get("required_any_events", []))
        errors.extend("action_required_event_missing:" + item for item in sorted(required_all - events))
        if required_any and not events.intersection(required_any):
            errors.append("action_required_any_event_missing:" + ",".join(sorted(required_any)))
        minimum_tier = action_contract.get("minimum_tier")
        if minimum_tier in TIER_RANK and TIER_RANK[step["tier"]] < TIER_RANK[minimum_tier]:
            errors.append(f"action_minimum_tier:{step['tier']}:requires={minimum_tier}")
        maximum_tier = action_contract.get("maximum_tier")
        if maximum_tier in TIER_RANK and TIER_RANK[step["tier"]] > TIER_RANK[maximum_tier]:
            errors.append(f"action_maximum_tier:{step['tier']}:allows_at_most={maximum_tier}")
        required_mode = action_contract.get("required_mode")
        if required_mode is not None and step["mode"] != required_mode:
            errors.append(f"action_required_mode:{step['mode']}:requires={required_mode}")
        if action_contract.get("requires_state_effect") is True and step.get("state_effect") is None:
            errors.append("action_state_effect_required")
        if (
            action_contract.get("requires_compatible_change") is True
            and not isinstance(step.get("facts", {}).get("compatible_change"), dict)
        ):
            errors.append("action_compatible_change_required")
        if action_contract.get("component_id_must_be_null") is True and step.get("component_id") is not None:
            errors.append("action_component_id_must_be_null")
        if action_contract.get("component_id_must_be_non_null") is True and step.get("component_id") is None:
            errors.append("action_component_id_required")
        allowed_prefixes = action_contract.get("allowed_change_path_prefixes", [])
        if allowed_prefixes:
            for path in (step.get("change_set") or {}).get("paths", []):
                if not any(path.startswith(prefix) for prefix in allowed_prefixes):
                    errors.append(f"action_change_path_outside_allowed_prefix:{path}")
        required_templates = action_contract.get("required_change_path_templates", [])
        if required_templates and step.get("component_id") is not None:
            actual_paths = set((step.get("change_set") or {}).get("paths", []))
            for template in required_templates:
                expected_path = template.replace(
                    "{component_id}", str(step["component_id"])
                )
                if expected_path not in actual_paths:
                    errors.append(
                        f"action_required_change_path_missing:{expected_path}"
                    )

    for event in sorted(events):
        requirement = prerequisites.get("events", {}).get(event, {})
        required_boolean_fact = requirement.get("required_boolean_fact")
        fact_objects = set(requirement.get("objects", []))
        if (
            isinstance(required_boolean_fact, str)
            and (not fact_objects or step.get("object") in fact_objects)
            and not isinstance(step.get("facts", {}).get(required_boolean_fact), bool)
        ):
            errors.append(
                f"event_boolean_fact_required:{event}:{required_boolean_fact}"
            )
        minimum_tier = requirement.get("minimum_tier")
        if minimum_tier in TIER_RANK and TIER_RANK[step["tier"]] < TIER_RANK[minimum_tier]:
            errors.append(f"event_minimum_tier:{event}:{step['tier']}:requires={minimum_tier}")
        maximum_tier = requirement.get("maximum_tier")
        if maximum_tier in TIER_RANK and TIER_RANK[step["tier"]] > TIER_RANK[maximum_tier]:
            errors.append(f"event_maximum_tier:{event}:{step['tier']}:allows_at_most={maximum_tier}")
        required_mode = requirement.get("required_mode")
        if required_mode is not None and step["mode"] != required_mode:
            errors.append(f"event_required_mode:{event}:{step['mode']}:requires={required_mode}")
        if requirement.get("requires_state_effect") is True and step.get("state_effect") is None:
            errors.append(f"event_state_effect_required:{event}")
        if requirement.get("requires_profile_selection") is True and step.get("facts", {}).get("profile_selected") is not True:
            errors.append(f"event_profile_selection_required:{event}")
    if RECOVERY_EVENT in events and step["tier"] == "G0_ADVISORY":
        errors.append("recovery_assessment_requires_g1_or_higher")
    return sorted(set(errors))


def controller_events_for_step(
    step: dict[str, Any], contract: dict[str, Any], project_root: Path | None
) -> set[str]:
    """Emit internal events only when this concrete step actually causes them."""
    policy = contract.get("event_policy", {}).get("controller_events", {})
    events = set(policy.get("per_step", []))
    if step["mode"] in WRITABLE_MODES:
        events.update(policy.get("before_writable_step", []))
        formal_events = set(policy.get("formal_artifact_events", []))
        if formal_events.intersection(step.get("events", [])):
            events.update(policy.get("before_formal_artifact_admission", []))
    return events


def validate_state_effect(
    step: dict[str, Any], node: dict[str, Any], root: Path
) -> list[str]:
    effect = step.get("state_effect")
    if effect is None:
        return []
    errors: list[str] = []
    if effect["component_id"] != step.get("component_id"):
        errors.append("state_effect_component_mismatch")
    if effect["from"] != node.get("state"):
        errors.append(f"state_effect_from_mismatch:{effect['from']}:actual={node.get('state')}")
    machine = load_json(root / "references/state-machine.json")
    component_type = node.get("component_type")
    transitions = machine.get("transitions", {}).get(component_type, [])
    if not any(
        item.get("from") == effect["from"] and item.get("to") == effect["to"]
        for item in transitions
    ):
        errors.append(
            f"state_effect_transition_not_allowed:{component_type}:{effect['from']}->{effect['to']}"
        )
    return sorted(set(errors))


def bind_compatible_change(
    step: dict[str, Any], node: dict[str, Any], state: dict[str, Any] | None
) -> list[str]:
    """Bind one compatible implementation delta to its exact component set.

    This is a validity overlay, not a lifecycle transition.  The route keeps
    the project state as its routing state while exposing the declared target
    questions as the execution/recovery scope.
    """
    change = step.get("facts", {}).get("compatible_change")
    route_id = node.get("route", {}).get("id")
    if route_id != COMPATIBLE_CHANGE_ROUTE:
        return ["compatible_change_route_mismatch"] if isinstance(change, dict) else []
    if not isinstance(change, dict):
        return ["compatible_change_missing"]
    errors: list[str] = []
    effects = change.get("effects", [])
    component_ids = [
        item.get("component_id") for item in effects if isinstance(item, dict)
    ]
    if len(component_ids) != len(set(component_ids)):
        errors.append("compatible_change_duplicate_component")
    change_facets = set((step.get("change_set") or {}).get("facets", []))
    declared_effect_facets: set[str] = set()
    for effect in effects:
        if not isinstance(effect, dict):
            continue
        component_id = effect.get("component_id")
        affected_levels = set(effect.get("affected_levels", []))
        effect_facets = set(effect.get("changed_facets", []))
        declared_effect_facets.update(str(item) for item in effect_facets)
        if affected_levels - COMPATIBLE_CHANGE_LEVELS:
            errors.append("compatible_change_forbidden_level:" + str(component_id))
        if effect_facets - change_facets:
            errors.append("compatible_change_facet_outside_changeset:" + str(component_id))
    if change_facets != declared_effect_facets:
        errors.append(
            "compatible_change_changeset_facet_mismatch:"
            + ",".join(sorted(change_facets ^ declared_effect_facets))
        )
    if step.get("component_id") is not None:
        errors.append("compatible_change_component_selector_must_be_null")
    if step.get("action") not in COMPATIBLE_CHANGE_ACTIONS:
        errors.append("compatible_change_action_invalid")
    if state is not None:
        components = state.get("components", {})
        source = change.get("source_component_id")
        if source not in components or components[source].get("type") != "question":
            errors.append("compatible_change_source_question_required")
        elif step.get("action") == "reconcile_compatible":
            source_component = components[source]
            if source_component.get("state") not in {"S5", "S6", "S7"}:
                errors.append("compatible_change_source_insight_not_implemented:" + str(source))
            if source_component.get("status") in {"blocked", "invalidated"}:
                errors.append("compatible_change_source_not_current:" + str(source))
            if current_evidence_levels is not None:
                missing_source = sorted(
                    {"implementation_ref", "E1_IMPLEMENTATION", "E2_NUMERICAL"}
                    - current_evidence_levels(state, str(source))
                )
                if missing_source:
                    errors.append(
                        "compatible_change_source_evidence_missing:"
                        + str(source) + ":" + ",".join(missing_source)
                    )
        for component_id in component_ids:
            component = components.get(component_id)
            if not isinstance(component, dict):
                errors.append("compatible_change_unknown_component:" + str(component_id))
                continue
            if component.get("type") != "question":
                errors.append("compatible_change_question_only:" + str(component_id))
            if component.get("state") not in {"S4", "S5", "S6", "S7"}:
                errors.append(
                    "compatible_change_requires_frozen_model_contract:"
                    + str(component_id) + ":" + str(component.get("state"))
                )
            if (
                step.get("action") == "reconcile_compatible"
                and component.get("status") in {"blocked", "invalidated"}
            ):
                errors.append(
                    "compatible_change_preexisting_component_not_current:"
                    + str(component_id) + ":" + str(component.get("status"))
                )
    if not errors:
        node["component_ids"] = sorted(str(item) for item in component_ids)
        node["component_type"] = "multiple" if len(component_ids) > 1 else "question"
        node["component_selector"] = None
        node["state_source"] = "compatible_change_component_set"
    return sorted(set(errors))


def _canonical_relative_posix(raw: Any, *, allow_dot: bool = False) -> str | None:
    """Return a canonical relative POSIX path or ``None`` for any alias."""
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        return None
    if allow_dot and raw == ".":
        return raw
    if re.match(r"^[A-Za-z]:", raw):
        return None
    pure = PurePosixPath(raw)
    normalized = pure.as_posix()
    if (
        pure.is_absolute()
        or normalized in {"", ".", ".."}
        or ".." in pure.parts
        or raw != normalized
    ):
        return None
    return normalized


def _matches_path_patterns(relative: str, patterns: list[Any]) -> bool:
    return any(
        isinstance(pattern, str) and re.fullmatch(pattern, relative)
        for pattern in patterns
    )


def _validated_platform_extension_names(
    step: dict[str, Any],
    request: str,
    reserved_patterns: list[Any],
    transient_patterns: list[Any],
) -> tuple[set[str], list[str]]:
    """Validate the rare, request-bound exception for a fresh top level."""
    extension = step.get("facts", {}).get("platform_extension")
    if extension is None:
        return set(), []
    if not isinstance(extension, dict):
        return set(), ["platform_extension_invalid_shape"]
    required = {"approval_quote", "top_level_namespaces", "purpose", "rollback"}
    if set(extension) != required:
        return set(), ["platform_extension_invalid_shape"]

    errors: list[str] = []
    quote = extension.get("approval_quote")
    if not isinstance(quote, str) or len(quote.strip()) < 2:
        errors.append("platform_extension_approval_quote_invalid")
    elif quote not in request:
        errors.append("platform_extension_quote_not_in_request")
    for field in ("purpose", "rollback"):
        value = extension.get(field)
        if not isinstance(value, str) or len(value.strip()) < 8:
            errors.append("platform_extension_" + field + "_too_short")

    values = extension.get("top_level_namespaces")
    names: set[str] = set()
    if not isinstance(values, list) or not values:
        errors.append("platform_extension_namespaces_invalid")
    else:
        if len(values) != len({item for item in values if isinstance(item, str)}):
            errors.append("platform_extension_namespaces_not_unique")
        for value in values:
            canonical = _canonical_relative_posix(value)
            if canonical is None or len(PurePosixPath(canonical).parts) != 1:
                errors.append("platform_extension_namespace_noncanonical:" + str(value))
                continue
            probe = canonical + "/probe"
            if (
                _matches_path_patterns(canonical, reserved_patterns + transient_patterns)
                or _matches_path_patterns(probe, reserved_patterns + transient_patterns)
            ):
                errors.append("platform_extension_namespace_reserved_or_transient:" + canonical)
                continue
            names.add(canonical)
    if errors:
        return set(), sorted(set(errors))
    return names, []


def validate_project_platform_paths(
    step: dict[str, Any], request: str, project_root: Path | None, root: Path
) -> list[str]:
    """Admit retained G1 paths without inferring their formal artifact role.

    Existing paths remain grandfathered.  A new retained path may use a
    canonical semantic placement (including overlapping role patterns), a
    declared project-support namespace, or an already-established nonreserved
    top-level directory.  Formal artifact admission still selects and validates
    exactly one semantic role elsewhere.  Tool-managed transient side effects
    do not belong in the retained ChangeSet at all.
    """
    if project_root is None or step.get("mode") not in WRITABLE_MODES:
        return []
    if step.get("object") == "skill" and step.get("mode") == "skill_maintenance":
        candidate_root = project_root.resolve()
        errors: list[str] = []
        for relative in (step.get("change_set") or {}).get("paths", []):
            canonical = _canonical_relative_posix(relative)
            if canonical is None:
                errors.append("skill_change_path_noncanonical:" + str(relative))
                continue
            relative_path = Path(canonical)
            target = (candidate_root / relative_path).resolve()
            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
                or (target != candidate_root and candidate_root not in target.parents)
            ):
                errors.append("skill_change_path_outside_candidate:" + relative)
        return sorted(set(errors))
    project_root = project_root.resolve()
    contract = load_json(root / "references/project-platform-contract.json")
    roles = contract.get("roles", {})
    namespaces = contract.get("path_namespaces", {})
    support_patterns = namespaces.get("project_support", {}).get("path_patterns", [])
    transient_patterns = namespaces.get("tool_managed_transient", {}).get("path_patterns", [])
    reserved = namespaces.get("reserved", {})
    repository_internal_patterns = reserved.get("repository_internal_patterns", [])
    controller_metadata_patterns = reserved.get("controller_metadata_patterns", [])
    controller_allowlist = reserved.get("controller_path_allowlist", {})
    controller_always = set(controller_allowlist.get("always", []))
    controller_recovery_patterns = controller_allowlist.get(
        "recovery_assessment_event_required_patterns", []
    )
    established_exclusions = set(
        namespaces.get("established_project", {}).get("excluded_top_levels", [])
    )
    errors: list[str] = []
    unknown_paths: list[tuple[str, str]] = []
    for relative in (step.get("change_set") or {}).get("paths", []):
        canonical = _canonical_relative_posix(relative)
        if canonical is None:
            errors.append(
                "new_path_outside_project_platform:noncanonical_path:" + str(relative)
            )
            continue
        relative = canonical
        relative_path = PurePosixPath(canonical)
        path = (project_root / Path(*relative_path.parts)).resolve()
        if (
            path != project_root and project_root not in path.parents
        ):
            errors.append("new_path_outside_project_platform:path_escapes_project_root:" + relative)
            continue
        if _matches_path_patterns(relative, transient_patterns):
            errors.append(
                "new_path_outside_project_platform:transient_declared_retained:" + relative
            )
            continue
        if _matches_path_patterns(relative, repository_internal_patterns):
            errors.append(
                "new_path_outside_project_platform:reserved_namespace:" + relative
            )
            continue
        if _matches_path_patterns(relative, controller_metadata_patterns):
            if relative in controller_always:
                continue
            if (
                RECOVERY_EVENT in set(step.get("events", []))
                and _matches_path_patterns(relative, controller_recovery_patterns)
            ):
                continue
            errors.append(
                "new_path_outside_project_platform:reserved_namespace:" + relative
            )
            continue
        if path.exists():
            continue
        if (
            step.get("object") == "manuscript"
            and step.get("facts", {}).get("existing_paths_only") is True
        ):
            errors.append("manuscript_existing_path_missing:" + relative)
            continue
        matches = [
            role for role, declaration in roles.items()
            if _matches_path_patterns(relative, declaration.get("path_patterns", []))
        ]
        if matches:
            continue
        if _matches_path_patterns(relative, support_patterns):
            continue
        top_level = relative_path.parts[0] if len(relative_path.parts) > 1 else None
        if (
            top_level is not None
            and top_level not in established_exclusions
            and (project_root / top_level).is_dir()
        ):
            continue
        unknown_paths.append((relative, relative_path.parts[0]))
    if unknown_paths:
        extension_names, extension_errors = _validated_platform_extension_names(
            step,
            request,
            repository_internal_patterns + controller_metadata_patterns,
            transient_patterns,
        )
        errors.extend(extension_errors)
        for relative, top_level in unknown_paths:
            if not extension_errors and top_level in extension_names:
                continue
            if extension_names and top_level not in extension_names:
                errors.append("platform_extension_scope_mismatch:" + relative)
            errors.append("new_path_outside_project_platform:unknown_namespace:" + relative)
    elif step.get("facts", {}).get("platform_extension") is not None:
        errors.append("platform_extension_unused")
    return sorted(set(errors))


def validate_skill_authorization(plan: dict[str, Any]) -> list[str]:
    """Keep project work from silently widening into Skill maintenance."""
    maintenance = [
        step for step in plan.get("steps", [])
        if step.get("mode") == "skill_maintenance"
    ]
    if not maintenance:
        return []
    errors: list[str] = []
    if any(step.get("object") != "skill" for step in maintenance):
        errors.append("skill_maintenance_object_must_be_skill")
    if len(maintenance) != len(plan.get("steps", [])):
        errors.append("skill_maintenance_must_be_isolated_plan")
    authorization = plan.get("skill_authorization")
    if not isinstance(authorization, dict):
        return sorted(set(errors + ["skill_maintenance_explicit_authorization_required"]))
    if (
        authorization.get("source") == "current_request"
        and authorization.get("quote") not in plan.get("request", "")
    ):
        errors.append("skill_authorization_quote_not_in_current_request")
    return sorted(set(errors))


def unordered_path_conflicts(
    steps: list[dict[str, Any]], project_root: Path | None = None
) -> dict[str, list[str]]:
    """Reject lexical aliases and unordered overlaps of one physical target."""
    dependencies = {step["id"]: set(step["depends_on"]) for step in steps}

    def ancestors(step_id: str) -> set[str]:
        found: set[str] = set()
        queue = list(dependencies[step_id])
        while queue:
            current = queue.pop()
            if current in found:
                continue
            found.add(current)
            queue.extend(dependencies.get(current, set()))
        return found

    all_ancestors = {step["id"]: ancestors(step["id"]) for step in steps}
    conflicts: dict[str, list[str]] = {step["id"]: [] for step in steps}
    normalized_paths: dict[str, set[str]] = {}
    physical_paths: dict[str, dict[str, set[str]]] = {}
    resolved_root = project_root.resolve() if project_root is not None else None
    for step in steps:
        normalized_paths[step["id"]] = set()
        physical_paths[step["id"]] = {}
        for raw in (step.get("change_set") or {}).get("paths", []):
            canonical = _canonical_relative_posix(raw)
            if canonical is None:
                conflicts[step["id"]].append(
                    "noncanonical_change_set_path:" + str(raw)
                )
                if isinstance(raw, str) and "\\" not in raw and "\x00" not in raw:
                    alias = PurePosixPath(raw).as_posix()
                    if (
                        alias not in {"", ".", ".."}
                        and not PurePosixPath(alias).is_absolute()
                        and ".." not in PurePosixPath(alias).parts
                        and not re.match(r"^[A-Za-z]:", alias)
                    ):
                        normalized_paths[step["id"]].add(alias)
                continue
            normalized_paths[step["id"]].add(canonical)
            physical_key = canonical
            if resolved_root is not None:
                try:
                    target = (
                        resolved_root / Path(*PurePosixPath(canonical).parts)
                    ).resolve(strict=False)
                    physical_key = target.relative_to(resolved_root).as_posix()
                except ValueError:
                    # The platform containment check reports the escaping path.
                    continue
                except (OSError, RuntimeError) as exc:
                    conflicts[step["id"]].append(
                        "physical_path_resolution_failed:"
                        + step["id"] + ":" + canonical + ":" + type(exc).__name__
                    )
                    continue
            physical_paths[step["id"]].setdefault(physical_key, set()).add(canonical)
        for physical_key, aliases in sorted(physical_paths[step["id"]].items()):
            if len(aliases) > 1:
                conflicts[step["id"]].append(
                    "same_step_physical_alias_overlap:"
                    + step["id"]
                    + ":target=" + physical_key
                    + ":paths=" + ",".join(sorted(aliases))
                )
    for index, left in enumerate(steps):
        left_paths = normalized_paths[left["id"]]
        for right in steps[index + 1:]:
            overlap = left_paths & normalized_paths[right["id"]]
            ordered = left["id"] in all_ancestors[right["id"]] or right["id"] in all_ancestors[left["id"]]
            if overlap and not ordered:
                detail = f"unordered_change_set_overlap:{left['id']}:{right['id']}:" + ",".join(sorted(overlap))
                conflicts[left["id"]].append(detail)
                conflicts[right["id"]].append(detail)
            if ordered:
                continue
            physical_overlap = set(physical_paths[left["id"]]) & set(
                physical_paths[right["id"]]
            )
            for physical_key in sorted(physical_overlap):
                left_aliases = physical_paths[left["id"]][physical_key]
                right_aliases = physical_paths[right["id"]][physical_key]
                alias_pairs = sorted(
                    f"{left_alias}<->{right_alias}"
                    for left_alias in left_aliases
                    for right_alias in right_aliases
                    if left_alias != right_alias
                )
                if not alias_pairs:
                    continue
                detail = (
                    "unordered_physical_alias_overlap:"
                    + left["id"] + ":" + right["id"]
                    + ":target=" + physical_key
                    + ":paths=" + ",".join(alias_pairs)
                )
                conflicts[left["id"]].append(detail)
                conflicts[right["id"]].append(detail)
    return conflicts


def _recovery_posture(recovery: Any) -> str:
    if not isinstance(recovery, dict) or recovery.get("level") != "R2_FULL":
        return "NORMAL"
    boundary = recovery.get("execution_boundary", {})
    if isinstance(boundary, dict) and boundary.get("barrier_open") is True:
        return "R2_OPEN"
    outcome = recovery.get("closure_outcome")
    return "R2_CLOSED_BLOCKED" if outcome == "blocked" else "R2_CLOSED_READY"


def _plan_recovery_context(
    plan: dict[str, Any], state: dict[str, Any] | None
) -> dict[str, Any]:
    declared_paths: set[str] = set()
    path_components: dict[str, set[str]] = {}
    declared_components: set[str] = set()
    compatible = False
    change_set_attestations: list[bool] = []
    propagation_attestations: list[bool] = []
    for step in plan.get("steps", []):
        if not isinstance(step, dict):
            continue
        change_set = step.get("change_set")
        paths = change_set.get("paths", []) if isinstance(change_set, dict) else []
        if paths:
            facts = step.get("facts", {})
            if not isinstance(facts, dict):
                facts = {}
            change_set_attestations.append(
                facts.get("change_set_complete") is True
            )
            propagation_attestations.append(
                facts.get(
                    "propagation_complete",
                    facts.get("invalidation_propagated", False),
                ) is True
            )
        components: set[str] = set()
        component_id = step.get("component_id")
        if isinstance(component_id, str):
            components.add(component_id)
        change = step.get("facts", {}).get("compatible_change")
        if isinstance(change, dict):
            compatible = True
            source = change.get("source_component_id")
            if isinstance(source, str):
                components.add(source)
            components.update(
                effect.get("component_id")
                for effect in change.get("effects", [])
                if isinstance(effect, dict)
                and isinstance(effect.get("component_id"), str)
            )
        if (
            not components and isinstance(state, dict)
            and step.get("object") in {"project", "delivery"}
            and step.get("action") != "pause"
        ):
            components.update(
                item for item in state.get("project", {}).get("required_components", [])
                if isinstance(item, str)
            )
        declared_components.update(components)
        for path in paths:
            if not isinstance(path, str):
                continue
            declared_paths.add(path)
            path_components.setdefault(path, set()).update(components)
    return {
        "same_window": plan.get("window_context") == "same_window",
        "plan_id": plan.get("plan_id") or "current_plan",
        "plan_hash": sha256_text(canonical_json(plan)),
        "request_hash": sha256_text(str(plan.get("request", ""))),
        "plan_step_ids": sorted(
            str(step.get("id")) for step in plan.get("steps", [])
            if isinstance(step, dict) and isinstance(step.get("id"), str)
        ),
        "declared_paths": sorted(declared_paths),
        "path_components": {
            path: sorted(components) for path, components in sorted(path_components.items())
        },
        "declared_component_ids": sorted(declared_components),
        "require_declared_closure": compatible,
        "change_set_complete": bool(change_set_attestations) and all(
            change_set_attestations
        ),
        "propagation_complete": bool(propagation_attestations) and all(
            propagation_attestations
        ),
        "checkpoint_revision": state.get("revision") if isinstance(state, dict) else None,
    }


def _bind_satisfied_recovery(
    recovery: Any,
    state: dict[str, Any] | None,
    plan: dict[str, Any],
    plan_hash: str,
    project_root: Path | None,
) -> Any:
    """Bind an exact closed R1/R2 episode, including its live execution."""
    if (
        not isinstance(recovery, dict)
        or recovery.get("level") not in {"R1_TARGETED", "R2_FULL"}
        or not isinstance(state, dict)
        or project_root is None
    ):
        return recovery
    recovery_level = str(recovery.get("level"))
    try:
        from lib_v10 import build_workspace_manifest
        from recovery_v16 import manifest_sha256

        current_manifest = build_workspace_manifest(project_root.resolve(), ["."])
        current_hash = manifest_sha256(current_manifest)
    except (ContractError, OSError, ValueError):
        return recovery
    request_hash = sha256_text(str(plan.get("request", "")))
    recovery_step_ids = {
        str(step.get("id"))
        for step in plan.get("steps", [])
        if isinstance(step, dict) and RECOVERY_EVENT in set(step.get("events", []))
    }
    plan_step_ids = {
        str(step.get("id"))
        for step in plan.get("steps", [])
        if isinstance(step, dict) and isinstance(step.get("id"), str)
    }
    candidates: list[tuple[int, str, dict[str, Any], str | None]] = []
    for recovery_id, record in state.get("recoveries", {}).items():
        if not isinstance(recovery_id, str) or not isinstance(record, dict):
            continue
        counts = record.get("full_manifest_counts")
        canonical_count = (
            counts.get("canonical_item_count") if isinstance(counts, dict) else None
        )
        completed_count = (
            counts.get("completed_canonical_count") if isinstance(counts, dict) else None
        )
        classified_count = (
            counts.get("classified_canonical_count") if isinstance(counts, dict) else None
        )
        coverage_complete = (
            isinstance(counts, dict)
            and isinstance(canonical_count, int)
            and canonical_count >= 0
            and isinstance(completed_count, int)
            and completed_count == canonical_count
            and isinstance(classified_count, int)
            and 0 <= classified_count <= completed_count
            and counts.get("unresolved_count") == 0
        )
        level_receipt_complete = (
            coverage_complete
            and isinstance(record.get("full_manifest_sha256"), str)
            if recovery_level == "R2_FULL"
            else isinstance(record.get("required_reads"), list)
            and isinstance(record.get("read_receipts"), list)
        )
        consumed_by = record.get("consumed_by_execution")
        matched_execution_id: str | None = None
        workspace_binding_current = (
            record.get("reviewed_manifest_sha256") == current_hash
        )
        consumption_valid = consumed_by is None
        if isinstance(consumed_by, str):
            execution = state.get("executions", {}).get(consumed_by)
            execution_steps = (
                execution.get("step_ids", []) if isinstance(execution, dict) else []
            )
            exact_open_execution = (
                isinstance(execution, dict)
                and execution.get("status") == "open"
                and execution.get("plan_hash") == plan_hash
                and execution.get("request_hash") == request_hash
                and execution.get("recovery_run_id") == recovery_id
                and execution.get("recovery_decision_id") == record.get("decision_id")
                and isinstance(execution_steps, list)
                and execution_steps == [record.get("step_id")]
                and set(execution_steps).issubset(plan_step_ids)
            )
            baseline = state.get("workspace_baseline")
            baseline_meta = state.get("workspace_baseline_meta")
            established_by = (
                baseline_meta.get("established_by", {})
                if isinstance(baseline_meta, dict) else {}
            )
            execution_baseline_bound = (
                isinstance(baseline, dict)
                and isinstance(established_by, dict)
                and established_by.get("kind") == "formal_execution_start"
                and established_by.get("source_id") == consumed_by
            )
            live_delta: set[str] = set()
            if isinstance(baseline, dict):
                baseline_paths = set(baseline)
                current_paths = set(current_manifest)
                live_delta.update(current_paths - baseline_paths)
                live_delta.update(baseline_paths - current_paths)
                live_delta.update(
                    path for path in baseline_paths & current_paths
                    if baseline[path] != current_manifest[path]
                )
            declared_paths = {
                path for path in (
                    execution.get("change_set", {}).get("paths", [])
                    if isinstance(execution, dict)
                    and isinstance(execution.get("change_set"), dict) else []
                )
                if isinstance(path, str)
            }
            consumption_valid = bool(
                exact_open_execution
                and execution_baseline_bound
                and live_delta.issubset(declared_paths)
            )
            workspace_binding_current = consumption_valid
            if consumption_valid:
                matched_execution_id = consumed_by
        if not (
            record.get("status") == "closed"
            and record.get("outcome") in {"ready", "blocked"}
            and record.get("recovery_level") == recovery_level
            and record.get("plan_hash") == plan_hash
            and record.get("request_hash") == request_hash
            and record.get("step_id") in recovery_step_ids
            and workspace_binding_current
            and isinstance(record.get("recovery_receipt_sha256"), str)
            and isinstance(record.get("decision_id"), str)
            and consumption_valid
            and level_receipt_complete
        ):
            continue
        revision = record.get("end_revision")
        candidates.append((
            revision if isinstance(revision, int) else -1,
            recovery_id,
            record,
            matched_execution_id,
        ))
    if not candidates:
        return recovery
    _, recovery_id, record, execution_id = max(
        candidates, key=lambda item: (item[0], item[1])
    )
    satisfied = deepcopy(recovery)
    fresh_decision_id = satisfied.get("decision_id")
    boundary = dict(satisfied.get("execution_boundary", {}))
    boundary.update({
        "barrier_open": False,
        "blocked_action_classes": (
            boundary.get("blocked_action_classes", [])
            if record.get("outcome") == "blocked" else []
        ),
        "requires_fresh_resolution_to_continue": False,
    })
    satisfied.update({
        "execution_boundary": boundary,
        "decision_id": record.get("decision_id"),
        "fresh_decision_id": fresh_decision_id,
        "satisfied_by_recovery_id": recovery_id,
        "satisfied_by_execution_id": execution_id,
        "closure_outcome": record.get("outcome"),
        "recovery_receipt_sha256": record.get("recovery_receipt_sha256"),
    })
    if recovery_level == "R2_FULL":
        satisfied.update({
            "full_manifest_sha256": record.get("full_manifest_sha256"),
            "full_manifest_counts": record.get("full_manifest_counts"),
        })
    return satisfied


def recovery_barrier_open(
    plan: dict[str, Any],
    project_root: Path | None,
    state_errors: list[str],
    recovery: Any = None,
) -> bool:
    """Return the actual assessed R2 boundary, retaining legacy call safety."""
    if isinstance(recovery, dict):
        boundary = recovery.get("execution_boundary", {})
        return bool(isinstance(boundary, dict) and boundary.get("barrier_open") is True)
    if project_root is None:
        return False
    explicit_full = any(
        isinstance(step, dict)
        and isinstance(step.get("facts"), dict)
        and step["facts"].get("request_explicit_full_recovery") is True
        for step in plan.get("steps", [])
    )
    if explicit_full:
        return True
    if not state_errors:
        return False
    state_exists = (project_root / ".modeling/state.json").exists()
    recovery_intent = any(
        RECOVERY_EVENT in step.get("events", [])
        or (
            step.get("object") == "project"
            and step.get("action") in RECOVERY_CONTROL_ACTIONS
        )
        for step in plan.get("steps", [])
        if isinstance(step, dict)
    )
    return state_exists or recovery_intent


def _path_allowed(path: str, exact: set[str], prefixes: tuple[str, ...]) -> bool:
    canonical = _canonical_relative_posix(path)
    if canonical is None:
        return False
    return canonical in exact or any(canonical.startswith(prefix) for prefix in prefixes)


def validate_recovery_barrier(
    step: dict[str, Any], node: dict[str, Any], policy: dict[str, Any], is_open: bool
) -> list[str]:
    """Keep an R2 control reconstruction from silently running project work."""
    if not is_open or step.get("object") == "skill":
        return []
    barrier = policy.get("recovery_execution_barrier", {})
    errors: list[str] = []
    blocked_events = set(barrier.get("blocked_events", []))
    blocked = sorted(set(step.get("events", [])) & blocked_events)
    if blocked:
        errors.append(R2_BLOCK_REASON)
        errors.extend("r2_blocked_event:" + event for event in blocked)
    route_id = node.get("route", {}).get("id")
    recovery_control = (
        RECOVERY_EVENT in set(step.get("events", []))
        and step.get("object") == "project"
        and step.get("action") in RECOVERY_CONTROL_ACTIONS
    )
    if step.get("mode") in WRITABLE_MODES:
        if not recovery_control and route_id != barrier.get("recovery_write_route"):
            errors.append(R2_BLOCK_REASON)
        else:
            exact = set(barrier.get("allowed_write_paths", []))
            prefixes = tuple(barrier.get("allowed_write_prefixes", []))
            for path in (step.get("change_set") or {}).get("paths", []):
                if not _path_allowed(path, exact, prefixes):
                    errors.append("r2_recovery_write_outside_control_scope:" + path)
    elif (
        not recovery_control
        and route_id not in set(barrier.get("safe_readonly_routes", []))
    ):
        errors.append(R2_BLOCK_REASON)
    return sorted(set(errors))


def _change_set_has_scope(step: dict[str, Any]) -> bool:
    change_set = step.get("change_set") or {}
    return any(change_set.get(field) for field in ("paths", "facets", "claim_refs"))


def _command_component_mentions(
    action: dict[str, Any], state: dict[str, Any] | None
) -> set[str]:
    if not isinstance(state, dict) or not isinstance(state.get("components"), dict):
        return set()
    command = action.get("command", {})
    text = " ".join([str(command.get("cwd", "")), *map(str, command.get("argv", []))])
    tokens = set(re.findall(r"[A-Za-z0-9_.-]+", text.replace("\\", "/")))
    return set(state["components"]) & tokens


def validate_runtime_actions(
    step: dict[str, Any],
    node: dict[str, Any],
    plan: dict[str, Any],
    results: dict[str, dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    contract: dict[str, Any],
    project_root: Path | None,
    state: dict[str, Any] | None,
    plan_hash: str,
    r2_open: bool,
    recovery: Any = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate optional high-risk commands without gating ordinary G1 work."""
    actions = step.get("runtime_actions", [])
    if not actions:
        return [], []
    policy = contract.get("runtime_action_policy", {})
    kind_events = {
        str(kind): set(events)
        for kind, events in policy.get("kind_events", {}).items()
        if isinstance(events, list)
    }
    direct_only = set(policy.get("direct_authorization_only_kinds", []))
    non_derivation = set(policy.get("non_derivation_actions", []))
    request = plan["request"]
    errors: list[str] = []
    grants: list[dict[str, Any]] = []
    identifiers = [action.get("id") for action in actions if isinstance(action, dict)]
    if len(identifiers) != len(set(identifiers)):
        errors.append("duplicate_runtime_action_ids")
    expected_objects = {
        "project_model_execution": {"model"},
        "project_verification_execution": {"verification"},
        "recompute_existing_result": {"model", "verification"},
        "skill_targeted_validation": {"skill"},
        "skill_package_validation": {"skill"},
        "full_project_audit": {"project"},
    }
    for action in actions:
        action_id = str(action.get("id", "<missing>"))
        prefix = f"runtime_action:{action_id}:"
        local: list[str] = []
        kind = action.get("kind")
        event = action.get("event")
        formal_recovery_hold = False
        if kind not in set(policy.get("guarded_kinds", [])):
            local.append("kind_not_guarded")
        if event not in kind_events.get(str(kind), set()):
            local.append("kind_event_mismatch")
        if event not in set(step.get("events", [])):
            local.append("event_not_declared_by_step")
        if step.get("object") not in expected_objects.get(str(kind), set()):
            local.append("object_kind_mismatch")
        if r2_open:
            local.append(R2_BLOCK_REASON)
        if _recovery_posture(recovery) == "R2_CLOSED_BLOCKED":
            local.append(R2_CLOSED_BLOCK_REASON)
        if isinstance(recovery, dict) and recovery.get("level") in {
            "R1_TARGETED", "R2_FULL",
        }:
            formal_recovery_hold = not (
                recovery.get("closure_outcome") == "ready"
                and isinstance(recovery.get("satisfied_by_recovery_id"), str)
                and isinstance(recovery.get("recovery_receipt_sha256"), str)
                and isinstance(recovery.get("satisfied_by_execution_id"), str)
            )
            if recovery.get("closure_outcome") == "blocked":
                local.append(R2_CLOSED_BLOCK_REASON)

        scope = action.get("scope", {})
        scope_kind = scope.get("kind")
        component_ids = set(scope.get("component_ids", []))
        if kind in {"project_model_execution", "project_verification_execution", "recompute_existing_result"}:
            if scope_kind not in {"component", "change_closure"}:
                local.append("project_action_scope_kind")
            if not component_ids:
                local.append("project_action_component_scope_empty")
        if kind in {"skill_targeted_validation", "skill_package_validation"} and scope_kind != "skill_candidate":
            local.append("skill_action_scope_kind")
        if kind == "full_project_audit" and scope_kind != "full_project":
            local.append("full_audit_scope_kind")
        step_component = step.get("component_id")
        if step_component is not None and component_ids != {step_component}:
            local.append("component_scope_exceeds_step")
        node_components = set(node.get("component_ids", []))
        if node_components and not component_ids.issubset(node_components):
            local.append("component_scope_exceeds_route")
        if isinstance(state, dict) and isinstance(state.get("components"), dict):
            unknown = component_ids - set(state["components"])
            if unknown:
                local.append("unknown_scope_components:" + ",".join(sorted(unknown)))
        mentioned = _command_component_mentions(action, state)
        if mentioned - component_ids:
            local.append("command_mentions_out_of_scope_component:" + ",".join(sorted(mentioned - component_ids)))

        for field in ("input_paths", "output_paths"):
            for raw_path in scope.get(field, []):
                if _canonical_relative_posix(raw_path) is None:
                    local.append("noncanonical_" + field + ":" + str(raw_path))
        output_paths = {
            canonical
            for raw_path in scope.get("output_paths", [])
            if (canonical := _canonical_relative_posix(raw_path)) is not None
        }
        declared_paths = {
            canonical
            for raw_path in (step.get("change_set") or {}).get("paths", [])
            if (canonical := _canonical_relative_posix(raw_path)) is not None
        }
        if output_paths - declared_paths:
            local.append("output_paths_outside_change_set:" + ",".join(sorted(output_paths - declared_paths)))
        command = action.get("command", {})
        cwd = str(command.get("cwd", "."))
        canonical_cwd = _canonical_relative_posix(cwd, allow_dot=True)
        if canonical_cwd is None:
            local.append("noncanonical_command_cwd")
        elif project_root is not None:
            resolved_cwd = (project_root.resolve() / cwd).resolve()
            if resolved_cwd != project_root.resolve() and project_root.resolve() not in resolved_cwd.parents:
                local.append("command_cwd_escapes_project_root")

        authorization = action.get("authorization", {})
        source = authorization.get("source")
        if kind in direct_only and source != "direct_user_request":
            local.append("direct_user_authorization_required")
        if action.get("repetition") == "rerun_existing" and source != "direct_user_request":
            local.append("rerun_requires_direct_user_authorization")
        if source == "direct_user_request":
            excerpt = authorization.get("request_excerpt")
            if not isinstance(excerpt, str) or excerpt not in request:
                local.append("request_excerpt_not_exact_substring")
        elif source == "derived_from_authorized_change":
            source_id = authorization.get("source_step_id")
            source_step = by_id.get(str(source_id))
            source_result = results.get(str(source_id))
            if source_id not in step.get("depends_on", []):
                local.append("derived_source_must_be_direct_dependency")
            if source_step is None or source_result is None or source_result.get("status") != "resolved":
                local.append("derived_source_not_resolved")
            else:
                if source_step.get("action") in non_derivation:
                    local.append("control_action_cannot_authorize_runtime_action")
                if source_step.get("mode") not in WRITABLE_MODES or not _change_set_has_scope(source_step):
                    local.append("derived_source_not_an_authorized_change")
                source_components = set(source_result.get("component_ids", []))
                if component_ids and source_components and not component_ids.issubset(source_components):
                    local.append("derived_scope_exceeds_source_step")
                if kind == "skill_targeted_validation" and source_step.get("object") != "skill":
                    local.append("skill_validation_source_not_skill_change")
        else:
            local.append("authorization_source_unknown")

        if kind == "skill_package_validation":
            boundary = policy.get("skill_package_boundary", {})
            if (
                step.get("object") != boundary.get("object")
                or step.get("tier") != boundary.get("tier")
                or step.get("mode") != boundary.get("mode")
                or scope_kind != boundary.get("scope_kind")
            ):
                local.append("skill_package_boundary_mismatch")

        if local:
            errors.extend(prefix + item for item in sorted(set(local)))
            continue
        # A valid formal step must remain resolvable so recovery can be
        # checkpointed and consumed by record-route.  Until that exact open
        # execution exists, withhold the command grant instead of turning the
        # step into a circular recovery failure.
        if formal_recovery_hold:
            continue
        command_hash = sha256_text(canonical_json(command))
        payload = {
            "request_hash": sha256_text(request),
            "plan_hash": plan_hash,
            "step_id": step["id"],
            "runtime_action_id": action_id,
            "kind": kind,
            "event": event,
            "repetition": action.get("repetition"),
            "scope": scope,
            "command": command,
            "command_hash": command_hash,
            "project_root": str(project_root.resolve()) if project_root is not None else None,
            "state_revision": state.get("revision") if isinstance(state, dict) else None,
            "recovery_posture": _recovery_posture(recovery),
            "recovery_level": (
                recovery.get("level") if isinstance(recovery, dict) else None
            ),
            "recovery_decision_id": (
                recovery.get("decision_id") if isinstance(recovery, dict) else None
            ),
            "recovery_barrier_open": r2_open,
            "recovery_id": (
                recovery.get("satisfied_by_recovery_id")
                if isinstance(recovery, dict) else None
            ),
            "recovery_receipt_sha256": (
                recovery.get("recovery_receipt_sha256")
                if isinstance(recovery, dict) else None
            ),
            "recovery_execution_id": (
                recovery.get("satisfied_by_execution_id")
                if isinstance(recovery, dict) else None
            ),
            "authorization": authorization,
        }
        grants.append({"grant_id": sha256_text(canonical_json(payload)), **payload})
    return grants, sorted(set(errors))


def manuscript_activation(
    step: dict[str, Any], root: Path
) -> tuple[dict[str, Any] | None, set[str], list[dict[str, str]], list[str], list[str]]:
    """Validate scope and normalize declared facets into legacy event tokens.

    Normalization never names a rule.  Frozen atoms still decide applicability
    through their own route, scope and trigger envelopes.
    """
    path = root / MANUSCRIPT_CLOSURE_REF
    if not path.is_file():
        return None, set(), [], ["manuscript_change_closure_contract_missing"], []
    contract = load_json(path)
    errors: list[str] = []
    warnings: list[str] = []
    if contract.get("schema_version") != "11.0":
        errors.append("manuscript_change_closure_schema_version")
    inventory = contract.get("semantic_inventory", {})
    source = root / str(inventory.get("source", "rules/manuscript.json"))
    expected_hash = inventory.get("source_sha256")
    if not source.is_file() or expected_hash != sha256_file(source):
        errors.append("manuscript_rule_inventory_hash_mismatch")
    facts = step["facts"]
    missing = sorted(set(contract.get("plan_contract", {}).get("required_fact_keys", [])) - set(facts))
    if missing:
        errors.append("manuscript_required_facts_missing:" + ",".join(missing))
    for field in ("profile_selected", "published_revision", "existing_paths_only"):
        if field in facts and not isinstance(facts[field], bool):
            errors.append("manuscript_fact_not_boolean:" + field)
    change_class = facts.get("change_class")
    closure = contract.get("closures", {}).get(change_class)
    if closure is None:
        errors.append("unknown_manuscript_change_class:" + str(change_class))
        return None, set(), [], sorted(set(errors)), warnings
    if step["tier"] not in closure.get("allowed_tiers", []):
        errors.append(f"manuscript_tier_not_allowed:{change_class}:{step['tier']}")
    if step["action"] not in closure.get("allowed_actions", []):
        errors.append(f"manuscript_action_not_allowed:{change_class}:{step['action']}")
    expected_published = change_class == "published_revision_edit"
    if isinstance(facts.get("published_revision"), bool) and facts["published_revision"] != expected_published:
        errors.append(
            f"manuscript_published_revision_mismatch:{facts['published_revision']}:"
            f"expected={expected_published}"
        )

    actual_events = set(step["events"])
    required_events = set(closure.get("required_events", []))
    allowed_events = set(closure.get("allowed_events", []))
    missing_events = required_events - actual_events
    if missing_events:
        errors.append("manuscript_required_events_missing:" + ",".join(sorted(missing_events)))

    change_set = step.get("change_set") or {"paths": [], "facets": [], "claim_refs": []}
    constraints = closure.get("change_set_constraints", {})
    minimum_paths = constraints.get("minimum_paths")
    if isinstance(minimum_paths, int) and len(change_set.get("paths", [])) < minimum_paths:
        errors.append(
            f"manuscript_change_set_minimum_paths:{len(change_set.get('paths', []))}:"
            f"requires={minimum_paths}"
        )
    facets = set(change_set.get("facets", []))
    missing_facets = set(closure.get("required_facets", [])) - facets
    if missing_facets:
        errors.append("manuscript_required_facets_missing:" + ",".join(sorted(missing_facets)))
    expected_scope = closure.get("completion_claim")
    if expected_scope is not None and facts.get("completion_scope") != expected_scope:
        errors.append(
            f"manuscript_completion_scope_mismatch:{facts.get('completion_scope')}:{expected_scope}"
        )
    profile = contract.get("profile_overlay", {})
    profile_active = facts.get("profile_selected") is True or "writing_profile" in facets
    if profile_active:
        allowed_events.add(str(profile.get("required_event", "writing_profile_apply")))
        required_profile_event = str(profile.get("required_event", "writing_profile_apply"))
        if required_profile_event not in actual_events:
            errors.append("profile_event_required:" + required_profile_event)
    elif "writing_profile_apply" in actual_events:
        errors.append("profile_event_without_explicit_selection")
    manuscript_route_events = {
        event for event in actual_events
        if event.startswith("manuscript_")
        or event.startswith("full_manuscript_")
        or event in {
            "local_manuscript_edit", "published_manuscript_change",
            "method_section_write", "result_section_write", "conclusion_write",
            "writing_profile_apply",
        }
    }
    unexpected = manuscript_route_events - allowed_events
    if unexpected:
        errors.append("manuscript_event_outside_closure:" + ",".join(sorted(unexpected)))

    # Window/state recovery is a controller event, not a manuscript facet.
    # A closure value of ``not_applicable`` means that this manuscript change
    # does not *infer* recovery; it must not reject the explicit R0/R1 event
    # already required by a G2/G3 project step.

    normalized_events: set[str] = set()
    provenance: list[dict[str, str]] = []
    for facet in sorted(facets):
        mapped = contract.get("facet_to_legacy_event", {}).get(facet)
        mapped_events = mapped if isinstance(mapped, list) else ([mapped] if isinstance(mapped, str) else [])
        for event in mapped_events:
            normalized_events.add(event)
            provenance.append({
                "facet": facet,
                "event": event,
                "source": MANUSCRIPT_CLOSURE_REF + "#facet_to_legacy_event",
            })
    return closure, normalized_events, provenance, sorted(set(errors)), warnings


def _runtime_safety_prerequisite(rule: dict[str, Any]) -> bool:
    if rule.get("enforcement", {}).get("kind") != "runtime_guard" or rule.get("strength") != "MUST":
        return False
    return rule.get("effect", {}).get("verb") in {
        "require", "forbid", "limit", "select", "invalidate"
    }


def select_step_rules(
    rules: list[dict[str, Any]],
    node: dict[str, Any],
    step: dict[str, Any],
    facts: dict[str, Any],
    controller_events: set[str],
    contract: dict[str, Any],
    normalized_events: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str], list[str], list[dict[str, Any]]]:
    selected: list[dict[str, Any]] = []
    deferred: list[str] = []
    blocking: list[str] = []
    decisions: list[dict[str, Any]] = []
    actual_events = set(step["events"])
    normalized = normalized_events or set()
    effective_events = actual_events | controller_events | normalized
    for rule in rules:
        if rule.get("status") != "active" or not rule_matches_route(rule, node["route"], step["mode"]):
            continue
        declared = set(rule.get("trigger", {}).get("events", []))
        matched_actual = actual_events & declared
        matched_normalized = normalized & declared
        matched_controller = controller_events & declared
        trigger_adapter = contract.get("legacy_trigger_adapters", {}).get(rule.get("id"))
        trigger_adapter_applied = False
        if isinstance(trigger_adapter, dict) and trigger_adapter.get("coarse_controller_event") in matched_controller:
            fact_key = trigger_adapter.get("when_fact_true")
            actual_triggers = set(trigger_adapter.get("when_any_actual_event", []))
            actual_use = facts.get(fact_key) is True or bool(actual_events & actual_triggers)
            if not actual_use:
                matched_controller.discard(str(trigger_adapter.get("coarse_controller_event")))
            else:
                trigger_adapter_applied = True
        if not matched_actual and not matched_normalized and not matched_controller:
            continue
        evaluation_events = set(effective_events)
        applicability_node = node
        applicability_rule = rule
        scope_adapter: dict[str, str] | None = None
        scope_object_adapter: dict[str, str] | None = None
        if (
            rule.get("domain") == "maintenance"
            and node.get("route", {}).get("object") == "skill"
            and node.get("state") == "V11"
            and "V10" in rule.get("scope", {}).get("states", [])
        ):
            applicability_node = dict(node)
            applicability_node["state"] = "V10"
            scope_adapter = {
                "actual_state": "V11",
                "frozen_scope_token": "V10",
                "source": "references/route-contract.json#legacy_scope_adapters/skill_state",
            }
        recovery_object_adapter = contract.get("legacy_scope_adapters", {}).get(
            "recovery_state_object", {}
        )
        if (
            node.get("route", {}).get("object") == recovery_object_adapter.get("actual_object")
            and recovery_object_adapter.get("route_selector") in rule.get("routes", [])
            and recovery_object_adapter.get("required_event") in actual_events
        ):
            applicability_rule = deepcopy(rule)
            applicability_rule["scope"] = deepcopy(rule.get("scope", {}))
            applicability_rule["scope"]["objects"] = sorted(set(
                applicability_rule["scope"].get("objects", [])
                + [str(recovery_object_adapter.get("actual_object"))]
            ))
            scope_object_adapter = {
                "actual_object": str(recovery_object_adapter.get("actual_object")),
                "frozen_scope_token": str(recovery_object_adapter.get("frozen_scope_token")),
                "source": "references/route-contract.json#legacy_scope_adapters/recovery_state_object",
            }
        applicability = rule_applicability(
            applicability_rule, applicability_node, evaluation_events, facts
        )
        if applicability["status"] == "not_applicable":
            continue
        selected.append(rule)
        decision = {
            "rule_id": rule["id"],
            "applicability": applicability["status"],
            "activation": (
                "actual_event" if matched_actual
                else "normalized_legacy_event" if matched_normalized
                else "controller_step_event" if matched_controller
                else "unreachable"
            ),
            "matched_events": sorted(matched_actual),
            "matched_normalized_events": sorted(matched_normalized),
            "matched_controller_events": sorted(matched_controller),
        }
        if scope_adapter is not None:
            decision["scope_state_adapter"] = scope_adapter
        if scope_object_adapter is not None:
            decision["scope_object_adapter"] = scope_object_adapter
        if trigger_adapter_applied:
            decision["trigger_adapter"] = {
                "coarse_controller_event": trigger_adapter.get("coarse_controller_event"),
                "actual_data_use": True,
                "source": "references/route-contract.json#legacy_trigger_adapters/"
                + rule["id"],
            }
        if applicability["status"] == "needs_fact":
            decision["predicate_evidence"] = applicability.get("checks", {}).get("predicates", [])
            enforcement = rule.get("enforcement", {}).get("kind")
            if _runtime_safety_prerequisite(rule):
                blocking.append(rule["id"])
                decision["disposition"] = "block_current_step_safety_fact"
            elif enforcement == "agent_obligation" and step["tier"] in CHECKPOINT_TIERS:
                blocking.append(rule["id"])
                decision["disposition"] = "block_current_checkpoint"
            else:
                deferred.append(rule["id"])
                decision["disposition"] = "defer_unverified_effect"
        else:
            decision["disposition"] = "selected"
        decisions.append(decision)
    selected.sort(key=lambda item: item["id"])
    return selected, sorted(set(deferred)), sorted(set(blocking)), decisions


def _merge_authoritative_fact(facts: dict[str, Any], key: str, value: Any) -> str | None:
    if key in facts and facts[key] != value:
        return f"authoritative_fact_conflict:{key}"
    facts[key] = value
    return None


def selected_state_evidence_errors(
    selected: list[dict[str, Any]],
    state: dict[str, Any] | None,
    node: dict[str, Any],
    step: dict[str, Any],
) -> list[str]:
    """Check only already-required state evidence at formal promotion boundaries.

    Evidence whose fields are not state evidence levels remains an execution
    obligation and is closed by the formal receipt.  This avoids demanding
    future command/file evidence before the command has run while still making
    S6 and similar pre-existing readiness evidence non-bypassable.
    """
    if step["tier"] not in CHECKPOINT_TIERS or step["mode"] != "promote":
        return []
    required: dict[str, set[str]] = {}
    for rule in selected:
        evidence = rule.get("evidence", {})
        if evidence.get("required") is not True or "state" not in evidence.get("kinds", []):
            continue
        levels = set(evidence.get("fields", [])) & set(EVIDENCE_LEVELS)
        if levels:
            required[rule["id"]] = levels
    if not required:
        return []
    if state is None:
        return ["formal_state_evidence_unavailable"]
    if current_evidence_levels is None:
        return ["state_evidence_closure_unavailable"]
    component_ids = node.get("component_ids", [])
    if step.get("component_id") is not None:
        component_ids = [step["component_id"]]
    errors: list[str] = []
    for rule_id, levels in sorted(required.items()):
        for level in sorted(levels):
            current = any(
                level in current_evidence_levels(state, component_id)
                for component_id in component_ids
            )
            if not current:
                errors.append(f"required_state_evidence_missing:{rule_id}:{level}")
    return errors


def step_facts(
    step: dict[str, Any],
    node: dict[str, Any],
    plan: dict[str, Any],
    project_root: Path | None,
    state: dict[str, Any] | None,
    runtime_policy: dict[str, Any] | None = None,
    plan_recovery: Any = None,
) -> tuple[dict[str, Any], Any, list[str]]:
    facts = dict(step["facts"])
    errors: list[str] = []
    project_value = str(project_root.resolve()) if project_root is not None else None
    for key, value in (
        ("project_root", project_value),
        ("detected_objects", "multiple" if len({item["object"] for item in plan["steps"]}) > 1 else "single"),
        ("component_state", node["state"]),
    ):
        conflict = _merge_authoritative_fact(facts, key, value)
        if conflict:
            errors.append(conflict)
    if state is not None:
        conflict = _merge_authoritative_fact(facts, "state_revision", state.get("revision"))
        if conflict:
            errors.append(conflict)

    window_policy = (runtime_policy or {}).get("window_recovery_policy", {})
    window_context = plan.get("window_context")
    if window_context is None:
        window_context = window_policy.get("unknown_default", "new_window")
    if window_context not in {"same_window", "new_window", "unknown"}:
        errors.append("window_context_invalid:" + str(window_context))
    new_window = window_context != "same_window"
    conflict = _merge_authoritative_fact(facts, "window_context", window_context)
    if conflict:
        errors.append(conflict)

    recovery: Any = "not_applicable"
    recovery_applies = (
        RECOVERY_EVENT in step["events"]
        or (
            bool(step.get("runtime_actions"))
            and isinstance(plan_recovery, dict)
        )
    )
    if recovery_applies:
        if project_root is None:
            errors.append("recovery_assessment_requires_project_root")
        elif isinstance(plan_recovery, dict):
            # One decision is computed for the whole plan.  Step-local scopes
            # may shape the subsequent read set but must not reclassify it.
            recovery = deepcopy(plan_recovery)
        else:
            try:
                from assess_recovery import assess

                gate = {"G1_WORKING": "G1", "G2_CHECKPOINT": "G2", "G3_RELEASE": "G3"}.get(step["tier"])
                if gate is None:
                    errors.append("recovery_assessment_requires_g1_or_higher")
                else:
                    recovery = assess(
                        project_root,
                        explicit_full=facts.get("request_explicit_full_recovery") is True,
                        gate=gate,
                        new_window=new_window,
                        continuity=_plan_recovery_context(plan, state),
                    )
            except (ContractError, OSError, ValueError) as exc:
                errors.append("recovery_assessment_failed:" + str(exc))
        if isinstance(recovery, dict):
            if node.get("route", {}).get("id") == COMPATIBLE_CHANGE_ROUTE:
                change = step.get("facts", {}).get("compatible_change", {})
                allowed_components = {
                    item.get("component_id")
                    for item in change.get("effects", [])
                    if isinstance(item, dict)
                    and isinstance(item.get("component_id"), str)
                }
                source_component = change.get("source_component_id")
                if isinstance(source_component, str):
                    allowed_components.add(source_component)
                unexpected = sorted(
                    set(recovery.get("affected_components", []))
                    - allowed_components
                )
                if unexpected:
                    errors.append(
                        "compatible_change_recovery_closure_mismatch:"
                        + ",".join(unexpected)
                    )
            conflict = _merge_authoritative_fact(
                facts, "recovery_level", recovery.get("level")
            )
            if conflict:
                errors.append(conflict)
    return facts, recovery, sorted(set(errors))


def context_refs_for_step(node: dict[str, Any], step: dict[str, Any]) -> list[str]:
    events = set(step["events"])
    refs: list[str] = []
    for item in node["route"].get("context_refs", []):
        terms = item.get("when_any", [])
        include = not terms
        ref = item.get("ref", "")
        if terms and "recovery" in ref:
            include = RECOVERY_EVENT in events
        elif terms and "visual" in ref:
            include = any(event.startswith("visual_") for event in events)
        if include and ref and ref not in refs:
            refs.append(ref)
    if step["object"] == "manuscript" and MANUSCRIPT_CLOSURE_REF not in refs:
        refs.append(MANUSCRIPT_CLOSURE_REF)
    return refs


def resolve(plan: dict[str, Any], project_root: Path | None = None, root: Path = SKILL_ROOT) -> dict[str, Any]:
    """Resolve a validated semantic plan; never classify its request string."""
    errors = schema_errors(plan, root)
    if errors:
        return {"schema_version": "11.0", "status": "blocked", "errors": errors, "steps": [], "rules": []}
    order, dependency_errors = dependency_order(plan["steps"])
    if dependency_errors:
        return {
            "schema_version": "11.0", "status": "blocked", "request": plan["request"],
            "request_hash": sha256_text(plan["request"]), "errors": dependency_errors,
            "steps": [], "rules": [],
        }

    contract = load_json(root / "references/route-contract.json")
    runtime_policy = load_json(root / "references/runtime-policy.json")
    if contract.get("schema_version") != "11.0":
        raise ContractError("route contract must be V11")
    rules, _ = load_rules(root)
    state: dict[str, Any] | None = None
    state_errors: list[str] = []
    if project_root is not None:
        if load_state is None:
            state_errors = ["state_v11_unavailable"]
        else:
            state, state_errors = load_state(project_root.resolve())
    authoritative_state = state if state is not None and not state_errors else None
    plan_hash = sha256_text(canonical_json(plan))
    recovery_requested = any(
        isinstance(step, dict) and RECOVERY_EVENT in set(step.get("events", []))
        for step in plan.get("steps", [])
    )
    recovery_control_requested = any(
        isinstance(step, dict)
        and step.get("object") == "project"
        and step.get("action") in RECOVERY_CONTROL_ACTIONS
        for step in plan.get("steps", [])
    )
    invalid_existing_state = bool(
        project_root is not None and state_errors and (
            (project_root.resolve() / ".modeling/state.json").exists()
            or recovery_control_requested
        )
    )
    plan_recovery: Any = "not_applicable"
    if project_root is not None and (recovery_requested or invalid_existing_state):
        try:
            from assess_recovery import assess

            gate_rank = {"G1_WORKING": 1, "G2_CHECKPOINT": 2, "G3_RELEASE": 3}
            assessed_steps = [
                step for step in plan.get("steps", [])
                if isinstance(step, dict) and (
                    RECOVERY_EVENT in set(step.get("events", []))
                    or invalid_existing_state
                )
            ]
            highest = max(
                (gate_rank.get(str(step.get("tier")), 1) for step in assessed_steps),
                default=1,
            )
            gate = {1: "G1", 2: "G2", 3: "G3"}[highest]
            explicit_full = any(
                isinstance(step.get("facts"), dict)
                and step["facts"].get("request_explicit_full_recovery") is True
                for step in assessed_steps
            )
            window_context = plan.get(
                "window_context",
                runtime_policy.get("window_recovery_policy", {}).get(
                    "unknown_default", "new_window"
                ),
            )
            plan_recovery = assess(
                project_root.resolve(), explicit_full=explicit_full, gate=gate,
                new_window=window_context != "same_window",
                continuity=_plan_recovery_context(plan, authoritative_state),
            )
        except (ContractError, OSError, ValueError) as exc:
            plan_recovery = {
                "schema_version": "11.0",
                "level": "R2_FULL",
                "state_valid": False,
                "reasons": ["recovery_assessment_failed:" + str(exc)],
                "decision_id": sha256_text("recovery_assessment_failed:" + str(exc)),
                "execution_boundary": {
                    "barrier_open": True,
                    "recomputation_authorized": False,
                    "requires_fresh_resolution_to_continue": True,
                },
            }
    plan_recovery = _bind_satisfied_recovery(
        plan_recovery, authoritative_state, plan, plan_hash, project_root
    )
    r2_open = recovery_barrier_open(
        plan, project_root, state_errors, plan_recovery
    )
    plan_recovery_posture = _recovery_posture(plan_recovery)
    skill_authorization_errors = validate_skill_authorization(plan)

    by_id = {step["id"]: step for step in plan["steps"]}
    path_conflicts = unordered_path_conflicts(plan["steps"], project_root)
    results: dict[str, dict[str, Any]] = {}
    selected_union: dict[str, dict[str, Any]] = {}
    for step_id in order:
        step = by_id[step_id]
        # Recovery barriers may intentionally stop the step before
        # ``step_facts`` runs.  Bind the two plan-level recovery facts here as
        # well so a permitted begin-recovery control operation sees the same
        # decision/window as the top-level resolution instead of the raw,
        # incomplete input facts.
        base_facts = dict(step["facts"])
        base_fact_errors: list[str] = []
        authoritative_window = plan.get(
            "window_context",
            runtime_policy.get("window_recovery_policy", {}).get(
                "unknown_default", "new_window"
            ),
        )
        conflict = _merge_authoritative_fact(
            base_facts, "window_context", authoritative_window
        )
        if conflict:
            base_fact_errors.append(conflict)
        if isinstance(plan_recovery, dict):
            conflict = _merge_authoritative_fact(
                base_facts, "recovery_level", plan_recovery.get("level")
            )
            if conflict:
                base_fact_errors.append(conflict)
        failed_dependencies = [
            dependency for dependency in step["depends_on"]
            if results[dependency]["status"] != "resolved"
        ]
        change_set = step.get("change_set") or {"paths": [], "facets": [], "claim_refs": []}
        projection: dict[str, str] = {}
        projection_errors: list[str] = []
        for dependency in step["depends_on"]:
            for component, projected_state in results[dependency].get("_state_projection", {}).items():
                if component in projection and projection[component] != projected_state:
                    projection_errors.append(
                        f"dependency_state_projection_conflict:{component}:"
                        f"{projection[component]}!={projected_state}"
                    )
                projection[component] = projected_state
        base = {
            "id": step_id,
            "tier": step["tier"],
            "mode": step["mode"],
            "object": step["object"],
            "action": step["action"],
            "component_id": step["component_id"],
            "events": list(step["events"]),
            "normalized_legacy_events": [],
            "event_normalization_provenance": [],
            "controller_events": [],
            "facts": base_facts,
            "working_context": step.get("working_context"),
            "depends_on": list(step["depends_on"]),
            "change_set": change_set,
            "state_effect": step.get("state_effect"),
            "runtime_actions": deepcopy(step.get("runtime_actions", [])),
            "action_grants": [],
            "projected_pre_states": dict(projection),
            "_state_projection": dict(projection),
            "recovery": (
                deepcopy(plan_recovery)
                if isinstance(plan_recovery, dict) and (
                    RECOVERY_EVENT in set(step.get("events", []))
                    or r2_open
                    or bool(step.get("runtime_actions"))
                )
                else "not_applicable"
            ),
            "route_id": None,
            "rule_ids": [],
            "deferred_rule_ids": [],
            "blocking_rule_ids": [],
            "unverified_effects": [],
            "context_refs": [],
            "reasons": [],
            "recovery_posture": plan_recovery_posture,
            "recovery_decision_id": (
                plan_recovery.get("decision_id")
                if isinstance(plan_recovery, dict) else None
            ),
        }
        if failed_dependencies:
            base.update({
                "status": "dependency_blocked",
                "reasons": ["failed_dependencies:" + ",".join(failed_dependencies)],
            })
            results[step_id] = base
            continue

        local_preflight_errors = (
            base_fact_errors
            + projection_errors
            + path_conflicts.get(step_id, [])
            + validate_project_platform_paths(step, plan["request"], project_root, root)
        )
        if step.get("mode") == "skill_maintenance":
            local_preflight_errors.extend(skill_authorization_errors)
        if local_preflight_errors:
            base.update({"status": "blocked", "reasons": sorted(set(local_preflight_errors))})
            results[step_id] = base
            continue

        node, route_errors, warnings = route_for_step(
            step, contract, state, state_errors, projection
        )
        if node is None:
            base.update({"status": "blocked", "reasons": route_errors, "warnings": warnings})
            results[step_id] = base
            continue
        compatible_errors = bind_compatible_change(step, node, authoritative_state)
        if compatible_errors:
            base.update({"status": "blocked", "reasons": compatible_errors, "warnings": warnings})
            results[step_id] = base
            continue
        base.update({
            "route_id": node["route"]["id"],
            "state": node["state"],
            "state_source": node["state_source"],
            "component_type": node["component_type"],
            "component_ids": node["component_ids"],
            "write_policy": node["route"].get("write_policy"),
            "expected_outputs": node["route"].get("expected_outputs", []),
            "exclusions": node["route"].get("exclusions", []),
            "warnings": warnings,
        })
        event_errors = validate_step_events(step, node, contract)
        event_errors.extend(validate_state_effect(step, node, root))
        event_errors.extend(
            validate_recovery_barrier(step, node, runtime_policy, r2_open)
        )

        # A new/unknown window must not silently continue an existing project.
        # The agent can include recovery_assessment in the same semantic plan,
        # so this does not add a user interaction step.
        window_context = plan.get("window_context")
        if (
            window_context != "same_window"
            and step.get("object") == "project"
            and step.get("action") in RECOVERY_PROJECT_ACTIONS
            and "recovery_assessment" not in set(step.get("events", []))
        ):
            event_errors.append("new_window_requires_recovery_assessment")
        if (
            project_root is not None
            and step.get("tier") in {"G2_CHECKPOINT", "G3_RELEASE"}
            and step.get("object") != "skill"
            and RECOVERY_EVENT not in set(step.get("events", []))
        ):
            event_errors.append("formal_project_step_requires_recovery_assessment")

        # Execution/verification/release-validation events must be bound to an
        # explicit runtime_action.  This is an internal plan requirement, not a
        # user confirmation gate.
        dangerous_events = set(step.get("events", [])) & MANDATORY_RUNTIME_ACTION_EVENTS
        if dangerous_events:
            declared_action_events = {
                item.get("event")
                for item in step.get("runtime_actions", [])
                if isinstance(item, dict) and isinstance(item.get("event"), str)
            }
            missing_dangerous = sorted(dangerous_events - declared_action_events)
            event_errors.extend(
                "missing_runtime_action_for_event:" + event
                for event in missing_dangerous
            )
        controller_events = controller_events_for_step(step, contract, project_root)
        base["controller_events"] = sorted(controller_events)
        closure: dict[str, Any] | None = None
        normalized_events: set[str] = set()
        if step["object"] == "manuscript":
            closure, normalized_events, normalization_provenance, manuscript_errors, manuscript_warnings = manuscript_activation(step, root)
            event_errors.extend(manuscript_errors)
            known_events = set(contract.get("event_policy", {}).get("known_events", []))
            allowed_route_events = set(
                contract.get("event_policy", {}).get("route_allowed_events", {}).get(node["route"]["id"], [])
            )
            event_errors.extend(
                "normalized_event_not_in_frozen_vocabulary:" + event
                for event in sorted(normalized_events - known_events)
            )
            event_errors.extend(
                "normalized_event_not_allowed_for_route:" + event
                for event in sorted(normalized_events - allowed_route_events)
            )
            base["normalized_legacy_events"] = sorted(normalized_events)
            base["event_normalization_provenance"] = normalization_provenance
            base["warnings"] = sorted(set(base["warnings"] + manuscript_warnings))
            if closure is not None:
                base["manuscript_closure"] = {
                    "change_class": step["facts"].get("change_class"),
                    "check_scope": closure.get("check_scope", []),
                    "completion_claim": closure.get("completion_claim"),
                    "recovery": closure.get("recovery"),
                    "required_evaluation_rule_ids": closure.get(
                        "required_evaluation_manuscript_rule_ids", []
                    ),
                    "expected_not_applicable_rule_ids": closure.get(
                        "expected_not_applicable_manuscript_rule_ids", []
                    ),
                }
        if event_errors:
            base.update({"status": "blocked", "reasons": sorted(set(event_errors))})
            results[step_id] = base
            continue

        facts, recovery, fact_errors = step_facts(
            step, node, plan, project_root, authoritative_state,
            runtime_policy, plan_recovery,
        )
        base["facts"] = facts
        base["recovery"] = recovery
        base["recovery_posture"] = plan_recovery_posture
        base["recovery_decision_id"] = (
            plan_recovery.get("decision_id")
            if isinstance(plan_recovery, dict) else None
        )
        if fact_errors:
            base.update({"status": "blocked", "reasons": fact_errors})
            results[step_id] = base
            continue
        grants, runtime_action_errors = validate_runtime_actions(
            step, node, plan, results, by_id, contract, project_root,
            authoritative_state, plan_hash, r2_open, plan_recovery,
        )
        base["action_grants"] = grants
        if runtime_action_errors:
            base.update({"status": "blocked", "reasons": runtime_action_errors})
            results[step_id] = base
            continue
        selected, deferred, blocking, decisions = select_step_rules(
            rules, node, step, facts, controller_events, contract,
            normalized_events
        )
        expected_not_applicable = set(
            closure.get("expected_not_applicable_manuscript_rule_ids", []) if closure else []
        )
        for decision in decisions:
            if decision["rule_id"] in expected_not_applicable:
                decision["closure_evaluation"] = "evaluate_not_applicable_do_not_claim_pass"
        selected_ids = {rule["id"] for rule in selected}
        conflicts = sorted({
            tuple(sorted((rule["id"], conflict)))
            for rule in selected
            for conflict in rule.get("conflicts_with", [])
            if conflict in selected_ids
        })
        for left, right in conflicts:
            blocking.extend([left, right])
            base["reasons"].append(f"unresolved_rule_conflict:{left}:{right}")
        evidence_errors = selected_state_evidence_errors(
            selected, authoritative_state, node, step
        )
        if evidence_errors:
            blocking.extend(evidence_errors)
            base["reasons"].extend(evidence_errors)
        max_rules = closure.get("max_total_rule_count") if closure else None
        if closure is not None:
            base["manuscript_closure"]["selection_telemetry"] = {
                "selected_rule_count": len(selected),
                "regression_budget": max_rules,
                "budget_is_runtime_gate": False,
            }
        for rule in selected:
            selected_union[rule["id"]] = rule
        base.update({
            "rule_ids": [rule["id"] for rule in selected],
            "deferred_rule_ids": deferred,
            "blocking_rule_ids": sorted(set(blocking)),
            "unverified_effects": [
                {"rule_id": rule["id"], "effect": rule.get("effect")}
                for rule in selected if rule["id"] in deferred
            ],
            "applicability_evidence": decisions,
            "governance_evidence": {
                "request_hash": sha256_text(plan["request"]),
                "raw_request_preserved": True,
                "semantic_interpreter": "agent",
                "machine_keyword_classification": False,
                "mode_scope": "step",
                "mode": step["mode"],
                "mode_stability_key": sha256_text(
                    sha256_text(plan["request"]) + ":" + step_id + ":" + step["mode"]
                ),
                "status": "blocked" if blocking else "resolved",
                "route_ids": [node["route"]["id"]],
                "contract_entry": node["route"]["id"],
                "route_tuple": {
                    "mode": step["mode"], "object": step["object"],
                    "action": step["action"], "state": node["state"],
                },
                "dependencies": list(step["depends_on"]),
                "controller_events": sorted(controller_events),
            },
            "context_refs": context_refs_for_step(node, step),
            "status": "blocked" if blocking else "resolved",
        })
        if not blocking and step.get("state_effect") is not None:
            effect = step["state_effect"]
            projection[effect["component_id"]] = effect["to"]
        base["projected_post_states"] = dict(projection)
        base["_state_projection"] = dict(projection)
        results[step_id] = base

    ordered_results = [deepcopy(results[step["id"]]) for step in plan["steps"]]
    for result in ordered_results:
        result.pop("_state_projection", None)
    resolved_count = sum(item["status"] == "resolved" for item in ordered_results)
    if resolved_count == len(ordered_results):
        status = "resolved"
    elif resolved_count:
        status = "partial"
    else:
        status = "blocked"
    union_rules = [runtime_rule_projection(selected_union[rule_id]) for rule_id in sorted(selected_union)]
    dependencies = [
        {"from": dependency, "to": step["id"]}
        for step in plan["steps"] for dependency in step["depends_on"]
    ]
    plan_route_ids = [
        result["route_id"] for result in ordered_results if result.get("route_id") is not None
    ]
    for result in ordered_results:
        governance = result.get("governance_evidence")
        if governance is not None:
            governance.update({
                "plan_step_ids": [step["id"] for step in plan["steps"]],
                "plan_route_ids": plan_route_ids,
                "plan_dependencies": dependencies,
                "plan_step_modes": {step["id"]: step["mode"] for step in plan["steps"]},
            })
    context_refs: list[str] = []
    for result in ordered_results:
        for ref in result.get("context_refs", []):
            if ref not in context_refs:
                context_refs.append(ref)
    reasons = [
        {"step_id": result["id"], "status": result["status"], "reasons": result.get("reasons", [])}
        for result in ordered_results if result["status"] != "resolved"
    ]
    return {
        "schema_version": "11.0",
        "status": status,
        "plan_id": plan.get("plan_id"),
        "plan_hash": plan_hash,
        "request": plan["request"],
        "request_hash": sha256_text(plan["request"]),
        "project_root": str(project_root.resolve()) if project_root is not None else None,
        "mode_model": {
            "single_global_mode": False,
            "step_modes": {step["id"]: step["mode"] for step in plan["steps"]},
        },
        "steps": ordered_results,
        "route_ids": plan_route_ids,
        "dependencies": dependencies,
        "execution_order": order,
        "recovery": plan_recovery,
        "recovery_decision_id": (
            plan_recovery.get("decision_id")
            if isinstance(plan_recovery, dict) else None
        ),
        "recovery_posture": plan_recovery_posture,
        "action_grants": [
            grant for result in ordered_results for grant in result.get("action_grants", [])
        ],
        "rule_ids": sorted(selected_union),
        "rules": union_rules,
        "context_refs": context_refs,
        "reasons": reasons,
    }
