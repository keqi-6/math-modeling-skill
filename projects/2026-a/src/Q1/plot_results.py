"""Render Q1's accepted unrounded fields; keep quantitative input/output identity."""
from pathlib import Path
import hashlib
import json
import os
import tempfile

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "cumcm-matplotlib"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    result = ROOT / "output/Q1/run_n5120.npz"
    verification = ROOT / "output/Q1/verification_report.json"
    state = json.loads((ROOT / ".modeling/state.json").read_text(encoding="utf-8"))
    identity = state["artifacts"].get("output/Q1/run_n5120.npz", {})
    if identity.get("sha256") != digest(result) or identity.get("identity_class") != "frozen":
        raise ValueError("Figure requires the accepted frozen numerical result")
    report = json.loads(verification.read_text(encoding="utf-8"))
    if not report["passed"]:
        raise ValueError("Numerical verification did not pass")
    with np.load(result) as z:
        t, r = z["time_s"] / 60, z["radius_m"] * 100
        temperature, moisture = z["temperature_C"], z["moisture_kg_kg"]
    boundary = json.loads((ROOT / "output/ENV/q1_boundary.json").read_text(encoding="utf-8"))
    font_manager.fontManager.addfont("C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update({"font.family": "Microsoft YaHei", "font.size": 10,
                         "axes.unicode_minus": False, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titleweight": "bold",
                         "svg.fonttype": "none", "axes.labelcolor": "#273546",
                         "text.color": "#273546", "xtick.color": "#526174",
                         "ytick.color": "#526174"})
    fig, axes = plt.subplots(2, 2, figsize=(12.6, 8.2))
    fig.subplots_adjust(top=.86, bottom=.11, left=.082, right=.975, hspace=.42, wspace=.25)
    fig.text(.082, .957, "问题1｜径向温度与含水率演化", fontsize=20, fontweight="bold")
    fig.text(.082, .916, "固定半径 2 cm  ·  固定热物性，D 随含水率变化  ·  0—30 min  ·  题给等效交换边界下的模型结果",
             fontsize=10.5, color="#637186")
    positions = [0, 5, 10, 15, 20]
    times = [100, 300, 600, 900, 1200, 1500, 1800]
    for row, (values, cmap, label, unit) in enumerate([
        (temperature, "YlOrRd", "温度", "℃"),
        (moisture, "Blues", "含水率", "kg/kg（干基）"),
    ]):
        left, right = axes[row]
        colors = plt.get_cmap(cmap)(np.linspace(.40, .92, 5))
        for index, color in zip(positions, colors):
            left.plot(t, values[:, index], color=color, lw=1.8, label=f"r = {r[index]:g} cm")
        if row == 0:
            left.plot([x["time_s"] / 60 for x in boundary["nodes"]],
                      [x["temperature_C"] for x in boundary["nodes"]],
                      color="#677384", linestyle="--", lw=1.3, label="环境温度")
        left.set(xlim=(0, 30), xlabel="时间 / min", ylabel=f"{label} / {unit}")
        left.set_title(f"{'a' if row == 0 else 'c'}  不同半径位置的{label}", loc="left", pad=10)
        left.legend(ncol=3, frameon=False, fontsize=8, loc="best", columnspacing=1)
        for tt, color in zip(times, plt.get_cmap(cmap)(np.linspace(.32, .94, len(times)))):
            right.plot(r, values[tt], lw=1.8, color=color, label=f"{tt} s")
        right.set(xlim=(0, 2), xlabel="距中心的半径 / cm", ylabel=f"{label} / {unit}")
        right.set_xticks([0, .5, 1, 1.5, 2])
        right.set_title(f"{'b' if row == 0 else 'd'}  代表时刻的径向分布", loc="left", pad=10)
        right.legend(ncol=3, frameon=False, fontsize=8, loc="best", columnspacing=1)
        for ax in (left, right):
            ax.grid(color="#dce2e9", linewidth=.65, alpha=.7)
            ax.set_axisbelow(True)
    fig.text(.082, .033, "曲线由未舍入数值解直接生成。温度向内传播较快；30 min 内，含水率下降主要集中在外层。",
             fontsize=10, color="#59687c")
    output = ROOT / "output/Q1"
    paths = [output / "field_evolution.png", output / "field_evolution.svg"]
    fig.savefig(paths[0], dpi=180, facecolor="white")
    fig.savefig(paths[1], facecolor="white")
    plt.close(fig)
    manifest = {
        "schema_version": "1.0", "question": "Q1", "role": "data_visualization",
        "purpose": "Inspect radial nonuniformity and the difference between temperature and moisture time scales",
        "source": {"path": result.relative_to(ROOT).as_posix(), "sha256": digest(result)},
        "verification": {"path": verification.relative_to(ROOT).as_posix(), "sha256": digest(verification)},
        "generator": {"path": "src/Q1/plot_results.py", "sha256": digest(__file__)},
        "consumer": "docs/Q1/solution_brief.md",
        "transformations": "time seconds to minutes; radius metres to centimetres; no smoothing or field rounding",
        "curves": {"time_history_radius_cm": [0, .5, 1, 1.5, 2], "profile_time_s": times},
        "claim_boundary": "Predictions under Q1-v1; no experimental agreement is claimed",
        "outputs": [{"path": p.relative_to(ROOT).as_posix(), "sha256": digest(p)} for p in paths],
    }
    (output / "figure_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("Rendered Q1 field histories and radial profiles")


if __name__ == "__main__":
    main()
