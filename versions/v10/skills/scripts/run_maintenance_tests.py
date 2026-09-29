#!/usr/bin/env python3
"""Execute every registered maintenance-kernel scenario against real isolated fixtures."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from analyze_rule_change import analyze, impact, rank_rules, rule_sha256 as analyzed_rule_sha256
from apply_rule_change import (
    ImpactPermit, apply_change, build_impact_analysis, ensure_isolated_staging,
    execute_staged_change, gate_attestation_errors, issue_impact_permit,
    manifest_sha256, minimum_risk, restore_tree,
    rule_behavior, rule_sha256, snapshot_digest, snapshot_tree, tree_manifest,
    validate_atom_minimal, validate_behavior_tests, validate_envelope, validate_rule_bindings,
    validate_transaction_events,
)
from lib_v10 import ContractError, SKILL_ROOT, dump_json, load_json, load_rules
from run_change_evals import case_shape_errors, evaluate as evaluate_change_case, run as run_change_cases
from validate_contracts import structured_conflict_graph, validate_relations


def rule(root: Path, rule_id: str) -> dict[str, Any]:
    _, by_id = load_rules(root)
    return by_id[rule_id]


def base_change(root: Path, rule_id: str, patch: dict[str, Any], risk: str = "L0") -> dict[str, Any]:
    current = rule(root, rule_id)
    updated = dict(current)
    updated.update(patch)
    updated["revision"] = current["revision"] + 1
    return {
        "operation": "modify", "rule_id": rule_id, "request": f"修改 {rule_id}",
        "old_behavior": rule_behavior(current), "new_behavior": rule_behavior(updated),
        "trigger": updated["trigger"], "exceptions": updated["exceptions"], "risk": risk,
        "impact_analysis": {},
        "expected_owner": current["owner"], "expected_revision": current["revision"],
        "expected_rule_sha256": rule_sha256(current), "patch": patch, "behavior_tests": [],
    }


def seal_change(change: dict[str, Any], root: Path) -> dict[str, Any]:
    change["impact_analysis"] = build_impact_analysis(change, root)
    return change


def component_fixture(state: str) -> dict[str, Any]:
    return {
        "project_state": "P0",
        "components": [{"id": "data-main", "type": "shared_data", "state": state}],
    }


def selected_oracle(target: dict[str, Any], route_ids: list[str], **observables: Any) -> dict[str, Any]:
    return {
        "status": "resolved", "mode": "mutate", "route_ids": route_ids,
        "target_selected": True, "target_effect": target["effect"],
        "selected_rule_ids": [target["id"]], **observables,
    }


def data_change_tests(
    before: dict[str, Any], after: dict[str, Any], prefix: str,
    wrong_candidate_route: bool = False,
) -> list[dict[str, Any]]:
    positive_base = selected_oracle(before, ["RT.DATA.TREAT"])
    positive_candidate = selected_oracle(
        after, ["RT.NOT.A.REAL.ROUTE"] if wrong_candidate_route else ["RT.DATA.TREAT"],
    )
    if before.get("failure_example") != after.get("failure_example"):
        positive_base["target_failure"] = before["failure_example"]
        positive_candidate["target_failure"] = after["failure_example"]
    if rule_behavior(before) != rule_behavior(after):
        positive_base["target_behavior"] = rule_behavior(before)
        positive_candidate["target_behavior"] = rule_behavior(after)
    observable_fields = {
        "scope": "target_scope", "trigger": "target_trigger", "exceptions": "target_exceptions",
        "conflicts_with": "target_conflicts_with", "refines": "target_refines",
        "depends_on": "target_depends_on", "enforcement": "target_enforcement",
        "context_ref": "target_context_ref",
    }
    for field, oracle_key in observable_fields.items():
        if before.get(field) != after.get(field):
            positive_base[oracle_key] = before.get(field)
            positive_candidate[oracle_key] = after.get(field)
    positive = {
        "id": prefix + ".POSITIVE", "kind": "positive", "target_rule_id": before["id"],
        "prompt": "清洗并预处理这个数据集", "component_id": "data-main",
        "fixture": component_fixture("D1"),
        "expected": {"base": positive_base, "candidate": positive_candidate},
    }
    if wrong_candidate_route:
        return [positive]
    unselected = {
        "status": "resolved", "mode": "project_readonly", "route_ids": ["RT.DATA.AUDIT"],
        "target_selected": False, "excluded_rule_ids": [before["id"]],
    }
    near_negative = {
        "id": prefix + ".NEAR_NEGATIVE", "kind": "near_negative", "target_rule_id": before["id"],
        "prompt": "审计数据的结构、缺失和异常", "component_id": "data-main",
        "fixture": component_fixture("D0"),
        "expected": {"base": dict(unselected), "candidate": dict(unselected)},
    }
    disjoint_base = selected_oracle(before, ["RT.DATA.TREAT"])
    disjoint_candidate = selected_oracle(after, ["RT.DATA.TREAT"])
    for oracle in (disjoint_base, disjoint_candidate):
        oracle["excluded_rule_ids"] = ["MNT.OWNER.CANONICAL"]
    conflict = {
        "id": prefix + ".CONFLICT", "kind": "conflict", "target_rule_id": before["id"],
        "prompt": "清洗并预处理这个数据集", "component_id": "data-main",
        "fixture": component_fixture("D1"), "conflict_rule_ids": ["MNT.OWNER.CANONICAL"],
        "resolution": "disjoint", "expected": {"base": disjoint_base, "candidate": disjoint_candidate},
    }
    state_true = {
        "id": prefix + ".STATE_D1", "kind": "state_binding", "target_rule_id": before["id"],
        "prompt": "清洗并预处理这个数据集", "component_id": "data-main", "pair_id": prefix + ".STATE",
        "fixture": component_fixture("D1"),
        "expected": {
            "base": selected_oracle(before, ["RT.DATA.TREAT"]),
            "candidate": selected_oracle(after, ["RT.DATA.TREAT"]),
        },
    }
    state_false_oracle = {
        "status": "blocked", "mode": "mutate", "route_ids": [],
        "target_selected": False, "excluded_rule_ids": [before["id"]],
    }
    state_false = {
        "id": prefix + ".STATE_D3", "kind": "state_binding", "target_rule_id": before["id"],
        "prompt": "清洗并预处理这个数据集", "component_id": "data-main", "pair_id": prefix + ".STATE",
        "fixture": component_fixture("D3"),
        "expected": {"base": dict(state_false_oracle), "candidate": dict(state_false_oracle)},
    }
    return [positive, near_negative, conflict, state_true, state_false]


def retirement_change(root: Path) -> dict[str, Any]:
    target = rule(root, "DATA.TREAT.COPY")
    replacement = rule(root, "DATA.TREAT.LINEAGE")
    base_selected = selected_oracle(target, ["RT.DATA.TREAT"])
    candidate_retired = {
        "status": "resolved", "mode": "mutate", "route_ids": ["RT.DATA.TREAT"],
        "target_selected": False, "selected_rule_ids": [replacement["id"]],
        "excluded_rule_ids": [target["id"]],
    }
    retirement = {
        "id": "MNT.PROBE.RETIRE.TARGET", "kind": "retirement", "target_rule_id": target["id"],
        "prompt": "清洗并预处理这个数据集", "component_id": "data-main",
        "fixture": component_fixture("D1"), "replacement_rule_ids": [replacement["id"]],
        "expected": {"base": base_selected, "candidate": candidate_retired},
    }
    unselected = {
        "status": "resolved", "mode": "project_readonly", "route_ids": ["RT.DATA.AUDIT"],
        "target_selected": False, "excluded_rule_ids": [target["id"]],
    }
    near_negative = {
        "id": "MNT.PROBE.RETIRE.NEAR_NEGATIVE", "kind": "near_negative", "target_rule_id": target["id"],
        "prompt": "审计数据的结构、缺失和异常", "component_id": "data-main",
        "fixture": component_fixture("D0"),
        "expected": {"base": dict(unselected), "candidate": dict(unselected)},
    }
    conflict_candidate = dict(candidate_retired)
    conflict_candidate["excluded_rule_ids"] = [target["id"], "MNT.OWNER.CANONICAL"]
    conflict = {
        "id": "MNT.PROBE.RETIRE.CONFLICT", "kind": "conflict", "target_rule_id": target["id"],
        "prompt": "清洗并预处理这个数据集", "component_id": "data-main",
        "fixture": component_fixture("D1"), "conflict_rule_ids": ["MNT.OWNER.CANONICAL"],
        "resolution": "disjoint", "expected": {"base": dict(base_selected), "candidate": conflict_candidate},
    }
    change = {
        "operation": "retire", "rule_id": target["id"], "request": "废弃 DATA.TREAT.COPY 并由 DATA.TREAT.LINEAGE 接替",
        "old_behavior": rule_behavior(target), "new_behavior": None,
        "trigger": target["trigger"], "exceptions": target["exceptions"], "risk": "L4",
        "expected_owner": target["owner"], "expected_revision": target["revision"],
        "expected_rule_sha256": rule_sha256(target), "replacement_ids": [replacement["id"]],
        "replacement_expectations": [{
            "id": replacement["id"], "expected_owner": replacement["owner"],
            "expected_revision": replacement["revision"], "expected_rule_sha256": rule_sha256(replacement),
        }],
        "behavior_tests": [retirement, near_negative, conflict],
    }
    return seal_change(change, root)


def scenario_analyze_change(root: Path) -> None:
    negated = analyze("不要删除任何规则，只新增一个数据处理规则", root)
    assert negated["classification"]["operation"] == "add", negated["classification"]
    assert negated["status"] == "needs_new_rule_identity"
    assert negated["change_envelope_draft"]["old_behavior"] is None
    assert negated["change_envelope_draft"]["expected_owner"] is None
    only_modify = analyze("禁止新增或删除，只修改 DATA.TREAT.COPY", root)
    assert only_modify["classification"]["operation"] == "modify", only_modify["classification"]
    named_add = analyze("新增 DATA.NEW_RULE_V9 规则", root)
    assert named_add["status"] == "ready_for_envelope", named_add
    assert named_add["change_envelope_draft"]["rule_id"] == "DATA.NEW_RULE_V9"
    exact = analyze("修改 GOV.AUTH.WRITE_SCOPE 的授权边界", root)
    top = exact["owner_candidates"][0]
    assert top["rule_id"] == "GOV.AUTH.WRITE_SCOPE" and top["explicit_id_match"] is True
    draft = exact["change_envelope_draft"]
    current = rule(root, "GOV.AUTH.WRITE_SCOPE")
    assert draft["expected_owner"] == current["owner"]
    assert draft["expected_revision"] == current["revision"]
    assert draft["expected_rule_sha256"] == analyzed_rule_sha256(current)
    assert analyze("修正 DATA.TREAT.COPY 的错别字", root)["classification"]["preliminary_risk"] == "L0"
    assert analyze("澄清 DATA.TREAT.COPY 的上下文引用", root)["classification"]["preliminary_risk"] == "L1"
    assert analyze("修改 DATA.TREAT.COPY 的触发路由", root)["classification"]["preliminary_risk"] == "L2"
    assert analyze("修改 DATA.TREAT.COPY 的 schema 校验", root)["classification"]["preliminary_risk"] == "L3"
    assert analyze("修改维护内核发布门禁", root)["classification"]["preliminary_risk"] == "L4"


def scenario_reject_compound_atom(root: Path) -> None:
    current = copy.deepcopy(rule(root, "DATA.TREAT.COPY"))
    behavior_key = "instruction_gloss" if "instruction_gloss" in current else "instruction"
    current[behavior_key] = "先复制数据；再静默覆盖原件。"
    errors = validate_atom_minimal(current, current["owner"], root)
    assert "new_rule_behavior_compound" in errors, errors


def scenario_risk_escalation(root: Path) -> None:
    current = rule(root, "DATA.TREAT.COPY")
    l0_after = copy.deepcopy(current)
    l0_after["failure_example"] += "（非规范示例探针）"
    assert minimum_risk("modify", current, l0_after, {"failure_example"})[0] == "L0"
    l1_after = copy.deepcopy(current)
    l1_after["context_ref"] = "references/route-contract.json"
    assert minimum_risk("modify", current, l1_after, {"context_ref"})[0] == "L1"
    l1_change = base_change(root, current["id"], {"context_ref": l1_after["context_ref"]}, "L1")
    l1_change["behavior_tests"] = data_change_tests(current, l1_after, "MNT.PROBE.L1")
    seal_change(l1_change, root)
    assert validate_envelope(l1_change, root) == [], validate_envelope(l1_change, root)
    with tempfile.TemporaryDirectory(prefix="v10-mnt-l1-oracle-") as raw:
        candidate = Path(raw) / "candidate"
        shutil.copytree(root, candidate)
        owner_path = candidate / current["owner"].split("#", 1)[0]
        bundle = load_json(owner_path)
        for index, item in enumerate(bundle["rules"]):
            if item["id"] == current["id"]:
                updated = copy.deepcopy(item)
                updated["context_ref"] = l1_after["context_ref"]
                updated["revision"] = item["revision"] + 1
                bundle["rules"][index] = updated
                break
        dump_json(owner_path, bundle)
        results = [evaluate_change_case(case, root, candidate) for case in l1_change["behavior_tests"]]
        assert all(item["status"] == "pass" for item in results), results
    changed = copy.deepcopy(current)
    changed["trigger"] = {"events": ["data_treatment", "dataset_register"], "predicates": []}
    level, reasons = minimum_risk("modify", current, changed, {"trigger"})
    assert level == "L2" and any("trigger" in item for item in reasons)
    l3_after = copy.deepcopy(current)
    l3_after["enforcement"] = {**current["enforcement"], "assurance": "behavior_verified"}
    assert minimum_risk("modify", current, l3_after, {"enforcement"})[0] == "L3"
    maintenance = rule(root, "MNT.CLASSIFY.RISK")
    maintenance_after = copy.deepcopy(maintenance)
    maintenance_after["trigger"] = {"events": [*maintenance["trigger"]["events"], "contract_changed"], "predicates": []}
    assert minimum_risk("modify", maintenance, maintenance_after, {"trigger"})[0] == "L4"
    change = base_change(root, current["id"], {"trigger": changed["trigger"]}, "L1")
    change["behavior_tests"] = data_change_tests(current, changed, "MNT.PROBE.L2")
    seal_change(change, root)
    errors = validate_envelope(change, root)
    assert any(item.startswith("risk_underreported:L1<L2") for item in errors), errors
    change["risk"] = "L2"
    assert validate_envelope(change, root) == [], validate_envelope(change, root)
    with tempfile.TemporaryDirectory(prefix="v10-mnt-l4-") as raw:
        base = Path(raw) / "base"
        candidate = Path(raw) / "candidate"
        shutil.copytree(root, base)
        shutil.copytree(root, candidate)
        before = tree_manifest(candidate)
        retirement = retirement_change(base)
        report, exit_code = execute_staged_change(retirement, base, candidate)
        assert exit_code == 3 and report["status"] == "requires_major_fork", report
        assert report["minimum_risk"] == "L4" and tree_manifest(candidate) == before
        permit = issue_impact_permit(retirement, candidate)
        try:
            apply_change(retirement, candidate, permit)
        except ContractError as exc:
            assert str(exc) == "requires_major_fork"
        else:
            raise AssertionError("low-level L4 write bypass was accepted")
        assert tree_manifest(candidate) == before


def scenario_impact_graph(root: Path) -> None:
    rules, _ = load_rules(root)
    candidates = rank_rules("修改 GOV.AUTH.WRITE_SCOPE 的授权规则", rules)
    result = impact(candidates, rules, "L4", ["authorization", "routing"])
    assert "GOV.AUTH.WRITE_SCOPE" in result["rules"]
    assert "GOV-AUTH-001" in result["capabilities"]
    assert "references/route-contract.json" in result["contracts"]
    assert any(edge["from"] == "GOV.AUTH.WRITE_SCOPE" and edge["kind"] == "owned_by" for edge in result["edges"])
    current = rule(root, "DATA.TREAT.COPY")
    changed = copy.deepcopy(current)
    changed["failure_example"] += "（impact CLI 探针）"
    change = base_change(root, current["id"], {"failure_example": changed["failure_example"]}, "L0")
    change["behavior_tests"] = data_change_tests(current, changed, "MNT.PROBE.IMPACT")
    expected_proof = build_impact_analysis(change, root)
    with tempfile.TemporaryDirectory(prefix="v10-mnt-impact-") as raw:
        envelope_path = Path(raw) / "change.json"
        dump_json(envelope_path, change)
        process = subprocess.run(
            [
                sys.executable, str(root / "scripts/apply_rule_change.py"),
                "--change", str(envelope_path), "--base-root", str(root), "--prepare-impact",
            ],
            text=True, capture_output=True, cwd=root, timeout=120,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        report = json.loads(process.stdout)
        assert process.returncode == 0 and report["status"] == "impact_analysis_passed", report
        assert report["impact_analysis"] == expected_proof
        candidate = Path(raw) / "candidate"
        shutil.copytree(root, candidate)
        change["impact_analysis"] = expected_proof
        forged = ImpactPermit(
            root=str(candidate.resolve()), rule_id=current["id"],
            base_rule_sha256=expected_proof["base_rule_sha256"],
            analysis_sha256=expected_proof["analysis_sha256"],
            tree_manifest_sha256=manifest_sha256(tree_manifest(candidate, ignore_caches=True)),
            issued_monotonic_ns=0, seal=object(),
        )
        candidate_before = tree_manifest(candidate)
        try:
            apply_change(change, candidate, forged)
        except ContractError as exc:
            assert str(exc) == "impact_permit_required"
        else:
            raise AssertionError("forged impact permit was accepted")
        assert tree_manifest(candidate) == candidate_before
        owner_path = candidate / current["owner"].split("#", 1)[0]
        bundle = load_json(owner_path)
        for index, item in enumerate(bundle["rules"]):
            if item["id"] == current["id"]:
                updated = copy.deepcopy(item)
                updated["failure_example"] = changed["failure_example"]
                updated["revision"] = item["revision"] + 1
                bundle["rules"][index] = updated
                break
        dump_json(owner_path, bundle)
        results = [evaluate_change_case(case, root, candidate) for case in change["behavior_tests"]]
        assert all(item["status"] == "pass" for item in results), results


def scenario_duplicate_owner(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="v10-mnt-duplicate-") as raw:
        candidate = Path(raw) / "candidate"
        shutil.copytree(root, candidate)
        duplicate = copy.deepcopy(rule(candidate, "DATA.TREAT.COPY"))
        duplicate["id"] = "DATA.TREAT.COPY_DUP"
        duplicate["revision"] = 1
        duplicate["owner"] = "rules/data.json#DATA.TREAT.COPY_DUP"
        errors = validate_rule_bindings(duplicate, candidate)
        assert any(item.startswith("duplicate_semantic_owner:DATA.TREAT.COPY") for item in errors), errors


def scenario_spoof_owner(root: Path) -> None:
    current = rule(root, "DATA.TREAT.COPY")
    changed_effect = dict(current["effect"])
    changed_effect["value"] = "spoofed"
    change = base_change(root, current["id"], {"effect": changed_effect}, "L2")
    change["expected_owner"] = "rules/modeling.json#DATA.TREAT.COPY"
    errors = validate_envelope(change, root)
    assert "expected_owner_mismatch" in errors, errors
    missing = base_change(root, current["id"], {"effect": changed_effect}, "L2")
    for field in ("expected_owner", "expected_revision", "expected_rule_sha256"):
        del missing[field]
    errors = validate_envelope(missing, root)
    assert {"expected_owner_required", "expected_revision_required", "expected_rule_sha256_required"} <= set(errors), errors
    stale = base_change(root, current["id"], {"effect": changed_effect}, "L2")
    stale["expected_revision"] += 1
    stale["expected_rule_sha256"] = "0" * 64
    errors = validate_envelope(stale, root)
    assert {"expected_revision_mismatch", "expected_rule_sha256_mismatch"} <= set(errors), errors
    mismatched = base_change(root, current["id"], {"effect": changed_effect}, "L2")
    mismatched["old_behavior"] = "伪造旧行为"
    mismatched["new_behavior"] = "伪造新行为"
    mismatched["trigger"] = {"events": ["request_received"], "predicates": []}
    errors = validate_envelope(mismatched, root)
    assert {"old_behavior_mismatch", "new_behavior_mismatch", "trigger_mismatch"} <= set(errors), errors
    retire = retirement_change(root)
    for field in ("expected_owner", "expected_revision", "expected_rule_sha256"):
        del retire[field]
    errors = validate_envelope(retire, root)
    assert {"expected_owner_required", "expected_revision_required", "expected_rule_sha256_required"} <= set(errors), errors


def scenario_structured_conflict(root: Path) -> None:
    invalid = {
        "id": "MNT.TEST.BAD_CONFLICT", "kind": "conflict",
        "target_rule_id": "MNT.OWNER.CANONICAL", "prompt": "修改Skill规则",
        "expected": {
            "base": {"status": "resolved", "route_ids": ["RT.SKILL.CHANGE"], "target_selected": True,
                     "target_effect": {"verb": "require", "target": "edit_target", "value": "declared_rule_owner"}},
            "candidate": {"status": "resolved", "route_ids": ["RT.SKILL.CHANGE"], "target_selected": True,
                          "target_effect": {"verb": "require", "target": "edit_target", "value": "declared_rule_owner"}},
        },
    }
    errors = case_shape_errors(invalid)
    assert "conflict_rule_ids_required" in errors and "resolution_invalid" in errors, errors
    contract = load_json(root / "references/route-contract.json")
    routes = contract["routes"]
    event_model = contract["event_model"]
    current_graph = structured_conflict_graph(load_rules(root)[0], routes, event_model)
    assert not [edge for edge in current_graph if edge["resolution"] == "unresolved"], current_graph

    left = copy.deepcopy(rule(root, "DATA.TREAT.COPY"))
    right = copy.deepcopy(rule(root, "DATA.TREAT.LINEAGE"))
    for item in (left, right):
        item["conflicts_with"] = []
        item["refines"] = []
        item["depends_on"] = []
        item["supersedes"] = []
    right["effect"] = {
        "verb": "forbid",
        "target": left["effect"]["target"],
        "value": "copy_creation",
    }
    probes = [left, right]
    graph = structured_conflict_graph(probes, routes, event_model)
    assert len(graph) == 1, graph
    edge = graph[0]
    assert edge["cross_semantic_key"] is True
    assert edge["effect_relation"] == "incompatible"
    assert edge["overlap_route_ids"] == ["RT.DATA.TREAT"]
    assert edge["resolution"] == "unresolved"
    relation_errors = validate_relations(
        probes, {item["id"]: item for item in probes}, routes, event_model,
    )
    assert any(item.startswith("effect_overlap_incompatible:") for item in relation_errors), relation_errors

    left["conflicts_with"] = [right["id"]]
    right["conflicts_with"] = [left["id"]]
    resolved = structured_conflict_graph(probes, routes, event_model)
    assert resolved[0]["resolution"] == "explicit"
    assert resolved[0]["relations"] == ["explicit_conflict"]
    resolved_errors = validate_relations(
        probes, {item["id"]: item for item in probes}, routes, event_model,
    )
    assert not [item for item in resolved_errors if item.startswith("effect_overlap_")], resolved_errors


def scenario_behavior_test_bundle(root: Path) -> None:
    invalid = {
        "id": "MNT.TEST.UNKNOWN_EXPECTED", "kind": "positive",
        "target_rule_id": "MNT.OWNER.CANONICAL", "prompt": "修改Skill规则",
        "expected": {
            "base": {"status": "resolved", "route_ids": ["RT.SKILL.CHANGE"], "target_selected": True,
                     "target_effect": {}, "banana": True},
            "candidate": {"status": "resolved", "route_ids": ["RT.SKILL.CHANGE"], "target_selected": True,
                          "target_effect": {}},
        },
    }
    errors = case_shape_errors(invalid)
    assert any("unknown:banana" in item for item in errors), errors
    current = rule(root, "DATA.TREAT.COPY")
    changed = copy.deepcopy(current)
    changed["failure_example"] += "（expected closure 探针）"
    change = base_change(root, current["id"], {"failure_example": changed["failure_example"]}, "L0")
    change["behavior_tests"] = data_change_tests(current, changed, "MNT.PROBE.EXPECTED_CLOSED")
    change["behavior_tests"][0]["expected"]["candidate"]["target_fields"] = {"banana": None}
    errors = validate_behavior_tests(change, current, changed, "L0", root)
    assert any("target_fields_unknown:banana" in item for item in errors), errors
    traversal = copy.deepcopy(load_json(root / "evals/change-cases.json")["cases"][0])
    traversal["fixture"] = {
        "project_state": "P0", "components": [{"id": "q1", "type": "question", "state": "S0"}],
        "r1_changed_artifact": {"path": "../../outside.txt", "producer": "q1", "content": "probe"},
    }
    errors = case_shape_errors(traversal, root)
    assert "case:fixture_changed_artifact_path_unsafe" in errors, errors
    with tempfile.TemporaryDirectory(prefix="v10-mnt-zero-") as raw:
        candidate = Path(raw) / "candidate"
        shutil.copytree(root, candidate)
        dump_json(candidate / "evals/change-cases.json", {"schema_version": "10.0", "cases": []})
        result = run_change_cases(candidate, candidate)
        assert result["status"] == "fail" and result["total"] == 0
    with tempfile.TemporaryDirectory(prefix="v10-mnt-retirement-") as raw:
        base = Path(raw) / "base"
        candidate = Path(raw) / "candidate"
        shutil.copytree(root, base)
        shutil.copytree(root, candidate)
        change = retirement_change(base)
        assert validate_envelope(change, base) == [], validate_envelope(change, base)
        # Materialize only an evaluator fixture. Production apply_change rejects all L4 writes.
        target = rule(candidate, change["rule_id"])
        replacement = rule(candidate, change["replacement_ids"][0])
        assert target["owner"].split("#", 1)[0] == replacement["owner"].split("#", 1)[0]
        bundle_path = candidate / target["owner"].split("#", 1)[0]
        bundle = load_json(bundle_path)
        for index, item in enumerate(bundle["rules"]):
            if item["id"] == target["id"]:
                updated = copy.deepcopy(item)
                updated.update({"status": "retired", "revision": item["revision"] + 1, "routes": []})
                bundle["rules"][index] = updated
            elif item["id"] == replacement["id"]:
                updated = copy.deepcopy(item)
                updated["revision"] = item["revision"] + 1
                updated["supersedes"] = sorted(set(item.get("supersedes", [])) | {target["id"]})
                bundle["rules"][index] = updated
        dump_json(bundle_path, bundle)
        results = [evaluate_change_case(case, base, candidate) for case in change["behavior_tests"]]
        assert {item["kind"] for item in results} == {"retirement", "near_negative", "conflict"}
        assert all(item["status"] == "pass" for item in results), results


def scenario_unreachable_rule(root: Path) -> None:
    template = copy.deepcopy(rule(root, "DATA.TREAT.COPY"))
    template.update({
        "id": "DATA.TREAT.UNREACHABLE", "revision": 1,
        "owner": "rules/data.json#DATA.TREAT.UNREACHABLE",
        "semantic_key": "data.treatment.unreachable_probe", "routes": ["RT.DOES.NOT.EXIST"],
    })
    change = {
        "operation": "add", "rule_id": template["id"], "request": "新增不可达数据规则",
        "old_behavior": None, "new_behavior": rule_behavior(template),
        "trigger": template["trigger"], "exceptions": template["exceptions"], "risk": "L2",
        "new_rule": template, "behavior_tests": [],
    }
    errors = validate_envelope(change, root)
    assert any(item.startswith("unknown_routes:RT.DOES.NOT.EXIST") for item in errors), errors


def scenario_fresh_process(root: Path) -> None:
    payload = load_json(root / "evals/change-cases.json")
    invariant_cases = [
        case for case in payload.get("cases", [])
        if isinstance(case, dict)
        and isinstance(case.get("expected"), dict)
        and case["expected"].get("base") == case["expected"].get("candidate")
    ]
    assert invariant_cases, "fresh-process baseline has zero invariant cases"
    results = [evaluate_change_case(case, root, root) for case in invariant_cases]
    assert all(item["status"] == "pass" for item in results), results


def scenario_previous_version(root: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="v10-mnt-rollback-") as raw:
        base = Path(raw) / "base"
        candidate = Path(raw) / "candidate"
        v9_root = Path(raw) / "v9"
        shutil.copytree(root, base)
        shutil.copytree(root, candidate)
        v9_root.mkdir()
        (base / "empty-preserved").mkdir()
        (candidate / "empty-preserved").mkdir()
        assert ensure_isolated_staging(base, candidate) == []
        base_before = tree_manifest(base)
        candidate_before = tree_manifest(candidate)
        base_snapshot = snapshot_tree(base)
        candidate_snapshot = snapshot_tree(candidate)
        current = rule(base, "DATA.TREAT.COPY")
        changed = copy.deepcopy(current)
        changed["failure_example"] = "回滚探针：不得原地覆盖已登记数据。"
        change = base_change(base, current["id"], {"failure_example": changed["failure_example"]}, "L0")
        change["behavior_tests"] = data_change_tests(
            current, changed, "MNT.PROBE.ROLLBACK", wrong_candidate_route=True,
        )
        seal_change(change, base)
        assert validate_envelope(change, base) == [], validate_envelope(change, base)

        unauthorized_before = tree_manifest(candidate)
        try:
            apply_change(change, candidate, None)
        except ContractError as exc:
            assert str(exc) == "impact_permit_required"
        else:
            raise AssertionError("rule write was reachable without an impact permit")
        assert tree_manifest(candidate) == unauthorized_before

        forged = copy.deepcopy(change)
        forged["impact_analysis"]["affected_routes"].append("RT.FORGED")
        assert "impact_analysis_mismatch" in validate_envelope(forged, base)

        called = {"gate": False}

        def failing_gate(base_root: Path, candidate_root: Path, _: Path | None) -> tuple[bool, list[dict[str, Any]]]:
            called["gate"] = True
            (candidate_root / "empty-preserved").rmdir()
            (candidate_root / "new" / "nested").mkdir(parents=True)
            (candidate_root / "new" / "nested" / "probe.txt").write_text("probe\n", encoding="utf-8")
            os.chmod(candidate_root / "scripts/analyze_rule_change.py", 0o600)
            (base_root / "illicit-base-write.txt").write_text("must be restored\n", encoding="utf-8")
            return False, [{
                "command": "injected_failure", "exit_code": 2, "stdout": "", "stderr": "probe",
            }]

        report, exit_code = execute_staged_change(
            change, base, candidate, v9_root, failing_gate,
            lambda _candidate, _v9: [],
        )
        assert exit_code == 2 and report["status"] == "rolled_back", report
        if not called["gate"]:
            assert any("atomic_case_rebuild_failed" in item for item in report.get("errors", [])), report
        assert validate_transaction_events(report["details"]["transaction_events"]) == []
        assert report["rollback_verified"] is True and report["rollback_errors"] == []
        assert tree_manifest(candidate) == candidate_before
        assert tree_manifest(base) == base_before
        assert (candidate / "empty-preserved").is_dir()
        if not called["gate"]:
            # Exercise the same full-tree restoration primitives despite an earlier derived-build failure.
            (candidate / "empty-preserved").rmdir()
            (candidate / "new" / "nested").mkdir(parents=True)
            (candidate / "new" / "nested" / "probe.txt").write_text("probe\n", encoding="utf-8")
            os.chmod(candidate / "scripts/analyze_rule_change.py", 0o600)
            (base / "illicit-base-write.txt").write_text("must be restored\n", encoding="utf-8")
            restore_tree(candidate, candidate_snapshot)
            restore_tree(base, base_snapshot)
            assert tree_manifest(candidate) == candidate_before
            assert tree_manifest(base) == base_before

    with tempfile.TemporaryDirectory(prefix="v10-mnt-hardlink-") as raw:
        base = Path(raw) / "base"
        candidate = Path(raw) / "candidate"
        base.mkdir()
        candidate.mkdir()
        source = base / "shared.txt"
        source.write_text("same inode\n", encoding="utf-8")
        os.link(source, candidate / "shared.txt")
        errors = ensure_isolated_staging(base, candidate)
        assert any(item.startswith("candidate_shares_file_identity_with_base:") for item in errors), errors


def scenario_generated_release_report(root: Path) -> None:
    forged = json.dumps({"schema_version": "10.0", "status": "pass", "total": 0, "results": []})
    assert "zero_results_is_not_evidence" in gate_attestation_errors("run_change_evals.py", forged)
    assert "case_execution_count_invalid" in gate_attestation_errors("run_change_evals.py", forged)
    with tempfile.TemporaryDirectory(prefix="v10-mnt-computed-") as raw:
        candidate = Path(raw) / "candidate"
        shutil.copytree(root, candidate)
        payload = load_json(candidate / "evals/change-cases.json")
        payload["cases"][0]["expected"]["candidate"]["status"] = "blocked"
        dump_json(candidate / "evals/change-cases.json", payload)
        result = run_change_cases(candidate, root)
        assert result["status"] == "fail" and result["failed"] > 0


SCENARIOS: dict[str, Callable[[Path], None]] = {
    "analyze_change": scenario_analyze_change,
    "reject_compound_atom": scenario_reject_compound_atom,
    "risk_escalation": scenario_risk_escalation,
    "impact_graph": scenario_impact_graph,
    "duplicate_owner": scenario_duplicate_owner,
    "spoof_owner": scenario_spoof_owner,
    "structured_conflict": scenario_structured_conflict,
    "behavior_test_bundle": scenario_behavior_test_bundle,
    "unreachable_rule": scenario_unreachable_rule,
    "fresh_process": scenario_fresh_process,
    "previous_version": scenario_previous_version,
    "generated_release_report": scenario_generated_release_report,
}


def registered_cases(root: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted((root / "evals").glob("*.json")):
        payload = load_json(path)
        for case in payload.get("cases", []):
            if case.get("kind") == "scenario" and case.get("driver") == "maintenance_tests":
                cases.append(case)
    return cases


def run(root: Path) -> dict[str, Any]:
    cases = registered_cases(root)
    results: list[dict[str, Any]] = []
    seen_scenarios: set[str] = set()
    for case in cases:
        scenario = str(case.get("scenario"))
        seen_scenarios.add(scenario)
        handler = SCENARIOS.get(scenario)
        if handler is None:
            results.append({"id": case["id"], "scenario": scenario, "status": "fail", "error": "implementation missing"})
            continue
        try:
            handler(root)
            results.append({"id": case["id"], "scenario": scenario, "status": "pass", "error": None})
        except Exception as exc:
            results.append({
                "id": case["id"], "scenario": scenario, "status": "fail",
                "error": f"{type(exc).__name__}: {exc}",
            })
    unregistered = sorted(set(SCENARIOS) - seen_scenarios)
    duplicate_ids = sorted({case["id"] for case in cases if sum(item["id"] == case["id"] for item in cases) > 1})
    failed = [item for item in results if item["status"] != "pass"]
    status = "pass" if cases and not failed and not unregistered and not duplicate_ids else "fail"
    return {
        "schema_version": "10.0", "status": status, "driver": "maintenance_kernel_real_scenarios",
        "total": len(results), "passed": len(results) - len(failed), "failed": len(failed),
        "unregistered_implementations": unregistered, "duplicate_case_ids": duplicate_ids, "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    args = parser.parse_args()
    result = run(args.root.resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
