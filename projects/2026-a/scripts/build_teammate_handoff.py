"""Assemble portable teammate reading materials; never run model calculations."""
from __future__ import annotations
import base64
import hashlib
import html
import importlib.util
import json
import re
import shutil
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / '<未收录-队友交付包_20260913>'
STYLE = '''
*{box-sizing:border-box}body{margin:0;background:#f1f3f5;color:#23313a;font-family:"Microsoft YaHei",Arial,sans-serif;line-height:1.85}
main{max-width:1060px;margin:28px auto;padding:38px 46px;background:white;border:1px solid #dee5e9;border-radius:8px}
h1{font-size:27px;line-height:1.5}h2{font-size:21px;margin-top:32px;border-bottom:1px solid #dbe3e7;padding-bottom:8px}h3{font-size:17px}
a{color:#166181;text-underline-offset:3px;overflow-wrap:anywhere}p,li{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;font-size:14px}
td,th{text-align:left;padding:9px 12px;border-bottom:1px solid #dfe6ea;vertical-align:top}th{background:#f1f5f7}img{max-width:100%;height:auto}
pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f5f7f8;padding:15px;font:14px/1.75 Consolas,"Microsoft YaHei",monospace}
.sub{color:#61727e;font-size:14px}.cards{display:grid;grid-template-columns:1fr 1fr;gap:15px}.card{border:1px solid #dce5ea;padding:15px 20px;border-radius:6px}
.card h2{margin:0 0 8px;font-size:19px;border:0;padding:0}.card p{margin:5px 0}.tag{background:#e8f1f5;color:#1f5971;border-radius:3px;padding:3px 7px;font-size:13px}
.notice{border-left:4px solid #427d96;background:#f0f6f8;padding:10px 18px}input{width:100%;padding:12px;border:1px solid #aebfc8;border-radius:5px;font-size:16px}
nav{font-size:14px;background:#eff5f8;padding:12px 17px;margin-bottom:25px;border-radius:4px}details{margin:10px 0}.filelist li{margin:8px 0}
@media(max-width:700px){main{margin:0;padding:22px 19px;border:0}.cards{grid-template-columns:1fr}table{font-size:12px}td,th{padding:6px}}
@media print{main{margin:0;border:0;padding:0}nav,input,.no-print{display:none}h2,h3{break-after:avoid}tr,img{break-inside:avoid}}
'''

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def shell(title, body, depth=1):
    back = '<nav><a href="' + '../'*depth + '00_从这里开始.html">← 返回交付包入口</a></nav>' if depth else ''
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style></head><body><main>'+back+body+'</main></body></html>'

def inline(s):
    s=html.escape(s)
    s=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',s)
    s=re.sub(r'\*\*(.+?)\*\*',r'<strong>\1</strong>',s)
    s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    return s

