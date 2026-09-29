#!/usr/bin/env python3
"""B题官方数据的完整审计、结构化预处理与可视化。

# 输入: data/附件1.xlsx, data/附件2.xlsx
# 输出: output/data_audit/audit_summary.json, run_manifest.json, artifact_manifest.csv
# 输出: output/data_audit/tables/*.csv, output/data_audit/figures/*.{png,pdf}
# 职责: 保留原始观测，解析催化剂因素，重算收率，审计数据质量与实验设计并冻结图表。
"""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
OUT = ROOT / "output" / "data_audit"
TABLES = OUT / "tables"
FIGURES = OUT / "figures"
ATT1 = DATA / "附件1.xlsx"
ATT2 = DATA / "附件2.xlsx"

COLORS = {
    "blue": "#0072B2", "sky": "#56B4E9", "green": "#009E73",
    "orange": "#E69F00", "vermillion": "#D55E00",
    "purple": "#CC79A7", "gray": "#73777D",
}
PRODUCTS = [
    "ethylene_selectivity_pct", "c4_selectivity_pct",
    "acetaldehyde_selectivity_pct", "c4_12_alcohol_selectivity_pct",
    "methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct", "other_selectivity_pct",
]
RESPONSES = ["ethanol_conversion_pct", "c4_selectivity_pct", "c4_yield_pct"]


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def setup_plotting() -> None:
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["WenQuanYi Micro Hei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": False,
        "savefig.dpi": 300,
        "pdf.fonttype": 42,
    })
    sns.set_context("paper", font_scale=1.05)


def save_fig(fig: plt.Figure, stem: str) -> list[Path]:
    paths = [FIGURES / f"{stem}.png", FIGURES / f"{stem}.pdf"]
    for path in paths:
        fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return paths


def parse_recipe(catalyst_id: str, description: str) -> dict[str, object]:
    """解析官方配方字符串；无法解析时立即失败，不静默猜测。"""
    text = re.sub(r"\s+", "", description)
    co = re.search(r"(\d+(?:\.\d+)?)mg(\d+(?:\.\d+)?)wt%Co/SiO2", text)
    flow = re.search(r"乙醇浓度(\d+(?:\.\d+)?)ml/min", text)
    if co is None or flow is None:
        raise ValueError(f"{catalyst_id} 配方无法解析: {description}")
    hap = re.search(r"(\d+(?:\.\d+)?)mgHAP", text)
    quartz = re.search(r"(\d+(?:\.\d+)?)mg石英砂", text)
    co_mass, loading = float(co.group(1)), float(co.group(2))
    hap_mass = float(hap.group(1)) if hap else 0.0
    quartz_mass = float(quartz.group(1)) if quartz else 0.0
    active_mass = co_mass + hap_mass
    return {
        "catalyst_id": catalyst_id,
        "catalyst_description": description,
        "loading_method": "I" if catalyst_id.startswith("A") else "II",
        "cosio2_mass_mg": co_mass,
        "co_loading_wt_pct": loading,
        "hap_mass_mg": hap_mass,
        "quartz_mass_mg": quartz_mass,
        "has_hap": hap_mass > 0,
        "active_catalyst_mass_mg": active_mass,
        "total_packed_mass_mg": active_mass + quartz_mass,
        "cosio2_to_hap_ratio": np.nan if hap_mass == 0 else co_mass / hap_mass,
        "hap_mass_fraction": np.nan if active_mass == 0 else hap_mass / active_mass,
        "ethanol_condition_ml_min": float(flow.group(1)),
    }


