"""问题一完整动作空间序贯方案的精确数学核心。

输入：运行时批量 N、情景标识 R/A、确定性统计阈值（R 为上阈值 r_t，A 为下阈值
a_t）和拉格朗日乘子。零风险事实动作（事实拒收 x>=D1、事实接收 x+(N-t)<=D0）在
两个情景中始终生效，不进入统计错误预算。
输出：精确停止/接收/拒收概率、ASN、全 D 曲线、Bellman 候选和有效对偶下界。
职责：逐式实现已批准的 S4 合同（2026-08-25_q1_s4_complete_action_specification.md），
不负责写文件、选择题面未给的业务批量或作最终声明。
"""

from __future__ import annotations

import heapq
import time
from dataclasses import dataclass
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Iterable, Mapping, Sequence

SCENARIOS = {"R", "A"}
ACTION_CONTINUE = 0
ACTION_ACCEPT = 1
ACTION_REJECT = 2


@dataclass(frozen=True)
class Evaluation:
    """一个固定策略在一个真实 D 下的精确程序级表现。

    stop_probability 是任意提前停止（接收或拒收）的概率；accept_probability 与
    reject_probability 分别只统计接收型与拒收型提前停止，供分情景风险约束使用。
    """

    stop_probability: Fraction
    accept_probability: Fraction
    reject_probability: Fraction
    asn: Fraction
    terminal_probability: Fraction


@dataclass(frozen=True)
class BellmanPoint:
    """一个拉格朗日乘子对应的宽类 Bellman 策略与下界。"""

    multiplier: Fraction
    actions: Mapping[tuple[int, int], int]
    null_stop_probability: Fraction
    target_asn: Fraction
    dual_lower_bound: Fraction
    thresholds: tuple[int, ...] | None


@dataclass(frozen=True)
class ThresholdClosureResult:
    """有限资源分支定界对确定性阈值类给出的证书。"""

    thresholds: tuple[int, ...]
    risk: Fraction
    asn_upper_bound: Fraction
    threshold_class_lower_bound: Fraction
    certified_gap: Fraction
    status: str
    stop_reason: str
    nodes_evaluated: int
    nodes_expanded: int
    nodes_pruned_by_risk: int
    nodes_pruned_by_bound: int
    leaves_evaluated: int
    feasible_completions_evaluated: int
    incumbent_updates: int
    dual_points_evaluated: int
    frontier_nodes: int
    elapsed_seconds: float


def validate_n(n: int) -> None:
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("N 必须是正整数")


def boundary_counts(n: int) -> tuple[int, int]:
    """把标称率 10% 映射为有限总体相邻整数边界。"""

    validate_n(n)
    d0 = n // 10
    return d0, d0 + 1


def factual_reject_at(t: int, x: int, d1: int) -> bool:
    """已见次品数超过 D0 时整批必超标，事实拒收。"""

    return x >= d1


def factual_accept_at(t: int, x: int, n: int, d0: int) -> bool:
    """剩余全部为次品也不超标时整批必合格，事实接收。"""

    return x + (n - t) <= d0


def falling(value: int, length: int) -> int:
    """下降阶乘；超出有限总体可行域时返回 0。"""

    if length < 0 or length > value:
        return 0
    result = 1
    for offset in range(length):
        result *= value - offset
    return result


def likelihood_under_fair_reference(n: int, d: int, t: int, x: int) -> Fraction:
    """有序前缀相对于公平二元参考分布 Q 的精确似然密度。"""

    validate_n(n)
    if not (0 <= d <= n and 0 <= t <= n and 0 <= x <= t):
        return Fraction(0)
    denominator = falling(n, t)
    numerator = (2**t) * falling(d, x) * falling(n - d, t - x)
    return Fraction(numerator, denominator)


def validate_thresholds(n: int, scenario: str, thresholds: Sequence[int]) -> None:
    """校验新规范阈值域：R 上阈值、A 下阈值，均排除与事实边界重复的编码。"""

    validate_n(n)
    if scenario not in SCENARIOS:
        raise ValueError("scenario 必须为 R 或 A")
    if len(thresholds) != n - 1:
        raise ValueError("阈值序列长度必须为 N-1")
    d0, _ = boundary_counts(n)
    for t, threshold in enumerate(thresholds, start=1):
        if scenario == "R":
            if threshold != t + 1 and not (0 <= threshold <= min(t, d0)):
                raise ValueError(f"R 情景 t={t} 的阈值 {threshold} 越出规范域")
        else:
            if threshold != -1 and not (
                max(0, t - (n - d0) + 1) <= threshold <= min(t, d0)
            ):
                raise ValueError(f"A 情景 t={t} 的阈值 {threshold} 越出规范域")


