#!/usr/bin/env python3
"""检查 V3 是否仍覆盖已知的流程与论文失败模式。"""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    entry = read("SKILL.md")
    receipt = read("rules/01-execution-receipt.md")
    lifecycle = read("rules/05-project-lifecycle.md")
    manuscript = read("rules/23-model-solution-results.md")
    failures: list[str] = []

    cases = {
        "接管时不能相信摘要并直接修改": (
            "SKILL.md",
            entry,
            ("takeover, “continue”, recovery, full audit", "K-02", "before accepting prior status"),
        ),
        "不得越过人工决定直接实现": (
            "rules/05-project-lifecycle.md",
            lifecycle,
            ("人工决定", "正式实现", "越级产物"),
        ),
        "代码正确不等于论文完整": (
            "SKILL.md + rules/23-model-solution-results.md",
            entry + manuscript,
            ("Technical correctness is not manuscript completeness", "每问完整链", "直接回答"),
        ),
        "规则跳过必须有证据": (
            "rules/01-execution-receipt.md",
            receipt,
            ("skipped_rules", "trigger_checked", "evidence", "reason"),
        ),
        "候选成果验证后必须重新准入": (
            "rules/05-project-lifecycle.md",
            lifecycle,
            ("L-06", "信息增量", "不得仅因"),
        ),
        "继续不等于理解确认": (
            "rules/05-project-lifecycle.md",
            lifecycle,
            ("“继续”", "不等于理解确认", "不等于模型"),
        ),
    }

    for name, (location, content, required) in cases.items():
        missing = [token for token in required if token not in content]
        if missing:
            failures.append(f"{name} [{location}] 缺少: {', '.join(missing)}")

    if failures:
        print("REGRESSION TESTS: FAIL")
        print("\n".join(f"- {item}" for item in failures))
        return 1

    print(f"REGRESSION TESTS: PASS ({len(cases)} cases)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
