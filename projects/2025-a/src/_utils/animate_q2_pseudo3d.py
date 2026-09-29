#!/usr/bin/env python3
"""Render a unified pseudo-3D Q2 animation inspired by teammate sketches.

The scene keeps a fixed camera on the missile--true-target region and shows
the missile sight cone, FY1 motion, bomb separation and explosion, and the
subsequent smoke-cloud motion.  Positions and event times come from the
frozen Q2 result; object sizes are enlarged for explanatory visibility.
"""

from __future__ import annotations

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
from matplotlib import colors as mcolors
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
import model as q1  # noqa: E402


INK = "#263238"
BLUE = "#246B86"
LIGHT_BLUE = "#9CC7D8"
GREEN = "#347A5A"
LIGHT_GREEN = "#BFDAC8"
RED = "#98342E"
ORANGE = "#D47B24"
GRAY = "#78838B"
GROUND = "#EDF1F2"


def setup_style() -> None:
    font_path = Path("/mnt/c/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
    else:
        font_name = "DejaVu Sans"
    plt.rcParams.update({"font.family": font_name, "axes.unicode_minus": False, "font.size": 10.5})


def load_case() -> tuple[dict, q1.Q1Parameters]:
    result = json.loads((ROOT / "docs" / "q2_result.json").read_text(encoding="utf-8"))
    decision = result["formal_best"]["decision"]
    base = q1.default_parameters()
    params = replace(
        base,
        uav_speed=float(decision["speed_mps"]),
        uav_direction=np.asarray(decision["heading_unit"], dtype=float),
        release_time=float(decision["release_time_s"]),
        fuse_delay=float(decision["fuse_delay_s"]),
    )
    return result, params


def km(point: np.ndarray) -> np.ndarray:
    return np.asarray(point, dtype=float) / 1000.0


def uav_position(t: float, p: q1.Q1Parameters) -> np.ndarray:
    return p.uav_initial + p.uav_speed * float(t) * p.uav_direction


def bomb_position(t: float, p: q1.Q1Parameters) -> np.ndarray:
    age = float(t) - p.release_time
    return p.uav_initial + p.uav_speed * float(t) * p.uav_direction - np.array([0.0, 0.0, 0.5 * p.gravity * age**2])


def covered(t: float, interval: list[float]) -> bool:
    return interval[0] - 2e-9 <= float(t) <= interval[1] + 2e-9


def boundary_state(t: float, interval: list[float]) -> str | None:
    if abs(float(t) - interval[0]) <= 2e-8:
        return "进入完整遮蔽边界"
    if abs(float(t) - interval[1]) <= 2e-8:
        return "退出完整遮蔽边界"
    return None


def draw_ground(ax) -> None:
    vertices = [[(-0.8, -0.8, 0.0), (20.8, -0.8, 0.0), (20.8, 1.05, 0.0), (-0.8, 1.05, 0.0)]]
    ax.add_collection3d(Poly3DCollection(vertices, facecolors=GROUND, edgecolors="none", alpha=0.34, zorder=0))


def draw_cylinder(ax, center: np.ndarray, radius: float = 0.19, height: float = 0.52) -> None:
    theta = np.linspace(0.0, 2.0 * math.pi, 36)
    z = np.linspace(0.0, height, 10)
    theta_grid, z_grid = np.meshgrid(theta, z)
    x = np.full_like(theta_grid, center[0]) + radius * np.cos(theta_grid)
    y = np.full_like(theta_grid, center[1]) + radius * np.sin(theta_grid)
    zz = center[2] + z_grid
    ax.plot_surface(x, y, zz, color="#5D8A69", alpha=0.78, linewidth=0.2, edgecolor="#456850", shade=True, zorder=5)
    ax.plot(center[0] + radius * np.cos(theta), center[1] + radius * np.sin(theta), np.full_like(theta, center[2] + height), color="#365941", lw=1.1, zorder=6)


def draw_sight_cone(ax, missile: np.ndarray, active: bool) -> None:
    # A visually enlarged elliptical base surrounds the true target.  It is a
    # schematic envelope for the family of finite missile--target sight lines.
    theta = np.linspace(0.0, 2.0 * math.pi, 28, endpoint=False)
    base = np.column_stack((np.zeros_like(theta), 0.20 + 0.45 * np.cos(theta), 0.38 + 0.38 * np.sin(theta)))
    color = GREEN if active else LIGHT_BLUE
    rgba = mcolors.to_rgba(color, 0.105 if not active else 0.13)
    faces = [[missile, base[i], base[(i + 1) % len(base)]] for i in range(len(base))]
    ax.add_collection3d(Poly3DCollection(faces, facecolors=[rgba] * len(faces), edgecolors="none", zorder=2))
    boundary_color = GREEN if active else "#6B9FB2"
    for index in (2, 7, 12, 17, 22, 27):
        point = base[index]
        ax.plot([missile[0], point[0]], [missile[1], point[1]], [missile[2], point[2]], color=boundary_color, lw=0.85, alpha=0.80, zorder=3)
    ring = np.vstack((base, base[0]))
    ax.plot(ring[:, 0], ring[:, 1], ring[:, 2], color=boundary_color, lw=1.0, alpha=0.8, zorder=3)


def draw_smoke_sphere(ax, center: np.ndarray, active: bool) -> None:
    u = np.linspace(0.0, 2.0 * math.pi, 28)
    v = np.linspace(0.0, math.pi, 18)
    radius = 0.43
    x = center[0] + radius * np.outer(np.cos(u), np.sin(v))
    y = center[1] + radius * np.outer(np.sin(u), np.sin(v))
    z = center[2] + radius * np.outer(np.ones_like(u), np.cos(v))
    color = LIGHT_GREEN if active else "#F4D3A9"
    edge = GREEN if active else ORANGE
    ax.plot_surface(x, y, z, color=color, alpha=0.48, linewidth=0.22, edgecolor=edge, shade=True, zorder=8)
    ax.plot([center[0]], [center[1]], [center[2]], marker="o", ms=3.5, color=edge, zorder=9)


def draw_drone(ax, center: np.ndarray) -> None:
    x, y, z = center
    dx, dy = 0.34, 0.16
    ax.plot([x - dx, x + dx], [y, y], [z, z], color=BLUE, lw=2.0, zorder=10)
    ax.plot([x, x], [y - dy, y + dy], [z, z], color=BLUE, lw=2.0, zorder=10)
    ax.scatter([x], [y], [z], s=52, color=BLUE, edgecolor="#174B5E", zorder=11)
    ax.scatter([x - dx, x + dx, x, x], [y, y, y - dy, y + dy], [z, z, z, z], s=23, facecolor="white", edgecolor=BLUE, zorder=11)


def draw_missile(ax, point: np.ndarray, direction: np.ndarray) -> None:
    direction = direction / np.linalg.norm(direction)
    tail = point - 0.58 * direction
    ax.plot([tail[0], point[0]], [tail[1], point[1]], [tail[2], point[2]], color=RED, lw=3.2, zorder=12)
    ax.scatter([point[0]], [point[1]], [point[2]], s=90, marker=">", color=RED, edgecolor="#68231F", zorder=13)


def status(t: float, p: q1.Q1Parameters, interval: list[float]) -> tuple[str, str]:
    boundary = boundary_state(t, interval)
    if boundary:
        return boundary, GREEN
    explosion = p.release_time + p.fuse_delay
    if t < p.release_time:
        return "FY1 携弹飞行", BLUE
    if t < explosion:
        return "烟幕弹已投放，FY1 继续飞行", ORANGE
    if covered(t, interval):
        return "烟幕完整截断目标视线锥", GREEN
    if t < interval[0]:
        return "烟幕已起爆，尚未形成完整遮蔽", ORANGE
    return "烟幕已离开完整遮蔽位置", RED


def draw_frame(ax, t: float, result: dict, p: q1.Q1Parameters) -> None:
    ax.clear()
    interval = [float(v) for v in result["formal_best"]["precise"]["intervals_s"][0]]
    info = q1.kinematics(p)
    release = km(np.asarray(info["release_point_m"], dtype=float))
    explosion = km(np.asarray(info["explosion_point_m"], dtype=float))
    missile = km(q1.missile_position(t, p))
    drone = km(uav_position(t, p))
    true_target = km(p.target_base_center)
    false_target = np.zeros(3)
    is_active = covered(t, interval)

    ax.set_xlim(-0.65, 20.65)
    ax.set_ylim(-0.82, 1.05)
    ax.set_zlim(0.0, 2.35)
    ax.set_box_aspect((2.55, 1.35, 1.38))
    # Fixed low camera on the external bisector of O->true-target and
    # O->initial-missile.  The negative ray places the camera outside the
    # angle so both arms open into the frame while it looks back toward O.
    true_center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    true_ray = true_center / np.linalg.norm(true_center)
    missile_ray = p.missile_initial / np.linalg.norm(p.missile_initial)
    bisector = true_ray + missile_ray
    bisector = bisector / np.linalg.norm(bisector)
    camera_ray = -bisector
    camera_elev = math.degrees(math.asin(float(camera_ray[2])))
    camera_azim = math.degrees(math.atan2(float(camera_ray[1]), float(camera_ray[0])))
    ax.view_init(elev=camera_elev, azim=camera_azim)
    ax.dist = 6.4
    ax.set_axis_off()
    ax.set_position([0.005, 0.01, 0.99, 0.93])
    ax.text2D(0.50, 0.965, "Q2 导弹视线锥与无人机投爆过程（角平分机位仰视）", transform=ax.transAxes, ha="center", fontsize=13)

    draw_ground(ax)
    draw_sight_cone(ax, missile, is_active)
    draw_cylinder(ax, true_target)
    ax.scatter([false_target[0]], [false_target[1]], [false_target[2]], marker="x", s=55, color=INK, zorder=7)
    ax.text(true_target[0] + 0.22, true_target[1] + 0.10, 0.58, "真目标", color=GREEN, zorder=14)
    ax.text(0.16, -0.08, 0.04, "假目标 O", color=INK, zorder=14)

    missile_direction = -p.missile_initial / np.linalg.norm(p.missile_initial) / 1000.0
    draw_missile(ax, missile, missile_direction)
    ax.text(missile[0] + 0.16, missile[1] + 0.12, missile[2] + 0.20, "M1", color=RED, zorder=14)

    track_t = np.linspace(0.0, 7.0, 100)
    track = np.asarray([km(uav_position(value, p)) for value in track_t])
    ax.plot(track[:, 0], track[:, 1], track[:, 2], color=BLUE, lw=1.2, alpha=0.60, zorder=5)
    draw_drone(ax, drone)
    ax.text(drone[0] + 0.18, drone[1] - 0.30, drone[2] - 0.05, "FY1", color=BLUE, zorder=14)

    ax.scatter([release[0]], [release[1]], [release[2]], s=30, marker="D", facecolor="white", edgecolor=ORANGE, zorder=10)
    if t <= p.release_time + 0.20:
        ax.text(release[0] - 0.20, release[1] - 0.36, release[2] - 0.24, "R 投放", color=ORANGE, zorder=14)

    explosion_time = p.release_time + p.fuse_delay
    if p.release_time <= t < explosion_time:
        bomb_t = np.linspace(p.release_time, t, 35)
        path = np.asarray([km(bomb_position(value, p)) for value in bomb_t])
        ax.plot(path[:, 0], path[:, 1], path[:, 2], color=ORANGE, lw=2.0, zorder=9)
        bomb = km(bomb_position(t, p))
        ax.scatter([bomb[0]], [bomb[1]], [bomb[2]], s=45, color=ORANGE, marker="o", zorder=11)
        ax.plot([drone[0], bomb[0]], [drone[1], bomb[1]], [drone[2], bomb[2]], color=ORANGE, lw=0.8, ls="--", alpha=0.7, zorder=7)
    elif t >= explosion_time:
        cloud = km(q1.smoke_center(t, p))
        ax.scatter([explosion[0]], [explosion[1]], [explosion[2]], s=78, marker="*", color=ORANGE, edgecolor=RED, zorder=12)
        if t <= explosion_time + 0.10:
            ax.text(explosion[0] - 0.28, explosion[1] + 0.30, explosion[2] + 0.30, "E 起爆", color=RED, zorder=14)
        draw_smoke_sphere(ax, cloud, is_active)
        ax.plot([explosion[0], cloud[0]], [explosion[1], cloud[1]], [explosion[2], cloud[2]], color=GREEN if is_active else ORANGE, lw=1.2, ls="--", zorder=7)
        ax.text(cloud[0] - 0.62, cloud[1] - 0.48, cloud[2] - 0.42, "烟幕球 C(t)", color=GREEN if is_active else ORANGE, zorder=14)

    label, color = status(t, p, interval)
    ax.text2D(0.025, 0.91, f"t = {t:.3f} s", transform=ax.transAxes, color=INK, fontsize=12)
    ax.text2D(0.025, 0.835, label, transform=ax.transAxes, color=color, fontsize=11.5, bbox=dict(boxstyle="round,pad=0.30", fc="white", ec=color))
    ax.text2D(0.985, 0.025, "伪三维示意（不按比例）：位置与时刻取自 Q2 正式结果，纵深压缩且物体尺寸作可视化放大", transform=ax.transAxes, ha="right", color=GRAY, fontsize=8.6)


def add_holds(base: np.ndarray, events: list[float], repeats: int = 5) -> np.ndarray:
    ordered = np.unique(np.concatenate((base, np.asarray(events, dtype=float))))
    frames: list[float] = []
    for value in ordered:
        frames.append(float(value))
        if any(abs(float(value) - event) <= 2e-8 for event in events):
            frames.extend([float(value)] * repeats)
    return np.asarray(frames)


def save_still(t: float, stem: str, result: dict, p: q1.Q1Parameters) -> None:
    fig = plt.figure(figsize=(10.2, 6.6))
    ax = fig.add_subplot(111, projection="3d")
    draw_frame(ax, t, result, p)
    fig.savefig(ROOT / "docs" / "fig" / f"{stem}.png", dpi=220, facecolor="white")
    plt.close(fig)


def save_gif(times: np.ndarray, result: dict, p: q1.Q1Parameters) -> None:
    fig = plt.figure(figsize=(10.2, 6.6))
    ax = fig.add_subplot(111, projection="3d")

    def update(index: int):
        draw_frame(ax, float(times[index]), result, p)
        return []

    movie = animation.FuncAnimation(fig, update, frames=len(times), interval=1000 / 12, blit=False)
    movie.save(ROOT / "docs" / "fig" / "q2_pseudo3d_los_cone.gif", writer=animation.PillowWriter(fps=12), dpi=105)
    plt.close(fig)


def run() -> None:
    setup_style()
    (ROOT / "docs" / "fig").mkdir(parents=True, exist_ok=True)
    result, p = load_case()
    entry, exit_time = (float(value) for value in result["formal_best"]["precise"]["intervals_s"][0])
    midpoint = 0.5 * (entry + exit_time)
    release = float(p.release_time)
    explosion = float(p.release_time + p.fuse_delay)
    events = [release, explosion, entry, midpoint, exit_time]
    times = add_holds(np.linspace(0.0, 6.35, 62), events)
    save_gif(times, result, p)
    for value, stem in (
        (release, "fig_q2_pseudo3d_release"),
        (explosion, "fig_q2_pseudo3d_explosion"),
        (entry, "fig_q2_pseudo3d_entry"),
        (midpoint, "fig_q2_pseudo3d_mid"),
        (exit_time, "fig_q2_pseudo3d_exit"),
    ):
        save_still(value, stem, result, p)
    print(json.dumps({"status": "ok", "frames_requested": len(times), "events_s": events}, ensure_ascii=False))


if __name__ == "__main__":
    run()
