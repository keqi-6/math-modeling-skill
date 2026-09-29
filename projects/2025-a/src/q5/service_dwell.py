#!/usr/bin/env python3
"""Deterministic fixed-event dwell candidates for the Q5 safe service domain."""
from __future__ import annotations

import argparse
import json
import math
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import brentq, minimize_scalar

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT))

from src.q5 import service_domains as service  # noqa: E402
from src.q5 import solve as q5  # noqa: E402


SPEC_ID = "Q5-FIXED-EVENT-DWELL-1.0"
HORIZON_S = service.HORIZON_S
DEFAULT_LAMBDAS = tuple(float(v) for v in np.linspace(0., 1., 11))
PLACEMENT_FRACTIONS = (-.999999, -.5, 0., .5, .999999)


def minimum_age_gap(platform_index: int, missile_index: int, observation_s: float,
                    lam: float, age_nodes: int = 41) -> dict:
    """Minimize the reachable-section gap over smoke age at fixed lambda."""
    age_cap = min(q5.p().smoke_duration, float(observation_s))
    ages = np.linspace(0., age_cap, max(3, int(age_nodes)))

    def objective(age: float) -> float:
        return float(service.reachable_ball_gap(
            platform_index, missile_index, observation_s, float(age), lam
        )["gap_m2"])

    values = np.asarray([objective(float(age)) for age in ages])
    candidates = [(float(value), float(age)) for value, age in zip(values, ages)]
    # Refine every grid-local minimum.  This avoids assuming that the nonsmooth
    # ring/height distance has a single age minimum.
    for index in range(len(ages)):
        left_value = values[index - 1] if index else math.inf
        right_value = values[index + 1] if index + 1 < len(ages) else math.inf
        if values[index] <= left_value and values[index] <= right_value:
            left = float(ages[max(0, index - 1)])
            right = float(ages[min(len(ages) - 1, index + 1)])
            if right > left + 1e-14:
                result = minimize_scalar(
                    objective, bounds=(left, right), method="bounded",
                    options={"xatol": 1e-11, "maxiter": 100},
                )
                candidates.append((float(result.fun), float(result.x)))
    best_gap, best_age = min(candidates, key=lambda row: row[0])
    reconstructed = service.reachable_ball_gap(
        platform_index, missile_index, observation_s, best_age, lam, reconstruct=True
    )
    reconstructed.update({
        "requested_lambda": float(lam),
        "optimized_gap_m2": best_gap,
        "age_node_count": len(ages),
        "feasible": best_gap <= 1e-8,
        "clearance_m": reconstructed["service_radius_m"]
                       - reconstructed["distance_to_reachable_slice_m"],
    })
    return reconstructed


def fixed_event_cloud(event: dict, time_s: float) -> np.ndarray:
    """Forward cloud centre for one fully fixed physical event."""
    platform_index = q5.NAMES.index(event["platform"])
    origin = np.asarray(q5.ORIGINS[platform_index], float)
    heading = float(event["heading_rad"])
    explosion_s = float(event["explosion_s"])
    fuse_s = float(event["fuse_s"])
    speed = float(event["speed_mps"])
    centre = origin + speed * explosion_s * np.array([
        math.cos(heading), math.sin(heading), 0.
    ])
    centre[2] = origin[2] - .5 * q5.p().gravity * fuse_s ** 2
    centre[2] -= q5.p().smoke_sink_speed * (float(time_s) - explosion_s)
    return centre


