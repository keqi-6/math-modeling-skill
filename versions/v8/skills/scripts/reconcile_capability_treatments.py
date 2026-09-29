#!/usr/bin/env python3
"""Reconcile reviewed V6 blocks with exact V7 text presence.

Missing exact text is conservatively marked rewrite, never remove or merge. Semantic verification
and behavior-test assignment remain separate gates.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("v7_skill_root", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--files", nargs="+", required=True)
    args = parser.parse_args()
    root = args.v7_skill_root.resolve()
    payload = json.loads(args.ledger.read_text(encoding="utf-8"))
    requested = set(args.files)
    texts = {}
    for relative in requested:
        path = root / relative
        if not path.is_file():
            raise SystemExit(f"missing V7 owner file: {relative}")
        texts[relative] = path.read_text(encoding="utf-8")
    counts = {"preserve": 0, "rewrite": 0, "skipped_unreviewed": 0}
    for entry in payload["entries"]:
        relative = entry["source_file"]
        if relative not in requested:
            continue
        if entry["review_status"] == "unreviewed":
            counts["skipped_unreviewed"] += 1
            continue
        if entry["source_text"] in texts[relative]:
            entry["treatment"] = "preserve"
            counts["preserve"] += 1
        else:
            entry["treatment"] = "rewrite"
            entry["rationale"] = (
                f"Exact V6 block changed in V7; semantic ownership retained in {relative}; "
                f"behavior verification pending under {args.review_id}."
            )
            counts["rewrite"] += 1
    args.ledger.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"review_id": args.review_id, "files": sorted(requested), **counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
