"""Prepare the bibliography actually marked in the current teammate PDF.

Uncited but relevant project sources are kept in a separate advisory file.
Neither the teammate paper nor the locked AI report is modified.
"""
from pathlib import Path
import hashlib
import html
import json
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/paper_references'
INTERNAL = ROOT / 'planning/paper_used_references_20260913'
BUILD = INTERNAL / 'pdf_build'
PAPER = ROOT / '<未收录-队友材料>/药材烘干.pdf'
REFS = [
    dict(n=1, key='mujumdar2014drying', author='Mujumdar, Arun S.', editor=True,
         title='Handbook of Industrial Drying', edition='4', year='2014',
         place='Boca Raton', publisher='CRC Press',
         citation='MUJUMDAR A S, ed. Handbook of Industrial Drying[M]. 4th ed. Boca Raton: CRC Press, 2014.',
         keywords='工业干燥；热风干燥；干燥工艺', location='第2页\n问题背景',
         url='https://arunmujumdar.com/wp-content/uploads/2020/03/K20788_output_V2.pdf',
         anchor='改进烘干工艺很有帮助',
         audit='背景中的引用位置明确。可用作工业干燥及工艺研究的背景来源；本轮核对了出版信息与目录，未声称读完该书。作者网站所存出版宣传页标明 July 2014；出版社网页显示 Copyright 2015，两种日期口径不同，本表沿用已核对的2014年发行信息。'),
    dict(n=2, key='crank1975diffusion', author='Crank, John', editor=False,
         title='The Mathematics of Diffusion', edition='2', year='1975',
         place='Oxford', publisher='Clarendon Press',
         citation='CRANK J. The Mathematics of Diffusion[M]. 2nd ed. Oxford: Clarendon Press, 1975.',
         keywords='扩散方程；扩散过程；解析与数值方法', location='第3页\n问题一分析',
         url='https://biblio.neel.cnrs.fr/index.php?id=8642&lang_sel=fr_FR&lvl=notice_display',
         anchor='常用方法有解析法、有限差分法和有限体积法',
         audit='当前用于解析法、差分法和有限体积法的比较。现有项目记录不足以证明该书支持附近全部优劣判断；扩散理论可继续引用，有限体积的控制体与面通量依据宜补引 NIST 官方说明。'),
    dict(n=3, key='bergman2011heat',
         author='Bergman, Theodore L. and Lavine, Adrienne S. and Incropera, Frank P. and DeWitt, David P.', editor=False,
         title='Fundamentals of Heat and Mass Transfer', edition='7', year='2011',
         place='Hoboken', publisher='John Wiley & Sons',
         citation='BERGMAN T L, LAVINE A S, INCROPERA F P, et al. Fundamentals of Heat and Mass Transfer[M]. 7th ed. Hoboken: John Wiley & Sons, 2011.',
         keywords='非稳态导热；对流边界；传热传质', location='第3页\n问题一分析',
         url='https://bcs.wiley.com/he-bcs/Books?action=index&bcsId=6563&itemId=0470501979',
         anchor='向后差分隐式格式',
         audit='第7版作者顺序已按 Wiley 官方配套站更正：Bergman、Lavine、Incropera、DeWitt。当前将此书引在自适应向后差分算法之后，来源不够直接；宜移至传热理论或边界说明处，算法处引用实际积分器的官方资料。年份由作者所在大学的书目页交叉核对。'),
    dict(n=4, key='luikov1966porous', author='Luikov, A. V.', editor=False,
         title='Heat and Mass Transfer in Capillary-Porous Bodies', edition=None, year='1966',
         place='Oxford', publisher='Pergamon Press',
         citation='LUIKOV A V. Heat and Mass Transfer in Capillary-Porous Bodies[M]. Oxford: Pergamon Press, 1966.',
         keywords='毛细多孔介质；热量与水分迁移；传递理论', location='第3页\n问题二分析',
         url='https://shop.elsevier.com/books/heat-and-mass-transfer-in-capillary-porous-bodies/luikov/978-1-4832-0065-1',
         anchor='常用策略有显式求解、交替迭代和全隐式联合求解',
         audit='可支撑毛细多孔介质中热量和水分传递的理论背景。当前引文承载了显式、交替及联合求解的性能比较；本轮没有取得支持该整组比较的书中页码，不能据此宣称某种算法普遍更稳定或更高效。'),
    dict(n=5, key='geankoplis1993transport', author='Geankoplis, Christie J.', editor=False,
         title='Transport Processes and Unit Operations', edition='3', year='1993',
         place='Englewood Cliffs', publisher='PTR Prentice Hall',
         citation='GEANKOPLIS C J. Transport Processes and Unit Operations[M]. 3rd ed. Englewood Cliffs: PTR Prentice Hall, 1993.',
         keywords='传递过程；传热；传质；单元操作', location='第3页\n问题二分析',
         url='https://library.kaist.ac.kr/search/ctlgSearch/posesn/view.do?bibctrlno=129772&ty=B',
         anchor='这种联合求解方式与多孔介质传热传质模型',
         audit='当前用于说明联合求解与领域常见处理一致。书目存在且版次、年份可核对，但项目尚无可对应到该具体论断的章节或页码。建议将引文用于一般传递过程背景，联合算法的具体选择由本文方程依赖关系和实际数值方法说明。'),
]
SUPPLEMENT = [
    dict(key='nistfipy', citation='NATIONAL INSTITUTE OF STANDARDS AND TECHNOLOGY. Finite Volume Method: FiPy Documentation[EB/OL]. [2026-09-13].',
         keywords='有限体积；控制体积分；面通量；散度离散',
         url='https://pages.nist.gov/fipy/en/stable/numerical/discret.html',
         location='第9—10页圆环控制体与面通量；第26—27页收缩坐标离散。',
         reason='项目已有查阅记录，当前正文已有对应离散内容，宜在首次介绍控制体积分与通量差处补引。它支持离散思路，不代表本项目使用 FiPy 软件，也不支持“有限差分不能守恒”等绝对判断。'),
    dict(key='scipybdf', citation='SCIPY COMMUNITY. scipy.integrate.BDF: SciPy Reference Guide[EB/OL]. [2026-09-13].',
         keywords='隐式BDF；变阶；自适应步长；稀疏Jacobian',
         url='https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.BDF.html',
         location='第3页算法选择；第11页式（9）—（10）；第16页式（16）—（18）。',
         reason='项目实际阅读并使用相应求解器，适合替代现稿[3]对具体积分算法的支撑。官方说明涉及1—5阶变化、NDF修正、误差容差与Jacobian；正文算法表述仍须与实现相符，添加引文不能替代修正。'),
    dict(key='brasiello2021drying', citation='BRASIELLO A, VENDITTI C, ADROVER A. Non-Isothermal Moving-Boundary Model for Food Drying[J]. Chemical Engineering Transactions, 2021, 87: 193–198. DOI: 10.3303/CET2187033.',
         keywords='热风干燥；收缩；移动边界；材料运动',
         url='https://doi.org/10.3303/CET2187033',
         location='第23—25页Q4坐标变换与移动域方程；第30页关于收缩模型的讨论。',
         reason='由队友提供，项目已阅读正文并核对关键公式。它是本题收缩建模的领域参照，当前PDF尚未补引。引用时说明本题使用实测半径和干基含水率，不能把原文的体积含水浓度方程、收缩关系或材料参数直接移入。'),
]


