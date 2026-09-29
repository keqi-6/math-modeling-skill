#!/usr/bin/env python3
"""Run an independently authored V11 forward-acceptance suite."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from lib_v10 import dump_json, now_iso
from state_v11 import evidence_binding_hash


def make_fixture(root: Path, fixture: dict[str, Any]) -> None:
    timestamp = now_iso()
    for relative in fixture.get("files", []):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("V11 forward fixture.\n", encoding="utf-8")
    declared = fixture.get("components", [])
    components: dict[str, dict[str, Any]] = {}
    for item in declared:
        terminal = item["state"] in {"S7", "D3", "A3"}
        components[item["id"]] = {
            "type": item["type"],
            "state": item["state"],
            "status": item.get("status", "closed" if terminal else "active"),
            "dependencies": sorted(set(item.get("dependencies", []))),
            "consumers": [],
            "evidence": [],
            "decisions": [],
            "invalidated_at_revision": None,
            "updated_at": timestamp,
        }
    for component_id, component in components.items():
        for dependency in component["dependencies"]:
            if dependency not in components:
                raise ValueError(f"unknown fixture dependency:{component_id}:{dependency}")
            components[dependency]["consumers"].append(component_id)
    for component in components.values():
        component["consumers"] = sorted(set(component["consumers"]))
    for declaration in fixture.get("evidence", []):
        component_id = declaration["component_id"]
        level = declaration["level"]
        evidence_id = declaration.get("id", f"EV-{component_id}-{level}")
        target = root / ".modeling/evidence-files" / f"{evidence_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"verified {level}\n", encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        claims = [f"claim:{component_id}:{level}"]
        components[component_id]["evidence"].append({
            "id": evidence_id, "level": level, "status": "pass", "kind": "file",
            "locator": {"path": target.relative_to(root).as_posix(), "sha256": digest},
            "claim": f"{level} is current for {component_id}", "observed_at": timestamp,
            "producer": "v11_forward_fixture", "subject_id": component_id,
            "input_refs": [], "claim_refs": claims,
            "binding_hash": evidence_binding_hash(component_id, level, [], claims),
            "recorded_revision": 1,
        })
    state = {
        "schema_version": "11.0",
        "revision": 1,
        "project": {
            "id": "forward-fixture",
            "state": fixture.get("project_state", "P0"),
            "required_components": sorted(components),
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        "components": components,
        "artifacts": {},
        "open_decisions": [],
        "next_actions": [],
        "history": [{
            "revision": 1,
            "event": "forward_fixture",
            "at": timestamp,
            "subject": "forward-fixture",
            "details": {},
        }],
    }
    dump_json(root / ".modeling/state.json", state)


def invoke(command: list[str], root: Path, skill_root: Path) -> tuple[int, dict[str, Any] | None, str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        command,
        cwd=skill_root,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    try:
        observed = json.loads(process.stdout)
    except json.JSONDecodeError:
        observed = None
    return process.returncode, observed, process.stderr or process.stdout


def recovery_value(step: dict[str, Any]) -> Any:
    value = step.get("recovery")
    return value.get("level") if isinstance(value, dict) else value


def check_plan(case: dict[str, Any], skill_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    plan = case.get("plan", case.get("invalid_plan"))
    if not isinstance(plan, dict):
        return {"id": case.get("id"), "status": "fail", "failures": ["plan_missing"]}
    with tempfile.TemporaryDirectory(prefix="v11-forward-") as raw:
        project_root = Path(raw)
        fixture = case.get("fixture")
        if isinstance(fixture, dict):
            make_fixture(project_root, fixture)
        command = [
            sys.executable,
            "-B",
            str(skill_root / "scripts/resolve_route.py"),
            "--plan-json",
            json.dumps(plan, ensure_ascii=False, sort_keys=True),
        ]
        if isinstance(fixture, dict):
            command.extend(["--project-root", str(project_root)])
        exit_code, observed, detail = invoke(command, project_root, skill_root)
    if observed is None:
        return {"id": case["id"], "status": "fail", "failures": ["resolver_output_not_json", detail]}
    expected = case["expected"]
    if observed.get("status") != expected.get("status"):
        failures.append(f"status:{observed.get('status')}!={expected.get('status')}")
    expected_exit = {"resolved": 0, "partial": 3, "blocked": 2}[expected.get("status")]
    if exit_code != expected_exit:
        failures.append(f"exit_code:{exit_code}!={expected_exit}")
    steps = {item.get("id"): item for item in observed.get("steps", [])}
    for step_id, status in expected.get("step_statuses", {}).items():
        if steps.get(step_id, {}).get("status") != status:
            failures.append(f"step_status:{step_id}:{steps.get(step_id, {}).get('status')}!={status}")
    if "route_ids" in expected and observed.get("route_ids") != expected["route_ids"]:
        failures.append(f"route_ids:{observed.get('route_ids')}!={expected['route_ids']}")
    for step_id, value in expected.get("recovery", {}).items():
        if recovery_value(steps.get(step_id, {})) != value:
            failures.append(f"recovery:{step_id}:{recovery_value(steps.get(step_id, {}))}!={value}")
    for step_id, count in expected.get("path_count", {}).items():
        actual = len(steps.get(step_id, {}).get("change_set", {}).get("paths", []))
        if actual != count:
            failures.append(f"path_count:{step_id}:{actual}!={count}")
    rule_ids = observed.get("rule_ids", [])
    missing_rules = sorted(set(expected.get("required_rule_ids", [])) - set(rule_ids))
    if missing_rules:
        failures.append("required_rule_ids_missing:" + ",".join(missing_rules))
    leaked_rules = sorted(set(expected.get("excluded_rule_ids", [])) & set(rule_ids))
    if leaked_rules:
        failures.append("excluded_rule_ids:" + ",".join(leaked_rules))
    for prefix in expected.get("excluded_rule_prefixes", []):
        leaked = [rule_id for rule_id in rule_ids if rule_id.startswith(prefix)]
        if leaked:
            failures.append(f"excluded_rule_prefix:{prefix}:{','.join(leaked)}")
    for step_id, needle in expected.get("reason_contains", {}).items():
        reasons = "|".join(steps.get(step_id, {}).get("reasons", []))
        if needle not in reasons:
            failures.append(f"reason_missing:{step_id}:{needle}")
    for step_id, events in expected.get("controller_events_by_step", {}).items():
        actual_events = steps.get(step_id, {}).get("controller_events", [])
        if not set(events).issubset(actual_events):
            failures.append(
                f"controller_events_missing:{step_id}:"
                + ",".join(sorted(set(events) - set(actual_events)))
            )
    for step_id, source in expected.get("state_source_by_step", {}).items():
        if steps.get(step_id, {}).get("state_source") != source:
            failures.append(
                f"state_source:{step_id}:{steps.get(step_id, {}).get('state_source')}!={source}"
            )
    for step_id, events in expected.get("events_by_step", {}).items():
        if steps.get(step_id, {}).get("events") != events:
            failures.append(
                f"events:{step_id}:{steps.get(step_id, {}).get('events')}!={events}"
            )
    for step_id, component_ids in expected.get("component_ids_by_step", {}).items():
        if steps.get(step_id, {}).get("component_ids") != component_ids:
            failures.append(
                f"component_ids:{step_id}:"
                f"{steps.get(step_id, {}).get('component_ids')}!={component_ids}"
            )
    actual_events = {
        event for step in observed.get("steps", []) for event in step.get("events", [])
    }
    leaked_events = sorted(actual_events & set(expected.get("forbidden_events", [])))
    if leaked_events:
        failures.append("forbidden_events:" + ",".join(leaked_events))
    if "action_grant_count" in expected and len(observed.get("action_grants", [])) != expected["action_grant_count"]:
        failures.append(
            f"action_grant_count:{len(observed.get('action_grants', []))}!={expected['action_grant_count']}"
        )
    if "execution_order" in expected and observed.get("execution_order") != expected["execution_order"]:
        failures.append(f"execution_order:{observed.get('execution_order')}!={expected['execution_order']}")
    if "machine_keyword_classification" in expected:
        values = [
            item.get("governance_evidence", {}).get("machine_keyword_classification")
            for item in observed.get("steps", [])
            if item.get("governance_evidence") is not None
        ]
        if not values or any(value != expected["machine_keyword_classification"] for value in values):
            failures.append(f"machine_keyword_classification:{values}")
    if "step_modes" in expected and observed.get("mode_model", {}).get("step_modes") != expected["step_modes"]:
        failures.append("step_modes_mismatch")
    if "dependency" in expected and expected["dependency"] not in observed.get("dependencies", []):
        failures.append("dependency_missing")
    if expected.get("request_preserved") and observed.get("request") != plan["request"]:
        failures.append("request_not_preserved")
    return {
        "id": case["id"],
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "observed": {
            "status": observed.get("status"),
            "route_ids": observed.get("route_ids"),
            "step_statuses": {key: value.get("status") for key, value in steps.items()},
        },
    }


def check_raw_cli(case: dict[str, Any], skill_root: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        "-B",
        str(skill_root / "scripts/resolve_route.py"),
        "--request",
        case["request"],
    ]
    exit_code, observed, detail = invoke(command, skill_root, skill_root)
    failures: list[str] = []
    expected = case["expected"]
    if observed is None:
        failures.append("resolver_output_not_json:" + detail)
    else:
        if observed.get("status") != expected.get("status"):
            failures.append("status_mismatch")
        if observed.get("error") != expected.get("error"):
            failures.append("error_mismatch")
    if exit_code != expected.get("exit_code"):
        failures.append(f"exit_code:{exit_code}!={expected.get('exit_code')}")
    return {"id": case["id"], "status": "pass" if not failures else "fail", "failures": failures}


def run(root: Path, selected: set[str] | None = None) -> dict[str, Any]:
    payload = json.loads((root / "evals/forward-acceptance-cases.json").read_text(encoding="utf-8"))
    cases = [
        case for case in payload.get("cases", [])
        if isinstance(case, dict) and (selected is None or case.get("id") in selected)
    ]
    results = [
        check_raw_cli(case, root) if case.get("type") == "raw_cli" else check_plan(case, root)
        for case in cases
    ]
    failed = [item for item in results if item["status"] != "pass"]
    return {
        "schema_version": "11.0",
        "status": "pass" if not failed else "fail",
        "driver": "independent_forward_acceptance",
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    report = run(args.root.resolve(), set(args.case) if args.case else None)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
