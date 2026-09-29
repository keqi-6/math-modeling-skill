from __future__ import annotations

import unittest

from src.q5 import solve


def result(longest, total, summed=0.0, minimum=0.0):
    return {
        "longest_continuous_s": float(longest),
        "total_intersection_s": float(total),
        "sum_duration_missile_s": float(summed),
        "minimum_missile_duration_s": float(minimum),
    }


class LongestObjectiveTests(unittest.TestCase):
    def test_longest_component_uses_one_connected_interval(self):
        interval, duration = solve.longest_component([[1.0, 3.0], [5.0, 8.5], [10.0, 11.0]])
        self.assertEqual(interval, [5.0, 8.5])
        self.assertAlmostEqual(duration, 3.5)

    def test_empty_intersection_has_zero_longest_duration(self):
        interval, duration = solve.longest_component([])
        self.assertIsNone(interval)
        self.assertEqual(duration, 0.0)

    def test_ranking_never_trades_primary_for_secondary(self):
        rows = [
            {"name": "longer", "score": result(7.0, 7.0)},
            {"name": "shorter_large_total", "score": result(6.9999, 100.0)},
        ]
        ranked = solve.ranked(rows, "score", tolerance=1.0)
        self.assertEqual(ranked[0]["name"], "longer")

    def test_acceptance_rejects_any_resolved_primary_loss(self):
        current = result(7.0, 8.0)
        candidate = result(6.999999, 20.0)
        self.assertFalse(solve.better_result(candidate, current))
        self.assertTrue(solve.better_result(result(7.0, 8.1), current))

    def test_historical_seed_is_independent_of_current_spec(self):
        decision, identity = solve.registered_incumbent()
        self.assertEqual(decision.source, "historical_intersection_seed_rescored")
        self.assertEqual(len(identity), 64)
        solve.validate(decision)

    def test_historical_seed_rescores_to_positive_continuous_window(self):
        decision, _ = solve.registered_incumbent()
        score = solve.evaluate(decision, solve.PROBE)
        self.assertGreater(score["longest_continuous_s"], 6.8)
        self.assertGreaterEqual(score["total_intersection_s"], score["longest_continuous_s"])
        self.assertAlmostEqual(score["objective_s"], score["longest_continuous_s"])


if __name__ == "__main__":
    unittest.main()
