#!/usr/bin/env python3
"""Run the three outcome-focused V14 release drivers in fresh subprocesses."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


EXPECTED_DRIVERS = ("package", "contracts", "scenarios")
REQUIRED_SCENARIO_CASES = (
    "SCENARIO.PLATFORM.PLAN_PREFLIGHT",
    "SCENARIO.STATE.D0_D1_ROUNDTRIP",
    "SCENARIO.IDENTITY.PREFLIGHT_AND_VOID",
    "SCENARIO.RECOVERY.R1_NEW_WINDOW_ROUNDTRIP",
    "SCENARIO.SKILL.EXPLICIT_AUTHORIZATION",
    "SCENARIO.STATE.ALL_EDGES_RESOLVE",
)


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def tree_identity(root: Path) -> str:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        files.append([relative, sha256(path.read_bytes()), path.stat().st_size])
    return sha256(canonical(files))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    root = skill_root(args.root)
    errors: list[str] = []
    try:
        plan = json.loads((root / "evals/release/release-plan.json").read_text(encoding="utf-8"))
    except Exception as exc:
        plan = {}
        errors.append(f"release_plan_unreadable:{exc}")

    drivers = plan.get("drivers", []) if isinstance(plan, dict) else []
    driver_ids = tuple(item.get("id") for item in drivers if isinstance(item, dict))
    if plan.get("schema_version") != "14.0" or plan.get("release_id") != "V14.0.0":
        errors.append("release_plan_identity_invalid")
    if tuple(plan.get("required_drivers", [])) != EXPECTED_DRIVERS or driver_ids != EXPECTED_DRIVERS:
        errors.append("release_driver_set_invalid")
    if tuple(plan.get("required_case_ids", [])) != REQUIRED_SCENARIO_CASES:
        errors.append("release_required_scenario_cases_invalid")
    try:
        release_state = json.loads((root / "evals/release/release-state.json").read_text(encoding="utf-8"))
        if release_state.get("status") != "candidate" or release_state.get("frozen_at") is not None:
            errors.append("validation_requires_unfrozen_candidate")
    except Exception as exc:
        errors.append(f"release_state_unreadable:{exc}")
    before = tree_identity(root)
    results: list[dict[str, Any]] = []
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    if not errors:
        for declaration in drivers:
            driver_id = declaration["id"]
            relative = declaration.get("script", "")
            script = root / relative
            if script.parent != root / "scripts" or not script.is_file():
                errors.append(f"driver_script_invalid:{driver_id}:{relative}")
                continue
            command = [sys.executable, "-B", str(script), "--root", str(root)]
            try:
                process = subprocess.run(
                    command,
                    cwd=root,
                    env=environment,
                    text=True,
                    capture_output=True,
                    timeout=args.timeout,
                    check=False,
                )
                try:
                    payload = json.loads(process.stdout)
                except json.JSONDecodeError:
                    payload = {}
                passed = process.returncode == 0 and payload.get("status") == "pass" and payload.get("driver") == driver_id
                if driver_id == "scenarios":
                    case_status = {
                        item.get("id"): item.get("status")
                        for item in payload.get("cases", []) if isinstance(item, dict)
                    }
                    missing_or_failed = [
                        case_id for case_id in REQUIRED_SCENARIO_CASES
                        if case_status.get(case_id) != "pass"
                    ]
                    if missing_or_failed:
                        passed = False
                results.append({
                    "id": driver_id,
                    "status": "pass" if passed else "fail",
                    "fresh_subprocess": True,
                    "exit_code": process.returncode,
                    "checks": payload.get("checks", []),
                    "cases": payload.get("cases", []),
                    "evidence": payload.get("evidence", {}),
                    "errors": payload.get("errors", []),
                    "stderr": process.stderr[-500:],
                })
                if not passed:
                    errors.append(f"driver_failed:{driver_id}")
            except subprocess.TimeoutExpired:
                results.append({"id": driver_id, "status": "fail", "fresh_subprocess": True, "errors": ["timeout"]})
                errors.append(f"driver_timeout:{driver_id}")

    after = tree_identity(root)
    if after != before:
        errors.append("release_gate_mutated_candidate")
    report = {
        "schema_version": "14.0",
        "release_id": "V14.0.0",
        "status": "pass" if not errors else "fail",
        "tree_sha256": before,
        "drivers": results,
        "errors": errors,
    }
    report["report_sha256"] = sha256(canonical(report))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
