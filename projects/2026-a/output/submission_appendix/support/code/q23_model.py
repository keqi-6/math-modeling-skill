"""Q2/Q3: local coupled properties and a full-domain drying criterion."""
from __future__ import annotations
import math
import time
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.sparse import coo_matrix
from common import Boundary, RadiusInput, save_result

R,H,HM=0.02,25.0,8e-7
INITIAL_T,INITIAL_C,THRESHOLD=28.0,2.55,0.15
OBSERVED_END=14400
SUMMARY_TIMES=(1800,3600,5400,7200,9000,10800)
MAX_EXCEL_DATA_ROWS=1048575
SAMPLE_BLOCK=64

class System:
    """Interleaved (theta_0,C_0,...,theta_N,C_N), with no diagnostic states."""

    def __init__(self, n, boundary):
        if isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)) or n < 1:
            raise ValueError("N must be a positive integer")
        self.n, self.boundary = int(n), boundary
        self.r = np.linspace(0.0, R, self.n + 1)
        self.dr = R / self.n
        faces = (self.r[:-1] + self.r[1:]) / 2
        self.v = np.diff(np.r_[0.0, faces, R] ** 2) / 2
        self.q = faces / self.dr
        self.h, self.hm = H, HM
        self.size = 2 * (self.n + 1)

    def split(self, y):
        y = np.asarray(y)
        if y.shape != (self.size,) or not np.isfinite(y).all():
            raise ValueError("Invalid joint-state shape or nonfinite value")
        theta, c = y[0::2], y[1::2]
        # Real-part checks permit an infinitesimal complex-step oracle without
        # modifying the analytic formulas. Production integration uses float64.
        if np.any(c.real <= 0) or np.any(theta.real <= -273.15):
            raise ValueError("Nonpositive moisture or absolute temperature; no clipping")
        return theta, c

    @staticmethod
    def coefficients(theta, c):
        rho = 650.0 + 128.0 * c
        cp = 1450.0 + 2736.0 * c / (1.0 + c)
        k = 0.21 + 0.38 * c / (1.0 + c)
        d = 2.4e-3 * np.exp(-0.45 / c - 3850.0 / (theta + 273.15))
        return dict(rho=rho, cp=cp, s=rho * cp, k=k, D=d,
                    s_C=128.0 * cp + rho * 2736.0 / (1.0 + c)**2,
                    k_C=0.38 / (1.0 + c)**2,
                    D_C=0.45 * d / c**2,
                    D_T=3850.0 * d / (theta + 273.15)**2)

    def powers(self, t, theta, c, p):
        dtype = np.result_type(theta, c, float)
        ft = np.empty(self.n + 2, dtype=dtype)
        fc = np.empty(self.n + 2, dtype=dtype)
        ft[0] = fc[0] = 0
        ft[1:-1] = self.q * (p["k"][:-1] + p["k"][1:]) / 2 * np.diff(theta)
        fc[1:-1] = self.q * (p["D"][:-1] + p["D"][1:]) / 2 * np.diff(c)
        t_air, c_eq = self.boundary.evaluate(t)
        ft[-1] = R * self.h * (t_air - theta[-1])
        fc[-1] = R * self.hm * (c_eq - c[-1])
        return np.diff(ft), np.diff(fc)

    def rhs(self, t, y):
        theta, c = self.split(y)
        p = self.coefficients(theta, c)
        qt, qc = self.powers(t, theta, c, p)
        out = np.empty(self.size, dtype=np.result_type(y, float))
        out[0::2] = qt / (self.v * p["s"])
        out[1::2] = qc / self.v
        return out

    def jac(self, t, y):
        theta, c = self.split(y)
        p = self.coefficients(theta, c)
        dt, dc = np.diff(theta), np.diff(c)
        kb = (p["k"][:-1] + p["k"][1:]) / 2
        db = (p["D"][:-1] + p["D"][1:]) / 2
        # Each column is the derivative with respect to theta_i,C_i,theta_j,C_j.
        jt = self.q[:, None] * np.column_stack(
            (-kb, p["k_C"][:-1] * dt / 2, kb, p["k_C"][1:] * dt / 2))
        jc = self.q[:, None] * np.column_stack(
            (p["D_T"][:-1] * dc / 2, p["D_C"][:-1] * dc / 2 - db,
             p["D_T"][1:] * dc / 2, p["D_C"][1:] * dc / 2 + db))
        i = np.arange(self.n)
        cols_face = 2 * i[:, None] + np.arange(4)[None, :]
        rows, cols, vals = [], [], []
        for offset, face_jac, weights in ((0, jt, self.v * p["s"]), (1, jc, self.v)):
            for shift, sign in ((0, 1), (1, -1)):
                nodes = i + shift
                rows.append(np.repeat(2 * nodes + offset, 4))
                cols.append(cols_face.ravel())
                vals.append((sign * face_jac / weights[nodes, None]).ravel())
        qt, _ = self.powers(t, theta, c, p)
        theta_dot = qt / (self.v * p["s"])
        nodes = np.arange(self.n + 1)
        rows.extend([2 * nodes, np.array([2 * self.n, 2 * self.n + 1])])
        cols.extend([2 * nodes + 1, np.array([2 * self.n, 2 * self.n + 1])])
        vals.extend([-p["s_C"] / p["s"] * theta_dot,
                     np.array([-R * self.h / (self.v[-1] * p["s"][-1]),
                               -R * self.hm / self.v[-1]])])
        return coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                          shape=(self.size, self.size)).tocsc()


