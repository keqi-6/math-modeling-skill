"""Q3 E3 structural checks and E4/Q4-direction sensitivity diagnostics."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    from . import solve
except ImportError:
    import solve


ROOT = Path(__file__).resolve().parents[2]
E3_SETTINGS = {"name": "e3", "scan_step_s": 0.01, "n_theta": 256, "n_levels": 17,
               "root_time_tolerance_s": 1e-9, "margin_tolerance_m": 1e-8, "surface_refinement": False}
SENS_SETTINGS = {"name": "sensitivity", "scan_step_s": 0.01, "n_theta": 256, "n_levels": 17,
                 "root_time_tolerance_s": 1e-9, "margin_tolerance_m": 1e-8, "surface_refinement": False}
TOL = {"invariant": 1e-8, "duration_s": 1e-6, "monotonic_m": 1e-10}
CONTROL_GRIDS = {
    "heading_offset_deg": [-0.20, -0.10, 0.0, 0.10, 0.20],
    "speed_offset_mps": [-1.0, -0.5, 0.0, 0.5, 1.0],
    "release_shift_s": [-0.10, -0.05, 0.0, 0.05, 0.10],
    "fuse_shift_s": [-0.10, -0.05, 0.0, 0.05, 0.10],
}
BRIDGE_DISTANCES_M = [-25.0, -10.0, 0.0, 10.0, 25.0]
UAV = {
    "FY1": np.array([17800.0, 0.0, 1800.0]),
    "FY2": np.array([12000.0, 1400.0, 1400.0]),
    "FY3": np.array([6000.0, -3000.0, 700.0]),
}


class ModelVerificationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ModelVerificationFailure(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ready(value):
    if isinstance(value, np.ndarray): return value.tolist()
    if isinstance(value, np.generic): return value.item()
    if isinstance(value, dict): return {k: ready(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)): return [ready(v) for v in value]
    return value


def load() -> tuple[dict, solve.kernel.Decision]:
    payload = json.loads((ROOT / "docs/q3_result.json").read_text(encoding="utf-8"))
    require(payload["spec_id"] == solve.SPEC_ID, "formal Q3 result uses another specification")
    record = payload["working_best"]["decision"]
    decision = solve.kernel.Decision(
        float(record["heading_rad"]), float(record["speed_mps"]),
        tuple(float(x) for x in record["release_times_s"]),
        tuple(float(x) for x in record["fuse_delays_s"]), "q3_model_validation", 0,
    )
    solve.kernel.validate_decision(decision)
    return payload, decision


def common(axis: str, started: float) -> dict:
    return {
        "schema_version": "1.0", "axis": axis, "spec_id": solve.SPEC_ID,
        "formal_result_sha256": sha256(ROOT / "docs/q3_result.json"),
        "verification_spec_sha256": sha256(ROOT / "planning/22_q3_verification_and_sensitivity_spec.md"),
        "validator_sha256": sha256(ROOT / "src/q3/verify_model.py"),
        "run_identity": {"executed_at": datetime.now(timezone.utc).isoformat(),
                         "python": sys.version.split()[0], "elapsed_seconds": time.perf_counter() - started},
    }


def run_e3(payload: dict, decision: solve.kernel.Decision) -> dict:
    started = time.perf_counter()
    mesh = solve.kernel.surface_mesh(E3_SETTINGS["n_theta"], E3_SETTINGS["n_levels"])
    interval = payload["working_best"]["precise"]["intervals_s"][0]
    times = np.array([interval[0] + 0.1, 8.95, 11.40, interval[1] - 0.1])
    nominal = solve.kernel.joint_margins(decision, times, mesh, (0, 1, 2))

    permutation_records = []
    maximum_permutation_difference = 0.0
    for order in itertools.permutations((0, 1, 2)):
        margins = solve.kernel.joint_margins(decision, times, mesh, order)
        difference = float(np.max(np.abs(margins - nominal)))
        maximum_permutation_difference = max(maximum_permutation_difference, difference)
        permutation_records.append({"cloud_order": list(order), "maximum_margin_difference_m": difference})

    individuals = []
    for index in range(3):
        observed = solve.evaluate(decision, E3_SETTINGS, mesh, (index,))
        stored = payload["final_diagnostics"]["precise"]["individuals"][index]
        individuals.append({
            "bomb": index + 1, "e3_duration_s": observed["effective_duration_s"],
            "stored_precise_duration_s": stored["effective_duration_s"],
            "same_single_cloud_semantics": abs(observed["effective_duration_s"] - stored["effective_duration_s"]) <= 0.01,
        })

    subset_records = []
    resource_pass = True
    for count in (1, 2):
        for subset in itertools.combinations((0, 1, 2), count):
            margins = solve.kernel.joint_margins(decision, times, mesh, subset)
            # More clouds can only lower the worst margin, hence improve coverage.
            violation = float(np.max(nominal - margins))
            passed = violation <= TOL["monotonic_m"]
            resource_pass &= passed
            subset_records.append({"active_cloud_indices": list(subset),
                                   "maximum_joint_minus_subset_margin_m": violation, "status": "pass" if passed else "fail"})

    no_active = float(solve.kernel.joint_margins(decision, np.array([0.5]), mesh)[0])
    merged = solve.kernel.merge_intervals([[1.0, 2.0], [1.5, 3.0], [4.0, 5.0]])
    measure = solve.kernel.interval_measure(merged)
    toy = np.array([[-1.0, 1.0], [1.0, -1.0]])  # rows=clouds, columns=target points
    single_worst = [float(np.max(row)) for row in toy]
    joint_worst = float(np.max(np.min(toy, axis=0)))

    checks = {
        "label_permutation_invariance": maximum_permutation_difference <= TOL["invariant"],
        "single_cloud_degeneration": all(x["same_single_cloud_semantics"] for x in individuals),
        "resource_monotonicity": resource_pass,
        "no_active_cloud_is_false": math.isinf(no_active) and no_active > 0.0,
        "interval_union_not_double_counted": merged == [[1.0, 3.0], [4.0, 5.0]] and abs(measure - 3.0) <= TOL["invariant"],
        "max_min_synergy_counterexample": all(x > 0.0 for x in single_worst) and joint_worst < 0.0,
        "current_solution_has_positive_leave_one_out_margins": all(
            float(x["marginal_contribution_s"]) > 0.0 for x in payload["final_diagnostics"]["leave_one_out"]),
        "current_pure_synergy_is_diagnostic_zero": abs(float(payload["final_diagnostics"]["precise"]["pure_synergy_duration_s"])) <= TOL["duration_s"],
    }
    status = "pass" if all(checks.values()) else "fail"
    result = {
        **common("E3_STRUCTURAL", started), "result_id": "Q3-E3-STRUCTURAL-20260828", "status": status,
        "method_role": "auxiliary_validator", "settings": E3_SETTINGS, "checks": checks,
        "label_permutation": {"maximum_difference_m": maximum_permutation_difference, "records": permutation_records},
        "single_cloud_degeneration": individuals, "resource_monotonicity": subset_records,
        "no_active_margin": no_active,
        "interval_union_oracle": {"input": [[1.0, 2.0], [1.5, 3.0], [4.0, 5.0]], "merged": merged, "measure_s": measure},
        "synergy_counterexample": {"distance_margin_matrix_m": toy.tolist(), "single_worst_margins_m": single_worst,
                                   "joint_max_min_margin_m": joint_worst,
                                   "role": "quantifier capability test, not a claim about the selected Q3 solution"},
        "claim_boundary": ["supports internal max-min structure and invariants", "does not prove global optimality",
                           "toy synergy witness is not a physical Q3 result"],
    }
    require(status == "pass", f"Q3 E3 checks failed: {checks}")
    return result


def perturbed_decision(decision: solve.kernel.Decision, factor: str, value: float) -> solve.kernel.Decision:
    if factor == "heading_offset_deg":
        return replace(decision, heading_rad=float((decision.heading_rad + math.radians(value)) % (2.0 * math.pi)), source="sens_heading")
    if factor == "speed_offset_mps":
        return replace(decision, speed_mps=float(decision.speed_mps + value), source="sens_speed")
    if factor == "release_shift_s":
        return replace(decision, release_times_s=tuple(float(x + value) for x in decision.release_times_s), source="sens_release")
    if factor == "fuse_shift_s":
        return replace(decision, fuse_delays_s=tuple(float(x + value) for x in decision.fuse_delays_s), source="sens_fuse")
    raise KeyError(factor)


def heterogeneous_evaluate(
    decision: solve.kernel.Decision,
    initial_positions: list[np.ndarray],
    mesh: solve.kernel.SurfaceMesh,
) -> dict:
    original = solve.kernel.cloud_center
    p = solve.kernel.base_parameters()
    te = solve.kernel.explosion_times(decision)
    direction = np.array([math.cos(decision.heading_rad), math.sin(decision.heading_rad), 0.0])

    def override(x: solve.kernel.Decision, cloud_index: int, times: np.ndarray) -> np.ndarray:
        initial = np.asarray(initial_positions[cloud_index], dtype=float)
        explosion = initial + decision.speed_mps * te[cloud_index] * direction
        explosion[2] = initial[2] - 0.5 * p.gravity * decision.fuse_delays_s[cloud_index] ** 2
        result = np.repeat(explosion.reshape(1, 3), len(times), axis=0)
        result[:, 2] -= p.smoke_sink_speed * (times - te[cloud_index])
        return result

    solve.kernel.cloud_center = override
    try:
        return solve.evaluate(decision, SENS_SETTINGS, mesh)
    finally:
        solve.kernel.cloud_center = original


def run_e4(payload: dict, decision: solve.kernel.Decision) -> dict:
    started = time.perf_counter()
    mesh = solve.kernel.surface_mesh(SENS_SETTINGS["n_theta"], SENS_SETTINGS["n_levels"])
    nominal_eval = solve.evaluate(decision, SENS_SETTINGS, mesh)
    nominal = float(nominal_eval["effective_duration_s"])

    control_records = {}
    feasible_ratios = []
    for factor, grid in CONTROL_GRIDS.items():
        records = []
        for value in grid:
            candidate = perturbed_decision(decision, factor, float(value))
            try:
                solve.kernel.validate_decision(candidate)
            except solve.kernel.PilotError as error:
                records.append({"value": value, "status": "infeasible", "failure_code": error.code,
                                "reason": str(error)})
                continue
            observed = solve.evaluate(candidate, SENS_SETTINGS, mesh)
            duration = float(observed["effective_duration_s"])
            ratio = duration / nominal if nominal > 0 else math.nan
            feasible_ratios.append(ratio)
            records.append({"value": value, "status": "feasible", "duration_s": duration,
                            "change_s": duration - nominal, "retention_ratio": ratio})
        control_records[factor] = records

    directions = {}
    for name in ("FY2", "FY3"):
        vector = UAV[name] - UAV["FY1"]
        directions[name] = vector / np.linalg.norm(vector)

    zero_positions = [UAV["FY1"].copy() for _ in range(3)]
    zero_duration = float(heterogeneous_evaluate(decision, zero_positions, mesh)["effective_duration_s"])
    zero_difference = abs(zero_duration - nominal)
    require(zero_difference <= TOL["duration_s"], f"heterogeneous zero-shift oracle mismatch {zero_difference}")

    bridge_records = []
    for direction_name, unit in directions.items():
        for bomb in range(3):
            group = []
            for distance in BRIDGE_DISTANCES_M:
                positions = [UAV["FY1"].copy() for _ in range(3)]
                positions[bomb] = positions[bomb] + distance * unit
                observed = heterogeneous_evaluate(decision, positions, mesh)
                duration = float(observed["effective_duration_s"])
                group.append({"distance_m": distance, "duration_s": duration, "change_s": duration - nominal})
            by_distance = {float(x["distance_m"]): x for x in group}
            central = (by_distance[10.0]["duration_s"] - by_distance[-10.0]["duration_s"]) / 20.0
            bridge_records.append({
                "direction_toward": direction_name, "direction_unit": unit.tolist(), "bomb": bomb + 1,
                "scenarios": group, "central_sensitivity_s_per_m": central,
                "best_change_s": max(x["change_s"] for x in group),
                "worst_change_s": min(x["change_s"] for x in group),
            })

    all_bridge = [scenario for group in bridge_records for scenario in group["scenarios"]]
    minimum_ratio = min(feasible_ratios) if feasible_ratios else math.nan
    result = {
        **common("E4_REALITY_AND_SENSITIVITY", started), "result_id": "Q3-E4-SENSITIVITY-20260828",
        "status": "pass", "method_role": "diagnostic_fixed_policy_sensitivity",
        "nominal": {"duration_s": nominal, "settings": SENS_SETTINGS},
        "control_sensitivity": {
            "design": "one-factor fixed-policy local exploration; no re-optimization",
            "grids": CONTROL_GRIDS, "records": control_records,
            "minimum_feasible_retention_ratio": minimum_ratio,
            "all_tested_feasible_scenarios_retain_90_percent": bool(minimum_ratio >= 0.90),
        },
        "q4_bridge_sensitivity": {
            "role": "local structural sensitivity of Q3 shared-platform coupling; not a Q4 strategy",
            "official_platform_positions_m": {key: value.tolist() for key, value in UAV.items()},
            "distance_grid_m": BRIDGE_DISTANCES_M,
            "zero_shift_oracle_difference_s": zero_difference,
            "records": bridge_records,
            "best_observed_change_s": max(x["change_s"] for x in all_bridge),
            "worst_observed_change_s": min(x["change_s"] for x in all_bridge),
            "prohibited_interpretations": ["Q4 solved", "Q4 feasible strategy", "re-optimized multi-platform result"],
        },
        "reality_boundary": {
            "parameter_ranges_are": "pre-registered exploratory local bands, not probability distributions",
            "fixed_policy_only": True, "empirical_data_used": False,
            "deployment_validity": "not established",
        },
        "claim_boundary": ["reports response of the fixed Q3 solution in tested bands",
                           "Q4 bridge points violate Q3 shared-platform feasibility by construction",
                           "does not solve Q4 or establish probabilistic robustness"],
    }
    return result


def report_e3(result: dict) -> str:
    checks = result["checks"]
    return f"""# Q3 E3 结构检验报告

