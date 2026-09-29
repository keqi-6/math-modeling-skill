#!/usr/bin/env python3
"""Turn a raw Skill-maintenance request into a conservative, auditable draft."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from lib_v10 import SKILL_ROOT, json_output, load_rules


RULE_ID_PATTERN = r"[A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+)+"
RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4}


def rule_behavior(rule: dict[str, Any]) -> str | None:
    """Return the maintained human-facing behavior field across schema revisions."""
    value = rule.get("instruction_gloss", rule.get("instruction"))
    return value if isinstance(value, str) else None


def rule_sha256(rule: dict[str, Any]) -> str:
    canonical = {key: value for key, value in rule.items() if key != "_bundle"}
    payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def tokens(text: str) -> set[str]:
    lowered = text.lower()
    result = set(re.findall(r"[a-z][a-z0-9_-]{2,}", lowered))
    for segment in re.findall(r"[\u4e00-\u9fff]+", lowered):
        result.update(segment[index:index + 2] for index in range(max(0, len(segment) - 1)))
    return result


def without_negated_actions(request: str) -> str:
    """Remove only local action negations so '不要删除，只新增' is not a retirement."""
    patterns = [
        r"(?:不要|禁止|不应|无需|无须|别|不)\s*(?:新增|增加|添加|废弃|删除|移除|修改|更新)(?:\s*(?:或|和|、|也不|且不)\s*(?:新增|增加|添加|废弃|删除|移除|修改|更新))+",
        r"(?:不要|不再|无需|无须|别|禁止|不应)\s*(?:再\s*)?(?:废弃|删除|移除|新增|增加|添加|修改|更新|发布|升级)",
        r"(?:^|(?<=[，,；;。.!！?？\s]))不\s*(?:废弃|删除|移除|新增|增加|添加|修改|更新|发布|升级)",
        r"(?:do\s+not|don't|never)\s+(?:add|retire|remove|delete|modify|update)(?:\s+(?:or|and)\s+(?:add|retire|remove|delete|modify|update))+",
        r"(?:do\s+not|don't|never)\s+(?:retire|remove|delete|add|modify|update|release|upgrade)",
        r"(?:不|并不)\s*(?:改变|涉及)\s*(?:路由|状态机|权限|授权|schema|契约)",
    ]
    result = request
    for pattern in patterns:
        result = re.sub(pattern, " ", result, flags=re.IGNORECASE)
    return result


def detected_operations(request: str) -> list[str]:
    effective = without_negated_actions(request)
    found: list[str] = []
    patterns = {
        "add": r"新增|增加|添加|add|new\s+rule",
        "retire": r"废弃|删除|移除|retire|remove|delete",
        "modify": r"修改|更新|改写|调整|合并|拆分|modify|update|merge|split",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, effective, flags=re.IGNORECASE):
            found.append(name)
    return found or ["modify"]


def operation(request: str) -> str:
    operations = detected_operations(request)
    return operations[0] if len(operations) == 1 else "ambiguous"


def risk(request: str) -> tuple[str, list[str]]:
    """Preliminary request risk; apply_rule_change recomputes the binding minimum from the diff."""
    effective = without_negated_actions(request)
    surfaces = []
    patterns = {
        "authorization": r"权限|授权|只读|写入|permission|authorization",
        "routing": r"路由|触发|分类|route|routing|trigger",
        "state_machine": r"状态机|状态迁移|s[0-7]|d[0-3]|a[0-3]|state\s+machine|transition",
        "maintenance_kernel": r"维护内核|owner|发布门禁|maintenance\s+kernel|release\s+gate",
        "schema": r"schema|契约|字段|contract",
        "script": r"脚本|解析器|校验器|script|resolver|validator",
        "domain_rule": r"数据|模型|验证|论文|图表|文献|交付|data|model|verification|manuscript|visual|literature|delivery",
        "clarification": r"澄清|说明|示例|引用|上下文|clarif|example|reference|context",
        "nonnormative": r"错别字|拼写|标点|格式|gloss|failure.?example|typo|spelling|punctuation|formatting",
    }
    for surface, pattern in patterns.items():
        if re.search(pattern, effective, flags=re.IGNORECASE):
            surfaces.append(surface)
    if "maintenance_kernel" in surfaces:
        return "L4", surfaces
    if set(surfaces) & {"authorization", "state_machine", "schema", "script"}:
        return "L3", surfaces
    if "nonnormative" in surfaces and not set(surfaces) & {"routing", "clarification"}:
        return "L0", surfaces
    if "clarification" in surfaces and "routing" not in surfaces:
        return "L1", surfaces
    if "routing" in surfaces or "domain_rule" in surfaces or re.search(r"规则|rule", effective, flags=re.IGNORECASE):
        return "L2", surfaces
    return "L0", surfaces


def rank_rules(request: str, rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    request_tokens = tokens(request)
    explicit_ids = set(re.findall(RULE_ID_PATTERN, request.upper()))
    ranked = []
    for rule in rules:
        behavior = rule_behavior(rule) or ""
        failure = str(rule.get("failure_example", rule.get("forbidden", "")))
        haystack = " ".join([
            rule["id"], rule["capability"], rule["semantic_key"], behavior,
            failure, str(rule["effect"]), " ".join(rule["trigger"]["events"]),
        ])
        overlap = request_tokens & tokens(haystack)
        score = len(overlap) / max(1, len(request_tokens))
        explicit = rule["id"] in explicit_ids
        if explicit:
            score += 10
        if score > 0:
            ranked.append({
                "rule_id": rule["id"], "owner": rule["owner"], "capability": rule["capability"],
                "revision": rule["revision"], "rule_sha256": rule_sha256(rule),
                "score": round(score, 4), "explicit_id_match": explicit,
                "matched_tokens": sorted(overlap)[:20],
                "old_effect": rule["effect"], "old_behavior": behavior,
                "old_trigger": rule["trigger"], "old_exceptions": rule["exceptions"],
            })
    return sorted(ranked, key=lambda item: (-item["score"], item["rule_id"]))[:12]


def impact(candidates: list[dict[str, Any]], rules: list[dict[str, Any]], level: str, surfaces: list[str]) -> dict[str, Any]:
    """Compute a conservative relationship closure, not merely the edited filename."""
    by_id = {rule["id"]: rule for rule in rules}
    selected = {item["rule_id"] for item in candidates[:5]}
    capabilities = {item["capability"] for item in candidates[:5]}
    relation_fields = ("conflicts_with", "supersedes", "refines", "depends_on")
    changed = True
    while changed:
        changed = False
        for rule in rules:
            relations = {
                related
                for field in relation_fields
                for related in rule.get(field, [])
                if isinstance(related, str)
            }
            reverse_hit = bool(relations & selected)
            forward_hit = rule["id"] in selected
            capability_hit = rule["capability"] in capabilities
            if not (reverse_hit or forward_hit or capability_hit):
                continue
            before = len(selected)
            selected.add(rule["id"])
            selected.update(item for item in relations if item in by_id)
            capabilities.add(rule["capability"])
            changed = changed or len(selected) != before

    route_ids: set[str] = set()
    test_ids: set[str] = set()
    edges: list[dict[str, str]] = []
    for rule_id in sorted(selected):
        rule = by_id[rule_id]
        route_ids.update(rule["routes"])
        test_ids.update(rule["tests"])
        edges.append({"from": rule_id, "to": rule["owner"], "kind": "owned_by"})
        edges.extend({"from": rule_id, "to": route, "kind": "selected_by"} for route in rule["routes"])
        edges.extend({"from": rule_id, "to": test, "kind": "tested_by"} for test in rule["tests"])
        for relation_field in relation_fields:
            edges.extend(
                {"from": rule_id, "to": other, "kind": relation_field}
                for other in rule.get(relation_field, [])
            )

    contract_files = []
    if "routing" in surfaces:
        contract_files.append("references/route-contract.json")
    if "state_machine" in surfaces:
        contract_files.extend(["references/state-machine.json", "references/state.schema.json"])
    if "authorization" in surfaces:
        contract_files.extend(["SKILL.md", "references/route-contract.json"])
    if "schema" in surfaces:
        contract_files.extend(["references/rule-atom.schema.json", "references/receipt.schema.json"])
    if level in {"L3", "L4"}:
        contract_files.append("scripts/validate_release.py")
    return {
        "rules": sorted(selected), "capabilities": sorted(capabilities), "routes": sorted(route_ids),
        "tests": sorted(test_ids), "contracts": sorted(set(contract_files)), "edges": edges,
    }


def analyze(request: str, root: Path) -> dict[str, Any]:
    rules, _ = load_rules(root)
    candidates = rank_rules(request, rules)
    existing_ids = {rule["id"] for rule in rules}
    explicit_ids = sorted(set(re.findall(RULE_ID_PATTERN, request.upper())))
    level, surfaces = risk(request)
    operations = detected_operations(request)
    op = operations[0] if len(operations) == 1 else "ambiguous"
    top = candidates[0] if candidates else None
    exact = bool(top and top["explicit_id_match"])
    confident = bool(top and (top["score"] >= 0.20) and (len(candidates) == 1 or top["score"] - candidates[1]["score"] >= 0.03))
    if op == "ambiguous":
        status = "needs_operation_decomposition"
    elif op == "add":
        if len(explicit_ids) != 1:
            status = "needs_new_rule_identity"
        elif explicit_ids[0] in existing_ids:
            status = "add_target_exists"
        else:
            status = "ready_for_envelope"
    elif len(explicit_ids) > 1:
        status = "needs_target"
    elif top is None or not (exact or confident):
        status = "needs_target"
    else:
        status = "ready_for_envelope"
    required_test_kinds = ["positive", "near_negative", "conflict", "state_binding"]
    if op == "retire":
        required_test_kinds = ["retirement", "near_negative", "conflict"]
    draft_target = top
    draft_rule_id = top["rule_id"] if top else "<EXISTING.RULE.ID>"
    if op == "add":
        draft_target = None
        draft_rule_id = explicit_ids[0] if len(explicit_ids) == 1 and explicit_ids[0] not in existing_ids else "<NEW.RULE.ID>"
    return {
        "schema_version": "10.0",
        "status": status,
        "request": request,
        "classification": {
            "operation": op, "detected_operations": operations,
            "preliminary_risk": level, "surfaces": surfaces,
            "binding_risk_note": "apply_rule_change recomputes minimum_risk from the actual before/after diff",
        },
        "owner_candidates": candidates,
        "impact": impact(candidates, rules, level, surfaces),
        "change_envelope_draft": {
            "operation": op if op != "ambiguous" else "<ONE.OPERATION>",
            "rule_id": draft_rule_id,
            "request": request,
            "old_behavior": draft_target["old_behavior"] if draft_target else None,
            "new_behavior": None if op == "retire" else "<observable behavior after change>",
            "trigger": draft_target["old_trigger"] if draft_target else {"events": ["<event>"], "predicates": []},
            "exceptions": draft_target["old_exceptions"] if draft_target else [],
            "risk": level,
            "expected_owner": draft_target["owner"] if draft_target else None,
            "expected_revision": draft_target["revision"] if draft_target else None,
            "expected_rule_sha256": draft_target["rule_sha256"] if draft_target else None,
            "impact_analysis_required": (
                "after patch and behavior tests are complete, run "
                "apply_rule_change.py --prepare-impact against the immutable base"
            ),
            "behavior_tests_required": required_test_kinds,
        },
        "next_step": (
            "resolve one operation and one canonical owner, complete the patch and behavior tests, "
            "then generate the exact pre-write impact proof against an isolated staging clone"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    args = parser.parse_args()
    result = analyze(args.request, args.root.resolve())
    json_output(result)
    return 0 if result["status"] == "ready_for_envelope" else 2


if __name__ == "__main__":
    raise SystemExit(main())
