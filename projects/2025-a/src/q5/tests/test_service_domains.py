import math
import unittest

import numpy as np

from src.q5 import geometry_audit as audit
from src.q5 import service_domains as service
from src.q5 import solve as q5


class Q5ServiceDomainTests(unittest.TestCase):
    def test_closed_form_ball_certificate_matches_dense_lambda_minimum(self):
        missile = service.missile_position(1, 23.)
        cloud = np.array([9000., 350., 900.])
        closed = service.ball_service_value(cloud, missile)
        lambdas = np.linspace(0., 1., 200001)
        direction = service.TARGET_MIDPOINT - missile
        centres = missile[None, :] + lambdas[:, None] * direction[None, :]
        radii = q5.p().smoke_radius - lambdas * service.TARGET_ENVELOPE_RADIUS
        brute = np.min(np.sum((cloud[None, :] - centres) ** 2, axis=1) - radii ** 2)
        self.assertLessEqual(abs(closed["value_m2"] - brute), 2e-4)

    def test_midpoint_core_is_in_every_missile_safe_domain(self):
        cloud = service.TARGET_MIDPOINT + np.array([.4, -.3, .2])
        for missile_index in range(3):
            missile = service.missile_position(missile_index, 40.)
            certificate = service.ball_service_value(cloud, missile)
            self.assertTrue(certificate["covered"])
            self.assertLessEqual(certificate["value_m2"], 0.)

    def test_shape_certificate_contains_ball_certificate_point(self):
        missile = service.missile_position(0, 20.)
        lam = .7
        cloud = missile + lam * (service.TARGET_MIDPOINT - missile) + np.array([0., 0., .5])
        ball = service.ball_service_value(cloud, missile)
        shape = service.shape_service_value(cloud, missile)
        self.assertTrue(ball["covered"])
        self.assertTrue(shape["covered"])

    def test_reachable_slice_reconstruction_closes_forward_kinematics(self):
        row = service.reachable_ball_gap(2, 0, 50., 4., .82, reconstruct=True)
        event = row["event"]
        rebuilt = audit.independent_cloud(
            q5.ORIGINS[2], event["heading_rad"], event["speed_mps"],
            event["release_s"], event["fuse_s"], event["observation_s"],
        )
        self.assertLess(np.linalg.norm(rebuilt - event["cloud_centre_m"]), 1e-7)
        self.assertGreaterEqual(event["speed_mps"], 70. - 1e-9)
        self.assertLessEqual(event["speed_mps"], 140. + 1e-9)
        self.assertGreaterEqual(event["release_s"], -1e-9)

    def test_perspective_shadow_quadratic_matches_ray_distance(self):
        missile = service.missile_position(0, 20.)
        cloud = missile + .6 * (service.TARGET_MIDPOINT - missile)
        frame = service.perspective_frame(missile)
        points = service.TARGET_MIDPOINT + np.array([
            [0., 0., 0.], [0., 7., 0.], [0., -7., 0.], [0., 0., 5.], [0., 0., -5.]
        ])
        for point in points:
            projected = service.project_to_perspective_plane(missile, point, frame)["point_m"]
            shadow = service.sphere_shadow_value(cloud, missile, projected)
            direction = point - missile
            line_distance = np.linalg.norm(np.cross(cloud - missile, direction)) / np.linalg.norm(direction)
            expected = line_distance <= q5.p().smoke_radius + 1e-10
            self.assertEqual(shadow["inside_shadow"], expected)

    def test_shadow_after_target_is_rejected_by_finite_segment(self):
        missile = service.missile_position(0, 20.)
        target = service.TARGET_MIDPOINT
        unit = (target - missile) / np.linalg.norm(target - missile)
        cloud = target + 20. * unit
        projected = service.project_to_perspective_plane(missile, target)["point_m"]
        self.assertTrue(service.sphere_shadow_value(cloud, missile, projected)["inside_shadow"])
        self.assertFalse(service.finite_segment_covered(cloud, missile, target))

    def test_fy3_can_reach_common_core_late_in_horizon(self):
        for missile_index in range(3):
            result = service.minimum_service_gap(2, missile_index, 55., age_nodes=31, lambda_nodes=41)
            self.assertTrue(result["feasible"])
            self.assertLessEqual(result["event"]["certificate_value_m2"], 1e-7)

    def test_reconstructed_safe_event_passes_production_surface_oracle(self):
        platform_index, missile_index, observation = 2, 1, 55.
        result = service.minimum_service_gap(
            platform_index, missile_index, observation, age_nodes=31, lambda_nodes=41
        )
        event = result["event"]
        headings = [0.] * 5
        speeds = [70.] * 5
        headings[platform_index] = event["heading_rad"]
        speeds[platform_index] = event["speed_mps"]
        decision = q5.Decision(
            tuple(headings), tuple(speeds),
            (q5.Bomb(platform_index, missile_index, event["release_s"], event["fuse_s"]),),
            "service_domain_test",
        )
        q5.validate(decision)
        mesh = q5.q3.surface_mesh(64, 9)
        margin = q5.strict_margins(decision, missile_index, [observation], mesh)[0]
        self.assertLessEqual(margin, 1e-8)


if __name__ == "__main__":
    unittest.main()
