#!/usr/bin/env python3
"""Render the six Q1 figures used by the teammate solution brief.

The four geometry figures are deliberately schematic.  The event timeline
and endpoint profile read their numerical values from the current Q1 result
artifacts; no plotted value is copied into the source by hand.
"""

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
DEFAULT_FIG_DIR = ROOT / "docs" / "fig"
RESULT_PATH = ROOT / "docs" / "q1_result.json"
SENS_PATH = ROOT / "docs" / "q1_decision_sensitivity.json"

INK = "#263238"
GRAY = "#7A858B"
PALE = "#EDF1F2"
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


def cylinder(ax: plt.Axes, centre, width, height, *, edge=BLUE, fill=PALE_BLUE, zorder=4) -> None:
    x, y = centre
    cap = 0.24 * width
    ax.add_patch(Rectangle((x - width / 2, y - height / 2), width, height, fc=fill, ec="none", alpha=0.75, zorder=zorder))
    ax.plot([x - width / 2, x - width / 2], [y - height / 2, y + height / 2], color=edge, lw=1.35, zorder=zorder + 1)
    ax.plot([x + width / 2, x + width / 2], [y - height / 2, y + height / 2], color=edge, lw=1.35, zorder=zorder + 1)
    ax.add_patch(Ellipse((x, y + height / 2), width, cap, fc="white", ec=edge, lw=1.35, zorder=zorder + 2))
    ax.add_patch(Ellipse((x, y - height / 2), width, cap, fc=fill, ec=edge, lw=1.35, zorder=zorder + 2))


def draw_overall_geometry(output_dir: Path) -> None:
    """One-view map of the five physical objects used in Q1."""
    fig, ax = plt.subplots(figsize=(9.4, 4.7))
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.0, 5.2)
    ax.axis("off")

    target = np.array([1.45, 2.65])
    fake = np.array([1.25, 0.78])
    missile = np.array([9.15, 1.05])
    cloud = np.array([5.35, 1.72])

    cylinder(ax, target, 0.86, 1.55)
    ax.text(target[0], 3.70, r"$T$", ha="center", color=BLUE, fontsize=12)
    ax.scatter(*fake, s=28, color=INK, zorder=7)
    ax.text(fake[0] - 0.03, 0.40, r"$O$", ha="center", fontsize=12)

    # The missile heads to the false target; the solid rays are the actual
    # boundary sight lines that must be intercepted.
    ax.plot([missile[0], fake[0]], [missile[1], fake[1]], color=RED, lw=1.15, ls=(0, (5, 3)), zorder=2)
    ax.plot([missile[0], target[0] - 0.10], [missile[1], target[1] - 0.83], color=INK, lw=1.05, zorder=2)
    ax.plot([missile[0], target[0] + 0.10], [missile[1], target[1] + 0.83], color=INK, lw=1.05, zorder=2)
    ax.scatter(*missile, marker="<", s=72, color=RED, zorder=8)
    arrow(ax, (8.82, 1.04), (8.08, 1.01), color=RED, lw=1.45)
    ax.text(missile[0], 0.55, r"$M(t)$", ha="center", color=RED, fontsize=12)

    ax.add_patch(Circle(tuple(cloud), 0.56, fc=PALE_GREEN, ec=GREEN, lw=1.45, alpha=0.94, zorder=5))
    ax.scatter(*cloud, s=17, color=GREEN, zorder=7)
    ax.text(cloud[0], 2.48, r"$C(t)$", ha="center", color=GREEN, fontsize=12)

    # UAV path is separated vertically from the sight bundle.
    ax.plot([3.55, 9.25], [4.45, 4.45], color=GRAY, lw=1.05, ls=(0, (5, 3)))
    ax.scatter([8.75], [4.45], marker="D", s=38, facecolor="white", edgecolor=BLUE, linewidth=1.35, zorder=7)
    arrow(ax, (8.50, 4.45), (7.72, 4.45), color=BLUE, lw=1.45)
    ax.text(8.76, 4.84, r"$U(t)$", ha="center", color=BLUE, fontsize=12)

    # A short leader identifies the sight bundle without filling the image
    # with a sentence.
    ax.text(3.12, 2.40, "边界视线束", color=GRAY, fontsize=9.5, ha="center")
    ax.plot([3.40, 3.95], [2.27, 2.02], color=GRAY, lw=0.8)
    save(fig, output_dir, "fig_q1_overall_geometry")


