#!/usr/bin/env python3
"""第三问S6：只在已有组合内部比较局部直线与PCHIP插值候选。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q3" / "candidates" / "narrow_pchip"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    rows = []
    for catalyst_id, group in data.groupby("catalyst_id", sort=True):
        group = group.sort_values("temperature_c").reset_index(drop=True)
        for index in range(1, len(group) - 1):
            test = group.iloc[index]
            train = group.drop(index=index)
            lower = train[train["temperature_c"] < test["temperature_c"]].iloc[-1]
            upper = train[train["temperature_c"] > test["temperature_c"]].iloc[0]
            weight = (
                (test["temperature_c"] - lower["temperature_c"])
                / (upper["temperature_c"] - lower["temperature_c"])
            )
            linear = lower["c4_yield_pct"] + weight * (
                upper["c4_yield_pct"] - lower["c4_yield_pct"]
            )
            pchip = float(PchipInterpolator(
                train["temperature_c"], train["c4_yield_pct"], extrapolate=False
            )(test["temperature_c"]))
            rows.append({
                "catalyst_id": catalyst_id,
                "held_temperature_c": float(test["temperature_c"]),
                "actual_c4_yield_pct": float(test["c4_yield_pct"]),
                "linear_prediction_pct": float(linear),
                "pchip_prediction_pct": pchip,
                "linear_abs_error_pct_point": abs(float(linear - test["c4_yield_pct"])),
                "pchip_abs_error_pct_point": abs(float(pchip - test["c4_yield_pct"])),
            })
    validation = pd.DataFrame(rows)
    validation.to_csv(OUT / "interior_holdout_predictions.csv", index=False)

    missing_rows = []
    for catalyst_id, group in data.groupby("catalyst_id", sort=True):
        group = group.sort_values("temperature_c")
        if (
            325.0 not in set(group["temperature_c"])
            and group["temperature_c"].min() < 325.0 < group["temperature_c"].max()
        ):
            prediction = float(PchipInterpolator(
                group["temperature_c"], group["c4_yield_pct"], extrapolate=False
            )(325.0))
            missing_rows.append({
                "catalyst_id": catalyst_id,
                "temperature_c": 325.0,
                "pchip_predicted_c4_yield_pct": prediction,
                "status": "candidate_prediction_not_observation",
            })
    missing = pd.DataFrame(missing_rows).sort_values(
        "pchip_predicted_c4_yield_pct", ascending=False
    )
    missing.to_csv(OUT / "missing_325_candidate_predictions.csv", index=False)

    metrics = {}
    for model in ("linear", "pchip"):
        errors = validation[f"{model}_abs_error_pct_point"]
        metrics[model] = {
            "n": int(len(errors)),
            "mae": float(errors.mean()),
            "rmse": float(np.sqrt(np.mean(errors**2))),
            "median_ae": float(errors.median()),
            "max_ae": float(errors.max()),
        }
    metrics["pchip"]["points_beating_linear"] = int(
        (
            validation["pchip_abs_error_pct_point"]
            < validation["linear_abs_error_pct_point"]
        ).sum()
    )

    rank_rows = []
    for temperature, group in validation.groupby("held_temperature_c", sort=True):
        actual_top = group.loc[group["actual_c4_yield_pct"].idxmax(), "catalyst_id"]
        for model in ("linear", "pchip"):
            predicted_top = group.loc[
                group[f"{model}_prediction_pct"].idxmax(), "catalyst_id"
            ]
            actual_top3 = set(group.nlargest(3, "actual_c4_yield_pct")["catalyst_id"])
            predicted_top3 = set(group.nlargest(3, f"{model}_prediction_pct")["catalyst_id"])
            rank_rows.append({
                "temperature_c": float(temperature),
                "model": model,
                "actual_top_catalyst": actual_top,
                "predicted_top_catalyst": predicted_top,
                "top1_correct": bool(actual_top == predicted_top),
                "top3_overlap": int(len(actual_top3 & predicted_top3)),
            })
    ranking = pd.DataFrame(rank_rows)
    ranking.to_csv(OUT / "temperature_ranking_checks.csv", index=False)

    low_best = (
        data[data["temperature_c"] < 350.0]
        .sort_values("c4_yield_pct", ascending=False)
        .iloc[0]
    )
    max_missing = missing.iloc[0]
    summary = {
        "status": "s6_candidate_only_not_approved",
        "candidate": "within_combination_pchip_interpolation",
        "scope": "existing_combination_strictly_inside_own_observed_temperature_range",
        "validation_metrics": metrics,
        "pchip_top1_correct_temperature_blocks": int(
            ranking[ranking["model"] == "pchip"]["top1_correct"].sum()
        ),
        "pchip_temperature_block_count": int(
            len(ranking[ranking["model"] == "pchip"])
        ),
        "missing_325_prediction_count": int(len(missing)),
        "highest_missing_325_prediction": {
            "catalyst_id": max_missing["catalyst_id"],
            "c4_yield_pct": float(max_missing["pchip_predicted_c4_yield_pct"]),
        },
        "observed_low_temperature_d0_best": {
            "catalyst_id": low_best["catalyst_id"],
            "temperature_c": float(low_best["temperature_c"]),
            "c4_yield_pct": float(low_best["c4_yield_pct"]),
        },
        "changes_low_temperature_recommendation": bool(
            max_missing["pchip_predicted_c4_yield_pct"] > low_best["c4_yield_pct"]
        ),
        "boundaries": [
            "不跨组合预测",
            "不在组合自身实测温度区间外外推",
            "不创造新配方",
            "候选验证通过不等于未测点已经成为观测",
            "400摄氏度遮点个案误差仍大",
        ],
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
