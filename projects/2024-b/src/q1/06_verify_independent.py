"""问题一完整动作空间 S6 独立验证器：不导入主求解核心，不复用其任何函数。

只从冻结产物读取 N、阈值和声称值，用独立公式重推导：
- 三值动作（继续/接收/拒收）的前向精确概率流、ASN 与全 D 曲线；
- 事实停止边界攻击（(9,9)、(9,0)、第二件次品、剩余容量）；
- N=10 规范阈值类完整枚举求独立最优；
- 独立拉格朗日 Bellman 下界与主实现交叉验证；
- 概率质量守恒、方向概率断言与阈值域有效性（N=1,2,3,9,10,20,23,50）。

输出：output/q1/s6_independent_verification.json 与运行清单。
"""

from __future__ import annotations

import hashlib
import itertools
import json
import platform
import sys
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "planning/analysis/2026-08-25_q1_s4_complete_action_specification.md"
S5_RESULT_PATH = PROJECT_ROOT / "output/q1/s5_results.json"
S5_CLOSURE_PATH = PROJECT_ROOT / "output/q1/s5_finite_closure.json"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/s6_independent_verification.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s6_independent_verification_manifest.json"
SCRIPT_PATH = Path(__file__).resolve()

ACTION_CONTINUE = 0
ACTION_ACCEPT = 1
ACTION_REJECT = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fraction_from_payload(payload: dict[str, object]) -> Fraction:
    return Fraction(int(payload["numerator"]), int(payload["denominator"]))


def fraction_payload(value: Fraction, digits: int = 24) -> dict[str, object]:
    with localcontext() as context:
        context.prec = digits
        decimal_value = Decimal(value.numerator) / Decimal(value.denominator)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": format(decimal_value, "f"),
    }


def boundary_counts(n: int) -> tuple[int, int]:
    if not isinstance(n, int) or isinstance(n, bool) or n < 1:
        raise ValueError("N必须为正整数")
    d0 = n // 10
    return d0, d0 + 1


def validate_domain(n: int, scenario: str, thresholds: tuple[int, ...]) -> None:
    """独立校验 S4 第 3 节规范阈值域（不导入主核心）。"""

    if len(thresholds) != n - 1:
        raise ValueError("阈值长度错误")
    d0, _ = boundary_counts(n)
    for t, threshold in enumerate(thresholds, start=1):
        if scenario == "R":
            if threshold != t + 1 and not (0 <= threshold <= min(t, d0)):
                raise ValueError(f"R t={t} 阈值越出规范域")
        else:
            if threshold != -1 and not (
                max(0, t - (n - d0) + 1) <= threshold <= min(t, d0)
            ):
                raise ValueError(f"A t={t} 阈值越出规范域")


def state_action(n: int, scenario: str, t: int, x: int, thresholds: tuple[int, ...]) -> int:
    """按 S4 合同独立推出 (t,x) 的三值动作：事实动作优先，统计阈值其次。"""

    d0, d1 = boundary_counts(n)
    if t >= n:
        return ACTION_CONTINUE
    if t < 1:
        return ACTION_CONTINUE
    if x >= d1:
        return ACTION_REJECT
    if x + (n - t) <= d0:
        return ACTION_ACCEPT
    threshold = thresholds[t - 1]
    if scenario == "R":
        return ACTION_REJECT if x >= threshold else ACTION_CONTINUE
    return ACTION_ACCEPT if x <= threshold else ACTION_CONTINUE


