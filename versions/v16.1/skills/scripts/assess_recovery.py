#!/usr/bin/env python3
"""Classify V16 recovery from full-workspace, baseline, and closure proofs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from lib_v10 import (
    ContractError,
    build_workspace_manifest,
    json_output,
    relative_safe,
    sha256_file,
    sha256_text,
)
from recovery_v16 import (
    artifact_registry_sha256,
    baseline_proof_errors,
    component_graph_sha256,
    inventory_policy_sha256,
    make_baseline_meta,
    manifest_sha256,
    root_fingerprint,
)
from state_v11 import (
    PROTECTED_IDENTITY_CLASSES,
    artifact_is_current_formal,
    load_state,
    transitive_consumers,
    validate_state_semantics,
)


GATES = {"G1", "G2", "G3"}
IMPORTANT_PREFIXES = (
    "data/", "src/", "docs/", "planning/", "results/", "result/",
    "output/", "outputs/", "paper/", "manuscript/", "figures/", "reports/",
)
IMPORTANT_ROOT_NAMES = {
    "paper.tex", "paper.md", "manuscript.tex", "manuscript.md",
    "report.tex", "report.md", "solution.md", "README.md",
}


def _stable_sha256(value: Any) -> str:
    return sha256_text(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ))


def build_workspace_baseline_meta(
    project_root: Path,
    state: dict[str, Any],
    baseline: dict[str, Any],
    established_by: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the metadata needed to treat a manifest as a trustworthy R1 base.

    The helper is public so the state manager and scenario fixtures can create
    byte-identical metadata instead of reimplementing the contract.
    """
    source = established_by or {
        "kind": "project_init",
        "id": str(state.get("project", {}).get("id", "unknown")),
    }
    source_id = source.get("source_id", source.get("id"))
    return make_baseline_meta(
        project_root.resolve(), state, baseline,
        captured_revision=int(state.get("revision", 0)),
        established_kind=str(source.get("kind", "project_init")),
        source_id=str(source_id) if source_id is not None else None,
    )


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
    """Return a path-level delta between two canonical workspace manifests."""
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


