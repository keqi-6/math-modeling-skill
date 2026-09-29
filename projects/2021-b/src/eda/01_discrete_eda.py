#!/usr/bin/env python3
"""第3步：21种完整组合与7级离散温度的探索性分析。

# 输入: output/data_audit/tables/modeling_dataset.csv, cleaned_attachment2.csv
# 输出: output/eda/tables/*.csv, output/eda/figures/*.{png,pdf}, summary.json, artifact_manifest.csv
# 职责: 只做离散描述、配对变化、排名、Pareto和附件2连续变化，不拟合正式模型。
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables"
OUT = ROOT / "output" / "eda"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
MODEL_DATA = INPUT / "modeling_dataset.csv"
TIME_DATA = INPUT / "cleaned_attachment2.csv"
TEMPERATURES = [250, 275, 300, 325, 350, 400, 450]
COMMON_TEMPERATURES = [250, 275, 300, 350]
RESPONSES = ["ethanol_conversion_pct", "c4_selectivity_pct", "c4_yield_pct"]
LABELS = {
    "ethanol_conversion_pct": "乙醇转化率（%）",
    "c4_selectivity_pct": "C4选择性（%）",
    "c4_yield_pct": "C4收率（%）",
}
COLORS = {"blue": "#0072B2", "orange": "#E69F00", "green": "#009E73",
          "purple": "#CC79A7", "gray": "#73777D", "red": "#D55E00"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def setup() -> None:
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["WenQuanYi Micro Hei", "DejaVu Sans"],
        "axes.unicode_minus": False, "axes.spines.top": False,
        "axes.spines.right": False, "savefig.dpi": 300, "pdf.fonttype": 42,
    })
    sns.set_context("paper", font_scale=1.05)


def save(fig: plt.Figure, name: str) -> list[Path]:
    paths = [FIGURES / f"{name}.png", FIGURES / f"{name}.pdf"]
    for path in paths:
        fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def pareto_ids(group: pd.DataFrame) -> set[str]:
    result = set()
    for row in group.itertuples():
        dominated = (
            (group.ethanol_conversion_pct >= row.ethanol_conversion_pct)
            & (group.c4_selectivity_pct >= row.c4_selectivity_pct)
            & (
                (group.ethanol_conversion_pct > row.ethanol_conversion_pct)
                | (group.c4_selectivity_pct > row.c4_selectivity_pct)
            )
        ).any()
        if not dominated:
            result.add(row.catalyst_id)
    return result


def build_tables(data: pd.DataFrame, time: pd.DataFrame) -> dict[str, pd.DataFrame]:
    common = data[data.temperature_c.isin(COMMON_TEMPERATURES)].copy()
    paired_rows = []
    for left_temp, right_temp in zip(COMMON_TEMPERATURES[:-1], COMMON_TEMPERATURES[1:]):
        left = common[common.temperature_c == left_temp].set_index("catalyst_id")
        right = common[common.temperature_c == right_temp].set_index("catalyst_id")
        for response in RESPONSES:
            changes = right[response] - left[response]
            paired_rows.append({
                "temperature_from_c": left_temp, "temperature_to_c": right_temp,
                "response": response, "pair_count": len(changes),
                "positive_count": int((changes > 0).sum()),
                "zero_count": int((changes == 0).sum()),
                "negative_count": int((changes < 0).sum()),
                "median_change_pct_point": changes.median(),
                "mean_change_pct_point": changes.mean(),
                "minimum_change_pct_point": changes.min(),
                "maximum_change_pct_point": changes.max(),
            })
    paired = pd.DataFrame(paired_rows)

    rank_corr_rows = []
    for response in RESPONSES:
        pivot = common.pivot(index="catalyst_id", columns="temperature_c", values=response)
        for i, left in enumerate(COMMON_TEMPERATURES):
            for right in COMMON_TEMPERATURES[i + 1:]:
                rank_corr_rows.append({
                    "response": response, "temperature_left_c": left,
                    "temperature_right_c": right, "combination_count": len(pivot),
                    "spearman_rank_correlation": pivot[left].corr(pivot[right], method="spearman"),
                })
    rank_correlations = pd.DataFrame(rank_corr_rows)

    rank_rows = []
    for response in RESPONSES:
        subset = common[["catalyst_id", "temperature_c", response]].copy()
        subset["rank"] = subset.groupby("temperature_c")[response].rank(
            method="min", ascending=False
        )
        summary = subset.groupby("catalyst_id").agg(
            mean_rank=("rank", "mean"), best_rank=("rank", "min"),
            worst_rank=("rank", "max"), rank_range=("rank", lambda x: x.max() - x.min()),
            top3_count=("rank", lambda x: int((x <= 3).sum())),
        ).reset_index()
        summary.insert(1, "response", response)
        rank_rows.append(summary)
    rank_stability = pd.concat(rank_rows, ignore_index=True)

    pareto_rows = []
    for temperature, group in data.groupby("temperature_c"):
        frontier = pareto_ids(group)
        for row in group.itertuples():
            pareto_rows.append({
                "temperature_c": temperature, "catalyst_id": row.catalyst_id,
                "ethanol_conversion_pct": row.ethanol_conversion_pct,
                "c4_selectivity_pct": row.c4_selectivity_pct,
                "c4_yield_pct": row.c4_yield_pct,
                "pareto_nondominated": row.catalyst_id in frontier,
            })
    pareto = pd.DataFrame(pareto_rows)

    top = data.sort_values(
        ["temperature_c", "c4_yield_pct"], ascending=[True, False]
    ).groupby("temperature_c", as_index=False).head(5)
    top = top[["temperature_c", "catalyst_id", "ethanol_conversion_pct",
               "c4_selectivity_pct", "c4_yield_pct"]]

    interval_rows = []
    for left, right in zip(time.iloc[:-1].itertuples(), time.iloc[1:].itertuples()):
        for response in RESPONSES:
            change = getattr(right, response) - getattr(left, response)
            interval_rows.append({
                "time_from_min": left.time_min, "time_to_min": right.time_min,
                "time_gap_min": right.time_min - left.time_min, "response": response,
                "change_pct_point": change,
                "change_per_10min_pct_point": change / (right.time_min - left.time_min) * 10,
            })
    time_intervals = pd.DataFrame(interval_rows)

    first, last = time.iloc[0], time.iloc[-1]
    time_summary_rows = []
    for response in RESPONSES:
        start, end = first[response], last[response]
        time_summary_rows.append({
            "response": response, "first_time_min": first.time_min,
            "last_time_min": last.time_min, "first_value_pct": start,
            "last_value_pct": end, "absolute_change_pct_point": end - start,
            "relative_change_pct": (end - start) / start * 100,
            "minimum_pct": time[response].min(), "maximum_pct": time[response].max(),
        })
    time_summary = pd.DataFrame(time_summary_rows)

    capability = pd.DataFrame([
        ("组合内温度变化", "支持", "只限已测离散标签，不声明连续函数"),
        ("全覆盖温度配对比较", "支持", "250、275、300、350℃覆盖全部21种组合"),
        ("325℃总体比较", "有限", "只有10种组合"),
        ("400℃总体比较", "有限", "只有19种组合"),
        ("450℃一般温度效应", "不支持", "只有A3一条观测"),
        ("新配方性能", "不支持", "组合域固定为21种完整类别"),
        ("标签外温度推荐", "不支持", "温度域固定为7个离散标签"),
        ("附件2普遍稳定性", "不支持", "单次未知组合实验，无重复"),
    ], columns=["claim", "status", "reason"])

    return {
        "common_temperature_paired_changes.csv": paired,
        "rank_correlations_common_temperatures.csv": rank_correlations,
        "combination_rank_stability.csv": rank_stability,
        "pareto_by_temperature.csv": pareto,
        "top5_yield_by_temperature.csv": top,
        "attachment2_interval_changes.csv": time_intervals,
        "attachment2_change_summary.csv": time_summary,
        "data_capability_boundaries.csv": capability,
    }


def draw(data: pd.DataFrame, time: pd.DataFrame,
         tables: dict[str, pd.DataFrame]) -> list[Path]:
    paths = []
    ids = sorted(data.catalyst_id.unique(), key=lambda x: (x[0], int(x[1:])))
    common = data[data.temperature_c.isin(COMMON_TEMPERATURES)]

    fig, axes = plt.subplots(1, 3, figsize=(14, 4.2))
    for ax, response, color in zip(axes, RESPONSES, [COLORS["blue"], COLORS["orange"], COLORS["green"]]):
        for cid, group in common.groupby("catalyst_id"):
            ordered = group.sort_values("temperature_c")
            ax.plot(ordered.temperature_c, ordered[response], color=color, alpha=.28,
                    linewidth=.8, linestyle=":", marker="o", markersize=2.5)
        median = common.groupby("temperature_c")[response].median()
        ax.plot(median.index, median.values, color="black", linewidth=2.3,
                marker="D", label="21种组合中位数")
        ax.set(xlabel="全覆盖离散温度（°C）", ylabel=LABELS[response])
        ax.legend(frameon=False)
    fig.suptitle("四个全覆盖温度条件下的组合内响应比较（连线仅辅助观察）")
    fig.tight_layout()
    paths += save(fig, "01_common_temperature_trajectories")

    paired = tables["common_temperature_paired_changes.csv"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.0))
    for ax, response, color in zip(axes, RESPONSES, [COLORS["blue"], COLORS["orange"], COLORS["green"]]):
        subset = paired[paired.response == response]
        labels = [f"{int(x.temperature_from_c)}→{int(x.temperature_to_c)}" for x in subset.itertuples()]
        ax.bar(labels, subset.median_change_pct_point, color=color)
        ax.axhline(0, color="black", linewidth=.8)
        for i, row in enumerate(subset.itertuples()):
            ax.text(i, row.median_change_pct_point, f"{row.positive_count}/21较高",
                    ha="center", va="bottom" if row.median_change_pct_point >= 0 else "top", fontsize=8)
        ax.set(xlabel="离散温度标签变化（°C）", ylabel="配对中位变化（百分点）",
               title=LABELS[response])
    fig.tight_layout()
    paths += save(fig, "02_paired_temperature_changes")

    pareto = tables["pareto_by_temperature.csv"]
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))
    for ax, temperature in zip(axes.flat, COMMON_TEMPERATURES):
        group = pareto[pareto.temperature_c == temperature]
        ax.scatter(group.ethanol_conversion_pct, group.c4_selectivity_pct,
                   c=np.where(group.pareto_nondominated, COLORS["red"], COLORS["gray"]),
                   s=np.where(group.pareto_nondominated, 55, 25), alpha=.85)
        for row in group[group.pareto_nondominated].itertuples():
            ax.annotate(row.catalyst_id, (row.ethanol_conversion_pct, row.c4_selectivity_pct),
                        xytext=(3, 3), textcoords="offset points", fontsize=8)
        ax.set(xlabel="乙醇转化率（%）", ylabel="C4选择性（%）",
               title=f"{temperature} °C")
    fig.suptitle("全覆盖温度下转化率—选择性的Pareto非支配组合")
    fig.tight_layout()
    paths += save(fig, "03_pareto_common_temperatures")

    ranks = tables["combination_rank_stability.csv"]
    y_rank = ranks[ranks.response == "c4_yield_pct"].sort_values("mean_rank")
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.barh(y_rank.catalyst_id, y_rank.mean_rank, color=COLORS["green"])
    ax.invert_yaxis()
    ax.set(xlabel="四个全覆盖温度的平均收率名次（越小越好）",
           ylabel="完整催化剂组合", title="C4收率排名的跨温度稳定性")
    paths += save(fig, "04_yield_average_rank")

    fig, ax = plt.subplots(figsize=(8, 5))
    for response, color, marker in [
        ("ethanol_conversion_pct", COLORS["blue"], "o"),
        ("c4_selectivity_pct", COLORS["orange"], "s"),
        ("c4_yield_pct", COLORS["green"], "^"),
    ]:
        ax.plot(time.time_min, time[response] - time[response].iloc[0],
                color=color, marker=marker, label=LABELS[response])
    ax.axhline(0, color="black", linewidth=.8)
    ax.set(xlabel="时间（min）", ylabel="相对首时刻变化（百分点）",
           title="附件2单次实验相对首时刻的连续变化")
    ax.legend(frameon=False)
    paths += save(fig, "05_attachment2_change_from_first")

    interval = tables["attachment2_interval_changes.csv"]
    fig, axes = plt.subplots(1, 3, figsize=(14, 3.8), sharex=True)
    for ax, response, color in zip(axes, RESPONSES, [COLORS["blue"], COLORS["orange"], COLORS["green"]]):
        subset = interval[interval.response == response]
        labels = [f"{int(x.time_from_min)}→{int(x.time_to_min)}" for x in subset.itertuples()]
        ax.bar(labels, subset.change_per_10min_pct_point, color=color)
        ax.axhline(0, color="black", linewidth=.8)
        ax.tick_params(axis="x", rotation=45)
        ax.set(xlabel="时间区间（min）", ylabel="每10 min变化（百分点）",
               title=LABELS[response])
    fig.tight_layout()
    paths += save(fig, "06_attachment2_interval_rates")
    return paths


def main() -> None:
    started = datetime.now(ZoneInfo("Asia/Shanghai"))
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    setup()
    data = pd.read_csv(MODEL_DATA)
    time = pd.read_csv(TIME_DATA)
    if set(data.catalyst_id) != {*(f"A{i}" for i in range(1, 15)), *(f"B{i}" for i in range(1, 8))}:
        raise ValueError("正式模型接口不是批准的21种完整组合")
    if sorted(data.temperature_c.unique()) != TEMPERATURES:
        raise ValueError("温度域不是批准的7个离散标签")
    tables = build_tables(data, time)
    for name, frame in tables.items():
        frame.to_csv(TABLES / name, index=False, encoding="utf-8-sig")
    figures = draw(data, time, tables)
    summary = {
        "schema_version": "1.0", "stage": "技术主线第3步",
        "scope": "21种完整组合、7级有序离散温度、三个核心响应",
        "continuous_temperature_fitting": False, "missing_cell_imputation": False,
        "artificial_stability_threshold": False,
        "record_count": len(data), "combination_count": data.catalyst_id.nunique(),
        "temperature_levels_c": TEMPERATURES, "full_coverage_temperatures_c": COMMON_TEMPERATURES,
        "attachment2_record_count": len(time),
        "table_count": len(tables), "figure_file_count": len(figures),
    }
    summary_path = OUT / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = OUT / "run_manifest.json"
    manifest_path.write_text(json.dumps({
        "producer": "src/eda/01_discrete_eda.py",
        "started_at": started.isoformat(), "finished_at": datetime.now(
            ZoneInfo("Asia/Shanghai")).isoformat(),
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in [MODEL_DATA, TIME_DATA]},
        "python": sys.version, "platform": platform.platform(),
        "packages": {"pandas": pd.__version__, "numpy": np.__version__,
                     "matplotlib": matplotlib.__version__, "seaborn": sns.__version__},
        "random_seed": None,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts = []
    for path in [summary_path, manifest_path] + [TABLES / name for name in tables] + figures:
        artifacts.append({
            "path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
            "sha256": sha256(path), "producer": "src/eda/01_discrete_eda.py",
            "status": "current",
        })
    pd.DataFrame(artifacts).to_csv(
        OUT / "artifact_manifest.csv", index=False, encoding="utf-8-sig"
    )
    print(json.dumps({"status": "ok", **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
