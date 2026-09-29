#!/usr/bin/env python3
"""Analytic Q5 smoke-service domains and deterministic corridor diagnostic."""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import minimize, minimize_scalar

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT))

from src.q5 import geometry_pilot as geometry  # noqa: E402
from src.q5 import solve as q5  # noqa: E402


SPEC_ID = "Q5-SERVICE-DOMAINS-1.0"
TARGET_MIDPOINT = np.asarray(q5.p().target_base_center, float) + np.array([0., 0., q5.p().target_height / 2])
TARGET_ENVELOPE_RADIUS = math.hypot(q5.p().target_radius, q5.p().target_height / 2)
HORIZON_S = min(q5.ARRIVAL_TIMES)


@dataclass(frozen=True)
class ReachableSlice:
    platform: int
    observation_s: float
    age_s: float
    explosion_s: float
    horizontal_min_m: float
    horizontal_max_m: float
    vertical_min_m: float
    vertical_max_m: float
    fuse_max_s: float


def missile_position(j: int, time_s: float) -> np.ndarray:
    initial = np.asarray(geometry.MISSILES[j], float)
    return (1. - q5.p().missile_speed * time_s / np.linalg.norm(initial)) * initial


def ball_service_value(cloud, missile) -> dict:
    """Closed-form membership value for the midpoint-envelope safe domain."""
    cloud = np.asarray(cloud, float)
    missile = np.asarray(missile, float)
    y = cloud - missile
    direction = TARGET_MIDPOINT - missile
    coefficient = float(direction @ direction - TARGET_ENVELOPE_RADIUS ** 2)
    if coefficient <= 0:
        raise ValueError("missile lies inside the target envelope")
    lambda_raw = float((y @ direction - q5.p().smoke_radius * TARGET_ENVELOPE_RADIUS) / coefficient)
    lam = min(1., max(0., lambda_raw))
    radius = q5.p().smoke_radius - lam * TARGET_ENVELOPE_RADIUS
    centre = missile + lam * direction
    squared_distance = float(np.sum((cloud - centre) ** 2))
    value = squared_distance - radius ** 2
    return {
        "value_m2": value, "lambda": lam, "lambda_unclipped": lambda_raw,
        "section_radius_m": radius, "section_centre_m": centre,
        "distance_to_section_centre_m": math.sqrt(max(0., squared_distance)),
        "clearance_m": radius - math.sqrt(max(0., squared_distance)),
        "covered": value <= 1e-10,
    }


def shape_value_at_lambda(cloud, missile, lam: float) -> float:
    cloud = np.asarray(cloud, float)
    missile = np.asarray(missile, float)
    e = cloud - missile - lam * (TARGET_MIDPOINT - missile)
    return float(
        e @ e + lam * lam * TARGET_ENVELOPE_RADIUS ** 2
        + 2 * lam * (
            q5.p().target_radius * np.linalg.norm(e[:2])
            + q5.p().target_height / 2 * abs(e[2])
        ) - q5.p().smoke_radius ** 2
    )


def shape_service_value(cloud, missile) -> dict:
    result = minimize_scalar(
        lambda lam: shape_value_at_lambda(cloud, missile, float(lam)),
        bounds=(0., 1.), method="bounded", options={"xatol": 1e-12, "maxiter": 100},
    )
    endpoint_rows = [(0., shape_value_at_lambda(cloud, missile, 0.)),
                     (1., shape_value_at_lambda(cloud, missile, 1.)),
                     (float(result.x), float(result.fun))]
    lam, value = min(endpoint_rows, key=lambda row: row[1])
    return {"value_m2": value, "lambda": lam, "covered": value <= 1e-10,
            "optimizer_success": bool(result.success)}


def perspective_frame(missile) -> dict:
    missile = np.asarray(missile, float)
    normal = TARGET_MIDPOINT - missile
    length = float(np.linalg.norm(normal))
    normal /= length
    reference = np.array([0., 0., 1.])
    if abs(float(normal @ reference)) > .95:
        reference = np.array([0., 1., 0.])
    axis_x = np.cross(reference, normal)
    axis_x /= np.linalg.norm(axis_x)
    axis_y = np.cross(normal, axis_x)
    return {"origin": TARGET_MIDPOINT.copy(), "normal": normal, "axis_x": axis_x,
            "axis_y": axis_y, "distance_m": length}


