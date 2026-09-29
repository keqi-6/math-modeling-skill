#!/usr/bin/env python3
"""Prove that V5 directly integrates every V1 rule source and reusable tool."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_line_subsequence(original: Path, active: Path) -> bool:
    source_lines = original.read_text(encoding="utf-8").splitlines()
    active_lines = iter(active.read_text(encoding="utf-8").splitlines())
    return all(any(candidate == line for candidate in active_lines) for line in source_lines)


def validate(root: Path = ROOT, source_v1: Path | None = None) -> list[str]:
    errors: list[str] = []
    map_path = root / "references/v1-integration-map.json"
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read integration map: {exc}"]
    if payload.get("schema_version") != "1.0":
        errors.append("unsupported integration-map schema")
    if payload.get("coverage_unit") != "source-preserving-active-file":
        errors.append("coverage_unit must be source-preserving-active-file")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return errors + ["entries must be a list"]

    mapped_sources: set[tuple[str, str]] = set()
    mapped_owners: set[str] = set()
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {index} is not an object")
            continue
        required = {"source", "sha256", "kind", "route", "owner", "status"}
        missing = sorted(required - entry.keys())
        if missing:
            errors.append(f"entry {index} missing fields: {missing}")
            continue
        kind = entry["kind"]
        source = entry["source"]
        owner = entry["owner"]
        key = (kind, source)
        if key in mapped_sources:
            errors.append(f"duplicate mapping: {kind}:{source}")
        mapped_sources.add(key)
        if owner in mapped_owners:
            errors.append(f"duplicate active owner: {owner}")
        mapped_owners.add(owner)
        if kind == "rule":
            original = source_v1 / source if source_v1 is not None else None
            expected_status = "exact_integrated_active"
        elif kind == "tool":
            original = source_v1 / "scripts" / source if source_v1 is not None else None
            expected_status = "exact_integrated_tool"
        else:
            errors.append(f"{source}: invalid kind {kind!r}")
            continue
        allowed_statuses = {expected_status}
        if kind == "rule" and "base_sha256" in entry:
            allowed_statuses.add("superset_integrated_active")
        if entry["status"] not in allowed_statuses:
            errors.append(f"{source}: invalid integration status")
        if not isinstance(entry["route"], str) or not entry["route"].strip():
            errors.append(f"{source}: empty route")
        if not isinstance(owner, str) or not owner.strip():
            errors.append(f"{source}: empty owner")
            continue
        active = root / owner
        if owner not in skill_text:
            errors.append(f"active routing absent from SKILL.md: {owner}")
        if not active.is_file():
            errors.append(f"{source}: integrated active file missing")
        elif sha256(active) != entry["sha256"]:
            errors.append(f"{source}: integrated active hash mismatch")
        if original is not None:
            if not original.is_file():
                errors.append(f"{source}: original V1 source missing")
            elif sha256(original) != entry.get("base_sha256", entry["sha256"]):
                errors.append(f"{source}: original V1 source differs from integration map")
            elif (
                entry["status"] == "superset_integrated_active"
                and active.is_file()
                and not is_line_subsequence(original, active)
            ):
                errors.append(f"{source}: claimed superset deletes or reorders V1 lines")

    expected_rule_owners = {
        f"rules/{index:02d}-{name}"
        for index, name in [
            (1, "contest-project-pattern.md"), (2, "latex-setup.md"),
            (3, "paper-content-rules.md"), (4, "figure-generator.md"),
            (5, "audit-protocol.md"), (6, "weiwei-norms.md"),
            (7, "algorithm-reference.md"), (8, "literature-search.md"),
            (9, "robustness-checker.md"), (10, "json-handoff.md"),
            (11, "paper-finalizer.md"), (12, "source-audit-and-provenance.md"),
            (13, "excellent-paper-expression.md"), (14, "session-handoff.md"),
            (15, "pipeline-methodology.md"), (16, "data-audit-methodology.md"),
        ]
    } | {"rules/00-project-orchestration.md"}
    expected_tool_owners = {
        "scripts/bootstrap_project.py", "scripts/session_checkpoint.py"
    }
    expected_owners = expected_rule_owners | expected_tool_owners
    if mapped_owners != expected_owners:
        missing = sorted(expected_owners - mapped_owners)
        extra = sorted(mapped_owners - expected_owners)
        if missing:
            errors.append(f"unmapped active V5 files: {missing}")
        if extra:
            errors.append(f"mapped non-integration files: {extra}")
    if (root / "references/v1-preserved").exists():
        errors.append("shadow V1 preservation directory must not exist")
    if (root / "scripts/legacy_v1").exists():
        errors.append("shadow V1 tool directory must not exist")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source-v1", type=Path,
        help="Optional original V1 skills directory for source-to-integration comparison.",
    )
    args = parser.parse_args()
    errors = validate(source_v1=args.source_v1)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: V5 directly integrates all 17 V1 rule authorities and 2 V1 tools")


if __name__ == "__main__":
    main()
