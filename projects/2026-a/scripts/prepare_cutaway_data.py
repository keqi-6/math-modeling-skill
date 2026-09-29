"""Prepare stored Q2 radial data for a middle-segment 3D illustration."""
from pathlib import Path
import hashlib
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'output/paper_figures/redesign_v3'
SRC = ROOT/'output/Q2/run_n10240_startsafe.npz'
EXPECTED = '79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b'


def main():
    digest = hashlib.sha256(SRC.read_bytes()).hexdigest()
    assert digest == EXPECTED, 'Reviewed Q2 source changed.'
    with np.load(SRC) as z:
        i = np.flatnonzero(z['snapshot_time_s'] == 1800).item()
        c = z['moisture_snapshots'][i]
        temp = z['temperature_snapshots'][i]
        xi = z['mesh_radius_m']/z['mesh_radius_m'][-1]
        assert np.max(np.diff(c)) < 1e-9
        assert np.min(np.diff(temp)) > -1e-9
        fields = {'xi':xi.tolist(),'C':c.tolist()}
        values = {'C_center':float(c[0]),'C_surface':float(c[-1]),
                  'theta_center':float(temp[0]),'theta_surface':float(temp[-1])}
    env = json.loads((ROOT/'output/ENV/q2_boundary.json').read_text(encoding='utf-8'))
    j = env['time_s'].index(1800)
    values.update(T_inf=env['temperature_C'][j],C_eq=env['air_moisture_kg_kg'][j])
    assert values['T_inf'] > values['theta_surface'] and values['C_surface'] > values['C_eq']
    data = {'source_path':SRC.relative_to(ROOT).as_posix(),'source_sha256':digest,
            'time_s':1800,'radius_m':.02,'fields':fields,'values':values,
            'colors':['#eaf3f7','#d6eff5','#99d3e1','#469dbf','#155c88'],
            'color_positions':[0,.25,.5,.75,1],'C_range':[0,2.55],
            'geometry':'A short middle segment with a 90-degree sector removed for viewing; cylinder height is illustrative. No axial solution or time evolution of length is implied.',
            'encoding':'Only the exposed cross-sections encode C. Neutral outer wall identifies material. Arrows indicate exchange direction, not magnitude.'}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'cutaway_data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('Prepared full 10241-node Q2 field; no solver executed.')


if __name__ == '__main__':
    main()
