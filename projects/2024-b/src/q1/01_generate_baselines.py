"""生成问题一完整动作空间的两项可验证基线的冻结结构化产物。

输入：planning/analysis/2026-08-25_q1_s4_complete_action_specification.md；命令行 N 列表。
输出：output/q1/baselines.json。
职责：为后续求解与独立验证提供唯一基线口径。factual_only 是零风险事实停止基线；
greedy_boundary 是只在整批必然超标/合格时停止的边界基线（与 factual_only 相同但显式
记录为独立命名，便于审计）。不生成主方案或全局最优声明。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from core import (
    boundary_counts,
    evaluate_threshold_policy,
    factual_only_thresholds,
    fraction_payload,
    validate_n,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "planning/analysis/2026-08-25_q1_s4_complete_action_specification.md"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/baselines.json"
DEFAULT_N_VALUES = (1, 2, 3, 9, 10, 20, 23, 50)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_n_values(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    if not values:
        raise ValueError("N 列表不能为空")
    for value in values:
        validate_n(value)
    return values


def build_baseline(n: int, scenario: str, name: str, thresholds: tuple[int, ...]) -> dict[str, object]:
    d0, d1 = boundary_counts(n)
    if scenario == "R":
        null_d, target_d, risk_limit = d0, d1, "1/20"
    else:
        null_d, target_d, risk_limit = d1, d0, "1/10"
    evaluation = evaluate_threshold_policy(n, null_d, scenario, thresholds)
    risk = evaluation.reject_probability if scenario == "R" else evaluation.accept_probability
    asn = evaluate_threshold_policy(n, target_d, scenario, thresholds).asn
    if risk != 0:
        raise AssertionError("事实基线的方向风险必须精确为 0")
    limit_numerator, limit_denominator = map(int, risk_limit.split("/"))
    if risk > Fraction(limit_numerator, limit_denominator):
        raise AssertionError("基线风险超过S4限额")
    return {
        "name": name,
        "thresholds": list(thresholds),
        "null_d": null_d,
        "target_d": target_d,
        "risk_limit": risk_limit,
        "risk_at_boundary": fraction_payload(risk),
        "asn_at_target": fraction_payload(asn),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成问题一完整动作空间S5基线产物")
    parser.add_argument(
        "--n-list",
        default=",".join(map(str, DEFAULT_N_VALUES)),
        help="逗号分隔的正整数批量，默认仅为S5结构测试集合",
    )
    args = parser.parse_args()
    n_values = parse_n_values(args.n_list)
    records: list[dict[str, object]] = []
    for n in n_values:
        d0, d1 = boundary_counts(n)
        scenarios: dict[str, object] = {}
        for scenario in ("R", "A"):
            factual = factual_only_thresholds(n, scenario)
            scenarios[scenario] = {
                "factual_only": build_baseline(
                    n,
                    scenario,
                    "factual_only",
                    factual,
                ),
                "factual_only_audit_copy": build_baseline(
                    n,
                    scenario,
                    "factual_only_audit_copy",
                    factual,
                ),
            }
        records.append({"N": n, "D0": d0, "D1": d1, "scenarios": scenarios})

    payload = {
        "schema_version": "1.0",
        "artifact_status": "s5_frozen_baseline_unverified",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "producer": "src/q1/01_generate_baselines.py",
        "consumers": [
            "src/q1/02_solve.py",
            "future S6 independent verifier",
            "planning/analysis/2026-08-25_q1_s5_complete_action_implementation.md",
        ],
        "specification": {
            "path": str(SPEC_PATH.relative_to(PROJECT_ROOT)),
            "sha256": sha256(SPEC_PATH),
            "authority_status": "approved_by_user_before_S5",
        },
        "input_identity": {
            "p0": "1/10",
            "n_values": list(n_values),
            "n_role": "S5 implementation fixtures, not an official or final business batch-size choice",
        },
        "records": records,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(OUTPUT_PATH), "records": len(records)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
