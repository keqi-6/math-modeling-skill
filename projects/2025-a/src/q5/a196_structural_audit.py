"""Structural reproduction audit of the A196 Q5 appendix.

This is an isolated working pilot.  It reproduces the executable structure
visible in the appendix, then evaluates the resulting 15-cloud decision with
the project's strict simultaneous three-missile quantifier.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.q3 import selection_pilot as q3  # noqa: E402
from src.q5 import full_condition_search as full  # noqa: E402
from src.q5 import solve as q5  # noqa: E402

SPEC_ID = "Q5-A196-STRUCTURAL-AUDIT-1.0"
SPEC_PATH = ROOT / "planning/47_q5_a196_structural_audit_spec.md"
INCUMBENT_PATH = ROOT / "docs/q5_full_condition_search.json"
OFFICIAL_PATH = ROOT / "data/A题.pdf"
RNG_SEED = 20260829
A196_REPORTED_S = 21.0770
A196_IMAGE_PDF_SHA256 = "e072d5a2500eee46a5fc48f29f74f4939d3e8805db99300d6609d7a57f368d6c"
STRUCTURAL_STEP_S = .25
STRUCTURAL_THETA = 16
STRUCTURAL_LEVELS = 3
STRUCTURAL_POPULATION = 14
FULL_POPULATION = 28
FULL_PROXY_STEP_S = .5
SEARCH_RESERVE_S = 8.
SOURCE_AUDIT = {
    "official_display_url": "https://dxs.moe.gov.cn/zx/a/hd_sxjm_sxjmlw_2025qgdxssxjmjslwzs/2022729.shtml",
    "ocr_url": "https://raw.githubusercontent.com/yushugulao/CUMCM-Archive/refs/heads/main/research_index/pdf_text/2025/A/%E4%BC%98%E7%A7%80%E8%AE%BA%E6%96%87/A196--89f5a9e676.md",
    "appendix_pages": [89, 90, 91, 92],
    "result_screenshot_page": 34,
    "result_table_exactly_recoverable": False,
    "reason_exact_table_unavailable": "official display contains only a low-resolution screenshot; result3.xlsx is listed but not publicly downloadable",
    "executable_structure": {
        "missile_choice": "one nearest missile per UAV",
        "release_pattern_s": [0., 1., 2.],
        "shared_fuse_within_uav": True,
        "per_uav_metric": "get_last_time(bomb1)+get_last_time(bomb2)+get_last_time(bomb3)",
        "overall_metric": "sum of five per-UAV metrics",
        "within_missile_interval_union_in_main_q5": False,
        "three_missile_interval_intersection_in_main_q5": False,
        "IntervalInter_called_by_main_q5": False,
        "fy5_appendix_coordinate_m": [13000., 2000., 1300.],
        "fy5_official_coordinate_m": [13000., -2000., 1300.],
    },
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def ready(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {key: ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [ready(item) for item in value]
    return value


def write_checkpoint(path: Path, stage: str, content: dict) -> None:
    """Persist useful partial results so a late reporting error cannot erase a run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0-checkpoint", "spec_id": SPEC_ID,
        "status": "running_checkpoint", "stage": stage,
        "updated_at": datetime.now(timezone.utc).isoformat(), **content,
    }
    path.write_text(json.dumps(ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def nearest_missile_assignment(origins: np.ndarray | None = None) -> tuple[int, ...]:
    """Reproduce the appendix horizontal nearest-at-equal-altitude rule."""
    origins = q5.ORIGINS if origins is None else np.asarray(origins, float)
    assignments = []
    velocities = -q5.geometry.MISSILES / np.linalg.norm(q5.geometry.MISSILES, axis=1)[:, None] * q5.p().missile_speed
    for origin in origins:
        distances = []
        for missile, velocity in zip(q5.geometry.MISSILES, velocities):
            t = (origin[2] - missile[2]) / velocity[2]
            point = missile + velocity * t
            distances.append(float(np.linalg.norm(point[:2] - origin[:2])))
        assignments.append(int(np.argmin(distances)))
    return tuple(assignments)


def paper_intercept_seed(platform_index: int, missile_index: int, step_s: float = .005) -> dict:
    """Translate the appendix get_vt1t1 construction using atan2 and official data."""
    origin = q5.ORIGINS[platform_index]
    missile0 = q5.geometry.MISSILES[missile_index]
    missile_velocity = -missile0 / np.linalg.norm(missile0) * q5.p().missile_speed
    for t in np.arange(step_s, q5.arrival(missile_index), step_s):
        point = missile0 + missile_velocity * t
        horizontal = point[:2] - origin[:2]
        speed = float(np.linalg.norm(horizontal) / t)
        if not 70. <= speed <= 140. or point[2] > origin[2]:
            continue
        s_square = float((origin[2] - point[2]) / (.5 * q5.p().gravity * t * t))
        if not 0. <= s_square < 1.:
            continue
        s = math.sqrt(s_square)
        release = (1. - s) * t
        fuse = s * t
        if release + 2. + fuse <= q5.arrival(missile_index) + 1e-9:
            return {
                "heading_rad": float(math.atan2(horizontal[1], horizontal[0]) % (2 * math.pi)),
                "speed_mps": speed,
                "base_release_s": float(release),
                "shared_fuse_s": float(fuse),
                "intercept_time_s": float(t),
            }
    # This branch is not expected for the official data, but keeps the pilot total.
    horizontal = -origin[:2]
    return {
        "heading_rad": float(math.atan2(horizontal[1], horizontal[0]) % (2 * math.pi)),
        "speed_mps": 105., "base_release_s": 0., "shared_fuse_s": 0.,
        "intercept_time_s": 0.,
    }


def decode_structural(vector: np.ndarray, platform_index: int, missile_index: int) -> tuple[float, float, float, float]:
    values = np.clip(np.asarray(vector, float), 0., 1.)
    if values.shape != (4,):
        raise ValueError(values.shape)
    heading = float((values[0] * 2 * math.pi) % (2 * math.pi))
    speed = float(70. + 70. * values[1])
    base_limit = max(0., q5.arrival(missile_index) - 2.)
    release = float(values[2] * base_limit)
    fuse_limit = min(
        math.sqrt(2. * q5.ORIGINS[platform_index, 2] / q5.p().gravity),
        max(0., q5.arrival(missile_index) - release - 2.),
    )
    fuse = float(values[3] * fuse_limit)
    return heading, speed, release, fuse


def encode_structural(seed: dict, platform_index: int, missile_index: int) -> np.ndarray:
    base_limit = max(0., q5.arrival(missile_index) - 2.)
    release = float(np.clip(seed["base_release_s"], 0., base_limit))
    fuse_limit = min(
        math.sqrt(2. * q5.ORIGINS[platform_index, 2] / q5.p().gravity),
        max(0., q5.arrival(missile_index) - release - 2.),
    )
    return np.array([
        (seed["heading_rad"] % (2 * math.pi)) / (2 * math.pi),
        (seed["speed_mps"] - 70.) / 70.,
        release / base_limit if base_limit else 0.,
        seed["shared_fuse_s"] / fuse_limit if fuse_limit else 0.,
    ], float).clip(0., 1.)


def platform_decision(vector: np.ndarray, platform_index: int, missile_index: int, separate: int | None = None) -> q5.Decision:
    heading, speed, release, fuse = decode_structural(vector, platform_index, missile_index)
    headings = [0.] * 5
    speeds = [70.] * 5
    headings[platform_index] = heading
    speeds[platform_index] = speed
    ordinals = range(3) if separate is None else [separate]
    bombs = tuple(q5.Bomb(platform_index, missile_index, release + ordinal, fuse) for ordinal in ordinals)
    decision = q5.Decision(tuple(headings), tuple(speeds), bombs, "a196_structural_platform")
    q5.validate(decision)
    return decision


def sampled_duration(times: np.ndarray, flags: np.ndarray) -> float:
    """Total duration of connected sampled runs, measured between end nodes."""
    total = 0.
    first = None
    for index, flag in enumerate(np.asarray(flags, bool)):
        if flag and first is None:
            first = index
        if first is not None and (not flag or index == len(flags) - 1):
            last = index if flag and index == len(flags) - 1 else index - 1
            total += float(times[last] - times[first])
            first = None
    return total


def independent_score(vector: np.ndarray, platform_index: int, missile_index: int,
                      times: np.ndarray, mesh) -> tuple[tuple, dict]:
    thresholds = (0., 5., 10., 20., 40., 80.)
    margins = []
    for ordinal in range(3):
        decision = platform_decision(vector, platform_index, missile_index, ordinal)
        margins.append(q5.strict_margins(decision, missile_index, times, mesh, assume_valid=True))
    rows = np.vstack(margins)
    duration_sums = [sum(sampled_duration(times, row <= threshold) for row in rows)
                     for threshold in thresholds]
    finite = rows[np.isfinite(rows)]
    tail = -float(np.mean(np.sort(finite)[:min(12, len(finite))])) if len(finite) else -math.inf
    return tuple([*duration_sums, tail]), {
        "independent_single_cloud_duration_sum_s": float(duration_sums[0]),
        "per_bomb_duration_s": [sampled_duration(times, row <= 0.) for row in rows],
        "threshold_duration_sums": [
            {"threshold_m": threshold, "duration_sum_s": duration}
            for threshold, duration in zip(thresholds, duration_sums)
        ],
        "minimum_margin_m": float(np.min(finite)) if len(finite) else math.inf,
    }


def optimise_platform(platform_index: int, missile_index: int, deadline: float,
                      rng: np.random.Generator, mesh) -> dict:
    seed = paper_intercept_seed(platform_index, missile_index)
    seed_vector = encode_structural(seed, platform_index, missile_index)
    population = [seed_vector]
    while len(population) < STRUCTURAL_POPULATION // 2:
        population.append(np.clip(seed_vector + rng.normal(0., [.03, .08, .08, .08]), 0., 1.))
    while len(population) < STRUCTURAL_POPULATION:
        population.append(rng.random(4))
    population = np.asarray(population)
    times = np.arange(0., q5.arrival(missile_index) + STRUCTURAL_STEP_S * .25, STRUCTURAL_STEP_S)
    scores, metrics = [], []
    evaluations = 0
    for vector in population:
        score, metric = independent_score(vector, platform_index, missile_index, times, mesh)
        scores.append(score)
        metrics.append(metric)
        evaluations += 1
    generations = 0
    while time.perf_counter() < deadline:
        for index in range(len(population)):
            if time.perf_counter() >= deadline:
                break
            pool = [value for value in range(len(population)) if value != index]
            a, b, c = rng.choice(pool, 3, replace=False)
            mutant = np.clip(population[a] + .72 * (population[b] - population[c]), 0., 1.)
            crossover = rng.random(4) < .78
            crossover[int(rng.integers(4))] = True
            trial = np.where(crossover, mutant, population[index])
            score, metric = independent_score(trial, platform_index, missile_index, times, mesh)
            evaluations += 1
            if score > scores[index]:
                population[index], scores[index], metrics[index] = trial, score, metric
        generations += 1
    best = max(range(len(population)), key=lambda index: scores[index])
    heading, speed, release, fuse = decode_structural(population[best], platform_index, missile_index)
    return {
        "platform_index": platform_index, "platform": q5.NAMES[platform_index],
        "assigned_missile_index": missile_index, "assigned_missile": q5.MISSILE_NAMES[missile_index],
        "paper_intercept_seed": seed,
        "heading_rad": heading, "heading_deg": math.degrees(heading) % 360., "speed_mps": speed,
        "base_release_s": release, "release_times_s": [release + value for value in range(3)],
        "shared_fuse_s": fuse, "proxy_metric": metrics[best],
        "score": list(map(float, scores[best])), "evaluation_count": evaluations,
        "generation_count": generations,
    }


def combine_platforms(rows: list[dict], source: str) -> q5.Decision:
    headings = [0.] * 5
    speeds = [70.] * 5
    bombs = []
    for row in rows:
        i = int(row["platform_index"])
        j = int(row["assigned_missile_index"])
        headings[i] = float(row["heading_rad"])
        speeds[i] = float(row["speed_mps"])
        for release in row["release_times_s"]:
            bombs.append(q5.Bomb(i, j, float(release), float(row["shared_fuse_s"])))
    decision = q5.Decision(tuple(headings), tuple(speeds),
                           tuple(sorted(bombs, key=lambda bomb: (bomb.platform, bomb.release_s))), source)
    q5.validate(decision)
    return decision


def load_incumbent() -> tuple[q5.Decision, dict]:
    payload = json.loads(INCUMBENT_PATH.read_text(encoding="utf-8"))
    decision = full.decision_from_record(payload["best_decision"], "pre_a196_strict_incumbent")
    return decision, payload["screen_verification"]["candidate"]


def hybrid(a: np.ndarray, b: np.ndarray, platforms_from_b: tuple[int, ...]) -> np.ndarray:
    row = np.array(a, copy=True)
    for platform_index in platforms_from_b:
        left = 8 * platform_index
        row[left:left + 8] = b[left:left + 8]
    return row


def refine_full_condition(incumbent: q5.Decision, structural: q5.Decision, deadline: float,
                          rng: np.random.Generator) -> dict:
    incumbent_vector = full.encode_decision(incumbent)
    structural_vector = full.encode_decision(structural)
    population = [incumbent_vector, structural_vector]
    population.extend(hybrid(incumbent_vector, structural_vector, (i,)) for i in range(5))
    population.extend(hybrid(structural_vector, incumbent_vector, (i,)) for i in range(5))
    while len(population) < 20:
        population.append(np.clip(incumbent_vector + rng.normal(0., .04, full.VECTOR_SIZE), 0., 1.))
    while len(population) < 24:
        selector = np.repeat(rng.random(5) < .5, 8)
        population.append(np.where(selector, incumbent_vector, structural_vector))
    while len(population) < FULL_POPULATION:
        population.append(rng.random(full.VECTOR_SIZE))
    population = np.asarray(population, float)
    mesh = q3.surface_mesh(full.PROXY_THETA, full.PROXY_LEVELS)
    times = np.arange(0., full.EARLIEST_ARRIVAL_S + FULL_PROXY_STEP_S * .25, FULL_PROXY_STEP_S)
    scores, metrics = [], []
    evaluations = failures = 0
    for vector in population:
        try:
            score, metric = full.proxy_score(full.decode_vector(vector), times, mesh)
        except Exception:
            score, metric = (-math.inf,) * 11, {}
            failures += 1
        scores.append(score)
        metrics.append(metric)
        evaluations += 1
    incumbent_strict = full.strict_record(incumbent)
    structural_strict = full.strict_record(structural)
    best_decision, best_strict = incumbent, incumbent_strict
    strict_audits = [
        {"source": "incumbent", **incumbent_strict},
        {"source": "a196_structural", **structural_strict},
    ]
    audited = {full.vector_key(incumbent_vector), full.vector_key(structural_vector)}
    generations = 0
    while time.perf_counter() < deadline:
        for index in range(len(population)):
            if time.perf_counter() >= deadline:
                break
            pool = [value for value in range(len(population)) if value != index]
            a, b, c = rng.choice(pool, 3, replace=False)
            mutant = np.clip(population[a] + .68 * (population[b] - population[c]), 0., 1.)
            crossover = rng.random(full.VECTOR_SIZE) < .72
            crossover[int(rng.integers(full.VECTOR_SIZE))] = True
            trial = np.where(crossover, mutant, population[index])
            try:
                score, metric = full.proxy_score(full.decode_vector(trial), times, mesh)
            except Exception:
                failures += 1
                evaluations += 1
                continue
            evaluations += 1
            if score > scores[index]:
                population[index], scores[index], metrics[index] = trial, score, metric
        generations += 1
        best_index = max(range(len(population)), key=lambda index: scores[index])
        if generations == 1 or generations % 3 == 0:
            key = full.vector_key(population[best_index])
            if key not in audited:
                audited.add(key)
                candidate = full.decode_vector(population[best_index], "a196_seeded_strict_audit")
                strict = full.strict_record(candidate)
                strict_audits.append({"source": f"generation_{generations}", **strict})
                if full.strict_better(strict, best_strict):
                    best_decision, best_strict = candidate, strict
        if generations == 1 or generations % 10 == 0:
            print(json.dumps(ready({
                "stage": "a196_full_refine_generation", "generation": generations,
                "evaluation_count": evaluations, "proxy_best": metrics[best_index],
                "strict_best_s": best_strict["longest_continuous_s"],
                "failure_count": failures, "remaining_search_s": max(0., deadline - time.perf_counter()),
            }), ensure_ascii=False), flush=True)
    for index in sorted(range(len(population)), key=lambda value: scores[value], reverse=True)[:4]:
        key = full.vector_key(population[index])
        if key in audited:
            continue
        candidate = full.decode_vector(population[index], "a196_seeded_final_proxy_audit")
        strict = full.strict_record(candidate)
        strict_audits.append({"source": "final_proxy", **strict})
        if full.strict_better(strict, best_strict):
            best_decision, best_strict = candidate, strict
    best_index = max(range(len(population)), key=lambda index: scores[index])
    return {
        "best_decision": best_decision, "best_strict_probe": best_strict,
        "incumbent_strict_probe": incumbent_strict, "structural_strict_probe": structural_strict,
        "strict_audits": strict_audits, "best_proxy": metrics[best_index],
        "evaluation_count": evaluations, "generation_count": generations,
        "failure_count": failures,
    }


def report_markdown(payload: dict) -> str:
    structural = payload["structural_reproduction"]
    strict = payload["strict_comparison"]
    lines = [
        "# Q5 A196 结构复现审计", "",
        f"状态：`{payload['status']}`；总用时 `{payload['elapsed_s']:.3f} s`。", "",
        "## 结论", "",
        f"A196 报告的 `21.0770 s` 不能与本项目的三导弹同时全遮蔽最长连续时长直接比较。附录主程序优化的是五架无人机、每架三枚单弹持续时间的直接求和，没有在主程序中执行烟团区间并集或三枚导弹区间交集。", "",
        f"本次按附录结构重新优化后，独立单弹代理时长和为 `{structural['independent_duration_sum_s']:.6f} s`；同一个 15 弹方案经严格 PROBE 复评，三导弹同时全遮蔽最长连续时长为 `{strict['structural_probe']['longest_continuous_s']:.9f} s`。", "",
        f"现有严格下界 SCREEN 为 `{strict['incumbent_screen']['longest_continuous_s']:.9f} s`；A196 结构播种搜索后的候选 SCREEN 为 `{strict['candidate_screen']['longest_continuous_s']:.9f} s`，差值 `{strict['screen_improvement_s']:.9f} s`。", "",
        "## 结构复现", "",
    ]
    for row in structural["platforms"]:
        lines.append(
            f"- {row['platform']}→{row['assigned_missile']}：航向 `{row['heading_deg']:.4f}°`，速度 `{row['speed_mps']:.4f} m/s`，投放 `{[round(v, 4) for v in row['release_times_s']]}`，共用引信 `{row['shared_fuse_s']:.4f} s`，独立时长和 `{row['proxy_metric']['independent_single_cloud_duration_sum_s']:.4f} s`。"
        )
    lines.extend([
        "", "## 证据边界", "",
        "`result3` 的网页截图分辨率不足，且支持材料未公开，因此本报告不猜测表中小数，也不声称精确复原论文参数。这里复现的是附录中可核验的量词、分配、投放间隔和累加方式，并使用题面正确的 FY5 纵坐标。", "",
        "本轮是固定种子、有限墙钟预算 pilot，只提供严格可行下界和指标不可比性的代码证据，不提供连续 40 维全局最优证明。正式 Q5、Q4、Q4_v2 与表格输出均未修改。", "",
    ])
    return "\n".join(lines)


def run(json_path: Path, report_path: Path, wall_time_s: float) -> dict:
    started = time.perf_counter()
    deadline = started + wall_time_s
    search_deadline = deadline - SEARCH_RESERVE_S
    structural_deadline = started + max(8., (search_deadline - started) * .38)
    rng = np.random.default_rng(RNG_SEED)
    assignments = nearest_missile_assignment()
    mesh = q3.surface_mesh(STRUCTURAL_THETA, STRUCTURAL_LEVELS)
    print(json.dumps(ready({
        "stage": "a196_structural_start", "assignments": [q5.MISSILE_NAMES[j] for j in assignments],
        "wall_time_s": wall_time_s, "surface_point_count": len(mesh.points),
        "exact_result3_recovery": False,
    }), ensure_ascii=False), flush=True)
    platform_rows = []
    for platform_index, missile_index in enumerate(assignments):
        now = time.perf_counter()
        platforms_left = 5 - platform_index
        platform_deadline = now + max(.5, (structural_deadline - now) / platforms_left)
        row = optimise_platform(platform_index, missile_index, platform_deadline, rng, mesh)
        platform_rows.append(row)
        write_checkpoint(json_path, "structural_platforms", {
            "completed_platform_count": len(platform_rows),
            "nearest_missile_assignments": [q5.MISSILE_NAMES[j] for j in assignments],
            "platforms": platform_rows,
            "elapsed_s": time.perf_counter() - started,
        })
        print(json.dumps(ready({
            "stage": "a196_platform_complete", "platform": row["platform"],
            "assigned_missile": row["assigned_missile"], "metric": row["proxy_metric"],
            "decision": {key: row[key] for key in ("heading_deg", "speed_mps", "release_times_s", "shared_fuse_s")},
            "elapsed_s": time.perf_counter() - started,
            "remaining_budget_s": max(0., deadline - time.perf_counter()),
        }), ensure_ascii=False), flush=True)
    structural_decision = combine_platforms(platform_rows, "a196_structural_reproduction")
    incumbent, incumbent_registered_screen = load_incumbent()
    refine = refine_full_condition(incumbent, structural_decision, search_deadline, rng)
    write_checkpoint(json_path, "full_condition_refinement", {
        "structural_reproduction": {
            "platforms": platform_rows,
            "independent_duration_sum_s": sum(
                row["proxy_metric"]["independent_single_cloud_duration_sum_s"] for row in platform_rows
            ),
        },
        "strict_probe": {
            "structural": refine["structural_strict_probe"],
            "incumbent": refine["incumbent_strict_probe"],
            "candidate": refine["best_strict_probe"],
        },
        "elapsed_s": time.perf_counter() - started,
    })
    incumbent_screen = full.strict_record(incumbent, q5.SCREEN)
    structural_screen = full.strict_record(structural_decision, q5.SCREEN)
    candidate_screen = full.strict_record(refine["best_decision"], q5.SCREEN)
    independent_sum = sum(row["proxy_metric"]["independent_single_cloud_duration_sum_s"] for row in platform_rows)
    payload = {
        "schema_version": "1.0", "spec_id": SPEC_ID, "status": "pilot_complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_audit": SOURCE_AUDIT,
        "reported_result": {
            "value_s": A196_REPORTED_S,
            "classification": "independent single-cloud duration accumulator; not verified as a simultaneous three-missile interval intersection",
            "directly_comparable_to_strict_longest_continuous": False,
        },
        "structural_reproduction": {
            "uses_official_fy5_coordinate": True,
            "nearest_missile_assignments": [q5.MISSILE_NAMES[j] for j in assignments],
            "independent_duration_sum_s": independent_sum,
            "platforms": platform_rows,
            "decision": q5.decision_record(structural_decision),
        },
        "strict_comparison": {
            "structural_probe": refine["structural_strict_probe"],
            "structural_screen": structural_screen,
            "incumbent_registered_screen": incumbent_registered_screen,
            "incumbent_screen": incumbent_screen,
            "candidate_probe": refine["best_strict_probe"],
            "candidate_screen": candidate_screen,
            "screen_improvement_s": candidate_screen["longest_continuous_s"] - incumbent_screen["longest_continuous_s"],
            "independent_sum_minus_structural_strict_s": independent_sum - structural_screen["longest_continuous_s"],
        },
        "refinement": {
            "algorithm": "A196/incumbent platform-block seeding plus bounded differential evolution",
            "decision_dimension": full.VECTOR_SIZE,
            "population_size": FULL_POPULATION,
            "evaluation_count": refine["evaluation_count"],
            "generation_count": refine["generation_count"],
            "failure_count": refine["failure_count"],
            "strict_audits": refine["strict_audits"],
            "best_proxy": refine["best_proxy"],
            "random_seed": RNG_SEED,
            "all_condition_proxy_uses_missile_assignment_labels": False,
            "continuous_domain_exhausted": False,
        },
        "best_decision": q5.decision_record(refine["best_decision"]),
        "claims": {
            "exact_A196_table_reproduced": False,
            "A196_executable_structure_reproduced": True,
            "strict_three_missile_re_evaluation": True,
            "formal_q5_result_modified": False,
            "global_optimality": False,
        },
        "input_hashes": {
            "data/A题.pdf": sha(OFFICIAL_PATH),
            "docs/q5_full_condition_search.json": sha(INCUMBENT_PATH),
            "planning/47_q5_a196_structural_audit_spec.md": sha(SPEC_PATH),
            "src/q5/a196_structural_audit.py": sha(Path(__file__)),
            "a196_image_pdf_external": A196_IMAGE_PDF_SHA256,
        },
        "software": {"python": platform.python_version(), "numpy": str(np.__version__)},
        "elapsed_s": time.perf_counter() - started,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(report_markdown(payload), encoding="utf-8")
    print(json.dumps(ready({
        "stage": "a196_audit_complete", "independent_duration_sum_s": independent_sum,
        "structural_strict_screen_s": structural_screen["longest_continuous_s"],
        "incumbent_screen_s": incumbent_screen["longest_continuous_s"],
        "candidate_screen_s": candidate_screen["longest_continuous_s"],
        "elapsed_s": payload["elapsed_s"],
    }), ensure_ascii=False), flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--wall-time-s", type=float, default=60.)
    args = parser.parse_args()
    if args.wall_time_s <= SEARCH_RESERVE_S + 10.:
        raise SystemExit("wall time must exceed 18 seconds")
    run(args.json, args.report, args.wall_time_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
