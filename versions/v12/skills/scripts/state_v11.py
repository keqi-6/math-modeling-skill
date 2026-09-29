#!/usr/bin/env python3
"""Shared V11 state, evidence, artifact, and invalidation semantics.

V11 deliberately separates two concerns that V10 coupled together:

* a workspace/file change is an observation;
* an evidence or component invalidation is a semantic consequence.

Only exact evidence references and protected identities create the latter.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from lib_v10 import (
    ContractError,
    Draft202012Validator,
    EVIDENCE_LEVELS,
    FormatChecker,
    SKILL_ROOT,
    STATE_REL,
    STRONG_EVIDENCE_KINDS,
    load_json,
    relative_safe,
    sha256_file,
    sha256_text,
    valid_iso_datetime,
)


STATE_SCHEMA_VERSION = "11.0"
PROTECTED_IDENTITY_CLASSES = {"milestone", "frozen", "final"}
INPUT_REF_KINDS = {"artifact", "claim", "decision", "run", "spec", "external"}
INPUT_REF_FACETS = {
    "content", "interface", "frozen_input", "result", "claim", "render",
    "format", "metadata", "decision", "run", "specification", "source",
}


def _is_hex(value: Any, length: int = 64) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and re.fullmatch(r"[0-9a-f]+", value) is not None
    )


def canonical_input_refs(input_refs: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Return a stable, duplicate-free representation of exact input refs."""
    normalized = {
        (
            str(item.get("kind", "")), str(item.get("id", "")),
            str(item.get("identity", "")), str(item.get("facet", "")),
        )
        for item in input_refs
        if isinstance(item, dict)
    }
    return [
        {"kind": kind, "id": identifier, "identity": identity, "facet": facet}
        for kind, identifier, identity, facet in sorted(normalized)
    ]


def evidence_binding_hash(
    component_id: str,
    level: str,
    input_refs: Iterable[dict[str, Any]],
    claim_refs: Iterable[str],
) -> str:
    """Bind one evidence record only to the identities and claims it uses."""
    payload = {
        "component_id": component_id,
        "level": level,
        "input_refs": canonical_input_refs(input_refs),
        "claim_refs": sorted(set(str(item) for item in claim_refs)),
    }
    return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def artifact_is_protected(artifact: dict[str, Any]) -> bool:
    """Protected identities may invalidate components; working identities may not."""
    return artifact.get("identity_class") in PROTECTED_IDENTITY_CLASSES


def artifact_is_current_formal(artifact: dict[str, Any]) -> bool:
    """Return whether an identity is both protected and still authoritative."""
    return artifact_is_protected(artifact) and artifact.get("status") != "superseded"


def transitive_consumers(components: dict[str, Any], seeds: Iterable[str]) -> list[str]:
    """Walk only the declared upstream -> downstream consumer direction."""
    queue = [item for item in seeds if item in components]
    seen = set(queue)
    while queue:
        current = queue.pop(0)
        for consumer in components.get(current, {}).get("consumers", []):
            if consumer in components and consumer not in seen:
                seen.add(consumer)
                queue.append(consumer)
    return sorted(seen)


