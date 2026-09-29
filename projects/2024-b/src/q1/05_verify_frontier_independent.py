"""独立重建S5有限闭合前沿下界；不导入主核心或主分支程序。"""

from __future__ import annotations

import argparse
import hashlib
import heapq
import json
import platform
import sys
import time
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = PROJECT_ROOT / "output/q1/s5_finite_closure.json"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/s6_frontier_verification.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s6_frontier_verification_manifest.json"
SCRIPT_PATH = Path(__file__).resolve()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def from_payload(payload: dict[str, object]) -> Fraction:
    return Fraction(int(payload["numerator"]), int(payload["denominator"]))


def payload(value: Fraction) -> dict[str, object]:
    with localcontext() as context:
        context.prec = 24
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": format(decimal_value, "f"),
    }


def boundary(n: int) -> tuple[int, int]:
    return n // 10, n // 10 + 1


def identity(n: int, scenario: str) -> tuple[int, int, Fraction]:
    d0, d1 = boundary(n)
    if scenario == "R":
        return d0, d1, Fraction(1, 20)
    return d1, d0, Fraction(1, 10)


def evaluate_actions(
    n: int,
    d: int,
    actions: dict[tuple[int, int], bool],
) -> tuple[Fraction, Fraction]:
    alive: dict[int, Fraction] = {0: Fraction(1)}
    stopped = Fraction(0)
    time_mass = Fraction(0)
    for t in range(n):
        following: dict[int, Fraction] = {}
        for x, mass in alive.items():
            if mass == 0:
                continue
            if 1 <= t < n and actions.get((t, x), False):
                stopped += mass
                time_mass += t * mass
                continue
            defect = Fraction(d - x, n - t)
            good = Fraction(n - d - t + x, n - t)
            if defect < 0 or good < 0 or defect + good != 1:
                raise AssertionError("独立前沿验证出现非法转移")
            following[x + 1] = following.get(x + 1, Fraction(0)) + mass * defect
            following[x] = following.get(x, Fraction(0)) + mass * good
        alive = following
    terminal = sum(alive.values(), Fraction(0))
    if stopped + terminal != 1:
        raise AssertionError("独立前沿验证质量不守恒")
    return stopped, time_mass + n * terminal


def actions_from_thresholds(
    n: int,
    scenario: str,
    thresholds: tuple[int, ...],
) -> dict[tuple[int, int], bool]:
    return {
        (t, x): x >= thresholds[t - 1] if scenario == "R" else x <= thresholds[t - 1]
        for t in range(1, n)
        for x in range(t + 1)
    }


def falling(value: int, length: int) -> int:
    if length > value:
        return 0
    answer = 1
    for offset in range(length):
        answer *= value - offset
    return answer


def likelihood(n: int, d: int, t: int, x: int) -> Fraction:
    return Fraction(
        (2**t) * falling(d, x) * falling(n - d, t - x),
        falling(n, t),
    )


def constrained_point(
    n: int,
    scenario: str,
    multiplier: Fraction,
    fixed: dict[int, int],
) -> tuple[Fraction, Fraction, Fraction]:
    null_d, target_d, limit = identity(n, scenario)
    values = {x: n * likelihood(n, target_d, n, x) for x in range(n + 1)}
    actions: dict[tuple[int, int], bool] = {}
    for t in range(n - 1, 0, -1):
        prior: dict[int, Fraction] = {}
        for x in range(t + 1):
            stop_cost = t * likelihood(n, target_d, t, x) + multiplier * likelihood(
                n,
                null_d,
                t,
                x,
            )
            continue_cost = (values[x] + values[x + 1]) / 2
            if t in fixed:
                stop = x >= fixed[t] if scenario == "R" else x <= fixed[t]
            else:
                stop = stop_cost < continue_cost
            actions[(t, x)] = stop
            prior[x] = stop_cost if stop else continue_cost
        values = prior
    risk, asn = evaluate_actions(n, null_d, actions)[0], evaluate_actions(
        n,
        target_d,
        actions,
    )[1]
    dual = (values[0] + values[1]) / 2 - multiplier * limit
    return risk, asn, dual


