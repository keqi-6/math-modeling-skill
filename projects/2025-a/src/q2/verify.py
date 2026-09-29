"""Execute the Q2 S5 implementation and numerical verification gate.

The verifier is an internal technical asset.  It does not load or compare any
external answer value.  All pass/fail tolerances are constants declared below,
before numerical observations are computed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import platform
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import brentq

import solve as formal
import reselection_pilot as pilot


ROOT = Path(__file__).resolve().parents[2]
FORMAL_RESULT_SHA = "0dd12455e0898bdb5e087888da848ea66bfa8caf325b1180b0412f23557eab7f"

TOLERANCES = {
    "reproduction_semantic_s": 1e-10,
    "mapping_roundtrip": 1e-10,
    "duration_convergence_s": 1e-4,
    "endpoint_convergence_s": 1e-4,
    "independent_duration_s": 1e-4,
    "independent_endpoint_s": 1e-4,
    "root_residual_m": 1e-6,
    "optimization_improvement_s": 0.05,
    "guard_counterexample_s": 1e-4,
}

REFINEMENT_SETTINGS = [
    {"scan_step_s": 0.02, "n_theta": 128, "n_levels": 17},
    {"scan_step_s": 0.01, "n_theta": 256, "n_levels": 25},
    {"scan_step_s": 0.005, "n_theta": 512, "n_levels": 33},
    {"scan_step_s": 0.0025, "n_theta": 1024, "n_levels": 49},
]
LOCAL_RADII = [0.005, 0.0025, 0.00125]
AUDIT_SEEDS = [250830, 250831, 250832]


class VerificationFailure(RuntimeError):
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


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def stage(name: str, status: str, **details) -> None:
    print(json.dumps({"stage": name, "status": status, **details}, ensure_ascii=False), flush=True)


def decision_from_record(record: dict, source: str) -> pilot.Decision:
    return pilot.Decision(
        heading_rad=float(record["heading_rad"]),
        speed_mps=float(record["speed_mps"]),
        release_time_s=float(record["release_time_s"]),
        fuse_delay_s=float(record["fuse_delay_s"]),
        source_domain=source,
    )


def run_unit_suite(project_root: Path) -> dict:
    loader = unittest.TestLoader()
    suite = loader.discover(str(project_root / "src/q2/tests"), pattern="test_q2.py")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    require(result.wasSuccessful(), "Q2 E1 semantic suite failed: " + stream.getvalue()[-3000:])
    return {
        "status": "pass",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "semantic_oracles": [
            "frozen input and specification identities",
            "complete four-dimensional unit mapping and corner feasibility",
            "C3-I analytic witness and inverse rejection",
            "15-start family/domain inventory",
            "proxy fallback exact-objective safety",
            "interval union and hard-constraint contract",
            "event geometry recomputation",
            "wrapped heading-domain classification",
        ],
    }


def identity_error_path() -> dict:
    original = formal.SPEC_SHA
    observed = None
    try:
        formal.SPEC_SHA = "0" * 64
        formal.verify_identities()
    except formal.Q2FormalError as error:
        observed = error.code
    finally:
        formal.SPEC_SHA = original
    require(observed == "Q2_FORMAL_IDENTITY_MISMATCH", "formal identity error signal changed")
    return {
        "status": "pass",
        "case": "mismatched frozen formal specification identity",
        "expected_signal": "Q2_FORMAL_IDENTITY_MISMATCH",
        "observed_signal": observed,
        "formal_files_modified": False,
    }


def semantic_signature(result: dict) -> dict:
    return {
        "contract": result["solver_contract"],
        "durations_s": result["multistart_summary"]["durations_s"],
        "chosen_decisions": [item["chosen"]["decision"] for item in result["multistart_records"]],
        "precise": [
            {
                "start_id": item["start_id"],
                "decision": item["decision"],
                "intervals_s": item["precise"]["intervals_s"],
                "duration_s": item["precise"]["effective_duration_s"],
            }
            for item in result["precise_finalists"]
        ],
        "best_start_id": result["formal_best"]["start_id"],
        "best_duration_s": result["formal_best"]["precise"]["effective_duration_s"],
        "guard": result["guard_diagnostic"],
    }


def maximum_numeric_difference(left, right) -> float:
    differences: list[float] = []

    def visit(a, b) -> None:
        if isinstance(a, dict) and isinstance(b, dict):
            require(set(a) == set(b), "fresh reproduction changed semantic keys")
            for key in sorted(a):
                visit(a[key], b[key])
        elif isinstance(a, list) and isinstance(b, list):
            require(len(a) == len(b), "fresh reproduction changed semantic list length")
            for one, two in zip(a, b):
                visit(one, two)
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
            differences.append(abs(float(a) - float(b)))
        else:
            require(a == b, "fresh reproduction changed semantic categorical value")

    visit(left, right)
    return max(differences, default=0.0)


def fresh_entrypoint_reproduction(project_root: Path, formal_result: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="q2-s6-reproduce-") as temporary:
        temporary_root = Path(temporary)
        output_path = temporary_root / "result.json"
        report_path = temporary_root / "report.md"
        command = [
            sys.executable, "-B", str(project_root / "src/q2/solve.py"),
            "--output", str(output_path), "--report", str(report_path),
        ]
        process = subprocess.run(
            command,
            cwd=project_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=360,
            check=False,
        )
        require(process.returncode == 0, "fresh Q2 formal entrypoint failed: " + process.stdout[-3000:])
        require(output_path.is_file() and report_path.is_file(), "fresh Q2 entrypoint omitted an output")
        reproduced = json.loads(output_path.read_text(encoding="utf-8"))
        maximum_difference = maximum_numeric_difference(
            semantic_signature(formal_result), semantic_signature(reproduced)
        )
        require(
            maximum_difference <= TOLERANCES["reproduction_semantic_s"],
            f"fresh reproduction semantic difference {maximum_difference}",
        )
        markers = ("identity", "seed_generation", "full4d_refinement", "precise_rescore")
        return {
            "status": "pass",
            "entrypoint": "python3 -B src/q2/solve.py",
            "exit_code": process.returncode,
            "maximum_semantic_difference_unrounded": maximum_difference,
            "new_output_sha256": sha256_file(output_path),
            "stage_markers_observed": {marker: f'"stage": "{marker}"' in process.stdout for marker in markers},
        }


def independent_surface_intervals(decision: pilot.Decision, scan_step_s: float = 0.01) -> dict:
    parameters = pilot.parameters(decision)
    start, stop = map(float, pilot.q1.kinematics(parameters)["active_window_s"])
    times = np.arange(start, stop, scan_step_s, dtype=float)
    if times.size == 0 or abs(float(times[-1]) - stop) > 1e-14:
        times = np.append(times, stop)

    def margin(time_s: float) -> float:
        return float(pilot.q1.full_surface_margin(float(time_s), parameters, 512, 65)["margin_m"])

    values = np.asarray([margin(float(time_s)) for time_s in times], dtype=float)
    inside = values <= 0.0
    blocks: list[tuple[int, int]] = []
    index = 0
    while index < inside.size:
        if not inside[index]:
            index += 1
            continue
        first = index
        while index + 1 < inside.size and inside[index + 1]:
            index += 1
        blocks.append((first, index))
        index += 1

    intervals: list[list[float]] = []
    residuals: list[float] = []
    boundary_margins: list[float] = []
    for first, last in blocks:
        if first == 0:
            left = start
            boundary_margins.append(margin(left))
        else:
            left = float(brentq(margin, float(times[first - 1]), float(times[first]), xtol=1e-12, rtol=1e-14))
            residuals.append(margin(left))
        if last == times.size - 1:
            right = stop
            boundary_margins.append(margin(right))
        else:
            right = float(brentq(margin, float(times[last]), float(times[last + 1]), xtol=1e-12, rtol=1e-14))
            residuals.append(margin(right))
        intervals.append([left, right])
    return {
        "method": "independent time scan and scipy brentq over a transposed 512-angle/65-level full-cylinder mesh",
        "scan_step_s": scan_step_s,
        "intervals_s": intervals,
        "effective_duration_s": float(sum(right - left for left, right in intervals)),
        "root_residuals_m": residuals,
        "active_boundary_margins_m": boundary_margins,
    }


def ordered_evaluator_refinement(decision: pilot.Decision, formal_best: dict) -> dict:
    records = []
    for settings in REFINEMENT_SETTINGS:
        observed = pilot.evaluate(decision, settings)
        records.append(observed)
    durations = [float(item["effective_duration_s"]) for item in records]
    require(all(len(item["intervals_s"]) == 1 for item in records), "refinement changed interval topology")
    finest_interval = records[-1]["intervals_s"][0]
    consecutive_duration_differences = [
        abs(durations[index + 1] - durations[index]) for index in range(len(durations) - 1)
    ]
    endpoint_differences_to_finest = [
        abs(float(value) - float(finest_interval[position]))
        for item in records[:-1]
        for position, value in enumerate(item["intervals_s"][0])
    ]
    actual_roots = [
        root
        for item in records
        for root in item["root_residuals"]
        if int(root.get("iterations", 0)) > 0
    ]
    active_boundaries = [
        root
        for item in records
        for root in item["root_residuals"]
        if int(root.get("iterations", 0)) == 0
    ]
    maximum_root_residual = max(
        (abs(float(root["margin_m"])) for root in actual_roots), default=0.0
    )
    maximum_active_boundary_margin = max(
        (float(root["margin_m"]) for root in active_boundaries), default=-math.inf
    )
    formal_duration_difference = abs(durations[-1] - float(formal_best["precise"]["effective_duration_s"]))
    pass_flags = {
        "duration_convergence": max(consecutive_duration_differences, default=0.0) <= TOLERANCES["duration_convergence_s"],
        "endpoint_convergence": max(endpoint_differences_to_finest, default=0.0) <= TOLERANCES["endpoint_convergence_s"],
        "root_residual": maximum_root_residual <= TOLERANCES["root_residual_m"],
        "active_boundary_feasible": maximum_active_boundary_margin <= TOLERANCES["root_residual_m"],
        "formal_to_finest": formal_duration_difference <= TOLERANCES["duration_convergence_s"],
    }
    return {
        "status": "pass" if all(pass_flags.values()) else "fail",
        "refinement_parameter": "scan_step_s decreases by 2 while n_theta doubles",
        "sequence": REFINEMENT_SETTINGS,
        "records": records,
        "consecutive_duration_differences_s": consecutive_duration_differences,
        "endpoint_differences_to_finest_s": endpoint_differences_to_finest,
        "maximum_root_residual_m": maximum_root_residual,
        "maximum_active_boundary_margin_m": maximum_active_boundary_margin,
        "formal_to_finest_duration_difference_s": formal_duration_difference,
        "decision_stability": all(len(item["intervals_s"]) == 1 and item["effective_duration_s"] > 0.0 for item in records),
        "pass_flags": pass_flags,
    }


def independent_recomputation(decision: pilot.Decision, refinement: dict) -> dict:
    independent = independent_surface_intervals(decision)
    reference = refinement["records"][-1]
    require(len(independent["intervals_s"]) == len(reference["intervals_s"]), "independent interval count mismatch")
    endpoint_differences = [
        abs(float(observed) - float(expected))
        for observed_interval, expected_interval in zip(independent["intervals_s"], reference["intervals_s"])
        for observed, expected in zip(observed_interval, expected_interval)
    ]
    duration_difference = abs(float(independent["effective_duration_s"]) - float(reference["effective_duration_s"]))
    maximum_root_residual = max((abs(float(value)) for value in independent["root_residuals_m"]), default=0.0)
    maximum_active_boundary_margin = max(
        (float(value) for value in independent["active_boundary_margins_m"]),
        default=-math.inf,
    )
    pass_flags = {
        "duration": duration_difference <= TOLERANCES["independent_duration_s"],
        "endpoints": max(endpoint_differences, default=0.0) <= TOLERANCES["independent_endpoint_s"],
        "root_residual": maximum_root_residual <= TOLERANCES["root_residual_m"],
        "active_boundary_feasible": maximum_active_boundary_margin <= TOLERANCES["root_residual_m"],
    }
    independent.update({
        "status": "pass" if all(pass_flags.values()) else "fail",
        "primary_method": "nested full-cylinder surface meshes plus bracketed time roots",
        "independent_method": independent["method"],
        "endpoint_differences_s": endpoint_differences,
        "duration_difference_s": duration_difference,
        "maximum_root_residual_m": maximum_root_residual,
        "maximum_active_boundary_margin_m": maximum_active_boundary_margin,
        "pass_flags": pass_flags,
    })
    return independent


def direct_local_search(best_decision: pilot.Decision, baseline_duration_s: float) -> dict:
    settings = {"scan_step_s": 0.01, "n_theta": 256}
    current_z = formal.decision_to_unit(best_decision)
    current_decision = best_decision
    current_score = float(pilot.evaluate(current_decision, settings)["effective_duration_s"])
    evaluations = []
    for radius in LOCAL_RADII:
        best_trial = None
        for coordinate in range(4):
            for direction in (-1.0, 1.0):
                trial_z = current_z.copy()
                trial_z[coordinate] = np.clip(trial_z[coordinate] + direction * radius, 0.0, 1.0)
                trial = formal.unit_to_decision(trial_z, "E2_direct_local")
                observed = pilot.evaluate(trial, settings)
                score = float(observed["effective_duration_s"])
                record = {
                    "radius": radius,
                    "coordinate": coordinate,
                    "direction": direction,
                    "unit_coordinates": json_ready(trial_z),
                    "decision": pilot.decision_record(trial),
                    "duration_s": score,
                }
                evaluations.append(record)
                if best_trial is None or score > best_trial[0]:
                    best_trial = (score, trial_z, trial)
        if best_trial is not None and best_trial[0] > current_score + 1e-12:
            current_score, current_z, current_decision = best_trial
    precise = pilot.evaluate(current_decision, REFINEMENT_SETTINGS[-1])
    precise_duration = float(precise["effective_duration_s"])
    improvement = precise_duration - baseline_duration_s
    return {
        "status": "pass" if improvement <= TOLERANCES["optimization_improvement_s"] else "fail",
        "method": "deterministic complete-coordinate pattern search on the direct continuous objective",
        "normalized_radii": LOCAL_RADII,
        "screen_settings": settings,
        "evaluation_count": len(evaluations) + 2,
        "baseline_duration_s": baseline_duration_s,
        "initial_direct_duration_s": float(pilot.evaluate(best_decision, REFINEMENT_SETTINGS[-1])["effective_duration_s"]),
        "final_decision": pilot.decision_record(current_decision),
        "final_precise": precise,
        "improvement_s": improvement,
        "threshold_s": TOLERANCES["optimization_improvement_s"],
        "evaluations": evaluations,
    }


def expanded_c3_budget(baseline_duration_s: float) -> dict:
    screen = {"scan_step_s": 0.01, "n_theta": 256}
    precise_settings = REFINEMENT_SETTINGS[-1]
    seed_records = []
    for seed in AUDIT_SEEDS:
        candidates, generation = pilot.generate_c3(seed)
        scored = [(float(pilot.proxy_score(item.decision)), index, item) for index, item in enumerate(candidates)]
        selected = sorted(scored, key=lambda item: (-item[0], item[1]))[:2]
        screened = []
        for proxy_score, index, candidate in selected:
            observed = pilot.evaluate(candidate.decision, screen)
            screened.append({
                "candidate_index": index,
                "proxy_score_s": proxy_score,
                "decision": pilot.decision_record(candidate.decision),
                "screen": observed,
                "_decision": candidate.decision,
            })
        best = max(screened, key=lambda item: float(item["screen"]["effective_duration_s"]))
        precise = pilot.evaluate(best["_decision"], precise_settings)
        seed_records.append({
            "seed": seed,
            "generation": generation,
            "selected": [{key: value for key, value in item.items() if not key.startswith("_")} for item in screened],
            "best_precise": precise,
            "best_decision": best["decision"],
        })
    durations = [float(item["best_precise"]["effective_duration_s"]) for item in seed_records]
    improvement = max(durations) - baseline_duration_s
    pass_flags = {
        "all_new_seeds_positive": all(value > 0.0 for value in durations),
        "no_material_improvement": improvement <= TOLERANCES["optimization_improvement_s"],
    }
    return {
        "status": "pass" if all(pass_flags.values()) else "fail",
        "seeds": AUDIT_SEEDS,
        "proxy_candidates_per_seed": pilot.N_PROXY,
        "screened_per_seed": 2,
        "seed_best_durations_s": durations,
        "positive_seed_count": sum(value > 0.0 for value in durations),
        "best_improvement_over_formal_s": improvement,
        "threshold_s": TOLERANCES["optimization_improvement_s"],
        "pass_flags": pass_flags,
        "records": seed_records,
    }


def expanded_guard_and_boundary(best_decision: pilot.Decision, baseline_duration_s: float) -> dict:
    coarse = {"scan_step_s": 0.04, "n_theta": 64}
    precise_settings = REFINEMENT_SETTINGS[-1]
    records = []
    for seed in AUDIT_SEEDS:
        candidates, generation = pilot.generate_c2(seed)
        guard = [candidate for candidate in candidates if candidate.generation["domain"] == "guard"][:8]
        for index, candidate in enumerate(guard):
            observed = pilot.evaluate(candidate.decision, coarse)
            duration = float(observed["effective_duration_s"])
            precise = pilot.evaluate(candidate.decision, precise_settings) if duration > 0.0 else None
            records.append({
                "kind": "new_seed_guard",
                "seed": seed,
                "index": index,
                "generation_summary": generation if index == 0 else None,
                "domain": formal.physical_domain(candidate.decision.heading_rad),
                "decision": pilot.decision_record(candidate.decision),
                "coarse": observed,
                "precise": precise,
            })

    parameters = pilot.q1.default_parameters()
    target_vector = parameters.target_base_center[:2] - parameters.uav_initial[:2]
    missile_vector = parameters.missile_initial[:2] - parameters.uav_initial[:2]
    centers = {
        "target": math.atan2(float(target_vector[1]), float(target_vector[0])) % (2.0 * math.pi),
        "missile": math.atan2(float(missile_vector[1]), float(missile_vector[0])) % (2.0 * math.pi),
    }
    for center_name, center in centers.items():
        for sign in (-1.0, 1.0):
            for offset in (formal.pilot.HALF_WIDTH - 0.01, formal.pilot.HALF_WIDTH, formal.pilot.HALF_WIDTH + 0.01):
                decision = pilot.Decision(
                    heading_rad=(center + sign * offset) % (2.0 * math.pi),
                    speed_mps=best_decision.speed_mps,
                    release_time_s=best_decision.release_time_s,
                    fuse_delay_s=best_decision.fuse_delay_s,
                    source_domain="E2_boundary_probe",
                )
                observed = pilot.evaluate(decision, coarse)
                duration = float(observed["effective_duration_s"])
                precise = pilot.evaluate(decision, precise_settings) if duration > 0.0 else None
                records.append({
                    "kind": "domain_boundary_probe",
                    "center": center_name,
                    "offset_rad": sign * offset,
                    "domain": formal.physical_domain(decision.heading_rad),
                    "decision": pilot.decision_record(decision),
                    "coarse": observed,
                    "precise": precise,
                })

    outside_values = []
    for item in records:
        if item["domain"] != "outside_both":
            continue
        value = item["precise"]["effective_duration_s"] if item["precise"] is not None else item["coarse"]["effective_duration_s"]
        outside_values.append(float(value))
    best_outside = max(outside_values, default=0.0)
    counterexample = best_outside > baseline_duration_s + TOLERANCES["guard_counterexample_s"]
    return {
        "status": "fail" if counterexample else "pass",
        "audit_seeds": AUDIT_SEEDS,
        "new_seed_guard_evaluations": sum(item["kind"] == "new_seed_guard" for item in records),
        "boundary_probe_evaluations": sum(item["kind"] == "domain_boundary_probe" for item in records),
        "coarse_settings": coarse,
        "positive_coarse_count": sum(float(item["coarse"]["effective_duration_s"]) > 0.0 for item in records),
        "best_outside_duration_s": best_outside,
        "formal_best_duration_s": baseline_duration_s,
        "counterexample_tolerance_s": TOLERANCES["guard_counterexample_s"],
        "outside_domain_counterexample": counterexample,
        "interpretation": "No counterexample means not found in the declared expanded audit, not exhaustive coverage proof.",
        "records": records,
    }


def path_inventory(formal_result: dict) -> dict:
    records = formal_result["multistart_records"]
    observed = {
        "C3-I_random": sum(item["source_family"] == "C3-I" and item["seed"] != "fixed_witness" for item in records),
        "C3-I_witness": sum(item["seed"] == "fixed_witness" for item in records),
        "C2_target": sum(item["source_domain"] == "target" for item in records),
        "C2_missile": sum(item["source_domain"] == "missile" for item in records),
        "C2_guard": sum(item["source_domain"] == "guard" for item in records),
        "fallback": sum(item["chosen"]["origin"] == "initial_proxy_fallback" for item in records),
        "refined": sum(item["chosen"]["origin"] == "refined" for item in records),
        "precise_finalists": len(formal_result["precise_finalists"]),
    }
    expected = {
        "C3-I_random": 6, "C3-I_witness": 1, "C2_target": 2,
        "C2_missile": 2, "C2_guard": 4, "precise_finalists": 3,
    }
    require(all(observed[key] == value for key, value in expected.items()), f"formal path inventory mismatch: {observed}")
    return {
        "status": "pass",
        "entrypoint": "src/q2/solve.py",
        "observed": observed,
        "expected": expected,
        "unexecuted_required_paths": [],
        "proxy_refinement_diagnosis": (
            "All 15 proxy refinements triggered the frozen exact-objective fallback. "
            "This makes the proxy ineffective in this run but prevents it from degrading the formal result."
        ),
    }


def build_report(result: dict) -> str:
    e1 = result["E1_IMPLEMENTATION"]
    e2 = result["E2_NUMERICAL"]
    refinement = e2["ordered_refinement"]
    independent = e2["independent_recomputation"]
    local = e2["direct_local_search"]
    expanded = e2["expanded_c3_budget"]
    guard = e2["expanded_guard"]
    return f"""# Q2 S5 实现与数值验证报告

