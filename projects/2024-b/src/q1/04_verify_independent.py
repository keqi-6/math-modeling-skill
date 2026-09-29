"""问题一S6独立验证器：不导入主求解核心，不复用其概率或优化函数。

计算输入仅取冻结产物中的N和阈值；报告数字只在独立计算完成后用于精确对账。验证风险、
ASN、全D最坏点、宽类Bellman下界、N=10阈值类全枚举，以及小N结构单调性。
"""

from __future__ import annotations

import hashlib
import itertools
import json
import platform
import sys
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "planning/analysis/2026-08-23_q1_s4_separate_sequential_specification.md"
S5_RESULT_PATH = PROJECT_ROOT / "output/q1/s5_results.json"
S5_CLOSURE_PATH = PROJECT_ROOT / "output/q1/s5_finite_closure.json"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/s6_independent_verification.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s6_independent_verification_manifest.json"
SCRIPT_PATH = Path(__file__).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fraction_from_payload(payload: dict[str, object]) -> Fraction:
    return Fraction(int(payload["numerator"]), int(payload["denominator"]))


def fraction_payload(value: Fraction, digits: int = 24) -> dict[str, object]:
    with localcontext() as context:
        context.prec = digits
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": format(decimal_value, "f"),
    }


def boundary_counts(n: int) -> tuple[int, int]:
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("N必须为正整数")
    d0 = n // 10
    return d0, d0 + 1


def threshold_actions(n: int, scenario: str, thresholds: tuple[int, ...]) -> tuple[int, ...]:
    if len(thresholds) != n - 1:
        raise ValueError("阈值长度错误")
    vector: list[int] = []
    for t, threshold in enumerate(thresholds, start=1):
        if scenario == "R" and not 0 <= threshold <= t + 1:
            raise ValueError("R阈值越界")
        if scenario == "A" and not -1 <= threshold <= t:
            raise ValueError("A阈值越界")
        for x in range(t + 1):
            vector.append(int(x >= threshold if scenario == "R" else x <= threshold))
    return tuple(vector)


def independently_evaluate(
    n: int,
    d: int,
    scenario: str,
    thresholds: tuple[int, ...],
) -> tuple[Fraction, Fraction, Fraction]:
    """独立前向概率流；返回早停概率、ASN和终点概率。"""

    threshold_actions(n, scenario, thresholds)
    alive: dict[int, Fraction] = {0: Fraction(1)}
    stopped = Fraction(0)
    stopped_time_mass = Fraction(0)
    for t in range(n):
        following: dict[int, Fraction] = {}
        for x, mass in alive.items():
            if mass == 0:
                continue
            stop = False
            if 1 <= t < n:
                threshold = thresholds[t - 1]
                stop = x >= threshold if scenario == "R" else x <= threshold
            if stop:
                stopped += mass
                stopped_time_mass += t * mass
                continue
            defect_numerator = d - x
            good_numerator = n - d - t + x
            if defect_numerator < 0 or good_numerator < 0:
                raise AssertionError("不可达状态出现正概率")
            denominator = n - t
            defect = Fraction(defect_numerator, denominator)
            good = Fraction(good_numerator, denominator)
            if defect + good != 1:
                raise AssertionError("独立转移不守恒")
            following[x + 1] = following.get(x + 1, Fraction(0)) + mass * defect
            following[x] = following.get(x, Fraction(0)) + mass * good
        alive = following
    terminal = sum(alive.values(), Fraction(0))
    if stopped + terminal != 1:
        raise AssertionError("独立早停与终点质量不守恒")
    return stopped, stopped_time_mass + n * terminal, terminal


def falling(value: int, length: int) -> int:
    if length < 0 or length > value:
        return 0
    answer = 1
    for offset in range(length):
        answer *= value - offset
    return answer


def likelihood(n: int, d: int, t: int, x: int) -> Fraction:
    if not 0 <= x <= t <= n:
        return Fraction(0)
    return Fraction(
        (2**t) * falling(d, x) * falling(n - d, t - x),
        falling(n, t),
    )


def independent_wide_bellman_bound(
    n: int,
    scenario: str,
    multiplier: Fraction,
) -> Fraction:
    d0, d1 = boundary_counts(n)
    if scenario == "R":
        target_d, null_d, delta = d1, d0, Fraction(1, 20)
    else:
        target_d, null_d, delta = d0, d1, Fraction(1, 10)
    values = {x: n * likelihood(n, target_d, n, x) for x in range(n + 1)}
    for t in range(n - 1, 0, -1):
        prior: dict[int, Fraction] = {}
        for x in range(t + 1):
            stop = t * likelihood(n, target_d, t, x) + multiplier * likelihood(
                n,
                null_d,
                t,
                x,
            )
            keep = (values[x] + values[x + 1]) / 2
            prior[x] = min(stop, keep)
        values = prior
    return (values[0] + values[1]) / 2 - multiplier * delta


