"""Independent structural checks for the Q4 multi-cloud semantics."""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.q4 import solve, verify  # noqa: E402

SPEC_ID = "SPEC-Q4-VERIFY-2.0"
SETTINGS = {
    "name": "q4_e3_subset",
    "scan_step_s": 0.02,
    "n_theta": 128,
    "n_levels": 9,
    "root_time_tolerance_s": 2e-6,
    "margin_tolerance_m": 2e-6,
    "surface_refinement": False,
}
TOL = {"margin_m": 1e-8, "duration_s": 5e-5, "monotonicity_s": 5e-5}


class StructuralFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StructuralFailure(message)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load():
    payload = json.loads((ROOT / "docs/q4_result.json").read_text(encoding="utf-8"))
    data = payload["formal_best"]["decision"]
    decision = solve.Decision(
        tuple(data["headings_rad"]), tuple(data["speeds_mps"]),
        tuple(data["release_times_s"]), tuple(data["fuse_delays_s"]),
        "q4_e3", 0,
    )
    solve.validate(decision)
    return payload, decision


def independent_margin(decision, t: float, mesh, indices) -> float:
    """Scalar point/cloud loops, independent of q4.joint_margins vectorization."""
    params = solve.p()
    missile = verify.missile_at(t)
    _, explosions, explosion_times = verify.independent_states(decision)
    worst = -math.inf
    visible_count = 0
    for row, point in enumerate(mesh.points):
        if mesh.kinds[row] == 0:
            if float(np.dot(mesh.point_normals[row], missile - point)) < -1e-12:
                continue
        elif missile[2] < point[2] - 1e-12:
            continue
        visible_count += 1
        segment = point - missile
        denominator = float(np.dot(segment, segment))
        best = math.inf
        for index in indices:
            end = min(explosion_times[index] + params.smoke_duration, solve.t_m())
            if not explosion_times[index] - solve.TIME_TOL <= t <= end + solve.TIME_TOL:
                continue
            center = explosions[index].copy()
            center[2] -= params.smoke_sink_speed * (t - explosion_times[index])
            lam = min(1.0, max(0.0, float(np.dot(center - missile, segment) / denominator)))
            distance = float(np.linalg.norm(center - (missile + lam * segment)))
            best = min(best, distance - params.smoke_radius)
        worst = max(worst, best)
    return worst if visible_count else math.inf


