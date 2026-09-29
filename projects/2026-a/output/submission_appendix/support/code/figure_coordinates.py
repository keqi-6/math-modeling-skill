"""Portable functions extracted from the team's existing figure source.
No solver is imported. See figures/README.md for scope and data provenance.
"""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_rgb
from matplotlib.cm import ScalarMappable
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.text import Text
import matplotlib.patheffects as path_effects
import numpy as np
DATA = Path(__file__).resolve().parents[1] / "figure_data"
OUT = Path.cwd() / "redrawn_figures"

def obs():
    return json.loads((DATA/"radius_observations.json").read_text(encoding="utf-8"))

def export(fig, name, dpi=300, transparent=False):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT/f"{name}.{ext}", dpi=dpi, transparent=transparent)
    plt.close(fig)

WIDTH_CM,HEIGHT_CM=15.8,6.4
BLUE,ORANGE,INK="#0072B2","#D55E00","#45525B"
BODY,GRAY="#F3EBDD","#747474"
def gray(color):
    rgb = np.array(to_rgb(color))
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = float(linear @ np.array([0.2126, 0.7152, 0.0722]))
    srgb = 12.92 * lum if lum <= 0.0031308 else 1.055 * lum ** (1 / 2.4) - 0.055
    return (srgb, srgb, srgb)

def draw(times, radii, selected, *, grayscale=False):
    color = gray if grayscale else lambda value: value
    blue, orange, ink, body, neutral = map(color, (BLUE, ORANGE, INK, BODY, GRAY))
    fig = plt.figure(figsize=(WIDTH_CM / 2.54, HEIGHT_CM / 2.54))
    chart = fig.add_axes((0.086, 0.195, 0.325, 0.705))
    chart.plot(times, radii, color=blue, lw=1.75, label="线性重建", zorder=2)
    chart.scatter(times, radii, s=5.1, color=neutral, edgecolors="none", label="半径观测", zorder=3)
    chart.set(xlim=(0, 72), ylim=(1.16, 2.035), xlabel="时间 / h")
    chart.set_xticks([0, 18, 36, 54, 72])
    chart.set_yticks([1.2, 1.4, 1.6, 1.8, 2.0])
    chart.tick_params(labelsize=8, length=2.8, width=0.7, pad=3)
    chart.grid(color="0.90", lw=0.45)
    chart.set_axisbelow(True)
    chart.legend(frameon=False, loc="upper right", bbox_to_anchor=(1.0, 0.84),
                 fontsize=8, handlelength=2.1, handletextpad=0.45)
    chart.text(-0.17, 0.48, "外\n半\n径\n(cm)", transform=chart.transAxes,
               ha="center", va="center", fontsize=8.5, linespacing=1.05)
    chart.text(0.0, 1.055, "(a)", transform=chart.transAxes, ha="left", va="bottom", fontsize=9)

    # Both snapshots live in a single equal-aspect axis, so their physical
    # centimetre scales cannot diverge through independent autoscaling.
    view = fig.add_axes((0.452, 0.10, 0.538, 0.80))
    view.set(xlim=(-2.3, 8.45), ylim=(-3.0, 3.10))
    view.set_aspect("equal", adjustable="box")
    view.axis("off")
    centers = [0.0, 5.75]
    for center, radius, hour in zip(centers, selected, [0, 6]):
        view.add_patch(Circle((center, 0), radius, facecolor=body, edgecolor=ink, lw=1.15, zorder=1))
        view.add_patch(Circle((center, 0), radius * 0.5, fill=False, edgecolor=blue, lw=1.65, zorder=3))
        view.plot([center - 2.1, center + 2.2], [0, 0], color="0.70", lw=0.65,
                  ls=(0, (4, 2, 1, 2)), zorder=2)
        view.plot(center, 0, "o", ms=2.7, color=ink, zorder=6)
        # A tagged material point lies on the same xi=0.5 circle in each view.
        view.plot(center + radius * 0.5, 0, "o", ms=4.3, mfc="white", mec=blue, mew=1.2, zorder=7)
        # This is a fixed-coordinate sample marker, not a physical instrument.
        fixed_x = center + 1.5
        view.plot([fixed_x, fixed_x], [-0.37, 0.50], color=orange, lw=1.1,
                  ls=(0, (2.5, 2.0)), zorder=4)
        view.plot(fixed_x, 0, marker="x", ms=4.3, mew=1.15, color=orange, zorder=8)
        view.text(center, 2.48, f"{hour} h", ha="center", va="center", fontsize=8.8)
        view.text(center, -2.49, rf"$R={radius:.3f}\,\mathrm{{cm}}$",
                  ha="center", va="center", fontsize=8.6)
        view.text(center - 0.08, -0.27, "O", ha="right", va="top", fontsize=7.6)
    # Sequence direction only; no arrow length encodes material velocity.
    view.annotate("", xy=(3.49, 0.88), xytext=(2.50, 0.88),
                  arrowprops=dict(arrowstyle="->", lw=1.15, color=ink))
    view.text(2.99, 1.22, r"$r=R(t)\xi$", ha="center", va="bottom", fontsize=8.4)
    fig.text(0.452, 0.939, "(b)", ha="left", va="bottom", fontsize=9)

    ring_handle = Line2D([0], [0], color=blue, lw=1.65, marker="o", mfc="white", ms=3.5)
    fixed_handle = Line2D([0], [0], color=orange, lw=1.1, ls="--", marker="x", ms=4.5)
    fig.legend([ring_handle, fixed_handle], [r"材料环 $\xi=0.5$", r"固定位置 $r=1.5\,\mathrm{cm}$"],
               loc="lower center", bbox_to_anchor=(0.722, 0.017), ncol=2, frameon=False,
               fontsize=8, handlelength=1.6, handletextpad=0.4, columnspacing=1.0)
    return fig
def render():
    a=np.array(obs()["q4_radius_time_s_cm"])
    selected=[float(a[a[:,0]==t,1].item()) for t in [0,21600]]
    export(draw(a[:,0]/3600,a[:,1],selected),"fig06_q4_coordinates",dpi=360)
