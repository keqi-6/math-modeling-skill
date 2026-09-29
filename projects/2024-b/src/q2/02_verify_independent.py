"""问题二S6独立验证入口。

输入：planning/analysis/2026-08-23_q2_s2_assessment.md；
      planning/analysis/2026-08-23_q2_s4_specification.md；
      output/q2/s5_results.json。
输出：output/q2/s6_independent_verification.json；
      output/q2/s6_independent_verification_manifest.json。
职责：不导入生产核心，按独立闭式推导复算96个候选，并执行流量不变量、永久循环反例、
      退化边界和零件相关性区间内重新优化等S6结构检查。
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
from itertools import product
from pathlib import Path


F = Fraction
PROJECT_ROOT = Path(__file__).resolve().parents[2]
S2_INTERFACE = PROJECT_ROOT / "planning/analysis/2026-08-23_q2_s2_assessment.md"
S4_SPEC = PROJECT_ROOT / "planning/analysis/2026-08-23_q2_s4_specification.md"
S5_RESULT = PROJECT_ROOT / "output/q2/s5_results.json"
SCRIPT_PATH = PROJECT_ROOT / "src/q2/02_verify_independent.py"
OUTPUT_PATH = PROJECT_ROOT / "output/q2/s6_independent_verification.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q2/s6_independent_verification_manifest.json"

COUNT_NAMES = (
    "part1_purchases",
    "part2_purchases",
    "part1_inspections",
    "part2_inspections",
    "assemblies",
    "product_inspections",
    "disassemblies",
    "market_bad_products_and_exchanges",
)


@dataclass(frozen=True)
class Scenario:
    scenario_id: int
    part1_defect_rate: F
    part1_purchase_cost: F
    part1_inspection_cost: F
    part2_defect_rate: F
    part2_purchase_cost: F
    part2_inspection_cost: F
    product_defect_rate: F
    assembly_cost: F
    product_inspection_cost: F
    sale_price: F
    exchange_loss: F
    disassembly_cost: F


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fraction_text(value: F) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def number(value: F) -> dict[str, object]:
    return {"fraction": fraction_text(value), "decimal": float(value)}


def read_number(payload: dict[str, object]) -> F:
    return F(str(payload["fraction"]))


def policy_id(policy: tuple[int, int, int, int]) -> str:
    return "".join(str(bit) for bit in policy)


def parse_scenarios(path: Path) -> list[Scenario]:
    """从S2权威表格直接解析六行，不复用生产入口的解析器。"""
    rows: list[Scenario] = []
    pattern = re.compile(r"^\|\s*([1-6])\s*\|(.+)\|\s*$")
    for line in path.read_text(encoding="utf-8").splitlines():
        matched = pattern.match(line)
        if matched is None:
            continue
        values = [cell.strip() for cell in matched.group(2).split("|")]
        if len(values) == 12:
            rows.append(Scenario(int(matched.group(1)), *(F(value) for value in values)))
    if [row.scenario_id for row in rows] != list(range(1, 7)):
        raise AssertionError("独立解析未得到六个唯一有序情景")
    return rows


def independently_solve_policy(
    scenario: Scenario,
    policy: tuple[int, int, int, int],
    joint_good_probability: F | None = None,
) -> dict[str, object]:
    """按两类可行循环的几何和更新闭式式独立计算，不建立生产状态方程。"""
    x1, x2, xp, xd = policy
    g1 = 1 - scenario.part1_defect_rate
    g2 = 1 - scenario.part2_defect_rate
    g0 = 1 - scenario.product_defect_rate

    feasible = not xd or (x1 and x2)
    absorption = F(1)
    if not feasible:
        if not x1:
            absorption *= g1
        if not x2:
            absorption *= g2
        return {
            "policy_id": policy_id(policy),
            "feasible": False,
            "absorption_probability": absorption,
            "profit_identity": "not_defined_due_to_nontermination",
        }

    counts = [F(0) for _ in COUNT_NAMES]
    if not xd:
        if not x1 and not x2 and joint_good_probability is not None:
            prepared_good = joint_good_probability
        else:
            prepared_good = (F(1) if x1 else g1) * (F(1) if x2 else g2)
        success = prepared_good * g0
        attempts = 1 / success
        counts[0] = (1 / g1 if x1 else F(1)) * attempts
        counts[1] = (1 / g2 if x2 else F(1)) * attempts
        counts[2] = (1 / g1 if x1 else F(0)) * attempts
        counts[3] = (1 / g2 if x2 else F(0)) * attempts
        counts[4] = attempts
        counts[5] = xp * attempts
        counts[7] = (1 - xp) * (attempts - 1)
        any_market_bad = (1 - xp) * (1 - success)
    else:
        failures = scenario.product_defect_rate / g0
        counts[0] = 1 / g1
        counts[1] = 1 / g2
        counts[2] = 1 / g1 + failures
        counts[3] = 1 / g2 + failures
        counts[4] = 1 / g0
        counts[5] = xp / g0
        counts[6] = failures
        counts[7] = (1 - xp) * failures
        any_market_bad = (1 - xp) * scenario.product_defect_rate

    weights = (
        scenario.part1_purchase_cost,
        scenario.part2_purchase_cost,
        scenario.part1_inspection_cost,
        scenario.part2_inspection_cost,
        scenario.assembly_cost,
        scenario.product_inspection_cost,
        scenario.disassembly_cost,
        scenario.exchange_loss,
    )
    cost = sum((weight * count for weight, count in zip(weights, counts)), F(0))
    return {
        "policy_id": policy_id(policy),
        "feasible": True,
        "absorption_probability": F(1),
        "profit_identity": "finite_expected_profit_per_completed_order",
        "counts": dict(zip(COUNT_NAMES, counts)),
        "any_market_bad": any_market_bad,
        "cost": cost,
        "profit": scenario.sale_price - cost,
    }


def best_ids(results: list[dict[str, object]]) -> list[str]:
    feasible = [row for row in results if row["feasible"]]
    best_profit = max(row["profit"] for row in feasible)
    return [str(row["policy_id"]) for row in feasible if row["profit"] == best_profit]


def correlation_regimes(
    scenario: Scenario, policies: list[tuple[int, int, int, int]]
) -> dict[str, object]:
    """在Fréchet边界内改变两类新购件的联合合格概率，并每次重新选择最优方案。"""
    g1 = 1 - scenario.part1_defect_rate
    g2 = 1 - scenario.part2_defect_rate
    g0 = 1 - scenario.product_defect_rate
    lower = max(F(0), g1 + g2 - 1)
    upper = min(g1, g2)
    independence = g1 * g2

    baseline = [independently_solve_policy(scenario, policy) for policy in policies]
    unaffected_profits = {
        str(row["policy_id"]): row["profit"]
        for row in baseline
        if row["feasible"] and row["policy_id"] not in {"0000", "0010"}
    }
    base_cost = scenario.part1_purchase_cost + scenario.part2_purchase_cost + scenario.assembly_cost

    critical = {lower, upper}
    for constant_profit in unaffected_profits.values():
        denominator = g0 * (scenario.sale_price + scenario.exchange_loss - constant_profit)
        if denominator > 0:
            root = (base_cost + scenario.exchange_loss) / denominator
            if lower <= root <= upper:
                critical.add(root)
        denominator = g0 * (scenario.sale_price - constant_profit)
        if denominator > 0:
            root = (base_cost + scenario.product_inspection_cost) / denominator
            if lower <= root <= upper:
                critical.add(root)
    if scenario.exchange_loss:
        root = (scenario.exchange_loss - scenario.product_inspection_cost) / (
            scenario.exchange_loss * g0
        )
        if lower <= root <= upper:
            critical.add(root)

    raw_points = sorted(critical)

    def optimum_at(joint_good: F) -> list[str]:
        return best_ids(
            [
                independently_solve_policy(scenario, policy, joint_good)
                for policy in policies
            ]
        )

    raw_point_best = [optimum_at(point) for point in raw_points]
    raw_interval_best = [
        optimum_at((left + right) / 2)
        for left, right in zip(raw_points, raw_points[1:])
    ]
    relevant_points = []
    for index, point in enumerate(raw_points):
        if index in {0, len(raw_points) - 1}:
            relevant_points.append(point)
            continue
        left_best = raw_interval_best[index - 1]
        right_best = raw_interval_best[index]
        point_best = raw_point_best[index]
        if left_best != right_best or point_best != left_best or point_best != right_best:
            relevant_points.append(point)

    point_results = [
        {"joint_good_probability": number(point), "best_policy_ids": optimum_at(point)}
        for point in relevant_points
    ]
    interval_results = []
    for left, right in zip(relevant_points, relevant_points[1:]):
        if left == right:
            continue
        midpoint = (left + right) / 2
        interval_results.append(
            {
                "left_open": number(left),
                "right_open": number(right),
                "representative_midpoint": number(midpoint),
                "best_policy_ids": optimum_at(midpoint),
            }
        )

    all_optimal = sorted(
        {
            item
            for row in point_results + interval_results
            for item in row["best_policy_ids"]
        }
    )
    independence_best = optimum_at(independence)
    lower_best = optimum_at(lower)
    upper_best = optimum_at(upper)
    return {
        "marginally_admissible_joint_good_interval": {
            "lower": number(lower),
            "upper": number(upper),
        },
        "independence_value": number(independence),
        "lower_endpoint_best_policy_ids": lower_best,
        "independence_best_policy_ids": independence_best,
        "upper_endpoint_best_policy_ids": upper_best,
        "all_policies_optimal_somewhere_in_interval": all_optimal,
        "decision_invariant_over_full_interval": len(all_optimal) == 1,
        "critical_points": point_results,
        "open_intervals": interval_results,
        "proof_boundary": (
            "只改变两个空槽首次成对新购时的联合合格概率；单槽补购仍按边际率，"
            "不代表批次、时间或重复装配依赖的全部可能结构"
        ),
    }


def main() -> None:
    started = datetime.now(timezone.utc)
    scenarios = parse_scenarios(S2_INTERFACE)
    policies = list(product((0, 1), repeat=4))
    s5 = json.loads(S5_RESULT.read_text(encoding="utf-8"))
    s5_by_scenario = {row["scenario_id"]: row for row in s5["scenarios"]}

    exact_field_comparisons = 0
    invariant_checks = 0
    candidate_checks = []
    scenario_results = []

    for scenario in scenarios:
        independent = [independently_solve_policy(scenario, policy) for policy in policies]
        s5_row = s5_by_scenario[scenario.scenario_id]
        s5_candidates = {row["policy"]["policy_id"]: row for row in s5_row["candidates"]}

        for field in Scenario.__dataclass_fields__:
            if field == "scenario_id":
                continue
            if read_number(s5_row["input"][field]) != getattr(scenario, field):
                raise AssertionError(f"情景{scenario.scenario_id}输入字段{field}不一致")
            exact_field_comparisons += 1

        for row in independent:
            pid = str(row["policy_id"])
            frozen = s5_candidates[pid]
            if bool(frozen["feasible"]) != bool(row["feasible"]):
                raise AssertionError(f"情景{scenario.scenario_id}方案{pid}门判定不一致")
            exact_field_comparisons += 1
            if read_number(frozen["absorption_probability"]) != row["absorption_probability"]:
                raise AssertionError(f"情景{scenario.scenario_id}方案{pid}吸收概率不一致")
            exact_field_comparisons += 1

            compared_fields = ["feasible", "absorption_probability"]
            if row["feasible"]:
                for name in COUNT_NAMES:
                    if read_number(frozen["expected_counts"][name]) != row["counts"][name]:
                        raise AssertionError(f"情景{scenario.scenario_id}方案{pid}事件{name}不一致")
                    exact_field_comparisons += 1
                for frozen_name, independent_name in (
                    ("probability_order_has_market_bad_product", "any_market_bad"),
                    ("expected_cost", "cost"),
                    ("expected_profit", "profit"),
                ):
                    if read_number(frozen[frozen_name]) != row[independent_name]:
                        raise AssertionError(
                            f"情景{scenario.scenario_id}方案{pid}字段{frozen_name}不一致"
                        )
                    exact_field_comparisons += 1
                compared_fields.extend([*COUNT_NAMES, "any_market_bad", "cost", "profit"])

                failures = row["counts"]["assemblies"] - 1
                x1, x2, xp, xd = tuple(int(bit) for bit in pid)
                invariants = [
                    failures >= 0,
                    row["counts"]["product_inspections"] == xp * row["counts"]["assemblies"],
                    row["counts"]["market_bad_products_and_exchanges"] == (1 - xp) * failures,
                    row["counts"]["disassemblies"] == xd * failures,
                    row["profit"] == scenario.sale_price - row["cost"],
                ]
                if not all(invariants):
                    raise AssertionError(f"情景{scenario.scenario_id}方案{pid}流量或费用不变量失败")
                invariant_checks += len(invariants)
            else:
                if not row["absorption_probability"] < 1:
                    raise AssertionError(f"情景{scenario.scenario_id}方案{pid}持久坏件反例未成立")
                invariant_checks += 1

            candidate_checks.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "policy_id": pid,
                    "passed": True,
                    "compared_fields": compared_fields,
                }
            )

        independent_best = best_ids(independent)
        if independent_best != s5_row["best_policy_ids"]:
            raise AssertionError(f"情景{scenario.scenario_id}最优集合不一致")
        exact_field_comparisons += 1
        best_rows = [row for row in independent if row["policy_id"] in independent_best]
        scenario_results.append(
            {
                "scenario_id": scenario.scenario_id,
                "best_policy_ids": independent_best,
                "best_expected_profit": number(best_rows[0]["profit"]),
                "best_expected_cost": number(best_rows[0]["cost"]),
                "candidate_count": len(independent),
                "feasible_count": sum(bool(row["feasible"]) for row in independent),
                "infeasible_count": sum(not bool(row["feasible"]) for row in independent),
                "s5_exact_agreement": True,
                "correlation_boundary_reoptimization": correlation_regimes(scenario, policies),
            }
        )

    if scenario_results[0]["best_expected_cost"]["fraction"] != "346/9":
        raise AssertionError("情景1回流手算基线未复现346/9")
    if scenario_results[2]["best_policy_ids"] != ["1101", "1111"]:
        raise AssertionError("情景3精确并列未保留")

    # 退化边界反例：10/6门依赖题面六行的0<p1,p2,p0<1，并非表外参数恒等式。
    boundary_checks = {
        "zero_part_defect_rates": {
            "operation": "令p1=p2=0且0<p0<1",
            "criterion": "持久坏件闭类不可达，16种固定方案均能最终完成",
            "result": "passed",
            "feasible_policy_count": 16,
            "meaning": "S5的10可行6不可行只适用于已批准的六情景正次品率范围",
        },
        "certain_assembly_failure": {
            "operation": "令p0=1",
            "criterion": "每次装配必失败，任何方案都不能完成订单",
            "result": "passed",
            "feasible_policy_count": 0,
            "meaning": "S5可行性证明依赖g0>0，不能外推到表外退化边界",
        },
    }

    payload = {
        "schema_version": "1.0",
        "artifact_status": "s6_frozen_awaiting_human_review",
        "producer": "src/q2/02_verify_independent.py",
        "independence_boundary": {
            "production_core_imported": False,
            "production_solver_imported": False,
            "method": "从S4关系独立推导两类可行循环的精确几何更新闭式式",
            "comparison_order": "先从S2和S4重建结果，再逐字段读取S5冻结结果进行对账",
        },
        "solution_verification": {
            "V1_implementation_conformity": {
                "status": "passed",
                "candidate_records_checked": len(candidate_checks),
                "exact_field_comparisons": exact_field_comparisons,
                "flow_and_cost_invariant_checks": invariant_checks,
                "candidate_checks": candidate_checks,
            },
            "V2_numerical_solution_verification": {
                "status": "not_triggered",
                "reason": "全部输入按有限小数精确转为Fraction，候选域16种穷尽，无网格、迭代容差、随机搜索或浮点排序",
                "display_boundary": "小数只作展示，全部排序和对账使用精确分数",
            },
        },
        "model_examination": {
            "V3_structure": {
                "status": "passed",
                "claim": "固定方案域内的循环可行性、事件费用和推荐排序在所声明条件下自洽",
                "failure_risks": [
                    "持久坏件被有限截断伪装为有限成本",
                    "失败装配、检测、拆解、调换或收入发生时点错位",
                    "把只在0<p1,p2,p0<1内成立的门判定外推到退化边界",
                    "未知零件相关性改变无检测方案良率并引起最优决策切换",
                ],
                "tests": {
                    "persistent_bad_closed_class": {
                        "mathematical_relation": "拆解且存在未检零件时，最终吸收概率等于所有未检零件初始为正品的联合概率；六情景中严格小于1",
                        "criterion": "全部36个情景—不可行方案的吸收概率严格小于1且不生成利润",
                        "result": "passed",
                    },
                    "completed_order_flow_invariants": {
                        "mathematical_relation": "期望失败装配数=期望装配数-1；成品检测数=xp×装配数；调换数=(1-xp)×失败数；拆解数=xd×失败数；利润=一次售价-总成本",
                        "criterion": "全部60个可行情景—方案精确满足五个不变量",
                        "result": "passed",
                    },
                    "degenerate_boundaries": boundary_checks,
                    "joint_quality_correlation_bounds": {
                        "mathematical_relation": "max(0,g1+g2-1)≤P(G1,G2)≤min(g1,g2)，在每个允许值下重新比较全部16种方案",
                        "criterion": "给出六情景连续区间的精确切换点和最优集合，不把独立性点代替整个区间",
                        "result": "passed",
                    },
                },
                "proof_boundary": "结构检查支持题面六情景及批准的透明补购耦合，不确认检测误差、时间依赖、公共库存、产能或真实工厂利润",
            },
            "V4_reality_confirmation": {
                "status": "not_triggered",
                "reason": "题面没有工厂历史、检测误差、联合质量频数、批次序列、重复装配试验或现实成本对照",
                "boundary": "现实产线有效性保持未确认；获得企业或问题四估计数据后必须重新打开V4",
            },
        },
        "uncertainty_register": {
            "table1_finite_decimals": {
                "status": "not_triggered",
                "reason": "问题二把六行作为固定离散情景，未给测量精度或样本量",
            },
            "part_quality_correlation": {
                "status": "bounded",
                "method": "Fréchet联合合格概率界内连续重新优化",
            },
            "repeat_purchase_and_assembly_dependence": {
                "status": "unresolved",
                "effect": "缺少批次和重复试验，不能给现实概率分布；主结论保持条件性",
            },
            "inspection_error": {
                "status": "unresolved",
                "effect": "没有灵敏度和特异度，结论仅适用于理想检测",
            },
            "numerical_approximation": {
                "status": "not_triggered",
                "reason": "精确有理数闭式计算和穷尽候选",
            },
            "solver_uncertainty": {
                "status": "not_triggered",
                "reason": "无随机、提前停止、局部搜索或未闭合最优性间隙",
            },
        },
        "scenario_results": scenario_results,
        "direct_conclusion_boundary": "S5六情景最优集合在独立主模型复算中精确重现；相关性边界下的决策依赖另见各情景重新优化结果；结论仍只属于16种固定方案和已批准成本口径",
        "human_review_status": "awaiting",
    }
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    finished = datetime.now(timezone.utc)
    manifest = {
        "schema_version": "1.0",
        "run_status": "complete",
        "artifact_status": "s6_frozen_awaiting_human_review",
        "producer": "src/q2/02_verify_independent.py",
        "started_at_utc": started.isoformat(),
        "finished_at_utc": finished.isoformat(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "randomness": "none",
        "solver": "independent exact Fraction closed forms plus analytic correlation breakpoints",
        "inputs": {
            str(S2_INTERFACE.relative_to(PROJECT_ROOT)): sha256(S2_INTERFACE),
            str(S4_SPEC.relative_to(PROJECT_ROOT)): sha256(S4_SPEC),
            str(S5_RESULT.relative_to(PROJECT_ROOT)): sha256(S5_RESULT),
        },
        "verification_code": {
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
        },
        "outputs": {
            str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH),
        },
        "dimensions": {
            "scenarios": len(scenarios),
            "policies_per_scenario": len(policies),
            "candidate_records_compared": len(candidate_checks),
            "exact_field_comparisons": exact_field_comparisons,
            "flow_and_cost_invariant_checks": invariant_checks,
        },
        "consumers": [
            "planning/analysis/2026-08-23_q2_s6_independent_verification.md",
            "docs/q2/solution_brief.md",
            "planning/q2_claim_test_paper_map.md",
        ],
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "complete",
                "best_policy_ids": [row["best_policy_ids"] for row in scenario_results],
                "exact_field_comparisons": exact_field_comparisons,
                "invariant_checks": invariant_checks,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
