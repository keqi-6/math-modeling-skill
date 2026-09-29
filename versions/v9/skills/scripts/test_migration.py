#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_all_v8_rule_files_have_disposition(self):
        doc = json.loads((ROOT / "references" / "migration" / "rule-disposition.json").read_text(encoding="utf-8"))
        entries = doc["entries"]
        self.assertEqual(len(entries), 38)
        self.assertEqual(len({entry["source"] for entry in entries}), 38)
        self.assertTrue(all(entry["status"] in {"retained","normalized","superseded","retired","merged"} for entry in entries))

    def test_active_source_text_is_byte_preserved_inside_modules(self):
        manifest = json.loads((ROOT / "references" / "migration" / "module-source-manifest.json").read_text(encoding="utf-8"))
        sibling = ROOT.parents[1] / "skills_v8" / "skills"
        workspace_history = Path("/mnt/d/AI/AI_program/2021（第四题）/总skill/skills_v8/skills")
        source_root = sibling if sibling.is_dir() else workspace_history
        if not source_root.is_dir():
            self.skipTest("frozen V8 history not mounted")
        for module in manifest["modules"]:
            text = (ROOT / module["module"]).read_text(encoding="utf-8")
            for source in module["sources"]:
                raw = (source_root / source["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), source["sha256"])
                self.assertIn(raw.decode("utf-8").rstrip(), text)

    def test_atomic_ledger_has_zero_unmapped_entries(self):
        ledger = json.loads((ROOT / "references" / "migration" / "v1-v9-capability-ledger.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(ledger["coverage"]["v1_v6_atomic_entries"], 1859)
        self.assertGreaterEqual(ledger["coverage"]["v7_native_entries"], 9)
        self.assertGreaterEqual(ledger["coverage"]["v8_native_entries"], 5)
        self.assertEqual(ledger["coverage"]["unmapped_entries"], 0)
        self.assertEqual(ledger["coverage"]["total_entries"], len(ledger["entries"]))

    def test_all_conflicts_are_resolved(self):
        conflicts = json.loads((ROOT / "references" / "migration" / "conflict-decisions.json").read_text(encoding="utf-8"))
        self.assertEqual(conflicts["unresolved"], 0)
        self.assertGreaterEqual(len(conflicts["decisions"]), 16)


if __name__ == "__main__":
    unittest.main()
