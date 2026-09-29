"""Redraw seven current figures; the spacetime grid has an editable SVG source.
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
