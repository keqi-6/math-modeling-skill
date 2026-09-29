#!/usr/bin/env python3
"""Forward regression for the V7 project scaffold and checkpoint writer."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BOOTSTRAP = HERE / "bootstrap_project.py"
CHECKPOINT = HERE / "session_checkpoint.py"
CONTRACT = ROOT / "references" / "scaffold-artifact-contract.json"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True, capture_output=True, text=True)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="v7-bootstrap-") as temporary:
        root = Path(temporary)
        (root / "skills").mkdir()
        run(str(BOOTSTRAP), "--root", str(root))

        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        actual_files = {
            path.relative_to(root).as_posix() for path in root.rglob("*")
            if path.is_file() and "skills" not in path.relative_to(root).parts
        }
        assert actual_files == set(contract["files"]), (actual_files, set(contract["files"]))
        for metadata in contract["files"].values():
            assert all(metadata.get(field) for field in ("owner", "consumer", "activation"))
        assert set(contract["directories"]) <= {
            path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_dir()
        }

        readme = (root / "README.md").read_text(encoding="utf-8")
        planning = (root / "planning" / "README.md").read_text(encoding="utf-8")
        state = json.loads((root / "project_state.json").read_text(encoding="utf-8"))
        assert "S0_RECOVER" in readme
        assert "Stage 0 — ORIENT" not in readme
        assert "skills/02-latex-setup.md" not in readme + planning
        assert "skills/rules/02-latex-setup.md" in readme + planning
        assert "solution_brief.md" in readme
        assert "current_stage" not in state and "stage_status" not in state
        assert state["components"]["shared_project"]["stage"] == "S0_RECOVER"
        assert state["project_summary"]["earliest_open_state"] == "S0_RECOVER"

        original = (root / "planning" / "understanding.md").read_text(encoding="utf-8")
        run(str(BOOTSTRAP), "--root", str(root))
        assert (root / "planning" / "understanding.md").read_text(encoding="utf-8") == original

        run(
            str(CHECKPOINT), "--root", str(root), "--component", "shared_project",
            "--stage", "S1_INTERPRET", "--stage-status", "in_progress",
        )
        state = json.loads((root / "project_state.json").read_text(encoding="utf-8"))
        assert state["components"]["shared_project"]["stage"] == "S1_INTERPRET"
        assert state["project_summary"]["earliest_open_state"] == "S1_INTERPRET"
        assert "current_stage" not in state and state["schema_version"] == "2.0"

    print("PASS: V7 bootstrap and component-authoritative checkpoint forward regression")


if __name__ == "__main__":
    main()