def md_html(text):
    lines=text.splitlines();out=[];i=0
    while i<len(lines):
        s=lines[i].strip()
        if not s:i+=1;continue
        if s.startswith('```'):
            block=[];i+=1
            while i<len(lines) and not lines[i].strip().startswith('```'):block.append(lines[i]);i+=1
            out.append('<pre>'+html.escape('\n'.join(block))+'</pre>');i+=1;continue
        m=re.match(r'^(#{1,4})\s+(.*)',s)
        if m:out.append(f'<h{len(m[1])}>{inline(m[2])}</h{len(m[1])}>');i+=1;continue
        if s.startswith('|'):
            rows=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                cells=[x.strip() for x in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?',x) for x in cells):rows.append(cells)
                i+=1
            out.append('<table>'+''.join('<tr>'+''.join(f'<{"th" if j==0 else "td"}>{inline(c)}</{"th" if j==0 else "td"}>' for c in row)+'</tr>' for j,row in enumerate(rows))+'</table>');continue
        if re.match(r'^(?:[-*]|\d+\.)\s+',s):
            out.append('<ul>')
            while i<len(lines) and re.match(r'^(?:[-*]|\d+\.)\s+',lines[i].strip()):
                out.append('<li>'+inline(re.sub(r'^(?:[-*]|\d+\.)\s+','',lines[i].strip()))+'</li>');i+=1
            out.append('</ul>');continue
        part=[s];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(?:#|```|\||[-*]\s|\d+\.\s)',lines[i].strip()):part.append(lines[i].strip());i+=1
        out.append('<p>'+inline(' '.join(part))+'</p>')
    return '\n'.join(out)

def write_note(name, text):
    folder=PACK/'02_论文修改';folder.mkdir(parents=True,exist_ok=True)
    (folder/(name+'.md')).write_text(text,encoding='utf-8')
    (folder/(name+'.html')).write_text(shell(name,md_html(text)),encoding='utf-8')

def figures():
    out=PACK/'03_图件';out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'output/paper_figures/current/figure_manifest.json').read_text(encoding='utf-8'))
    mapping={};rows=[];body=['<h1>论文图件</h1><p>以下8幅与本包四问讲解稿逐一对应。PNG用于预览与Word插图；PDF用于LaTeX；SVG用于编辑。图号按小问编号，合稿时统一调整。</p>']
    for f in manifest['figures']:
        number=f['number'];prefix=number.replace('图','fig').replace('-','_')
        links=[]
        for ext,meta in f['files'].items():
            src=ROOT/meta['path'];dst=out/(prefix+'_'+src.name)
            if sha(src)!=meta['sha256']:raise ValueError(f'Stale figure identity: {src}')
            shutil.copy2(src,dst);mapping[str(src.resolve()).replace('\\','/')]=dst
            links.append(f'<a href="{html.escape(dst.name)}">{ext.upper()}</a>')
            if ext=='png':png=dst
        caption=f['caption'];body.append('<h2>'+html.escape(number+' · 问题'+str(f['q']))+'</h2><p>'+' · '.join(links)+'</p><img src="'+html.escape(png.name)+'" alt="'+html.escape(number)+'"><p>'+html.escape(caption)+'</p>')
        rows.append((number,caption,png.name))
    (out/'图件索引.html').write_text(shell('论文图件', '\n'.join(body)),encoding='utf-8')
    (out/'图注与使用说明.md').write_text('# 当前选用图件\n\n'+ '\n\n'.join('## '+n+'\n\n'+c+'\n\nPNG：'+p for n,c,p in rows),encoding='utf-8')
    return mapping

