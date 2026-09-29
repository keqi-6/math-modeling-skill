"""Semantic unit and boundary tests for the frozen Q2 formal solver."""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]
Q2_SRC = ROOT / "src/q2"
if str(Q2_SRC) not in sys.path:
    sys.path.insert(0, str(Q2_SRC))

import solve as formal  # noqa: E402
import reselection_pilot as pilot  # noqa: E402


RESULT_PATH = ROOT / "docs/q2_result.json"


class Q2SemanticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    def test_frozen_identities_are_current(self) -> None:
        observed = formal.verify_identities()
        self.assertEqual(observed[formal.INPUT_PATH.as_posix()], formal.INPUT_SHA)
        self.assertEqual(observed[formal.SPEC_PATH.as_posix()], formal.SPEC_SHA)

    def test_unit_mapping_round_trip_for_formal_finalists(self) -> None:
        for item in self.result["precise_finalists"]:
            source = item["decision"]
            decision = pilot.Decision(
                heading_rad=float(source["heading_rad"]),
                speed_mps=float(source["speed_mps"]),
                release_time_s=float(source["release_time_s"]),
                fuse_delay_s=float(source["fuse_delay_s"]),
                source_domain="roundtrip_test",
            )
            recovered = formal.unit_to_decision(formal.decision_to_unit(decision), "roundtrip_test")
            self.assertLessEqual(formal.wrapped_angle_difference(decision.heading_rad, recovered.heading_rad), 1e-12)
            self.assertAlmostEqual(decision.speed_mps, recovered.speed_mps, places=11)
            self.assertAlmostEqual(decision.release_time_s, recovered.release_time_s, places=11)
            self.assertAlmostEqual(decision.fuse_delay_s, recovered.fuse_delay_s, places=11)

    def test_unit_cube_corners_are_feasible(self) -> None:
        for values in (
            np.zeros(4),
            np.ones(4),
            np.array([0.0, 1.0, 0.0, 1.0]),
            np.array([1.0, 0.0, 1.0, 0.0]),
        ):
            decision = formal.unit_to_decision(values, "corner_test")
            margins = pilot.constraint_margins(decision)
            self.assertGreaterEqual(min(margins.values()), -1e-8)

    def test_strict_witness_is_inside_analytic_interval(self) -> None:
        intervals = pilot.q_intervals(5.0, 1.0)
        self.assertTrue(any(left < 0.06 < right for left, right in intervals))
        witness = pilot.witness_oracle()
        self.assertEqual(witness["status"], "strict_interior_pass")
        self.assertGreater(min(witness["decision"]["constraint_margins"].values()), 0.0)

    def test_inverse_c3_rejects_fraction_outside_segment(self) -> None:
        for fraction in (-0.01, 1.01):
            with self.assertRaises(pilot.PilotError):
                pilot.inverse_c3(5.0, 1.0, fraction, "invalid_fraction")

    def test_formal_multistart_structure_and_domains(self) -> None:
        records = self.result["multistart_records"]
        self.assertEqual(len(records), 15)
        self.assertEqual(sum(item["source_family"] == "C3-I" for item in records), 7)
        self.assertEqual(sum(item["source_family"] == "C2" for item in records), 8)
        domains = {item["source_domain"] for item in records if item["source_family"] == "C2"}
        self.assertEqual(domains, {"target", "missile", "guard"})

    def test_proxy_fallback_never_selects_worse_exact_screen(self) -> None:
        for item in self.result["multistart_records"]:
            initial = float(item["initial"]["screen"]["effective_duration_s"])
            refined = float(item["refined"]["screen"]["effective_duration_s"])
            chosen = float(item["chosen"]["screen"]["effective_duration_s"])
            self.assertAlmostEqual(chosen, max(initial, refined), places=12)
            if item["chosen"]["origin"] == "initial_proxy_fallback":
                self.assertGreaterEqual(initial, refined)

    def test_formal_outputs_obey_interval_and_constraint_contract(self) -> None:
        for item in self.result["precise_finalists"]:
            decision_data = item["decision"]
            decision = pilot.Decision(
                heading_rad=float(decision_data["heading_rad"]),
                speed_mps=float(decision_data["speed_mps"]),
                release_time_s=float(decision_data["release_time_s"]),
                fuse_delay_s=float(decision_data["fuse_delay_s"]),
                source_domain="validation_test",
            )
            formal.validate_solution(decision, item["precise"])
            self.assertEqual(item["precise"]["geometry_scope"], "arbitrary_control_full_cylinder_mesh")
            duration = sum(float(right) - float(left) for left, right in item["precise"]["intervals_s"])
            self.assertAlmostEqual(duration, float(item["precise"]["effective_duration_s"]), places=10)

    def test_decision_record_recomputes_event_geometry(self) -> None:
        best = self.result["formal_best"]["decision"]
        decision = pilot.Decision(
            heading_rad=float(best["heading_rad"]),
            speed_mps=float(best["speed_mps"]),
            release_time_s=float(best["release_time_s"]),
            fuse_delay_s=float(best["fuse_delay_s"]),
            source_domain="geometry_test",
        )
        recomputed = pilot.decision_record(decision)
        self.assertTrue(np.allclose(recomputed["release_point_m"], best["release_point_m"], atol=1e-9, rtol=0.0))
        self.assertTrue(np.allclose(recomputed["explosion_point_m"], best["explosion_point_m"], atol=1e-9, rtol=0.0))
        self.assertAlmostEqual(recomputed["explosion_time_s"], best["explosion_time_s"], places=12)

    def test_geometry_pruning_preserves_formal_best_at_screen_precision(self) -> None:
        best = self.result["formal_best"]["decision"]
        decision = pilot.Decision(
            heading_rad=float(best["heading_rad"]),
            speed_mps=float(best["speed_mps"]),
            release_time_s=float(best["release_time_s"]),
            fuse_delay_s=float(best["fuse_delay_s"]),
            source_domain="pruning_equivalence_test",
        )
        pruned = pilot.evaluate(decision, formal.SCREEN, geometry_pruning=True)
        full = pilot.evaluate(decision, formal.SCREEN, geometry_pruning=False)
        np.testing.assert_allclose(pruned["intervals_s"], full["intervals_s"], atol=1e-7, rtol=0.0)
        self.assertAlmostEqual(pruned["effective_duration_s"], full["effective_duration_s"], places=8)
        self.assertLess(pruned["scan_count"], full["scan_count"])

    def test_heading_domain_classification_wraps_at_two_pi(self) -> None:
        self.assertEqual(formal.physical_domain(0.0), formal.physical_domain(2.0 * math.pi))
        self.assertEqual(formal.physical_domain(-1e-12), formal.physical_domain(2.0 * math.pi - 1e-12))


if __name__ == "__main__":
    unittest.main()