def actions_from_thresholds(
    n: int,
    scenario: str,
    thresholds: Sequence[int],
) -> dict[tuple[int, int], int]:
    """由统计阈值与始终生效的事实动作生成三值状态动作表。

    动作值：0=继续，1=接收，2=拒收。事实接收/事实拒收优先于统计阈值；两方向事实
    条件互斥，统计阈值域与事实边界不重叠，因此每状态动作唯一。
    """

    validate_thresholds(n, scenario, thresholds)
    d0, d1 = boundary_counts(n)
    actions: dict[tuple[int, int], int] = {}
    for t in range(1, n):
        threshold = thresholds[t - 1]
        for x in range(t + 1):
            if factual_accept_at(t, x, n, d0):
                actions[(t, x)] = ACTION_ACCEPT
            elif factual_reject_at(t, x, d1):
                actions[(t, x)] = ACTION_REJECT
            elif scenario == "R":
                actions[(t, x)] = (
                    ACTION_REJECT if x >= threshold else ACTION_CONTINUE
                )
            else:
                actions[(t, x)] = (
                    ACTION_ACCEPT if x <= threshold else ACTION_CONTINUE
                )
    return actions


def evaluate_action_policy(
    n: int,
    d: int,
    actions: Mapping[tuple[int, int], int],
) -> Evaluation:
    """按 S4 前向递推精确评价任意当前计数状态三值动作。"""

    validate_n(n)
    if not 0 <= d <= n:
        raise ValueError("D 必须位于 0,...,N")
    alive: dict[int, Fraction] = {0: Fraction(1)}
    stopped = Fraction(0)
    accepted = Fraction(0)
    rejected = Fraction(0)
    early_asn = Fraction(0)
    for t in range(n):
        next_alive: dict[int, Fraction] = {}
        for x, mass in alive.items():
            if mass == 0:
                continue
            action = int(actions.get((t, x), ACTION_CONTINUE)) if 1 <= t < n else ACTION_CONTINUE
            if action != ACTION_CONTINUE:
                stopped += mass
                early_asn += t * mass
                if action == ACTION_ACCEPT:
                    accepted += mass
                elif action == ACTION_REJECT:
                    rejected += mass
                else:
                    raise AssertionError("非法动作值")
                continue
            defect_probability = Fraction(d - x, n - t)
            good_probability = Fraction(n - d - t + x, n - t)
            if defect_probability < 0 or good_probability < 0:
                raise AssertionError("不可达状态获得了正概率质量")
            if defect_probability + good_probability != 1:
                raise AssertionError("一步转移概率不守恒")
            next_alive[x + 1] = next_alive.get(x + 1, Fraction(0)) + mass * defect_probability
            next_alive[x] = next_alive.get(x, Fraction(0)) + mass * good_probability
        alive = next_alive
    terminal = sum(alive.values(), Fraction(0))
    if stopped + terminal != 1:
        raise AssertionError("早停质量与终点质量不守恒")
    return Evaluation(stopped, accepted, rejected, early_asn + n * terminal, terminal)


def evaluate_threshold_policy(
    n: int,
    d: int,
    scenario: str,
    thresholds: Sequence[int],
) -> Evaluation:
    return evaluate_action_policy(
        n, d, actions_from_thresholds(n, scenario, thresholds)
    )


def full_curve(n: int, scenario: str, thresholds: Sequence[int]) -> list[Evaluation]:
    return [evaluate_threshold_policy(n, d, scenario, thresholds) for d in range(n + 1)]


def factual_only_thresholds(n: int, scenario: str) -> tuple[int, ...]:
    """零风险基线：统计动作关闭（R 的 r_t=t+1、A 的 a_t=-1），只保留事实停止。"""

    validate_n(n)
    if scenario == "R":
        return tuple(t + 1 for t in range(1, n))
    if scenario == "A":
        return tuple(-1 for t in range(1, n))
    raise ValueError("scenario 必须为 R 或 A")


def thresholds_from_actions(
    n: int,
    scenario: str,
    actions: Mapping[tuple[int, int], int],
) -> tuple[int, ...] | None:
    """仅当状态动作满足 S4 的阈值形状（事实动作恒生效）时返回阈值序列。"""

    d0, d1 = boundary_counts(n)
    thresholds: list[int] = []
    for t in range(1, n):
        row: dict[int, int] = {}
        for x in range(t + 1):
            row[x] = int(actions.get((t, x), ACTION_CONTINUE))
        factual_accept_max = d0 - (n - t)
        undecided = [x for x in range(t + 1) if not (
            factual_accept_at(t, x, n, d0) or factual_reject_at(t, x, d1)
        )]
        for x in range(t + 1):
            expected = ACTION_CONTINUE
            if factual_accept_at(t, x, n, d0):
                expected = ACTION_ACCEPT
            elif factual_reject_at(t, x, d1):
                expected = ACTION_REJECT
            if row[x] != expected:
                return None
        if not undecided:
            thresholds.append(t + 1 if scenario == "R" else -1)
            continue
        if scenario == "R":
            rejecters = [x for x in undecided if row[x] == ACTION_REJECT]
            if not rejecters:
                thresholds.append(t + 1)
            else:
                first = min(rejecters)
                if any(x < first and row[x] != ACTION_CONTINUE for x in undecided):
                    return None
                if any(x > first and row[x] != ACTION_REJECT for x in undecided):
                    return None
                thresholds.append(first)
        else:
            accepters = [x for x in undecided if row[x] == ACTION_ACCEPT]
            if not accepters:
                thresholds.append(-1)
            else:
                last = max(accepters)
                if any(x > last and row[x] != ACTION_CONTINUE for x in undecided):
                    return None
                if any(x < last and row[x] != ACTION_ACCEPT for x in undecided):
                    return None
                thresholds.append(last)
    return tuple(thresholds)