def canonical_domains(n: int, scenario: str) -> tuple[tuple[int, ...], ...]:
    d0, d1 = boundary_counts(n)
    domains: list[tuple[int, ...]] = []
    for t in range(1, n):
        if scenario == "R":
            active_maximum = min(t, d1)
            values = list(range(active_maximum + 1))
            if t + 1 not in values:
                values.append(t + 1)
        else:
            reachable_minimum = max(0, t - (n - d0))
            reachable_maximum = min(t, d1)
            values = [-1, *range(reachable_minimum, reachable_maximum + 1)]
        domains.append(tuple(values))
    return tuple(domains)


def independent_exhaustive_optimum(
    n: int,
    scenario: str,
) -> tuple[Fraction, tuple[int, ...], int, int]:
    d0, d1 = boundary_counts(n)
    if scenario == "R":
        null_d, target_d, limit = d0, d1, Fraction(1, 20)
    else:
        null_d, target_d, limit = d1, d0, Fraction(1, 10)
    best: tuple[Fraction, tuple[int, ...], tuple[int, ...]] | None = None
    policies = 0
    feasible = 0
    for thresholds in itertools.product(*canonical_domains(n, scenario)):
        policies += 1
        risk, _, _ = independently_evaluate(n, null_d, scenario, thresholds)
        if risk > limit:
            continue
        feasible += 1
        _, asn, _ = independently_evaluate(n, target_d, scenario, thresholds)
        candidate = (asn, threshold_actions(n, scenario, thresholds), thresholds)
        if best is None or candidate < best:
            best = candidate
    if best is None:
        raise AssertionError("独立全枚举没有找到可行阈值")
    return best[0], best[2], policies, feasible


def structural_small_n_examination() -> tuple[int, int]:
    """V3：攻击“边界D一定是复合最坏点”的结构主张。"""

    policies = 0
    comparisons = 0
    for n in range(1, 7):
        for scenario in ("R", "A"):
            for thresholds in itertools.product(*canonical_domains(n, scenario)):
                policies += 1
                curve = [
                    independently_evaluate(n, d, scenario, thresholds)
                    for d in range(n + 1)
                ]
                stops = [item[0] for item in curve]
                asns = [item[1] for item in curve]
                if scenario == "R":
                    valid = stops == sorted(stops) and asns == sorted(asns, reverse=True)
                else:
                    valid = stops == sorted(stops, reverse=True) and asns == sorted(asns)
                if not valid:
                    raise AssertionError("V3小N反例：复合最坏点缩减失效")
                comparisons += 2 * n
    return policies, comparisons


