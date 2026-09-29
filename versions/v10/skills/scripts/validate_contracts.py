#!/usr/bin/env python3
"""Validate V10 ownership, atom semantics, applicability, routes, and test bindings."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lib_v10 import (
    SKILL_ROOT, Draft202012Validator, FormatChecker, json_output, load_json,
    load_rules, route_emitted_events, rule_matches_route,
)


RULE_REQUIRED = {
    "id", "revision", "status", "capability", "domain", "owner", "strength", "semantic_key",
    "scope", "trigger", "effect", "instruction_gloss", "failure_example", "evidence", "outcomes",
    "exceptions", "conflicts_with", "refines", "depends_on", "supersedes", "legacy_refs",
    "routes", "tests", "enforcement",
}
RULE_OPTIONAL = {"context_ref"}
DOMAINS = {"governance", "project", "evidence_delivery", "data", "modeling", "verification", "manuscript", "visuals", "maintenance"}
STRENGTHS = {"MUST", "SHOULD", "MAY"}
EFFECT_VERBS = {"require", "forbid", "allow", "select", "record", "verify", "invalidate", "transition", "limit"}
SELECTORS = {"*", "@write", "@recovery"}
MODES = {"advisory_readonly", "project_readonly", "mutate", "promote", "skill_maintenance"}
KNOWN_FACTS = {
    "project_root", "frozen_decision", "ambiguity", "detected_objects",
    "predictive_or_evaluative_use", "policy_may_change", "recovery_level",
    "integrity", "change_ownership", "request_explicit_full_recovery",
    "recovery_closure_requested", "scope_change_requested",
}
SEMANTIC_FIELDS = {
    "id", "revision", "capability", "semantic_key", "strength", "effect",
    "instruction_gloss", "failure_example", "scope", "trigger", "evidence",
    "outcomes", "exceptions", "conflicts_with", "refines", "depends_on",
    "enforcement", "owner",
}


def value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return "unknown"


def markdown_anchor_exists(path: Path, anchor: str) -> bool:
    if not anchor:
        return path.exists()
    if not path.is_file():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        heading = line.lstrip("#").strip().lower()
        slug = re.sub(r"[^\w\u4e00-\u9fff -]", "", heading)
        slug = re.sub(r"\s+", "-", slug)
        if slug == anchor.lower():
            return True
    return False


def load_test_ids(root: Path) -> set[str]:
    ids: set[str] = set()
    for path in sorted((root / "evals").glob("*.json")):
        payload = load_json(path)
        if isinstance(payload, dict):
            for case in payload.get("cases", []):
                if isinstance(case, dict) and isinstance(case.get("id"), str):
                    ids.add(case["id"])
    return ids


def validate_route_behavior_coverage(root: Path, routes: list[dict[str, Any]]) -> list[str]:
    """Require at least one successful raw-language behavior case per route."""
    errors: list[str] = []
    payload = load_json(root / "evals/behavior-cases.json")
    covered: set[str] = set()
    for case in payload.get("cases", []):
        if not isinstance(case, dict) or case.get("kind") != "route":
            continue
        expected = case.get("expected")
        if not isinstance(expected, dict) or expected.get("status") != "resolved":
            continue
        route_ids = expected.get("route_ids")
        if isinstance(route_ids, list):
            covered.update(item for item in route_ids if isinstance(item, str))
    declared = {route.get("id") for route in routes if isinstance(route.get("id"), str)}
    for route_id in sorted(declared - covered):
        errors.append(f"route_without_success_behavior_case:{route_id}")
    for route_id in sorted(covered - declared):
        errors.append(f"behavior_case_unknown_route:{route_id}")
    return errors


def predicate_errors(rid: str, predicate: Any, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(predicate, dict) or set(predicate) != {"field", "op", "value"}:
        return [f"{rid}:{label}_bad_predicate_shape"]
    if predicate["field"] not in KNOWN_FACTS:
        errors.append(f"{rid}:{label}_unknown_fact:{predicate['field']}")
    if predicate["op"] not in {"eq", "ne", "in", "exists", "changed", "matches"}:
        errors.append(f"{rid}:{label}_unknown_operator:{predicate['op']}")
    if predicate["op"] == "matches":
        try:
            re.compile(str(predicate["value"]))
        except re.error:
            errors.append(f"{rid}:{label}_bad_match_regex")
    return errors


def validate_rule(
    root: Path,
    rule: dict[str, Any],
    route_ids: set[str],
    test_ids: set[str],
    event_vocabulary: set[str],
) -> list[str]:
    rid = str(rule.get("id", "<missing>"))
    errors: list[str] = []
    keys = set(rule) - {"_bundle"}
    missing = RULE_REQUIRED - keys
    extra = keys - RULE_REQUIRED - RULE_OPTIONAL
    if missing:
        errors.append(f"{rid}:missing_fields:{','.join(sorted(missing))}")
    if extra:
        errors.append(f"{rid}:extra_fields:{','.join(sorted(extra))}")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+)+", rid):
        errors.append(f"{rid}:bad_id")
    if rule.get("status") not in {"active", "retired"}:
        errors.append(f"{rid}:bad_status")
    if rule.get("strength") not in STRENGTHS:
        errors.append(f"{rid}:bad_strength")
    if rule.get("domain") not in DOMAINS:
        errors.append(f"{rid}:bad_domain")
    expected_owner = f"{rule.get('_bundle')}#{rid}"
    if rule.get("owner") != expected_owner:
        errors.append(f"{rid}:owner_mismatch:{rule.get('owner')}!={expected_owner}")
    if not re.fullmatch(r"[a-z0-9_.-]+", str(rule.get("semantic_key", ""))):
        errors.append(f"{rid}:bad_semantic_key")
    scope = rule.get("scope")
    if not isinstance(scope, dict) or set(scope) != {"objects", "component_types", "states"}:
        errors.append(f"{rid}:bad_scope_shape")
    elif not scope["objects"] or not scope["states"]:
        errors.append(f"{rid}:empty_scope")
    trigger = rule.get("trigger")
    if not isinstance(trigger, dict) or set(trigger) != {"events", "predicates"} or not trigger.get("events"):
        errors.append(f"{rid}:bad_trigger_shape")
    else:
        unknown_events = set(trigger["events"]) - event_vocabulary
        if unknown_events:
            errors.append(f"{rid}:unknown_trigger_events:{','.join(sorted(unknown_events))}")
        for predicate in trigger["predicates"]:
            errors.extend(predicate_errors(rid, predicate, "trigger"))
        equalities: dict[str, set[str]] = defaultdict(set)
        for predicate in trigger["predicates"]:
            if isinstance(predicate, dict) and predicate.get("op") == "eq":
                equalities[str(predicate.get("field"))].add(json.dumps(predicate.get("value"), sort_keys=True))
        if any(len(values) > 1 for values in equalities.values()):
            errors.append(f"{rid}:contradictory_trigger_predicates")
    effect = rule.get("effect")
    if not isinstance(effect, dict) or set(effect) != {"verb", "target", "value"}:
        errors.append(f"{rid}:bad_effect_shape")
    elif effect.get("verb") not in EFFECT_VERBS or not effect.get("target"):
        errors.append(f"{rid}:bad_effect")
    gloss = rule.get("instruction_gloss")
    if not isinstance(gloss, str) or not (8 <= len(gloss) <= 220):
        errors.append(f"{rid}:instruction_gloss_length")
    failure_example = rule.get("failure_example")
    if not isinstance(failure_example, str) or not (4 <= len(failure_example) <= 180):
        errors.append(f"{rid}:failure_example_length")
    evidence = rule.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"required", "kinds", "fields"}:
        errors.append(f"{rid}:bad_evidence_shape")
    outcomes = rule.get("outcomes")
    if not isinstance(outcomes, dict) or set(outcomes) != {"pass", "fail", "not_applicable"}:
        errors.append(f"{rid}:bad_outcomes_shape")
    for field in ("exceptions", "conflicts_with", "refines", "depends_on", "supersedes", "legacy_refs", "routes", "tests"):
        if not isinstance(rule.get(field), list):
            errors.append(f"{rid}:{field}_not_list")
    for exception in rule.get("exceptions", []):
        if not isinstance(exception, dict):
            errors.append(f"{rid}:exception_not_object")
        elif exception.get("kind") == "runtime_condition":
            if set(exception) != {"kind", "when", "disposition"} or exception.get("disposition") != "override_applicability":
                errors.append(f"{rid}:runtime_exception_bad_shape")
            else:
                errors.extend(predicate_errors(rid, exception["when"], "exception"))
        elif exception.get("kind") == "decision_required":
            if set(exception) != {"kind", "condition_key", "when", "disposition"}:
                errors.append(f"{rid}:decision_exception_bad_shape")
            elif not re.fullmatch(r"[a-z0-9_.-]+", str(exception.get("condition_key", ""))):
                errors.append(f"{rid}:decision_exception_bad_key")
        else:
            errors.append(f"{rid}:exception_unknown_kind")
    enforcement = rule.get("enforcement")
    if not isinstance(enforcement, dict) or set(enforcement) != {"kind", "assurance", "refs"}:
        errors.append(f"{rid}:bad_enforcement_shape")
    else:
        expected_assurance = "behavior_verified" if enforcement["kind"] == "runtime_guard" else "selection_verified"
        if enforcement.get("assurance") != expected_assurance:
            errors.append(f"{rid}:enforcement_assurance_mismatch")
        for ref in enforcement.get("refs", []):
            rel, _, anchor = ref.partition("#")
            path = root / rel
            if not path.is_file():
                errors.append(f"{rid}:missing_enforcement_ref:{ref}")
            elif anchor and path.suffix == ".md" and not markdown_anchor_exists(path, anchor):
                errors.append(f"{rid}:missing_enforcement_anchor:{ref}")
    unknown_routes = set(rule.get("routes", [])) - route_ids - SELECTORS
    if unknown_routes:
        errors.append(f"{rid}:unknown_routes:{','.join(sorted(unknown_routes))}")
    unknown_tests = set(rule.get("tests", [])) - test_ids
    if unknown_tests:
        errors.append(f"{rid}:unknown_tests:{','.join(sorted(unknown_tests))}")
    atom_test = f"ATOM.{rid}"
    if rule.get("status") == "active" and atom_test not in rule.get("tests", []):
        errors.append(f"{rid}:missing_atomic_test")
    if rule.get("status") == "active" and (not rule.get("routes") or not rule.get("tests")):
        errors.append(f"{rid}:active_rule_unbound")
    if rule.get("status") == "retired" and rule.get("routes"):
        errors.append(f"{rid}:retired_rule_routed")
    return errors


def static_route_applicable(rule: dict[str, Any], route: dict[str, Any], mode: str, event_model: dict[str, Any]) -> bool:
    if not rule_matches_route(rule, route, mode):
        return False
    scope = rule.get("scope", {})
    objects = set(scope.get("objects", []))
    if "*" not in objects and route["object"] not in objects:
        return False
    types = set(scope.get("component_types", []))
    if "none" not in types and not (types & set(route["component_types"])):
        return False
    states = set(scope.get("states", []))
    if "*" not in states and not (states & set(route["states"])) and mode != "advisory_readonly":
        return False
    events = set(rule.get("trigger", {}).get("events", []))
    return bool(events & route_emitted_events(route, event_model, mode))


def potential_route_ids(rule: dict[str, Any], routes: list[dict[str, Any]], event_model: dict[str, Any]) -> set[str]:
    return {
        route["id"]
        for route in routes
        for mode in route["modes"]
        if static_route_applicable(rule, route, mode, event_model)
    }


def structured_conflict_graph(
    rules: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    event_model: dict[str, Any],
) -> list[dict[str, Any]]:
    """Describe same-target applicability overlaps across distinct semantic owners."""
    active = [rule for rule in rules if rule.get("status") == "active"]
    reach = {rule["id"]: potential_route_ids(rule, routes, event_model) for rule in active}
    edges: list[dict[str, Any]] = []
    for index, left in enumerate(active):
        for right in active[index + 1:]:
            if left["effect"]["target"] != right["effect"]["target"]:
                continue
            overlap = sorted(reach[left["id"]] & reach[right["id"]])
            if not overlap:
                continue
            relations: list[str] = []
            if (
                right["id"] in left.get("conflicts_with", [])
                or left["id"] in right.get("conflicts_with", [])
            ):
                relations.append("explicit_conflict")
            if (
                right["id"] in left.get("refines", [])
                or left["id"] in right.get("refines", [])
            ):
                relations.append("refinement")
            if (
                right["id"] in left.get("depends_on", [])
                or left["id"] in right.get("depends_on", [])
            ):
                relations.append("dependency")
            edges.append({
                "left_rule_id": left["id"],
                "right_rule_id": right["id"],
                "semantic_keys": sorted([left["semantic_key"], right["semantic_key"]]),
                "cross_semantic_key": left["semantic_key"] != right["semantic_key"],
                "effect_target": left["effect"]["target"],
                "effect_relation": "duplicate" if left["effect"] == right["effect"] else "incompatible",
                "overlap_route_ids": overlap,
                "relations": sorted(relations),
                "resolution": "explicit" if relations else "unresolved",
            })
    return sorted(edges, key=lambda item: (item["left_rule_id"], item["right_rule_id"]))


def validate_routes(root: Path, routes: list[dict[str, Any]], rules: list[dict[str, Any]], event_model: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    ids = [route.get("id") for route in routes]
    route_ids = set(ids)
    for duplicated, count in Counter(ids).items():
        if count > 1:
            errors.append(f"duplicate_route_id:{duplicated}")
    valid_states = {"UNINITIALIZED", "V10", "P0", "P1", "P2"} | {f"S{i}" for i in range(8)} | {f"D{i}" for i in range(4)} | {f"A{i}" for i in range(4)}
    required = {
        "id", "object", "intents", "patterns", "exclude_patterns", "modes", "component_types", "states",
        "priority", "write_policy", "recovery", "phase", "after_objects", "expected_outputs", "exclusions", "context_refs",
    }
    if set(event_model) != {"global", "writable", "promote", "recovery", "route_events"}:
        errors.append("event_model_bad_shape")
    route_event_keys = set(event_model.get("route_events", {}))
    if route_event_keys != route_ids:
        errors.append("event_model_route_keys_mismatch")
    for route in routes:
        rid = route.get("id", "<missing>")
        if set(route) != required:
            errors.append(f"{rid}:route_fields:{','.join(sorted(set(route) ^ required))}")
        if not route.get("patterns") or not route.get("intents") or not route.get("modes"):
            errors.append(f"{rid}:empty_route_selector")
        for pattern in route.get("patterns", []) + route.get("exclude_patterns", []):
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"{rid}:bad_regex:{exc}")
        if set(route.get("modes", [])) - MODES:
            errors.append(f"{rid}:bad_modes")
        if set(route.get("states", [])) - valid_states:
            errors.append(f"{rid}:bad_states")
        if route.get("write_policy") == "never" and any(mode in {"mutate", "promote", "skill_maintenance"} for mode in route.get("modes", [])):
            errors.append(f"{rid}:never_write_has_write_mode")
        if route.get("write_policy") == "maintenance" and route.get("modes") != ["skill_maintenance"]:
            errors.append(f"{rid}:maintenance_policy_mode_mismatch")
        selected = [
            rule for rule in rules if rule.get("status") == "active"
            and any(static_route_applicable(rule, route, mode, event_model) for mode in route["modes"])
        ]
        if not selected:
            errors.append(f"{rid}:selects_no_applicable_rules")
        for context in route.get("context_refs", []):
            if not isinstance(context, dict) or set(context) != {"ref", "when_any"}:
                errors.append(f"{rid}:bad_context_ref_shape")
                continue
            ref, _, anchor = context["ref"].partition("#")
            if not markdown_anchor_exists(root / ref, anchor):
                errors.append(f"{rid}:missing_context_ref:{context['ref']}")
    return errors


def validate_relations(
    rules: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    routes: list[dict[str, Any]],
    event_model: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    active = [rule for rule in rules if rule.get("status") == "active"]
    reach = {rule["id"]: potential_route_ids(rule, routes, event_model) for rule in active}
    for rule in rules:
        rid = rule["id"]
        for field in ("conflicts_with", "refines", "depends_on"):
            for relation in rule.get(field, []):
                if relation == rid:
                    errors.append(f"{rid}:self_{field}")
                elif relation not in by_id:
                    errors.append(f"{rid}:unknown_{field}:{relation}")
        for relation in rule.get("conflicts_with", []):
            if relation in by_id and rid not in by_id[relation].get("conflicts_with", []):
                errors.append(f"{rid}:asymmetric_conflict:{relation}")
        for relation in rule.get("supersedes", []):
            if relation in by_id and by_id[relation].get("status") != "retired":
                errors.append(f"{rid}:supersedes_active:{relation}")
            elif relation not in by_id and not relation.startswith("V"):
                errors.append(f"{rid}:unknown_supersedes:{relation}")
        if rule.get("status") == "active" and not reach.get(rid):
            errors.append(f"{rid}:unreachable_after_scope_event_check")
    for edge in structured_conflict_graph(active, routes, event_model):
        if edge["resolution"] == "unresolved":
            errors.append(
                f"effect_overlap_{edge['effect_relation']}:"
                f"{edge['left_rule_id']}:{edge['right_rule_id']}:{edge['effect_target']}"
            )
    graph = {rule["id"]: set(rule.get("depends_on", [])) & by_id.keys() for rule in active}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            errors.append(f"depends_on_cycle:{node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for dependency in graph.get(node, set()):
            visit(dependency)
        visiting.remove(node)
        visited.add(node)

    for node in graph:
        visit(node)
    return errors


def validate_atomic_cases(root: Path, rules: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    path = root / "evals/atomic-rule-cases.json"
    if not path.is_file():
        return ["atomic_rule_cases_missing"]
    cases = load_json(path).get("cases", [])
    targets = [case.get("target_rule_id") for case in cases]
    active_ids = {rule["id"] for rule in rules if rule.get("status") == "active"}
    if set(targets) != active_ids or len(targets) != len(set(targets)):
        errors.append("atomic_cases_not_bijective_with_active_rules")
    required = {"id", "kind", "driver", "target_rule_id", "source_behavior_case_id", "expected", "verified_boundary"}
    expected_fields = {
        "applicability_status", "source_status", "revision", "strength", "effect", "owner",
        "enforcement_kind", "assurance", "semantic_envelope_sha256",
    }
    for case in cases:
        target = case.get("target_rule_id", "<missing>")
        if set(case) != required:
            errors.append(f"atomic_case_shape:{target}")
        if case.get("id") != f"ATOM.{target}" or case.get("kind") != "atomic_rule" or case.get("driver") != "atomic_rule_evals":
            errors.append(f"atomic_case_identity:{target}")
        if set(case.get("expected", {})) != expected_fields:
            errors.append(f"atomic_case_expected_shape:{target}")
        if not re.fullmatch(r"[0-9a-f]{64}", str(case.get("expected", {}).get("semantic_envelope_sha256", ""))):
            errors.append(f"atomic_case_bad_hash:{target}")
    return errors


def validate_target_registry(root: Path, rules: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    payload = load_json(root / "references/effect-target-registry.json")
    entries = payload.get("targets", [])
    by_target = {item.get("target"): item for item in entries}
    if len(by_target) != len(entries):
        errors.append("duplicate_effect_target_registry_entry")
    actual_targets = {rule["effect"]["target"] for rule in rules}
    if set(by_target) != actual_targets:
        errors.append("effect_target_registry_set_mismatch")
    for rule in rules:
        entry = by_target.get(rule["effect"]["target"], {})
        if rule["effect"]["verb"] not in entry.get("verbs", []):
            errors.append(f"{rule['id']}:effect_verb_not_registered")
        if value_type(rule["effect"]["value"]) not in entry.get("value_types", []):
            errors.append(f"{rule['id']}:effect_value_type_not_registered")
        if rule["domain"] not in entry.get("domains", []):
            errors.append(f"{rule['id']}:effect_domain_not_registered")
    return errors


def validate_ownership_contract(root: Path) -> list[str]:
    errors: list[str] = []
    payload = load_json(root / "references/ownership-contract.json")
    if payload.get("principle") != "each_normative_fact_has_exactly_one_owner":
        errors.append("ownership_principle_missing")
    policy = payload.get("classes", {}).get("policy_atom", {})
    if policy.get("normative_field") != "effect":
        errors.append("policy_atom_normative_field_not_effect")
    if set(policy.get("non_normative_fields", [])) != {"instruction_gloss", "failure_example", "outcomes"}:
        errors.append("policy_atom_non_normative_fields_mismatch")
    atomicity = payload.get("atomicity_policy", {})
    if atomicity.get("normative_unit") != "one_independently_decidable_effect":
        errors.append("atomicity_normative_unit_missing")
    if set(atomicity.get("required_effect_fields", [])) != {"verb", "target", "value"}:
        errors.append("atomicity_effect_shape_mismatch")
    if not atomicity.get("compound_value_allowed_only_for") or not atomicity.get("split_required_when"):
        errors.append("atomicity_split_policy_missing")
    referenced_paths: set[str] = set()
    for value in payload.get("classes", {}).values():
        if not isinstance(value, dict):
            continue
        for key, item in value.items():
            if key in {"owner", "shape_owner", "interpreter", "semantic_interpreter", "selection_contract", "selection_driver"} and isinstance(item, str):
                referenced_paths.add(item)
            if key in {"interpreters", "semantic_interpreters"} and isinstance(item, list):
                referenced_paths.update(str(entry) for entry in item)
    for rel in referenced_paths:
        if "*" not in rel and not (root / rel).is_file():
            errors.append(f"ownership_ref_missing:{rel}")
    return errors


def validate_rule_schema(root: Path) -> list[str]:
    errors: list[str] = []
    if Draft202012Validator is None or FormatChecker is None:
        return ["jsonschema_dependency_missing"]
    schema = load_json(root / "references/rule-atom.schema.json")
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        return [f"rule_atom_schema_invalid:{exc}"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for path in sorted((root / "rules").glob("*.json")):
        payload = load_json(path)
        for error in validator.iter_errors(payload):
            location = "/".join(str(item) for item in error.absolute_path)
            errors.append(f"schema:{path.name}:{location}:{error.message}")
    return errors


def validate_skill_metadata(root: Path) -> list[str]:
    errors: list[str] = []
    text = (root / "SKILL.md").read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        errors.append("skill_frontmatter_missing")
    name_match = re.search(r"^name:\s*([^\n]+)$", text, flags=re.MULTILINE)
    description_match = re.search(r"^description:\s*([^\n]+)$", text, flags=re.MULTILINE)
    version_match = re.search(r'^\s*version:\s*"([^"]+)"$', text, flags=re.MULTILINE)
    if not name_match or name_match.group(1).strip() != "mathematical-modeling-project-controller":
        errors.append("skill_name_invalid")
    if not description_match or len(description_match.group(1).strip()) < 30:
        errors.append("skill_description_invalid")
    if not version_match or version_match.group(1) != "10.0.0":
        errors.append("skill_version_invalid")
    yaml_text = (root / "agents/openai.yaml").read_text(encoding="utf-8")
    default_match = re.search(r'^\s*default_prompt:\s*"([^"]+)"$', yaml_text, flags=re.MULTILINE)
    short_match = re.search(r'^\s*short_description:\s*"([^"]+)"$', yaml_text, flags=re.MULTILINE)
    if not default_match or "$mathematical-modeling-project-controller" not in default_match.group(1):
        errors.append("openai_default_prompt_invalid")
    if not short_match or not (25 <= len(short_match.group(1)) <= 64):
        errors.append("openai_short_description_length")
    return errors


def validate(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    errors.extend(validate_skill_metadata(root))
    errors.extend(validate_rule_schema(root))
    contract = load_json(root / "references/route-contract.json")
    routes = contract.get("routes", [])
    event_model = contract.get("event_model", {})
    route_ids = {route.get("id") for route in routes}
    event_vocabulary = {
        event
        for key in ("global", "writable", "promote", "recovery")
        for event in event_model.get(key, [])
    } | {
        event for events in event_model.get("route_events", {}).values() for event in events
    }
    test_ids = load_test_ids(root)
    rules, by_id = load_rules(root)
    for rule in rules:
        errors.extend(validate_rule(root, rule, route_ids, test_ids, event_vocabulary))
    ids = [rule["id"] for rule in rules]
    semantic_keys = [rule["semantic_key"] for rule in rules if rule.get("status") == "active"]
    owners = [rule["owner"] for rule in rules]
    exception_keys = [
        exception["condition_key"]
        for rule in rules for exception in rule.get("exceptions", [])
        if exception.get("kind") == "decision_required"
    ]
    for label, values in (("rule_id", ids), ("semantic_key", semantic_keys), ("owner", owners), ("exception_key", exception_keys)):
        for duplicated, count in Counter(values).items():
            if count > 1:
                errors.append(f"duplicate_{label}:{duplicated}")
    errors.extend(validate_routes(root, routes, rules, event_model))
    errors.extend(validate_route_behavior_coverage(root, routes))
    errors.extend(validate_relations(rules, by_id, routes, event_model))
    errors.extend(validate_atomic_cases(root, rules))
    errors.extend(validate_target_registry(root, rules))
    errors.extend(validate_ownership_contract(root))
    baseline_path = root / "references/migration/v9-capability-baseline.json"
    if baseline_path.exists():
        baseline = load_json(baseline_path)
        baseline_ids = {item["id"] for item in baseline.get("capabilities", [])}
        current_caps = {rule["capability"] for rule in rules if rule.get("status") == "active"}
        if baseline_ids - current_caps:
            errors.append("missing_v9_capabilities:" + ",".join(sorted(baseline_ids - current_caps)))
        if len(baseline_ids) != 51:
            errors.append(f"v9_capability_baseline_count:{len(baseline_ids)}")
    else:
        errors.append("migration_baseline_missing")
    return {
        "schema_version": "10.0", "status": "pass" if not errors else "fail",
        "metrics": {
            "active_rules": sum(rule.get("status") == "active" for rule in rules),
            "capabilities": len({rule["capability"] for rule in rules if rule.get("status") == "active"}),
            "routes": len(routes), "events": len(event_vocabulary), "test_ids": len(test_ids),
            "atomic_cases": len(load_json(root / "evals/atomic-rule-cases.json").get("cases", [])),
            "runtime_guards": sum(rule.get("enforcement", {}).get("kind") == "runtime_guard" for rule in rules),
            "agent_obligations": sum(rule.get("enforcement", {}).get("kind") == "agent_obligation" for rule in rules),
        },
        "errors": sorted(set(errors)),
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
