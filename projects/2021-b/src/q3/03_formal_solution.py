#!/usr/bin/env python3
"""第三问S9正式实现：生成D0推荐和标签内D1辅助预测。

输入：output/data_audit/tables/cleaned_attachment1.csv
输出：output/q3/formal/下的D0排序、D1预测、推荐、摘要和产物清单
职责：忠实实现S8冻结规格；正式推荐仅来自D0，D1不得改写为观测。
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime
from pathlib import Path

import pandas as pd
import scipy
from scipy.interpolate import PchipInterpolator

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q3" / "formal"
SCRIPT = Path(__file__).resolve()
TEMPERATURE_LABELS = (250.0, 275.0, 300.0, 325.0, 350.0, 400.0, 450.0)
SCENARIOS = {
    "general": "附件1全部D0实测单元",
    "strict_below_350": "附件1中temperature_c严格小于350的D0实测单元",
}
TOL = 1e-10


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def ordered_domain(data: pd.DataFrame, scenario: str) -> pd.DataFrame:
    domain = data if scenario == "general" else data[data["temperature_c"] < 350.0]
    ordered = domain.sort_values(
        ["c4_yield_pct", "catalyst_id", "temperature_c"],
        ascending=[False, True, True],
        kind="mergesort",
    ).copy()
    ordered.insert(0, "scenario", scenario)
    ordered.insert(1, "rank", range(1, len(ordered) + 1))
    best_yield = float(ordered.iloc[0]["c4_yield_pct"])
    ordered["gap_from_best_pct_point"] = best_yield - ordered["c4_yield_pct"]
    ordered["gap_from_previous_pct_point"] = (
        ordered["c4_yield_pct"].shift(1) - ordered["c4_yield_pct"]
    )
    ordered.loc[ordered.index[0], "gap_from_previous_pct_point"] = 0.0
    ordered["evidence_status"] = "d0_observation"
    return ordered


def build_d1(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for catalyst_id, group in data.groupby("catalyst_id", sort=True):
        group = group.sort_values("temperature_c")
        observed = set(float(value) for value in group["temperature_c"])
        lower_bound = float(group["temperature_c"].min())
        upper_bound = float(group["temperature_c"].max())
        for temperature in TEMPERATURE_LABELS:
            if (
                temperature not in observed
                and lower_bound < temperature < upper_bound
            ):
                prediction = float(
                    PchipInterpolator(
                        group["temperature_c"],
                        group["c4_yield_pct"],
                        extrapolate=False,
                    )(temperature)
                )
                lower = group[group["temperature_c"] < temperature].iloc[-1]
                upper = group[group["temperature_c"] > temperature].iloc[0]
                rows.append(
                    {
                        "catalyst_id": catalyst_id,
                        "temperature_c": temperature,
                        "pchip_predicted_c4_yield_pct": prediction,
                        "lower_observed_temperature_c": float(lower["temperature_c"]),
                        "upper_observed_temperature_c": float(upper["temperature_c"]),
                        "within_own_observed_range": True,
                        "general_d1_eligible": True,
                        "strict_below_350_d1_eligible": temperature < 350.0,
                        "evidence_status": "candidate_prediction_not_observation",
                    }
                )
    return pd.DataFrame(rows).sort_values(
        ["temperature_c", "pchip_predicted_c4_yield_pct", "catalyst_id"],
        ascending=[True, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def recommendation_row(
    ranking: pd.DataFrame, d1: pd.DataFrame, scenario: str
) -> dict:
    best = ranking.iloc[0]
    runner_up = ranking.iloc[1]
    distinct = ranking[ranking["catalyst_id"] != best["catalyst_id"]].iloc[0]
    eligible_d1 = d1[
        d1[
            "general_d1_eligible"
            if scenario == "general"
            else "strict_below_350_d1_eligible"
        ]
    ]
    d1_max = eligible_d1.iloc[
        eligible_d1["pchip_predicted_c4_yield_pct"].argmax()
    ]
    return {
        "scenario": scenario,
        "constraint": SCENARIOS[scenario],
        "formal_recommendation_source": "d0_observation",
        "best_source_excel_row": int(best["source_excel_row"]),
        "best_catalyst_id": best["catalyst_id"],
        "best_temperature_c": float(best["temperature_c"]),
        "best_ethanol_conversion_pct": float(best["ethanol_conversion_pct"]),
        "best_c4_selectivity_pct": float(best["c4_selectivity_pct"]),
        "best_c4_yield_pct": float(best["c4_yield_pct"]),
        "runner_up_source_excel_row": int(runner_up["source_excel_row"]),
        "runner_up_catalyst_id": runner_up["catalyst_id"],
        "runner_up_temperature_c": float(runner_up["temperature_c"]),
        "runner_up_c4_yield_pct": float(runner_up["c4_yield_pct"]),
        "lead_over_runner_up_pct_point": float(
            best["c4_yield_pct"] - runner_up["c4_yield_pct"]
        ),
        "best_distinct_combination_source_excel_row": int(
            distinct["source_excel_row"]
        ),
        "best_distinct_combination_id": distinct["catalyst_id"],
        "best_distinct_combination_temperature_c": float(
            distinct["temperature_c"]
        ),
        "best_distinct_combination_c4_yield_pct": float(
            distinct["c4_yield_pct"]
        ),
        "lead_over_best_distinct_combination_pct_point": float(
            best["c4_yield_pct"] - distinct["c4_yield_pct"]
        ),
        "d1_candidate_count": int(len(eligible_d1)),
        "highest_d1_candidate_id": d1_max["catalyst_id"],
        "highest_d1_candidate_temperature_c": float(d1_max["temperature_c"]),
        "highest_d1_candidate_predicted_c4_yield_pct": float(
            d1_max["pchip_predicted_c4_yield_pct"]
        ),
        "d1_exceeds_formal_d0_recommendation": bool(
            d1_max["pchip_predicted_c4_yield_pct"] > best["c4_yield_pct"]
        ),
        "recommendation_changed_by_d1": False,
    }


def main() -> None:
    started_at = datetime.now().astimezone()
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(INPUT)
    required = {
        "source_excel_row",
        "catalyst_id",
        "temperature_c",
        "ethanol_conversion_pct",
        "c4_selectivity_pct",
        "c4_yield_pct",
    }
    missing_columns = required - set(data.columns)
    if missing_columns:
        raise ValueError(f"缺少字段：{sorted(missing_columns)}")
    if len(data) != 114 or data["catalyst_id"].nunique() != 21:
        raise ValueError("输入规模不符合S8规格")
    if data.duplicated(["catalyst_id", "temperature_c"]).any():
        raise ValueError("组合—温度键存在重复")
    formula_error = float(
        (
            data["c4_yield_pct"]
            - data["ethanol_conversion_pct"] * data["c4_selectivity_pct"] / 100.0
        )
        .abs()
        .max()
    )
    if formula_error > TOL:
        raise ValueError(f"收率公式不一致：{formula_error}")

    rankings = {
        scenario: ordered_domain(data, scenario) for scenario in SCENARIOS
    }
    d1 = build_d1(data)
    expected_d1 = {
        ("A6", 325.0), ("A7", 325.0), ("A8", 325.0),
        ("A9", 325.0), ("A10", 325.0), ("A11", 325.0),
        ("A12", 325.0), ("A13", 325.0), ("A14", 325.0),
        ("B1", 325.0), ("B2", 325.0),
    }
    actual_d1 = set(zip(d1["catalyst_id"], d1["temperature_c"]))
    if actual_d1 != expected_d1:
        raise ValueError(f"D1身份不符合S8规格：{sorted(actual_d1)}")

    ranking_columns = [
        "scenario", "rank", "source_excel_row", "catalyst_id",
        "temperature_c", "ethanol_conversion_pct", "c4_selectivity_pct",
        "c4_yield_pct", "gap_from_best_pct_point",
        "gap_from_previous_pct_point", "evidence_status",
    ]
    d0_path = OUT / "d0_rankings.csv"
    d1_path = OUT / "d1_label_predictions.csv"
    recommendation_path = OUT / "recommendations.csv"
    summary_path = OUT / "formal_summary.json"
    pd.concat(
        [ranking[ranking_columns] for ranking in rankings.values()],
        ignore_index=True,
    ).to_csv(d0_path, index=False)
    d1.to_csv(d1_path, index=False)
    recommendations = pd.DataFrame(
        [
            recommendation_row(rankings[scenario], d1, scenario)
            for scenario in SCENARIOS
        ]
    )
    recommendations.to_csv(recommendation_path, index=False)

    summary = {
        "schema_version": "1.0",
        "status": "s9_formal_solution_generated_pending_s10_verification",
        "input": str(INPUT.relative_to(ROOT)),
        "input_sha256": sha256(INPUT),
        "producer": str(SCRIPT.relative_to(ROOT)),
        "method": {
            "target": "c4_yield_pct",
            "yield_formula": "ethanol_conversion_pct * c4_selectivity_pct / 100",
            "formula_max_abs_error_pct_point": formula_error,
            "d0_role": "formal_recommendation_from_observed_cells",
            "d1_role": "auxiliary_label_only_prediction_not_observation",
            "d1_interpolator": "within_combination_pchip",
            "temperature_labels_c": list(TEMPERATURE_LABELS),
            "extrapolation_allowed": False,
            "new_recipe_allowed": False,
        },
        "domain_counts": {
            "d0_general": int(len(rankings["general"])),
            "d0_strict_below_350": int(len(rankings["strict_below_350"])),
            "d1_general": int(d1["general_d1_eligible"].sum()),
            "d1_strict_below_350": int(
                d1["strict_below_350_d1_eligible"].sum()
            ),
        },
        "recommendations": recommendations.to_dict(orient="records"),
        "claim_boundaries": [
            "正式推荐仅表示附件1D0实测范围内的最高观测收率",
            "严格低温情景要求温度严格小于350摄氏度",
            "D1仅含已有温度标签中且位于组合自身实测范围内部的缺失单元",
            "D1预测不是观测，即使更高也只能作为待实验验证候选",
            "不搜索连续温度，不外推，不创建新配方",
            "不外推到工业规模、长期稳定性、安全性或经济性",
            "单次观测排名不表示未来实验中必然仍为第一",
        ],
        "run": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now().astimezone().isoformat(),
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "scipy": scipy.__version__,
            "random_seed": None,
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    manifest_entries = [
        (INPUT, "input", "第三问唯一清洁输入"),
        (SCRIPT, "source", "S9正式实现"),
        (d0_path, "output", "两种情景D0完整排序"),
        (d1_path, "output", "11个标签内D1辅助预测"),
        (recommendation_path, "output", "两种情景正式推荐与差距"),
        (summary_path, "output", "S9方法、结果、边界和运行信息"),
    ]
    pd.DataFrame(
        [
            {
                "path": str(path.relative_to(ROOT)),
                "role": role,
                "description": description,
                "producer": (
                    str(SCRIPT.relative_to(ROOT))
                    if role == "output"
                    else "upstream_or_self"
                ),
                "consumer": "S10独立验证、S11解释与后续论文映射",
                "sha256": sha256(path),
            }
            for path, role, description in manifest_entries
        ]
    ).to_csv(OUT / "artifact_manifest.csv", index=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
