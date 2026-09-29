#!/usr/bin/env python3
"""Structurally audit one canonical per-question teammate solution brief.

This helper checks only observable carrier rules.  Mathematical correctness,
identity freshness, claim boundaries, and actual human understanding remain
manual S6-closure obligations.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


EXPECTED_SECTIONS = [
    "1 问题重述",
    "2 问题分析",
    "3 模型假设",
    "4 主要符号说明",
    "5 模型建立",
    "6 模型求解",
    "7 模型结果",
    "8 模型检验与敏感性分析",
    "9 模型评价",
]
COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
TITLE_RE = re.compile(r"^# 问题\S+：.+模型的建立与求解\s*$")
CONCLUSION_RE = re.compile(r"^10 问题\S+结论$")
TEXT_FENCE_RE = re.compile(r"```text\s*\n(.*?)\n```", re.DOTALL)
FORMULA_LABEL_RE = re.compile(r"（(\d+)）\s*$")
WORKFLOW_LINE_RE = re.compile(
    r"(?im)^(?:status|state|spec_id|result_id|run_id|next_action|todo)\s*[:：]"
)
WORKFLOW_HEADING_RE = re.compile(
    r"(?im)^#{1,6}\s*(?:\d+\s+)?(?:当前状态|工作流状态|复现入口|运行命令|代码与产物|"
    r"队友必须复述|贯穿全文定位|统一全文主线|安全声明|下一步|TODO)\s*$"
)


def audit_text(text: str) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    lines = text.splitlines()
    h1 = [(index + 1, line) for index, line in enumerate(lines) if line.startswith("# ")]
    if len(h1) != 1:
        errors.append(f"main_title_count:{len(h1)}")
    elif not TITLE_RE.fullmatch(h1[0][1]):
        errors.append(f"main_title_invalid:line={h1[0][0]}")

    h2 = [
        (index + 1, line[3:].strip())
        for index, line in enumerate(lines)
        if line.startswith("## ")
    ]
    headings = [heading for _, heading in h2]
    if len(headings) != 10:
        errors.append(f"second_level_section_count:{len(headings)}")
    for index, expected in enumerate(EXPECTED_SECTIONS):
        actual = headings[index] if index < len(headings) else None
        if actual != expected:
            errors.append(
                f"section_heading_mismatch:{index + 1}:expected={expected}:actual={actual}"
            )
    if len(headings) < 10 or not CONCLUSION_RE.fullmatch(headings[9]):
        actual = headings[9] if len(headings) >= 10 else None
        errors.append(f"section_heading_mismatch:10:actual={actual}")

    for index, (line_number, _) in enumerate(h2[:10]):
        end = h2[index + 1][0] - 1 if index + 1 < len(h2) else len(lines)
        body = "\n".join(lines[line_number:end]).strip()
        visible = re.sub(r"[#|`*:_\-\s]", "", body)
        if len(visible) < 12:
            errors.append(f"section_body_too_short:{index + 1}")

    if WORKFLOW_LINE_RE.search(text):
        errors.append("workflow_metadata_line_in_main_brief")
    if WORKFLOW_HEADING_RE.search(text):
        errors.append("workflow_heading_in_main_brief")
    if ".modeling/state.json" in text or ("九项" in text and "复述" in text):
        errors.append("workflow_or_nine_item_checklist_in_main_brief")

    formula_blocks = TEXT_FENCE_RE.findall(text)
    formula_numbers = [
        int(match.group(1))
        for block in formula_blocks
        for line in block.splitlines()
        if (match := FORMULA_LABEL_RE.search(line)) is not None
    ]
    if not formula_numbers:
        errors.append("numbered_text_formula_missing")
    elif formula_numbers[0] != 1 or any(
        right <= left for left, right in zip(formula_numbers, formula_numbers[1:])
    ):
        errors.append("formula_labels_not_strictly_increasing_from_one")
    formula_number_gaps = (
        sorted(set(range(1, formula_numbers[-1] + 1)) - set(formula_numbers))
        if formula_numbers
        else []
    )

    evidence = {
        "main_title_count": len(h1),
        "second_level_headings": headings,
        "numbered_formula_count": len(formula_numbers),
        "formula_numbers": formula_numbers,
        "formula_number_gaps_for_manual_review": formula_number_gaps,
        "manual_review_required": [
            "formula_objects_symbols_ranges_units_roles_and_claim_limits_are_explained_locally",
            "results_match_current_frozen_outputs_and_explain_conditions_mechanisms_and_boundaries",
            "verification_separates_internal_independent_structural_robustness_and_reality_checks",
            "a_human_read_this_exact_file_and_can_restate_object_mechanism_evidence_conclusion_boundary",
        ],
    }
    return evidence, sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--component-id", required=True)
    args = parser.parse_args()
    errors: list[str] = []
    evidence: dict[str, Any] = {}
    if not COMPONENT_RE.fullmatch(args.component_id):
        errors.append("component_id_noncanonical")
        path = args.project_root / "docs" / "invalid" / "solution_brief.md"
    else:
        path = args.project_root / "docs" / args.component_id / "solution_brief.md"
    if not path.is_file():
        errors.append("canonical_brief_missing")
    else:
        try:
            evidence, text_errors = audit_text(path.read_text(encoding="utf-8"))
            errors.extend(text_errors)
        except UnicodeDecodeError:
            errors.append("canonical_brief_not_utf8")
    result = {
        "schema_version": "16.0",
        "status": "pass" if not errors else "fail",
        "component_id": args.component_id,
        "canonical_path": (
            f"docs/{args.component_id}/solution_brief.md"
            if COMPONENT_RE.fullmatch(args.component_id)
            else None
        ),
        "evidence": evidence,
        "errors": sorted(set(errors)),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
