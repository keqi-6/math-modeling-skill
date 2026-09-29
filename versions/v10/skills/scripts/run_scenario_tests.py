#!/usr/bin/env python3
"""Exercise V10 state, recovery, artifact, and receipt contracts on real fixtures."""

from __future__ import annotations

import argparse
import copy
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from assess_recovery import assess
from lib_v10 import (
    ContractError, SKILL_ROOT, STRONG_EVIDENCE_KINDS, component_subject_hash,
    dump_json, load_json, manifest_sha256, now_iso, sha256_file,
    validate_artifact_proposal, validate_evidence, validate_state_semantics,
)
from resolve_route import resolve
from state_manager import (
    do_add_component, do_checkpoint, do_close_execution, do_init, do_record_evidence,
    do_inspect, do_record_route, do_refresh_artifact, do_register_artifact, do_set_next,
    do_set_dependencies, do_transition, do_validate_artifact,
    do_revalidate_component,
)
from validate_receipt import shape_errors, validate_end, validate_start


def args(**values: Any) -> SimpleNamespace:
    return SimpleNamespace(**values)


def write_json(path: Path, value: Any) -> None:
    dump_json(path, value)


def init_project(root: Path, project_id: str = "fixture") -> dict[str, Any]:
    return do_init(args(project_root=root, project_id=project_id, watch_root=["."]))


def add_component(
    root: Path,
    component_id: str,
    component_type: str,
    dependencies: list[str] | None = None,
    optional: bool = False,
) -> dict[str, Any]:
    return do_add_component(args(
        project_root=root, component_id=component_id, type=component_type,
        dependency=dependencies or [], optional=optional,
    ))


def evidence_record(
    root: Path,
    component_id: str,
    level: str,
    evidence_id: str,
    status: str = "pass",
) -> dict[str, Any]:
    state = load_json(root / ".modeling/state.json")
    record: dict[str, Any] = {
        "id": evidence_id,
        "level": level,
        "status": status,
        "kind": "observation",
        "locator": {"subject": level, "method": "independent fixture assertion", "value": True},
        "claim": f"{level} was independently observed",
        "observed_at": now_iso(),
        "producer": "scenario_tests",
        "subject_id": component_id,
        "subject_hash": component_subject_hash(state, component_id),
    }
    allowed_kinds = STRONG_EVIDENCE_KINDS.get(level, set())
    if "file" in allowed_kinds:
        target = root / ".modeling/evidence-files" / f"{evidence_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"verified {level}\n", encoding="utf-8")
        record["kind"] = "file"
        record["locator"] = {
            "path": target.relative_to(root).as_posix(),
            "sha256": sha256_file(target),
        }
    elif "command" in allowed_kinds:
        target = root / ".modeling/evidence-files" / f"{evidence_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"verified {level}\n", encoding="utf-8")
        digest = sha256_file(target)
        record["kind"] = "command"
        record["locator"] = {
            "command_hash": digest,
            "exit_code": 0,
            "output_ref": target.relative_to(root).as_posix(),
            "output_sha256": digest,
        }
    elif "decision" in allowed_kinds:
        decision_id = f"DEC-{evidence_id}"
        state = load_json(root / ".modeling/state.json")
        timestamp = now_iso()
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
        record["kind"] = "decision"
        record["locator"] = {"decision_id": decision_id, "recorded_at": timestamp}
        record["subject_hash"] = component_subject_hash(state, component_id)
    return record


def record_level(
    root: Path,
    component_id: str,
    level: str,
    evidence_id: str | None = None,
    status: str = "pass",
) -> str:
    identifier = evidence_id or f"EV-{component_id}-{level}"
    path = root / ".modeling" / f"{identifier}.json"
    write_json(path, evidence_record(root, component_id, level, identifier, status=status))
    do_record_evidence(args(
        project_root=root, component_id=component_id, evidence=path, replace=False,
    ))
    return identifier


def transition(root: Path, component_id: str, target: str, reason_evidence_id: str | None = None) -> dict[str, Any]:
    return do_transition(args(
        project_root=root, project=False, component_id=component_id, to=target,
        reason=None, reason_evidence_id=reason_evidence_id,
    ))


def checkpoint(root: Path) -> dict[str, Any]:
    state = load_json(root / ".modeling/state.json")
    return do_checkpoint(args(
        project_root=root, expected_revision=state["revision"],
        expected_manifest_sha256=manifest_sha256(state["workspace_manifest"]),
    ))


def advance_artifact_to_a3(root: Path, component_id: str = "paper") -> dict[str, Any]:
    for target, level in (("A1", "artifact_draft"), ("A2", "artifact_validation"), ("A3", "artifact_acceptance")):
        record_level(root, component_id, level)
        transition(root, component_id, target)
    return load_json(root / ".modeling/state.json")


def advance_data_to_d3(root: Path, component_id: str = "data") -> dict[str, Any]:
    for level in ("data_identity", "provenance"):
        record_level(root, component_id, level)
    transition(root, component_id, "D1")
    for level in ("data_audit", "treatment_decision"):
        record_level(root, component_id, level)
    transition(root, component_id, "D2")
    for level in ("processed_identity", "artifact_validation"):
        record_level(root, component_id, level)
    transition(root, component_id, "D3")
    return load_json(root / ".modeling/state.json")


def advance_question_to_s6(root: Path, component_id: str = "q1") -> dict[str, Any]:
    for level in ("scope", "problem_definition"):
        record_level(root, component_id, level)
    transition(root, component_id, "S1")
    for target, levels in (
        ("S2", ["evidence_plan"]), ("S3", ["candidate_set"]),
        ("S4", ["model_spec", "selection_rationale"]),
        ("S5", ["implementation_ref"]),
        ("S6", ["E1_IMPLEMENTATION", "E2_NUMERICAL"]),
    ):
        for level in levels:
            record_level(root, component_id, level)
        transition(root, component_id, target)
    return load_json(root / ".modeling/state.json")


def advance_question_to_s7(root: Path, component_id: str = "q1") -> dict[str, Any]:
    advance_question_to_s6(root, component_id)
    for level in ("E3_STRUCTURAL", "E4_REALITY", "result_claims", "delivery_acceptance"):
        record_level(root, component_id, level)
    transition(root, component_id, "S7")
    return load_json(root / ".modeling/state.json")


