from __future__ import annotations

import unittest

from src.q5 import solve as q5
from src.q5_v2.solver import PlatformColumn, combine_columns, proxy_metrics


class SolverContractTests(unittest.TestCase):
    def test_combining_platform_columns_preserves_shared_track(self):
        columns = [
            PlatformColumn(0, 0.1, 80.0, (q5.Bomb(0, 0, 1.0, 1.0),), "a", "base"),
            PlatformColumn(1, 1.2, 90.0, (q5.Bomb(1, 2, 2.0, 1.0),), "b", "base"),
        ]
        decision = combine_columns(columns, [0, 1], "test")
        self.assertEqual(decision.headings_rad[:2], (0.1, 1.2))
        self.assertEqual(decision.speeds_mps[:2], (80.0, 90.0))
        self.assertEqual(len(decision.bombs), 2)

    def test_proxy_metric_requires_complete_surface_coverage(self):
        import numpy as np

        coverage = np.array([[[True, False], [True, True]]], dtype=bool)
        visible = np.ones_like(coverage)
        weights = np.array([[1.0, 1.0]])
        metrics = proxy_metrics(coverage, visible, weights)
        self.assertEqual(metrics["j_sum_missile_s"], 1.0)


if __name__ == "__main__":
    unittest.main()