def _event_from_cloud(platform_index: int, missile_index: int, observation_s: float,
                      age_s: float, lam: float, cloud: np.ndarray) -> dict | None:
    """Reconstruct a physical event from a point in one reachable slice."""
    sl = service.reachable_slice(platform_index, observation_s, age_s)
    origin = np.asarray(q5.ORIGINS[platform_index], float)
    cloud = np.asarray(cloud, float)
    offset = cloud[:2] - origin[:2]
    radial = float(np.linalg.norm(offset))
    if sl.explosion_s <= 1e-12:
        if radial > 1e-8:
            return None
        speed, heading = 70., 0.
    else:
        speed = radial / sl.explosion_s
        if not 70. - 1e-8 <= speed <= 140. + 1e-8:
            return None
        heading = float(math.atan2(offset[1], offset[0]) % (2 * math.pi))
    explosion_height = cloud[2] + q5.p().smoke_sink_speed * sl.age_s
    if explosion_height < -1e-8 or explosion_height > origin[2] + 1e-8:
        return None
    fuse = math.sqrt(max(0., 2. * (origin[2] - explosion_height) / q5.p().gravity))
    release = sl.explosion_s - fuse
    if release < -1e-8:
        return None
    if release < 0.:
        release = 0.
    missile = service.missile_position(missile_index, observation_s)
    section_centre = missile + lam * (service.TARGET_MIDPOINT - missile)
    section_radius = q5.p().smoke_radius - lam * service.TARGET_ENVELOPE_RADIUS
    certificate = service.ball_service_value(cloud, missile)
    if certificate["value_m2"] > 1e-7:
        return None
    return {
        "platform": q5.NAMES[platform_index], "missile": q5.MISSILE_NAMES[missile_index],
        "observation_s": float(observation_s), "smoke_age_s": float(age_s),
        "explosion_s": sl.explosion_s, "release_s": release, "fuse_s": fuse,
        "heading_rad": heading, "heading_deg": math.degrees(heading),
        "speed_mps": min(140., max(70., speed)), "cloud_centre_m": cloud,
        "service_section_centre_m": section_centre,
        "service_section_radius_m": section_radius,
        "certificate_value_m2": certificate["value_m2"],
        "certificate_lambda": certificate["lambda"],
    }


def placement_events(platform_index: int, missile_index: int, observation_s: float,
                     age_s: float, lam: float) -> list[tuple[float, dict]]:
    """Generate reachable chord placements without privileging the sphere centre."""
    sl = service.reachable_slice(platform_index, observation_s, age_s)
    origin = np.asarray(q5.ORIGINS[platform_index], float)
    missile = service.missile_position(missile_index, observation_s)
    section_centre = missile + lam * (service.TARGET_MIDPOINT - missile)
    section_radius = q5.p().smoke_radius - lam * service.TARGET_ENVELOPE_RADIUS
    initial = np.asarray(service.geometry.MISSILES[missile_index], float)
    missile_velocity = -q5.p().missile_speed * initial / np.linalg.norm(initial)
    relative_velocity = np.array([0., 0., -q5.p().smoke_sink_speed]) \
                        - (1. - lam) * missile_velocity
    norm = float(np.linalg.norm(relative_velocity))
    forward_support = -relative_velocity / norm if norm > 1e-14 else np.array([0., 0., 1.])
    rows = []
    for fraction in PLACEMENT_FRACTIONS:
        desired = section_centre + fraction * section_radius * forward_support
        horizontal = desired[:2] - origin[:2]
        horizontal_norm = float(np.linalg.norm(horizontal))
        radial = min(sl.horizontal_max_m, max(sl.horizontal_min_m, horizontal_norm))
        if horizontal_norm > 1e-12:
            horizontal_unit = horizontal / horizontal_norm
        else:
            centre_offset = section_centre[:2] - origin[:2]
            centre_norm = float(np.linalg.norm(centre_offset))
            horizontal_unit = (centre_offset / centre_norm if centre_norm > 1e-12
                               else np.array([1., 0.]))
        cloud = np.array([
            *(origin[:2] + radial * horizontal_unit),
            min(sl.vertical_max_m, max(sl.vertical_min_m, desired[2])),
        ])
        event = _event_from_cloud(
            platform_index, missile_index, observation_s, age_s, lam, cloud
        )
        if event is not None:
            rows.append((float(fraction), event))
    return rows


def fixed_event_value(event: dict, missile_index: int, time_s: float) -> float:
    cloud = fixed_event_cloud(event, time_s)
    missile = service.missile_position(missile_index, time_s)
    return float(service.ball_service_value(cloud, missile)["value_m2"])


def fixed_event_decision(event: dict, missile_index: int) -> q5.Decision:
    """Convert a reconstructed event to the production solver representation."""
    platform_index = q5.NAMES.index(event["platform"])
    headings = [0.] * len(q5.NAMES)
    speeds = [70.] * len(q5.NAMES)
    headings[platform_index] = float(event["heading_rad"])
    speeds[platform_index] = float(event["speed_mps"])
    release = float(event["release_s"])
    if -1e-9 < release < 0.:
        release = 0.
    decision = q5.Decision(
        tuple(headings), tuple(speeds),
        (q5.Bomb(platform_index, missile_index, release, float(event["fuse_s"])),),
        "q5_fixed_event_dwell",
    )
    q5.validate(decision)
    return decision


