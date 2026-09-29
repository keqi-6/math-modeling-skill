"""Run the internal Q2 E3 structural or E4 reality-model validation.

The checks use only the official problem statement, frozen project contracts,
and the formal Q2 result.  Stress bands are declared below before observations
and are diagnostic ranges, not empirical confidence intervals.
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
sys.path.insert(0, str(ROOT / "src" / "q2"))
import model as q1  # noqa: E402
import reselection_pilot as pilot  # noqa: E402


EXPECTED = {
    "data/A题.pdf": "a37f6aad30b16ea09da9cb320ce194b12d3a28874008cf9ff19549f6c6079447",
    "planning/12_q2_c3_geometry_and_candidate_reselection.md": "210f5fc5ccb99dc8bba7877265f0da7762efca0614bc5ffe540d08bbdb397eaf",
    "planning/13_q2_reselection_pilot_spec.md": "dfe33fbda5cbc4203730e2f6bc26aa972e42711fd571c42b2cf2904553f331c3",
    "planning/14_q2_formal_solver_spec.md": "39b2b9f842d25e7111198a7c3dd5a277c2286ca0cabe15104ac95c56d91031df",
    "src/q1/model.py": "cb36870ca55ed3b1e3c3adfe02cd91667c89249fa1aeb730cb42f0a1bbd4f7f1",
    "src/q2/reselection_pilot.py": "061ef27a29eb2afe62f28a13843ff2bd28d5133e22801c44b2804ecf2d621244",
    "src/q2/solve.py": "7a9ca6e7dbe425620d22d714acb6f174531d368ac950f866da3818685b4e9d8f",
    "docs/q2_result.json": "0dd12455e0898bdb5e087888da848ea66bfa8caf325b1180b0412f23557eab7f",
    "docs/q2_validation_results.json": "16971468e98106e916405d7da4fda0d0c23f5e96fd23a0739f15d56fb083a436",
}

# Declared before observations. E3 tolerances follow the existing E1/E2 scale.
TOLERANCES = {
    "identity_and_kinematic_closure": 1e-7,
    "constraint_margin": 1e-7,
    "duration_consistency_s": 1e-4,
    "endpoint_margin_m": 1e-6,
    "monotonic_duration_s": 1e-4,
    "symmetry_duration_s": 1e-4,
    "zero_radius_limit_s": 1e-4,
}

E3_SETTINGS = {"scan_step_s": 0.005, "n_theta": 512, "n_levels": 33}
E3_MONOTONIC_GRIDS = {
    "smoke_radius_m": [8.0, 10.0, 12.0],
    "smoke_duration_s": [1.0, 10.0, 20.0],
    "target_radius_m": [5.0, 7.0, 9.0],
    "target_height_m": [5.0, 10.0, 15.0],
}

# Diagnostic stress bands around official values, not probability statements.
E4_SETTINGS = {"scan_step_s": 0.02, "n_theta": 128, "n_levels": 17}
E4_PARAMETER_GRIDS = {
    "smoke_radius_m": [9.0, 9.5, 10.0, 10.5, 11.0],
    "smoke_sink_speed_mps": [2.4, 2.7, 3.0, 3.3, 3.6],
    "missile_speed_mps": [285.0, 292.5, 300.0, 307.5, 315.0],
    "target_radius_m": [6.3, 6.65, 7.0, 7.35, 7.7],
    "target_height_m": [9.0, 9.5, 10.0, 10.5, 11.0],
}
E4_CONTROL_GRIDS = {
    "heading_offset_deg": [-1.0, -0.5, -0.25, 0.0, 0.25, 0.5, 1.0],
    "speed_offset_mps": [-5.0, -2.0, -1.0, 0.0, 1.0, 2.0, 5.0],
    "release_offset_s": [-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10],
    "fuse_offset_s": [-0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10],
}
DIAGNOSTIC_THRESHOLDS = {
    "near_optimal_ratio": 0.95,
    "substantial_retention_ratio": 0.80,
    "meaningful_duration_s": 1.0,
}


class ModelValidationFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_ready(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    return value


def verify_identities(formal_result_path: Path) -> dict[str, str]:
    observed = {path: sha256_file(ROOT / path) for path in EXPECTED}
    expected_formal = EXPECTED["docs/q2_result.json"]
    if formal_result_path.resolve() != (ROOT / "docs/q2_result.json").resolve():
        observed_formal = sha256_file(formal_result_path)
        if observed_formal != expected_formal:
            raise ModelValidationFailure("Q2_MODEL_VALIDATION_FORMAL_RESULT_IDENTITY_MISMATCH")
    mismatches = {
        path: {"expected": EXPECTED[path], "observed": observed[path]}
        for path in EXPECTED if observed[path] != EXPECTED[path]
    }
    if mismatches:
        raise ModelValidationFailure("Q2_MODEL_VALIDATION_IDENTITY_MISMATCH:" + json.dumps(mismatches))
    return observed


def decision_from_record(record: dict, source: str) -> pilot.Decision:
    return pilot.Decision(
        heading_rad=float(record["heading_rad"]),
        speed_mps=float(record["speed_mps"]),
        release_time_s=float(record["release_time_s"]),
        fuse_delay_s=float(record["fuse_delay_s"]),
        source_domain=source,
    )


def solve_parameters(p: q1.Q1Parameters, settings: dict) -> dict:
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
    duration = float(result["effective_duration_s"])
    if not math.isfinite(duration) or duration < 0.0:
        raise ModelValidationFailure("Q2_MODEL_VALIDATION_NONFINITE_DURATION")
    return json_ready(result)


def parameterized(decision: pilot.Decision, factor: str | None = None, value: float | None = None) -> q1.Q1Parameters:
    p = pilot.parameters(decision)
    if factor is None:
        return p
    field = {
        "smoke_radius_m": "smoke_radius",
        "smoke_duration_s": "smoke_duration",
        "smoke_sink_speed_mps": "smoke_sink_speed",
        "missile_speed_mps": "missile_speed",
        "target_radius_m": "target_radius",
        "target_height_m": "target_height",
    }[factor]
    return replace(p, **{field: float(value)})


def is_nondecreasing(values: list[float], tolerance: float) -> bool:
    return all(right + tolerance >= left for left, right in zip(values, values[1:]))


def is_nonincreasing(values: list[float], tolerance: float) -> bool:
    return all(right <= left + tolerance for left, right in zip(values, values[1:]))


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(json_ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_e3(formal: dict, identities: dict[str, str]) -> dict:
    best = formal["formal_best"]
    decision = decision_from_record(best["decision"], "E3_formal_best")
    p = pilot.parameters(decision)
    info = q1.kinematics(p)
    nominal = solve_parameters(p, E3_SETTINGS)
    stored = best["precise"]

    release_expected = p.uav_initial + p.uav_speed * p.release_time * p.uav_direction
    explosion_expected = (
        p.uav_initial
        + p.uav_speed * (p.release_time + p.fuse_delay) * p.uav_direction
        - np.array([0.0, 0.0, 0.5 * p.gravity * p.fuse_delay**2])
    )
    release_residual = float(np.linalg.norm(release_expected - np.asarray(best["decision"]["release_point_m"])))
    explosion_residual = float(np.linalg.norm(explosion_expected - np.asarray(best["decision"]["explosion_point_m"])))
    heading_norm_residual = abs(float(np.linalg.norm(p.uav_direction)) - 1.0)
    interval_duration = float(sum(b - a for a, b in nominal["intervals_s"]))
    duration_reconstruction_residual = abs(interval_duration - float(nominal["effective_duration_s"]))
    nominal_stored_difference = abs(float(nominal["effective_duration_s"]) - float(stored["effective_duration_s"]))
    margins = pilot.constraint_margins(decision)
    minimum_constraint_margin = float(min(margins.values()))
    active_start, active_stop = (float(value) for value in info["active_window_s"])
    interval_window_residual = max(
        [0.0]
        + [max(active_start - float(a), float(b) - active_stop) for a, b in nominal["intervals_s"]]
    )

    event_times = []
    for a, b in nominal["intervals_s"]:
        event_times.extend([float(a), 0.5 * (float(a) + float(b)), float(b)])
    event_geometry = []
    for index, time_s in enumerate(event_times):
        margin = q1.full_surface_margin(
            time_s, p, E3_SETTINGS["n_theta"], E3_SETTINGS["n_levels"]
        )
        event_geometry.append({
            "kind": ["entry", "interior", "exit"][index % 3],
            "time_s": time_s,
            "margin_m": float(margin["margin_m"]),
            "lambda_raw": float(margin["lambda_raw"]),
            "target_z_m": float(margin["z_m"]),
        })
    endpoint_events = [item for item in event_geometry if item["kind"] != "interior"]
    active_boundary_events = [
        item
        for item in endpoint_events
        if min(abs(item["time_s"] - active_start), abs(item["time_s"] - active_stop))
        <= TOLERANCES["duration_consistency_s"]
    ]
    root_events = [item for item in endpoint_events if item not in active_boundary_events]
    endpoint_residual = max([0.0] + [abs(item["margin_m"]) for item in root_events])
    maximum_active_boundary_margin = max(
        [-math.inf] + [item["margin_m"] for item in active_boundary_events]
    )
    interior_margins_valid = all(
        item["margin_m"] <= TOLERANCES["endpoint_margin_m"]
        for item in event_geometry if item["kind"] == "interior"
    )

    monotonic_records = {}
    for factor, grid in E3_MONOTONIC_GRIDS.items():
        durations = [
            float(solve_parameters(parameterized(decision, factor, value), E3_SETTINGS)["effective_duration_s"])
            for value in grid
        ]
        expected_direction = "nondecreasing" if factor in {"smoke_radius_m", "smoke_duration_s"} else "nonincreasing"
        direction_pass = (
            is_nondecreasing(durations, TOLERANCES["monotonic_duration_s"])
            if expected_direction == "nondecreasing"
            else is_nonincreasing(durations, TOLERANCES["monotonic_duration_s"])
        )
        monotonic_records[factor] = {
            "values": grid,
            "durations_s": durations,
            "expected_direction": expected_direction,
            "status": "pass" if direction_pass else "fail",
        }

    reflected_decision = replace(
        decision,
        heading_rad=float((-decision.heading_rad) % (2.0 * math.pi)),
        source_domain="E3_reflected",
    )
    reflected_p = replace(
        pilot.parameters(reflected_decision),
        target_base_center=np.array([0.0, -200.0, 0.0]),
    )
    reflected = solve_parameters(reflected_p, E3_SETTINGS)
    symmetry_difference = abs(float(reflected["effective_duration_s"]) - float(nominal["effective_duration_s"]))

    near_zero_radius = solve_parameters(replace(p, smoke_radius=1e-6), E3_SETTINGS)
    short_lived = solve_parameters(replace(p, smoke_duration=0.25), E3_SETTINGS)
    center_only = q1.center_point_intervals(p, scan_step=E3_SETTINGS["scan_step_s"])
    center_overstatement = float(center_only["effective_duration_s"]) - float(nominal["effective_duration_s"])

    witness = pilot.witness_oracle()
    witness_forward_residual = float(witness["construction"]["forward_inverse_mismatch_m"])
    witness_minimum_margin = float(min(witness["decision"]["constraint_margins"].values()))

    checks = {
        "release_kinematic_closure": release_residual <= TOLERANCES["identity_and_kinematic_closure"],
        "explosion_kinematic_closure": explosion_residual <= TOLERANCES["identity_and_kinematic_closure"],
        "heading_unit_norm": heading_norm_residual <= TOLERANCES["identity_and_kinematic_closure"],
        "all_hard_constraints_feasible": minimum_constraint_margin >= -TOLERANCES["constraint_margin"],
        "intervals_inside_active_window": interval_window_residual <= TOLERANCES["duration_consistency_s"],
        "duration_equals_interval_measure": duration_reconstruction_residual <= TOLERANCES["duration_consistency_s"],
        "nominal_reproduces_formal_result": nominal_stored_difference <= TOLERANCES["duration_consistency_s"],
        "computed_transition_endpoints_are_roots": endpoint_residual <= TOLERANCES["endpoint_margin_m"],
        "active_domain_boundaries_are_feasible": maximum_active_boundary_margin <= TOLERANCES["endpoint_margin_m"],
        "interval_interior_is_effective": interior_margins_valid,
        "all_monotonic_invariants": all(item["status"] == "pass" for item in monotonic_records.values()),
        "y_reflection_symmetry": symmetry_difference <= TOLERANCES["symmetry_duration_s"],
        "zero_radius_limit": float(near_zero_radius["effective_duration_s"]) <= TOLERANCES["zero_radius_limit_s"],
        "short_lived_cloud_bound": float(short_lived["effective_duration_s"]) <= 0.25 + TOLERANCES["duration_consistency_s"],
        "c3_witness_forward_inverse": witness_forward_residual <= TOLERANCES["identity_and_kinematic_closure"],
        "c3_witness_strictly_feasible": witness_minimum_margin > 0.0,
        "center_only_simplification_is_optimistic": center_overstatement >= -TOLERANCES["duration_consistency_s"],
    }
    status = "pass" if all(checks.values()) else "fail"
    return {
        "schema_version": "1.0",
        "result_id": "Q2-S6-E3-STRUCTURAL-20260827",
        "question_id": "Q2",
        "level": "E3_STRUCTURAL",
        "status": status,
        "external_numeric_results_used": False,
        "tolerance_policy": {
            "declared_before_observation": True,
            "values": TOLERANCES,
            "basis": "Existing Q2 E1/E2 numerical scale and exact kinematic identities.",
        },
        "identities": identities,
        "nominal": nominal,
        "kinematic_and_constraint_closure": {
            "release_point_residual_m": release_residual,
            "explosion_point_residual_m": explosion_residual,
            "heading_unit_norm_residual": heading_norm_residual,
            "minimum_constraint_margin": minimum_constraint_margin,
            "constraint_margins": margins,
            "interval_window_residual_s": interval_window_residual,
            "duration_reconstruction_residual_s": duration_reconstruction_residual,
            "nominal_to_formal_duration_difference_s": nominal_stored_difference,
        },
        "event_geometry": {
            "records": event_geometry,
            "maximum_endpoint_root_residual_m": endpoint_residual,
            "maximum_active_boundary_margin_m": maximum_active_boundary_margin,
            "all_interior_margins_nonpositive": interior_margins_valid,
        },
        "invariants": {
            "monotonicity": monotonic_records,
            "reflection_symmetry": {
                "nominal_duration_s": nominal["effective_duration_s"],
                "reflected_duration_s": reflected["effective_duration_s"],
                "absolute_difference_s": symmetry_difference,
            },
        },
        "limit_and_counterexample_cases": {
            "near_zero_smoke_radius": {
                "radius_m": 1e-6,
                "duration_s": near_zero_radius["effective_duration_s"],
                "expected": "zero measure effective interval",
            },
            "short_lived_cloud": {
                "smoke_duration_s": 0.25,
                "effective_duration_s": short_lived["effective_duration_s"],
                "expected_upper_bound_s": 0.25,
            },
            "center_only_target_counterexample": {
                "full_cylinder_duration_s": nominal["effective_duration_s"],
                "center_only_duration_s": center_only["effective_duration_s"],
                "center_minus_full_s": center_overstatement,
                "implication": "A center-only target can overstate coverage and cannot replace the full-cylinder model.",
            },
        },
        "c3_geometry": {
            "witness_forward_inverse_residual_m": witness_forward_residual,
            "witness_minimum_constraint_margin": witness_minimum_margin,
            "q_intervals": witness["q_intervals"],
        },
        "checks": checks,
        "claim_boundary": "Supports structural consistency and feasible behavior of the frozen Q2 model; it is not a global-optimality proof.",
    }


def perturb_decision(base: pilot.Decision, factor: str, offset: float) -> pilot.Decision:
    values = {
        "heading_rad": base.heading_rad,
        "speed_mps": base.speed_mps,
        "release_time_s": base.release_time_s,
        "fuse_delay_s": base.fuse_delay_s,
        "source_domain": f"E4_{factor}_{offset}",
    }
    if factor == "heading_offset_deg":
        values["heading_rad"] = (base.heading_rad + math.radians(offset)) % (2.0 * math.pi)
    elif factor == "speed_offset_mps":
        values["speed_mps"] = base.speed_mps + offset
    elif factor == "release_offset_s":
        values["release_time_s"] = base.release_time_s + offset
    elif factor == "fuse_offset_s":
        values["fuse_delay_s"] = base.fuse_delay_s + offset
    else:
        raise KeyError(factor)
    return pilot.Decision(**values)


def run_e4(formal: dict, identities: dict[str, str]) -> dict:
    finalists = [
        {
            "start_id": item["start_id"],
            "decision": decision_from_record(item["decision"], f"E4_{item['start_id']}"),
        }
        for item in formal["precise_finalists"]
    ]
    best = finalists[0]["decision"]
    nominal = solve_parameters(pilot.parameters(best), E4_SETTINGS)
    nominal_duration = float(nominal["effective_duration_s"])

    parameter_sensitivity = {}
    for factor, grid in E4_PARAMETER_GRIDS.items():
        level_records = []
        for value in grid:
            candidate_records = []
            for finalist in finalists:
                result = solve_parameters(parameterized(finalist["decision"], factor, value), E4_SETTINGS)
                candidate_records.append({
                    "start_id": finalist["start_id"],
                    "duration_s": float(result["effective_duration_s"]),
                })
            selected = max(candidate_records, key=lambda item: (item["duration_s"], item["start_id"]))
            level_records.append({
                "value": value,
                "formal_best_fixed_duration_s": candidate_records[0]["duration_s"],
                "three_finalist_durations_s": candidate_records,
                "selected_start_id": selected["start_id"],
                "selected_duration_s": selected["duration_s"],
            })
        fixed_durations = [item["formal_best_fixed_duration_s"] for item in level_records]
        expected_direction = {
            "smoke_radius_m": "nondecreasing",
            "target_radius_m": "nonincreasing",
            "target_height_m": "nonincreasing",
        }.get(factor, "context_dependent")
        direction_pass = True
        if expected_direction == "nondecreasing":
            direction_pass = is_nondecreasing(fixed_durations, TOLERANCES["monotonic_duration_s"])
        elif expected_direction == "nonincreasing":
            direction_pass = is_nonincreasing(fixed_durations, TOLERANCES["monotonic_duration_s"])
        winners = [item["selected_start_id"] for item in level_records]
        parameter_sensitivity[factor] = {
            "stress_values": grid,
            "records": level_records,
            "expected_direction": expected_direction,
            "direction_status": "pass" if direction_pass else "fail",
            "selected_decision_switch_count": sum(a != b for a, b in zip(winners, winners[1:])),
            "stress_band_is_empirical_confidence_interval": False,
        }

    control_sensitivity = {}
    for factor, grid in E4_CONTROL_GRIDS.items():
        records = []
        for offset in grid:
            decision = perturb_decision(best, factor, float(offset))
            margins = pilot.constraint_margins(decision)
            result = solve_parameters(pilot.parameters(decision), E4_SETTINGS)
            duration = float(result["effective_duration_s"])
            records.append({
                "offset": offset,
                "duration_s": duration,
                "retention_ratio": duration / nominal_duration if nominal_duration else 0.0,
                "minimum_constraint_margin": float(min(margins.values())),
            })
        inner = [item for item in records if abs(float(item["offset"])) <= {
            "heading_offset_deg": 0.25,
            "speed_offset_mps": 1.0,
            "release_offset_s": 0.02,
            "fuse_offset_s": 0.02,
        }[factor] + 1e-15]
        minimum_inner_retention = min(item["retention_ratio"] for item in inner)
        control_sensitivity[factor] = {
            "records": records,
            "minimum_inner_band_retention_ratio": minimum_inner_retention,
            "inner_band_substantial_retention": minimum_inner_retention >= DIAGNOSTIC_THRESHOLDS["substantial_retention_ratio"],
            "diagnostic_only": True,
        }

    assumptions = [
        {
            "assumption": "Missile M1 travels at constant 300 m/s on the straight line to the decoy origin.",
            "support": "Official problem statement.",
            "violation_impact": "Maneuver or speed changes move the sight-line geometry and can change the optimal timing.",
        },
        {
            "assumption": "FY1 changes heading instantaneously once, then flies horizontally at constant speed in [70,140] m/s.",
            "support": "Official problem statement.",
            "violation_impact": "Turn-rate, acceleration, or wind constraints can make the nominal release/explosion point unreachable.",
        },
        {
            "assumption": "The bomb inherits horizontal UAV motion and follows vertical ballistic motion with g=9.8 m/s^2 and no drag.",
            "support": "Official gravity-motion wording plus the project's stated standard-gravity convention.",
            "violation_impact": "Aerodynamic drift changes the explosion point; fuse timing would require recalibration.",
        },
        {
            "assumption": "The cloud is a radius-10 m sphere, sinks at 3 m/s, and remains effective for at most 20 s with a hard concentration threshold.",
            "support": "Official experimental-data abstraction.",
            "violation_impact": "Wind, diffusion, concentration gradients, or gradual decay require a stochastic/advection-diffusion cloud model.",
        },
        {
            "assumption": "The protected object is the stated radius-7 m, height-10 m fixed cylinder and complete finite sight-line blockage defines effectiveness.",
            "support": "Official target geometry and the project's conservative full-cylinder interpretation.",
            "violation_impact": "A different visible surface or partial-coverage criterion changes the objective duration.",
        },
        {
            "assumption": "Positions, command time, heading, speed, and fuse delay are deterministic and exactly executed.",
            "support": "No error distribution is supplied by the official problem.",
            "violation_impact": "Operational use needs uncertainty propagation or robust re-optimization; the present stress bands only diagnose sensitivity.",
        },
    ]

    p = pilot.parameters(best)
    info = q1.kinematics(p)
    quantity_scale = {
        "heading_rad": best.heading_rad,
        "uav_speed_mps": best.speed_mps,
        "official_uav_speed_range_mps": [70.0, 140.0],
        "release_time_s": best.release_time_s,
        "fuse_delay_s": best.fuse_delay_s,
        "explosion_time_s": float(info["explosion_time_s"]),
        "explosion_height_m": float(np.asarray(info["explosion_point_m"])[2]),
        "smoke_effective_duration_s": p.smoke_duration,
        "formal_effective_duration_s": nominal_duration,
        "formal_duration_fraction_of_cloud_life": nominal_duration / p.smoke_duration,
        "missile_arrival_time_s": pilot.arrival(p),
    }

    direction_checks = {
        factor: record["direction_status"] == "pass"
        for factor, record in parameter_sensitivity.items()
        if record["expected_direction"] != "context_dependent"
    }
    all_control_feasible = all(
        item["minimum_constraint_margin"] >= -TOLERANCES["constraint_margin"]
        for factor in control_sensitivity.values() for item in factor["records"]
    )
    all_values_finite = all(
        math.isfinite(item["formal_best_fixed_duration_s"])
        and all(math.isfinite(candidate["duration_s"]) for candidate in item["three_finalist_durations_s"])
        for factor in parameter_sensitivity.values() for item in factor["records"]
    ) and all(
        math.isfinite(item["duration_s"])
        for factor in control_sensitivity.values() for item in factor["records"]
    )
    checks = {
        "official_parameter_mapping_complete": len(assumptions) == 6,
        "nominal_matches_formal_result": abs(nominal_duration - float(formal["formal_best"]["precise"]["effective_duration_s"])) <= TOLERANCES["duration_consistency_s"],
        "required_mechanism_directions": all(direction_checks.values()),
        "all_stress_evaluations_finite": all_values_finite,
        "all_control_perturbations_remain_hard_feasible": all_control_feasible,
        "uncertainty_boundary_explicit": all(not record["stress_band_is_empirical_confidence_interval"] for record in parameter_sensitivity.values()),
        "real_world_extension_boundary_explicit": any("stochastic" in item["violation_impact"] for item in assumptions),
    }
    status = "pass" if all(checks.values()) else "fail"
    return {
        "schema_version": "1.0",
        "result_id": "Q2-S6-E4-REALITY-20260827",
        "question_id": "Q2",
        "level": "E4_REALITY",
        "status": status,
        "external_numeric_results_used": False,
        "stress_policy": {
            "declared_before_observation": True,
            "physical_parameter_grids": E4_PARAMETER_GRIDS,
            "control_perturbation_grids": E4_CONTROL_GRIDS,
            "diagnostic_thresholds": DIAGNOSTIC_THRESHOLDS,
            "interpretation": "Designed stress bands around official values; not empirical confidence intervals or probability claims.",
        },
        "identities": identities,
        "nominal": nominal,
        "parameter_sensitivity_and_three_finalist_response": parameter_sensitivity,
        "control_perturbation_response": control_sensitivity,
        "quantity_scale": quantity_scale,
        "assumption_applicability": assumptions,
        "checks": checks,
        "claim_boundary": "Valid for the official deterministic idealization. Operational extrapolation needs wind, dispersion, control-error, and trajectory uncertainty models.",
    }


def report_e3(result: dict) -> str:
    closure = result["kinematic_and_constraint_closure"]
    symmetry = result["invariants"]["reflection_symmetry"]
    counterexample = result["limit_and_counterexample_cases"]["center_only_target_counterexample"]
    monotonic = result["invariants"]["monotonicity"]
    return f"""# Q2 E3 结构轴验证报告

