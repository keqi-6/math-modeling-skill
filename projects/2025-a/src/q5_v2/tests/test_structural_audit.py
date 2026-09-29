from __future__ import annotations

import unittest

from src.q5 import solve as q5
from src.q5_v2.structural_audit import interval_difference, remove_bombs


class StructuralAuditHelpersTest(unittest.TestCase):
    def test_interval_difference_splits_and_normalizes(self) -> None:
        result = interval_difference([(0.0, 5.0), (6.0, 8.0)], [(1.0, 2.0), (3.0, 7.0)])
        self.assertEqual(result, ((0.0, 1.0), (2.0, 3.0), (7.0, 8.0)))

    def test_interval_difference_empty_subtrahend(self) -> None:
        self.assertEqual(interval_difference([(0.0, 1.0)], []), ((0.0, 1.0),))

    def test_remove_bomb_preserves_other_controls(self) -> None:
        decision = q5.Decision(
            headings_rad=(0.0, 0.0, 0.0, 0.0, 0.0),
            speeds_mps=(70.0, 70.0, 70.0, 70.0, 70.0),
            bombs=(
                q5.Bomb(platform=0, label=0, release_s=0.0, fuse_s=0.0),
                q5.Bomb(platform=0, label=1, release_s=1.0, fuse_s=0.0),
            ),
            source="test",
        )
        reduced = remove_bombs(decision, {0}, "reduced")
        self.assertEqual(reduced.headings_rad, decision.headings_rad)
        self.assertEqual(reduced.speeds_mps, decision.speeds_mps)
        self.assertEqual(reduced.bombs, (decision.bombs[1],))
        self.assertEqual(reduced.source, "reduced")


if __name__ == "__main__":
    unittest.main()
