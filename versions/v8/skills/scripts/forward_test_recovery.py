#!/usr/bin/env python3
"""Run a read-only S0 recovery-gate forward test against a real project."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from recovery_manifest import inventory, verify_manifest


def fingerprint(payload: dict) -> list[tuple[str, int, str]]:
    return sorted(
        (item["path"], item["bytes"], item["sha256"])
        for item in payload["files"]
    )


def run(root: Path) -> dict:
    before = inventory(root)
    errors, counts = verify_manifest(root, before)
    after = inventory(root)
    checks = {
        "inventory_nonempty": counts["inventory_file_count"] > 0,
        "uninspected_gate_rejected": bool(errors),
        "no_false_completed_items": counts["completed_canonical_count"] == 0,
        "project_unchanged": fingerprint(before) == fingerprint(after),
    }
    return {
        "passed": all(checks.values()),
        "project_root": root.as_posix(),
        "checks": checks,
        "counts": counts,
        "gate_error_count": len(errors),
    }


def build_fixture(root: Path) -> None:
    (root / "planning").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "data").mkdir()
    (root / "planning/task.md").write_text(
        "# Task\nRecover the project before continuing.\n", encoding="utf-8"
    )
    (root / "src/solve.py").write_text(
        "print('candidate only')\n", encoding="utf-8"
    )
    (root / "data/input.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (root / "data/input-copy.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (root / "opaque.bin").write_bytes(b"\x00\x01fixture")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("project_root", type=Path, nargs="?")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Build a mixed realistic fixture in a temporary directory and test the read-only gate.",
    )
    args = parser.parse_args()
    if args.self_test:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "inherited-project"
            root.mkdir()
            build_fixture(root)
            result = run(root)
    elif args.project_root is not None:
        result = run(args.project_root.resolve())
    else:
        parser.error("provide project_root or --self-test")
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
