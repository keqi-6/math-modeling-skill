"""Independent E1/E2 verification for the unified Q3 working solver."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import subprocess
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

try:
    from . import solve
except ImportError:
    import solve


ROOT = Path(__file__).resolve().parents[2]
TOL = {
    "kinematic_m": 1e-7,
    "time_s": 1e-10,
    "independent_margin_m": 1e-8,
    "densified_duration_s": 1e-4,
    "root_margin_m": 1e-6,
    "excel_duration_s": 1e-9,
    "fresh_semantic": 1e-9,
}


class VerificationFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationFailure(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decision_from_result(payload: dict, source: str = "q3_e1e2") -> solve.kernel.Decision:
    record = payload["working_best"]["decision"]
    return solve.kernel.Decision(
        heading_rad=float(record["heading_rad"]),
        speed_mps=float(record["speed_mps"]),
        release_times_s=tuple(float(x) for x in record["release_times_s"]),
        fuse_delays_s=tuple(float(x) for x in record["fuse_delays_s"]),
        source=source,
        proposal_index=0,
    )


def unit_suite() -> dict:
    # Running this file directly puts ``src/q3`` rather than the repository
    # root on sys.path.  The production tests deliberately import
    # ``src.q3.solve`` to exercise the public package path, so make that path
    # explicit instead of relying on the caller's environment.
    root_text = str(ROOT)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromName("src.q3.tests.test_unified_solver")
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    require(result.wasSuccessful(), "Q3 unit suite failed: " + stream.getvalue()[-3000:])
    return {"status": "pass", "tests_run": result.testsRun, "failures": 0, "errors": 0}


def kinematic_reconstruction(decision: solve.kernel.Decision, stored: dict) -> dict:
    p = solve.kernel.base_parameters()
    direction = np.array([math.cos(decision.heading_rad), math.sin(decision.heading_rad), 0.0])
    tau = np.asarray(decision.release_times_s)
    delta = np.asarray(decision.fuse_delays_s)
    te = tau + delta
    release = p.uav_initial + decision.speed_mps * tau[:, None] * direction
    explosion = p.uav_initial + decision.speed_mps * te[:, None] * direction
    explosion[:, 2] = p.uav_initial[2] - 0.5 * p.gravity * delta**2
    release_residual = float(np.max(np.linalg.norm(release - np.asarray(stored["release_points_m"]), axis=1)))
    explosion_residual = float(np.max(np.linalg.norm(explosion - np.asarray(stored["explosion_points_m"]), axis=1)))
    time_residual = float(np.max(np.abs(te - np.asarray(stored["explosion_times_s"]))))
    gap = np.diff(tau)
    sink_residual = 0.0
    for index in range(3):
        centres = solve.kernel.cloud_center(decision, index, np.array([te[index], te[index] + 1.0]))
        sink_residual = max(sink_residual, abs(float(centres[0, 2] - centres[1, 2]) - 3.0))
    margins = solve.kernel.constraint_margins(decision)
    checked = [value for key, value in margins.items() if key != "heading_domain_rad"]
    checks = {
        "release_points": release_residual <= TOL["kinematic_m"],
        "explosion_points": explosion_residual <= TOL["kinematic_m"],
        "explosion_times": time_residual <= TOL["time_s"],
        "release_gap": bool(np.all(gap >= 1.0 - TOL["time_s"])),
        "sink_speed": sink_residual <= TOL["kinematic_m"],
        "hard_constraints": min(checked) >= -TOL["kinematic_m"],
    }
    require(all(checks.values()), f"kinematic E1 failure: {checks}")
    return {
        "status": "pass", "checks": checks, "release_point_max_residual_m": release_residual,
        "explosion_point_max_residual_m": explosion_residual, "explosion_time_max_residual_s": time_residual,
        "release_gaps_s": gap.tolist(), "sink_one_second_residual_m": sink_residual,
        "minimum_hard_constraint_margin": float(min(checked)),
    }


def independent_visible(mesh: solve.kernel.SurfaceMesh, missile: np.ndarray) -> np.ndarray:
    side = mesh.kinds == 0
    visible = np.zeros(len(mesh.points), dtype=bool)
    if np.any(side):
        points = mesh.points[side]
        normals = mesh.point_normals[side]
        visible[side] = (
            missile[:2] @ normals[:, :2].T
            - np.einsum("ij,ij->i", points[:, :2], normals[:, :2])
        ) >= -1e-12
    visible[~side] = missile[2] >= mesh.points[~side, 2] - 1e-12
    return visible


def independent_margin(decision: solve.kernel.Decision, time_s: float, mesh: solve.kernel.SurfaceMesh) -> float:
    p = solve.kernel.base_parameters()
    missile = solve.kernel.q1.missile_position(time_s, p)
    visible = independent_visible(mesh, missile)
    te = np.asarray(decision.release_times_s) + np.asarray(decision.fuse_delays_s)
    clouds = []
    direction = np.array([math.cos(decision.heading_rad), math.sin(decision.heading_rad), 0.0])
    for index in range(3):
        if te[index] - solve.kernel.TIME_TOL <= time_s <= min(te[index] + p.smoke_duration, solve.kernel.arrival_time()) + solve.kernel.TIME_TOL:
            explosion = p.uav_initial + decision.speed_mps * te[index] * direction
            explosion[2] = p.uav_initial[2] - 0.5 * p.gravity * decision.fuse_delays_s[index] ** 2
            cloud = explosion.copy()
            cloud[2] -= p.smoke_sink_speed * (time_s - te[index])
            clouds.append(cloud)
    if not clouds:
        return math.inf
    worst = -math.inf
    for point in mesh.points[visible]:
        vector = point - missile
        denominator = float(np.dot(vector, vector))
        best = math.inf
        for cloud in clouds:
            lam = float(np.clip(np.dot(cloud - missile, vector) / denominator, 0.0, 1.0))
            nearest = missile + lam * vector
            best = min(best, float(np.linalg.norm(cloud - nearest)) - p.smoke_radius)
        worst = max(worst, best)
    return float(worst)


def independent_oracle(decision: solve.kernel.Decision, payload: dict) -> dict:
    mesh = solve.kernel.surface_mesh(128, 9)
    entry, exit_time = payload["working_best"]["precise"]["intervals_s"][0]
    te = np.asarray(decision.release_times_s) + np.asarray(decision.fuse_delays_s)
    times = sorted(set([
        float(entry), float(entry + 0.15), float(te[1]), float(te[1] + 0.15),
        float(te[2]), float(te[2] + 0.15), float(exit_time - 0.15), float(exit_time),
    ]))
    records = []
    maximum = 0.0
    for time_s in times:
        production = float(solve.kernel.joint_margins(decision, np.array([time_s]), mesh)[0])
        independent = independent_margin(decision, time_s, mesh)
        difference = abs(production - independent)
        maximum = max(maximum, difference)
        records.append({"time_s": time_s, "production_margin_m": production,
                        "independent_margin_m": independent, "absolute_difference_m": difference})
    require(maximum <= TOL["independent_margin_m"], f"independent max-min margin mismatch {maximum}")
    return {"status": "pass", "mesh": {"n_theta": 128, "n_levels": 9},
            "maximum_absolute_difference_m": maximum, "records": records}


def numerical_checks(payload: dict) -> dict:
    diagnostics = payload["final_diagnostics"]
    dense_change = abs(float(diagnostics["densified_joint_change_s"]))
    roots = diagnostics["precise"]["joint"]["root_residuals"]
    root_residual = max(abs(float(item["margin_m"])) for item in roots)
    excel = payload["excel_roundtrip"]
    excel_difference = abs(float(excel["joint_duration_change_s"]))
    incumbent = payload["comparison_to_legacy"]
    checks = {
        "densified_surface_stability": dense_change <= TOL["densified_duration_s"],
        "time_root_residual": root_residual <= TOL["root_margin_m"],
        "excel_roundtrip": excel["status"] == "pass" and excel_difference <= TOL["excel_duration_s"],
        "incumbent_not_lost": bool(incumbent["incumbent_not_lost"]),
        "resource_monotonicity": bool(diagnostics["resource_monotonicity_pass"]),
    }
    require(all(checks.values()), f"E2 numerical checks failed: {checks}")
    return {"status": "pass", "checks": checks, "densified_joint_change_s": float(diagnostics["densified_joint_change_s"]),
            "maximum_root_residual_m": root_residual, "excel_joint_duration_change_s": excel_difference,
            "legacy_change_s": float(incumbent["change_s"])}


def semantic_signature(payload: dict) -> dict:
    best = payload["working_best"]
    return {
        "status": payload["status"], "spec_id": payload["spec_id"],
        "decision": {key: best["decision"][key] for key in ("heading_rad", "speed_mps", "release_times_s", "fuse_delays_s")},
        "precise_intervals": best["precise"]["intervals_s"],
        "precise_duration": best["precise"]["effective_duration_s"],
        "individual_durations": [x["effective_duration_s"] for x in payload["final_diagnostics"]["precise"]["individuals"]],
        "marginal_contributions": [x["marginal_contribution_s"] for x in payload["final_diagnostics"]["leave_one_out"]],
    }


def maximum_numeric_difference(left, right) -> float:
    differences = []
    def visit(a, b):
        if isinstance(a, dict):
            require(set(a) == set(b), "fresh reproduction keys changed")
            for key in a: visit(a[key], b[key])
        elif isinstance(a, list):
            require(len(a) == len(b), "fresh reproduction list length changed")
            for x, y in zip(a, b): visit(x, y)
        elif isinstance(a, (int, float)) and not isinstance(a, bool):
            differences.append(abs(float(a) - float(b)))
        else:
            require(a == b, "fresh reproduction category changed")
    visit(left, right)
    return max(differences, default=0.0)


def fresh_reproduction(payload: dict) -> dict:
    # Re-run the declared production entrypoint against its declared outputs.
    # The writer intentionally requires repository-relative paths; using the
    # production targets tests that interface and avoids weakening it merely
    # for the validator.  ``payload`` already holds the before-run semantics.
    command = [sys.executable, "-B", str(ROOT / "src/q3/solve.py"),
               "--output", "docs/q3_result.json",
               "--report", "docs/q3_implementation_report.md",
               "--excel", "output/q3/result1.xlsx"]
    process = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, timeout=300, check=False)
    require(process.returncode == 0, "fresh Q3 reproduction failed: " + process.stdout[-4000:])
    result_path = ROOT / "docs/q3_result.json"
    reproduced = json.loads(result_path.read_text(encoding="utf-8"))
    difference = maximum_numeric_difference(semantic_signature(payload), semantic_signature(reproduced))
    require(difference <= TOL["fresh_semantic"], f"fresh reproduction difference {difference}")
    return {"status": "pass", "maximum_semantic_difference": difference,
            "reproduced_result_sha256": sha256(result_path),
            "elapsed_marker_present": '"elapsed_seconds"' in process.stdout,
            "stage_markers": {name: f'"stage": "{name}"' in process.stdout for name in
                              ("initial_track_proxy", "original8d_pattern_refinement", "final_precise")}}


def report_text(result: dict) -> str:
    return f"""# Q3 E1/E2 实现与数值验证报告