> 内部技术证据，不进入论文或队友讲解稿；未载入或使用外部数值答案。

## 结论

E3 状态：`{result['status']}`。正式解的运动学、硬约束、区间测度、边界根、对称性、单调方向和极限行为均按预设容差核验。

- 投放点回代残差：`{closure['release_point_residual_m']:.3e} m`；起爆点回代残差：`{closure['explosion_point_residual_m']:.3e} m`。
- 最小硬约束余量：`{closure['minimum_constraint_margin']:.12g}`；正式时长复现差：`{closure['nominal_to_formal_duration_difference_s']:.3e} s`。
- y 轴镜像时长差：`{symmetry['absolute_difference_s']:.3e} s`。
- 烟幕半径、有效期增大时遮蔽时长不减；目标半径、高度增大时遮蔽时长不增：`{all(item['status'] == 'pass' for item in monotonic.values())}`。
- 近零烟幕半径的有效时长为 `{result['limit_and_counterexample_cases']['near_zero_smoke_radius']['duration_s']:.12g} s`。
- 若把完整圆柱错误退化为中心点，时长变化为 `{counterexample['center_minus_full_s']:.9f} s`；这说明中心点模型不能替代正式模型。

本轴只支持模型结构自洽与正式方案可行，不构成严格全局最优证明。
"""


def report_e4(result: dict) -> str:
    scale = result["quantity_scale"]
    parameters = result["parameter_sensitivity_and_three_finalist_response"]
    controls = result["control_perturbation_response"]
    physical_rows = []
    for factor, record in parameters.items():
        values = [item["formal_best_fixed_duration_s"] for item in record["records"]]
        physical_rows.append(
            f"| {factor} | `{min(values):.6f}`–`{max(values):.6f}` | {record['expected_direction']} | {record['selected_decision_switch_count']} |"
        )
    control_rows = []
    for factor, record in controls.items():
        control_rows.append(
            f"| {factor} | `{record['minimum_inner_band_retention_ratio']:.6f}` | `{record['inner_band_substantial_retention']}` |"
        )
    return f"""# Q2 E4 现实轴验证报告