def _workspace_inventory(
    project_root: Path, state: dict[str, Any] | None
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    # Recovery classification is a project-root boundary.  Historical
    # ``watch_roots`` and caller scopes describe an older/targeted baseline;
    # neither is allowed to hide a live delta from R0/R1 qualification or to
    # shrink an explicit R2 full read.
    roots = ["."]
    errors: list[str] = []
    try:
        manifest = build_workspace_manifest(project_root.resolve(), roots)
    except (ContractError, OSError, ValueError) as exc:
        errors.append("workspace_inventory_failed:" + str(exc))
        manifest = {}
    required_paths = sorted(manifest)
    if (project_root / ".modeling/state.json").is_file():
        required_paths = sorted(set(required_paths) | {".modeling/state.json"})
    return manifest, required_paths, errors


def _baseline_proof(
    project_root: Path,
    state: dict[str, Any],
    baseline: Any,
    meta: Any,
) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(baseline, dict):
        errors.append("baseline_missing")
        baseline = {}
    if not isinstance(meta, dict):
        errors.append("baseline_metadata_missing")
        meta = {}
    if isinstance(baseline, dict) and isinstance(meta, dict):
        errors.extend(baseline_proof_errors(project_root, state))
    coverage_roots = meta.get("coverage_roots")
    return {
        "valid": not errors,
        "status": "trusted" if not errors else "untrusted",
        "errors": sorted(set(errors)),
        "manifest_sha256": manifest_sha256(baseline),
        "component_graph_sha256": component_graph_sha256(state),
        "artifact_registry_sha256": artifact_registry_sha256(state),
        "inventory_policy_sha256": inventory_policy_sha256(),
        "root_fingerprint": root_fingerprint(project_root, state),
        "coverage_roots": coverage_roots if isinstance(coverage_roots, list) else [],
    }


def _evidence_paths(state: dict[str, Any]) -> set[str]:
    paths: set[str] = set()
    for component in state.get("components", {}).values():
        if not isinstance(component, dict):
            continue
        for record in component.get("evidence", []):
            if not isinstance(record, dict):
                continue
            locator = record.get("locator", {})
            if not isinstance(locator, dict):
                continue
            for field in ("path", "output_ref"):
                value = locator.get(field)
                if isinstance(value, str) and value:
                    paths.add(value)
    return paths


def _is_recovery_relevant_path(
    path: str,
    kind: str,
    state: dict[str, Any],
    declared_paths: set[str],
    evidence_paths: set[str],
) -> bool:
    artifact = state.get("artifacts", {}).get(path)
    if isinstance(artifact, dict):
        if artifact_is_current_formal(artifact):
            return True
        if artifact.get("role") in {"official_input", "delivery", "planning"}:
            return True
    if path in declared_paths or path in evidence_paths:
        return True
    if path in IMPORTANT_ROOT_NAMES or path.startswith(IMPORTANT_PREFIXES):
        return True
    # A file that disappeared or changed after being part of the trusted
    # snapshot cannot be dismissed as a harmless newly-created scratch file.
    return kind in {"deleted", "modified"}


def _closed_execution_provenance(
    state: dict[str, Any], path: str, baseline_captured_revision: int | None
) -> tuple[list[str], list[dict[str, str]]]:
    components: set[str] = set()
    provenance: list[dict[str, str]] = []
    for execution_id, execution in sorted(state.get("executions", {}).items()):
        if not isinstance(execution, dict) or execution.get("status") != "closed":
            continue
        end_revision = execution.get("end_revision")
        observed_paths = execution.get("observed_changed_paths", [])
        if not (
            isinstance(baseline_captured_revision, int)
            and isinstance(end_revision, int)
            and end_revision > baseline_captured_revision
            and isinstance(observed_paths, list)
            and path in observed_paths
            and execution.get("change_set_provenance_complete") is True
            and isinstance(execution.get("execution_receipt_sha256"), str)
        ):
            continue
        components.update(
            item for item in execution.get("component_ids", []) if isinstance(item, str)
        )
        compatible = execution.get("compatible_change")
        if isinstance(compatible, dict):
            source = compatible.get("source_component_id")
            if isinstance(source, str):
                components.add(source)
        provenance.append({"kind": "closed_execution", "id": str(execution_id)})
    return sorted(components), provenance


def _matching_open_execution(
    state: dict[str, Any], continuity: dict[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    """Return only the exact plan/baseline/recovery-bound live execution."""
    meta = state.get("workspace_baseline_meta")
    established_by = meta.get("established_by", {}) if isinstance(meta, dict) else {}
    execution_id = (
        established_by.get("source_id") if isinstance(established_by, dict) else None
    )
    execution = (
        state.get("executions", {}).get(execution_id)
        if isinstance(execution_id, str) else None
    )
    if not (
        isinstance(meta, dict)
        and isinstance(established_by, dict)
        and established_by.get("kind") == "formal_execution_start"
        and isinstance(execution, dict)
        and execution.get("status") == "open"
        and execution.get("plan_hash") == continuity.get("plan_hash")
        and execution.get("request_hash") == continuity.get("request_hash")
        and set(execution.get("step_ids", [])).issubset(
            set(continuity.get("plan_step_ids", []))
        )
        and execution.get("workspace_manifest_before_sha256")
        == meta.get("manifest_sha256")
    ):
        return None
    recovery_id = execution.get("recovery_run_id")
    recovery = state.get("recoveries", {}).get(recovery_id)
    r0_execution = (
        execution.get("recovery") == "R0_CONTINUE"
        and recovery_id is None
        and isinstance(execution.get("recovery_decision_id"), str)
    )
    receipt_bound_execution = (
        isinstance(recovery_id, str)
        and isinstance(recovery, dict)
        and recovery.get("status") == "closed"
        and recovery.get("outcome") == "ready"
        and recovery.get("consumed_by_execution") == execution_id
        and recovery.get("plan_hash") == execution.get("plan_hash")
        and recovery.get("request_hash") == execution.get("request_hash")
        and recovery.get("step_id") in execution.get("step_ids", [])
        and recovery.get("recovery_level") == execution.get("recovery")
        and recovery.get("decision_id") == execution.get("recovery_decision_id")
        and isinstance(recovery.get("recovery_receipt_sha256"), str)
        and recovery.get("reviewed_manifest_sha256")
        == execution.get("workspace_manifest_before_sha256")
    )
    if not (r0_execution or receipt_bound_execution):
        return None
    return execution_id, execution


def _open_execution_provenance(
    state: dict[str, Any],
    path: str,
    matched: tuple[str, dict[str, Any]] | None,
) -> tuple[list[str], list[dict[str, str]]]:
    """Recognize a path owned by the exact execution now in progress."""
    if matched is None:
        return [], []
    execution_id, execution = matched
    declared_paths = execution.get("change_set", {}).get("paths", [])
    if path not in declared_paths:
        return [], []
    components = {
        item for item in execution.get("component_ids", [])
        if isinstance(item, str) and item in state.get("components", {})
    }
    compatible = execution.get("compatible_change")
    if isinstance(compatible, dict):
        source = compatible.get("source_component_id")
        if isinstance(source, str) and source in state.get("components", {}):
            components.add(source)
    return sorted(components), [{"kind": "open_execution_changeset", "id": execution_id}]


def _attribute_changes(
    state: dict[str, Any],
    workspace_diff: dict[str, list[str]],
    identity_associations: dict[str, list[str]],
    continuity: dict[str, Any] | None,
    baseline_captured_revision: int | None,
) -> tuple[dict[str, dict[str, Any]], list[str], list[str], list[str]]:
    continuity = continuity if isinstance(continuity, dict) else {}
    declared_paths = {
        item for item in continuity.get("declared_paths", []) if isinstance(item, str)
    }
    path_components = continuity.get("path_components", {})
    if not isinstance(path_components, dict):
        path_components = {}
    attributed: dict[str, dict[str, Any]] = {}
    unowned: list[str] = []
    ignored: list[str] = []
    relevant: list[str] = []
    exact_open_execution = _matching_open_execution(state, continuity)
    evidence_paths = _evidence_paths(state)
    for kind in ("added", "deleted", "modified"):
        for path in workspace_diff.get(kind, []):
            if (
                exact_open_execution is None
                and not _is_recovery_relevant_path(
                    path, kind, state, declared_paths, evidence_paths
                )
            ):
                ignored.append(path)
                continue
            relevant.append(path)
            component_ids, provenance = _closed_execution_provenance(
                state, path, baseline_captured_revision
            )
            open_components, open_provenance = _open_execution_provenance(
                state, path, exact_open_execution
            )
            component_ids.extend(open_components)
            provenance.extend(open_provenance)
            if continuity.get("same_window") is True and path in declared_paths:
                declared_components = path_components.get(path, [])
                component_ids.extend(
                    item for item in declared_components if isinstance(item, str)
                )
                provenance.append({
                    "kind": "current_plan_changeset",
                    "id": str(continuity.get("plan_id") or "current_plan"),
                })
            component_ids.extend(identity_associations.get(path, []))
            component_ids = sorted(set(
                item for item in component_ids if item in state.get("components", {})
            ))
            if not provenance:
                unowned.append(path)
                continue
            attributed[path] = {
                "kind": kind,
                "component_ids": component_ids,
                "provenance": provenance,
            }
    return attributed, sorted(set(unowned)), sorted(set(ignored)), sorted(set(relevant))


def _closure_proof(
    state: dict[str, Any],
    attributed: dict[str, dict[str, Any]],
    relevant_changes: list[str],
    unowned_changes: list[str],
    continuity: dict[str, Any] | None,
) -> dict[str, Any]:
    seeds = {
        component_id
        for item in attributed.values()
        for component_id in item.get("component_ids", [])
        if component_id in state.get("components", {})
    }
    affected = transitive_consumers(state.get("components", {}), seeds)
    paths_without_components = sorted(
        path for path, item in attributed.items() if not item.get("component_ids")
    )
    context = continuity if isinstance(continuity, dict) else {}
    errors: list[str] = []
    if unowned_changes:
        errors.append("unowned_relevant_changes")
    if paths_without_components:
        errors.append("changed_paths_without_component_owner")
    if context.get("require_declared_closure") is True:
        allowed = {
            item for item in context.get("declared_component_ids", [])
            if isinstance(item, str)
        }
        outside = sorted(set(affected) - allowed)
        if outside:
            errors.append("affected_components_outside_declared_closure:" + ",".join(outside))
    if relevant_changes and not attributed:
        errors.append("relevant_change_attribution_empty")
    return {
        "complete": not errors,
        "errors": sorted(set(errors)),
        "seed_components": sorted(seeds),
        "affected_components": affected,
        "paths_without_components": paths_without_components,
        "graph_sha256": component_graph_sha256(state),
    }


def _decision_id(payload: dict[str, Any]) -> str:
    stable = {
        key: value for key, value in payload.items()
        if key not in {"decision_id", "state_revision"}
    }
    return _stable_sha256(stable)


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
    continuity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify one project recovery decision from machine-checkable proofs.

    ``new_window`` encodes V8's same-uninterrupted-session boundary: a fresh
    window/context must never classify a consistent state as R0.  The caller
    derives it from the semantic plan's ``window_context``; unknown/missing
    plans are treated as new window by the policy.  ``scope_paths`` remains a
    compatibility argument for callers that derive an R1 read set; it never
    narrows classification and therefore cannot hide a global identity change.
    """
    if gate not in GATES:
        raise ContractError(f"unknown gate: {gate}")
    project_root = project_root.resolve()
    state, load_errors = load_state(project_root)
    current_workspace, required_paths, inventory_errors = _workspace_inventory(
        project_root, state
    )
    full_inventory = {
        "paths": sorted(current_workspace),
        "file_count": len(current_workspace),
        "manifest_sha256": manifest_sha256(current_workspace),
        "coverage_roots": ["."],
    }

    def finish(payload: dict[str, Any]) -> dict[str, Any]:
        payload.setdefault("schema_version", "11.0")
        payload.setdefault("gate", gate)
        payload.setdefault("full_inventory", full_inventory)
        payload.setdefault("required_paths", required_paths)
        closure_proof = payload.get("closure_proof", {})
        payload.setdefault(
            "closure_complete",
            bool(isinstance(closure_proof, dict) and closure_proof.get("complete") is True),
        )
        payload.setdefault("execution_boundary", recovery_execution_boundary(
            str(payload.get("level"))
        ))
        payload["decision_id"] = _decision_id(payload)
        return payload

    if state is None:
        reasons = (["explicit_full_recovery"] if explicit_full else []) + [
            "state_missing_or_unreadable", *load_errors, *inventory_errors,
        ]
        return finish({
            "level": "R2_FULL", "state_valid": False,
            "reasons": sorted(set(reasons)), "changed_paths": [],
            "owned_changes": {}, "attributed_changes": {},
            "unowned_changes": [], "ignored_changes": [],
            "affected_components": [],
            "baseline_status": "missing",
            "baseline_proof": {"valid": False, "status": "missing", "errors": ["baseline_missing"]},
            "closure_proof": {"complete": False, "errors": ["authoritative_state_unavailable"]},
            "required_scope": "full_project_inventory_and_semantic_read_without_implicit_recomputation",
            "state_format": "missing_or_unreadable",
        })
    structural_errors = sorted(set(
        load_errors + validate_state_semantics(state, project_root, check_files=False)
    ))
    if structural_errors:
        reasons = (["explicit_full_recovery"] if explicit_full else []) + [
            "state_or_identity_invalid", *structural_errors, *inventory_errors,
        ]
        return finish({
            "level": "R2_FULL", "state_valid": False,
            "state_revision": state.get("revision"),
            "reasons": sorted(set(reasons)), "changed_paths": [],
            "owned_changes": {}, "attributed_changes": {},
            "unowned_changes": [], "ignored_changes": [],
            "affected_components": [],
            "baseline_status": "invalid_state",
            "baseline_proof": {"valid": False, "status": "untrusted", "errors": ["state_invalid"]},
            "closure_proof": {"complete": False, "errors": ["authoritative_state_invalid"]},
            "required_scope": "full_project_inventory_and_semantic_read_without_implicit_recomputation",
            "state_format": (
                "legacy_or_incompatible" if state.get("schema_version") != "11.0"
                or not isinstance(state.get("components"), dict)
                or not isinstance(state.get("artifacts"), dict)
                else "invalid_v11"
            ),
        })

    # Classification is deliberately global.  ``scope_paths`` may later reduce
    # the R1 read set, but it cannot suppress a changed protected identity here.
    protected_changes, identity_associations, identity_errors = _protected_identity_changes(
        project_root, state, None
    )
    if identity_errors:
        reasons = (["explicit_full_recovery"] if explicit_full else []) + [
            "state_or_identity_invalid", *identity_errors,
        ]
        return finish({
            "level": "R2_FULL", "state_valid": False,
            "state_revision": state["revision"],
            "reasons": sorted(set(reasons)), "changed_paths": protected_changes,
            "owned_changes": identity_associations, "attributed_changes": {},
            "unowned_changes": protected_changes, "ignored_changes": [],
            "affected_components": sorted(state["components"]),
            "baseline_status": "identity_conflict",
            "baseline_proof": {"valid": False, "status": "untrusted", "errors": ["identity_registry_invalid"]},
            "closure_proof": {"complete": False, "errors": ["identity_registry_invalid"]},
            "required_scope": "full_project_inventory_and_semantic_read_without_implicit_recomputation",
            "state_format": "invalid_v11_identity_registry",
        })

    baseline = state.get("workspace_baseline")
    baseline_meta = state.get("workspace_baseline_meta")
    baseline_proof = _baseline_proof(project_root, state, baseline, baseline_meta)
    workspace_diff = (
        manifest_diff(baseline, current_workspace)
        if isinstance(baseline, dict) and not inventory_errors else
        {"added": [], "deleted": [], "modified": []}
    )
    for path in protected_changes:
        if not any(path in workspace_diff[kind] for kind in workspace_diff):
            kind = "modified" if path in current_workspace else "deleted"
            workspace_diff[kind].append(path)
    workspace_diff = {
        kind: sorted(set(paths)) for kind, paths in workspace_diff.items()
    }

    continuity_context = dict(continuity) if isinstance(continuity, dict) else {}
    continuity_context.setdefault("same_window", not new_window)
    attributed, unowned, ignored, relevant = _attribute_changes(
        state, workspace_diff, identity_associations, continuity_context,
        (
            baseline_meta.get("captured_revision")
            if isinstance(baseline_meta, dict)
            and isinstance(baseline_meta.get("captured_revision"), int)
            else None
        ),
    )
    closure = _closure_proof(
        state, attributed, relevant, unowned, continuity_context
    )
    affected = closure["affected_components"]
    workspace_changed_paths = sorted(set(
        workspace_diff.get("added", [])
        + workspace_diff.get("deleted", [])
        + workspace_diff.get("modified", [])
    ))
    all_changed_paths = sorted(set(protected_changes) | set(workspace_changed_paths))

    current_plan_attributed = all(
        any(item.get("kind") == "current_plan_changeset" for item in proof.get("provenance", []))
        for path, proof in attributed.items() if path in relevant
    )
    open_execution_attributed = all(
        any(
            item.get("kind") == "open_execution_changeset"
            for item in proof.get("provenance", [])
        )
        for path, proof in attributed.items() if path in relevant
    )
    continuity_complete = (
        not new_window
        and isinstance(baseline, dict)
        and (state.get("watch_roots") or ["."]) == ["."]
        and not inventory_errors
        and baseline_proof.get("valid") is True
        and not unowned
        and closure.get("complete") is True
        and (
            not relevant
            or (
                open_execution_attributed
                or (
                    current_plan_attributed
                    and continuity_context.get("change_set_complete", False) is True
                    and continuity_context.get(
                        "propagation_complete",
                        continuity_context.get("invalidation_propagated", False),
                    ) is True
                )
            )
        )
    )
    r1_proofs_complete = (
        baseline_proof.get("valid") is True
        and not inventory_errors
        and not unowned
        and closure.get("complete") is True
        and set(relevant) == set(attributed)
    )

    if explicit_full:
        level = "R2_FULL"
        reasons = ["explicit_full_recovery"]
        required_scope = "full_project_inventory_and_semantic_read_without_implicit_recomputation"
        affected = sorted(state["components"])
    elif continuity_complete:
        level = "R0_CONTINUE"
        reasons = ["trusted_same_window_continuity"]
        required_scope = (
            "declared_release_identity_and_evidence_scope"
            if gate == "G3" else "next_legal_action"
        )
    elif r1_proofs_complete:
        level = "R1_TARGETED"
        reasons = ["r1_proofs_complete"]
        if protected_changes:
            reasons.append("protected_registered_identity_changed")
        if workspace_changed_paths:
            reasons.append("workspace_changes_detected")
        if new_window:
            reasons.append("new_window_requires_targeted_recovery")
        required_scope = "changed_identity_and_workspace_delta_and_true_downstream_consumers"
    else:
        level = "R2_FULL"
        reasons = []
        reasons.extend(baseline_proof.get("errors", []))
        reasons.extend(inventory_errors)
        if unowned:
            reasons.append("changes_not_attributable")
        if not closure.get("complete"):
            reasons.append("consumer_closure_unproven")
            reasons.extend(closure.get("errors", []))
        if new_window:
            reasons.append("new_window_r1_qualification_failed")
        elif not continuity_complete:
            reasons.append("same_window_continuity_unproven")
        reasons = sorted(set(reasons or ["r1_qualification_unproven"]))
        required_scope = "full_project_inventory_and_semantic_read_without_implicit_recomputation"
        affected = sorted(state["components"])
    working = sorted(
        rel for rel, artifact in state.get("artifacts", {}).items()
        if isinstance(artifact, dict)
        and artifact.get("identity_class") not in PROTECTED_IDENTITY_CLASSES
    )
    owned_changes = {
        path: item.get("component_ids", []) for path, item in attributed.items()
    }
    return finish({
        "level": level, "state_valid": True,
        "state_revision": state["revision"], "reasons": reasons,
        "changed_paths": all_changed_paths, "owned_changes": owned_changes,
        "attributed_changes": attributed,
        "unowned_changes": unowned,
        "ignored_changes": ignored,
        "affected_components": affected, "unmonitored_working_artifacts": working,
        "workspace_diff": workspace_diff,
        "workspace_baseline_missing": not isinstance(baseline, dict),
        "baseline_status": baseline_proof.get("status"),
        "baseline_proof": baseline_proof,
        "closure_proof": closure,
        "required_scope": required_scope,
        "state_format": "v11",
    })


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