> 内部技术证据，不是论文或队友讲解稿资产。本报告未载入、显示或使用任何外部数值答案。

## 门禁结论

- E1 实现轴：`{e1['status']}`；E2 数值轴：`{e2['status']}`；总状态：`{result['status']}`。
- 本报告只判断 Q2 是否具备 `S5→S6` 条件，不替代后续 E3 结构验证和 E4 现实映射验证。

## E1 实现正确性

- 语义、接口、边界与异常测试：`{e1['unit_suite']['tests_run']}` 项，全部通过。
- 正式入口全新复现的最大未舍入语义差：`{e1['fresh_entrypoint']['maximum_semantic_difference_unrounded']:.17g}`。
- 已覆盖 6 个随机 C3-I 起点、1 个严格内点、C2 目标/导弹/全域守卫 2/2/4 个入口、15 次代理回退和 3 个精算候选。
- 代理精修在本次正式运行中没有产生可保留的正式目标改善，但回退逻辑逐起点阻止了劣化；因此它是“无效但安全”的内部层，而不是额外正确性证据。

## E2 数值稳定性

| 核验项 | 未舍入结果 | 预设阈值 | 状态 |
|---|---:|---:|---|
| 时间步长减半、角度数加倍序列的最大相邻时长差 | `{max(refinement['consecutive_duration_differences_s'], default=0.0):.17g} s` | `≤1e-4 s` | `{refinement['status']}` |
| 各层端点相对最细层的最大差 | `{max(refinement['endpoint_differences_to_finest_s'], default=0.0):.17g} s` | `≤1e-4 s` | `{refinement['status']}` |
| 连续圆周主路径与临界角实根独立路径的时长差 | `{independent['duration_difference_s']:.17g} s` | `≤1e-4 s` | `{independent['status']}` |
| 直接连续目标局部搜索的改善 | `{local['improvement_s']:.17g} s` | `≤0.05 s` | `{local['status']}` |
| 三个新增 C3-I 种子的最佳改善 | `{expanded['best_improvement_over_formal_s']:.17g} s` | `≤0.05 s` | `{expanded['status']}` |
| 扩展 C2 守卫与分域边界反例 | `{guard['best_outside_duration_s']:.17g} s` | 不得超过正式最佳值加 `1e-4 s` | `{guard['status']}` |

