#!/usr/bin/env python3
"""V14 targeted-recovery read set and receipt bindings.

R1 is a scoped semantic context reconstruction, not a hash-only label.  This
module derives the important files that must be read, validates one accountable
receipt, and binds the reviewed snapshot to later checkpoint execution.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lib_v10 import (
    ContractError, build_workspace_manifest, relative_safe, sha256_file,
    sha256_text,
)
from lib_v11 import canonical_json
from state_v11 import artifact_is_current_formal


SEMANTIC_READ_MODES = {"content", "structured_extract", "visual_review"}


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return sha256_text(canonical_json(manifest))


def window_context(plan: dict[str, Any]) -> str:
    value = plan.get("window_context", "new_window")
    return value if value in {"same_window", "new_window", "unknown"} else "unknown"


def recovery_level(step: dict[str, Any]) -> str | None:
    value = step.get("recovery")
    return value.get("level") if isinstance(value, dict) else None


def recovery_assessment(step: dict[str, Any]) -> dict[str, Any]:
    value = step.get("recovery")
    if not isinstance(value, dict):
        raise ContractError("formal project execution requires recovery_assessment in its semantic step")
    level = value.get("level")
    if level not in {"R0_CONTINUE", "R1_TARGETED", "R2_FULL"}:
        raise ContractError("semantic recovery assessment has an unknown level")
    return value


def _component_dependency_closure(
    state: dict[str, Any], component_ids: set[str]
) -> set[str]:
    components = state.get("components", {})
    closure = set(component_ids)
    pending = list(component_ids)
    while pending:
        component_id = pending.pop()
        component = components.get(component_id, {})
        dependencies = component.get("dependencies", []) if isinstance(component, dict) else []
        for dependency in dependencies if isinstance(dependencies, list) else []:
            if isinstance(dependency, str) and dependency in components and dependency not in closure:
                closure.add(dependency)
                pending.append(dependency)
    return closure


def _owners(artifact: dict[str, Any]) -> set[str]:
    consumers = artifact.get("consumers", [])
    return {
        item for item in [artifact.get("producer"), *(consumers if isinstance(consumers, list) else [])]
        if isinstance(item, str)
    }


def required_recovery_reads(
    project_root: Path,
    state: dict[str, Any],
    step: dict[str, Any],
    assessment: dict[str, Any],
) -> list[dict[str, Any]]:
    """Derive the minimum R1 semantic read set for one resolved step.

    The authoritative state and official inputs are always semantic reads.
    Frozen planning/process records are semantic reads when they belong to the
    target, an upstream dependency, or an affected component.  Other formal
    identities in the exact step scope remain identity reads.  Workspace deltas
    are reviewed semantically so a baseline cannot swallow unseen changes.
    """
    from assess_recovery import scope_paths_for_step

    root = project_root.resolve()
    artifacts = state.get("artifacts", {})
    targets = {
        item for item in step.get("component_ids", []) if isinstance(item, str)
    }
    if (
        not targets
        and step.get("object") in {"project", "delivery"}
        and step.get("action") != "pause"
    ):
        targets.update(
            item for item in state.get("project", {}).get("required_components", [])
            if isinstance(item, str)
        )
    targets.update(
        item for item in assessment.get("affected_components", []) if isinstance(item, str)
    )
    relevant_components = _component_dependency_closure(state, targets)
    formal_scope = set(scope_paths_for_step(state, step))
    changed_paths = {
        item for item in assessment.get("changed_paths", []) if isinstance(item, str)
    }
    requirements: dict[str, dict[str, Any]] = {}

    def add(path: str, semantic_role: str, required_mode: str) -> None:
        current = requirements.get(path)
        rank = {"existence": 0, "identity": 1, "semantic": 2, "content": 3}
        if current is not None and rank[current["required_mode"]] >= rank[required_mode]:
            return
        expected_hash: str | None = None
        expected_size: int | None = None
        if path != ".modeling/state.json":
            try:
                live, normalized = relative_safe(root, path)
            except ContractError:
                live, normalized = root / "__invalid__", path
            if normalized == path and live.is_file():
                expected_hash = sha256_file(live)
                expected_size = live.stat().st_size
            elif required_mode != "existence":
                required_mode = "existence"
        requirements[path] = {
            "path": path,
            "semantic_role": semantic_role,
            "required_mode": required_mode,
            "expected_sha256": expected_hash,
            "expected_size": expected_size,
        }

    add(".modeling/state.json", "authoritative_state", "content")

    for path, artifact in sorted(artifacts.items()):
        if not isinstance(path, str) or not isinstance(artifact, dict):
            continue
        if not artifact_is_current_formal(artifact):
            continue
        role = artifact.get("role")
        if role == "official_input":
            add(path, "official_input", "semantic")
            continue
        if (
            role == "planning"
            and artifact.get("identity_class") in {"milestone", "frozen", "final"}
            and bool(_owners(artifact) & relevant_components)
        ):
            add(path, "frozen_process", "semantic")
            continue
        if path in formal_scope:
            add(path, "formal_identity", "identity")

    # Canonical data/ files are official inputs even before formal registration.
    # This prevents a fresh window from recovering only the registry while never
    # reading the original statement or its official attachments.
    current_manifest = build_workspace_manifest(root, state.get("watch_roots") or ["."])
    for path in sorted(current_manifest):
        if path.startswith("data/") and path not in artifacts:
            add(path, "unregistered_official_input", "semantic")

    components = state.get("components", {})
    for component_id in sorted(relevant_components):
        component = components.get(component_id, {})
        evidence_records = (
            component.get("evidence", []) if isinstance(component, dict) else []
        )
        for evidence in evidence_records if isinstance(evidence_records, list) else []:
            if not isinstance(evidence, dict) or evidence.get("status") != "pass":
                continue
            locator = evidence.get("locator", {})
            if evidence.get("kind") == "file" and isinstance(locator, dict):
                evidence_path = locator.get("path")
                if isinstance(evidence_path, str) and evidence_path:
                    add(evidence_path, "evidence_source", "semantic")

    for path in sorted(changed_paths):
        add(path, "workspace_delta", "semantic")

    return [requirements[path] for path in sorted(requirements)]


def assessment_sha256(assessment: dict[str, Any]) -> str:
    stable = {
        key: value for key, value in assessment.items()
        if key not in {"state_revision"}
    }
    return sha256_text(canonical_json(stable))


def validate_read_receipts(
    project_root: Path,
    required_reads: list[dict[str, Any]],
    receipts: Any,
    *,
    verify_dynamic_state_file: bool = True,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipts, list):
        return ["recovery_read_receipts_not_array"]
    by_path: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(receipts):
        if not isinstance(item, dict):
            errors.append(f"recovery_read_receipt_not_object:{index}")
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            errors.append(f"recovery_read_receipt_path_invalid:{index}")
            continue
        if path in by_path:
            errors.append("recovery_read_receipt_duplicate:" + path)
        by_path[path] = item
    required_by_path = {item["path"]: item for item in required_reads}
    missing = sorted(set(required_by_path) - set(by_path))
    extra = sorted(set(by_path) - set(required_by_path))
    if missing:
        errors.append("recovery_required_read_missing:" + ",".join(missing))
    if extra:
        errors.append("recovery_undeclared_read_receipt:" + ",".join(extra))

    root = project_root.resolve()
    for path in sorted(set(required_by_path) & set(by_path)):
        required = required_by_path[path]
        item = by_path[path]
        if item.get("semantic_role") != required.get("semantic_role"):
            errors.append("recovery_read_role_mismatch:" + path)
        mode = item.get("read_mode")
        requirement = required.get("required_mode")
        if requirement == "content" and mode != "content":
            errors.append("recovery_content_read_required:" + path)
        elif requirement == "semantic" and mode not in SEMANTIC_READ_MODES:
            errors.append("recovery_semantic_read_required:" + path)
        elif requirement == "identity" and mode not in {
            "identity_plus_validation_summary", *SEMANTIC_READ_MODES
        }:
            errors.append("recovery_identity_read_required:" + path)
        elif requirement == "existence" and mode != "missing_review":
            errors.append("recovery_missing_review_required:" + path)
        note = item.get("note")
        if not isinstance(note, str) or len(note.strip()) < 8:
            errors.append("recovery_read_note_too_short:" + path)
        review_result = item.get("review_result")
        if review_result not in {"consistent", "changed", "missing", "unreadable"}:
            errors.append("recovery_read_result_invalid:" + path)

        if path == ".modeling/state.json" and not verify_dynamic_state_file:
            continue
        live, normalized = relative_safe(root, path)
        if normalized != path:
            errors.append("recovery_read_path_not_normalized:" + path)
            continue
        if live.is_file():
            observed_hash = sha256_file(live)
            observed_size = live.stat().st_size
            if item.get("sha256") != observed_hash:
                errors.append("recovery_read_hash_mismatch:" + path)
            if item.get("size") != observed_size:
                errors.append("recovery_read_size_mismatch:" + path)
            expected_hash = required.get("expected_sha256")
            if expected_hash is not None and expected_hash != observed_hash:
                errors.append("recovery_required_file_changed_during_review:" + path)
        else:
            if item.get("sha256") is not None or item.get("size") is not None:
                errors.append("recovery_missing_file_identity_present:" + path)
            if mode != "missing_review":
                errors.append("recovery_missing_file_not_reviewed:" + path)
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
    """Validate that one closed R1 run still binds the live project snapshot."""
    if not recovery_id:
        return ["r1_closed_recovery_id_required"]
    record = state.get("recoveries", {}).get(recovery_id)
    if not isinstance(record, dict):
        return ["r1_recovery_not_registered"]
    errors: list[str] = []
    if record.get("status") != "closed" or record.get("outcome") != "ready":
        errors.append("r1_recovery_not_closed_ready")
    expected_window = step.get("facts", {}).get("window_context")
    for field, expected in (
        ("plan_hash", resolution.get("plan_hash")),
        ("request_hash", resolution.get("request_hash")),
        ("step_id", step.get("id")),
        ("window_context", expected_window),
        ("recovery_level", "R1_TARGETED"),
    ):
        if record.get(field) != expected:
            errors.append("r1_recovery_binding_mismatch:" + field)
    if record.get("component_ids") != sorted(step.get("component_ids", [])):
        errors.append("r1_recovery_binding_mismatch:component_ids")
    if record.get("consumed_by_execution") is not None:
        errors.append("r1_recovery_already_consumed")
    allowed_revisions = {record.get("end_revision"), record.get("baseline_revision")}
    if allow_checkpoint_revision:
        allowed_revisions.add(record.get("checkpoint_revision"))
    if state.get("revision") not in {item for item in allowed_revisions if isinstance(item, int)}:
        errors.append("r1_recovery_state_revision_advanced")
    current_manifest = build_workspace_manifest(
        project_root.resolve(), state.get("watch_roots") or ["."]
    )
    if manifest_sha256(current_manifest) != record.get("reviewed_manifest_sha256"):
        errors.append("r1_recovery_workspace_changed_after_review")
    errors.extend(validate_read_receipts(
        project_root, record.get("required_reads", []), record.get("read_receipts", []),
        verify_dynamic_state_file=False,
    ))
    return sorted(set(errors))
