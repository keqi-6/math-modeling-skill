"""Q1-v1 cylindrical finite-volume model; unrounded output and provenance.

Input: frozen 31-node environment JSON. Output: NPZ plus JSON run metadata.
The model and tolerances are defined in planning/Q1/model_spec.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from pathlib import Path

import numpy as np
import scipy
from scipy.integrate import solve_ivp
from scipy.sparse import coo_matrix

ROOT = Path(__file__).resolve().parents[2]
R = 0.02
RHO, CP, K, H, HM = 820.0, 2600.0, 0.36, 25.0, 8e-7
SPEC_SHA256 = "c9aa1d7771b729e4659a6ae7d92bf5523b3fefca4ea28c95630ed62dd350285a"
BOUNDARY_SHA256 = "4c80135753189b839bcbe3ccc667a65118364a07471135695180fe7e8c6f923d"
SNAPSHOT_TIMES = np.array([0, 1, 60, 1800], dtype=int)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Boundary:
    """Strict frozen-input reader, with interpolation only on the valid interval."""

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.sha256 = sha256(self.path)
        if self.sha256 != BOUNDARY_SHA256:
            raise ValueError("Environment identity differs from the frozen Q1 interface")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.times = np.array([x["time_s"] for x in data["nodes"]], dtype=float)
        self.temperature = np.array([x["temperature_C"] for x in data["nodes"]])
        self.moisture = np.array([x["air_moisture_kg_kg"] for x in data["nodes"]])
        if not np.array_equal(self.times, np.arange(0, 1801, 60)):
            raise ValueError("Expected exactly 31 original boundary nodes")
        if not np.isfinite([self.temperature, self.moisture]).all():
            raise ValueError("Nonfinite environment values")
        if data["interpolation"] != "piecewise_linear" or data["extrapolation"] != "error":
            raise ValueError("Unsupported interpolation contract")
        source = ROOT / data["source"]["path"]
        if sha256(source) != data["source"]["sha256"]:
            raise ValueError("Original environment workbook identity changed")

    def evaluate(self, t):
        if not np.isfinite(t) or t < 0 or t > 1800:
            raise ValueError("Environment query outside [0,1800] seconds")
        return (float(np.interp(t, self.times, self.temperature)),
                float(np.interp(t, self.times, self.moisture)))


class FieldSystem:
    """N+1 physical nodes and one diagnostic integrated boundary-flux state."""

    def __init__(self, n, field, boundary, constant_diffusivity=False):
        if not isinstance(n, (int, np.integer)) or n < 20 or n % 20:
            raise ValueError("N must be a positive multiple of 20")
        if field not in ("temperature", "moisture"):
            raise ValueError("Unknown field")
        self.n, self.field, self.boundary = n, field, boundary
        self.constant_diffusivity = constant_diffusivity
        self.r = np.linspace(0, R, n + 1)
        self.dr = R / n
        faces = (self.r[:-1] + self.r[1:]) / 2
        edges = np.r_[0.0, faces, R]
        self.v = np.diff(edges**2) / 2
        self.q = faces / self.dr
        self.capacity = RHO * CP if field == "temperature" else 1.0
        self.transfer = H if field == "temperature" else HM
        self.initial = 28.0 if field == "temperature" else 2.55

    def coefficients(self, u):
        if not np.isfinite(u).all():
            raise ValueError("Nonfinite field state")
        if self.field == "temperature":
            return np.full_like(u, K), np.zeros_like(u)
        if np.any(u <= 0):
            raise ValueError("Nonpositive moisture state; clipping is forbidden")
        if self.constant_diffusivity:
            return np.full_like(u, 7e-9 * np.exp(-0.89 / 2.55)), np.zeros_like(u)
        d = 7e-9 * np.exp(-0.89 / u)
        return d, 0.89 * d / u**2

    def rhs(self, t, y):
        u = y[:-1]
        d, _ = self.coefficients(u)
        g = self.boundary.evaluate(t)[0 if self.field == "temperature" else 1]
        flux = np.empty(self.n + 2)
        flux[0] = 0.0
        flux[1:-1] = self.q * (d[:-1] + d[1:]) / 2 * np.diff(u)
        flux[-1] = R * self.transfer * (g - u[-1])
        return np.r_[np.diff(flux) / (self.capacity * self.v), flux[-1]]

    def jac(self, t, y):
        u = y[:-1]
        d, dp = self.coefficients(u)
        delta = np.diff(u)
        dbar = (d[:-1] + d[1:]) / 2
        a = self.q * (0.5 * dp[:-1] * delta - dbar)
        b = self.q * (0.5 * dp[1:] * delta + dbar)
        weights = self.capacity * self.v
        ix = np.arange(self.n)
        rows = np.r_[ix, ix, ix + 1, ix + 1, self.n, self.n + 1]
        cols = np.r_[ix, ix + 1, ix, ix + 1, self.n, self.n]
        vals = np.r_[a / weights[:-1], b / weights[:-1],
                     -a / weights[1:], -b / weights[1:],
                     -R * self.transfer / weights[-1], -R * self.transfer]
        return coo_matrix((vals, (rows, cols)), shape=(self.n + 2, self.n + 2)).tocsc()


def solve_field(n, field, boundary, rtol=2e-9, atol_scale=1.0,
                constant_diffusivity=False):
    started = time.perf_counter()
    system = FieldSystem(n, field, boundary, constant_diffusivity)
    y = np.r_[np.full(n + 1, system.initial), 0.0]
    index = np.arange(21) * (n // 20)
    values = np.empty((1801, 21))
    mean = np.empty(1801)
    integral = np.empty(1801)
    snapshots = np.empty((4, n + 1))
    integral_snapshots = np.empty(4)
    values[0], mean[0], integral[0] = system.initial, system.initial, 0.0
    snapshots[0], integral_snapshots[0] = y[:-1], y[-1]
    base_atol = (2e-9 if field == "temperature" else 2e-11) * atol_scale
    atol = np.r_[np.full(n + 1, base_atol), base_atol * system.capacity * R**2 / 2]
    nfev = njev = nlu = 0
    for a in range(0, 1800, 60):
        sample_times = np.arange(a + 1, a + 61)
        sol = solve_ivp(system.rhs, (a, a + 60), y, method="BDF", jac=system.jac,
                        rtol=rtol, atol=atol, max_step=5.0, t_eval=sample_times)
        if not sol.success or sol.y.shape != (n + 2, 60):
            raise RuntimeError(f"{field} N={n}, interval {a}: {sol.message}")
        if not np.isfinite(sol.y).all() or (field == "moisture" and np.any(sol.y[:-1] <= 0)):
            raise RuntimeError("Invalid solution; no successful output will be written")
        values[sample_times] = sol.y[index].T
        mean[sample_times] = 2 / R**2 * (system.v @ sol.y[:-1])
        integral[sample_times] = sol.y[-1]
        for j, t in enumerate(SNAPSHOT_TIMES[1:], 1):
            if a < t <= a + 60:
                snapshots[j] = sol.y[:-1, t - a - 1]
                integral_snapshots[j] = sol.y[-1, t - a - 1]
        y = sol.y[:, -1]
        nfev += sol.nfev
        njev += sol.njev
        nlu += sol.nlu
    return dict(values=values, mean=mean, integral=integral, snapshots=snapshots,
                integral_snapshots=integral_snapshots, n=n, nfev=nfev, njev=njev,
                nlu=nlu, elapsed_s=time.perf_counter()-started)


def run_case(n, boundary, output, rtol=2e-9, atol_scale=1.0):
    output = Path(output)
    meta_path = output.with_suffix(".json")
    if output.exists() or meta_path.exists():
        raise FileExistsError("Choose a new run path; existing runs are not overwritten")
    spec_path = ROOT / "planning/Q1/model_spec.md"
    if sha256(spec_path) != SPEC_SHA256:
        raise ValueError("Frozen model specification changed")
    fields = {}
    for name in ("temperature", "moisture"):
        print(f"Solving {name}, N={n}, rtol={rtol:g}", flush=True)
        fields[name] = solve_field(n, name, boundary, rtol, atol_scale)
    payload = dict(time_s=np.arange(1801), radius_m=np.linspace(0,R,21),
                   mesh_radius_m=np.linspace(0,R,n+1), snapshot_time_s=SNAPSHOT_TIMES,
                   temperature_C=fields["temperature"]["values"],
                   moisture_kg_kg=fields["moisture"]["values"])
    for name, result in fields.items():
        for key in ("mean", "integral", "snapshots", "integral_snapshots"):
            payload[f"{name}_{key}"] = result[key]
    meta = dict(schema_version="1.0", question="Q1", specification="Q1-v1",
                spec_sha256=SPEC_SHA256, boundary_sha256=boundary.sha256,
                solver_sha256=sha256(__file__), n=n, rtol=rtol, atol_scale=atol_scale,
                atol_temperature=2e-9*atol_scale, atol_moisture=2e-11*atol_scale,
                max_step_s=5.0, method="nodal_finite_volume_segmented_BDF",
                python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                status="computed_pending_independent_verification",
                fields={name:{k:r[k] for k in ("nfev","njev","nlu","elapsed_s")}
                        for name,r in fields.items()})
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, **payload)
    meta["result_sha256"] = sha256(output)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(dict(output=str(output), n=n, fields=meta["fields"])), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--n", type=int, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--boundary", type=Path, default=ROOT/"output/ENV/q1_boundary.json")
    p.add_argument("--rtol", type=float, default=2e-9)
    p.add_argument("--atol-scale", type=float, default=1.0)
    args = p.parse_args()
    run_case(args.n, Boundary(args.boundary), args.output, args.rtol, args.atol_scale)


if __name__ == "__main__":
    main()
