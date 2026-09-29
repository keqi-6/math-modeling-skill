#!/usr/bin/env python3
"""Run the focused V11 manuscript closure and semantic-plan behavior suite."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from lib_v10 import SKILL_ROOT, json_output, load_json
from run_behavior_evals import run as run_behavior


CONTRACT_PATH = Path("references/manuscript-change-closure.json")
REGISTRY_PATH = Path("evals/manuscript-behavior-cases.json")
ACTION_WITNESSES = {
    "fix_typo": "typo",
    "polish_paragraph": "paragraph_polish",
    "render": "render_output",
    "typeset": "render_output",
    "layout_check": "layout_check",
    "structure": "structure_only",
}


def _nonempty_change_set(step: dict[str, Any]) -> bool:
    change_set = step.get("change_set")
    return isinstance(change_set, dict) and any(
        bool(change_set.get(field)) for field in ("paths", "facets", "claim_refs")
    )


def validate_extensions(skill_root: Path) -> list[str]:
    """Validate closure data that is intentionally not a runtime hard gate."""
    contract = load_json(skill_root / CONTRACT_PATH)
    registry = load_json(skill_root / REGISTRY_PATH)
    closures = contract.get("closures", {})
    errors: list[str] = []

    policy = contract.get("rule_count_telemetry_policy", {})
    if policy.get("runtime_effect") != "none":
        errors.append("rule_count_telemetry_runtime_effect")
    for name, closure in closures.items():
        if "max_total_rule_count" in closure:
            errors.append(f"runtime_rule_count_gate_present:{name}")
        telemetry = closure.get("rule_count_telemetry")
        if not isinstance(telemetry, dict):
            errors.append(f"rule_count_telemetry_missing:{name}")
            continue
        limit = telemetry.get("expected_max_total_rule_count")
        if not isinstance(limit, int) or limit < 0:
            errors.append(f"rule_count_telemetry_limit_invalid:{name}")
        if telemetry.get("runtime_effect") != "none":
            errors.append(f"rule_count_telemetry_not_observational:{name}")

    section = closures.get("section_checkpoint", {})
    if "method" in section.get("required_facets", []):
        errors.append("section_checkpoint_fixed_method_facet")
    section_overlays = section.get("derived_expected_rule_overlays_by_legacy_event", {})
    if section_overlays.get("method_section_write") != ["MAN.CONTENT.METHOD"]:
        errors.append("section_checkpoint_method_overlay_missing")
    if section_overlays.get("result_section_write") != ["MAN.CONTENT.RESULT"]:
        errors.append("section_checkpoint_result_overlay_missing")

    multi = closures.get("multi_file_substantive", {})
    minimum_paths = multi.get("change_set_constraints", {}).get("minimum_paths")
    if not isinstance(minimum_paths, int) or minimum_paths < 2:
        errors.append("multi_file_minimum_paths_contract")

    cases = registry.get("cases", [])
    witnessed: dict[tuple[str, str], bool] = {
        (action, change_class): False
        for action, change_class in ACTION_WITNESSES.items()
    }
    multi_witnesses = 0
    mixed_close: dict[str, Any] | None = None
    for case in cases:
        for step in case.get("plan", {}).get("steps", []):
            action = step.get("action")
            change_class = step.get("facts", {}).get("change_class")
            key = (str(action), str(change_class))
            if key in witnessed:
                witnessed[key] = True
            if change_class == "multi_file_substantive":
                multi_witnesses += 1
                paths = step.get("change_set", {}).get("paths", [])
                if isinstance(minimum_paths, int) and len(paths) < minimum_paths:
                    errors.append(f"multi_file_case_too_few_paths:{case.get('id')}")
            if case.get("id") == "BEH.V11.MAN.MIXED.CLOSE_S6.THEN_WRITE" and action == "close_s6":
                mixed_close = step

    for (action, change_class), present in witnessed.items():
        closure = closures.get(change_class, {})
        if action not in closure.get("allowed_actions", []):
            errors.append(f"closure_action_not_declared:{action}:{change_class}")
        if not present:
            errors.append(f"closure_action_witness_missing:{action}:{change_class}")
    if multi_witnesses < 1:
        errors.append("multi_file_behavior_witness_missing")

    if mixed_close is None:
        errors.append("mixed_s6_close_witness_missing")
    else:
        if mixed_close.get("events") != ["s6_close"]:
            errors.append("mixed_s6_close_not_minimal_event")
        if mixed_close.get("state_effect") != {
            "component_id": "q1", "from": "S6", "to": "S7"
        }:
            errors.append("mixed_s6_close_state_effect_missing")
        if not _nonempty_change_set(mixed_close):
            errors.append("mixed_s6_close_change_set_empty")

    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    skill_root = args.root.resolve()

    report = run_behavior(
        skill_root,
        set(args.case) if args.case else None,
        [REGISTRY_PATH],
    )
    extension_errors = validate_extensions(skill_root)
    extension_result = {
        "id": "CONTRACT:MANUSCRIPT_ACTION_CLOSURE_EXTENSIONS",
        "status": "pass" if not extension_errors else "fail",
        "failures": extension_errors,
    }
    report["results"].insert(0, extension_result)
    report["total"] += 1
    if extension_errors:
        report["failed"] += 1
        report["status"] = "fail"
    else:
        report["passed"] += 1
    report["driver"] = "focused_manuscript_semantic_plans_and_contract_invariants"
    json_output(report)
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
