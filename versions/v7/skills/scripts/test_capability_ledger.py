#!/usr/bin/env python3
"""Regression tests for V7 anti-compression capability coverage."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from build_capability_ledger import build
from validate_capability_ledger import validate


class CapabilityLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_root = Path(__file__).resolve().parents[1]
        cls.source_root = cls.skill_root.parents[1] / "skills_v6" / "skills"
        cls.payload = build(cls.source_root)

    def write_payload(self, root: Path, payload: dict) -> Path:
        path = root / "ledger.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_complete_candidate_coverage_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(Path(directory), self.payload)
            self.assertEqual(validate(self.source_root, path, False), [])

    def test_deleting_one_source_block_fails(self) -> None:
        broken = copy.deepcopy(self.payload)
        broken["entries"].pop(len(broken["entries"]) // 2)
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(Path(directory), broken)
            errors = validate(self.source_root, path, False)
            self.assertTrue(any("misses 1 source blocks" in item for item in errors))

    def test_closed_mode_rejects_unreviewed_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(Path(directory), self.payload)
            errors = validate(self.source_root, path, True)
            self.assertTrue(any("remains unreviewed" in item for item in errors))

    def test_merge_without_target_reason_or_test_fails(self) -> None:
        broken = copy.deepcopy(self.payload)
        for entry in broken["entries"]:
            entry["review_status"] = "context_only"
        target = broken["entries"][0]
        target["review_status"] = "confirmed_capability"
        target["strength"] = "must"
        target["v7_owner"] = "rules/example.md"
        target["treatment"] = "merge"
        target["trigger_ids"] = ["TR-EXAMPLE"]
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(Path(directory), broken)
            errors = validate(self.source_root, path, True)
            self.assertTrue(any("merge/remove lacks rationale" in item for item in errors))
            self.assertTrue(any("merge/remove lacks regression test" in item for item in errors))
            self.assertTrue(any("merge lacks target capability" in item for item in errors))

    def test_preserve_claim_missing_from_v7_owner_fails(self) -> None:
        broken = copy.deepcopy(self.payload)
        for entry in broken["entries"]:
            entry["review_status"] = "context_only"
        target = broken["entries"][1]
        target.update({
            "review_status": "confirmed_capability", "strength": "must",
            "v7_owner": "SKILL.md", "treatment": "preserve",
            "trigger_ids": ["TR-SKILL-MAINTENANCE"],
            "test_ids": ["T-PRESERVE-EXACT"],
        })
        target["source_text"] = "invented capability absent from V7 owner"
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(Path(directory), broken)
            errors = validate(self.source_root, path, True)
            self.assertTrue(any("preserve capability is absent from V7 owner" in item for item in errors))

    def test_unknown_test_id_fails(self) -> None:
        broken = copy.deepcopy(self.payload)
        for entry in broken["entries"]:
            entry["review_status"] = "context_only"
        target = broken["entries"][1]
        target.update({
            "review_status": "confirmed_capability", "strength": "must",
            "v7_owner": "SKILL.md", "treatment": "rewrite",
            "trigger_ids": ["TR-SKILL-MAINTENANCE"], "test_ids": ["T-INVENTED"],
        })
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(Path(directory), broken)
            errors = validate(self.source_root, path, True)
            self.assertTrue(any("unknown tests" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
