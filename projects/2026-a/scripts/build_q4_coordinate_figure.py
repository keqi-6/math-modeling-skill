"""Draw the observed Q4 radius and the adopted material-coordinate mapping.

Read retained inputs only: no solver, solution regeneration, or model changes.
The circles share one physical scale. Their interior ring is a material label,
not a moisture contour or an observed interior deformation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.text import Text
import numpy as np
import openpyxl
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/paper_figures/brief_refresh_20260911"
STEM = "fig06_q4_coordinates"
GEOMETRY = ROOT / "output/GEOMETRY/q4_radius.json"
WORKBOOK = ROOT / "附件/附件2.xlsx"
PROBLEM = ROOT / "A题.pdf"
WIDTH_CM, HEIGHT_CM, DPI = 15.8, 6.4, 360
BLUE, ORANGE, INK = "#0072B2", "#D55E00", "#45525B"
BODY, GRAY = "#F3EBDD", "#747474"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gray(color):
    rgb = np.array(to_rgb(color))
    linear = np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)
    lum = float(linear @ np.array([0.2126, 0.7152, 0.0722]))
    srgb = 12.92 * lum if lum <= 0.0031308 else 1.055 * lum ** (1 / 2.4) - 0.055
    return (srgb, srgb, srgb)


def load_inputs():
    geometry = json.loads(GEOMETRY.read_text(encoding="utf-8-sig"))
    if digest(WORKBOOK) != geometry["source"]["sha256"]:
        raise ValueError("The original radius workbook no longer matches the geometry source.")
    workbook = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    worksheet = workbook[geometry["source"]["sheet"]]
    original = np.array([[float(a), float(b)] for a, b in worksheet.iter_rows(
        min_row=2, max_row=146, min_col=1, max_col=2, values_only=True)])
    workbook.close()
    retained = np.array([[n["time_s"], n["radius_cm"]] for n in geometry["nodes"]], dtype=float)
    if retained.shape != (145, 2) or not np.array_equal(original, retained):
        raise ValueError("All 145 plotted observations must exactly equal original workbook cells.")
    if not np.array_equal(retained[:, 0], np.arange(145) * 1800):
        raise ValueError("Unexpected observation times.")
    if geometry["interpolation"] != "linear" or np.any(np.diff(retained[:, 1]) > 0):
        raise ValueError("Unexpected radius reconstruction contract.")
    # The Q4 statement supplies changing radius and fixed-distance output; it
    # does not observe the movement of interior material points.
    pdf = PdfReader(PROBLEM)
    text = "\n".join(page.extract_text() for page in pdf.pages)
    if not all(token in text for token in ("问题 4", "附件2", "药材表面", "半径")):
        raise ValueError("Original problem wording could not be located.")
    r0 = float(retained[0, 1])
    r6 = float(retained[retained[:, 0] == 21600, 1].item())
    if r0 != 2.0 or r6 != 1.374:
        raise ValueError("The two selected observed geometries changed.")
    return retained[:, 0] / 3600, retained[:, 1], [r0, r6]


def configure():
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font_manager.fontManager.addfont(str(font_path))
    plt.rcParams.update({
        "font.family": font_manager.FontProperties(fname=str(font_path)).get_name(),
        "font.size": 8.5, "mathtext.fontset": "stix", "axes.unicode_minus": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "axes.linewidth": 0.8, "xtick.direction": "in", "ytick.direction": "in",
        "savefig.facecolor": "white", "figure.facecolor": "white",
    })


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


def main():
    configure()
    times, radii, selected = load_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    figure = draw(times, radii, selected)
    outputs = {}
    for ext in ("png", "pdf", "svg"):
        path = OUT / f"{STEM}.{ext}"
        figure.savefig(path, dpi=DPI)
        outputs[ext] = {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
    for text in figure.findobj(match=Text):
        # The sequence arrow is an empty Annotation, and must remain visible.
        if text.get_text().strip():
            text.set_visible(False)
    textfree = OUT / f"{STEM}_no_text.png"
    figure.savefig(textfree, dpi=DPI)
    plt.close(figure)
    grayfigure = draw(times, radii, selected, grayscale=True)
    graypath = OUT / f"{STEM}_gray.png"
    grayfigure.savefig(graypath, dpi=DPI)
    plt.close(grayfigure)
    for key, path in [("no_text", textfree), ("gray", graypath)]:
        outputs[key] = {"path": path.relative_to(ROOT).as_posix(), "sha256": digest(path)}
    fonts = subprocess.run(["pdffonts", str(OUT / f"{STEM}.pdf")], text=True,
                           capture_output=True, check=True).stdout
    if "Type 3" in fonts:
        raise ValueError("Type 3 font is not permitted in this figure.")
    source_paths = [PROBLEM, WORKBOOK, GEOMETRY, Path(__file__)]
    record = {
        "schema_version": "1.0", "figure_id": STEM, "data_driven_visual": True,
        "role": "observed_radius_and_adopted_material_mapping",
        "sources": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in source_paths],
        "truth_mapping": [
            {"object": "circular radial cross-section", "source": "A题.pdf page 1: cylindrical object, initial radius 2 cm"},
            {"object": "changing radius and fixed-distance output", "source": "A题.pdf pages 2–3: Q4 and Table 6"},
            {"object": "145 radius points and 0 h/6 h circle sizes", "source": "附件/附件2.xlsx Sheet1!A2:B146; exact all-node agreement with GEOMETRY JSON"},
            {"object": "uniform interior material scaling", "source": "docs/Q4/solution_brief.md sections 5.1–5.2, equations (1),(3)", "kind": "adopted model assumption, not observed internal motion"},
            {"object": "fixed r=1.5 cm sampling marker", "source": "docs/Q4/solution_brief.md section 5.7, equation (16)", "kind": "coordinate marker, not a physical probe"},
        ],
        "data_checks": {"observations": 145, "original_cells": "A2:B146", "all_nodes_equal": True,
                        "time_range_h": [0, 72], "interpolation": "piecewise linear, no fitted curve",
                        "selected_times_h": [0, 6], "selected_radii_cm": selected,
                        "material_xi": 0.5, "material_radii_cm": [0.5 * r for r in selected],
                        "fixed_radius_cm": 1.5, "fixed_position_inside": [bool(1.5 <= r) for r in selected]},
        "visual_contract": {"width_cm": WIDTH_CM, "height_cm": HEIGHT_CM, "dpi": DPI,
                            "circle_scale": "one equal-aspect axis, identical physical centimetre scale",
                            "body_color": "material extent only; no moisture or density encoding",
                            "blue_ring": "same material coordinate, not a concentration contour",
                            "orange_marker": "fixed physical sampling radius; dashed line and x give non-colour redundancy",
                            "arrow": "snapshot order only; no velocity or quantitative displacement encoding",
                            "left_curve": "all observations and exact line segments, no extrapolation",
                            "no_top_title": True, "svg_editable_text": True},
        "outputs": outputs,
        "audit": {"font_report": fonts, "type3_fonts": False,
                  "source_and_geometry_checks": "passed", "visual_review": "awaiting rendered colour, no-text, and grayscale inspection"},
        "suggested_caption": "外半径观测与均匀径向缩放下的材料坐标对应。（a）附件2的145个半径观测及逐段线性重建。（b）0 h和6 h的截面使用相同厘米尺度，实线外轮廓半径分别为2.000和1.374 cm；蓝色材料环保持ξ=0.5，其物理半径由1.000 cm缩至0.687 cm。橙色叉号标记固定r=1.5 cm位置，在6 h已落在药材外。内部材料对应来自均匀缩放假设，填色只表示材料范围，不表示含水率；箭头表示两个时刻的先后。",
    }
    source_file = OUT / f"{STEM}_sources.json"
    source_file.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"outputs": outputs, "sources": str(source_file), "fonts": fonts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
