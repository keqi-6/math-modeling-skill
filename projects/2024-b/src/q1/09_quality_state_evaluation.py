"""精确评价冻结的 N=1000 问题一规则在不同批内次品数下的平均检测量。

本脚本不重新设计或优化阈值。它只读取已经通过风险核对的大批量候选，在 0%--100%
的 1 个百分点网格及 10% 相邻边界上，使用有限总体无放回 Fraction 递推计算停止概率
与平均检测件数。网格中的质量状态只用于事后性能评价，不是第二质量点或灰区参数。
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = Path(__file__).resolve()
INPUT_PATH = PROJECT_ROOT / "output/q1/s5_large_batch_extension.json"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/s7_quality_state_evaluation.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s7_quality_state_evaluation_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fraction_payload(value: Fraction, digits: int = 24) -> dict[str, object]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": format(float(value), f".{digits}g"),
    }


def evaluate(
    n: int,
    d: int,
    scenario: str,
    thresholds: tuple[int, ...],
) -> dict[str, Fraction]:
    """按冻结动作优先级执行精确有限总体概率流。"""

    d0, d1 = n // 10, n // 10 + 1
    alive: dict[int, Fraction] = {0: Fraction(1)}
    accepted = Fraction(0)
    rejected = Fraction(0)
    weighted_stop = Fraction(0)
    for t in range(n):
        next_alive: dict[int, Fraction] = {}
        for x, mass in alive.items():
            action = 0
            if 1 <= t < n:
                if x + (n - t) <= d0:
                    action = 1
                elif x >= d1:
                    action = 2
                elif scenario == "R" and x >= thresholds[t - 1]:
                    action = 2
                elif scenario == "A" and x <= thresholds[t - 1]:
                    action = 1
            if action:
                weighted_stop += t * mass
                if action == 1:
                    accepted += mass
                else:
                    rejected += mass
                continue

            defect_probability = Fraction(d - x, n - t)
            good_probability = Fraction(n - d - t + x, n - t)
            if defect_probability < 0 or good_probability < 0 or defect_probability + good_probability != 1:
                raise AssertionError(f"不可达状态获得正质量: N={n},D={d},t={t},x={x}")
            if defect_probability:
                next_alive[x + 1] = next_alive.get(x + 1, Fraction(0)) + mass * defect_probability
            if good_probability:
                next_alive[x] = next_alive.get(x, Fraction(0)) + mass * good_probability
        alive = next_alive

    terminal = sum(alive.values(), Fraction(0))
    if accepted + rejected + terminal != 1:
        raise AssertionError(f"概率质量不守恒: N={n},D={d},scenario={scenario}")
    return {
        "accept_probability": accepted,
        "reject_probability": rejected,
        "terminal_probability": terminal,
        "asn": weighted_stop + n * terminal,
    }


def main() -> None:
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    source = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    frozen = next(item for item in source["results"] if int(item["N"]) == 1000)
    n = int(frozen["N"])
    d0, d1 = int(frozen["D0"]), int(frozen["D1"])
    grid = sorted(set(range(0, n + 1, n // 100)) | {d0, d1})
    scenario_results: dict[str, object] = {}

    for scenario in ("R", "A"):
        source_scenario = frozen["scenarios"][scenario]
        thresholds = tuple(int(row["threshold"]) for row in source_scenario["thresholds"])
        points = []
        for d in grid:
            result = evaluate(n, d, scenario, thresholds)
            ratio = result["asn"] / n
            points.append(
                {
                    "D": d,
                    "defect_rate": fraction_payload(Fraction(d, n)),
                    "average_inspected_items": fraction_payload(result["asn"]),
                    "average_inspection_ratio": fraction_payload(ratio),
                    "accept_probability": fraction_payload(result["accept_probability"]),
                    "reject_probability": fraction_payload(result["reject_probability"]),
                    "terminal_probability": fraction_payload(result["terminal_probability"]),
                }
            )

        boundary_d = d1 if scenario == "R" else d0
        boundary_point = next(point for point in points if point["D"] == boundary_d)
        frozen_asn = source_scenario["worst_target_ASN_upper_bound"]
        if (
            boundary_point["average_inspected_items"]["numerator"] != frozen_asn["numerator"]
            or boundary_point["average_inspected_items"]["denominator"] != frozen_asn["denominator"]
        ):
            raise AssertionError(f"边界ASN未与冻结结果一致: scenario={scenario}")

        scenario_results[scenario] = {
            "scenario": scenario,
            "threshold_source": "output/q1/s5_large_batch_extension.json",
            "boundary_target_D": boundary_d,
            "points": points,
        }

    result_payload = {
        "schema_version": "1.0",
        "artifact_status": "s7_post_solution_exact_performance_evaluation",
        "producer": "src/q1/09_quality_state_evaluation.py",
        "input_identity": {"path": str(INPUT_PATH.relative_to(PROJECT_ROOT)), "sha256": sha256(INPUT_PATH)},
        "N": n,
        "D0": d0,
        "D1": d1,
        "evaluation_grid": {
            "description": "0%--100% in one-percentage-point increments, plus the adjacent D1 boundary",
            "D_values": grid,
            "point_count_per_scenario": len(grid),
        },
        "scenarios": scenario_results,
        "interpretation_boundary": [
            "quality states are post-solution evaluation fixtures and do not enter threshold design",
            "the evaluation does not introduce a second quality point, indifference zone, or new decision boundary",
            "every plotted point is an exact finite-population expectation; line segments only guide the eye",
            "N=1000 is a representative computational fixture rather than an observed enterprise batch size",
        ],
    }
    OUTPUT_PATH.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s7_evaluation_run_identity",
        "producer": "src/q1/09_quality_state_evaluation.py",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT)), *sys.argv[1:]],
        "environment": {"python": sys.version, "platform": platform.platform(), "random_seed": None},
        "inputs": {
            str(INPUT_PATH.relative_to(PROJECT_ROOT)): sha256(INPUT_PATH),
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
        },
        "outputs": {str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH)},
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "N": n, "points_per_scenario": len(grid), "output": str(OUTPUT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