def dual_bound(
    n: int,
    scenario: str,
    fixed: dict[int, int],
    iterations: int,
) -> tuple[Fraction, int]:
    _, _, limit = identity(n, scenario)
    points: dict[Fraction, tuple[Fraction, Fraction, Fraction]] = {}

    def point(multiplier: Fraction) -> tuple[Fraction, Fraction, Fraction]:
        if multiplier not in points:
            points[multiplier] = constrained_point(n, scenario, multiplier, fixed)
        return points[multiplier]

    low_multiplier = Fraction(0)
    low = point(low_multiplier)
    if low[0] > limit:
        high_multiplier = Fraction(1)
        high = point(high_multiplier)
        while high[0] > limit:
            low_multiplier, low = high_multiplier, high
            high_multiplier *= 2
            high = point(high_multiplier)
        for _ in range(iterations):
            middle_multiplier = (low_multiplier + high_multiplier) / 2
            middle = point(middle_multiplier)
            if middle[0] > limit:
                low_multiplier, low = middle_multiplier, middle
            else:
                high_multiplier, high = middle_multiplier, middle
        risk_difference = low[0] - high[0]
        if risk_difference > 0:
            intersection = Fraction(high[1] - low[1], risk_difference)
            if low_multiplier <= intersection <= high_multiplier:
                point(intersection)
    return max(item[2] for item in points.values()), len(points)


def domains(n: int, scenario: str, t: int) -> tuple[int, ...]:
    d0, d1 = boundary(n)
    if scenario == "R":
        values = list(range(min(t, d1) + 1))
        if t + 1 not in values:
            values.append(t + 1)
        return tuple(values)
    return tuple([-1, *range(max(0, t - (n - d0)), min(t, d1) + 1)])


def continuing_completion(
    n: int,
    scenario: str,
    fixed: dict[int, int],
) -> tuple[int, ...]:
    return tuple(
        fixed.get(t, t + 1 if scenario == "R" else -1)
        for t in range(1, n)
    )