def action_vector(n: int, scenario: str, thresholds: Sequence[int]) -> tuple[int, ...]:
    actions = actions_from_thresholds(n, scenario, thresholds)
    return tuple(
        int(actions[(t, x)]) for t in range(1, n) for x in range(t + 1)
    )


def _scenario_identity(n: int, scenario: str) -> tuple[int, int, Fraction]:
    d0, d1 = boundary_counts(n)
    if scenario == "R":
        return d0, d1, Fraction(1, 20)
    if scenario == "A":
        return d1, d0, Fraction(1, 10)
    raise ValueError("scenario 必须为 R 或 A")


def lagrangian_bellman_point(n: int, scenario: str, multiplier: Fraction) -> BellmanPoint:
    """计算一个乘子下的宽类最优三值动作和确定有效的对偶下界。

    放宽只作用于未决状态：事实状态必须停止，方向事实动作计入风险惩罚，反方向事实
    动作只计停止时间；未决状态可选择方向动作或继续。这保留了拉格朗日下界的有效性，
    同时不把"任意提前接收"作为逃逸方向。
    """

    validate_n(n)
    if scenario not in SCENARIOS:
        raise ValueError("scenario 必须为 R 或 A")
    if multiplier < 0:
        raise ValueError("拉格朗日乘子必须非负")
    null_d, target_d, _ = _scenario_identity(n, scenario)
    d0, d1 = boundary_counts(n)

    values = {
        x: n * likelihood_under_fair_reference(n, target_d, n, x)
        for x in range(n + 1)
    }
    actions: dict[tuple[int, int], int] = {}
    for t in range(n - 1, 0, -1):
        next_values: dict[int, Fraction] = {}
        for x in range(t + 1):
            target_likelihood = likelihood_under_fair_reference(n, target_d, t, x)
            null_likelihood = likelihood_under_fair_reference(n, null_d, t, x)
            continue_cost = (values[x] + values[x + 1]) / 2
            if factual_accept_at(t, x, n, d0):
                cost = t * target_likelihood
                action = ACTION_ACCEPT
            elif factual_reject_at(t, x, d1):
                if scenario == "R":
                    cost = t * target_likelihood + multiplier * null_likelihood
                else:
                    cost = t * target_likelihood
                action = ACTION_REJECT
            elif scenario == "R":
                reject_cost = t * target_likelihood + multiplier * null_likelihood
                if reject_cost < continue_cost:
                    cost, action = reject_cost, ACTION_REJECT
                else:
                    cost, action = continue_cost, ACTION_CONTINUE
            else:
                accept_cost = t * target_likelihood + multiplier * null_likelihood
                if accept_cost < continue_cost:
                    cost, action = accept_cost, ACTION_ACCEPT
                else:
                    cost, action = continue_cost, ACTION_CONTINUE
            actions[(t, x)] = action
            next_values[x] = cost
        values = next_values

    root_value = (values[0] + values[1]) / 2 if n >= 1 else Fraction(0)
    delta = Fraction(1, 20) if scenario == "R" else Fraction(1, 10)
    dual_lower_bound = root_value - multiplier * delta
    null_evaluation = evaluate_action_policy(n, null_d, actions)
    target_evaluation = evaluate_action_policy(n, target_d, actions)
    return BellmanPoint(
        multiplier=multiplier,
        actions=actions,
        null_stop_probability=(
            null_evaluation.reject_probability
            if scenario == "R"
            else null_evaluation.accept_probability
        ),
        target_asn=target_evaluation.asn,
        dual_lower_bound=dual_lower_bound,
        thresholds=thresholds_from_actions(n, scenario, actions),
    )