def briefs(mapping):
    spec=importlib.util.spec_from_file_location('brief_renderer',ROOT/'scripts/export_teammate_briefs.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    folder=PACK/'01_讲解稿';folder.mkdir(parents=True,exist_ok=True)
    sourcefolder=folder/'Markdown源稿';sourcefolder.mkdir(exist_ok=True)
    standalone=ROOT/'output/teammate_briefs';standalone.mkdir(exist_ok=True)
    metadata=[]
    for q in range(1,5):
        src=ROOT/f'docs/Q{q}/solution_brief.md'
        rendered,meta=module.render(src)
        anchors=[]
        def heading(m):
            n=len(anchors)+1;anchors.append((f'section-{n}',m[1]));return f'<h2 id="section-{n}">{m[1]}</h2>'
        portable=re.sub(r'<h2>(.*?)</h2>',heading,rendered)
        nav='<nav style="padding:12px 17px;background:#eff5f8;font-family:Microsoft YaHei,sans-serif;font-size:14px"><a href="../00_从这里开始.html">← 返回交付包入口</a><details><summary>本问目录</summary>'+''.join(f'<div><a href="#{a}">{t}</a></div>' for a,t in anchors)+'</details></nav>'
        portable=portable.replace('<body><main>','<body><main>'+nav)
        name=f'问题{q}_队友讲解稿.html';(folder/name).write_text(portable,encoding='utf-8')
        (standalone/name).write_text(rendered,encoding='utf-8')
        md=src.read_text(encoding='utf-8-sig')
        for original,dst in mapping.items():md=md.replace(original,'../../03_图件/'+dst.name)
        if re.search(r'!\[[^\]]*\]\([A-Za-z]:',md):raise ValueError('Nonportable image path in '+str(src))
        (sourcefolder/f'问题{q}_队友讲解稿.md').write_text(md,encoding='utf-8')
        meta.update(output=(standalone/name).relative_to(ROOT).as_posix(),output_sha256=sha(standalone/name),bytes=(standalone/name).stat().st_size);metadata.append(meta)
    with ZipFile(standalone/'队友讲解稿_四问.zip','w',ZIP_DEFLATED) as z:
        for q in range(1,5):z.write(standalone/f'问题{q}_队友讲解稿.html',f'问题{q}_队友讲解稿.html')
    (standalone/'build_manifest.json').write_text(json.dumps(dict(editable_source='docs/Q1..Q4/solution_brief.md',external_runtime_dependencies=False,files=metadata),ensure_ascii=False,indent=2),encoding='utf-8')

def notes():
    write_note('初稿修改清单', REVIEW)
    write_note('四问关系与关键结果', OVERVIEW)
    write_note('文末模型改进_蒸发耗热', LATENT)
    (PACK/'02_论文修改/关键公式与改进.tex').write_text(LATEX,encoding='utf-8')

def navigation():
    p=PACK
    ai=p/'06_AI报告';ai.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/'docs/<未收录-AI工具使用详情>.pdf',ai/'<未收录-AI工具使用详情>.')
    (ai/'说明.txt').write_text('本PDF采用队伍共同商讨并指定的完整版本，原样收录。\n未重排、补写或替换；不提供不属于此版本的旧LaTeX源稿。\n',encoding='utf-8')
    cards=[('01 阅读四问讲解','01_讲解稿/问题1_队友讲解稿.html','先读Q1的共同算法，再按Q2→Q3→Q4阅读新增关系。四份HTML均内嵌图件，单独复制也能阅读。'),('02 对照初稿修改','02_论文修改/初稿修改清单.html','按31页初稿页码定位公式、数值和解释问题；另有关键结果总览及可复制LaTeX片段。'),('03 找图与图注','03_图件/图件索引.html','8幅选用图件统一提供PNG、PDF和SVG；与讲解稿对应，不混入旧版候选图。'),('04 取结果或复算','04_计算与结果/阅读说明.html','四份result表、原始附件、计算与绘图代码、主轨迹及必要验证记录。'),('05 合并文献与附录','05_文献与附录/阅读说明.html','附录PDF、可编辑LaTeX、参考文献及每条来源的用途说明。'),('06 使用队伍AI报告','06_AI报告/<未收录-AI工具使用详情>.','队伍指定版本原样收录，供最终合稿和支撑材料整合。')]
    body=['<h1>药材烘干 · 队友交付包</h1><p class="sub">整理日期：2026年9月13日 · 先将整个压缩包解压，再打开本页</p><div class="notice">本包汇集我们的参考解法与计算材料，供队伍理解、核对和合稿。最终论文表述、取舍和提交由队伍决定。先读“初稿修改清单”，再按对应问题查完整讲解。</div><div class="cards">']
    for title,target,desc in cards:body.append(f'<section class="card"><h2><a href="{target}">{title}</a></h2><p>{desc}</p></section>')
    body.append('</div><h2>常用直达</h2><p>'+ ' · '.join(f'<a href="01_讲解稿/问题{q}_队友讲解稿.html">问题{q}</a>' for q in range(1,5))+' · <a href="02_论文修改/四问关系与关键结果.html">四问关系与关键结果</a> · <a href="02_论文修改/文末模型改进_蒸发耗热.html">文末潜热改进</a></p><p>'+ ' · '.join(f'<a href="04_计算与结果/results/result{q}.xlsx">result{q}.xlsx</a>' for q in range(1,5))+'</p>')
    body.append('<h2>怎样使用</h2><ol><li>读稿与取图无需配置运行环境。讲解稿仅提供HTML阅读版和Markdown源稿。</li><li>写正文时以各问讲解为依据，共同算法在Q1展开，后问引用并说明新增关系。四情境与其他辅助对照放在模型检验中。</li><li>02是合稿说明，04包含核算材料；整包供队伍使用，不直接作为组委会上传包。最终按实际采用的代码、图件和文献整理附录。</li><li>如需自行复算，先看04说明。未舍入主解用于直接查数，不必为了核对一格重新运行全部模型。</li></ol>')
    body.append('<h2>按名称查找文件</h2><input id="find" placeholder="输入：网格、问题4、result2、附录、潜热、代码……" aria-label="查找文件"><ul class="filelist" id="files">')
    for f in sorted(p.rglob('*')):
        if f.is_file() and f.name not in {'00_从这里开始.html','文件校验.sha256'} and f.suffix.lower() not in {'.aux','.log','.out'}:
            rel=f.relative_to(p).as_posix()
            keywords=[]
            if '/code/' in rel:keywords.extend(['代码','程序','复算'])
            if 'figure' in rel:keywords.append('绘图')
            if 'spacetime_grid' in rel:keywords.extend(['网格','时空'])
            if 'annular' in rel:keywords.extend(['网格','圆环'])
            body.append('<li data-keywords="'+html.escape(' '.join(keywords))+'"><a href="'+html.escape(rel)+'">'+html.escape(rel)+'</a></li>')
    body.append('</ul><script>document.getElementById("find").addEventListener("input",function(){let q=this.value.toLowerCase();document.querySelectorAll("#files li").forEach(x=>x.hidden=!(x.textContent+" "+x.dataset.keywords).toLowerCase().includes(q));});</script>')
    (p/'00_从这里开始.html').write_text(shell('药材烘干·队友交付包','\n'.join(body),0),encoding='utf-8')
    (p/'00_阅读说明.txt').write_text('请先解压整个压缩包，然后双击 00_从这里开始.html。\n\n01_讲解稿：四问HTML与Markdown源稿\n02_论文修改：本轮初稿勘误、关键结果、潜热改进与LaTeX片段\n03_图件：当前8幅选用图，PNG/PDF/SVG及图注\n04_计算与结果：正式结果、原始附件、程序、未舍入主解及必要核验\n05_文献与附录：新附录PDF、LaTeX、题录和引用用途\n06_AI报告：队伍锁定版PDF\n\n本包用于队伍理解与合稿，不直接上传整包。未包括工作环境、缓存、历史试算、外部个人解题答案或网上答案复核。\n',encoding='utf-8')

