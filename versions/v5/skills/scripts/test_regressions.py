#!/usr/bin/env python3
"""Behavioral regressions for V5 recovery and decision permission gates."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from recovery_manifest import inventory
from validate_receipt import validate_decision, validate_receipt


def decision(
    *, necessity: str, options: list[str], approval: str,
    scope: str | None, allowed: bool,
) -> dict:
    return {
        "id": "D-MODEL-1", "type": "model", "component": "q1",
        "current_approach": "descriptive baseline",
        "observed_gap": "external rubric mentions fitted functions",
        "evidence_for_gap": ["official rubric"],
        "necessity": {"status": necessity, "consequence_if_unchanged": "assess"},
        "options": [{"id": item} for item in options],
        "recommendation": None, "user_decision": approval,
        "approved_scope": scope, "prohibited_scope": None,
        "implementation_allowed": allowed,
    }


def complete_manifest(root: Path) -> tuple[Path, dict]:
    manifest = inventory(root)
    for item in manifest["files"]:
        if item["duplicate_of"] is not None:
            continue
        if item["representation"] == "text":
            count = item["line_count"]
            item["inspection"] = {
                "status": "complete", "truncated": False,
                "read_ranges": [] if count == 0 else [[1, count]],
            }
        else:
            item["inspection"] = {
                "status": "complete", "truncated": False,
                "method": "native test inspection", "inspected_units": ["all"],
                "findings": "test fixture inspected",
            }
    path = root.parent / "recovery_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path, manifest


def recovery_receipt(root: Path, path: Path, manifest: dict) -> dict:
    canonical = [item for item in manifest["files"] if item["duplicate_of"] is None]
    return {
        "receipt_kind": "start", "task": "continue", "scope": ".",
        "components": ["project"], "state_before": "unknown",
        "earliest_open_state": "S0_RECOVER", "required_inputs": [],
        "routed_rules": [], "allowed_actions": ["read"],
        "prohibited_actions": ["mutate"], "full_read_gate": "closed",
        "recovery_evidence": {
            "manifest_path": path.as_posix(),
            "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "inventory_file_count": len(manifest["files"]),
            "canonical_item_count": len(canonical),
            "completed_canonical_count": len(canonical),
            "unresolved_count": 0,
        },
        "decisions_required": [], "implementation_allowed": False,
    }


def expect_invalid(name: str, errors: list[str]) -> None:
    if not errors:
        raise AssertionError(f"{name}: unsafe payload unexpectedly passed")


def expect_valid(name: str, errors: list[str]) -> None:
    if errors:
        raise AssertionError(f"{name}: {errors}")


def main() -> None:
    expect_invalid("rubric_to_model_jump", validate_decision(decision(
        necessity="not_assessed", options=["major_change"],
        approval="not_requested", scope=None, allowed=True,
    )))
    expect_invalid("continue_is_not_approval", validate_decision(decision(
        necessity="necessary", options=["keep_current", "major_change"],
        approval="awaiting", scope=None, allowed=True,
    )))
    expect_invalid("verified_candidate_not_auto_promoted", validate_decision(decision(
        necessity="necessary", options=["major_change"],
        approval="approved", scope="candidate", allowed=True,
    )))
    expect_valid("explicit_scoped_approval", validate_decision(decision(
        necessity="necessary", options=["keep_current", "major_change"],
        approval="approved", scope="Q1 sensitivity only", allowed=True,
    )))

    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        root = base / "project"
        root.mkdir()
        (root / "a.md").write_text("one\ntwo\n", encoding="utf-8")
        (root / "copy.md").write_text("one\ntwo\n", encoding="utf-8")
        path, manifest = complete_manifest(root)
        valid = recovery_receipt(root, path, manifest)
        expect_valid("valid_recovery_closure", validate_receipt(valid, root))

        custom = dict(valid)
        custom["full_read_gate"] = "closed_by_prior_audit"
        expect_invalid("custom_gate_value", validate_receipt(custom, root))

        missing = dict(valid)
        missing.pop("recovery_evidence")
        expect_invalid("closed_without_evidence", validate_receipt(missing, root))

        mismatch = json.loads(json.dumps(valid))
        mismatch["recovery_evidence"]["completed_canonical_count"] += 1
        expect_invalid("count_mismatch", validate_receipt(mismatch, root))

        open_mutation = dict(valid)
        open_mutation["full_read_gate"] = "in_progress"
        open_mutation["implementation_allowed"] = True
        open_mutation["allowed_actions"] = ["read", "modify_project"]
        expect_invalid("s0_mutation", validate_receipt(open_mutation, root))

        truncated_manifest = json.loads(json.dumps(manifest))
        canonical = next(
            item for item in truncated_manifest["files"] if item["duplicate_of"] is None
        )
        canonical["inspection"]["truncated"] = True
        path.write_text(
            json.dumps(truncated_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        truncated = recovery_receipt(root, path, truncated_manifest)
        expect_invalid("truncated_output", validate_receipt(truncated, root))

        path, manifest = complete_manifest(root)
        unresolved_manifest = json.loads(json.dumps(manifest))
        unresolved_manifest["unresolved"] = [{"path": "unknown.bin"}]
        path.write_text(
            json.dumps(unresolved_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        unresolved = recovery_receipt(root, path, unresolved_manifest)
        unresolved["recovery_evidence"]["unresolved_count"] = 1
        expect_invalid("unresolved_item", validate_receipt(unresolved, root))

        path, manifest = complete_manifest(root)
        stale = recovery_receipt(root, path, manifest)
        (root / "new.md").write_text("new\n", encoding="utf-8")
        expect_invalid("stale_inventory", validate_receipt(stale, root))

    print("PASS: 12 behavioral permission and recovery regressions")


if __name__ == "__main__":
    main()
