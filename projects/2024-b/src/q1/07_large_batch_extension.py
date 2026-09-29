"""求解问题一的大批量可行阈值候选，并对最终候选作精确有理数评价。

大批量路径不再执行原S5的逐坐标穷举改进。它先用float64 Bellman松弛搜索方向动作，
再逐行投影到S4允许的确定性计数阈值，最后用Fraction前向递推精确核对风险和平均检测
件数。输出只声称“满足风险约束的可行候选”，不声称全局最优。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
import time
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy.special import gammaln


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = Path(__file__).resolve()
CORE_PATH = PROJECT_ROOT / "src/q1/core.py"
SPEC_PATH = PROJECT_ROOT / "planning/analysis/2026-08-25_q1_s4_complete_action_specification.md"
RESULT_PATH = PROJECT_ROOT / "output/q1/s5_large_batch_extension.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s5_large_batch_extension_manifest.json"

ACTION_CONTINUE = 0
ACTION_ACCEPT = 1
ACTION_REJECT = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fraction_payload(value: Fraction, digits: int = 24) -> dict[str, object]:
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": format(float(value), f".{digits}g"),
    }


def parse_n_values(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    if not values or any(value < 10 for value in values):
        raise ValueError("大批量扩展N列表必须由不小于10的正整数组成")
    return values


def boundary_counts(n: int) -> tuple[int, int]:
    return n // 10, n // 10 + 1


def factual_accept_mask(n: int, d0: int, t: int, x: np.ndarray) -> np.ndarray:
    return x + (n - t) <= d0


def factual_reject_mask(d1: int, x: np.ndarray) -> np.ndarray:
    return x >= d1


def likelihood_rows(n: int, d: int) -> list[np.ndarray]:
    """返回每个(t,x)有序前缀相对于公平二元参考分布的似然密度。"""

    rows: list[np.ndarray] = []
    log_two = math.log(2.0)
    log_d_fact = float(gammaln(d + 1))
    log_g_fact = float(gammaln(n - d + 1))
    log_n_fact = float(gammaln(n + 1))
    for t in range(n + 1):
        x = np.arange(t + 1, dtype=np.int64)
        good = t - x
        valid = (x <= d) & (good <= n - d)
        row = np.zeros(t + 1, dtype=np.float64)
        xv = x[valid]
        gv = good[valid]
        log_values = (
            t * log_two
            + log_d_fact
            - gammaln(d - xv + 1)
            + log_g_fact
            - gammaln(n - d - gv + 1)
            - log_n_fact
            + gammaln(n - t + 1)
        )
        row[valid] = np.exp(log_values)
        rows.append(row)
    return rows


def evaluate_actions_float(
    n: int,
    d: int,
    actions: list[np.ndarray | None],
) -> tuple[float, float, float, float]:
    alive = np.array([1.0], dtype=np.float64)
    accepted = 0.0
    rejected = 0.0
    early_asn = 0.0
    for t in range(n):
        if 1 <= t < n:
            row_actions = actions[t]
            if row_actions is None:
                raise AssertionError("动作表缺少中间时刻")
            stop = row_actions != ACTION_CONTINUE
            if np.any(stop):
                stopped_mass = alive[stop]
                early_asn += t * float(stopped_mass.sum())
                accepted += float(alive[row_actions == ACTION_ACCEPT].sum())
                rejected += float(alive[row_actions == ACTION_REJECT].sum())
                alive = alive.copy()
                alive[stop] = 0.0
        x = np.arange(t + 1, dtype=np.float64)
        defect_probability = np.clip((d - x) / (n - t), 0.0, 1.0)
        next_alive = np.zeros(t + 2, dtype=np.float64)
        next_alive[1:] += alive * defect_probability
        next_alive[:-1] += alive * (1.0 - defect_probability)
        alive = next_alive
    terminal = float(alive.sum())
    asn = early_asn + n * terminal
    total = accepted + rejected + terminal
    if abs(total - 1.0) > 5e-10:
        raise AssertionError(f"float动作评价质量不守恒: {total}")
    return accepted, rejected, asn, terminal


def bellman_actions_float(
    n: int,
    scenario: str,
    multiplier: float,
    null_rows: list[np.ndarray],
    target_rows: list[np.ndarray],
) -> list[np.ndarray | None]:
    d0, d1 = boundary_counts(n)
    values = n * target_rows[n]
    actions: list[np.ndarray | None] = [None] * (n + 1)
    for t in range(n - 1, 0, -1):
        x = np.arange(t + 1, dtype=np.int64)
        target = target_rows[t]
        null = null_rows[t]
        continuation = (values[:-1] + values[1:]) / 2.0
        cost = continuation.copy()
        row_actions = np.zeros(t + 1, dtype=np.int8)
        fact_accept = factual_accept_mask(n, d0, t, x)
        fact_reject = factual_reject_mask(d1, x)
        undecided = ~(fact_accept | fact_reject)

        cost[fact_accept] = t * target[fact_accept]
        row_actions[fact_accept] = ACTION_ACCEPT
        if scenario == "R":
            reject_cost = t * target + multiplier * null
            cost[fact_reject] = reject_cost[fact_reject]
            row_actions[fact_reject] = ACTION_REJECT
            choose = undecided & (reject_cost < continuation)
            cost[choose] = reject_cost[choose]
            row_actions[choose] = ACTION_REJECT
        else:
            cost[fact_reject] = t * target[fact_reject]
            row_actions[fact_reject] = ACTION_REJECT
            accept_cost = t * target + multiplier * null
            choose = undecided & (accept_cost < continuation)
            cost[choose] = accept_cost[choose]
            row_actions[choose] = ACTION_ACCEPT

        actions[t] = row_actions
        values = cost
    return actions


def project_actions_to_thresholds(
    n: int,
    scenario: str,
    actions: list[np.ndarray | None],
) -> tuple[int, ...]:
    d0, d1 = boundary_counts(n)
    thresholds: list[int] = []
    for t in range(1, n):
        row_actions = actions[t]
        if row_actions is None:
            raise AssertionError("动作表缺少投影时刻")
        x = np.arange(t + 1, dtype=np.int64)
        undecided = ~(factual_accept_mask(n, d0, t, x) | factual_reject_mask(d1, x))
        if scenario == "R":
            active = x[undecided & (row_actions == ACTION_REJECT)]
            thresholds.append(int(active.min()) if active.size else t + 1)
        else:
            active = x[undecided & (row_actions == ACTION_ACCEPT)]
            thresholds.append(int(active.max()) if active.size else -1)
    return tuple(thresholds)


def evaluate_threshold_float(
    n: int,
    d: int,
    scenario: str,
    thresholds: tuple[int, ...],
) -> tuple[float, float, float, float]:
    d0, d1 = boundary_counts(n)
    actions: list[np.ndarray | None] = [None] * (n + 1)
    for t in range(1, n):
        x = np.arange(t + 1, dtype=np.int64)
        fact_accept = factual_accept_mask(n, d0, t, x)
        fact_reject = factual_reject_mask(d1, x)
        row = np.zeros(t + 1, dtype=np.int8)
        row[fact_accept] = ACTION_ACCEPT
        row[fact_reject] = ACTION_REJECT
        undecided = ~(fact_accept | fact_reject)
        if scenario == "R":
            row[undecided & (x >= thresholds[t - 1])] = ACTION_REJECT
        else:
            row[undecided & (x <= thresholds[t - 1])] = ACTION_ACCEPT
        actions[t] = row
    return evaluate_actions_float(n, d, actions)


def exact_threshold_evaluation(
    n: int,
    d: int,
    scenario: str,
    thresholds: tuple[int, ...],
) -> dict[str, Fraction]:
    """不构造完整动作字典的精确Fraction前向递推。"""

    d0, d1 = boundary_counts(n)
    alive: dict[int, Fraction] = {0: Fraction(1)}
    accepted = Fraction(0)
    rejected = Fraction(0)
    early_asn = Fraction(0)
    for t in range(n):
        next_alive: dict[int, Fraction] = {}
        for x, mass in alive.items():
            if mass == 0:
                continue
            action = ACTION_CONTINUE
            if 1 <= t < n:
                if x + (n - t) <= d0:
                    action = ACTION_ACCEPT
                elif x >= d1:
                    action = ACTION_REJECT
                elif scenario == "R" and x >= thresholds[t - 1]:
                    action = ACTION_REJECT
                elif scenario == "A" and x <= thresholds[t - 1]:
                    action = ACTION_ACCEPT
            if action != ACTION_CONTINUE:
                early_asn += t * mass
                if action == ACTION_ACCEPT:
                    accepted += mass
                else:
                    rejected += mass
                continue
            defect = Fraction(d - x, n - t)
            good = Fraction(n - d - t + x, n - t)
            if defect:
                next_alive[x + 1] = next_alive.get(x + 1, Fraction(0)) + mass * defect
            if good:
                next_alive[x] = next_alive.get(x, Fraction(0)) + mass * good
        alive = next_alive
    terminal = sum(alive.values(), Fraction(0))
    if accepted + rejected + terminal != 1:
        raise AssertionError("精确候选评价质量不守恒")
    return {
        "accepted": accepted,
        "rejected": rejected,
        "asn": early_asn + n * terminal,
        "terminal": terminal,
    }


def solve_scenario(n: int, scenario: str, iterations: int) -> dict[str, object]:
    d0, d1 = boundary_counts(n)
    if scenario == "R":
        null_d, target_d, risk_limit = d0, d1, Fraction(1, 20)
    else:
        null_d, target_d, risk_limit = d1, d0, Fraction(1, 10)

    null_rows = likelihood_rows(n, null_d)
    target_rows = likelihood_rows(n, target_d)

    def point(multiplier: float) -> tuple[list[np.ndarray | None], float]:
        actions = bellman_actions_float(n, scenario, multiplier, null_rows, target_rows)
        accepted, rejected, _, _ = evaluate_actions_float(n, null_d, actions)
        return actions, rejected if scenario == "R" else accepted

    delta = float(risk_limit)
    low = 0.0
    high = 1.0
    high_actions, high_risk = point(high)
    while high_risk > delta:
        low = high
        high *= 2.0
        if high > 2.0**60:
            raise RuntimeError("float Bellman乘子搜索未找到风险可行点")
        high_actions, high_risk = point(high)

    bellman_points: list[tuple[float, list[np.ndarray | None], float]] = [
        (high, high_actions, high_risk)
    ]
    for _ in range(iterations):
        middle = (low + high) / 2.0
        actions, risk = point(middle)
        bellman_points.append((middle, actions, risk))
        if risk > delta:
            low = middle
        else:
            high = middle

    candidates: dict[tuple[int, ...], dict[str, float]] = {}
    factual = tuple(t + 1 for t in range(1, n)) if scenario == "R" else tuple(-1 for _ in range(1, n))
    projected = [factual]
    projected.extend(project_actions_to_thresholds(n, scenario, actions) for _, actions, _ in bellman_points)
    for thresholds in projected:
        if thresholds in candidates:
            continue
        accepted, rejected, asn, terminal = evaluate_threshold_float(n, null_d, scenario, thresholds)
        risk = rejected if scenario == "R" else accepted
        if risk <= delta - 1e-12:
            _, _, target_asn, _ = evaluate_threshold_float(n, target_d, scenario, thresholds)
            candidates[thresholds] = {
                "risk": risk,
                "target_asn": target_asn,
                "null_terminal": terminal,
            }
    if not candidates:
        raise AssertionError("至少应保留零风险事实停止基线")

    selected_thresholds, float_metrics = min(
        candidates.items(),
        key=lambda item: (item[1]["target_asn"], item[0]),
    )
    exact_null = exact_threshold_evaluation(n, null_d, scenario, selected_thresholds)
    exact_target = exact_threshold_evaluation(n, target_d, scenario, selected_thresholds)
    exact_risk = exact_null["rejected"] if scenario == "R" else exact_null["accepted"]
    if exact_risk > risk_limit:
        raise AssertionError("float筛选的最终阈值在精确评价中超过风险上限")
    if abs(float(exact_risk) - float_metrics["risk"]) > 2e-10:
        raise AssertionError("float与精确风险评价不一致")
    if abs(float(exact_target["asn"]) - float_metrics["target_asn"]) > 2e-8 * n:
        raise AssertionError("float与精确平均检测件数不一致")

    return {
        "scenario": scenario,
        "null_boundary_D": null_d,
        "target_boundary_D": target_d,
        "risk_limit": fraction_payload(risk_limit),
        "risk_at_composite_worst_point": fraction_payload(exact_risk),
        "worst_target_ASN_upper_bound": fraction_payload(exact_target["asn"]),
        "average_inspection_ratio": fraction_payload(exact_target["asn"] / n),
        "thresholds": [
            {"t": t, "threshold": threshold}
            for t, threshold in enumerate(selected_thresholds, start=1)
        ],
        "candidate_count": len(candidates),
        "search_identity": {
            "method": "float64_lagrangian_bellman_rowwise_threshold_projection_then_exact_fraction_evaluation",
            "bisection_iterations": iterations,
            "bellman_points": len(bellman_points),
            "float_exact_risk_absolute_difference": abs(float(exact_risk) - float_metrics["risk"]),
            "float_exact_asn_absolute_difference": abs(float(exact_target["asn"]) - float_metrics["target_asn"]),
        },
        "optimization_status": "feasible_deterministic_threshold_candidate_not_global_optimality_claim",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="问题一大批量可行阈值候选扩展")
    parser.add_argument("--n-list", default="100,200,500,1000")
    parser.add_argument("--bisection-iterations", type=int, default=24)
    args = parser.parse_args()
    n_values = parse_n_values(args.n_list)
    if args.bisection_iterations < 8:
        raise ValueError("Bellman二分次数不得少于8")

    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    monotonic_start = time.monotonic()
    results = []
    for n in n_values:
        case_start = time.monotonic()
        scenarios = {
            scenario: solve_scenario(n, scenario, args.bisection_iterations)
            for scenario in ("R", "A")
        }
        results.append(
            {
                "N": n,
                "D0": n // 10,
                "D1": n // 10 + 1,
                "elapsed_seconds": time.monotonic() - case_start,
                "scenarios": scenarios,
            }
        )

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "artifact_status": "s5_unverified_large_batch_extension",
        "producer": "src/q1/07_large_batch_extension.py",
        "consumers": [
            "src/q1/08_verify_large_batch_extension.py",
            "src/figures/build_explanatory_figures.py",
            "docs/q1/solution_brief.md",
        ],
        "input_identity": {
            "n_values": list(n_values),
            "p0": "1/10",
            "specification_path": str(SPEC_PATH.relative_to(PROJECT_ROOT)),
            "specification_sha256": sha256(SPEC_PATH),
        },
        "arithmetic": {
            "candidate_search": "numpy.float64",
            "final_risk_and_ASN": "fractions.Fraction exact rational arithmetic",
            "random_seed": None,
        },
        "results": results,
        "claim_boundary": [
            "all reported candidates satisfy the exact scenario risk limit",
            "large-batch candidates are feasible deterministic threshold rules, not global optimality claims",
            "N values are representative model fixtures rather than enterprise observations",
        ],
    }
    RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s5_run_identity",
        "producer": "src/q1/07_large_batch_extension.py",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "elapsed_seconds": time.monotonic() - monotonic_start,
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT)), *sys.argv[1:]],
        "environment": {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__, "random_seed": None},
        "parameters": {"n_values": list(n_values), "bisection_iterations": args.bisection_iterations},
        "inputs": {
            str(SPEC_PATH.relative_to(PROJECT_ROOT)): sha256(SPEC_PATH),
            str(CORE_PATH.relative_to(PROJECT_ROOT)): sha256(CORE_PATH),
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
        },
        "outputs": {str(RESULT_PATH.relative_to(PROJECT_ROOT)): sha256(RESULT_PATH)},
        "claim_boundary": "S5 large-batch feasible candidates; independent verification is a separate artifact",
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "result": str(RESULT_PATH), "N_values": list(n_values), "elapsed_seconds": manifest["elapsed_seconds"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
