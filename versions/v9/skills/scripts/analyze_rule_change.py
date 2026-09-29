#!/usr/bin/env python3
"""Validate a Skill change envelope and report its contract impact."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator


SKILL_ROOT = Path(__file__).resolve().parents[1]


def analyze(payload: dict, postflight: bool = False, skill_root: Path = SKILL_ROOT) -> dict:
    schema = json.loads((skill_root / "references" / "receipt.schema.json").read_text(encoding="utf-8"))
    errors = [error.message for error in Draft202012Validator(schema).iter_errors(payload)]
    if payload.get("receipt_kind") != "skill_change":
        errors.append("receipt_kind must be skill_change")

    capabilities = {
        item["id"]: item
        for item in json.loads((skill_root / "references" / "capability-registry.json").read_text(encoding="utf-8"))["capabilities"]
    }
    routes = {
        item["id"]: item
        for item in json.loads((skill_root / "references" / "route-contract.json").read_text(encoding="utf-8"))["routes"]
    }
    eval_ids = {
        item["id"]
        for item in json.loads((skill_root / "evals" / "registry.json").read_text(encoding="utf-8"))["evals"]
    } if (skill_root / "evals" / "registry.json").exists() else set()

    unknown_caps = sorted(set(payload.get("affected_capabilities", [])) - set(capabilities))
    if postflight or payload.get("change_type") != "new_capability":
        if unknown_caps:
            errors.append(f"unknown affected capabilities: {unknown_caps}")
    unknown_routes = sorted(set(payload.get("affected_routes", [])) - set(routes))
    if unknown_routes:
        errors.append(f"unknown affected routes: {unknown_routes}")
    if postflight:
        unknown_tests = sorted(set(payload.get("tests", [])) - eval_ids)
        if unknown_tests:
            errors.append(f"unknown tests after change: {unknown_tests}")

    owner = payload.get("canonical_owner")
    if owner and postflight and not (skill_root / owner.split("#", 1)[0]).exists():
        errors.append(f"canonical owner does not exist: {owner}")

    risk = payload.get("risk_level")
    compatibility = payload.get("compatibility")
    if risk in {"L3", "L4"} and compatibility == "backward_compatible":
        errors.append("L3/L4 changes cannot be assumed backward compatible without an explicit behavior_change or breaking classification")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": sorted(errors),
        "impact": {
            "capabilities": payload.get("affected_capabilities", []),
            "routes": payload.get("affected_routes", []),
            "canonical_owner": owner,
            "tests": payload.get("tests", []),
            "requires_fresh_invocation": risk in {"L2", "L3", "L4"},
            "requires_rollback_point": risk in {"L3", "L4"},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("change", type=Path)
    parser.add_argument("--postflight", action="store_true")
    args = parser.parse_args()
    result = analyze(json.loads(args.change.read_text(encoding="utf-8")), args.postflight)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

