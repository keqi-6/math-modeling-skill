#!/usr/bin/env python3
"""Regression test for stale internal Skill paths."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from validate_internal_paths import ROOT, validate


def main() -> None:
    temp = Path(tempfile.mkdtemp())
    target = temp / "renamed-skill-package"
    try:
        shutil.copytree(ROOT, target)
        errors = validate(target)
        if errors:
            raise AssertionError(f"renamed package failed: {errors}")
        path = target / "rules/14-session-handoff.md"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n`skills/99-missing.md`\n",
            encoding="utf-8",
        )
        if not validate(target):
            raise AssertionError("unresolved legacy alias unexpectedly passed")
    finally:
        shutil.rmtree(temp)
    print("PASS: renamed-package path resolution and stale-alias regression")


if __name__ == "__main__":
    main()
