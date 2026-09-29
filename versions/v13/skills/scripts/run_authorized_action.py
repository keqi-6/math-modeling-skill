#!/usr/bin/env python3
"""Re-resolve and execute one declared high-risk V11 runtime action.

Ordinary reads, edits, compilation, rendering, and scoped non-executing checks
do not use this entry.  It exists only for solver/verifier execution, existing
result recomputation, full-project audit, and Skill validation commands.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from lib_v10 import ContractError, SKILL_ROOT, json_output
from lib_v11 import resolve


def load_plan(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"runtime action plan unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("runtime action plan must be an object")
    return value


def authorized_action(
    plan: dict[str, Any],
    project_root: Path,
    step_id: str,
    action_id: str,
    skill_root: Path = SKILL_ROOT,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a fresh exact grant and its declared action or fail before launch."""
    resolution = resolve(plan, project_root.resolve(), skill_root.resolve())
    step = next(
        (item for item in resolution.get("steps", []) if item.get("id") == step_id),
        None,
    )
    if not isinstance(step, dict):
        raise ContractError(f"runtime action step not found: {step_id}")
    if step.get("status") != "resolved":
        reasons = ";".join(str(item) for item in step.get("reasons", []))
        raise ContractError(f"runtime action step is not resolved: {reasons}")
    action = next(
        (
            item for item in step.get("runtime_actions", [])
            if isinstance(item, dict) and item.get("id") == action_id
        ),
        None,
    )
    grant = next(
        (
            item for item in step.get("action_grants", [])
            if isinstance(item, dict) and item.get("runtime_action_id") == action_id
        ),
        None,
    )
    if not isinstance(action, dict) or not isinstance(grant, dict):
        raise ContractError(f"no executable grant for runtime action: {action_id}")
    if action.get("command") != grant.get("command"):
        raise ContractError("runtime action command differs from fresh grant")
    if grant.get("project_root") != str(project_root.resolve()):
        raise ContractError("runtime action project root differs from fresh grant")
    if grant.get("recovery_posture") != "NORMAL":
        raise ContractError("runtime action forbidden while R2 recovery is open")
    return grant, action


def execute(
    plan: dict[str, Any],
    project_root: Path,
    step_id: str,
    action_id: str,
    *,
    skill_root: Path = SKILL_ROOT,
    dry_run: bool = False,
) -> dict[str, Any]:
    grant, action = authorized_action(
        plan, project_root, step_id, action_id, skill_root
    )
    command = action["command"]
    cwd = (project_root.resolve() / command["cwd"]).resolve()
    if cwd != project_root.resolve() and project_root.resolve() not in cwd.parents:
        raise ContractError("runtime action cwd escapes project root")
    if not cwd.is_dir():
        raise ContractError(f"runtime action cwd is missing: {command['cwd']}")
    report = {
        "schema_version": "11.0",
        "status": "authorized" if dry_run else "pending",
        "step_id": step_id,
        "runtime_action_id": action_id,
        "grant_id": grant["grant_id"],
        "kind": grant["kind"],
        "command_hash": grant["command_hash"],
        "command": command,
        "project_root": str(project_root.resolve()),
        "exit_code": None,
    }
    if dry_run:
        return report
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    if grant["kind"] == "skill_package_validation":
        environment["V11_AUTHORIZED_SKILL_PACKAGE_VALIDATION"] = grant["grant_id"]
    elif grant["kind"] == "skill_targeted_validation":
        environment["V11_AUTHORIZED_SKILL_TARGETED_VALIDATION"] = grant["grant_id"]
    try:
        process = subprocess.run(
            list(command["argv"]), cwd=cwd, env=environment, check=False
        )
    except OSError as exc:
        raise ContractError(f"runtime action launch failed: {exc}") from exc
    report["exit_code"] = process.returncode
    report["status"] = "pass" if process.returncode == 0 else "fail"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--step-id", required=True)
    parser.add_argument("--action-id", required=True)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        report = execute(
            load_plan(args.plan), args.project_root, args.step_id, args.action_id,
            skill_root=args.root, dry_run=args.dry_run,
        )
    except (ContractError, OSError, ValueError) as exc:
        json_output({
            "schema_version": "11.0", "status": "blocked",
            "step_id": args.step_id, "runtime_action_id": args.action_id,
            "errors": [str(exc)],
        })
        return 2
    json_output(report)
    if report["status"] in {"authorized", "pass"}:
        return 0
    return int(report.get("exit_code") or 2)


if __name__ == "__main__":
    raise SystemExit(main())
