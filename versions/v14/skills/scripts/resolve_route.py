#!/usr/bin/env python3
"""Resolve a V11 agent-authored multi-step semantic plan.

The original request is retained and hashed for auditability.  It is never
classified here: language understanding belongs to the agent that submits the
semantic plan.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from lib_v10 import ContractError, json_output, sha256_text
from lib_v11 import resolve


def load_plan_file(path: str) -> dict[str, Any]:
    try:
        if path == "-":
            value = json.load(sys.stdin)
        else:
            with Path(path).open("r", encoding="utf-8") as handle:
                value = json.load(handle)
    except FileNotFoundError as exc:
        raise ContractError(f"missing semantic plan: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid semantic plan JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("semantic plan must be a JSON object")
    return value


def load_inline_plan(payload: str) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid --plan-json: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError("semantic plan must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--plan", help="Semantic plan JSON file, or - for stdin")
    source.add_argument("--plan-json", help="Inline semantic plan JSON")
    source.add_argument(
        "--request",
        help="Deprecated V10 argument; accepted only to return semantic_plan_required",
    )
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()

    if args.request is not None:
        json_output({
            "schema_version": "11.0",
            "status": "blocked",
            "request": args.request,
            "request_hash": sha256_text(args.request),
            "error": "semantic_plan_required",
            "message": "V11 does not classify raw language; submit --plan or --plan-json.",
        })
        return 2
    if args.plan is None and args.plan_json is None:
        json_output({
            "schema_version": "11.0", "status": "blocked",
            "error": "semantic_plan_required",
        })
        return 2
    try:
        plan = load_plan_file(args.plan) if args.plan is not None else load_inline_plan(args.plan_json)
        result = resolve(plan, args.project_root)
    except (ContractError, OSError, ValueError) as exc:
        json_output({
            "schema_version": "11.0", "status": "blocked", "errors": [str(exc)]
        })
        return 2
    json_output(result)
    if result["status"] == "resolved":
        return 0
    return 3 if result["status"] == "partial" else 2


if __name__ == "__main__":
    raise SystemExit(main())
