"""High-resolution working rescore for the current Q5_v2 incumbent.

The full-horizon SCREEN result is used only as a support guard.  Every reported
SCREEN interval is expanded before PRECISE surface/time evaluation and endpoint
root reconstruction.  Progress is checkpointed after each missile.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from src.q5 import solve as q5
from src.q5_v2.objectives import from_interval_sets
from src.q5_v2.solver import ROOT, atomic_json, platform_record_decision, ready


def emit(stage: str, **payload: object) -> None:
    print(json.dumps({"stage": stage, **ready(payload)}, ensure_ascii=False), flush=True)


def write_checkpoint(path: Path, started: float, stage: str, records: list[dict[str, object]]) -> None:
    atomic_json(path, {
        "schema_version": "q5-v2-precise-checkpoint-1.0",
        "stage": stage,
        "elapsed_s": time.perf_counter() - started,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "completed_missiles": len(records),
        "records": records,
    })


def expanded(intervals: list[list[float]], pad_s: float, cap_s: float) -> list[list[float]]:
    return q5.q3.merge_intervals([
        [max(0.0, float(left) - pad_s), min(cap_s, float(right) + pad_s)]
        for left, right in intervals
    ])


def report(payload: dict[str, object]) -> str:
    metrics = payload["metrics"]
    comparison = payload["comparison_to_screen"]
    return "\n".join([
        "# Q5_v2 当前方案 PRECISE 工作复算",
        "",
        "该复算使用全时域 SCREEN 结果作为区间守卫，并对每段外扩后采用项目 PRECISE 表面网格与连续端点求根。它是工作数值证据，不等于正式 E1/E2 或全局最优证明。",
        "",
        "在全文链条中，本文件只承担最终严格复算证据：它验证选定平台计划在共享几何与连续区间口径下的四项指标，不另立模型，也不证明候选库完备或连续域全局最优。",
        "",
        f"- `J_sum = {metrics['j_sum_missile_s']:.12f}` 导弹·s；",
        f"- `J_fair = {metrics['j_fair_s']:.12f}` s；",
        f"- `J_all = {metrics['j_all_s']:.12f}` s；",
        f"- `L_all = {metrics['l_all_s']:.12f}` s；",
        f"- 逐导弹时长：`{metrics['per_missile_duration_s']}` s；",
        f"- 相对 SCREEN 的 `J_sum` 变化：`{comparison['j_sum_missile_s']:.12f}` 导弹·s；",
        f"- 相对 SCREEN 的 `J_all` 变化：`{comparison['j_all_s']:.12f}` s；",
        f"- 总耗时：`{payload['elapsed_s']:.3f}` s。",
        "",
    ])


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    input_path = ROOT / args.input_json
    output_path = ROOT / args.output_json
    report_path = ROOT / args.report_md
    checkpoint_path = ROOT / args.checkpoint_json
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    best = payload["working_best"]
    decision = platform_record_decision(best["decision"], "q5_v2_precise_rescore")
    q5.validate(decision)
    screen = best["strict_screen"]
    restricts = [
        expanded(record["intervals_s"], args.guard_pad_s, q5.arrival(missile))
        for missile, record in enumerate(screen["by_missile"])
    ]
    mesh = q5.q3.surface_mesh(q5.PRECISE["n_theta"], q5.PRECISE["n_levels"])
    emit("precise_start", surface_point_count=len(mesh.points), guard_pad_s=args.guard_pad_s,
         screen_j_sum_missile_s=screen["sum_duration_missile_s"])
    records: list[dict[str, object]] = []
    write_checkpoint(checkpoint_path, started, "started", records)
    for missile in range(3):
        emit("precise_missile_start", missile=missile + 1, restricts_s=restricts[missile])
        record = q5.solve_intervals(decision, missile, q5.PRECISE, mesh, restricts[missile])
        records.append(record)
        emit("precise_missile_complete", missile=missile + 1,
             duration_s=record["duration_s"], intervals_s=record["intervals_s"],
             scan_count=record["scan_count"], elapsed_s=time.perf_counter() - started)
        write_checkpoint(checkpoint_path, started, f"missile_{missile + 1}_complete", records)

    metrics = from_interval_sets([record["intervals_s"] for record in records])
    screen_metrics = from_interval_sets([record["intervals_s"] for record in screen["by_missile"]])
    comparison = {
        "j_sum_missile_s": metrics.j_sum_missile_s - screen_metrics.j_sum_missile_s,
        "j_fair_s": metrics.j_fair_s - screen_metrics.j_fair_s,
        "j_all_s": metrics.j_all_s - screen_metrics.j_all_s,
        "l_all_s": metrics.l_all_s - screen_metrics.l_all_s,
    }
    result: dict[str, object] = {
        "schema_version": "q5-v2-precise-working-1.0",
        "status": "working_precise_rescore_complete",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "elapsed_s": time.perf_counter() - started,
        "source_result": args.input_json,
        "source_result_sha256": q5.sha(input_path),
        "settings": dict(q5.PRECISE),
        "guard": {
            "source": "full-horizon SCREEN intervals",
            "pad_s": args.guard_pad_s,
            "restricts_s": restricts,
            "claim_boundary": "PRECISE rescoring covers all SCREEN-positive support plus padding; it is not an independent full-horizon missed-island proof",
        },
        "by_missile": records,
        "metrics": metrics.as_dict(),
        "screen_metrics": screen_metrics.as_dict(),
        "comparison_to_screen": comparison,
        "decision": q5.decision_record(decision),
        "proof_boundary": {
            "strict_continuous_endpoints": True,
            "strict_complete_cylinder_mesh": True,
            "full_horizon_screen_guard": True,
            "independent_full_horizon_precise_scan": False,
            "global_optimality": False,
        },
    }
    result["elapsed_s"] = time.perf_counter() - started
    atomic_json(output_path, result)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report(result), encoding="utf-8")
    write_checkpoint(checkpoint_path, started, "complete", records)
    emit("precise_complete", elapsed_s=result["elapsed_s"], **metrics.as_dict())
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--report-md", required=True)
    parser.add_argument("--checkpoint-json", required=True)
    parser.add_argument("--guard-pad-s", type=float, default=0.15)
    return parser.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
