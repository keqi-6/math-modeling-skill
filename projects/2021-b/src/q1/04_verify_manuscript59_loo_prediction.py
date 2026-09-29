#!/usr/bin/env python3
"""独立复算《59初稿》第一问留一预测结果，不导入主程序。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUT = ROOT / "output/q1/manuscript59"
RESPONSES = ("ethanol_conversion_pct", "c4_selectivity_pct")
TOL = 1e-9


def main() -> None:
    data = pd.read_csv(INPUT)
    saved_predictions = pd.read_csv(OUT / "loo_predictions.csv")
    saved_metrics = pd.read_csv(OUT / "loo_metrics_by_combination.csv")
    saved_table = pd.read_csv(OUT / "table3_loo_summary.csv")
    checks: list[dict] = []

    checks.append({
        "check": "预测行数为114个观测乘2个响应",
        "passed": bool(len(saved_predictions) == 228),
        "detail": f"rows={len(saved_predictions)}",
    })
    maximum_prediction_error = 0.0
    recomputed_metrics = []
    for catalyst_id, group in data.groupby("catalyst_id", sort=True):
        group = group.sort_values("temperature_c")
        temperatures = group["temperature_c"].to_numpy(float)
        for response in RESPONSES:
            values = group[response].to_numpy(float)
            errors = []
            for held_index, temperature in enumerate(temperatures):
                keep = np.arange(len(group)) != held_index
                x_train = temperatures[keep]
                y_train = values[keep]
                slope = float(
                    np.sum((x_train - x_train.mean()) * (y_train - y_train.mean()))
                    / np.sum((x_train - x_train.mean()) ** 2)
                )
                intercept = float(y_train.mean() - slope * x_train.mean())
                prediction = intercept + slope * temperature
                saved = saved_predictions[
                    (saved_predictions["catalyst_id"] == catalyst_id)
                    & (saved_predictions["response"] == response)
                    & (saved_predictions["held_temperature_c"] == temperature)
                ].iloc[0]
                maximum_prediction_error = max(
                    maximum_prediction_error, abs(prediction - saved["predicted_pct"])
                )
                errors.append(values[held_index] - prediction)
            errors = np.asarray(errors)
            rmse = float(np.sqrt(np.mean(errors**2)))
            recomputed_metrics.append({
                "catalyst_id": catalyst_id,
                "response": response,
                "cv_mae_pct_point": float(np.mean(np.abs(errors))),
                "cv_rmse_pct_point": rmse,
                "nrmse_pct": float(rmse / (values.max() - values.min()) * 100.0),
            })
    checks.append({
        "check": "逐点预测独立复算",
        "passed": bool(maximum_prediction_error < TOL),
        "detail": f"max_abs_difference={maximum_prediction_error:.3e}",
    })

    recomputed = pd.DataFrame(recomputed_metrics)
    merged = saved_metrics.merge(
        recomputed, on=["catalyst_id", "response"], suffixes=("_saved", "_calc")
    )
    metric_error = max(
        float(np.max(np.abs(merged[f"{column}_saved"] - merged[f"{column}_calc"])))
        for column in ("cv_mae_pct_point", "cv_rmse_pct_point", "nrmse_pct")
    )
    checks.append({
        "check": "组合层指标独立复算",
        "passed": bool(metric_error < TOL and len(merged) == 42),
        "detail": f"rows={len(merged)}, max_abs_difference={metric_error:.3e}",
    })

    expected_rounded = {
        "ethanol_conversion_pct": (7.803, 9.410, 22.77),
        "c4_selectivity_pct": (3.819, 4.399, 14.43),
    }
    matches = True
    details = []
    for response, expected in expected_rounded.items():
        row = saved_table[saved_table["response"] == response].iloc[0]
        actual = (
            round(float(row["median_cv_mae_pct_point"]), 3),
            round(float(row["median_cv_rmse_pct_point"]), 3),
            round(float(row["median_nrmse_pct"]), 2),
        )
        matches &= actual == expected
        details.append(f"{response}={actual}")
    checks.append({
        "check": "底稿表3显示值",
        "passed": bool(matches),
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

