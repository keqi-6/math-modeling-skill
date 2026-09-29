#!/usr/bin/env python3
"""Focused multi-event, multi-cloud Q5 longest-continuous-window pilot."""
from __future__ import annotations

import argparse
import itertools
import json
import math
import platform
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT))

from src.q3 import selection_pilot as q3  # noqa: E402
from src.q5 import geometry_pilot as geometry  # noqa: E402
from src.q5 import global_window_pilot as global_pilot  # noqa: E402
from src.q5 import service_domains as service  # noqa: E402
from src.q5 import solve as q5  # noqa: E402


SPEC_ID = "Q5-MULTI-EVENT-CONTINUOUS-1.0"
SEED_PATH = ROOT / "docs/q5_longest_pilot.json"
SERVICE_PATH = ROOT / "docs/q5_service_dwell_candidates.json"
SEARCH_PLATFORMS = (2, 4, 3, 1)
PROXY_THETA = 32
PROXY_LEVELS = 5
EVENT_ANCHOR_STEP_S = .5
TRACK_PLAN_BEAM = 480
EVENTS_PER_TRACK = 56
PLANS_PER_TRACK = 6
STRICT_SHORTLIST = 18


@dataclass(frozen=True)
class ProxyPlan:
    track: geometry.Track
    events: tuple[global_pilot.GlobalEvent, ...]
    mask: int
    combined_mask: int
    score: tuple


def emit(stage: str, **values) -> None:
    print(json.dumps({"stage": stage, **q5.ready(values)}, ensure_ascii=False), flush=True)


def decision_from_record(record: dict, source: str) -> q5.Decision:
    headings = [0.] * 5
    speeds = [70.] * 5
    bombs = []
    for platform_row in record["platforms"]:
        index = q5.NAMES.index(platform_row["platform"])
        headings[index] = float(platform_row["heading_rad"])
        speeds[index] = float(platform_row["speed_mps"])
        for bomb in platform_row["bombs"]:
            bombs.append(q5.Bomb(
                index, q5.MISSILE_NAMES.index(bomb["label"]),
                float(bomb["release_s"]), float(bomb["fuse_s"]),
            ))
    decision = q5.Decision(
        tuple(headings), tuple(speeds),
        tuple(sorted(bombs, key=lambda row: (row.platform, row.release_s))), source,
    )
    q5.validate(decision)
    return decision


