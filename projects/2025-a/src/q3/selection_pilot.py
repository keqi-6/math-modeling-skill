"""Pre-registered C4 admission pilot for Q3 under SPEC-Q3-1.0.

The pilot compares three fixed-total-budget seed pools: C2, C2+C3, and
C2+C3+C4.  C4 is a genuine point-time surface-coverage construction; every
selected triple is subsequently scored by the same visible-cylinder,
finite-segment, continuous-time evaluator used for all sources.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import scipy
from scipy.optimize import minimize, minimize_scalar
from scipy.special import expit
from scipy.stats import qmc, spearmanr


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
import model as q1  # noqa: E402
sys.path.insert(0, str(ROOT / "src" / "q2"))
import reselection_pilot as q2_inverse  # noqa: E402

SPEC_ID = "SPEC-Q3-1.0"
CLAIM_ID = "A.Q3.C4_ADMISSION_PILOT.001"
INPUT_PATH = Path("data/A题.pdf")
SPEC_PATH = Path("planning/17_q3_model_spec_and_selection.md")
Q1_PATH = Path("src/q1/model.py")
Q2_RESELECTION_PATH = Path("src/q2/reselection_pilot.py")
Q2_RESULT_PATH = Path("docs/q2_result.json")
EXPECTED_HASHES = {
    "official_input_sha256": "a37f6aad30b16ea09da9cb320ce194b12d3a28874008cf9ff19549f6c6079447",
    "spec_sha256": "d3b8f4dc58927665c69c74d0c78965cac742d50785867411b94eab0da1bf6c34",
    "q1_model_sha256": "a7dd496204e30e90000fc8554919309da36fde3a6c45e3a3f4fdca46a55c8669",
    "q2_reselection_sha256": "a65c0153d5a9260eef4678e912be878c0a5937acad9c2c49d89958e6061331b1",
    "q2_result_sha256": "721537914e17404145fa25131bf489776dbc2820444b1b7ae70003ba2069eb88",
}

SEEDS = [250827, 250828, 250829]
N_PROXY, N_SCREEN, N_PRECISE = 96, 6, 2
C3_PROPOSALS = 4096
C4_TRACKS, C4_SINGLES, C4_STARTERS = 12, 32, 8
HALF_WIDTH = 0.18
DURATION_TOL = 1e-4
TIME_TOL = 1e-10
LENGTH_TOL = 1e-8

PRIOR_ATTEMPTS = [
    {
        "attempt_id": "PLAN-Q3-C4-ADMISSION-PILOT-20260827-A",
        "status": "failed_before_screening",
        "failure_code": "Q3_PILOT_UNDERPOWERED",
        "observed": "seed 250827 produced C2=96, C3=96, C4=77 instead of the required 96",
        "disposition": "release-time stratification and distinct alternate triples; no pilot result accepted",
        "formal_outputs_written": False,
    },
    {
        "attempt_id": "PLAN-Q3-C4-ADMISSION-PILOT-20260827-B",
        "status": "interrupted_for_performance_repair",
        "failure_code": "Q3_SURFACE_REFINEMENT_SCALAR_LOOP",
        "observed": "per-root Python loop over all precise surface points made endpoint refinement impractical",
        "disposition": "algebraically identical vectorized point margins; partial paired results discarded",
        "formal_outputs_written": False,
    },
    {
        "attempt_id": "PLAN-Q3-C4-ADMISSION-PILOT-20260827-C",
        "status": "interrupted_for_performance_repair",
        "failure_code": "Q3_DENSIFICATION_REDUNDANT_FULL_SPAN",
        "observed": "nested twofold mesh was scanning the complete active envelope, including known precise-invalid times",
        "disposition": "strictly nested mesh scans precise-positive windows plus brackets; partial run discarded",
        "formal_outputs_written": False,
    },
]

PROXY = {
    "name": "proxy",
    "scan_step_s": 0.10,
    "n_theta": 64,
    "n_levels": 5,
    "root_time_tolerance_s": None,
    "margin_tolerance_m": None,
    "surface_refinement": False,
}
SCREEN = {
    "name": "screen",
    "scan_step_s": 0.02,
    "n_theta": 128,
    "n_levels": 9,
    "root_time_tolerance_s": 1e-7,
    "margin_tolerance_m": 1e-7,
    "surface_refinement": False,
}
PRECISE = {
    "name": "precise",
    "scan_step_s": 0.005,
    "n_theta": 512,
    "n_levels": 33,
    "root_time_tolerance_s": 1e-9,
    "margin_tolerance_m": 1e-8,
    "surface_refinement": True,
}
DENSIFIED = {
    "name": "densified",
    "scan_step_s": 0.005,
    "n_theta": 1024,
    "n_levels": 65,
    "root_time_tolerance_s": 5e-10,
    "margin_tolerance_m": 5e-9,
    "surface_refinement": True,
}


class PilotError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Decision:
    heading_rad: float
    speed_mps: float
    release_times_s: tuple[float, float, float]
    fuse_delays_s: tuple[float, float, float]
    source: str
    proposal_index: int


@dataclass(frozen=True)
class SurfaceMesh:
    points: np.ndarray
    point_normals: np.ndarray
    kinds: np.ndarray
    theta: np.ndarray
    second: np.ndarray
    point_norm2: np.ndarray
    n_theta: int
    n_levels: int


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ready(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [ready(item) for item in value]
    return value


def base_parameters() -> q1.Q1Parameters:
    return q1.default_parameters()


def arrival_time() -> float:
    p = base_parameters()
    return float(np.linalg.norm(p.missile_initial) / p.missile_speed)


def wrap_angle(angle: float) -> float:
    return float(angle % (2.0 * math.pi))


def heading_centers() -> tuple[float, float]:
    p = base_parameters()
    target = p.target_base_center[:2] - p.uav_initial[:2]
    missile = p.missile_initial[:2] - p.uav_initial[:2]
    return (
        math.atan2(float(target[1]), float(target[0])),
        math.atan2(float(missile[1]), float(missile[0])),
    )


def domain_heading(selector: float, coordinate: float) -> tuple[str, float]:
    target, missile = heading_centers()
    if selector < 0.45:
        return "target", wrap_angle(target + (2.0 * coordinate - 1.0) * HALF_WIDTH)
    if selector < 0.90:
        return "missile", wrap_angle(missile + (2.0 * coordinate - 1.0) * HALF_WIDTH)
    return "guard", wrap_angle(2.0 * math.pi * coordinate)


def explosion_times(x: Decision) -> np.ndarray:
    return np.asarray(x.release_times_s) + np.asarray(x.fuse_delays_s)


def explosion_points(x: Decision) -> np.ndarray:
    p = base_parameters()
    te = explosion_times(x)
    direction = np.array([math.cos(x.heading_rad), math.sin(x.heading_rad)])
    xy = p.uav_initial[:2] + x.speed_mps * te[:, None] * direction
    z = p.uav_initial[2] - 0.5 * p.gravity * np.square(np.asarray(x.fuse_delays_s))
    return np.column_stack((xy, z))


def constraint_margins(x: Decision) -> dict[str, float]:
    p = base_parameters()
    tau = np.asarray(x.release_times_s, dtype=float)
    delta = np.asarray(x.fuse_delays_s, dtype=float)
    te = tau + delta
    height = p.uav_initial[2] - 0.5 * p.gravity * delta**2
    t_m = arrival_time()
    return {
        "heading_domain_rad": min(x.heading_rad, 2.0 * math.pi - x.heading_rad),
        "speed_lower_mps": x.speed_mps - 70.0,
        "speed_upper_mps": 140.0 - x.speed_mps,
        "release_1_lower_s": tau[0],
        "release_gap_12_s": tau[1] - tau[0] - 1.0,
        "release_gap_23_s": tau[2] - tau[1] - 1.0,
        "last_release_margin_s": t_m - tau[2],
        "minimum_fuse_delay_s": float(np.min(delta)),
        "minimum_explosion_height_m": float(np.min(height)),
        "minimum_explosion_arrival_margin_s": float(np.min(t_m - te)),
    }


def minimum_constraint_margin(x: Decision) -> float:
    margins = constraint_margins(x)
    return float(min(value for key, value in margins.items() if key != "heading_domain_rad"))


def validate_decision(x: Decision) -> None:
    values = np.array([
        x.heading_rad,
        x.speed_mps,
        *x.release_times_s,
        *x.fuse_delays_s,
    ])
    if not np.all(np.isfinite(values)):
        raise PilotError("Q3_CONSTRAINT_FAILURE", "decision contains non-finite values")
    margins = constraint_margins(x)
    if not 0.0 <= x.heading_rad < 2.0 * math.pi:
        raise PilotError("Q3_CONSTRAINT_FAILURE", "heading outside [0,2pi)")
    checked = {key: value for key, value in margins.items() if key != "heading_domain_rad"}
    if min(checked.values()) < -max(LENGTH_TOL, TIME_TOL):
        raise PilotError("Q3_CONSTRAINT_FAILURE", f"negative hard-constraint margin: {margins}")


def decision_record(x: Decision) -> dict:
    validate_decision(x)
    p = base_parameters()
    tau = np.asarray(x.release_times_s)
    delta = np.asarray(x.fuse_delays_s)
    direction = np.array([math.cos(x.heading_rad), math.sin(x.heading_rad), 0.0])
    release = p.uav_initial + x.speed_mps * tau[:, None] * direction
    explosion = explosion_points(x)
    literal_margin = arrival_time() - float(np.sum(tau))
    return {
        **asdict(x),
        "heading_deg": math.degrees(x.heading_rad) % 360.0,
        "heading_unit": direction.tolist(),
        "explosion_times_s": explosion_times(x).tolist(),
        "release_points_m": release.tolist(),
        "explosion_points_m": explosion.tolist(),
        "constraint_margins": constraint_margins(x),
        "official_literal_sum_release_margin_s": literal_margin,
        "official_literal_sum_release_pass": literal_margin >= -TIME_TOL,
    }


def cloud_center(x: Decision, cloud_index: int, times: np.ndarray) -> np.ndarray:
    p = base_parameters()
    te = explosion_times(x)[cloud_index]
    point = explosion_points(x)[cloud_index]
    result = np.repeat(point.reshape(1, 3), len(times), axis=0)
    result[:, 2] -= p.smoke_sink_speed * (times - te)
    return result


def surface_mesh(n_theta: int, n_levels: int) -> SurfaceMesh:
    p = base_parameters()
    center = p.target_base_center
    angles = np.arange(n_theta, dtype=float) * (2.0 * math.pi / n_theta)
    cosine, sine = np.cos(angles), np.sin(angles)

    heights = np.linspace(0.0, p.target_height, n_levels)
    side_theta = np.tile(angles, n_levels)
    side_z = np.repeat(heights, n_theta)
    side = np.column_stack((
        center[0] + p.target_radius * np.cos(side_theta),
        center[1] + p.target_radius * np.sin(side_theta),
        side_z,
    ))
    side_normals = np.column_stack((np.cos(side_theta), np.sin(side_theta), np.zeros_like(side_theta)))

    # n_levels includes the centre.  Counts 33 -> 65 make the 65-level radial
    # grid a strict superset of the 33-level grid.
    radii = np.linspace(0.0, p.target_radius, n_levels)[1:]
    top_theta = np.tile(angles, len(radii))
    top_radius = np.repeat(radii, n_theta)
    top = np.column_stack((
        center[0] + top_radius * np.cos(top_theta),
        center[1] + top_radius * np.sin(top_theta),
        np.full_like(top_radius, p.target_height),
    ))
    # One explicit centre prevents the polar mesh from omitting a possible
    # max-min switching point without duplicating it n_theta times.
    top = np.vstack((top, np.array([[center[0], center[1], p.target_height]])))
    top_theta = np.concatenate((top_theta, np.array([0.0])))
    top_radius = np.concatenate((top_radius, np.array([0.0])))
    top_normals = np.repeat(np.array([[0.0, 0.0, 1.0]]), len(top), axis=0)

    points = np.vstack((side, top)).astype(np.float64)
    normals = np.vstack((side_normals, top_normals)).astype(np.float64)
    kinds = np.concatenate((np.zeros(len(side), dtype=np.int8), np.ones(len(top), dtype=np.int8)))
    theta = np.concatenate((side_theta, top_theta))
    second = np.concatenate((side_z, top_radius))
    return SurfaceMesh(
        points=points,
        point_normals=normals,
        kinds=kinds,
        theta=theta,
        second=second,
        point_norm2=np.einsum("ij,ij->i", points, points),
        n_theta=n_theta,
        n_levels=n_levels,
    )


def visibility_mask(missiles: np.ndarray, mesh: SurfaceMesh) -> np.ndarray:
    side = mesh.kinds == 0
    top = ~side
    visible = np.zeros((len(missiles), len(mesh.points)), dtype=bool)
    if np.any(side):
        points = mesh.points[side]
        normals = mesh.point_normals[side]
        visible[:, side] = (
            missiles[:, :2] @ normals[:, :2].T
            - np.einsum("ij,ij->i", points[:, :2], normals[:, :2])[None, :]
        ) >= -1e-12
    if np.any(top):
        visible[:, top] = missiles[:, 2, None] >= mesh.points[top, 2][None, :] - 1e-12
    return visible


def _distance_to_segments(
    cloud: np.ndarray, missiles: np.ndarray, mesh: SurfaceMesh,
) -> np.ndarray:
    # Algebraic form avoids materializing a (time, point, xyz) tensor.
    denominator = (
        mesh.point_norm2[None, :]
        + np.einsum("ij,ij->i", missiles, missiles)[:, None]
        - 2.0 * missiles @ mesh.points.T
    )
    if np.any(denominator <= 0.0):
        raise PilotError("Q3_SURFACE_EVALUATOR_FAILURE", "degenerate missile-target segment")
    w = cloud - missiles
    numerator = w @ mesh.points.T - np.einsum("ij,ij->i", w, missiles)[:, None]
    lam = np.clip(numerator / denominator, 0.0, 1.0)
    distance2 = (
        np.einsum("ij,ij->i", w, w)[:, None]
        - 2.0 * lam * numerator
        + lam * lam * denominator
    )
    return np.sqrt(np.maximum(distance2, 0.0))


def joint_margins(
    x: Decision,
    times: np.ndarray,
    mesh: SurfaceMesh,
    cloud_indices: Sequence[int] = (0, 1, 2),
    batch_size: int | None = None,
) -> np.ndarray:
    validate_decision(x)
    p = base_parameters()
    times = np.asarray(times, dtype=float)
    if not np.all(np.isfinite(times)):
        raise PilotError("Q3_TIME_EVENT_FAILURE", "non-finite evaluation time")
    if batch_size is None:
        batch_size = max(4, min(128, int(2_500_000 / max(1, len(mesh.points)))))
    result = np.empty(len(times), dtype=float)
    te = explosion_times(x)
    t_m = arrival_time()
    for left in range(0, len(times), batch_size):
        right = min(len(times), left + batch_size)
        block = times[left:right]
        missiles = np.vstack([q1.missile_position(float(t), p) for t in block])
        visible = visibility_mask(missiles, mesh)
        minimum = np.full((len(block), len(mesh.points)), np.inf, dtype=float)
        for cloud_index in cloud_indices:
            active = (
                (block >= te[cloud_index] - TIME_TOL)
                & (block <= np.minimum(te[cloud_index] + p.smoke_duration, t_m) + TIME_TOL)
            )
            if not np.any(active):
                continue
            centers = cloud_center(x, cloud_index, block)
            distances = _distance_to_segments(centers, missiles, mesh)
            distances[~active, :] = np.inf
            minimum = np.minimum(minimum, distances)
        margins = minimum - p.smoke_radius
        margins[~visible] = -np.inf
        block_result = np.max(margins, axis=1)
        block_result[~np.any(visible, axis=1)] = np.inf
        result[left:right] = block_result
    if np.any(np.isnan(result)):
        raise PilotError("Q3_SURFACE_EVALUATOR_FAILURE", "NaN joint margin")
    return result


def single_coverage_tensor(
    x: Decision, cloud_index: int, times: np.ndarray, mesh: SurfaceMesh,
) -> tuple[np.ndarray, np.ndarray]:
    p = base_parameters()
    times = np.asarray(times, dtype=float)
    missiles = np.vstack([q1.missile_position(float(t), p) for t in times])
    visible = visibility_mask(missiles, mesh)
    coverage = np.zeros_like(visible)
    te = explosion_times(x)[cloud_index]
    active = (times >= te - TIME_TOL) & (times <= min(te + p.smoke_duration, arrival_time()) + TIME_TOL)
    batch = max(8, min(128, int(2_500_000 / max(1, len(mesh.points)))))
    for left in range(0, len(times), batch):
        right = min(len(times), left + batch)
        centers = cloud_center(x, cloud_index, times[left:right])
        distance = _distance_to_segments(centers, missiles[left:right], mesh)
        coverage[left:right] = distance <= p.smoke_radius
    coverage[~active, :] = False
    coverage[~visible] = False
    return coverage, visible


def _point_margin(x: Decision, t: float, point: np.ndarray, cloud_indices: Sequence[int]) -> float:
    p = base_parameters()
    missile = q1.missile_position(t, p)
    vectors = point.reshape(1, 3) - missile
    best = math.inf
    te = explosion_times(x)
    for cloud_index in cloud_indices:
        if not te[cloud_index] - TIME_TOL <= t <= min(te[cloud_index] + p.smoke_duration, arrival_time()) + TIME_TOL:
            continue
        center = cloud_center(x, cloud_index, np.array([t]))[0]
        distance, _ = q1.segment_distance(center, missile, vectors)
        best = min(best, float(distance[0]) - p.smoke_radius)
    return best


def point_margins_at_time(
    x: Decision, t: float, mesh: SurfaceMesh, cloud_indices: Sequence[int],
) -> tuple[np.ndarray, np.ndarray]:
    """Return every visible mesh-point margin with vectorized cloud geometry."""
    p = base_parameters()
    missile = q1.missile_position(t, p).reshape(1, 3)
    visible = visibility_mask(missile, mesh)[0]
    minimum = np.full(len(mesh.points), np.inf, dtype=float)
    te = explosion_times(x)
    for cloud_index in cloud_indices:
        if not te[cloud_index] - TIME_TOL <= t <= min(te[cloud_index] + p.smoke_duration, arrival_time()) + TIME_TOL:
            continue
        center = cloud_center(x, cloud_index, np.array([t]))
        minimum = np.minimum(minimum, _distance_to_segments(center, missile, mesh)[0])
    values = minimum - p.smoke_radius
    values[~visible] = -np.inf
    return values, visible


def refined_surface_margin(
    x: Decision, t: float, mesh: SurfaceMesh, cloud_indices: Sequence[int], starts: int = 4,
) -> tuple[float, dict]:
    p = base_parameters()
    missile = q1.missile_position(t, p)
    point_values, visible = point_margins_at_time(x, t, mesh, cloud_indices)
    grid = float(np.max(point_values))
    if not math.isfinite(float(grid)):
        return float(grid), {"grid_margin_m": float(grid), "refined": False}

    # Recover per-point margins once and refine the largest grid witnesses on
    # their native side/top parameter cells.  min_k stays inside the objective,
    # so smoke-identity switching is retained during local refinement.
    order = np.argsort(-point_values)[:starts]
    candidates = [(float(grid), None)]
    angle_step = 2.0 * math.pi / mesh.n_theta
    level_step_z = p.target_height / max(1, mesh.n_levels - 1)
    level_step_r = p.target_radius / mesh.n_levels

    for index in order:
        kind = int(mesh.kinds[index])
        theta0 = float(mesh.theta[index])
        second0 = float(mesh.second[index])
        if kind == 0:
            bounds = [
                (theta0 - angle_step, theta0 + angle_step),
                (max(0.0, second0 - level_step_z), min(p.target_height, second0 + level_step_z)),
            ]

            def point_from(y):
                return np.array([
                    p.target_base_center[0] + p.target_radius * math.cos(y[0]),
                    p.target_base_center[1] + p.target_radius * math.sin(y[0]),
                    y[1],
                ])
        else:
            bounds = [
                (theta0 - angle_step, theta0 + angle_step),
                (max(0.0, second0 - level_step_r), min(p.target_radius, second0 + level_step_r)),
            ]

            def point_from(y):
                return np.array([
                    p.target_base_center[0] + y[1] * math.cos(y[0]),
                    p.target_base_center[1] + y[1] * math.sin(y[0]),
                    p.target_height,
                ])

        def objective(y):
            point = point_from(y)
            if kind == 0:
                normal = np.array([math.cos(y[0]), math.sin(y[0]), 0.0])
                if float(np.dot(normal, missile - point)) < -1e-9:
                    return 1e3
            elif missile[2] < p.target_height - 1e-9:
                return 1e3
            value = _point_margin(x, t, point, cloud_indices)
            return -value if math.isfinite(value) else 1e3

        optimization = minimize(
            objective,
            np.array([theta0, second0]),
            method="Powell",
            bounds=bounds,
            options={"maxiter": 35, "maxfev": 100, "xtol": 1e-9, "ftol": 1e-10},
        )
        if optimization.success and math.isfinite(float(optimization.fun)):
            candidates.append((-float(optimization.fun), {"kind": kind, "parameters": optimization.x.tolist()}))
    value, witness = max(candidates, key=lambda item: item[0])
    return value, {
        "grid_margin_m": float(grid),
        "refined": witness is not None,
        "refined_margin_m": float(value),
        "witness": witness,
    }


def _time_grid(
    x: Decision,
    step: float,
    cloud_indices: Sequence[int],
    restrict_windows: Sequence[Sequence[float]] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    p = base_parameters()
    te = explosion_times(x)
    events = np.array(sorted({
        *[float(te[k]) for k in cloud_indices],
        *[float(min(te[k] + p.smoke_duration, arrival_time())) for k in cloud_indices],
        float(arrival_time()),
    }), dtype=float)
    active_windows = merge_intervals([
        [float(te[k]), float(min(te[k] + p.smoke_duration, arrival_time()))]
        for k in cloud_indices
    ])
    if restrict_windows is not None:
        restricted: list[list[float]] = []
        for a, b in active_windows:
            for c, d in restrict_windows:
                left, right = max(a, float(c)), min(b, float(d))
                if right >= left:
                    restricted.append([left, right])
        active_windows = merge_intervals(restricted)
    pieces: list[float] = []
    for active_left, active_right in active_windows:
        boundaries = sorted({
            float(active_left), float(active_right),
            *[float(value) for value in events if active_left < value < active_right],
        })
        for left, right in zip(boundaries[:-1], boundaries[1:]):
            count = max(1, int(math.ceil((right - left) / step)))
            pieces.extend(np.linspace(left, right, count + 1).tolist())
    return np.array(sorted(set(pieces)), dtype=float), events


def _bisect_time_root(
    x: Decision,
    left: float,
    right: float,
    mesh: SurfaceMesh,
    cloud_indices: Sequence[int],
    time_tolerance: float,
    margin_tolerance: float,
    refine_surface: bool,
) -> tuple[float, float, int, bool]:
    evaluator = (
        (lambda t: refined_surface_margin(x, t, mesh, cloud_indices)[0])
        if refine_surface
        else (lambda t: float(joint_margins(x, np.array([t]), mesh, cloud_indices)[0]))
    )
    f_left, f_right = evaluator(left), evaluator(right)
    if not math.isfinite(f_left) or not math.isfinite(f_right) or f_left * f_right > 0.0:
        # The mesh scan can bracket a root that moves slightly under continuous
        # surface refinement.  Preserve the conservative inside endpoint and
        # expose the fallback instead of fabricating a converged bisection.
        endpoint = left if f_left <= 0.0 else right
        residual = f_left if f_left <= 0.0 else f_right
        return endpoint, residual, 0, True
    midpoint, f_mid = 0.5 * (left + right), math.nan
    for iteration in range(1, 101):
        midpoint = 0.5 * (left + right)
        f_mid = evaluator(midpoint)
        if not math.isfinite(f_mid):
            raise PilotError("Q3_TIME_EVENT_FAILURE", "non-finite root residual")
        if right - left <= time_tolerance and abs(f_mid) <= margin_tolerance:
            return midpoint, f_mid, iteration, False
        if f_left == 0.0:
            return left, f_left, iteration, False
        if f_right == 0.0:
            return right, f_right, iteration, False
        if f_left * f_mid <= 0.0:
            right, f_right = midpoint, f_mid
        else:
            left, f_left = midpoint, f_mid
    return midpoint, f_mid, 100, True


def merge_intervals(intervals: Iterable[Sequence[float]], tolerance: float = 2e-9) -> list[list[float]]:
    ordered = sorted((float(a), float(b)) for a, b in intervals if b >= a)
    merged: list[list[float]] = []
    for left, right in ordered:
        if merged and left <= merged[-1][1] + tolerance:
            merged[-1][1] = max(merged[-1][1], right)
        else:
            merged.append([left, right])
    return merged


def interval_measure(intervals: Iterable[Sequence[float]]) -> float:
    return float(sum(float(right) - float(left) for left, right in merge_intervals(intervals)))


def interval_difference(left: Iterable[Sequence[float]], right: Iterable[Sequence[float]]) -> list[list[float]]:
    remaining = merge_intervals(left)
    cutters = merge_intervals(right)
    for cut_left, cut_right in cutters:
        updated: list[list[float]] = []
        for a, b in remaining:
            if cut_right <= a + TIME_TOL or cut_left >= b - TIME_TOL:
                updated.append([a, b])
                continue
            if a < cut_left - TIME_TOL:
                updated.append([a, min(b, cut_left)])
            if b > cut_right + TIME_TOL:
                updated.append([max(a, cut_right), b])
        remaining = updated
    return merge_intervals(remaining)


def solve_intervals(
    x: Decision,
    settings: dict,
    cloud_indices: Sequence[int] = (0, 1, 2),
    mesh: SurfaceMesh | None = None,
    restrict_windows: Sequence[Sequence[float]] | None = None,
) -> dict:
    mesh = surface_mesh(settings["n_theta"], settings["n_levels"]) if mesh is None else mesh
    times, events = _time_grid(x, settings["scan_step_s"], cloud_indices, restrict_windows)
    if len(times) == 0:
        return {
            "settings": dict(settings), "surface_point_count": int(len(mesh.points)),
            "scan_count": 0, "intervals_s": [], "effective_duration_s": 0.0,
            "minimum_scan_margin_m": float("inf"), "root_residuals": [], "root_fallback_count": 0,
        }
    margins = joint_margins(x, times, mesh, cloud_indices)
    inside = margins <= 0.0
    intervals: list[list[float]] = []
    residuals: list[dict] = []
    fallback_count = 0
    index = 0
    while index < len(times):
        if not inside[index]:
            index += 1
            continue
        first = index
        while (
            index + 1 < len(times)
            and inside[index + 1]
            and times[index + 1] - times[index] <= settings["scan_step_s"] * (1.0 + 1e-6)
        ):
            index += 1
        last = index

        previous_gap = first == 0 or times[first] - times[first - 1] > settings["scan_step_s"] * (1.0 + 1e-6)
        if previous_gap or np.any(np.isclose(times[first], events, atol=TIME_TOL, rtol=0.0)):
            entry = float(times[first])
            entry_residual = float(margins[first])
            entry_iterations = 0
            entry_fallback = False
        else:
            entry, entry_residual, entry_iterations, entry_fallback = _bisect_time_root(
                x, float(times[first - 1]), float(times[first]), mesh, cloud_indices,
                settings["root_time_tolerance_s"], settings["margin_tolerance_m"],
                settings["surface_refinement"],
            )
        following_gap = last == len(times) - 1 or times[last + 1] - times[last] > settings["scan_step_s"] * (1.0 + 1e-6)
        if following_gap or np.any(np.isclose(times[last], events, atol=TIME_TOL, rtol=0.0)):
            exit_time = float(times[last])
            exit_residual = float(margins[last])
            exit_iterations = 0
            exit_fallback = False
        else:
            exit_time, exit_residual, exit_iterations, exit_fallback = _bisect_time_root(
                x, float(times[last]), float(times[last + 1]), mesh, cloud_indices,
                settings["root_time_tolerance_s"], settings["margin_tolerance_m"],
                settings["surface_refinement"],
            )
        fallback_count += int(entry_fallback) + int(exit_fallback)
        intervals.append([entry, exit_time])
        residuals.extend([
            {"kind": "entry", "time_s": entry, "margin_m": entry_residual, "iterations": entry_iterations, "fallback": entry_fallback},
            {"kind": "exit", "time_s": exit_time, "margin_m": exit_residual, "iterations": exit_iterations, "fallback": exit_fallback},
        ])
        index += 1

    evaluator = (
        (lambda t: refined_surface_margin(x, float(t), mesh, cloud_indices)[0])
        if settings["surface_refinement"]
        else (lambda t: float(joint_margins(x, np.array([float(t)]), mesh, cloud_indices)[0]))
    )
    try:
        tangencies = q1.recover_unsampled_intervals(
            times,
            margins,
            evaluator,
            time_tolerance=float(settings["root_time_tolerance_s"] or 1e-8),
            margin_tolerance=float(settings["margin_tolerance_m"] or 1e-7),
            maximum_gap=float(settings["scan_step_s"]) * (1.0 + 1e-6),
        )
    except q1.Q1Error as error:
        raise PilotError("Q3_TIME_EVENT_FAILURE", str(error)) from error
    intervals.extend(tangencies["recovered_intervals_s"])
    for item in tangencies["records"]:
        residuals.extend([
            {
                "kind": "entry_from_local_minimum",
                "time_s": item["entry_time_s"],
                "margin_m": item["entry_margin_m"],
                "iterations": item["entry_iterations"],
                "fallback": False,
            },
            {
                "kind": "exit_from_local_minimum",
                "time_s": item["exit_time_s"],
                "margin_m": item["exit_margin_m"],
                "iterations": item["exit_iterations"],
                "fallback": False,
            },
        ])
    merged = merge_intervals(intervals)
    return {
        "settings": dict(settings),
        "surface_point_count": int(len(mesh.points)),
        "scan_count": int(len(times)),
        "intervals_s": merged,
        "effective_duration_s": interval_measure(merged),
        "minimum_scan_margin_m": float(np.min(margins)),
        "root_residuals": residuals,
        "root_fallback_count": fallback_count,
        "local_minimum_checks": tangencies["checked_local_minima"],
        "recovered_unsampled_interval_count": len(tangencies["recovered_intervals_s"]),
        "local_minimum_records": tangencies["records"],
    }


def centerline_distance(point: np.ndarray, time_s: float) -> float:
    p = base_parameters()
    missile = q1.missile_position(time_s, p)
    target = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    distance, _ = q1.segment_distance(point, missile, target.reshape(1, 3))
    return float(distance[0])


def generate_c2(seed: int) -> tuple[list[Decision], dict]:
    sample = qmc.LatinHypercube(d=9, seed=seed).random(N_PROXY)
    t_m = arrival_time()
    p = base_parameters()
    delta_cap = math.sqrt(2.0 * p.uav_initial[2] / p.gravity)
    values: list[Decision] = []
    domains = {"target": 0, "missile": 0, "guard": 0}
    for index, row in enumerate(sample):
        domain, heading = domain_heading(float(row[0]), float(row[1]))
        speed = 70.0 + 70.0 * float(row[2])
        tau1 = (t_m - 2.0) * float(row[3])
        tau2 = tau1 + 1.0 + (t_m - tau1 - 2.0) * float(row[4])
        tau3 = tau2 + 1.0 + (t_m - tau2 - 1.0) * float(row[5])
        tau = np.array([tau1, tau2, tau3])
        delta = np.array([
            float(row[6 + k]) * min(delta_cap, t_m - tau[k]) for k in range(3)
        ])
        decision = Decision(heading, speed, tuple(tau), tuple(delta), f"C2_{domain}", index)
        validate_decision(decision)
        values.append(decision)
        domains[domain] += 1
    return values, {"status": "pass", "candidate_count": len(values), "domain_counts": domains, "proposal_count": len(sample)}


def inverse_service_state(
    observation_time: float,
    smoke_age: float,
    sight_fraction: float,
    source: str,
    index: int,
) -> Decision:
    """Map a desired LOS service state back to a feasible shared UAV track."""
    p = base_parameters()
    if not (0.0 < observation_time < arrival_time() and 0.0 <= smoke_age <= p.smoke_duration):
        raise PilotError("Q3_CONSTRAINT_FAILURE", "inverse service time/age outside domain")
    if not 0.0 < sight_fraction < 1.0:
        raise PilotError("Q3_CONSTRAINT_FAILURE", "inverse sight fraction outside open segment")
    explosion_time = observation_time - smoke_age
    if explosion_time <= 0.0:
        raise PilotError("Q3_CONSTRAINT_FAILURE", "inverse explosion time is nonpositive")
    missile = q1.missile_position(observation_time, p)
    target = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    desired_cloud = missile + sight_fraction * (target - missile)
    explosion = desired_cloud + np.array([0.0, 0.0, p.smoke_sink_speed * smoke_age])
    if not 0.0 <= explosion[2] <= p.uav_initial[2]:
        raise PilotError("Q3_CONSTRAINT_FAILURE", "inverse explosion height is unreachable")
    delta = math.sqrt(2.0 * (p.uav_initial[2] - float(explosion[2])) / p.gravity)
    tau = explosion_time - delta
    displacement = explosion[:2] - p.uav_initial[:2]
    speed = float(np.linalg.norm(displacement) / explosion_time)
    heading = wrap_angle(math.atan2(float(displacement[1]), float(displacement[0])))
    if tau < 0.0 or tau + 2.0 > arrival_time() or not 70.0 <= speed <= 140.0:
        raise PilotError("Q3_CONSTRAINT_FAILURE", "inverse service state violates release or speed limits")
    decision = Decision(
        heading,
        speed,
        (tau, tau + 1.0, tau + 2.0),
        (delta, delta, delta),
        source,
        index,
    )
    validate_decision(decision)
    return decision


def generate_c3(seed: int) -> tuple[list[Decision], dict]:
    """Inverse-geometry C3 seeds in service-time rather than raw controls."""
    sample = qmc.LatinHypercube(d=3, seed=seed + 101).random(C3_PROPOSALS)
    p = base_parameters()
    t_m = arrival_time()
    feasible: list[tuple[float, float, int, Decision]] = []
    failures = 0
    for index, row in enumerate(sample):
        observation = t_m * (0.05 + 0.90 * float(row[0]))
        age_cap = min(p.smoke_duration, 0.95 * observation)
        age = age_cap * float(row[1])
        intervals = q2_inverse.q_intervals(observation, age, p)
        lengths = np.asarray([max(0.0, hi - lo) for lo, hi in intervals], dtype=float)
        total = float(np.sum(lengths))
        if not intervals or total <= 0.0:
            failures += 1
            continue
        target_length = min(float(row[2]), np.nextafter(1.0, 0.0)) * total
        carried = 0.0
        fraction = float(intervals[-1][1])
        for (left, right), length in zip(intervals, lengths):
            if target_length <= carried + length:
                fraction = float(left + target_length - carried)
                break
            carried += float(length)
        try:
            decision = inverse_service_state(
                observation, age, fraction, "C3_inverse_service_clone", index,
            )
        except PilotError:
            failures += 1
            continue
        # Prefer interior feasibility, then distribute the selected service
        # times instead of collapsing all starts onto a single instant.
        interior = minimum_constraint_margin(decision)
        feasible.append((-interior, observation, index, decision))
    feasible.sort(key=lambda item: (item[0], item[1], item[2]))
    strata = np.array_split(np.arange(len(feasible)), N_PROXY) if feasible else []
    chosen_records = [
        min((feasible[int(i)] for i in group), key=lambda item: (item[0], item[2]))
        for group in strata if len(group)
    ]
    chosen = [item[3] for item in chosen_records[:N_PROXY]]
    status = "pass" if len(chosen) == N_PROXY else "Q3_PILOT_UNDERPOWERED"
    return chosen, {
        "status": status,
        "construction": "inverse_service_time_age_los_fraction_then_staggered_clone",
        "proposal_count": len(sample),
        "feasible_count": len(feasible),
        "rejected_count": failures,
        "candidate_count": len(chosen),
        "selected_observation_time_range_s": [
            float(min(item[1] for item in chosen_records)) if chosen_records else None,
            float(max(item[1] for item in chosen_records)) if chosen_records else None,
        ],
    }


def single_decision(heading: float, speed: float, tau: float, delta: float, source: str, index: int) -> Decision:
    # Duplicate the physical single across labels; callers explicitly select
    # cloud 0.  This keeps one frozen Decision schema everywhere.
    gap_tau = min(arrival_time(), tau + 2.0)
    releases = (tau, min(arrival_time() - 1.0, tau + 1.0), gap_tau)
    if releases[2] - releases[1] < 1.0 - TIME_TOL:
        shift = max(0.0, arrival_time() - 2.0)
        releases = (shift, shift + 1.0, shift + 2.0)
    decision = Decision(heading, speed, tuple(releases), (delta, 0.0, 0.0), source, index)
    validate_decision(decision)
    return decision


def single_corridor_score(x: Decision) -> float:
    p = base_parameters()
    te = explosion_times(x)[0]
    stop = min(te + p.smoke_duration, arrival_time())
    ages = np.linspace(0.0, max(0.0, stop - te), 7)
    distances = []
    for age in ages:
        t = te + float(age)
        center = cloud_center(x, 0, np.array([t]))[0]
        distances.append(centerline_distance(center, t))
    return float(min(distances))


def generate_single_bank(heading: float, speed: float, seed: int, track_index: int) -> list[Decision]:
    p = base_parameters()
    t_m = arrival_time()
    delta_cap = math.sqrt(2.0 * p.uav_initial[2] / p.gravity)
    sample = qmc.LatinHypercube(d=2, seed=seed + 1009 * (track_index + 1)).random(192)
    candidates: list[tuple[float, int, Decision]] = []
    for index, row in enumerate(sample):
        delta = delta_cap * float(row[0])
        tau = max(0.0, t_m - delta) * float(row[1])
        try:
            decision = single_decision(heading, speed, tau, delta, f"C4_single_track_{track_index}", index)
        except PilotError:
            continue
        candidates.append((single_corridor_score(decision), index, decision))
    candidates.sort(key=lambda item: (item[0], item[1]))
    if len(candidates) < C4_SINGLES:
        raise PilotError("Q3_PILOT_UNDERPOWERED", f"C4 track {track_index} produced only {len(candidates)} singles")
    # Preserve both corridor quality and release-time diversity.  Taking only
    # the smallest corridor distances can collapse the library to one narrow
    # time band and make eight distinct starter triples impossible.
    selected: list[tuple[float, int, Decision]] = list(candidates[:16])
    by_release = sorted(candidates, key=lambda item: (item[2].release_times_s[0], item[0], item[1]))
    for group in np.array_split(np.arange(len(by_release)), 16):
        if len(group):
            selected.append(min((by_release[int(i)] for i in group), key=lambda item: (item[0], item[1])))
    unique: dict[tuple[float, ...], tuple[float, int, Decision]] = {}
    for item in selected + candidates:
        unique.setdefault(decision_key(item[2]), item)
        if len(unique) >= C4_SINGLES:
            break
    return [item[2] for item in list(unique.values())[:C4_SINGLES]]


def triple_from_singles(singles: Sequence[Decision], source: str, proposal_index: int) -> Decision:
    ordered = sorted(
        ((item.release_times_s[0], item.fuse_delays_s[0]) for item in singles),
        key=lambda item: item[0],
    )
    reference = singles[0]
    decision = Decision(
        reference.heading_rad,
        reference.speed_mps,
        tuple(float(item[0]) for item in ordered),
        tuple(float(item[1]) for item in ordered),
        source,
        proposal_index,
    )
    validate_decision(decision)
    return decision


def releases_compatible(items: Sequence[Decision]) -> bool:
    tau = sorted(item.release_times_s[0] for item in items)
    return all(b - a >= 1.0 - TIME_TOL for a, b in zip(tau[:-1], tau[1:]))


def coverage_score(union: np.ndarray, visible: np.ndarray) -> tuple[int, int]:
    full = np.all(union | ~visible, axis=1)
    return int(np.sum(full)), int(np.sum(union & visible))


def generate_c4(seed: int, mesh: SurfaceMesh, proxy_times: np.ndarray) -> tuple[list[Decision], dict]:
    tracks_lhs = qmc.LatinHypercube(d=3, seed=seed + 303).random(C4_TRACKS)
    values: list[Decision] = []
    track_records = []
    dedup: set[tuple[float, ...]] = set()
    for track_index, row in enumerate(tracks_lhs):
        domain, heading = domain_heading(float(row[0]), float(row[1]))
        speed = 70.0 + 70.0 * float(row[2])
        singles = generate_single_bank(heading, speed, seed, track_index)
        coverages = []
        visible = None
        for single in singles:
            coverage, current_visible = single_coverage_tensor(single, 0, proxy_times, mesh)
            coverages.append(coverage)
            if visible is None:
                visible = current_visible
        assert visible is not None
        complete_masks = [np.all(coverage | ~visible, axis=1) for coverage in coverages]
        single_order = sorted(
            range(len(singles)),
            key=lambda index: (
                -int(np.sum(complete_masks[index])),
                -coverage_score(coverages[index], visible)[1],
                singles[index].release_times_s[0],
                index,
            ),
        )
        produced = 0
        for starter in single_order[:C4_STARTERS]:
            pair_options = []
            for second in range(len(singles)):
                if second == starter or not releases_compatible([singles[starter], singles[second]]):
                    continue
                pair_union = coverages[starter] | coverages[second]
                individual_union = complete_masks[starter] | complete_masks[second]
                pair_options.append((
                    int(np.sum(individual_union)),
                    *coverage_score(pair_union, visible),
                    -singles[second].release_times_s[0], -second,
                    second, pair_union, individual_union,
                ))
            pair_options.sort(key=lambda item: item[:5], reverse=True)
            triple_options = []
            for pair in pair_options[:4]:
                second, pair_union, pair_individual_union = pair[-3], pair[-2], pair[-1]
                for third in range(len(singles)):
                    indices = [starter, second, third]
                    if third in (starter, second) or not releases_compatible([singles[i] for i in indices]):
                        continue
                    joint_score = coverage_score(pair_union | coverages[third], visible)
                    individual_score = int(np.sum(pair_individual_union | complete_masks[third]))
                    triple_options.append((
                        individual_score,
                        *joint_score,
                        -sum(singles[i].release_times_s[0] for i in indices),
                        -third,
                        indices,
                    ))
            triple_options.sort(key=lambda item: item[:-1], reverse=True)
            accepted = None
            for option in triple_options:
                indices = option[-1]
                triple = triple_from_singles(
                    [singles[index] for index in indices],
                    f"C4_{domain}_track_{track_index}",
                    track_index * C4_STARTERS + starter,
                )
                key = decision_key(triple)
                if key not in dedup:
                    accepted = (key, triple)
                    break
            if accepted is None:
                continue
            key, triple = accepted
            dedup.add(key)
            values.append(triple)
            produced += 1
        track_records.append({
            "track_index": track_index,
            "domain": domain,
            "heading_rad": heading,
            "speed_mps": speed,
            "single_candidate_count": len(singles),
            "triple_count": produced,
        })
    status = "pass" if len(values) == N_PROXY else "Q3_PILOT_UNDERPOWERED"
    return values[:N_PROXY], {
        "status": status,
        "track_count": len(track_records),
        "single_candidates_per_track": C4_SINGLES,
        "starter_count_per_track": C4_STARTERS,
        "candidate_count": min(len(values), N_PROXY),
        "raw_unique_triple_count": len(values),
        "tracks": track_records,
        "construction": "individual_complete_cover_interval_union_primary_with_joint_surface_synergy_secondary",
    }


def proxy_score(x: Decision, mesh: SurfaceMesh) -> dict:
    times, _ = _time_grid(x, PROXY["scan_step_s"], (0, 1, 2))
    margins = joint_margins(x, times, mesh)
    finite = np.isfinite(margins)
    soft = np.zeros_like(margins)
    scaled = margins[finite] / 2.0
    # The logistic term is accurate near the boundary; the small rational
    # tail prevents distant but finite candidates from becoming exactly
    # indistinguishable on an all-zero floating-point plateau.
    soft[finite] = expit(-scaled) + 1e-4 / (1.0 + np.maximum(scaled, 0.0))
    score = float(np.trapezoid(soft, times))
    grid_duration = float(np.trapezoid((margins <= 0.0).astype(float), times))
    return {
        "soft_score_s": score,
        "grid_duration_s": grid_duration,
        "minimum_margin_m": float(np.min(margins)),
        "time_count": int(len(times)),
    }


def decision_key(x: Decision) -> tuple[float, ...]:
    return tuple(round(value, 12) for value in (
        x.heading_rad, x.speed_mps, *x.release_times_s, *x.fuse_delays_s,
    ))


def build_pools(c2: list[Decision], c3: list[Decision], c4: list[Decision]) -> dict[str, list[Decision]]:
    if min(len(c2), len(c3), len(c4)) < N_PROXY:
        raise PilotError("Q3_PILOT_UNDERPOWERED", f"base bank sizes: C2={len(c2)}, C3={len(c3)}, C4={len(c4)}")
    return {
        "C2": c2[:96],
        "C2+C3": c2[:48] + c3[:48],
        "C2+C3+C4": c2[:32] + c3[:32] + c4[:32],
    }


def score_pool(
    pool_name: str,
    seed: int,
    candidates: list[Decision],
    proxy_mesh: SurfaceMesh,
    screen_mesh: SurfaceMesh,
    precise_mesh: SurfaceMesh,
    proxy_cache: dict[tuple[float, ...], dict],
) -> dict:
    started = time.perf_counter()
    proxy_started = time.perf_counter()
    proxy_records = []
    for index, decision in enumerate(candidates):
        key = decision_key(decision)
        if key not in proxy_cache:
            proxy_cache[key] = proxy_score(decision, proxy_mesh)
        proxy_records.append({
            "pool_index": index,
            "decision": decision,
            "proxy": proxy_cache[key],
        })
    proxy_seconds = time.perf_counter() - proxy_started
    finalists = sorted(
        proxy_records,
        key=lambda item: (-item["proxy"]["soft_score_s"], -item["proxy"]["grid_duration_s"], item["pool_index"]),
    )[:N_SCREEN]
    screen_records = []
    for call, item in enumerate(finalists, 1):
        print(json.dumps({"stage": "screen", "pool": pool_name, "seed": seed, "call": call, "total": N_SCREEN}), flush=True)
        continuous = solve_intervals(item["decision"], SCREEN, mesh=screen_mesh)
        screen_records.append({
            "call_index": call,
            "pool_index": item["pool_index"],
            "proxy": item["proxy"],
            "decision": item["decision"],
            "screen": continuous,
        })
    precise_inputs = sorted(
        screen_records,
        key=lambda item: (
            -item["screen"]["effective_duration_s"],
            -minimum_constraint_margin(item["decision"]),
            -item["proxy"]["soft_score_s"],
            item["pool_index"],
        ),
    )[:N_PRECISE]
    precise_records = []
    for rank, item in enumerate(precise_inputs, 1):
        print(json.dumps({"stage": "precise", "pool": pool_name, "seed": seed, "call": rank, "total": N_PRECISE}), flush=True)
        precise = solve_intervals(item["decision"], PRECISE, mesh=precise_mesh)
        precise_records.append({
            "rank": rank,
            "pool_index": item["pool_index"],
            "proxy": item["proxy"],
            "screen_duration_s": item["screen"]["effective_duration_s"],
            "decision": item["decision"],
            "precise": precise,
        })
    proxy_values = np.array([item["proxy"]["soft_score_s"] for item in screen_records])
    screen_values = np.array([item["screen"]["effective_duration_s"] for item in screen_records])
    if len(np.unique(proxy_values)) > 1 and len(np.unique(screen_values)) > 1:
        rho = float(spearmanr(proxy_values, screen_values).statistic)
    else:
        rho = None
    systematic_reversal = bool(
        (rho is not None and rho < -0.25)
        or (np.all(screen_values[:3] <= DURATION_TOL) and np.any(screen_values[3:] > DURATION_TOL))
    )
    best = max((item["precise"]["effective_duration_s"] for item in precise_records), default=0.0)
    return {
        "pool": pool_name,
        "seed": seed,
        "status": "completed",
        "logical_proxy_calls": len(proxy_records),
        "proxy_seconds": proxy_seconds,
        "proxy_records": [
            {"pool_index": item["pool_index"], "source": item["decision"].source, "proposal_index": item["decision"].proposal_index, "proxy": item["proxy"]}
            for item in proxy_records
        ],
        "screen_calls": len(screen_records),
        "positive_screen_count": int(np.sum(screen_values > DURATION_TOL)),
        "proxy_screen_spearman": rho,
        "systematic_proxy_reversal": systematic_reversal,
        "screen_records": [
            {**item, "decision": decision_record(item["decision"])} for item in screen_records
        ],
        "precise_calls": len(precise_records),
        "precise_records": [
            {**item, "decision": decision_record(item["decision"])} for item in precise_records
        ],
        "_precise_objects": precise_records,
        "seed_best_precise_duration_s": float(best),
        "elapsed_seconds": time.perf_counter() - started,
    }


def baseline_b0() -> Decision:
    data = json.loads((ROOT / Q2_RESULT_PATH).read_text(encoding="utf-8"))
    q2_best = data["formal_best"]["decision"]
    tau = float(q2_best["release_time_s"])
    delta = float(q2_best["fuse_delay_s"])
    return Decision(
        float(q2_best["heading_rad"]),
        float(q2_best["speed_mps"]),
        (tau, tau + 1.0, tau + 2.0),
        (delta, delta, delta),
        "B0_q2_staggered_clone",
        0,
    )


def baseline_c1(
    b0: Decision,
    proxy_mesh: SurfaceMesh,
    strict_mesh: SurfaceMesh | None = None,
) -> Decision:
    """Frozen C1: greedily maximize strict interval marginal gains.

    The old implementation ranked a coarse Boolean point-time tensor.  C1's
    contract is instead J1, then J12-J1, then J123-J12 on a fixed flight path.
    We evaluate those quantities as unions of strict single-cloud intervals;
    the resulting triple still returns to the full joint Q3 evaluator.
    """
    del proxy_mesh  # retained in the public signature for backwards callers
    strict_mesh = surface_mesh(SCREEN["n_theta"], SCREEN["n_levels"]) if strict_mesh is None else strict_mesh
    b0_first = single_decision(
        b0.heading_rad,
        b0.speed_mps,
        b0.release_times_s[0],
        b0.fuse_delays_s[0],
        "C1_exact_B0_first",
        -1,
    )
    raw_bank = [b0_first, *generate_single_bank(b0.heading_rad, b0.speed_mps, 1103, 0)]
    bank = list({decision_key(item): item for item in raw_bank}.values())
    strict = [
        solve_intervals(item, SCREEN, cloud_indices=(0,), mesh=strict_mesh)
        for item in bank
    ]

    first = max(
        range(len(bank)),
        key=lambda index: (
            float(strict[index]["effective_duration_s"]),
            -bank[index].release_times_s[0],
            -index,
        ),
    )
    chosen = [first]
    current_union = merge_intervals(strict[first]["intervals_s"])
    current_measure = interval_measure(current_union)
    while len(chosen) < 3:
        options = []
        for index in range(len(bank)):
            if index in chosen or not releases_compatible([bank[i] for i in chosen + [index]]):
                continue
            candidate_union = merge_intervals([
                *current_union,
                *strict[index]["intervals_s"],
            ])
            gain = interval_measure(candidate_union) - current_measure
            options.append((
                gain,
                interval_measure(candidate_union),
                float(strict[index]["effective_duration_s"]),
                -bank[index].release_times_s[0],
                -index,
                index,
                candidate_union,
            ))
        if not options:
            raise PilotError("Q3_PILOT_UNDERPOWERED", "C1 could not form a feasible triple")
        selected = max(options, key=lambda item: item[:-1])
        chosen.append(selected[-2])
        current_union = selected[-1]
        current_measure = interval_measure(current_union)
    return triple_from_singles([bank[index] for index in chosen], "C1_strict_marginal_greedy", 0)


def synergy_diagnostics(x: Decision, settings: dict, mesh: SurfaceMesh) -> dict:
    joint = solve_intervals(x, settings, mesh=mesh)
    individuals = [solve_intervals(x, settings, cloud_indices=(k,), mesh=mesh) for k in range(3)]
    union = merge_intervals(interval for item in individuals for interval in item["intervals_s"])
    pure = interval_difference(joint["intervals_s"], union)
    return {
        "joint": joint,
        "individuals": individuals,
        "individual_union_intervals_s": union,
        "pure_synergy_intervals_s": pure,
        "pure_synergy_duration_s": interval_measure(pure),
    }


def densified_synergy_diagnostics(
    x: Decision,
    precise: dict,
    mesh: SurfaceMesh,
) -> dict:
    """Densify only precise-positive windows on a strict superset mesh.

    Because every PRECISE surface node is present in DENSIFIED, adding nodes
    can only increase max_P min_k margin and shrink the valid set.  Therefore
    no densified-valid interval can occur outside the corresponding precise
    interval; scanning expanded precise windows is exhaustive for this check.
    """
    pad = DENSIFIED["scan_step_s"]

    def expanded(intervals: Sequence[Sequence[float]]) -> list[list[float]]:
        return [[max(0.0, float(a) - pad), min(arrival_time(), float(b) + pad)] for a, b in intervals]

    joint = solve_intervals(
        x, DENSIFIED, mesh=mesh,
        restrict_windows=expanded(precise["joint"]["intervals_s"]),
    )
    individuals = [
        solve_intervals(
            x, DENSIFIED, cloud_indices=(k,), mesh=mesh,
            restrict_windows=expanded(precise["individuals"][k]["intervals_s"]),
        )
        for k in range(3)
    ]
    union = merge_intervals(interval for item in individuals for interval in item["intervals_s"])
    pure = interval_difference(joint["intervals_s"], union)
    return {
        "joint": joint,
        "individuals": individuals,
        "individual_union_intervals_s": union,
        "pure_synergy_intervals_s": pure,
        "pure_synergy_duration_s": interval_measure(pure),
        "restriction_justification": "densified mesh strictly contains precise mesh, so valid sets can only shrink",
    }


def aggregate(records: list[dict]) -> dict:
    result = {}
    for pool in ("C2", "C2+C3", "C2+C3+C4"):
        chosen = [item for item in records if item["pool"] == pool]
        durations = np.array([item["seed_best_precise_duration_s"] for item in chosen], dtype=float)
        result[pool] = {
            "positive_seed_count": int(np.sum(durations > DURATION_TOL)),
            "seed_best_durations_s": durations.tolist(),
            "seed_best_median_s": float(np.median(durations)),
            "seed_best_best_s": float(np.max(durations)),
            "seed_best_std_s": float(np.std(durations)),
            "logical_proxy_calls": int(sum(item["logical_proxy_calls"] for item in chosen)),
            "screen_calls": int(sum(item["screen_calls"] for item in chosen)),
            "precise_calls": int(sum(item["precise_calls"] for item in chosen)),
            "positive_screen_count": int(sum(item["positive_screen_count"] for item in chosen)),
            "systematic_proxy_reversal": bool(any(item["systematic_proxy_reversal"] for item in chosen)),
            "elapsed_seconds": float(sum(item["elapsed_seconds"] for item in chosen)),
        }
    return result


def role_decision(summary: dict, records: list[dict], densified: list[dict], generation: dict) -> dict:
    baseline = summary["C2+C3"]
    c4 = summary["C2+C3+C4"]
    max_precise_synergy = max((item["precise_synergy_duration_s"] for item in densified), default=0.0)
    max_dense_synergy = max((item["densified_synergy_duration_s"] for item in densified), default=0.0)
    positive = c4["positive_seed_count"] >= 2
    median_noninferior = c4["seed_best_median_s"] >= baseline["seed_best_median_s"] - DURATION_TOL
    strict_improvement = c4["seed_best_best_s"] > baseline["seed_best_best_s"] + DURATION_TOL
    synergy_retained = max_precise_synergy > DURATION_TOL and max_dense_synergy > DURATION_TOL
    generation_failures = [key for key, value in generation.items() if value.get("status") != "pass"]
    proxy_reversal = c4["systematic_proxy_reversal"]
    grid_role_reversal = any(item["grid_role_reversal"] for item in densified)
    no_failures = not generation_failures and not proxy_reversal and not grid_role_reversal
    criteria = {
        "criterion_1_positive_in_at_least_two_seeds": positive,
        "criterion_2_seed_best_median_decline_le_1e-4_s": median_noninferior,
        "criterion_3_strict_best_improvement_or_retained_pure_synergy": strict_improvement or synergy_retained,
        "criterion_4_no_constraint_proxy_or_grid_role_failure": no_failures,
    }
    admitted = all(criteria.values())
    return {
        "decision": "C4_ADMITTED_TO_FORMAL_SEED_POOL" if admitted else "C4_INTERNAL_SYNERGY_VALIDATOR_ONLY",
        "admitted": admitted,
        "criteria": criteria,
        "diagnostics": {
            "duration_tolerance_s": DURATION_TOL,
            "positive_seed_count": c4["positive_seed_count"],
            "baseline_seed_best_median_s": baseline["seed_best_median_s"],
            "c4_pool_seed_best_median_s": c4["seed_best_median_s"],
            "median_change_s": c4["seed_best_median_s"] - baseline["seed_best_median_s"],
            "baseline_best_s": baseline["seed_best_best_s"],
            "c4_pool_best_s": c4["seed_best_best_s"],
            "best_change_s": c4["seed_best_best_s"] - baseline["seed_best_best_s"],
            "maximum_precise_pure_synergy_s": max_precise_synergy,
            "maximum_densified_pure_synergy_s": max_dense_synergy,
            "generation_failures": generation_failures,
            "systematic_proxy_reversal": proxy_reversal,
            "grid_role_reversal": grid_role_reversal,
        },
    }


def report_text(result: dict) -> str:
    rows = []
    for name in ("C2", "C2+C3", "C2+C3+C4"):
        item = result["aggregate"][name]
        rows.append(
            f"| {name} | {item['positive_seed_count']}/3 | "
            f"{item['seed_best_median_s']:.9f} | {item['seed_best_best_s']:.9f} | "
            f"{item['seed_best_std_s']:.3e} | {item['logical_proxy_calls']} | "
            f"{item['screen_calls']} | {item['precise_calls']} |"
        )
    decision = result["admission"]
    checks = "\n".join(
        f"- `{key}`：{'通过' if value else '未通过'}"
        for key, value in decision["criteria"].items()
    )
    return f"""# Q3 C4 准入 pilot

