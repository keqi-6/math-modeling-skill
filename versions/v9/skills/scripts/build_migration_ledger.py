#!/usr/bin/env python3
"""Create a V1-V9 traceability ledger without dropping legacy atomic entries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REFERENCE_OWNER_MAP = {
    "references/start_receipt.schema.json": "references/receipt.schema.json",
    "references/end_receipt.schema.json": "references/receipt.schema.json",
    "references/migration-ledger.md": "references/migration/v1-v9-capability-ledger.json",
    "references/qualified-skill-standard.md": "scripts/validate_release.py",
    "references/v1-integration-map.json": "references/migration/v1-v9-capability-ledger.json",
    "references/version-delta-map.json": "references/migration/v1-v9-capability-ledger.json",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def owner_path(owner: str) -> str:
    return owner.split("#", 1)[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, help="V8 skills directory")
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    skill_root = args.skill_root.resolve()
    source_root = (args.source_root or (skill_root.parents[1] / "skills_v8" / "skills")).resolve()
    legacy_path = source_root / "references" / "v6-capability-ledger.json"
    legacy = json.loads(legacy_path.read_text(encoding="utf-8"))
    disposition = json.loads(
        (skill_root / "references" / "migration" / "rule-disposition.json").read_text(encoding="utf-8")
    )
    disposition_by_source = {entry["source"]: entry for entry in disposition["entries"]}

    entries = []
    for old in legacy["entries"]:
        old_owner = old["v7_owner"]
        if old_owner == "SKILL.md":
            new_owner = "SKILL.md"
            status = "normalized"
        elif old_owner.startswith("rules/"):
            if old_owner not in disposition_by_source:
                raise SystemExit(f"no V9 disposition for {old_owner}")
            decision = disposition_by_source[old_owner]
            new_owner = decision["v9_owner"]
            status = decision["status"]
        else:
            new_owner = REFERENCE_OWNER_MAP.get(old_owner)
            if new_owner is None:
                raise SystemExit(f"no V9 reference mapping for {old_owner}")
            status = "normalized"
        path = skill_root / owner_path(new_owner)
        if not path.exists() and new_owner != "references/migration/v1-v9-capability-ledger.json":
            raise SystemExit(f"mapped owner does not exist: {new_owner}")
        updated = dict(old)
        updated.update(
            {
                "lineage_scope": "V1-V6 frozen atomic baseline",
                "legacy_owner": old_owner,
                "v9_owner": new_owner,
                "migration_status": status,
                "migration_release": "9.0.0",
            }
        )
        entries.append(updated)

    native_path = skill_root / "references" / "migration" / "native-capabilities.json"
    native = json.loads(native_path.read_text(encoding="utf-8"))["entries"]
    entries.extend(native)

    operational = json.loads(
        (skill_root / "references" / "capability-registry.json").read_text(encoding="utf-8")
    )["capabilities"]
    for cap in operational:
        entries.append(
            {
                "capability_id": cap["id"],
                "introduced_in": "V9",
                "capability": cap["expected"],
                "source": cap["owner"],
                "v9_owner": cap["owner"],
                "migration_status": "native",
                "strength": cap["strength"],
                "trigger": cap["trigger"],
                "forbidden": cap["forbidden"],
            }
        )

    ids = [entry["capability_id"] for entry in entries]
    duplicates = sorted({cap_id for cap_id in ids if ids.count(cap_id) > 1})
    if duplicates:
        raise SystemExit(f"duplicate capability IDs: {duplicates[:10]}")

    out = {
        "schema_version": "2.0",
        "release": "9.0.0",
        "status": "complete",
        "source_snapshot": {
            "v6_atomic_ledger": str(legacy_path),
            "sha256": sha256(legacy_path),
            "entry_count": len(legacy["entries"]),
        },
        "coverage": {
            "v1_v6_atomic_entries": len(legacy["entries"]),
            "v7_native_entries": sum(e.get("introduced_in") == "V7" for e in native),
            "v8_native_entries": sum(e.get("introduced_in") == "V8" for e in native),
            "v9_operational_entries": len(operational),
            "total_entries": len(entries),
            "unmapped_entries": 0,
        },
        "entries": entries,
    }
    out_path = skill_root / "references" / "migration" / "v1-v9-capability-ledger.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"built traceability ledger with {len(entries)} entries; unmapped=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

