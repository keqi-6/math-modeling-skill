"""第二问S6候选信息增量诊断，不是正式求解模型。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUTPUT = ROOT / "output/q2/candidates"
TEMPERATURES = [250.0, 275.0, 300.0, 350.0]
RESPONSES = {
    "ethanol_conversion_pct": "乙醇转化率",
    "c4_selectivity_pct": "C4烯烃选择性",
}


def prepare() -> pd.DataFrame:
    data = pd.read_csv(INPUT)
    common = data[data["temperature_c"].isin(TEMPERATURES)].copy()
    coverage = common.groupby("temperature_c")["catalyst_id"].nunique().to_dict()
    if coverage != {temperature: 21 for temperature in TEMPERATURES}:
        raise ValueError(f"共同温度覆盖异常: {coverage}")
    return common.sort_values(["catalyst_id", "temperature_c"]).reset_index(drop=True)


def additive_predict(train: pd.DataFrame, target: pd.DataFrame, response: str) -> np.ndarray:
    grand = train[response].mean()
    combination_effect = train.groupby("catalyst_id")[response].mean() - grand
    temperature_effect = train.groupby("temperature_c")[response].mean() - grand
    return np.array(
        [
            grand
            + combination_effect.get(row.catalyst_id, 0.0)
            + temperature_effect.get(row.temperature_c, 0.0)
            for row in target.itertuples()
        ]
    )


def line_predict(train: pd.DataFrame, target: pd.DataFrame, response: str) -> np.ndarray:
    predictions = []
    for row in target.itertuples():
        subset = train[train["catalyst_id"] == row.catalyst_id]
        if len(subset) < 2:
            predictions.append(float(train[response].mean()))
            continue
        slope, intercept = np.polyfit(
            subset["temperature_c"].to_numpy(), subset[response].to_numpy(), 1
        )
        predictions.append(float(intercept + slope * row.temperature_c))
    return np.array(predictions)


def leave_one_cell_out(data: pd.DataFrame, response: str, predictor) -> tuple[float, float]:
    errors = []
    for index in data.index:
        target = data.loc[[index]]
        prediction = predictor(data.drop(index), target, response)[0]
        errors.append(float(target.iloc[0][response] - prediction))
    values = np.asarray(errors)
    return float(np.mean(np.abs(values))), float(np.sqrt(np.mean(values**2)))


def analyse(data: pd.DataFrame, response: str) -> tuple[dict, pd.DataFrame]:
    grand = data[response].mean()
    combination_means = data.groupby("catalyst_id")[response].mean()
    temperature_means = data.groupby("temperature_c")[response].mean()
    total_ss = float(np.sum((data[response] - grand) ** 2))
    combination_ss = float(4 * np.sum((combination_means - grand) ** 2))
    temperature_ss = float(21 * np.sum((temperature_means - grand) ** 2))
    additive_prediction = (
        data["catalyst_id"].map(combination_means)
        + data["temperature_c"].map(temperature_means)
        - grand
    )
    additive_sse = float(np.sum((data[response] - additive_prediction) ** 2))

    slope_rows = []
    line_predictions = pd.Series(index=data.index, dtype=float)
    for catalyst_id, group in data.groupby("catalyst_id"):
        slope, intercept = np.polyfit(
            group["temperature_c"].to_numpy(), group[response].to_numpy(), 1
        )
        line_predictions.loc[group.index] = intercept + slope * group["temperature_c"]
        slope_rows.append(
            {
                "response": response,
                "response_cn": RESPONSES[response],
                "catalyst_id": catalyst_id,
                "slope_per_25c_pct_point": float(slope * 25),
            }
        )
    line_sse = float(np.sum((data[response] - line_predictions) ** 2))
    additive_cv_mae, additive_cv_rmse = leave_one_cell_out(data, response, additive_predict)
    line_cv_mae, line_cv_rmse = leave_one_cell_out(data, response, line_predict)
    slopes = np.array([row["slope_per_25c_pct_point"] for row in slope_rows])

    summary = {
        "response": response,
        "response_cn": RESPONSES[response],
        "observation_count": int(len(data)),
        "additive_parameter_count": 24,
        "combination_line_parameter_count": 42,
        "total_ss": total_ss,
        "combination_ss": combination_ss,
        "temperature_ss": temperature_ss,
        "additive_nonadditive_ss": additive_sse,
        "combination_share_total_ss": combination_ss / total_ss,
        "temperature_share_total_ss": temperature_ss / total_ss,
        "nonadditive_share_total_ss": additive_sse / total_ss,
        "combination_line_sse": line_sse,
        "line_sse_reduction_vs_additive": 1 - line_sse / additive_sse,
        "additive_leave_one_cell_out_mae": additive_cv_mae,
        "additive_leave_one_cell_out_rmse": additive_cv_rmse,
        "line_leave_one_cell_out_mae": line_cv_mae,
        "line_leave_one_cell_out_rmse": line_cv_rmse,
        "slope_per_25c_min": float(np.min(slopes)),
        "slope_per_25c_median": float(np.median(slopes)),
        "slope_per_25c_max": float(np.max(slopes)),
    }
    return summary, pd.DataFrame(slope_rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = prepare()
    summaries = []
    slopes = []
    for response in RESPONSES:
        summary, slope_table = analyse(data, response)
        summaries.append(summary)
        slopes.append(slope_table)
    pd.DataFrame(summaries).to_csv(
        OUTPUT / "candidate_information_comparison.csv", index=False
    )
    pd.concat(slopes, ignore_index=True).to_csv(
        OUTPUT / "candidate_combination_slopes.csv", index=False
    )
    payload = {
        "status": "s6_candidate_diagnostic_not_formal_model",
        "domain": "21 combinations x 4 common temperatures",
        "responses": summaries,
        "boundaries": [
            "平方和占比只作平衡主体域的描述性分解",
            "加和剩余混合交互、曲率、测量误差和未记录因素",
            "逐组合直线用线性形状换取压缩，不证明因果交互",
            "留一误差只比较候选压缩能力，不是未测温度外推证明",
            "混合效应候选因职责不匹配而不作数值试拟合",
        ],
    }
    (OUTPUT / "candidate_information_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
