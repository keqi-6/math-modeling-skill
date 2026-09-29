"""Paired Q1/Q2 benchmark for the safe geometry time-window backport."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/q1"))
sys.path.insert(0, str(ROOT / "src/q2"))

import model as q1  # noqa: E402
import reselection_pilot as q2  # noqa: E402


LEGACY_Q1 = {
    "result_sha256": "1687e971ba6a5852023e84ac8f96adfc9659b20097f3db07deab4ed5fddc1938",
    "duration_s": 1.391642668485641,
}
LEGACY_Q2 = {
    "result_sha256": "721537914e17404145fa25131bf489776dbc2820444b1b7ae70003ba2069eb88",
    "duration_s": 4.581608247160911,
    "elapsed_seconds": 180.59774718200015,
    "decision": {
        "heading_rad": 0.10700711450221934,
        "speed_mps": 89.48702874013804,
        "release_time_s": 0.4683560670671222,
        "fuse_delay_s": 0.6909391553755698,
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def timed(function):
    started = time.perf_counter()
    value = function()
    return value, time.perf_counter() - started


def interval_delta(left: list[list[float]], right: list[list[float]]) -> float:
    if len(left) != len(right):
        return float("inf")
    return max((abs(float(a) - float(b)) for x, y in zip(left, right) for a, b in zip(x, y)), default=0.0)


def decision_from_record(record: dict, source: str) -> q2.Decision:
    return q2.Decision(
        heading_rad=float(record["heading_rad"]),
        speed_mps=float(record["speed_mps"]),
        release_time_s=float(record["release_time_s"]),
        fuse_delay_s=float(record["fuse_delay_s"]),
        source_domain=source,
    )


def q1_pair() -> dict:
    parameters = q1.default_parameters()
    settings = {"scan_step": 0.01, "n_theta": 512}
    full, full_elapsed = timed(lambda: q1.solve_intervals(parameters, **settings, geometry_pruning=False))
    pruned, pruned_elapsed = timed(lambda: q1.solve_intervals(parameters, **settings, geometry_pruning=True))
    return {
        "settings": settings,
        "full": {"elapsed_seconds": full_elapsed, "scan_count": full["scan_count"], "duration_s": full["effective_duration_s"], "intervals_s": full["intervals_s"]},
        "pruned": {"elapsed_seconds": pruned_elapsed, "scan_count": pruned["scan_count"], "duration_s": pruned["effective_duration_s"], "intervals_s": pruned["intervals_s"], "geometry_pruning": pruned["geometry_pruning"]},
        "comparison": {
            "duration_delta_s": abs(float(full["effective_duration_s"]) - float(pruned["effective_duration_s"])),
            "maximum_endpoint_delta_s": interval_delta(full["intervals_s"], pruned["intervals_s"]),
            "scan_reduction_fraction": 1.0 - pruned["scan_count"] / full["scan_count"],
            "speedup": full_elapsed / pruned_elapsed,
        },
    }


def q2_pair(label: str, decision: q2.Decision) -> dict:
    full_proxy, full_proxy_elapsed = timed(lambda: q2.proxy_score_record(decision, geometry_pruning=False))
    pruned_proxy, pruned_proxy_elapsed = timed(lambda: q2.proxy_score_record(decision, geometry_pruning=True))
    full, full_elapsed = timed(lambda: q2.evaluate(decision, {"scan_step_s": 0.02, "n_theta": 128, "n_levels": 17}, geometry_pruning=False))
    pruned, pruned_elapsed = timed(lambda: q2.evaluate(decision, {"scan_step_s": 0.02, "n_theta": 128, "n_levels": 17}, geometry_pruning=True))
    return {
        "label": label,
        "decision": q2.decision_record(decision),
        "proxy": {
            "full": {**full_proxy, "elapsed_seconds": full_proxy_elapsed},
            "pruned": {**pruned_proxy, "elapsed_seconds": pruned_proxy_elapsed},
            "score_delta_s": abs(float(full_proxy["score_s"]) - float(pruned_proxy["score_s"])),
            "speedup": full_proxy_elapsed / pruned_proxy_elapsed,
        },
        "screen": {
            "full": {"elapsed_seconds": full_elapsed, "scan_count": full["scan_count"], "duration_s": full["effective_duration_s"], "intervals_s": full["intervals_s"]},
            "pruned": {"elapsed_seconds": pruned_elapsed, "scan_count": pruned["scan_count"], "duration_s": pruned["effective_duration_s"], "intervals_s": pruned["intervals_s"], "geometry_pruning": pruned["geometry_pruning"]},
            "duration_delta_s": abs(float(full["effective_duration_s"]) - float(pruned["effective_duration_s"])),
            "maximum_endpoint_delta_s": interval_delta(full["intervals_s"], pruned["intervals_s"]),
            "scan_reduction_fraction": 1.0 - pruned["scan_count"] / full["scan_count"],
            "speedup": full_elapsed / pruned_elapsed,
        },
    }


def report_text(result: dict) -> str:
    q1_result = result["q1_pair"]
    lines = [
        "# Q1/Q2 几何时间窗剪枝配对基准",
        "",
        "> 同一候选、同一完整几何求值器，仅切换 `geometry_pruning`；计时含窗口构造开销。代理分数因积分域从完整有效窗改为严格可能窗而允许变化，正式连续时长必须保持。",
        "",
        "## Q1 固定方案",
        "",
        f"- 可能窗：`{q1_result['pruned']['geometry_pruning']['possible_window_s']}` s；扫描点减少 `{100*q1_result['comparison']['scan_reduction_fraction']:.2f}%`。",
        f"- 连续时长差：`{q1_result['comparison']['duration_delta_s']:.3e} s`；端点最大差：`{q1_result['comparison']['maximum_endpoint_delta_s']:.3e} s`。",
        f"- 本机配对耗时：`{q1_result['full']['elapsed_seconds']:.6f} → {q1_result['pruned']['elapsed_seconds']:.6f} s`，加速 `{q1_result['comparison']['speedup']:.3f}×`。",
        "",
        "## Q2 候选",
        "",
    ]
    for item in result["q2_pairs"]:
        screen = item["screen"]
        lines.extend([
            f"- `{item['label']}`：可能窗 `{screen['pruned']['geometry_pruning']['possible_window_s']}` s，扫描点减少 `{100*screen['scan_reduction_fraction']:.2f}%`，时长差 `{screen['duration_delta_s']:.3e} s`，端点差 `{screen['maximum_endpoint_delta_s']:.3e} s`，筛选加速 `{screen['speedup']:.3f}×`。",
        ])
    lines.extend([
        "",
        "## 边界",
        "",
        "该基准证明当前配对候选的实现等价性和计算收益；它不提供全局最优性证明。正式端到端运行的旧/新耗时与最终最优值另保存在 `formal_run_comparison`。",
    ])
    return "\n".join(lines) + "\n"


def run(output: Path, report: Path) -> dict:
    current = json.loads((ROOT / "docs/q2_result.json").read_text(encoding="utf-8"))
    current_best = current["formal_best"]["decision"]
    candidates = [
        ("legacy_formal_best", decision_from_record(LEGACY_Q2["decision"], "benchmark_legacy")),
        ("current_formal_best", decision_from_record(current_best, "benchmark_current")),
    ]
    result = {
        "schema_version": "1.0",
        "status": "ok",
        "role": "paired_internal_benchmark",
        "legacy": {"q1": LEGACY_Q1, "q2": LEGACY_Q2},
        "q1_pair": q1_pair(),
        "q2_pairs": [q2_pair(label, decision) for label, decision in candidates],
        "formal_run_comparison": {
            "legacy_q2_elapsed_seconds": LEGACY_Q2["elapsed_seconds"],
            "legacy_q2_duration_s": LEGACY_Q2["duration_s"],
            "current_q2_elapsed_seconds": current["run_identity"]["elapsed_seconds"],
            "current_q2_duration_s": current["formal_best"]["precise"]["effective_duration_s"],
            "duration_delta_s": float(current["formal_best"]["precise"]["effective_duration_s"]) - LEGACY_Q2["duration_s"],
            "speedup": LEGACY_Q2["elapsed_seconds"] / float(current["run_identity"]["elapsed_seconds"]),
        },
        "identities": {
            "q1_model_sha256": sha256(ROOT / "src/q1/model.py"),
            "q2_reselection_sha256": sha256(ROOT / "src/q2/reselection_pilot.py"),
            "q2_result_sha256": sha256(ROOT / "docs/q2_result.json"),
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.write_text(report_text(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("docs/q12_geometry_pruning_benchmark.json"))
    parser.add_argument("--report", type=Path, default=Path("docs/q12_geometry_pruning_benchmark.md"))
    args = parser.parse_args()
    result = run(ROOT / args.output, ROOT / args.report)
    print(json.dumps({"status": result["status"], "output": args.output.as_posix(), "report": args.report.as_posix()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
