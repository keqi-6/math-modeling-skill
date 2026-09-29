#!/usr/bin/env python3
"""第四问S9正式实现：生成五次实验设计及观测后更新规则。

本程序忠实实现S8冻结规格。它只读取现有冻结证据，不预测或创建未来实验响应。
"""

from __future__ import annotations

import hashlib
import json
import platform
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
Q3_RECOMMENDATIONS = ROOT / "output" / "q3" / "formal" / "recommendations.csv"
Q3_GAPS = ROOT / "output" / "q3" / "robustness" / "ranking_gaps.csv"
Q3_COVERAGE = ROOT / "output" / "q3" / "robustness" / "temperature_coverage.csv"
Q3_ROBUSTNESS = ROOT / "output" / "q3" / "robustness" / "robustness_summary.json"
OUT = ROOT / "output" / "q4" / "formal"
SCRIPT = Path(__file__).resolve()
TOL = 1e-9

DESIGN = [
    {
        "experiment_id": "E1",
        "catalyst_id": "A3",
        "temperature_c": 375.0,
        "is_repeat_of_existing_condition": False,
        "responsibility_codes": "G2|G5",
        "experiment_role": "general_lower_interval_refinement_and_same_temperature_competition",
        "plain_reason": "细分A3的350—400℃区间，并与E5在375℃直接比较",
    },
    {
        "experiment_id": "E2",
        "catalyst_id": "A3",
        "temperature_c": 425.0,
        "is_repeat_of_existing_condition": False,
        "responsibility_codes": "G3",
        "experiment_role": "general_upper_interval_refinement",
        "plain_reason": "细分A3的400—450℃区间，判断400℃附近是峰值还是平台",
    },
    {
        "experiment_id": "E3",
        "catalyst_id": "A2",
        "temperature_c": 337.5,
        "is_repeat_of_existing_condition": False,
        "responsibility_codes": "G4",
        "experiment_role": "strict_low_temperature_interval_refinement",
        "plain_reason": "细分A2的325—350℃区间，直接更新严格低温推荐",
    },
    {
        "experiment_id": "E4",
        "catalyst_id": "A3",
        "temperature_c": 400.0,
        "is_repeat_of_existing_condition": True,
        "responsibility_codes": "G1",
        "experiment_role": "local_independent_replication_of_current_global_best",
        "plain_reason": "检查当前全题最高观测A3—400℃的局部可复现性",
    },
    {
        "experiment_id": "E5",
        "catalyst_id": "A4",
        "temperature_c": 375.0,
        "is_repeat_of_existing_condition": False,
        "responsibility_codes": "G5",
        "experiment_role": "same_temperature_competitor_challenge",
        "plain_reason": "与E1形成A3/A4在375℃的直接同温竞争",
    },
]

