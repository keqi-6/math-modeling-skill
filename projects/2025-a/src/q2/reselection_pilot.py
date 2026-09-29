"""Fair C2-seed versus analytic-feasible C3-I seed pilot for Q2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.special import expit
from scipy.stats import qmc

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
import model as q1  # noqa: E402

INPUT_PATH = Path("data/A题.pdf")
GEOMETRY_PATH = Path("planning/12_q2_c3_geometry_and_candidate_reselection.md")
SPEC_PATH = Path("planning/13_q2_reselection_pilot_spec.md")
INPUT_SHA = "a37f6aad30b16ea09da9cb320ce194b12d3a28874008cf9ff19549f6c6079447"
GEOMETRY_SHA = "210f5fc5ccb99dc8bba7877265f0da7762efca0614bc5ffe540d08bbdb397eaf"
SPEC_SHA = "dfe33fbda5cbc4203730e2f6bc26aa972e42711fd571c42b2cf2904553f331c3"

SEEDS = [250827, 250828, 250829]
N_PROXY, N_SCREEN, N_PRECISE = 128, 8, 2
C3_BANK_SIZE = 2048
HALF_WIDTH = 0.18
PROXY = {"time_count": 41, "n_theta": 64, "n_levels": 9, "logistic_scale_m": 2.0}
SCREEN = {"scan_step_s": 0.02, "n_theta": 128, "n_levels": 17}
PRECISE = {"scan_step_s": 0.005, "n_theta": 512, "n_levels": 33}
TOL = 1e-10


class PilotError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Decision:
    heading_rad: float
    speed_mps: float
    release_time_s: float
    fuse_delay_s: float
    source_domain: str


@dataclass(frozen=True)
class Candidate:
    decision: Decision
    generation: dict


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


def arrival(p: q1.Q1Parameters) -> float:
    return float(np.linalg.norm(p.missile_initial) / p.missile_speed)


def parameters(x: Decision) -> q1.Q1Parameters:
    p = q1.default_parameters()
    direction = np.array([math.cos(x.heading_rad), math.sin(x.heading_rad), 0.0])
    return replace(
        p,
        uav_speed=x.speed_mps,
        uav_direction=direction,
        release_time=x.release_time_s,
        fuse_delay=x.fuse_delay_s,
    )


def decision_record(x: Decision) -> dict:
    p = parameters(x)
    info = q1.kinematics(p)
    return {
        **asdict(x),
        "heading_unit": p.uav_direction.tolist(),
        "release_point_m": ready(info["release_point_m"]),
        "explosion_time_s": float(info["explosion_time_s"]),
        "explosion_point_m": ready(info["explosion_point_m"]),
        "active_window_s": ready(info["active_window_s"]),
        "constraint_margins": constraint_margins(x),
    }


def constraint_margins(x: Decision) -> dict:
    p = parameters(x)
    info = q1.kinematics(p)
    explosion = np.asarray(info["explosion_point_m"], dtype=float)
    te = float(info["explosion_time_s"])
    return {
        "release_time_lower_s": x.release_time_s,
        "fuse_delay_lower_s": x.fuse_delay_s,
        "speed_lower_mps": x.speed_mps - 70.0,
        "speed_upper_mps": 140.0 - x.speed_mps,
        "explosion_height_lower_m": float(explosion[2]),
        "explosion_height_upper_m": float(p.uav_initial[2] - explosion[2]),
        "missile_arrival_margin_s": arrival(p) - te,
    }


def _intersect(left: list[tuple[float, float]], right: list[tuple[float, float]]) -> list[tuple[float, float]]:
    result: list[tuple[float, float]] = []
    for a, b in left:
        for c, d in right:
            lo, hi = max(a, c), min(b, d)
            if lo <= hi + TOL:
                result.append((max(0.0, lo), min(1.0, hi)))
    result.sort()
    merged: list[tuple[float, float]] = []
    for lo, hi in result:
        lo, hi = max(0.0, lo), min(1.0, hi)
        if lo > hi + TOL:
            continue
        if merged and lo <= merged[-1][1] + TOL:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def _quadratic_leq(a: float, b: float, c_minus_k: float) -> list[tuple[float, float]]:
    disc = b * b - 4.0 * a * c_minus_k
    scale = max(1.0, b * b, abs(4.0 * a * c_minus_k))
    if disc < -1e-12 * scale:
        return []
    root_disc = math.sqrt(max(0.0, disc))
    lo, hi = sorted(((-b - root_disc) / (2.0 * a), (-b + root_disc) / (2.0 * a)))
    return _intersect([(0.0, 1.0)], [(lo, hi)])


def _quadratic_geq(a: float, b: float, c_minus_k: float) -> list[tuple[float, float]]:
    disc = b * b - 4.0 * a * c_minus_k
    scale = max(1.0, b * b, abs(4.0 * a * c_minus_k))
    if disc <= 1e-12 * scale:
        return [(0.0, 1.0)]
    root_disc = math.sqrt(disc)
    lo, hi = sorted(((-b - root_disc) / (2.0 * a), (-b + root_disc) / (2.0 * a)))
    return _intersect([(0.0, 1.0)], [(0.0, lo), (hi, 1.0)])


def q_intervals(t_obs: float, age: float, p: q1.Q1Parameters | None = None) -> list[tuple[float, float]]:
    p = q1.default_parameters() if p is None else p
    te = float(t_obs - age)
    if te <= 0.0 or t_obs > arrival(p) + TOL or age < 0.0 or age > min(p.smoke_duration, t_obs) + TOL:
        return []
    center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    missile = q1.missile_position(t_obs, p)
    a_h = missile[:2]
    b_h = center[:2] - missile[:2]
    a_z = float(missile[2] + p.smoke_sink_speed * age)
    b_z = float(center[2] - missile[2])
    z_low = max(0.0, float(p.uav_initial[2] - 0.5 * p.gravity * te * te))
    z_high = float(p.uav_initial[2])
    if abs(b_z) <= 1e-14:
        q_z = [(0.0, 1.0)] if z_low - TOL <= a_z <= z_high + TOL else []
    else:
        q1z, q2z = (z_low - a_z) / b_z, (z_high - a_z) / b_z
        q_z = _intersect([(0.0, 1.0)], [(min(q1z, q2z), max(q1z, q2z))])
    d = a_h - p.uav_initial[:2]
    qa = float(np.dot(b_h, b_h))
    qb = float(2.0 * np.dot(d, b_h))
    qc = float(np.dot(d, d))
    q_upper = _quadratic_leq(qa, qb, qc - (140.0 * te) ** 2)
    q_lower = _quadratic_geq(qa, qb, qc - (70.0 * te) ** 2)
    return _intersect(_intersect(q_z, q_upper), q_lower)


def _choose_interval(intervals: list[tuple[float, float]], u: float) -> tuple[float, float]:
    lengths = np.array([max(0.0, hi - lo) for lo, hi in intervals], dtype=float)
    total = float(lengths.sum())
    if total <= TOL:
        return float(intervals[0][0]), total
    target = min(max(float(u), 0.0), np.nextafter(1.0, 0.0)) * total
    carried = 0.0
    for (lo, hi), length in zip(intervals, lengths):
        if target <= carried + length or (lo, hi) == intervals[-1]:
            return float(lo + max(0.0, target - carried)), total
        carried += float(length)
    raise AssertionError("interval selection failed")


def inverse_c3(t_obs: float, age: float, fraction: float, source: str) -> Candidate:
    if not all(math.isfinite(value) for value in (t_obs, age, fraction)):
        raise PilotError("Q2_RESELECT_GEOMETRY_MISMATCH", "C3 inverse inputs must be finite")
    if t_obs <= 0.0 or age < 0.0 or age > min(20.0, t_obs) or not 0.0 <= fraction <= 1.0:
        raise PilotError(
            "Q2_RESELECT_GEOMETRY_MISMATCH",
            f"C3 inverse input outside domain: t_obs={t_obs}, age={age}, q={fraction}",
        )
    p = q1.default_parameters()
    te = float(t_obs - age)
    center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    missile = q1.missile_position(t_obs, p)
    cloud = missile + fraction * (center - missile)
    explosion = cloud + np.array([0.0, 0.0, p.smoke_sink_speed * age])
    fuse = math.sqrt(max(0.0, 2.0 * (p.uav_initial[2] - float(explosion[2])) / p.gravity))
    release = te - fuse
    displacement = explosion[:2] - p.uav_initial[:2]
    speed = float(np.linalg.norm(displacement) / te)
    decision = Decision(
        float(math.atan2(displacement[1], displacement[0]) % (2.0 * math.pi)),
        speed,
        release,
        fuse,
        source,
    )
    forward = np.asarray(q1.kinematics(parameters(decision))["explosion_point_m"], dtype=float)
    mismatch = float(np.linalg.norm(forward - explosion))
    margins = constraint_margins(decision)
    if mismatch > 1e-7 or min(margins.values()) < -1e-8:
        raise PilotError("Q2_RESELECT_GEOMETRY_MISMATCH", f"inverse mismatch={mismatch}, margins={margins}")
    return Candidate(decision, {
        "t_obs_s": float(t_obs), "smoke_age_s": float(age), "q": float(fraction),
        "cloud_center_m": ready(cloud), "constructed_explosion_m": ready(explosion),
        "forward_inverse_mismatch_m": mismatch,
    })


def witness_oracle() -> dict:
    intervals = q_intervals(5.0, 1.0)
    inside = any(lo - TOL <= 0.06 <= hi + TOL for lo, hi in intervals)
    if not inside:
        raise PilotError("Q2_RESELECT_GEOMETRY_MISMATCH", f"witness q not in {intervals}")
    candidate = inverse_c3(5.0, 1.0, 0.06, "C3I_witness")
    margins = constraint_margins(candidate.decision)
    if min(margins.values()) <= 0.0:
        raise PilotError("Q2_RESELECT_GEOMETRY_MISMATCH", "witness is not a strict interior point")
    return {
        "input": {"t_obs_s": 5.0, "smoke_age_s": 1.0, "q": 0.06},
        "q_intervals": ready(intervals),
        "interval_total_length": float(sum(hi - lo for lo, hi in intervals)),
        "decision": decision_record(candidate.decision),
        "construction": candidate.generation,
        "status": "strict_interior_pass",
    }


def _time_map(u_delta: float, u_time: float, p: q1.Q1Parameters) -> tuple[float, float]:
    delta_max = math.sqrt(2.0 * p.uav_initial[2] / p.gravity)
    delta = float(u_delta * delta_max)
    te = float(delta + u_time * (arrival(p) - delta))
    return te - delta, delta


def generate_c2(seed: int) -> tuple[list[Candidate], dict]:
    p = q1.default_parameters()
    sample = qmc.LatinHypercube(d=5, seed=seed).random(N_PROXY)
    target = p.target_base_center[:2] - p.uav_initial[:2]
    missile = p.missile_initial[:2] - p.uav_initial[:2]
    a_target = math.atan2(float(target[1]), float(target[0]))
    a_missile = math.atan2(float(missile[1]), float(missile[0]))
    values: list[Candidate] = []
    counts = {"target": 0, "missile": 0, "guard": 0}
    for row in sample:
        if row[0] < 0.45:
            domain, angle = "target", a_target + (2.0 * row[1] - 1.0) * HALF_WIDTH
        elif row[0] < 0.90:
            domain, angle = "missile", a_missile + (2.0 * row[1] - 1.0) * HALF_WIDTH
        else:
            domain, angle = "guard", 2.0 * math.pi * row[1]
        release, fuse = _time_map(float(row[3]), float(row[4]), p)
        decision = Decision(float(angle % (2.0 * math.pi)), float(70.0 + 70.0 * row[2]), release, fuse, f"C2_{domain}")
        values.append(Candidate(decision, {"domain": domain}))
        counts[domain] += 1
    return values, {"candidate_count": len(values), "domain_counts": counts, "outer_attempts": len(values), "status": "pass"}


def generate_c3(seed: int) -> tuple[list[Candidate], dict]:
    p = q1.default_parameters()
    broad = qmc.LatinHypercube(d=3, seed=seed).random(C3_BANK_SIZE)
    local = qmc.LatinHypercube(d=3, seed=seed + 7919).random(C3_BANK_SIZE)
    values: list[Candidate] = []
    stats = {
        "outer_attempts": 0, "nonempty_outer": 0, "empty_outer": 0,
        "accepted_by_stratum": {"broad": 0, "witness_neighborhood": 0},
        "interval_total_length_sum": 0.0, "interval_component_count": 0,
    }
    for index in range(C3_BANK_SIZE):
        for stratum, row in (("broad", broad[index]), ("witness_neighborhood", local[index])):
            stats["outer_attempts"] += 1
            if stratum == "broad":
                t_obs = float(0.25 + row[0] * (arrival(p) - 0.25))
                age = float(row[1] * min(p.smoke_duration, t_obs - 1e-6))
            else:
                t_obs = float(4.0 + 2.0 * row[0])
                age = float(0.5 + row[1])
            intervals = q_intervals(t_obs, age, p)
            if not intervals:
                stats["empty_outer"] += 1
                continue
            stats["nonempty_outer"] += 1
            fraction, total = _choose_interval(intervals, float(row[2]))
            candidate = inverse_c3(t_obs, age, fraction, f"C3I_{stratum}")
            candidate.generation.update({
                "q_intervals": ready(intervals), "q_interval_total_length": total,
                "stratum": stratum, "outer_index": index,
            })
            values.append(candidate)
            stats["accepted_by_stratum"][stratum] += 1
            stats["interval_total_length_sum"] += total
            stats["interval_component_count"] += len(intervals)
            if len(values) >= N_PROXY:
                stats["candidate_count"] = len(values)
                stats["nonempty_outer_rate"] = stats["nonempty_outer"] / stats["outer_attempts"]
                stats["mean_interval_total_length"] = stats["interval_total_length_sum"] / stats["nonempty_outer"]
                stats["status"] = "pass"
                return values, stats
    stats["candidate_count"] = len(values)
    stats["nonempty_outer_rate"] = stats["nonempty_outer"] / stats["outer_attempts"]
    stats["mean_interval_total_length"] = (
        stats["interval_total_length_sum"] / stats["nonempty_outer"] if stats["nonempty_outer"] else 0.0
    )
    stats["status"] = "Q2_RESELECT_C3_UNDERPOWERED"
    return values, stats


def proxy_score_record(x: Decision, geometry_pruning: bool = True) -> dict:
    p = parameters(x)
    pruning = q1.geometry_possible_window(p)
    window = pruning["possible_window_s"] if geometry_pruning else pruning["active_window_s"]
    if window is None:
        return {
            "score_s": 0.0,
            "time_point_count": 0,
            "geometry_pruning": {**pruning, "enabled": bool(geometry_pruning)},
        }
    start, stop = map(float, window)
    times = np.linspace(start, stop, PROXY["time_count"])
    margins = np.array([
        q1.full_surface_margin(float(t), p, PROXY["n_theta"], PROXY["n_levels"])["margin_m"]
        for t in times
    ])
    scaled = margins / PROXY["logistic_scale_m"]
    soft = expit(-scaled) + 1e-4 / (1.0 + np.maximum(scaled, 0.0))
    return {
        "score_s": float(np.trapezoid(soft, times)),
        "time_point_count": int(times.size),
        "geometry_pruning": {**pruning, "enabled": bool(geometry_pruning)},
    }


def proxy_score(x: Decision, geometry_pruning: bool = True) -> float:
    return float(proxy_score_record(x, geometry_pruning=geometry_pruning)["score_s"])


def evaluate(x: Decision, settings: dict, geometry_pruning: bool = True) -> dict:
    try:
        p = parameters(x)
        levels = int(settings.get("n_levels", 17 if settings["n_theta"] <= 128 else 33))
        result = q1.solve_intervals(
            p,
            scan_step=settings["scan_step_s"],
            n_theta=settings["n_theta"],
            margin_evaluator=lambda time: float(
                q1.full_surface_margin(time, p, settings["n_theta"], levels)["margin_m"]
            ),
            geometry_scope="arbitrary_control_full_cylinder_mesh",
            geometry_pruning=geometry_pruning,
        )
    except Exception as error:
        raise PilotError("Q2_RESELECT_EVALUATOR_FAILURE", str(error)) from error
    duration = float(result["effective_duration_s"])
    if not math.isfinite(duration):
        raise PilotError("Q2_RESELECT_EVALUATOR_FAILURE", "non-finite duration")
    return {
        "effective_duration_s": duration,
        "intervals_s": ready(result["intervals_s"]),
        "minimum_scan_margin_m": float(result["minimum_scan_margin_m"]),
        "root_residuals": ready(result["root_residuals"]),
        "geometry_scope": result["geometry_scope"],
        "local_minimum_checks": int(result["local_minimum_checks"]),
        "recovered_unsampled_interval_count": int(result["recovered_unsampled_interval_count"]),
        "scan_count": int(result["scan_count"]),
        "geometry_pruning": ready(result["geometry_pruning"]),
        "settings": {**dict(settings), "n_levels": levels},
    }


def run_method(method: str, seed: int, candidates: list[Candidate], generation: dict, paired_n: int) -> dict:
    started = time.perf_counter()
    candidates = candidates[:paired_n]
    proxy_started = time.perf_counter()
    scored = [(proxy_score(item.decision), index, item) for index, item in enumerate(candidates)]
    proxy_seconds = time.perf_counter() - proxy_started
    screen_n = min(N_SCREEN, len(scored))
    finalists = sorted(scored, key=lambda item: (-item[0], item[1]))[:screen_n]
    screen_records = []
    first_positive = None
    for call, (score, index, candidate) in enumerate(finalists, 1):
        result = evaluate(candidate.decision, SCREEN)
        if first_positive is None and result["effective_duration_s"] > 1e-9:
            first_positive = call
        screen_records.append({
            "call_index": call, "proposal_index": index, "proxy_score_s": score,
            "decision": decision_record(candidate.decision), "generation": candidate.generation,
            "continuous_screen": result,
        })
    precise_n = min(N_PRECISE, len(screen_records))
    precise_inputs = sorted(
        screen_records,
        key=lambda item: (-item["continuous_screen"]["effective_duration_s"], -item["proxy_score_s"], item["proposal_index"]),
    )[:precise_n]
    precise_records = []
    for rank, item in enumerate(precise_inputs, 1):
        keys = ("heading_rad", "speed_mps", "release_time_s", "fuse_delay_s", "source_domain")
        decision = Decision(**{key: item["decision"][key] for key in keys})
        precise_records.append({
            "rank": rank, "proposal_index": item["proposal_index"],
            "decision": item["decision"], "generation": item["generation"],
            "proxy_score_s": item["proxy_score_s"],
            "screen_duration_s": item["continuous_screen"]["effective_duration_s"],
            "precise": evaluate(decision, PRECISE),
        })
    seed_best = max((item["precise"]["effective_duration_s"] for item in precise_records), default=0.0)
    return {
        "method": method, "seed": seed, "status": "completed",
        "generation": generation, "paired_proxy_calls": len(candidates),
        "proxy_seconds": proxy_seconds, "screen_calls": len(screen_records),
        "first_positive_screen_call": first_positive,
        "positive_screen_count": sum(item["continuous_screen"]["effective_duration_s"] > 1e-9 for item in screen_records),
        "screen_records": screen_records, "precise_calls": len(precise_records),
        "precise_records": precise_records, "seed_best_precise_duration_s": seed_best,
        "elapsed_seconds": time.perf_counter() - started,
    }


def aggregate(records: list[dict]) -> dict:
    result = {}
    for method in ("C2-seed", "C3-I-seed"):
        chosen = [item for item in records if item["method"] == method]
        durations = np.array([item["seed_best_precise_duration_s"] for item in chosen], dtype=float)
        positives = sum(item["positive_screen_count"] for item in chosen)
        screen_calls = sum(item["screen_calls"] for item in chosen)
        first_calls = [item["first_positive_screen_call"] for item in chosen if item["first_positive_screen_call"] is not None]
        result[method] = {
            "positive_seed_count": int(np.sum(durations > 1e-9)),
            "seed_best_durations_s": durations.tolist(),
            "seed_best_median_s": float(np.median(durations)),
            "seed_best_best_s": float(np.max(durations)),
            "seed_best_std_s": float(np.std(durations)),
            "positive_screen_count": int(positives),
            "screen_call_count": int(screen_calls),
            "screen_positive_rate": float(positives / screen_calls) if screen_calls else 0.0,
            "median_first_positive_call": float(np.median(first_calls)) if first_calls else None,
            "proxy_call_count": int(sum(item["paired_proxy_calls"] for item in chosen)),
            "precise_call_count": int(sum(item["precise_calls"] for item in chosen)),
            "elapsed_seconds": float(sum(item["elapsed_seconds"] for item in chosen)),
        }
    return result


def choose_role(summary: dict) -> tuple[str, dict]:
    c2, c3 = summary["C2-seed"], summary["C3-I-seed"]
    eps = 1e-4
    d2, d3 = c2["seed_best_durations_s"], c3["seed_best_durations_s"]
    c2_wins = sum(a > b + eps for a, b in zip(d2, d3))
    c3_wins = sum(b > a + eps for a, b in zip(d2, d3))
    if c3["positive_seed_count"] > c2["positive_seed_count"] or (
        c3["positive_seed_count"] == c2["positive_seed_count"]
        and c3["seed_best_median_s"] > c2["seed_best_median_s"] + eps
    ):
        role = "C3_PRIMARY_SEED_C2_GUARD"
    elif (c2_wins > 0 and c3_wins > 0) or c3["screen_positive_rate"] > c2["screen_positive_rate"]:
        role = "COMBINED_C2_C3_SEEDING"
    elif (
        c3["positive_seed_count"] <= c2["positive_seed_count"]
        and c3["seed_best_median_s"] <= c2["seed_best_median_s"] + eps
        and c3["seed_best_best_s"] <= c2["seed_best_best_s"] + eps
        and c3["screen_positive_rate"] <= c2["screen_positive_rate"]
    ):
        role = "C2_PRIMARY_C3_INTERNAL_ONLY"
    else:
        role = "Q2_RESELECT_INCONCLUSIVE"
    if c2["positive_seed_count"] == 0 and c3["positive_seed_count"] == 0:
        role = "Q2_RESELECT_ALL_ZERO"
    return role, {"duration_tolerance_s": eps, "c2_seed_wins": c2_wins, "c3_seed_wins": c3_wins}


def report_text(result: dict) -> str:
    rows = []
    for method in ("C2-seed", "C3-I-seed"):
        item = result["aggregate"][method]
        rows.append(
            f"| {method} | {item['positive_seed_count']}/3 | "
            f"{item['positive_screen_count']}/{item['screen_call_count']} | "
            f"{item['seed_best_median_s']:.9f} | {item['seed_best_best_s']:.9f} | "
            f"{item['seed_best_std_s']:.3e} | {item['proxy_call_count']} | {item['precise_call_count']} |"
        )
    witness = result["geometry_witness"]
    return f"""# Q2 C3 几何复核与公平重选试验