def finish():
    from PIL import Image
    from pypdf import PdfReader
    from xml.etree import ElementTree
    import ast
    failures=[]; links=0
    for f in PACK.rglob('*'):
        if not f.is_file():continue
        ext=f.suffix.lower()
        if ext=='.png':
            with Image.open(f) as im:im.verify()
        elif ext=='.pdf':
            if not len(PdfReader(f).pages):failures.append('Empty PDF: '+str(f))
        elif ext=='.svg':ElementTree.parse(f)
        elif ext=='.py':ast.parse(f.read_text(encoding='utf-8-sig'),filename=str(f))
        elif ext in {'.html','.md'}:
            t=f.read_text(encoding='utf-8-sig')
            if re.search(r'(?:file:///|[CD]:[/\\](?:Users|AI)[/\\])',t):failures.append('Local author path: '+str(f.relative_to(PACK)))
            # Equations inside fenced blocks are literal text, not Markdown links.
            link_text=re.sub(r'```[^\n]*\n[\s\S]*?```','',t) if ext=='.md' else t
            targets=re.findall(r'(?:href|src)="([^"]+)"',t) if ext=='.html' else re.findall(r'\]\(([^)]+)\)',link_text)
            for target in targets:
                if target.startswith(('http:','https:','data:','mailto:','#')):continue
                from urllib.parse import unquote
                target=unquote(html.unescape(target.split('#')[0]))
                if target and not (f.parent/target).exists():failures.append(f'Broken link: {f.relative_to(PACK)} -> {target}')
                links+=1
    for q in range(1,5):
        if sha(PACK/f'04_计算与结果/results/result{q}.xlsx')!=sha(ROOT/f'output/Q{q}/result{q}.xlsx'):failures.append(f'result{q} changed')
    if sha(PACK/'06_AI报告/<未收录-AI工具使用详情>.')!=sha(ROOT/'docs/<未收录-AI工具使用详情>.pdf'):failures.append('AI report changed')
    if failures:raise RuntimeError('\n'.join(failures))
    files=sorted(x for x in PACK.rglob('*') if x.is_file() and x.name!='文件校验.sha256')
    (PACK/'文件校验.sha256').write_text('\n'.join(sha(f)+'  '+f.relative_to(PACK).as_posix() for f in files)+'\n',encoding='utf-8')
    package=PACK.with_suffix('.zip')
    with ZipFile(package,'w',ZIP_DEFLATED,compresslevel=6) as z:
        for f in sorted(PACK.rglob('*')):
            if f.is_file():z.write(f,PACK.name+'/'+f.relative_to(PACK).as_posix())
    with ZipFile(package) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        for f in PACK.rglob('*'):
            if f.is_file() and hashlib.sha256(z.read(PACK.name+'/'+f.relative_to(PACK).as_posix())).hexdigest()!=sha(f):raise ValueError('ZIP differs: '+str(f))
    audit=dict(files=len(files)+1,local_links_checked=links,zip_bytes=package.stat().st_size,zip_sha256=sha(package),original_results_and_ai_unchanged=True,model_execution=False,files_validated=True)
    (ROOT/'planning/teammate_handoff_check_20260913.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False))

REVIEW = '''# 初稿修改清单

针对2026年9月13日收到的31页《药材烘干.pdf》。页码按该版本PDF；后续重排时按公式、表图号定位。本文件供合稿修改使用，解释与替换片段分别写明，不作为论文正文整体粘贴。

## 1 优先修正两处公式

第8页式（5）的表面换热符号应为：

```text
−k T_r(R,t)=h_T[T(R,t)−T∞(t)]。
```

第27页Step 4按第26页通量定义，表面节点应为：

```text
v_N s_N dΘ_N/dt=(H^T_{N+1/2}−H^T_{N−1/2})/R(t)^2；
v_N dU_N/dt=(H^U_{N+1/2}−H^U_{N−1/2})/R(t)^2。
```

原稿内侧面符号错误，且表面项漏除R²。当前程序采用正确形式；修稿不改变已有数值结果。可复制LaTeX见同目录“关键公式与改进.tex”。

## 2 同步旧版本数字与配置

| 位置 | 当前内容 | 修改为 |
|---|---|---|
| 第1页摘要 | 800秒和旧物性依赖描述 | 1800秒；ρ、cp、k依赖C，D依赖C和T |
| 第9、13页Q1 | 正式N=2560、5120仅参考 | 正式N=5120，5121节点，Δr=3.90625×10⁻⁶m |
| 第27页 | 83949秒 | 183949秒 |
| 第29页图8 | 57.44、25.24、129.83、51.09小时 | 57.48、25.25、129.86、51.10小时 |
| 第29页收缩比例 | 56.06% | 56.08% |
| 第30页物性比例 | 126.03% | 125.93% |

表10的四情境时长、−32.23/+72.38/−46.53小时及净缩短11.10%正确。比例从对应未舍入整数终点计算，避免再次混用图中旧数字。Q1的正式工作簿来自N=5120；不能因另一网格显示四位后接近，就把运行配置写成另一套。

## 3 网格检验只支持其实际比较对象

第13页表3以N=5120为参考时，温度最大差应依次为3.0733×10⁻⁵、7.7151×10⁻⁶、1.9078×10⁻⁶、5.2913×10⁻⁷、2.1916×10⁻⁷°C，对应N=160、320、640、1280、2560。含水率列与保存结果一致。

把“标准答案”改为“细网格参考解”。网格间差低于阈值是数值分辨证据，不直接等于已知连续真解误差，也不保证每个四位数的舍入均不变。第30页0.0619秒只对应Q4；Q3末级加密约0.64秒，整数结束秒相差1秒。各问分别注明即可，不必重复整个验证过程。

## 4 两处结果解释的方向

第12页图2后“温差已经缩小到3.2°C”与表1不符。改为：“到1800秒时，表面与中心仍存在约3.2°C的温差。”

第18页“问题二水分分布更不均匀”与表6的共同预热时段对照相反。同为1800秒时，Q1表里含水率差1.0398，Q2为0.9013。可改为：“在1800秒时，问题二的表面含水率较高、平均含水率略低，说明两组物性下的失水分布不同；其中心与表面的含水率差反而较小。”这里不是拿Q1的1800秒与Q2的3小时相比；Q2到3小时时的径向差为0.7581。

Q1本来已有D(C)，两问比较的是不同附录整组物性，不是仅把同一组参数从常数变成变量。“水分向内部传递”宜改为“失水影响向内部发展”。没有独立内部观测，不能据这一对照证明哪个模型更贴近实测。

## 5 保留物性分析，删除没有证据的敏感性排名

第19页图5表示主轨迹中k/k0、s/s0、D/D0如何变化，没有逐一扰动参数并重求输出。因此系数相对变化幅度不能直接用来比较温度或时长对它的敏感性。

建议节名用“物性变化及其作用分析”，删除“k影响相对较小”“D最敏感”的排名。保留实际发现：“升温有利于水分扩散，而含水率下降会抑制扩散；表面失水较快，因而后期中心的扩散系数可高于表面。”对应完整解释见Q2讲解第7.3节。

## 6 方法选择围绕本题困难展开

第3—4页不宜用没有比较证据的绝对评价排除有限差分、交替迭代或事件定位。隐式差分并不普遍精度低；连续事件定位也不要求状态突变，本项目恰好采用它定位最大含水率穿越阈值。

可用的选型理由：“有限体积法保留圆柱几何权重与共享面收支；隐式时间积分处理细网格扩散的刚性；联合迭代同步处理温度和含水率反馈；全节点事件定位确定阈值穿越，再核对首个严格达标整数秒。”

## 7 补足两段推导之间的关系

第14页从常物性推广时，s(C)T_t并不等于∂t[s(C)T]，后者多出T s′(C) C_t。应说明本模型采用题给物性的有效储热关系，再给出方程，不能只称“把守恒式中的常数换成变量”。干基含水率体积积分也不直接等于真实水质量。完整口径在Q2讲解第3、5节。

第25页应先写明：“采用均匀径向收缩近似，将前问的状态变化率改为随材料运动的变化率，再代入链式法则。”如此式（27）到（29）的运动项抵消才有依据。Q4讲解第5.2—5.4节提供完整推导。

## 8 四情境的结论统一

第30页前面已经正确区分整组物性影响，后面不再归结为“附录4始终减慢内部扩散”。建议落在：“同一物性下收缩缩短达标时长，同一几何条件下改用附录4整组物性延长达标时长；二者存在交互，最终净缩短约11.10%。”

表8目前只列0、0.5、1厘米和实际表面，符合原题；从6小时起1.5厘米已在材料之外，不要求额外添加全空列。工作簿中的固定位置域外格仍应留空。

## 9 文献与文末改进

第4页坐标变换的[?]需要修复。BDF的方法出处、领域热质传输与收缩研究分别按本包文献用途说明选取，不用一本教材代替所有来源，也不为凑数量加入没有使用的文献。

潜热改进目前没有进入初稿，只出现忽略假设和局限。可将同目录短改进段放在文末；它不属于已计算主模型，不附加到四问结果解释中。

## 10 亮点补充与阅读定位

优先补Q1的网格示意图及相邻的系数导数、边界收支说明，以此替换重复的算法步骤。Q1讲解第5.4—5.5节解释启动、初始不相容与隐式联立，Q2第5.3和5.6节解释链式导数与联合Jacobian，Q4第5.4节解释内部R⁻²与表面R⁻¹。这些已有内容无需重新发明模型。

讲解稿是完整参考，合稿按论文篇幅取舍。保留决定模型含义的推导、真实结果和关键证据，其余检验可以压缩为紧凑表格。
'''

OVERVIEW = '''# 四问关系与关键结果

## 阅读顺序

Q1说明共同几何、边界、有限体积与隐式迭代；Q2整组使用附录3，补足双向耦合；Q3沿用Q2方程，增加长期环境与全域停止；Q4整组使用附录4，在实测半径与均匀径向缩放假设下建立随体模型。每问都从题给均匀初态开始，不能把Q1的1800秒状态作为Q2零时刻。

| 问题 | 独有内容 | 正式结果范围 |
|---|---|---|
| Q1 | 附录2；热参数固定，D(C)非线性 | result1：1—1800秒，21个规定半径，两张表 |
| Q2 | 附录3；ρ(C)、cp(C)、k(C)、D(C,T) | result2：1—10800秒，21个规定半径，两张表 |
| Q3 | 附录3；4小时后末小时均值，全域阈值 | result3：每60秒及206927秒结束行 |
| Q4 | 附录4；实测R(t)，固定物理位置与实际表面 | result4：每60秒及183949秒结束行，域外格留空 |

## 核心结果

| 时刻/问题 | 中心温度/°C | 表面温度/°C | 中心含水率/(kg/kg) | 表面含水率/(kg/kg) |
|---|---:|---:|---:|---:|
| Q1，1800秒 | 33.5753 | 36.7856 | 2.5500 | 1.5102 |
| Q2，3小时 | 49.8495 | 49.9664 | 1.7662 | 1.0081 |

Q3首个严格达标整数秒206927秒，即57.4797小时；Q4为183949秒，即51.0969小时。临界穿越时刻分别约206926.138641秒、183948.743215秒；临界时刻最大含水率等于0.15，严格判断使用未舍入值。Q4比Q3短6.3828小时，约11.10%。两次主计算均由中心最后达标，但程序始终检查全部计算节点。

## 哪些解释可以承接

Q1表层先失水、内部仍接近初始值；Q2温度已接近均匀但含水率差仍明显；所以Q3不能只看表面或均温，必须采用全域含水率。Q4另区分外形缩小与内部干燥，半径接近稳定也不表示全域达标。

Q1、Q2预热对照改变的是整组物性；Q3、Q4直接对照同时改变几何与整组物性。对照结论按实际改动范围表述，不归给单个未经隔离的参数。

## 四情境辅助对照

| 情境 | 半径 | 物性 | 达标小时 |
|---|---|---|---:|
| A | 固定 | 附录3 | 57.48 |
| B | 收缩 | 附录3 | 25.25 |
| C | 固定 | 附录4 | 129.86 |
| D | 收缩 | 附录4 | 51.10 |

以A为基准，B−A约−32.23小时，C−A约+72.38小时，D−B−C+A约−46.53小时。作用存在交互，不能把两项单因素差简单相加代替总差。这组表属于Q4模型检验，B/C不替代result3或result4。

## 检验各有职责

Q1解释离散收支与启动，给解析参照和加密证据；Q2核对联合系数导数、四块Jacobian及变物性影响；Q3直接比较终点并检查长期环境延续；Q4核对运动、半径因子、制造解及四情境。重复算法只引用前文，新增条件及其证据在对应问题中说清。

## 取用说明

主表用04的results，图片用03，具体推导用01，论文修改定位用02。所有模型与计算供队伍理解、审核和写作参考，最终论文内容由队伍确认。文末潜热改进属于后续改进，不改变本包主模型数字。
'''

LATENT = '''# 文末模型改进：表面蒸发耗热

## 可用于模型改进部分的短段

主模型没有显式计入水分蒸发耗热。蒸发潜热是单位质量液态水转化为水蒸气所需的能量；若把相变近似集中于药材表面，可在表面热量平衡中增加蒸发耗热项，使空气供热同时用于内部升温和水分汽化：

```text
h(T∞−Ts)=k(C_s)·T_r|s + L_v(Ts)·j_w，
即 −k(C_s)·T_r|s=h(Ts−T∞)+L_v(Ts)·j_w。
```

其中L_v为水的气化潜热，单位J/kg水，可根据IAPWS饱和水与饱和水蒸气的比焓差L_v(Ts)=h_v^sat(Ts)−h_l^sat(Ts)确定。j_w是表面实际水质量通量，单位kg水/(m²·s)，可由样品称重得到的失水率与实际蒸发表面积标定。在相同状态下，蒸发消耗部分供热，可能降低表面温度；由于扩散系数随温度升高而增加，这一修正还会影响水分迁移。其对干燥时长的具体影响需在通量标定后联合求解，并与测温、称重数据比较。

## 公式使用说明

本题C是干基质量比。原模型的−D∂C/∂r或h_m(C_s−g)不能直接当作kg水/(m²·s)使用，更不能未经换算就乘潜热。均匀表面蒸发、总质量变化仅来自失水时，可用j_w=−(1/A_s) dm_w/dt；题目没有提供这一独立称重序列，不能写成已经完成标定。

Q4材料坐标中将T_r|s替换为Θ_ξ(1,t)/R(t)。表面汽化近似下不再同时添加一个重复的体积蒸发热源。纯水气化潜热也不自动等于结合水完整脱附热。

这段是未实施的模型改进，不写入Q1—Q4的已求解方程，不改变57.48与51.10小时的归属，也不声称已经提高预测精度。

## 参数与方法来源

- [IAPWS：Revised Supplementary Release on Saturation Properties of Ordinary Water Substance，1992](https://www.iapws.org/relguide/Supp-sat.html)：提供普通水饱和液相与气相比焓等性质，支持L_v取两相焓差。LaTeX引用键iapws1992saturation。
- [Nguyen等，2019，药用根片的热质传递研究](https://doi.org/10.1155/2019/2623404)：提供药材干燥中表面能量处理的领域参考；对象与本题不同，不移用其材料参数。引用键nguyen2019codonopsis。
'''

LATEX = r'''% 可复制的局部公式与文末改进片段；不是独立论文。
% 需在主文档中加载 amsmath；公式编号由合稿统一。

% Q1 表面换热：正径向指向外表面。
\begin{equation}
-k\left.\frac{\partial T}{\partial r}\right|_{r=R}
=h_T\bigl[T(R,t)-T_\infty(t)\bigr].
\end{equation}

% Q4 表面控制体；沿用第26页的H定义。
\begin{align}
v_Ns_N\frac{\mathrm d\Theta_N}{\mathrm dt}
&=\frac{H^T_{N+1/2}-H^T_{N-1/2}}{R(t)^2},\\
v_N\frac{\mathrm dU_N}{\mathrm dt}
&=\frac{H^U_{N+1/2}-H^U_{N-1/2}}{R(t)^2}.
\end{align}

% 变物性储热口径。
本模型以题给物性构造局部有效储热关系，温度变化率项取
$s(C)\partial T/\partial t$，其中$s(C)=\rho(C)c_p(C)$。
该项不改写为$\partial[s(C)T]/\partial t$；后者还包含
$Ts'(C)\partial C/\partial t$，对应另一种储热关系。

% 从固定域向随体模型扩展的桥接。
在均匀径向收缩近似下，材料速度为$v_s=rR'(t)/R(t)$。
将状态变化率取为随材料运动的变化率，再令$\xi=r/R(t)$，可得
\begin{equation}
\frac{\partial C}{\partial t}+v_s\frac{\partial C}{\partial r}
=\frac{\partial U}{\partial t}\bigg|_\xi.
\end{equation}
温度同理。由此将移动区域转换到固定材料区间，运动贡献已包含在时间导数中。

% 文末模型改进：按需保留，主模型尚未实施这一修正。
\paragraph{考虑表面蒸发耗热}
蒸发潜热是单位质量液态水转化为水蒸气所需的能量。
若将相变近似集中于药材表面，可将表面热量平衡改为
\begin{equation}
h_T(T_\infty-T_s)
=k(C_s)\left.\frac{\partial T}{\partial r}\right|_s
+L_v(T_s)j_w.
\end{equation}
其中$L_v(T_s)$单位为$\mathrm{J/kg}$水，可由IAPWS饱和两相比焓差
$L_v=h_v^{\mathrm{sat}}-h_l^{\mathrm{sat}}$确定\cite{iapws1992saturation}；
$j_w$为实际水质量通量，单位为$\mathrm{kg/(m^2\,s)}$。
均匀表面蒸发且总质量变化仅来自失水时，可结合称重数据和实际蒸发表面积
按$j_w=-A_s^{-1}\mathrm{d}m_w/\mathrm{d}t$标定。
原模型中的$C$为干基含水率，$-D\partial C/\partial r$不能直接作为该质量通量。
在相同状态下，蒸发消耗部分供热，可能降低表面温度，并通过温度相关扩散系数影响失水。
其对干燥时长的具体影响需在通量标定后联合求解及实验验证。
'''

if __name__=='__main__':
    import argparse
    a=argparse.ArgumentParser();a.add_argument('--finish',action='store_true');args=a.parse_args()
    PACK.mkdir(parents=True,exist_ok=True)
    if not args.finish:
        maps=figures();briefs(maps);notes();print('Reading copies and figures assembled.')
    else:navigation();finish()
