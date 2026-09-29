#!/usr/bin/env python3
"""Run focused disposable V14 project-control and recovery scenarios."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from lib_v10 import sha256_file, sha256_text
from lib_v11 import canonical_json, resolve
from state_v11 import evidence_binding_hash
from validate_receipt import checkpoint_pair_hash


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def run(script: Path, *arguments: str) -> tuple[int, dict[str, Any], str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, "-B", str(script), *arguments],
        text=True, capture_output=True, check=False, timeout=15, env=environment,
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {}
    return process.returncode, payload, (process.stderr + process.stdout)[-800:]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def evidence(component_id: str, identifier: str, level: str) -> dict[str, Any]:
    refs: list[dict[str, str]] = []
    claims: list[str] = []
    return {
        "id": identifier,
        "level": level,
        "status": "pass",
        "kind": "observation",
        "locator": {
            "subject": component_id,
            "method": "independent disposable scenario inspection",
            "value": "verified",
        },
        "claim": f"{level} is verified in the disposable scenario.",
        "observed_at": "2026-08-26T00:00:00Z",
        "producer": "v14-scenario",
        "subject_id": component_id,
        "input_refs": refs,
        "claim_refs": claims,
        "binding_hash": evidence_binding_hash(component_id, level, refs, claims),
    }


def validation(component_id: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "component_id": component_id,
        "level": record["level"],
        "status": "pass",
        "evidence_ref": f"state:components/{component_id}/evidence/{record['id']}",
        "input_refs": record["input_refs"],
        "claim_refs": record["claim_refs"],
        "binding_hash": record["binding_hash"],
    }


def end_receipt(
    project: Path, plan: dict[str, Any], resolution: dict[str, Any],
    execution_id: str, validations: list[dict[str, Any]],
    changed_identities: list[dict[str, str]],
) -> dict[str, Any]:
    state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
    execution = state["executions"][execution_id]
    step = resolution["steps"][0]
    transitions = []
    for entry in state["history"]:
        if not execution["start_revision"] < entry["revision"] <= state["revision"]:
            continue
        if entry["event"] in {"component_transition", "project_transition"}:
            transitions.append({
                "component_id": entry["subject"],
                "from": entry["details"]["from"],
                "to": entry["details"]["to"],
            })
    return {
        "receipt_type": "end", "schema_version": "11.0",
        "request": plan["request"], "request_hash": sha256_text(plan["request"]),
        "semantic_plan": plan, "plan_hash": sha256_text(canonical_json(plan)),
        "step_id": step["id"], "execution_id": execution_id,
        "pair_hash": checkpoint_pair_hash(execution),
        "project_root": str(project.resolve()), "tier": step["tier"], "mode": step["mode"],
        "route_ids": [step["route_id"]], "rule_ids": step["rule_ids"],
        "component_ids": step["component_ids"],
        "before_revision": execution["start_revision"], "after_revision": state["revision"],
        "change_set": step["change_set"], "changed_identities": changed_identities,
        "validations": validations, "state_transitions": transitions,
        "open_issues": sorted(item["id"] for item in state["open_decisions"] if item["status"] == "open"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    manager = root / "scripts/state_manager.py"
    receipt_validator = root / "scripts/validate_receipt.py"
    cases: list[dict[str, Any]] = []

    def record(identifier: str, passed: bool, evidence_text: str) -> None:
        cases.append({"id": identifier, "status": "pass" if passed else "fail", "evidence": evidence_text})

    with tempfile.TemporaryDirectory(prefix="v14-scenarios-") as raw:
        workspace = Path(raw)
        project = workspace / "project"
        init_code, _, init_log = run(manager, "init", "--project-root", str(project), "--project-id", "demo")
        add_code, _, add_log = run(
            manager, "add-component", "--project-root", str(project),
            "--component-id", "INPUTS", "--type", "shared_data",
        )
        relative_files = sorted(path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file())
        record(
            "SCENARIO.PLATFORM.INIT_CONTROL_ONLY",
            init_code == 0 and add_code == 0 and relative_files == [".modeling/state.json"],
            f"files={relative_files};log={init_log}{add_log}",
        )

        canonical_plan = {
            "schema_version": "11.0", "request": "建立规范项目计划", "window_context": "same_window",
            "steps": [{
                "id": "plan", "tier": "G1_WORKING", "mode": "mutate",
                "object": "project", "action": "plan", "component_id": None,
                "events": ["project_planning"], "facts": {}, "depends_on": [],
                "change_set": {"paths": ["planning/01_scope.md"], "facets": ["project_plan"], "claim_refs": []},
            }],
        }
        arbitrary_plan = json.loads(json.dumps(canonical_plan))
        arbitrary_plan["steps"][0]["change_set"]["paths"] = ["scratch/notes.md"]
        canonical_result = resolve(canonical_plan, project, root)
        arbitrary_result = resolve(arbitrary_plan, project, root)
        record(
            "SCENARIO.PLATFORM.PLAN_PREFLIGHT",
            canonical_result.get("status") == "resolved"
            and arbitrary_result.get("status") == "blocked"
            and any("new_path_outside_project_platform" in reason for reason in arbitrary_result["steps"][0]["reasons"]),
            f"canonical={canonical_result.get('status')}:{canonical_result.get('steps', [{}])[0].get('reasons')};arbitrary={arbitrary_result.get('steps', [{}])[0].get('reasons')}",
        )

        for identifier, level in (("EV-DATA-ID", "data_identity"), ("EV-PROV", "provenance")):
            path = workspace / f"{identifier}.json"
            write_json(path, evidence("INPUTS", identifier, level))
            run(
                manager, "record-evidence", "--project-root", str(project),
                "--component-id", "INPUTS", "--evidence", str(path),
            )

        transition_plan = {
            "schema_version": "11.0", "request": "证据满足后推进 INPUTS 到 D1", "window_context": "same_window",
            "steps": [{
                "id": "promote-inputs", "tier": "G2_CHECKPOINT", "mode": "promote",
                "object": "state", "action": "transition", "component_id": "INPUTS",
                "events": ["recovery_assessment", "state_transition"], "facts": {}, "depends_on": [],
                "change_set": {"paths": [".modeling/state.json"], "facets": ["shared_data_state"], "claim_refs": []},
                "state_effect": {"component_id": "INPUTS", "from": "D0", "to": "D1"},
            }],
        }
        transition_path = workspace / "transition-plan.json"
        write_json(transition_path, transition_plan)
        transition_result = resolve(transition_plan, project, root)
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        checkpoint_code, _, checkpoint_log = run(
            manager, "checkpoint", "--project-root", str(project),
            "--expected-revision", str(state["revision"]), "--gate", "G2",
            "--plan", str(transition_path), "--step-id", "promote-inputs",
        )
        start_code, _, start_log = run(
            manager, "record-route", "--project-root", str(project), "--plan", str(transition_path),
            "--step-id", "promote-inputs", "--execution-id", "EXEC-TRANSITION",
        )
        transition_code, _, transition_log = run(
            manager, "transition", "--project-root", str(project), "--component-id", "INPUTS",
            "--to", "D1", "--execution-id", "EXEC-TRANSITION",
        )
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        stored = {item["level"]: item for item in state["components"]["INPUTS"]["evidence"]}
        receipt = end_receipt(
            project, transition_plan, transition_result, "EXEC-TRANSITION",
            [validation("INPUTS", stored["data_identity"]), validation("INPUTS", stored["provenance"])], [],
        )
        receipt_path = workspace / "transition-receipt.json"
        write_json(receipt_path, receipt)
        close_code, _, close_log = run(
            manager, "close-execution", "--project-root", str(project), "--receipt", str(receipt_path),
        )
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        record(
            "SCENARIO.STATE.D0_D1_ROUNDTRIP",
            transition_result.get("status") == "resolved" and checkpoint_code == 0
            and start_code == 0 and transition_code == 0
            and close_code == 0 and state["components"]["INPUTS"]["state"] == "D1"
            and state["executions"]["EXEC-TRANSITION"]["status"] == "closed",
            f"resolve={transition_result.get('status')};checkpoint={checkpoint_code};start={start_code};transition={transition_code};close={close_code};log={checkpoint_log}{start_log}{transition_log}{close_log}",
        )

        data_file = project / "data/input.csv"
        data_file.parent.mkdir(parents=True)
        data_file.write_text("x\n1\n", encoding="utf-8")
        proposal = {
            "path": "data/input.csv", "platform_role": "official_input",
            "purpose": "Official disposable input for identity binding test.",
            "consumer_ids": ["INPUTS"], "lifecycle": "milestone", "identity_class": "frozen",
            "class": "data", "authorization_basis": "authorized scenario fixture", "replaces": None,
        }
        proposal_path = workspace / "proposal.json"
        write_json(proposal_path, proposal)

        def audit_plan(paths: list[str], identifier: str) -> dict[str, Any]:
            return {
                "schema_version": "11.0", "plan_id": identifier,
                "request": "登记并审计正式输入", "window_context": "same_window",
                "steps": [{
                    "id": "audit", "tier": "G2_CHECKPOINT", "mode": "mutate",
                    "object": "data", "action": "audit", "component_id": "INPUTS",
                    "events": ["recovery_assessment", "data_audit", "dataset_register"],
                    "facts": {"predictive_or_evaluative_use": False}, "depends_on": [],
                    "change_set": {"paths": paths, "facets": ["data_identity"], "claim_refs": []},
                }],
            }

        bad_plan = audit_plan(["planning/inputs.md"], "bad-identity-plan")
        bad_path = workspace / "bad-plan.json"
        write_json(bad_path, bad_plan)
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        bad_checkpoint, _, bad_checkpoint_log = run(
            manager, "checkpoint", "--project-root", str(project),
            "--expected-revision", str(state["revision"]), "--gate", "G2",
            "--plan", str(bad_path), "--step-id", "audit",
        )
        bad_start, _, _ = run(
            manager, "record-route", "--project-root", str(project), "--plan", str(bad_path),
            "--step-id", "audit", "--execution-id", "EXEC-BAD-IDENTITY",
        )
        bad_register, _, bad_log = run(
            manager, "register-artifact", "--project-root", str(project), "--proposal", str(proposal_path),
            "--producer", "INPUTS", "--execution-id", "EXEC-BAD-IDENTITY",
        )
        void_code, _, void_log = run(
            manager, "void-execution", "--project-root", str(project),
            "--execution-id", "EXEC-BAD-IDENTITY", "--failure-code", "CHANGE_SET_OMISSION",
            "--reason", "Formal identity path was omitted from the sealed ChangeSet.",
        )
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        record(
            "SCENARIO.IDENTITY.PREFLIGHT_AND_VOID",
            bad_checkpoint == 0 and bad_start == 0 and bad_register != 0 and "outside sealed ChangeSet" in bad_log
            and void_code == 0 and state["executions"]["EXEC-BAD-IDENTITY"]["status"] == "void",
            f"checkpoint={bad_checkpoint};register={bad_register};void={void_code};log={bad_checkpoint_log}{bad_log}{void_log}",
        )

        good_plan = audit_plan(["data/input.csv"], "good-identity-plan")
        good_path = workspace / "good-plan.json"
        write_json(good_path, good_plan)
        good_result = resolve(good_plan, project, root)
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        good_checkpoint, _, good_checkpoint_log = run(
            manager, "checkpoint", "--project-root", str(project),
            "--expected-revision", str(state["revision"]), "--gate", "G2",
            "--plan", str(good_path), "--step-id", "audit",
        )
        good_start, _, good_start_log = run(
            manager, "record-route", "--project-root", str(project), "--plan", str(good_path),
            "--step-id", "audit", "--execution-id", "EXEC-GOOD-IDENTITY",
        )
        good_register, _, good_register_log = run(
            manager, "register-artifact", "--project-root", str(project), "--proposal", str(proposal_path),
            "--producer", "INPUTS", "--execution-id", "EXEC-GOOD-IDENTITY",
        )
        good_close = 99
        good_close_log = "close_not_attempted"
        if good_start == 0 and good_register == 0:
            identity = {"kind": "artifact", "id": "data/input.csv", "identity": sha256_file(data_file), "facet": "content"}
            receipt = end_receipt(
                project, good_plan, good_result, "EXEC-GOOD-IDENTITY",
                [validation("INPUTS", stored["data_identity"])], [identity],
            )
            good_receipt_path = workspace / "good-receipt.json"
            write_json(good_receipt_path, receipt)
            good_close, _, good_close_log = run(
                manager, "close-execution", "--project-root", str(project), "--receipt", str(good_receipt_path),
            )
        record(
            "SCENARIO.IDENTITY.DECLARED_ROUNDTRIP",
            good_result.get("status") == "resolved" and good_checkpoint == 0
            and good_start == 0 and good_register == 0 and good_close == 0,
            f"resolve={good_result.get('status')}:{good_result.get('steps', [{}])[0].get('reasons')}:blocking={good_result.get('steps', [{}])[0].get('blocking_rule_ids')};checkpoint={good_checkpoint};start={good_start};register={good_register};close={good_close};log={good_checkpoint_log}{good_start_log}{good_register_log}{good_close_log}",
        )

        # Real new-window chain: registered statement + frozen process must be
        # semantically reread and closed under one R1 receipt before D0 -> D1.
        r1_project = workspace / "r1-project"
        run(manager, "init", "--project-root", str(r1_project), "--project-id", "r1-demo")
        run(
            manager, "add-component", "--project-root", str(r1_project),
            "--component-id", "INPUTS", "--type", "shared_data",
        )
        problem_file = r1_project / "data/problem.txt"
        frozen_flow = r1_project / "planning/frozen_flow.md"
        problem_file.parent.mkdir(parents=True)
        frozen_flow.parent.mkdir(parents=True)
        problem_file.write_text("Official problem statement for targeted recovery.\n", encoding="utf-8")
        frozen_flow.write_text("Frozen and accepted INPUTS workflow.\n", encoding="utf-8")
        for identifier, level in (("R1-DATA-ID", "data_identity"), ("R1-PROV", "provenance")):
            evidence_path = workspace / f"{identifier}.json"
            write_json(evidence_path, evidence("INPUTS", identifier, level))
            run(
                manager, "record-evidence", "--project-root", str(r1_project),
                "--component-id", "INPUTS", "--evidence", str(evidence_path),
            )

        fixture_plan = {
            "schema_version": "11.0", "plan_id": "r1-fixture",
            "request": "登记恢复场景的正式题面和冻结流程", "window_context": "same_window",
            "steps": [{
                "id": "fixture", "tier": "G2_CHECKPOINT", "mode": "mutate",
                "object": "data", "action": "audit", "component_id": "INPUTS",
                "events": ["recovery_assessment", "data_audit", "dataset_register"],
                "facts": {"predictive_or_evaluative_use": False}, "depends_on": [],
                "change_set": {
                    "paths": ["data/problem.txt", "planning/frozen_flow.md"],
                    "facets": ["data_identity"], "claim_refs": [],
                },
            }],
        }
        fixture_plan_path = workspace / "r1-fixture-plan.json"
        write_json(fixture_plan_path, fixture_plan)
        fixture_resolution = resolve(fixture_plan, r1_project, root)
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        fixture_checkpoint, _, _ = run(
            manager, "checkpoint", "--project-root", str(r1_project),
            "--expected-revision", str(r1_state["revision"]), "--gate", "G2",
            "--plan", str(fixture_plan_path), "--step-id", "fixture",
        )
        fixture_start, _, _ = run(
            manager, "record-route", "--project-root", str(r1_project),
            "--plan", str(fixture_plan_path), "--step-id", "fixture",
            "--execution-id", "EXEC-R1-FIXTURE",
        )
        proposals = [
            {
                "path": "data/problem.txt", "platform_role": "official_input",
                "purpose": "Official problem statement for recovery context.",
                "consumer_ids": ["INPUTS"], "lifecycle": "milestone",
                "identity_class": "frozen", "class": "source",
                "authorization_basis": "authorized recovery scenario fixture", "replaces": None,
            },
            {
                "path": "planning/frozen_flow.md", "platform_role": "planning",
                "purpose": "Frozen accepted workflow for INPUTS recovery.",
                "consumer_ids": ["INPUTS"], "lifecycle": "milestone",
                "identity_class": "frozen", "class": "control",
                "authorization_basis": "authorized recovery scenario fixture", "replaces": None,
            },
        ]
        fixture_register_codes: list[int] = []
        for index, proposal_item in enumerate(proposals):
            proposal_path = workspace / f"r1-proposal-{index}.json"
            write_json(proposal_path, proposal_item)
            code, _, _ = run(
                manager, "register-artifact", "--project-root", str(r1_project),
                "--proposal", str(proposal_path), "--producer", "INPUTS",
                "--execution-id", "EXEC-R1-FIXTURE",
            )
            fixture_register_codes.append(code)
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        fixture_stored = {item["level"]: item for item in r1_state["components"]["INPUTS"]["evidence"]}
        fixture_identities = [
            {"kind": "artifact", "id": path, "identity": r1_state["artifacts"][path]["sha256"], "facet": "content"}
            for path in ("data/problem.txt", "planning/frozen_flow.md")
        ]
        fixture_receipt = end_receipt(
            r1_project, fixture_plan, fixture_resolution, "EXEC-R1-FIXTURE",
            [validation("INPUTS", fixture_stored["data_identity"])], fixture_identities,
        )
        fixture_receipt_path = workspace / "r1-fixture-receipt.json"
        write_json(fixture_receipt_path, fixture_receipt)
        fixture_close, _, fixture_close_log = run(
            manager, "close-execution", "--project-root", str(r1_project),
            "--receipt", str(fixture_receipt_path),
        )

        r1_plan = {
            "schema_version": "11.0", "plan_id": "r1-transition",
            "request": "新窗口恢复后推进 INPUTS 到 D1", "window_context": "new_window",
            "steps": [{
                "id": "promote", "tier": "G2_CHECKPOINT", "mode": "promote",
                "object": "state", "action": "transition", "component_id": "INPUTS",
                "events": ["recovery_assessment", "state_transition"],
                "facts": {}, "depends_on": [],
                "change_set": {"paths": [".modeling/state.json"], "facets": ["shared_data_state"], "claim_refs": []},
                "state_effect": {"component_id": "INPUTS", "from": "D0", "to": "D1"},
            }],
        }
        r1_plan_path = workspace / "r1-transition-plan.json"
        write_json(r1_plan_path, r1_plan)
        r1_resolution = resolve(r1_plan, r1_project, root)
        r1_begin, r1_begin_payload, r1_begin_log = run(
            manager, "begin-recovery", "--project-root", str(r1_project),
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        recovery_record = r1_state["recoveries"]["REC-R1-NEW-WINDOW"]

        def recovery_read(requirement: dict[str, Any]) -> dict[str, Any]:
            live = r1_project / requirement["path"]
            required_mode = requirement["required_mode"]
            mode = {
                "content": "content", "semantic": "structured_extract",
                "identity": "identity_plus_validation_summary", "existence": "missing_review",
            }[required_mode]
            return {
                "path": requirement["path"],
                "semantic_role": requirement["semantic_role"],
                "read_mode": mode,
                "sha256": sha256_file(live) if live.is_file() else None,
                "size": live.stat().st_size if live.is_file() else None,
                "review_result": "consistent" if live.is_file() else "missing",
                "note": "Content and project meaning were reviewed against the current target.",
            }

        all_reads = [recovery_read(item) for item in recovery_record["required_reads"]]
        incomplete_receipt = {
            "schema_version": "14.0", "receipt_type": "r1_targeted_recovery",
            "recovery_id": "REC-R1-NEW-WINDOW", "project_root": str(r1_project.resolve()),
            "read_receipts": [
                item for item in all_reads if item["path"] != "planning/frozen_flow.md"
            ],
            "changed_paths": recovery_record["assessment"]["changed_paths"],
            "affected_components": recovery_record["assessment"]["affected_components"],
            "conclusion": {"status": "ready", "inconsistencies": [], "next_legal_action": "Run the bound G2 checkpoint."},
        }
        incomplete_path = workspace / "r1-incomplete-receipt.json"
        write_json(incomplete_path, incomplete_receipt)
        incomplete_close, _, incomplete_log = run(
            manager, "close-recovery", "--project-root", str(r1_project),
            "--receipt", str(incomplete_path),
        )
        preclose_checkpoint, _, preclose_log = run(
            manager, "checkpoint", "--project-root", str(r1_project),
            "--expected-revision", str(r1_state["revision"]), "--gate", "G2",
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        unbound_baseline, _, unbound_baseline_log = run(
            manager, "update-baseline", "--project-root", str(r1_project),
        )

        complete_receipt = dict(incomplete_receipt)
        complete_receipt["read_receipts"] = all_reads
        complete_path = workspace / "r1-complete-receipt.json"
        write_json(complete_path, complete_receipt)
        complete_close, _, complete_close_log = run(
            manager, "close-recovery", "--project-root", str(r1_project),
            "--receipt", str(complete_path),
        )
        reviewed_flow = frozen_flow.read_text(encoding="utf-8")
        frozen_flow.write_text(reviewed_flow + "unreviewed change\n", encoding="utf-8")
        postclose_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        changed_after_review_baseline, _, changed_after_review_log = run(
            manager, "update-baseline", "--project-root", str(r1_project),
            "--recovery-id", "REC-R1-NEW-WINDOW",
            "--expected-revision", str(postclose_state["revision"]),
        )
        frozen_flow.write_text(reviewed_flow, encoding="utf-8")
        no_checkpoint_start, _, no_checkpoint_log = run(
            manager, "record-route", "--project-root", str(r1_project),
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--execution-id", "EXEC-R1-NO-CHECKPOINT",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        r1_checkpoint, _, r1_checkpoint_log = run(
            manager, "checkpoint", "--project-root", str(r1_project),
            "--expected-revision", str(r1_state["revision"]), "--gate", "G2",
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        r1_start, _, r1_start_log = run(
            manager, "record-route", "--project-root", str(r1_project),
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--execution-id", "EXEC-R1-TRANSITION",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        r1_execution = r1_state["executions"].get("EXEC-R1-TRANSITION", {})
        r1_start_resolution = resolve(r1_plan, r1_project, root)
        r1_start_step = r1_start_resolution["steps"][0]
        r1_start_receipt = {
            "receipt_type": "start", "schema_version": "11.0",
            "request": r1_plan["request"], "request_hash": sha256_text(r1_plan["request"]),
            "semantic_plan": r1_plan, "plan_hash": sha256_text(canonical_json(r1_plan)),
            "step_id": "promote", "execution_id": "EXEC-R1-TRANSITION",
            "pair_hash": checkpoint_pair_hash(r1_execution),
            "project_root": str(r1_project.resolve()), "tier": "G2_CHECKPOINT",
            "mode": "promote", "route_ids": [r1_start_step["route_id"]],
            "rule_ids": r1_start_step["rule_ids"], "component_ids": r1_start_step["component_ids"],
            "state_revision": r1_execution.get("start_revision"), "recovery": "R1_TARGETED",
            "change_set": r1_start_step["change_set"],
            "required_identities": [
                {
                    "kind": "artifact", "id": path,
                    "identity": r1_state["artifacts"][path]["sha256"], "facet": "content",
                }
                for path in ("data/problem.txt", "planning/frozen_flow.md")
            ],
            "blocked": False,
        }
        r1_start_receipt_path = workspace / "r1-start-receipt.json"
        write_json(r1_start_receipt_path, r1_start_receipt)
        r1_start_receipt_code, _, r1_start_receipt_log = run(
            receipt_validator, "--receipt", str(r1_start_receipt_path),
        )
        tampered_start = dict(r1_start_receipt)
        tampered_start["recovery"] = "R0_CONTINUE"
        tampered_start_path = workspace / "r1-start-receipt-tampered.json"
        write_json(tampered_start_path, tampered_start)
        tampered_start_code, _, tampered_start_log = run(
            receipt_validator, "--receipt", str(tampered_start_path),
        )
        r1_transition, _, r1_transition_log = run(
            manager, "transition", "--project-root", str(r1_project),
            "--component-id", "INPUTS", "--to", "D1",
            "--execution-id", "EXEC-R1-TRANSITION",
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        r1_stored = {item["level"]: item for item in r1_state["components"]["INPUTS"]["evidence"]}
        r1_end = end_receipt(
            r1_project, r1_plan, r1_resolution, "EXEC-R1-TRANSITION",
            [
                validation("INPUTS", r1_stored["data_identity"]),
                validation("INPUTS", r1_stored["provenance"]),
            ], [],
        )
        r1_end_path = workspace / "r1-transition-receipt.json"
        write_json(r1_end_path, r1_end)
        r1_close, _, r1_close_log = run(
            manager, "close-execution", "--project-root", str(r1_project),
            "--receipt", str(r1_end_path),
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        required_roles = {
            item["semantic_role"] for item in recovery_record["required_reads"]
        }
        record(
            "SCENARIO.RECOVERY.R1_NEW_WINDOW_ROUNDTRIP",
            fixture_checkpoint == 0 and fixture_start == 0
            and fixture_register_codes == [0, 0] and fixture_close == 0
            and r1_resolution.get("status") == "resolved"
            and r1_resolution["steps"][0]["recovery"]["level"] == "R1_TARGETED"
            and {
                "REC.R1.READ_SCOPE", "REC.R1.REVIEW_CLOSURE", "REC.R1.TRANSITIVE",
            }.issubset(set(r1_resolution["steps"][0]["rule_ids"]))
            and r1_begin == 0 and incomplete_close != 0 and preclose_checkpoint != 0
            and unbound_baseline != 0 and complete_close == 0
            and changed_after_review_baseline != 0
            and no_checkpoint_start != 0 and r1_checkpoint == 0 and r1_start == 0
            and r1_start_receipt_code == 0 and tampered_start_code != 0
            and r1_transition == 0 and r1_close == 0
            and {"authoritative_state", "official_input", "frozen_process"}.issubset(required_roles)
            and r1_state["executions"]["EXEC-R1-TRANSITION"]["recovery"] == "R1_TARGETED"
            and r1_state["recoveries"]["REC-R1-NEW-WINDOW"]["consumed_by_execution"] == "EXEC-R1-TRANSITION"
            and set(r1_state.get("workspace_baseline", {})) == {
                "data/problem.txt", "planning/frozen_flow.md"
            }
            and r1_state["components"]["INPUTS"]["state"] == "D1",
            "fixture=" + str((fixture_checkpoint, fixture_start, fixture_register_codes, fixture_close))
            + ";r1=" + str((r1_begin, incomplete_close, preclose_checkpoint, unbound_baseline, complete_close, changed_after_review_baseline, no_checkpoint_start, r1_checkpoint, r1_start, r1_start_receipt_code, tampered_start_code, r1_transition, r1_close))
            + ";roles=" + str(sorted(required_roles))
            + ";log=" + (fixture_close_log + r1_begin_log + incomplete_log + preclose_log + unbound_baseline_log + complete_close_log + changed_after_review_log + no_checkpoint_log + r1_checkpoint_log + r1_start_log + r1_start_receipt_log + tampered_start_log + r1_transition_log + r1_close_log)[-1200:],
        )

        unauthorized = {
            "schema_version": "11.0", "request": "继续项目",
            "steps": [{
                "id": "skill", "tier": "G1_WORKING", "mode": "skill_maintenance",
                "object": "skill", "action": "change_route", "component_id": None,
                "events": ["rule_load", "rule_change_request", "rule_change_analysis", "rule_change", "normative_behavior_change"],
                "facts": {}, "depends_on": [],
                "change_set": {"paths": ["references/route-contract.json"], "facets": ["route"], "claim_refs": []},
            }],
        }
        authorized = json.loads(json.dumps(unauthorized))
        authorized["request"] = "去修之前明确指出的 Skill 问题"
        authorized["skill_authorization"] = {
            "source": "prior_explicit_user_request", "quote": "去修", "target": "skill"
        }
        mixed = json.loads(json.dumps(authorized))
        mixed["steps"].insert(0, {
            "id": "project", "tier": "G0_ADVISORY", "mode": "advisory_readonly",
            "object": "project", "action": "advise", "component_id": None,
            "events": [], "facts": {}, "depends_on": [],
        })
        unauthorized_result = resolve(unauthorized, None, root)
        authorized_result = resolve(authorized, None, root)
        mixed_result = resolve(mixed, None, root)
        mixed_skill = next(item for item in mixed_result.get("steps", []) if item.get("id") == "skill")
        record(
            "SCENARIO.SKILL.EXPLICIT_AUTHORIZATION",
            unauthorized_result.get("status") == "blocked"
            and authorized_result.get("status") == "resolved"
            and mixed_skill.get("status") == "blocked"
            and "skill_maintenance_must_be_isolated_plan" in mixed_skill.get("reasons", []),
            f"unauthorized={unauthorized_result.get('errors')};authorized={authorized_result.get('status')};mixed={mixed_skill.get('reasons')}",
        )

        machine = json.loads((root / "references/state-machine.json").read_text(encoding="utf-8"))
        edge_failures: list[str] = []
        edge_count = 0
        terminal = {"question": "S7", "shared_data": "D3", "artifact": "A3"}
        for component_type, transitions in machine.get("transitions", {}).items():
            for index, edge in enumerate(transitions):
                edge_count += 1
                edge_project = workspace / f"edge-{component_type}-{index}"
                project_id = f"edge-{index}"
                init_edge, _, init_edge_log = run(
                    manager, "init", "--project-root", str(edge_project), "--project-id", project_id,
                )
                component_id = project_id
                if component_type != "project":
                    component_id = "component"
                    add_edge, _, add_edge_log = run(
                        manager, "add-component", "--project-root", str(edge_project),
                        "--component-id", component_id, "--type", component_type,
                    )
                    if add_edge != 0:
                        edge_failures.append(f"{component_type}:{edge['from']}->{edge['to']}:fixture:{add_edge_log}")
                        continue
                if init_edge != 0:
                    edge_failures.append(f"{component_type}:{edge['from']}->{edge['to']}:init:{init_edge_log}")
                    continue
                state_path = edge_project / ".modeling/state.json"
                edge_state = json.loads(state_path.read_text(encoding="utf-8"))
                if component_type == "project":
                    edge_state["project"]["state"] = edge["from"]
                else:
                    edge_state["components"][component_id]["state"] = edge["from"]
                    edge_state["components"][component_id]["status"] = (
                        "closed" if edge["from"] == terminal[component_type] else "active"
                    )
                write_json(state_path, edge_state)
                edge_plan = {
                    "schema_version": "11.0", "request": "验证状态机迁移路由闭合",
                    "window_context": "same_window",
                    "steps": [{
                        "id": "edge", "tier": "G2_CHECKPOINT", "mode": "promote",
                        "object": "state", "action": "transition", "component_id": component_id,
                        "events": ["recovery_assessment", "state_transition"], "facts": {}, "depends_on": [],
                        "change_set": {"paths": [".modeling/state.json"], "facets": ["state"], "claim_refs": []},
                        "state_effect": {"component_id": component_id, "from": edge["from"], "to": edge["to"]},
                    }],
                }
                edge_result = resolve(edge_plan, edge_project, root)
                if edge_result.get("status") != "resolved":
                    edge_failures.append(
                        f"{component_type}:{edge['from']}->{edge['to']}:"
                        + ",".join(edge_result.get("steps", [{}])[0].get("reasons", []))
                    )
        record(
            "SCENARIO.STATE.ALL_EDGES_RESOLVE",
            edge_count > 0 and not edge_failures,
            f"edges={edge_count};failures={edge_failures}",
        )

    errors = [item["id"] for item in cases if item["status"] != "pass"]
    result = {
        "schema_version": "14.0", "driver": "scenarios",
        "status": "pass" if not errors else "fail", "cases": cases, "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
