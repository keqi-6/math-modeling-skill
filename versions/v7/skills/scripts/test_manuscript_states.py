#!/usr/bin/env python3
"""Regression tests for the single seven-level manuscript audit state model."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from validate_manuscript_states import validate


class ManuscriptStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_root = Path(__file__).resolve().parents[1]
        cls.registry = cls.skill_root / "references/manuscript-audit-states.json"
        cls.payload = json.loads(cls.registry.read_text(encoding="utf-8"))

    def fixture(self, directory: str, payload: dict) -> tuple[Path, Path]:
        root = Path(directory) / "skill"
        (root / "rules").mkdir(parents=True)
        for relative in payload["mirrors"]:
            shutil.copy2(self.skill_root / relative, root / relative)
        registry = root / "registry.json"
        registry.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return root, registry

    def test_live_state_contract_passes(self) -> None:
        self.assertEqual(validate(self.skill_root, self.registry), [])

    def test_missing_level_fails(self) -> None:
        broken = copy.deepcopy(self.payload)
        broken["states"].pop(3)
        with tempfile.TemporaryDirectory() as directory:
            root, registry = self.fixture(directory, broken)
            self.assertTrue(any("exactly 1..7" in item for item in validate(root, registry)))

    def test_machine_only_promotion_fails(self) -> None:
        broken = copy.deepcopy(self.payload)
        broken["promotion_rules"]["compile_or_machine_check_cannot_promote_alone"] = False
        with tempfile.TemporaryDirectory() as directory:
            root, registry = self.fixture(directory, broken)
            self.assertTrue(any("must not promote alone" in item for item in validate(root, registry)))


if __name__ == "__main__":
    unittest.main()
