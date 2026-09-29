#!/usr/bin/env python3
"""第一问分析：离散关系为主体，增加受限线性概括、诊断与删点稳健性。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables"
OUT = ROOT / "output" / "q1"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
RESPONSES = {"ethanol_conversion_pct": "乙醇转化率", "c4_selectivity_pct": "C4烯烃选择性"}
SELECTIVITIES = {
    "ethylene_selectivity_pct": "乙烯", "c4_selectivity_pct": "C4烯烃",
    "acetaldehyde_selectivity_pct": "乙醛",
    "c4_12_alcohol_selectivity_pct": "C4—C12脂肪醇",
    "methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct":
        "甲基苯甲醛和甲基苯甲醇",
    "other_selectivity_pct": "其他",
}
TIME_RESPONSES = {
    "ethanol_conversion_pct": "乙醇转化率",
    "c4_yield_pct": "C4烯烃收率",
}
COLORS = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
          "purple": "#CC79A7", "gray": "#73777D", "red": "#D55E00", "sky": "#56B4E9"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def setup() -> None:
    matplotlib.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": ["WenQuanYi Micro Hei", "DejaVu Sans"],
        "axes.unicode_minus": False, "axes.spines.top": False, "axes.spines.right": False,
        "savefig.dpi": 300, "pdf.fonttype": 42,
    })


def save_figure(fig: plt.Figure, stem: str) -> list[Path]:
    paths = [FIGURES / f"{stem}.png", FIGURES / f"{stem}.pdf"]
    for path in paths:
        fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def classify_changes(changes: np.ndarray) -> str:
    if np.all(changes > 0):
        return "各相邻温度条件中，较高温度对应较高值"
    if len(changes) >= 2 and changes[0] < 0 and np.all(changes[1:] > 0):
        return "275℃低于250℃，其余较高温度对应较高值"
    if len(changes) >= 2 and changes[-1] < 0 and np.all(changes[:-1] > 0):
        return "最高温度条件低于前一温度，其余较高温度对应较高值"
    if np.all(changes >= 0):
        return "各相邻温度条件中，较高温度对应值不低于前一温度"
    return "存在其他相邻温度条件反向差异"


def direction(value: float, tolerance: float = 1e-12) -> int:
    """把数值方向压缩为-1、0、1，避免浮点噪声制造方向。"""
    if value > tolerance:
        return 1
    if value < -tolerance:
        return -1
    return 0


def linear_diagnostics(x: np.ndarray, y: np.ndarray) -> dict:
    """计算只用于已测范围概括的一元直线及残差诊断。"""
    slope, intercept = np.polyfit(x, y, 1)
    fitted = intercept + slope * x
    residuals = y - fitted
    total = float(np.sum((y - y.mean()) ** 2))
    residual_sum = float(np.sum(residuals ** 2))
    r_squared = 1.0 - residual_sum / total if total > 0 else float("nan")
    return {
        "slope_per_unit": float(slope),
        "intercept_pct": float(intercept),
        "r_squared": float(r_squared),
        "mean_absolute_residual_pct_point": float(np.mean(np.abs(residuals))),
        "max_absolute_residual_pct_point": float(np.max(np.abs(residuals))),
        "fitted": fitted,
        "residuals": residuals,
    }


def analyze_attachment1(
    data: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    adjacent_rows, summary_rows, linear_rows, robustness_rows = [], [], [], []
    for catalyst_id, group in data.groupby("catalyst_id", sort=False):
        ordered = group.sort_values("temperature_c")
        for response, response_cn in RESPONSES.items():
            values = ordered[response].to_numpy(float)
            temperatures = ordered["temperature_c"].to_numpy(float)
            changes = np.diff(values)
            for index, change in enumerate(changes):
                adjacent_rows.append({
                    "catalyst_id": catalyst_id, "response": response, "response_cn": response_cn,
                    "temperature_from_c": temperatures[index],
                    "temperature_to_c": temperatures[index + 1],
                    "value_from_pct": values[index], "value_to_pct": values[index + 1],
                    "change_pct_point": change,
                    "condition_relation": (
                        "较高温度条件的值更高" if change > 0
                        else ("较高温度条件的值更低" if change < 0 else "两温度条件的值相同")
                    ),
                })
            rank_score = pd.Series(temperatures).corr(pd.Series(values), method="spearman")
            summary_rows.append({
                "catalyst_id": catalyst_id, "response": response, "response_cn": response_cn,
                "observed_temperature_count": len(ordered),
                "lowest_temperature_c": temperatures[0], "highest_temperature_c": temperatures[-1],
                "lowest_temperature_value_pct": values[0], "highest_temperature_value_pct": values[-1],
                "total_change_pct_point": values[-1] - values[0],
                "up_interval_count": int(np.sum(changes > 0)),
                "down_interval_count": int(np.sum(changes < 0)),
                "flat_interval_count": int(np.sum(changes == 0)),
                "change_type": classify_changes(changes),
                "rank_direction_score": rank_score,
            })
            diagnostics = linear_diagnostics(temperatures, values)
            slope_sign = direction(diagnostics["slope_per_unit"])
            endpoint_sign = direction(values[-1] - values[0])
            rank_sign = direction(float(rank_score))
            opposite_or_flat = int(np.sum(
                [direction(change) != slope_sign for change in changes]
            ))
            directions_consistent = slope_sign == endpoint_sign == rank_sign
            if not directions_consistent:
                status = "直线不足以概括，必须以离散关系为准"
            elif opposite_or_flat:
                status = "直线仅作辅助，必须同时报告局部反向或持平"
            else:
                status = "方向一致的辅助概括"
            full_slope = diagnostics["slope_per_unit"]
            loo_slopes = []
            for removed_index in range(len(temperatures)):
                keep = np.arange(len(temperatures)) != removed_index
                loo = linear_diagnostics(temperatures[keep], values[keep])
                loo_slope = loo["slope_per_unit"]
                loo_slopes.append(loo_slope)
                robustness_rows.append({
                    "catalyst_id": catalyst_id, "response": response,
                    "response_cn": response_cn,
                    "removed_temperature_c": temperatures[removed_index],
                    "full_slope_per_c": full_slope,
                    "loo_slope_per_c": loo_slope,
                    "slope_direction_changed": direction(loo_slope) != slope_sign,
                })
            linear_rows.append({
                "catalyst_id": catalyst_id, "response": response,
                "response_cn": response_cn,
                "observed_temperature_count": len(temperatures),
                "slope_per_c_pct_point": full_slope,
                "slope_per_25c_pct_point": full_slope * 25.0,
                "intercept_pct": diagnostics["intercept_pct"],
                "spearman_rank_correlation": rank_score,
                "r_squared": diagnostics["r_squared"],
                "mean_absolute_residual_pct_point":
                    diagnostics["mean_absolute_residual_pct_point"],
                "max_absolute_residual_pct_point":
                    diagnostics["max_absolute_residual_pct_point"],
                "slope_direction": slope_sign,
                "endpoint_direction": endpoint_sign,
                "spearman_direction": rank_sign,
                "opposite_or_flat_interval_count": opposite_or_flat,
                "direction_indicators_consistent": directions_consistent,
                "loo_slope_direction_change_count": int(np.sum(
                    [direction(value) != slope_sign for value in loo_slopes]
                )),
                "loo_slope_per_25c_min": float(np.min(loo_slopes) * 25.0),
                "loo_slope_per_25c_max": float(np.max(loo_slopes) * 25.0),
                "linear_summary_status": status,
            })
    return (
        pd.DataFrame(adjacent_rows),
        pd.DataFrame(summary_rows),
        pd.DataFrame(linear_rows),
        pd.DataFrame(robustness_rows),
    )


def analyze_attachment2(
    time: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ratios = time[["time_min", "temperature_c", "ethanol_conversion_pct", "c4_selectivity_pct",
                   "acetaldehyde_selectivity_pct", "c4_12_alcohol_selectivity_pct",
                   "c4_yield_pct"]].copy()
    ratios["acetaldehyde_to_c4_ratio"] = (
        ratios["acetaldehyde_selectivity_pct"] / ratios["c4_selectivity_pct"]
    )
    ratios["alcohol_to_c4_ratio"] = (
        ratios["c4_12_alcohol_selectivity_pct"] / ratios["c4_selectivity_pct"]
    )
    rows = []
    for column, name in SELECTIVITIES.items():
        values = time[column].to_numpy(float)
        rows.append({
            "product_category": name, "column": column, "first_pct": values[0],
            "last_pct": values[-1], "change_pct_point": values[-1] - values[0],
            "minimum_pct": values.min(), "maximum_pct": values.max(),
            "up_interval_count": int(np.sum(np.diff(values) > 0)),
            "down_interval_count": int(np.sum(np.diff(values) < 0)),
        })
    trend_rows = []
    times = time["time_min"].to_numpy(float)
    for response, response_cn in TIME_RESPONSES.items():
        values = time[response].to_numpy(float)
        diagnostics = linear_diagnostics(times, values)
        trend_rows.append({
            "response": response, "response_cn": response_cn,
            "observed_time_count": len(times),
            "slope_per_min_pct_point": diagnostics["slope_per_unit"],
            "slope_per_10min_pct_point": diagnostics["slope_per_unit"] * 10.0,
            "intercept_pct": diagnostics["intercept_pct"],
            "r_squared": diagnostics["r_squared"],
            "mean_absolute_residual_pct_point":
                diagnostics["mean_absolute_residual_pct_point"],
            "max_absolute_residual_pct_point":
                diagnostics["max_absolute_residual_pct_point"],
            "first_pct": values[0], "last_pct": values[-1],
            "change_pct_point": values[-1] - values[0],
            "interpretation_scope": "仅概括本次实验已观测时段，不作外推",
        })
    return ratios, pd.DataFrame(rows), pd.DataFrame(trend_rows)


def draw_profiles(data: pd.DataFrame) -> list[Path]:
    ids = sorted(data["catalyst_id"].unique(), key=lambda x: (x[0], int(x[1:])))
    fig, axes = plt.subplots(7, 3, figsize=(11.2, 17.5), sharex=True)
    for ax, catalyst_id in zip(axes.flat, ids):
        group = data[data.catalyst_id == catalyst_id].sort_values("temperature_c")
        ax.plot(group.temperature_c, group.ethanol_conversion_pct, color=COLORS["blue"],
                marker="o", linewidth=.9, linestyle=":", label="转化率")
        ax.plot(group.temperature_c, group.c4_selectivity_pct, color=COLORS["orange"],
                marker="s", linestyle="--", linewidth=.9, label="C4烯烃选择性")
        temperatures = group.temperature_c.to_numpy(float)
        for response, color in [
            ("ethanol_conversion_pct", COLORS["blue"]),
            ("c4_selectivity_pct", COLORS["orange"]),
        ]:
            fit = linear_diagnostics(temperatures, group[response].to_numpy(float))
            ax.plot(temperatures, fit["fitted"], color=color, linewidth=1.1, alpha=.55)
        ax.set_title(catalyst_id, fontsize=9, fontweight="bold")
        ax.set_ylim(-2, 102)
        ax.tick_params(labelsize=7)
    for ax in axes[-1, :]:
        ax.set_xlabel("温度（°C）", fontsize=8)
    for ax in axes[:, 0]:
        ax.set_ylabel("百分比（%）", fontsize=8)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", ncol=2, frameon=False,
               title="点线为实际观测关系，淡实线为受限线性概括")
    fig.subplots_adjust(top=.965, hspace=.55, wspace=.28)
    return save_figure(fig, "01_each_combination_temperature_profiles")


def draw_change_map(adjacent: pd.DataFrame) -> list[Path]:
    order = sorted(adjacent["catalyst_id"].unique(), key=lambda x: (x[0], int(x[1:])))
    intervals = ["250→275", "275→300", "300→325", "325→350", "350→400", "400→450"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 7), sharey=True)
    for ax, (response, name) in zip(axes, RESPONSES.items()):
        subset = adjacent[adjacent.response == response].copy()
        subset["interval"] = (subset.temperature_from_c.astype(int).astype(str) + "→"
                              + subset.temperature_to_c.astype(int).astype(str))
        pivot = subset.pivot(index="catalyst_id", columns="interval", values="change_pct_point")
        pivot = pivot.reindex(index=order, columns=intervals)
        values = pivot.to_numpy(float)
        vmax = np.nanmax(np.abs(values))
        cmap = matplotlib.colormaps["RdBu_r"].copy()
        cmap.set_bad("#D9DDE2")
        image = ax.imshow(np.ma.masked_invalid(values), aspect="auto", cmap=cmap,
                          vmin=-vmax, vmax=vmax)
        for row_index, column_index in zip(*np.where(np.isnan(values))):
            ax.text(column_index, row_index, "×", ha="center", va="center",
                    fontsize=7, color="#73777D")
        ax.set_xticks(range(len(intervals)), intervals, rotation=45, ha="right", fontsize=8)
        ax.set_yticks(range(len(order)), order, fontsize=8)
        ax.set_title(name)
        ax.set_xlabel("相邻已测温度（°C）")
        fig.colorbar(image, ax=ax, shrink=.75, label="变化（百分点）")
    axes[0].set_ylabel("完整催化剂组合")
    fig.tight_layout()
    return save_figure(fig, "02_adjacent_temperature_change_map")


def draw_attachment2(time: pd.DataFrame, ratios: pd.DataFrame) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    styles = [
        ("ethylene_selectivity_pct", "乙烯", COLORS["sky"], "o"),
        ("c4_selectivity_pct", "C4烯烃", COLORS["orange"], "s"),
        ("acetaldehyde_selectivity_pct", "乙醛", COLORS["red"], "^"),
        ("c4_12_alcohol_selectivity_pct", "C4—C12脂肪醇", COLORS["green"], "D"),
        ("methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct",
         "甲基苯甲醛和甲基苯甲醇", COLORS["purple"], "v"),
        ("other_selectivity_pct", "其他", COLORS["gray"], "P"),
    ]
    for column, label, color, marker in styles:
        axes[0].plot(time.time_min, time[column], label=label, color=color,
                     marker=marker, linewidth=1.5)
    axes[0].set(xlabel="反应时间（min）", ylabel="产物选择性（%）")
    axes[0].legend(frameon=False, fontsize=8, ncol=2)
    axes[1].plot(ratios.time_min, ratios.acetaldehyde_to_c4_ratio,
                 color=COLORS["red"], marker="^", label="乙醛 ÷ C4烯烃")
    axes[1].plot(ratios.time_min, ratios.alcohol_to_c4_ratio,
                 color=COLORS["green"], marker="D", linestyle="--", label="脂肪醇 ÷ C4烯烃")
    axes[1].set(xlabel="反应时间（min）", ylabel="相对比例")
    axes[1].legend(frameon=False)
    fig.tight_layout()
    return save_figure(fig, "03_attachment2_product_shares_and_ratios")


def draw_linear_diagnostics(linear: pd.DataFrame) -> list[Path]:
    order = sorted(linear["catalyst_id"].unique(), key=lambda x: (x[0], int(x[1:])))
    fig, axes = plt.subplots(2, 2, figsize=(12, 7.2), sharex="col")
    for column, (response, response_cn) in enumerate(RESPONSES.items()):
        subset = linear[linear.response == response].set_index("catalyst_id").reindex(order)
        has_exception = subset.opposite_or_flat_interval_count.to_numpy() > 0
        colors = np.where(
            has_exception, COLORS["orange"], COLORS["blue"],
        )
        slope_ax, r2_ax = axes[0, column], axes[1, column]
        slope_ax.bar(order, subset.slope_per_25c_pct_point, color=colors, alpha=.85)
        slope_ax.axhline(0, color="#333333", linewidth=.8)
        slope_ax.set_title(response_cn)
        slope_ax.set_ylabel("每升高25°C的平均变化\n（百分点）")

        r2_ax.scatter(order, subset.r_squared, c=colors, s=34, zorder=3)
        r2_ax.vlines(order, 0.70, subset.r_squared, color=colors, alpha=.45,
                     linewidth=1.0)
        r2_ax.set_ylim(0.70, 1.01)
        r2_ax.set_ylabel(r"决定系数 $R^2$")
        r2_ax.set_xlabel("催化剂组合")
        r2_ax.tick_params(axis="x", rotation=55)
        r2_ax.grid(axis="y", color="#DDDDDD", linewidth=.6)

    from matplotlib.patches import Patch
    fig.legend(
        handles=[
            Patch(facecolor=COLORS["blue"], label="相邻观测均上升"),
            Patch(facecolor=COLORS["orange"], label="存在局部下降或持平"),
        ],
        loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.5, 0.995),
    )
    fig.suptitle("各组合的平均温度斜率与线性概括程度", y=1.03)
    fig.tight_layout()
    return save_figure(fig, "05_attachment1_linear_summary_diagnostics")


def draw_attachment2_trends(time: pd.DataFrame) -> list[Path]:
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2))
    times = time.time_min.to_numpy(float)
    for ax, (response, response_cn), color, marker in zip(
        axes, TIME_RESPONSES.items(), [COLORS["blue"], COLORS["green"]], ["o", "s"]
    ):
        values = time[response].to_numpy(float)
        diagnostics = linear_diagnostics(times, values)
        ax.plot(times, values, color=color, marker=marker, linestyle=":",
                linewidth=1.2, label="实际观测")
        ax.plot(times, diagnostics["fitted"], color="#333333", linewidth=1.2,
                label="简单线性概括")
        ax.set(xlabel="反应时间（min）", ylabel="百分比（%）", title=response_cn)
        ax.legend(frameon=False)
    fig.suptitle("直线仅概括本次实验已观测时段，不用于时间外推")
    fig.tight_layout()
    return save_figure(fig, "06_attachment2_limited_linear_summaries")


def main() -> None:
    setup()
    model_path = INPUT / "modeling_dataset.csv"
    time_path = INPUT / "cleaned_attachment2.csv"
    data = pd.read_csv(model_path, encoding="utf-8-sig")
    time = pd.read_csv(time_path, encoding="utf-8-sig")
    adjacent, summary, linear, robustness = analyze_attachment1(data)
    ratios, selectivity_summary, time_trends = analyze_attachment2(time)
    tables = {
        "attachment1_adjacent_changes.csv": adjacent,
        "attachment1_shape_summary.csv": summary,
        "attachment1_linear_summaries.csv": linear,
        "attachment1_leave_one_out_robustness.csv": robustness,
        "attachment2_relative_ratios.csv": ratios,
        "attachment2_selectivity_summary.csv": selectivity_summary,
        "attachment2_time_linear_summaries.csv": time_trends,
    }
    artifacts: list[Path] = []
    for name, table in tables.items():
        path = TABLES / name
        table.to_csv(path, index=False, encoding="utf-8-sig")
        artifacts.append(path)
    artifacts += draw_profiles(data)
    artifacts += draw_change_map(adjacent)
    artifacts += draw_attachment2(time, ratios)
    artifacts += draw_linear_diagnostics(linear)
    artifacts += draw_attachment2_trends(time)
    type_counts = summary.groupby(["response_cn", "change_type"]).size().rename(
        "combination_count").reset_index()
    result = {
        "input_sha256": {str(model_path.relative_to(ROOT)): sha256(model_path),
                         str(time_path.relative_to(ROOT)): sha256(time_path)},
        "record_counts": {"attachment1": len(data), "attachment2": len(time),
                          "catalyst_combinations": data.catalyst_id.nunique()},
        "shape_type_counts": type_counts.to_dict(orient="records"),
        "attachment2_ratio_change": {
            "acetaldehyde_to_c4_first": float(ratios.acetaldehyde_to_c4_ratio.iloc[0]),
            "acetaldehyde_to_c4_last": float(ratios.acetaldehyde_to_c4_ratio.iloc[-1]),
            "alcohol_to_c4_first": float(ratios.alcohol_to_c4_ratio.iloc[0]),
            "alcohol_to_c4_last": float(ratios.alcohol_to_c4_ratio.iloc[-1]),
        },
        "limited_linear_summary": {
            "attachment1_relation_count": len(linear),
            "attachment1_direction_sensitive_count": int(
                (linear.loo_slope_direction_change_count > 0).sum()
            ),
            "attachment1_with_local_exception_count": int(
                (linear.opposite_or_flat_interval_count > 0).sum()
            ),
            "attachment2": time_trends.to_dict(orient="records"),
        },
        "claim_boundaries": [
            "只描述已测离散温度，不生成标签外温度",
            "相对比例不表示两类产物互相转化",
            "可能反应路线来自文献，不是本题数据直接证明",
            "趋势辅助数字不单独裁决温度是否有影响",
            "简单直线和Spearman只概括方向，不进行显著性推断",
            "拟合残差不是同条件重复实验误差",
        ],
    }
    summary_path = OUT / "summary.json"
    summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    artifacts.append(summary_path)
    manifest_rows = [{"relative_path": str(path.relative_to(ROOT)), "sha256": sha256(path),
                      "producer": "src/q1/01_question1_analysis.py"} for path in artifacts]
    manifest_path = OUT / "artifact_manifest.csv"
    manifest = pd.DataFrame(manifest_rows)
    if manifest_path.exists():
        previous = pd.read_csv(manifest_path, encoding="utf-8-sig")
        retained = previous[
            previous.producer != "src/q1/01_question1_analysis.py"
        ]
        manifest = pd.concat([manifest, retained], ignore_index=True)
    manifest.drop_duplicates("relative_path", keep="first").to_csv(
        manifest_path, index=False, encoding="utf-8-sig")
    print(f"第一问分析完成：{len(tables)}张表、{len(artifacts) - len(tables) - 1}个图文件。")


if __name__ == "__main__":
    main()
