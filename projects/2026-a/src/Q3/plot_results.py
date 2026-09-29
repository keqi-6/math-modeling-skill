"""Q3 moisture history and terminal threshold detail from accepted stored results.

Result consumer only: no solver, verifier, spreadsheet authoring or state writes.
Run after the Q3 workbook audit exists, through the exact authorized action.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

SOURCE_SHA = '79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b'
METADATA_SHA = '1608daaf85666c495d9d62eaf19d07ff385c45bf66c58c598773e3769318871f'
POSITIONS = [0, 5, 10, 15, 20]
COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#343434']
STYLES = ['-', '--', '-.', ':', (0, (5, 1, 1, 1))]
MARKERS = ['o', 's', '^', 'D', 'v']


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def require(ok, message):
    if not bool(ok):
        raise ValueError(message)


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def identify(path, root):
    path = Path(path).resolve()
    try:
        name = path.relative_to(root).as_posix()
    except ValueError:
        name = str(path)
    return {'path': name, 'sha256': digest(path), 'size': path.stat().st_size}


def choose_font(explicit, labels):
    from matplotlib import font_manager, ft2font
    folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    candidates = [explicit] if explicit else [folder / 'msyh.ttc', folder / 'simhei.ttf', folder / 'simsun.ttc']
    required = {ord(c) for text in labels for c in text if '\u4e00' <= c <= '\u9fff'}
    for p in candidates:
        if p.is_file() and required.issubset(ft2font.FT2Font(str(p)).get_charmap()):
            font_manager.fontManager.addfont(str(p))
            return p, font_manager.FontProperties(fname=str(p)).get_name()
    raise ValueError('A font covering all Chinese labels is required')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output-dir', type=Path, default=Path('output/Q3'))
    parser.add_argument('--font', type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    output = (root / args.output_dir).resolve()
    require(output == (root / 'output/Q3').resolve(), 'Only the admitted Q3 output directory is supported')
    png, manifest_path = output / 'field_evolution.png', output / 'figure_manifest.json'
    require(not png.exists() and not manifest_path.exists(), 'Preserve existing figure identities')
    result = root / 'output/Q2/run_n10240_startsafe.npz'
    metadata_path = result.with_suffix('.json')
    specification = root / 'planning/Q3/model_spec.md'
    summary_path, audit_path = output / 'summary_values.json', output / 'workbook_audit.json'
    require(digest(result) == SOURCE_SHA and digest(metadata_path) == METADATA_SHA, 'Original numerical source identity changed')
    state = read_json(root / '.modeling/state.json')
    spec_hash = digest(specification)
    for path, expected in ((result, SOURCE_SHA), (specification, spec_hash)):
        record = state['artifacts'].get(path.relative_to(root).as_posix(), {})
        require(record.get('identity_class') == 'frozen' and record.get('status') == 'validated' and record.get('sha256') == expected, 'A frozen validated source/specification is required')
    meta, summary, audit = read_json(metadata_path), read_json(summary_path), read_json(audit_path)
    require(summary['input_npz_sha256'] == SOURCE_SHA and summary['specification']['sha256'] == spec_hash, 'Q3 summary source/specification mismatch')
    require(audit.get('data_status') == 'pass' and audit.get('input_npz_sha256') == SOURCE_SHA and audit.get('specification', {}).get('sha256') == spec_hash, 'Q3 workbook numerical audit is not current and passing')
    check = audit['independent_verification']['terminal_verification']
    end = meta['n_end']
    require(end == 206927 and check.get('status') == 'pass' and check.get('first_passing_integer_s') == end, 'Independent terminal evidence is missing')
    require(meta['threshold_kg_kg'] == .15 and summary['n_end_s'] == end, 'Threshold/terminal semantics changed')
    with np.load(result, allow_pickle=False) as archive:
        seconds = archive['time_s'][:end + 1].copy()
        radius = archive['radius_m'].copy()
        moisture = archive['moisture_kg_kg'][:end + 1, POSITIONS].copy()
        maxima = archive['max_moisture_kg_kg'][:end + 1].copy()
        event_index = meta['snapshot_roles']['threshold_crossing']
        event_time = float(archive['snapshot_time_s'][event_index])
        event_maximum = float(archive['moisture_snapshots'][event_index].max())
    require(np.array_equal(seconds, np.arange(end + 1)) and moisture.shape == (end + 1, 5), 'Wrong plotting sample axes')
    require(np.isfinite(moisture).all() and np.isfinite(maxima).all(), 'Nonfinite plotting data')
    require(abs(event_time - meta['t_cross_s']) <= 1e-12 and abs(event_maximum - .15) <= 5e-10, 'Crossing marker differs from stored full snapshot')
    source_identities = {'result': identify(result, root), 'metadata': identify(metadata_path, root),
                         'specification': identify(specification, root), 'summary': identify(summary_path, root),
                         'workbook_audit': identify(audit_path, root), 'generator': identify(__file__, root)}

    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'cumcm-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    labels = ['固定半径的含水率历程', '全节点最大值', '终点放大', '时间', '含水率', '干基',
              '阈值', '距中心', '高于阈值的量', '距', '的时间', '整数秒', '连续穿越']
    font_path, font_name = choose_font(args.font, labels)
    plt.rcParams.update({'font.family': font_name, 'font.size': 9.5, 'axes.unicode_minus': False,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#273546', 'text.color': '#273546',
                         'xtick.color': '#526174', 'ytick.color': '#526174',
                         'path.simplify': False, 'agg.path.chunksize': 20000})
    fig = plt.figure(figsize=(7.5, 3.8))
    grid = fig.add_gridspec(1, 2, left=.112, right=.975, top=.872, bottom=.285, wspace=.43)
    a, b = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
    hours = seconds / 3600
    handles = []
    for j, (color, style, marker) in enumerate(zip(COLORS, STYLES, MARKERS)):
        line, = a.plot(hours, moisture[:, j], color=color, linestyle=style, linewidth=1.35,
                       marker=marker, markevery=21600, markersize=3.1,
                       markerfacecolor='white', markeredgewidth=.75)
        handles.append(line)
    a.axhline(.15, color='#777777', linewidth=.9, linestyle=(0, (2, 3)))
    a.text(end / 3600 - 1, .18, '阈值 0.15', ha='right', va='bottom', fontsize=7.8, color='#666666')
    a.set(xlim=(0, end / 3600), ylim=(0, 2.65), xlabel='时间 / h', ylabel='含水率 $C$ / (kg/kg，干基)')
    a.set_xticks([0, 12, 24, 36, 48])
    a.set_title('(a) 固定半径的含水率历程', loc='left', fontsize=9.6, pad=8)

    chosen = np.arange(end - 5, end + 1)
    offsets = chosen - end
    excess = (maxima[chosen] - .15) * 1e6
    b.plot(offsets, excess, color='#222222', linewidth=1.05, marker='o', markersize=3.9,
           markerfacecolor='white', markeredgewidth=.9, label='整数秒')
    b.axhline(0, color='#777777', linewidth=.9, linestyle=(0, (2, 3)), label='阈值')
    b.plot(event_time - end, (event_maximum - .15) * 1e6, marker='D', linestyle='none',
           color='#222222', markerfacecolor='white', markersize=4.4, label='连续穿越')
    b.annotate(f'{end-1} s\n{maxima[end-1]:.10f}', xy=(-1, excess[-2]), xytext=(-25, 60),
               textcoords='offset points', ha='right', va='bottom', fontsize=7.8,
               arrowprops={'arrowstyle': '-', 'color': '#666666', 'linewidth': .65})
    b.annotate(f'{end} s\n{maxima[end]:.10f}', xy=(0, excess[-1]), xytext=(-16, -2),
               textcoords='offset points', ha='right', va='center', fontsize=7.8,
               arrowprops={'arrowstyle': '-', 'color': '#666666', 'linewidth': .65})
    b.set(xlim=(-5.3, .4), ylim=(-.65, 1.5), xlabel=f'距 {end} s 的时间 / s',
          ylabel='高于阈值的量 / (10$^{-6}$ kg/kg)')
    b.set_xticks([-5, -4, -3, -2, -1, 0])
    b.set_title('(b) 全节点最大值：终点放大', loc='left', fontsize=9.6, pad=8)
    b.legend(frameon=False, fontsize=7.8, loc='upper right', handlelength=2.1)
    for axis in (a, b):
        axis.grid(color='#dce2e9', linewidth=.55, alpha=.7)
        axis.set_axisbelow(True)
    fig.legend(handles, [f'r = {100 * radius[i]:g} cm' for i in POSITIONS], title='距中心',
               ncol=5, frameon=False, fontsize=8.5, title_fontsize=8.5,
               loc='lower center', bbox_to_anchor=(.55, .015), handlelength=2.6,
               columnspacing=1.15, handletextpad=.45)
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=240, facecolor='white')
    plt.close(fig)
    require(digest(result) == SOURCE_SHA and digest(specification) == spec_hash, 'Source changed while drawing')
    manifest = {'schema_version': '1.0', 'question': 'Q3', 'visual_id': 'Q3_MOISTURE_AND_TERMINAL',
                'data_driven_visual': True, 'created_at': datetime.now(timezone.utc).isoformat(),
                'purpose': 'Relate the full moisture history to the strict whole-node endpoint that four-decimal output cannot resolve.',
                'supported_claim': 'A slowly drying interior controls completion; the last two integer seconds straddle the strict threshold in the stored nominal trajectory.',
                'source_identities': source_identities, 'generation_argv': [sys.executable, *sys.argv],
                'consumers': ['docs/Q3/solution_brief.md:7.3'],
                'table_relation': 'Table5 provides exact 6h and terminal queries; the figure supplies full temporal structure and enlarged threshold differences.',
                'panels': [{'id': 'a', 'interval_s': [0, end], 'field': 'moisture_kg_kg', 'columns': POSITIONS, 'sample_count_per_radius': end + 1},
                           {'id': 'b', 'interval_s': [end - 5, end], 'field': 'max_moisture_kg_kg', 'node_scope': 'All 10241 original mesh nodes',
                            'seconds': chosen.tolist(), 'unrounded_maxima': maxima[chosen].tolist(), 'scaled_threshold_excess': excess.tolist(),
                            'crossing_marker': {'time_s': event_time, 'max_moisture_kg_kg': event_maximum, 'source': 'Stored full-mesh crossing snapshot'}}],
                'transformations': ['Panel a uses every stored integer second through actual endpoint; seconds converted to hours.',
                                    'Panel b subtracts n_end from time and scales (M_N-0.15) by 1e6; all six integer values are displayed.',
                                    'The crossing marker comes from its separate stored snapshot; connecting integer points is a visual aid, not a newly fitted trajectory.',
                                    'No smoothing, altered result values or new model run.'],
                'visual_encoding': {'radius_cm': (radius[POSITIONS] * 100).tolist(), 'colors': COLORS, 'line_styles': [str(s) for s in STYLES], 'markers': MARKERS,
                                    'radius_encoding': 'Same five radius styles as earlier accepted Q2 plots',
                                    'global_maximum': 'Black open circles at integer seconds; open diamond at continuous crossing', 'threshold': 'Grey dashed line'},
                'font': {'family': font_name, 'file': str(font_path.resolve()), 'sha256': digest(font_path), 'glyph_coverage': 'All planned Chinese labels covered'},
                'matplotlib_version': matplotlib.__version__,
                'target': {'width_mm': 190.5, 'height_mm': 96.52, 'dpi': 240, 'pixels': [1800, 912], 'smallest_font_pt': 7.8, 'minimum_main_linewidth_pt': 1.05},
                'outputs': [identify(png, root)],
                'caption_draft': '问题3主情景的含水率历程与严格终点。左图为五个固定半径的未舍入轨迹，灰线为0.15阈值；右图放大全节点最大值在最后几秒的阈值差，并标出连续穿越事件。右图缩放仅用于分辨严格比较，不增加数值精度。',
                'claim_boundary': ['The strict endpoint is for the selected N10240 trajectory; neighboring grids differ by one integer second.', 'The two panels have different vertical scales and time units.'],
                'acceptance': {'numerical_source_binding': 'Passing Q3 workbook audit and unchanged frozen numerical source/specification checked',
                               'independent_png_visual_review': 'pending', 'grayscale_review': 'pending', 'final_manuscript_size_review': 'pending', 'formal_visual_acceptance': 'not claimed'}}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'figure': str(png), 'manifest': str(manifest_path), 'visual_review': 'pending actual inspection'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
