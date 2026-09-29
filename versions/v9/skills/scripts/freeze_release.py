#!/usr/bin/env python3
"""Freeze a validated V9 package with a deterministic file manifest and report."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from validate_release import validate


SKILL_ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {
    "references/migration/release-manifest.json",
    "references/migration/v9-release-report.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    result = validate(args.source_root)
    if result["status"] != "PASS":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    files = []
    for path in sorted(SKILL_ROOT.rglob("*")):
        if not path.is_file() or path.suffix == ".pyc" or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(SKILL_ROOT).as_posix()
        if relative in EXCLUDED:
            continue
        files.append({"path": relative, "sha256": sha256(path), "bytes": path.stat().st_size})

    manifest = {
        "schema_version": "1.0",
        "release": "9.0.0",
        "status": "frozen",
        "file_count": len(files),
        "files": files,
    }
    manifest_path = SKILL_ROOT / "references" / "migration" / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ledger = json.loads((SKILL_ROOT / "references" / "migration" / "v1-v9-capability-ledger.json").read_text(encoding="utf-8"))
    route_contract = json.loads((SKILL_ROOT / "references" / "route-contract.json").read_text(encoding="utf-8"))
    module_manifest = json.loads((SKILL_ROOT / "references" / "migration" / "module-source-manifest.json").read_text(encoding="utf-8"))
    eval_registry = json.loads((SKILL_ROOT / "evals" / "registry.json").read_text(encoding="utf-8"))
    forward_results = json.loads((SKILL_ROOT / "evals" / "forward-results.json").read_text(encoding="utf-8"))
    differential_results = json.loads((SKILL_ROOT / "evals" / "differential-results.json").read_text(encoding="utf-8"))
    test_count = 0
    for check in result["checks"]:
        match = re.search(r"Ran (\d+) tests", check["stdout"] + check["stderr"])
        if match:
            test_count = max(test_count, int(match.group(1)))
    report = {
        "release": "9.0.0",
        "status": "accepted",
        "phases": {
            "V9-design": "complete",
            "V9-alpha": "complete",
            "V9-beta": "complete",
            "V9-rc": "complete",
            "V9.0.0": "complete"
        },
        "capability_coverage": ledger["coverage"],
        "v8_active_detail_sources": module_manifest["source_count"],
        "v8_active_detail_lines": sum(source["lines"] for module in module_manifest["modules"] for source in module["sources"]),
        "routes": len(route_contract["routes"]),
        "eval_definitions": len(eval_registry["evals"]),
        "deterministic_tests": test_count,
        "fresh_forward_scenarios": len(forward_results["scenarios"]),
        "fresh_forward_invocations": forward_results["method"]["independent_fresh_invocations"],
        "forward_issues_found_and_fixed": len(forward_results["issues_found_and_fixed"]),
        "unresolved_conflicts": 0,
        "readonly_file_creation": 0,
        "minimal_initialization": [".modeling/state.json"],
        "v8_bootstrap_files": differential_results["measurement"]["v8_bootstrap"]["files_created"],
        "v9_initialization_files": differential_results["measurement"]["v9_explicit_initialization"]["files_created"],
        "deterministic_validation": "PASS",
        "fresh_runtime_validation": "PASS",
        "future_behavior_change_gate": "fresh invocation required for every L2-L4 change",
        "rollback": "skills_v8 remains immutable beside skills_v9"
    }
    report_path = SKILL_ROOT / "references" / "migration" / "v9-release-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
