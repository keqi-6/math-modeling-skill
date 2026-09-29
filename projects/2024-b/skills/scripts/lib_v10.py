#!/usr/bin/env python3
"""Shared deterministic helpers for the V10 controller."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # surfaced as a contract failure, never silently skipped
    Draft202012Validator = None  # type: ignore[assignment]
    FormatChecker = None  # type: ignore[assignment]


SKILL_ROOT = Path(__file__).resolve().parents[1]
STATE_REL = Path(".modeling/state.json")
IGNORED_DIRS = {
    ".git", ".svn", ".hg", ".modeling", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", "node_modules", ".venv", "venv", "dist", "build"
}
IGNORED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".swp", ".lock"}

EVIDENCE_LEVELS = {
    "scope", "problem_definition", "evidence_plan", "candidate_set", "model_spec",
    "selection_rationale", "implementation_ref", "result_claims", "data_identity",
    "provenance", "data_audit", "treatment_decision", "processed_identity",
    "artifact_draft", "artifact_validation", "artifact_acceptance", "delivery_acceptance",
    "uncertainty", "robustness", "model_redesign_control", "consumer_invalidation",
    "E1_IMPLEMENTATION", "E2_NUMERICAL", "E3_STRUCTURAL", "E4_REALITY",
}
STRONG_EVIDENCE_KINDS = {
    "implementation_ref": {"file", "command"},
    "result_claims": {"file", "command"},
    "processed_identity": {"file"},
    "artifact_draft": {"file"},
    "artifact_validation": {"file", "command"},
    "artifact_acceptance": {"file", "decision"},
    "delivery_acceptance": {"file", "decision"},
    "model_redesign_control": {"decision"},
    "consumer_invalidation": {"command", "decision"},
    "robustness": {"file", "command"},
    "E1_IMPLEMENTATION": {"file", "command"},
    "E2_NUMERICAL": {"file", "command"},
    "E3_STRUCTURAL": {"file", "command"},
    "E4_REALITY": {"file", "citation", "decision"},
}


class ContractError(ValueError):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise ContractError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON {path}: {exc}") from exc


def dump_json(path: Path, value: Any) -> None:
    """Atomically replace a JSON control file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_safe(root: Path, raw: str) -> tuple[Path, str]:
    candidate = Path(raw)
    if candidate.is_absolute():
        raise ContractError(f"path must be project-relative: {raw}")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        rel = resolved.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise ContractError(f"path escapes project root: {raw}") from exc
    if rel == ".modeling/state.json":
        return resolved, rel
    if any(part == ".." for part in candidate.parts):
        raise ContractError(f"path contains parent traversal: {raw}")
    return resolved, rel


def root_fingerprint(root: Path) -> str:
    return sha256_text(str(root.resolve()))


