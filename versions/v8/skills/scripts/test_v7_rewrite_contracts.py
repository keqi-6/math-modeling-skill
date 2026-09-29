#!/usr/bin/env python3
"""Regression contracts for V6 capability blocks intentionally rewritten in V7."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def require(relative: str, *needles: str) -> None:
    text = read(relative)
    missing = [item for item in needles if item not in text]
    if missing:
        raise AssertionError(f"{relative} misses rewrite contract: {missing}")


def forbid(relative: str, *needles: str) -> None:
    text = read(relative)
    found = [item for item in needles if item in text]
    if found:
        raise AssertionError(f"{relative} retains rejected contract: {found}")


def main() -> None:
    require("SKILL.md", "sole authority", "S0_RECOVER", "S7_PUBLISH",
            "solution_brief", "per-question teammate solution explanation", "paper/", "docs/")
    require("rules/00-project-orchestration.md", "详细项目编排参考",
            "Stage 8 COMMUNICATE", "逐问队友讲解稿")
    forbid("rules/00-project-orchestration.md", "name: math-modeling-project-bootstrap")
    require("rules/01-contest-project-pattern.md", "R0", "R1", "R2",
            "docs/<task-id>/solution_brief.md", "逐问解决方案讲解稿")
    require("rules/03-paper-content-rules.md", "S4", "不从求解结果反推假设")
    forbid("rules/03-paper-content-rules.md", "**时机**：做完第一题再写假设")
    require("rules/11-paper-finalizer.md", "rules/02-latex-setup.md")
    forbid("rules/11-paper-finalizer.md", "skills/02-latex-setup.md")
    require("rules/14-session-handoff.md", "R0", "R1", "R2")
    require("rules/16-data-audit-methodology.md", "待审候选")
    require("rules/18-execution-receipt.md", "# 18 —", "scripts/validate_skill.py",
            "scripts/test_regressions.py")
    forbid("rules/18-execution-receipt.md", "validate_skill_v3.py", "test_skill_regressions.py")
    require("rules/19-project-lifecycle.md", "# 19 —", "Recovery and full-read gate", "所选恢复级别")
    forbid("rules/19-project-lifecycle.md", "入口 K-02")
    require("rules/27-visual-layout-acceptance.md", "29-governance-acceptance.md")
    forbid("rules/27-visual-layout-acceptance.md", "`50-governance-handoff.md`")
    require("rules/29-governance-acceptance.md", "20-execution-gates.md")
    forbid("rules/29-governance-acceptance.md", "`00-execution-gates.md`")
    require("rules/36-uncertainty-error-analysis.md", "现为 V7 的误差与不确定性专项主责")
    require("references/start_receipt.schema.json", "solution_brief")
    require("references/end_receipt.schema.json", "solution_brief")
    print("PASS: V7 rewritten-capability contracts")


if __name__ == "__main__":
    main()
