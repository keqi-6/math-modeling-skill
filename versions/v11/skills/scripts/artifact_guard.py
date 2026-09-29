#!/usr/bin/env python3
"""Reject redundant or unowned project artifact proposals before creation."""

from __future__ import annotations

import argparse
from pathlib import Path

from lib_v10 import json_output, load_json
from state_v11 import load_state, validate_artifact_proposal


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--proposal", type=Path, required=True)
    args = parser.parse_args()
    proposal = load_json(args.proposal)
    state, state_errors = load_state(args.project_root)
    fatal_state_errors = [item for item in state_errors if item != "state_missing"]
    errors = fatal_state_errors + validate_artifact_proposal(proposal, args.project_root, state)
    result = {
        "schema_version": "11.0",
        "status": "admitted" if not errors else "rejected",
        "proposal": proposal,
        "errors": errors,
    }
    json_output(result)
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