def advance_question_to_state(root: Path, target: str, component_id: str = "q1") -> dict[str, Any]:
    sequence = (
        ("S1", ("scope", "problem_definition")),
        ("S2", ("evidence_plan",)),
        ("S3", ("candidate_set",)),
        ("S4", ("model_spec", "selection_rationale")),
        ("S5", ("implementation_ref",)),
        ("S6", ("E1_IMPLEMENTATION", "E2_NUMERICAL")),
        ("S7", ("E3_STRUCTURAL", "E4_REALITY", "result_claims", "delivery_acceptance")),
    )
    declared = {state for state, _ in sequence}
    if target not in declared:
        raise AssertionError(f"unsupported fixture target: {target}")
    for state_name, levels in sequence:
        for level in levels:
            record_level(root, component_id, level)
        transition(root, component_id, state_name)
        if state_name == target:
            return load_json(root / ".modeling/state.json")
    raise AssertionError(f"fixture did not reach {target}")


def must_raise(action: Callable[[], Any], contains: str | None = None) -> str:
    try:
        action()
    except ContractError as exc:
        message = str(exc)
        if contains is not None and contains not in message:
            raise AssertionError(f"expected error containing {contains!r}, got {message!r}") from exc
        return message
    raise AssertionError("expected ContractError, but action succeeded")


def proposal(path: str, consumers: list[str], artifact_class: str = "result") -> dict[str, Any]:
    return {
        "path": path,
        "purpose": "Provide a consumed, testable scenario artifact",
        "consumer_ids": consumers,
        "lifecycle": "milestone",
        "class": artifact_class,
        "authorization_basis": "scenario test request",
        "replaces": None,
    }


def scenario_artifact_guard() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-artifact-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        redundant = proposal("README.md", ["q1"], "control")
        errors = validate_artifact_proposal(redundant, root, load_json(root / ".modeling/state.json"))
        assert "default_redundant_artifact_requires_registered_same_path_replacement" in errors
        no_consumer = proposal("results/model.json", [])
        assert "consumer_ids_invalid" in validate_artifact_proposal(no_consumer, root, load_json(root / ".modeling/state.json"))
        admitted = proposal("results/model.json", ["q1"])
        assert validate_artifact_proposal(admitted, root, load_json(root / ".modeling/state.json")) == []
        target = root / admitted["path"]
        target.parent.mkdir(parents=True)
        target.write_text('{"value": 1}\n', encoding="utf-8")
        proposal_path = root / ".modeling/admitted.json"
        write_json(proposal_path, admitted)
        state = do_register_artifact(args(
            project_root=root, proposal=proposal_path, producer="q1", role="result",
        ))
        assert admitted["path"] in state["artifacts"]


def _resume_resolution(root: Path) -> tuple[str, dict[str, Any]]:
    request = "继续完成这个数学建模项目"
    resolution = resolve(request, root, None)
    assert resolution["status"] == "resolved", resolution
    return request, resolution


def _component_ids(resolution: dict[str, Any]) -> list[str]:
    return sorted({item for node in resolution["route_nodes"] for item in node["component_ids"]})


def scenario_spoof_start_receipt() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-receipt-start-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        checkpoint(root)
        request, _ = _resume_resolution(root)
        state = do_record_route(args(
            project_root=root, request=request, execution_id="EXEC-START", component_id=None,
        ))
        resolution = resolve(request, root, None)
        execution = state["executions"]["EXEC-START"]
        receipt = {
            "receipt_type": "start", "schema_version": "10.0", "request": request,
            "request_hash": resolution["request_hash"], "project_root": str(root.resolve()),
            "execution_id": "EXEC-START", "component_id": None, "component_map": {},
            "mode": resolution["mode"], "route_ids": resolution["route_ids"],
            "rule_ids": resolution["rule_ids"], "component_ids": _component_ids(resolution),
            "state_revision": execution["start_revision"], "recovery": execution["recovery"],
            "planned_artifacts": [], "blocked": not execution["write_authorized"],
        }
        assert shape_errors(receipt) == []
        assert validate_start(receipt, resolution, root) == []
        spoofed = copy.deepcopy(receipt)
        spoofed["route_ids"] = ["RT.DELIVERY.FINAL"]
        spoofed["recovery"] = "R2_FULL"
        errors = validate_start(spoofed, resolution, root)
        assert "route_ids_mismatch" in errors and "recovery_mismatch" in errors


def scenario_spoof_end_receipt() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-receipt-end-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        request, resolution = _resume_resolution(root)
        state = do_record_route(args(
            project_root=root, request=request, execution_id="EXEC-END", component_id=None,
        ))
        execution = state["executions"]["EXEC-END"]
        current = resolve(request, root, None)
        receipt = {
            "receipt_type": "end", "schema_version": "10.0", "request": request,
            "request_hash": resolution["request_hash"], "project_root": str(root.resolve()),
            "execution_id": "EXEC-END", "component_id": None, "component_map": {},
            "mode": resolution["mode"], "route_ids": resolution["route_ids"],
            "rule_ids": resolution["rule_ids"], "component_ids": _component_ids(resolution),
            "before_revision": execution["start_revision"], "after_revision": state["revision"],
            "changed_artifacts": [], "validations": [], "state_transitions": [],
            "open_issues": [], "next_actions": [],
        }
        assert shape_errors(receipt) == []
        assert validate_end(receipt, current, root) == []
        spoofed = copy.deepcopy(receipt)
        spoofed["after_revision"] += 1
        spoofed["rule_ids"] = spoofed["rule_ids"][:-1]
        errors = validate_end(spoofed, current, root)
        assert "after_revision_mismatch" in errors and "execution_rule_ids_mismatch" in errors


def scenario_state_type_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-state-type-") as raw:
        root = Path(raw)
        state = init_project(root)
        state = add_component(root, "q1", "question")
        state["components"]["q1"]["state"] = "D1"
        assert any("state_type_mismatch" in item for item in validate_state_semantics(state, root, check_files=True))


