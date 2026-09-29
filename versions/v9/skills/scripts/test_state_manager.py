#!/usr/bin/env python3

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from assess_recovery import assess
from init_project import initialize
from state_manager import add_component, register_artifact, set_next_action, transition


class StateManagerTests(unittest.TestCase):
    def test_authorized_component_transition_and_artifact_registration(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            state_path = initialize(root, "managed", True)
            add_component(root, "q1", "question", "S0", True)
            with self.assertRaises(ValueError):
                transition(root, "q1", "S1", [], True)
            transition(root, "q1", "S1", ["problem_scope=planning/scope.md"], True)
            result = root / "result.json"
            result.write_text('{"value": 1}\n', encoding="utf-8")
            register_artifact(root, "result.json", "formal", "paper", "verified result", "through delivery", "user request", ["q1"], ["unit-test"], True)
            set_next_action(root, "q1", "collect evidence", True)
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(state["components"][0]["state"], "S1")
            self.assertEqual(state["artifacts"][0]["path"], "result.json")
            self.assertEqual(state["next_actions"][0]["action"], "collect evidence")
            self.assertEqual(assess(root)["level"], "R0_CONTINUE")
            result.write_text('{"value": 2}\n', encoding="utf-8")
            self.assertEqual(assess(root)["level"], "R1_TARGETED")

    def test_mutation_without_authorization_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            initialize(root, "managed", True)
            with self.assertRaises(PermissionError):
                add_component(root, "q1", "question", "S0", False)

    def test_illegal_transition_is_refused(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            initialize(root, "managed", True)
            add_component(root, "q1", "question", "S0", True)
            with self.assertRaises(ValueError):
                transition(root, "q1", "S2", ["evidence_inventory=x", "data_identity=y"], True)


if __name__ == "__main__":
    unittest.main()

