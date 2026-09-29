#!/usr/bin/env python3
"""不导入主程序，独立复算第三问S5的D0实测基线。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q3" / "baseline"
TOL = 1e-10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    data = pd.read_csv(INPUT)
    saved = pd.read_csv(OUT / "scenario_summary.csv")
    rankings = pd.read_csv(OUT / "top10_observed_rankings.csv")
    checks = []

    formula = data["ethanol_conversion_pct"] * data["c4_selectivity_pct"] / 100.0
    formula_error = float((formula - data["c4_yield_pct"]).abs().max())
    checks.append({
        "check": "收率公式",
        "passed": bool(formula_error < TOL),
        "detail": f"max_abs_error={formula_error:.3e}",
    })

    domains = {
        "general": data,
        "strict_below_350": data[data["temperature_c"] < 350.0],
    }
    expected_counts = {"general": 114, "strict_below_350": 73}
    checks.append({
        "check": "两个情景候选数",
        "passed": bool(
            all(len(domains[key]) == value for key, value in expected_counts.items())
        ),
        "detail": str({key: len(value) for key, value in domains.items()}),
    })
    checks.append({
        "check": "严格低温约束",
        "passed": bool(
            (domains["strict_below_350"]["temperature_c"] < 350.0).all()
            and 350.0 not in domains["strict_below_350"]["temperature_c"].unique()
        ),
        "detail": str(
            sorted(
                float(value)
                for value in domains["strict_below_350"]["temperature_c"].unique()
            )
        ),
    })

    best_errors = []
    runner_errors = []
    lead_errors = []
    distinct_errors = []
    identity_ok = True
    ranking_ok = True
    for scenario, domain in domains.items():
        ordered = domain.sort_values(
            ["c4_yield_pct", "catalyst_id", "temperature_c"],
            ascending=[False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
        row = saved[saved["scenario"] == scenario].iloc[0]
        distinct = ordered[
            ordered["catalyst_id"] != ordered.iloc[0]["catalyst_id"]
        ].iloc[0]
        identity_ok &= (
            row["best_catalyst_id"] == ordered.iloc[0]["catalyst_id"]
            and abs(row["best_temperature_c"] - ordered.iloc[0]["temperature_c"]) < TOL
            and row["runner_up_catalyst_id"] == ordered.iloc[1]["catalyst_id"]
            and abs(row["runner_up_temperature_c"] - ordered.iloc[1]["temperature_c"]) < TOL
            and row["best_distinct_combination_id"] == distinct["catalyst_id"]
            and abs(
                row["best_distinct_combination_temperature_c"]
                - distinct["temperature_c"]
            )
            < TOL
        )
        best_errors.append(abs(row["best_c4_yield_pct"] - ordered.iloc[0]["c4_yield_pct"]))
        runner_errors.append(
            abs(row["runner_up_c4_yield_pct"] - ordered.iloc[1]["c4_yield_pct"])
        )
        lead_errors.append(
            abs(
                row["lead_over_runner_up_pct_point"]
                - (ordered.iloc[0]["c4_yield_pct"] - ordered.iloc[1]["c4_yield_pct"])
            )
        )
        distinct_errors.extend([
            abs(
                row["best_distinct_combination_c4_yield_pct"]
                - distinct["c4_yield_pct"]
            ),
            abs(
                row["lead_over_best_distinct_combination_pct_point"]
                - (
                    ordered.iloc[0]["c4_yield_pct"]
                    - distinct["c4_yield_pct"]
                )
            ),
        ])
        saved_top = rankings[rankings["scenario"] == scenario]
        ranking_ok &= (
            saved_top["rank"].tolist() == list(range(1, 11))
            and saved_top["catalyst_id"].tolist()
            == ordered.head(10)["catalyst_id"].tolist()
            and all(
                abs(left - right) < TOL
                for left, right in zip(
                    saved_top["c4_yield_pct"],
                    ordered.head(10)["c4_yield_pct"],
                )
            )
        )

    checks.append({
        "check": "最优与次优身份",
        "passed": bool(identity_ok),
    })
    checks.append({
        "check": "最优、次优和领先差距数值",
        "passed": bool(
            max(best_errors + runner_errors + lead_errors + distinct_errors) < TOL
        ),
        "detail": (
            "max_abs_error="
            f"{max(best_errors + runner_errors + lead_errors + distinct_errors):.3e}"
        ),
    })
    checks.append({
        "check": "前十排序",
        "passed": bool(ranking_ok),
    })
    checks.append({
        "check": "D0边界",
        "passed": bool(
            len(data) == 114
            and data["catalyst_id"].nunique() == 21
            and not data.duplicated(["catalyst_id", "temperature_c"]).any()
        ),
        "detail": "rows=114, combinations=21, duplicate_keys=0",
    })

    result = {
        "status": "s5_d0_baseline_independent_verification",
        "passed": bool(all(item["passed"] for item in checks)),
        "check_count": len(checks),
        "checks": checks,
        "note": "通过只证明D0枚举和输出一致，不批准D1、D2或最终推荐。",
    }
    verification_path = OUT / "verification.json"
    verification_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    artifact_paths = [
        INPUT,
        ROOT / "src" / "q3" / "01_observed_baseline.py",
        ROOT / "src" / "q3" / "02_verify_observed_baseline.py",
        OUT / "top10_observed_rankings.csv",
        OUT / "scenario_summary.csv",
        OUT / "summary.json",
        verification_path,
    ]
    pd.DataFrame([
        {
            "path": str(path.relative_to(ROOT)),
            "sha256": sha256(path),
        }
        for path in artifact_paths
    ]).to_csv(OUT / "artifact_manifest.csv", index=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
