#!/usr/bin/env python3
"""Validate V7 receipts, recovery evidence, artifact classes, and decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from recovery_manifest import inventory, ranges_cover, verify_manifest


STATES = {
    "S0_RECOVER", "S1_INTERPRET", "S2_ASSESS", "S3_DECIDE",
    "S4_SPECIFY", "S5_IMPLEMENT", "S6_VERIFY", "S7_PUBLISH",
}
GATES = {"not_triggered", "in_progress", "closed"}
RECOVERY_LEVELS = {
    "R0_INCREMENTAL_CHECKPOINT", "R1_HASH_DELTA_RECOVERY", "R2_FULL_RECOVERY",
}
READ_ONLY_RECOVERY_ACTIONS = {
    "enumerate", "hash", "read", "extract", "render", "inspect", "compare",
    "write_external_recovery_evidence",
}
ARTIFACT_DISPOSITIONS = {
    "provisional", "current_authority", "frozen_evidence",
    "external_recovery_evidence", "no_project_artifact",
}
AUTHORITY_STATUSES = {
    "provisional", "approved", "frozen", "external_only", "not_applicable",
}
ARTIFACT_CLASSES = {
    "analysis_candidate", "solution_brief", "reproduction_document",
    "machine_evidence", "formal_delivery", "navigation", "external_evidence",
    "not_applicable",
}


def validate_artifact_class(
    item: dict, label: str, state: str | None, manuscript_mutation: object
) -> list[str]:
    errors: list[str] = []
    artifact_class = item.get("artifact_class")
    path = item.get("path")
    if artifact_class not in ARTIFACT_CLASSES:
        return [f"{label} has invalid artifact_class"]
    if artifact_class == "not_applicable":
        if item.get("disposition") != "no_project_artifact" or path not in {"", None}:
            errors.append(f"{label} not_applicable class requires no_project_artifact")
        return errors
    if not isinstance(path, str) or not path.strip():
        return errors
    parts = Path(path).parts
    if artifact_class == "analysis_candidate" and not path.startswith("planning/analysis/"):
        errors.append(f"{label} analysis_candidate must be under planning/analysis/")
    elif artifact_class == "solution_brief":
        if not (len(parts) == 3 and parts[0] == "docs" and parts[1] and parts[2] == "solution_brief.md"):
            errors.append(f"{label} solution_brief must be exactly docs/<task-id>/solution_brief.md")
        if state is not None and state not in {"S6_VERIFY", "S7_PUBLISH"}:
            errors.append(f"{label} solution_brief requires S6_VERIFY or S7_PUBLISH")
    elif artifact_class == "reproduction_document":
        if not path.startswith("docs/"):
            errors.append(f"{label} reproduction_document must be under docs/")
        if path.endswith("/solution_brief.md"):
            errors.append(f"{label} solution_brief path requires solution_brief class")
    elif artifact_class == "machine_evidence" and not (
        path.startswith("output/") or path.startswith("planning/audits/")
    ):
        errors.append(f"{label} machine_evidence must be under output/ or planning/audits/")
    elif artifact_class == "formal_delivery":
        if not path.startswith("paper/"):
            errors.append(f"{label} formal_delivery must be under paper/")
        if state is not None and state != "S7_PUBLISH":
            errors.append(f"{label} formal_delivery requires S7_PUBLISH")
        if manuscript_mutation is not None and manuscript_mutation is not True:
            errors.append(f"{label} formal_delivery requires manuscript_mutation=true")
    elif artifact_class == "navigation" and not (
        path in {"HANDOFF.md", "README.md", "project_state.json"}
        or path.startswith("planning/")
    ):
        errors.append(f"{label} navigation path is outside the navigation contract")
    elif artifact_class == "external_evidence" and not (
        path.startswith("references/") or path.startswith("data/")
    ):
        errors.append(f"{label} external_evidence must be under references/ or data/")
    return errors


def validate_artifact_plan(payload: dict) -> list[str]:
    """Require every start receipt to declare whether substantive content lands."""
    errors: list[str] = []
    substantive = payload.get("substantive_analysis")
    if not isinstance(substantive, bool):
        errors.append("substantive_analysis must be boolean")
    plan = payload.get("artifact_plan")
    if not isinstance(plan, list) or not plan:
        return errors + ["artifact_plan must be a nonempty list"]
    material_count = 0
    for index, item in enumerate(plan):
        label = f"artifact_plan[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in ("content", "disposition", "artifact_class", "path", "promotion_requires", "reason"):
            if field not in item:
                errors.append(f"{label} missing {field}")
        disposition = item.get("disposition")
        if disposition not in ARTIFACT_DISPOSITIONS:
            errors.append(f"{label} has invalid disposition")
            continue
        path = item.get("path")
        errors.extend(validate_artifact_class(
            item, label, payload.get("earliest_open_state"), payload.get("manuscript_mutation")
        ))
        if disposition == "no_project_artifact":
            if path not in {"", None}:
                errors.append(f"{label} no_project_artifact must not name a path")
            if not str(item.get("reason", "")).strip():
                errors.append(f"{label} no_project_artifact requires a concrete reason")
        else:
            material_count += 1
            if not isinstance(path, str) or not path.strip():
                errors.append(f"{label} material artifact requires a path")
            elif disposition == "provisional" and item.get("artifact_class") != "analysis_candidate":
                errors.append(f"{label} provisional disposition requires analysis_candidate")
    if substantive is True and material_count == 0:
        errors.append("substantive analysis requires a non-chat artifact disposition")
    return errors


def validate_artifact_disposition(
    payload: dict, project_root: Path | None
) -> list[str]:
    """Reject complete end receipts that leave planned substantive artifacts unrealized."""
    errors: list[str] = []
    items = payload.get("artifact_disposition")
    if not isinstance(items, list) or not items:
        return ["artifact_disposition must be a nonempty list"]
    outputs = payload.get("outputs")
    output_set = set(outputs) if isinstance(outputs, list) else set()
    for index, item in enumerate(items):
        label = f"artifact_disposition[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        for field in (
            "content", "disposition", "artifact_class", "path", "realized", "authority_status", "evidence"
        ):
            if field not in item:
                errors.append(f"{label} missing {field}")
        disposition = item.get("disposition")
        if disposition not in ARTIFACT_DISPOSITIONS:
            errors.append(f"{label} has invalid disposition")
            continue
        errors.extend(validate_artifact_class(item, label, None, None))
        if item.get("authority_status") not in AUTHORITY_STATUSES:
            errors.append(f"{label} has invalid authority_status")
        realized = item.get("realized")
        if not isinstance(realized, bool):
            errors.append(f"{label} realized must be boolean")
            continue
        path_value = item.get("path")
        if disposition == "no_project_artifact":
            if path_value not in {"", None} or item.get("authority_status") != "not_applicable":
                errors.append(f"{label} invalid no_project_artifact disposition")
            continue
        if payload.get("status") == "complete" and not realized:
            errors.append(f"{label} complete receipt cannot leave artifact unrealized")
        if realized:
            if not isinstance(path_value, str) or not path_value.strip():
                errors.append(f"{label} realized artifact requires a path")
                continue
            if path_value not in output_set:
                errors.append(f"{label} realized artifact must appear in outputs")
            if project_root is None:
                errors.append(f"{label} realized artifact validation requires --project-root")
            elif not (project_root / path_value).exists():
                errors.append(f"{label} realized artifact path does not exist")
    return errors


def validate_manuscript_round(payload: dict, project_root: Path | None) -> list[str]:
    """Require current-round rule evidence before any manuscript mutation."""
    if payload.get("manuscript_mutation") is not True:
        return []
    errors: list[str] = []
    if not payload.get("manuscript_round_id"):
        errors.append("manuscript mutation requires manuscript_round_id")
    evidence = payload.get("manuscript_rule_read_evidence")
    if not isinstance(evidence, list) or not evidence:
        return errors + ["manuscript mutation requires current-round rule-read evidence"]
    if project_root is None:
        return errors + ["manuscript mutation validation requires --project-root"]
    for index, item in enumerate(evidence):
        label = f"manuscript_rule_read_evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        path_value = item.get("path")
        path = project_root / path_value if isinstance(path_value, str) else None
        if path is None or not path.is_file():
            errors.append(f"{label} path does not exist")
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if item.get("sha256") != sha256(path):
            errors.append(f"{label} SHA-256 mismatch")
        if item.get("line_count") != line_count:
            errors.append(f"{label} line_count mismatch")
        if item.get("truncated") is not False:
            errors.append(f"{label} truncated must be false")
        if not ranges_cover(line_count, item.get("read_ranges")):
            errors.append(f"{label} read ranges do not cover line 1 through EOF")
    if payload.get("cross_section_propagation") is True:
        for field in ("propagation_matrix", "pre_mutation_baseline"):
            value = payload.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"cross-section propagation requires {field}")
    return errors


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspection_complete(item: dict) -> bool:
    inspection = item.get("inspection")
    if not isinstance(inspection, dict):
        return False
    if inspection.get("status") != "complete" or inspection.get("truncated") is not False:
        return False
    if item.get("representation") == "text":
        return ranges_cover(item.get("line_count", 0), inspection.get("read_ranges"))
    return bool(inspection.get("method") and inspection.get("inspected_units") and inspection.get("findings"))


def validate_decision(decision: dict) -> list[str]:
    errors: list[str] = []
    required = {
        "id", "type", "component", "current_approach", "observed_gap",
        "evidence_for_gap", "necessity", "options", "recommendation",
        "user_decision", "approved_scope", "prohibited_scope",
        "implementation_allowed",
    }
    missing = sorted(required - decision.keys())
    if missing:
        return [f"decision missing fields: {missing}"]
    necessity = decision["necessity"]
    if not isinstance(necessity, dict) or necessity.get("status") not in {
        "not_assessed", "unnecessary", "necessary", "disputed"
    }:
        errors.append("invalid necessity.status")
        necessity = {}
    options = decision["options"]
    if not isinstance(options, list):
        return errors + ["decision options must be a list"]
    option_ids = {item.get("id") for item in options if isinstance(item, dict)}
    if decision["type"] == "model" and "keep_current" not in option_ids:
        errors.append("model decision must evaluate keep_current")
    allowed = (
        necessity.get("status") == "necessary"
        and "keep_current" in option_ids
        and len(option_ids) >= 2
        and decision["user_decision"] == "approved"
        and bool(decision["approved_scope"])
    )
    if bool(decision["implementation_allowed"]) != allowed:
        errors.append(
            "implementation_allowed conflicts with necessity, options, approval, or scope"
        )
    return errors


def validate_recovery(
    payload: dict, project_root: Path | None
) -> list[str]:
    errors: list[str] = []
    gate = payload.get("full_read_gate")
    if gate not in GATES:
        return [f"invalid full_read_gate: {gate!r}"]
    level = payload.get("recovery_level")
    if level is not None and level not in RECOVERY_LEVELS:
        errors.append(f"invalid recovery_level: {level!r}")
    recovery_triggered = payload.get("earliest_open_state") == "S0_RECOVER"
    if level == "R0_INCREMENTAL_CHECKPOINT":
        evidence = payload.get("recovery_evidence")
        if gate != "not_triggered":
            errors.append("R0 must use full_read_gate=not_triggered")
        if not isinstance(evidence, dict) or not evidence.get("checkpoint_identity"):
            errors.append("R0 requires checkpoint_identity")
        if not isinstance(evidence, dict) or not isinstance(evidence.get("changed_paths"), list):
            errors.append("R0 requires changed_paths list")
        return errors
    if level == "R1_HASH_DELTA_RECOVERY":
        evidence = payload.get("recovery_evidence")
        for field in (
            "baseline_manifest_path", "baseline_manifest_sha256",
            "delta_manifest_path", "delta_manifest_sha256", "changed_paths",
        ):
            if not isinstance(evidence, dict) or field not in evidence:
                errors.append(f"R1 requires {field}")
        if not isinstance(evidence, dict) or not isinstance(evidence.get("changed_paths"), list):
            errors.append("R1 changed_paths must be a list")
        if gate not in {"in_progress", "closed"}:
            errors.append("R1 must use an active recovery gate")
        if errors or project_root is None:
            if project_root is None:
                errors.append("R1 requires --project-root")
            return errors
        baseline_path = Path(evidence["baseline_manifest_path"])
        delta_path = Path(evidence["delta_manifest_path"])
        for label, path, expected_hash in (
            ("baseline", baseline_path, evidence["baseline_manifest_sha256"]),
            ("delta", delta_path, evidence["delta_manifest_sha256"]),
        ):
            if not path.is_file():
                errors.append(f"R1 {label} manifest does not exist")
            elif sha256(path) != expected_hash:
                errors.append(f"R1 {label} manifest SHA-256 mismatch")
        if errors:
            return errors
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        delta = json.loads(delta_path.read_text(encoding="utf-8"))
        if baseline.get("unresolved"):
            errors.append("R1 baseline contains unresolved items")
        baseline_files = {item["path"]: item for item in baseline.get("files", [])}
        delta_files = {item["path"]: item for item in delta.get("files", [])}
        live_files = {item["path"]: item for item in inventory(project_root.resolve())["files"]}
        for item in baseline_files.values():
            if item.get("duplicate_of") is None and not inspection_complete(item):
                errors.append(f"R1 baseline canonical inspection incomplete: {item['path']}")
        computed_changed = sorted(
            path for path in set(baseline_files) | set(live_files)
            if path not in baseline_files or path not in live_files
            or baseline_files[path].get("sha256") != live_files[path].get("sha256")
        )
        if sorted(evidence["changed_paths"]) != computed_changed:
            errors.append("R1 changed_paths does not match live hash delta")
        if set(delta_files) != set(live_files):
            errors.append("R1 delta manifest inventory is stale or incomplete")
        baseline_complete_hashes = {
            item.get("sha256") for item in baseline_files.values()
            if item.get("duplicate_of") is None and inspection_complete(item)
        }
        for path, live in live_files.items():
            recorded = delta_files.get(path)
            if recorded is None:
                continue
            for field in ("bytes", "sha256", "representation", "duplicate_of"):
                if recorded.get(field) != live.get(field):
                    errors.append(f"R1 {path}: stale {field}")
            if live.get("duplicate_of") is None and live.get("sha256") not in baseline_complete_hashes:
                if not inspection_complete(recorded):
                    errors.append(f"R1 changed canonical inspection incomplete: {path}")
        if gate == "closed" and errors:
            errors.append("R1 cannot close with unresolved delta evidence")
        return errors
    if recovery_triggered and gate == "not_triggered":
        errors.append("S0_RECOVER cannot use full_read_gate=not_triggered")
    if gate != "closed":
        if recovery_triggered and payload.get("implementation_allowed"):
            errors.append("implementation is prohibited while recovery is open")
        return errors

    evidence = payload.get("recovery_evidence")
    required = {
        "manifest_path", "manifest_sha256", "inventory_file_count",
        "canonical_item_count", "completed_canonical_count", "unresolved_count",
    }
    if not isinstance(evidence, dict):
        return errors + ["closed full_read_gate requires recovery_evidence"]
    missing = sorted(required - evidence.keys())
    if missing:
        return errors + [f"recovery_evidence missing fields: {missing}"]
    if project_root is None:
        return errors + ["closed full_read_gate requires --project-root"]
    manifest_path = Path(evidence["manifest_path"])
    if not manifest_path.is_file():
        return errors + ["recovery manifest does not exist"]
    if sha256(manifest_path) != evidence["manifest_sha256"]:
        errors.append("recovery manifest SHA-256 mismatch")
        return errors
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_errors, counts = verify_manifest(project_root.resolve(), manifest)
    errors.extend(manifest_errors)
    for field in (
        "inventory_file_count", "canonical_item_count",
        "completed_canonical_count", "unresolved_count",
    ):
        if evidence[field] != counts[field]:
            errors.append(f"receipt {field} does not match verified manifest")
    return errors


def validate_receipt(
    payload: dict, project_root: Path | None = None
) -> list[str]:
    errors: list[str] = []
    kind = payload.get("receipt_kind")
    if kind == "end":
        required_end = {
            "receipt_kind", "task", "outputs", "verification", "state_closures",
            "decisions", "affected_downstream", "unresolved", "completion_scope", "status",
            "artifact_disposition",
        }
        missing = sorted(required_end - payload.keys())
        if missing:
            errors.append(f"end receipt missing fields: {missing}")
        if payload.get("completion_scope") not in {"local", "state", "milestone", "full_project"}:
            errors.append("invalid completion_scope")
        if payload.get("status") not in {"complete", "partial", "blocked"}:
            errors.append("invalid end status")
        errors.extend(validate_artifact_disposition(payload, project_root))
        return errors
    required = {
        "receipt_kind", "task", "scope", "components", "state_before",
        "earliest_open_state", "required_inputs", "routed_rules",
        "allowed_actions", "prohibited_actions", "full_read_gate",
        "decisions_required", "implementation_allowed", "substantive_analysis",
        "artifact_plan",
    }
    missing = sorted(required - payload.keys())
    if missing:
        errors.append(f"receipt missing fields: {missing}")
    if kind != "start":
        errors.append("receipt_kind must be start or end")
    if payload.get("earliest_open_state") not in STATES:
        errors.append("invalid earliest_open_state")
    errors.extend(validate_recovery(payload, project_root))
    errors.extend(validate_manuscript_round(payload, project_root))
    errors.extend(validate_artifact_plan(payload))
    decisions = payload.get("decisions_required", [])
    if not isinstance(decisions, list):
        return errors + ["decisions_required must be a list"]
    for decision in decisions:
        if not isinstance(decision, dict):
            errors.append("decision must be an object")
        else:
            errors.extend(validate_decision(decision))
    expected = bool(decisions) and all(
        isinstance(item, dict) and bool(item.get("implementation_allowed"))
        for item in decisions
    )
    if decisions and bool(payload.get("implementation_allowed")) != expected:
        errors.append("receipt implementation_allowed conflicts with decisions")
    if payload.get("earliest_open_state") == "S0_RECOVER" and (
        payload.get("full_read_gate") != "closed"
    ):
        actions = payload.get("allowed_actions")
        if not isinstance(actions, list):
            errors.append("allowed_actions must be a list")
        elif set(actions) - READ_ONLY_RECOVERY_ACTIONS:
            errors.append("S0 mutation prohibition violated")
        if payload.get("implementation_allowed"):
            errors.append("S0 mutation prohibition violated")
    return errors


def validate_project_state(payload: dict) -> list[str]:
    """Validate a component ledger and its mechanically derived project summary."""
    components = payload.get("components")
    summary = payload.get("project_summary")
    if not isinstance(components, dict) or not components:
        return ["project state requires nonempty components"]
    if not isinstance(summary, dict):
        return ["project state requires project_summary"]
    errors: list[str] = []
    ordered = [
        "S0_RECOVER", "S1_INTERPRET", "S2_ASSESS", "S3_DECIDE",
        "S4_SPECIFY", "S5_IMPLEMENT", "S6_VERIFY", "S7_PUBLISH",
    ]
    rank = {state: index for index, state in enumerate(ordered)}
    open_stages: list[str] = []
    for name, component in components.items():
        if not isinstance(component, dict):
            errors.append(f"component {name} must be an object")
            continue
        stage = component.get("stage")
        status = component.get("status")
        if stage not in rank:
            errors.append(f"component {name} has invalid stage")
        if status not in {"not_started", "in_progress", "complete", "blocked"}:
            errors.append(f"component {name} has invalid status")
        if stage in rank and status != "complete":
            open_stages.append(stage)
    derived = min(open_stages, key=rank.get) if open_stages else "S7_PUBLISH"
    if summary.get("earliest_open_state") != derived:
        errors.append("project_summary earliest_open_state is not derived from components")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.receipt.read_text(encoding="utf-8"))
    errors = validate_receipt(payload, args.project_root)
    print(json.dumps({"passed": not errors, "errors": errors}, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
