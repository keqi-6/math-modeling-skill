"""问题三精确固定策略求解核。

本模块实现批准的 S4 合同。它利用树结构做严格的更新过程约化：半成品层保留
拆回子对象的真实质量，成品层在通过硬门后只有空前沿与三件已检合格半成品前沿。
所有概率与期望均使用 Fraction；约化只压缩已证明等价的几何循环。当前接口允许
12 个节点分别取不同次品率，以支持逐节点一因子敏感性检验。
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from pathlib import Path
import re
from typing import Iterable


F = Fraction
GOOD, BAD = "G", "B"

LEAVES = tuple(f"P{i}" for i in range(1, 9))
SEMIS = ("S1", "S2", "S3")
ASSEMBLIES = SEMIS + ("F",)
CHILDREN = {
    "S1": ("P1", "P2", "P3"),
    "S2": ("P4", "P5", "P6"),
    "S3": ("P7", "P8"),
    "F": SEMIS,
}

EVENT_NAMES = (
    *(f"purchase_{u}" for u in LEAVES),
    *(f"inspect_{v}" for v in LEAVES + ASSEMBLIES),
    *(f"assemble_{v}" for v in ASSEMBLIES),
    *(f"disassemble_{v}" for v in ASSEMBLIES),
    "root_attempts",
    "market_bad_products_and_exchanges",
    "atomic_steps",
)
EVENT_INDEX = {name: i for i, name in enumerate(EVENT_NAMES)}


@dataclass(frozen=True)
class Instance:
    defect_rates: dict[str, F]
    purchase_costs: dict[str, F]
    inspection_costs: dict[str, F]
    assembly_costs: dict[str, F]
    disassembly_costs: dict[str, F]
    sale_price: F
    exchange_loss: F


@dataclass(frozen=True)
class Policy:
    bits: tuple[int, ...]

    def __post_init__(self) -> None:
        if len(self.bits) != 16 or any(bit not in (0, 1) for bit in self.bits):
            raise ValueError("策略必须是规范位序的16个二元位")

    @property
    def policy_id(self) -> str:
        return "".join(map(str, self.bits))

    @property
    def leaf_inspections(self) -> dict[str, int]:
        return dict(zip(LEAVES, self.bits[:8]))

    @property
    def semi_inspections(self) -> dict[str, int]:
        return dict(zip(SEMIS, self.bits[8:11]))

    @property
    def inspect_final(self) -> int:
        return self.bits[11]

    @property
    def semi_disassemblies(self) -> dict[str, int]:
        return dict(zip(SEMIS, self.bits[12:15]))

    @property
    def disassemble_final(self) -> int:
        return self.bits[15]


@dataclass(frozen=True)
class RateScenario:
    name: str
    changed_node: str | None
    direction: str
    defect_rates: dict[str, F]

    def __post_init__(self) -> None:
        if set(self.defect_rates) != set(LEAVES + ASSEMBLIES) or any(
            not (0 <= rate < 1) for rate in self.defect_rates.values()
        ):
            raise ValueError("敏感性情形必须给出12个合法节点次品率")
        if self.direction not in {"nominal", "low", "high"}:
            raise ValueError("敏感性方向必须为 nominal、low 或 high")


@dataclass(frozen=True)
class LocalKernel:
    feasible: bool
    reason: str
    good_probability: F | None
    events_from_empty: tuple[F, ...] | None
    events_from_known_good: tuple[F, ...] | None


def load_instance_from_s2(path: Path | None = None) -> Instance:
    """直接解析S2批准的表2唯一字段接口，避免在S5另建参数副本。"""
    if path is None:
        path = Path(__file__).resolve().parents[2] / "planning" / "analysis" / "2026-08-24_q3_s2_assessment.md"
    text = path.read_text(encoding="utf-8")
    part_pattern = re.compile(
        r"^\|\s*([1-8])\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*$",
        re.MULTILINE,
    )
    assembly_pattern = re.compile(
        r"^\|\s*(半成品[123]|最终成品)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*$",
        re.MULTILINE,
    )
    parts = part_pattern.findall(text)
    assemblies = assembly_pattern.findall(text)
    if len(parts) != 8 or len(assemblies) != 4:
        raise ValueError(f"S2参数接口解析失败: parts={len(parts)}, assemblies={len(assemblies)}")

    name_map = {"半成品1": "S1", "半成品2": "S2", "半成品3": "S3", "最终成品": "F"}
    defect_rates: dict[str, F] = {}
    purchase_costs: dict[str, F] = {}
    inspection_costs: dict[str, F] = {}
    assembly_costs: dict[str, F] = {}
    disassembly_costs: dict[str, F] = {}
    for part_id, rate, purchase, inspection in parts:
        node = f"P{part_id}"
        defect_rates[node] = F(rate)
        purchase_costs[node] = F(purchase)
        inspection_costs[node] = F(inspection)
    for raw_name, rate, assembly, inspection, disassembly in assemblies:
        node = name_map[raw_name]
        defect_rates[node] = F(rate)
        assembly_costs[node] = F(assembly)
        inspection_costs[node] = F(inspection)
        disassembly_costs[node] = F(disassembly)

    market = re.search(
        r"market_price=([0-9.]+).*?exchange_loss=([0-9.]+)", text, re.DOTALL
    )
    if market is None:
        raise ValueError("S2接口缺少市场售价或调换损失")
    instance = Instance(
        defect_rates=defect_rates,
        purchase_costs=purchase_costs,
        inspection_costs=inspection_costs,
        assembly_costs=assembly_costs,
        disassembly_costs=disassembly_costs,
        sale_price=F(market.group(1)),
        exchange_loss=F(market.group(2)),
    )
    validate_instance(instance)
    return instance


def default_instance() -> Instance:
    """兼容调用名；其唯一数据源仍是S2冻结接口。"""
    return load_instance_from_s2()


def sensitivity_scenarios(instance: Instance | None = None) -> tuple[RateScenario, ...]:
    """生成名义情形与 12 个节点各自 ±5 个百分点的 OAT 情形。"""
    instance = instance or default_instance()
    baseline = dict(instance.defect_rates)
    scenarios = [RateScenario("NOMINAL", None, "nominal", baseline)]
    for node in LEAVES + ASSEMBLIES:
        for direction, rate in (("low", F(1, 20)), ("high", F(3, 20))):
            rates = dict(baseline)
            rates[node] = rate
            scenarios.append(
                RateScenario(f"{node}_{direction.upper()}", node, direction, rates)
            )
    return tuple(scenarios)


def all_policies() -> Iterable[Policy]:
    """机械生成完整65536候选域，不预删硬门失败策略。"""
    for bits in product((0, 1), repeat=16):
        yield Policy(bits)


def zero_events() -> list[F]:
    return [F(0) for _ in EVENT_NAMES]


def add_events(*vectors: Iterable[F]) -> list[F]:
    answer = zero_events()
    for vector in vectors:
        for i, value in enumerate(vector):
            answer[i] += value
    return answer


def scale_events(vector: Iterable[F], factor: F) -> list[F]:
    return [factor * value for value in vector]


def event_vector(**counts: F | int) -> list[F]:
    """建立事件向量；atomic_steps定义为全部实际动作事件（不含自身）之和。"""
    answer = zero_events()
    for name, value in counts.items():
        if name == "atomic_steps" or name not in EVENT_INDEX:
            raise KeyError(name)
        answer[EVENT_INDEX[name]] += F(value)
        answer[EVENT_INDEX["atomic_steps"]] += F(value)
    return answer


def validate_instance(instance: Instance) -> None:
    nodes = set(LEAVES + ASSEMBLIES)
    if set(instance.defect_rates) != nodes:
        raise ValueError("12个节点的次品率字段不完整")
    if set(instance.purchase_costs) != set(LEAVES):
        raise ValueError("8个叶节点购买费字段不完整")
    if set(instance.inspection_costs) != nodes:
        raise ValueError("12个节点检测费字段不完整")
    if set(instance.assembly_costs) != set(ASSEMBLIES):
        raise ValueError("4个装配节点装配费字段不完整")
    if set(instance.disassembly_costs) != set(ASSEMBLIES):
        raise ValueError("4个装配节点拆解费字段不完整")
    if any(not (0 <= rate < 1) for rate in instance.defect_rates.values()):
        raise ValueError("次品率必须位于[0,1)")
    # 本题展开树：12节点、11条边、唯一根、每个非根位置只供给一个父节点。
    edges = [(child, parent) for parent, children in CHILDREN.items() for child in children]
    if len(edges) != 11 or len({child for child, _ in edges}) != 11:
        raise ValueError("物料图不是题定的单根展开树")
    reachable = {"F"}
    pending = ["F"]
    while pending:
        parent = pending.pop()
        for child in CHILDREN.get(parent, ()):
            if child not in reachable:
                reachable.add(child)
                pending.append(child)
    if reachable != nodes:
        raise ValueError("物料图存在不可达节点")


def parent_quality(child_qualities: Iterable[str], shock_quality: str) -> str:
    """S4第4.2节的唯一父节点质量律。"""
    qualities = tuple(child_qualities)
    if any(value not in (GOOD, BAD) for value in qualities + (shock_quality,)):
        raise ValueError("质量只能为G或B")
    return GOOD if all(value == GOOD for value in qualities) and shock_quality == GOOD else BAD


def disassemble_frontier(
    frontier: frozenset[str], parent: str
) -> frozenset[str]:
    """微型前沿解释器：只移除父对象并恢复其直接输入，不复制嵌套对象。"""
    if parent not in frontier or parent not in CHILDREN:
        raise ValueError("待拆节点必须是前沿中的装配对象")
    answer = (set(frontier) - {parent}) | set(CHILDREN[parent])
    # 展开树中任一节点与其祖先不得同时位于前沿。
    for node in answer:
        pending = list(CHILDREN.get(node, ()))
        while pending:
            child = pending.pop()
            if child in answer:
                raise ValueError("非法前沿：祖先与后代同时存在")
            pending.extend(CHILDREN.get(child, ()))
    return frozenset(answer)


def inspect_knowledge(actual_quality: str) -> str:
    """准确检测只揭示被测对象本身；坏父件不定位具体坏因。"""
    if actual_quality not in (GOOD, BAD):
        raise ValueError(actual_quality)
    return actual_quality


def _semi_kernel(
    semi: str,
    leaf_inspections: tuple[int, ...],
    inspect_semi: int,
    disassemble_semi: int,
    rates: dict[str, F],
) -> LocalKernel:
    """从空半成品位置或已知良品对象出发的精确局部更新核。"""
    children = CHILDREN[semi]
    if len(children) != len(leaf_inspections):
        raise ValueError("局部策略长度错误")
    semi_good = 1 - rates[semi]

    # 检出坏半成品后拆回，但某个未检叶坏件会永久保留，形成非吸收闭类。
    if inspect_semi and disassemble_semi and any(
        not inspect_leaf and rates[leaf] > 0
        for leaf, inspect_leaf in zip(children, leaf_inspections)
    ):
        return LocalKernel(
            False,
            "persistent_bad_uninspected_leaf_closed_class",
            None,
            None,
            None,
        )

    initial = zero_events()
    for leaf, inspect_leaf in zip(children, leaf_inspections):
        leaf_good = 1 - rates[leaf]
        if inspect_leaf:
            initial = add_events(
                initial,
                event_vector(
                    **{
                        f"purchase_{leaf}": 1 / leaf_good,
                        f"inspect_{leaf}": 1 / leaf_good,
                    }
                ),
            )
        else:
            initial = add_events(initial, event_vector(**{f"purchase_{leaf}": 1}))
    initial = add_events(initial, event_vector(**{f"assemble_{semi}": 1}))

    child_good_probability = F(1)
    for leaf, inspect_leaf in zip(children, leaf_inspections):
        child_good_probability *= F(1) if inspect_leaf else 1 - rates[leaf]
    one_build_success = child_good_probability * semi_good

    known_good = zero_events()
    if inspect_semi:
        known_good = event_vector(**{f"inspect_{semi}": 1})

    if not inspect_semi:
        return LocalKernel(
            True,
            "uninspected_semi_returns_after_one_build",
            one_build_success,
            tuple(initial),
            tuple(known_good),
        )

    initial = add_events(initial, event_vector(**{f"inspect_{semi}": 1}))
    if not disassemble_semi:
        # 每次坏品连同内部树丢弃，下一循环与空状态同分布。
        total = scale_events(initial, 1 / one_build_success)
        return LocalKernel(
            True,
            "bad_semi_discard_renews_empty_state",
            F(1),
            tuple(total),
            tuple(known_good),
        )

    # 到此所有叶件均检测合格。首次装配失败后拆回同一批良叶；每轮按固定策略重检。
    retained_cycle = zero_events()
    for leaf in children:
        retained_cycle = add_events(retained_cycle, event_vector(**{f"inspect_{leaf}": 1}))
    retained_cycle = add_events(
        retained_cycle,
        event_vector(**{f"assemble_{semi}": 1, f"inspect_{semi}": 1}),
    )
    retained_value = add_events(
        scale_events(retained_cycle, 1 / semi_good),
        scale_events(
            event_vector(**{f"disassemble_{semi}": 1}),
            rates[semi] / semi_good,
        ),
    )
    total = add_events(
        initial,
        scale_events(
            add_events(event_vector(**{f"disassemble_{semi}": 1}), retained_value),
            rates[semi],
        ),
    )
    return LocalKernel(
        True,
        "screened_children_reassembly_geometric_macro",
        F(1),
        tuple(total),
        tuple(known_good),
    )


def local_kernel(
    policy: Policy,
    semi: str,
    rates: dict[str, F],
    cache: dict[tuple, LocalKernel] | None = None,
) -> LocalKernel:
    leaves = policy.leaf_inspections
    semi_i = policy.semi_inspections[semi]
    semi_d = policy.semi_disassemblies[semi]
    rate_key = tuple(rates[node] for node in CHILDREN[semi] + (semi,))
    key = (
        semi,
        tuple(leaves[leaf] for leaf in CHILDREN[semi]),
        semi_i,
        semi_d,
        rate_key,
    )
    if cache is not None and key in cache:
        return cache[key]
    answer = _semi_kernel(semi, key[1], semi_i, semi_d, rates)
    if cache is not None:
        cache[key] = answer
    return answer


def _attempt_kernel(
    policy: Policy,
    rates: dict[str, F],
    start: str,
    cache: dict[tuple, LocalKernel] | None,
) -> tuple[F, list[F], str | None]:
    """返回一次根尝试的成功率、无条件期望事件和局部不可行原因。"""
    kernels = [local_kernel(policy, semi, rates, cache) for semi in SEMIS]
    for semi, kernel in zip(SEMIS, kernels):
        if not kernel.feasible:
            return F(0), zero_events(), f"{semi}:{kernel.reason}"

    if start == "empty":
        local_events = add_events(*(kernel.events_from_empty for kernel in kernels))
        semi_good = F(1)
        for kernel in kernels:
            semi_good *= kernel.good_probability
    elif start == "known_good_semis":
        local_events = add_events(*(kernel.events_from_known_good for kernel in kernels))
        semi_good = F(1)
    else:
        raise ValueError(start)

    success = semi_good * (1 - rates["F"])
    common = add_events(
        local_events,
        event_vector(
            assemble_F=1,
            root_attempts=1,
            **({"inspect_F": 1} if policy.inspect_final else {}),
        ),
    )
    failure = 1 - success
    failure_events = zero_events()
    if policy.disassemble_final:
        failure_events = add_events(failure_events, event_vector(disassemble_F=1))
    if not policy.inspect_final:
        failure_events = add_events(
            failure_events, event_vector(market_bad_products_and_exchanges=1)
        )
    return success, add_events(common, scale_events(failure_events, failure)), None


def event_cost(events: Iterable[F], instance: Instance) -> F:
    values = dict(zip(EVENT_NAMES, events))
    total = F(0)
    for leaf in LEAVES:
        total += instance.purchase_costs[leaf] * values[f"purchase_{leaf}"]
    for node in LEAVES + ASSEMBLIES:
        total += instance.inspection_costs[node] * values[f"inspect_{node}"]
    for node in ASSEMBLIES:
        total += instance.assembly_costs[node] * values[f"assemble_{node}"]
        total += instance.disassembly_costs[node] * values[f"disassemble_{node}"]
    total += instance.exchange_loss * values["market_bad_products_and_exchanges"]
    return total


def evaluate_policy(
    policy: Policy,
    scenario: RateScenario,
    instance: Instance | None = None,
    cache: dict[tuple, LocalKernel] | None = None,
) -> dict[str, object]:
    instance = instance or default_instance()
    rates = scenario.defect_rates
    positive_rates = [rate for rate in rates.values() if rate > 0]
    trap_lower_bound = min(positive_rates, default=F(0))

    def infeasible(reason: str) -> dict[str, object]:
        # 指定闭类均可由首个相关未检对象/冲击为坏触发；该原语的精确边际即下界。
        return {
            "policy_id": policy.policy_id,
            "scenario": scenario.name,
            "feasible": False,
            "gate_status": "infeasible_nonabsorbing",
            "gate_reason": reason,
            "graph_closed_class_check": "fail",
            "equation_absorption_check": "fail_certified_by_positive_trap_probability",
            "nonabsorption_probability_lower_bound": trap_lower_bound,
            "absorption_probability_upper_bound": 1 - trap_lower_bound,
            "absorption_probability": None,
            "expected_events": None,
            "total_cost": None,
            "profit": None,
        }

    # 若最终坏品拆回，未检测半成品可能作为永久坏对象反复回用。
    if policy.disassemble_final and not all(policy.semi_inspections.values()):
        return infeasible("persistent_bad_uninspected_semi_closed_class")

    success_empty, events_empty, reason = _attempt_kernel(
        policy, rates, "empty", cache
    )
    if reason is not None:
        return infeasible(reason)
    if success_empty <= 0:
        raise ArithmeticError("空前沿根尝试没有正成功概率")

    if not policy.disassemble_final:
        total_events = scale_events(events_empty, 1 / success_empty)
        gate_reason = "root_failure_renews_empty_frontier"
    else:
        success_good, events_good, reason = _attempt_kernel(
            policy, rates, "known_good_semis", cache
        )
        if reason is not None or success_good <= 0:
            raise ArithmeticError("已知良半成品状态不应无法吸收")
        value_good = scale_events(events_good, 1 / success_good)
        total_events = add_events(
            events_empty, scale_events(value_good, 1 - success_empty)
        )
        gate_reason = "two_state_root_kernel_absorbs_with_probability_one"

    cost = event_cost(total_events, instance)
    market_hit_probability = F(0) if policy.inspect_final else 1 - success_empty
    return {
        "policy_id": policy.policy_id,
        "scenario": scenario.name,
        "feasible": True,
        "gate_status": "feasible",
        "gate_reason": gate_reason,
        "graph_closed_class_check": "pass",
        "equation_absorption_check": "pass",
        "absorption_probability": F(1),
        "expected_events": tuple(total_events),
        "total_cost": cost,
        "profit": instance.sale_price - cost,
        "first_root_attempt_success_probability": success_empty,
        "at_least_one_market_bad_probability": market_hit_probability,
    }


def direct_parent_failure_posterior(child_good_rates: tuple[F, ...], shock_good: F) -> dict[tuple[str, ...], F]:
    """直接枚举父失败条件下的子件联合后验，用于相关性验收。"""
    joint: dict[tuple[str, ...], F] = {}
    failure_probability = F(0)
    for child_bits in product((0, 1), repeat=len(child_good_rates)):
        child_probability = F(1)
        for bit, rate in zip(child_bits, child_good_rates):
            child_probability *= rate if bit else 1 - rate
        parent_success = shock_good if all(child_bits) else F(0)
        mass = child_probability * (1 - parent_success)
        state = tuple(GOOD if bit else BAD for bit in child_bits)
        joint[state] = mass
        failure_probability += mass
    return {state: mass / failure_probability for state, mass in joint.items() if mass}


def fraction_text(value: F) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def decimal_text(value: F, places: int = 12) -> str:
    return f"{float(value):.{places}f}"
