#!/usr/bin/env python3
"""Regression tests for V7 route reachability and ownership."""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from validate_routing_registry import validate


class RoutingRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_root = Path(__file__).resolve().parents[1]
        cls.registry_path = cls.skill_root / "references" / "routing-registry.json"
        cls.payload = json.loads(cls.registry_path.read_text(encoding="utf-8"))

    def write_payload(self, directory: str, payload: dict) -> Path:
        path = Path(directory) / "routing.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def test_live_registry_passes(self) -> None:
        self.assertEqual(validate(self.skill_root, self.registry_path), [])

    def test_unknown_rule_fails(self) -> None:
        broken = copy.deepcopy(self.payload)
        broken["triggers"][0]["required_rules"].append("rules/does-not-exist.md")
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(directory, broken)
            self.assertTrue(any("missing routed rule" in item for item in validate(self.skill_root, path)))

    def test_primary_owner_outside_route_fails(self) -> None:
        broken = copy.deepcopy(self.payload)
        broken["triggers"][0]["primary_owner"] = "rules/00-project-orchestration.md"
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(directory, broken)
            self.assertTrue(any("primary_owner is not in its route" in item for item in validate(self.skill_root, path)))

    def test_removing_unique_business_route_makes_rule_unreachable(self) -> None:
        broken = copy.deepcopy(self.payload)
        broken["triggers"] = [
            item for item in broken["triggers"]
            if item["trigger_id"] not in {"TR-CLOSURE", "TR-SKILL-MAINTENANCE"}
        ]
        recovery = next(item for item in broken["triggers"] if item["trigger_id"] == "TR-RECOVERY")
        recovery["required_rules"].remove("rules/00-project-orchestration.md")
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_payload(directory, broken)
            self.assertTrue(any("unreachable rules" in item for item in validate(self.skill_root, path)))


if __name__ == "__main__":
    unittest.main()