def read_attachment1() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    workbook = load_workbook(ATT1, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if len(rows[0]) != 11 or rows[0][10] is not None:
        raise ValueError("附件1预期存在10个有效字段和1个完全空的尾列")
    records, current_id, current_desc = [], None, None
    for excel_row, row in enumerate(rows[1:], 2):
        current_id = str(row[0]).strip() if row[0] is not None else current_id
        current_desc = str(row[1]).strip() if row[1] is not None else current_desc
        if row[2] is None:
            continue
        if current_id is None or current_desc is None:
            raise ValueError(f"附件1第{excel_row}行缺少组合信息")
        records.append({
            "source_excel_row": excel_row,
            "catalyst_id": current_id,
            "catalyst_description": current_desc,
            "temperature_c": float(row[2]),
            "ethanol_conversion_pct": float(row[3]),
            "ethylene_selectivity_pct": float(row[4]),
            "c4_selectivity_pct": float(row[5]),
            "acetaldehyde_selectivity_pct": float(row[6]),
            "c4_12_alcohol_selectivity_pct": float(row[7]),
            "methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct": float(row[8]),
            "other_selectivity_pct": float(row[9]),
        })
    base = pd.DataFrame(records)
    recipes = pd.DataFrame([
        parse_recipe(cid, desc)
        for cid, desc in base[["catalyst_id", "catalyst_description"]]
        .drop_duplicates().itertuples(index=False, name=None)
    ])
    clean = base.merge(
        recipes.drop(columns="catalyst_description"),
        on="catalyst_id", how="left", validate="many_to_one",
    )
    clean["c4_yield_pct"] = clean.ethanol_conversion_pct * clean.c4_selectivity_pct / 100
    clean["selectivity_sum_pct"] = clean[PRODUCTS].sum(axis=1)
    clean["selectivity_closure_error_pct_point"] = clean.selectivity_sum_pct - 100
    clean["selectivity_closure_abs_error_pct_point"] = clean.selectivity_closure_error_pct_point.abs()
    clean["duplicate_catalyst_temperature"] = clean.duplicated(
        ["catalyst_id", "temperature_c"], keep=False
    )
    for column in RESPONSES:
        q1, q3 = clean[column].quantile([0.25, 0.75])
        iqr = q3 - q1
        clean[f"{column}_global_iqr_flag"] = (
            (clean[column] < q1 - 1.5 * iqr) | (clean[column] > q3 + 1.5 * iqr)
        )
        grouped = clean.groupby("temperature_c")[column]
        median = grouped.transform("median")
        mad = grouped.transform(lambda x: np.median(np.abs(x - np.median(x))))
        robust_z = np.where(mad > 0, 0.6745 * (clean[column] - median) / mad, 0)
        clean[f"{column}_within_temperature_robust_z"] = robust_z
        clean[f"{column}_within_temperature_flag"] = np.abs(robust_z) > 3.5
    meta = {
        "sheet_name": sheet.title, "max_row": sheet.max_row,
        "max_column": sheet.max_column, "blank_trailing_columns": 1,
        "effective_records": len(clean), "combination_count": clean.catalyst_id.nunique(),
    }
    return clean, recipes, meta


def read_attachment2() -> tuple[pd.DataFrame, dict[str, object]]:
    workbook = load_workbook(ATT2, read_only=True, data_only=True)
    sheet = workbook.active
    rows = list(sheet.iter_rows(values_only=True))
    if rows[0][0] != "350度时给定的某种催化剂组合的测试数据":
        raise ValueError("附件2标题发生变化")
    records = []
    for excel_row, row in enumerate(rows[3:], 4):
        if row[0] is None:
            continue
        records.append({
            "source_excel_row": excel_row, "time_min": float(row[0]),
            "temperature_c": 350.0, "catalyst_identity": "题面未给出",
            "ethanol_conversion_pct": float(row[1]),
            "ethylene_selectivity_pct": float(row[2]),
            "c4_selectivity_pct": float(row[3]),
            "acetaldehyde_selectivity_pct": float(row[4]),
            "c4_12_alcohol_selectivity_pct": float(row[5]),
            "methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct": float(row[6]),
            "other_selectivity_pct": float(row[7]),
        })
    clean = pd.DataFrame(records)
    clean["c4_yield_pct"] = clean.ethanol_conversion_pct * clean.c4_selectivity_pct / 100
    clean["selectivity_sum_pct"] = clean[PRODUCTS].sum(axis=1)
    clean["selectivity_closure_error_pct_point"] = clean.selectivity_sum_pct - 100
    clean["selectivity_closure_abs_error_pct_point"] = clean.selectivity_closure_error_pct_point.abs()
    clean["time_gap_min"] = clean.time_min.diff()
    for name in ["ethanol_conversion_pct", "c4_selectivity_pct", "c4_yield_pct"]:
        clean[f"{name}_change_from_first_pct_point"] = clean[name] - clean[name].iloc[0]
    meta = {
        "sheet_name": sheet.title, "max_row": sheet.max_row,
        "max_column": sheet.max_column, "effective_records": len(clean),
        "time_min": clean.time_min.min(), "time_max": clean.time_min.max(),
        "is_strictly_increasing_time": bool(clean.time_min.is_monotonic_increasing),
    }
    return clean, meta


def audit_tables(a: pd.DataFrame, recipes: pd.DataFrame, b: pd.DataFrame) -> dict[str, pd.DataFrame]:
    coverage = a.groupby(["catalyst_id", "loading_method"], as_index=False).agg(
        observation_count=("temperature_c", "size"),
        temperature_min_c=("temperature_c", "min"),
        temperature_max_c=("temperature_c", "max"),
        temperature_unique_count=("temperature_c", "nunique"),
        conversion_min_pct=("ethanol_conversion_pct", "min"),
        conversion_max_pct=("ethanol_conversion_pct", "max"),
        c4_selectivity_min_pct=("c4_selectivity_pct", "min"),
        c4_selectivity_max_pct=("c4_selectivity_pct", "max"),
        yield_min_pct=("c4_yield_pct", "min"),
        yield_max_pct=("c4_yield_pct", "max"),
    )
    temperature = a.groupby("temperature_c", as_index=False).agg(
        observation_count=("catalyst_id", "size"),
        conversion_mean_pct=("ethanol_conversion_pct", "mean"),
        conversion_median_pct=("ethanol_conversion_pct", "median"),
        conversion_std_pct=("ethanol_conversion_pct", "std"),
        c4_selectivity_mean_pct=("c4_selectivity_pct", "mean"),
        c4_selectivity_median_pct=("c4_selectivity_pct", "median"),
        c4_selectivity_std_pct=("c4_selectivity_pct", "std"),
        yield_mean_pct=("c4_yield_pct", "mean"),
        yield_median_pct=("c4_yield_pct", "median"),
        yield_std_pct=("c4_yield_pct", "std"),
    )
    response_summary = a[RESPONSES + ["selectivity_sum_pct"]].describe(
        percentiles=[.05, .25, .5, .75, .95]
    ).T.reset_index().rename(columns={"index": "variable"})
    factor_rows = []
    factor_columns = [
        "loading_method", "cosio2_mass_mg", "co_loading_wt_pct", "hap_mass_mg",
        "quartz_mass_mg", "has_hap", "active_catalyst_mass_mg", "ethanol_condition_ml_min",
    ]
    for column in factor_columns:
        for level, count in recipes[column].value_counts(dropna=False).sort_index().items():
            factor_rows.append({"factor": column, "level": str(level), "combination_count": count})
    keys = ["cosio2_mass_mg", "co_loading_wt_pct", "hap_mass_mg", "quartz_mass_mg",
            "ethanol_condition_ml_min"]
    matched = recipes.groupby(keys, dropna=False).filter(
        lambda group: group.loading_method.nunique() > 1
    ).sort_values(keys + ["loading_method"])
    corr_cols = [
        "temperature_c", "cosio2_mass_mg", "co_loading_wt_pct", "hap_mass_mg",
        "active_catalyst_mass_mg", "ethanol_condition_ml_min",
        "ethanol_conversion_pct", "c4_selectivity_pct", "c4_yield_pct",
    ]
    spearman = a[corr_cols].corr(method="spearman").reset_index().rename(columns={"index": "variable"})

    recipe_numeric = [
        "cosio2_mass_mg", "co_loading_wt_pct", "hap_mass_mg", "quartz_mass_mg",
        "active_catalyst_mass_mg", "total_packed_mass_mg", "ethanol_condition_ml_min",
    ]
    recipe_factor_correlation = (
        recipes[recipe_numeric].corr(method="spearman").reset_index()
        .rename(columns={"index": "variable"})
    )

    trend_rows = []
    for catalyst_id, group in a.groupby("catalyst_id"):
        ordered = group.sort_values("temperature_c")
        for response in RESPONSES:
            values = ordered[response]
            diffs = values.diff().dropna()
            trend_rows.append({
                "catalyst_id": catalyst_id,
                "loading_method": ordered.loading_method.iloc[0],
                "response": response,
                "observation_count": len(ordered),
                "temperature_min_c": ordered.temperature_c.min(),
                "temperature_max_c": ordered.temperature_c.max(),
                "spearman_temperature_response": ordered.temperature_c.corr(values, method="spearman"),
                "strictly_increasing": bool((diffs > 0).all()),
                "nondecreasing": bool((diffs >= 0).all()),
                "strictly_decreasing": bool((diffs < 0).all()),
                "sign_change_count": int(
                    (np.sign(diffs).replace(0, np.nan).dropna().diff().fillna(0) != 0).sum()
                ),
                "first_value": values.iloc[0],
                "last_value": values.iloc[-1],
                "absolute_change": values.iloc[-1] - values.iloc[0],
            })
    trend_summary = pd.DataFrame(trend_rows)

    matched_response_rows = []
    matched_recipes = recipes.groupby(keys, dropna=False).filter(
        lambda group: group.loading_method.nunique() > 1
    )
    for _, recipe_group in matched_recipes.groupby(keys, dropna=False):
        ids_in_group = recipe_group.catalyst_id.tolist()
        if len(ids_in_group) != 2:
            continue
        left = a[a.catalyst_id == ids_in_group[0]]
        right = a[a.catalyst_id == ids_in_group[1]]
        common = left.merge(right, on="temperature_c", suffixes=("_left", "_right"))
        for row in common.itertuples(index=False):
            matched_response_rows.append({
                "catalyst_left": row.catalyst_id_left,
                "method_left": row.loading_method_left,
                "catalyst_right": row.catalyst_id_right,
                "method_right": row.loading_method_right,
                "temperature_c": row.temperature_c,
                "conversion_difference_left_minus_right_pct_point":
                    row.ethanol_conversion_pct_left - row.ethanol_conversion_pct_right,
                "c4_selectivity_difference_left_minus_right_pct_point":
                    row.c4_selectivity_pct_left - row.c4_selectivity_pct_right,
                "yield_difference_left_minus_right_pct_point":
                    row.c4_yield_pct_left - row.c4_yield_pct_right,
            })
    matched_responses = pd.DataFrame(matched_response_rows)

    flag_columns = [
        f"{response}_{suffix}"
        for response in RESPONSES
        for suffix in ["global_iqr_flag", "within_temperature_flag"]
    ]
    flagged = a.loc[a[flag_columns].any(axis=1), [
        "source_excel_row", "catalyst_id", "temperature_c",
        "ethanol_conversion_pct", "c4_selectivity_pct", "c4_yield_pct",
    ] + flag_columns].copy()

    # 身份相似度只是线索诊断：使用350 °C响应向量，绝不把最近邻自动当作身份结论。
    identity_features = ["ethanol_conversion_pct"] + PRODUCTS
    candidates = a[a.temperature_c == 350].copy()
    scale = candidates[identity_features].std(ddof=0).replace(0, 1)
    identity_rows = []
    for time_row in b.itertuples(index=False):
        time_vector = pd.Series({feature: getattr(time_row, feature) for feature in identity_features})
        distances = np.sqrt((((candidates[identity_features] - time_vector) / scale) ** 2).sum(axis=1))
        for rank, index in enumerate(distances.nsmallest(5).index, 1):
            identity_rows.append({
                "time_min": time_row.time_min,
                "rank": rank,
                "candidate_catalyst_id": candidates.loc[index, "catalyst_id"],
                "standardized_euclidean_distance": distances.loc[index],
            })
    identity_similarity = pd.DataFrame(identity_rows)

    dictionary_rows = [
        ("source_excel_row", "原工作簿行号", "整数", "来源定位"),
        ("catalyst_id", "催化剂组合编号", "类别", "题面A1—A14、B1—B7"),
        ("loading_method", "装料方式", "类别", "A组为I，B组为II"),
        ("temperature_c", "反应温度；7水平有序离散标签", "°C", "原始字段；不连续插值"),
        ("ethanol_conversion_pct", "乙醇转化率", "%", "原始字段"),
        ("c4_selectivity_pct", "C4烯烃选择性", "%", "原始字段"),
        ("c4_yield_pct", "C4烯烃收率", "%", "转化率×选择性÷100"),
        ("cosio2_mass_mg", "Co/SiO2装料质量", "mg", "配方文本解析"),
        ("co_loading_wt_pct", "Co负载量", "wt%", "配方文本解析"),
        ("hap_mass_mg", "HAP装料质量", "mg", "配方文本解析；A11为0"),
        ("quartz_mass_mg", "石英砂质量", "mg", "配方文本解析；仅A11非零"),
        ("ethanol_condition_ml_min", "附件所列乙醇条件", "ml/min",
         "保留附件单位，不自行判定为浓度或流量"),
        ("selectivity_sum_pct", "六类产物选择性合计", "%", "完整性审计派生"),
        ("time_min", "单次实验反应时间", "min", "附件2原始字段"),
    ]
    data_dictionary = pd.DataFrame(
        dictionary_rows, columns=["field", "meaning", "unit_or_type", "source_or_rule"]
    )
    top_columns = [
        "catalyst_id", "loading_method", "temperature_c", "ethanol_conversion_pct",
        "c4_selectivity_pct", "c4_yield_pct", "co_loading_wt_pct",
        "cosio2_mass_mg", "hap_mass_mg", "ethanol_condition_ml_min",
    ]
    closure = pd.concat([
        a.assign(dataset="附件1", record_id=a.catalyst_id + "@" + a.temperature_c.astype(str)),
        b.assign(dataset="附件2", record_id="t=" + b.time_min.astype(str)),
    ], ignore_index=True, sort=False)[
        ["dataset", "record_id", "selectivity_sum_pct",
         "selectivity_closure_error_pct_point", "selectivity_closure_abs_error_pct_point"]
    ]
    missing_rows = []
    for dataset, frame in [("附件1清洁表", a), ("催化剂组合表", recipes), ("附件2清洁表", b)]:
        for column in frame:
            missing_rows.append({
                "dataset": dataset, "column": column, "row_count": len(frame),
                "missing_count": frame[column].isna().sum(),
                "missing_rate": frame[column].isna().mean(),
            })

    # 正式模型接口只保留用户批准的完整组合、离散温度与响应，不暴露配方拆分空间。
    modeling_dataset = a[[
        "source_excel_row", "catalyst_id", "temperature_c",
        "ethanol_conversion_pct", "c4_selectivity_pct", "c4_yield_pct",
    ]].copy()
    modeling_dataset["temperature_level"] = modeling_dataset.temperature_c.astype(int).astype(str)
    modeling_dataset["temperature_order"] = modeling_dataset.temperature_c.map(
        {value: rank for rank, value in enumerate(sorted(a.temperature_c.unique()), 1)}
    )

    coverage_matrix = (
        a.assign(observed=1)
        .pivot(index="catalyst_id", columns="temperature_c", values="observed")
        .reindex(
            index=sorted(a.catalyst_id.unique(), key=lambda x: (x[0], int(x[1:]))),
            columns=sorted(a.temperature_c.unique()),
        )
        .fillna(0).astype(int).reset_index()
    )
    temperature_common_sets = a.groupby("temperature_c").agg(
        observed_combination_count=("catalyst_id", "nunique"),
        observed_combinations=("catalyst_id", lambda values: "|".join(
            sorted(values, key=lambda x: (x[0], int(x[1:])))
        )),
    ).reset_index()
    temperature_common_sets["covers_all_21_combinations"] = (
        temperature_common_sets.observed_combination_count == 21
    )

    adjacent_rows = []
    for catalyst_id, group in a.groupby("catalyst_id"):
        ordered = group.sort_values("temperature_c")
        for left, right in zip(ordered.iloc[:-1].itertuples(), ordered.iloc[1:].itertuples()):
            adjacent_rows.append({
                "catalyst_id": catalyst_id,
                "temperature_from_c": left.temperature_c,
                "temperature_to_c": right.temperature_c,
                "temperature_gap_c": right.temperature_c - left.temperature_c,
                "conversion_change_pct_point":
                    right.ethanol_conversion_pct - left.ethanol_conversion_pct,
                "c4_selectivity_change_pct_point":
                    right.c4_selectivity_pct - left.c4_selectivity_pct,
                "c4_yield_change_pct_point": right.c4_yield_pct - left.c4_yield_pct,
            })
    adjacent_differences = pd.DataFrame(adjacent_rows)

    rank_rows = []
    for temperature_c, group in a.groupby("temperature_c"):
        for response in RESPONSES:
            ranks = group[response].rank(method="min", ascending=False)
            for index, rank in ranks.items():
                rank_rows.append({
                    "temperature_c": temperature_c,
                    "catalyst_id": group.loc[index, "catalyst_id"],
                    "response": response,
                    "response_value_pct": group.loc[index, response],
                    "rank_descending": int(rank),
                    "comparison_count": len(group),
                })
    response_ranks = pd.DataFrame(rank_rows)

    grid = pd.MultiIndex.from_product(
        [sorted(a.catalyst_id.unique(), key=lambda x: (x[0], int(x[1:]))),
         sorted(a.temperature_c.unique())],
        names=["catalyst_id", "temperature_c"],
    ).to_frame(index=False)
    observed_keys = a[["catalyst_id", "temperature_c"]].assign(observed=True)
    unobserved = grid.merge(observed_keys, how="left", on=["catalyst_id", "temperature_c"])
    unobserved = unobserved[unobserved.observed.isna()].drop(columns="observed")
    ranges = a.groupby("catalyst_id").temperature_c.agg(["min", "max"]).reset_index()
    unobserved = unobserved.merge(ranges, on="catalyst_id")
    unobserved["within_combination_observed_temperature_range"] = (
        (unobserved.temperature_c >= unobserved["min"])
        & (unobserved.temperature_c <= unobserved["max"])
    )
    unobserved["safety_status"] = "题面未给出；实验设计前必须审查"
    unobserved = unobserved.rename(columns={
        "min": "combination_observed_min_c", "max": "combination_observed_max_c"
    })

    driver_rows = []
    for temperature_c, group in a.groupby("temperature_c"):
        driver_rows.append({
            "temperature_c": temperature_c,
            "combination_count": len(group),
            "spearman_yield_conversion": group.c4_yield_pct.corr(
                group.ethanol_conversion_pct, method="spearman"
            ) if len(group) >= 3 else np.nan,
            "spearman_yield_c4_selectivity": group.c4_yield_pct.corr(
                group.c4_selectivity_pct, method="spearman"
            ) if len(group) >= 3 else np.nan,
            "interpretation": "同温度组合排名关联，仅描述收率排序更贴近哪个乘积组成项",
        })
    yield_driver = pd.DataFrame(driver_rows)

    domain_specs = {
        "temperature_c": ("属于批准的7个离散标签", lambda s: s.isin([250, 275, 300, 325, 350, 400, 450])),
        "time_min": ("非负", lambda s: s >= 0),
        "ethanol_conversion_pct": ("0至100", lambda s: s.between(0, 100)),
        "ethylene_selectivity_pct": ("0至100", lambda s: s.between(0, 100)),
        "c4_selectivity_pct": ("0至100", lambda s: s.between(0, 100)),
        "acetaldehyde_selectivity_pct": ("0至100", lambda s: s.between(0, 100)),
        "c4_12_alcohol_selectivity_pct": ("0至100", lambda s: s.between(0, 100)),
        "methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct": (
            "0至100", lambda s: s.between(0, 100)
        ),
        "other_selectivity_pct": ("0至100", lambda s: s.between(0, 100)),
        "c4_yield_pct": ("0至100", lambda s: s.between(0, 100)),
        "cosio2_mass_mg": ("非负", lambda s: s >= 0),
        "co_loading_wt_pct": ("非负", lambda s: s >= 0),
        "hap_mass_mg": ("非负", lambda s: s >= 0),
        "quartz_mass_mg": ("非负", lambda s: s >= 0),
        "ethanol_condition_ml_min": ("正数", lambda s: s > 0),
    }
    domain_rows = []
    for dataset, frame in [("附件1清洁表", a), ("催化剂组合表", recipes), ("附件2清洁表", b)]:
        for field, (rule, validator) in domain_specs.items():
            if field not in frame:
                continue
            values = frame[field].dropna()
            valid = validator(values)
            domain_rows.append({
                "dataset": dataset, "field": field, "rule": rule,
                "nonmissing_count": len(values), "missing_count": int(frame[field].isna().sum()),
                "minimum": values.min() if len(values) else np.nan,
                "maximum": values.max() if len(values) else np.nan,
                "violation_count": int((~valid).sum()),
            })
    domain_audit = pd.DataFrame(domain_rows)

    recipe_verification = recipes[[
        "catalyst_id", "catalyst_description", "loading_method",
        "cosio2_mass_mg", "co_loading_wt_pct", "hap_mass_mg",
        "quartz_mass_mg", "ethanol_condition_ml_min",
    ]].copy()
    recipe_verification["parser_succeeded"] = True
    recipe_verification["full_row_review_scope"] = "21种组合全部纳入人工逐行核验"

    raw1 = list(load_workbook(ATT1, read_only=True, data_only=True).active.iter_rows(values_only=True))
    raw2 = list(load_workbook(ATT2, read_only=True, data_only=True).active.iter_rows(values_only=True))
    reconciliation_rows = []
    map1 = {
        "temperature_c": 2, "ethanol_conversion_pct": 3, "ethylene_selectivity_pct": 4,
        "c4_selectivity_pct": 5, "acetaldehyde_selectivity_pct": 6,
        "c4_12_alcohol_selectivity_pct": 7,
        "methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct": 8,
        "other_selectivity_pct": 9,
    }
    map2 = {
        "time_min": 0, "ethanol_conversion_pct": 1, "ethylene_selectivity_pct": 2,
        "c4_selectivity_pct": 3, "acetaldehyde_selectivity_pct": 4,
        "c4_12_alcohol_selectivity_pct": 5,
        "methylbenzaldehyde_methylbenzyl_alcohol_selectivity_pct": 6,
        "other_selectivity_pct": 7,
    }
    for dataset, clean, raw, mapping in [
        ("附件1", a, raw1, map1), ("附件2", b, raw2, map2)
    ]:
        for field, raw_column in mapping.items():
            differences = [
                abs(float(raw[int(row.source_excel_row) - 1][raw_column]) - float(getattr(row, field)))
                for row in clean.itertuples(index=False)
            ]
            reconciliation_rows.append({
                "dataset": dataset, "field": field, "compared_count": len(differences),
                "mismatch_count": int(sum(value > 1e-12 for value in differences)),
                "max_abs_difference": max(differences, default=0),
                "tolerance": 1e-12,
            })
    reconciliation = pd.DataFrame(reconciliation_rows)

    return {
        "cleaned_attachment1.csv": a,
        "catalyst_combinations.csv": recipes,
        "cleaned_attachment2.csv": b,
        "modeling_dataset.csv": modeling_dataset,
        "temperature_coverage.csv": coverage,
        "combination_temperature_coverage_matrix.csv": coverage_matrix,
        "temperature_common_sets.csv": temperature_common_sets,
        "adjacent_temperature_differences.csv": adjacent_differences,
        "response_ranks_by_temperature.csv": response_ranks,
        "unobserved_existing_grid_cells.csv": unobserved,
        "yield_driver_diagnostic.csv": yield_driver,
        "temperature_summary.csv": temperature,
        "response_summary.csv": response_summary,
        "factor_levels.csv": pd.DataFrame(factor_rows),
        "cross_method_matched_combinations.csv": matched,
        "spearman_correlation.csv": spearman,
        "recipe_factor_spearman_correlation.csv": recipe_factor_correlation,
        "within_combination_trend_summary.csv": trend_summary,
        "matched_loading_method_response_differences.csv": matched_responses,
        "flagged_observations.csv": flagged,
        "attachment2_identity_similarity_diagnostic.csv": identity_similarity,
        "data_dictionary.csv": data_dictionary,
        "field_domain_audit.csv": domain_audit,
        "raw_clean_reconciliation.csv": reconciliation,
        "recipe_parse_verification.csv": recipe_verification,
        "top20_observed_yield.csv": a.nlargest(20, "c4_yield_pct")[top_columns],
        "top20_observed_yield_below350.csv": a[a.temperature_c < 350].nlargest(20, "c4_yield_pct")[top_columns],
        "selectivity_closure.csv": closure,
        "missingness.csv": pd.DataFrame(missing_rows),
    }


def plot_all(a: pd.DataFrame, recipes: pd.DataFrame, b: pd.DataFrame) -> list[Path]:
    paths: list[Path] = []
    ids = sorted(a.catalyst_id.unique(), key=lambda x: (x[0], int(x[1:])))
    temps = sorted(a.temperature_c.unique())

    matrix = a.assign(observed=1).pivot(
        index="catalyst_id", columns="temperature_c", values="observed"
    ).reindex(index=ids, columns=temps)
    fig, ax = plt.subplots(figsize=(7.2, 6.3))
    sns.heatmap(matrix, cmap=sns.color_palette(["#F1F3F5", COLORS["blue"]], as_cmap=True),
                cbar=False, linewidths=.4, linecolor="white", ax=ax)
    ax.set(xlabel="温度（°C）", ylabel="催化剂组合", title="附件1各组合的温度观测覆盖")
    paths += save_fig(fig, "01_temperature_coverage")

    descriptions = recipes.set_index("catalyst_id").reindex(ids)
    fig, axes = plt.subplots(1, 4, figsize=(12.5, 6.3), sharey=True)
    description_fields = [
        ("co_loading_wt_pct", "Co负载量（wt%）", COLORS["blue"]),
        ("cosio2_mass_mg", "Co/SiO2质量（mg）", COLORS["sky"]),
        ("hap_mass_mg", "HAP质量（mg）", COLORS["orange"]),
        ("ethanol_condition_ml_min", "附件所列乙醇条件（ml/min）", COLORS["green"]),
    ]
    y = np.arange(len(ids))
    for ax, (field, label, color) in zip(axes, description_fields):
        ax.scatter(descriptions[field], y, color=color, s=28)
        ax.set(xlabel=label, yticks=y)
        ax.grid(axis="x", color="#E5E7EB", linewidth=.6)
    axes[0].set_yticklabels(ids)
    axes[0].set_ylabel("完整催化剂组合")
    fig.suptitle("21种完整催化剂组合的配方描述（非独立决策因素）")
    fig.tight_layout()
    paths += save_fig(fig, "02_combination_descriptions")

    labels = {
        "ethanol_conversion_pct": "乙醇转化率（%）",
        "c4_selectivity_pct": "C4烯烃选择性（%）",
        "c4_yield_pct": "C4烯烃收率（%）",
    }
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 3.5))
    for ax, column, color in zip(axes, RESPONSES, [COLORS["blue"], COLORS["orange"], COLORS["green"]]):
        sns.histplot(a[column], bins="auto", kde=True, color=color, ax=ax)
        ax.axvline(a[column].median(), color="black", linestyle="--", label="中位数")
        ax.set(xlabel=labels[column], ylabel="观测数")
        ax.legend(frameon=False)
    fig.suptitle("附件1三个核心响应的原始分布", y=1.03)
    fig.tight_layout()
    paths += save_fig(fig, "03_response_distributions")

    common_temperatures = [250, 275, 300, 350]
    common = a[a.temperature_c.isin(common_temperatures)]
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.3), sharex=True)
    for ax, response, color in zip(
        axes, RESPONSES, [COLORS["blue"], COLORS["orange"], COLORS["green"]]
    ):
        sns.boxplot(data=common, x="temperature_c", y=response, color="white",
                    width=.55, fliersize=0, ax=ax)
        sns.stripplot(data=common, x="temperature_c", y=response, color=color,
                      size=3.2, alpha=.72, jitter=.18, ax=ax)
        ax.set(xlabel="全组合共同温度标签（°C）", ylabel=labels[response])
    fig.suptitle("21种完整组合在四个全覆盖温度标签下的响应分布")
    fig.tight_layout()
    paths += save_fig(fig, "04_common_temperature_distributions")

    fig, axes = plt.subplots(7, 3, figsize=(12, 18))
    for ax, cid in zip(axes.flat, ids):
        group = a[a.catalyst_id == cid].sort_values("temperature_c")
        for response, color, marker, style, label in [
            ("ethanol_conversion_pct", COLORS["blue"], "o", "-", "转化率"),
            ("c4_selectivity_pct", COLORS["orange"], "s", "--", "C4选择性"),
            ("c4_yield_pct", COLORS["green"], "^", ":", "C4收率"),
        ]:
            ax.plot(group.temperature_c, group[response], color=color, marker=marker,
                    linestyle=style, linewidth=1.4, label=label)
        ax.set(title=cid, xlabel="温度（°C）", ylabel="百分比（%）")
    handles, legend_labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=3, frameon=False,
               bbox_to_anchor=(.5, .987))
    fig.suptitle("21种催化剂组合的温度响应小多图", y=1.005)
    fig.tight_layout(rect=[0, 0, 1, .972])
    paths += save_fig(fig, "05_per_combination_profiles")

    yield_matrix = a.pivot(index="catalyst_id", columns="temperature_c", values="c4_yield_pct").reindex(
        index=ids, columns=temps
    )
    fig, ax = plt.subplots(figsize=(8, 7))
    sns.heatmap(yield_matrix, cmap=sns.light_palette(COLORS["vermillion"], as_cmap=True),
                annot=True, fmt=".1f", linewidths=.35,
                cbar_kws={"label": "C4烯烃收率（%）"}, ax=ax)
    ax.set(xlabel="温度（°C）", ylabel="催化剂组合", title="附件1已观测C4烯烃收率")
    paths += save_fig(fig, "06_observed_yield_heatmap")

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.8))
    closure_a = a.selectivity_closure_error_pct_point.where(
        a.selectivity_closure_error_pct_point.abs() >= 1e-10, 0
    )
    closure_b = b.selectivity_closure_error_pct_point.where(
        b.selectivity_closure_error_pct_point.abs() >= 1e-10, 0
    )
    axes[0].scatter(np.arange(len(a)), closure_a,
                    color=COLORS["blue"], s=16)
    axes[0].axhline(0, color="black", linestyle="--")
    axes[0].set(xlabel="附件1观测序号", ylabel="合计误差（百分点）", title="附件1选择性闭合误差")
    axes[0].set_ylim(-.01, .01)
    axes[0].text(.5, .82, "114条记录在1e-10容差内均闭合",
                 transform=axes[0].transAxes, ha="center")
    axes[1].plot(b.time_min, closure_b,
                 color=COLORS["orange"], marker="s")
    axes[1].axhline(0, color="black", linestyle="--")
    axes[1].set(xlabel="时间（min）", ylabel="合计误差（百分点）", title="附件2选择性闭合误差")
    axes[1].set_ylim(-.01, .01)
    axes[1].text(.5, .82, "7条记录在1e-10容差内均闭合",
                 transform=axes[1].transAxes, ha="center")
    fig.tight_layout()
    paths += save_fig(fig, "07_selectivity_closure")

    fig, axes = plt.subplots(1, 3, figsize=(14.5, 6.6), sharey=True)
    for ax, response, title in zip(
        axes, RESPONSES, ["转化率排名", "C4选择性排名", "C4收率排名"]
    ):
        rank_matrix = (
            a.assign(rank=a.groupby("temperature_c")[response].rank(
                method="min", ascending=False
            ))
            .pivot(index="catalyst_id", columns="temperature_c", values="rank")
            .reindex(index=ids, columns=temps)
        )
        sns.heatmap(rank_matrix, cmap="Blues_r", annot=True, fmt=".0f",
                    linewidths=.35, cbar=False, ax=ax)
        ax.set(xlabel="离散温度标签（°C）", ylabel="完整催化剂组合", title=title)
    fig.suptitle("各离散温度标签下已观测完整组合的响应排名（1为最高）")
    fig.tight_layout()
    paths += save_fig(fig, "08_response_rank_heatmaps")

    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for column, label, color, marker, style in [
        ("ethanol_conversion_pct", "乙醇转化率", COLORS["blue"], "o", "-"),
        ("c4_selectivity_pct", "C4选择性", COLORS["orange"], "s", "--"),
        ("c4_yield_pct", "C4收率", COLORS["green"], "^", ":"),
    ]:
        axes[0].plot(b.time_min, b[column], label=label, color=color,
                     marker=marker, linestyle=style, linewidth=1.8)
    axes[0].set(xlabel="时间（min）", ylabel="百分比（%）", title="350 °C单次实验核心响应")
    axes[0].legend(frameon=False)
    for column, label, color, marker in zip(
        PRODUCTS,
        ["乙烯", "C4烯烃", "乙醛", "C4—C12脂肪醇",
         "甲基苯甲醛和甲基苯甲醇", "其他"],
        [COLORS["sky"], COLORS["orange"], COLORS["purple"],
         COLORS["green"], COLORS["vermillion"], COLORS["gray"]],
        ["o", "s", "^", "D", "P", "X"],
    ):
        axes[1].plot(b.time_min, b[column], label=label, color=color,
                     marker=marker, linewidth=1.3)
    axes[1].set(xlabel="时间（min）", ylabel="产物选择性（%）",
                title="350 °C单次实验的六类选择性")
    axes[1].legend(frameon=False, fontsize=7, loc="upper center", ncol=2)
    fig.tight_layout()
    paths += save_fig(fig, "09_attachment2_time_series")

    top = a.nlargest(15, "c4_yield_pct").sort_values("c4_yield_pct")
    bar_labels = top.catalyst_id + " / " + top.temperature_c.astype(int).astype(str) + " °C"
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    ax.barh(bar_labels, top.c4_yield_pct,
            color=[COLORS["blue"] if x == "I" else COLORS["orange"] for x in top.loading_method])
    for index, value in enumerate(top.c4_yield_pct):
        ax.text(value + .3, index, f"{value:.2f}", va="center", fontsize=8)
    ax.set(xlabel="已观测C4烯烃收率（%）", ylabel="组合 / 温度",
           title="附件1已观测收率最高的15个条件")
    ax.set_xlim(0, top.c4_yield_pct.max() * 1.13)
    paths += save_fig(fig, "10_top_observed_yield")
    return paths


