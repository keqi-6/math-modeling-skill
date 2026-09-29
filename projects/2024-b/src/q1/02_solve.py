"""生成问题一完整动作空间两个情景的S5候选、上下界与运行清单。

输入：output/q1/baselines.json；已批准S4规格；命令行Bellman二分次数。
输出：output/q1/s5_results.json、output/q1/s5_run_manifest.json。
职责：用精确有理数递推生成可行确定性阈值候选和有效对偶下界；未闭合时只报告间隙。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from core import (
    action_vector,
    assert_scenario_metrics,
    boundary_counts,
    evaluate_threshold_policy,
    fraction_payload,
    full_curve,
    solve_with_dual_search,
    validate_thresholds,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "planning/analysis/2026-08-25_q1_s4_complete_action_specification.md"
BASELINE_PATH = PROJECT_ROOT / "output/q1/baselines.json"
RESULT_PATH = PROJECT_ROOT / "output/q1/s5_results.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s5_run_manifest.json"
CORE_PATH = PROJECT_ROOT / "src/q1/core.py"
SCRIPT_PATH = Path(__file__).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fraction_from_payload(payload: dict[str, object]) -> Fraction:
    return Fraction(int(payload["numerator"]), int(payload["denominator"]))


def serialize_scenario(
    n: int,
    scenario: str,
    baselines: dict[str, dict[str, object]],
    bisection_iterations: int,
) -> tuple[dict[str, object], list[str]]:
    baseline_thresholds = {
        name: tuple(int(value) for value in record["thresholds"])
        for name, record in baselines.items()
    }
    solved = solve_with_dual_search(
        n,
        scenario,
        baseline_thresholds,
        bisection_iterations=bisection_iterations,
    )
    thresholds = tuple(int(value) for value in solved["selected_thresholds"])
    validate_thresholds(n, scenario, thresholds)
    risk, target_asn = assert_scenario_metrics(n, scenario, thresholds)
    curve = full_curve(n, scenario, thresholds)
    d0, d1 = boundary_counts(n)
    if scenario == "R":
        null_d, target_d = d0, d1
        risk_supremum = max(item.reject_probability for item in curve[: d0 + 1])
        target_asn_supremum = max(item.asn for item in curve[d1:])
        action_rule = "事实接收优先；否则x>=D1或x>=r_t拒收；其余继续；t=N按事实终点"
    else:
        null_d, target_d = d1, d0
        risk_supremum = max(item.accept_probability for item in curve[d1:])
        target_asn_supremum = max(item.asn for item in curve[: d0 + 1])
        action_rule = "x>=D1事实拒收优先；否则x<=a_t或事实接收则接收；其余继续；t=N按事实终点"
    if risk_supremum != solved["risk"]:
        raise AssertionError("全D风险上确界与边界风险不一致")
    if target_asn_supremum != solved["asn_upper_bound"]:
        raise AssertionError("全D目标ASN上确界与边界ASN不一致")

    baseline_asns = [fraction_from_payload(record["asn_at_target"]) for record in baselines.values()]
    if solved["asn_upper_bound"] > min(baseline_asns):
        raise AssertionError("选中候选没有支配输入基线")
    if len(action_vector(n, scenario, thresholds)) != (n - 1) * (n + 2) // 2:
        raise AssertionError("动作向量状态数与阈值域不一致")

    checks = [
        "threshold_domain_passed",
        "exact_boundary_risk_passed",
        "target_side_worst_point_passed",
        "factual_zero_risk_budget_passed",
        "baseline_dominance_passed",
        "mass_conservation_enforced_in_core",
        "terminal_t_equals_N_excluded_from_early_risk",
        "factual_reject_unreachable_below_D1",
        "factual_accept_unreachable_above_D0",
    ]
    serialized = {
        "scenario": scenario,
        "null_boundary_D": null_d,
        "target_boundary_D": target_d,
        "risk_limit": fraction_payload(solved["risk_limit"]),
        "execution_rule": action_rule,
        "thresholds": [
            {"t": t, "threshold": threshold}
            for t, threshold in enumerate(thresholds, start=1)
        ],
        "selected_sources": list(solved["selected_sources"]),
        "risk_at_composite_worst_point": fraction_payload(solved["risk"]),
        "worst_target_ASN_upper_bound": fraction_payload(solved["asn_upper_bound"]),
        "dual_lower_bound": fraction_payload(solved["dual_lower_bound"]),
        "certified_gap": fraction_payload(solved["certified_gap"]),
        "certificate_status": solved["certificate_status"],
        "best_multiplier": fraction_payload(solved["best_multiplier"]),
        "search_identity": {
            "method": "exact_fraction_lagrangian_bellman_dyadic_bisection",
            "bisection_iterations": bisection_iterations,
            "bellman_points_evaluated": solved["bellman_points_evaluated"],
            "nonthreshold_bellman_points": solved["nonthreshold_bellman_points"],
            "feasible_threshold_candidates": solved["feasible_threshold_candidates"],
            "coordinate_sweeps": solved["coordinate_sweeps"],
            "coordinate_evaluations": solved["coordinate_evaluations"],
            "branch_and_bound_status": (
                "not_needed_gap_closed"
                if solved["certified_gap"] == 0
                else "not_run_S5_remains_in_progress"
            ),
        },
        "full_D_audit_curve": [
            {
                "D": d,
                "early_stop_probability": fraction_payload(item.stop_probability),
                "early_accept_probability": fraction_payload(item.accept_probability),
                "early_reject_probability": fraction_payload(item.reject_probability),
                "ASN": fraction_payload(item.asn),
            }
            for d, item in enumerate(curve)
        ],
        "same_source_checks": checks,
    }
    return serialized, checks


def main() -> None:
    parser = argparse.ArgumentParser(description="求解问题一完整动作空间S5两个情景")
    parser.add_argument(
        "--bisection-iterations",
        type=int,
        default=48,
        help="Bellman对偶乘子二分次数；使用精确二进有理数，不是浮点容差",
    )
    args = parser.parse_args()
    if args.bisection_iterations < 1:
        raise ValueError("二分次数必须为正整数")
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    baseline_payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if baseline_payload["specification"]["sha256"] != sha256(SPEC_PATH):
        raise AssertionError("基线读取的S4规格哈希已经失效")

    results: list[dict[str, object]] = []
    all_checks: list[str] = []
    all_certificates_closed = True
    for record in baseline_payload["records"]:
        n = int(record["N"])
        d0, d1 = boundary_counts(n)
        if (d0, d1) != (int(record["D0"]), int(record["D1"])):
            raise AssertionError("基线中的D0/D1与当前数学核心不一致")
        scenarios: dict[str, object] = {}
        for scenario in ("R", "A"):
            serialized, checks = serialize_scenario(
                n,
                scenario,
                record["scenarios"][scenario],
                args.bisection_iterations,
            )
            scenarios[scenario] = serialized
            all_checks.extend(f"N={n}:{scenario}:{check}" for check in checks)
            if serialized["certificate_status"] != "proved_against_wide_class":
                all_certificates_closed = False
        results.append({"N": n, "D0": d0, "D1": d1, "scenarios": scenarios})

    result_payload = {
        "schema_version": "1.0",
        "artifact_status": "s5_unverified",
        "claim_status": (
            "all_fixture_candidates_have_wide_class_certificates"
            if all_certificates_closed
            else "feasible_fixture_candidates_with_valid_reported_gaps"
        ),
        "producer": "src/q1/02_solve.py",
        "consumers": [
            "future S6 independent verifier",
            "planning/analysis/2026-08-25_q1_s5_complete_action_implementation.md",
            "future docs/q1/solution_brief.md after S6",
        ],
        "input_identity": {
            "baseline_path": str(BASELINE_PATH.relative_to(PROJECT_ROOT)),
            "baseline_sha256": sha256(BASELINE_PATH),
            "specification_path": str(SPEC_PATH.relative_to(PROJECT_ROOT)),
            "specification_sha256": sha256(SPEC_PATH),
            "n_values": baseline_payload["input_identity"]["n_values"],
            "n_role": baseline_payload["input_identity"]["n_role"],
        },
        "arithmetic": {
            "probability_and_dynamic_programming": "fractions.Fraction exact rational arithmetic",
            "decimal_fields": "readability only; numerator/denominator are authoritative",
            "random_seed": None,
        },
        "results": results,
        "same_source_check_count": len(all_checks),
        "same_source_checks": all_checks,
        "unresolved": [
            "S6 independent verification has not started",
            "fixture N values are not an official or user-selected business batch size",
            "when certified_gap is positive, deterministic threshold global optimality is not proved",
            "reality validity under inspection error or non-random sampling remains unconfirmed",
        ],
    }
    RESULT_PATH.write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s5_run_identity",
        "producer": "src/q1/02_solve.py",
        "consumers": ["future S6 independent verifier", "project audit"],
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT)), *sys.argv[1:]],
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "random_seed": None,
        },
        "parameters": {
            "bisection_iterations": args.bisection_iterations,
            "n_values": baseline_payload["input_identity"]["n_values"],
        },
        "inputs": {
            str(SPEC_PATH.relative_to(PROJECT_ROOT)): sha256(SPEC_PATH),
            str(BASELINE_PATH.relative_to(PROJECT_ROOT)): sha256(BASELINE_PATH),
        },
        "sources": {
            str(CORE_PATH.relative_to(PROJECT_ROOT)): sha256(CORE_PATH),
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
            "src/q1/01_generate_baselines.py": sha256(PROJECT_ROOT / "src/q1/01_generate_baselines.py"),
        },
        "outputs": {
            str(RESULT_PATH.relative_to(PROJECT_ROOT)): sha256(RESULT_PATH),
        },
        "claim_boundary": "This manifest identifies an S5 run; it does not provide S6 independent verification.",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "result": str(RESULT_PATH),
                "manifest": str(MANIFEST_PATH),
                "N_count": len(results),
                "all_fixture_certificates_closed": all_certificates_closed,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
