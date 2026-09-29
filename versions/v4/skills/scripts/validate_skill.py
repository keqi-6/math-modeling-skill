#!/usr/bin/env python3
"""Structural checks for the V4 skill."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
RULES = {
    "data.md",
    "modeling.md",
    "verification.md",
    "manuscript.md",
    "visuals-layout.md",
    "provenance-delivery.md",
}


def main() -> None:
    errors: list[str] = []
    text = SKILL.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append("missing YAML frontmatter")
    for field in ["name:", "description:"]:
        if field not in text.split("---", 2)[1]:
            errors.append(f"missing frontmatter field {field}")
    if len(text.splitlines()) > 500:
        errors.append("SKILL.md exceeds 500 lines")
    for state in [
        "S0_RECOVER", "S1_INTERPRET", "S2_ASSESS", "S3_DECIDE",
        "S4_SPECIFY", "S5_IMPLEMENT", "S6_VERIFY", "S7_PUBLISH",
    ]:
        if state not in text:
            errors.append(f"missing state {state}")
    for phrase in [
        "implementation_allowed",
        "keep_current",
        "External-guidance boundary",
        "Silence",
        "full-read",
    ]:
        if phrase not in text:
            errors.append(f"missing controller guard: {phrase}")

    actual_rules = {path.name for path in (ROOT / "rules").glob("*.md")}
    if actual_rules != RULES:
        errors.append(
            f"rule set mismatch: expected={sorted(RULES)}, actual={sorted(actual_rules)}"
        )

    permission_terms = re.compile(
        r"\bimplementation_allowed\b|explicit user confirmation|明确批准|允许正式"
    )
    for path in (ROOT / "rules").glob("*.md"):
        body = path.read_text(encoding="utf-8")
        if permission_terms.search(body):
            errors.append(f"distributed permission language in {path.name}")

    required = [
        ROOT / "references/migration-ledger.md",
        ROOT / "scripts/validate_receipt.py",
        ROOT / "scripts/test_regressions.py",
        ROOT / "agents/openai.yaml",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: V4 structure, controller guards, and unique quality owners")


if __name__ == "__main__":
    main()

