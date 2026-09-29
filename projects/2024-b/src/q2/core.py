"""问题二精确固定方案状态递推核心。

输入：由 ``01_solve.py`` 从已批准S2表1接口解析的六个参数情景。
输出：不直接写文件；返回16种固定方案的可行性、精确事件期望、成本和利润。
职责：严格实现S4规格中的质量状态、首步期望方程、硬可行性门和闭式回归路径。
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from typing import Iterable


F = Fraction
EMPTY, GOOD, BAD = "E", "G", "B"
INITIAL_STATE = (EMPTY, EMPTY)
COUNT_NAMES = (
    "part1_purchases",
    "part2_purchases",
    "part1_inspections",
    "part2_inspections",
    "assemblies",
    "product_inspections",
    "disassemblies",
    "market_bad_products_and_exchanges",
)


@dataclass(frozen=True)
class Scenario:
    scenario_id: int
    part1_defect_rate: F
    part1_purchase_cost: F
    part1_inspection_cost: F
    part2_defect_rate: F
    part2_purchase_cost: F
    part2_inspection_cost: F
    product_defect_rate: F
    assembly_cost: F
    product_inspection_cost: F
    sale_price: F
    exchange_loss: F
    disassembly_cost: F


@dataclass(frozen=True)
class Policy:
    inspect_part1: int
    inspect_part2: int
    inspect_product: int
    disassemble_bad_product: int

    @property
    def bits(self) -> tuple[int, int, int, int]:
        return (
            self.inspect_part1,
            self.inspect_part2,
            self.inspect_product,
            self.disassemble_bad_product,
        )

    @property
    def policy_id(self) -> str:
        return "".join(str(value) for value in self.bits)


def all_policies() -> list[Policy]:
    """从四个二元决策机械生成全部16种方案，不使用可行白名单。"""
    return [Policy(*bits) for bits in product((0, 1), repeat=4)]


def _zero_counts() -> list[F]:
    return [F(0) for _ in COUNT_NAMES]


def _add_counts(left: Iterable[F], right: Iterable[F]) -> list[F]:
    return [a + b for a, b in zip(left, right)]


def _prepare_one(
    quality: str,
    inspect: int,
    defect_rate: F,
    purchase_index: int,
    inspection_index: int,
) -> list[tuple[str, F, list[F]]]:
    """执行一个槽位的补购/保留和固定检测，返回质量、概率与条件期望计数。"""
    good_rate = 1 - defect_rate
    if not inspect:
        if quality == EMPTY:
            counts = _zero_counts()
            counts[purchase_index] = F(1)
            return [
                (GOOD, good_rate, counts.copy()),
                (BAD, defect_rate, counts.copy()),
            ]
        return [(quality, F(1), _zero_counts())]

    counts = _zero_counts()
    if quality == EMPTY:
        counts[purchase_index] = 1 / good_rate
        counts[inspection_index] = 1 / good_rate
    elif quality == GOOD:
        counts[inspection_index] = F(1)
    elif quality == BAD:
        counts[purchase_index] = 1 / good_rate
        counts[inspection_index] = 1 + 1 / good_rate
    else:
        raise ValueError(f"非法零件质量状态: {quality}")
    return [(GOOD, F(1), counts)]


def preparation_kernel(
    state: tuple[str, str], policy: Policy, scenario: Scenario
) -> list[tuple[tuple[str, str], F, list[F]]]:
    """组合两槽位准备动作；主模型中新购零件质量独立。"""
    rows: list[tuple[tuple[str, str], F, list[F]]] = []
    part1 = _prepare_one(
        state[0], policy.inspect_part1, scenario.part1_defect_rate, 0, 2
    )
    part2 = _prepare_one(
        state[1], policy.inspect_part2, scenario.part2_defect_rate, 1, 3
    )
    for quality1, probability1, counts1 in part1:
        for quality2, probability2, counts2 in part2:
            rows.append(
                (
                    (quality1, quality2),
                    probability1 * probability2,
                    _add_counts(counts1, counts2),
                )
            )
    return rows


def product_success_probability(
    prepared_quality: tuple[str, str], scenario: Scenario
) -> F:
    if prepared_quality == (GOOD, GOOD):
        return 1 - scenario.product_defect_rate
    return F(0)


def transition_rows(
    state: tuple[str, str], policy: Policy, scenario: Scenario
) -> list[tuple[F, tuple[str, str] | None, list[F], bool]]:
    """返回一轮的概率、下一状态、事件计数和是否吸收；成功分支下一状态为None。"""
    rows = []
    for quality, prep_probability, prep_counts in preparation_kernel(
        state, policy, scenario
    ):
        success_probability = product_success_probability(quality, scenario)
        common = prep_counts.copy()
        common[4] += 1
        common[5] += policy.inspect_product

        rows.append((prep_probability * success_probability, None, common, True))

        fail_counts = common.copy()
        fail_counts[6] += policy.disassemble_bad_product
        fail_counts[7] += 1 - policy.inspect_product
        next_state = quality if policy.disassemble_bad_product else INITIAL_STATE
        rows.append(
            (
                prep_probability * (1 - success_probability),
                next_state,
                fail_counts,
                False,
            )
        )
    return rows


def reachable_states(policy: Policy, scenario: Scenario) -> list[tuple[str, str]]:
    seen = {INITIAL_STATE}
    pending = [INITIAL_STATE]
    while pending:
        state = pending.pop()
        for probability, next_state, _, absorbed in transition_rows(
            state, policy, scenario
        ):
            if probability and not absorbed and next_state not in seen:
                seen.add(next_state)
                pending.append(next_state)
    return sorted(seen)


def feasibility_gate(policy: Policy, scenario: Scenario) -> dict[str, object]:
    """用S4结构证明判门，并给出从初始状态最终吸收的精确概率。"""
    if not policy.disassemble_bad_product:
        return {
            "feasible": True,
            "absorption_probability": F(1),
            "reason": "bad_product_discard_resets_to_empty_state",
        }
    if policy.inspect_part1 and policy.inspect_part2:
        return {
            "feasible": True,
            "absorption_probability": F(1),
            "reason": "both_parts_screened_and_assembly_success_probability_positive",
        }

    absorption = F(1)
    if not policy.inspect_part1:
        absorption *= 1 - scenario.part1_defect_rate
    if not policy.inspect_part2:
        absorption *= 1 - scenario.part2_defect_rate
    return {
        "feasible": False,
        "absorption_probability": absorption,
        "reason": "reachable_persistent_bad_part_closed_class",
    }


def _solve_linear_system(matrix: list[list[F]], rhs: list[F]) -> list[F]:
    """以Fraction高斯消元求有限状态线性方程，不使用浮点容差或伪逆。"""
    n = len(rhs)
    augmented = [matrix[i][:] + [rhs[i]] for i in range(n)]
    for column in range(n):
        pivot = next(
            (row for row in range(column, n) if augmented[row][column]), None
        )
        if pivot is None:
            raise ValueError("暂态方程奇异，方案不得产生有限期望")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(n):
            if row == column or not augmented[row][column]:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                value - factor * base
                for value, base in zip(augmented[row], augmented[column])
            ]
    return [row[-1] for row in augmented]


def exact_state_expectations(
    policy: Policy, scenario: Scenario
) -> tuple[list[F], F, list[tuple[str, str]]]:
    """按 ``V=a+QV`` 求事件期望，并单独求订单至少一次市场坏品的概率。"""
    gate = feasibility_gate(policy, scenario)
    if not gate["feasible"]:
        raise ValueError("不可行方案没有有限事件期望")

    states = reachable_states(policy, scenario)
    index = {state: position for position, state in enumerate(states)}
    n = len(states)
    transition = [[F(0) for _ in range(n)] for _ in range(n)]
    immediate = [[F(0) for _ in COUNT_NAMES] for _ in range(n)]
    h_immediate = [F(0) for _ in range(n)]

    for state in states:
        row_index = index[state]
        for probability, next_state, counts, absorbed in transition_rows(
            state, policy, scenario
        ):
            for count_index, count in enumerate(counts):
                immediate[row_index][count_index] += probability * count
            if not absorbed:
                transition[row_index][index[next_state]] += probability
                if not policy.inspect_product:
                    h_immediate[row_index] += probability
            # 事件计数对全部失败分支递推；H在首次市场坏品处停止递推。

    identity_minus_transition = [
        [F(int(i == j)) - transition[i][j] for j in range(n)] for i in range(n)
    ]
    start = index[INITIAL_STATE]
    expected_counts = []
    for count_index in range(len(COUNT_NAMES)):
        column = _solve_linear_system(
            [row[:] for row in identity_minus_transition],
            [immediate[i][count_index] for i in range(n)],
        )
        expected_counts.append(column[start])

    # H需要独立的转移矩阵：市场坏品发生后不再追踪“至少一次”事件。
    h_transition = [[F(0) for _ in range(n)] for _ in range(n)]
    for state in states:
        i = index[state]
        for probability, next_state, _, absorbed in transition_rows(state, policy, scenario):
            if not absorbed and policy.inspect_product:
                h_transition[i][index[next_state]] += probability
    h_matrix = [
        [F(int(i == j)) - h_transition[i][j] for j in range(n)] for i in range(n)
    ]
    h_values = _solve_linear_system(h_matrix, h_immediate)
    return expected_counts, h_values[start], states


def closed_form_expectations(policy: Policy, scenario: Scenario) -> tuple[list[F], F]:
    """按S4证明的两类可行结构独立写出闭式计数，作为S5内部回归。"""
    gate = feasibility_gate(policy, scenario)
    if not gate["feasible"]:
        raise ValueError("不可行方案没有闭式有限期望")

    g1 = 1 - scenario.part1_defect_rate
    g2 = 1 - scenario.part2_defect_rate
    g0 = 1 - scenario.product_defect_rate
    counts = _zero_counts()

    if not policy.disassemble_bad_product:
        part1_good = F(1) if policy.inspect_part1 else g1
        part2_good = F(1) if policy.inspect_part2 else g2
        success = part1_good * part2_good * g0
        attempts = 1 / success
        counts[0] = (1 / g1 if policy.inspect_part1 else F(1)) * attempts
        counts[1] = (1 / g2 if policy.inspect_part2 else F(1)) * attempts
        counts[2] = (1 / g1 if policy.inspect_part1 else F(0)) * attempts
        counts[3] = (1 / g2 if policy.inspect_part2 else F(0)) * attempts
        counts[4] = attempts
        counts[5] = policy.inspect_product * attempts
        counts[6] = F(0)
        counts[7] = (1 - policy.inspect_product) * (1 - success) / success
        any_market_bad = (1 - policy.inspect_product) * (1 - success)
        return counts, any_market_bad

    # 通过拆解门的方案必然检测两类零件；首轮筛选后仅重复复检和装配。
    failures = scenario.product_defect_rate / g0
    counts[0] = 1 / g1
    counts[1] = 1 / g2
    counts[2] = 1 / g1 + failures
    counts[3] = 1 / g2 + failures
    counts[4] = 1 / g0
    counts[5] = policy.inspect_product / g0
    counts[6] = failures
    counts[7] = (1 - policy.inspect_product) * failures
    any_market_bad = (1 - policy.inspect_product) * scenario.product_defect_rate
    return counts, any_market_bad


def expected_cost(counts: list[F], scenario: Scenario) -> F:
    weights = (
        scenario.part1_purchase_cost,
        scenario.part2_purchase_cost,
        scenario.part1_inspection_cost,
        scenario.part2_inspection_cost,
        scenario.assembly_cost,
        scenario.product_inspection_cost,
        scenario.disassembly_cost,
        scenario.exchange_loss,
    )
    return sum((weight * count for weight, count in zip(weights, counts)), F(0))


def solve_policy(policy: Policy, scenario: Scenario) -> dict[str, object]:
    gate = feasibility_gate(policy, scenario)
    result: dict[str, object] = {
        "policy": policy,
        "feasible": gate["feasible"],
        "feasibility_reason": gate["reason"],
        "absorption_probability": gate["absorption_probability"],
    }
    if not gate["feasible"]:
        result["profit_identity"] = "not_defined_due_to_nontermination"
        return result

    counts, any_market_bad, states = exact_state_expectations(policy, scenario)
    closed_counts, closed_h = closed_form_expectations(policy, scenario)
    if counts != closed_counts or any_market_bad != closed_h:
        raise AssertionError(f"状态方程与闭式回归不一致: 情景{scenario.scenario_id}, {policy.policy_id}")
    cost = expected_cost(counts, scenario)
    result.update(
        {
            "reachable_states": states,
            "expected_counts": dict(zip(COUNT_NAMES, counts)),
            "probability_order_has_market_bad_product": any_market_bad,
            "expected_cost": cost,
            "expected_profit": scenario.sale_price - cost,
            "profit_identity": "finite_expected_profit_per_completed_order",
        }
    )
    return result
