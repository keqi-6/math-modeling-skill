#!/usr/bin/env python3
"""Mechanical checks for a reproducible scientific-figure asset bundle."""

from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("invalid PNG signature")
    return struct.unpack(">II", header[16:24])


def run_text(command: list[str]) -> str:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout


def validate(
    source: Path,
    svg: Path,
    pdf: Path,
    png: Path,
    min_width: int = 1200,
    min_height: int = 600,
    allow_raster_in_svg: bool = False,
    allow_type3: bool = False,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    facts: dict[str, object] = {}

    for label, path in {"source": source, "svg": svg, "pdf": pdf, "png": png}.items():
        if not path.is_file():
            errors.append(f"missing {label}: {path}")
    if errors:
        return {"passed": False, "errors": errors, "warnings": warnings, "facts": facts}

    if source.suffix.lower() not in {".py", ".r", ".jl", ".m", ".tex", ".svg"}:
        warnings.append(f"unusual editable source suffix: {source.suffix}")

    try:
        root = ET.parse(svg).getroot()
        local_tags = [node.tag.rsplit("}", 1)[-1] for node in root.iter()]
        if root.tag.rsplit("}", 1)[-1] != "svg":
            errors.append("SVG root element is not svg")
        if "viewBox" not in root.attrib:
            errors.append("SVG lacks viewBox")
        if not any(tag in {"text", "path", "line", "polyline", "polygon"} for tag in local_tags):
            errors.append("SVG has no inspectable vector content")
        raster_count = local_tags.count("image")
        if raster_count and not allow_raster_in_svg:
            errors.append("SVG embeds raster images without explicit allowance")
        if any(tag in {"linearGradient", "radialGradient", "filter"} for tag in local_tags):
            warnings.append("SVG contains gradient or filter effects; confirm they carry information")
        facts["svg_viewbox"] = root.attrib.get("viewBox")
        facts["svg_text_elements"] = local_tags.count("text")
        facts["svg_embedded_images"] = raster_count
    except (ET.ParseError, OSError) as exc:
        errors.append(f"cannot parse SVG: {exc}")

    try:
        width, height = png_size(png)
        facts["png_pixels"] = [width, height]
        if width < min_width or height < min_height:
            errors.append(
                f"PNG too small for review: {width}x{height}; minimum {min_width}x{min_height}"
            )
    except (OSError, ValueError, struct.error) as exc:
        errors.append(f"cannot inspect PNG: {exc}")

    try:
        if pdf.read_bytes()[:5] != b"%PDF-":
            errors.append("invalid PDF signature")
    except OSError as exc:
        errors.append(f"cannot inspect PDF: {exc}")

    if shutil.which("pdfinfo"):
        try:
            info = run_text(["pdfinfo", str(pdf)])
            pages = next(
                (line.split(":", 1)[1].strip() for line in info.splitlines() if line.startswith("Pages:")),
                None,
            )
            facts["pdf_pages"] = int(pages) if pages is not None else None
            if facts["pdf_pages"] != 1:
                errors.append(f"figure PDF must have one page, found {facts['pdf_pages']}")
        except (RuntimeError, ValueError) as exc:
            errors.append(f"pdfinfo failed: {exc}")
    else:
        warnings.append("pdfinfo unavailable; page count not checked")

    if shutil.which("pdffonts"):
        try:
            fonts = run_text(["pdffonts", str(pdf)])
            facts["pdf_type3_fonts"] = "Type 3" in fonts
            if facts["pdf_type3_fonts"] and not allow_type3:
                errors.append("PDF contains Type 3 fonts")
        except RuntimeError as exc:
            errors.append(f"pdffonts failed: {exc}")
    else:
        warnings.append("pdffonts unavailable; font type not checked")

    return {"passed": not errors, "errors": errors, "warnings": warnings, "facts": facts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--svg", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--min-width", type=int, default=1200)
    parser.add_argument("--min-height", type=int, default=600)
    parser.add_argument("--allow-raster-in-svg", action="store_true")
    parser.add_argument("--allow-type3", action="store_true")
    args = parser.parse_args()
    result = validate(
        args.source,
        args.svg,
        args.pdf,
        args.png,
        args.min_width,
        args.min_height,
        args.allow_raster_in_svg,
        args.allow_type3,
    )
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
