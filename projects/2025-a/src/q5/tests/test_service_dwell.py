import unittest

import numpy as np

from src.q5 import geometry_audit as audit
from src.q5 import service_dwell as dwell
from src.q5 import solve as q5


class Q5FixedEventDwellTests(unittest.TestCase):
    def test_fixed_event_forward_trajectory_closes_reconstruction(self):
        result = dwell.minimum_age_gap(0, 0, 8., 0., age_nodes=31)
        self.assertTrue(result["feasible"])
        event = result["event"]
        rebuilt = audit.independent_cloud(
            q5.ORIGINS[0], event["heading_rad"], event["speed_mps"],
            event["release_s"], event["fuse_s"], event["observation_s"],
        )
        forward = dwell.fixed_event_cloud(event, event["observation_s"])
        self.assertLess(np.linalg.norm(rebuilt - forward), 1e-7)
        self.assertLess(np.linalg.norm(forward - event["cloud_centre_m"]), 1e-7)

    def test_lambda_zero_seed_has_short_post_intercept_tail(self):
        result = dwell.minimum_age_gap(0, 0, 8., 0., age_nodes=31)
        interval = dwell.service_interval(result["event"], 0, 8., root_step_s=.05)
        self.assertIsNotNone(interval)
        self.assertGreater(interval["duration_s"], 0.)
        # Requested lambda is fixed only when constructing the seed event.  At
        # earlier times the same cloud can occupy a different optimal section
        # of the service frustum; only the tail after missile/cloud passage is
        # necessarily short.
        self.assertLess(interval["right_s"] - 8., .2)
        self.assertGreater(interval["duration_s"], 1.)
        self.assertLessEqual(abs(interval["left_value_m2"]), 2e-5)
        self.assertLessEqual(abs(interval["right_value_m2"]), 2e-5)

    def test_target_core_event_services_all_three_missiles(self):
        result = dwell.minimum_age_gap(2, 0, 59., 1., age_nodes=41)
        self.assertTrue(result["feasible"])
        variants = dwell.placement_events(2, 0, 59., result["age_s"], 1.)
        common = max(
            (dwell.all_missile_interval(event, 59., root_step_s=.05)
             for _, event in variants),
            key=lambda row: row["duration_s"] if row else -1.,
        )
        self.assertIsNotNone(common)
        expected_diameter_residence = 2. * (10. - np.sqrt(74.)) / 3.
        self.assertAlmostEqual(common["duration_s"], expected_diameter_residence, places=5)
        self.assertLessEqual(common["left_s"], 59.)
        self.assertGreaterEqual(common["right_s"], 59.)

    def test_safe_interval_midpoint_passes_production_surface_oracle(self):
        platform_index, missile_index = 2, 1
        result = dwell.minimum_age_gap(platform_index, missile_index, 55., 1., age_nodes=41)
        interval = dwell.service_interval(result["event"], missile_index, 55., root_step_s=.05)
        self.assertIsNotNone(interval)
        midpoint = .5 * (interval["left_s"] + interval["right_s"])
        decision = dwell.fixed_event_decision(result["event"], missile_index)
        mesh = q5.q3.surface_mesh(64, 9)
        strict_margin = q5.strict_margins(decision, missile_index, [midpoint], mesh)[0]
        self.assertLessEqual(strict_margin, 1e-8)

    def test_fixed_lambda_age_minimum_is_not_worse_than_dense_check(self):
        result = dwell.minimum_age_gap(3, 1, 30., .6, age_nodes=41)
        ages = np.linspace(0., 20., 2001)
        dense = min(dwell.service.reachable_ball_gap(3, 1, 30., float(age), .6)["gap_m2"]
                    for age in ages)
        self.assertLessEqual(result["optimized_gap_m2"], dense + 1e-6)


if __name__ == "__main__":
    unittest.main()
