#!/usr/bin/env python3
"""Run inherited V15 and active V16 behavior scenarios."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def invoke(root: Path, relative: str, expected_schema: str) -> tuple[list[dict[str, Any]], list[str]]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, "-B", str(root / relative), "--root", str(root)],
        cwd=root, env=environment, text=True, capture_output=True,
        timeout=120, check=False,
    )
    errors: list[str] = []
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {}
        errors.append(relative + ":output_not_json")
    if process.returncode != 0 or payload.get("status") != "pass":
        errors.append(relative + ":failed")
    if payload.get("schema_version") != expected_schema:
        errors.append(relative + ":schema_version_invalid")
    cases = payload.get("cases", [])
    if not isinstance(cases, list) or not cases:
        errors.append(relative + ":cases_missing")
        cases = []
    return cases, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    inherited, errors = invoke(root, "scripts/run_v15_scenarios.py", "15.0")
    current, current_errors = invoke(root, "scripts/run_v16_gate_scenarios.py", "16.0")
    errors.extend(current_errors)
    recovery, recovery_errors = invoke(
        root, "scripts/run_v16_recovery_scenarios.py", "16.0"
    )
    errors.extend(recovery_errors)
    teammate, teammate_errors = invoke(
        root, "scripts/run_v16_teammate_brief_scenarios.py", "16.0"
    )
    errors.extend(teammate_errors)
    cases = inherited + current + recovery + teammate
    identifiers = [item.get("id") for item in cases if isinstance(item, dict)]
    if len(identifiers) != len(set(identifiers)):
        errors.append("scenario_case_id_duplicate")
    failed = [
        str(item.get("id")) for item in cases
        if not isinstance(item, dict) or item.get("status") != "pass"
    ]
    if failed:
        errors.append("scenario_cases_failed:" + ",".join(failed))
    result = {
        "schema_version": "16.1", "driver": "scenarios",
        "status": "pass" if not errors else "fail", "cases": cases,
        "evidence": {
            "inherited_v15_cases": len(inherited),
            "v16_gate_cases": len(current),
            "v16_recovery_cases": len(recovery),
            "v16_teammate_brief_cases": len(teammate),
            "total_cases": len(cases),
        },
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