def summary(a: pd.DataFrame, recipes: pd.DataFrame, b: pd.DataFrame,
            meta1: dict[str, object], meta2: dict[str, object]) -> dict[str, object]:
    best = a.loc[a.c4_yield_pct.idxmax()]
    low = a.loc[a[a.temperature_c < 350].c4_yield_pct.idxmax()]
    match_keys = ["cosio2_mass_mg", "co_loading_wt_pct", "hap_mass_mg",
                  "quartz_mass_mg", "ethanol_condition_ml_min"]
    matched_count = recipes.groupby(match_keys, dropna=False).loading_method.nunique().gt(1).sum()
    return {
        "schema_version": "1.0",
        "identity": {
            "problem": "2021 CUMCM B题",
            "stage": "技术主线第2步",
            "attachment2_catalyst_identity": "题面未给出；默认不映射到A1—B7",
            "catalyst_domain": "A1—A14、B1—B7共21种完整不可拆分类别",
            "temperature_domain": "250、275、300、325、350、400、450°C有序离散标签",
        },
        "source_files": {
            str(ATT1.relative_to(ROOT)): {"sha256": file_hash(ATT1), "bytes": ATT1.stat().st_size, **meta1},
            str(ATT2.relative_to(ROOT)): {"sha256": file_hash(ATT2), "bytes": ATT2.stat().st_size, **meta2},
        },
        "attachment1": {
            "record_count": len(a), "catalyst_count": a.catalyst_id.nunique(),
            "loading_method_counts": recipes.loading_method.value_counts().to_dict(),
            "temperature_levels_c": sorted(a.temperature_c.unique().tolist()),
            "missing_core_value_count": int(a[
                ["catalyst_id", "temperature_c", "ethanol_conversion_pct", "c4_selectivity_pct"]
            ].isna().sum().sum()),
            "duplicate_catalyst_temperature_count": int(a.duplicate_catalyst_temperature.sum()),
            "selectivity_sum_range_pct": [a.selectivity_sum_pct.min(), a.selectivity_sum_pct.max()],
            "max_abs_closure_error_pct_point": a.selectivity_closure_abs_error_pct_point.max(),
            "matched_recipe_across_loading_method_count": int(matched_count),
            "observed_best": {
                "catalyst_id": best.catalyst_id, "temperature_c": best.temperature_c,
                "conversion_pct": best.ethanol_conversion_pct,
                "c4_selectivity_pct": best.c4_selectivity_pct, "c4_yield_pct": best.c4_yield_pct,
            },
            "observed_best_below_350": {
                "catalyst_id": low.catalyst_id, "temperature_c": low.temperature_c,
                "conversion_pct": low.ethanol_conversion_pct,
                "c4_selectivity_pct": low.c4_selectivity_pct, "c4_yield_pct": low.c4_yield_pct,
            },
            "global_iqr_flag_counts": {
                x: int(a[f"{x}_global_iqr_flag"].sum()) for x in RESPONSES
            },
            "within_temperature_robust_flag_counts": {
                x: int(a[f"{x}_within_temperature_flag"].sum()) for x in RESPONSES
            },
        },
        "attachment2": {
            "record_count": len(b), "time_points_min": b.time_min.tolist(),
            "time_gap_min": b.time_gap_min.dropna().tolist(),
            "selectivity_sum_range_pct": [b.selectivity_sum_pct.min(), b.selectivity_sum_pct.max()],
            "conversion_first_last_pct": [b.ethanol_conversion_pct.iloc[0], b.ethanol_conversion_pct.iloc[-1]],
            "c4_selectivity_first_last_pct": [b.c4_selectivity_pct.iloc[0], b.c4_selectivity_pct.iloc[-1]],
            "yield_first_last_pct": [b.c4_yield_pct.iloc[0], b.c4_yield_pct.iloc[-1]],
        },
        "data_treatments": [
            "附件1合并单元格按Excel视觉语义前向填充",
            "完全空的尾列不进入数据表，不删除有效观测",
            "催化剂描述解析为数值因素并保留原始描述",
            "百分数收率按转化率乘选择性再除以100",
            "异常观测只加标记，不删除、不缩尾、不插补",
            "附件2催化剂身份记录为未知，不自动匹配附件1",
            "正式模型接口不读取配方拆分字段，只使用21种完整组合类别",
            "温度按7水平有序离散标签处理，不连续插值或推荐标签外温度",
        ],
        "known_design_risks": [
            "组合温度覆盖不完全一致",
            "催化剂因素不是完整平衡析因设计，存在混杂",
            "附件1没有独立重复实验",
            "附件2是一次实验的7个时间点，不是独立重复",
            "附件乙醇字段保留ml/min单位，结构化字段不自行判定为浓度或流量",
        ],
    }


