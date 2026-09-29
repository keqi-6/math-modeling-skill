"""Deterministic Q1 kinematics, geometry, interval solving, and validators.

The implementation is bound to SPEC-Q1-1.0.  The continuous angular
extremum evaluator is the production path; dense sampling and the
critical-angle real-root enumerator are independent internal checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, pi
from typing import Callable

import numpy as np
from numpy.polynomial import polynomial as poly
from scipy.optimize import minimize_scalar


SPEC_IDENTITY = "cdb63ddda18c89311dfa7bd6477437cc8e4fc8a1ea19db33a1f2eeedf478e3bb"
OFFICIAL_INPUT_IDENTITY = "a37f6aad30b16ea09da9cb320ce194b12d3a28874008cf9ff19549f6c6079447"
GEOMETRY_LENGTH_TOL_M = 1e-9
GEOMETRY_TIME_TOL_S = 2e-9
EMPTY_MARGIN_SENTINEL_M = 1e9


class Q1Error(RuntimeError):
    """Observable Q1 failure carrying a frozen failure code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Q1Parameters:
    missile_initial: np.ndarray
    uav_initial: np.ndarray
    target_base_center: np.ndarray
    target_radius: float
    target_height: float
    missile_speed: float
    uav_speed: float
    uav_direction: np.ndarray
    release_time: float
    fuse_delay: float
    gravity: float
    smoke_radius: float
    smoke_sink_speed: float
    smoke_duration: float


def default_parameters() -> Q1Parameters:
    return Q1Parameters(
        missile_initial=np.array([20000.0, 0.0, 2000.0]),
        uav_initial=np.array([17800.0, 0.0, 1800.0]),
        target_base_center=np.array([0.0, 200.0, 0.0]),
        target_radius=7.0,
        target_height=10.0,
        missile_speed=300.0,
        uav_speed=120.0,
        uav_direction=np.array([-1.0, 0.0, 0.0]),
        release_time=1.5,
        fuse_delay=3.6,
        gravity=9.8,
        smoke_radius=10.0,
        smoke_sink_speed=3.0,
        smoke_duration=20.0,
    )


def validate_parameters(p: Q1Parameters) -> None:
    vectors = {
        "missile_initial": p.missile_initial,
        "uav_initial": p.uav_initial,
        "target_base_center": p.target_base_center,
        "uav_direction": p.uav_direction,
    }
    for name, value in vectors.items():
        array = np.asarray(value, dtype=np.float64)
        if array.shape != (3,) or not np.all(np.isfinite(array)):
            raise Q1Error("Q1_INVALID_INPUT", f"{name} must be a finite float64 vector of length 3")
    scalars = {
        "target_radius": p.target_radius,
        "target_height": p.target_height,
        "missile_speed": p.missile_speed,
        "uav_speed": p.uav_speed,
        "release_time": p.release_time,
        "fuse_delay": p.fuse_delay,
        "gravity": p.gravity,
        "smoke_radius": p.smoke_radius,
        "smoke_sink_speed": p.smoke_sink_speed,
        "smoke_duration": p.smoke_duration,
    }
    if any(not np.isfinite(float(value)) for value in scalars.values()):
        raise Q1Error("Q1_INVALID_INPUT", "all scalar parameters must be finite")
    if np.linalg.norm(p.missile_initial) <= 0.0:
        raise Q1Error("Q1_INVALID_INPUT", "missile_initial must have positive norm")
    if p.uav_initial[2] < 0.0 or p.target_base_center[2] != 0.0:
        raise Q1Error("Q1_INVALID_INPUT", "initial heights or target base are invalid")
    if p.target_radius <= 0.0 or p.target_height <= 0.0:
        raise Q1Error("Q1_INVALID_INPUT", "target dimensions must be positive")
    if p.missile_speed <= 0.0 or not 70.0 <= p.uav_speed <= 140.0:
        raise Q1Error("Q1_INVALID_INPUT", "speeds are outside their domains")
    if p.release_time < 0.0 or p.fuse_delay < 0.0:
        raise Q1Error("Q1_INVALID_INPUT", "event times must be nonnegative")
    if p.gravity <= 0.0 or p.smoke_radius <= 0.0 or p.smoke_duration <= 0.0:
        raise Q1Error("Q1_INVALID_INPUT", "physical scales must be positive")
    if p.smoke_sink_speed < 0.0:
        raise Q1Error("Q1_INVALID_INPUT", "smoke sink speed must be nonnegative")
    if abs(np.linalg.norm(p.uav_direction) - 1.0) > 1e-12 or abs(p.uav_direction[2]) > 1e-12:
        raise Q1Error("Q1_INVALID_INPUT", "uav_direction must be a horizontal unit vector")


