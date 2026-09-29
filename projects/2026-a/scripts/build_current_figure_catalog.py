"""Build the current figure index directly from the four editable briefs.

This is a reading/figure-export build only. Historical producer bundles remain
unchanged. The zip contains selected graphics and captions, never audit records.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import subprocess
import tempfile
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/paper_figures/current'
IMAGE=re.compile(r'^!\[([^\]]+)\]\(([^\n]+)\)$',re.M)


def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def tex(text):
    text=text.replace('**','')
    chars={'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$',
        '#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}',
        '^':r'\textasciicircum{}','ξ':r'$\xi$','Δ':r'$\Delta$',
        '−':r'$-$','×':r'$\times$','⁶':r'$^{6}$','₀':r'$_0$',
        '²':r'$^2$','³':r'$^3$','⁻':r'$^-$','⁹':r'$^9$'}
    return ''.join(chars.get(c,c) for c in text)


def read_current():
    result=[]
    for q in range(1,5):
        brief=ROOT/f'docs/Q{q}/solution_brief.md'
        text=brief.read_text(encoding='utf-8-sig')
        for m in IMAGE.finditer(text):
            png=Path(m[2]);png=png if png.is_absolute() else (brief.parent/png).resolve()
            if not png.is_relative_to(ROOT): raise ValueError('Outside-project figure')
            after=text[m.end():].strip().split('\n\n',1)[0]
            number=re.search(r'图\d+-\d+',after)
            if not number: raise ValueError(f'No caption: {m[1]}')
            labels=re.findall(r'^### (.+)$',text[:m.start()],re.M)
            origin=png
            if png.parent.name=='reading' and png.name.startswith('fig03_q1_profiles_'):
                origin=ROOT/'output/paper_figures/v1/fig03_q1_profiles.png'
                if sha(origin)!=sha(png): raise ValueError('Q1 reading figure differs from producer')
            files={ext:origin.with_suffix('.'+ext) for ext in ['pdf','svg']}
            files['png']=png
            for p in files.values():
                if not p.exists(): raise FileNotFoundError(p)
            result.append({'q':q,'number':number[0],'caption':after.replace('**',''),
                'section':labels[-1],'brief':brief.relative_to(ROOT).as_posix(),
                'brief_sha256':sha(brief),
                'files':{ext:{'path':p.relative_to(ROOT).as_posix(),'sha256':sha(p)} for ext,p in files.items()}})
    numbers=[x['number'] for x in result]
    if len(numbers)!=len(set(numbers)): raise ValueError('Duplicate figure number')
    for q in range(1,5):
        got=[x['number'] for x in result if x['q']==q]
        if got!=[f'图{q}-{i+1}' for i in range(len(got))]: raise ValueError('Figure order/number mismatch')
    return result


def main():
    figs=read_current();OUT.mkdir(parents=True,exist_ok=True)
    md=['# 当前讲解稿选用图件','',
        '本目录直接依据四问讲解稿中的实际图片引用生成。旧版图仍留在原生产目录，取图请以本页为准。',
        '', '[A4预览册](figure_catalog.pdf) · [当前图件打包](论文图件_当前选用.zip)', '',
        '每幅均提供PDF、SVG和PNG。图号按问题内部编号；队伍合稿时统一连续编号。', '']
    latex=[r'\documentclass[UTF8,a4paper,10pt]{ctexart}',
        r'\usepackage[margin=2.5cm]{geometry}',r'\usepackage{graphicx}',
        r'\setmainfont{Times New Roman}',r'\setCJKmainfont{Microsoft YaHei}',
        r'\setlength{\parindent}{0pt}',r'\pagestyle{plain}',r'\begin{document}']
    packread=['# 当前论文图件','', '仅收录当前四问讲解稿引用的图件。PDF用于LaTeX；SVG可编辑，Word兼容性请在实际版本检查；PNG可直接插图。图号按问题内部编号，合稿时由队伍统一。', '']
    for index,f in enumerate(figs):
        label=f"问题{f['q']} · {f['section']}"
        md += [f"## {f['number']}　{label}",'',
            ' · '.join(f"[{ext.upper()}]({os.path.relpath(ROOT/info['path'],OUT).replace(chr(92),'/')})" for ext,info in f['files'].items()),
            '',f"![{f['number']}]({os.path.relpath(ROOT/f['files']['png']['path'],OUT).replace(chr(92),'/')})",'',f['caption'],'']
        pdfpath=(ROOT/f['files']['pdf']['path']).as_posix()
        latex += [r'{\large '+tex(label)+r'}\par\medskip',
            r'\includegraphics[width=15.8cm]{\detokenize{'+pdfpath+r'}}\par\medskip',
            r'{\small '+tex(f['caption'])+r'\par}',
            r'\vfill{\footnotesize 图形按15.8厘米宽展示；题注由讲解稿同步。}\par']
        if index<len(figs)-1: latex.append(r'\newpage')
        packread += [f"## {f['number']}",'',f['caption'],'']
    latex.append(r'\end{document}')
    (OUT/'index.md').write_text('\n'.join(md)+'\n',encoding='utf-8')
    (OUT/'figure_catalog.tex').write_text('\n'.join(latex)+'\n',encoding='utf-8')
    # Keep TeX logs/intermediates outside the current reading collection.
    build=Path(tempfile.gettempdir())/'cumcm-figure-refresh-20260911/catalog-build'
    build.mkdir(parents=True,exist_ok=True)
    for _ in range(2):
        proc=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error',
            '-output-directory='+str(build),str(OUT/'figure_catalog.tex')],
            cwd=ROOT,capture_output=True,timeout=90)
        if proc.returncode: raise RuntimeError(proc.stdout.decode('utf-8','replace')[-3000:])
    pdf=OUT/'figure_catalog.pdf';pdf.write_bytes((build/'figure_catalog.pdf').read_bytes())
    log=(build/'figure_catalog.log').read_text(encoding='utf-8',errors='replace')
    issues=[s for s in log.splitlines() if any(k in s for k in ['Missing character','Overfull','Undefined control','not found'])]
    if issues: raise RuntimeError('\n'.join(issues))
    archive=OUT/'论文图件_当前选用.zip'
    with ZipFile(archive,'w',ZIP_DEFLATED) as z:
        for f in figs:
            for ext,info in f['files'].items(): z.write(ROOT/info['path'],f"{f['number']}.{ext}")
        z.write(pdf,pdf.name);z.writestr('图件说明.md','\n'.join(packread)+'\n')
    manifest={'role':'Current brief-consumer index; working figure selection, not official submission',
        'selection_authority':'docs/Q1..Q4/solution_brief.md actual ordered image references',
        'generator':{'path':Path(__file__).relative_to(ROOT).as_posix(),'sha256':sha(__file__)},
        'figures':figs,'figure_count':len(figs),'catalog_pdf_sha256':sha(pdf),
        'archive_sha256':sha(archive),'historical_producer_statuses':'Preserved as records at their creation time; current use is established by this consumer manifest.'}
    (OUT/'figure_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'current_figures':len(figs),'catalog':pdf.relative_to(ROOT).as_posix(),'archive_MB':round(archive.stat().st_size/1024**2,2)},ensure_ascii=False))


if __name__=='__main__': main()
