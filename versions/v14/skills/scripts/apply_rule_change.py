#!/usr/bin/env python3
"""Validate and apply one typed rule change inside a verified staging clone."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

sys.dont_write_bytecode = True

from lib_v10 import (
    ContractError, Draft202012Validator, dump_json, json_output, load_json, load_rules,
)


RULE_ID_RE = re.compile(r"[A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+)+")
HASH_RE = re.compile(r"[0-9a-f]{64}")
RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}
REQUIRED_ENVELOPE = {
    "operation", "rule_id", "request", "old_behavior", "new_behavior",
    "trigger", "exceptions", "risk", "impact_analysis", "behavior_tests",
}
OPTIONAL_ENVELOPE = {
    "expected_owner", "expected_revision", "expected_rule_sha256",
    "replacement_ids", "replacement_expectations", "patch", "new_rule",
}
IDENTITY_FIELDS = {"id", "revision", "status", "capability", "domain", "owner", "semantic_key"}
DERIVED_FIELDS = {"tests"}
L0_FIELDS = {"instruction_gloss", "failure_example"}
L1_FIELDS = {"context_ref"}
L2_FIELDS = {
    "effect", "instruction", "forbidden", "evidence", "outcomes", "scope", "trigger",
    "routes", "exceptions", "conflicts_with", "supersedes", "legacy_refs", "refines", "depends_on",
}
L3_FIELDS = {"strength", "enforcement"}
L3_CAPABILITY_PREFIXES = ("GOV-MODE", "GOV-AUTH", "GOV-ROUTE", "STATE-", "REC-")
CASE_KINDS = {"positive", "near_negative", "conflict", "state_binding", "retirement"}
CASE_REQUIRED = {"id", "kind", "target_rule_id", "prompt", "expected"}
CASE_OPTIONAL = {
    "fixture", "component_id", "pair_id", "conflict_rule_ids", "resolution", "replacement_rule_ids",
}
ORACLE_REQUIRED = {"status", "route_ids", "target_selected"}
ORACLE_OPTIONAL = {
    "mode", "target_strength", "target_effect", "target_behavior", "target_failure",
    "target_evidence", "target_outcomes", "target_enforcement", "target_scope", "target_trigger",
    "target_exceptions", "target_context_ref", "target_fields", "target_conflicts_with", "target_refines", "target_depends_on",
    "selected_rule_ids", "excluded_rule_ids",
}
TARGET_ORACLE_FIELDS = {
    "target_strength", "target_effect", "target_behavior", "target_failure",
    "target_evidence", "target_outcomes", "target_enforcement", "target_scope", "target_trigger",
    "target_exceptions", "target_context_ref", "target_fields", "target_conflicts_with", "target_refines", "target_depends_on",
}


class MigrationReviewRequired(ContractError):
    """A candidate changed sealed semantics and requires a reviewed migration decision."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def canonical_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in rule.items() if key != "_bundle"}