def draw_release_explosion(output_dir: Path) -> None:
    """Schematic dependency from UAV motion to cloud descent."""
    fig, ax = plt.subplots(figsize=(9.2, 4.5))
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.1, 5.3)
    ax.axis("off")

    ax.plot([1.0, 9.25], [4.45, 4.45], color=INK, lw=1.15)
    arrow(ax, (8.60, 4.45), (7.78, 4.45), color=BLUE, lw=1.45)
    ax.scatter([8.95], [4.45], marker="D", s=38, facecolor="white", edgecolor=BLUE, linewidth=1.3, zorder=6)
    ax.text(9.00, 4.82, r"$U(t)$", ha="center", color=BLUE, fontsize=12)
    ax.text(7.95, 4.84, r"$(\alpha,v)$", ha="center", color=BLUE)

    release = np.array([6.85, 4.45])
    explosion = np.array([4.65, 2.62])
    ax.scatter(*release, s=48, color=ORANGE, zorder=7)
    ax.text(release[0], 4.86, r"$R(\tau)$", ha="center", color=ORANGE, fontsize=12)

    s = np.linspace(0.0, 1.0, 120)
    x = release[0] + (explosion[0] - release[0]) * s
    y = release[1] - 0.16 * s - 1.67 * s**2
    ax.plot(x, y, color=ORANGE, lw=1.75)
    arrow(ax, (x[56], y[56]), (x[67], y[67]), color=ORANGE, lw=1.25)
    ax.text(5.85, 3.64, r"$\delta$", color=ORANGE, fontsize=12)

    ax.scatter(*explosion, s=50, color=RED, zorder=7)
    ax.add_patch(Circle(tuple(explosion), 0.13, fill=False, ec=RED, lw=1.0))
    ax.text(explosion[0] - 0.25, 2.94, r"$E(\tau+\delta)$", ha="right", color=RED, fontsize=12)

    cloud = np.array([4.65, 1.05])
    ax.plot([explosion[0], cloud[0]], [explosion[1] - 0.15, cloud[1] + 0.48], color=GREEN, lw=1.05, ls=(0, (4, 3)))
    arrow(ax, (4.65, 2.16), (4.65, 1.72), color=GREEN, lw=1.25)
    ax.text(4.92, 1.95, r"$v_s$", color=GREEN)
    ax.add_patch(Circle(tuple(cloud), 0.50, fc=PALE_GREEN, ec=GREEN, lw=1.45, alpha=0.94))
    ax.scatter(*cloud, s=17, color=GREEN, zorder=7)
    ax.text(5.40, 1.03, r"$C(t)$", va="center", color=GREEN, fontsize=12)
    save(fig, output_dir, "fig_q1_release_explosion")


def draw_finite_segment(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 4.4))
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.0, 4.8)
    ax.axis("off")

    m = np.array([1.15, 1.05])
    p = np.array([8.85, 1.72])
    c = np.array([5.75, 3.55])
    direction = p - m
    lam = np.dot(c - m, direction) / np.dot(direction, direction)
    q = m + lam * direction

    # Extension and physical segment use different line styles, so the
    # finite-domain distinction survives grayscale printing.
    ext_start = m - 0.12 * direction
    ext_end = p + 0.12 * direction
    ax.plot([ext_start[0], ext_end[0]], [ext_start[1], ext_end[1]], color=GRAY, lw=1.0, ls=(0, (5, 3)))
    ax.plot([m[0], p[0]], [m[1], p[1]], color=BLUE, lw=2.6)
    ax.scatter(*m, marker="<", s=70, color=RED, zorder=7)
    ax.scatter(*p, s=50, color=BLUE, zorder=7)
    ax.text(m[0], 0.58, r"$M(t)$", ha="center", color=RED, fontsize=12)
    ax.text(p[0], 1.25, r"$P$", ha="center", color=BLUE, fontsize=12)
    ax.text(m[0] + 0.12, 1.42, r"$\lambda=0$", color=GRAY, fontsize=9.3)
    ax.text(p[0] - 0.55, 2.05, r"$\lambda=1$", color=GRAY, fontsize=9.3)

    ax.add_patch(Circle(tuple(c), 0.56, fc=PALE_GREEN, ec=GREEN, lw=1.45, alpha=0.94))
    ax.scatter(*c, s=17, color=GREEN, zorder=7)
    ax.text(c[0] + 0.72, c[1] + 0.05, r"$C(t)$", color=GREEN, fontsize=12)
    ax.plot([c[0], q[0]], [c[1], q[1]], color=INK, lw=1.25)
    ax.scatter(*q, s=30, color=INK, zorder=7)
    ax.text(q[0] - 0.18, q[1] - 0.37, r"$Q$", ha="right")
    ax.text((c[0] + q[0]) / 2 - 0.30, (c[1] + q[1]) / 2, r"$d_{\rm seg}$", ha="right", fontsize=12)

    # Small right-angle mark at Q.
    tangent = direction / np.linalg.norm(direction)
    normal = (c - q) / np.linalg.norm(c - q)
    size = 0.16
    r1 = q + tangent * size
    r2 = r1 + normal * size
    r3 = q + normal * size
    ax.plot([q[0], r1[0], r2[0], r3[0]], [q[1], r1[1], r2[1], r3[1]], color=INK, lw=0.9)
    save(fig, output_dir, "fig_q1_finite_segment")


