#!/usr/bin/env python3
"""Build an exhaustive, review-first V6 source-block ledger.

This script deliberately does not decide that text is redundant. It partitions every
non-empty source line into a stable block so human review can later classify atomic
capabilities without losing source coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


SOURCE_PATTERNS = ("SKILL.md", "rules/*.md", "references/*.json", "references/*.md")


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def source_files(root: Path) -> list[Path]:
    paths: set[Path] = set()
    for pattern in SOURCE_PATTERNS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return sorted(paths, key=lambda path: path.relative_to(root).as_posix())


def tree_digest(root: Path, paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def kind_for(lines: list[str]) -> str:
    first = lines[0].lstrip()
    if first == "---":
        return "separator"
    if first.startswith("#"):
        return "heading"
    if first.startswith(("- ", "* ")) or re.match(r"\d+[.)]\s", first):
        return "list"
    if first.startswith("```") or all(line.startswith("    ") or not line for line in lines):
        return "code"
    return "prose"


def blocks(lines: list[str]) -> list[tuple[int, int, list[str]]]:
    result: list[tuple[int, int, list[str]]] = []
    start: int | None = None
    current: list[str] = []
    in_fence = False
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if start is None:
                start = number
            current.append(line)
            in_fence = not in_fence
            if not in_fence:
                result.append((start, number, current))
                start, current = None, []
            continue
        if in_fence:
            current.append(line)
            continue
        if not stripped:
            if current:
                result.append((start or number, number - 1, current))
                start, current = None, []
            continue
        structural = stripped.startswith("#") or stripped == "---"
        if structural and current:
            result.append((start or number, number - 1, current))
            start, current = None, []
        if start is None:
            start = number
        current.append(line)
        if structural:
            result.append((start, number, current))
            start, current = None, []
    if current:
        result.append((start or len(lines), len(lines), current))
    return result


def anchor_for(lines: list[str], prior_anchor: str) -> str:
    first = lines[0].strip()
    return first.lstrip("# ").strip() if first.startswith("#") else prior_anchor


def build(root: Path) -> dict:
    paths = source_files(root)
    entries: list[dict] = []
    seen_ids: set[str] = set()
    for path in paths:
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        text_lines = raw.decode("utf-8").splitlines()
        file_hash = digest_bytes(raw)
        anchor = ""
        for start, end, block_lines in blocks(text_lines):
            anchor = anchor_for(block_lines, anchor)
            source_text = "\n".join(block_lines).strip()
            identity = f"{relative}:{start}:{end}:{source_text}".encode("utf-8")
            capability_id = "V6-" + hashlib.sha256(identity).hexdigest()[:12].upper()
            if capability_id in seen_ids:
                raise RuntimeError(f"capability id collision: {capability_id}")
            seen_ids.add(capability_id)
            entries.append({
                "capability_id": capability_id,
                "source_file": relative,
                "source_lines": [start, end],
                "source_sha256": file_hash,
                "source_anchor": anchor,
                "source_text": source_text,
                "candidate_kind": kind_for(block_lines),
                "review_status": "unreviewed",
                "strength": "unclassified",
                "v7_owner": None,
                "treatment": "unclassified",
                "rationale": None,
                "trigger_ids": [],
                "test_ids": [],
                "merged_into": None,
            })
    return {
        "schema_version": "1.0",
        "source_root": root.resolve().as_posix(),
        "source_snapshot": {
            "algorithm": "sha256-tree-v1",
            "digest": tree_digest(root, paths),
            "file_count": len(paths),
        },
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payload = build(args.source_root.resolve())
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": args.output.as_posix(),
        "source_file_count": payload["source_snapshot"]["file_count"],
        "entry_count": len(payload["entries"]),
        "snapshot": payload["source_snapshot"]["digest"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
