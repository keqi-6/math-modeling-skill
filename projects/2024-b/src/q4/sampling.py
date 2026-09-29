"""问题四有限总体抽样层。

输入：经S4批准的分析设置 ``(N,n,q)``。
输出：样本次品数 ``x``、单率95%精确双侧超几何集合及 ``L/Q/U``。
职责：只处理固定样本无放回推断；不实现问题一的接收、拒收或序贯停止规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import comb


F = Fraction
ALPHA_HALF = F(1, 40)


@dataclass(frozen=True)
class SamplingSetting:
    setting_id: str
    population_size: int
    sample_size: int


@dataclass(frozen=True)
class ExactInterval:
    setting_id: str
    population_size: int
    sample_size: int
    observed_defects: int
    displayed_rate: F
    accepted_defect_counts: tuple[int, ...]

    @property
    def lower(self) -> F:
        return F(self.accepted_defect_counts[0], self.population_size)

    @property
    def center(self) -> F:
        return self.displayed_rate

    @property
    def upper(self) -> F:
        return F(self.accepted_defect_counts[-1], self.population_size)

    @property
    def levels(self) -> tuple[F, F, F]:
        return self.lower, self.center, self.upper


SETTINGS = (
    SamplingSetting("N200_n100", 200, 100),
    SamplingSetting("N500_n20", 500, 20),
    SamplingSetting("N500_n100", 500, 100),
    SamplingSetting("N500_n200", 500, 200),
    SamplingSetting("N1000_n100", 1000, 100),
)

DISPLAYED_RATES = (F(1, 20), F(1, 10), F(1, 5))


def _support(N: int, D: int, n: int) -> range:
    return range(max(0, n - (N - D)), min(n, D) + 1)


def hypergeometric_mass_numerators(N: int, D: int, n: int) -> dict[int, int]:
    """返回共同分母 ``C(N,n)`` 下的精确概率分子。"""
    return {k: comb(D, k) * comb(N - D, n - k) for k in _support(N, D, n)}


def exact_two_sided_interval(setting: SamplingSetting, q: F) -> ExactInterval:
    N, n = setting.population_size, setting.sample_size
    if not (N >= 1 and 1 <= n <= N and 0 <= q <= 1):
        raise ValueError("非法有限总体抽样设置")
    x_value = q * n
    if x_value.denominator != 1:
        raise ValueError(f"样本率与样本量不相容: n={n}, q={q}")
    x = x_value.numerator
    if not 0 <= x <= n:
        raise ValueError("样本次品数超界")

    denominator = comb(N, n)
    accepted: list[int] = []
    for D in range(x, N - n + x + 1):
        masses = hypergeometric_mass_numerators(N, D, n)
        upper_numerator = sum(value for k, value in masses.items() if k >= x)
        lower_numerator = sum(value for k, value in masses.items() if k <= x)
        if upper_numerator * ALPHA_HALF.denominator > denominator * ALPHA_HALF.numerator and lower_numerator * ALPHA_HALF.denominator > denominator * ALPHA_HALF.numerator:
            accepted.append(D)
    if not accepted:
        raise ArithmeticError("精确超几何反演得到空集合")
    return ExactInterval(setting.setting_id, N, n, x, q, tuple(accepted))


def build_interval_table() -> dict[tuple[str, F], ExactInterval]:
    return {
        (setting.setting_id, q): exact_two_sided_interval(setting, q)
        for setting in SETTINGS
        for q in DISPLAYED_RATES
    }


def fraction_text(value: F) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def interval_record(interval: ExactInterval) -> dict[str, object]:
    return {
        "setting_id": interval.setting_id,
        "N": interval.population_size,
        "n": interval.sample_size,
        "x": interval.observed_defects,
        "q": fraction_text(interval.displayed_rate),
        "accepted_D_min": interval.accepted_defect_counts[0],
        "accepted_D_max": interval.accepted_defect_counts[-1],
        "accepted_D_count": len(interval.accepted_defect_counts),
        "accepted_D_contiguous": interval.accepted_defect_counts
        == tuple(range(interval.accepted_defect_counts[0], interval.accepted_defect_counts[-1] + 1)),
        "L": fraction_text(interval.lower),
        "Q": fraction_text(interval.center),
        "U": fraction_text(interval.upper),
        "confidence_identity": "single_rate_exact_two_sided_hypergeometric_at_least_95_percent",
        "joint_confidence_claim": False,
        "provenance": "analysis_setting",
    }
