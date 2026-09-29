#!/usr/bin/env python3
"""静态检查 V3 skill 的活动路由、引用、规则 ID 与迁移状态。"""

from __future__ import annotations

import re
import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "SKILL.md"
ACTIVE = ROOT / "rules"
LEDGER = ROOT / "references" / "migration-ledger.md"


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-complete-migration",
        action="store_true",
        help="迁移台账存在 pending 时返回失败。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors: list[str] = []
    required = [
        ENTRY,
        ACTIVE / "00-execution-gates.md",
        ACTIVE / "01-execution-receipt.md",
        ACTIVE / "05-project-lifecycle.md",
        ACTIVE / "10-global-manuscript-rules.md",
        ACTIVE / "23-model-solution-results.md",
        ACTIVE / "40-evidence-provenance.md",
        ACTIVE / "rule-ownership-map.md",
        LEDGER,
    ]
    for path in required:
        if not path.is_file():
            fail(f"缺少必需文件: {path.relative_to(ROOT)}", errors)

    if errors:
        print("\n".join(errors))
        return 1

    entry = ENTRY.read_text(encoding="utf-8")
    ledger = LEDGER.read_text(encoding="utf-8")
    active_files = sorted(ACTIVE.glob("*.md"))
    all_active = "\n".join(path.read_text(encoding="utf-8") for path in active_files)

    for token in (
        "Mandatory routing matrix",
        "01-execution-receipt.md",
        "05-project-lifecycle.md",
        "No stage jumping",
        "No unproved skip",
    ):
        if token not in entry:
            fail(f"入口缺少强制触发: {token}", errors)

    for prefix in ("K", "G", "R", "L", "M", "F", "B", "A", "S", "C", "V", "E", "H"):
        if not re.search(rf"\b{prefix}-\d{{2}}\b", entry + "\n" + all_active):
            fail(f"缺少稳定规则 ID 族: {prefix}-*", errors)

    ids: dict[str, str] = {}
    for path in [ENTRY, *active_files]:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            match = re.match(r"^#{2,4}\s+([A-Z]-\d{2})\b", line)
            if not match:
                continue
            rule_id = match.group(1)
            if rule_id in ids:
                fail(
                    f"稳定规则 ID 重复: {rule_id} ({ids[rule_id]}, {path.relative_to(ROOT)})",
                    errors,
                )
            ids[rule_id] = path.relative_to(ROOT).as_posix()

    for path in active_files:
        if path.name == "rule-ownership-map.md":
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if re.match(r"^#{2,4}\s+", line) and not re.match(
                r"^#{2,4}\s+[A-Z]-\d{2}\b", line
            ):
                fail(
                    f"活动规则标题缺少稳定 ID: {path.relative_to(ROOT)}:{line_number}",
                    errors,
                )

    references = re.findall(r"`((?:rules|references)/[^`]+\.md)`", entry + "\n" + all_active)
    for relative in sorted(set(references)):
        if not (ROOT / relative).is_file():
            fail(f"内部引用不存在: {relative}", errors)

    source_dir = ROOT / "references" / "rule-sources"
    source_modules = sorted(path.stem for path in source_dir.glob("*.md"))
    for module in source_modules:
        if f"`{module}`" not in ledger:
            fail(f"迁移台账缺少来源模块: {module}", errors)

    migration_pending = "| pending |" in ledger or "待分配" in ledger
    if migration_pending and args.require_complete_migration:
        fail("迁移台账仍有 pending；允许试用，不允许宣称完整迁移", errors)

    if errors:
        print("V3 VALIDATION: NOT COMPLETE")
        print("\n".join(f"- {item}" for item in errors))
        return 2

    if migration_pending:
        print("V3 VALIDATION: STRUCTURE PASS; MIGRATION PENDING")
    else:
        print("V3 VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