def _root_from_safe_seed(function, seed: float, limit: float, direction: int,
                         step_s: float) -> float:
    """Walk from a known-safe seed and return the first zero or active limit."""
    current = float(seed)
    current_value = float(function(current))
    while abs(current - limit) > 1e-13:
        following = (max(limit, current - step_s) if direction < 0
                     else min(limit, current + step_s))
        following_value = float(function(following))
        if following_value > 0.:
            if current_value >= 0.:
                return current
            a, b = sorted((current, following))
            return float(brentq(function, a, b, xtol=1e-9, rtol=1e-14, maxiter=100))
        current, current_value = following, following_value
    return float(limit)


def service_interval(event: dict, missile_index: int, seed_s: float,
                     root_step_s: float = .05, seed_tolerance_m2: float = 1e-8) -> dict | None:
    """Connected sufficient full-obscuration interval containing ``seed_s``."""
    explosion_s = float(event["explosion_s"])
    left_limit = max(0., explosion_s)
    right_limit = min(explosion_s + q5.p().smoke_duration,
                      q5.arrival(missile_index), HORIZON_S)
    seed_s = float(seed_s)
    if seed_s < left_limit - 1e-10 or seed_s > right_limit + 1e-10:
        return None
    seed_s = min(right_limit, max(left_limit, seed_s))
    function = lambda t: fixed_event_value(event, missile_index, float(t))
    seed_value = float(function(seed_s))
    if seed_value > seed_tolerance_m2:
        return None
    # A small positive residual is numerical tangency, not evidence of an
    # interval.  Preserve it as a zero-duration component.
    if seed_value > 0.:
        left = right = seed_s
    else:
        left = _root_from_safe_seed(function, seed_s, left_limit, -1, root_step_s)
        right = _root_from_safe_seed(function, seed_s, right_limit, +1, root_step_s)
    return {
        "left_s": left, "right_s": right, "duration_s": max(0., right - left),
        "seed_s": seed_s, "seed_value_m2": seed_value,
        "left_value_m2": float(function(left)), "right_value_m2": float(function(right)),
        "active_limits_s": [left_limit, right_limit],
    }


def all_missile_interval(event: dict, seed_s: float, root_step_s: float = .05) -> dict | None:
    intervals = [service_interval(event, j, seed_s, root_step_s) for j in range(3)]
    if any(interval is None for interval in intervals):
        return None
    left = max(interval["left_s"] for interval in intervals)
    right = min(interval["right_s"] for interval in intervals)
    if right < left - 1e-10:
        return None
    return {
        "left_s": left, "right_s": max(left, right),
        "duration_s": max(0., right - left), "per_missile": intervals,
    }


def _candidate(platform_index: int, missile_index: int, seed_s: float, lam: float,
               age_nodes: int, root_step_s: float) -> dict | None:
    result = minimum_age_gap(
        platform_index, missile_index, seed_s, lam, age_nodes=age_nodes
    )
    if not result["feasible"]:
        return None
    variants = []
    for placement_fraction, event in placement_events(
            platform_index, missile_index, seed_s, result["age_s"], lam):
        interval = service_interval(event, missile_index, seed_s, root_step_s)
        if interval is None:
            continue
        common = all_missile_interval(event, seed_s, root_step_s)
        seed_certificates = [
            service.ball_service_value(
                fixed_event_cloud(event, seed_s), service.missile_position(j, seed_s)
            )["value_m2"] for j in range(3)
        ]
        variants.append({
            "platform": q5.NAMES[platform_index],
            "target_missile": q5.MISSILE_NAMES[missile_index],
            "seed_s": float(seed_s), "requested_lambda": float(lam),
            "placement_fraction": placement_fraction,
            "optimized_age_s": float(result["age_s"]),
            "reachable_gap_m2": float(result["optimized_gap_m2"]),
            "reachable_clearance_m": float(result["clearance_m"]),
            "event": event, "target_interval": interval,
            "all_missile_interval": common,
            "seed_certificate_values_m2": seed_certificates,
        })
    return _best(variants)


