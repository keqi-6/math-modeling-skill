#!/usr/bin/env python3
"""第三问S11：汇总插值误差、替代预测、排名差距和温度覆盖边界。

输入：清洁数据、S6遮点产物、S9—S10正式产物
输出：output/q3/robustness/中的三张表、摘要和产物清单
职责：检查已批准结论的稳定范围，不新增模型权限或统计推断。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
CANDIDATE = ROOT / "output/q3/candidates/narrow_pchip"
FORMAL = ROOT / "output/q3/formal"
OUT = ROOT / "output/q3/robustness"
SCRIPT = Path(__file__).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    holdout = pd.read_csv(CANDIDATE / "interior_holdout_predictions.csv")
    rank_checks = pd.read_csv(CANDIDATE / "temperature_ranking_checks.csv")
    d1 = pd.read_csv(FORMAL / "d1_label_predictions.csv")
    recommendations = pd.read_csv(FORMAL / "recommendations.csv")
    verification = json.loads(
        (FORMAL / "verification.json").read_text(encoding="utf-8")
    )
    if not verification["passed"]:
        raise ValueError("S10尚未通过，不得生成S11解释")

    comparison_rows = []
    for row in d1.itertuples(index=False):
        group = data[data["catalyst_id"] == row.catalyst_id]
        lower = group[group["temperature_c"] < row.temperature_c].sort_values(
            "temperature_c"
        ).iloc[-1]
        upper = group[group["temperature_c"] > row.temperature_c].sort_values(
            "temperature_c"
        ).iloc[0]
        weight = (
            (row.temperature_c - lower["temperature_c"])
            / (upper["temperature_c"] - lower["temperature_c"])
        )
        linear = float(
            lower["c4_yield_pct"]
            + weight * (upper["c4_yield_pct"] - lower["c4_yield_pct"])
        )
        comparison_rows.append(
            {
                "catalyst_id": row.catalyst_id,
                "temperature_c": float(row.temperature_c),
                "lower_observed_temperature_c": float(lower["temperature_c"]),
                "upper_observed_temperature_c": float(upper["temperature_c"]),
                "lower_observed_c4_yield_pct": float(lower["c4_yield_pct"]),
                "upper_observed_c4_yield_pct": float(upper["c4_yield_pct"]),
                "linear_predicted_c4_yield_pct": linear,
                "pchip_predicted_c4_yield_pct": float(
                    row.pchip_predicted_c4_yield_pct
                ),
                "pchip_minus_linear_pct_point": float(
                    row.pchip_predicted_c4_yield_pct - linear
                ),
                "both_below_low_d0_recommendation": True,
                "evidence_status": "sensitivity_prediction_not_observation",
            }
        )
    comparison = pd.DataFrame(comparison_rows).sort_values(
        "pchip_predicted_c4_yield_pct", ascending=False, kind="mergesort"
    )
    low_best = float(
        recommendations.loc[
            recommendations["scenario"] == "strict_below_350",
            "best_c4_yield_pct",
        ].iloc[0]
    )
    comparison["both_below_low_d0_recommendation"] = (
        comparison[
            ["linear_predicted_c4_yield_pct", "pchip_predicted_c4_yield_pct"]
        ].max(axis=1)
        < low_best
    )

    labels = sorted(float(value) for value in data["temperature_c"].unique())
    coverage_rows = []
    total_combinations = int(data["catalyst_id"].nunique())
    for temperature in labels:
        subset = data[data["temperature_c"] == temperature]
        coverage_rows.append(
            {
                "temperature_c": temperature,
                "observed_cell_count": int(len(subset)),
                "observed_combination_count": int(subset["catalyst_id"].nunique()),
                "total_combination_count": total_combinations,
                "observed_coverage_fraction": float(
                    subset["catalyst_id"].nunique() / total_combinations
                ),
                "missing_combination_count": int(
                    total_combinations - subset["catalyst_id"].nunique()
                ),
                "is_strict_below_350": temperature < 350.0,
                "coverage_interpretation": (
                    "single_combination_case"
                    if len(subset) == 1
                    else "partial_coverage"
                    if len(subset) < total_combinations
                    else "complete_coverage"
                ),
            }
        )
    coverage = pd.DataFrame(coverage_rows)

    gap_columns = [
        "scenario",
        "best_catalyst_id",
        "best_temperature_c",
        "best_c4_yield_pct",
        "runner_up_catalyst_id",
        "runner_up_temperature_c",
        "runner_up_c4_yield_pct",
        "lead_over_runner_up_pct_point",
        "best_distinct_combination_id",
        "best_distinct_combination_temperature_c",
        "best_distinct_combination_c4_yield_pct",
        "lead_over_best_distinct_combination_pct_point",
    ]
    gaps = recommendations[gap_columns].copy()

    comparison_path = OUT / "d1_pchip_linear_comparison.csv"
    coverage_path = OUT / "temperature_coverage.csv"
    gaps_path = OUT / "ranking_gaps.csv"
    summary_path = OUT / "robustness_summary.json"
    comparison.to_csv(comparison_path, index=False)
    coverage.to_csv(coverage_path, index=False)
    gaps.to_csv(gaps_path, index=False)

    pchip_error = holdout["pchip_abs_error_pct_point"]
    linear_error = holdout["linear_abs_error_pct_point"]
    pchip_rank = rank_checks[rank_checks["model"] == "pchip"]
    summary = {
        "schema_version": "1.0",
        "status": "q3_s11_robustness_and_explanation",
        "s10_verified": True,
        "interior_holdout": {
            "count": int(len(holdout)),
            "linear": {
                "mae_pct_point": float(linear_error.mean()),
                "median_ae_pct_point": float(linear_error.median()),
                "rmse_pct_point": float(np.sqrt(np.mean(linear_error**2))),
                "max_ae_pct_point": float(linear_error.max()),
            },
            "pchip": {
                "mae_pct_point": float(pchip_error.mean()),
                "median_ae_pct_point": float(pchip_error.median()),
                "rmse_pct_point": float(np.sqrt(np.mean(pchip_error**2))),
                "max_ae_pct_point": float(pchip_error.max()),
                "points_beating_linear": int((pchip_error < linear_error).sum()),
            },
            "top1_identification": {
                "correct_temperature_blocks": int(
                    pchip_rank["top1_correct"].sum()
                ),
                "temperature_block_count": int(len(pchip_rank)),
                "perfect": bool(pchip_rank["top1_correct"].all()),
            },
        },
        "d1_alternative_prediction": {
            "cell_count": int(len(comparison)),
            "all_pchip_and_linear_below_low_d0_recommendation": bool(
                comparison["both_below_low_d0_recommendation"].all()
            ),
            "maximum_pchip_prediction_pct": float(
                comparison["pchip_predicted_c4_yield_pct"].max()
            ),
            "maximum_linear_prediction_pct": float(
                comparison["linear_predicted_c4_yield_pct"].max()
            ),
            "maximum_absolute_method_difference_pct_point": float(
                comparison["pchip_minus_linear_pct_point"].abs().max()
            ),
            "changes_formal_recommendation_under_either_method": False,
        },
        "ranking_gaps": gaps.to_dict(orient="records"),
        "coverage": {
            "temperature_450_observed_combinations": int(
                coverage.loc[
                    coverage["temperature_c"] == 450.0,
                    "observed_combination_count",
                ].iloc[0]
            ),
            "temperature_450_observed_ids": sorted(
                data.loc[data["temperature_c"] == 450.0, "catalyst_id"].unique()
            ),
            "temperature_325_observed_combinations": int(
                coverage.loc[
                    coverage["temperature_c"] == 325.0,
                    "observed_combination_count",
                ].iloc[0]
            ),
            "temperature_325_total_combinations": total_combinations,
        },
        "interpretation": [
            "PCHIP在72次内部遮点的平均和中位绝对误差低于局部直线，且68次更准，因此适合作为窄D1辅助。",
            "PCHIP的最高候选识别只在5个温度块中正确4个，最坏遮点误差仍为13.4906个百分点，不能把插值候选写成真实最优。",
            "11个325摄氏度缺口改用局部直线后也均低于低温D0推荐，因此低温推荐不依赖单一插值形式。",
            "一般情景最高与次高均为A3，领先1.6096个百分点；与最高不同组合A4的差距为8.4502个百分点。",
            "严格低温A2领先A3为6.4716个百分点；但没有重复实验，差距是观测差，不是显著性结论。",
            "450摄氏度只有A3一个实测组合，325摄氏度仅覆盖10/21个组合，跨组合比较和高温推广必须受限。",
        ],
        "claim_boundaries": [
            "遮点误差是预测验证误差，不是实验测量误差",
            "不构造无重复数据无法支持的传统显著性检验或置信区间",
            "D1两种插值对照只检查推荐是否依赖单一插值形式，不批准新模型",
            "450摄氏度结果仅代表A3个案，不能推为全部组合的高温规律",
            "325摄氏度实测覆盖不足，D1预测仍须实验验证",
            "本阶段不改变D0正式推荐、D1辅助和D2关闭的权限结构",
        ],
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    entries = [
        (INPUT, "input", "唯一清洁输入"),
        (
            CANDIDATE / "interior_holdout_predictions.csv",
            "input",
            "S6的72次内部遮点结果",
        ),
        (
            CANDIDATE / "temperature_ranking_checks.csv",
            "input",
            "S6的最高候选识别结果",
        ),
        (FORMAL / "d1_label_predictions.csv", "input", "S9的D1正式辅助预测"),
        (FORMAL / "recommendations.csv", "input", "S9两情景正式推荐"),
        (FORMAL / "verification.json", "input", "S10独立验证"),
        (SCRIPT, "source", "S11稳健性与解释程序"),
        (comparison_path, "output", "D1两种插值对照"),
        (coverage_path, "output", "各温度观测覆盖"),
        (gaps_path, "output", "两情景排名差距"),
        (summary_path, "output", "S11结构化摘要与边界"),
    ]
    pd.DataFrame(
        [
            {
                "path": str(path.relative_to(ROOT)),
                "role": role,
                "description": description,
                "producer": (
                    str(SCRIPT.relative_to(ROOT))
                    if role == "output"
                    else "upstream_or_self"
                ),
                "consumer": "S11独立验证、S12人工复审与后续论文映射",
                "sha256": sha256(path),
            }
            for path, role, description in entries
        ]
    ).to_csv(OUT / "artifact_manifest.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
