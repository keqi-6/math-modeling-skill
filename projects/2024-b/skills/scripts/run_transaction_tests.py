#!/usr/bin/env python3
"""Legacy V10-only staged transaction compatibility probe.

This is not a V11 semantic-plan interpreter or release driver.
"""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from apply_rule_change import (
    build_impact_analysis,
    execute_staged_change,
    rule_behavior,
    rule_sha256,
    tree_manifest,
    validate_transaction_events,
)
from lib_v10 import SKILL_ROOT, load_rules


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


def base_change(root: Path, rule_id: str, patch: dict[str, Any], risk: str = "L0") -> dict[str, Any]:
    """Build the historical single-operation V10 envelope for this legacy probe."""
    current = rule(root, rule_id)
    updated = dict(current)
    updated.update(patch)
    updated["revision"] = current["revision"] + 1
    return {
        "operation": "modify", "rule_id": rule_id, "request": f"修改 {rule_id}",
        "old_behavior": rule_behavior(current), "new_behavior": rule_behavior(updated),
        "trigger": updated["trigger"], "exceptions": updated["exceptions"], "risk": risk,
        "impact_analysis": {}, "expected_owner": current["owner"],
        "expected_revision": current["revision"],
        "expected_rule_sha256": rule_sha256(current), "patch": patch,
        "behavior_tests": [],
    }


def seal_change(change: dict[str, Any], root: Path) -> dict[str, Any]:
    change["impact_analysis"] = build_impact_analysis(change, root)
    return change


def _component_fixture(state: str) -> dict[str, Any]:
    return {
        "project_state": "P0",
        "components": [{"id": "data-main", "type": "shared_data", "state": state}],
    }


def _selected_oracle(target: dict[str, Any], route_ids: list[str], **values: Any) -> dict[str, Any]:
    return {
        "status": "resolved", "mode": "mutate", "route_ids": route_ids,
        "target_selected": True, "target_effect": target["effect"],
        "selected_rule_ids": [target["id"]], **values,
    }


def data_change_tests(
    before: dict[str, Any], after: dict[str, Any], prefix: str,
) -> list[dict[str, Any]]:
    """Retain the old positive/negative/conflict/state probes only for V10."""
    positive_base = _selected_oracle(before, ["RT.DATA.TREAT"])
    positive_candidate = _selected_oracle(after, ["RT.DATA.TREAT"])
    if before.get("failure_example") != after.get("failure_example"):
        positive_base["target_failure"] = before["failure_example"]
        positive_candidate["target_failure"] = after["failure_example"]
    positive = {
        "id": prefix + ".POSITIVE", "kind": "positive",
        "target_rule_id": before["id"], "prompt": "清洗并预处理这个数据集",
        "component_id": "data-main", "fixture": _component_fixture("D1"),
        "expected": {"base": positive_base, "candidate": positive_candidate},
    }
    unselected = {
        "status": "resolved", "mode": "project_readonly",
        "route_ids": ["RT.DATA.AUDIT"], "target_selected": False,
        "excluded_rule_ids": [before["id"]],
    }
    near_negative = {
        "id": prefix + ".NEAR_NEGATIVE", "kind": "near_negative",
        "target_rule_id": before["id"], "prompt": "审计数据的结构、缺失和异常",
        "component_id": "data-main", "fixture": _component_fixture("D0"),
        "expected": {"base": dict(unselected), "candidate": dict(unselected)},
    }
    conflict_base = _selected_oracle(before, ["RT.DATA.TREAT"])
    conflict_candidate = _selected_oracle(after, ["RT.DATA.TREAT"])
    for oracle in (conflict_base, conflict_candidate):
        oracle["excluded_rule_ids"] = ["MNT.OWNER.CANONICAL"]
    conflict = {
        "id": prefix + ".CONFLICT", "kind": "conflict",
        "target_rule_id": before["id"], "prompt": "清洗并预处理这个数据集",
        "component_id": "data-main", "fixture": _component_fixture("D1"),
        "conflict_rule_ids": ["MNT.OWNER.CANONICAL"], "resolution": "disjoint",
        "expected": {"base": conflict_base, "candidate": conflict_candidate},
    }
    state_true = {
        "id": prefix + ".STATE_D1", "kind": "state_binding",
        "target_rule_id": before["id"], "prompt": "清洗并预处理这个数据集",
        "component_id": "data-main", "pair_id": prefix + ".STATE",
        "fixture": _component_fixture("D1"),
        "expected": {
            "base": _selected_oracle(before, ["RT.DATA.TREAT"]),
            "candidate": _selected_oracle(after, ["RT.DATA.TREAT"]),
        },
    }
    state_false = {
        "id": prefix + ".STATE_D3", "kind": "state_binding",
        "target_rule_id": before["id"], "prompt": "清洗并预处理这个数据集",
        "component_id": "data-main", "pair_id": prefix + ".STATE",
        "fixture": _component_fixture("D3"),
        "expected": {
            "base": {"status": "blocked", "mode": "mutate", "route_ids": [], "target_selected": False, "excluded_rule_ids": [before["id"]]},
            "candidate": {"status": "blocked", "mode": "mutate", "route_ids": [], "target_selected": False, "excluded_rule_ids": [before["id"]]},
        },
    }
    return [positive, near_negative, conflict, state_true, state_false]


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
