"""Draw accepted Q2 fields and extract the official 6-by-5 summary tables.

This is a result consumer: it never imports or executes a model or validator.
Run only after the root workflow has frozen the numerical result and reports.
The PNG still requires actual visual inspection; its existence is not acceptance.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np

TIMES = np.arange(1800, 10801, 1800, dtype=np.int64)
POSITIONS = np.array([0, 5, 10, 15, 20], dtype=np.int64)
COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#343434']
STYLES = ['-', '--', '-.', ':', (0, (5, 1, 1, 1))]
MARKERS = ['o', 's', '^', 'D', 'v']


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def relative_or_absolute(path, root):
    path = Path(path).resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def identify(path, root):
    path = Path(path).resolve()
    return dict(path=relative_or_absolute(path, root), sha256=digest(path), size=path.stat().st_size)


def require_frozen(path, root, state):
    key = Path(path).resolve().relative_to(root).as_posix()
    record = state['artifacts'].get(key, {})
    if (record.get('identity_class') != 'frozen' or record.get('status') != 'validated'
            or record.get('sha256') != digest(path)):
        raise ValueError('A current frozen, validated identity is required: ' + key)


def require_report(path, root, state, result, metadata):
    require_frozen(path, root, state)
    report = read_json(path)
    if report.get('question') != 'Q2' or report.get('mode') != 'full_process':
        raise ValueError('A full-process Q2 verification report is required')
    checks = report.get('checks', [])
    if report.get('passed') is not True or not checks or any(c.get('passed') is not True for c in checks):
        raise ValueError('The verification report contains failed or missing checks')
    for source, expected in report.get('identities', {}).items():
        p = Path(source)
        p = p if p.is_absolute() else root / p
        if not p.is_file() or digest(p) != expected:
            raise ValueError('Verification source identity is stale: ' + str(p))
    result_hash, meta_hash = digest(result), digest(metadata)
    matches = [record for record in report.get('details', {}).get('run_identities', [])
               if record.get('result_sha256') == result_hash
               and record.get('metadata_sha256') == meta_hash]
    if not matches:
        raise ValueError('The verification report does not bind this exact result and metadata')
    return report


def rounded_string(value):
    return format(Decimal.from_float(float(value)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), '.4f')


def extreme(values, time_s, radius_m, which):
    flat = int(np.argmin(values) if which == 'minimum' else np.argmax(values))
    i, j = np.unravel_index(flat, values.shape)
    return dict(value=float(values[i, j]), time_s=int(time_s[i]), radius_m=float(radius_m[j]),
                scope='21 output radii at integer-second samples through n_end')


def radial_spread(values, time_s, radius_m):
    differences = values.max(axis=1) - values.min(axis=1)
    i = int(differences.argmax())
    return dict(maximum=float(differences[i]), time_s=int(time_s[i]),
                radius_at_maximum_m=float(radius_m[int(values[i].argmax())]),
                radius_at_minimum_m=float(radius_m[int(values[i].argmin())]),
                scope='21 output radii; not a claim about every continuous radius')


def prepare(args):
    root = args.project_root.resolve()
    paths = [args.result, args.metadata, args.boundary, *args.verification]
    result, metadata, boundary_path = [p.resolve() for p in paths[:3]]
    state = read_json(root / '.modeling/state.json')
    for p in paths:
        require_frozen(p, root, state)
    meta, boundary = read_json(metadata), read_json(boundary_path)
    if meta.get('success') is not True or meta.get('scenario') != 'mean_tail':
        raise ValueError('Use the successful primary mean_tail run for the official Q2 figure')
    if meta.get('result_sha256') != digest(result) or meta.get('boundary_sha256') != digest(boundary_path):
        raise ValueError('Metadata does not bind the current result and boundary')
    source_contracts = {'spec_sha256': root / 'planning/Q2/model_spec.md',
                        'raw_environment_sha256': root / '附件/附件1.xlsx',
                        'solver_sha256': root / 'src/Q2/solve.py'}
    for key, path in source_contracts.items():
        if meta.get(key) != digest(path):
            raise ValueError('Result source differs from the current source: ' + key)
    reports = [require_report(p, root, state, result, metadata) for p in args.verification]
    if not {'E1', 'E2', 'E3'}.issubset(set().union(*(set(p.get('axes', [])) for p in reports))):
        raise ValueError('Full-process E1/E2 and E3 evidence must accompany the primary result')
    with np.load(result, allow_pickle=False) as archive:
        data = {key: archive[key] for key in (
            'time_s', 'radius_m', 'mesh_radius_m', 'temperature_C', 'moisture_kg_kg',
            'max_moisture_kg_kg', 'max_moisture_node', 'max_moisture_radius_m',
            'temperature_mean', 'moisture_mean', 'snapshot_time_s',
            'temperature_snapshots', 'moisture_snapshots')}
    n_end = meta['n_end']
    if isinstance(n_end, bool) or not isinstance(n_end, int) or n_end < 10800:
        raise ValueError('The strict endpoint must cover all six official summary times')
    t, r = data['time_s'], data['radius_m']
    if not np.array_equal(t, np.arange(len(t))) or n_end >= len(t):
        raise ValueError('The input must contain every integer second through n_end')
    if r.shape != (21,) or np.max(np.abs(r - np.arange(21) * .001)) > 1e-15:
        raise ValueError('The official 21 radial output locations are missing')
    for key in ('temperature_C', 'moisture_kg_kg'):
        a = data[key]
        if a.shape != (len(t), 21) or not np.isfinite(a).all():
            raise ValueError('Invalid field array: ' + key)
    maxima = data['max_moisture_kg_kg']
    threshold = float(meta['threshold_kg_kg'])
    if threshold != .15 or maxima.shape != t.shape or not np.isfinite(maxima).all():
        raise ValueError('Invalid all-node maximum or threshold')
    first = np.flatnonzero((t > 0) & (maxima < threshold))
    if len(first) == 0 or int(first[0]) != n_end or maxima[n_end - 1] < threshold:
        raise ValueError('Stored all-node maxima contradict the first strict integer endpoint')
    roles = meta['snapshot_roles']
    for role, expected in [('before_n_end', n_end - 1), ('n_end', n_end)]:
        index = int(roles[role])
        if data['snapshot_time_s'][index] != expected:
            raise ValueError('Incorrect endpoint snapshot role')
        if abs(float(data['moisture_snapshots'][index].max()) - float(maxima[expected])) > 1e-13:
            raise ValueError('Endpoint maximum does not agree with the full mesh snapshot')
    return root, result, metadata, boundary_path, meta, boundary, data, state['revision']


def make_summary(root, result, metadata, boundary_path, args, meta, data, revision):
    stop = int(meta['n_end'])
    time_s, radius_m = data['time_s'][:stop + 1], data['radius_m']
    sources = dict(result=identify(result, root), metadata=identify(metadata, root),
                   boundary=identify(boundary_path, root),
                   verification=[identify(p, root) for p in args.verification],
                   generator=identify(__file__, root))
    tables, fields = {}, {}
    for key, unit in [('temperature_C', 'degC'), ('moisture_kg_kg', 'kg/kg dry basis')]:
        selected = data[key][np.ix_(TIMES, POSITIONS)]
        tables[key] = dict(time_s=TIMES.tolist(), time_h=(TIMES / 3600).tolist(),
                           radius_m=radius_m[POSITIONS].tolist(), radius_cm=(radius_m[POSITIONS] * 100).tolist(),
                           values=selected.tolist(), display_4dp=[[rounded_string(v) for v in row] for row in selected],
                           units=unit, source_selector='field[np.ix_([1800,3600,5400,7200,9000,10800],[0,5,10,15,20])]')
        a = data[key][:stop + 1]
        fields[key] = dict(units=unit, minimum=extreme(a, time_s, radius_m, 'minimum'),
                           maximum=extreme(a, time_s, radius_m, 'maximum'),
                           first_3h_maximum_radial_spread=radial_spread(a[:10801], time_s[:10801], radius_m),
                           full_process_maximum_radial_spread=radial_spread(a, time_s, radius_m),
                           at_3h=dict(center=float(a[10800, 0]), surface=float(a[10800, -1]),
                                      surface_minus_center=float(a[10800, -1] - a[10800, 0])),
                           at_n_end=dict(center=float(a[stop, 0]), surface=float(a[stop, -1]),
                                         surface_minus_center=float(a[stop, -1] - a[stop, 0])))
    endpoint = dict(threshold_kg_kg=float(meta['threshold_kg_kg']), t_cross_s=float(meta['t_cross_s']),
                    n_end=stop, n_end_h=stop / 3600, n_end_days=stop / 86400,
                    common_end_s=int(meta['common_end_s']),
                    criterion='First positive integer n with max over all N+1 mesh nodes C(n) < 0.15; raw float64 values')
    for label, t in [('before', stop - 1), ('at', stop)]:
        endpoint[label] = dict(time_s=t, max_moisture_kg_kg=float(data['max_moisture_kg_kg'][t]),
                               max_node=int(data['max_moisture_node'][t]),
                               max_radius_m=float(data['max_moisture_radius_m'][t]),
                               strict_below_threshold=bool(data['max_moisture_kg_kg'][t] < .15))
    event_index = int(meta['snapshot_roles']['threshold_crossing'])
    event_c = data['moisture_snapshots'][event_index]
    endpoint['crossing_snapshot'] = dict(time_s=float(data['snapshot_time_s'][event_index]),
                                        max_moisture_kg_kg=float(event_c.max()),
                                        max_radius_m=float(data['mesh_radius_m'][int(event_c.argmax())]))
    return dict(schema_version='1.0', question='Q2', scenario=meta['scenario'], grid_n=int(meta['grid_n']),
                created_at=datetime.now(timezone.utc).isoformat(), checked_state_revision=revision,
                sources=sources, tables=tables, endpoint=endpoint, fields=fields,
                trajectory_extrema_as_recorded=dict(values=meta.get('observed_extrema'), scope=meta.get('extrema_scope')),
                interpretation_limits=['Conditional prediction of Q2-v1 under the chosen continuation.',
                                       'No E4 empirical accuracy or per-cell correct-rounding guarantee.',
                                       'Field extrema/spreads here use 21 radii; endpoint maxima use every mesh node.',
                                       'n_end is the Q2 workbook endpoint; this file does not promote or deliver Q3.'])


def choose_font(font_path, labels):
    from matplotlib import font_manager, ft2font
    if font_path:
        candidates = [font_path]
    else:
        folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        candidates = [folder / 'msyh.ttc', folder / 'simhei.ttf', folder / 'simsun.ttc']
    required = {ord(c) for text in labels for c in text if '\u4e00' <= c <= '\u9fff'}
    for p in candidates:
        if p.is_file():
            cmap = ft2font.FT2Font(str(p)).get_charmap()
            if required.issubset(cmap):
                font_manager.fontManager.addfont(str(p))
                return p, font_manager.FontProperties(fname=str(p)).get_name()
    raise ValueError('A Chinese font containing every required label is needed; supply --font')


def draw(args, root, meta, boundary, data, png):
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'cumcm-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    labels = ['时间', '温度', '含水率', '干基', '前', '全程', '环境温度', '全网格最大值', '达标阈值', '距中心']
    font_path, font_name = choose_font(args.font, labels)
    plt.rcParams.update({'font.family': font_name, 'font.size': 9.5, 'axes.unicode_minus': False,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#273546', 'text.color': '#273546',
                         'xtick.color': '#526174', 'ytick.color': '#526174',
                         'path.simplify': False, 'agg.path.chunksize': 20000})
    fig = plt.figure(figsize=(7.5, 6.7))
    grid = fig.add_gridspec(2, 2, left=.112, right=.975, top=.943, bottom=.145,
                          hspace=.54, wspace=.37, height_ratios=[1, 1.12])
    a, b, c = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1]), fig.add_subplot(grid[1, :])
    short_t = data['time_s'][:10801] / 3600
    stop = int(meta['n_end'])
    long_t = data['time_s'][:stop + 1] / 3600
    handles = []
    for number, (index, color, style, marker) in enumerate(zip(POSITIONS, COLORS, STYLES, MARKERS)):
        common = dict(color=color, linestyle=style, linewidth=1.35, marker=marker,
                      markersize=3.1, markerfacecolor='white', markeredgewidth=.75)
        line, = a.plot(short_t, data['temperature_C'][:10801, index], markevery=1800, **common)
        handles.append(line)
        b.plot(short_t, data['moisture_kg_kg'][:10801, index], markevery=1800, **common)
        c.plot(long_t, data['moisture_kg_kg'][:stop + 1, index],
               markevery=max(1, stop // 12), **common)
    env_t = np.asarray(boundary['time_s'], dtype=float)
    mask = env_t <= 10800
    a.plot(env_t[mask] / 3600, np.asarray(boundary['temperature_C'])[mask],
           color='#888888', linewidth=.95, linestyle=(0, (2, 2)), label='环境温度')
    a.legend(frameon=False, fontsize=8.2, loc='lower right')
    max_line, = c.plot(long_t, data['max_moisture_kg_kg'][:stop + 1], color='#111111',
                       linewidth=.85, linestyle=(0, (7, 3)), label='全网格最大值')
    threshold_line = c.axhline(float(meta['threshold_kg_kg']), color='#777777',
                              linewidth=1.05, linestyle=(0, (2, 3)), label='达标阈值 0.15')
    c.legend(handles=[max_line, threshold_line], frameon=False, fontsize=8.2, loc='upper right')
    for ax, title in [(a, '(a) 前 3 h：温度'), (b, '(b) 前 3 h：含水率'), (c, '(c) 全程：含水率')]:
        ax.set_title(title, loc='left', fontsize=10, pad=8)
        ax.set_xlabel('时间 / h')
        ax.grid(color='#dce2e9', linewidth=.55, alpha=.7)
        ax.set_axisbelow(True)
    a.set(xlim=(0, 3), ylabel='温度 $\\theta$ / °C')
    b.set(xlim=(0, 3), ylabel='含水率 $C$ / (kg/kg，干基)')
    c.set(xlim=(0, stop / 3600), ylabel='含水率 $C$ / (kg/kg，干基)')
    for ax in (a, b):
        ax.set_xticks([0, 1, 2, 3])
    fig.legend(handles, [f'r = {100 * data["radius_m"][i]:g} cm' for i in POSITIONS],
               title='距中心', ncol=5, frameon=False, fontsize=8.5, title_fontsize=8.5,
               loc='lower center', bbox_to_anchor=(.55, .022), handlelength=2.6,
               columnspacing=1.15, handletextpad=.45)
    fig.savefig(png, dpi=240, facecolor='white')
    plt.close(fig)
    return dict(family=font_name, file=str(font_path.resolve()), sha256=digest(font_path),
                chinese_glyph_coverage='all planned Chinese labels present in font character map',
                visual_glyph_check='pending actual PNG inspection'), matplotlib.__version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--result', required=True, type=Path)
    parser.add_argument('--metadata', required=True, type=Path)
    parser.add_argument('--boundary', required=True, type=Path)
    parser.add_argument('--verification', required=True, nargs='+', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--font', type=Path)
    args = parser.parse_args()
    args.project_root = args.project_root.resolve()
    for name in ('result', 'metadata', 'boundary', 'output_dir', 'font'):
        p = getattr(args, name)
        if p is not None and not p.is_absolute():
            setattr(args, name, args.project_root / p)
    args.verification = [p if p.is_absolute() else args.project_root / p for p in args.verification]
    root, result, metadata, boundary_path, meta, boundary, data, revision = prepare(args)
    output = args.output_dir.resolve()
    output.relative_to((root / 'output/Q2').resolve())
    png, summary_path, manifest_path = [output / p for p in ('field_evolution.png', 'summary_values.json', 'figure_manifest.json')]
    if any(p.exists() for p in (png, summary_path, manifest_path)):
        raise FileExistsError('Existing figure identities must not be overwritten; use a fresh output directory')
    summary = make_summary(root, result, metadata, boundary_path, args, meta, data, revision)
    output.mkdir(parents=True, exist_ok=True)
    font, matplotlib_version = draw(args, root, meta, boundary, data, png)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    manifest = dict(schema_version='1.0', question='Q2', visual_id='Q2_FIELD_EVOLUTION', data_driven_visual=True,
        created_at=datetime.now(timezone.utc).isoformat(), checked_state_revision=revision,
        purpose='How do the five radial positions respond during the first 3 h, and how does the whole-grid maximum reach the full-process moisture threshold?',
        supported_claim='Quantitative temperature/moisture histories and the stored all-node stopping criterion under Q2-v1.',
        source_identities=summary['sources'], generator=identify(__file__, root),
        generation_argv=[sys.executable, *sys.argv],
        consumers=['docs/Q2/solution_brief.md: model solution/results; placement to be reviewed'],
        table_relation='The 6-by-5 tables provide exact queries; the figure shows time evolution and radial separation between table rows.',
        panels=[dict(id='a', interval_s=[0, 10800], field='temperature_C', columns=POSITIONS.tolist(), environment='original nodes 0..10800 s'),
                dict(id='b', interval_s=[0, 10800], field='moisture_kg_kg', columns=POSITIONS.tolist()),
                dict(id='c', interval_s=[0, meta['n_end']], field='moisture_kg_kg', columns=POSITIONS.tolist(),
                     extra_series=['max_moisture_kg_kg over all N+1 mesh nodes', 'threshold_kg_kg from metadata'])],
        transformations=['seconds to hours; metres to centimetres in legend',
                         'all integer-second source samples plotted; no smoothing, interpolation or field rounding',
                         'metadata common_end beyond n_end excluded from the formal-process figure',
                         'display_4dp is a separate Decimal-from-float ROUND_HALF_UP view; raw values remain unchanged'],
        visual_encoding=dict(radius_cm=(data['radius_m'][POSITIONS] * 100).tolist(), colors=COLORS,
                             line_styles=[str(s) for s in STYLES], markers=MARKERS,
                             radius_encoding='same colors, line styles and markers in all panels',
                             units='Temperature degC; moisture kg/kg dry basis; time hours; radius cm'),
        font=font, matplotlib_version=matplotlib_version,
        target=dict(width_mm=190.5, height_mm=170.18, dpi=240, pixels=[1800, 1608],
                    smallest_font_pt=8.2, minimum_main_linewidth_pt=1.35),
        outputs=[identify(png, root), identify(summary_path, root)],
        caption_draft='问题2主情景的径向温湿响应。前两面板显示前3小时的五个半径位置及原始环境温度；第三面板显示相同位置的全程含水率、全部网格节点的最大含水率及0.15阈值。全程截至首个全节点严格达标的整数秒；所有曲线取自同一未舍入数值结果。',
        claim_boundary=summary['interpretation_limits'],
        acceptance=dict(numerical_sources='frozen validated identities and passing full-process reports checked',
                        independent_png_visual_review='pending', grayscale_review='pending',
                        final_manuscript_size_review='not yet embedded; pending at actual placement',
                        caption_and_placement='draft; no manuscript was changed', formal_visual_acceptance='not claimed'))
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps(dict(png=str(png), summary=str(summary_path), manifest=str(manifest_path),
                          visual_review='pending'), ensure_ascii=False))


if __name__ == '__main__':
    main()
