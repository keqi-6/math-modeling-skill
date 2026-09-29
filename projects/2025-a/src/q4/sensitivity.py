"""Mechanism-aware fixed-policy sensitivity for Q4."""
from __future__ import annotations

import argparse
import hashlib
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
from src.q4 import solve  # noqa: E402

SPEC_ID = "SPEC-Q4-VERIFY-2.0"
SETTINGS = {
    "name": "q4_fixed_policy_window_sensitivity",
    "scan_step_s": 0.02,
    "n_theta": 128,
    "n_levels": 9,
    "root_time_tolerance_s": 2e-6,
    "margin_tolerance_m": 2e-6,
    "surface_refinement": False,
}
CONFIRM_SETTINGS = dict(solve.PRECISE, name="q4_sensitivity_critical_confirmation")
GRIDS = {
    "heading_deg": (-0.2, -0.1, 0.1, 0.2),
    "speed_mps": (-1.0, -0.5, 0.5, 1.0),
    "release_time_s": (-0.1, -0.05, 0.05, 0.1),
    "fuse_delay_s": (-0.1, -0.05, 0.05, 0.1),
}
FACTOR_ZH = {
    "heading_deg": "航向角",
    "speed_mps": "飞行速度",
    "release_time_s": "投放时刻",
    "fuse_delay_s": "引信时长",
}
TOPOLOGY_ZH = {
    "retained": "窗口保留",
    "weakened_below_90_percent": "窗口明显缩短",
    "window_lost": "窗口消失",
}


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
        "q4_sensitivity_nominal", 0,
    )
    solve.validate(decision)
    return payload, decision


def perturb(decision, platform_index: int, factor: str, offset: float, ordinal: int):
    headings = list(decision.headings_rad)
    speeds = list(decision.speeds_mps)
    release = list(decision.release_times_s)
    fuse = list(decision.fuse_delays_s)
    if factor == "heading_deg":
        headings[platform_index] = (headings[platform_index] + math.radians(offset)) % (2 * math.pi)
    elif factor == "speed_mps":
        speeds[platform_index] += offset
    elif factor == "release_time_s":
        release[platform_index] += offset
    elif factor == "fuse_delay_s":
        fuse[platform_index] += offset
    else:
        raise ValueError(factor)
    return solve.Decision(tuple(headings), tuple(speeds), tuple(release), tuple(fuse), f"q4_sensitivity_{factor}", ordinal)


def window_record(value, nominal_window, nominal_duration):
    intervals = value["intervals_s"]
    duration = value["effective_duration_s"]
    retention = duration / nominal_duration if nominal_duration > 0 else math.nan
    if not intervals:
        topology = "window_lost"
        entry_shift = exit_shift = None
    else:
        topology = "retained" if retention >= 0.9 else "weakened_below_90_percent"
        entry_shift = intervals[0][0] - nominal_window[0]
        exit_shift = intervals[-1][1] - nominal_window[1]
    return {
        "intervals_s": intervals,
        "interval_count": len(intervals),
        "duration_s": duration,
        "retention_ratio": retention,
        "entry_shift_s": entry_shift,
        "exit_shift_s": exit_shift,
        "topology": topology,
    }


