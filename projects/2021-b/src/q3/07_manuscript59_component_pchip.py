#!/usr/bin/env python3
"""生成《59初稿》第三问分量PCHIP及三种插值比较。

输入：output/data_audit/tables/cleaned_attachment1.csv
输出：output/q3/manuscript59/中的缺测预测、遮点预测、表14—16和结构化摘要
职责：分别插值转化率和选择性后重构收率，并与直接收率PCHIP、局部直线比较。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUT = ROOT / "output/q3/manuscript59"
SCRIPT = Path(__file__).resolve()
TARGET_TEMPERATURE = 325.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def three_predictions(train: pd.DataFrame, temperature: float) -> dict:
    train = train.sort_values("temperature_c")
    x = train["temperature_c"].to_numpy(float)
    conversion = train["ethanol_conversion_pct"].to_numpy(float)
    selectivity = train["c4_selectivity_pct"].to_numpy(float)
    yields = train["c4_yield_pct"].to_numpy(float)
    component_conversion = float(PchipInterpolator(x, conversion, extrapolate=False)(temperature))
    component_selectivity = float(PchipInterpolator(x, selectivity, extrapolate=False)(temperature))
    component_yield = component_conversion * component_selectivity / 100.0
    direct_yield = float(PchipInterpolator(x, yields, extrapolate=False)(temperature))
    upper_index = int(np.searchsorted(x, temperature))
    lower_index = upper_index - 1
    weight = (temperature - x[lower_index]) / (x[upper_index] - x[lower_index])
    linear_yield = float(yields[lower_index] + weight * (yields[upper_index] - yields[lower_index]))
    return {
        "component_pchip_conversion_pct": component_conversion,
        "component_pchip_selectivity_pct": component_selectivity,
        "component_pchip_yield_pct": component_yield,
        "direct_yield_pchip_pct": direct_yield,
        "local_linear_yield_pct": linear_yield,
    }


def error_metrics(values: pd.Series) -> dict:
    values = values.abs()
    return {
        "mae_pct_point": float(values.mean()),
        "median_ae_pct_point": float(values.median()),
        "rmse_pct_point": float(np.sqrt(np.mean(values**2))),
        "max_ae_pct_point": float(values.max()),
        "q90_ae_pct_point": float(values.quantile(0.9)),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)

    missing_rows = []
    for catalyst_id, group in data.groupby("catalyst_id", sort=True):
        temperatures = set(group["temperature_c"].astype(float))
        if (
            TARGET_TEMPERATURE not in temperatures
            and group["temperature_c"].min() < TARGET_TEMPERATURE < group["temperature_c"].max()
        ):
            missing_rows.append({
                "catalyst_id": catalyst_id,
                "temperature_c": TARGET_TEMPERATURE,
                **three_predictions(group, TARGET_TEMPERATURE),
                "status": "interpolation_check_not_observation",
            })
    missing = pd.DataFrame(missing_rows).sort_values(
        "component_pchip_yield_pct", ascending=False, kind="mergesort"
    )
    observed_low_best = float(
        data.loc[data["temperature_c"] < 350.0, "c4_yield_pct"].max()
    )
    for column in (
        "component_pchip_yield_pct", "direct_yield_pchip_pct", "local_linear_yield_pct"
    ):
        missing[f"observed_low_best_minus_{column}_pct_point"] = (
            observed_low_best - missing[column]
        )

    holdout_rows = []
    for catalyst_id, group in data.groupby("catalyst_id", sort=True):
        group = group.sort_values("temperature_c").reset_index(drop=True)
        for held_index in range(1, len(group) - 1):
            held = group.iloc[held_index]
            predicted = three_predictions(group.drop(index=held_index), float(held["temperature_c"]))
            holdout_rows.append({
                "catalyst_id": catalyst_id,
                "held_temperature_c": float(held["temperature_c"]),
                "actual_c4_yield_pct": float(held["c4_yield_pct"]),
                **predicted,
            })
    holdout = pd.DataFrame(holdout_rows)
    methods = {
        "分量PCHIP后重构": "component_pchip_yield_pct",
        "直接收率PCHIP": "direct_yield_pchip_pct",
        "局部直线插值": "local_linear_yield_pct",
    }
    metric_rows = []
    for method, column in methods.items():
        errors = holdout[column] - holdout["actual_c4_yield_pct"]
        metric_rows.append({"method": method, **error_metrics(errors)})
        holdout[f"{column}_absolute_error_pct_point"] = errors.abs()
    table16 = pd.DataFrame(metric_rows)

    sensitivity_rows = []
    for method, column in methods.items():
        best = missing.sort_values(column, ascending=False, kind="mergesort").iloc[0]
        sensitivity_rows.append({
            "method": method,
            "highest_missing_prediction_pct": float(best[column]),
            "catalyst_id": best["catalyst_id"],
            "a2_observed_lead_pct_point": float(observed_low_best - best[column]),
        })
    table15 = pd.DataFrame(sensitivity_rows)
    table14 = missing[[
        "catalyst_id",
        "component_pchip_conversion_pct",
        "component_pchip_selectivity_pct",
        "component_pchip_yield_pct",
    ]].head(5)

    outputs = {
        "missing": OUT / "missing_325_predictions.csv",
        "holdout": OUT / "interior_holdout_predictions.csv",
        "table14": OUT / "table14_component_pchip_top5.csv",
        "table15": OUT / "table15_method_sensitivity.csv",
        "table16": OUT / "table16_holdout_metrics.csv",
    }
    missing.to_csv(outputs["missing"], index=False)
    holdout.to_csv(outputs["holdout"], index=False)
    table14.to_csv(outputs["table14"], index=False)
    table15.to_csv(outputs["table15"], index=False)
    table16.to_csv(outputs["table16"], index=False)

    summary = {
        "schema_version": "1.0",
        "status": "manuscript59_q3_component_pchip",
        "missing_325_count": int(len(missing)),
        "interior_holdout_count": int(len(holdout)),
        "observed_low_best_yield_pct": observed_low_best,
        "table15": table15.to_dict(orient="records"),
        "table16": table16.to_dict(orient="records"),
        "boundaries": [
            "只插值组合自身温度范围内的325摄氏度标签缺口",
            "插值结果不是实测观测，不替代两情景实测枚举推荐",
            "遮点误差是预测误差，不是重复实验测量误差",
        ],
    }
    summary_path = OUT / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    entries = [
        (INPUT, "input", "清洁附件1"),
        (SCRIPT, "source", "分量PCHIP主程序"),
        *[(path, "output", name) for name, path in outputs.items()],
        (summary_path, "output", "结构化摘要"),
    ]
    pd.DataFrame([
        {
            "path": str(path.relative_to(ROOT)),
            "role": role,
            "description": description,
            "producer": str(SCRIPT.relative_to(ROOT)) if role == "output" else "upstream_or_self",
            "consumer": "独立验证及《59初稿》表14—16",
            "sha256": sha256(path),
        }
        for path, role, description in entries
    ]).to_csv(OUT / "artifact_manifest.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

