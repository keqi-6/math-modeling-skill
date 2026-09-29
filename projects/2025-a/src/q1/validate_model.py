"""Run Q1 E3 structural and E4 reality-mapping verification.

Outputs are internal technical evidence.  No external answer value is loaded,
compared, or written by this verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy

from model import (
    OFFICIAL_INPUT_IDENTITY,
    SPEC_IDENTITY,
    Q1Parameters,
    center_point_intervals,
    default_parameters,
    kinematics,
    missile_position,
    primary_margin,
    segment_distance,
    smoke_center,
    solve_intervals,
)


class ModelValidationFailure(RuntimeError):
    pass


# Registered before any sensitivity result is observed.  These are local
# structural diagnostics, not probability distributions or empirical errors.
SENSITIVITY_DESIGN = [
    ("smoke_radius", 0.95),
    ("smoke_radius", 1.05),
    ("smoke_sink_speed", 0.95),
    ("smoke_sink_speed", 1.05),
    ("gravity", 0.99),
    ("gravity", 1.01),
    ("target_radius", 0.95),
    ("target_radius", 1.05),
]
SENSITIVITY_SCAN_STEP_S = 4e-3
SENSITIVITY_N_THETA = 1024
STRUCTURAL_TOLERANCE = 1e-7


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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelValidationFailure(message)


def stage(name: str, status: str, **details) -> None:
    print(json.dumps({"stage": name, "status": status, **details}, ensure_ascii=False), flush=True)


def load_formal(project_root: Path, result_path: Path) -> dict:
    require(sha256_file(project_root / "data/A题.pdf") == OFFICIAL_INPUT_IDENTITY, "official input identity mismatch")
    require(sha256_file(project_root / "planning/06_q1_model_spec_and_selection.md") == SPEC_IDENTITY, "frozen specification identity mismatch")
    formal = json.loads(result_path.read_text(encoding="utf-8"))
    require(formal.get("status") == "ok", "formal result is not passing")
    require(formal.get("input_identity") == OFFICIAL_INPUT_IDENTITY, "formal result input identity mismatch")
    require(formal.get("spec_identity") == SPEC_IDENTITY, "formal result specification identity mismatch")
    return formal


def full_cylinder_surface_points(p: Q1Parameters) -> np.ndarray:
    theta = np.linspace(0.0, 2.0 * np.pi, 720, endpoint=False)
    z_values = np.linspace(0.0, p.target_height, 21)
    side = np.vstack([
        np.column_stack((
            p.target_base_center[0] + p.target_radius * np.cos(theta),
            p.target_base_center[1] + p.target_radius * np.sin(theta),
            np.full(theta.shape, z),
        ))
        for z in z_values
    ])
    radii = np.linspace(0.0, p.target_radius, 21)
    disks = []
    for z in (0.0, p.target_height):
        for radius in radii:
            disks.append(np.column_stack((
                p.target_base_center[0] + radius * np.cos(theta),
                p.target_base_center[1] + radius * np.sin(theta),
                np.full(theta.shape, z),
            )))
    return np.vstack([side, *disks])


def constraint_checks(formal: dict, p: Q1Parameters) -> dict[str, object]:
    info = kinematics(p)
    start, stop = [float(value) for value in info["active_window_s"]]
    entry, exit_ = [float(value) for value in formal["intervals_s"][0]]
    midpoint = 0.5 * (entry + exit_)
    epsilon = 1e-4
    margins = {
        "before_entry_m": float(primary_margin(entry - epsilon, p)["margin_m"]),
        "after_entry_m": float(primary_margin(entry + epsilon, p)["margin_m"]),
        "midpoint_m": float(primary_margin(midpoint, p)["margin_m"]),
        "before_exit_m": float(primary_margin(exit_ - epsilon, p)["margin_m"]),
        "after_exit_m": float(primary_margin(exit_ + epsilon, p)["margin_m"]),
    }
    require(start <= entry < exit_ <= stop, "formal interval violates active window")
    require(margins["before_entry_m"] > 0.0 and margins["after_entry_m"] < 0.0, "entry does not change feasibility in the expected direction")
    require(margins["midpoint_m"] < 0.0, "interval midpoint is not fully occluded")
    require(margins["before_exit_m"] < 0.0 and margins["after_exit_m"] > 0.0, "exit does not change feasibility in the expected direction")
    maximum_root_residual = max(abs(float(item["margin_m"])) for item in formal["residuals"])
    require(maximum_root_residual <= STRUCTURAL_TOLERANCE, "formal root residual violates constraint tolerance")
    return {
        "status": "pass",
        "checks": [
            {"constraint": "release/explosion event order", "residual": float(info["explosion_time_s"]) - p.release_time - p.fuse_delay, "tolerance": 1e-12},
            {"constraint": "explosion above ground", "residual": float(info["explosion_point_m"][2]), "tolerance": ">=0 m"},
            {"constraint": "occlusion interval inside active window", "residual": {"entry_slack_s": entry - start, "exit_slack_s": stop - exit_}, "tolerance": ">=0 s"},
            {"constraint": "root feasibility residual", "residual": maximum_root_residual, "tolerance": STRUCTURAL_TOLERANCE},
            {"constraint": "inside/outside sign pattern", "residual": margins, "tolerance": "strict sign at ±1e-4 s"},
        ],
    }


def invariant_checks(formal: dict, p: Q1Parameters) -> dict[str, object]:
    t0, t1 = 6.0, 16.0
    missile_speed_observed = float(np.linalg.norm(missile_position(t1, p) - missile_position(t0, p)) / (t1 - t0))
    smoke_sink_observed = float((smoke_center(t0, p)[2] - smoke_center(t1, p)[2]) / (t1 - t0))
    translation = np.array([123.0, -45.0, 67.0])
    cloud = np.array([1.0, 2.0, 3.0])
    missile = np.array([4.0, 5.0, 6.0])
    points = np.array([[7.0, 8.0, 10.0], [2.0, -1.0, 5.0]])
    original_distance, original_lambda = segment_distance(cloud, missile, points)
    shifted_distance, shifted_lambda = segment_distance(cloud + translation, missile + translation, points + translation)
    translation_distance_residual = float(np.max(np.abs(original_distance - shifted_distance)))
    translation_lambda_residual = float(np.max(np.abs(original_lambda - shifted_lambda)))
    larger = replace(p, smoke_radius=p.smoke_radius + 0.5)
    sample_times = np.linspace(float(formal["active_window_s"][0]), float(formal["active_window_s"][1]), 9)
    radius_shift_residuals = [
        abs(float(primary_margin(float(time), larger, 1024)["margin_m"]) - float(primary_margin(float(time), p, 1024)["margin_m"]) + 0.5)
        for time in sample_times
    ]
    require(abs(missile_speed_observed - p.missile_speed) <= 1e-10, "missile constant-speed invariant failed")
    require(abs(smoke_sink_observed - p.smoke_sink_speed) <= 1e-10, "smoke constant-sink invariant failed")
    require(translation_distance_residual <= 1e-12 and translation_lambda_residual <= 1e-12, "segment translation invariance failed")
    require(max(radius_shift_residuals) <= 1e-10, "smoke-radius margin monotonicity failed")
    return {
        "status": "pass",
        "checks": [
            {"invariant": "missile constant speed", "test": f"finite difference over [{t0},{t1}] s", "result": missile_speed_observed},
            {"invariant": "smoke vertical constant sink", "test": f"finite difference over [{t0},{t1}] s", "result": smoke_sink_observed},
            {"invariant": "common-translation invariance of finite segment distance", "test": translation.tolist(), "result": {"distance_residual": translation_distance_residual, "lambda_residual": translation_lambda_residual}},
            {"invariant": "pointwise margin decreases exactly with smoke radius", "test": "+0.5 m radius over nine times", "result": {"maximum_residual": max(radius_shift_residuals)}},
        ],
    }


def surface_equivalence_checks(formal: dict, p: Q1Parameters) -> dict[str, object]:
    points = full_cylinder_surface_points(p)
    entry, exit_ = [float(value) for value in formal["intervals_s"][0]]
    times = [float(formal["active_window_s"][0]), entry, 0.5 * (entry + exit_), exit_, float(formal["active_window_s"][1])]
    records = []
    maximum_excess = -np.inf
    for time in times:
        distances, _ = segment_distance(smoke_center(time, p), missile_position(time, p), points)
        sampled_surface_max = float(np.max(distances - p.smoke_radius))
        rim_max = float(primary_margin(time, p, 4096)["margin_m"])
        excess = sampled_surface_max - rim_max
        maximum_excess = max(maximum_excess, excess)
        records.append({
            "time_s": time,
            "sampled_surface_max_margin_m": sampled_surface_max,
            "continuous_top_bottom_rim_max_margin_m": rim_max,
            "surface_excess_over_rim_m": excess,
        })
    require(maximum_excess <= STRUCTURAL_TOLERANCE, "sampled full cylinder surface exceeds controlling rims")
    return {
        "status": "pass",
        "sample_count_per_time": int(points.shape[0]),
        "records": records,
        "maximum_surface_excess_over_rim_m": float(maximum_excess),
        "implication": "deterministic full-surface samples found no point worse than the continuous top/bottom rim control",
    }


def limit_checks(formal: dict, p: Q1Parameters) -> dict[str, object]:
    small = replace(p, smoke_radius=0.1)
    huge = replace(p, smoke_radius=1e6)
    small_result = solve_intervals(small, scan_step=1e-2, n_theta=256)
    huge_result = solve_intervals(huge, scan_step=1e-2, n_theta=256)
    active_duration = float(formal["active_window_s"][1]) - float(formal["active_window_s"][0])
    center = center_point_intervals(p)
    require(float(small_result["effective_duration_s"]) <= float(formal["effective_duration_s"]), "small-radius limit violates monotonicity")
    require(abs(float(huge_result["effective_duration_s"]) - active_duration) <= 1e-9, "large-radius limit does not cover the full active window")
    require(float(center["effective_duration_s"]) >= float(formal["effective_duration_s"]), "center-point relaxation is not an upper relaxation in the Q1 scenario")
    return {
        "status": "pass",
        "cases": [
            {"case": "smoke radius -> small positive value", "expected": "duration cannot exceed nominal", "observed": float(small_result["effective_duration_s"])},
            {"case": "smoke radius -> very large value", "expected": active_duration, "observed": float(huge_result["effective_duration_s"])},
            {"case": "full cylinder -> center-point relaxation", "expected": "center duration >= full-cylinder duration for this scenario", "observed": float(center["effective_duration_s"])},
        ],
    }


def infinite_line_distance(cloud: np.ndarray, missile: np.ndarray, points: np.ndarray) -> np.ndarray:
    vectors = points - missile
    raw = np.einsum("j,ij->i", cloud - missile, vectors) / np.einsum("ij,ij->i", vectors, vectors)
    closest = missile + raw[:, None] * vectors
    return np.linalg.norm(cloud - closest, axis=1)


def counterexample_checks(formal: dict, p: Q1Parameters) -> dict[str, object]:
    center_result = center_point_intervals(p)
    center_interval = center_result["intervals_s"][0]
    full_entry, full_exit = [float(value) for value in formal["intervals_s"][0]]
    candidates = np.linspace(float(center_interval[0]), float(center_interval[1]), 1001)
    center_only_time = next((float(time) for time in candidates if time < full_entry or time > full_exit), None)
    require(center_only_time is not None, "center-point relaxation did not expose a counterexample")
    full_margin = float(primary_margin(center_only_time, p, 4096)["margin_m"])
    require(full_margin > 0.0, "center-only counterexample is not rejected by the full-cylinder model")

    theta = np.linspace(0.0, 2.0 * np.pi, 720, endpoint=False)
    target_points = np.vstack([
        np.column_stack((p.target_radius * np.cos(theta), 200.0 + p.target_radius * np.sin(theta), np.zeros_like(theta))),
        np.column_stack((p.target_radius * np.cos(theta), 200.0 + p.target_radius * np.sin(theta), np.full_like(theta, p.target_height))),
    ])
    line_case = None
    for time in np.linspace(full_exit + 0.05, float(formal["active_window_s"][1]), 100):
        cloud = smoke_center(float(time), p)
        missile = missile_position(float(time), p)
        line_distances = infinite_line_distance(cloud, missile, target_points)
        segment_distances, raw_lambda = segment_distance(cloud, missile, target_points)
        indices = np.flatnonzero((line_distances <= p.smoke_radius) & (segment_distances > p.smoke_radius))
        if indices.size:
            index = int(indices[0])
            line_case = {
                "time_s": float(time),
                "infinite_line_distance_m": float(line_distances[index]),
                "finite_segment_distance_m": float(segment_distances[index]),
                "raw_lambda": float(raw_lambda[index]),
            }
            break
    require(line_case is not None, "infinite-line counterexample was not found in the active window")
    return {
        "status": "pass",
        "cases": [
            {
                "counterexample": "target center is occluded while some cylinder boundary is not",
                "result": {"time_s": center_only_time, "full_cylinder_margin_m": full_margin},
                "implication": "center-point visibility cannot replace complete-cylinder visibility",
            },
            {
                "counterexample": "infinite line accepts smoke behind the missile while finite segment rejects it",
                "result": line_case,
                "implication": "unclipped line distance violates directed finite-line-of-sight semantics",
            },
        ],
    }


def sensitivity_checks(formal: dict, p: Q1Parameters) -> dict[str, object]:
    nominal = solve_intervals(p, scan_step=SENSITIVITY_SCAN_STEP_S, n_theta=SENSITIVITY_N_THETA)
    records = []
    for index, (factor, multiplier) in enumerate(SENSITIVITY_DESIGN, start=1):
        stage("e3_sensitivity", "progress", completed=index, total=len(SENSITIVITY_DESIGN), factor=factor, multiplier=multiplier)
        perturbed = replace(p, **{factor: float(getattr(p, factor)) * multiplier})
        observed = solve_intervals(perturbed, scan_step=SENSITIVITY_SCAN_STEP_S, n_theta=SENSITIVITY_N_THETA)
        records.append({
            "factor": factor,
            "multiplier": multiplier,
            "parameter_value": float(getattr(perturbed, factor)),
            "duration_s": float(observed["effective_duration_s"]),
            "duration_change_s": float(observed["effective_duration_s"] - nominal["effective_duration_s"]),
            "interval_count": len(observed["intervals_s"]),
            "decision_response": "positive complete-occlusion interval" if observed["effective_duration_s"] > 0.0 else "no positive-measure interval",
        })
    require(all(item["interval_count"] == 1 and item["duration_s"] > 0.0 for item in records), "local sensitivity range changed the interval topology")
    radius_low = next(item for item in records if item["factor"] == "smoke_radius" and item["multiplier"] < 1.0)
    radius_high = next(item for item in records if item["factor"] == "smoke_radius" and item["multiplier"] > 1.0)
    require(radius_low["duration_s"] <= nominal["effective_duration_s"] <= radius_high["duration_s"], "duration is not monotone in smoke radius")
    return {
        "status": "pass",
        "design_registered_before_execution": True,
        "range_kind": "local structural perturbation, not empirical uncertainty",
        "scan_step_s": SENSITIVITY_SCAN_STEP_S,
        "n_theta": SENSITIVITY_N_THETA,
        "nominal_duration_s": float(nominal["effective_duration_s"]),
        "records": records,
        "decision_stability": "one positive-measure interval in all predeclared scenarios",
    }


def run_e3(project_root: Path, result_path: Path, output_path: Path) -> dict:
    formal = load_formal(project_root, result_path)
    p = default_parameters()
    stage("e3_constraints", "started")
    constraints = constraint_checks(formal, p)
    stage("e3_constraints", "passed")
    stage("e3_invariants", "started")
    invariants = invariant_checks(formal, p)
    stage("e3_invariants", "passed")
    stage("e3_full_surface_equivalence", "started")
    surface = surface_equivalence_checks(formal, p)
    stage("e3_full_surface_equivalence", "passed")
    stage("e3_limits_and_counterexamples", "started")
    limits = limit_checks(formal, p)
    counterexamples = counterexample_checks(formal, p)
    stage("e3_limits_and_counterexamples", "passed")
    stage("e3_sensitivity", "started")
    sensitivity = sensitivity_checks(formal, p)
    stage("e3_sensitivity", "passed")
    result = json_ready({
        "schema_version": "1.0",
        "validation_id": "Q1-E3-STRUCTURAL-DETERMINISTIC",
        "status": "pass",
        "external_reference_policy": "excluded",
        "spec_identity": SPEC_IDENTITY,
        "input_identity": OFFICIAL_INPUT_IDENTITY,
        "formal_result_sha256": sha256_file(result_path),
        "constraints": constraints,
        "invariants": invariants,
        "full_surface_equivalence": surface,
        "limit_cases": limits,
        "counterexamples": counterexamples,
        "sensitivity": sensitivity,
        "run_identity": {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "model_sha256": sha256_file(project_root / "src/q1/model.py"),
            "validator_sha256": sha256_file(project_root / "src/q1/validate_model.py"),
            "execution_kind": "deterministic",
            "seed": "not_applicable",
        },
    })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def reality_mapping(formal: dict, p: Q1Parameters) -> dict[str, object]:
    info = kinematics(p)
    assumptions = [
        {
            "assumption": "M1 moves at constant 300 m/s toward the origin",
            "support": "explicit official-problem motion rule",
            "violation_impact": "missile position and every line-of-sight segment must be rebuilt",
        },
        {
            "assumption": "FY1 flies horizontally at constant 120 m/s toward the decoy before release",
            "support": "explicit Q1 strategy in the official problem",
            "violation_impact": "release and explosion positions change",
        },
        {
            "assumption": "the released bomb follows ideal gravity-only motion with project convention g=9.8 m/s^2",
            "support": "contest idealization plus resolved project convention",
            "violation_impact": "drag, lift or another gravity convention changes explosion height",
        },
        {
            "assumption": "effective smoke is a hard 10 m sphere sinking at 3 m/s for 20 s",
            "support": "explicit official-problem effective-region rule",
            "violation_impact": "wind, diffusion or concentration decay requires a different state and visibility model",
        },
        {
            "assumption": "the true target is the complete closed cylinder and visibility uses the missile-to-target finite segment",
            "support": "official target geometry and frozen task semantics",
            "violation_impact": "center-point or infinite-line substitutes change the event being measured",
        },
    ]
    parameters = [
        ("missile_initial", p.missile_initial.tolist(), "m", "given exactly; not estimated"),
        ("uav_initial", p.uav_initial.tolist(), "m", "given exactly; not estimated"),
        ("missile_speed", p.missile_speed, "m/s", "given exactly; not estimated"),
        ("uav_speed", p.uav_speed, "m/s", "fixed Q1 strategy; not optimized"),
        ("release_time", p.release_time, "s", "fixed Q1 strategy"),
        ("fuse_delay", p.fuse_delay, "s", "fixed Q1 strategy"),
        ("target_radius/height", [p.target_radius, p.target_height], "m", "given exactly"),
        ("smoke_radius/sink/duration", [p.smoke_radius, p.smoke_sink_speed, p.smoke_duration], "m, m/s, s", "given exactly under hard-threshold interpretation"),
        ("gravity", p.gravity, "m/s^2", "resolved project convention; not inferred from Q1 output"),
    ]
    scales = [
        {"quantity": "initial engagement distance", "model_value": float(np.linalg.norm(p.missile_initial)), "reference_range": "official scenario: order 10^4 m"},
        {"quantity": "platform speeds", "model_value": [p.uav_speed, p.missile_speed], "reference_range": "official scenario: order 10^2 m/s"},
        {"quantity": "target dimensions", "model_value": [p.target_radius, p.target_height], "reference_range": "official scenario: order 10 m"},
        {"quantity": "effective smoke scale", "model_value": p.smoke_radius, "reference_range": "official scenario: order 10 m"},
        {"quantity": "event and effective times", "model_value": [float(info["explosion_time_s"]), p.smoke_duration], "reference_range": "official scenario: order 1-10 s"},
        {"quantity": "computed occlusion duration", "model_value": float(formal["effective_duration_s"]), "reference_range": "strictly between 0 and the 20 s active-window upper bound"},
    ]
    mechanisms = [
        {
            "modeled_mechanism": "ballistic fall before explosion and vertical smoke sinking after explosion",
            "domain_mechanism": "piecewise motion specified by the contest problem",
            "direction_and_constraints": "height decreases under gravity, then smoke center decreases linearly",
            "known_mismatch": "no aerodynamic drag, wind or turbulent spreading",
        },
        {
            "modeled_mechanism": "complete occlusion requires every controlling target sightline to intersect the smoke sphere",
            "domain_mechanism": "line-of-sight screening of the complete cylindrical target",
            "direction_and_constraints": "larger smoke radius weakly enlarges the feasible time set; finite segment rejects smoke behind missile/target",
            "known_mismatch": "hard binary visibility replaces graded optical density",
        },
        {
            "modeled_mechanism": "effective duration is the measure of the feasible time-set union",
            "domain_mechanism": "continuous-time accumulation without double counting",
            "direction_and_constraints": "interval topology and endpoints determine duration",
            "known_mismatch": "does not predict detection probability or operational damage",
        },
    ]
    reality_fit = {
        "observed_reference": "official problem-defined Q1 scenario, frozen identities and model-generated feasibility pattern only",
        "fit_measure": {
            "all fixed inputs trace to official statement or resolved project convention": True,
            "computed interval lies within the official active window": True,
            "mechanism directions pass E3 invariants, limits and counterexamples": True,
        },
        "context_match": "valid for the deterministic idealized contest scenario",
        "use_boundary": "not an empirical field-performance, optical-density, probability-of-detection or causal-effect estimate",
    }
    return {
        "status": "pass",
        "assumptions": assumptions,
        "parameters": [
            {"parameter": name, "range": value, "unit": unit, "identifiability": identity}
            for name, value, unit, identity in parameters
        ],
        "scale_checks": scales,
        "mechanisms": mechanisms,
        "reality_fit": reality_fit,
    }


def build_report(result: dict) -> str:
    e3 = result["E3_STRUCTURAL"]
    e4 = result["E4_REALITY"]
    sensitivity = e3["sensitivity"]
    surface = e3["full_surface_equivalence"]
    return f"""# Q1 E3/E4 模型验证报告

