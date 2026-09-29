#!/usr/bin/env python3
"""Validate deterministic one-hop routing and complete rule reachability."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REQUIRED_TRIGGER_FIELDS = {
    "trigger_id", "when", "exclude_when", "stages", "primary_owner",
    "required_rules", "required_approval", "expected_evidence", "rollback",
}


def validate(skill_root: Path, registry_path: Path) -> list[str]:
    errors: list[str] = []
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0":
        errors.append("unsupported schema_version")
    policy = payload.get("policy", {})
    if policy.get("max_reference_depth") != 1:
        errors.append("max_reference_depth must be 1")
    triggers = payload.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        return errors + ["triggers must be a non-empty list"]

    all_rules = {
        path.relative_to(skill_root).as_posix()
        for path in (skill_root / "rules").glob("*.md")
    }
    reachable: set[str] = set()
    trigger_ids: set[str] = set()
    for index, trigger in enumerate(triggers):
        prefix = f"triggers[{index}]"
        if not isinstance(trigger, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        missing = REQUIRED_TRIGGER_FIELDS - set(trigger)
        if missing:
            errors.append(f"{prefix}: missing fields {sorted(missing)}")
        trigger_id = trigger.get("trigger_id")
        if trigger_id in trigger_ids:
            errors.append(f"{prefix}: duplicate trigger_id {trigger_id}")
        elif isinstance(trigger_id, str):
            trigger_ids.add(trigger_id)
        if not trigger.get("when") or not trigger.get("exclude_when"):
            errors.append(f"{prefix}: trigger and exclusion must both be explicit")
        if not trigger.get("required_approval") or not trigger.get("rollback"):
            errors.append(f"{prefix}: approval or rollback missing")
        if not trigger.get("expected_evidence"):
            errors.append(f"{prefix}: expected evidence missing")

        routed = list(trigger.get("required_rules", []))
        for condition in trigger.get("conditional_rules", []):
            if not condition.get("when"):
                errors.append(f"{prefix}: conditional route lacks condition")
            routed.extend(condition.get("rules", []))
        for pattern in trigger.get("required_rule_globs", []):
            if pattern != "rules/*.md":
                errors.append(f"{prefix}: unsupported or deep rule glob {pattern}")
                continue
            routed.extend(sorted(all_rules))
        for relative in routed:
            if relative not in all_rules:
                errors.append(f"{prefix}: missing routed rule {relative}")
            else:
                reachable.add(relative)
        owner = trigger.get("primary_owner")
        if owner != "SKILL.md" and owner not in routed:
            errors.append(f"{prefix}: primary_owner is not in its route")

    if policy.get("every_rule_must_be_reachable") is not True:
        errors.append("every_rule_must_be_reachable must be true")
    unreachable = sorted(all_rules - reachable)
    if unreachable:
        errors.append(f"unreachable rules: {unreachable}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", type=Path)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--max-errors", type=int, default=20)
    args = parser.parse_args()
    errors = validate(args.skill_root.resolve(), args.registry)
    shown = max(args.max_errors, 0)
    print(json.dumps({
        "passed": not errors,
        "error_count": len(errors),
        "errors_shown": errors[:shown],
        "errors_omitted": max(len(errors) - shown, 0),
    }, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
