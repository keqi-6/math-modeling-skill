"""Draw three explanatory figures from compact, unrounded numerical data.

Portable rendering:
  python figure_restructured.py --data-dir compact --out-dir figures
  python figure_restructured.py --data-dir compact --out-dir figures --only 2-2
Explicit extraction from an original run (does not execute a solver):
  python build_restructured_figures.py --source run.npz --data-dir compact --extract-only
Dependencies: Python 3.10+, NumPy and Matplotlib; supply --font-path if needed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, Rectangle, Patch
from matplotlib.text import Text, Annotation

DATA_NAME = "restructured_figure_data.json"
WIDTH_CM = 15.8
BLUE, PALE_BLUE = "#286F8C", "#E4EFF3"
WARM, INK, GRAY = "#C76B50", "#263D49", "#74838A"
NAMES = {"1-1": "fig01_annular_control_volumes",
         "2-2": "fig09_q2_diffusivity_decomposition",
         "3-1": "fig05_q3_completion_progress"}


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_data(source_path: Path, data_dir: Path, provenance_path: Path | None = None) -> dict:
    """Reduce existing arrays to all quantitative values required by the plots."""
    source_path = source_path.resolve()
    with np.load(source_path, allow_pickle=False) as z:
        time = z["time_s"].copy()
        radius = z["radius_m"].copy()
        moisture = z["moisture_kg_kg"].copy()
        maximum = z["max_moisture_kg_kg"].copy()
        node_count = int(z["mesh_radius_m"].size)
        assert time.size > 10800 and np.array_equal(time, np.arange(time.size)), "Expected a continuous integer-second trajectory from zero through at least 3 h."
        np.testing.assert_allclose(radius, np.arange(21) * .001, rtol=0, atol=2e-18)
        assert moisture.shape == (time.size, 21)
        assert np.isfinite(moisture).all() and np.isfinite(maximum).all()
        assert (moisture > 0).all()
        assert np.all(maximum >= moisture.max(axis=1) - 2e-15)
        sample_seconds = np.array([1800, 5400, 10800])
        c = moisture[sample_seconds][:, [0, -1]]
        t = z["temperature_C"][sample_seconds][:, [0, -1]]

    heat = 3850 * (1 / (28 + 273.15) - 1 / (t + 273.15))
    drying = -.45 * (1 / c - 1 / 2.55)
    diffusivity = 2.4e-3 * np.exp(-.45 / c - 3850 / (t + 273.15))
    d0 = 2.4e-3 * np.exp(-.45 / 2.55 - 3850 / (28 + 273.15))
    net = np.log(diffusivity / d0)
    np.testing.assert_allclose(heat + drying, net, rtol=0, atol=5e-15)
    assert (heat > 0).all() and (drying < 0).all()

    threshold = .15
    first = np.array([np.flatnonzero(moisture[:, j] < threshold)[0] for j in range(21)])
    end_index = int(np.flatnonzero(maximum < threshold)[0])
    end = int(time[end_index])
    assert int(first.max()) <= end, "All-node completion cannot precede sampled-position completion."
    assert np.all(maximum[end_index:] < threshold)
    rows = []
    for j, index in enumerate(first):
        assert index > 0 and moisture[index-1, j] >= threshold
        assert np.all(moisture[index:, j] < threshold), "Threshold recrossing requires segmented bands."
        rows.append({"radius_cm": float(100 * radius[j]),
                     "first_strict_second": int(time[index]),
                     "previous_moisture_kg_kg": float(moisture[index-1, j]),
                     "first_moisture_kg_kg": float(moisture[index, j])})
    data = {
        "schema_version": "1.0", "source_file": source_path.name,
        "diffusivity": {
            "time_s": sample_seconds.tolist(), "positions": ["中心", "表面"],
            "temperature_C": t.tolist(), "moisture_kg_kg": c.tolist(),
            "initial_temperature_C": 28., "initial_moisture_kg_kg": 2.55,
            "heat_log_contribution": heat.tolist(), "drying_log_contribution": drying.tolist(),
            "net_log_ratio": net.tolist(), "diffusivity_m2_s": diffusivity.tolist(),
            "initial_diffusivity_m2_s": float(d0),
            "interpretation": "Exact algebraic decomposition along one main trajectory; not independent causal effects or alternate simulations."
        },
        "completion": {
            "threshold_kg_kg": threshold, "sampling_interval_s": 1,
            "checked_time_range_s": [int(time[0]), int(time[-1])],
            "sampled_positions": rows, "threshold_recrossings": 0,
            "all_node_count": node_count, "all_node_first_strict_second": end,
            "all_node_previous_maximum_kg_kg": float(maximum[end_index-1]),
            "all_node_first_maximum_kg_kg": float(maximum[end_index]),
            "interpretation": f"Bars classify integer-second samples at 21 requested output radii; the final stopping time separately uses the maximum over all {node_count} solver nodes."
        }
    }
    write_json(data_dir / DATA_NAME, data)
    provenance = {
        "source": {"path": str(source_path), "sha256": digest(source_path)},
        "compact_file": DATA_NAME, "compact_sha256": digest(data_dir / DATA_NAME),
        "extraction_script_sha256": digest(Path(__file__)), "solver_executed": False,
        "identity_residual": float(np.max(np.abs(heat + drying - net))),
        "threshold_checks": {"positions": 21, "checked_until_s": int(time[-1]),
                             "sample_interval_s": 1, "recrossings": 0,
                             "all_node_final_s": end},
        "rounding": "All numerical inputs retained as float64; only plot labels are formatted."
    }
    if provenance_path is not None:
        write_json(provenance_path, provenance)
    return data


def configure(font_path: str | None) -> str:
    if font_path:
        font_manager.fontManager.addfont(font_path)
        name = font_manager.FontProperties(fname=font_path).get_name()
    else:
        fonts = {f.name for f in font_manager.fontManager.ttflist}
        name = next((x for x in ["Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", "SimHei"] if x in fonts), None)
        if name is None:
            raise RuntimeError("Chinese font unavailable: provide --font-path with a Chinese font file.")
    plt.rcParams.update({
        "font.family": name, "font.size": 9, "axes.labelsize": 9,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
        "axes.linewidth": .8, "lines.linewidth": 1.8,
        "mathtext.fontset": "stix", "axes.unicode_minus": False,
        "xtick.direction": "out", "ytick.direction": "out",
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "path.simplify": False,
    })
    return name


def gray(color):
    r, g, b, a = to_rgba(color)
    y = .2126*r + .7152*g + .0722*b
    return (y, y, y, a)


def save_bundle(fig, key: str, out_dir: Path, qa: bool, font: str, metadata: dict) -> dict:
    name = NAMES[key]
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw()
    outputs = {}
    for ext in ["png", "pdf", "svg"]:
        path = out_dir / f"{name}.{ext}"
        fig.savefig(path, dpi=300)
        outputs[ext] = {"file": path.name, "sha256": digest(path)}
    if qa:
        qa_dir = out_dir / "qa"
        qa_dir.mkdir(exist_ok=True)
        texts = list(fig.findobj(Text))
        visible = [x.get_visible() for x in texts]
        strings = [x.get_text() for x in texts]
        for x in texts:
            if isinstance(x, Annotation):
                x.set_text("")  # retain geometric arrows attached to annotation artists
            else:
                x.set_visible(False)
        fig.savefig(qa_dir / f"{name}_no_text.png", dpi=300)
        for x, vis, string in zip(texts, visible, strings):
            x.set_visible(vis)
            x.set_text(string)
        for item in fig.findobj(Line2D):
            for getter, setter in [(item.get_color, item.set_color),
                                   (item.get_markeredgecolor, item.set_markeredgecolor),
                                   (item.get_markerfacecolor, item.set_markerfacecolor)]:
                try:
                    setter(gray(getter()))
                except (ValueError, TypeError):
                    pass
        for item in fig.findobj(Patch):
            item.set_facecolor(gray(item.get_facecolor()))
            item.set_edgecolor(gray(item.get_edgecolor()))
        for item in texts:
            item.set_color(gray(item.get_color()))
            if isinstance(item, Annotation) and item.arrow_patch is not None:
                item.arrow_patch.set_facecolor(gray(item.arrow_patch.get_facecolor()))
                item.arrow_patch.set_edgecolor(gray(item.arrow_patch.get_edgecolor()))
        for collection in fig.findobj(matplotlib.collections.Collection):
            for getter, setter in [(collection.get_facecolors, collection.set_facecolors),
                                   (collection.get_edgecolors, collection.set_edgecolors)]:
                values = getter()
                if values.size:
                    setter([gray(x) for x in values])
        fig.savefig(qa_dir / f"{name}_gray.png", dpi=300)
    metadata.update({"id": key, "name": name, "outputs": outputs,
                     "width_cm": WIDTH_CM, "height_cm": float(fig.get_figheight()*2.54),
                     "font": font, "font_size_pt": 9, "solver_executed": False})
    plt.close(fig)
    return metadata


def annular_figure():
    fig = plt.figure(figsize=(WIDTH_CM/2.54, 7.9/2.54))
    a = fig.add_axes([.035, .12, .34, .80])
    b = fig.add_axes([.445, .15, .53, .76])
    for ax in [a, b]:
        ax.axis("off")
    a.set_aspect("equal")
    a.set_xlim(-1.13, 1.25); a.set_ylim(-1.2, 1.25)
    # The five displayed node locations only illustrate node-centred geometry.
    faces = np.array([0., .125, .375, .625, .875, 1.])
    colors = [PALE_BLUE, "#F3F5F5", "#B9D7E1", "#F3F5F5", "#F4E3DB"]
    for j in reversed(range(5)):
        a.add_patch(Circle((0, 0), faces[j+1], fc=colors[j], ec="none"))
    for face in faces[1:-1]:
        a.add_patch(Circle((0, 0), face, fill=False, ec=GRAY, lw=.7, ls=(0, (3, 2))))
    a.add_patch(Circle((0, 0), 1, fill=False, ec=INK, lw=1.5))
    a.plot([0, 1], [0, 0], color=INK, lw=1.2)
    a.plot(np.linspace(0, 1, 5), np.zeros(5), "o", ms=4.4, color=INK, mec="white", mew=.7)
    a.text(-.065, -.095, "O", ha="right", va="top")
    a.annotate("", (1.11, 0), (1.0, 0), arrowprops={"arrowstyle": "->", "lw": 1.1, "color": INK})
    a.text(1.15, 0, "$r$", va="center")
    fig.text(.04, .945, "(a)", fontsize=10, fontweight="bold")

    b.set_xlim(-.2, 4.75); b.set_ylim(-1.04, 1.4)
    fig.text(.445, .945, "(b)", fontsize=10, fontweight="bold")
    xfaces = faces * 4
    for j in range(5):
        b.add_patch(Rectangle((xfaces[j], -.28), xfaces[j+1]-xfaces[j], .56,
                              fc=colors[j], ec="none"))
    b.plot([0, 4], [-.28, -.28], color=INK, lw=.9)
    b.plot([0, 4], [.28, .28], color=INK, lw=.9)
    for face in xfaces[1:-1]:
        b.plot([face, face], [-.42, .43], color=GRAY, ls=(0, (3, 2)), lw=.9)
    b.plot([0, 0], [-.28, .28], color=INK, lw=1.3)
    b.plot([4, 4], [-.42, .43], color=INK, lw=1.7)
    b.plot([0, 4], [0, 0], color=INK, lw=1.2)
    b.plot(np.arange(5), np.zeros(5), "o", ms=5, color=INK, mec="white", mew=.8)
    for x, label in zip(range(5), ["$r_0=0$", "$r_1$", "$r_i$", "$r_{i+1}$", "$r_N=R$"]):
        b.text(x, -.58, label, ha="center", va="top", fontsize=8.5)
    b.text(1.5, .55, "$r_{i-1/2}$", ha="center", fontsize=8.5)
    b.text(2.5, .55, "$r_{i+1/2}$", ha="center", fontsize=8.5)
    b.annotate("", (1.5, .44), (1.5, .52), arrowprops={"arrowstyle": "-", "color": GRAY})
    b.annotate("", (2.5, .44), (2.5, .52), arrowprops={"arrowstyle": "-", "color": GRAY})
    for x0, x1, y, text in [(1., 2., -1.00, r"$\Delta r$"), (3.5, 4., .91, r"$\Delta r/2$")]:
        b.plot([x0, x1], [y, y], color=INK, lw=1.)
        b.plot([x0, x0], [y-.045, y+.045], color=INK, lw=1.)
        b.plot([x1, x1], [y-.045, y+.045], color=INK, lw=1.)
        b.text((x0+x1)/2, y+.08, text, ha="center", fontsize=8.5)
    b.annotate("", (4.7, .02), (4.05, .02), arrowprops={"arrowstyle": "-|>", "lw": 2.1, "color": BLUE, "mutation_scale": 13})
    b.text(3.85, .52, "$h_m(C_N-C_{eq})$", ha="center", fontsize=8)
    b.text(.1, 1.12, r"$C_0=C_1=\cdots=C_N=C_{init}$", ha="left", fontsize=9)
    fig.legend(handles=[Line2D([], [], ls="none", marker="o", color=INK, ms=4.5, label="节点"),
                        Line2D([], [], color=GRAY, ls="--", lw=1., label="控制体界面"),
                        Patch(facecolor="#F4E3DB", edgecolor="none", label="表面半控制体")],
               loc="lower center", bbox_to_anchor=(.52, -.01), ncol=3, frameon=False)
    return fig, {"data_driven_visual": False,
                 "scope": "Conceptual Q1 radial node-centred control-volume geometry, not a simulation result.",
                 "mapping": "Solid dots are radial nodes; dashed circles/lines are midpoint faces. Surface node is exactly at R, on the outer edge of its half-width volume. Uniform initial moisture makes all internal face fluxes zero; the arrow is the initial outward moisture exchange. Circle area is geometric, with displayed node count schematic."}


def diffusivity_figure(data: dict):
    d = data["diffusivity"]
    heat, drying, net = (np.asarray(d[key]) for key in ["heat_log_contribution", "drying_log_contribution", "net_log_ratio"])
    c, t = np.asarray(d["moisture_kg_kg"]), np.asarray(d["temperature_C"])
    reference = np.log(2.4e-3 * np.exp(-.45/c-3850/(t+273.15)) / d["initial_diffusivity_m2_s"])
    np.testing.assert_allclose(heat + drying, reference, rtol=0, atol=5e-15)
    np.testing.assert_allclose(net, reference, rtol=0, atol=5e-15)
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH_CM/2.54, 7.3/2.54), sharex=True, sharey=True)
    fig.subplots_adjust(left=.095, right=.98, top=.84, bottom=.25, wspace=.18)
    y = np.array([2., 1., 0.])
    for j, ax in enumerate(axes):
        ax.barh(y, heat[:, j], height=.48, color=WARM, edgecolor="white", lw=.6)
        ax.barh(y, drying[:, j], height=.48, color=BLUE, edgecolor=INK, lw=.4, hatch="///")
        ax.plot(net[:, j], y, ls="none", marker="D", color=INK, mec="white", mew=.85, ms=5.6, zorder=4)
        ax.axvline(0, color=INK, lw=1.)
        ax.set_axisbelow(True)
        ax.grid(axis="x", color="#DAE0E3", lw=.55)
        for side in ["top", "right", "left"]:
            ax.spines[side].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.set_yticks(y, [f"{x/3600:g} h" for x in d["time_s"]])
        ax.set_ylim(-.55, 2.55)
        ax.set_xlim(-.4, 1.02)
        ax.set_xticks([-.3, 0, .3, .6, .9])
        ax.text(0, 1.10, f"({'ab'[j]}) {d['positions'][j]}", transform=ax.transAxes, fontweight="bold")
        ax.set_xlabel(r"$\ln(D/D_0)$ 的分解")
    axes[1].tick_params(axis="y", labelleft=True)
    fig.legend(handles=[Patch(facecolor=WARM, label="升温项"),
                        Patch(facecolor=BLUE, edgecolor=INK, hatch="///", label="失水项"),
                        Line2D([], [], marker="D", ls="none", color=INK, mec="white", ms=5, label="净变化")],
               ncol=3, frameon=False, loc="lower center", bbox_to_anchor=(.54, .005))
    return fig, {"data_driven_visual": True, "source_file": data["source_file"],
                 "quantity": "Natural logarithm of local diffusivity relative to its uniform initial value; dimensionless.",
                 "sampling": "0.5, 1.5 and 3 h, centre and surface.",
                 "interpretation": d["interpretation"],
                 "identity_residual": float(np.max(np.abs(heat+drying-reference)))}


def completion_figure(data: dict):
    d = data["completion"]
    rows = d["sampled_positions"]
    r = np.array([x["radius_cm"] for x in rows])
    first = np.array([x["first_strict_second"] for x in rows])
    end = d["all_node_first_strict_second"] / 3600
    assert all(x["previous_moisture_kg_kg"] >= .15 > x["first_moisture_kg_kg"] for x in rows)
    assert d["all_node_previous_maximum_kg_kg"] >= .15 > d["all_node_first_maximum_kg_kg"]
    fig, ax = plt.subplots(figsize=(WIDTH_CM/2.54, 9.5/2.54))
    fig.subplots_adjust(left=.12, right=.96, bottom=.19, top=.91)
    ax.barh(r, end, height=.078, color=PALE_BLUE, edgecolor="none")
    ax.barh(r, first/3600, height=.078, color=BLUE, edgecolor="none")
    ax.plot(first/3600, r, ls="none", marker="o", ms=3.1, color=INK, mec="white", mew=.5)
    ax.axvline(end, color=WARM, lw=1.7, ls=(0, (4, 2)))
    ax.set_axisbelow(True)
    ax.grid(axis="x", color="#DAE0E3", lw=.55)
    ax.set_ylim(-.09, 2.12)
    ax.set_xlim(0, end + 1.4)
    ax.set_yticks([0, .5, 1, 1.5, 2.], ["0", "0.5", "1.0", "1.5", "2.0"])
    step = 12. if end >= 48 else (6. if end >= 24 else (3. if end >= 12 else 1.))
    interior_ticks = np.arange(0, end, step)
    interior_ticks = interior_ticks[(end-interior_ticks >= .35*step) | (interior_ticks == 0)]
    ax.set_xticks([*interior_ticks, end], [*[f"{x:g}" for x in interior_ticks], f"{end:.2f}"])
    ax.set_xlabel("时间 / h")
    ax.set_ylabel("半\n径\ncm", rotation=0, labelpad=18, va="center")
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    ax.text(end-.7, 2.095, "全域达标", ha="right", va="bottom", fontsize=8, color=WARM)
    fig.legend(handles=[Patch(facecolor=BLUE, label=r"$C\geq0.15$"),
                        Patch(facecolor=PALE_BLUE, edgecolor=GRAY, linewidth=.4, label="$C<0.15$"),
                        Line2D([], [], ls="none", marker="o", ms=4, color=INK, label="首次严格达标秒")],
               ncol=3, frameon=False, loc="lower center", bbox_to_anchor=(.54, .018))
    return fig, {"data_driven_visual": True, "source_file": data["source_file"],
                 "interpretation": d["interpretation"],
                 "threshold_kg_kg": d["threshold_kg_kg"],
                 "all_node_first_strict_second": d["all_node_first_strict_second"],
                 "no_recrossing_check": {"through_s": d["checked_time_range_s"][1], "recrossings": d["threshold_recrossings"]},
                 "time_display": "Hours on axis, underlying bar boundaries are integer seconds; the rounded final tick label is not a new stopping time."}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--source", type=Path, help="Explicitly extract compact data from an existing original NPZ.")
    parser.add_argument("--provenance", type=Path, help="Optional separate extraction provenance JSON.")
    parser.add_argument("--extract-only", action="store_true")
    parser.add_argument("--only", nargs="+", choices=list(NAMES), default=list(NAMES))
    parser.add_argument("--font-path")
    parser.add_argument("--qa", action="store_true", help="Also create text-hidden and grayscale audit PNGs.")
    args = parser.parse_args()
    if args.source:
        extract_data(args.source, args.data_dir, args.provenance)
    if args.extract_only:
        if not args.source:
            parser.error("--extract-only requires --source")
        print(f"Prepared {DATA_NAME}; no solver was executed.")
        return
    if args.out_dir is None:
        parser.error("--out-dir is required for rendering")
    data_path = args.data_dir / DATA_NAME
    data = json.loads(data_path.read_text(encoding="utf-8"))
    font = configure(args.font_path)
    generators = {"1-1": lambda: annular_figure(),
                  "2-2": lambda: diffusivity_figure(data),
                  "3-1": lambda: completion_figure(data)}
    figures = []
    for key in args.only:
        fig, meta = generators[key]()
        figures.append(save_bundle(fig, key, args.out_dir, args.qa, font, meta))
    write_json(args.out_dir / "figure_manifest.json", {
        "schema_version": "1.0", "generator_file": Path(__file__).name,
        "generator_sha256": digest(Path(__file__)), "compact_file": DATA_NAME,
        "compact_sha256": digest(data_path), "figures": figures,
        "qa_rendered": args.qa})
    print(f"Rendered {len(figures)} figures with PDF, SVG and PNG outputs.")


if __name__ == "__main__":
    main()