def _rank(candidate: dict) -> tuple:
    common = candidate["all_missile_interval"]
    return (
        candidate["target_interval"]["duration_s"],
        common["duration_s"] if common else 0.,
        candidate["reachable_clearance_m"],
    )


def _best(candidates: list[dict]) -> dict | None:
    return max(candidates, key=_rank) if candidates else None


def report_markdown(payload: dict) -> str:
    lines = [
        "# Q5 固定事件连续安全驻留候选", "",
        f"状态：`{payload['status']}`；种子步长 {payload['settings']['seed_step_s']} s；"
        f"边界括号步长 {payload['settings']['root_step_s']} s。", "",
        "下表的每一行都是同一枚已固定烟幕干扰弹的球包络充分安全驻留，不是将不同时刻的可行烟团拼接而成。", "",
        "| 平台 | 目标导弹 | 可行事件 | 最优 lambda 层 | 最长单导弹驻留/s | 区间/s | 最长三导弹共同驻留/s |",
        "|---|---|---:|---:|---:|---|---:|",
    ]
    for pair in payload["pairs"]:
        best = pair["best_target_candidate"]
        if best is None:
            lines.append(f"| {pair['platform']} | {pair['missile']} | 0 | — | 0 | — | 0 |")
            continue
        interval = best["target_interval"]
        common = pair["best_all_missile_candidate"]
        common_duration = (common["all_missile_interval"]["duration_s"] if common else 0.)
        lines.append(
            f"| {pair['platform']} | {pair['missile']} | {pair['feasible_event_count']} | "
            f"{best['requested_lambda']:.1f} | {interval['duration_s']:.9f} | "
            f"[{interval['left_s']:.9f},{interval['right_s']:.9f}] | {common_duration:.9f} |"
        )
    lines.extend(["", "## lambda 分层全局最长值", "",
                  "| lambda | 单导弹最长/s | 三导弹共同最长/s |", "|---:|---:|---:|"])
    for row in payload["lambda_summary"]:
        lines.append(f"| {row['lambda']:.1f} | {row['best_target_duration_s']:.9f} | {row['best_all_missile_duration_s']:.9f} |")
    lines.extend([
        "", "## 主张边界", "",
        "- 区间边界是已知安全种子所在连通分支的连续函数求根结果，不是时间网格长度。",
        "- 球包络域完整覆盖整个圆柱，因而为安全充分证书；但它可能漏掉形状感知域或多烟团并集可行解。",
        "- 各事件仍未应用同一无人机的固定航向/速度耦合、1 s 投放间隔和每机最多 3 枚的组合调度。",
        "- 该文件是 Q5 工作诊断，不是正式 Q5 结果。",
    ])
    return "\n".join(lines) + "\n"


