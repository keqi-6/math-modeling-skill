"""Build portable reading copies of the four canonical Markdown briefs.

The Markdown files remain the editable source. Before export, Q1's figure-1-3
reference and its README image entry are refreshed to a byte-identical image
whose filename contains its content hash. This prevents an older same-path
preview from masking a changed figure. Scientific prose is not rewritten.
The renderer rejects local document links, so a reading copy never silently
depends on the author's project directory. It does not run model code.
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import mimetypes
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "teammate_briefs"
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^\n]+)\)")
LINK = re.compile(r"\[([^\]]+)\]\(([^\n]+?)\)")
CSS = """
:root { color-scheme: light; }
* { box-sizing: border-box; }
body { margin: 0; background: #edf1f3; color: #20272d;
  font-family: 'Times New Roman','Songti SC','SimSun',serif; }
main { max-width: 1020px; margin: 28px auto; padding: 54px 62px 62px;
  background: white; box-shadow: 0 2px 18px #24374612;
  font-size: 17px; line-height: 1.9; }
h1,h2,h3,h4 { font-family: 'Microsoft YaHei','PingFang SC',sans-serif;
  line-height: 1.5; color: #17384b; font-weight: 600; }
h1 { font-size: 27px; margin: 0 0 30px; padding-bottom: 20px;
  border-bottom: 2px solid #b7cbd6; }
h2 { margin: 38px 0 15px; font-size: 23px; }
h3 { margin: 27px 0 12px; font-size: 19px; }
h4 { margin: 20px 0 10px; font-size: 17px; }
p { margin: 12px 0; text-align: justify; overflow-wrap: anywhere; }
a { color: #165879; text-decoration-thickness: 1px;
  text-underline-offset: 3px; overflow-wrap: anywhere; }
strong { font-weight: bold; }
ol,ul { padding-left: 1.65em; margin: 12px 0; }
li { margin: 8px 0; padding-left: 3px; }
.equation { margin: 18px 0; padding: 14px 19px; background: #f5f8fa;
  border-left: 3px solid #9ab8c8; line-height: 1.75; white-space: pre-wrap;
  overflow-wrap: anywhere; font-family: 'Cambria Math','Microsoft YaHei',sans-serif;
  font-size: 15.4px; font-variant-numeric: lining-nums; }
.table-wrap { margin: 18px 0; overflow-x: auto; }
table { border-collapse: collapse; width: 100%; font-size: 14.8px;
  line-height: 1.65; border-top: 1.6px solid #385468;
  border-bottom: 1.6px solid #385468; font-variant-numeric: tabular-nums; }
th { font-family: 'Microsoft YaHei','PingFang SC',sans-serif;
  font-weight: 500; background: #f2f6f8; border-bottom: 1px solid #90a6b4; }
td,th { padding: 9px 10px; text-align: left; vertical-align: top;
  overflow-wrap: anywhere; }
tr:not(:last-child) td { border-bottom: 1px solid #e1e8ec; }
td.num { text-align: right; }
figure { margin: 23px 0 12px; }
figure img { display: block; width: 100%; height: auto; }
p.caption { margin: 8px 0 16px; font-size: 15px; line-height: 1.75; }
code { font-family: 'Cambria Math','Microsoft YaHei',sans-serif; }
@media(max-width: 700px) {
  body { background: white; }
  main { margin: 0; padding: 26px 20px 40px; box-shadow: none; font-size: 16px; }
  h1 { font-size: 23px; } h2 { font-size: 21px; }
  .equation { font-size: 14px; padding: 12px; }
  table { font-size: 13.5px; } td,th { padding: 7px; }
}
@media print {
  @page { size: A4; margin: 20mm; }
  body { background: white; } main { max-width: none; margin: 0; padding: 0;
    box-shadow: none; font-size: 10.7pt; line-height: 1.65; }
  h1 { font-size: 17pt; } h2 { font-size: 14pt; } h3 { font-size: 12pt; }
  h1,h2,h3,h4 { break-after: avoid; }
  figure,.equation,tr { break-inside: avoid; }
  .equation { font-size: 9.5pt; } table { font-size: 9pt; }
  figure { break-after: avoid; } p.caption { font-size: 9pt; }
  .table-wrap { overflow: visible; }
}
"""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_q1_figure_reference() -> dict:
    """Keep one producer image and give the current reading image a fresh URL."""
    producer = ROOT / "output/paper_figures/v1/fig03_q1_profiles.png"
    identity = digest(producer)
    source_map = json.loads((producer.parent / "figure_sources.json").read_text(encoding="utf-8"))
    # The producer's own manifest still owns the scientific image identity.
    figures = source_map.get("figures", source_map)
    if figures["fig03_q1_profiles"]["outputs"]["png"]["sha256"] != identity:
        raise ValueError("fig03 source image no longer matches its figure manifest")
    asset = ROOT / f"output/paper_figures/reading/fig03_q1_profiles_{identity[:12]}.png"
    asset.parent.mkdir(parents=True, exist_ok=True)
    if not asset.exists():
        asset.write_bytes(producer.read_bytes())
    if digest(asset) != identity:
        raise ValueError("The content-identified fig03 reading image has changed")

    brief = ROOT / "docs/Q1/solution_brief.md"
    original = brief.read_bytes().decode("utf-8")
    pattern = r"^(!\[图1-3[^\]\r\n]*\]\()[^\r\n]+(\))$"
    revised, count = re.subn(pattern, lambda m: m[1] + asset.as_posix() + m[2],
                             original.replace("\r\n", "\n"), flags=re.M)
    if count != 1:
        raise ValueError(f"Expected one figure-1-3 image reference, found {count}")
    if "\r\n" in original:
        revised = revised.replace("\n", "\r\n")
    if revised != original:
        brief.write_bytes(revised.encode("utf-8"))

    readme = ROOT / "README.md"
    original = readme.read_bytes().decode("utf-8")
    pattern = r"(\[图1-3五时刻径向剖面\]\()[^\r\n]+?(\))"
    revised, count = re.subn(pattern, lambda m: m[1] + asset.relative_to(ROOT).as_posix() + m[2], original)
    if count != 1:
        raise ValueError(f"Expected one current Q1 image entry in README, found {count}")
    if revised != original:
        readme.write_bytes(revised.encode("utf-8"))
    return dict(producer=producer.relative_to(ROOT).as_posix(),
                reading_asset=asset.relative_to(ROOT).as_posix(), sha256=identity,
                consumers=[brief.relative_to(ROOT).as_posix(), "README.md"])


def inline(text: str) -> str:
    """Escape content first; restore only supported, checked inline markup."""
    tokens: list[str] = []

    def keep(markup: str) -> str:
        tokens.append(markup)
        return f"\x00{len(tokens) - 1}\x00"

    def link(match: re.Match[str]) -> str:
        label, target = match.groups()
        if not target.startswith(("https://", "http://")):
            raise ValueError(f"Non-portable document link: {label} -> {target}")
        return keep(f'<a href="{html.escape(target, quote=True)}">{html.escape(label)}</a>')

    text = LINK.sub(link, text)
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    for i, value in enumerate(tokens):
        text = text.replace(f"\x00{i}\x00", value)
    return text


def render(source: Path) -> tuple[str, dict]:
    text = source.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    blocks: list[str] = []
    pictures: list[dict] = []
    headings: list[str] = []
    formulas: list[str] = []
    table_sizes: list[dict] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("```"):
            content = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                content.append(lines[i])
                i += 1
            if i == len(lines):
                raise ValueError(f"Unclosed equation block in {source}")
            equation = "\n".join(content)
            formulas.append(equation)
            blocks.append(f'<pre class="equation">{html.escape(equation)}</pre>')
            i += 1
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            level, content = len(heading[1]), heading[2]
            headings.append(content)
            blocks.append(f"<h{level}>{inline(content)}</h{level}>")
            i += 1
            continue
        picture = IMAGE.fullmatch(line)
        if picture:
            alt, target = picture.groups()
            path = Path(target)
            if not path.is_absolute():
                path = source.parent / path
            path = path.resolve(strict=True)
            if not path.is_relative_to(ROOT):
                raise ValueError(f"Unexpected image outside project: {path}")
            media = mimetypes.guess_type(path.name)[0]
            if media not in {"image/png", "image/jpeg", "image/svg+xml"}:
                raise ValueError(f"Unsupported image type: {path}")
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            blocks.append(f'<figure><img alt="{html.escape(alt, quote=True)}" '
                          f'src="data:{media};base64,{data}"></figure>')
            pictures.append(dict(path=path.relative_to(ROOT).as_posix(), sha256=digest(path), alt=alt))
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            if len(rows) < 2 or not all(re.fullmatch(r":?-{2,}:?", c) for c in rows[1]):
                raise ValueError(f"Malformed table in {source}: {rows[:2]}")
            if any(len(row) != len(rows[0]) for row in rows):
                raise ValueError(f"Unequal table columns in {source}")
            alignment = [c.endswith(":") for c in rows[1]]
            rendered_rows = ["<thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in rows[0]) + "</tr></thead>"]
            rendered_rows.append("<tbody>")
            for row in rows[2:]:
                rendered_rows.append("<tr>" + "".join(
                    f'<td class="{"num" if alignment[j] else "text"}">{inline(c)}</td>'
                    for j, c in enumerate(row)) + "</tr>")
            rendered_rows.append("</tbody>")
            blocks.append('<div class="table-wrap"><table>' + "".join(rendered_rows) + "</table></div>")
            table_sizes.append(dict(columns=len(rows[0]), body_rows=len(rows)-2))
            continue
        ordered = re.match(r"^\d+\.\s+", line)
        unordered = re.match(r"^[-*]\s+", line)
        if ordered or unordered:
            pattern = r"^\d+\.\s+" if ordered else r"^[-*]\s+"
            tag = "ol" if ordered else "ul"
            items = []
            while i < len(lines) and re.match(pattern, lines[i].strip()):
                items.append("<li>" + inline(re.sub(pattern, "", lines[i].strip())) + "</li>")
                i += 1
            blocks.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue
        if line.startswith(("<", ">")):
            raise ValueError(f"Unsupported raw HTML/block quote in {source}: {line[:60]}")
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(
                r"^(?:#|```|\||!\[|\d+\.\s|[-*]\s)", lines[i].strip()):
            paragraph.append(lines[i].strip())
            i += 1
        joined = " ".join(paragraph)
        caption = bool(re.match(r"^(?:\*\*)?图\d+[-－—]\d+", joined))
        blocks.append(f'<p{" class=\"caption\"" if caption else ""}>{inline(joined)}</p>')

    if len(re.findall(r"^## \d+ ", text, re.M)) != 10:
        raise ValueError(f"Expected ten main sections: {source}")
    title = headings[0]
    document = ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{html.escape(title)}</title><style>{CSS}</style></head>'
                '<body><main>' + "\n".join(blocks) + '</main></body></html>')
    metadata = dict(source=source.relative_to(ROOT).as_posix(), source_sha256=digest(source),
                    images=pictures, heading_count=len(headings), main_section_count=10,
                    equation_block_count=len(formulas), tables=table_sizes)
    return document, metadata


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    refreshed_figure = refresh_q1_figure_reference()
    results = []
    for q in range(1, 5):
        source = ROOT / f"docs/Q{q}/solution_brief.md"
        document, metadata = render(source)
        path = OUT / f"问题{q}_队友讲解稿.html"
        path.write_text(document, encoding="utf-8", newline="\n")
        metadata.update(output=path.relative_to(ROOT).as_posix(), output_sha256=digest(path), bytes=path.stat().st_size)
        results.append(metadata)
    package = OUT / "队友讲解稿_四问.zip"
    with ZipFile(package, "w", ZIP_DEFLATED) as archive:
        for item in results:
            path = ROOT / item["output"]
            archive.write(path, path.name)
    manifest = dict(editable_source="docs/Q1..Q4/solution_brief.md", role="portable reading copies; not submission files",
                    build_script="scripts/export_teammate_briefs.py", build_script_sha256=digest(Path(__file__)),
                    refreshed_figure_reference=refreshed_figure,
                    external_runtime_dependencies=False, files=results,
                    archive=dict(path=package.relative_to(ROOT).as_posix(), sha256=digest(package),
                                 members=[Path(x["output"]).name for x in results]))
    (OUT / "build_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(dict(files=len(results), embedded_images=sum(len(x['images']) for x in results),
                          archive=manifest['archive']['path']), ensure_ascii=False))


if __name__ == "__main__":
    main()
