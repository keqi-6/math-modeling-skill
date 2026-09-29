"""Internal property-surface sample from Appendix 3 and the existing Q2 run.

No external image values, no solver execution, and no submission-file writes.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, Normalize
from matplotlib.lines import Line2D
from matplotlib.text import Text
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/Q2/run_n10240_startsafe.npz'
OUT = ROOT / 'planning/internal_visual_reference_20260912'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    font = Path('C:/Windows/Fonts/msyh.ttc')
    font_manager.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(font)).get_name(),
        'font.size': 9, 'axes.unicode_minus': False, 'mathtext.fontset': 'stix',
        'svg.fonttype': 'none', 'axes.linewidth': .8, 'figure.facecolor': 'white'})
    with np.load(SOURCE, allow_pickle=False) as z:
        ids = np.flatnonzero((z['time_s'] <= 10800) & (z['time_s'] % 60 == 0))
        time = z['time_s'][ids]
        path_t = z['temperature_C'][ids][:, [0, -1]]
        path_c = z['moisture_kg_kg'][ids][:, [0, -1]]
    t = np.linspace(28., 50., 101)
    c = np.linspace(1., 2.55, 101)
    TT, CC = np.meshgrid(t, c)
    D = 2.4e-3 * np.exp(-.45 / CC - 3850 / (TT + 273.15))
    K = .21 + .38 * CC / (1 + CC)
    assert np.all(np.diff(D, axis=0) > 0) and np.all(np.diff(D, axis=1) > 0)
    assert np.all(np.diff(K, axis=0) > 0) and np.all(np.diff(K, axis=1) == 0)
    assert path_c.min() >= c.min() and path_c.max() <= c.max() + 1e-14
    cmap = LinearSegmentedColormap.from_list('lake', ['#E9F2F5', '#ACD2DD', '#4B97B0', '#205D79'])
    fig = plt.figure(figsize=(17.2/2.54, 9.1/2.54))
    axes = [fig.add_subplot(121, projection='3d', computed_zorder=False),
            fig.add_subplot(122, projection='3d', computed_zorder=False)]
    fig.subplots_adjust(left=.015, right=.99, bottom=.16, top=.98, wspace=.02)
    meta = []
    for idx, ax in enumerate(axes):
        values = D * 1e9 if idx == 0 else K
        floor = 3.0 if idx == 0 else .37
        top = 14.5 if idx == 0 else .495
        norm = Normalize(values.min(), values.max())
        ax.plot_surface(TT, CC, values, cmap=cmap, norm=norm, rcount=51, ccount=51,
                        linewidth=0, antialiased=True, shade=False, alpha=.94, zorder=2)
        ax.contourf(TT, CC, values, zdir='z', offset=floor, levels=14,
                    cmap=cmap, norm=norm, alpha=.77, zorder=1)
        ax.contour(TT, CC, values, zdir='z', offset=floor, levels=6,
                   colors='#648493', linewidths=.45, zorder=1)
        for j, style in enumerate(['-', '--']):
            local = 2.4e-3*np.exp(-.45/path_c[:, j]-3850/(path_t[:, j]+273.15))*1e9 if idx == 0 else .21+.38*path_c[:, j]/(1+path_c[:, j])
            lift = .08 if idx == 0 else .0008
            ax.plot(path_t[:, j], path_c[:, j], local+lift, color='white', lw=2.8, zorder=4)
            ax.plot(path_t[:, j], path_c[:, j], local+lift, color='#283D49', lw=1.4,
                    ls=style, zorder=5)
            marker = [int(np.flatnonzero(time == s)[0]) for s in [1800, 5400, 10800]]
            ax.scatter(path_t[marker, j], path_c[marker, j], local[marker]+lift,
                       marker='o' if j == 0 else 's', s=15, color='#C06A4E',
                       edgecolors='white', linewidths=.6, depthshade=False, zorder=6)
        ax.view_init(elev=26, azim=-57)
        ax.set_box_aspect((1.12, 1, .75))
        ax.set_xlim(28, 50); ax.set_ylim(1, 2.55); ax.set_zlim(floor, top)
        ax.set_xticks([30, 40, 50]); ax.set_yticks([1.2, 1.6, 2, 2.55])
        ax.set_zticks([4, 8, 12] if idx == 0 else [.38, .42, .46, .49])
        ax.set_xlabel(r'$T$ / °C', labelpad=0)
        ax.set_ylabel(r'$C$ / (kg/kg)', labelpad=1)
        ax.set_zlabel('')
        ax.text2D(.01, .94, '(a)' if idx == 0 else '(b)', transform=ax.transAxes,
                  fontsize=12, fontweight='bold')
        ax.text2D(.14, .94, r'$D$ / ($10^{-9}$ m²/s)' if idx == 0 else r'$k$ / (W/(m·K))',
                  transform=ax.transAxes, fontsize=9)
        ax.tick_params(axis='both', which='major', pad=0, labelsize=8)
        for axis in [ax.xaxis, ax.yaxis, ax.zaxis]:
            axis.set_pane_color((.98, .985, .99, 1))
            axis._axinfo['grid']['color'] = (.80, .85, .87, .5)
            axis._axinfo['grid']['linewidth'] = .45
        meta.append({'quantity': 'D' if idx == 0 else 'k',
                     'minimum': float((D if idx == 0 else K).min()),
                     'maximum': float((D if idx == 0 else K).max())})
    fig.legend(handles=[Line2D([], [], color='#283D49', lw=1.6, marker='o', ms=4, label='中心状态轨迹'),
                        Line2D([], [], color='#283D49', lw=1.6, ls='--', marker='s', ms=4, label='表面状态轨迹')],
               ncol=2, frameon=False, loc='lower center', bbox_to_anchor=(.5, .015), fontsize=8.5)
    stem = 'property_response_sample'
    for ext in ['png', 'svg']:
        fig.savefig(OUT / f'{stem}.{ext}', dpi=300)
    with Image.open(OUT / f'{stem}.png') as raster:
        raster.convert('L').save(OUT / f'{stem}_grayscale.png')
        small = raster.copy()
        small.thumbnail((1130, 1130))
        small.save(OUT / f'{stem}_page_width.png')
    for text in fig.findobj(Text): text.set_visible(False)
    fig.savefig(OUT / f'{stem}_no_text.png', dpi=150)
    plt.close(fig)
    np.savez_compressed(OUT/'property_response_data.npz', temperature_C=TT, moisture_kg_kg=CC,
                        D_m2_s=D, k_W_m_K=K, time_s=time, path_temperature_C=path_t, path_moisture_kg_kg=path_c)
    report = {'role': 'internal visual-design sample; not part of briefs or submissions',
              'data_driven_visual': True, 'source': SOURCE.relative_to(ROOT).as_posix(),
              'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'formula': 'Original problem Appendix 3', 'state_rectangle': {'T_C': [28, 50], 'C_kg_kg': [1, 2.55]},
              'domain_meaning': 'Constitutive function evaluated over a rectangle containing the first-three-hour states; all rectangle pairs are not claimed to have occurred in the PDE trajectory.',
              'trajectories': 'Minute samples of the existing center/surface states, 0 to 10800 s; markers at 0.5,1.5,3 h.',
              'rendering': 'Small vertical line offset only prevents z-fighting; constitutive values and plane projections are unaltered.',
              'normalization': 'No normalization; D axis displays physical D times 1e9.',
              'mathematical_checks': 'D increases with C and T; k increases with C and is constant along T.',
              'qa_views': ['property_response_sample.png', 'property_response_sample_no_text.png',
                           'property_response_sample_grayscale.png', 'property_response_sample_page_width.png'],
              'quantity_ranges': meta,
              'generator_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT/'property_sample_metadata.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(OUT/stem)


if __name__ == '__main__': main()