def scenario_string_evidence_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-state-evidence-") as raw:
        root = Path(raw)
        init_project(root)
        state = add_component(root, "q1", "question")
        state["components"]["q1"]["evidence"].append("E1 passed")
        assert any("evidence_not_object" in item for item in validate_state_semantics(state, root, check_files=True))


def scenario_s6_gate_order() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-s6-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        for level in ("scope", "problem_definition"):
            record_level(root, "q1", level)
        transition(root, "q1", "S1")
        for target, levels in (
            ("S2", ["evidence_plan"]),
            ("S3", ["candidate_set"]),
            ("S4", ["model_spec", "selection_rationale"]),
            ("S5", ["implementation_ref"]),
        ):
            for level in levels:
                record_level(root, "q1", level)
            transition(root, "q1", target)
        record_level(root, "q1", "E1_IMPLEMENTATION")
        must_raise(lambda: transition(root, "q1", "S6"), "E2_NUMERICAL")
        record_level(root, "q1", "E2_NUMERICAL")
        transition(root, "q1", "S6")
        must_raise(lambda: transition(root, "q1", "S7"), "E3_STRUCTURAL")
        for level in ("E3_STRUCTURAL", "E4_REALITY", "result_claims", "delivery_acceptance"):
            record_level(root, "q1", level)
        final = transition(root, "q1", "S7")
        assert final["components"]["q1"]["status"] == "closed"


def scenario_controlled_reopen() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-reopen-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "paper", "artifact")
        for target, level in (("A1", "artifact_draft"), ("A2", "artifact_validation"), ("A3", "artifact_acceptance")):
            record_level(root, "paper", level)
            transition(root, "paper", target)
        must_raise(lambda: transition(root, "paper", "A1"), "selection_rationale")
        reason_id = record_level(root, "paper", "selection_rationale", "EV-REOPEN-NEW-EVIDENCE")
        reopened = transition(root, "paper", "A1", reason_id)
        assert reopened["components"]["paper"]["status"] == "active"


def scenario_route_record() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-route-record-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        request = "继续完成这个数学建模项目"
        resolution = resolve(request, root, None)
        assert resolution["status"] == "resolved"
        before = resolution["state_revision"]
        state = do_record_route(args(
            project_root=root, request=request, execution_id="EXEC-ROUTE", component_id=None,
        ))
        assert state["revision"] == before + 1
        assert state["last_route"]["request_hash"] == resolution["request_hash"]
        assert state["last_route"]["route_ids"] == resolution["route_ids"]


def scenario_artifact_identity() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-artifact-id-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        target = root / "results/value.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"value": 1}\n', encoding="utf-8")
        proposal_path = root / ".modeling/proposal.json"
        write_json(proposal_path, proposal("results/value.json", ["q1"]))
        state = do_register_artifact(args(
            project_root=root, proposal=proposal_path, producer="q1", role="result",
        ))
        old_hash = state["artifacts"]["results/value.json"]["sha256"]
        assert old_hash == sha256_file(target)
        validation = evidence_record(root, "q1", "artifact_validation", "EV-ARTIFACT-VALIDATE")
        validation["locator"] = {"path": "results/value.json", "sha256": old_hash}
        validation_path = root / ".modeling/artifact-validation.json"
        write_json(validation_path, validation)
        do_record_evidence(args(
            project_root=root, component_id="q1", evidence=validation_path, replace=False,
        ))
        validated = do_validate_artifact(args(
            project_root=root, path="results/value.json", evidence_id="EV-ARTIFACT-VALIDATE",
        ))
        assert validated["artifacts"]["results/value.json"]["status"] == "validated"
        target.write_text('{"value": 2}\n', encoding="utf-8")
        refreshed = do_refresh_artifact(args(
            project_root=root, path="results/value.json", expected_old_sha256=old_hash,
        ))
        assert refreshed["artifacts"]["results/value.json"]["sha256"] == sha256_file(target)
        assert refreshed["components"]["q1"]["status"] == "invalidated"


def scenario_dependency_cycle() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-cycle-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data", "shared_data")
        state = add_component(root, "q1", "question", ["data"])
        state["components"]["data"]["dependencies"] = ["q1"]
        state["components"]["q1"]["consumers"] = ["data"]
        errors = validate_state_semantics(state, root, check_files=True)
        assert any(item.startswith("component_dependency_cycle:") for item in errors)


def scenario_next_action() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-next-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        do_set_next(args(
            project_root=root, component_id="q1", action_id="NEXT-1",
            action="Define the objective", blocked_by=["DEC-1"],
        ))
        state = do_set_next(args(
            project_root=root, component_id="q1", action_id="NEXT-1",
            action="Verify the objective", blocked_by=[],
        ))
        assert state["next_actions"] == [{
            "id": "NEXT-1", "component_id": "q1", "action": "Verify the objective", "blocked_by": [],
        }]


def scenario_recovery_r0() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-r0-") as raw:
        root = Path(raw)
        init_project(root)
        checkpoint(root)
        result = assess(root)
        assert result["level"] == "R0_CONTINUE", result


def scenario_recovery_r1_transitive() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-r1-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data", "shared_data")
        add_component(root, "q1", "question", ["data"])
        add_component(root, "paper", "artifact", ["q1"])
        target = root / "data/processed.csv"
        target.parent.mkdir(parents=True)
        target.write_text("x\n1\n", encoding="utf-8")
        proposal_path = root / ".modeling/proposal.json"
        write_json(proposal_path, proposal("data/processed.csv", ["q1"], "data"))
        do_register_artifact(args(
            project_root=root, proposal=proposal_path, producer="data", role="intermediate",
        ))
        target.write_text("x\n2\n", encoding="utf-8")
        result = assess(root)
        assert result["level"] == "R1_TARGETED", result
        assert set(result["affected_components"]) == {"data", "q1", "paper"}, result


def scenario_recovery_r2_missing() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-r2-missing-") as raw:
        result = assess(Path(raw))
        assert result["level"] == "R2_FULL" and result["state_valid"] is False


def scenario_recovery_r2_invalid() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-r2-invalid-") as raw:
        root = Path(raw)
        state = init_project(root)
        state["project"]["root_fingerprint"] = "0" * 64
        write_json(root / ".modeling/state.json", state)
        result = assess(root)
        assert result["level"] == "R2_FULL" and "project_root_fingerprint_mismatch" in result["reasons"]


