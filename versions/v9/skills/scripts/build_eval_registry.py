#!/usr/bin/env python3
"""Build the evaluation registry from route and behavioral cases."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    routes = json.loads((SKILL_ROOT / "references" / "route-contract.json").read_text(encoding="utf-8"))["routes"]
    route_cases = json.loads((SKILL_ROOT / "evals" / "routing-cases.json").read_text(encoding="utf-8"))["cases"]
    behavior_cases = json.loads((SKILL_ROOT / "evals" / "behavior-cases.json").read_text(encoding="utf-8"))["cases"]

    route_by_test: dict[str, set[str]] = defaultdict(set)
    caps_by_test: dict[str, set[str]] = defaultdict(set)
    case_by_test: dict[str, set[str]] = defaultdict(set)
    for route in routes:
        for test_id in route["tests"]:
            route_by_test[test_id].add(route["id"])
            caps_by_test[test_id].update(route["capabilities"])
    for case in route_cases:
        for test_id in case.get("eval_ids", []):
            case_by_test[test_id].add(case["id"])
    for case in behavior_cases:
        case_by_test[case["eval_id"]].add(case["id"])

    all_ids = sorted(set(route_by_test) | set(case_by_test))
    evals = []
    for test_id in all_ids:
        evals.append(
            {
                "id": test_id,
                "kind": "behavioral" if test_id.startswith("BEH-") else "routing",
                "routes": sorted(route_by_test[test_id]),
                "capabilities": sorted(caps_by_test[test_id]),
                "cases": sorted(case_by_test[test_id]),
            }
        )
    for test_id, capabilities in {
        "CONTRACT-RECEIPT": ["GOV-RECEIPT-001"],
        "CONTRACT-STATE": ["STATE-TYPED-001"],
        "CONTRACT-ARTIFACT": ["ART-LAZY-001", "ART-PROMOTE-001"],
        "CONTRACT-MIGRATION": ["GOV-OWNER-001", "MNT-ROLLBACK-001"],
    }.items():
        evals.append({"id": test_id, "kind": "contract", "routes": [], "capabilities": capabilities, "cases": []})
    evals.sort(key=lambda item: item["id"])
    out = {"schema_version": "1.0", "release": "9.0.0", "evals": evals}
    (SKILL_ROOT / "evals" / "registry.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"built evaluation registry with {len(evals)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

