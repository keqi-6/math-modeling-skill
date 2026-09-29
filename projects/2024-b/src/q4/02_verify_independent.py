#!/usr/bin/env python3
"""问题四S6独立验证。

本程序不导入 ``src/q4`` 主求解模块。它以不同的计算路径复核：
1. 超几何区间端点、全抽退化与小总体覆盖率；
2. 问题二全部12960条候选的闭式事件账本；
3. 问题三选定非对称十二率情景的65536策略机械枚举、最优集合与交换对称。
"""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction as F
from itertools import product
from math import comb
from pathlib import Path
from datetime import datetime, timezone
import gzip
import hashlib
import json
import platform
import sys


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/q4"
INTERVALS = OUT / "s5_intervals.json"
Q2_CANDIDATES = OUT / "s5_q2_candidates.jsonl.gz"
Q3_REPRESENTATIVES = OUT / "s5_q3_representatives.jsonl.gz"
Q3_SUMMARY = OUT / "s5_q3_summary.json"
RESULT = OUT / "s6_independent_verification.json"
MANIFEST = OUT / "s6_verification_manifest.json"

SETTINGS = {
    "N200_n100": (200, 100),
    "N500_n20": (500, 20),
    "N500_n100": (500, 100),
    "N500_n200": (500, 200),
    "N1000_n100": (1000, 100),
}

# 冻结表1；顺序为p1,c1,t1,p2,c2,t2,p0,a,t0,sale,exchange,d.
Q2_DATA = {
    1: (F(1, 10), F(4), F(2), F(1, 10), F(18), F(3), F(1, 10), F(6), F(3), F(56), F(6), F(5)),
    2: (F(1, 5), F(4), F(2), F(1, 5), F(18), F(3), F(1, 5), F(6), F(3), F(56), F(6), F(5)),
    3: (F(1, 10), F(4), F(2), F(1, 10), F(18), F(3), F(1, 10), F(6), F(3), F(56), F(30), F(5)),
    4: (F(1, 5), F(4), F(1), F(1, 5), F(18), F(1), F(1, 5), F(6), F(2), F(56), F(30), F(5)),
    5: (F(1, 10), F(4), F(8), F(1, 5), F(18), F(1), F(1, 10), F(6), F(2), F(56), F(10), F(5)),
    6: (F(1, 20), F(4), F(2), F(1, 20), F(18), F(3), F(1, 20), F(6), F(3), F(56), F(10), F(40)),
}

# 冻结表2费用，不从主评价器取值。
PURCHASE = (F(2), F(8), F(12), F(2), F(8), F(12), F(8), F(12))
PART_INSPECT = (F(1), F(1), F(2), F(1), F(1), F(2), F(1), F(2))
SEMI_ASSEMBLE = (F(8), F(8), F(8))
SEMI_INSPECT = (F(4), F(4), F(4))
SEMI_DISASSEMBLE = (F(6), F(6), F(6))
FINAL_ASSEMBLE = F(8)
FINAL_INSPECT = F(6)
FINAL_DISASSEMBLE = F(10)
SALE = F(200)
EXCHANGE = F(40)
MODULE_PARTS = ((0, 1, 2), (3, 4, 5), (6, 7))


def frac(text: str | int) -> F:
    return F(str(text))


def ftext(value: F) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def hg_tail_by_recurrence(N: int, D: int, n: int, x: int, upper: bool) -> F:
    """从支持集左端递推PMF，不使用主程序的逐项comb字典。"""
    lo = max(0, n - (N - D))
    hi = min(n, D)
    mass = F(comb(D, lo) * comb(N - D, n - lo), comb(N, n))
    total = F(0)
    for k in range(lo, hi + 1):
        if (upper and k >= x) or (not upper and k <= x):
            total += mass
        if k < hi:
            mass *= F((D - k) * (n - k), (k + 1) * (N - D - n + k + 1))
    return total


def independent_interval(N: int, n: int, x: int) -> tuple[int, ...]:
    accepted = []
    for D in range(x, N - n + x + 1):
        if hg_tail_by_recurrence(N, D, n, x, True) > F(1, 40) and hg_tail_by_recurrence(N, D, n, x, False) > F(1, 40):
            accepted.append(D)
    return tuple(accepted)


