#!/usr/bin/env python3
"""Render Q3 fixed-policy sensitivity and the bounded Q4-direction bridge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[2]
INK = "#263238"
GRAY = "#7A858B"
BLUE = "#315F78"
GREEN = "#3E7259"
RED = "#A64B43"
ORANGE = "#C88432"


def setup_style() -> None:
    font_path = Path("/mnt/c/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
    else:
        font_name = "DejaVu Sans"
    plt.rcParams.update({
        "font.family": font_name,
        "font.size": 10.0,
        "axes.unicode_minus": False,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "svg.fonttype": "none",
    })


def base_axis(ax: plt.Axes, tag: str, title: str) -> None:
    ax.axhline(0.0, color=GRAY, lw=0.9, ls="--", zorder=0)
    ax.grid(axis="y", color="#D9E0E3", lw=0.7, alpha=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_title(f"{tag}  {title}", loc="left", fontweight="bold", pad=8)
    ax.set_ylabel(r"时长变化 $\Delta J$ / s")


def feasible_xy(records: list[dict]) -> tuple[list[float], list[float]]:
    feasible = [item for item in records if item["status"] == "feasible"]
    return [float(item["value"]) for item in feasible], [float(item["change_s"]) for item in feasible]


def control_panels(axes, payload: dict) -> None:
    records = payload["control_sensitivity"]["records"]
    ax = axes[0]
    base_axis(ax, "A", "共享航向与速度的一因子扰动")
    x, y = feasible_xy(records["heading_offset_deg"])
    ax.plot(x, y, color=BLUE, marker="o", lw=1.8, label="航向偏移 / °")
    ax.set_xlabel("航向偏移 / °")
    twin = ax.twiny()
    x2, y2 = feasible_xy(records["speed_offset_mps"])
    twin.plot(x2, y2, color=GREEN, marker="s", ls="--", lw=1.6, label="速度偏移 / (m/s)")
    twin.set_xlabel("速度偏移 / (m/s)", color=GREEN)
    twin.tick_params(axis="x", colors=GREEN)
    lines = ax.lines[-1:] + twin.lines[-1:]
    ax.legend(lines, [line.get_label() for line in lines], frameon=False, loc="lower left")

    ax = axes[1]
    base_axis(ax, "B", "三枚弹时刻整体平移")
    x, y = feasible_xy(records["release_shift_s"])
    ax.plot(x, y, color=ORANGE, marker="^", lw=1.8, label="投放时刻整体平移")
    infeasible = [float(item["value"]) for item in records["release_shift_s"] if item["status"] != "feasible"]
    if infeasible:
        ax.scatter(infeasible, [0.0] * len(infeasible), marker="x", s=56, color=RED, label="违反首投放时刻下界")
    x, y = feasible_xy(records["fuse_shift_s"])
    ax.plot(x, y, color=RED, marker="D", ls="--", lw=1.6, label="引信延迟整体平移")
    ax.set_xlabel("整体平移量 / s")
    ax.legend(frameon=False, loc="lower left")


def bridge_panel(ax: plt.Axes, payload: dict, toward: str, tag: str) -> None:
    base_axis(ax, tag, f"单弹有效初始位置沿 FY1→{toward} 位移")
    colors = [BLUE, GREEN, RED]
    markers = ["o", "s", "^"]
    linestyles = ["-", "--", "-."]
    records = [item for item in payload["q4_bridge_sensitivity"]["records"] if item["direction_toward"] == toward]
    for item, color, marker, linestyle in zip(records, colors, markers, linestyles):
        ax.plot(
            [float(point["distance_m"]) for point in item["scenarios"]],
            [float(point["change_s"]) for point in item["scenarios"]],
            color=color, marker=marker, ls=linestyle, lw=1.7,
            label=f"第 {item['bomb']} 枚弹",
        )
    ax.set_xlabel(f"沿 FY1→{toward} 的位移 / m")
    ax.legend(frameon=False, ncol=3, loc="lower center")


def run(input_path: Path, output_dir: Path) -> None:
    setup_style()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if payload.get("status") != "pass":
        raise RuntimeError("Q3_E4_RESULT_NOT_PASS")
    fig, axes = plt.subplots(2, 2, figsize=(12.2, 8.2), constrained_layout=True)
    control_panels(axes[0], payload)
    bridge_panel(axes[1, 0], payload, "FY2", "C")
    bridge_panel(axes[1, 1], payload, "FY3", "D")
    fig.suptitle("Q3 固定方案局部灵敏度与 Q4 方向结构探针", fontsize=15, fontweight="bold")
    fig.text(0.5, -0.015, "注：C、D 中的位移故意放松 Q3 同平台约束，仅作结构诊断，不是 Q4 可行方案。", ha="center", color=GRAY)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = output_dir / "fig_q3_sensitivity_q4_bridge"
    fig.savefig(stem.with_suffix(".png"), dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(stem.with_suffix(".svg"), bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(json.dumps({"status": "pass", "png": str(stem.with_suffix('.png')), "svg": str(stem.with_suffix('.svg'))}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=ROOT / "docs/q3_e4_sensitivity_results.json")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs/fig")
    args = parser.parse_args()
    run(args.input, args.output_dir)


if __name__ == "__main__":
    main()
