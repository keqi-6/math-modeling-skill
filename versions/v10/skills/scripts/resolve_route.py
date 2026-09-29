#!/usr/bin/env python3
"""Resolve raw user language against real project state and return atomic rules."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from lib_v10 import (
    SKILL_ROOT, component_state_for_route, json_output, load_json, load_rules,
    load_state, route_emitted_events, selected_rules_for_routes, sha256_text,
)


def matches_any(patterns: list[str], text: str) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE)]


def classify_mode(request: str, classification: dict[str, Any]) -> tuple[str, dict[str, list[str]]]:
    hits = {
        mode: matches_any(classification["mode_patterns"].get(mode, []), request)
        for mode in classification["mode_order"]
    }
    if re.search(r"只读|不要(?:修改|写入|创建)|不(?:修改|写文件)|read.?only|do not (?:write|modify|create)", request, flags=re.IGNORECASE):
        if re.search(r"skill|技能|v10", request, flags=re.IGNORECASE):
            return "project_readonly", hits
        if re.search(r"建议|解释|方案|advice|explain", request, flags=re.IGNORECASE):
            return "advisory_readonly", hits
        return "project_readonly", hits
    skill_advice = bool(
        re.search(r"skill|技能|v\d+\s*(?:skill|技能|规则版本)", request, flags=re.IGNORECASE)
        and re.search(
            r"看看|意见|建议|方案|如何|怎么|需不需要|要不要|是否(?:需要|应该)|有没有必要|"
            r"what do you think|should we|do we need",
            request,
            flags=re.IGNORECASE,
        )
    )
    explicit_skill_change = bool(re.search(
        r"去做|执行|落地|立即|直接|开始|务必|"
        r"请.*(?:新增|增加|修改|更新|删除|废弃|合并|发布|迭代|升级)|"
        r"(?:并|然后|再|之后).*(?:新增|增加|修改|更新|删除|废弃|合并|发布|迭代|升级)|"
        r"^(?:新增|增加|修改|更新|删除|废弃|合并|发布|迭代|升级)|"
        r"(?:我要|我希望|需要你|帮我).*(?:新增|增加|修改|更新|删除|废弃|合并|发布|迭代|升级)|"
        r"do it|make the change|implement it|release it",
        request,
        flags=re.IGNORECASE,
    ))
    if skill_advice and not explicit_skill_change:
        return "advisory_readonly", hits
    if re.search(r"如何|怎么|怎样|是否|能否|可否|需不需要|要不要|how\b|should\b|do we need", request, flags=re.IGNORECASE) and not re.search(
        r"^\s*(?:请)?(?:审计|检查|核对|复核|评估|验收|验证|检验|audit|inspect|check|verify|validate|assess)",
        request,
        flags=re.IGNORECASE,
    ) and not re.search(
        r"去做|执行|落地|立即|请(?:修改|创建|实现|完成)|do it|execute|implement it", request, flags=re.IGNORECASE,
    ):
        return "advisory_readonly", hits
    if re.search(r"(?:是否|能否|可否).*(?:完成|结束)|(?:完成|结束).*(?:了吗|没有|么)|already.*(?:done|finished)", request, flags=re.IGNORECASE):
        return "advisory_readonly", hits
    if hits.get("skill_maintenance"):
        return "skill_maintenance", hits
    if hits.get("promote"):
        return "promote", hits
    if re.search(r"验证|检验|检查|审计|核验|评估|复核|verify|validate|audit|inspect|check|assess", request, flags=re.IGNORECASE) and not re.search(
        r"创建|新建|修改|改写|重写|修复|编写|撰写|实现|求解|计算|清洗|预处理|绘制|生成|重画|排版|关闭|冻结|发布|交付|执行|create|edit|fix|write|implement|solve|compute|clean|draw|release|deliver",
        request,
        flags=re.IGNORECASE,
    ):
        return "project_readonly", hits
    for mode in classification["mode_order"]:
        if hits[mode]:
            return mode, hits
    return classification["default_mode"], hits


def split_clauses(request: str, pattern: str) -> list[str]:
    action = r"审计|检查|复核|清洗|预处理|冻结|比较|选择|实现|求解|验证|撰写|修改|创建|绘制|生成|打包|交付|发布|audit|inspect|clean|freeze|compare|select|implement|solve|verify|write|edit|create|draw|generate|package|deliver|release"
    separator = rf"(?:{pattern})|(?:(?:，|,)?\s*(?:并且|同时|然后|以及|and\s+then|then)\s*)|(?:\s*并\s*(?=(?:{action})))|(?:\s+and\s+(?=(?:{action})\b))"
    clauses = [item.strip(" ，,") for item in re.split(separator, request, flags=re.IGNORECASE) if item and item.strip(" ，,")]
    if len(clauses) < 2:
        return clauses or [request]

    # Coordinated verbs often share the noun phrase that appears only once at
    # the end (for example, "clean and preprocess this dataset").  Such text is
    # one substantive clause for routing.  Clauses that each name an object
    # remain separate, so "audit data and clean data" cannot silently lose one
    # of its actions through a route exclusion.
    object_term = re.compile(
        r"项目|题目|问题|数据(?:集)?|样本|字段|模型|算法|候选|基线|结果|验证|证据|"
        r"论文|稿件|图(?:表|像)?|视觉|文件|工件|交付|发布|规则|skill|技能|"
        r"project|problem|question|data(?:set)?|sample|field|model|algorithm|candidate|baseline|result|"
        r"verification|evidence|manuscript|paper|figure|visual|file|artifact|delivery|release|rule",
        flags=re.IGNORECASE,
    )
    merged: list[str] = []
    pending = ""
    for clause in clauses:
        current = f"{pending}并{clause}" if pending else clause
        if object_term.search(current):
            merged.append(current)
            pending = ""
        else:
            pending = current
    if pending:
        if merged:
            merged[-1] = f"{merged[-1]}并{pending}"
        else:
            merged.append(pending)
    return merged


def route_candidates(
    request: str,
    mode: str,
    routes: list[dict[str, Any]],
    state: dict[str, Any] | None,
    component_id: str | None,
    component_map: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    for route in routes:
        hits = matches_any(route["patterns"], request)
        if not hits or matches_any(route.get("exclude_patterns", []), request):
            continue
        route_mode_ok = mode in route["modes"]
        mapped_component_id = (component_map or {}).get(
            route["id"], (component_map or {}).get(route["object"], component_id)
        )
        if state is not None and mapped_component_id is None and "project" in route["component_types"]:
            actual_state, component_type, component_ids = state["project"]["state"], "project", []
        else:
            actual_state, component_type, component_ids = component_state_for_route(
                state, route["component_types"], mapped_component_id
            )
        advisory_unbound = state is None and mode == "advisory_readonly" and "advisory_readonly" in route["modes"]
        if advisory_unbound:
            actual_state, component_type = "UNBOUND_ADVISORY", "none"
        state_ok = advisory_unbound or actual_state in route["states"] or "*" in route["states"]
        missing_state_write = (
            state is None
            and mode in {"mutate", "promote"}
            and route["id"] not in {"RT.PROJECT.INIT", "RT.PROJECT.RECOVER.MISSING"}
        )
        node = {
            "route": route,
            "state": actual_state,
            "component_type": component_type,
            "component_ids": component_ids,
            "component_selector": mapped_component_id,
            "matched_patterns": hits,
            "score": len(hits) * 10 + int(route.get("priority", 0)),
        }
        if route_mode_ok and state_ok and not missing_state_write:
            eligible.append(node)
        else:
            reasons = []
            if not route_mode_ok:
                reasons.append(f"mode {mode} not in {route['modes']}")
            if not state_ok:
                reasons.append(f"state {actual_state} not in {route['states']}")
            if missing_state_write:
                reasons.append("state missing for writable non-initialization route")
            blocked.append({**node, "reasons": reasons})
    return eligible, blocked


def remove_shadowed(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep distinct actions, but remove a lower-priority route with identical object/phase and overlapping intent."""
    kept: list[dict[str, Any]] = []
    for node in sorted(nodes, key=lambda item: (-item["score"], item["route"]["id"])):
        route = node["route"]
        duplicate = False
        for prior in kept:
            other = prior["route"]
            if route["object"] != other["object"] or route["phase"] != other["phase"]:
                continue
            if set(route["intents"]) & set(other["intents"]):
                duplicate = True
                break
        if not duplicate:
            kept.append(node)
    return kept