def project_to_perspective_plane(missile, point, frame=None) -> dict:
    missile = np.asarray(missile, float)
    point = np.asarray(point, float)
    frame = frame or perspective_frame(missile)
    ray = point - missile
    denominator = float(frame["normal"] @ ray)
    if denominator <= 0:
        raise ValueError("point is behind the perspective plane")
    scale = frame["distance_m"] / denominator
    projected = missile + scale * ray
    offset = projected - frame["origin"]
    return {"point_m": projected, "coordinates_m": np.array([
        float(offset @ frame["axis_x"]), float(offset @ frame["axis_y"])
    ]), "ray_scale": scale}


def sphere_shadow_value(cloud, missile, plane_point) -> dict:
    """Positive iff the infinite ray through a plane point intersects the smoke sphere."""
    cloud = np.asarray(cloud, float)
    missile = np.asarray(missile, float)
    plane_point = np.asarray(plane_point, float)
    c = cloud - missile
    y = plane_point - missile
    dot = float(c @ y)
    value = dot * dot - (float(c @ c) - q5.p().smoke_radius ** 2) * float(y @ y)
    return {"value_m4": value, "forward": dot > 0.,
            "inside_shadow": dot > 0. and value >= -1e-7}


def finite_segment_covered(cloud, missile, target_point) -> bool:
    cloud = np.asarray(cloud, float)
    missile = np.asarray(missile, float)
    target_point = np.asarray(target_point, float)
    segment = target_point - missile
    parameter = float((cloud - missile) @ segment / (segment @ segment))
    parameter = min(1., max(0., parameter))
    closest = missile + parameter * segment
    return float(np.linalg.norm(cloud - closest)) <= q5.p().smoke_radius + 1e-10


def reachable_slice(platform_index: int, observation_s: float, age_s: float) -> ReachableSlice:
    if not 0 <= platform_index < 5:
        raise ValueError("platform index")
    age_cap = min(q5.p().smoke_duration, observation_s)
    if not -1e-12 <= age_s <= age_cap + 1e-12:
        raise ValueError("smoke age outside active observation window")
    age_s = min(age_cap, max(0., float(age_s)))
    explosion_s = observation_s - age_s
    altitude = float(q5.ORIGINS[platform_index, 2])
    fuse_max = min(explosion_s, math.sqrt(2 * altitude / q5.p().gravity))
    return ReachableSlice(
        platform=platform_index, observation_s=float(observation_s), age_s=age_s,
        explosion_s=explosion_s,
        horizontal_min_m=70. * explosion_s,
        horizontal_max_m=140. * explosion_s,
        vertical_min_m=altitude - .5 * q5.p().gravity * fuse_max ** 2
                       - q5.p().smoke_sink_speed * age_s,
        vertical_max_m=altitude - q5.p().smoke_sink_speed * age_s,
        fuse_max_s=fuse_max,
    )


def interval_distance(value: float, lower: float, upper: float) -> float:
    return lower - value if value < lower else value - upper if value > upper else 0.


def reachable_ball_gap(platform_index: int, missile_index: int, observation_s: float,
                       age_s: float, lam: float, reconstruct=False) -> dict:
    sl = reachable_slice(platform_index, observation_s, age_s)
    lam = min(1., max(0., float(lam)))
    missile = missile_position(missile_index, observation_s)
    service_centre = missile + lam * (TARGET_MIDPOINT - missile)
    service_radius = q5.p().smoke_radius - lam * TARGET_ENVELOPE_RADIUS
    origin = q5.ORIGINS[platform_index]
    offset = service_centre[:2] - origin[:2]
    horizontal_distance = float(np.linalg.norm(offset))
    radial_gap = interval_distance(horizontal_distance, sl.horizontal_min_m, sl.horizontal_max_m)
    vertical_gap = interval_distance(service_centre[2], sl.vertical_min_m, sl.vertical_max_m)
    squared_distance = radial_gap ** 2 + vertical_gap ** 2
    row = {
        "gap_m2": squared_distance - service_radius ** 2,
        "distance_to_reachable_slice_m": math.sqrt(squared_distance),
        "service_radius_m": service_radius, "lambda": lam,
        "age_s": sl.age_s, "explosion_s": sl.explosion_s,
    }
    if not reconstruct:
        return row
    radial = min(sl.horizontal_max_m, max(sl.horizontal_min_m, horizontal_distance))
    if horizontal_distance > 1e-12:
        horizontal_unit = offset / horizontal_distance
    else:
        horizontal_unit = np.array([1., 0.])
    cloud_xy = origin[:2] + radial * horizontal_unit
    cloud_z = min(sl.vertical_max_m, max(sl.vertical_min_m, service_centre[2]))
    cloud = np.array([cloud_xy[0], cloud_xy[1], cloud_z])
    speed = radial / sl.explosion_s if sl.explosion_s > 1e-12 else 70.
    heading = float(math.atan2(horizontal_unit[1], horizontal_unit[0]) % (2 * math.pi))
    explosion_height = cloud_z + q5.p().smoke_sink_speed * sl.age_s
    fuse = math.sqrt(max(0., 2 * (origin[2] - explosion_height) / q5.p().gravity))
    release = sl.explosion_s - fuse
    certificate = ball_service_value(cloud, missile)
    row["event"] = {
        "platform": q5.NAMES[platform_index], "missile": q5.MISSILE_NAMES[missile_index],
        "observation_s": float(observation_s), "smoke_age_s": sl.age_s,
        "explosion_s": sl.explosion_s, "release_s": release, "fuse_s": fuse,
        "heading_rad": heading, "heading_deg": math.degrees(heading), "speed_mps": speed,
        "cloud_centre_m": cloud, "service_section_centre_m": service_centre,
        "service_section_radius_m": service_radius,
        "certificate_value_m2": certificate["value_m2"],
        "certificate_lambda": certificate["lambda"],
    }
    return row


