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

COLORS = ["#0072BD", "#D95319", "#3A923A", "#7E2F8E", "#333333"]
STYLES = ["-", "--", "-.", ":", (0, (5, 1, 1, 1))]
MARKERS = ["o", "s", "^", "D", "v"]
WIDTH = 15.8/2.54
def save(fig, name):
    upright_ylabels(fig)
    export(fig, name)


def axes_pair(height=2.8):
    fig, axs = plt.subplots(1, 2, figsize=(WIDTH, height), layout="constrained")
    for ax in axs:
        ax.grid(True, color=".87", linewidth=.4)
        ax.set_axisbelow(True)
    return fig, axs

def tag(ax, letter, name):
    # Descriptive titles belong in the adjacent manuscript text/caption.
    ax.set_title(f"({letter})", loc="left", pad=7, fontweight="bold")

def upright_ylabels(fig):
    """Stack Chinese names, keeping units and mathematical expressions intact."""
    for ax in fig.axes:
        label = ax.get_ylabel()
        if " / " not in label:
            continue
        name, unit = label.split(" / ", 1)
        if not all("\u4e00" <= char <= "\u9fff" for char in name):
            continue
        ax.set_ylabel("\n".join(name) + "\n" + unit, rotation=0,
                      ha="right", va="center", labelpad=10)
        ax.yaxis.label.set_multialignment("center")
        ax.yaxis.label.set_linespacing(1.05)

def line(ax, x, y, i, label, markevery=None, **kw):
    ax.plot(x, y, color=COLORS[i % 5], linestyle=STYLES[i % 5],
            marker=MARKERS[i % 5] if markevery else None,
            markevery=markevery, markersize=3.2, markerfacecolor="white",
            markeredgewidth=.9, label=label, **kw)

def fig03():
    p = DATA/"q1_profiles.npz"
    fig, axs = axes_pair(2.8)
    with np.load(p) as z:
        # Five saved times use distinct markers and line styles.
        for time, style_index in [(100, 0), (600, 1), (900, 3), (1200, 4), (1800, 2)]:
            k = np.flatnonzero(z["time_s"] == time).item()
            for ax, field in zip(axs, ["temperature_C", "moisture_kg_kg"]):
                line(ax, z["radius_m"]*100, z[field][k], style_index, f"{time} s", markevery=2)
    for ax, title, ylabel in zip(axs, ["温度径向剖面", "含水率径向剖面"], ["温度 / °C", "干基含水率 / (kg/kg)"]):
        tag(ax, "a" if ax is axs[0] else "b", title)
        ax.set(xlim=(-.04, 2.04), xlabel="半径 / cm", ylabel=ylabel)
        ax.set_xticks([0, .5, 1, 1.5, 2])
        ax.legend(frameon=False, loc="upper left" if ax is axs[0] else "lower left",
                  ncol=2, handlelength=2.7, columnspacing=1)
    save(fig, 'fig03_q1_profiles')
