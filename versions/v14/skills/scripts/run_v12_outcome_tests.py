#!/usr/bin/env python3
"""Verify V12 platform behavior through disposable project filesystem outcomes."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def run(script: Path, *arguments: str) -> tuple[int, dict[str, Any], str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, "-B", str(script), *arguments],
        text=True,
        capture_output=True,
        check=False,
        timeout=15,
        env=environment,
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {}
    return process.returncode, payload, process.stderr[-500:]


def proposal(path: str, role: str, artifact_class: str) -> dict[str, Any]:
    return {
        "path": path,
        "platform_role": role,
        "purpose": "Provide a real solver consumed by question one.",
        "consumer_ids": ["q1"],
        "lifecycle": "working",
        "identity_class": "working",
        "class": artifact_class,
        "authorization_basis": "authorized test fixture",
        "replaces": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    state_manager = root / "scripts/state_manager.py"
    guard = root / "scripts/artifact_guard.py"
    case_results: list[dict[str, Any]] = []

    def record(case_id: str, passed: bool, evidence: str) -> None:
        case_results.append({"id": case_id, "status": "pass" if passed else "fail", "evidence": evidence})

    with tempfile.TemporaryDirectory(prefix="v12-platform-outcome-") as directory:
        project = Path(directory) / "new-project"
        code, _, stderr = run(
            state_manager, "init", "--project-root", str(project), "--project-id", "demo"
        )
        relative_files = sorted(path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file())
        canonical_dirs = {"data", "references", "planning", "src", "output", "docs", "paper", "delivery", "skills"}
        record(
            "OUTCOME.PLATFORM.INIT_CONTROL_ONLY",
            code == 0 and relative_files == [".modeling/state.json"] and not any((project / item).exists() for item in canonical_dirs),
            f"exit={code};files={relative_files};stderr={stderr}",
        )

        add_code, _, add_stderr = run(
            state_manager, "add-component", "--project-root", str(project),
            "--component-id", "q1", "--type", "question"
        )
        valid_path = Path(directory) / "valid-proposal.json"
        valid_path.write_text(json.dumps(proposal("src/q1/solve.py", "code", "code")), encoding="utf-8")
        guard_code, guard_payload, guard_stderr = run(
            guard, "--project-root", str(project), "--proposal", str(valid_path)
        )
        guard_did_not_create = not (project / "src").exists()
        (project / "src/q1").mkdir(parents=True)
        (project / "src/q1/solve.py").write_text("print('ok')\n", encoding="utf-8")
        register_code, _, register_stderr = run(
            state_manager, "register-artifact", "--project-root", str(project),
            "--proposal", str(valid_path), "--producer", "q1"
        )
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        registered_role = state.get("artifacts", {}).get("src/q1/solve.py", {}).get("role")
        record(
            "OUTCOME.PLATFORM.LAZY_CANONICAL",
            add_code == 0 and guard_code == 0 and guard_payload.get("status") == "admitted"
            and guard_did_not_create and register_code == 0 and registered_role == "code",
            f"add={add_code};guard={guard_code};guard_created_src={not guard_did_not_create};register={register_code};role={registered_role};stderr={add_stderr}{guard_stderr}{register_stderr}",
        )

        arbitrary_path = Path(directory) / "arbitrary-proposal.json"
        arbitrary = proposal("scratch/solve.py", "code", "code")
        arbitrary["purpose"] = "Provide a separate exploratory solver for question one."
        arbitrary_path.write_text(json.dumps(arbitrary), encoding="utf-8")
        arbitrary_code, arbitrary_payload, arbitrary_stderr = run(
            guard, "--project-root", str(project), "--proposal", str(arbitrary_path)
        )
        record(
            "OUTCOME.PLATFORM.REJECT_ARBITRARY_PATH",
            arbitrary_code != 0 and "platform_role_path_mismatch" in arbitrary_payload.get("errors", [])
            and not (project / "scratch").exists(),
            f"exit={arbitrary_code};errors={arbitrary_payload.get('errors')};stderr={arbitrary_stderr}",
        )

        mismatch_path = Path(directory) / "mismatch-proposal.json"
        mismatch_path.write_text(json.dumps(proposal("src/q1/input.csv", "code", "source")), encoding="utf-8")
        mismatch_code, mismatch_payload, mismatch_stderr = run(
            guard, "--project-root", str(project), "--proposal", str(mismatch_path)
        )
        record(
            "OUTCOME.PLATFORM.REJECT_ROLE_CLASS_MISMATCH",
            mismatch_code != 0 and "platform_role_class_mismatch" in mismatch_payload.get("errors", []),
            f"exit={mismatch_code};errors={mismatch_payload.get('errors')};stderr={mismatch_stderr}",
        )

    with tempfile.TemporaryDirectory(prefix="v12-existing-outcome-") as directory:
        project = Path(directory) / "existing-project"
        legacy = project / "legacy_code/solver.py"
        legacy.parent.mkdir(parents=True)
        original = "print('legacy')\n"
        legacy.write_text(original, encoding="utf-8")
        code, _, stderr = run(
            state_manager, "init", "--project-root", str(project), "--project-id", "existing"
        )
        record(
            "OUTCOME.PLATFORM.EXISTING_NO_AUTOMOVE",
            code == 0 and legacy.read_text(encoding="utf-8") == original and not (project / "src").exists(),
            f"exit={code};legacy_exists={legacy.exists()};src_exists={(project / 'src').exists()};stderr={stderr}",
        )

    with tempfile.TemporaryDirectory(prefix="v12-freeze-boundary-") as directory:
        destination = Path(directory) / "unauthorized-release"
        freeze_code, _, freeze_stderr = run(
            root / "scripts/freeze_release.py", "--root", str(root), "--destination", str(destination)
        )
        record(
            "OUTCOME.RELEASE.FREEZE_REQUIRES_AUTHORIZATION",
            freeze_code != 0 and not destination.exists(),
            f"exit={freeze_code};destination_exists={destination.exists()};stderr={freeze_stderr}",
        )

    declared = {
        item.get("id") for item in json.loads((root / "evals/platform-outcomes.json").read_text(encoding="utf-8")).get("cases", [])
    }
    executed = {item["id"] for item in case_results}
    if declared != executed:
        case_results.append({
            "id": "OUTCOME.REGISTRY.COVERAGE",
            "status": "fail",
            "evidence": f"declared={sorted(declared)};executed={sorted(executed)}",
        })
    errors = [item["id"] for item in case_results if item["status"] != "pass"]
    result = {
        "schema_version": "12.0",
        "driver": "outcomes",
        "status": "pass" if not errors else "fail",
        "cases": case_results,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
