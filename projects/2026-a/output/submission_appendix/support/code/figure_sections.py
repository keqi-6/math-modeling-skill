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

PALETTE=("#eaf3f7","#d6eff5","#99d3e1","#469dbf","#155c88")
THRESHOLD=.15
THRESHOLD_COLOR="#66395F"
FIELD_LIMITS=(0,2.55)
AXIS_LIMIT_CM=2.2
DISPLAY_RINGS=512
WIDTH_CM,HEIGHT_CM=15.8,11.5
def grey(color):
    """Equal-RGB tone with the same Rec.709 luminance as the input colour."""
    rgb = np.asarray(to_rgb(color))
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = float(linear @ np.array([0.2126, 0.7152, 0.0722]))
    tone = 12.92 * lum if lum <= 0.0031308 else 1.055 * lum ** (1 / 2.4) - 0.055
    return (tone, tone, tone)

def make_figure(xi, frames, *, grayscale=False):
    colors = [grey(c) for c in PALETTE] if grayscale else list(PALETTE)
    cmap = LinearSegmentedColormap.from_list("q4_fixed_moisture", colors, N=1024)
    norm = Normalize(*FIELD_LIMITS, clip=False)
    threshold_color = grey(THRESHOLD_COLOR) if grayscale else THRESHOLD_COLOR
    rim_color = grey("#47525A") if grayscale else "#47525A"
    fig = plt.figure(figsize=(WIDTH_CM / 2.54, HEIGHT_CM / 2.54))
    panel_width = 0.27
    panel_height = panel_width * WIDTH_CM / HEIGHT_CM
    # Identical square axes enforce a common centimetre scale; no autoscaling.
    for i, frame in enumerate(frames):
        row, col = divmod(i, 3)
        left = (0.055, 0.365, 0.675)[col]
        bottom = (0.570, 0.145)[row]
        ax = fig.add_axes((left, bottom, panel_width, panel_height), facecolor="none")
        ax.set(xlim=(-AXIS_LIMIT_CM, AXIS_LIMIT_CM), ylim=(-AXIS_LIMIT_CM, AXIS_LIMIT_CM))
        ax.set_aspect("equal", adjustable="box")
        ax.set_axis_off()
        radius = frame["radius_cm"]
        field = frame["moisture"]
        # Draw nested filled disks from outside inward. The visible thin bands
        # sample the retained 10241-node radial field at their midpoints.
        # All disks and contours remain vector primitives in PDF and SVG.
        bands = 1 if np.ptp(field) == 0 else DISPLAY_RINGS
        edges = np.linspace(0, radius, bands + 1)
        middle = (edges[:-1] + edges[1:]) / 2
        values = np.interp(middle / radius, xi, field)
        for edge, value in zip(edges[:0:-1], values[::-1]):
            ax.add_patch(Circle((0, 0), float(edge), facecolor=cmap(norm(value)),
                                edgecolor="none", linewidth=0, antialiased=False))
        ax.add_patch(Circle((0, 0), radius, fill=False, edgecolor=rim_color, linewidth=0.95))
        if frame["threshold_radius_cm"] is not None:
            ax.add_patch(Circle((0, 0), frame["threshold_radius_cm"], fill=False,
                                edgecolor=threshold_color, linewidth=1.15,
                                linestyle=(0, (3.2, 1.6))))
        time_label = f"{frame['time_s'] / 3600:g} h" if i != 5 else f"{frame['time_s']/3600:.4f} h"
        header = f"({chr(97 + i)}) {time_label}  " + rf"$R={radius:.3f}\,\mathrm{{cm}}$"
        ax.text(0.5, 1.030, header, transform=ax.transAxes,
                ha="center", va="bottom", fontsize=9)

    # One contour key is sufficient; the solid rim is the actual material edge.
    key = Line2D([0], [0], color=threshold_color, linewidth=1.15, linestyle=(0, (3.2, 1.6)))
    fig.legend([key], [r"$C=0.15$"], loc="center", bbox_to_anchor=(0.5, 0.152),
               frameon=False, fontsize=9, handlelength=2.7, handletextpad=0.7)
    bar_ax = fig.add_axes((0.20, 0.098, 0.60, 0.024), facecolor="none")
    cb = fig.colorbar(ScalarMappable(norm=norm, cmap=cmap), cax=bar_ax, orientation="horizontal",
                      ticks=[0, 0.5, 1.0, 1.5, 2.0, 2.55])
    cb.ax.tick_params(labelsize=8, length=2.2, width=0.65, pad=2)
    cb.ax.set_xticklabels(["0", "0.5", "1.0", "1.5", "2.0", "2.55"])
    cb.outline.set_linewidth(0.65)
    cb.set_label("干基含水率 / (kg/kg)", fontsize=9, labelpad=3)
    return fig
def render():
    frames=[]
    with np.load(DATA/"q4_sections.npz",allow_pickle=False) as z:
        xi=z["mesh_xi"]
        for t,R,C in zip(z["snapshot_time_s"],z["snapshot_radius_m"],z["moisture_snapshots"]):
            assert np.isfinite(C).all() and np.max(np.diff(C))<1e-12
            radius=100*float(R)
            level=float(np.interp(.15,C[::-1],(radius*xi)[::-1])) if C.min()<.15<C.max() else None
            frames.append({"time_s":int(t),"radius_cm":radius,"moisture":C,"threshold_radius_cm":level})
        fig=make_figure(xi,frames)
    export(fig,"fig07_q4_sections_sample",dpi=360,transparent=True)
