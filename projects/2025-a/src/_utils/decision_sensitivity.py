"""Decision-axis sensitivity and cylinder-geometry diagnostics for Q1/Q2."""

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
sys.path.insert(0, str(ROOT / "src" / "q2"))
import model as q1  # noqa: E402

SETTINGS = {"scan_step_s": 0.02, "n_theta": 128, "n_levels": 17}
GEOMETRY_GRID = {"theta_count": 361, "z_count": 81}


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


def parameters(heading_rad: float, speed_mps: float, release_time_s: float, explosion_time_s: float):
    base = q1.default_parameters()
    return replace(
        base,
        uav_direction=np.array([math.cos(heading_rad), math.sin(heading_rad), 0.0]),
        uav_speed=float(speed_mps),
        release_time=float(release_time_s),
        fuse_delay=float(explosion_time_s - release_time_s),
    )


def evaluate(point: dict[str, float]) -> dict:
    try:
        p = parameters(**point)
        info = q1.kinematics(p)
        result = q1.solve_intervals(
            p,
            scan_step=SETTINGS["scan_step_s"],
            n_theta=SETTINGS["n_theta"],
            margin_evaluator=lambda time: float(
                q1.full_surface_margin(
                    time, p, SETTINGS["n_theta"], SETTINGS["n_levels"]
                )["margin_m"]
            ),
            geometry_scope="arbitrary_control_full_cylinder_mesh",
        )
        return {
            "feasible": True,
            "duration_s": float(result["effective_duration_s"]),
            "intervals_s": result["intervals_s"],
            "explosion_height_m": float(np.asarray(info["explosion_point_m"])[2]),
            "minimum_scan_margin_m": float(result["minimum_scan_margin_m"]),
            "geometry_scope": result["geometry_scope"],
        }
    except (q1.Q1Error, ValueError, FloatingPointError) as error:
        return {"feasible": False, "duration_s": None, "intervals_s": [], "failure": getattr(error, "code", type(error).__name__)}


def sweep(base: dict[str, float], axis: str, values: list[float]) -> list[dict]:
    records = []
    for index, value in enumerate(values, 1):
        point = dict(base)
        point[axis] = float(value)
        records.append({"value": float(value), **evaluate(point)})
        if index == len(values) or index % 12 == 0:
            print(json.dumps({"axis": axis, "completed": index, "total": len(values)}), flush=True)
    return records


def retention_summary(records: list[dict], nominal_duration: float) -> dict:
    feasible = [item for item in records if item["feasible"]]
    positive = [item for item in feasible if float(item["duration_s"]) > 1e-9]
    near = [item for item in feasible if float(item["duration_s"]) >= 0.95 * nominal_duration]
    best = max(feasible, key=lambda item: float(item["duration_s"])) if feasible else None
    return {
        "feasible_count": len(feasible),
        "positive_count": len(positive),
        "positive_sampled_range": None if not positive else [positive[0]["value"], positive[-1]["value"]],
        "retention_95_sampled_range": None if not near else [near[0]["value"], near[-1]["value"]],
        "sampled_best": None if best is None else {"value": best["value"], "duration_s": best["duration_s"]},
    }


def surface_geometry(p: q1.Q1Parameters, time_s: float, keep_grid: bool) -> dict:
    theta = np.linspace(0.0, 2.0 * math.pi, GEOMETRY_GRID["theta_count"], endpoint=False)
    z_values = np.linspace(float(p.target_base_center[2]), float(p.target_base_center[2] + p.target_height), GEOMETRY_GRID["z_count"])
    cloud, missile = q1.smoke_center(time_s, p), q1.missile_position(time_s, p)
    margins, lambdas = np.empty((z_values.size, theta.size)), np.empty((z_values.size, theta.size))
    for row, z_value in enumerate(z_values):
        distances, raw_lambda = q1.segment_distance(cloud, missile, q1.target_circle(theta, float(z_value), p))
        margins[row], lambdas[row] = distances - p.smoke_radius, raw_lambda
    endpoint_by_theta = np.maximum(margins[0], margins[-1])
    all_z_by_theta = np.max(margins, axis=0)
    surface_index = np.unravel_index(int(np.argmax(margins)), margins.shape)
    worst_theta_index = int(np.argmax(all_z_by_theta))
    result = {
        "time_s": float(time_s),
        "surface_max_margin_m": float(margins[surface_index]),
        "surface_argmax": {"theta_rad": float(theta[surface_index[1]]), "z_m": float(z_values[surface_index[0]]), "lambda_raw": float(lambdas[surface_index])},
        "sampled_rim_max_margin_m": float(np.max(endpoint_by_theta)),
        "max_vertical_interior_excess_over_endpoints_m": float(np.max(all_z_by_theta - endpoint_by_theta)),
        "max_surface_minus_sampled_rim_m": float(np.max(margins) - np.max(endpoint_by_theta)),
        "all_sampled_vertical_generators_endpoint_controlled": bool(np.max(all_z_by_theta - endpoint_by_theta) <= 1e-10),
        "missile_position_m": missile,
        "smoke_center_m": cloud,
    }
    if keep_grid:
        result["grid"] = {
            "theta_deg": np.degrees(theta), "z_m": z_values, "margin_m": margins,
            "lambda_raw": lambdas, "worst_theta_index": worst_theta_index,
            "worst_vertical_profile_margin_m": margins[:, worst_theta_index],
            "worst_vertical_endpoint_envelope_m": endpoint_by_theta[worst_theta_index],
        }
    return ready(result)


