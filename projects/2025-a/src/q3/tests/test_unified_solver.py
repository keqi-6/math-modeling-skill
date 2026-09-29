from __future__ import annotations

import math
import unittest

import numpy as np

from src.q3 import solve


class UnifiedQ3SolverTests(unittest.TestCase):
    def test_service_event_reconstructs_centre_sightline(self) -> None:
        event = solve.service_event_for_track(
            solve.LEGACY_INCUMBENT["heading_rad"],
            solve.LEGACY_INCUMBENT["speed_mps"],
            5.0,
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertLess(event.horizontal_residual_m, 1e-6)
        self.assertLess(event.vertical_residual_m, 1e-7)
        self.assertGreater(event.sight_fraction, 0.0)
        self.assertLess(event.sight_fraction, 1.0)

    def test_legacy_release_gap_and_sink(self) -> None:
        decision = solve.legacy_decision()
        release = np.asarray(decision.release_times_s)
        self.assertTrue(np.all(np.diff(release) >= 1.0 - 1e-10))
        t0 = float(solve.kernel.explosion_times(decision)[0])
        centers = solve.kernel.cloud_center(decision, 0, np.array([t0, t0 + 1.0]))
        self.assertAlmostEqual(float(centers[0, 2] - centers[1, 2]), 3.0, places=10)

    def test_service_curve_and_schedule_are_deterministic(self) -> None:
        heading = solve.LEGACY_INCUMBENT["heading_rad"]
        speed = solve.LEGACY_INCUMBENT["speed_mps"]
        first = solve.service_curve(heading, speed)
        second = solve.service_curve(heading, speed)
        self.assertEqual(first, second)
        self.assertGreater(len(first), 3)
        times = np.arange(0.0, solve.global_contribution_time_cap(), solve.PROXY_STEP_S)
        selected = solve.select_curve_events(heading, speed, first, times)
        self.assertEqual(
            solve.schedule_curve(heading, speed, selected, times, "test"),
            solve.schedule_curve(heading, speed, selected, times, "test"),
        )

        schedules = []
        chosen_track = None
        for track in solve.initial_track_bank():
            record = solve.score_track(track, times)
            if record is not None:
                schedules = record["schedules"]
                chosen_track = track
                break
        self.assertIsNotNone(chosen_track, "no initial physical track admits three gap-feasible service events")
        self.assertGreater(len(schedules), 0)
        for schedule in schedules:
            release = schedule["decision"].release_times_s
            self.assertGreaterEqual(release[1] - release[0], 1.0 - 1e-10)
            self.assertGreaterEqual(release[2] - release[1], 1.0 - 1e-10)

    def test_unit_mapping_preserves_constraints(self) -> None:
        decision = solve.legacy_decision()
        reconstructed = solve.unit_to_decision(
            solve.decision_to_unit(decision), "roundtrip", 0,
        )
        solve.kernel.validate_decision(reconstructed)
        self.assertTrue(math.isfinite(solve.kernel.minimum_constraint_margin(reconstructed)))
        self.assertTrue(np.all(np.diff(reconstructed.release_times_s) >= 1.0 - 1e-10))


if __name__ == "__main__":
    unittest.main()
