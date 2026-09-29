#!/usr/bin/env python3
"""独立复算第三问S6窄PCHIP候选，不导入候选主程序。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q3" / "candidates" / "narrow_pchip"
TOL = 1e-10


def main() -> None:
    data = pd.read_csv(INPUT)
    saved = pd.read_csv(OUT / "interior_holdout_predictions.csv")
    missing = pd.read_csv(OUT / "missing_325_candidate_predictions.csv")
    ranking = pd.read_csv(OUT / "temperature_ranking_checks.csv")
    checks = []

    expected_count = int(sum(len(group) - 2 for _, group in data.groupby("catalyst_id")))
    checks.append({
        "check": "内部遮点数量",
        "passed": bool(len(saved) == expected_count == 72),
        "detail": f"rows={len(saved)}",
    })

    prediction_errors = []
    for row in saved.itertuples(index=False):
        group = data[data["catalyst_id"] == row.catalyst_id].sort_values("temperature_c")
        train = group[group["temperature_c"] != row.held_temperature_c]
        prediction = float(PchipInterpolator(
            train["temperature_c"], train["c4_yield_pct"], extrapolate=False
        )(row.held_temperature_c))
        prediction_errors.append(abs(prediction - row.pchip_prediction_pct))
    checks.append({
        "check": "PCHIP逐点独立复算",
        "passed": bool(max(prediction_errors) < TOL),
        "detail": f"max_abs_error={max(prediction_errors):.3e}",
    })

    pchip_error = (saved["pchip_prediction_pct"] - saved["actual_c4_yield_pct"]).abs()
    linear_error = (saved["linear_prediction_pct"] - saved["actual_c4_yield_pct"]).abs()
    checks.append({
        "check": "误差改善",
        "passed": bool(
            pchip_error.mean() < linear_error.mean()
            and pchip_error.median() < linear_error.median()
            and int((pchip_error < linear_error).sum()) == 68
        ),
        "detail": (
            f"mae_pchip={pchip_error.mean():.6f}, "
            f"mae_linear={linear_error.mean():.6f}, wins=68/72"
        ),
    })
    checks.append({
        "check": "最坏误差仍显式保留",
        "passed": bool(pchip_error.max() > 10.0),
        "detail": f"max_abs_error={pchip_error.max():.6f}",
    })

    expected_missing = {
        "A6", "A7", "A8", "A9", "A10", "A11",
        "A12", "A13", "A14", "B1", "B2",
    }
    checks.append({
        "check": "325摄氏度缺口身份",
        "passed": bool(set(missing["catalyst_id"]) == expected_missing),
        "detail": f"count={len(missing)}",
    })

    missing_errors = []
    for row in missing.itertuples(index=False):
        group = data[data["catalyst_id"] == row.catalyst_id].sort_values("temperature_c")
        prediction = float(PchipInterpolator(
            group["temperature_c"], group["c4_yield_pct"], extrapolate=False
        )(325.0))
        missing_errors.append(abs(prediction - row.pchip_predicted_c4_yield_pct))
    checks.append({
        "check": "325摄氏度预测独立复算",
        "passed": bool(max(missing_errors) < TOL),
        "detail": f"max_abs_error={max(missing_errors):.3e}",
    })

    low_best = float(
        data[data["temperature_c"] < 350.0]["c4_yield_pct"].max()
    )
    checks.append({
        "check": "低温D0推荐不变",
        "passed": bool(missing["pchip_predicted_c4_yield_pct"].max() < low_best),
        "detail": (
            f"max_missing_prediction={missing['pchip_predicted_c4_yield_pct'].max():.6f}, "
            f"d0_best={low_best:.6f}"
        ),
    })
    pchip_ranking = ranking[ranking["model"] == "pchip"]
    checks.append({
        "check": "最高候选识别并非全对",
        "passed": bool(
            int(pchip_ranking["top1_correct"].sum()) == 4
            and len(pchip_ranking) == 5
        ),
        "detail": "top1_correct=4/5",
    })

    result = {
        "status": "s6_candidate_independent_verification",
        "passed": bool(all(item["passed"] for item in checks)),
        "check_count": len(checks),
        "checks": checks,
        "note": "通过只证明窄候选产物一致，不批准D1或最终方法。",
    }
    (OUT / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
