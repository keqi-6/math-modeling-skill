#!/usr/bin/env python3
"""Validate source coverage and migration closure of the V7 capability ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_capability_ledger import build


def validate(source_root: Path, ledger_path: Path, require_closed: bool) -> list[str]:
    errors: list[str] = []
    live = build(source_root)
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    skill_root = Path(__file__).resolve().parents[1]
    registry_path = skill_root / "references/capability-test-registry.json"
    registered_tests: set[str] = set()
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        for item in registry.get("tests", []):
            test_id = item.get("test_id")
            if isinstance(test_id, str):
                registered_tests.add(test_id)
    elif require_closed:
        errors.append("capability test registry is missing")
    if ledger.get("schema_version") != "1.0":
        errors.append("unsupported schema_version")
    if ledger.get("source_root") != source_root.resolve().as_posix():
        errors.append("source_root mismatch")
    if ledger.get("source_snapshot") != live.get("source_snapshot"):
        errors.append("source snapshot is stale")

    expected = {
        (entry["source_file"], tuple(entry["source_lines"]), entry["source_sha256"], entry["source_text"])
        for entry in live["entries"]
    }
    entries = ledger.get("entries")
    if not isinstance(entries, list):
        return errors + ["entries must be a list"]
    actual = set()
    ids: set[str] = set()
    for index, entry in enumerate(entries):
        prefix = f"entries[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        capability_id = entry.get("capability_id")
        if not isinstance(capability_id, str):
            errors.append(f"{prefix}: capability_id missing")
        elif capability_id in ids:
            errors.append(f"{prefix}: duplicate capability_id {capability_id}")
        else:
            ids.add(capability_id)
        try:
            key = (
                entry["source_file"], tuple(entry["source_lines"]),
                entry["source_sha256"], entry["source_text"],
            )
            actual.add(key)
        except (KeyError, TypeError):
            errors.append(f"{prefix}: incomplete source identity")
        if require_closed:
            status = entry.get("review_status")
            if status == "unreviewed":
                errors.append(f"{prefix}: remains unreviewed")
            if status == "confirmed_capability":
                if entry.get("strength") == "unclassified":
                    errors.append(f"{prefix}: capability strength unclassified")
                if not entry.get("v7_owner"):
                    errors.append(f"{prefix}: capability has no V7 owner")
                if entry.get("treatment") == "unclassified":
                    errors.append(f"{prefix}: capability treatment unclassified")
                if not entry.get("trigger_ids"):
                    errors.append(f"{prefix}: capability has no trigger")
                if not entry.get("test_ids"):
                    errors.append(f"{prefix}: capability has no test")
                else:
                    unknown_tests = set(entry["test_ids"]) - registered_tests
                    if unknown_tests:
                        errors.append(f"{prefix}: capability cites unknown tests {sorted(unknown_tests)}")
                owner = entry.get("v7_owner")
                if entry.get("treatment") == "preserve" and isinstance(owner, str):
                    owner_path = skill_root / owner
                    if not owner_path.is_file() or entry.get("source_text") not in owner_path.read_text(encoding="utf-8"):
                        errors.append(f"{prefix}: preserve capability is absent from V7 owner")
                if entry.get("treatment") == "rewrite" and "T-V7-REWRITE-CONTRACT" not in entry.get("test_ids", []):
                    errors.append(f"{prefix}: rewrite lacks V7 rewrite contract test")
            if entry.get("treatment") in {"merge", "remove"}:
                if not entry.get("rationale"):
                    errors.append(f"{prefix}: merge/remove lacks rationale")
                if not entry.get("test_ids"):
                    errors.append(f"{prefix}: merge/remove lacks regression test")
                if entry.get("treatment") == "merge" and not entry.get("merged_into"):
                    errors.append(f"{prefix}: merge lacks target capability")
    missing = expected - actual
    extra = actual - expected
    if missing:
        errors.append(f"ledger misses {len(missing)} source blocks")
    if extra:
        errors.append(f"ledger contains {len(extra)} stale or altered source blocks")
    if len(actual) != len(entries):
        errors.append("duplicate source block entries detected")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--require-closed", action="store_true")
    parser.add_argument("--max-errors", type=int, default=20)
    args = parser.parse_args()
    errors = validate(args.source_root.resolve(), args.ledger, args.require_closed)
    print(json.dumps({
        "passed": not errors,
        "mode": "closed" if args.require_closed else "coverage",
        "error_count": len(errors),
        "errors_shown": errors[:max(args.max_errors, 0)],
        "errors_omitted": max(len(errors) - max(args.max_errors, 0), 0),
    }, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
