#!/usr/bin/env python3
"""比较第一问现行最小二乘概括与队友提出的 Theil–Sen 稳健斜率。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
CURRENT = ROOT / "output" / "q1" / "tables" / "attachment1_linear_summaries.csv"
OUT = ROOT / "output" / "q1" / "candidates" / "theilsen"
RESPONSES = ("ethanol_conversion_pct", "c4_selectivity_pct")


def direction(value: float, tolerance: float = 1e-12) -> int:
    return 1 if value > tolerance else (-1 if value < -tolerance else 0)


def ols_fit(temperature: np.ndarray, response: np.ndarray) -> dict[str, float]:
    slope, intercept = np.polyfit(temperature, response, 1)
    residual = response - (intercept + slope * temperature)
    return {
        "slope_per_25c": float(25.0 * slope),
        "mae": float(np.mean(np.abs(residual))),
        "maxae": float(np.max(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
    }


def theilsen_fit(temperature: np.ndarray, response: np.ndarray) -> dict[str, float]:
    x = (temperature - 350.0) / 25.0
    pair_slopes = np.array([
        (response[k] - response[j]) / (x[k] - x[j])
        for j in range(len(x)) for k in range(j + 1, len(x))
    ])
    slope = float(np.median(pair_slopes))
    intercept = float(np.median(response - slope * x))
    residual = response - (intercept + slope * x)
    return {
        "slope_per_25c": slope,
        "mae": float(np.mean(np.abs(residual))),
        "maxae": float(np.max(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        "pair_slope_count": int(len(pair_slopes)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    current = pd.read_csv(CURRENT)
    rows, loo_rows = [], []
    for catalyst_id, group in data.groupby("catalyst_id", sort=False):
        ordered = group.sort_values("temperature_c")
        temperature = ordered["temperature_c"].to_numpy(float)
        for response_name in RESPONSES:
            response = ordered[response_name].to_numpy(float)
            ols = ols_fit(temperature, response)
            sen = theilsen_fit(temperature, response)
            sen_sign = direction(sen["slope_per_25c"])
            loo_slopes = []
            for removed in range(len(temperature)):
                keep = np.arange(len(temperature)) != removed
                loo_slope = theilsen_fit(
                    temperature[keep], response[keep]
                )["slope_per_25c"]
                loo_slopes.append(loo_slope)
                loo_rows.append({
                    "catalyst_id": catalyst_id,
                    "response": response_name,
                    "removed_temperature_c": temperature[removed],
                    "theilsen_full_slope_per_25c": sen["slope_per_25c"],
                    "theilsen_loo_slope_per_25c": loo_slope,
                    "theilsen_direction_changed": direction(loo_slope) != sen_sign,
                })
            rows.append({
                "catalyst_id": catalyst_id,
                "response": response_name,
                "n": len(temperature),
                "ols_slope_per_25c": ols["slope_per_25c"],
                "theilsen_slope_per_25c": sen["slope_per_25c"],
                "slope_difference_theilsen_minus_ols":
                    sen["slope_per_25c"] - ols["slope_per_25c"],
                "slope_relative_difference_abs":
                    abs(sen["slope_per_25c"] - ols["slope_per_25c"])
                    / max(abs(ols["slope_per_25c"]), 1e-12),
                "direction_same":
                    direction(sen["slope_per_25c"]) == direction(ols["slope_per_25c"]),
                "ols_mae": ols["mae"],
                "theilsen_mae": sen["mae"],
                "mae_difference_theilsen_minus_ols": sen["mae"] - ols["mae"],
                "ols_maxae": ols["maxae"],
                "theilsen_maxae": sen["maxae"],
                "maxae_difference_theilsen_minus_ols": sen["maxae"] - ols["maxae"],
                "ols_rmse": ols["rmse"],
                "theilsen_rmse": sen["rmse"],
                "rmse_difference_theilsen_minus_ols": sen["rmse"] - ols["rmse"],
                "theilsen_pair_slope_count": sen["pair_slope_count"],
                "theilsen_loo_direction_change_count": int(sum(
                    direction(value) != sen_sign for value in loo_slopes
                )),
                "theilsen_loo_slope_min_per_25c": min(loo_slopes),
                "theilsen_loo_slope_max_per_25c": max(loo_slopes),
            })

    comparison = pd.DataFrame(rows)
    loo = pd.DataFrame(loo_rows)
    merged = comparison.merge(
        current[[
            "catalyst_id", "response", "slope_per_25c_pct_point",
            "mean_absolute_residual_pct_point", "max_absolute_residual_pct_point",
        ]],
        on=["catalyst_id", "response"], validate="one_to_one",
    )
    reproduction = {
        "max_slope_absolute_error": float(np.max(np.abs(
            merged["ols_slope_per_25c"] - merged["slope_per_25c_pct_point"]
        ))),
        "max_mae_absolute_error": float(np.max(np.abs(
            merged["ols_mae"] - merged["mean_absolute_residual_pct_point"]
        ))),
        "max_maxae_absolute_error": float(np.max(np.abs(
            merged["ols_maxae"] - merged["max_absolute_residual_pct_point"]
        ))),
    }
    by_response = {}
    for response_name, group in comparison.groupby("response"):
        by_response[response_name] = {
            "relationship_count": int(len(group)),
            "direction_same_count": int(group["direction_same"].sum()),
            "theilsen_positive_slope_count":
                int((group["theilsen_slope_per_25c"] > 0).sum()),
            "median_absolute_slope_difference":
                float(group["slope_difference_theilsen_minus_ols"].abs().median()),
            "max_absolute_slope_difference":
                float(group["slope_difference_theilsen_minus_ols"].abs().max()),
            "median_absolute_relative_slope_difference":
                float(group["slope_relative_difference_abs"].median()),
            "theilsen_lower_mae_count":
                int((group["theilsen_mae"] < group["ols_mae"]).sum()),
            "theilsen_lower_maxae_count":
                int((group["theilsen_maxae"] < group["ols_maxae"]).sum()),
            "theilsen_lower_rmse_count":
                int((group["theilsen_rmse"] < group["ols_rmse"]).sum()),
            "theilsen_loo_direction_change_relationship_count":
                int((group["theilsen_loo_direction_change_count"] > 0).sum()),
            "slope_rank_correlation": float(group["ols_slope_per_25c"].corr(
                group["theilsen_slope_per_25c"], method="spearman"
            )),
        }
    largest = comparison.loc[
        comparison["slope_relative_difference_abs"].nlargest(10).index,
        [
            "catalyst_id", "response", "ols_slope_per_25c",
            "theilsen_slope_per_25c", "slope_difference_theilsen_minus_ols",
            "slope_relative_difference_abs", "ols_mae", "theilsen_mae",
            "ols_maxae", "theilsen_maxae",
        ],
    ]
    summary = {
        "status": "candidate_comparison_only_not_adopted",
        "input": str(INPUT.relative_to(ROOT)),
        "relationship_count": int(len(comparison)),
        "leave_one_out_refit_count": int(len(loo)),
        "teammate_specification": {
            "temperature_scale": "x=(T-350)/25",
            "slope": "median of all pairwise slopes",
            "intercept": "median of y-slope*x",
        },
        "current_output_reproduction": reproduction,
        "overall": {
            "direction_same_count": int(comparison["direction_same"].sum()),
            "theilsen_positive_slope_count":
                int((comparison["theilsen_slope_per_25c"] > 0).sum()),
            "theilsen_lower_mae_count":
                int((comparison["theilsen_mae"] < comparison["ols_mae"]).sum()),
            "theilsen_lower_maxae_count":
                int((comparison["theilsen_maxae"] < comparison["ols_maxae"]).sum()),
            "theilsen_lower_rmse_count":
                int((comparison["theilsen_rmse"] < comparison["ols_rmse"]).sum()),
            "theilsen_loo_direction_change_relationship_count":
                int((comparison["theilsen_loo_direction_change_count"] > 0).sum()),
        },
        "by_response": by_response,
        "largest_relative_slope_differences": largest.to_dict(orient="records"),
    }
    comparison.to_csv(OUT / "ols_vs_theilsen.csv", index=False)
    loo.to_csv(OUT / "theilsen_leave_one_out.csv", index=False)
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
