"""Equal-budget full-horizon window-feasibility pilot for Q5."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.q3 import selection_pilot as q3  # noqa: E402
from src.q5 import full_condition_search as full  # noqa: E402
from src.q5 import solve as q5  # noqa: E402

SPEC_ID = "Q5-FULL-HORIZON-WINDOW-1.0"
SPEC_PATH = ROOT / "planning/46_q5_full_horizon_window_spec.md"
SEED_PATH = ROOT / "docs/q5_full_condition_search.json"
OFFICIAL_PATH = ROOT / "data/A题.pdf"
RNG_SEED = 20260830
POPULATION_SIZE = 10
PROXY_THETA = 16
PROXY_LEVELS = 3
PROXY_TIME_STEP_S = .5
MAX_COMPLETE_ROUNDS = 80
FINAL_RESERVE_S = 4.5
FINAL_NEAR_WINDOW_COUNT = 12
STRICT_FINAL_LIMIT = 24
INFEASIBLE_MARGIN_M = 1_000_000.


@dataclass
class WindowState:
    start_s: float
    end_s: float
    times: np.ndarray
    population: np.ndarray
    scores: list[tuple]
    metrics: list[dict]
    evaluations: int
    generations: int = 0

    def best_index(self) -> int:
        return max(range(len(self.population)), key=lambda index: self.scores[index])


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


def window_starts(horizon_s: float, duration_s: float, step_s: float) -> np.ndarray:
    if not 0 < duration_s <= horizon_s or step_s <= 0:
        raise ValueError("invalid horizon window settings")
    last = float(horizon_s - duration_s)
    regular = np.arange(0., last + 1e-12, step_s)
    values = np.unique(np.r_[regular, last])
    values.sort()
    values[0], values[-1] = 0., last
    return values


def window_times(start_s: float, duration_s: float, step_s: float = PROXY_TIME_STEP_S) -> np.ndarray:
    count = int(math.floor(duration_s / step_s + 1e-12))
    values = start_s + step_s * np.arange(count + 1, dtype=float)
    end = float(start_s + duration_s)
    if values[-1] < end - 1e-12:
        values = np.r_[values, end]
    else:
        values[-1] = end
    return values


def load_incumbent() -> tuple[q5.Decision, dict]:
    payload = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    decision = full.decision_from_record(payload["best_decision"], "full_horizon_incumbent")
    return decision, {
        "probe": payload["best_strict_probe"],
        "screen": payload["screen_verification"]["candidate"],
    }


def retime_decision(decision: q5.Decision, delta_s: float) -> q5.Decision:
    bombs = []
    for i in range(5):
        rows = list(q5.by_platform(decision, i))
        releases = np.array([bomb.release_s + delta_s for bomb in rows], float)
        if releases[0] < 0.:
            releases -= releases[0]
        if releases[-1] > full.RELEASE_HORIZON_S:
            releases -= releases[-1] - full.RELEASE_HORIZON_S
        for release, bomb in zip(releases, rows):
            maximum_fuse = min(
                math.sqrt(2. * q5.ORIGINS[i, 2] / q5.p().gravity),
                max(0., full.LATEST_ARRIVAL_S - float(release)),
            )
            bombs.append(q5.Bomb(i, 0, float(release), min(float(bomb.fuse_s), maximum_fuse)))
    candidate = q5.Decision(decision.headings_rad, decision.speeds_mps,
                            tuple(sorted(bombs, key=lambda row: (row.platform, row.release_s))),
                            "full_horizon_retimed")
    q5.validate(candidate)
    return candidate


def margin_metrics(global_margins: np.ndarray) -> tuple[tuple, dict]:
    margins = np.asarray(global_margins, float)
    finite = np.where(np.isfinite(margins), margins, INFEASIBLE_MARGIN_M)
    ordered = np.sort(finite)[::-1]
    maximum = float(ordered[0])
    worst_mean = float(np.mean(ordered[:min(5, len(ordered))]))
    positive_count = int(np.sum(finite > 0.))
    score = (-maximum, -worst_mean, -positive_count, -float(np.mean(np.maximum(finite, 0.))))
    return score, {
        "maximum_margin_m": maximum,
        "worst_five_mean_margin_m": worst_mean,
        "positive_node_count": positive_count,
        "full_node_count": int(len(finite) - positive_count),
        "node_count": len(finite),
        "proxy_feasible": maximum <= 0.,
    }


def window_score(decision: q5.Decision, times: np.ndarray, mesh) -> tuple[tuple, dict]:
    per_missile = np.vstack([
        q5.strict_margins(decision, j, times, mesh, assume_valid=True) for j in range(3)
    ])
    score, metrics = margin_metrics(np.max(per_missile, axis=0))
    metrics["minimum_per_missile_margin_m"] = [float(np.min(row)) for row in per_missile]
    return score, metrics


def initialise_window(start_s: float, duration_s: float, incumbent: q5.Decision,
                      reference_start_s: float, mesh, rng: np.random.Generator) -> WindowState:
    times = window_times(start_s, duration_s)
    base = full.encode_decision(retime_decision(incumbent, start_s - reference_start_s))
    rows = [base]
    while len(rows) < 4:
        rows.append(np.clip(base + rng.normal(0., .08, full.VECTOR_SIZE), 0., 1.))
    while len(rows) < 7:
        global_row = full.random_vector(rng)
        selector = rng.random(full.VECTOR_SIZE) < .5
        rows.append(np.where(selector, base, global_row))
    while len(rows) < POPULATION_SIZE:
        rows.append(full.random_vector(rng))
    population = np.asarray(rows, float)
    scores, metrics = [], []
    for vector in population:
        score, metric = window_score(full.decode_vector(vector), times, mesh)
        scores.append(score)
        metrics.append(metric)
    return WindowState(float(start_s), float(start_s + duration_s), times,
                       population, scores, metrics, len(population))


def advance_window(state: WindowState, mesh, rng: np.random.Generator) -> None:
    population = state.population
    for index in range(len(population)):
        pool = [value for value in range(len(population)) if value != index]
        a, b, c = rng.choice(pool, 3, replace=False)
        mutant = np.clip(population[a] + .70 * (population[b] - population[c]), 0., 1.)
        crossover = rng.random(full.VECTOR_SIZE) < .72
        crossover[int(rng.integers(full.VECTOR_SIZE))] = True
        trial = np.where(crossover, mutant, population[index])
        score, metric = window_score(full.decode_vector(trial), state.times, mesh)
        state.evaluations += 1
        if score > state.scores[index]:
            population[index], state.scores[index], state.metrics[index] = trial, score, metric

    worst = min(range(len(population)), key=lambda index: state.scores[index])
    trial = full.random_vector(rng)
    score, metric = window_score(full.decode_vector(trial), state.times, mesh)
    population[worst], state.scores[worst], state.metrics[worst] = trial, score, metric
    state.evaluations += 1

    best = state.best_index()
    trial = population[best].copy()
    coordinate = (state.generations + int(round(2 * state.start_s))) % full.VECTOR_SIZE
    sigma = max(.004, .035 * (.97 ** state.generations))
    trial[coordinate] = np.clip(trial[coordinate] + rng.normal(0., sigma), 0., 1.)
    score, metric = window_score(full.decode_vector(trial), state.times, mesh)
    state.evaluations += 1
    worst = min(range(len(population)), key=lambda index: state.scores[index])
    if score > state.scores[worst]:
        population[worst], state.scores[worst], state.metrics[worst] = trial, score, metric
    state.generations += 1


def state_record(state: WindowState) -> dict:
    index = state.best_index()
    return {
        "start_s": state.start_s, "end_s": state.end_s,
        "generations": state.generations, "evaluation_count": state.evaluations,
        **state.metrics[index],
    }


def strict_summary(decision: q5.Decision, settings: dict) -> dict:
    return full.strict_record(decision, settings)


def report_markdown(payload: dict) -> str:
    probe = payload["best_strict_probe"]
    screen = payload["screen_verification"]
    coverage = payload["horizon_coverage"]
    lines = [
        "# Q5 全时域窗口可行性搜索 pilot", "",
        f"状态：`{payload['status']}`；用时 `{payload['elapsed_s']:.3f} s`。", "",
        f"- 公共完整时域：`[0,{coverage['horizon_end_s']:.12f}] s`。",
        f"- 窗口：长度 `{coverage['window_duration_s']:.3f} s`，起点步长 "
        f"`{coverage['window_step_s']:.3f} s`，总数 `{coverage['window_count']}`。",
        f"- 每窗完整轮数：`{coverage['minimum_generations_per_window']}`；评价次数范围 "
        f"`[{coverage['minimum_evaluations_per_window']},{coverage['maximum_evaluations_per_window']}]`。",
        f"- PROBE 最优：`{probe['longest_continuous_s']:.9f} s`，`{probe['longest_interval_s']}`。",
        f"- SCREEN：基线 `{screen['baseline']['longest_continuous_s']:.9f} s`，"
        f"本轮 `{screen['candidate']['longest_continuous_s']:.9f} s`，"
        f"差值 `{screen['improvement_s']:.9f} s`。", "",
        "## 全时域搜索覆盖", "",
        "全部窗口在初始化后按起点轮转；只有完成所有窗口的一整轮后才进入下一轮。未按当前最优窗口追加专属轮数，也未使用候选删除式几何剪枝。最后一个窗口精确贴合公共时域右端。", "",
        f"代理可行窗口 `{coverage['proxy_feasible_window_count']}` 个；进入连续严格复核的不同候选 "
        f"`{payload['strict_verification']['unique_candidate_count']}` 个。", "",
        "## 各十秒时段的最佳窗口裕量", "",
        "| 起点时段 / s | 最小最大裕量 / m | 对应窗口起点 / s |", "|---:|---:|---:|",
    ]
    for row in payload["horizon_bins"]:
        lines.append(f"| {row['bin_s']} | {row['best_maximum_margin_m']:.6f} | {row['best_start_s']:.6f} |")
    lines.extend([
        "", "## 主张边界", "",
        "本轮完整覆盖已声明的有限窗口起点族，并保证各窗口搜索预算相同；窗口内部仍是有限预算随机搜索，0.5秒起点与表面代理也不是连续域穷尽。因此结果只是一条全时域均衡搜索下的严格可行下界，不是全局最优证明。",
        "正式 Q5、Q4、Q4_v2 与表格输出均未修改。",
    ])
    return "\n".join(lines) + "\n"


def run(json_path: Path, report_path: Path, wall_time_s: float,
        window_step_s: float, window_duration_s: float) -> dict:
    started = time.perf_counter()
    deadline = started + wall_time_s
    rng = np.random.default_rng(RNG_SEED)
    incumbent, incumbent_record = load_incumbent()
    baseline_probe = strict_summary(incumbent, q5.PROBE)
    baseline_screen = strict_summary(incumbent, q5.SCREEN)
    reference_start = round(float(baseline_probe["longest_interval_s"][0]) / window_step_s) * window_step_s
    starts = window_starts(full.EARLIEST_ARRIVAL_S, window_duration_s, window_step_s)
    mesh = q3.surface_mesh(PROXY_THETA, PROXY_LEVELS)

    states = [initialise_window(float(start), window_duration_s, incumbent,
                                reference_start, mesh, rng) for start in starts]
    initial_elapsed = time.perf_counter() - started
    print(json.dumps(ready({
        "stage": "full_horizon_initialised", "horizon_s": [0., full.EARLIEST_ARRIVAL_S],
        "window_count": len(states), "first_window_s": [states[0].start_s, states[0].end_s],
        "last_window_s": [states[-1].start_s, states[-1].end_s],
        "evaluations": sum(state.evaluations for state in states),
        "proxy_feasible_windows": sum(state.metrics[state.best_index()]["proxy_feasible"] for state in states),
        "elapsed_s": initial_elapsed, "remaining_budget_s": deadline - time.perf_counter(),
    }), ensure_ascii=False), flush=True)

    complete_rounds = 0
    last_round_duration = max(.1, initial_elapsed)
    for round_number in range(1, MAX_COMPLETE_ROUNDS + 1):
        now = time.perf_counter()
        predicted = max(last_round_duration * 1.20, .5)
        if now + predicted >= deadline - FINAL_RESERVE_S:
            break
        round_started = now
        for state in states:
            advance_window(state, mesh, rng)
        complete_rounds = round_number
        last_round_duration = time.perf_counter() - round_started
        records = [state_record(state) for state in states]
        best = min(records, key=lambda row: row["maximum_margin_m"])
        print(json.dumps(ready({
            "stage": "full_horizon_round", "round": round_number,
            "all_windows_generations": [min(state.generations for state in states),
                                         max(state.generations for state in states)],
            "evaluations": sum(state.evaluations for state in states),
            "proxy_feasible_windows": sum(row["proxy_feasible"] for row in records),
            "best_window_start_s": best["start_s"], "best_maximum_margin_m": best["maximum_margin_m"],
            "round_elapsed_s": last_round_duration, "elapsed_s": time.perf_counter() - started,
            "remaining_budget_s": deadline - time.perf_counter(),
        }), ensure_ascii=False), flush=True)

    records = [state_record(state) for state in states]
    ordered_states = sorted(states, key=lambda state: state.metrics[state.best_index()]["maximum_margin_m"])
    candidate_states = [state for state in ordered_states
                        if state.metrics[state.best_index()]["proxy_feasible"]]
    candidate_states.extend(ordered_states[:FINAL_NEAR_WINDOW_COUNT])
    unique_vectors = {}
    source_windows = {}
    for state in candidate_states:
        vector = state.population[state.best_index()]
        key = full.vector_key(vector)
        unique_vectors.setdefault(key, vector.copy())
        source_windows.setdefault(key, []).append(state.start_s)

    best_decision = incumbent
    best_probe = baseline_probe
    strict_rows = []
    for key, vector in list(unique_vectors.items())[:STRICT_FINAL_LIMIT]:
        if time.perf_counter() >= deadline - 1.8:
            break
        candidate = full.decode_vector(vector, "full_horizon_window_candidate")
        probe = strict_summary(candidate, q5.PROBE)
        strict_rows.append({"vector_key": key, "source_window_starts_s": source_windows[key], **probe})
        if full.strict_better(probe, best_probe):
            best_decision, best_probe = candidate, probe

    best_screen = strict_summary(best_decision, q5.SCREEN)
    screen_verification = {
        "baseline": baseline_screen, "candidate": best_screen,
        "improvement_s": best_screen["longest_continuous_s"] - baseline_screen["longest_continuous_s"],
        "candidate_retains_improvement": best_screen["longest_continuous_s"] >= baseline_screen["longest_continuous_s"],
    }
    handoff = full.handoff_audit(best_decision, best_screen["longest_interval_s"])
    bins = []
    for left in np.arange(0., full.EARLIEST_ARRIVAL_S, 10.):
        rows = [row for row in records if left <= row["start_s"] < min(left + 10., full.EARLIEST_ARRIVAL_S)]
        if not rows:
            continue
        row = min(rows, key=lambda item: item["maximum_margin_m"])
        bins.append({"bin_s": f"[{left:.0f},{min(left + 10., full.EARLIEST_ARRIVAL_S):.3f})",
                     "best_maximum_margin_m": row["maximum_margin_m"], "best_start_s": row["start_s"]})

    elapsed = time.perf_counter() - started
    payload = {
        "schema_version": "1.0", "spec_id": SPEC_ID, "status": "pilot_complete",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "objective": "equal-budget feasibility search over every declared full-horizon window",
        "incumbent_source": incumbent_record,
        "baseline_strict_probe": baseline_probe,
        "best_strict_probe": best_probe,
        "screen_verification": screen_verification,
        "best_decision": q5.decision_record(best_decision),
        "handoff_audit": handoff,
        "horizon_coverage": {
            "horizon_start_s": 0., "horizon_end_s": full.EARLIEST_ARRIVAL_S,
            "window_duration_s": window_duration_s, "window_step_s": window_step_s,
            "window_count": len(states), "first_window_s": [states[0].start_s, states[0].end_s],
            "last_window_s": [states[-1].start_s, states[-1].end_s],
            "exact_right_endpoint_included": abs(states[-1].end_s - full.EARLIEST_ARRIVAL_S) <= 1e-12,
            "minimum_generations_per_window": min(state.generations for state in states),
            "maximum_generations_per_window": max(state.generations for state in states),
            "minimum_evaluations_per_window": min(state.evaluations for state in states),
            "maximum_evaluations_per_window": max(state.evaluations for state in states),
            "equal_generation_budget_pass": len({state.generations for state in states}) == 1,
            "equal_evaluation_budget_pass": len({state.evaluations for state in states}) == 1,
            "proxy_feasible_window_count": sum(row["proxy_feasible"] for row in records),
        },
        "window_records": records,
        "horizon_bins": bins,
        "strict_verification": {
            "unique_candidate_count": len(unique_vectors), "evaluated_candidate_count": len(strict_rows),
            "candidates": strict_rows,
        },
        "search": {
            "algorithm": "round-robin equal-budget per-window differential evolution",
            "random_seed": RNG_SEED, "population_size_per_window": POPULATION_SIZE,
            "complete_rounds": complete_rounds,
            "total_evaluation_count": sum(state.evaluations for state in states),
            "decision_dimension": full.VECTOR_SIZE,
            "proxy_surface_theta": PROXY_THETA, "proxy_surface_levels": PROXY_LEVELS,
            "proxy_time_step_s": PROXY_TIME_STEP_S,
            "heuristic_window_exclusion": False, "geometric_candidate_pruning_applied": False,
            "repetition_policy": "one fixed-seed working pilot",
            "variability_summary": "not estimated; no distributional or global-optimality claim",
        },
        "claims": {
            "full_declared_window_family_evaluated": True,
            "equal_budget_across_windows": True,
            "all_three_missiles_dynamic_cloud_quantifier": True,
            "strict_probe_verified": True, "screen_verified": True,
            "continuous_start_times_exhausted": False,
            "continuous_decision_domain_exhausted": False,
            "formal_q5_result": False, "global_optimality": False,
        },
        "input_hashes": {
            "data/A题.pdf": sha(OFFICIAL_PATH),
            "docs/q5_full_condition_search.json": sha(SEED_PATH),
            "planning/46_q5_full_horizon_window_spec.md": sha(SPEC_PATH),
            "src/q5/full_horizon_window_search.py": sha(Path(__file__)),
        },
        "software": {"python": platform.python_version(), "numpy": np.__version__},
        "elapsed_s": elapsed,
    }
    json_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(ready(payload), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(report_markdown(payload), encoding="utf-8")
    print(json.dumps(ready({
        "stage": "full_horizon_complete", "window_count": len(states),
        "complete_rounds": complete_rounds, "evaluations": sum(state.evaluations for state in states),
        "proxy_feasible_windows": payload["horizon_coverage"]["proxy_feasible_window_count"],
        "best_probe_s": best_probe["longest_continuous_s"],
        "best_screen_s": best_screen["longest_continuous_s"], "elapsed_s": elapsed,
    }), ensure_ascii=False), flush=True)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--wall-time-s", type=float, default=60.)
    parser.add_argument("--window-step-s", type=float, default=.5)
    parser.add_argument("--window-duration-s", type=float, default=8.)
    args = parser.parse_args()
    if args.wall_time_s <= FINAL_RESERVE_S + 3.:
        raise SystemExit("wall time too small for equal-budget search and strict finalisation")
    run(args.json, args.report, args.wall_time_s, args.window_step_s, args.window_duration_s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
