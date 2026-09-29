#!/usr/bin/env python3
"""Resolve and validate a structured V9 route selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_contract(skill_root: Path = SKILL_ROOT) -> dict[str, Any]:
    return json.loads((skill_root / "references" / "route-contract.json").read_text(encoding="utf-8"))


def resolve_route(
    mode: str,
    object_name: str,
    action: str,
    state: str,
    skill_root: Path = SKILL_ROOT,
) -> dict[str, Any]:
    contract = load_contract(skill_root)
    matches = [
        route
        for route in contract["routes"]
        if mode in route["modes"]
        and object_name == route["object"]
        and action in route["actions"]
        and state in route["states"]
    ]
    if not matches:
        raise LookupError(
            f"no route for mode={mode}, object={object_name}, action={action}, state={state}"
        )
    if len(matches) != 1:
        raise RuntimeError(f"ambiguous route selection: {[route['id'] for route in matches]}")
    route = dict(matches[0])
    state_contract = json.loads(
        (skill_root / "references" / "state-contract.json").read_text(encoding="utf-8")
    )
    mode_writes = bool(state_contract["execution_modes"][mode]["writes"])
    declared = route["write_allowed"]
    route["resolved_write_allowed"] = mode_writes and declared is not False
    recovery = contract.get("recovery_policy", {})
    route["recovery_policy"] = recovery.get("overrides", {}).get(
        route["id"], recovery.get("default", "if_project_state_exists")
    )
    if state == "UNINITIALIZED":
        route["recovery_policy"] = "not_applicable"
    route["loaded_modules"] = list(route["modules"])
    route["optional_modules_available"] = list(route.get("optional_modules", []))
    return route


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True)
    parser.add_argument("--object", dest="object_name", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--state", required=True)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    try:
        route = resolve_route(args.mode, args.object_name, args.action, args.state)
    except LookupError as exc:
        print(json.dumps({"status": "no_match", "error": str(exc)}, ensure_ascii=False))
        return 2
    except RuntimeError as exc:
        print(json.dumps({"status": "ambiguous", "error": str(exc)}, ensure_ascii=False))
        return 3
    print(json.dumps(route, ensure_ascii=False, indent=None if args.compact else 2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
