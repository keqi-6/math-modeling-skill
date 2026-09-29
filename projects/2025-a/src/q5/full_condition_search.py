"""Q5 full-condition stochastic pilot with dynamic three-missile cloud handoff."""
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

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.q3 import selection_pilot as q3  # noqa: E402
from src.q5 import solve as q5  # noqa: E402

SPEC_ID = "Q5-FULL-CONDITION-HANDOFF-1.0"
SPEC_PATH = ROOT / "planning/45_q5_full_condition_search_spec.md"
SEED_PATH = ROOT / "docs/q5_longest_pilot.json"
OFFICIAL_PATH = ROOT / "data/A题.pdf"
RNG_SEED = 20260829
VECTOR_SIZE = 40
POPULATION_SIZE = 36
GLOBAL_INJECTIONS_PER_GENERATION = 3
MAX_GENERATIONS = 300
PROXY_STEP_S = .5
PROXY_THETA = 16
PROXY_LEVELS = 3
STRICT_AUDIT_EVERY_GENERATIONS = 4
PERIODIC_STRICT_AUDIT_LIMIT = 16
FINAL_STRICT_AUDIT_LIMIT = 8
SEARCH_RESERVE_S = 4.
THRESHOLDS_M = (0., 2.5, 5., 10., 20., 40., 80., 160.)
EARLIEST_ARRIVAL_S = min(q5.ARRIVAL_TIMES)
LATEST_ARRIVAL_S = max(q5.ARRIVAL_TIMES)
RELEASE_HORIZON_S = EARLIEST_ARRIVAL_S - .1


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


def decision_from_record(record: dict, source: str) -> q5.Decision:
    headings = [0.] * 5
    speeds = [70.] * 5
    bombs = []
    for platform_row in record["platforms"]:
        index = q5.NAMES.index(platform_row["platform"])
        headings[index] = float(platform_row["heading_rad"])
        speeds[index] = float(platform_row["speed_mps"])
        for bomb in platform_row["bombs"]:
            bombs.append(q5.Bomb(index, 0, float(bomb["release_s"]), float(bomb["fuse_s"])))
    decision = q5.Decision(tuple(headings), tuple(speeds),
                           tuple(sorted(bombs, key=lambda row: (row.platform, row.release_s))), source)
    q5.validate(decision)
    return decision


def load_seed() -> tuple[q5.Decision, dict]:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    row = payload["best_before_refinement"]
    return decision_from_record(row["decision"], "full_condition_seed"), {
        "longest_continuous_s": float(row["longest_continuous_s"]),
        "longest_interval_s": [float(value) for value in row["longest_interval_s"]],
        "total_intersection_s": float(row["total_intersection_s"]),
    }


def _fill_platform_bombs(decision: q5.Decision, platform_index: int) -> list[tuple[float, float]]:
    rows = [(float(b.release_s), float(b.fuse_s)) for b in q5.by_platform(decision, platform_index)]
    for candidate in np.arange(0., RELEASE_HORIZON_S + 1e-9, 1.):
        if len(rows) >= 3:
            break
        if all(abs(candidate - release) >= 1. - 1e-10 for release, _ in rows):
            rows.append((float(candidate), 0.))
    rows.sort()
    if len(rows) != 3:
        raise q5.Q5Error("Q5_FULL_CAPACITY_EXTENSION_FAILURE", q5.NAMES[platform_index])
    return rows


def encode_decision(decision: q5.Decision) -> np.ndarray:
    """Encode a valid <=15-bomb decision into the full 15-bomb unit cube."""
    vector = np.empty(VECTOR_SIZE, float)
    release_scale = RELEASE_HORIZON_S - 2.
    for i in range(5):
        base = 8 * i
        vector[base] = (decision.headings_rad[i] % (2 * math.pi)) / (2 * math.pi)
        vector[base + 1] = (decision.speeds_mps[i] - 70.) / 70.
        rows = _fill_platform_bombs(decision, i)
        for ordinal, (release, fuse) in enumerate(rows):
            vector[base + 2 + ordinal] = (release - ordinal) / release_scale
            maximum_fuse = min(
                math.sqrt(2. * q5.ORIGINS[i, 2] / q5.p().gravity),
                max(0., LATEST_ARRIVAL_S - release),
            )
            vector[base + 5 + ordinal] = fuse / maximum_fuse if maximum_fuse > 0 else 0.
    return np.clip(vector, 0., 1.)


