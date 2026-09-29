#!/usr/bin/env python3
"""第四问S10独立验证：不导入S9，复核正式五次实验及全部边界。"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import platform
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
Q3_RECOMMENDATIONS = ROOT / "output" / "q3" / "formal" / "recommendations.csv"
Q3_GAPS = ROOT / "output" / "q3" / "robustness" / "ranking_gaps.csv"
Q3_COVERAGE = ROOT / "output" / "q3" / "robustness" / "temperature_coverage.csv"
Q3_ROBUSTNESS = ROOT / "output" / "q3" / "robustness" / "robustness_summary.json"
OUT = ROOT / "output" / "q4" / "formal"
DESIGN_PATH = OUT / "experiment_design.csv"
EVIDENCE_PATH = OUT / "evidence_mapping.csv"
UPDATE_PATH = OUT / "update_rules.json"
SEQUENTIAL_PATH = OUT / "sequential_alternative.json"
SUMMARY_PATH = OUT / "formal_summary.json"
MANIFEST_PATH = OUT / "artifact_manifest.csv"
VERIFY_PATH = OUT / "verification.json"
TOL = 1e-9

EXPECTED = {
    "E1": ("A3", 375.0, False, {"G2", "G5"}),
    "E2": ("A3", 425.0, False, {"G3"}),
    "E3": ("A2", 337.5, False, {"G4"}),
    "E4": ("A3", 400.0, True, {"G1"}),
    "E5": ("A4", 375.0, False, {"G5"}),
}
RECIPE_FIELDS = [
    "catalyst_description",
    "loading_method",
    "cosio2_mass_mg",
    "co_loading_wt_pct",
    "hap_mass_mg",
    "quartz_mass_mg",
    "ethanol_condition_ml_min",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def close(left: float, right: float, tol: float = TOL) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=tol)


def condition_map(data: list[dict[str, str]]) -> dict[tuple[str, float], dict]:
    result: dict[tuple[str, float], dict] = {}
    for row in data:
        key = (row["catalyst_id"], float(row["temperature_c"]))
        if key in result:
            raise AssertionError(f"原输入键重复：{key}")
        result[key] = row
    return result


def recipe_map(data: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for row in data:
        catalyst = row["catalyst_id"]
        recipe = {field: row[field] for field in RECIPE_FIELDS}
        if catalyst in result and result[catalyst] != recipe:
            raise AssertionError(f"{catalyst}配方不唯一")
        result[catalyst] = recipe
    return result


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    started = datetime.now().astimezone()
    data = read_csv(DATA)
    design = read_csv(DESIGN_PATH)
    evidence = read_csv(EVIDENCE_PATH)
    recommendations = read_csv(Q3_RECOMMENDATIONS)
    gaps = read_csv(Q3_GAPS)
    coverage = read_csv(Q3_COVERAGE)
    manifest = read_csv(MANIFEST_PATH)
    update = json.loads(UPDATE_PATH.read_text(encoding="utf-8"))
    sequential = json.loads(SEQUENTIAL_PATH.read_text(encoding="utf-8"))
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    robustness = json.loads(Q3_ROBUSTNESS.read_text(encoding="utf-8"))
    conditions = condition_map(data)
    recipes = recipe_map(data)
    checks: list[dict] = []

    # 1. 五行与唯一ID
    ids = [row["experiment_id"] for row in design]
    check(len(design) == 5 and set(ids) == set(EXPECTED) and len(set(ids)) == 5,
          "正式设计不是5个唯一E1—E5")
    checks.append({"id": 1, "name": "five_unique_experiments", "passed": True})

    # 2. 组合域
    valid_catalysts = set(recipes)
    check(len(valid_catalysts) == 21, "原输入不是21种组合")
    check(all(row["catalyst_id"] in valid_catalysts for row in design),
          "设计含未知组合")
    checks.append({"id": 2, "name": "existing_21_combination_domain", "passed": True})

    # 3. 配方一致性
    for row in design:
        expected_recipe = recipes[row["catalyst_id"]]
        for field in RECIPE_FIELDS:
            if field in {"catalyst_description", "loading_method"}:
                check(row[field] == expected_recipe[field],
                      f"{row['experiment_id']}的{field}不一致")
            else:
                check(close(float(row[field]), float(expected_recipe[field])),
                      f"{row['experiment_id']}的{field}不一致")
    checks.append({"id": 3, "name": "full_recipe_matches_clean_input", "passed": True})

    # 4. 新条件与重复身份
    for row in design:
        experiment_id = row["experiment_id"]
        catalyst, temperature, is_repeat, responsibilities = EXPECTED[experiment_id]
        check(row["catalyst_id"] == catalyst
              and close(float(row["temperature_c"]), temperature),
              f"{experiment_id}条件偏离S8")
        parsed_repeat = row["is_repeat_of_existing_condition"].lower() == "true"
        check(parsed_repeat == is_repeat, f"{experiment_id}重复标记错误")
        exists = (catalyst, temperature) in conditions
        check(exists == is_repeat, f"{experiment_id}新增/已有身份错误")
        expected_count = 1 if is_repeat else 0
        check(int(row["existing_condition_observation_count"]) == expected_count,
              f"{experiment_id}已有观测数错误")
        check(set(row["responsibility_codes"].split("|")) == responsibilities,
              f"{experiment_id}职责代码错误")
    checks.append({"id": 4, "name": "four_new_cells_and_one_exact_repeat", "passed": True})

    # 5. 375摄氏度配对
    by_id = {row["experiment_id"]: row for row in design}
    check(by_id["E1"]["catalyst_id"] == "A3"
          and by_id["E5"]["catalyst_id"] == "A4"
          and close(float(by_id["E1"]["temperature_c"]), 375.0)
          and close(float(by_id["E5"]["temperature_c"]), 375.0),
          "E1/E5不是A3/A4同温配对")
    checks.append({"id": 5, "name": "a3_a4_same_temperature_pair", "passed": True})

    # 6. 严格低温边界
    check(close(float(by_id["E3"]["temperature_c"]), 337.5)
          and float(by_id["E3"]["temperature_c"]) < 350.0
          and by_id["E3"]["strict_below_350_eligible"].lower() == "true",
          "E3不满足严格低温")
    checks.append({"id": 6, "name": "strict_below_350_boundary", "passed": True})

    # 7. 新中点均由同组合实测值包围
    expected_brackets = {
        "E1": (350.0, 400.0),
        "E2": (400.0, 450.0),
        "E3": (325.0, 350.0),
        "E5": (350.0, 400.0),
    }
    for experiment_id, (lower, upper) in expected_brackets.items():
        row = by_id[experiment_id]
        check(close(float(row["lower_observed_temperature_c"]), lower)
              and close(float(row["upper_observed_temperature_c"]), upper)
              and (row["catalyst_id"], lower) in conditions
              and (row["catalyst_id"], upper) in conditions,
              f"{experiment_id}包围温度错误")
    checks.append({"id": 7, "name": "new_temperatures_bracketed_by_observations", "passed": True})

    # 8. 职责覆盖与证据映射
    all_responsibilities = {
        code for row in design for code in row["responsibility_codes"].split("|")
    }
    check(all_responsibilities == {"G1", "G2", "G3", "G4", "G5"},
          "G1—G5未完整覆盖")
    check({row["experiment_id"] for row in evidence} == set(EXPECTED)
          and len(evidence) == 5
          and all(row["evidence_gap"] and row["possible_update"] for row in evidence),
          "证据映射不完整")
    checks.append({"id": 8, "name": "responsibilities_and_evidence_mapping", "passed": True})

    # 9. 锚点和上游冻结事实
    for row in data:
        calculated = float(row["ethanol_conversion_pct"]) * float(
            row["c4_selectivity_pct"]
        ) / 100.0
        check(close(calculated, float(row["c4_yield_pct"])),
              "原输入收率公式不一致")
    anchor_map = {
        (item["catalyst_id"], float(item["temperature_c"])): item
        for item in update["observed_anchors"]
    }
    for key, item in anchor_map.items():
        source = conditions[key]
        check(close(item["c4_yield_pct"], float(source["c4_yield_pct"]))
              and close(item["ethanol_conversion_pct"],
                        float(source["ethanol_conversion_pct"]))
              and close(item["c4_selectivity_pct"],
                        float(source["c4_selectivity_pct"])),
              f"锚点{key}与清洁输入不一致")
    general_rec = next(row for row in recommendations if row["scenario"] == "general")
    low_rec = next(
        row for row in recommendations if row["scenario"] == "strict_below_350"
    )
    general_gap = next(row for row in gaps if row["scenario"] == "general")
    low_gap = next(row for row in gaps if row["scenario"] == "strict_below_350")
    facts = summary["upstream_frozen_facts"]
    check(facts["general_recommendation"]["catalyst_id"]
          == general_rec["best_catalyst_id"]
          and close(facts["general_recommendation"]["c4_yield_pct"],
                    float(general_rec["best_c4_yield_pct"]))
          and close(facts["general_recommendation"]["lead_over_runner_up_pct_point"],
                    float(general_gap["lead_over_runner_up_pct_point"])),
          "一般情景锚点不一致")
    check(facts["strict_low_recommendation"]["catalyst_id"]
          == low_rec["best_catalyst_id"]
          and close(facts["strict_low_recommendation"]["c4_yield_pct"],
                    float(low_rec["best_c4_yield_pct"]))
          and close(
              facts["strict_low_recommendation"][
                  "lead_over_best_distinct_combination_pct_point"
              ],
              float(low_gap["lead_over_best_distinct_combination_pct_point"]),
          ),
          "低温情景锚点不一致")
    coverage_map = {
        float(row["temperature_c"]): int(row["observed_combination_count"])
        for row in coverage
    }
    check(facts["coverage_325"] == coverage_map[325.0]
          and facts["coverage_450"] == coverage_map[450.0]
          and close(facts["pchip_worst_holdout_error_pct_point"],
                    robustness["interior_holdout"]["pchip"]["max_ae_pct_point"]),
          "覆盖或稳健性锚点不一致")
    checks.append({"id": 9, "name": "upstream_anchors_independently_recomputed", "passed": True})

    # 10. 不含未来结果、预测或显著性阈值
    future_fields = [
        "future_ethanol_conversion_pct",
        "future_c4_selectivity_pct",
        "future_c4_yield_pct",
    ]
    check(all(all(row[field] == "" for field in future_fields) for row in design),
          "设计文件出现未来响应")
    check(summary["future_responses_created"] is False
          and update["general_scenario"]["predictions_allowed_in_ranking"] is False
          and "significance_test"
          in update["replicate_condition"]["forbidden_claims"],
          "更新规则允许预测或显著性越界")
    checks.append({"id": 10, "name": "no_future_response_or_unapproved_inference", "passed": True})

    # 11. 序贯条件与总预算
    check(sequential["budget"] == 5
          and len(sequential["stage1_fixed"]) == 3
          and sequential["activation_condition"].startswith("only_if_results")
          and sequential["significance_threshold_used"] is False
          and sequential["may_not_be_combined_with_formal_one_shot_as_seven_runs"]
          is True,
          "序贯备选边界或预算错误")
    checks.append({"id": 11, "name": "conditional_sequential_budget_and_boundary", "passed": True})

    # 12. 结构化文件和清单哈希
    manifest_paths = {row["path"]: row for row in manifest}
    check(len(manifest) == 11 and len(manifest_paths) == 11,
          "正式清单条目数或路径不唯一")
    for relative, row in manifest_paths.items():
        path = ROOT / relative
        check(path.exists(), f"清单文件不存在：{relative}")
        check(sha256(path) == row["sha256"], f"哈希不一致：{relative}")
        check(path.stat().st_size == int(row["size_bytes"]),
              f"大小不一致：{relative}")
    checks.append({"id": 12, "name": "structured_artifacts_and_manifest_hashes", "passed": True})

    result = {
        "schema_version": "1.0",
        "status": "q4_s10_independent_verification_passed",
        "independent_of_s9_import": True,
        "verification_count": len(checks),
        "passed_count": sum(item["passed"] for item in checks),
        "all_passed": all(item["passed"] for item in checks),
        "checks": checks,
        "max_numeric_tolerance": TOL,
        "run": {
            "started_at": started.isoformat(),
            "finished_at": datetime.now().astimezone().isoformat(),
            "python": platform.python_version(),
            "random_seed": None,
        },
    }
    VERIFY_PATH.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"第四问S10独立验证：{result['passed_count']}/{len(checks)}通过")
    for item in checks:
        print(f"[PASS] {item['id']:02d} {item['name']}")


if __name__ == "__main__":
    main()