def draw_cylinder_endpoint(output_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.set_xlim(0.0, 10.0)
    ax.set_ylim(0.0, 5.5)
    ax.axis("off")

    target = np.array([7.65, 2.75])
    cylinder(ax, target, 2.35, 3.15)
    gx = 8.22
    p0 = np.array([gx, 1.22])
    ph = np.array([gx, 4.28])
    pz = np.array([gx, 2.80])
    ax.plot([gx, gx], [p0[1], ph[1]], color=RED, lw=2.3, zorder=8)
    ax.scatter(*p0, s=42, color=RED, zorder=9)
    ax.scatter(*ph, s=42, color=RED, zorder=9)
    ax.scatter(*pz, s=28, facecolor="white", edgecolor=RED, linewidth=1.2, zorder=9)
    ax.text(gx + 0.25, p0[1] - 0.05, r"$P_0(\theta)$", va="top", color=RED, zorder=10)
    ax.text(gx + 0.25, ph[1] + 0.02, r"$P_H(\theta)$", va="bottom", color=RED, zorder=10)
    ax.text(gx + 0.25, pz[1], r"$P_z(\theta)$", va="center", color=RED, zorder=10)

    missile = np.array([0.95, 0.70])
    cloud = np.array([4.25, 1.82])
    ax.scatter(*missile, marker="<", s=70, color=INK, zorder=8)
    ax.text(missile[0], 0.25, r"$M(t)$", ha="center", fontsize=12)
    for point, width in ((p0, 1.25), (pz, 0.8), (ph, 1.25)):
        ax.plot([missile[0], point[0]], [missile[1], point[1]], color=INK, lw=width, alpha=0.78, zorder=2)

    ax.add_patch(Circle(tuple(cloud), 0.58, fc=PALE_GREEN, ec=GREEN, lw=1.45, alpha=0.94, zorder=5))
    ax.scatter(*cloud, s=17, color=GREEN, zorder=7)
    ax.text(cloud[0] - 0.05, 2.62, r"$C(t)$", ha="center", color=GREEN, fontsize=12)
    ax.text(7.36, 4.95, r"固定 $\theta$", color=GRAY, ha="center")
    save(fig, output_dir, "fig_q1_cylinder_endpoint")


def draw_event_timeline(result: dict, output_dir: Path) -> None:
    release = 1.5
    explosion = float(result["explosion_time_s"])
    entry, exit_time = (float(value) for value in result["intervals_s"][0])
    active_end = float(result["active_window_s"][1])
    possible_end = float(result["geometry_pruning"]["primary"]["possible_window_s"][1])

    break_time = 10.2
    break_x = 10.2
    end_x = 13.15

    def tx(value: float) -> float:
        if value <= break_time:
            return value
        return break_x + (value - break_time) * (end_x - break_x) / (active_end - break_time)

    fig, ax = plt.subplots(figsize=(9.6, 3.05))
    ax.set_xlim(-0.35, end_x + 0.75)
    ax.set_ylim(-1.35, 1.50)
    ax.axis("off")
    ax.plot([0, end_x + 0.35], [0, 0], color=INK, lw=1.30)
    arrow(ax, (end_x + 0.05, 0), (end_x + 0.52, 0), color=INK, lw=1.30)
    ax.fill_between([tx(explosion), tx(active_end)], -0.14, 0.14, color=PALE_GREEN, alpha=0.95)
    ax.fill_between([tx(explosion), tx(possible_end)], -0.19, 0.19, color=PALE_BLUE, alpha=0.96)
    ax.fill_between(
        [tx(possible_end), tx(active_end)], -0.14, 0.14,
        facecolor=PALE, edgecolor=GRAY, hatch="////", linewidth=0.0, alpha=0.92,
    )
    ax.fill_between([tx(entry), tx(exit_time)], -0.26, 0.26, color=GREEN, alpha=0.85)

    events = [
        (0.0, "计时起点", INK, 0.63),
        (release, f"投放\n{release:.1f} s", ORANGE, -0.78),
        (explosion, f"起爆\n{explosion:.1f} s", RED, 0.80),
        (entry, f"进入遮蔽\n{entry:.6f} s", GREEN, -0.92),
        (exit_time, f"退出遮蔽\n{exit_time:.6f} s", GREEN, 0.84),
        (active_end, f"烟幕失效\n{active_end:.1f} s", GRAY, -0.78),
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
    ax.text((tx(possible_end) + tx(active_end)) / 2, 0.41, "必要条件排除", color=GRAY, ha="center", fontsize=8.8)
    ax.text((tx(explosion) + tx(possible_end)) / 2, 0.40, "几何必要可行窗", color=BLUE, ha="center", fontsize=9.0)
    ax.text((tx(entry) + tx(exit_time)) / 2, -1.22, rf"$T_{{\rm eff}}={result['effective_duration_s']:.6f}\,\mathrm{{s}}$", color=GREEN, ha="center", fontsize=10.2)
    ax.text(end_x + 0.54, -0.18, r"$t$/s", color=INK)
    save(fig, output_dir, "fig_q1_event_timeline")


def draw_endpoint_profile(sensitivity: dict, output_dir: Path) -> None:
    record = sensitivity["geometry_validation"]["records"][1]
    grid = record["grid"]
    z = np.asarray(grid["z_m"], dtype=float)
    margin = np.asarray(grid["worst_vertical_profile_margin_m"], dtype=float)
    envelope = float(grid["worst_vertical_endpoint_envelope_m"])

    fig, ax = plt.subplots(figsize=(7.6, 4.35))
    ax.plot(z, margin, color=BLUE, lw=2.0)
    ax.axhline(envelope, color=GRAY, lw=1.0, ls=(0, (5, 3)))
    ax.scatter([z[0], z[-1]], [margin[0], margin[-1]], s=42, facecolor="white", edgecolor=RED, linewidth=1.35, zorder=6)
    ax.annotate(r"$z=0$", (z[0], margin[0]), xytext=(10, 10), textcoords="offset points", color=RED)
    ax.annotate(r"$z=H_T$", (z[-1], margin[-1]), xytext=(-8, 10), textcoords="offset points", ha="right", color=RED)
    ax.text(z[-1] * 0.98, envelope, "端点包络", ha="right", va="bottom", color=GRAY, fontsize=9.2)
    ax.set_xlabel(r"目标高度 $z$/m")
    ax.set_ylabel("遮蔽余量/m")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color=PALE, lw=0.8)
    fig.tight_layout()
    save(fig, output_dir, "fig_q1_endpoint_profile")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_FIG_DIR)
    args = parser.parse_args()
    setup_style()
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    sensitivity = json.loads(SENS_PATH.read_text(encoding="utf-8"))

    draw_overall_geometry(args.output_dir)
    draw_release_explosion(args.output_dir)
    draw_finite_segment(args.output_dir)
    draw_cylinder_endpoint(args.output_dir)
    draw_event_timeline(result, args.output_dir)
    draw_endpoint_profile(sensitivity, args.output_dir)
    print(json.dumps({"status": "ok", "figure_count": 6, "output_dir": str(args.output_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