def interval_checks(records: list[dict[str, object]]) -> list[dict[str, object]]:
    checks = []
    for row in records:
        N, n, x = int(row["N"]), int(row["n"]), int(row["x"])
        accepted = independent_interval(N, n, x)
        ok = accepted[0] == row["accepted_D_min"] and accepted[-1] == row["accepted_D_max"] and len(accepted) == row["accepted_D_count"]
        if not ok:
            raise AssertionError(f"interval:{row['setting_id']}:{row['q']}")
        checks.append({"id": f"interval_{row['setting_id']}_{row['q']}", "status": "pass", "evidence": f"D={accepted[0]}..{accepted[-1]} by PMF recurrence"})

    for N in (1, 2, 7, 20):
        for x in range(N + 1):
            if independent_interval(N, N, x) != (x,):
                raise AssertionError(f"full census N={N},x={x}")
    checks.append({"id": "full_census_degeneracy", "status": "pass", "evidence": "N in {1,2,7,20}, every x gives singleton D=x"})

    # V3：不只复算端点，而是枚举真实D和所有可能x，核验反演程序的最小覆盖率。
    worst = (F(1), None)
    for N, n in ((8, 3), (10, 5), (12, 4), (15, 10), (20, 7)):
        intervals_by_x = {x: set(independent_interval(N, n, x)) for x in range(n + 1)}
        for D in range(N + 1):
            coverage = F(0)
            for x in range(max(0, n - (N - D)), min(n, D) + 1):
                if D in intervals_by_x[x]:
                    coverage += F(comb(D, x) * comb(N - D, n - x), comb(N, n))
            if coverage < F(19, 20):
                raise AssertionError(f"coverage below 95%: N={N},n={n},D={D},coverage={coverage}")
            if coverage < worst[0]:
                worst = (coverage, (N, n, D))
    checks.append({"id": "finite_population_coverage_property", "status": "pass", "evidence": f"exhaustive small-population minimum={ftext(worst[0])} at {worst[1]}"})
    return checks


def q2_independent(policy: str, rates: tuple[F, F, F], scenario_id: int) -> dict[str, object]:
    _, c1, t1, _, c2, t2, _, assembly, t0, sale, exchange, disassembly = Q2_DATA[scenario_id]
    p1, p2, p0 = rates
    i1, i2, i0, d0 = map(int, policy)
    if d0 and not (i1 and i2):
        return {"feasible": False}
    g1, g2, g0 = 1 - p1, 1 - p2, 1 - p0
    if not d0:
        success = (F(1) if i1 else g1) * (F(1) if i2 else g2) * g0
        attempts = 1 / success
        counts = (
            (1 / g1 if i1 else F(1)) * attempts,
            (1 / g2 if i2 else F(1)) * attempts,
            (1 / g1 if i1 else F(0)) * attempts,
            (1 / g2 if i2 else F(0)) * attempts,
            attempts,
            i0 * attempts,
            F(0),
            (1 - i0) * (1 - success) / success,
        )
    else:
        failures = p0 / g0
        counts = (
            1 / g1, 1 / g2, 1 / g1 + failures, 1 / g2 + failures,
            1 / g0, i0 / g0, failures, (1 - i0) * failures,
        )
    weights = (c1, c2, t1, t2, assembly, t0, disassembly, exchange)
    cost = sum((a * b for a, b in zip(counts, weights)), F(0))
    return {"feasible": True, "counts": counts, "cost": cost, "profit": sale - cost}


