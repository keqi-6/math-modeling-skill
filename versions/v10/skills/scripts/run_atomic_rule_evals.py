#!/usr/bin/env python3
"""Execute every atomic route oracle and optional deletion mutation checks."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from build_atomic_rule_cases import SEMANTIC_FIELDS, envelope_sha256
from lib_v10 import SKILL_ROOT, dump_json, json_output, load_json, load_rules
from run_behavior_evals import make_fixture


def resolve_case(root: Path, case: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    with tempfile.TemporaryDirectory(prefix="v10-atom-eval-") as directory:
        project_root = Path(directory)
        fixture = case.get("fixture")
        if fixture is not None:
            make_fixture(project_root, fixture)
        command = [sys.executable, str(root / "scripts/resolve_route.py"), "--request", case["prompt"]]
        if fixture is not None:
            command.extend(["--project-root", str(project_root)])
        if case.get("component_id"):
            command.extend(["--component-id", case["component_id"]])
        if case.get("component_map"):
            command.extend(["--component-map", json.dumps(case["component_map"], ensure_ascii=False, sort_keys=True)])
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.run(command, text=True, capture_output=True, cwd=root, env=environment)
        try:
            return json.loads(process.stdout), process.stderr
        except json.JSONDecodeError:
            return None, process.stderr or process.stdout


def evaluate_case(
    atom_case: dict[str, Any],
    behavior_case: dict[str, Any],
    observed: dict[str, Any] | None,
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    failures: list[str] = []
    target = atom_case["target_rule_id"]
    rule = by_id.get(target)
    if observed is None:
        failures.append("resolver_output_not_json")
    elif target not in observed.get("rule_ids", []):
        failures.append("target_not_selected")
    if rule is None or rule.get("status") != "active":
        failures.append("target_not_active")
    expected = atom_case.get("expected", {})
    if rule is not None:
        if envelope_sha256(rule) != expected.get("semantic_envelope_sha256"):
            failures.append("semantic_envelope_hash_mismatch")
        for field in ("revision", "strength", "effect", "owner"):
            if rule.get(field) != expected.get(field):
                failures.append(f"expected_{field}_mismatch")
        if rule.get("enforcement", {}).get("kind") != expected.get("enforcement_kind"):
            failures.append("enforcement_kind_mismatch")
        if rule.get("enforcement", {}).get("assurance") != expected.get("assurance"):
            failures.append("assurance_mismatch")
        if atom_case["id"] not in rule.get("tests", []):
            failures.append("rule_missing_atomic_test_backref")
    if observed is not None:
        selected = next((item for item in observed.get("rules", []) if item.get("id") == target), None)
        if selected is None:
            failures.append("semantic_envelope_not_delivered")
        elif set(selected) != set(SEMANTIC_FIELDS):
            failures.append("delivered_semantic_fields_not_closed")
        elif envelope_sha256(selected) != expected.get("semantic_envelope_sha256"):
            failures.append("delivered_semantic_envelope_mismatch")
        statuses = {
            item.get("status")
            for item in observed.get("applicability_evidence", {}).get(target, [])
        }
        if expected.get("applicability_status") not in statuses:
            failures.append("applicability_status_not_observed")
        if observed.get("status") != expected.get("source_status"):
            failures.append("source_status_changed")
        if observed.get("request") != behavior_case.get("prompt"):
            failures.append("source_request_not_preserved")
    return {
        "id": atom_case["id"], "target_rule_id": target,
        "status": "pass" if not failures else "fail", "failures": failures,
    }


def mutation_checks(root: Path, cases: list[dict[str, Any]], behavior_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    with tempfile.TemporaryDirectory(prefix="v10-atom-mutation-") as directory:
        staged = Path(directory) / "skills"
        shutil.copytree(root, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))
        _, staged_by_id = load_rules(staged)
        for atom_case in cases:
            target = atom_case["target_rule_id"]
            rule = staged_by_id[target]
            bundle_path = staged / rule["_bundle"]
            original = bundle_path.read_bytes()
            payload = load_json(bundle_path)
            payload["rules"] = [item for item in payload["rules"] if item["id"] != target]
            dump_json(bundle_path, payload)
            observed, detail = resolve_case(staged, behavior_by_id[atom_case["source_behavior_case_id"]])
            detected = observed is not None and target not in observed.get("rule_ids", [])
            results.append({
                "id": atom_case["id"], "mutation": "delete_target_atom",
                "status": "pass" if detected else "fail",
                "failures": [] if detected else ["deletion_mutation_not_detected", detail],
            })
            bundle_path.write_bytes(original)
    return results


def run(root: Path, selected: set[str] | None = None, check_mutations: bool = False) -> dict[str, Any]:
    atomic_payload = load_json(root / "evals/atomic-rule-cases.json")
    behavior_payload = load_json(root / "evals/behavior-cases.json")
    all_cases = atomic_payload.get("cases", [])
    cases = [case for case in all_cases if selected is None or case["id"] in selected]
    behavior_by_id = {case["id"]: case for case in behavior_payload.get("cases", []) if case.get("kind") == "route"}
    rules, by_id = load_rules(root)
    active_ids = {rule["id"] for rule in rules if rule["status"] == "active"}
    declaration_errors = []
    if selected is None:
        targets = [case.get("target_rule_id") for case in all_cases]
        if set(targets) != active_ids or len(targets) != len(set(targets)):
            declaration_errors.append("atomic_cases_not_bijective_with_active_rules")
    needed_sources = {case["source_behavior_case_id"] for case in cases}
    missing_sources = needed_sources - behavior_by_id.keys()
    if missing_sources:
        declaration_errors.append("missing_source_cases:" + ",".join(sorted(missing_sources)))
    observations = {
        source_id: resolve_case(root, behavior_by_id[source_id])[0]
        for source_id in sorted(needed_sources - missing_sources)
    }
    results = [
        evaluate_case(case, behavior_by_id[case["source_behavior_case_id"]], observations.get(case["source_behavior_case_id"]), by_id)
        for case in cases if case["source_behavior_case_id"] in behavior_by_id
    ]
    mutations = mutation_checks(root, cases, behavior_by_id) if check_mutations and not declaration_errors else []
    failures = declaration_errors + [
        item["id"] for item in results + mutations if item["status"] != "pass"
    ]
    return {
        "schema_version": "10.0", "status": "pass" if not failures else "fail",
        "driver": "atomic_rule_evals", "declared": len(cases), "executed": len(results),
        "passed": sum(item["status"] == "pass" for item in results),
        "mutation_executed": len(mutations), "mutation_passed": sum(item["status"] == "pass" for item in mutations),
        "declaration_errors": declaration_errors, "results": results, "mutations": mutations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--mutation-check", action="store_true")
    args = parser.parse_args()
    result = run(args.root.resolve(), set(args.case) if args.case else None, args.mutation_check)
    json_output(result)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