def scenario_schema_extra_unknown_level_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-schema-attack-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        item = evidence_record(root, "q1", "scope", "EV-BAD-SCHEMA")
        item["level"] = "E99_INVENTED"
        item["producer"] = ""
        item["observed_at"] = "not-a-time"
        item["extra"] = True
        errors = validate_evidence(item, root, True, state=state, component_id="q1", stored=False)
        assert {"evidence_bad_level", "evidence_producer_invalid", "evidence_observed_at_invalid"}.issubset(errors)
        assert any(error.startswith("evidence_extra:") for error in errors)


def scenario_passing_command_nonzero_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-command-attack-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        output = root / ".modeling/command-output.txt"
        output.write_text("failed\n", encoding="utf-8")
        state = load_json(root / ".modeling/state.json")
        item = evidence_record(root, "q1", "E1_IMPLEMENTATION", "EV-COMMAND-99")
        item["kind"] = "command"
        item["locator"] = {
            "command_hash": "a" * 64, "exit_code": 99,
            "output_ref": ".modeling/command-output.txt", "output_sha256": sha256_file(output),
        }
        errors = validate_evidence(item, root, True, state=state, component_id="q1", stored=False)
        assert "evidence_passing_command_nonzero_exit" in errors


def scenario_observation_only_s6_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-observation-attack-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        item = evidence_record(root, "q1", "scope", "EV-WEAK-E1")
        item["level"] = "E1_IMPLEMENTATION"
        errors = validate_evidence(item, root, True, state=state, component_id="q1", stored=False)
        assert "evidence_kind_too_weak_for_level" in errors


def scenario_stale_subject_hash_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-stale-subject-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        item = evidence_record(root, "q1", "scope", "EV-STALE-SUBJECT")
        item["subject_hash"] = "0" * 64
        errors = validate_evidence(item, root, True, state=state, component_id="q1", stored=False)
        assert "evidence_subject_hash_stale" in errors


def scenario_closed_evidence_write_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-closed-write-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "paper", "artifact")
        advance_artifact_to_a3(root)
        path = root / ".modeling/closed-write.json"
        write_json(path, evidence_record(root, "paper", "artifact_draft", "EV-CLOSED-WRITE"))
        must_raise(lambda: do_record_evidence(args(
            project_root=root, component_id="paper", evidence=path, replace=False,
        )), "closed component")


def scenario_stale_d3_reopen_reason_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-d3-stale-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data", "shared_data")
        advance_data_to_d3(root)
        must_raise(
            lambda: transition(root, "data", "D1", "EV-data-data_audit"),
            "stale",
        )


def scenario_stale_a3_reopen_reason_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-a3-stale-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "paper", "artifact")
        for target, level in (("A1", "artifact_draft"), ("A2", "artifact_validation")):
            record_level(root, "paper", level)
            transition(root, "paper", target)
        reason_id = record_level(root, "paper", "selection_rationale", "EV-OLD-REOPEN")
        record_level(root, "paper", "artifact_acceptance")
        transition(root, "paper", "A3")
        must_raise(lambda: transition(root, "paper", "A1", reason_id), "stale")


def scenario_reopen_immediate_reclose_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-reclose-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "paper", "artifact")
        advance_artifact_to_a3(root)
        reason_id = record_level(root, "paper", "selection_rationale", "EV-NEW-REOPEN")
        transition(root, "paper", "A1", reason_id)
        must_raise(lambda: transition(root, "paper", "A2"), "artifact_validation")


def scenario_model_redesign_reopen_matrix() -> None:
    for source_state in ("S4", "S5", "S6", "S7"):
        with tempfile.TemporaryDirectory(prefix=f"v10-redesign-{source_state.lower()}-") as raw:
            root = Path(raw)
            init_project(root)
            add_component(root, "q1", "question")
            add_component(root, "paper", "artifact", ["q1"], optional=True)
            advance_question_to_state(root, source_state)
            must_raise(lambda: transition(root, "q1", "S2"), "model_redesign_control")
            reason_id = record_level(
                root, "q1", "model_redesign_control",
                f"EV-REDESIGN-{source_state}",
            )
            record_level(
                root, "q1", "consumer_invalidation",
                f"EV-CONSUMER-INVALIDATION-{source_state}",
            )
            reopened = transition(root, "q1", "S2", reason_id)
            assert reopened["components"]["q1"]["state"] == "S2"
            assert reopened["components"]["q1"]["status"] == "active"
            assert reopened["components"]["paper"]["status"] == "invalidated"
            assert reopened["history"][-1]["details"]["affected_components"] == ["paper"]


def scenario_s7_failure_reopen_matrix() -> None:
    cases = (("E1_IMPLEMENTATION", "S5"), ("E3_STRUCTURAL", "S6"))
    for failure_level, target_state in cases:
        with tempfile.TemporaryDirectory(prefix=f"v10-s7-failure-{target_state.lower()}-") as raw:
            root = Path(raw)
            init_project(root)
            add_component(root, "q1", "question")
            add_component(root, "paper", "artifact", ["q1"], optional=True)
            advance_question_to_s7(root)
            reason_id = record_level(
                root, "q1", failure_level,
                f"EV-FAIL-{failure_level}", status="fail",
            )
            invalidated = load_json(root / ".modeling/state.json")
            assert invalidated["components"]["q1"]["status"] == "invalidated"
            assert invalidated["components"]["paper"]["status"] == "invalidated"
            record_level(
                root, "q1", "consumer_invalidation",
                f"EV-CONSUMER-INVALIDATION-{target_state}",
            )
            reopened = transition(root, "q1", target_state, reason_id)
            assert reopened["components"]["q1"]["state"] == target_state
            assert reopened["components"]["q1"]["status"] == "active"


def scenario_d3_reopen_invalidation() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-d3-reopen-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data", "shared_data")
        add_component(root, "q1", "question", ["data"], optional=True)
        advance_data_to_d3(root)
        reason_id = record_level(root, "data", "data_audit", "EV-D3-FRESH-AUDIT")
        reopened = transition(root, "data", "D1", reason_id)
        assert reopened["components"]["data"]["state"] == "D1"
        assert reopened["components"]["data"]["status"] == "active"
        assert reopened["components"]["q1"]["status"] == "invalidated"


