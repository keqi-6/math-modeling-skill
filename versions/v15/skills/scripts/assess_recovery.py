#!/usr/bin/env python3
"""Assess V11 recovery from protected registered identities only."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Iterable

from lib_v10 import (
    ContractError, build_workspace_manifest, json_output, relative_safe, sha256_file,
)
from state_v11 import (
    PROTECTED_IDENTITY_CLASSES,
    artifact_is_current_formal,
    load_state,
    transitive_consumers,
    validate_state_semantics,
)


GATES = {"G1", "G2", "G3"}


def recovery_execution_boundary(level: str) -> dict[str, Any]:
    """Describe execution posture without turning recovery into recomputation."""
    open_barrier = level == "R2_FULL"
    return {
        "barrier_open": open_barrier,
        "recomputation_authorized": False,
        "allowed_actions": [
            "read", "enumerate", "hash", "compare", "parse",
            "reconstruct_control_metadata", "reuse_current_identity",
            "record_known_gap",
        ] if open_barrier else [],
        "blocked_action_classes": [
            "model_execution", "verification_execution", "recompute_existing_result",
            "manuscript_mutation", "delivery_build",
        ] if open_barrier else [],
        "requires_fresh_resolution_to_continue": open_barrier,
    }


def manifest_diff(saved: dict[str, Any], current: dict[str, Any]) -> dict[str, list[str]]:
    """Compatibility helper; V11 recovery no longer builds a workspace manifest."""
    saved_paths = set(saved)
    current_paths = set(current)
    return {
        "added": sorted(current_paths - saved_paths),
        "deleted": sorted(saved_paths - current_paths),
        "modified": sorted(
            path for path in saved_paths & current_paths if saved[path] != current[path]
        ),
    }


def _protected_identity_changes(
    project_root: Path,
    state: dict[str, Any],
    scope_paths: set[str] | None = None,
) -> tuple[list[str], dict[str, list[str]], list[str]]:
    changed: list[str] = []
    owners: dict[str, list[str]] = {}
    errors: list[str] = []
    components = state.get("components", {})
    project = state.get("project", {})
    artifacts = state.get("artifacts", {})
    if not isinstance(components, dict) or not isinstance(project, dict) or not isinstance(artifacts, dict):
        return [], {}, ["protected_identity_registry_not_object"]
    project_id = project.get("id")
    for rel, artifact in sorted(artifacts.items()):
        if not isinstance(rel, str) or not isinstance(artifact, dict):
            errors.append(f"artifact:{rel}:identity_not_object")
            continue
        if not artifact_is_current_formal(artifact):
            continue
        if scope_paths is not None and rel not in scope_paths:
            continue
        try:
            path, normalized = relative_safe(project_root, rel)
        except ContractError as exc:
            errors.append(f"artifact:{rel}:{exc}")
            continue
        if normalized != rel:
            errors.append(f"artifact:{rel}:non_normalized_path")
            continue
        producer = artifact.get("producer")
        consumers = artifact.get("consumers", [])
        component_owners = []
        if producer in components:
            component_owners.append(producer)
        elif producer != project_id:
            errors.append(f"artifact:{rel}:unknown_producer")
        unknown_consumers = set(consumers) - set(components) - {project_id}
        if unknown_consumers:
            errors.append(
                f"artifact:{rel}:unknown_consumers:" + ",".join(sorted(unknown_consumers))
            )
        component_owners.extend(item for item in consumers if item in components)
        if not component_owners and producer != project_id and project_id not in consumers:
            errors.append(f"artifact:{rel}:identity_has_no_owner")
        if not path.is_file() or sha256_file(path) != artifact.get("sha256"):
            changed.append(rel)
            owners[rel] = sorted(set(component_owners))
    return sorted(changed), owners, sorted(set(errors))


def scope_paths_for_step(state: dict[str, Any], step: dict[str, Any]) -> list[str]:
    """Derive a formal identity closure and remain total on legacy V9 shapes."""
    change_set = step.get("change_set")
    declared_paths = change_set.get("paths", []) if isinstance(change_set, dict) else []
    paths = {item for item in declared_paths if isinstance(item, str)}
    declared_components = step.get("component_ids", [])
    component_ids = {
        item for item in declared_components if isinstance(item, str)
    } if isinstance(declared_components, list) else set()
    project = state.get("project", {}) if isinstance(state, dict) else {}
    artifacts = state.get("artifacts", {}) if isinstance(state, dict) else {}
    if not isinstance(project, dict):
        project = {}
    if not isinstance(artifacts, dict):
        artifacts = {}
    # A pause/handoff synchronizes the control plane only.  It must never expand
    # an omitted component selector to every required project component.
    is_pause = step.get("action") == "pause"
    required = project.get("required_components", [])
    if (
        not is_pause and not component_ids
        and step.get("object") in {"project", "delivery"}
        and isinstance(required, list)
    ):
        component_ids.update(item for item in required if isinstance(item, str))
    project_id = project.get("id")
    for path, artifact in artifacts.items():
        if not isinstance(path, str) or not isinstance(artifact, dict):
            continue
        if not artifact_is_current_formal(artifact):
            continue
        consumers = artifact.get("consumers", [])
        if not isinstance(consumers, list):
            consumers = []
        owners = {artifact.get("producer"), *consumers}
        if component_ids.intersection(owners) or (
            step.get("tier") == "G3_RELEASE" and project_id in owners
        ):
            paths.add(path)
    return sorted(paths)


def assess(
    project_root: Path,
    explicit_full: bool = False,
    gate: str = "G1",
    scope_paths: Iterable[str] | None = None,
    new_window: bool = True,
) -> dict[str, Any]:
    """Classify recovery without treating ordinary working files as corruption.

    ``new_window`` encodes V8's same-uninterrupted-session boundary: a fresh
    window/context must never classify a consistent state as R0.  The caller
    derives it from the semantic plan's ``window_context``; unknown/missing
    plans are treated as new window by the policy.
    """
    if gate not in GATES:
        raise ContractError(f"unknown gate: {gate}")
    state, load_errors = load_state(project_root)
    if state is None:
        return {
            "schema_version": "11.0", "level": "R2_FULL", "state_valid": False,
            "gate": gate, "reasons": load_errors, "changed_paths": [],
            "owned_changes": {}, "affected_components": [],
            "required_scope": "reconstruct_control_state_and_registered_identity_index_without_recomputation",
            "state_format": "missing_or_unreadable",
            "execution_boundary": recovery_execution_boundary("R2_FULL"),
        }
    structural_errors = validate_state_semantics(state, project_root, check_files=False)
    if structural_errors:
        return {
            "schema_version": "11.0", "level": "R2_FULL", "state_valid": False,
            "state_revision": state.get("revision"), "gate": gate,
            "reasons": structural_errors, "changed_paths": [], "owned_changes": {},
            "affected_components": [],
            "required_scope": "reconstruct_control_state_and_registered_identity_index_without_recomputation",
            "state_format": (
                "legacy_or_incompatible" if state.get("schema_version") != "11.0"
                or not isinstance(state.get("components"), dict)
                or not isinstance(state.get("artifacts"), dict)
                else "invalid_v11"
            ),
            "execution_boundary": recovery_execution_boundary("R2_FULL"),
        }

    normalized_scope = None if scope_paths is None else set(scope_paths)
    changed_paths, owned_changes, identity_errors = _protected_identity_changes(
        project_root, state, normalized_scope
    )
    if identity_errors:
        return {
            "schema_version": "11.0", "level": "R2_FULL", "state_valid": False,
            "state_revision": state["revision"], "gate": gate,
            "reasons": identity_errors, "changed_paths": changed_paths,
            "owned_changes": owned_changes, "affected_components": sorted(state["components"]),
            "required_scope": "repair_state_or_identity_conflict_without_implicit_recomputation",
            "state_format": "invalid_v11_identity_registry",
            "execution_boundary": recovery_execution_boundary("R2_FULL"),
        }

    workspace_diff: dict[str, list[str]] | None = None
    workspace_baseline_missing = False
    if new_window and not explicit_full:
        baseline = state.get("workspace_baseline")
        watch_roots = state.get("watch_roots") or ["."]
        if not isinstance(baseline, dict):
            workspace_baseline_missing = True
        else:
            try:
                current_workspace = build_workspace_manifest(project_root, watch_roots)
                workspace_diff = manifest_diff(baseline, current_workspace)
            except (ContractError, OSError, ValueError):
                workspace_baseline_missing = True

    seed_components = {
        component_id
        for component_ids in owned_changes.values()
        for component_id in component_ids
    }
    affected = transitive_consumers(state["components"], seed_components)
    workspace_changed_paths = sorted(set(
        (workspace_diff or {}).get("added", [])
        + (workspace_diff or {}).get("deleted", [])
        + (workspace_diff or {}).get("modified", [])
    ))
    all_changed_paths = sorted(set(changed_paths) | set(workspace_changed_paths))
    if explicit_full:
        level = "R2_FULL"
        reasons = ["explicit_full_recovery"]
        required_scope = "full_registered_identity_and_evidence_gap_reconstruction_without_implicit_recomputation"
        affected = sorted(state["components"])
    elif changed_paths or workspace_changed_paths:
        level = "R1_TARGETED"
        reasons = []
        if changed_paths:
            reasons.append("protected_registered_identity_changed")
        if workspace_changed_paths:
            reasons.append("workspace_changes_detected")
        if new_window:
            reasons.append("new_window_requires_targeted_recovery")
        required_scope = "changed_identity_and_workspace_delta_and_true_downstream_consumers"
        affected = transitive_consumers(state["components"], seed_components)
    elif new_window and workspace_baseline_missing:
        level = "R1_TARGETED"
        reasons = ["new_window_requires_targeted_recovery", "workspace_baseline_missing"]
        required_scope = "establish_or_verify_recovery_baseline_without_recomputation"
        affected = []
    elif new_window:
        level = "R1_TARGETED"
        reasons = ["new_window_requires_targeted_recovery"]
        required_scope = "new_window_registered_identity_and_direct_consumer_review"
        affected = []
    else:
        level = "R0_CONTINUE"
        reasons = ["protected_registered_identities_consistent"]
        required_scope = (
            "declared_release_identity_and_evidence_scope"
            if gate == "G3" else "next_legal_action"
        )
        affected = []
    working = sorted(
        rel for rel, artifact in state.get("artifacts", {}).items()
        if artifact.get("identity_class") not in PROTECTED_IDENTITY_CLASSES
    )
    return {
        "schema_version": "11.0", "level": level, "state_valid": True,
        "state_revision": state["revision"], "gate": gate, "reasons": reasons,
        "changed_paths": all_changed_paths, "owned_changes": owned_changes,
        "affected_components": affected, "unmonitored_working_artifacts": working,
        "workspace_diff": workspace_diff,
        "workspace_baseline_missing": workspace_baseline_missing,
        "required_scope": required_scope,
        "state_format": "v11",
        "execution_boundary": recovery_execution_boundary(level),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--gate", choices=sorted(GATES), default="G1")
    parser.add_argument("--full", action="store_true")
    context = parser.add_mutually_exclusive_group()
    context.add_argument("--new-window", action="store_true", help="Treat this as a fresh window/context; R0 is not allowed.")
    context.add_argument("--same-window", action="store_true", help="Assert direct continuity with the same uninterrupted session.")
    args = parser.parse_args()
    try:
        result = assess(
            args.project_root,
            explicit_full=args.full,
            gate=args.gate,
            new_window=not args.same_window,
        )
    except ContractError as exc:
        json_output({"schema_version": "11.0", "status": "fail", "errors": [str(exc)]})
        return 2
    json_output(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
