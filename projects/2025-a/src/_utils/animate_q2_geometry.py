#!/usr/bin/env python3
"""Render Q2 geometry animations and event-keyed still frames.

All motion and event times are read from the frozen Q2 result.  The global
view uses true trajectory coordinates but enlarges point markers for
visibility.  The local view is a missile-centred angular projection and is
intended to explain the complete-cylinder occlusion mechanism.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.animation as animation
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Polygon


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
import model as q1  # noqa: E402


INK = "#263238"
BLUE = "#2878B5"
LIGHT_BLUE = "#D9EEF6"
GREEN = "#3A9D5D"
LIGHT_GREEN = "#CBE8D3"
RED = "#C84545"
ORANGE = "#E58A2B"
GRAY = "#75808A"
LIGHT_GRAY = "#E7ECEF"


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
            "axes.unicode_minus": False,
            "font.size": 10.5,
            "axes.edgecolor": INK,
            "axes.labelcolor": INK,
            "xtick.color": INK,
            "ytick.color": INK,
        }
    )


def load_case() -> tuple[dict, q1.Q1Parameters]:
    payload = json.loads((ROOT / "docs" / "q2_result.json").read_text(encoding="utf-8"))
    decision = payload["formal_best"]["decision"]
    base = q1.default_parameters()
    params = replace(
        base,
        uav_speed=float(decision["speed_mps"]),
        uav_direction=np.asarray(decision["heading_unit"], dtype=float),
        release_time=float(decision["release_time_s"]),
        fuse_delay=float(decision["fuse_delay_s"]),
    )
    return payload, params


def uav_position(t: float, p: q1.Q1Parameters) -> np.ndarray:
    return p.uav_initial + p.uav_speed * float(t) * p.uav_direction


def bomb_position(t: float, p: q1.Q1Parameters) -> np.ndarray:
    age = float(t) - p.release_time
    return (
        p.uav_initial
        + p.uav_speed * float(t) * p.uav_direction
        - np.array([0.0, 0.0, 0.5 * p.gravity * age**2])
    )


def is_covered(t: float, interval: list[float], tolerance: float = 2e-9) -> bool:
    return interval[0] - tolerance <= float(t) <= interval[1] + tolerance


def status_text(t: float, p: q1.Q1Parameters, interval: list[float]) -> tuple[str, str]:
    te = p.release_time + p.fuse_delay
    if abs(t - interval[0]) <= 2e-8:
        return "进入完整遮蔽边界", GREEN
    if abs(t - interval[1]) <= 2e-8:
        return "退出完整遮蔽边界", GREEN
    if t < p.release_time:
        return "无人机飞行，尚未投放", BLUE
    if t < te:
        return "烟幕弹飞行", ORANGE
    if is_covered(t, interval):
        return "完整遮蔽", GREEN
    if t < interval[0]:
        return "烟幕已形成，尚未完整遮蔽", ORANGE
    return "已退出完整遮蔽", RED


def style_axis(ax: plt.Axes) -> None:
    ax.grid(True, color=LIGHT_GRAY, lw=0.8)
    for spine in ax.spines.values():
        spine.set_color(LIGHT_GRAY)


def draw_global(ax: plt.Axes, t: float, payload: dict, p: q1.Q1Parameters) -> None:
    ax.clear()
    interval = payload["formal_best"]["precise"]["intervals_s"][0]
    te = p.release_time + p.fuse_delay
    info = q1.kinematics(p)
    release = np.asarray(info["release_point_m"], dtype=float)
    explosion = np.asarray(info["explosion_point_m"], dtype=float)
    missile = q1.missile_position(t, p)
    uav = uav_position(t, p)
    target = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])

    ax.set_xlim(-0.55, 20.55)
    ax.set_ylim(-0.10, 2.25)
    ax.set_xlabel("x / km")
    ax.set_ylabel("高度 z / km")
    ax.set_title("Q2 投放—起爆—遮蔽过程（全局侧视）", pad=12, fontsize=13)
    style_axis(ax)

    # Reference trajectories in true x-z coordinates.
    missile_arrival = float(info["missile_arrival_time_s"])
    tm = np.linspace(0.0, min(7.2, missile_arrival), 160)
    mp = np.asarray([q1.missile_position(value, p) for value in tm])
    ax.plot(mp[:, 0] / 1000.0, mp[:, 2] / 1000.0, color=RED, lw=1.5, alpha=0.42, label="M1 轨迹")
    tu = np.linspace(0.0, 7.2, 120)
    up = np.asarray([uav_position(value, p) for value in tu])
    ax.plot(up[:, 0] / 1000.0, up[:, 2] / 1000.0, color=BLUE, lw=1.5, alpha=0.42, label="FY1 航迹")

    ax.scatter([target[0] / 1000.0], [target[2] / 1000.0], s=80, marker="s", color=INK, zorder=7, label="真目标")
    ax.annotate("真目标\n(y=200 m)", (0.02, 0.02), xytext=(0.8, 0.28), arrowprops=dict(arrowstyle="->", color=INK), color=INK)
    ax.scatter([missile[0] / 1000.0], [missile[2] / 1000.0], s=74, marker=">", color=RED, zorder=8)
    ax.scatter([uav[0] / 1000.0], [uav[2] / 1000.0], s=82, marker="^", color=BLUE, zorder=8)

    # Finite sight segment to target centre; two faint boundary rays show the vertical bundle.
    ax.plot([missile[0] / 1000.0, target[0] / 1000.0], [missile[2] / 1000.0, target[2] / 1000.0], color=GRAY, lw=1.1, alpha=0.70)
    ax.plot([missile[0] / 1000.0, 0.0], [missile[2] / 1000.0, 0.0], color=LIGHT_BLUE, lw=0.9)
    ax.plot([missile[0] / 1000.0, 0.0], [missile[2] / 1000.0, p.target_height / 1000.0], color=LIGHT_BLUE, lw=0.9)

    ax.scatter([release[0] / 1000.0], [release[2] / 1000.0], s=42, color=ORANGE, zorder=7)
    ax.scatter([explosion[0] / 1000.0], [explosion[2] / 1000.0], s=46, facecolor="white", edgecolor=RED, lw=1.5, zorder=7)
    ax.text(release[0] / 1000.0 - 0.10, 1.70, "投放点", color=ORANGE, ha="right")
    ax.text(explosion[0] / 1000.0 + 0.12, 1.67, "起爆点", color=RED, ha="left")

    if p.release_time <= t < te:
        tb = np.linspace(p.release_time, t, 45)
        bp = np.asarray([bomb_position(value, p) for value in tb])
        ax.plot(bp[:, 0] / 1000.0, bp[:, 2] / 1000.0, color=ORANGE, lw=2.2)
        bomb = bomb_position(t, p)
        ax.scatter([bomb[0] / 1000.0], [bomb[2] / 1000.0], s=52, color=ORANGE, marker="o", zorder=9)
    elif t >= te:
        cloud = q1.smoke_center(t, p)
        covered = is_covered(t, interval)
        cloud_color = GREEN if covered else ORANGE
        ax.scatter(
            [cloud[0] / 1000.0],
            [cloud[2] / 1000.0],
            s=330,
            color=LIGHT_GREEN if covered else "#F8D7AD",
            edgecolor=cloud_color,
            linewidth=2.0,
            alpha=0.92,
            zorder=9,
            label="烟幕球（标记放大）",
        )
        ax.plot([explosion[0] / 1000.0, cloud[0] / 1000.0], [explosion[2] / 1000.0, cloud[2] / 1000.0], color=cloud_color, lw=1.4, ls="--")

    status, color = status_text(t, p, interval)
    ax.text(0.02, 0.95, f"t = {t:.3f} s", transform=ax.transAxes, fontsize=12, color=INK, va="top")
    ax.text(0.02, 0.86, status, transform=ax.transAxes, fontsize=12, color=color, va="top", bbox=dict(boxstyle="round,pad=0.28", fc="white", ec=color))
    ax.text(0.985, 0.04, "轨迹按真实坐标绘制；物体标记为便于观察而放大", transform=ax.transAxes, ha="right", color=GRAY, fontsize=8.8)
    ax.legend(loc="upper center", bbox_to_anchor=(0.55, 0.99), ncol=4, frameon=False, fontsize=8.8)


def camera_basis(missile: np.ndarray, target_center: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    forward = target_center - missile
    forward = forward / np.linalg.norm(forward)
    up = np.array([0.0, 0.0, 1.0])
    up = up - np.dot(up, forward) * forward
    up = up / np.linalg.norm(up)
    right = np.cross(forward, up)
    right = right / np.linalg.norm(right)
    return forward, right, up


def angular_projection(
    points: np.ndarray,
    origin: np.ndarray,
    basis: tuple[np.ndarray, np.ndarray, np.ndarray],
) -> np.ndarray:
    forward, right, up = basis
    vectors = np.atleast_2d(points) - origin
    depths = vectors @ forward
    return np.column_stack((1000.0 * (vectors @ right) / depths, 1000.0 * (vectors @ up) / depths))


def convex_hull(points: np.ndarray) -> np.ndarray:
    unique = sorted({(float(x), float(y)) for x, y in np.asarray(points)})
    if len(unique) <= 2:
        return np.asarray(unique)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return np.asarray(lower[:-1] + upper[:-1])


def target_silhouette(t: float, p: q1.Q1Parameters) -> tuple[np.ndarray, np.ndarray, tuple[np.ndarray, np.ndarray, np.ndarray]]:
    missile = q1.missile_position(t, p)
    center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    basis = camera_basis(missile, center)
    theta = np.linspace(0.0, 2.0 * math.pi, 181)
    bottom = q1.target_circle(theta, p.target_base_center[2], p)
    top = q1.target_circle(theta, p.target_base_center[2] + p.target_height, p)
    projected = angular_projection(np.vstack((bottom, top)), missile, basis)
    return convex_hull(projected), missile, basis


def screen_margin(t: float, p: q1.Q1Parameters, n_theta: int = 720) -> float:
    theta = np.arange(n_theta, dtype=float) * (2.0 * math.pi / n_theta)
    bottom, _ = q1.circle_margins(theta, t, p.target_base_center[2], p)
    top, _ = q1.circle_margins(theta, t, p.target_base_center[2] + p.target_height, p)
    return float(max(np.max(bottom), np.max(top)))


def draw_local(ax: plt.Axes, t: float, payload: dict, p: q1.Q1Parameters) -> None:
    ax.clear()
    interval = payload["formal_best"]["precise"]["intervals_s"][0]
    hull, missile, basis = target_silhouette(t, p)
    cloud = q1.smoke_center(t, p)
    cloud_uv = angular_projection(cloud, missile, basis)[0]
    distance = float(np.linalg.norm(cloud - missile))
    angular_radius = 1000.0 * p.smoke_radius / math.sqrt(max(distance**2 - p.smoke_radius**2, 1e-12))
    covered = is_covered(t, interval)
    cloud_color = GREEN if covered else ORANGE

    ax.set_xlim(-13.0, 55.0)
    ax.set_ylim(-55.0, 15.0)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("水平角偏差 ξ / mrad")
    ax.set_ylabel("竖直角偏差 η / mrad")
    ax.set_title("导弹视角下的烟幕—完整圆柱投影", pad=12, fontsize=13)
    style_axis(ax)
    ax.axhline(0.0, color=LIGHT_GRAY, lw=1.0)
    ax.axvline(0.0, color=LIGHT_GRAY, lw=1.0)

    ax.add_patch(Polygon(hull, closed=True, fc=LIGHT_BLUE, ec=BLUE, lw=2.0, label="真目标圆柱投影", zorder=5))
    ax.add_patch(
        Circle(
            cloud_uv,
            angular_radius,
            fc=LIGHT_GREEN if covered else "#F8D7AD",
            ec=cloud_color,
            lw=2.2,
            alpha=0.78,
            label="烟幕球视角范围",
            zorder=3,
        )
    )
    ax.scatter([cloud_uv[0]], [cloud_uv[1]], s=28, color=cloud_color, zorder=7)
    ax.scatter([0.0], [0.0], s=24, color=INK, marker="+", zorder=8)

    margin = screen_margin(t, p)
    if abs(margin) < 5e-4:
        margin = 0.0
    if abs(t - interval[0]) <= 2e-8:
        status = "进入完整遮蔽边界"
    elif abs(t - interval[1]) <= 2e-8:
        status = "退出完整遮蔽边界"
    else:
        status = "完整遮蔽" if covered else ("尚未完整遮蔽" if t < interval[0] else "已退出完整遮蔽")
    ax.text(0.02, 0.95, f"t = {t:.6f} s", transform=ax.transAxes, fontsize=11.5, color=INK, va="top")
    ax.text(0.02, 0.87, f"{status}　最坏余量 ≈ {margin:.3f} m", transform=ax.transAxes, fontsize=11, color=cloud_color, va="top", bbox=dict(boxstyle="round,pad=0.28", fc="white", ec=cloud_color))
    ax.text(0.985, 0.025, "角度投影示意；遮蔽状态由完整圆柱有限视线段判据给出", transform=ax.transAxes, ha="right", color=GRAY, fontsize=8.7)
    ax.legend(loc="lower left", frameon=False)


def save_still(draw, t: float, stem: str, payload: dict, p: q1.Q1Parameters, figsize=(9.6, 5.4)) -> None:
    fig, ax = plt.subplots(figsize=figsize)
    draw(ax, t, payload, p)
    fig.tight_layout()
    fig.savefig(ROOT / "docs" / "fig" / f"{stem}.png", dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def save_gif(draw, times: np.ndarray, stem: str, payload: dict, p: q1.Q1Parameters, fps: int, figsize=(9.6, 5.4)) -> None:
    fig, ax = plt.subplots(figsize=figsize)

    def update(index: int):
        draw(ax, float(times[index]), payload, p)
        return []

    movie = animation.FuncAnimation(fig, update, frames=len(times), interval=1000 / fps, blit=False)
    movie.save(ROOT / "docs" / "fig" / f"{stem}.gif", writer=animation.PillowWriter(fps=fps), dpi=110)
    plt.close(fig)


def add_event_holds(base: np.ndarray, events: list[float], repeats: int = 5) -> np.ndarray:
    ordered = np.unique(np.concatenate((np.asarray(base, dtype=float), np.asarray(events, dtype=float))))
    frames: list[float] = []
    for value in ordered:
        frames.append(float(value))
        if any(abs(float(value) - event) <= 2e-8 for event in events):
            frames.extend([float(value)] * repeats)
    return np.asarray(frames, dtype=float)


def run() -> None:
    setup_style()
    out = ROOT / "docs" / "fig"
    out.mkdir(parents=True, exist_ok=True)
    payload, p = load_case()
    precise = payload["formal_best"]["precise"]
    entry, exit_time = (float(value) for value in precise["intervals_s"][0])
    midpoint = 0.5 * (entry + exit_time)
    release = float(p.release_time)
    explosion = float(p.release_time + p.fuse_delay)

    global_times = add_event_holds(np.linspace(0.0, 7.0, 72), [release, explosion, entry, midpoint, exit_time])
    local_times = add_event_holds(np.linspace(explosion, exit_time, 68), [entry, midpoint, exit_time])
    save_gif(draw_global, global_times, "q2_geometry_global", payload, p, fps=12)
    save_gif(draw_local, local_times, "q2_los_projection", payload, p, fps=12, figsize=(7.4, 7.0))

    save_still(draw_global, release, "fig_q2_anim_release", payload, p)
    save_still(draw_global, explosion, "fig_q2_anim_explosion", payload, p)
    save_still(draw_local, entry, "fig_q2_anim_cover_entry", payload, p, figsize=(7.4, 7.0))
    save_still(draw_local, midpoint, "fig_q2_anim_cover_mid", payload, p, figsize=(7.4, 7.0))
    save_still(draw_local, exit_time, "fig_q2_anim_cover_exit", payload, p, figsize=(7.4, 7.0))

    print(
        json.dumps(
            {
                "status": "ok",
                "global_frames": len(global_times),
                "local_frames": len(local_times),
                "event_times_s": {
                    "release": release,
                    "explosion": explosion,
                    "cover_entry": entry,
                    "cover_midpoint": midpoint,
                    "cover_exit": exit_time,
                },
            },
            ensure_ascii=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    run()


if __name__ == "__main__":
    main()