def scenario_a3_reopen_resets_project() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-a3-project-reopen-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "paper", "artifact")
        add_component(root, "package", "artifact", ["paper"], optional=True)
        advance_artifact_to_a3(root)
        do_transition(args(
            project_root=root, project=True, component_id=None, to="P1",
            reason=None, reason_evidence_id=None,
        ))
        reason_id = record_level(root, "paper", "selection_rationale", "EV-A3-FRESH-REOPEN")
        reopened = transition(root, "paper", "A1", reason_id)
        assert reopened["project"]["state"] == "P0"
        assert reopened["components"]["paper"]["state"] == "A1"
        assert reopened["components"]["package"]["status"] == "invalidated"


def scenario_project_p2_reopen() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-p2-reopen-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "paper", "artifact")
        record_level(root, "paper", "artifact_draft")
        transition(root, "paper", "A1")
        record_level(root, "paper", "artifact_validation")
        transition(root, "paper", "A2")
        record_level(root, "paper", "delivery_acceptance")
        record_level(root, "paper", "artifact_acceptance")
        transition(root, "paper", "A3")
        do_transition(args(
            project_root=root, project=True, component_id=None, to="P1",
            reason=None, reason_evidence_id=None,
        ))
        do_transition(args(
            project_root=root, project=True, component_id=None, to="P2",
            reason=None, reason_evidence_id=None,
        ))
        reason_id = record_level(root, "paper", "selection_rationale", "EV-P2-FRESH-REOPEN")
        reopened = do_transition(args(
            project_root=root, project=True, component_id=None, to="P0",
            reason="authorized new release cycle", reason_evidence_id=reason_id,
        ))
        assert reopened["project"]["state"] == "P0"


def scenario_transitive_invalidation() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-transitive-invalid-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data", "shared_data")
        add_component(root, "q1", "question", ["data"])
        add_component(root, "paper", "artifact", ["q1"])
        target = root / "data/source.csv"
        target.parent.mkdir(parents=True)
        target.write_text("x\n1\n", encoding="utf-8")
        prop_path = root / ".modeling/transitive-proposal.json"
        write_json(prop_path, proposal("data/source.csv", ["q1"], "data"))
        registered = do_register_artifact(args(
            project_root=root, proposal=prop_path, producer="data", role="source",
        ))
        old_hash = registered["artifacts"]["data/source.csv"]["sha256"]
        target.write_text("x\n2\n", encoding="utf-8")
        refreshed = do_refresh_artifact(args(
            project_root=root, path="data/source.csv", expected_old_sha256=old_hash,
        ))
        assert all(refreshed["components"][item]["status"] == "invalidated" for item in ("data", "q1", "paper"))


def scenario_invalidated_s6_recovery() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-s6-revalidate-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        advance_question_to_s6(root)
        target = root / "results/model.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"v": 1}\n', encoding="utf-8")
        prop_path = root / ".modeling/s6-proposal.json"
        write_json(prop_path, proposal("results/model.json", ["q1"]))
        state = do_register_artifact(args(
            project_root=root, proposal=prop_path, producer="q1", role="result",
        ))
        assert state["components"]["q1"]["state"] == "S6" and state["components"]["q1"]["status"] == "invalidated"
        must_raise(lambda: do_revalidate_component(args(project_root=root, component_id="q1")), "fresh evidence")
        for level in sorted({
            "scope", "problem_definition", "evidence_plan", "candidate_set", "model_spec",
            "selection_rationale", "implementation_ref", "E1_IMPLEMENTATION", "E2_NUMERICAL",
        }):
            record_level(root, "q1", level, "EV-FRESH-" + level)
        recovered = do_revalidate_component(args(project_root=root, component_id="q1"))
        assert recovered["components"]["q1"]["status"] == "active"


def scenario_dependency_change_transitive() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-dependency-change-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data1", "shared_data")
        add_component(root, "data2", "shared_data")
        add_component(root, "q1", "question", ["data1"])
        add_component(root, "paper", "artifact", ["q1"])
        state = do_set_dependencies(args(project_root=root, component_id="q1", dependency=["data2"]))
        assert state["components"]["q1"]["status"] == "invalidated"
        assert state["components"]["paper"]["status"] == "invalidated"
        assert state["components"]["data1"]["consumers"] == []


def scenario_checkpoint_launder_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-checkpoint-launder-") as raw:
        root = Path(raw)
        init_project(root)
        rogue = root / "rogue.txt"
        rogue.write_text("unowned\n", encoding="utf-8")
        before_hash = sha256_file(root / ".modeling/state.json")
        state = load_json(root / ".modeling/state.json")
        assert assess(root)["level"] == "R2_FULL"
        must_raise(lambda: do_checkpoint(args(
            project_root=root, expected_revision=state["revision"],
            expected_manifest_sha256=manifest_sha256(state["workspace_manifest"]),
        )), "R0")
        assert sha256_file(root / ".modeling/state.json") == before_hash
        assert assess(root)["level"] == "R2_FULL"


def scenario_watch_root_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-watch-root-") as raw:
        base = Path(raw)
        must_raise(lambda: do_init(args(project_root=base / "escape", project_id="p", watch_root=["../outside"])), "escapes")
        must_raise(lambda: do_init(args(project_root=base / "missing", project_id="p", watch_root=["not-there"])), "does not exist")
        root = base / "symlink"
        init_project(root)
        (root / "outside-link").symlink_to("/etc/hosts")
        result = assess(root)
        assert result["level"] == "R2_FULL" and any("escapes project root" in item for item in result["reasons"])
        state = load_json(root / ".modeling/state.json")
        state["watch_roots"] = []
        assert "watch_roots_invalid" in validate_state_semantics(state, root, check_files=True)


