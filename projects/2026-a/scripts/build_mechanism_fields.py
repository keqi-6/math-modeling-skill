"""Build the two quantitative cut-face color layers; no solver is invoked."""
from pathlib import Path
import hashlib
import json
import numpy as np
import matplotlib as mpl

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/paper_figures/mechanism_candidate_v2'
SRC = ROOT / 'output/Q2/run_n10240_startsafe.npz'
EXPECTED = '79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b'


def main():
    digest = hashlib.sha256(SRC.read_bytes()).hexdigest()
    if digest != EXPECTED:
        raise ValueError('Q2 source identity differs from the reviewed run.')
    OUT.mkdir(parents=True, exist_ok=True)
    tex = ['% Generated from the unrounded Q2 full-mesh snapshot at 1800 s.']
    evidence = []
    with np.load(SRC) as z:
        snap = np.flatnonzero(z['snapshot_time_s'] == 1800).item()
        mesh = z['mesh_radius_m']
        for name, field, cmap_name, lo, hi, unit in [
            ('Heat', 'temperature_snapshots', 'YlOrRd', 32., 36., 'degC'),
            ('Moisture', 'moisture_snapshots', 'Blues', 1.5, 2.6, 'kg/kg dry basis'),
        ]:
            values = z[field][snap]
            cmap = mpl.colormaps[cmap_name]
            # Equal-width radial bands sample their midpoint on the saved mesh.
            # 64 rings are display bins, not new computation/measurement nodes.
            rings = []
            colors = []
            for i in range(64):
                midpoint = (i + .5) / 64 * mesh[-1]
                idx = int(np.argmin(abs(mesh - midpoint)))
                value = float(values[idx])
                color = mpl.colors.to_hex(cmap(np.clip((value-lo)/(hi-lo), 0, 1)))[1:].upper()
                tex.append(f'\\definecolor{{{name}Ring{i}}}{{HTML}}{{{color}}}')
                colors.append(color)
                rings.append({'display_outer_r_m':float((i+1)/64*mesh[-1]),'source_node':idx,'source_r_m':float(mesh[idx]),'value':value})
            tex.append(f'\\newcommand{{\\{name}Section}}{{%')
            for i in reversed(range(64)):
                tex.append(f'\\fill[{name}Ring{i}] (0,0) circle[radius={(i+1)/64:.8f}];%')
            tex.append('}')
            tex.append(f'\\newcommand{{\\{name}Scale}}{{%')
            for i in range(96):
                color = mpl.colors.to_hex(cmap((i+.5)/96))[1:].upper()
                # Overlap adjacent opaque swatches to prevent SVG antialias seams.
                right = min(1.0, (i+1)/96 + .003)
                tex.append(f'\\definecolor{{cb}}{{HTML}}{{{color}}}\\fill[cb] ({i/96:.8f},0) rectangle ({right:.8f},1);%')
            tex.append('}')
            evidence.append({'quantity':field,'unit':unit,'range':[lo,hi],'colormap':cmap_name,
                             'center':float(values[0]),'surface':float(values[-1]),
                             'rings':rings})
    (OUT/'field_colors.tex').write_text('\n'.join(tex)+'\n',encoding='utf-8')
    metadata={
        'status':'working_candidate_for_user_review','data_driven_visual':True,
        'source':{'path':SRC.relative_to(ROOT).as_posix(),'sha256':digest,
                  'snapshot_time_s':1800,'node_count':len(mesh)},
        'representation':'Two views of the same material at the same instant; only exposed middle sections encode field values. Cylinder side color identifies material, not field magnitude. Geometry is schematic.',
        'display':'64 midpoint-sampled rings from the stored 10241-node fields; no smoothing, re-solving, or external values.',
        'fields':evidence,
        'mapping':{'heat_arrow':'inward, q_in=h(T_inf-theta_s)','moisture_arrow':'outward, j_C=h_m(C_s-C_eq); effective dry-basis concentration flux',
                   'scope':'Q2/Q3 fixed-radius model; C_eq:=Y_inf','symbolic_icons':'thermometer and water-drop are quantity legends, not internal structures',
                   'arrows':'Widths and lengths encode direction emphasis only, not flux magnitude.'}
    }
    (OUT/'source_map.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Two cut-face color layers generated from the existing 1800 s snapshot.')


if __name__ == '__main__':
    main()
