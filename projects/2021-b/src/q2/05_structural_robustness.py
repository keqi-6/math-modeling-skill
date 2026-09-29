#!/usr/bin/env python3
"""第二问S11：保持组合—温度实验结构的稳健性与边界检查。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
TABLES = ROOT / "output/q2/tables"
OUT = ROOT / "output/q2"
COMMON_TEMPERATURES = [250.0, 275.0, 300.0, 350.0]
RESPONSES = {
    "ethanol_conversion_pct": "乙醇转化率",
    "c4_selectivity_pct": "C4烯烃选择性",
}


def decomposition(data: pd.DataFrame, response: str) -> dict:
    """对任意完整I×J交叉表计算加和分解和效应排序。"""
    combinations = sorted(data["catalyst_id"].unique())
    temperatures = sorted(data["temperature_c"].unique())
    expected = len(combinations) * len(temperatures)
    if len(data) != expected:
        raise ValueError(f"非完整交叉表: rows={len(data)}, expected={expected}")
    grand = float(data[response].mean())
    combination_means = data.groupby("catalyst_id")[response].mean()
    temperature_means = data.groupby("temperature_c")[response].mean()
    combination_effects = combination_means - grand
    temperature_effects = temperature_means - grand
    fitted = (
        data["catalyst_id"].map(combination_means)
        + data["temperature_c"].map(temperature_means)
        - grand
    )
    residual = data[response] - fitted
    total_ss = float(np.sum((data[response] - grand) ** 2))
    combination_ss = float(len(temperatures) * np.sum(combination_effects**2))
    temperature_ss = float(len(combinations) * np.sum(temperature_effects**2))
    nonadditive_ss = float(np.sum(residual**2))
    maximum_index = residual.abs().idxmax()
    maximum_row = data.loc[maximum_index]
    ordered = combination_effects.sort_values(ascending=False)
    temperature_differences = np.diff(temperature_means.sort_index().to_numpy())
    return {
        "combination_share": combination_ss / total_ss,
        "temperature_share": temperature_ss / total_ss,
        "nonadditive_share": nonadditive_ss / total_ss,
        "closure_error": total_ss - combination_ss - temperature_ss - nonadditive_ss,
        "top5": ordered.head(5).index.tolist(),
        "bottom5": ordered.tail(5).index.tolist(),
        "temperature_mean_increasing": bool(np.all(temperature_differences > 0)),
        "minimum_temperature_mean_step_pct_point": (
            float(temperature_differences.min())
            if len(temperature_differences)
            else np.nan
        ),
        "maximum_residual_catalyst": maximum_row["catalyst_id"],
        "maximum_residual_temperature_c": float(maximum_row["temperature_c"]),
        "maximum_absolute_residual_pct_point": float(abs(residual.loc[maximum_index])),
        "residual": residual,
    }


def retention(new: list[str], baseline: list[str], retained: set[str]) -> tuple[int, float]:
    target = set(baseline) & retained
    overlap = len(set(new) & target)
    return overlap, overlap / len(target)


def build_deletion_tables(common: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    combination_rows = []
    temperature_rows = []
    baselines = {}
    for response, response_cn in RESPONSES.items():
        baseline = decomposition(common, response)
        baselines[response] = baseline
        for omitted in sorted(common["catalyst_id"].unique()):
            subset = common[common["catalyst_id"] != omitted].copy()
            result = decomposition(subset, response)
            retained = set(subset["catalyst_id"])
            top_count, top_fraction = retention(
                result["top5"], baseline["top5"], retained
            )
            bottom_count, bottom_fraction = retention(
                result["bottom5"], baseline["bottom5"], retained
            )
            combination_rows.append(
                {
                    "response": response,
                    "response_cn": response_cn,
                    "omitted_catalyst_id": omitted,
                    "combination_count": 20,
                    "temperature_count": 4,
                    "cell_count": 80,
                    "combination_share": result["combination_share"],
                    "temperature_share": result["temperature_share"],
                    "nonadditive_share": result["nonadditive_share"],
                    "combination_share_exceeds_temperature_share": (
                        result["combination_share"] > result["temperature_share"]
                    ),
                    "temperature_mean_increasing": result[
                        "temperature_mean_increasing"
                    ],
                    "minimum_temperature_mean_step_pct_point": result[
                        "minimum_temperature_mean_step_pct_point"
                    ],
                    "top5_overlap_count": top_count,
                    "top5_retention_fraction": top_fraction,
                    "bottom5_overlap_count": bottom_count,
                    "bottom5_retention_fraction": bottom_fraction,
                    "maximum_residual_catalyst": result[
                        "maximum_residual_catalyst"
                    ],
                    "maximum_residual_temperature_c": result[
                        "maximum_residual_temperature_c"
                    ],
                    "maximum_absolute_residual_pct_point": result[
                        "maximum_absolute_residual_pct_point"
                    ],
                    "closure_error": result["closure_error"],
                }
            )
        for omitted in COMMON_TEMPERATURES:
            subset = common[common["temperature_c"] != omitted].copy()
            result = decomposition(subset, response)
            retained = set(subset["catalyst_id"])
            top_count, top_fraction = retention(
                result["top5"], baseline["top5"], retained
            )
            bottom_count, bottom_fraction = retention(
                result["bottom5"], baseline["bottom5"], retained
            )
            temperature_rows.append(
                {
                    "response": response,
                    "response_cn": response_cn,
                    "omitted_temperature_c": omitted,
                    "combination_count": 21,
                    "temperature_count": 3,
                    "cell_count": 63,
                    "combination_share": result["combination_share"],
                    "temperature_share": result["temperature_share"],
                    "nonadditive_share": result["nonadditive_share"],
                    "combination_share_exceeds_temperature_share": (
                        result["combination_share"] > result["temperature_share"]
                    ),
                    "temperature_mean_increasing": result[
                        "temperature_mean_increasing"
                    ],
                    "minimum_temperature_mean_step_pct_point": result[
                        "minimum_temperature_mean_step_pct_point"
                    ],
                    "top5_overlap_count": top_count,
                    "top5_retention_fraction": top_fraction,
                    "bottom5_overlap_count": bottom_count,
                    "bottom5_retention_fraction": bottom_fraction,
                    "maximum_residual_catalyst": result[
                        "maximum_residual_catalyst"
                    ],
                    "maximum_residual_temperature_c": result[
                        "maximum_residual_temperature_c"
                    ],
                    "maximum_absolute_residual_pct_point": result[
                        "maximum_absolute_residual_pct_point"
                    ],
                    "closure_error": result["closure_error"],
                }
            )
    return pd.DataFrame(combination_rows), pd.DataFrame(temperature_rows), baselines


def build_flag_diagnostic(common: pd.DataFrame, baselines: dict) -> pd.DataFrame:
    rows = []
    for response, response_cn in RESPONSES.items():
        flags = (
            common[f"{response}_global_iqr_flag"]
            | common[f"{response}_within_temperature_flag"]
        )
        absolute = baselines[response]["residual"].abs()
        top10_indices = set(absolute.nlargest(10).index)
        flagged_indices = set(common.index[flags])
        largest_index = absolute.idxmax()
        rows.append(
            {
                "response": response,
                "response_cn": response_cn,
                "common_domain_flagged_cell_count": int(flags.sum()),
                "top10_absolute_residual_flagged_count": len(
                    top10_indices & flagged_indices
                ),
                "largest_residual_cell_is_flagged": largest_index in flagged_indices,
                "flagged_catalyst_count": int(common.loc[flags, "catalyst_id"].nunique()),
                "flagged_catalysts": "|".join(
                    sorted(common.loc[flags, "catalyst_id"].unique())
                ),
            }
        )
    return pd.DataFrame(rows)


def build_supplemental_diagnostic() -> pd.DataFrame:
    source = pd.read_csv(TABLES / "supplemental_matched_change_summary.csv")
    source["nonnegative_share"] = (
        source["positive_count"] + source["zero_count"]
    ) / source["paired_combination_count"]
    source["supports_common_domain_direction"] = source["median_change_pct_point"] > 0
    source["scope"] = np.where(
        source["domain"] == "a3_case",
        "A3 individual case only",
        "matched combinations only",
    )
    return source


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    data = pd.read_csv(INPUT)
    common = data[data["temperature_c"].isin(COMMON_TEMPERATURES)].copy()
    common = common.sort_values(["catalyst_id", "temperature_c"]).reset_index(drop=True)
    combination_table, temperature_table, baselines = build_deletion_tables(common)
    flag_table = build_flag_diagnostic(common, baselines)
    supplemental_table = build_supplemental_diagnostic()

    combination_table.to_csv(
        TABLES / "robustness_leave_combination_out.csv", index=False
    )
    temperature_table.to_csv(
        TABLES / "robustness_leave_temperature_out.csv", index=False
    )
    flag_table.to_csv(TABLES / "robustness_flag_diagnostic.csv", index=False)
    supplemental_table.to_csv(
        TABLES / "robustness_supplemental_temperature.csv", index=False
    )

    responses = {}
    for response, response_cn in RESPONSES.items():
        combination_subset = combination_table[
            combination_table["response"] == response
        ]
        temperature_subset = temperature_table[
            temperature_table["response"] == response
        ]
        flag_row = flag_table[flag_table["response"] == response].iloc[0]
        responses[response] = {
            "response_cn": response_cn,
            "leave_combination_out": {
                "runs": int(len(combination_subset)),
                "combination_share_range": [
                    float(combination_subset["combination_share"].min()),
                    float(combination_subset["combination_share"].max()),
                ],
                "temperature_share_range": [
                    float(combination_subset["temperature_share"].min()),
                    float(combination_subset["temperature_share"].max()),
                ],
                "nonadditive_share_range": [
                    float(combination_subset["nonadditive_share"].min()),
                    float(combination_subset["nonadditive_share"].max()),
                ],
                "combination_share_exceeds_temperature_all_runs": bool(
                    combination_subset[
                        "combination_share_exceeds_temperature_share"
                    ].all()
                ),
                "temperature_mean_increasing_all_runs": bool(
                    combination_subset["temperature_mean_increasing"].all()
                ),
                "minimum_top5_retention": float(
                    combination_subset["top5_retention_fraction"].min()
                ),
                "minimum_bottom5_retention": float(
                    combination_subset["bottom5_retention_fraction"].min()
                ),
            },
            "leave_temperature_out": {
                "runs": int(len(temperature_subset)),
                "combination_share_range": [
                    float(temperature_subset["combination_share"].min()),
                    float(temperature_subset["combination_share"].max()),
                ],
                "temperature_share_range": [
                    float(temperature_subset["temperature_share"].min()),
                    float(temperature_subset["temperature_share"].max()),
                ],
                "nonadditive_share_range": [
                    float(temperature_subset["nonadditive_share"].min()),
                    float(temperature_subset["nonadditive_share"].max()),
                ],
                "combination_share_exceeds_temperature_all_runs": bool(
                    temperature_subset[
                        "combination_share_exceeds_temperature_share"
                    ].all()
                ),
                "temperature_mean_increasing_all_runs": bool(
                    temperature_subset["temperature_mean_increasing"].all()
                ),
                "minimum_top5_retention": float(
                    temperature_subset["top5_retention_fraction"].min()
                ),
                "minimum_bottom5_retention": float(
                    temperature_subset["bottom5_retention_fraction"].min()
                ),
            },
            "flag_diagnostic": {
                "flagged_cells": int(flag_row["common_domain_flagged_cell_count"]),
                "flagged_among_top10_absolute_residuals": int(
                    flag_row["top10_absolute_residual_flagged_count"]
                ),
                "largest_residual_cell_is_flagged": bool(
                    flag_row["largest_residual_cell_is_flagged"]
                ),
            },
        }

    summary = {
        "status": "q2_s11_structural_robustness_results",
        "responses": responses,
        "supplemental": {
            "matched_rows": int(
                (supplemental_table["domain"] != "a3_case").sum()
            ),
            "matched_direction_supported_rows": int(
                supplemental_table.loc[
                    supplemental_table["domain"] != "a3_case",
                    "supports_common_domain_direction",
                ].sum()
            ),
            "a3_case_rows": int(
                (supplemental_table["domain"] == "a3_case").sum()
            ),
        },
        "claim_boundaries": [
            "删除单位为完整组合或完整温度，不删除或替换单个实验单元",
            "异常标记用于影响诊断，不作为错误或删值证据",
            "325和400摄氏度只在匹配组合中补充方向",
            "450摄氏度只作A3个案",
            "非加和剩余可能混合交互、曲率、实验误差和未记录因素",
        ],
        "literature_interpretation": {
            "supported": (
                "HAP相关乙醇偶联研究显示连续中间步骤和多产物路径可使温度与完整组合"
                "共同影响转化和产物分配，因此可作为非加和现象的候选解释。"
            ),
            "not_supported": (
                "这些文献不能证明本题Co/SiO2-HAP完整组合的具体机理、活化能或单一"
                "配方成分作用。"
            ),
        },
    }
    path = OUT / "robustness_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest = pd.read_csv(OUT / "artifact_manifest.csv")
    new_paths = [
        TABLES / "robustness_leave_combination_out.csv",
        TABLES / "robustness_leave_temperature_out.csv",
        TABLES / "robustness_flag_diagnostic.csv",
        TABLES / "robustness_supplemental_temperature.csv",
        path,
    ]
    relative = [str(item.relative_to(ROOT)).replace("\\", "/") for item in new_paths]
    manifest = manifest[~manifest["relative_path"].isin(relative)]
    rows = pd.DataFrame(
        [
            {
                "relative_path": rel,
                "sha256": sha256(item),
                "producer": "src/q2/05_structural_robustness.py",
            }
            for item, rel in zip(new_paths, relative)
        ]
    )
    pd.concat([manifest, rows], ignore_index=True).to_csv(
        OUT / "artifact_manifest.csv", index=False
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
