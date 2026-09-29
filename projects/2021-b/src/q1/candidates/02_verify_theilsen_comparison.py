#!/usr/bin/env python3
"""独立复算队友 Theil–Sen 候选比较的关键结果，不调用候选主程序。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import theilslopes

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q1" / "candidates" / "theilsen"
RESPONSES = ("ethanol_conversion_pct", "c4_selectivity_pct")


def sign(value: float) -> int:
    return 1 if value > 1e-12 else (-1 if value < -1e-12 else 0)


def sen_slope(temperature: np.ndarray, response: np.ndarray) -> float:
    slopes = []
    for left in range(len(temperature)):
        for right in range(left + 1, len(temperature)):
            slopes.append(
                25.0 * (response[right] - response[left])
                / (temperature[right] - temperature[left])
            )
    return float(np.median(np.asarray(slopes)))


def main() -> None:
    data = pd.read_csv(INPUT)
    reported = pd.read_csv(OUT / "ols_vs_theilsen.csv")
    slope_errors = []
    scipy_slope_errors = []
    loo_changed_relationships = 0
    for catalyst_id, group in data.groupby("catalyst_id", sort=False):
        ordered = group.sort_values("temperature_c")
        temperature = ordered["temperature_c"].to_numpy(float)
        for response_name in RESPONSES:
            response = ordered[response_name].to_numpy(float)
            full = sen_slope(temperature, response)
            row = reported[
                (reported["catalyst_id"] == catalyst_id)
                & (reported["response"] == response_name)
            ].iloc[0]
            slope_errors.append(abs(full - row["theilsen_slope_per_25c"]))
            x = (temperature - 350.0) / 25.0
            scipy_result = theilslopes(response, x, method="joint")
            scipy_slope_errors.append(
                abs(float(scipy_result.slope) - row["theilsen_slope_per_25c"])
            )
            changed = False
            for removed in range(len(temperature)):
                keep = np.arange(len(temperature)) != removed
                changed |= sign(sen_slope(
                    temperature[keep], response[keep]
                )) != sign(full)
            loo_changed_relationships += int(changed)
    checks = [
        {
            "check": "42组Theil-Sen斜率独立复算",
            "passed": bool(len(slope_errors) == 42 and max(slope_errors) < 1e-10),
            "detail": f"count={len(slope_errors)}, max_abs_error={max(slope_errors):.3e}",
        },
        {
            "check": "全部候选斜率方向",
            "passed": bool(int((reported["theilsen_slope_per_25c"] > 0).sum()) == 42),
            "detail": f"positive={int((reported['theilsen_slope_per_25c'] > 0).sum())}/42",
        },
        {
            "check": "SciPy实现交叉核对",
            "passed": bool(
                len(scipy_slope_errors) == 42 and max(scipy_slope_errors) < 1e-10
            ),
            "detail": (
                f"count={len(scipy_slope_errors)}, "
                f"max_abs_error={max(scipy_slope_errors):.3e}"
            ),
        },
        {
            "check": "留一方向变化关系数独立复算",
            "passed": bool(
                loo_changed_relationships
                == int((reported["theilsen_loo_direction_change_count"] > 0).sum())
            ),
            "detail": f"relationship_count={loo_changed_relationships}",
        },
    ]
    result = {
        "status": "candidate_verification_only",
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
    }
    (OUT / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
