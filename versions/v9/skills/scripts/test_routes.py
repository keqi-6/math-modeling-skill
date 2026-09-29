#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest
from pathlib import Path

from resolve_route import resolve_route


ROOT = Path(__file__).resolve().parents[1]


class RouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / "evals" / "routing-cases.json").read_text(encoding="utf-8"))["cases"]
        cls.routes = json.loads((ROOT / "references" / "route-contract.json").read_text(encoding="utf-8"))["routes"]

    def test_positive_and_negative_cases(self):
        for case in self.cases:
            with self.subTest(case=case["id"]):
                request = case["input"]
                if case["expected_route"] is None:
                    with self.assertRaises(LookupError):
                        resolve_route(request["mode"], request["object"], request["action"], request["state"])
                else:
                    route = resolve_route(request["mode"], request["object"], request["action"], request["state"])
                    self.assertEqual(route["id"], case["expected_route"])
                    self.assertEqual(route["resolved_write_allowed"], case["expected_write"])
                    self.assertEqual(route["loaded_modules"], route["modules"])
                    if "expected_recovery" in case:
                        self.assertEqual(route["recovery_policy"], case["expected_recovery"])

    def test_every_route_has_a_positive_case(self):
        covered = {case["expected_route"] for case in self.cases if case["expected_route"]}
        self.assertEqual(covered, {route["id"] for route in self.routes})

    def test_no_wildcards_or_transitive_loads(self):
        contract = json.loads((ROOT / "references" / "route-contract.json").read_text(encoding="utf-8"))
        self.assertFalse(contract["transitive_loading"])
        self.assertFalse(contract["catchalls_count_for_reachability"])
        for route in self.routes:
            for module in route["modules"] + route.get("optional_modules", []):
                self.assertFalse(any(char in module for char in "*?["), module)


if __name__ == "__main__":
    unittest.main()
