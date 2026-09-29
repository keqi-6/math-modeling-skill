"""Run the deterministic Q1 S4 implementation gate and write inspectable outputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy

from model import (
    OFFICIAL_INPUT_IDENTITY,
    SPEC_IDENTITY,
    Q1Error,
    center_point_intervals,
    default_parameters,
    geometry_cross_validation,
    internal_checks,
    kinematics,
    solve_intervals,
)


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


def progress_reporter(phase: str):
    def report(completed: int, total: int) -> None:
        print(json.dumps({
            "stage": phase,
            "completed": completed,
            "total": total,
            "progress": round(completed / total, 6),
        }, ensure_ascii=False), flush=True)
    return report


def build_report(result: dict, output_path: Path) -> str:
    interval = result["intervals_s"][0]
    convergence = result["convergence"]
    geometry = result["geometry_cross_validation"]
    maximum_dense = max(item["abs_primary_dense_m"] for item in geometry)
    maximum_analytic = max(item["abs_primary_analytic_m"] for item in geometry)
    maximum_refined = max(item["abs_primary_refined_m"] for item in geometry)
    pruning = result["geometry_pruning"]["primary"]
    return f"""# Q1 实现与 S4→S5 技术核销

> 本文是可检查的技术证据，不是论文正文。正式实现绑定 `SPEC-Q1-1.0`。

## 运行身份

- 执行类型：确定性，无随机种子。
- Python：`{result['run_identity']['python']}`。
- NumPy：`{result['run_identity']['numpy']}`；SciPy：`{result['run_identity']['scipy']}`。
- 规格 SHA-256：`{result['spec_identity']}`。
- 官方题面 SHA-256：`{result['input_identity']}`。
- 代码 SHA-256：`{result['run_identity']['model_sha256']}`、`{result['run_identity']['solver_sha256']}`。
- 机器结果：`{output_path.as_posix()}`。

## 正式主链

主求值器按上下圆周 `4096` 个周期节点发现全部局部最大值候选，并对每个候选执行有界连续角度求精；时间引擎以 `1e-3 s` 扫描发现区间，用二分同时满足 `1e-9 s` 时间括区间和 `1e-7 m` 余量残差。`5e-4 s` 重扫只用于收敛复核。

完整遮蔽的坐标盒必要条件把昂贵扫描从 `{pruning['active_window_s']}` s 安全缩到 `{pruning['possible_window_s']}` s，裁去 `{100.0 * pruning['pruned_fraction']:.3f}%` 的有效窗；半径与右端点分别向外保护 `{pruning['length_expansion_m']:.1e} m`、`{pruning['time_expansion_s']:.1e} s`。该窗口只排除必不可能时刻，异常时回退完整有效窗，不改变正式余量或根求精。

## Q1 结果

- 投放点：`{result['release_point_m']}` m。
- 起爆时刻：`{result['explosion_time_s']:.12f}` s。
- 起爆点：`{result['explosion_point_m']}` m。
- 烟幕有效窗：`{result['active_window_s']}` s。
- 完整圆柱遮蔽区间：`[{interval[0]:.12f}, {interval[1]:.12f}]` s。
- 正式有效时长：`{result['effective_duration_s']:.12f}` s。
- 中心点错误对照：`{result['center_point_duration_s']:.12f}` s，仅作诊断。

## 数值交叉与收敛

| 核销项 | 观测值 | 门槛 | 状态 |
|---|---:|---:|---|
| 4096→8192 最大余量差 | `{maximum_refined:.3e} m` | `≤1e-7 m` | `{convergence['angular_status']}` |
| 主求值器→131072 点采样最大差 | `{maximum_dense:.3e} m` | `≤1e-6 m` | `{convergence['dense_status']}` |
| 主求值器→解析实根法最大差 | `{maximum_analytic:.3e} m` | `≤1e-6 m` | `{convergence['analytic_status']}` |
| `1e-3→5e-4 s` 总时长差 | `{convergence['duration_difference_s']:.3e} s` | `≤1e-6 s` | `{convergence['time_status']}` |
| 外部回归差 | `{convergence['regression_difference_s']:.3e} s` | `≤1e-3 s` | `{convergence['regression_status']}` |