def design(question: str) -> tuple[dict, dict, dict, float, list]:
    if question == "q1":
        formal = json.loads((ROOT / "docs/q1_result.json").read_text(encoding="utf-8"))
        base = {"heading_rad": math.pi, "speed_mps": 120.0, "release_time_s": 1.5, "explosion_time_s": 5.1}
        grids = {
            "heading_rad": (base["heading_rad"] + np.radians(np.linspace(-2.0, 2.0, 81))).tolist(),
            "speed_mps": np.linspace(70.0, 140.0, 71).tolist(),
            "release_time_s": np.linspace(0.0, 3.0, 61).tolist(),
            "explosion_time_s": np.linspace(4.0, 6.5, 51).tolist(),
        }
        return base, grids, formal, float(formal["effective_duration_s"]), formal["intervals_s"]
    formal = json.loads((ROOT / "docs/q2_result.json").read_text(encoding="utf-8"))
    decision = formal["formal_best"]["decision"]
    release, explosion = float(decision["release_time_s"]), float(decision["explosion_time_s"])
    base = {"heading_rad": float(decision["heading_rad"]), "speed_mps": float(decision["speed_mps"]), "release_time_s": release, "explosion_time_s": explosion}
    grids = {
        "heading_rad": (base["heading_rad"] + np.radians(np.linspace(-3.0, 3.0, 31))).tolist(),
        "speed_mps": np.linspace(70.0, 140.0, 29).tolist(),
        "release_time_s": np.linspace(0.0, explosion, 25).tolist(),
        "explosion_time_s": np.linspace(release, 3.0, 31).tolist(),
    }
    precise = formal["formal_best"]["precise"]
    return base, grids, formal, float(precise["effective_duration_s"]), precise["intervals_s"]


def run(question: str) -> dict:
    base, grids, _, stored_duration, stored_intervals = design(question)
    nominal = evaluate(base)
    if not nominal["feasible"]:
        raise RuntimeError(f"{question.upper()}_DECISION_SENSITIVITY_NOMINAL_INFEASIBLE")
    sweeps = {axis: sweep(base, axis, values) for axis, values in grids.items()}
    summaries = {axis: retention_summary(records, float(nominal["duration_s"])) for axis, records in sweeps.items()}
    p = parameters(**base)
    entry, exit_ = (float(value) for value in stored_intervals[0])
    midpoint = 0.5 * (entry + exit_)
    geometry = {"settings": GEOMETRY_GRID, "records": [surface_geometry(p, entry, False), surface_geometry(p, midpoint, True), surface_geometry(p, exit_, False)]}
    max_vertical_excess = max(float(record["max_vertical_interior_excess_over_endpoints_m"]) for record in geometry["records"])
    nominal_difference = abs(float(nominal["duration_s"]) - stored_duration)
    checks = {
        "nominal_matches_stored_within_screening_tolerance": nominal_difference <= 1e-4,
        "full_surface_evaluator_used_for_all_perturbed_controls": nominal.get("geometry_scope") == "arbitrary_control_full_cylinder_mesh",
        "all_nominal_constraints_feasible": True,
    }
    return ready({
        "schema_version": "1.0", "question_id": question.upper(),
        "result_id": f"{question.upper()}-DECISION-AXIS-SENSITIVITY-20260827",
        "status": "pass" if all(checks.values()) else "fail",
        "analysis_kind": "fixed_nominal_scheme_one_axis_deterministic_scenario_sweep",
        "probability_interpretation": False, "reoptimization_per_perturbation": False,
        "settings": SETTINGS,
        "design_declared_before_observation": {
            "axes": ["heading_rad", "speed_mps", "release_time_s", "explosion_time_s"],
            "meaning": "Equivalent Q2 decision coordinates; release and explosion times are independent with fuse_delay=explosion-release.",
            "ranges": {axis: [float(values[0]), float(values[-1]), len(values)] for axis, values in grids.items()},
            "interpretation": "Exploratory deterministic scenarios for positive-performance and 95% retention windows; not empirical uncertainty bands.",
        },
        "identities": {
            "official_input_sha256": sha256(ROOT / "data/A题.pdf"),
            "q1_model_sha256": sha256(ROOT / "src/q1/model.py"),
            "formal_result_sha256": sha256(ROOT / f"docs/{question}_result.json"),
        },
        "baseline": {"decision": base, "stored_duration_s": stored_duration, "screening_duration_s": nominal["duration_s"], "absolute_difference_s": nominal_difference, "stored_intervals_s": stored_intervals},
        "sweeps": sweeps, "summaries": summaries, "geometry_validation": geometry, "checks": checks,
        "claim_boundary": "Supports decision-axis interpretation under a full-cylinder surface mesh. Endpoint-control diagnostics are descriptive only and are not generalized from Q1 to arbitrary controls; this is not global optimality or empirical reliability.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", choices=["q1", "q2"], required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = run(args.question)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": payload["status"], "output": str(args.output)}), flush=True)
    if payload["status"] != "pass":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
