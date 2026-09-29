#!/usr/bin/env python3
"""Assess R0/R1/R2 from the authoritative project state and registered artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assess(root: Path, explicit_full: bool = False, closure: bool = False) -> dict[str, Any]:
    root = root.resolve()
    state_path = root / ".modeling" / "state.json"
    if explicit_full or closure:
        return {
            "level": "R2_FULL",
            "reasons": ["explicit_full_recovery" if explicit_full else "milestone_or_final_closure"],
            "affected_components": [],
            "affected_artifacts": [],
        }
    if not state_path.is_file():
        return {"level": "R2_FULL", "reasons": ["state_missing_or_invalid"], "affected_components": [], "affected_artifacts": []}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"level": "R2_FULL", "reasons": ["state_missing_or_invalid"], "affected_components": [], "affected_artifacts": []}

    contract = json.loads((SKILL_ROOT / "references" / "state-contract.json").read_text(encoding="utf-8"))
    missing_fields = [key for key in contract["project_state_required_fields"] if key not in state]
    if missing_fields:
        return {
            "level": "R2_FULL",
            "reasons": ["state_missing_or_invalid", f"missing_fields:{','.join(missing_fields)}"],
            "affected_components": [],
            "affected_artifacts": [],
        }

    changed_artifacts: list[str] = []
    affected_components: set[str] = set()
    unlocalizable = False
    for artifact in state.get("artifacts", []):
        relative = artifact.get("path")
        expected = artifact.get("sha256")
        component_ids = artifact.get("component_ids", [])
        if not relative or not expected:
            unlocalizable = True
            changed_artifacts.append(str(relative or "<missing-path>"))
            continue
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            unlocalizable = True
            changed_artifacts.append(relative)
            continue
        if not candidate.is_file() or file_sha256(candidate) != expected:
            changed_artifacts.append(relative)
            if component_ids:
                affected_components.update(component_ids)
            else:
                unlocalizable = True

    external = state.get("external_changes", [])
    for change in external:
        component_ids = change.get("component_ids", []) if isinstance(change, dict) else []
        if component_ids:
            affected_components.update(component_ids)
        else:
            unlocalizable = True

    if unlocalizable:
        level = "R2_FULL"
        reasons = ["changes_not_localizable"]
    elif changed_artifacts or external:
        level = "R1_TARGETED"
        reasons = ["registered_artifact_change"]
    else:
        level = "R0_CONTINUE"
        reasons = ["state_valid", "registered_artifacts_match", "no_unexplained_changes"]
    return {
        "level": level,
        "reasons": reasons,
        "affected_components": sorted(affected_components),
        "affected_artifacts": sorted(changed_artifacts),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--closure", action="store_true")
    args = parser.parse_args()
    print(json.dumps(assess(args.root, args.full, args.closure), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