def critical_search(decision, platform_index, factor, direction, maximum, nominal_duration, mesh, cache):
    def evaluate(magnitude):
        key = (platform_index, factor, round(direction * magnitude, 12))
        if key not in cache:
            candidate = perturb(decision, platform_index, factor, direction * magnitude, 100000 + len(cache))
            try:
                solve.validate(candidate)
                value = solve.solve_intervals(candidate, SETTINGS, (platform_index,), mesh)
                cache[key] = (value["effective_duration_s"] / nominal_duration, len(value["intervals_s"]) == 0)
            except solve.Q4Error:
                cache[key] = (0.0, True)
        return cache[key]

    samples = []
    for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
        retention, lost = evaluate(maximum * fraction)
        samples.append({"fraction": fraction, "offset": direction * maximum * fraction, "retention_ratio": retention, "window_lost": lost})
    monotone = all(samples[i + 1]["retention_ratio"] <= samples[i]["retention_ratio"] + 2e-3 for i in range(4))

    def locate(predicate):
        low, high = 0.0, maximum
        if not monotone or not predicate(*evaluate(high)):
            return None
        for _ in range(8):
            middle = (low + high) / 2
            if predicate(*evaluate(middle)):
                high = middle
            else:
                low = middle
        return direction * high

    return {
        "direction": "positive" if direction > 0 else "negative",
        "maximum_registered_offset": direction * maximum,
        "monotone_nonincreasing_on_samples": monotone,
        "samples": samples,
        "retention_90_boundary_offset": locate(lambda retention, lost: retention <= 0.9),
        "window_loss_boundary_offset": locate(lambda retention, lost: lost),
    }


def make_report(result):
    worst = result["worst_scenario"]
    lines = [
        "# Q4 固定方案服务窗口灵敏度", "",
        f"在同一灵敏度离散层下，名义联合遮蔽时长为 `{result['nominal']['joint_duration_s']:.9f} s`。固定十二变量名义方案后，共复算 48 个单因素扰动情景；正式结果仍为 `{result['nominal']['formal_densified_duration_s']:.12f} s`，本分析不改解。", "",
        "## 先看最差情景", "",
        f"最差情景是 {worst['platform']} 的{FACTOR_ZH[worst['factor']]}偏移 `{worst['offset']:+g}`：该平台服务窗由 `{worst['nominal_platform_window']['duration_s']:.6f} s` 变为 `{worst['platform_window']['duration_s']:.6f} s`，保留率 `{100 * worst['platform_window']['retention_ratio']:.2f}%`；联合总时长变为 `{worst['joint_duration_s']:.6f} s`。因此不能把当前方案概括为“在登记扰动带内统一稳定”。", "",
        "这里最重要的不是一个总时长百分比，而是哪个平台的哪段服务窗先缩短或消失。联合解的三个时窗彼此分离，所以单个平台失稳会直接表现为对应时窗的损失。", "",
        "## 十二组风险排序", "",
        "| 排名 | 平台—变量 | 最差方向 | 最低窗口保留率 | 窗口状态 |", "|---:|---|---:|---:|---|",
    ]
    for rank, item in enumerate(result["risk_ranking"], 1):
        lines.append(f"| {rank} | {item['platform']}—{FACTOR_ZH[item['factor']]} | `{item['worst_offset']:+g}` | {100 * item['minimum_window_retention_ratio']:.2f}% | {TOPOLOGY_ZH[item['worst_topology']]} |")
    lines.extend(["", "## 高风险组合的临界偏移", ""])
    for item in result["critical_offsets"]:
        lines.append(f"- {item['platform']}—{FACTOR_ZH[item['factor']]}：")
        for direction in item["directions"]:
            label = "正向" if direction["direction"] == "positive" else "负向"
            boundary = direction["retention_90_boundary_offset"]
            loss = direction["window_loss_boundary_offset"]
            boundary_text = "登记范围内未定位" if boundary is None else f"约 `{boundary:+.6g}`"
            loss_text = "登记范围内未出现" if loss is None else f"约 `{loss:+.6g}`"
            monotone_text = "样本单调" if direction["monotone_nonincreasing_on_samples"] else "样本非单调，禁止二分外推"
            lines.append(f"  - {label}：90% 保留边界 {boundary_text}；窗口消失边界 {loss_text}；{monotone_text}。")
        confirmations = item["dense_confirmation"]
        lines.append(f"  - 加密复核：该组所列临界点共 `{len(confirmations)}` 个，均已用 `256×17` 表面和 `0.01 s` 扫描重算；详细保留率见 JSON。")
    lines.extend([
        "", "## 怎样理解这项检验", "",
        "航向和速度主要改变烟团相对视线的横向位置，投放时刻与引信时长还会同时改变起爆时刻、起爆高度及随后下沉轨迹。因此，同样大小的参数偏移不会产生同样的窗口变化；入口和出口的漂移也可能不对称。表中的临界值只是当前固定方案在登记局部范围内的数值诊断。", "",
        "本分析没有在扰动后重新搜索，所以不能据此断言新最优解怎样变化；扰动范围也不是概率分布或现实误差模型。Q4 中暴露出的差异化服务窗口稳定性，可为下一问考虑资源分工提供启发，但这里仍只回答 Q4。", "",
    ])
    return "\n".join(lines)