def order_nodes(nodes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    ordered = sorted(nodes, key=lambda item: (item["route"]["phase"], -item["score"], item["route"]["id"]))
    edges: list[dict[str, str]] = []
    for index, node in enumerate(ordered):
        route = node["route"]
        for previous in ordered[:index]:
            earlier = previous["route"]
            if earlier["object"] in route.get("after_objects", []) or earlier["phase"] < route["phase"]:
                edge = {"from": earlier["id"], "to": route["id"]}
                if edge not in edges:
                    edges.append(edge)
    return ordered, edges


def context_refs(request: str, nodes: list[dict[str, Any]]) -> list[str]:
    selected: list[str] = []
    for node in nodes:
        for item in node["route"].get("context_refs", []):
            terms = item.get("when_any", [])
            if not terms or any(term.lower() in request.lower() for term in terms):
                if item["ref"] not in selected:
                    selected.append(item["ref"])
    return selected


def public_node(node: dict[str, Any]) -> dict[str, Any]:
    route = node["route"]
    return {
        "id": route["id"],
        "object": route["object"],
        "intents": route["intents"],
        "state": node["state"],
        "component_type": node["component_type"],
        "component_ids": node["component_ids"],
        "component_selector": node.get("component_selector"),
        "write_policy": route["write_policy"],
        "expected_outputs": route["expected_outputs"],
        "exclusions": route["exclusions"],
        "matched_patterns": node["matched_patterns"],
        "matched_clauses": node.get("matched_clauses", []),
    }


def runtime_facts(
    request: str,
    project_root: Path | None,
    state: dict[str, Any] | None,
    ordered: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the closed fact vocabulary used by atomic trigger predicates."""
    objects = {node["route"]["object"] for node in ordered}
    facts: dict[str, Any] = {
        "project_root": str(project_root.resolve()) if project_root is not None else None,
        "frozen_decision": None,
        "ambiguity": None,
        "detected_objects": "multiple" if len(objects) > 1 else "single",
        "predictive_or_evaluative_use": bool(
            objects & {"model", "verification"}
            or re.search(r"预测|评估|拟合|分类|predict|evaluate|forecast|fit|classif", request, flags=re.IGNORECASE)
        ),
        "policy_may_change": bool(
            re.search(r"政策|规则|提交要求|官方|当前|最新|policy|official|current|latest", request, flags=re.IGNORECASE)
        ),
        "request_explicit_full_recovery": bool(
            re.search(r"完整恢复|全量恢复|从头恢复|重建全部|full\s+recovery|reconstruct\s+everything", request, flags=re.IGNORECASE)
        ),
        "recovery_closure_requested": any(
            node["route"]["id"] in {"RT.DELIVERY.FINAL", "RT.VERIFY.S6.CLOSE"}
            for node in ordered
        ),
        "scope_change_requested": bool(
            re.search(
                r"变更|改动|调整|重划|重定|重新规划|重规划|re.?scope|scope\s+change|replan",
                request,
                flags=re.IGNORECASE,
            )
        ),
    }
    if re.search(r"歧义|不明确|模糊|ambigu|unclear", request, flags=re.IGNORECASE):
        facts["ambiguity"] = True
    if state is not None and any(item.get("status") == "resolved" for item in state.get("open_decisions", [])):
        facts["frozen_decision"] = True
    recovery_route = any(node["route"].get("recovery") for node in ordered)
    if project_root is None and recovery_route:
        facts["recovery_level"] = "R2_FULL"
        facts["integrity"] = "missing"
        facts["change_ownership"] = "none"
    if project_root is not None and recovery_route:
        try:
            from assess_recovery import assess
            recovery = assess(project_root)
            level = recovery.get("level")
            facts["recovery_level"] = (
                "R2_FULL"
                if facts["request_explicit_full_recovery"] or facts["recovery_closure_requested"]
                else level
            )
            facts["integrity"] = "consistent" if level == "R0_CONTINUE" else (
                "missing" if "state_missing" in recovery.get("reasons", []) else "invalid"
            )
            facts["change_ownership"] = "locatable" if level == "R1_TARGETED" else (
                "unowned" if recovery.get("unowned_changes") else "none"
            )
        except Exception:
            # Absence is intentionally unresolved; it is never treated as true.
            pass
    return facts


def resolve(
    request: str,
    project_root: Path | None,
    component_id: str | None,
    component_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    contract = load_json(SKILL_ROOT / "references/route-contract.json")
    component_map = component_map or {}
    mode, mode_hits = classify_mode(request, contract["classification"])
    state = None
    state_errors: list[str] = []
    state_revision = None
    if project_root is not None:
        state, state_errors = load_state(project_root)
        if state is not None:
            state_revision = state.get("revision")
    routing_state = state if not state_errors else None
    clauses = split_clauses(request, contract["classification"]["clause_split_pattern"])
    eligible: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    clause_coverage: list[dict[str, Any]] = []
    for clause in clauses:
        clause_eligible, clause_blocked = route_candidates(
            clause, mode, contract["routes"], routing_state, component_id, component_map
        )
        for node in clause_eligible + clause_blocked:
            node["matched_clauses"] = [clause]
        eligible.extend(clause_eligible)
        blocked.extend(clause_blocked)
        clause_coverage.append({
            "clause": clause,
            "eligible_route_ids": sorted({node["route"]["id"] for node in clause_eligible}),
            "blocked_route_ids": sorted({node["route"]["id"] for node in clause_blocked}),
        })
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    for node in eligible:
        key = (
            node["route"]["id"], node["state"], node["component_type"],
            tuple(node["component_ids"]),
        )
        if key not in merged:
            merged[key] = node
        else:
            merged[key]["matched_patterns"] = sorted(set(merged[key]["matched_patterns"] + node["matched_patterns"]))
            merged[key]["matched_clauses"] = sorted(set(merged[key]["matched_clauses"] + node["matched_clauses"]))
            merged[key]["score"] = max(merged[key]["score"], node["score"])
    eligible = list(merged.values())
    eligible = remove_shadowed(eligible)
    ordered, dependencies = order_nodes(eligible)
    facts = runtime_facts(request, project_root, state, ordered)
    rules, by_id = load_rules()
    selected_rules, applicability = selected_rules_for_routes(
        rules, ordered, mode, contract["event_model"], facts
    )

    status = "resolved"
    reasons: list[str] = []
    allowed_component_keys = {route["id"] for route in contract["routes"]} | {
        route["object"] for route in contract["routes"]
    }
    invalid_component_keys = sorted(set(component_map) - allowed_component_keys)
    if invalid_component_keys:
        status = "blocked"
        reasons.append("unknown component-map keys: " + ",".join(invalid_component_keys))
    used_component_keys = {
        key for node in ordered for key in (node["route"]["id"], node["route"]["object"])
        if key in component_map
    }
    unused_component_keys = sorted(set(component_map) - used_component_keys)
    if unused_component_keys:
        status = "blocked"
        reasons.append("unused component-map keys: " + ",".join(unused_component_keys))
    if state_errors and state_errors != ["state_missing"] and project_root is not None:
        status = "blocked"
        reasons.extend(state_errors)
    if not ordered:
        status = "blocked" if mode in {"mutate", "promote", "skill_maintenance"} else "ambiguous"
        reasons.append("no executable route matched raw request and actual state")
    uncovered = [item["clause"] for item in clause_coverage if not item["eligible_route_ids"]]
    if uncovered:
        status = "blocked" if mode in {"mutate", "promote", "skill_maintenance"} else "ambiguous"
        reasons.append("uncovered substantive clauses: " + " | ".join(uncovered))
    if project_root is None and re.fullmatch(r"\s*(?:继续做|续做|继续|continue|resume)\s*[。.!！]?", request, flags=re.IGNORECASE):
        status = "blocked" if mode in {"mutate", "promote"} else "ambiguous"
        reasons.append("generic continuation requires project context or an explicit object")
    explicit_all = re.search(r"全部|所有|每个|all\b|every\b", request, flags=re.IGNORECASE) is not None
    if any(node["component_type"] == "multiple" for node in ordered) and mode in {"mutate", "promote"} and component_id is None and not explicit_all:
        status = "blocked"
        reasons.append("multiple writable target components require component-id or explicit all-components scope")
    if mode in {"mutate", "promote", "skill_maintenance"} and len({(n["route"]["object"], n["route"]["phase"]) for n in ordered}) < len(ordered):
        status = "blocked"
        reasons.append("writable routes overlap without an ordering distinction")
    if ordered and not selected_rules:
        status = "blocked"
        reasons.append("matched routes select no active rule atoms")
    needs_fact_must = [
        rule["id"] for rule in selected_rules
        if rule["strength"] == "MUST"
        and any(item["status"] == "needs_fact" for item in applicability.get(rule["id"], []))
    ]
    if needs_fact_must and mode in {"mutate", "promote", "skill_maintenance"}:
        status = "blocked"
        reasons.append("writable MUST rules need unresolved facts: " + ",".join(sorted(needs_fact_must)))
    selected_ids = {rule["id"] for rule in selected_rules}
    unresolved_conflicts = sorted({
        tuple(sorted((rule["id"], conflict)))
        for rule in selected_rules
        for conflict in rule.get("conflicts_with", [])
        if conflict in selected_ids and conflict in by_id
    })
    if unresolved_conflicts:
        status = "blocked"
        reasons.extend("unresolved rule conflict: " + " <-> ".join(pair) for pair in unresolved_conflicts)

    return {
        "schema_version": "10.0",
        "status": status,
        "request": request,
        "request_hash": sha256_text(request),
        "mode": mode,
        "mode_evidence": {key: value for key, value in mode_hits.items() if value},
        "project_root": str(project_root.resolve()) if project_root else None,
        "requested_component_id": component_id,
        "requested_component_map": dict(sorted(component_map.items())),
        "state_revision": state_revision,
        "state_errors": state_errors,
        "clause_coverage": clause_coverage,
        "route_nodes": [
            {**public_node(node), "emitted_events": sorted(route_emitted_events(node["route"], contract["event_model"], mode))}
            for node in ordered
        ],
        "route_ids": [node["route"]["id"] for node in ordered],
        "dependencies": dependencies,
        "rule_ids": [rule["id"] for rule in selected_rules],
        "needs_fact_rule_ids": [
            rule["id"] for rule in selected_rules
            if any(item["status"] == "needs_fact" for item in applicability.get(rule["id"], []))
        ],
        "judgment_rule_ids": [
            rule["id"] for rule in selected_rules
            if any(
                exception.get("status") == "deferred_to_agent"
                for item in applicability.get(rule["id"], [])
                for exception in item.get("checks", {}).get("exceptions", [])
            )
        ],
        "runtime_facts": facts,
        "applicability_evidence": {
            rule["id"]: applicability.get(rule["id"], []) for rule in selected_rules
        },
        "rules": [
            {
                "id": rule["id"], "revision": rule["revision"], "capability": rule["capability"],
                "semantic_key": rule["semantic_key"], "strength": rule["strength"],
                "effect": rule["effect"], "instruction_gloss": rule["instruction_gloss"],
                "failure_example": rule["failure_example"], "enforcement": rule["enforcement"],
                "scope": rule["scope"], "trigger": rule["trigger"],
                "evidence": rule["evidence"], "outcomes": rule["outcomes"],
                "exceptions": rule["exceptions"], "conflicts_with": rule["conflicts_with"],
                "refines": rule["refines"], "depends_on": rule["depends_on"],
                "owner": rule["owner"]
            }
            for rule in selected_rules
        ],
        "context_refs": context_refs(request, ordered),
        "blocked_candidates": [
            {**public_node(node), "reasons": node["reasons"]}
            for node in sorted(blocked, key=lambda item: -item["score"])[:8]
        ],
        "reasons": sorted(set(reasons)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True, help="Original user request, unchanged")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--component-id")
    parser.add_argument("--component-map", help="JSON object mapping a route ID or object to a component ID")
    args = parser.parse_args()
    component_map: dict[str, str] = {}
    if args.component_map:
        import json
        try:
            raw_map = json.loads(args.component_map)
        except json.JSONDecodeError as exc:
            parser.error(f"--component-map is not valid JSON: {exc}")
        if not isinstance(raw_map, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in raw_map.items()):
            parser.error("--component-map must be an object of string keys and component IDs")
        component_map = raw_map
    result = resolve(args.request, args.project_root, args.component_id, component_map)
    json_output(result)
    return 0 if result["status"] == "resolved" else 2


if __name__ == "__main__":
    raise SystemExit(main())
