#!/usr/bin/env python3
"""Render the Q1--Q5 service chain and the current Q3 schedule."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "docs" / "fig"
RESULT = ROOT / "docs" / "q3_result.json"
INK = "#263238"
BLUE = "#315F78"
PALE_BLUE = "#E2EEF2"
GREEN = "#3E7259"
PALE_GREEN = "#E1ECE5"
ORANGE = "#C88432"
RED = "#A64B43"
GRAY = "#7A858B"


def setup_style() -> None:
    font_path = Path("/mnt/c/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
    else:
        font_name = "DejaVu Sans"
    plt.rcParams.update({"font.family": font_name, "font.size": 10.5,
                         "axes.unicode_minus": False, "svg.fonttype": "none"})


def save(fig: plt.Figure, stem: str) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG_DIR / f"{stem}.png", dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(FIG_DIR / f"{stem}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def arrow(ax: plt.Axes, start, end, color=INK, lw=1.2) -> None:
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=12,
                                linewidth=lw, color=color, shrinkA=4, shrinkB=4))


def service_chain() -> None:
    fig, ax = plt.subplots(figsize=(11.2, 3.6))
    ax.set_xlim(0, 11.2)
    ax.set_ylim(0, 3.6)
    ax.axis("off")
    boxes = [
        (0.25, "Q1\n固定服务单元", "严格评价核"),
        (2.45, "Q2\n单服务单元", "四维优化"),
        (4.65, "Q3\n同平台三事件", "间隔调度"),
        (6.85, "Q4\n多平台单事件", "服务组合"),
        (9.05, "Q5\n多导弹多资源", "分配＋联合复算"),
    ]
    for index, (x, title, subtitle) in enumerate(boxes):
        color = GREEN if index >= 2 else BLUE
        pale = PALE_GREEN if index >= 2 else PALE_BLUE
        ax.add_patch(FancyBboxPatch((x, 1.25), 1.75, 1.15,
                                    boxstyle="round,pad=0.05,rounding_size=0.08",
                                    fc=pale, ec=color, lw=1.4))
        ax.text(x + 0.875, 1.93, title, ha="center", va="center", color=color, fontsize=11)
        ax.text(x + 0.875, 1.48, subtitle, ha="center", va="center", color=INK, fontsize=9.1)
        if index < len(boxes) - 1:
            arrow(ax, (x + 1.80, 1.82), (x + 2.18, 1.82), color=GRAY)
    ax.text(5.6, 3.16, "统一物理与严格目标", ha="center", color=INK, fontsize=12)
    ax.text(5.6, 2.78, r"$C_{ik}(t)$  ·  有限视线段  ·  完整圆柱  ·  $\Phi_j(t)=\max_P\min_k(\cdot)$  ·  连续时间集合",
            ha="center", color=INK, fontsize=10.4)
    ax.plot([0.72, 10.48], [2.58, 2.58], color=GRAY, lw=0.8)
    ax.text(5.6, 0.72, "物理可达候选 → 严格筛选 → 资源组合/调度 → 原变量精修 → 独立复核",
            ha="center", color=INK, fontsize=10.8)
    ax.text(5.6, 0.30, "各问只改变资源组织，不改变遮蔽定义", ha="center", color=GRAY, fontsize=9.6)
    save(fig, "fig_q1_q5_service_chain")


def q3_schedule(payload: dict) -> None:
    best = payload["working_best"]
    decision = best["decision"]
    diagnostics = payload["final_diagnostics"]["precise"]
    release = decision["release_times_s"]
    explosion = decision["explosion_times_s"]
    indiv = [entry["intervals_s"][0] for entry in diagnostics["individuals"]]
    joint = diagnostics["joint"]["intervals_s"][0]

    fig, (ax0, ax1) = plt.subplots(2, 1, figsize=(10.8, 5.3),
                                   gridspec_kw={"height_ratios": [1.1, 2.1]})
    fig.subplots_adjust(hspace=0.16)
    ax0.set_xlim(-0.4, 13.2)
    ax0.set_ylim(-0.15, 1.15)
    ax0.axis("off")
    ax0.plot([0, 13], [0.45, 0.45], color=INK, lw=1.15)
    arrow(ax0, (12.72, 0.45), (13.12, 0.45), color=INK)
    for k, (tr, te) in enumerate(zip(release, explosion), start=1):
        ax0.plot([tr, te], [0.45, 0.45], color=ORANGE, lw=4, alpha=0.52)
        ax0.scatter([tr], [0.45], s=36, color=ORANGE, zorder=4)
        ax0.scatter([te], [0.45], s=42, color=RED, marker="D", zorder=4)
        ax0.text(tr, 0.12, f"投{k}\n{tr:.3f}", ha="center", va="top", color=ORANGE, fontsize=8.5)
        ax0.text(te, 0.79, f"爆{k}\n{te:.3f}", ha="center", va="bottom", color=RED, fontsize=8.5)
    ax0.text(12.98, 0.18, "t/s", ha="right", color=INK)
    ax0.text(0, 1.04, "共享航迹：179.861°，138.490 m/s；相邻投放间隔 3.475 s、1.820 s",
             ha="left", color=INK, fontsize=10.2)

    ax1.set_xlim(5.35, 13.0)
    ax1.set_ylim(0.35, 4.8)
    ax1.set_xlabel("任务时刻 t / s")
    ax1.set_yticks([1, 2, 3, 4])
    ax1.set_yticklabels(["烟幕 3", "烟幕 2", "烟幕 1", "联合"])
    ax1.grid(axis="x", color="#D5DADD", lw=0.65)
    colors = [BLUE, ORANGE, GREEN]
    for row, (interval, color) in enumerate(zip(reversed(indiv), reversed(colors)), start=1):
        a, b = interval
        ax1.barh(row, b-a, left=a, height=0.38, color=color, alpha=0.82)
        ax1.text((a+b)/2, row, f"{b-a:.3f} s", ha="center", va="center", color="white", fontsize=9)
    a, b = joint
    ax1.barh(4, b-a, left=a, height=0.50, color=INK, alpha=0.88)
    ax1.text((a+b)/2, 4, f"联合 {b-a:.6f} s", ha="center", va="center", color="white", fontsize=10)
    ax1.axvline(a, color=GRAY, lw=0.8, ls=(0, (3, 3)))
    ax1.axvline(b, color=GRAY, lw=0.8, ls=(0, (3, 3)))
    ax1.text(9.18, 4.62, "三弹时间接力；纯协同时长 = 0 s", ha="center", color=INK, fontsize=10.2)
    for spine in ("top", "right", "left"):
        ax1.spines[spine].set_visible(False)
    ax1.tick_params(axis="y", length=0)
    save(fig, "fig_q3_track_schedule")


def main() -> None:
    setup_style()
    payload = json.loads(RESULT.read_text(encoding="utf-8"))
    service_chain()
    q3_schedule(payload)
    print(json.dumps({"status": "ok", "figure_count": 2, "output_dir": str(FIG_DIR)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
