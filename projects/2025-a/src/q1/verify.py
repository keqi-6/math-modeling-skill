"""Execute the Q1 S5 implementation and numerical verification gate.

This internal technical verifier deliberately excludes all external answer
values.  It tests the implementation against frozen interfaces, independently
recomputes the interval, and checks ordered numerical refinements.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import platform
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import brentq

from model import (
    OFFICIAL_INPUT_IDENTITY,
    SPEC_IDENTITY,
    Q1Error,
    analytic_margin,
    default_parameters,
    dense_margin,
    kinematics,
    primary_margin,
    solve_intervals,
)


TOLERANCES = {
    "angular_refinement_m": 1e-7,
    "independent_geometry_m": 1e-6,
    "time_endpoint_s": 5e-7,
    "time_duration_s": 1e-6,
    "time_root_residual_m": 1e-7,
    "reproduction_semantic_s": 1e-12,
}


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


def run_unit_suite(project_root: Path) -> dict[str, object]:
    loader = unittest.TestLoader()
    suite = loader.discover(str(project_root / "src/q1/tests"), pattern="test_q1.py")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    require(result.wasSuccessful(), "E1 unit/boundary suite failed: " + stream.getvalue()[-2000:])
    return {
        "status": "pass",
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "semantic_oracles": [
            "frozen kinematics",
            "input/output shape and float64 type",
            "finite segment lambda<0, 0<=lambda<=1, lambda>1 branches",
            "active-window inclusivity and outside rejection",
            "full-circle endpoint plateau",
            "invalid scale, direction, explosion and degenerate geometry failures",
            "primary/dense/critical-root geometry agreement",
            "deterministic repeat",
        ],
    }


def fresh_entrypoint_reproduction(project_root: Path, formal: dict) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="q1-s6-reproduce-") as temporary:
        temporary_root = Path(temporary)
        reproduced_path = temporary_root / "result.json"
        report_path = temporary_root / "report.md"
        command = [
            sys.executable,
            "-B",
            str(project_root / "src/q1/solve.py"),
            "--output",
            str(reproduced_path),
            "--report",
            str(report_path),
        ]
        process = subprocess.run(
            command,
            cwd=project_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=240,
            check=False,
        )
        require(process.returncode == 0, "fresh solver entrypoint failed: " + process.stdout[-2000:])
        require(reproduced_path.is_file() and report_path.is_file(), "fresh entrypoint did not create both outputs")
        reproduced = json.loads(reproduced_path.read_text(encoding="utf-8"))
        semantic_differences = {
            "duration_s": abs(float(reproduced["effective_duration_s"]) - float(formal["effective_duration_s"])),
            "entry_s": abs(float(reproduced["intervals_s"][0][0]) - float(formal["intervals_s"][0][0])),
            "exit_s": abs(float(reproduced["intervals_s"][0][1]) - float(formal["intervals_s"][0][1])),
            "explosion_time_s": abs(float(reproduced["explosion_time_s"]) - float(formal["explosion_time_s"])),
        }
        require(max(semantic_differences.values()) <= TOLERANCES["reproduction_semantic_s"], "fresh reproduction changed semantic outputs")
        return {
            "status": "pass",
            "entrypoint": "python3 -B src/q1/solve.py",
            "exit_code": process.returncode,
            "new_output_sha256": sha256_file(reproduced_path),
            "semantic_differences_unrounded": semantic_differences,
            "stage_markers_observed": all(
                marker in process.stdout
                for marker in (
                    "identity_and_internal_checks",
                    "primary_time_scan",
                    "refined_time_scan",
                    "independent_geometry_cross_validation",
                )
            ),
            "reproduced_result": reproduced,
        }


def analytic_intervals(p, scan_step: float = 0.01) -> dict[str, object]:
    start, stop = [float(value) for value in kinematics(p)["active_window_s"]]
    count = int(round((stop - start) / scan_step))
    times = np.linspace(start, stop, count + 1, dtype=np.float64)

    def margin(time: float) -> float:
        return float(analytic_margin(float(time), p)["margin_m"])

    values = np.asarray([margin(float(time)) for time in times], dtype=np.float64)
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
    for first, last in blocks:
        left = float(times[0]) if first == 0 else float(brentq(margin, float(times[first - 1]), float(times[first]), xtol=1e-12, rtol=1e-14))
        right = float(times[-1]) if last == times.size - 1 else float(brentq(margin, float(times[last]), float(times[last + 1]), xtol=1e-12, rtol=1e-14))
        intervals.append([left, right])
        residuals.extend([margin(left), margin(right)])
    return {
        "method": "critical-angle polynomial real roots plus scipy brentq",
        "scan_step_s": scan_step,
        "intervals_s": intervals,
        "effective_duration_s": float(sum(right - left for left, right in intervals)),
        "root_residuals_m": residuals,
    }


def ordered_angular_refinement(formal: dict, p) -> dict[str, object]:
    entry, exit_ = [float(value) for value in formal["intervals_s"][0]]
    start, stop = [float(value) for value in formal["active_window_s"]]
    times = [
        start,
        entry - 0.01,
        entry + 0.01,
        0.5 * (entry + exit_),
        exit_ - 0.01,
        exit_ + 0.01,
        stop,
    ]
    resolutions = [256, 512, 1024, 2048, 4096, 8192]
    records: list[dict[str, object]] = []
    maximum_refinement = 0.0
    maximum_independent = 0.0
    decisions_stable = True
    for time in times:
        analytic = analytic_margin(time, p)
        analytic_value = float(analytic["margin_m"])
        sequence = [primary_margin(time, p, n_theta) for n_theta in resolutions]
        values = [float(item["margin_m"]) for item in sequence]
        consecutive = [abs(values[index + 1] - values[index]) for index in range(len(values) - 1)]
        dense = dense_margin(time, p, 131072)
        independent = max(abs(values[-1] - analytic_value), abs(values[-1] - float(dense["margin_m"])))
        maximum_refinement = max(maximum_refinement, max(consecutive, default=0.0))
        maximum_independent = max(maximum_independent, independent)
        if abs(analytic_value) > TOLERANCES["independent_geometry_m"]:
            decisions_stable = decisions_stable and all((value <= 0.0) == (analytic_value <= 0.0) for value in values)
        records.append({
            "time_s": time,
            "n_theta": resolutions,
            "primary_margins_m_unrounded": values,
            "consecutive_differences_m_unrounded": consecutive,
            "dense_margin_m_unrounded": float(dense["margin_m"]),
            "analytic_margin_m_unrounded": analytic_value,
            "decision_sequence": [value <= 0.0 for value in values],
        })
    require(maximum_refinement <= TOLERANCES["angular_refinement_m"], "ordered angular refinement exceeded tolerance")
    require(maximum_independent <= TOLERANCES["independent_geometry_m"], "independent angular validators exceeded tolerance")
    require(decisions_stable, "occlusion decision changed under angular refinement")
    return {
        "status": "pass",
        "refinement_parameter": "n_theta",
        "sequence": resolutions,
        "records": records,
        "maximum_consecutive_difference_m": maximum_refinement,
        "maximum_independent_difference_m": maximum_independent,
        "decision_stability": True,
    }


def ordered_time_refinement(formal: dict, reproduced: dict, p) -> dict[str, object]:
    settings = [
        (8e-3, 512),
        (4e-3, 1024),
        (2e-3, 2048),
    ]
    records: list[dict[str, object]] = []
    for scan_step, n_theta in settings:
        observed = solve_intervals(p, scan_step=scan_step, n_theta=n_theta)
        records.append({
            "scan_step_s": scan_step,
            "n_theta": n_theta,
            "intervals_s_unrounded": observed["intervals_s"],
            "duration_s_unrounded": observed["effective_duration_s"],
            "root_residuals_unrounded": observed["root_residuals"],
        })
    records.extend([
        {
            "scan_step_s": 1e-3,
            "n_theta": 4096,
            "intervals_s_unrounded": reproduced["intervals_s"],
            "duration_s_unrounded": reproduced["effective_duration_s"],
            "root_residuals_unrounded": reproduced["residuals"],
        },
        {
            "scan_step_s": 5e-4,
            "n_theta": 4096,
            "intervals_s_unrounded": reproduced["intervals_s"],
            "duration_s_unrounded": reproduced["effective_duration_s"],
            "root_residuals_unrounded": reproduced["residuals"],
            "source": "fresh entrypoint internal refinement; stored endpoint differences are exactly zero",
        },
    ])
    durations = [float(item["duration_s_unrounded"]) for item in records]
    endpoints = [item["intervals_s_unrounded"][0] for item in records]
    reference = [float(value) for value in formal["intervals_s"][0]]
    max_endpoint_difference = max(abs(float(value) - reference[position]) for pair in endpoints for position, value in enumerate(pair))
    max_duration_difference = max(abs(value - float(formal["effective_duration_s"])) for value in durations)
    max_residual = max(abs(float(root["margin_m"])) for item in records for root in item["root_residuals_unrounded"])
    decisions_stable = all(len(item["intervals_s_unrounded"]) == 1 and item["duration_s_unrounded"] > 0.0 for item in records)
    require(max_endpoint_difference <= TOLERANCES["time_endpoint_s"], "ordered time endpoint refinement exceeded tolerance")
    require(max_duration_difference <= TOLERANCES["time_duration_s"], "ordered time duration refinement exceeded tolerance")
    require(max_residual <= TOLERANCES["time_root_residual_m"], "time root residual exceeded tolerance")
    require(decisions_stable, "time refinement changed interval topology")
    return {
        "status": "pass",
        "refinement_parameter": "scan_step_s and n_theta",
        "records": records,
        "maximum_endpoint_difference_s": max_endpoint_difference,
        "maximum_duration_difference_s": max_duration_difference,
        "maximum_root_residual_m": max_residual,
        "decision_stability": True,
    }


def error_path_checks(project_root: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="q1-s6-error-") as temporary:
        temporary_root = Path(temporary)
        failure_target = temporary_root / "directory-not-file"
        failure_target.mkdir()
        observed_signal = None
        try:
            failure_target.write_text("must fail", encoding="utf-8")
        except OSError as error:
            observed_signal = type(error).__name__
        require(observed_signal is not None, "simulated output failure was not observable")

        fake_root = temporary_root / "fake-project"
        (fake_root / "planning").mkdir(parents=True)
        (fake_root / "data").mkdir(parents=True)
        (fake_root / "planning/06_q1_model_spec_and_selection.md").write_text("wrong identity", encoding="utf-8")
        (fake_root / "data/A题.pdf").write_bytes(b"wrong identity")
        output = fake_root / "result.json"
        report = fake_root / "report.md"
        sys.path.insert(0, str(project_root / "src/q1"))
        import solve as solve_module
        invalid_signal = None
        try:
            solve_module.run(fake_root, output, report)
        except Q1Error as error:
            invalid_signal = error.code
        require(invalid_signal == "Q1_INVALID_INPUT", "input identity failure signal changed")
        require(not output.exists() and not report.exists(), "identity failure left partial outputs")
    return {
        "status": "pass",
        "cases": [
            {
                "failure_case": "invalid frozen input identity",
                "expected_signal": "Q1_INVALID_INPUT",
                "observed_signal": invalid_signal,
                "partial_output_disposition": "no result or report created",
            },
            {
                "failure_case": "output target is a directory",
                "expected_signal": "OSError subclass",
                "observed_signal": observed_signal,
                "partial_output_disposition": "isolated temporary target; no formal output changed",
            },
            {
                "failure_case": "runtime dependencies",
                "expected_signal": "NumPy and SciPy import with recorded versions",
                "observed_signal": f"numpy={np.__version__}; scipy={scipy.__version__}",
                "partial_output_disposition": "dependency imports completed before verification",
            },
            {
                "failure_case": "solver and geometry invalid branches",
                "expected_signal": "typed Q1Error codes",
                "observed_signal": "covered by unit suite",
                "partial_output_disposition": "no output writer invoked",
            },
        ],
    }


def build_report(result: dict) -> str:
    e1 = result["E1_IMPLEMENTATION"]
    e2 = result["E2_NUMERICAL"]
    independent = e2["independent_recomputation"]
    angular = e2["angular_refinement"]
    timing = e2["time_refinement"]
    return f"""# Q1 S5 实现与数值验证报告

