#!/usr/bin/env python3

from __future__ import annotations

import json
import unittest
from pathlib import Path

from resolve_route import resolve_route


ROOT = Path(__file__).resolve().parents[1]


class BehaviorContractTests(unittest.TestCase):
    def test_behavior_cases_resolve_and_have_observable_expectations(self):
        cases = json.loads((ROOT / "evals" / "behavior-cases.json").read_text(encoding="utf-8"))["cases"]
        known_caps = {cap["id"] for cap in json.loads((ROOT / "references" / "capability-registry.json").read_text(encoding="utf-8"))["capabilities"]}
        for case in cases:
            with self.subTest(case=case["id"]):
                query = case["classification"]
                route = resolve_route(query["mode"], query["object"], query["action"], query["state"])
                self.assertEqual(route["id"], case["expected_route"])
                if "expected_recovery" in case:
                    self.assertEqual(route["recovery_policy"], case["expected_recovery"])
                self.assertTrue(case["prompt"].strip())
                self.assertTrue(case["required"])
                self.assertTrue(case["forbidden"])
                required_caps = {item for item in case["required"] if item in known_caps}
                self.assertTrue(required_caps.issubset(set(route["capabilities"])))

    def test_positive_and_negative_trigger_balance(self):
        route_cases = json.loads((ROOT / "evals" / "routing-cases.json").read_text(encoding="utf-8"))["cases"]
        positives = [case for case in route_cases if case["expected_route"]]
        negatives = [case for case in route_cases if case["expected_route"] is None]
        self.assertGreaterEqual(len(positives), 23)
        self.assertGreaterEqual(len(negatives), 7)


if __name__ == "__main__":
    unittest.main()