def write_outputs(tables: dict[str, pd.DataFrame], audit: dict[str, object],
                  figures: list[Path], started: datetime) -> None:
    for name, frame in tables.items():
        frame.to_csv(TABLES / name, index=False, encoding="utf-8-sig")
    audit_path = OUT / "audit_summary.json"
    audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest_path = OUT / "run_manifest.json"
    manifest = {
        "schema_version": "1.0",
        "producer": str(Path(__file__).resolve().relative_to(ROOT)),
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "python": sys.version, "platform": platform.platform(),
        "packages": {
            "pandas": pd.__version__, "numpy": np.__version__,
            "matplotlib": matplotlib.__version__, "seaborn": sns.__version__,
        },
        "inputs": {str(p.relative_to(ROOT)): file_hash(p) for p in [ATT1, ATT2]},
        "random_seed": None, "notes": "确定性审计与制图，不使用随机算法。",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    artifacts = []
    auxiliary_tables = {
        "factor_levels.csv", "cross_method_matched_combinations.csv",
        "spearman_correlation.csv", "recipe_factor_spearman_correlation.csv",
        "matched_loading_method_response_differences.csv",
        "attachment2_identity_similarity_diagnostic.csv",
    }
    paths = [audit_path, manifest_path] + [TABLES / x for x in tables] + figures
    for path in paths:
        if path.suffix in {".png", ".pdf"}:
            kind, consumer, status = (
                "figure", "用户视觉复核、数据审计报告、后续论文候选图", "current"
            )
        elif path.name == "modeling_dataset.csv":
            kind, consumer, status = (
                "model_input", "第3步探索、第4步基线和获批正式模型", "current"
            )
        elif path.name in {"cleaned_attachment1.csv", "cleaned_attachment2.csv", "catalyst_combinations.csv"}:
            kind, consumer, status = (
                "clean_data", "审计追踪；正式模型默认只读取modeling_dataset.csv", "current"
            )
        elif path.name in auxiliary_tables:
            kind, consumer, status = (
                "auxiliary_diagnostic", "数据审计解释；正式模型默认不得读取", "auxiliary"
            )
        else:
            kind, consumer, status = "audit", "数据审计报告与独立复核", "current"
        artifacts.append({
            "path": str(path.relative_to(ROOT)), "artifact_type": kind,
            "producer": str(Path(__file__).resolve().relative_to(ROOT)),
            "consumer": consumer, "bytes": path.stat().st_size,
            "sha256": file_hash(path), "status": status,
        })
    pd.DataFrame(artifacts).to_csv(OUT / "artifact_manifest.csv", index=False, encoding="utf-8-sig")


def main() -> None:
    started = datetime.now(ZoneInfo("Asia/Shanghai"))
    TABLES.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    setup_plotting()
    a, recipes, meta1 = read_attachment1()
    b, meta2 = read_attachment2()
    tables = audit_tables(a, recipes, b)
    figures = plot_all(a, recipes, b)
    write_outputs(tables, summary(a, recipes, b, meta1, meta2), figures, started)
    print(json.dumps({
        "status": "ok", "attachment1_records": len(a), "attachment2_records": len(b),
        "table_count": len(tables), "figure_file_count": len(figures),
        "output": str(OUT.relative_to(ROOT)),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