def canonical_start_receipt(root: Path, request: str, execution_id: str, component_id: str | None = None) -> dict[str, Any]:
    state = load_json(root / ".modeling/state.json")
    execution = state["executions"][execution_id]
    return {
        "receipt_type": "start", "schema_version": "10.0", "request": request,
        "request_hash": execution["request_hash"], "project_root": str(root.resolve()),
        "execution_id": execution_id, "component_id": component_id,
        "component_map": execution.get("component_map", {}), "mode": execution["mode"],
        "route_ids": execution["route_ids"], "rule_ids": execution["rule_ids"],
        "component_ids": execution["component_ids"], "state_revision": execution["start_revision"],
        "recovery": execution["recovery"], "planned_artifacts": [],
        "blocked": execution["mode"] in {"mutate", "promote", "skill_maintenance"} and not execution["write_authorized"],
    }


def canonical_end_receipt(root: Path, request: str, execution_id: str, component_id: str | None = None) -> dict[str, Any]:
    state = load_json(root / ".modeling/state.json")
    execution = state["executions"][execution_id]
    return {
        "receipt_type": "end", "schema_version": "10.0", "request": request,
        "request_hash": execution["request_hash"], "project_root": str(root.resolve()),
        "execution_id": execution_id, "component_id": component_id,
        "component_map": execution.get("component_map", {}), "mode": execution["mode"],
        "route_ids": execution["route_ids"], "rule_ids": execution["rule_ids"],
        "component_ids": execution["component_ids"], "before_revision": execution["start_revision"],
        "after_revision": state["revision"], "changed_artifacts": [], "validations": [],
        "state_transitions": [],
        "open_issues": sorted(item.get("id", "") for item in state["open_decisions"] if item.get("status") == "open"),
        "next_actions": sorted(item.get("id", "") for item in state["next_actions"]),
    }


def scenario_rootless_end_forgery_reject() -> None:
    request = "审计这个数学建模项目"
    resolution = resolve(request, None, None)
    assert resolution["status"] == "resolved"
    receipt = {
        "receipt_type": "end", "schema_version": "10.0", "request": request,
        "request_hash": resolution["request_hash"], "project_root": None,
        "execution_id": None, "component_id": None, "component_map": {}, "mode": resolution["mode"],
        "route_ids": ["FORGED.ROUTE"], "rule_ids": ["FORGED.RULE"], "component_ids": [],
        "before_revision": None, "after_revision": None, "changed_artifacts": [],
        "validations": [], "state_transitions": [], "open_issues": [], "next_actions": [],
    }
    assert shape_errors(receipt) == []
    errors = validate_end(receipt, resolution, None)
    assert "route_ids_mismatch" in errors and "rule_ids_mismatch" in errors


def scenario_forged_record_route_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-forged-route-") as raw:
        root = Path(raw)
        init_project(root)
        before = sha256_file(root / ".modeling/state.json")
        must_raise(lambda: do_record_route(args(
            project_root=root, request="write banana without an executable object",
            execution_id="FORGED", component_id=None,
        )), "unresolved")
        state = load_json(root / ".modeling/state.json")
        assert sha256_file(root / ".modeling/state.json") == before and state["last_route"] is None


def scenario_component_bound_receipt() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-component-receipt-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        add_component(root, "q2", "question")
        request = "执行问题定义，明确目标和约束"
        do_record_route(args(project_root=root, request=request, execution_id="EXEC-Q1", component_id="q1"))
        receipt = canonical_start_receipt(root, request, "EXEC-Q1", "q1")
        resolution = resolve(request, root, "q1")
        assert receipt["component_ids"] == ["q1"]
        assert validate_start(receipt, resolution, root) == []


def scenario_component_map_receipt() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-component-map-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        add_component(root, "q2", "question")
        state = load_json(root / ".modeling/state.json")
        state["components"]["q1"]["state"] = "S4"
        state["components"]["q2"]["state"] = "S5"
        dump_json(root / ".modeling/state.json", state)
        checkpoint(root)
        request = "实现q1模型并验证q2模型代码"
        component_map = {"RT.MODEL.IMPLEMENT": "q1", "RT.VERIFY.IMPLEMENTATION": "q2"}
        state = do_record_route(args(
            project_root=root, request=request, execution_id="EXEC-MAP",
            component_id=None, component_map=json.dumps(component_map),
        ))
        execution = state["executions"]["EXEC-MAP"]
        assert execution["component_map"] == component_map
        assert execution["component_ids"] == ["q1", "q2"]
        receipt = canonical_start_receipt(root, request, "EXEC-MAP")
        resolution = resolve(request, root, None, component_map)
        assert shape_errors(receipt) == []
        assert validate_start(receipt, resolution, root) == []
        forged = copy.deepcopy(receipt)
        forged["component_map"] = {"RT.MODEL.IMPLEMENT": "q2", "RT.VERIFY.IMPLEMENTATION": "q1"}
        forged_resolution = resolve(request, root, None, forged["component_map"])
        errors = validate_start(forged, forged_resolution, root)
        assert "execution_component_map_mismatch" in errors


def scenario_state_inspect_values() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-state-inspect-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        state = load_json(root / ".modeling/state.json")
        observed = do_inspect(args(project_root=root))
        assert observed["status"] == "pass"
        assert observed["revision"] == state["revision"]
        assert observed["workspace_manifest_sha256"] == manifest_sha256(state["workspace_manifest"])
        assert observed["component_subject_hashes"]["q1"] == component_subject_hash(state, "q1")


def scenario_unauthorized_execution_delta_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-unauthorized-delta-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data-main", "shared_data")
        state = load_json(root / ".modeling/state.json")
        state["components"]["data-main"]["state"] = "D1"
        dump_json(root / ".modeling/state.json", state)
        (root / "unowned.txt").write_text("unowned change\n", encoding="utf-8")
        request = "清洗这个数据集"
        state = do_record_route(args(
            project_root=root, request=request, execution_id="EXEC-BLOCKED-WRITE",
            component_id="data-main",
        ))
        assert state["executions"]["EXEC-BLOCKED-WRITE"]["write_authorized"] is False
        do_set_next(args(
            project_root=root, component_id="data-main", action_id="ILLEGAL-NEXT",
            action="should not be accepted", blocked_by=[],
        ))
        receipt = canonical_end_receipt(root, request, "EXEC-BLOCKED-WRITE", "data-main")
        errors = validate_end(receipt, resolve(request, root, "data-main"), root)
        assert "unauthorized_execution_has_delta" in errors


