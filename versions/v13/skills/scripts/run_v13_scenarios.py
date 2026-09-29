#!/usr/bin/env python3
"""Run a few disposable, end-to-end V13 project-control scenarios."""

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
        "producer": "v13-scenario",
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
    cases: list[dict[str, Any]] = []

    def record(identifier: str, passed: bool, evidence_text: str) -> None:
        cases.append({"id": identifier, "status": "pass" if passed else "fail", "evidence": evidence_text})

    with tempfile.TemporaryDirectory(prefix="v13-scenarios-") as raw:
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
                "events": ["state_transition"], "facts": {}, "depends_on": [],
                "change_set": {"paths": [".modeling/state.json"], "facets": ["shared_data_state"], "claim_refs": []},
                "state_effect": {"component_id": "INPUTS", "from": "D0", "to": "D1"},
            }],
        }
        transition_path = workspace / "transition-plan.json"
        write_json(transition_path, transition_plan)
        transition_result = resolve(transition_plan, project, root)
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
            transition_result.get("status") == "resolved" and start_code == 0 and transition_code == 0
            and close_code == 0 and state["components"]["INPUTS"]["state"] == "D1"
            and state["executions"]["EXEC-TRANSITION"]["status"] == "closed",
            f"resolve={transition_result.get('status')};start={start_code};transition={transition_code};close={close_code};log={start_log}{transition_log}{close_log}",
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
                    "events": ["data_audit", "dataset_register"],
                    "facts": {"predictive_or_evaluative_use": False}, "depends_on": [],
                    "change_set": {"paths": paths, "facets": ["data_identity"], "claim_refs": []},
                }],
            }

        bad_plan = audit_plan(["planning/inputs.md"], "bad-identity-plan")
        bad_path = workspace / "bad-plan.json"
        write_json(bad_path, bad_plan)
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
            bad_start == 0 and bad_register != 0 and "outside sealed ChangeSet" in bad_log
            and void_code == 0 and state["executions"]["EXEC-BAD-IDENTITY"]["status"] == "void",
            f"register={bad_register};void={void_code};log={bad_log}{void_log}",
        )

        good_plan = audit_plan(["data/input.csv"], "good-identity-plan")
        good_path = workspace / "good-plan.json"
        write_json(good_path, good_plan)
        good_result = resolve(good_plan, project, root)
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
            good_result.get("status") == "resolved" and good_start == 0 and good_register == 0 and good_close == 0,
            f"resolve={good_result.get('status')}:{good_result.get('steps', [{}])[0].get('reasons')}:blocking={good_result.get('steps', [{}])[0].get('blocking_rule_ids')};start={good_start};register={good_register};close={good_close};log={good_start_log}{good_register_log}{good_close_log}",
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
                        "events": ["state_transition"], "facts": {}, "depends_on": [],
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
        "schema_version": "13.0", "driver": "scenarios",
        "status": "pass" if not errors else "fail", "cases": cases, "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
