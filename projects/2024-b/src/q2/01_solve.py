"""问题二S5正式求解入口。

输入：planning/analysis/2026-08-23_q2_s2_assessment.md 中冻结的表1接口；
      planning/analysis/2026-08-23_q2_s4_specification.md 中已批准数学合同。
输出：output/q2/s5_results.json；output/q2/s5_run_manifest.json。
职责：解析六个情景，完整生成96个情景—方案组合，执行硬门和精确求解并冻结运行身份。
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from core import COUNT_NAMES, Scenario, all_policies, preparation_kernel, solve_policy, transition_rows


PROJECT_ROOT = Path(__file__).resolve().parents[2]
S2_INTERFACE = PROJECT_ROOT / "planning/analysis/2026-08-23_q2_s2_assessment.md"
S4_SPEC = PROJECT_ROOT / "planning/analysis/2026-08-23_q2_s4_specification.md"
CORE_PATH = PROJECT_ROOT / "src/q2/core.py"
SCRIPT_PATH = PROJECT_ROOT / "src/q2/01_solve.py"
OUTPUT_PATH = PROJECT_ROOT / "output/q2/s5_results.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q2/s5_run_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def number(value: Fraction) -> dict[str, object]:
    return {"fraction": fraction_text(value), "decimal": float(value)}


def parse_scenarios(path: Path) -> list[Scenario]:
    """只解析S2权威表格的6个数据行，避免另建手抄参数副本。"""
    rows = []
    row_pattern = re.compile(r"^\|\s*([1-6])\s*\|(.+)\|\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = row_pattern.match(line)
        if not match:
            continue
        values = [part.strip() for part in match.group(2).split("|")]
        if len(values) != 12:
            continue
        parsed = [Fraction(value) for value in values]
        rows.append(Scenario(int(match.group(1)), *parsed))
    if [row.scenario_id for row in rows] != list(range(1, 7)):
        raise ValueError("S2表1接口未解析出唯一且有序的六个情景")
    return rows


def policy_json(policy) -> dict[str, object]:
    return {
        "policy_id": policy.policy_id,
        "bits": list(policy.bits),
        "inspect_part1": bool(policy.inspect_part1),
        "inspect_part2": bool(policy.inspect_part2),
        "inspect_product": bool(policy.inspect_product),
        "disassemble_bad_product": bool(policy.disassemble_bad_product),
    }


def scenario_input_json(scenario: Scenario) -> dict[str, object]:
    return {
        field: number(getattr(scenario, field))
        for field in Scenario.__dataclass_fields__
        if field != "scenario_id"
    }


def candidate_json(result: dict[str, object]) -> dict[str, object]:
    payload = {
        "policy": policy_json(result["policy"]),
        "feasible": result["feasible"],
        "feasibility_reason": result["feasibility_reason"],
        "absorption_probability": number(result["absorption_probability"]),
        "profit_identity": result["profit_identity"],
    }
    if not result["feasible"]:
        payload.update(
            {
                "reachable_states": None,
                "expected_counts": None,
                "probability_order_has_market_bad_product": None,
                "expected_cost": None,
                "expected_profit": None,
            }
        )
        return payload
    payload.update(
        {
            "reachable_states": [list(state) for state in result["reachable_states"]],
            "expected_counts": {
                name: number(value) for name, value in result["expected_counts"].items()
            },
            "probability_order_has_market_bad_product": number(
                result["probability_order_has_market_bad_product"]
            ),
            "expected_cost": number(result["expected_cost"]),
            "expected_profit": number(result["expected_profit"]),
        }
    )
    return payload


def run_acceptance_checks(scenarios: list[Scenario], solved: list[dict[str, object]]) -> dict[str, object]:
    checks = []

    def record(check_id: str, condition: bool, evidence: str) -> None:
        if not condition:
            raise AssertionError(f"{check_id}失败: {evidence}")
        checks.append({"id": check_id, "passed": True, "evidence": evidence})

    policies = all_policies()
    record("candidate_domain", len(policies) == 16 and len({p.bits for p in policies}) == 16, "16个唯一四元组合")

    for scenario, scenario_result in zip(scenarios, solved):
        candidates = scenario_result["raw_candidates"]
        feasible = [item for item in candidates if item["feasible"]]
        record(f"scenario_{scenario.scenario_id}_gate", len(candidates) == 16 and len(feasible) == 10, "16个候选中10可行6不可行")

    # 对九种槽位、全部方案检查准备核和产品分支概率守恒。
    qualities = ("E", "G", "B")
    probability_checks = 0
    for scenario in scenarios:
        for policy in policies:
            for state1 in qualities:
                for state2 in qualities:
                    state = (state1, state2)
                    prep_sum = sum(row[1] for row in preparation_kernel(state, policy, scenario))
                    transition_sum = sum(row[0] for row in transition_rows(state, policy, scenario))
                    record(
                        f"probability_{scenario.scenario_id}_{policy.policy_id}_{state1}{state2}",
                        prep_sum == 1 and transition_sum == 1,
                        "准备核与一轮分支概率均精确和为1",
                    )
                    probability_checks += 1

    # 冻结表中的显示小数只用于回归显示，精确公式由状态求解产生。
    baseline_display = [15.360768, -4.406250, 6.438957, -27.281250, 7.358025, 21.678670]
    for scenario_result, target in zip(solved, baseline_display):
        baseline = next(item for item in scenario_result["raw_candidates"] if item["policy"].policy_id == "0000")
        record(
            f"baseline_{scenario_result['scenario_id']}",
            abs(float(baseline["expected_profit"]) - target) < 6e-7,
            f"(0,0,0,0)利润显示值复现S2: {float(baseline['expected_profit']):.9f}",
        )

    walkthrough = next(item for item in solved[0]["raw_candidates"] if item["policy"].policy_id == "1101")
    record("walkthrough_cost", walkthrough["expected_cost"] == Fraction(346, 9), "情景1的1101成本为346/9")
    record("walkthrough_profit", walkthrough["expected_profit"] == Fraction(158, 9), "情景1的1101利润为158/9")

    for scenario_result in solved:
        for policy_id in ("1001", "0101"):
            item = next(candidate for candidate in scenario_result["raw_candidates"] if candidate["policy"].policy_id == policy_id)
            record(f"persistent_{scenario_result['scenario_id']}_{policy_id}", not item["feasible"] and item["profit_identity"] == "not_defined_due_to_nontermination", "持久坏件方案不可比较")

    return {
        "passed": True,
        "check_count": len(checks),
        "probability_state_checks": probability_checks,
        "dual_representation_policy_checks": len(scenarios) * 10,
        "checks": checks,
    }


def main() -> None:
    started = datetime.now(timezone.utc)
    scenarios = parse_scenarios(S2_INTERFACE)
    policies = all_policies()
    solved_internal = []
    scenario_outputs = []

    for scenario in scenarios:
        candidates = [solve_policy(policy, scenario) for policy in policies]
        feasible = [item for item in candidates if item["feasible"]]
        best_profit = max(item["expected_profit"] for item in feasible)
        best = [item for item in feasible if item["expected_profit"] == best_profit]
        solved_internal.append({"scenario_id": scenario.scenario_id, "raw_candidates": candidates})
        scenario_outputs.append(
            {
                "scenario_id": scenario.scenario_id,
                "input": scenario_input_json(scenario),
                "candidate_count": len(candidates),
                "feasible_count": len(feasible),
                "infeasible_count": len(candidates) - len(feasible),
                "best_policy_ids": [item["policy"].policy_id for item in best],
                "best_is_tied": len(best) > 1,
                "best_expected_profit": number(best_profit),
                "best_solutions": [
                    {
                        "policy": policy_json(item["policy"]),
                        "expected_cost": number(item["expected_cost"]),
                        "expected_profit": number(item["expected_profit"]),
                        "expected_counts": {
                            name: number(value)
                            for name, value in item["expected_counts"].items()
                        },
                        "probability_order_has_market_bad_product": number(
                            item["probability_order_has_market_bad_product"]
                        ),
                    }
                    for item in best
                ],
                "candidates": [candidate_json(item) for item in candidates],
            }
        )

    acceptance = run_acceptance_checks(scenarios, solved_internal)
    payload = {
        "schema_version": "1.0",
        "artifact_status": "s5_frozen_unverified",
        "producer": "src/q2/01_solve.py",
        "specification": "planning/analysis/2026-08-23_q2_s4_specification.md",
        "decision_identity": "Q2-S4-SPEC-01 approved by user on 2026-08-23",
        "candidate_domain": "all 16 fixed four-bit policies per scenario",
        "selection_rule": "hard feasibility gate, then exact maximum expected profit per completed order",
        "count_order": list(COUNT_NAMES),
        "scenario_count": len(scenarios),
        "candidate_record_count": len(scenarios) * len(policies),
        "same_implementation_acceptance": acceptance,
        "scenarios": scenario_outputs,
        "verification_boundary": "not independently verified; S6 not started",
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    finished = datetime.now(timezone.utc)
    manifest = {
        "schema_version": "1.0",
        "run_status": "complete",
        "artifact_status": "s5_frozen_unverified",
        "producer": "src/q2/01_solve.py",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "randomness": "none",
        "solver": "exact Fraction Gaussian elimination plus closed-form regression",
        "inputs": {
            str(S2_INTERFACE.relative_to(PROJECT_ROOT)): sha256(S2_INTERFACE),
            str(S4_SPEC.relative_to(PROJECT_ROOT)): sha256(S4_SPEC),
        },
        "code": {
            str(CORE_PATH.relative_to(PROJECT_ROOT)): sha256(CORE_PATH),
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
        },
        "outputs": {str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH)},
        "dimensions": {
            "scenarios": len(scenarios),
            "policies_per_scenario": len(policies),
            "candidate_records": len(scenarios) * len(policies),
            "feasible_per_scenario": 10,
            "infeasible_per_scenario": 6,
        },
        "consumers": [
            "planning/analysis/2026-08-23_q2_s5_implementation.md",
            "future independent S6 verifier",
            "future docs/q2/solution_brief.md after S6 authorization",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "best_policy_ids": [row["best_policy_ids"] for row in scenario_outputs], "acceptance_checks": acceptance["check_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
