"""Focused unit checks for the Q1 deterministic implementation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model import (  # noqa: E402
    Q1Error,
    Q1Parameters,
    analytic_margin,
    circle_margins,
    continuous_circle_max,
    dense_margin,
    default_parameters,
    full_surface_margin,
    geometry_possible_window,
    internal_checks,
    kinematics,
    primary_margin,
    recover_unsampled_intervals,
    segment_distance,
    solve_intervals,
    target_circle,
)


class Q1ImplementationTests(unittest.TestCase):
    def test_frozen_kinematics(self) -> None:
        info = kinematics(default_parameters())
        np.testing.assert_allclose(info["release_point_m"], [17620.0, 0.0, 1800.0], atol=1e-9, rtol=0.0)
        np.testing.assert_allclose(info["explosion_point_m"], [17188.0, 0.0, 1736.496], atol=1e-9, rtol=0.0)
        self.assertAlmostEqual(float(info["explosion_time_s"]), 5.1, places=12)

    def test_segment_clips_to_finite_endpoints(self) -> None:
        distances, lambdas = segment_distance(
            np.array([0.0, 0.0, 0.0]),
            np.array([1.0, 0.0, 0.0]),
            np.array([[2.0, 0.0, 0.0], [0.0, 0.0, 0.0]]),
        )
        np.testing.assert_allclose(distances, [1.0, 0.0])
        np.testing.assert_allclose(lambdas, [-1.0, 1.0])

    def test_all_segment_projection_branches(self) -> None:
        missile = np.array([0.0, 0.0, 0.0])
        point = np.array([[2.0, 0.0, 0.0]])
        cases = [
            (np.array([-1.0, 0.0, 0.0]), -0.5, 1.0),
            (np.array([1.0, 1.0, 0.0]), 0.5, 1.0),
            (np.array([3.0, 0.0, 0.0]), 1.5, 1.0),
        ]
        for cloud, expected_lambda, expected_distance in cases:
            distances, lambdas = segment_distance(cloud, missile, point)
            self.assertAlmostEqual(float(lambdas[0]), expected_lambda, places=14)
            self.assertAlmostEqual(float(distances[0]), expected_distance, places=14)

    def test_circle_interface_shape_and_dtype(self) -> None:
        p = default_parameters()
        theta = np.array([0.0, np.pi / 2.0, np.pi])
        points = target_circle(theta, p.target_base_center[2], p)
        margins, lambdas = circle_margins(theta, 8.75, p.target_base_center[2], p)
        self.assertEqual(points.shape, (3, 3))
        self.assertEqual(margins.shape, (3,))
        self.assertEqual(lambdas.shape, (3,))
        self.assertEqual(points.dtype, np.float64)
        self.assertTrue(np.all(np.isfinite(margins)))

    def test_active_window_boundaries(self) -> None:
        p = default_parameters()
        start, stop = kinematics(p)["active_window_s"]
        self.assertTrue(np.isinf(primary_margin(float(start) - 1e-9, p)["margin_m"]))
        self.assertTrue(np.isfinite(primary_margin(float(start), p)["margin_m"]))
        self.assertTrue(np.isfinite(primary_margin(float(stop), p)["margin_m"]))
        self.assertTrue(np.isinf(primary_margin(float(stop) + 1e-9, p)["margin_m"]))

    def test_geometry_window_is_a_strict_safe_subset_for_q1(self) -> None:
        p = default_parameters()
        pruning = geometry_possible_window(p)
        self.assertEqual(pruning["reasons"], [])
        self.assertGreater(float(pruning["pruned_fraction"]), 0.70)
        self.assertLess(float(pruning["possible_window_s"][1]), float(pruning["active_window_s"][1]))
        pruned = solve_intervals(p, scan_step=0.01, n_theta=256, geometry_pruning=True)
        full = solve_intervals(p, scan_step=0.01, n_theta=256, geometry_pruning=False)
        np.testing.assert_allclose(pruned["intervals_s"], full["intervals_s"], atol=1e-8, rtol=0.0)
        self.assertAlmostEqual(pruned["effective_duration_s"], full["effective_duration_s"], places=9)
        self.assertLess(pruned["scan_count"], full["scan_count"])

    def test_flat_circle_endpoint_branch(self) -> None:
        p = default_parameters()
        stop = float(kinematics(p)["active_window_s"][1])
        theta = np.linspace(0.0, 2.0 * np.pi, 257, endpoint=False)
        margins, lambdas = circle_margins(theta, stop, p.target_base_center[2], p)
        self.assertLessEqual(float(np.ptp(margins)), 1e-12)
        self.assertTrue(np.all(lambdas < 0.0))
        observed = continuous_circle_max(stop, p.target_base_center[2], p, 256)
        self.assertAlmostEqual(observed["margin_m"], float(margins[0]), places=11)

    def test_independent_geometry_paths_agree(self) -> None:
        p = default_parameters()
        time = 8.75
        primary = primary_margin(time, p, 4096)
        dense = dense_margin(time, p, 131072)
        analytic = analytic_margin(time, p)
        self.assertLessEqual(abs(primary["margin_m"] - dense["margin_m"]), 1e-6)
        self.assertLessEqual(abs(primary["margin_m"] - float(analytic["margin_m"])), 1e-6)

    def test_full_surface_interface_does_not_assume_end_ring_scope(self) -> None:
        p = default_parameters()
        full = full_surface_margin(8.75, p, n_theta=64, n_levels=9)
        rings = dense_margin(8.75, p, n_theta=64)
        self.assertGreaterEqual(int(full["surface_point_count"]), 64 * 9)
        self.assertIn(full["surface_kind"], {"side", "bottom_cap", "top_cap"})
        # End rings are a subset of the full mesh; the general evaluator may
        # be more conservative but must never report a smaller sampled max.
        self.assertGreaterEqual(float(full["margin_m"]) + 1e-12, float(rings["margin_m"]))

    def test_invalid_direction_is_rejected(self) -> None:
        p = default_parameters()
        broken = Q1Parameters(**{**p.__dict__, "uav_direction": np.array([-2.0, 0.0, 0.0])})
        with self.assertRaises(Q1Error):
            kinematics(broken)

    def test_invalid_physical_scale_is_rejected(self) -> None:
        p = default_parameters()
        broken = Q1Parameters(**{**p.__dict__, "target_radius": 0.0})
        with self.assertRaises(Q1Error) as context:
            kinematics(broken)
        self.assertEqual(context.exception.code, "Q1_INVALID_INPUT")

    def test_infeasible_explosion_is_rejected(self) -> None:
        p = default_parameters()
        broken = Q1Parameters(**{**p.__dict__, "fuse_delay": 30.0})
        with self.assertRaises(Q1Error) as context:
            kinematics(broken)
        self.assertEqual(context.exception.code, "Q1_INFEASIBLE_EXPLOSION")

    def test_degenerate_segment_is_rejected(self) -> None:
        with self.assertRaises(Q1Error) as context:
            segment_distance(
                np.zeros(3), np.ones(3), np.ones((1, 3)),
            )
        self.assertEqual(context.exception.code, "Q1_GEOMETRY_NONFINITE")

    def test_too_small_angular_grid_is_rejected(self) -> None:
        p = default_parameters()
        with self.assertRaises(Q1Error) as context:
            continuous_circle_max(8.75, p.target_base_center[2], p, 16)
        self.assertEqual(context.exception.code, "Q1_INVALID_INPUT")

    def test_deterministic_repeat(self) -> None:
        p = default_parameters()
        first = primary_margin(8.75, p, 2048)
        second = primary_margin(8.75, p, 2048)
        self.assertEqual(first, second)

    def test_positive_sampled_local_minimum_recovers_short_interval(self) -> None:
        times = np.array([0.0, 1.0, 2.0])
        function = lambda time: (float(time) - 1.2) ** 2 - 0.01
        margins = np.asarray([function(time) for time in times])
        self.assertTrue(np.all(margins > 0.0))
        recovered = recover_unsampled_intervals(
            times, margins, function, time_tolerance=1e-10, margin_tolerance=1e-8,
        )
        self.assertEqual(recovered["checked_local_minima"], 1)
        self.assertEqual(len(recovered["recovered_intervals_s"]), 1)
        left, right = recovered["recovered_intervals_s"][0]
        self.assertAlmostEqual(left, 1.1, places=7)
        self.assertAlmostEqual(right, 1.3, places=7)

    def test_internal_checks(self) -> None:
        self.assertEqual(internal_checks(default_parameters())["status"], "pass")


if __name__ == "__main__":
    unittest.main()
