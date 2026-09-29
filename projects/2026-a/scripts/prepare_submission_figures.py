"""Prepare approved figure assets and portable redraw sources; never run a solver.

This is a workspace-only white-list builder. The appendix receives standalone
plotting/extraction modules, not this project's planning or audit machinery.
"""
from __future__ import annotations
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SUPPORT = ROOT / 'output/submission_appendix/support'
CODE = SUPPORT / 'code'
FIG = SUPPORT / 'figures'
DATA = SUPPORT / 'figure_data'
REBUILD = ROOT / 'output/paper_figures/structural_rebuild_20260912'
COMPACT = 'restructured_figure_data.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.rstrip()+'\n', encoding='utf-8')


def functions(filename, names):
    source = (ROOT/'scripts'/filename).read_text(encoding='utf-8-sig')
    nodes = {n.name: n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef)}
    return {name: ast.get_source_segment(source, nodes[name]) for name in names}


def trim_save_metadata(text):
    """Keep the plotting body, replacing the old workspace-only metadata call."""
    lines=text.splitlines()
    tree=ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
            call=node.value
            if isinstance(call.func,ast.Name) and call.func.id=='save':
                name=ast.literal_eval(call.args[1])
                lines[node.lineno-1:node.end_lineno]=[f'    save(fig, {name!r})']
                break
    return '\n'.join(lines)


HEADER = '''"""Portable functions extracted from the team's existing figure source.
No solver is imported. See figures/README.md for scope and data provenance.
"""
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, Normalize, to_rgb
from matplotlib.cm import ScalarMappable
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.text import Text
import matplotlib.patheffects as path_effects
import numpy as np
DATA = Path(__file__).resolve().parents[1] / "figure_data"
OUT = Path.cwd() / "redrawn_figures"

def obs():
    return json.loads((DATA/"radius_observations.json").read_text(encoding="utf-8"))

def export(fig, name, dpi=300, transparent=False):
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("pdf", "svg", "png"):
        fig.savefig(OUT/f"{name}.{ext}", dpi=dpi, transparent=transparent)
    plt.close(fig)
'''


EXTRACT = r'''"""Extract only plotted arrays from existing saved results (no model execution).

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
'''


REDRAW = r'''"""Redraw seven current figures; the spacetime grid has an editable SVG source.
Read compact numerical arrays and write to a separate output directory.
"""
from pathlib import Path
import argparse
import importlib
import subprocess
import sys
import matplotlib
matplotlib.use('Agg')
from matplotlib import font_manager
import matplotlib.pyplot as plt

def font_name(path=None):
    if path:
        font_manager.fontManager.addfont(str(path))
        return font_manager.FontProperties(fname=str(path)).get_name()
    candidates=['Microsoft YaHei','Noto Sans CJK SC','Source Han Sans SC','SimHei','PingFang SC']
    installed={f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            return name
    raise RuntimeError('请安装中文字体，或以 --font 指定字体文件。')

def configure(font, kind):
    plt.rcdefaults()
    plt.rcParams.update({'font.family':font,'font.size':9,'axes.labelsize':9,
        'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,'axes.titlesize':9,
        'mathtext.fontset':'stix','axes.unicode_minus':False,'axes.linewidth':.85,
        'lines.linewidth':1.8,'xtick.direction':'in','ytick.direction':'in',
        'pdf.fonttype':42,'ps.fonttype':42,'svg.fonttype':'none',
        'figure.facecolor':'white','savefig.facecolor':'white'})
    if kind=='coordinates':
        plt.rcParams.update({'font.size':8.5,'axes.linewidth':.8})
    elif kind=='sections':
        plt.rcParams.update({'figure.facecolor':'none','savefig.facecolor':'none',
                             'xtick.direction':'out','ytick.direction':'out'})

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data',type=Path,default=Path(__file__).resolve().parents[1]/'figure_data')
    p.add_argument('--font',type=Path)
    p.add_argument('--only',nargs='*',choices=['1-1','1-3','2-1','2-2','3-1','4-1','4-2'])
    a=p.parse_args(); output=a.output.resolve()
    baseline=Path(__file__).resolve().parents[1]/'figures'
    if output==baseline.resolve() or baseline.resolve() in output.parents:
        raise ValueError('重绘请使用 figures 以外的新目录，保留随包图件。')
    font=font_name(a.font)
    selected=[x for x in ['1-1','2-2','3-1'] if not a.only or x in a.only]
    if selected:
        command=[sys.executable,'-B',str(Path(__file__).with_name('figure_restructured.py')),
                 '--data-dir',str(a.data.resolve()),'--out-dir',str(output),'--only',*selected]
        if a.font: command.extend(['--font-path',str(a.font.resolve())])
        subprocess.run(command,check=True,timeout=180)
    for module,label,function in [('core','1-3','fig03'),('fields','2-1','render'),
                                  ('coordinates','4-1','render'),('sections','4-2','render')]:
        if a.only and label not in a.only: continue
        configure(font,module)
        m=importlib.import_module('figure_'+module); m.DATA=a.data.resolve(); m.OUT=output
        getattr(m,function)()
        print('Rendered figure '+label)

if __name__=='__main__': main()
'''


