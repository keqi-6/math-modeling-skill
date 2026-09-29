#!/usr/bin/env python3
"""Shared V16 recovery proofs, baselines, and receipt bindings.

Recovery decides how much context must be restored.  It never performs
ChangeSet invalidation or propagation; those remain execution/state concerns.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib_v10 import build_workspace_manifest, sha256_text
from lib_v11 import canonical_json
from recovery_v14 import (
    assessment_sha256, manifest_sha256, recovery_assessment,
    required_recovery_reads, validate_read_receipts,
)


BASELINE_POLICY = {
    "version": "workspace-baseline-v16.0",
    "coverage_roots": ["."],
    "ignored_items_are_classified_by_r2": True,
    "state_file_excluded_from_workspace_delta": True,
}


def root_fingerprint(project_root: Path, state: dict[str, Any]) -> str:
    return sha256_text(canonical_json({
        "project_root": project_root.resolve().as_posix(),
        "project_id": state.get("project", {}).get("id"),
    }))


def component_graph_sha256(state: dict[str, Any]) -> str:
    graph = {
        component_id: {
            "type": component.get("type"),
            "dependencies": sorted(component.get("dependencies", [])),
            "consumers": sorted(component.get("consumers", [])),
        }
        for component_id, component in sorted(state.get("components", {}).items())
        if isinstance(component_id, str) and isinstance(component, dict)
    }
    return sha256_text(canonical_json(graph))


def artifact_registry_sha256(state: dict[str, Any]) -> str:
    registry = {
        path: {
            "producer": artifact.get("producer"),
            "consumers": sorted(artifact.get("consumers", [])),
            "role": artifact.get("role"),
            "class": artifact.get("class"),
            "identity_class": artifact.get("identity_class"),
            "sha256": artifact.get("sha256"),
            "size": artifact.get("size"),
        }
        for path, artifact in sorted(state.get("artifacts", {}).items())
        if isinstance(path, str) and isinstance(artifact, dict)
    }
    return sha256_text(canonical_json(registry))


def inventory_policy_sha256() -> str:
    return sha256_text(canonical_json(BASELINE_POLICY))


def make_baseline_meta(
    project_root: Path,
    state: dict[str, Any],
    manifest: dict[str, Any],
    *,
    captured_revision: int,
    established_kind: str,
    source_id: str | None = None,
    coverage_roots: list[str] | None = None,
    coverage_complete: bool | None = None,
    continuity_change_set: dict[str, Any] | None = None,
) -> dict[str, Any]:
    roots = sorted(set(coverage_roots or state.get("watch_roots") or ["."]))
    complete = roots == ["."] if coverage_complete is None else coverage_complete
    established_by: dict[str, Any] = {"kind": established_kind}
    if source_id is not None:
        established_by["source_id"] = source_id
    return {
        "root_fingerprint": root_fingerprint(project_root, state),
        "coverage_roots": roots,
        "coverage_complete": bool(complete),
        "manifest_sha256": manifest_sha256(manifest),
        "inventory_policy_sha256": inventory_policy_sha256(),
        "captured_revision": captured_revision,
        "component_graph_sha256": component_graph_sha256(state),
        "artifact_registry_sha256": artifact_registry_sha256(state),
        "established_by": established_by,
        "file_count": len(manifest),
        "unresolved": [],
        "continuity_change_set": continuity_change_set or {
            "paths": [], "component_ids": [], "facets": [],
            "propagation_complete": True,
        },
    }


def establish_workspace_baseline(
    project_root: Path,
    state: dict[str, Any],
    *,
    captured_revision: int,
    established_kind: str,
    source_id: str | None = None,
    continuity_change_set: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Capture the complete workspace-delta baseline used for later R0/R1.

    R2's evidence manifest is stricter and inventories ignored/cache/control
    objects as well.  This baseline intentionally uses the runtime delta policy,
    but records that policy and requires whole-root coverage so it cannot be
    mistaken for R2 proof.
    """
    state["watch_roots"] = ["."]
    manifest = build_workspace_manifest(project_root.resolve(), ["."])
    meta = make_baseline_meta(
        project_root, state, manifest,
        captured_revision=captured_revision,
        established_kind=established_kind,
        source_id=source_id,
        coverage_roots=["."], coverage_complete=True,
        continuity_change_set=continuity_change_set,
    )
    return manifest, meta