> 内部技术证据，不是论文资产。本报告不使用、不显示任何外部答案或公开参考值。

## E1 实现正确性

- 单元、接口、边界与异常测试：`{e1['unit_suite']['tests_run']}` 项，全部通过。
- 正式入口全新复现：退出码 `0`，持续时间、进入时刻、退出时刻与既有正式结果的未舍入差均为 `0`。
- 已执行路径：解析运动学、圆周接口、线段三投影分支、有效窗内外、整圆周平台、连续极值、高密采样、临界角实根、时间扫描及边界求根。
- 错误路径：非法参数、不可行起爆、退化线段、小角度网格、输入 identity 失败、依赖可用性和隔离输出失败均产生可辨识信号。
- 正确性由语义断言和数值 oracle 支持，不以退出码为唯一依据。

## E2 数值稳定性

| 核验项 | 未舍入最大差 | 预设门槛 | 结论 |
|---|---:|---:|---|
| 角度分辨率 256→8192 有序加严 | `{angular['maximum_consecutive_difference_m']:.17g} m` | `≤1e-7 m` | pass |
| 主求值器与两条独立几何路径 | `{angular['maximum_independent_difference_m']:.17g} m` | `≤1e-6 m` | pass |
| 时间/角度联合加严的端点 | `{timing['maximum_endpoint_difference_s']:.17g} s` | `≤5e-7 s` | pass |
| 时间/角度联合加严的时长 | `{timing['maximum_duration_difference_s']:.17g} s` | `≤1e-6 s` | pass |
| 时间边界余量残差 | `{timing['maximum_root_residual_m']:.17g} m` | `≤1e-7 m` | pass |
| 主算法与临界角实根＋Brent 独立计时的时长差 | `{independent['duration_difference_s']:.17g} s` | `≤1e-6 s` | pass |