def minimum_service_gap(platform_index: int, missile_index: int, observation_s: float,
                        age_nodes=41, lambda_nodes=61) -> dict:
    age_cap = min(q5.p().smoke_duration, observation_s)
    ages = np.linspace(0., age_cap, age_nodes)
    lambdas = np.linspace(0., 1., lambda_nodes)
    values = np.empty((age_nodes, lambda_nodes))
    for age_index, age in enumerate(ages):
        for lambda_index, lam in enumerate(lambdas):
            values[age_index, lambda_index] = reachable_ball_gap(
                platform_index, missile_index, observation_s, float(age), float(lam)
            )["gap_m2"]
    best_index = np.unravel_index(int(np.argmin(values)), values.shape)
    x0 = np.array([ages[best_index[0]], lambdas[best_index[1]]])
    bounds = ((0., age_cap), (0., 1.))
    result = minimize(
        lambda x: reachable_ball_gap(
            platform_index, missile_index, observation_s, float(x[0]), float(x[1])
        )["gap_m2"],
        x0, method="L-BFGS-B", bounds=bounds,
        options={"maxiter": 80, "ftol": 1e-13, "gtol": 1e-9, "maxls": 30},
    )
    candidates = [(float(values[best_index]), x0), (float(result.fun), np.asarray(result.x))]
    best_value, best_x = min(candidates, key=lambda item: item[0])
    reconstructed = reachable_ball_gap(
        platform_index, missile_index, observation_s, float(best_x[0]), float(best_x[1]), True
    )
    reconstructed.update({
        "grid_best_gap_m2": float(values[best_index]), "optimized_gap_m2": best_value,
        "optimizer_success": bool(result.success), "age_node_count": age_nodes,
        "lambda_node_count": lambda_nodes,
        "feasible": best_value <= 1e-8,
        "clearance_m": reconstructed["service_radius_m"]
                       - reconstructed["distance_to_reachable_slice_m"],
    })
    return reconstructed


def sampled_intervals(samples: list[dict], step_s: float) -> list[list[float]]:
    feasible = [row for row in samples if row["feasible"]]
    if not feasible:
        return []
    intervals = []
    left = right = feasible[0]["time_s"]
    for row in feasible[1:]:
        time_s = row["time_s"]
        if time_s - right <= step_s * 1.01:
            right = time_s
        else:
            intervals.append([left, right])
            left = right = time_s
    intervals.append([left, right])
    return intervals


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent,
                                     prefix=path.name + ".", suffix=".tmp") as handle:
        handle.write(content)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def report_markdown(payload: dict) -> str:
    lines = [
        "# Q5 平台—导弹解析安全服务走廊", "",
        f"状态：`{payload['status']}`；时间节点步长：{payload['settings']['time_step_s']} s。", "",
        "该结果只表示单个平台在单个时刻存在一枚落入球包络充分域的合法烟团；不是投弹调度，也不包含多烟团部分覆盖拼接。", "",
        "| 平台 | 导弹 | 可行节点 | 采样走廊 | 最佳安全余量/m |", "|---|---|---:|---|---:|",
    ]
    for row in payload["pairs"]:
        intervals = ", ".join(f"[{a:.3f},{b:.3f}]" for a, b in row["sampled_feasible_intervals_s"]) or "无"
        lines.append(f"| {row['platform']} | {row['missile']} | {row['feasible_sample_count']} | {intervals} | {row['best_clearance_m']:.6f} |")
    lines.extend([
        "", "## 主张边界", "",
        "- 空走廊只表示在当前球包络充分域和 1 s 节点下未找到单云完整服务事件。",
        "- 它不排除形状感知充分域、多个部分烟团联合覆盖或窄于节点步长的可行岛。",
        "- 每个保存事件均可正向恢复航向、速度、投放、引信和烟团中心；跨事件固定航迹尚未求解。",
    ])
    return "\n".join(lines) + "\n"


