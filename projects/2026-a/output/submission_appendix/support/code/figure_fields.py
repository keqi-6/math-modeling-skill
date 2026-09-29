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

WIDTH_CM=15.8
HEIGHT_IN=3.2
PALETTE_POSITIONS=[0,.25,.5,.75,1]
TEMPERATURE_COLORS=["#fffaf1","#fee0c5","#f9b39d","#e77968","#b8443f"]
MOISTURE_COLORS=["#eaf3f7","#d6eff5","#99d3e1","#469dbf","#155c88"]
MOISTURE_LIMITS=[0,2.55]
CONTOUR_LEVELS=[[35,40,45,48],[1.5,2,2.4]]
LABEL_POSITIONS=[[(.65,1.1),(.95,1.65),(1.45,1.1),(1.85,1.65)],[(1.5,1.8),(1.8,1.25),(1.1,.75)]]
def palette(name: str, colors: list[str]) -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list(
        name, list(zip(PALETTE_POSITIONS, colors)), N=256)

def draw_fields(time_h: np.ndarray, radius_cm: np.ndarray,
                fields: list[np.ndarray], textfree: bool = False) -> plt.Figure:
    cmaps = [palette("q2_warm_coral", TEMPERATURE_COLORS),
             palette("shared_moisture_lake", MOISTURE_COLORS)]
    limits = [[float(fields[0].min()), float(fields[0].max())], MOISTURE_LIMITS]
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH_CM / 2.54, HEIGHT_IN),
                             layout="constrained")
    dt = float(time_h[1] - time_h[0])
    dr = float(radius_cm[1] - radius_cm[0])
    # Saved node values are pixel centers, so the image edges lie half a cell out.
    extent = [float(time_h[0] - dt / 2), float(time_h[-1] + dt / 2),
              float(radius_cm[0] - dr / 2), float(radius_cm[-1] + dr / 2)]
    for j, (ax, values, cmap, bounds) in enumerate(zip(axes, fields, cmaps, limits)):
        mesh = ax.imshow(values, origin="lower", aspect="auto", extent=extent,
                          interpolation="bilinear", interpolation_stage="data",
                          cmap=cmap, vmin=bounds[0], vmax=bounds[1],
                          rasterized=True)
        ax.set(xlim=(0, 3), ylim=(0, 2))
        contour_color = "#6e332c" if j == 0 else "#153e57"
        contours = ax.contour(time_h, radius_cm, values, levels=CONTOUR_LEVELS[j],
                              colors=[contour_color], linewidths=0.7)
        labels = ax.clabel(contours, inline=False, fontsize=7, fmt="%g",
                           manual=LABEL_POSITIONS[j])
        for label in labels:
            label.set_rotation(0)
            label.set_path_effects([
                path_effects.withStroke(linewidth=2.0, foreground="#ffffff", alpha=0.9)])
        cbar = fig.colorbar(mesh, ax=ax, orientation="horizontal", fraction=0.075,
                            pad=0.13, aspect=24)
        cbar.set_label(["温度 / °C", "干基含水率 / (kg/kg)"][j], fontsize=8)
        cbar.ax.tick_params(labelsize=8)
        if j == 1:
            cbar.set_ticks([0, 0.5, 1, 1.5, 2, 2.55],
                           labels=["0", "0.5", "1", "1.5", "2", "2.55"])
        ax.set(xlabel="时间 / h")
        ax.set_xticks([0, 1, 2, 3])
        ax.set_yticks([0, 0.5, 1, 1.5, 2])
        ax.set_ylabel("半\n径\ncm", rotation=0, ha="right", va="center", labelpad=10)
        ax.yaxis.label.set_multialignment("center")
        ax.yaxis.label.set_linespacing(1.05)
        ax.set_title(f"({'ab'[j]})", loc="left", pad=7, fontweight="bold")
        ax.grid(False)
    # Use the same output-resolution layout for the full and text-free versions.
    fig.set_dpi(300)
    fig.canvas.draw()
    fig.set_layout_engine(None)
    if textfree:
        # Keep every graphical element (including contours, ticks, axes and
        # colorbars) in place; hide only the text after the layout is frozen.
        for text in fig.findobj(Text):
            text.set_visible(False)
    return fig
def render():
    with np.load(DATA/"q2_fields.npz", allow_pickle=False) as z:
        fig=draw_fields(z["time_s"]/3600,z["radius_m"]*100,[z[k].T for k in ["temperature_C","moisture_kg_kg"]])
    export(fig,"fig04_q2_fields_sample")
