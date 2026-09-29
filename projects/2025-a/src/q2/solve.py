"""Run the frozen Q2 formal hierarchical solver and write inspectable outputs.

Inverse-service C3-I and C2 provide starts.  A multiscale local Powell/pattern
search proposes moves, while the strict screen evaluator owns acceptance and
the initial feasible incumbent can never be degraded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import minimize

import reselection_pilot as pilot


ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = Path("planning/14_q2_formal_solver_spec.md")
GEOMETRY_PATH = Path("planning/12_q2_c3_geometry_and_candidate_reselection.md")
RESELECTION_SPEC_PATH = Path("planning/13_q2_reselection_pilot_spec.md")
INPUT_PATH = Path("data/A题.pdf")

SPEC_SHA = "39b2b9f842d25e7111198a7c3dd5a277c2286ca0cabe15104ac95c56d91031df"
GEOMETRY_SHA = "210f5fc5ccb99dc8bba7877265f0da7762efca0614bc5ffe540d08bbdb397eaf"
RESELECTION_SPEC_SHA = "dfe33fbda5cbc4203730e2f6bc26aa972e42711fd571c42b2cf2904553f331c3"
INPUT_SHA = "a37f6aad30b16ea09da9cb320ce194b12d3a28874008cf9ff19549f6c6079447"

SEEDS = [250827, 250828, 250829]
SCREEN = {"scan_step_s": 0.02, "n_theta": 128, "n_levels": 17}
PRECISE = {"scan_step_s": 0.005, "n_theta": 512, "n_levels": 33}
POWELL = {"maxiter": 80, "maxfev": 240, "xtol": 1e-5, "ftol": 1e-7}
TRUST_RADII = (0.05, 0.02, 0.007)
PATTERN_SCREEN_PER_RADIUS = 3
C3_PER_SEED = 2
C2_QUOTAS = {"target": 2, "missile": 2, "guard": 4}
COUNTEREXAMPLE_TOL_S = 1e-4


class Q2FormalError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_identities() -> dict[str, str]:
    expected = {
        INPUT_PATH: INPUT_SHA,
        GEOMETRY_PATH: GEOMETRY_SHA,
        RESELECTION_SPEC_PATH: RESELECTION_SPEC_SHA,
        SPEC_PATH: SPEC_SHA,
    }
    observed = {path: sha256(ROOT / path) for path in expected}
    mismatches = {
        path.as_posix(): {"expected": expected[path], "observed": observed[path]}
        for path in expected
        if observed[path] != expected[path]
    }
    if mismatches:
        raise Q2FormalError("Q2_FORMAL_IDENTITY_MISMATCH", json.dumps(mismatches, ensure_ascii=False))
    return {path.as_posix(): value for path, value in observed.items()}


def arrival_time() -> float:
    return pilot.arrival(pilot.q1.default_parameters())


def decision_to_unit(x: pilot.Decision) -> np.ndarray:
    p = pilot.q1.default_parameters()
    delta_max = math.sqrt(2.0 * p.uav_initial[2] / p.gravity)
    te = float(x.release_time_s + x.fuse_delay_s)
    remaining = arrival_time() - x.fuse_delay_s
    zt = 0.0 if remaining <= 1e-14 else x.release_time_s / remaining
    return np.clip(np.array([
        (x.heading_rad % (2.0 * math.pi)) / (2.0 * math.pi),
        (x.speed_mps - 70.0) / 70.0,
        x.fuse_delay_s / delta_max,
        zt,
    ], dtype=float), 0.0, 1.0)


def unit_to_decision(z: np.ndarray, source: str) -> pilot.Decision:
    p = pilot.q1.default_parameters()
    values = np.clip(np.asarray(z, dtype=float), 0.0, 1.0)
    delta_max = math.sqrt(2.0 * p.uav_initial[2] / p.gravity)
    fuse = float(delta_max * values[2])
    if values[2] >= 1.0:
        # Keep the mathematically feasible ground boundary on the accepted
        # side of the downstream floating-point height check.
        fuse = math.nextafter(delta_max, 0.0)
    te = float(fuse + values[3] * (arrival_time() - fuse))
    return pilot.Decision(
        heading_rad=float((2.0 * math.pi * values[0]) % (2.0 * math.pi)),
        speed_mps=float(70.0 + 70.0 * values[1]),
        release_time_s=float(te - fuse),
        fuse_delay_s=fuse,
        source_domain=source,
    )


def safe_proxy(x: pilot.Decision) -> float:
    value = float(pilot.proxy_score(x))
    if not math.isfinite(value):
        raise Q2FormalError("Q2_FORMAL_EVALUATOR_FAILURE", "non-finite proxy")
    return value


def continuous(x: pilot.Decision, settings: dict) -> dict:
    try:
        result = pilot.evaluate(x, settings)
    except Exception as error:
        raise Q2FormalError("Q2_FORMAL_EVALUATOR_FAILURE", str(error)) from error
    if not math.isfinite(float(result["effective_duration_s"])):
        raise Q2FormalError("Q2_FORMAL_EVALUATOR_FAILURE", "non-finite duration")
    return result


def score_bank(candidates: list[pilot.Candidate], method: str, seed: int) -> list[dict]:
    records: list[dict] = []
    for index, candidate in enumerate(candidates):
        records.append({
            "method": method,
            "seed": seed,
            "proposal_index": index,
            "candidate": candidate,
            "proxy_score_s": safe_proxy(candidate.decision),
        })
    return records


def select_starts() -> tuple[list[dict], dict]:
    starts: list[dict] = []
    c2_pool: list[dict] = []
    generation = {"C3-I": {}, "C2": {}}
    for seed in SEEDS:
        print(json.dumps({"stage": "seed_generation", "method": "C3-I", "seed": seed, "status": "started"}), flush=True)
        c3, c3_stats = pilot.generate_c3(seed)
        if len(c3) < pilot.N_PROXY:
            raise Q2FormalError("Q2_FORMAL_SEED_UNDERPOWERED", f"C3-I seed {seed}: {len(c3)}")
        c3_scored = score_bank(c3, "C3-I", seed)
        selected = sorted(c3_scored, key=lambda item: (-item["proxy_score_s"], item["proposal_index"]))[:C3_PER_SEED]
        for rank, item in enumerate(selected, 1):
            starts.append({**item, "start_id": f"C3I-{seed}-{rank}", "source_family": "C3-I", "source_domain": "centerline"})
        generation["C3-I"][str(seed)] = c3_stats
        print(json.dumps({"stage": "seed_generation", "method": "C3-I", "seed": seed, "status": "completed", "selected": len(selected)}), flush=True)

        print(json.dumps({"stage": "seed_generation", "method": "C2", "seed": seed, "status": "started"}), flush=True)
        c2, c2_stats = pilot.generate_c2(seed)
        if len(c2) < pilot.N_PROXY:
            raise Q2FormalError("Q2_FORMAL_SEED_UNDERPOWERED", f"C2 seed {seed}: {len(c2)}")
        c2_pool.extend(score_bank(c2, "C2", seed))
        generation["C2"][str(seed)] = c2_stats
        print(json.dumps({"stage": "seed_generation", "method": "C2", "seed": seed, "status": "completed"}), flush=True)

    for domain, quota in C2_QUOTAS.items():
        domain_pool = [item for item in c2_pool if item["candidate"].generation["domain"] == domain]
        selected = sorted(domain_pool, key=lambda item: (-item["proxy_score_s"], item["seed"], item["proposal_index"]))[:quota]
        if len(selected) < quota:
            raise Q2FormalError("Q2_FORMAL_SEED_UNDERPOWERED", f"C2 {domain}: {len(selected)} < {quota}")
        for rank, item in enumerate(selected, 1):
            starts.append({**item, "start_id": f"C2-{domain}-{rank}", "source_family": "C2", "source_domain": domain})

    witness = pilot.witness_oracle()
    witness_candidate = pilot.inverse_c3(5.0, 1.0, 0.06, "C3I_witness")
    starts.append({
        "method": "C3-I", "seed": "fixed_witness", "proposal_index": -1,
        "candidate": witness_candidate, "proxy_score_s": safe_proxy(witness_candidate.decision),
        "start_id": "C3I-WITNESS", "source_family": "C3-I", "source_domain": "witness",
    })
    expected_count = len(SEEDS) * C3_PER_SEED + sum(C2_QUOTAS.values()) + 1
    if len(starts) != expected_count:
        raise Q2FormalError("Q2_FORMAL_SEED_UNDERPOWERED", f"start count {len(starts)} != {expected_count}")
    return starts, {"generation": generation, "witness": witness, "start_count": len(starts)}


def refine_one(start: dict, ordinal: int, total: int) -> dict:
    initial = start["candidate"].decision
    initial_z = decision_to_unit(initial)
    calls = 0
    proxy_cache: dict[tuple[float, ...], tuple[pilot.Decision, float]] = {}

    def evaluate_proxy(z: np.ndarray) -> tuple[pilot.Decision, float]:
        nonlocal calls
        clipped = np.clip(np.asarray(z, dtype=float), 0.0, 1.0)
        key = tuple(np.round(clipped, 13))
        if key not in proxy_cache:
            calls += 1
            decision = unit_to_decision(clipped, f"TRUST4D_from_{start['start_id']}")
            proxy_cache[key] = (decision, safe_proxy(decision))
        return proxy_cache[key]

    def objective(z: np.ndarray) -> float:
        return -evaluate_proxy(z)[1]

    print(json.dumps({"stage": "full4d_refinement", "start_id": start["start_id"], "completed": ordinal - 1, "total": total, "status": "started"}), flush=True)
    initial_screen = continuous(initial, SCREEN)
    current_z = initial_z.copy()
    chosen = initial
    chosen_proxy = float(start["proxy_score_s"])
    chosen_screen = initial_screen
    stages = []
    reported_evaluations = 0
    optimizer_iterations = 0
    local_successes = 0
    strict_calls = 0

    def strict_key(screen: dict, proxy: float) -> tuple[float, float]:
        return float(screen["effective_duration_s"]), float(proxy)

    for radius in TRUST_RADII:
        lower = np.maximum(0.0, current_z - radius)
        upper = np.minimum(1.0, current_z + radius)
        optimization = minimize(
            objective,
            current_z,
            method="Powell",
            bounds=list(zip(lower, upper)),
            options=dict(POWELL),
        )
        reported_evaluations += int(getattr(optimization, "nfev", 0))
        optimizer_iterations += int(getattr(optimization, "nit", 0))
        local_successes += int(bool(optimization.success))
        proposals = [np.clip(np.asarray(optimization.x, dtype=float), lower, upper)]
        for coordinate in range(4):
            for sign in (-1.0, 1.0):
                probe = current_z.copy()
                probe[coordinate] = np.clip(
                    probe[coordinate] + sign * radius,
                    lower[coordinate], upper[coordinate],
                )
                proposals.append(probe)
        unique = {tuple(np.round(item, 13)): item for item in proposals}
        ranked = sorted(
            unique.values(), key=lambda z: -evaluate_proxy(z)[1]
        )[:PATTERN_SCREEN_PER_RADIUS]
        stage_best = None
        for proposal in ranked:
            decision, proxy = evaluate_proxy(proposal)
            screen = continuous(decision, SCREEN)
            strict_calls += 1
            candidate = (strict_key(screen, proxy), proposal, decision, proxy, screen)
            if stage_best is None or candidate[0] > stage_best[0]:
                stage_best = candidate
        assert stage_best is not None
        accepted = stage_best[0] > strict_key(chosen_screen, chosen_proxy)
        if accepted:
            _, current_z, chosen, chosen_proxy, chosen_screen = stage_best
        stages.append({
            "radius": radius,
            "powell_success": bool(optimization.success),
            "powell_status": int(optimization.status),
            "powell_message": str(optimization.message),
            "powell_iterations": int(getattr(optimization, "nit", -1)),
            "powell_function_evaluations": int(getattr(optimization, "nfev", -1)),
            "strict_proposals_evaluated": len(ranked),
            "accepted": accepted,
            "incumbent_screen_duration_s": float(chosen_screen["effective_duration_s"]),
        })
    refined = chosen
    refined_proxy = chosen_proxy
    refined_screen = chosen_screen
    choose_refined = pilot.decision_record(chosen) != pilot.decision_record(initial)
    record = {
        "start_id": start["start_id"],
        "source_family": start["source_family"],
        "source_domain": start["source_domain"],
        "seed": start["seed"],
        "proposal_index": start["proposal_index"],
        "initial": {
            "unit_coordinates": pilot.ready(initial_z),
            "decision": pilot.decision_record(initial),
            "proxy_score_s": float(start["proxy_score_s"]),
            "screen": initial_screen,
        },
        "refined": {
            "unit_coordinates": pilot.ready(current_z),
            "decision": pilot.decision_record(refined),
            "proxy_score_s": refined_proxy,
            "screen": refined_screen,
        },
        "chosen": {
            "origin": "trust_region_refined" if choose_refined else "initial_incumbent_retained",
            "decision": pilot.decision_record(chosen),
            "proxy_score_s": chosen_proxy,
            "screen": chosen_screen,
        },
        "screen_gain_s": float(chosen_screen["effective_duration_s"] - initial_screen["effective_duration_s"]),
        "optimizer": {
            "method": "incumbent_preserving_multiscale_local_powell_pattern",
            "success": True,
            "status": 0,
            "message": "incumbent retained at every trust radius",
            "iterations": optimizer_iterations,
            "reported_function_evaluations": reported_evaluations,
            "observed_function_evaluations": calls,
            "strict_screen_evaluations": strict_calls,
            "powell_success_count": local_successes,
            "settings": {"powell": dict(POWELL), "trust_radii": list(TRUST_RADII), "pattern_screen_per_radius": PATTERN_SCREEN_PER_RADIUS},
            "stages": stages,
        },
        "_chosen_decision": chosen,
    }
    print(json.dumps({
        "stage": "full4d_refinement", "start_id": start["start_id"], "completed": ordinal,
        "total": total, "status": "completed", "initial_s": initial_screen["effective_duration_s"],
        "chosen_s": chosen_screen["effective_duration_s"], "gain_s": record["screen_gain_s"],
    }), flush=True)
    return record


def wrapped_angle_difference(a: float, b: float) -> float:
    return abs((a - b + math.pi) % (2.0 * math.pi) - math.pi)


def physical_domain(heading: float) -> str:
    p = pilot.q1.default_parameters()
    target = p.target_base_center[:2] - p.uav_initial[:2]
    missile = p.missile_initial[:2] - p.uav_initial[:2]
    a_target = math.atan2(float(target[1]), float(target[0])) % (2.0 * math.pi)
    a_missile = math.atan2(float(missile[1]), float(missile[0])) % (2.0 * math.pi)
    in_target = wrapped_angle_difference(heading, a_target) <= pilot.HALF_WIDTH
    in_missile = wrapped_angle_difference(heading, a_missile) <= pilot.HALF_WIDTH
    if in_target and in_missile:
        return "target_and_missile"
    if in_target:
        return "target"
    if in_missile:
        return "missile"
    return "outside_both"


def validate_solution(decision: pilot.Decision, result: dict) -> None:
    margins = pilot.constraint_margins(decision)
    if min(margins.values()) < -1e-7:
        raise Q2FormalError("Q2_FORMAL_OUTPUT_INVALID", f"negative constraint margin: {margins}")
    duration = float(result["effective_duration_s"])
    intervals = result["intervals_s"]
    if not math.isfinite(duration) or duration < 0.0:
        raise Q2FormalError("Q2_FORMAL_OUTPUT_INVALID", "invalid duration")
    if any(float(a) > float(b) or (index and float(a) < float(intervals[index - 1][1]) - 1e-9)
           for index, (a, b) in enumerate(intervals)):
        raise Q2FormalError("Q2_FORMAL_OUTPUT_INVALID", "interval order invalid")
    reconstructed = sum(float(b) - float(a) for a, b in intervals)
    if abs(reconstructed - duration) > 1e-6:
        raise Q2FormalError("Q2_FORMAL_OUTPUT_INVALID", "duration/interval mismatch")


def build_report(result: dict, output_path: Path, output_sha: str) -> str:
    best = result["formal_best"]
    guard = result["guard_diagnostic"]
    c3_gains = result["c3i_to_full4d_gains_s"]
    distribution = result["multistart_summary"]
    pruning = best["precise"]["geometry_pruning"]
    return f"""# Q2 正式求解实现与 S4→S5 技术核销

