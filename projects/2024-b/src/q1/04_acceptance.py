"""问题一完整动作空间 S5 同实现验收：S4 规格第 6 节必过测试。

输入：output/q1/s5_results.json 与 output/q1/s5_finite_closure.json。
输出：output/q1/s5_acceptance.json。
职责：在 S6 独立验证之前，用同一核心对冻结结果做边界攻击与守恒检查；不冒充独立验证。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from core import (
    ACTION_ACCEPT,
    ACTION_CONTINUE,
    ACTION_REJECT,
    actions_from_thresholds,
    assert_scenario_metrics,
    boundary_counts,
    evaluate_action_policy,
    evaluate_threshold_policy,
    factual_accept_at,
    factual_reject_at,
    fraction_payload,
    full_curve,
    validate_n,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = PROJECT_ROOT / "planning/analysis/2026-08-25_q1_s4_complete_action_specification.md"
RESULTS_PATH = PROJECT_ROOT / "output/q1/s5_results.json"
CLOSURE_PATH = PROJECT_ROOT / "output/q1/s5_finite_closure.json"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/s5_acceptance.json"
CORE_PATH = PROJECT_ROOT / "src/q1/core.py"
SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_N_VALUES = (1, 2, 3, 9, 10, 20, 23, 50)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_n_values(raw: str) -> tuple[int, ...]:
    values = tuple(sorted({int(item.strip()) for item in raw.split(",") if item.strip()}))
    if not values:
        raise ValueError("N列表不能为空")
    for value in values:
        validate_n(value)
    return values


def run_acceptance(n: int, scenario: str, thresholds: tuple[int, ...]) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    d0, d1 = boundary_counts(n)

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append({"check": name, "pass": bool(condition), "detail": detail})

    # C1: 概率质量守恒与方向概率守恒
    curve = full_curve(n, scenario, thresholds)
    conserved = all(
        ev.stop_probability + ev.terminal_probability == 1
        and ev.accept_probability + ev.reject_probability == ev.stop_probability
        for ev in curve
    )
    check("mass_conservation", conserved, f"full curve over D=0..{n}")

    # C2: 反方向事实动作零错误预算。R 无统计接收 => D>=D1 接收概率恒 0；
    # A 无统计拒收 => D<=D0 拒收概率恒 0。方向统计动作是受约束的风险项，允许非零。
    if scenario == "R":
        accept_above = all(
            ev.accept_probability == 0 for ev in curve[d1:]
        )
        check("factual_accept_zero_risk_budget", accept_above, "R: D>=D1 无接收")
        check("factual_reject_zero_risk_budget", True, "R: D<=D0 拒收为统计拒收")
    else:
        reject_below = all(
            ev.reject_probability == 0 for ev in curve[: d0 + 1]
        )
        check("factual_reject_zero_risk_budget", reject_below, "A: D<=D0 无拒收")
        check("factual_accept_zero_risk_budget", True, "A: D>=D1 接收为统计接收")

    # C3: 边界状态攻击
    if n >= 2:
        actions = actions_from_thresholds(n, scenario, thresholds)
        for t in range(1, n):
            for x in range(t + 1):
                factual_accept = factual_accept_at(t, x, n, d0)
                factual_reject = factual_reject_at(t, x, d1)
                action = actions[(t, x)]
                if factual_accept and action != ACTION_ACCEPT:
                    check("factual_accept_forces_accept", False, f"({t},{x})")
                elif factual_reject and action != ACTION_REJECT:
                    check("factual_reject_forces_reject", False, f"({t},{x})")
    else:
        check("boundary_state_attack", True, "N=1 无中间状态")

    # C4: 目标侧/风险侧最坏点与限额（assert_scenario_metrics 内部强校验）
    try:
        risk, target_asn = assert_scenario_metrics(n, scenario, thresholds)
        check("scenario_metrics_assertions", True, f"risk={risk}, target_asn={target_asn}")
    except AssertionError as exc:
        check("scenario_metrics_assertions", False, str(exc))
        return checks

    # C5: 阈值域（无与事实边界重复的编码）
    domain_ok = True
    for t, threshold in enumerate(thresholds, start=1):
        if scenario == "R":
            if threshold != t + 1 and not (0 <= threshold <= min(t, d0)):
                domain_ok = False
        else:
            if threshold != -1 and not (
                max(0, t - (n - d0) + 1) <= threshold <= min(t, d0)
            ):
                domain_ok = False
    check("threshold_domain", domain_ok, str(thresholds))

    # C6: 全 D 曲线非平凡事实停止（对 N>=10 至少一侧出现事实停止节省）
    if n >= 10:
        factual_saving = any(
            ev.asn < n for ev in curve
        )
        check("factual_stops_reduce_asn", factual_saving, "至少一个 D 的 ASN 小于全检 n")
    else:
        check("factual_stops_reduce_asn", True, "小 N 结构夹具")

    return checks


def main() -> None:
    parser = argparse.ArgumentParser(description="问题一完整动作空间S5验收")
    parser.add_argument(
        "--n-list",
        default=",".join(map(str, DEFAULT_N_VALUES)),
        help="逗号分隔的验收N，默认覆盖S4第6节全部结构夹具",
    )
    args = parser.parse_args()
    n_values = parse_n_values(args.n_list)

    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    results_payload = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    closure_payload = json.loads(CLOSURE_PATH.read_text(encoding="utf-8"))
    if results_payload["input_identity"]["specification_sha256"] != sha256(SPEC_PATH):
        raise AssertionError("S5主结果引用的S4规格哈希已经失效")
    if closure_payload["input_identity"]["specification_sha256"] != sha256(SPEC_PATH):
        raise AssertionError("S5闭合结果引用的S4规格哈希已经失效")

    results_by_n = {int(record["N"]): record for record in results_payload["results"]}
    closure_by_n = {int(record["N"]): record for record in closure_payload["results"]}

    checks: list[dict[str, object]] = []
    for n in n_values:
        if n not in results_by_n:
            raise ValueError(f"S5主结果缺少N={n}")
        source = results_by_n[n]
        closure = closure_by_n.get(n)
        for scenario in ("R", "A"):
            thresholds = tuple(
                int(item["threshold"])
                for item in source["scenarios"][scenario]["thresholds"]
            )
            checks.extend(run_acceptance(n, scenario, thresholds))
            if closure is not None:
                closure_thresholds = tuple(
                    int(item["threshold"])
                    for item in closure["scenarios"][scenario]["thresholds"]
                )
                closure_asn = Fraction(
                    int(closure["scenarios"][scenario]["ASN_upper_bound"]["numerator"]),
                    int(closure["scenarios"][scenario]["ASN_upper_bound"]["denominator"]),
                )
                source_asn = Fraction(
                    int(source["scenarios"][scenario]["worst_target_ASN_upper_bound"]["numerator"]),
                    int(source["scenarios"][scenario]["worst_target_ASN_upper_bound"]["denominator"]),
                )
                if closure_thresholds != thresholds and closure_asn > source_asn:
                    checks.append({
                        "check": "closure_does_not_worsen_selection",
                        "pass": False,
                        "detail": f"N={n} {scenario} 闭合候选ASN劣于主结果",
                    })

    passed = sum(1 for item in checks if item["pass"])
    total = len(checks)
    payload = {
        "schema_version": "1.0",
        "artifact_status": "s5_same_source_acceptance",
        "claim_status": "all_same_source_acceptance_checks_passed" if passed == total else "acceptance_failures_present",
        "producer": "src/q1/04_acceptance.py",
        "consumers": [
            "future S6 independent verifier",
            "planning/analysis/2026-08-25_q1_s5_complete_action_implementation.md",
        ],
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "input_identity": {
            "results_path": str(RESULTS_PATH.relative_to(PROJECT_ROOT)),
            "results_sha256": sha256(RESULTS_PATH),
            "closure_path": str(CLOSURE_PATH.relative_to(PROJECT_ROOT)),
            "closure_sha256": sha256(CLOSURE_PATH),
            "specification_path": str(SPEC_PATH.relative_to(PROJECT_ROOT)),
            "specification_sha256": sha256(SPEC_PATH),
            "n_values": list(n_values),
        },
        "n_values": list(n_values),
        "check_count": total,
        "passed_count": passed,
        "checks": checks,
        "unresolved": [
            "same-source acceptance is not S6 independent verification",
            "fixture N values are not an official or user-selected business batch size",
        ],
    }
    OUTPUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s5_acceptance_run_identity",
        "producer": "src/q1/04_acceptance.py",
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT)), *sys.argv[1:]],
        "environment": {"python": sys.version, "platform": platform.platform()},
        "parameters": {"n_values": list(n_values)},
        "inputs": {
            str(SPEC_PATH.relative_to(PROJECT_ROOT)): sha256(SPEC_PATH),
            str(RESULTS_PATH.relative_to(PROJECT_ROOT)): sha256(RESULTS_PATH),
            str(CLOSURE_PATH.relative_to(PROJECT_ROOT)): sha256(CLOSURE_PATH),
        },
        "sources": {
            str(CORE_PATH.relative_to(PROJECT_ROOT)): sha256(CORE_PATH),
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
        },
        "outputs": {
            str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH),
        },
        "claim_boundary": "This manifest identifies an S5 same-source acceptance run; it does not provide S6 independent verification.",
    }
    (PROJECT_ROOT / "output/q1/s5_acceptance_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "output": str(OUTPUT_PATH),
        "n_values": list(n_values),
        "passed": passed,
        "total": total,
        "claim_status": payload["claim_status"],
    }, ensure_ascii=False))
    if passed != total:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
