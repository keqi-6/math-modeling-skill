"""Internal visual sample: circular Q2 sections from the full main-run mesh.

The external screenshot suggests a small-multiple layout only. No values,
features or physical claims are imported from it. This script does not update
the briefs, selected figures, official results or submission packages.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.patches import Circle
from matplotlib.text import Text
import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "output/Q2/run_n10240_startsafe.npz"
DEST = ROOT / "planning/internal_visual_reference_20260912"
STEM = "section_sample"
TIMES = np.array([0.0, 1800.0, 5400.0, 10800.0])


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    with np.load(SOURCE) as source:
        snapshot_times = source["snapshot_time_s"]
        positions = [int(np.flatnonzero(snapshot_times == time)[0]) for time in TIMES]
        radius = source["mesh_radius_m"].copy()
        temperature = source["temperature_snapshots"][positions].copy()
        moisture = source["moisture_snapshots"][positions].copy()

    assert radius.size == 10241 and radius[0] == 0 and radius[-1] == 0.02
    assert np.all(np.diff(radius) > 0)
    assert temperature.shape == moisture.shape == (4, 10241)
    assert np.isfinite(temperature).all() and np.isfinite(moisture).all()
    assert np.ptp(temperature[0]) == 0.0 and np.ptp(moisture[0]) == 0.0
    assert np.all((temperature >= 28) & (temperature <= 50))
    assert np.all((moisture >= 0) & (moisture <= 2.55))

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "Arial"],
        "mathtext.fontset": "stix",
        "font.size": 11,
        "axes.unicode_minus": False,
        "svg.fonttype": "path",
        "savefig.facecolor": "white",
    })

    thermal = LinearSegmentedColormap.from_list(
        "warm_coral", ["#fff4df", "#fbdcb2", "#f6af88", "#e87b62", "#b84546"]
    )
    water = LinearSegmentedColormap.from_list(
        "lake_blue", ["#f5fbfb", "#cce8e8", "#86c9d0", "#3a9caf", "#216a91", "#183e67"]
    )
    schemes = [
        (temperature, thermal, Normalize(28, 50), [35, 40, 45], [28, 35, 40, 45, 50]),
        (moisture, water, Normalize(0, 2.55), [1.5, 2.0, 2.4], [0, 0.5, 1, 1.5, 2, 2.55]),
    ]

    # Full double-precision radial profiles are linearly evaluated at each pixel.
    # This is a display mapping, not a new spatial solve or smoothing of results.
    pixels = 801
    coordinates = np.linspace(-radius[-1], radius[-1], pixels)
    x, y = np.meshgrid(coordinates, coordinates)
    radial_distance = np.hypot(x, y)
    mask = radial_distance > radius[-1]

    fig = plt.figure(figsize=(11.3, 6.0), facecolor="white")
    grid = fig.add_gridspec(
        2, 5, left=0.105, right=0.92, bottom=0.13, top=0.885,
        width_ratios=[1, 1, 1, 1, 0.075], wspace=0.14, hspace=0.29,
    )
    image_extents = [-2, 2, -2, 2]
    section_axes = []
    isoline_counts = []

    for row, (profiles, cmap, norm, contour_levels, ticks) in enumerate(schemes):
        row_counts = []
        for column in range(4):
            axis = fig.add_subplot(grid[row, column])
            section_axes.append(axis)
            display = np.interp(radial_distance, radius, profiles[column])
            display = np.ma.array(display, mask=mask)
            image = axis.imshow(
                display, origin="lower", extent=image_extents,
                cmap=cmap, norm=norm, interpolation="nearest", rasterized=True,
            )
            # Clip the field at the exact circular boundary, which stays fixed.
            boundary = Circle((0, 0), 2, fill=False, edgecolor="#6f7e85", linewidth=0.9)
            axis.add_patch(boundary)
            image.set_clip_path(boundary)
            levels = [level for level in contour_levels
                      if profiles[column].min() < level < profiles[column].max()]
            row_counts.append(len(levels))
            if levels:
                axis.contour(
                    coordinates * 100, coordinates * 100, display,
                    levels=levels, colors="white", linewidths=0.8, alpha=0.72,
                )
            axis.set(xlim=(-2.08, 2.08), ylim=(-2.08, 2.08), aspect="equal")
            axis.set_axis_off()
            if row == 0:
                hours = TIMES[column] / 3600
                axis.text(0.5, 1.12, f"{hours:g} h", transform=axis.transAxes,
                          ha="center", va="bottom", fontsize=12, color="#293b47")
        isoline_counts.append(row_counts)
        color_axis = fig.add_subplot(grid[row, 4])
        bar = fig.colorbar(image, cax=color_axis, ticks=ticks)
        bar.outline.set_visible(False)
        bar.ax.tick_params(length=2.5, width=0.65, labelsize=10, colors="#42515b")
        bar.ax.set_yticklabels([f"{tick:g}" for tick in ticks])
        color_axis.set_position([
            color_axis.get_position().x0,
            color_axis.get_position().y0 + 0.025,
            color_axis.get_position().width,
            color_axis.get_position().height - 0.05,
        ])

    fig.text(0.064, 0.706, "温度\n" + r"$\theta$ (°C)", ha="center", va="center",
             linespacing=1.75, fontsize=11, color="#7c3438")
    fig.text(0.061, 0.293, "含水率\n" + r"$C$ (kg/kg)", ha="center", va="center",
             linespacing=1.75, fontsize=11, color="#23516d")

    # One geometric ruler conveys the physical radius for all equal-scale disks.
    ruler = fig.add_axes([0.135, 0.041, 0.122, 0.055])
    ruler.plot([0, 2], [0, 0], color="#5e6c76", lw=1.05)
    for tick in [0, 1, 2]:
        ruler.plot([tick, tick], [-0.1, 0.1], color="#5e6c76", lw=1.05)
        ruler.text(tick, -0.19, str(tick), ha="center", va="top", fontsize=9, color="#42515b")
    ruler.text(2.22, -0.02, "cm", ha="left", va="center", fontsize=10, color="#42515b")
    ruler.set(xlim=(-0.08, 2.7), ylim=(-0.45, 0.25))
    ruler.set_axis_off()

    png = DEST / f"{STEM}.png"
    svg = DEST / f"{STEM}.svg"
    fig.savefig(png, dpi=240)
    fig.savefig(svg)
    for text in fig.findobj(match=Text):
        text.set_visible(False)
    fig.savefig(DEST / f"{STEM}_no_text.png", dpi=160)
    plt.close(fig)
    with Image.open(png) as rendered:
        rendered.convert("L").save(DEST / f"{STEM}_grayscale.png")
        rendered.resize((1130, 600), Image.Resampling.LANCZOS).save(
            DEST / f"{STEM}_page_width.png")

    np.savez_compressed(
        DEST / f"{STEM}_profiles.npz", time_s=TIMES, radius_m=radius,
        temperature_C=temperature, moisture_kg_kg=moisture,
    )
    metadata = {
        "status": "internal_reference_only_not_selected_for_briefs_or_submission",
        "data_driven_visual": True,
        "information_task": "Compare thermal equalization with persistent radial moisture gradients over the first 3 h.",
        "source": {"path": SOURCE.relative_to(ROOT).as_posix(), "sha256": sha256(SOURCE)},
        "generator": {"path": Path(__file__).relative_to(ROOT).as_posix(),
                      "sha256": sha256(Path(__file__))},
        "external_reference_use": "Small-multiple circular-section layout only; no traced values, boundary features, or conclusions.",
        "time_s": TIMES.tolist(),
        "snapshot_selection": "Exact stored snapshots; no time interpolation.",
        "radius_m": float(radius[-1]),
        "nodes_per_snapshot": int(radius.size),
        "retained_input_precision": "All 10,241 radial nodes in float64 for each selected snapshot.",
        "spatial_display_mapping": {
            "grid_pixels": [pixels, pixels],
            "method": "np.interp(sqrt(x*x+y*y), mesh_radius_m, full_profile)",
            "outside_radius": "masked and clipped at the circular boundary",
            "shading": "Continuous fixed-range color scale shared across time within each row.",
            "svg_note": "Dense numerical color fields are embedded rasters; outlines, isolines, rulers and labels remain vector paths.",
        },
        "row_units": ["degree_Celsius", "kg_water/kg_dry_matter"],
        "color_ranges": {"temperature_C": [28, 50], "moisture_kg_kg": [0, 2.55]},
        "isoline_levels": {"temperature_C": [35, 40, 45], "moisture_kg_kg": [1.5, 2, 2.4]},
        "isoline_meaning": "Fixed-value contour lines, not a separately modeled physical drying front.",
        "isoline_counts_per_time": {"temperature": isoline_counts[0], "moisture": isoline_counts[1]},
        "physical_geometry": "Fixed-radius cross section only; no axial variation, 3D thickness or shrinkage is implied.",
        "checks": {
            "initial_temperature_uniform": bool(np.ptp(temperature[0]) == 0.0),
            "initial_moisture_uniform": bool(np.ptp(moisture[0]) == 0.0),
            "no_source_clipping_by_color_limits": True,
            "same_geometric_scale_all_eight_sections": True,
            "temperature_center_surface_C": temperature[:, [0, -1]].tolist(),
            "moisture_center_surface_kg_kg": moisture[:, [0, -1]].tolist(),
            "temperature_radial_range_C": np.ptp(temperature, axis=1).tolist(),
            "moisture_radial_range_kg_kg": np.ptp(moisture, axis=1).tolist(),
        },
        "review": {
            "rendered_outputs": [f"{STEM}.png", f"{STEM}_no_text.png", f"{STEM}_grayscale.png", f"{STEM}_page_width.png"],
            "embedding": "Not embedded in any brief or formal package.",
            "human_review": "Pending user review as an internal visual sample.",
        },
        "outputs": {path.name: {"sha256": sha256(path), "bytes": path.stat().st_size}
                    for path in sorted(DEST.glob(f"{STEM}*"))
                    if path.is_file() and path.suffix != ".json"},
    }
    (DEST / f"{STEM}_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"png": str(png), "svg": str(svg),
                      "metadata": str(DEST / f"{STEM}_metadata.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