> 内部技术证据，不是论文或队友讲解稿。本报告不加载、不比较、不显示任何外部答案。

## E3 模型结构

- 约束：起爆事件顺序、起爆高度、有效窗、遮蔽区间、根余量和区间内外符号全部满足。
- 不变量：导弹恒速、烟幕恒定下沉、有限线段距离的共同平移不变性、烟幕半径对余量的单调响应全部满足。
- 完整目标：每个关键时刻以 `{surface['sample_count_per_time']}` 个完整圆柱表面确定性样点复核，未发现比上下圆周连续控制值更差的点；最大超出量为 `{surface['maximum_surface_excess_over_rim_m']:.17g} m`。
- 极限与反例：小/大烟幕半径极限、中心点放松、无限直线替代均按预期暴露或拒绝错误模型。
- 敏感性：对烟幕半径、下沉速度、重力和目标半径执行预先登记的局部扰动，全部场景仍保持一个正测度遮蔽区间；烟幕半径与时长响应方向满足单调性。名义诊断时长为 `{sensitivity['nominal_duration_s']:.17g} s`。

## E4 现实映射

- `{len(e4['assumptions'])}` 条假设均绑定题设或已解决项目约定，并逐条记录违反后的模型影响。
- `{len(e4['parameters'])}` 组参数均为题设固定值或显式项目约定；Q1 不从输出反向识别参数。
- 距离、速度、目标/烟幕尺度和时间均与题设场景的数量级一致。
- 机制方向与题设一致：重力下降、烟幕下沉、完整圆柱有限视线遮蔽以及连续区间计时；风、扩散、光学浓度、探测概率和实战因果效应明确排除。
- 适用结论只限确定性理想化竞赛场景，不外推为现场性能预测。