def decode_vector(vector: np.ndarray, source: str = "full_condition_candidate") -> q5.Decision:
    values = np.clip(np.asarray(vector, float), 0., 1.)
    if values.shape != (VECTOR_SIZE,):
        raise q5.Q5Error("Q5_FULL_VECTOR_SHAPE", str(values.shape))
    headings, speeds, bombs = [], [], []
    release_scale = RELEASE_HORIZON_S - 2.
    for i in range(5):
        base = 8 * i
        headings.append(float(values[base] * 2 * math.pi) % (2 * math.pi))
        speeds.append(float(70. + 70. * values[base + 1]))
        raw_releases = np.sort(values[base + 2:base + 5])
        releases = release_scale * raw_releases + np.arange(3, dtype=float)
        for ordinal, release in enumerate(releases):
            maximum_fuse = min(
                math.sqrt(2. * q5.ORIGINS[i, 2] / q5.p().gravity),
                max(0., LATEST_ARRIVAL_S - float(release)),
            )
            fuse = float(values[base + 5 + ordinal] * maximum_fuse)
            bombs.append(q5.Bomb(i, 0, float(release), fuse))
    decision = q5.Decision(tuple(headings), tuple(speeds), tuple(bombs), source)
    q5.validate(decision)
    return decision


def random_vector(rng: np.random.Generator) -> np.ndarray:
    return rng.random(VECTOR_SIZE)


def _longest_run(times: np.ndarray, flags: np.ndarray) -> tuple[float, list[float] | None, int]:
    best_first = best_last = None
    first = None
    for index, flag in enumerate(np.asarray(flags, bool)):
        if flag and first is None:
            first = index
        if first is not None and (not flag or index == len(flags) - 1):
            last = index if flag and index == len(flags) - 1 else index - 1
            if best_first is None or times[last] - times[first] > times[best_last] - times[best_first]:
                best_first, best_last = first, last
            first = None
    if best_first is None:
        return 0., None, 0
    return (float(times[best_last] - times[best_first]),
            [float(times[best_first]), float(times[best_last])],
            int(best_last - best_first + 1))


def proxy_score(decision: q5.Decision, times: np.ndarray, mesh) -> tuple[tuple, dict]:
    per_missile = np.vstack([
        q5.strict_margins(decision, j, times, mesh, assume_valid=True) for j in range(3)
    ])
    global_margins = np.max(per_missile, axis=0)
    runs = []
    intervals = []
    for threshold in THRESHOLDS_M:
        duration, interval, count = _longest_run(times, global_margins <= threshold)
        runs.append(duration)
        intervals.append({"threshold_m": threshold, "duration_s": duration,
                          "interval_s": interval, "node_count": count})
    strict_interval = intervals[0]["interval_s"]
    if strict_interval is None:
        extension_margin = float(np.min(global_margins))
    else:
        first = int(np.searchsorted(times, strict_interval[0]))
        last = int(np.searchsorted(times, strict_interval[1]))
        neighbours = []
        if first > 0:
            neighbours.append(float(global_margins[first - 1]))
        if last + 1 < len(times):
            neighbours.append(float(global_margins[last + 1]))
        extension_margin = max(neighbours, default=float(np.max(global_margins[first:last + 1])))
    finite = global_margins[np.isfinite(global_margins)]
    if not len(finite):
        tail = (-math.inf, -math.inf)
    else:
        ordered = np.sort(finite)
        tail = (-float(ordered[0]), -float(np.mean(ordered[:min(12, len(ordered))])))
    score = (runs[0], -extension_margin, *runs[1:], *tail)
    return score, {
        "longest_continuous_node_s": runs[0],
        "longest_interval_nodes_s": intervals[0]["interval_s"],
        "threshold_runs": intervals,
        "strict_extension_margin_m": extension_margin,
        "minimum_global_margin_m": float(np.min(finite)) if len(finite) else math.inf,
        "minimum_per_missile_margin_m": [float(np.min(row)) for row in per_missile],
    }


def score_key_text(score: tuple) -> list[float]:
    return [float(value) for value in score]


def vector_key(vector: np.ndarray) -> str:
    return hashlib.sha256(np.round(vector, 12).tobytes()).hexdigest()


