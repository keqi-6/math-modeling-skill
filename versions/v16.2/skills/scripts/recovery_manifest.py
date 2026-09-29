#!/usr/bin/env python3
"""Inventory and verify the V16 R2 whole-project read contract.

The manifest is intentionally stored outside the recovered project.  R2 may
update ``.modeling/state.json`` only after verification, so the inventory is a
stable snapshot for the entire recovery episode rather than a self-referential
file inside the project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "16.0"
TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".pyi", ".json", ".jsonl", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".tex", ".bib", ".csv", ".tsv",
    ".xml", ".html", ".css", ".scss", ".js", ".jsx", ".ts", ".tsx",
    ".sh", ".bash", ".ps1", ".bat", ".cmd", ".sql", ".r", ".jl",
    ".java", ".c", ".h", ".cc", ".cpp", ".hpp", ".rs", ".go",
}
CACHE_DIRS = {
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".cache", ".ipynb_checkpoints",
}
VENDOR_DIRS = {"node_modules", ".venv", "venv", "vendor"}
CONTROL_DIRS = {".git", ".hg", ".svn"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if any(part in CACHE_DIRS for part in path.parts) or suffix in {".pyc", ".pyo"}:
        return "cache"
    if any(part in VENDOR_DIRS for part in path.parts):
        return "vendor"
    if any(part in CONTROL_DIRS for part in path.parts):
        return "control"
    if path.name.startswith("~$") or suffix in {".lock", ".lck"}:
        return "lock"
    if suffix in TEXT_SUFFIXES or path.name in {
        "Dockerfile", "Makefile", "Procfile", "LICENSE", "README",
    }:
        return "text"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt", ".ods", ".odp"}:
        return "office"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".webp", ".svg"}:
        return "image"
    if suffix in {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz"}:
        return "archive"
    if suffix in {".npy", ".npz", ".parquet", ".feather", ".h5", ".hdf5", ".mat", ".sav", ".dta"}:
        return "structured"
    return "binary"


def inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    files = [
        path for path in sorted(root.rglob("*"))
        if path.is_file() or path.is_symlink()
    ]
    entries: list[dict[str, Any]] = []
    first_by_hash: dict[tuple[str, str], str] = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        is_link = path.is_symlink()
        if is_link:
            link_target = os.readlink(path)
            digest = hashlib.sha256(link_target.encode("utf-8")).hexdigest()
            byte_count = path.lstat().st_size
        else:
            digest = sha256(path)
            byte_count = path.stat().st_size
        representation = "symlink" if is_link else classify(path.relative_to(root))
        canonical = first_by_hash.setdefault((representation, digest), relative)
        entry: dict[str, Any] = {
            "path": relative,
            "bytes": byte_count,
            "sha256": digest,
            "representation": representation,
            "duplicate_of": None if canonical == relative else canonical,
            "inspection": None,
        }
        if is_link:
            entry["link_target"] = link_target
        if representation == "text":
            try:
                entry["line_count"] = len(path.read_text(encoding="utf-8").splitlines())
            except UnicodeDecodeError:
                entry["representation"] = "binary"
        entries.append(entry)
    return {
        "schema_version": SCHEMA_VERSION,
        "project_root": root.as_posix(),
        "inventory_at": datetime.now(timezone.utc).isoformat(),
        "coverage": "whole_project",
        "files": entries,
        "unresolved": [],
    }


def ranges_cover(line_count: int, ranges: object) -> bool:
    if line_count == 0:
        return ranges == []
    if not isinstance(ranges, list):
        return False
    expected = 1
    for item in ranges:
        if (
            not isinstance(item, list) or len(item) != 2
            or not all(isinstance(value, int) for value in item)
            or item[0] != expected or item[1] < item[0]
        ):
            return False
        expected = item[1] + 1
    return expected == line_count + 1


def verify_manifest(root: Path, manifest: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
    """Verify inventory identity and every canonical item's disposition.

    Cache/lock/vendor objects still appear in the inventory, but may use a
    ``classified`` disposition.  Every project-owned canonical object requires
    a complete, untruncated read or native inspection.  Duplicates inherit the
    canonical item's inspection by content hash.
    """
    errors: list[str] = []
    root = root.resolve()
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported_manifest_schema_version")
    if manifest.get("project_root") != root.as_posix():
        errors.append("manifest_project_root_mismatch")
    if manifest.get("coverage") != "whole_project":
        errors.append("manifest_coverage_not_whole_project")
    if not isinstance(manifest.get("inventory_at"), str):
        errors.append("manifest_inventory_at_missing")

    current = inventory(root)
    recorded = manifest.get("files")
    if not isinstance(recorded, list):
        recorded = []
        errors.append("manifest_files_not_array")
    current_map = {item["path"]: item for item in current["files"]}
    recorded_map: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(recorded):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append(f"manifest_entry_invalid:{index}")
            continue
        path = item["path"]
        if path in recorded_map:
            errors.append("manifest_entry_duplicate:" + path)
        recorded_map[path] = item
    if set(current_map) != set(recorded_map):
        missing = sorted(set(current_map) - set(recorded_map))
        extra = sorted(set(recorded_map) - set(current_map))
        if missing:
            errors.append("manifest_paths_missing:" + ",".join(missing))
        if extra:
            errors.append("manifest_paths_stale:" + ",".join(extra))

    completed = 0
    classified = 0
    canonical_count = 0
    for relative, live in current_map.items():
        item = recorded_map.get(relative)
        if item is None:
            continue
        for field in ("bytes", "sha256", "representation", "duplicate_of"):
            if item.get(field) != live.get(field):
                errors.append(f"{relative}:stale_{field}")
        if live["representation"] == "symlink" and item.get("link_target") != live.get("link_target"):
            errors.append(f"{relative}:stale_link_target")
        if live["duplicate_of"] is not None:
            continue
        canonical_count += 1
        inspection = item.get("inspection")
        if not isinstance(inspection, dict):
            errors.append(f"{relative}:canonical_inspection_missing")
            continue
        status = inspection.get("status")
        representation = live["representation"]
        if representation in {"cache", "lock", "vendor", "control"}:
            if status != "classified" or not inspection.get("findings"):
                errors.append(f"{relative}:classification_disposition_incomplete")
                continue
            classified += 1
            completed += 1
            continue
        if status != "complete":
            errors.append(f"{relative}:canonical_inspection_incomplete")
            continue
        if inspection.get("truncated") is not False:
            errors.append(f"{relative}:truncated_must_be_false")
            continue
        if representation == "text":
            if item.get("line_count") != live.get("line_count"):
                errors.append(f"{relative}:stale_line_count")
                continue
            if not ranges_cover(live.get("line_count", 0), inspection.get("read_ranges")):
                errors.append(f"{relative}:read_ranges_do_not_cover_1_to_eof")
                continue
        elif not (
            inspection.get("method")
            and inspection.get("inspected_units")
            and inspection.get("findings")
        ):
            errors.append(f"{relative}:native_inspection_fields_missing")
            continue
        completed += 1

    unresolved = manifest.get("unresolved")
    if not isinstance(unresolved, list):
        unresolved = ["invalid"]
        errors.append("manifest_unresolved_not_array")
    if unresolved:
        errors.append("manifest_unresolved_items_remain")
    counts = {
        "inventory_file_count": len(current_map),
        "canonical_item_count": canonical_count,
        "completed_canonical_count": completed,
        "classified_canonical_count": classified,
        "unresolved_count": len(unresolved),
    }
    if completed != canonical_count:
        errors.append("not_every_canonical_item_has_complete_disposition")
    return sorted(set(errors)), counts


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("inventory")
    create.add_argument("project_root", type=Path)
    create.add_argument("manifest", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("project_root", type=Path)
    verify.add_argument("manifest", type=Path)
    verify.add_argument("--max-errors", type=int, default=20)
    args = parser.parse_args()
    if args.command == "inventory":
        payload = inventory(args.project_root)
        args.manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "status": "created", "manifest": str(args.manifest),
            "file_count": len(payload["files"]),
        }, ensure_ascii=False))
        return 0
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors, counts = verify_manifest(args.project_root, payload)
    limit = max(args.max_errors, 0)
    print(json.dumps({
        "status": "pass" if not errors else "fail", "counts": counts,
        "error_count": len(errors), "errors": errors[:limit],
        "errors_omitted": max(len(errors) - limit, 0),
    }, ensure_ascii=False))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
