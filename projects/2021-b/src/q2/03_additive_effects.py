#!/usr/bin/env python3
"""第二问S9：按修订S8实现题目回答汇总、加和分解与正式图件。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUT = ROOT / "output/q2"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
COMMON_TEMPERATURES = [250.0, 275.0, 300.0, 350.0]
RESPONSES = {
    "ethanol_conversion_pct": "乙醇转化率",
    "c4_selectivity_pct": "C4 烯烃选择性",
}


def configure_plotting() -> None:
    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["WenQuanYi Micro Hei", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.dpi": 300,
            "pdf.fonttype": 42,
        }
    )
    sns.set_context("paper", font_scale=1.15)


def save_figure(fig: plt.Figure, stem: str) -> None:
    for suffix in ("png", "pdf"):
        fig.savefig(FIGURES / f"{stem}.{suffix}", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def calculate_response(data: pd.DataFrame, response: str) -> tuple[dict, list, list, list]:
    response_cn = RESPONSES[response]
    grand_mean = float(data[response].mean())
    combination_means = data.groupby("catalyst_id")[response].mean()
    temperature_means = data.groupby("temperature_c")[response].mean()
    combination_effects = combination_means - grand_mean
    temperature_effects = temperature_means - grand_mean

    fitted = (
        data["catalyst_id"].map(combination_means)
        + data["temperature_c"].map(temperature_means)
        - grand_mean
    )
    residual = data[response] - fitted

    total_ss = float(np.sum((data[response] - grand_mean) ** 2))
    combination_ss = float(
        len(COMMON_TEMPERATURES) * np.sum(combination_effects**2)
    )
    temperature_ss = float(data["catalyst_id"].nunique() * np.sum(temperature_effects**2))
    nonadditive_ss = float(np.sum(residual**2))

    decomposition = {
        "response": response,
        "response_cn": response_cn,
        "observation_count": int(len(data)),
        "combination_count": int(data["catalyst_id"].nunique()),
        "temperature_count": int(data["temperature_c"].nunique()),
        "identifiable_parameter_count": 24,
        "grand_mean_pct": grand_mean,
        "total_ss": total_ss,
        "combination_ss": combination_ss,
        "temperature_ss": temperature_ss,
        "nonadditive_ss": nonadditive_ss,
        "combination_share": combination_ss / total_ss,
        "temperature_share": temperature_ss / total_ss,
        "nonadditive_share": nonadditive_ss / total_ss,
    }
    combination_rows = [
        {
            "response": response,
            "response_cn": response_cn,
            "catalyst_id": catalyst_id,
            "combination_mean_pct": float(combination_means.loc[catalyst_id]),
            "combination_effect_pct_point": float(combination_effects.loc[catalyst_id]),
        }
        for catalyst_id in combination_means.index
    ]
    temperature_rows = [
        {
            "response": response,
            "response_cn": response_cn,
            "temperature_c": float(temperature),
            "temperature_mean_pct": float(temperature_means.loc[temperature]),
            "temperature_effect_pct_point": float(temperature_effects.loc[temperature]),
        }
        for temperature in temperature_means.index
    ]
    cell_rows = [
        {
            "response": response,
            "response_cn": response_cn,
            "catalyst_id": row.catalyst_id,
            "temperature_c": float(row.temperature_c),
            "observed_pct": float(getattr(row, response)),
            "additive_fitted_pct": float(fitted.loc[row.Index]),
            "nonadditive_residual_pct_point": float(residual.loc[row.Index]),
            "absolute_nonadditive_residual_pct_point": float(abs(residual.loc[row.Index])),
        }
        for row in data.itertuples()
    ]
    return decomposition, combination_rows, temperature_rows, cell_rows


def build_adjusted_profiles(
    combination_table: pd.DataFrame, rank_table: pd.DataFrame
) -> pd.DataFrame:
    """把调整后组合效应与同温排名证据合并为一张逐组合表。"""
    return (
        combination_table.merge(
            rank_table,
            on=["response", "response_cn", "catalyst_id"],
            how="left",
            validate="one_to_one",
        )
        .sort_values(["response", "mean_rank", "catalyst_id"])
        .reset_index(drop=True)
    )


def build_nonadditive_summary(cell_table: pd.DataFrame) -> pd.DataFrame:
    """按完整组合概括未被固定组合和固定温度差异解释的部分。"""
    rows = []
    for (response, response_cn, catalyst_id), subset in cell_table.groupby(
        ["response", "response_cn", "catalyst_id"], sort=False
    ):
        maximum = subset.loc[
            subset["absolute_nonadditive_residual_pct_point"].idxmax()
        ]
        rows.append(
            {
                "response": response,
                "response_cn": response_cn,
                "catalyst_id": catalyst_id,
                "residual_rms_pct_point": float(
                    np.sqrt(np.mean(subset["nonadditive_residual_pct_point"] ** 2))
                ),
                "max_absolute_residual_pct_point": float(
                    maximum["absolute_nonadditive_residual_pct_point"]
                ),
                "max_residual_temperature_c": float(maximum["temperature_c"]),
                "signed_residual_at_max_pct_point": float(
                    maximum["nonadditive_residual_pct_point"]
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["response", "residual_rms_pct_point"], ascending=[True, False]
    )


def build_answer_summary(
    paired: pd.DataFrame,
    decomposition: pd.DataFrame,
    profiles: pd.DataFrame,
    cells: pd.DataFrame,
) -> pd.DataFrame:
    """以题目要求为主键冻结可复算的直接答案，而非仅罗列模型指标。"""
    rows = []
    for item in paired.itertuples(index=False):
        rows.append(
            {
                "question_aspect": "temperature_influence",
                "response": item.response,
                "response_cn": item.response_cn,
                "evidence_unit": (
                    f"{item.temperature_from_c:g}-{item.temperature_to_c:g}C paired combinations"
                ),
                "primary_metric": "positive_pair_share",
                "primary_value": item.positive_count / item.paired_combination_count,
                "secondary_metric": "median_change_pct_point",
                "secondary_value": item.median_change_pct_point,
                "key_object": item.min_change_catalyst,
                "allowed_conclusion": (
                    "共同组合内该温区多数记录上升；负向或零变化按配对计数保留"
                ),
            }
        )

    for item in decomposition.itertuples(index=False):
        subset = profiles[profiles["response"] == item.response]
        highest = subset.nlargest(1, "combination_effect_pct_point").iloc[0]
        lowest = subset.nsmallest(1, "combination_effect_pct_point").iloc[0]
        rows.append(
            {
                "question_aspect": "combination_influence",
                "response": item.response,
                "response_cn": item.response_cn,
                "evidence_unit": "21 complete combinations across four common temperatures",
                "primary_metric": "combination_share_of_total_variation",
                "primary_value": item.combination_share,
                "secondary_metric": "highest_adjusted_effect_pct_point",
                "secondary_value": highest["combination_effect_pct_point"],
                "key_object": highest["catalyst_id"],
                "allowed_conclusion": (
                    f"完整组合存在调整后水平差异；最低组合为{lowest['catalyst_id']}，"
                    "不拆解为单一配方成分作用"
                ),
            }
        )

        response_cells = cells[cells["response"] == item.response]
        maximum = response_cells.nlargest(
            1, "absolute_nonadditive_residual_pct_point"
        ).iloc[0]
        rows.append(
            {
                "question_aspect": "joint_variation",
                "response": item.response,
                "response_cn": item.response_cn,
                "evidence_unit": "84 cells in the balanced combination-temperature table",
                "primary_metric": "nonadditive_share_of_total_variation",
                "primary_value": item.nonadditive_share,
                "secondary_metric": "largest_absolute_residual_pct_point",
                "secondary_value": maximum[
                    "absolute_nonadditive_residual_pct_point"
                ],
                "key_object": (
                    f"{maximum['catalyst_id']}@{maximum['temperature_c']:g}C"
                ),
                "allowed_conclusion": (
                    "温度变化幅度并非完全一致，存在加和结构未解释的共同变化迹象"
                ),
            }
        )
    return pd.DataFrame(rows)


def draw_combination_effects(table: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 6.5), sharey=True)
    order = sorted(table["catalyst_id"].unique(), key=lambda value: (value[0], int(value[1:])))
    positions = np.arange(len(order))
    for ax, (response, response_cn) in zip(axes, RESPONSES.items()):
        subset = table[table["response"] == response].set_index("catalyst_id").loc[order]
        values = subset["combination_effect_pct_point"].to_numpy()
        colors = np.where(values >= 0, "#B54835", "#2D6F9F")
        ax.scatter(values, positions, c=colors, s=34, zorder=3)
        ax.axvline(0, color="#444444", linewidth=0.9)
        ax.set_title(f"{response_cn}：组合平均偏差")
        ax.set_xlabel("相对总体均值的差异（百分点）")
        ax.set_yticks(positions, order)
    axes[0].set_ylabel("催化剂组合")
    fig.suptitle("扣除温度总体差异后的组合偏差", fontweight="bold")
    fig.tight_layout()
    save_figure(fig, "01_additive_combination_effects")


def draw_temperature_effects(table: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    for ax, (response, response_cn) in zip(axes, RESPONSES.items()):
        subset = table[table["response"] == response].sort_values("temperature_c")
        ax.plot(
            subset["temperature_c"],
            subset["temperature_effect_pct_point"],
            marker="o",
            color="#315F82",
            linewidth=1.8,
        )
        ax.axhline(0, color="#444444", linewidth=0.9)
        ax.set_title(response_cn)
        ax.set_xlabel("温度（°C）")
        ax.set_ylabel("相对总体均值的差异（百分点）")
        ax.set_xticks(COMMON_TEMPERATURES)
    fig.suptitle("共同21种组合下的温度固定差异", fontweight="bold")
    fig.tight_layout()
    save_figure(fig, "02_additive_temperature_effects")


def draw_residual_heatmaps(table: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12.5, 7.0), sharey=True)
    order = sorted(table["catalyst_id"].unique(), key=lambda value: (value[0], int(value[1:])))
    for ax, (response, response_cn) in zip(axes, RESPONSES.items()):
        subset = table[table["response"] == response]
        maximum = float(subset["nonadditive_residual_pct_point"].abs().max())
        pivot = (
            subset
            .pivot(
                index="catalyst_id",
                columns="temperature_c",
                values="nonadditive_residual_pct_point",
            )
            .loc[order, COMMON_TEMPERATURES]
        )
        sns.heatmap(
            pivot,
            ax=ax,
            cmap="RdBu_r",
            center=0,
            vmin=-maximum,
            vmax=maximum,
            cbar_kws={"label": "未解释变化（百分点）"},
            linewidths=0.25,
            linecolor="white",
        )
        ax.set_title(response_cn)
        ax.set_xlabel("温度（°C）")
        ax.set_ylabel("催化剂组合" if ax is axes[0] else "")
    fig.suptitle("组合偏差与温度偏差相加后仍未解释的变化", fontweight="bold")
    fig.tight_layout()
    save_figure(fig, "03_nonadditive_residual_heatmaps")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest() -> None:
    rows = []
    for path in sorted(OUT.rglob("*")):
        if not path.is_file() or "candidates" in path.parts:
            continue
        if path.name in {"README.md", "artifact_manifest.csv", "verification.json"}:
            continue
        if (
            path.name.startswith("additive_")
            or path.name
            in {
                "formal_summary.json",
                "question2_answer_summary.csv",
                "combination_adjusted_profiles.csv",
                "nonadditive_combination_summary.csv",
            }
            or path.parent == FIGURES
        ):
            producer = "src/q2/03_additive_effects.py"
        else:
            producer = "src/q2/01_common_temperature_baseline.py"
        rows.append(
            {
                "relative_path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(path),
                "producer": producer,
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "artifact_manifest.csv", index=False)


def main() -> None:
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    common = data[data["temperature_c"].isin(COMMON_TEMPERATURES)].copy()
    coverage = common.groupby("temperature_c")["catalyst_id"].nunique().to_dict()
    if coverage != {temperature: 21 for temperature in COMMON_TEMPERATURES}:
        raise ValueError(f"共同温度覆盖异常: {coverage}")
    common = common.sort_values(["catalyst_id", "temperature_c"]).reset_index(drop=True)

    decompositions = []
    combination_rows = []
    temperature_rows = []
    cell_rows = []
    for response in RESPONSES:
        decomposition, combinations, temperatures, cells = calculate_response(
            common, response
        )
        decompositions.append(decomposition)
        combination_rows.extend(combinations)
        temperature_rows.extend(temperatures)
        cell_rows.extend(cells)

    decomposition_table = pd.DataFrame(decompositions)
    combination_table = pd.DataFrame(combination_rows)
    temperature_table = pd.DataFrame(temperature_rows)
    cell_table = pd.DataFrame(cell_rows)
    decomposition_table.to_csv(TABLES / "additive_decomposition.csv", index=False)
    combination_table.to_csv(TABLES / "additive_combination_effects.csv", index=False)
    temperature_table.to_csv(TABLES / "additive_temperature_effects.csv", index=False)
    cell_table.to_csv(TABLES / "additive_cell_residuals.csv", index=False)

    paired_table = pd.read_csv(TABLES / "common_temperature_paired_change_summary.csv")
    rank_table = pd.read_csv(TABLES / "common_temperature_rank_stability.csv")
    profiles_table = build_adjusted_profiles(combination_table, rank_table)
    nonadditive_table = build_nonadditive_summary(cell_table)
    answer_table = build_answer_summary(
        paired_table,
        decomposition_table,
        profiles_table,
        cell_table,
    )
    answer_table.to_csv(TABLES / "question2_answer_summary.csv", index=False)
    profiles_table.to_csv(TABLES / "combination_adjusted_profiles.csv", index=False)
    nonadditive_table.to_csv(
        TABLES / "nonadditive_combination_summary.csv", index=False
    )

    configure_plotting()
    draw_combination_effects(combination_table)
    draw_temperature_effects(temperature_table)
    draw_residual_heatmaps(cell_table)

    response_summaries = {}
    for row in decomposition_table.itertuples(index=False):
        combinations = profiles_table[profiles_table["response"] == row.response]
        cells = cell_table[cell_table["response"] == row.response]
        paired_response = paired_table[paired_table["response"] == row.response]
        highest = combinations.nlargest(1, "combination_effect_pct_point").iloc[0]
        lowest = combinations.nsmallest(1, "combination_effect_pct_point").iloc[0]
        maximum = cells.nlargest(
            1, "absolute_nonadditive_residual_pct_point"
        ).iloc[0]
        response_summaries[row.response] = {
            "response_cn": row.response_cn,
            "grand_mean_pct": row.grand_mean_pct,
            "answers": {
                "temperature_influence": {
                    "intervals": [
                        {
                            "from_c": item.temperature_from_c,
                            "to_c": item.temperature_to_c,
                            "positive_count": item.positive_count,
                            "negative_count": item.negative_count,
                            "zero_count": item.zero_count,
                            "paired_count": item.paired_combination_count,
                            "median_change_pct_point": item.median_change_pct_point,
                        }
                        for item in paired_response.itertuples(index=False)
                    ],
                    "temperature_share_of_total_variation": row.temperature_share,
                    "allowed_conclusion": "共同组合与共同温度域内的配对条件关联",
                },
                "combination_influence": {
                    "combination_share_of_total_variation": row.combination_share,
                    "highest_adjusted_combination": highest["catalyst_id"],
                    "highest_adjusted_effect_pct_point": highest[
                        "combination_effect_pct_point"
                    ],
                    "lowest_adjusted_combination": lowest["catalyst_id"],
                    "lowest_adjusted_effect_pct_point": lowest[
                        "combination_effect_pct_point"
                    ],
                    "allowed_conclusion": "完整组合的调整后水平差异，不拆成单一成分作用",
                },
                "joint_variation": {
                    "nonadditive_share_of_total_variation": row.nonadditive_share,
                    "largest_residual_cell": {
                        "catalyst_id": maximum["catalyst_id"],
                        "temperature_c": maximum["temperature_c"],
                        "residual_pct_point": maximum[
                            "nonadditive_residual_pct_point"
                        ],
                    },
                    "allowed_conclusion": "存在加和结构未解释的共同变化迹象",
                },
            },
            "technical_decomposition": {
                "combination": row.combination_share,
                "temperature": row.temperature_share,
                "nonadditive": row.nonadditive_share,
            },
            "largest_positive_combination_effects": combinations.nlargest(
                5, "combination_effect_pct_point"
            )["catalyst_id"].tolist(),
            "largest_negative_combination_effects": combinations.nsmallest(
                5, "combination_effect_pct_point"
            )["catalyst_id"].tolist(),
            "largest_absolute_residual_cells": [
                {
                    "catalyst_id": item.catalyst_id,
                    "temperature_c": item.temperature_c,
                    "residual_pct_point": item.nonadditive_residual_pct_point,
                }
                for item in cells.nlargest(
                    5, "absolute_nonadditive_residual_pct_point"
                ).itertuples(index=False)
            ],
        }
    summary = {
        "status": "q2_revised_s9_results",
        "input": str(INPUT.relative_to(ROOT)),
        "method": "A direct evidence plus B fixed combination-temperature additive decomposition",
        "common_temperatures_c": COMMON_TEMPERATURES,
        "common_combination_count": 21,
        "common_cell_count": 84,
        "responses": response_summaries,
        "a_layer": {
            "summary": "output/q2/summary.json",
            "verification": "output/q2/verification.json",
        },
        "direct_answer_tables": {
            "question_summary": "output/q2/tables/question2_answer_summary.csv",
            "combination_profiles": "output/q2/tables/combination_adjusted_profiles.csv",
            "nonadditive_summary": "output/q2/tables/nonadditive_combination_summary.csv",
        },
        "b_layer_verification_expected": "output/q2/formal_verification.json",
        "claim_boundaries": [
            "影响仅指现有实验域内条件差异或关联",
            "完整组合不拆成配方成分的独立作用",
            "非加和剩余不称为纯交互或随机误差",
            "不进行普通交互显著性检验",
            "不预测未测温度或新组合",
        ],
    }
    (OUT / "formal_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_manifest()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
