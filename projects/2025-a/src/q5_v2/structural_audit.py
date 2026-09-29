"""Finite structural audit for the current Q5_v2 incumbent.

The audit is deliberately bounded: leave-one-bomb/platform-out ablations and
an existing-library FY1 multi-bomb replacement check.  It does not optimize a
new continuous model and does not claim global optimality.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Iterable, Mapping, Sequence

from src.q5 import solve as q5
from src.q5_v2.objectives import ObjectiveMetrics, from_interval_sets, from_q5_evaluation, normalize_intervals
from src.q5_v2 import solver


ROOT = Path(__file__).resolve().parents[2]
SCREEN_PRIMARY_TOLERANCE = float(q5.RANK_TOLERANCE[q5.SCREEN["name"]])


def emit(stage: str, **payload: object) -> None:
    print(json.dumps({"stage": stage, **solver.ready(payload)}, ensure_ascii=False), flush=True)


def checkpoint(path: Path, started: float, stage: str, **payload: object) -> None:
    solver.atomic_json(path, {
        "schema_version": "q5-v2-structural-audit-checkpoint-1.0",
        "stage": stage,
        "elapsed_s": time.perf_counter() - started,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        **payload,
    })


def interval_difference(
    minuend: Iterable[Sequence[float]],
    subtrahend: Iterable[Sequence[float]],
    *,
    tolerance_s: float = 1e-10,
) -> tuple[tuple[float, float], ...]:
    """Return the normalized interval-set difference."""

    base = normalize_intervals(minuend, tolerance_s=tolerance_s)
    removed = normalize_intervals(subtrahend, tolerance_s=tolerance_s)
    result: list[tuple[float, float]] = []
    for left, right in base:
        cursor = left
        for cut_left, cut_right in removed:
            if cut_right <= cursor + tolerance_s:
                continue
            if cut_left >= right - tolerance_s:
                break
            if cut_left > cursor + tolerance_s:
                result.append((cursor, min(cut_left, right)))
            cursor = max(cursor, cut_right)
            if cursor >= right - tolerance_s:
                break
        if cursor < right - tolerance_s:
            result.append((cursor, right))
    return normalize_intervals(result, tolerance_s=tolerance_s)


def remove_bombs(decision: q5.Decision, removed_indices: set[int], source: str) -> q5.Decision:
    bombs = tuple(bomb for index, bomb in enumerate(decision.bombs) if index not in removed_indices)
    candidate = q5.Decision(decision.headings_rad, decision.speeds_mps, bombs, source)
    q5.validate(candidate)
    return candidate


def replace_platform_plan(
    decision: q5.Decision, column: solver.PlatformColumn, source: str
) -> q5.Decision:
    headings = list(decision.headings_rad)
    speeds = list(decision.speeds_mps)
    headings[column.platform] = column.heading_rad
    speeds[column.platform] = column.speed_mps
    bombs = tuple(
        [bomb for bomb in decision.bombs if bomb.platform != column.platform]
        + list(column.bombs)
    )
    candidate = q5.Decision(tuple(headings), tuple(speeds), bombs, source)
    q5.validate(candidate)
    return candidate


def bomb_rows(decision: q5.Decision) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for global_index, bomb in enumerate(decision.bombs):
        platform_bombs = q5.by_platform(decision, bomb.platform)
        local_number = next(
            number for number, item in enumerate(platform_bombs, 1) if item == bomb
        )
        rows.append({
            "global_index": global_index,
            "bomb_id": f"{q5.NAMES[bomb.platform]}-B{local_number}",
            "platform": q5.NAMES[bomb.platform],
            "platform_index": bomb.platform,
            "bomb_number": local_number,
            "label": q5.MISSILE_NAMES[bomb.label],
            "release_s": bomb.release_s,
            "fuse_s": bomb.fuse_s,
            "explosion_time_s": q5.explosion_time(bomb),
        })
    return rows


def metric_loss(baseline: ObjectiveMetrics, candidate: ObjectiveMetrics) -> dict[str, object]:
    return {
        "per_missile_duration_s": [
            base - value
            for base, value in zip(baseline.per_missile_duration_s, candidate.per_missile_duration_s)
        ],
        "j_sum_missile_s": baseline.j_sum_missile_s - candidate.j_sum_missile_s,
        "j_fair_s": baseline.j_fair_s - candidate.j_fair_s,
        "j_all_s": baseline.j_all_s - candidate.j_all_s,
        "l_all_s": baseline.l_all_s - candidate.l_all_s,
    }


def ablation_record(
    baseline: ObjectiveMetrics,
    candidate: q5.Decision,
    evaluation: Mapping[str, object],
) -> dict[str, object]:
    metrics = from_q5_evaluation(evaluation)
    losses = metric_loss(baseline, metrics)
    maximum_monotonicity_violation = max(
        [metrics.j_sum_missile_s - baseline.j_sum_missile_s]
        + [
            value - base
            for value, base in zip(metrics.per_missile_duration_s, baseline.per_missile_duration_s)
        ]
    )
    if maximum_monotonicity_violation > SCREEN_PRIMARY_TOLERANCE:
        raise RuntimeError(
            f"resource deletion increased a monotone metric by {maximum_monotonicity_violation}"
        )
    lost_intervals = [
        [list(interval) for interval in interval_difference(base, subset)]
        for base, subset in zip(
            baseline.per_missile_intervals_s, metrics.per_missile_intervals_s
        )
    ]
    return {
        "metrics": metrics.as_dict(),
        "loss_from_comparable_baseline": losses,
        "positive_primary_marginal_at_screen": (
            losses["j_sum_missile_s"] > SCREEN_PRIMARY_TOLERANCE
        ),
        "lost_intervals_by_missile_s": lost_intervals,
        "constraint_margins": q5.constraint_margins(candidate),
        "monotonicity_max_violation_missile_s": maximum_monotonicity_violation,
    }


def comparable_restricts(precise_payload: Mapping[str, object]) -> list[list[list[float]]]:
    metrics = precise_payload["metrics"]
    return [
        [list(map(float, interval)) for interval in intervals]
        for intervals in metrics["per_missile_intervals_s"]
    ]


def screen_metrics(
    decision: q5.Decision,
    mesh: object,
    restricts: Sequence[Sequence[Sequence[float]]] | None,
) -> tuple[dict[str, object], ObjectiveMetrics]:
    evaluation = q5.evaluate(decision, q5.SCREEN, mesh, restricts)
    return evaluation, from_q5_evaluation(evaluation)


def precise_confirmation(
    decision: q5.Decision,
    restricts: Sequence[Sequence[Sequence[float]]],
    baseline_precise: ObjectiveMetrics,
) -> dict[str, object]:
    mesh = q5.q3.surface_mesh(q5.PRECISE["n_theta"], q5.PRECISE["n_levels"])
    evaluation = q5.evaluate(decision, q5.PRECISE, mesh, restricts)
    metrics = from_q5_evaluation(evaluation)
    return {
        "settings": dict(q5.PRECISE),
        "metrics": metrics.as_dict(),
        "loss_from_precise_baseline": metric_loss(baseline_precise, metrics),
        "proof_boundary": "restricted to the baseline PRECISE interval union; safe only for resource-deletion monotonicity",
    }


def markdown(payload: Mapping[str, object]) -> str:
    baseline = payload["comparable_screen_baseline"]["metrics"]
    precise = payload["precise_baseline"]["metrics"]
    lines = [
        "# Q5_v2 当前 13 枚弹方案有限结构审计",
        "",
        "本审计只检验当前固定方案的删除边际和现有 FY1 多弹计划族，不扩大主求解器，也不声称连续域全局最优。",
        "",
        "## 基线与口径",
        "",
        f"- PRECISE 工作基线：`J_sum={precise['j_sum_missile_s']:.12f}` 导弹·s；",
        f"- 同层可比 SCREEN 基线：`J_sum={baseline['j_sum_missile_s']:.12f}` 导弹·s；",
        f"- SCREEN 正边际判据：`Delta J_sum > {payload['screen_primary_tolerance_missile_s']}` 导弹·s。",
        "",
        "## 逐弹删除",
        "",
        "| 烟幕弹 | 标签 | ΔJ_sum/(导弹·s) | 逐导弹损失/s | ΔJ_all/s | SCREEN 正边际 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in payload["bomb_ablation"]:
        loss = row["loss_from_comparable_baseline"]
        per = ", ".join(f"{value:.6f}" for value in loss["per_missile_duration_s"])
        lines.append(
            f"| {row['bomb_id']} | {row['label']} | {loss['j_sum_missile_s']:.6f} | {per} | {loss['j_all_s']:.6f} | {'是' if row['positive_primary_marginal_at_screen'] else '否'} |"
        )
    lines.extend([
        "",
        "## 逐平台删除",
        "",
        "| 平台 | 删除弹数 | ΔJ_sum/(导弹·s) | 逐导弹损失/s | ΔJ_all/s | SCREEN 正边际 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for row in payload["platform_ablation"]:
        loss = row["loss_from_comparable_baseline"]
        per = ", ".join(f"{value:.6f}" for value in loss["per_missile_duration_s"])
        lines.append(
            f"| {row['platform']} | {row['removed_bomb_count']} | {loss['j_sum_missile_s']:.6f} | {per} | {loss['j_all_s']:.6f} | {'是' if row['positive_primary_marginal_at_screen'] else '否'} |"
        )
    capacity = payload["capacity_audit"]
    lines.extend([
        "",
        "## 空槽与现有候选族检查",
        "",
        f"当前共使用 `{capacity['used_bombs']}/15` 个槽位；未使用槽位为 `{capacity['unused_slots']}` 个，均位于 FY1。",
        "",
        f"现有确定性列库中 FY1 多弹计划共 `{payload['fy1_multibomb_replacement']['candidate_count']}` 个；严格 SCREEN 复算 `{len(payload['fy1_multibomb_replacement']['strict_candidates'])}` 个代理排名靠前方案。",
    ])
    best_delta = payload["fy1_multibomb_replacement"]["best_screen_delta_j_sum_missile_s"]
    if best_delta is None:
        lines.append("未完成 FY1 多弹严格候选复算。")
    elif best_delta > SCREEN_PRIMARY_TOLERANCE:
        lines.append(f"发现现有计划族内的 SCREEN 改善反例，最佳 `Delta J_sum={best_delta:.6f}` 导弹·s；当前候选需重新精确复核。")
    else:
        lines.append(f"未发现现有计划族内的 SCREEN 改善；最佳 `Delta J_sum={best_delta:.6f}` 导弹·s。该结论不覆盖连续加弹域。")
    lines.extend([
        "",
        "## 结论边界",
        "",
        payload["conclusion"]["summary"],
        "",
        payload["conclusion"]["claim_boundary"],
        "",
    ])
    confirmation = payload.get("precise_confirmation")
    if confirmation:
        loss = confirmation["result"]["loss_from_precise_baseline"]
        lines.insert(-2, f"PRECISE 定向确认对象为 `{confirmation['target']}`，其 `Delta J_sum={loss['j_sum_missile_s']:.12f}` 导弹·s。")
        lines.insert(-2, "")
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    deadline = started + args.wall_time_s
    precise_path = ROOT / args.input_precise
    result_path = ROOT / args.input_result
    output_path = ROOT / args.output_json
    report_path = ROOT / args.report_md
    checkpoint_path = ROOT / args.checkpoint_json

    precise_payload = json.loads(precise_path.read_text(encoding="utf-8"))
    result_payload = json.loads(result_path.read_text(encoding="utf-8"))
    decision = solver.platform_record_decision(precise_payload["decision"], "q5_v2_structural_audit")
    q5.validate(decision)
    if len(decision.bombs) != 13:
        raise RuntimeError(f"expected 13 bombs, found {len(decision.bombs)}")
    precise_metrics = from_interval_sets(precise_payload["metrics"]["per_missile_intervals_s"])
    if abs(precise_metrics.j_sum_missile_s - float(precise_payload["metrics"]["j_sum_missile_s"])) > 1e-9:
        raise RuntimeError("precise metrics identity mismatch")
    restricts = comparable_restricts(precise_payload)
    screen_mesh = q5.q3.surface_mesh(q5.SCREEN["n_theta"], q5.SCREEN["n_levels"])

    emit("audit_start", wall_time_s=args.wall_time_s, bomb_count=len(decision.bombs))
    comparable_evaluation, comparable_metrics = screen_metrics(decision, screen_mesh, restricts)
    emit("comparable_baseline_complete", j_sum_missile_s=comparable_metrics.j_sum_missile_s)
    checkpoint(checkpoint_path, started, "comparable_baseline_complete",
               completed_bomb_ablations=0, completed_platform_ablations=0)

    rows = bomb_rows(decision)
    bomb_ablation: list[dict[str, object]] = []
    bomb_by_id: dict[str, dict[str, object]] = {}
    for row in rows:
        if time.perf_counter() >= deadline - 15.0:
            raise RuntimeError("wall-time guard reached before all bomb ablations completed")
        candidate = remove_bombs(decision, {int(row["global_index"])}, f"remove_{row['bomb_id']}")
        evaluation, _ = screen_metrics(candidate, screen_mesh, restricts)
        record = {**row, **ablation_record(comparable_metrics, candidate, evaluation)}
        bomb_ablation.append(record)
        bomb_by_id[str(row["bomb_id"])] = record
        emit("bomb_ablation_complete", bomb_id=row["bomb_id"],
             delta_j_sum_missile_s=record["loss_from_comparable_baseline"]["j_sum_missile_s"],
             completed=len(bomb_ablation), total=len(rows))
        checkpoint(checkpoint_path, started, "bomb_ablation",
                   completed_bomb_ablations=len(bomb_ablation), last_bomb_id=row["bomb_id"])

    platform_ablation: list[dict[str, object]] = []
    for platform in range(5):
        indices = {index for index, bomb in enumerate(decision.bombs) if bomb.platform == platform}
        if len(indices) == 1:
            only_index = next(iter(indices))
            base_row = next(row for row in rows if row["global_index"] == only_index)
            record = {
                "platform": q5.NAMES[platform],
                "platform_index": platform,
                "removed_bomb_count": 1,
                "reused_bomb_ablation": base_row["bomb_id"],
                **{
                    key: value for key, value in bomb_by_id[str(base_row["bomb_id"])].items()
                    if key in {
                        "metrics", "loss_from_comparable_baseline",
                        "positive_primary_marginal_at_screen", "lost_intervals_by_missile_s",
                        "constraint_margins", "monotonicity_max_violation_missile_s",
                    }
                },
            }
        else:
            if time.perf_counter() >= deadline - 12.0:
                raise RuntimeError("wall-time guard reached before all platform ablations completed")
            candidate = remove_bombs(decision, indices, f"remove_{q5.NAMES[platform]}")
            evaluation, _ = screen_metrics(candidate, screen_mesh, restricts)
            record = {
                "platform": q5.NAMES[platform],
                "platform_index": platform,
                "removed_bomb_count": len(indices),
                "reused_bomb_ablation": None,
                **ablation_record(comparable_metrics, candidate, evaluation),
            }
        platform_ablation.append(record)
        emit("platform_ablation_complete", platform=q5.NAMES[platform],
             delta_j_sum_missile_s=record["loss_from_comparable_baseline"]["j_sum_missile_s"],
             completed=len(platform_ablation), total=5)
        checkpoint(checkpoint_path, started, "platform_ablation",
                   completed_bomb_ablations=13,
                   completed_platform_ablations=len(platform_ablation),
                   last_platform=q5.NAMES[platform])

    counts = [len(q5.by_platform(decision, platform)) for platform in range(5)]
    capacity = {
        "used_bombs": len(decision.bombs),
        "total_capacity": 15,
        "unused_slots": 15 - len(decision.bombs),
        "by_platform": [
            {
                "platform": q5.NAMES[platform],
                "used": count,
                "unused": 3 - count,
            }
            for platform, count in enumerate(counts)
        ],
        "constraint_margins": q5.constraint_margins(decision),
    }
    emit("capacity_audit_complete", used_bombs=capacity["used_bombs"],
         unused_slots=capacity["unused_slots"])

    replacement: dict[str, object] = {
        "scope": "existing deterministic FY1 complete-plan library; FY2-FY5 fixed",
        "candidate_count": 0,
        "proxy_candidates": [],
        "strict_candidates": [],
        "best_screen_delta_j_sum_missile_s": None,
        "continuous_add_bomb_domain_exhausted": False,
    }
    if time.perf_counter() < deadline - 12.0:
        seeds, _ = solver.load_seed_decisions()
        columns = [
            column for column in solver.generate_columns(seeds)
            if column.platform == 0 and len(column.bombs) >= 2
        ]
        unique: dict[tuple[object, ...], solver.PlatformColumn] = {}
        for column in columns:
            unique.setdefault(solver.column_signature(column), column)
        columns = list(unique.values())
        replacement["candidate_count"] = len(columns)
        emit("fy1_multibomb_library_complete", candidate_count=len(columns))
        if columns:
            times, weights = solver.time_nodes(0.2)
            proxy_mesh = q5.q3.surface_mesh(24, 5)
            missiles, visible = solver.visible_masks(times, proxy_mesh)
            ranked: list[tuple[tuple[float, float, float], q5.Decision, solver.PlatformColumn, dict[str, object]]] = []
            for index, column in enumerate(columns):
                candidate = replace_platform_plan(decision, column, f"fy1_multibomb_{index}")
                proxy, _ = solver.decision_proxy(candidate, times, proxy_mesh, missiles, visible, weights)
                ranked.append((solver.proxy_key(proxy), candidate, column, proxy))
            ranked.sort(key=lambda item: item[0], reverse=True)
            replacement["proxy_candidates"] = [
                {
                    "rank": rank,
                    "column": asdict(column),
                    "proxy": proxy,
                }
                for rank, (_, _, column, proxy) in enumerate(ranked[:5], 1)
            ]
            current_full_screen = from_q5_evaluation(result_payload["working_best"]["strict_screen"])
            strict_candidates: list[dict[str, object]] = []
            for rank, (_, candidate, column, proxy) in enumerate(ranked[:3], 1):
                if time.perf_counter() >= deadline - 8.0:
                    break
                evaluation = q5.evaluate(candidate, q5.SCREEN, screen_mesh)
                metrics = from_q5_evaluation(evaluation)
                delta = metrics.j_sum_missile_s - current_full_screen.j_sum_missile_s
                strict_candidates.append({
                    "rank": rank,
                    "column": asdict(column),
                    "proxy": proxy,
                    "metrics": metrics.as_dict(),
                    "delta_from_current_full_screen": {
                        "j_sum_missile_s": delta,
                        "j_fair_s": metrics.j_fair_s - current_full_screen.j_fair_s,
                        "j_all_s": metrics.j_all_s - current_full_screen.j_all_s,
                        "l_all_s": metrics.l_all_s - current_full_screen.l_all_s,
                    },
                    "decision": q5.decision_record(candidate),
                })
                emit("fy1_multibomb_screen_complete", rank=rank,
                     delta_j_sum_missile_s=delta,
                     bomb_count=len(candidate.bombs))
                checkpoint(checkpoint_path, started, "fy1_multibomb_screen",
                           completed_bomb_ablations=13, completed_platform_ablations=5,
                           completed_fy1_candidates=len(strict_candidates))
            replacement["strict_candidates"] = strict_candidates
            if strict_candidates:
                replacement["best_screen_delta_j_sum_missile_s"] = max(
                    row["delta_from_current_full_screen"]["j_sum_missile_s"]
                    for row in strict_candidates
                )

    precise_result = None
    precise_status = "PRECISE_CONFIRMATION_SKIPPED_BUDGET"
    elapsed_before_precise = time.perf_counter() - started
    if deadline - time.perf_counter() >= 34.0:
        improving = [
            row for row in replacement["strict_candidates"]
            if row["delta_from_current_full_screen"]["j_sum_missile_s"] > SCREEN_PRIMARY_TOLERANCE
        ]
        if improving:
            # Add-resource candidates are not monotone subsets, so a full-horizon
            # PRECISE confirmation would require a fresh SCREEN guard.  Keep this
            # working audit bounded and report the counterexample for the next run.
            precise_status = "PRECISE_CONFIRMATION_DEFERRED_ADD_CANDIDATE"
        else:
            target = min(
                bomb_ablation,
                key=lambda row: row["loss_from_comparable_baseline"]["j_sum_missile_s"],
            )
            candidate = remove_bombs(decision, {int(target["global_index"])}, f"precise_remove_{target['bomb_id']}")
            emit("precise_confirmation_start", target=target["bomb_id"],
                 remaining_budget_s=deadline - time.perf_counter())
            precise_result = {
                "target": target["bomb_id"],
                "kind": "leave_one_bomb_out",
                "result": precise_confirmation(candidate, restricts, precise_metrics),
            }
            precise_status = "PRECISE_CONFIRMATION_COMPLETE"
            emit("precise_confirmation_complete", target=target["bomb_id"],
                 delta_j_sum_missile_s=precise_result["result"]["loss_from_precise_baseline"]["j_sum_missile_s"])

    all_bombs_positive = len(bomb_ablation) == 13 and all(
        row["positive_primary_marginal_at_screen"] for row in bomb_ablation
    )
    all_platforms_positive = len(platform_ablation) == 5 and all(
        row["positive_primary_marginal_at_screen"] for row in platform_ablation
    )
    best_add_delta = replacement["best_screen_delta_j_sum_missile_s"]
    add_counterexample = best_add_delta is not None and best_add_delta > SCREEN_PRIMARY_TOLERANCE
    if add_counterexample:
        summary = "逐弹和逐平台删除结果已完成，但现有 FY1 多弹计划族出现 SCREEN 改善反例；当前候选不应直接晋升，须先对该反例作高精度复核。"
    elif all_bombs_positive and all_platforms_positive:
        summary = "在固定其余参数和统一 SCREEN 严格口径下，13 枚烟幕弹及 5 个平台均具有可分辨的题意主目标删除边际；现有 FY1 多弹计划族未发现简单改善。"
    else:
        summary = "至少存在一个烟幕弹或平台在 SCREEN 层没有可分辨的题意主目标删除边际，当前资源必要性表述必须收窄。"

    payload: dict[str, object] = {
        "schema_version": "q5-v2-structural-audit-1.0",
        "status": "working_structural_audit_complete",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "elapsed_s": time.perf_counter() - started,
        "inputs": {
            args.input_precise: q5.sha(precise_path),
            args.input_result: q5.sha(result_path),
        },
        "risk": {
            "primary": "resource redundancy or a simple unused-slot improvement in the existing deterministic FY1 plan family",
            "selected_checks": ["constraint_verification", "leave_one_out_counterexample", "finite_unused_slot_counterexample"],
            "excluded_checks": {
                "limit_case": "not informative for the current 13-bomb resource structure",
                "parameter_sensitivity": "reserved for later E2/E4; this step isolates resource deletion",
                "reality_fit": "no empirical deployment model is introduced in this working E3 audit",
            },
        },
        "screen_primary_tolerance_missile_s": SCREEN_PRIMARY_TOLERANCE,
        "precise_baseline": {
            "metrics": precise_metrics.as_dict(),
            "settings": precise_payload["settings"],
        },
        "comparable_screen_baseline": {
            "metrics": comparable_metrics.as_dict(),
            "settings": dict(q5.SCREEN),
            "evaluation": comparable_evaluation,
            "restriction": "exact baseline PRECISE interval unions; valid for deletion monotonicity",
        },
        "bomb_ablation": bomb_ablation,
        "platform_ablation": platform_ablation,
        "capacity_audit": capacity,
        "fy1_multibomb_replacement": replacement,
        "precise_confirmation_status": precise_status,
        "precise_confirmation": precise_result,
        "timing": {
            "wall_time_budget_s": args.wall_time_s,
            "elapsed_before_precise_s": elapsed_before_precise,
            "elapsed_total_s": time.perf_counter() - started,
        },
        "conclusion": {
            "all_13_bombs_positive_primary_marginal_at_screen": all_bombs_positive,
            "all_5_platforms_positive_primary_marginal_at_screen": all_platforms_positive,
            "fy1_existing_library_improvement_counterexample": add_counterexample,
            "summary": summary,
            "claim_boundary": "逐项删除只支持其余参数固定时的局部必要性；有限 FY1 计划库没有穷尽连续加弹域，且只有明确列出的删除对象取得 PRECISE 确认。",
        },
        "proof_boundary": {
            "formal_e3_pass": False,
            "working_structural_evidence": True,
            "global_optimality": False,
            "continuous_add_bomb_domain_exhausted": False,
        },
    }
    payload["elapsed_s"] = time.perf_counter() - started
    payload["timing"]["elapsed_total_s"] = payload["elapsed_s"]
    solver.atomic_json(output_path, payload)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown(payload), encoding="utf-8")
    checkpoint(checkpoint_path, started, "complete",
               output_json=args.output_json, report_md=args.report_md,
               conclusion=payload["conclusion"],
               precise_confirmation_status=precise_status)
    emit("audit_complete", elapsed_s=payload["elapsed_s"],
         all_bombs_positive=all_bombs_positive,
         all_platforms_positive=all_platforms_positive,
         add_counterexample=add_counterexample,
         precise_confirmation_status=precise_status)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wall-time-s", type=float, default=60.0)
    parser.add_argument("--input-precise", required=True)
    parser.add_argument("--input-result", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--report-md", required=True)
    parser.add_argument("--checkpoint-json", required=True)
    return parser.parse_args()


def main() -> int:
    run(parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