def strict_record(decision: q5.Decision, settings: dict | None = None) -> dict:
    settings = q5.PROBE if settings is None else settings
    result = q5.evaluate(decision, settings)
    return {
        "settings": settings["name"],
        "longest_continuous_s": result["longest_continuous_s"],
        "longest_interval_s": result["longest_interval_s"],
        "total_intersection_s": result["total_intersection_s"],
        "intersection_intervals_s": result["intersection_intervals_s"],
        "durations_s": result["durations_s"],
    }


def strict_better(candidate: dict, current: dict) -> bool:
    return (candidate["longest_continuous_s"], candidate["total_intersection_s"]) > (
        current["longest_continuous_s"], current["total_intersection_s"])


def relabel(decision: q5.Decision) -> q5.Decision:
    bombs = tuple(q5.Bomb(b.platform, index % 3, b.release_s, b.fuse_s)
                  for index, b in enumerate(decision.bombs))
    return q5.Decision(decision.headings_rad, decision.speeds_mps, bombs, "label_invariance_audit")


def label_invariance_audit(decision: q5.Decision) -> dict:
    mesh = q3.surface_mesh(16, 3)
    times = np.linspace(0., EARLIEST_ARRIVAL_S, 17)
    changed = relabel(decision)
    differences = []
    for j in range(3):
        a = q5.strict_margins(decision, j, times, mesh)
        b = q5.strict_margins(changed, j, times, mesh)
        if not np.array_equal(a, b):
            differences.append(math.inf)
        else:
            finite = np.isfinite(a)
            differences.append(float(np.max(np.abs(a[finite] - b[finite]))) if np.any(finite) else 0.)
    return {"maximum_margin_change_m": max(differences), "pass": max(differences) <= 1e-12}


def handoff_audit(decision: q5.Decision, interval: list[float] | None) -> dict:
    if interval is None:
        return {"available": False}
    left, right = map(float, interval)
    times = np.unique(np.r_[np.arange(left, right + 1e-12, .25), right])
    mesh = q3.surface_mesh(32, 5)
    per_missile = []
    for j in range(3):
        last_contributors = None
        switches = joint_only = single_full = union_full = 0
        contributor_counts = []
        examples = []
        for t in times:
            missile = q5.pilot.missile(j, np.array([t]))
            visible = q3.visibility_mask(missile, mesh)[0]
            distances, indices = [], []
            for index, bomb in enumerate(decision.bombs):
                et = q5.explosion_time(bomb)
                if et - q5.TIME_TOL <= t <= min(et + q5.p().smoke_duration, q5.arrival(j)) + q5.TIME_TOL:
                    row = q3._distance_to_segments(
                        q5.cloud(decision, bomb, np.array([t])), missile, mesh
                    )[0]
                    distances.append(row)
                    indices.append(index)
            if not distances or not np.any(visible):
                contributors = frozenset()
                full = False
                singles = 0
            else:
                matrix = np.vstack(distances)
                visible_matrix = matrix[:, visible]
                full = bool(np.max(np.min(visible_matrix, axis=0)) <= q5.p().smoke_radius + 1e-12)
                singles = int(np.sum(np.max(visible_matrix, axis=1) <= q5.p().smoke_radius + 1e-12))
                winners = np.argmin(visible_matrix, axis=0)
                contributors = frozenset(indices[int(value)] for value in np.unique(winners))
            union_full += int(full)
            single_full += int(full and singles > 0)
            joint_only += int(full and singles == 0)
            contributor_counts.append(len(contributors))
            if last_contributors is not None and contributors != last_contributors:
                switches += 1
            if len(examples) < 5 and full and (singles == 0 or len(contributors) > 1):
                examples.append({"time_s": float(t), "contributing_bomb_indices": sorted(contributors),
                                 "single_full_cloud_count": singles})
            last_contributors = contributors
        per_missile.append({
            "missile": q5.MISSILE_NAMES[j],
            "sample_count": len(times),
            "union_full_sample_count": union_full,
            "single_cloud_full_sample_count": single_full,
            "joint_only_full_sample_count": joint_only,
            "contributor_set_switch_count": switches,
            "maximum_contributing_cloud_count": max(contributor_counts, default=0),
            "examples": examples,
        })
    return {"available": True, "sample_step_s": .25, "per_missile": per_missile}


def decision_payload(decision: q5.Decision) -> dict:
    return q5.decision_record(decision)


