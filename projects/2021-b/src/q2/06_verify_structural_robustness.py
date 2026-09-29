#!/usr/bin/env python3
"""第二问S11独立验证：不导入稳健性主程序，逐表复算。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
TABLES = ROOT / "output/q2/tables"
OUT = ROOT / "output/q2"
TEMPERATURES = [250.0, 275.0, 300.0, 350.0]
RESPONSES = ["ethanol_conversion_pct", "c4_selectivity_pct"]


def calculate(data: pd.DataFrame, response: str) -> dict:
    grand = float(data[response].mean())
    combination_mean = data.groupby("catalyst_id")[response].mean()
    temperature_mean = data.groupby("temperature_c")[response].mean()
    fitted = (
        data["catalyst_id"].map(combination_mean)
        + data["temperature_c"].map(temperature_mean)
        - grand
    )
    residual = data[response] - fitted
    total = float(np.sum((data[response] - grand) ** 2))
    combination = float(
        data["temperature_c"].nunique() * np.sum((combination_mean - grand) ** 2)
    )
    temperature = float(
        data["catalyst_id"].nunique() * np.sum((temperature_mean - grand) ** 2)
    )
    nonadditive = float(np.sum(residual**2))
    ordered = combination_mean.sort_values(ascending=False)
    maximum = residual.abs().idxmax()
    return {
        "combination_share": combination / total,
        "temperature_share": temperature / total,
        "nonadditive_share": nonadditive / total,
        "closure_error": total - combination - temperature - nonadditive,
        "top5": ordered.head(5).index.tolist(),
        "bottom5": ordered.tail(5).index.tolist(),
        "increasing": bool(np.all(np.diff(temperature_mean.sort_index()) > 0)),
        "minimum_step": float(np.diff(temperature_mean.sort_index()).min()),
        "maximum_catalyst": data.loc[maximum, "catalyst_id"],
        "maximum_temperature": float(data.loc[maximum, "temperature_c"]),
        "maximum_residual": float(abs(residual.loc[maximum])),
        "residual": residual,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    data = pd.read_csv(INPUT)
    common = data[data["temperature_c"].isin(TEMPERATURES)].copy()
    common = common.sort_values(["catalyst_id", "temperature_c"]).reset_index(drop=True)
    leave_combination = pd.read_csv(
        TABLES / "robustness_leave_combination_out.csv"
    )
    leave_temperature = pd.read_csv(
        TABLES / "robustness_leave_temperature_out.csv"
    )
    flags = pd.read_csv(TABLES / "robustness_flag_diagnostic.csv")
    supplemental = pd.read_csv(TABLES / "robustness_supplemental_temperature.csv")
    summary = json.loads((OUT / "robustness_summary.json").read_text(encoding="utf-8"))
    checks = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    combination_errors = []
    temperature_errors = []
    closure_errors = []
    categorical_errors = 0
    for response in RESPONSES:
        baseline = calculate(common, response)
        for saved in leave_combination[
            leave_combination["response"] == response
        ].itertuples(index=False):
            subset = common[common["catalyst_id"] != saved.omitted_catalyst_id]
            result = calculate(subset, response)
            retained = set(subset["catalyst_id"])
            target_top = set(baseline["top5"]) & retained
            target_bottom = set(baseline["bottom5"]) & retained
            top_count = len(set(result["top5"]) & target_top)
            bottom_count = len(set(result["bottom5"]) & target_bottom)
            combination_errors.extend(
                [
                    abs(saved.combination_share - result["combination_share"]),
                    abs(saved.temperature_share - result["temperature_share"]),
                    abs(saved.nonadditive_share - result["nonadditive_share"]),
                    abs(saved.minimum_temperature_mean_step_pct_point - result["minimum_step"]),
                    abs(saved.maximum_absolute_residual_pct_point - result["maximum_residual"]),
                    abs(saved.top5_retention_fraction - top_count / len(target_top)),
                    abs(
                        saved.bottom5_retention_fraction
                        - bottom_count / len(target_bottom)
                    ),
                ]
            )
            closure_errors.append(abs(result["closure_error"]))
            categorical_errors += int(
                saved.temperature_mean_increasing != result["increasing"]
                or saved.maximum_residual_catalyst != result["maximum_catalyst"]
                or saved.maximum_residual_temperature_c
                != result["maximum_temperature"]
            )
        for saved in leave_temperature[
            leave_temperature["response"] == response
        ].itertuples(index=False):
            subset = common[
                common["temperature_c"] != saved.omitted_temperature_c
            ]
            result = calculate(subset, response)
            top_count = len(set(result["top5"]) & set(baseline["top5"]))
            bottom_count = len(set(result["bottom5"]) & set(baseline["bottom5"]))
            temperature_errors.extend(
                [
                    abs(saved.combination_share - result["combination_share"]),
                    abs(saved.temperature_share - result["temperature_share"]),
                    abs(saved.nonadditive_share - result["nonadditive_share"]),
                    abs(saved.minimum_temperature_mean_step_pct_point - result["minimum_step"]),
                    abs(saved.maximum_absolute_residual_pct_point - result["maximum_residual"]),
                    abs(saved.top5_retention_fraction - top_count / 5),
                    abs(saved.bottom5_retention_fraction - bottom_count / 5),
                ]
            )
            closure_errors.append(abs(result["closure_error"]))
            categorical_errors += int(
                saved.temperature_mean_increasing != result["increasing"]
                or saved.maximum_residual_catalyst != result["maximum_catalyst"]
                or saved.maximum_residual_temperature_c
                != result["maximum_temperature"]
            )

    add(
        "1 完整组合删除结构",
        len(leave_combination) == 42
        and leave_combination["cell_count"].eq(80).all()
        and leave_combination["combination_count"].eq(20).all()
        and leave_combination["temperature_count"].eq(4).all(),
        f"rows={len(leave_combination)}, expected=42, cells=80",
    )
    add(
        "2 完整温度删除结构",
        len(leave_temperature) == 8
        and leave_temperature["cell_count"].eq(63).all()
        and leave_temperature["combination_count"].eq(21).all()
        and leave_temperature["temperature_count"].eq(3).all(),
        f"rows={len(leave_temperature)}, expected=8, cells=63",
    )
    add(
        "3 完整组合删除数值复算",
        max(combination_errors) <= 1e-10 and categorical_errors == 0,
        f"max_abs_error={max(combination_errors):.3e}, categorical_errors={categorical_errors}",
    )
    add(
        "4 完整温度删除数值复算",
        max(temperature_errors) <= 1e-10 and categorical_errors == 0,
        f"max_abs_error={max(temperature_errors):.3e}, categorical_errors={categorical_errors}",
    )
    add(
        "5 所有删减平方和闭合",
        max(closure_errors) <= 1e-9,
        f"runs={len(closure_errors)}, max_abs_error={max(closure_errors):.3e}",
    )

    flag_errors = 0
    for response in RESPONSES:
        baseline = calculate(common, response)
        flag_mask = (
            common[f"{response}_global_iqr_flag"]
            | common[f"{response}_within_temperature_flag"]
        )
        saved = flags[flags["response"] == response].iloc[0]
        top10 = set(baseline["residual"].abs().nlargest(10).index)
        flagged = set(common.index[flag_mask])
        flag_errors += int(
            saved["common_domain_flagged_cell_count"] != flag_mask.sum()
            or saved["top10_absolute_residual_flagged_count"]
            != len(top10 & flagged)
            or bool(saved["largest_residual_cell_is_flagged"])
            != (baseline["residual"].abs().idxmax() in flagged)
        )
    add(
        "6 异常标记影响复算",
        len(flags) == 2 and flag_errors == 0,
        f"rows={len(flags)}, mismatches={flag_errors}",
    )

    matched = supplemental[supplemental["domain"] != "a3_case"]
    add(
        "7 高温匹配与个案边界",
        len(matched) == 6
        and matched["supports_common_domain_direction"].all()
        and (supplemental["domain"] == "a3_case").sum() == 2
        and summary["supplemental"]["matched_direction_supported_rows"] == 6,
        (
            f"matched_supported={matched['supports_common_domain_direction'].sum()}/6, "
            f"a3_rows={(supplemental['domain'] == 'a3_case').sum()}"
        ),
    )

    source_text = (ROOT / "src/q2/05_structural_robustness.py").read_text(
        encoding="utf-8"
    )
    forbidden = ["replacement_value", "imputed_cell", "leave_one_cell_out"]
    add(
        "8 禁止单单元替换",
        all(term not in source_text for term in forbidden)
        and set(summary["claim_boundaries"])
        >= {
            "删除单位为完整组合或完整温度，不删除或替换单个实验单元",
            "异常标记用于影响诊断，不作为错误或删值证据",
        },
        f"forbidden_hits={sum(term in source_text for term in forbidden)}",
    )

    manifest = pd.read_csv(OUT / "artifact_manifest.csv")
    expected = {
        "output/q2/tables/robustness_leave_combination_out.csv",
        "output/q2/tables/robustness_leave_temperature_out.csv",
        "output/q2/tables/robustness_flag_diagnostic.csv",
        "output/q2/tables/robustness_supplemental_temperature.csv",
        "output/q2/robustness_summary.json",
    }
    manifest_subset = manifest[manifest["relative_path"].isin(expected)]
    hashes = [
        (ROOT / row.relative_path).exists()
        and sha256(ROOT / row.relative_path) == row.sha256
        for row in manifest_subset.itertuples(index=False)
    ]
    add(
        "9 S11输出合同与哈希",
        set(manifest_subset["relative_path"]) == expected and all(hashes),
        f"files={len(manifest_subset)}/5, hashes={sum(hashes)}/5",
    )

    result = {
        "status": "q2_s11_independent_verification",
        "passed": all(item["passed"] for item in checks),
        "check_count": len(checks),
        "checks": checks,
        "note": "稳健性验证支持条件关联的稳定范围，不构成显著性或因果检验。",
    }
    path = OUT / "robustness_verification.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest = pd.read_csv(OUT / "artifact_manifest.csv")
    relative = "output/q2/robustness_verification.json"
    manifest = manifest[manifest["relative_path"] != relative]
    row = pd.DataFrame(
        [
            {
                "relative_path": relative,
                "sha256": sha256(path),
                "producer": "src/q2/06_verify_structural_robustness.py",
            }
        ]
    )
    pd.concat([manifest, row], ignore_index=True).to_csv(
        OUT / "artifact_manifest.csv", index=False
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
