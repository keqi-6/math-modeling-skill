"""Two-layer r-t grid for the actual NDF1 start of each Q1 solve segment.

This is a symbolic local residual diagram, not a plot of saved solver steps.
Earlier spacetime-grid outputs are preserved; the new startup figure has a
distinct path. No solver, manuscript exporter, or document builder runs here.
"""
from pathlib import Path
import hashlib
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch
from matplotlib.text import Text
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/paper_figures/startup_grid_20260912"
STEM = "fig01_startup_grid"
BLUE, ORANGE, DARK, GRID = "#337FA6", "#CF6C3F", "#293D49", "#BCC8CE"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    font_manager.fontManager.addfont("C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update({
        "font.family": "Microsoft YaHei", "font.size": 10,
        "mathtext.fontset": "stix", "pdf.fonttype": 42,
        "svg.fonttype": "none", "savefig.facecolor": "white",
        "axes.unicode_minus": False,
    })
    fig = plt.figure(figsize=(15.8 / 2.54, 6.8 / 2.54))
    ax = fig.add_axes([.065, .18, .915, .80])
    ax.set(xlim=(-1.05, 9.10), ylim=(-.82, 2.47))
    ax.set_axis_off()
    xs = np.arange(9, dtype=float)
    lower, upper = 0.0, 1.78

    # Every node lies on a row/column intersection. The darker radial endpoints
    # mark r=0 and r=R without claiming to illustrate their boundary stencils.
    for x in xs:
        ax.plot([x, x], [lower, upper], color=GRID, lw=.95, zorder=1)
    for y in (lower, upper):
        ax.plot([0, 8], [y, y], color=GRID, lw=.95, zorder=1)
    for x in (0, 8):
        ax.plot([x, x], [lower, upper], color="#81939E", lw=1.20, zorder=1)

    # Known state at the segment start, and the simultaneously solved new layer.
    ax.plot([0, 8], [upper, upper], color=ORANGE, lw=1.25, zorder=2)
    ax.scatter(xs, np.full_like(xs, lower), s=25, color=BLUE,
               edgecolors="white", linewidths=.55, zorder=4)
    ax.scatter(xs, np.full_like(xs, upper), s=35, facecolors="white",
               edgecolors=ORANGE, linewidths=1.35, zorder=4)

    # The interior startup residual has three nodes at each level. Arrows show
    # its actual old-state contribution, not implicit inverse-matrix influence.
    ax.plot([3, 5], [upper, upper], color=ORANGE, lw=3.05, zorder=3)
    for x in (3, 4, 5):
        ax.add_patch(FancyArrowPatch(
            (x, lower), (4, upper), arrowstyle="-|>", mutation_scale=11,
            shrinkA=7, shrinkB=10, linewidth=1.85, color=BLUE, zorder=3,
        ))
    ax.scatter([3, 4, 5], [lower] * 3, s=75, color=BLUE,
               edgecolors="white", linewidths=.9, zorder=5)
    ax.scatter([3, 4, 5], [upper] * 3, s=98, facecolors="white",
               edgecolors=ORANGE, linewidths=2.0, zorder=6)

    for x, index in ((3, "i-1"), (4, "i"), (5, "i+1")):
        ax.text(x, upper + .29, rf"$u_{{{index}}}^1$", ha="center",
                va="center", color=ORANGE, fontsize=12)
        ax.text(x, lower - .26, rf"$u_{{{index}}}^0$", ha="center",
                va="center", color=BLUE, fontsize=12)
    ax.text(-.18, lower, r"$t_s$", ha="right", va="center",
            fontsize=11.5, color=BLUE)
    ax.text(-.18, upper, r"$t_1$", ha="right", va="center",
            fontsize=11.5, color=ORANGE)
    ax.text(0, -.27, r"$0$", ha="center", va="center", fontsize=11.5, color=DARK)
    ax.text(8, -.27, r"$R$", ha="center", va="center", fontsize=11.5, color=DARK)

    # Offset axes retain visible endpoint nodes. This sole time interval is
    # adaptive and internal; it is not the one-second delivery sampling period.
    ax.add_patch(FancyArrowPatch((-.90, -.08), (-.90, 2.25), arrowstyle="-|>",
                                mutation_scale=10, linewidth=1.2, color=DARK))
    ax.text(-.90, 2.39, r"$t$", ha="center", va="center", fontsize=13, color=DARK)
    ax.add_patch(FancyArrowPatch((-.08, -.66), (8.51, -.66), arrowstyle="-|>",
                                mutation_scale=10, linewidth=1.2, color=DARK))
    ax.text(8.64, -.66, r"$r$", ha="center", va="center", fontsize=13, color=DARK)
    ax.plot([8.39, 8.39], [lower, upper], color=DARK, lw=.9)
    for y in (lower, upper):
        ax.plot([8.31, 8.47], [y, y], color=DARK, lw=.9)
    ax.text(8.55, (upper + lower) / 2, r"$\Delta t$", ha="left",
            va="center", fontsize=11, color=DARK)
    ax.plot([1, 2], [-.17, -.17], color=DARK, lw=.9)
    for x in (1, 2):
        ax.plot([x, x], [-.11, -.23], color=DARK, lw=.9)
    ax.text(1.5, -.33, r"$\Delta r$", ha="center", va="center",
            fontsize=11, color=DARK)

    handles = [
        Line2D([], [], marker="o", ls="none", ms=5.7, color=BLUE, label="已知值"),
        Line2D([], [], marker="o", ls="none", ms=6.1, mfc="white", mec=ORANGE,
               mew=1.5, label="待求值"),
        Line2D([], [], marker=">", ms=5, lw=1.7, color=BLUE, label="已知项输入"),
    ]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(.535, .019),
               ncol=3, frameon=False, handletextpad=.5, columnspacing=1.55,
               handlelength=1.6, fontsize=9.1)

    OUT.mkdir(parents=True, exist_ok=True)
    outputs = {}
    for ext in ("png", "pdf", "svg"):
        path = OUT / f"{STEM}.{ext}"
        fig.savefig(path, dpi=360)
        outputs[ext] = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
    for label in fig.findobj(Text):
        label.set_visible(False)
    path = OUT / f"{STEM}_no_text.png"
    fig.savefig(path, dpi=360)
    outputs["no_text"] = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
    path = OUT / f"{STEM}_gray.png"
    Image.open(OUT / f"{STEM}.png").convert("L").save(path)
    outputs["gray"] = {"path": path.relative_to(ROOT).as_posix(), "sha256": sha(path)}
    plt.close(fig)

    sources = ("docs/Q1/solution_brief.md", "src/Q1/solve.py")
    scipy_path = ROOT / ".venv/Lib/site-packages/scipy/integrate/_ivp/bdf.py"
    record = {
        "figure_id": STEM, "data_driven_visual": False, "size_cm": [15.8, 6.8],
        "sources": {path: sha(ROOT / path) for path in sources},
        "algorithm_source": {
            "path": scipy_path.relative_to(ROOT).as_posix(), "sha256": sha(scipy_path),
            "selection": "kappa[1]=-0.185, alpha[1]=1.185, D[0]=u^0, D[1]=dt*f(t_s,u^0)",
        },
        "generator": {"path": Path(__file__).relative_to(ROOT).as_posix(),
                      "sha256": sha(__file__)},
        "mapping": {
            "axes": "horizontal radial coordinate r; vertical internal integration time t",
            "levels": "only segment start t_s and its first internal step t_1=t_s+dt",
            "known_level": "u^0, solid blue at all radial node intersections",
            "unknown_level": "u^1, open orange at all radial node intersections; solved together",
            "local_stencil": "interior i-1, i, i+1 at both levels; no boundary stencil is depicted",
            "upper_link": "f_i(t_1,u^1) depends on the three nearest spatial values implicitly",
            "three_arrows": "direct known contribution 1.185*u_i^0 + 0.185*dt*f_i(t_s,u^0), not inverse-matrix effects",
            "residual": "1.185*(u_i^1-u_i^0)-0.185*dt*f_i(t_s,u^0)-dt*f_i(t_1,u^1)=0",
            "spacing": "schematic uniform radial spacing; one schematic adaptive first time step, not saved output times",
            "scope": "Q1 scalar field and NDF1 initialization at each numerical integration segment; later adaptive orders omitted",
            "initial_uniformity": "some old-layer f_i values vanish for the initial physical uniform state; generic segment-start dependencies remain",
        },
        "outputs": outputs,
        "status": "working diagram using approved single-grid style; independent image review followed by parent page review",
    }
    (OUT / f"{STEM}_sources.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(OUT / f"{STEM}.png")


if __name__ == "__main__":
    main()
