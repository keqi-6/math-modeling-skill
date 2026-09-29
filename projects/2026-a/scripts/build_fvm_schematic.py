"""Draw the actual node-centred radial finite-volume topology; no solver runs."""
from pathlib import Path
import hashlib
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Wedge, Rectangle
from matplotlib.text import Text
from matplotlib import font_manager
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/paper_figures/brief_refresh_20260911'
STEM = 'fig01_fvm_cells'
BLUE, ORANGE, DARK = '#0072BD', '#D95319', '#273640'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'font.size': 9,
        'mathtext.fontset': 'stix', 'pdf.fonttype': 42, 'svg.fonttype': 'none',
        'axes.unicode_minus': False, 'savefig.facecolor': 'white'})
    fig = plt.figure(figsize=(15.8/2.54, 8.5/2.54))
    a = fig.add_axes([.025,.13,.405,.79])
    b = fig.add_axes([.485,.55,.49,.36])
    c = fig.add_axes([.485,.06,.49,.36])
    for ax in [a,b,c]:
        ax.set_axis_off()
    a.set(xlim=(-1.19,1.25), ylim=(-1.22,1.15), aspect='equal')
    # N=6 is illustrative, with exactly the same boundary truncation rule.
    n=6
    a.add_patch(Circle((0,0),1,fc='#F5F8FA',ec=DARK,lw=1.6))
    a.add_patch(Circle((0,0),.5/n,fc='#CCE2F0',ec=BLUE,lw=1))
    a.add_patch(Wedge((0,0),3.5/n,0,360,width=1/n,fc='#F6D8C8',ec=ORANGE,lw=1.3))
    a.add_patch(Wedge((0,0),1,0,360,width=.5/n,fc='#CCE2F0',ec=BLUE,lw=1.3))
    for face in [.5/n,1.5/n,2.5/n,3.5/n,4.5/n,5.5/n]:
        a.add_patch(Circle((0,0),face,fill=False,ec='#82919B',lw=.6,ls='--'))
    a.plot([0,1.12],[0,0],color=DARK,lw=1)
    a.scatter(np.arange(n+1)/n,np.zeros(n+1),s=14,c=DARK,zorder=5)
    a.annotate('',(1.12,0),(.9,0),arrowprops={'arrowstyle':'->','lw':1,'color':DARK})
    a.text(1.13,-.09,r'$r$',ha='center')
    a.text(-.05,-.13,r'$0$',ha='right')
    a.text(1,-.14,r'$R$',ha='center')
    a.text(.50,.11,r'$r_i$',ha='center',color=ORANGE)
    a.text(-1.14,1.09,'(a)',weight='bold')
    # The annotation points into the annulus, not to an unrelated boundary.
    a.annotate(r'$v_i=\int_{a_i}^{b_i} r\,\mathrm{d}r$',xy=(-.36,.36),xytext=(-.72,1.0),
        ha='center',va='center',arrowprops={'arrowstyle':'-','color':ORANGE,'lw':.85},fontsize=10)
    a.text(0,-1.18,'圆环截面',ha='center',fontsize=8.5)

    # Two adjacent annuli represented by their radial intervals. Geometry is
    # radial length here, not an assertion that physical cell areas are equal.
    b.set(xlim=(-.4,3.05),ylim=(-.75,1.50))
    b.text(-.38,1.38,'(b)',weight='bold')
    for x,fc,ec in [(.0,'#F6D8C8',ORANGE),(1.25,'#D7E7F0',BLUE)]:
        b.add_patch(Rectangle((x,.0),1.25,.60,fc=fc,ec=ec,lw=1.1))
    b.plot([1.25,1.25],[-.08,.68],color=DARK,lw=2.1)
    b.scatter([.625,1.875],[.30,.30],s=23,c=DARK,zorder=5)
    b.text(.625,.82,r'$r_i$',ha='center')
    b.text(1.875,.82,r'$r_{i+1}$',ha='center')
    for x,label in [(0,r'$r_{i-1/2}$'),(1.25,r'$r_{i+1/2}$'),(2.5,r'$r_{i+3/2}$')]:
        b.text(x,-.21,label,ha='center',fontsize=8.5)
    b.text(.625,1.19,r'$+H_{i+1/2}$',ha='center',color=ORANGE,fontsize=10)
    b.text(1.875,1.19,r'$-H_{i+1/2}$',ha='center',color=BLUE,fontsize=10)
    b.text(1.25,-.64,'共享同一面，收支中异号计入',ha='center',fontsize=8)

    # Boundary node remains on the boundary and has a half radial interval.
    c.set(xlim=(-.35,3.2),ylim=(-.7,1.53))
    c.text(-.33,1.43,'(c)',weight='bold')
    # Centre: domain begins at x=0. A full neighbouring cell gives a width cue.
    c.add_patch(Rectangle((0,.12),.43,.50,fc='#CCE2F0',ec=BLUE,lw=1.2))
    c.add_patch(Rectangle((.43,.12),.86,.50,fc='#F5F8FA',ec='#A1ABB2',lw=.8))
    c.plot([0,0],[-.01,.76],color=DARK,lw=1.6)
    c.scatter([0,.86],[.37,.37],s=20,c=DARK,zorder=4)
    c.text(0,.91,r'$r_0=0$',ha='center')
    c.text(.86,.91,r'$r_1$',ha='center')
    c.annotate('',(.43,-.05),(0,-.05),arrowprops={'arrowstyle':'|-|','lw':.7,'color':BLUE})
    c.text(.215,-.30,r'$\Delta r/2$',ha='center',fontsize=9)
    c.text(.5,-.65,'中心：零通量',ha='center',fontsize=8)
    # Surface: whole inner neighbour followed by the half surface cell.
    c.add_patch(Rectangle((1.65,.12),.86,.50,fc='#F5F8FA',ec='#A1ABB2',lw=.8))
    c.add_patch(Rectangle((2.51,.12),.43,.50,fc='#CCE2F0',ec=BLUE,lw=1.2))
    c.plot([2.94,2.94],[-.01,.76],color=DARK,lw=1.6)
    c.scatter([2.08,2.94],[.37,.37],s=20,c=DARK,zorder=4)
    c.text(2.01,.91,r'$r_{N-1}$',ha='center')
    c.text(2.94,.91,r'$r_N=R$',ha='center')
    c.annotate('',(2.94,-.05),(2.51,-.05),arrowprops={'arrowstyle':'|-|','lw':.7,'color':BLUE})
    c.text(2.725,-.30,r'$\Delta r/2$',ha='center',fontsize=9)
    c.text(2.38,-.65,'表面：Robin交换',ha='center',fontsize=8)
    OUT.mkdir(parents=True,exist_ok=True)
    outputs={}
    for ext in ['png','pdf','svg']:
        p=OUT/f'{STEM}.{ext}';fig.savefig(p,dpi=320);outputs[ext]={'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}
    texts=fig.findobj(Text)
    for text in texts: text.set_visible(False)
    p=OUT/f'{STEM}_no_text.png';fig.savefig(p,dpi=320);outputs['no_text']={'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}
    p=OUT/f'{STEM}_gray.png';Image.open(OUT/f'{STEM}.png').convert('L').save(p);outputs['gray']={'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}
    plt.close(fig)
    sources=['A题.pdf','planning/Q1/model_spec.md']
    record={'figure_id':STEM,'data_driven_visual':False,'width_cm':15.8,'height_cm':8.5,
        'source_files':{rel:{'sha256':sha(ROOT/rel)} for rel in sources},
        'generator':{'path':Path(__file__).relative_to(ROOT).as_posix(),'sha256':sha(__file__)},
        'mapping':{'object':'axisymmetric middle cross-section; no physical shells',
                   'grid':'Illustrative N=6; faces at (i+1/2)R/N, endpoint cells clipped at 0,R',
                   'annular_weight':'vi=(bi^2-ai^2)/2, centre dr^2/8, surface R*dr/2-dr^2/8',
                   'shared_face':'same H contributes +H to left balance and -H to right balance; H is gradient transport, not outward physical flux',
                   'boundary':'nodes stay at actual centre and surface, both keep their clipped storage volumes',
                   'color':'orange interior control volume; blue adjacent or boundary control volume, not T/C values'},
        'outputs':outputs,'acceptance':'working replacement for team review; not final manuscript approval'}
    (OUT/f'{STEM}_sources.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(OUT/f'{STEM}.png')


if __name__=='__main__': main()