def run(json_path: Path, report_path: Path, seed_step_s: float = 1.,
        root_step_s: float = .05, age_nodes: int = 41,
        lambdas: tuple[float, ...] = DEFAULT_LAMBDAS) -> dict:
    started = time.perf_counter()
    seeds = list(np.arange(seed_step_s, HORIZON_S, seed_step_s))
    seeds.append(HORIZON_S)
    pairs = []
    completed = 0
    for platform_index in range(5):
        for missile_index in range(3):
            by_lambda = []
            feasible_count = 0
            all_pair_candidates = []
            for lam in lambdas:
                layer = []
                for seed_s in seeds:
                    candidate = _candidate(
                        platform_index, missile_index, float(seed_s), float(lam),
                        age_nodes, root_step_s,
                    )
                    if candidate is not None:
                        feasible_count += 1
                        layer.append(candidate)
                        all_pair_candidates.append(candidate)
                retained = sorted(layer, key=_rank, reverse=True)[:3]
                by_lambda.append({
                    "lambda": float(lam), "feasible_event_count": len(layer),
                    "best_target_duration_s": (_rank(retained[0])[0] if retained else 0.),
                    "best_all_missile_duration_s": max(
                        (row["all_missile_interval"]["duration_s"]
                         for row in layer if row["all_missile_interval"] is not None),
                        default=0.,
                    ),
                    "retained_candidates": retained,
                })
            common_candidates = [row for row in all_pair_candidates
                                 if row["all_missile_interval"] is not None]
            best_target = _best(all_pair_candidates)
            best_common = max(
                common_candidates,
                key=lambda row: (row["all_missile_interval"]["duration_s"], *_rank(row)),
                default=None,
            )
            pair = {
                "platform": q5.NAMES[platform_index],
                "missile": q5.MISSILE_NAMES[missile_index],
                "feasible_event_count": feasible_count,
                "best_target_candidate": best_target,
                "best_all_missile_candidate": best_common,
                "lambda_layers": by_lambda,
            }
            pairs.append(pair)
            completed += 1
            print(json.dumps({
                "stage": "fixed_event_dwell_pair_complete", "completed": completed,
                "total": 15, "platform": pair["platform"], "missile": pair["missile"],
                "feasible_event_count": feasible_count,
                "best_target_duration_s": (_rank(best_target)[0] if best_target else 0.),
                "best_all_missile_duration_s": (
                    best_common["all_missile_interval"]["duration_s"] if best_common else 0.
                ),
                "elapsed_s": time.perf_counter() - started,
            }, ensure_ascii=False), flush=True)

    lambda_summary = []
    for lambda_index, lam in enumerate(lambdas):
        layers = [pair["lambda_layers"][lambda_index] for pair in pairs]
        lambda_summary.append({
            "lambda": float(lam),
            "best_target_duration_s": max(
                (row["best_target_duration_s"] for row in layers), default=0.
            ),
            "best_all_missile_duration_s": max(
                (row["best_all_missile_duration_s"] for row in layers), default=0.
            ),
        })
    payload = {
        "schema_version": "1.0", "spec_id": SPEC_ID,
        "status": "diagnostic_complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "continuous sufficient full-obscuration dwell of one fixed physical smoke event",
        "horizon_s": HORIZON_S,
        "settings": {
            "seed_step_s": seed_step_s, "root_step_s": root_step_s,
            "root_xtol_s": 1e-9, "age_nodes": age_nodes,
            "lambda_strata": list(lambdas), "retained_per_pair_lambda": 3,
            "placement_fractions_along_relative_motion_chord": list(PLACEMENT_FRACTIONS),
            "deterministic": True, "random_seed": None,
        },
        "input_identity": {
            "data/A题.pdf": q5.sha(ROOT / "data/A题.pdf"),
            "planning/41_q5_geometric_service_domains.md": q5.sha(ROOT / "planning/41_q5_geometric_service_domains.md"),
            "planning/43_q5_fixed_event_dwell_spec.md": q5.sha(ROOT / "planning/43_q5_fixed_event_dwell_spec.md"),
            "src/q5/service_domains.py": q5.sha(ROOT / "src/q5/service_domains.py"),
            "src/q5/service_dwell.py": q5.sha(Path(__file__).resolve()),
        },
        "pairs": pairs, "lambda_summary": lambda_summary,
        "claims": {
            "fixed_event_forward_physics": True,
            "continuous_boundary_roots": True,
            "single_cloud_safe_certificate": True,
            "lambda_stratified": True,
            "relative_motion_chord_placements": True,
            "fixed_track_multi_event_schedule": False,
            "multi_cloud_union_applied": False,
            "formal_q5_result": False,
        },
        "software": {
            "python": platform.python_version(), "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "elapsed_s": time.perf_counter() - started,
    }
    service.atomic_write(json_path, json.dumps(q5.ready(payload), ensure_ascii=False, indent=2))
    service.atomic_write(report_path, report_markdown(payload))
    print(json.dumps({"stage": "fixed_event_dwell_complete", "pair_count": len(pairs),
                      "retained_candidate_count": sum(
                          len(layer["retained_candidates"])
                          for pair in pairs for layer in pair["lambda_layers"]
                      ),
                      "elapsed_s": payload["elapsed_s"]}, ensure_ascii=False), flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=ROOT / "docs/q5_service_dwell_candidates.json")
    parser.add_argument("--report", type=Path, default=ROOT / "docs/q5_service_dwell_candidates.md")
    parser.add_argument("--seed-step-s", type=float, default=1.)
    parser.add_argument("--root-step-s", type=float, default=.05)
    parser.add_argument("--age-nodes", type=int, default=41)
    args = parser.parse_args()
    run(args.json.resolve(), args.report.resolve(), max(.25, args.seed_step_s),
        max(.005, args.root_step_s), max(11, args.age_nodes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
