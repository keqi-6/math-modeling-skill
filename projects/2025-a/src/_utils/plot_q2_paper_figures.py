#!/usr/bin/env python3
"""Render the two existing Q2 figures in a sparse paper style."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, Rectangle


ROOT = Path(__file__).resolve().parents[2]
RESULT_PATH = ROOT / "docs" / "q2_result.json"

INK = "#263238"
GRAY = "#7A858B"
BLUE = "#315F78"
PALE_BLUE = "#E2EEF2"
GREEN = "#3E7259"
PALE_GREEN = "#E1ECE5"
RED = "#A64B43"
ORANGE = "#C88432"


def setup_style() -> None:
    font_path = Path("/mnt/c/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
    else:
        font_name = "DejaVu Sans"
    plt.rcParams.update(
        {
            "font.family": font_name,
            "font.size": 10.5,
            "axes.unicode_minus": False,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
            "svg.fonttype": "none",
        }
    )


def save(fig: plt.Figure, output_dir: Path, stem: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_dir / f"{stem}.png", dpi=240, bbox_inches="tight", facecolor="white")
    fig.savefig(output_dir / f"{stem}.svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)


def arrow(ax: plt.Axes, start, end, *, color=INK, lw=1.35, scale=11, style="-|>", **kwargs) -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle=style,
            mutation_scale=scale,
            linewidth=lw,
            color=color,
            shrinkA=0,
            shrinkB=0,
            **kwargs,
        )
    )


def cylinder(ax: plt.Axes, centre, width, height) -> None:
    x, y = centre
    cap = 0.24 * width
    ax.add_patch(Rectangle((x - width / 2, y - height / 2), width, height, fc=PALE_BLUE, ec="none", alpha=0.72, zorder=4))
    ax.plot([x - width / 2, x - width / 2], [y - height / 2, y + height / 2], color=BLUE, lw=1.25, zorder=5)
    ax.plot([x + width / 2, x + width / 2], [y - height / 2, y + height / 2], color=BLUE, lw=1.25, zorder=5)
    ax.add_patch(Ellipse((x, y + height / 2), width, cap, fc="white", ec=BLUE, lw=1.25, zorder=6))
    ax.add_patch(Ellipse((x, y - height / 2), width, cap, fc=PALE_BLUE, ec=BLUE, lw=1.25, zorder=6))


def draw_decision_geometry(output_dir: Path) -> None:
    """Show only how the four decisions propagate into the LOS geometry."""
    fig, ax = plt.subplots(figsize=(9.4, 4.7))
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.0, 5.2)
    ax.axis("off")

    # UAV state and release–detonation chain.
    ax.plot([3.25, 9.35], [4.42, 4.42], color=INK, lw=1.10)
    ax.scatter([8.95], [4.42], marker="D", s=38, facecolor="white", edgecolor=BLUE, linewidth=1.3, zorder=7)
    arrow(ax, (8.60, 4.42), (7.80, 4.42), color=BLUE, lw=1.45)
    ax.text(8.98, 4.82, r"$U_0$", ha="center", color=BLUE, fontsize=12)
    ax.text(8.05, 4.80, r"$(\alpha,v)$", ha="center", color=BLUE)

    release = np.array([6.75, 4.42])
    explosion = np.array([4.85, 2.88])
    cloud = np.array([4.85, 1.42])
    ax.scatter(*release, s=46, color=ORANGE, zorder=7)
    ax.text(release[0], 4.82, r"$R(\tau)$", ha="center", color=ORANGE, fontsize=12)

    s = np.linspace(0.0, 1.0, 120)
    x = release[0] + (explosion[0] - release[0]) * s
    y = release[1] - 0.12 * s - 1.42 * s**2
    ax.plot(x, y, color=ORANGE, lw=1.65)
    arrow(ax, (x[54], y[54]), (x[66], y[66]), color=ORANGE, lw=1.20)
    ax.text(5.80, 3.67, r"$\delta$", color=ORANGE, fontsize=12)
    ax.scatter(*explosion, s=48, color=RED, zorder=7)
    ax.add_patch(Circle(tuple(explosion), 0.13, fill=False, ec=RED, lw=1.0))
    ax.text(explosion[0] - 0.25, 3.18, r"$E(\tau+\delta)$", ha="right", color=RED, fontsize=12)

    ax.plot([explosion[0], cloud[0]], [explosion[1] - 0.15, cloud[1] + 0.50], color=GREEN, lw=1.0, ls=(0, (4, 3)))
    arrow(ax, (4.85, 2.48), (4.85, 2.02), color=GREEN, lw=1.20)
    ax.text(5.08, 2.22, r"$v_s$", color=GREEN)
    ax.add_patch(Circle(tuple(cloud), 0.54, fc=PALE_GREEN, ec=GREEN, lw=1.40, alpha=0.94, zorder=5))
    ax.scatter(*cloud, s=17, color=GREEN, zorder=7)
    ax.text(cloud[0] + 0.72, cloud[1] + 0.53, r"$C(t;x)$", ha="left", va="center", color=GREEN, fontsize=12)

    # The lower construction shows the quantity ultimately affected by the
    # four decisions: interception of all target-bound finite sight lines.
    missile = np.array([9.15, 0.90])
    target = np.array([1.25, 1.55])
    fake = np.array([0.85, 0.48])
    cylinder(ax, target, 0.72, 1.22)
    ax.text(target[0], 2.35, r"$T$", ha="center", color=BLUE, fontsize=12)
    ax.scatter(*fake, s=24, color=INK, zorder=7)
    ax.text(fake[0] - 0.02, 0.18, r"$O$", ha="center", fontsize=12)
    ax.plot([missile[0], fake[0]], [missile[1], fake[1]], color=RED, lw=1.05, ls=(0, (5, 3)), zorder=2)
    ax.plot([missile[0], target[0] - 0.02], [missile[1], target[1] - 0.67], color=INK, lw=0.95, alpha=0.84, zorder=2)
    ax.plot([missile[0], target[0] + 0.05], [missile[1], target[1] + 0.67], color=INK, lw=0.95, alpha=0.84, zorder=2)
    ax.scatter(*missile, marker="<", s=68, color=RED, zorder=8)
    arrow(ax, (8.82, 0.88), (8.08, 0.84), color=RED, lw=1.40)
    ax.text(missile[0], 0.44, r"$M(t)$", ha="center", color=RED, fontsize=12)
    save(fig, output_dir, "fig_q2_decision_geometry")


def draw_optimized_timeline(payload: dict, output_dir: Path) -> None:
    decision = payload["formal_best"]["decision"]
    precise = payload["formal_best"]["precise"]
    release = float(decision["release_time_s"])
    explosion = float(decision["explosion_time_s"])
    entry, exit_time = (float(value) for value in precise["intervals_s"][0])
    active_end = float(decision["active_window_s"][1])
    possible_end = float(precise["geometry_pruning"]["possible_window_s"][1])

    break_time = 6.25
    break_x = 6.25
    end_x = 9.35

    def tx(value: float) -> float:
        if value <= break_time:
            return value
        return break_x + (value - break_time) * (end_x - break_x) / (active_end - break_time)

    fig, ax = plt.subplots(figsize=(9.4, 3.0))
    ax.set_xlim(-0.30, end_x + 0.72)
    ax.set_ylim(-1.34, 1.46)
    ax.axis("off")
    ax.plot([0.0, end_x + 0.33], [0.0, 0.0], color=INK, lw=1.30)
    arrow(ax, (end_x + 0.04, 0.0), (end_x + 0.51, 0.0), color=INK, lw=1.30)
    ax.fill_between([tx(explosion), tx(active_end)], -0.14, 0.14, color=PALE_GREEN, alpha=0.95)
    ax.fill_between([tx(explosion), tx(possible_end)], -0.19, 0.19, color=PALE_BLUE, alpha=0.96)
    ax.fill_between(
        [tx(possible_end), tx(active_end)], -0.14, 0.14,
        facecolor="#EDF1F2", edgecolor=GRAY, hatch="////", linewidth=0.0, alpha=0.92,
    )
    ax.fill_between([tx(entry), tx(exit_time)], -0.26, 0.26, color=GREEN, alpha=0.85)

    events = [
        (0.0, "任务开始", INK, 0.62),
        (release, f"投放\n{release:.3f} s", ORANGE, -0.78),
        (explosion, f"起爆\n{explosion:.3f} s", RED, 0.80),
        (entry, f"进入遮蔽\n{entry:.3f} s", GREEN, -0.91),
        (exit_time, f"退出遮蔽\n{exit_time:.3f} s", GREEN, 0.83),
        (active_end, f"烟幕失效\n{active_end:.3f} s", GRAY, -0.78),
    ]
    for value, label, color, ypos in events:
        x = tx(value)
        ax.plot([x, x], [-0.20, 0.20], color=color, lw=1.05)
        ax.scatter([x], [0], s=24, color=color, zorder=7)
        ax.text(x, ypos, label, ha="center", va="center", color=color, fontsize=8.9)

    ax.plot([tx(possible_end), tx(possible_end)], [-0.34, 0.34], color=BLUE, lw=1.0, ls=(0, (3, 2)))

    for dx in (-0.055, 0.055):
        ax.plot([break_x + dx - 0.055, break_x + dx + 0.025], [-0.09, 0.09], color="white", lw=3.8, zorder=8)
        ax.plot([break_x + dx - 0.055, break_x + dx + 0.025], [-0.09, 0.09], color=INK, lw=0.9, zorder=9)
    ax.text((tx(possible_end) + tx(active_end)) / 2, 0.40, "必要条件排除", color=GRAY, ha="center", fontsize=8.8)
    ax.text((tx(explosion) + tx(possible_end)) / 2, 0.40, "几何必要可行窗", color=BLUE, ha="center", fontsize=9.0)
    ax.text((tx(entry) + tx(exit_time)) / 2, -1.20, rf"$T_{{\rm eff}}={precise['effective_duration_s']:.6f}\,\mathrm{{s}}$", color=GREEN, ha="center", fontsize=10.2)
    ax.text(end_x + 0.53, -0.18, r"$t$/s", color=INK)
    save(fig, output_dir, "fig_q2_optimized_timeline")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "fig")
    args = parser.parse_args()
    setup_style()
    payload = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    draw_decision_geometry(args.output_dir)
    draw_optimized_timeline(payload, args.output_dir)
    print(json.dumps({"status": "ok", "figure_count": 2, "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
