#!/usr/bin/env python3
"""Execute typed, target-specific maintenance prompts against base and candidate roots."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from apply_rule_change import (
    CASE_KINDS, CASE_OPTIONAL, CASE_REQUIRED, RULE_ID_RE, _rules_conflict,
    rule_behavior, rule_failure, validate_fixture, validate_oracle,
)
from lib_v10 import SKILL_ROOT, json_output, load_json, load_rules
from run_behavior_evals import make_fixture


def case_shape_errors(case: Any, root: Path | None = None) -> list[str]:
    if not isinstance(case, dict):
        return ["case_not_object"]
    errors: list[str] = []
    missing = CASE_REQUIRED - case.keys()
    extra = set(case) - CASE_REQUIRED - CASE_OPTIONAL
    if missing:
        errors.append("missing_fields:" + ",".join(sorted(missing)))
    if extra:
        errors.append("unknown_fields:" + ",".join(sorted(extra)))
    if case.get("kind") not in CASE_KINDS:
        errors.append("kind_invalid")
    if not isinstance(case.get("target_rule_id"), str) or RULE_ID_RE.fullmatch(case["target_rule_id"]) is None:
        errors.append("target_rule_id_invalid")
    if not isinstance(case.get("prompt"), str) or len(case["prompt"].strip()) < 2:
        errors.append("prompt_invalid")
    if "fixture" in case:
        errors.extend(validate_fixture(case["fixture"], "case", root))
    expected = case.get("expected")
    if not isinstance(expected, dict) or set(expected) != {"base", "candidate"}:
        errors.append("expected_shape")
    else:
        errors.extend(validate_oracle(expected["base"], "base"))
        errors.extend(validate_oracle(expected["candidate"], "candidate"))
    if case.get("kind") == "conflict":
        conflicts = case.get("conflict_rule_ids")
        if (
            not isinstance(conflicts, list) or not conflicts or len(conflicts) != len(set(conflicts))
            or case.get("target_rule_id") in conflicts
            or any(not isinstance(item, str) or RULE_ID_RE.fullmatch(item) is None for item in conflicts)
        ):
            errors.append("conflict_rule_ids_required")
        if case.get("resolution") not in {"blocked", "target_wins", "target_loses", "disjoint"}:
            errors.append("resolution_invalid")
    if case.get("kind") == "state_binding":
        if not isinstance(case.get("pair_id"), str) or not case["pair_id"]:
            errors.append("pair_id_required")
        if not isinstance(case.get("fixture"), dict) or not isinstance(case.get("component_id"), str):
            errors.append("state_fixture_required")
    if case.get("kind") == "retirement" and not isinstance(case.get("replacement_rule_ids"), list):
        errors.append("replacement_rule_ids_required")
    return sorted(set(errors))


def _resolve(case: dict[str, Any], skill_root: Path) -> tuple[dict[str, Any] | None, int, str]:
    with tempfile.TemporaryDirectory(prefix="v10-change-eval-") as directory:
        project_root = Path(directory)
        fixture = case.get("fixture")
        if fixture is not None:
            make_fixture(project_root, fixture)
        command = [sys.executable, str(skill_root / "scripts/resolve_route.py"), "--request", case["prompt"]]
        if fixture is not None:
            command.extend(["--project-root", str(project_root)])
        if case.get("component_id"):
            command.extend(["--component-id", case["component_id"]])
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        try:
            process = subprocess.run(
                command, text=True, capture_output=True, cwd=skill_root, env=environment, timeout=30,
            )
        except subprocess.TimeoutExpired as exc:
            return None, 124, str(exc)
        try:
            return json.loads(process.stdout), process.returncode, process.stderr
        except json.JSONDecodeError:
            return None, process.returncode, process.stderr or process.stdout


def _compare_oracle(
    observed: dict[str, Any] | None,
    oracle: dict[str, Any],
    target_rule_id: str,
    label: str,
) -> list[str]:
    if observed is None:
        return [f"{label}:non_json_output"]
    failures: list[str] = []
    for field in ("status", "mode", "route_ids"):
        if field in oracle and observed.get(field) != oracle[field]:
            failures.append(f"{label}:{field}:{observed.get(field)!r}!={oracle[field]!r}")
    selected_ids = set(observed.get("rule_ids", []))
    selected = target_rule_id in selected_ids
    if selected != oracle["target_selected"]:
        failures.append(f"{label}:target_selected:{selected}!={oracle['target_selected']}")
    missing = set(oracle.get("selected_rule_ids", [])) - selected_ids
    unexpected = set(oracle.get("excluded_rule_ids", [])) & selected_ids
    if missing:
        failures.append(f"{label}:missing_selected:" + ",".join(sorted(missing)))
    if unexpected:
        failures.append(f"{label}:unexpected_selected:" + ",".join(sorted(unexpected)))

    if selected:
        target = next((rule for rule in observed.get("rules", []) if rule.get("id") == target_rule_id), None)
        if target is None:
            failures.append(f"{label}:selected_target_projection_missing")
        else:
            comparisons = {
                "target_strength": target.get("strength"),
                "target_effect": target.get("effect"),
                "target_behavior": rule_behavior(target),
                "target_failure": rule_failure(target),
                "target_evidence": target.get("evidence"),
                "target_outcomes": target.get("outcomes"),
                "target_enforcement": target.get("enforcement"),
                "target_scope": target.get("scope"),
                "target_trigger": target.get("trigger"),
                "target_exceptions": target.get("exceptions"),
                "target_conflicts_with": target.get("conflicts_with"),
                "target_refines": target.get("refines"),
                "target_depends_on": target.get("depends_on"),
            }
            for field, actual in comparisons.items():
                if field in oracle and actual != oracle[field]:
                    failures.append(f"{label}:{field}_mismatch")
    return failures


def evaluate(case: dict[str, Any], base_root: Path, candidate_root: Path) -> dict[str, Any]:
    shape = case_shape_errors(case, candidate_root)
    if shape:
        return {"id": case.get("id", "<missing>"), "kind": case.get("kind"), "status": "fail", "failures": shape}
    base, base_exit, base_stderr = _resolve(case, base_root)
    candidate, candidate_exit, candidate_stderr = _resolve(case, candidate_root)
    target = case["target_rule_id"]
    expected = case["expected"]
    failures = _compare_oracle(base, expected["base"], target, "base")
    failures.extend(_compare_oracle(candidate, expected["candidate"], target, "candidate"))

    _, base_rules = load_rules(base_root)
    _, candidate_rules = load_rules(candidate_root)
    for label, rules, oracle in (
        ("base", base_rules, expected["base"]),
        ("candidate", candidate_rules, expected["candidate"]),
    ):
        if oracle.get("target_selected") and "target_context_ref" in oracle:
            canonical = rules.get(target)
            actual = canonical.get("context_ref") if canonical is not None else None
            if actual != oracle["target_context_ref"]:
                failures.append(f"{label}:target_context_ref_mismatch")
        if oracle.get("target_selected") and "target_fields" in oracle:
            canonical = rules.get(target)
            for field, expected_value in oracle["target_fields"].items():
                actual = canonical.get(field) if canonical is not None else None
                if canonical is None or field not in canonical or actual != expected_value:
                    failures.append(f"{label}:target_fields_mismatch:{field}")

    for label, exit_code, oracle in (
        ("base", base_exit, expected["base"]), ("candidate", candidate_exit, expected["candidate"]),
    ):
        expected_exit = 0 if oracle["status"] == "resolved" else 2
        if exit_code != expected_exit:
            failures.append(f"{label}:exit_code:{exit_code}!={expected_exit}")

    candidate_ids = set(candidate.get("rule_ids", [])) if candidate else set()
    resolution = case.get("resolution")
    conflicts = set(case.get("conflict_rule_ids", []))
    if case["kind"] == "conflict":
        target_rule = candidate_rules.get(target) or base_rules.get(target)
        declared = {
            conflict for conflict in conflicts
            if _rules_conflict(
                target_rule,
                candidate_rules.get(conflict) or base_rules.get(conflict),
            )
        }
        missing_rules = {
            conflict for conflict in conflicts
            if conflict not in candidate_rules and conflict not in base_rules
        }
        if missing_rules:
            failures.append("conflict_rules_missing:" + ",".join(sorted(missing_rules)))
        if resolution == "disjoint" and declared:
            failures.append("disjoint_has_declared_conflict:" + ",".join(sorted(declared)))
        if resolution != "disjoint" and conflicts - declared:
            failures.append("undeclared_conflict:" + ",".join(sorted(conflicts - declared)))
        if resolution == "blocked" and candidate and candidate.get("status") not in {"blocked", "ambiguous"}:
            failures.append("candidate:conflict_not_blocked")
        elif resolution == "target_wins" and (target not in candidate_ids or conflicts & candidate_ids):
            failures.append("candidate:target_did_not_win")
        elif resolution == "target_loses" and (target in candidate_ids or not conflicts <= candidate_ids):
            failures.append("candidate:target_did_not_lose")
        elif resolution == "disjoint":
            candidate_target = candidate_rules.get(target)
            target_should_select = candidate_target is not None and candidate_target.get("status") == "active"
            if conflicts & candidate_ids or (target_should_select and target not in candidate_ids):
                failures.append("candidate:conflict_not_disjoint")
    if case["kind"] == "retirement":
        base_ids = set(base.get("rule_ids", [])) if base else set()
        replacements = set(case.get("replacement_rule_ids", []))
        if target not in base_ids or target in candidate_ids or not replacements <= candidate_ids:
            failures.append("retirement_differential_failed")

    return {
        "id": case["id"], "kind": case["kind"], "target_rule_id": target,
        "status": "pass" if not failures else "fail", "failures": failures,
        "observed": {
            "base": {
                "status": base.get("status") if base else None,
                "route_ids": base.get("route_ids") if base else None,
                "target_selected": target in set(base.get("rule_ids", [])) if base else False,
                "stderr": base_stderr[-300:] if base_stderr else "",
            },
            "candidate": {
                "status": candidate.get("status") if candidate else None,
                "route_ids": candidate.get("route_ids") if candidate else None,
                "target_selected": target in set(candidate.get("rule_ids", [])) if candidate else False,
                "stderr": candidate_stderr[-300:] if candidate_stderr else "",
            },
        },
    }


def _fixture_state(case: dict[str, Any]) -> str | None:
    fixture = case.get("fixture")
    component_id = case.get("component_id")
    if not isinstance(fixture, dict):
        return None
    for item in fixture.get("components", []):
        if isinstance(item, dict) and item.get("id") == component_id:
            return item.get("state")
    return None


def run(candidate_root: Path, base_root: Path | None = None) -> dict[str, Any]:
    base = (base_root or candidate_root).resolve()
    candidate = candidate_root.resolve()
    payload = load_json(candidate / "evals/change-cases.json")
    cases = payload.get("cases", [])
    if not isinstance(cases, list) or not cases:
        return {
            "schema_version": "10.0", "status": "fail", "driver": "typed_base_candidate_rule_oracles",
            "total": 0, "passed": 0, "failed": 1,
            "errors": ["zero_change_cases_is_not_evidence"], "results": [],
        }
    ids = [case.get("id") for case in cases if isinstance(case, dict)]
    preflight_errors: list[str] = []
    if len(ids) != len(cases) or len(ids) != len(set(ids)):
        preflight_errors.append("change_case_ids_invalid")
    pairs: dict[str, list[dict[str, Any]]] = {}
    for case in cases:
        if isinstance(case, dict) and case.get("kind") == "state_binding" and isinstance(case.get("pair_id"), str):
            pairs.setdefault(case["pair_id"], []).append(case)
    for pair_id, pair in pairs.items():
        states = {_fixture_state(case) for case in pair}
        selections = {case.get("expected", {}).get("candidate", {}).get("target_selected") for case in pair}
        prompts = {case.get("prompt") for case in pair}
        targets = {case.get("target_rule_id") for case in pair}
        components = {case.get("component_id") for case in pair}
        if (
            len(pair) != 2 or len(states) != 2 or selections != {True, False}
            or len(prompts) != 1 or len(targets) != 1 or len(components) != 1
        ):
            preflight_errors.append(f"state_binding_pair_invalid:{pair_id}")
    results = [evaluate(case, base, candidate) for case in cases if isinstance(case, dict)]
    failures = [item for item in results if item["status"] != "pass"]
    failed_count = len(failures) + len(preflight_errors)
    return {
        "schema_version": "10.0", "status": "pass" if failed_count == 0 else "fail",
        "driver": "typed_base_candidate_rule_oracles", "total": len(results),
        "passed": len(results) - len(failures), "failed": failed_count,
        "errors": preflight_errors, "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT, help="Candidate Skill root")
    parser.add_argument("--base-root", type=Path, help="Immutable base Skill root; defaults to candidate for baseline cases")
    args = parser.parse_args()
    result = run(args.root.resolve(), args.base_root.resolve() if args.base_root else None)
    json_output(result)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