def _locator_errors(
    evidence: dict[str, Any], project_root: Path | None, check_files: bool
) -> list[str]:
    errors: list[str] = []
    kind = evidence.get("kind")
    locator = evidence.get("locator")
    if not isinstance(locator, dict):
        return ["evidence_locator_not_object"]
    expected_keys = {
        "file": {"path", "sha256"},
        "command": {"command_hash", "exit_code", "output_ref", "output_sha256"},
        "citation": {"uri", "accessed_at"},
        "observation": {"subject", "method", "value"},
        "decision": {"decision_id", "recorded_at"},
    }.get(kind)
    if expected_keys is None:
        return ["evidence_bad_kind"]
    if set(locator) != expected_keys:
        return ["evidence_locator_shape"]
    if kind == "file":
        if not _is_hex(locator.get("sha256")):
            errors.append("evidence_bad_sha256")
        if project_root is not None and check_files and evidence.get("status") == "pass":
            try:
                path, _ = relative_safe(project_root, locator.get("path", ""))
                if not path.is_file():
                    errors.append("evidence_file_missing")
                elif sha256_file(path) != locator.get("sha256"):
                    errors.append("evidence_file_hash_mismatch")
            except (ContractError, TypeError) as exc:
                errors.append(str(exc))
    elif kind == "command":
        if (
            not _is_hex(locator.get("command_hash"))
            or not isinstance(locator.get("exit_code"), int)
            or not _is_hex(locator.get("output_sha256"))
        ):
            errors.append("evidence_command_identity_invalid")
        if evidence.get("status") == "pass" and locator.get("exit_code") != 0:
            errors.append("evidence_passing_command_nonzero_exit")
        if project_root is not None and check_files and evidence.get("status") == "pass":
            try:
                output, _ = relative_safe(project_root, locator.get("output_ref", ""))
                if not output.is_file():
                    errors.append("evidence_command_output_missing")
                elif sha256_file(output) != locator.get("output_sha256"):
                    errors.append("evidence_command_output_hash_mismatch")
            except (ContractError, TypeError) as exc:
                errors.append(str(exc))
    elif kind == "citation":
        if not re.match(r"^https?://", str(locator.get("uri", ""))):
            errors.append("evidence_citation_uri_invalid")
        if not valid_iso_datetime(locator.get("accessed_at")):
            errors.append("evidence_citation_time_invalid")
    elif kind == "observation":
        if not locator.get("subject") or not locator.get("method"):
            errors.append("evidence_observation_invalid")
    elif kind == "decision":
        if not locator.get("decision_id") or not valid_iso_datetime(locator.get("recorded_at")):
            errors.append("evidence_decision_invalid")
    return errors


def validate_evidence(
    evidence: Any,
    project_root: Path | None,
    check_files: bool,
    *,
    state: dict[str, Any] | None = None,
    component_id: str | None = None,
    stored: bool = False,
) -> list[str]:
    """Validate a typed record without coupling it to a component-wide hash."""
    if not isinstance(evidence, dict):
        return ["evidence_not_object"]
    required = {
        "id", "level", "status", "kind", "locator", "claim", "observed_at",
        "producer", "subject_id", "input_refs", "claim_refs", "binding_hash",
    }
    if stored:
        required.add("recorded_revision")
    missing = required - evidence.keys()
    if missing:
        return ["evidence_missing:" + ",".join(sorted(missing))]
    allowed = required | {"subject_hash"}
    errors: list[str] = []
    extra = set(evidence) - allowed
    if extra:
        errors.append("evidence_extra:" + ",".join(sorted(extra)))
    if not isinstance(evidence.get("id"), str) or not evidence["id"].strip():
        errors.append("evidence_id_invalid")
    if evidence.get("level") not in EVIDENCE_LEVELS:
        errors.append("evidence_bad_level")
    if evidence.get("status") not in {"pass", "fail", "not_applicable", "stale"}:
        errors.append("evidence_bad_status")
    if evidence.get("kind") not in {"file", "command", "citation", "observation", "decision"}:
        errors.append("evidence_bad_kind")
    allowed_kinds = STRONG_EVIDENCE_KINDS.get(evidence.get("level"))
    if (
        evidence.get("status") == "pass"
        and allowed_kinds is not None
        and evidence.get("kind") not in allowed_kinds
    ):
        errors.append("evidence_kind_too_weak_for_level")
    errors.extend(_locator_errors(evidence, project_root, check_files))
    if evidence.get("kind") == "decision" and state is not None:
        decision_id = evidence.get("locator", {}).get("decision_id")
        decision = next(
            (
                item for item in state.get("open_decisions", [])
                if isinstance(item, dict) and item.get("id") == decision_id
            ),
            None,
        )
        if decision is None or decision.get("status") != "resolved":
            errors.append("evidence_decision_not_resolved_in_state")
    if not isinstance(evidence.get("claim"), str) or len(evidence["claim"].strip()) < 3:
        errors.append("evidence_claim_invalid")
    if not valid_iso_datetime(evidence.get("observed_at")):
        errors.append("evidence_observed_at_invalid")
    if not isinstance(evidence.get("producer"), str) or not evidence["producer"].strip():
        errors.append("evidence_producer_invalid")
    if not isinstance(evidence.get("subject_id"), str) or not evidence["subject_id"].strip():
        errors.append("evidence_subject_id_invalid")
    if component_id is not None and evidence.get("subject_id") != component_id:
        errors.append("evidence_subject_mismatch")
    if "subject_hash" in evidence and not _is_hex(evidence.get("subject_hash")):
        errors.append("evidence_legacy_subject_hash_invalid")

    refs = evidence.get("input_refs")
    if not isinstance(refs, list):
        errors.append("evidence_input_refs_invalid")
        refs = []
    elif canonical_input_refs(refs) != refs:
        errors.append("evidence_input_refs_not_canonical")
    for index, ref in enumerate(refs):
        if not isinstance(ref, dict) or set(ref) != {"kind", "id", "identity", "facet"}:
            errors.append(f"evidence_input_ref_shape:{index}")
            continue
        if ref.get("kind") not in INPUT_REF_KINDS:
            errors.append(f"evidence_input_ref_kind:{index}")
        if not isinstance(ref.get("id"), str) or not ref["id"].strip():
            errors.append(f"evidence_input_ref_id:{index}")
        if not _is_hex(ref.get("identity")):
            errors.append(f"evidence_input_ref_identity:{index}")
        if ref.get("facet") not in INPUT_REF_FACETS:
            errors.append(f"evidence_input_ref_facet:{index}")
        if state is not None and ref.get("kind") == "artifact" and evidence.get("status") == "pass":
            artifact_registry = state.get("artifacts", {})
            artifact = (
                artifact_registry.get(ref.get("id"))
                if isinstance(artifact_registry, dict) else None
            )
            if artifact is None:
                errors.append(f"evidence_input_artifact_missing:{index}")
            elif artifact.get("sha256") != ref.get("identity"):
                errors.append(f"evidence_input_artifact_stale:{index}")

    claim_refs = evidence.get("claim_refs")
    if (
        not isinstance(claim_refs, list)
        or any(not isinstance(item, str) or not item.strip() for item in claim_refs)
        or sorted(set(claim_refs or [])) != (claim_refs or [])
    ):
        errors.append("evidence_claim_refs_invalid")
        claim_refs = []
    expected_binding = evidence_binding_hash(
        str(evidence.get("subject_id", "")),
        str(evidence.get("level", "")),
        refs,
        claim_refs,
    )
    if evidence.get("binding_hash") != expected_binding:
        errors.append("evidence_binding_hash_stale")
    if stored and (
        not isinstance(evidence.get("recorded_revision"), int)
        or evidence["recorded_revision"] < 1
    ):
        errors.append("evidence_recorded_revision_invalid")
    return sorted(set(errors))