def scenario_execution_replay_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-replay-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        request = "继续完成这个数学建模项目"
        do_record_route(args(project_root=root, request=request, execution_id="EXEC-ONCE", component_id=None))
        receipt = canonical_end_receipt(root, request, "EXEC-ONCE")
        path = root / ".modeling/end-receipt.json"
        write_json(path, receipt)
        do_close_execution(args(project_root=root, receipt=path))
        resolution = resolve(request, root, None)
        assert "execution_already_closed" in validate_end(receipt, resolution, root)
        must_raise(lambda: do_close_execution(args(project_root=root, receipt=path)), "already_closed")


def scenario_end_omitted_artifact_delta_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-end-delta-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        request = "继续完成这个数学建模项目"
        do_record_route(args(project_root=root, request=request, execution_id="EXEC-DELTA", component_id=None))
        target = root / "results/new.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"new": true}\n', encoding="utf-8")
        prop_path = root / ".modeling/delta-proposal.json"
        write_json(prop_path, proposal("results/new.json", ["q1"]))
        do_register_artifact(args(project_root=root, proposal=prop_path, producer="q1", role="result"))
        receipt = canonical_end_receipt(root, request, "EXEC-DELTA")
        receipt["changed_artifacts"] = []
        errors = validate_end(receipt, resolve(request, root, None), root)
        assert "changed_artifacts_mismatch" in errors


def scenario_readonly_delta_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-readonly-delta-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        request = "只读审计这个项目"
        resolution = resolve(request, root, None)
        state = load_json(root / ".modeling/state.json")
        state_hash = sha256_file(root / ".modeling/state.json")
        must_raise(lambda: do_record_route(args(
            project_root=root, request=request, execution_id="EXEC-RO", component_id=None,
        )), "readonly route recording")
        assert sha256_file(root / ".modeling/state.json") == state_hash
        start = {
            "receipt_type": "start", "schema_version": "10.0", "request": request,
            "request_hash": resolution["request_hash"], "project_root": str(root.resolve()),
            "execution_id": None, "component_id": None, "component_map": {},
            "mode": resolution["mode"], "route_ids": resolution["route_ids"],
            "rule_ids": resolution["rule_ids"], "component_ids": _component_ids(resolution),
            "state_revision": state["revision"], "recovery": "R0_CONTINUE",
            "planned_artifacts": [], "blocked": False,
        }
        assert shape_errors(start) == []
        assert validate_start(start, resolution, root) == []
        start["planned_artifacts"] = [proposal("results/illegal.json", ["q1"])]
        assert "readonly_planned_artifacts_forbidden" in validate_start(start, resolution, root)
        (root / "rogue.txt").write_text("illegal\n", encoding="utf-8")
        end = {
            "receipt_type": "end", "schema_version": "10.0", "request": request,
            "request_hash": resolution["request_hash"], "project_root": str(root.resolve()),
            "execution_id": None, "component_id": None, "component_map": {},
            "mode": resolution["mode"], "route_ids": resolution["route_ids"],
            "rule_ids": resolution["rule_ids"], "component_ids": _component_ids(resolution),
            "before_revision": state["revision"], "after_revision": state["revision"],
            "changed_artifacts": [], "validations": [], "state_transitions": [],
            "open_issues": [], "next_actions": [],
        }
        errors = validate_end(end, resolve(request, root, None), root)
        assert "readonly_workspace_not_r0" in errors


def scenario_wrong_execution_binding_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-binding-attack-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        request = "执行问题定义，明确目标和约束"
        do_record_route(args(project_root=root, request=request, execution_id="EXEC-BIND", component_id="q1"))
        receipt = canonical_start_receipt(root, request, "EXEC-BIND", "q1")
        receipt["request"] = "审计论文"
        receipt["component_id"] = None
        errors = validate_start(receipt, resolve(receipt["request"], root, None), root)
        assert "request_hash_mismatch" in errors
        assert "execution_request_mismatch" in errors and "execution_component_selector_mismatch" in errors


def scenario_project_gate_reject() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-project-gate-") as raw:
        root = Path(raw)
        init_project(root)
        must_raise(lambda: do_transition(args(
            project_root=root, project=True, component_id=None, to="P1", reason=None, reason_evidence_id=None,
        )), "required_components_empty")
        add_component(root, "paper", "artifact")
        advance_artifact_to_a3(root)
        do_transition(args(project_root=root, project=True, component_id=None, to="P1", reason=None, reason_evidence_id=None))
        must_raise(lambda: add_component(root, "late", "question"), "only while project is P0")
        must_raise(lambda: do_transition(args(
            project_root=root, project=True, component_id=None, to="P2", reason=None, reason_evidence_id=None,
        )), "delivery_acceptance")


def scenario_artifact_validation_evidence_required() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-artifact-validation-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "q1", "question")
        target = root / "results/value.json"
        target.parent.mkdir(parents=True)
        target.write_text('{"value": 1}\n', encoding="utf-8")
        prop_path = root / ".modeling/no-validation-proposal.json"
        write_json(prop_path, proposal("results/value.json", ["q1"]))
        do_register_artifact(args(project_root=root, proposal=prop_path, producer="q1", role="result"))
        before = sha256_file(root / ".modeling/state.json")
        must_raise(lambda: do_validate_artifact(args(
            project_root=root, path="results/value.json", evidence_id="FORGED-EVIDENCE",
        )), "missing")
        assert sha256_file(root / ".modeling/state.json") == before


