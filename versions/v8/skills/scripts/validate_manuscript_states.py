#!/usr/bin/env python3
"""Validate the single manuscript audit-state registry and its full mirrors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate(skill_root: Path, registry_path: Path) -> list[str]:
    errors: list[str] = []
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    states = payload.get("states", [])
    levels = [item.get("level") for item in states if isinstance(item, dict)]
    labels = [item.get("label") for item in states if isinstance(item, dict)]
    if levels != list(range(1, 8)):
        errors.append(f"manuscript state levels must be exactly 1..7: {levels}")
    if len(labels) != 7 or len(set(labels)) != 7 or any(not item for item in labels):
        errors.append("manuscript state labels must contain seven unique non-empty values")
    promotion = payload.get("promotion_rules", {})
    if promotion.get("submit_for_human_review_from") != 6:
        errors.append("human review submission must start at level 6")
    if promotion.get("formal_promotion_requires") != 7:
        errors.append("formal promotion must require level 7")
    if promotion.get("explicit_human_confirmation") is not True:
        errors.append("explicit human confirmation must remain required")
    if promotion.get("compile_or_machine_check_cannot_promote_alone") is not True:
        errors.append("machine checks must not promote alone")
    mirrors = payload.get("mirrors", [])
    if set(mirrors) != {
        "rules/17-reader-first-manuscript-audit.md",
        "rules/20-execution-gates.md",
    }:
        errors.append("state mirrors must be exactly rules 17 and 20")
    for relative in mirrors:
        path = skill_root / relative
        if not path.is_file():
            errors.append(f"missing state mirror {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        section_heading = "## 8. 状态机与禁止越级" if relative.startswith("rules/17-") else "## G-04 七级状态"
        if section_heading not in text:
            errors.append(f"{relative}: missing state section heading")
            continue
        section = text.split(section_heading, 1)[1]
        next_heading = section.find("\n## ")
        if next_heading >= 0:
            section = section[:next_heading]
        positions = []
        for label in labels:
            marker = f"`{label}`"
            position = section.find(marker)
            if position < 0:
                errors.append(f"{relative}: missing state label {label}")
            positions.append(position)
        if all(position >= 0 for position in positions) and positions != sorted(positions):
            errors.append(f"{relative}: state labels are out of order")
        if "references/manuscript-audit-states.json" not in section:
            errors.append(f"{relative}: does not declare the shared state registry")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", type=Path)
    parser.add_argument("registry", type=Path)
    args = parser.parse_args()
    errors = validate(args.skill_root.resolve(), args.registry)
    print(json.dumps({"passed": not errors, "error_count": len(errors), "errors": errors}, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