> 内部技术证据；实现绑定 `SPEC-Q2-3.1-FORMAL-SOLVER`，不使用外部数值结果。

## 实现主链

正式实现为“C3-I 解析可行播种 + C2 物理分域及全域守卫 → 原变量四维 incumbent-preserving 多尺度局部 Powell/模式精修 → 任意控制轨迹完整圆柱表面连续筛选与精算”。C3-I 只提供高命中初值，不替代完整四维模型。

代理、筛选和精算在进入完整圆柱求值前，先用有限视线段坐标盒的严格必要条件截短时间域。正式最佳候选的有效窗由 `{pruning['active_window_s']}` s 缩到 `{pruning['possible_window_s']}` s，裁去 `{100.0 * pruning['pruned_fraction']:.3f}%`；窗口不是新可行约束，失败时回退原 20 s 有效窗。

## 运行与覆盖

- 固定种子：`{result['run_identity']['seeds']}`；执行类型：`{result['run_identity']['execution_kind']}`。
- 多启动：`{distribution['count']}` 个；筛选正值：`{distribution['positive_count']}` 个。
- 筛选时长范围：`[{distribution['minimum_s']:.9f}, {distribution['maximum_s']:.9f}] s`；中位数：`{distribution['median_s']:.9f} s`。
- C3-I 到完整四维精修增益：最小 `{min(c3_gains):.9f} s`，中位 `{float(np.median(c3_gains)):.9f} s`，最大 `{max(c3_gains):.9f} s`。
- C2 全域守卫在两个物理航向带外的最佳筛选值：`{guard['best_outside_guard_screen_s']:.9f} s`；分域外反例：`{guard['outside_domain_counterexample']}`。