def scenario_recovery_rule_exclusive() -> None:
    with tempfile.TemporaryDirectory(prefix="v10-recovery-exclusive-r0-") as raw:
        root = Path(raw)
        init_project(root)
        checkpoint(root)
        result = resolve("继续完成这个数学建模项目", root, None)
        selected = {item for item in result["rule_ids"] if item.startswith("REC.")}
        assert selected == {"REC.R0.CONTINUE", "REC.R0.READ_SCOPE", "REC.R0.NO_MANIFEST"}, result
    with tempfile.TemporaryDirectory(prefix="v10-recovery-exclusive-") as raw:
        root = Path(raw)
        init_project(root)
        add_component(root, "data", "shared_data")
        target = root / "data/value.csv"
        target.parent.mkdir(parents=True)
        target.write_text("x\n1\n", encoding="utf-8")
        prop_path = root / ".modeling/recovery-proposal.json"
        write_json(prop_path, proposal("data/value.csv", ["data"], "data"))
        do_register_artifact(args(project_root=root, proposal=prop_path, producer="data", role="source"))
        target.write_text("x\n2\n", encoding="utf-8")
        result = resolve("继续完成这个数学建模项目", root, None)
        selected = {item for item in result["rule_ids"] if item.startswith("REC.")}
        assert selected == {"REC.R1.TRANSITIVE", "REC.R1.REVIEW_CLOSURE", "REC.R1.READ_SCOPE"}, result
    with tempfile.TemporaryDirectory(prefix="v10-recovery-exclusive-r2-") as raw:
        root = Path(raw)
        init_project(root)
        checkpoint(root)
        result = resolve("打包并最终交付项目", root, None)
        selected = {item for item in result["rule_ids"] if item.startswith("REC.")}
        assert result["runtime_facts"]["recovery_level"] == "R2_FULL", result
        assert selected == {"REC.R2.FULL", "REC.R2.EVIDENCE_REBUILD", "REC.R2.NO_NARRATIVE_ONLY"}, result


SCENARIOS: dict[str, Callable[[], None]] = {
    "artifact_guard": scenario_artifact_guard,
    "spoof_start_receipt": scenario_spoof_start_receipt,
    "spoof_end_receipt": scenario_spoof_end_receipt,
    "state_type_reject": scenario_state_type_reject,
    "string_evidence_reject": scenario_string_evidence_reject,
    "s6_gate_order": scenario_s6_gate_order,
    "controlled_reopen": scenario_controlled_reopen,
    "route_record": scenario_route_record,
    "artifact_identity": scenario_artifact_identity,
    "dependency_cycle": scenario_dependency_cycle,
    "next_action": scenario_next_action,
    "recovery_r0": scenario_recovery_r0,
    "recovery_r1_transitive": scenario_recovery_r1_transitive,
    "recovery_r2_missing": scenario_recovery_r2_missing,
    "recovery_r2_invalid": scenario_recovery_r2_invalid,
    "schema_extra_unknown_level_reject": scenario_schema_extra_unknown_level_reject,
    "passing_command_nonzero_reject": scenario_passing_command_nonzero_reject,
    "observation_only_s6_reject": scenario_observation_only_s6_reject,
    "stale_subject_hash_reject": scenario_stale_subject_hash_reject,
    "closed_evidence_write_reject": scenario_closed_evidence_write_reject,
    "stale_d3_reopen_reason_reject": scenario_stale_d3_reopen_reason_reject,
    "stale_a3_reopen_reason_reject": scenario_stale_a3_reopen_reason_reject,
    "reopen_immediate_reclose_reject": scenario_reopen_immediate_reclose_reject,
    "model_redesign_reopen_matrix": scenario_model_redesign_reopen_matrix,
    "s7_failure_reopen_matrix": scenario_s7_failure_reopen_matrix,
    "d3_reopen_invalidation": scenario_d3_reopen_invalidation,
    "a3_reopen_resets_project": scenario_a3_reopen_resets_project,
    "project_p2_reopen": scenario_project_p2_reopen,
    "transitive_invalidation": scenario_transitive_invalidation,
    "invalidated_s6_recovery": scenario_invalidated_s6_recovery,
    "dependency_change_transitive": scenario_dependency_change_transitive,
    "checkpoint_launder_reject": scenario_checkpoint_launder_reject,
    "watch_root_reject": scenario_watch_root_reject,
    "rootless_end_forgery_reject": scenario_rootless_end_forgery_reject,
    "forged_record_route_reject": scenario_forged_record_route_reject,
    "component_bound_receipt": scenario_component_bound_receipt,
    "component_map_receipt": scenario_component_map_receipt,
    "state_inspect_values": scenario_state_inspect_values,
    "unauthorized_execution_delta_reject": scenario_unauthorized_execution_delta_reject,
    "execution_replay_reject": scenario_execution_replay_reject,
    "end_omitted_artifact_delta_reject": scenario_end_omitted_artifact_delta_reject,
    "readonly_delta_reject": scenario_readonly_delta_reject,
    "wrong_execution_binding_reject": scenario_wrong_execution_binding_reject,
    "project_gate_reject": scenario_project_gate_reject,
    "artifact_validation_evidence_required": scenario_artifact_validation_evidence_required,
    "recovery_rule_exclusive": scenario_recovery_rule_exclusive,
}


def selected_cases(root: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted((root / "evals").glob("*.json")):
        payload = load_json(path)
        for case in payload.get("cases", []):
            if case.get("kind") == "scenario" and case.get("driver") == "scenario_tests":
                cases.append(case)
    return cases


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    cli = parser.parse_args()
    root = cli.root.resolve()
    cases = selected_cases(root)
    results: list[dict[str, Any]] = []
    executed: dict[str, tuple[str, str | None]] = {}
    for case in cases:
        scenario = case.get("scenario")
        if scenario not in executed:
            handler = SCENARIOS.get(str(scenario))
            if handler is None:
                executed[str(scenario)] = ("fail", "scenario implementation missing")
            else:
                try:
                    handler()
                    executed[str(scenario)] = ("pass", None)
                except Exception as exc:  # each failure is isolated and reported
                    executed[str(scenario)] = ("fail", f"{type(exc).__name__}: {exc}")
        status, error = executed[str(scenario)]
        results.append({"id": case["id"], "scenario": scenario, "status": status, "error": error})
    missing_registry = sorted(set(SCENARIOS) - {str(case.get("scenario")) for case in cases})
    failed = [item for item in results if item["status"] != "pass"]
    status = "pass" if not failed and not missing_registry else "fail"
    print(json.dumps({
        "schema_version": "10.0", "status": status,
        "driver": "real_fixture_state_recovery_receipt_scenarios",
        "total": len(results), "passed": len(results) - len(failed), "failed": len(failed),
        "unregistered_scenarios": missing_registry, "results": results,
    }, ensure_ascii=False, indent=2))
    return 0 if status == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
