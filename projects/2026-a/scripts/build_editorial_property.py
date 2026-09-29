"""Build an internal, layered SVG composition from Appendix 3 and saved Q2 states.

All curves, projected surface geometry, and bar endpoints are data driven.
The SVG master uses editable labels and separately labelled Inkscape layers.
"""
from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import subprocess
import sys

import contourpy
import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'planning/figure_redraw_trial_20260912'
SOURCE = ROOT / 'output/Q2/run_n10240_startsafe.npz'
TEXT = '#243A46'
HEAT = '#C66A4B'
WATER = '#237F99'
GRID = '#D9E1E5'


def D(t, c):
    return 2.4e-3 * np.exp(-.45 / np.asarray(c) - 3850 / (np.asarray(t) + 273.15))


def K(c):
    return .21 + .38 * np.asarray(c) / (1 + np.asarray(c))


def pts(a):
    return ' '.join(f'{x:.3f},{y:.3f}' for x, y in a)


def project(t, c, d):
    """Orthographic axonometric projection, with literal common data scales."""
    u = (np.asarray(t)-28)/22
    v = (np.asarray(c)-1)/1.55
    w = (np.asarray(d)-3)/11
    return np.stack((245+290*u-155*v, 485-82*u-92*v-238*w), axis=-1)


def color(value):
    anchors = np.array([[245, 241, 227], [177, 211, 213], [54, 135, 156], [31, 74, 103]])
    z = np.clip((float(value)-4)/10, 0, 1)*3
    i = min(int(z), 2)
    rgb = np.rint(anchors[i]*(1-(z-i))+anchors[i+1]*(z-i)).astype(int)
    return '#' + ''.join(f'{v:02x}' for v in rgb)


