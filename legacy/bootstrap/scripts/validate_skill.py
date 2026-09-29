#!/usr/bin/env python3
"""Structural checks for the V6 skill."""

from __future__ import annotations

from pathlib import Path

from validate_v1_migration import validate as validate_v1_migration
from validate_version_deltas import validate as validate_version_deltas
from validate_internal_paths import validate as validate_internal_paths


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
RULES = {
    "00-project-orchestration.md",
    "01-contest-project-pattern.md", "02-latex-setup.md",
    "03-paper-content-rules.md", "04-figure-generator.md",
    "05-audit-protocol.md", "06-weiwei-norms.md",
    "07-algorithm-reference.md", "08-literature-search.md",
    "09-robustness-checker.md", "10-json-handoff.md",
    "11-paper-finalizer.md", "12-source-audit-and-provenance.md",
    "13-excellent-paper-expression.md", "14-session-handoff.md",
    "15-pipeline-methodology.md", "16-data-audit-methodology.md",
    "17-reader-first-manuscript-audit.md", "18-execution-receipt.md",
    "19-project-lifecycle.md", "20-execution-gates.md",
    "21-global-manuscript-acceptance.md", "22-front-matter-acceptance.md",
    "23-background-analysis-acceptance.md", "24-assumptions-data-acceptance.md",
    "25-model-results-acceptance.md", "26-conclusion-references-acceptance.md",
    "27-visual-layout-acceptance.md", "28-evidence-acceptance.md",
    "29-governance-acceptance.md", "30-data-minimum.md",
    "31-modeling-minimum.md", "32-verification-minimum.md",
    "33-manuscript-minimum.md", "34-visuals-minimum.md",
    "35-provenance-delivery-minimum.md",
    "36-uncertainty-error-analysis.md",
    "37-scientific-figure-design.md",
}


