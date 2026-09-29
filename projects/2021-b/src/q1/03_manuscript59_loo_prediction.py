#!/usr/bin/env python3
"""生成《59初稿》第一问留一预测检验结果。

输入：output/data_audit/tables/cleaned_attachment1.csv
输出：output/q1/manuscript59/loo_predictions.csv
      output/q1/manuscript59/loo_metrics_by_combination.csv
      output/q1/manuscript59/table3_loo_summary.csv
      output/q1/manuscript59/summary.json
      output/q1/manuscript59/artifact_manifest.csv
职责：逐组合、逐响应删除一个温度点，以其余点拟合直线并预测删除点，冻结表3指标。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUT = ROOT / "output/q1/manuscript59"
SCRIPT = Path(__file__).resolve()
RESPONSES = {
    "ethanol_conversion_pct": "乙醇转化率",
    "c4_selectivity_pct": "C4烯烃选择性",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    prediction_rows: list[dict] = []
    metric_rows: list[dict] = []

    for catalyst_id, group in data.groupby("catalyst_id", sort=True):
        group = group.sort_values("temperature_c").reset_index(drop=True)
        x = (group["temperature_c"].to_numpy(float) - 350.0) / 25.0
        for response, response_cn in RESPONSES.items():
            y = group[response].to_numpy(float)
            errors = []
            for held_index in range(len(group)):
                keep = np.arange(len(group)) != held_index
                slope, intercept = np.polyfit(x[keep], y[keep], 1)
                prediction = float(intercept + slope * x[held_index])
                error = float(y[held_index] - prediction)
                errors.append(error)
                prediction_rows.append({
                    "catalyst_id": catalyst_id,
                    "response": response,
                    "response_cn": response_cn,
                    "held_temperature_c": float(group.loc[held_index, "temperature_c"]),
                    "actual_pct": float(y[held_index]),
                    "predicted_pct": prediction,
                    "error_pct_point": error,
                    "absolute_error_pct_point": abs(error),
                    "training_count": int(len(group) - 1),
                })
            error_array = np.asarray(errors)
            value_range = float(np.max(y) - np.min(y))
            rmse = float(np.sqrt(np.mean(error_array**2)))
            metric_rows.append({
                "catalyst_id": catalyst_id,
                "response": response,
                "response_cn": response_cn,
                "observation_count": int(len(group)),
                "cv_mae_pct_point": float(np.mean(np.abs(error_array))),
                "cv_rmse_pct_point": rmse,
                "observed_range_pct_point": value_range,
                "nrmse_pct": float(rmse / value_range * 100.0),
            })

    predictions = pd.DataFrame(prediction_rows)
    metrics = pd.DataFrame(metric_rows)
    table3 = (
        metrics.groupby(["response", "response_cn"], sort=False)
        .agg(
            median_cv_mae_pct_point=("cv_mae_pct_point", "median"),
            median_cv_rmse_pct_point=("cv_rmse_pct_point", "median"),
            median_nrmse_pct=("nrmse_pct", "median"),
            combination_count=("catalyst_id", "nunique"),
        )
        .reset_index()
    )

    paths = {
        "predictions": OUT / "loo_predictions.csv",
        "metrics": OUT / "loo_metrics_by_combination.csv",
        "table3": OUT / "table3_loo_summary.csv",
    }
    predictions.to_csv(paths["predictions"], index=False)
    metrics.to_csv(paths["metrics"], index=False)
    table3.to_csv(paths["table3"], index=False)

    summary = {
        "schema_version": "1.0",
        "status": "manuscript59_q1_loo_prediction",
        "prediction_count": int(len(predictions)),
        "combination_response_count": int(len(metrics)),
        "table3": table3.to_dict(orient="records"),
        "scope": "只评估各组合已测温度点的留一线性预测，不支持标签外温度外推",
    }
    summary_path = OUT / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    entries = [
        (INPUT, "input", "清洁附件1"),
        (SCRIPT, "source", "留一预测主程序"),
        (paths["predictions"], "output", "228次逐点预测"),
        (paths["metrics"], "output", "42个组合—响应指标"),
        (paths["table3"], "output", "底稿表3汇总"),
        (summary_path, "output", "结构化摘要"),
    ]
    pd.DataFrame([
        {
            "path": str(path.relative_to(ROOT)),
            "role": role,
            "description": description,
            "producer": str(SCRIPT.relative_to(ROOT)) if role == "output" else "upstream_or_self",
            "consumer": "独立验证及《59初稿》表3",
            "sha256": sha256(path),
        }
        for path, role, description in entries
    ]).to_csv(OUT / "artifact_manifest.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

