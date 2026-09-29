#!/usr/bin/env python3
"""Validate that V7 has one activation, permission, and state authority."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def validate(skill_root: Path) -> list[str]:
    errors: list[str] = []
    controller = (skill_root / "SKILL.md").read_text(encoding="utf-8")
    if not controller.startswith("---\n"):
        errors.append("SKILL.md must remain the activation entry")
    for path in sorted((skill_root / "rules").glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if text.startswith("---\n") and "\nname:" in text.split("---", 2)[1]:
            errors.append(f"parallel Skill frontmatter in {path.relative_to(skill_root)}")

    orchestration = (skill_root / "rules/00-project-orchestration.md").read_text(encoding="utf-8")
    for phrase in [
        "不是独立 Skill、第二入口或第二状态机",
        "Stage 0–9 是工作类别和检查清单",
        "V7 控制器状态",
        "`S0_RECOVER`", "`S1_INTERPRET`", "`S2_ASSESS`", "`S3_DECIDE`",
        "`S4_SPECIFY`", "`S5_IMPLEMENT`", "`S6_VERIFY`", "`S7_PUBLISH`",
    ]:
        if phrase not in orchestration:
            errors.append(f"orchestration mapping missing: {phrase}")

    handoff = (skill_root / "rules/14-session-handoff.md").read_text(encoding="utf-8")
    for phrase in [
        "R0_INCREMENTAL_CHECKPOINT", "R1_HASH_DELTA_RECOVERY", "R2_FULL_RECOVERY",
        "新会话本身至少触发 R1，但不自动等于 R2",
        "普通暂停执行变更路径及消费者复核",
        "里程碑或最终闭合执行全量复核",
    ]:
        if phrase not in handoff:
            errors.append(f"proportional recovery contract missing: {phrase}")

    registry = json.loads((skill_root / "references/routing-registry.json").read_text(encoding="utf-8"))
    if registry.get("policy", {}).get("permission_owner") != "SKILL.md":
        errors.append("routing registry permission_owner must be SKILL.md")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", type=Path)
    args = parser.parse_args()
    errors = validate(args.skill_root.resolve())
    print(json.dumps({"passed": not errors, "error_count": len(errors), "errors": errors}, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
