"""Q4: local coupled diffusion on an observed shrinking material domain."""
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
OBSERVED_END,RADIUS_OBSERVED_END=14400,259200
SAMPLE_INTERVAL,SUMMARY_INTERVAL,SAMPLE_BLOCK=60,21600,64
MAX_MODEL_TIME=RADIUS_OBSERVED_END
MAX_EXCEL_DATA_ROWS=1048575

class System:
    """Interleaved (theta_0,C_0,...,theta_N,C_N), with no diagnostic states."""

    def __init__(self, n, boundary, radius, properties="appendix4"):
        if isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)) or n < 1:
            raise ValueError("N must be a positive integer")
        if properties not in ("appendix3", "appendix4"):
            raise ValueError("Unknown empirical-property appendix")
        self.n, self.boundary, self.radius = int(n), boundary, radius
        self.properties = properties
        self.xi = np.linspace(0.0, 1.0, self.n + 1)
        self.dx = 1.0 / self.n
        faces = (self.xi[:-1] + self.xi[1:]) / 2
        self.v = np.diff(np.r_[0.0, faces, 1.0] ** 2) / 2
        self.q = faces / self.dx
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

    def r_at(self, t):
        return self.radius.evaluate(t) * self.xi

    def coefficients(self, theta, c):
        if self.properties == "appendix4":
            rho0, rho1, cp0, cp1, k0, k1, d0, beta = 760., 90., 1850., 2150., .12, .20, 4.2e-4, .30
        else:
            rho0, rho1, cp0, cp1, k0, k1, d0, beta = 650., 128., 1450., 2736., .21, .38, 2.4e-3, .45
        rho = rho0 + rho1 * c
        cp = cp0 + cp1 * c / (1.0 + c)
        k = k0 + k1 * c / (1.0 + c)
        d = d0 * np.exp(-beta / c - 3850.0 / (theta + 273.15))
        return dict(rho=rho, cp=cp, s=rho * cp, k=k, D=d,
                    s_C=rho1 * cp + rho * cp1 / (1.0 + c)**2,
                    k_C=k1 / (1.0 + c)**2, D_C=beta * d / c**2,
                    D_T=3850.0 * d / (theta + 273.15)**2)

    def powers(self, t, theta, c, p):
        radius = self.radius.evaluate(t)
        dtype = np.result_type(theta, c, float)
        ft = np.empty(self.n + 2, dtype=dtype)
        fc = np.empty(self.n + 2, dtype=dtype)
        ft[0] = fc[0] = 0
        ft[1:-1] = self.q / radius**2 * (p["k"][:-1] + p["k"][1:]) / 2 * np.diff(theta)
        fc[1:-1] = self.q / radius**2 * (p["D"][:-1] + p["D"][1:]) / 2 * np.diff(c)
        t_air, c_eq = self.boundary.evaluate(t)
        ft[-1] = self.h / radius * (t_air - theta[-1])
        fc[-1] = self.hm / radius * (c_eq - c[-1])
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
        radius = self.radius.evaluate(t)
        theta, c = self.split(y)
        p = self.coefficients(theta, c)
        dt, dc = np.diff(theta), np.diff(c)
        kb = (p["k"][:-1] + p["k"][1:]) / 2
        db = (p["D"][:-1] + p["D"][1:]) / 2
        # Each column is the derivative with respect to theta_i,C_i,theta_j,C_j.
        jt = self.q[:, None] / radius**2 * np.column_stack(
            (-kb, p["k_C"][:-1] * dt / 2, kb, p["k_C"][1:] * dt / 2))
        jc = self.q[:, None] / radius**2 * np.column_stack(
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
                     np.array([-self.h / radius / (self.v[-1] * p["s"][-1]),
                               -self.hm / radius / self.v[-1]])])
        return coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                          shape=(self.size, self.size)).tocsc()


