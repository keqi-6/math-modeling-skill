"""Paired Q3 benchmark for the conservative contribution-window pruning.

This is a working verification artifact for SPEC-Q3-1.0.  It replays the
candidate identities stored by the current formal run, compares legacy and
pruned evaluators on identical inputs, and never overwrites formal Q3 outputs.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import solve as formal
import selection_pilot as pilot


ROOT = Path(__file__).resolve().parents[2]
DURATION_TOL_S = 2e-6
MIN_SCREEN_SPEEDUP = 1.10
MIN_PRECISE_SPEEDUP = 1.05


def decision_from_record(record: dict, fallback_source: str, index: int) -> pilot.Decision:
    return pilot.Decision(
        heading_rad=float(record["heading_rad"]),
        speed_mps=float(record["speed_mps"]),
        release_times_s=tuple(float(value) for value in record["release_times_s"]),
        fuse_delays_s=tuple(float(value) for value in record["fuse_delays_s"]),
        source=str(record.get("source", fallback_source)),
        proposal_index=int(record.get("proposal_index", index)),
    )


def timed(callable_):
    started = time.perf_counter()
    value = callable_()
    return value, time.perf_counter() - started


def interval_subset(intervals: list[list[float]], windows: list[list[float]]) -> bool:
    for left, right in intervals:
        if not any(left >= a - DURATION_TOL_S and right <= b + DURATION_TOL_S for a, b in windows):
            return False
    return True


def run(baseline_path: Path) -> dict:
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    if baseline.get("spec_id") != pilot.SPEC_ID or baseline.get("status") != "ok":
        raise RuntimeError("baseline is not a current passing SPEC-Q3-1.0 result")

    proxy_mesh = pilot.surface_mesh(pilot.PROXY["n_theta"], pilot.PROXY["n_levels"])
    screen_mesh = pilot.surface_mesh(pilot.SCREEN["n_theta"], pilot.SCREEN["n_levels"])
    precise_mesh = pilot.surface_mesh(pilot.PRECISE["n_theta"], pilot.PRECISE["n_levels"])

    proxy_groups = []
    proxy_legacy_seconds = 0.0
    proxy_pruned_seconds = 0.0
    total_legacy_points = 0
    total_pruned_points = 0
    empty_candidate_count = 0
    stored_proxy_max_abs_delta = 0.0
    for group in baseline["source_seed_records"]:
        decisions = [
            decision_from_record(item["decision"], group["source"], item["candidate_index"])
            for item in group["proxy_records"]
        ]
        legacy_records = []
        pruned_records = []
        for decision in decisions:
            value, elapsed = timed(lambda d=decision: formal.proxy_value(d, proxy_mesh, geometry_pruning=False))
            legacy_records.append(value)
            proxy_legacy_seconds += elapsed
        for decision in decisions:
            value, elapsed = timed(lambda d=decision: formal.proxy_value(d, proxy_mesh, geometry_pruning=True))
            pruned_records.append(value)
            proxy_pruned_seconds += elapsed
        total_legacy_points += sum(item["time_count"] for item in legacy_records)
        total_pruned_points += sum(item["time_count"] for item in pruned_records)
        empty_candidate_count += sum(item["time_count"] == 0 for item in pruned_records)
        stored_proxy_max_abs_delta = max(
            stored_proxy_max_abs_delta,
            max(abs(float(new["soft_score_s"]) - float(old["proxy"]["soft_score_s"]))
                for new, old in zip(legacy_records, group["proxy_records"])),
        )
        legacy_top = sorted(
            range(len(decisions)),
            key=lambda i: (-legacy_records[i]["soft_score_s"], -legacy_records[i]["grid_duration_s"], i),
        )[:12]
        pruned_top = sorted(
            range(len(decisions)),
            key=lambda i: (-pruned_records[i]["soft_score_s"], -pruned_records[i]["grid_duration_s"], i),
        )[:12]
        proxy_groups.append({
            "source": group["source"],
            "seed": group["seed"],
            "candidate_count": len(decisions),
            "legacy_top12": legacy_top,
            "pruned_top12": pruned_top,
            "top12_overlap_count": len(set(legacy_top) & set(pruned_top)),
            "legacy_time_points": int(sum(item["time_count"] for item in legacy_records)),
            "pruned_time_points": int(sum(item["time_count"] for item in pruned_records)),
            "pruned_empty_count": int(sum(item["time_count"] == 0 for item in pruned_records)),
        })

    screen_cases = []
    screen_legacy_seconds = 0.0
    screen_pruned_seconds = 0.0
    max_screen_duration_delta = 0.0
    screen_interval_subset_pass = True
    for group in baseline["source_seed_records"]:
        for ordinal, item in enumerate(group["screen_records"]):
            decision = decision_from_record(item["decision"], group["source"], item["candidate_index"])
            if ordinal % 2:
                pruned, pruned_s = timed(lambda: formal.continuous(
                    decision, pilot.SCREEN, mesh=screen_mesh, geometry_pruning=True,
                ))
                legacy, legacy_s = timed(lambda: formal.continuous(
                    decision, pilot.SCREEN, mesh=screen_mesh, geometry_pruning=False,
                ))
            else:
                legacy, legacy_s = timed(lambda: formal.continuous(
                    decision, pilot.SCREEN, mesh=screen_mesh, geometry_pruning=False,
                ))
                pruned, pruned_s = timed(lambda: formal.continuous(
                    decision, pilot.SCREEN, mesh=screen_mesh, geometry_pruning=True,
                ))
            screen_legacy_seconds += legacy_s
            screen_pruned_seconds += pruned_s
            delta = float(pruned["effective_duration_s"] - legacy["effective_duration_s"])
            max_screen_duration_delta = max(max_screen_duration_delta, abs(delta))
            windows = pruned["geometry_pruning"]["possible_windows_s"]
            subset_pass = interval_subset(pruned["intervals_s"], windows)
            screen_interval_subset_pass = screen_interval_subset_pass and subset_pass
            screen_cases.append({
                "source": group["source"],
                "seed": group["seed"],
                "candidate_index": item["candidate_index"],
                "legacy_duration_s": legacy["effective_duration_s"],
                "pruned_duration_s": pruned["effective_duration_s"],
                "duration_delta_s": delta,
                "legacy_scan_count": legacy["scan_count"],
                "pruned_scan_count": pruned["scan_count"],
                "possible_windows_s": windows,
                "interval_subset_pass": subset_pass,
            })

    best = baseline["formal_best"]["decision"]
    best_decision = decision_from_record(best, "formal_best", 0)
    precise_legacy, precise_legacy_seconds = timed(lambda: formal.continuous(
        best_decision, pilot.PRECISE, mesh=precise_mesh, geometry_pruning=False,
    ))
    precise_pruned, precise_pruned_seconds = timed(lambda: formal.continuous(
        best_decision, pilot.PRECISE, mesh=precise_mesh, geometry_pruning=True,
    ))
    precise_duration_delta = float(
        precise_pruned["effective_duration_s"] - precise_legacy["effective_duration_s"]
    )

    correctness_pass = bool(
        stored_proxy_max_abs_delta <= 1e-12
        and max_screen_duration_delta <= DURATION_TOL_S
        and abs(precise_duration_delta) <= DURATION_TOL_S
        and screen_interval_subset_pass
    )
    screen_speedup = screen_legacy_seconds / max(screen_pruned_seconds, 1e-12)
    precise_speedup = precise_legacy_seconds / max(precise_pruned_seconds, 1e-12)
    positive_benefit = bool(
        correctness_pass
        and screen_speedup >= MIN_SCREEN_SPEEDUP
        and precise_speedup >= MIN_PRECISE_SPEEDUP
    )
    return {
        "schema_version": "1.0",
        "artifact_metadata": {
            "role": "technical_documentation",
            "class": "result",
            "lifecycle": "working",
            "producer": "Q3",
            "consumers": ["Q3"],
            "purpose": "paired benchmark of safe geometry contribution-window pruning",
            "authorization_basis": "direct user request to implement and test pruning in Q3 first",
        },
        "benchmark_id": "Q3-GEOMETRY-PRUNING-PAIRED-20260828",
        "spec_id": pilot.SPEC_ID,
        "status": "pass" if correctness_pass else "fail",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "global_contribution_time_cap_s": formal.global_contribution_time_cap(),
        "acceptance": {
            "duration_tolerance_s": DURATION_TOL_S,
            "minimum_screen_speedup": MIN_SCREEN_SPEEDUP,
            "minimum_precise_speedup": MIN_PRECISE_SPEEDUP,
            "correctness_pass": correctness_pass,
            "positive_benefit": positive_benefit,
        },
        "proxy": {
            "candidate_count": int(sum(item["candidate_count"] for item in proxy_groups)),
            "legacy_seconds": proxy_legacy_seconds,
            "pruned_seconds": proxy_pruned_seconds,
            "speedup": proxy_legacy_seconds / max(proxy_pruned_seconds, 1e-12),
            "legacy_time_points": total_legacy_points,
            "pruned_time_points": total_pruned_points,
            "time_point_reduction_fraction": 1.0 - total_pruned_points / max(total_legacy_points, 1),
            "pruned_empty_candidate_count": empty_candidate_count,
            "stored_legacy_replay_max_abs_soft_score_delta": stored_proxy_max_abs_delta,
            "groups": proxy_groups,
        },
        "screen": {
            "case_count": len(screen_cases),
            "legacy_seconds": screen_legacy_seconds,
            "pruned_seconds": screen_pruned_seconds,
            "speedup": screen_speedup,
            "legacy_scan_count": int(sum(item["legacy_scan_count"] for item in screen_cases)),
            "pruned_scan_count": int(sum(item["pruned_scan_count"] for item in screen_cases)),
            "scan_reduction_fraction": 1.0 - sum(item["pruned_scan_count"] for item in screen_cases)
            / max(sum(item["legacy_scan_count"] for item in screen_cases), 1),
            "maximum_abs_duration_delta_s": max_screen_duration_delta,
            "all_intervals_inside_possible_windows": screen_interval_subset_pass,
            "cases": screen_cases,
        },
        "current_best_precise": {
            "legacy_seconds": precise_legacy_seconds,
            "pruned_seconds": precise_pruned_seconds,
            "speedup": precise_speedup,
            "legacy_scan_count": precise_legacy["scan_count"],
            "pruned_scan_count": precise_pruned["scan_count"],
            "legacy_duration_s": precise_legacy["effective_duration_s"],
            "pruned_duration_s": precise_pruned["effective_duration_s"],
            "duration_delta_s": precise_duration_delta,
            "possible_windows_s": precise_pruned["geometry_pruning"]["possible_windows_s"],
        },
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
        },
        "limitations": [
            "Runtime is a paired local-machine measurement and can vary with system load.",
            "This benchmark proves replay consistency on the stored formal candidate workload, not global search completeness.",
            "The pruning is a necessary coordinate-box test; every surviving candidate still uses the unchanged strict evaluator.",
        ],
    }


def report_text(result: dict) -> str:
    return f"""# Q3 几何剪枝配对实验

