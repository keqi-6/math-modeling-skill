#!/usr/bin/env python3
"""第三问S11独立验证：从清洁输入和冻结表逐项复算稳健性结论。

输入：清洁数据、S6/S9冻结产物和S11输出
输出：output/q3/robustness/verification.json，并更新本阶段清单
职责：验证误差、替代预测、排名差距、覆盖边界和禁止声明。
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
CANDIDATE = ROOT / "output/q3/candidates/narrow_pchip"
FORMAL = ROOT / "output/q3/formal"
OUT = ROOT / "output/q3/robustness"
SCRIPT = Path(__file__).resolve()
TOL = 1e-10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def add(checks: list[dict], name: str, passed: bool, detail: str) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def main() -> None:
    data = pd.read_csv(INPUT)
    holdout = pd.read_csv(CANDIDATE / "interior_holdout_predictions.csv")
    rank_checks = pd.read_csv(CANDIDATE / "temperature_ranking_checks.csv")
    formal_d1 = pd.read_csv(FORMAL / "d1_label_predictions.csv")
    recommendations = pd.read_csv(FORMAL / "recommendations.csv")
    comparison = pd.read_csv(OUT / "d1_pchip_linear_comparison.csv")
    coverage = pd.read_csv(OUT / "temperature_coverage.csv")
    gaps = pd.read_csv(OUT / "ranking_gaps.csv")
    summary = json.loads(
        (OUT / "robustness_summary.json").read_text(encoding="utf-8")
    )
    checks: list[dict] = []

    pchip_error = (
        holdout["pchip_prediction_pct"] - holdout["actual_c4_yield_pct"]
    ).abs()
    linear_error = (
        holdout["linear_prediction_pct"] - holdout["actual_c4_yield_pct"]
    ).abs()
    saved_holdout = summary["interior_holdout"]
    metric_errors = [
        abs(saved_holdout["pchip"]["mae_pct_point"] - pchip_error.mean()),
        abs(saved_holdout["pchip"]["median_ae_pct_point"] - pchip_error.median()),
        abs(
            saved_holdout["pchip"]["rmse_pct_point"]
            - np.sqrt(np.mean(pchip_error**2))
        ),
        abs(saved_holdout["pchip"]["max_ae_pct_point"] - pchip_error.max()),
        abs(saved_holdout["linear"]["mae_pct_point"] - linear_error.mean()),
        abs(saved_holdout["linear"]["median_ae_pct_point"] - linear_error.median()),
        abs(
            saved_holdout["linear"]["rmse_pct_point"]
            - np.sqrt(np.mean(linear_error**2))
        ),
        abs(saved_holdout["linear"]["max_ae_pct_point"] - linear_error.max()),
    ]
    add(
        checks,
        "1_遮点误差复算",
        len(holdout) == 72
        and max(metric_errors) < TOL
        and int((pchip_error < linear_error).sum()) == 68,
        f"rows={len(holdout)}, wins={int((pchip_error < linear_error).sum())}/72, "
        f"max_metric_error={max(metric_errors):.3e}",
    )

    pchip_rank = rank_checks[rank_checks["model"] == "pchip"]
    add(
        checks,
        "2_最高候选识别边界",
        len(pchip_rank) == 5
        and int(pchip_rank["top1_correct"].sum()) == 4
        and not summary["interior_holdout"]["top1_identification"]["perfect"],
        f"top1_correct={int(pchip_rank['top1_correct'].sum())}/{len(pchip_rank)}",
    )

    linear_errors = []
    identity_ok = set(zip(comparison["catalyst_id"], comparison["temperature_c"])) == set(
        zip(formal_d1["catalyst_id"], formal_d1["temperature_c"])
    )
    for row in comparison.itertuples(index=False):
        group = data[data["catalyst_id"] == row.catalyst_id]
        lower = group[group["temperature_c"] < row.temperature_c].sort_values(
            "temperature_c"
        ).iloc[-1]
        upper = group[group["temperature_c"] > row.temperature_c].sort_values(
            "temperature_c"
        ).iloc[0]
        weight = (
            (row.temperature_c - lower["temperature_c"])
            / (upper["temperature_c"] - lower["temperature_c"])
        )
        expected = float(
            lower["c4_yield_pct"]
            + weight * (upper["c4_yield_pct"] - lower["c4_yield_pct"])
        )
        linear_errors.append(abs(row.linear_predicted_c4_yield_pct - expected))
    add(
        checks,
        "3_D1局部直线独立复算",
        identity_ok and len(comparison) == 11 and max(linear_errors) < TOL,
        f"rows={len(comparison)}, max_abs_error={max(linear_errors):.3e}",
    )

    low_best = float(
        data[data["temperature_c"] < 350.0]["c4_yield_pct"].max()
    )
    alternative_ok = (
        comparison[
            ["linear_predicted_c4_yield_pct", "pchip_predicted_c4_yield_pct"]
        ].max(axis=1)
        < low_best
    ).all()
    add(
        checks,
        "4_两种插值均不改变推荐",
        alternative_ok
        and comparison["both_below_low_d0_recommendation"].all()
        and not summary["d1_alternative_prediction"][
            "changes_formal_recommendation_under_either_method"
        ],
        f"max_linear={comparison['linear_predicted_c4_yield_pct'].max():.6f}, "
        f"max_pchip={comparison['pchip_predicted_c4_yield_pct'].max():.6f}, "
        f"low_d0_best={low_best:.6f}",
    )

    coverage_expected = (
        data.groupby("temperature_c")["catalyst_id"]
        .nunique()
        .sort_index()
    )
    coverage_saved = coverage.set_index("temperature_c")[
        "observed_combination_count"
    ].sort_index()
    add(
        checks,
        "5_温度覆盖复算",
        coverage_expected.equals(coverage_saved.astype(int))
        and int(coverage_saved.loc[450.0]) == 1
        and int(coverage_saved.loc[325.0]) == 10
        and set(data.loc[data["temperature_c"] == 450.0, "catalyst_id"])
        == {"A3"},
        f"coverage={coverage_saved.astype(int).to_dict()}",
    )

    gap_errors = []
    identities_ok = True
    for scenario in ("general", "strict_below_350"):
        domain = (
            data
            if scenario == "general"
            else data[data["temperature_c"] < 350.0]
        )
        ordered = domain.sort_values(
            ["c4_yield_pct", "catalyst_id", "temperature_c"],
            ascending=[False, True, True],
            kind="mergesort",
        ).reset_index(drop=True)
        distinct = ordered[
            ordered["catalyst_id"] != ordered.iloc[0]["catalyst_id"]
        ].iloc[0]
        row = gaps[gaps["scenario"] == scenario].iloc[0]
        identities_ok &= (
            row["best_catalyst_id"] == ordered.iloc[0]["catalyst_id"]
            and row["runner_up_catalyst_id"] == ordered.iloc[1]["catalyst_id"]
            and row["best_distinct_combination_id"] == distinct["catalyst_id"]
        )
        gap_errors.extend(
            [
                abs(
                    row["lead_over_runner_up_pct_point"]
                    - (
                        ordered.iloc[0]["c4_yield_pct"]
                        - ordered.iloc[1]["c4_yield_pct"]
                    )
                ),
                abs(
                    row["lead_over_best_distinct_combination_pct_point"]
                    - (
                        ordered.iloc[0]["c4_yield_pct"]
                        - distinct["c4_yield_pct"]
                    )
                ),
            ]
        )
    add(
        checks,
        "6_排名差距复算",
        identities_ok and max(gap_errors) < TOL,
        f"max_abs_error={max(gap_errors):.3e}",
    )

    boundary_text = " ".join(summary["claim_boundaries"])
    forbidden_terms = ["显著优于", "置信区间为", "实验测量误差为"]
    add(
        checks,
        "7_声明边界",
        all(term not in boundary_text for term in forbidden_terms)
        and "不构造无重复数据无法支持的传统显著性检验或置信区间"
        in summary["claim_boundaries"]
        and "遮点误差是预测验证误差，不是实验测量误差"
        in summary["claim_boundaries"],
        f"forbidden_hits={sum(term in boundary_text for term in forbidden_terms)}",
    )

    manifest_path = OUT / "artifact_manifest.csv"
    with manifest_path.open(encoding="utf-8-sig", newline="") as stream:
        manifest = list(csv.DictReader(stream))
    expected_outputs = {
        "output/q3/robustness/d1_pchip_linear_comparison.csv",
        "output/q3/robustness/temperature_coverage.csv",
        "output/q3/robustness/ranking_gaps.csv",
        "output/q3/robustness/robustness_summary.json",
    }
    listed = {row["path"] for row in manifest}
    hash_ok = all(
        (ROOT / row["path"]).is_file()
        and sha256(ROOT / row["path"]) == row["sha256"]
        for row in manifest
    )
    add(
        checks,
        "8_产物合同与哈希",
        expected_outputs.issubset(listed) and hash_ok,
        f"pre_verification_hashes={sum(sha256(ROOT / row['path']) == row['sha256'] for row in manifest)}/{len(manifest)}",
    )

    result = {
        "schema_version": "1.0",
        "status": "q3_s11_independent_verification",
        "passed": bool(all(item["passed"] for item in checks)),
        "check_count": len(checks),
        "passed_count": sum(bool(item["passed"]) for item in checks),
        "checks": checks,
        "note": "通过支持S11所述稳定范围与失败边界，不构成显著性、因果或连续温度最优证明。",
    }
    verification_path = OUT / "verification.json"
    verification_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    kept = [
        row
        for row in manifest
        if row["path"]
        not in {
            str(SCRIPT.relative_to(ROOT)),
            str(verification_path.relative_to(ROOT)),
        }
    ]
    kept.extend(
        [
            {
                "path": str(SCRIPT.relative_to(ROOT)),
                "role": "verification_source",
                "description": "S11独立验证程序",
                "producer": "self",
                "consumer": "S12人工复审与后续论文映射",
                "sha256": sha256(SCRIPT),
            },
            {
                "path": str(verification_path.relative_to(ROOT)),
                "role": "verification_output",
                "description": "S11八项独立复算结果",
                "producer": str(SCRIPT.relative_to(ROOT)),
                "consumer": "S12人工复审与后续论文映射",
                "sha256": sha256(verification_path),
            },
        ]
    )
    pd.DataFrame(kept).to_csv(manifest_path, index=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
