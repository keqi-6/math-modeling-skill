#!/usr/bin/env python3
"""独立复核第3步离散探索结果。

# 输入: modeling_dataset.csv, cleaned_attachment2.csv, output/eda/*
# 输出: output/eda/verification.json
# 职责: 不调用主EDA脚本，复算配对变化、排名、Pareto、时间变化与产物哈希。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "output" / "data_audit" / "tables"
OUT = ROOT / "output" / "eda"
TABLES = OUT / "tables"


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    data = pd.read_csv(AUDIT / "modeling_dataset.csv")
    time = pd.read_csv(AUDIT / "cleaned_attachment2.csv")
    paired = pd.read_csv(TABLES / "common_temperature_paired_changes.csv")
    ranks = pd.read_csv(TABLES / "rank_correlations_common_temperatures.csv")
    pareto = pd.read_csv(TABLES / "pareto_by_temperature.csv")
    time_summary = pd.read_csv(TABLES / "attachment2_change_summary.csv")
    manifest = pd.read_csv(OUT / "artifact_manifest.csv")
    results = []

    def add(name: str, passed: bool, observed: object, expected: object) -> None:
        results.append({"check": name, "passed": bool(passed),
                        "observed": observed, "expected": expected})

    add("正式接口记录与组合数",
        len(data) == 114 and data.catalyst_id.nunique() == 21,
        {"records": len(data), "combinations": int(data.catalyst_id.nunique())},
        {"records": 114, "combinations": 21})
    add("温度域",
        sorted(data.temperature_c.unique().tolist()) == [250, 275, 300, 325, 350, 400, 450],
        sorted(data.temperature_c.unique().tolist()), [250, 275, 300, 325, 350, 400, 450])
    add("全覆盖配对均为21组", set(paired.pair_count) == {21},
        sorted(paired.pair_count.unique().tolist()), [21])

    direct_changes = []
    for left, right in [(250, 275), (275, 300), (300, 350)]:
        x = data[data.temperature_c == left].set_index("catalyst_id")
        y = data[data.temperature_c == right].set_index("catalyst_id")
        direct_changes.append(int(((y.c4_yield_pct - x.c4_yield_pct) > 0).sum()))
    recorded = paired[paired.response == "c4_yield_pct"].positive_count.tolist()
    add("三组相邻温度条件中较高温度对应较高收率的数量", direct_changes == recorded == [21, 21, 21],
        {"direct": direct_changes, "recorded": recorded}, [21, 21, 21])

    recomputed_rank = (
        data[data.temperature_c.isin([250, 275, 300, 350])]
        .pivot(index="catalyst_id", columns="temperature_c", values="c4_yield_pct")
    )
    expected_rank = recomputed_rank[250].corr(recomputed_rank[350], method="spearman")
    stored_rank = ranks[
        (ranks.response == "c4_yield_pct")
        & (ranks.temperature_left_c == 250)
        & (ranks.temperature_right_c == 350)
    ].spearman_rank_correlation.iloc[0]
    add("250与350℃收率排名相关", abs(expected_rank - stored_rank) < 1e-12,
        float(stored_rank), float(expected_rank))

    violations = 0
    for temperature, group in pareto.groupby("temperature_c"):
        for row in group[group.pareto_nondominated].itertuples():
            violations += int(((
                group.ethanol_conversion_pct >= row.ethanol_conversion_pct
            ) & (
                group.c4_selectivity_pct >= row.c4_selectivity_pct
            ) & ((
                group.ethanol_conversion_pct > row.ethanol_conversion_pct
            ) | (
                group.c4_selectivity_pct > row.c4_selectivity_pct
            ))).any())
    add("Pareto标记无被支配点", violations == 0, violations, 0)

    first, last = time.iloc[0], time.iloc[-1]
    stored_time = time_summary.set_index("response")
    time_errors = []
    for response in ["ethanol_conversion_pct", "c4_selectivity_pct", "c4_yield_pct"]:
        time_errors.append(abs(
            (last[response] - first[response])
            - stored_time.loc[response, "absolute_change_pct_point"]
        ))
    add("附件2首末变化独立复算", max(time_errors) < 1e-12,
        float(max(time_errors)), "< 1e-12")

    missing, bad_hash = [], []
    for row in manifest.itertuples(index=False):
        path = ROOT / row.path
        if not path.is_file():
            missing.append(row.path)
        elif digest(path) != row.sha256:
            bad_hash.append(row.path)
    add("产物路径完整", not missing, missing, [])
    add("产物哈希一致", not bad_hash, bad_hash, [])
    add("当前图形12个", len(list((OUT / "figures").glob("*"))) == 12,
        len(list((OUT / "figures").glob("*"))), 12)

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "verifier": "src/eda/02_verify_eda.py",
        "independence": "未导入主EDA脚本",
        "checks": results, "passed_count": sum(x["passed"] for x in results),
        "check_count": len(results), "all_passed": all(x["passed"] for x in results),
    }
    (OUT / "verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if not report["all_passed"]:
        raise SystemExit(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps({"status": "ok", "passed": report["passed_count"],
                      "total": report["check_count"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
