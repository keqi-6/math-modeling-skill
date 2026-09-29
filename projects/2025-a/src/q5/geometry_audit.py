#!/usr/bin/env python3
"""Independent geometry and kinematics audit for Q5.

The reference path intentionally uses scalar three-dimensional constructions
instead of the production vectorized distance and normal-visibility formulas.
It verifies geometry only; it does not search for a better Q5 decision.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT))

from src.q3 import selection_pilot as q3  # noqa: E402
from src.q5 import geometry_pilot as geometry  # noqa: E402
from src.q5 import solve as q5  # noqa: E402


SPEC_ID = "SPEC-Q5-GEOMETRY-AUDIT-1.0"
POSITION_TOL_M = 1e-7
DISTANCE_TOL_M = 5e-9
VISIBILITY_TOL = 2e-8


def reference_segment_distance(cloud, missile, point) -> float:
    """Distance from a point to a finite segment, using an explicit vector path."""
    cloud = np.asarray(cloud, dtype=np.longdouble)
    missile = np.asarray(missile, dtype=np.longdouble)
    point = np.asarray(point, dtype=np.longdouble)
    segment = point - missile
    denominator = np.dot(segment, segment)
    if denominator <= 0:
        raise ValueError("degenerate finite segment")
    parameter = np.dot(cloud - missile, segment) / denominator
    parameter = min(np.longdouble(1), max(np.longdouble(0), parameter))
    closest = missile + parameter * segment
    return float(np.linalg.norm(cloud - closest))


def infinite_line_distance(cloud, missile, point) -> float:
    cloud = np.asarray(cloud, float)
    missile = np.asarray(missile, float)
    point = np.asarray(point, float)
    direction = point - missile
    return float(np.linalg.norm(np.cross(cloud - missile, direction)) / np.linalg.norm(direction))


def ray_cylinder_first_hit(missile, point, base_center, radius, height) -> float | None:
    """First intersection parameter of M+s(P-M) with a closed finite cylinder."""
    missile = np.asarray(missile, np.longdouble)
    point = np.asarray(point, np.longdouble)
    base = np.asarray(base_center, np.longdouble)
    direction = point - missile
    candidates: list[np.longdouble] = []
    relative = missile[:2] - base[:2]
    a = np.dot(direction[:2], direction[:2])
    b = 2 * np.dot(relative, direction[:2])
    c = np.dot(relative, relative) - np.longdouble(radius) ** 2
    if a > 0:
        discriminant = b * b - 4 * a * c
        if discriminant >= -np.longdouble(1e-18):
            root = np.sqrt(max(np.longdouble(0), discriminant))
            for value in ((-b - root) / (2 * a), (-b + root) / (2 * a)):
                z = missile[2] + value * direction[2]
                if -1e-12 <= value <= 1 + 1e-12 and base[2] - 1e-10 <= z <= base[2] + height + 1e-10:
                    candidates.append(value)
    if abs(direction[2]) > 1e-24:
        for z_plane in (base[2], base[2] + height):
            value = (z_plane - missile[2]) / direction[2]
            xy = missile[:2] + value * direction[:2]
            if (-1e-12 <= value <= 1 + 1e-12
                    and np.dot(xy - base[:2], xy - base[:2]) <= radius ** 2 + 1e-9):
                candidates.append(value)
    nonnegative = [value for value in candidates if value >= -1e-12]
    return None if not nonnegative else float(min(nonnegative))


def reference_visibility(missile, points, base_center, radius, height) -> np.ndarray:
    result = []
    for point in np.asarray(points, float):
        first = ray_cylinder_first_hit(missile, point, base_center, radius, height)
        result.append(first is not None and abs(first - 1.) <= VISIBILITY_TOL)
    return np.asarray(result, bool)


def independent_surface(n_theta=180, n_levels=21) -> np.ndarray:
    p = q5.p()
    centre = np.asarray(p.target_base_center, float)
    angles = np.linspace(0., 2 * math.pi, n_theta, endpoint=False)
    heights = np.linspace(0., p.target_height, n_levels)
    side = np.asarray([
        [centre[0] + p.target_radius * math.cos(angle),
         centre[1] + p.target_radius * math.sin(angle), centre[2] + height]
        for height in heights for angle in angles
    ])
    radii = np.linspace(0., p.target_radius, n_levels)
    top = np.asarray([
        [centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle),
         centre[2] + p.target_height]
        for radius in radii for angle in angles
    ])
    return np.vstack((side, top))


def independent_missile(j: int, t: float) -> np.ndarray:
    initial = np.asarray(geometry.MISSILES[j], float)
    return initial + t * (-q5.p().missile_speed * initial / np.linalg.norm(initial))


def independent_explosion(origin, heading, speed, release, fuse) -> np.ndarray:
    time_s = release + fuse
    return np.asarray(origin, float) + np.array([
        speed * time_s * math.cos(heading), speed * time_s * math.sin(heading),
        -.5 * q5.p().gravity * fuse * fuse,
    ])


def independent_cloud(origin, heading, speed, release, fuse, observation) -> np.ndarray:
    explosion = independent_explosion(origin, heading, speed, release, fuse)
    explosion[2] -= q5.p().smoke_sink_speed * (observation - release - fuse)
    return explosion


def geometry_margin(clouds, missile, points, visible) -> tuple[float, int, np.ndarray]:
    distances = []
    for point in points:
        distances.append(min(reference_segment_distance(cloud, missile, point) for cloud in clouds))
    distances = np.asarray(distances, float)
    values = np.where(visible, distances - q5.p().smoke_radius, -np.inf)
    index = int(np.argmax(values))
    return float(values[index]), index, distances


def active_clouds(decision, time_s: float, j: int) -> list[np.ndarray]:
    rows = []
    for bomb in decision.bombs:
        explosion_s = bomb.release_s + bomb.fuse_s
        if explosion_s - q5.TIME_TOL <= time_s <= min(
            explosion_s + q5.p().smoke_duration, q5.arrival(j)
        ) + q5.TIME_TOL:
            rows.append(independent_cloud(
                q5.ORIGINS[bomb.platform], decision.headings_rad[bomb.platform],
                decision.speeds_mps[bomb.platform], bomb.release_s, bomb.fuse_s, time_s,
            ))
    return rows


def audit_segment_distance() -> dict:
    rng = np.random.default_rng(20260829)
    mesh = q3.surface_mesh(37, 7)
    missiles, clouds = [], []
    for _ in range(36):
        j = int(rng.integers(0, 3))
        t = float(rng.uniform(0., min(q5.ARRIVAL_TIMES) - .1))
        missiles.append(independent_missile(j, t))
        clouds.append(rng.uniform([-200., -200., -100.], [18000., 2000., 2100.]))
    missiles = np.asarray(missiles)
    clouds = np.asarray(clouds)
    production = q3._distance_to_segments(clouds, missiles, mesh)
    maximum_error = 0.
    for row in range(len(missiles)):
        for column, point in enumerate(mesh.points):
            reference = reference_segment_distance(clouds[row], missiles[row], point)
            maximum_error = max(maximum_error, abs(reference - production[row, column]))
    missile = np.array([10., 0., 0.])
    point = np.array([0., 0., 0.])
    past_target_cloud = np.array([-5., 0., 0.])
    finite = reference_segment_distance(past_target_cloud, missile, point)
    infinite = infinite_line_distance(past_target_cloud, missile, point)
    passed = maximum_error <= DISTANCE_TOL_M and abs(finite - 5.) <= 1e-12 and infinite <= 1e-12
    return {
        "name": "finite_segment_distance", "status": "pass" if passed else "fail",
        "random_pair_count": len(missiles), "surface_point_count": len(mesh.points),
        "maximum_absolute_error_m": maximum_error,
        "counterexample": {
            "description": "cloud lies beyond target on the infinite sightline",
            "finite_segment_distance_m": finite, "infinite_line_distance_m": infinite,
            "implication": "an infinite-line implementation would create a false obscuration",
        },
    }


def audit_visibility() -> dict:
    p = q5.p()
    mesh = q3.surface_mesh(73, 11)
    mismatches = ambiguous = checked = 0
    examples = []
    for j in range(3):
        for t in (0., 20., 45.):
            missile = independent_missile(j, t)
            production = q3.visibility_mask(missile.reshape(1, 3), mesh)[0]
            reference = reference_visibility(
                missile, mesh.points, p.target_base_center, p.target_radius, p.target_height
            )
            for index in np.flatnonzero(production != reference):
                point = mesh.points[index]
                radial = abs(np.linalg.norm(point[:2] - p.target_base_center[:2]) - p.target_radius)
                at_rim = radial <= 1e-9 and abs(point[2] - p.target_height) <= 1e-9
                normal_dot = float(np.dot(mesh.point_normals[index], missile - point))
                is_ambiguous = at_rim or abs(normal_dot) <= 2e-7
                ambiguous += int(is_ambiguous)
                mismatches += int(not is_ambiguous)
                if len(examples) < 5:
                    examples.append({"missile": j, "time_s": t, "point": point.tolist(),
                                     "normal_dot": normal_dot, "ambiguous": is_ambiguous})
            checked += len(mesh.points)
    return {
        "name": "visible_surface_first_hit", "status": "pass" if mismatches == 0 else "fail",
        "checked_point_views": checked, "nonambiguous_mismatch_count": mismatches,
        "edge_or_tangent_mismatch_count": ambiguous, "mismatch_examples": examples,
        "reference_method": "first analytic ray intersection with finite cylinder",
    }


def circular_error(a, b) -> float:
    return abs((a - b + math.pi) % (2 * math.pi) - math.pi)


def audit_kinematics() -> dict:
    rng = np.random.default_rng(1962025)
    maximum = {"heading_rad": 0., "speed_mps": 0., "release_s": 0., "fuse_s": 0., "cloud_m": 0.,
               "missile_m": 0., "production_explosion_m": 0.}
    count = 0
    for j in range(3):
        for t in np.linspace(0., q5.arrival(j), 9):
            maximum["missile_m"] = max(maximum["missile_m"], float(np.linalg.norm(
                independent_missile(j, float(t)) - geometry.missile(j, float(t))
            )))
    for i in range(5):
        fuse_cap = math.sqrt(2 * q5.ORIGINS[i, 2] / q5.p().gravity)
        for _ in range(12):
            heading = float(rng.uniform(0., 2 * math.pi))
            speed = float(rng.uniform(70., 140.))
            release = float(rng.uniform(.1, 18.))
            fuse = float(rng.uniform(.05, min(.75 * fuse_cap, 8.)))
            age = float(rng.uniform(.1, 6.))
            observation = release + fuse + age
            cloud = independent_cloud(q5.ORIGINS[i], heading, speed, release, fuse, observation)
            solved = geometry.inverse_track(i, observation, age, cloud.copy())
            if solved is None:
                return {"name": "kinematic_roundtrip", "status": "fail",
                        "failure": "inverse_track rejected a forward-feasible state"}
            got_heading, got_speed, got_release, got_fuse = solved
            rebuilt = independent_cloud(
                q5.ORIGINS[i], got_heading, got_speed, got_release, got_fuse, observation
            )
            maximum["heading_rad"] = max(maximum["heading_rad"], circular_error(heading, got_heading))
            maximum["speed_mps"] = max(maximum["speed_mps"], abs(speed - got_speed))
            maximum["release_s"] = max(maximum["release_s"], abs(release - got_release))
            maximum["fuse_s"] = max(maximum["fuse_s"], abs(fuse - got_fuse))
            maximum["cloud_m"] = max(maximum["cloud_m"], float(np.linalg.norm(cloud - rebuilt)))
            decision = q5.Decision(
                tuple(heading if k == i else 0. for k in range(5)),
                tuple(speed if k == i else 70. for k in range(5)),
                (q5.Bomb(i, 0, release, fuse),), "audit",
            )
            maximum["production_explosion_m"] = max(
                maximum["production_explosion_m"],
                float(np.linalg.norm(independent_explosion(
                    q5.ORIGINS[i], heading, speed, release, fuse
                ) - q5.explosion_point(decision, decision.bombs[0]))),
            )
            count += 1
    passed = (maximum["heading_rad"] <= 1e-10 and maximum["speed_mps"] <= 1e-8
              and maximum["release_s"] <= 1e-9 and maximum["fuse_s"] <= 1e-9
              and maximum["cloud_m"] <= POSITION_TOL_M
              and maximum["missile_m"] <= POSITION_TOL_M
              and maximum["production_explosion_m"] <= POSITION_TOL_M)
    return {"name": "kinematic_roundtrip", "status": "pass" if passed else "fail",
            "roundtrip_count": count, "maximum_errors": maximum}


def audit_centreline_and_union() -> dict:
    p = q5.p()
    points = independent_surface(180, 21)
    centre = np.asarray(p.target_base_center, float) + np.array([0., 0., .5 * p.target_height])
    envelope = math.hypot(p.target_radius, .5 * p.target_height)
    maximum_centreline_distance = 0.
    for j in range(3):
        missile = independent_missile(j, 20.)
        for fraction in (.1, .5, .9, 1.):
            cloud = missile + fraction * (centre - missile)
            maximum_centreline_distance = max(maximum_centreline_distance, max(
                reference_segment_distance(cloud, missile, point) for point in points
            ))
    missile = independent_missile(0, 20.)
    base_cloud = np.asarray(p.target_base_center, float)
    visible = reference_visibility(
        missile, points, p.target_base_center, p.target_radius, p.target_height
    )
    base_margin, base_worst, _ = geometry_margin([base_cloud], missile, points, visible)

    direction = centre - missile
    direction /= np.linalg.norm(direction)
    transverse = np.cross(direction, np.array([0., 0., 1.]))
    transverse /= np.linalg.norm(transverse)
    fraction = .95
    central_cloud = missile + fraction * (centre - missile)
    cloud_a = central_cloud + 4.5 * transverse
    cloud_b = central_cloud - 4.5 * transverse
    margin_a, _, distances_a = geometry_margin([cloud_a], missile, points, visible)
    margin_b, _, distances_b = geometry_margin([cloud_b], missile, points, visible)
    union_values = np.minimum(distances_a, distances_b) - p.smoke_radius
    union_margin = float(np.max(union_values[visible]))
    quantifier_pass = margin_a > 0 and margin_b > 0 and union_margin <= 0
    passed = (envelope < p.smoke_radius and maximum_centreline_distance <= envelope + 2e-9
              and base_margin > 0 and quantifier_pass)
    return {
        "name": "centreline_certificate_and_cloud_union",
        "status": "pass" if passed else "fail",
        "analytic_envelope_radius_m": envelope, "smoke_radius_m": p.smoke_radius,
        "maximum_dense_centreline_distance_m": maximum_centreline_distance,
        "base_centreline_counterexample": {
            "worst_margin_m": base_margin, "worst_point_m": points[base_worst].tolist(),
            "implication": "the base-centre sightline has no unconditional full-cylinder certificate",
        },
        "two_cloud_union_counterexample": {
            "cloud_a_margin_m": margin_a, "cloud_b_margin_m": margin_b,
            "union_margin_m": union_margin,
            "implication": "each cloud may fail alone while their per-ray union fully obscures the target",
        },
    }


def audit_production_quantifier() -> dict:
    incumbent, _ = q5.registered_incumbent()
    relabelled = replace(incumbent, bombs=tuple(
        replace(bomb, label=(bomb.label + 1) % 3) for bomb in incumbent.bombs
    ), source="audit_relabelled")
    mesh = q3.surface_mesh(32, 5)
    times = (16., 18., 20., 22., 30., 32.)
    maximum_reference_error = 0.
    maximum_label_error = 0.
    worst_records = []
    p = q5.p()
    for j in range(3):
        production = q5.strict_margins(incumbent, j, times, mesh)
        relabel = q5.strict_margins(relabelled, j, times, mesh)
        maximum_label_error = max(maximum_label_error, float(np.max(np.abs(production - relabel))))
        for ordinal, time_s in enumerate(times):
            missile = independent_missile(j, time_s)
            visible = reference_visibility(
                missile, mesh.points, p.target_base_center, p.target_radius, p.target_height
            )
            clouds = active_clouds(incumbent, time_s, j)
            reference, index, _ = geometry_margin(clouds, missile, mesh.points, visible)
            error = abs(reference - production[ordinal])
            maximum_reference_error = max(maximum_reference_error, error)
            worst_records.append({"missile": q5.MISSILE_NAMES[j], "time_s": time_s,
                                  "reference_margin_m": reference,
                                  "production_margin_m": float(production[ordinal]),
                                  "worst_point_m": mesh.points[index].tolist()})
    passed = maximum_reference_error <= 2e-8 and maximum_label_error <= 1e-12
    return {
        "name": "production_full_obscuration_quantifier",
        "status": "pass" if passed else "fail",
        "maximum_independent_margin_error_m": maximum_reference_error,
        "maximum_relabelling_effect_m": maximum_label_error,
        "sample_records": worst_records,
    }


def audit_mesh_convergence() -> dict:
    incumbent, _ = q5.registered_incumbent()
    times = np.asarray([15.8876, 18., 20., 22., 22.9477, 29.55, 31., 32.2245])
    levels = ((32, 5), (64, 9), (128, 17), (256, 33))
    records = []
    previous = None
    differences = []
    for n_theta, n_levels in levels:
        mesh = q3.surface_mesh(n_theta, n_levels)
        values = np.vstack([q5.strict_margins(incumbent, j, times, mesh) for j in range(3)])
        if previous is not None:
            differences.append(float(np.max(np.abs(values - previous))))
        records.append({"n_theta": n_theta, "n_levels": n_levels,
                        "surface_point_count": len(mesh.points), "times_s": times.tolist(),
                        "margins_m_by_missile": values.tolist()})
        previous = values
    return {
        "name": "historical_geometry_mesh_convergence", "status": "diagnostic",
        "levels": records, "successive_maximum_margin_differences_m": differences,
        "finest_successive_difference_m": differences[-1],
        "claim_boundary": "finite mesh convergence is numerical evidence, not a continuous-surface proof",
    }


def markdown_report(payload: dict) -> str:
    lines = [
        "# Q5 独立几何—物理审计报告", "",
        f"状态：`{payload['status']}`；规格：`{payload['spec_id']}`。", "",
        "本报告只审计几何与运动学，没有执行全域优化，也没有替换正式 Q5 结果。", "",
        "## 结论", "",
    ]
    for check in payload["checks"]:
        lines.append(f"- `{check['name']}`：`{check['status']}`")
    centre = next(check for check in payload["checks"] if check["name"] == "centreline_certificate_and_cloud_union")
    segment = next(check for check in payload["checks"] if check["name"] == "finite_segment_distance")
    visibility = next(check for check in payload["checks"] if check["name"] == "visible_surface_first_hit")
    quantifier = next(check for check in payload["checks"] if check["name"] == "production_full_obscuration_quantifier")
    convergence = next(check for check in payload["checks"] if check["name"] == "historical_geometry_mesh_convergence")
    lines.extend([
        "", "## 关键数值", "",
        f"- 圆柱中点包络半径：{centre['analytic_envelope_radius_m']:.9f} m，小于烟幕半径 10 m。",
        f"- 有限线段距离独立交叉最大误差：{segment['maximum_absolute_error_m']:.3e} m。",
        f"- 可见面非歧义不一致数：{visibility['nonambiguous_mismatch_count']}。",
        f"- 生产全遮蔽余量与独立逐点参考最大差：{quantifier['maximum_independent_margin_error_m']:.3e} m。",
        f"- 历史方案最细两层选定时刻最大余量差：{convergence['finest_successive_difference_m']:.6g} m。",
        "", "## 反例边界", "",
        "- 位于目标之后的烟团对无限直线距离为零，但对有限视线段距离为正，禁止使用无限直线替代。",
        "- 导弹—圆柱底面中心线不具有无条件全圆柱遮蔽证书。",
        "- 两个烟团可以各自不能全遮蔽，但按逐视线并集后实现全遮蔽；不能要求某一个烟团独立覆盖全部表面。",
        "", "## 主张边界", "",
        "通过表示当前离散实现与独立解析/逐点参考在所列检查中一致；不表示已证明连续圆柱上的全局最优，也不表示当前搜索库完整。",
    ])
    return "\n".join(lines) + "\n"


def write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent,
                                     prefix=path.name + ".", suffix=".tmp") as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def run(json_path: Path, report_path: Path) -> dict:
    checks = [
        audit_segment_distance(), audit_visibility(), audit_kinematics(),
        audit_centreline_and_union(), audit_production_quantifier(), audit_mesh_convergence(),
    ]
    critical = [check for check in checks if check["status"] != "diagnostic"]
    status = "pass" if all(check["status"] == "pass" for check in critical) else "fail"
    payload = {
        "schema_version": "1.0", "spec_id": SPEC_ID, "status": status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "independent Q5 geometry and kinematics audit; no optimization",
        "checks": checks,
        "claims": {
            "formal_q5_result_modified": False, "optimization_executed": False,
            "continuous_surface_proved": False, "independent_reference_path_used": True,
            "geometry_audit_passed": status == "pass",
        },
    }
    write_atomic(json_path, json.dumps(q5.ready(payload), ensure_ascii=False, indent=2))
    write_atomic(report_path, markdown_report(payload))
    print(json.dumps({"stage": "q5_geometry_audit_complete", "status": status,
                      "checks": {check["name"]: check["status"] for check in checks}},
                     ensure_ascii=False), flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=ROOT / "docs/q5_geometry_audit.json")
    parser.add_argument("--report", type=Path, default=ROOT / "docs/q5_geometry_audit.md")
    args = parser.parse_args()
    result = run(args.json.resolve(), args.report.resolve())
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
