#!/usr/bin/env python3
"""Bind reviewed capabilities to registered triggers and executable test families."""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.ledger.read_text(encoding="utf-8"))
    counts = {"preserve": 0, "rewrite": 0, "context": 0}
    for entry in payload["entries"]:
        if entry["review_status"] != "confirmed_capability":
            counts["context"] += 1
            continue
        if not entry["trigger_ids"]:
            entry["trigger_ids"] = ["TR-SKILL-MAINTENANCE"]
        if entry["treatment"] == "preserve":
            entry["test_ids"] = ["T-PRESERVE-EXACT"]
            counts["preserve"] += 1
        elif entry["treatment"] == "rewrite":
            entry["test_ids"] = ["T-V7-REWRITE-CONTRACT"]
            counts["rewrite"] += 1
        else:
            raise SystemExit(f"unsupported closed treatment for {entry['capability_id']}: {entry['treatment']}")
    args.ledger.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(counts, ensure_ascii=False))


if __name__ == "__main__":
    main()
