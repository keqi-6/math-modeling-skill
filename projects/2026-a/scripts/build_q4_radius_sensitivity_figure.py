"""Plot Q4 radius reconstruction sensitivity from saved results, without solving.

Run without arguments to extract compact figure data from the project results.
Use --data <fig10_q4_radius_sensitivity.data.json> to redraw independently of
the full results; --output selects the destination directory. No solver is called.
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
from matplotlib.text import Text
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
STEM = "fig10_q4_radius_sensitivity"
DEFAULT_OUTPUT = ROOT / "output/paper_figures/verification_refresh_20260912"
WIDTH_CM, HEIGHT_CM, DPI = 15.8, 7.8, 360
BLUE, ORANGE, GRAY = "#0072BD", "#D95319", "#333333"
CAPTION = (
    "问题4启动阶段的半径重建与局部含水率差异。"
    "（a）前30 min的两种半径重建，灰色圆点为附件2的原始半径观测；"
    "线性与PCHIP曲线连接各自已保存的每分钟半径值。"
    "（b）三个固定物理位置的含水率差ΔC=C_PCHIP−C_线性，"
    "每分钟取样，其余输入与N=10240网格相同；仅画双方均在材料内的共同位置。"
    "r=1.9 cm曲线止于22 min，此后该位置在至少一种几何中已处于材料外，未补线或填零。"
    "线型及标记共同区分曲线。"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(path: Path) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
            "bytes": path.stat().st_size}


def finite_list(array: np.ndarray):
    return json.loads(json.dumps(np.asarray(array).tolist(), allow_nan=True)
                      .replace("NaN", "null"))


def extract_data() -> dict:
    from scipy.interpolate import PchipInterpolator

    main_path = ROOT / "output/Q4/run_n10240-v1-20260911.npz"
    other_path = ROOT / "output/Q4/run_n10240-pchip-v1-20260911.npz"
    geometry_path = ROOT / "output/GEOMETRY/q4_radius.json"
    raw_path = ROOT / "附件/附件2.xlsx"
    sources = [main_path, other_path, main_path.with_suffix(".json"),
               other_path.with_suffix(".json"), geometry_path, raw_path]
    metadata_pair = []
    for path in (main_path, other_path):
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        metadata_pair.append(metadata)
        if sha(path) != metadata["result_sha256"]:
            raise ValueError(f"Result identity mismatch: {path}")
        if metadata["grid_n"] != 10240 or metadata["properties"] != "appendix4":
            raise ValueError("The figure requires the matched N=10240 Appendix 4 runs.")
    shared_keys = ["spec_sha256", "boundary_sha256", "raw_environment_sha256",
                   "radius_json_sha256", "raw_radius_sha256", "solver_sha256", "scenario",
                   "initial_temperature_C", "initial_moisture_kg_kg", "initial_radius_m",
                   "rtol", "atol_temperature", "atol_moisture", "max_step_observed_s", "max_step_tail_s"]
    if any(metadata_pair[0][key] != metadata_pair[1][key] for key in shared_keys):
        raise ValueError("The two sensitivity runs are not otherwise matched.")
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    if sha(raw_path) != geometry["source"]["sha256"]:
        raise ValueError("Raw radius attachment identity mismatch.")
    nodes_t = np.array([v["time_s"] for v in geometry["nodes"]], dtype=float)
    nodes_r = np.array([v["radius_cm"] for v in geometry["nodes"]], dtype=float)
    with np.load(main_path) as main, np.load(other_path) as other:
        time, ia, ib = np.intersect1d(main["time_s"], other["time_s"], return_indices=True)
        use = (time >= 0) & (time <= 1800) & (time % 60 == 0)
        time, ia, ib = time[use], ia[use], ib[use]
        if not np.array_equal(time, np.arange(0, 1801, 60)):
            raise ValueError("The expected common minute samples are incomplete.")
        radii_m = np.array([.017, .018, .019])
        columns = [np.flatnonzero(np.isclose(main["radius_m"], r, rtol=0,
                                           atol=1e-14)).item() for r in radii_m]
        if not np.allclose(main["radius_m"], other["radius_m"], rtol=0, atol=0):
            raise ValueError("Fixed physical radius columns differ.")
        radius_cm = np.stack([main["surface_radius_m"][ia],
                              other["surface_radius_m"][ib]]) * 100
        expected_r = np.stack([np.interp(time, nodes_t, nodes_r),
                               PchipInterpolator(nodes_t, nodes_r)(time)])
        if not np.allclose(radius_cm, expected_r, rtol=0, atol=1e-13):
            raise ValueError("Saved surface radii differ from the observed-node reconstructions.")
        c_main = main["moisture_kg_kg"][ia][:, columns]
        c_other = other["moisture_kg_kg"][ib][:, columns]
        common_inside = main["inside_mask"][ia][:, columns] & other["inside_mask"][ib][:, columns]
        c_main, c_other = np.where(common_inside, c_main, np.nan), np.where(common_inside, c_other, np.nan)
        observed = (nodes_t >= 0) & (nodes_t <= 1800)
        return {
            "schema_version": "1.0", "figure_id": STEM,
            "data_driven_visual": True, "source_files": [identity(p) for p in sources],
            "time_s": time.tolist(), "fixed_radius_cm": (radii_m * 100).tolist(),
            "radius_linear_cm": radius_cm[0].tolist(), "radius_pchip_cm": radius_cm[1].tolist(),
            "observed_time_s": nodes_t[observed].tolist(), "observed_radius_cm": nodes_r[observed].tolist(),
            "moisture_linear_kg_kg": finite_list(c_main),
            "moisture_pchip_kg_kg": finite_list(c_other),
            "common_inside": common_inside.tolist(),
            "transformations": {
                "alignment": "Intersection of saved time_s arrays; 0..1800 s at every 60 s.",
                "radius": "Saved surface_radius_m multiplied by 100; independently checked against all attachment nodes using linear/PCHIP interpolation.",
                "moisture_difference": "PCHIP minus linear, at the same saved time and fixed physical radius.",
                "domain": "Intersection of both inside_mask arrays. Outside values are null; no extension, zero fill, or surface substitution.",
                "line_rendering": "Straight connections between actual saved minute samples; no further fit or smoothing.",
                "selection": "First 30 minutes and three near-surface fixed positions illustrate the reported maximum at 960 s, 1.9 cm; not a new global error scan.",
            },
            "caption": CAPTION,
        }


def validate_data(data: dict) -> dict:
    if data.get("figure_id") != STEM:
        raise ValueError("Wrong compact-data figure identity.")
    time = np.array(data["time_s"], dtype=float)
    radii = np.array(data["fixed_radius_cm"], dtype=float)
    main = np.array(data["moisture_linear_kg_kg"], dtype=float)
    other = np.array(data["moisture_pchip_kg_kg"], dtype=float)
    inside = np.array(data["common_inside"], dtype=bool)
    if not np.array_equal(time, np.arange(0, 1801, 60)) or not np.allclose(radii, [1.7, 1.8, 1.9]):
        raise ValueError("Unexpected plotted samples.")
    if main.shape != (31, 3) or other.shape != main.shape or inside.shape != main.shape:
        raise ValueError("Invalid compact array shape.")
    if not np.array_equal(np.isfinite(main) & np.isfinite(other), inside):
        raise ValueError("Finite values and the joint domain mask disagree.")
    delta = np.where(inside, other-main, np.nan)
    peak = np.unravel_index(np.nanargmax(np.abs(delta)), delta.shape)
    if time[peak[0]] != 960 or not np.isclose(radii[peak[1]], 1.9):
        raise ValueError("The recorded local maximum cannot be reproduced.")
    if not np.isclose(delta[peak], -0.054857364284587096, rtol=0, atol=1e-13):
        raise ValueError("The plotted local difference disagrees with verified evidence.")
    return {"maximum_sampled_local_difference_kg_kg": float(delta[peak]),
            "maximum_time_s": float(time[peak[0]]), "maximum_radius_cm": float(radii[peak[1]]),
            "last_common_interior_time_s_by_radius": [float(time[inside[:, j]][-1]) for j in range(3)]}


def configure_font(font_path: Path | None = None) -> str:
    if font_path:
        font_manager.fontManager.addfont(str(font_path))
        name = font_manager.FontProperties(fname=str(font_path)).get_name()
    else:
        installed = {font.name for font in font_manager.fontManager.ttflist}
        candidates = ["Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "SimHei", "PingFang SC"]
        name = next((x for x in candidates if x in installed), None)
        if name is None:
            raise RuntimeError("Install a Chinese font or supply --font <font-file>.")
    plt.rcParams.update({
        "font.family": name, "font.size": 8.5, "axes.labelsize": 8.5,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 7.7,
        "mathtext.fontset": "stix", "axes.unicode_minus": False,
        "axes.linewidth": .85, "lines.linewidth": 1.9,
        "xtick.direction": "in", "ytick.direction": "in",
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "savefig.facecolor": "white", "figure.facecolor": "white",
    })
    return name


def make_figure(data: dict):
    time_min = np.array(data["time_s"])/60
    delta = np.array(data["moisture_pchip_kg_kg"], dtype=float) - np.array(data["moisture_linear_kg_kg"], dtype=float)
    fig, (left, right) = plt.subplots(1, 2, figsize=(WIDTH_CM/2.54, HEIGHT_CM/2.54))
    fig.subplots_adjust(left=.12, right=.985, bottom=.24, top=.90, wspace=.60)
    for ax, letter in zip((left, right), "ab"):
        ax.set_xlim(0, 30)
        ax.set_xticks([0, 10, 20, 30])
        ax.set_xlabel("时间 / min", labelpad=4)
        ax.grid(True, color=".89", lw=.45)
        ax.set_axisbelow(True)
        ax.text(0, 1.045, f"({letter})", transform=ax.transAxes, ha="left", va="bottom", fontsize=9, weight="bold")
    left.plot(time_min, data["radius_linear_cm"], color=BLUE, lw=1.9, label="线性重建")
    left.plot(time_min, data["radius_pchip_cm"], color=ORANGE, lw=1.9, ls="--", label="PCHIP")
    left.scatter(np.array(data["observed_time_s"])/60, data["observed_radius_cm"],
                 color=".35", edgecolors="white", linewidths=.5, s=22, zorder=4, label="半径观测", clip_on=False)
    left.set_ylim(1.865, 2.012)
    left.set_yticks([1.88, 1.92, 1.96, 2.00])
    left.set_ylabel("外\n半\n径\n(cm)", rotation=0, ha="center", va="center", labelpad=15, linespacing=1.05)
    left.legend(loc="upper right", bbox_to_anchor=(1.01, .96), frameon=False, handlelength=2.2, labelspacing=.5)
    right.axhline(0, color=".65", lw=.9, ls="--")
    for j, (color, style, marker) in enumerate(zip([BLUE, ORANGE, GRAY], ["-", "--", "-."], ["o", "s", "^"])):
        valid = np.isfinite(delta[:, j])
        right.plot(time_min, delta[:, j], color=color, lw=1.9, ls=style,
                   marker=marker, markevery=5, ms=3.2, mfc="white", mec=color, mew=.9,
                   label=f"{data['fixed_radius_cm'][j]:.1f} cm")
        if not valid[-1]:
            last = np.flatnonzero(valid)[-1]
            right.plot(time_min[last], delta[last, j], marker=marker, ms=5,
                       mfc="white", mec=color, mew=1.1, ls="none")
    right.set_ylim(-.061, .008)
    right.set_yticks([-.06, -.04, -.02, 0])
    right.set_ylabel("含\n水\n率\n差\n(kg/kg)", rotation=0, ha="center", va="center", labelpad=21, linespacing=1.05)
    right.legend(loc="upper center", bbox_to_anchor=(.5, -.24), ncol=3,
                 frameon=False, handlelength=1.5, handletextpad=.35,
                 columnspacing=.8, borderaxespad=0, fontsize=7.4)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, help="Standalone compact figure-data JSON, or its containing directory.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--font", type=Path, help="Optional local Chinese font file; no font is redistributed.")
    parser.add_argument("--qa-dir", type=Path, help="Optional separate directory for text-free and grayscale review images.")
    args = parser.parse_args()
    data_input = args.data/f"{STEM}.data.json" if args.data and args.data.is_dir() else args.data
    data = json.loads(data_input.read_text(encoding="utf-8")) if data_input else extract_data()
    evidence = validate_data(data)
    args.output.mkdir(parents=True, exist_ok=True)
    data_path = args.output / f"{STEM}.data.json"
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    font_name = configure_font(args.font)
    fig = make_figure(data)
    outputs = {}
    for extension in ("png", "pdf", "svg"):
        target = args.output / f"{STEM}.{extension}"
        fig.savefig(target, dpi=DPI)
        outputs[extension] = {"file": target.name, "sha256": sha(target), "bytes": target.stat().st_size}
    qa_dir = args.qa_dir or Path(tempfile.mkdtemp(prefix="q4-radius-figure-qa-"))
    qa_dir.mkdir(parents=True, exist_ok=True)
    from PIL import Image
    Image.open(args.output/f"{STEM}.png").convert("L").save(qa_dir/f"{STEM}.gray.png")
    for text in fig.findobj(match=Text):
        text.set_visible(False)
    fig.savefig(qa_dir/f"{STEM}.no_text.png", dpi=DPI)
    plt.close(fig)
    source_info = {
        "schema_version": "1.0", "figure_id": STEM, "data_driven_visual": True,
        "role": "Q4 auxiliary radius-reconstruction comparison, for section 8.3 only",
        "caption": CAPTION, "original_sources": data["source_files"],
        "compact_data": {"file": data_path.name, "sha256": sha(data_path), "bytes": data_path.stat().st_size},
        "generator": {"file": Path(__file__).name, "sha256": sha(Path(__file__))},
        "transformations": data["transformations"], "verified_values": evidence,
        "visual_contract": {"width_cm": WIDTH_CM, "height_cm": HEIGHT_CM, "dpi": DPI,
                            "font": font_name, "line_width_pt": 1.9,
                            "series_encoding": "Colors plus line styles; fixed positions also have markers.",
                            "no_text_plot_relationship": "Two radius histories share measured endpoints but differ between them; three local responses differ in depth and one stops at the joint-domain boundary.",
                            "uncertainty": "No confidence intervals or probability interpretation."},
        "outputs": outputs,
    }
    (args.output/f"{STEM}.sources.json").write_text(json.dumps(source_info, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"outputs": str(args.output.resolve()), "qa_dir": str(qa_dir.resolve()), "verified_values": evidence}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
