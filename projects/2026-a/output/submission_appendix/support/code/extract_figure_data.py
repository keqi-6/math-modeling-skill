"""Extract only plotted arrays from existing saved results (no model execution).

Use explicit input filenames. This extractor does not require the original
workspace, diagnostics directory, source hashes, or any solver import.
Measured radius metadata already supplied with the appendix is retained.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import numpy as np

def extract(q1, q2, q4, output, q4_end=None, observations=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    inputs = {}
    for key, path in [('q1', q1), ('q2', q2), ('q4', q4)]:
        path = Path(path)
        inputs[key] = {'filename': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    def keep(name, **arrays):
        np.savez_compressed(output/name, **arrays)
    with np.load(q1, allow_pickle=False) as z:
        times = np.array([100, 600, 900, 1200, 1800])
        ids = np.array([np.flatnonzero(z['time_s']==t).item() for t in times])
        keep('q1_profiles.npz', time_s=times, radius_m=z['radius_m'],
             temperature_C=z['temperature_C'][ids], moisture_kg_kg=z['moisture_kg_kg'][ids])
    with np.load(q2, allow_pickle=False) as z:
        hits=np.flatnonzero(z['max_moisture_kg_kg']<.15)
        if not len(hits):
            raise ValueError('Q2/Q3结果中尚未达到全域阈值，不能绘制完整干燥图。')
        q3_end=int(z['time_s'][hits[0]])
        t = z['time_s']; ids = np.flatnonzero((t>=0)&(t<=10800))
        assert np.array_equal(t[ids], np.arange(10801))
        keep('q2_fields.npz', time_s=t[ids], radius_m=z['radius_m'],
             temperature_C=z['temperature_C'][ids], moisture_kg_kg=z['moisture_kg_kg'][ids])
    with np.load(q4, allow_pickle=False) as z:
        if q4_end is None:
            hits=np.flatnonzero(z['max_moisture_kg_kg']<.15)
            if not len(hits):
                raise ValueError('Q4结果中尚未达到全域阈值。')
            q4_end=int(z['time_s'][hits[0]])
        times = np.array([0, 21600, 64800, 129600, 172800, q4_end])
        ids = np.array([np.flatnonzero(z['snapshot_time_s']==t).item() for t in times])
        keep('q4_sections.npz', mesh_xi=z['mesh_xi'], snapshot_time_s=times,
             snapshot_radius_m=z['snapshot_radius_m'][ids], moisture_snapshots=z['moisture_snapshots'][ids])
    observations=Path(observations) if observations else Path(__file__).resolve().parents[1]/'figure_data/radius_observations.json'
    if observations.is_file():
        observed=json.loads(observations.read_text(encoding='utf-8'))
        (output/'radius_observations.json').write_text(json.dumps(observed,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('figure_restructured.py')),
                    '--source', str(Path(q2).resolve()), '--data-dir', str(output.resolve()),
                    '--extract-only'], check=True, timeout=120)
    files = {}
    for path in sorted(output.glob('*.npz')):
        with np.load(path, allow_pickle=False) as z:
            files[path.name] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                               'bytes': path.stat().st_size,
                               'arrays': {key: {'shape': list(z[key].shape), 'dtype': str(z[key].dtype)} for key in z.files}}
    manifest = {'inputs': inputs, 'files': files, 'q3_end_s': q3_end, 'q4_end_s': q4_end,
                'units': {'time_s': 's', 'radius_m': 'm', 'temperature_C': 'degC',
                          'moisture_kg_kg': 'kg/kg dry basis', 'mesh_xi': 'dimensionless'},
                'operation': 'Exact array selection; no rounding, fitting, filtering, or solver execution.',
                'q3_maximum': 'Saved maximum over all numerical nodes. Completion bands display the 21 prescribed radii.',
                'additional_data': 'restructured_figure_data.json contains exact diffusivity decomposition and integer-second radial threshold crossings.'}
    (output/'data_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('q1', 'q2', 'q4', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--q4-end', type=int, help='Override first saved all-node threshold time')
    p.add_argument('--observations', type=Path, help='Optional replacement measured-radius JSON')
    a = p.parse_args()
    extract(a.q1, a.q2, a.q4, a.output, a.q4_end, a.observations)

if __name__=='__main__':
    main()