> 内部技术证据；不进入论文，不引用或展示外部数值结果。绑定 `SPEC-Q2-2.1-RESELECTION-PILOT`。

## 几何结论

严格内点 `(t_o,s,q)=(5,1,0.06)` 复核状态为 `{witness['status']}`。解析 `Q(5,1)` 为 `{witness['q_intervals']}`，总区间长度 `{witness['interval_total_length']:.12f}`；反解速度 `{witness['decision']['speed_mps']:.9f} m/s`、释放时刻 `{witness['decision']['release_time_s']:.9f} s`。因此 C3-I 可行集在该点附近连续，不可能只有旧试验随机命中的 6 个点。

## 公平条件

- C2-seed 与 C3-I-seed 使用相同三个种子、相同实际代理调用数、每种子 8 次连续筛选和 2 次精算。
- C3-I 先解析求 `Q(t_o,s)` 再在区间内直接取样；候选数只作预算，不作几何判据。
- 最终评分均为同一完整圆柱有限线段连续遮蔽时长。

## 结果

| 方法 | 正值种子 | 筛选正值 | seed-best 中位数/s | 最佳值/s | 标准差/s | 代理调用 | 精算调用 |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(rows)}

冻结规则给出的角色判定为 **{result['role_decision']['role']}**。它只决定种子入口关系：C3-I 仍是三维几何播种流形，后续正式优化必须回到 C3-X 或原变量完整四维域，并由统一连续目标精算。

