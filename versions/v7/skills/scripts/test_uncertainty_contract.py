#!/usr/bin/env python3
"""Regressions for the V5 uncertainty and error-analysis contract."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RULE = ROOT / "rules/36-uncertainty-error-analysis.md"

REQUIRED = {
    "four_source_classes": [
        "输入、观测与参数不确定性",
        "数值近似与计算实现误差",
        "求解与优化不确定性",
        "模型形式与适用域不确定性",
    ],
    "evidence_before_distribution": ["缺少依据时不得虚构概率分布"],
    "tested_not_quantified": ["`tested` 不得升级为 `quantified`"],
    "implementation_failure_rolls_back": ["程序实现错误属于验证失败，必须修复"],
    "sensitivity_not_uncertainty": ["敏感性分析", "不确定性分析", "配套但分责"],
    "decision_impact": ["是否改变数值、排序、可行性或决策"],
    "question_credibility_chain": [
        "模型 → 求解 → 结果 → 可信度说明",
        "不要求四个标题、四个段落或四种",
        "摘要可信度准入门",
        "正文就地闭环门",
    ],
    "cross_solver_internal_only": [
        "只用于内部实现审计",
        "本身不是论文中的误差分析或敏感性分析",
        "不作为摘要中的验证亮点",
    ],
}


def validate(text: str) -> list[str]:
    errors: list[str] = []
    for case, phrases in REQUIRED.items():
        if any(phrase not in text for phrase in phrases):
            errors.append(case)
    return errors


def main() -> None:
    baseline = RULE.read_text(encoding="utf-8")
    if validate(baseline):
        raise AssertionError(f"valid uncertainty contract failed: {validate(baseline)}")
    for case, phrases in REQUIRED.items():
        altered = baseline
        for phrase in phrases:
            altered = altered.replace(phrase, "removed guard")
        errors = validate(altered)
        if case not in errors:
            raise AssertionError(f"{case}: missing guard unexpectedly passed")
    print(f"PASS: {len(REQUIRED)} uncertainty-contract regressions")


if __name__ == "__main__":
    main()