def evidence_references_artifact(evidence: dict[str, Any], path: str, identity: str) -> bool:
    """Match only an exact old artifact identity, never a component-wide snapshot."""
    if evidence_references_input(evidence, "artifact", path, identity):
        return True
    locator = evidence.get("locator", {})
    return bool(
        (evidence.get("kind") == "file" and locator.get("path") == path and locator.get("sha256") == identity)
        or (
            evidence.get("kind") == "command"
            and locator.get("output_ref") == path
            and locator.get("output_sha256") == identity
        )
    )


def evidence_references_input(
    evidence: dict[str, Any], kind: str, identifier: str, identity: str
) -> bool:
    """Match one exact typed input, including an exact claim version."""
    return any(
        ref.get("kind") == kind
        and ref.get("id") == identifier
        and ref.get("identity") == identity
        for ref in evidence.get("input_refs", [])
        if isinstance(ref, dict)
    )


def stale_exact_input_evidence(
    state: dict[str, Any], kind: str, identifier: str, old_identity: str
) -> tuple[list[str], list[str], list[str]]:
    """Stale passing records that name one exact typed input identity."""
    component_ids: set[str] = set()
    evidence_ids: set[str] = set()
    claim_ids: set[str] = set()
    for component_id, component in state.get("components", {}).items():
        if not isinstance(component, dict):
            continue
        for record in component.get("evidence", []):
            if (
                isinstance(record, dict)
                and record.get("status") == "pass"
                and evidence_references_input(
                    record, kind, identifier, old_identity
                )
            ):
                record["status"] = "stale"
                component_ids.add(component_id)
                evidence_ids.add(str(record.get("id", "")))
                claim_ids.update(
                    item for item in record.get("claim_refs", [])
                    if isinstance(item, str)
                )
    return sorted(component_ids), sorted(evidence_ids), sorted(claim_ids)


