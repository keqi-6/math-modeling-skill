#!/usr/bin/env python3
"""生成《59初稿》第一问表1与图1—3。

输入：清洁附件1、附件2及第一问既有线性与删点产物
输出：output/q1/manuscript59/table1_overall_linear_summary.csv 和 figures/
职责：按底稿口径生成总体统计、标准化相邻差分、删点斜率及时间变化图。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "output/data_audit/tables"
Q1 = ROOT / "output/q1/tables"
OUT = ROOT / "output/q1/manuscript59"
FIGURES = OUT / "figures"
RESPONSES = {
    "ethanol_conversion_pct": "乙醇转化率",
    "c4_selectivity_pct": "C4烯烃选择性",
}


def setup() -> None:
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["WenQuanYi Micro Hei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "savefig.dpi": 300,
        "pdf.fonttype": 42,
    })
    FIGURES.mkdir(parents=True, exist_ok=True)


def save(fig: plt.Figure, stem: str) -> None:
    for extension in ("png", "pdf"):
        fig.savefig(FIGURES / f"{stem}.{extension}", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def table1(linear: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for response, response_cn in RESPONSES.items():
        group = linear[linear["response"] == response]
        rows.append({
            "response": response,
            "response_cn": response_cn,
            "slope_per_25c_min_pct_point": float(group["slope_per_25c_pct_point"].min()),
            "slope_per_25c_max_pct_point": float(group["slope_per_25c_pct_point"].max()),
            "median_slope_per_25c_pct_point": float(group["slope_per_25c_pct_point"].median()),
            "median_mae_pct_point": float(group["mean_absolute_residual_pct_point"].median()),
            "median_r_squared": float(group["r_squared"].median()),
        })
    return pd.DataFrame(rows)


def figure1(data: pd.DataFrame) -> None:
    order = sorted(data["catalyst_id"].unique(), key=lambda value: (value[0], int(value[1:])))
    intervals = ["250→275", "275→300", "300→325", "325→350", "350→400", "400→450"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 7), sharey=True)
    for ax, (response, response_cn) in zip(axes, RESPONSES.items()):
        rows = []
        for catalyst_id, group in data.groupby("catalyst_id", sort=False):
            group = group.sort_values("temperature_c")
            for left, right in zip(group.iloc[:-1].itertuples(), group.iloc[1:].itertuples()):
                rows.append({
                    "catalyst_id": catalyst_id,
                    "interval": f"{int(left.temperature_c)}→{int(right.temperature_c)}",
                    "value": (
                        (getattr(right, response) - getattr(left, response))
                        * 25.0 / (right.temperature_c - left.temperature_c)
                    ),
                })
        pivot = pd.DataFrame(rows).pivot(
            index="catalyst_id", columns="interval", values="value"
        ).reindex(index=order, columns=intervals)
        values = pivot.to_numpy(float)
        limit = float(np.nanmax(np.abs(values)))
        cmap = matplotlib.colormaps["RdBu_r"].copy()
        cmap.set_bad("#D9DDE2")
        image = ax.imshow(np.ma.masked_invalid(values), aspect="auto", cmap=cmap,
                          vmin=-limit, vmax=limit)
        ax.set_xticks(range(len(intervals)), intervals, rotation=45, ha="right")
        ax.set_yticks(range(len(order)), order)
        ax.set_title(response_cn)
        ax.set_xlabel("相邻实测温度（°C）")
        fig.colorbar(image, ax=ax, shrink=.78, label="每升高25°C的变化（百分点）")
    axes[0].set_ylabel("催化剂组合")
    fig.suptitle("不同催化剂组合在相邻温度区间内的响应变化")
    fig.tight_layout()
    save(fig, "figure1_standardized_adjacent_changes")


def figure2(linear: pd.DataFrame, robustness: pd.DataFrame) -> None:
    order = sorted(linear["catalyst_id"].unique(), key=lambda value: (value[0], int(value[1:])))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2), sharex=True)
    for ax, (response, response_cn) in zip(axes, RESPONSES.items()):
        base = linear[linear["response"] == response].set_index("catalyst_id").reindex(order)
        loo = robustness[robustness["response"] == response]
        bounds = loo.groupby("catalyst_id")["loo_slope_per_c"].agg(["min", "max"]).reindex(order) * 25
        full = base["slope_per_25c_pct_point"].to_numpy(float)
        lower = full - bounds["min"].to_numpy(float)
        upper = bounds["max"].to_numpy(float) - full
        positions = np.arange(len(order))
        ax.errorbar(positions, full, yerr=np.vstack([lower, upper]), fmt="o",
                    color="#0072B2", ecolor="#8CBBD9", capsize=2.5, markersize=4)
        ax.axhline(0, color="#333333", linewidth=.8)
        ax.set_xticks(positions, order, rotation=55)
        ax.set_title(response_cn)
        ax.set_ylabel("每升高25°C的回归斜率（百分点）")
        ax.grid(axis="y", color="#DDDDDD", linewidth=.6)
    fig.suptitle("各催化剂组合逐点删除后的回归斜率范围")
    fig.tight_layout()
    save(fig, "figure2_leave_one_out_slopes")


def figure3(time: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    axes[0].plot(time["time_min"], time["ethanol_conversion_pct"], marker="o",
                 label="乙醇转化率")
    axes[0].plot(time["time_min"], time["c4_selectivity_pct"], marker="s",
                 label="C4烯烃选择性")
    axes[0].plot(time["time_min"], time["c4_yield_pct"], marker="^",
                 label="C4烯烃收率")
    axes[0].set(xlabel="反应时间（min）", ylabel="百分比（%）", title="反应指标")
    axes[0].legend(frameon=False)
    products = [
        ("ethylene_selectivity_pct", "乙烯"),
        ("c4_selectivity_pct", "C4烯烃"),
        ("acetaldehyde_selectivity_pct", "乙醛"),
        ("c4_12_alcohol_selectivity_pct", "C4—C12脂肪醇"),
        ("methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct", "甲基苯甲醛和甲基苯甲醇"),
        ("other_selectivity_pct", "其他"),
    ]
    for column, label in products:
        axes[1].plot(time["time_min"], time[column], marker="o", markersize=3, label=label)
    axes[1].set(xlabel="反应时间（min）", ylabel="选择性（%）", title="产物组成")
    axes[1].legend(frameon=False, fontsize=8, ncol=2)
    fig.suptitle("350°C下各反应指标及产物选择性随时间的变化")
    fig.tight_layout()
    save(fig, "figure3_attachment2_time_changes")


def main() -> None:
    setup()
    data = pd.read_csv(DATA / "cleaned_attachment1.csv")
    time = pd.read_csv(DATA / "cleaned_attachment2.csv")
    linear = pd.read_csv(Q1 / "attachment1_linear_summaries.csv")
    robustness = pd.read_csv(Q1 / "attachment1_leave_one_out_robustness.csv")
    summary = table1(linear)
    summary.to_csv(OUT / "table1_overall_linear_summary.csv", index=False)
    figure1(data)
    figure2(linear, robustness)
    figure3(time)
    print("《59初稿》第一问表1与图1—3生成完成")


if __name__ == "__main__":
    main()
