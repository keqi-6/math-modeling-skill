#!/usr/bin/env python3
"""Negative regressions for V1 preservation and routing completeness."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from validate_v1_migration import ROOT, validate


def clone() -> Path:
    temp = Path(tempfile.mkdtemp())
    target = temp / "skill"
    shutil.copytree(ROOT, target)
    return target


def expect_invalid(name: str, root: Path) -> None:
    if not validate(root):
        raise AssertionError(f"{name}: incomplete migration unexpectedly passed")


def main() -> None:
    baseline = clone()
    try:
        errors = validate(baseline)
        if errors:
            raise AssertionError(f"valid_baseline: {errors}")
    finally:
        shutil.rmtree(baseline.parent)

    missing = clone()
    try:
        (missing / "rules/08-literature-search.md").unlink()
        expect_invalid("missing_integrated_rule", missing)
    finally:
        shutil.rmtree(missing.parent)

    altered = clone()
    try:
        path = altered / "rules/03-paper-content-rules.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        if validate(altered):
            raise AssertionError("legacy_hash_freeze: V7 owner evolution was incorrectly rejected")
    finally:
        shutil.rmtree(altered.parent)

    unmapped = clone()
    try:
        path = unmapped / "references/v1-integration-map.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["entries"] = [
            item for item in payload["entries"]
            if item["source"] != "16-data-audit-methodology.md"
        ]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        expect_invalid("unmapped_rule", unmapped)
    finally:
        shutil.rmtree(unmapped.parent)

    unrouted = clone()
    try:
        path = unrouted / "SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "`rules/07-algorithm-reference.md`, `rules/15-pipeline-methodology.md`",
                "`rules/15-pipeline-methodology.md`",
            ),
            encoding="utf-8",
        )
        expect_invalid("unrouted_rule", unrouted)
    finally:
        shutil.rmtree(unrouted.parent)

    duplicate = clone()
    try:
        path = duplicate / "references/v1-integration-map.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["entries"].append(dict(payload["entries"][0]))
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        expect_invalid("duplicate_mapping", duplicate)
    finally:
        shutil.rmtree(duplicate.parent)

    print("PASS: V1 identity/routing regressions and no legacy whole-file hash freeze")


if __name__ == "__main__":
    main()