## 正式最佳候选

- 航向：`{best['decision']['heading_rad']:.12f} rad`；速度：`{best['decision']['speed_mps']:.12f} m/s`。
- 投放时刻：`{best['decision']['release_time_s']:.12f} s`；引信延迟：`{best['decision']['fuse_delay_s']:.12f} s`。
- 投放点：`{best['decision']['release_point_m']} m`。
- 起爆点：`{best['decision']['explosion_point_m']} m`。
- 完整遮蔽区间：`{best['precise']['intervals_s']} s`。
- 精算总时长：`{best['precise']['effective_duration_s']:.12f} s`。
- 全部硬约束余量：`{best['decision']['constraint_margins']}`。

## 可检查身份与结论边界

- 机器结果：`{output_path.as_posix()}`；SHA-256：`{output_sha}`。
- 正式合同 SHA-256：`{result['identities']['formal_spec_sha256']}`；求解代码 SHA-256：`{result['run_identity']['solver_sha256']}`。
- 当前结果只支持实现引用和 Q2 `S4→S5`。角度、时间、预算加严以及独立数值复核属于后续 E1/E2；本阶段不宣称严格全局最优或完成 S6。
"""


def run(output_path: Path, report_path: Path) -> dict:
    identities = verify_identities()
    started = time.perf_counter()
    print(json.dumps({"stage": "identity", "status": "passed"}), flush=True)
    starts, seed_diagnostics = select_starts()
    records = [refine_one(start, index, len(starts)) for index, start in enumerate(starts, 1)]
    if all(float(record["chosen"]["screen"]["effective_duration_s"]) <= 1e-9 for record in records):
        raise Q2FormalError("Q2_FORMAL_ALL_ZERO", "all multistarts returned zero")

    ranked = sorted(
        enumerate(records),
        key=lambda pair: (
            -float(pair[1]["chosen"]["screen"]["effective_duration_s"]),
            -float(pair[1]["chosen"]["proxy_score_s"]),
            pair[0],
        ),
    )[:3]
    precise_records = []
    for rank, (index, record) in enumerate(ranked, 1):
        print(json.dumps({"stage": "precise_rescore", "rank": rank, "start_id": record["start_id"], "status": "started"}), flush=True)
        decision = record["_chosen_decision"]
        precise = continuous(decision, PRECISE)
        validate_solution(decision, precise)
        precise_records.append({
            "rank": rank,
            "multistart_index": index,
            "start_id": record["start_id"],
            "source_family": record["source_family"],
            "source_domain": record["source_domain"],
            "decision": pilot.decision_record(decision),
            "screen_duration_s": record["chosen"]["screen"]["effective_duration_s"],
            "precise": precise,
        })
        print(json.dumps({"stage": "precise_rescore", "rank": rank, "start_id": record["start_id"], "status": "completed", "duration_s": precise["effective_duration_s"]}), flush=True)
    formal_best = max(precise_records, key=lambda item: (item["precise"]["effective_duration_s"], -item["rank"]))

    best_c3_screen = max(
        float(record["chosen"]["screen"]["effective_duration_s"])
        for record in records if record["source_family"] == "C3-I"
    )
    guard_details = []
    for record in records:
        if record["source_domain"] != "guard":
            continue
        heading = float(record["chosen"]["decision"]["heading_rad"])
        domain = physical_domain(heading)
        guard_details.append({
            "start_id": record["start_id"],
            "final_domain": domain,
            "screen_duration_s": float(record["chosen"]["screen"]["effective_duration_s"]),
            "decision": record["chosen"]["decision"],
        })
    outside = [item for item in guard_details if item["final_domain"] == "outside_both"]
    best_outside = max((item["screen_duration_s"] for item in outside), default=0.0)
    guard_diagnostic = {
        "definition_tolerance_s": COUNTEREXAMPLE_TOL_S,
        "best_c3i_screen_s": best_c3_screen,
        "best_outside_guard_screen_s": best_outside,
        "outside_domain_counterexample": bool(best_outside > best_c3_screen + COUNTEREXAMPLE_TOL_S),
        "guard_records": guard_details,
        "interpretation": "No counterexample means not found under this fixed budget, not a proof of exhaustive coverage.",
    }

    durations = np.array([float(record["chosen"]["screen"]["effective_duration_s"]) for record in records])
    c3_gains = [float(record["screen_gain_s"]) for record in records if record["source_family"] == "C3-I"]
    public_records = []
    for record in records:
        public_records.append({key: value for key, value in record.items() if not key.startswith("_")})

    result = {
        "schema_version": "1.0",
        "result_id": "Q2-SPEC-Q2-3.1-FORMAL-SOLVER",
        "question_id": "Q2",
        "status": "ok",
        "purpose": "formal_q2_s5_implementation_output",
        "units": {
            "heading_rad": "rad", "speed_mps": "m/s", "time": "s", "position": "m",
            "duration": "s", "constraint_margins": "field-specific SI units",
        },
        "identities": {
            "official_input_sha256": identities[INPUT_PATH.as_posix()],
            "geometry_sha256": identities[GEOMETRY_PATH.as_posix()],
            "reselection_spec_sha256": identities[RESELECTION_SPEC_PATH.as_posix()],
            "formal_spec_sha256": identities[SPEC_PATH.as_posix()],
        },
        "solver_contract": {
            "seeds": SEEDS,
            "c3_candidates_per_seed": pilot.N_PROXY,
            "c3_selected_per_seed": C3_PER_SEED,
            "c2_candidates_per_seed": pilot.N_PROXY,
            "c2_selected_quotas": C2_QUOTAS,
            "strict_witness_count": 1,
            "multistart_count": len(records),
            "proxy": pilot.PROXY,
            "screen": SCREEN,
            "precise": PRECISE,
            "geometry_pruning": {
                "enabled": True,
                "role": "safe_necessary_precheck_only",
                "length_expansion_m": pilot.q1.GEOMETRY_LENGTH_TOL_M,
                "time_expansion_s": pilot.q1.GEOMETRY_TIME_TOL_S,
                "fallback": "full_active_window_on_precheck_failure",
            },
            "full4d_optimizer": {
                "method": "incumbent_preserving_multiscale_local_powell_pattern",
                "trust_radii": list(TRUST_RADII),
                "pattern_screen_per_radius": PATTERN_SCREEN_PER_RADIUS,
                "local_powell": dict(POWELL),
            },
        },
        "seed_diagnostics": seed_diagnostics,
        "multistart_records": public_records,
        "multistart_summary": {
            "count": int(durations.size),
            "positive_count": int(np.sum(durations > 1e-9)),
            "durations_s": pilot.ready(durations),
            "minimum_s": float(np.min(durations)),
            "median_s": float(np.median(durations)),
            "maximum_s": float(np.max(durations)),
            "standard_deviation_s": float(np.std(durations)),
        },
        "c3i_to_full4d_gains_s": c3_gains,
        "guard_diagnostic": guard_diagnostic,
        "precise_finalists": precise_records,
        "formal_best": formal_best,
        "limitations": [
            "The fixed-budget multistart result is a reproducible feasible near-optimum, not a strict global optimum proof.",
            "C3-I is used only for seeding; full four-dimensional refinement and C2 guards retain coverage.",
            "E1/E2 implementation and numerical convergence gates remain for S5 to S6.",
            "External numerical results were not loaded, ranked, or used as thresholds.",
        ],
        "run_identity": {
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "execution_kind": "declared_stochastic_repeated_fixed_seeds",
            "seeds": SEEDS,
            "repetition_policy": "one formal run containing three fixed seed strata and one deterministic witness",
            "variability_policy": "retain all multistart outcomes; do not hide zero or failed starts",
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "solver_sha256": sha256(ROOT / "src/q2/solve.py"),
            "reselection_code_sha256": sha256(ROOT / "src/q2/reselection_pilot.py"),
            "q1_model_sha256": sha256(ROOT / "src/q1/model.py"),
            "elapsed_seconds": time.perf_counter() - started,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(pilot.ready(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output_sha = sha256(output_path)
    report_path.write_text(build_report(result, output_path, output_sha), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(ROOT / args.output, ROOT / args.report)
    except (Q2FormalError, pilot.PilotError) as error:
        code = getattr(error, "code", "Q2_FORMAL_EVALUATOR_FAILURE")
        print(json.dumps({"status": "fail", "failure_code": code, "message": str(error)}, ensure_ascii=False), flush=True)
        return 2
    print(json.dumps({
        "status": result["status"],
        "effective_duration_s": result["formal_best"]["precise"]["effective_duration_s"],
        "start_id": result["formal_best"]["start_id"],
        "output": args.output.as_posix(),
        "report": args.report.as_posix(),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