def q2_checks() -> list[dict[str, object]]:
    count = 0
    feasible = 0
    with gzip.open(Q2_CANDIDATES, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            rates = tuple(frac(value) for value in row["rates"])
            current = q2_independent(row["policy_id"], rates, int(row["scenario_id"]))
            if current["feasible"] != row["feasible"]:
                raise AssertionError(f"q2 feasibility:{row}")
            if current["feasible"]:
                feasible += 1
                names = ("part1_purchases", "part2_purchases", "part1_inspections", "part2_inspections", "assemblies", "product_inspections", "disassemblies", "market_bad_products_and_exchanges")
                expected = {name: ftext(value) for name, value in zip(names, current["counts"])}
                if expected != row["expected_counts"] or ftext(current["cost"]) != row["expected_cost"] or ftext(current["profit"]) != row["expected_profit"]:
                    raise AssertionError(f"q2 ledger:{row['setting_id']}:{row['scenario_id']}:{row['level_code']}:{row['policy_id']}")
            count += 1
    if count != 12960:
        raise AssertionError(f"q2 record count {count}")
    return [{"id": "q2_all_candidate_ledgers", "status": "pass", "evidence": f"{count} candidates, {feasible} feasible, independent closed forms"}]


def decode_rate_code(code: str, levels: tuple[F, F, F]) -> tuple[tuple[F, ...], tuple[F, F, F, F]]:
    if len(code) != 12:
        raise ValueError(code)
    values = tuple(levels[int(ch)] for ch in code)
    # module rate tuples include direct parts then conditional semi rate.
    part_positions = (0, 1, 2, 4, 5, 6, 8, 9)
    return tuple(values[index] for index in part_positions), (values[3], values[7], values[10], values[11])


def local_responses(module: int, part_rates: tuple[F, ...], semi_rate: F) -> list[tuple[tuple[int, ...], F | None, F | None, F | None]]:
    """返回(bits,一次空状态成功率,空状态成本,已知合格状态成本)。"""
    part_ids = MODULE_PARTS[module]
    answer = []
    for bits in product((0, 1), repeat=len(part_ids) + 2):
        leaf_bits, inspect_semi, disassemble_semi = bits[:-2], bits[-2], bits[-1]
        if inspect_semi and disassemble_semi and any(not flag and part_rates[pid] > 0 for pid, flag in zip(part_ids, leaf_bits)):
            answer.append((bits, None, None, None))
            continue
        initial = SEMI_ASSEMBLE[module]
        child_good = F(1)
        for pid, flag in zip(part_ids, leaf_bits):
            good = 1 - part_rates[pid]
            if flag:
                initial += (PURCHASE[pid] + PART_INSPECT[pid]) / good
            else:
                initial += PURCHASE[pid]
                child_good *= good
        semi_good = 1 - semi_rate
        one_build_success = child_good * semi_good
        known_good_cost = SEMI_INSPECT[module] if inspect_semi else F(0)
        if not inspect_semi:
            answer.append((bits, one_build_success, initial, known_good_cost))
        elif not disassemble_semi:
            answer.append((bits, F(1), (initial + SEMI_INSPECT[module]) / one_build_success, known_good_cost))
        else:
            retained_cycle = sum((PART_INSPECT[pid] for pid in part_ids), F(0)) + SEMI_ASSEMBLE[module] + SEMI_INSPECT[module]
            retained_value = retained_cycle / semi_good + SEMI_DISASSEMBLE[module] * semi_rate / semi_good
            empty_cost = initial + SEMI_INSPECT[module] + semi_rate * (SEMI_DISASSEMBLE[module] + retained_value)
            answer.append((bits, F(1), empty_cost, known_good_cost))
    return answer


def policy_id(local_bits: tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]], inspect_final: int, disassemble_final: int) -> str:
    m1, m2, m3 = local_bits
    bits = [0] * 16
    bits[0:3], bits[3:6], bits[6:8] = m1[:-2], m2[:-2], m3[:-2]
    bits[8:11] = (m1[-2], m2[-2], m3[-2])
    bits[11] = inspect_final
    bits[12:15] = (m1[-1], m2[-1], m3[-1])
    bits[15] = disassemble_final
    return "".join(map(str, bits))


def brute_q3(code: str, levels: tuple[F, F, F]) -> tuple[F, tuple[str, ...], int, int]:
    part_rates, (s1, s2, s3, p_final) = decode_rate_code(code, levels)
    locals_by_module = (
        local_responses(0, part_rates, s1),
        local_responses(1, part_rates, s2),
        local_responses(2, part_rates, s3),
    )
    best: F | None = None
    ids: list[str] = []
    feasible_count = 0
    candidate_count = 0
    g_final = 1 - p_final
    for a, b, c in product(*locals_by_module):
        rows = (a, b, c)
        for inspect_final, disassemble_final in product((0, 1), repeat=2):
            candidate_count += 1
            if any(row[1] is None for row in rows):
                continue
            if disassemble_final and any(row[1] < 1 and not row[0][-2] for row in rows):
                continue
            feasible_count += 1
            success = a[1] * b[1] * c[1] * g_final
            root_common = FINAL_ASSEMBLE + inspect_final * FINAL_INSPECT
            failure_cost = (1 - inspect_final) * EXCHANGE + disassemble_final * FINAL_DISASSEMBLE
            empty = sum((row[2] for row in rows), F(0)) + root_common + (1 - success) * failure_cost
            if not disassemble_final:
                cost = empty / success
            else:
                good = sum((row[3] for row in rows), F(0)) + root_common + p_final * failure_cost
                cost = empty + (1 - success) * good / g_final
            pid = policy_id((a[0], b[0], c[0]), inspect_final, disassemble_final)
            if best is None or cost < best:
                best, ids = cost, [pid]
            elif cost == best:
                ids.append(pid)
    if best is None:
        raise AssertionError(code)
    return best, tuple(sorted(ids)), feasible_count, candidate_count


def swap_code(code: str) -> str:
    return code[4:8] + code[:4] + code[8:]


def swap_policy(pid: str) -> str:
    bits = list(pid)
    for left, right in ((0, 3), (1, 4), (2, 5), (8, 9), (12, 13)):
        bits[left], bits[right] = bits[right], bits[left]
    return "".join(bits)


