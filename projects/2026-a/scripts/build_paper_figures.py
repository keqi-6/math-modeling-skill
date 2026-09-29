"""Reproduce the eight manuscript figures from existing, unrounded results.

No solver is called. Run from any directory with the project's Python runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, Ellipse, Rectangle
from matplotlib.ticker import FixedLocator, ScalarFormatter
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/paper_figures/v1"
FONT = Path("C:/Windows/Fonts/msyh.ttc")
font_manager.fontManager.addfont(str(FONT))
plt.rcParams.update({
    "font.family": font_manager.FontProperties(fname=str(FONT)).get_name(),
    "font.size": 9, "axes.labelsize": 9, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "legend.fontsize": 8, "axes.titlesize": 9,
    "mathtext.fontset": "stix", "axes.unicode_minus": False,
    "axes.linewidth": .85, "lines.linewidth": 1.8,
    "xtick.direction": "in", "ytick.direction": "in",
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
    "savefig.facecolor": "white", "figure.facecolor": "white",
})
# Distinct engineering-plot hues, with dark gray for the surface series.
COLORS = ["#0072BD", "#D95319", "#3A923A", "#7E2F8E", "#333333"]
STYLES = ["-", "--", "-.", ":", (0, (5, 1, 1, 1))]
MARKERS = ["o", "s", "^", "D", "v"]
WIDTH = 15.8 / 2.54
FIGURES = {}
SOURCES = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source(rel, expected=None):
    p = ROOT / rel
    digest = sha(p)
    if expected and digest != expected:
        raise ValueError(f"Source identity changed: {rel}")
    SOURCES[rel] = {"sha256": digest, "bytes": p.stat().st_size}
    return p


def read_json(rel):
    return json.loads(source(rel).read_text(encoding="utf-8"))


def axes_pair(height=2.8):
    fig, axs = plt.subplots(1, 2, figsize=(WIDTH, height), layout="constrained")
    for ax in axs:
        ax.grid(True, color=".87", linewidth=.4)
        ax.set_axisbelow(True)
    return fig, axs


def tag(ax, letter, name):
    # Descriptive titles belong in the adjacent manuscript text/caption.
    ax.set_title(f"({letter})", loc="left", pad=7, fontweight="bold")


def upright_ylabels(fig):
    """Stack Chinese names, keeping units and mathematical expressions intact."""
    for ax in fig.axes:
        label = ax.get_ylabel()
        if " / " not in label:
            continue
        name, unit = label.split(" / ", 1)
        if not all("\u4e00" <= char <= "\u9fff" for char in name):
            continue
        ax.set_ylabel("\n".join(name) + "\n" + unit, rotation=0,
                      ha="right", va="center", labelpad=10)
        ax.yaxis.label.set_multialignment("center")
        ax.yaxis.label.set_linespacing(1.05)


def line(ax, x, y, i, label, markevery=None, **kw):
    ax.plot(x, y, color=COLORS[i % 5], linestyle=STYLES[i % 5],
            marker=MARKERS[i % 5] if markevery else None,
            markevery=markevery, markersize=3.2, markerfacecolor="white",
            markeredgewidth=.9, label=label, **kw)


def save(fig, name, title, caption, sources, transformations):
    OUT.mkdir(parents=True, exist_ok=True)
    upright_ylabels(fig)
    outputs = {}
    for ext in ("png", "pdf", "svg"):
        p = OUT / f"{name}.{ext}"
        fig.savefig(p, dpi=300, metadata={"Creator": "Project scientific figure generator"}
                    if ext == "pdf" else None)
        outputs[ext] = {"file": p.name, "sha256": sha(p), "bytes": p.stat().st_size}
    FIGURES[name] = {"title": title, "caption": caption, "sources": sources,
                     "transformations": transformations,
                     "width_cm": 15.8, "height_cm": fig.get_figheight() * 2.54,
                     "outputs": outputs}
    plt.close(fig)


def fig01():
    source("A题.pdf")
    source("docs/Q1/solution_brief.md")
    fig, axs = plt.subplots(1, 2, figsize=(WIDTH, 3.5),
                            gridspec_kw={"width_ratios": [1, 1.15]})
    fig.subplots_adjust(left=.035, right=.985, bottom=.07, top=.90, wspace=.15)
    a, b = axs
    for ax in axs:
        ax.set_axis_off()
    tag(a, "a", "圆柱中部径向模型（示意）")
    a.set_xlim(-.3, 4.0); a.set_ylim(-.5, 4.8); a.set_aspect("equal")
    # Cylinder projection, explicitly schematic (not to scale).
    for x in [.25, 3.30]:
        a.add_patch(Ellipse((x, 3.9), .40, .90, fill=False, ec=".25", lw=1.2))
    a.plot([.25, 3.3], [4.35, 4.35], color=".25", lw=1.2)
    a.plot([.25, 3.3], [3.45, 3.45], color=".25", lw=1.2)
    a.plot([-.05, 3.60], [3.9, 3.9], color=".6", ls="-.", lw=.8)
    a.add_patch(Ellipse((1.775, 3.9), .40, .90, fill=False, ec=COLORS[0], lw=1.6))
    a.annotate("", (3.30, 4.65), (.25, 4.65), arrowprops={"arrowstyle": "<->", "lw": .9})
    a.text(1.775, 4.71, r"$L=25\,\mathrm{cm}$", ha="center", va="bottom")
    a.plot([1.775, 1.775], [3.45, 2.72], color=".55", ls="--", lw=.8)
    center = (1.775, 1.5); R = 1.18
    a.add_patch(Circle(center, R, fill=False, ec=".2", lw=1.4))
    a.plot(*center, "o", color=".2", ms=3)
    a.plot([.40, 3.16], [1.5, 1.5], color=".7", ls="-.", lw=.8)
    a.annotate("", (2.94, 1.5), center, arrowprops={"arrowstyle": "->", "color": COLORS[0], "lw": 1.3})
    a.text(2.3, 1.65, r"$r$", ha="center")
    a.text(1.68, 1.28, r"$0$", ha="right")
    a.text(1.775, .05, r"$R=2\,\mathrm{cm}$", ha="center")
    a.text(1.775, -.35, "中心对称；表面与烘房环境交换", ha="center", fontsize=8)
    tag(b, "b", "径向节点与控制体（示意）")
    b.set_xlim(-.65, 5.95); b.set_ylim(-.55, 4.75)
    # The colored interval is the radial projection of an annular volume.
    y = 3.65
    b.add_patch(Rectangle((1.5, y-.28), 1.0, .56, fc=COLORS[0], alpha=.13, ec="none"))
    b.plot([.2, 3.9], [y, y], color=".2", lw=1.2)
    for x, label in [(1, r"$r_{i-1}$"), (2, r"$r_i$"), (3, r"$r_{i+1}$")]:
        b.plot(x, y, "o", color=".2", ms=3.5); b.text(x, y+.4, label, ha="center")
    for x, label in [(1.5, r"$a_i=r_{i-1/2}$"), (2.5, r"$b_i=r_{i+1/2}$")]:
        b.plot([x, x], [y-.36, y+.30], color=COLORS[0], lw=1.1)
        b.text(x + (-.27 if x < 2 else .38), y-.58, label, ha="center", fontsize=8)
    b.text(2, 2.45, r"$v_i=\int_{a_i}^{b_i}r\,\mathrm{d}r$", ha="center")
    b.text(2.1, 1.83, "端部控制体在实际边界截断", ha="center", fontsize=8)
    for x0, left, right, dot, label, below in [
        (0, 0, .55, 0, "中心", r"$a_0=0$"),
        (3.25, 0, .55, .55, "表面", r"$b_N=R$")]:
        yy = .94
        b.add_patch(Rectangle((x0+left, yy-.22), right-left, .44, fc=".91", ec=".4", lw=.9))
        b.plot(x0+dot, yy, "o", color=".15", ms=3.5)
        b.text(x0+.275, 1.43, label, ha="center", fontsize=8)
        b.text(x0+.275, .42, below, ha="center")
    b.text(2.2, -.23, r"$N$ 段径向网格，$N+1$ 个节点（$i=0,\ldots,N$）", ha="center", fontsize=8)
    save(fig, "fig01_radial_model", "圆柱中部径向模型与控制体",
         "圆柱及网格均为示意。控制体按径向位置截取圆环，中心与表面控制体分别截断于0与R；图中少量节点不代表正式网格数。",
         ["A题.pdf", "docs/Q1/solution_brief.md"],
         {"kind": "schematic", "geometry": "cylinder L=25 cm, R=2 cm; schematic projection", "indices": "i=0,...,N; ai,bi follow Q1 equation (7)", "no_flux_direction_claim": True})


def fig02():
    rel = "output/ENV/q2_boundary.json"; env = read_json(rel)
    source("附件/附件1.xlsx", env["source"]["sha256"])
    t = np.array(env["time_s"]) / 3600
    fig, axs = axes_pair(2.7)
    for ax, field, ylabel, title in zip(axs,
        ["temperature_C", "air_moisture_kg_kg"],
        ["烘房温度 / °C", "空气水分浓度 / (kg/kg)"], ["温度输入", "水分输入"]):
        y = np.array(env[field])
        ax.plot(t, y, color=COLORS[0], lw=1.7, label="分段线性重建", zorder=2)
        ax.scatter(t, y, s=2.5, color=".45", edgecolors="none", label="原始观测", zorder=3)
        ax.set(xlim=(0, 4), xlabel="时间 / h", ylabel=ylabel)
        ax.set_xticks(range(5)); tag(ax, "a" if ax is axs[0] else "b", title)
        ax.legend(loc="lower right", frameon=False, handlelength=2)
    save(fig, "fig02_environment", "烘房环境观测与分段线性重建",
         "两幅图分别表示附件1的温度与空气水分浓度。灰点为241个原始观测，蓝线为分段线性重建。图示0—4 h；Q1仅使用前0.5 h，Q2结果展示前三小时。",
         [rel, "附件/附件1.xlsx"], {"time_unit": "s/3600 -> h", "observations": len(t), "interpolation": "piecewise linear, no smoothing or extrapolation"})


def fig03():
    rel = "output/Q1/run_n5120.npz"
    p = source(rel, "c3eb65e2b2f1ccea870986401c5f1ae42346562be1fe11ace3e61104dc79cc7e")
    fig, axs = axes_pair(2.8)
    with np.load(p) as z:
        # Keep the existing 100/600/1800 s styles; add two intermediate profiles.
        for time, style_index in [(100, 0), (600, 1), (900, 3), (1200, 4), (1800, 2)]:
            k = np.flatnonzero(z["time_s"] == time).item()
            for ax, field in zip(axs, ["temperature_C", "moisture_kg_kg"]):
                line(ax, z["radius_m"]*100, z[field][k], style_index, f"{time} s", markevery=2)
    for ax, title, ylabel in zip(axs, ["温度径向剖面", "含水率径向剖面"], ["温度 / °C", "干基含水率 / (kg/kg)"]):
        tag(ax, "a" if ax is axs[0] else "b", title)
        ax.set(xlim=(-.04, 2.04), xlabel="半径 / cm", ylabel=ylabel)
        ax.set_xticks([0, .5, 1, 1.5, 2])
        ax.legend(frameon=False, loc="upper left" if ax is axs[0] else "lower left",
                  ncol=2, handlelength=2.7, columnspacing=1)
    save(fig, "fig03_q1_profiles", "Q1预热阶段温度与含水率的径向响应",
         "分别绘制100、600、900、1200、1800 s时的温度和干基含水率，均为题目规定的表格时刻。900、1200 s的剖面补充中间阶段的径向变化。每条曲线连接21个规定半径的未舍入计算值，稀疏标记用于识别曲线，未额外拟合。",
         [rel], {"times_s": [100, 600, 900, 1200, 1800], "radius_count": 21, "radius_unit": "m*100 -> cm", "extra_fit": False,
                 "style_indices_by_time_s": {"100": 0, "600": 1, "900": 3, "1200": 4, "1800": 2},
                 "legend": "two columns; chronological order down columns; temperature upper left, moisture lower left"})


def shared_path():
    return source("output/Q2/run_n10240_startsafe.npz", "79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b")


def fig04():
    fig, axs = axes_pair(3.2)
    with np.load(shared_path()) as z:
        mask = z["time_s"] <= 10800
        t = z["time_s"][mask]/3600; r = z["radius_m"]*100
        for j, (ax, field, title, unit, cmap) in enumerate(zip(axs,
            ["temperature_C", "moisture_kg_kg"], ["温度场", "含水率场"],
            ["温度 / °C", "干基含水率 / (kg/kg)"], ["cividis", "viridis"])):
            v = z[field][mask].T
            # Color bins use exactly the saved radii and integer seconds.
            mesh = ax.pcolormesh(t, r, v, shading="nearest", cmap=cmap, rasterized=True,
                                 vmin=float(v.min()), vmax=float(v.max()))
            cbar = fig.colorbar(mesh, ax=ax, orientation="horizontal",
                                fraction=.075, pad=.13, aspect=24)
            cbar.set_label(unit, fontsize=8); cbar.ax.tick_params(labelsize=8)
            ax.grid(False); ax.set(xlim=(0, 3), ylim=(0, 2), xlabel="时间 / h", ylabel="半径 / cm")
            ax.set_xticks([0, 1, 2, 3]); tag(ax, "ab"[j], title)
    save(fig, "fig04_q2_fields", "Q2前三小时温度与含水率的时空分布",
         "横轴为时间，纵轴为实际半径，色标分别表示温度与干基含水率。色场取前三小时逐秒保存的21个规定半径值，采用邻近色块显示；它不表示全部细网格节点的逐秒快照。",
         ["output/Q2/run_n10240_startsafe.npz"], {"time_s": [0, 10800], "time_stride_s": 1, "radius_count": 21, "display": "pcolormesh shading=nearest; color fields rasterized, labels vector"})


def fig05():
    s = read_json("output/Q3/summary_values.json"); end = int(s["n_end_s"])
    fig, ax = plt.subplots(figsize=(WIDTH, 3.55), layout="constrained")
    with np.load(shared_path()) as z:
        t = z["time_s"]; ids = np.flatnonzero((t <= end) & (t % 60 == 0))
        ids = np.unique(np.r_[ids, np.flatnonzero(t == end)])
        for j, r in enumerate([0, .005, .01, .015, .02]):
            col = np.flatnonzero(np.isclose(z["radius_m"], r)).item()
            line(ax, t[ids]/3600, z["moisture_kg_kg"][ids, col], j, f"{r*100:g} cm", markevery=120)
        ax.axhline(.15, color=".3", lw=1.05, ls="--")
        ax.text(4, .045, "达标阈值 0.15", fontsize=8, va="bottom")
        ax.set(xlim=(-.35, end/3600+.7), ylim=(0, 2.7), xlabel="时间 / h", ylabel="干基含水率 / (kg/kg)")
        ax.grid(True, color=".87", lw=.4)
        ax.legend(loc="upper right", title="固定半径", frameon=False, ncol=3, fontsize=8, title_fontsize=8)
        inset = ax.inset_axes([.58, .43, .37, .30])
        near = (t >= end-4) & (t <= end)
        delta = (z["max_moisture_kg_kg"][near]-.15)*1e6
        inset.plot(t[near]-end, delta, color=".2", marker="o", ms=3, lw=1.3)
        inset.axhline(0, color=".6", ls="--", lw=.9)
        inset.set(xlabel=r"$t-t_{\mathrm{end}}$ / s")
        inset.xaxis.label.set_size(8)
        inset.text(0, 1.04, r"$(M_N-0.15)\times10^6$", transform=inset.transAxes,
                   ha="left", va="bottom", fontsize=8)
        inset.set_xticks([-4, -2, -1, 0]); inset.tick_params(labelsize=8)
        inset.grid(True, color=".9", lw=.35)
        ax.text(.95, .27, f"结束时刻 {s['display_end_h']} h", transform=ax.transAxes,
                ha="right", fontsize=8)
        assert delta[-2] >= 0 and delta[-1] < 0
    save(fig, "fig05_q3_drying", "Q3完整干燥过程与全域达标判定",
         f"主图为五个固定半径的干基含水率历程。小图的M_N为全10241节点的最大含水率，{end-1} s尚未严格低于0.15，{end} s首次达标。微小差值只解释数值终点判据，不代表实际干燥时长具有秒级准确度。",
         ["output/Q3/summary_values.json", "output/Q2/run_n10240_startsafe.npz"],
         {"time_s": [0, end], "main_display_sampling": "every 60 s plus exact end", "inset_sampling": "every integer second from end-4 to end", "max_source": "saved maximum of all 10241 nodes, not five display curves"})


def fig06():
    rel = "output/GEOMETRY/q4_radius.json"; g = read_json(rel)
    source("附件/附件2.xlsx", g["source"]["sha256"])
    s = read_json("output/Q4/summary_values.json"); end = int(s["n_end_s"])
    t = np.array([n["time_s"] for n in g["nodes"]])/3600
    r = np.array([n["radius_cm"] for n in g["nodes"]])
    fig, axs = axes_pair(3.05)
    a, b = axs
    a.plot(t, r, color=COLORS[0], label="分段线性重建", lw=1.7)
    a.scatter(t, r, s=3, color=".45", label="外半径观测", zorder=3)
    a.axvline(end/3600, color=".4", lw=1.05, ls="--")
    a.text(end/3600-1.7, 1.94, "模型结束", ha="right", fontsize=8)
    a.legend(frameon=True, facecolor="white", edgecolor="white", framealpha=1,
             loc="center right", bbox_to_anchor=(.98,.70))
    a.set(xlim=(0,72), ylim=(1.15,2.04), xlabel="时间 / h", ylabel="外半径 / cm")
    a.set_xticks([0,18,36,54,72]); tag(a,"a","实测外半径及时间重建")
    b.grid(False); b.spines[["left", "right", "top"]].set_visible(False)
    b.set(xlim=(0,2.08), ylim=(-.35,2.7), xlabel="实际半径 / cm")
    b.set_xticks([0,.5,1,1.5,2]); b.set_yticks([])
    tag(b,"b","坐标对应（均匀缩放示意）")
    b.axvline(1.5, ymax=.90, color=COLORS[1], ls="--", lw=1.2)
    b.text(1.52,2.64,r"固定 $r=1.5$ cm",ha="right", fontsize=8, color=COLORS[1])
    for time, y, label in [(0,2.15,"0 h"),(6,1.25,"6 h"),(end/3600,.35,"结束时")]:
        rad = float(np.interp(time,t,r))
        b.plot([0,rad],[y,y],color=".35",lw=2.5,solid_capstyle="butt")
        b.plot(rad,y,marker="|",color=".15",ms=10)
        b.plot(.5*rad,y,marker="o",color=COLORS[0],ms=5,mfc="white",mew=1.2)
        b.text(.03,y+.17,f"{label}：R={rad:.3f} cm",fontsize=8)
    b.text(.38,-.2,r"○ 同一材料位置 $\xi=0.5$",color=COLORS[0],fontsize=8)
    save(fig,"fig06_q4_geometry","Q4外半径观测与收缩坐标对应",
         "左图展示附件2的0—72 h外半径观测，虚线标出当前模型结束时刻。右图按均匀径向缩放假设绘制r=R(t)ξ：同一ξ的位置随半径移动，固定r=1.5 cm在6 h时已位于材料外。三行仅排列时刻，内部位置不是实测数据。",
         [rel,"附件/附件2.xlsx","output/Q4/summary_values.json"],
         {"geometry_times_h":[0,6,end/3600],"radius_unit":"cm", "mapping":"r=R(t)*xi, xi=0.5; uniform radial scaling assumption", "fixed_probe_cm":1.5})


def fig07():
    s = read_json("output/Q4/summary_values.json"); end = int(s["n_end_s"])
    rel = "output/Q4/run_n10240-v1-20260911.npz"
    p = source(rel, s["input_npz_sha256"])
    fig, axs = axes_pair(3.15)
    a,b=axs
    with np.load(p) as z:
        ids = np.flatnonzero(z["time_s"]<=end); t=z["time_s"][ids]/3600
        for j,r in enumerate([0,.005,.01,.015]):
            col=np.flatnonzero(np.isclose(z["radius_m"],r)).item()
            v=np.where(z["inside_mask"][ids,col],z["moisture_kg_kg"][ids,col],np.nan)
            line(a,t,v,j,f"固定 {r*100:g} cm",markevery=180)
        line(a,t,z["surface_moisture_kg_kg"][ids],4,"实际表面",markevery=180)
        a.set(xlim=(-.7,end/3600+.7),ylim=(0,2.7),xlabel="时间 / h",ylabel="干基含水率 / (kg/kg)")
        a.legend(frameon=False,loc="upper right",fontsize=8)
        for j,time in enumerate([21600,64800,108000,151200,end]):
            k=np.flatnonzero(z["snapshot_time_s"]==time).item()
            x=z["mesh_xi"]*z["snapshot_radius_m"][k]*100
            y=z["moisture_snapshots"][k]
            label=f"{time/3600:g} h" if time!=end else "结束时"
            line(b,x,y,j,label)
            b.plot(x[-1],y[-1],marker=MARKERS[j],color=COLORS[j],ms=4,mfc="white",mew=1)
        b.set(xlim=(0,1.43),ylim=(0,2.7),xlabel="实际半径 / cm",ylabel="干基含水率 / (kg/kg)")
        b.legend(frameon=False,loc="upper right",fontsize=8)
        tag(a,"a","固定位置与实际表面历程"); tag(b,"b","当前材料内的径向剖面")
    save(fig,"fig07_q4_profiles","Q4收缩条件下的含水率演变",
         "左图采用固定物理位置和实际移动表面的含水率；固定位置移出材料后断线。右图为6、18、30、42 h及结束时的完整细网格剖面，横坐标是实际半径，各曲线端点为当时表面R(t)。",
         [rel,"output/Q4/summary_values.json"],
         {"time_s":[0,end],"fixed_radius_cm":[0,.5,1,1.5],"outside_domain":"masked by saved inside_mask, never zero filled", "profile_times_s":[21600,64800,108000,151200,end],"profile_radius":"mesh_xi * snapshot_radius_m *100 -> cm"})


def fig08():
    rel="output/Q1/verification_report.json"; report=read_json(rel)
    checks={c["name"]:c for c in report["checks"]}
    fig,axs=axes_pair(2.9)
    for j,(ax,field,title,unit) in enumerate(zip(axs,["temperature","moisture"],
        ["温度网格差","含水率网格差"],["最大绝对差 / °C","最大绝对差 / (kg/kg)"])):
        c=checks[field+"_spatial_differences_decrease"]["comparisons"]
        n=np.array([v["coarse_n"] for v in c]); d=np.array([v["max_abs"] for v in c])
        limit=checks[field+"_spatial_final_difference"]["limit"]
        ax.loglog(n,d,color=COLORS[j],marker=MARKERS[j],ms=4,mfc="white",label="相邻网格最大差")
        ax.axhline(limit,color=".4",ls="--",lw=1.05,label=r"预定标准 $2\times10^{-5}$")
        ax.set(xlabel=r"较粗网格段数 $N$",ylabel=unit,xlim=(135,3100))
        ax.set_xticks(n,labels=[str(v) for v in n]); ax.minorticks_off()
        tag(ax,"ab"[j],title);ax.legend(frameon=False,fontsize=8,loc="best")
    save(fig,"fig08_grid_convergence","Q1网格加密的数值一致性",
         "比较N与2N网格在全部1800×21个规定输出点上的最大绝对差。温度和含水率分别显示，虚线为已有预定检验标准。相邻网格差用于评价数值一致性，不是连续解误差的严格上界；本图只对应Q1。",
         [rel],{"source_fields":["checks.temperature_spatial_differences_decrease.comparisons","checks.moisture_spatial_differences_decrease.comparisons"],"maximum_over":"1800 times x 21 radii", "coarse_N":[160,320,640,1280,2560],"reference_slopes":False})


def catalogue():
    ordered=sorted(FIGURES)
    lines=["# 论文图件与使用入口", "", "八组图已插入四问队友讲解稿；这是供队伍选用的工作图件包。图号按各问内部编号，合稿时由队伍统一连续编号。", "",
           "[A4图件预览册](figure_catalog.pdf) · [LaTeX预览册源文件](figure_catalog.tex) · [来源及变换记录](figure_sources.json)", "",
           "所有图按15.8 cm宽设计。LaTeX建议使用PDF；Word可优先试用SVG，不兼容时用300 dpi PNG。正式题注由正文排版，勿截图复制预览册。", "",
           "主曲线加粗至1.7—1.8 pt，纵轴中文逐字竖排、字形正立，单位与数学式保持易读；图内不设描述性标题，仅保留子图编号及必要标注。离散曲线改用蓝、橙红、绿、紫、深灰，配合线型和标记区分，保持同一对象跨图一致。配色借鉴干燥领域论文以鲜明色相区分曲线的方式，具体色值按本图可读性选定；连续色场保留cividis/viridis。", "",
           "参考了干燥领域论文[Brasiello等（2021）](https://doi.org/10.3303/CET2187033)中分面表达、观测标记和曲线区分的方式；本图包全部数据与几何关系来自本项目，没有移用该论文的数值或图像。", ""]
    tex=[r"\documentclass[UTF8,a4paper,10pt]{ctexart}",r"\usepackage[margin=2.5cm]{geometry}",r"\usepackage{graphicx}",r"\usepackage{caption}",r"\usepackage{hyperref}",r"\setlength{\parindent}{0pt}",r"\pagestyle{plain}",r"\begin{document}"]
    for name in ordered:
        f=FIGURES[name]
        lines += ["## "+f["title"],"",f"[PDF]({name}.pdf) · [SVG]({name}.svg) · [PNG]({name}.png)","",f"![{f['title']}]({name}.png)","",f["caption"],""]
        tex += [r"{\large "+f["title"]+r"}\par\medskip",
                r"\includegraphics[width=15.8cm]{"+name+r".pdf}\par\smallskip",
                f["caption"].replace("_",r"\_").replace("ξ",r"$\xi$"),r"\par\bigskip"]
        if name != ordered[-1]: tex += [r"\newpage"]
    tex += [r"\end{document}"]
    (OUT/"index.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (OUT/"figure_catalog.tex").write_text("\n".join(tex)+"\n",encoding="utf-8")


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--only",nargs="*",type=int)
    args=parser.parse_args()
    for i,func in enumerate([fig01,fig02,fig03,fig04,fig05,fig06,fig07,fig08],1):
        if not args.only or i in args.only:
            func();print(f"Generated figure {i}")
    if not args.only:
        catalogue()
        manifest={"schema_version":"1.0","role":"G1 working manuscript figure package",
                  "generator":{"path":"scripts/build_paper_figures.py","sha256":sha(__file__)},
                  "source_files":SOURCES,"figures":FIGURES,
                  "style":{"main_linewidth_pt":1.8,"input_linewidth_pt":1.7,
                           "categorical_colors":COLORS,
                           "palette_reference":"https://doi.org/10.3303/CET2187033",
                           "palette_basis":"Distinct curve hues inspired by drying-paper figures; color values adapted for this project, not sampled from the paper.",
                           "continuous_colormaps":["cividis","viridis"],
                           "chinese_ylabels":"upright characters stacked vertically; units intact",
                           "in_image_titles":"panel identifiers only; descriptive titles in adjacent text"},
                  "claim_boundary":"Existing results visualized; no model change, no solver run, no new experimental validation. Final team manuscript acceptance is not asserted."}
        (OUT/"figure_sources.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")


if __name__=="__main__":
    main()
