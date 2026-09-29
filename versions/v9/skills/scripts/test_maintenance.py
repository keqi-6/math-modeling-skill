#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest
from pathlib import Path

from analyze_rule_change import analyze
from resolve_route import resolve_route


ROOT = Path(__file__).resolve().parents[1]


class MaintenanceTests(unittest.TestCase):
    def test_change_envelopes(self):
        cases = json.loads((ROOT / "evals" / "maintenance-cases.json").read_text(encoding="utf-8"))["cases"]
        for case in cases:
            with self.subTest(case=case["id"]):
                result = analyze(case["payload"], case["postflight"])
                self.assertEqual(result["status"], case["expected"])

    def test_skill_change_requires_maintenance_mode(self):
        with self.assertRaises(LookupError):
            resolve_route("mutate", "skill", "modify_rule", "V9")
        route = resolve_route("skill_maintenance", "skill", "modify_rule", "V9")
        self.assertEqual(route["id"], "RT-SKILL-CHANGE")

    def test_skill_audit_is_readonly(self):
        route = resolve_route("advisory_readonly", "skill", "audit", "V9")
        self.assertFalse(route["resolved_write_allowed"])


if __name__ == "__main__":
    unittest.main()