> 内部选择试验证据；绑定 `{SPEC_ID}`，只决定 C4 的种子角色，不是 Q3 正式最优解。

## 公平合同

- 固定种子：`{result['budget']['seeds']}`。
- 三个来源池各自每种子严格使用 96 个代理候选、6 次中精度筛选、2 次高精度复算。
- `C2+C3` 采用 48/48 固定总预算，`C2+C3+C4` 采用 32/32/32 固定总预算；C4 的加入不会扩大昂贵调用预算。
- C4 使用可见圆柱表面的布尔点—时覆盖张量选择三元组，随后与其他来源共用有限线段、`max_P min_k` 和连续区间求值器。
- 运行历史保留 1 次 underpowered 失败和 2 次性能修复中止；这些部分结果全部丢弃，未混入下表。

## 配对结果

| 来源池 | 正值种子 | seed-best 中位数/s | 最佳值/s | 标准差/s | 代理调用 | 筛选调用 | 精算调用 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

## 准入判定

结论：**{decision['decision']}**。

{checks}

关键诊断：中位数变化 `{decision['diagnostics']['median_change_s']:.9f} s`，最佳值变化 `{decision['diagnostics']['best_change_s']:.9f} s`，高精度/加密后最大纯协同时长分别为 `{decision['diagnostics']['maximum_precise_pure_synergy_s']:.9f} s` 与 `{decision['diagnostics']['maximum_densified_pure_synergy_s']:.9f} s`。