def main() -> None:
    errors: list[str] = []
    errors.extend(validate_v1_migration(ROOT))
    errors.extend(validate_version_deltas(ROOT))
    errors.extend(validate_internal_paths(ROOT))
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
        "Recovery evidence contract",
        "recovery_manifest.json",
        "truncated: false",
        "`S0_RECOVER` is open",
        "V6 owns its detailed rules directly",
        "R0_INCREMENTAL_CHECKPOINT",
        "R1_HASH_DELTA_RECOVERY",
        "R2_FULL_RECOVERY",
        "single hand-written `current_stage` is not authoritative",
        "receipt_kind: end",
        "explicit `skill_change` approval",
        "may strengthen quality within an allowed action",
        "stable-ID criteria and V4's concise cross-checks",
        "Every manuscript mutation round",
        "A previous round's or previous window's read",
        "pre-mutation propagation matrix",
        "substantive_analysis: true | false",
        "do not confuse “not approved for promotion” with “must remain only in chat.”",
    ]:
        if phrase not in text:
            errors.append(f"missing controller guard: {phrase}")

    actual_rules = {path.name for path in (ROOT / "rules").glob("*.md")}
    if actual_rules != RULES:
        errors.append(
            f"rule set mismatch: expected={sorted(RULES)}, actual={sorted(actual_rules)}"
        )

    required = [
        ROOT / "references/migration-ledger.md",
        ROOT / "references/qualified-skill-standard.md",
        ROOT / "references/v1-integration-map.json",
        ROOT / "references/version-delta-map.json",
        ROOT / "references/start_receipt.schema.json",
        ROOT / "references/end_receipt.schema.json",
        ROOT / "scripts/validate_receipt.py",
        ROOT / "scripts/recovery_manifest.py",
        ROOT / "scripts/test_regressions.py",
        ROOT / "scripts/validate_v1_migration.py",
        ROOT / "scripts/test_v1_migration.py",
        ROOT / "scripts/validate_version_deltas.py",
        ROOT / "scripts/test_version_deltas.py",
        ROOT / "scripts/validate_internal_paths.py",
        ROOT / "scripts/test_internal_paths.py",
        ROOT / "scripts/forward_test_recovery.py",
        ROOT / "scripts/test_uncertainty_contract.py",
        ROOT / "scripts/validate_figure_assets.py",
        ROOT / "scripts/test_figure_assets.py",
        ROOT / "agents/openai.yaml",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")

    uncertainty = (ROOT / "rules/36-uncertainty-error-analysis.md").read_text(
        encoding="utf-8"
    )
    for phrase in [
        "输入、观测与参数不确定性",
        "数值近似与计算实现误差",
        "求解与优化不确定性",
        "模型形式与适用域不确定性",
        "tested` 不得升级为 `quantified",
        "缺少依据时不得虚构概率分布",
        "程序实现错误属于验证失败",
        "模型 → 求解 → 结果 → 可信度说明",
        "摘要可信度准入门",
        "只用于内部实现审计",
        "本身不是论文中的误差分析或敏感性分析",
        "误差与灵敏度的方法—数理关系门",
        "不得用相对同值差伪装成离散误差",
    ]:
        if phrase not in uncertainty:
            errors.append(f"uncertainty contract missing guard: {phrase}")

    figure_design = (ROOT / "rules/37-scientific-figure-design.md").read_text(
        encoding="utf-8"
    )
    for phrase in [
        "真实性映射门",
        "题面对象 → 几何/拓扑关系 → 数学变量 → 作用或信息流 → 图中元素",
        "公式可以约束动力学关系，但不能唯一确定",
        "工程结构、剖面与受力图",
        "动态平衡坐标",
        "样板门与准入门",
        "不得把“准入项目目录”默认为“替换正文现图”",
        "自动检查与人工检查边界",
        "生成式位图只用于不承载精确几何、数值或拓扑的装饰性素材",
    ]:
        if phrase not in figure_design:
            errors.append(f"scientific figure contract missing guard: {phrase}")

    paper_rule = (ROOT / "rules/03-paper-content-rules.md").read_text(encoding="utf-8")
    for phrase in [
        "多步关键模型的可跟随推导门",
        "不得只给紧凑矩阵式",
        "代表性",
        "交叉项",
        "删除反例",
        "论文正文元话语禁令",
        "物理模型另加“来源逐项落地”检查",
        "LaTeX正文按一级标题拆分合同",
        "一个body文件不得包含两个不同的一级标题",
        "同一一级标题也不得跨多个body文件拼接",
        "每轮改稿全规则读取门",
        "跨章节传播矩阵",
        "结论只回收逐问答案、最低必要证据、成立条件和适用边界",
        "优化模型的语义闭合与自然展开门",
        "标签只是导航，不是合格证",
        "求解叙述的数学主线门",
        "不是按“每步一式”配额组织",
        "删除标签检查和重复信息检查",
        "编号能帮助复述时",
        "不把全部操作拼成冗长的自造算法名",
    ]:
        if phrase not in paper_rule:
            errors.append(f"paper derivation contract missing guard: {phrase}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    validator = (ROOT / "scripts/validate_receipt.py").read_text(encoding="utf-8")
    for phrase in [
        "GATES =", "verify_manifest", "manifest_sha256",
        "S0 mutation prohibition violated", "validate_manuscript_round",
        "cross-section propagation requires", "validate_artifact_plan",
        "validate_artifact_disposition",
        "substantive analysis requires a non-chat artifact disposition",
    ]:
        if phrase not in validator:
            errors.append(f"receipt validator missing recovery guard: {phrase}")

    tests = (ROOT / "scripts/test_regressions.py").read_text(encoding="utf-8")
    for case in [
        "custom_gate_value", "closed_without_evidence", "count_mismatch",
        "s0_mutation", "truncated_output", "unresolved_item", "stale_inventory",
        "substantive_analysis_without_artifact", "complete_with_unrealized_artifact",
    ]:
        if case not in tests:
            errors.append(f"missing recovery regression: {case}")

    delta_tests = (ROOT / "scripts/test_version_deltas.py").read_text(encoding="utf-8")
    for case in [
        "altered_v3_stable_id_acceptance", "missing_v4_quality_crosscheck",
        "semantic_only_downgrade", "unrouted_exact_delta",
    ]:
        if case not in delta_tests:
            errors.append(f"missing exact-delta regression: {case}")

    forward_test = (ROOT / "scripts/forward_test_recovery.py").read_text(encoding="utf-8")
    for phrase in ["--self-test", "build_fixture", "project_unchanged"]:
        if phrase not in forward_test:
            errors.append(f"forward-test interface missing: {phrase}")

    migration_validator = (
        ROOT / "scripts/validate_v1_migration.py"
    ).read_text(encoding="utf-8")
    for phrase in [
        "integrated active hash mismatch", "unmapped active V5 files",
        "active routing absent", "shadow V1 preservation directory",
    ]:
        if phrase not in migration_validator:
            errors.append(f"migration validator missing guard: {phrase}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: V6 structure, proportional recovery, component state, receipt dispatch, and integrated detailed rules")


if __name__ == "__main__":
    main()
