#!/usr/bin/env python3
"""Prove one real L0 transaction through the production migration and gate stack."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from apply_rule_change import (
    execute_staged_change,
    tree_manifest,
    validate_transaction_events,
)
from lib_v10 import SKILL_ROOT, load_rules
from run_maintenance_tests import base_change, data_change_tests, seal_change


CASE_ID = "MNT.TRANSACTION.L0.SUCCESS"
EXPECTED_GATE_COMMANDS = [
    "quick_validate.py",
    "validate_contracts.py",
    "run_behavior_evals.py",
    "run_atomic_rule_evals.py",
    "run_scenario_tests.py",
    "run_change_evals.py",
    "run_maintenance_tests.py",
    "validate_migration.py",
]


def rule(root: Path, rule_id: str) -> dict[str, Any]:
    _, by_id = load_rules(root)
    return by_id[rule_id]


def run_case(root: Path, v9_root: Path) -> dict[str, Any]:
    v9_before = tree_manifest(v9_root)
    with tempfile.TemporaryDirectory(prefix="v10-real-transaction-") as raw:
        workspace = Path(raw)
        base = workspace / "base"
        candidate = workspace / "candidate"
        shutil.copytree(root, base)
        shutil.copytree(root, candidate)
        base_before = tree_manifest(base)
        candidate_before = tree_manifest(candidate)

        current = rule(base, "DATA.TREAT.COPY")
        probe = "真实 L0 成功事务探针：不得原地覆盖已登记数据。"
        changed = copy.deepcopy(current)
        changed["failure_example"] = probe
        change = base_change(
            base, current["id"], {"failure_example": changed["failure_example"]}, "L0",
        )
        change["behavior_tests"] = data_change_tests(
            current, changed, "MNT.PROBE.TRANSACTION.SUCCESS",
        )
        seal_change(change, base)

        report, exit_code = execute_staged_change(change, base, candidate, v9_root)
        errors: list[str] = []
        if exit_code != 0 or report.get("status") != "validated_staging":
            errors.append(f"transaction_not_validated:exit={exit_code}:status={report.get('status')}")
        if report.get("promotion_performed") is not False:
            errors.append("transaction_performed_promotion")
        if validate_transaction_events(report.get("details", {}).get("transaction_events")):
            errors.append("transaction_event_attestation_invalid")
        if tree_manifest(base) != base_before:
            errors.append("base_mutated")
        candidate_after = tree_manifest(candidate)
        if candidate_after == candidate_before:
            errors.append("candidate_not_changed")
        gates = report.get("gates", [])
        commands = [item.get("command") for item in gates if isinstance(item, dict)]
        if commands != EXPECTED_GATE_COMMANDS:
            errors.append(f"gate_sequence_mismatch:{commands}")
        if any(not isinstance(item, dict) or item.get("exit_code") != 0 for item in gates):
            errors.append("nonpassing_real_gate")
        changed_rule = rule(candidate, current["id"])
        if changed_rule.get("revision") != current["revision"] + 1:
            errors.append("revision_not_incremented")
        if changed_rule.get("failure_example") != probe:
            errors.append("requested_l0_change_missing")
        touched = set(report.get("touched", []))
        required_touched = {
            "rules/data.json",
            "evals/change-cases.json",
            "evals/atomic-rule-cases.json",
            "references/migration/v9-capability-baseline.json",
            "references/migration/clause-preservation.json",
            "references/migration/capability-crosswalk.json",
            "references/migration/legacy-coverage.json",
        }
        missing_touched = sorted(required_touched - touched)
        if missing_touched:
            errors.append("derived_evidence_not_transaction_bound:" + ",".join(missing_touched))
        if tree_manifest(v9_root) != v9_before:
            errors.append("v9_source_mutated")
        return {
            "id": CASE_ID,
            "status": "pass" if not errors else "fail",
            "errors": errors,
            "gate_count": len(gates),
            "transaction_status": report.get("status"),
            "promotion_performed": report.get("promotion_performed"),
        }


def run(root: Path, v9_root: Path) -> dict[str, Any]:
    result = run_case(root, v9_root)
    passed = result["status"] == "pass"
    return {
        "schema_version": "10.0",
        "status": "pass" if passed else "fail",
        "driver": "real_staged_transaction",
        "total": 1,
        "passed": 1 if passed else 0,
        "failed": 0 if passed else 1,
        "metrics": {
            "successful_transactions": 1 if passed else 0,
            "production_gates_executed": result["gate_count"],
        },
        "results": [result],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--v9-root", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.root.resolve(), args.v9_root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