def report_markdown(payload: dict) -> str:
    best = payload["best_strict_probe"]
    baseline = payload["baseline_strict_probe"]
    screen = payload["screen_verification"]
    lines = [
        "# Q5 全条件动态接力搜索 pilot", "",
        f"状态：`{payload['status']}`；用时 `{payload['elapsed_s']:.3f} s`。", "",
        f"- 历史下界：`{baseline['longest_continuous_s']:.9f} s`，`{baseline['longest_interval_s']}`。",
        f"- 本轮严格最优：`{best['longest_continuous_s']:.9f} s`，`{best['longest_interval_s']}`。",
        f"- 提升：`{payload['improvement_over_baseline_s']:.9f} s`。",
        f"- SCREEN 加密复核：基线 `{screen['baseline']['longest_continuous_s']:.9f} s`，"
        f"候选 `{screen['candidate']['longest_continuous_s']:.9f} s`，"
        f"差值 `{screen['improvement_s']:.9f} s`。",
        f"- 代理评价 `{payload['search']['evaluation_count']}` 次，全域随机注入 "
        f"`{payload['search']['global_sample_count']}` 个。", "",
        "## 搜索语义", "",
        "五个平台的航向、速度、三次投放时刻和三枚弹引信均进入同一40维决策向量。搜索不使用主责导弹标签、指定平台或固定接力次序；每个 `(t,j,P)` 都独立在全部有效烟团中选择几何距离最小者。", "",
        "本轮未使用候选删除式几何剪枝。代理层的正裕量阈值只用于给不连续目标提供排序方向，所有严格接受仍要求三枚导弹在同一连续区间满足零裕量全遮蔽。", "",
        "## 接力量词审计", "",
    ]
    for row in payload["handoff_audit"].get("per_missile", []):
        lines.append(
            f"- {row['missile']}：联合完整节点 `{row['union_full_sample_count']}/{row['sample_count']}`，"
            f"其中只能靠多团联合的节点 `{row['joint_only_full_sample_count']}`，"
            f"贡献烟团集合切换 `{row['contributor_set_switch_count']}` 次，"
            f"单时刻最多 `{row['maximum_contributing_cloud_count']}` 团参与。"
        )
    lines.extend([
        "", "## 证明边界", "",
        "本 pilot 覆盖完整变量类型和题面约束，并在完整三导弹动态量词下评价，但60秒随机有限预算没有穷尽连续40维可行域。结果只是一条严格可行下界，不是全局最优证明。",
        "正式 Q5、Q4、Q4_v2 与表格输出均未修改。",
    ])
    return "\n".join(lines) + "\n"


