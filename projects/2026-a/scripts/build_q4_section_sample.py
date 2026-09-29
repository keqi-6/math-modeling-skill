"""Render a Q4 section-sequence candidate from retained solution snapshots.

This script reads existing results only. It does not import or run a solver.
All six sections use one physical scale and one linear moisture colour scale.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.cm import ScalarMappable
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.text import Text
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/paper_figures/redesign_v3"
SOURCE = ROOT / "output/Q4/run_n10240-v1-20260911.npz"
META = SOURCE.with_suffix(".json")
EXPECTED_SOURCE_SHA = "4045f74c14062b4554aa2aa752797aa1f1dedf28d84f956513da924d5f8a6b92"
TIMES = (0, 21600, 64800, 129600, 172800, 183949)
PALETTE = ("#eaf3f7", "#d6eff5", "#99d3e1", "#469dbf", "#155c88")
THRESHOLD = 0.15
THRESHOLD_COLOR = "#66395F"
FIELD_LIMITS = (0.0, 2.55)
AXIS_LIMIT_CM = 2.20
DISPLAY_RINGS = 512
WIDTH_CM, HEIGHT_CM = 15.8, 11.5
DPI = 360


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def grey(color):
    """Equal-RGB tone with the same Rec.709 luminance as the input colour."""
    rgb = np.asarray(to_rgb(color))
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = float(linear @ np.array([0.2126, 0.7152, 0.0722]))
    tone = 12.92 * lum if lum <= 0.0031308 else 1.055 * lum ** (1 / 2.4) - 0.055
    return (tone, tone, tone)


def load_snapshots():
    if digest(SOURCE) != EXPECTED_SOURCE_SHA:
        raise ValueError("The retained Q4 source identity has changed.")
    metadata = json.loads(META.read_text(encoding="utf-8-sig"))
    if metadata["grid_n"] != 10240 or metadata["n_end"] != TIMES[-1]:
        raise ValueError("Unexpected mesh or reported endpoint.")
    frames = []
    with np.load(SOURCE, allow_pickle=False) as z:
        xi = z["mesh_xi"].copy()
        times = z["snapshot_time_s"]
        radii = z["snapshot_radius_m"]
        fields = z["moisture_snapshots"]
        if xi.shape != (10241,) or not np.all(np.diff(xi) > 0):
            raise ValueError("Invalid material-coordinate axis.")
        if xi[0] != 0 or xi[-1] != 1 or fields.shape != (len(times), len(xi)):
            raise ValueError("Incomplete full-mesh snapshots.")
        for second in TIMES:
            indices = np.flatnonzero(times == second)
            if len(indices) != 1:
                raise ValueError(f"Missing or duplicate snapshot at {second} s.")
            i = int(indices[0])
            c = fields[i].copy()
            radius_cm = float(100 * radii[i])
            if not np.isfinite(c).all() or not (0 < c.min() <= c.max() <= FIELD_LIMITS[1]):
                raise ValueError("Moisture outside the declared display range.")
            # The selected snapshots are radially nonincreasing. Check this
            # property before using the inverse interpolation for a contour.
            if np.max(np.diff(c)) > 1e-12:
                raise ValueError("Selected snapshot is not radially nonincreasing.")
            threshold_radius = None
            if c.min() < THRESHOLD < c.max():
                threshold_radius = float(np.interp(THRESHOLD, c[::-1], (radius_cm * xi)[::-1]))
                if not 0 < threshold_radius < radius_cm:
                    raise ValueError("A threshold contour must be strictly internal.")
            frames.append(dict(time_s=second, snapshot_index=i, radius_cm=radius_cm,
                               moisture=c, threshold_radius_cm=threshold_radius,
                               all_nodes_below=bool(c.max() < THRESHOLD),
                               center=float(c[0]), surface=float(c[-1]),
                               minimum=float(c.min()), maximum=float(c.max()),
                               max_radial_increase=float(np.max(np.diff(c)))))
    if not frames[-1]["all_nodes_below"] or frames[-1]["threshold_radius_cm"] is not None:
        raise ValueError("The last section must be the retained strict endpoint.")
    return xi, frames, metadata


def configure():
    font = Path("C:/Windows/Fonts/msyh.ttc")
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({
        "font.family": font_manager.FontProperties(fname=str(font)).get_name(),
        "font.size": 9, "mathtext.fontset": "stix", "axes.unicode_minus": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.facecolor": "none", "savefig.facecolor": "none",
    })


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
        time_label = f"{frame['time_s'] / 3600:g} h" if i != 5 else "51.0969 h"
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


def save_outputs(xi, frames):
    OUT.mkdir(parents=True, exist_ok=True)
    fig = make_figure(xi, frames)
    outputs = {}
    stem = "fig07_q4_sections_sample"
    for ext in ("pdf", "png", "svg"):
        path = OUT / f"{stem}.{ext}"
        kwargs = {"metadata": {"Creator": "Q4 retained-snapshot section renderer"}} if ext == "pdf" else {}
        fig.savefig(path, dpi=DPI, transparent=True, **kwargs)
        outputs[ext] = dict(path=path.relative_to(ROOT).as_posix(), sha256=digest(path), bytes=path.stat().st_size)
    for item in fig.findobj(match=Text):
        item.set_visible(False)
    textfree = OUT / "fig07_q4_sections_textfree.png"
    fig.savefig(textfree, dpi=DPI, transparent=True)
    outputs["textfree_png"] = dict(path=textfree.relative_to(ROOT).as_posix(), sha256=digest(textfree), bytes=textfree.stat().st_size)
    plt.close(fig)
    audit_dir = Path(os.environ.get("TEMP", str(OUT))) / "cumcm-q4-sections-sample-20260911"
    audit_dir.mkdir(parents=True, exist_ok=True)
    grey_path = audit_dir / "fig07_q4_sections_gray.png"
    grey_fig = make_figure(xi, frames, grayscale=True)
    grey_fig.savefig(grey_path, dpi=DPI, transparent=True)
    plt.close(grey_fig)
    return outputs, grey_path


def main():
    configure()
    xi, frames, metadata = load_snapshots()
    outputs, grey_path = save_outputs(xi, frames)
    source_note = {
        "schema_version": "1.0", "status": "candidate_sample_not_manuscript_replacement",
        "source_npz": {"path": SOURCE.relative_to(ROOT).as_posix(), "sha256": digest(SOURCE)},
        "source_metadata": {"path": META.relative_to(ROOT).as_posix(), "sha256": digest(META)},
        "generator": {"path": Path(__file__).relative_to(ROOT).as_posix(), "sha256": digest(Path(__file__))},
        "source_arrays": ["mesh_xi", "snapshot_time_s", "snapshot_radius_m", "moisture_snapshots"],
        "source_grid_n": int(metadata["grid_n"]), "nodes_per_snapshot": len(xi),
        "frames": [{k: v for k, v in f.items() if k != "moisture"} for f in frames],
        "mapping": {"physical_radius_cm": "r_cm = 100 * snapshot_radius_m * mesh_xi",
                    "planar_field": "C(x,y,t)=U(sqrt(x^2+y^2)/R(t),t) inside the current disk",
                    "display": "512 midpoint-coloured nested vector disks from the retained radial field; 1 disk for the uniform initial state",
                    "interpolation": "piecewise linear interpolation in the saved material coordinate; no PDE recomputation",
                    "outside_current_radius": "transparent; no zero-valued field outside the material",
                    "threshold_contour": "one interpolated radial level set only if min(C)<0.15<max(C); no contour at the strict endpoint",
                    "no_mass_interpretation": "disk area and colour are not total water mass; this is a radial model rotated in the cross-section, not a 2D or 3D solve"},
        "design": {"width_cm": WIDTH_CM, "height_cm": HEIGHT_CM, "dpi": DPI,
                   "layout": "2 rows by 3 columns, equal physical scale",
                   "each_axis_limits_cm": [-AXIS_LIMIT_CM, AXIS_LIMIT_CM],
                   "colour_limits_kg_kg": FIELD_LIMITS, "colour_scale": "linear and identical for all frames",
                   "colour_nodes": [{"value": float(v), "colour": c} for v, c in zip(np.linspace(*FIELD_LIMITS, len(PALETTE)), PALETTE)],
                   "threshold_line": {"value_kg_kg": THRESHOLD, "colour": THRESHOLD_COLOR, "style": "dashed"},
                   "descriptive_titles": False, "initial_reference_circle": False,
                   "intended_textfree_reading": "the actual disk shrinks early; the internal threshold ring contracts later while the outside radius is nearly fixed"},
        "suggested_caption": "同尺度的药材含水率截面序列。各截面由问题四主轨迹的完整材料节点场按r=R(t)xi旋转绘制，统一使用0至2.55 kg/kg线性色标，圆外透明。实线为实际外表面；虚线仅表示C=0.15的内部等值线，不是物理相界面。末幅取183949 s，全部节点未舍入值均低于阈值。图中面积不表示水质量。",
        "outputs": outputs,
        "audit": {"grayscale_preview": str(grey_path), "grayscale_conversion": "rendered anew using equal-RGB colours with matched Rec.709 luminance",
                  "numerical_assertions": "passed", "visual_review": "pending parent review; colour/textfree/gray previews produced"},
    }
    manifest = OUT / "q4_sample_sources.json"
    manifest.write_text(json.dumps(source_note, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"outputs": outputs, "source_note": str(manifest), "grayscale_preview": str(grey_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
