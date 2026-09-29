#!/usr/bin/env python3
"""Exercise the V16 canonical teammate-brief format and S6 selection boundary."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

from lib_v11 import resolve
from run_v16_gate_scenarios import create_project, write_json
from validate_teammate_brief import EXPECTED_SECTIONS, audit_text


def errors_of(result: dict[str, Any]) -> list[str]:
    return [
        reason
        for item in result.get("reasons", [])
        for reason in item.get("reasons", [])
    ]


def fixture_text() -> str:
    bodies = {
        "1 问题重述": "本问需要在给定条件下确定决策变量，并明确研究对象和回答范围。",
        "2 问题分析": "难点是把现实对象映射为可计算关系，并避免把求解输出当成现实真值。",
        "3 模型假设": "假设输入在本次决策周期内稳定；若条件变化，结论需要重新评估。",
        "4 主要符号说明": "下表索引跨节使用的主要符号；每个公式附近仍会解释局部含义。\n\n| 符号 | 含义 | 单位 |\n|---|---|---|\n| x | 决策量 | 件 |",
        "5 模型建立": "定义决策量 x 和结果 y，建立当前示例的基本计算关系。\n\n```text\ny = x + 1。 （1）\n```\n\n式（1）中，x 是非负整数决策量，y 是对应结果；该式只描述模型内关系。",
        "6 模型求解": "枚举允许的 x，逐一计算 y，并按预先规定的目标排序；候选耗尽后停止。",
        "7 模型结果": "在演示条件下得到当前方案；该数值只用于结构测试，不形成外部事实。",
        "8 模型检验与敏感性分析": "分别进行手算、独立复算、边界检查和参数扰动，并限制结论范围。",
        "9 模型评价": "模型结构透明且便于复核，但示例关系简单，不能外推到未建模对象。",
    }
    parts = ["# 问题一：演示决策模型的建立与求解"]
    for heading in EXPECTED_SECTIONS:
        parts.extend([f"## {heading}", bodies[heading]])
    parts.extend([
        "## 10 问题一结论",
        "本问在既定候选域内给出可复核方案；超出假设范围时不得沿用该结论。",
    ])
    return "\n\n".join(parts) + "\n"


def brief_plan(path: str) -> dict[str, Any]:
    return {
        "schema_version": "11.0",
        "plan_id": "v16-teammate-brief-g1",
        "request": "为第一问写队友讲解稿。",
        "steps": [{
            "id": "brief",
            "tier": "G1_WORKING",
            "mode": "mutate",
            "object": "model",
            "action": "prepare_teammate_brief",
            "component_id": "q1",
            "working_context": {"component_type": "question", "state": "S6"},
            "events": ["teammate_brief_write"],
            "facts": {},
            "depends_on": [],
            "change_set": {
                "paths": [path],
                "facets": ["technical_handoff"],
                "claim_refs": [],
            },
        }],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    cases: list[dict[str, str]] = []

    def record(identifier: str, passed: bool, detail: str) -> None:
        cases.append({
            "id": identifier,
            "status": "pass" if passed else "fail",
            "detail": detail,
        })

    canonical = resolve(brief_plan("docs/q1/solution_brief.md"), None, root)
    canonical_step = canonical.get("steps", [{}])[0]
    record(
        "BEH.V16.TEAMMATE_BRIEF.G1.CANONICAL_PATH",
        canonical.get("status") == "resolved"
        and canonical.get("route_ids") == ["RT.MODEL.RESULTS"]
        and "MOD.RESULTS.TEAMMATE_BRIEF" in canonical_step.get("rule_ids", [])
        and canonical_step.get("component_ids") == ["q1"],
        json.dumps({
            "status": canonical.get("status"),
            "errors": errors_of(canonical),
            "rules": canonical_step.get("rule_ids", []),
        }, ensure_ascii=False, sort_keys=True),
    )

    wrong = resolve(brief_plan("docs/q1/solution-brief.md"), None, root)
    wrong_errors = errors_of(wrong)
    record(
        "BEH.V16.TEAMMATE_BRIEF.G1.WRONG_PATH.REJECTED",
        wrong.get("status") == "blocked"
        and "action_required_change_path_missing:docs/q1/solution_brief.md" in wrong_errors,
        json.dumps(wrong_errors, ensure_ascii=False, sort_keys=True),
    )

    structure_evidence, structure_errors = audit_text(fixture_text())
    record(
        "BEH.V16.TEAMMATE_BRIEF.STRUCTURE.TEN_SECTION",
        not structure_errors
        and structure_evidence.get("numbered_formula_count") == 1
        and len(structure_evidence.get("second_level_headings", [])) == 10,
        json.dumps({
            "errors": structure_errors,
            "headings": structure_evidence.get("second_level_headings"),
        }, ensure_ascii=False, sort_keys=True),
    )

    checklist = fixture_text().replace(
        "## 10 问题一结论",
        "## 10 队友必须复述\n\n本节列出九项复述清单。\n\n## 11 问题一结论",
    )
    _, checklist_errors = audit_text(checklist)
    record(
        "BEH.V16.TEAMMATE_BRIEF.STRUCTURE.NINE_ITEM.REJECTED",
        "second_level_section_count:11" in checklist_errors
        and "workflow_heading_in_main_brief" in checklist_errors
        and "workflow_or_nine_item_checklist_in_main_brief" in checklist_errors,
        json.dumps(checklist_errors, ensure_ascii=False, sort_keys=True),
    )

    meta_narrative = fixture_text().replace(
        "## 3 模型假设",
        "## 贯穿全文定位\n\n本节把多问统一方法另列为元叙事。\n\n"
        "## 安全声明\n\n本节集中堆放与具体结论脱节的防御性声明。\n\n## 3 模型假设",
    )
    _, meta_errors = audit_text(meta_narrative)
    record(
        "BEH.V16.TEAMMATE_BRIEF.STRUCTURE.META_OR_SAFETY_HEADING.REJECTED",
        "second_level_section_count:12" in meta_errors
        and "workflow_heading_in_main_brief" in meta_errors,
        json.dumps(meta_errors, ensure_ascii=False, sort_keys=True),
    )

    with tempfile.TemporaryDirectory(prefix="v16-teammate-brief-") as raw:
        project = create_project(Path(raw))
        state_path = project / ".modeling/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["components"]["Q1"]["state"] = "S6"
        state["components"]["Q1"]["status"] = "active"
        write_json(state_path, state)
        close_plan = {
            "schema_version": "11.0",
            "plan_id": "v16-teammate-brief-s6-close",
            "request": "核对当前讲解稿的人类理解门并关闭第一问 S6。",
            "window_context": "same_window",
            "steps": [{
                "id": "close",
                "tier": "G2_CHECKPOINT",
                "mode": "promote",
                "object": "verification",
                "action": "close_s6",
                "component_id": "Q1",
                "events": ["recovery_assessment", "s6_close"],
                "facts": {},
                "depends_on": [],
                "change_set": {
                    "paths": [".modeling/state.json"],
                    "facets": ["question_state"],
                    "claim_refs": [],
                },
                "state_effect": {"component_id": "Q1", "from": "S6", "to": "S7"},
            }],
        }
        close = resolve(close_plan, project, root)
        close_step = close.get("steps", [{}])[0]
        record(
            "BEH.V16.TEAMMATE_BRIEF.S6.HUMAN_GATE_SELECTED",
            close.get("status") == "resolved"
            and "MOD.RESULTS.TEAMMATE_BRIEF" in close_step.get("rule_ids", [])
            and "references/modeling-method-notes.md#results" in close_step.get("context_refs", [])
            and close_step.get("route_id") == "RT.VERIFY.S6.CLOSE",
            json.dumps({
                "status": close.get("status"),
                "errors": errors_of(close),
                "rules": close_step.get("rule_ids", []),
                "context_refs": close_step.get("context_refs", []),
            }, ensure_ascii=False, sort_keys=True),
        )

    failed = [item["id"] for item in cases if item["status"] != "pass"]
    result = {
        "schema_version": "16.0",
        "driver": "teammate_brief_scenarios",
        "status": "pass" if not failed else "fail",
        "cases": cases,
        "evidence": {"case_count": len(cases)},
        "errors": ["failed_cases:" + ",".join(failed)] if failed else [],
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
