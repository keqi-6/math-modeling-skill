#!/usr/bin/env python3
"""Validate legacy Skill aliases and direct package-relative paths."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEGACY = re.compile(r"skills/([A-Za-z0-9_./-]+\.(?:md|py|json|yaml))")


def resolve_legacy(relative: str, root: Path) -> Path:
    if relative == "SKILL.md":
        return root / "SKILL.md"
    if relative.startswith("scripts/"):
        return root / relative
    if re.match(r"^\d{2}-[^/]+\.md$", relative):
        return root / "rules" / relative
    return root / relative


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    sources = [root / "SKILL.md"]
    sources.extend(sorted((root / "rules").glob("*.md")))
    sources.extend(
        path for path in sorted((root / "scripts").glob("*.py"))
        if not path.name.startswith("test_")
    )
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for match in LEGACY.finditer(text):
            target = resolve_legacy(match.group(1), root)
            if not target.is_file():
                errors.append(
                    f"{source.relative_to(root)}: unresolved legacy alias "
                    f"skills/{match.group(1)}"
                )
    return errors


def main() -> None:
    errors = validate()
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: all internal Skill path aliases resolve inside V5")


if __name__ == "__main__":
    main()
