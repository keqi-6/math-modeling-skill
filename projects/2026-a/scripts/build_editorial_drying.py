"""Internal drying-process figure: data layers + editable SVG composition.

Uses saved Q2 states only. The figure is not automatically selected for a brief.
"""
from pathlib import Path
from io import BytesIO
import base64
import hashlib
import json
import xml.etree.ElementTree as ET

import numpy as np
import contourpy
from PIL import Image
from matplotlib.colors import LinearSegmentedColormap

from graphics_tools import export_svg

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'output/Q2/run_n10240_startsafe.npz'
OUT = ROOT / 'planning/figure_redraw_trial_20260912'
SHA = '79f4b32f3a8858980b4649ed71ad2d3924b1c0312dc3de6260fea87866e9a59b'
INK = '#243A46'
MUTED = '#5F737E'
BLUE = '#237F99'
CORAL = '#C66A4B'
GOLD = '#AD792C'
SVGNS = 'http://www.w3.org/2000/svg'


def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def png_data(array):
    buf = BytesIO()
    Image.fromarray(array).save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


def gradient_stops(colors):
    return ''.join(f'<stop offset="{100*i/(len(colors)-1):g}%" stop-color="{c}"/>'
                   for i,c in enumerate(colors))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    assert digest(SOURCE) == SHA
    hours = np.array([0., .5, 1., 2., 3.])
    with np.load(SOURCE, allow_pickle=False) as data:
        snapshot_ids = [int(np.flatnonzero(data['snapshot_time_s'] == h*3600)[0]) for h in hours]
        radius = data['mesh_radius_m'].copy()
        moisture = data['moisture_snapshots'][snapshot_ids].copy()
        temperature = data['temperature_snapshots'][snapshot_ids].copy()
        time_ids = np.flatnonzero((data['time_s']<=10800)&(data['time_s']%30==0))
        time_h = data['time_s'][time_ids]/3600
        coarse_radius = data['radius_m']/radius[-1]
        sampled_temperature = data['temperature_C'][time_ids].copy()
    assert len(radius)==10241 and np.ptp(moisture[0])==0
    assert np.all(np.diff(moisture,axis=1)<=2e-10)
    mean_c = np.trapezoid(2*radius[None,:]*moisture, radius, axis=1)/radius[-1]**2
    delta = sampled_temperature-sampled_temperature[:,0,None]
    assert delta.min()>-1e-9 and delta.max()<3.5
    assert np.all(moisture[:,-1]<=mean_c+1e-10) and np.all(mean_c<=moisture[:,0]+1e-10)

    # All data fields have shared absolute scales. Smooth pixel evaluation uses
    # only linear spatial/time interpolation, not a new PDE solve or fitting.
    water_colors=['#F3F7F4','#D4E7DE','#8CC4C5','#439BAC','#246B8F','#173C5C']
    heat_colors=['#FFFAF0','#F5D5B1','#EBA77D','#D77B58','#A94942']
    water=LinearSegmentedColormap.from_list('water',water_colors)
    heat=LinearSegmentedColormap.from_list('heat',heat_colors)
    rr=np.linspace(-1,1,601);xx,yy=np.meshgrid(rr,rr);radial=np.hypot(xx,yy)
    blobs=[]
    for profile in moisture:
        values=np.interp(np.minimum(radial,1),radius/radius[-1],profile)
        rgba=(water(values/2.55)*255).astype('uint8')
        rgba[...,3]=np.where(radial<=1,255,0).astype('uint8')
        blobs.append(png_data(rgba))
    r_display=np.linspace(1,0,320)
    t_display=np.linspace(0,3,620)
    radial_interp=np.array([np.interp(r_display,coarse_radius,row) for row in delta])
    display_delta=np.array([np.interp(t_display,time_h,radial_interp[:,j]) for j in range(len(r_display))])
    heat_blob=png_data((heat(np.maximum(display_delta,0)/3.5)*255).astype('uint8'))

    labels=[]; guides=[]; plots=[]
    def text(x,y,value,size=21,anchor='start',fill=INK,weight='normal'):
        labels.append(f'<text x="{x:g}" y="{y:g}" font-size="{size:g}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}">{value}</text>')
    def line(x1,y1,x2,y2,color='#DCE5E8',width=1.1,dash=''):
        guides.append(f'<path d="M{x1:g} {y1:g}L{x2:g} {y2:g}" fill="none" stroke="{color}" stroke-width="{width:g}"'+(f' stroke-dasharray="{dash}"' if dash else '')+'/>')
    def circle(x,y,r,fill,stroke='none',width=1.8):
        plots.append(f'<circle cx="{x:g}" cy="{y:g}" r="{r:g}" fill="{fill}" stroke="{stroke}" stroke-width="{width:g}"/>')
    def diamond(x,y,r=5.5):
        plots.append(f'<path d="M{x:g} {y-r:g}L{x+r:g} {y:g}L{x:g} {y+r:g}L{x-r:g} {y:g}Z" fill="{GOLD}" stroke="white" stroke-width="1.2"/>')
    def panel(x,y,letter,title):
        text(x,y,f'({letter})',23,weight='bold')
        text(x+51,y,title,23,weight='bold')

    panel(32,34,'a','水分截面')
    centers=[127,351,575,799,1023]
    isoline_radii=[]
    for i,(x,h) in enumerate(zip(centers,hours)):
        text(x,76,f'{h:g} h',22,anchor='middle')
        plots.append(f'<image x="{x-84}" y="91" width="168" height="168" href="{blobs[i]}"/>')
        circle(x,175,84,'none','#3F6573',1.4)
        if moisture[i,-1]<2.0<moisture[i,0]:
            iso=float(np.interp(2.,moisture[i,::-1],radius[::-1]/radius[-1]))
            circle(x,175,84*iso,'none','#FDFDF9',1.6)
            isoline_radii.append(iso)
        else:
            isoline_radii.append(None)
    plots.append('<rect x="104" y="282" width="540" height="13" fill="url(#water-scale)"/>')
    for val in [0,.5,1,1.5,2,2.55]:
        x=104+540*val/2.55
        line(x,295,x,301,MUTED,1.2);text(x,324,f'{val:g}',18,anchor='middle',fill=MUTED)
    text(669,295,'C / (kg/kg)',21)
    circle(860,288,9,BLUE,'none')
    circle(860,288,6,'none','white',1.3)
    text(877,295,'C = 2.0',18,fill=MUTED)
    line(1001,290,1085,290,MUTED,2)
    line(1001,284,1001,296,MUTED,1.5);line(1085,284,1085,296,MUTED,1.5)
    text(1043,322,'2 cm',19,anchor='middle',fill=MUTED)
    line(32,349,1150,349,'#D6E0E3',1.3)

    panel(32,392,'b','径向温差')
    panel(667,392,'c','含水率的空间差异')
    text(81,429,'Δθ / °C',20)
    plots.append('<rect x="228" y="413" width="321" height="10" fill="url(#heat-scale)"/>')
    for val in [0,1,2,3.5]:
        x=228+321*val/3.5
        line(x,423,x,427,MUTED,1);text(x,447,f'{val:g}',17,anchor='middle',fill=MUTED)

    # Heat map positions preserve the actual time/radius coordinate mapping.
    hx,hy,hw,hh=82,473,467,224
    plots.append(f'<image x="{hx}" y="{hy}" width="{hw}" height="{hh}" href="{heat_blob}" preserveAspectRatio="none"/>')
    contours=contourpy.contour_generator(x=time_h,y=coarse_radius,z=delta.T)
    for level in [1.,2.,3.]:
        for segment in contours.lines(level):
            xy=np.column_stack((hx+hw*segment[:,0]/3,hy+hh*(1-segment[:,1])))
            path='M'+'L'.join(f'{x:.2f} {y:.2f}' for x,y in xy)
            plots.append(f'<path d="{path}" fill="none" stroke="#A95F42" stroke-opacity=".50" stroke-width="1.25"/>')
            k=int(np.argmin(segment[:,1])); lx,ly=xy[k]
            # A small label at each contour's radial minimum gives an exact
            # value without introducing a physical front interpretation.
            labels.append(f'<text x="{lx:.2f}" y="{ly+6:.2f}" text-anchor="middle" font-size="17" fill="#884D37" stroke="#FFFAF0" stroke-width="4" paint-order="stroke">{level:g}</text>')
    for val in [0,.5,1]:
        y=hy+hh*(1-val);line(hx-5,y,hx,y,MUTED,1)
        text(hx-14,y+6,f'{val:g}',19,anchor='end',fill=MUTED)
    text(36,455,'r/R',20)
    for val in [0,.5,1,1.5,2,2.5,3]:
        x=hx+hw*val/3;line(x,hy+hh,x,hy+hh+5,MUTED,1)
        text(x,hy+hh+28,f'{val:g}',19,anchor='middle',fill=MUTED)
    text(hx+hw,766,'t / h',21,anchor='end')
    line(hx,hy,hx,hy+hh,MUTED,1);line(hx,hy+hh,hx+hw,hy+hh,MUTED,1)

    # The data layer encodes center/surface as filled/open circles. The diamond
    # is the area mean 2/R² integral(C r dr), not an unlabelled bulk mass mean.
    circle(741,428,5.3,BLUE);text(756,435,'中心',18)
    circle(858,428,5.3,'white',BLUE,2);text(873,435,'表面',18)
    diamond(980,428);text(995,435,'面积平均',18)
    cx,cw=747,386
    c_min,c_max=.8,2.6
    position=lambda val:cx+cw*(val-c_min)/(c_max-c_min)
    for val in [.8,1,1.5,2,2.55]:
        x=position(val)
        line(x,468,x,697,'#E5EAEC',1)
        text(x,725,f'{val:g}',19,anchor='middle',fill=MUTED)
    line(cx,697,cx+cw,697,MUTED,1)
    for i,h in enumerate(hours):
        y=484+i*47
        text(cx-24,y+7,f'{h:g} h',20,anchor='end',fill=MUTED)
        x_s=position(moisture[i,-1])
        x_c=position(moisture[i,0])
        x_m=position(mean_c[i])
        plots.append(f'<path d="M{x_s:g} {y:g}H{x_c:g}" stroke="{BLUE}" stroke-opacity=".40" stroke-width="5" fill="none"/>')
        circle(x_s,y,6.5,'white',BLUE,2)
        circle(x_c,y,6.5,BLUE,'white',1.1)
        # Equal initial values share one compound marker, with a gold center.
        diamond(x_m,y,4.8)
    text(cx+cw,766,'C / (kg/kg)',21,anchor='end')

    svg=(f'<svg xmlns="{SVGNS}" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
         'width="170mm" height="112.625mm" viewBox="0 0 1200 795">'
         '<defs><linearGradient id="water-scale">'+gradient_stops(water_colors)+'</linearGradient>'
         '<linearGradient id="heat-scale">'+gradient_stops(heat_colors)+'</linearGradient></defs>'
         '<rect width="1200" height="795" fill="white"/>'
         '<g id="guides" inkscape:groupmode="layer" inkscape:label="坐标与参考线">'+''.join(guides)+'</g>'
         '<g id="data-fields" inkscape:groupmode="layer" inkscape:label="数据色场与标记">'+''.join(plots)+'</g>'
         '<g id="editable-labels" inkscape:groupmode="layer" inkscape:label="可编辑文字" '
         'font-family="Microsoft YaHei, sans-serif">'+''.join(labels)+'</g></svg>')
    stem=OUT/'drying_process'
    stem.with_suffix('.svg').write_text(svg,encoding='utf-8')
    records=[]
    for ext in ['png','pdf']:
        records.append(export_svg(stem.with_suffix('.svg'),stem.with_suffix('.'+ext),300,False,True))
    no_text=ET.fromstring(svg)
    for parent in no_text.iter():
        for child in list(parent):
            if child.tag==f'{{{SVGNS}}}text': parent.remove(child)
    no_text_file=OUT/'drying_process_no_text.svg'
    ET.ElementTree(no_text).write(no_text_file,encoding='utf-8',xml_declaration=True)
    records.append(export_svg(no_text_file,OUT/'drying_process_no_text.png',160,False,True))
    with Image.open(stem.with_suffix('.png')) as im:
        im.convert('L').save(OUT/'drying_process_grayscale.png')
        thumb=im.copy();thumb.thumbnail((1200,1200));thumb.save(OUT/'drying_process_page_width.png')
    np.savez_compressed(OUT/'drying_process_data.npz',time_h=hours,radius_m=radius,
                        moisture_kg_kg=moisture,temperature_C=temperature,area_mean_moisture=mean_c,
                        heatmap_time_h=time_h,heatmap_radius_ratio=coarse_radius,heatmap_delta_C=delta)
    metadata={'status':'internal candidate; not selected for briefs or official files',
              'data_driven_visual':True,'question':'How do moisture gradients persist while radial temperature differences subside?',
              'source':SOURCE.relative_to(ROOT).as_posix(),'source_sha256':SHA,
              'information_design':'Main row of moisture cross sections; complementary radial temperature-difference map and center/surface/area-mean range plot.',
              'time_h':hours.tolist(),'center_moisture':moisture[:,0].tolist(),'surface_moisture':moisture[:,-1].tolist(),
              'area_mean_moisture':mean_c.tolist(),'area_mean_definition':'2/R^2 integral_0^R C(r) r dr, trapezoid integration of all 10241 nodes',
              'circle_contour':'C=2.0 kg/kg when within the snapshot range; not a physical front',
              'contour_radius_ratio':isoline_radii,'temperature_difference_definition':'theta(r,t)-theta(0,t)',
              'heatmap_source_sampling':'21 stored requested radii, every 30 seconds through 3 h; bilinear display interpolation only',
              'disk_source_sampling':'10241 nodes at exact stored times; radial display interpolation only',
              'color_scales':{'C_kg_kg':[0,2.55],'delta_theta_C':[0,3.5]},
              'range_panel_axis':[c_min,c_max],
              'range_panel_axis_rationale':'Point positions and interval differences, not bars measured from zero; the displayed lower bound is explicitly ticked 0.8.',
              'thermal_contour_levels_C':[1,2,3],
              'target_size_mm':[170,112.625],'svg_structure':'Editable text, guides and markers; embedded numerical image fields.',
              'export_records':records,'generator_sha256':digest(Path(__file__)),
              'review':'Awaiting actual visual inspection; no publication-quality acceptance claim.'}
    (OUT/'drying_process_metadata.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(stem.with_suffix('.png'))


if __name__=='__main__':main()
