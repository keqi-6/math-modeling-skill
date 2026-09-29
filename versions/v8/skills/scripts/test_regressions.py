#!/usr/bin/env python3
"""Behavioral regressions for V5 recovery and decision permission gates."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from recovery_manifest import inventory
from validate_receipt import (
    validate_artifact_plan, validate_decision, validate_receipt, validate_project_state,
)


def decision(
    *, necessity: str, options: list[str], approval: str,
    scope: str | None, allowed: bool,
) -> dict:
    return {
        "id": "D-MODEL-1", "type": "model", "component": "q1",
        "current_approach": "descriptive baseline",
        "observed_gap": "external rubric mentions fitted functions",
        "evidence_for_gap": ["official rubric"],
        "necessity": {"status": necessity, "consequence_if_unchanged": "assess"},
        "options": [{"id": item} for item in options],
        "recommendation": None, "user_decision": approval,
        "approved_scope": scope, "prohibited_scope": None,
        "implementation_allowed": allowed,
    }


def complete_manifest(root: Path) -> tuple[Path, dict]:
    manifest = inventory(root)
    for item in manifest["files"]:
        if item["duplicate_of"] is not None:
            continue
        if item["representation"] == "text":
            count = item["line_count"]
            item["inspection"] = {
                "status": "complete", "truncated": False,
                "read_ranges": [] if count == 0 else [[1, count]],
            }
        else:
            item["inspection"] = {
                "status": "complete", "truncated": False,
                "method": "native test inspection", "inspected_units": ["all"],
                "findings": "test fixture inspected",
            }
    path = root.parent / "recovery_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, manifest


def recovery_receipt(root: Path, path: Path, manifest: dict) -> dict:
    canonical = [item for item in manifest["files"] if item["duplicate_of"] is None]
    return {
        "receipt_kind": "start", "task": "continue", "scope": ".",
        "components": ["project"], "state_before": "unknown",
        "earliest_open_state": "S0_RECOVER", "required_inputs": [],
        "routed_rules": [], "allowed_actions": ["read"],
        "prohibited_actions": ["mutate"], "full_read_gate": "closed",
        "recovery_evidence": {
            "manifest_path": path.as_posix(),
            "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "inventory_file_count": len(manifest["files"]),
            "canonical_item_count": len(canonical),
            "completed_canonical_count": len(canonical),
            "unresolved_count": 0,
        },
        "decisions_required": [], "implementation_allowed": False,
        "substantive_analysis": False,
        "artifact_plan": [{
            "content": "recovery inspection", "disposition": "no_project_artifact",
            "artifact_class": "not_applicable",
            "path": "", "promotion_requires": "none",
            "reason": "fixture keeps recovery evidence outside the project",
        }],
    }


def expect_invalid(name: str, errors: list[str]) -> None:
    if not errors:
        raise AssertionError(f"{name}: unsafe payload unexpectedly passed")


def expect_valid(name: str, errors: list[str]) -> None:
    if errors:
        raise AssertionError(f"{name}: {errors}")


def main() -> None:
    # Figure-design regression: visual polish must follow a source-grounded
    # topology/force mapping, and admission must not silently replace the
    # manuscript's current figure.
    figure_rule = (
        Path(__file__).resolve().parents[1] / "rules/37-scientific-figure-design.md"
    ).read_text(encoding="utf-8")
    for guard in [
        "真实性映射门",
        "题面对象 → 几何/拓扑关系 → 数学变量 → 作用或信息流 → 图中元素",
        "公式可以约束动力学关系，但不能唯一确定",
        "生成式位图只用于不承载精确几何、数值或拓扑的装饰性素材",
        "不得把“准入项目目录”默认为“替换正文现图”",
        "自动检查不能判断拓扑是否忠于原题",
    ]:
        if guard not in figure_rule:
            raise AssertionError(f"scientific_figure_guard_missing: {guard}")

    # Manuscript regression: a compact final matrix alone must not satisfy a
    # multi-step model derivation.  The active rule must require traceable
    # intermediate relations, representative coupling terms, and a deletion
    # counterexample while preserving the evidence-strength boundary.
    paper_rule = (
        Path(__file__).resolve().parents[1] / "rules/03-paper-content-rules.md"
    ).read_text(encoding="utf-8")
    for guard in [
        "多步关键模型的可跟随推导门",
        "不得只给紧凑矩阵式",
        "代表性",
        "交叉项",
        "删除反例",
        "数值收敛、实现一致、局部不可改进和全局最优",
    ]:
        if guard not in paper_rule:
            raise AssertionError(f"followable_derivation_guard_missing: {guard}")

    # Manuscript regression: internal reader-audit language must not leak into
    # evaluator-visible prose; physical equations need an explicit source
    # chain; multi-file LaTeX body ownership follows first-level headings.
    for guard in [
        "论文正文元话语禁令",
        "对普通读者而言",
        "审计工具不入正文",
        "物理模型另加“来源逐项落地”检查",
        "不得从坐标图直接跳到质量阵",
        "LaTeX正文按一级标题拆分合同",
        "一个body文件不得包含两个不同的一级标题",
        "同一一级标题也不得跨多个body文件拼接",
    ]:
        if guard not in paper_rule and guard not in (
            Path(__file__).resolve().parents[1] / "rules/17-reader-first-manuscript-audit.md"
        ).read_text(encoding="utf-8"):
            raise AssertionError(f"manuscript_reader_structure_guard_missing: {guard}")

    controller = (
        Path(__file__).resolve().parents[1] / "SKILL.md"
    ).read_text(encoding="utf-8")
    for guard in [
        "Every manuscript mutation round",
        "read every rule listed in the manuscript drafting, revision, or content audit row completely",
        "A previous round's or previous window's read",
        "pre-mutation propagation matrix",
    ]:
        if guard not in controller:
            raise AssertionError(f"each_round_manuscript_read_guard_missing: {guard}")

    registry = json.loads((
        Path(__file__).resolve().parents[1] / "references/routing-registry.json"
    ).read_text(encoding="utf-8"))
    manuscript_route = next(
        item for item in registry["triggers"] if item["trigger_id"] == "TR-MANUSCRIPT"
    )
    expected_manuscript_rules = {
        "rules/03-paper-content-rules.md", "rules/06-weiwei-norms.md",
        "rules/13-excellent-paper-expression.md", "rules/17-reader-first-manuscript-audit.md",
        "rules/20-execution-gates.md", "rules/21-global-manuscript-acceptance.md",
        "rules/22-front-matter-acceptance.md", "rules/23-background-analysis-acceptance.md",
        "rules/24-assumptions-data-acceptance.md", "rules/25-model-results-acceptance.md",
        "rules/26-conclusion-references-acceptance.md", "rules/33-manuscript-minimum.md",
    }
    actual_manuscript_rules = set(manuscript_route["required_rules"])
    if actual_manuscript_rules != expected_manuscript_rules:
        raise AssertionError(
            "manuscript_required_rule_set_mismatch: "
            f"expected={sorted(expected_manuscript_rules)} actual={sorted(actual_manuscript_rules)}"
        )

    for guard in [
        "跨章节传播矩阵",
        "问题分析只接收任务难点、数据能力、方法方向和选择理由",
        "模型评价只综合比较已证实的优点、局限和共同边界",
        "结论只回收逐问答案、最低必要证据、成立条件和适用边界",
        "传播审计直接失败",
    ]:
        if guard not in paper_rule:
            raise AssertionError(f"cross_section_propagation_guard_missing: {guard}")

    uncertainty_rule = (
        Path(__file__).resolve().parents[1] / "rules/36-uncertainty-error-analysis.md"
    ).read_text(encoding="utf-8")
    verification_rule = (
        Path(__file__).resolve().parents[1] / "rules/32-verification-minimum.md"
    ).read_text(encoding="utf-8")

    for guard in [
        "S6双轴最低合同", "V3没有`not_triggered`状态",
        "每一问至少展示一项", "engineering checks do not satisfy",
    ]:
        if guard not in verification_rule:
            raise AssertionError(f"s6_dual_axis_guard_missing: {guard}")

    for guard in [
        "每问至少一项实质模型检验", "灵敏度分析不是固定必选项",
        "内部哈希、字段对账、再次代入同一公式", "模型评价章节也不能替代",
    ]:
        if guard not in paper_rule:
            raise AssertionError(f"paper_model_examination_guard_missing: {guard}")

    for guard in [
        "V3不得记为`not_triggered`", "V4记为`not_triggered`",
        "不得用代码同值、数值误差界",
    ]:
        if guard not in uncertainty_rule:
            raise AssertionError(f"s6_v3_v4_boundary_guard_missing: {guard}")
    for guard in [
        "共享基础不得替代逐问闭环",
        "删除共享章节标题检查",
        "优化模型的语义闭合与自然展开门",
        "标签只是导航，不是合格证",
        "删除标签检查和重复信息检查",
        "求解叙述的数学主线门",
        "不为满足格式另造无公式",
        "不是按“每步一式”配额组织",
        "编号能帮助复述时",
        "不把全部操作拼成冗长的自造算法名",
        "面向普通评审的算法回放门",
        "时间积分或动力学推进",
        "周期射击或边值闭合",
        "参数搜索或优化",
        "解析寻优",
        "只写“采用某求解器/智能算法得到结果”",
    ]:
        if guard not in paper_rule:
            raise AssertionError(f"algorithm_replay_guard_missing: {guard}")

    for guard in [
        "误差与灵敏度的方法—数理关系门",
        "不把“工具”作为机械标签",
        "不得用相对同值差伪装成离散误差",
        "明确记为`unresolved`并收缩声明",
    ]:
        if guard not in uncertainty_rule:
            raise AssertionError(f"uncertainty_visible_evidence_guard_missing: {guard}")

    pipeline_rule = (
        Path(__file__).resolve().parents[1] / "rules/15-pipeline-methodology.md"
    ).read_text(encoding="utf-8")
    for guard in ["本文件维护阶段、依赖、回退、逐问闭环和变更传播", "典型传播"]:
        if guard not in pipeline_rule:
            raise AssertionError(f"propagation_owner_guard_missing: {guard}")

    # V6 P0: valid end receipts must be checked by their own contract.
    end_receipt = {
        "receipt_kind": "end", "task": "bounded maintenance",
        "outputs": ["skills/SKILL.md"], "verification": ["tests passed"],
        "state_closures": [], "decisions": [], "affected_downstream": [],
        "unresolved": [], "completion_scope": "local", "status": "complete",
        "artifact_disposition": [{
            "content": "bounded maintenance report", "disposition": "no_project_artifact",
            "artifact_class": "not_applicable",
            "path": "", "realized": False, "authority_status": "not_applicable",
            "evidence": "test fixture intentionally produces no project artifact",
        }],
    }
    expect_valid("valid_end_receipt", validate_receipt(end_receipt))

    # V6 P0: component states are authoritative; the summary is derived.
    component_state = {
        "schema_version": "2.0",
        "components": {
            "q1": {"stage": "S6_VERIFY", "status": "complete"},
            "q2": {"stage": "S1_INTERPRET", "status": "in_progress"},
            "delivery": {"stage": "S7_PUBLISH", "status": "not_started"},
        },
        "project_summary": {"earliest_open_state": "S1_INTERPRET"},
    }
    expect_valid("component_state_summary", validate_project_state(component_state))
    wrong_summary = json.loads(json.dumps(component_state))
    wrong_summary["project_summary"]["earliest_open_state"] = "S6_VERIFY"
    expect_invalid("component_state_summary_mismatch", validate_project_state(wrong_summary))

    # V6 P0: an unchanged, same-session checkpoint uses R0 without a full manifest.
    incremental = {
        "receipt_kind": "start", "task": "continue same session", "scope": ".",
        "components": ["q1"], "state_before": "known current session",
        "earliest_open_state": "S6_VERIFY", "required_inputs": [],
        "routed_rules": [], "allowed_actions": ["read"],
        "prohibited_actions": ["unapproved mutation"],
        "recovery_level": "R0_INCREMENTAL_CHECKPOINT",
        "full_read_gate": "not_triggered", "recovery_evidence": {
            "checkpoint_identity": "same-session-1", "changed_paths": []
        },
        "decisions_required": [], "implementation_allowed": False,
        "substantive_analysis": False,
        "artifact_plan": [{
            "content": "same-session status read", "disposition": "no_project_artifact",
            "artifact_class": "not_applicable",
            "path": "", "promotion_requires": "none",
            "reason": "no reusable analysis is formed",
        }],
    }
    expect_valid("r0_incremental_checkpoint", validate_receipt(incremental))

    # A substantive task card may not remain only in chat.  It must plan a
    # provisional or stronger artifact before the turn proceeds.
    substantive_without_artifact = json.loads(json.dumps(incremental))
    substantive_without_artifact["substantive_analysis"] = True
    expect_invalid(
        "substantive_analysis_without_artifact",
        validate_receipt(substantive_without_artifact),
    )
    substantive_with_artifact = json.loads(json.dumps(incremental))
    substantive_with_artifact["substantive_analysis"] = True
    substantive_with_artifact["artifact_plan"] = [{
        "content": "question interpretation task card", "disposition": "provisional",
        "artifact_class": "analysis_candidate",
        "path": "planning/analysis/q1_task_card.md",
        "promotion_requires": "explicit user approval",
        "reason": "the interpretation is reusable but not yet authoritative",
    }]
    expect_valid(
        "substantive_analysis_with_provisional_artifact",
        validate_receipt(substantive_with_artifact),
    )

    # V7 artifact classes keep planning, technical docs, and paper delivery in
    # separate permission lanes. docs must not regain a manuscript-draft role.
    rejected_docs_draft = {
        "earliest_open_state": "S6_VERIFY", "manuscript_mutation": True,
        "substantive_analysis": True,
        "artifact_plan": [{
            "content": "question paper draft", "disposition": "provisional",
            "artifact_class": "manuscript_draft", "path": "docs/q1/paper_draft.md",
            "promotion_requires": "undefined after docs-role rollback",
            "reason": "regression fixture: docs cannot hold manuscript prose",
        }],
    }
    expect_invalid("docs_manuscript_draft_rejected", validate_artifact_plan(rejected_docs_draft))

    reproduction_plan = {
        "earliest_open_state": "S5_IMPLEMENT", "substantive_analysis": True,
        "artifact_plan": [{
            "content": "reproduction commands", "disposition": "current_authority",
            "artifact_class": "reproduction_document", "path": "docs/q1/reproduction.md",
            "promotion_requires": "verification of commands and environment",
            "reason": "document reproducibility without mutating manuscript prose",
        }],
    }
    expect_valid("reproduction_docs_not_manuscript", validate_artifact_plan(reproduction_plan))

    solution_brief_plan = {
        "earliest_open_state": "S6_VERIFY", "substantive_analysis": True,
        "artifact_plan": [{
            "content": "question solution explanation for teammates",
            "disposition": "current_authority", "artifact_class": "solution_brief",
            "path": "docs/q1/solution_brief.md",
            "promotion_requires": "reviewed model, results, verification, and teammate explanation",
            "reason": "communicate the completed question without creating manuscript prose",
        }],
    }
    expect_valid("s6_solution_brief_lane", validate_artifact_plan(solution_brief_plan))
    wrong_brief_path = json.loads(json.dumps(solution_brief_plan))
    wrong_brief_path["artifact_plan"][0]["path"] = "docs/q1/brief.md"
    expect_invalid("solution_brief_fixed_path", validate_artifact_plan(wrong_brief_path))
    early_brief = json.loads(json.dumps(solution_brief_plan))
    early_brief["earliest_open_state"] = "S5_IMPLEMENT"
    expect_invalid("solution_brief_requires_s6", validate_artifact_plan(early_brief))
    blurred_brief = json.loads(json.dumps(solution_brief_plan))
    blurred_brief["artifact_plan"][0]["artifact_class"] = "reproduction_document"
    expect_invalid("solution_brief_class_not_blurred", validate_artifact_plan(blurred_brief))

    formal_plan = {
        "earliest_open_state": "S6_VERIFY", "manuscript_mutation": True,
        "substantive_analysis": True,
        "artifact_plan": [{
            "content": "paper source", "artifact_class": "formal_delivery",
            "disposition": "current_authority", "path": "paper/main.tex",
            "promotion_requires": "S7 manuscript permission and human formal promotion",
            "reason": "paper is the sole manuscript workspace",
        }],
    }
    expect_invalid("s6_result_approval_not_formal_promotion", validate_artifact_plan(formal_plan))
    formal_plan["earliest_open_state"] = "S7_PUBLISH"
    expect_valid("s7_formal_delivery_lane", validate_artifact_plan(formal_plan))

    complete_with_unrealized_artifact = json.loads(json.dumps(end_receipt))
    complete_with_unrealized_artifact["artifact_disposition"] = [{
        "content": "question interpretation task card", "disposition": "provisional",
        "artifact_class": "analysis_candidate",
        "path": "planning/analysis/q1_task_card.md", "realized": False,
        "authority_status": "provisional", "evidence": "only shown in chat",
    }]
    expect_invalid(
        "complete_with_unrealized_artifact",
        validate_receipt(complete_with_unrealized_artifact),
    )

    # A manuscript round cannot inherit an old declaration or start a
    # cross-section propagation without current read evidence and rollback data.
    manuscript_round = dict(incremental)
    manuscript_round.update({
        "manuscript_mutation": True,
        "manuscript_round_id": "round-20260803-1",
        "manuscript_rule_read_evidence": [],
        "cross_section_propagation": True,
    })
    expect_invalid(
        "manuscript_round_without_current_read_evidence",
        validate_receipt(manuscript_round, Path(__file__).resolve().parents[2]),
    )
    manuscript_round["manuscript_rule_read_evidence"] = [{
        "path": "skills/rules/03-paper-content-rules.md",
        "sha256": hashlib.sha256(paper_rule.encode("utf-8")).hexdigest(),
        "line_count": len(paper_rule.splitlines()),
        "read_ranges": [[1, len(paper_rule.splitlines())]],
        "truncated": False,
    }]
    expect_invalid(
        "cross_section_propagation_without_matrix_or_baseline",
        validate_receipt(manuscript_round, Path(__file__).resolve().parents[2]),
    )
    manuscript_round["propagation_matrix"] = "planning/audits/round-matrix.md"
    manuscript_round["pre_mutation_baseline"] = "sha256:baseline"
    expect_valid(
        "current_round_read_and_propagation_evidence",
        validate_receipt(manuscript_round, Path(__file__).resolve().parents[2]),
    )

    expect_invalid("rubric_to_model_jump", validate_decision(decision(
        necessity="not_assessed", options=["major_change"],
        approval="not_requested", scope=None, allowed=True,
    )))
    expect_invalid("continue_is_not_approval", validate_decision(decision(
        necessity="necessary", options=["keep_current", "major_change"],
        approval="awaiting", scope=None, allowed=True,
    )))
    expect_invalid("verified_candidate_not_auto_promoted", validate_decision(decision(
        necessity="necessary", options=["major_change"],
        approval="approved", scope="candidate", allowed=True,
    )))
    expect_valid("explicit_scoped_approval", validate_decision(decision(
        necessity="necessary", options=["keep_current", "major_change"],
        approval="approved", scope="Q1 sensitivity only", allowed=True,
    )))

    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "project"
        root.mkdir()
        (root / "a.md").write_text("one\ntwo\n", encoding="utf-8")
        (root / "copy.md").write_text("one\ntwo\n", encoding="utf-8")
        path, manifest = complete_manifest(root)
        valid = recovery_receipt(root, path, manifest)
        expect_valid("valid_recovery_closure", validate_receipt(valid, root))

        # R1 proves unchanged items from the complete baseline and reads only the live delta.
        baseline_path = path
        (root / "new.md").write_text("delta\n", encoding="utf-8")
        delta_manifest = inventory(root)
        changed_item = next(item for item in delta_manifest["files"] if item["path"] == "new.md")
        changed_item["inspection"] = {
            "status": "complete", "truncated": False, "read_ranges": [[1, 1]],
        }
        delta_path = base / "delta_manifest.json"
        delta_path.write_text(json.dumps(delta_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        r1 = {
            "receipt_kind": "start", "task": "recover changed files", "scope": ".",
            "components": ["project"], "state_before": "verified baseline",
            "earliest_open_state": "S1_INTERPRET", "required_inputs": [],
            "routed_rules": [], "allowed_actions": ["read"],
            "prohibited_actions": ["unapproved mutation"],
            "recovery_level": "R1_HASH_DELTA_RECOVERY", "full_read_gate": "closed",
            "recovery_evidence": {
                "baseline_manifest_path": baseline_path.as_posix(),
                "baseline_manifest_sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
                "delta_manifest_path": delta_path.as_posix(),
                "delta_manifest_sha256": hashlib.sha256(delta_path.read_bytes()).hexdigest(),
                "changed_paths": ["new.md"],
            },
            "decisions_required": [], "implementation_allowed": False,
            "substantive_analysis": False,
            "artifact_plan": [{
                "content": "hash-delta recovery", "disposition": "no_project_artifact",
                "artifact_class": "not_applicable",
                "path": "", "promotion_requires": "none",
                "reason": "test fixture keeps manifests external",
            }],
        }
        expect_valid("r1_verified_hash_delta", validate_receipt(r1, root))
        wrong_delta = json.loads(json.dumps(r1))
        wrong_delta["recovery_evidence"]["changed_paths"] = []
        expect_invalid("r1_changed_paths_mismatch", validate_receipt(wrong_delta, root))
        (root / "new.md").unlink()

        custom = dict(valid)
        custom["full_read_gate"] = "closed_by_prior_audit"
        expect_invalid("custom_gate_value", validate_receipt(custom, root))

        missing = dict(valid)
        missing.pop("recovery_evidence")
        expect_invalid("closed_without_evidence", validate_receipt(missing, root))

        mismatch = json.loads(json.dumps(valid))
        mismatch["recovery_evidence"]["completed_canonical_count"] += 1
        expect_invalid("count_mismatch", validate_receipt(mismatch, root))

        open_mutation = dict(valid)
        open_mutation["full_read_gate"] = "in_progress"
        open_mutation["implementation_allowed"] = True
        open_mutation["allowed_actions"] = ["read", "modify_project"]
        expect_invalid("s0_mutation", validate_receipt(open_mutation, root))

        truncated_manifest = json.loads(json.dumps(manifest))
        canonical = next(
            item for item in truncated_manifest["files"] if item["duplicate_of"] is None
        )
        canonical["inspection"]["truncated"] = True
        path.write_text(
            json.dumps(truncated_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        truncated = recovery_receipt(root, path, truncated_manifest)
        expect_invalid("truncated_output", validate_receipt(truncated, root))

        path, manifest = complete_manifest(root)
        unresolved_manifest = json.loads(json.dumps(manifest))
        unresolved_manifest["unresolved"] = [{"path": "unknown.bin"}]
        path.write_text(
            json.dumps(unresolved_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        unresolved = recovery_receipt(root, path, unresolved_manifest)
        unresolved["recovery_evidence"]["unresolved_count"] = 1
        expect_invalid("unresolved_item", validate_receipt(unresolved, root))

        path, manifest = complete_manifest(root)
        stale = recovery_receipt(root, path, manifest)
        (root / "new.md").write_text("new\n", encoding="utf-8")
        expect_invalid("stale_inventory", validate_receipt(stale, root))

    print("PASS: behavioral permission, receipt, artifact-disposition, component-state, recovery, derivation, reader-meta-language, body-split, each-round-read, structure-propagation, and algorithm-replay regressions")


if __name__ == "__main__":
    main()
