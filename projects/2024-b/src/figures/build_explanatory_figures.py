#!/usr/bin/env python3
"""Generate five explanatory figures from the frozen Q1--Q4 result files."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from fractions import Fraction
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", "/tmp/cumcm_b_matplotlib")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


COLORS = {
    "navy": "#22324A",
    "blue": "#277DA1",
    "teal": "#43AA8B",
    "green": "#2A9D8F",
    "orange": "#F8961E",
    "red": "#D1495B",
    "gray": "#D9E1E8",
    "dark_gray": "#657786",
    "light": "#F7F9FB",
}

SOURCE_PATHS = [
    "output/q1/s5_results.json",
    "output/q1/s5_finite_closure.json",
    "output/q1/s5_large_batch_extension.json",
    "output/q1/s6_large_batch_verification.json",
    "output/q1/s7_quality_state_evaluation.json",
    "output/q1/s7_quality_state_verification.json",
    "output/q2/s5_results.json",
    "output/q3/s5_results.json",
    "output/q4/s5_intervals.json",
    "output/q4/s5_q2_summary.json",
    "output/q4/s5_q3_summary.json",
]

SOURCE_UNITS = {
    "output/q1/s5_results.json": "risk as probability; ASN and absolute gap in inspected items; N as items",
    "output/q1/s5_finite_closure.json": "risk and relative gap as proportions; ASN and absolute gap in inspected items",
    "output/q1/s5_large_batch_extension.json": "risk and average inspection ratio as exact fractions; N as items",
    "output/q1/s6_large_batch_verification.json": "independent exact-fraction verification of large-batch thresholds and metrics",
    "output/q1/s7_quality_state_evaluation.json": "exact average inspected items and ratios over hypothetical within-batch defect counts; N as items",
    "output/q1/s7_quality_state_verification.json": "independent exact-fraction verification of all plotted Q1 quality-state points",
    "output/q2/s5_results.json": "profit in yuan per completed order; policy as four binary decisions",
    "output/q3/s5_results.json": "defect rate as proportion; profit change in yuan per completed order",
    "output/q4/s5_intervals.json": "L, Q and U as exact defect-rate fractions",
    "output/q4/s5_q2_summary.json": "strategy switches as labeled scenario counts",
    "output/q4/s5_q3_summary.json": "strategy switches as labeled scenario counts",
}


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frac(value: str) -> float:
    return float(Fraction(value))


def configure_style() -> None:
    matplotlib.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["WenQuanYi Micro Hei", "DejaVu Sans"],
            "axes.unicode_minus": False,
            "axes.edgecolor": COLORS["dark_gray"],
            "axes.labelcolor": COLORS["navy"],
            "axes.titlecolor": COLORS["navy"],
            "axes.titlesize": 10.5,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "xtick.color": COLORS["navy"],
            "ytick.color": COLORS["navy"],
            "grid.color": "#DCE3EA",
            "grid.linewidth": 0.7,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
            "svg.hashsalt": "cumcm2024-b-explanatory-figures-v2",
        }
    )


def save_figure(fig: plt.Figure, out_dir: Path, stem: str) -> list[Path]:
    outputs = []
    for suffix in ("png", "svg"):
        path = out_dir / f"{stem}.{suffix}"
        metadata = {"Software": "Matplotlib 3.11; generated from frozen project JSON"}
        if suffix == "svg":
            metadata = {"Creator": "build_explanatory_figures.py", "Date": None}
        fig.savefig(path, dpi=240, bbox_inches="tight", pad_inches=0.14, metadata=metadata)
        outputs.append(path)
    plt.close(fig)
    return outputs


def _q1_state_action(key: str, t: int, x: int, n: int, d0: int, d1: int, thresholds: dict[int, int]) -> str:
    """完整动作空间下 (t,x) 的动作类别。

    返回 'continue' | 'stat_accept' | 'stat_reject' | 'fact_accept' | 'fact_reject'。
    事实动作优先于统计阈值；事实条件互斥，统计阈值域与事实边界不重叠。
    """

    if 1 <= t < n and x + (n - t) <= d0:
        return "fact_accept"
    if x >= d1:
        return "fact_reject"
    if t < 1 or t >= n:
        return "continue"
    threshold = thresholds[t]
    if key == "R":
        return "stat_reject" if x >= threshold else "continue"
    return "stat_accept" if x <= threshold else "continue"


def q1_sequential_state(project_root: Path, out_dir: Path) -> list[Path]:
    data = load_json(project_root / "output/q1/s5_finite_closure.json")
    result = next(item for item in data["results"] if item["N"] == 10)
    n, d0, d1 = result["N"], result["D0"], result["D1"]

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.8), sharex=True, sharey=True)
    panels = [
        ("R", "A  情景R：控制错拒风险\n最优规则无统计拒收动作"),
        ("A", "B  情景A：控制错收风险\n仅 t=7, x=0 时统计接收"),
    ]
    marker_style = {
        "continue": dict(marker="o", s=22, facecolor="white", edgecolor=COLORS["dark_gray"], linewidth=0.9, zorder=2),
        "stat_reject": dict(marker="D", s=58, color=COLORS["red"], edgecolor="white", linewidth=0.9, zorder=5),
        "stat_accept": dict(marker="D", s=58, color=COLORS["green"], edgecolor="white", linewidth=0.9, zorder=5),
        "fact_reject": dict(marker="*", s=120, color=COLORS["red"], edgecolor="white", linewidth=0.7, zorder=6),
        "fact_accept": dict(marker="*", s=120, color=COLORS["green"], edgecolor="white", linewidth=0.7, zorder=6),
    }

    for ax, (key, title) in zip(axes, panels):
        scenario = result["scenarios"][key]
        thresholds = {row["t"]: row["threshold"] for row in scenario["thresholds"]}
        reachable = {0: {0}}
        buckets: dict[str, list[tuple[int, int]]] = {k: [] for k in marker_style}
        edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
        for t in range(n):
            next_states = set()
            for x in sorted(reachable.get(t, set())):
                action = _q1_state_action(key, t, x, n, d0, d1, thresholds)
                if action != "continue":
                    buckets[action].append((t, x))
                    continue
                buckets["continue"].append((t, x))
                for next_x in (x, x + 1):
                    next_states.add(next_x)
                    edges.append(((t, x), (t + 1, next_x)))
            reachable[t + 1] = next_states

        terminal = sorted(reachable[n])
        for (t0, x0), (t1, x1) in edges:
            ax.plot([t0, t1], [x0, x1], color="#D8E0E8", linewidth=0.72, alpha=0.7, zorder=1)
        for action, pts in buckets.items():
            if pts:
                xs, ys = zip(*pts)
                ax.scatter(xs, ys, **marker_style[action])
        for values, color in (([x for x in terminal if x <= d0], COLORS["green"]), ([x for x in terminal if x >= d1], COLORS["red"])):
            ax.scatter([n] * len(values), values, s=46, marker="s", color=color, edgecolor="white", linewidth=0.9, zorder=5)

        ax.axvline(n - 0.5, color=COLORS["navy"], linestyle="--", linewidth=0.9)
        ax.set_title(title, fontweight="bold", pad=7, loc="left")
        ax.set_xlabel("已检测件数  t")
        ax.set_xlim(-0.4, n + 0.35)
        ax.set_ylim(-0.35, 2.5)
        ax.set_xticks(range(0, n + 1, 2))
        ax.set_yticks([0, 1, 2])
        ax.grid(alpha=0.45)

        if key == "R":
            ax.annotate("第2件次品出现\n事实拒收", xy=(5, 2), xytext=(2.25, 2.25), ha="center", fontsize=7.2,
                        color=COLORS["red"], fontweight="bold", arrowprops={"arrowstyle": "->", "color": COLORS["red"], "lw": 1.0})
            ax.annotate("前9件全合格\n事实接收", xy=(9, 0), xytext=(6.75, 0.7), ha="center", fontsize=7.1,
                        color=COLORS["green"], fontweight="bold", arrowprops={"arrowstyle": "->", "color": COLORS["green"], "lw": 1.0})
        else:
            ax.annotate("前7件全合格\n统计接收", xy=(7, 0), xytext=(4.45, 0.9), ha="center", fontsize=7.2,
                        color=COLORS["green"], fontweight="bold", arrowprops={"arrowstyle": "->", "color": COLORS["green"], "lw": 1.0})
            ax.annotate("第2件次品出现\n事实拒收", xy=(4, 2), xytext=(1.7, 2.25), ha="center", fontsize=7.1,
                        color=COLORS["red"], fontweight="bold", arrowprops={"arrowstyle": "->", "color": COLORS["red"], "lw": 1.0})

        risk = float(scenario["risk_at_composite_worst_point"]["decimal"])
        asn = float(scenario["ASN_upper_bound"]["decimal"])
        ax.text(0.98, 0.96, f"风险 {risk:.3f} | 平均检测 {asn:.2f}件", transform=ax.transAxes,
                ha="right", va="top", fontsize=6.7, color=COLORS["navy"],
                bbox={"boxstyle": "round,pad=0.18", "fc": "white", "ec": "#CBD5DF", "alpha": 0.94})

    axes[0].set_ylabel("累计发现次品数  x")
    fig.suptitle("问题一：N=10 最优序贯规则的实际可达状态", fontsize=12.5, fontweight="bold", color=COLORS["navy"], y=0.995)
    fig.legend(
        handles=[
            Line2D([0], [0], marker="o", color="#D8E0E8", markerfacecolor="white", markeredgecolor=COLORS["dark_gray"], markersize=6, label="继续抽样"),
            Line2D([0], [0], marker="D", color="none", markerfacecolor=COLORS["green"], markersize=6, label="统计动作（菱形）"),
            Line2D([0], [0], marker="*", color="none", markerfacecolor=COLORS["red"], markersize=9, label="事实动作（星形）"),
            Line2D([0], [0], marker="s", color="none", markerfacecolor=COLORS["navy"], markersize=6, label="全检判定（方形）"),
        ],
        loc="lower center", bbox_to_anchor=(0.5, 0.055), ncol=4, frameon=False, fontsize=6.8,
    )
    fig.text(0.5, 0.012, "绿色为接收、红色为拒收；事实动作不占统计错误预算；R、A为抽样前分别选定的两个情景。",
             ha="center", color=COLORS["dark_gray"], fontsize=7.1)
    fig.tight_layout(rect=(0, 0.145, 1, 0.92), w_pad=1.0)
    return save_figure(fig, out_dir, "q1_sequential_state")


def q1_average_inspection_ratio(project_root: Path, out_dir: Path) -> list[Path]:
    """Show exact stopping effort across hypothetical quality states for frozen N=1000 rules."""

    data = load_json(project_root / "output/q1/s7_quality_state_evaluation.json")
    panels = [
        ("R", "A  用于识别超标批次", COLORS["red"], [101, 150, 200]),
        ("A", "B  用于确认不超标批次", COLORS["blue"], [0, 50, 100]),
    ]
    offsets = {
        ("R", 101): (22, -18),
        ("R", 150): (10, 11),
        ("R", 200): (10, 10),
        ("A", 0): (14, 10),
        ("A", 50): (12, -17),
        ("A", 100): (24, -16),
    }

    fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.45), sharex=True, sharey=True)
    for ax, (scenario, title, color, feature_ds) in zip(axes, panels):
        points = data["scenarios"][scenario]["points"]
        defect_rates = np.array([100 * float(point["defect_rate"]["decimal"]) for point in points])
        inspection_ratios = np.array([100 * float(point["average_inspection_ratio"]["decimal"]) for point in points])
        lookup = {int(point["D"]): point for point in points}

        ax.plot(defect_rates, inspection_ratios, color=color, linewidth=2.05, zorder=2)
        ax.scatter(defect_rates, inspection_ratios, s=8, color=color, alpha=0.55, linewidth=0, zorder=3)
        ax.axvline(10, color=COLORS["dark_gray"], linestyle=":", linewidth=1.0, zorder=0)
        ax.axhline(100, color="#C8D2DC", linestyle="--", linewidth=0.9, zorder=0)
        ax.text(10.6, 97.0, "10%标称值", fontsize=7.3, color=COLORS["dark_gray"], va="top")

        for d in feature_ds:
            point = lookup[d]
            x = 100 * float(point["defect_rate"]["decimal"])
            y = 100 * float(point["average_inspection_ratio"]["decimal"])
            ax.scatter([x], [y], s=38, facecolor="white", edgecolor=color, linewidth=1.4, zorder=5)
            ax.annotate(
                f"{x:g}%：{y:.1f}%",
                xy=(x, y),
                xytext=offsets[(scenario, d)],
                textcoords="offset points",
                fontsize=7.5,
                color=color,
                ha="left",
                arrowprops={"arrowstyle": "-", "color": color, "lw": 0.7},
            )

        ax.set_title(title, loc="left", fontweight="bold")
        ax.set_ylabel("平均检测比例（%）")
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 103)
        ax.set_yticks([0, 20, 40, 60, 80, 100])
        ax.grid(axis="y", alpha=0.52)
        ax.spines[["top", "right"]].set_visible(False)

    axes[-1].set_xlabel("批内实际次品率（%）")
    fig.suptitle("问题一：越接近10%边界，平均检测比例越高", fontsize=12.5, fontweight="bold", color=COLORS["navy"], y=0.995)
    fig.tight_layout(rect=(0, 0, 1, 0.95), h_pad=1.05)
    return save_figure(fig, out_dir, "q1_average_inspection_ratio")


def q2_decision_profit(project_root: Path, out_dir: Path) -> list[Path]:
    data = load_json(project_root / "output/q2/s5_results.json")
    scenarios = data["scenarios"]
    scenario_ids = [str(item["scenario_id"]) for item in scenarios]
    row_labels = ["检测零件1", "检测零件2", "检测成品", "拆解坏品"]
    matrix = np.zeros((4, len(scenarios)), dtype=float)
    profits = []
    policy_labels = []

    for col, item in enumerate(scenarios):
        policies = item["best_policy_ids"]
        bits = np.array([[int(bit) for bit in policy] for policy in policies], dtype=int)
        for row in range(4):
            unique = set(bits[:, row])
            matrix[row, col] = float(next(iter(unique))) if len(unique) == 1 else 0.5
        profits.append(float(item["best_expected_profit"]["decimal"]))
        policy_labels.append(" / ".join(policies))

    fig = plt.figure(figsize=(7.2, 5.15))
    grid = fig.add_gridspec(2, 1, height_ratios=[1.15, 1.0], hspace=0.46)
    ax0 = fig.add_subplot(grid[0])
    cmap = ListedColormap(["#E8EDF2", "#F4B942", "#277DA1"])
    norm = BoundaryNorm([-0.25, 0.25, 0.75, 1.25], cmap.N)
    ax0.pcolormesh(
        np.arange(matrix.shape[1] + 1) - 0.5,
        np.arange(matrix.shape[0] + 1) - 0.5,
        matrix,
        cmap=cmap,
        norm=norm,
        shading="flat",
    )
    ax0.set_xlim(-0.5, matrix.shape[1] - 0.5)
    ax0.set_ylim(matrix.shape[0] - 0.5, -0.5)
    for row in range(matrix.shape[0]):
        for col in range(matrix.shape[1]):
            value = matrix[row, col]
            label = "否" if value == 0 else ("是" if value == 1 else "并列分歧")
            color = "white" if value == 1 else COLORS["navy"]
            ax0.text(col, row, label, ha="center", va="center", color=color, fontsize=8.2, fontweight="bold")
    ax0.set_xticks(range(len(scenario_ids)), [f"情形{s}" for s in scenario_ids])
    ax0.set_yticks(range(len(row_labels)), row_labels)
    ax0.set_title("A  六种题设情形的最优固定决策", loc="left", fontweight="bold")
    ax0.tick_params(length=0)
    for spine in ax0.spines.values():
        spine.set_visible(False)
    ax0.legend(
        handles=[
            Patch(facecolor="#E8EDF2", label="不执行"),
            Patch(facecolor="#277DA1", label="执行"),
            Patch(facecolor="#F4B942", label="并列最优方案对此动作有分歧"),
        ],
        loc="upper center",
        bbox_to_anchor=(0.5, -0.14),
        ncol=3,
        frameon=False,
        fontsize=7.2,
    )

    ax1 = fig.add_subplot(grid[1])
    x = np.arange(len(scenarios))
    bars = ax1.bar(x, profits, color=COLORS["teal"], width=0.64)
    ax1.set_xticks(x, [f"情形{s}\n{policy_labels[i]}" for i, s in enumerate(scenario_ids)], fontsize=7.1)
    ax1.set_ylabel("期望利润（元/完成订单）")
    ax1.set_title("B  对应期望利润（精确结果的小数展示）", loc="left", fontweight="bold")
    ax1.set_ylim(0, max(profits) * 1.24)
    ax1.grid(axis="y", alpha=0.55)
    ax1.spines[["top", "right"]].set_visible(False)
    for bar, value in zip(bars, profits):
        ax1.text(bar.get_x() + bar.get_width() / 2, value + 0.35, f"{value:.3f}", ha="center", va="bottom", fontsize=7.3, color=COLORS["navy"])

    fig.suptitle("问题二：最优策略由费用情形共同决定", fontsize=12.5, fontweight="bold", color=COLORS["navy"], y=0.995)
    fig.text(0.5, 0.012, "策略码顺序：检零件1、检零件2、检成品、拆坏品；情形3的1101与1111精确并列。", ha="center", fontsize=7.2, color=COLORS["dark_gray"])
    fig.tight_layout(rect=(0, 0.04, 1, 0.93))
    return save_figure(fig, out_dir, "q2_decision_profit")


def q3_oat_sensitivity(project_root: Path, out_dir: Path) -> list[Path]:
    data = load_json(project_root / "output/q3/s5_results.json")
    scenarios = data["scenarios"]
    nodes = ["P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "S1", "S2", "S3", "F"]
    records = {}
    for node in nodes:
        low = scenarios[f"{node}_LOW"]
        high = scenarios[f"{node}_HIGH"]
        records[node] = {
            "low": float(low["profit_change_from_nominal_decimal"]),
            "high": float(high["profit_change_from_nominal_decimal"]),
            "switch": bool(high["policy_switch_from_nominal"] or low["policy_switch_from_nominal"]),
        }
    ordered = sorted(nodes, key=lambda node: max(abs(records[node]["low"]), abs(records[node]["high"])), reverse=True)
    node_labels = {
        **{f"P{i}": f"零件{i}  P{i}" for i in range(1, 9)},
        **{f"S{i}": f"半成品{i}  S{i}" for i in range(1, 4)},
        "F": "最终装配  F",
    }
    low_values = [records[node]["low"] for node in ordered]
    high_values = [records[node]["high"] for node in ordered]
    y = np.arange(len(ordered))

    fig, ax = plt.subplots(figsize=(7.2, 5.25))
    height = 0.34
    ax.barh(y - height / 2, low_values, height=height, color=COLORS["teal"], label="次品率降至5%")
    ax.barh(y + height / 2, high_values, height=height, color=COLORS["orange"], label="次品率升至15%")
    ax.axvline(0, color=COLORS["navy"], linewidth=1)
    ax.set_yticks(y, [node_labels[node] for node in ordered])
    ax.invert_yaxis()
    ax.set_xlabel("相对名义最优利润的变化（元/完成订单）")
    ax.set_title("十二个节点逐项扰动后的最优利润变化", fontweight="bold", pad=13)
    ax.grid(axis="x", alpha=0.55)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="lower right", frameon=False)

    for yy, low, high in zip(y, low_values, high_values):
        ax.text(low + 0.05, yy - height / 2, f"{low:+.2f}", va="center", ha="left", fontsize=7.1, color=COLORS["navy"])
        ax.text(high - 0.05, yy + height / 2, f"{high:+.2f}", va="center", ha="right", fontsize=7.1, color=COLORS["navy"])

    f_index = ordered.index("F")
    f_high = records["F"]["high"]
    ax.scatter([f_high], [f_index + height / 2], marker="*", s=145, color=COLORS["red"], edgecolor="white", zorder=4)
    ax.annotate(
        "F升至15%时：全1策略加入精确并列最优",
        xy=(f_high, f_index + height / 2),
        xytext=(-3.15, -0.72),
        arrowprops={"arrowstyle": "->", "color": COLORS["red"], "lw": 1.1},
        color=COLORS["red"],
        fontsize=7.6,
    )
    ax.set_xlim(min(high_values) - 0.9, max(low_values) + 0.85)
    ax.set_ylim(len(ordered) - 0.5, -1.05)
    fig.suptitle("问题三：最终装配次品率对利润最敏感", fontsize=12.5, fontweight="bold", color=COLORS["navy"], y=0.995)
    fig.text(0.5, 0.015, "OAT：每次仅改变一个题定节点率；不是置信区间，也不表示多个节点同时变化。", ha="center", fontsize=7.2, color=COLORS["dark_gray"])
    fig.tight_layout(rect=(0, 0.045, 1, 0.95))
    return save_figure(fig, out_dir, "q3_oat_sensitivity")


def q4_sampling_stability(project_root: Path, out_dir: Path) -> list[Path]:
    intervals = load_json(project_root / "output/q4/s5_intervals.json")
    q2 = load_json(project_root / "output/q4/s5_q2_summary.json")
    q3 = load_json(project_root / "output/q4/s5_q3_summary.json")
    order = ["N200_n100", "N500_n20", "N500_n100", "N500_n200", "N1000_n100"]
    labels = ["N=200, n=100", "N=500, n=20", "N=500, n=100", "N=500, n=200", "N=1000, n=100"]
    interval_map = {row["setting_id"]: row for row in intervals["records"] if row["q"] == "1/10"}
    lower = np.array([frac(interval_map[key]["L"]) for key in order])
    center = np.array([frac(interval_map[key]["Q"]) for key in order])
    upper = np.array([frac(interval_map[key]["U"]) for key in order])
    q2_switch = np.array([sum(item["switch_scenario_count"] for item in q2["settings"][key].values()) for key in order])
    q3_switch = np.array([q3["settings"][key]["switch_scenario_count"] for key in order])
    q2_total = 162
    q3_total = np.array([q3["settings"][key]["expanded_labeled_scenario_count"] for key in order])
    q2_pct = 100 * q2_switch / q2_total
    q3_pct = 100 * q3_switch / q3_total
    y = np.arange(len(order))
    row_colors = [COLORS["blue"], COLORS["orange"], COLORS["blue"], COLORS["green"], COLORS["blue"]]

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(11.8, 5.2),
        sharey=True,
        gridspec_kw={"width_ratios": [1.55, 1.0, 1.0], "wspace": 0.24},
    )
    ax0, ax1, ax2 = axes
    for yy, lo, mid, hi, color in zip(y, lower, center, upper, row_colors):
        ax0.errorbar(
            mid,
            yy,
            xerr=np.array([[mid - lo], [hi - mid]]),
            fmt="o",
            color=COLORS["navy"],
            ecolor=color,
            elinewidth=5,
            capsize=5,
            markersize=5,
        )
    ax0.axvline(0.10, color=COLORS["dark_gray"], linestyle="--", linewidth=1)
    ax0.set_yticks(y, labels, fontsize=8.5)
    ax0.invert_yaxis()
    ax0.set_xlim(0, max(upper) + 0.07)
    ax0.set_xlabel("真实次品率的95%估计范围")
    ax0.set_title("A  次品率估计范围", loc="left", fontweight="bold")
    ax0.grid(axis="x", alpha=0.55)
    for yy, lo, hi in zip(y, lower, upper):
        ax0.text(hi + 0.006, yy, f"[{lo:.3f}, {hi:.3f}]", va="center", fontsize=7.6, color=COLORS["navy"])

    bars1 = ax1.barh(y, q2_pct, color=row_colors, height=0.58)
    ax1.set_xlim(0, 60)
    ax1.set_xlabel("策略切换比例（%）")
    ax1.set_title("B  问题二策略切换", loc="left", fontweight="bold")
    ax1.grid(axis="x", alpha=0.55)
    for bar, count, pct in zip(bars1, q2_switch, q2_pct):
        ax1.text(pct + 1.2, bar.get_y() + bar.get_height() / 2, f"{pct:.1f}%", va="center", fontsize=7.8, color=COLORS["navy"])

    bars2 = ax2.barh(y, q3_pct, color=row_colors, height=0.58)
    ax2.set_xlim(0, 92)
    ax2.set_xlabel("策略切换比例（%）")
    ax2.set_title("C  问题三策略切换", loc="left", fontweight="bold")
    ax2.grid(axis="x", alpha=0.55)
    for bar, count, total, pct in zip(bars2, q3_switch, q3_total, q3_pct):
        label_x = pct + 1.4 if pct > 0 else 2.0
        ax2.text(label_x, bar.get_y() + bar.get_height() / 2, f"{pct:.1f}%", va="center", fontsize=7.8, color=COLORS["navy"])
    zero_idx = order.index("N500_n200")
    ax2.scatter([0.8], [zero_idx], marker="*", s=55, color=COLORS["navy"], edgecolor="white", linewidth=0.6, zorder=4)

    for ax in axes:
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.suptitle("问题四：区间收窄通常伴随生产决策更稳定", fontsize=12.5, fontweight="bold", color=COLORS["navy"], y=0.995)
    fig.subplots_adjust(left=0.09, right=0.985, bottom=0.14, top=0.82, wspace=0.28)
    return save_figure(fig, out_dir, "q4_sampling_stability")


def write_manifest(project_root: Path, out_dir: Path, outputs: list[Path]) -> Path:
    source_records = []
    for rel in SOURCE_PATHS:
        path = project_root / rel
        source_records.append(
            {
                "path": rel,
                "sha256": sha256(path),
                "schema": "project post-solution evaluation JSON" if rel.startswith("output/q1/s7_") else "project frozen JSON result",
                "units": SOURCE_UNITS[rel],
                "time_scope": "not_applicable_competition_scenario",
                "space_scope": "not_applicable_competition_scenario",
            }
        )
    manifest = {
        "schema_version": "1.1",
        "status": "working_visuals",
        "generation_command": "python3 -B src/figures/build_explanatory_figures.py --project-root . --output-dir docs/figures",
        "sources": source_records,
        "outputs": [{"path": f"docs/figures/{path.name}", "sha256": sha256(path)} for path in outputs],
        "interpretation_boundaries": [
            "q1 panels are separate sampling scenarios and must not be combined into one two-sided rule",
            "q1 star markers are zero-risk factual stops and do not consume either scenario's statistical error budget",
            "q1 quality-state rates are post-solution evaluation fixtures and do not enter threshold design or create a second quality point",
            "q1 plotted ratios are exact finite-population expected inspection counts divided by N=1000; line segments only guide the eye",
            "q1 large-batch points are exact-risk-verified feasible threshold candidates and are not global optimality claims",
            "q3 OAT changes one node at a time and is not a confidence interval",
            "q4 single-rate confidence sets do not form a joint 95 percent region",
        ],
    }
    path = out_dir / "figure_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/figures"))
    args = parser.parse_args()
    project_root = args.project_root.resolve()
    out_dir = args.output_dir
    if not out_dir.is_absolute():
        out_dir = project_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    configure_style()

    outputs: list[Path] = []
    outputs.extend(q1_sequential_state(project_root, out_dir))
    outputs.extend(q1_average_inspection_ratio(project_root, out_dir))
    outputs.extend(q2_decision_profit(project_root, out_dir))
    outputs.extend(q3_oat_sensitivity(project_root, out_dir))
    outputs.extend(q4_sampling_stability(project_root, out_dir))
    write_manifest(project_root, out_dir, outputs)
    print(json.dumps({"status": "ok", "outputs": [str(path) for path in outputs]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
