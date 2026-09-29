#!/usr/bin/env python3
"""编译Chemfig反应路线图，并登记PDF、SVG和PNG矢量/预览产物。"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src" / "q1" / "04_literature_possible_reaction_pathways.tex"
OUT = ROOT / "output" / "q1"
FIGURES = OUT / "figures"
STEM = "04_literature_possible_reaction_pathways"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    xelatex = shutil.which("xelatex")
    pdftocairo = shutil.which("pdftocairo")
    if not xelatex or not pdftocairo:
        raise RuntimeError("需要可用的xelatex与pdftocairo")

    FIGURES.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [xelatex, "-interaction=nonstopmode", "-halt-on-error",
         f"-output-directory={FIGURES.relative_to(ROOT)}", str(SOURCE.relative_to(ROOT))],
        cwd=ROOT, check=True,
    )
    pdf = FIGURES / f"{STEM}.pdf"
    svg = FIGURES / f"{STEM}.svg"
    png = FIGURES / f"{STEM}.png"
    subprocess.run([pdftocairo, "-svg", str(pdf), str(svg)], check=True)
    subprocess.run([pdftocairo, "-png", "-singlefile", "-r", "300",
                    str(pdf), str(png.with_suffix(""))], check=True)
    for suffix in (".aux", ".log"):
        auxiliary = FIGURES / f"{STEM}{suffix}"
        if auxiliary.exists():
            auxiliary.unlink()

    manifest_path = OUT / "artifact_manifest.csv"
    manifest = pd.read_csv(manifest_path, encoding="utf-8-sig")
    relative = [str(path.relative_to(ROOT)) for path in (pdf, svg, png)]
    manifest = manifest[~manifest["relative_path"].isin(relative)]
    additions = pd.DataFrame([
        {"relative_path": str(path.relative_to(ROOT)), "sha256": sha256(path),
         "producer": "src/q1/04_build_reaction_scheme.py"}
        for path in (pdf, svg, png)
    ])
    pd.concat([manifest, additions], ignore_index=True).to_csv(
        manifest_path, index=False, encoding="utf-8-sig"
    )
    print("Chemfig路线图完成：PDF、SVG、PNG。")


if __name__ == "__main__":
    main()