## 门禁边界

本报告支持 E3 与 E4，但不作为论文中的数学合同。论文模型检验只能摘要检验对象、设置、指标与结论；内部反例构造、表面复核及敏感性明细不进入论文或队友讲解稿。
"""


def run_e4(project_root: Path, result_path: Path, e3_path: Path, output_path: Path, report_path: Path) -> dict:
    formal = load_formal(project_root, result_path)
    e3 = json.loads(e3_path.read_text(encoding="utf-8"))
    require(e3.get("status") == "pass", "E3 structural evidence is not passing")
    require(e3.get("spec_identity") == SPEC_IDENTITY and e3.get("input_identity") == OFFICIAL_INPUT_IDENTITY, "E3 identity mismatch")
    stage("e4_assumptions_parameters_scales", "started")
    e4 = reality_mapping(formal, default_parameters())
    stage("e4_assumptions_parameters_scales", "passed")
    result = json_ready({
        "schema_version": "1.0",
        "validation_id": "Q1-E3-E4-MODEL-VALIDATION",
        "status": "pass",
        "external_reference_policy": "excluded",
        "writing_boundary": "internal technical evidence; manuscript/teammate materials may only summarize object, setting, metric and conclusion",
        "spec_identity": SPEC_IDENTITY,
        "input_identity": OFFICIAL_INPUT_IDENTITY,
        "formal_result_sha256": sha256_file(result_path),
        "e3_result_sha256": sha256_file(e3_path),
        "E3_STRUCTURAL": e3,
        "E4_REALITY": e4,
        "run_identity": {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "model_sha256": sha256_file(project_root / "src/q1/model.py"),
            "validator_sha256": sha256_file(project_root / "src/q1/validate_model.py"),
            "execution_kind": "deterministic",
            "seed": "not_applicable",
        },
    })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(build_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--axis", choices=["e3", "e4"], required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--e3", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[2]
    try:
        if args.axis == "e3":
            result = run_e3(project_root, project_root / args.result, project_root / args.output)
        else:
            require(args.e3 is not None and args.report is not None, "E4 requires --e3 and --report")
            result = run_e4(
                project_root,
                project_root / args.result,
                project_root / args.e3,
                project_root / args.output,
                project_root / args.report,
            )
    except (ModelValidationFailure, OSError, ValueError, KeyError, IndexError) as error:
        print(json.dumps({"status": "fail", "error": type(error).__name__, "message": str(error)}, ensure_ascii=False), flush=True)
        return 2
    print(json.dumps({"status": result["status"], "validation_id": result["validation_id"], "axis": args.axis, "output": args.output.as_posix()}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