> 工作技术证据；role=`technical_documentation`，class=`result`，lifecycle=`working`。  
> 生产者与消费者：Q3。授权依据：用户要求先在 Q3 实现并验证正收益。  
> 绑定 `{result['spec_id']}`，不替代正式结果或 S5/S6 验证。

## 判定

- 几何等价性复核：`{result['acceptance']['correctness_pass']}`。
- 正收益门槛通过：`{result['acceptance']['positive_benefit']}`。
- 全局安全贡献时间上界：`{result['global_contribution_time_cap_s']:.12f} s`。

## 配对结果

| 层级 | 样本 | 旧版耗时/s | 剪枝耗时/s | 加速比 | 扫描点削减 |
|---|---:|---:|---:|---:|---:|
| 代理 | {result['proxy']['candidate_count']} | {result['proxy']['legacy_seconds']:.6f} | {result['proxy']['pruned_seconds']:.6f} | {result['proxy']['speedup']:.3f}× | {result['proxy']['time_point_reduction_fraction']:.1%} |
| 中精度 | {result['screen']['case_count']} | {result['screen']['legacy_seconds']:.6f} | {result['screen']['pruned_seconds']:.6f} | {result['screen']['speedup']:.3f}× | {result['screen']['scan_reduction_fraction']:.1%} |
| 当前最优高精度 | 1 | {result['current_best_precise']['legacy_seconds']:.6f} | {result['current_best_precise']['pruned_seconds']:.6f} | {result['current_best_precise']['speedup']:.3f}× | {1-result['current_best_precise']['pruned_scan_count']/result['current_best_precise']['legacy_scan_count']:.1%} |