def kinematics(p: Q1Parameters) -> dict[str, np.ndarray | float | list[float]]:
    validate_parameters(p)
    release = p.uav_initial + p.uav_speed * p.release_time * p.uav_direction
    explosion_time = p.release_time + p.fuse_delay
    explosion = (
        p.uav_initial
        + p.uav_speed * explosion_time * p.uav_direction
        - np.array([0.0, 0.0, 0.5 * p.gravity * p.fuse_delay**2])
    )
    if explosion[2] < 0.0:
        raise Q1Error("Q1_INFEASIBLE_EXPLOSION", "explosion height is below ground")
    missile_arrival = np.linalg.norm(p.missile_initial) / p.missile_speed
    stop = min(explosion_time + p.smoke_duration, missile_arrival)
    return {
        "release_point_m": release,
        "explosion_time_s": explosion_time,
        "explosion_point_m": explosion,
        "missile_arrival_time_s": missile_arrival,
        "active_window_s": [explosion_time, stop],
    }


def missile_position(t: float, p: Q1Parameters) -> np.ndarray:
    direction = p.missile_initial / np.linalg.norm(p.missile_initial)
    return p.missile_initial - p.missile_speed * float(t) * direction


def smoke_center(t: float, p: Q1Parameters) -> np.ndarray:
    info = kinematics(p)
    te = float(info["explosion_time_s"])
    explosion = np.asarray(info["explosion_point_m"], dtype=np.float64)
    return explosion - np.array([0.0, 0.0, p.smoke_sink_speed * (float(t) - te)])


def geometry_possible_window(p: Q1Parameters) -> dict[str, object]:
    """Return a conservative time window in which full concealment is possible.

    Full-cylinder concealment implies that the smoke sphere intersects at least
    one missile-target segment.  Every such segment stays inside a simple
    coordinate box.  Comparing the analytic missile and cloud coordinates with
    that box yields necessary (never sufficient) bounds.  The radius is expanded
    and the right endpoint is shifted outward so floating-point roundoff can only
    reduce pruning, never create a false negative.
    """
    info = kinematics(p)
    active_start, active_stop = map(float, info["active_window_s"])
    explosion = np.asarray(info["explosion_point_m"], dtype=np.float64)
    radius = float(p.smoke_radius + GEOMETRY_LENGTH_TOL_M)
    missile_direction = p.missile_initial / np.linalg.norm(p.missile_initial)
    missile_velocity = p.missile_speed * missile_direction

    target_x_min = float(p.target_base_center[0] - p.target_radius)
    target_y_min = float(p.target_base_center[1] - p.target_radius)
    target_y_max = float(p.target_base_center[1] + p.target_radius)
    segment_x_min = min(target_x_min, 0.0, float(p.missile_initial[0]))
    segment_y_min = min(target_y_min, 0.0, float(p.missile_initial[1]))
    segment_y_max = max(target_y_max, 0.0, float(p.missile_initial[1]))

    reasons: list[str] = []
    if float(explosion[0]) < segment_x_min - radius:
        reasons.append("x_below_segment_box")
    if not segment_y_min - radius <= float(explosion[1]) <= segment_y_max + radius:
        reasons.append("y_outside_segment_box")

    upper_bounds = {"active_stop_s": active_stop}
    missile_x_speed = float(missile_velocity[0])
    if missile_x_speed > 0.0:
        upper_bounds["candidate_x_cap_s"] = (
            float(p.missile_initial[0]) + radius - float(explosion[0])
        ) / missile_x_speed
    vertical_relative_speed = float(missile_velocity[2]) - p.smoke_sink_speed
    if vertical_relative_speed > 0.0:
        upper_bounds["candidate_z_upper_cap_s"] = (
            float(p.missile_initial[2]) + radius - float(explosion[2])
            - p.smoke_sink_speed * active_start
        ) / vertical_relative_speed
    if p.smoke_sink_speed > 0.0:
        upper_bounds["candidate_z_lower_cap_s"] = (
            active_start
            + (float(explosion[2]) - float(p.target_base_center[2]) + radius)
            / p.smoke_sink_speed
        )

    right = float(min(upper_bounds.values()))
    if right < active_start - GEOMETRY_TIME_TOL_S:
        reasons.append("upper_bound_before_explosion")
    possible = None if reasons else [
        active_start,
        min(active_stop, max(active_start, right + GEOMETRY_TIME_TOL_S)),
    ]
    active_span = max(0.0, active_stop - active_start)
    possible_span = 0.0 if possible is None else max(0.0, possible[1] - possible[0])
    return {
        "role": "safe_necessary_precheck_only",
        "active_window_s": [active_start, active_stop],
        "possible_window_s": possible,
        "upper_bounds_s": {key: float(value) for key, value in upper_bounds.items()},
        "length_expansion_m": GEOMETRY_LENGTH_TOL_M,
        "time_expansion_s": GEOMETRY_TIME_TOL_S,
        "active_span_s": active_span,
        "possible_span_s": possible_span,
        "pruned_fraction": 0.0 if active_span == 0.0 else 1.0 - possible_span / active_span,
        "pruned": possible is None,
        "reasons": reasons,
    }


