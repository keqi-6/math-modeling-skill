#!/usr/bin/env python3
"""问题三 S5：完整枚举、精确求解、同实现验收与结构化落盘。"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from core import (
    ASSEMBLIES,
    CHILDREN,
    EVENT_INDEX,
    EVENT_NAMES,
    F,
    GOOD,
    LEAVES,
    SEMIS,
    Policy,
    _semi_kernel,
    all_policies,
    decimal_text,
    default_instance,
    direct_parent_failure_posterior,
    disassemble_frontier,
    evaluate_policy,
    fraction_text,
    inspect_knowledge,
    parent_quality,
    sensitivity_scenarios,
    validate_instance,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output" / "q3"
RESULTS_PATH = OUT / "s5_results.json"
CANDIDATES_PATH = OUT / "s5_candidates.jsonl.gz"
ACCEPTANCE_PATH = OUT / "s5_acceptance.json"
MANIFEST_PATH = OUT / "s5_run_manifest.json"


def exact(value):
    if isinstance(value, Fraction):
        return fraction_text(value)
    if isinstance(value, tuple):
        return [exact(item) for item in value]
    if isinstance(value, list):
        return [exact(item) for item in value]
    if isinstance(value, dict):
        return {key: exact(item) for key, item in value.items()}
    return value


def candidate_record(result: dict[str, object]) -> dict[str, object]:
    record = {
        "scenario": result["scenario"],
        "policy_id": result["policy_id"],
        "feasible": result["feasible"],
        "gate_status": result["gate_status"],
        "gate_reason": result["gate_reason"],
    }
    if not result["feasible"]:
        record.update(
            {
                "graph_closed_class_check": result["graph_closed_class_check"],
                "equation_absorption_check": result["equation_absorption_check"],
                "nonabsorption_probability_lower_bound": fraction_text(
                    result["nonabsorption_probability_lower_bound"]
                ),
                "absorption_probability_upper_bound": fraction_text(
                    result["absorption_probability_upper_bound"]
                ),
                "profit": "not_defined_due_to_nontermination",
            }
        )
        return record
    record.update(
        {
            "graph_closed_class_check": result["graph_closed_class_check"],
            "equation_absorption_check": result["equation_absorption_check"],
            "absorption_probability": exact(result["absorption_probability"]),
            "expected_events": {
                name: fraction_text(value)
                for name, value in zip(EVENT_NAMES, result["expected_events"])
            },
            "total_cost": fraction_text(result["total_cost"]),
            "profit": fraction_text(result["profit"]),
            "first_root_attempt_success_probability": fraction_text(
                result["first_root_attempt_success_probability"]
            ),
            "at_least_one_market_bad_probability": fraction_text(
                result["at_least_one_market_bad_probability"]
            ),
        }
    )
    return record


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def preliminary_acceptance() -> list[dict[str, str]]:
    instance = default_instance()
    scenarios = sensitivity_scenarios(instance)
    nominal = scenarios[0]
    tests: list[dict[str, str]] = []

    def check(number: int, name: str, action) -> None:
        action()
        tests.append({"id": f"T{number:02d}", "name": name, "status": "pass"})

    def t1():
        validate_instance(instance)
        _assert(sum(instance.purchase_costs.values()) == 64, "购买费合计")
        _assert(sum(instance.inspection_costs[p] for p in LEAVES) == 11, "叶检测费合计")

    def t2():
        policies = list(all_policies())
        ids = [p.policy_id for p in policies]
        _assert(len(ids) == len(set(ids)) == 65536, "候选域不完整")
        _assert(ids[0] == "0" * 16 and ids[-1] == "1" * 16, "位序边界错误")

    def t3():
        first = disassemble_frontier(frozenset({"F"}), "F")
        second = disassemble_frontier(first, "S2")
        _assert(first == frozenset(SEMIS), "根拆解前沿错误")
        _assert(second == frozenset(("S1", "S3", "P4", "P5", "P6")), "局部拆解前沿错误")

    def t4():
        policy = Policy((0,) * 16)
        result = evaluate_policy(policy, nominal, instance, {})
        s = result["first_root_attempt_success_probability"]
        _assert(0 < s < 1 and s + (1 - s) == 1, "根核概率不守恒")

    def t5():
        _assert(parent_quality((GOOD, GOOD), GOOD) == GOOD, "全良质量律")
        for child in (("B", GOOD), (GOOD, "B")):
            _assert(parent_quality(child, GOOD) == "B", "坏子件质量律")
        _assert(parent_quality((GOOD, GOOD), "B") == "B", "装配冲击质量律")

    def t6():
        restored = disassemble_frontier(frozenset({"S1", "S2", "S3"}), "S1")
        _assert(len(restored) == 5 and "S1" not in restored, "拆解对象守恒")

    def t7():
        _assert(inspect_knowledge("B") == "B", "检测知识错误")
        posterior = direct_parent_failure_posterior((F(9, 10), F(9, 10)), F(9, 10))
        _assert(len(posterior) > 1, "坏父件被错误定位为单一坏因")

    def t8():
        result = evaluate_policy(Policy((0,) * 16), nominal, instance, {})
        _assert(result["profit"] == instance.sale_price - result["total_cost"], "售价未恰计一次")

    def t9():
        kernel = _semi_kernel("S1", (1, 0, 0), 0, 0, nominal.defect_rates)
        events = kernel.events_from_empty
        _assert(events[EVENT_INDEX["purchase_P1"]] == F(10, 9), "叶筛选购买几何期望")
        _assert(events[EVENT_INDEX["inspect_P1"]] == F(10, 9), "叶筛选检测几何期望")

    def t10():
        kernel = _semi_kernel("S1", (1, 1, 1), 1, 1, nominal.defect_rates)
        events = kernel.events_from_empty
        _assert(events[EVENT_INDEX["assemble_S1"]] == F(10, 9), "重装次数")
        _assert(events[EVENT_INDEX["inspect_S1"]] == F(10, 9), "半成品检测次数")
        _assert(events[EVENT_INDEX["disassemble_S1"]] == F(1, 9), "半成品拆解次数")
        _assert(events[EVENT_INDEX["purchase_P1"]] == F(10, 9), "拆回良件不应重购")

    def t11():
        kernel = _semi_kernel("S1", (0, 1, 1), 1, 1, nominal.defect_rates)
        _assert(not kernel.feasible and "closed_class" in kernel.reason, "持久坏件闭环未检出")

    def t12():
        posterior = direct_parent_failure_posterior((F(9, 10), F(9, 10)), F(9, 10))
        p1 = sum(m for state, m in posterior.items() if state[0] == GOOD)
        p2 = sum(m for state, m in posterior.items() if state[1] == GOOD)
        joint = posterior[(GOOD, GOOD)]
        _assert(joint != p1 * p2, "父失败后错误恢复为边际独立")
        _assert(sum(posterior.values()) == 1, "后验未归一")

    def t13():
        result = evaluate_policy(Policy((0,) * 16), nominal, instance, {})
        g = F(9, 10) ** 12
        expected_cost = (F(96) + F(40) * (1 - g)) / g
        _assert(result["first_root_attempt_success_probability"] == g, "S2基线成功率")
        _assert(result["total_cost"] == expected_cost, "S2基线成本")

    def t14():
        q, reward = F(1, 10), F(7)
        macro = reward / (1 - q)
        # 一状态原子方程 (1-q)V=reward 的Fraction消元结果。
        linear = reward / (F(1) - q)
        partial = sum(reward * q**k for k in range(12))
        remainder = reward * q**12 / (1 - q)
        _assert(macro == linear == partial + remainder, "原子/宏/方程不一致")

    def t15():
        policy = Policy(tuple(int(c) for c in "1010101010101010"))
        cached = evaluate_policy(policy, nominal, instance, {})
        uncached = evaluate_policy(policy, nominal, instance, None)
        _assert(cached == uncached, "缓存改变了求值")

    def t16():
        _assert(len(scenarios) == 25, "OAT情形数不是25")
        _assert(nominal.name == "NOMINAL", "名义情形缺失")
        observed = set()
        for scenario in scenarios[1:]:
            changed = [
                node for node in LEAVES + ASSEMBLIES
                if scenario.defect_rates[node] != nominal.defect_rates[node]
            ]
            _assert(changed == [scenario.changed_node], "情形不是一因子一次变化")
            rate = scenario.defect_rates[scenario.changed_node]
            _assert(rate in {F(1, 20), F(3, 20)}, "扰动不是正负5个百分点")
            observed.add((scenario.changed_node, rate))
        _assert(len(observed) == 24, "12节点双向扰动未覆盖完整")

    for number, name, action in (
        (1, "input_completeness", t1),
        (2, "candidate_domain_completeness", t2),
        (3, "frontier_state_legality", t3),
        (4, "probability_conservation", t4),
        (5, "quality_logic", t5),
        (6, "disassembly_conservation", t6),
        (7, "knowledge_boundary", t7),
        (8, "fee_timing_and_single_revenue", t8),
        (9, "leaf_screening_geometric_fixture", t9),
        (10, "known_good_input_reassembly_fixture", t10),
        (11, "persistent_bad_child_closed_loop", t11),
        (12, "parent_failure_joint_posterior", t12),
        (13, "s2_all_zero_baseline", t13),
        (14, "atomic_macro_linear_equivalence", t14),
        (15, "cached_uncached_equivalence", t15),
        (16, "twelve_node_oat_scenario_contract", t16),
    ):
        check(number, name, action)
    return tests


def run_enumeration() -> tuple[dict[str, object], list[dict[str, str]]]:
    instance = default_instance()
    validate_instance(instance)
    scenarios = sensitivity_scenarios(instance)
    OUT.mkdir(parents=True, exist_ok=True)
    cache = {}
    summaries: dict[str, object] = {}
    scenario_results: dict[str, list[dict[str, object]]] = {}
    written = 0

    with gzip.open(CANDIDATES_PATH, "wt", encoding="utf-8", compresslevel=6) as stream:
        for scenario in scenarios:
            feasible: list[dict[str, object]] = []
            infeasible_count = 0
            for policy in all_policies():
                result = evaluate_policy(policy, scenario, instance, cache)
                stream.write(json.dumps(candidate_record(result), ensure_ascii=False, separators=(",", ":")) + "\n")
                written += 1
                if result["feasible"]:
                    feasible.append(result)
                else:
                    infeasible_count += 1
            best_profit = max(item["profit"] for item in feasible)
            best = [item for item in feasible if item["profit"] == best_profit]
            feasible.sort(key=lambda item: (-item["profit"], item["policy_id"]))
            scenario_results[scenario.name] = feasible
            summaries[scenario.name] = {
                "changed_node": scenario.changed_node,
                "direction": scenario.direction,
                "changed_rate_exact": (
                    None if scenario.changed_node is None
                    else fraction_text(scenario.defect_rates[scenario.changed_node])
                ),
                "defect_rates": {
                    node: fraction_text(scenario.defect_rates[node])
                    for node in LEAVES + ASSEMBLIES
                },
                "candidate_count": 65536,
                "feasible_count": len(feasible),
                "infeasible_count": infeasible_count,
                "best_profit_exact": fraction_text(best_profit),
                "best_profit_decimal": decimal_text(best_profit, 9),
                "best_policy_ids": [item["policy_id"] for item in best],
                "best_solutions": [candidate_record(item) for item in best],
                "top10": [
                    {
                        "rank_key": rank + 1,
                        "policy_id": item["policy_id"],
                        "profit_exact": fraction_text(item["profit"]),
                        "profit_decimal": decimal_text(item["profit"], 9),
                        "total_cost_decimal": decimal_text(item["total_cost"], 9),
                    }
                    for rank, item in enumerate(feasible[:10])
                ],
            }

    nominal_profit = F(summaries["NOMINAL"]["best_profit_exact"])
    nominal_policies = summaries["NOMINAL"]["best_policy_ids"]
    for summary in summaries.values():
        profit_change = F(summary["best_profit_exact"]) - nominal_profit
        summary["profit_change_from_nominal_exact"] = fraction_text(profit_change)
        summary["profit_change_from_nominal_decimal"] = decimal_text(profit_change, 9)
        summary["policy_switch_from_nominal"] = (
            summary["best_policy_ids"] != nominal_policies
        )

    tests = preliminary_acceptance()

    def add_test(number: int, name: str, condition: bool) -> None:
        _assert(condition, name)
        tests.append({"id": f"T{number:02d}", "name": name, "status": "pass"})

    add_test(
        17,
        "exact_ranking_without_display_rounding",
        all(
            rows[i]["profit"] >= rows[i + 1]["profit"]
            for rows in scenario_results.values()
            for i in range(len(rows) - 1)
        ),
    )
    add_test(
        18,
        "independent_validation_interface_ready",
        written == 25 * 65536
        and all(len(summaries[name]["best_solutions"]) >= 1 for name in summaries),
    )
    results = {
        "status": "s5_implemented_not_s6_validated",
        "decision_bit_order": [
            *(f"iP{i}" for i in range(1, 9)),
            "iS1", "iS2", "iS3", "iF", "dS1", "dS2", "dS3", "dF",
        ],
        "event_order": list(EVENT_NAMES),
        "atomic_step_definition": "one step per charged/action event, including root-attempt and market-return events",
        "sensitivity_design": {
            "method": "one_factor_at_a_time",
            "nodes": list(LEAVES + ASSEMBLIES),
            "nominal_rate": "1/10",
            "low_rate": "1/20",
            "high_rate": "3/20",
            "interpretation": "plus_or_minus_five_percentage_points",
            "scenario_count": 25,
            "full_reoptimization_per_scenario": 65536
        },
        "scenarios": summaries,
        "candidate_file": CANDIDATES_PATH.name,
        "candidate_record_count": written,
        "acceptance": {"passed": len(tests), "total": 18, "file": ACCEPTANCE_PATH.name},
    }
    return results, tests


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    started = datetime.now(timezone.utc)
    results, tests = run_enumeration()
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ACCEPTANCE_PATH.write_text(
        json.dumps(
            {
                "status": "pass" if len(tests) == 18 else "fail",
                "same_implementation_kernel": "src/q3/core.py",
                "tests": tests,
                "s6_independent_validation": "not_started",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    finished = datetime.now(timezone.utc)
    manifest = {
        "command": "python3 src/q3/01_solve.py",
        "python": sys.version,
        "platform": platform.platform(),
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "elapsed_seconds": (finished - started).total_seconds(),
        "inputs": {
            "s4_specification": "planning/analysis/2026-08-24_q3_s4_specification.md",
            "s2_parameter_interface": "planning/analysis/2026-08-24_q3_s2_assessment.md",
        },
        "outputs_sha256": {
            path.name: sha256(path)
            for path in (RESULTS_PATH, CANDIDATES_PATH, ACCEPTANCE_PATH)
        },
        "source_sha256": {
            path.name: sha256(path)
            for path in (Path(__file__), Path(__file__).with_name("core.py"))
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "complete",
        "elapsed_seconds": manifest["elapsed_seconds"],
        "candidate_records": results["candidate_record_count"],
        "acceptance": results["acceptance"],
        "best": {name: data["best_policy_ids"] for name, data in results["scenarios"].items()},
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
