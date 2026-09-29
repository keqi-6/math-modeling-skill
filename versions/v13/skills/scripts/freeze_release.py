#!/usr/bin/env python3
"""Freeze a validated V13 candidate into a new destination; never modify source."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any


MANIFEST = Path("evals/release/frozen-manifest.json")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def root_for(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def within(path: Path, parent: Path) -> bool:
    path, parent = path.resolve(), parent.resolve()
    return path == parent or parent in path.parents


def tree_manifest(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or path.is_symlink() or relative == MANIFEST.as_posix() or "__pycache__" in path.parts:
            continue
        files.append({"path": relative, "sha256": digest(path.read_bytes()), "size": path.stat().st_size})
    return {"algorithm": "sha256-canonical-file-list-v1", "file_count": len(files), "sha256": digest(canonical(files)), "files": files}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--authorization", required=True, help="verbatim user authorization for this freeze")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()
    source = root_for(args.root)
    destination = args.destination.resolve()
    if len(args.authorization.strip()) < 8:
        raise SystemExit("freeze refused: authorization is missing or too short")
    if destination.exists():
        raise SystemExit("freeze refused: destination already exists")
    if within(destination, source) or within(source, destination):
        raise SystemExit("freeze refused: source and destination overlap")

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    gate = subprocess.run(
        [sys.executable, "-B", str(source / "scripts/validate_release.py"), "--root", str(source), "--timeout", str(args.timeout)],
        cwd=source,
        env=environment,
        text=True,
        capture_output=True,
        timeout=max(60, args.timeout * 4 + 10),
        check=False,
    )
    try:
        report = json.loads(gate.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"freeze refused: release gate did not return JSON: {exc}") from exc
    claimed = report.get("report_sha256")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    if gate.returncode != 0 or report.get("status") != "pass" or claimed != digest(canonical(unsigned)):
        raise SystemExit(f"freeze refused: release gate failed: {report.get('errors', [])}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    try:
        shutil.copytree(source, staging, symlinks=True)
        skill_path = staging / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        stable, count = re.subn(r'(?m)^(\s{2}release:\s*)["\']?candidate["\']?\s*$', r'\1"stable"', skill)
        if count != 1:
            raise RuntimeError("candidate release marker is missing or ambiguous")
        skill_path.write_text(stable, encoding="utf-8")

        frozen_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        state_path = staging / "evals/release/release-state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state.update({"status": "stable", "frozen_at": frozen_at, "gate_report_sha256": claimed})
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        release_tree = tree_manifest(staging)
        manifest = {
            "schema_version": "13.0",
            "release_id": "V13.0.0",
            "status": "stable",
            "generated_at": frozen_at,
            "authorization_sha256": digest(args.authorization.encode("utf-8")),
            "source_gate": {"report_sha256": claimed, "candidate_tree_sha256": report.get("tree_sha256")},
            "release_tree": release_tree,
            "external_signature": None,
        }
        manifest["manifest_sha256"] = digest(canonical(manifest))
        manifest_path = staging / MANIFEST
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.rename(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    print(json.dumps({
        "schema_version": "13.0", "status": "stable", "destination": str(destination),
        "manifest_sha256": manifest["manifest_sha256"], "gate_report_sha256": claimed,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