EVIDENCE = [
    {
        "experiment_id": "E1",
        "upstream_question": "Q1|Q2|Q3",
        "evidence_gap": "A3在350—400℃无内部观测，且其他组合不能由A3曲线代表",
        "anchor_conditions": "A3@350|A3@400|A4@375(E5)",
        "possible_update": "缩小一般情景低侧区间，并形成375℃A3/A4同温比较",
    },
    {
        "experiment_id": "E2",
        "upstream_question": "Q1|Q3",
        "evidence_gap": "A3@400与A3@450相差1.6096个百分点但区间内部未测",
        "anchor_conditions": "A3@400|A3@450",
        "possible_update": "判断A3一般情景推荐是否移到425℃或形成较宽高收率区",
    },
    {
        "experiment_id": "E3",
        "upstream_question": "Q1|Q3",
        "evidence_gap": "A2@325至350℃之间未测，而严格低温排除350℃",
        "anchor_conditions": "A2@325|A2@350",
        "possible_update": "决定严格低温推荐是否从325℃移到337.5℃",
    },
    {
        "experiment_id": "E4",
        "upstream_question": "Q1|Q3",
        "evidence_gap": "114个原条件均无独立重复，A3@400是当前最高观测",
        "anchor_conditions": "A3@400",
        "possible_update": "报告局部重复差异并以两次均值更新该条件描述性排序",
    },
    {
        "experiment_id": "E5",
        "upstream_question": "Q2|Q3",
        "evidence_gap": "A4是400℃最强不同组合，但375℃无A3/A4同温比较",
        "anchor_conditions": "A3@375(E1)|A4@400",
        "possible_update": "检查A3对A4的领先是否在375℃保持",
    },
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def unique_recipe(data: pd.DataFrame, catalyst_id: str) -> pd.Series:
    group = data[data["catalyst_id"] == catalyst_id]
    if group.empty:
        raise ValueError(f"输入不存在组合：{catalyst_id}")
    fields = [
        "catalyst_description",
        "loading_method",
        "cosio2_mass_mg",
        "co_loading_wt_pct",
        "hap_mass_mg",
        "quartz_mass_mg",
        "ethanol_condition_ml_min",
    ]
    if any(group[field].nunique(dropna=False) != 1 for field in fields):
        raise ValueError(f"{catalyst_id}的完整配方在输入中不唯一")
    return group.iloc[0]


def build_design(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    observed_keys = set(zip(data["catalyst_id"], data["temperature_c"]))
    for item in DESIGN:
        catalyst_id = item["catalyst_id"]
        temperature = float(item["temperature_c"])
        recipe = unique_recipe(data, catalyst_id)
        group = data[data["catalyst_id"] == catalyst_id].sort_values("temperature_c")
        key_exists = (catalyst_id, temperature) in observed_keys
        if key_exists != bool(item["is_repeat_of_existing_condition"]):
            raise ValueError(f"{item['experiment_id']}的新增/重复身份与输入不一致")

        lower = group[group["temperature_c"] < temperature]
        upper = group[group["temperature_c"] > temperature]
        rows.append(
            {
                **item,
                "existing_condition_observation_count": int(
                    ((data["catalyst_id"] == catalyst_id)
                     & (data["temperature_c"] == temperature)).sum()
                ),
                "lower_observed_temperature_c": (
                    float(lower.iloc[-1]["temperature_c"]) if not lower.empty else None
                ),
                "upper_observed_temperature_c": (
                    float(upper.iloc[0]["temperature_c"]) if not upper.empty else None
                ),
                "within_own_observed_temperature_range": bool(
                    float(group["temperature_c"].min()) <= temperature
                    <= float(group["temperature_c"].max())
                ),
                "strict_below_350_eligible": bool(temperature < 350.0),
                "catalyst_description": recipe["catalyst_description"],
                "loading_method": recipe["loading_method"],
                "cosio2_mass_mg": float(recipe["cosio2_mass_mg"]),
                "co_loading_wt_pct": float(recipe["co_loading_wt_pct"]),
                "hap_mass_mg": float(recipe["hap_mass_mg"]),
                "quartz_mass_mg": float(recipe["quartz_mass_mg"]),
                "ethanol_condition_ml_min": float(
                    recipe["ethanol_condition_ml_min"]
                ),
                "future_ethanol_conversion_pct": None,
                "future_c4_selectivity_pct": None,
                "future_c4_yield_pct": None,
                "evidence_status": "planned_experiment_not_observation",
            }
        )
    result = pd.DataFrame(rows)
    if len(result) != 5 or result["experiment_id"].nunique() != 5:
        raise ValueError("正式设计必须恰好包含5个唯一实验ID")
    if not result["within_own_observed_temperature_range"].all():
        raise ValueError("存在组合自身观测范围外的正式实验")
    return result


def anchor(data: pd.DataFrame, catalyst_id: str, temperature_c: float) -> dict:
    row = data[
        (data["catalyst_id"] == catalyst_id)
        & (data["temperature_c"] == temperature_c)
    ]
    if len(row) != 1:
        raise ValueError(f"锚点不唯一：{catalyst_id}@{temperature_c}")
    record = row.iloc[0]
    return {
        "catalyst_id": catalyst_id,
        "temperature_c": temperature_c,
        "ethanol_conversion_pct": float(record["ethanol_conversion_pct"]),
        "c4_selectivity_pct": float(record["c4_selectivity_pct"]),
        "c4_yield_pct": float(record["c4_yield_pct"]),
        "source_excel_row": int(record["source_excel_row"]),
    }


def main() -> None:
    started_at = datetime.now().astimezone()
    OUT.mkdir(parents=True, exist_ok=True)
    data = pd.read_csv(DATA)
    recommendations = pd.read_csv(Q3_RECOMMENDATIONS)
    gaps = pd.read_csv(Q3_GAPS)
    coverage = pd.read_csv(Q3_COVERAGE)
    robustness = json.loads(Q3_ROBUSTNESS.read_text(encoding="utf-8"))

    required = {
        "source_excel_row",
        "catalyst_id",
        "catalyst_description",
        "temperature_c",
        "ethanol_conversion_pct",
        "c4_selectivity_pct",
        "c4_yield_pct",
        "loading_method",
        "cosio2_mass_mg",
        "co_loading_wt_pct",
        "hap_mass_mg",
        "quartz_mass_mg",
        "ethanol_condition_ml_min",
    }
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"清洁输入缺少字段：{sorted(missing)}")
    if len(data) != 114 or data["catalyst_id"].nunique() != 21:
        raise ValueError("清洁输入规模不符合S8规格")
    if data.duplicated(["catalyst_id", "temperature_c"]).any():
        raise ValueError("原输入组合—温度键不唯一")
    formula_error = float(
        (
            data["c4_yield_pct"]
            - data["ethanol_conversion_pct"] * data["c4_selectivity_pct"] / 100
        ).abs().max()
    )
    if formula_error > TOL:
        raise ValueError(f"原输入收率公式误差超限：{formula_error}")

    design = build_design(data)
    expected_responsibilities = {"G1", "G2", "G3", "G4", "G5"}
    actual_responsibilities = {
        code
        for value in design["responsibility_codes"]
        for code in value.split("|")
    }
    if actual_responsibilities != expected_responsibilities:
        raise ValueError("G1—G5职责未完整覆盖")

    design_path = OUT / "experiment_design.csv"
    evidence_path = OUT / "evidence_mapping.csv"
    update_path = OUT / "update_rules.json"
    sequential_path = OUT / "sequential_alternative.json"
    summary_path = OUT / "formal_summary.json"
    design.to_csv(design_path, index=False)
    pd.DataFrame(EVIDENCE).to_csv(evidence_path, index=False)

    anchors = [
        anchor(data, "A3", 350.0),
        anchor(data, "A3", 400.0),
        anchor(data, "A3", 450.0),
        anchor(data, "A2", 325.0),
        anchor(data, "A2", 350.0),
        anchor(data, "A4", 400.0),
    ]
    update_rules = {
        "schema_version": "1.0",
        "status": "pre_observation_rules_no_future_responses",
        "yield_formula": "ethanol_conversion_pct * c4_selectivity_pct / 100",
        "future_response_fields_must_remain_null": [
            "future_ethanol_conversion_pct",
            "future_c4_selectivity_pct",
            "future_c4_yield_pct",
        ],
        "replicate_condition": {
            "catalyst_id": "A3",
            "temperature_c": 400.0,
            "original_c4_yield_pct": anchor(data, "A3", 400.0)["c4_yield_pct"],
            "updated_condition_value": "(original_yield + E4_yield) / 2",
            "also_report": ["E4_yield - original_yield", "absolute_difference"],
            "allowed_claim": "local_descriptive_replication_only",
            "forbidden_claims": [
                "global_error_distribution",
                "significance_test",
                "proof_that_previous_answers_are_correct",
            ],
        },
        "general_scenario": {
            "eligible": "all_observed_conditions_after_experiment",
            "a3_400_representation": "mean_of_original_and_E4",
            "selection": "descending_enumeration_by_observed_c4_yield",
            "predictions_allowed_in_ranking": False,
        },
        "strict_below_350_scenario": {
            "eligible": "observed_conditions_with_temperature_c < 350",
            "selection": "descending_enumeration_by_observed_c4_yield",
            "E3_eligible": True,
            "temperature_350_eligible": False,
        },
        "question2_supplement": {
            "comparison": "E1_A3_375_vs_E5_A4_375",
            "responses": [
                "ethanol_conversion_pct",
                "c4_selectivity_pct",
                "c4_yield_pct",
            ],
            "scope": "375C_only_no_replacement_of_four_common_temperature_model",
        },
        "question1_supplement": {
            "affected_combinations": ["A2", "A3", "A4"],
            "scope": "local_interval_update_only",
        },
        "observed_anchors": anchors,
    }
    update_path.write_text(
        json.dumps(update_rules, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    sequential = {
        "schema_version": "1.0",
        "status": "conditional_alternative_not_formal_one_shot_design",
        "activation_condition": (
            "only_if_results_are_available_before_scheduling_later_experiments"
        ),
        "budget": 5,
        "stage1_fixed": ["A3@375", "A3@425", "A2@337.5"],
        "run4_rule": (
            "repeat the observed highest-yield A3 condition among "
            "350, 375, 400, 425 and 450 C"
        ),
        "run5_rule": (
            "if A2@337.5 changes the strict-low recommendation or reverses "
            "the prior A2 325-to-350 increasing relation, repeat the updated "
            "A2 strict-low best; otherwise run A4@375"
        ),
        "significance_threshold_used": False,
        "may_not_be_combined_with_formal_one_shot_as_seven_runs": True,
    }
    sequential_path.write_text(
        json.dumps(sequential, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    general = recommendations[recommendations["scenario"] == "general"].iloc[0]
    low = recommendations[
        recommendations["scenario"] == "strict_below_350"
    ].iloc[0]
    general_gap = gaps[gaps["scenario"] == "general"].iloc[0]
    low_gap = gaps[gaps["scenario"] == "strict_below_350"].iloc[0]
    summary = {
        "schema_version": "1.0",
        "status": "s9_formal_design_generated_pending_s10_verification",
        "producer": str(SCRIPT.relative_to(ROOT)),
        "formal_policy": "one_shot_evidence_directed_five_run_design",
        "experiment_count": 5,
        "experiment_ids": design["experiment_id"].tolist(),
        "future_responses_created": False,
        "responsibilities_covered": sorted(actual_responsibilities),
        "upstream_frozen_facts": {
            "general_recommendation": {
                "catalyst_id": general["best_catalyst_id"],
                "temperature_c": float(general["best_temperature_c"]),
                "c4_yield_pct": float(general["best_c4_yield_pct"]),
                "lead_over_runner_up_pct_point": float(
                    general_gap["lead_over_runner_up_pct_point"]
                ),
                "lead_over_best_distinct_combination_pct_point": float(
                    general_gap["lead_over_best_distinct_combination_pct_point"]
                ),
            },
            "strict_low_recommendation": {
                "catalyst_id": low["best_catalyst_id"],
                "temperature_c": float(low["best_temperature_c"]),
                "c4_yield_pct": float(low["best_c4_yield_pct"]),
                "lead_over_best_distinct_combination_pct_point": float(
                    low_gap["lead_over_best_distinct_combination_pct_point"]
                ),
            },
            "coverage_325": int(
                coverage.loc[
                    coverage["temperature_c"] == 325.0,
                    "observed_combination_count",
                ].iloc[0]
            ),
            "coverage_450": int(
                coverage.loc[
                    coverage["temperature_c"] == 450.0,
                    "observed_combination_count",
                ].iloc[0]
            ),
            "pchip_worst_holdout_error_pct_point": float(
                robustness["interior_holdout"]["pchip"]["max_ae_pct_point"]
            ),
        },
        "claim_boundaries": [
            "本产物是实验计划，不是已经执行的实验结果",
            "五次实验由前三问证据缺口推出，不声称全局唯一最优",
            "一次重复只支持关键条件的局部描述性复现",
            "375摄氏度A3/A4比较只支持该温度",
            "新增非均衡点不替代第二问四共同温度主体模型",
            "不拟合完整响应面，不采用贝叶斯优化，不生成预测响应",
            "337.5摄氏度正式执行前须确认设备控温能力",
        ],
        "run": {
            "started_at": started_at.isoformat(),
            "finished_at": datetime.now().astimezone().isoformat(),
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "random_seed": None,
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    manifest_rows = []
    for path, role, description in [
        (DATA, "input", "附件1冻结清洁输入"),
        (Q3_RECOMMENDATIONS, "input", "第三问正式推荐"),
        (Q3_GAPS, "input", "第三问排序差距"),
        (Q3_COVERAGE, "input", "第三问温度覆盖"),
        (Q3_ROBUSTNESS, "input", "第三问稳健性摘要"),
        (SCRIPT, "source", "第四问S9正式实现"),
        (design_path, "output", "正式五次实验完整条件"),
        (evidence_path, "output", "前三问证据与实验职责映射"),
        (update_path, "output", "观测后更新规则"),
        (sequential_path, "output", "条件序贯备选"),
        (summary_path, "output", "正式设计摘要"),
    ]:
        manifest_rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "role": role,
                "description": description,
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    pd.DataFrame(manifest_rows).to_csv(
        OUT / "artifact_manifest.csv", index=False
    )

    print("第四问S9正式设计生成完成")
    print(design[["experiment_id", "catalyst_id", "temperature_c",
                  "is_repeat_of_existing_condition", "responsibility_codes"]]
          .to_string(index=False))
    print("状态：等待S10独立验证；未生成未来实验响应")


if __name__ == "__main__":
    main()
