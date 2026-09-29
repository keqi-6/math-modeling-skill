#!/usr/bin/env python3
"""Create and verify an evidence manifest for the V5 full-read recovery gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".tex", ".bib", ".csv", ".tsv", ".xml", ".html", ".css", ".js", ".ts",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify(path: Path) -> str:
    suffix = path.suffix.lower()
    if "__pycache__" in path.parts or suffix == ".pyc":
        return "cache"
    if path.name.startswith("~$") or suffix == ".lock":
        return "lock"
    if suffix in TEXT_SUFFIXES:
        return "text"
    if suffix == ".pdf":
        return "pdf"
    if suffix in {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}:
        return "office"
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".bmp", ".webp"}:
        return "image"
    if suffix in {".zip", ".7z", ".rar", ".tar", ".gz"}:
        return "archive"
    if suffix in {".npy", ".npz", ".parquet", ".feather", ".h5", ".hdf5"}:
        return "structured"
    return "binary"


def inventory(root: Path) -> dict:
    files = [path for path in sorted(root.rglob("*")) if path.is_file()]
    entries: list[dict] = []
    first_by_hash: dict[str, str] = {}
    for path in files:
        digest = sha256(path)
        relative = path.relative_to(root).as_posix()
        canonical = first_by_hash.setdefault(digest, relative)
        kind = classify(path)
        entry = {
            "path": relative,
            "bytes": path.stat().st_size,
            "sha256": digest,
            "representation": kind,
            "duplicate_of": None if canonical == relative else canonical,
            "inspection": None,
        }
        if kind == "text":
            try:
                line_count = len(path.read_text(encoding="utf-8").splitlines())
                entry["line_count"] = line_count
            except UnicodeDecodeError:
                entry["representation"] = "binary"
        entries.append(entry)
    return {
        "schema_version": "1.0",
        "project_root": root.resolve().as_posix(),
        "inventory_at": datetime.now(timezone.utc).isoformat(),
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


def verify_manifest(root: Path, manifest: dict) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    if manifest.get("schema_version") != "1.0":
        errors.append("unsupported manifest schema_version")
    if manifest.get("project_root") != root.resolve().as_posix():
        errors.append("manifest project_root mismatch")
    if not isinstance(manifest.get("inventory_at"), str):
        errors.append("manifest inventory_at missing")
    current = inventory(root)
    recorded = manifest.get("files")
    if not isinstance(recorded, list):
        recorded = []
        errors.append("manifest files must be a list")
    current_map = {item["path"]: item for item in current["files"]}
    recorded_map = {
        item.get("path"): item for item in recorded
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    if set(current_map) != set(recorded_map):
        errors.append("manifest inventory paths are stale or incomplete")
    completed = 0
    canonical_count = 0
    for relative, live in current_map.items():
        item = recorded_map.get(relative)
        if item is None:
            continue
        for field in ("bytes", "sha256", "representation", "duplicate_of"):
            if item.get(field) != live.get(field):
                errors.append(f"{relative}: stale {field}")
        if live["duplicate_of"] is not None:
            continue
        canonical_count += 1
        inspection = item.get("inspection")
        if not isinstance(inspection, dict) or inspection.get("status") != "complete":
            errors.append(f"{relative}: canonical inspection incomplete")
            continue
        if inspection.get("truncated") is not False:
            errors.append(f"{relative}: truncated must be false")
            continue
        if live["representation"] == "text":
            if item.get("line_count") != live.get("line_count"):
                errors.append(f"{relative}: stale line_count")
                continue
            if not ranges_cover(live.get("line_count", 0), inspection.get("read_ranges")):
                errors.append(f"{relative}: read ranges do not cover 1..EOF")
                continue
        else:
            if (
                not inspection.get("method")
                or not inspection.get("inspected_units")
                or not inspection.get("findings")
            ):
                errors.append(f"{relative}: native inspection method/units/findings missing")
                continue
        completed += 1
    unresolved = manifest.get("unresolved")
    if not isinstance(unresolved, list):
        errors.append("unresolved must be a list")
        unresolved = ["invalid"]
    if unresolved:
        errors.append("unresolved items remain")
    counts = {
        "inventory_file_count": len(current_map),
        "canonical_item_count": canonical_count,
        "completed_canonical_count": completed,
        "unresolved_count": len(unresolved),
    }
    if completed != canonical_count:
        errors.append("not every canonical item has complete inspection evidence")
    return errors, counts


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("inventory")
    create.add_argument("project_root", type=Path)
    create.add_argument("manifest", type=Path)
    verify = subparsers.add_parser("verify")
    verify.add_argument("project_root", type=Path)
    verify.add_argument("manifest", type=Path)
    verify.add_argument(
        "--max-errors", type=int, default=20,
        help="Maximum error examples printed; the full error count is always reported.",
    )
    args = parser.parse_args()
    if args.command == "inventory":
        payload = inventory(args.project_root.resolve())
        args.manifest.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"WROTE: {args.manifest}")
        return
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    errors, counts = verify_manifest(args.project_root.resolve(), payload)
    limit = max(args.max_errors, 0)
    print(json.dumps({
        "passed": not errors,
        "counts": counts,
        "error_count": len(errors),
        "errors_shown": errors[:limit],
        "errors_omitted": max(len(errors) - limit, 0),
    }, ensure_ascii=False))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
