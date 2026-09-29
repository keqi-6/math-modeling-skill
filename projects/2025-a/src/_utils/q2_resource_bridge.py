#!/usr/bin/env python3
"""Exploratory Q2 sensitivity bridges toward Q3 and Q4.

This script deliberately does not solve Q3 or Q4.  It keeps the frozen Q2
solution as the baseline and varies only one resource mechanism at a time:

* a second bomb on the same frozen FY1 track, shifted only in release time;
* one additional UAV at a time, using either direct decision transfer or a
  one-dimensional inherited-geometry opportunity scan.

Multiple-cloud performance is measured as the union of intervals in which an
individual cloud already covers the complete cylinder.  This is a conservative
lower bound and excludes cross-cloud partial-target geometric synergy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
import model as q1  # noqa: E402


SCREEN = {"scan_step_s": 0.05, "n_theta": 64, "n_levels": 9}
PRECISE = {"scan_step_s": 0.005, "n_theta": 512, "n_levels": 33}
SECOND_BOMB_GAPS_S = np.linspace(1.0, 8.0, 29)
OPPORTUNITY_DENSE_STEP_S = 0.05
OPPORTUNITY_EVALUATIONS = 31
UAV_INITIALS = {
    "FY2": np.array([12000.0, 1400.0, 1400.0]),
    "FY3": np.array([6000.0, -3000.0, 700.0]),
}


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


def merge_intervals(*collections: list[list[float]]) -> list[list[float]]:
    intervals = sorted(
        ([float(left), float(right)] for collection in collections for left, right in collection),
        key=lambda item: (item[0], item[1]),
    )
    merged: list[list[float]] = []
    for left, right in intervals:
        if not merged or left - merged[-1][1] > 2e-9:
            merged.append([left, right])
        else:
            merged[-1][1] = max(merged[-1][1], right)
    return merged


def interval_duration(intervals: list[list[float]]) -> float:
    return float(sum(float(right) - float(left) for left, right in intervals))


def union_metrics(baseline_intervals: list[list[float]], added_intervals: list[list[float]]) -> dict:
    baseline = interval_duration(baseline_intervals)
    added = interval_duration(added_intervals)
    union = merge_intervals(baseline_intervals, added_intervals)
    union_duration = interval_duration(union)
    overlap = max(0.0, baseline + added - union_duration)
    return {
        "conservative_union_intervals_s": union,
        "conservative_union_duration_s": union_duration,
        "added_single_cloud_duration_s": added,
        "overlap_loss_s": overlap,
        "marginal_union_gain_s": union_duration - baseline,
        "marginal_capture_ratio": 0.0 if added <= 1e-12 else (union_duration - baseline) / added,
    }


def parameters(
    uav_initial: np.ndarray,
    heading_rad: float,
    speed_mps: float,
    release_time_s: float,
    fuse_delay_s: float,
) -> q1.Q1Parameters:
    base = q1.default_parameters()
    return replace(
        base,
        uav_initial=np.asarray(uav_initial, dtype=float),
        uav_direction=np.array([math.cos(heading_rad), math.sin(heading_rad), 0.0]),
        uav_speed=float(speed_mps),
        release_time=float(release_time_s),
        fuse_delay=float(fuse_delay_s),
    )


def evaluate(p: q1.Q1Parameters, settings: dict) -> dict:
    try:
        info = q1.kinematics(p)
        result = q1.solve_intervals(
            p,
            scan_step=float(settings["scan_step_s"]),
            n_theta=int(settings["n_theta"]),
            margin_evaluator=lambda time: float(
                q1.full_surface_margin(
                    time, p, int(settings["n_theta"]), int(settings["n_levels"])
                )["margin_m"]
            ),
            geometry_scope="arbitrary_control_full_cylinder_mesh",
        )
        return ready(
            {
                "feasible": True,
                "effective_duration_s": float(result["effective_duration_s"]),
                "intervals_s": result["intervals_s"],
                "minimum_scan_margin_m": float(result["minimum_scan_margin_m"]),
                "kinematics": info,
            }
        )
    except (q1.Q1Error, ValueError, FloatingPointError) as error:
        return {
            "feasible": False,
            "effective_duration_s": None,
            "intervals_s": [],
            "failure": getattr(error, "code", type(error).__name__),
        }


def base_decision(formal: dict) -> dict:
    decision = formal["formal_best"]["decision"]
    return {
        "heading_rad": float(decision["heading_rad"]),
        "speed_mps": float(decision["speed_mps"]),
        "release_time_s": float(decision["release_time_s"]),
        "fuse_delay_s": float(decision["fuse_delay_s"]),
        "explosion_time_s": float(decision["explosion_time_s"]),
    }


def same_uav_second_bomb(formal: dict, decision: dict) -> dict:
    baseline_intervals = formal["formal_best"]["precise"]["intervals_s"]
    records = []
    for index, gap in enumerate(SECOND_BOMB_GAPS_S, 1):
        release = decision["release_time_s"] + float(gap)
        p = parameters(
            q1.default_parameters().uav_initial,
            decision["heading_rad"],
            decision["speed_mps"],
            release,
            decision["fuse_delay_s"],
        )
        result = evaluate(p, SCREEN)
        record = {
            "release_gap_s": float(gap),
            "second_release_time_s": release,
            "second_explosion_time_s": release + decision["fuse_delay_s"],
            "second_single_cloud": result,
        }
        if result["feasible"]:
            record.update(union_metrics(baseline_intervals, result["intervals_s"]))
        records.append(record)
        if index == len(SECOND_BOMB_GAPS_S) or index % 7 == 0:
            print(json.dumps({"stage": "same_uav_second_bomb", "completed": index, "total": len(SECOND_BOMB_GAPS_S)}), flush=True)

    feasible = [record for record in records if record["second_single_cloud"]["feasible"]]
    best = max(feasible, key=lambda item: (item["marginal_union_gain_s"], -item["release_gap_s"]))
    best_p = parameters(
        q1.default_parameters().uav_initial,
        decision["heading_rad"],
        decision["speed_mps"],
        best["second_release_time_s"],
        decision["fuse_delay_s"],
    )
    precise = evaluate(best_p, PRECISE)
    precise_metrics = union_metrics(baseline_intervals, precise["intervals_s"])
    return {
        "design": {
            "fixed": ["FY1 heading", "FY1 speed", "first Q2 bomb", "second-bomb fuse delay"],
            "varied": "second release gap only",
            "range_s": [float(SECOND_BOMB_GAPS_S[0]), float(SECOND_BOMB_GAPS_S[-1]), len(SECOND_BOMB_GAPS_S)],
            "official_minimum_release_gap_s": 1.0,
            "metric": "union of independently complete-cylinder intervals",
            "joint_partial_target_synergy_included": False,
        },
        "records": records,
        "screen_best": best,
        "precise_best": {
            "release_gap_s": best["release_gap_s"],
            "second_release_time_s": best["second_release_time_s"],
            "second_explosion_time_s": best["second_explosion_time_s"],
            "second_single_cloud": precise,
            **precise_metrics,
        },
    }


def inherited_geometry(decision: dict, baseline_intervals: list[list[float]]) -> dict:
    p = parameters(
        q1.default_parameters().uav_initial,
        decision["heading_rad"],
        decision["speed_mps"],
        decision["release_time_s"],
        decision["fuse_delay_s"],
    )
    midpoint = 0.5 * sum(float(value) for value in baseline_intervals[0])
    missile = q1.missile_position(midpoint, p)
    cloud = q1.smoke_center(midpoint, p)
    target_center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    sight = target_center - missile
    q_value = float(np.dot(cloud - missile, sight) / np.dot(sight, sight))
    projected = missile + q_value * sight
    return ready(
        {
            "observation_time_s": midpoint,
            "smoke_age_s": midpoint - decision["explosion_time_s"],
            "line_parameter_q": q_value,
            "baseline_cloud_center_m": cloud,
            "projected_line_point_m": projected,
            "baseline_perpendicular_residual_m": float(np.linalg.norm(cloud - projected)),
            "target_center_m": target_center,
        }
    )


def derive_opportunity(
    uav_initial: np.ndarray,
    observation_time_s: float,
    geometry: dict,
) -> dict | None:
    base = q1.default_parameters()
    smoke_age = float(geometry["smoke_age_s"])
    q_value = float(geometry["line_parameter_q"])
    explosion_time = float(observation_time_s - smoke_age)
    if explosion_time <= 0.0:
        return None
    missile = q1.missile_position(observation_time_s, base)
    target_center = np.asarray(geometry["target_center_m"], dtype=float)
    desired_cloud = missile + q_value * (target_center - missile)
    explosion = desired_cloud + np.array([0.0, 0.0, base.smoke_sink_speed * smoke_age])
    height = float(uav_initial[2])
    if explosion[2] < 0.0 or explosion[2] > height:
        return None
    fuse_delay = math.sqrt(max(0.0, 2.0 * (height - float(explosion[2])) / base.gravity))
    release_time = explosion_time - fuse_delay
    if release_time < 0.0:
        return None
    horizontal = explosion[:2] - uav_initial[:2]
    distance = float(np.linalg.norm(horizontal))
    speed = distance / explosion_time
    if not 70.0 <= speed <= 140.0 or distance <= 1e-12:
        return None
    heading = float(math.atan2(horizontal[1], horizontal[0]) % (2.0 * math.pi))
    return ready(
        {
            "observation_time_s": float(observation_time_s),
            "heading_rad": heading,
            "speed_mps": speed,
            "release_time_s": release_time,
            "fuse_delay_s": fuse_delay,
            "explosion_time_s": explosion_time,
            "desired_cloud_at_observation_m": desired_cloud,
            "explosion_point_m": explosion,
        }
    )


def select_opportunities(uav_initial: np.ndarray, geometry: dict) -> tuple[list[dict], dict]:
    arrival = float(np.linalg.norm(q1.default_parameters().missile_initial) / q1.default_parameters().missile_speed)
    times = np.arange(
        float(geometry["smoke_age_s"]) + OPPORTUNITY_DENSE_STEP_S,
        arrival,
        OPPORTUNITY_DENSE_STEP_S,
    )
    dense = [candidate for time in times if (candidate := derive_opportunity(uav_initial, float(time), geometry)) is not None]
    if not dense:
        return [], {"dense_feasible_count": 0, "feasible_observation_time_range_s": None}
    indices = np.unique(np.rint(np.linspace(0, len(dense) - 1, min(OPPORTUNITY_EVALUATIONS, len(dense)))).astype(int))
    selected = [dense[int(index)] for index in indices]
    return selected, {
        "dense_step_s": OPPORTUNITY_DENSE_STEP_S,
        "dense_feasible_count": len(dense),
        "feasible_observation_time_range_s": [dense[0]["observation_time_s"], dense[-1]["observation_time_s"]],
        "evaluated_count": len(selected),
    }


def additional_uav_bridge(formal: dict, decision: dict) -> dict:
    baseline_intervals = formal["formal_best"]["precise"]["intervals_s"]
    geometry = inherited_geometry(decision, baseline_intervals)
    platforms = {}
    for uav_id, uav_initial in UAV_INITIALS.items():
        transferred_p = parameters(
            uav_initial,
            decision["heading_rad"],
            decision["speed_mps"],
            decision["release_time_s"],
            decision["fuse_delay_s"],
        )
        transferred = evaluate(transferred_p, SCREEN)
        transferred_metrics = union_metrics(baseline_intervals, transferred["intervals_s"]) if transferred["feasible"] else None

        candidates, feasibility = select_opportunities(uav_initial, geometry)
        records = []
        for index, candidate in enumerate(candidates, 1):
            p = parameters(
                uav_initial,
                candidate["heading_rad"],
                candidate["speed_mps"],
                candidate["release_time_s"],
                candidate["fuse_delay_s"],
            )
            result = evaluate(p, SCREEN)
            record = {**candidate, "single_cloud": result}
            if result["feasible"]:
                record.update(union_metrics(baseline_intervals, result["intervals_s"]))
            records.append(record)
            if index == len(candidates) or index % 8 == 0:
                print(json.dumps({"stage": "additional_uav_opportunity", "uav_id": uav_id, "completed": index, "total": len(candidates)}), flush=True)

        feasible_records = [record for record in records if record["single_cloud"]["feasible"]]
        best = max(feasible_records, key=lambda item: (item["marginal_union_gain_s"], -item["observation_time_s"])) if feasible_records else None
        precise_best = None
        if best is not None:
            best_p = parameters(
                uav_initial,
                best["heading_rad"],
                best["speed_mps"],
                best["release_time_s"],
                best["fuse_delay_s"],
            )
            precise = evaluate(best_p, PRECISE)
            precise_best = {**{key: best[key] for key in (
                "observation_time_s", "heading_rad", "speed_mps", "release_time_s",
                "fuse_delay_s", "explosion_time_s", "desired_cloud_at_observation_m", "explosion_point_m",
            )}, "single_cloud": precise, **union_metrics(baseline_intervals, precise["intervals_s"])}
        platforms[uav_id] = {
            "uav_initial_m": uav_initial,
            "direct_q2_decision_transfer": {"single_cloud": transferred, "union_with_q2": transferred_metrics},
            "opportunity_feasibility": feasibility,
            "opportunity_records": records,
            "screen_best": best,
            "precise_best": precise_best,
        }
    return {
        "design": {
            "fixed_geometry_from_q2": geometry,
            "varied": "observation time only",
            "platforms_tested_separately": list(UAV_INITIALS),
            "joint_multi_uav_optimization": False,
            "all_three_uav_combination_reported": False,
            "metric": "union of frozen Q2 interval and one independently complete additional-cloud interval",
        },
        "platforms": ready(platforms),
    }


def run() -> dict:
    formal_path = ROOT / "docs" / "q2_result.json"
    decision_path = ROOT / "docs" / "q2_decision_sensitivity.json"
    formal = json.loads(formal_path.read_text(encoding="utf-8"))
    prior_sensitivity = json.loads(decision_path.read_text(encoding="utf-8"))
    decision = base_decision(formal)
    baseline_duration = float(formal["formal_best"]["precise"]["effective_duration_s"])

    same_uav = same_uav_second_bomb(formal, decision)
    additional = additional_uav_bridge(formal, decision)

    formal_hash = sha256(formal_path)
    checks = {
        "formal_result_identity_matches_existing_decision_sensitivity": formal_hash == prior_sensitivity["identities"]["formal_result_sha256"],
        "q2_formal_result_unchanged": baseline_duration == float(prior_sensitivity["baseline"]["stored_duration_s"]),
        "same_uav_release_gap_respects_official_minimum": all(float(record["release_gap_s"]) >= 1.0 for record in same_uav["records"]),
        "additional_uav_opportunity_candidates_exist": all(additional["platforms"][uav_id]["opportunity_records"] for uav_id in UAV_INITIALS),
        "no_q3_or_q4_joint_optimization_performed": True,
    }
    return ready(
        {
            "schema_version": "1.0",
            "result_id": "Q2-RESOURCE-BRIDGE-SENSITIVITY-20260827",
            "question_id": "Q2",
            "status": "pass" if all(checks.values()) else "fail",
            "analysis_kind": "fixed_q2_baseline_resource_increment_scenario_analysis",
            "probability_interpretation": False,
            "reoptimization_of_q2_baseline": False,
            "formal_q3_or_q4_solution": False,
            "settings": {
                "screen": SCREEN,
                "precise_best_rescore": PRECISE,
                "second_bomb_gap_grid_s": [float(SECOND_BOMB_GAPS_S[0]), float(SECOND_BOMB_GAPS_S[-1]), len(SECOND_BOMB_GAPS_S)],
                "opportunity_dense_step_s": OPPORTUNITY_DENSE_STEP_S,
                "opportunity_evaluations_per_platform_max": OPPORTUNITY_EVALUATIONS,
            },
            "identities": {
                "official_input_sha256": sha256(ROOT / "data" / "A题.pdf"),
                "parameter_registry_sha256": sha256(ROOT / "planning" / "05_official_parameter_registry.md"),
                "q1_model_sha256": sha256(ROOT / "src" / "q1" / "model.py"),
                "q2_formal_result_sha256": formal_hash,
                "q2_decision_sensitivity_sha256": sha256(decision_path),
            },
            "baseline": {
                "result_id": formal["result_id"],
                "decision": decision,
                "effective_duration_s": baseline_duration,
                "intervals_s": formal["formal_best"]["precise"]["intervals_s"],
            },
            "same_uav_second_bomb": same_uav,
            "additional_uav": additional,
            "checks": checks,
            "claim_boundary": {
                "supports": [
                    "local Q2 decision-response interpretation from the existing decision-axis artifact",
                    "same-track temporal complementarity under a one-parameter second-bomb shift",
                    "platform-specific reachability and separated opportunity windows for FY2/FY3",
                ],
                "does_not_support": [
                    "Q3 three-bomb optimality",
                    "Q4 three-UAV joint optimality",
                    "cross-cloud partial-target geometric synergy",
                    "global optimality or empirical reliability",
                ],
            },
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(output.relative_to(ROOT))}), flush=True)
    if payload["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
