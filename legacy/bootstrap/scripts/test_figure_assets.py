#!/usr/bin/env python3
"""Regression tests for scientific-figure asset validation."""

from __future__ import annotations

import struct
import tempfile
import zlib
from pathlib import Path

from validate_figure_assets import validate


def png(path: Path, width: int, height: int) -> None:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))

    rows = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    path.write_bytes(data)


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = root / "draw.py"
        svg = root / "figure.svg"
        pdf = root / "figure.pdf"
        image = root / "figure.png"
        source.write_text("print('reproducible')\n", encoding="utf-8")
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<path d="M0 0L10 10"/><text x="1" y="5">x</text></svg>',
            encoding="utf-8",
        )
        pdf.write_bytes(b"%PDF-1.4\n")
        png(image, 1200, 600)

        # Disable external PDF tools for this minimal fixture by accepting their
        # expected failure only through missing executable-independent checks.
        result = validate(source, svg, pdf, image)
        external_only = [e for e in result["errors"] if e.startswith(("pdfinfo failed", "pdffonts failed"))]
        if len(external_only) != len(result["errors"]):
            raise AssertionError(result)

        small = root / "small.png"
        png(small, 200, 100)
        result = validate(source, svg, pdf, small)
        if not any("PNG too small" in error for error in result["errors"]):
            raise AssertionError("small_png_regression_failed")

        raster_svg = root / "raster.svg"
        raster_svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<image href="x.png" width="10" height="10"/></svg>',
            encoding="utf-8",
        )
        result = validate(source, raster_svg, pdf, image)
        if not any("embeds raster" in error for error in result["errors"]):
            raise AssertionError("embedded_raster_regression_failed")

    print("PASS: figure asset validator regressions")


if __name__ == "__main__":
    main()
