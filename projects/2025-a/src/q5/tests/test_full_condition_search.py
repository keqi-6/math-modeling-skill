import unittest

import numpy as np

from src.q3 import selection_pilot as q3
from src.q5 import full_condition_search as full
from src.q5 import solve as q5


class Q5FullConditionSearchTests(unittest.TestCase):
    def test_decode_covers_all_platform_variables_and_constraints(self):
        decision = full.decode_vector(np.linspace(0.001, 0.999, full.VECTOR_SIZE))
        q5.validate(decision)
        self.assertEqual(len(decision.headings_rad), 5)
        self.assertEqual(len(decision.speeds_mps), 5)
        self.assertEqual(len(decision.bombs), 15)
        self.assertTrue(all(len(q5.by_platform(decision, i)) == 3 for i in range(5)))
        self.assertGreaterEqual(q5.constraint_margins(decision)["one_second_gap_s"], -1e-8)

    def test_seed_roundtrip_preserves_original_bombs_and_adds_only_capacity(self):
        seed, _ = full.load_seed()
        augmented = full.decode_vector(full.encode_decision(seed))
        self.assertEqual(len(augmented.bombs), 15)
        for original in seed.bombs:
            candidates = q5.by_platform(augmented, original.platform)
            self.assertTrue(any(abs(row.release_s - original.release_s) < 1e-9 and
                                abs(row.fuse_s - original.fuse_s) < 1e-9 for row in candidates))

    def test_labels_do_not_change_strict_geometry(self):
        seed, _ = full.load_seed()
        changed = full.relabel(seed)
        mesh = q3.surface_mesh(12, 3)
        times = np.array([16., 20., 23.])
        for j in range(3):
            np.testing.assert_allclose(
                q5.strict_margins(seed, j, times, mesh),
                q5.strict_margins(changed, j, times, mesh), atol=0., rtol=0.,
            )

    def test_longest_run_does_not_sum_disconnected_components(self):
        times = np.arange(0., 3.5, .5)
        duration, interval, count = full._longest_run(
            times, np.array([True, True, False, True, True, True, False])
        )
        self.assertEqual(duration, 1.)
        self.assertEqual(interval, [1.5, 2.5])
        self.assertEqual(count, 3)

    def test_random_vectors_span_every_platform_block(self):
        rng = np.random.default_rng(7)
        rows = np.vstack([full.random_vector(rng) for _ in range(20)])
        self.assertEqual(rows.shape, (20, 40))
        for i in range(5):
            self.assertGreater(float(np.ptp(rows[:, 8 * i:8 * i + 8])), .5)


if __name__ == "__main__":
    unittest.main()