class Recorder:
    """Minute physical-radius samples plus complete material-grid key states."""

    def __init__(self, system, boundary):
        self.system = system
        self.output_r = np.arange(21, dtype=float) * 0.001
        self.samples, self.snapshots, self.roles = {}, {}, {}
        self.last_regular_time = -SAMPLE_INTERVAL
        self.n_end = None
        self.endpoint_check = None
        self.extrema = dict(temperature_min_C=float("inf"), temperature_max_C=-float("inf"),
                            moisture_min_kg_kg=float("inf"), moisture_max_kg_kg=-float("inf"))
        self.bounds = dict(temperature_min_C=min(INITIAL_T, float(boundary.temperature.min()), boundary.tail[0]),
                           temperature_max_C=max(INITIAL_T, float(boundary.temperature.max()), boundary.tail[0]),
                           moisture_min_kg_kg=min(INITIAL_C, float(boundary.moisture.min()), boundary.tail[1]),
                           moisture_max_kg_kg=max(INITIAL_C, float(boundary.moisture.max()), boundary.tail[1]))
        self.allowances = dict(temperature_C=1e-7, moisture_kg_kg=1e-8)

    def inspect(self, states):
        a = np.asarray(states)
        if not np.isfinite(a).all() or np.any(a[1::2] <= 0) or np.any(a[0::2] <= -273.15):
            raise RuntimeError("Accepted solution contains nonfinite/nonphysical values")
        for field, values, allowance in (("temperature", a[0::2], self.allowances["temperature_C"]),
                                         ("moisture", a[1::2], self.allowances["moisture_kg_kg"])):
            suffix = "C" if field == "temperature" else "kg_kg"
            low, high = f"{field}_min_{suffix}", f"{field}_max_{suffix}"
            self.extrema[low] = min(self.extrema[low], float(values.min()))
            self.extrema[high] = max(self.extrema[high], float(values.max()))
            if values.min() < self.bounds[low] - allowance or values.max() > self.bounds[high] + allowance:
                raise RuntimeError(f"Accepted {field} exceeds the invariant-range allowance")

    def snapshot(self, t, y, role):
        self.inspect(y)
        self.snapshots[float(t)] = np.asarray(y, dtype=float).copy()
        self.roles[role] = float(t)

    def project(self, t, y):
        """Interpolate only points inside the current material; surface is separate."""
        self.inspect(y)
        theta, c = np.asarray(y)[0::2], np.asarray(y)[1::2]
        rad = self.system.radius.evaluate(t)
        # This tolerance only handles binary arithmetic equality at a surface.
        eps = 16 * np.finfo(float).eps * max(R, rad)
        mask = self.output_r <= rad + eps
        x = np.minimum(self.output_r[mask] / rad, 1.0)
        out_t, out_c = np.full(21, np.nan), np.full(21, np.nan)
        out_t[mask] = np.interp(x, self.system.xi, theta)
        out_c[mask] = np.interp(x, self.system.xi, c)
        argmax = int(np.argmax(c))
        return dict(temperature=out_t, moisture=out_c, inside=mask,
                    surface_radius=rad, surface_temperature=float(theta[-1]),
                    surface_moisture=float(c[-1]), maximum=float(c[argmax]),
                    argmax=argmax, max_radius=float(rad * self.system.xi[argmax]),
                    temperature_mean=float(2 * (self.system.v @ theta)),
                    moisture_mean=float(2 * (self.system.v @ c)))

    def append_regular(self, times, states):
        times = np.asarray(times, dtype=np.int64)
        if times.size == 0:
            return
        expected = self.last_regular_time + SAMPLE_INTERVAL * np.arange(1, len(times) + 1)
        if not np.array_equal(times, expected):
            raise RuntimeError("Missing, repeated, or unordered 60-second sample")
        if states.shape != (self.system.size, len(times)):
            raise ValueError("Invalid regular-sample state array")
        self.inspect(states)
        for j, t in enumerate(times):
            y = states[:, j]
            self.samples[int(t)] = self.project(t, y)
            if t == 0:
                self.snapshot(t, y, "initial")
            if t == OBSERVED_END:
                self.snapshot(t, y, "environment_observed_end")
            if t == RADIUS_OBSERVED_END:
                self.snapshot(t, y, "radius_observed_end")
            if t > 0 and t % SUMMARY_INTERVAL == 0:
                self.snapshot(t, y, f"summary_{t}s")
        self.last_regular_time = int(times[-1])

    def accept_endpoint(self, t, y, preceding):
        if t < 1 or np.max(y[1::2]) >= THRESHOLD or np.max(preceding[1::2]) < THRESHOLD:
            raise RuntimeError("Cannot establish the first strict integer-second endpoint")
        self.n_end = int(t)
        before_node, after_node = int(np.argmax(preceding[1::2])), int(np.argmax(y[1::2]))
        self.endpoint_check = dict(
            before_time_s=int(t - 1), before_max_moisture_kg_kg=float(preceding[1::2][before_node]),
            before_max_node=before_node, before_max_radius_m=float(self.system.r_at(t - 1)[before_node]),
            end_time_s=int(t), end_max_moisture_kg_kg=float(y[1::2][after_node]),
            end_max_node=after_node, end_max_radius_m=float(self.system.r_at(t)[after_node]),
            scope="unrounded all-node values of this numerical run; cross-grid integer stability is not asserted")
        self.snapshot(t - 1, preceding, "before_n_end")
        self.snapshot(t, y, "n_end")
        self.samples[int(t)] = self.project(t, y)

    def finish(self, end, y):
        if int(end) != end:
            raise RuntimeError("Final record requires an integer common endpoint")
        self.snapshot(end, y, "common_end" if self.n_end is not None else "horizon_end")
        self.samples[int(end)] = self.project(end, y)
        times = np.asarray(sorted(self.samples), dtype=np.int64)
        entries = [self.samples[int(t)] for t in times]
        snapshot_times = sorted(self.snapshots)
        snapshots = np.asarray([self.snapshots[t] for t in snapshot_times])
        def field(name, dtype=float):
            return np.asarray([e[name] for e in entries], dtype=dtype)
        payload = dict(
            time_s=times, radius_m=self.output_r.copy(), mesh_xi=self.system.xi.copy(),
            temperature_C=field("temperature"), moisture_kg_kg=field("moisture"),
            inside_mask=field("inside", bool), surface_radius_m=field("surface_radius"),
            surface_temperature_C=field("surface_temperature"), surface_moisture_kg_kg=field("surface_moisture"),
            max_moisture_kg_kg=field("maximum"), max_moisture_node=field("argmax", np.int64),
            max_moisture_radius_m=field("max_radius"), temperature_mean=field("temperature_mean"),
            moisture_mean=field("moisture_mean"),
            official_output_mask=((times > 0) & (times <= self.n_end) &
                                  ((times % SAMPLE_INTERVAL == 0) | (times == self.n_end))) if self.n_end is not None
                                 else np.zeros(times.shape, dtype=bool),
            snapshot_time_s=np.asarray(snapshot_times, dtype=float),
            snapshot_radius_m=self.system.radius.evaluate(np.asarray(snapshot_times)),
            temperature_snapshots=snapshots[:, 0::2], moisture_snapshots=snapshots[:, 1::2])
        roles = {role: snapshot_times.index(t) for role, t in self.roles.items()}
        return payload, roles


