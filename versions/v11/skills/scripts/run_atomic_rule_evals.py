#!/usr/bin/env python3
"""Verify every inherited atom and prove deletion mutations are detected.

V11 behavior routing is tested with semantic-plan cases.  This driver has the
narrower job of ensuring that every frozen V10 atom still has one complete,
unchanged semantic envelope and one atomic oracle.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from build_atomic_rule_cases import envelope_sha256
from lib_v10 import SKILL_ROOT, load_json, load_rules


def evaluate_case(case: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    target = case.get("target_rule_id")
    rule = by_id.get(target) if isinstance(target, str) else None
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    if rule is None:
        failures.append("target_rule_missing")
    else:
        if rule.get("status") != "active":
            failures.append("target_not_active")
        if envelope_sha256(rule) != expected.get("semantic_envelope_sha256"):
            failures.append("semantic_envelope_hash_mismatch")
        for field in ("revision", "strength", "effect", "owner"):
            if rule.get(field) != expected.get(field):
                failures.append(f"expected_{field}_mismatch")
        enforcement = rule.get("enforcement", {})
        if enforcement.get("kind") != expected.get("enforcement_kind"):
            failures.append("enforcement_kind_mismatch")
        if enforcement.get("assurance") != expected.get("assurance"):
            failures.append("assurance_mismatch")
        if case.get("id") not in rule.get("tests", []):
            failures.append("rule_missing_atomic_test_backref")
    return {
        "id": case.get("id", "<missing>"),
        "target_rule_id": target,
        "status": "pass" if not failures else "fail",
        "failures": failures,
    }


def mutation_check(
    case: dict[str, Any], by_id: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Delete the target from a virtual corpus and require the real oracle to fail."""
    target = case.get("target_rule_id")
    mutated = dict(by_id)
    original_present = isinstance(target, str) and target in mutated
    if isinstance(target, str):
        mutated.pop(target, None)
    observed = evaluate_case(case, mutated)
    detected = original_present and observed["status"] == "fail" and "target_rule_missing" in observed["failures"]
    return {
        "id": case.get("id", "<missing>"),
        "mutation": "delete_target_atom",
        "status": "pass" if detected else "fail",
        "failures": [] if detected else ["deletion_mutation_not_detected"],
    }


def run(root: Path, selected: set[str] | None = None, check_mutations: bool = False) -> dict[str, Any]:
    payload = load_json(root / "evals/atomic-rule-cases.json")
    all_cases = payload.get("cases", []) if isinstance(payload, dict) else []
    cases = [
        case for case in all_cases
        if isinstance(case, dict) and (selected is None or case.get("id") in selected)
    ]
    rules, by_id = load_rules(root)
    active_ids = {rule["id"] for rule in rules if rule.get("status") == "active"}
    declaration_errors: list[str] = []
    if selected is None:
        targets = [case.get("target_rule_id") for case in all_cases if isinstance(case, dict)]
        if set(targets) != active_ids or len(targets) != len(set(targets)):
            declaration_errors.append("atomic_cases_not_bijective_with_active_rules")
        identifiers = [case.get("id") for case in all_cases if isinstance(case, dict)]
        if len(identifiers) != len(set(identifiers)):
            declaration_errors.append("duplicate_atomic_case_ids")
    results = [evaluate_case(case, by_id) for case in cases]
    mutations = [mutation_check(case, by_id) for case in cases] if check_mutations else []
    failures = declaration_errors + [
        item["id"] for item in results + mutations if item["status"] != "pass"
    ]
    return {
        "schema_version": "11.0",
        "status": "pass" if not failures else "fail",
        "driver": "atomic_rule_evals",
        "total": len(results),
        "declared": len(cases),
        "executed": len(results),
        "passed": sum(item["status"] == "pass" for item in results),
        "failed": sum(item["status"] != "pass" for item in results),
        "mutation_executed": len(mutations),
        "mutation_passed": sum(item["status"] == "pass" for item in mutations),
        "declaration_errors": declaration_errors,
        "results": results,
        "mutations": mutations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--mutation-check", action="store_true")
    args = parser.parse_args()
    report = run(
        args.root.resolve(), set(args.case) if args.case else None, args.mutation_check
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
