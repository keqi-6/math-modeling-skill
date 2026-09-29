#!/usr/bin/env python3
"""Run raw-language routing cases in fresh interpreter processes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from lib_v10 import SKILL_ROOT, dump_json, json_output, load_json, now_iso, root_fingerprint


def make_fixture(root: Path, fixture: dict[str, Any]) -> None:
    if fixture.get("missing_state"):
        return
    timestamp = now_iso()
    components = {}
    for item in fixture.get("components", []):
        terminal = item["state"] in {"S7", "D3", "A3"}
        components[item["id"]] = {
            "type": item["type"], "state": item["state"],
            "status": item.get("status", "closed" if terminal else "active"),
            "dependencies": [], "consumers": [], "evidence": [], "decisions": [],
            "evidence_epoch_revision": 0, "invalidated_at_revision": None,
            "updated_at": timestamp,
        }
    artifacts: dict[str, Any] = {}
    workspace_manifest: dict[str, Any] = {}
    changed_artifact = fixture.get("r1_changed_artifact")
    if changed_artifact:
        rel = changed_artifact.get("path", "changed.txt")
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(changed_artifact.get("content", "changed\n"), encoding="utf-8")
        producer = changed_artifact["producer"]
        stale_hash = "0" * 64
        artifacts[rel] = {
            "sha256": stale_hash, "size": max(1, target.stat().st_size),
            "media_type": "text/plain", "role": "result", "lifecycle": "working",
            "producer": producer, "consumers": [producer], "status": "registered",
            "validated_at": None, "validation_evidence_id": None, "supersedes": None,
        }
        workspace_manifest[rel] = {"sha256": stale_hash, "size": target.stat().st_size}
    state = {
        "schema_version": "10.0", "revision": 1,
        "project": {
            "id": "eval-project", "state": fixture.get("project_state", "P0"),
            "root_fingerprint": root_fingerprint(root), "required_components": sorted(components),
            "created_at": timestamp, "updated_at": timestamp,
        },
        "components": components, "artifacts": artifacts,
        "open_decisions": fixture.get("open_decisions", []), "next_actions": [],
        "last_route": None, "executions": {}, "watch_roots": ["."], "workspace_manifest": workspace_manifest,
        "history": [{"revision": 1, "event": "eval_fixture", "at": timestamp, "subject": "eval-project", "details": {}}],
    }
    dump_json(root / ".modeling/state.json", state)


def run_case(case: dict[str, Any], skill_root: Path) -> dict[str, Any]:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="v10-route-eval-") as directory:
        project_root = Path(directory)
        fixture = case.get("fixture")
        if fixture is not None:
            make_fixture(project_root, fixture)
        command = [sys.executable, str(skill_root / "scripts/resolve_route.py"), "--request", case["prompt"]]
        if fixture is not None:
            command.extend(["--project-root", str(project_root)])
        if case.get("component_id"):
            command.extend(["--component-id", case["component_id"]])
        if case.get("component_map"):
            command.extend(["--component-map", json.dumps(case["component_map"], ensure_ascii=False, sort_keys=True)])
        process = subprocess.run(command, text=True, capture_output=True, cwd=skill_root)
        try:
            observed = json.loads(process.stdout)
        except json.JSONDecodeError:
            return {"id": case["id"], "status": "fail", "failures": ["resolver_output_not_json", process.stderr], "observed": process.stdout}
        expected = case["expected"]
        for field in ("status", "mode", "route_ids"):
            if field in expected and observed.get(field) != expected[field]:
                failures.append(f"{field}:{observed.get(field)!r}!={expected[field]!r}")
        if observed.get("request") != case["prompt"]:
            failures.append("raw_request_not_preserved")
        if len(observed.get("request_hash", "")) != 64:
            failures.append("request_hash_missing")
        if "rule_ids_include" in expected:
            missing = sorted(set(expected["rule_ids_include"]) - set(observed.get("rule_ids", [])))
            if missing:
                failures.append("missing_rule_ids:" + ",".join(missing))
        if "states" in expected:
            states = [node["state"] for node in observed.get("route_nodes", [])]
            if states != expected["states"]:
                failures.append(f"states:{states!r}!={expected['states']!r}")
        if "write_policies" in expected:
            policies = [node["write_policy"] for node in observed.get("route_nodes", [])]
            if policies != expected["write_policies"]:
                failures.append(f"write_policies:{policies!r}!={expected['write_policies']!r}")
        if "dependency_edge" in expected and expected["dependency_edge"] not in observed.get("dependencies", []):
            failures.append("missing_dependency_edge")
        if "component_ids_by_route" in expected:
            actual_bindings = {node["id"]: node.get("component_ids", []) for node in observed.get("route_nodes", [])}
            if actual_bindings != expected["component_ids_by_route"]:
                failures.append(f"component_ids_by_route:{actual_bindings!r}!={expected['component_ids_by_route']!r}")
        if len(observed.get("rule_ids", [])) > 60:
            failures.append("route_rule_budget_exceeded")
        if len(observed.get("context_refs", [])) > 4:
            failures.append("context_reference_budget_exceeded")
        expected_exit = 0 if expected.get("status") == "resolved" else 2
        if process.returncode != expected_exit:
            failures.append(f"exit_code:{process.returncode}!={expected_exit}")
        return {
            "id": case["id"], "status": "pass" if not failures else "fail", "failures": failures,
            "observed": {"status": observed.get("status"), "mode": observed.get("mode"), "route_ids": observed.get("route_ids"), "rule_count": len(observed.get("rule_ids", []))},
        }


def run(skill_root: Path, selected: set[str] | None = None) -> dict[str, Any]:
    payload = load_json(skill_root / "evals/behavior-cases.json")
    cases = [case for case in payload["cases"] if case.get("kind") == "route" and (selected is None or case["id"] in selected)]
    results = [run_case(case, skill_root) for case in cases]
    failed = [item for item in results if item["status"] != "pass"]
    return {
        "schema_version": "10.0", "status": "pass" if not failed else "fail",
        "driver": "fresh_process_raw_language_routes", "total": len(results), "passed": len(results) - len(failed),
        "failed": len(failed), "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    result = run(args.root.resolve(), set(args.case) if args.case else None)
    json_output(result)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
