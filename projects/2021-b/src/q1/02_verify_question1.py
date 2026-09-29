#!/usr/bin/env python3
"""独立核对第一问产物；不导入主分析脚本。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables"
OUT = ROOT / "output" / "q1"
TABLES = OUT / "tables"


def item(name: str, condition: bool, details: str) -> dict:
    return {"check": name, "passed": bool(condition), "details": details}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    data = pd.read_csv(INPUT / "modeling_dataset.csv", encoding="utf-8-sig")
    time = pd.read_csv(INPUT / "cleaned_attachment2.csv", encoding="utf-8-sig")
    adjacent = pd.read_csv(TABLES / "attachment1_adjacent_changes.csv", encoding="utf-8-sig")
    shapes = pd.read_csv(TABLES / "attachment1_shape_summary.csv", encoding="utf-8-sig")
    ratios = pd.read_csv(TABLES / "attachment2_relative_ratios.csv", encoding="utf-8-sig")
    selection = pd.read_csv(TABLES / "attachment2_selectivity_summary.csv", encoding="utf-8-sig")
    linear = pd.read_csv(TABLES / "attachment1_linear_summaries.csv", encoding="utf-8-sig")
    robustness = pd.read_csv(
        TABLES / "attachment1_leave_one_out_robustness.csv", encoding="utf-8-sig"
    )
    time_linear = pd.read_csv(
        TABLES / "attachment2_time_linear_summaries.csv", encoding="utf-8-sig"
    )
    expected_intervals = int(sum(len(group) - 1 for _, group in data.groupby("catalyst_id")))
    expected_robustness_rows = len(data) * 2
    direct_linear_ok = True
    direct_rank_ok = True
    direct_residual_ok = True
    direct_loo_ok = True
    for row in linear.itertuples():
        group = data[data.catalyst_id == row.catalyst_id].sort_values("temperature_c")
        x = group.temperature_c.to_numpy(float)
        y = group[row.response].to_numpy(float)
        slope, intercept = np.polyfit(x, y, 1)
        fitted = intercept + slope * x
        residuals = y - fitted
        rank = pd.Series(x).corr(pd.Series(y), method="spearman")
        direct_linear_ok &= np.isclose(row.slope_per_c_pct_point, slope, atol=1e-12)
        direct_linear_ok &= np.isclose(row.slope_per_25c_pct_point, slope * 25, atol=1e-12)
        direct_rank_ok &= np.isclose(row.spearman_rank_correlation, rank, atol=1e-12)
        direct_residual_ok &= np.isclose(
            row.mean_absolute_residual_pct_point, np.mean(np.abs(residuals)), atol=1e-12
        )
        direct_residual_ok &= np.isclose(
            row.max_absolute_residual_pct_point, np.max(np.abs(residuals)), atol=1e-12
        )
        subset = robustness[
            (robustness.catalyst_id == row.catalyst_id)
            & (robustness.response == row.response)
        ].sort_values("removed_temperature_c")
        direct_loo_ok &= len(subset) == len(x)
        for removed in subset.itertuples():
            keep = ~np.isclose(x, removed.removed_temperature_c)
            loo_slope = np.polyfit(x[keep], y[keep], 1)[0]
            direct_loo_ok &= np.isclose(removed.loo_slope_per_c, loo_slope, atol=1e-12)
    time_linear_ok = True
    for row in time_linear.itertuples():
        x = time.time_min.to_numpy(float)
        y = time[row.response].to_numpy(float)
        slope, intercept = np.polyfit(x, y, 1)
        fitted = intercept + slope * x
        time_linear_ok &= np.isclose(row.slope_per_min_pct_point, slope, atol=1e-12)
        time_linear_ok &= np.isclose(row.slope_per_10min_pct_point, slope * 10, atol=1e-12)
        time_linear_ok &= np.isclose(
            row.mean_absolute_residual_pct_point,
            np.mean(np.abs(y - fitted)), atol=1e-12
        )
    tests = [
        item("组合数", data.catalyst_id.nunique() == 21, "应为21种完整组合"),
        item("相邻变化行数", len(adjacent) == expected_intervals * 2,
             f"两项响应应有{expected_intervals * 2}行"),
        item("变化类型行数", len(shapes) == 42, "21种组合乘2项响应"),
        item("受限线性概括行数", len(linear) == 42, "21种组合乘2项响应"),
        item("线性斜率与单位换算", direct_linear_ok, "直接读取输入并复算斜率"),
        item("Spearman辅助数字", direct_rank_ok, "直接按排序复算"),
        item("残差诊断", direct_residual_ok, "直接复算平均和最大绝对残差"),
        item("逐次删点行数", len(robustness) == expected_robustness_rows,
             f"每条附件1记录对两个响应各删一次，应为{expected_robustness_rows}行"),
        item("逐次删点斜率", direct_loo_ok, "不调用主程序逐项重算"),
        item("转化率在各相邻条件均为较高温度对应较高值的组合数",
             int(((shapes.response == "ethanol_conversion_pct")
                  & (shapes.change_type == "各相邻温度条件中，较高温度对应较高值")).sum()) == 19,
             "应为19种"),
        item("选择性在各相邻条件均为较高温度对应较高值的组合数",
             int(((shapes.response == "c4_selectivity_pct")
                  & (shapes.change_type == "各相邻温度条件中，较高温度对应较高值")).sum()) == 15,
             "应为15种"),
        item("A5的250℃与275℃条件差异", np.isclose(adjacent.query(
            "catalyst_id == 'A5' and response == 'ethanol_conversion_pct' "
            "and temperature_from_c == 250").change_pct_point.iloc[0],
            -2.3631725529995, atol=1e-10), "核对250→275摄氏度"),
        item("A3的400℃与450℃条件差异", np.isclose(adjacent.query(
            "catalyst_id == 'A3' and response == 'c4_selectivity_pct' "
            "and temperature_from_c == 400").change_pct_point.iloc[0],
            -3.53, atol=1e-12), "核对400→450摄氏度"),
        item("乙醛相对比例", np.allclose(
            ratios.acetaldehyde_to_c4_ratio,
            time.acetaldehyde_selectivity_pct / time.c4_selectivity_pct), "逐时点直接相除"),
        item("脂肪醇相对比例", np.allclose(
            ratios.alcohol_to_c4_ratio,
            time.c4_12_alcohol_selectivity_pct / time.c4_selectivity_pct), "逐时点直接相除"),
        item("六类首末变化相抵", np.isclose(
            selection.change_pct_point.sum(), 0, atol=1e-12), "首末变化合计应为0"),
        item("附件2受限线性概括", len(time_linear) == 2 and time_linear_ok,
             "只复算转化率和C4收率"),
        item("附件2未拟合C4选择性",
             "c4_selectivity_pct" not in set(time_linear.response),
             "选择性保持波动描述"),
        item("图件齐全", all((OUT / "figures" / f"{index:02d}_{stem}.{suffix}").exists()
             for index, stem in [
                 (1, "each_combination_temperature_profiles"),
                 (2, "adjacent_temperature_change_map"),
                 (3, "attachment2_product_shares_and_ratios"),
                 (4, "literature_possible_reaction_pathways"),
                 (5, "attachment1_linear_summary_diagnostics"),
                 (6, "attachment2_limited_linear_summaries"),
             ] for suffix in ["png", "pdf"]), "6种图均应有PNG和PDF"),
    ]
    passed = sum(test["passed"] for test in tests)
    result = {"passed": passed, "total": len(tests), "all_passed": passed == len(tests),
              "checks": tests}
    verification_path = OUT / "verification.json"
    verification_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path = OUT / "artifact_manifest.csv"
    manifest = pd.read_csv(manifest_path, encoding="utf-8-sig")
    relative = str(verification_path.relative_to(ROOT))
    manifest = manifest[manifest.relative_path != relative]
    manifest = pd.concat([manifest, pd.DataFrame([{
        "relative_path": relative,
        "sha256": sha256(verification_path),
        "producer": "src/q1/02_verify_question1.py",
    }])], ignore_index=True)
    manifest.to_csv(manifest_path, index=False, encoding="utf-8-sig")
    print(f"第一问独立核对：{passed}/{len(tests)}")
    if passed != len(tests):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
