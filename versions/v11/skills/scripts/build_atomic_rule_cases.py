#!/usr/bin/env python3
"""Build the frozen one-case-per-atom selection oracle after review."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from lib_v10 import SKILL_ROOT, ContractError, dump_json, load_json, load_rules, sha256_text
from run_behavior_evals import make_fixture


SEMANTIC_FIELDS = [
    "id", "revision", "capability", "semantic_key", "strength", "effect",
    "instruction_gloss", "failure_example", "scope", "trigger", "evidence",
    "outcomes", "exceptions", "conflicts_with", "refines", "depends_on",
    "enforcement", "owner",
]


def semantic_envelope(rule: dict[str, Any]) -> dict[str, Any]:
    return {field: rule[field] for field in SEMANTIC_FIELDS}


def envelope_sha256(rule: dict[str, Any]) -> str:
    payload = json.dumps(semantic_envelope(rule), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)


def resolve_case(root: Path, case: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="v10-atom-build-") as directory:
        project_root = Path(directory)
        fixture = case.get("fixture")
        if fixture is not None:
            make_fixture(project_root, fixture)
        command = [sys.executable, str(root / "scripts/resolve_route.py"), "--request", case["prompt"]]
        if fixture is not None:
            command.extend(["--project-root", str(project_root)])
        if case.get("component_id"):
            command.extend(["--component-id", case["component_id"]])
        if case.get("component_map"):
            command.extend(["--component-map", json.dumps(case["component_map"], ensure_ascii=False, sort_keys=True)])
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        process = subprocess.run(command, text=True, capture_output=True, cwd=root, env=environment)
        try:
            return json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise ContractError(f"resolver failed for {case['id']}: {process.stderr}") from exc


def build(root: Path) -> dict[str, Any]:
    behavior = load_json(root / "evals/behavior-cases.json")
    route_cases = [case for case in behavior["cases"] if case.get("kind") == "route"]
    observations = {case["id"]: resolve_case(root, case) for case in route_cases}
    rules, _ = load_rules(root)
    cases = []
    for rule in sorted((item for item in rules if item["status"] == "active"), key=lambda item: item["id"]):
        sources = []
        for behavior_case in route_cases:
            observed = observations[behavior_case["id"]]
            if rule["id"] not in observed.get("rule_ids", []):
                continue
            evidence = observed.get("applicability_evidence", {}).get(rule["id"], [])
            if any(item.get("status") == "applicable" for item in evidence):
                sources.append(behavior_case)
        if not sources:
            raise ContractError(f"active atom has no applicable route case: {rule['id']}")
        sources.sort(key=lambda item: (item["expected"].get("status") != "resolved", item["id"]))
        source = sources[0]
        cases.append({
            "id": f"ATOM.{rule['id']}",
            "kind": "atomic_rule",
            "driver": "atomic_rule_evals",
            "target_rule_id": rule["id"],
            "source_behavior_case_id": source["id"],
            "expected": {
                "applicability_status": "applicable",
                "source_status": observations[source["id"]]["status"],
                "revision": rule["revision"],
                "strength": rule["strength"],
                "effect": rule["effect"],
                "owner": rule["owner"],
                "enforcement_kind": rule["enforcement"]["kind"],
                "assurance": rule["enforcement"]["assurance"],
                "semantic_envelope_sha256": envelope_sha256(rule),
            },
            "verified_boundary": (
                "runtime_guard_and_selection" if rule["enforcement"]["kind"] == "runtime_guard"
                else "selection_and_semantic_delivery_only"
            ),
        })
    return {"schema_version": "10.0", "generated_by": "reviewed_atomic_case_builder", "cases": cases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    args = parser.parse_args()
    root = args.root.resolve()
    payload = build(root)
    dump_json(root / "evals/atomic-rule-cases.json", payload)
    print(json.dumps({"status": "written", "cases": len(payload["cases"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