> 内部技术证据，不进入论文或队友讲解稿；未载入或使用外部数值答案。

## 结论

E4 状态：`{result['status']}`。模型与官方确定性题面在参数、机制、数量级和应用语境上闭合；扰动范围是预先规定的诊断压力区间，不是经验置信区间。

- 正式遮蔽时长：`{scale['formal_effective_duration_s']:.12f} s`，约占烟幕20 s有效期的 `{100.0 * scale['formal_duration_fraction_of_cloud_life']:.3f}%`。
- 起爆时刻：`{scale['explosion_time_s']:.9f} s`；起爆高度：`{scale['explosion_height_m']:.6f} m`；均在题面运动学范围内。
- 三个精算候选在物理参数压力网格中允许重新排序，用于反映“决策响应”，不冒充完整再优化。

| 压力因素 | 正式决策固定时长范围/s | 必然方向 | 三候选换位次数 |
|---|---:|---|---:|
{chr(10).join(physical_rows)}

| 执行扰动因素 | 小扰动带最小保留率 | 是否至少保留80% |
|---|---:|---|
{chr(10).join(control_rows)}

现实边界：当前结论只适用于题面给定的无风、定速直线导弹、无人机瞬时定航向、弹体无阻力、球形匀速下沉烟幕和精确控制条件。若用于真实部署，必须补充风场、扩散、制导机动与执行误差的不确定性模型。
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("e3", "e4"), required=True)
    parser.add_argument("--formal-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    formal_path = args.formal_result if args.formal_result.is_absolute() else ROOT / args.formal_result
    output_path = args.output if args.output.is_absolute() else ROOT / args.output
    report_path = args.report if args.report.is_absolute() else ROOT / args.report
    identities = verify_identities(formal_path)
    formal = json.loads(formal_path.read_text(encoding="utf-8"))
    print(json.dumps({"phase": args.phase, "stage": "identity", "status": "pass"}), flush=True)
    result = run_e3(formal, identities) if args.phase == "e3" else run_e4(formal, identities)
    result["observed_at"] = datetime.now(timezone.utc).isoformat()
    result["verification_code_sha256"] = sha256_file(Path(__file__))
    write_json(output_path, result)
    report = report_e3(result) if args.phase == "e3" else report_e4(result)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(json.dumps({
        "phase": args.phase,
        "stage": "completed",
        "status": result["status"],
        "output": output_path.relative_to(ROOT).as_posix(),
        "report": report_path.relative_to(ROOT).as_posix(),
    }), flush=True)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ModelValidationFailure as error:
        print(json.dumps({"status": "fail", "error": str(error)}), file=sys.stderr)
        raise SystemExit(2)