def constrained_lagrangian_bellman_point(
    n: int,
    scenario: str,
    multiplier: Fraction,
    fixed_thresholds: Mapping[int, int],
) -> BellmanPoint:
    """固定部分时点阈值，其余状态放宽后计算节点的有效拉格朗日下界。

    一个已固定时点必须统一采用该行阈值；未固定时点允许每个未决状态独立选择方向
    动作或继续（事实状态仍强制停止）。后者扩大了所有合法阈值补全的集合，所以递推
    值仍是该分支的严格下界。
    """

    validate_n(n)
    if scenario not in SCENARIOS:
        raise ValueError("scenario 必须为 R 或 A")
    if multiplier < 0:
        raise ValueError("拉格朗日乘子必须非负")
    for t, threshold in fixed_thresholds.items():
        if not 1 <= t < n:
            raise ValueError("固定阈值时点必须位于 1,...,N-1")
    # 用真实 N 的完整补全校验每个固定阈值：D0 依赖 N，前缀长度不能改变规范域。
    validate_thresholds(
        n,
        scenario,
        tuple(
            int(fixed_thresholds.get(row_t, _all_continue_threshold(row_t, scenario)))
            for row_t in range(1, n)
        ),
    )

    null_d, target_d, _ = _scenario_identity(n, scenario)
    d0, d1 = boundary_counts(n)

    values = {
        x: n * likelihood_under_fair_reference(n, target_d, n, x)
        for x in range(n + 1)
    }
    actions: dict[tuple[int, int], int] = {}
    for t in range(n - 1, 0, -1):
        next_values: dict[int, Fraction] = {}
        fixed_threshold = fixed_thresholds.get(t)
        for x in range(t + 1):
            target_likelihood = likelihood_under_fair_reference(n, target_d, t, x)
            null_likelihood = likelihood_under_fair_reference(n, null_d, t, x)
            continue_cost = (values[x] + values[x + 1]) / 2
            if factual_accept_at(t, x, n, d0):
                cost = t * target_likelihood
                action = ACTION_ACCEPT
            elif factual_reject_at(t, x, d1):
                if scenario == "R":
                    cost = t * target_likelihood + multiplier * null_likelihood
                else:
                    cost = t * target_likelihood
                action = ACTION_REJECT
            elif fixed_threshold is not None:
                if scenario == "R":
                    if x >= fixed_threshold:
                        cost = t * target_likelihood + multiplier * null_likelihood
                        action = ACTION_REJECT
                    else:
                        cost, action = continue_cost, ACTION_CONTINUE
                else:
                    if x <= fixed_threshold:
                        cost = t * target_likelihood + multiplier * null_likelihood
                        action = ACTION_ACCEPT
                    else:
                        cost, action = continue_cost, ACTION_CONTINUE
            elif scenario == "R":
                reject_cost = t * target_likelihood + multiplier * null_likelihood
                if reject_cost < continue_cost:
                    cost, action = reject_cost, ACTION_REJECT
                else:
                    cost, action = continue_cost, ACTION_CONTINUE
            else:
                accept_cost = t * target_likelihood + multiplier * null_likelihood
                if accept_cost < continue_cost:
                    cost, action = accept_cost, ACTION_ACCEPT
                else:
                    cost, action = continue_cost, ACTION_CONTINUE
            actions[(t, x)] = action
            next_values[x] = cost
        values = next_values

    root_value = (values[0] + values[1]) / 2
    delta = Fraction(1, 20) if scenario == "R" else Fraction(1, 10)
    null_evaluation = evaluate_action_policy(n, null_d, actions)
    target_evaluation = evaluate_action_policy(n, target_d, actions)
    return BellmanPoint(
        multiplier=multiplier,
        actions=actions,
        null_stop_probability=(
            null_evaluation.reject_probability
            if scenario == "R"
            else null_evaluation.accept_probability
        ),
        target_asn=target_evaluation.asn,
        dual_lower_bound=root_value - multiplier * delta,
        thresholds=thresholds_from_actions(n, scenario, actions),
    )


def canonical_threshold_domain(n: int, scenario: str, t: int) -> tuple[int, ...]:
    """返回 S4 第 3 节规范阈值域（含"无额外统计动作"哨兵）。

    域设计为与事实边界不相交：R 的 r_t<=min(t,D0)<D1；A 的下界 max(0,t-(N-D0)+1)
    保证 a_t 不再覆盖事实接收已必然停止的状态。
    """

    validate_n(n)
    if not 1 <= t < n:
        raise ValueError("t 必须位于 1,...,N-1")
    d0, _ = boundary_counts(n)
    if scenario == "R":
        active_maximum = min(t, d0)
        values = list(range(active_maximum + 1))
        disabled = t + 1
        if disabled not in values:
            values.append(disabled)
        return tuple(values)
    if scenario == "A":
        reachable_minimum = max(0, t - (n - d0) + 1)
        reachable_maximum = min(t, d0)
        return tuple([-1, *range(reachable_minimum, reachable_maximum + 1)])
    raise ValueError("scenario 必须为 R 或 A")


