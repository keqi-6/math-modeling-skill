"""Review and plot the user-confirmed Q2 interval without running a model.

The sole numerical scope is 0..10800 s at the prescribed 21 output radii.
Run only through the root's exact authorized, bounded runtime action.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time

import numpy as np

END = 10800
FIELDS = ('temperature_C', 'moisture_kg_kg')
UNITS = {'temperature_C': 'degC', 'moisture_kg_kg': 'kg water/kg dry solid'}
TIMES = np.arange(1800, END + 1, 1800, dtype=np.int64)
POSITIONS = np.array([0, 5, 10, 15, 20], dtype=np.int64)
COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#343434']
STYLES = ['-', '--', '-.', ':', (0, (5, 1, 1, 1))]
MARKERS = ['o', 's', '^', 'D', 'v']
RUNS = {
    'nominal': ('run_n10240_startsafe', 10240, False,
                '79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b',
                '1608daaf85666c495d9d62eaf19d07ff385c45bf66c58c598773e3769318871f'),
    'coarse': ('run_n5120_startsafe', 5120, False,
               '1a4c436af2032829e20ad9ad976ff7eafadd70aff1747901844402ebfd5b4414',
               '56d260115f23fd8435fb5d7ff6426c6ab22501baa23d9e6f4032df903b4d756c'),
    'tight': ('run_n10240_tight_startsafe', 10240, True,
              '2b5fd0e7c819a97721d3063091a6f251d441af086dcf63d9bfa64f74fe20fadf',
              '0e324fa21adf3eae8a7ff214604b48c6c673ad2ba089892569b6e62a2674ed32'),
}
REPORTS = {
    'verification_implementation.json': '8365797324c7ceaadc7ca2cf27515d6ea14b325dba4f0a2ea2dd494b33b436f7',
    'verification_structure.json': 'ff82989f40157cebb12a03bdb18e02d8411ede05c1cadf4e7f84c44898ac5fd8',
}
BOUNDARY_SHA = 'f30996b8fc3a132164ae1a8b688f683bd15120fa38d54155221d8839085f178f'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def identity(path, root):
    path = Path(path).resolve()
    try:
        name = path.relative_to(root).as_posix()
    except ValueError:
        name = str(path)
    return {'path': name, 'sha256': digest(path), 'size': path.stat().st_size}


def require(ok, message):
    if not bool(ok):
        raise ValueError(message)


def check(report, name, ok, **details):
    record = {'name': name, 'passed': bool(ok), **details}
    report['checks'].append(record)
    require(ok, name)


def frozen(path, root, state):
    record = state['artifacts'].get(path.relative_to(root).as_posix(), {})
    require(record.get('identity_class') == 'frozen' and record.get('status') == 'validated'
            and record.get('sha256') == digest(path), 'Frozen validated identity required: ' + str(path))


def rounded(value):
    return format(Decimal.from_float(float(value)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), '.4f')


def read_table_snapshot(brief):
    text = brief.read_text(encoding='utf-8-sig')
    lines = text.splitlines()
    heads = [i for i, line in enumerate(lines) if line.strip().startswith('| 时间/h | r=0 cm |')]
    require(len(heads) == 2, 'Exactly the two official 6-by-5 summary tables are required')
    result = {}
    for field, start in zip(FIELDS, heads):
        header = [v.strip() for v in lines[start].strip().strip('|').split('|')]
        require(header == ['时间/h', 'r=0 cm', 'r=0.5 cm', 'r=1.0 cm', 'r=1.5 cm', 'r=2.0 cm'], 'Summary radius columns changed')
        rows = []
        for line in lines[start + 2:start + 8]:
            columns = [v.strip() for v in line.strip().strip('|').split('|')]
            require(len(columns) == 6, 'Summary table must have one time and five values per row')
            require(all(re.fullmatch(r'-?\d+\.\d{4}', v) for v in columns[1:]), 'Summary cells must display four decimals')
            rows.append(columns)
        require([float(row[0]) for row in rows] == (TIMES / 3600).tolist(), 'Summary time rows changed')
        result[field] = [row[1:] for row in rows]
    return result


def load_sources(root, report):
    state = read_json(root / '.modeling/state.json')
    output = root / 'output/Q2'
    reports = {}
    report['sources'] = {'runs': {}, 'prior_reports': [], 'generator': identity(__file__, root)}
    report['checked_state_revision'] = state['revision']
    for name, expected in REPORTS.items():
        path = output / name
        require(digest(path) == expected, 'Prior report identity changed: ' + name)
        frozen(path, root, state)
        data = read_json(path)
        require(data.get('question') == 'Q2' and data.get('mode') == 'full_process', 'Wrong prior report question or mode')
        require(data.get('passed') is True and data.get('checks') and all(c.get('passed') is True for c in data['checks']), 'Prior report is not passing')
        reports[name] = data
        report['sources']['prior_reports'].append({**identity(path, root), 'passed_check_count': len(data['checks']), 'axes': data['axes'], 'reuse': 'Identity and existing checks only; no prior verifier execution'})
    implementation = reports['verification_implementation.json']
    require(set(implementation.get('axes', [])) == {'E1', 'E2'}, 'Wrong implementation report axes')
    run_identities = implementation['details']['run_identities']
    runs = {}
    for role, (stem, grid, tight, expected, expected_meta) in RUNS.items():
        path, metadata_path = output / (stem + '.npz'), output / (stem + '.json')
        require(digest(path) == expected and digest(metadata_path) == expected_meta, 'Accepted run identity changed: ' + role)
        meta = read_json(metadata_path)
        require(meta.get('success') is True and meta.get('result_sha256') == expected, 'Unsuccessful/unbound result: ' + role)
        require(meta.get('grid_n') == grid and meta.get('tight') is tight, 'Grid/tolerance role mismatch: ' + role)
        require(any(i.get('result_sha256') == expected and i.get('metadata_sha256') == expected_meta for i in run_identities), 'Run pair is absent from the frozen passing report: ' + role)
        if role == 'nominal':
            frozen(path, root, state)
        entry = {'npz': identity(path, root), 'metadata': identity(metadata_path, root), 'grid_n': grid,
                 'binding': 'individually frozen validated NPZ and frozen report binding' if role == 'nominal' else 'exact NPZ/metadata pair bound by frozen passing implementation report; not claimed individually registered'}
        report['sources']['runs'][role] = entry
        with np.load(path, allow_pickle=False) as archive:
            seconds, radius = archive['time_s'], archive['radius_m']
            require(seconds.ndim == 1 and len(seconds) > END and np.array_equal(seconds[:END + 1], np.arange(END + 1)), 'Missing integer-second prefix: ' + role)
            require(radius.shape == (21,) and np.max(np.abs(radius - np.arange(21) / 1000)) <= 1e-15, 'Wrong prescribed radii: ' + role)
            fields = {}
            for key in FIELDS:
                values = archive[key]
                require(values.dtype == np.dtype('float64') and values.shape == (len(seconds), 21), 'Wrong source field shape/dtype: ' + role + key)
                prefix = values[:END + 1].copy()
                require(np.isfinite(prefix).all(), 'Nonfinite prefix: ' + role + key)
                require(np.max(np.abs(prefix[0] - (28. if key == 'temperature_C' else 2.55))) <= 1e-13, 'Wrong initial field: ' + role + key)
                fields[key] = prefix
                del values
            runs[role] = {'meta': meta, 'radius_m': radius.copy(), 'time_s': seconds[:END + 1].copy(), **fields}
            if role == 'nominal':
                index = meta['snapshot_roles']['summary_10800s']
                require(archive['snapshot_time_s'][index] == END, 'Wrong 3h snapshot role')
                mesh_radius = archive['mesh_radius_m']
                require(mesh_radius.shape == (grid + 1,) and np.max(np.abs(mesh_radius - np.linspace(0, .02, grid + 1))) < 1e-15, 'Wrong full mesh radius')
                faces = np.r_[0., (mesh_radius[1:] + mesh_radius[:-1]) / 2, .02]
                weights = np.diff(faces ** 2) / .02 ** 2
                report['at_3h_full_mesh'] = {}
                for field, snapshot_key in zip(FIELDS, ('temperature_snapshots', 'moisture_snapshots')):
                    snapshot = archive[snapshot_key][index]
                    require(snapshot.shape == (grid + 1,) and np.isfinite(snapshot).all(), 'Wrong full 3h snapshot')
                    require(np.max(np.abs(snapshot[::grid // 20] - fields[field][END])) <= 1e-12, '3h output does not match full snapshot')
                    report['at_3h_full_mesh'][field] = {'center': float(snapshot[0]), 'surface': float(snapshot[-1]), 'minimum': float(snapshot.min()), 'maximum': float(snapshot.max()), 'radius_at_minimum_m': float(mesh_radius[snapshot.argmin()]), 'radius_at_maximum_m': float(mesh_radius[snapshot.argmax()]), 'area_weighted_mean': float(weights @ snapshot), 'node_count': grid + 1, 'units': UNITS[field]}
    nominal, coarse, tight = [runs[role]['meta'] for role in ('nominal', 'coarse', 'tight')]
    for key in ('spec_sha256', 'boundary_sha256', 'solver_sha256', 'raw_environment_sha256'):
        check(report, 'same_model_source_' + key, nominal[key] == coarse[key] == tight[key], sha256=nominal[key])
    for key in ('rtol', 'atol_temperature', 'atol_moisture', 'max_step_observed_s', 'explicit_initial_step_s'):
        check(report, 'space_same_settings_' + key, nominal[key] == coarse[key])
    for key in ('rtol', 'atol_temperature', 'atol_moisture'):
        check(report, 'time_tenfold_tighter_' + key, abs(tight[key] / nominal[key] - .1) <= 1e-14, nominal=nominal[key], tight=tight[key])
    check(report, 'time_half_maximum_observed_step', tight['max_step_observed_s'] == nominal['max_step_observed_s'] / 2)
    boundary_path = root / 'output/ENV/q2_boundary.json'
    require(digest(boundary_path) == BOUNDARY_SHA and nominal['boundary_sha256'] == BOUNDARY_SHA, 'Boundary identity changed')
    boundary = read_json(boundary_path)
    bt = np.asarray(boundary['time_s'])
    require(np.array_equal(bt[:181], np.arange(181) * 60), 'Boundary must include all 181 nodes through 3h')
    report['sources']['boundary'] = identity(boundary_path, root)
    return runs, boundary


def compare(report, a, b, label, limit):
    require(np.array_equal(a['time_s'], b['time_s']) and np.array_equal(a['radius_m'], b['radius_m']), 'Comparisons must share identical times and radii')
    result = {}
    for field in FIELDS:
        differences = np.abs(a[field] - b[field])
        index = np.unravel_index(int(differences.argmax()), differences.shape)
        value = float(differences[index])
        result[field] = {'max_abs': value, 'limit': limit, 'units': UNITS[field], 'passed': value <= limit,
                         'at_time_s': int(a['time_s'][index[0]]), 'at_radius_m': float(a['radius_m'][index[1]]),
                         'samples_compared': int(differences.size), 'shape': list(differences.shape)}
        check(report, label + '_' + field, value <= limit, **{k: v for k, v in result[field].items() if k != 'passed'})
    return result


def summary_audit(root, brief, nominal, report):
    snapshot = read_table_snapshot(brief)
    summary_path = root / 'output/Q2/summary_values.json'
    old = read_json(summary_path)
    require(old['sources']['result']['sha256'] == RUNS['nominal'][3], 'Existing summary binds a different result')
    report['sources']['prior_summary'] = identity(summary_path, root)
    report['sources']['brief_table_snapshot'] = identity(brief, root)
    report['tables'] = {}
    cells = []
    for table_number, field in zip((3, 4), FIELDS):
        raw = nominal[field][np.ix_(TIMES, POSITIONS)]
        expected = [[rounded(v) for v in row] for row in raw]
        prior = old['tables'][field]
        require(prior['time_s'] == TIMES.tolist() and prior['radius_m'] == nominal['radius_m'][POSITIONS].tolist(), 'Existing summary axes changed')
        check(report, 'prior_summary_raw_values_' + field, np.array_equal(np.asarray(prior['values']), raw), values_checked=30)
        check(report, 'prior_summary_4dp_' + field, prior['display_4dp'] == expected, values_checked=30)
        for i, t in enumerate(TIMES):
            for j, position in enumerate(POSITIONS):
                cells.append({'table': table_number, 'time_s': int(t), 'radius_cm': float(nominal['radius_m'][position] * 100),
                              'source_float64': float(raw[i, j]), 'expected_4dp': expected[i][j], 'manuscript_4dp': snapshot[field][i][j],
                              'passed': snapshot[field][i][j] == expected[i][j]})
        report['tables'][field] = {'time_s': TIMES.tolist(), 'radius_cm': (nominal['radius_m'][POSITIONS] * 100).tolist(), 'values': raw.tolist(), 'display_4dp': expected, 'units': UNITS[field]}
    check(report, 'manuscript_tables_3_and_4_all_60_values', len(cells) == 60 and all(c['passed'] for c in cells), values_checked=len(cells))
    report['summary_audit'] = {'values_checked': 60, 'cells': cells, 'table_content_sha256': hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest(), 'rounding': 'Decimal.from_float(binary64).quantize(0.0001, ROUND_HALF_UP)', 'scope': 'The supplied brief snapshot tables only; prose/placeholder edits after this run have a different whole-document identity'}


def choose_font(font_path, labels):
    from matplotlib import font_manager, ft2font
    folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    candidates = [font_path] if font_path else [folder / 'msyh.ttc', folder / 'simhei.ttf', folder / 'simsun.ttc']
    required = {ord(c) for text in labels for c in text if '\u4e00' <= c <= '\u9fff'}
    for p in candidates:
        if p.is_file() and required.issubset(ft2font.FT2Font(str(p)).get_charmap()):
            font_manager.fontManager.addfont(str(p))
            return p, font_manager.FontProperties(fname=str(p)).get_name()
    raise ValueError('No Chinese font covers every planned label')


def draw(nominal, boundary, destination, font_path):
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'cumcm-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    labels = ['时间', '温度', '含水率', '干基', '前', '环境温度', '距中心']
    font_path, font_name = choose_font(font_path, labels)
    plt.rcParams.update({'font.family': font_name, 'font.size': 9.5, 'axes.unicode_minus': False,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#273546', 'text.color': '#273546',
                         'xtick.color': '#526174', 'ytick.color': '#526174',
                         'path.simplify': False, 'agg.path.chunksize': 20000})
    fig = plt.figure(figsize=(7.5, 3.7))
    grid = fig.add_gridspec(1, 2, left=.112, right=.975, top=.875, bottom=.285, wspace=.37)
    a, b = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
    hours = nominal['time_s'] / 3600
    handles = []
    for index, color, style, marker in zip(POSITIONS, COLORS, STYLES, MARKERS):
        common = dict(color=color, linestyle=style, linewidth=1.35, marker=marker,
                      markersize=3.1, markerfacecolor='white', markeredgewidth=.75)
        line, = a.plot(hours, nominal['temperature_C'][:, index], markevery=1800, **common)
        handles.append(line)
        b.plot(hours, nominal['moisture_kg_kg'][:, index], markevery=1800, **common)
    a.plot(np.asarray(boundary['time_s'][:181]) / 3600, boundary['temperature_C'][:181],
           color='#888888', linewidth=.95, linestyle=(0, (2, 2)), label='环境温度')
    a.legend(frameon=False, fontsize=8.2, loc='lower right')
    for axis, title in ((a, '(a) 前 3 h：温度'), (b, '(b) 前 3 h：含水率')):
        axis.set_title(title, loc='left', fontsize=10, pad=8)
        axis.set_xlabel('时间 / h')
        axis.grid(color='#dce2e9', linewidth=.55, alpha=.7)
        axis.set_axisbelow(True)
        axis.set_xlim(0, 3)
        axis.set_xticks([0, 1, 2, 3])
    a.set_ylabel('温度 $\\theta$ / °C')
    b.set_ylabel('含水率 $C$ / (kg/kg，干基)')
    fig.legend(handles, [f'r = {100 * nominal["radius_m"][i]:g} cm' for i in POSITIONS],
               title='距中心', ncol=5, frameon=False, fontsize=8.5, title_fontsize=8.5,
               loc='lower center', bbox_to_anchor=(.55, .018), handlelength=2.6,
               columnspacing=1.15, handletextpad=.45)
    fig.savefig(destination, dpi=240, facecolor='white')
    plt.close(fig)
    return {'family': font_name, 'file': str(font_path.resolve()), 'sha256': digest(font_path),
            'chinese_glyph_coverage': 'All planned Chinese labels present in font character map',
            'visual_glyph_check': 'pending actual PNG inspection'}, matplotlib.__version__


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--brief', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=Path('output/Q2'))
    parser.add_argument('--font', type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    args.brief = (root / args.brief).resolve()
    output = (root / args.output_dir).resolve()
    require(output == (root / 'output/Q2').resolve(), 'Only admitted Q2 outputs are supported')
    report_path, png, manifest_path = [output / p for p in ('submission_verification.json', 'field_evolution.png', 'figure_manifest.json')]
    require(not report_path.exists(), 'Do not overwrite an existing submission verification identity')
    started = time.monotonic()
    report = {'schema_version': '1.0', 'question': 'Q2', 'status': 'started', 'output_start_s': 1,
              'output_end_s': END, 'input_npz_sha256': RUNS['nominal'][3], 'created_at': datetime.now(timezone.utc).isoformat(),
              'checks': [], 'coverage': {'comparison_time_s': [0, END], 'integer_seconds': END + 1, 'radii': 21,
                                        'sample_pairs_per_field_per_comparison': (END + 1) * 21,
                                        'comparison_count': 2, 'field_count': 2, 'total_scalar_differences': (END + 1) * 21 * 4},
              'claim_boundary': 'Observed spatial/time refinement differences on the prescribed samples; not a rigorous continuous-solution error bound or per-cell correct-rounding guarantee. No model or original verifier is executed.'}
    try:
        runs, boundary = load_sources(root, report)
        report['spatial'] = compare(report, runs['coarse'], runs['nominal'], 'spatial', 2.5e-5)
        report['temporal'] = compare(report, runs['nominal'], runs['tight'], 'temporal', 5e-6)
        summary_audit(root, args.brief, runs['nominal'], report)
        with tempfile.TemporaryDirectory(prefix='cumcm-q2-submission-figure-') as tmp:
            temporary_png = Path(tmp) / 'field_evolution.png'
            font, version = draw(runs['nominal'], boundary, temporary_png, args.font)
            staged = output / '.field_evolution.png.staging'
            require(not staged.exists(), 'Preserve unexpected destination staging file')
            shutil.copyfile(temporary_png, staged)
            require(digest(staged) == digest(temporary_png), 'Figure placement checksum mismatch')
            os.replace(staged, png)
        manifest = {'schema_version': '1.0', 'question': 'Q2', 'visual_id': 'Q2_FIELD_EVOLUTION', 'data_driven_visual': True,
                    'output_end_s': END, 'input_npz_sha256': report['input_npz_sha256'], 'created_at': datetime.now(timezone.utc).isoformat(),
                    'purpose': 'Compare temperature and dry-basis moisture histories at five prescribed radii during the first three hours.',
                    'supported_claim': 'Temperature and moisture show different radial evolution over 0..10800 seconds.',
                    'source_identities': report['sources'], 'generator': identity(__file__, root), 'generation_argv': [sys.executable, *sys.argv],
                    'consumers': ['docs/Q2/solution_brief.md'], 'table_relation': 'Same unrounded nominal trajectory as the independently checked 6-by-5 tables.',
                    'panels': [{'id': 'a', 'interval_s': [0, END], 'field': FIELDS[0], 'columns': POSITIONS.tolist(), 'environment': '181 original nodes from 0..10800 s'},
                               {'id': 'b', 'interval_s': [0, END], 'field': FIELDS[1], 'columns': POSITIONS.tolist()}],
                    'transformations': ['seconds to hours; metres to centimetres in legend', 'all 10801 integer-second samples plotted at five radii; no smoothing or field rounding'],
                    'visual_encoding': {'radius_cm': (runs['nominal']['radius_m'][POSITIONS] * 100).tolist(), 'colors': COLORS,
                                        'line_styles': [str(s) for s in STYLES], 'markers': MARKERS,
                                        'radius_encoding': 'Same color, line style and marker identify each radius in both panels',
                                        'units': 'Temperature degC; moisture kg water/kg dry solid; time hours; radius cm'},
                    'font': font, 'matplotlib_version': version,
                    'target': {'width_mm': 190.5, 'height_mm': 93.98, 'dpi': 240, 'pixels': [1800, 888], 'smallest_font_pt': 8.2, 'minimum_main_linewidth_pt': 1.35},
                    'outputs': [identity(png, root)],
                    'caption_draft': '问题2前三小时的径向温湿响应。两面板分别显示距中心0、0.5、1、1.5、2 cm处的温度与干基含水率，灰色虚线为环境温度。所有药材曲线来自同一未舍入数值轨迹。',
                    'claim_boundary': ['First three hours only; five plotted radii, with 21 radii checked numerically.', 'Numerical consistency is separate from material-model validation.'],
                    'acceptance': {'numerical_sources': 'Source identities and scoped sample comparisons passed', 'independent_png_visual_review': 'pending',
                                   'grayscale_review': 'pending', 'final_manuscript_size_review': 'pending at actual placement', 'formal_visual_acceptance': 'not claimed'}}
        for group in report['sources']['runs'].values():
            for key in ('npz', 'metadata'):
                require(digest(root / group[key]['path']) == group[key]['sha256'], 'Run changed during review')
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        report['figure'] = {'png': identity(png, root), 'manifest': identity(manifest_path, root), 'visual_review': 'pending actual inspection'}
        report['status'] = 'pass'
    except Exception as exc:
        report['status'] = 'fail'
        report['exception'] = {'type': type(exc).__name__, 'message': str(exc)}
    report['elapsed_s'] = time.monotonic() - started
    output.mkdir(parents=True, exist_ok=True)
    with report_path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': report['status'], 'report': str(report_path), 'figure': str(png), 'elapsed_s': report['elapsed_s']}, ensure_ascii=False))
    if report['status'] != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
