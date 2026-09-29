#!/usr/bin/env python3
"""Negative regressions for V2–V4 delta integration."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from validate_version_deltas import ROOT, validate


def clone() -> Path:
    temp = Path(tempfile.mkdtemp())
    target = temp / "skill"
    shutil.copytree(ROOT, target)
    return target


def expect_invalid(name: str, root: Path) -> None:
    if not validate(root):
        raise AssertionError(f"{name}: missing version delta unexpectedly passed")


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
        (missing / "rules/17-reader-first-manuscript-audit.md").unlink()
        expect_invalid("missing_v2_reader_gate", missing)
    finally:
        shutil.rmtree(missing.parent)

    altered = clone()
    try:
        path = altered / "rules/18-execution-receipt.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        if validate(altered):
            raise AssertionError("legacy_delta_hash_freeze: reviewed V7 evolution was rejected")
    finally:
        shutil.rmtree(altered.parent)

    altered_acceptance = clone()
    try:
        path = altered_acceptance / "rules/25-model-results-acceptance.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
        if validate(altered_acceptance):
            raise AssertionError("legacy_acceptance_hash_freeze: reviewed V7 evolution was rejected")
    finally:
        shutil.rmtree(altered_acceptance.parent)

    missing_crosscheck = clone()
    try:
        (missing_crosscheck / "rules/30-data-minimum.md").unlink()
        expect_invalid("missing_v4_quality_crosscheck", missing_crosscheck)
    finally:
        shutil.rmtree(missing_crosscheck.parent)

    downgraded = clone()
    try:
        path = downgraded / "references/version-delta-map.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        target = next(
            item for item in payload["entries"]
            if item["source"] == "skills_v3/rules/10-global-manuscript-rules.md"
        )
        target["treatment"] = "stable_ids_mapped_to_full_detail"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        expect_invalid("semantic_only_downgrade", downgraded)
    finally:
        shutil.rmtree(downgraded.parent)

    unrouted = clone()
    try:
        path = unrouted / "SKILL.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                ", `rules/34-visuals-minimum.md`", ""
            ),
            encoding="utf-8",
        )
        expect_invalid("unrouted_exact_delta", unrouted)
    finally:
        shutil.rmtree(unrouted.parent)

    unmapped = clone()
    try:
        path = unmapped / "references/version-delta-map.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["entries"] = [
            item for item in payload["entries"] if item["introduced_in"] != "V4"
        ]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        expect_invalid("missing_v4_delta", unmapped)
    finally:
        shutil.rmtree(unmapped.parent)

    print("PASS: V2–V4 identity/routing regressions and no legacy whole-file hash freeze")


if __name__ == "__main__":
    main()
