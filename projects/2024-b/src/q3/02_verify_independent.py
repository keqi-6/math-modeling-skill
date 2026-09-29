#!/usr/bin/env python3
"""问题三S6独立验证器。

输入：S2批准参数接口、S5压缩候选账本与汇总结果。
输出：output/q3/s6_independent_verification.json 和对应运行清单。
职责：不导入主求解核心，独立重建25个节点率情形下的65536策略、硬门、精确
期望、成本与排序；同时执行父失败后相关性反例、非吸收闭类、订单流量不变量和
逐节点次品率敏感性等V3结构检查。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import re
import sys
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path


F = Fraction
ROOT = Path(__file__).resolve().parents[2]
S2 = ROOT / "planning/analysis/2026-08-24_q3_s2_assessment.md"
S5 = ROOT / "output/q3/s5_candidates.jsonl.gz"
S5_SUMMARY = ROOT / "output/q3/s5_results.json"
OUT = ROOT / "output/q3/s6_independent_verification.json"
MANIFEST = ROOT / "output/q3/s6_independent_verification_manifest.json"

PARTS = tuple(f"P{i}" for i in range(1, 9))
SEMIS = ("S1", "S2", "S3")
ASSEMBLIES = SEMIS + ("F",)
KIDS = {"S1": ("P1", "P2", "P3"), "S2": ("P4", "P5", "P6"), "S3": ("P7", "P8")}
EVENTS = (
    *(f"purchase_{x}" for x in PARTS),
    *(f"inspect_{x}" for x in PARTS + ASSEMBLIES),
    *(f"assemble_{x}" for x in ASSEMBLIES),
    *(f"disassemble_{x}" for x in ASSEMBLIES),
    "root_attempts", "market_bad_products_and_exchanges", "atomic_steps",
)


def frac(value: str | int | F) -> F:
    return value if isinstance(value, F) else F(value)


def ftext(value: F) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def blank() -> dict[str, F]:
    return {name: F(0) for name in EVENTS}


def plus(*vectors: dict[str, F]) -> dict[str, F]:
    out = blank()
    for vector in vectors:
        for name in EVENTS:
            out[name] += vector[name]
    return out


def times(vector: dict[str, F], factor: F) -> dict[str, F]:
    return {name: value * factor for name, value in vector.items()}


def actions(**values: F | int) -> dict[str, F]:
    out = blank()
    for name, value in values.items():
        out[name] += F(value)
        out["atomic_steps"] += F(value)
    return out


def read_input() -> dict[str, object]:
    text = S2.read_text(encoding="utf-8")
    parts = re.findall(
        r"^\|\s*([1-8])\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*$",
        text, re.MULTILINE,
    )
    nodes = re.findall(
        r"^\|\s*(半成品[123]|最终成品)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*([0-9.]+)\s*\|\s*$",
        text, re.MULTILINE,
    )
    market = re.search(r"market_price=([0-9.]+).*?exchange_loss=([0-9.]+)", text, re.DOTALL)
    if len(parts) != 8 or len(nodes) != 4 or market is None:
        raise AssertionError("独立解析未获得8个零件、4个装配节点和2个市场字段")
    names = {"半成品1": "S1", "半成品2": "S2", "半成品3": "S3", "最终成品": "F"}
    data = {"q": {}, "buy": {}, "inspect": {}, "assemble": {}, "disassemble": {}}
    for number, q, buy, inspect in parts:
        node = f"P{number}"
        data["q"][node] = F(q); data["buy"][node] = F(buy); data["inspect"][node] = F(inspect)
    for raw, q, assemble, inspect, disassemble in nodes:
        node = names[raw]
        data["q"][node] = F(q); data["assemble"][node] = F(assemble)
        data["inspect"][node] = F(inspect); data["disassemble"][node] = F(disassemble)
    data["price"] = F(market.group(1)); data["exchange"] = F(market.group(2))
    return data


def decode(key: str) -> dict[str, object]:
    if len(key) != 16 or set(key) - {"0", "1"}:
        raise AssertionError(key)
    b = tuple(map(int, key))
    return {
        "leaf_i": dict(zip(PARTS, b[:8])), "semi_i": dict(zip(SEMIS, b[8:11])),
        "final_i": b[11], "semi_d": dict(zip(SEMIS, b[12:15])), "final_d": b[15],
    }


def semi_empty(
    semi: str,
    policy: dict[str, object],
    rates: dict[str, F],
) -> tuple[bool, F | None, dict[str, F] | None]:
    leaf_i = policy["leaf_i"]; i_s = policy["semi_i"][semi]; d_s = policy["semi_d"][semi]
    semi_good = 1 - rates[semi]
    if i_s and d_s and any(
        not leaf_i[leaf] and rates[leaf] > 0 for leaf in KIDS[semi]
    ):
        return False, None, None
    initial = blank(); child_good = F(1)
    for leaf in KIDS[semi]:
        leaf_good = 1 - rates[leaf]
        if leaf_i[leaf]:
            initial = plus(initial, actions(**{
                f"purchase_{leaf}": 1/leaf_good,
                f"inspect_{leaf}": 1/leaf_good,
            }))
        else:
            initial = plus(initial, actions(**{f"purchase_{leaf}": 1})); child_good *= leaf_good
    initial = plus(initial, actions(**{f"assemble_{semi}": 1}))
    success = child_good * semi_good
    if not i_s:
        return True, success, initial
    initial = plus(initial, actions(**{f"inspect_{semi}": 1}))
    if not d_s:
        return True, F(1), times(initial, 1/success)
    retained = blank()
    for leaf in KIDS[semi]:
        retained = plus(retained, actions(**{f"inspect_{leaf}": 1}))
    retained = plus(retained, actions(**{f"assemble_{semi}": 1, f"inspect_{semi}": 1}))
    retained_value = plus(
        times(retained, 1/semi_good),
        times(actions(**{f"disassemble_{semi}": 1}), rates[semi]/semi_good),
    )
    total = plus(
        initial,
        times(plus(actions(**{f"disassemble_{semi}": 1}), retained_value), rates[semi]),
    )
    return True, F(1), total


def attempt(
    policy: dict[str, object],
    rates: dict[str, F],
    start_good: bool,
    cache: dict[tuple[object, ...], tuple[bool, F | None, dict[str, F] | None]],
) -> tuple[bool, F | None, dict[str, F] | None]:
    local = blank(); p_good = F(1)
    for semi in SEMIS:
        key = (
            semi,
            tuple(policy["leaf_i"][leaf] for leaf in KIDS[semi]),
            policy["semi_i"][semi],
            policy["semi_d"][semi],
            tuple(rates[node] for node in KIDS[semi] + (semi,)),
        )
        if key not in cache:
            cache[key] = semi_empty(semi, policy, rates)
        feasible, probability, counts = cache[key]
        if not feasible:
            return False, None, None
        if start_good:
            counts = actions(**({f"inspect_{semi}": 1} if policy["semi_i"][semi] else {}))
            probability = F(1)
        local = plus(local, counts); p_good *= probability
    success = p_good * (1-rates["F"])
    root = {"assemble_F": 1, "root_attempts": 1}
    if policy["final_i"]: root["inspect_F"] = 1
    common = plus(local, actions(**root)); fail = 1-success
    extras = blank()
    if policy["final_d"]: extras = plus(extras, actions(disassemble_F=1))
    if not policy["final_i"]: extras = plus(extras, actions(market_bad_products_and_exchanges=1))
    return True, success, plus(common, times(extras, fail))


def evaluate(
    key: str,
    rates: dict[str, F],
    data: dict[str, object],
    cache: dict[tuple[object, ...], tuple[bool, F | None, dict[str, F] | None]],
) -> dict[str, object]:
    policy = decode(key)
    positive_rates = [rate for rate in rates.values() if rate > 0]
    trap_lower_bound = min(positive_rates, default=F(0))
    if policy["final_d"] and not all(policy["semi_i"].values()):
        return {"feasible": False, "reason": "persistent_bad_uninspected_semi_closed_class",
                "nonabsorption_lb": trap_lower_bound, "absorption_ub": 1-trap_lower_bound}
    ok, s0, b0 = attempt(policy, rates, False, cache)
    if not ok:
        return {"feasible": False, "reason": "persistent_bad_uninspected_leaf_closed_class",
                "nonabsorption_lb": trap_lower_bound, "absorption_ub": 1-trap_lower_bound}
    if not policy["final_d"]:
        total = times(b0, 1/s0)
    else:
        ok, sg, bg = attempt(policy, rates, True, cache)
        total = plus(b0, times(times(bg, 1/sg), 1-s0))
    cost = F(0)
    for leaf in PARTS: cost += data["buy"][leaf]*total[f"purchase_{leaf}"]
    for node in PARTS+ASSEMBLIES: cost += data["inspect"][node]*total[f"inspect_{node}"]
    for node in ASSEMBLIES:
        cost += data["assemble"][node]*total[f"assemble_{node}"]
        cost += data["disassemble"][node]*total[f"disassemble_{node}"]
    cost += data["exchange"]*total["market_bad_products_and_exchanges"]
    return {"feasible": True, "events": total, "cost": cost, "profit": data["price"]-cost,
            "first_success": s0, "market_hit": F(0) if policy["final_i"] else 1-s0}


def scenarios(data: dict[str, object]) -> dict[str, dict[str, F]]:
    baseline = dict(data["q"])
    answer = {"NOMINAL": baseline}
    for node in PARTS + ASSEMBLIES:
        for suffix, rate in (("LOW", F(1,20)), ("HIGH", F(3,20))):
            changed = dict(baseline); changed[node] = rate
            answer[f"{node}_{suffix}"] = changed
    return answer


def parse_events(record: dict[str, object]) -> dict[str, F]:
    return {name: F(record["expected_events"][name]) for name in EVENTS}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify() -> dict[str, object]:
    data = read_input(); rate_scenarios = scenarios(data); comparisons = 0; field_checks = 0
    counts = {name: {"candidate":0,"feasible":0,"infeasible":0} for name in rate_scenarios}
    best: dict[str, tuple[F | None, list[str]]] = {name:(None,[]) for name in rate_scenarios}
    flow_checks = 0; cache = {}
    with gzip.open(S5, "rt", encoding="utf-8") as stream:
        for line in stream:
            record = json.loads(line); name = record["scenario"]; key = record["policy_id"]
            result = evaluate(key, rate_scenarios[name], data, cache); counts[name]["candidate"] += 1; comparisons += 1
            if bool(record["feasible"]) != result["feasible"]: raise AssertionError((name,key,"gate"))
            field_checks += 1
            if not result["feasible"]:
                counts[name]["infeasible"] += 1
                if F(record["nonabsorption_probability_lower_bound"]) != result["nonabsorption_lb"]: raise AssertionError((name,key,"trap"))
                field_checks += 1; continue
            counts[name]["feasible"] += 1
            frozen_events = parse_events(record)
            for event in EVENTS:
                if frozen_events[event] != result["events"][event]: raise AssertionError((name,key,event))
                field_checks += 1
            for frozen, live in (("total_cost","cost"),("profit","profit"),
                                 ("first_root_attempt_success_probability","first_success"),
                                 ("at_least_one_market_bad_probability","market_hit")):
                if F(record[frozen]) != result[live]: raise AssertionError((name,key,frozen))
                field_checks += 1
            p = decode(key); events = result["events"]
            if events["assemble_F"] != events["root_attempts"]: raise AssertionError("root flow")
            if not p["final_i"] and events["root_attempts"]-events["market_bad_products_and_exchanges"] != 1: raise AssertionError("market flow")
            if p["final_i"] and (events["inspect_F"] != events["root_attempts"] or events["market_bad_products_and_exchanges"]): raise AssertionError("inspection flow")
            flow_checks += 1
            value, keys = best[name]
            if value is None or result["profit"] > value: best[name] = (result["profit"],[key])
            elif result["profit"] == value: keys.append(key)
    for name in rate_scenarios:
        if counts[name] != {"candidate":65536,"feasible":17060,"infeasible":48476}: raise AssertionError(counts[name])

    frozen_summary = json.loads(S5_SUMMARY.read_text(encoding="utf-8"))
    for name,(value,keys) in best.items():
        summary = frozen_summary["scenarios"][name]
        if ftext(value) != summary["best_profit_exact"] or keys != summary["best_policy_ids"]: raise AssertionError((name,"ranking"))

    # V3-A：父件失败会诱导子件后验相关，不能把两个边际重新相乘。
    q = F(1,10); g = 1-q; fail = 1-g**3
    joint_gg = g*g*q/fail
    marginal_g = g*((1-g)+g*q)/fail
    posterior_covariance = joint_gg - marginal_g*marginal_g
    if posterior_covariance == 0: raise AssertionError("posterior independence false negative")

    nominal_value, nominal_keys = best["NOMINAL"]
    sensitivity = []
    for name, rates in rate_scenarios.items():
        value, keys = best[name]
        changed = [node for node in PARTS + ASSEMBLIES if rates[node] != data["q"][node]]
        if name == "NOMINAL":
            if changed: raise AssertionError("nominal scenario changed")
            node = None; direction = "nominal"; changed_rate = None
        else:
            if len(changed) != 1: raise AssertionError((name, "not OAT"))
            node = changed[0]; changed_rate = rates[node]
            direction = "low" if changed_rate == F(1,20) else "high"
        sensitivity.append({
            "scenario": name,
            "changed_node": node,
            "direction": direction,
            "changed_rate_exact": None if changed_rate is None else ftext(changed_rate),
            "best_policy_ids": keys,
            "best_profit_exact": ftext(value),
            "profit_change_from_nominal_exact": ftext(value - nominal_value),
            "policy_switch_from_nominal": keys != nominal_keys,
        })

    best_nominal = evaluate("1111111111101111", rate_scenarios["NOMINAL"], data, cache)
    return {
        "status": "pass",
        "producer_independence": {"imports_primary_core": False, "reads_primary_source": False,
                                  "method": "independent_dict_reward_renewal_reconstruction"},
        "solution_verification": {
            "V1": {"status":"pass","candidate_records_compared":comparisons,
                   "exact_field_checks":field_checks,"feasible_flow_invariants":flow_checks,
                   "scenario_counts":counts,
                   "best":{name:{"profit_exact":ftext(value),"policy_ids":keys} for name,(value,keys) in best.items()}},
            "V2": {"status":"not_triggered","reason":"all probabilities, renewals, costs and rankings are exact Fractions; the candidate domain is exhaustively enumerated without tolerance, iteration or random search"}
        },
        "model_examination": {
            "V3": {"status":"pass","tests":[
                {"id":"posterior_dependence","claim":"拆回对象必须保留父失败条件下的联合质量信息",
                 "failure_risk":"把条件后验边际重新相乘会错误恢复独立性",
                 "relation":"Cov(1_child1_good,1_child2_good | parent_bad) != 0",
                 "criterion":"精确条件协方差非零","result":{"joint_GG":ftext(joint_gg),"marginal_G":ftext(marginal_g),"covariance":ftext(posterior_covariance)},
                 "boundary":"two-child analytic fixture; it proves the aggregation risk, not arbitrary factory dependence"},
                {"id":"persistent_object_counterexample","claim":"不可终止策略必须在利润比较前排除",
                 "failure_risk":"有限轮截断会给永久坏件回流策略伪造有限利润",
                 "relation":"P(nonabsorption) >= marginal primitive defect rate = 1/10",
                 "criterion":"存在正概率可达且不含成功态的闭类","result":"pass; all 48476 rejected policies per scenario carry the scenario-specific conservative lower bound min_j(q_j), equal to 1/20 or 1/10 here",
                 "boundary":"the 25 stated node-rate scenarios and fixed strategy domain"},
                {"id":"order_flow_conservation","claim":"每个完成订单只吸收一次并只计一次售价",
                 "failure_risk":"调换轮次重复收入或根尝试漏计",
                 "relation":"E[root attempts]-E[market bad]=1 when final inspection is off; E[assemble_F]=E[root attempts] always",
                 "criterion":"all feasible policy-scenario records satisfy the exact identities","result":f"pass; {flow_checks} feasible records",
                 "boundary":"event-flow necessity, not real production validation"},
                {"id":"node_rate_oat_reoptimization","claim":"问题三决策对题定12个节点次品率的局部敏感性已直接检验",
                 "failure_risk":"单个节点次品率估计偏差可能改变最优策略或利润",
                 "relation":"one node at a time: q_j in {0.05,0.15}, all other q=0.10; re-optimize all 65536 policies",
                 "criterion":"report all 25 scenarios, exact profit changes and every exact policy switch","result":sensitivity,
                 "boundary":"discrete plus/minus five percentage-point OAT perturbations; not a joint confidence region or a proof for simultaneous changes"}
            ]},
            "V4": {"status":"not_triggered","reason":"the official problem provides no factory history, joint-quality observations, inspection-error study, or out-of-sample profit comparator","unconfirmed_domain":"real factory defect dependence, inspection accuracy, reuse practice, and realized profit"}
        },
        "uncertainty_register": {
            "input_parameter_uncertainty":"locally examined by 24 OAT perturbations; problem four owns sampling-based rate estimation and joint uncertainty",
            "numerical_approximation":"not_triggered; exact rational arithmetic",
            "optimization_uncertainty":"not_triggered; complete 65536 enumeration",
            "model_form_dependence":"not varied; the task-stated independent node-rate model is held fixed while its 12 rates are perturbed"
        },
        "headline_independent_fixture": {"policy_id":"1111111111101111","nominal_cost":ftext(best_nominal["cost"]),"nominal_profit":ftext(best_nominal["profit"])}
    }


def main() -> int:
    start = datetime.now(timezone.utc); result = verify()
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    end = datetime.now(timezone.utc)
    manifest = {"command":"python3 src/q3/02_verify_independent.py","started_utc":start.isoformat(),
                "finished_utc":end.isoformat(),"elapsed_seconds":(end-start).total_seconds(),
                "python":sys.version,"platform":platform.platform(),"random_seed":None,
                "inputs_sha256":{p.name:sha256(p) for p in (S2,S5,S5_SUMMARY)},
                "source_sha256":sha256(Path(__file__)),"outputs_sha256":{OUT.name:sha256(OUT)}}
    MANIFEST.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":result["status"],"elapsed_seconds":manifest["elapsed_seconds"],
                      "records":result["solution_verification"]["V1"]["candidate_records_compared"],
                      "sensitivity_scenarios":len(result["model_examination"]["V3"]["tests"][3]["result"])},ensure_ascii=False,indent=2))
    return 0


if __name__ == "__main__": raise SystemExit(main())
