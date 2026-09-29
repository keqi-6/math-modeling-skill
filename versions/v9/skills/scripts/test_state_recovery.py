#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from assess_recovery import assess
from init_project import initialize


class StateRecoveryTests(unittest.TestCase):
    def test_unauthorized_initialization_creates_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with self.assertRaises(PermissionError):
                initialize(root, "p", False)
            self.assertEqual(list(root.iterdir()), [])

    def test_minimal_initialization_and_r0(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state = initialize(root, "p", True)
            self.assertEqual({path.relative_to(root).as_posix() for path in root.rglob("*")}, {".modeling", ".modeling/state.json"})
            self.assertTrue(state.is_file())
            self.assertEqual(assess(root)["level"], "R0_CONTINUE")

    def test_localized_artifact_change_is_r1(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state_path = initialize(root, "p", True)
            artifact = root / "result.json"
            artifact.write_text('{"value": 1}\n', encoding="utf-8")
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["artifacts"] = [{"path":"result.json","sha256":hashlib.sha256(artifact.read_bytes()).hexdigest(),"component_ids":["q2"]}]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            self.assertEqual(assess(root)["level"], "R0_CONTINUE")
            artifact.write_text('{"value": 2}\n', encoding="utf-8")
            result = assess(root)
            self.assertEqual(result["level"], "R1_TARGETED")
            self.assertEqual(result["affected_components"], ["q2"])

    def test_unlocalizable_change_and_missing_state_are_r2(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            self.assertEqual(assess(root)["level"], "R2_FULL")
            state_path = initialize(root, "p", True)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["artifacts"] = [{"path":"missing.csv","sha256":"0" * 64,"component_ids":[]}]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            self.assertEqual(assess(root)["level"], "R2_FULL")

    def test_explicit_full_and_closure_are_r2(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            initialize(root, "p", True)
            self.assertEqual(assess(root, explicit_full=True)["level"], "R2_FULL")
            self.assertEqual(assess(root, closure=True)["level"], "R2_FULL")


if __name__ == "__main__":
    unittest.main()

