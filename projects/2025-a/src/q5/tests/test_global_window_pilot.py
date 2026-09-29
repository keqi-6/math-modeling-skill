import unittest

from src.q5 import global_window_pilot as pilot


class GlobalWindowPilotContractTests(unittest.TestCase):
    def test_horizon_is_earliest_missile_arrival(self):
        self.assertAlmostEqual(pilot.HORIZON_S, min(pilot.q5.ARRIVAL_TIMES), places=12)
        self.assertGreater(pilot.HORIZON_S, 60.)
        self.assertLess(pilot.HORIZON_S, 61.)

    def test_duration_ladder_reaches_sixty_seconds(self):
        self.assertEqual(pilot.DURATION_LADDER_S[-1], 60.)
        self.assertIn(10., pilot.DURATION_LADDER_S)

    def test_window_catalog_is_global_not_incumbent_anchored(self):
        windows = pilot.window_catalog(durations=(10., 60.), start_step_s=5.)
        starts_10 = [row["start_s"] for row in windows if row["duration_s"] == 10.]
        self.assertEqual(starts_10[0], 0.)
        self.assertGreater(starts_10[-1], 45.)
        starts_60 = [row["start_s"] for row in windows if row["duration_s"] == 60.]
        self.assertEqual(starts_60[0], 0.)
        self.assertAlmostEqual(starts_60[-1], pilot.HORIZON_S - 60., places=9)

    def test_proxy_times_include_horizon_and_all_window_endpoints(self):
        windows = pilot.window_catalog(durations=(10., 60.), start_step_s=5.)
        times = pilot.proxy_times(windows)
        self.assertAlmostEqual(times[-1], pilot.HORIZON_S, places=12)
        for row in windows:
            self.assertTrue(any(abs(value - row["start_s"]) <= 1e-9 for value in times))
            self.assertTrue(any(abs(value - row["end_s"]) <= 1e-9 for value in times))

    def test_mask_metrics_requires_every_time_slice(self):
        universes = [0b0011, 0b1100]
        self.assertEqual(pilot.mask_metrics(0b1111, [0, 1], universes)[0], 1)
        self.assertEqual(pilot.mask_metrics(0b1011, [0, 1], universes)[0], 0)
        self.assertAlmostEqual(pilot.mask_metrics(0b1011, [0, 1], universes)[1], .5)


if __name__ == "__main__":
    unittest.main()
