"""Visualize the implemented Q1 nodal FVM; symbolic geometry, no solver run."""
from pathlib import Path
import hashlib
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Wedge, Rectangle, FancyArrowPatch
from matplotlib.text import Text
from matplotlib import font_manager
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output/paper_figures/grid_algorithm_20260912'
STEM = 'fig01_fvm_algorithm'
DARK, BLUE, ORANGE = '#263B49', '#287EAA', '#D86C3E'
PALE, WARM, COOL = '#F0F3F5', '#F8DDCF', '#D2E7EF'
GRAY = '#8C9BA4'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def arrow(ax, start, end, color=DARK, lw=1.8, size=10):
    ax.add_patch(FancyArrowPatch(start, end, arrowstyle='-|>',
                                mutation_scale=size, color=color, lw=lw))


def dim(ax, left, right, y, label, color=DARK):
    ax.plot([left, right], [y, y], c=color, lw=.9)
    ax.plot([left, left], [y-.06, y+.06], c=color, lw=.9)
    ax.plot([right, right], [y-.06, y+.06], c=color, lw=.9)
    ax.text((left+right)/2, y-.10, label, ha='center', va='top', fontsize=8.5, c=color)


def main():
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family': 'Microsoft YaHei', 'font.size': 9,
        'mathtext.fontset': 'stix', 'pdf.fonttype': 42, 'svg.fonttype': 'none',
        'axes.unicode_minus': False, 'savefig.facecolor': 'white'})
    fig = plt.figure(figsize=(16.8/2.54, 10.8/2.54))
    a = fig.add_axes([.025,.435,.375,.54])
    b = fig.add_axes([.47,.47,.505,.49])
    c = fig.add_axes([.025,.025,.60,.34])
    d = fig.add_axes([.69,.025,.285,.34])
    for ax in (a,b,c,d): ax.set_axis_off()

    # (a) Seven nodal volumes in six radial intervals. Colour has no field value.
    a.set(xlim=(-1.20,1.32), ylim=(-1.24,1.15), aspect='equal')
    a.add_patch(Circle((0,0), 1, fc=PALE, ec=DARK, lw=1.4))
    a.add_patch(Circle((0,0),1/12,fc=COOL,ec=BLUE,lw=1.0))
    a.add_patch(Wedge((0,0),3.5/6,0,360,width=1/6,fc=WARM,ec=ORANGE,lw=1.2))
    a.add_patch(Wedge((0,0),4.5/6,0,360,width=1/6,fc=COOL,ec=BLUE,lw=1.0))
    a.add_patch(Wedge((0,0),1,0,360,width=1/12,fc=COOL,ec=BLUE,lw=1.0))
    for face in np.arange(.5,6)/6:
        a.add_patch(Circle((0,0),face,fill=False,ec=GRAY,lw=.75,ls=(0,(3,2))))
    arrow(a, (0,0), (1.23,0), lw=1.15, size=8)
    a.scatter(np.arange(7)/6,np.zeros(7),s=15,c=DARK,zorder=5)
    a.scatter([.5],[0],s=23,c=ORANGE,zorder=6)
    a.text(-1.18,1.09,'(a)',weight='bold')
    a.text(-.04,-.17,'0',ha='right',fontsize=8.5)
    a.text(1.0,-.17,r'$R$',ha='center')
    a.text(1.22,-.15,r'$r$',ha='center')
    a.text(.5,.13,r'$r_i$',ha='center',color=ORANGE)
    a.annotate(r'$v_i=\frac{b_i^2-a_i^2}{2}$', xy=(-.35,.36),xytext=(-.72,1.01),
               ha='center', va='center',fontsize=10,
               arrowprops={'arrowstyle':'-','color':ORANGE,'lw':.9})
    a.text(0,-1.19,r'$N$ 段，$N+1$ 个节点',ha='center',fontsize=8.5)

    # (b) One cell receives two signed contributions. These arrows are the
    # positive INTO-cell convention for H_right and -H_left, not actual flow.
    b.set(xlim=(-.38,3.30),ylim=(-.82,1.65))
    b.text(-.34,1.52,'(b)',weight='bold')
    for j in range(3):
        fc,ec=(WARM,ORANGE) if j==1 else ((COOL,BLUE) if j==2 else (PALE,GRAY))
        b.add_patch(Rectangle((j,.12),1,.66,fc=fc,ec=ec,lw=1.15))
    for face in [1,2]: b.plot([face,face],[-.02,.92],c=DARK,lw=1.1,ls=(0,(3,2)))
    for j,lab in enumerate([r'$u_{i-1}$',r'$u_i$',r'$u_{i+1}$']):
        b.scatter([j+.5],[.43],s=25,c=ORANGE if j==1 else DARK,zorder=5)
        b.text(j+.5,.93,lab,ha='center',fontsize=10)
    # Signed incoming contributions to the selected cell, in separate lanes.
    arrow(b,(.64,.25),(1.35,.25),BLUE,lw=1.9)
    arrow(b,(2.38,.63),(1.65,.63),ORANGE,lw=1.9)
    b.text(.74,-.12,r'$-H_{i-1/2}$',ha='center',color=BLUE,fontsize=10)
    b.text(2.20,1.34,r'$+H_{i+1/2}$',ha='center',color=ORANGE,fontsize=10)
    b.text(1.5,-.52,r'$s\,v_i\,\dot u_i=H_{i+1/2}-H_{i-1/2}$',ha='center',fontsize=11)

    # (c) Two boundary neighbourhoods in one radial metric, with a break.
    c.set(xlim=(-.36,5.16),ylim=(-.65,1.54))
    c.text(-.33,1.40,'(c)',weight='bold')
    for x,w,fc,ec in [(0,.45,COOL,BLUE),(.45,.90,PALE,GRAY),
                       (2.65,.9,PALE,GRAY),(3.55,.45,COOL,BLUE)]:
        c.add_patch(Rectangle((x,.19),w,.57,fc=fc,ec=ec,lw=1.1))
    for x in [0,4]: c.plot([x,x],[.07,.87],c=DARK,lw=1.65)
    for x in [.45,3.55]: c.plot([x,x],[.08,.86],c=GRAY,lw=.9,ls=(0,(3,2)))
    c.scatter([0,.90,3.10,4],[.475]*4,s=21,c=DARK,zorder=6)
    for x,lab in [(0,r'$r_0=0$'),(.90,r'$r_1$'),(3.05,r'$r_{N-1}$'),(4,r'$r_N=R$')]:
        c.text(x,.98,lab,ha='center',fontsize=9)
    c.plot([1.64,1.76],[.40,.55],c=GRAY,lw=1.1)
    c.plot([1.83,1.95],[.40,.55],c=GRAY,lw=1.1)
    dim(c,0,.45,.02,r'$\Delta r/2$',BLUE)
    dim(c,3.55,4,.02,r'$\Delta r/2$',BLUE)
    c.text(.45,-.53,r'$H_{-1/2}=0$',ha='center',fontsize=9.5)
    c.text(3.15,-.53,r'$H_{N+1/2}=Rb(g-u_N)$',ha='center',fontsize=9.5)
    arrow(c,(4.94,.47),(4.04,.47),ORANGE,lw=1.9)
    c.text(4.72,.82,r'$g(t)$',ha='center',fontsize=9)

    # (d) Symbolic sparsity only: arrows/dependence never imply explicit time stepping.
    d.set(xlim=(-1.38,7.35),ylim=(-.88,7.68),aspect='equal')
    d.text(-1.27,7.24,'(d)',weight='bold')
    for row in range(7):
        for col in range(7):
            fc=PALE
            if abs(row-col)<=1: fc=ORANGE if row==3 else BLUE
            d.add_patch(Rectangle((col,6-row),.82,.82,fc=fc,ec='white',lw=.25))
    # Brackets, not axes, indicate a coefficient matrix.
    d.plot([-.14,-.35,-.35,-.14],[6.94,6.94,-.10,-.10],c=DARK,lw=1.0)
    d.plot([7.00,7.20,7.20,7.00],[6.94,6.94,-.10,-.10],c=DARK,lw=1.0)
    d.text(-.90,3.4,r'$J=$',ha='center',fontsize=10)
    d.text(3.4,-.77,'相邻节点耦合',ha='center',fontsize=8.5)

    OUT.mkdir(parents=True,exist_ok=True)
    outputs={}
    for ext in ['png','pdf','svg']:
        p=OUT/f'{STEM}.{ext}';fig.savefig(p,dpi=360)
        outputs[ext]={'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}
    for item in fig.findobj(Text): item.set_visible(False)
    p=OUT/f'{STEM}_no_text.png';fig.savefig(p,dpi=360)
    outputs['no_text']={'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}
    p=OUT/f'{STEM}_gray.png';Image.open(OUT/f'{STEM}.png').convert('L').save(p)
    outputs['gray']={'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)}
    plt.close(fig)
    sources=['A题.pdf','docs/Q1/solution_brief.md','src/Q1/solve.py']
    record={'figure_id':STEM,'data_driven_visual':False,'width_cm':16.8,'height_cm':10.8,
        'sources':{p:sha(ROOT/p) for p in sources},
        'generator':{'path':Path(__file__).relative_to(ROOT).as_posix(),'sha256':sha(__file__)},
        'mapping':{'a':'Illustrative N=6, N+1 nodal control volumes; annular area weights, no physical layers',
            'b':'arrows show signed incoming contributions -H_left and +H_right to cell i; not actual T/C flow directions',
            'c':'clipped endpoint cells store state; centre zero flux, surface exchange; R is fixed Q1 radius',
            'd':'symbolic structural nonzeros of one scalar field Jacobian; dimension/value not actual',
            'scope':'Q1 spatial FVM and Jacobian; not a Q4 moving-grid or fixed-order BDF stencil',
            'colors':'selected cell/row orange, adjacent/boundary cells blue; no field-value encoding'},
        'outputs':outputs,'status':'working reading figure; no final manuscript approval claimed'}
    (OUT/f'{STEM}_sources.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(OUT/f'{STEM}.png')


if __name__=='__main__': main()