def main() -> None:
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    s5_payload = json.loads(S5_RESULT_PATH.read_text(encoding="utf-8"))
    closure_payload = json.loads(S5_CLOSURE_PATH.read_text(encoding="utf-8"))
    closure_by_n = {int(record["N"]): record for record in closure_payload["results"]}
    records: list[dict[str, object]] = []
    checks: list[str] = []

    for record in s5_payload["results"]:
        n = int(record["N"])
        d0, d1 = boundary_counts(n)
        scenario_records: dict[str, object] = {}
        for scenario in ("R", "A"):
            source = record["scenarios"][scenario]
            thresholds = tuple(int(item["threshold"]) for item in source["thresholds"])
            curve = [
                independently_evaluate(n, d, scenario, thresholds)
                for d in range(n + 1)
            ]
            stops = [item[0] for item in curve]
            asns = [item[1] for item in curve]
            if scenario == "R":
                null_d, target_d, limit = d0, d1, Fraction(1, 20)
                monotone = stops == sorted(stops) and asns == sorted(asns, reverse=True)
            else:
                null_d, target_d, limit = d1, d0, Fraction(1, 10)
                monotone = stops == sorted(stops, reverse=True) and asns == sorted(asns)
            risk = curve[null_d][0]
            target_asn = curve[target_d][1]
            if not monotone:
                raise AssertionError("独立全D曲线单调性失败")
            if risk > limit:
                raise AssertionError("独立复算发现风险超限")
            if risk != fraction_from_payload(source["risk_at_composite_worst_point"]):
                raise AssertionError("独立风险与S5报告不一致")
            if target_asn != fraction_from_payload(source["worst_target_ASN_upper_bound"]):
                raise AssertionError("独立ASN与S5报告不一致")
            multiplier = fraction_from_payload(source["best_multiplier"])
            wide_bound = independent_wide_bellman_bound(n, scenario, multiplier)
            if wide_bound != fraction_from_payload(source["dual_lower_bound"]):
                raise AssertionError("独立Bellman下界与S5报告不一致")
            checks.extend(
                [
                    f"N={n}:{scenario}:independent_risk_exact_match",
                    f"N={n}:{scenario}:independent_ASN_exact_match",
                    f"N={n}:{scenario}:independent_full_D_worst_points",
                    f"N={n}:{scenario}:independent_mass_conservation",
                    f"N={n}:{scenario}:independent_wide_bound_exact_match",
                ]
            )
            scenario_record: dict[str, object] = {
                "scenario": scenario,
                "thresholds_read_as_verification_input_only": list(thresholds),
                "independent_risk": fraction_payload(risk),
                "independent_target_ASN": fraction_payload(target_asn),
                "independent_wide_lower_bound_at_reported_multiplier": fraction_payload(
                    wide_bound
                ),
                "risk_limit": fraction_payload(limit),
                "full_D_monotonicity": "passed",
                "mass_conservation": "passed_for_every_D",
            }
            if n in closure_by_n:
                closure = closure_by_n[n]["scenarios"][scenario]
                if thresholds != tuple(
                    int(item["threshold"]) for item in closure["thresholds"]
                ):
                    raise AssertionError("S5主候选与有限闭合候选不一致")
                if n == 10:
                    optimum, best_thresholds, policies, feasible = independent_exhaustive_optimum(
                        n,
                        scenario,
                    )
                    if optimum != target_asn or best_thresholds != thresholds:
                        raise AssertionError("N=10独立全枚举否定了阈值类最优声明")
                    scenario_record["deterministic_threshold_certificate"] = {
                        "status": "independently_verified_by_complete_enumeration",
                        "optimum_ASN": fraction_payload(optimum),
                        "canonical_policies_enumerated": policies,
                        "feasible_policies": feasible,
                    }
                    checks.append(f"N=10:{scenario}:independent_complete_threshold_enumeration")
                else:
                    threshold_bound = fraction_from_payload(
                        closure["deterministic_threshold_lower_bound"]
                    )
                    reported_upper = fraction_from_payload(closure["ASN_upper_bound"])
                    if not wide_bound <= threshold_bound <= reported_upper == target_asn:
                        raise AssertionError("有限闭合的界顺序或上界对账失败")
                    scenario_record["deterministic_threshold_certificate"] = {
                        "status": "reported_frontier_bound_not_yet_independently_reconstructed",
                        "reported_threshold_lower_bound": fraction_payload(threshold_bound),
                        "safe_independently_verified_fallback_lower_bound": fraction_payload(
                            wide_bound
                        ),
                    }
            scenario_records[scenario] = scenario_record
        records.append({"N": n, "D0": d0, "D1": d1, "scenarios": scenario_records})

    v3_policies, v3_comparisons = structural_small_n_examination()
    output = {
        "schema_version": "1.0",
        "artifact_status": "s6_verification_in_progress",
        "producer": "src/q1/04_verify_independent.py",
        "independence_contract": {
            "imports_main_core": False,
            "uses_reported_thresholds_as_inputs": True,
            "uses_reported_metrics_as_computation_inputs": False,
            "comparison_occurs_after_independent_recomputation": True,
        },
        "solution_verification": {
            "V1_implementation_conformance": "passed_for_all_8_fixture_N_and_both_scenarios",
            "V2_numerical_solution": "exact_rational_arithmetic_no_rounding_decision",
            "N10_threshold_optimality": "passed_by_independent_complete_enumeration",
            "N23_N50_threshold_frontier_bounds": "not_yet_independently_reconstructed",
        },
        "model_examination": {
            "V3_status": "passed",
            "claim_attacked": "single-direction threshold policies place composite risk and ASN worst cases at adjacent boundary populations",
            "failure_risk": "an interior D could dominate, invalidating the two-point optimization reduction",
            "operation": "independently enumerate every canonical threshold policy for N=1..6 and every D=0..N",
            "criterion": "R stop probability nondecreasing and ASN nonincreasing in D; A directions reversed",
            "policies_examined": v3_policies,
            "adjacent_D_comparisons": v3_comparisons,
            "result": "no counterexample",
            "proof_boundary": "computational structural attack supports but does not replace the general coupling proof",
            "V4_reality_confirmation": "not_triggered_no_observed_or_reliable_real_batch_data",
            "reality_domain": "unconfirmed beyond uniform random sampling without replacement and accurate inspection",
        },
        "records": records,
        "independent_check_count": len(checks),
        "independent_checks": checks,
        "unresolved": [
            "independently reconstruct the N=23 and N=50 finite-closure frontier lower bounds or fall back to verified wide-class bounds",
            "inspection error and non-random sampling remain outside the validated reality domain",
            "S6 remains in progress and no result is yet a final frozen problem-one answer",
        ],
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s6_independent_verification_run_identity",
        "producer": "src/q1/04_verify_independent.py",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT))],
        "environment": {"python": sys.version, "platform": platform.platform()},
        "inputs": {
            str(SPEC_PATH.relative_to(PROJECT_ROOT)): sha256(SPEC_PATH),
            str(S5_RESULT_PATH.relative_to(PROJECT_ROOT)): sha256(S5_RESULT_PATH),
            str(S5_CLOSURE_PATH.relative_to(PROJECT_ROOT)): sha256(S5_CLOSURE_PATH),
        },
        "sources": {str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH)},
        "outputs": {str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH)},
        "claim_boundary": "S6 in progress; N=23 and N=50 frontier bounds are not independently reconstructed.",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(OUTPUT_PATH),
                "manifest": str(MANIFEST_PATH),
                "independent_checks": len(checks),
                "V3_policies": v3_policies,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