所有判断使用 JSON 中的未舍入值。正式最优仍限定为固定预算下的稳定可行近优解，不宣称严格全局最优；扩展守卫未发现反例也不构成全域覆盖证明。
"""


def run(project_root: Path, formal_result_path: Path, output_path: Path, report_path: Path) -> dict:
    require(sha256_file(project_root / "data/A题.pdf") == formal.INPUT_SHA, "official input identity mismatch")
    require(sha256_file(project_root / formal.SPEC_PATH) == formal.SPEC_SHA, "formal specification identity mismatch")
    require(sha256_file(formal_result_path) == FORMAL_RESULT_SHA, "formal Q2 result identity mismatch")
    formal_result = json.loads(formal_result_path.read_text(encoding="utf-8"))
    require(formal_result.get("status") == "ok", "formal Q2 result is not passing")
    require(formal_result["identities"]["formal_spec_sha256"] == formal.SPEC_SHA, "result/specification binding mismatch")
    require(formal_result["run_identity"]["solver_sha256"] == sha256_file(project_root / "src/q2/solve.py"), "result/solver binding mismatch")
    started = time.perf_counter()

    stage("e1_semantic_unit_boundary_suite", "started")
    unit_suite = run_unit_suite(project_root)
    error_path = identity_error_path()
    inventory = path_inventory(formal_result)
    stage("e1_semantic_unit_boundary_suite", "passed", tests=unit_suite["tests_run"])

    stage("e1_fresh_formal_entrypoint", "started")
    reproduction = fresh_entrypoint_reproduction(project_root, formal_result)
    stage("e1_fresh_formal_entrypoint", "passed")

    best = formal_result["formal_best"]
    best_decision = decision_from_record(best["decision"], "E2_formal_best")
    baseline_duration = float(best["precise"]["effective_duration_s"])

    stage("e2_ordered_evaluator_refinement", "started")
    refinement = ordered_evaluator_refinement(best_decision, best)
    stage("e2_ordered_evaluator_refinement", refinement["status"])

    stage("e2_independent_critical_root_recomputation", "started")
    independent = independent_recomputation(best_decision, refinement)
    stage("e2_independent_critical_root_recomputation", independent["status"])

    stage("e2_direct_local_objective", "started")
    local = direct_local_search(best_decision, baseline_duration)
    stage("e2_direct_local_objective", local["status"], improvement_s=local["improvement_s"])

    stage("e2_expanded_c3_budget", "started")
    expanded = expanded_c3_budget(baseline_duration)
    stage("e2_expanded_c3_budget", expanded["status"], improvement_s=expanded["best_improvement_over_formal_s"])

    stage("e2_expanded_c2_guard", "started")
    guard = expanded_guard_and_boundary(best_decision, baseline_duration)
    stage("e2_expanded_c2_guard", guard["status"], counterexample=guard["outside_domain_counterexample"])

    e1 = {
        "status": "pass",
        "unit_suite": unit_suite,
        "fresh_entrypoint": reproduction,
        "error_path": error_path,
        "path_inventory": inventory,
        "units": formal_result["units"],
    }
    e2_parts = [refinement, independent, local, expanded, guard]
    e2 = {
        "status": "pass" if all(item["status"] == "pass" for item in e2_parts) else "fail",
        "tolerance_policy": {
            "declared_before_observation": True,
            "values": TOLERANCES,
            "scale_basis": (
                "Evaluator and independent tolerances are 2% of the frozen 0.005 s precise scan step; "
                "the 0.05 s optimization threshold is approximately 1% of the 4.58 s baseline and ten precise steps."
            ),
        },
        "ordered_refinement": refinement,
        "independent_recomputation": independent,
        "direct_local_search": local,
        "expanded_c3_budget": expanded,
        "expanded_guard": guard,
        "formatting_policy": "all assertions use stored unrounded float64 values; formatting is presentation only",
    }
    result = {
        "schema_version": "1.0",
        "result_id": "Q2-S5-S6-E1E2-20260827",
        "question_id": "Q2",
        "status": "pass" if e1["status"] == "pass" and e2["status"] == "pass" else "fail",
        "purpose": "internal_q2_s5_to_s6_implementation_and_numerical_gate",
        "external_numeric_results_used": False,
        "identities": {
            "official_input_sha256": formal.INPUT_SHA,
            "formal_spec_sha256": formal.SPEC_SHA,
            "formal_result_sha256": FORMAL_RESULT_SHA,
            "formal_solver_sha256": sha256_file(project_root / "src/q2/solve.py"),
            "verification_code_sha256": sha256_file(project_root / "src/q2/verify.py"),
            "unit_test_sha256": sha256_file(project_root / "src/q2/tests/test_q2.py"),
        },
        "E1_IMPLEMENTATION": e1,
        "E2_NUMERICAL": e2,
        "gate_boundary": {
            "supports": "Q2 S5 to S6 only when overall status is pass",
            "does_not_support": ["E3 structural validation", "E4 reality validation", "strict global optimum", "paper-ready validation narrative"],
        },
        "run_identity": {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "execution_kind": "deterministic_verification_with_fixed_additional_seeds",
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "audit_seeds": AUDIT_SEEDS,
            "elapsed_seconds": time.perf_counter() - started,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(json_ready(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(build_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(ROOT, ROOT / args.formal_result, ROOT / args.output, ROOT / args.report)
    except Exception as error:
        print(json.dumps({"status": "error", "type": type(error).__name__, "message": str(error)}, ensure_ascii=False), flush=True)
        return 2
    print(json.dumps({
        "status": result["status"],
        "E1_IMPLEMENTATION": result["E1_IMPLEMENTATION"]["status"],
        "E2_NUMERICAL": result["E2_NUMERICAL"]["status"],
        "output": args.output.as_posix(),
        "report": args.report.as_posix(),
    }, ensure_ascii=False), flush=True)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
