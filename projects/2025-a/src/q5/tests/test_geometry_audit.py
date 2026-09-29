import math
import unittest

import numpy as np

from src.q3 import selection_pilot as q3
from src.q5 import geometry_audit as audit
from src.q5 import geometry_pilot as geometry
from src.q5 import solve as q5


class Q5GeometryAuditTests(unittest.TestCase):
    def test_reference_segment_distance_clips_both_endpoints(self):
        missile = np.array([10., 0., 0.])
        point = np.array([0., 0., 0.])
        self.assertAlmostEqual(audit.reference_segment_distance([15., 0., 0.], missile, point), 5.)
        self.assertAlmostEqual(audit.reference_segment_distance([-5., 0., 0.], missile, point), 5.)
        self.assertAlmostEqual(audit.reference_segment_distance([5., 3., 0.], missile, point), 3.)

    def test_reference_distance_agrees_with_production_vector_path(self):
        mesh = q3.surface_mesh(19, 5)
        missile = geometry.missile(1, 17.)
        cloud = np.array([9000., 300., 800.])
        production = q3._distance_to_segments(cloud[None, :], missile[None, :], mesh)[0]
        reference = np.array([
            audit.reference_segment_distance(cloud, missile, point) for point in mesh.points
        ])
        self.assertLessEqual(float(np.max(np.abs(production - reference))), audit.DISTANCE_TOL_M)

    def test_ray_first_hit_distinguishes_near_and_far_cylinder_side(self):
        missile = np.array([20., 0., 5.])
        base = np.zeros(3)
        near = audit.ray_cylinder_first_hit(missile, [1., 0., 1.], base, 1., 2.)
        far = audit.ray_cylinder_first_hit(missile, [-1., 0., 1.], base, 1., 2.)
        self.assertAlmostEqual(near, 1., places=10)
        self.assertLess(far, 1.)

    def test_midpoint_centreline_has_analytic_full_cover_certificate(self):
        p = q5.p()
        envelope = math.hypot(p.target_radius, p.target_height / 2)
        self.assertLess(envelope, p.smoke_radius)
        missile = audit.independent_missile(0, 20.)
        centre = p.target_base_center + np.array([0., 0., p.target_height / 2])
        fraction = .73
        cloud = missile + fraction * (centre - missile)
        points = audit.independent_surface(72, 11)
        maximum = max(audit.reference_segment_distance(cloud, missile, point) for point in points)
        self.assertLessEqual(maximum, fraction * envelope + 1e-9)

    def test_inverse_track_reconstructs_forward_cloud(self):
        platform = 3
        heading, speed, release, fuse, age = 4.2, 123., 3.4, 5.1, 2.3
        observation = release + fuse + age
        cloud = audit.independent_cloud(
            q5.ORIGINS[platform], heading, speed, release, fuse, observation
        )
        solved = geometry.inverse_track(platform, observation, age, cloud.copy())
        self.assertIsNotNone(solved)
        got_heading, got_speed, got_release, got_fuse = solved
        rebuilt = audit.independent_cloud(
            q5.ORIGINS[platform], got_heading, got_speed, got_release, got_fuse, observation
        )
        self.assertLess(np.linalg.norm(rebuilt - cloud), audit.POSITION_TOL_M)
        self.assertLess(audit.circular_error(got_heading, heading), 1e-10)
        self.assertAlmostEqual(got_speed, speed, places=9)
        self.assertAlmostEqual(got_release, release, places=9)
        self.assertAlmostEqual(got_fuse, fuse, places=9)

    def test_full_obscuration_quantifier_uses_union_per_surface_point(self):
        missile = np.array([10., 0., 0.])
        points = np.array([[0., -1., 0.], [0., 1., 0.]])
        clouds = (np.array([5., -1., 0.]), np.array([5., 1., 0.]))
        radius = .6
        cover = np.array([
            [audit.reference_segment_distance(cloud, missile, point) <= radius for point in points]
            for cloud in clouds
        ])
        self.assertFalse(np.any(np.all(cover, axis=1)))
        self.assertTrue(np.all(np.any(cover, axis=0)))


if __name__ == "__main__":
    unittest.main()
