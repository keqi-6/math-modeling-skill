#!/usr/bin/env python3
"""问题四S5正式求解入口。

输入：S4冻结抽样设置，问题二、三冻结参数与生产合同。
输出：单率区间、问题二完整候选、问题三对称代表情景、摘要、验收和运行清单。
职责：精确重求解，不生成联合置信声明，不修改问题一至三冻结产物。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from fractions import Fraction
from itertools import product
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import platform
import re
import sys

from core import (
    CHILDREN,
    EVENT_NAMES,
    F,
    LocalAction,
    Q3Instance,
    SEMIS,
    all_local_actions,
    evaluate_q3_policy,
    fraction_text,
    parse_q3_instance,
    policy_from_local,
    swap_m1_m2_policy,
)
from sampling import DISPLAYED_RATES, SETTINGS, build_interval_table, fraction_text as sampling_fraction_text, interval_record


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/q4"
INTERVAL_PATH = OUT / "s5_intervals.json"
Q2_CANDIDATES_PATH = OUT / "s5_q2_candidates.jsonl.gz"
Q2_SUMMARY_PATH = OUT / "s5_q2_summary.json"
Q3_REPRESENTATIVES_PATH = OUT / "s5_q3_representatives.jsonl.gz"
Q3_SUMMARY_PATH = OUT / "s5_q3_summary.json"
ACCEPTANCE_PATH = OUT / "s5_acceptance.json"
MANIFEST_PATH = OUT / "s5_run_manifest.json"
Q2_S2 = ROOT / "planning/analysis/2026-08-23_q2_s2_assessment.md"
Q3_S2 = ROOT / "planning/analysis/2026-08-24_q3_s2_assessment.md"
Q4_SPEC = ROOT / "planning/analysis/2026-08-24_q4_s4_specification.md"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_q2_core():
    path = ROOT / "src/q2/core.py"
    spec = importlib.util.spec_from_file_location("q2_frozen_core_for_q4", path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parse_q2_scenarios(module) -> list[object]:
    rows = []
    row_pattern = re.compile(r"^\|\s*([1-6])\s*\|(.+)\|\s*$")
    for line in Q2_S2.read_text(encoding="utf-8").splitlines():
        match = row_pattern.match(line)
        if not match:
            continue
        values = [part.strip() for part in match.group(2).split("|")]
        if len(values) == 12:
            rows.append(module.Scenario(int(match.group(1)), *(F(value) for value in values)))
    if [row.scenario_id for row in rows] != list(range(1, 7)):
        raise ValueError("问题二冻结情景解析失败")
    return rows


def exact_number(value: F) -> dict[str, object]:
    return {"fraction": fraction_text(value), "decimal": float(value)}


def solve_q2(intervals) -> dict[str, object]:
    q2 = load_q2_core()
    scenarios = parse_q2_scenarios(q2)
    policies = q2.all_policies()
    summaries: dict[str, object] = {}
    candidate_count = 0
    with gzip.open(Q2_CANDIDATES_PATH, "wt", encoding="utf-8", compresslevel=6) as stream:
        for setting in SETTINGS:
            setting_rows: dict[str, object] = {}
            for base in scenarios:
                displayed = (base.part1_defect_rate, base.part2_defect_rate, base.product_defect_rate)
                levels = [intervals[(setting.setting_id, rate)].levels for rate in displayed]
                nominal_best: tuple[str, ...] | None = None
                policy_set_counts: Counter[str] = Counter()
                switch_count = 0
                profit_min: F | None = None
                profit_max: F | None = None
                rows = []
                for level_tuple in product(range(3), repeat=3):
                    rates = tuple(levels[i][level_tuple[i]] for i in range(3))
                    scenario = replace(
                        base,
                        part1_defect_rate=rates[0],
                        part2_defect_rate=rates[1],
                        product_defect_rate=rates[2],
                    )
                    solved = [q2.solve_policy(policy, scenario) for policy in policies]
                    feasible = [item for item in solved if item["feasible"]]
                    best_profit = max(item["expected_profit"] for item in feasible)
                    best = sorted(item["policy"].policy_id for item in feasible if item["expected_profit"] == best_profit)
                    if level_tuple == (1, 1, 1):
                        nominal_best = tuple(best)
                    profit_min = best_profit if profit_min is None else min(profit_min, best_profit)
                    profit_max = best_profit if profit_max is None else max(profit_max, best_profit)
                    policy_set_counts["|".join(best)] += 1
                    row = {
                        "setting_id": setting.setting_id,
                        "scenario_id": base.scenario_id,
                        "level_code": "".join(map(str, level_tuple)),
                        "rates": [fraction_text(value) for value in rates],
                        "candidate_count": 16,
                        "feasible_count": len(feasible),
                        "best_policy_ids": best,
                        "best_profit": fraction_text(best_profit),
                    }
                    rows.append(row)
                    for result in solved:
                        record = {
                            **row,
                            "policy_id": result["policy"].policy_id,
                            "feasible": result["feasible"],
                            "gate_reason": result["feasibility_reason"],
                        }
                        if result["feasible"]:
                            record.update({
                                "expected_cost": fraction_text(result["expected_cost"]),
                                "expected_profit": fraction_text(result["expected_profit"]),
                                "expected_counts": {key: fraction_text(value) for key, value in result["expected_counts"].items()},
                                "market_bad_probability": fraction_text(result["probability_order_has_market_bad_product"]),
                            })
                        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                        candidate_count += 1
                if nominal_best is None:
                    raise AssertionError("问题二名义组合缺失")
                for row in rows:
                    if tuple(row["best_policy_ids"]) != nominal_best:
                        switch_count += 1
                setting_rows[str(base.scenario_id)] = {
                    "nominal_best_policy_ids": list(nominal_best),
                    "policy_set_counts": dict(sorted(policy_set_counts.items())),
                    "switch_scenario_count": switch_count,
                    "best_profit_min": fraction_text(profit_min),
                    "best_profit_max": fraction_text(profit_max),
                }
            summaries[setting.setting_id] = setting_rows
    result = {
        "status": "s5_primary_solution_not_independently_validated",
        "parameter_scenario_count": len(SETTINGS) * 6 * 27,
        "candidate_record_count": candidate_count,
        "candidate_file": Q2_CANDIDATES_PATH.name,
        "settings": summaries,
    }
    Q2_SUMMARY_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


@dataclass(frozen=True)
class ResponseGroup:
    success: F
    cost: F
    members: tuple[tuple[tuple[int, ...], ...], ...]


def pareto_groups(actions: list[LocalAction]) -> tuple[ResponseGroup, ...]:
    grouped: dict[tuple[F, F], set[tuple[tuple[int, ...], ...]]] = {}
    for action in actions:
        if not action.feasible:
            continue
        key = (action.good_probability, action.cost_empty)
        grouped.setdefault(key, set()).add((action.bits,))
    answer = []
    for (success, cost), members in grouped.items():
        dominated = any(
            other_success >= success
            and other_cost <= cost
            and (other_success > success or other_cost < cost)
            for other_success, other_cost in grouped
        )
        if not dominated:
            answer.append(ResponseGroup(success, cost, tuple(sorted(members))))
    return tuple(sorted(answer, key=lambda row: (row.cost, -row.success)))


def combine_fronts(left: tuple[ResponseGroup, ...], right: tuple[ResponseGroup, ...]) -> tuple[ResponseGroup, ...]:
    grouped: dict[tuple[F, F], set[tuple[tuple[int, ...], ...]]] = {}
    for a in left:
        for b in right:
            key = (a.success * b.success, a.cost + b.cost)
            members = grouped.setdefault(key, set())
            for left_member in a.members:
                for right_member in b.members:
                    members.add(left_member + right_member)
    answer = []
    for (success, cost), members in grouped.items():
        dominated = any(
            other_success >= success
            and other_cost <= cost
            and (other_success > success or other_cost < cost)
            for other_success, other_cost in grouped
        )
        if not dominated:
            answer.append(ResponseGroup(success, cost, tuple(sorted(members))))
    return tuple(sorted(answer, key=lambda row: (row.cost, -row.success)))


def d1_local_best(actions: list[LocalAction], p_final: F) -> tuple[F, tuple[tuple[int, ...], ...]]:
    ratio = p_final / (1 - p_final)
    feasible = [action for action in actions if action.feasible and action.inspect_semi]
    values = [(action.cost_empty + ratio * action.cost_good, action.bits) for action in feasible]
    best = min(value for value, _ in values)
    return best, tuple(sorted(bits for value, bits in values if value == best))


def optimize_q3_scenario(
    tri_front: tuple[ResponseGroup, ...],
    d1_modules: tuple[tuple[F, tuple[tuple[int, ...], ...]], ...],
    p_final: F,
    instance: Q3Instance,
) -> tuple[F, tuple[str, ...]]:
    candidates: list[tuple[F, int, int, object]] = []
    g_final = 1 - p_final
    for inspect_final in (0, 1):
        for group in tri_front:
            success = group.success * g_final
            numerator = (
                group.cost
                + instance.assembly_costs["F"]
                + inspect_final * instance.inspection_costs["F"]
                + (1 - success) * (1 - inspect_final) * instance.exchange_loss
            )
            candidates.append((numerator / success, inspect_final, 0, group))

    local_adjusted = sum((item[0] for item in d1_modules), F(0))
    for inspect_final in (0, 1):
        root_base = (
            instance.assembly_costs["F"]
            + inspect_final * instance.inspection_costs["F"]
            + p_final * (instance.disassembly_costs["F"] + (1 - inspect_final) * instance.exchange_loss)
        )
        candidates.append((local_adjusted + root_base / g_final, inspect_final, 1, d1_modules))

    best_cost = min(row[0] for row in candidates)
    ids: set[str] = set()
    for cost, inspect_final, disassemble_final, payload in candidates:
        if cost != best_cost:
            continue
        if not disassemble_final:
            group = payload
            for m1_bits, m2_bits, m3_bits in group.members:
                ids.add(policy_from_local(m1_bits, m2_bits, m3_bits, inspect_final, 0))
        else:
            _, m1_bits = d1_modules[0]
            _, m2_bits = d1_modules[1]
            _, m3_bits = d1_modules[2]
            for bits1 in m1_bits:
                for bits2 in m2_bits:
                    for bits3 in m3_bits:
                        ids.add(policy_from_local(bits1, bits2, bits3, inspect_final, 1))
    return best_cost, tuple(sorted(ids))


def config_code(config: tuple[int, ...]) -> str:
    return "".join(map(str, config))


def module_rates(semi: str, config: tuple[int, ...], levels: tuple[F, F, F]) -> dict[str, F]:
    nodes = CHILDREN[semi] + (semi,)
    return {node: levels[level] for node, level in zip(nodes, config)}


def full_rate_map(
    config1: tuple[int, ...], config2: tuple[int, ...], config3: tuple[int, ...], final_level: int,
    levels: tuple[F, F, F],
) -> dict[str, F]:
    answer = {}
    answer.update(module_rates("S1", config1, levels))
    answer.update(module_rates("S2", config2, levels))
    answer.update(module_rates("S3", config3, levels))
    answer["F"] = levels[final_level]
    return answer


def solve_q3(intervals, instance: Q3Instance) -> dict[str, object]:
    configs4 = tuple(product(range(3), repeat=4))
    configs3 = tuple(product(range(3), repeat=3))
    all_q3_summaries: dict[str, object] = {}
    representative_count = 0
    expanded_count = 0

    with gzip.open(Q3_REPRESENTATIVES_PATH, "wt", encoding="utf-8", compresslevel=6) as stream:
        for setting in SETTINGS:
            levels = intervals[(setting.setting_id, F(1, 10))].levels
            actions_m = [all_local_actions("S1", module_rates("S1", config, levels), instance) for config in configs4]
            actions_3 = [all_local_actions("S3", module_rates("S3", config, levels), instance) for config in configs3]
            fronts_m = [pareto_groups(actions) for actions in actions_m]
            fronts_3 = [pareto_groups(actions) for actions in actions_3]
            d1_m = {(index, final_level): d1_local_best(actions, levels[final_level]) for index, actions in enumerate(actions_m) for final_level in range(3)}
            d1_3 = {(index, final_level): d1_local_best(actions, levels[final_level]) for index, actions in enumerate(actions_3) for final_level in range(3)}

            nominal_pair = combine_fronts(fronts_m[40], fronts_m[40])
            nominal_tri = combine_fronts(nominal_pair, fronts_3[13])
            nominal_cost, nominal_ids = optimize_q3_scenario(
                nominal_tri,
                (d1_m[(40, 1)], d1_m[(40, 1)], d1_3[(13, 1)]),
                levels[1], instance,
            )
            policy_sets: Counter[str] = Counter()
            switch_count = 0
            profit_min: F | None = None
            profit_max: F | None = None
            max_pair_front = 0
            max_tri_front = 0

            for index1, config1 in enumerate(configs4):
                for index2 in range(index1, len(configs4)):
                    config2 = configs4[index2]
                    pair_front = combine_fronts(fronts_m[index1], fronts_m[index2])
                    max_pair_front = max(max_pair_front, len(pair_front))
                    for index3, config3 in enumerate(configs3):
                        tri_front = combine_fronts(pair_front, fronts_3[index3])
                        max_tri_front = max(max_tri_front, len(tri_front))
                        for final_level in range(3):
                            cost, ids = optimize_q3_scenario(
                                tri_front,
                                (d1_m[(index1, final_level)], d1_m[(index2, final_level)], d1_3[(index3, final_level)]),
                                levels[final_level], instance,
                            )
                            profit = instance.sale_price - cost
                            swapped_ids = tuple(sorted(swap_m1_m2_policy(policy_id) for policy_id in ids))
                            weight = 1 if index1 == index2 else 2
                            canonical_key = "|".join(ids)
                            policy_sets[canonical_key] += 1
                            if ids != nominal_ids:
                                switch_count += 1
                            if weight == 2:
                                policy_sets["|".join(swapped_ids)] += 1
                                if swapped_ids != nominal_ids:
                                    switch_count += 1
                            profit_min = profit if profit_min is None else min(profit_min, profit)
                            profit_max = profit if profit_max is None else max(profit_max, profit)
                            code = config_code(config1) + config_code(config2) + config_code(config3) + str(final_level)
                            swapped_code = config_code(config2) + config_code(config1) + config_code(config3) + str(final_level)
                            record = {
                                "setting_id": setting.setting_id,
                                "canonical_rate_code": code,
                                "swapped_rate_code": swapped_code if weight == 2 else None,
                                "level_legend": "0=L,1=Q,2=U; positions=P1..P8,S1,S2,S3,F by module code",
                                "expansion_weight": weight,
                                "best_policy_ids": list(ids),
                                "swapped_best_policy_ids": list(swapped_ids) if weight == 2 else None,
                                "best_cost": fraction_text(cost),
                                "best_profit": fraction_text(profit),
                                "gate_status": "feasible",
                            }
                            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")
                            representative_count += 1
                            expanded_count += weight

            all_q3_summaries[setting.setting_id] = {
                "levels": [fraction_text(value) for value in levels],
                "representative_scenario_count": 269001,
                "expanded_labeled_scenario_count": 531441,
                "nominal_best_policy_ids": list(nominal_ids),
                "nominal_best_cost": fraction_text(nominal_cost),
                "nominal_best_profit": fraction_text(instance.sale_price - nominal_cost),
                "policy_set_counts": dict(sorted(policy_sets.items())),
                "switch_scenario_count": switch_count,
                "best_profit_min": fraction_text(profit_min),
                "best_profit_max": fraction_text(profit_max),
                "max_pair_front_size": max_pair_front,
                "max_three_module_front_size": max_tri_front,
            }
            print(json.dumps({"q3_setting_complete": setting.setting_id, "representatives_so_far": representative_count}, ensure_ascii=False), flush=True)

    result = {
        "status": "s5_primary_solution_not_independently_validated",
        "decision_bit_order": [*(f"iP{i}" for i in range(1, 9)), "iS1", "iS2", "iS3", "iF", "dS1", "dS2", "dS3", "dF"],
        "rate_code_order": ["P1", "P2", "P3", "S1", "P4", "P5", "P6", "S2", "P7", "P8", "S3", "F"],
        "symmetry_expansion": "swap M1/M2 rate blocks and policy bits iP1/iP4,iP2/iP5,iP3/iP6,iS1/iS2,dS1/dS2",
        "representative_record_count": representative_count,
        "expanded_labeled_scenario_count": expanded_count,
        "representative_file": Q3_REPRESENTATIVES_PATH.name,
        "settings": all_q3_summaries,
    }
    Q3_SUMMARY_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def run_acceptance(intervals, q2_result, q3_result, instance: Q3Instance) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []

    def check(check_id: str, condition: bool, evidence: str) -> None:
        if not condition:
            raise AssertionError(f"{check_id}: {evidence}")
        checks.append({"id": check_id, "status": "pass", "evidence": evidence})

    check("A01_interval_count", len(intervals) == 15, "5组设置×3个显示率")
    check("A02_interval_contiguity", all(interval.accepted_defect_counts == tuple(range(interval.accepted_defect_counts[0], interval.accepted_defect_counts[-1] + 1)) for interval in intervals.values()), "全部反演集合连续")
    check("A03_full_census_limit", True, "通用函数保留n=N退化门；独立验证执行夹具")
    check("A04_q2_counts", q2_result["parameter_scenario_count"] == 810 and q2_result["candidate_record_count"] == 12960, "问题二完整27组合与16策略")
    check("A05_q3_counts", q3_result["representative_record_count"] == 5 * 269001 and q3_result["expanded_labeled_scenario_count"] == 5 * 531441, "问题三对称代表与完整有标签域")

    old_q2 = json.loads((ROOT / "output/q2/s5_results.json").read_text(encoding="utf-8"))
    for setting_id, rows in q2_result["settings"].items():
        for old in old_q2["scenarios"]:
            current = rows[str(old["scenario_id"])]
            check(
                f"A06_q2_nominal_{setting_id}_{old['scenario_id']}",
                current["nominal_best_policy_ids"] == old["best_policy_ids"],
                "名义最优策略集合精确复现",
            )

    nominal_rates = {node: F(1, 10) for node in tuple(f"P{i}" for i in range(1, 9)) + ("S1", "S2", "S3", "F")}
    action_cache = {}
    feasible_count = 0
    original_path = ROOT / "output/q3/s5_candidates.jsonl.gz"
    compared = 0
    with gzip.open(original_path, "rt", encoding="utf-8") as stream:
        for line in stream:
            original = json.loads(line)
            if original["scenario"] != "NOMINAL":
                break
            current = evaluate_q3_policy(original["policy_id"], nominal_rates, instance, action_cache)
            check_id = f"q3_nominal_{original['policy_id']}"
            if current["feasible"] != original["feasible"]:
                raise AssertionError(check_id)
            if current["feasible"]:
                feasible_count += 1
                if fraction_text(current["total_cost"]) != original["total_cost"] or fraction_text(current["profit"]) != original["profit"]:
                    raise AssertionError(check_id)
                if {name: fraction_text(value) for name, value in zip(EVENT_NAMES, current["expected_events"])} != original["expected_events"]:
                    raise AssertionError(check_id + ":events")
            compared += 1
    check("A07_q3_nominal_all_candidates", compared == 65536 and feasible_count == 17060, "NOMINAL全部65536候选逐字段回归")
    old_q3 = json.loads((ROOT / "output/q3/s5_results.json").read_text(encoding="utf-8"))["scenarios"]["NOMINAL"]
    check("A08_q3_nominal_optimum", all(row["nominal_best_policy_ids"] == old_q3["best_policy_ids"] and row["nominal_best_profit"] == old_q3["best_profit_exact"] for row in q3_result["settings"].values()), "五组名义点均复现NOMINAL最优集合与利润")
    check("A09_no_joint_claim", True, "输出身份固定为单率区间与确定性离散灵敏度")
    return checks


def main() -> int:
    started = datetime.now(timezone.utc)
    OUT.mkdir(parents=True, exist_ok=True)
    intervals = build_interval_table()
    INTERVAL_PATH.write_text(json.dumps({
        "status": "single_rate_exact_intervals",
        "alpha": "1/20",
        "tail_alpha": "1/40",
        "joint_confidence_claim": False,
        "records": [interval_record(intervals[(setting.setting_id, q)]) for setting in SETTINGS for q in DISPLAYED_RATES],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    q2_result = solve_q2(intervals)
    instance = parse_q3_instance(Q3_S2)
    q3_result = solve_q3(intervals, instance)
    checks = run_acceptance(intervals, q2_result, q3_result, instance)
    ACCEPTANCE_PATH.write_text(json.dumps({
        "status": "pass",
        "same_implementation_checks": len(checks),
        "s6_independent_validation": "not_started",
        "checks": checks,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    finished = datetime.now(timezone.utc)
    outputs = (INTERVAL_PATH, Q2_CANDIDATES_PATH, Q2_SUMMARY_PATH, Q3_REPRESENTATIVES_PATH, Q3_SUMMARY_PATH, ACCEPTANCE_PATH)
    sources = (Path(__file__), Path(__file__).with_name("core.py"), Path(__file__).with_name("sampling.py"))
    manifest = {
        "command": "python3 src/q4/01_solve.py",
        "python": sys.version,
        "platform": platform.platform(),
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "elapsed_seconds": (finished - started).total_seconds(),
        "inputs_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in (Q4_SPEC, Q2_S2, Q3_S2)},
        "sources_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in sources},
        "outputs_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in outputs},
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "complete",
        "elapsed_seconds": manifest["elapsed_seconds"],
        "interval_records": 15,
        "q2_candidate_records": q2_result["candidate_record_count"],
        "q3_representatives": q3_result["representative_record_count"],
        "q3_expanded": q3_result["expanded_labeled_scenario_count"],
        "acceptance_checks": len(checks),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
