#!/usr/bin/env python3
"""第二问候选：在近似单因素序列和完全匹配配方中计算局部条件对应关系。

# 输入: output/data_audit/tables/cleaned_attachment1.csv
# 输出: output/q2/candidates/controlled_factor_sequences/*.csv 与 summary.json
# 职责: 补齐队友提出的受控配方因素候选；不把局部对应关系解释为独立因果效应。
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
RESPONSES = {
    "ethanol_conversion_pct": "乙醇转化率",
    "c4_selectivity_pct": "C4烯烃选择性",
}
SEQUENCES = {
    "co_loading": {
        "name_cn": "Co负载量",
        "ids": ["A4", "A1", "A2", "A6"],
        "level_field": "co_loading_wt_pct",
        "unit": "wt%",
        "fixed": "方式I；Co/SiO2 200 mg；HAP 200 mg；附件乙醇条件1.68 ml/min",
    },
    "ethanol_condition": {
        "name_cn": "附件所列乙醇条件",
        "ids": ["A7", "A8", "A12", "A9"],
        "level_field": "ethanol_condition_ml_min",
        "unit": "ml/min",
        "fixed": "方式I；1 wt% Co；Co/SiO2 50 mg；HAP 50 mg",
    },
    "active_mass": {
        "name_cn": "活性催化剂总质量",
        "ids": ["B3", "B4", "B1", "B6", "B2"],
        "level_field": "active_catalyst_mass_mg",
        "unit": "mg",
        "fixed": "方式II；1 wt% Co；Co/SiO2:HAP=1:1；附件乙醇条件1.68 ml/min",
    },
    "hap_fraction": {
        "name_cn": "HAP质量分数",
        "ids": ["A14", "A12", "A13"],
        "level_field": "hap_mass_fraction",
        "unit": "比例",
        "fixed": "方式I；1 wt% Co；活性催化剂总质量100 mg；附件乙醇条件1.68 ml/min",
    },
}
METHOD_PAIRS = [("A12", "B1"), ("A9", "B5")]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare() -> pd.DataFrame:
    data = pd.read_csv(INPUT)
    data = data[data["temperature_c"].isin(TEMPERATURES)].copy()
    coverage = data.groupby("catalyst_id")["temperature_c"].nunique()
    if len(data) != 84 or len(coverage) != 21 or not coverage.eq(4).all():
        raise ValueError("四个共同温度的21组合平衡接口不完整")
    return data.sort_values(["catalyst_id", "temperature_c"]).reset_index(drop=True)


def verify_sequence_contract(data: pd.DataFrame, key: str, spec: dict) -> dict:
    recipes = (
        data[data["catalyst_id"].isin(spec["ids"])]
        .drop_duplicates("catalyst_id")
        .set_index("catalyst_id")
        .loc[spec["ids"]]
    )
    varying = spec["level_field"]
    checked = [
        "loading_method",
        "cosio2_mass_mg",
        "co_loading_wt_pct",
        "hap_mass_mg",
        "active_catalyst_mass_mg",
        "ethanol_condition_ml_min",
    ]
    constant_fields = [field for field in checked if field != varying]
    if key == "active_mass":
        constant_fields = [
            "loading_method",
            "co_loading_wt_pct",
            "cosio2_to_hap_ratio",
            "ethanol_condition_ml_min",
        ]
    if key == "hap_fraction":
        constant_fields = [
            "loading_method",
            "co_loading_wt_pct",
            "active_catalyst_mass_mg",
            "ethanol_condition_ml_min",
        ]
    violations = {
        field: int(recipes[field].nunique(dropna=False))
        for field in constant_fields
        if recipes[field].nunique(dropna=False) != 1
    }
    levels = recipes[varying].astype(float)
    return {
        "sequence": key,
        "ids": spec["ids"],
        "level_field": varying,
        "levels": levels.to_dict(),
        "constant_fields": constant_fields,
        "violations": violations,
        "passed": not violations and levels.nunique() == len(levels),
    }


def sequence_rows(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, list[dict]]:
    levels_rows: list[dict] = []
    summary_rows: list[dict] = []
    contracts: list[dict] = []
    for key, spec in SEQUENCES.items():
        contract = verify_sequence_contract(data, key, spec)
        contracts.append(contract)
        if not contract["passed"]:
            raise ValueError(f"{key}对照序列不满足合同: {contract}")
        subset = data[data["catalyst_id"].isin(spec["ids"])].copy()
        recipe = subset.drop_duplicates("catalyst_id").set_index("catalyst_id")
        for response, response_cn in RESPONSES.items():
            matrix = subset.pivot(
                index="catalyst_id", columns="temperature_c", values=response
            ).loc[spec["ids"], TEMPERATURES]
            means = matrix.mean(axis=1)
            levels = recipe.loc[spec["ids"], spec["level_field"]].astype(float)
            order = levels.sort_values().index
            adjusted = means - float(means.mean())
            for catalyst_id in order:
                levels_rows.append(
                    {
                        "sequence": key,
                        "factor_cn": spec["name_cn"],
                        "fixed_conditions": spec["fixed"],
                        "response": response,
                        "response_cn": response_cn,
                        "catalyst_id": catalyst_id,
                        "factor_level": float(levels.loc[catalyst_id]),
                        "factor_unit": spec["unit"],
                        "four_temperature_mean_pct": float(means.loc[catalyst_id]),
                        "subset_adjusted_effect_pct_point": float(
                            adjusted.loc[catalyst_id]
                        ),
                    }
                )
            endpoint = float(means.loc[order[-1]] - means.loc[order[0]])
            deletion_contrasts = []
            for omitted in TEMPERATURES:
                kept = [temperature for temperature in TEMPERATURES if temperature != omitted]
                reduced = matrix[kept].mean(axis=1)
                deletion_contrasts.append(
                    float(reduced.loc[order[-1]] - reduced.loc[order[0]])
                )
            rho = float(pd.Series(levels).corr(pd.Series(means), method="spearman"))
            summary_rows.append(
                {
                    "sequence": key,
                    "factor_cn": spec["name_cn"],
                    "response": response,
                    "response_cn": response_cn,
                    "level_count": len(order),
                    "lowest_level": float(levels.loc[order[0]]),
                    "highest_level": float(levels.loc[order[-1]]),
                    "endpoint_contrast_pct_point": endpoint,
                    "spearman_level_response": rho,
                    "leave_one_temperature_min_contrast": min(deletion_contrasts),
                    "leave_one_temperature_max_contrast": max(deletion_contrasts),
                    "endpoint_direction_stable": bool(
                        all(value > 0 for value in deletion_contrasts)
                        or all(value < 0 for value in deletion_contrasts)
                    ),
                    "allowed_claim": "本近似对照序列内的局部条件对应关系，不是独立因果效应",
                }
            )
    return pd.DataFrame(levels_rows), pd.DataFrame(summary_rows), contracts


def method_rows(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    detail_rows: list[dict] = []
    summary_rows: list[dict] = []
    recipe_fields = [
        "cosio2_mass_mg",
        "co_loading_wt_pct",
        "hap_mass_mg",
        "quartz_mass_mg",
        "ethanol_condition_ml_min",
    ]
    recipes = data.drop_duplicates("catalyst_id").set_index("catalyst_id")
    for left, right in METHOD_PAIRS:
        mismatches = [
            field
            for field in recipe_fields
            if not np.isclose(
                float(recipes.loc[left, field]),
                float(recipes.loc[right, field]),
                equal_nan=True,
            )
        ]
        if mismatches or recipes.loc[left, "loading_method"] == recipes.loc[right, "loading_method"]:
            raise ValueError(f"{left}-{right}并非只改变装料方式: {mismatches}")
        for response, response_cn in RESPONSES.items():
            left_values = (
                data[data["catalyst_id"] == left]
                .set_index("temperature_c")
                .loc[TEMPERATURES, response]
            )
            right_values = (
                data[data["catalyst_id"] == right]
                .set_index("temperature_c")
                .loc[TEMPERATURES, response]
            )
            differences = right_values - left_values
            for temperature, difference in differences.items():
                detail_rows.append(
                    {
                        "pair": f"{left}-{right}",
                        "method_i_catalyst": left,
                        "method_ii_catalyst": right,
                        "response": response,
                        "response_cn": response_cn,
                        "temperature_c": float(temperature),
                        "method_ii_minus_i_pct_point": float(difference),
                    }
                )
            summary_rows.append(
                {
                    "pair": f"{left}-{right}",
                    "response": response,
                    "response_cn": response_cn,
                    "mean_method_ii_minus_i_pct_point": float(differences.mean()),
                    "positive_temperature_count": int((differences > 0).sum()),
                    "negative_temperature_count": int((differences < 0).sum()),
                    "allowed_claim": "该完全匹配配方对内的装料方式差异，不推广到全部组合",
                }
            )
    return pd.DataFrame(detail_rows), pd.DataFrame(summary_rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = prepare()
    levels, sequences, contracts = sequence_rows(data)
    method_detail, method_summary = method_rows(data)
    artifacts = {
        "sequence_level_effects.csv": levels,
        "sequence_summaries.csv": sequences,
        "loading_method_pair_details.csv": method_detail,
        "loading_method_pair_summaries.csv": method_summary,
    }
    for name, frame in artifacts.items():
        frame.to_csv(OUT / name, index=False)
    payload = {
        "status": "candidate_evidence_not_formal_question2_model",
        "input": str(INPUT.relative_to(ROOT)),
        "input_sha256": sha256(INPUT),
        "common_temperatures_c": TEMPERATURES,
        "sequence_contracts": contracts,
        "boundaries": [
            "每个因素水平主要由一个完整组合代表，不能识别独立因果效应",
            "只使用21种组合共有的四个温度，避免覆盖不平衡改变比较",
            "Spearman系数只概括水平顺序，不作小样本显著性裁决",
            "装料方式只由两组完全匹配配方支持，不能推广到全部组合",
            "本候选不得在负责人决定前替换已冻结的第二问",
        ],
    }
    (OUT / "summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    manifest_rows = []
    for path in sorted(OUT.iterdir()):
        if path.name == "artifact_manifest.csv" or not path.is_file():
            continue
        manifest_rows.append(
            {
                "artifact": path.name,
                "sha256": sha256(path),
                "producer": "src/q2/candidates/03_controlled_factor_sequences.py",
                "consumer": "candidate verification and human method review",
            }
        )
    pd.DataFrame(manifest_rows).to_csv(OUT / "artifact_manifest.csv", index=False)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
