"""在有限资源预算内闭合问题一完整动作空间确定性计数阈值类。

输入：output/q1/s5_results.json；命令行N列表、节点上限、单情景时间上限和对偶二分次数。
输出：output/q1/s5_finite_closure.json、output/q1/s5_finite_closure_manifest.json。
职责：用证书化分支定界证明新规范阈值类最优，或在资源上限处保留严格有效的剩余间隙。
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
    assert_scenario_metrics,
    boundary_counts,
    evaluate_threshold_policy,
    finite_threshold_branch_and_bound,
    fraction_payload,
    validate_n,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "planning/analysis/2026-08-25_q1_s4_complete_action_specification.md"
INPUT_PATH = PROJECT_ROOT / "output/q1/s5_results.json"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/s5_finite_closure.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s5_finite_closure_manifest.json"
CORE_PATH = PROJECT_ROOT / "src/q1/core.py"
SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_N_VALUES = (10, 23, 50)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_n_values(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    if not values:
        raise ValueError("N列表不能为空")
    for value in values:
        validate_n(value)
    return values


def fraction_from_payload(payload: dict[str, object]) -> Fraction:
    return Fraction(int(payload["numerator"]), int(payload["denominator"]))


def main() -> None:
    parser = argparse.ArgumentParser(description="问题一完整动作空间S5有限闭合与及时止损")
    parser.add_argument(
        "--n-list",
        default=",".join(map(str, DEFAULT_N_VALUES)),
        help="逗号分隔的待闭合夹具N，默认10,23,50",
    )
    parser.add_argument(
        "--node-limit",
        type=int,
        default=3000,
        help="每个N、每个情景最多评价的分支节点数",
    )
    parser.add_argument(
        "--time-limit-seconds",
        type=float,
        default=60.0,
        help="每个N、每个情景的墙钟秒数上限",
    )
    parser.add_argument(
        "--dual-bisection-iterations",
        type=int,
        default=20,
        help="每个分支节点用于增强严格下界的精确二分次数",
    )
    args = parser.parse_args()
    n_values = parse_n_values(args.n_list)
    if args.node_limit < 1:
        raise ValueError("节点上限必须为正整数")
    if args.time_limit_seconds <= 0:
        raise ValueError("时间上限必须为正数")
    if args.dual_bisection_iterations < 1:
        raise ValueError("节点对偶二分次数必须为正整数")

    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    input_payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if input_payload["input_identity"]["specification_sha256"] != sha256(SPEC_PATH):
        raise AssertionError("S5主结果引用的S4规格哈希已经失效")
    records_by_n = {int(record["N"]): record for record in input_payload["results"]}
    missing = [n for n in n_values if n not in records_by_n]
    if missing:
        raise ValueError(f"S5主结果缺少请求的N：{missing}")

    records: list[dict[str, object]] = []
    total_nodes = 0
    all_closed = True
    for n in n_values:
        source_record = records_by_n[n]
        d0, d1 = boundary_counts(n)
        if (d0, d1) != (int(source_record["D0"]), int(source_record["D1"])):
            raise AssertionError("输入结果的D0/D1与当前核心不一致")
        scenarios: dict[str, object] = {}
        for scenario in ("R", "A"):
            source = source_record["scenarios"][scenario]
            initial_thresholds = tuple(
                int(item["threshold"])
                for item in source["thresholds"]
            )
            wide_lower_bound = fraction_from_payload(source["dual_lower_bound"])
            closure = finite_threshold_branch_and_bound(
                n,
                scenario,
                initial_thresholds,
                node_limit=args.node_limit,
                time_limit_seconds=args.time_limit_seconds,
                dual_bisection_iterations=args.dual_bisection_iterations,
                known_global_lower_bound=wide_lower_bound,
            )
            total_nodes += closure.nodes_evaluated
            all_closed = all_closed and closure.status == "proved_deterministic_threshold_optimal"
            null_d = d0 if scenario == "R" else d1
            target_d = d1 if scenario == "R" else d0
            risk, _ = assert_scenario_metrics(n, scenario, closure.thresholds)
            exact_asn = evaluate_threshold_policy(
                n,
                target_d,
                scenario,
                closure.thresholds,
            ).asn
            if risk != closure.risk or exact_asn != closure.asn_upper_bound:
                raise AssertionError("闭合结果与独立入口精确复算不一致")
            if closure.threshold_class_lower_bound < wide_lower_bound:
                raise AssertionError("阈值类下界不应弱于输入宽类下界")
            scenarios[scenario] = {
                "scenario": scenario,
                "null_boundary_D": null_d,
                "target_boundary_D": target_d,
                "thresholds": [
                    {"t": t, "threshold": threshold}
                    for t, threshold in enumerate(closure.thresholds, start=1)
                ],
                "risk_at_composite_worst_point": fraction_payload(closure.risk),
                "ASN_upper_bound": fraction_payload(closure.asn_upper_bound),
                "input_wide_class_lower_bound": fraction_payload(wide_lower_bound),
                "deterministic_threshold_lower_bound": fraction_payload(
                    closure.threshold_class_lower_bound
                ),
                "deterministic_threshold_certified_gap": fraction_payload(
                    closure.certified_gap
                ),
                "relative_gap_upper_bound": fraction_payload(
                    closure.certified_gap / closure.asn_upper_bound
                    if closure.asn_upper_bound
                    else Fraction(0)
                ),
                "status": closure.status,
                "stop_reason": closure.stop_reason,
                "search_resources": {
                    "nodes_evaluated": closure.nodes_evaluated,
                    "nodes_expanded": closure.nodes_expanded,
                    "nodes_pruned_by_risk": closure.nodes_pruned_by_risk,
                    "nodes_pruned_by_bound": closure.nodes_pruned_by_bound,
                    "leaves_evaluated": closure.leaves_evaluated,
                    "feasible_completions_evaluated": closure.feasible_completions_evaluated,
                    "incumbent_updates": closure.incumbent_updates,
                    "dual_points_evaluated": closure.dual_points_evaluated,
                    "frontier_nodes": closure.frontier_nodes,
                    "elapsed_seconds": closure.elapsed_seconds,
                },
            }
        records.append({"N": n, "D0": d0, "D1": d1, "scenarios": scenarios})

    result_payload = {
        "schema_version": "1.0",
        "artifact_status": "s5_finite_closure_unverified",
        "claim_status": (
            "all_requested_fixtures_closed_in_threshold_class"
            if all_closed
            else "valid_reported_gaps_at_resource_limits"
        ),
        "producer": "src/q1/03_finite_closure.py",
        "consumers": [
            "future S6 independent verifier",
            "planning/analysis/2026-08-25_q1_s5_complete_action_implementation.md",
        ],
        "input_identity": {
            "input_path": str(INPUT_PATH.relative_to(PROJECT_ROOT)),
            "input_sha256": sha256(INPUT_PATH),
            "specification_path": str(SPEC_PATH.relative_to(PROJECT_ROOT)),
            "specification_sha256": sha256(SPEC_PATH),
            "n_values": list(n_values),
        },
        "parameters": {
            "node_limit": args.node_limit,
            "time_limit_seconds": args.time_limit_seconds,
            "dual_bisection_iterations": args.dual_bisection_iterations,
        },
        "arithmetic": {
            "probability_and_dynamic_programming": "fractions.Fraction exact rational arithmetic",
            "branch_and_bound_bounds": "exact Lagrangian dual lower bounds",
        },
        "results": records,
        "total_nodes_evaluated": total_nodes,
        "unresolved": [
            "S6 independent verification has not started",
            "threshold-class certificates do not cover non-threshold action classes",
            "fixture N values are not an official or user-selected business batch size",
        ],
    }
    OUTPUT_PATH.write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s5_finite_closure_run_identity",
        "producer": "src/q1/03_finite_closure.py",
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
            "n_values": list(n_values),
            "node_limit": args.node_limit,
            "time_limit_seconds": args.time_limit_seconds,
            "dual_bisection_iterations": args.dual_bisection_iterations,
        },
        "inputs": {
            str(SPEC_PATH.relative_to(PROJECT_ROOT)): sha256(SPEC_PATH),
            str(INPUT_PATH.relative_to(PROJECT_ROOT)): sha256(INPUT_PATH),
        },
        "sources": {
            str(CORE_PATH.relative_to(PROJECT_ROOT)): sha256(CORE_PATH),
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
            "src/q1/01_generate_baselines.py": sha256(PROJECT_ROOT / "src/q1/01_generate_baselines.py"),
            "src/q1/02_solve.py": sha256(PROJECT_ROOT / "src/q1/02_solve.py"),
        },
        "outputs": {
            str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH),
        },
        "claim_boundary": "This manifest identifies an S5 finite-closure run; it does not provide S6 independent verification.",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "result": str(OUTPUT_PATH),
                "manifest": str(MANIFEST_PATH),
                "N_count": len(n_values),
                "all_requested_fixtures_closed": all_closed,
                "total_nodes": total_nodes,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
