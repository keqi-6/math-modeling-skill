#!/usr/bin/env python3
"""独立复核受控配方因素候选，不导入候选主程序。

# 输入: cleaned_attachment1.csv 与 controlled_factor_sequences 候选产物
# 输出: output/q2/candidates/controlled_factor_sequences/verification.json
# 职责: 独立复算对照合同、均值、端点差、删温度方向、匹配配方差和产物哈希。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUT = ROOT / "output/q2/candidates/controlled_factor_sequences"
TEMPERATURES = [250.0, 275.0, 300.0, 350.0]
SEQUENCES = {
    "co_loading": (["A4", "A1", "A2", "A6"], "co_loading_wt_pct"),
    "ethanol_condition": (
        ["A7", "A8", "A12", "A9"],
        "ethanol_condition_ml_min",
    ),
    "active_mass": (
        ["B3", "B4", "B1", "B6", "B2"],
        "active_catalyst_mass_mg",
    ),
    "hap_fraction": (["A14", "A12", "A13"], "hap_mass_fraction"),
}
RESPONSES = ["ethanol_conversion_pct", "c4_selectivity_pct"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add(checks: list[dict], name: str, passed: bool, detail: str) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def main() -> None:
    data = pd.read_csv(INPUT)
    common = data[data["temperature_c"].isin(TEMPERATURES)].copy()
    levels = pd.read_csv(OUT / "sequence_level_effects.csv")
    summaries = pd.read_csv(OUT / "sequence_summaries.csv")
    method_detail = pd.read_csv(OUT / "loading_method_pair_details.csv")
    method_summary = pd.read_csv(OUT / "loading_method_pair_summaries.csv")
    summary_json = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    manifest = pd.read_csv(OUT / "artifact_manifest.csv")
    checks: list[dict] = []

    coverage = common.groupby("catalyst_id")["temperature_c"].nunique()
    add(
        checks,
        "1 共同温度接口",
        len(common) == 84 and len(coverage) == 21 and coverage.eq(4).all(),
        f"rows={len(common)}, combinations={len(coverage)}",
    )

    contract_ok = all(
        item["passed"] and not item["violations"]
        for item in summary_json["sequence_contracts"]
    )
    add(
        checks,
        "2 对照序列合同",
        contract_ok and len(summary_json["sequence_contracts"]) == 4,
        f"contracts={len(summary_json['sequence_contracts'])}",
    )

    mean_errors = []
    effect_sum_errors = []
    contrast_errors = []
    stability_matches = []
    for sequence, (ids, level_field) in SEQUENCES.items():
        recipe = common.drop_duplicates("catalyst_id").set_index("catalyst_id")
        factor = recipe.loc[ids, level_field].astype(float).sort_values()
        for response in RESPONSES:
            matrix = common[common["catalyst_id"].isin(ids)].pivot(
                index="catalyst_id", columns="temperature_c", values=response
            ).loc[ids, TEMPERATURES]
            means = matrix.mean(axis=1)
            saved = levels[
                (levels["sequence"] == sequence) & (levels["response"] == response)
            ].set_index("catalyst_id")
            for catalyst_id in ids:
                mean_errors.append(
                    abs(
                        float(means.loc[catalyst_id])
                        - saved.loc[catalyst_id, "four_temperature_mean_pct"]
                    )
                )
            effect_sum_errors.append(
                abs(float(saved["subset_adjusted_effect_pct_point"].sum()))
            )
            full_contrast = float(means.loc[factor.index[-1]] - means.loc[factor.index[0]])
            row = summaries[
                (summaries["sequence"] == sequence)
                & (summaries["response"] == response)
            ].iloc[0]
            contrast_errors.append(abs(full_contrast - row["endpoint_contrast_pct_point"]))
            deletion = []
            for omitted in TEMPERATURES:
                reduced = matrix[
                    [temperature for temperature in TEMPERATURES if temperature != omitted]
                ].mean(axis=1)
                deletion.append(
                    float(reduced.loc[factor.index[-1]] - reduced.loc[factor.index[0]])
                )
            stable = all(value > 0 for value in deletion) or all(
                value < 0 for value in deletion
            )
            stability_matches.append(stable == bool(row["endpoint_direction_stable"]))
    add(checks, "3 四温度均值复算", max(mean_errors) < 1e-10, f"max={max(mean_errors):.3e}")
    add(
        checks,
        "4 调整效应和为零",
        max(effect_sum_errors) < 1e-10,
        f"max={max(effect_sum_errors):.3e}",
    )
    add(
        checks,
        "5 端点差与删温度方向",
        max(contrast_errors) < 1e-10 and all(stability_matches),
        f"contrast_max={max(contrast_errors):.3e}, stability={sum(stability_matches)}/8",
    )

    method_errors = []
    method_count_errors = []
    for pair in ["A12-B1", "A9-B5"]:
        left, right = pair.split("-")
        for response in RESPONSES:
            left_values = (
                common[common["catalyst_id"] == left]
                .set_index("temperature_c")
                .loc[TEMPERATURES, response]
            )
            right_values = (
                common[common["catalyst_id"] == right]
                .set_index("temperature_c")
                .loc[TEMPERATURES, response]
            )
            differences = right_values - left_values
            saved_detail = method_detail[
                (method_detail["pair"] == pair)
                & (method_detail["response"] == response)
            ].set_index("temperature_c")
            method_errors.extend(
                abs(
                    differences
                    - saved_detail.loc[
                        TEMPERATURES, "method_ii_minus_i_pct_point"
                    ]
                ).tolist()
            )
            saved_summary = method_summary[
                (method_summary["pair"] == pair)
                & (method_summary["response"] == response)
            ].iloc[0]
            method_errors.append(
                abs(
                    float(differences.mean())
                    - saved_summary["mean_method_ii_minus_i_pct_point"]
                )
            )
            method_count_errors.extend(
                [
                    int((differences > 0).sum())
                    == int(saved_summary["positive_temperature_count"]),
                    int((differences < 0).sum())
                    == int(saved_summary["negative_temperature_count"]),
                ]
            )
    add(
        checks,
        "6 装料方式匹配差复算",
        max(method_errors) < 1e-10 and all(method_count_errors),
        f"max={max(method_errors):.3e}, counts={sum(method_count_errors)}/{len(method_count_errors)}",
    )

    manifest_ok = True
    for row in manifest.itertuples(index=False):
        path = OUT / row.artifact
        manifest_ok &= path.exists() and sha256(path) == row.sha256
    add(
        checks,
        "7 产物清单",
        manifest_ok and len(manifest) == 5,
        f"manifest_rows={len(manifest)}",
    )

    input_ok = (
        summary_json["input_sha256"] == sha256(INPUT)
        and summary_json["status"] == "candidate_evidence_not_formal_question2_model"
    )
    add(checks, "8 输入与候选状态", input_ok, summary_json["status"])

    payload = {
        "passed": all(item["passed"] for item in checks),
        "checks": checks,
        "what_this_proves": "候选产物忠实实现四条近似对照序列和两组完全匹配配方的描述计算",
        "what_this_does_not_prove": "不证明单一配方因素的独立因果作用，也不批准其进入正式第二问",
    }
    (OUT / "verification.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
