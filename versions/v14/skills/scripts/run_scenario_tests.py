#!/usr/bin/env python3
"""Run active V11 state, recovery, artifact, route, and receipt scenarios."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from assess_recovery import assess, scope_paths_for_step
from lib_v10 import (
    ContractError,
    SKILL_ROOT,
    STRONG_EVIDENCE_KINDS,
    dump_json,
    load_json,
    now_iso,
    sha256_file,
    sha256_text,
)
from lib_v11 import resolve
from run_authorized_action import execute as execute_authorized_action
from state_manager import (
    current_evidence_levels,
    do_add_component,
    do_add_open_decision,
    do_checkpoint,
    do_checkpoint_before_interrupt,
    do_init,
    do_record_evidence,
    do_record_route,
    do_refresh_artifact,
    do_register_artifact,
    do_resolve_open_decision,
    do_revalidate_component,
    do_transition,
)
from state_v11 import (
    canonical_input_refs,
    evidence_binding_hash,
    stale_exact_input_evidence,
    validate_artifact_proposal,
    validate_state_semantics,
)
from validate_receipt import (
    checkpoint_pair_hash,
    shape_errors,
    validate_end,
    validate_start,
)


def args(**values: Any) -> SimpleNamespace:
    return SimpleNamespace(**values)


def must_raise(action: Callable[[], Any], contains: str) -> str:
    try:
        action()
    except ContractError as exc:
        message = str(exc)
        assert contains in message, (contains, message)
        return message
    raise AssertionError(f"expected ContractError containing {contains!r}")


def assert_error(errors: list[str], fragment: str) -> None:
    assert any(fragment in item for item in errors), (fragment, errors)


def init_project(root: Path, project_id: str = "fixture") -> dict[str, Any]:
    return do_init(args(project_root=root, project_id=project_id, watch_root=[]))


def add_component(
    root: Path,
    component_id: str,
    component_type: str,
    dependencies: list[str] | None = None,
    *,
    optional: bool = False,
) -> dict[str, Any]:
    return do_add_component(args(
        project_root=root,
        component_id=component_id,
        type=component_type,
        dependency=dependencies or [],
        optional=optional,
    ))


def typed_evidence(
    root: Path,
    component_id: str,
    level: str,
    evidence_id: str,
    *,
    status: str = "pass",
    input_refs: list[dict[str, str]] | None = None,
    claim_refs: list[str] | None = None,
    locator_artifact: str | None = None,
) -> dict[str, Any]:
    refs = canonical_input_refs(input_refs or [])
    claims = sorted(set(claim_refs or [f"claim:{component_id}:{level}:{evidence_id}"]))
    allowed = STRONG_EVIDENCE_KINDS.get(level, set())
    timestamp = now_iso()
    if "file" in allowed:
        target = root / locator_artifact if locator_artifact else (
            root / ".modeling/evidence-files" / f"{evidence_id}.txt"
        )
        if locator_artifact is None:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"verified {level}\n", encoding="utf-8")
        locator = {
            "path": target.relative_to(root).as_posix(),
            "sha256": sha256_file(target),
        }
        kind = "file"
    elif "command" in allowed:
        target = root / ".modeling/evidence-files" / f"{evidence_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"verified {level}\n", encoding="utf-8")
        digest = sha256_file(target)
        locator = {
            "command_hash": digest,
            "exit_code": 0,
            "output_ref": target.relative_to(root).as_posix(),
            "output_sha256": digest,
        }
        kind = "command"
    elif "decision" in allowed:
        decision_id = f"DEC-{evidence_id}"
        state = load_json(root / ".modeling/state.json")
        state["open_decisions"].append({
            "id": decision_id,
            "subject": level,
            "options": ["reject", "authorize"],
            "status": "resolved",
            "opened_at": timestamp,
            "resolved_at": timestamp,
            "selected": "authorize",
            "affects": [component_id],
        })
        state["components"][component_id]["decisions"].append(decision_id)
        dump_json(root / ".modeling/state.json", state)
        locator = {"decision_id": decision_id, "recorded_at": timestamp}
        kind = "decision"
    else:
        locator = {
            "subject": level,
            "method": "independent V11 fixture assertion",
            "value": True,
        }
        kind = "observation"
    return {
        "id": evidence_id,
        "level": level,
        "status": status,
        "kind": kind,
        "locator": locator,
        "claim": f"{level} was independently checked for {component_id}",
        "observed_at": timestamp,
        "producer": "v11_scenario_tests",
        "subject_id": component_id,
        "input_refs": refs,
        "claim_refs": claims,
        "binding_hash": evidence_binding_hash(component_id, level, refs, claims),
    }


def record_evidence(
    root: Path,
    component_id: str,
    level: str,
    evidence_id: str | None = None,
    *,
    status: str = "pass",
    replace: bool = False,
    input_refs: list[dict[str, str]] | None = None,
    claim_refs: list[str] | None = None,
    locator_artifact: str | None = None,
) -> str:
    identifier = evidence_id or f"EV-{component_id}-{level}"
    record = typed_evidence(
        root,
        component_id,
        level,
        identifier,
        status=status,
        input_refs=input_refs,
        claim_refs=claim_refs,
        locator_artifact=locator_artifact,
    )
    record_path = root / ".modeling/evidence-records" / f"{identifier}.json"
    dump_json(record_path, record)
    do_record_evidence(args(
        project_root=root,
        component_id=component_id,
        evidence=record_path,
        replace=replace,
    ))
    return identifier


def transition(root: Path, component_id: str, target: str) -> dict[str, Any]:
    return do_transition(args(
        project_root=root,
        project=False,
        component_id=component_id,
        to=target,
        reason=None,
        reason_evidence_id=None,
    ))


def advance_question_to_s5(root: Path, component_id: str = "q1") -> None:
    sequence = (
        ("S1", ("scope", "problem_definition")),
        ("S2", ("evidence_plan",)),
        ("S3", ("candidate_set",)),
        ("S4", ("model_spec", "selection_rationale")),
        ("S5", ("implementation_ref",)),
    )
    for target, levels in sequence:
        for level in levels:
            record_evidence(root, component_id, level)
        transition(root, component_id, target)


def advance_question_to_s6(root: Path, component_id: str = "q1") -> None:
    advance_question_to_s5(root, component_id)
    record_evidence(root, component_id, "E1_IMPLEMENTATION")
    record_evidence(root, component_id, "E2_NUMERICAL")
    transition(root, component_id, "S6")


def advance_question_to_s7(root: Path, component_id: str = "q1") -> None:
    advance_question_to_s6(root, component_id)
    record_evidence(root, component_id, "E3_STRUCTURAL")
    record_evidence(root, component_id, "E4_REALITY")
    transition(root, component_id, "S7")


def transition_project(root: Path, target: str) -> dict[str, Any]:
    return do_transition(args(
        project_root=root,
        project=True,
        component_id=None,
        to=target,
        reason=None,
        reason_evidence_id=None,
    ))


def artifact_proposal(
    path: str,
    consumers: list[str],
    identity_class: str,
    *,
    artifact_class: str = "result",
) -> dict[str, Any]:
    lifecycle = {
        "working": "working",
        "milestone": "milestone",
        "frozen": "milestone",
        "final": "final",
    }[identity_class]
    return {
        "path": path,
        "purpose": f"Provide the scenario identity at {path}",
        "consumer_ids": sorted(set(consumers)),
        "lifecycle": lifecycle,
        "identity_class": identity_class,
        "class": artifact_class,
        "authorization_basis": "active V11 contract scenario",
        "replaces": None,
    }


def register_artifact(
    root: Path,
    path: str,
    producer: str,
    consumers: list[str],
    *,
    identity_class: str = "working",
    artifact_class: str = "result",
    role: str | None = None,
    content: str = "identity version one\n",
) -> tuple[dict[str, Any], str]:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    proposal_path = root / ".modeling/proposals" / (Path(path).name + ".json")
    dump_json(
        proposal_path,
        artifact_proposal(
            path, consumers, identity_class, artifact_class=artifact_class
        ),
    )
    state = do_register_artifact(args(
        project_root=root,
        proposal=proposal_path,
        producer=producer,
        role=role or artifact_class,
    ))
    return state, state["artifacts"][path]["sha256"]


def refresh_artifact(root: Path, path: str, old_identity: str, content: str) -> dict[str, Any]:
    (root / path).write_text(content, encoding="utf-8")
    return do_refresh_artifact(args(
        project_root=root,
        path=path,
        expected_old_sha256=old_identity,
    ))


def advisory_plan() -> dict[str, Any]:
    return {
        "schema_version": "11.0",
        "plan_id": "PLAN-V11-ADVISE",
        "request": "Explain the current project state.",
        "steps": [{
            "id": "advise",
            "tier": "G0_ADVISORY",
            "mode": "advisory_readonly",
            "object": "project",
            "action": "explain",
            "component_id": None,
            "events": [],
            "facts": {},
            "depends_on": [],
            "change_set": {"paths": [], "facets": [], "claim_refs": []},
        }],
    }


def g2_recovery_plan() -> dict[str, Any]:
    return {
        "schema_version": "11.0",
        "plan_id": "PLAN-V11-G2-RECOVERY",
        "request": "Resume and inspect the current project.",
        "window_context": "same_window",
        "steps": [{
            "id": "resume",
            "tier": "G2_CHECKPOINT",
            "mode": "project_readonly",
            "object": "project",
            "action": "recover",
            "component_id": None,
            "events": ["recovery_assessment"],
            "facts": {},
            "depends_on": [],
            "change_set": {"paths": [], "facets": [], "claim_refs": []},
        }],
    }


def s6_close_plan() -> dict[str, Any]:
    return {
        "schema_version": "11.0",
        "plan_id": "PLAN-V11-S6-CLOSE",
        "request": "关闭第一问 S6。",
        "steps": [{
            "id": "close",
            "tier": "G2_CHECKPOINT",
            "mode": "promote",
            "object": "verification",
            "action": "close_s6",
            "component_id": "q1",
            "events": ["s6_readiness", "s6_close"],
            "facts": {},
            "depends_on": [],
            "change_set": {
                "paths": [], "facets": ["question_state"], "claim_refs": [],
            },
            "state_effect": {"component_id": "q1", "from": "S6", "to": "S7"},
        }],
    }


def pause_plan(tier: str = "G1_WORKING", mode: str = "mutate") -> dict[str, Any]:
    return {
        "schema_version": "11.0",
        "plan_id": f"PLAN-V11-PAUSE-{tier}",
        "request": "今天先到这里，做收尾整理并记下下一步。",
        "steps": [{
            "id": "pause", "tier": tier, "mode": mode,
            "object": "project", "action": "pause", "component_id": None,
            "events": ["handoff"], "facts": {}, "depends_on": [],
            "change_set": {
                "paths": [], "facets": ["open_decisions", "next_actions"],
                "claim_refs": [],
            },
        }],
    }


def model_runtime_plan(marker: str = "marker.txt") -> dict[str, Any]:
    request = "运行第一问模型并保存本轮结果。"
    return {
        "schema_version": "11.0",
        "plan_id": "PLAN-V11-GUARDED-MODEL-RUN",
        "request": request,
        "steps": [{
            "id": "solve-q1", "tier": "G1_WORKING", "mode": "mutate",
            "object": "model", "action": "solve", "component_id": "q1",
            "events": ["model_execution"], "facts": {}, "depends_on": [],
            "change_set": {
                "paths": [marker], "facets": ["computation"], "claim_refs": [],
            },
            "runtime_actions": [{
                "id": "run-q1", "kind": "project_model_execution",
                "event": "model_execution", "repetition": "first_run",
                "scope": {
                    "kind": "component", "component_ids": ["q1"],
                    "input_paths": [], "output_paths": [marker],
                },
                "command": {
                    "argv": [
                        sys.executable, "-c",
                        f"from pathlib import Path; Path({marker!r}).write_text('ran', encoding='utf-8')",
                    ],
                    "cwd": ".",
                },
                "authorization": {
                    "source": "direct_user_request",
                    "request_excerpt": "运行第一问模型",
                },
            }],
        }],
    }


def receipt_validation(
    state: dict[str, Any], component_id: str, evidence_id: str
) -> dict[str, Any]:
    stored = next(
        item for item in state["components"][component_id]["evidence"]
        if item["id"] == evidence_id
    )
    return {
        "id": stored["id"],
        "component_id": component_id,
        "level": stored["level"],
        "status": stored["status"],
        "evidence_ref": (
            f"state:components/{component_id}/evidence/{stored['id']}"
        ),
        "input_refs": stored["input_refs"],
        "claim_refs": stored["claim_refs"],
        "binding_hash": stored["binding_hash"],
    }


def receipt_common(
    root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan = g2_recovery_plan()
    plan_path = root / ".modeling/formal-plan.json"
    dump_json(plan_path, plan)
    state = do_record_route(args(
        project_root=root,
        plan=plan_path,
        step_id="resume",
        execution_id="EXEC-V11-RECEIPT",
    ))
    execution = state["executions"]["EXEC-V11-RECEIPT"]
    resolution = resolve(plan, root)
    step = next(item for item in resolution["steps"] if item["id"] == "resume")
    assert step["status"] == "resolved", resolution
    common = {
        "schema_version": "11.0",
        "request": plan["request"],
        "request_hash": sha256_text(plan["request"]),
        "semantic_plan": plan,
        "plan_hash": resolution["plan_hash"],
        "step_id": step["id"],
        "execution_id": execution["id"],
        "pair_hash": checkpoint_pair_hash(execution),
        "project_root": str(root.resolve()),
        "tier": step["tier"],
        "mode": step["mode"],
        "route_ids": [step["route_id"]],
        "rule_ids": step["rule_ids"],
        "component_ids": step["component_ids"],
        "change_set": step["change_set"],
    }
    return common, resolution, state, execution


def start_receipt(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    common, resolution, _, execution = receipt_common(root)
    receipt = {
        **common,
        "receipt_type": "start",
        "state_revision": execution["start_revision"],
        "recovery": execution["recovery"],
        "required_identities": [],
        "blocked": False,
    }
    return receipt, resolution


def end_receipt(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    common, resolution, _, execution = receipt_common(root)
    evidence_id = record_evidence(root, "q1", "scope", "EV-RECEIPT-SCOPE")
    state = load_json(root / ".modeling/state.json")
    stored = next(
        item for item in state["components"]["q1"]["evidence"]
        if item["id"] == evidence_id
    )
    validation = {
        "id": stored["id"],
        "component_id": "q1",
        "level": stored["level"],
        "status": stored["status"],
        "evidence_ref": f"state:components/q1/evidence/{stored['id']}",
        "input_refs": stored["input_refs"],
        "claim_refs": stored["claim_refs"],
        "binding_hash": stored["binding_hash"],
    }
    receipt = {
        **common,
        "receipt_type": "end",
        "before_revision": execution["start_revision"],
        "after_revision": state["revision"],
        "changed_identities": [],
        "validations": [validation],
        "state_transitions": [],
        "open_issues": [],
    }
    return receipt, resolution


def scenario_artifact_guard() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-artifact-guard-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        redundant = artifact_proposal(
            "README.md", ["q1"], "working", artifact_class="control"
        )
        assert_error(
            validate_artifact_proposal(redundant, root, state),
            "default_redundant_artifact_requires_registered_same_path_replacement",
        )
        no_consumer = artifact_proposal("results/model.json", [], "working")
        assert_error(
            validate_artifact_proposal(no_consumer, root, state),
            "consumer_ids_invalid",
        )
        admitted = artifact_proposal("results/model.json", ["q1"], "working")
        assert validate_artifact_proposal(admitted, root, state) == []


def scenario_g1_init_minimal() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-g1-init-") as raw:
        root = Path(raw)
        state = init_project(root)
        assert state["schema_version"] == "11.0"
        for forbidden in ("executions", "workspace_manifest", "last_route"):
            assert forbidden not in state, forbidden
        assert "root_fingerprint" not in state["project"]
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        assert "executions" not in state and "workspace_manifest" not in state


def scenario_schema_strict() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-schema-") as raw:
        root = Path(raw)
        state = init_project(root)
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        state["unexpected"] = True
        assert_error(validate_state_semantics(state, root), "additionalProperties")
        bad = typed_evidence(root, "q1", "scope", "EV-BAD-LEVEL")
        bad["level"] = "unknown_level"
        bad["binding_hash"] = evidence_binding_hash(
            "q1", bad["level"], bad["input_refs"], bad["claim_refs"]
        )
        path = root / ".modeling/evidence-records/bad-level.json"
        dump_json(path, bad)
        must_raise(
            lambda: do_record_evidence(args(
                project_root=root,
                component_id="q1",
                evidence=path,
                replace=False,
            )),
            "evidence_bad_level",
        )


def scenario_typed_exact_evidence() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-evidence-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        _, identity = register_artifact(
            root, "results/current.txt", "q1", ["q1"], identity_class="working"
        )
        ref = [{
            "kind": "artifact", "id": "results/current.txt",
            "identity": identity, "facet": "result",
        }]
        valid = typed_evidence(
            root,
            "q1",
            "result_claims",
            "EV-EXACT",
            input_refs=ref,
            locator_artifact="results/current.txt",
        )
        bad_binding = copy.deepcopy(valid)
        bad_binding["id"] = "EV-BAD-BINDING"
        bad_binding["binding_hash"] = "0" * 64
        bad_path = root / ".modeling/evidence-records/bad-binding.json"
        dump_json(bad_path, bad_binding)
        must_raise(
            lambda: do_record_evidence(args(
                project_root=root,
                component_id="q1",
                evidence=bad_path,
                replace=False,
            )),
            "evidence_binding_hash_stale",
        )
        stale_ref = copy.deepcopy(valid)
        stale_ref["id"] = "EV-OLD-IDENTITY"
        stale_ref["input_refs"][0]["identity"] = "f" * 64
        stale_ref["binding_hash"] = evidence_binding_hash(
            "q1", stale_ref["level"], stale_ref["input_refs"], stale_ref["claim_refs"]
        )
        stale_path = root / ".modeling/evidence-records/old-identity.json"
        dump_json(stale_path, stale_ref)
        must_raise(
            lambda: do_record_evidence(args(
                project_root=root,
                component_id="q1",
                evidence=stale_path,
                replace=False,
            )),
            "evidence_input_artifact_stale",
        )
        valid_path = root / ".modeling/evidence-records/exact.json"
        dump_json(valid_path, valid)
        do_record_evidence(args(
            project_root=root,
            component_id="q1",
            evidence=valid_path,
            replace=False,
        ))
        state = load_json(root / ".modeling/state.json")
        assert state["components"]["q1"]["evidence"][-1]["binding_hash"] == valid["binding_hash"]


def scenario_s6_g2_evidence_hard() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-s6-hard-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        advance_question_to_s5(root)
        record_evidence(root, "q1", "E1_IMPLEMENTATION")
        message = must_raise(lambda: transition(root, "q1", "S6"), "E2_NUMERICAL")
        assert "E1_IMPLEMENTATION" not in message
        record_evidence(root, "q1", "E2_NUMERICAL")
        state = transition(root, "q1", "S6")
        assert state["components"]["q1"]["state"] == "S6"
        receipt, resolution = end_receipt(root)
        receipt["validations"] = []
        assert shape_errors(receipt)
        assert_error(validate_end(receipt, resolution, root), "checkpoint_validations_empty")


def scenario_s7_e1_e4_only() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-s7-e1-e4-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        advance_question_to_s6(root)
        record_evidence(root, "q1", "E3_STRUCTURAL")
        message = must_raise(lambda: transition(root, "q1", "S7"), "E4_REALITY")
        assert "result_claims" not in message
        assert "delivery_acceptance" not in message
        record_evidence(root, "q1", "E4_REALITY")
        state = transition(root, "q1", "S7")
        assert state["components"]["q1"]["state"] == "S7"
        assert state["history"][-1]["details"]["required"] == [
            "E1_IMPLEMENTATION", "E2_NUMERICAL", "E3_STRUCTURAL", "E4_REALITY",
        ]
        transition_project(root, "P1")
        must_raise(lambda: transition_project(root, "P2"), "delivery_acceptance")
        record_evidence(root, "q1", "delivery_acceptance")
        state = transition_project(root, "P2")
        assert state["project"]["state"] == "P2"
        record_evidence(
            root, "q1", "delivery_acceptance", "EV-q1-delivery-fail",
            status="fail",
        )
        assert load_json(root / ".modeling/state.json")["project"]["state"] == "P1"


def scenario_artifact_register_no_invalidate() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-register-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        record_evidence(root, "q1", "scope", "EV-BASELINE")
        before = load_json(root / ".modeling/state.json")
        state, _ = register_artifact(
            root, "results/working.txt", "q1", ["q1"], identity_class="working"
        )
        assert state["components"]["q1"]["status"] == before["components"]["q1"]["status"]
        assert state["components"]["q1"]["evidence"] == before["components"]["q1"]["evidence"]
        assert state["history"][-1]["details"]["affected_components"] == []


def scenario_working_refresh_exact() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-working-refresh-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "model", "question")
        add_component(root, "paper", "artifact", ["model"])
        _, old_identity = register_artifact(
            root,
            "results/working.txt",
            "model",
            ["paper"],
            identity_class="working",
        )
        ref = [{
            "kind": "artifact", "id": "results/working.txt",
            "identity": old_identity, "facet": "result",
        }]
        record_evidence(
            root,
            "model",
            "result_claims",
            "EV-OLD-WORKING",
            input_refs=ref,
            locator_artifact="results/working.txt",
        )
        record_evidence(root, "paper", "artifact_draft", "EV-UNRELATED")
        state = refresh_artifact(
            root, "results/working.txt", old_identity, "identity version two\n"
        )
        evidence = {
            item["id"]: item["status"]
            for component in state["components"].values()
            for item in component["evidence"]
        }
        assert evidence["EV-OLD-WORKING"] == "stale"
        assert evidence["EV-UNRELATED"] == "pass"
        assert {item["status"] for item in state["components"].values()} == {"active"}
        assert state["history"][-1]["details"]["affected_components"] == []


def scenario_protected_refresh_downstream() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-protected-refresh-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data", "shared_data")
        add_component(root, "model", "question", ["data"])
        add_component(root, "paper", "artifact", ["model"])
        add_component(root, "unrelated", "question", optional=True)
        _, old_identity = register_artifact(
            root,
            "results/frozen.txt",
            "model",
            ["paper"],
            identity_class="milestone",
        )
        (root / "results/frozen.txt").write_text("changed before refresh\n", encoding="utf-8")
        recovery = assess(root)
        assert recovery["level"] == "R1_TARGETED", recovery
        assert recovery["affected_components"] == ["model", "paper"]
        state = do_refresh_artifact(args(
            project_root=root,
            path="results/frozen.txt",
            expected_old_sha256=old_identity,
        ))
        statuses = {key: value["status"] for key, value in state["components"].items()}
        assert statuses == {
            "data": "active", "model": "invalidated",
            "paper": "invalidated", "unrelated": "active",
        }
        assert state["history"][-1]["details"]["affected_components"] == ["model", "paper"]


def scenario_claim_identity_exact() -> None:
    old_identity = "a" * 64
    new_identity = "b" * 64
    state = {
        "components": {
            "paper": {
                "status": "active",
                "evidence": [
                    {
                        "id": "EV-OLD-CLAIM", "status": "pass",
                        "claim_refs": ["claim:paper"],
                        "input_refs": [{
                            "kind": "claim", "id": "claim:model",
                            "identity": old_identity, "facet": "claim",
                        }],
                    },
                    {
                        "id": "EV-NEW-CLAIM", "status": "pass",
                        "claim_refs": ["claim:paper:new"],
                        "input_refs": [{
                            "kind": "claim", "id": "claim:model",
                            "identity": new_identity, "facet": "claim",
                        }],
                    },
                ],
            }
        }
    }
    components, evidence_ids, claim_ids = stale_exact_input_evidence(
        state, "claim", "claim:model", old_identity
    )
    assert components == ["paper"]
    assert evidence_ids == ["EV-OLD-CLAIM"]
    assert claim_ids == ["claim:paper"]
    assert state["components"]["paper"]["evidence"][0]["status"] == "stale"
    assert state["components"]["paper"]["evidence"][1]["status"] == "pass"
    assert state["components"]["paper"]["status"] == "active"


def scenario_revalidate_delta_only() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-revalidate-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        add_component(root, "paper", "artifact", ["q1"])
        advance_question_to_s6(root)
        state, old_identity = register_artifact(
            root,
            "results/milestone.txt",
            "q1",
            ["paper"],
            identity_class="milestone",
        )
        old_ref = [{
            "kind": "artifact", "id": "results/milestone.txt",
            "identity": old_identity, "facet": "result",
        }]
        record_evidence(
            root,
            "q1",
            "E2_NUMERICAL",
            "EV-q1-E2_NUMERICAL",
            replace=True,
            input_refs=old_ref,
            locator_artifact="results/milestone.txt",
        )
        before = load_json(root / ".modeling/state.json")
        unaffected_revisions = {
            item["id"]: item["recorded_revision"]
            for item in before["components"]["q1"]["evidence"]
            if item["id"] != "EV-q1-E2_NUMERICAL"
        }
        state = refresh_artifact(
            root,
            "results/milestone.txt",
            old_identity,
            "milestone identity version two\n",
        )
        assert state["components"]["q1"]["status"] == "invalidated"
        message = must_raise(
            lambda: do_revalidate_component(args(project_root=root, component_id="q1")),
            "E2_NUMERICAL",
        )
        for level in current_evidence_levels(state, "q1"):
            assert level != "E2_NUMERICAL"
        assert "E1_IMPLEMENTATION" not in message and "scope" not in message
        new_identity = state["artifacts"]["results/milestone.txt"]["sha256"]
        new_ref = [{
            "kind": "artifact", "id": "results/milestone.txt",
            "identity": new_identity, "facet": "result",
        }]
        record_evidence(
            root,
            "q1",
            "E2_NUMERICAL",
            "EV-q1-E2_NUMERICAL",
            replace=True,
            input_refs=new_ref,
            locator_artifact="results/milestone.txt",
        )
        state = do_revalidate_component(args(project_root=root, component_id="q1"))
        assert state["components"]["q1"]["status"] == "active"
        observed = {
            item["id"]: item["recorded_revision"]
            for item in state["components"]["q1"]["evidence"]
            if item["id"] in unaffected_revisions
        }
        assert observed == unaffected_revisions


def scenario_unregistered_dirty_ignored() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-dirty-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        dirty = root / "notes-in-progress.txt"
        dirty.write_text("draft one\n", encoding="utf-8")
        assert assess(root)["level"] == "R0_CONTINUE"
        dirty.write_text("draft two\n", encoding="utf-8")
        (root / "another-unregistered.bin").write_bytes(b"dirty")
        assert assess(root)["level"] == "R0_CONTINUE"


def scenario_recovery_r0() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-r0-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        register_artifact(
            root, "results/frozen.txt", "q1", ["q1"], identity_class="frozen"
        )
        result = assess(root)
        assert result["level"] == "R0_CONTINUE" and result["changed_paths"] == []


def scenario_recovery_r1_protected() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-r1-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "upstream", "shared_data")
        add_component(root, "owner", "question", ["upstream"])
        add_component(root, "downstream", "artifact", ["owner"])
        _, _ = register_artifact(
            root,
            "results/final.txt",
            "owner",
            ["downstream"],
            identity_class="final",
        )
        (root / "results/final.txt").write_text("changed final\n", encoding="utf-8")
        result = assess(root)
        assert result["level"] == "R1_TARGETED"
        assert result["affected_components"] == ["downstream", "owner"]
        assert "upstream" not in result["affected_components"]


def scenario_recovery_r2_explicit() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-r2-explicit-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        result = assess(root, explicit_full=True)
        assert result["level"] == "R2_FULL"
        assert result["reasons"] == ["explicit_full_recovery"]


def scenario_recovery_r2_missing() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-r2-missing-") as raw:
        result = assess(Path(raw))
        assert result["level"] == "R2_FULL" and result["state_valid"] is False
        assert "state_missing" in result["reasons"]


def scenario_recovery_r2_corrupt() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-r2-corrupt-") as raw:
        root = Path(raw)
        state = init_project(root)
        state["revision"] = "corrupt"
        dump_json(root / ".modeling/state.json", state)
        result = assess(root)
        assert result["level"] == "R2_FULL" and result["state_valid"] is False
        assert_error(result["reasons"], "state_revision_invalid")


def legacy_v9_state() -> dict[str, Any]:
    return {
        "schema_version": "9.0",
        "revision": 17,
        "project": {
            "id": "legacy-v9", "state": "P0", "required_components": ["q1"],
            "created_at": now_iso(), "updated_at": now_iso(),
        },
        "components": [
            {"id": "q1", "type": "question", "state": "S4", "status": "active"}
        ],
        "artifacts": [
            {"path": "results/q1.json", "sha256": "0" * 64, "producer": "q1"}
        ],
        "open_decisions": [], "next_actions": [], "history": [],
    }


def legacy_recovery_plan(include_solve: bool = False) -> dict[str, Any]:
    steps: list[dict[str, Any]] = [{
        "id": "recover", "tier": "G1_WORKING", "mode": "mutate",
        "object": "project", "action": "recover", "component_id": None,
        "events": ["recovery_assessment"], "facts": {},
        "working_context": {"component_type": "project", "state": "P0"},
        "depends_on": [],
        "change_set": {
            "paths": [".modeling/state.json"],
            "facets": ["identity_inventory", "known_gaps"], "claim_refs": [],
        },
    }]
    if include_solve:
        steps.append({
            "id": "solve", "tier": "G1_WORKING", "mode": "mutate",
            "object": "model", "action": "solve", "component_id": "q1",
            "events": ["model_execution"], "facts": {},
            "working_context": {"component_type": "question", "state": "S4"},
            "depends_on": ["recover"],
            "change_set": {
                "paths": ["results/q1.json"], "facets": ["computation"],
                "claim_refs": [],
            },
            "runtime_actions": [{
                "id": "solve-q1", "kind": "project_model_execution",
                "event": "model_execution", "repetition": "first_run",
                "scope": {
                    "kind": "component", "component_ids": ["q1"],
                    "input_paths": [], "output_paths": ["results/q1.json"],
                },
                "command": {
                    "argv": [sys.executable, "-c", "print('run')"],
                    "cwd": ".",
                },
                "authorization": {
                    "source": "direct_user_request",
                    "request_excerpt": "接手这个旧项目",
                },
            }],
        })
    return {
        "schema_version": "11.0", "plan_id": "PLAN-LEGACY-R2",
        "request": "接手这个旧项目，先按现有证据恢复；恢复完成后继续原计划。",
        "window_context": "new_window",
        "steps": steps,
    }


def scenario_legacy_v9_recovery_route() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-legacy-route-") as raw:
        root = Path(raw)
        dump_json(root / ".modeling/state.json", legacy_v9_state())
        observed = resolve(legacy_recovery_plan(), root)
        step = observed["steps"][0]
        assert observed["status"] == "resolved", observed
        assert step["route_id"] == "RT.PROJECT.RECOVER.MISSING", step
        assert step["state_source"] == "incompatible_authoritative_state"
        assert step["recovery"]["level"] == "R2_FULL"
        assert step["recovery"]["execution_boundary"]["recomputation_authorized"] is False
        assert "working_context_ignored_during_r2_binding" in step["warnings"]


def scenario_r2_blocks_same_plan_execution() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-r2-block-") as raw:
        root = Path(raw)
        dump_json(root / ".modeling/state.json", legacy_v9_state())
        observed = resolve(legacy_recovery_plan(include_solve=True), root)
        steps = {step["id"]: step for step in observed["steps"]}
        assert steps["recover"]["status"] == "resolved", observed
        assert steps["solve"]["status"] == "blocked", observed
        assert_error(steps["solve"]["reasons"], "r2_recovery_open")
        assert observed["action_grants"] == []


def scenario_r2_recovery_write_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-r2-scope-") as raw:
        root = Path(raw)
        dump_json(root / ".modeling/state.json", legacy_v9_state())
        allowed = legacy_recovery_plan()
        allowed["steps"][0]["change_set"]["paths"].append(
            ".modeling/recovery/v9-state.json"
        )
        assert resolve(allowed, root)["status"] == "resolved"
        for forbidden in ("README.md", "output/q1/result.json", "paper.tex"):
            plan = legacy_recovery_plan()
            plan["steps"][0]["change_set"]["paths"] = [forbidden]
            observed = resolve(plan, root)
            assert observed["status"] == "blocked", (forbidden, observed)
            assert_error(observed["steps"][0]["reasons"], "r2_recovery_write_outside_control_scope")


def scenario_r2_fresh_resolution_closes_barrier() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-r2-fresh-") as raw:
        root = Path(raw)
        plan = legacy_recovery_plan(include_solve=True)
        dump_json(root / ".modeling/state.json", legacy_v9_state())
        first = resolve(plan, root)
        assert first["recovery_posture"] == "R2_OPEN"
        assert first["steps"][1]["status"] == "blocked"
        (root / ".modeling/state.json").unlink()
        init_project(root, "migrated-v11")
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        state["components"]["q1"]["state"] = "S4"
        dump_json(root / ".modeling/state.json", state)
        second = resolve(plan, root)
        assert second["recovery_posture"] == "NORMAL", second
        assert [step["status"] for step in second["steps"]] == ["resolved", "resolved"]


def scenario_scope_paths_legacy_total() -> None:
    step = {
        "object": "project", "action": "recover", "tier": "G1_WORKING",
        "events": ["recovery_assessment"], "component_ids": [],
        "change_set": {"paths": [".modeling/state.json"]},
    }
    for components in ([], None, "legacy"):
        for artifacts in ([], None, "legacy", {}):
            state = {
                "project": {"id": "legacy", "required_components": ["q1"]},
                "components": components, "artifacts": artifacts,
            }
            assert scope_paths_for_step(state, step) == [".modeling/state.json"]


def scenario_pause_tier_and_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-pause-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q3", "question")
        add_component(root, "q4", "question", optional=True)
        resolved = resolve(pause_plan(), root)
        pause = resolved["steps"][0]
        assert resolved["status"] == "resolved", resolved
        assert pause["route_id"] == "RT.PROJECT.RESUME"
        assert pause["tier"] == "G1_WORKING" and pause["component_ids"] == []
        assert pause["events"] == ["handoff"] and pause["action_grants"] == []
        for tier, mode in (("G2_CHECKPOINT", "mutate"), ("G3_RELEASE", "mutate")):
            blocked = resolve(pause_plan(tier, mode), root)
            assert blocked["status"] == "blocked", blocked
            assert_error(blocked["steps"][0]["reasons"], "action_maximum_tier")


def scenario_close_then_pause_no_replay() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-close-pause-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q3", "question")
        add_component(root, "q4", "question", optional=True)
        advance_question_to_s6(root, "q3")
        record_evidence(root, "q3", "E3_STRUCTURAL")
        record_evidence(root, "q3", "E4_REALITY")
        plan = {
            "schema_version": "11.0", "plan_id": "PLAN-CLOSE-Q3-THEN-PAUSE",
            "request": "确认关闭第三问 S6，今天先到这里，做收尾整理。",
            "steps": [
                {
                    "id": "close-q3", "tier": "G2_CHECKPOINT", "mode": "promote",
                    "object": "verification", "action": "close_s6", "component_id": "q3",
                    "events": ["s6_close"], "facts": {}, "depends_on": [],
                    "change_set": {"paths": [], "facets": ["question_state"], "claim_refs": []},
                    "state_effect": {"component_id": "q3", "from": "S6", "to": "S7"},
                },
                {
                    "id": "pause", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "project", "action": "pause", "component_id": None,
                    "events": ["handoff"], "facts": {}, "depends_on": ["close-q3"],
                    "change_set": {"paths": [], "facets": ["next_actions"], "claim_refs": []},
                },
            ],
        }
        observed = resolve(plan, root)
        assert observed["status"] == "resolved", observed
        steps = {step["id"]: step for step in observed["steps"]}
        assert steps["close-q3"]["component_ids"] == ["q3"]
        assert steps["pause"]["component_ids"] == []
        all_events = {event for step in observed["steps"] for event in step["events"]}
        assert not all_events.intersection({
            "model_execution", "implementation_verification", "numerical_verification",
            "structural_verification", "reality_verification", "recovery_assessment",
            "final_delivery",
        })
        assert observed["action_grants"] == []


def scenario_runtime_action_wrapper() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-runtime-action-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        state["components"]["q1"]["state"] = "S4"
        dump_json(root / ".modeling/state.json", state)
        plan = model_runtime_plan()
        resolution = resolve(plan, root)
        assert resolution["status"] == "resolved", resolution
        assert len(resolution["action_grants"]) == 1
        report = execute_authorized_action(
            plan, root, "solve-q1", "run-q1",
            skill_root=Path(__file__).resolve().parents[1],
        )
        assert report["status"] == "pass" and (root / "marker.txt").read_text() == "ran"
        unauthorized_marker = root / "unauthorized.txt"
        must_raise(
            lambda: execute_authorized_action(
                pause_plan(), root, "pause", "run-q4",
                skill_root=Path(__file__).resolve().parents[1],
            ),
            "no executable grant",
        )
        assert not unauthorized_marker.exists()


def scenario_quick_validate_context_guard() -> None:
    skill_root = Path(__file__).resolve().parents[1]
    command = [
        sys.executable, "-B", str(skill_root / "scripts/quick_validate.py"),
        "--root", str(skill_root),
    ]
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    without_context = subprocess.run(
        command, cwd=skill_root, env=environment, text=True,
        capture_output=True, check=False,
    )
    assert without_context.returncode == 2
    release_without_authority = subprocess.run(
        [*command, "--invocation-context", "skill-release"],
        cwd=skill_root, env=environment, text=True, capture_output=True, check=False,
    )
    assert release_without_authority.returncode == 2
    payload = json.loads(release_without_authority.stdout)
    assert payload["error"] == "skill_package_validation_not_authorized_for_invocation_context"


def scenario_recovery_g3_scoped_r0() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-g3-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        result = assess(root, gate="G3")
        assert result["level"] == "R0_CONTINUE"
        assert result["reasons"] == ["protected_registered_identities_consistent"]
        assert result["required_scope"] == "declared_release_identity_and_evidence_scope"


def scenario_s6_no_full_recovery() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-s6-recovery-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        advance_question_to_s6(root)
        state = load_json(root / ".modeling/state.json")
        assert state["components"]["q1"]["state"] == "S6"
        assert assess(root, gate="G1")["level"] == "R0_CONTINUE"
        assert assess(root, gate="G2")["level"] == "R0_CONTINUE"


def scenario_checkpoint_no_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-checkpoint-") as raw:
        root = Path(raw)
        state = init_project(root)
        add_component(root, "q1", "question")
        (root / "unregistered.tmp").write_text("ordinary edit\n", encoding="utf-8")
        state = load_json(root / ".modeling/state.json")
        state = do_checkpoint(args(
            project_root=root,
            expected_revision=state["revision"],
            gate="G2",
        ))
        assert state["history"][-1]["event"] == "identity_checkpoint"
        assert "workspace_manifest" not in state
        assert "expected_manifest_sha256" not in state["history"][-1]["details"]


def scenario_checkpoint_scoped_recovery() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-checkpoint-scope-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        add_component(root, "optional", "question", optional=True)
        _, _ = register_artifact(
            root, "results/q1-milestone.txt", "q1", ["q1"],
            identity_class="milestone",
        )
        _, _ = register_artifact(
            root, "results/optional-milestone.txt", "optional", ["optional"],
            identity_class="milestone",
        )
        _, _ = register_artifact(
            root, "delivery/optional-package.txt", "optional", ["optional"],
            identity_class="final", artifact_class="delivery", role="delivery",
        )
        (root / "results/optional-milestone.txt").write_text(
            "optional identity changed\n", encoding="utf-8"
        )
        (root / "delivery/optional-package.txt").write_text(
            "optional delivery changed\n", encoding="utf-8"
        )
        assert assess(root, gate="G2")["level"] == "R1_TARGETED"
        plan = g2_recovery_plan()
        plan_path = root / ".modeling/checkpoint-plan.json"
        dump_json(plan_path, plan)
        before = load_json(root / ".modeling/state.json")
        state = do_checkpoint(args(
            project_root=root,
            expected_revision=before["revision"],
            gate="G2",
            plan=plan_path,
            step_id="resume",
        ))
        details = state["history"][-1]["details"]
        assert details["recovery_level"] == "R0_CONTINUE"
        assert details["scope_paths"] == ["results/q1-milestone.txt"]
        must_raise(
            lambda: do_checkpoint(args(
                project_root=root,
                expected_revision=state["revision"],
                gate="G3",
            )),
            "G3 release audit requires a consistent delivery closure",
        )
        (root / "results/q1-milestone.txt").write_text(
            "required identity changed\n", encoding="utf-8"
        )
        must_raise(
            lambda: do_checkpoint(args(
                project_root=root,
                expected_revision=state["revision"],
                gate="G2",
                plan=plan_path,
                step_id="resume",
            )),
            "consistent protected identities",
        )


def scenario_semantic_plan_route_no_manifest() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-route-") as raw:
        root = Path(raw)
        init_project(root)
        advisory = advisory_plan()
        advisory_path = root / ".modeling/advisory-plan.json"
        dump_json(advisory_path, advisory)
        must_raise(
            lambda: do_record_route(args(
                project_root=root,
                plan=advisory_path,
                step_id="advise",
                execution_id="EXEC-V11-G0",
            )),
            "execution ledger is reserved for G2/G3 formal steps",
        )
        state = load_json(root / ".modeling/state.json")
        assert "executions" not in state

        plan = g2_recovery_plan()
        plan_path = root / ".modeling/formal-plan.json"
        dump_json(plan_path, plan)
        state = do_record_route(args(
            project_root=root,
            plan=plan_path,
            step_id="resume",
            execution_id="EXEC-V11-PLAN",
        ))
        execution = state["executions"]["EXEC-V11-PLAN"]
        assert execution["plan_hash"] == resolve(plan, root)["plan_hash"]
        assert "start_manifest" not in execution and "start_manifest_sha256" not in execution
        assert "workspace_manifest" not in state


def scenario_receipt_start_authenticity() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-receipt-start-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        receipt, resolution = start_receipt(root)
        assert shape_errors(receipt) == []
        assert validate_start(receipt, resolution, root) == []
        forged = copy.deepcopy(receipt)
        forged["state_revision"] += 1
        forged["rule_ids"] = forged["rule_ids"][:-1]
        forged["pair_hash"] = "0" * 64
        errors = validate_start(forged, resolution, root)
        assert_error(errors, "state_revision_mismatch")
        assert_error(errors, "rule_ids_mismatch")
        assert_error(errors, "receipt_pair_hash_mismatch")
        no_execution = copy.deepcopy(receipt)
        no_execution["execution_id"] = None
        assert shape_errors(no_execution)


def scenario_receipt_end_authenticity() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-receipt-end-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        receipt, resolution = end_receipt(root)
        assert shape_errors(receipt) == []
        assert validate_end(receipt, resolution, root) == []
        forged = copy.deepcopy(receipt)
        forged["after_revision"] += 1
        forged["validations"][0]["binding_hash"] = "0" * 64
        errors = validate_end(forged, resolution, root)
        assert_error(errors, "after_revision_mismatch")
        assert_error(errors, "validation_binding_hash_mismatch")
        skipped_interval = copy.deepcopy(receipt)
        skipped_interval["before_revision"] = skipped_interval["after_revision"]
        assert_error(
            validate_end(skipped_interval, resolution, root),
            "before_revision_not_execution_start",
        )
        nonexistent = copy.deepcopy(receipt)
        nonexistent["validations"][0]["id"] = "EV-NOT-IN-STATE"
        nonexistent["validations"][0]["evidence_ref"] = (
            "state:components/q1/evidence/EV-NOT-IN-STATE"
        )
        assert_error(
            validate_end(nonexistent, resolution, root),
            "validation_evidence_not_registered",
        )
        failed = copy.deepcopy(receipt)
        failed["validations"][0]["status"] = "fail"
        assert shape_errors(failed)


def scenario_receipt_end_start_binding() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-receipt-start-binding-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        advance_question_to_s6(root)
        record_evidence(root, "q1", "E3_STRUCTURAL")
        record_evidence(root, "q1", "E4_REALITY")
        plan = s6_close_plan()
        plan_path = root / ".modeling/s6-close-plan.json"
        dump_json(plan_path, plan)
        state = do_record_route(args(
            project_root=root,
            plan=plan_path,
            step_id="close",
            execution_id="EXEC-V11-S6-CLOSE",
        ))
        execution = state["executions"]["EXEC-V11-S6-CLOSE"]
        transition(root, "q1", "S7")
        state = load_json(root / ".modeling/state.json")
        after_resolution = resolve(plan, root)
        after_step = next(item for item in after_resolution["steps"] if item["id"] == "close")
        assert after_step["status"] == "blocked"
        receipt = {
            "receipt_type": "end",
            "schema_version": "11.0",
            "request": execution["request"],
            "request_hash": execution["request_hash"],
            "semantic_plan": plan,
            "plan_hash": execution["plan_hash"],
            "step_id": "close",
            "execution_id": execution["id"],
            "pair_hash": checkpoint_pair_hash(execution),
            "project_root": str(root.resolve()),
            "tier": "G2_CHECKPOINT",
            "mode": execution["mode"],
            "route_ids": execution["route_ids"],
            "rule_ids": execution["rule_ids"],
            "component_ids": execution["component_ids"],
            "before_revision": execution["start_revision"],
            "after_revision": state["revision"],
            "change_set": plan["steps"][0]["change_set"],
            "changed_identities": [],
            "validations": [
                receipt_validation(state, "q1", f"EV-q1-{level}")
                for level in (
                    "E1_IMPLEMENTATION", "E2_NUMERICAL",
                    "E3_STRUCTURAL", "E4_REALITY",
                )
            ],
            "state_transitions": [
                {"component_id": "q1", "from": "S6", "to": "S7"},
            ],
            "open_issues": [],
        }
        assert shape_errors(receipt) == []
        assert validate_end(receipt, None, root) == []
        assert validate_end(receipt, after_resolution, root) == []
        incomplete = copy.deepcopy(receipt)
        incomplete["validations"] = incomplete["validations"][:-1]
        assert_error(
            validate_end(incomplete, None, root),
            "transition_validation_missing:q1:E4_REALITY",
        )


def scenario_project_gate_scoped_invalidation() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-project-gate-scope-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        add_component(root, "delivery", "question", optional=True)
        add_component(root, "notes", "question", optional=True)
        advance_question_to_s6(root)
        _, delivery_identity = register_artifact(
            root,
            "delivery/package.txt",
            "delivery",
            ["delivery"],
            identity_class="final",
            artifact_class="delivery",
            role="delivery",
        )
        delivery_ref = [{
            "kind": "artifact", "id": "delivery/package.txt",
            "identity": delivery_identity, "facet": "result",
        }]
        record_evidence(
            root,
            "delivery",
            "delivery_acceptance",
            "EV-DELIVERY-PASS-1",
            input_refs=delivery_ref,
            locator_artifact="delivery/package.txt",
        )
        record_evidence(root, "q1", "E3_STRUCTURAL")
        record_evidence(root, "q1", "E4_REALITY")
        transition(root, "q1", "S7")
        transition_project(root, "P1")
        state = transition_project(root, "P2")
        assert state["project"]["state"] == "P2"

        record_evidence(
            root, "notes", "uncertainty", "EV-NOTES-FAIL", status="fail"
        )
        state, notes_identity = register_artifact(
            root,
            "results/notes-milestone.txt",
            "notes",
            ["notes"],
            identity_class="milestone",
        )
        assert state["project"]["state"] == "P2"
        state = refresh_artifact(
            root,
            "results/notes-milestone.txt",
            notes_identity,
            "optional notes changed\n",
        )
        assert state["project"]["state"] == "P2"
        record_evidence(
            root, "delivery", "uncertainty", "EV-DELIVERY-UNRELATED-FAIL",
            status="fail",
        )
        assert load_json(root / ".modeling/state.json")["project"]["state"] == "P2"

        record_evidence(
            root,
            "delivery",
            "delivery_acceptance",
            "EV-DELIVERY-FAIL",
            status="fail",
        )
        state = load_json(root / ".modeling/state.json")
        assert state["project"]["state"] == "P1"
        record_evidence(
            root,
            "delivery",
            "delivery_acceptance",
            "EV-DELIVERY-PASS-2",
            input_refs=delivery_ref,
            locator_artifact="delivery/package.txt",
        )
        state = transition_project(root, "P2")
        assert state["project"]["state"] == "P2"

        state, _ = register_artifact(
            root,
            "delivery/supplement.txt",
            "delivery",
            ["delivery"],
            identity_class="final",
            artifact_class="delivery",
            role="delivery",
        )
        assert state["project"]["state"] == "P1"
        transition_project(root, "P2")
        state = refresh_artifact(
            root,
            "delivery/package.txt",
            delivery_identity,
            "delivery package changed\n",
        )
        assert state["project"]["state"] == "P1"

        new_delivery_identity = state["artifacts"]["delivery/package.txt"]["sha256"]
        new_delivery_ref = [{
            "kind": "artifact", "id": "delivery/package.txt",
            "identity": new_delivery_identity, "facet": "result",
        }]
        record_evidence(
            root,
            "delivery",
            "delivery_acceptance",
            "EV-DELIVERY-PASS-3",
            input_refs=new_delivery_ref,
            locator_artifact="delivery/package.txt",
        )
        do_revalidate_component(args(project_root=root, component_id="delivery"))
        transition_project(root, "P2")
        state, q1_identity = register_artifact(
            root,
            "results/q1-ready.txt",
            "q1",
            ["q1"],
            identity_class="milestone",
        )
        assert state["project"]["state"] == "P2"
        state = refresh_artifact(
            root,
            "results/q1-ready.txt",
            q1_identity,
            "required result changed\n",
        )
        assert state["project"]["state"] == "P0"


def scenario_open_decision_lifecycle() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-open-decision-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q3", "question")
        do_add_open_decision(args(
            project_root=root,
            decision_id="DEC-Q3",
            subject="Q3 最终方案选择",
            option=["A3-400", "A2-325"],
            affects=["q3"],
        ))
        state = load_json(root / ".modeling/state.json")
        assert any(item["id"] == "DEC-Q3" and item["status"] == "open" for item in state["open_decisions"])
        do_resolve_open_decision(args(
            project_root=root,
            decision_id="DEC-Q3",
            selected="A3-400",
        ))
        state = load_json(root / ".modeling/state.json")
        decision = next(item for item in state["open_decisions"] if item["id"] == "DEC-Q3")
        assert decision["status"] == "resolved" and decision["selected"] == "A3-400"


def scenario_checkpoint_before_interrupt_single_file() -> None:
    with tempfile.TemporaryDirectory(prefix="v11-interrupt-checkpoint-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        do_checkpoint_before_interrupt(args(
            project_root=root,
            reason="context window near limit",
        ))
        state = load_json(root / ".modeling/state.json")
        assert state["history"][-1]["event"] == "control_checkpoint_before_interrupt"
        assert state["history"][-1]["details"]["reason"] == "context window near limit"
        # V11 native state remains a single control file: no HANDOFF, no separate manifest.
        assert not (root / "HANDOFF.md").exists()
        assert not (root / "project_state.json").exists()


SCENARIOS: dict[str, Callable[[], None]] = {
    "g1_init_minimal": scenario_g1_init_minimal,
    "schema_strict": scenario_schema_strict,
    "typed_exact_evidence": scenario_typed_exact_evidence,
    "s6_g2_evidence_hard": scenario_s6_g2_evidence_hard,
    "s7_e1_e4_only": scenario_s7_e1_e4_only,
    "artifact_guard": scenario_artifact_guard,
    "artifact_register_no_invalidate": scenario_artifact_register_no_invalidate,
    "working_refresh_exact": scenario_working_refresh_exact,
    "protected_refresh_downstream": scenario_protected_refresh_downstream,
    "claim_identity_exact": scenario_claim_identity_exact,
    "revalidate_delta_only": scenario_revalidate_delta_only,
    "unregistered_dirty_ignored": scenario_unregistered_dirty_ignored,
    "recovery_r0": scenario_recovery_r0,
    "recovery_r1_protected": scenario_recovery_r1_protected,
    "recovery_r2_explicit": scenario_recovery_r2_explicit,
    "recovery_r2_missing": scenario_recovery_r2_missing,
    "recovery_r2_corrupt": scenario_recovery_r2_corrupt,
    "legacy_v9_recovery_route": scenario_legacy_v9_recovery_route,
    "r2_blocks_same_plan_execution": scenario_r2_blocks_same_plan_execution,
    "r2_recovery_write_scope": scenario_r2_recovery_write_scope,
    "r2_fresh_resolution_closes_barrier": scenario_r2_fresh_resolution_closes_barrier,
    "scope_paths_legacy_total": scenario_scope_paths_legacy_total,
    "pause_tier_and_scope": scenario_pause_tier_and_scope,
    "close_then_pause_no_replay": scenario_close_then_pause_no_replay,
    "runtime_action_wrapper": scenario_runtime_action_wrapper,
    "quick_validate_context_guard": scenario_quick_validate_context_guard,
    "recovery_g3_scoped_r0": scenario_recovery_g3_scoped_r0,
    "s6_no_full_recovery": scenario_s6_no_full_recovery,
    "checkpoint_no_manifest": scenario_checkpoint_no_manifest,
    "checkpoint_scoped_recovery": scenario_checkpoint_scoped_recovery,
    "semantic_plan_route_no_manifest": scenario_semantic_plan_route_no_manifest,
    "receipt_start_authenticity": scenario_receipt_start_authenticity,
    "receipt_end_authenticity": scenario_receipt_end_authenticity,
    "receipt_end_start_binding": scenario_receipt_end_start_binding,
    "project_gate_scoped_invalidation": scenario_project_gate_scoped_invalidation,
    "open_decision_lifecycle": scenario_open_decision_lifecycle,
    "checkpoint_before_interrupt_single_file": scenario_checkpoint_before_interrupt_single_file,
}


def selected_cases(root: Path) -> list[dict[str, Any]]:
    payload = load_json(root / "evals/contract-cases.json")
    return [
        case for case in payload.get("cases", [])
        if case.get("kind") == "scenario" and case.get("driver") == "scenario_tests"
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    cli = parser.parse_args()
    cases = selected_cases(cli.root.resolve())
    results: list[dict[str, Any]] = []
    for case in cases:
        scenario = str(case.get("scenario"))
        handler = SCENARIOS.get(scenario)
        if handler is None:
            status, error = "fail", "scenario implementation missing"
        else:
            try:
                handler()
                status, error = "pass", None
            except Exception as exc:  # isolate and report every active contract case
                status, error = "fail", f"{type(exc).__name__}: {exc}"
        results.append({
            "id": case.get("id"),
            "scenario": scenario,
            "status": status,
            "error": error,
        })
    failed = sum(item["status"] != "pass" for item in results)
    report = {
        "schema_version": "11.0",
        "status": "pass" if failed == 0 else "fail",
        "total": len(results),
        "passed": len(results) - failed,
        "failed": failed,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