def run(json_path: Path, report_path: Path, wall_time_s: float) -> dict:
    started = time.perf_counter()
    deadline = started + wall_time_s
    search_deadline = deadline - SEARCH_RESERVE_S
    seed, seed_summary = load_seed()
    baseline_strict = strict_record(seed)
    seed_vector = encode_decision(seed)
    augmented_seed = decode_vector(seed_vector, "full_condition_augmented_seed")
    mesh = q3.surface_mesh(PROXY_THETA, PROXY_LEVELS)
    times = np.arange(0., EARLIEST_ARRIVAL_S + PROXY_STEP_S * .25, PROXY_STEP_S)
    rng = np.random.default_rng(RNG_SEED)

    population = [seed_vector]
    local_count = (POPULATION_SIZE - 1) // 3
    for _ in range(local_count):
        population.append(np.clip(seed_vector + rng.normal(0., .08, VECTOR_SIZE), 0., 1.))
    while len(population) < POPULATION_SIZE * 2 // 3:
        selector = rng.random(VECTOR_SIZE) < .5
        global_row = random_vector(rng)
        population.append(np.where(selector, seed_vector, global_row))
    while len(population) < POPULATION_SIZE:
        population.append(random_vector(rng))
    population = np.asarray(population, float)

    scores, metrics = [], []
    failures = 0
    global_samples = POPULATION_SIZE - 1 - local_count
    for vector in population:
        try:
            score, metric = proxy_score(decode_vector(vector), times, mesh)
        except Exception:
            failures += 1
            score, metric = (-math.inf,) * (len(THRESHOLDS_M) + 3), {}
        scores.append(score)
        metrics.append(metric)
    evaluation_count = len(population)
    scores = list(scores)
    strict_cache = {}
    best_decision = seed
    best_strict = baseline_strict
    strict_audits = [{"source": "historical_seed", **baseline_strict}]
    audited_vectors = set()
    generations = 0
    local_probe_count = 0

    print(json.dumps(ready({
        "stage": "full_condition_start", "population_size": POPULATION_SIZE,
        "decision_dimension": VECTOR_SIZE, "proxy_time_count": len(times),
        "surface_point_count": len(mesh.points), "baseline_strict": baseline_strict,
        "seed_proxy": metrics[0], "wall_time_s": wall_time_s,
    }), ensure_ascii=False), flush=True)

    for generation in range(1, MAX_GENERATIONS + 1):
        if time.perf_counter() >= search_deadline:
            break
        order = sorted(range(len(population)), key=lambda index: scores[index], reverse=True)
        best_index = order[0]
        for index in range(len(population)):
            if time.perf_counter() >= search_deadline:
                break
            pool = [value for value in range(len(population)) if value != index]
            a, b, c = rng.choice(pool, 3, replace=False)
            mutant = np.clip(population[a] + .72 * (population[b] - population[c]), 0., 1.)
            crossover = rng.random(VECTOR_SIZE) < .76
            crossover[int(rng.integers(VECTOR_SIZE))] = True
            trial = np.where(crossover, mutant, population[index])
            try:
                trial_score, trial_metric = proxy_score(decode_vector(trial), times, mesh)
            except Exception:
                failures += 1
                evaluation_count += 1
                continue
            evaluation_count += 1
            if trial_score > scores[index]:
                population[index] = trial
                scores[index] = trial_score
                metrics[index] = trial_metric

        worst = sorted(range(len(population)), key=lambda index: scores[index])[:GLOBAL_INJECTIONS_PER_GENERATION]
        for index in worst:
            if time.perf_counter() >= search_deadline:
                break
            trial = random_vector(rng)
            trial_score, trial_metric = proxy_score(decode_vector(trial), times, mesh)
            population[index], scores[index], metrics[index] = trial, trial_score, trial_metric
            evaluation_count += 1
            global_samples += 1

        # Symmetric fine probes cycle through every coordinate of every
        # platform block. They improve resolution without assigning any
        # platform, bomb, or cloud to a missile.
        best_index = max(range(len(population)), key=lambda index: scores[index])
        sigma = max(.003, .03 * (.985 ** generation))
        for platform_index in range(5):
            if time.perf_counter() >= search_deadline:
                break
            trial = population[best_index].copy()
            coordinate = 8 * platform_index + (generation + platform_index) % 8
            trial[coordinate] = np.clip(trial[coordinate] + rng.normal(0., sigma), 0., 1.)
            trial_score, trial_metric = proxy_score(decode_vector(trial), times, mesh)
            evaluation_count += 1
            local_probe_count += 1
            worst_index = min(range(len(population)), key=lambda index: scores[index])
            if trial_score > scores[worst_index]:
                population[worst_index] = trial
                scores[worst_index] = trial_score
                metrics[worst_index] = trial_metric
                if trial_score > scores[best_index]:
                    best_index = worst_index

        generations = generation
        best_index = max(range(len(population)), key=lambda index: scores[index])
        if generation == 1 or generation % STRICT_AUDIT_EVERY_GENERATIONS == 0:
            key = vector_key(population[best_index])
            if key not in audited_vectors and len(strict_audits) <= PERIODIC_STRICT_AUDIT_LIMIT:
                audited_vectors.add(key)
                candidate = decode_vector(population[best_index], "full_condition_strict_audit")
                strict = strict_record(candidate)
                strict_cache[key] = strict
                strict_audits.append({"source": f"generation_{generation}", **strict})
                if strict_better(strict, best_strict):
                    best_decision, best_strict = candidate, strict
        elapsed = time.perf_counter() - started
        print(json.dumps(ready({
            "stage": "full_condition_generation", "generation": generation,
            "evaluation_count": evaluation_count, "global_sample_count": global_samples,
            "local_probe_count": local_probe_count,
            "proxy_best": metrics[best_index], "strict_best_s": best_strict["longest_continuous_s"],
            "failure_count": failures, "elapsed_s": elapsed,
            "remaining_budget_s": max(0., deadline - time.perf_counter()),
        }), ensure_ascii=False), flush=True)

    ranked = sorted(range(len(population)), key=lambda index: scores[index], reverse=True)
    final_audit_count = 0
    for index in ranked:
        if time.perf_counter() >= deadline - .8 or final_audit_count >= FINAL_STRICT_AUDIT_LIMIT:
            break
        key = vector_key(population[index])
        if key in audited_vectors:
            continue
        audited_vectors.add(key)
        candidate = decode_vector(population[index], "full_condition_final_audit")
        strict = strict_record(candidate)
        final_audit_count += 1
        strict_audits.append({"source": "final_top_proxy", **strict})
        if strict_better(strict, best_strict):
            best_decision, best_strict = candidate, strict

    baseline_screen = strict_record(seed, q5.SCREEN)
    best_screen = strict_record(best_decision, q5.SCREEN)
    screen_verification = {
        "baseline": baseline_screen,
        "candidate": best_screen,
        "improvement_s": best_screen["longest_continuous_s"] - baseline_screen["longest_continuous_s"],
        "candidate_retains_improvement": best_screen["longest_continuous_s"] > baseline_screen["longest_continuous_s"],
    }
    label_audit = label_invariance_audit(best_decision)
    handoff = handoff_audit(best_decision, best_screen["longest_interval_s"])
    best_proxy_index = max(range(len(population)), key=lambda index: scores[index])
    elapsed = time.perf_counter() - started
    payload = {
        "schema_version": "1.0", "spec_id": SPEC_ID,
        "status": "pilot_complete" if generations else "pilot_initialisation_only",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "longest connected interval satisfying forall missile, forall visible target point, exists active cloud",
        "baseline_seed_record": seed_summary,
        "baseline_strict_probe": baseline_strict,
        "best_strict_probe": best_strict,
        "screen_verification": screen_verification,
        "improvement_over_baseline_s": best_strict["longest_continuous_s"] - baseline_strict["longest_continuous_s"],
        "best_decision": decision_payload(best_decision),
        "best_proxy": metrics[best_proxy_index],
        "best_proxy_score": score_key_text(scores[best_proxy_index]),
        "strict_audits": strict_audits,
        "handoff_audit": handoff,
        "label_invariance_audit": label_audit,
        "search": {
            "algorithm": "bounded differential evolution with global-domain injection",
            "decision_dimension": VECTOR_SIZE, "population_size": POPULATION_SIZE,
            "generation_count": generations, "maximum_generations": MAX_GENERATIONS,
            "evaluation_count": evaluation_count, "global_sample_count": global_samples,
            "local_probe_count": local_probe_count,
            "failure_count": failures, "random_seed": RNG_SEED,
            "repetition_policy": "one fixed-seed 60-second working pilot; no distributional or global-optimality claim",
            "variability_summary": "not estimated in this single-budget run",
            "proxy_step_s": PROXY_STEP_S, "proxy_surface_theta": PROXY_THETA,
            "proxy_surface_levels": PROXY_LEVELS, "thresholds_m": THRESHOLDS_M,
            "search_time_interval_s": [0., EARLIEST_ARRIVAL_S],
            "heuristic_candidate_deletion": False,
            "geometric_candidate_pruning_applied": False,
            "all_five_platforms_in_vector": True,
            "three_bombs_per_platform_in_vector": True,
            "missile_labels_used_by_search": False,
        },
        "claims": {
            "all_three_missiles_simultaneous": True,
            "cloud_identity_dynamic_in_time_missile_surface": True,
            "single_joint_single_handoff_allowed": True,
            "strict_probe_verified": True,
            "screen_verified": True,
            "formal_q5_result": False,
            "continuous_domain_exhausted": False,
            "global_optimality": False,
        },
        "input_hashes": {
            "data/A题.pdf": sha(OFFICIAL_PATH),
            "docs/q5_longest_pilot.json": sha(SEED_PATH),
            "planning/45_q5_full_condition_search_spec.md": sha(SPEC_PATH),
            "src/q5/full_condition_search.py": sha(Path(__file__)),
        },
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        "elapsed_s": elapsed,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(report_markdown(payload), encoding="utf-8")
    print(json.dumps(ready({
        "stage": "full_condition_complete", "status": payload["status"],
        "generations": generations, "evaluation_count": evaluation_count,
        "global_sample_count": global_samples,
        "best_strict_s": best_strict["longest_continuous_s"],
        "improvement_s": payload["improvement_over_baseline_s"], "elapsed_s": elapsed,
    }), ensure_ascii=False), flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--wall-time-s", type=float, default=60.)
    args = parser.parse_args()
    if args.wall_time_s <= SEARCH_RESERVE_S + 1.:
        raise SystemExit("wall time must exceed search reserve")
    run(args.json, args.report, args.wall_time_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
