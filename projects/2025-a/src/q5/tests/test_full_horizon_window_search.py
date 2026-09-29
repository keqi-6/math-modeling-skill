import unittest

import numpy as np

from src.q3 import selection_pilot as q3
from src.q5 import full_condition_search as full
from src.q5 import full_horizon_window_search as horizon
from src.q5 import solve as q5


class Q5FullHorizonWindowSearchTests(unittest.TestCase):
    def test_window_family_contains_exact_full_horizon_endpoint(self):
        starts = horizon.window_starts(full.EARLIEST_ARRIVAL_S, 8., .5)
        self.assertEqual(starts[0], 0.)
        self.assertAlmostEqual(starts[-1] + 8., full.EARLIEST_ARRIVAL_S, places=12)
        self.assertLessEqual(float(np.max(np.diff(starts))), .5 + 1e-12)
        self.assertGreater(len(starts), 100)

    def test_each_window_contains_both_endpoints(self):
        times = horizon.window_times(52.36647340296691, 8., .5)
        self.assertEqual(times[0], 52.36647340296691)
        self.assertAlmostEqual(times[-1], 60.36647340296691, places=12)
        self.assertEqual(len(times), 17)

    def test_retimed_incumbent_is_valid_at_early_and_late_windows(self):
        incumbent, _ = horizon.load_incumbent()
        for delta in (-16., 36.):
            candidate = horizon.retime_decision(incumbent, delta)
            q5.validate(candidate)
            self.assertEqual(len(candidate.bombs), 15)
            self.assertTrue(all(len(q5.by_platform(candidate, i)) == 3 for i in range(5)))

    def test_window_objective_is_worst_node_not_average(self):
        score_a, metric_a = horizon.margin_metrics(np.array([-2., -2., 1.]))
        score_b, metric_b = horizon.margin_metrics(np.array([.5, .5, .5]))
        self.assertGreater(score_b, score_a)
        self.assertEqual(metric_a["maximum_margin_m"], 1.)
        self.assertFalse(metric_a["proxy_feasible"])
        self.assertTrue(horizon.margin_metrics(np.array([-1., 0.]))[1]["proxy_feasible"])

    def test_window_score_is_label_invariant_for_all_three_missiles(self):
        incumbent, _ = horizon.load_incumbent()
        changed = full.relabel(incumbent)
        mesh = q3.surface_mesh(12, 3)
        times = horizon.window_times(16., 2., .5)
        score_a, metric_a = horizon.window_score(incumbent, times, mesh)
        score_b, metric_b = horizon.window_score(changed, times, mesh)
        self.assertEqual(score_a, score_b)
        self.assertEqual(metric_a, metric_b)


if __name__ == "__main__":
    unittest.main()
