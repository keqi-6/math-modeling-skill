#!/usr/bin/env python3
"""Q5 full-horizon rolling-window feasibility pilot.

This module deliberately does not write the formal Q5 result.  It builds a
deterministic, coarse full-horizon plan library, searches duration/start-time
windows, and sends only the best proxy candidates through the existing strict
continuous evaluator.  A missed duration is therefore ``not_found_under_budget``
rather than a proof of infeasibility.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.q3 import selection_pilot as q3  # noqa: E402
from src.q5 import geometry_pilot as geometry  # noqa: E402
from src.q5 import solve as q5  # noqa: E402


SPEC_ID = "SPEC-Q5-GLOBAL-WINDOW-PILOT-5.0"
HORIZON_S = min(q5.ARRIVAL_TIMES)
DURATION_LADDER_S = (10., 15., 20., 25., 30., 35., 40., 45., 50., 55., 60.)


@dataclass(frozen=True)
class GlobalEvent:
    event: geometry.Event
    mask: int
    explosion_s: float


@dataclass(frozen=True)
class GlobalTrackSeed:
    track: geometry.Track
    source_times: tuple[float, ...]
    seed_events: tuple[geometry.Event, ...]
    source_score: int


@dataclass(frozen=True)
class TrackPlan:
    platform: int
    heading: float
    speed: float
    events: tuple[GlobalEvent, ...]
    mask: int
    source: str


def emit(stage: str, **values) -> None:
    print(json.dumps({"stage": stage, **q5.ready(values)}, ensure_ascii=False), flush=True)


def window_starts(duration_s: float, step_s: float = 5.) -> list[float]:
    latest = HORIZON_S - duration_s
    if latest < -1e-9:
        return []
    values = list(np.arange(0., max(0., latest) + 1e-12, step_s))
    values.append(max(0., latest))
    return sorted(set(round(float(value), 9) for value in values))


def window_catalog(durations=DURATION_LADDER_S, start_step_s=5.) -> list[dict]:
    return [
        {"duration_s": float(duration), "start_s": float(start), "end_s": float(start + duration)}
        for duration in durations
        for start in window_starts(float(duration), start_step_s)
    ]


def proxy_times(windows: list[dict], base_step_s=2.) -> np.ndarray:
    values = {0., float(HORIZON_S)}
    values.update(float(value) for value in np.arange(0., HORIZON_S + 1e-12, base_step_s))
    for window in windows:
        values.add(min(HORIZON_S, max(0., float(window["start_s"]))))
        values.add(min(HORIZON_S, max(0., float(window["end_s"]))))
    return np.asarray(sorted(value for value in values if 0. <= value <= HORIZON_S + 1e-9), float)


def track_key(track: geometry.Track, heading_step=.02, speed_step=2.) -> tuple[int, int]:
    return round((track.heading % (2 * math.pi)) / heading_step), round(track.speed / speed_step)


def collect_tracks(mesh, anchors: np.ndarray, per_platform=10) -> tuple[list[list[GlobalTrackSeed]], list[dict]]:
    incumbent, _ = q5.registered_incumbent()
    libraries, diagnostics = [], []
    for i in range(5):
        buckets: dict[tuple[int, int], dict] = {}
        current = geometry.Track(i, incumbent.headings_rad[i], incumbent.speeds_mps[i],
                                 "historical_track_guard", -1, -1)
        buckets[track_key(current)] = {
            "track": current, "times": set(), "sources": {current.source}, "events": {}, "score": 0
        }
        proposed = feasible = 0
        for t in anchors:
            sl = geometry.Slice(float(t), mesh)
            c3, c3_stats = q5.c3_tracks(i, sl)
            occupied = {(round(track.heading, 12), round(track.speed, 9)) for track in c3}
            guards, guard_stats = q5.c2_guard_tracks(i, sl, occupied)
            proposed += int(c3_stats["proposed"]) + int(guard_stats["sampled_tracks"])
            feasible += int(c3_stats["kinematically_feasible"]) + int(guard_stats["selected_tracks"])
            scored = []
            for track in [*c3[:18], *guards[:4]]:
                events, _ = q5.event_library(track, sl)
                score = max((event.mask.bit_count() for event in events), default=0)
                scored.append((track, events, score))
            chosen = []
            for source, count in (("C3_surface_tube", 2), ("C2_complete_guard", 1)):
                rows = sorted((row for row in scored if row[0].source == source),
                              key=lambda row: (row[2], len(row[1])), reverse=True)
                chosen.extend(rows[:count])
            for track, events, score in chosen:
                key = track_key(track)
                row = buckets.setdefault(key, {
                    "track": track, "times": set(), "sources": set(), "events": {}, "score": 0
                })
                row["times"].add(round(float(t), 6))
                row["sources"].add(track.source)
                row["score"] = max(row["score"], int(score))
                for event in events:
                    event_key = (round(event.release / .02), round(event.fuse / .02))
                    old = row["events"].get(event_key)
                    if old is None or event.mask.bit_count() > old.mask.bit_count():
                        row["events"][event_key] = event
        rows = list(buckets.values())
        c3_rows = [row for row in rows if "C3_surface_tube" in row["sources"] and row["times"]]
        guard_rows = [row for row in rows if "C2_complete_guard" in row["sources"] and row["times"]]
        selected_rows = []
        for target in np.linspace(float(anchors[0]), float(anchors[-1]), max(1, per_platform - 2)):
            available = [row for row in c3_rows if row not in selected_rows]
            if not available:
                break
            row = min(available, key=lambda item: (
                abs(float(np.mean(list(item["times"]))) - target), -item["score"], -len(item["events"])
            ))
            selected_rows.append(row)
        if guard_rows:
            selected_rows.append(max(guard_rows, key=lambda row: (row["score"], len(row["events"]))))
        historical = buckets[track_key(current)]
        selected_rows.append(historical)
        unique_selected = []
        seen = set()
        for row in selected_rows:
            key = track_key(row["track"])
            if key not in seen:
                unique_selected.append(row)
                seen.add(key)
        if len(unique_selected) < per_platform:
            remainder = sorted((row for row in rows if track_key(row["track"]) not in seen),
                               key=lambda row: (row["score"], len(row["events"]), len(row["times"])), reverse=True)
            unique_selected.extend(remainder[:per_platform - len(unique_selected)])
        selected = [GlobalTrackSeed(
            row["track"], tuple(sorted(row["times"])), tuple(row["events"].values()), int(row["score"])
        ) for row in unique_selected[:per_platform]]
        libraries.append(selected)
        record = {
            "platform": q5.NAMES[i], "anchor_count": len(anchors), "raw_cluster_count": len(rows),
            "selected_track_count": len(selected), "proposed_state_count": proposed,
            "kinematically_feasible_state_count": feasible,
            "selected_c3_track_count": sum(seed.track.source == "C3_surface_tube" for seed in selected),
            "selected_guard_track_count": sum(seed.track.source == "C2_complete_guard" for seed in selected),
            "source_time_min_s": min((min(seed.source_times) for seed in selected if seed.source_times), default=None),
            "source_time_max_s": max((max(seed.source_times) for seed in selected if seed.source_times), default=None),
            "historical_track_retained": track_key(current) in {track_key(seed.track) for seed in selected},
        }
        diagnostics.append(record)
        emit("global_track_library", completed=i + 1, total=5, **record)
    return libraries, diagnostics


def build_time_geometry(times: np.ndarray, mesh) -> tuple[list[np.ndarray], list[np.ndarray], list[int], int]:
    missiles, visible, time_universe = [], [], []
    n = len(mesh.points)
    universe = 0
    for time_index, t in enumerate(times):
        missile_rows = np.vstack([geometry.missile(j, float(t)) for j in range(3)])
        visible_rows = np.vstack([q3.visibility_mask(missile_rows[j:j + 1], mesh)[0] for j in range(3)])
        local = 0
        for j in range(3):
            local |= geometry.bits(visible_rows[j]) << ((time_index * 3 + j) * n)
        missiles.append(missile_rows)
        visible.append(visible_rows)
        time_universe.append(local)
        universe |= local
    return missiles, visible, time_universe, universe


def event_global_mask(track: geometry.Track, event: geometry.Event, times: np.ndarray, mesh,
                      missiles: list[np.ndarray], visible: list[np.ndarray]) -> int:
    explosion_s = event.release + event.fuse
    active_indices = np.flatnonzero(
        (times >= explosion_s - q5.TIME_TOL)
        & (times <= np.minimum(explosion_s + q5.p().smoke_duration, HORIZON_S) + q5.TIME_TOL)
    )
    if not len(active_indices):
        return 0
    direction = np.array([math.cos(track.heading), math.sin(track.heading), 0.])
    explosion = q5.ORIGINS[track.platform] + track.speed * explosion_s * direction
    explosion[2] = q5.ORIGINS[track.platform, 2] - .5 * q5.p().gravity * event.fuse ** 2
    clouds = np.repeat(explosion.reshape(1, 3), len(active_indices), axis=0)
    clouds[:, 2] -= q5.p().smoke_sink_speed * (times[active_indices] - explosion_s)
    mask = 0
    n = len(mesh.points)
    for local_index, time_index in enumerate(active_indices):
        for j in range(3):
            distance = q3._distance_to_segments(
                clouds[local_index:local_index + 1], missiles[time_index][j:j + 1], mesh
            )[0]
            hits = (distance <= q5.p().smoke_radius + 1e-12) & visible[time_index][j]
            mask |= geometry.bits(hits) << ((int(time_index) * 3 + j) * n)
    return mask


def temporal_event_sample(events: list[geometry.Event], limit=42) -> list[geometry.Event]:
    unique = {}
    for event in events:
        key = (round(event.release / .05), round(event.fuse / .05))
        old = unique.get(key)
        if old is None or (event.mask.bit_count(), min(event.counts)) > (old.mask.bit_count(), min(old.counts)):
            unique[key] = event
    buckets: dict[int, list[geometry.Event]] = {}
    for event in unique.values():
        buckets.setdefault(int((event.release + event.fuse) // 4.), []).append(event)
    sampled = []
    for bucket in sorted(buckets):
        rows = sorted(buckets[bucket], key=lambda event: (
            event.mask.bit_count(), min(event.counts), -event.release
        ), reverse=True)
        sampled.extend(rows[:3])
    if len(sampled) > limit:
        indices = np.linspace(0, len(sampled) - 1, limit, dtype=int)
        sampled = [sampled[index] for index in sorted(set(indices.tolist()))]
    return sampled


def incumbent_proxy_plans(times, mesh, missiles, visible) -> list[TrackPlan]:
    incumbent, _ = q5.registered_incumbent()
    plans = []
    for i in range(5):
        track = geometry.Track(i, incumbent.headings_rad[i], incumbent.speeds_mps[i],
                               "historical_incumbent_plan", -1, -1)
        global_events = []
        for bomb in q5.by_platform(incumbent, i):
            point = q5.explosion_point(incumbent, bomb)
            event = geometry.Event(i, track.heading, track.speed, 0., bomb.release_s, bomb.fuse_s,
                                   tuple(map(float, point)), 0, (0, 0, 0), bomb.label,
                                   "historical_incumbent_plan")
            mask = event_global_mask(track, event, times, mesh, missiles, visible)
            global_events.append(GlobalEvent(event, mask, bomb.release_s + bomb.fuse_s))
        combined_mask = 0
        for item in global_events:
            combined_mask |= item.mask
        plans.append(TrackPlan(i, track.heading, track.speed, tuple(global_events), combined_mask,
                               "historical_incumbent_plan"))
    return plans


def build_event_libraries(track_libraries, event_times, times, mesh, missiles, visible,
                          started, wall_time_s) -> tuple[list[list[tuple[geometry.Track, list[GlobalEvent]]]], list[dict], bool]:
    slices = {round(float(t), 9): geometry.Slice(float(t), mesh) for t in event_times}
    libraries, diagnostics = [], []
    total_tracks = sum(map(len, track_libraries))
    completed = 0
    exhausted = False
    for i, track_seeds in enumerate(track_libraries):
        platform_rows = []
        for seed in track_seeds:
            track = seed.track
            if time.perf_counter() - started >= wall_time_s:
                exhausted = True
                break
            raw_events = list(seed.seed_events)
            for t in event_times:
                events, _ = q5.event_library(track, slices[round(float(t), 9)])
                raw_events.extend(events)
            sampled = temporal_event_sample(raw_events)
            global_events = []
            for event in sampled:
                mask = event_global_mask(track, event, times, mesh, missiles, visible)
                if mask:
                    global_events.append(GlobalEvent(event, mask, event.release + event.fuse))
            platform_rows.append((track, global_events))
            completed += 1
            record = {
                "platform": q5.NAMES[i], "track_source": track.source,
                "source_times_s": seed.source_times, "source_score": seed.source_score,
                "raw_event_count": len(raw_events), "sampled_event_count": len(sampled),
                "nonzero_global_event_count": len(global_events),
            }
            diagnostics.append(record)
            emit("global_event_library", completed=completed, total=total_tracks,
                 elapsed_s=time.perf_counter() - started, **record)
        libraries.append(platform_rows)
        if exhausted:
            libraries.extend([] for _ in range(4 - i))
            break
    return libraries, diagnostics, exhausted


def indices_for_window(times: np.ndarray, start_s: float, end_s: float) -> list[int]:
    return np.flatnonzero((times >= start_s - 1e-9) & (times <= end_s + 1e-9)).astype(int).tolist()


def mask_metrics(mask: int, indices: list[int], time_universe: list[int]) -> tuple[int, float, float, int]:
    ratios = []
    covered = total = 0
    for index in indices:
        local = time_universe[index]
        denominator = local.bit_count()
        numerator = (mask & local).bit_count()
        covered += numerator
        total += denominator
        ratios.append(numerator / denominator if denominator else 0.)
    full = int(all(ratio >= 1. - 1e-15 for ratio in ratios))
    return full, min(ratios, default=0.), covered / total if total else 0., covered


def plan_library_for_track(track, global_events, indices, time_universe, event_limit=28, beam=48):
    ranked_events = sorted(global_events, key=lambda item: mask_metrics(item.mask, indices, time_universe), reverse=True)
    ranked_events = ranked_events[:event_limit]
    states = [(0, tuple(), -1)]
    plans = []
    for depth in range(1, 4):
        candidates = {}
        for mask, chosen, last_index in states:
            for index in range(last_index + 1, len(ranked_events)):
                event = ranked_events[index]
                events = tuple(sorted((*chosen, event), key=lambda item: item.event.release))
                if any(v.event.release - u.event.release < 1. - q5.TIME_TOL
                       for u, v in zip(events[:-1], events[1:])):
                    continue
                new_mask = mask | event.mask
                old = candidates.get(new_mask)
                row = (new_mask, events, index)
                if old is None or len(events) < len(old[1]):
                    candidates[new_mask] = row
        states = sorted(candidates.values(),
                        key=lambda row: (*mask_metrics(row[0], indices, time_universe), -len(row[1])),
                        reverse=True)[:beam]
        plans.extend(TrackPlan(track.platform, track.heading, track.speed, row[1], row[0], track.source)
                     for row in states)
        if not states:
            break
    return plans


def platform_plan_libraries(event_libraries, indices, time_universe, forced_plans=None, per_platform=36):
    result = []
    for platform, rows in enumerate(event_libraries):
        plans = [TrackPlan(platform, 0., 70., tuple(), 0, "empty")]
        per_track_best = []
        for track, events in rows:
            track_plans = plan_library_for_track(track, events, indices, time_universe)
            track_plans.sort(key=lambda plan: (
                *mask_metrics(plan.mask, indices, time_universe), -len(plan.events)
            ), reverse=True)
            per_track_best.extend(track_plans[:2])
            plans.extend(track_plans)
        if forced_plans is not None:
            plans.append(forced_plans[platform])
        unique = {}
        for plan in plans:
            old = unique.get(plan.mask)
            if old is None or len(plan.events) < len(old.events):
                unique[plan.mask] = plan
        ordered = sorted(unique.values(), key=lambda plan: (
            *mask_metrics(plan.mask, indices, time_universe), -len(plan.events)
        ), reverse=True)
        mandatory = []
        mandatory_masks = set()
        for plan in [*(per_track_best), *(([forced_plans[platform]] if forced_plans is not None else []))]:
            if plan.mask not in mandatory_masks:
                mandatory.append(plan)
                mandatory_masks.add(plan.mask)
        selected = mandatory[:per_platform]
        for plan in ordered:
            if len(selected) >= per_platform:
                break
            if plan.mask not in {item.mask for item in selected}:
                selected.append(plan)
        result.append(selected)
    return result


def combine_plans(libraries, indices, time_universe, beam=1800, keep=3):
    states = [(0, tuple())]
    for library in libraries:
        candidates = {}
        for mask, chosen in states:
            for plan in library:
                new_mask = mask | plan.mask
                row = (new_mask, (*chosen, plan))
                old = candidates.get(new_mask)
                bombs = sum(len(item.events) for item in row[1])
                if old is None or bombs < sum(len(item.events) for item in old[1]):
                    candidates[new_mask] = row
        states = sorted(candidates.values(), key=lambda row: (
            *mask_metrics(row[0], indices, time_universe),
            -sum(len(item.events) for item in row[1]),
        ), reverse=True)[:beam]
        if not states:
            break
    return states[:keep]


def decision_from_plans(plans: tuple[TrackPlan, ...], source: str) -> q5.Decision:
    incumbent, _ = q5.registered_incumbent()
    headings, speeds = list(incumbent.headings_rad), list(incumbent.speeds_mps)
    bombs = []
    for plan in plans:
        if plan.events:
            headings[plan.platform] = plan.heading % (2 * math.pi)
            speeds[plan.platform] = plan.speed
        bombs.extend(q5.Bomb(plan.platform, item.event.label, item.event.release, item.event.fuse)
                     for item in plan.events)
    decision = q5.Decision(tuple(headings), tuple(speeds),
                           tuple(sorted(bombs, key=lambda bomb: (bomb.platform, bomb.release_s))), source)
    q5.validate(decision)
    return decision


def strict_summary(decision: q5.Decision) -> dict:
    result = q5.evaluate(decision, q5.PROBE)
    return {
        "longest_continuous_s": result["longest_continuous_s"],
        "longest_interval_s": result["longest_interval_s"],
        "total_intersection_s": result["total_intersection_s"],
        "intersection_intervals_s": result["intersection_intervals_s"],
        "minimum_missile_duration_s": result["minimum_missile_duration_s"],
    }


def run(output: Path, wall_time_s=180., start_step_s=5.) -> dict:
    started = time.perf_counter()
    windows = window_catalog(start_step_s=start_step_s)
    times = proxy_times(windows)
    mesh = q3.surface_mesh(12, 3)
    missiles, visible, time_universe, _ = build_time_geometry(times, mesh)
    forced_incumbent_plans = incumbent_proxy_plans(times, mesh, missiles, visible)
    forced_incumbent_mask = 0
    for plan in forced_incumbent_plans:
        forced_incumbent_mask |= plan.mask
    anchor_times = np.arange(4., HORIZON_S, 4.)
    event_times = np.arange(2., HORIZON_S, 4.)
    emit("global_pilot_start", horizon_s=HORIZON_S, duration_ladder_s=DURATION_LADDER_S,
         window_count=len(windows), proxy_time_count=len(times), surface_point_count=len(mesh.points),
         wall_time_s=wall_time_s)
    incumbent, seed_sha = q5.registered_incumbent()
    incumbent_strict = strict_summary(incumbent)
    incumbent_interval = incumbent_strict["longest_interval_s"]
    incumbent_indices = indices_for_window(times, incumbent_interval[0], incumbent_interval[1])
    incumbent_proxy_metrics = mask_metrics(forced_incumbent_mask, incumbent_indices, time_universe)
    emit("global_incumbent", strict_probe=incumbent_strict,
         proxy_interval_time_count=len(incumbent_indices),
         proxy_interval_full=bool(incumbent_proxy_metrics[0]),
         proxy_interval_min_time_coverage=incumbent_proxy_metrics[1],
         proxy_interval_overall_coverage=incumbent_proxy_metrics[2])
    if not incumbent_proxy_metrics[0]:
        raise q5.Q5Error(
            "Q5_GLOBAL_PROXY_STRICT_GAP",
            "historical strict incumbent is not fully represented by the global proxy mask",
        )
    tracks, track_diagnostics = collect_tracks(mesh, anchor_times)
    events, event_diagnostics, exhausted = build_event_libraries(
        tracks, event_times, times, mesh, missiles, visible, started, wall_time_s
    )
    ladder = []
    best_decision = incumbent
    best_strict = incumbent_strict
    generated_best_decision = None
    generated_best_strict = None
    if not exhausted:
        for duration in DURATION_LADDER_S:
            rows = []
            starts = window_starts(duration, start_step_s)
            for ordinal, start_s in enumerate(starts, 1):
                if time.perf_counter() - started >= wall_time_s:
                    exhausted = True
                    break
                end_s = start_s + duration
                indices = indices_for_window(times, start_s, end_s)
                plan_libraries = platform_plan_libraries(
                    events, indices, time_universe, forced_plans=forced_incumbent_plans
                )
                combinations = combine_plans(plan_libraries, indices, time_universe)
                if not combinations:
                    continue
                candidate_combinations = [*combinations, (forced_incumbent_mask, tuple(forced_incumbent_plans))]
                candidate_combinations.sort(key=lambda row: (
                    *mask_metrics(row[0], indices, time_universe),
                    -sum(len(item.events) for item in row[1]),
                ), reverse=True)
                mask, plans = candidate_combinations[0]
                metrics = mask_metrics(mask, indices, time_universe)
                is_incumbent = all(plan.source == "historical_incumbent_plan" for plan in plans)
                decision = incumbent if is_incumbent else decision_from_plans(
                    plans, f"global_window_T{duration:.0f}_s{start_s:.3f}"
                )
                row = {
                    "start_s": start_s, "end_s": end_s,
                    "proxy_full": bool(metrics[0]), "proxy_min_time_coverage": metrics[1],
                    "proxy_overall_coverage": metrics[2], "proxy_covered_bits": metrics[3],
                    "platform_plan_counts": [len(library) for library in plan_libraries],
                    "active_bomb_count": len(decision.bombs), "decision": decision,
                    "candidate_source": "historical_incumbent" if is_incumbent else "global_generated",
                }
                rows.append(row)
                emit("global_window_progress", duration_s=duration, completed=ordinal, total=len(starts),
                     start_s=start_s, proxy_full=row["proxy_full"],
                     proxy_min_time_coverage=row["proxy_min_time_coverage"],
                     proxy_overall_coverage=row["proxy_overall_coverage"],
                     active_bomb_count=row["active_bomb_count"], elapsed_s=time.perf_counter() - started)
            if not rows:
                ladder.append({"duration_s": duration, "status": "not_evaluated", "window_count": 0})
                if exhausted:
                    break
                continue
            rows.sort(key=lambda row: (
                row["proxy_full"], row["proxy_min_time_coverage"], row["proxy_overall_coverage"],
                -row["active_bomb_count"]
            ), reverse=True)
            winner = rows[0]
            strict = strict_summary(winner["decision"])
            if winner["candidate_source"] == "global_generated" and (
                generated_best_strict is None or (
                    strict["longest_continuous_s"], strict["total_intersection_s"]
                ) > (
                    generated_best_strict["longest_continuous_s"], generated_best_strict["total_intersection_s"]
                )
            ):
                generated_best_decision, generated_best_strict = winner["decision"], strict
            if best_strict is None or (
                strict["longest_continuous_s"], strict["total_intersection_s"]
            ) > (
                best_strict["longest_continuous_s"], best_strict["total_intersection_s"]
            ):
                best_decision, best_strict = winner["decision"], strict
            ladder_row = {
                "duration_s": duration,
                "status": "strict_window_feasible" if strict["longest_continuous_s"] >= duration - .15
                          else "proxy_full_strict_failed" if winner["proxy_full"]
                          else "not_found_under_budget",
                "window_count": len(rows),
                "best_start_s": winner["start_s"], "best_end_s": winner["end_s"],
                "proxy_full": winner["proxy_full"],
                "proxy_min_time_coverage": winner["proxy_min_time_coverage"],
                "proxy_overall_coverage": winner["proxy_overall_coverage"],
                "active_bomb_count": winner["active_bomb_count"],
                "candidate_source": winner["candidate_source"],
                "platform_plan_counts": winner["platform_plan_counts"],
                "strict_probe": strict,
                "decision": q5.decision_record(winner["decision"]),
            }
            ladder.append(ladder_row)
            emit("global_duration_complete", **{k: v for k, v in ladder_row.items() if k != "decision"},
                 elapsed_s=time.perf_counter() - started)
            if exhausted:
                break
    payload = {
        "schema_version": "1.0", "spec_id": SPEC_ID,
        "status": "budget_exhausted" if exhausted else "pilot_complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "role": "S2 full-horizon candidate pilot; not a formal Q5 result",
        "horizon_s": HORIZON_S, "duration_ladder_s": list(DURATION_LADDER_S),
        "budgets": {
            "wall_time_s": wall_time_s, "window_start_step_s": start_step_s,
            "proxy_base_time_step_s": 2., "track_anchor_step_s": 4., "event_anchor_step_s": 4.,
            "mesh_theta": 12, "mesh_levels": 3, "tracks_per_platform": 10,
            "events_per_track": 42, "track_plan_beam": 48, "combination_beam": 1800,
        },
        "incumbent": {
            "seed_sha256": seed_sha,
            "strict_probe": incumbent_strict,
            "proxy_interval_time_count": len(incumbent_indices),
            "proxy_interval_full": bool(incumbent_proxy_metrics[0]),
            "proxy_interval_min_time_coverage": incumbent_proxy_metrics[1],
            "proxy_interval_overall_coverage": incumbent_proxy_metrics[2],
        },
        "track_diagnostics": track_diagnostics,
        "event_diagnostics": event_diagnostics,
        "ladder": ladder,
        "best_strict_probe": best_strict,
        "best_decision": q5.decision_record(best_decision) if best_decision is not None else None,
        "generated_best_strict_probe": generated_best_strict,
        "generated_best_decision": q5.decision_record(generated_best_decision) if generated_best_decision is not None else None,
        "monitoring": {
            "global_horizon_used": bool(len(times) and abs(times[-1] - HORIZON_S) <= 1e-9),
            "historical_window_only": False,
            "completed_duration_levels": len(ladder),
            "planned_duration_levels": len(DURATION_LADDER_S),
            "stop_reason": "wall_time_budget" if exhausted else "completed_ladder",
        },
        "claims": {
            "formal_solution": False, "global_optimality": False,
            "unfound_means_infeasible": False, "continuous_proxy_complete": False,
            "strict_probe_applied_to_each_duration_winner": True,
        },
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "elapsed_s": time.perf_counter() - started,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False,
                                     dir=output.parent, prefix=output.name + ".", suffix=".tmp") as handle:
        handle.write(json.dumps(q5.ready(payload), ensure_ascii=False, indent=2))
        temporary = Path(handle.name)
    os.replace(temporary, output)
    emit("global_pilot_complete", status=payload["status"], completed_duration_levels=len(ladder),
         best_strict_probe=best_strict, elapsed_s=payload["elapsed_s"])
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "docs/q5_global_window_pilot.json")
    parser.add_argument("--wall-time-s", type=float, default=180.)
    parser.add_argument("--start-step-s", type=float, default=5.)
    args = parser.parse_args()
    try:
        run(args.output.resolve(), max(10., args.wall_time_s), max(.5, args.start_step_s))
    except q5.Q5Error as exc:
        emit("global_pilot_fail", code=exc.code, message=str(exc))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