def independently_evaluate(
    n: int,
    d: int,
    scenario: str,
    thresholds: tuple[int, ...],
) -> tuple[Fraction, Fraction, Fraction, Fraction, Fraction]:
    """独立前向精确概率流：返回(任意停止, 接收, 拒收, ASN, 终点)。"""

    validate_domain(n, scenario, thresholds)
    alive: dict[int, Fraction] = {0: Fraction(1)}
    stopped = Fraction(0)
    accepted = Fraction(0)
    rejected = Fraction(0)
    time_mass = Fraction(0)
    for t in range(n):
        following: dict[int, Fraction] = {}
        for x, mass in alive.items():
            if mass == 0:
                continue
            action = state_action(n, scenario, t, x, thresholds)
            if action != ACTION_CONTINUE:
                stopped += mass
                time_mass += t * mass
                if action == ACTION_ACCEPT:
                    accepted += mass
                else:
                    rejected += mass
                continue
            defect_numerator = d - x
            good_numerator = n - d - t + x
            if defect_numerator < 0 or good_numerator < 0:
                raise AssertionError(f"不可达状态 (t={t},x={x}) 获得正概率")
            denominator = n - t
            defect = Fraction(defect_numerator, denominator)
            good = Fraction(good_numerator, denominator)
            if defect + good != 1:
                raise AssertionError("独立一步转移不守恒")
            following[x + 1] = following.get(x + 1, Fraction(0)) + mass * defect
            following[x] = following.get(x, Fraction(0)) + mass * good
        alive = following
    terminal = sum(alive.values(), Fraction(0))
    if stopped + terminal != 1:
        raise AssertionError("独立早停与终点质量不守恒")
    if accepted + rejected != stopped:
        raise AssertionError("独立接收与拒收质量不等于总停止质量")
    return stopped, accepted, rejected, time_mass + n * terminal, terminal


def full_curve(n: int, scenario: str, thresholds: tuple[int, ...]) -> list[tuple[Fraction, Fraction, Fraction, Fraction, Fraction]]:
    return [independently_evaluate(n, d, scenario, thresholds) for d in range(n + 1)]


def canonical_domains(n: int, scenario: str) -> tuple[tuple[int, ...], ...]:
    d0, _ = boundary_counts(n)
    domains: list[tuple[int, ...]] = []
    for t in range(1, n):
        if scenario == "R":
            values = list(range(min(t, d0) + 1))
            disabled = t + 1
            if disabled not in values:
                values.append(disabled)
        else:
            reachable_minimum = max(0, t - (n - d0) + 1)
            reachable_maximum = min(t, d0)
            values = [-1, *range(reachable_minimum, reachable_maximum + 1)]
        domains.append(tuple(values))
    return tuple(domains)


