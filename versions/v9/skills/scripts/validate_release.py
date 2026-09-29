#!/usr/bin/env python3
"""Run the complete deterministic V9 release validation suite."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> dict:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def validate(source_root: Path | None = None) -> dict:
    contract_command = [sys.executable, "-B", "scripts/validate_contracts.py"]
    if source_root:
        contract_command.extend(["--source-root", str(source_root)])
    checks = [
        run(contract_command, SKILL_ROOT),
        run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "scripts", "-p", "test_*.py", "-v"], SKILL_ROOT),
    ]
    return {
        "release": "9.0.0",
        "status": "PASS" if all(check["returncode"] == 0 for check in checks) else "FAIL",
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    result = validate(args.source_root)
    print(json.dumps(result, ensure_ascii=False, indent=None if args.compact else 2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