def esc(s):
    return ''.join({'\\':r'\textbackslash{}','&':r'\&','%':r'\%','$':r'\$','#':r'\#','_':r'\_','{':r'\{','}':r'\}','~':r'\textasciitilde{}','^':r'\textasciicircum{}'}.get(c,c) for c in s)


def build():
    OUT.mkdir(parents=True, exist_ok=True); BUILD.mkdir(parents=True, exist_ok=True)
    before=hashlib.sha256(PAPER.read_bytes()).hexdigest()
    from pypdf import PdfReader
    pages=[p.extract_text() or '' for p in PdfReader(PAPER).pages]
    hits={}
    for ref in REFS:
        n=ref['n'];matches=[]
        for i,text in enumerate(pages[:-1],1):
            if f'[{n}]' in re.sub(r'\s+','',text):matches.append(i)
        assert matches == ([2] if n==1 else [3]), (n,matches)
        hits[n]=matches
    title='论文参考文献表 · 附关键词'
    note='依据《药材烘干.pdf》（2026年9月13日初稿，共31页）整理。以下五条均在现稿正文出现引用标记，编号与现稿一致。关键词为围绕本题整理的主题词，置于文献旁，便于队友查阅。'
    md=[f'# {title}','',note,'','| 编号 | 参考文献 | 关键词 | 现稿位置 |','|---|---|---|---|']
    for r in REFS:
        md += [f'| [{r["n"]}] | {r["citation"]} [书目核验]({r["url"]}) | {r["keywords"]} | {r["location"].replace(chr(10),"·")} |']
    foot='本表确认现稿的引用使用情况。引文与具体论断的对应问题，以及已有方法内容仍缺少的引用，见《引用位置核对与补引建议》；该说明中的候选文献未混入本表。第7版《Fundamentals of Heat and Mass Transfer》的作者顺序已按出版社信息核正。'
    md += ['',foot]
    (OUT/'论文参考文献表_附关键词.md').write_text('\n'.join(md),encoding='utf-8')
    style='body{font-family:"Microsoft YaHei",sans-serif;line-height:1.8;color:#26323b;background:#f2f4f6;margin:0}main{max-width:1100px;padding:35px 40px;margin:24px auto;background:white}h1{font-size:25px}h2{font-size:20px;margin-top:32px}p,td{font-size:14px}table{width:100%;border-collapse:collapse;table-layout:fixed}th,td{text-align:left;vertical-align:top;padding:13px 12px;border-bottom:1px solid #d7dfe3;overflow-wrap:anywhere}th{background:#eaf0f3}a{color:#315f7d}small{font-size:12px;color:#667078}@media print{body{background:white}main{padding:0;margin:0}tr{break-inside:avoid}}'
    rows=[]
    for r in REFS:
        rows.append(f'<tr><td>[{r["n"]}]</td><td>{html.escape(r["citation"])}<br><a href="{html.escape(r["url"],quote=True)}">书目核验</a></td><td>{r["keywords"]}</td><td>{r["location"].replace(chr(10),"<br>")}</td></tr>')
    web=f'<h1>{title}</h1><p>{note}</p><table><colgroup><col style="width:5%"><col style="width:59%"><col style="width:23%"><col style="width:13%"></colgroup><tr><th>编号</th><th>参考文献</th><th>关键词</th><th>现稿位置</th></tr>'+''.join(rows)+f'</table><p>{foot}</p><p><a href="引用位置核对与补引建议.html">查看引用核对与补引建议</a></p>'
    wrap=lambda body: '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>论文参考文献</title><style>'+style+'</style></head><body><main>'+body+'</main></body></html>'
    (OUT/'论文参考文献表_附关键词.html').write_text(wrap(web),encoding='utf-8')
    audit=['# 引用位置核对与补引建议','',
           '已引用与已充分支撑论断是两件事。当前PDF的[1]—[5]都能找到正文标记；本轮未把“有标记”当作已经核实了整段内容的来源。以下先核对现有用法，再列出三项最直接的补引建议。','',
           '## 现稿五条引文的对应情况','']
    ah=['<h1>引用位置核对与补引建议</h1><p>'+audit[2]+'</p><h2>现稿五条引文的对应情况</h2>']
    for r in REFS:
        audit += [f'**[{r["n"]}] {r["title"]}**', '',r['audit']+f' [核验来源]({r["url"]})','']
        ah += [f'<p><strong>[{r["n"]}] {html.escape(r["title"])}</strong><br>{r["audit"]} <a href="{html.escape(r["url"],quote=True)}">核验来源</a></p>']
    audit += ['## 当前正文已有相关方法、但尚未补引的三项来源','','这三项都有项目查阅或使用依据，并能对应现稿的具体方法内容。采用时须在相应正文位置补引后，再进入论文末尾参考文献表；这里不为它们预占正式编号。','','| 来源 | 关键词 | 建议补引位置与用途 |','|---|---|---|']
    ah += ['<h2>当前正文已有相关方法、但尚未补引的三项来源</h2><p>这三项都有项目查阅或使用依据，并能对应现稿的具体方法内容。采用时须在相应正文位置补引后，再进入论文末尾参考文献表；这里不为它们预占正式编号。</p><table><tr><th>来源</th><th>关键词</th><th>建议补引位置与用途</th></tr>']
    for r in SUPPLEMENT:
        audit += [f'| {r["citation"]} [原文]({r["url"]}) | {r["keywords"]} | {r["location"]} {r["reason"]} |']
        ah += [f'<tr><td>{r["citation"]}<br><a href="{r["url"]}">原文</a></td><td>{r["keywords"]}</td><td>{r["location"]} {r["reason"]}</td></tr>']
    ah += ['</table>']
    audit += ['','Q3“各处低于0.15”的判据和Q4题给半径、附录参数来自原题及附件，无须强行为它们寻找外部论文出处。当前稿未展示的PCHIP对照、Bessel解析核验等资料，以及内部外部答案复核材料，不列入这次文献表。']
    ah += [f'<p>{audit[-1]}</p>']
    (OUT/'引用位置核对与补引建议.md').write_text('\n'.join(audit),encoding='utf-8')
    (OUT/'引用位置核对与补引建议.html').write_text(wrap(''.join(ah)),encoding='utf-8')
    bib=[]
    for r in REFS:
        bib += [f'@book{{{r["key"]},',f'  {"editor" if r["editor"] else "author"} = {{{r["author"]}}},',f'  title = {{{r["title"]}}},',f'  year = {{{r["year"]}}},',f'  address = {{{r["place"]}}},',f'  publisher = {{{r["publisher"]}}},',f'  keywords = {{{r["keywords"]}}},']
        if r['edition']:bib += [f'  edition = {{{r["edition"]}}},']
        bib += ['}','']
    (OUT/'现稿已引用文献.bib').write_text('\n'.join(bib),encoding='utf-8')
    tx=[r'''\documentclass[UTF8,a4paper,11pt,fontset=windows]{ctexart}
\usepackage[left=21mm,right=21mm,top=23mm,bottom=23mm]{geometry}
\usepackage{array,booktabs,tabularx,xcolor,hyperref}
\hypersetup{colorlinks=true,urlcolor=black,pdftitle={论文参考文献表：附关键词},pdfauthor={}}
\setlength{\parindent}{0pt}\setlength{\parskip}{0.7em}
\renewcommand{\arraystretch}{1.45}
\begin{document}
\begin{center}{\Large\bfseries 论文参考文献表}\par{\normalsize 现稿已引用文献 · 关键词与正文位置}\end{center}
''',esc(note)+r'\par',r'\small',r'\begin{tabularx}{\textwidth}{@{}>{\raggedright\arraybackslash}X >{\raggedright\arraybackslash}p{30mm} >{\raggedright\arraybackslash}p{21mm}@{}}',r'\toprule 参考文献 & 关键词 & 现稿位置 \\ \midrule']
    for r in REFS:
        url = r['url'].replace('&', r'\&').replace('_', r'\_').replace('%', r'\%').replace('#', r'\#')
        tx += ['{}'+f'[{r["n"]}] '+esc(r['citation'])+r'\par\href{'+url+r'}{\footnotesize 书目核验}'+' & '+esc(r['keywords'])+' & '+esc(r['location']).replace('\n',r'\par ')+r'\\ \addlinespace[0.65em]']
    tx += [r'\bottomrule\end{tabularx}\par',r'\vspace{0.8em}',r'{\footnotesize '+esc(foot)+'}',r'\end{document}']
    tex=OUT/'论文参考文献表_附关键词.tex';tex.write_text('\n'.join(tx),encoding='utf-8')
    for i in range(2):
        proc=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error',f'-output-directory={BUILD}',str(tex)],capture_output=True,cwd=ROOT)
        (BUILD/f'compile_{i}.txt').write_bytes(proc.stdout+proc.stderr)
        if proc.returncode: raise RuntimeError('See compile log')
    (OUT/'论文参考文献表_附关键词.pdf').write_bytes((BUILD/'论文参考文献表_附关键词.pdf').read_bytes())
    names=['论文参考文献表_附关键词.pdf','论文参考文献表_附关键词.tex','论文参考文献表_附关键词.html','论文参考文献表_附关键词.md','现稿已引用文献.bib','引用位置核对与补引建议.md','引用位置核对与补引建议.html']
    with zipfile.ZipFile(OUT/'参考文献与关键词_交付.zip','w',zipfile.ZIP_DEFLATED) as z:
        for name in names:z.write(OUT/name,arcname='参考文献与关键词/'+name)
    after=hashlib.sha256(PAPER.read_bytes()).hexdigest();assert before==after
    result=dict(paper_sha256=before,paper_unchanged=True,explicit_citation_pages=hits,
                main_table_count=len(REFS),separate_uncited_suggestions_count=len(SUPPLEMENT),
                keyword_basis='Task-oriented subject keywords prepared by editor, not quoted author keywords',
                metadata_correction='Seventh-edition author order for Fundamentals of Heat and Mass Transfer',
                sources=REFS,supplement=SUPPLEMENT,rendered_pages=len(PdfReader(OUT/'论文参考文献表_附关键词.pdf').pages),
                pdf_visual_qa='pending',artifacts={n:hashlib.sha256((OUT/n).read_bytes()).hexdigest() for n in names})
    (INTERNAL/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('sources','supplement','artifacts')},ensure_ascii=False,indent=2))


if __name__=='__main__':build()