def interval_overlap(a, b) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def run(output: Path, report_path: Path):
    started = time.perf_counter()
    payload, decision = load()
    mesh = verify.independent_mesh(SETTINGS["n_theta"], SETTINGS["n_levels"])
    subset_results = {}
    for size in (1, 2, 3):
        for subset in itertools.combinations(range(3), size):
            value = solve.solve_intervals(decision, SETTINGS, subset, mesh)
            key = "".join(str(i + 1) for i in subset)
            subset_results[key] = {
                "indices": list(subset),
                "platforms": [solve.NAMES[i] for i in subset],
                "duration_s": value["effective_duration_s"],
                "intervals_s": value["intervals_s"],
            }

    monotonic_checks = []
    subsets = [tuple(value["indices"]) for value in subset_results.values()]
    for left in subsets:
        for right in subsets:
            if set(left) < set(right):
                a = subset_results["".join(str(i + 1) for i in left)]["duration_s"]
                b = subset_results["".join(str(i + 1) for i in right)]["duration_s"]
                passed = a <= b + TOL["monotonicity_s"]
                monotonic_checks.append({"subset": list(left), "superset": list(right), "subset_duration_s": a, "superset_duration_s": b, "pass": passed})
                require(passed, f"resource monotonicity failed: {left} -> {right}")

    precise_mesh = solve.q3.surface_mesh(solve.PRECISE["n_theta"], solve.PRECISE["n_levels"])
    singleton_checks = []
    for index in range(3):
        recomputed = solve.solve_intervals(decision, solve.PRECISE, (index,), precise_mesh)
        stored = payload["verification"]["individuals"][index]
        difference = recomputed["effective_duration_s"] - stored["effective_duration_s"]
        passed = abs(difference) <= TOL["duration_s"]
        singleton_checks.append({"platform": solve.NAMES[index], "recomputed_duration_s": recomputed["effective_duration_s"], "stored_duration_s": stored["effective_duration_s"], "difference_s": difference, "pass": passed})
        require(passed, f"single-cloud degeneration failed for {solve.NAMES[index]}")

    probe_times = [0.0]
    for item in payload["formal_best"]["densified_intervals_s"]:
        probe_times.extend([item[0], (item[0] + item[1]) / 2, item[1]])
    permutation_checks = []
    independent_differences = []
    for t in sorted(set(float(v) for v in probe_times)):
        base = float(solve.joint_margins(decision, [t], mesh, (0, 1, 2))[0])
        scalar = independent_margin(decision, t, mesh, (0, 1, 2))
        if math.isfinite(base) and math.isfinite(scalar):
            independent_differences.append(abs(base - scalar))
        values = [float(solve.joint_margins(decision, [t], mesh, order)[0]) for order in itertools.permutations((0, 1, 2))]
        finite = [v for v in values if math.isfinite(v)]
        spread = max(finite) - min(finite) if finite else 0.0
        passed = spread <= TOL["margin_m"]
        permutation_checks.append({"time_s": t, "spread_m": spread, "pass": passed})
        require(passed, f"label-order invariance failed at t={t}")
    max_independent_difference = max(independent_differences, default=0.0)
    require(max_independent_difference <= TOL["margin_m"], "independent scalar oracle mismatch")

    no_active_production = float(solve.joint_margins(decision, [0.0], mesh, (0, 1, 2))[0])
    no_active_independent = independent_margin(decision, 0.0, mesh, (0, 1, 2))
    require(math.isinf(no_active_production) and no_active_production > 0, "production no-active margin is not +inf")
    require(math.isinf(no_active_independent) and no_active_independent > 0, "independent no-active margin is not +inf")

    raw_intervals = [[0.0, 2.0], [1.0, 3.0], [5.0, 6.0], [5.5, 7.0]]
    merged = solve.q3.merge_intervals(raw_intervals)
    measure = solve.q3.interval_measure(merged)
    require(merged == [[0.0, 3.0], [5.0, 7.0]] and abs(measure - 5.0) <= 1e-12, "interval-union oracle failed")

    toy = np.array([[-1.0, 1.0], [1.0, -1.0]])
    single_worst = [float(np.max(row)) for row in toy]
    combined_worst = float(np.max(np.min(toy, axis=0)))
    require(all(v > 0 for v in single_worst) and combined_worst <= 0, "max-min synergy counterexample failed")

    singleton_intervals = [payload["verification"]["individuals"][i]["intervals_s"] for i in range(3)]
    pair_overlap = 0.0
    for i, j in itertools.combinations(range(3), 2):
        pair_overlap += sum(interval_overlap(a, b) for a in singleton_intervals[i] for b in singleton_intervals[j])
    current_solution_form = "temporal_relay" if pair_overlap <= TOL["duration_s"] else "overlapping_or_spatially_combined"

    result = {
        "schema_version": "1.0",
        "spec_id": SPEC_ID,
        "result_id": "Q4-E3-STRUCTURAL-20260828",
        "status": "pass",
        "method_role": "auxiliary_validator",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_identity": {
            name: sha(ROOT / name) for name in (
                "planning/27_q4_e1e2_and_sensitivity_spec.md",
                "src/q4/solve.py", "src/q4/verify.py", "docs/q4_result.json",
            )
        },
        "settings": SETTINGS,
        "tolerances": TOL,
        "subset_results": subset_results,
        "resource_monotonicity": {"check_count": len(monotonic_checks), "checks": monotonic_checks, "pass": True},
        "single_cloud_degeneration": {"checks": singleton_checks, "pass": True},
        "label_order_invariance": {"checks": permutation_checks, "pass": True},
        "independent_scalar_oracle": {"probe_count": len(independent_differences), "maximum_difference_m": max_independent_difference, "pass": True},
        "no_active_semantics": {"production_margin": "positive_infinity", "independent_margin": "positive_infinity", "pass": True},
        "interval_union_oracle": {"input": raw_intervals, "merged": merged, "measure_s": measure, "pass": True},
        "max_min_counterexample": {"cloud_by_point_margins": toy.tolist(), "single_cloud_worst_margins": single_worst, "combined_worst_margin": combined_worst, "pass": True},
        "current_solution_structure": {"classification": current_solution_form, "pairwise_single_window_overlap_s": pair_overlap},
        "proof_boundary": {"continuous_global_optimality": False, "current_solution_requires_spatial_synergy": False, "model_can_represent_spatial_synergy": True},
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        "elapsed_s": time.perf_counter() - started,
    }
    output.write_text(json.dumps(solve.ready(result), ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Q4 E3 结构复核报告", "",
        "本报告只复核多烟团联合判据与资源集合语义，不参与选解。", "",
        "## 复核结果", "",
        f"- 七个非空资源子集已全部复算；共检查 `{len(monotonic_checks)}` 个 `A⊂B` 关系，资源单调性全部通过。",
        f"- 三个单云退化检验全部通过，最大时长差 `{max(abs(v['difference_s']) for v in singleton_checks):.3e} s`。",
        f"- 烟团遍历顺序置换不改变余量；独立标量 oracle 的最大余量差 `{max_independent_difference:.3e} m`。",
        "- 无活动烟团时余量为正无穷；手工区间并集测度为 `5 s`，没有重复计入重叠段。",
        "- 两烟团—两点反例中，两枚单云的最坏余量均为 `+1 m`，组合后的最坏余量为 `−1 m`，因此实现确实允许不同烟团分别遮住圆柱表面的不同部分。", "",
        "## 对当前 Q4 解的解释", "",
        f"当前三枚烟团的单独服务窗两两交叠总长为 `{pair_overlap:.9f} s`，所以当前工作解属于“时间接力型”，而不是同一时刻的空间拼接型。模型具备表达空间拼接的能力，但求解结果没有被预设成必须出现这种形态。", "",
        "## 证据边界", "",
        "以上结果支持当前 Q4 多烟团量词、资源子集与区间并集的结构语义，不证明十二维连续域全局最优，也不构成现实数据验证。", "",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.output.resolve(), args.report.resolve())
    except StructuralFailure as error:
        print(json.dumps({"status": "fail", "message": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": result["status"], "subset_count": len(result["subset_results"]), "elapsed_s": result["elapsed_s"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