def target_circle(theta: np.ndarray, z: float, p: Q1Parameters) -> np.ndarray:
    theta = np.asarray(theta, dtype=np.float64)
    return np.column_stack(
        (
            p.target_base_center[0] + p.target_radius * np.cos(theta),
            p.target_base_center[1] + p.target_radius * np.sin(theta),
            np.full(theta.shape, z, dtype=np.float64),
        )
    )


def segment_distance(
    cloud: np.ndarray, missile: np.ndarray, points: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    points = np.asarray(points, dtype=np.float64)
    vectors = points - missile
    denominators = np.einsum("ij,ij->i", vectors, vectors)
    if np.any(denominators <= 0.0):
        raise Q1Error("Q1_GEOMETRY_NONFINITE", "degenerate missile-target segment")
    raw_lambda = np.einsum("j,ij->i", cloud - missile, vectors) / denominators
    clipped = np.clip(raw_lambda, 0.0, 1.0)
    closest = missile + clipped[:, None] * vectors
    distances = np.linalg.norm(cloud - closest, axis=1)
    if not np.all(np.isfinite(distances)):
        raise Q1Error("Q1_GEOMETRY_NONFINITE", "non-finite segment distance")
    return distances, raw_lambda


def circle_margins(theta: np.ndarray, t: float, z: float, p: Q1Parameters) -> tuple[np.ndarray, np.ndarray]:
    points = target_circle(np.mod(theta, 2.0 * pi), z, p)
    distances, lambdas = segment_distance(smoke_center(t, p), missile_position(t, p), points)
    return distances - p.smoke_radius, lambdas


def _scalar_margin(theta: float, t: float, z: float, p: Q1Parameters) -> float:
    values, _ = circle_margins(np.array([theta]), t, z, p)
    return float(values[0])


def continuous_circle_max(t: float, z: float, p: Q1Parameters, n_theta: int = 4096) -> dict[str, float]:
    if n_theta < 32:
        raise Q1Error("Q1_INVALID_INPUT", "angular grid is too small")
    theta = np.arange(n_theta, dtype=np.float64) * (2.0 * pi / n_theta)
    values, lambdas = circle_margins(theta, t, z, p)
    previous = np.roll(values, 1)
    following = np.roll(values, -1)
    # Use one-sided strictness so a flat-topped local maximum contributes only
    # one candidate.  When the finite-segment projection clips to the missile
    # endpoint the whole circle can be exactly flat; in that case every angle
    # is already a maximizer and continuous angular refinement is unnecessary.
    local = np.flatnonzero((values >= previous) & (values > following))
    if local.size == 0:
        if float(np.ptp(values)) <= 1e-12:
            index = int(np.argmax(values))
            return {
                "margin_m": float(values[index]),
                "theta_rad": float(theta[index]),
                "lambda_raw": float(lambdas[index]),
                "z_m": float(z),
            }
        raise Q1Error("Q1_ANGULAR_NONCONVERGENCE", "no periodic maximum candidate found")
    step = 2.0 * pi / n_theta
    candidates: list[tuple[float, float]] = [
        (float(values[index]), float(theta[index])) for index in local
    ]
    for index in local:
        center = float(theta[index])
        result = minimize_scalar(
            lambda angle: -_scalar_margin(angle, t, z, p),
            bounds=(center - step, center + step),
            method="bounded",
            options={"xatol": 1e-12, "maxiter": 200},
        )
        if not result.success or not np.isfinite(result.fun):
            raise Q1Error("Q1_ANGULAR_NONCONVERGENCE", "bounded angular refinement failed")
        candidates.append((-float(result.fun), float(result.x % (2.0 * pi))))
    value, angle = max(candidates, key=lambda item: item[0])
    _, refined_lambda = circle_margins(np.array([angle]), t, z, p)
    return {"margin_m": value, "theta_rad": angle, "lambda_raw": float(refined_lambda[0]), "z_m": float(z)}


def primary_margin(t: float, p: Q1Parameters, n_theta: int = 4096) -> dict[str, float]:
    info = kinematics(p)
    start, stop = (float(value) for value in info["active_window_s"])
    if t < start or t > stop:
        return {"margin_m": float("inf"), "theta_rad": float("nan"), "lambda_raw": float("nan"), "z_m": float("nan")}
    bottom = continuous_circle_max(t, p.target_base_center[2], p, n_theta)
    top = continuous_circle_max(t, p.target_base_center[2] + p.target_height, p, n_theta)
    return bottom if bottom["margin_m"] >= top["margin_m"] else top


def dense_margin(t: float, p: Q1Parameters, n_theta: int = 131072) -> dict[str, float]:
    theta = np.arange(n_theta, dtype=np.float64) * (2.0 * pi / n_theta)
    candidates: list[dict[str, float]] = []
    for z in (p.target_base_center[2], p.target_base_center[2] + p.target_height):
        values, lambdas = circle_margins(theta, t, z, p)
        index = int(np.argmax(values))
        candidates.append({
            "margin_m": float(values[index]),
            "theta_rad": float(theta[index]),
            "lambda_raw": float(lambdas[index]),
            "z_m": float(z),
        })
    return max(candidates, key=lambda item: item["margin_m"])


def full_surface_margin(
    t: float,
    p: Q1Parameters,
    n_theta: int = 512,
    n_levels: int = 17,
) -> dict[str, float | int | str]:
    """Conservative full-cylinder mesh evaluator for arbitrary controls.

    ``primary_margin`` is the continuously refined end-ring evaluator verified
    for the fixed Q1 geometry.  Its end-ring dominance is not assumed for an
    arbitrary optimized Q2/Q3 trajectory.  This separate interface samples
    the complete side and both caps, making that reuse boundary explicit.
    Q3 keeps its stronger visible-surface evaluator and does not call this
    routine.
    """
    if n_theta < 32 or n_levels < 3:
        raise Q1Error("Q1_INVALID_INPUT", "full-surface mesh is too small")
    info = kinematics(p)
    start, stop = (float(value) for value in info["active_window_s"])
    if t < start or t > stop:
        return {
            "margin_m": float("inf"), "theta_rad": float("nan"),
            "lambda_raw": float("nan"), "z_m": float("nan"),
            "surface_kind": "inactive", "surface_point_count": 0,
        }
    theta = np.arange(n_theta, dtype=np.float64) * (2.0 * pi / n_theta)
    center = p.target_base_center

    side_z = np.linspace(center[2], center[2] + p.target_height, n_levels)
    side_theta = np.tile(theta, n_levels)
    side_points = np.column_stack((
        center[0] + p.target_radius * np.cos(side_theta),
        center[1] + p.target_radius * np.sin(side_theta),
        np.repeat(side_z, n_theta),
    ))

    radial = np.linspace(0.0, p.target_radius, n_levels)
    cap_theta = np.tile(theta, n_levels - 1)
    cap_radius = np.repeat(radial[1:], n_theta)
    cap_xy = np.column_stack((
        center[0] + cap_radius * np.cos(cap_theta),
        center[1] + cap_radius * np.sin(cap_theta),
    ))
    cap_xy = np.vstack((center[:2], cap_xy))
    bottom = np.column_stack((cap_xy, np.full(len(cap_xy), center[2])))
    top = np.column_stack((cap_xy, np.full(len(cap_xy), center[2] + p.target_height)))
    points = np.vstack((side_points, bottom, top))
    distances, lambdas = segment_distance(smoke_center(t, p), missile_position(t, p), points)
    margins = distances - p.smoke_radius
    index = int(np.argmax(margins))
    if index < len(side_points):
        surface_kind = "side"
    elif index < len(side_points) + len(bottom):
        surface_kind = "bottom_cap"
    else:
        surface_kind = "top_cap"
    point = points[index]
    return {
        "margin_m": float(margins[index]),
        "theta_rad": float(atan2(point[1] - center[1], point[0] - center[0]) % (2.0 * pi)),
        "lambda_raw": float(lambdas[index]),
        "z_m": float(point[2]),
        "surface_kind": surface_kind,
        "surface_point_count": int(len(points)),
    }


def _real_polynomial_roots(coefficients: np.ndarray, tolerance: float = 1e-8) -> list[float]:
    coefficients = np.asarray(coefficients, dtype=np.float64)
    while coefficients.size > 1 and abs(coefficients[-1]) <= 1e-13 * max(1.0, np.max(np.abs(coefficients))):
        coefficients = coefficients[:-1]
    if coefficients.size <= 1:
        return []
    roots = np.roots(coefficients[::-1])
    return [float(root.real) for root in roots if abs(root.imag) <= tolerance * max(1.0, abs(root.real))]


def _trig_linear_numerator(constant: float, cosine: float, sine: float) -> np.ndarray:
    # (constant + cosine*cos(theta) + sine*sin(theta))*(1+u^2), u=tan(theta/2)
    return np.array([constant + cosine, 2.0 * sine, constant - cosine], dtype=np.float64)


def analytic_circle_max(t: float, z: float, p: Q1Parameters) -> dict[str, float | int]:
    """Enumerate stationary and finite-segment branch angles via real roots."""
    missile = missile_position(t, p)
    cloud = smoke_center(t, p)
    center = np.array([p.target_base_center[0], p.target_base_center[1], z], dtype=np.float64)
    base = center - missile
    cloud_from_missile = cloud - missile
    radius = p.target_radius

    a0 = float(np.dot(cloud_from_missile, base))
    ax = float(radius * cloud_from_missile[0])
    ay = float(radius * cloud_from_missile[1])
    b0 = float(np.dot(base, base) + radius**2)
    bx = float(2.0 * radius * base[0])
    by = float(2.0 * radius * base[1])

    a = _trig_linear_numerator(a0, ax, ay)
    b = _trig_linear_numerator(b0, bx, by)
    a_prime = np.array([ay, -2.0 * ax, -ay], dtype=np.float64)
    b_prime = np.array([by, -2.0 * bx, -by], dtype=np.float64)
    interior_stationary = poly.polysub(2.0 * poly.polymul(a_prime, b), poly.polymul(a, b_prime))

    # lambda=0, lambda=1 branch switches and stationary points of ||C-P||.
    branch_zero = a
    branch_one = poly.polysub(a, b)
    center_from_cloud = center - cloud
    endpoint_stationary = _trig_linear_numerator(0.0, float(center_from_cloud[1]), float(-center_from_cloud[0]))

    angles = [0.0, pi]
    for coefficients in (interior_stationary, branch_zero, branch_one, endpoint_stationary):
        angles.extend((2.0 * np.arctan(root)) % (2.0 * pi) for root in _real_polynomial_roots(coefficients))
    angles = sorted({round(float(angle % (2.0 * pi)), 13) for angle in angles})
    theta = np.asarray(angles, dtype=np.float64)
    values, lambdas = circle_margins(theta, t, z, p)
    index = int(np.argmax(values))
    return {
        "margin_m": float(values[index]),
        "theta_rad": float(theta[index]),
        "lambda_raw": float(lambdas[index]),
        "z_m": float(z),
        "candidate_count": len(angles),
    }


def analytic_margin(t: float, p: Q1Parameters) -> dict[str, float | int]:
    bottom = analytic_circle_max(t, p.target_base_center[2], p)
    top = analytic_circle_max(t, p.target_base_center[2] + p.target_height, p)
    return bottom if float(bottom["margin_m"]) >= float(top["margin_m"]) else top


def _refine_root(
    function: Callable[[float], float], left: float, right: float,
    time_tolerance: float = 1e-9, margin_tolerance: float = 1e-7,
) -> tuple[float, float, int]:
    f_left = float(function(left))
    f_right = float(function(right))
    if not np.isfinite(f_left) or not np.isfinite(f_right) or f_left * f_right > 0.0:
        raise Q1Error("Q1_TIME_ROOT_UNRESOLVED", "root is not bracketed")
    midpoint = 0.5 * (left + right)
    f_mid = float(function(midpoint))
    for iteration in range(1, 101):
        midpoint = 0.5 * (left + right)
        f_mid = float(function(midpoint))
        if not np.isfinite(f_mid):
            raise Q1Error("Q1_TIME_ROOT_UNRESOLVED", "non-finite root residual")
        if right - left <= time_tolerance and abs(f_mid) <= margin_tolerance:
            return midpoint, f_mid, iteration
        if f_left == 0.0:
            return left, f_left, iteration
        if f_right == 0.0:
            return right, f_right, iteration
        if f_left * f_mid <= 0.0:
            right, f_right = midpoint, f_mid
        else:
            left, f_left = midpoint, f_mid
    raise Q1Error("Q1_TIME_ROOT_UNRESOLVED", "root failed the joint time/residual tolerance")


def recover_unsampled_intervals(
    times: np.ndarray,
    margins: np.ndarray,
    function: Callable[[float], float],
    *,
    time_tolerance: float = 1e-9,
    margin_tolerance: float = 1e-7,
    maximum_gap: float | None = None,
) -> dict[str, object]:
    """Recover negative excursions whose sampled endpoints stay positive.

    A sign-change scan cannot see a short interval when both adjacent samples
    are outside.  SPEC-Q1-1.0 therefore requires every positive discrete local
    minimum to be bracketed by three samples and minimized continuously.  The
    returned intervals are additional to the ordinary sampled-inside blocks.

    ``maximum_gap`` lets callers with piecewise time grids avoid minimizing
    across inactive-window or event discontinuities.
    """
    times = np.asarray(times, dtype=np.float64)
    margins = np.asarray(margins, dtype=np.float64)
    if times.ndim != 1 or margins.shape != times.shape or times.size < 3:
        raise Q1Error("Q1_INVALID_INPUT", "time scan must contain matching one-dimensional arrays")
    if np.any(~np.isfinite(times)) or np.any(np.diff(times) <= 0.0):
        raise Q1Error("Q1_INVALID_INPUT", "time scan must be finite and strictly increasing")

    recovered: list[list[float]] = []
    records: list[dict[str, float | int]] = []
    checks = 0
    for index in range(1, times.size - 1):
        left_gap = float(times[index] - times[index - 1])
        right_gap = float(times[index + 1] - times[index])
        if maximum_gap is not None and max(left_gap, right_gap) > maximum_gap:
            continue
        left_value, center_value, right_value = (
            float(margins[index - 1]), float(margins[index]), float(margins[index + 1])
        )
        if not all(np.isfinite(value) for value in (left_value, center_value, right_value)):
            continue
        is_local_minimum = (
            center_value > 0.0
            and center_value <= left_value
            and center_value <= right_value
            and (center_value < left_value or center_value < right_value)
        )
        if not is_local_minimum:
            continue
        checks += 1
        left, right = float(times[index - 1]), float(times[index + 1])
        result = minimize_scalar(
            function,
            bounds=(left, right),
            method="bounded",
            options={"xatol": time_tolerance, "maxiter": 200},
        )
        if not result.success or not np.isfinite(result.fun):
            raise Q1Error("Q1_TIME_ROOT_UNRESOLVED", "local time minimum refinement failed")
        minimum_time = float(result.x)
        minimum_margin = float(function(minimum_time))
        if minimum_margin > 0.0:
            continue
        # A boundary minimum belongs to an adjacent sampled block/event and is
        # not an unsampled excursion owned by this three-point bracket.
        if minimum_time - left <= time_tolerance or right - minimum_time <= time_tolerance:
            continue
        if minimum_margin == 0.0:
            entry = exit_time = minimum_time
            entry_residual = exit_residual = minimum_margin
            entry_iterations = exit_iterations = 0
        else:
            entry, entry_residual, entry_iterations = _refine_root(
                function, left, minimum_time, time_tolerance, margin_tolerance
            )
            exit_time, exit_residual, exit_iterations = _refine_root(
                function, minimum_time, right, time_tolerance, margin_tolerance
            )
        recovered.append([entry, exit_time])
        records.append({
            "scan_index": int(index),
            "minimum_time_s": minimum_time,
            "minimum_margin_m": minimum_margin,
            "entry_time_s": entry,
            "entry_margin_m": entry_residual,
            "entry_iterations": int(entry_iterations),
            "exit_time_s": exit_time,
            "exit_margin_m": exit_residual,
            "exit_iterations": int(exit_iterations),
        })
    return {
        "checked_local_minima": checks,
        "recovered_intervals_s": recovered,
        "records": records,
    }


def _scan_values(
    p: Q1Parameters,
    scan_step: float,
    n_theta: int,
    progress: Callable[[int, int], None] | None = None,
    margin_evaluator: Callable[[float], float] | None = None,
    time_window_s: list[float] | tuple[float, float] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    active_start, active_stop = (float(value) for value in kinematics(p)["active_window_s"])
    start, stop = (
        (active_start, active_stop)
        if time_window_s is None else tuple(float(value) for value in time_window_s)
    )
    if start < active_start - GEOMETRY_TIME_TOL_S or stop > active_stop + GEOMETRY_TIME_TOL_S or stop < start:
        raise Q1Error("Q1_INVALID_INPUT", "time window must lie inside the active window")
    count = max(1, int(ceil((stop - start) / scan_step)))
    times = np.linspace(start, stop, count + 1, dtype=np.float64)
    margins = np.empty(times.size, dtype=np.float64)
    evaluator = (
        (lambda time: float(primary_margin(float(time), p, n_theta)["margin_m"]))
        if margin_evaluator is None else margin_evaluator
    )
    for index, time in enumerate(times):
        margins[index] = float(evaluator(float(time)))
        completed = index + 1
        if progress is not None and (completed == times.size or completed % 5000 == 0):
            progress(completed, int(times.size))
    return times, margins


def solve_intervals(
    p: Q1Parameters,
    scan_step: float = 1e-3,
    n_theta: int = 4096,
    progress: Callable[[int, int], None] | None = None,
    margin_evaluator: Callable[[float], float] | None = None,
    geometry_scope: str = "q1_fixed_geometry_end_rings",
    geometry_pruning: bool = True,
) -> dict[str, object]:
    if margin_evaluator is not None and geometry_scope == "q1_fixed_geometry_end_rings":
        raise Q1Error(
            "Q1_INVALID_INPUT",
            "a custom margin evaluator must declare its non-Q1 geometry scope",
        )
    pruning = geometry_possible_window(p)
    time_window = pruning["possible_window_s"] if geometry_pruning else pruning["active_window_s"]
    if time_window is None or float(time_window[1]) - float(time_window[0]) <= GEOMETRY_TIME_TOL_S:
        return {
            "scan_step_s": scan_step,
            "geometry_scope": geometry_scope,
            "scan_count": 0,
            "intervals_s": [],
            "effective_duration_s": 0.0,
            "root_residuals": [],
            "minimum_scan_margin_m": EMPTY_MARGIN_SENTINEL_M,
            "local_minimum_checks": 0,
            "recovered_unsampled_interval_count": 0,
            "local_minimum_records": [],
            "geometry_pruning": {**pruning, "enabled": bool(geometry_pruning)},
        }
    times, margins = _scan_values(
        p, scan_step, n_theta, progress=progress, margin_evaluator=margin_evaluator,
        time_window_s=time_window,
    )
    inside = margins <= 0.0
    blocks: list[tuple[int, int]] = []
    index = 0
    while index < inside.size:
        if not inside[index]:
            index += 1
            continue
        start_index = index
        while index + 1 < inside.size and inside[index + 1]:
            index += 1
        blocks.append((start_index, index))
        index += 1

    function = (
        (lambda time: float(primary_margin(float(time), p, n_theta)["margin_m"]))
        if margin_evaluator is None else margin_evaluator
    )
    intervals: list[list[float]] = []
    residuals: list[dict[str, float | int | str]] = []
    for start_index, end_index in blocks:
        if start_index == 0:
            start_time = float(times[0])
            start_residual = float(margins[0])
            start_iterations = 0
        else:
            start_time, start_residual, start_iterations = _refine_root(
                function, float(times[start_index - 1]), float(times[start_index])
            )
        if end_index == times.size - 1:
            end_time = float(times[-1])
            end_residual = float(margins[-1])
            end_iterations = 0
        else:
            end_time, end_residual, end_iterations = _refine_root(
                function, float(times[end_index]), float(times[end_index + 1])
            )
        intervals.append([start_time, end_time])
        residuals.extend([
            {"kind": "entry", "time_s": start_time, "margin_m": start_residual, "iterations": start_iterations},
            {"kind": "exit", "time_s": end_time, "margin_m": end_residual, "iterations": end_iterations},
        ])

    tangencies = recover_unsampled_intervals(
        times,
        margins,
        function,
        time_tolerance=1e-9,
        margin_tolerance=1e-7,
        maximum_gap=scan_step * (1.0 + 1e-6),
    )
    intervals.extend(tangencies["recovered_intervals_s"])
    for item in tangencies["records"]:
        residuals.extend([
            {
                "kind": "entry_from_local_minimum",
                "time_s": item["entry_time_s"],
                "margin_m": item["entry_margin_m"],
                "iterations": item["entry_iterations"],
            },
            {
                "kind": "exit_from_local_minimum",
                "time_s": item["exit_time_s"],
                "margin_m": item["exit_margin_m"],
                "iterations": item["exit_iterations"],
            },
        ])

    merged: list[list[float]] = []
    for interval in intervals:
        if not merged or interval[0] - merged[-1][1] > 2e-9:
            merged.append(interval)
        else:
            merged[-1][1] = max(merged[-1][1], interval[1])
    duration = float(sum(right - left for left, right in merged))
    return {
        "scan_step_s": scan_step,
        "geometry_scope": geometry_scope,
        "scan_count": int(times.size),
        "intervals_s": merged,
        "effective_duration_s": duration,
        "root_residuals": residuals,
        "minimum_scan_margin_m": float(np.min(margins)),
        "local_minimum_checks": tangencies["checked_local_minima"],
        "recovered_unsampled_interval_count": len(tangencies["recovered_intervals_s"]),
        "local_minimum_records": tangencies["records"],
        "geometry_pruning": {**pruning, "enabled": bool(geometry_pruning)},
    }


def center_point_intervals(p: Q1Parameters, scan_step: float = 1e-3) -> dict[str, object]:
    center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    start, stop = (float(value) for value in kinematics(p)["active_window_s"])
    count = int(round((stop - start) / scan_step))
    times = np.linspace(start, stop, count + 1, dtype=np.float64)

    def margin(time: float) -> float:
        distance, _ = segment_distance(
            smoke_center(time, p), missile_position(time, p), center.reshape(1, 3)
        )
        return float(distance[0] - p.smoke_radius)

    values = np.asarray([margin(float(time)) for time in times])
    inside = values <= 0.0
    indices = np.flatnonzero(inside)
    if indices.size == 0:
        return {"intervals_s": [], "effective_duration_s": 0.0, "diagnostic_only": True}
    first, last = int(indices[0]), int(indices[-1])
    left = float(times[0]) if first == 0 else _refine_root(margin, float(times[first - 1]), float(times[first]))[0]
    right = float(times[-1]) if last == times.size - 1 else _refine_root(margin, float(times[last]), float(times[last + 1]))[0]
    return {"intervals_s": [[left, right]], "effective_duration_s": right - left, "diagnostic_only": True}


def geometry_cross_validation(times: list[float], p: Q1Parameters) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for time in times:
        primary = primary_margin(time, p, 4096)
        refined = primary_margin(time, p, 8192)
        dense = dense_margin(time, p, 131072)
        analytic = analytic_margin(time, p)
        records.append({
            "time_s": time,
            "primary_4096": primary,
            "primary_8192": refined,
            "dense_131072": dense,
            "analytic_roots": analytic,
            "abs_primary_refined_m": abs(primary["margin_m"] - refined["margin_m"]),
            "abs_primary_dense_m": abs(primary["margin_m"] - dense["margin_m"]),
            "abs_primary_analytic_m": abs(primary["margin_m"] - float(analytic["margin_m"])),
        })
    return records


def internal_checks(p: Q1Parameters) -> dict[str, object]:
    info = kinematics(p)
    checks: dict[str, bool] = {
        "release_point": bool(np.allclose(info["release_point_m"], [17620.0, 0.0, 1800.0], atol=1e-9, rtol=0.0)),
        "explosion_time": abs(float(info["explosion_time_s"]) - 5.1) <= 1e-12,
        "explosion_point": bool(np.allclose(info["explosion_point_m"], [17188.0, 0.0, 1736.496], atol=1e-9, rtol=0.0)),
        "active_window": bool(np.allclose(info["active_window_s"], [5.1, 25.1], atol=1e-12, rtol=0.0)),
    }
    cloud = np.array([0.0, 0.0, 0.0])
    missile = np.array([1.0, 0.0, 0.0])
    points = np.array([[2.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
    distances, raw = segment_distance(cloud, missile, points)
    checks["segment_clipping"] = bool(np.allclose(distances, [1.0, 0.0]) and np.allclose(raw, [-1.0, 1.0]))
    larger = Q1Parameters(**{**p.__dict__, "smoke_radius": p.smoke_radius + 1.0})
    checks["parameter_response"] = abs(
        (primary_margin(8.0, larger)["margin_m"] - primary_margin(8.0, p)["margin_m"]) + 1.0
    ) <= 1e-10
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise Q1Error("Q1_HIDDEN_CONSTANT", "internal checks failed: " + ",".join(failed))
    return {"status": "pass", "checks": checks}