完整逐候选未舍入参数、解析区间、约束余量、连续区间与运行身份保存在 `{result['output_path']}`。
"""


def run(output: Path, report: Path) -> dict:
    identities = {
        "official_input_sha256": sha256(ROOT / INPUT_PATH),
        "geometry_sha256": sha256(ROOT / GEOMETRY_PATH),
        "spec_sha256": sha256(ROOT / SPEC_PATH),
    }
    expected = {
        "official_input_sha256": INPUT_SHA,
        "geometry_sha256": GEOMETRY_SHA,
        "spec_sha256": SPEC_SHA,
    }
    if identities != expected:
        raise PilotError("Q2_RESELECT_IDENTITY_MISMATCH", f"expected={expected}, observed={identities}")
    witness = witness_oracle()
    records = []
    paired_counts = {}
    for seed in SEEDS:
        c2_candidates, c2_generation = generate_c2(seed)
        c3_candidates, c3_generation = generate_c3(seed)
        paired_n = min(len(c2_candidates), len(c3_candidates), N_PROXY)
        paired_counts[str(seed)] = paired_n
        if paired_n == 0:
            raise PilotError("Q2_RESELECT_C3_UNDERPOWERED", f"seed {seed} produced no C3 candidate")
        for method, candidates, generation in (
            ("C2-seed", c2_candidates, c2_generation),
            ("C3-I-seed", c3_candidates, c3_generation),
        ):
            print(json.dumps({"stage": "reselection", "method": method, "seed": seed, "status": "started"}), flush=True)
            record = run_method(method, seed, candidates, generation, paired_n)
            records.append(record)
            print(json.dumps({
                "stage": "reselection", "method": method, "seed": seed, "status": "completed",
                "seed_best_precise_duration_s": record["seed_best_precise_duration_s"],
                "positive_screen_count": record["positive_screen_count"],
                "elapsed_seconds": record["elapsed_seconds"],
            }), flush=True)
    summary = aggregate(records)
    role, diagnostics = choose_role(summary)
    script = ROOT / "src/q2/reselection_pilot.py"
    result = {
        "schema_version": "1.0",
        "result_id": "Q2-SPEC-Q2-2.1-RESELECTION-PILOT",
        "claim_id": "A.Q2.RESELECTION_PILOT.001",
        "status": "ok" if role not in {"Q2_RESELECT_ALL_ZERO"} else "fail",
        "purpose": "internal_seed_family_comparison_not_formal_q2_solution",
        "identities": identities,
        "geometry_witness": witness,
        "budget": {
            "seeds": SEEDS, "proxy_candidates_per_method_seed": N_PROXY,
            "screen_calls_per_method_seed": N_SCREEN, "precise_calls_per_method_seed": N_PRECISE,
            "c3_outer_bank_per_stratum": C3_BANK_SIZE, "half_width_rad": HALF_WIDTH,
            "proxy": PROXY, "screen": SCREEN, "precise": PRECISE,
            "paired_actual_proxy_calls": paired_counts,
        },
        "records": records,
        "aggregate": summary,
        "role_decision": {"role": role, **diagnostics},
        "limitations": [
            "The pilot compares seed generators, not complete model families or strict global optima.",
            "C3-I is a three-dimensional centerline seed manifold and does not cover the full four-dimensional domain.",
            "External numerical results were neither loaded nor compared.",
        ],
        "run_identity": {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "execution_kind": "declared_stochastic_repeated_fixed_seeds",
            "python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__,
            "seeds": SEEDS, "script_sha256": sha256(script),
            "q1_model_sha256": sha256(ROOT / "src/q1/model.py"), **identities,
        },
        "output_path": output.as_posix(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ready(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        print(json.dumps({"status": "fail", "failure_code": error.code, "message": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "status": result["status"], "result_id": result["result_id"],
        "role": result["role_decision"]["role"], "output": result["output_path"],
    }, ensure_ascii=False))
    return 0 if result["status"] == "ok" else 3


if __name__ == "__main__":
    raise SystemExit(main())
