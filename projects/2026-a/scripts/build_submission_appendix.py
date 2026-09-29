"""Assemble the appendix preview from the explicit support-material selection.

This local authoring utility does not run the numerical model or upload files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "output/submission_appendix"
SUPPORT = DEST / "support"
ASSEMBLY = DEST / "assembly"
TEAM_AI_REPORT = ROOT / "docs/<未收录-AI工具使用详情>.pdf"


def tex_escape(value: str) -> str:
    return value.translate(str.maketrans({
        "\\": r"\textbackslash{}", "_": r"\_", "%": r"\%",
        "&": r"\&", "#": r"\#", "{": r"\{", "}": r"\}",
    }))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sync_team_ai_report() -> None:
    """Integrate the team-selected PDF byte for byte; never regenerate it."""
    if not TEAM_AI_REPORT.is_file():
        raise FileNotFoundError(TEAM_AI_REPORT)
    target = SUPPORT / "<未收录-AI工具使用详情>."
    if not target.is_file() or digest(target) != digest(TEAM_AI_REPORT):
        shutil.copyfile(TEAM_AI_REPORT, target)
    assert target.read_bytes() == TEAM_AI_REPORT.read_bytes()


CODE_SECTIONS = [
    ("运行入口", "run_models.py", "选择问题、设置网格与容差，并限制单次计算时间。问题二与问题三复用同一条耦合计算轨迹，分别导出前三小时与完整干燥过程。"),
    ("数据接口与公共参数", "common.py", "读取题给环境与半径观测，构造分段插值和长期环境延续接口。"),
    ("问题一：预热阶段的径向传热传质", "q1_model.py", "给出节点控制体、通量、解析Jacobian及分段隐式积分的完整实现。"),
    ("问题二、三：局部变物性耦合计算", "q23_model.py", "给出题给附录3物性、热质耦合方程及全域含水率达标判据。"),
    ("问题四：收缩域的热质耦合计算", "q4_model.py", "在材料坐标上处理实测半径收缩，按题给附录4计算物性，并区分固定物理位置与实际表面。"),
    ("结果工作簿导出", "export_results.py", "按题给模板写入规定时空点的四位小数结果；域外位置保留空白。"),
]
FIGURE_SECTIONS = {
    "extract_figure_data.py": ("绘图数值样本提取", "读取已有计算结果，提取图件所需的数值数组及元数据。"),
    "redraw_figures.py": ("数据图绘制入口", "统一选择绘图对象、输入数据、字体与输出目录。"),
    "figure_core.py": ("问题一径向剖面图", "绘制五个时刻的温度与含水率径向分布。"),
    "figure_restructured.py": ("空间离散、扩散系数分解与达标进程图", "构造圆环控制体示意；从主解状态分解扩散系数变化，并提取各规定半径的达标进程。"),
    "figure_fields.py": ("问题二时空分布图", "读取前三小时的温度与含水率场，绘制对应时空分布。"),
    "figure_coordinates.py": ("实测收缩与材料坐标图", "结合半径观测说明固定物理位置与材料坐标之间的关系。"),
    "figure_sections.py": ("问题四含水率截面图", "将六个时刻的完整径向含水率快照映射到同一厘米尺度下的圆截面。"),
}


def write_sources() -> None:
    ASSEMBLY.mkdir(parents=True, exist_ok=True)
    for _, file, _ in CODE_SECTIONS:
        if not (SUPPORT / "code" / file).is_file():
            raise FileNotFoundError(SUPPORT / "code" / file)
    rows = [
        ("code/run_models.py", "问题选择、参数设置与限时运行入口"),
        ("code/common.py", "原始观测读取、环境与半径插值"),
        ("code/q1_model.py", "问题一径向有限体积计算"),
        ("code/q23_model.py", "问题二、三的局部变物性耦合计算"),
        ("code/q4_model.py", "问题四收缩域耦合计算"),
        ("code/export_results.py", "四份结果工作簿导出"),
        ("code/requirements.txt", "公开软件依赖及版本"),
        ("data/", "题给原始观测与结果模板"),
        ("results/result1.xlsx", "问题一：1秒间隔、前30分钟"),
        ("results/result2.xlsx", "问题二：1秒间隔、前三小时"),
        ("results/result3.xlsx", "问题三：1分钟间隔与完整干燥终点"),
        ("results/result4.xlsx", "问题四：收缩过程、固定位置与实际表面"),
        ("figures/", "当前选用图件的矢量版本与图注索引"),
        ("figure_data/", "用于重绘的数值样本和说明"),
        ("references/", "参考文献题录与检索标识"),
        ("<未收录-AI工具使用详情>.", "AI使用范围与人工修订说明"),
        ("README.md", "环境配置、运行方法与文件说明"),
    ]
    extra = sorted(p for p in (SUPPORT / "code").rglob("*")
                   if p.is_file() and p.suffix in {".py", ".js", ".cjs", ".mjs", ".html"}
                   and p.name not in {x[1] for x in CODE_SECTIONS}
                   and "vendor" not in p.parts)
    descriptions = dict(rows)
    figures = json.loads((SUPPORT / "figures/figure_manifest.json").read_text(encoding="utf-8"))["figures"]
    for fig in figures:
        for fmt, info in fig["files"].items():
            descriptions["figures/" + info["file"]] = fig["number"] + "，" + fmt.upper() + "图件"
    for p in extra:
        descriptions[p.relative_to(SUPPORT).as_posix()] = FIGURE_SECTIONS.get(p.name, ("图件数据准备或绘制", ""))[0]
    def description(path):
        key = path.relative_to(SUPPORT).as_posix()
        if key in descriptions:
            return descriptions[key]
        if key.startswith("data/templates/"):
            return "题给" + path.stem + "输出模板"
        if key == "data/附件1.xlsx":
            return "题给环境温度与水分浓度观测"
        if key == "data/附件2.xlsx":
            return "题给半径收缩观测"
        if key.startswith("figure_data/"):
            return "绘图数值样本及其来源、单位说明"
        if key.endswith("LICENSE"):
            return "第三方绘图库许可文本"
        if "three." in path.name:
            return "Three.js三维绘图库依赖"
        if key.endswith("cutaway_scene.html"):
            return "三维场景的几何、颜色及交互"
        if key.endswith("cutaway_data.json"):
            return "剖切场景使用的径向含水率数据"
        if path.name == "figure_manifest.json":
            return "图号、题注、文件对应关系"
        if path.name == "requirements_figures.txt":
            return "绘图软件依赖及版本"
        if key.startswith("references/"):
            return "参考文献题录与检索标识"
        if path.name == "README.md":
            return "图件编辑与重绘说明"
        raise ValueError("Missing file-list description: " + key)
    listed = sorted(p for p in SUPPORT.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    rows = [(p.relative_to(SUPPORT).as_posix(), description(p)) for p in listed]
    def table_path(name):
        return tex_escape(name) if re.search(r"[\u4e00-\u9fff]", name) else rf"\path{{{name}}}"

    def table(title, label, header, widths, body):
        fmt = "@{}" + "".join(rf"p{{{w}\linewidth}}" for w in widths) + "@{}"
        head = " & ".join(r"\heiti " + h for h in header) + r" \\"
        return [r"\Needspace{6\baselineskip}",
                r"{\linespread{1}\fontsize{10.5}{15}\selectfont\renewcommand{\arraystretch}{1.05}",
                rf"\begin{{longtable}}{{{fmt}}}",
                rf"\caption{{{title}}}\label{{{label}}}\\",
                r"\toprule[0.9pt]", head, r"\midrule[0.55pt]\endfirsthead",
                rf"\multicolumn{{{len(header)}}}{{c}}{{表\thetable\quad {title}（续）}}\\[4pt]",
                r"\toprule[0.9pt]", head, r"\midrule[0.55pt]\endhead",
                r"\bottomrule[0.9pt]\endfoot", *body, r"\end{longtable}}"]

    out = [r"\section*{附录 A\quad 文件清单}",
           "支撑材料中的程序、数据、图件与说明文件分别列于下表。除已注明的公共目录外，路径均相对于支撑材料根目录。"]
    code_rows = [(name.removeprefix("code/"), desc) for name, desc in rows if name.startswith("code/")]
    out += table("程序文件（公共目录：code/）", "tab:appendix-files", ["文件名", "功能说明"], ["0.52", "0.44"],
                 [rf"{table_path(name)} & {desc} \\" for name, desc in code_rows])
    data_rows = [(name, desc) for name, desc in rows if name.split('/')[0] in {"data", "figure_data", "results"}]
    out += table("输入数据、绘图数据与计算结果", "tab:appendix-data", ["文件名", "内容"], ["0.58", "0.38"],
                 [rf"{table_path(name)} & {desc} \\" for name, desc in data_rows])

    figure_body, grouped_files = [], set()
    for fig in figures:
        stems = {}
        for extension, item in fig["files"].items():
            name = item["file"]
            stems.setdefault(Path(name).stem, []).append(extension)
            grouped_files.add("figures/" + name)
        for stem, extensions in stems.items():
            formats = " / ".join(extensions)
            figure_body.append(rf"{table_path(stem)} & {formats} & {fig['number']} \\")
    out += ["图件均位于\\texttt{figures/}，完整文件名由表中基名加对应扩展名构成。"]
    out += table("论文图件文件", "tab:appendix-figures", ["文件基名", "扩展名", "对应图号"], ["0.57", "0.20", "0.15"], figure_body)
    others = [(name, desc) for name, desc in rows if name.split('/')[0] not in {"code", "data", "figure_data", "results"} and name not in grouped_files]
    out += table("参考文献与说明文件", "tab:appendix-other", ["文件名", "用途"], ["0.58", "0.38"],
                 [rf"{table_path(name)} & {desc} \\" for name, desc in others])
    expanded = {"code/" + name for name, _ in code_rows} | {name for name, _ in data_rows} | grouped_files | {name for name, _ in others}
    assert expanded == {name for name, _ in rows}
    out += [r"\clearpage", r"\section*{附录 B\quad 完整程序}",
            "以下按逐问模型、公共模块和绘图程序列出源代码。题给附录3、4分别指原题提供的物性关系。版面中的长行自动续排，行号仍按原始源程序计数。"]
    sections = [CODE_SECTIONS[i] for i in (2, 3, 4, 1, 0, 5)]
    for p in extra:
        title, desc = FIGURE_SECTIONS.get(p.name, ("图件数据与绘制：" + tex_escape(p.stem), "程序读取随附数据绘制对应图件。"))
        sections.append((title, p.relative_to(SUPPORT / "code").as_posix(), desc))
    for idx, (title, file, desc) in enumerate(sections, 1):
        out.append(r"\Needspace{10\baselineskip}")
        out += [rf"\subsection*{{B.{idx}\quad {title}}}", desc,
                rf"\AppendixListing{{{idx}}}{{{tex_escape('code/' + file)}}}{{../support/code/{file}}}{{Python}}"]
    scene = SUPPORT / "figures/scene/cutaway_scene.html"
    if scene.is_file():
        out += [r"\Needspace{8\baselineskip}", rf"\subsection*{{B.{len(sections)+1}\quad 三维剖切场景}}",
                "以下为自编场景代码，使用随附的Three.js模块。径向含水率数据从相邻JSON文件读取；第三方库依赖由原许可文本标识。",
                rf"\AppendixListing[12.5]{{{len(sections)+1}}}{{figures/scene/cutaway\_scene.html}}{{../support/figures/scene/cutaway_scene.html}}{{HTML}}"]
    (ASSEMBLY / "appendix.tex").write_text("\n\n".join(out) + "\n", encoding="utf-8")


def copy_results() -> None:
    target = SUPPORT / "results"
    target.mkdir(parents=True, exist_ok=True)
    for q in range(1, 5):
        source = ROOT / f"output/Q{q}/result{q}.xlsx"
        dest = target / source.name
        shutil.copyfile(source, dest)
        assert digest(source) == digest(dest)


def compile_preview() -> None:
    engine = shutil.which("xelatex")
    if not engine:
        raise RuntimeError("XeLaTeX is required for the appendix preview")
    for entry, output in [("main", "附录_合稿预览.pdf"), ("appendix_standalone", "附录.pdf")]:
        with tempfile.TemporaryDirectory(prefix="cumcm-appendix-tex-") as tmp:
            for _ in range(2):
                p = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error",
                                    "-output-directory=" + tmp, entry + ".tex"],
                                   cwd=ASSEMBLY, capture_output=True, timeout=180)
                log = (Path(tmp) / (entry + ".log")).read_text(encoding="utf-8", errors="replace")
                if p.returncode:
                    raise RuntimeError(log[-10000:])
            issues = [line for line in log.splitlines() if any(x in line for x in
                      ("Missing character:", "Overfull ", "undefined", "LaTeX Warning:"))]
            if issues:
                print("Layout/source notices:", "\n".join(issues))
            shutil.copyfile(Path(tmp) / (entry + ".pdf"), DEST / output)
            print("Preview:", DEST / output)


def archives(winrar: Path | None = None) -> None:
    sync_team_ai_report()
    allowed_roots = {"code", "data", "results", "figures", "figure_data", "references"}
    allowed_root_files = {"README.md", "<未收录-AI工具使用详情>."}
    forbidden_parts = {"__pycache__", ".venv", ".git", "_validation", "planning", "internal_reviews"}
    files = []
    for path in sorted(SUPPORT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(SUPPORT)
        if set(rel.parts) & forbidden_parts or path.suffix in {".pyc", ".log", ".aux"}:
            raise ValueError(f"Unwanted support file: {rel}")
        if (len(rel.parts) == 1 and path.name not in allowed_root_files) or (len(rel.parts) > 1 and rel.parts[0] not in allowed_roots):
            raise ValueError(f"Not on support whitelist: {rel}")
        files.append(path)
    required = [SUPPORT / "<未收录-AI工具使用详情>."] + [SUPPORT / f"results/result{q}.xlsx" for q in range(1, 5)]
    for path in required:
        if path not in files:
            raise FileNotFoundError(path)
    archive = DEST / "支撑材料_待合稿确认.zip"
    if winrar is not None:
        if not winrar.is_file():
            raise FileNotFoundError(winrar)
        with tempfile.TemporaryDirectory(prefix="cumcm-support-archive-") as tmp:
            trial = Path(tmp) / "support.zip"
            listing = Path(tmp) / "files.txt"
            listing.write_text("\n".join(str(p.relative_to(SUPPORT)) for p in files), encoding="utf-16")
            command = [str(winrar), "a", "-afzip", "-m5", "-idq", "-ibck", "-y", "-r-", "-scul", str(trial), "@" + str(listing)]
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
            subprocess.run(command, cwd=SUPPORT, check=True, timeout=120,
                           startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            shutil.copyfile(trial, archive)
    else:
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for path in files:
                z.write(path, path.relative_to(SUPPORT).as_posix())
    if archive.stat().st_size > 20_000_000:
        raise ValueError("Support archive exceeds the conservative 20,000,000-byte limit")
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert sorted(z.namelist()) == sorted(p.relative_to(SUPPORT).as_posix() for p in files)
        for p in files:
            assert hashlib.sha256(z.read(p.relative_to(SUPPORT).as_posix())).hexdigest() == digest(p)
    info = {"status": "prepared_for_team_final_assembly_review",
            "archive": archive.name, "archive_bytes": archive.stat().st_size,
            "archive_sha256": digest(archive),
            "archive_software": "WinRAR" if winrar is not None else "Python zipfile (review copy)",
            "files": [{"path": p.relative_to(SUPPORT).as_posix(), "bytes": p.stat().st_size,
                       "sha256": digest(p)} for p in files]}
    (DEST / "support_manifest.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    assembly_archive(files)
    print(json.dumps({"support_files": len(files), "support_bytes": archive.stat().st_size,
                      "support_sha256": digest(archive)}, ensure_ascii=False))


def assembly_archive(files=None) -> None:
    sync_team_ai_report()
    files = files or sorted(p for p in SUPPORT.rglob("*") if p.is_file())
    with zipfile.ZipFile(DEST / "附录与合稿素材.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for p in sorted(ASSEMBLY.rglob("*")):
            if p.is_file() and p.suffix in {".tex", ".bib", ".md"} and p.name != "ai_usage_details.tex":
                z.write(p, "assembly/" + p.relative_to(ASSEMBLY).as_posix())
        for p in files:
            z.write(p, "support/" + p.relative_to(SUPPORT).as_posix())
        for name in ("附录.pdf", "附录_合稿预览.pdf", "README.md"):
            p = DEST / name
            z.write(p, p.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["sources", "compile", "archives", "assembly", "all"])
    parser.add_argument("--winrar", type=Path, help="Path to WinRAR.exe for the competition support ZIP")
    args = parser.parse_args()
    if args.mode in {"sources", "all"}:
        write_sources()
    if args.mode == "assembly":
        assembly_archive()
    if args.mode in {"compile", "all"}:
        compile_preview()
    if args.mode in {"archives", "all"}:
        archives(args.winrar)


if __name__ == "__main__":
    main()
