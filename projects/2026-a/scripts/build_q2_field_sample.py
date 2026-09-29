"""Build the Q2 field redesign sample from existing, unrounded results.

No solver is called. This sample does not replace the accepted v1 figure.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as path_effects
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.text import Text
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/paper_figures/redesign_v3"
SOURCE_REL = "output/Q2/run_n10240_startsafe.npz"
SOURCE_SHA256 = "79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b"
WIDTH_CM = 15.8
HEIGHT_IN = 3.2
PALETTE_POSITIONS = [0.0, 0.25, 0.5, 0.75, 1.0]
TEMPERATURE_COLORS = ["#fffaf1", "#fee0c5", "#f9b39d", "#e77968", "#b8443f"]
MOISTURE_COLORS = ["#eaf3f7", "#d6eff5", "#99d3e1", "#469dbf", "#155c88"]
MOISTURE_LIMITS = [0.0, 2.55]
CONTOUR_LEVELS = [[35.0, 40.0, 45.0, 48.0], [1.5, 2.0, 2.4]]
# Labels are placed on the nearest genuine contour; these are placement hints.
LABEL_POSITIONS = [
    [(0.65, 1.1), (0.95, 1.65), (1.45, 1.1), (1.85, 1.65)],
    [(1.5, 1.8), (1.8, 1.25), (1.1, 0.75)],
]
FONT = Path("C:/Windows/Fonts/msyh.ttc")


def identity(path: Path) -> dict:
    return {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def configure_style() -> None:
    font_manager.fontManager.addfont(str(FONT))
    plt.rcParams.update({
        "font.family": font_manager.FontProperties(fname=str(FONT)).get_name(),
        "font.size": 9,
        "axes.labelsize": 9,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.titlesize": 9,
        "axes.linewidth": 0.85,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "axes.unicode_minus": False,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
        "figure.facecolor": "white",
        "savefig.facecolor": "white",
    })


def palette(name: str, colors: list[str]) -> LinearSegmentedColormap:
    return LinearSegmentedColormap.from_list(
        name, list(zip(PALETTE_POSITIONS, colors)), N=256)


def load_fields() -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    path = ROOT / SOURCE_REL
    if identity(path)["sha256"] != SOURCE_SHA256:
        raise ValueError("The saved Q2 result identity has changed.")
    with np.load(path) as data:
        mask = (data["time_s"] >= 0) & (data["time_s"] <= 10800)
        time_h = data["time_s"][mask] / 3600
        radius_cm = data["radius_m"] * 100
        fields = [data[name][mask].T.copy()
                  for name in ["temperature_C", "moisture_kg_kg"]]
    assert all(v.shape == (21, 10801) for v in fields)
    assert np.allclose(np.diff(time_h) * 3600, 1)
    assert np.allclose(radius_cm, np.linspace(0, 2, 21))
    assert all(np.isfinite(v).all() for v in fields)
    return time_h, radius_cm, fields


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


def main() -> None:
    configure_style()
    time_h, radius_cm, fields = load_fields()
    OUT.mkdir(parents=True, exist_ok=True)
    fig = draw_fields(time_h, radius_cm, fields)
    outputs = {}
    for ext in ["png", "pdf", "svg"]:
        path = OUT / f"fig04_q2_fields_sample.{ext}"
        kwargs = {"metadata": {"Creator": "Project Q2 field sample generator"}} if ext == "pdf" else {}
        fig.savefig(path, dpi=300, **kwargs)
        outputs[ext] = {"file": path.name, **identity(path)}
    plt.close(fig)
    textfree = draw_fields(time_h, radius_cm, fields, textfree=True)
    path = OUT / "fig04_q2_fields_textfree.png"
    textfree.savefig(path, dpi=300)
    plt.close(textfree)
    outputs["textfree_png"] = {"file": path.name, **identity(path),
                                "purpose": "same composition with text hidden; contours, axes, ticks and colorbars retained"}
    metadata = {
        "schema_version": "1.0",
        "role": "Q2 visual redesign sample for team review; v1 not replaced",
        "title": "Q2前三小时温度与含水率的时空分布",
        "caption": "横轴为时间，纵轴为实际半径；(a)温度，(b)干基含水率。色场来自前三小时逐秒保存的21个规定半径值，仅在相邻保存点之间作数据值的双线性显示内插，再映射为颜色。细线为标注数值对应的等值线，由同一组已有网格数据在线性单元内定位。显示内插与等值线仅辅助读图，不代表新增细网格求解精度或物理阈值。含水率色标固定为0–2.55 kg/kg，便于与其他含水率图保持同值同色。",
        "source": {"path": SOURCE_REL, **identity(ROOT / SOURCE_REL)},
        "generator": {"path": "scripts/build_q2_field_sample.py", **identity(Path(__file__))},
        "data": {
            "time_s": [0, 10800], "time_count": len(time_h), "time_stride_s": 1,
            "radius_cm": radius_cm.tolist(), "field_shape_radius_by_time": [21, 10801],
            "temperature_range_C": [float(fields[0].min()), float(fields[0].max())],
            "moisture_range_kg_kg": [float(fields[1].min()), float(fields[1].max())],
            "end_center_surface": {
                "temperature_C": fields[0][[0, -1], -1].tolist(),
                "moisture_kg_kg": fields[1][[0, -1], -1].tolist()},
            "data_change": "saved arrays unchanged; linear display interpolation only; no solver run or fitted field",
        },
        "color_encoding": {
            "node_positions": PALETTE_POSITIONS,
            "temperature_hex": TEMPERATURE_COLORS,
            "temperature_limits_C": [float(fields[0].min()), float(fields[0].max())],
            "moisture_hex": MOISTURE_COLORS,
            "moisture_limits_kg_kg": MOISTURE_LIMITS,
            "normalization": "linear in each physical quantity",
            "colormap_generation": "LinearSegmentedColormap with 256 entries and the listed equally spaced sRGB nodes",
            "shared_semantics": "Use the exact moisture nodes and 0–2.55 limits for Q4 to preserve equal-value colors.",
        },
        "display": {
            "base_field": "imshow interpolation=bilinear, interpolation_stage=data; scalar values interpolated before color mapping; axes and contours vector",
            "image_extent_time_h_radius_cm": [
                float(time_h[0] - (time_h[1] - time_h[0]) / 2),
                float(time_h[-1] + (time_h[1] - time_h[0]) / 2),
                float(radius_cm[0] - (radius_cm[1] - radius_cm[0]) / 2),
                float(radius_cm[-1] + (radius_cm[1] - radius_cm[0]) / 2)],
            "image_origin": "lower; saved nodes are cell centers; half-cell outer extent clipped to t=0–3 h and r=0–2 cm",
            "temperature_contours_C": CONTOUR_LEVELS[0],
            "moisture_contours_kg_kg": CONTOUR_LEVELS[1],
            "contour_interpolation": "linear crossing locations in adjacent saved-data grid cells; no smoothing",
            "contour_linewidth_pt": 0.7,
            "contour_labels": "upright; placement hints snapped onto actual contours",
            "width_cm": WIDTH_CM, "height_cm": HEIGHT_IN * 2.54, "png_dpi": 300,
            "textfree_height_cm": HEIGHT_IN * 2.54,
            "textfree": "identical figure layout frozen before hiding all Text artists; no graphical elements removed",
        },
        "outputs": outputs,
        "claim_boundary": "Existing Q2 model results visualized over 0–3 h. No solver run, new physical claim, or promotion into v1/teammate manuscript.",
    }
    (OUT / "q2_sample_sources.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Generated Q2 sample only; existing figures and manuscript files were not changed.")


if __name__ == "__main__":
    main()