def rule_sha256(rule: dict[str, Any]) -> str:
    payload = json.dumps(canonical_rule(rule), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rule_behavior(rule: dict[str, Any] | None) -> str | None:
    if rule is None:
        return None
    value = rule.get("instruction_gloss", rule.get("instruction"))
    return value if isinstance(value, str) else None


def rule_failure(rule: dict[str, Any] | None) -> str | None:
    if rule is None:
        return None
    value = rule.get("failure_example", rule.get("forbidden"))
    return value if isinstance(value, str) else None


def rule_schema_fields(root: Path) -> tuple[set[str], set[str]]:
    schema = load_json(root / "references/rule-atom.schema.json")
    definition = schema.get("$defs", {}).get("rule", {})
    properties = set(definition.get("properties", {}))
    required = set(definition.get("required", []))
    return properties, required


def patchable_fields(root: Path) -> set[str]:
    properties, _ = rule_schema_fields(root)
    return properties - IDENTITY_FIELDS - DERIVED_FIELDS


def find_rule_location(root: Path, rule_id: str) -> tuple[Path, dict[str, Any], int] | None:
    for path in sorted((root / "rules").glob("*.json")):
        bundle = load_json(path)
        for index, rule in enumerate(bundle.get("rules", [])):
            if rule.get("id") == rule_id:
                return path, bundle, index
    return None


def validate_atom_minimal(rule: dict[str, Any], owner_path: str, root: Path | None = None) -> list[str]:
    errors: list[str] = []
    if root is not None:
        schema = load_json(root / "references/rule-atom.schema.json")
        definition = schema.get("$defs", {}).get("rule", {})
        allowed, required = set(definition.get("properties", {})), set(definition.get("required", []))
        missing = required - rule.keys()
        extra = set(rule) - allowed
        if missing:
            errors.append("new_rule_missing:" + ",".join(sorted(missing)))
        if extra:
            errors.append("new_rule_extra:" + ",".join(sorted(extra)))
        if Draft202012Validator is None:
            errors.append("jsonschema_dependency_missing")
        else:
            for item in Draft202012Validator(definition).iter_errors(rule):
                location = "/".join(str(part) for part in item.absolute_path) or "<root>"
                errors.append(f"new_rule_schema:{location}:{item.validator}")
    else:
        required = {
            "id", "revision", "status", "capability", "domain", "owner", "strength", "semantic_key",
            "scope", "trigger", "effect", "evidence", "outcomes", "exceptions", "conflicts_with",
            "supersedes", "legacy_refs", "routes", "tests",
        }
        if required - rule.keys():
            errors.append("new_rule_missing:" + ",".join(sorted(required - rule.keys())))
    if rule.get("owner") != owner_path:
        errors.append("new_rule_owner_mismatch")
    effect = rule.get("effect")
    if not isinstance(effect, dict) or set(effect) != {"verb", "target", "value"}:
        errors.append("new_rule_effect_not_atomic")
    behavior = rule_behavior(rule)
    if behavior is not None and any(marker in behavior for marker in ("\n", "；", ";", "•")):
        errors.append("new_rule_behavior_compound")
    return errors


def validate_rule_bindings(rule: dict[str, Any], root: Path, existing_rule_id: str | None = None) -> list[str]:
    """Reject dead route selectors and duplicate live semantic owners before mutation."""
    errors: list[str] = []
    contract = load_json(root / "references/route-contract.json")
    known_routes = {item.get("id") for item in contract.get("routes", [])} | {"*", "@write", "@recovery"}
    routes = rule.get("routes")
    if rule.get("status") == "active" and (not isinstance(routes, list) or not routes):
        errors.append("active_rule_has_no_routes")
    if isinstance(routes, list):
        unknown = set(routes) - known_routes
        if unknown:
            errors.append("unknown_routes:" + ",".join(sorted(unknown)))
    rules, _ = load_rules(root)
    duplicates = [
        item["id"] for item in rules
        if item.get("status") == "active"
        and item.get("semantic_key") == rule.get("semantic_key")
        and item.get("id") != existing_rule_id
    ]
    if duplicates:
        errors.append("duplicate_semantic_owner:" + ",".join(sorted(duplicates)))
    return errors


def minimum_risk(
    operation: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    changed_fields: set[str],
) -> tuple[str, list[str]]:
    """Compute a binding lower bound from the actual target and changed fields."""
    reasons: list[str] = []
    rule = after or before or {}
    capability = str(rule.get("capability", ""))
    domain = str(rule.get("domain", ""))
    level = "L0"

    def raise_to(candidate: str, reason: str) -> None:
        nonlocal level
        if RISK_ORDER[candidate] > RISK_ORDER[level]:
            level = candidate
        reasons.append(reason)

    if operation == "retire":
        raise_to("L4", "retirement removes an active normative target")
    if operation == "add":
        raise_to("L2", "new active normative atom")
    operational_fields = changed_fields - L0_FIELDS - L1_FIELDS
    if operational_fields and (domain == "maintenance" or capability.startswith("MNT-")):
        raise_to("L4", f"maintenance-kernel normative change:{capability or domain}")
    elif operational_fields and (domain == "governance" or capability.startswith(L3_CAPABILITY_PREFIXES)):
        raise_to("L3", f"governance/state/recovery change:{capability or domain}")
    for field in sorted(changed_fields):
        if field in L3_FIELDS:
            raise_to("L3", f"control/enforcement field:{field}")
        elif field in L2_FIELDS:
            raise_to("L2", f"normative behavior field:{field}")
        elif field in L1_FIELDS:
            raise_to("L1", f"reference/context field:{field}")
        elif field in L0_FIELDS:
            raise_to("L0", f"non-normative gloss/example field:{field}")
        else:
            raise_to("L3", f"unclassified schema field:{field}")
    return level, sorted(set(reasons))


def build_impact_analysis(change: dict[str, Any], root: Path) -> dict[str, Any]:
    """Compute the exact pre-write impact closure from the prospective diff."""
    before, after, _, changed_fields, errors = prospective_change(change, root)
    if errors:
        raise ContractError("impact_analysis_unavailable:" + ";".join(errors))
    rules, _ = load_rules(root)
    by_id = {rule["id"]: rule for rule in rules}
    if after is not None:
        by_id[after["id"]] = {**after, "_bundle": by_id.get(after["id"], {}).get("_bundle")}
    target = after or before
    if target is None:
        raise ContractError("impact_analysis_target_missing")
    relation_fields = ("conflicts_with", "supersedes", "refines", "depends_on")
    selected = {target["id"]}
    capabilities = {target.get("capability")}
    if before is not None:
        selected.update(
            related for field in relation_fields for related in before.get(field, [])
            if isinstance(related, str) and related in by_id
        )
    changed = True
    while changed:
        changed = False
        for rule in by_id.values():
            relations = {
                related for field in relation_fields for related in rule.get(field, [])
                if isinstance(related, str)
            }
            if rule["id"] not in selected and rule.get("capability") not in capabilities and not relations & selected:
                continue
            previous = len(selected)
            selected.add(rule["id"])
            selected.update(item for item in relations if item in by_id)
            capabilities.add(rule.get("capability"))
            changed = changed or len(selected) != previous
    affected_routes: set[str] = set()
    affected_tests: set[str] = {
        case["id"] for case in change.get("behavior_tests", [])
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }
    edges: set[tuple[str, str, str]] = set()
    if before is not None:
        affected_routes.update(item for item in before.get("routes", []) if isinstance(item, str))
        affected_tests.update(item for item in before.get("tests", []) if isinstance(item, str))
        for route in before.get("routes", []):
            edges.add((before["id"], route, "selected_by"))
        for field in relation_fields:
            for related in before.get(field, []):
                edges.add((before["id"], related, field))
    for rule_id in sorted(selected):
        rule = by_id[rule_id]
        affected_routes.update(item for item in rule.get("routes", []) if isinstance(item, str))
        affected_tests.update(item for item in rule.get("tests", []) if isinstance(item, str))
        edges.add((rule_id, str(rule.get("owner")), "owned_by"))
        for route in rule.get("routes", []):
            edges.add((rule_id, route, "selected_by"))
        for test in rule.get("tests", []):
            edges.add((rule_id, test, "tested_by"))
        for field in relation_fields:
            for related in rule.get(field, []):
                edges.add((rule_id, related, field))
    contracts = {
        "references/change-envelope.schema.json", "references/rule-atom.schema.json",
        "references/ownership-contract.json", "references/route-contract.json",
        "references/state-machine.json", "evals/change-cases.json",
        "evals/atomic-rule-cases.json", "references/migration/capability-crosswalk.json",
        "references/migration/clause-preservation.json",
        "scripts/apply_rule_change.py", "scripts/resolve_route.py", "scripts/run_change_evals.py",
        "scripts/build_atomic_rule_cases.py", "scripts/run_atomic_rule_evals.py",
        "scripts/validate_contracts.py", "scripts/build_clause_preservation.py",
        "scripts/build_migration_coverage.py",
        "scripts/validate_migration.py",
    }
    for version in (before, after):
        if version is None:
            continue
        context_ref = version.get("context_ref")
        if isinstance(context_ref, str):
            contracts.add(context_ref.split("#", 1)[0])
        enforcement = version.get("enforcement")
        if isinstance(enforcement, dict):
            contracts.update(
                item.split("#", 1)[0] for item in enforcement.get("refs", [])
                if isinstance(item, str)
            )
    if changed_fields & {"scope", "trigger", "routes", "exceptions", "conflicts_with"}:
        contracts.update({"references/route-contract.json", "scripts/resolve_route.py"})
    if str(target.get("capability", "")).startswith(("STATE-", "REC-")):
        contracts.update({"references/state-machine.json", "references/state.schema.json"})
    minimum, _ = minimum_risk(str(change.get("operation")), before, after, changed_fields)
    proof: dict[str, Any] = {
        "status": "passed", "rule_id": change.get("rule_id"),
        "base_rule_sha256": rule_sha256(before) if before is not None else None,
        "candidate_rule_sha256": rule_sha256(after) if after is not None else None,
        "minimum_risk": minimum, "affected_rule_ids": sorted(selected),
        "affected_routes": sorted(affected_routes), "affected_test_ids": sorted(affected_tests),
        "affected_contracts": sorted(contracts),
        "relation_edges": [
            {"from": source, "to": destination, "kind": kind}
            for source, destination, kind in sorted(edges)
        ],
    }
    proof["analysis_sha256"] = canonical_sha256(proof)
    return proof


def validate_impact_analysis(change: dict[str, Any], root: Path) -> list[str]:
    try:
        expected = build_impact_analysis(change, root)
    except ContractError as exc:
        return [str(exc)]
    supplied = change.get("impact_analysis")
    if supplied != expected:
        return ["impact_analysis_mismatch"]
    return []


@dataclass
class ImpactPermit:
    root: str
    rule_id: str
    base_rule_sha256: str | None
    analysis_sha256: str
    tree_manifest_sha256: str
    issued_monotonic_ns: int
    seal: object
    consumed: bool = False


_IMPACT_PERMIT_SEAL = object()


def issue_impact_permit(change: dict[str, Any], root: Path) -> ImpactPermit:
    """Issue an in-memory, one-use capability only after a read-only impact pass."""
    errors = validate_impact_analysis(change, root)
    if errors:
        raise ContractError(";".join(errors))
    proof = change["impact_analysis"]
    return ImpactPermit(
        root=str(root.resolve()), rule_id=change["rule_id"],
        base_rule_sha256=proof["base_rule_sha256"], analysis_sha256=proof["analysis_sha256"],
        tree_manifest_sha256=manifest_sha256(tree_manifest(root, ignore_caches=True)),
        issued_monotonic_ns=time.monotonic_ns(), seal=_IMPACT_PERMIT_SEAL,
    )


def consume_impact_permit(
    change: dict[str, Any], root: Path, permit: ImpactPermit | None,
) -> dict[str, Any]:
    """Revalidate and consume the pre-write capability before mutation is reachable."""
    if not isinstance(permit, ImpactPermit) or permit.seal is not _IMPACT_PERMIT_SEAL:
        raise ContractError("impact_permit_required")
    if permit.consumed:
        raise ContractError("impact_permit_already_consumed")
    if permit.root != str(root.resolve()) or permit.rule_id != change.get("rule_id"):
        raise ContractError("impact_permit_target_mismatch")
    proof = change.get("impact_analysis")
    if not isinstance(proof, dict) or permit.analysis_sha256 != proof.get("analysis_sha256"):
        raise ContractError("impact_permit_analysis_mismatch")
    current_manifest = manifest_sha256(tree_manifest(root, ignore_caches=True))
    if current_manifest != permit.tree_manifest_sha256:
        raise ContractError("impact_permit_stale_tree")
    location = find_rule_location(root, permit.rule_id)
    current_hash = rule_sha256(location[1]["rules"][location[2]]) if location is not None else None
    if current_hash != permit.base_rule_sha256:
        raise ContractError("impact_permit_stale_rule")
    errors = validate_impact_analysis(change, root)
    if errors:
        raise ContractError(";".join(errors))
    passed_ns = time.monotonic_ns()
    while passed_ns <= permit.issued_monotonic_ns:
        passed_ns = time.monotonic_ns()
    permit.consumed = True
    return {
        "sequence": 1, "event": "impact_analysis_passed",
        "monotonic_ns": passed_ns, "analysis_sha256": permit.analysis_sha256,
    }


def _owner_expectation_errors(change: dict[str, Any], current: dict[str, Any]) -> list[str]:
    errors = []
    if change.get("expected_owner") is None:
        errors.append("expected_owner_required")
    elif change["expected_owner"] != current.get("owner"):
        errors.append("expected_owner_mismatch")
    if change.get("expected_revision") is None:
        errors.append("expected_revision_required")
    elif change["expected_revision"] != current.get("revision"):
        errors.append("expected_revision_mismatch")
    expected_hash = change.get("expected_rule_sha256")
    if expected_hash is None:
        errors.append("expected_rule_sha256_required")
    elif expected_hash != rule_sha256(current):
        errors.append("expected_rule_sha256_mismatch")
    return errors


def prospective_change(
    change: dict[str, Any], root: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, tuple[Path, dict[str, Any], int] | None, set[str], list[str]]:
    errors: list[str] = []
    operation = change.get("operation")
    rule_id = str(change.get("rule_id", ""))
    location = find_rule_location(root, rule_id)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    changed_fields: set[str] = set()
    test_ids = {
        item.get("id") for item in change.get("behavior_tests", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }

    if operation == "add":
        if location is not None:
            errors.append("add_target_exists")
            return None, None, location, changed_fields, errors
        new_rule = change.get("new_rule")
        if not isinstance(new_rule, dict) or new_rule.get("id") != rule_id:
            errors.append("add_requires_matching_new_rule")
            return None, None, None, changed_fields, errors
        after = dict(new_rule)
        after["tests"] = sorted(set(after.get("tests", [])) | test_ids)
        if after.get("revision") != 1:
            errors.append("new_rule_revision_must_be_1")
        if after.get("status") != "active":
            errors.append("new_rule_status_must_be_active")
        owner = str(after.get("owner", ""))
        owner_file = owner.split("#", 1)[0]
        owner_path = (root / owner_file).resolve()
        try:
            owner_path.relative_to(root.resolve())
        except ValueError:
            errors.append("new_owner_escapes_root")
            return before, after, None, set(after), errors
        expected_owner = f"{owner_path.relative_to(root).as_posix()}#{rule_id}"
        if not owner_path.is_file():
            errors.append("new_owner_bundle_missing")
        else:
            bundle = load_json(owner_path)
            if bundle.get("domain") != after.get("domain"):
                errors.append("new_rule_domain_owner_mismatch")
        errors.extend(validate_atom_minimal(after, expected_owner, root))
        errors.extend(validate_rule_bindings(after, root))
        changed_fields = set(after) - IDENTITY_FIELDS - DERIVED_FIELDS
    elif operation in {"modify", "retire"}:
        if location is None:
            errors.append(f"{operation}_target_not_found")
            return None, None, None, changed_fields, errors
        path, bundle, index = location
        before = dict(bundle["rules"][index])
        errors.extend(_owner_expectation_errors(change, before))
        if operation == "modify":
            patch = change.get("patch")
            if not isinstance(patch, dict) or not patch:
                errors.append("modify_requires_nonempty_patch")
                return before, None, location, changed_fields, errors
            forbidden = set(patch) - patchable_fields(root)
            if forbidden:
                errors.append("patch_fields_forbidden:" + ",".join(sorted(forbidden)))
            after = dict(before)
            after.update(patch)
            after["revision"] = before["revision"] + 1
            after["tests"] = sorted(set(after.get("tests", [])) | test_ids)
            changed_fields = {field for field in patch if before.get(field) != after.get(field)}
            if not changed_fields:
                errors.append("patch_has_no_effect")
            errors.extend(validate_atom_minimal(after, before["owner"], root))
            errors.extend(validate_rule_bindings(after, root, before["id"]))
        else:
            after = dict(before)
            after.update({"status": "retired", "revision": before["revision"] + 1, "routes": []})
            after["tests"] = sorted(set(after.get("tests", [])) | test_ids)
            changed_fields = {"status", "routes"}
    return before, after, location, changed_fields, errors


def validate_replacements(change: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    ids = change.get("replacement_ids")
    expectations = change.get("replacement_expectations")
    if not isinstance(ids, list) or not ids or len(ids) != len(set(ids)):
        return ["replacement_ids_invalid"]
    if change.get("rule_id") in ids:
        errors.append("retired_rule_cannot_replace_itself")
    if not isinstance(expectations, list):
        return ["replacement_expectations_required"]
    by_expectation = {
        item.get("id"): item for item in expectations
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if set(by_expectation) != set(ids) or len(by_expectation) != len(expectations):
        errors.append("replacement_expectations_id_mismatch")
        return errors
    _, by_id = load_rules(root)
    for replacement_id in ids:
        rule = by_id.get(replacement_id)
        expected = by_expectation[replacement_id]
        if rule is None or rule.get("status") != "active":
            errors.append(f"replacement_invalid:{replacement_id}")
            continue
        if expected.get("expected_owner") != rule.get("owner"):
            errors.append(f"replacement_owner_mismatch:{replacement_id}")
        if expected.get("expected_revision") != rule.get("revision"):
            errors.append(f"replacement_revision_mismatch:{replacement_id}")
        if expected.get("expected_rule_sha256") != rule_sha256(rule):
            errors.append(f"replacement_hash_mismatch:{replacement_id}")
    return errors


def validate_oracle(oracle: Any, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(oracle, dict):
        return [f"{label}:not_object"]
    missing = ORACLE_REQUIRED - oracle.keys()
    extra = set(oracle) - ORACLE_REQUIRED - ORACLE_OPTIONAL
    if missing:
        errors.append(f"{label}:missing:" + ",".join(sorted(missing)))
    if extra:
        errors.append(f"{label}:unknown:" + ",".join(sorted(extra)))
    if oracle.get("status") not in {"resolved", "blocked", "ambiguous"}:
        errors.append(f"{label}:status_invalid")
    route_ids = oracle.get("route_ids", [])
    if not isinstance(route_ids, list) or any(not isinstance(item, str) for item in route_ids):
        errors.append(f"{label}:route_ids_invalid")
    elif len(route_ids) != len(set(route_ids)):
        errors.append(f"{label}:route_ids_duplicate")
    if not isinstance(oracle.get("target_selected"), bool):
        errors.append(f"{label}:target_selected_invalid")
    for field in ("selected_rule_ids", "excluded_rule_ids"):
        if field in oracle and (not isinstance(oracle[field], list) or any(not isinstance(item, str) for item in oracle[field])):
            errors.append(f"{label}:{field}_invalid")
        elif field in oracle and len(oracle[field]) != len(set(oracle[field])):
            errors.append(f"{label}:{field}_duplicate")
    if set(oracle.get("selected_rule_ids", [])) & set(oracle.get("excluded_rule_ids", [])):
        errors.append(f"{label}:selected_excluded_overlap")
    if oracle.get("target_selected") and not isinstance(oracle.get("target_effect"), dict):
        errors.append(f"{label}:selected_target_effect_required")
    if "target_fields" in oracle and not isinstance(oracle["target_fields"], dict):
        errors.append(f"{label}:target_fields_invalid")
    if oracle.get("target_selected") is False:
        forbidden = TARGET_ORACLE_FIELDS & oracle.keys()
        if forbidden:
            errors.append(f"{label}:unselected_target_fields:" + ",".join(sorted(forbidden)))
    return errors


def _fixture_state(case: dict[str, Any]) -> str | None:
    fixture = case.get("fixture")
    component_id = case.get("component_id")
    if not isinstance(fixture, dict) or not isinstance(component_id, str):
        return None
    for component in fixture.get("components", []):
        if isinstance(component, dict) and component.get("id") == component_id:
            return component.get("state") if isinstance(component.get("state"), str) else None
    return None


def validate_fixture(fixture: Any, label: str, root: Path | None = None) -> list[str]:
    if not isinstance(fixture, dict):
        return [f"{label}:fixture_not_object"]
    errors: list[str] = []
    allowed = {"project_state", "missing_state", "components", "open_decisions", "r1_changed_artifact"}
    extra = set(fixture) - allowed
    if extra:
        errors.append(f"{label}:fixture_unknown:" + ",".join(sorted(extra)))
    if "missing_state" in fixture and not isinstance(fixture["missing_state"], bool):
        errors.append(f"{label}:fixture_missing_state_invalid")
    if "project_state" in fixture and not isinstance(fixture["project_state"], str):
        errors.append(f"{label}:fixture_project_state_invalid")
    components = fixture.get("components", [])
    if not isinstance(components, list):
        errors.append(f"{label}:fixture_components_invalid")
        components = []
    component_ids: list[str] = []
    allowed_states: dict[str, set[str]] = {}
    if root is not None:
        machine = load_json(root / "references/state-machine.json")
        allowed_states = {
            key: set(values) for key, values in machine.get("state_sets", {}).items()
            if isinstance(values, list)
        }
        project_state = fixture.get("project_state", "P0")
        if project_state not in allowed_states.get("project", set()):
            errors.append(f"{label}:fixture_project_state_unknown")
    for index, component in enumerate(components):
        item_label = f"{label}:fixture_component:{index}"
        if not isinstance(component, dict) or not {"id", "type", "state"} <= component.keys():
            errors.append(item_label + ":shape")
            continue
        extra_component = set(component) - {"id", "type", "state", "status"}
        if extra_component:
            errors.append(item_label + ":unknown:" + ",".join(sorted(extra_component)))
        component_id = component.get("id")
        component_type = component.get("type")
        state = component.get("state")
        if not isinstance(component_id, str) or not component_id or any(part in {"", ".", ".."} for part in Path(component_id).parts):
            errors.append(item_label + ":id_invalid")
        else:
            component_ids.append(component_id)
        if component_type not in {"project", "question", "shared_data", "artifact"}:
            errors.append(item_label + ":type_invalid")
        if not isinstance(state, str) or not state:
            errors.append(item_label + ":state_invalid")
        elif root is not None and state not in allowed_states.get(str(component_type), set()):
            errors.append(item_label + ":state_type_mismatch")
        if "status" in component and component["status"] not in {"active", "closed", "blocked", "invalidated"}:
            errors.append(item_label + ":status_invalid")
    if len(component_ids) != len(set(component_ids)):
        errors.append(f"{label}:fixture_component_ids_duplicate")
    if "open_decisions" in fixture and not isinstance(fixture["open_decisions"], list):
        errors.append(f"{label}:fixture_open_decisions_invalid")
    changed = fixture.get("r1_changed_artifact")
    if changed is not None:
        if not isinstance(changed, dict) or set(changed) - {"path", "producer", "content"} or "producer" not in changed:
            errors.append(f"{label}:fixture_changed_artifact_shape")
        else:
            raw_path = changed.get("path", "changed.txt")
            path = Path(raw_path) if isinstance(raw_path, str) else Path("/")
            if (
                not isinstance(raw_path, str) or not raw_path or path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
            ):
                errors.append(f"{label}:fixture_changed_artifact_path_unsafe")
            if changed.get("producer") not in set(component_ids):
                errors.append(f"{label}:fixture_changed_artifact_producer_unknown")
            if "content" in changed and not isinstance(changed["content"], str):
                errors.append(f"{label}:fixture_changed_artifact_content_invalid")
            elif isinstance(changed.get("content"), str) and len(changed["content"]) > 100000:
                errors.append(f"{label}:fixture_changed_artifact_content_too_large")
    return errors


def _rules_conflict(left: dict[str, Any] | None, right: dict[str, Any] | None) -> bool:
    if left is None or right is None:
        return False
    return (
        right.get("id") in set(left.get("conflicts_with", []))
        or left.get("id") in set(right.get("conflicts_with", []))
    )


def validate_behavior_tests(
    change: dict[str, Any], before: dict[str, Any] | None, after: dict[str, Any] | None, minimum: str,
    root: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    tests = change.get("behavior_tests")
    if not isinstance(tests, list) or not tests:
        return ["behavior_tests_empty"]
    ids = [item.get("id") for item in tests if isinstance(item, dict)]
    if len(ids) != len(tests) or any(not isinstance(item, str) or not item for item in ids) or len(ids) != len(set(ids)):
        errors.append("behavior_test_ids_invalid")
    kinds: list[str] = []
    state_pairs: dict[str, list[dict[str, Any]]] = {}
    rule_id = change.get("rule_id")
    operation = change.get("operation")
    patch = change.get("patch", {}) if isinstance(change.get("patch"), dict) else {}
    root_rules = load_rules(root)[1] if root is not None else {}

    for index, case in enumerate(tests):
        label = f"behavior_test:{index}"
        if not isinstance(case, dict):
            errors.append(label + ":not_object")
            continue
        missing = CASE_REQUIRED - case.keys()
        extra = set(case) - CASE_REQUIRED - CASE_OPTIONAL
        if missing:
            errors.append(label + ":missing:" + ",".join(sorted(missing)))
        if extra:
            errors.append(label + ":unknown:" + ",".join(sorted(extra)))
        if not isinstance(case.get("id"), str) or not case["id"] or re.fullmatch(r"[A-Z0-9_.-]+", case["id"]) is None:
            errors.append(label + ":id_invalid")
        if not isinstance(case.get("prompt"), str) or len(case["prompt"].strip()) < 2:
            errors.append(label + ":prompt_invalid")
        if "fixture" in case:
            errors.extend(validate_fixture(case["fixture"], label, root))
        kind = case.get("kind")
        if kind not in CASE_KINDS:
            errors.append(label + ":kind_invalid")
            continue
        kinds.append(kind)
        if case.get("target_rule_id") != rule_id:
            errors.append(label + ":target_rule_mismatch")
        expected = case.get("expected")
        if not isinstance(expected, dict) or set(expected) != {"base", "candidate"}:
            errors.append(label + ":expected_shape")
            continue
        errors.extend(validate_oracle(expected.get("base"), label + ":base"))
        errors.extend(validate_oracle(expected.get("candidate"), label + ":candidate"))
        base = expected.get("base", {}) if isinstance(expected.get("base"), dict) else {}
        candidate = expected.get("candidate", {}) if isinstance(expected.get("candidate"), dict) else {}
        for oracle_label, oracle in (("base", base), ("candidate", candidate)):
            declared_selected = oracle.get("selected_rule_ids")
            if isinstance(declared_selected, list) and (
                (rule_id in declared_selected) != bool(oracle.get("target_selected"))
            ):
                errors.append(label + f":{oracle_label}:target_selection_list_inconsistent")

        if kind == "positive":
            if not candidate.get("target_selected"):
                errors.append(label + ":positive_target_not_selected")
            if operation == "add" and base.get("target_selected"):
                errors.append(label + ":add_positive_selected_in_base")
            if operation == "modify" and not base.get("target_selected"):
                errors.append(label + ":modify_positive_missing_in_base")
        elif kind == "near_negative":
            if candidate.get("target_selected"):
                errors.append(label + ":near_negative_selected")
        elif kind == "conflict":
            conflicts = case.get("conflict_rule_ids")
            resolution = case.get("resolution")
            if not isinstance(conflicts, list) or not conflicts or len(conflicts) != len(set(conflicts)):
                errors.append(label + ":conflict_rule_ids_invalid")
                conflicts = []
            elif rule_id in conflicts or any(RULE_ID_RE.fullmatch(str(item)) is None for item in conflicts):
                errors.append(label + ":conflict_rule_ids_invalid")
            if resolution not in {"blocked", "target_wins", "target_loses", "disjoint"}:
                errors.append(label + ":resolution_invalid")
            elif resolution == "blocked" and candidate.get("status") not in {"blocked", "ambiguous"}:
                errors.append(label + ":blocked_resolution_not_observed")
            elif resolution == "target_wins":
                if not candidate.get("target_selected") or not set(conflicts or []) <= set(candidate.get("excluded_rule_ids", [])):
                    errors.append(label + ":target_wins_oracle_invalid")
            elif resolution == "target_loses":
                if candidate.get("target_selected") or not set(conflicts or []) <= set(candidate.get("selected_rule_ids", [])):
                    errors.append(label + ":target_loses_oracle_invalid")
            elif resolution == "disjoint":
                target_selection_ok = (
                    not candidate.get("target_selected") if operation == "retire"
                    else bool(candidate.get("target_selected"))
                )
                if not target_selection_ok or not set(conflicts or []) <= set(candidate.get("excluded_rule_ids", [])):
                    errors.append(label + ":disjoint_oracle_invalid")
            if root is not None and conflicts:
                target_rule = after or before
                missing_conflicts = sorted(item for item in conflicts if item not in root_rules)
                if missing_conflicts:
                    errors.append(label + ":conflict_targets_missing:" + ",".join(missing_conflicts))
                declared = {
                    item for item in conflicts
                    if _rules_conflict(target_rule, root_rules.get(item))
                }
                if resolution == "disjoint" and declared:
                    errors.append(label + ":disjoint_has_declared_conflict:" + ",".join(sorted(declared)))
                if resolution != "disjoint" and set(conflicts) - declared:
                    errors.append(
                        label + ":undeclared_conflict:" + ",".join(sorted(set(conflicts) - declared))
                    )
        elif kind == "state_binding":
            pair_id = case.get("pair_id")
            if not isinstance(pair_id, str) or not pair_id:
                errors.append(label + ":state_pair_id_required")
            else:
                state_pairs.setdefault(pair_id, []).append(case)
            if _fixture_state(case) is None:
                errors.append(label + ":state_fixture_required")
        elif kind == "retirement":
            replacements = case.get("replacement_rule_ids")
            if operation != "retire":
                errors.append(label + ":retirement_case_for_nonretire")
            if not base.get("target_selected") or candidate.get("target_selected"):
                errors.append(label + ":retirement_target_oracle_invalid")
            if not isinstance(replacements, list) or set(replacements) != set(change.get("replacement_ids", [])):
                errors.append(label + ":retirement_replacements_mismatch")
            elif not set(replacements) <= set(candidate.get("selected_rule_ids", [])):
                errors.append(label + ":retirement_replacements_not_selected")

        for oracle_label, oracle, rule in (("base", base, before), ("candidate", candidate, after)):
            if not oracle.get("target_selected") or rule is None:
                continue
            if oracle.get("target_effect") != rule.get("effect"):
                errors.append(f"{label}:{oracle_label}:target_effect_mismatch")
            if "target_strength" in oracle and oracle["target_strength"] != rule.get("strength"):
                errors.append(f"{label}:{oracle_label}:target_strength_mismatch")
            if "target_behavior" in oracle and oracle["target_behavior"] != rule_behavior(rule):
                errors.append(f"{label}:{oracle_label}:target_behavior_mismatch")
            if "target_failure" in oracle and oracle["target_failure"] != rule_failure(rule):
                errors.append(f"{label}:{oracle_label}:target_failure_mismatch")
            for oracle_key, rule_key in (
                ("target_evidence", "evidence"), ("target_outcomes", "outcomes"),
                ("target_enforcement", "enforcement"), ("target_scope", "scope"),
                ("target_trigger", "trigger"), ("target_exceptions", "exceptions"),
                ("target_context_ref", "context_ref"),
                ("target_conflicts_with", "conflicts_with"), ("target_refines", "refines"),
                ("target_depends_on", "depends_on"),
            ):
                if oracle_key in oracle and oracle[oracle_key] != rule.get(rule_key):
                    errors.append(f"{label}:{oracle_label}:{oracle_key}_mismatch")
            target_fields = oracle.get("target_fields")
            if target_fields is not None:
                if not isinstance(target_fields, dict):
                    errors.append(f"{label}:{oracle_label}:target_fields_invalid")
                else:
                    unknown_fields = set(target_fields) - set(rule)
                    if unknown_fields:
                        errors.append(
                            f"{label}:{oracle_label}:target_fields_unknown:" + ",".join(sorted(unknown_fields))
                        )
                    for field, expected_value in target_fields.items():
                        if field in rule and rule.get(field) != expected_value:
                            errors.append(f"{label}:{oracle_label}:target_fields_mismatch:{field}")

    if operation in {"add", "modify"} and RISK_ORDER.get(minimum, 4) >= RISK_ORDER["L2"]:
        missing = {"positive", "near_negative", "conflict", "state_binding"} - set(kinds)
        if missing:
            errors.append("behavior_test_kinds_missing:" + ",".join(sorted(missing)))
    elif operation == "retire":
        missing = {"retirement", "near_negative", "conflict"} - set(kinds)
        if missing:
            errors.append("behavior_test_kinds_missing:" + ",".join(sorted(missing)))
    elif "positive" not in kinds:
        errors.append("behavior_test_kinds_missing:positive")

    for pair_id, cases in state_pairs.items():
        states = {_fixture_state(case) for case in cases}
        selections = {
            case.get("expected", {}).get("candidate", {}).get("target_selected")
            for case in cases if isinstance(case.get("expected"), dict)
        }
        prompts = {case.get("prompt") for case in cases}
        targets = {case.get("target_rule_id") for case in cases}
        components = {case.get("component_id") for case in cases}
        if len(cases) != 2 or len(states) != 2 or selections != {True, False} or len(prompts) != 1 or len(targets) != 1 or len(components) != 1:
            errors.append(f"state_binding_pair_invalid:{pair_id}")

    positive = next((case for case in tests if isinstance(case, dict) and case.get("kind") == "positive"), None)
    if operation == "modify" and positive is not None:
        base_oracle = positive["expected"]["base"]
        candidate_oracle = positive["expected"]["candidate"]
        observable_map = {
            "effect": "target_effect", "strength": "target_strength",
            "instruction": "target_behavior", "instruction_gloss": "target_behavior",
            "forbidden": "target_failure", "failure_example": "target_failure",
            "evidence": "target_evidence", "outcomes": "target_outcomes", "enforcement": "target_enforcement",
            "scope": "target_scope", "trigger": "target_trigger", "exceptions": "target_exceptions",
            "context_ref": "target_context_ref",
            "conflicts_with": "target_conflicts_with", "refines": "target_refines",
            "depends_on": "target_depends_on",
        }
        for field in set(patch):
            oracle_key = observable_map.get(field)
            if oracle_key is not None:
                if oracle_key not in base_oracle or oracle_key not in candidate_oracle or base_oracle.get(oracle_key) == candidate_oracle.get(oracle_key):
                    errors.append(f"positive_oracle_not_differential:{field}")
                continue
            base_fields = base_oracle.get("target_fields")
            candidate_fields = candidate_oracle.get("target_fields")
            if (
                not isinstance(base_fields, dict) or not isinstance(candidate_fields, dict)
                or field not in base_fields or field not in candidate_fields
                or base_fields.get(field) == candidate_fields.get(field)
            ):
                errors.append(f"positive_oracle_not_differential:{field}")
    return errors


def validate_envelope(change: Any, root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(change, dict):
        return ["change_not_object"]
    schema = load_json(root / "references/change-envelope.schema.json")
    if Draft202012Validator is None:
        errors.append("jsonschema_dependency_missing")
    else:
        for item in Draft202012Validator(schema).iter_errors(change):
            location = "/".join(str(part) for part in item.absolute_path) or "<root>"
            errors.append(f"change_schema:{location}:{item.validator}")
    missing = REQUIRED_ENVELOPE - change.keys()
    extra = set(change) - REQUIRED_ENVELOPE - OPTIONAL_ENVELOPE
    if missing:
        errors.append("missing_fields:" + ",".join(sorted(missing)))
    if extra:
        errors.append("extra_fields:" + ",".join(sorted(extra)))
    operation = change.get("operation")
    if operation not in {"add", "modify", "retire"}:
        errors.append("operation_invalid")
    operation_only_fields = {
        "add": {"new_rule"},
        "modify": {"patch", "expected_owner", "expected_revision", "expected_rule_sha256"},
        "retire": {
            "expected_owner", "expected_revision", "expected_rule_sha256",
            "replacement_ids", "replacement_expectations",
        },
    }
    if operation in operation_only_fields:
        supplied = OPTIONAL_ENVELOPE & change.keys()
        invalid = supplied - operation_only_fields[operation]
        if operation == "add":
            invalid -= {
                field for field in ("expected_owner", "expected_revision", "expected_rule_sha256")
                if change.get(field) is None
            }
        if invalid:
            errors.append("fields_invalid_for_operation:" + ",".join(sorted(invalid)))
    rule_id = str(change.get("rule_id", ""))
    if RULE_ID_RE.fullmatch(rule_id) is None:
        errors.append("rule_id_invalid")
    if not isinstance(change.get("request"), str) or len(change["request"].strip()) < 3:
        errors.append("request_invalid")
    if change.get("risk") not in RISK_ORDER:
        errors.append("risk_invalid")

    before, after, _, changed_fields, prospective_errors = prospective_change(change, root)
    errors.extend(prospective_errors)
    if operation == "retire":
        errors.extend(validate_replacements(change, root))
    if before is not None or after is not None:
        if change.get("old_behavior") != rule_behavior(before):
            errors.append("old_behavior_mismatch")
        expected_new = None if operation == "retire" else rule_behavior(after)
        if change.get("new_behavior") != expected_new:
            errors.append("new_behavior_mismatch")
        trigger_owner = before if operation == "retire" else after
        if trigger_owner is not None and change.get("trigger") != trigger_owner.get("trigger"):
            errors.append("trigger_mismatch")
        if trigger_owner is not None and change.get("exceptions") != trigger_owner.get("exceptions"):
            errors.append("exceptions_mismatch")

        minimum, _ = minimum_risk(str(operation), before, after, changed_fields)
        if change.get("risk") in RISK_ORDER and RISK_ORDER[change["risk"]] < RISK_ORDER[minimum]:
            errors.append(f"risk_underreported:{change['risk']}<{minimum}")
        errors.extend(validate_behavior_tests(change, before, after, minimum, root))
        errors.extend(validate_impact_analysis(change, root))
    return sorted(set(errors))


def append_change_cases(root: Path, tests: list[dict[str, Any]]) -> None:
    path = root / "evals/change-cases.json"
    payload = load_json(path)
    existing = {case["id"] for case in payload.get("cases", [])}
    overlap = existing & {case["id"] for case in tests}
    if overlap:
        raise ContractError("behavior test ids already exist: " + ",".join(sorted(overlap)))
    payload["cases"].extend(tests)
    dump_json(path, payload)


def rebuild_atomic_cases(root: Path) -> Path:
    """Regenerate the derived one-case-per-active-atom oracle in a fresh process."""
    script = root / "scripts/build_atomic_rule_cases.py"
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, str(script), "--root", str(root)],
        text=True, capture_output=True, cwd=root, env=environment, timeout=120,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout)[-2000:]
        raise ContractError(f"atomic_case_rebuild_failed:{detail}")
    return root / "evals/atomic-rule-cases.json"


def rebuild_migration_evidence(root: Path, v9_root: Path) -> list[Path]:
    """Recompile derived evidence; the compiler itself rejects unreviewed semantic changes."""
    script = root / "scripts/build_migration_coverage.py"
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [
            sys.executable, str(script), "--v9-root", str(v9_root),
            "--output-root", str(root),
        ],
        text=True, capture_output=True, cwd=root, env=environment, timeout=120,
    )
    if process.returncode != 0:
        detail = (process.stderr or process.stdout)[-4000:]
        if "semantics changed without a versioned migration re-seal" in detail:
            raise MigrationReviewRequired(detail)
        raise ContractError(f"migration_evidence_rebuild_failed:{detail}")
    return [
        root / "references/migration/v9-capability-baseline.json",
        root / "references/migration/clause-preservation.json",
        root / "references/migration/capability-crosswalk.json",
        root / "references/migration/legacy-coverage.json",
    ]


def validate_transaction_events(events: Any) -> list[str]:
    if not isinstance(events, list) or len(events) != 2:
        return ["transaction_event_count_invalid"]
    if [item.get("event") for item in events if isinstance(item, dict)] != [
        "impact_analysis_passed", "rule_write",
    ]:
        return ["transaction_event_order_invalid"]
    if [item.get("sequence") for item in events if isinstance(item, dict)] != [1, 2]:
        return ["transaction_event_sequence_invalid"]
    timestamps = [item.get("monotonic_ns") for item in events if isinstance(item, dict)]
    if len(timestamps) != 2 or any(not isinstance(item, int) for item in timestamps):
        return ["transaction_event_time_invalid"]
    if timestamps[0] >= timestamps[1]:
        return ["impact_analysis_not_before_rule_write"]
    return []


def apply_change(
    change: dict[str, Any], root: Path, permit: ImpactPermit | None,
    details_sink: dict[str, Any] | None = None,
) -> tuple[list[Path], dict[str, Any]]:
    impact_event = consume_impact_permit(change, root, permit)
    before, after, location, changed_fields, errors = prospective_change(change, root)
    if errors or after is None:
        raise ContractError("; ".join(errors or ["prospective change unavailable"]))
    operation = change["operation"]
    rule_id = change["rule_id"]
    touched: set[Path] = set()
    details: dict[str, Any] = details_sink if details_sink is not None else {}
    details.update({
        "operation": operation, "rule_id": rule_id,
        "transaction_events": [impact_event],
    })
    minimum, reasons = minimum_risk(operation, before, after, changed_fields)
    details.update({"minimum_risk": minimum, "risk_reasons": reasons})
    if minimum == "L4":
        raise ContractError("requires_major_fork")

    def enter_rule_write() -> None:
        if len(details["transaction_events"]) != 1:
            raise ContractError("rule_write_boundary_reentered")
        current_manifest = manifest_sha256(tree_manifest(root, ignore_caches=True))
        if current_manifest != permit.tree_manifest_sha256:
            raise ContractError("impact_permit_stale_at_write_boundary")
        write_ns = time.monotonic_ns()
        while write_ns <= impact_event["monotonic_ns"]:
            write_ns = time.monotonic_ns()
        details["transaction_events"].append({
            "sequence": 2, "event": "rule_write", "monotonic_ns": write_ns,
        })
        event_errors = validate_transaction_events(details["transaction_events"])
        if event_errors:
            raise ContractError(";".join(event_errors))

    if operation == "add":
        owner_file = str(after["owner"]).split("#", 1)[0]
        path = (root / owner_file).resolve()
        bundle = load_json(path)
        bundle["rules"].append(after)
        bundle["rules"].sort(key=lambda item: item["id"])
        enter_rule_write()
        dump_json(path, bundle)
        touched.add(path)
        details["owner"] = after["owner"]
    else:
        assert location is not None
        path, bundle, index = location
        bundle["rules"][index] = after
        enter_rule_write()
        dump_json(path, bundle)
        touched.add(path)
        details.update({"owner": after["owner"], "revision": after["revision"]})
        if operation == "retire":
            for replacement_id in change["replacement_ids"]:
                replacement_location = find_rule_location(root, replacement_id)
                if replacement_location is None:
                    raise ContractError(f"replacement disappeared during transaction: {replacement_id}")
                replacement_path, replacement_bundle, replacement_index = replacement_location
                replacement = dict(replacement_bundle["rules"][replacement_index])
                replacement["supersedes"] = sorted(set(replacement.get("supersedes", [])) | {rule_id})
                replacement["revision"] += 1
                replacement_bundle["rules"][replacement_index] = replacement
                dump_json(replacement_path, replacement_bundle)
                touched.add(replacement_path)
            details["replacements"] = change["replacement_ids"]

    append_change_cases(root, change["behavior_tests"])
    touched.add(root / "evals/change-cases.json")
    touched.add(rebuild_atomic_cases(root))
    return sorted(touched), details


def _ignored_manifest_path(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    return "__pycache__" in rel.parts or path.suffix in {".pyc", ".pyo"}


def tree_manifest(root: Path, ignore_caches: bool = False) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ContractError(f"staging tree contains symlink: {path.relative_to(root)}")
        if ignore_caches and _ignored_manifest_path(path, root):
            continue
        relative = path.relative_to(root).as_posix()
        mode = path.stat().st_mode & 0o777
        if path.is_dir():
            manifest[relative + "/"] = f"dir:{mode:03o}"
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest[relative] = f"file:{mode:03o}:{digest}"
        else:
            raise ContractError(f"staging tree contains unsupported node: {relative}")
    return manifest


def manifest_sha256(manifest: dict[str, str]) -> str:
    payload = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TreeSnapshot:
    files: dict[str, tuple[bytes, int]]
    directories: dict[str, int]


def snapshot_tree(root: Path) -> TreeSnapshot:
    files: dict[str, tuple[bytes, int]] = {}
    directories: dict[str, int] = {"": root.stat().st_mode & 0o777}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ContractError(f"staging tree contains symlink: {path.relative_to(root)}")
        if path.is_file():
            files[path.relative_to(root).as_posix()] = (path.read_bytes(), path.stat().st_mode & 0o777)
        elif path.is_dir():
            directories[path.relative_to(root).as_posix()] = path.stat().st_mode & 0o777
        else:
            raise ContractError(f"staging tree contains unsupported node: {path.relative_to(root)}")
    return TreeSnapshot(files=files, directories=directories)


def restore_tree(root: Path, snapshot: TreeSnapshot) -> None:
    """Restore files, empty directories, and permission modes from one closed snapshot."""
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or (path.is_file() and relative not in snapshot.files):
            path.unlink()
    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if not path.is_dir():
            continue
        relative = path.relative_to(root).as_posix()
        if relative not in snapshot.directories:
            try:
                path.rmdir()
            except OSError as exc:
                raise ContractError(f"rollback_extra_directory_not_empty:{relative}") from exc
    for rel in sorted(snapshot.directories, key=lambda item: (len(Path(item).parts), item)):
        if not rel:
            continue
        path = root / rel
        if path.exists() and not path.is_dir():
            path.unlink()
        path.mkdir(parents=True, exist_ok=True)
    for rel, (payload, mode) in snapshot.files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            path.rmdir()
        descriptor, temporary_name = tempfile.mkstemp(prefix=".v10-rollback-", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
    for rel, mode in sorted(snapshot.directories.items(), key=lambda item: len(Path(item[0]).parts), reverse=True):
        os.chmod(root / rel if rel else root, mode)


def snapshot_digest(snapshot: TreeSnapshot) -> str:
    manifest = {
        rel: f"file:{mode:03o}:{hashlib.sha256(payload).hexdigest()}"
        for rel, (payload, mode) in snapshot.files.items()
    }
    manifest.update({rel + "/": f"dir:{mode:03o}" for rel, mode in snapshot.directories.items() if rel})
    manifest["<root>/"] = f"dir:{snapshot.directories['']:03o}"
    return manifest_sha256(manifest)


def ensure_isolated_staging(base: Path, candidate: Path) -> list[str]:
    errors: list[str] = []
    if base == candidate:
        return ["candidate_must_differ_from_base"]
    try:
        if os.path.samefile(base, candidate):
            return ["candidate_must_differ_from_base"]
    except OSError:
        pass
    try:
        candidate.relative_to(base)
        errors.append("candidate_must_not_be_inside_base")
    except ValueError:
        pass
    try:
        base.relative_to(candidate)
        errors.append("base_must_not_be_inside_candidate")
    except ValueError:
        pass
    if not base.is_dir() or not candidate.is_dir():
        errors.append("base_and_candidate_must_exist")
        return errors
    if (base.stat().st_mode & 0o777) != (candidate.stat().st_mode & 0o777):
        errors.append("candidate_root_mode_differs_from_base")
    try:
        if tree_manifest(base) != tree_manifest(candidate):
            errors.append("candidate_is_not_an_unchanged_staging_clone")
    except ContractError as exc:
        errors.append(str(exc))
    if not errors:
        shared: list[str] = []
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(base)
            peer = candidate / relative
            try:
                left, right = path.stat(), peer.stat()
            except OSError:
                continue
            if left.st_dev == right.st_dev and left.st_ino == right.st_ino:
                shared.append(relative.as_posix())
                if len(shared) >= 5:
                    break
        if shared:
            errors.append("candidate_shares_file_identity_with_base:" + ",".join(shared))
    return errors


def gate_attestation_errors(command_name: str, stdout: str) -> list[str]:
    """Reject exit-zero, empty, zero-case, or static-summary gate output."""
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return ["output_not_json"]
    if not isinstance(payload, dict):
        return ["output_not_object"]
    errors: list[str] = []
    if payload.get("status") != "pass":
        errors.append("reported_status_not_pass")
    results = payload.get("results")
    if command_name == "validate_contracts.py":
        active = payload.get("metrics", {}).get("active_rules") if isinstance(payload.get("metrics"), dict) else None
        if not isinstance(active, int) or active <= 0:
            errors.append("active_rule_evidence_missing")
        if payload.get("errors") not in (None, []):
            errors.append("contract_errors_present")
    else:
        if not isinstance(results, list) or not results:
            errors.append("zero_results_is_not_evidence")
        elif any(not isinstance(item, dict) or item.get("status") != "pass" for item in results):
            errors.append("nonpassing_result_present")
    if command_name == "run_atomic_rule_evals.py":
        declared, executed = payload.get("declared"), payload.get("executed")
        mutation_executed, mutations = payload.get("mutation_executed"), payload.get("mutations")
        if not isinstance(declared, int) or declared <= 0 or executed != declared:
            errors.append("atomic_execution_incomplete")
        if not isinstance(mutation_executed, int) or mutation_executed != declared:
            errors.append("atomic_mutation_execution_incomplete")
        if not isinstance(mutations, list) or len(mutations) != declared or any(
            not isinstance(item, dict) or item.get("status") != "pass" for item in mutations
        ):
            errors.append("atomic_mutation_results_invalid")
    elif command_name.startswith("run_"):
        total = payload.get("total")
        if not isinstance(total, int) or total <= 0 or not isinstance(results, list) or len(results) != total:
            errors.append("case_execution_count_invalid")
    elif command_name == "validate_migration.py":
        metrics = payload.get("metrics")
        if not isinstance(metrics, dict) or not isinstance(metrics.get("v9_capabilities"), int) or metrics["v9_capabilities"] <= 0:
            errors.append("independent_v9_evidence_missing")
    return sorted(set(errors))


def run_gates(base: Path, root: Path, v9_root: Path | None) -> tuple[bool, list[dict[str, Any]]]:
    if v9_root is None:
        return False, [{
            "command": "validate_migration.py", "exit_code": 2, "stdout": "",
            "stderr": "an independent --v9-root is required for migration validation",
        }]
    commands = [
        [
            sys.executable, str(root / "scripts/quick_validate.py"),
            "--root", str(root), "--invocation-context", "skill-maintenance",
        ],
        [sys.executable, str(root / "scripts/validate_contracts.py"), "--root", str(root)],
        [sys.executable, str(root / "scripts/run_behavior_evals.py"), "--root", str(root)],
        [sys.executable, str(root / "scripts/run_atomic_rule_evals.py"), "--root", str(root), "--mutation-check"],
        [sys.executable, str(root / "scripts/run_scenario_tests.py"), "--root", str(root)],
        [sys.executable, str(root / "scripts/run_change_evals.py"), "--root", str(root), "--base-root", str(base)],
        [sys.executable, str(root / "scripts/run_maintenance_tests.py"), "--root", str(root)],
        [
            sys.executable, str(root / "scripts/validate_migration.py"), "--root", str(root),
            "--v9-root", str(v9_root),
        ],
    ]
    results = []
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["V11_SKILL_MAINTENANCE_PROCESS"] = "1"
    for command in commands:
        try:
            process = subprocess.run(
                command, text=True, capture_output=True, cwd=root, env=environment, timeout=120,
            )
            attestation_errors = gate_attestation_errors(Path(command[1]).name, process.stdout)
            effective_exit = process.returncode if process.returncode != 0 else (2 if attestation_errors else 0)
            results.append({
                "command": Path(command[1]).name, "exit_code": effective_exit,
                "stdout": process.stdout[-6000:],
                "stderr": (process.stderr[-1600:] + (
                    "\ngate_attestation_invalid:" + ",".join(attestation_errors)
                    if attestation_errors else ""
                ))[-2000:],
            })
        except subprocess.TimeoutExpired as exc:
            results.append({"command": Path(command[1]).name, "exit_code": 124, "stdout": "", "stderr": str(exc)})
    return all(item["exit_code"] == 0 for item in results), results


GateRunner = Callable[[Path, Path, Path | None], tuple[bool, list[dict[str, Any]]]]
MigrationRebuilder = Callable[[Path, Path], list[Path]]


def _restore_transaction(
    base: Path, root: Path, base_snapshot: TreeSnapshot, candidate_snapshot: TreeSnapshot,
) -> tuple[bool, list[str]]:
    """Restore both transaction trees and independently verify content, paths, and modes."""
    errors: list[str] = []
    try:
        restore_tree(root, candidate_snapshot)
    except Exception as exc:
        errors.append(f"candidate_restore_failed:{type(exc).__name__}:{exc}")
    try:
        try:
            base_changed = snapshot_digest(snapshot_tree(base)) != snapshot_digest(base_snapshot)
        except Exception:
            base_changed = True
        if base_changed:
            restore_tree(base, base_snapshot)
    except Exception as exc:
        errors.append(f"base_restore_failed:{type(exc).__name__}:{exc}")
    try:
        candidate_ok = snapshot_digest(snapshot_tree(root)) == snapshot_digest(candidate_snapshot)
    except Exception as exc:
        candidate_ok = False
        errors.append(f"candidate_verify_failed:{type(exc).__name__}:{exc}")
    try:
        base_ok = snapshot_digest(snapshot_tree(base)) == snapshot_digest(base_snapshot)
    except Exception as exc:
        base_ok = False
        errors.append(f"base_verify_failed:{type(exc).__name__}:{exc}")
    return candidate_ok and base_ok and not errors, errors


def execute_staged_change(
    change: dict[str, Any], base: Path, root: Path, v9_root: Path | None = None,
    gate_runner: GateRunner = run_gates,
    migration_rebuilder: MigrationRebuilder = rebuild_migration_evidence,
) -> tuple[dict[str, Any], int]:
    base, root = base.resolve(), root.resolve()
    isolation_errors = ensure_isolated_staging(base, root)
    if isolation_errors:
        return {"schema_version": "10.0", "status": "rejected", "errors": isolation_errors}, 2
    errors = validate_envelope(change, base)
    if errors:
        return {"schema_version": "10.0", "status": "rejected", "errors": errors}, 2
    isolation_errors = ensure_isolated_staging(base, root)
    if isolation_errors:
        return {
            "schema_version": "10.0", "status": "rejected",
            "errors": ["staging_changed_during_validation", *isolation_errors],
        }, 2
    before, after, _, changed_fields, _ = prospective_change(change, base)
    minimum, reasons = minimum_risk(change["operation"], before, after, changed_fields)
    if minimum == "L4":
        return {
            "schema_version": "10.0", "status": "requires_major_fork", "minimum_risk": minimum,
            "reasons": reasons, "base_root": str(base), "candidate_root": str(root),
            "next_step": "create a new-major candidate and run the major-version migration/release workflow",
        }, 3
    if v9_root is None:
        return {
            "schema_version": "10.0", "status": "rejected",
            "errors": ["v9_root_required_for_migration_gate"],
        }, 2
    resolved_v9 = v9_root.resolve()
    if not resolved_v9.is_dir() or resolved_v9 in {base, root}:
        return {
            "schema_version": "10.0", "status": "rejected",
            "errors": ["v9_root_must_be_an_independent_existing_directory"],
        }, 2

    snapshot = snapshot_tree(root)
    base_snapshot = snapshot_tree(base)
    base_manifest_before = tree_manifest(base)
    details: dict[str, Any] = {}
    try:
        permit = issue_impact_permit(change, root)
        touched, details = apply_change(change, root, permit, details)
        event_errors = validate_transaction_events(details.get("transaction_events"))
        if event_errors:
            raise ContractError(";".join(event_errors))
        touched = sorted(set(touched) | set(migration_rebuilder(root, resolved_v9)))
        candidate_before_gates = tree_manifest(root)
        passed, gates = gate_runner(base, root, resolved_v9)
        if passed and gate_runner is not run_gates:
            passed = False
            gates.append({
                "command": "gate_runner_identity", "exit_code": 2, "stdout": "",
                "stderr": "an injected gate runner cannot authorize validated_staging",
            })
        candidate_after_gates = tree_manifest(root)
        if candidate_after_gates != candidate_before_gates:
            passed = False
            gates.append({
                "command": "gate_purity", "exit_code": 2, "stdout": "",
                "stderr": "gates mutated candidate tree",
            })
        if tree_manifest(base) != base_manifest_before:
            passed = False
            gates.append({
                "command": "base_immutability", "exit_code": 2, "stdout": "",
                "stderr": "base tree changed",
            })
        if not passed:
            rollback_verified, rollback_errors = _restore_transaction(base, root, base_snapshot, snapshot)
            return {
                "schema_version": "10.0", "status": "rolled_back", "details": details,
                "rollback_verified": rollback_verified, "rollback_errors": rollback_errors, "gates": gates,
            }, 2
        return {
            "schema_version": "10.0", "status": "validated_staging", "details": details,
            "base_manifest_sha256": manifest_sha256(base_manifest_before),
            "candidate_manifest_sha256": manifest_sha256(candidate_after_gates),
            "touched": [path.relative_to(root).as_posix() for path in touched], "gates": gates,
            "promotion_performed": False,
        }, 0
    except MigrationReviewRequired as exc:
        rollback_verified, rollback_errors = _restore_transaction(base, root, base_snapshot, snapshot)
        return {
            "schema_version": "10.0", "status": "rolled_back",
            "errors": ["migration_semantic_review_required"],
            "details": details,
            "requires_manual_review": True,
            "review_queue": [{
                "kind": "migration_semantic_reseal", "rule_id": change.get("rule_id"),
                "minimum_risk": minimum,
                "required_evidence": [
                    "reviewed V9 capability impact", "versioned semantic decision",
                    "updated semantic binding seal", "base/candidate behavior oracles",
                ],
                "detail": exc.detail[-2000:],
            }],
            "rollback_verified": rollback_verified, "rollback_errors": rollback_errors,
        }, 2
    except Exception as exc:
        rollback_verified, rollback_errors = _restore_transaction(base, root, base_snapshot, snapshot)
        return {
            "schema_version": "10.0", "status": "rolled_back", "errors": [f"{type(exc).__name__}: {exc}"],
            "details": details,
            "rollback_verified": rollback_verified, "rollback_errors": rollback_errors,
        }, 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--change", type=Path, required=True)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--v9-root", type=Path, help="Independent V9 source root required for L0-L3 gates")
    parser.add_argument(
        "--prepare-impact", action="store_true",
        help="Read-only: calculate the exact impact proof to insert into the final envelope",
    )
    args = parser.parse_args()
    try:
        change = load_json(args.change.resolve())
    except Exception as exc:
        json_output({
            "schema_version": "10.0", "status": "rejected",
            "errors": [f"change_load_failed:{type(exc).__name__}:{exc}"],
        })
        return 2
    if args.prepare_impact:
        try:
            proof = build_impact_analysis(change, args.base_root.resolve())
        except Exception as exc:
            json_output({
                "schema_version": "10.0", "status": "rejected",
                "errors": [f"impact_analysis_failed:{type(exc).__name__}:{exc}"],
            })
            return 2
        json_output({
            "schema_version": "10.0", "status": "impact_analysis_passed",
            "impact_analysis": proof,
            "next_step": "insert this exact object as impact_analysis; then run the staged transaction",
        })
        return 0
    if args.candidate_root is None:
        json_output({
            "schema_version": "10.0", "status": "rejected",
            "errors": ["candidate_root_required_for_staged_change"],
        })
        return 2
    report, exit_code = execute_staged_change(change, args.base_root, args.candidate_root, args.v9_root)
    json_output(report)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