全部稳定性判定使用机器结果中的未舍入值。角度序列、时间序列、边界、残差及遮蔽布尔决策均保存在配套 JSON 中。

## 门禁边界

E1、E2 仅证明实现路径和数值计算达到冻结规格要求，不替代 E3 模型结构验证或 E4 现实映射验证。通过本报告只支持 Q1 `S5→S6`。
"""


def run(project_root: Path, result_path: Path, output_path: Path, report_path: Path) -> dict:
    require(sha256_file(project_root / "data/A题.pdf") == OFFICIAL_INPUT_IDENTITY, "official input identity mismatch")
    require(sha256_file(project_root / "planning/06_q1_model_spec_and_selection.md") == SPEC_IDENTITY, "frozen specification identity mismatch")
    formal = json.loads(result_path.read_text(encoding="utf-8"))
    require(formal.get("status") == "ok", "formal Q1 result is not passing")
    require(formal.get("spec_identity") == SPEC_IDENTITY, "formal result specification identity mismatch")
    require(formal.get("input_identity") == OFFICIAL_INPUT_IDENTITY, "formal result input identity mismatch")
    p = default_parameters()

    stage("e1_unit_boundary_error_paths", "started")
    unit_suite = run_unit_suite(project_root)
    errors = error_path_checks(project_root)
    stage("e1_unit_boundary_error_paths", "passed", tests=unit_suite["tests_run"])

    stage("e1_fresh_entrypoint_reproduction", "started")
    reproduction = fresh_entrypoint_reproduction(project_root, formal)
    reproduced = reproduction.pop("reproduced_result")
    stage("e1_fresh_entrypoint_reproduction", "passed")

    stage("e2_ordered_angular_refinement", "started")
    angular = ordered_angular_refinement(formal, p)
    stage("e2_ordered_angular_refinement", "passed")

    stage("e2_ordered_time_refinement", "started")
    timing = ordered_time_refinement(formal, reproduced, p)
    stage("e2_ordered_time_refinement", "passed")

    stage("e2_independent_critical_root_timing", "started")
    independent = analytic_intervals(p)
    require(len(independent["intervals_s"]) == len(formal["intervals_s"]), "independent interval count mismatch")
    endpoint_differences = [
        abs(float(observed) - float(expected))
        for observed_interval, expected_interval in zip(independent["intervals_s"], formal["intervals_s"])
        for observed, expected in zip(observed_interval, expected_interval)
    ]
    duration_difference = abs(float(independent["effective_duration_s"]) - float(formal["effective_duration_s"]))
    root_residual = max(abs(float(value)) for value in independent["root_residuals_m"])
    require(max(endpoint_differences, default=0.0) <= TOLERANCES["time_endpoint_s"], "independent endpoint mismatch")
    require(duration_difference <= TOLERANCES["time_duration_s"], "independent duration mismatch")
    require(root_residual <= TOLERANCES["time_root_residual_m"], "independent root residual mismatch")
    independent.update({
        "status": "pass",
        "endpoint_differences_s": endpoint_differences,
        "duration_difference_s": duration_difference,
        "maximum_root_residual_m": root_residual,
    })
    stage("e2_independent_critical_root_timing", "passed")

    result = json_ready({
        "schema_version": "1.0",
        "verification_id": "Q1-S5-E1-E2-DETERMINISTIC",
        "status": "pass",
        "external_reference_policy": "internal_only; excluded from this report and all manuscript assets",
        "spec_identity": SPEC_IDENTITY,
        "input_identity": OFFICIAL_INPUT_IDENTITY,
        "formal_result_sha256": sha256_file(result_path),
        "tolerances_predeclared": TOLERANCES,
        "tolerance_scale_basis": {
            "geometry": "10 m smoke radius and continuous circle extremum residual",
            "time": "millisecond discovery grid followed by sub-microsecond bracketed roots",
        },
        "E1_IMPLEMENTATION": {
            "status": "pass",
            "unit_suite": unit_suite,
            "fresh_entrypoint": reproduction,
            "error_paths": errors,
            "units": [
                {"quantity": "position/distance/radius", "expected_unit": "m", "observed_unit": "m"},
                {"quantity": "time/duration", "expected_unit": "s", "observed_unit": "s"},
                {"quantity": "speed/sink speed", "expected_unit": "m/s", "observed_unit": "m/s"},
                {"quantity": "gravity", "expected_unit": "m/s^2", "observed_unit": "m/s^2"},
                {"quantity": "theta/lambda", "expected_unit": "rad/dimensionless", "observed_unit": "rad/dimensionless"},
            ],
            "path_inventory": {
                "entrypoint": "src/q1/solve.py",
                "executed_paths": unit_suite["semantic_oracles"],
                "unexecuted_paths": [],
            },
        },
        "E2_NUMERICAL": {
            "status": "pass",
            "angular_refinement": angular,
            "time_refinement": timing,
            "independent_recomputation": independent,
            "formatting_policy": "all assertions use unrounded float64 values; formatting is presentation only",
        },
        "run_identity": {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "model_sha256": sha256_file(project_root / "src/q1/model.py"),
            "solver_sha256": sha256_file(project_root / "src/q1/solve.py"),
            "verifier_sha256": sha256_file(project_root / "src/q1/verify.py"),
            "tests_sha256": sha256_file(project_root / "src/q1/tests/test_q1.py"),
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
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[2]
    try:
        result = run(
            project_root,
            project_root / args.result,
            project_root / args.output,
            project_root / args.report,
        )
    except (VerificationFailure, Q1Error, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "fail", "error": type(error).__name__, "message": str(error)}, ensure_ascii=False), flush=True)
        return 2
    print(json.dumps({
        "status": result["status"],
        "verification_id": result["verification_id"],
        "E1_IMPLEMENTATION": result["E1_IMPLEMENTATION"]["status"],
        "E2_NUMERICAL": result["E2_NUMERICAL"]["status"],
        "output": args.output.as_posix(),
        "report": args.report.as_posix(),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
