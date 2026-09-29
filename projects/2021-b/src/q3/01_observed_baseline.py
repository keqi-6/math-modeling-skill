#!/usr/bin/env python3
"""第三问S5：分别枚举一般与严格低温情景的D0实测基线。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q3" / "baseline"
TOP_N = 10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def scenario_rows(data: pd.DataFrame, scenario: str) -> tuple[pd.DataFrame, dict]:
    if scenario == "general":
        feasible = data.copy()
        constraint = "附件1全部D0实测单元"
    elif scenario == "strict_below_350":
        feasible = data[data["temperature_c"] < 350.0].copy()
        constraint = "附件1中temperature_c严格小于350的D0实测单元"
    else:
        raise ValueError(f"未知情景：{scenario}")

    feasible = feasible.sort_values(
        ["c4_yield_pct", "catalyst_id", "temperature_c"],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    feasible["scenario"] = scenario
    feasible["rank"] = feasible.index + 1
    best = feasible.iloc[0]
    feasible["gap_from_best_pct_point"] = (
        float(best["c4_yield_pct"]) - feasible["c4_yield_pct"]
    )
    feasible["gap_from_previous_pct_point"] = (
        feasible["c4_yield_pct"].shift(1) - feasible["c4_yield_pct"]
    )
    feasible.loc[0, "gap_from_previous_pct_point"] = 0.0

    second = feasible.iloc[1]
    distinct = feasible[feasible["catalyst_id"] != best["catalyst_id"]].iloc[0]
    summary = {
        "scenario": scenario,
        "constraint": constraint,
        "feasible_cell_count": int(len(feasible)),
        "combination_count": int(feasible["catalyst_id"].nunique()),
        "temperature_labels_c": sorted(
            float(value) for value in feasible["temperature_c"].unique()
        ),
        "best": {
            "source_excel_row": int(best["source_excel_row"]),
            "catalyst_id": best["catalyst_id"],
            "temperature_c": float(best["temperature_c"]),
            "ethanol_conversion_pct": float(best["ethanol_conversion_pct"]),
            "c4_selectivity_pct": float(best["c4_selectivity_pct"]),
            "c4_yield_pct": float(best["c4_yield_pct"]),
        },
        "runner_up": {
            "source_excel_row": int(second["source_excel_row"]),
            "catalyst_id": second["catalyst_id"],
            "temperature_c": float(second["temperature_c"]),
            "c4_yield_pct": float(second["c4_yield_pct"]),
        },
        "lead_over_runner_up_pct_point": float(
            best["c4_yield_pct"] - second["c4_yield_pct"]
        ),
        "best_distinct_combination": {
            "source_excel_row": int(distinct["source_excel_row"]),
            "catalyst_id": distinct["catalyst_id"],
            "temperature_c": float(distinct["temperature_c"]),
            "c4_yield_pct": float(distinct["c4_yield_pct"]),
        },
        "lead_over_best_distinct_combination_pct_point": float(
            best["c4_yield_pct"] - distinct["c4_yield_pct"]
        ),
    }
    columns = [
        "scenario",
        "rank",
        "source_excel_row",
        "catalyst_id",
        "temperature_c",
        "ethanol_conversion_pct",
        "c4_selectivity_pct",
        "c4_yield_pct",
        "gap_from_best_pct_point",
        "gap_from_previous_pct_point",
    ]
    return feasible[columns].head(TOP_N), summary


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    required = {
        "source_excel_row",
        "catalyst_id",
        "temperature_c",
        "ethanol_conversion_pct",
        "c4_selectivity_pct",
        "c4_yield_pct",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"缺少字段：{sorted(missing)}")
    if data.duplicated(["catalyst_id", "temperature_c"]).any():
        raise ValueError("组合—温度键存在重复")

    formula_error = (
        data["c4_yield_pct"]
        - data["ethanol_conversion_pct"] * data["c4_selectivity_pct"] / 100.0
    ).abs().max()
    if formula_error > 1e-10:
        raise ValueError(f"收率公式不一致：{formula_error}")

    ranking_parts = []
    scenario_summaries = []
    for scenario in ("general", "strict_below_350"):
        ranking, summary = scenario_rows(data, scenario)
        ranking_parts.append(ranking)
        scenario_summaries.append(summary)

    rankings = pd.concat(ranking_parts, ignore_index=True)
    rankings_path = OUT / "top10_observed_rankings.csv"
    scenario_path = OUT / "scenario_summary.csv"
    summary_path = OUT / "summary.json"
    rankings.to_csv(rankings_path, index=False)
    pd.DataFrame([
        {
            "scenario": item["scenario"],
            "constraint": item["constraint"],
            "feasible_cell_count": item["feasible_cell_count"],
            "combination_count": item["combination_count"],
            "temperature_labels_c": "|".join(
                f"{value:g}" for value in item["temperature_labels_c"]
            ),
            "best_catalyst_id": item["best"]["catalyst_id"],
            "best_temperature_c": item["best"]["temperature_c"],
            "best_c4_yield_pct": item["best"]["c4_yield_pct"],
            "runner_up_catalyst_id": item["runner_up"]["catalyst_id"],
            "runner_up_temperature_c": item["runner_up"]["temperature_c"],
            "runner_up_c4_yield_pct": item["runner_up"]["c4_yield_pct"],
            "lead_over_runner_up_pct_point": item[
                "lead_over_runner_up_pct_point"
            ],
            "best_distinct_combination_id": item[
                "best_distinct_combination"
            ]["catalyst_id"],
            "best_distinct_combination_temperature_c": item[
                "best_distinct_combination"
            ]["temperature_c"],
            "best_distinct_combination_c4_yield_pct": item[
                "best_distinct_combination"
            ]["c4_yield_pct"],
            "lead_over_best_distinct_combination_pct_point": item[
                "lead_over_best_distinct_combination_pct_point"
            ],
        }
        for item in scenario_summaries
    ]).to_csv(scenario_path, index=False)

    summary = {
        "status": "s5_d0_observed_baseline_not_final_recommendation",
        "input": str(INPUT.relative_to(ROOT)),
        "input_sha256": sha256(INPUT),
        "target": "c4_yield_pct",
        "formula": "ethanol_conversion_pct * c4_selectivity_pct / 100",
        "formula_max_abs_error": float(formula_error),
        "top_n_saved_per_scenario": TOP_N,
        "scenarios": scenario_summaries,
        "claim_boundaries": [
            "结果只表示附件1D0实测单元内的最高观测收率",
            "严格低温情景排除350摄氏度",
            "未测单元不填零、不插补且不参与本基线",
            "单次观测排名不表示未来实验中必然仍为第一",
            "本基线不批准D1插值或D2新配方",
        ],
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