def run(json_path: Path, report_path: Path, time_step_s=1.) -> dict:
    started = time.perf_counter()
    times = list(np.arange(time_step_s, HORIZON_S, time_step_s))
    times.append(HORIZON_S)
    pairs = []
    total_pairs = 15
    completed = 0
    for platform_index in range(5):
        for missile_index in range(3):
            samples = []
            for time_s in times:
                result = minimum_service_gap(platform_index, missile_index, float(time_s))
                samples.append({
                    "time_s": float(time_s), "gap_m2": result["optimized_gap_m2"],
                    "clearance_m": result["clearance_m"], "feasible": result["feasible"],
                    "age_s": result["age_s"], "lambda": result["lambda"],
                    "event": result["event"], "optimizer_success": result["optimizer_success"],
                })
            best = min(samples, key=lambda row: row["gap_m2"])
            intervals = sampled_intervals(samples, time_step_s)
            pair = {
                "platform": q5.NAMES[platform_index], "missile": q5.MISSILE_NAMES[missile_index],
                "feasible_sample_count": sum(row["feasible"] for row in samples),
                "sampled_feasible_intervals_s": intervals,
                "best_gap_m2": best["gap_m2"], "best_clearance_m": best["clearance_m"],
                "best_time_s": best["time_s"], "best_event": best["event"],
                "samples": samples,
            }
            pairs.append(pair)
            completed += 1
            print(json.dumps({
                "stage": "service_corridor_pair_complete", "completed": completed,
                "total": total_pairs, "platform": pair["platform"], "missile": pair["missile"],
                "feasible_sample_count": pair["feasible_sample_count"],
                "best_clearance_m": pair["best_clearance_m"],
                "elapsed_s": time.perf_counter() - started,
            }, ensure_ascii=False), flush=True)
    payload = {
        "schema_version": "1.0", "spec_id": SPEC_ID, "status": "diagnostic_complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "single-event reachable intersection with the analytic midpoint-envelope full-obscuration domain",
        "horizon_s": HORIZON_S,
        "settings": {"time_step_s": time_step_s, "age_nodes": 41, "lambda_nodes": 61,
                     "deterministic": True, "random_seed": None},
        "input_identity": {
            "data/A题.pdf": q5.sha(ROOT / "data/A题.pdf"),
            "planning/41_q5_geometric_service_domains.md": q5.sha(ROOT / "planning/41_q5_geometric_service_domains.md"),
            "src/q5/service_domains.py": q5.sha(Path(__file__).resolve()),
        },
        "parameters": {
            "target_midpoint_m": TARGET_MIDPOINT, "target_envelope_radius_m": TARGET_ENVELOPE_RADIUS,
            "smoke_radius_m": q5.p().smoke_radius, "smoke_duration_s": q5.p().smoke_duration,
            "smoke_sink_speed_mps": q5.p().smoke_sink_speed,
            "speed_bounds_mps": [70., 140.],
        },
        "pairs": pairs,
        "claims": {
            "schedule_optimized": False, "fixed_track_coupling_applied": False,
            "multi_cloud_union_applied": False, "continuous_corridor_exhausted": False,
            "single_cloud_safe_certificate": True, "formal_q5_result": False,
        },
        "software": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
        "elapsed_s": time.perf_counter() - started,
    }
    atomic_write(json_path, json.dumps(q5.ready(payload), ensure_ascii=False, indent=2))
    atomic_write(report_path, report_markdown(payload))
    print(json.dumps({"stage": "service_corridor_complete", "pair_count": len(pairs),
                      "elapsed_s": payload["elapsed_s"]}, ensure_ascii=False), flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=ROOT / "docs/q5_service_corridors.json")
    parser.add_argument("--report", type=Path, default=ROOT / "docs/q5_service_corridors.md")
    parser.add_argument("--time-step-s", type=float, default=1.)
    args = parser.parse_args()
    run(args.json.resolve(), args.report.resolve(), max(.25, args.time_step_s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