def verify_reported_bound(
    n: int,
    scenario: str,
    thresholds: tuple[int, ...],
    known_wide_bound: Fraction,
    target_bound: Fraction,
    node_limit: int,
    time_limit_seconds: float,
    dual_iterations: int,
) -> dict[str, object]:
    null_d, target_d, limit = identity(n, scenario)
    incumbent_actions = actions_from_thresholds(n, scenario, thresholds)
    incumbent_risk, incumbent_asn = evaluate_actions(n, null_d, incumbent_actions)[0], evaluate_actions(
        n,
        target_d,
        incumbent_actions,
    )[1]
    if incumbent_risk > limit or not known_wide_bound <= target_bound <= incumbent_asn:
        raise AssertionError("待验证界的基本顺序错误")
    order = tuple(
        sorted(
            range(1, n),
            key=lambda t: (
                thresholds[t - 1] == (t + 1 if scenario == "R" else -1),
                t,
            ),
        )
    )
    frontier: list[tuple[Fraction, int, int, tuple[tuple[int, int], ...]]] = []
    nodes = 0
    risk_prunes = 0
    bound_prunes = 0
    leaves = 0
    dual_points = 0
    counter = 0
    started = time.monotonic()

    def register(items: tuple[tuple[int, int], ...]) -> None:
        nonlocal nodes, risk_prunes, bound_prunes, leaves, dual_points, counter
        fixed = dict(items)
        completion = continuing_completion(n, scenario, fixed)
        actions = actions_from_thresholds(n, scenario, completion)
        risk, objective = evaluate_actions(n, null_d, actions)[0], evaluate_actions(
            n,
            target_d,
            actions,
        )[1]
        nodes += 1
        if risk > limit:
            risk_prunes += 1
            return
        if len(items) == n - 1:
            leaves += 1
            if objective < target_bound:
                raise AssertionError("独立分支验证发现低于报告下界的可行反例")
            return
        lower, point_count = dual_bound(n, scenario, fixed, dual_iterations)
        dual_points += point_count
        lower = max(lower, known_wide_bound)
        if lower >= target_bound:
            bound_prunes += 1
            return
        counter += 1
        heapq.heappush(frontier, (lower, -len(items), counter, items))

    register(tuple())
    stop_reason = "target_bound_verified"
    while frontier:
        if nodes >= node_limit:
            stop_reason = "node_limit"
            break
        if time.monotonic() - started >= time_limit_seconds:
            stop_reason = "time_limit"
            break
        _, _, _, items = heapq.heappop(frontier)
        fixed = dict(items)
        t = next(value for value in order if value not in fixed)
        preferred = thresholds[t - 1]
        child_values = (preferred, *[value for value in domains(n, scenario, t) if value != preferred])
        for threshold in child_values:
            register(tuple(sorted((*items, (t, threshold)))))
    verified = not frontier
    achieved_bound = target_bound if verified else min(frontier[0][0], target_bound)
    return {
        "status": "independently_verified" if verified else "resource_limited_not_verified",
        "stop_reason": stop_reason,
        "reported_bound": payload(target_bound),
        "independently_achieved_bound": payload(achieved_bound),
        "nodes_evaluated": nodes,
        "risk_prunes": risk_prunes,
        "bound_prunes": bound_prunes,
        "leaves": leaves,
        "dual_points": dual_points,
        "frontier_nodes": len(frontier),
        "elapsed_seconds": time.monotonic() - started,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="S6独立重建有限闭合前沿下界")
    parser.add_argument("--node-limit", type=int, default=5000)
    parser.add_argument("--time-limit-seconds", type=float, default=35.0)
    parser.add_argument("--dual-iterations", type=int, default=20)
    args = parser.parse_args()
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    source = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, object]] = []
    all_verified = True
    for record in source["results"]:
        n = int(record["N"])
        if n not in {23, 50}:
            continue
        scenarios: dict[str, object] = {}
        for scenario in ("R", "A"):
            item = record["scenarios"][scenario]
            thresholds = tuple(int(row["threshold"]) for row in item["thresholds"])
            result = verify_reported_bound(
                n,
                scenario,
                thresholds,
                from_payload(item["input_wide_class_lower_bound"]),
                from_payload(item["deterministic_threshold_lower_bound"]),
                args.node_limit,
                args.time_limit_seconds,
                args.dual_iterations,
            )
            scenarios[scenario] = result
            all_verified = all_verified and result["status"] == "independently_verified"
        results.append({"N": n, "scenarios": scenarios})
    output = {
        "schema_version": "1.0",
        "artifact_status": "s6_frontier_verification",
        "claim_status": "all_reported_frontier_bounds_independently_verified" if all_verified else "some_reported_frontier_bounds_not_verified",
        "producer": "src/q1/05_verify_frontier_independent.py",
        "independence_contract": {
            "imports_main_core_or_brancher": False,
            "verification_target": "prove each reported lower bound or return a weaker achieved bound",
        },
        "resource_contract": {
            "node_limit_per_case": args.node_limit,
            "time_limit_seconds_per_case": args.time_limit_seconds,
            "dual_iterations": args.dual_iterations,
        },
        "results": results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s6_frontier_verification_run_identity",
        "producer": "src/q1/05_verify_frontier_independent.py",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT)), *sys.argv[1:]],
        "environment": {"python": sys.version, "platform": platform.platform()},
        "inputs": {str(INPUT_PATH.relative_to(PROJECT_ROOT)): sha256(INPUT_PATH)},
        "sources": {str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH)},
        "outputs": {str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH)},
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"all_verified": all_verified, "output": str(OUTPUT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
