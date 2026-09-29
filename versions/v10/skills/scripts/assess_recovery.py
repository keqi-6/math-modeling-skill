#!/usr/bin/env python3
"""Classify project recovery from validated state, artifacts, and workspace manifest."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lib_v10 import (
    ContractError, build_workspace_manifest, json_output, load_state, transitive_consumers,
    validate_state_semantics,
)


LOCATABLE_FILE_ERRORS = (":missing", ":hash_mismatch", ":size_mismatch")


def manifest_diff(saved: dict[str, Any], current: dict[str, Any]) -> dict[str, list[str]]:
    saved_paths = set(saved)
    current_paths = set(current)
    return {
        "added": sorted(current_paths - saved_paths),
        "deleted": sorted(saved_paths - current_paths),
        "modified": sorted(
            path for path in saved_paths & current_paths
            if saved[path] != current[path]
        ),
    }


def assess(project_root: Path) -> dict[str, Any]:
    state, load_errors = load_state(project_root)
    if state is None:
        return {
            "schema_version": "10.0", "level": "R2_FULL", "state_valid": False,
            "reasons": load_errors, "changed_paths": [], "unowned_changes": [],
            "affected_components": [], "required_scope": "full_project_reconstruction"
        }
    full_errors = validate_state_semantics(state, project_root, check_files=True)
    structural_errors = [item for item in full_errors if not item.startswith("artifact:") or not item.endswith(LOCATABLE_FILE_ERRORS)]
    if structural_errors:
        return {
            "schema_version": "10.0", "level": "R2_FULL", "state_valid": False,
            "reasons": structural_errors, "changed_paths": [], "unowned_changes": [],
            "affected_components": [], "required_scope": "full_project_reconstruction"
        }
    try:
        current_manifest = build_workspace_manifest(project_root, state["watch_roots"])
    except ContractError as exc:
        return {
            "schema_version": "10.0", "level": "R2_FULL", "state_valid": False,
            "state_revision": state["revision"], "reasons": [str(exc)],
            "changed_paths": [], "unowned_changes": [], "affected_components": sorted(state["components"]),
            "required_scope": "full_project_reconstruction",
        }
    differences = manifest_diff(state["workspace_manifest"], current_manifest)
    changed_paths = sorted(set(differences["added"] + differences["deleted"] + differences["modified"]))
    registered = state["artifacts"]
    owned_changes: dict[str, list[str]] = {}
    unowned_changes: list[str] = []
    seed_components: set[str] = set()
    for path in changed_paths:
        artifact = registered.get(path)
        if artifact is None:
            unowned_changes.append(path)
            continue
        owners = []
        if artifact["producer"] in state["components"]:
            owners.append(artifact["producer"])
        owners.extend(item for item in artifact["consumers"] if item in state["components"])
        owned_changes[path] = sorted(set(owners))
        seed_components.update(owners)
    for error in full_errors:
        if error.startswith("artifact:") and error.endswith(LOCATABLE_FILE_ERRORS):
            parts = error.split(":")
            path = ":".join(parts[1:-1])
            artifact = registered.get(path)
            if artifact:
                owners = []
                if artifact["producer"] in state["components"]:
                    owners.append(artifact["producer"])
                owners.extend(item for item in artifact["consumers"] if item in state["components"])
                owned_changes.setdefault(path, sorted(set(owners)))
                seed_components.update(owners)
                if path not in changed_paths:
                    changed_paths.append(path)
    if unowned_changes:
        level = "R2_FULL"
        reasons = ["workspace changes cannot be mapped to registered artifacts"]
        affected = sorted(state["components"])
        required_scope = "full_project_reconstruction"
    elif changed_paths or full_errors:
        level = "R1_TARGETED"
        reasons = ["registered artifact changes are locatable"]
        affected = transitive_consumers(state["components"], seed_components)
        required_scope = "affected_components_and_transitive_consumers"
    else:
        level = "R0_CONTINUE"
        reasons = ["state, registered artifacts, and workspace manifest are consistent"]
        affected = []
        required_scope = "next_legal_action"
    return {
        "schema_version": "10.0",
        "level": level,
        "state_valid": not structural_errors,
        "state_revision": state["revision"],
        "reasons": reasons,
        "manifest_diff": differences,
        "changed_paths": sorted(set(changed_paths)),
        "owned_changes": owned_changes,
        "unowned_changes": sorted(unowned_changes),
        "affected_components": affected,
        "required_scope": required_scope,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.project_root)
    json_output(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
