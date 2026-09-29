#!/usr/bin/env python3
"""Create one geometry-faithful Q2 camera calibration frame.

The camera is placed close to the missile--smoke event region and looks down
the engagement corridor.  Every centre, direction, target boundary point and
trajectory is passed through one perspective projection.  The image plane is
only rolled (never stretched) so the projected M--target line is horizontal.
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
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, Ellipse, FancyArrowPatch, Polygon, Rectangle


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "q1"))
import model as q1  # noqa: E402

INK = "#37444A"
BLUE = "#246B86"
GREEN = "#326B51"
LIGHT_GREEN = "#C5DACB"
RED = "#91332D"
ORANGE = "#D27B24"
GRAY = "#7A858B"


def setup_style() -> None:
    font_path = Path("/mnt/c/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
    else:
        font_name = "DejaVu Sans"
    plt.rcParams.update({"font.family": font_name, "axes.unicode_minus": False, "font.size": 11})


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


class Camera:
    def __init__(self, p: q1.Q1Parameters, reference_time: float, view: str = "near_corridor"):
        self.origin = np.zeros(3)
        self.target_center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
        self.reference_missile = q1.missile_position(reference_time, p)
        self.reference_cloud = q1.smoke_center(reference_time, p)

        world_up = np.array([0.0, 0.0, 1.0])
        if view == "event_plane":
            reference_uav = p.uav_initial + p.uav_speed * reference_time * p.uav_direction
            event_center = (self.reference_missile + self.reference_cloud + reference_uav) / 3.0
            normal = np.cross(self.reference_cloud - self.reference_missile, reference_uav - self.reference_missile)
            normal /= np.linalg.norm(normal)
            if normal[2] > 0.0:
                normal = -normal
            self.position = event_center + 4000.0 * normal
            self.look_at = event_center
            self.forward = -normal
        else:
            # A near-event oblique viewpoint.  The offset is perpendicular to
            # the M--target corridor and slightly below it.
            corridor = self.target_center - self.reference_missile
            corridor /= np.linalg.norm(corridor)
            lateral = np.cross(corridor, world_up)
            lateral /= np.linalg.norm(lateral)
            event_center = 0.5 * (self.reference_missile + self.reference_cloud)
            self.position = event_center + 4500.0 * lateral - 1500.0 * world_up
            self.look_at = self.reference_cloud + 0.25 * (self.target_center - self.reference_cloud)
            self.forward = self.look_at - self.position
            self.forward /= np.linalg.norm(self.forward)
        self.right = np.cross(self.forward, world_up)
        self.right /= np.linalg.norm(self.right)
        self.up = np.cross(self.right, self.forward)
        self.up /= np.linalg.norm(self.up)

        q_target = self._raw(self.target_center)
        q_missile = self._raw(self.reference_missile)
        delta = q_missile - q_target
        angle = math.atan2(float(delta[1]), float(delta[0]))
        c, s = math.cos(-angle), math.sin(-angle)
        self.roll = np.array([[c, -s], [s, c]])

    def _raw(self, point: np.ndarray) -> np.ndarray:
        vector = np.asarray(point, dtype=float) - self.position
        depth = float(np.dot(vector, self.forward))
        if depth <= 0.0:
            raise ValueError("point is behind the calibration camera")
        return np.array([np.dot(vector, self.right) / depth, np.dot(vector, self.up) / depth])

    def project(self, point: np.ndarray) -> np.ndarray:
        value = self.roll @ self._raw(point)
        # A horizontal/vertical image flip changes only presentation handedness;
        # unlike the old draft, no anisotropic display magnification is used.
        return np.array([-value[0], -value[1]])


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


def draw_drone(ax: plt.Axes, point: np.ndarray) -> None:
    x, y = point
    ax.plot([x - 0.028, x + 0.028], [y, y], color=BLUE, lw=2.0, zorder=12)
    ax.plot([x, x], [y - 0.018, y + 0.018], color=BLUE, lw=1.8, zorder=12)
    ax.add_patch(Ellipse((x, y), 0.025, 0.016, fc=BLUE, ec="#164A5C", lw=1.0, zorder=13))
    for dx, dy in ((-0.028, 0.0), (0.028, 0.0), (0.0, -0.018), (0.0, 0.018)):
        ax.add_patch(Ellipse((x + dx, y + dy), 0.022, 0.008, fc="white", ec=BLUE, lw=1.0, zorder=13))


def draw_missile(ax: plt.Axes, centre: np.ndarray, direction: np.ndarray) -> None:
    direction = direction / np.linalg.norm(direction)
    normal = np.array([-direction[1], direction[0]])
    nose = centre + 0.045 * direction
    tail = centre - 0.035 * direction
    polygon = np.vstack((nose, tail + 0.014 * normal, tail - 0.014 * normal))
    ax.add_patch(Polygon(polygon, closed=True, fc="#A94841", ec="#6F2521", lw=1.4, zorder=13))
    ax.add_patch(FancyArrowPatch(centre - 0.075 * direction, centre + 0.052 * direction, arrowstyle="-|>", mutation_scale=12, color=RED, lw=1.5, zorder=12))


def render(output: Path, view: str = "near_corridor") -> None:
    setup_style()
    result, p = load_case()
    entry, exit_time = (float(value) for value in result["formal_best"]["precise"]["intervals_s"][0])
    t = 0.5 * (entry + exit_time)
    camera = Camera(p, t, view=view)

    O = np.zeros(3)
    target_center = p.target_base_center + np.array([0.0, 0.0, 0.5 * p.target_height])
    missile = q1.missile_position(t, p)
    cloud = q1.smoke_center(t, p)
    uav = p.uav_initial + p.uav_speed * t * p.uav_direction
    qO, qT, qM, qC, qU = (camera.project(point) for point in (O, target_center, missile, cloud, uav))

    theta = np.linspace(0.0, 2.0 * math.pi, 361)
    target_points = np.vstack((q1.target_circle(theta, 0.0, p), q1.target_circle(theta, p.target_height, p)))
    projected_target = np.asarray([camera.project(point) for point in target_points])
    target_hull = convex_hull(projected_target)
    top_point = projected_target[np.argmax(projected_target[:, 1])]
    bottom_point = projected_target[np.argmin(projected_target[:, 1])]

    if view == "event_plane":
        fig, ax = plt.subplots(figsize=(11.2, 5.0))
        ax.set_xlim(min(qM[0], qC[0], qU[0]) - 0.075, max(qM[0], qC[0], qU[0]) + 0.075)
        ax.set_ylim(-0.080, 0.080)
        ax.set_aspect("equal", adjustable="box")
        ax.axis("off")

        times = np.linspace(0.0, 6.35, 160)
        missile_track = np.asarray([camera.project(q1.missile_position(value, p)) for value in times])
        uav_track = np.asarray([camera.project(p.uav_initial + p.uav_speed * value * p.uav_direction) for value in times])
        ax.plot(missile_track[:, 0], missile_track[:, 1], color=RED, lw=1.8, alpha=0.82, label="M1 轨迹", zorder=3)
        ax.plot(uav_track[:, 0], uav_track[:, 1], color=BLUE, lw=1.8, ls="--", alpha=0.88, label="FY1 轨迹", zorder=4)

        target_direction = qT - qC
        target_direction /= np.linalg.norm(target_direction)
        ray_end = qC + 0.40 * target_direction
        ax.add_patch(FancyArrowPatch(qC, ray_end, arrowstyle="-|>", mutation_scale=13, color=GREEN, lw=1.3, alpha=0.70, zorder=2))
        ax.text(qC[0] + 0.075, qC[1] - 0.035, "真目标与假目标方向（画外）", color=GREEN, fontsize=9.5, ha="center")

        ax.add_patch(Circle(tuple(qC), 0.025, fc=LIGHT_GREEN, ec=GREEN, lw=1.5, alpha=0.82, zorder=8))
        ax.add_patch(Ellipse(tuple(qC), 0.050, 0.014, fc="none", ec=GREEN, lw=0.8, alpha=0.65, zorder=9))
        draw_drone(ax, qU)
        missile_forward_world = -p.missile_initial / np.linalg.norm(p.missile_initial)
        projected_tip = camera.project(missile + 800.0 * missile_forward_world)
        draw_missile(ax, qM, projected_tip - qM)
        ax.scatter([qM[0], qC[0], qU[0]], [qM[1], qC[1], qU[1]], s=16, color=[RED, GREEN, BLUE], zorder=14)

        plane_height = np.linalg.norm(np.cross(qU - qM, qC - qM)) / np.linalg.norm(qC - qM)
        world_height = np.linalg.norm(np.cross(uav - missile, cloud - missile)) / np.linalg.norm(cloud - missile)
        ax.annotate("M1", xy=qM, xytext=(qM[0] - 0.015, 0.052), color=RED, ha="center", arrowprops=dict(arrowstyle="->", color=RED, lw=0.9))
        ax.annotate("烟幕中心 C(t)", xy=qC, xytext=(qC[0] + 0.005, -0.062), color=GREEN, ha="center", arrowprops=dict(arrowstyle="->", color=GREEN, lw=0.9))
        ax.annotate("FY1", xy=qU, xytext=(qU[0] + 0.018, 0.050), color=BLUE, ha="center", arrowprops=dict(arrowstyle="->", color=BLUE, lw=0.9))
        ax.text(0.50, 0.96, "Q2 事件平面法向视角（局部真透视）", transform=ax.transAxes, ha="center", va="top", fontsize=13)
        ax.text(0.50, 0.05, f"相机光轴垂直于 M1—C(t)—FY1 三点平面；FY1 到 M1—C(t) 连线的真实垂距为 {world_height:.2f} m", transform=ax.transAxes, ha="center", color=GRAY, fontsize=9)

        output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=220, facecolor="white")
        plt.close(fig)
        print(json.dumps({"status": "ok", "output": str(output), "view": view, "time_s": t, "world_plane_height_m": world_height, "projected_plane_height": plane_height, "camera_position_m": camera.position.tolist()}, ensure_ascii=False))
        return

    fig, ax = plt.subplots(figsize=(11.2, 6.3))
    ax.set_xlim(-1.62, 0.82)
    ax.set_ylim(-0.50, 0.50)
    ax.set_aspect("equal", adjustable="box")
    ax.axis("off")

    # Same-matrix projected geometry.  The pale broad cone is a visibility aid;
    # the dark central and boundary rays are the true projected rays.
    display_top = qT + np.array([0.0, 0.12])
    display_bottom = qT - np.array([0.0, 0.12])
    ax.add_patch(Polygon([qM, display_top, display_bottom], closed=True, fc="#D9E9E0", ec="none", alpha=0.38, zorder=1))
    ax.plot([qM[0], display_top[0]], [qM[1], display_top[1]], color=GREEN, ls=":", lw=1.0, alpha=0.45, zorder=2)
    ax.plot([qM[0], display_bottom[0]], [qM[1], display_bottom[1]], color=GREEN, ls=":", lw=1.0, alpha=0.45, zorder=2)
    for point, style, width in ((top_point, "-", 1.6), (bottom_point, "-", 1.6), (qT, "--", 1.1)):
        ax.plot([qM[0], point[0]], [qM[1], point[1]], color=GREEN, ls=style, lw=width, alpha=0.86, zorder=3)
    ax.plot([qM[0], qT[0]], [qM[1], qT[1]], color=INK, lw=1.2, alpha=0.72, zorder=4)
    ax.plot([qM[0], qO[0]], [qM[1], qO[1]], color=RED, lw=1.35, ls="--", alpha=0.88, zorder=5)

    # Actual projected target hull plus a screen-space body glyph centred at qT.
    ax.add_patch(Polygon(target_hull, closed=True, fc="#90AE98", ec=GREEN, lw=1.4, alpha=0.80, zorder=7))
    ax.add_patch(Rectangle((qT[0] - 0.007, qT[1] - 0.12), 0.014, 0.24, fc="#91AE98", ec=GREEN, lw=1.3, alpha=0.62, zorder=6))
    ax.add_patch(Ellipse((qT[0], qT[1] + 0.12), 0.016, 0.010, fc="#A7BEAC", ec=GREEN, lw=1.2, zorder=8))
    ax.add_patch(Ellipse((qT[0], qT[1] - 0.12), 0.016, 0.010, fc="#88A38F", ec=GREEN, lw=1.2, zorder=8))

    # Smoke and vehicle glyphs are enlarged only in screen space; centres stay exact.
    ax.add_patch(Circle(tuple(qC), 0.082, fc=LIGHT_GREEN, ec=GREEN, lw=1.7, alpha=0.86, zorder=9))
    ax.add_patch(Ellipse(tuple(qC), 0.164, 0.042, fc="none", ec=GREEN, lw=0.9, alpha=0.65, zorder=10))

    times = np.linspace(0.0, 6.35, 120)
    track = np.asarray([camera.project(p.uav_initial + p.uav_speed * value * p.uav_direction) for value in times])
    ax.plot(track[:, 0], track[:, 1], color=BLUE, lw=1.2, ls="--", alpha=0.55, zorder=5)
    draw_drone(ax, qU)

    missile_forward_world = -p.missile_initial / np.linalg.norm(p.missile_initial)
    projected_tip = camera.project(missile + 800.0 * missile_forward_world)
    draw_missile(ax, qM, projected_tip - qM)

    ax.scatter([qO[0]], [qO[1]], marker="x", s=82, color=RED, linewidths=1.6, zorder=14)
    ax.scatter([qT[0], qC[0]], [qT[1], qC[1]], s=20, color=GREEN, zorder=14)

    ax.annotate("假目标 O（红色航向线终点）", xy=qO, xytext=(qO[0] - 0.10, -0.27), ha="center", color=RED, fontsize=10, arrowprops=dict(arrowstyle="->", color=RED, lw=0.9))
    ax.annotate("真目标圆柱", xy=qT, xytext=(qT[0] + 0.12, 0.27), ha="center", color=GREEN, fontsize=11.5, arrowprops=dict(arrowstyle="->", color=GREEN, lw=0.9))
    ax.annotate("烟幕球 C(t)", xy=qC, xytext=(qC[0] + 0.03, -0.24), ha="center", color=GREEN, fontsize=11.5, arrowprops=dict(arrowstyle="->", color=GREEN, lw=0.9))
    ax.annotate("FY1 与航迹", xy=qU, xytext=(qU[0] - 0.03, 0.24), ha="center", color=BLUE, fontsize=11, arrowprops=dict(arrowstyle="->", color=BLUE, lw=0.9))
    ax.annotate("M1（弹头朝向假目标 O）", xy=qM, xytext=(qM[0] + 0.18, 0.27), ha="center", color=RED, fontsize=11, arrowprops=dict(arrowstyle="->", color=RED, lw=0.9))

    ax.text(0.50, 0.965, "Q2 近导弹—烟幕视角：单一透视关系校准", transform=ax.transAxes, ha="center", va="top", fontsize=13)
    ax.text(0.985, 0.025, "相机位于导弹—烟幕事件区侧下方，朝交战走廊观察；所有中心与轨迹采用同一透视矩阵，仅目标与图标尺寸作示意放大", transform=ax.transAxes, ha="right", color=GRAY, fontsize=8.6)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220, facecolor="white")
    plt.close(fig)
    print(json.dumps({"status": "ok", "output": str(output), "time_s": t, "camera_position_m": camera.position.tolist()}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--view", choices=("near_corridor", "event_plane"), default="near_corridor")
    args = parser.parse_args()
    render(args.output, view=args.view)


if __name__ == "__main__":
    main()
