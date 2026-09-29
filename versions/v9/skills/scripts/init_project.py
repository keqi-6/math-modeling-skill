#!/usr/bin/env python3
"""Create only the minimal authorized V9 project state."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def initial_state(project_id: str) -> dict:
    return {
        "schema_version": "9.0.0",
        "project_id": project_id,
        "components": [],
        "artifacts": [],
        "open_decisions": [],
        "next_actions": [],
        "last_route": "RT-PROJECT-INIT",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def initialize(root: Path, project_id: str, authorized: bool) -> Path:
    if not authorized:
        raise PermissionError("explicit --authorized is required for project initialization")
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"project root does not exist: {root}")
    control_dir = root / ".modeling"
    state_path = control_dir / "state.json"
    if state_path.exists():
        raise FileExistsError(f"state already exists: {state_path}")
    control_dir.mkdir(exist_ok=True)
    payload = json.dumps(initial_state(project_id), ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix="state.", suffix=".tmp", dir=control_dir)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, state_path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return state_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()
    try:
        path = initialize(args.root, args.project_id, args.authorized)
    except (PermissionError, FileNotFoundError, FileExistsError) as exc:
        print(json.dumps({"status": "refused", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps({"status": "created", "path": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