def action_vector(n: int, scenario: str, thresholds: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(
        state_action(n, scenario, t, x, thresholds)
        for t in range(1, n)
        for x in range(t + 1)
    )


def exhaustive_optimum(
    n: int,
    scenario: str,
) -> tuple[Fraction, Fraction, tuple[int, ...], int, int]:
    """独立完整枚举规范阈值类，返回(风险, ASN, 阈值, 策略数, 可行数)。"""

    d0, d1 = boundary_counts(n)
    if scenario == "R":
        null_d, target_d, limit = d0, d1, Fraction(1, 20)
    else:
        null_d, target_d, limit = d1, d0, Fraction(1, 10)
    best: tuple[Fraction, tuple[int, ...], tuple[int, ...]] | None = None
    best_risk: Fraction | None = None
    policies = 0
    feasible = 0
    for thresholds in itertools.product(*canonical_domains(n, scenario)):
        policies += 1
        _, acc, rej, _, _ = independently_evaluate(n, null_d, scenario, thresholds)
        risk = acc if scenario == "A" else rej
        if risk > limit:
            continue
        feasible += 1
        _, _, _, asn, _ = independently_evaluate(n, target_d, scenario, thresholds)
        candidate = (asn, action_vector(n, scenario, thresholds), thresholds)
        if best is None or candidate < best:
            best = candidate
            best_risk = risk
    if best is None:
        raise AssertionError("独立全枚举没有找到可行阈值")
    return best_risk, best[0], best[2], policies, feasible


def falling(value: int, length: int) -> int:
    if length < 0 or length > value:
        return 0
    answer = 1
    for offset in range(length):
        answer *= value - offset
    return answer


def likelihood(n: int, d: int, t: int, x: int) -> Fraction:
    if not 0 <= x <= t <= n:
        return Fraction(0)
    return Fraction(
        (2**t) * falling(d, x) * falling(n - d, t - x),
        falling(n, t),
    )


def independent_wide_bellman_bound(
    n: int,
    scenario: str,
    multiplier: Fraction,
) -> Fraction:
    """独立重推导的宽类拉格朗日下界。

    事实状态必须停止：方向事实动作计入风险惩罚，反方向事实动作只计停止时间；
    未决状态在方向动作与继续之间取最小。与主实现不共享任何代码。
    """

    d0, d1 = boundary_counts(n)
    if scenario == "R":
        target_d, null_d, delta = d1, d0, Fraction(1, 20)
    else:
        target_d, null_d, delta = d0, d1, Fraction(1, 10)
    values = {x: n * likelihood(n, target_d, n, x) for x in range(n + 1)}
    for t in range(n - 1, 0, -1):
        prior: dict[int, Fraction] = {}
        for x in range(t + 1):
            target_l = likelihood(n, target_d, t, x)
            null_l = likelihood(n, null_d, t, x)
            keep = (values[x] + values[x + 1]) / 2
            if x >= d1:
                if scenario == "R":
                    prior[x] = t * target_l + multiplier * null_l
                else:
                    prior[x] = t * target_l
            elif x + (n - t) <= d0:
                if scenario == "R":
                    prior[x] = t * target_l
                else:
                    prior[x] = t * target_l + multiplier * null_l
            elif scenario == "R":
                prior[x] = min(t * target_l + multiplier * null_l, keep)
            else:
                prior[x] = min(t * target_l + multiplier * null_l, keep)
        values = prior
    return (values[0] + values[1]) / 2 - multiplier * delta


def main() -> None:
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    s5_payload = json.loads(S5_RESULT_PATH.read_text(encoding="utf-8"))
    closure_payload = json.loads(S5_CLOSURE_PATH.read_text(encoding="utf-8"))
    closure_by_n = {int(record["N"]): record for record in closure_payload["results"]}
    records: list[dict[str, object]] = []
    checks: list[dict[str, object]] = []
    exhaustive_summary: dict[str, object] = {}

    for record in s5_payload["results"]:
        n = int(record["N"])
        d0, d1 = boundary_counts(n)
        scenario_records: dict[str, object] = {}
        for scenario in ("R", "A"):
            source = record["scenarios"][scenario]
            thresholds = tuple(int(item["threshold"]) for item in source["thresholds"])
            validate_domain(n, scenario, thresholds)
            curve = full_curve(n, scenario, thresholds)
            if scenario == "R":
                null_d, target_d, limit = d0, d1, Fraction(1, 20)
            else:
                null_d, target_d, limit = d1, d0, Fraction(1, 10)

            # 概率守恒与方向断言
            for d, ev in enumerate(curve):
                checks.append({
                    "check": f"N={n}:{scenario}:D={d}:mass_conservation",
                    "pass": bool(ev[0] + ev[4] == 1 and ev[1] + ev[2] == ev[0]),
                    "detail": "stopped+terminal=1 且 accepted+rejected=stopped",
                })
            if scenario == "R":
                direction_ok = all(
                    ev[1] == 0 for d, ev in enumerate(curve) if d >= d1
                )
                checks.append({
                    "check": f"N={n}:{scenario}:no_accept_above_D0",
                    "pass": bool(direction_ok),
                    "detail": "D>=D1 无任何接收（R 无统计接收且事实接收不可达）",
                })
            else:
                direction_ok = all(
                    ev[2] == 0 for d, ev in enumerate(curve) if d <= d0
                )
                checks.append({
                    "check": f"N={n}:{scenario}:no_reject_below_D1",
                    "pass": bool(direction_ok),
                    "detail": "D<=D0 无任何拒收（A 无统计拒收且事实拒收不可达）",
                })

            # 边界风险、目标侧最坏点与限额（独立计算）
            if scenario == "R":
                risk = curve[d0][2]
                target_asn = max(ev[3] for d, ev in enumerate(curve) if d >= d1)
                target_at_boundary = curve[d1][3]
            else:
                risk = curve[d1][1]
                target_asn = max(ev[3] for d, ev in enumerate(curve) if d <= d0)
                target_at_boundary = curve[d0][3]
            checks.append({
                "check": f"N={n}:{scenario}:risk_limit",
                "pass": bool(risk <= limit),
                "detail": f"risk={risk} limit={limit}",
            })
            checks.append({
                "check": f"N={n}:{scenario}:target_worst_point_at_boundary",
                "pass": bool(target_asn == target_at_boundary),
                "detail": f"target_asn={target_asn} boundary={target_at_boundary}",
            })
            checks.append({
                "check": f"N={n}:{scenario}:risk_matches_claim",
                "pass": bool(risk == fraction_from_payload(source["risk_at_composite_worst_point"])),
                "detail": "独立风险与冻结声称一致",
            })
            checks.append({
                "check": f"N={n}:{scenario}:asn_matches_claim",
                "pass": bool(target_at_boundary == fraction_from_payload(source["worst_target_ASN_upper_bound"])),
                "detail": "独立目标侧ASN与冻结声称一致",
            })

            # 边界状态攻击
            boundary_attacks: list[dict[str, object]] = []
            for t in range(1, n):
                for x in range(t + 1):
                    action = state_action(n, scenario, t, x, thresholds)
                    if x >= d1 and action != ACTION_REJECT:
                        boundary_attacks.append({"state": [t, x], "problem": "事实拒收态未拒收"})
                    if x + (n - t) <= d0 and action != ACTION_ACCEPT:
                        boundary_attacks.append({"state": [t, x], "problem": "事实接收态未接收"})
            checks.append({
                "check": f"N={n}:{scenario}:factual_state_attack",
                "pass": len(boundary_attacks) == 0,
                "detail": str(boundary_attacks[:5]) if boundary_attacks else "全部事实状态动作正确",
            })
            if n == 10:
                checks.append({
                    "check": "N=10:scenario_agnostic:(9,9)_reject",
                    "pass": bool(state_action(n, scenario, 9, 9, thresholds) == ACTION_REJECT),
                    "detail": "(9,9) 必须为拒收",
                })
                checks.append({
                    "check": "N=10:scenario_agnostic:(9,0)_accept",
                    "pass": bool(state_action(n, scenario, 9, 0, thresholds) == ACTION_ACCEPT),
                    "detail": "(9,0) 必须为接收",
                })
                checks.append({
                    "check": "N=10:scenario_agnostic:second_defective_reject",
                    "pass": bool(state_action(n, scenario, 2, 2, thresholds) == ACTION_REJECT),
                    "detail": "发现第2件次品立即拒收（事实拒收 x>=D1=2）",
                })

            # 独立宽类 Bellman 下界交叉验证
            frozen_multiplier = fraction_from_payload(source["best_multiplier"])
            frozen_dual = fraction_from_payload(source["dual_lower_bound"])
            independent_dual = independent_wide_bellman_bound(n, scenario, frozen_multiplier)
            frozen_asn = fraction_from_payload(source["worst_target_ASN_upper_bound"])
            checks.append({
                "check": f"N={n}:{scenario}:dual_is_valid_lower_bound",
                "pass": bool(independent_dual <= frozen_asn),
                "detail": f"independent_dual={independent_dual} <= frozen_asn={frozen_asn}",
            })
            checks.append({
                "check": f"N={n}:{scenario}:dual_cross_validation",
                "pass": bool(independent_dual == frozen_dual),
                "detail": f"independent_dual={independent_dual} frozen_dual={frozen_dual}",
            })

            scenario_records[scenario] = {
                "scenario": scenario,
                "thresholds": list(thresholds),
                "independently_recomputed_risk": fraction_payload(risk),
                "independently_recomputed_target_asn": fraction_payload(target_at_boundary),
                "independent_dual_lower_bound": fraction_payload(independent_dual),
                "frozen_dual_lower_bound": fraction_payload(frozen_dual),
                "dual_cross_validation": independent_dual == frozen_dual,
                "boundary_attacks": boundary_attacks,
            }

        records.append({"N": n, "D0": d0, "D1": d1, "scenarios": scenario_records})

    # N=10 独立完整枚举
    for scenario in ("R", "A"):
        n = 10
        risk, asn, thresholds, policies, feasible = exhaustive_optimum(n, scenario)
        source = None
        for record in s5_payload["results"]:
            if int(record["N"]) == n:
                source = record["scenarios"][scenario]
                break
        frozen_asn = fraction_from_payload(source["worst_target_ASN_upper_bound"])
        frozen_thresholds = tuple(int(item["threshold"]) for item in source["thresholds"])
        optimum_matches = (
            asn == frozen_asn and action_vector(n, scenario, thresholds) == action_vector(n, scenario, frozen_thresholds)
        )
        checks.append({
            "check": f"N=10:{scenario}:exhaustive_class_optimum_matches",
            "pass": bool(optimum_matches),
            "detail": f"独立最优 asn={asn} 阈值={thresholds}；冻结 asn={frozen_asn} 阈值={frozen_thresholds}",
        })
        exhaustive_summary[f"N10_{scenario}"] = {
            "policies_enummerated": policies,
            "feasible_policies": feasible,
            "independent_optimum_asn": fraction_payload(asn),
            "independent_optimum_risk": fraction_payload(risk),
            "independent_optimum_thresholds": list(thresholds),
            "matches_frozen_selection": optimum_matches,
        }

    # 闭合结果一致性：N=10/23 声称 proved 的阈值与独立数值一致
    closure_checks: list[dict[str, object]] = []
    for n, closure_record in closure_by_n.items():
        for scenario in ("R", "A"):
            c = closure_record["scenarios"][scenario]
            closure_thresholds = tuple(int(item["threshold"]) for item in c["thresholds"])
            d0, d1 = boundary_counts(n)
            null_d = d0 if scenario == "R" else d1
            _, acc, rej, _, _ = independently_evaluate(n, null_d, scenario, closure_thresholds)
            risk = acc if scenario == "A" else rej
            limit = Fraction(1, 20) if scenario == "R" else Fraction(1, 10)
            claimed_risk = fraction_from_payload(c["risk_at_composite_worst_point"])
            claimed_asn = fraction_from_payload(c["ASN_upper_bound"])
            closure_checks.append({
                "check": f"closure:N={n}:{scenario}:numeric_consistency",
                "pass": bool(
                    risk <= limit
                    and risk == claimed_risk
                ),
                "detail": f"independent_risk={risk} claimed={claimed_risk} asn={claimed_asn}",
            })
    checks.extend(closure_checks)

    passed = sum(1 for item in checks if item["pass"])
    total = len(checks)
    payload = {
        "schema_version": "1.0",
        "artifact_status": "s6_independent_verification",
        "claim_status": (
            "all_independent_checks_passed"
            if passed == total
            else "independent_verification_failures_present"
        ),
        "producer": "src/q1/06_verify_independent.py",
        "consumers": [
            "planning/analysis/2026-08-25_q1_s6_independent_verification.md",
            "planning/audits/2026-08-25_q1_s6_closure.md",
            "docs/q1/solution_brief.md",
        ],
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "input_identity": {
            "specification_path": str(SPEC_PATH.relative_to(PROJECT_ROOT)),
            "specification_sha256": sha256(SPEC_PATH),
            "s5_results_path": str(S5_RESULT_PATH.relative_to(PROJECT_ROOT)),
            "s5_results_sha256": sha256(S5_RESULT_PATH),
            "s5_closure_path": str(S5_CLOSURE_PATH.relative_to(PROJECT_ROOT)),
            "s5_closure_sha256": sha256(S5_CLOSURE_PATH),
        },
        "independence": "no import of src/q1/core.py or any main implementation module",
        "records": records,
        "exhaustive_enumeration": exhaustive_summary,
        "check_count": total,
        "passed_count": passed,
        "checks": checks,
        "unresolved": [
            "reality validity under inspection error or non-random sampling remains unconfirmed (V4 not triggered)",
            "fixture N values are not an official or user-selected business batch size",
        ],
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s6_independent_verification_run_identity",
        "producer": "src/q1/06_verify_independent.py",
        "consumers": ["project audit"],
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT)), *sys.argv[1:]],
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "random_seed": None,
        },
        "inputs": {
            str(SPEC_PATH.relative_to(PROJECT_ROOT)): sha256(SPEC_PATH),
            str(S5_RESULT_PATH.relative_to(PROJECT_ROOT)): sha256(S5_RESULT_PATH),
            str(S5_CLOSURE_PATH.relative_to(PROJECT_ROOT)): sha256(S5_CLOSURE_PATH),
        },
        "sources": {
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
        },
        "outputs": {
            str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH),
        },
        "claim_boundary": "Independent S6 verification of frozen S5 results; it does not itself prove non-threshold policy classes.",
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "passed": passed,
        "total": total,
        "claim_status": payload["claim_status"],
    }, ensure_ascii=False))
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
