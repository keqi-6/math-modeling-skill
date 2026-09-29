"""问题四问题三十二率精确评价核心。

输入：十二个节点各自的固定次品率、问题三冻结费用和16位固定策略。
输出：局部模块响应、全局硬门、精确事件期望、成本和利润。
职责：复用问题三节点特异率语义，供问题四抽样区间传播；问题三名义回归键为NOMINAL。
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from itertools import product
from pathlib import Path
import re
from typing import Iterable


F = Fraction
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
class Q3Instance:
    purchase_costs: dict[str, F]
    inspection_costs: dict[str, F]
    assembly_costs: dict[str, F]
    disassembly_costs: dict[str, F]
    sale_price: F
    exchange_loss: F


@dataclass(frozen=True)
class LocalAction:
    semi: str
    bits: tuple[int, ...]
    feasible: bool
    reason: str
    good_probability: F | None
    events_empty: tuple[F, ...] | None
    events_good: tuple[F, ...] | None
    cost_empty: F | None
    cost_good: F | None

    @property
    def inspect_semi(self) -> int:
        return self.bits[-2]

    @property
    def disassemble_semi(self) -> int:
        return self.bits[-1]


def zero_events() -> list[F]:
    return [F(0) for _ in EVENT_NAMES]


def add_events(*vectors: Iterable[F]) -> list[F]:
    total = zero_events()
    for vector in vectors:
        total = [left + right for left, right in zip(total, vector)]
    return total


def scale_events(vector: Iterable[F], factor: F) -> list[F]:
    return [value * factor for value in vector]


def event_vector(**counts: F | int) -> list[F]:
    vector = zero_events()
    for name, value in counts.items():
        vector[EVENT_INDEX[name]] = F(value)
    vector[EVENT_INDEX["atomic_steps"]] = sum(
        (F(value) for name, value in counts.items() if name != "atomic_steps"), F(0)
    )
    return vector


def parse_q3_instance(path: Path) -> Q3Instance:
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
        raise ValueError("问题三冻结参数接口解析失败")
    purchase = {f"P{i}": F(cost) for i, _, cost, _ in parts}
    inspection = {f"P{i}": F(cost) for i, _, _, cost in parts}
    assembly: dict[str, F] = {}
    disassembly: dict[str, F] = {}
    name_map = {"半成品1": "S1", "半成品2": "S2", "半成品3": "S3", "最终成品": "F"}
    for raw, _, assemble_cost, inspect_cost, disassemble_cost in assemblies:
        node = name_map[raw]
        assembly[node] = F(assemble_cost)
        inspection[node] = F(inspect_cost)
        disassembly[node] = F(disassemble_cost)
    market = re.search(r"market_price=([0-9.]+).*?exchange_loss=([0-9.]+)", text, re.DOTALL)
    if market is None:
        raise ValueError("问题三接口缺少售价或调换损失")
    answer = Q3Instance(purchase, inspection, assembly, disassembly, F(market.group(1)), F(market.group(2)))
    if set(answer.purchase_costs) != set(LEAVES) or set(answer.inspection_costs) != set(LEAVES + ASSEMBLIES):
        raise ValueError("问题三费用字段不完整")
    return answer


def event_cost(events: Iterable[F], instance: Q3Instance) -> F:
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


def local_action(
    semi: str,
    bits: tuple[int, ...],
    rates: dict[str, F],
    instance: Q3Instance,
) -> LocalAction:
    children = CHILDREN[semi]
    if len(bits) != len(children) + 2:
        raise ValueError("局部策略长度错误")
    leaf_bits, inspect_semi, disassemble_semi = bits[:-2], bits[-2], bits[-1]
    if inspect_semi and disassemble_semi and any(
        not inspect and rates[leaf] > 0 for leaf, inspect in zip(children, leaf_bits)
    ):
        return LocalAction(semi, bits, False, "persistent_bad_uninspected_leaf_closed_class", None, None, None, None, None)

    initial = zero_events()
    child_good = F(1)
    for leaf, inspect in zip(children, leaf_bits):
        good = 1 - rates[leaf]
        if good <= 0:
            return LocalAction(semi, bits, False, f"zero_good_probability:{leaf}", None, None, None, None, None)
        if inspect:
            initial = add_events(initial, event_vector(**{f"purchase_{leaf}": 1 / good, f"inspect_{leaf}": 1 / good}))
        else:
            initial = add_events(initial, event_vector(**{f"purchase_{leaf}": 1}))
            child_good *= good
    semi_good = 1 - rates[semi]
    if semi_good <= 0:
        return LocalAction(semi, bits, False, f"zero_good_probability:{semi}", None, None, None, None, None)
    initial = add_events(initial, event_vector(**{f"assemble_{semi}": 1}))
    one_build_success = child_good * semi_good
    known_good = event_vector(**{f"inspect_{semi}": 1}) if inspect_semi else zero_events()

    if not inspect_semi:
        events_empty = tuple(initial)
        events_good = tuple(known_good)
        return LocalAction(
            semi, bits, True, "uninspected_semi_returns_after_one_build", one_build_success,
            events_empty, events_good, event_cost(events_empty, instance), event_cost(events_good, instance),
        )

    initial = add_events(initial, event_vector(**{f"inspect_{semi}": 1}))
    if not disassemble_semi:
        total = tuple(scale_events(initial, 1 / one_build_success))
        good_events = tuple(known_good)
        return LocalAction(
            semi, bits, True, "bad_semi_discard_renews_empty_state", F(1),
            total, good_events, event_cost(total, instance), event_cost(good_events, instance),
        )

    retained_cycle = zero_events()
    for leaf in children:
        retained_cycle = add_events(retained_cycle, event_vector(**{f"inspect_{leaf}": 1}))
    retained_cycle = add_events(retained_cycle, event_vector(**{f"assemble_{semi}": 1, f"inspect_{semi}": 1}))
    retained_value = add_events(
        scale_events(retained_cycle, 1 / semi_good),
        scale_events(event_vector(**{f"disassemble_{semi}": 1}), rates[semi] / semi_good),
    )
    total = tuple(add_events(
        initial,
        scale_events(add_events(event_vector(**{f"disassemble_{semi}": 1}), retained_value), rates[semi]),
    ))
    good_events = tuple(known_good)
    return LocalAction(
        semi, bits, True, "screened_children_reassembly_geometric_macro", F(1),
        total, good_events, event_cost(total, instance), event_cost(good_events, instance),
    )


def all_local_actions(semi: str, rates: dict[str, F], instance: Q3Instance) -> list[LocalAction]:
    return [
        local_action(semi, bits, rates, instance)
        for bits in product((0, 1), repeat=len(CHILDREN[semi]) + 2)
    ]


def decode_policy(policy_id: str) -> tuple[int, ...]:
    if len(policy_id) != 16 or any(bit not in "01" for bit in policy_id):
        raise ValueError("问题三策略必须是16位二进制串")
    return tuple(int(bit) for bit in policy_id)


def policy_from_local(
    m1_bits: tuple[int, ...],
    m2_bits: tuple[int, ...],
    m3_bits: tuple[int, ...],
    inspect_final: int,
    disassemble_final: int,
) -> str:
    bits = [0] * 16
    for target, values in (((0, 1, 2), m1_bits[:-2]), ((3, 4, 5), m2_bits[:-2]), ((6, 7), m3_bits[:-2])):
        for index, value in zip(target, values):
            bits[index] = value
    bits[8], bits[12] = m1_bits[-2], m1_bits[-1]
    bits[9], bits[13] = m2_bits[-2], m2_bits[-1]
    bits[10], bits[14] = m3_bits[-2], m3_bits[-1]
    bits[11], bits[15] = inspect_final, disassemble_final
    return "".join(map(str, bits))


def swap_m1_m2_policy(policy_id: str) -> str:
    bits = list(decode_policy(policy_id))
    for left, right in ((0, 3), (1, 4), (2, 5), (8, 9), (12, 13)):
        bits[left], bits[right] = bits[right], bits[left]
    return "".join(map(str, bits))


def evaluate_q3_policy(
    policy_id: str,
    rates: dict[str, F],
    instance: Q3Instance,
    action_cache: dict[tuple[object, ...], LocalAction] | None = None,
) -> dict[str, object]:
    bits = decode_policy(policy_id)
    module_bits = {
        "S1": (bits[0], bits[1], bits[2], bits[8], bits[12]),
        "S2": (bits[3], bits[4], bits[5], bits[9], bits[13]),
        "S3": (bits[6], bits[7], bits[10], bits[14]),
    }
    actions: dict[str, LocalAction] = {}
    for semi in SEMIS:
        rate_key = tuple(rates[node] for node in CHILDREN[semi] + (semi,))
        key = (semi, module_bits[semi], rate_key)
        if action_cache is not None and key in action_cache:
            actions[semi] = action_cache[key]
        else:
            actions[semi] = local_action(semi, module_bits[semi], rates, instance)
            if action_cache is not None:
                action_cache[key] = actions[semi]
    for semi, action in actions.items():
        if not action.feasible:
            return {"policy_id": policy_id, "feasible": False, "gate_reason": f"{semi}:{action.reason}"}

    inspect_final, disassemble_final = bits[11], bits[15]
    if disassemble_final and any(
        not actions[semi].inspect_semi and actions[semi].good_probability < 1 for semi in SEMIS
    ):
        return {"policy_id": policy_id, "feasible": False, "gate_reason": "persistent_bad_uninspected_semi_closed_class"}

    local_empty = add_events(*(actions[semi].events_empty for semi in SEMIS))
    semi_good = F(1)
    for semi in SEMIS:
        semi_good *= actions[semi].good_probability
    success_empty = semi_good * (1 - rates["F"])
    if success_empty <= 0:
        return {"policy_id": policy_id, "feasible": False, "gate_reason": "zero_root_success_probability"}
    root_common = event_vector(
        assemble_F=1,
        root_attempts=1,
        **({"inspect_F": 1} if inspect_final else {}),
    )
    failure_events = event_vector(
        **({"disassemble_F": 1} if disassemble_final else {}),
        **({"market_bad_products_and_exchanges": 1} if not inspect_final else {}),
    )
    events_empty = add_events(local_empty, root_common, scale_events(failure_events, 1 - success_empty))

    if not disassemble_final:
        total_events = tuple(scale_events(events_empty, 1 / success_empty))
        gate_reason = "root_failure_renews_empty_frontier"
    else:
        local_good = add_events(*(actions[semi].events_good for semi in SEMIS))
        success_good = 1 - rates["F"]
        events_good = add_events(local_good, root_common, scale_events(failure_events, rates["F"]))
        total_events = tuple(add_events(events_empty, scale_events(events_good, (1 - success_empty) / success_good)))
        gate_reason = "two_state_root_kernel_absorbs_with_probability_one"

    total_cost = event_cost(total_events, instance)
    return {
        "policy_id": policy_id,
        "feasible": True,
        "gate_reason": gate_reason,
        "expected_events": total_events,
        "total_cost": total_cost,
        "profit": instance.sale_price - total_cost,
        "first_root_attempt_success_probability": success_empty,
        "at_least_one_market_bad_probability": F(0) if inspect_final else 1 - success_empty,
    }


def fraction_text(value: F) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"
