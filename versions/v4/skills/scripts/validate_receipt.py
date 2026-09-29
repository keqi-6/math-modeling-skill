#!/usr/bin/env python3
"""Validate V4 state and material-decision receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


STATES = {
    "S0_RECOVER",
    "S1_INTERPRET",
    "S2_ASSESS",
    "S3_DECIDE",
    "S4_SPECIFY",
    "S5_IMPLEMENT",
    "S6_VERIFY",
    "S7_PUBLISH",
}


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
        errors.append(f"decision missing fields: {missing}")
        return errors

    necessity = decision["necessity"]
    if not isinstance(necessity, dict) or necessity.get("status") not in {
        "not_assessed", "unnecessary", "necessary", "disputed"
    }:
        errors.append("invalid necessity.status")

    option_ids = {
        item.get("id") for item in decision["options"] if isinstance(item, dict)
    }
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


def validate_receipt(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("earliest_open_state") not in STATES:
        errors.append("invalid earliest_open_state")
    decisions = payload.get("decisions_required", [])
    if not isinstance(decisions, list):
        errors.append("decisions_required must be a list")
        return errors
    decision_errors = []
    for decision in decisions:
        decision_errors.extend(validate_decision(decision))
    errors.extend(decision_errors)
    expected = bool(decisions) and all(
        bool(item.get("implementation_allowed")) for item in decisions
    )
    if decisions and bool(payload.get("implementation_allowed")) != expected:
        errors.append("receipt implementation_allowed conflicts with decisions")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.receipt.read_text(encoding="utf-8"))
    errors = validate_receipt(payload)
    print(json.dumps({"passed": not errors, "errors": errors}, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()

