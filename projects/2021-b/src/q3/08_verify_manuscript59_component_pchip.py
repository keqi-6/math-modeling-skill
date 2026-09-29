#!/usr/bin/env python3
"""独立复算《59初稿》第三问表14—16，不导入主程序。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUT = ROOT / "output/q3/manuscript59"
TOL = 1e-9


def main() -> None:
    data = pd.read_csv(INPUT)
    missing = pd.read_csv(OUT / "missing_325_predictions.csv")
    holdout = pd.read_csv(OUT / "interior_holdout_predictions.csv")
    table14 = pd.read_csv(OUT / "table14_component_pchip_top5.csv")
    table15 = pd.read_csv(OUT / "table15_method_sensitivity.csv")
    table16 = pd.read_csv(OUT / "table16_holdout_metrics.csv")
    checks: list[dict] = []

    expected_missing = {
        "A6", "A7", "A8", "A9", "A10", "A11",
        "A12", "A13", "A14", "B1", "B2",
    }
    checks.append({
        "check": "325摄氏度内部缺口身份",
        "passed": bool(set(missing["catalyst_id"]) == expected_missing),
        "detail": f"count={len(missing)}",
    })

    maximum_component_difference = 0.0
    for row in missing.itertuples(index=False):
        group = data[data["catalyst_id"] == row.catalyst_id].sort_values("temperature_c")
        x = group["temperature_c"].to_numpy(float)
        conversion = float(PchipInterpolator(
            x, group["ethanol_conversion_pct"].to_numpy(float), extrapolate=False
        )(325.0))
        selectivity = float(PchipInterpolator(
            x, group["c4_selectivity_pct"].to_numpy(float), extrapolate=False
        )(325.0))
        reconstructed = conversion * selectivity / 100.0
        maximum_component_difference = max(
            maximum_component_difference,
            abs(conversion - row.component_pchip_conversion_pct),
            abs(selectivity - row.component_pchip_selectivity_pct),
            abs(reconstructed - row.component_pchip_yield_pct),
        )
    checks.append({
        "check": "分量PCHIP逐点独立复算",
        "passed": bool(maximum_component_difference < TOL),
        "detail": f"max_abs_difference={maximum_component_difference:.3e}",
    })

    expected_top5 = ["A7", "A8", "A6", "B1", "A12"]
    top_values = [round(value, 4) for value in table14["component_pchip_yield_pct"]]
    checks.append({
        "check": "底稿表14排序和显示值",
        "passed": bool(
            list(table14["catalyst_id"]) == expected_top5
            and top_values == [6.4562, 4.1571, 3.3078, 2.2259, 1.9996]
        ),
        "detail": f"ids={list(table14['catalyst_id'])}, yields={top_values}",
    })

    expected_table15 = {
        "分量PCHIP后重构": (6.4562, "A7", 10.8081),
        "直接收率PCHIP": (6.5517, "A7", 10.7126),
        "局部直线插值": (7.2293, "A7", 10.0350),
    }
    table15_ok = True
    for row in table15.itertuples(index=False):
        expected = expected_table15[row.method]
        actual = (
            round(row.highest_missing_prediction_pct, 4),
            row.catalyst_id,
            round(row.a2_observed_lead_pct_point, 4),
        )
        table15_ok &= actual == expected
    checks.append({
        "check": "底稿表15显示值",
        "passed": bool(table15_ok),
        "detail": "三种方法最高缺测预测及A2领先幅度",
    })

    expected_table16 = {
        "分量PCHIP后重构": (0.5365, 0.0804, 1.7048, 13.0338, 1.0864),
        "直接收率PCHIP": (0.7152, 0.1627, 1.9203, 13.4906, 1.8012),
        "局部直线插值": (1.5570, 0.8092, 2.7874, 14.1522, None),
    }
    table16_ok = len(holdout) == 72
    details = []
    for row in table16.itertuples(index=False):
        expected = expected_table16[row.method]
        actual = (
            round(row.mae_pct_point, 4),
            round(row.median_ae_pct_point, 4),
            round(row.rmse_pct_point, 4),
            round(row.max_ae_pct_point, 4),
            round(row.q90_ae_pct_point, 4),
        )
        comparison = actual[:4] == expected[:4]
        if expected[4] is not None:
            comparison &= actual[4] == expected[4]
        table16_ok &= comparison
        details.append(f"{row.method}={actual}")
    checks.append({
        "check": "底稿表16显示值",
        "passed": bool(table16_ok),
        "detail": "; ".join(details),
    })

    verification = {
        "schema_version": "1.0",
        "passed": bool(all(item["passed"] for item in checks)),
        "checks_passed": int(sum(item["passed"] for item in checks)),
        "checks_total": len(checks),
        "checks": checks,
    }
    (OUT / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(verification, ensure_ascii=False, indent=2))
    if not verification["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
