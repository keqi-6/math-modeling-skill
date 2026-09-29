"""Generate Q4 teammate-facing timeline and sensitivity figures."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/fig"

INK = "#253342"
GRAY = "#7B8794"
LIGHT = "#E8EDF2"
BLUE = "#2878B5"
GREEN = "#2E9D6F"
ORANGE = "#E79727"
RED = "#D64B40"
COLORS = ("#2878B5", "#7B61A8", "#2E9D6F")


def configure() -> None:
    font_path = Path("/mnt/c/Windows/Fonts/simhei.ttf")
    if font_path.exists():
        fm.fontManager.addfont(font_path)
        font_name = fm.FontProperties(fname=font_path).get_name()
    else:
        font_name = "DejaVu Sans"
    plt.rcParams.update({
        "font.family": font_name,
        "font.size": 10.5,
        "axes.unicode_minus": False,
        "svg.fonttype": "none",
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "xtick.color": INK,
        "ytick.color": INK,
    })


def save(fig, stem: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / f"{stem}.svg", bbox_inches="tight", facecolor="white")
    fig.savefig(OUT / f"{stem}.png", dpi=240, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def service_timeline(result: dict) -> None:
    decision = result["formal_best"]["decision"]["platforms"]
    individuals = result["verification"]["individuals"]
    joint = result["formal_best"]["densified_intervals_s"]
    rows = (3, 2, 1)
    fig, ax = plt.subplots(figsize=(11.2, 4.9))

    for index, (platform, single, y, color) in enumerate(zip(decision, individuals, rows, COLORS)):
        release = platform["release_time_s"]
        explosion = platform["explosion_time_s"]
        active_end = min(explosion + 20.0, 67.8)
        ax.barh(y, active_end - explosion, left=explosion, height=0.32, color=LIGHT, edgecolor="none", zorder=1)
        ax.plot(release, y, marker="v", ms=7, color=ORANGE, zorder=4)
        ax.plot(explosion, y, marker="D", ms=6, color=RED, zorder=4)
        for left, right in single["intervals_s"]:
            ax.barh(y, right - left, left=left, height=0.34, color=color, edgecolor="white", linewidth=0.8, zorder=3)
            ax.text((left + right) / 2, y, f"{right-left:.3f} s", ha="center", va="center", color="white", fontsize=9.4, zorder=5)
        ax.text(active_end + 0.35, y, "烟团有效期", va="center", color=GRAY, fontsize=8.7)

    for left, right in joint:
        ax.barh(0, right - left, left=left, height=0.38, color=GREEN, edgecolor="white", linewidth=0.8)
    ax.text(17.0, -0.52, f"区间并集测度  {result['formal_best']['densified_duration_s']:.6f} s",
            ha="center", color=INK, fontsize=10.4)

    ax.scatter([], [], marker="v", color=ORANGE, label="投放时刻")
    ax.scatter([], [], marker="D", color=RED, label="起爆时刻")
    ax.barh([], [], color=LIGHT, label="起爆后 20 s 有效期")
    ax.barh([], [], color=GREEN, label="完整遮蔽服务窗")
    ax.set_yticks([0, 1, 2, 3], ["三平台联合", "FY3", "FY2", "FY1"])
    ax.set_xlim(0, 49)
    ax.set_ylim(-0.9, 3.75)
    ax.set_xlabel("时间 / s")
    ax.set_title("Q4 三平台投放—起爆—完整遮蔽服务时间轴", loc="left", fontsize=14, fontweight="bold", pad=10)
    ax.text(0.0, 1.015, "灰带表示烟团物理有效期，彩色实条表示满足完整圆柱判据的实际服务窗",
            transform=ax.transAxes, color=GRAY, fontsize=9.4)
    ax.grid(axis="x", color="#D7DEE5", linewidth=0.7, alpha=0.85)
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.legend(loc="upper right", frameon=False, ncol=4, fontsize=8.6, bbox_to_anchor=(1.0, 1.16))
    fig.tight_layout()
    save(fig, "fig_q4_service_timeline")


def sensitivity_windows(data: dict) -> None:
    ranking = data["risk_ranking"]
    top = ranking[:3]
    fig, axes = plt.subplots(1, 2, figsize=(12.0, 5.7), gridspec_kw={"width_ratios": [1.08, 1.0]})

    labels = [f"{row['platform']}—{ {'heading_deg':'航向','speed_mps':'速度','release_time_s':'投放时刻','fuse_delay_s':'引信时长'}[row['factor']] }" for row in ranking]
    retention = np.array([100 * row["minimum_window_retention_ratio"] for row in ranking])
    colors = [RED if value == 0 else ORANGE if value < 90 else GREEN for value in retention]
    positions = np.arange(len(ranking))[::-1]
    axes[0].barh(positions, retention, color=colors, height=0.68)
    axes[0].axvline(90, color=INK, linestyle="--", linewidth=1.0)
    axes[0].set_yticks(positions, labels)
    axes[0].set_xlim(0, 104)
    axes[0].set_xlabel("登记扰动内最差窗口保留率 / %")
    axes[0].set_title("(a) 十二组平台—变量风险排序", loc="left", fontweight="bold")
    axes[0].grid(axis="x", color="#D7DEE5", linewidth=0.7)
    for y, value in zip(positions, retention):
        axes[0].text(min(value + 1.3, 98.0), y, f"{value:.1f}%", va="center", color=INK, fontsize=8.8)

    for row, color in zip(data["critical_offsets"], COLORS):
        factor = row["factor"]
        maximum = max(abs(value) for value in data["grids"][factor])
        x_values, y_values = [], []
        for direction in row["directions"]:
            for sample in direction["samples"]:
                x_values.append(sample["offset"] / maximum)
                y_values.append(100 * sample["retention_ratio"])
        order = np.argsort(x_values)
        label = f"{row['platform']}—{ {'speed_mps':'速度','release_time_s':'投放时刻','fuse_delay_s':'引信时长'}[factor] }"
        axes[1].plot(np.asarray(x_values)[order], np.asarray(y_values)[order], marker="o", ms=4.5, lw=2.0, color=color, label=label)
    axes[1].axhline(90, color=INK, linestyle="--", linewidth=1.0, label="90% 保留线")
    axes[1].axhline(0, color=GRAY, linewidth=0.8)
    axes[1].axvline(0, color=GRAY, linewidth=0.8)
    axes[1].set_xlim(-1.04, 1.04)
    axes[1].set_ylim(-3, 104)
    axes[1].set_xticks([-1, -0.5, 0, 0.5, 1], ["负向上限", "-50%", "名义值", "+50%", "正向上限"])
    axes[1].set_ylabel("受扰平台服务窗保留率 / %")
    axes[1].set_title("(b) 三个首要风险的窗口退化过程", loc="left", fontweight="bold")
    axes[1].grid(color="#D7DEE5", linewidth=0.7)
    axes[1].legend(frameon=False, fontsize=8.8, loc="lower center")

    for ax in axes:
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
    fig.suptitle("Q4 固定方案灵敏度：从总时长追溯到具体服务窗", x=0.07, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.07, 0.925, "红色表示登记扰动内窗口消失，橙色表示低于 90%，绿色表示仍保留至少 90%",
             color=GRAY, fontsize=9.5)
    fig.tight_layout(rect=(0, 0, 1, 0.90), w_pad=3.2)
    save(fig, "fig_q4_sensitivity_windows")


def main() -> int:
    configure()
    result = json.loads((ROOT / "docs/q4_result.json").read_text(encoding="utf-8"))
    sensitivity = json.loads((ROOT / "docs/q4_sensitivity_results.json").read_text(encoding="utf-8"))
    service_timeline(result)
    sensitivity_windows(sensitivity)
    print(json.dumps({
        "status": "pass",
        "outputs": [
            "docs/fig/fig_q4_service_timeline.svg", "docs/fig/fig_q4_service_timeline.png",
            "docs/fig/fig_q4_sensitivity_windows.svg", "docs/fig/fig_q4_sensitivity_windows.png",
        ],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