- 代理回放相对原记录最大差：`{result['proxy']['stored_legacy_replay_max_abs_soft_score_delta']:.3e}`。
- 中精度新旧时长最大差：`{result['screen']['maximum_abs_duration_delta_s']:.3e} s`。
- 当前最优高精度新旧时长差：`{result['current_best_precise']['duration_delta_s']:.3e} s`。
- 剪枝后为空的代理候选：`{result['proxy']['pruned_empty_candidate_count']}`。

## 边界

剪枝只删除不可能靠近任何“导弹—圆柱点”有限线段的时间段；保留下来的时间仍调用同一完整圆柱、多烟团 `max_P min_k` 严格评价器。实验若通过，只支持把它作为 Q3 求解器的等价预筛，不支持全局最优或三弹协同存在性主张。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run(ROOT / args.baseline)
    output = ROOT / args.output
    report = ROOT / args.report
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(pilot.ready(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.write_text(report_text(result), encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "correctness_pass": result["acceptance"]["correctness_pass"],
        "positive_benefit": result["acceptance"]["positive_benefit"],
        "screen_speedup": result["screen"]["speedup"],
        "precise_speedup": result["current_best_precise"]["speedup"],
    }, ensure_ascii=False), flush=True)
    return 0 if result["acceptance"]["correctness_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