def _all_continue_threshold(t: int, scenario: str) -> int:
    return t + 1 if scenario == "R" else -1


def _complete_with_continuation(
    n: int,
    scenario: str,
    fixed_thresholds: Mapping[int, int],
) -> tuple[int, ...]:
    return tuple(
        int(fixed_thresholds.get(t, _all_continue_threshold(t, scenario)))
        for t in range(1, n)
    )


def constrained_dual_search(
    n: int,
    scenario: str,
    fixed_thresholds: Mapping[int, int],
    bisection_iterations: int = 20,
) -> tuple[Fraction, Fraction, int]:
    """为一个分支返回有效下界、最佳乘子和实际评价点数。"""

    if bisection_iterations < 1:
        raise ValueError("节点对偶二分次数必须为正整数")
    _, _, delta = _scenario_identity(n, scenario)
    points: dict[Fraction, BellmanPoint] = {}

    def evaluate(multiplier: Fraction) -> BellmanPoint:
        if multiplier not in points:
            points[multiplier] = constrained_lagrangian_bellman_point(
                n,
                scenario,
                multiplier,
                fixed_thresholds,
            )
        return points[multiplier]

    low_multiplier = Fraction(0)
    low_point = evaluate(low_multiplier)
    if low_point.null_stop_probability > delta:
        high_multiplier = Fraction(1)
        high_point = evaluate(high_multiplier)
        while high_point.null_stop_probability > delta:
            low_multiplier, low_point = high_multiplier, high_point
            high_multiplier *= 2
            if high_multiplier.numerator.bit_length() > 512:
                raise RuntimeError("节点对偶搜索未能找到风险不超限的放宽策略")
            high_point = evaluate(high_multiplier)
        for _ in range(bisection_iterations):
            middle_multiplier = (low_multiplier + high_multiplier) / 2
            middle_point = evaluate(middle_multiplier)
            if middle_point.null_stop_probability > delta:
                low_multiplier, low_point = middle_multiplier, middle_point
            else:
                high_multiplier, high_point = middle_multiplier, middle_point

        risk_difference = low_point.null_stop_probability - high_point.null_stop_probability
        if risk_difference > 0:
            intersection = Fraction(
                high_point.target_asn - low_point.target_asn,
                risk_difference,
            )
            if low_multiplier <= intersection <= high_multiplier:
                evaluate(intersection)

    best = max(points.values(), key=lambda point: point.dual_lower_bound)
    return best.dual_lower_bound, best.multiplier, len(points)