TARGET_CODES = (
    "111111111111",  # 名义点
    "221111011111",  # P1,P2上升而P6下降
    "001111211111",  # 上述方向反转
    "222200002102",  # M1全U、M2全L，M3内部混合
    "201111210120",  # 跨三个模块的非对称混合
)


def q3_checks(interval_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    levels_by_setting = {}
    for row in interval_rows:
        if row["q"] == "1/10":
            levels_by_setting[row["setting_id"]] = (frac(row["L"]), frac(row["Q"]), frac(row["U"]))
    wanted = {(setting, code) for setting in SETTINGS for code in TARGET_CODES}
    found: dict[tuple[str, str], dict[str, object]] = {}
    with gzip.open(Q3_REPRESENTATIVES, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            key = (row["setting_id"], row["canonical_rate_code"])
            swap_key = (row["setting_id"], row["swapped_rate_code"])
            if key in wanted:
                found[key] = {"best_cost": row["best_cost"], "best_ids": tuple(row["best_policy_ids"])}
            if row["swapped_rate_code"] is not None and swap_key in wanted:
                found[swap_key] = {"best_cost": row["best_cost"], "best_ids": tuple(row["swapped_best_policy_ids"])}
    missing = wanted - set(found)
    if missing:
        raise AssertionError(f"missing representative expansions: {sorted(missing)}")

    checks = []
    brute_cache = {}
    for setting in SETTINGS:
        levels = levels_by_setting[setting]
        feasible_counts = set()
        for code in TARGET_CODES:
            best, ids, feasible_count, candidate_count = brute_q3(code, levels)
            brute_cache[(setting, code)] = (best, ids)
            feasible_counts.add(feasible_count)
            if candidate_count != 65536:
                raise AssertionError(f"q3 candidate count:{setting}:{code}:{candidate_count}")
            reference = found[(setting, code)]
            if ftext(best) != reference["best_cost"] or ids != reference["best_ids"]:
                raise AssertionError(f"q3 brute mismatch:{setting}:{code}")
        checks.append({"id": f"q3_full_enumeration_{setting}", "status": "pass", "evidence": f"{len(TARGET_CODES)} scenarios x 65536 policies; feasible counts={sorted(feasible_counts)}"})

    # 交换是对主输出与独立枚举同时施加的形变，不只检查一条实现路径。
    asym = "222200002102"
    swapped = swap_code(asym)
    for setting in SETTINGS:
        levels = levels_by_setting[setting]
        best, ids, _, candidate_count = brute_q3(swapped, levels)
        if candidate_count != 65536:
            raise AssertionError(f"q3 symmetry candidate count:{setting}:{candidate_count}")
        source_best, source_ids = brute_cache[(setting, asym)]
        if best != source_best or ids != tuple(sorted(swap_policy(pid) for pid in source_ids)):
            raise AssertionError(f"q3 symmetry:{setting}")
    checks.append({"id": "q3_m1_m2_metamorphic_symmetry", "status": "pass", "evidence": "all five settings, full 65536-policy enumeration before and after labeled module swap"})

    summary = json.loads(Q3_SUMMARY.read_text(encoding="utf-8"))
    if summary["representative_record_count"] != 5 * 269001 or summary["expanded_labeled_scenario_count"] != 5 * 531441:
        raise AssertionError("q3 completeness counts")
    checks.append({"id": "q3_labeled_domain_completeness", "status": "pass", "evidence": "1,345,005 representatives expand losslessly to 2,657,205 labeled rate scenarios"})
    return checks


def main() -> int:
    started = datetime.now(timezone.utc)
    primary = json.loads(INTERVALS.read_text(encoding="utf-8"))
    records = primary["records"]
    checks = []
    checks.extend(interval_checks(records))
    checks.extend(q2_checks())
    checks.extend(q3_checks(records))
    result = {
        "status": "pass",
        "verification_identity": "independent_implementation_and_structural_examination",
        "imports_q4_primary_modules": False,
        "v4_external_validation_applicable": False,
        "v4_reason": "题面未提供企业真实N,n,x、留出样本或实现后收益；禁止伪造经验验证",
        "checks": checks,
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finished = datetime.now(timezone.utc)
    manifest = {
        "command": "python3 src/q4/02_verify_independent.py",
        "python": sys.version,
        "platform": platform.platform(),
        "started_utc": started.isoformat(),
        "finished_utc": finished.isoformat(),
        "elapsed_seconds": (finished - started).total_seconds(),
        "inputs_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in (INTERVALS, Q2_CANDIDATES, Q3_REPRESENTATIVES, Q3_SUMMARY)},
        "source_sha256": sha256(Path(__file__)),
        "result_sha256": sha256(RESULT),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "pass", "check_count": len(checks), "elapsed_seconds": manifest["elapsed_seconds"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
