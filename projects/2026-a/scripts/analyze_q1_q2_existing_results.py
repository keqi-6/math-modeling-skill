"""Compare saved Q1/Q2 fields and evaluate appendix-3 local properties.

This bounded post-processing step does not import or execute either solver.
The common observation grid supports a comparison of the two complete
parameterizations, not an attribution to one parameter or coupling term.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output/diagnostics/q1_q2_parameterization_review.json"
INPUTS = {
    "q1_fields": ("output/Q1/run_n5120.npz",
                  "c3eb65e2b2f1ccea870986401c5f1ae42346562be1fe11ace3e61104dc79cc7e"),
    "q2_fields": ("output/Q2/run_n10240_startsafe.npz",
                  "79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b"),
    "q1_boundary": ("output/ENV/q1_boundary.json",
                    "4c80135753189b839bcbe3ccc667a65118364a07471135695180fe7e8c6f923d"),
    "q2_boundary": ("output/ENV/q2_boundary.json",
                    "f30996b8fc3a132164ae1a8b688f683bd15120fa38d54155221d8839085f178f"),
}
FIELDS = {"temperature_C": "degC", "moisture_kg_kg": "kg water/kg dry matter"}
PROPERTY_TIMES = (0, 1800, 3600, 5400, 7200, 9000, 10800)


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def read_fields(path: Path, end_s: int) -> dict[str, np.ndarray]:
    with np.load(path, allow_pickle=False) as saved:
        times = saved["time_s"]
        radius = saved["radius_m"]
        if not np.array_equal(times[:end_s + 1], np.arange(end_s + 1)):
            raise ValueError(f"Missing or reordered integer-second observations: {path}")
        if radius.shape != (21,) or not np.allclose(
                radius, np.linspace(0, 0.02, 21), rtol=0, atol=2e-16):
            raise ValueError(f"Unexpected physical observation radii: {path}")
        result = {"time_s": times[:end_s + 1].copy(), "radius_m": radius.copy()}
        for key in FIELDS:
            array = saved[key]
            if array.shape != (times.size, 21):
                raise ValueError(f"Field shape differs from saved observation axes: {key}")
            result[key] = array[:end_s + 1].copy()
            if not np.isfinite(result[key]).all():
                raise ValueError(f"Nonfinite observations: {key}")
    if np.any(result["moisture_kg_kg"] <= 0) or np.any(result["temperature_C"] <= -273.15):
        raise ValueError("Saved observations leave the material-property domain")
    for key, initial in (("temperature_C", 28.0), ("moisture_kg_kg", 2.55)):
        if not np.allclose(result[key][0], initial, rtol=0, atol=1e-13):
            raise ValueError(f"Unexpected initial state: {key}")
    return result


def material_properties(temperature: float, moisture: float) -> dict[str, float]:
    """Evaluate the original appendix-3 formulas at one saved local state."""
    density = 650 + 128 * moisture
    heat_capacity = 1450 + 2736 * moisture / (1 + moisture)
    return {
        "k_W_mK": 0.21 + 0.38 * moisture / (1 + moisture),
        "s_J_m3K": density * heat_capacity,
        "D_m2_s": float(2.4e-3 * np.exp(-0.45 / moisture - 3850 / (temperature + 273.15))),
    }


def main() -> None:
    sources = {}
    for role, (relative, expected) in INPUTS.items():
        observed = sha256(ROOT / relative)
        if observed != expected:
            raise ValueError(f"Source identity changed: {relative}")
        sources[role] = {"path": relative, "sha256": observed}

    b1 = json.loads((ROOT / INPUTS["q1_boundary"][0]).read_text(encoding="utf-8"))
    b2 = json.loads((ROOT / INPUTS["q2_boundary"][0]).read_text(encoding="utf-8"))
    for key in ("time_s", "temperature_C", "air_moisture_kg_kg"):
        first = np.asarray([node[key] for node in b1["nodes"]])
        second = np.asarray(b2[key])[:31]
        if first.shape != (31,) or not np.array_equal(first, second):
            raise ValueError(f"The two early boundary inputs differ: {key}")
    if not np.array_equal(b2["time_s"][:31], np.arange(0, 1801, 60)):
        raise ValueError("Unexpected early environment observation times")
    if b1["interpolation"] != "piecewise_linear" or b2["interpolation"] != "piecewise_linear":
        raise ValueError("The two environment reconstructions do not match")

    q1 = read_fields(ROOT / INPUTS["q1_fields"][0], 1800)
    q2 = read_fields(ROOT / INPUTS["q2_fields"][0], 10800)
    if not np.allclose(q1["radius_m"], q2["radius_m"], rtol=0, atol=2e-16):
        raise ValueError("The two field observation grids do not coincide")

    comparisons = {}
    endpoint = []
    for key, unit in FIELDS.items():
        first, second = q1[key], q2[key][:1801]
        difference = second - first
        row, col = np.unravel_index(np.argmax(np.abs(difference)), difference.shape)
        comparisons[key] = {
            "unit": unit,
            "max_absolute_difference": float(abs(difference[row, col])),
            "at_time_s": int(row), "at_radius_m": float(q1["radius_m"][col]),
            "q1_value": float(first[row, col]), "q2_value": float(second[row, col]),
            "signed_q2_minus_q1": float(difference[row, col]),
        }
        for index, position in ((0, "center"), (20, "surface")):
            endpoint.append({
                "field": key, "unit": unit, "time_s": 1800, "position": position,
                "radius_m": float(q1["radius_m"][index]),
                "q1_value": float(first[1800, index]),
                "q2_value": float(second[1800, index]),
                "signed_q2_minus_q1": float(difference[1800, index]),
            })

    initial_properties = material_properties(28.0, 2.55)
    properties = []
    for time_s in PROPERTY_TIMES:
        for index, position in ((0, "center"), (20, "surface")):
            temperature = float(q2["temperature_C"][time_s, index])
            moisture = float(q2["moisture_kg_kg"][time_s, index])
            coefficients = material_properties(temperature, moisture)
            properties.append({
                "time_s": time_s, "position": position,
                "radius_m": float(q2["radius_m"][index]),
                "temperature_C": temperature, "moisture_kg_kg": moisture,
                **coefficients,
                "ratio_to_initial": {key: value / initial_properties[key]
                                     for key, value in coefficients.items()},
            })

    report = {
        "schema_version": "1.0",
        "purpose": "Internal post-processing evidence for self-contained Q1/Q2 explanations",
        "method": "Read existing unrounded observations; evaluate appendix-3 formulas directly",
        "solver_executed": False,
        "sources": sources,
        "script": {"path": Path(__file__).relative_to(ROOT).as_posix(),
                   "sha256": sha256(Path(__file__))},
        "alignment": {
            "same_first_31_environment_nodes": True,
            "same_piecewise_linear_reconstruction": True,
            "same_uniform_initial_state": True,
            "physical_radius_alignment_tolerance_m": 2e-16,
            "maximum_radius_roundoff_difference_m": float(np.max(np.abs(
                q1["radius_m"] - q2["radius_m"]))),
        },
        "q1_q2_comparison": {
            "range_s": [0, 1800], "time_spacing_s": 1,
            "radius_range_m": [0, 0.02], "radius_spacing_m": 0.001,
            "observations_per_field": 1801 * 21,
            "difference_direction": "Q2 minus Q1",
            "maxima": comparisons, "endpoint_comparisons": endpoint,
            "interpretation_limit": (
                "Comparison of complete appendix-2 and appendix-3 parameterizations on their "
                "respective accepted grids. It does not isolate one coefficient/coupling effect, "
                "validate against internal measurements, or designate either question as truth."
            ),
        },
        "q2_local_properties": {
            "formula_source": "Original problem appendix 3",
            "formulas": {
                "rho": "650+128*C", "cp": "1450+2736*C/(1+C)",
                "k": "0.21+0.38*C/(1+C)", "s": "rho*cp",
                "D": "2.4e-3*exp(-0.45/C-3850/(temperature_C+273.15))",
            },
            "initial_properties": initial_properties, "rows": properties,
            "interpretation_limit": "Local states at the specified times and two endpoint radii only",
        },
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({"output": OUTPUT.relative_to(ROOT).as_posix(),
                      "maxima": comparisons, "property_rows": len(properties)},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