def finite_threshold_branch_and_bound(
    n: int,
    scenario: str,
    incumbent_thresholds: Sequence[int],
    node_limit: int,
    time_limit_seconds: float,
    dual_bisection_iterations: int = 20,
    known_global_lower_bound: Fraction | None = None,
) -> ThresholdClosureResult:
    """在有限节点与时间预算内闭合新规范确定性计数阈值类。"""

    validate_n(n)
    if scenario not in SCENARIOS:
        raise ValueError("scenario 必须为 R 或 A")
    if node_limit < 1:
        raise ValueError("node_limit 必须为正整数")
    if time_limit_seconds <= 0:
        raise ValueError("time_limit_seconds 必须为正数")
    validate_thresholds(n, scenario, incumbent_thresholds)
    null_d, target_d, delta = _scenario_identity(n, scenario)
    incumbent = tuple(int(value) for value in incumbent_thresholds)
    incumbent_evaluation = evaluate_threshold_policy(n, null_d, scenario, incumbent)
    incumbent_risk = (
        incumbent_evaluation.reject_probability
        if scenario == "R"
        else incumbent_evaluation.accept_probability
    )
    if incumbent_risk > delta:
        raise ValueError("分支定界初始候选必须满足风险约束")
    incumbent_asn = evaluate_threshold_policy(n, target_d, scenario, incumbent).asn
    incumbent_vector = action_vector(n, scenario, incumbent)
    if known_global_lower_bound is None:
        known_global_lower_bound = Fraction(0)
    if known_global_lower_bound > incumbent_asn:
        raise ValueError("已知全局下界不能超过初始可行上界")

    nodes_evaluated = 0
    nodes_expanded = 0
    nodes_pruned_by_risk = 0
    nodes_pruned_by_bound = 0
    leaves_evaluated = 0
    feasible_completions_evaluated = 0
    incumbent_updates = 0
    dual_points_evaluated = 0
    counter = 0
    started = time.monotonic()

    branch_order = tuple(
        sorted(
            range(1, n),
            key=lambda t: (
                incumbent[t - 1] == _all_continue_threshold(t, scenario),
                t,
            ),
        )
    )

    frontier: list[tuple[Fraction, int, int, tuple[tuple[int, int], ...]]] = []

    def lexicographically_minimal_completion(
        fixed: Mapping[int, int],
    ) -> tuple[int, ...]:
        return _complete_with_continuation(n, scenario, fixed)

    def bound_and_register(fixed_items: tuple[tuple[int, int], ...]) -> None:
        nonlocal counter, nodes_evaluated, nodes_pruned_by_risk
        nonlocal nodes_pruned_by_bound, feasible_completions_evaluated
        nonlocal incumbent, incumbent_risk, incumbent_asn, incumbent_vector
        nonlocal incumbent_updates, dual_points_evaluated
        fixed = dict(fixed_items)
        completion = lexicographically_minimal_completion(fixed)
        completion_evaluation = evaluate_threshold_policy(
            n,
            null_d,
            scenario,
            completion,
        )
        completion_risk = (
            completion_evaluation.reject_probability
            if scenario == "R"
            else completion_evaluation.accept_probability
        )
        nodes_evaluated += 1
        if completion_risk > delta:
            nodes_pruned_by_risk += 1
            return
        completion_asn = evaluate_threshold_policy(
            n,
            target_d,
            scenario,
            completion,
        ).asn
        completion_vector = action_vector(n, scenario, completion)
        feasible_completions_evaluated += 1
        if (completion_asn, completion_vector) < (incumbent_asn, incumbent_vector):
            incumbent = completion
            incumbent_risk = completion_risk
            incumbent_asn = completion_asn
            incumbent_vector = completion_vector
            incumbent_updates += 1

        lower_bound, _, point_count = constrained_dual_search(
            n,
            scenario,
            fixed,
            bisection_iterations=dual_bisection_iterations,
        )
        lower_bound = max(lower_bound, known_global_lower_bound)
        dual_points_evaluated += point_count
        if lower_bound > incumbent_asn:
            nodes_pruned_by_bound += 1
            return
        if lower_bound == incumbent_asn:
            minimum_vector = action_vector(n, scenario, completion)
            if minimum_vector >= incumbent_vector:
                nodes_pruned_by_bound += 1
                return
        counter += 1
        heapq.heappush(frontier, (lower_bound, -len(fixed_items), counter, fixed_items))

    bound_and_register(tuple())
    stop_reason = "frontier_exhausted"
    while frontier:
        elapsed = time.monotonic() - started
        if elapsed >= time_limit_seconds:
            stop_reason = "time_limit"
            break
        lower_bound, negative_depth, _, fixed_items = frontier[0]
        fixed = dict(fixed_items)
        if lower_bound > incumbent_asn:
            heapq.heappop(frontier)
            nodes_pruned_by_bound += 1
            continue
        if lower_bound == incumbent_asn:
            completion = lexicographically_minimal_completion(fixed)
            if action_vector(n, scenario, completion) >= incumbent_vector:
                heapq.heappop(frontier)
                nodes_pruned_by_bound += 1
                continue
        unassigned = next((t for t in branch_order if t not in fixed), None)
        if unassigned is None:
            heapq.heappop(frontier)
            leaves_evaluated += 1
            continue
        domain = canonical_threshold_domain(n, scenario, unassigned)
        if nodes_evaluated + len(domain) > node_limit:
            stop_reason = "node_limit"
            break

        heapq.heappop(frontier)
        nodes_expanded += 1
        preferred = incumbent[unassigned - 1]
        child_values = (preferred, *[value for value in domain if value != preferred])
        for threshold in child_values:
            child = tuple(sorted((*fixed_items, (unassigned, threshold))))
            bound_and_register(child)

    elapsed_seconds = time.monotonic() - started
    if frontier:
        threshold_lower_bound = min(frontier[0][0], incumbent_asn)
        status = "resource_limited_valid_gap"
    else:
        threshold_lower_bound = incumbent_asn
        status = "proved_deterministic_threshold_optimal"
        stop_reason = "frontier_exhausted"
    return ThresholdClosureResult(
        thresholds=incumbent,
        risk=incumbent_risk,
        asn_upper_bound=incumbent_asn,
        threshold_class_lower_bound=threshold_lower_bound,
        certified_gap=incumbent_asn - threshold_lower_bound,
        status=status,
        stop_reason=stop_reason,
        nodes_evaluated=nodes_evaluated,
        nodes_expanded=nodes_expanded,
        nodes_pruned_by_risk=nodes_pruned_by_risk,
        nodes_pruned_by_bound=nodes_pruned_by_bound,
        leaves_evaluated=leaves_evaluated,
        feasible_completions_evaluated=feasible_completions_evaluated,
        incumbent_updates=incumbent_updates,
        dual_points_evaluated=dual_points_evaluated,
        frontier_nodes=len(frontier),
        elapsed_seconds=elapsed_seconds,
    )


