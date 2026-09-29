#!/usr/bin/env python3
"""Bound the V11-to-V12 delta and verify the platform-loss repair is explicit."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    errors: list[str] = []
    record = load(root / "references/migration/platform-restoration.json")
    platform = load(root / "references/project-platform-contract.json")
    legacy = load(root / "references/migration/legacy-coverage.json")
    outcomes = load(root / "evals/platform-outcomes.json")

    for relative, expected in record.get("unchanged_v11_rule_sha256", {}).items():
        actual = digest(root / relative)
        if actual != expected:
            errors.append(f"unrelated_v11_rule_changed:{relative}:{actual}")

    project_rules = load(root / "rules/project.json").get("rules", [])
    lazy = next((item for item in project_rules if item.get("id") == "PRJ.STRUCTURE.LAZY"), {})
    if lazy.get("revision") != 2 or lazy.get("effect", {}).get("value") != "canonical_platform_admitted_artifact_parents_only":
        errors.append("declared_project_rule_change_missing")

    family = next(
        (item for item in legacy.get("legacy_family_dispositions", []) if item.get("v9_owner_family") == "references/modules/project-platform.md"),
        None,
    )
    if family is None:
        # V10 stores the list below migration_summary in some generated layouts.
        def walk(value: Any) -> list[dict[str, Any]]:
            found: list[dict[str, Any]] = []
            if isinstance(value, dict):
                if value.get("v9_owner_family") == "references/modules/project-platform.md":
                    found.append(value)
                for child in value.values():
                    found.extend(walk(child))
            elif isinstance(value, list):
                for child in value:
                    found.extend(walk(child))
            return found
        matches = walk(legacy)
        family = matches[0] if matches else None
    if not family or family.get("disposition") != "context_only" or family.get("v9_review_counts", {}).get("confirmed_capability", 0) < 1:
        errors.append("historical_platform_loss_evidence_missing")

    if platform.get("owner") != record.get("restored_owner") or len(platform.get("roles", {})) < 10:
        errors.append("restored_platform_owner_incomplete")
    declared = {item.get("id") for item in outcomes.get("cases", [])}
    if not set(record.get("required_outcomes", [])).issubset(declared):
        errors.append("migration_outcome_set_drift")

    result = {
        "schema_version": "12.0",
        "driver": "migration",
        "status": "pass" if not errors else "fail",
        "checks": ["MIGRATION.UNRELATED_RULES", "MIGRATION.DEFECT_EVIDENCE", "MIGRATION.RESTORED_OWNER", "MIGRATION.OUTCOMES"],
        "evidence": {
            "unchanged_rule_files": len(record.get("unchanged_v11_rule_sha256", {})),
            "restored_roles": len(platform.get("roles", {})),
            "required_outcomes": len(record.get("required_outcomes", [])),
        },
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