## 边界

该 pilot 只支持 C4 在预注册预算下是否值得占用正式种子配额。它不证明连续域全局最优、官方双域完备、离散覆盖等价于连续几何，也不形成正式三弹策略。完整未舍入控制量、全部筛选/精算记录、失败与网格加密诊断保存在 `{result['output_path']}`。
"""


def verify_identities() -> dict[str, str]:
    observed = {
        "official_input_sha256": sha256(ROOT / INPUT_PATH),
        "spec_sha256": sha256(ROOT / SPEC_PATH),
        "q1_model_sha256": sha256(ROOT / Q1_PATH),
        "q2_reselection_sha256": sha256(ROOT / Q2_RESELECTION_PATH),
        "q2_result_sha256": sha256(ROOT / Q2_RESULT_PATH),
    }
    if observed != EXPECTED_HASHES:
        raise PilotError("Q3_IDENTITY_MISMATCH", f"expected={EXPECTED_HASHES}, observed={observed}")
    return observed


def run(output: Path, report: Path) -> dict:
    started = time.perf_counter()
    identities = verify_identities()
    proxy_mesh = surface_mesh(PROXY["n_theta"], PROXY["n_levels"])
    screen_mesh = surface_mesh(SCREEN["n_theta"], SCREEN["n_levels"])
    precise_mesh = surface_mesh(PRECISE["n_theta"], PRECISE["n_levels"])
    dense_mesh = surface_mesh(DENSIFIED["n_theta"], DENSIFIED["n_levels"])
    proxy_times = np.arange(0.0, arrival_time() + 0.5 * PROXY["scan_step_s"], PROXY["scan_step_s"])

    records = []
    generation_records = {}
    for seed in SEEDS:
        print(json.dumps({"stage": "generation", "seed": seed, "status": "started"}), flush=True)
        c2, g2 = generate_c2(seed)
        c3, g3 = generate_c3(seed)
        c4, g4 = generate_c4(seed, proxy_mesh, proxy_times)
        generation_records[str(seed)] = {"C2": g2, "C3": g3, "C4": g4}
        pools = build_pools(c2, c3, c4)
        proxy_cache: dict[tuple[float, ...], dict] = {}
        print(json.dumps({
            "stage": "generation", "seed": seed, "status": "completed",
            "counts": {key: len(value) for key, value in (("C2", c2), ("C3", c3), ("C4", c4))},
        }), flush=True)
        for pool_name, candidates in pools.items():
            print(json.dumps({"stage": "pool", "pool": pool_name, "seed": seed, "status": "started"}), flush=True)
            record = score_pool(
                pool_name, seed, candidates, proxy_mesh, screen_mesh, precise_mesh, proxy_cache,
            )
            records.append(record)
            print(json.dumps({
                "stage": "pool", "pool": pool_name, "seed": seed, "status": "completed",
                "seed_best_precise_duration_s": record["seed_best_precise_duration_s"],
                "elapsed_seconds": record["elapsed_seconds"],
            }), flush=True)

    print(json.dumps({"stage": "baselines", "status": "started"}), flush=True)
    b0 = baseline_b0()
    validate_decision(b0)
    c1 = baseline_c1(b0, proxy_mesh, screen_mesh)
    baseline_results = {
        "B0": {"decision": decision_record(b0), "precise": solve_intervals(b0, PRECISE, mesh=precise_mesh)},
        "C1": {"decision": decision_record(c1), "precise": solve_intervals(c1, PRECISE, mesh=precise_mesh)},
    }
    print(json.dumps({"stage": "baselines", "status": "completed"}), flush=True)

    print(json.dumps({"stage": "c4_synergy_and_densification", "status": "started"}), flush=True)
    densified_records = []
    for record in records:
        if record["pool"] != "C2+C3+C4":
            continue
        precise_objects = record.pop("_precise_objects")
        best = max(precise_objects, key=lambda item: item["precise"]["effective_duration_s"])
        decision = best["decision"]
        precise_synergy = synergy_diagnostics(decision, PRECISE, precise_mesh)
        dense_synergy = densified_synergy_diagnostics(decision, precise_synergy, dense_mesh)
        precise_positive = precise_synergy["joint"]["effective_duration_s"] > DURATION_TOL
        dense_positive = dense_synergy["joint"]["effective_duration_s"] > DURATION_TOL
        precise_synergistic = precise_synergy["pure_synergy_duration_s"] > DURATION_TOL
        dense_synergistic = dense_synergy["pure_synergy_duration_s"] > DURATION_TOL
        densified_records.append({
            "seed": record["seed"],
            "source": decision.source,
            "decision": decision_record(decision),
            "precise_joint_duration_s": precise_synergy["joint"]["effective_duration_s"],
            "densified_joint_duration_s": dense_synergy["joint"]["effective_duration_s"],
            "duration_change_s": dense_synergy["joint"]["effective_duration_s"] - precise_synergy["joint"]["effective_duration_s"],
            "precise_synergy_duration_s": precise_synergy["pure_synergy_duration_s"],
            "densified_synergy_duration_s": dense_synergy["pure_synergy_duration_s"],
            "grid_role_reversal": bool(precise_positive != dense_positive or precise_synergistic != dense_synergistic),
            "precise": precise_synergy,
            "densified": dense_synergy,
        })
    for record in records:
        record.pop("_precise_objects", None)
    print(json.dumps({"stage": "c4_synergy_and_densification", "status": "completed"}), flush=True)

    summary = aggregate(records)
    admission = role_decision(summary, records, densified_records, {
        f"{seed}:{method}": values
        for seed, methods in generation_records.items()
        for method, values in methods.items()
    })
    script_path = ROOT / "src/q3/selection_pilot.py"
    result = {
        "schema_version": "1.0",
        "result_id": "Q3-SPEC-Q3-1.0-C4-ADMISSION-PILOT",
        "claim_id": CLAIM_ID,
        "spec_id": SPEC_ID,
        "status": "ok",
        "purpose": "internal_c4_seed_admission_not_formal_q3_solution",
        "identities": identities,
        "budget": {
            "seeds": SEEDS,
            "proxy_candidates_per_pool_seed": N_PROXY,
            "screen_calls_per_pool_seed": N_SCREEN,
            "precise_calls_per_pool_seed": N_PRECISE,
            "pool_allocations": {"C2": [96, 0, 0], "C2+C3": [48, 48, 0], "C2+C3+C4": [32, 32, 32]},
            "c3_max_proposals": C3_PROPOSALS,
            "c4_tracks": C4_TRACKS,
            "c4_single_candidates_per_track": C4_SINGLES,
            "c4_starters_per_track": C4_STARTERS,
            "proxy": PROXY,
            "screen": SCREEN,
            "precise": PRECISE,
            "densified": DENSIFIED,
        },
        "generation": generation_records,
        "prior_attempts": PRIOR_ATTEMPTS,
        "baselines": baseline_results,
        "records": records,
        "aggregate": summary,
        "c4_synergy_and_densification": densified_records,
        "admission": admission,
        "limitations": [
            "The pilot decides only whether C4 receives formal seed quota under SPEC-Q3-1.0.",
            "Finite surface meshes plus local endpoint refinement are numerical certification, not an analytic continuous-domain proof.",
            "Fixed-total pool allocations compare discovery systems under equal expensive-call budgets; they do not rank isolated candidate families with unlimited generation.",
            "No formal Q3 solver, Excel output, global-optimum claim, or real-deployment claim is produced.",
        ],
        "run_identity": {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "execution_kind": "declared_stochastic_repeated_fixed_seeds",
            "seed_policy": "three_pre_registered_fixed_seeds",
            "repetition_policy": "one paired run over every source pool and all three fixed seeds",
            "variability_policy": "retain every seed-best, zero, failure, proxy reversal, and densification role check",
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "script_sha256": sha256(script_path),
            "elapsed_seconds": time.perf_counter() - started,
            **identities,
        },
        "output_path": output.as_posix(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ready(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result["output_sha256"] = sha256(output)
    report.write_text(report_text(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.output, args.report)
    except PilotError as error:
        print(json.dumps({"status": "fail", "failure_code": error.code, "message": str(error)}, ensure_ascii=False), flush=True)
        return 2
    print(json.dumps({
        "status": result["status"],
        "result_id": result["result_id"],
        "admission": result["admission"]["decision"],
        "output": result["output_path"],
        "elapsed_seconds": result["run_identity"]["elapsed_seconds"],
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