def build_modules():
    write(CODE/'extract_figure_data.py', EXTRACT)
    write(CODE/'redraw_figures.py', REDRAW)
    write(CODE/'requirements_figures.txt', '# Versions used for the supplied redraw check.\nnumpy==2.5.3\nmatplotlib==3.11.1\n')
    f = functions('build_paper_figures.py', ['axes_pair','tag','upright_ylabels','line','fig03'])
    f['fig03']=f['fig03'].replace('    rel = "output/Q1/run_n5120.npz"\n    p = source(rel, "c3eb65e2b2f1ccea870986401c5f1ae42346562be1fe11ace3e61104dc79cc7e")',
                                '    p = DATA/"q1_profiles.npz"')
    f['fig03']=f['fig03'].replace('Keep the existing 100/600/1800 s styles; add two intermediate profiles.',
                                'Five saved times use distinct markers and line styles.')
    f['fig03']=trim_save_metadata(f['fig03'])
    core = HEADER + '''
COLORS = ["#0072BD", "#D95319", "#3A923A", "#7E2F8E", "#333333"]
STYLES = ["-", "--", "-.", ":", (0, (5, 1, 1, 1))]
MARKERS = ["o", "s", "^", "D", "v"]
WIDTH = 15.8/2.54
def save(fig, name):
    upright_ylabels(fig)
    export(fig, name)
'''
    write(CODE/'figure_core.py', core+'\n\n'+'\n\n'.join(f.values()))

    f=functions('build_q2_field_sample.py',['palette','draw_fields'])
    constants='''
WIDTH_CM=15.8
HEIGHT_IN=3.2
PALETTE_POSITIONS=[0,.25,.5,.75,1]
TEMPERATURE_COLORS=["#fffaf1","#fee0c5","#f9b39d","#e77968","#b8443f"]
MOISTURE_COLORS=["#eaf3f7","#d6eff5","#99d3e1","#469dbf","#155c88"]
MOISTURE_LIMITS=[0,2.55]
CONTOUR_LEVELS=[[35,40,45,48],[1.5,2,2.4]]
LABEL_POSITIONS=[[(.65,1.1),(.95,1.65),(1.45,1.1),(1.85,1.65)],[(1.5,1.8),(1.8,1.25),(1.1,.75)]]
'''
    wrapper='''
def render():
    with np.load(DATA/"q2_fields.npz", allow_pickle=False) as z:
        fig=draw_fields(z["time_s"]/3600,z["radius_m"]*100,[z[k].T for k in ["temperature_C","moisture_kg_kg"]])
    export(fig,"fig04_q2_fields_sample")
'''
    write(CODE/'figure_fields.py',HEADER+constants+'\n\n'.join(f.values())+wrapper)

    f=functions('build_q4_coordinate_figure.py',['gray','draw'])
    constants='''
WIDTH_CM,HEIGHT_CM=15.8,6.4
BLUE,ORANGE,INK="#0072B2","#D55E00","#45525B"
BODY,GRAY="#F3EBDD","#747474"
'''
    wrapper='''
def render():
    a=np.array(obs()["q4_radius_time_s_cm"])
    selected=[float(a[a[:,0]==t,1].item()) for t in [0,21600]]
    export(draw(a[:,0]/3600,a[:,1],selected),"fig06_q4_coordinates",dpi=360)
'''
    write(CODE/'figure_coordinates.py',HEADER+constants+'\n\n'.join(f.values())+wrapper)

    f=functions('build_q4_section_sample.py',['grey','make_figure'])
    constants='''
PALETTE=("#eaf3f7","#d6eff5","#99d3e1","#469dbf","#155c88")
THRESHOLD=.15
THRESHOLD_COLOR="#66395F"
FIELD_LIMITS=(0,2.55)
AXIS_LIMIT_CM=2.2
DISPLAY_RINGS=512
WIDTH_CM,HEIGHT_CM=15.8,11.5
'''
    # The baseline endpoint label is unchanged; alternative retained snapshots
    # supplied by the user are displayed using their own actual time instead.
    f['make_figure']=f['make_figure'].replace('else "51.0969 h"','else f"{frame[\'time_s\']/3600:.4f} h"')
    wrapper='''
def render():
    frames=[]
    with np.load(DATA/"q4_sections.npz",allow_pickle=False) as z:
        xi=z["mesh_xi"]
        for t,R,C in zip(z["snapshot_time_s"],z["snapshot_radius_m"],z["moisture_snapshots"]):
            assert np.isfinite(C).all() and np.max(np.diff(C))<1e-12
            radius=100*float(R)
            level=float(np.interp(.15,C[::-1],(radius*xi)[::-1])) if C.min()<.15<C.max() else None
            frames.append({"time_s":int(t),"radius_cm":radius,"moisture":C,"threshold_radius_cm":level})
        fig=make_figure(xi,frames)
    export(fig,"fig07_q4_sections_sample",dpi=360,transparent=True)
'''
    write(CODE/'figure_sections.py',HEADER+constants+'\n\n'.join(f.values())+wrapper)
    standalone=(ROOT/'scripts/build_restructured_figures.py').read_text(encoding='utf-8-sig')
    standalone=standalone.replace('python build_restructured_figures.py --source',
                                  'python figure_restructured.py --source')
    write(CODE/'figure_restructured.py',standalone)