def stale_exact_artifact_evidence(
    state: dict[str, Any], path: str, old_identity: str
) -> tuple[list[str], list[str], list[str]]:
    """Stale only records that cite the exact old identity."""
    components, evidence, claims = stale_exact_input_evidence(
        state, "artifact", path, old_identity
    )
    component_ids = set(components)
    evidence_ids = set(evidence)
    claim_ids = set(claims)
    for component_id, component in state.get("components", {}).items():
        if not isinstance(component, dict):
            continue
        for record in component.get("evidence", []):
            if record.get("status") == "pass" and evidence_references_artifact(record, path, old_identity):
                record["status"] = "stale"
                component_ids.add(component_id)
                evidence_ids.add(str(record.get("id", "")))
                claim_ids.update(
                    item for item in record.get("claim_refs", [])
                    if isinstance(item, str)
                )
    return sorted(component_ids), sorted(evidence_ids), sorted(claim_ids)


def clear_invalid_artifact_validations(state: dict[str, Any]) -> list[str]:
    """Downgrade only artifacts whose named validation is no longer current."""
    evidence_by_id = {
        record.get("id"): record
        for component in state.get("components", {}).values()
        if isinstance(component, dict)
        for record in component.get("evidence", [])
        if isinstance(record, dict)
    }
    cleared: list[str] = []
    for path, artifact in state.get("artifacts", {}).items():
        if not isinstance(artifact, dict) or artifact.get("status") != "validated":
            continue
        validation = evidence_by_id.get(artifact.get("validation_evidence_id"))
        current = bool(
            validation is not None
            and validation.get("level") == "artifact_validation"
            and validation.get("status") == "pass"
            and evidence_references_artifact(
                validation, path, artifact.get("sha256", "")
            )
        )
        if not current:
            artifact["status"] = "registered"
            artifact["validated_at"] = None
            artifact["validation_evidence_id"] = None
            cleared.append(path)
    return sorted(cleared)


def invalidate_components(
    state: dict[str, Any], seeds: Iterable[str], revision: int
) -> list[str]:
    """Invalidate a real downstream closure without rewriting evidence statuses."""
    affected = transitive_consumers(state.get("components", {}), seeds)
    for component_id in affected:
        component = state["components"][component_id]
        component["status"] = "invalidated"
        component["invalidated_at_revision"] = revision
    return affected


