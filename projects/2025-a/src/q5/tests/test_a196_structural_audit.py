import unittest
import json
import tempfile
from pathlib import Path

import numpy as np

from src.q3 import selection_pilot as q3
from src.q5 import a196_structural_audit as audit
from src.q5 import solve as q5


class A196StructuralAuditTests(unittest.TestCase):
    def test_official_fy5_coordinate_and_assignment_are_explicit(self):
        self.assertEqual(float(q5.ORIGINS[4, 1]), -2000.)
        assignments = audit.nearest_missile_assignment()
        self.assertEqual(len(assignments), 5)
        self.assertTrue(all(value in (0, 1, 2) for value in assignments))
        self.assertEqual(
            audit.SOURCE_AUDIT["executable_structure"]["fy5_appendix_coordinate_m"][1],
            2000.,
        )

    def test_structural_decision_has_exact_one_second_release_pattern(self):
        assignment = audit.nearest_missile_assignment()[0]
        seed = audit.paper_intercept_seed(0, assignment, step_s=.02)
        vector = audit.encode_structural(seed, 0, assignment)
        decision = audit.platform_decision(vector, 0, assignment)
        releases = [bomb.release_s for bomb in q5.by_platform(decision, 0)]
        self.assertEqual(len(releases), 3)
        np.testing.assert_allclose(np.diff(releases), [1., 1.], atol=1e-12, rtol=0.)
        fuses = [bomb.fuse_s for bomb in q5.by_platform(decision, 0)]
        np.testing.assert_allclose(fuses, [fuses[0]] * 3, atol=1e-12, rtol=0.)

    def test_closed_unit_heading_boundary_wraps_to_legal_angle(self):
        assignment = audit.nearest_missile_assignment()[0]
        heading, _, _, _ = audit.decode_structural(np.array([1., .5, .2, .2]), 0, assignment)
        self.assertEqual(heading, 0.)
        decision = audit.platform_decision(np.array([1., .5, .2, .2]), 0, assignment)
        q5.validate(decision)

    def test_independent_accumulator_is_not_interval_union(self):
        assignment = audit.nearest_missile_assignment()[0]
        seed = audit.paper_intercept_seed(0, assignment, step_s=.02)
        vector = audit.encode_structural(seed, 0, assignment)
        times = np.arange(0., q5.arrival(assignment), .5)
        mesh = q3.surface_mesh(8, 3)
        _, metric = audit.independent_score(vector, 0, assignment, times, mesh)
        triple = audit.platform_decision(vector, 0, assignment)
        union_flags = q5.strict_margins(triple, assignment, times, mesh) <= 0.
        union_duration = audit.sampled_duration(times, union_flags)
        self.assertGreaterEqual(
            metric["independent_single_cloud_duration_sum_s"] + 1e-12,
            union_duration,
        )

    def test_combined_reproduction_uses_all_five_platforms_and_fifteen_bombs(self):
        rows = []
        for platform_index, missile_index in enumerate(audit.nearest_missile_assignment()):
            rows.append({
                "platform_index": platform_index,
                "assigned_missile_index": missile_index,
                "heading_rad": 0., "speed_mps": 70.,
                "release_times_s": [0., 1., 2.], "shared_fuse_s": 0.,
            })
        decision = audit.combine_platforms(rows, "test")
        self.assertEqual(len(decision.bombs), 15)
        self.assertEqual([len(q5.by_platform(decision, i)) for i in range(5)], [3] * 5)
        q5.validate(decision)

    def test_checkpoint_is_immediately_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            audit.write_checkpoint(path, "unit_test", {"value": np.float64(1.25)})
            payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "running_checkpoint")
        self.assertEqual(payload["stage"], "unit_test")
        self.assertEqual(payload["value"], 1.25)
        self.assertIsInstance(str(np.__version__), str)


if __name__ == "__main__":
    unittest.main()