def baseline_proof_errors(
    project_root: Path,
    state: dict[str, Any],
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    baseline = state.get("workspace_baseline")
    meta = state.get("workspace_baseline_meta")
    if not isinstance(baseline, dict):
        return ["baseline_missing"]
    if not isinstance(meta, dict):
        return ["baseline_metadata_missing"]
    errors: list[str] = []
    current_manifest = manifest if isinstance(manifest, dict) else baseline
    expected = {
        "root_fingerprint": root_fingerprint(project_root, state),
        "coverage_roots": ["."],
        "coverage_complete": True,
        "manifest_sha256": manifest_sha256(baseline),
        "inventory_policy_sha256": inventory_policy_sha256(),
        "component_graph_sha256": component_graph_sha256(state),
        "artifact_registry_sha256": artifact_registry_sha256(state),
    }
    for field, value in expected.items():
        if meta.get(field) != value:
            errors.append("baseline_binding_mismatch:" + field)
    revision = meta.get("captured_revision")
    if not isinstance(revision, int) or revision < 1 or revision > state.get("revision", 0):
        errors.append("baseline_captured_revision_invalid")
    if meta.get("unresolved") != []:
        errors.append("baseline_unresolved_items")
    if meta.get("file_count") != len(baseline):
        errors.append("baseline_file_count_mismatch")
    if not isinstance(meta.get("established_by"), dict):
        errors.append("baseline_source_missing")
    if current_manifest is baseline:
        return sorted(set(errors))
    return sorted(set(errors))


def closed_recovery_errors(
    project_root: Path,
    state: dict[str, Any],
    resolution: dict[str, Any],
    step: dict[str, Any],
    recovery_id: str | None,
    *,
    allow_checkpoint_revision: bool = True,
) -> list[str]:
    """Bind one closed R1 or R2 episode to the current formal step."""
    level = recovery_assessment(step).get("level")
    if level not in {"R1_TARGETED", "R2_FULL"}:
        return ["closed_recovery_not_applicable"]
    prefix = "r1" if level == "R1_TARGETED" else "r2"
    if not recovery_id:
        return [prefix + "_closed_recovery_id_required"]
    record = state.get("recoveries", {}).get(recovery_id)
    if not isinstance(record, dict):
        return [prefix + "_recovery_not_registered"]
    errors: list[str] = []
    if record.get("status") != "closed" or record.get("outcome") not in {"ready", "blocked"}:
        errors.append(prefix + "_recovery_not_closed")
    if record.get("outcome") == "blocked" and step.get("mode") != "project_readonly":
        errors.append(prefix + "_blocked_recovery_cannot_authorize_mutation")
    expected_window = step.get("facts", {}).get("window_context")
    for field, expected in (
        ("plan_hash", resolution.get("plan_hash")),
        ("request_hash", resolution.get("request_hash")),
        ("step_id", step.get("id")),
        ("window_context", expected_window),
        ("recovery_level", level),
    ):
        if record.get(field) != expected:
            errors.append(prefix + "_recovery_binding_mismatch:" + field)
    if record.get("component_ids") != sorted(step.get("component_ids", [])):
        errors.append(prefix + "_recovery_binding_mismatch:component_ids")
    if record.get("consumed_by_execution") is not None:
        errors.append(prefix + "_recovery_already_consumed")
    allowed_revisions = {record.get("end_revision"), record.get("baseline_revision")}
    if allow_checkpoint_revision:
        allowed_revisions.add(record.get("checkpoint_revision"))
    if state.get("revision") not in {item for item in allowed_revisions if isinstance(item, int)}:
        errors.append(prefix + "_recovery_state_revision_advanced")
    current_manifest = build_workspace_manifest(project_root.resolve(), ["."])
    if manifest_sha256(current_manifest) != record.get("reviewed_manifest_sha256"):
        errors.append(prefix + "_recovery_workspace_changed_after_review")
    if level == "R1_TARGETED":
        errors.extend(validate_read_receipts(
            project_root, record.get("required_reads", []), record.get("read_receipts", []),
            verify_dynamic_state_file=False,
        ))
    else:
        if not record.get("full_manifest_sha256"):
            errors.append("r2_full_manifest_binding_missing")
        counts = record.get("full_manifest_counts")
        if not isinstance(counts, dict) or counts.get("completed_canonical_count") != counts.get("canonical_item_count"):
            errors.append("r2_full_manifest_coverage_incomplete")
    return sorted(set(errors))


__all__ = [
    "assessment_sha256", "artifact_registry_sha256", "baseline_proof_errors",
    "closed_recovery_errors", "component_graph_sha256",
    "establish_workspace_baseline", "inventory_policy_sha256",
    "make_baseline_meta", "manifest_sha256", "recovery_assessment",
    "required_recovery_reads", "root_fingerprint", "validate_read_receipts",
]
