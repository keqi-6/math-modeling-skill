#!/usr/bin/env python3
"""Regression tests for single-controller and proportional-recovery architecture."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from validate_single_controller import validate


class SingleControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_root = Path(__file__).resolve().parents[1]

    def copy_fixture(self, directory: str) -> Path:
        root = Path(directory) / "skill"
        shutil.copytree(self.skill_root, root, ignore=shutil.ignore_patterns("__pycache__"))
        return root

    def test_live_contract_passes(self) -> None:
        self.assertEqual(validate(self.skill_root), [])

    def test_parallel_rule_frontmatter_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_fixture(directory)
            path = root / "rules/00-project-orchestration.md"
            path.write_text("---\nname: second-controller\n---\n" + path.read_text(encoding="utf-8"), encoding="utf-8")
            self.assertTrue(any("parallel Skill frontmatter" in item for item in validate(root)))

    def test_loss_of_r1_r2_distinction_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_fixture(directory)
            path = root / "rules/14-session-handoff.md"
            text = path.read_text(encoding="utf-8").replace(
                "新会话本身至少触发 R1，但不自动等于 R2",
                "新会话总是执行 R2",
            )
            path.write_text(text, encoding="utf-8")
            self.assertTrue(any("proportional recovery contract missing" in item for item in validate(root)))


if __name__ == "__main__":
    unittest.main()
