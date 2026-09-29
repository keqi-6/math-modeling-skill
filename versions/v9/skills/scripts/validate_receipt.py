#!/usr/bin/env python3
"""Validate V9 receipts, including route-to-module consistency."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from resolve_route import resolve_route


SKILL_ROOT = Path(__file__).resolve().parents[1]


def validate_receipt(payload: dict, skill_root: Path = SKILL_ROOT) -> list[str]:
    schema = json.loads((skill_root / "references" / "receipt.schema.json").read_text(encoding="utf-8"))
    errors = [error.message for error in Draft202012Validator(schema).iter_errors(payload)]
    if errors:
        return sorted(errors)

    kind = payload["receipt_kind"]
    if kind == "start":
        try:
            route = resolve_route(
                payload["mode"], payload["object"], payload["action"], payload["route_state"], skill_root
            )
        except (LookupError, RuntimeError) as exc:
            return [str(exc)]
        if payload["route_id"] != route["id"]:
            errors.append(f"route_id must be {route['id']}")
        if payload["routed_modules"] != route["modules"]:
            errors.append("routed_modules must exactly match the resolved direct modules")
        if not route["resolved_write_allowed"] and payload["artifact_plan"]:
            errors.append("read-only route cannot declare artifact creation")
    elif kind == "end":
        routes = {
            route["id"]: route
            for route in json.loads((skill_root / "references" / "route-contract.json").read_text(encoding="utf-8"))["routes"]
        }
        route = routes.get(payload["route_id"])
        if route is None:
            errors.append("unknown route_id")
        elif payload["mode"] in {"advisory_readonly", "project_readonly"} and payload["changed_artifacts"]:
            errors.append("read-only end receipt cannot report changed artifacts")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.receipt.read_text(encoding="utf-8"))
    errors = validate_receipt(payload)
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "receipt_kind": payload["receipt_kind"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