def main():
    FIG.mkdir(parents=True, exist_ok=True); DATA.mkdir(parents=True, exist_ok=True)
    manifest=json.loads((ROOT/'output/paper_figures/current/figure_manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['figures'])==8
    expected_numbers={'图1-1','图1-2','图1-3','图2-1','图2-2','图3-1','图4-1','图4-2'}
    assert {v['number'] for v in manifest['figures']}==expected_numbers
    old_manifest=FIG/'figure_manifest.json'
    previous=json.loads(old_manifest.read_text(encoding='utf-8'))['figures'] if old_manifest.is_file() else []
    records=[]
    for entry in manifest['figures']:
        prefix=entry['number'].replace('图','fig').replace('-','_')
        row={'number':entry['number'],'caption':entry['caption'],'files':{}}
        for ext in ('pdf','svg','png'):
            src=ROOT/entry['files'][ext]['path']
            assert digest(src)==entry['files'][ext]['sha256'], src
            if entry['number']=='图1-2':
                assert 'spacetime_grid_20260912/fig01_spacetime_grid' in src.as_posix()
            dst=FIG/(prefix+'_'+src.name); shutil.copy2(src,dst)
            row['files'][ext]={'file':dst.name,'sha256':digest(dst),'bytes':dst.stat().st_size}
        row['editing']='SVG geometry source' if entry['number']=='图1-2' else ('Python geometry schematic' if entry['number']=='图1-1' else 'Python from compact figure data')
        records.append(row)
    current_names={v['file'] for row in records for v in row['files'].values()}
    for row in previous:
        for info in row['files'].values():
            if info['file'] in current_names:
                continue
            superseded=FIG/info['file']
            assert superseded.resolve().parent==FIG.resolve(), superseded
            assert superseded.suffix in {'.pdf','.svg','.png'}, superseded
            if superseded.is_file():
                assert digest(superseded)==info['sha256'], 'Unrecorded edit: '+str(superseded)
                superseded.unlink()
    previous_support=json.loads((SUPPORT.parent/'support_manifest.json').read_text(encoding='utf-8'))
    recorded={v['path']:v['sha256'] for v in previous_support['files']}
    retired=['code/figure_startup.py','code/figure_radius_sensitivity.py','code/figure_environment.py',
             'figure_data/fig08_q1_startup_precision_data.json',
             'figure_data/fig10_q4_radius_sensitivity.data.json',
             'figure_data/q3_drying.npz','figure_data/observations_and_convergence.json']
    retired += ['figures/scene/'+name for name in ('cutaway_scene.html','cutaway_data.json',
                                                'three.module.js','three.core.js','LICENSE')]
    for relative in retired:
        path=(SUPPORT/relative).resolve()
        assert path.is_relative_to(SUPPORT.resolve()) and path!=SUPPORT.resolve()
        if path.is_file():
            assert digest(path)==recorded.get(relative), 'Unrecorded edit: '+str(path)
            path.unlink()
    scene=(FIG/'scene').resolve()
    assert scene.is_relative_to(SUPPORT.resolve())
    if scene.is_dir() and not any(scene.iterdir()): scene.rmdir()
    build_modules()
    subprocess.run([sys.executable,'-B',str(CODE/'extract_figure_data.py'),
        '--q1',str(ROOT/'output/Q1/run_n5120.npz'),'--q2',str(ROOT/'output/Q2/run_n10240_startsafe.npz'),
        '--q4',str(ROOT/'output/Q4/run_n10240-v1-20260911.npz'),'--output',str(DATA)],check=True)
    geometry=json.loads((ROOT/'output/GEOMETRY/q4_radius.json').read_text(encoding='utf-8'))
    observed={'q4_radius_time_s_cm':[[v['time_s'],v['radius_cm']] for v in geometry['nodes']],
              'source':'附件2.xlsx','units':{'time':'s','radius':'cm'}}
    write(DATA/'radius_observations.json',json.dumps(observed,ensure_ascii=False,indent=2))
    baseline=json.loads((REBUILD/'compact'/COMPACT).read_text(encoding='utf-8'))
    assert json.loads((DATA/COMPACT).read_text(encoding='utf-8'))==baseline
    data_manifest_path=DATA/'data_manifest.json'
    data_manifest=json.loads(data_manifest_path.read_text(encoding='utf-8'))
    data_manifest['files'][COMPACT]={'sha256':digest(DATA/COMPACT),'bytes':(DATA/COMPACT).stat().st_size,
                                   'contents':'Main-state diffusivity decomposition and radial completion times'}
    write(data_manifest_path,json.dumps(data_manifest,ensure_ascii=False,indent=2))
    write(FIG/'figure_manifest.json',json.dumps({'figures':records,'exports':'Eight supplied figures; seven Python redraws and one editable spacetime SVG.'},ensure_ascii=False,indent=2))
    write(FIG/'README.md',README)
    paths=[p for base in (FIG,DATA) for p in base.rglob('*') if p.is_file()]
    print(json.dumps({'figure_and_data_files':len(paths),'figure_and_data_bytes':sum(p.stat().st_size for p in paths),
                      'python_modules':[p.name for p in sorted(CODE.glob('*figure*.py'))]},ensure_ascii=False,indent=2))


README='''# 论文图件、数据与重绘

本目录保存四问当前选用的8幅图，每幅均有PDF、SVG和PNG。文件名前缀对应逐问图号，论文连续编号由队伍统一。图按约15.8 cm宽制作，图片内部不另加论文式标题。PDF适合LaTeX，SVG便于矢量编辑，PNG便于兼容插图；时空色场包含栅格层，其坐标与标注为矢量。

| 图号 | 内容 | 修改入口 |
|---|---|---|
| 1-1 | 圆环控制体、径向节点与共享面 | Python：restructured |
| 1-2 | 径向与时间交点网格 | 原SVG |
| 1-3 | 五时刻径向剖面 | Python：core |
| 2-1 | 前三小时温度与含水率时空分布 | Python：fields |
| 2-2 | 扩散系数对数变化的升温项、失水项与净值 | Python：restructured |
| 3-1 | 21个规定半径的达标进程 | Python：restructured |
| 4-1 | 实测半径与材料坐标对应 | Python：coordinates |
| 4-2 | 同一厘米尺度的六个含水率截面 | Python：sections |

## 重绘

在支撑材料根目录运行（合并素材包中先进入support）：

```text
python -m pip install -r code/requirements_figures.txt
python code/redraw_figures.py --output redrawn_figures
```

默认生成除图1-2外七幅图的三种格式。`--only 1-3 2-1`选择部分图；`--font 字体文件路径`指定中文字体。原图使用Microsoft YaHei，不分发系统字体。跨平台字体或软件版本会影响文字布局，应按最终页内尺寸检查。重绘目录必须与随附原图分开。

`figure_data`保存未舍入的绘图数值：Q1五时刻×21半径、Q2前三小时逐秒×21半径、Q4六份完整径向快照；`radius_observations.json`保存题给半径节点。`restructured_figure_data.json`包含图2-2的六个主解状态及对数分解、图3-1各规定半径首个严格达标秒和全节点终点。来源、单位与提取口径随数据保存，文件校验值见`data_manifest.json`。图件说明与文件对应见`figure_manifest.json`。

如已有新的同格式结果，可以仅提取画图数据后重绘，无需再次求解：

```text
python code/extract_figure_data.py --q1 generated/q1.npz --q2 generated/q23.npz --q4 generated/q4.npz --output new_figure_data
python code/redraw_figures.py --data new_figure_data --output new_figures
```

三个输入参数均指定实际文件。提取器读取已有场值及全节点最大值，Q4需保存0、6、18、36、48 h和最终时刻的完整径向快照；半径观测改变时，以`--observations 新JSON路径`同步。程序只做数值摘取与一致性核对，不能验证替换后结果的物理模型。

## 图形含义

图1-1的圆环、径向控制体和图1-2的时空交点都是算法示意。显示节点数不等于实际网格数，时间层间距不代表固定步长；图1-1说明空间通量共享，图1-2说明隐式时间层中的关系。图1-2完整编辑源为SVG。

图2-2按附录3的指数本构精确分解主解沿程的对数变化；两项分别由实际温度与含水率变化计算，不是相互独立的因果效应，也不代表最终干燥时间的分项贡献。图3-1只显示题给21个半径的达标顺序，完整干燥终点仍取全部数值节点的最大含水率；提取时核对显示位置在首次达标之后没有越回阈值。

Q4材料环对应均匀径向收缩假设，不是内部位移观测；六截面按实际半径使用相同厘米尺度，圆外不填零，阈值虚线是含水率等值线。所有图注与正文解释由队伍合稿时统一。
'''

if __name__=='__main__':
    main()
