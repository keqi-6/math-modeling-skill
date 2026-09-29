#!/usr/bin/env python3
"""Check the few cross-file contracts that can break V12 runtime behavior."""

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
    routes = load(root / "references/route-contract.json")
    release_policy = load(root / "references/release-policy.json")
    release_plan = load(root / "evals/release/release-plan.json")
    outcomes = load(root / "evals/platform-outcomes.json")

    platform_owner = ownership.get("classes", {}).get("project_platform_contract", {})
    if platform_owner.get("owner") != "references/project-platform-contract.json":
        errors.append("platform_owner_missing")

    roles = platform.get("roles", {})
    artifact_roles = set(artifact.get("properties", {}).get("platform_role", {}).get("enum", []))
    state_roles = set(
        state_schema.get("$defs", {}).get("artifact", {}).get("properties", {})
        .get("role", {}).get("enum", [])
    )
    if set(roles) != artifact_roles:
        errors.append("artifact_platform_role_enum_drift")
    if not set(roles).issubset(state_roles):
        errors.append("state_platform_role_enum_incomplete")
    artifact_classes = set(artifact.get("properties", {}).get("class", {}).get("enum", []))
    for role, contract in roles.items():
        if not set(contract.get("classes", [])).issubset(artifact_classes):
            errors.append(f"platform_class_unknown:{role}")
        for pattern in contract.get("path_patterns", []):
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"platform_path_regex_invalid:{role}:{exc}")

    init_route = next((item for item in routes.get("routes", []) if item.get("id") == "RT.PROJECT.INIT"), {})
    init_refs = {item.get("ref") for item in init_route.get("context_refs", [])}
    if "canonical_logical_platform_binding" not in init_route.get("expected_outputs", []):
        errors.append("init_route_platform_output_missing")
    if "references/project-platform-contract.json" not in init_refs:
        errors.append("init_route_platform_contract_missing")

    rules = [rule for path in (root / "rules").glob("*.json") for rule in load(path).get("rules", [])]
    lazy = next((rule for rule in rules if rule.get("id") == "PRJ.STRUCTURE.LAZY"), {})
    if lazy.get("effect", {}).get("value") != "canonical_platform_admitted_artifact_parents_only":
        errors.append("lazy_rule_not_bound_to_platform")
    required_outcomes = set(lazy.get("tests", []))
    declared_outcomes = {item.get("id") for item in outcomes.get("cases", [])}
    if not required_outcomes.issubset(declared_outcomes):
        errors.append("lazy_rule_outcome_missing")

    policy_drivers = [item.get("id") for item in release_policy.get("active_drivers", [])]
    plan_drivers = release_plan.get("required_drivers", [])
    if policy_drivers != plan_drivers or policy_drivers != ["package", "contracts", "outcomes", "migration"]:
        errors.append("release_driver_contract_drift")

    result = {
        "schema_version": "12.0",
        "driver": "contracts",
        "status": "pass" if not errors else "fail",
        "checks": [
            "CONTRACT.OWNERSHIP", "CONTRACT.PLATFORM_MAP", "CONTRACT.INIT_ROUTE",
            "CONTRACT.LAZY_RULE", "CONTRACT.RELEASE_DRIVERS"
        ],
        "evidence": {"platform_roles": len(roles), "active_rules": len(rules)},
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
