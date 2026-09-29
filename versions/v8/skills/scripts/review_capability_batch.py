#!/usr/bin/env python3
"""Record a conservative human-reviewed preservation batch in the capability ledger.

The reviewer must fully read every named source file before running this script. The script
classifies headings/separators as context and preserves every other block as a capability unit.
It intentionally leaves test_ids empty: behavioral tests must be assigned separately.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from build_capability_ledger import build


def infer_strength(text: str) -> str:
    if any(token in text for token in ("禁止", "不得", "不能", "不可", "严禁")):
        return "prohibition"
    if any(token in text for token in ("必须", "只有", "均为 A", "硬门")):
        return "must"
    if any(token in text for token in ("应当", "应该", "应")):
        return "should"
    if any(token in text for token in ("可以", "可用", "允许")):
        return "may"
    return "guidance"


def route_map(registry: dict, all_rules: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = defaultdict(list)
    for trigger in registry["triggers"]:
        routed = list(trigger.get("required_rules", []))
        for condition in trigger.get("conditional_rules", []):
            routed.extend(condition.get("rules", []))
        if "rules/*.md" in trigger.get("required_rule_globs", []):
            routed.extend(all_rules)
        for relative in sorted(set(routed)):
            result[relative].append(trigger["trigger_id"])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("routing_registry", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--files", nargs="+", required=True)
    args = parser.parse_args()

    source_root = args.source_root.resolve()
    live = build(source_root)
    payload = json.loads(args.ledger.read_text(encoding="utf-8"))
    if payload.get("source_snapshot") != live.get("source_snapshot"):
        raise SystemExit("ledger source snapshot is stale; do not record review")
    registry = json.loads(args.routing_registry.read_text(encoding="utf-8"))
    all_rules = sorted(
        path.relative_to(source_root).as_posix()
        for path in (source_root / "rules").glob("*.md")
    )
    routes = route_map(registry, all_rules)
    requested = set(args.files)
    # The ledger covers controller, rules, schemas, and migration references.  Restrict
    # selection to the current snapshotted source set instead of making non-rule entries
    # permanently unreviewable.
    known_sources = {entry["source_file"] for entry in payload["entries"]}
    unknown = requested - known_sources
    if unknown:
        raise SystemExit(f"unknown review files: {sorted(unknown)}")

    reviewed = 0
    capabilities = 0
    contexts = 0
    for entry in payload["entries"]:
        if entry["source_file"] not in requested:
            continue
        if entry["review_status"] != "unreviewed":
            raise SystemExit(f"already reviewed: {entry['capability_id']}")
        reviewed += 1
        if entry["candidate_kind"] in {"heading", "separator", "frontmatter"}:
            entry["review_status"] = "context_only"
            entry["strength"] = "guidance"
            entry["v7_owner"] = entry["source_file"]
            entry["treatment"] = "preserve"
            entry["rationale"] = f"Structural context retained; full-file review {args.review_id}."
            contexts += 1
        else:
            entry["review_status"] = "confirmed_capability"
            entry["strength"] = infer_strength(entry["source_text"])
            entry["v7_owner"] = entry["source_file"]
            entry["treatment"] = "preserve"
            entry["rationale"] = f"Conservative semantic preservation after full-file review {args.review_id}."
            entry["trigger_ids"] = routes.get(entry["source_file"], [])
            capabilities += 1
        entry["test_ids"] = []
    if reviewed == 0:
        raise SystemExit("review batch selected no ledger entries")
    args.ledger.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "review_id": args.review_id,
        "files": sorted(requested),
        "reviewed_blocks": reviewed,
        "confirmed_capabilities": capabilities,
        "context_blocks": contexts,
        "behavior_tests_assigned": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
