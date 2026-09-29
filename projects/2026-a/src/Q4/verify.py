"""Q4 independent verifier draft; modes execute distinct evidence responsibilities.

This source is prepared in TEMP only and has not been imported or run. Runtime
routing must authorize each selected axis. No missing result can block a mode
that does not depend on that result, and no mode launches the production solver.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import traceback
import tempfile

import numpy as np
from scipy.integrate import solve_ivp

OBS_END, RAD_END, H, HM, LIMIT = 14400, 259200, 25., 8e-7, .15
Q2_SOLVER_SHA = "ad7eaf29c960bd00b1937cebb64507de952a4185b767dfeb50a31d89d72cb5ce"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module_at(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Evidence:
    def __init__(self, axes):
        self.axes, self.checks, self.details, self.identities = axes, [], {}, {}

    def check(self, axis, name, passed, observed=None, target=None, note=None):
        if axis not in self.axes:
            raise RuntimeError("Attempt to execute an evidence axis outside the requested route")
        self.checks.append(dict(axis=axis, id=name, passed=bool(passed), observed=observed,
                                target=target, note=note))

    def close(self, axis, name, actual, expected, *, atol=1e-12, rtol=1e-10, note=None):
        a, b = np.asarray(actual), np.asarray(expected)
        error = float(np.max(np.abs(a - b)))
        self.check(axis, name, bool(np.isfinite(a).all() and np.isfinite(b).all()
                                   and np.allclose(a, b, atol=atol, rtol=rtol)),
                   dict(max_abs_difference=error if np.isfinite(error) else None), dict(atol=atol, rtol=rtol), note)

    def guard(self, axis, name, function):
        try:
            function()
        except Exception as exc:
            self.check(axis, name, False, dict(type=type(exc).__name__, message=str(exc)))
            self.details[name + "_exception"] = traceback.format_exc(limit=5)

    def identity(self, path):
        path = Path(path).resolve()
        value = digest(path)
        self.identities[str(path)] = value
        return value


class ConstantBoundary:
    def __init__(self, theta=42., moisture=.05):
        self.theta, self.moisture = theta, moisture
    def evaluate(self, t):
        return self.theta, self.moisture


class AnalyticRadius:
    """Independent smooth geometric fixture, not production input reconstruction."""
    def __init__(self, duration=120., constant=False):
        self.duration, self.constant = duration, constant
    def evaluate(self, t):
        return .02 if self.constant else .02 * (1 - .15 * np.asarray(t) / self.duration)


def physical_coefficients(theta, c, appendix="appendix4"):
    """Independent literal empirical formulas; never calls production coefficients."""
    theta, c = np.asarray(theta), np.asarray(c)
    if appendix == "appendix4":
        density = 760 + 90 * c
        heat_capacity = 1850 + 2150 * c / (1 + c)
        conductivity = .12 + .20 * c / (1 + c)
        diffusivity = .00042 * np.exp(-.30 / c) * np.exp(-3850 / (theta + 273.15))
    elif appendix == "appendix3":
        density = 650 + 128 * c
        heat_capacity = 1450 + 2736 * c / (1 + c)
        conductivity = .21 + .38 * c / (1 + c)
        diffusivity = .0024 * np.exp(-.45 / c) * np.exp(-3850 / (theta + 273.15))
    else:
        raise ValueError("Unknown empirical appendix")
    return density * heat_capacity, conductivity, diffusivity


def independent_volumes(n, radius=1.):
    weights = []
    for i in range(n + 1):
        lower = max(0., (i - .5) * radius / n)
        upper = min(radius, (i + .5) * radius / n)
        weights.append((upper * upper - lower * lower) / 2)
    return np.asarray(weights)


def independent_rhs(t, y, n, boundary, radius, appendix="appendix4"):
    """Physical-volume, scalar shared-face loop, independent of ξ-scaled assembly."""
    rad = float(radius.evaluate(t))
    theta, c = np.asarray(y)[0::2], np.asarray(y)[1::2]
    storage, k, d = physical_coefficients(theta, c, appendix)
    volume = independent_volumes(n, rad)
    ht, hc = np.zeros(n + 1), np.zeros(n + 1)
    for i in range(n):
        face_r = (i + .5) * rad / n
        face_distance = rad / n
        kt = (k[i] + k[i + 1]) / 2
        dc = (d[i] + d[i + 1]) / 2
        flow_t = face_r * kt * (theta[i + 1] - theta[i]) / face_distance
        flow_c = face_r * dc * (c[i + 1] - c[i]) / face_distance
        ht[i] += flow_t
        ht[i + 1] -= flow_t
        hc[i] += flow_c
        hc[i + 1] -= flow_c
    ambient, equilibrium = boundary.evaluate(t)
    ht[-1] += rad * H * (ambient - theta[-1])
    hc[-1] += rad * HM * (equilibrium - c[-1])
    result = np.empty(2 * (n + 1))
    result[0::2], result[1::2] = ht / (volume * storage), hc / volume
    return result


def implementation_checks(m, boundary, radius, evidence, q2_path):
    n = 7
    x = np.arange(n + 1) / n
    y = np.empty(2 * (n + 1))
    y[0::2], y[1::2] = 31 + 15 * x**2, 2.1 - 1.2 * x**2
    for appendix in ("appendix4", "appendix3"):
        system = m.System(n, boundary, radius, properties=appendix)
        for t in (900., 21600.):
            f = system.rhs(t, y)
            ref = independent_rhs(t, y, n, boundary, radius, appendix)
            evidence.close("E1", f"face_loop_{appendix}_{int(t)}s", f, ref, atol=2e-13, rtol=2e-11)
            analytic = system.jac(t, y).toarray()
            numerical = np.empty_like(analytic)
            for j in range(len(y)):
                perturbed = y.astype(complex)
                perturbed[j] += 1j * 1e-25
                numerical[:, j] = np.imag(system.rhs(t, perturbed)) / 1e-25
            for row, column, label in ((0, 0, "TT"), (0, 1, "TC"), (1, 0, "CT"), (1, 1, "CC")):
                evidence.close("E1", f"jacobian_{appendix}_{int(t)}s_{label}",
                               analytic[row::2, column::2], numerical[row::2, column::2],
                               atol=3e-12, rtol=3e-9,
                               note="Complex-step of RHS is independent of the assembled analytical Jacobian.")
    if evidence.identity(q2_path) != Q2_SOLVER_SHA:
        raise ValueError("Original fixed-domain Q2 source identity changed")
    old = module_at(q2_path, "q2_fixed_domain_reference")
    fixed = AnalyticRadius(constant=True)
    old_system = old.System(n, boundary)
    new_system = m.System(n, boundary, fixed, properties="appendix3")
    for t in (0., 21600.):
        evidence.close("E1", f"fixed_appendix3_rhs_{int(t)}s", new_system.rhs(t, y),
                       old_system.rhs(t, y), atol=2e-13, rtol=3e-11)
        evidence.close("E1", f"fixed_appendix3_jac_{int(t)}s", new_system.jac(t, y).toarray(),
                       old_system.jac(t, y).toarray(), atol=3e-12, rtol=3e-10)


def consumer_checks(m, radius_path, radius_sha, root, evidence):
    def rejected(function):
        try:
            function()
        except (ValueError, TypeError):
            return True
        return False
    make = lambda **kw: m.RadiusInput(radius_path, expected_sha256=radius_sha, project_root=root, **kw)
    evidence.check("E1", "radius_reject_unknown_method", rejected(lambda: make(method="smooth_fit")))
    evidence.check("E1", "radius_reject_unknown_tail", rejected(lambda: make(tail="extrapolate")))
    evidence.check("E1", "radius_reject_nonpositive_constant", rejected(lambda: make(constant_radius_m=-.02)))
    evidence.check("E1", "radius_reject_wrong_identity", rejected(lambda: m.RadiusInput(
        radius_path, expected_sha256="0" * 64, project_root=root)))
    linear = make()
    evidence.check("E1", "radius_reject_negative_time", rejected(lambda: linear.evaluate(-1)))
    evidence.check("E1", "radius_reject_nonfinite_time", rejected(lambda: linear.evaluate(float("nan"))))
    evidence.check("E1", "radius_default_reject_beyond_72h", rejected(lambda: linear.evaluate(RAD_END + 1)))
    holding = make(tail="hold_last")
    evidence.close("E1", "radius_explicit_hold_last", holding.evaluate(RAD_END + 3600), 1.198 * .01,
                   atol=0, rtol=0)
    evidence.check("E1", "radius_tail_activation_metadata",
                   not holding.describe(RAD_END)["continuation_used"] and
                   holding.describe(RAD_END + 1)["continuation_used"])
    data = json.loads(Path(radius_path).read_text(encoding="utf-8"))
    times = np.asarray([node["time_s"] for node in data["nodes"]], float)
    values = np.asarray([node["radius_cm"] for node in data["nodes"]], float) * .01
    for method in ("linear", "pchip"):
        law = make(method=method)
        evidence.close("E1", f"radius_{method}_original_nodes", law.evaluate(times), values,
                       atol=2e-17, rtol=0)
        sample = np.linspace(0, RAD_END, 4 * 144 + 1)
        vals = law.evaluate(sample)
        evidence.check("E1", f"radius_{method}_positive_monotone", bool(np.all(vals > 0)
                       and np.all(np.diff(vals) <= 2e-17)), note="Checks input reconstruction, not physical field accuracy.")
    malformed = {
        "negative_node": lambda d: d["nodes"][20].update(radius_cm=-1.),
        "duplicate_time": lambda d: d["nodes"][20].update(time_s=d["nodes"][19]["time_s"]),
        "wrong_source_row": lambda d: d["nodes"][20].update(source_row=2),
        "wrong_unit": lambda d: d["units"].update(radius_cm="m"),
    }
    with tempfile.TemporaryDirectory(prefix="q4-consumer-fixtures-") as folder:
        for name, mutate in malformed.items():
            changed = json.loads(json.dumps(data))
            mutate(changed)
            fixture = Path(folder) / (name + ".json")
            fixture.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
            evidence.check("E1", "radius_semantic_reject_" + name, rejected(lambda:
                m.RadiusInput(fixture, expected_sha256=digest(fixture), project_root=root)),
                note="Correct fixture SHA bypasses the identity guard so the semantic consumer check is exercised.")
    evidence.close("E1", "radius_linear_midpoint_rule", linear.evaluate((times[:-1] + times[1:]) / 2),
                   (values[:-1] + values[1:]) / 2, atol=2e-17, rtol=0)


def recorder_contract_checks(m, boundary, radius, evidence):
    """Synthetic storage fixture only; it is not a physical trajectory or result."""
    n = 20
    system = m.System(n, boundary, radius)
    recorder = m.Recorder(system, boundary)
    initial = np.tile([28., 2.55], n + 1)
    before = np.tile([40., .150001], n + 1)
    after = np.tile([40., .149999], n + 1)
    later = np.tile([40., .14], n + 1)
    recorder.append_regular([0], initial[:, None])
    recorder.append_regular([60], before[:, None])
    recorder.accept_endpoint(61, after, before)
    recorder.append_regular([120], later[:, None])
    data, roles = recorder.finish(120, later)
    evidence.check("E1", "recorder_unique_endpoint_and_common_tail",
                   np.array_equal(data["time_s"], [0, 60, 61, 120])
                   and np.array_equal(data["official_output_mask"], [False, True, True, False]),
                   note="Synthetic fixture verifies storage/selection only, not event accuracy.")
    evidence.check("E1", "recorder_moving_surface_and_outside_blank_contract",
                   bool(np.isnan(data["moisture_kg_kg"][1:, -1]).all()
                        and not data["inside_mask"][1:, -1].any()
                        and np.array_equal(data["surface_moisture_kg_kg"], [2.55, .150001, .149999, .14])))
    evidence.check("E1", "recorder_complete_endpoint_roles",
                   all(role in roles for role in ("initial", "before_n_end", "n_end", "common_end")))
    for bad_end, bad_before, name in ((np.tile([40., .15], n + 1), before, "equality_at_endpoint"),
                                      (after, after, "preceding_already_strict")):
        try:
            m.Recorder(system, boundary).accept_endpoint(61, bad_end, bad_before)
        except RuntimeError:
            evidence.check("E1", "recorder_reject_" + name, True)
        else:
            evidence.check("E1", "recorder_reject_" + name, False)
    profile = np.empty(2 * (n + 1))
    profile[0::2] = 31 + 10 * system.xi
    profile[1::2] = .4 + .3 * system.xi
    for instant in (900., 21600.):
        projected = recorder.project(instant, profile)
        physical = np.arange(21) * .001
        rad = float(radius.evaluate(instant))
        mask = physical <= rad
        evidence.close("E1", f"physical_projection_nonuniform_T_{int(instant)}s",
                       projected["temperature"][mask], 31 + 10 * physical[mask] / rad, atol=2e-13, rtol=0)
        evidence.close("E1", f"physical_projection_nonuniform_C_{int(instant)}s",
                       projected["moisture"][mask], .4 + .3 * physical[mask] / rad, atol=3e-15, rtol=0)
    partial = m.Recorder(system, boundary)
    partial.append_regular([0], initial[:, None])
    partial.append_regular([60], before[:, None])
    partial_data, partial_roles = partial.finish(60, before)
    evidence.check("E1", "recorder_partial_horizon_not_official_answer",
                   not partial_data["official_output_mask"].any()
                   and "horizon_end" in partial_roles and "n_end" not in partial_roles)


MMS_DURATION = 120.


def exact_fields(t, xi):
    z = np.asarray(xi)
    u = t / MMS_DURATION
    a0, a = 1.7 - .2 * u, .2 + .05 * u
    b0, b = 31 + 2 * u, .6 + .2 * u
    theta, c = b0 + b * z**2, a0 + a * z**2
    theta_t, c_t = (2 + .2 * z**2) / MMS_DURATION, (-.2 + .05 * z**2) / MMS_DURATION
    return theta, c, theta_t, c_t, a, b


def manufactured_source(t, xi):
    theta, c, theta_t, c_t, a, b = exact_fields(t, xi)
    storage, k, d = physical_coefficients(theta, c)
    d_c, d_t = .30 * d / c**2, 3850 * d / (theta + 273.15)**2
    k_c = .20 / (1 + c)**2
    rad = float(AnalyticRadius(MMS_DURATION).evaluate(t))
    # (1/ξ)dξ(ξ D Cξ)=4aD+4aξ²(a D_C+b D_T); heat similarly.
    heat_operator = (4 * b * k + 4 * a * b * np.asarray(xi)**2 * k_c) / rad**2
    moisture_operator = (4 * a * d + 4 * a * np.asarray(xi)**2 * (a * d_c + b * d_t)) / rad**2
    forcing = np.empty(2 * len(np.asarray(xi)))
    forcing[0::2] = theta_t - heat_operator / storage
    forcing[1::2] = c_t - moisture_operator
    return forcing


class ManufacturedBoundary:
    def evaluate(self, t):
        theta, c, _, _, a, b = exact_fields(t, np.asarray([1.]))
        _, k, d = physical_coefficients(theta, c)
        radius = float(AnalyticRadius(MMS_DURATION).evaluate(t))
        return float(theta[0] + 2 * b * k[0] / (H * radius)), float(c[0] + 2 * a * d[0] / (HM * radius))


def mms_case(m, n, tight=False):
    radius, boundary = AnalyticRadius(MMS_DURATION), ManufacturedBoundary()
    system = m.System(n, boundary, radius)
    xi = np.arange(n + 1) / n
    theta, c, *_ = exact_fields(0., xi)
    initial = np.empty(2 * (n + 1))
    initial[0::2], initial[1::2] = theta, c
    scale = .1 if tight else 1.
    solution = solve_ivp(lambda t, y: system.rhs(t, y) + manufactured_source(t, xi),
                         (0., MMS_DURATION), initial, method="BDF", jac=system.jac,
                         rtol=1e-10 * scale, atol=np.tile([1e-10 * scale, 1e-12 * scale], n + 1),
                         first_step=1e-4, max_step=MMS_DURATION / (40 if tight else 20), dense_output=True)
    if not solution.success:
        raise RuntimeError("Independent manufactured-forcing integration failed: " + solution.message)
    times = np.linspace(0., MMS_DURATION, 5)
    result = solution.sol(times)
    exact = np.empty_like(result)
    for j, t in enumerate(times):
        exact[0::2, j], exact[1::2, j], *_ = exact_fields(t, xi)
    errors = dict(temperature=float(np.max(np.abs(result[0::2] - exact[0::2]))),
                  moisture=float(np.max(np.abs(result[1::2] - exact[1::2]))))
    return errors, result


def manufactured_checks(m, evidence):
    records = []
    for n in (40, 80, 160):
        errors, values = mms_case(m, n)
        records.append(dict(n=n, **errors))
        if n == 160:
            main = values
    tightened_errors, tight = mms_case(m, 160, tight=True)
    evidence.details["manufactured_solution"] = dict(duration_s=MMS_DURATION,
        formula="Theta=b0(t)+b(t)xi^2; C=a0(t)+a(t)xi^2; R=.02(1-.15t/120)",
        refinements=records, tightened_errors=tightened_errors,
        role="independently differentiated continuous source and Robin forcing; not a new production model")
    for field, tol in (("temperature", 2e-3), ("moisture", 2e-4)):
        errors = [r[field] for r in records]
        evidence.check("E2", "mms_" + field + "_absolute", errors[-1] <= tol, errors[-1], tol)
        evidence.check("E2", "mms_" + field + "_refinement", errors[2] < errors[1] < errors[0]
                       and errors[1] / max(errors[2], 1e-30) >= 1.5,
                       dict(errors=errors, last_ratio=errors[1] / max(errors[2], 1e-30)),
                       "decreasing with last ratio >=1.5; measured convergence, not a formal order proof")
    evidence.close("E2", "mms_independent_time_tightening", main, tight, atol=1e-7, rtol=0)


def balance_measurements(system, t, y, appendix="appendix4"):
    """Independent geometry/properties, paired with production RHS at a full state."""
    n = system.n
    volume = independent_volumes(n)
    theta, c = y[0::2], y[1::2]
    capacity, _, d = physical_coefficients(theta, c, appendix)
    rad = float(system.radius.evaluate(t))
    ambient, g = system.boundary.evaluate(t)
    derivative = system.rhs(t, y)
    normalized_heat = float(np.dot(volume * capacity, derivative[0::2]))
    normalized_water = float(np.dot(volume, derivative[1::2]))
    expected_heat, expected_water = H / rad * (ambient - theta[-1]), HM / rad * (g - c[-1])
    z = c - g
    energy_derivative = float(np.dot(volume * z, derivative[1::2]))
    dissipated = HM / rad * z[-1]**2
    for i in range(n):
        q = i + .5
        dissipated += q * (d[i] + d[i + 1]) / (2 * rad**2) * (z[i + 1] - z[i])**2
    return (normalized_heat, expected_heat, normalized_water, expected_water,
            energy_derivative, -float(dissipated))


def structure_checks(m, boundary, radius, evidence):
    n = 11
    xi = np.arange(n + 1) / n
    system = m.System(n, boundary, radius)
    volume = independent_volumes(n)
    evidence.close("E3", "dimensionless_cell_weights", system.v, volume, atol=3e-17, rtol=3e-14)
    evidence.close("E3", "axis_surface_and_total_weight", [system.v[0], system.v[-1], np.sum(system.v)],
                   [1 / (8 * n**2), 1 / (2 * n) - 1 / (8 * n**2), .5], atol=3e-17, rtol=3e-14)
    for t in (0., 60., 120.):
        uniform = np.tile([40., 1.], n + 1)
        closed = m.System(n, ConstantBoundary(40., 1.), AnalyticRadius())
        evidence.close("E3", f"uniform_material_field_under_shrinkage_{int(t)}s",
                       closed.rhs(t, uniform), np.zeros_like(uniform), atol=0, rtol=0,
                       note="A dry-basis ratio is invariant under pure geometric shrinkage with no relative exchange.")
    y = np.empty(2 * (n + 1))
    y[0::2], y[1::2] = 32 + 12 * xi**2, 1.8 - .8 * xi**2
    for t in (900., 21600., 259200.):
        values = balance_measurements(system, t, y)
        for name, a, b, tol in (("heat", values[0], values[1], 2e-8),
                                 ("water", values[2], values[3], 2e-15)):
            evidence.close("E3", f"normalized_{name}_balance_{int(t)}s", a, b, atol=tol, rtol=3e-10,
                           note="Instantaneous effective balance, not a claim about true total material mass or enthalpy.")
        if t > OBS_END:
            evidence.close("E3", f"constant_tail_energy_identity_{int(t)}s", values[4], values[5],
                           atol=3e-15, rtol=3e-10)
            evidence.check("E3", f"constant_tail_energy_nonincrease_{int(t)}s", values[4] <= 3e-15,
                           values[4], 0.)
    theta_lo = min(28., float(boundary.temperature.min()), boundary.tail[0])
    theta_hi = max(28., float(boundary.temperature.max()), boundary.tail[0])
    c_lo = min(2.55, float(boundary.moisture.min()), boundary.tail[1])
    c_hi = max(2.55, float(boundary.moisture.max()), boundary.tail[1])
    base = np.tile([(theta_lo + theta_hi) / 2, (c_lo + c_hi) / 2], n + 1)
    violation = 0.
    for t in (0., 900., 21600.):
        for j in range(len(base)):
            lo, hi = (theta_lo, theta_hi) if j % 2 == 0 else (c_lo, c_hi)
            for endpoint, sign in ((lo, -1.), (hi, 1.)):
                trial = base.copy()
                trial[j] = endpoint
                violation = max(violation, float(sign * system.rhs(t, trial)[j]))
    evidence.check("E3", "invariant_rectangle_component_face_directions", violation <= 1e-12,
                   violation, 1e-12, "Tests selected faces; the full rectangle theorem remains a mathematical argument.")
    flat = base.copy()
    flat[1::2] = LIMIT
    flow = system.rhs(21600., flat)[1::2]
    evidence.check("E3", "closed_threshold_rectangle_face_direction", bool(np.max(flow) <= 1e-14 and flow[-1] < 0),
                   dict(max_derivative=float(np.max(flow)), surface_derivative=float(flow[-1])),
                   "<=0 at all current maxima; strictly negative forcing at the surface")


class Run:
    def __init__(self, label, path, evidence, axis, context):
        self.label, self.path = label, Path(path).resolve()
        self.meta_path = self.path.with_suffix(".json")
        self.sha = evidence.identity(self.path)
        self.meta_sha = evidence.identity(self.meta_path)
        self.meta = json.loads(self.meta_path.read_text(encoding="utf-8"))
        for key, expected in (("question", "Q4"), ("result_sha256", self.sha),
                              ("solver_sha256", context["solver_sha"]),
                              ("spec_sha256", context["spec_sha"]),
                              ("boundary_sha256", context["boundary_sha"]),
                              ("radius_json_sha256", context["radius_sha"])):
            if self.meta.get(key) != expected:
                raise ValueError(f"{label}: metadata {key} identity does not match the actual bound source")
        evidence.details.setdefault("run_identities", []).append(dict(
            label=label, result=str(self.path), result_sha256=self.sha,
            metadata=str(self.meta_path), metadata_sha256=self.meta_sha))
        with np.load(self.path, allow_pickle=False) as data:
            self.data = {key: data[key].copy() for key in data.files}
        a, info = self.data, self.meta
        scale = .1 if info.get("tight") else 1.
        expected_settings = dict(rtol=2e-9 * scale, atol_temperature=2e-9 * scale,
            atol_moisture=2e-11 * scale, max_step_observed_s=2.5 if info.get("tight") else 5.,
            max_step_tail_s=150. if info.get("tight") else 300., explicit_initial_step_s=.001,
            initial_temperature_C=28., initial_moisture_kg_kg=2.55)
        for key, value in expected_settings.items():
            if info.get(key) != value:
                raise ValueError(f"{label}: {key} differs from the frozen numerical/initial contract")
        self.n = int(info["grid_n"])
        self.time = a["time_s"]
        required = ("radius_m", "mesh_xi", "temperature_C", "moisture_kg_kg", "inside_mask",
                    "surface_radius_m", "surface_temperature_C", "surface_moisture_kg_kg",
                    "max_moisture_kg_kg", "max_moisture_node", "max_moisture_radius_m",
                    "temperature_mean", "moisture_mean", "snapshot_time_s", "snapshot_radius_m", "temperature_snapshots", "moisture_snapshots")
        if any(key not in a for key in required):
            raise ValueError(f"{label}: missing required numerical arrays")
        if self.time.dtype != np.int64 or a["max_moisture_node"].dtype != np.int64:
            raise ValueError(f"{label}: time/node axes must be int64")
        for key in required:
            if key not in ("inside_mask", "max_moisture_node") and a[key].dtype != np.float64:
                raise ValueError(f"{label}: {key} must be float64")
        if np.any(a["max_moisture_node"] < 0) or np.any(a["max_moisture_node"] > self.n):
            raise ValueError(f"{label}: invalid maximum node index")
        if not (self.time.ndim == 1 and self.time[0] == 0 and np.all(np.diff(self.time) > 0)
                and np.array_equal(self.time, self.time.astype(np.int64))):
            raise ValueError(f"{label}: invalid time axis")
        if int(info["common_end_s"]) != self.time[-1]:
            raise ValueError(f"{label}: common endpoint disagrees with the stored time axis")
        if not np.allclose(a["mesh_xi"], np.arange(self.n + 1) / self.n, rtol=0, atol=3e-16):
            raise ValueError(f"{label}: material grid differs from uniform frozen nodes")
        if a["temperature_C"].shape != (len(self.time), 21) or a["moisture_kg_kg"].shape != (len(self.time), 21):
            raise ValueError(f"{label}: invalid physical-column field shape")
        mask = a["inside_mask"]
        if mask.dtype != np.bool_ or mask.shape != (len(self.time), 21):
            raise ValueError(f"{label}: invalid inside mask")
        for field in ("temperature_C", "moisture_kg_kg"):
            if not np.isfinite(a[field][mask]).all() or not np.isnan(a[field][~mask]).all():
                raise ValueError(f"{label}: inside/outside value convention violated")
        if a["snapshot_time_s"].ndim != 1 or np.any(np.diff(a["snapshot_time_s"]) <= 0):
            raise ValueError(f"{label}: invalid ordered snapshot times")
        if a["temperature_snapshots"].shape != (len(a["snapshot_time_s"]), self.n + 1):
            raise ValueError(f"{label}: invalid full snapshot shape")
        if a["moisture_snapshots"].shape != a["temperature_snapshots"].shape:
            raise ValueError(f"{label}: mismatched two-field snapshot shapes")
        for field in ("surface_radius_m", "surface_temperature_C", "surface_moisture_kg_kg",
                      "max_moisture_kg_kg", "max_moisture_radius_m", "temperature_snapshots", "moisture_snapshots"):
            if not np.isfinite(a[field]).all():
                raise ValueError(f"{label}: nonfinite {field}")
        evidence.check(axis, label + "_complete_drying_case", bool(info.get("success") and info.get("drying_complete")),
                       dict(status=info.get("status"), n_end=info.get("n_end")),
                       "success=true and drying_complete=true; a 72h partial case is not a completed drying answer")
        if not info.get("drying_complete"):
            raise ValueError(f"{label}: bounded partial case cannot pass endpoint/convergence acceptance")

    def indices(self, times):
        ix = np.searchsorted(self.time, times)
        if np.any(ix >= len(self.time)) or not np.array_equal(self.time[ix], times):
            raise ValueError(f"{self.label}: requested comparison times not present exactly")
        return ix

    def full_state(self, role):
        index = self.meta["snapshot_roles"][role]
        y = np.empty(2 * (self.n + 1))
        y[0::2], y[1::2] = self.data["temperature_snapshots"][index], self.data["moisture_snapshots"][index]
        return float(self.data["snapshot_time_s"][index]), y


def require_main(run):
    if (run.meta["scenario"], run.meta["properties"], run.meta["radius"]["method"], run.meta["tight"]) != (
            "mean_tail", "appendix4", "linear", False):
        raise ValueError("Selected main must be the ordinary linear-radius/appendix4/mean-tail case")


def comparison_times(common_end):
    if isinstance(common_end, bool) or not isinstance(common_end, int) or common_end < 1:
        raise ValueError("runs-config common_end_s must be a positive integer")
    if common_end < RAD_END:
        raise ValueError("The frozen common comparison domain must cover at least 259200 seconds")
    times = np.arange(0, common_end + 1, 60, dtype=np.int64)
    return np.unique(np.r_[times, common_end])


def compare_fields(first, second, times, *, material_snapshots=True):
    ia, ib = first.indices(times), second.indices(times)
    a, b = first.data, second.data
    mask = a["inside_mask"][ia] & b["inside_mask"][ib]
    metrics = {}
    for field, surface, label in (("temperature_C", "surface_temperature_C", "temperature"),
                                  ("moisture_kg_kg", "surface_moisture_kg_kg", "moisture")):
        fixed_error = float(np.max(np.abs(a[field][ia] - b[field][ib])[mask]))
        surface_error = float(np.max(np.abs(a[surface][ia] - b[surface][ib])))
        snapshot_error = 0.
        shared = np.intersect1d(a["snapshot_time_s"], b["snapshot_time_s"])
        shared = shared[(shared >= 0) & (shared <= times[-1])]
        if material_snapshots:
            snapshot_key = "temperature_snapshots" if label == "temperature" else "moisture_snapshots"
            xi = np.linspace(0., 1., max(first.n, second.n) + 1)
            for instant in shared:
                aj = int(np.searchsorted(a["snapshot_time_s"], instant))
                bj = int(np.searchsorted(b["snapshot_time_s"], instant))
                va = np.interp(xi, a["mesh_xi"], a[snapshot_key][aj])
                vb = np.interp(xi, b["mesh_xi"], b[snapshot_key][bj])
                snapshot_error = max(snapshot_error, float(np.max(np.abs(va - vb))))
        metrics[label] = dict(fixed_physical_columns=fixed_error, moving_surface=surface_error,
                              common_full_material_snapshots=snapshot_error if material_snapshots else None,
                              maximum=max(fixed_error, surface_error, snapshot_error))
    metrics["maximum_moisture_trace"] = float(np.max(np.abs(a["max_moisture_kg_kg"][ia] - b["max_moisture_kg_kg"][ib])))
    metrics["crossing_difference_s"] = float(abs(first.meta["t_cross_s"] - second.meta["t_cross_s"]))
    metrics["n_end_pair"] = [int(first.meta["n_end"]), int(second.meta["n_end"])]
    metrics["integer_endpoint_equal"] = bool(first.meta["n_end"] == second.meta["n_end"])
    metrics["shared_minute_and_endpoint_times"] = len(times)
    metrics["common_end_s"] = int(times[-1])
    return metrics


def compare_implementation(config, load, evidence, part="all"):
    times = comparison_times(config["common_end_s"])
    main = load(config["main"], "E2")
    require_main(main)
    evidence.details["selected_main"] = dict(
        label=main.label, result=str(main.path), result_sha256=main.sha,
        metadata=str(main.meta_path), metadata_sha256=main.meta_sha,
        grid_n=main.n, tight=main.meta["tight"], method=main.meta["method"],
        scenario=main.meta["scenario"], properties=main.meta["properties"],
        radius_method=main.meta["radius"]["method"])
    stability = {}
    evidence.details["comparison_part"] = part
    if part in ("all", "spatial"):
        pairs = config["spatial_pairs"]
        if not pairs:
            raise ValueError("At least one actual spatial refinement pair is required")
        records = []
        for low_name, high_name in pairs:
            low, high = load(low_name, "E2"), load(high_name, "E2")
            if high.n != 2 * low.n:
                raise ValueError("A spatial pair must double N")
            for key in ("scenario", "properties", "tight"):
                if low.meta[key] != high.meta[key]:
                    raise ValueError("Spatial comparisons must hold inputs/properties/time settings fixed")
            if low.meta["radius"]["method"] != high.meta["radius"]["method"]:
                raise ValueError("Spatial comparison changed the radius reconstruction")
            records.append(dict(low=low_name, high=high_name, **compare_fields(low, high, times)))
        selected = records[-1]
        if load(pairs[-1][1], "E2").sha != main.sha:
            raise ValueError("The highest accepted spatial result must be the selected main result")
        for field in ("temperature", "moisture"):
            error = selected[field]["maximum"]
            evidence.check("E2", "selected_spatial_" + field, error <= 2.5e-5, error, 2.5e-5)
        evidence.check("E2", "selected_spatial_crossing", selected["crossing_difference_s"] <= 1.,
                       selected["crossing_difference_s"], 1.)
        evidence.details["spatial_comparisons"] = records
        stability.update(selected_space=selected["n_end_pair"], selected_space_equal=selected["integer_endpoint_equal"])
    if part in ("all", "time"):
        tight = load(config["tight"], "E2")
        if main.n != tight.n or not tight.meta["tight"] or main.meta["tight"]:
            raise ValueError("Independent time comparison requires same N, ordinary main, and tightened run")
        if (main.meta["scenario"], main.meta["properties"], main.meta["radius"]["method"]) != (
                tight.meta["scenario"], tight.meta["properties"], tight.meta["radius"]["method"]):
            raise ValueError("Time comparison changed physical inputs")
        temporal = compare_fields(main, tight, times)
        for field in ("temperature", "moisture"):
            error = temporal[field]["maximum"]
            evidence.check("E2", "independent_time_" + field, error <= 5e-6, error, 5e-6)
        evidence.check("E2", "independent_time_crossing", temporal["crossing_difference_s"] <= .1,
                       temporal["crossing_difference_s"], .1)
        evidence.details["time_comparison"] = temporal
        stability.update(time=temporal["n_end_pair"], time_equal=temporal["integer_endpoint_equal"])
    stability["role"] = "reported separately; numerical field/crossing acceptance is not exact integer certification"
    evidence.details["integer_stability"] = stability


def run_structure(run, m, context, evidence):
    info, a = run.meta, run.data
    boundary = m.Boundary(context["boundary_path"], info["scenario"], project_root=context["root"])
    radius = m.RadiusInput(context["radius_path"], info["radius"]["method"],
                           expected_sha256=context["radius_sha"], project_root=context["root"],
                           tail=info["radius"]["continuation"],
                           constant_radius_m=info["radius"].get("constant_radius_m") or .02)
    system = m.System(run.n, boundary, radius, properties=info["properties"])
    expected_r = np.asarray(radius.evaluate(run.time))
    eps = 16 * np.finfo(float).eps * np.maximum(.02, expected_r)
    expected_inside = np.arange(21)[None, :] * .001 <= expected_r[:, None] + eps[:, None]
    evidence.close("E3", run.label + "_physical_radius_columns", a["radius_m"], np.arange(21) * .001, atol=0, rtol=0)
    evidence.close("E3", run.label + "_surface_radius_sequence", a["surface_radius_m"], expected_r, atol=2e-17, rtol=0)
    evidence.check("E3", run.label + "_moving_domain_mask", np.array_equal(a["inside_mask"], expected_inside))
    n_end = int(info["n_end"])
    expected_output = ((run.time > 0) & (run.time <= n_end) & ((run.time % 60 == 0) | (run.time == n_end)))
    evidence.check("E3", run.label + "_official_output_mask", np.array_equal(a["official_output_mask"], expected_output))
    t0, initial = run.full_state("initial")
    evidence.close("E3", run.label + "_initial_state", initial, np.tile([28., 2.55], run.n + 1), atol=0, rtol=0)
    before_t, before = run.full_state("before_n_end")
    after_t, after = run.full_state("n_end")
    before_node, after_node = int(np.argmax(before[1::2])), int(np.argmax(after[1::2]))
    evidence.check("E3", run.label + "_strict_integer_endpoint",
                   before_t == n_end - 1 and after_t == n_end and np.max(before[1::2]) >= LIMIT
                   and np.max(after[1::2]) < LIMIT,
                   dict(before_s=before_t, before_max=float(np.max(before[1::2])),
                        before_node=before_node, before_r_m=float(radius.evaluate(before_t) * before_node / run.n),
                        end_s=after_t, end_max=float(np.max(after[1::2])), after_node=after_node,
                        after_r_m=float(radius.evaluate(after_t) * after_node / run.n)))
    early = run.time < n_end
    late = run.time >= n_end
    evidence.check("E3", run.label + "_stored_maximum_threshold_trace",
                   bool(np.all(a["max_moisture_kg_kg"][early] >= LIMIT)
                        and np.all(a["max_moisture_kg_kg"][late] < LIMIT)),
                   note="Minute trace plus complete endpoint states; not an independent recomputation of every unsaved node/time.")
    active = run.time >= OBS_END
    evidence.check("E3", run.label + "_late_maximum_nonincrease",
                   bool(np.max(np.diff(a["max_moisture_kg_kg"][active]), initial=0.) <= 1e-8),
                   float(np.max(np.diff(a["max_moisture_kg_kg"][active]), initial=0.)), 1e-8)
    bounds = dict(tlo=min(28., float(boundary.temperature.min()), boundary.tail[0]),
                  thi=max(28., float(boundary.temperature.max()), boundary.tail[0]),
                  clo=min(2.55, float(boundary.moisture.min()), boundary.tail[1]),
                  chi=max(2.55, float(boundary.moisture.max()), boundary.tail[1]))
    evidence.check("E3", run.label + "_complete_snapshot_invariant_ranges",
                   bool(np.all(a["temperature_snapshots"] >= bounds["tlo"] - 1e-7)
                        and np.all(a["temperature_snapshots"] <= bounds["thi"] + 1e-7)
                        and np.all(a["moisture_snapshots"] >= bounds["clo"] - 1e-8)
                        and np.all(a["moisture_snapshots"] <= bounds["chi"] + 1e-8)), bounds)
    heat_err, water_err, dissipation_err, worst_energy_derivative = 0., 0., 0., -float("inf")
    surface_t_error, surface_c_error, trace_error, maximum_radius_error = 0., 0., 0., 0.
    energy_values = []
    projection_error, mean_error = 0., 0.
    weights = independent_volumes(run.n)
    for index, instant in enumerate(a["snapshot_time_s"]):
        y = np.empty(2 * (run.n + 1))
        y[0::2], y[1::2] = a["temperature_snapshots"][index], a["moisture_snapshots"][index]
        system.boundary = boundary if instant < OBS_END else boundary.right_side()
        values = balance_measurements(system, instant, y, info["properties"])
        heat_err = max(heat_err, abs(values[0] - values[1]) / max(1., abs(values[1])))
        water_err = max(water_err, abs(values[2] - values[3]))
        if instant >= OBS_END:
            dissipation_err = max(dissipation_err, abs(values[4] - values[5]))
            worst_energy_derivative = max(worst_energy_derivative, values[4])
            energy_values.append(float(.5 * np.dot(weights, (y[1::2] - boundary.tail[1])**2)))
        indices = np.flatnonzero(run.time == instant)
        if indices.size:
            row = int(indices[0])
            node = int(np.argmax(y[1::2]))
            rad = float(radius.evaluate(instant))
            for col in np.flatnonzero(a["inside_mask"][row]):
                position = min(float(a["radius_m"][col] / rad), 1.) * run.n
                left = min(int(np.floor(position)), run.n - 1)
                fraction = position - left
                for values, field in ((y[0::2], "temperature_C"), (y[1::2], "moisture_kg_kg")):
                    expected = (1 - fraction) * values[left] + fraction * values[left + 1]
                    projection_error = max(projection_error, abs(expected - a[field][row, col]))
            mean_error = max(mean_error, abs(2 * np.dot(weights, y[0::2]) - a["temperature_mean"][row]),
                             abs(2 * np.dot(weights, y[1::2]) - a["moisture_mean"][row]))
            surface_t_error = max(surface_t_error, abs(y[0::2][-1] - a["surface_temperature_C"][row]))
            surface_c_error = max(surface_c_error, abs(y[1::2][-1] - a["surface_moisture_kg_kg"][row]))
            trace_error = max(trace_error, abs(y[1::2][node] - a["max_moisture_kg_kg"][row]))
            if a["max_moisture_node"][row] != node:
                raise ValueError("Stored maximum node disagrees with an available complete snapshot")
            maximum_radius_error = max(maximum_radius_error,
                abs(radius.evaluate(instant) * node / run.n - a["max_moisture_radius_m"][row]))
    evidence.check("E3", run.label + "_physical_projection_against_complete_snapshots",
                   projection_error <= 5e-12, projection_error, 5e-12)
    evidence.check("E3", run.label + "_normalized_means_against_complete_snapshots",
                   mean_error <= 5e-12, mean_error, 5e-12)
    evidence.check("E3", run.label + "_all_snapshot_effective_heat_balance", heat_err <= 2e-8, heat_err, 2e-8)
    evidence.check("E3", run.label + "_all_snapshot_normalized_water_balance", water_err <= 3e-13, water_err, 3e-13)
    evidence.check("E3", run.label + "_all_tail_snapshot_dissipation",
                   bool(energy_values) and dissipation_err <= 3e-13 and worst_energy_derivative <= 3e-13,
                   dict(identity_abs_error=dissipation_err, largest_E_prime=worst_energy_derivative if energy_values else None), 3e-13)
    evidence.check("E3", run.label + "_tail_snapshot_energy_order",
                   len(energy_values) > 1 and np.max(np.diff(energy_values), initial=0.) <= 1e-9,
                   dict(samples=len(energy_values), maximum_rise=float(np.max(np.diff(energy_values), initial=0.))), 1e-9)
    evidence.check("E3", run.label + "_surface_and_maximum_against_complete_snapshots",
                   max(surface_t_error, surface_c_error, trace_error) <= 2e-13 and maximum_radius_error <= 2e-16,
                   dict(surface_T_error=surface_t_error, surface_C_error=surface_c_error,
                        max_C_error=trace_error, max_r_error=maximum_radius_error))


def compare_structure(config, load, m, context, evidence):
    main = load(config["main"], "E3")
    require_main(main)
    evidence.details["selected_main"] = dict(
        label=main.label, result=str(main.path), result_sha256=main.sha,
        metadata=str(main.meta_path), metadata_sha256=main.meta_sha,
        grid_n=main.n, tight=main.meta["tight"], method=main.meta["method"],
        scenario=main.meta["scenario"], properties=main.meta["properties"],
        radius_method=main.meta["radius"]["method"])
    evidence.guard("E3", "main_result_structure", lambda: run_structure(main, m, context, evidence))
    times = comparison_times(config["common_end_s"])
    sensitivities = config.get("sensitivities", {})
    if not sensitivities:
        raise ValueError("Declare the actual radius/interpolation and environment-tail sensitivity results")
    details = {}
    for role, label in sensitivities.items():
        def inspect_case():
            case = load(label, "E3")
            if (case.n != main.n or case.meta["properties"] != "appendix4"
                    or case.meta["tight"] != main.meta["tight"]):
                raise ValueError("Input sensitivity must hold the selected N, appendix4, and time settings fixed")
            run_structure(case, m, context, evidence)
            metrics = compare_fields(main, case, times, material_snapshots=False)
            metrics["signed_crossing_shift_s"] = float(case.meta["t_cross_s"] - main.meta["t_cross_s"])
            if role == "last_value":
                if (case.meta["scenario"], case.meta["radius"]["method"]) != ("last_value", "linear"):
                    raise ValueError("last_value sensitivity changed the wrong input")
                early = times[times <= OBS_END]
                earlier = compare_fields(main, case, early, material_snapshots=False)
                evidence.check("E3", "last_value_identical_observed_interval",
                               max(earlier["temperature"]["maximum"], earlier["moisture"]["maximum"]) <= 1e-10,
                               earlier, 1e-10)
            elif role == "pchip":
                if (case.meta["scenario"], case.meta["radius"]["method"]) != ("mean_tail", "pchip"):
                    raise ValueError("pchip sensitivity changed the wrong input")
            else:
                raise ValueError("Unknown sensitivity role; use pchip and last_value")
            details[role] = metrics
            evidence.check("E3", role + "_sensitivity_computed_and_reported", True,
                           dict(signed_crossing_shift_s=metrics["signed_crossing_shift_s"],
                                n_end_pair=metrics["n_end_pair"]),
                           note="No invented smallness threshold; an input sensitivity is a quantified limitation.")
        evidence.guard("E3", "sensitivity_" + role, inspect_case)
    evidence.check("E3", "both_prespecified_input_sensitivities_present",
                   set(sensitivities) == {"pchip", "last_value"}, sorted(sensitivities), ["last_value", "pchip"])
    evidence.details["input_sensitivities"] = details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("implementation", "structure", "compare"), required=True)
    parser.add_argument("--axes", help="implementation: E1,E2 or a subset; structure: E3; compare: E2 or E3 separately")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--solver", type=Path)
    parser.add_argument("--q2-solver", type=Path)
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--radius", type=Path)
    parser.add_argument("--radius-sha256", required=True)
    parser.add_argument("--spec-sha256", required=True)
    parser.add_argument("--runs-config", type=Path)
    parser.add_argument("--compare-part", choices=("all", "spatial", "time"), default="all",
                        help="Only for E2 compare: load and execute the selected independent comparison")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    axes = set(args.axes.split(",")) if args.axes else ({"E1", "E2"} if args.mode == "implementation" else {"E3"})
    if ((args.mode == "implementation" and (not axes or not axes <= {"E1", "E2"}))
            or (args.mode == "structure" and axes != {"E3"})
            or (args.mode == "compare" and axes not in ({"E2"}, {"E3"}))):
        parser.error("Evidence axes do not match the selected execution mode/route")
    if args.mode == "compare" and args.runs_config is None:
        parser.error("compare mode requires the explicit runs-config path")
    if args.mode != "compare" and args.runs_config is not None:
        parser.error("Result paths are not inputs to standalone implementation/structure modes")
    if args.compare_part != "all" and not (args.mode == "compare" and axes == {"E2"}):
        parser.error("compare-part is only meaningful for E2 result comparison")
    root = args.project_root.resolve()
    solver_path = (args.solver or root / "src/Q4/solve.py").resolve()
    q2_path = (args.q2_solver or root / "src/Q2/solve.py").resolve()
    boundary_path = (args.boundary or root / "output/ENV/q2_boundary.json").resolve()
    radius_path = (args.radius or root / "output/GEOMETRY/q4_radius.json").resolve()
    spec_path = root / "planning/Q4/model_spec.md"
    output = args.output.resolve()
    output.relative_to((root / "output/Q4").resolve())
    if output.exists():
        raise FileExistsError("Verification reports are not silently overwritten")
    evidence = Evidence(axes)
    evidence.identity(__file__)
    context = dict(root=root, solver_sha=evidence.identity(solver_path),
                   spec_sha=evidence.identity(spec_path), radius_sha=evidence.identity(radius_path),
                   boundary_sha=evidence.identity(boundary_path), radius_path=radius_path,
                   boundary_path=boundary_path)
    if context["spec_sha"] != args.spec_sha256 or context["radius_sha"] != args.radius_sha256:
        raise ValueError("Verifier inputs do not match the requested frozen identities")
    m = module_at(solver_path, "q4_production_under_review")
    boundary = m.Boundary(boundary_path, project_root=root)
    radius = m.RadiusInput(radius_path, expected_sha256=args.radius_sha256, project_root=root)
    evidence.identity(root / "附件/附件1.xlsx")
    evidence.identity(root / "附件/附件2.xlsx")
    if args.mode == "implementation":
        if "E1" in axes:
            evidence.guard("E1", "independent_operator_and_jacobian", lambda:
                           implementation_checks(m, boundary, radius, evidence, q2_path))
            evidence.guard("E1", "geometry_consumer_contract", lambda:
                           consumer_checks(m, radius_path, args.radius_sha256, root, evidence))
            evidence.guard("E1", "recording_and_endpoint_contract", lambda:
                           recorder_contract_checks(m, boundary, radius, evidence))
        if "E2" in axes:
            evidence.guard("E2", "continuous_manufactured_solution", lambda: manufactured_checks(m, evidence))
    elif args.mode == "structure":
        evidence.guard("E3", "standalone_structure", lambda: structure_checks(m, boundary, radius, evidence))
    else:
        config_path = args.runs_config.resolve()
        evidence.identity(config_path)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        cache = {}
        def load(label, axis):
            if label not in cache:
                value = Path(config["runs"][label])
                path = value if value.is_absolute() else root / value
                cache[label] = Run(label, path, evidence, axis, context)
            return cache[label]
        if axes == {"E2"}:
            evidence.guard("E2", "actual_process_refinement", lambda: compare_implementation(config, load, evidence, args.compare_part))
        else:
            evidence.guard("E3", "actual_process_structure_and_sensitivity", lambda:
                           compare_structure(config, load, m, context, evidence))
    report = dict(schema_version="1.0", question="Q4", axes=sorted(axes), mode=args.mode,
                  method_role="auxiliary_validator", created_at=datetime.now(timezone.utc).isoformat(),
                  passed=bool(evidence.checks and all(c["passed"] for c in evidence.checks)),
                  identities=evidence.identities, checks=evidence.checks, details=evidence.details,
                  claim_boundary="Only the actually executed axes/checks are reported. No E4 observation is supplied; "
                                 "no continuum strong-solution theorem, arbitrary-step BDF positivity, per-cell correct "
                                 "rounding proof, or cross-grid integer certainty is inferred.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    failed = [c["id"] for c in evidence.checks if not c["passed"]]
    print(json.dumps(dict(output=str(output), passed=report["passed"], checks=len(evidence.checks), failed=failed)))
    if not report["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