def coordinate_improve_thresholds(
    n: int,
    scenario: str,
    initial_thresholds: Sequence[int],
    max_sweeps: int = 12,
) -> tuple[tuple[int, ...], int, int]:
    """在风险硬约束内做确定性阈值坐标改进，只负责收紧可行上界。"""

    null_d, target_d, delta = _scenario_identity(n, scenario)
    current = tuple(int(value) for value in initial_thresholds)
    validate_thresholds(n, scenario, current)
    cache: dict[tuple[int, ...], tuple[Fraction, Fraction, tuple[int, ...]]] = {}

    def metrics(thresholds: tuple[int, ...]) -> tuple[Fraction, Fraction, tuple[int, ...]]:
        if thresholds not in cache:
            evaluation = evaluate_threshold_policy(n, null_d, scenario, thresholds)
            risk = (
                evaluation.reject_probability
                if scenario == "R"
                else evaluation.accept_probability
            )
            asn = evaluate_threshold_policy(n, target_d, scenario, thresholds).asn
            cache[thresholds] = (risk, asn, action_vector(n, scenario, thresholds))
        return cache[thresholds]

    if metrics(current)[0] > delta:
        raise ValueError("坐标改进的初始策略必须可行")
    sweeps = 0
    evaluations = 0
    for _ in range(max_sweeps):
        sweeps += 1
        best = current
        _, best_asn, best_vector = metrics(best)
        for t in range(1, n):
            domain = canonical_threshold_domain(n, scenario, t)
            for threshold in domain:
                if threshold == current[t - 1]:
                    continue
                trial_list = list(current)
                trial_list[t - 1] = threshold
                trial = tuple(trial_list)
                risk, asn, vector = metrics(trial)
                evaluations += 1
                if risk <= delta and (asn, vector) < (best_asn, best_vector):
                    best = trial
                    best_asn = asn
                    best_vector = vector
        if best == current:
            break
        current = best
    return current, sweeps, evaluations


def solve_with_dual_search(
    n: int,
    scenario: str,
    baseline_thresholds: Mapping[str, Sequence[int]],
    bisection_iterations: int = 48,
) -> dict[str, object]:
    """用基线可行上界和精确 Bellman 乘子搜索形成 S5 候选与有效间隙。"""

    validate_n(n)
    null_d, target_d, delta = _scenario_identity(n, scenario)
    candidates: dict[tuple[int, ...], set[str]] = {}
    for name, raw_thresholds in baseline_thresholds.items():
        thresholds = tuple(int(value) for value in raw_thresholds)
        validate_thresholds(n, scenario, thresholds)
        candidates.setdefault(thresholds, set()).add(name)

    points: list[BellmanPoint] = []
    nonthreshold_points = 0

    def register(point: BellmanPoint) -> Fraction:
        nonlocal nonthreshold_points
        points.append(point)
        if point.thresholds is None:
            nonthreshold_points += 1
        elif point.null_stop_probability <= delta:
            candidates.setdefault(point.thresholds, set()).add("bellman_multiplier")
        return point.null_stop_probability

    zero_point = lagrangian_bellman_point(n, scenario, Fraction(0))
    zero_risk = register(zero_point)
    if zero_risk > delta:
        low = Fraction(0)
        high = Fraction(1)
        high_point = lagrangian_bellman_point(n, scenario, high)
        while register(high_point) > delta:
            low = high
            high *= 2
            if high.numerator.bit_length() > 512:
                raise RuntimeError("未能在有限乘子范围找到可行 Bellman 策略")
            high_point = lagrangian_bellman_point(n, scenario, high)
        for _ in range(bisection_iterations):
            middle = (low + high) / 2
            middle_point = lagrangian_bellman_point(n, scenario, middle)
            if register(middle_point) > delta:
                low = middle
            else:
                high = middle

    coordinate_sweeps = 0
    coordinate_evaluations = 0
    for initial, initial_sources in list(candidates.items()):
        initial_evaluation = evaluate_threshold_policy(n, null_d, scenario, initial)
        initial_risk = (
            initial_evaluation.reject_probability
            if scenario == "R"
            else initial_evaluation.accept_probability
        )
        if initial_risk > delta:
            continue
        improved, sweeps, evaluations = coordinate_improve_thresholds(
            n,
            scenario,
            initial,
        )
        coordinate_sweeps += sweeps
        coordinate_evaluations += evaluations
        if improved != initial:
            source_label = "coordinate_descent_from_" + "+".join(sorted(initial_sources))
            candidates.setdefault(improved, set()).add(source_label)

    evaluated_candidates: list[dict[str, object]] = []
    for thresholds, sources in candidates.items():
        null_evaluation = evaluate_threshold_policy(n, null_d, scenario, thresholds)
        null_risk = (
            null_evaluation.reject_probability
            if scenario == "R"
            else null_evaluation.accept_probability
        )
        target_evaluation = evaluate_threshold_policy(n, target_d, scenario, thresholds)
        if null_risk > delta:
            continue
        evaluated_candidates.append(
            {
                "thresholds": thresholds,
                "sources": tuple(sorted(sources)),
                "risk": null_risk,
                "asn": target_evaluation.asn,
                "action_vector": action_vector(n, scenario, thresholds),
            }
        )
    if not evaluated_candidates:
        raise AssertionError("至少一个批准基线应当可行")
    selected = min(
        evaluated_candidates,
        key=lambda item: (item["asn"], item["action_vector"]),
    )
    dual_point = max(points, key=lambda point: point.dual_lower_bound)
    upper_bound = selected["asn"]
    lower_bound = dual_point.dual_lower_bound
    if lower_bound > upper_bound:
        raise AssertionError("有效下界超过可行上界，Bellman或评价实现有误")
    gap = upper_bound - lower_bound
    return {
        "scenario": scenario,
        "null_d": null_d,
        "target_d": target_d,
        "risk_limit": delta,
        "selected_thresholds": selected["thresholds"],
        "selected_sources": selected["sources"],
        "risk": selected["risk"],
        "asn_upper_bound": upper_bound,
        "dual_lower_bound": lower_bound,
        "certified_gap": gap,
        "certificate_status": (
            "proved_against_wide_class" if gap == 0 else "valid_gap_only"
        ),
        "best_multiplier": dual_point.multiplier,
        "bellman_points_evaluated": len(points),
        "nonthreshold_bellman_points": nonthreshold_points,
        "feasible_threshold_candidates": len(evaluated_candidates),
        "coordinate_sweeps": coordinate_sweeps,
        "coordinate_evaluations": coordinate_evaluations,
    }