总状态：`{result['status']}`。烟幕标签遍历顺序造成的最大余量差为
`{result['label_permutation']['maximum_difference_m']:.3e} m`；单弹退化、资源单调、无活跃烟幕、
区间并集去重均通过。两点两烟幕最小反例中，任一单烟幕最坏余量均为 `+1 m`，联合
`max_P min_k` 余量为 `-1 m`，说明实现确实允许不同烟幕分别覆盖不同目标点。

当前最优工作解的纯协同时长仍为 `0 s`，该反例只验证模型结构能力，不把纯协同追加为
Q3 硬约束，也不证明当前候选全局最优。
"""


def report_e4(result: dict) -> str:
    control = result["control_sensitivity"]
    bridge = result["q4_bridge_sensitivity"]
    return f"""# Q3 灵敏度与 Q4 方向局部桥接检验

名义固定方案在统一灵敏度网格上的联合时长为 `{result['nominal']['duration_s']:.6f} s`。
Q3 可行域内的一因子局部扰动中，所有可行情景的最小保留比例为
`{control['minimum_feasible_retention_ratio']:.4f}`；负投放整体平移若使首枚投放早于任务开始，
按硬约束记为不可行，而不是强行裁剪。

作为 Q4 方向的初步结构诊断，本轮只沿题面 FY1→FY2、FY1→FY3 方位，将一枚弹的有效平台
初始位置移动 `±10/±25 m`，其余控制保持不变。零位移异质求值器与 Q3 生产求值器相差
`{bridge['zero_shift_oracle_difference_s']:.3e} s`；所有方向情景中的最好变化为
`{bridge['best_observed_change_s']:+.6f} s`，最差变化为 `{bridge['worst_observed_change_s']:+.6f} s`。

这些点故意放松了 Q3 的同平台共享位置约束，只用于观察耦合压力。它们不是 Q3 可行方案，
也没有使用 FY2/FY3 的完整实际位置重新优化，因此不能写成 Q4 结果、Q4 策略或现实误差概率。
"""


def run(axis: str, output: Path, report: Path) -> dict:
    payload, decision = load()
    result = run_e3(payload, decision) if axis == "e3" else run_e4(payload, decision)
    # Refresh elapsed after all work rather than at common-header construction time.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(ready(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.write_text(report_e3(result) if axis == "e3" else report_e4(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "axis": axis, "output": str(output), "report": str(report)}, ensure_ascii=False))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--axis", choices=("e3", "e4"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.axis, args.output, args.report)
    except (ModelVerificationFailure, solve.Q3UnifiedError, solve.kernel.PilotError) as error:
        print(json.dumps({"status": "fail", "axis": args.axis, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
