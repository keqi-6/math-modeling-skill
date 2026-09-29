#!/usr/bin/env python3
"""第三问S10独立验证：不导入S9，也不调用SciPy插值接口。

输入：唯一清洁数据及output/q3/formal中的S9正式产物
输出：output/q3/formal/verification.json，并更新artifact_manifest.csv
职责：按S8冻结合同独立复算D0、D1、推荐、边界与哈希闭合。
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q3" / "formal"
SCRIPT = Path(__file__).resolve()
TOL = 1e-10
LABELS = {250.0, 275.0, 300.0, 325.0, 350.0, 400.0, 450.0}
EXPECTED_D1 = {
    ("A6", 325.0), ("A7", 325.0), ("A8", 325.0),
    ("A9", 325.0), ("A10", 325.0), ("A11", 325.0),
    ("A12", 325.0), ("A13", 325.0), ("A14", 325.0),
    ("B1", 325.0), ("B2", 325.0),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def endpoint_derivative(h0: float, h1: float, m0: float, m1: float) -> float:
    derivative = ((2.0 * h0 + h1) * m0 - h0 * m1) / (h0 + h1)
    if np.sign(derivative) != np.sign(m0):
        return 0.0
    if np.sign(m0) != np.sign(m1) and abs(derivative) > 3.0 * abs(m0):
        return 3.0 * m0
    return float(derivative)


def pchip_derivatives(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """按PCHIP保形规则独立计算节点导数。"""
    h = np.diff(x)
    slopes = np.diff(y) / h
    derivatives = np.zeros(len(x), dtype=float)
    if len(x) == 2:
        derivatives[:] = slopes[0]
        return derivatives
    derivatives[0] = endpoint_derivative(h[0], h[1], slopes[0], slopes[1])
    derivatives[-1] = endpoint_derivative(
        h[-1], h[-2], slopes[-1], slopes[-2]
    )
    for index in range(1, len(x) - 1):
        left = slopes[index - 1]
        right = slopes[index]
        if left == 0.0 or right == 0.0 or np.sign(left) != np.sign(right):
            derivatives[index] = 0.0
        else:
            weight_left = 2.0 * h[index] + h[index - 1]
            weight_right = h[index] + 2.0 * h[index - 1]
            derivatives[index] = (weight_left + weight_right) / (
                weight_left / left + weight_right / right
            )
    return derivatives


def manual_pchip(x: np.ndarray, y: np.ndarray, target: float) -> float:
    if not x[0] < target < x[-1]:
        raise ValueError("独立复算拒绝外推或端点预测")
    upper_index = int(np.searchsorted(x, target, side="right"))
    lower_index = upper_index - 1
    h = float(x[upper_index] - x[lower_index])
    s = float((target - x[lower_index]) / h)
    derivatives = pchip_derivatives(x, y)
    return float(
        (2 * s**3 - 3 * s**2 + 1) * y[lower_index]
        + (s**3 - 2 * s**2 + s) * h * derivatives[lower_index]
        + (-2 * s**3 + 3 * s**2) * y[upper_index]
        + (s**3 - s**2) * h * derivatives[upper_index]
    )


def ordered(data: pd.DataFrame) -> pd.DataFrame:
    return data.sort_values(
        ["c4_yield_pct", "catalyst_id", "temperature_c"],
        ascending=[False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)


def add_check(checks: list[dict], name: str, passed: bool, detail: str) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def main() -> None:
    data = pd.read_csv(INPUT)
    saved_d0 = pd.read_csv(OUT / "d0_rankings.csv")
    saved_d1 = pd.read_csv(OUT / "d1_label_predictions.csv")
    saved_recommendations = pd.read_csv(OUT / "recommendations.csv")
    summary = json.loads((OUT / "formal_summary.json").read_text(encoding="utf-8"))
    manifest_path = OUT / "artifact_manifest.csv"
    checks: list[dict] = []

    duplicate_count = int(
        data.duplicated(["catalyst_id", "temperature_c"]).sum()
    )
    add_check(
        checks,
        "1_输入规模与主键",
        len(data) == 114
        and data["catalyst_id"].nunique() == 21
        and duplicate_count == 0,
        f"rows={len(data)}, combinations={data['catalyst_id'].nunique()}, "
        f"duplicate_keys={duplicate_count}",
    )

    recomputed_yield = (
        data["ethanol_conversion_pct"] * data["c4_selectivity_pct"] / 100.0
    )
    formula_error = float((recomputed_yield - data["c4_yield_pct"]).abs().max())
    add_check(
        checks,
        "2_收率公式",
        formula_error < TOL,
        f"max_abs_error_pct_point={formula_error:.3e}",
    )

    domains = {
        "general": data.copy(),
        "strict_below_350": data[data["temperature_c"] < 350.0].copy(),
    }
    domain_ok = (
        len(domains["general"]) == 114
        and len(domains["strict_below_350"]) == 73
        and (domains["strict_below_350"]["temperature_c"] < 350.0).all()
        and 350.0 not in set(domains["strict_below_350"]["temperature_c"])
    )
    add_check(
        checks,
        "3_D0两情景边界",
        domain_ok,
        "general=114, strict_below_350=73, 350_excluded=True",
    )

    derived_d1: set[tuple[str, float]] = set()
    for catalyst_id, group in data.groupby("catalyst_id"):
        observed = set(float(value) for value in group["temperature_c"])
        lower = float(group["temperature_c"].min())
        upper = float(group["temperature_c"].max())
        for label in LABELS:
            if label not in observed and lower < label < upper:
                derived_d1.add((str(catalyst_id), label))
    saved_d1_ids = set(zip(saved_d1["catalyst_id"], saved_d1["temperature_c"]))
    add_check(
        checks,
        "4_D1标签身份",
        derived_d1 == EXPECTED_D1 == saved_d1_ids and len(saved_d1) == 11,
        f"derived={sorted(derived_d1)}, saved_count={len(saved_d1)}",
    )

    enclosure_ok = True
    for row in saved_d1.itertuples(index=False):
        group = data[data["catalyst_id"] == row.catalyst_id]
        lower_values = group[group["temperature_c"] < row.temperature_c][
            "temperature_c"
        ]
        upper_values = group[group["temperature_c"] > row.temperature_c][
            "temperature_c"
        ]
        enclosure_ok &= (
            len(lower_values) > 0
            and len(upper_values) > 0
            and abs(float(lower_values.max()) - row.lower_observed_temperature_c)
            < TOL
            and abs(float(upper_values.min()) - row.upper_observed_temperature_c)
            < TOL
            and bool(row.within_own_observed_range)
        )
    add_check(
        checks,
        "5_D1同组合包围与零外推",
        enclosure_ok,
        "all_11_have_lower_and_upper_observations=True",
    )

    d1_errors = []
    for row in saved_d1.itertuples(index=False):
        group = data[data["catalyst_id"] == row.catalyst_id].sort_values(
            "temperature_c"
        )
        prediction = manual_pchip(
            group["temperature_c"].to_numpy(float),
            group["c4_yield_pct"].to_numpy(float),
            float(row.temperature_c),
        )
        d1_errors.append(abs(prediction - row.pchip_predicted_c4_yield_pct))
    max_d1_error = max(d1_errors)
    add_check(
        checks,
        "6_D1手工PCHIP复算",
        max_d1_error < TOL,
        f"max_abs_error_pct_point={max_d1_error:.3e}",
    )

    ranking_errors: list[float] = []
    ranking_identity_ok = True
    recommendation_identity_ok = True
    for scenario, domain in domains.items():
        expected = ordered(domain)
        saved = saved_d0[saved_d0["scenario"] == scenario].reset_index(drop=True)
        recommendation = saved_recommendations[
            saved_recommendations["scenario"] == scenario
        ].iloc[0]
        distinct = expected[
            expected["catalyst_id"] != expected.iloc[0]["catalyst_id"]
        ].iloc[0]
        ranking_identity_ok &= (
            len(saved) == len(expected)
            and saved["rank"].tolist() == list(range(1, len(expected) + 1))
            and saved["source_excel_row"].tolist()
            == expected["source_excel_row"].tolist()
            and saved["catalyst_id"].tolist() == expected["catalyst_id"].tolist()
        )
        ranking_errors.extend(
            abs(saved["c4_yield_pct"] - expected["c4_yield_pct"]).tolist()
        )
        expected_gap_best = (
            expected.iloc[0]["c4_yield_pct"] - expected["c4_yield_pct"]
        )
        ranking_errors.extend(
            abs(saved["gap_from_best_pct_point"] - expected_gap_best).tolist()
        )
        recommendation_identity_ok &= (
            recommendation["best_source_excel_row"]
            == expected.iloc[0]["source_excel_row"]
            and recommendation["runner_up_source_excel_row"]
            == expected.iloc[1]["source_excel_row"]
            and recommendation["best_distinct_combination_source_excel_row"]
            == distinct["source_excel_row"]
        )
        ranking_errors.extend(
            [
                abs(
                    recommendation["best_c4_yield_pct"]
                    - expected.iloc[0]["c4_yield_pct"]
                ),
                abs(
                    recommendation["runner_up_c4_yield_pct"]
                    - expected.iloc[1]["c4_yield_pct"]
                ),
                abs(
                    recommendation["lead_over_runner_up_pct_point"]
                    - (
                        expected.iloc[0]["c4_yield_pct"]
                        - expected.iloc[1]["c4_yield_pct"]
                    )
                ),
                abs(
                    recommendation[
                        "lead_over_best_distinct_combination_pct_point"
                    ]
                    - (
                        expected.iloc[0]["c4_yield_pct"]
                        - distinct["c4_yield_pct"]
                    )
                ),
            ]
        )
    max_ranking_error = max(ranking_errors)
    add_check(
        checks,
        "7_D0排序推荐与差距",
        ranking_identity_ok
        and recommendation_identity_ok
        and max_ranking_error < TOL,
        f"full_ranking_identity=True, max_abs_error={max_ranking_error:.3e}",
    )

    status_ok = (
        set(saved_d0["evidence_status"]) == {"d0_observation"}
        and set(saved_d1["evidence_status"])
        == {"candidate_prediction_not_observation"}
        and set(saved_recommendations["formal_recommendation_source"])
        == {"d0_observation"}
        and not saved_d1["evidence_status"].isin(["d0_observation"]).any()
    )
    add_check(
        checks,
        "8_D0与D1证据状态",
        status_ok,
        "d0=observation, d1=candidate_prediction_not_observation",
    )

    low_best = float(domains["strict_below_350"]["c4_yield_pct"].max())
    highest_d1 = float(saved_d1["pchip_predicted_c4_yield_pct"].max())
    saved_low = saved_recommendations[
        saved_recommendations["scenario"] == "strict_below_350"
    ].iloc[0]
    d1_effect_ok = (
        highest_d1 < low_best
        and not bool(saved_low["d1_exceeds_formal_d0_recommendation"])
        and not bool(saved_low["recommendation_changed_by_d1"])
    )
    add_check(
        checks,
        "9_D1不改变低温推荐",
        d1_effect_ok,
        f"highest_d1={highest_d1:.12f}, low_d0_best={low_best:.12f}",
    )

    expected_files = {
        "output/q3/formal/d0_rankings.csv",
        "output/q3/formal/d1_label_predictions.csv",
        "output/q3/formal/recommendations.csv",
        "output/q3/formal/formal_summary.json",
    }
    with manifest_path.open(encoding="utf-8-sig", newline="") as stream:
        manifest_rows = list(csv.DictReader(stream))
    listed_paths = {row["path"] for row in manifest_rows}
    hash_ok = True
    for row in manifest_rows:
        path = ROOT / row["path"]
        hash_ok &= path.is_file() and sha256(path) == row["sha256"]
    summary_ok = (
        summary["input_sha256"] == sha256(INPUT)
        and summary["domain_counts"]
        == {
            "d0_general": 114,
            "d0_strict_below_350": 73,
            "d1_general": 11,
            "d1_strict_below_350": 11,
        }
        and summary["status"]
        == "s9_formal_solution_generated_pending_s10_verification"
    )
    files_ok = expected_files.issubset(listed_paths)
    add_check(
        checks,
        "10_结构化产物与哈希闭合",
        hash_ok and summary_ok and files_ok,
        f"pre_verification_manifest_hashes={sum(sha256(ROOT / row['path']) == row['sha256'] for row in manifest_rows)}/{len(manifest_rows)}",
    )

    result = {
        "schema_version": "1.0",
        "status": "s10_independent_verification",
        "passed": bool(all(item["passed"] for item in checks)),
        "tolerance_pct_point": TOL,
        "check_count": len(checks),
        "passed_count": sum(bool(item["passed"]) for item in checks),
        "independence": [
            "未导入S9正式实现",
            "未调用scipy.interpolate.PchipInterpolator",
            "按PCHIP节点导数与Hermite分段公式手工复算",
            "直接读取唯一清洁输入和S9冻结产物",
        ],
        "checks": checks,
        "verified_recommendations": {
            "general": {
                "catalyst_id": "A3",
                "temperature_c": 400.0,
                "c4_yield_pct": float(domains["general"]["c4_yield_pct"].max()),
            },
            "strict_below_350": {
                "catalyst_id": "A2",
                "temperature_c": 325.0,
                "c4_yield_pct": low_best,
            },
            "highest_d1": {
                "catalyst_id": str(
                    saved_d1.loc[
                        saved_d1["pchip_predicted_c4_yield_pct"].idxmax(),
                        "catalyst_id",
                    ]
                ),
                "temperature_c": 325.0,
                "predicted_c4_yield_pct": highest_d1,
                "changes_formal_recommendation": False,
            },
        },
        "note": "通过证明S9实现与S8规格及冻结产物一致；不等于完成S11解释、S12人工冻结或论文批准。",
    }
    verification_path = OUT / "verification.json"
    verification_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    kept_rows = [
        row
        for row in manifest_rows
        if row["path"]
        not in {
            str(SCRIPT.relative_to(ROOT)),
            str(verification_path.relative_to(ROOT)),
        }
    ]
    kept_rows.extend(
        [
            {
                "path": str(SCRIPT.relative_to(ROOT)),
                "role": "verification_source",
                "description": "S10独立验证程序",
                "producer": "self",
                "consumer": "S10技术完成证据、S11解释与后续论文映射",
                "sha256": sha256(SCRIPT),
            },
            {
                "path": str(verification_path.relative_to(ROOT)),
                "role": "verification_output",
                "description": "S8合同的10项独立复算结果",
                "producer": str(SCRIPT.relative_to(ROOT)),
                "consumer": "S10技术完成证据、S11解释与后续论文映射",
                "sha256": sha256(verification_path),
            },
        ]
    )
    pd.DataFrame(kept_rows).to_csv(manifest_path, index=False)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
