"""Plot Q1 mesh agreement and its startup-time distribution without solving.

The default run extracts an auditable, compact JSON from the saved Q1 arrays.
The same figure can then be reproduced using only that JSON:
    python build_q1_startup_figure.py --data fig08_q1_startup_precision_data.json --output figures
Requires NumPy, Matplotlib and an installed Chinese sans-serif font.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.text import Text
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
NAME = "fig08_q1_startup_precision"
DEFAULT_OUT = ROOT / "output/paper_figures/verification_refresh_20260912"
BLUE, ORANGE, GRAY = "#0072BD", "#D95319", "#666666"
TARGETS = {"temperature_C": 2e-5, "moisture_kg_kg": 2e-5}
GRID_COUNTS = [160, 320, 640, 1280, 2560, 5120]
CAPTION = (
    "问题1网格加密及启动阶段的数值差异。(a)温度与含水率的相邻网格最大差，"
    "分别除以各自2×10⁻⁵的检验目标，所得比值无量纲；最大值遍历1～1800 s的"
    "21个规定半径，虚线表示比值1。(b)N=2560与5120的含水率差在每秒21个"
    "规定半径上的最大值，虚线为2×10⁻⁵ kg/kg。保留全部逐秒值，未拟合或平滑；"
    "两个面板的横纵轴均为对数尺度。"
)


def identity(path: Path, label: str | None = None) -> dict:
    return {"path": label or path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size}


def extract_data() -> dict:
    report_path = ROOT / "output/Q1/verification_report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report["passed"]:
        raise ValueError("The source Q1 verification report is not passed.")
    references = {item["name"]: item for item in report["checks"]}
    sources = [identity(report_path, "output/Q1/verification_report.json")]
    arrays = []
    for n in GRID_COUNTS:
        path = ROOT / f"output/Q1/run_n{n}.npz"
        sources.append(identity(path, f"output/Q1/run_n{n}.npz"))
        with np.load(path) as z:
            np.testing.assert_array_equal(z["time_s"], np.arange(1801))
            np.testing.assert_allclose(z["radius_m"], np.arange(21)*.001,
                                       rtol=0, atol=2e-16)
            arrays.append({field: z[field].copy() for field in TARGETS})
    maxima = {field: [] for field in TARGETS}
    peak_locations = {field: [] for field in TARGETS}
    maximum_reference_difference = 0.
    for index, (coarse, fine) in enumerate(zip(arrays[:-1], arrays[1:])):
        for field, prefix in [("temperature_C", "temperature"),
                              ("moisture_kg_kg", "moisture")]:
            difference = np.abs(fine[field][1:]-coarse[field][1:])
            if not np.isfinite(difference).all():
                raise ValueError("Nonfinite saved-array difference.")
            ti, ri = np.unravel_index(np.argmax(difference), difference.shape)
            value = float(difference[ti, ri])
            expected = references[f"{prefix}_spatial_differences_decrease"]["comparisons"][index]
            if (expected["coarse_n"], expected["fine_n"]) != tuple(GRID_COUNTS[index:index+2]):
                raise ValueError("The report mesh-pair order differs.")
            np.testing.assert_allclose(value, expected["max_abs"], rtol=1e-13, atol=0)
            np.testing.assert_allclose([ti+1, ri*.001],
                                       [expected["time_s"], expected["radius_m"]],
                                       rtol=0, atol=2e-16)
            maximum_reference_difference = max(maximum_reference_difference,
                                               abs(value-expected["max_abs"]))
            maxima[field].append(value)
            peak_locations[field].append({"time_s": int(ti+1), "radius_m": float(ri*.001)})
    envelope = np.max(np.abs(arrays[-1]["moisture_kg_kg"][1:]
                            -arrays[-2]["moisture_kg_kg"][1:]), axis=1)
    return {
        "schema_version": "q1-startup-precision-1.0",
        "data_driven_visual": True,
        "original_sources": sources,
        "coarse_n": GRID_COUNTS[:-1], "fine_n": GRID_COUNTS[1:],
        "maximum_absolute_difference": maxima,
        "maximum_locations": peak_locations,
        "targets": {"temperature_C": {"value": TARGETS["temperature_C"], "unit": "degC"},
                    "moisture_kg_kg": {"value": TARGETS["moisture_kg_kg"], "unit": "kg/kg"}},
        "time_s": list(range(1, 1801)),
        "finest_pair_moisture_maximum_over_radii_kg_kg": envelope.tolist(),
        "sampling": {"time_s_inclusive": [1, 1800], "time_stride_s": 1,
                     "radii_m": (np.arange(21)*.001).tolist(),
                     "finest_mesh_pair": [2560, 5120]},
        "transformations": [
            "Recompute absolute fine-minus-coarse differences from unrounded saved arrays.",
            "Left: maximum over all 1800 times and 21 required radii; divide each field by its own target.",
            "Right: at every saved second, maximize moisture difference over the 21 required radii.",
            "Exclude t=0, where both differences are zero, to use a logarithmic time axis.",
            "Connect consecutive saved values; no fitting, smoothing, decimation or solver execution."],
        "checks": {"all_ten_mesh_maxima_and_locations_match_existing_report": True,
                   "maximum_difference_from_report": maximum_reference_difference},
        "claim_boundary": (
            "Differences between numerical solutions, not a continuous-solution error bound. "
            "The 1 s surface peak concerns moisture. The final temperature mesh difference peaks at 307 s. "
            "No information about subsecond error maxima or experimental prediction accuracy is inferred."),
    }


def validate_data(data: dict) -> None:
    if data["schema_version"] != "q1-startup-precision-1.0":
        raise ValueError("Unsupported compact-data schema.")
    np.testing.assert_array_equal(data["coarse_n"], GRID_COUNTS[:-1])
    np.testing.assert_array_equal(data["fine_n"], GRID_COUNTS[1:])
    np.testing.assert_array_equal(data["time_s"], np.arange(1, 1801))
    for field in TARGETS:
        values = np.asarray(data["maximum_absolute_difference"][field])
        if values.shape != (5,) or not np.isfinite(values).all() or not (values > 0).all():
            raise ValueError("Invalid maximum-difference series.")
        if data["targets"][field]["value"] != TARGETS[field]:
            raise ValueError("The compact-data target differs from the Q1 contract.")
    envelope = np.asarray(data["finest_pair_moisture_maximum_over_radii_kg_kg"])
    if envelope.shape != (1800,) or not np.isfinite(envelope).all() or not (envelope >= 0).all():
        raise ValueError("Invalid per-second moisture difference.")
    np.testing.assert_allclose(envelope.max(),
                               data["maximum_absolute_difference"]["moisture_kg_kg"][-1],
                               rtol=1e-14, atol=0)
    if np.argmax(envelope) != 0:
        raise ValueError("The compact data no longer support a 1 s peak.")


def configure_style(requested_font: str | None) -> str:
    if requested_font and Path(requested_font).is_file():
        font_manager.fontManager.addfont(requested_font)
        requested_font = font_manager.FontProperties(fname=requested_font).get_name()
    installed = {font.name for font in font_manager.fontManager.ttflist}
    candidates = ([requested_font] if requested_font else []) + [
        "Microsoft YaHei", "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "SimHei"]
    selected = next((name for name in candidates if name in installed), None)
    if selected is None:
        raise RuntimeError("Install a Chinese sans-serif font (for example Noto Sans SC), or use --font FAMILY.")
    plt.rcParams.update({
        "font.family": selected, "font.size": 8.5, "axes.labelsize": 8.5,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 7.7,
        "axes.linewidth": .85, "xtick.direction": "in", "ytick.direction": "in",
        "axes.unicode_minus": False, "mathtext.fontset": "stix",
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "path.simplify": False,
    })
    return selected


def draw(data: dict) -> plt.Figure:
    fig, axes = plt.subplots(1, 2, figsize=(15.8/2.54, 7.5/2.54))
    fig.subplots_adjust(left=.12, right=.985, bottom=.19, top=.89, wspace=.43)
    a, b = axes
    n = np.asarray(data["coarse_n"])
    for field, color, marker, style, label in [
        ("temperature_C", BLUE, "o", "-", "温度"),
        ("moisture_kg_kg", ORANGE, "s", "--", "含水率")]:
        values = np.asarray(data["maximum_absolute_difference"][field])
        a.plot(n, values/data["targets"][field]["value"], color=color,
               marker=marker, mfc="white", mew=1.15, ms=4.7, lw=1.9,
               ls=style, label=label)
    a.axhline(1, color=GRAY, ls=(0, (4, 2)), lw=1.0, label="检验目标")
    a.set(xscale="log", yscale="log", xlim=(135, 3100), ylim=(.006, 650))
    a.set_xticks(n, labels=[str(v) for v in n])
    a.set_yticks([.01, .1, 1, 10, 100])
    a.set_xlabel(r"较粗网格段数 $N$")
    a.set_ylabel("网\n格\n差\n/\n目\n标", rotation=0,
                 labelpad=19, ha="center", va="center")
    a.yaxis.label.set_linespacing(.94)
    a.legend(loc="upper right", frameon=False, handlelength=2.6, borderaxespad=.4)

    time = np.asarray(data["time_s"])
    envelope = np.asarray(data["finest_pair_moisture_maximum_over_radii_kg_kg"])
    b.plot(time, envelope, color=ORANGE, lw=1.9)
    b.plot(time[0], envelope[0], marker="s", mfc="white", mec=ORANGE,
           mew=1.15, ms=4.7, zorder=4)
    b.axhline(TARGETS["moisture_kg_kg"], color=GRAY, ls=(0, (4, 2)), lw=1.0)
    b.set(xscale="log", yscale="log", xlim=(.85, 2200), ylim=(1e-7, 3.2e-5))
    b.set_xticks([1, 10, 100, 1000], labels=["1", "10", "100", "1000"])
    b.set_yticks([1e-7, 1e-6, 1e-5])
    b.set_xlabel("时间 / s")
    b.set_ylabel("含\n水\n率\n最\n大\n差\n(kg/kg)", rotation=0,
                 labelpad=22, ha="center", va="center")
    b.yaxis.label.set_linespacing(.97)
    b.annotate("1 s，表面", xy=(1, envelope[0]), xytext=(3.7, 1.05e-5),
               fontsize=7.7, color=GRAY, ha="left", va="center",
               arrowprops={"arrowstyle": "-", "color": GRAY, "lw": .75,
                           "shrinkA": 2, "shrinkB": 4})
    for index, ax in enumerate(axes):
        ax.text(0, 1.045, f"({'ab'[index]})", transform=ax.transAxes,
                fontweight="bold", fontsize=10, va="bottom")
        ax.grid(axis="y", color="#DCE0E3", linewidth=.55)
        ax.minorticks_off()
    return fig


def gray(value):
    r, g, b, alpha = to_rgba(value)
    luminance = .2126*r + .7152*g + .0722*b
    return (luminance, luminance, luminance, alpha)


def render_qa(fig: plt.Figure, directory: Path) -> dict:
    fig.canvas.draw()
    text_artists = list(fig.findobj(Text))
    visibility = [artist.get_visible() for artist in text_artists]
    for artist in text_artists:
        artist.set_visible(False)
    no_text = directory / f"{NAME}_no_text.png"
    fig.savefig(no_text, dpi=300)
    for artist, visible in zip(text_artists, visibility):
        artist.set_visible(visible)
    for line in fig.findobj(Line2D):
        line.set_color(gray(line.get_color()))
        for getter, setter in [(line.get_markeredgecolor, line.set_markeredgecolor),
                               (line.get_markerfacecolor, line.set_markerfacecolor)]:
            try:
                setter(gray(getter()))
            except (ValueError, TypeError):
                pass
    for artist in text_artists:
        artist.set_color(gray(artist.get_color()))
    grayscale = directory / f"{NAME}_gray.png"
    fig.savefig(grayscale, dpi=300)
    return {"no_text_png": str(no_text), "grayscale_png": str(grayscale)}


def check_text_bounds(fig: plt.Figure) -> None:
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    canvas = fig.bbox
    for artist in fig.findobj(Text):
        if not artist.get_visible() or not artist.get_text().strip():
            continue
        bounds = artist.get_window_extent(renderer)
        if (bounds.x0 < canvas.x0-.5 or bounds.y0 < canvas.y0-.5
                or bounds.x1 > canvas.x1+.5 or bounds.y1 > canvas.y1+.5):
            raise ValueError(f"Text outside the figure canvas: {artist.get_text()!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Self-contained compact JSON or its directory; skips original result files.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT, help="Output directory.")
    parser.add_argument("--font", help="Installed Chinese sans-serif family name or font file path.")
    args = parser.parse_args()
    data_path = args.data
    if data_path and data_path.is_dir():
        data_path = data_path / f"{NAME}_data.json"
    data = json.loads(data_path.read_text(encoding="utf-8")) if data_path else extract_data()
    validate_data(data)
    font = configure_style(args.font)
    args.output.mkdir(parents=True, exist_ok=True)
    compact_path = args.output / f"{NAME}_data.json"
    compact_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    fig = draw(data)
    check_text_bounds(fig)
    outputs = {}
    for extension in ["png", "pdf", "svg"]:
        path = args.output / f"{NAME}.{extension}"
        fig.savefig(path, dpi=300)
        outputs[extension] = identity(path)
    qa = render_qa(fig, Path(tempfile.mkdtemp(prefix="q1-startup-figure-qa-")))
    plt.close(fig)
    sources = {
        "schema_version": "1.0", "figure_id": NAME, "data_driven_visual": True,
        "caption": CAPTION, "generator": identity(Path(__file__), "scripts/build_q1_startup_figure.py"),
        "compact_data": identity(compact_path), "original_sources": data["original_sources"],
        "transformations": data["transformations"], "checks": data["checks"],
        "claim_boundary": data["claim_boundary"],
        "display": {"width_cm": 15.8, "height_cm": 7.5, "dpi": 300,
                    "font_family": font, "main_line_width_pt": 1.9,
                    "minimum_main_font_size_pt": 7.6,
                    "temperature": {"color": BLUE, "line": "solid", "marker": "circle"},
                    "moisture": {"color": ORANGE, "line": "dashed in left, solid in right", "marker": "square"},
                    "left_y": "dimensionless ratio, separate field-specific targets",
                    "left_axes": "logarithmic x and y", "right_axes": "logarithmic x and y",
                    "curve_simplification": False, "solver_executed": False},
        "outputs": outputs,
        "qa_method": "Same artist positions; all Text hidden for text-free check; line colors mapped to luminance for grayscale.",
    }
    (args.output/f"{NAME}_sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"outputs": [str(args.output/item["path"]) for item in outputs.values()],
                      "compact_data": str(compact_path), "qa": qa, "font": font,
                      "source_maximum_difference": data["checks"]["maximum_difference_from_report"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
