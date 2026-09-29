#!/usr/bin/env python3
"""第二问S5：共同温度描述性基线，不拟合正式影响模型。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q2"
TABLES = OUT / "tables"
COMMON_TEMPS = [250.0, 275.0, 300.0, 350.0]
RESPONSES = {
    "ethanol_conversion_pct": "乙醇转化率",
    "c4_selectivity_pct": "C4烯烃选择性",
}


def paired_rows(
    data: pd.DataFrame, from_temp: float, to_temp: float, domain: str
) -> list[dict]:
    left = data[data["temperature_c"] == from_temp].set_index("catalyst_id")
    right = data[data["temperature_c"] == to_temp].set_index("catalyst_id")
    ids = sorted(set(left.index) & set(right.index))
    rows = []
    for response, response_cn in RESPONSES.items():
        for catalyst_id in ids:
            change = float(right.loc[catalyst_id, response] - left.loc[catalyst_id, response])
            rows.append({
                "domain": domain,
                "temperature_from_c": from_temp,
                "temperature_to_c": to_temp,
                "temperature_gap_c": to_temp - from_temp,
                "catalyst_id": catalyst_id,
                "response": response,
                "response_cn": response_cn,
                "value_from_pct": float(left.loc[catalyst_id, response]),
                "value_to_pct": float(right.loc[catalyst_id, response]),
                "change_pct_point": change,
                "change_per_25c_pct_point": change * 25.0 / (to_temp - from_temp),
            })
    return rows


def summarize_changes(changes: pd.DataFrame) -> pd.DataFrame:
    rows = []
    keys = ["domain", "temperature_from_c", "temperature_to_c", "response", "response_cn"]
    for key, group in changes.groupby(keys, sort=False):
        values = group["change_pct_point"]
        standardized = group["change_per_25c_pct_point"]
        minimum = group.loc[values.idxmin()]
        maximum = group.loc[values.idxmax()]
        rows.append(dict(zip(keys, key)) | {
            "paired_combination_count": int(len(group)),
            "positive_count": int((values > 0).sum()),
            "negative_count": int((values < 0).sum()),
            "zero_count": int((values == 0).sum()),
            "mean_change_pct_point": float(values.mean()),
            "median_change_pct_point": float(values.median()),
            "q1_change_pct_point": float(values.quantile(0.25)),
            "q3_change_pct_point": float(values.quantile(0.75)),
            "min_change_pct_point": float(values.min()),
            "min_change_catalyst": minimum["catalyst_id"],
            "max_change_pct_point": float(values.max()),
            "max_change_catalyst": maximum["catalyst_id"],
            "mean_change_per_25c_pct_point": float(standardized.mean()),
            "median_change_per_25c_pct_point": float(standardized.median()),
        })
    return pd.DataFrame(rows)


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    common = data[data["temperature_c"].isin(COMMON_TEMPS)].copy()
    counts = common.groupby("temperature_c")["catalyst_id"].nunique()
    if counts.to_dict() != {temperature: 21 for temperature in COMMON_TEMPS}:
        raise ValueError(f"共同温度覆盖不完整：{counts.to_dict()}")

    distribution_rows = []
    rank_rows = []
    for temperature, group in common.groupby("temperature_c", sort=True):
        for response, response_cn in RESPONSES.items():
            values = group[response]
            minimum = group.loc[values.idxmin()]
            maximum = group.loc[values.idxmax()]
            distribution_rows.append({
                "temperature_c": temperature,
                "response": response,
                "response_cn": response_cn,
                "combination_count": int(len(group)),
                "mean_pct": float(values.mean()),
                "median_pct": float(values.median()),
                "q1_pct": float(values.quantile(0.25)),
                "q3_pct": float(values.quantile(0.75)),
                "min_pct": float(values.min()),
                "min_catalyst": minimum["catalyst_id"],
                "max_pct": float(values.max()),
                "max_catalyst": maximum["catalyst_id"],
                "range_pct_point": float(values.max() - values.min()),
            })
            ranked = group[["catalyst_id", response]].copy()
            ranked["rank_descending"] = ranked[response].rank(
                method="average", ascending=False
            )
            for row in ranked.itertuples(index=False):
                rank_rows.append({
                    "temperature_c": temperature,
                    "response": response,
                    "response_cn": response_cn,
                    "catalyst_id": row.catalyst_id,
                    "value_pct": getattr(row, response),
                    "rank_descending": row.rank_descending,
                })

    distributions = pd.DataFrame(distribution_rows)
    ranks = pd.DataFrame(rank_rows)
    stability_rows = []
    for (response, response_cn, catalyst_id), group in ranks.groupby(
        ["response", "response_cn", "catalyst_id"], sort=False
    ):
        stability_rows.append({
            "response": response,
            "response_cn": response_cn,
            "catalyst_id": catalyst_id,
            "mean_rank": float(group["rank_descending"].mean()),
            "best_rank": float(group["rank_descending"].min()),
            "worst_rank": float(group["rank_descending"].max()),
            "rank_range": float(
                group["rank_descending"].max() - group["rank_descending"].min()
            ),
            "top5_count": int((group["rank_descending"] <= 5).sum()),
            "bottom5_count": int((group["rank_descending"] >= 17).sum()),
        })
    stability = pd.DataFrame(stability_rows)

    rank_pair_rows = []
    for response, response_cn in RESPONSES.items():
        pivot = ranks[ranks["response"] == response].pivot(
            index="catalyst_id", columns="temperature_c", values="rank_descending"
        )
        for from_temp, to_temp in zip(COMMON_TEMPS[:-1], COMMON_TEMPS[1:]):
            before, after = pivot[from_temp], pivot[to_temp]
            shifts = after - before
            rank_pair_rows.append({
                "response": response,
                "response_cn": response_cn,
                "temperature_from_c": from_temp,
                "temperature_to_c": to_temp,
                "spearman_rank_correlation": float(
                    spearmanr(before, after).statistic
                ),
                "mean_absolute_rank_change": float(shifts.abs().mean()),
                "max_absolute_rank_change": float(shifts.abs().max()),
                "max_rank_change_catalyst": shifts.abs().idxmax(),
            })
    rank_pairs = pd.DataFrame(rank_pair_rows)

    common_change_rows = []
    for from_temp, to_temp in zip(COMMON_TEMPS[:-1], COMMON_TEMPS[1:]):
        common_change_rows.extend(paired_rows(common, from_temp, to_temp, "common_21"))
    common_changes = pd.DataFrame(common_change_rows)
    common_change_summary = summarize_changes(common_changes)

    supplemental_rows = []
    supplemental_rows.extend(paired_rows(data, 300.0, 325.0, "matched_325"))
    supplemental_rows.extend(paired_rows(data, 325.0, 350.0, "matched_325"))
    supplemental_rows.extend(paired_rows(data, 350.0, 400.0, "matched_400"))
    supplemental_rows.extend(paired_rows(data, 400.0, 450.0, "a3_case"))
    supplemental = pd.DataFrame(supplemental_rows)
    supplemental_summary = summarize_changes(supplemental)

    top_bottom = {}
    for response, response_cn in RESPONSES.items():
        group = stability[stability["response"] == response].sort_values("mean_rank")
        top_bottom[response] = {
            "response_cn": response_cn,
            "best_mean_rank_combinations": group.head(5)["catalyst_id"].tolist(),
            "worst_mean_rank_combinations": group.tail(5)["catalyst_id"].tolist(),
            "largest_rank_range_combinations": group.nlargest(
                5, "rank_range"
            )["catalyst_id"].tolist(),
        }
    summary = {
        "status": "s5_descriptive_baseline_not_formal_model",
        "input": str(INPUT.relative_to(ROOT)),
        "common_temperature_domain": COMMON_TEMPS,
        "common_cell_count": int(len(common)),
        "common_combination_count": int(common["catalyst_id"].nunique()),
        "common_pair_change_count": int(len(common_changes)),
        "supplemental_pair_change_count": int(len(supplemental)),
        "top_bottom_rank_summary": top_bottom,
        "claim_boundaries": [
            "完整组合是比较单位，不拆分配方成分因果作用",
            "共同温度使用相同21种组合",
            "325和400摄氏度只在匹配子集内比较",
            "450摄氏度只作A3个案",
            "增量异质性只称非加和或交互迹象",
            "本基线不进行显著性检验或未测条件预测",
        ],
    }
    distributions.to_csv(TABLES / "common_temperature_distributions.csv", index=False)
    common_changes.to_csv(TABLES / "common_temperature_paired_changes.csv", index=False)
    common_change_summary.to_csv(
        TABLES / "common_temperature_paired_change_summary.csv", index=False
    )
    ranks.to_csv(TABLES / "common_temperature_ranks.csv", index=False)
    stability.to_csv(TABLES / "common_temperature_rank_stability.csv", index=False)
    rank_pairs.to_csv(TABLES / "common_temperature_rank_pair_summary.csv", index=False)
    supplemental.to_csv(TABLES / "supplemental_matched_changes.csv", index=False)
    supplemental_summary.to_csv(
        TABLES / "supplemental_matched_change_summary.csv", index=False
    )
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