def validate_artifact_proposal(
    proposal: Any,
    project_root: Path,
    state: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(proposal, dict):
        return ["proposal_not_object"]
    required = {
        "path", "platform_role", "purpose", "consumer_ids", "lifecycle", "class",
        "authorization_basis", "replaces", "identity_class",
    }
    missing = required - proposal.keys()
    if missing:
        return ["proposal_missing:" + ",".join(sorted(missing))]
    extra = set(proposal) - required - {"promotion_gate"}
    if extra:
        errors.append("proposal_extra:" + ",".join(sorted(extra)))
    try:
        _, rel = relative_safe(project_root, proposal["path"])
    except (ContractError, TypeError) as exc:
        return [str(exc)]
    if len(str(proposal.get("purpose", "")).strip()) < 8:
        errors.append("purpose_too_short")
    consumers = proposal.get("consumer_ids")
    if not isinstance(consumers, list) or not consumers or any(not str(item).strip() for item in consumers):
        errors.append("consumer_ids_invalid")
        consumers = []
    elif sorted(set(consumers)) != consumers:
        errors.append("consumer_ids_not_canonical")
    if proposal.get("lifecycle") not in {"ephemeral", "working", "milestone", "final"}:
        errors.append("lifecycle_invalid")
    if proposal.get("identity_class") not in {"working", "milestone", "frozen", "final"}:
        errors.append("identity_class_invalid")
    lifecycle_identity = {
        "ephemeral": {"working"},
        "working": {"working"},
        "milestone": {"milestone", "frozen"},
        "final": {"final"},
    }
    if (
        proposal.get("lifecycle") in lifecycle_identity
        and proposal.get("identity_class") not in lifecycle_identity[proposal["lifecycle"]]
    ):
        errors.append("lifecycle_identity_class_mismatch")
    if proposal.get("class") not in {"source", "code", "data", "result", "manuscript", "visual", "delivery", "control"}:
        errors.append("class_invalid")
    if len(str(proposal.get("authorization_basis", "")).strip()) < 4:
        errors.append("authorization_basis_too_short")

    contract = load_json(SKILL_ROOT / "references/artifact-contract.json")
    platform = load_json(SKILL_ROOT / "references/project-platform-contract.json")
    platform_role = proposal.get("platform_role")
    role_contract = platform.get("roles", {}).get(platform_role)
    if not isinstance(role_contract, dict):
        errors.append("platform_role_invalid")
    else:
        allowed_classes = role_contract.get("classes", [])
        if proposal.get("class") not in allowed_classes:
            errors.append("platform_role_class_mismatch")
        patterns = role_contract.get("path_patterns", [])
        if not patterns or not any(re.fullmatch(pattern, rel) for pattern in patterns):
            errors.append("platform_role_path_mismatch")
    basename = Path(rel).name
    if basename in set(contract.get("policy", {}).get("never_create_by_default", [])):
        replacement = proposal.get("replaces")
        replacement_valid = state is not None and replacement == rel and replacement in state.get("artifacts", {})
        if not replacement_valid:
            errors.append("default_redundant_artifact_requires_registered_same_path_replacement")
    for pattern in contract.get("policy", {}).get("forbidden_patterns", []):
        if re.search(pattern, rel, flags=re.IGNORECASE):
            errors.append("forbidden_artifact_pattern:" + pattern)

    if state is None:
        errors.append("state_required_for_artifact_admission")
    else:
        components = state.get("components", {})
        known_consumers = set(components) | {state.get("project", {}).get("id", "")}
        unknown = sorted(set(consumers) - known_consumers)
        if unknown:
            errors.append("unknown_consumers:" + ",".join(unknown))
        replacement = proposal.get("replaces")
        if replacement is not None and replacement not in state.get("artifacts", {}):
            errors.append("replacement_not_registered")
        promotion_gate = proposal.get("promotion_gate", [])
        if not isinstance(promotion_gate, list) or len(promotion_gate) != len(set(promotion_gate)):
            errors.append("promotion_gate_invalid")
        else:
            passing_ids = {
                item.get("id")
                for component in components.values()
                for item in component.get("evidence", [])
                if isinstance(item, dict) and item.get("status") == "pass"
            }
            missing_gate = set(promotion_gate) - passing_ids
            if missing_gate:
                errors.append("promotion_gate_unsatisfied:" + ",".join(sorted(missing_gate)))
        for existing_path, artifact in state.get("artifacts", {}).items():
            same_purpose = artifact.get("purpose") == proposal.get("purpose")
            same_consumers = sorted(artifact.get("consumers", [])) == sorted(consumers)
            same_class = artifact.get("class") == proposal.get("class")
            if (
                existing_path != rel
                and same_purpose and same_consumers and same_class
                and proposal.get("replaces") != existing_path
            ):
                errors.append("possible_duplicate_artifact:" + existing_path)
    return sorted(set(errors))


def validate_acyclic_components(components: dict[str, Any]) -> list[str]:
    visiting: set[str] = set()
    visited: set[str] = set()
    errors: list[str] = []

    def visit(node: str, trail: list[str]) -> None:
        if node in visiting:
            errors.append("component_dependency_cycle:" + "->".join(trail + [node]))
            return
        if node in visited:
            return
        visiting.add(node)
        component = components.get(node, {})
        dependencies = component.get("dependencies", []) if isinstance(component, dict) else []
        if not isinstance(dependencies, list):
            dependencies = []
        for dependency in dependencies:
            if isinstance(dependency, str) and dependency in components:
                visit(dependency, trail + [node])
        visiting.remove(node)
        visited.add(node)

    for component_id in components:
        visit(component_id, [])
    return errors


def validate_state_semantics(
    state: Any, project_root: Path | None, check_files: bool = False
) -> list[str]:
    """Validate control state; G1 callers intentionally skip live-file equality."""
    if not isinstance(state, dict):
        return ["state_not_object"]
    errors: list[str] = []
    if Draft202012Validator is None or FormatChecker is None:
        errors.append("jsonschema_dependency_missing")
    else:
        schema = load_json(SKILL_ROOT / "references/state.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for violation in validator.iter_errors(state):
            location = "/".join(str(item) for item in violation.absolute_path) or "$"
            errors.append(f"schema:{location}:{violation.validator}")
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        errors.append("state_schema_version")
    revision = state.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        return sorted(set(errors + ["state_revision_invalid"]))
    project = state.get("project")
    if not isinstance(project, dict):
        return sorted(set(errors + ["project_not_object"]))
    components = state.get("components")
    if not isinstance(components, dict):
        return sorted(set(errors + ["components_not_object"]))
    state_sets = {
        "question": {f"S{i}" for i in range(8)},
        "shared_data": {f"D{i}" for i in range(4)},
        "artifact": {f"A{i}" for i in range(4)},
    }
    evidence_ids: set[str] = set()
    terminal_states = {"question": "S7", "shared_data": "D3", "artifact": "A3"}
    for component_id, component in components.items():
        prefix = f"component:{component_id}:"
        if not isinstance(component, dict):
            errors.append(prefix + "not_object")
            continue
        component_type = component.get("type")
        if component_type not in state_sets:
            errors.append(prefix + "bad_type")
            continue
        if component.get("state") not in state_sets[component_type]:
            errors.append(prefix + "state_type_mismatch")
        terminal = terminal_states[component_type]
        if component.get("status") == "closed" and component.get("state") != terminal:
            errors.append(prefix + "closed_nonterminal")
        if (
            component.get("state") == terminal
            and component.get("status") not in {"closed", "invalidated"}
        ):
            errors.append(prefix + "terminal_not_closed")
        invalidated_at = component.get("invalidated_at_revision")
        if component.get("status") == "invalidated" and not isinstance(invalidated_at, int):
            errors.append(prefix + "invalidated_without_revision")
        if component.get("status") != "invalidated" and invalidated_at is not None:
            errors.append(prefix + "invalidation_revision_without_status")
        for field in ("dependencies", "consumers", "evidence", "decisions"):
            if not isinstance(component.get(field), list):
                errors.append(prefix + field + "_not_list")
        dependencies = component.get("dependencies", [])
        if not isinstance(dependencies, list):
            dependencies = []
        consumers = component.get("consumers", [])
        if not isinstance(consumers, list):
            consumers = []
        records = component.get("evidence", [])
        if not isinstance(records, list):
            records = []
        for dependency in dependencies:
            if not isinstance(dependency, str) or dependency not in components:
                errors.append(prefix + "missing_dependency:" + str(dependency))
            elif not isinstance(components[dependency], dict):
                errors.append(prefix + "dependency_not_object:" + str(dependency))
            elif component_id not in components[dependency].get("consumers", []):
                errors.append(prefix + "dependency_reverse_edge_missing:" + str(dependency))
        for consumer in consumers:
            if not isinstance(consumer, str) or consumer not in components:
                errors.append(prefix + "missing_consumer:" + str(consumer))
            elif not isinstance(components[consumer], dict):
                errors.append(prefix + "consumer_not_object:" + str(consumer))
            elif component_id not in components[consumer].get("dependencies", []):
                errors.append(prefix + "consumer_reverse_edge_missing:" + str(consumer))
        for evidence in records:
            errors.extend(prefix + item for item in validate_evidence(
                evidence, project_root, check_files, state=state,
                component_id=component_id, stored=True,
            ))
            evidence_id = evidence.get("id") if isinstance(evidence, dict) else None
            if isinstance(evidence_id, str):
                if evidence_id in evidence_ids:
                    errors.append(prefix + "duplicate_global_evidence_id:" + evidence_id)
                evidence_ids.add(evidence_id)
    errors.extend(validate_acyclic_components(components))

    required_components = project.get("required_components", [])
    if isinstance(required_components, list):
        unknown_required = {
            str(item) for item in required_components
            if not isinstance(item, str) or item not in components
        }
        if unknown_required:
            errors.append(
                "project_unknown_required_components:" + ",".join(sorted(unknown_required))
            )

    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("artifacts_not_object")
    else:
        project_id = project.get("id")
        for rel, artifact in artifacts.items():
            prefix = f"artifact:{rel}:"
            if not isinstance(artifact, dict):
                errors.append(prefix + "not_object")
                continue
            lifecycle_identity = {
                "ephemeral": {"working"},
                "working": {"working"},
                "milestone": {"milestone", "frozen"},
                "final": {"final"},
            }
            if (
                artifact.get("lifecycle") in lifecycle_identity
                and artifact.get("identity_class")
                not in lifecycle_identity[artifact["lifecycle"]]
            ):
                errors.append(prefix + "lifecycle_identity_class_mismatch")
            if artifact.get("producer") not in components and artifact.get("producer") != project_id:
                errors.append(prefix + "unknown_producer")
            artifact_consumers = artifact.get("consumers", [])
            if not isinstance(artifact_consumers, list):
                artifact_consumers = []
            unknown = {
                str(item) for item in artifact_consumers
                if not isinstance(item, str)
                or (item not in components and item != project_id)
            }
            if unknown:
                errors.append(prefix + "unknown_consumers:" + ",".join(sorted(unknown)))
            supersedes = artifact.get("supersedes")
            if supersedes is not None and supersedes not in artifacts:
                errors.append(prefix + "supersedes_missing:" + str(supersedes))
            if artifact.get("status") == "validated":
                evidence_id = artifact.get("validation_evidence_id")
                validation = next(
                    (
                        evidence
                        for component in components.values()
                        if isinstance(component, dict)
                        for evidence in component.get("evidence", [])
                        if isinstance(component.get("evidence", []), list)
                        if isinstance(evidence, dict) and evidence.get("id") == evidence_id
                    ),
                    None,
                )
                if (
                    validation is None
                    or validation.get("level") != "artifact_validation"
                    or validation.get("status") != "pass"
                    or not evidence_references_artifact(
                        validation, rel, artifact.get("sha256", "")
                    )
                ):
                    errors.append(prefix + "validated_without_current_evidence")
            if check_files and project_root is not None and artifact_is_current_formal(artifact):
                try:
                    path, normalized = relative_safe(project_root, rel)
                    if normalized != rel:
                        errors.append(prefix + "non_normalized_path")
                    if not path.is_file():
                        errors.append(prefix + "missing")
                    elif sha256_file(path) != artifact.get("sha256"):
                        errors.append(prefix + "hash_mismatch")
                except ContractError as exc:
                    errors.append(prefix + str(exc))

    last_route = state.get("last_route")
    if last_route is not None and not isinstance(last_route, dict):
        errors.append("last_route_not_object")
    executions = state.get("executions")
    if executions is not None:
        if not isinstance(executions, dict):
            errors.append("executions_not_object")
        else:
            for execution_id, execution in executions.items():
                prefix = f"execution:{execution_id}:"
                if not isinstance(execution, dict):
                    errors.append(prefix + "not_object")
                    continue
                if execution.get("id") != execution_id:
                    errors.append(prefix + "id_mismatch")
                start_revision = execution.get("start_revision")
                resolved_revision = execution.get("resolved_revision")
                if (
                    not isinstance(start_revision, int)
                    or not isinstance(resolved_revision, int)
                    or start_revision <= resolved_revision
                ):
                    errors.append(prefix + "revision_order")
                step_ids = execution.get("step_ids")
                step_modes = execution.get("step_modes")
                if (
                    isinstance(step_ids, list) and isinstance(step_modes, dict)
                    and set(step_ids) != set(step_modes)
                ):
                    errors.append(prefix + "step_mode_keys_mismatch")
                if isinstance(step_modes, dict):
                    mode_count = len(set(step_modes.values()))
                    aggregate_mode = execution.get("mode")
                    if mode_count > 1 and aggregate_mode != "mixed":
                        errors.append(prefix + "mixed_mode_not_declared")
                    if mode_count == 1 and aggregate_mode != next(iter(step_modes.values())):
                        errors.append(prefix + "single_mode_mismatch")
                if execution.get("status") == "open" and (
                    execution.get("end_revision") is not None
                    or execution.get("ended_at") is not None
                ):
                    errors.append(prefix + "open_has_end")
                if execution.get("status") == "closed" and (
                    execution.get("end_revision") is None
                    or execution.get("ended_at") is None
                ):
                    errors.append(prefix + "closed_missing_end")
    history = state.get("history")
    if not isinstance(history, list):
        errors.append("history_not_list")
    else:
        revisions = [item.get("revision") for item in history if isinstance(item, dict)]
        if revisions and revisions != list(range(1, revision + 1)):
            errors.append("history_revision_sequence")
        if revisions and revisions[-1] != revision:
            errors.append("history_revision_tail_mismatch")
    return sorted(set(errors))


def load_state(project_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = project_root / STATE_REL
    if not path.exists():
        return None, ["state_missing"]
    try:
        state = load_json(path)
    except ContractError as exc:
        return None, [str(exc)]
    return state, validate_state_semantics(state, project_root, check_files=False)