class Recorder:
    """Only short dense blocks, output columns, and selected full states live here."""

    def __init__(self, system, boundary):
        self.system = system
        self.output_nodes = np.arange(21) * (system.n // 20)
        self.temperature, self.moisture = [], []
        self.maxima, self.argmax = [], []
        self.t_mean, self.c_mean = [], []
        self.last_time = -1
        self.last_state = None
        self.snapshots, self.roles = {}, {}
        self.n_end = None
        self.extrema = dict(temperature_min_C=float("inf"), temperature_max_C=-float("inf"),
                            moisture_min_kg_kg=float("inf"), moisture_max_kg_kg=-float("inf"))
        self.bounds = dict(temperature_min_C=min(INITIAL_T, float(boundary.temperature.min()), boundary.tail[0]),
                           temperature_max_C=max(INITIAL_T, float(boundary.temperature.max()), boundary.tail[0]),
                           moisture_min_kg_kg=min(INITIAL_C, float(boundary.moisture.min()), boundary.tail[1]),
                           moisture_max_kg_kg=max(INITIAL_C, float(boundary.moisture.max()), boundary.tail[1]))
        self.allowances = dict(temperature_C=1e-7, moisture_kg_kg=1e-8)
        self.fixed_roles = {0: "initial", OBSERVED_END: "observed_end"}
        self.fixed_roles.update({t: f"summary_{t}s" for t in SUMMARY_TIMES})

    def inspect(self, states):
        a = np.asarray(states)
        if not np.isfinite(a).all() or np.any(a[1::2] <= 0) or np.any(a[0::2] <= -273.15):
            raise RuntimeError("Accepted solution contains nonfinite or nonphysical values")
        for field, values, allowance in (("temperature", a[0::2], 1e-7),
                                         ("moisture", a[1::2], 1e-8)):
            suffix = "C" if field == "temperature" else "kg_kg"
            low, high = f"{field}_min_{suffix}", f"{field}_max_{suffix}"
            self.extrema[low] = min(self.extrema[low], float(values.min()))
            self.extrema[high] = max(self.extrema[high], float(values.max()))
            if values.min() < self.bounds[low] - allowance or values.max() > self.bounds[high] + allowance:
                raise RuntimeError(f"Accepted {field} exceeds the stated invariant-range allowance")

    def snapshot(self, t, y, role):
        self.snapshots[float(t)] = np.asarray(y, dtype=float).copy()
        self.roles[role] = float(t)

    def append(self, times, states):
        times = np.asarray(times, dtype=np.int64)
        if times.size == 0:
            return
        if not np.array_equal(times, np.arange(self.last_time + 1, self.last_time + 1 + len(times))):
            raise RuntimeError("Missing, repeated, or unordered integer output sample")
        self.inspect(states)
        theta, c = states[0::2], states[1::2]
        maxima = c.max(axis=0)
        if self.n_end is None:
            below = np.flatnonzero((times > 0) & (maxima < THRESHOLD))
            if below.size:
                j = int(below[0])
                self.n_end = int(times[j])
                preceding = states[:, j - 1] if j else self.last_state
                if preceding is None or np.max(preceding[1::2]) < THRESHOLD:
                    raise RuntimeError("Cannot establish the first strict integer threshold sample")
                self.snapshot(self.n_end - 1, preceding, "before_n_end")
                self.snapshot(self.n_end, states[:, j], "n_end")
        for j, t in enumerate(times):
            if int(t) in self.fixed_roles:
                self.snapshot(t, states[:, j], self.fixed_roles[int(t)])
        self.temperature.append(theta[self.output_nodes].T.copy())
        self.moisture.append(c[self.output_nodes].T.copy())
        self.maxima.append(maxima.copy())
        self.argmax.append(c.argmax(axis=0).astype(np.int64))
        self.t_mean.append(2 / R**2 * (self.system.v @ theta))
        self.c_mean.append(2 / R**2 * (self.system.v @ c))
        self.last_time, self.last_state = int(times[-1]), states[:, -1].copy()

    def finish(self):
        self.snapshot(self.last_time, self.last_state, "common_end")
        snapshot_times = sorted(self.snapshots)
        snapshots = np.asarray([self.snapshots[t] for t in snapshot_times])
        nodes = np.concatenate(self.argmax)
        payload = dict(time_s=np.arange(self.last_time + 1, dtype=np.int64),
                       radius_m=self.system.r[self.output_nodes].copy(),
                       mesh_radius_m=self.system.r.copy(),
                       temperature_C=np.concatenate(self.temperature),
                       moisture_kg_kg=np.concatenate(self.moisture),
                       max_moisture_kg_kg=np.concatenate(self.maxima),
                       max_moisture_node=nodes,
                       max_moisture_radius_m=self.system.r[nodes],
                       temperature_mean=np.concatenate(self.t_mean),
                       moisture_mean=np.concatenate(self.c_mean),
                       snapshot_time_s=np.asarray(snapshot_times),
                       temperature_snapshots=snapshots[:, 0::2],
                       moisture_snapshots=snapshots[:, 1::2])
        return payload, {role: snapshot_times.index(t) for role, t in self.roles.items()}


def solve(n, boundary, *, tight=False, common_end_s=None, max_time_s=MAX_EXCEL_DATA_ROWS):
    """Return (NPZ payload, run diagnostics); caller owns persistence and acceptance."""
    if isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)) or n < 20 or n % 20:
        raise ValueError("Production N must be a positive multiple of 20")
    for name, value in (("common_end_s", common_end_s), ("max_time_s", max_time_s)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1):
            raise ValueError(f"{name} must be a positive integer")
    if max_time_s < OBSERVED_END or (common_end_s is not None and common_end_s > max_time_s):
        raise ValueError("Work limit cannot cover the requested output interval")
    started = time.perf_counter()
    system = System(n, boundary)
    recorder = Recorder(system, boundary)
    y = np.tile([INITIAL_T, INITIAL_C], n + 1)
    recorder.append([0], y[:, None])
    factor = 0.1 if tight else 1.0
    rtol, atol_t, atol_c = 2e-9 * factor, 2e-9 * factor, 2e-11 * factor
    atol = np.tile([atol_t, atol_c], n + 1)
    step_observed, step_tail = (2.5, 150.0) if tight else (5.0, 300.0)
    t, crossing = 0.0, None
    work = dict(nfev=0, njev=0, nlu=0, accepted_steps=0, segments=0)

    def event(_t, state):
        return float(np.max(state[1::2]) - THRESHOLD)

    event.direction, event.terminal = -1, True
    try:
        while True:
            if recorder.n_end is not None:
                target = max(recorder.n_end, common_end_s or 0, OBSERVED_END)
                if t >= target:
                    break
            elif crossing is not None:
                target = max(math.ceil(crossing), math.floor(t) + 1)
            else:
                target = max_time_s
            if t >= max_time_s:
                raise RuntimeError("Work/Excel-row limit reached before completing the strict endpoint; not a drying-time answer")
            if t < OBSERVED_END:
                end = min((math.floor(t / 60) + 1) * 60, target, max_time_s)
                system.boundary = boundary
                max_step = step_observed
            else:
                end = min(t + 3600, target, max_time_s)
                system.boundary = boundary.right_side()
                max_step = step_tail
            if end <= t:
                raise RuntimeError("Integration interval failed to advance")
            sol = solve_ivp(system.rhs, (t, end), y, method="BDF", jac=system.jac,
                            rtol=rtol, atol=atol, max_step=max_step,
                            first_step=min(1e-3, end - t) if t == 0 else None,
                            dense_output=True, events=event if crossing is None else None)
            for key in ("nfev", "njev", "nlu"):
                work[key] += int(getattr(sol, key))
            work["segments"] += 1
            work["accepted_steps"] += len(sol.t) - 1
            if not sol.success:
                raise RuntimeError(f"BDF failed after t={t}: {sol.message}")
            recorder.inspect(sol.y)
            stop = float(sol.t[-1])
            last_integer = math.floor(stop)
            for first in range(recorder.last_time + 1, last_integer + 1, SAMPLE_BLOCK):
                samples = np.arange(first, min(first + SAMPLE_BLOCK, last_integer + 1), dtype=np.int64)
                recorder.append(samples, sol.sol(samples))
            if crossing is None and len(sol.t_events[0]):
                crossing = float(sol.t_events[0][0])
                recorder.snapshot(crossing, sol.y_events[0][0], "threshold_crossing")
                print(f"Threshold crossing: t={crossing:.9f} s, N={n}", flush=True)
            t, y = stop, sol.y[:, -1].copy()
            if work["segments"] % 60 == 0 or crossing is not None:
                print(f"N={n} {boundary.scenario}: t={t:.3f} s, max C={np.max(y[1::2]):.9g}", flush=True)
        if crossing is None or recorder.n_end is None or recorder.last_time != int(t):
            raise RuntimeError("Incomplete event or integer endpoint contract")
        if recorder.n_end > MAX_EXCEL_DATA_ROWS:
            raise RuntimeError("Dense sampled trajectory exceeds the configured sample limit")
        payload, roles = recorder.finish()
        diagnostics = dict(success=True, status="computed",
                           grid_n=int(n), scenario=boundary.scenario, tight=bool(tight),
                           t_cross_s=crossing, n_end=recorder.n_end,
                           common_end_s=recorder.last_time, requested_common_end_s=common_end_s,
                           rtol=rtol, atol_temperature=atol_t, atol_moisture=atol_c,
                           max_step_observed_s=step_observed, max_step_tail_s=step_tail,
                           explicit_initial_step_s=1e-3,
                           output_sample_block_size=SAMPLE_BLOCK, tail_segment_s=3600,
                           work_limit_s=max_time_s, threshold_kg_kg=THRESHOLD,
                           snapshot_roles=roles, observed_extrema=recorder.extrema,
                           extrema_scope="all nodes at accepted steps and integer-second dense samples",
                           invariant_bounds=recorder.bounds, invariant_allowances=recorder.allowances,
                           work=work, elapsed_s=time.perf_counter() - started)
        return payload, diagnostics
    except Exception as exc:
        exc.q2_diagnostics = dict(success=False, status="failed", grid_n=int(n),
                                 scenario=boundary.scenario, tight=bool(tight),
                                 failure_type=type(exc).__name__, failure_message=str(exc),
                                 last_complete_segment_time_s=t, last_output_time_s=recorder.last_time,
                                 t_cross_s=crossing, n_end=recorder.n_end,
                                 observed_extrema=recorder.extrema, work=work,
                                 elapsed_s=time.perf_counter() - started)
        raise


def run(n, output, data, *, tight=False, scenario="mean_tail"):
    boundary=Boundary(Path(data)/"附件1.xlsx",scenario)
    payload,metadata=solve(n,boundary,tight=tight)
    return save_result(output,"q23",payload,metadata)
