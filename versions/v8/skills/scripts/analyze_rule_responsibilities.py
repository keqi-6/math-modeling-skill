#!/usr/bin/env python3
"""Create a conservative responsibility-overlap report without changing rules."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from build_capability_ledger import build


def normalize(text: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"^[#>*\-\d.、（）()]+", "", text)
    return text.casefold()


def family_for(relative: str) -> str:
    match = re.search(r"rules/(\d+)-", relative)
    if not match:
        return "controller_or_reference"
    number = int(match.group(1))
    if number <= 18:
        return "detailed_procedure"
    if number <= 29:
        return "acceptance_crosscheck"
    if number <= 35:
        return "minimum_crosscheck"
    return "native_repair"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("routing_registry", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    ledger = build(source_root)
    registry = json.loads(args.routing_registry.read_text(encoding="utf-8"))

    routes_by_file: dict[str, list[str]] = defaultdict(list)
    all_rules = sorted(
        path.relative_to(source_root).as_posix()
        for path in (source_root / "rules").glob("*.md")
    )
    for trigger in registry["triggers"]:
        routed = list(trigger.get("required_rules", []))
        for condition in trigger.get("conditional_rules", []):
            routed.extend(condition.get("rules", []))
        if "rules/*.md" in trigger.get("required_rule_globs", []):
            routed.extend(all_rules)
        for relative in sorted(set(routed)):
            routes_by_file[relative].append(trigger["trigger_id"])

    exact_groups: dict[str, list[dict]] = defaultdict(list)
    headings: dict[str, list[dict]] = defaultdict(list)
    file_stats: dict[str, dict] = {}
    for entry in ledger["entries"]:
        relative = entry["source_file"]
        if not relative.startswith("rules/"):
            continue
        stats = file_stats.setdefault(relative, {
            "family": family_for(relative), "block_count": 0,
            "heading_count": 0, "trigger_ids": routes_by_file.get(relative, []),
        })
        stats["block_count"] += 1
        normalized = normalize(entry["source_text"])
        if entry["candidate_kind"] == "heading":
            stats["heading_count"] += 1
            if len(normalized) >= 4:
                headings[normalized].append({
                    "file": relative, "lines": entry["source_lines"],
                    "text": entry["source_text"],
                })
        elif len(normalized) >= 24:
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            exact_groups[digest].append({
                "file": relative, "lines": entry["source_lines"],
                "text": entry["source_text"],
            })

    repeated_blocks = [
        {"normalized_sha256": digest, "occurrences": items}
        for digest, items in exact_groups.items()
        if len({item["file"] for item in items}) > 1
    ]
    repeated_headings = [
        {"normalized_heading": heading, "occurrences": items}
        for heading, items in headings.items()
        if len({item["file"] for item in items}) > 1
    ]
    uncovered = sorted(set(all_rules) - set(routes_by_file))
    payload = {
        "schema_version": "1.0",
        "source_snapshot": ledger["source_snapshot"],
        "method": {
            "exact_overlap_only": True,
            "deletion_authority": False,
            "warning": "Absence from this report does not prove absence of semantic overlap."
        },
        "file_stats": file_stats,
        "exact_cross_file_block_groups": sorted(
            repeated_blocks,
            key=lambda item: (-len(item["occurrences"]), item["normalized_sha256"]),
        ),
        "repeated_heading_groups": sorted(
            repeated_headings,
            key=lambda item: (-len(item["occurrences"]), item["normalized_heading"]),
        ),
        "unreachable_rules": uncovered,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": args.output.as_posix(),
        "rule_count": len(file_stats),
        "exact_cross_file_block_groups": len(repeated_blocks),
        "repeated_heading_groups": len(repeated_headings),
        "unreachable_rule_count": len(uncovered),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