class Drawing:
    def __init__(self):
        self.parts = []

    def add(self, s):
        self.parts.append(s)

    def line(self, a, b, stroke=TEXT, width=1.1, dash=None):
        style = f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<line x1="{a[0]:.3f}" y1="{a[1]:.3f}" x2="{b[0]:.3f}" y2="{b[1]:.3f}" stroke="{stroke}" stroke-width="{width}"{style}/>')

    def polyline(self, xy, stroke=TEXT, width=1.5, dash=None):
        style = f' stroke-dasharray="{dash}"' if dash else ''
        self.add(f'<polyline points="{pts(xy)}" fill="none" stroke="{stroke}" stroke-width="{width}" stroke-linejoin="round"{style}/>')

    def polygon(self, xy, fill, stroke=None, width=.4):
        self.add(f'<polygon points="{pts(xy)}" fill="{fill}" stroke="{stroke or fill}" stroke-width="{width}" stroke-linejoin="round"/>')

    def rect(self, x, y, w, h, fill, stroke='none', width=1):
        self.add(f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')

    def marker(self, xy, kind, size=5.5, fill='white', stroke=TEXT, width=1.8):
        x, y = xy
        if kind == 'circle':
            self.add(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{size}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>')
        else:
            self.polygon([(x,y-size*1.25),(x+size*1.25,y),(x,y+size*1.25),(x-size*1.25,y)], fill, stroke, width)

    def text(self, x, y, text, size=17.6, anchor='start', weight='normal', fill=TEXT):
        self.add(f'<text x="{x}" y="{y}" fill="{fill}" font-family="Microsoft YaHei, Arial" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}">{html.escape(text)}</text>')

    def layer(self, ident, label):
        self.add(f'<g id="{ident}" inkscape:groupmode="layer" inkscape:label="{label}">')

    def end(self):
        self.add('</g>')


def build(no_text=False):
    with np.load(SOURCE, allow_pickle=False) as z:
        ids = np.flatnonzero((z['time_s'] <= 10800) & (z['time_s'] % 60 == 0))
        time = z['time_s'][ids]
        temperatures = z['temperature_C'][ids][:, [0, -1]]
        moisture = z['moisture_kg_kg'][ids][:, [0, -1]]
    theta = np.linspace(28, 50, 97)
    concentration = np.linspace(1, 2.55, 65)
    tt, cc = np.meshgrid(theta, concentration)
    zz = D(tt, cc)*1e9
    assert np.all(np.diff(zz, axis=0)>0) and np.all(np.diff(zz, axis=1)>0)
    assert np.all(np.diff(K(concentration))>0)
    heat = -3850*(1/(temperatures[-1]+273.15)-1/(28+273.15))
    water = -.45*(1/moisture[-1]-1/2.55)
    net = np.log(D(temperatures[-1], moisture[-1])/D(28,2.55))
    assert np.allclose(heat+water, net, atol=5e-15)

    g = Drawing()
    g.add('<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" width="170mm" height="103.7mm" viewBox="0 0 1000 610">')
    g.add('<defs><pattern id="property-loss-hatch" width="8" height="8" patternUnits="userSpaceOnUse"><path d="M-2,2 l4,-4 M0,8 l8,-8 M6,10 l4,-4" stroke="white" stroke-width=".8" opacity=".35"/></pattern></defs>')
    g.layer('property-layout', '01 Layout')
    g.rect(0,0,1000,610,'white')
    g.line((610,48),(610,565),GRID,.8)
    g.line((645,313),(978,313),GRID,.8)
    g.end()

    g.layer('property-surface-floor', '02 D floor projection')
    # Each floor tile shares the scalar color of its exact surface counterpart.
    for j in range(len(concentration)-1):
        for i in range(len(theta)-1):
            vertices = [(theta[i],concentration[j]),(theta[i+1],concentration[j]),
                        (theta[i+1],concentration[j+1]),(theta[i],concentration[j+1])]
            fill = color(np.mean(zz[j:j+2,i:i+2]))
            # A white overlay later lowers floor salience without altering its scales.
            g.polygon([project(t,c,3) for t,c in vertices],fill,width=.4)
    floor = [project(28,1,3),project(50,1,3),project(50,2.55,3),project(28,2.55,3)]
    g.add(f'<polygon points="{pts(floor)}" fill="white" opacity=".32"/>')
    generator = contourpy.contour_generator(x=theta,y=concentration,z=zz)
    for level in [5,6,8,10,12]:
        for segment in generator.lines(level):
            g.polyline(project(segment[:,0],segment[:,1],3),stroke='#587C89',width=.8)
    g.polygon(floor, 'none', '#91A7B0', .9)
    g.end()

    g.layer('property-surface', '03 D response surface')
    # Render distant grid quads first. No transparency, lighting distortion, or mesh overlay.
    indices = [(j,i) for j in range(len(concentration)-1) for i in range(len(theta)-1)]
    indices.sort(key=lambda ji:ji[0]/len(concentration)+ji[1]/len(theta),reverse=True)
    for j,i in indices:
        quad = [project(theta[i],concentration[j],zz[j,i]),
                project(theta[i+1],concentration[j],zz[j,i+1]),
                project(theta[i+1],concentration[j+1],zz[j+1,i+1]),
                project(theta[i],concentration[j+1],zz[j+1,i])]
        fill=color(np.mean(zz[j:j+2,i:i+2]))
        g.polygon(quad,fill,width=.55)
    # Subtle iso-D traces carry geometry without a rectilinear wire cage.
    for level in [6,8,10,12]:
        for segment in generator.lines(level):
            g.polyline(project(segment[:,0],segment[:,1],level),stroke='#EAF1EC',width=.85)
    for c in [1,2.55]:
        g.polyline(project(theta,c,D(theta,c)*1e9),stroke='#38657A',width=.9)
    for t in [28,50]:
        g.polyline(project(t,concentration,D(t,concentration)*1e9),stroke='#38657A',width=.9)
    g.end()

    g.layer('property-state-paths','04 Saved state trajectories')
    for j in range(2):
        path=project(temperatures[:,j],moisture[:,j],D(temperatures[:,j],moisture[:,j])*1e9)
        g.polyline(path,stroke='#EAF2F1',width=3.3,dash=None if j==0 else '5 4')
        g.polyline(path,stroke=TEXT,width=1.5,dash=None if j==0 else '5 4')
        g.marker(path[-1],'circle',size=5.6,fill=WATER if j==0 else 'white',stroke=WATER)
        foot=project(temperatures[-1,j],moisture[-1,j],3)
        g.line(path[-1],foot,'#537684',.9,'3 4')
        g.marker(foot,'circle',size=4.2,fill=WATER if j==0 else 'white',stroke=WATER,width=1.3)
    start=project(28,2.55,D(28,2.55)*1e9)
    g.marker(start,'circle',size=4.8,fill=TEXT,width=1)
    g.end()

    g.layer('property-axes','05 Axes and guides')
    # Three visible axes. D uses a physical zero in labels but the projected floor is at 3.
    g.line(project(28,1,3),project(50,1,3),TEXT,1.2)
    g.line(project(28,1,3),project(28,2.55,3),TEXT,1.2)
    g.line(project(28,2.55,3),project(28,2.55,14),TEXT,1.2)
    for t in [30,40,50]:
        p=project(t,1,3)
        g.line(p,p+[-3,6],TEXT,1)
    for c in [1,1.5,2,2.55]:
        p=project(28,c,3)
        g.line(p,p+[-5,4],TEXT,1)
    for d in [4,8,12]:
        p=project(28,2.55,d)
        g.line(p,p+[-5,0],TEXT,1)
    # k(C) miniature: explicit scales, initial and 3 h states.
    kx=lambda c:680+(np.asarray(c)-1)/1.55*280
    ky=lambda k:255-(np.asarray(k)-.39)/.10*155
    for k in [.40,.44,.48]:
        g.line((680,ky(k)),(960,ky(k)),GRID,.7)
        g.line((675,ky(k)),(680,ky(k)),TEXT,1)
    g.line((680,95),(680,255),TEXT,1.1)
    g.line((680,255),(960,255),TEXT,1.1)
    for c in [1,1.5,2,2.55]:
        g.line((kx(c),255),(kx(c),260),TEXT,1)
    # Contribution panel has a common diverging scale and explicit signed axis.
    bx=lambda v:705+(np.asarray(v)+.30)/1.30*260
    for v in [-.3,0,.3,.6,.9]:
        g.line((bx(v),406),(bx(v),523),GRID,.8)
        g.line((bx(v),523),(bx(v),528),TEXT,1)
    g.line((bx(0),406),(bx(0),523),'#91A1A8',1.1)
    g.line((705,523),(965,523),TEXT,1.1)
    g.end()

    g.layer('property-conductivity','06 k constitutive response')
    g.polyline(np.stack((kx(concentration),ky(K(concentration))),axis=-1),WATER,2.9)
    for j in range(2):
        x=kx(moisture[-1,j]); y=ky(K(moisture[-1,j]))
        g.line((x,y),(x,255),'#8EADB9',1,'3 3')
        g.marker((x,y),'circle',size=5.8,fill=WATER if j==0 else 'white',stroke=WATER)
    g.marker((kx(2.55),ky(K(2.55))),'circle',size=4.8,fill=TEXT,width=1)
    g.end()

    g.layer('property-decomposition','07 Exact log decomposition')
    for j,y in enumerate([427,486]):
        g.rect(bx(0),y-10,bx(heat[j])-bx(0),20,HEAT)
        g.rect(bx(water[j]),y-10,bx(0)-bx(water[j]),20,WATER)
        g.rect(bx(water[j]),y-10,bx(0)-bx(water[j]),20,'url(#property-loss-hatch)')
        g.line((bx(net[j]),y-14),(bx(net[j]),y+14),'white',6)
        g.line((bx(net[j]),y-14),(bx(net[j]),y+14),TEXT,3.2)
    g.end()

    g.layer('property-legends','08 Symbols')
    g.marker((160,571),'circle',size=5.5,fill=WATER,stroke=WATER)
    g.marker((295,571),'circle',size=5.5,fill='white',stroke=WATER)
    g.marker((430,571),'circle',size=4.8,fill=TEXT,width=1)
    g.rect(664,373,18,11,HEAT)
    g.rect(760,373,18,11,WATER)
    g.rect(760,373,18,11,'url(#property-loss-hatch)')
    g.line((865,371),(865,387),TEXT,3.2)
    g.end()

    if not no_text:
        g.layer('property-labels','09 Editable labels')
        g.text(30,34,'(a)',weight='bold',size=19)
        g.text(67,34,'D(C, θ)',size=19)
        g.text(645,34,'(b)',weight='bold',size=19)
        g.text(682,34,'k(C)',size=19)
        g.text(645,345,'(c)',weight='bold',size=19)
        g.text(682,345,'3 h：ln(D/D₀)',size=19)
        g.text(36,82,'D / (10⁻⁹ m²/s)')
        for t in [30,40,50]:
            p=project(t,1,3)
            g.text(p[0]+2,p[1]+23,str(t),anchor='middle',size=17)
        for c in [1,1.5,2,2.55]:
            p=project(28,c,3)
            g.text(p[0]-15,p[1]+10,str(c),anchor='end',size=17)
        for d in [4,8,12]:
            p=project(28,2.55,d)
            g.text(p[0]-11,p[1]+5,str(d),anchor='end',size=17)
        g.text(440,475,'θ / °C',anchor='middle')
        g.text(109,486,'C / (kg/kg)',anchor='middle')
        g.text(87,310,'0 h',anchor='middle',size=17)
        g.text(174,577,'中心（3 h）',size=17)
        g.text(309,577,'表面（3 h）',size=17)
        g.text(444,577,'初始状态',size=17)
        g.text(680,73,'k / [W/(m·K)]')
        for k in [.40,.44,.48]:
            g.text(667,ky(k)+5,f'{k:.2f}',anchor='end',size=17)
        for c in [1,1.5,2,2.55]:
            g.text(kx(c),278,str(c),anchor='middle',size=17)
        g.text(820,303,'C / (kg/kg)',anchor='middle')
        g.text(689,385,'升温',size=17)
        g.text(785,385,'失水',size=17)
        g.text(878,385,'净变化',size=17)
        g.text(676,433,'中心',anchor='end',size=17)
        g.text(676,492,'表面',anchor='end',size=17)
        for v in [-.3,0,.3,.6,.9]:
            g.text(bx(v),550,'0' if v==0 else f'{v:.1f}'.replace('-','−'),anchor='middle',size=17)
        g.text(835,581,'ln(D/D₀) = 升温项 + 失水项',anchor='middle',size=16.8)
        g.end()
    g.add('</svg>')
    report={
        'source':SOURCE.relative_to(ROOT).as_posix(),
        'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'role':'Internal A0 visual trial only; no official brief or result modifications.',
        'width_mm':170,'height_mm':103.7,
        'formula':{'D':'2.4e-3 exp(-0.45/C-3850/(theta+273.15))', 'k':'0.21+0.38C/(1+C)',
                   'log_heat':'-3850[1/(theta+273.15)-1/(28+273.15)]',
                   'log_water':'-0.45[1/C-1/2.55]'},
        'source_formula':'Original problem Appendix 3; theta in Celsius, C in dry-basis kg/kg.',
        'surface_domain':{'theta_C':[28,50], 'C_kg_kg':[1,2.55], 'meaning':'Constitutive rectangle; not all pairs are states visited by the solution.'},
        'state_selection':'Existing centre/surface values at minute intervals from 0 through 10800 s. No PDE rerun.',
        'surface_mapping':'Exact orthographic projection of direct formula evaluation; no lighting, false geometry, normalization, or 3D k dependence.',
        'projection_floor_D_display':3,
        'path_mapping':'Solid centre; dashed surface; filled lake-blue circle marks the centre at 3h; open lake-blue circle marks the surface at 3h. Initial state is a filled deep-ink circle. Dotted lines project endpoint onto floor. Symbols match the companion drying-process trial.',
        'bar_mapping':'Positive heat term in coral; negative water term in hatched lake blue; black vertical ticks denote their algebraic sum. Common signed scale. Net marker differs from the filled/open circle spatial-location symbols.',
        'source_state_3h':{'temperature_C':temperatures[-1].tolist(),'moisture_kg_kg':moisture[-1].tolist()},
        'derived_3h':{'heat':heat.tolist(),'water':water.tolist(),'net':net.tolist(),'k':K(moisture[-1]).tolist()},
        'mathematical_audit':{'D_monotone_C':True,'D_monotone_theta':True,'k_monotone_C':True,'k_theta_derivative':0,'log_identity_max_error':float(np.max(abs(heat+water-net)))},
        'editable_structure':'Nine named SVG layers. Surface/floor geometry and axes separate from editable labels. Inkscape CLI exports all final rasters and PDF.',
    }
    return '\n'.join(g.parts),report


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    svg,metadata=build()
    stem=OUT/'property_editorial'
    stem.with_suffix('.svg').write_text(svg,encoding='utf-8')
    no_text,_=build(no_text=True)
    (OUT/'property_editorial_no_text.svg').write_text(no_text,encoding='utf-8')
    results=[]
    for input_path,out_path,dpi in [(stem.with_suffix('.svg'),stem.with_suffix('.png'),300),
                                    (stem.with_suffix('.svg'),stem.with_suffix('.pdf'),300),
                                    (OUT/'property_editorial_no_text.svg',OUT/'property_editorial_no_text.png',150)]:
        args=[sys.executable,str(ROOT/'scripts/graphics_tools.py'),'export',str(input_path),'-o',str(out_path),'--dpi',str(dpi),'--overwrite']
        proc=subprocess.run(args,check=True,capture_output=True,text=True,encoding='utf-8')
        results.append(json.loads(proc.stdout))
    with Image.open(stem.with_suffix('.png')) as im:
        ImageOps.grayscale(im).save(OUT/'property_editorial_grayscale.png')
        small=im.copy(); small.thumbnail((1000,1000)); small.save(OUT/'property_editorial_page_width.png')
    metadata['exports']=results
    metadata['generator_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (OUT/'property_editorial_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(stem)


if __name__=='__main__':
    main()
