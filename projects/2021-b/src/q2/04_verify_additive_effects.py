#!/usr/bin/env python3
"""第二问S10：不导入正式程序，独立核对修订S8的数学与回答产物。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUT = ROOT / "output/q2"
TABLES = OUT / "tables"
COMMON_TEMPERATURES = [250.0, 275.0, 300.0, 350.0]
RESPONSES = ["ethanol_conversion_pct", "c4_selectivity_pct"]


def add_check(checks: list[dict], name: str, passed: bool, detail: str) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def max_abs(values: list[float]) -> float:
    return float(max(values)) if values else 0.0


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    data = pd.read_csv(INPUT)
    common = data[data["temperature_c"].isin(COMMON_TEMPERATURES)].copy()
    decomposition = pd.read_csv(TABLES / "additive_decomposition.csv").set_index("response")
    combinations = pd.read_csv(TABLES / "additive_combination_effects.csv")
    temperatures = pd.read_csv(TABLES / "additive_temperature_effects.csv")
    cells = pd.read_csv(TABLES / "additive_cell_residuals.csv")
    answers = pd.read_csv(TABLES / "question2_answer_summary.csv")
    profiles = pd.read_csv(TABLES / "combination_adjusted_profiles.csv")
    nonadditive = pd.read_csv(TABLES / "nonadditive_combination_summary.csv")
    paired = pd.read_csv(TABLES / "common_temperature_paired_change_summary.csv")
    ranks = pd.read_csv(TABLES / "common_temperature_rank_stability.csv")
    candidate = pd.read_csv(
        OUT / "candidates/candidate_information_comparison.csv"
    ).set_index("response")
    a_verification = json.loads((OUT / "verification.json").read_text(encoding="utf-8"))
    formal_summary = json.loads((OUT / "formal_summary.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUT / "artifact_manifest.csv")
    checks: list[dict] = []

    coverage = common.groupby("temperature_c")["catalyst_id"].nunique().to_dict()
    per_combination = common.groupby("catalyst_id")["temperature_c"].nunique()
    add_check(
        checks,
        "1 主体域覆盖",
        len(common) == 84
        and coverage == {temperature: 21 for temperature in COMMON_TEMPERATURES}
        and len(per_combination) == 21
        and per_combination.eq(4).all(),
        f"cells={len(common)}, temperatures={coverage}, combinations={len(per_combination)}",
    )

    mean_errors = []
    for response in RESPONSES:
        saved = decomposition.loc[response]
        mean_errors.append(abs(float(common[response].mean()) - saved["grand_mean_pct"]))
        saved_combinations = combinations[
            combinations["response"] == response
        ].set_index("catalyst_id")
        for catalyst_id, value in common.groupby("catalyst_id")[response].mean().items():
            mean_errors.append(
                abs(float(value) - saved_combinations.loc[catalyst_id, "combination_mean_pct"])
            )
        saved_temperatures = temperatures[
            temperatures["response"] == response
        ].set_index("temperature_c")
        for temperature, value in common.groupby("temperature_c")[response].mean().items():
            mean_errors.append(
                abs(float(value) - saved_temperatures.loc[temperature, "temperature_mean_pct"])
            )
    add_check(
        checks,
        "2 均值独立复算",
        max_abs(mean_errors) <= 1e-10,
        f"max_abs_error={max_abs(mean_errors):.3e}",
    )

    effect_sums = []
    for response in RESPONSES:
        effect_sums.extend(
            [
                abs(
                    float(
                        combinations[combinations["response"] == response][
                            "combination_effect_pct_point"
                        ].sum()
                    )
                ),
                abs(
                    float(
                        temperatures[temperatures["response"] == response][
                            "temperature_effect_pct_point"
                        ].sum()
                    )
                ),
            ]
        )
    add_check(
        checks,
        "3 和为零约束",
        max_abs(effect_sums) <= 1e-10,
        f"max_abs_sum={max_abs(effect_sums):.3e}",
    )

    reconstruction_errors = []
    for row in cells.itertuples(index=False):
        source = common[
            (common["catalyst_id"] == row.catalyst_id)
            & (common["temperature_c"] == row.temperature_c)
        ][row.response]
        reconstruction_errors.extend(
            [
                abs(float(source.iloc[0]) - row.observed_pct),
                abs(
                    row.observed_pct
                    - row.additive_fitted_pct
                    - row.nonadditive_residual_pct_point
                ),
            ]
        )
    add_check(
        checks,
        "4 单元重构",
        len(cells) == 168 and max_abs(reconstruction_errors) <= 1e-10,
        f"rows={len(cells)}, max_abs_error={max_abs(reconstruction_errors):.3e}",
    )

    ss_errors = []
    independent_values: dict[str, dict[str, float]] = {}
    for response in RESPONSES:
        grand = float(common[response].mean())
        combination_mean = common.groupby("catalyst_id")[response].mean()
        temperature_mean = common.groupby("temperature_c")[response].mean()
        total_ss = float(np.sum((common[response] - grand) ** 2))
        combination_ss = float(4 * np.sum((combination_mean - grand) ** 2))
        temperature_ss = float(21 * np.sum((temperature_mean - grand) ** 2))
        nonadditive_ss = total_ss - combination_ss - temperature_ss
        independent_values[response] = {
            "total_ss": total_ss,
            "combination_ss": combination_ss,
            "temperature_ss": temperature_ss,
            "nonadditive_ss": nonadditive_ss,
        }
        saved = decomposition.loc[response]
        ss_errors.extend(
            [
                abs(total_ss - saved["total_ss"]),
                abs(combination_ss - saved["combination_ss"]),
                abs(temperature_ss - saved["temperature_ss"]),
                abs(nonadditive_ss - saved["nonadditive_ss"]),
                abs(
                    saved["total_ss"]
                    - saved["combination_ss"]
                    - saved["temperature_ss"]
                    - saved["nonadditive_ss"]
                ),
            ]
        )
    add_check(
        checks,
        "5 平方和独立复算与闭合",
        max_abs(ss_errors) <= 1e-9,
        f"max_abs_error={max_abs(ss_errors):.3e}",
    )

    share_errors = []
    for response in RESPONSES:
        saved = decomposition.loc[response]
        values = independent_values[response]
        share_errors.extend(
            [
                abs(saved["combination_share"] - values["combination_ss"] / values["total_ss"]),
                abs(saved["temperature_share"] - values["temperature_ss"] / values["total_ss"]),
                abs(saved["nonadditive_share"] - values["nonadditive_ss"] / values["total_ss"]),
                abs(
                    saved["combination_share"]
                    + saved["temperature_share"]
                    + saved["nonadditive_share"]
                    - 1
                ),
            ]
        )
    add_check(
        checks,
        "6 占比复算与闭合",
        max_abs(share_errors) <= 1e-12,
        f"max_abs_error={max_abs(share_errors):.3e}",
    )

    candidate_errors = []
    mapping = {
        "total_ss": "total_ss",
        "combination_ss": "combination_ss",
        "temperature_ss": "temperature_ss",
        "nonadditive_ss": "additive_nonadditive_ss",
    }
    for response in RESPONSES:
        formal = decomposition.loc[response]
        pilot = candidate.loc[response]
        for formal_field, candidate_field in mapping.items():
            candidate_errors.append(abs(formal[formal_field] - pilot[candidate_field]))
    add_check(
        checks,
        "7 S6同口径结果一致",
        max_abs(candidate_errors) <= 1e-9,
        f"max_abs_error={max_abs(candidate_errors):.3e}",
    )

    add_check(
        checks,
        "8 A层既有验证",
        a_verification.get("passed") is True
        and len(a_verification.get("checks", [])) == 5
        and all(item.get("passed") is True for item in a_verification["checks"]),
        f"passed={a_verification.get('passed')}, checks={len(a_verification.get('checks', []))}",
    )

    b_temperatures = set(temperatures["temperature_c"].astype(float))
    cell_temperatures = set(cells["temperature_c"].astype(float))
    add_check(
        checks,
        "9 非平衡温度排除",
        b_temperatures == set(COMMON_TEMPERATURES)
        and cell_temperatures == set(COMMON_TEMPERATURES)
        and set(formal_summary["common_temperatures_c"]) == set(COMMON_TEMPERATURES),
        f"effect_temperatures={sorted(b_temperatures)}, cell_temperatures={sorted(cell_temperatures)}",
    )

    profile_errors = []
    for row in profiles.itertuples(index=False):
        effect = combinations[
            (combinations["response"] == row.response)
            & (combinations["catalyst_id"] == row.catalyst_id)
        ].iloc[0]
        rank = ranks[
            (ranks["response"] == row.response)
            & (ranks["catalyst_id"] == row.catalyst_id)
        ].iloc[0]
        profile_errors.extend(
            [
                abs(row.combination_mean_pct - effect["combination_mean_pct"]),
                abs(
                    row.combination_effect_pct_point
                    - effect["combination_effect_pct_point"]
                ),
                abs(row.mean_rank - rank["mean_rank"]),
                abs(row.rank_range - rank["rank_range"]),
                abs(row.top5_count - rank["top5_count"]),
                abs(row.bottom5_count - rank["bottom5_count"]),
            ]
        )
    add_check(
        checks,
        "10 调整后组合画像独立拼接",
        len(profiles) == 42 and max_abs(profile_errors) <= 1e-12,
        f"rows={len(profiles)}, max_abs_error={max_abs(profile_errors):.3e}",
    )

    residual_errors = []
    for row in nonadditive.itertuples(index=False):
        subset = cells[
            (cells["response"] == row.response)
            & (cells["catalyst_id"] == row.catalyst_id)
        ]
        independent_rms = float(
            np.sqrt(np.mean(subset["nonadditive_residual_pct_point"] ** 2))
        )
        maximum = subset.loc[
            subset["absolute_nonadditive_residual_pct_point"].idxmax()
        ]
        residual_errors.extend(
            [
                abs(row.residual_rms_pct_point - independent_rms),
                abs(
                    row.max_absolute_residual_pct_point
                    - maximum["absolute_nonadditive_residual_pct_point"]
                ),
                abs(row.max_residual_temperature_c - maximum["temperature_c"]),
                abs(
                    row.signed_residual_at_max_pct_point
                    - maximum["nonadditive_residual_pct_point"]
                ),
            ]
        )
    add_check(
        checks,
        "11 非加和组合汇总独立复算",
        len(nonadditive) == 42 and max_abs(residual_errors) <= 1e-12,
        f"rows={len(nonadditive)}, max_abs_error={max_abs(residual_errors):.3e}",
    )

    answer_errors = []
    temperature_answers = answers[
        answers["question_aspect"] == "temperature_influence"
    ]
    for item in paired.itertuples(index=False):
        key = f"{item.temperature_from_c:g}-{item.temperature_to_c:g}C paired combinations"
        saved = temperature_answers[
            (temperature_answers["response"] == item.response)
            & (temperature_answers["evidence_unit"] == key)
        ].iloc[0]
        answer_errors.extend(
            [
                abs(
                    saved["primary_value"]
                    - item.positive_count / item.paired_combination_count
                ),
                abs(saved["secondary_value"] - item.median_change_pct_point),
            ]
        )
    for response in RESPONSES:
        saved_decomposition = decomposition.loc[response]
        combination_answer = answers[
            (answers["question_aspect"] == "combination_influence")
            & (answers["response"] == response)
        ].iloc[0]
        joint_answer = answers[
            (answers["question_aspect"] == "joint_variation")
            & (answers["response"] == response)
        ].iloc[0]
        highest = combinations[
            combinations["response"] == response
        ].nlargest(1, "combination_effect_pct_point").iloc[0]
        maximum = cells[cells["response"] == response].nlargest(
            1, "absolute_nonadditive_residual_pct_point"
        ).iloc[0]
        answer_errors.extend(
            [
                abs(
                    combination_answer["primary_value"]
                    - saved_decomposition["combination_share"]
                ),
                abs(
                    combination_answer["secondary_value"]
                    - highest["combination_effect_pct_point"]
                ),
                abs(
                    joint_answer["primary_value"]
                    - saved_decomposition["nonadditive_share"]
                ),
                abs(
                    joint_answer["secondary_value"]
                    - maximum["absolute_nonadditive_residual_pct_point"]
                ),
            ]
        )
    summary_has_answers = all(
        set(value.get("answers", {}))
        == {"temperature_influence", "combination_influence", "joint_variation"}
        for value in formal_summary["responses"].values()
    )
    add_check(
        checks,
        "12 题目直接回答表与摘要复算",
        len(answers) == 10
        and max_abs(answer_errors) <= 1e-12
        and summary_has_answers,
        (
            f"rows={len(answers)}, max_abs_error={max_abs(answer_errors):.3e}, "
            f"summary_has_answers={summary_has_answers}"
        ),
    )

    expected_files = {
        "output/q2/tables/additive_decomposition.csv",
        "output/q2/tables/additive_combination_effects.csv",
        "output/q2/tables/additive_temperature_effects.csv",
        "output/q2/tables/additive_cell_residuals.csv",
        "output/q2/tables/question2_answer_summary.csv",
        "output/q2/tables/combination_adjusted_profiles.csv",
        "output/q2/tables/nonadditive_combination_summary.csv",
        "output/q2/formal_summary.json",
        "output/q2/figures/01_additive_combination_effects.png",
        "output/q2/figures/01_additive_combination_effects.pdf",
        "output/q2/figures/02_additive_temperature_effects.png",
        "output/q2/figures/02_additive_temperature_effects.pdf",
        "output/q2/figures/03_nonadditive_residual_heatmaps.png",
        "output/q2/figures/03_nonadditive_residual_heatmaps.pdf",
    }
    manifest_paths = set(manifest["relative_path"])
    manifest_hash_errors = []
    for row in manifest.itertuples(index=False):
        path = ROOT / row.relative_path
        manifest_hash_errors.append(path.exists() and sha256(path) == row.sha256)
    required_boundaries = {
        "影响仅指现有实验域内条件差异或关联",
        "完整组合不拆成配方成分的独立作用",
        "非加和剩余不称为纯交互或随机误差",
        "不进行普通交互显著性检验",
        "不预测未测温度或新组合",
    }
    add_check(
        checks,
        "13 输出合同、哈希与声明边界",
        expected_files.issubset(manifest_paths)
        and all(manifest_hash_errors)
        and required_boundaries.issubset(set(formal_summary["claim_boundaries"]))
        and formal_summary["method"]
        == "A direct evidence plus B fixed combination-temperature additive decomposition",
        (
            f"expected_files={len(expected_files & manifest_paths)}/{len(expected_files)}, "
            f"hashes={sum(manifest_hash_errors)}/{len(manifest_hash_errors)}, "
            f"boundaries={len(required_boundaries & set(formal_summary['claim_boundaries']))}/5"
        ),
    )

    result = {
        "status": "q2_revised_s10_independent_verification",
        "passed": bool(all(item["passed"] for item in checks)),
        "check_count": len(checks),
        "checks": checks,
        "tolerances": {
            "effect_sum": 1e-10,
            "cell_reconstruction": 1e-10,
            "sum_of_squares": 1e-9,
            "share_closure": 1e-12,
            "candidate_consistency": 1e-9,
        },
        "note": "数值容差只用于浮点计算一致性，不代表实验测量精度。",
    }
    (OUT / "formal_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    refreshed_manifest = pd.read_csv(OUT / "artifact_manifest.csv")
    refreshed_manifest = refreshed_manifest[
        ~refreshed_manifest["relative_path"].isin(
            ["output/q2/verification.json", "output/q2/formal_verification.json"]
        )
    ]
    verification_rows = pd.DataFrame(
        [
            {
                "relative_path": "output/q2/verification.json",
                "sha256": sha256(OUT / "verification.json"),
                "producer": "src/q2/02_verify_common_temperature_baseline.py",
            },
            {
                "relative_path": "output/q2/formal_verification.json",
                "sha256": sha256(OUT / "formal_verification.json"),
                "producer": "src/q2/04_verify_additive_effects.py",
            },
        ]
    )
    pd.concat([refreshed_manifest, verification_rows], ignore_index=True).to_csv(
        OUT / "artifact_manifest.csv", index=False
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