- 无变号切触检查：主网格检查 `{result['time_event_diagnostics']['primary_local_minimum_checks']}` 个正值离散局部极小值，恢复 `{result['time_event_diagnostics']['primary_recovered_unsampled_intervals']}` 个漏采区间；加密网格对应为 `{result['time_event_diagnostics']['refined_local_minimum_checks']}` 与 `{result['time_event_diagnostics']['refined_recovered_unsampled_intervals']}`。

根残差、区间端点差、各时刻最坏角及三路原始值完整保存在机器结果中。三路一致性只说明实现精度；模型有效性仍需在后续 E3/E4 中由语义、约束、假设和稳健性证明。

## 门禁结论

`implementation_ref` 所需实现已形成，内部检查和本阶段数值核销均通过。该结论只支持 Q1 `S4→S5`，不提前宣称 E1/E2、S6 或最终结果验收完成。
"""


def run(project_root: Path, output_path: Path, report_path: Path) -> dict:
    spec_path = project_root / "planning/06_q1_model_spec_and_selection.md"
    input_path = project_root / "data/A题.pdf"
    model_path = project_root / "src/q1/model.py"
    solver_path = project_root / "src/q1/solve.py"
    if sha256_file(spec_path) != SPEC_IDENTITY:
        raise Q1Error("Q1_INVALID_INPUT", "frozen specification identity mismatch")
    if sha256_file(input_path) != OFFICIAL_INPUT_IDENTITY:
        raise Q1Error("Q1_INVALID_INPUT", "official input identity mismatch")

    parameters = default_parameters()
    print(json.dumps({"stage": "identity_and_internal_checks", "status": "started"}, ensure_ascii=False), flush=True)
    checks = internal_checks(parameters)
    info = kinematics(parameters)
    print(json.dumps({"stage": "identity_and_internal_checks", "status": "passed"}, ensure_ascii=False), flush=True)
    print(json.dumps({"stage": "primary_time_scan", "status": "started"}, ensure_ascii=False), flush=True)
    primary = solve_intervals(
        parameters,
        scan_step=1e-3,
        n_theta=4096,
        progress=progress_reporter("primary_time_scan"),
    )
    print(json.dumps({"stage": "primary_time_scan", "status": "passed"}, ensure_ascii=False), flush=True)
    print(json.dumps({"stage": "refined_time_scan", "status": "started"}, ensure_ascii=False), flush=True)
    refined_time = solve_intervals(
        parameters,
        scan_step=5e-4,
        n_theta=4096,
        progress=progress_reporter("refined_time_scan"),
    )
    print(json.dumps({"stage": "refined_time_scan", "status": "passed"}, ensure_ascii=False), flush=True)
    if len(primary["intervals_s"]) != len(refined_time["intervals_s"]):
        raise Q1Error("Q1_INTERVAL_NONCONVERGENCE", "time refinement changed interval count")
    endpoint_differences = [
        abs(a - b)
        for first, second in zip(primary["intervals_s"], refined_time["intervals_s"])
        for a, b in zip(first, second)
    ]
    duration_difference = abs(primary["effective_duration_s"] - refined_time["effective_duration_s"])
    if max(endpoint_differences, default=0.0) > 5e-7 or duration_difference > 1e-6:
        raise Q1Error("Q1_INTERVAL_NONCONVERGENCE", "time-grid refinement exceeded tolerance")

    validation_times = sorted({
        float(info["active_window_s"][0]),
        float(info["active_window_s"][1]),
        *[float(value) for interval in primary["intervals_s"] for value in interval],
        *[float(sum(interval) / 2.0) for interval in primary["intervals_s"]],
    })
    print(json.dumps({"stage": "independent_geometry_cross_validation", "status": "started"}, ensure_ascii=False), flush=True)
    geometry = geometry_cross_validation(validation_times, parameters)
    maximum_refined = max(item["abs_primary_refined_m"] for item in geometry)
    maximum_dense = max(item["abs_primary_dense_m"] for item in geometry)
    maximum_analytic = max(item["abs_primary_analytic_m"] for item in geometry)
    if maximum_refined > 1e-7:
        raise Q1Error("Q1_ANGULAR_NONCONVERGENCE", "4096/8192 angular refinement mismatch")
    if maximum_dense > 1e-6 or maximum_analytic > 1e-6:
        raise Q1Error("Q1_VALIDATOR_MISMATCH", "independent geometry validator mismatch")
    if any(abs(item["margin_m"]) > 1e-7 for item in primary["root_residuals"]):
        raise Q1Error("Q1_TIME_ROOT_UNRESOLVED", "stored root residual exceeds tolerance")
    print(json.dumps({"stage": "independent_geometry_cross_validation", "status": "passed"}, ensure_ascii=False), flush=True)

    regression_difference = abs(primary["effective_duration_s"] - 1.391643)
    if regression_difference > 1e-3:
        raise Q1Error("Q1_REGRESSION_WARNING", "Q1 duration differs from the external reference")
    center = center_point_intervals(parameters)

    result = {
        "schema_version": "1.0",
        "result_id": "Q1-SPEC-Q1-1.0-DETERMINISTIC",
        "status": "ok",
        "spec_identity": SPEC_IDENTITY,
        "input_identity": OFFICIAL_INPUT_IDENTITY,
        **json_ready(info),
        "intervals_s": primary["intervals_s"],
        "effective_duration_s": primary["effective_duration_s"],
        "center_point_duration_s": center["effective_duration_s"],
        "center_point_diagnostic_only": True,
        "worst_geometry": geometry,
        "geometry_cross_validation": geometry,
        "residuals": primary["root_residuals"],
        "time_event_diagnostics": {
            "primary_local_minimum_checks": primary["local_minimum_checks"],
            "primary_recovered_unsampled_intervals": primary["recovered_unsampled_interval_count"],
            "refined_local_minimum_checks": refined_time["local_minimum_checks"],
            "refined_recovered_unsampled_intervals": refined_time["recovered_unsampled_interval_count"],
        },
        "geometry_pruning": {
            "primary": primary["geometry_pruning"],
            "refined": refined_time["geometry_pruning"],
            "primary_scan_count": primary["scan_count"],
            "refined_scan_count": refined_time["scan_count"],
            "unpruned_primary_scan_count": int(round(parameters.smoke_duration / 1e-3)) + 1,
            "unpruned_refined_scan_count": int(round(parameters.smoke_duration / 5e-4)) + 1,
        },
        "convergence": {
            "angular_4096_to_8192_max_difference_m": maximum_refined,
            "primary_to_dense_max_difference_m": maximum_dense,
            "primary_to_analytic_max_difference_m": maximum_analytic,
            "endpoint_differences_s": endpoint_differences,
            "duration_difference_s": duration_difference,
            "regression_reference_s": 1.391643,
            "regression_difference_s": regression_difference,
            "angular_status": "pass",
            "dense_status": "pass",
            "analytic_status": "pass",
            "time_status": "pass",
            "regression_status": "pass",
        },
        "internal_checks": checks,
        "warnings": ["External 1.391643 s is a regression reference, not an official unique answer."],
        "failure_code": None,
        "run_identity": {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "execution_kind": "deterministic",
            "seed": "not_applicable",
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "model_sha256": sha256_file(model_path),
            "solver_sha256": sha256_file(solver_path),
            "spec_sha256": SPEC_IDENTITY,
            "input_sha256": OFFICIAL_INPUT_IDENTITY,
            "parameters": json_ready(parameters.__dict__),
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(build_report(result, output_path), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    project_root = Path(__file__).resolve().parents[2]
    try:
        result = run(project_root, project_root / args.output, project_root / args.report)
    except Q1Error as error:
        print(json.dumps({"status": "fail", "failure_code": error.code, "message": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({
        "status": result["status"],
        "effective_duration_s": result["effective_duration_s"],
        "intervals_s": result["intervals_s"],
        "output": args.output.as_posix(),
        "report": args.report.as_posix(),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