def load_seed(path: Path = SEED_PATH) -> tuple[q5.Decision, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    row = payload["best_before_refinement"]
    decision = decision_from_record(row["decision"], "multi_event_continuous_seed")
    summary = {
        "source": row["source"],
        "longest_continuous_s": float(row["longest_continuous_s"]),
        "longest_interval_s": [float(v) for v in row["longest_interval_s"]],
        "total_intersection_s": float(row["total_intersection_s"]),
        "active_bomb_count": len(decision.bombs),
    }
    return decision, summary


def _longest_boolean_run(times: np.ndarray, covered: list[bool], nominal_step: float) -> tuple[list[float] | None, float]:
    best = None
    first = None
    previous = None
    for index, flag in enumerate(covered):
        if flag and (first is None or times[index] - times[previous] <= nominal_step * 1.01):
            if first is None:
                first = index
            previous = index
        else:
            if first is not None:
                candidate = [float(times[first]), float(times[previous])]
                if best is None or candidate[1] - candidate[0] > best[1] - best[0]:
                    best = candidate
            first = index if flag else None
            previous = index if flag else None
    if first is not None:
        candidate = [float(times[first]), float(times[previous])]
        if best is None or candidate[1] - candidate[0] > best[1] - best[0]:
            best = candidate
    return best, (best[1] - best[0] if best else 0.)


def proxy_metrics(mask: int, times: np.ndarray, time_universe: list[int], nominal_step: float) -> dict:
    ratios = []
    full = []
    for universe in time_universe:
        denominator = universe.bit_count()
        numerator = (mask & universe).bit_count()
        ratio = numerator / denominator if denominator else 0.
        ratios.append(ratio)
        full.append(numerator == denominator and denominator > 0)
    interval, duration = _longest_boolean_run(times, full, nominal_step)
    return {
        "longest_full_node_run_s": duration,
        "longest_full_node_interval_s": interval,
        "full_time_node_count": int(sum(full)),
        "minimum_time_coverage": float(min(ratios, default=0.)),
        "overall_coverage": float(np.mean(ratios) if ratios else 0.),
    }


def metric_key(metrics: dict) -> tuple:
    return (
        metrics["longest_full_node_run_s"], metrics["full_time_node_count"],
        metrics["minimum_time_coverage"], metrics["overall_coverage"],
    )


def event_from_bomb(decision: q5.Decision, bomb: q5.Bomb) -> geometry.Event:
    point = q5.explosion_point(decision, bomb)
    return geometry.Event(
        bomb.platform, decision.headings_rad[bomb.platform], decision.speeds_mps[bomb.platform],
        0., bomb.release_s, bomb.fuse_s, tuple(map(float, point)), 0, (0, 0, 0),
        bomb.label, "seed_exact_event",
    )


def global_event(track: geometry.Track, event: geometry.Event, times, mesh, missiles, visible) -> global_pilot.GlobalEvent:
    mask = global_pilot.event_global_mask(track, event, times, mesh, missiles, visible)
    return global_pilot.GlobalEvent(event, mask, event.release + event.fuse)


def track_key(track: geometry.Track) -> tuple:
    return round(track.heading, 8), round(track.speed, 6)


def angular_distance(a: float, b: float) -> float:
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


def candidate_tracks(seed: q5.Decision, mesh, anchors: list[float], platform_index: int,
                     service_path: Path = SERVICE_PATH, limit: int = 14) -> list[geometry.Track]:
    i = platform_index
    seed_heading, seed_speed = seed.headings_rad[i], seed.speeds_mps[i]
    tracks = []
    for heading_delta in (-.05, -.025, 0., .025, .05):
        for speed_delta in (-15., -7.5, 0., 7.5, 15.):
            speed = min(140., max(70., seed_speed + speed_delta))
            tracks.append(geometry.Track(
                i, (seed_heading + heading_delta) % (2 * math.pi), speed,
                "seed_local_track_grid", -1, -1,
            ))
    if service_path.is_file():
        payload = json.loads(service_path.read_text(encoding="utf-8"))
        rows = []
        for pair in payload.get("pairs", []):
            if pair.get("platform") != q5.NAMES[i]:
                continue
            for layer in pair.get("lambda_layers", []):
                for candidate in layer.get("retained_candidates", []):
                    if anchors[0] - 2. <= candidate["seed_s"] <= anchors[-1] + 2.:
                        event = candidate["event"]
                        rows.append((candidate["target_interval"]["duration_s"], event))
        for _, event in sorted(rows, key=lambda row: row[0], reverse=True)[:10]:
            tracks.append(geometry.Track(
                i, float(event["heading_rad"]), float(event["speed_mps"]),
                "analytic_service_seed", -1, -1,
            ))
    c3_rows = []
    for anchor in anchors:
        sl = geometry.Slice(float(anchor), mesh)
        generated, _ = q5.c3_tracks(i, sl)
        c3_rows.extend(generated)
    c3_rows.sort(key=lambda row: (
        angular_distance(row.heading, seed_heading), abs(row.speed - seed_speed),
        row.source_label, row.source_surface,
    ))
    tracks.extend(c3_rows[:8])
    unique = {}
    for track in tracks:
        unique.setdefault(track_key(track), track)
    seed_key = (round(seed_heading, 8), round(seed_speed, 6))
    ordered = sorted(unique.values(), key=lambda row: (
        0 if track_key(row) == seed_key else 1,
        angular_distance(row.heading, seed_heading), abs(row.speed - seed_speed), row.source,
    ))
    # Preserve source diversity after the local neighbourhood.
    local = [row for row in ordered if row.source == "seed_local_track_grid"][:14]
    other = [row for row in ordered if row.source != "seed_local_track_grid"]
    selected = local + other[:max(0, limit - len(local))]
    if not any(track_key(row) == seed_key for row in selected):
        selected.insert(0, unique[seed_key])
    return selected[:limit]


def collect_track_events(track: geometry.Track, anchor_times: np.ndarray, mesh,
                         exact_seed_events: list[geometry.Event]) -> list[geometry.Event]:
    pool = list(exact_seed_events)
    for observation_s in anchor_times:
        events, _ = q5.event_library(track, geometry.Slice(float(observation_s), mesh))
        pool.extend(events)
    unique = {}
    for event in pool:
        key = (round(event.release / .02), round(event.fuse / .02), event.label)
        old = unique.get(key)
        if old is None or (event.mask.bit_count(), min(event.counts)) > (old.mask.bit_count(), min(old.counts)):
            unique[key] = event
    return sorted(unique.values(), key=lambda row: (
        row.mask.bit_count(), min(row.counts), -(row.release + row.fuse)
    ), reverse=True)


def dense_event_library(track: geometry.Track, sl: geometry.Slice,
                        age_step_s: float = .5, limit: int = 36) -> list[geometry.Event]:
    """Fixed-track event library without the legacy six-age hard coding."""
    direction = np.array([math.cos(track.heading), math.sin(track.heading)])
    surface_ids = q5.stratified_surface_indices(sl.mesh, 6, 4)
    states = []
    age_cap = min(q5.p().smoke_duration, sl.t)
    ages = np.arange(0., age_cap + 1e-10, age_step_s)
    for age in ages:
        explosion_s = sl.t - float(age)
        if explosion_s <= 1e-10:
            continue
        cloud_xy = q5.ORIGINS[track.platform, :2] + track.speed * explosion_s * direction
        minimum_explosion_z = max(
            0., q5.ORIGINS[track.platform, 2] - .5 * q5.p().gravity * explosion_s ** 2
        )
        for missile_index in range(3):
            missile = sl.missiles[missile_index]
            for surface_index in surface_ids:
                if not sl.visible[missile_index, surface_index]:
                    continue
                point = sl.mesh.points[surface_index]
                horizontal_line = point[:2] - missile[:2]
                denominator = float(horizontal_line @ horizontal_line)
                lam = float(np.clip(
                    ((cloud_xy - missile[:2]) @ horizontal_line) / denominator, 0., 1.
                )) if denominator > 0. else 0.
                nearest_xy = missile[:2] + lam * horizontal_line
                if np.linalg.norm(cloud_xy - nearest_xy) > q5.p().smoke_radius + 2.:
                    continue
                line_z = float(missile[2] + lam * (point[2] - missile[2]))
                for dz in (-8., -4., 0., 4., 8.):
                    cloud_z = line_z + dz
                    explosion_z = cloud_z + q5.p().smoke_sink_speed * age
                    if not minimum_explosion_z - q5.TIME_TOL <= explosion_z <= q5.ORIGINS[track.platform, 2] + q5.TIME_TOL:
                        continue
                    fuse = math.sqrt(max(
                        0., 2. * (q5.ORIGINS[track.platform, 2] - explosion_z) / q5.p().gravity
                    ))
                    release = explosion_s - fuse
                    if release < -q5.TIME_TOL:
                        continue
                    states.append((
                        max(0., release), fuse,
                        (float(cloud_xy[0]), float(cloud_xy[1]), cloud_z), missile_index, float(age),
                    ))
    if not states:
        return []
    clouds = np.asarray([row[2] for row in states], float)
    masks = [0] * len(states)
    counts = [[0, 0, 0] for _ in states]
    for missile_index in range(3):
        missiles = np.repeat(sl.missiles[missile_index:missile_index + 1], len(states), axis=0)
        distances = q3._distance_to_segments(clouds, missiles, sl.mesh)
        hits = distances <= q5.p().smoke_radius + 1e-12
        hits &= sl.visible[missile_index][None, :]
        for index, hit_row in enumerate(hits):
            local = geometry.bits(hit_row)
            masks[index] |= local << sl.offsets[missile_index]
            counts[index][missile_index] = int(np.sum(hit_row))
    unique = {}
    for state, mask, count in zip(states, masks, counts):
        if not mask:
            continue
        release, fuse, cloud, label, age = state
        event = geometry.Event(
            track.platform, track.heading, track.speed, age, release, fuse, cloud,
            mask, tuple(count), label, "dense_fixed_track_age",
        )
        key = (round(release / .02), round(fuse / .02), label)
        old = unique.get(key)
        if old is None or (event.mask.bit_count(), min(event.counts)) > (
                old.mask.bit_count(), min(old.counts)):
            unique[key] = event
    return sorted(unique.values(), key=lambda row: (
        row.mask.bit_count(), row.counts[row.label], min(row.counts), -row.release
    ), reverse=True)[:limit]


def compatible(events: tuple[global_pilot.GlobalEvent, ...]) -> bool:
    ordered = sorted(events, key=lambda row: row.event.release)
    return all(v.event.release - u.event.release >= 1. - q5.TIME_TOL
               for u, v in zip(ordered[:-1], ordered[1:]))


def search_track_plans(track: geometry.Track, events: list[global_pilot.GlobalEvent],
                       base_mask: int, times: np.ndarray, time_universe: list[int],
                       proxy_step_s: float, beam: int = TRACK_PLAN_BEAM,
                       required_events: tuple[global_pilot.GlobalEvent, ...] = ()) -> list[ProxyPlan]:
    score_cache = {}

    def scored(mask: int) -> tuple[tuple, dict]:
        combined = base_mask | mask
        if combined not in score_cache:
            metrics = proxy_metrics(combined, times, time_universe, proxy_step_s)
            score_cache[combined] = (metric_key(metrics), metrics)
        return score_cache[combined]

    required_keys = {
        (round(row.event.release, 9), round(row.event.fuse, 9), row.event.label)
        for row in required_events
    }
    ranked_events = [row for row in events if (
        round(row.event.release, 9), round(row.event.fuse, 9), row.event.label
    ) not in required_keys]
    ranked_events = sorted(ranked_events, key=lambda row: scored(row.mask)[0], reverse=True)[:EVENTS_PER_TRACK]
    required_mask = 0
    for row in required_events:
        required_mask |= row.mask
    required_events = tuple(sorted(required_events, key=lambda item: item.event.release))
    states = [(required_mask, required_events, -1)]
    plans = [ProxyPlan(
        track, required_events, required_mask, base_mask | required_mask,
        scored(required_mask)[0],
    )] if required_events else []
    for _depth in range(1, 3 - len(required_events) + 1):
        candidates = {}
        for mask, chosen, last_index in states:
            for index in range(last_index + 1, len(ranked_events)):
                event = ranked_events[index]
                selection = (*chosen, event)
                if not compatible(selection):
                    continue
                new_mask = mask | event.mask
                old = candidates.get(new_mask)
                if old is None:
                    candidates[new_mask] = (new_mask, selection, index)
        states = sorted(candidates.values(), key=lambda row: scored(row[0])[0], reverse=True)[:beam]
        plans.extend(ProxyPlan(
            track, tuple(sorted(row[1], key=lambda item: item.event.release)),
            row[0], base_mask | row[0], scored(row[0])[0],
        ) for row in states[:PLANS_PER_TRACK])
        if not states:
            break
    unique = {}
    for plan in plans:
        signature = tuple((round(row.event.release, 8), round(row.event.fuse, 8), row.event.label)
                          for row in plan.events)
        unique.setdefault(signature, plan)
    return sorted(unique.values(), key=lambda row: row.score, reverse=True)[:PLANS_PER_TRACK]


def decision_from_proxy_plan(seed: q5.Decision, plan: ProxyPlan) -> q5.Decision:
    return decision_from_proxy_plans(seed, (plan,))


def decision_from_proxy_plans(seed: q5.Decision, plans: tuple[ProxyPlan, ...]) -> q5.Decision:
    platforms = {plan.track.platform for plan in plans}
    if len(platforms) != len(plans):
        raise ValueError("duplicate platform plans")
    headings, speeds = list(seed.headings_rad), list(seed.speeds_mps)
    bombs = [row for row in seed.bombs if row.platform not in platforms]
    for plan in plans:
        i = plan.track.platform
        headings[i], speeds[i] = plan.track.heading % (2 * math.pi), plan.track.speed
        bombs.extend(q5.Bomb(i, row.event.label, row.event.release, row.event.fuse)
                     for row in plan.events)
    decision = q5.Decision(
        tuple(headings), tuple(speeds),
        tuple(sorted(bombs, key=lambda row: (row.platform, row.release_s))),
        "multi_event_fixed_track_plan" if len(plans) == 1 else "multi_platform_fixed_track_exchange",
    )
    q5.validate(decision)
    return decision


def strict_summary(decision: q5.Decision, mesh=None) -> dict:
    result = q5.evaluate(decision, q5.PROBE, mesh)
    return {
        "longest_continuous_s": result["longest_continuous_s"],
        "longest_interval_s": result["longest_interval_s"],
        "total_intersection_s": result["total_intersection_s"],
        "intersection_intervals_s": result["intersection_intervals_s"],
        "durations_s": result["durations_s"],
        "minimum_missile_duration_s": result["minimum_missile_duration_s"],
        "sum_duration_missile_s": result["sum_duration_missile_s"],
    }


def report_markdown(payload: dict) -> str:
    baseline = payload["baseline_strict_probe"]
    best = payload["best_strict_probe"]
    lines = [
        "# Q5 多事件联合覆盖最长连续区间 pilot", "",
        f"状态：`{payload['status']}`；用时 `{payload['elapsed_s']:.3f} s`。", "",
        f"- 基线严格最长连续区间：`{baseline['longest_continuous_s']:.9f} s`，"
        f"`{baseline['longest_interval_s']}`。",
        f"- 本轮最优严格最长连续区间：`{best['longest_continuous_s']:.9f} s`，"
        f"`{best['longest_interval_s']}`。",
        f"- 提升：`{payload['improvement_over_baseline_s']:.9f} s`。",
        f"- 最优方案烟幕干扰弹数：`{payload['best_decision']['active_bomb_count']}`。", "",
        "## 最优固定航迹计划", "",
    ]
    for row in payload["best_decision"]["platforms"]:
        labels = ",".join(item["label"] for item in row["bombs"]) or "无"
        lines.append(
            f"- {row['platform']}：航向 `{row['heading_deg']:.6f}°`，速度 `{row['speed_mps']:.6f} m/s`，"
            f"投弹 `{len(row['bombs'])}` 枚，标签 `{labels}`。"
        )
    lines.extend([
        "", "## 联合覆盖语义", "",
        "代理位集和严格核均先对全部有效烟团取最小有限视线段距离，因而允许多云分别覆盖目标表面的不同部分。最终时长只取三导弹同时全遮蔽集合的最长连通分支，不累加分离区间。", "",
        "烟团选择不是在整个区间内固定不变，也不要求每个时刻存在一团烟幕能够单独遮住整个目标。判定允许“前一团单独完整遮蔽 → 两团分别遮挡部分表面并联合完整遮蔽 → 后一团单独完整遮蔽”的连续接力；相应时序已纳入专项回归测试。", "",
        "## 主张边界", "",
        "- 严格候选是当前圆柱表面 PROBE 层下的可行下界；若要升级为正式结果，仍需 SCREEN/PRECISE/DENSIFIED 收敛链。",
        "- 本 pilot 搜索了 FY2/FY3/FY4/FY5 的单平台换弹和任意两平台联合换弹，未穷尽三平台及以上联合拓扑。",
        "- 正式 Q5 文件、Q4 和 Q4_v2 均未修改。",
    ])
    return "\n".join(lines) + "\n"


def run(json_path: Path, report_path: Path, wall_time_s: float = 60., proxy_step_s: float = .25) -> dict:
    started = time.perf_counter()
    seed, seed_record = load_seed()
    probe_mesh = q3.surface_mesh(q5.PROBE["n_theta"], q5.PROBE["n_levels"])
    baseline_strict = strict_summary(seed, probe_mesh)
    if baseline_strict["longest_continuous_s"] < seed_record["longest_continuous_s"] - .02:
        raise q5.Q5Error("Q5_MULTI_EVENT_SEED_DRIFT", str(baseline_strict))
    left = float(baseline_strict["longest_interval_s"][0])
    search_right = min(service.HORIZON_S, left + 20.)
    times = np.arange(left, search_right + 1e-12, proxy_step_s)
    if times[-1] < search_right - 1e-10:
        times = np.append(times, search_right)
    proxy_mesh = q3.surface_mesh(PROXY_THETA, PROXY_LEVELS)
    missiles, visible, time_universe, _ = global_pilot.build_time_geometry(times, proxy_mesh)
    baseline_mask = 0
    baseline_platform_masks = {i: 0 for i in range(5)}
    for bomb in seed.bombs:
        track = geometry.Track(
            bomb.platform, seed.headings_rad[bomb.platform], seed.speeds_mps[bomb.platform],
            "fixed_baseline_track", -1, -1,
        )
        item_mask = global_event(
            track, event_from_bomb(seed, bomb), times, proxy_mesh, missiles, visible
        ).mask
        baseline_platform_masks[bomb.platform] |= item_mask
        baseline_mask |= item_mask
    baseline_proxy = proxy_metrics(baseline_mask, times, time_universe, proxy_step_s)
    anchor_left = max(left, baseline_strict["longest_interval_s"][1] - 1.)
    track_anchors = [float(v) for v in np.arange(anchor_left, min(search_right, anchor_left + 8.) + 1e-9, 2.)]
    event_anchor_times = np.arange(max(left, anchor_left - 2.), search_right + 1e-9, EVENT_ANCHOR_STEP_S)
    track_libraries = {
        i: candidate_tracks(seed, proxy_mesh, track_anchors, i)
        for i in SEARCH_PLATFORMS
    }
    total_tracks = sum(len(rows) for rows in track_libraries.values())
    emit(
        "multi_event_start", baseline_strict=baseline_strict,
        baseline_proxy=baseline_proxy, search_interval_s=[left, search_right],
        proxy_time_count=len(times), surface_point_count=len(proxy_mesh.points),
        search_platforms=[q5.NAMES[i] for i in SEARCH_PLATFORMS],
        track_count=total_tracks, wall_time_s=wall_time_s,
    )
    proxy_plans = []
    completed_tracks = 0
    stopped_early = False
    platform_track_counts = {}
    for search_platform in SEARCH_PLATFORMS:
        if stopped_early:
            break
        base_mask = 0
        for bomb in seed.bombs:
            if bomb.platform == search_platform:
                continue
            fixed_track = geometry.Track(
                bomb.platform, seed.headings_rad[bomb.platform], seed.speeds_mps[bomb.platform],
                "fixed_baseline_track", -1, -1,
            )
            base_mask |= global_event(
                fixed_track, event_from_bomb(seed, bomb), times, proxy_mesh, missiles, visible
            ).mask
        seed_track = geometry.Track(
            search_platform, seed.headings_rad[search_platform], seed.speeds_mps[search_platform],
            "seed_exact_track", -1, -1,
        )
        seed_platform_events = [
            event_from_bomb(seed, row) for row in q5.by_platform(seed, search_platform)
        ]
        seed_key = track_key(seed_track)
        platform_completed = 0
        for track in track_libraries[search_platform]:
            if time.perf_counter() - started >= wall_time_s - 10.:
                stopped_early = True
                break
            is_seed_track = track_key(track) == seed_key
            exact = seed_platform_events if is_seed_track else []
            raw_events = collect_track_events(track, event_anchor_times, proxy_mesh, exact)
            if is_seed_track:
                dense_times = np.arange(
                    max(left, baseline_strict["longest_interval_s"][1] - .5),
                    min(search_right, baseline_strict["longest_interval_s"][1] + 4.) + 1e-10,
                    .25,
                )
                for observation_s in dense_times:
                    raw_events.extend(dense_event_library(
                        track, geometry.Slice(float(observation_s), proxy_mesh)
                    ))
                unique_raw = {}
                for event in raw_events:
                    key = (round(event.release / .02), round(event.fuse / .02), event.label)
                    old = unique_raw.get(key)
                    if old is None or (event.mask.bit_count(), min(event.counts)) > (
                            old.mask.bit_count(), min(old.counts)):
                        unique_raw[key] = event
                raw_events = sorted(unique_raw.values(), key=lambda row: (
                    row.mask.bit_count(), row.counts[row.label], min(row.counts), -row.release
                ), reverse=True)
            raw_events = raw_events[:EVENTS_PER_TRACK * 2]
            global_events = []
            for event in raw_events:
                item = global_event(track, event, times, proxy_mesh, missiles, visible)
                if item.mask:
                    global_events.append(item)
            exact_global = tuple(
                global_event(track, event, times, proxy_mesh, missiles, visible)
                for event in exact
            )
            if is_seed_track and len(exact_global) >= 2:
                required_sets = [
                    tuple(rows) for rows in itertools.combinations(exact_global, len(exact_global) - 1)
                ]
                required_sets.append(exact_global)
            elif is_seed_track:
                required_sets = [exact_global]
            else:
                required_sets = [tuple()]
            plans = []
            for required in required_sets:
                plans.extend(search_track_plans(
                    track, global_events, base_mask, times, time_universe, proxy_step_s,
                    required_events=required,
                ))
            plans.sort(key=lambda row: row.score, reverse=True)
            proxy_plans.extend(plans[:PLANS_PER_TRACK * 2])
            completed_tracks += 1
            platform_completed += 1
            best_proxy = plans[0].score[0] if plans else 0.
            emit(
                "multi_event_track_complete", completed=completed_tracks, total=total_tracks,
                platform=q5.NAMES[search_platform], track_source=track.source,
                heading_deg=math.degrees(track.heading), speed_mps=track.speed,
                raw_event_count=len(raw_events), global_event_count=len(global_events),
                retained_plan_count=len(plans), best_proxy_continuous_s=best_proxy,
                elapsed_s=time.perf_counter() - started,
                remaining_budget_s=max(0., wall_time_s - (time.perf_counter() - started)),
            )
        platform_track_counts[q5.NAMES[search_platform]] = platform_completed
    proxy_plans.sort(key=lambda row: row.score, reverse=True)
    candidate_entries = [{
        "plans": (plan,), "combined_mask": plan.combined_mask,
        "metrics": proxy_metrics(plan.combined_mask, times, time_universe, proxy_step_s),
    } for plan in proxy_plans]
    plans_by_platform = {
        i: [plan for plan in proxy_plans if plan.track.platform == i][:18]
        for i in SEARCH_PLATFORMS
    }
    pair_candidate_count = 0
    for first_platform, second_platform in itertools.combinations(SEARCH_PLATFORMS, 2):
        unaffected_mask = 0
        for platform_index, mask in baseline_platform_masks.items():
            if platform_index not in (first_platform, second_platform):
                unaffected_mask |= mask
        for first in plans_by_platform[first_platform]:
            for second in plans_by_platform[second_platform]:
                combined_mask = unaffected_mask | first.mask | second.mask
                metrics = proxy_metrics(combined_mask, times, time_universe, proxy_step_s)
                candidate_entries.append({
                    "plans": (first, second), "combined_mask": combined_mask,
                    "metrics": metrics,
                })
                pair_candidate_count += 1
    candidate_entries.sort(key=lambda row: metric_key(row["metrics"]), reverse=True)
    shortlisted = []
    seen_decisions = set()
    for entry in candidate_entries:
        decision = decision_from_proxy_plans(seed, entry["plans"])
        key = q5.signature(decision)
        if key not in seen_decisions:
            shortlisted.append((entry, decision))
            seen_decisions.add(key)
        if len(shortlisted) >= STRICT_SHORTLIST:
            break
    strict_rows = [{
        "source": "baseline", "decision": seed, "proxy": baseline_proxy,
        "strict": baseline_strict, "plan": None,
    }]
    for ordinal, (entry, decision) in enumerate(shortlisted, 1):
        if time.perf_counter() - started >= wall_time_s - 3.:
            stopped_early = True
            break
        strict = strict_summary(decision, probe_mesh)
        metrics = entry["metrics"]
        strict_rows.append({
            "source": "generated", "decision": decision, "proxy": metrics,
            "strict": strict, "plans": entry["plans"],
        })
        emit(
            "multi_event_strict_candidate", completed=ordinal, total=len(shortlisted),
            proxy_continuous_s=metrics["longest_full_node_run_s"],
            strict_continuous_s=strict["longest_continuous_s"],
            strict_interval_s=strict["longest_interval_s"],
            active_bomb_count=len(decision.bombs), elapsed_s=time.perf_counter() - started,
        )
    strict_rows.sort(key=lambda row: (
        row["strict"]["longest_continuous_s"], row["strict"]["total_intersection_s"],
        row["strict"]["sum_duration_missile_s"], row["strict"]["minimum_missile_duration_s"],
    ), reverse=True)
    best = strict_rows[0]
    payload = {
        "schema_version": "1.0", "spec_id": SPEC_ID,
        "status": "budget_partial" if stopped_early else "pilot_complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "longest connected interval of strict simultaneous full obscuration of all three missiles",
        "baseline_seed_record": seed_record,
        "baseline_strict_probe": baseline_strict,
        "baseline_proxy": baseline_proxy,
        "best_strict_probe": best["strict"],
        "best_proxy": best["proxy"],
        "best_decision": q5.decision_record(best["decision"]),
        "improvement_over_baseline_s": (
            best["strict"]["longest_continuous_s"] - baseline_strict["longest_continuous_s"]
        ),
        "search": {
            "search_platforms": [q5.NAMES[i] for i in SEARCH_PLATFORMS],
            "search_interval_s": [left, search_right],
            "proxy_time_count": len(times), "proxy_step_s": proxy_step_s,
            "proxy_mesh_theta": PROXY_THETA, "proxy_mesh_levels": PROXY_LEVELS,
            "proxy_surface_point_count": len(proxy_mesh.points),
            "event_anchor_step_s": EVENT_ANCHOR_STEP_S,
            "candidate_track_count": total_tracks, "completed_track_count": completed_tracks,
            "completed_tracks_by_platform": platform_track_counts,
            "proxy_plan_count": len(proxy_plans),
            "two_platform_proxy_candidate_count": pair_candidate_count,
            "combined_candidate_entry_count": len(candidate_entries),
            "strict_shortlist_limit": STRICT_SHORTLIST,
            "strict_evaluated_generated_count": sum(row["source"] == "generated" for row in strict_rows),
            "track_plan_beam": TRACK_PLAN_BEAM, "events_per_track": EVENTS_PER_TRACK,
            "plans_per_track": PLANS_PER_TRACK, "wall_time_s": wall_time_s,
            "deterministic": True, "random_seed": None,
        },
        "strict_candidates": [{
            "source": row["source"], "proxy": row["proxy"], "strict": row["strict"],
            "decision": q5.decision_record(row["decision"]),
        } for row in strict_rows[:8]],
        "input_identity": {
            "data/A题.pdf": q5.sha(ROOT / "data/A题.pdf"),
            "docs/q5_longest_pilot.json": q5.sha(SEED_PATH),
            "docs/q5_service_dwell_candidates.json": q5.sha(SERVICE_PATH),
            "planning/44_q5_multi_event_continuous_spec.md": q5.sha(ROOT / "planning/44_q5_multi_event_continuous_spec.md"),
            "src/q5/solve.py": q5.sha(ROOT / "src/q5/solve.py"),
            "src/q5/global_window_pilot.py": q5.sha(ROOT / "src/q5/global_window_pilot.py"),
            "src/q5/multi_event_continuous.py": q5.sha(Path(__file__).resolve()),
        },
        "claims": {
            "multi_event_fixed_track": True,
            "multi_cloud_partial_surface_union": True,
            "one_and_two_platform_plan_exchanges": True,
            "longest_connected_interval_objective": True,
            "strict_probe_verified": True,
            "all_platform_topologies_exhausted": False,
            "formal_q5_result": False,
            "global_optimality": False,
        },
        "software": {
            "python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "elapsed_s": time.perf_counter() - started,
    }
    service.atomic_write(json_path, json.dumps(q5.ready(payload), ensure_ascii=False, indent=2))
    service.atomic_write(report_path, report_markdown(payload))
    emit(
        "multi_event_complete", status=payload["status"],
        baseline_continuous_s=baseline_strict["longest_continuous_s"],
        best_continuous_s=best["strict"]["longest_continuous_s"],
        improvement_s=payload["improvement_over_baseline_s"],
        completed_track_count=completed_tracks, strict_candidate_count=len(strict_rows),
        elapsed_s=payload["elapsed_s"],
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=ROOT / "docs/q5_multi_event_continuous.json")
    parser.add_argument("--report", type=Path, default=ROOT / "docs/q5_multi_event_continuous.md")
    parser.add_argument("--wall-time-s", type=float, default=60.)
    parser.add_argument("--proxy-step-s", type=float, default=.25)
    args = parser.parse_args()
    try:
        run(args.json.resolve(), args.report.resolve(), max(15., args.wall_time_s),
            max(.1, args.proxy_step_s))
    except q5.Q5Error as exc:
        emit("multi_event_fail", code=exc.code, message=str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
