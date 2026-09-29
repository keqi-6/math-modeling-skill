import unittest

import numpy as np

from src.q5 import geometry_pilot as geometry
from src.q5 import global_window_pilot as global_pilot
from src.q5 import multi_event_continuous as multi
from src.q5 import solve as q5


def fake_event(release, fuse=1., label=0, mask=0):
    event = geometry.Event(
        2, 1.2, 100., 0., release, fuse, (1., 2., 3.),
        0, (0, 0, 0), label, "test",
    )
    return global_pilot.GlobalEvent(event, mask, release + fuse)


class Q5MultiEventContinuousTests(unittest.TestCase):
    def test_seed_is_existing_multi_event_continuous_lower_bound(self):
        decision, summary = multi.load_seed()
        self.assertEqual(len(decision.bombs), 11)
        self.assertGreater(summary["longest_continuous_s"], 7.7)
        self.assertEqual(len(q5.by_platform(decision, 2)), 1)
        q5.validate(decision)

    def test_proxy_union_allows_two_partial_clouds_to_complete_surface(self):
        times = np.array([1., 1.25, 1.5])
        universe = [0b1111, 0b1111 << 4, 0b1111 << 8]
        left = 0b0011 | (0b0011 << 4) | (0b0011 << 8)
        right = 0b1100 | (0b1100 << 4) | (0b1100 << 8)
        self.assertEqual(multi.proxy_metrics(left, times, universe, .25)["longest_full_node_run_s"], 0.)
        self.assertEqual(multi.proxy_metrics(right, times, universe, .25)["longest_full_node_run_s"], 0.)
        joined = multi.proxy_metrics(left | right, times, universe, .25)
        self.assertAlmostEqual(joined["longest_full_node_run_s"], .5)
        self.assertEqual(joined["full_time_node_count"], 3)

    def test_temporal_handoff_allows_single_joint_single_full_cover(self):
        """A full -> A+B partial union -> B full is one continuous interval."""
        times = np.array([1., 1.25, 1.5])
        universe = [0b1111, 0b1111 << 4, 0b1111 << 8]
        cloud_a = 0b1111 | (0b0011 << 4)
        cloud_b = (0b1100 << 4) | (0b1111 << 8)

        a_only = multi.proxy_metrics(cloud_a, times, universe, .25)
        b_only = multi.proxy_metrics(cloud_b, times, universe, .25)
        handoff = multi.proxy_metrics(cloud_a | cloud_b, times, universe, .25)

        self.assertEqual(a_only["full_time_node_count"], 1)
        self.assertEqual(b_only["full_time_node_count"], 1)
        self.assertEqual(handoff["full_time_node_count"], 3)
        self.assertEqual(handoff["longest_full_node_interval_s"], [1., 1.5])
        self.assertAlmostEqual(handoff["longest_full_node_run_s"], .5)

    def test_plan_compatibility_enforces_one_second_release_gap(self):
        self.assertFalse(multi.compatible((fake_event(2.), fake_event(2.9))))
        self.assertTrue(multi.compatible((fake_event(2.), fake_event(3.))))

    def test_proxy_decision_replaces_one_platform_with_one_fixed_track(self):
        seed, _ = multi.load_seed()
        bomb = q5.by_platform(seed, 2)[0]
        event = multi.event_from_bomb(seed, bomb)
        track = geometry.Track(2, seed.headings_rad[2], seed.speeds_mps[2], "test", -1, -1)
        plan = multi.ProxyPlan(track, (global_pilot.GlobalEvent(event, 1, bomb.release_s + bomb.fuse_s),),
                               1, 1, (0., 0, 0., 0.))
        rebuilt = multi.decision_from_proxy_plan(seed, plan)
        q5.validate(rebuilt)
        self.assertEqual(len(rebuilt.bombs), len(seed.bombs))
        self.assertEqual(rebuilt.headings_rad[2], track.heading)
        self.assertEqual(rebuilt.speeds_mps[2], track.speed)

    def test_longest_run_does_not_add_disconnected_nodes(self):
        times = np.array([1., 1.25, 1.5, 1.75, 2.])
        interval, duration = multi._longest_boolean_run(
            times, [True, True, False, True, True], .25
        )
        self.assertEqual(interval, [1., 1.25])
        self.assertAlmostEqual(duration, .25)


if __name__ == "__main__":
    unittest.main()
