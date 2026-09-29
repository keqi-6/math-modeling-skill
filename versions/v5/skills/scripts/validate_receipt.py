#!/usr/bin/env python3
"""Validate V5 start receipts, recovery evidence, and material decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from recovery_manifest import verify_manifest


STATES = {
    "S0_RECOVER", "S1_INTERPRET", "S2_ASSESS", "S3_DECIDE",
    "S4_SPECIFY", "S5_IMPLEMENT", "S6_VERIFY", "S7_PUBLISH",
}
GATES = {"not_triggered", "in_progress", "closed"}
READ_ONLY_RECOVERY_ACTIONS = {
    "enumerate", "hash", "read", "extract", "render", "inspect", "compare",
    "write_external_recovery_evidence",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    recovery_triggered = payload.get("earliest_open_state") == "S0_RECOVER"
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
    required = {
        "receipt_kind", "task", "scope", "components", "state_before",
        "earliest_open_state", "required_inputs", "routed_rules",
        "allowed_actions", "prohibited_actions", "full_read_gate",
        "decisions_required", "implementation_allowed",
    }
    missing = sorted(required - payload.keys())
    if missing:
        errors.append(f"receipt missing fields: {missing}")
    if payload.get("receipt_kind") != "start":
        errors.append("receipt_kind must be start")
    if payload.get("earliest_open_state") not in STATES:
        errors.append("invalid earliest_open_state")
    errors.extend(validate_recovery(payload, project_root))
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