def load_rules(root: Path | None = None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    base = root or SKILL_ROOT
    rules: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for path in sorted((base / "rules").glob("*.json")):
        bundle = load_json(path)
        for rule in bundle.get("rules", []):
            copied = dict(rule)
            copied["_bundle"] = path.relative_to(base).as_posix()
            rules.append(copied)
            if copied.get("id") in by_id:
                raise ContractError(f"duplicate rule id: {copied.get('id')}")
            by_id[copied["id"]] = copied
    return rules, by_id


def load_state(project_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = project_root / STATE_REL
    if not path.exists():
        return None, ["state_missing"]
    try:
        state = load_json(path)
    except ContractError as exc:
        return None, [str(exc)]
    errors = validate_state_semantics(state, project_root, check_files=False)
    return state, errors


def evidence_levels(component: dict[str, Any]) -> set[str]:
    return {
        evidence.get("level", "")
        for evidence in component.get("evidence", [])
        if evidence.get("status") == "pass"
    }


def _is_hex(value: Any, length: int = 64) -> bool:
    return isinstance(value, str) and len(value) == length and re.fullmatch(r"[0-9a-f]+", value) is not None


def valid_iso_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def component_subject_hash(state: dict[str, Any], component_id: str) -> str:
    """Bind evidence to the component's current dependency/artifact identity."""
    component = state.get("components", {}).get(component_id, {})
    related = {component_id, *component.get("dependencies", [])}
    artifacts = {
        path: item.get("sha256")
        for path, item in state.get("artifacts", {}).items()
        if item.get("producer") in related or related & set(item.get("consumers", []))
    }
    identity = {
        "component_id": component_id,
        "component_type": component.get("type"),
        "dependencies": sorted(component.get("dependencies", [])),
        "artifacts": dict(sorted(artifacts.items())),
    }
    return sha256_text(json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def validate_evidence(
    evidence: Any,
    project_root: Path | None,
    check_files: bool,
    *,
    state: dict[str, Any] | None = None,
    component_id: str | None = None,
    stored: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(evidence, dict):
        return ["evidence_not_object"]
    required = {
        "id", "level", "status", "kind", "locator", "claim", "observed_at", "producer",
        "subject_id", "subject_hash",
    }
    if stored:
        required.add("recorded_revision")
    missing = required - evidence.keys()
    if missing:
        errors.append("evidence_missing:" + ",".join(sorted(missing)))
        return errors
    extra = set(evidence) - required
    if extra:
        errors.append("evidence_extra:" + ",".join(sorted(extra)))
    if not isinstance(evidence.get("id"), str) or not evidence["id"].strip():
        errors.append("evidence_id_invalid")
    if evidence.get("level") not in EVIDENCE_LEVELS:
        errors.append("evidence_bad_level")
    if evidence["status"] not in {"pass", "fail", "not_applicable", "stale"}:
        errors.append("evidence_bad_status")
    if evidence["kind"] not in {"file", "command", "citation", "observation", "decision"}:
        errors.append("evidence_bad_kind")
        return errors
    allowed_kinds = STRONG_EVIDENCE_KINDS.get(evidence.get("level"))
    if evidence.get("status") == "pass" and allowed_kinds is not None and evidence["kind"] not in allowed_kinds:
        errors.append("evidence_kind_too_weak_for_level")
    locator = evidence["locator"]
    if not isinstance(locator, dict):
        return errors + ["evidence_locator_not_object"]
    expected_keys = {
        "file": {"path", "sha256"},
        "command": {"command_hash", "exit_code", "output_ref", "output_sha256"},
        "citation": {"uri", "accessed_at"},
        "observation": {"subject", "method", "value"},
        "decision": {"decision_id", "recorded_at"},
    }[evidence["kind"]]
    if set(locator) != expected_keys:
        errors.append("evidence_locator_shape")
        return errors
    if evidence["kind"] == "file":
        if not _is_hex(locator.get("sha256")):
            errors.append("evidence_bad_sha256")
        if project_root is not None:
            try:
                path, _ = relative_safe(project_root, locator["path"])
                if check_files and evidence.get("status") != "stale":
                    if not path.is_file():
                        errors.append("evidence_file_missing")
                    elif sha256_file(path) != locator["sha256"]:
                        errors.append("evidence_file_hash_mismatch")
            except ContractError as exc:
                errors.append(str(exc))
    elif evidence["kind"] == "command":
        if not _is_hex(locator.get("command_hash")) or not isinstance(locator.get("exit_code"), int) or not _is_hex(locator.get("output_sha256")):
            errors.append("evidence_command_identity_invalid")
        if evidence.get("status") == "pass" and locator.get("exit_code") != 0:
            errors.append("evidence_passing_command_nonzero_exit")
        if project_root is not None:
            try:
                output_path, _ = relative_safe(project_root, locator.get("output_ref", ""))
                if check_files and evidence.get("status") != "stale":
                    if not output_path.is_file():
                        errors.append("evidence_command_output_missing")
                    elif sha256_file(output_path) != locator.get("output_sha256"):
                        errors.append("evidence_command_output_hash_mismatch")
            except (ContractError, TypeError) as exc:
                errors.append(str(exc))
    elif evidence["kind"] == "citation":
        if not re.match(r"^https?://", str(locator.get("uri", ""))):
            errors.append("evidence_citation_uri_invalid")
        if not valid_iso_datetime(locator.get("accessed_at")):
            errors.append("evidence_citation_time_invalid")
    elif evidence["kind"] == "observation":
        if not locator.get("subject") or not locator.get("method"):
            errors.append("evidence_observation_invalid")
    elif evidence["kind"] == "decision":
        if not locator.get("decision_id") or not valid_iso_datetime(locator.get("recorded_at")):
            errors.append("evidence_decision_invalid")
        if state is not None:
            decision = next((item for item in state.get("open_decisions", []) if item.get("id") == locator.get("decision_id")), None)
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
    if not _is_hex(evidence.get("subject_hash")):
        errors.append("evidence_subject_hash_invalid")
    if component_id is not None and evidence.get("subject_id") != component_id:
        errors.append("evidence_subject_mismatch")
    if state is not None and component_id is not None and not stored and evidence.get("subject_hash") != component_subject_hash(state, component_id):
        errors.append("evidence_subject_hash_stale")
    if stored and (not isinstance(evidence.get("recorded_revision"), int) or evidence["recorded_revision"] < 1):
        errors.append("evidence_recorded_revision_invalid")
    return errors


def validate_state_semantics(state: Any, project_root: Path | None, check_files: bool = True) -> list[str]:
    errors: list[str] = []
    if not isinstance(state, dict):
        return ["state_not_object"]
    if Draft202012Validator is None or FormatChecker is None:
        errors.append("jsonschema_dependency_missing")
    else:
        schema = load_json(SKILL_ROOT / "references/state.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for violation in validator.iter_errors(state):
            location = "/".join(str(item) for item in violation.absolute_path) or "$"
            errors.append(f"schema:{location}:{violation.validator}")
    required = {
        "schema_version", "revision", "project", "components", "artifacts", "open_decisions",
        "next_actions", "last_route", "executions", "watch_roots", "workspace_manifest", "history"
    }
    missing = required - state.keys()
    if missing:
        errors.append("state_missing_fields:" + ",".join(sorted(missing)))
        return errors
    if state.get("schema_version") != "10.0":
        errors.append("state_schema_version")
    if not isinstance(state.get("revision"), int) or state["revision"] < 0:
        errors.append("state_revision_invalid")
    project = state.get("project")
    if not isinstance(project, dict):
        errors.append("project_not_object")
        return errors
    if project.get("state") not in {"P0", "P1", "P2"}:
        errors.append("project_state_invalid")
    if project_root is not None and project.get("root_fingerprint") != root_fingerprint(project_root):
        errors.append("project_root_fingerprint_mismatch")
    components = state.get("components")
    if not isinstance(components, dict):
        errors.append("components_not_object")
        return errors
    state_sets = {
        "question": {f"S{i}" for i in range(8)},
        "shared_data": {f"D{i}" for i in range(4)},
        "artifact": {f"A{i}" for i in range(4)},
    }
    evidence_ids: set[str] = set()
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
        if component.get("status") not in {"active", "blocked", "invalidated", "closed"}:
            errors.append(prefix + "bad_status")
        terminal = {"question": "S7", "shared_data": "D3", "artifact": "A3"}.get(component_type)
        if component.get("status") == "closed" and component.get("state") != terminal:
            errors.append(prefix + "closed_nonterminal")
        if component.get("state") == terminal and component.get("status") not in {"closed", "invalidated"}:
            errors.append(prefix + "terminal_not_closed")
        invalidated_at = component.get("invalidated_at_revision")
        if component.get("status") == "invalidated" and not isinstance(invalidated_at, int):
            errors.append(prefix + "invalidated_without_revision")
        if component.get("status") != "invalidated" and invalidated_at is not None:
            errors.append(prefix + "invalidation_revision_without_status")
        epoch = component.get("evidence_epoch_revision")
        if not isinstance(epoch, int) or epoch < 0 or epoch > state.get("revision", -1):
            errors.append(prefix + "bad_evidence_epoch_revision")
        for field in ("dependencies", "consumers", "evidence", "decisions"):
            if not isinstance(component.get(field), list):
                errors.append(prefix + field + "_not_list")
        for evidence in component.get("evidence", []):
            errors.extend(prefix + item for item in validate_evidence(
                evidence, project_root, check_files, state=state,
                component_id=component_id, stored=True,
            ))
            if isinstance(evidence, dict) and isinstance(evidence.get("id"), str):
                if evidence["id"] in evidence_ids:
                    errors.append(prefix + "duplicate_global_evidence_id:" + evidence["id"])
                evidence_ids.add(evidence["id"])
    required_components = project.get("required_components", [])
    if not isinstance(required_components, list):
        errors.append("project_required_components_not_list")
    else:
        unknown_required = set(required_components) - set(components)
        if unknown_required:
            errors.append("project_unknown_required_components:" + ",".join(sorted(unknown_required)))
    for component_id, component in components.items():
        for dependency in component.get("dependencies", []):
            if dependency not in components:
                errors.append(f"component:{component_id}:missing_dependency:{dependency}")
            elif component_id not in components[dependency].get("consumers", []):
                errors.append(f"component:{component_id}:dependency_reverse_edge_missing:{dependency}")
        for consumer in component.get("consumers", []):
            if consumer not in components:
                errors.append(f"component:{component_id}:missing_consumer:{consumer}")
            elif component_id not in components[consumer].get("dependencies", []):
                errors.append(f"component:{component_id}:consumer_reverse_edge_missing:{consumer}")
    errors.extend(validate_acyclic_components(components))
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("artifacts_not_object")
    else:
        for rel, artifact in artifacts.items():
            prefix = f"artifact:{rel}:"
            if not isinstance(artifact, dict):
                errors.append(prefix + "not_object")
                continue
            if not _is_hex(artifact.get("sha256")):
                errors.append(prefix + "bad_sha256")
            if not isinstance(artifact.get("size"), int) or artifact.get("size", 0) < 1:
                errors.append(prefix + "bad_size")
            if not artifact.get("consumers"):
                errors.append(prefix + "no_consumers")
            if artifact.get("producer") not in components and artifact.get("producer") != project.get("id"):
                errors.append(prefix + "unknown_producer")
            unknown_consumers = set(artifact.get("consumers", [])) - set(components) - {project.get("id")}
            if unknown_consumers:
                errors.append(prefix + "unknown_consumers:" + ",".join(sorted(unknown_consumers)))
            if artifact.get("status") == "validated":
                evidence_id = artifact.get("validation_evidence_id")
                validation = next(
                    (
                        evidence for component in components.values()
                        for evidence in component.get("evidence", [])
                        if isinstance(evidence, dict) and evidence.get("id") == evidence_id
                    ),
                    None,
                )
                if validation is None or validation.get("level") != "artifact_validation" or validation.get("status") != "pass":
                    errors.append(prefix + "validated_without_evidence")
            if project_root is not None:
                try:
                    path, normalized = relative_safe(project_root, rel)
                    if normalized != rel:
                        errors.append(prefix + "non_normalized_path")
                    if check_files:
                        if not path.is_file():
                            errors.append(prefix + "missing")
                        else:
                            if path.stat().st_size != artifact.get("size"):
                                errors.append(prefix + "size_mismatch")
                            if sha256_file(path) != artifact.get("sha256"):
                                errors.append(prefix + "hash_mismatch")
                except ContractError as exc:
                    errors.append(prefix + str(exc))
    last_route = state.get("last_route")
    if last_route is not None:
        if not isinstance(last_route, dict):
            errors.append("last_route_not_object")
        else:
            for field in ("request_hash", "route_ids", "rule_ids", "component_ids", "resolved_at"):
                if field not in last_route:
                    errors.append("last_route_missing:" + field)
            if not _is_hex(last_route.get("request_hash")):
                errors.append("last_route_bad_request_hash")
    executions = state.get("executions")
    if not isinstance(executions, dict):
        errors.append("executions_not_object")
    else:
        for execution_id, execution in executions.items():
            if not isinstance(execution, dict):
                errors.append(f"execution:{execution_id}:not_object")
                continue
            if execution.get("id") != execution_id:
                errors.append(f"execution:{execution_id}:id_mismatch")
            if execution.get("start_revision", 0) <= execution.get("resolved_revision", -1):
                errors.append(f"execution:{execution_id}:revision_order")
            if execution.get("status") == "open" and (execution.get("end_revision") is not None or execution.get("ended_at") is not None):
                errors.append(f"execution:{execution_id}:open_has_end")
            if execution.get("status") == "closed" and (execution.get("end_revision") is None or execution.get("ended_at") is None):
                errors.append(f"execution:{execution_id}:closed_missing_end")
    watch_roots = state.get("watch_roots")
    if not isinstance(watch_roots, list) or not watch_roots or len(watch_roots) != len(set(watch_roots)):
        errors.append("watch_roots_invalid")
    elif project_root is not None:
        for raw_root in watch_roots:
            try:
                watched, _ = relative_safe(project_root, raw_root)
                if not watched.exists():
                    errors.append("watch_root_missing:" + str(raw_root))
            except (ContractError, TypeError) as exc:
                errors.append("watch_root_invalid:" + str(exc))
        for rel in artifacts or {}:
            if not any(rel == raw or raw == "." or rel.startswith(str(raw).rstrip("/") + "/") for raw in watch_roots):
                errors.append("artifact_outside_watch_roots:" + rel)
    manifest = state.get("workspace_manifest")
    if not isinstance(manifest, dict):
        errors.append("workspace_manifest_not_object")
    else:
        for rel, identity in manifest.items():
            try:
                if project_root is not None:
                    relative_safe(project_root, rel)
            except (ContractError, TypeError) as exc:
                errors.append("manifest_path_invalid:" + str(exc))
            if not isinstance(identity, dict) or set(identity) != {"sha256", "size"}:
                errors.append("manifest_identity_invalid:" + str(rel))
            elif not _is_hex(identity.get("sha256")) or not isinstance(identity.get("size"), int) or identity["size"] < 0:
                errors.append("manifest_identity_invalid:" + str(rel))
    history = state.get("history")
    if not isinstance(history, list):
        errors.append("history_not_list")
    else:
        revisions = [entry.get("revision") for entry in history if isinstance(entry, dict)]
        if revisions and revisions != list(range(1, state.get("revision", 0) + 1)):
            errors.append("history_revision_sequence")
        if revisions and revisions[-1] != state.get("revision"):
            errors.append("history_revision_tail_mismatch")
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
        for dependency in components.get(node, {}).get("dependencies", []):
            if dependency in components:
                visit(dependency, trail + [node])
        visiting.remove(node)
        visited.add(node)

    for component_id in components:
        visit(component_id, [])
    return errors


def transitive_consumers(components: dict[str, Any], seeds: Iterable[str]) -> list[str]:
    queue = list(seeds)
    seen = set(queue)
    while queue:
        current = queue.pop(0)
        for consumer in components.get(current, {}).get("consumers", []):
            if consumer not in seen:
                seen.add(consumer)
                queue.append(consumer)
    return sorted(seen)


def iter_workspace_files(project_root: Path, watch_roots: Iterable[str]) -> Iterable[tuple[str, Path]]:
    seen: set[str] = set()
    for raw_root in watch_roots:
        root_path, _ = relative_safe(project_root, raw_root)
        if not root_path.exists():
            raise ContractError(f"watch root does not exist: {raw_root}")
        candidates = [root_path] if root_path.is_file() else root_path.rglob("*")
        for path in candidates:
            if not path.is_file():
                continue
            resolved = path.resolve()
            try:
                rel_path = resolved.relative_to(project_root.resolve())
            except ValueError as exc:
                raise ContractError(f"workspace path escapes project root: {path}") from exc
            if any(part in IGNORED_DIRS for part in rel_path.parts):
                continue
            if path.suffix.lower() in IGNORED_SUFFIXES:
                continue
            rel = rel_path.as_posix()
            if rel in seen or rel == STATE_REL.as_posix():
                continue
            seen.add(rel)
            yield rel, path


def build_workspace_manifest(project_root: Path, watch_roots: Iterable[str]) -> dict[str, dict[str, Any]]:
    return {
        rel: {"sha256": sha256_file(path), "size": path.stat().st_size}
        for rel, path in sorted(iter_workspace_files(project_root, watch_roots), key=lambda item: item[0])
    }


def manifest_sha256(manifest: dict[str, Any]) -> str:
    return sha256_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def component_state_for_route(
    state: dict[str, Any] | None,
    component_types: list[str],
    component_id: str | None,
) -> tuple[str, str, list[str]]:
    if "skill" in component_types:
        return "V10", "skill", []
    if state is None:
        return "UNINITIALIZED", "project" if "project" in component_types else "none", []
    if component_id:
        component = state.get("components", {}).get(component_id)
        if component is None:
            return "UNKNOWN_COMPONENT", "none", []
        return component["state"], component["type"], [component_id]
    wanted = {item for item in component_types if item in {"question", "shared_data", "artifact"}}
    matches = [
        (identifier, component)
        for identifier, component in state.get("components", {}).items()
        if component.get("type") in wanted
    ]
    if len(matches) == 1:
        identifier, component = matches[0]
        return component["state"], component["type"], [identifier]
    if len(matches) > 1:
        states = {component["state"] for _, component in matches}
        if len(states) == 1:
            return next(iter(states)), "multiple", [identifier for identifier, _ in matches]
        return "AMBIGUOUS_COMPONENT", "multiple", [identifier for identifier, _ in matches]
    if "project" in component_types:
        return state["project"]["state"], "project", []
    if "none" in component_types:
        return state["project"]["state"], "none", []
    return "MISSING_COMPONENT", "none", []


def rule_matches_route(rule: dict[str, Any], route: dict[str, Any], mode: str | None = None) -> bool:
    selectors = set(rule.get("routes", []))
    if "*" in selectors or route["id"] in selectors:
        return True
    if "@recovery" in selectors and route.get("recovery"):
        return True
    write_applies = (
        mode in {"mutate", "promote", "skill_maintenance"}
        if mode is not None else route.get("write_policy") != "never"
    )
    if "@write" in selectors and write_applies:
        return True
    return False


def route_emitted_events(route: dict[str, Any], event_model: dict[str, Any], mode: str) -> set[str]:
    """Return the closed event vocabulary emitted by one route execution."""
    events = set(event_model.get("global", []))
    if mode in {"mutate", "promote", "skill_maintenance"}:
        events.update(event_model.get("writable", []))
    if mode == "promote":
        events.update(event_model.get("promote", []))
    if route.get("recovery"):
        events.update(event_model.get("recovery", []))
    events.update(event_model.get("route_events", {}).get(route["id"], []))
    return events


def evaluate_predicate(predicate: dict[str, Any], facts: dict[str, Any]) -> tuple[str, str]:
    """Evaluate one closed-vocabulary predicate as true, false, or unresolved."""
    field = predicate.get("field")
    operator = predicate.get("op")
    expected = predicate.get("value")
    if field not in facts:
        return "unresolved", f"fact {field} is unavailable"
    actual = facts[field]
    try:
        if operator == "exists":
            result = actual is not None if expected else actual is None
        elif operator == "eq":
            result = actual == expected
        elif operator == "ne":
            result = actual != expected
        elif operator == "in":
            result = actual in expected if isinstance(expected, (list, tuple, set, str)) else actual == expected
        elif operator == "matches":
            result = re.search(str(expected), str(actual), flags=re.IGNORECASE) is not None
        elif operator == "changed":
            result = bool(actual) is bool(expected)
        else:
            return "unresolved", f"operator {operator} has no evaluator"
    except (TypeError, re.error) as exc:
        return "unresolved", f"predicate evaluation failed: {exc}"
    return ("true" if result else "false"), f"{field} {operator} {expected!r}; actual={actual!r}"


def rule_applicability(
    rule: dict[str, Any],
    node: dict[str, Any],
    emitted_events: set[str],
    facts: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate every structured applicability dimension of one atomic rule."""
    route = node["route"]
    state = node["state"]
    component_type = node["component_type"]
    scope = rule.get("scope", {})
    objects = set(scope.get("objects", []))
    states = set(scope.get("states", []))
    types = set(scope.get("component_types", []))
    object_ok = "*" in objects or route["object"] in objects
    state_ok = "*" in states or state in states or state == "UNBOUND_ADVISORY"
    type_ok = "none" in types or component_type in types or (
        component_type == "multiple" and bool(types & {"question", "shared_data", "artifact"})
    )
    declared_events = set(rule.get("trigger", {}).get("events", []))
    matched_events = sorted(declared_events & emitted_events)
    event_ok = bool(matched_events)
    predicate_results = []
    for predicate in rule.get("trigger", {}).get("predicates", []):
        status, reason = evaluate_predicate(predicate, facts)
        predicate_results.append({"predicate": predicate, "status": status, "reason": reason})
    predicate_false = any(item["status"] == "false" for item in predicate_results)
    predicate_unresolved = any(item["status"] == "unresolved" for item in predicate_results)
    exception_results: list[dict[str, Any]] = []
    override_applicability = False
    for exception in rule.get("exceptions", []):
        if exception.get("kind") == "runtime_condition":
            exception_status, reason = evaluate_predicate(exception["when"], facts)
            activated = exception_status == "true"
            override_applicability = override_applicability or (
                activated and exception.get("disposition") == "override_applicability"
            )
            exception_results.append({
                "kind": "runtime_condition", "status": exception_status,
                "activated": activated, "reason": reason,
                "disposition": exception.get("disposition"),
            })
        elif exception.get("kind") == "decision_required":
            exception_results.append({
                "kind": "decision_required", "status": "deferred_to_agent",
                "condition_key": exception.get("condition_key"),
                "when": exception.get("when"), "disposition": exception.get("disposition"),
            })
        else:
            exception_results.append({"kind": exception.get("kind"), "status": "invalid"})
    dimensions_ok = object_ok and state_ok and type_ok and event_ok
    applicable = dimensions_ok and (override_applicability or not predicate_false)
    if not applicable:
        status = "not_applicable"
    elif predicate_unresolved and not override_applicability:
        status = "needs_fact"
    else:
        status = "applicable"
    return {
        "status": status,
        "route_id": route["id"],
        "checks": {
            "route_selector": True,
            "object": {"status": object_ok, "actual": route["object"], "allowed": sorted(objects)},
            "component_type": {"status": type_ok, "actual": component_type, "allowed": sorted(types)},
            "state": {"status": state_ok, "actual": state, "allowed": sorted(states)},
            "events": {"status": event_ok, "matched": matched_events, "declared": sorted(declared_events)},
            "predicates": predicate_results,
            "exceptions": exception_results,
            "exception_override": override_applicability,
        },
    }


def selected_rules_for_routes(
    rules: list[dict[str, Any]],
    route_nodes: list[dict[str, Any]],
    mode: str,
    event_model: dict[str, Any],
    facts: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Select rules only after route, scope, event, and predicate evaluation."""
    selected: dict[str, dict[str, Any]] = {}
    evidence: dict[str, list[dict[str, Any]]] = {}
    for node in route_nodes:
        route = node["route"]
        emitted_events = route_emitted_events(route, event_model, mode)
        for rule in rules:
            if rule.get("status") != "active" or not rule_matches_route(rule, route, mode):
                continue
            applicability = rule_applicability(rule, node, emitted_events, facts)
            evidence.setdefault(rule["id"], []).append(applicability)
            if applicability["status"] in {"applicable", "needs_fact"}:
                selected[rule["id"]] = rule
    return [selected[key] for key in sorted(selected)], {key: evidence[key] for key in sorted(evidence)}


def validate_artifact_proposal(
    proposal: Any,
    project_root: Path,
    state: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(proposal, dict):
        return ["proposal_not_object"]
    required = {"path", "purpose", "consumer_ids", "lifecycle", "class", "authorization_basis", "replaces"}
    missing = required - proposal.keys()
    if missing:
        return ["proposal_missing:" + ",".join(sorted(missing))]
    extra = set(proposal) - required - {"promotion_gate"}
    if extra:
        errors.append("proposal_extra:" + ",".join(sorted(extra)))
    try:
        _, rel = relative_safe(project_root, proposal["path"])
    except (ContractError, TypeError) as exc:
        errors.append(str(exc))
        return errors
    if len(str(proposal.get("purpose", "")).strip()) < 8:
        errors.append("purpose_too_short")
    consumers = proposal.get("consumer_ids")
    if not isinstance(consumers, list) or not consumers or any(not str(item).strip() for item in consumers):
        errors.append("consumer_ids_invalid")
    if proposal.get("lifecycle") not in {"ephemeral", "working", "milestone", "final"}:
        errors.append("lifecycle_invalid")
    if proposal.get("class") not in {"source", "code", "data", "result", "manuscript", "visual", "delivery", "control"}:
        errors.append("class_invalid")
    if len(str(proposal.get("authorization_basis", "")).strip()) < 4:
        errors.append("authorization_basis_too_short")
    contract = load_json(SKILL_ROOT / "references/artifact-contract.json")
    basename = Path(rel).name
    if basename in set(contract["policy"]["never_create_by_default"]):
        replacement = proposal.get("replaces")
        replacement_valid = state is not None and replacement == rel and replacement in state.get("artifacts", {})
        if not replacement_valid:
            errors.append("default_redundant_artifact_requires_registered_same_path_replacement")
    for pattern in contract["policy"]["forbidden_patterns"]:
        if re.search(pattern, rel, flags=re.IGNORECASE):
            errors.append("forbidden_artifact_pattern:" + pattern)
    if rel.endswith("/"):
        errors.append("artifact_must_be_file")
    if state is None:
        errors.append("state_required_for_artifact_admission")
    else:
        components = state.get("components", {})
        known_consumers = set(components) | {state.get("project", {}).get("id", "")}
        unknown = [item for item in consumers or [] if item not in known_consumers]
        if unknown:
            errors.append("unknown_consumers:" + ",".join(sorted(unknown)))
        replacement = proposal.get("replaces")
        if replacement is not None and replacement not in state.get("artifacts", {}):
            errors.append("replacement_not_registered")
        if replacement is not None and replacement in state.get("artifacts", {}):
            replaced = state["artifacts"][replacement]
            if sorted(replaced.get("consumers", [])) != sorted(consumers or []):
                errors.append("replacement_consumer_mismatch")
        promotion_gate = proposal.get("promotion_gate", [])
        if not isinstance(promotion_gate, list) or len(promotion_gate) != len(set(promotion_gate)):
            errors.append("promotion_gate_invalid")
        else:
            passing_ids = {
                evidence.get("id")
                for component in components.values()
                for evidence in component.get("evidence", [])
                if isinstance(evidence, dict) and evidence.get("status") == "pass"
            }
            missing_gate = set(promotion_gate) - passing_ids
            if missing_gate:
                errors.append("promotion_gate_unsatisfied:" + ",".join(sorted(missing_gate)))
        for existing_path, artifact in state.get("artifacts", {}).items():
            same_consumers = sorted(artifact.get("consumers", [])) == sorted(consumers or [])
            same_role = artifact.get("role") == proposal.get("class") or (
                proposal.get("class") in {"code", "data"} and artifact.get("role") in {"source", "intermediate", "result"}
            )
            if existing_path != rel and same_consumers and same_role and replacement != existing_path:
                errors.append("possible_duplicate_artifact:" + existing_path)
    return sorted(set(errors))


def json_output(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False))
