"""Plot official observations and descriptive diagnostics; no fitted drying model."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile

os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'cumcm-matplotlib'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/diagnostics'
BLUE, ORANGE, GREY = '#24689B', '#BD642C', '#6B7280'


def read_source(relative, columns):
    path = ROOT / relative
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    book = load_workbook(path, read_only=True, data_only=False)
    try:
        rows = list(book.active.values)
        if any(len(row) != columns for row in rows):
            raise ValueError(f'Unexpected column count: {relative}')
        values = np.asarray(rows[1:], dtype=float)
    finally:
        book.close()
    if not np.isfinite(values).all() or not (np.diff(values[:, 0]) > 0).all():
        raise ValueError(f'Invalid values or time ordering: {relative}')
    return values, {'path': relative, 'sha256': sha, 'records': len(values),
                    'units_source': 'A题.pdf 第3页附录1'}


def axes_style(ax, x, y, title):
    ax.set(xlabel=x, ylabel=y, title=title)
    ax.grid(axis='y', color='#DDE2E7', linewidth=.65)
    ax.set_axisbelow(True)
    ax.spines[['top', 'right']].set_visible(False)
    ax.tick_params(labelsize=10)
    ax.title.set_fontsize(12)


def save(fig, name, note):
    fig.text(.06, .025, note, fontsize=9, color='#4B5563', va='bottom')
    fig.savefig(OUT / f'{name}.png', dpi=180, facecolor='white')
    fig.savefig(OUT / f'{name}.svg', facecolor='white')
    plt.close(fig)


def main():
    font = Path('C:/Windows/Fonts/msyh.ttc')
    if not font.exists():
        raise FileNotFoundError('Chinese chart font missing: Microsoft YaHei')
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(font)).get_name(),
                         'font.size': 11, 'axes.unicode_minus': False,
                         'svg.fonttype': 'path', 'axes.titlelocation': 'left'})
    env, env_id = read_source('附件/附件1.xlsx', 3)
    geo, geo_id = read_source('附件/附件2.xlsx', 2)
    OUT.mkdir(parents=True, exist_ok=True)
    h = env[:, 0] / 3600
    early = env[:, 0] <= 1800
    fig, ax = plt.subplots(2, 2, figsize=(11.2, 7.8))
    fig.subplots_adjust(left=.085, right=.975, bottom=.12, top=.94, wspace=.30, hspace=.42)
    for j, (col, color, label) in enumerate([(1, BLUE, '烘房温度 / °C'), (2, ORANGE, '空气水分浓度 / (kg/kg)')]):
        ax[0, j].plot(h, env[:, col], color=color, linewidth=1.15, marker='o', markersize=2.0)
        ax[0, j].axvspan(0, .5, color='#CCDCE9', alpha=.35, zorder=0)
        axes_style(ax[0, j], '时间 / h', label, f'({chr(97+j)}) 全部 241 个原始节点')
        ax[0, j].set_xlim(0, 4)
        ax[0, j].set_xticks(np.arange(0, 4.1, .5))
        ax[1, j].plot(env[early, 0] / 60, env[early, col], color=color, linewidth=1.2,
                      marker='o', markersize=3.2, markerfacecolor='white', markeredgewidth=.8)
        axes_style(ax[1, j], '时间 / min', label, f'({chr(99+j)}) 问题1：前 30 min 的 31 个节点')
        ax[1, j].set_xlim(0, 30)
    save(fig, 'environment_history', '来源：附件1，Sheet1!A2:C242。上排浅色区域为前30 min；下排采用局部纵轴范围。\n点为观测，连线仅帮助追踪时间顺序，未平滑或拟合。空气数据不是药材内部含水率。')

    gh, radius = geo[:, 0] / 3600, geo[:, 1]
    rates = -np.diff(radius) / np.diff(gh)
    midpoints = (gh[:-1] + gh[1:]) / 2
    fig = plt.figure(figsize=(11.2, 8.2))
    grid = fig.add_gridspec(2, 2, left=.085, right=.975, bottom=.13, top=.94, hspace=.43, wspace=.26)
    a, b, c = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, :])
    a.plot(gh, radius, color=BLUE, marker='o', markersize=2.1, linewidth=1.15)
    axes_style(a, '时间 / h', '药材半径 / cm', '(a) 72 h 半径观测')
    a.set_xlim(0, 72)
    a.set_xticks(np.arange(0, 73, 12))
    first = gh <= 4
    b.plot(gh[first], radius[first], color=BLUE, marker='o', markersize=4,
           markerfacecolor='white', linewidth=1.1)
    axes_style(b, '时间 / h', '药材半径 / cm', '(b) 前 4 h：与附件1同一时间范围')
    b.set_xlim(0, 4)
    b.annotate(f'0.5 h：{radius[1]:.3f} cm\n半径减少 {(1-radius[1]/radius[0])*100:.2f}%',
               xy=(gh[1], radius[1]), xytext=(1.4, 1.89), fontsize=10,
               arrowprops={'arrowstyle': '->', 'color': GREY, 'lw': .8})
    c.plot(midpoints, rates, color=ORANGE, marker='s', markersize=2.5, linewidth=.9,
           markerfacecolor='white')
    c.axhline(0, color=GREY, lw=.7)
    axes_style(c, '相邻观测区间中点 / h', '区间平均收缩速率 / (cm/h)', '(c) 半小时差分：−ΔR/Δt')
    c.set_xlim(0, 72)
    c.set_xticks(np.arange(0, 73, 6))
    late = midpoints >= 24
    inset = c.inset_axes([.54, .40, .42, .44])
    inset.plot(midpoints[late], rates[late], color=ORANGE, marker='s', markersize=2.4,
               linewidth=.65, markerfacecolor='white')
    inset.set(xlim=(24, 72), ylim=(-.0002, .0022), xticks=[24, 36, 48, 60, 72],
              yticks=[0, .001, .002], title='24–72 h 局部放大（同单位）')
    inset.tick_params(labelsize=8)
    inset.title.set_fontsize(9)
    inset.grid(axis='y', color='#DDE2E7', linewidth=.5)
    inset.spines[['top', 'right']].set_visible(False)
    save(fig, 'shrinkage_history', '来源：附件2，Sheet1!A2:B146。半径每0.5 h记录一次；速率是区间平均值，不是瞬时导数。\n半径记录保留三位小数，长段相同读数不能证明水分已达标；题面将附件2用于问题4。')

    windows = []
    for lo, hi in [(0, .5), (.5, 1), (1, 2), (2, 3), (3, 4)]:
        v = env[(h >= lo) & (h <= hi)]
        windows.append({'hours': [lo, hi], 'nodes': len(v),
                        'temperature_start_end_C': v[[0, -1], 1].tolist(),
                        'air_moisture_start_end_kg_kg': v[[0, -1], 2].tolist(),
                        'temperature_range_C': [float(v[:, 1].min()), float(v[:, 1].max())],
                        'air_moisture_range_kg_kg': [float(v[:, 2].min()), float(v[:, 2].max())]})
    stats = {'kind': 'descriptive_input_diagnostics', 'inputs': [env_id, geo_id],
             'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
             'environment_windows': windows,
             'radius_0_cm': float(radius[0]), 'radius_30min_cm': float(radius[1]),
             'radius_72h_cm': float(radius[-1]),
             'radius_fraction_decrease_30min': float(1-radius[1]/radius[0]),
             'radius_fraction_decrease_72h': float(1-radius[-1]/radius[0]),
             'radius_decreasing_intervals': int(np.count_nonzero(np.diff(radius) < 0)),
             'radius_unchanged_intervals': int(np.count_nonzero(np.diff(radius) == 0)),
             'radius_increasing_intervals': int(np.count_nonzero(np.diff(radius) > 0)),
             'maximum_interval_shrinkage_cm_h': float(rates.max()),
             'geometry_sample_hours': gh.tolist(), 'radius_cm': radius.tolist(),
             'interval_midpoint_hours': midpoints.tolist(), 'interval_shrinkage_cm_h': rates.tolist(),
             'limitations': ['No treatment, fit or drying simulation.',
                             'Common timestamps do not establish a paired specimen or experiment.',
                             'A recorded radius plateau does not establish moisture equilibrium.']}
    (OUT/'input_stats.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for relative, record in [('附件/附件1.xlsx', env_id), ('附件/附件2.xlsx', geo_id)]:
        if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() != record['sha256']:
            raise RuntimeError('Source changed during reading')
    print(json.dumps({'outputs': ['environment_history.png', 'shrinkage_history.png'],
                      'radius_30min_decrease_percent': 100*stats['radius_fraction_decrease_30min'],
                      'environment_windows': windows}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