def solve(n, boundary, radius, *, properties="appendix4", tight=False,
          common_end_s=None, max_time_s=MAX_MODEL_TIME):
    """Return unrounded data and diagnostics, without declaring independent acceptance.

    Event localization uses max over ALL material-grid nodes. Only minute output
    samples and endpoint-neighbor probes are projected/stored, never every full
    grid at every second. Accepted BDF states and all dense samples are inspected.
    """
    if isinstance(n, (bool, np.bool_)) or not isinstance(n, (int, np.integer)) or n < 20 or n % 20:
        raise ValueError("Production N must be a positive multiple of 20")
    for name, value in (("common_end_s", common_end_s), ("max_time_s", max_time_s)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, np.integer)) or value < 1):
            raise ValueError(f"{name} must be a positive integer")
    if max_time_s < OBSERVED_END or (common_end_s is not None and common_end_s > max_time_s):
        raise ValueError("Work ceiling cannot cover the requested comparison interval")
    if max(float(boundary.moisture.max()), boundary.tail[1]) >= THRESHOLD:
        raise ValueError("This first-crossing endpoint contract requires all g(t) < the threshold")
    started = time.perf_counter()
    system = System(n, boundary, radius, properties)
    recorder = Recorder(system, boundary)
    y0 = np.tile([INITIAL_T, INITIAL_C], n + 1)
    y = y0.copy()
    recorder.append_regular([0], y[:, None])
    factor = 0.1 if tight else 1.0
    rtol, atol_t, atol_c = 2e-9 * factor, 2e-9 * factor, 2e-11 * factor
    atol = np.tile([atol_t, atol_c], n + 1)
    step_observed, step_tail = (2.5, 150.0) if tight else (5.0, 300.0)
    knots = np.unique(np.r_[boundary.times[1:], radius.breakpoints_s])
    t, crossing = 0.0, None
    previous_dense = None
    horizon_stop_reason = None
    next_candidate, preceding_candidate = None, None
    work = dict(nfev=0, njev=0, nlu=0, accepted_steps=0, segments=0)

    def event(_t, state):
        return float(np.max(state[1::2]) - THRESHOLD)
    event.direction, event.terminal = -1, True

    try:
        while True:
            if recorder.n_end is not None:
                target = max(recorder.n_end, common_end_s or 0, math.ceil(t))
                if t >= target:
                    break
            elif crossing is not None:
                target = max(next_candidate, math.floor(t) + 1)
            else:
                target = max_time_s
            if t >= max_time_s:
                horizon_stop_reason = "explicit_model_time_limit"
                break
            if (radius.method != "constant" and radius.tail == "error" and t >= RADIUS_OBSERVED_END):
                horizon_stop_reason = "radius_observation_limit_without_continuation"
                break
            ix = int(np.searchsorted(knots, t, side="right"))
            next_knot = float(knots[ix]) if ix < len(knots) else float("inf")
            end = min(next_knot, t + 3600, target, max_time_s)
            if radius.method != "constant" and radius.tail == "error":
                end = min(end, RADIUS_OBSERVED_END)
            if end <= t:
                raise RuntimeError("Integration interval failed to advance")
            system.boundary = boundary if t < OBSERVED_END else boundary.right_side()
            max_step = step_observed if t < OBSERVED_END else step_tail
            start = t
            sol = solve_ivp(system.rhs, (start, end), y, method="BDF", jac=system.jac,
                            rtol=rtol, atol=atol, max_step=max_step,
                            first_step=min(1e-3, end - start) if start == 0 else None,
                            dense_output=True, events=event if crossing is None else None)
            for key in ("nfev", "njev", "nlu"):
                work[key] += int(getattr(sol, key))
            work["segments"] += 1
            work["accepted_steps"] += len(sol.t) - 1
            if not sol.success:
                raise RuntimeError(f"BDF failed after t={start}: {sol.message}")
            recorder.inspect(sol.y)
            stop = float(sol.t[-1])
            last_regular = SAMPLE_INTERVAL * math.floor(stop / SAMPLE_INTERVAL)
            for first in range(recorder.last_regular_time + SAMPLE_INTERVAL, last_regular + 1,
                               SAMPLE_INTERVAL * SAMPLE_BLOCK):
                sample_times = np.arange(first, min(first + SAMPLE_INTERVAL * SAMPLE_BLOCK,
                                                    last_regular + SAMPLE_INTERVAL), SAMPLE_INTERVAL,
                                         dtype=np.int64)
                recorder.append_regular(sample_times, sol.sol(sample_times))

            def state_at_when_available(instant):
                # Never extrapolate a dense polynomial across an input knot.
                if start <= instant <= stop:
                    value = np.asarray(sol.sol(instant), dtype=float)
                elif previous_dense is not None and previous_dense[0] <= instant <= previous_dense[1]:
                    value = np.asarray(previous_dense[2](instant), dtype=float)
                elif instant == 0:
                    value = y0.copy()
                else:
                    raise RuntimeError("Required endpoint-neighbor state lies outside retained dense intervals")
                recorder.inspect(value)
                return value

            new_crossing = crossing is None and len(sol.t_events[0]) > 0
            if new_crossing:
                crossing = float(sol.t_events[0][0])
                recorder.snapshot(crossing, sol.y_events[0][0], "threshold_crossing")
                next_candidate = max(1, math.floor(crossing))
                preceding_candidate = state_at_when_available(next_candidate - 1)
                if np.max(preceding_candidate[1::2]) < THRESHOLD:
                    raise RuntimeError("Numerical event follows an already strict preceding integer; refine the event check")
                print(f"Threshold crossing: t={crossing:.9f} s, N={n}", flush=True)
            if crossing is not None and recorder.n_end is None:
                while next_candidate <= math.floor(stop):
                    candidate_state = state_at_when_available(next_candidate)
                    if np.max(candidate_state[1::2]) < THRESHOLD:
                        recorder.accept_endpoint(next_candidate, candidate_state, preceding_candidate)
                        break
                    preceding_candidate = candidate_state
                    next_candidate += 1
            # This view keeps only one previous interval; older dense coefficients
            # are released. It supports a crossing exactly at an input knot.
            previous_dense = (start, stop, sol.sol)
            t, y = stop, sol.y[:, -1].copy()
            if work["segments"] % 60 == 0 or new_crossing:
                print(f"Q4 N={n} {boundary.scenario}/{radius.method}/{properties}: "
                      f"t={t:.3f} s, R={radius.evaluate(t):.8f} m, max C={np.max(y[1::2]):.9g}", flush=True)
        if int(t) != t:
            raise RuntimeError("Final modeled horizon is not an integer second")
        drying_complete = crossing is not None and recorder.n_end is not None
        comparison_complete = common_end_s is None or t >= common_end_s
        complete = drying_complete and comparison_complete
        expected_minutes = np.arange(0, SAMPLE_INTERVAL * math.floor(t / SAMPLE_INTERVAL) + 1,
                                     SAMPLE_INTERVAL, dtype=np.int64)
        if any(int(instant) not in recorder.samples for instant in expected_minutes):
            raise RuntimeError("Missing a required minute sample")
        payload, roles = recorder.finish(t, y)
        if not complete:
            payload["official_output_mask"][:] = False
        if int(payload["official_output_mask"].sum()) > MAX_EXCEL_DATA_ROWS:
            raise RuntimeError("The result4 time table exceeds one Excel worksheet")
        diagnostics = dict(success=bool(complete),
                           status=("computed" if complete
                                   else "threshold_not_reached_within_horizon" if not drying_complete
                                   else "comparison_horizon_not_completed"),
                           drying_complete=bool(drying_complete), comparison_complete=bool(comparison_complete),
                           horizon_stop_reason=horizon_stop_reason,
                           final_max_moisture_kg_kg=float(np.max(y[1::2])),
                           final_max_moisture_radius_m=float(system.r_at(t)[np.argmax(y[1::2])]),
                           grid_n=int(n), scenario=boundary.scenario, properties=properties,
                           initial_temperature_C=INITIAL_T, initial_moisture_kg_kg=INITIAL_C,
                           initial_radius_m=float(radius.evaluate(0)),
                           radius=radius.describe(t), tight=bool(tight),
                           t_cross_s=crossing, n_end=recorder.n_end, common_end_s=int(t),
                           requested_common_end_s=common_end_s,
                           crossing_within_radius_observations=bool(crossing <= RADIUS_OBSERVED_END) if crossing is not None else None,
                           strict_endpoint_within_radius_observations=bool(recorder.n_end <= RADIUS_OBSERVED_END) if recorder.n_end is not None else None,
                           rtol=rtol, atol_temperature=atol_t, atol_moisture=atol_c,
                           max_step_observed_s=step_observed, max_step_tail_s=step_tail,
                           explicit_initial_step_s=1e-3, output_interval_s=SAMPLE_INTERVAL,
                           output_sample_block_size=SAMPLE_BLOCK, tail_segment_max_s=3600,
                           work_limit_s=max_time_s, threshold_kg_kg=THRESHOLD,
                           snapshot_roles=roles, endpoint_check=recorder.endpoint_check,
                           observed_extrema=recorder.extrema,
                           extrema_scope="all material nodes at accepted BDF steps, 60-second dense samples, "
                                         "event/neighbor probes, and selected complete snapshots; not a continuum bound",
                           invariant_bounds=recorder.bounds, invariant_allowances=recorder.allowances,
                           output_domain="fixed physical radii; NaN with inside_mask=false outside the material; "
                                         "moving surface is an independent column",
                           work=work, elapsed_s=time.perf_counter() - started)
        return payload, diagnostics
    except Exception as exc:
        exc.q4_diagnostics = dict(success=False, status="failed", grid_n=int(n),
                                 scenario=boundary.scenario, properties=properties,
                                 radius=radius.describe(t), tight=bool(tight),
                                 failure_type=type(exc).__name__, failure_message=str(exc),
                                 last_complete_segment_time_s=t,
                                 last_regular_output_time_s=recorder.last_regular_time,
                                 t_cross_s=crossing, n_end=recorder.n_end,
                                 observed_extrema=recorder.extrema, work=work,
                                 elapsed_s=time.perf_counter() - started)
        raise


def run(n, output, data, *, tight=False, scenario="mean_tail",radius_method="linear"):
    boundary=Boundary(Path(data)/"附件1.xlsx",scenario)
    radius=RadiusInput(Path(data)/"附件2.xlsx",method=radius_method)
    payload,metadata=solve(n,boundary,radius,tight=tight)
    if not metadata["success"]:
        raise RuntimeError("Drying criterion not reached within the radius observations")
    return save_result(output,"q4",payload,metadata)