def fraction_payload(value: Fraction, decimal_digits: int = 24) -> dict[str, object]:
    """同时保存精确分数和只用于阅读的十进制近似。"""

    with localcontext() as context:
        context.prec = decimal_digits
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": format(decimal_value, "f"),
    }


def assert_scenario_metrics(
    n: int,
    scenario: str,
    thresholds: Sequence[int],
) -> None:
    """S5 同源自检：事实边界行为、风险/目标最坏点与概率守恒。不替代 S6。"""

    validate_thresholds(n, scenario, thresholds)
    d0, d1 = boundary_counts(n)
    null_d, target_d, delta = _scenario_identity(n, scenario)
    curve = full_curve(n, scenario, thresholds)

    for d, evaluation in enumerate(curve):
        if evaluation.stop_probability + evaluation.terminal_probability != 1:
            raise AssertionError(f"D={d} 停止与终点质量不守恒")
        if evaluation.accept_probability + evaluation.reject_probability != evaluation.stop_probability:
            raise AssertionError(f"D={d} 接收与拒收质量不等于总停止质量")

    # 反方向事实动作在对面总体不可达；方向统计动作才是被约束的风险项。
    if scenario == "R":
        # R 无统计接收：D>=D1 侧接收概率必须恒为 0（事实接收不可达）。
        for d in range(d1, n + 1):
            if curve[d].accept_probability != 0:
                raise AssertionError(f"D={d}>=D1 出现了提前接收概率")
        reject_curve = [item.reject_probability for item in curve]
        # D<=D0 侧拒收只含统计拒收（事实拒收不可达），随 D 不减，最坏点在 D0。
        for d in range(d0):
            if reject_curve[d] > reject_curve[d + 1]:
                raise AssertionError("R 情景 D<=D0 侧拒收概率应随 D 不减")
        risk = reject_curve[d0]
        if risk > delta:
            raise AssertionError("R 情景边界风险超过 1/20")
        asn_curve = [item.asn for item in curve]
        for d in range(d1, n):
            if asn_curve[d] < asn_curve[d + 1]:
                raise AssertionError("R 情景目标侧 ASN 最坏点应为 D1")
        target_asn = asn_curve[d1]
    else:
        # A 无统计拒收：D<=D0 侧拒收概率必须恒为 0（事实拒收不可达）。
        for d in range(d0 + 1):
            if curve[d].reject_probability != 0:
                raise AssertionError(f"D={d}<=D0 出现了提前拒收概率")
        accept_curve = [item.accept_probability for item in curve]
        # D>=D1 侧接收含统计接收（事实接收不可达），随 D 不减? -> 不增，最坏点在 D1。
        for d in range(d1, n):
            if accept_curve[d] < accept_curve[d + 1]:
                raise AssertionError("A 情景 D>=D1 侧接收概率应随 D 不增")
        risk = accept_curve[d1]
        if risk > delta:
            raise AssertionError("A 情景边界风险超过 1/10")
        asn_curve = [item.asn for item in curve]
        for d in range(d0):
            if asn_curve[d] > asn_curve[d + 1]:
                raise AssertionError("A 情景目标侧 ASN 最坏点应为 D0")
        target_asn = asn_curve[d0]
    return risk, target_asn
