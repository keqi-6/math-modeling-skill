#!/usr/bin/env python3
"""Render the Q2 event sequence as a clean pseudo-3D storyboard animation.

The composition follows a fixed explanatory camera: the missile, smoke cloud
and true target lie on the central horizontal sight axis; the false target is
near the image centre with a slight offset; FY1 remains above the sight axis.
Formal Q2 event times drive the animation, while longitudinal distances and
object sizes are deliberately compressed/enlarged for legibility.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, Polygon, Rectangle


ROOT = Path(__file__).resolve().parents[2]

INK = "#37444A"
BLUE = "#246B86"
LIGHT_BLUE = "#D6E8EE"
GREEN = "#326B51"
LIGHT_GREEN = "#BFD6C5"
RED = "#91332D"
ORANGE = "#D27B24"
GRAY = "#7A858B"
LIGHT_GRAY = "#E7ECEE"


def setup_style() -> None:
    font_path = Path("/mnt/c/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
    else:
        font_name = "DejaVu Sans"
    plt.rcParams.update({"font.family": font_name, "axes.unicode_minus": False, "font.size": 11})


def load_result() -> dict:
    return json.loads((ROOT / "docs" / "q2_result.json").read_text(encoding="utf-8"))


def lerp(a: float, b: float, s: float) -> float:
    return (1.0 - s) * a + s * b


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def add_holds(base: np.ndarray, events: list[float], repeats: int = 5) -> np.ndarray:
    ordered = np.unique(np.concatenate((base, np.asarray(events, dtype=float))))
    frames: list[float] = []
    for value in ordered:
        frames.append(float(value))
        if any(abs(float(value) - event) <= 2e-8 for event in events):
            frames.extend([float(value)] * repeats)
    return np.asarray(frames)


def arrow(ax: plt.Axes, start, end, color=INK, lw=1.7, alpha=1.0, zorder=5) -> None:
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle="-|>", mutation_scale=13, color=color, lw=lw, alpha=alpha, zorder=zorder))


def draw_target(ax: plt.Axes) -> None:
    x, bottom, width, height, ellipse_h = 10.45, 2.03, 1.02, 2.28, 0.34
    ax.add_patch(Rectangle((x - width / 2, bottom), width, height, fc="#88A991", ec=GREEN, lw=1.8, alpha=0.72, zorder=6))
    ax.add_patch(Ellipse((x, bottom), width, ellipse_h, fc="#7E9F87", ec=GREEN, lw=1.8, alpha=0.88, zorder=7))
    ax.add_patch(Ellipse((x, bottom + height), width, ellipse_h, fc="#9BB7A2", ec=GREEN, lw=1.8, alpha=0.95, zorder=8))
    ax.text(x, bottom + height + 0.48, "真目标", ha="center", color=GREEN, fontsize=12.5)


def draw_missile(ax: plt.Axes, x: float, y: float) -> None:
    body = np.array(
        [
            [x - 0.30, y + 0.12],
            [x + 0.38, y + 0.07],
            [x + 0.60, y],
            [x + 0.38, y - 0.07],
            [x - 0.30, y - 0.12],
            [x - 0.50, y - 0.31],
            [x - 0.43, y - 0.05],
            [x - 0.58, y + 0.20],
            [x - 0.30, y + 0.12],
        ]
    )
    ax.add_patch(Polygon(body, closed=True, fc="#A94841", ec="#6F2521", lw=1.7, zorder=12))
    ax.plot([x - 0.25, x + 0.40], [y + 0.02, y + 0.01], color="#D27670", lw=2.0, zorder=13)
    ax.text(x - 0.10, y + 0.47, "导弹 M(t)", ha="center", color=RED, fontsize=11.5)


def draw_drone(ax: plt.Axes, x: float, y: float) -> None:
    ax.plot([x - 0.34, x + 0.34], [y, y], color=BLUE, lw=2.2, zorder=13)
    ax.plot([x, x], [y - 0.18, y + 0.18], color=BLUE, lw=2.0, zorder=13)
    ax.add_patch(Ellipse((x, y), 0.34, 0.18, fc=BLUE, ec="#164A5C", lw=1.3, zorder=14))
    for dx, dy in ((-0.34, 0.0), (0.34, 0.0), (0.0, -0.18), (0.0, 0.18)):
        ax.add_patch(Ellipse((x + dx, y + dy), 0.28, 0.10, fc="white", ec=BLUE, lw=1.3, zorder=14))
    ax.text(x, y + 0.40, "FY1", ha="center", color=BLUE, fontsize=11.5)


def draw_smoke(ax: plt.Axes, x: float, y: float, active: bool) -> None:
    edge = GREEN if active else ORANGE
    fill = LIGHT_GREEN if active else "#F2D2A8"
    radius = 0.78
    ax.add_patch(Circle((x, y), radius, fc=fill, ec=edge, lw=2.0, alpha=0.86, zorder=10))
    ax.add_patch(Ellipse((x, y), 2 * radius, 0.48, fc="none", ec=edge, lw=1.0, alpha=0.65, zorder=11))
    ax.add_patch(Ellipse((x, y), 0.42, 2 * radius, fc="none", ec=edge, lw=0.9, ls="--", alpha=0.55, zorder=11))
    ax.scatter([x], [y], s=22, color=edge, zorder=12)
    ax.text(x, y - 1.05, "烟幕球 C(t)", ha="center", color=edge, fontsize=11.5)


def smoke_visual_position(t: float, te: float, entry: float, midpoint: float, exit_time: float) -> tuple[float, float]:
    axis_y = 3.20
    x = 5.05 + 0.17 * max(0.0, t - te)
    if t <= entry:
        s = clamp01((t - te) / max(entry - te, 1e-9))
        offset = lerp(0.62, 0.32, s)
    elif t <= midpoint:
        s = clamp01((t - entry) / max(midpoint - entry, 1e-9))
        offset = lerp(0.32, 0.0, s)
    elif t <= exit_time:
        s = clamp01((t - midpoint) / max(exit_time - midpoint, 1e-9))
        offset = lerp(0.0, -0.32, s)
    else:
        offset = -0.32 - 0.18 * (t - exit_time)
    return x, axis_y + offset


def drone_position(t: float) -> tuple[float, float]:
    return 4.62 + 0.39 * t, 4.95 + 0.025 * t


def status_text(t: float, release: float, te: float, entry: float, exit_time: float) -> tuple[str, str]:
    if abs(t - release) <= 2e-8:
        return "烟幕弹投放，FY1 继续飞行", ORANGE
    if abs(t - te) <= 2e-8:
        return "烟幕弹起爆", ORANGE
    if abs(t - entry) <= 2e-8:
        return "进入完整遮蔽边界", GREEN
    if abs(t - exit_time) <= 2e-8:
        return "退出完整遮蔽边界", GREEN
    if t < release:
        return "FY1 携弹飞行", BLUE
    if t < te:
        return "烟幕弹脱离 FY1 并下落", ORANGE
    if entry < t < exit_time:
        return "烟幕完整截断目标视线锥", GREEN
    if t < entry:
        return "烟幕已形成，尚未完整遮蔽", ORANGE
    return "烟幕退出完整遮蔽位置", RED


def draw_frame(ax: plt.Axes, t: float, result: dict) -> None:
    ax.clear()
    ax.set_xlim(0.0, 12.0)
    ax.set_ylim(0.35, 6.25)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    decision = result["formal_best"]["decision"]
    release = float(decision["release_time_s"])
    te = float(decision["explosion_time_s"])
    entry, exit_time = (float(value) for value in result["formal_best"]["precise"]["intervals_s"][0])
    midpoint = 0.5 * (entry + exit_time)
    active = entry - 2e-9 <= t <= exit_time + 2e-9
    axis_y = 3.20

    # Screen-centred fake target and the central missile--smoke--target line.
    ax.plot([0.60, 11.40], [axis_y, axis_y], color="#AAB4B9", lw=1.0, ls="--", zorder=1)
    ax.scatter([6.00], [axis_y - 0.17], marker="x", s=55, color=INK, zorder=5)
    ax.plot([6.00, 6.00], [axis_y - 0.13, axis_y], color=GRAY, lw=0.9, ls=":", zorder=4)
    ax.annotate(
        "假目标 O\n（镜头瞄准参考）",
        xy=(6.00, axis_y - 0.17),
        xytext=(6.72, 1.18),
        ha="center",
        va="center",
        color=INK,
        fontsize=9.5,
        arrowprops=dict(arrowstyle="->", color=GRAY, lw=0.9),
        zorder=17,
    )

    missile_x = 1.08 + 0.15 * t
    cone_apex = (missile_x + 0.56, axis_y)
    top = (10.45, 4.48)
    bottom = (10.45, 1.88)
    centre = (10.45, axis_y)
    cone_color = GREEN if active else "#5E737D"
    fill = LIGHT_GREEN if active else LIGHT_BLUE
    ax.add_patch(Polygon([cone_apex, top, bottom], closed=True, fc=fill, ec="none", alpha=0.24, zorder=2))
    ax.plot([cone_apex[0], top[0]], [cone_apex[1], top[1]], color=cone_color, lw=1.7, zorder=3)
    ax.plot([cone_apex[0], bottom[0]], [cone_apex[1], bottom[1]], color=cone_color, lw=1.7, zorder=3)
    ax.plot([cone_apex[0], centre[0]], [cone_apex[1], centre[1]], color=cone_color, lw=1.4, zorder=3)
    ax.plot([cone_apex[0], 10.45], [cone_apex[1], 3.88], color=cone_color, lw=1.0, ls="--", alpha=0.75, zorder=3)
    ax.plot([cone_apex[0], 10.45], [cone_apex[1], 2.50], color=cone_color, lw=1.0, ls="--", alpha=0.75, zorder=3)
    arrow(ax, (10.45, axis_y), (11.55, axis_y), color=cone_color, lw=1.3, alpha=0.75, zorder=3)

    draw_target(ax)
    draw_missile(ax, missile_x, axis_y)

    # UAV path and current FY1 position.
    path_t = np.linspace(0.0, 6.35, 80)
    path = np.asarray([drone_position(value) for value in path_t])
    ax.plot(path[:, 0], path[:, 1], color=BLUE, lw=1.2, ls="--", alpha=0.38, zorder=5)
    dx, dy = drone_position(t)
    draw_drone(ax, dx, dy)

    release_x, release_y = drone_position(release)
    smoke_x, smoke_y = smoke_visual_position(max(t, te), te, entry, midpoint, exit_time)
    explosion_x, explosion_y = smoke_visual_position(te, te, entry, midpoint, exit_time)
    ax.scatter([release_x], [release_y], s=34, marker="D", facecolor="white", edgecolor=ORANGE, lw=1.4, zorder=8)

    if t < release:
        ax.scatter([dx], [dy - 0.18], s=34, color=ORANGE, zorder=15)
    elif t < te:
        s = clamp01((t - release) / (te - release))
        bomb_x = lerp(release_x, explosion_x, s)
        bomb_y = lerp(release_y - 0.18, explosion_y, s) - 0.42 * s * (1.0 - s)
        curve_s = np.linspace(0.0, s, 45)
        curve_x = [lerp(release_x, explosion_x, value) for value in curve_s]
        curve_y = [lerp(release_y - 0.18, explosion_y, value) - 0.42 * value * (1.0 - value) for value in curve_s]
        ax.plot(curve_x, curve_y, color=ORANGE, lw=2.0, zorder=8)
        ax.scatter([bomb_x], [bomb_y], s=42, color=ORANGE, zorder=15)
    else:
        if t <= te + 0.18:
            ax.scatter([explosion_x], [explosion_y], s=135, marker="*", color=ORANGE, edgecolor=RED, zorder=16)
            ax.text(explosion_x + 0.18, explosion_y + 0.55, "E 起爆", color=RED, fontsize=10.8)
        draw_smoke(ax, smoke_x, smoke_y, active)

    if t <= release + 0.18:
        ax.text(release_x - 0.48, release_y - 0.42, "R 投放", color=ORANGE, fontsize=10.5)

    label, color = status_text(t, release, te, entry, exit_time)
    ax.text(0.025, 0.955, f"t = {t:.3f} s", transform=ax.transAxes, va="top", color=INK, fontsize=11.5)
    ax.text(0.025, 0.875, label, transform=ax.transAxes, va="top", color=color, fontsize=11.5, bbox=dict(boxstyle="round,pad=0.30", fc="white", ec=color))
    ax.text(0.50, 0.985, "Q2 无人机投爆与烟幕遮蔽过程", transform=ax.transAxes, ha="center", va="top", fontsize=13)
    ax.text(0.985, 0.025, "统一伪三维示意（不按比例）：事件时刻取自 Q2 正式结果，纵深和局部运动作可视化压缩/放大", transform=ax.transAxes, ha="right", color=GRAY, fontsize=8.5)


def save_still(t: float, stem: str, result: dict) -> None:
    fig, ax = plt.subplots(figsize=(11.2, 6.3))
    draw_frame(ax, t, result)
    fig.savefig(ROOT / "docs" / "fig" / f"{stem}.png", dpi=220, facecolor="white")
    plt.close(fig)


def save_gif(times: np.ndarray, result: dict) -> None:
    fig, ax = plt.subplots(figsize=(11.2, 6.3))

    def update(index: int):
        draw_frame(ax, float(times[index]), result)
        return []

    movie = animation.FuncAnimation(fig, update, frames=len(times), interval=1000 / 12, blit=False)
    movie.save(ROOT / "docs" / "fig" / "q2_pseudo3d_los_cone.gif", writer=animation.PillowWriter(fps=12), dpi=105)
    plt.close(fig)


def run() -> None:
    setup_style()
    result = load_result()
    decision = result["formal_best"]["decision"]
    release = float(decision["release_time_s"])
    explosion = float(decision["explosion_time_s"])
    entry, exit_time = (float(value) for value in result["formal_best"]["precise"]["intervals_s"][0])
    midpoint = 0.5 * (entry + exit_time)
    events = [release, explosion, entry, midpoint, exit_time]
    times = add_holds(np.linspace(0.0, 6.35, 68), events)
    save_gif(times, result)
    for value, stem in (
        (release, "fig_q2_pseudo3d_release"),
        (explosion, "fig_q2_pseudo3d_explosion"),
        (entry, "fig_q2_pseudo3d_entry"),
        (midpoint, "fig_q2_pseudo3d_mid"),
        (exit_time, "fig_q2_pseudo3d_exit"),
    ):
        save_still(value, stem, result)
    print(json.dumps({"status": "ok", "frames_requested": len(times), "events_s": events}, ensure_ascii=False))


if __name__ == "__main__":
    run()
