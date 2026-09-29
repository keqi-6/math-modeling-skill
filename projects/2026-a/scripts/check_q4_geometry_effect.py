"""Compare two Q4 geometries at matched times without solving a new trajectory.

The fixed-radius runs deliberately end at the shrinking main run's endpoint.
Failure to dry by that finite horizon is an admissible comparison outcome,
not a claim that the fixed-radius drying time has been calculated.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/Q4/geometry_effect_review.json"
TIMES = (172800, 183949)
GRIDS = (2560, 5120)
MATCHED = (
    "spec_sha256", "boundary_sha256", "raw_environment_sha256",
    "radius_json_sha256", "raw_radius_sha256", "solver_sha256",
    "scenario", "properties", "initial_temperature_C", "initial_moisture_kg_kg",
    "initial_radius_m", "rtol", "atol_temperature", "atol_moisture",
    "max_step_observed_s", "max_step_tail_s", "explicit_initial_step_s",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def demand(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_index(values: np.ndarray, target: int) -> int:
    found = np.flatnonzero(values == target)
    demand(found.size == 1, f"Expected one exact stored sample at {target} s")
    return int(found[0])


def load_case(n: int, geometry: str) -> tuple[dict, dict, list[dict]]:
    suffix = "v1-20260911" if geometry == "shrinking" else "fixedradius-geometry-20260911"
    path = ROOT / f"output/Q4/run_n{n}-{suffix}.npz"
    meta_path = path.with_suffix(".json")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    demand(meta["result_sha256"] == digest(path), f"Result identity mismatch: {path}")
    demand(meta["grid_n"] == n, "Grid identity mismatch")
    demand(meta["properties"] == "appendix4" and meta["scenario"] == "mean_tail", "Unmatched physics/input")
    demand(meta["solver_sha256"] == digest(ROOT / "src/Q4/solve.py"), "Solver identity changed")
    demand(meta["spec_sha256"] == digest(ROOT / "planning/Q4/model_spec.md"), "Specification identity changed")
    demand(meta["boundary_sha256"] == digest(ROOT / "output/ENV/q2_boundary.json"), "Environment identity changed")
    demand(meta["radius_json_sha256"] == digest(ROOT / "output/GEOMETRY/q4_radius.json"), "Radius input identity changed")
    demand(meta["comparison_complete"], "Requested comparison horizon not completed")
    demand(meta["status"] in ("computed_pending_independent_verification", "threshold_not_reached_within_horizon"),
           "Solver stopped with an inadmissible status")
    if not meta["drying_complete"]:
        demand(meta["status"] == "threshold_not_reached_within_horizon" and meta["n_end"] is None,
               "Finite-horizon status is inconsistent")
    expected_method = "linear" if geometry == "shrinking" else "constant"
    demand(meta["radius"]["method"] == expected_method, "Wrong geometry")
    demand(not meta["radius"]["continuation_used"], "Unexpected radius extrapolation")
    if geometry == "fixed":
        demand(meta["radius"]["constant_radius_m"] == 0.02, "Wrong fixed radius")
        demand(meta["common_end_s"] == TIMES[-1] and meta["work_limit_s"] == TIMES[-1], "Wrong fixed comparison horizon")

    rows = []
    with np.load(path, allow_pickle=False) as data:
        xi = np.asarray(data["mesh_xi"])
        demand(xi.shape == (n + 1,) and xi[0] == 0 and xi[-1] == 1, "Malformed material mesh")
        demand(np.all(np.diff(xi) > 0), "Material mesh is not strictly ordered")
        # Independent geometric weights: annular area divided by pi R(t)^2.
        faces = np.r_[0.0, (xi[:-1] + xi[1:]) / 2, 1.0]
        weights = np.diff(faces**2)
        demand(abs(float(weights.sum()) - 1.0) < 1e-14, "Area weights do not normalize")
        c_all, theta_all = data["moisture_snapshots"], data["temperature_snapshots"]
        demand(c_all.shape[1] == n + 1 and theta_all.shape == c_all.shape, "Snapshot dimensions mismatch")
        demand(np.isfinite(c_all).all() and np.isfinite(theta_all).all(), "Nonfinite full snapshot")
        demand(np.min(c_all) > 0 and np.min(theta_all) > -273.15, "Nonphysical full snapshot")
        initial = unique_index(data["snapshot_time_s"], 0)
        demand(np.all(c_all[initial] == 2.55) and np.all(theta_all[initial] == 28), "Initial state mismatch")
        for t in TIMES:
            si = unique_index(data["snapshot_time_s"], t)
            ti = unique_index(data["time_s"], t)
            c = c_all[si]
            radius = float(data["snapshot_radius_m"][si])
            demand(radius == float(data["surface_radius_m"][ti]), "Snapshot/sample radius mismatch")
            if geometry == "fixed":
                demand(radius == 0.02, "Fixed-radius snapshot moved")
            maximum = float(np.max(c))
            mean = float(np.sum(weights * c))
            max_residual = abs(maximum - float(data["max_moisture_kg_kg"][ti]))
            mean_residual = abs(mean - float(data["moisture_mean"][ti]))
            demand(max_residual <= 1e-12 and mean_residual <= 1e-12, "Independent observable reconstruction disagrees")
            rows.append(dict(grid_n=n, geometry=geometry, time_s=t, radius_m=radius,
                             max_moisture_kg_kg=maximum, max_node=int(np.argmax(c)),
                             normalized_cross_section_mean_kg_kg=mean,
                             strict_all_node_threshold=bool(maximum < 0.15),
                             max_reconstruction_residual=max_residual,
                             mean_reconstruction_residual=mean_residual))
        demand(int(data["time_s"][-1]) == meta["common_end_s"], "Stored horizon mismatch")
        if not meta["drying_complete"]:
            demand(not np.any(data["official_output_mask"]), "Incomplete drying marked as official output")
    source = dict(grid_n=n, geometry=geometry, result_path=path.relative_to(ROOT).as_posix(),
                  result_sha256=digest(path), metadata_path=meta_path.relative_to(ROOT).as_posix(),
                  metadata_sha256=digest(meta_path), solver_status=meta["status"],
                  drying_complete=meta["drying_complete"], comparison_complete=meta["comparison_complete"],
                  common_end_s=meta["common_end_s"], elapsed_s=meta["elapsed_s"])
    return meta, source, rows


def main() -> None:
    sources, observations, metadata = [], [], {}
    for n in GRIDS:
        for geometry in ("shrinking", "fixed"):
            meta, source, rows = load_case(n, geometry)
            sources.append(source)
            observations.extend(rows)
            metadata[n, geometry] = meta
        for field in MATCHED:
            demand(metadata[n, "shrinking"][field] == metadata[n, "fixed"][field], f"Unmatched setting: {field}")
    by_key = {(r["grid_n"], r["geometry"], r["time_s"]): r for r in observations}
    contrasts, grid_checks = [], []
    observables = ("max_moisture_kg_kg", "normalized_cross_section_mean_kg_kg")
    for t in TIMES:
        for metric in observables:
            effects = {}
            for n in GRIDS:
                shrinking = by_key[n, "shrinking", t][metric]
                fixed = by_key[n, "fixed", t][metric]
                effects[n] = fixed - shrinking
                contrasts.append(dict(time_s=t, grid_n=n, observable=metric,
                                      shrinking=shrinking, fixed=fixed,
                                      fixed_minus_shrinking=effects[n]))
            grid_changes = {g: abs(by_key[5120, g, t][metric] - by_key[2560, g, t][metric])
                            for g in ("shrinking", "fixed")}
            difference_change = abs(effects[5120] - effects[2560])
            change_sum = sum(grid_changes.values())
            grid_checks.append(dict(time_s=t, observable=metric,
                                    within_geometry_grid_changes=grid_changes,
                                    contrast_change_on_refinement=difference_change,
                                    comparison_numerical_change_sum=change_sum,
                                    contrast_sign_consistent=bool(effects[2560] * effects[5120] > 0),
                                    effect_to_grid_change_sum=(abs(effects[5120]) / change_sum if change_sum else None),
                                    relative_contrast_change=(difference_change / abs(effects[5120]) if effects[5120] else None)))
    report = dict(schema_version="1.0", question="Q4", role="auxiliary_matched_geometry_comparison",
                  status="comparison_data_verified", script_sha256=digest(Path(__file__)),
                  design=dict(times_s=list(TIMES), grids=list(GRIDS), changed_input="radius history only",
                              shrinking="all original observed R(t), piecewise linear",
                              fixed="R(t) = R0 = 0.02 m", properties="appendix4", environment="mean_tail",
                              comparison_end_s=TIMES[-1], fixed_drying_time_requested=False,
                              matching_fields=list(MATCHED),
                              observable_scope="all material nodes at the two exact stored snapshots",
                              mean_definition="sum_i (xi_face_right^2-xi_face_left^2) C_i = 2 sum_i v_i C_i",
                              time_discretization_note="same BDF tolerances and step limits; adaptive steps and geometry-dependent knot segmentation need not coincide"),
                  sources=sources, observations=observations, contrasts=contrasts, grid_comparisons=grid_checks,
                  limitations=["Two-grid differences are observed numerical changes, not certified continuum error bounds.",
                               "The normalized cross-section mean is not a measured total water mass or a dry-solid-mass-weighted mean.",
                               "This matched appendix4 contrast isolates geometry within the adopted model; it does not isolate the complete Q3-to-Q4 difference.",
                               "No fixed-radius final drying time, physical accuracy, or shrinkage-parameter sensitivity is inferred."])
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=OUT.relative_to(ROOT).as_posix(), contrasts=contrasts,
                          grid_comparisons=grid_checks), ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
