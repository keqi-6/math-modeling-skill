"""Q4 moving-domain moisture histories and physical radial profiles.

Consumer of the actual verified main result and current workbook data audit.
No solver, verifier, spreadsheet authoring, or project-state mutation.
Use the project venv (matplotlib), through the authorized 3540-second wrapper.
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

FIXED_POSITIONS = [0, 5, 10, 15]
COLORS = ['#0072B2', '#D55E00', '#009E73', '#CC79A7', '#343434']
STYLES = ['-', '--', '-.', ':', (0, (5, 1, 1, 1))]
MARKERS = ['o', 's', '^', 'D', 'v']


def require(ok, message):
    if not bool(ok):
        raise ValueError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def identify(path, root):
    path = Path(path).resolve()
    try:
        name = path.relative_to(root).as_posix()
    except ValueError:
        name = str(path)
    return {'path': name, 'sha256': digest(path), 'size': path.stat().st_size}


def registered_binding(path, root, state, *, require_frozen=False, check_registered=False):
    path = path.resolve()
    name = path.relative_to(root).as_posix()
    record = state['artifacts'].get(name)
    actual = identify(path, root)
    if require_frozen:
        require(record is not None and record.get('identity_class') == 'frozen'
                and record.get('status') == 'validated' and record.get('sha256') == actual['sha256'],
                'Frozen validated model/shared input required: ' + name)
    if record is not None and (check_registered or record.get('identity_class') == 'frozen'):
        require(record.get('sha256') == actual['sha256'], 'Already registered input identity changed: ' + name)
    return actual


def choose_font(explicit, labels):
    from matplotlib import font_manager, ft2font
    folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    candidates = [explicit] if explicit else [folder / 'msyh.ttc', folder / 'simhei.ttf', folder / 'simsun.ttc']
    required = {ord(c) for label in labels for c in label if '\u4e00' <= c <= '\u9fff'}
    for candidate in candidates:
        if candidate.is_file() and required.issubset(ft2font.FT2Font(str(candidate)).get_charmap()):
            font_manager.fontManager.addfont(str(candidate))
            return candidate, font_manager.FontProperties(fname=str(candidate)).get_name()
    raise ValueError('A font covering every Chinese plot label is required')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--input', type=Path, required=True, help='Actual verified Q4 main NPZ; original path retained')
    parser.add_argument('--metadata', type=Path, required=True, help='Matching original main-run metadata JSON')
    parser.add_argument('--output-dir', type=Path, default=Path('output/Q4'))
    parser.add_argument('--font', type=Path)
    args = parser.parse_args()
    root = args.project_root.resolve()
    output = (root / args.output_dir).resolve()
    require(output == (root / 'output/Q4').resolve(), 'Only the admitted Q4 output directory is supported')
    png, manifest_path = output / 'field_evolution.png', output / 'figure_manifest.json'
    require(not png.exists() and not manifest_path.exists(), 'Preserve existing figure identities')
    result, metadata_path = (root / args.input).resolve(), (root / args.metadata).resolve()
    result.relative_to(output)
    require(result.suffix == '.npz' and metadata_path == result.with_suffix('.json'), 'Use the actual NPZ and its matching metadata')
    specification, geometry, boundary = root / 'planning/Q4/model_spec.md', root / 'output/GEOMETRY/q4_radius.json', root / 'output/ENV/q2_boundary.json'
    summary_path, audit_path, workbook_path = output / 'summary_values.json', output / 'workbook_audit.json', output / 'result4.xlsx'
    state = read_json(root / '.modeling/state.json')
    source_ids = {}
    for role, p in [('specification', specification), ('geometry', geometry), ('boundary', boundary)]:
        source_ids[role] = registered_binding(p, root, state, require_frozen=True)
    for role, p in [('result', result), ('metadata', metadata_path)]:
        source_ids[role] = registered_binding(p, root, state, check_registered=True)
    meta, summary, audit = read_json(metadata_path), read_json(summary_path), read_json(audit_path)
    sha = source_ids['result']['sha256']
    require(meta['question'] == 'Q4' and meta['success'] is True and meta['drying_complete'] is True
            and meta['comparison_complete'] is True and meta['case_role'] == 'main', 'An actual complete main result is required')
    require(meta['properties'] == 'appendix4' and meta['scenario'] == 'mean_tail' and meta['radius']['method'] == 'linear', 'Official Q4 scenario changed')
    require(type(meta['grid_n']) is int and meta['grid_n'] >= 20 and meta['grid_n'] % 20 == 0
            and meta['tight'] is False and meta['method'] == 'material_coordinate_nodal_finite_volume_segmented_BDF',
            'Official ordinary main grid/tight/method contract mismatch')
    require(meta['result_sha256'] == sha and meta['spec_sha256'] == source_ids['specification']['sha256']
            and meta['radius_json_sha256'] == source_ids['geometry']['sha256']
            and meta['boundary_sha256'] == source_ids['boundary']['sha256'], 'Current result provenance mismatch')
    require(audit.get('data_status') == 'pass' and audit.get('status') != 'fail'
            and audit['independent_verification']['status'] == 'pass'
            and audit['input_npz_sha256'] == sha and audit['metadata_sha256'] == source_ids['metadata']['sha256']
            and audit['specification']['sha256'] == source_ids['specification']['sha256'], 'Current workbook data audit is not passing for this exact run')
    require(summary['input_npz_sha256'] == sha and summary['metadata_sha256'] == source_ids['metadata']['sha256']
            and summary['specification']['sha256'] == source_ids['specification']['sha256'], 'Current summary source mismatch')
    require(digest(summary_path) == audit['independent_verification']['summary_sha256']
            and digest(workbook_path) == audit['independent_verification']['xlsx_sha256'], 'Summary or workbook changed after the full audit')
    # A report can contain coarse, main and sensitivity sources. Presence among
    # those identities is insufficient: consume the report's selected_main.
    comparison_axes, comparison_checks = set(), set()
    for i, recorded in enumerate(audit['prior_verification']):
        evidence_path = Path(recorded['path']).resolve()
        evidence_path.relative_to(root)
        require(digest(evidence_path) == recorded['sha256'], 'Recorded verification report changed')
        evidence = read_json(evidence_path)
        require(evidence['passed'] is True and evidence['checks']
                and all(c['passed'] is True for c in evidence['checks']), 'Actual comparison evidence is not passing')
        source_ids['verification_' + str(i + 1)] = identify(evidence_path, root)
        if evidence['mode'] != 'compare':
            continue
        selected = evidence['details']['selected_main']
        require(Path(selected['result']).resolve() == result and selected['result_sha256'] == sha
                and Path(selected['metadata']).resolve() == metadata_path
                and selected['metadata_sha256'] == source_ids['metadata']['sha256'],
                'The plotted result must be the selected main, not another input of the passing report')
        require(selected['grid_n'] == meta['grid_n'] and selected['tight'] is False
                and selected['method'] == meta['method'] and selected['scenario'] == meta['scenario']
                and selected['properties'] == meta['properties'] and selected['radius_method'] == meta['radius']['method'],
                'Selected-main numerical/scenario identity mismatch')
        require(recorded['selected_main'] == selected, 'Workbook audit selected-main binding differs from the actual report')
        comparison_axes.update(evidence['axes'])
        comparison_checks.update(c['id'] for c in evidence['checks'])
    require({'E2', 'E3'} <= comparison_axes and {
        'selected_spatial_temperature', 'selected_spatial_moisture', 'selected_spatial_crossing',
        'independent_time_temperature', 'independent_time_moisture', 'independent_time_crossing',
        'both_prespecified_input_sensitivities_present'} <= comparison_checks,
        'Actual selected-main space/time/structure and sensitivity comparisons are required')
    end = meta['n_end']
    require(type(end) is int and end > 0 and summary['n_end_s'] == end and meta['threshold_kg_kg'] == .15, 'Actual endpoint/threshold semantics missing')
    endpoint = audit['independent_verification']['strict_endpoint']
    require(endpoint['before_n_end']['time_s'] == end - 1 and endpoint['before_n_end']['maximum_kg_kg'] >= .15
            and endpoint['n_end']['time_s'] == end and endpoint['n_end']['maximum_kg_kg'] < .15,
            'Independent adjacent-second endpoint evidence missing')
    table_times = sorted(set(range(21600, end + 1, 21600)) | {end})
    require(summary['table6']['time_s'] == table_times, 'Actual Table6 axis changed')
    # Choose actual stored Table6 times, never synthetic/interpolated figure times.
    selected_indices = list(range(len(table_times))) if len(table_times) <= 5 else np.linspace(0, len(table_times) - 1, 5, dtype=int).tolist()
    selected_times = [table_times[i] for i in selected_indices]
    require(len(set(selected_times)) == len(selected_times) and selected_times[-1] == end, 'Profile selection must retain the unique endpoint')
    profiles = []
    with np.load(result, allow_pickle=False) as archive:
        all_seconds = archive['time_s']
        select = (all_seconds >= 0) & (all_seconds <= end)
        seconds = all_seconds[select].copy()
        radius = archive['radius_m'].copy()
        moisture = archive['moisture_kg_kg'][select].copy()
        inside = archive['inside_mask'][select].copy()
        surface_c = archive['surface_moisture_kg_kg'][select].copy()
        surface_r = archive['surface_radius_m'][select].copy()
        xi = archive['mesh_xi'].copy()
        snapshot_t, snapshot_r, snapshot_c = archive['snapshot_time_s'], archive['snapshot_radius_m'], archive['moisture_snapshots']
        require(np.array_equal(seconds, np.array(sorted(set(range(0, end + 1, 60)) | {end}), dtype=np.int64)), 'Complete minute/endpoint plotting axis')
        require(radius.shape == (21,) and np.allclose(radius, np.arange(21) * .001, rtol=0, atol=1e-15), 'Fixed radius axis changed')
        require(moisture.shape == inside.shape == (len(seconds), 21) and inside.dtype == np.dtype('bool'), 'Field/mask shape mismatch')
        require(np.isfinite(moisture[inside]).all() and np.isnan(moisture[~inside]).all(), 'Domain mask must match finite/NaN data exactly')
        require(surface_c.shape == surface_r.shape == seconds.shape and np.isfinite(surface_c).all() and np.isfinite(surface_r).all(), 'Actual surface data missing')
        expected_mask = radius[None, :] <= surface_r[:, None] + 16 * np.finfo(float).eps * np.maximum(.02, surface_r[:, None])
        require(np.array_equal(inside, expected_mask), 'Current physical-domain classification mismatch')
        require(not np.any(inside[seconds > 0, 20]), 'The proposed omission of a 2 cm history requires that every positive-time sample is outside')
        require(xi.shape == (meta['grid_n'] + 1,) and np.allclose(xi, np.linspace(0, 1, len(xi)), rtol=0, atol=1e-15), 'Actual material mesh axis changed')
        for instant in selected_times:
            role = 'n_end' if instant == end else 'summary_' + str(instant) + 's'
            index = meta['snapshot_roles'][role]
            values, rad = snapshot_c[index].copy(), float(snapshot_r[index])
            require(snapshot_t[index] == instant and values.shape == xi.shape and np.isfinite(values).all() and rad > 0, 'Exact full-node profile missing')
            sample_index = int(np.searchsorted(seconds, instant))
            require(seconds[sample_index] == instant and abs(rad - surface_r[sample_index]) <= 2e-17
                    and abs(values[-1] - surface_c[sample_index]) <= 2e-13, 'Profile surface differs from the actual time-series surface')
            profiles.append({'time_s': instant, 'snapshot_role': role, 'snapshot_index': index,
                             'radius_m': rad, 'physical_r_m': rad * xi, 'moisture': values})
    for role, p in [('summary', summary_path), ('workbook_audit', audit_path), ('workbook', workbook_path), ('generator', Path(__file__))]:
        source_ids[role] = identify(p, root)

    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'cumcm-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator
    labels = ['固定位置及表面的含水率', '真实半径下的径向剖面', '时间', '距中心', '含水率', '干基',
              '位置', '实际药材表面', '阈值', '结束', '端点标记为表面']
    font_path, font_name = choose_font(args.font, labels)
    plt.rcParams.update({'font.family': font_name, 'font.size': 9.5, 'axes.unicode_minus': False,
                         'axes.spines.top': False, 'axes.spines.right': False,
                         'axes.labelcolor': '#273546', 'text.color': '#273546',
                         'xtick.color': '#526174', 'ytick.color': '#526174',
                         'path.simplify': False, 'agg.path.chunksize': 20000})
    fig = plt.figure(figsize=(7.5, 4.5))
    grid = fig.add_gridspec(1, 2, left=.11, right=.975, top=.9, bottom=.34, wspace=.43)
    a, b = fig.add_subplot(grid[0, 0]), fig.add_subplot(grid[0, 1])
    hours = seconds / 3600
    history_records = []
    for j, position in enumerate(FIXED_POSITIONS):
        mask = inside[:, position]
        valid_indices = np.flatnonzero(mask)
        require(valid_indices.size > 0, 'Each requested fixed radius must have at least its valid initial sample')
        values = np.where(mask, moisture[:, position], np.nan)
        marks = np.flatnonzero(mask & (seconds % 21600 == 0)).tolist()
        marks = sorted(set(marks + [int(valid_indices[-1])]))
        a.plot(hours, values, color=COLORS[j], linestyle=STYLES[j], linewidth=1.35,
               marker=MARKERS[j], markevery=marks, markersize=3.2, markerfacecolor='white', markeredgewidth=.75,
               label=f'r = {100 * radius[position]:g} cm')
        outside_indices = np.flatnonzero(~mask)
        history_records.append({'column_index': position, 'radius_m': float(radius[position]), 'inside_samples_drawn': int(mask.sum()),
                                'outside_samples_masked': int((~mask).sum()), 'first_valid_time_s': int(seconds[valid_indices[0]]),
                                'last_valid_sample_time_s': int(seconds[valid_indices[-1]]),
                                'first_outside_sample_time_s': int(seconds[outside_indices[0]]) if outside_indices.size else None,
                                'marker_sample_indices': marks})
    surface_marks = sorted(set(np.flatnonzero(seconds % 21600 == 0).tolist() + [len(seconds) - 1]))
    a.plot(hours, surface_c, color=COLORS[4], linestyle=STYLES[4], linewidth=1.85, marker=MARKERS[4],
           markevery=surface_marks, markersize=3.6, markerfacecolor='white', markeredgewidth=.9, label='实际药材表面')
    a.axhline(.15, color='#777777', linewidth=.9, linestyle=(0, (2, 3)), label='阈值 0.15')
    y_max = max(float(np.nanmax(moisture)), float(surface_c.max())) * 1.04
    a.set(xlim=(0, end / 3600 * 1.02), ylim=(0, y_max), xlabel='时间 / h', ylabel='含水率 $C$ / (kg/kg，干基)')
    a.xaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))
    a.set_title('(a) 固定位置及表面的含水率', loc='left', fontsize=9.4, pad=8)
    a.legend(title='位置', loc='upper center', bbox_to_anchor=(.5, -.23), ncol=2, frameon=False,
             fontsize=8.1, title_fontsize=8.3, handlelength=2.6, columnspacing=1, handletextpad=.45)

    for j, profile in enumerate(profiles):
        instant = profile['time_s']
        label = f'{instant / 3600:.4f} h（结束）' if instant == end else f'{instant / 3600:g} h'
        b.plot(profile['physical_r_m'] * 100, profile['moisture'], color=COLORS[j], linestyle=STYLES[j], linewidth=1.35,
               marker=MARKERS[j], markevery=[len(xi) - 1], markersize=4.1,
               markerfacecolor='white', markeredgewidth=.9, label=label)
    b.axhline(.15, color='#777777', linewidth=.9, linestyle=(0, (2, 3)))
    b.set(xlim=(0, max(p['radius_m'] for p in profiles) * 100 * 1.055), ylim=(0, y_max),
          xlabel='距中心 $r$ / cm', ylabel='含水率 $C$ / (kg/kg，干基)')
    b.xaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))
    b.set_title('(b) 真实半径下的径向剖面', loc='left', fontsize=9.4, pad=8)
    b.legend(title='时间（端点标记为表面）', loc='upper center', bbox_to_anchor=(.5, -.23), ncol=2, frameon=False,
             fontsize=8.1, title_fontsize=8.3, handlelength=2.6, columnspacing=1, handletextpad=.45)
    for axis in [a, b]:
        axis.grid(color='#dce2e9', linewidth=.55, alpha=.7)
        axis.set_axisbelow(True)
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(png, dpi=240, facecolor='white')
    plt.close(fig)
    for identity in source_ids.values():
        p = Path(identity['path'])
        p = p if p.is_absolute() else root / p
        require(digest(p) == identity['sha256'], 'Bound plotting input changed: ' + str(p))
    manifest = {
        'schema_version': '1.0', 'question': 'Q4', 'visual_id': 'Q4_MOVING_DOMAIN_MOISTURE',
        'created_at': datetime.now(timezone.utc).isoformat(), 'data_driven_visual': True,
        'purpose': 'Show fixed-location moisture histories only while those locations remain inside the material, alongside profiles on the actual shrinking physical radius.',
        'supported_claim': 'The recorded geometric domain shrinks; fixed locations cease to represent material after they leave it, whereas the actual surface is tracked continuously.',
        'source_identities': source_ids, 'generation_argv': [sys.executable, *sys.argv],
        'consumers': ['docs/Q4/solution_brief.md:7'],
        'terminal_time_s': end, 'grid_intervals': meta['grid_n'],
        'panels': [
            {'id': 'a', 'interval_s': [0, end], 'field': 'moisture_kg_kg', 'stored_times': len(seconds), 'fixed_locations': history_records,
             'moving_surface': {'field': 'surface_moisture_kg_kg', 'radius_field': 'surface_radius_m', 'samples_drawn': len(seconds), 'marker_sample_indices': surface_marks},
             'omitted_2cm': 'Every positive-time sample at 2 cm was independently checked outside; no empty or fabricated curve is drawn.'},
            {'id': 'b', 'field': 'moisture_snapshots', 'coordinate': 'actual r(t)=snapshot_radius_m*mesh_xi, converted m to cm once',
             'available_table6_time_s': table_times, 'selected_table6_row_indices': selected_indices, 'selected_time_s': selected_times,
             'selection_rule': 'All Table6 times if at most five; otherwise five evenly spaced integer row indices including the first and actual endpoint. Table6 itself remains complete.',
             'profiles': [{'time_s': p['time_s'], 'snapshot_role': p['snapshot_role'], 'snapshot_index': p['snapshot_index'],
                           'surface_radius_m': p['radius_m'], 'material_nodes_drawn': len(xi)} for p in profiles]}],
        'transformations': ['Seconds converted to hours for histories; every stored minute and actual endpoint retained.',
                            'Outside fixed-location values are masked NaNs, so no segment is connected through material-free positions.',
                            'Full material-node profiles use their current physical radius; only the moving-surface endpoint receives a marker.',
                            'No smoothing, result alteration, fabricated data or new model computation.'],
        'visual_encoding': {'base_colors': COLORS, 'line_styles': [str(v) for v in STYLES], 'markers': MARKERS,
                            'panel_a': 'Existing Q2/Q3 fixed-radius color/style pairs for 0,.5,1,1.5 cm; separate thicker dark dash pattern and open triangle for actual surface.',
                            'panel_b': 'Color and line style identify selected actual times; each end marker denotes that time-dependent surface. This local time encoding is stated in its separate legend.',
                            'threshold': 'Neutral grey dashed line at C=.15 on both panels'},
        'font': {'family': font_name, 'file': str(font_path.resolve()), 'sha256': digest(font_path), 'glyph_coverage': 'All planned Chinese labels checked'},
        'matplotlib_version': matplotlib.__version__,
        'target': {'width_mm': 190.5, 'height_mm': 114.3, 'dpi': 240, 'pixels': [1800, 1080], 'smallest_font_pt': 8.1, 'minimum_data_linewidth_pt': 1.35},
        'outputs': [identify(png, root)],
        'caption_draft': '问题4主情景的干基含水率演化。左图给出四个固定物理位置仍在药材内部时的轨迹，并以独立线型跟踪实际药材表面；固定位置越出当前药材范围后曲线停止。右图选取表6中的实际时刻，在当前真实半径上绘制完整节点剖面，曲线末端标记对应当时的表面。灰线为0.15阈值；表6保留所有规定时刻。',
        'claim_boundary': ['The figure describes the accepted Appendix4 moving-domain run; a difference from Q3 alone does not isolate shrinkage because properties also change.',
                           'Line endings show the last valid stored sample, not an independently estimated continuous exit time.',
                           'Only the actual plotted time range and source results are represented; no uncomputed Q4 endpoint is assumed.'],
        'acceptance': {'numerical_source_binding': 'Exact current main-run, summary and passing workbook data audit identities checked; model/spec and shared inputs remain frozen prerequisites.',
                       'phase_boundary': 'New numerical results and consumer products need not be frozen before the same S5 batch is completed; existing registered NPZ/meta identities must match.',
                       'independent_png_visual_review': 'pending', 'grayscale_review': 'pending', 'final_manuscript_size_review': 'pending', 'formal_visual_acceptance': 'not claimed'}}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'figure': str(png), 'manifest': str(manifest_path), 'visual_review': 'pending actual inspection'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
