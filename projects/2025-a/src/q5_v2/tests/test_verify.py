from __future__ import annotations

import json
import unittest

import numpy as np

from src.q5 import solve as q5
from src.q5_v2.objectives import from_interval_sets
from src.q5_v2.verify import decision_from_payload, independent_margin, invalid_case_results


class Q5V2VerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open("docs/q5_v2_precise.json", encoding="utf-8") as handle:
            cls.payload = json.load(handle)
        cls.decision = decision_from_payload(cls.payload)

    def test_invalid_cases_are_rejected(self) -> None:
        self.assertTrue(all(invalid_case_results(self.decision).values()))

    def test_independent_oracle_matches_small_production_case(self) -> None:
        mesh = q5.q3.surface_mesh(32, 5)
        times = [1.0, 14.0, 21.0]
        independent = independent_margin(self.decision, 0, times, mesh)
        production = q5.strict_margins(self.decision, 0, times, mesh)
        np.testing.assert_allclose(independent, production, rtol=0.0, atol=1e-9)

    def test_interval_algebra_reconstructs_registered_metrics(self) -> None:
        recomputed = from_interval_sets(self.payload["metrics"]["per_missile_intervals_s"])
        self.assertAlmostEqual(recomputed.j_sum_missile_s, self.payload["metrics"]["j_sum_missile_s"], places=11)
        self.assertAlmostEqual(recomputed.j_all_s, self.payload["metrics"]["j_all_s"], places=11)

    def test_multi_cloud_quantifier_counterexample(self) -> None:
        margins = np.array([[-1.0, 1.0], [1.0, -1.0]])
        self.assertGreater(float(np.min(np.max(margins, axis=1))), 0.0)
        self.assertLessEqual(float(np.max(np.min(margins, axis=0))), 0.0)


if __name__ == "__main__":
    unittest.main()
