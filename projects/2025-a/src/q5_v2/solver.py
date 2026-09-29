"""First executable Q5_v2 restricted-column solver.

This working solver intentionally separates four claims:

1. historical decisions are feasible seeds, not current objective values;
2. the MILP is exact only on its current time/surface grid and column library;
3. deterministic local enrichment is heuristic pricing;
4. the existing Q5 continuous interval evaluator is the strict rescoring oracle.

The program emits progress records and an atomic checkpoint after every major
stage so a stalled or weak implementation is visible before the wall-time cap.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Iterable, Iterator, Mapping, Sequence

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from src.q5 import solve as q5
from src.q5_v2.objectives import from_q5_evaluation


ROOT = Path(__file__).resolve().parents[2]
MISSILE_LABELS = {"M1": 0, "M2": 1, "M3": 2}
SEED_FILES = (
    "docs/q5_a196_structural_audit.json",
    "docs/q5_full_condition_search.json",
    "docs/q5_full_horizon_window_search.json",
    "docs/q5_geometry_audit.json",
    "docs/q5_geometry_pilot.json",
    "docs/q5_global_window_pilot.json",
    "docs/q5_intersection_seed.json",
    "docs/q5_longest_pilot.json",
    "docs/q5_multi_event_continuous.json",
    "docs/q5_result.json",
    "docs/q5_selection_pilot.json",
    "docs/q5_service_corridors.json",
    "docs/q5_service_dwell_candidates.json",
)
OPTIONAL_INCUMBENT_FILES = (
    "docs/q5_v2_result.json",
    "docs/q5_v2_precise.json",
)


@dataclass(frozen=True)
class PlatformColumn:
    platform: int
    heading_rad: float
    speed_mps: float
    bombs: tuple[q5.Bomb, ...]
    source: str
    variant: str


def emit(stage: str, **payload: object) -> None:
    print(json.dumps({"stage": stage, **payload}, ensure_ascii=False), flush=True)


def ready(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [ready(item) for item in value]
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def checkpoint(path: Path, stage: str, started: float, **payload: object) -> None:
    atomic_json(path, {
        "schema_version": "q5-v2-checkpoint-1.0",
        "stage": stage,
        "elapsed_s": time.perf_counter() - started,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        **payload,
    })


def label_index(value: object) -> int:
    if isinstance(value, str):
        if value not in MISSILE_LABELS:
            raise ValueError(f"unknown missile label {value!r}")
        return MISSILE_LABELS[value]
    index = int(value)
    if not 0 <= index < 3:
        raise ValueError(f"invalid missile index {index}")
    return index


def raw_decision(record: Mapping[str, object], source: str) -> q5.Decision:
    headings = tuple(float(value) for value in record["headings_rad"])
    speeds = tuple(float(value) for value in record["speeds_mps"])
    bombs = tuple(q5.Bomb(
        platform=int(item["platform"]),
        label=label_index(item["label"]),
        release_s=float(item["release_s"]),
        fuse_s=float(item["fuse_s"]),
    ) for item in record["bombs"])
    return q5.Decision(headings, speeds, bombs, source)


def platform_record_decision(record: Mapping[str, object], source: str) -> q5.Decision:
    platforms = record["platforms"]
    if not isinstance(platforms, Sequence) or len(platforms) != 5:
        raise ValueError("a full decision must contain five platform records")
    headings = [0.0] * 5
    speeds = [70.0] * 5
    bombs: list[q5.Bomb] = []
    for position, platform_record in enumerate(platforms):
        if not isinstance(platform_record, Mapping):
            raise ValueError("invalid platform record")
        platform_value = platform_record.get("platform", position)
        if isinstance(platform_value, str) and platform_value.startswith("FY"):
            platform = int(platform_value[2:]) - 1
        else:
            platform = int(platform_value)
        headings[platform] = float(platform_record["heading_rad"])
        speeds[platform] = float(platform_record["speed_mps"])
        events = platform_record.get("bombs", platform_record.get("events", ()))
        for event in events:
            release = event.get("release_s", event.get("release"))
            fuse = event.get("fuse_s", event.get("fuse"))
            bombs.append(q5.Bomb(platform, label_index(event["label"]), float(release), float(fuse)))
    return q5.Decision(tuple(headings), tuple(speeds), tuple(bombs), source)


def decision_signature(decision: q5.Decision, digits: int = 8) -> tuple[object, ...]:
    return (
        *(round(value, digits) for value in decision.headings_rad),
        *(round(value, digits) for value in decision.speeds_mps),
        *((bomb.platform, bomb.label, round(bomb.release_s, digits), round(bomb.fuse_s, digits))
          for bomb in sorted(decision.bombs, key=lambda item: (item.platform, item.release_s, item.fuse_s, item.label))),
    )


def walk_decisions(value: object, path: str) -> Iterator[q5.Decision]:
    if isinstance(value, Mapping):
        try:
            if {"headings_rad", "speeds_mps", "bombs"}.issubset(value):
                yield raw_decision(value, path)
            elif "platforms" in value:
                yield platform_record_decision(value, path)
        except (KeyError, TypeError, ValueError, q5.Q5Error):
            pass
        for key, item in value.items():
            yield from walk_decisions(item, f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            yield from walk_decisions(item, f"{path}[{index}]")


def load_seed_decisions() -> tuple[list[q5.Decision], dict[str, str]]:
    decisions: dict[tuple[object, ...], q5.Decision] = {}
    identities: dict[str, str] = {}
    for relative in (*SEED_FILES, *OPTIONAL_INCUMBENT_FILES):
        path = ROOT / relative
        if not path.exists():
            continue
        identities[relative] = sha256(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        for decision in walk_decisions(payload, relative):
            try:
                q5.validate(decision)
            except q5.Q5Error:
                continue
            decisions.setdefault(decision_signature(decision), decision)
    return list(decisions.values()), identities


def column_signature(column: PlatformColumn, digits: int = 8) -> tuple[object, ...]:
    return (
        column.platform,
        round(column.heading_rad % (2 * math.pi), digits),
        round(column.speed_mps, digits),
        *((bomb.label, round(bomb.release_s, digits), round(bomb.fuse_s, digits))
          for bomb in sorted(column.bombs, key=lambda item: (item.release_s, item.fuse_s, item.label))),
    )


def column_decision(column: PlatformColumn) -> q5.Decision:
    headings = [0.0] * 5
    speeds = [70.0] * 5
    headings[column.platform] = column.heading_rad % (2 * math.pi)
    speeds[column.platform] = column.speed_mps
    return q5.Decision(tuple(headings), tuple(speeds), column.bombs, column.source)


def make_column(
    base: PlatformColumn,
    *,
    heading_delta: float = 0.0,
    speed_delta: float = 0.0,
    release_delta: float = 0.0,
    variant: str,
) -> PlatformColumn | None:
    column = PlatformColumn(
        platform=base.platform,
        heading_rad=(base.heading_rad + heading_delta) % (2 * math.pi),
        speed_mps=float(np.clip(base.speed_mps + speed_delta, 70.0, 140.0)),
        bombs=tuple(replace(bomb, release_s=bomb.release_s + release_delta) for bomb in base.bombs),
        source=base.source,
        variant=variant,
    )
    try:
        q5.validate(column_decision(column))
    except q5.Q5Error:
        return None
    return column


def mutate_column_bomb(
    base: PlatformColumn, bomb_index: int, field: str, delta: float
) -> PlatformColumn | None:
    bombs = list(base.bombs)
    bomb = bombs[bomb_index]
    if field == "release":
        bombs[bomb_index] = replace(bomb, release_s=bomb.release_s + delta)
    elif field == "fuse":
        bombs[bomb_index] = replace(bomb, fuse_s=bomb.fuse_s + delta)
    else:
        raise ValueError(field)
    column = PlatformColumn(
        platform=base.platform,
        heading_rad=base.heading_rad,
        speed_mps=base.speed_mps,
        bombs=tuple(bombs),
        source=base.source,
        variant=f"bomb_{bomb_index}_{field}_{delta:+.2f}",
    )
    try:
        q5.validate(column_decision(column))
    except q5.Q5Error:
        return None
    return column


def generate_columns(seeds: Sequence[q5.Decision]) -> list[PlatformColumn]:
    base_columns: list[PlatformColumn] = []
    for decision in seeds:
        for platform in range(5):
            bombs = tuple(sorted((bomb for bomb in decision.bombs if bomb.platform == platform),
                                 key=lambda item: item.release_s))
            if not bombs:
                continue
            base_columns.append(PlatformColumn(
                platform=platform,
                heading_rad=decision.headings_rad[platform],
                speed_mps=decision.speeds_mps[platform],
                bombs=bombs,
                source=decision.source,
                variant="base",
            ))

    variants: dict[tuple[object, ...], PlatformColumn] = {}
    for base in base_columns:
        choices = [
            make_column(base, variant="base"),
            *(make_column(base, release_delta=delta, variant=f"release_shift_{delta:+.1f}")
              for delta in (-2.0, -1.0, 1.0, 2.0)),
            *(make_column(base, heading_delta=delta, variant=f"heading_{delta:+.3f}")
              for delta in (-0.025, 0.025)),
            *(make_column(base, speed_delta=delta, variant=f"speed_{delta:+.1f}")
              for delta in (-8.0, 8.0)),
            *(mutate_column_bomb(base, bomb_index, field, delta)
              for bomb_index in range(len(base.bombs))
              for field in ("release", "fuse")
              for delta in (-0.25, 0.25)),
        ]
        for column in choices:
            if column is not None:
                variants.setdefault(column_signature(column), column)
    return list(variants.values())


def time_nodes(step_s: float) -> tuple[np.ndarray, np.ndarray]:
    horizon = max(q5.ARRIVAL_TIMES)
    nodes = np.arange(0.0, horizon + step_s * 0.5, step_s)
    nodes = np.unique(np.concatenate([nodes, np.asarray(q5.ARRIVAL_TIMES)]))
    nodes.sort()
    weights = np.zeros((3, len(nodes)))
    edges = np.empty(len(nodes) + 1)
    edges[1:-1] = (nodes[:-1] + nodes[1:]) / 2
    edges[0] = 0.0
    edges[-1] = horizon
    for missile, arrival in enumerate(q5.ARRIVAL_TIMES):
        weights[missile] = np.maximum(0.0, np.minimum(edges[1:], arrival) - np.minimum(edges[:-1], arrival))
    return nodes, weights


def visible_masks(times: np.ndarray, mesh: object) -> tuple[np.ndarray, np.ndarray]:
    missiles = np.stack([q5.pilot.missile(missile, times) for missile in range(3)])
    visible = np.stack([q5.q3.visibility_mask(missiles[missile], mesh) for missile in range(3)])
    return missiles, visible


def coverage_for_decision(
    decision: q5.Decision,
    times: np.ndarray,
    mesh: object,
    missiles: np.ndarray,
    visible: np.ndarray,
    *,
    conservative_margin_m: float,
) -> np.ndarray:
    q5.validate(decision)
    covered = np.zeros_like(visible, dtype=bool)
    threshold = q5.p().smoke_radius - conservative_margin_m
    for missile in range(3):
        for bomb in decision.bombs:
            explosion = q5.explosion_time(bomb)
            active = np.flatnonzero(
                (times >= explosion - q5.TIME_TOL)
                & (times <= min(explosion + q5.p().smoke_duration, q5.arrival(missile)) + q5.TIME_TOL)
            )
            if not len(active):
                continue
            distances = q5.q3._distance_to_segments(
                q5.cloud(decision, bomb, times[active]), missiles[missile, active], mesh
            )
            covered[missile, active] |= distances <= threshold
    return covered


def proxy_metrics(coverage: np.ndarray, visible: np.ndarray, weights: np.ndarray) -> dict[str, object]:
    complete = np.all(coverage | ~visible, axis=2)
    durations = np.sum(weights * complete, axis=1)
    all_three = np.all(complete, axis=0)
    return {
        "per_missile_s": durations.tolist(),
        "j_sum_missile_s": float(np.sum(durations)),
        "j_fair_s": float(np.min(durations)),
        "j_all_node_integral_s": float(np.sum(np.min(weights, axis=0) * all_three)),
        "complete_node_count": int(np.sum(complete)),
    }


def column_potential(coverage: np.ndarray, visible: np.ndarray, weights: np.ndarray) -> float:
    visible_count = np.maximum(1, np.sum(visible, axis=2))
    fraction = np.sum(coverage & visible, axis=2) / visible_count
    return float(np.sum(weights * fraction ** 6))


def score_and_prune_columns(
    columns: Sequence[PlatformColumn],
    times: np.ndarray,
    mesh: object,
    missiles: np.ndarray,
    visible: np.ndarray,
    weights: np.ndarray,
    *,
    max_per_platform: int,
    deadline: float,
) -> tuple[list[PlatformColumn], np.ndarray, list[dict[str, object]]]:
    rows: list[tuple[PlatformColumn, np.ndarray, float]] = []
    total = len(columns)
    for index, column in enumerate(columns, 1):
        if time.perf_counter() >= deadline:
            break
        coverage = coverage_for_decision(
            column_decision(column), times, mesh, missiles, visible, conservative_margin_m=0.10
        )
        potential = column_potential(coverage, visible, weights)
        rows.append((column, coverage, potential))
        if index == 1 or index % 20 == 0 or index == total:
            emit("column_scoring_progress", completed=index, total=total,
                 elapsed_s=None, current_potential=potential)

    selected: list[tuple[PlatformColumn, np.ndarray, float]] = []
    summary: list[dict[str, object]] = []
    for platform in range(5):
        group = [row for row in rows if row[0].platform == platform]
        group.sort(key=lambda row: (row[2], row[0].variant == "base"), reverse=True)
        base = [row for row in group if row[0].variant == "base"][:3]
        chosen: list[tuple[PlatformColumn, np.ndarray, float]] = []
        seen: set[tuple[object, ...]] = set()
        for row in [*base, *group]:
            signature = column_signature(row[0])
            if signature in seen:
                continue
            seen.add(signature)
            chosen.append(row)
            if len(chosen) >= max_per_platform:
                break
        if not chosen:
            raise RuntimeError(f"no feasible columns for platform {platform}")
        selected.extend(chosen)
        summary.append({
            "platform": platform,
            "raw_count": len(group),
            "selected_count": len(chosen),
            "best_potential": chosen[0][2],
            "base_column_count": sum(row[0].variant == "base" for row in chosen),
        })
    return [row[0] for row in selected], np.stack([row[1] for row in selected]), summary


def restricted_master(
    columns: Sequence[PlatformColumn],
    coverages: np.ndarray,
    visible: np.ndarray,
    weights: np.ndarray,
    *,
    time_limit_s: float,
) -> tuple[list[int], dict[str, object]]:
    column_count = len(columns)
    missile_count, time_count, point_count = visible.shape
    y_count = missile_count * time_count
    variable_count = column_count + y_count

    row_indices: list[int] = []
    column_indices: list[int] = []
    data: list[float] = []
    lower: list[float] = []
    upper: list[float] = []
    row = 0

    for platform in range(5):
        for index, column in enumerate(columns):
            if column.platform == platform:
                row_indices.append(row)
                column_indices.append(index)
                data.append(1.0)
        lower.append(1.0)
        upper.append(1.0)
        row += 1

    for missile in range(missile_count):
        for node in range(time_count):
            if weights[missile, node] <= 0:
                continue
            y_index = column_count + missile * time_count + node
            for point in np.flatnonzero(visible[missile, node]):
                row_indices.append(row)
                column_indices.append(y_index)
                data.append(1.0)
                for column_index in np.flatnonzero(coverages[:, missile, node, point]):
                    row_indices.append(row)
                    column_indices.append(int(column_index))
                    data.append(-1.0)
                lower.append(-np.inf)
                upper.append(0.0)
                row += 1

    matrix = coo_matrix((data, (row_indices, column_indices)), shape=(row, variable_count)).tocsr()
    objective = np.zeros(variable_count)
    objective[column_count:] = -weights.reshape(-1)
    variable_lower = np.zeros(variable_count)
    variable_upper = np.ones(variable_count)
    for missile in range(missile_count):
        for node in range(time_count):
            if weights[missile, node] <= 0:
                variable_upper[column_count + missile * time_count + node] = 0.0

    started = time.perf_counter()
    result = milp(
        objective,
        integrality=np.ones(variable_count),
        bounds=Bounds(variable_lower, variable_upper),
        constraints=LinearConstraint(matrix, np.asarray(lower), np.asarray(upper)),
        options={"time_limit": max(1.0, time_limit_s), "mip_rel_gap": 0.0, "presolve": True},
    )
    elapsed = time.perf_counter() - started
    if result.x is None:
        raise RuntimeError(f"restricted master failed: status={result.status}, message={result.message}")
    chosen: list[int] = []
    for platform in range(5):
        candidates = [index for index, column in enumerate(columns) if column.platform == platform]
        chosen.append(max(candidates, key=lambda index: result.x[index]))
    record = {
        "status": int(result.status),
        "message": str(result.message),
        "success": bool(result.success),
        "elapsed_s": elapsed,
        "column_count": column_count,
        "binary_y_count": y_count,
        "constraint_count": row,
        "nonzero_count": int(matrix.nnz),
        "proxy_objective_missile_s": float(-result.fun),
        "mip_gap": None if getattr(result, "mip_gap", None) is None else float(result.mip_gap),
        "mip_node_count": None if getattr(result, "mip_node_count", None) is None else int(result.mip_node_count),
        "chosen_column_indices": chosen,
    }
    return chosen, record


def combine_columns(columns: Sequence[PlatformColumn], chosen: Sequence[int], source: str) -> q5.Decision:
    headings = [0.0] * 5
    speeds = [70.0] * 5
    bombs: list[q5.Bomb] = []
    for index in chosen:
        column = columns[index]
        headings[column.platform] = column.heading_rad
        speeds[column.platform] = column.speed_mps
        bombs.extend(column.bombs)
    decision = q5.Decision(tuple(headings), tuple(speeds), tuple(bombs), source)
    q5.validate(decision)
    return decision


def strict_key(evaluation: Mapping[str, object]) -> tuple[float, float, float, float]:
    metrics = from_q5_evaluation(evaluation)
    return metrics.official_lexicographic_key


def proxy_key(record: Mapping[str, object]) -> tuple[float, float, float]:
    return (float(record["j_sum_missile_s"]), float(record["j_fair_s"]),
            float(record["j_all_node_integral_s"]))


def decision_proxy(
    decision: q5.Decision,
    times: np.ndarray,
    mesh: object,
    missiles: np.ndarray,
    visible: np.ndarray,
    weights: np.ndarray,
) -> tuple[dict[str, object], np.ndarray]:
    coverage = coverage_for_decision(
        decision, times, mesh, missiles, visible, conservative_margin_m=0.0
    )
    return proxy_metrics(coverage, visible, weights), coverage


def deterministic_neighbours(decision: q5.Decision, scale: int) -> Iterator[q5.Decision]:
    steps = (
        ("heading", 0.010 if scale == 0 else 0.003),
        ("speed", 2.0 if scale == 0 else 0.5),
        ("platform_shift", 0.20 if scale == 0 else 0.05),
        ("release", 0.20 if scale == 0 else 0.05),
        ("fuse", 0.20 if scale == 0 else 0.05),
    )
    coordinates = [
        *((kind, index, step) for kind, step in steps[:3] for index in range(5)),
        *((kind, index, step) for kind, step in steps[3:] for index in range(len(decision.bombs))),
    ]
    for kind, index, step in coordinates:
        for sign in (-1.0, 1.0):
            candidate = q5.mutate(decision, kind, index, sign * step,
                                  f"q5_v2_deterministic_refine_s{scale}")
            if candidate is not None:
                yield candidate


def deterministic_refine(
    start: q5.Decision,
    times: np.ndarray,
    mesh: object,
    missiles: np.ndarray,
    visible: np.ndarray,
    weights: np.ndarray,
    *,
    deadline: float,
) -> tuple[list[q5.Decision], dict[str, object]]:
    current = start
    current_score, _ = decision_proxy(current, times, mesh, missiles, visible, weights)
    cache = {decision_signature(current): current_score}
    accepted = [current]
    evaluations = 1
    stages: list[dict[str, object]] = []
    for scale in range(2):
        scale_start = current_score
        accepted_count = 0
        for candidate in deterministic_neighbours(current, scale):
            if time.perf_counter() >= deadline:
                break
            signature = decision_signature(candidate)
            if signature not in cache:
                cache[signature], _ = decision_proxy(candidate, times, mesh, missiles, visible, weights)
                evaluations += 1
            candidate_score = cache[signature]
            if proxy_key(candidate_score) > proxy_key(current_score):
                current = candidate
                current_score = candidate_score
                accepted.append(current)
                accepted_count += 1
            if evaluations % 10 == 0:
                emit("deterministic_refine_progress", scale=scale, evaluations=evaluations,
                     accepted=len(accepted) - 1, j_sum_proxy=current_score["j_sum_missile_s"])
        stages.append({
            "scale": scale,
            "start": scale_start,
            "end": current_score,
            "accepted_moves": accepted_count,
        })
        if time.perf_counter() >= deadline:
            break
    return accepted, {
        "evaluation_count": evaluations,
        "accepted_count": len(accepted) - 1,
        "stages": stages,
        "best_proxy": current_score,
        "terminated_by": "wall_time" if time.perf_counter() >= deadline else "completed_scales",
    }


def report_markdown(payload: Mapping[str, object]) -> str:
    best = payload["working_best"]
    strict = best["strict_screen"]
    metrics = best["metrics"]
    baseline = payload["baseline"]
    master = payload["restricted_master"]
    lines = [
        "# Q5_v2 平台列—MILP 工作求解报告",
        "",
        "本报告是工作结果，不替代正式 E1/E2，不声称连续原问题全局最优。原 Q5 未被覆盖。",
        "",
        "本轮的全文方法角色已收束为“物理可达平台计划生成—严格筛选—受限 MILP 资源组合—原变量确定性精修—严格复核”。MILP 只承担 Q5 新增的完整平台计划选择；当前没有把启发式候选扩充称为已认证列生成，也没有实现可声称收敛的连续时间—表面交换算法。",
        "",
        "## 当前结果",
        "",
        f"- `J_sum = {metrics['j_sum_missile_s']:.12f}` 导弹·s；",
        f"- `J_fair = {metrics['j_fair_s']:.12f}` s；",
        f"- `J_all = {metrics['j_all_s']:.12f}` s；",
        f"- `L_all = {metrics['l_all_s']:.12f}` s；",
        f"- 三枚导弹分别为 `{metrics['per_missile_duration_s']}` s；",
        f"- 严格复算层级：`{strict['by_missile'][0]['settings']['name']}`。",
        "",
        "## 与基线比较",
        "",
        f"- 本轮历史种子严格基线：`{baseline['metrics']['j_sum_missile_s']:.12f}` 导弹·s；",
        f"- 当前增量：`{metrics['j_sum_missile_s'] - baseline['metrics']['j_sum_missile_s']:.12f}` 导弹·s。",
        "",
        "## 求解边界",
        "",
        f"- 受限主问题列数：`{master['column_count']}`；约束数：`{master['constraint_count']}`；",
        f"- MILP 状态：`{master['message']}`；受限主问题 gap：`{master['mip_gap']}`；",
        "- `RESTRICTED_MASTER_ONLY`：只证明当前离散节点、表面网格和列库内的组合结果；",
        "- `PRICING_NOT_CERTIFIED`：本轮定向扰动不是全局定价 oracle；",
        "- 最终时间由现有连续区间严格核重建，不采用 MILP 节点计数作为正式时长。",
        "- 因而本结果可表述为经严格工作复算的高质量可行候选，以及当前受限主问题内的组合最优；不能表述为连续原问题全局最优。",
        "",
        "## 监管记录",
        "",
        f"- 总耗时：`{payload['elapsed_s']:.3f}` s；",
        f"- 提取历史可行决策：`{payload['seed_library']['decision_count']}`；",
        f"- 原始计划列：`{payload['column_library']['generated_count']}`；",
        f"- 精简后计划列：`{payload['column_library']['selected_count']}`；",
        f"- 确定性精修评价：`{payload['deterministic_refinement']['evaluation_count']}`。",
        "",
    ]
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, object]:
    started = time.perf_counter()
    deadline = started + args.wall_time_s
    output_path = ROOT / args.output_json
    report_path = ROOT / args.report_md
    checkpoint_path = ROOT / args.checkpoint_json

    emit("start", wall_time_s=args.wall_time_s, objective="J_sum_then_J_fair_J_all_L_all")
    seeds, seed_identities = load_seed_decisions()
    if not seeds:
        raise RuntimeError("no valid historical decisions were recovered")
    emit("seed_library", decision_count=len(seeds), source_file_count=len(seed_identities))
    checkpoint(checkpoint_path, "seed_library", started, decision_count=len(seeds))

    times, weights = time_nodes(args.master_time_step_s)
    mesh = q5.q3.surface_mesh(args.master_theta, args.master_levels)
    missiles, visible = visible_masks(times, mesh)
    generated_columns = generate_columns(seeds)
    emit("column_library_generated", column_count=len(generated_columns), time_node_count=len(times),
         surface_point_count=len(mesh.points))

    scoring_deadline = min(deadline - 24.0, time.perf_counter() + max(8.0, args.wall_time_s * 0.35))
    columns, coverages, column_summary = score_and_prune_columns(
        generated_columns, times, mesh, missiles, visible, weights,
        max_per_platform=args.max_columns_per_platform, deadline=scoring_deadline,
    )
    emit("column_library_pruned", selected_count=len(columns), by_platform=column_summary)
    checkpoint(checkpoint_path, "column_library_pruned", started,
               generated_count=len(generated_columns), selected_count=len(columns), by_platform=column_summary)

    master_time = max(2.0, min(args.master_time_limit_s, deadline - time.perf_counter() - 18.0))
    chosen, master_record = restricted_master(
        columns, coverages, visible, weights, time_limit_s=master_time
    )
    combined = combine_columns(columns, chosen, "q5_v2_restricted_master")
    master_union = np.any(coverages[np.asarray(chosen)], axis=0)
    master_proxy = proxy_metrics(master_union, visible, weights)
    emit("restricted_master_complete", **master_record, selected_proxy=master_proxy)
    checkpoint(checkpoint_path, "restricted_master_complete", started,
               restricted_master=master_record, selected_proxy=master_proxy)

    incumbent_seeds = [decision for decision in seeds if "q5_v2" in decision.source]
    other_seeds = sorted(
        (decision for decision in seeds if "q5_v2" not in decision.source),
        key=lambda decision: len(decision.bombs), reverse=True,
    )
    seed_candidates = [*incumbent_seeds, *other_seeds[:12]]
    strict_candidates: list[dict[str, object]] = []
    for decision in [combined, *seed_candidates]:
        if time.perf_counter() >= deadline - 14.0:
            break
        try:
            evaluation = q5.evaluate(decision, q5.PROBE)
        except q5.Q5Error as exc:
            emit("strict_probe_rejected", source=decision.source, code=exc.code)
            continue
        strict_candidates.append({"decision": decision, "probe": evaluation})
        emit("strict_probe_candidate", source=decision.source,
             j_sum_missile_s=evaluation["sum_duration_missile_s"],
             j_fair_s=evaluation["minimum_missile_duration_s"],
             j_all_s=evaluation["total_intersection_s"],
             l_all_s=evaluation["longest_continuous_s"])
    if not strict_candidates:
        raise RuntimeError("no candidate survived strict probe evaluation")
    historical_rows = [row for row in strict_candidates if row["decision"].source != "q5_v2_restricted_master"]
    if not historical_rows:
        historical_rows = list(strict_candidates)
    historical_rows.sort(key=lambda row: strict_key(row["probe"]), reverse=True)
    baseline_row = historical_rows[0]
    strict_candidates.sort(key=lambda row: strict_key(row["probe"]), reverse=True)

    refine_deadline = min(deadline - 9.0, time.perf_counter() + max(0.0, args.wall_time_s * 0.20))
    accepted, refine_record = deterministic_refine(
        strict_candidates[0]["decision"], times, mesh, missiles, visible, weights,
        deadline=refine_deadline,
    )
    emit("deterministic_refine_complete", **refine_record)
    checkpoint(checkpoint_path, "deterministic_refine_complete", started,
               deterministic_refinement=refine_record)

    for decision in accepted[-4:]:
        if decision_signature(decision) in {
            decision_signature(row["decision"]) for row in strict_candidates
        }:
            continue
        if time.perf_counter() >= deadline - 5.0:
            break
        evaluation = q5.evaluate(decision, q5.PROBE)
        strict_candidates.append({"decision": decision, "probe": evaluation})
        emit("refined_strict_probe", source=decision.source,
             j_sum_missile_s=evaluation["sum_duration_missile_s"])

    strict_candidates.sort(key=lambda row: strict_key(row["probe"]), reverse=True)
    screen_rows: list[dict[str, object]] = []
    for row in strict_candidates[:3]:
        evaluation = q5.evaluate(row["decision"], q5.SCREEN)
        screen_rows.append({**row, "screen": evaluation})
        emit("strict_screen_candidate", source=row["decision"].source,
             j_sum_missile_s=evaluation["sum_duration_missile_s"],
             j_fair_s=evaluation["minimum_missile_duration_s"],
             j_all_s=evaluation["total_intersection_s"],
             l_all_s=evaluation["longest_continuous_s"])
    screen_rows.sort(key=lambda row: strict_key(row["screen"]), reverse=True)
    winner = screen_rows[0]
    historical_screen_rows = [
        row for row in screen_rows if "q5_v2" not in row["decision"].source
    ]
    if not historical_screen_rows:
        historical_screen_rows = list(screen_rows)
    historical_screen_rows.sort(key=lambda row: strict_key(row["screen"]), reverse=True)
    baseline_screen_row = historical_screen_rows[0]
    metrics = from_q5_evaluation(winner["screen"])
    baseline_metrics = from_q5_evaluation(baseline_screen_row["screen"])

    payload: dict[str, object] = {
        "schema_version": "q5-v2-working-result-1.0",
        "status": "working_feasible_restricted_master",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "elapsed_s": time.perf_counter() - started,
        "objective_hierarchy": ["J_sum", "J_fair", "J_all", "L_all"],
        "units": {"J_sum": "missile*s", "J_fair": "s", "J_all": "s", "L_all": "s"},
        "seed_library": {"decision_count": len(seeds), "input_identities": seed_identities},
        "column_library": {
            "generated_count": len(generated_columns),
            "selected_count": len(columns),
            "by_platform": column_summary,
            "chosen": [asdict(columns[index]) for index in chosen],
        },
        "master_discretization": {
            "time_step_s": args.master_time_step_s,
            "time_node_count": len(times),
            "surface_theta": args.master_theta,
            "surface_levels": args.master_levels,
            "surface_point_count": len(mesh.points),
            "conservative_column_margin_m": 0.10,
        },
        "restricted_master": master_record,
        "deterministic_refinement": refine_record,
        "baseline": {
            "source": baseline_screen_row["decision"].source,
            "strict_probe": baseline_screen_row["probe"],
            "strict_screen": baseline_screen_row["screen"],
            "metrics": baseline_metrics.as_dict(),
        },
        "working_best": {
            "source": winner["decision"].source,
            "decision": q5.decision_record(winner["decision"]),
            "strict_probe": winner["probe"],
            "strict_screen": winner["screen"],
            "metrics": metrics.as_dict(),
        },
        "proof_boundary": {
            "restricted_master_only": True,
            "pricing_certified": False,
            "continuous_global_optimality": False,
            "strict_continuous_rescore": True,
            "strict_level": q5.SCREEN["name"],
            "failure_signals": ["RESTRICTED_MASTER_ONLY", "PRICING_NOT_CERTIFIED", "REFINEMENT_UNSTABLE"],
        },
    }
    payload["elapsed_s"] = time.perf_counter() - started
    atomic_json(output_path, payload)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report_markdown(payload), encoding="utf-8")
    checkpoint(checkpoint_path, "complete", started,
               output_json=args.output_json, report_md=args.report_md,
               metrics=metrics.as_dict())
    emit("complete", elapsed_s=payload["elapsed_s"], **metrics.as_dict())
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wall-time-s", type=float, default=60.0)
    parser.add_argument("--master-time-step-s", type=float, default=0.30)
    parser.add_argument("--master-theta", type=int, default=16)
    parser.add_argument("--master-levels", type=int, default=4)
    parser.add_argument("--max-columns-per-platform", type=int, default=16)
    parser.add_argument("--master-time-limit-s", type=float, default=12.0)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--report-md", required=True)
    parser.add_argument("--checkpoint-json", required=True)
    args = parser.parse_args()
    if args.wall_time_s < 30:
        parser.error("wall-time-s must be at least 30 seconds")
    return args


def main() -> int:
    args = parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
