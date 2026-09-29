from __future__ import annotations

import unittest

from src.q5_v2.objectives import (
    from_interval_sets,
    from_q5_evaluation,
    lexicographic_better,
    pareto_dominates,
)


class ObjectiveMetricTests(unittest.TestCase):
    def test_same_missile_overlap_is_unioned_before_measure(self):
        metrics = from_interval_sets(
            [
                [(0.0, 4.0), (2.0, 6.0), (8.0, 9.0)],
                [(0.0, 1.0)],
                [(0.0, 1.0)],
            ]
        )
        self.assertEqual(metrics.per_missile_intervals_s[0], ((0.0, 6.0), (8.0, 9.0)))
        self.assertEqual(metrics.per_missile_duration_s, (7.0, 1.0, 1.0))
        self.assertEqual(metrics.j_sum_missile_s, 9.0)

    def test_noncontinuous_components_all_count_in_primary_objective(self):
        metrics = from_interval_sets(
            [
                [(0.0, 2.0), (10.0, 13.0)],
                [(1.0, 3.0), (11.0, 14.0)],
                [(1.5, 2.5), (12.0, 15.0)],
            ]
        )
        self.assertEqual(metrics.per_missile_duration_s, (5.0, 5.0, 4.0))
        self.assertEqual(metrics.j_sum_missile_s, 14.0)
        self.assertEqual(metrics.intersection_intervals_s, ((1.5, 2.0), (12.0, 13.0)))
        self.assertEqual(metrics.j_all_s, 1.5)
        self.assertEqual(metrics.longest_all_interval_s, (12.0, 13.0))
        self.assertEqual(metrics.l_all_s, 1.0)

    def test_primary_sum_is_not_traded_for_secondary_metrics(self):
        incumbent = from_interval_sets([[(0.0, 4.0)], [(0.0, 4.0)], [(0.0, 4.0)]])
        candidate = from_interval_sets([[(0.0, 3.9)], [(0.0, 3.9)], [(0.0, 3.9)]])
        self.assertFalse(lexicographic_better(candidate, incumbent))

    def test_pareto_dominance_requires_no_metric_loss(self):
        strong = from_interval_sets([[(0.0, 5.0)], [(0.0, 4.0)], [(0.0, 4.0)]])
        weak = from_interval_sets([[(0.0, 4.0)], [(0.0, 4.0)], [(0.0, 4.0)]])
        tradeoff = from_interval_sets([[(0.0, 8.0)], [(6.0, 10.0)], [(6.0, 10.0)]])
        self.assertTrue(pareto_dominates(strong, weak))
        self.assertFalse(pareto_dominates(tradeoff, weak))

    def test_existing_q5_evaluation_is_recomputed_and_checked(self):
        evaluation = {
            "by_missile": [
                {"intervals_s": [[0.0, 3.0], [2.0, 4.0]]},
                {"intervals_s": [[1.0, 5.0]]},
                {"intervals_s": [[2.0, 6.0]]},
            ],
            "sum_duration_missile_s": 12.0,
            "minimum_missile_duration_s": 4.0,
            "total_intersection_s": 2.0,
            "longest_continuous_s": 2.0,
        }
        metrics = from_q5_evaluation(evaluation)
        self.assertEqual(metrics.official_lexicographic_key, (12.0, 4.0, 2.0, 2.0))
        evaluation["sum_duration_missile_s"] = 13.0
        with self.assertRaises(ValueError):
            from_q5_evaluation(evaluation)


if __name__ == "__main__":
    unittest.main()