- 总状态：`{result['status']}`。
- E1：`{result['E1']['status']}`；单元测试 `{result['E1']['unit_suite']['tests_run']}` 项全部通过，
  投放点最大重构残差 `{result['E1']['kinematics']['release_point_max_residual_m']:.3e} m`，
  起爆点最大重构残差 `{result['E1']['kinematics']['explosion_point_max_residual_m']:.3e} m`。
- E2：`{result['E2']['status']}`；独立逐点 `max_P min_k` 余量与生产向量化求值最大差
  `{result['E2']['independent_oracle']['maximum_absolute_difference_m']:.3e} m`；加密时长变化
  `{result['E2']['numerical']['densified_joint_change_s']:.3e} s`；Excel 回读时长差
  `{result['E2']['numerical']['excel_joint_duration_change_s']:.3e} s`。
- 从声明生产入口完整复跑的语义最大差为
  `{result['E2']['fresh_reproduction']['maximum_semantic_difference']:.3e}`。

这些检查支持当前实现与 `SPEC-Q3-WORKING-2.0` 同义，并支持 `6.926038728 s` 在当前离散、
求根和回读设置下数值稳定；它们不证明连续八维域全局最优，也不验证现实部署效果。
"""


def run(output: Path, report: Path) -> dict:
    started = time.perf_counter()
    payload = json.loads((ROOT / "docs/q3_result.json").read_text(encoding="utf-8"))
    require(payload["status"] == "working" and payload["spec_id"] == solve.SPEC_ID, "unexpected Q3 result identity")
    decision = decision_from_result(payload)
    solve.kernel.validate_decision(decision)
    identities = {path: sha256(ROOT / path) for path in (
        "data/A题.pdf", "data/附件/result1.xlsx", "planning/20_q3_unified_solver_spec.md",
        "planning/22_q3_verification_and_sensitivity_spec.md", "src/q3/solve.py",
        "src/q3/selection_pilot.py", "docs/q3_result.json", "output/q3/result1.xlsx")}
    require(identities["data/A题.pdf"] == solve.OFFICIAL_SHA256, "official identity mismatch")
    require(identities["data/附件/result1.xlsx"] == solve.TEMPLATE_SHA256, "template identity mismatch")
    unit = unit_suite()
    kinematics = kinematic_reconstruction(decision, payload["working_best"]["decision"])
    independent = independent_oracle(decision, payload)
    numerical = numerical_checks(payload)
    reproduction = fresh_reproduction(payload)
    # The reproduction intentionally refreshes the formal result/report/xlsx;
    # bind the emitted validation record to their post-run identities.
    identities = {path: sha256(ROOT / path) for path in identities}
    result = {
        "schema_version": "1.0", "result_id": "Q3-E1E2-SPEC-Q3-WORKING-2.0-20260828",
        "status": "pass", "spec_id": solve.SPEC_ID, "formal_result_id": payload["result_id"],
        "method_role": "auxiliary_validator", "identities": identities, "tolerances": TOL,
        "E1": {"status": "pass", "unit_suite": unit, "kinematics": kinematics},
        "E2": {"status": "pass", "independent_oracle": independent,
               "numerical": numerical, "fresh_reproduction": reproduction},
        "claim_boundary": ["supports implementation fidelity and numerical stability",
                           "does not prove continuous-domain global optimality",
                           "does not establish empirical or deployment validity"],
        "run_identity": {"executed_at": datetime.now(timezone.utc).isoformat(),
                         "python": sys.version.split()[0], "elapsed_seconds": time.perf_counter() - started},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(solve.ready(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report.write_text(report_text(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(output),
                      "report": str(report), "elapsed_seconds": result["run_identity"]["elapsed_seconds"]}, ensure_ascii=False))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.output, args.report)
    except (VerificationFailure, solve.Q3UnifiedError, solve.kernel.PilotError) as error:
        print(json.dumps({"status": "fail", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
