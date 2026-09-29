#!/usr/bin/env python3
"""Behavioral regression tests for V4 permission decisions."""

from __future__ import annotations

from validate_receipt import validate_decision


def decision(
    *,
    necessity: str,
    options: list[str],
    approval: str,
    scope: str | None,
    allowed: bool,
) -> dict:
    return {
        "id": "D-MODEL-1",
        "type": "model",
        "component": "q1",
        "current_approach": "descriptive baseline",
        "observed_gap": "external rubric mentions fitted functions",
        "evidence_for_gap": ["official rubric"],
        "necessity": {
            "status": necessity,
            "consequence_if_unchanged": "requires assessment",
        },
        "options": [{"id": item} for item in options],
        "recommendation": None,
        "user_decision": approval,
        "approved_scope": scope,
        "prohibited_scope": None,
        "implementation_allowed": allowed,
    }


def expect_invalid(name: str, payload: dict) -> None:
    errors = validate_decision(payload)
    if not errors:
        raise AssertionError(f"{name}: unsafe decision unexpectedly passed")


def expect_valid(name: str, payload: dict) -> None:
    errors = validate_decision(payload)
    if errors:
        raise AssertionError(f"{name}: {errors}")


def main() -> None:
    # The observed V3 failure: rubric language does not prove necessity or authorize a model.
    expect_invalid(
        "rubric_to_model_jump",
        decision(
            necessity="not_assessed",
            options=["major_change"],
            approval="not_requested",
            scope=None,
            allowed=True,
        ),
    )
    # “Continue” is represented by absence of an explicit approved decision.
    expect_invalid(
        "continue_is_not_approval",
        decision(
            necessity="necessary",
            options=["keep_current", "major_change"],
            approval="awaiting",
            scope=None,
            allowed=True,
        ),
    )
    # A successful candidate still needs a no-change comparison and approval.
    expect_invalid(
        "verified_candidate_not_auto_promoted",
        decision(
            necessity="necessary",
            options=["major_change"],
            approval="approved",
            scope="candidate model",
            allowed=True,
        ),
    )
    # If no change is sufficient, implementation must remain false.
    expect_valid(
        "no_change_sufficient",
        decision(
            necessity="unnecessary",
            options=["keep_current", "minimal_change"],
            approval="rejected",
            scope=None,
            allowed=False,
        ),
    )
    # The only positive model-change path.
    expect_valid(
        "explicit_scoped_approval",
        decision(
            necessity="necessary",
            options=["keep_current", "minimal_change", "major_change"],
            approval="approved",
            scope="Q1 auxiliary fitted model for sensitivity only",
            allowed=True,
        ),
    )
    print("PASS: 5 behavioral permission regressions")


if __name__ == "__main__":
    main()