def run(output: Path, report_path: Path):
    started = time.perf_counter()
    payload, decision = load()
    mesh = solve.q3.surface_mesh(SETTINGS["n_theta"], SETTINGS["n_levels"])
    nominal_joint = solve.solve_intervals(decision, SETTINGS, mesh=mesh)
    nominal_platforms = [solve.solve_intervals(decision, SETTINGS, (i,), mesh) for i in range(3)]
    records = []
    cache = {}
    ordinal = 0
    for platform_index, name in enumerate(solve.NAMES):
        nominal_window = nominal_platforms[platform_index]["intervals_s"][0]
        nominal_duration = nominal_platforms[platform_index]["effective_duration_s"]
        for factor, offsets in GRIDS.items():
            for offset in offsets:
                ordinal += 1
                candidate = perturb(decision, platform_index, factor, offset, ordinal)
                try:
                    solve.validate(candidate)
                    joint = solve.solve_intervals(candidate, SETTINGS, mesh=mesh)
                    individual = solve.solve_intervals(candidate, SETTINGS, (platform_index,), mesh)
                    window = window_record(individual, nominal_window, nominal_duration)
                    cache[(platform_index, factor, round(offset, 12))] = (window["retention_ratio"], window["interval_count"] == 0)
                    records.append({
                        "scenario_id": ordinal, "status": "feasible", "platform": name,
                        "platform_index": platform_index, "factor": factor, "offset": offset,
                        "joint_duration_s": joint["effective_duration_s"], "joint_intervals_s": joint["intervals_s"],
                        "joint_interval_count": len(joint["intervals_s"]),
                        "joint_change_s": joint["effective_duration_s"] - nominal_joint["effective_duration_s"],
                        "joint_retention_ratio": joint["effective_duration_s"] / nominal_joint["effective_duration_s"],
                        "nominal_platform_window": {"intervals_s": nominal_platforms[platform_index]["intervals_s"], "duration_s": nominal_duration},
                        "platform_window": window,
                    })
                except solve.Q4Error as error:
                    records.append({"scenario_id": ordinal, "status": "infeasible", "platform": name, "platform_index": platform_index, "factor": factor, "offset": offset, "failure_code": error.code, "message": str(error)})

    feasible = [item for item in records if item["status"] == "feasible"]
    worst = min(feasible, key=lambda item: item["platform_window"]["retention_ratio"])
    ranking = []
    for platform_index, name in enumerate(solve.NAMES):
        for factor in GRIDS:
            group = [item for item in feasible if item["platform_index"] == platform_index and item["factor"] == factor]
            item = min(group, key=lambda row: row["platform_window"]["retention_ratio"])
            ranking.append({
                "platform": name, "platform_index": platform_index, "factor": factor,
                "worst_offset": item["offset"],
                "minimum_window_retention_ratio": item["platform_window"]["retention_ratio"],
                "worst_topology": item["platform_window"]["topology"],
                "maximum_absolute_entry_shift_s": max(abs(row["platform_window"]["entry_shift_s"] or 0.0) for row in group),
                "maximum_absolute_exit_shift_s": max(abs(row["platform_window"]["exit_shift_s"] or 0.0) for row in group),
            })
    ranking.sort(key=lambda item: item["minimum_window_retention_ratio"])

    critical = []
    confirm_mesh = solve.q3.surface_mesh(CONFIRM_SETTINGS["n_theta"], CONFIRM_SETTINGS["n_levels"])
    for risk in ranking[:3]:
        maximum = max(abs(value) for value in GRIDS[risk["factor"]])
        nominal_duration = nominal_platforms[risk["platform_index"]]["effective_duration_s"]
        directions = [critical_search(decision, risk["platform_index"], risk["factor"], direction, maximum, nominal_duration, mesh, cache) for direction in (-1, 1)]
        dense_confirmation = []
        dense_nominal = solve.solve_intervals(decision, CONFIRM_SETTINGS, (risk["platform_index"],), confirm_mesh)["effective_duration_s"]
        for direction in directions:
            for boundary_kind in ("retention_90_boundary_offset", "window_loss_boundary_offset"):
                offset = direction[boundary_kind]
                if offset is None:
                    continue
                candidate = perturb(decision, risk["platform_index"], risk["factor"], offset, 200000 + len(dense_confirmation))
                value = solve.solve_intervals(candidate, CONFIRM_SETTINGS, (risk["platform_index"],), confirm_mesh)
                dense_confirmation.append({
                    "direction": direction["direction"], "boundary_kind": boundary_kind,
                    "offset": offset, "duration_s": value["effective_duration_s"],
                    "retention_ratio": value["effective_duration_s"] / dense_nominal,
                    "window_lost": len(value["intervals_s"]) == 0,
                })
        critical.append({"platform": risk["platform"], "platform_index": risk["platform_index"], "factor": risk["factor"], "directions": directions, "dense_confirmation_settings": CONFIRM_SETTINGS, "dense_confirmation": dense_confirmation})

    result = {
        "schema_version": "2.0", "spec_id": SPEC_ID,
        "result_id": "Q4-FIXED-POLICY-WINDOW-SENSITIVITY-20260828",
        "status": "pass", "method_role": "diagnostic_fixed_policy_sensitivity",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_identity": {name: sha(ROOT / name) for name in ("planning/27_q4_e1e2_and_sensitivity_spec.md", "src/q4/solve.py", "docs/q4_result.json")},
        "settings": SETTINGS, "grids": GRIDS,
        "nominal": {
            "joint_duration_s": nominal_joint["effective_duration_s"],
            "joint_intervals_s": nominal_joint["intervals_s"],
            "platform_windows": [{"platform": solve.NAMES[i], "duration_s": value["effective_duration_s"], "intervals_s": value["intervals_s"]} for i, value in enumerate(nominal_platforms)],
            "formal_densified_duration_s": payload["formal_best"]["densified_duration_s"],
        },
        "scenario_count": 49, "perturbed_scenario_count": len(records),
        "feasible_count": len(feasible) + 1, "infeasible_count": len(records) - len(feasible),
        "scenarios": records, "worst_scenario": worst, "risk_ranking": ranking,
        "critical_offsets": critical,
        "all_scenarios_retain_at_least_90_percent_of_platform_window": all(item["platform_window"]["retention_ratio"] >= 0.9 for item in feasible),
        "interpretation": {
            "fixed_policy": True, "reoptimized_under_perturbation": False,
            "probabilistic_robustness": False, "empirical_reality_validation": False,
            "q5_solved": False,
        },
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        "elapsed_s": time.perf_counter() - started,
    }
    output.write_text(json.dumps(solve.ready(result), ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(make_report(result), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.output.resolve(), args.report.resolve())
    print(json.dumps({
        "status": result["status"], "scenario_count": result["scenario_count"],
        "worst_window_retention_ratio": result["worst_scenario"]["platform_window"]["retention_ratio"],
        "elapsed_s": result["elapsed_s"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
