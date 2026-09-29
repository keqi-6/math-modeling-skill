#!/usr/bin/env python3
# 输入: output/data_audit/tables/cleaned_attachment1.csv
# 输出: output/q3/candidates/unified_model_audit/predictions.csv,
#       output/q3/candidates/unified_model_audit/fold_settings.csv,
#       output/q3/candidates/unified_model_audit/summary.json
# 职责: 用分块外层验证和训练集内调参比较统一收率模型与透明局部基线，不产生正式推荐

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
OUT = ROOT / "output/q3/candidates/unified_model_audit"
ALPHAS = np.array([0.01, 0.1, 1.0, 10.0, 100.0, 1000.0])
TARGET = "c4_yield_pct"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def add_engineered_fields(data: pd.DataFrame) -> pd.DataFrame:
    d = data.copy()
    d["loading_method_II"] = (d["loading_method"] == "II").astype(float)
    d["has_hap_num"] = d["has_hap"].astype(str).str.lower().eq("true").astype(float)
    return d


def feature_matrix(
    train: pd.DataFrame, test: pd.DataFrame, model: str
) -> tuple[np.ndarray, np.ndarray]:
    t0 = 325.0
    scale = 75.0

    def temperature_part(frame: pd.DataFrame) -> list[np.ndarray]:
        z = (frame["temperature_c"].to_numpy(float) - t0) / scale
        return [z, z**2]

    tr_parts = temperature_part(train)
    te_parts = temperature_part(test)
    if model == "temperature_only":
        pass
    elif model == "shared_combination_curve":
        levels = sorted(train["catalyst_id"].unique())
        tr_z = tr_parts[0]
        te_z = te_parts[0]
        for level in levels:
            tr_ind = (train["catalyst_id"].to_numpy() == level).astype(float)
            te_ind = (test["catalyst_id"].to_numpy() == level).astype(float)
            tr_parts.extend([tr_ind, tr_ind * tr_z])
            te_parts.extend([te_ind, te_ind * te_z])
    elif model == "factor_surface":
        cols = [
            "co_loading_wt_pct",
            "cosio2_mass_mg",
            "hap_mass_mg",
            "ethanol_condition_ml_min",
            "loading_method_II",
            "has_hap_num",
        ]
        tr_z = tr_parts[0]
        te_z = te_parts[0]
        for col in cols:
            a = train[col].to_numpy(float)
            b = test[col].to_numpy(float)
            tr_parts.extend([a, a * tr_z])
            te_parts.extend([b, b * te_z])
    else:
        raise ValueError(model)
    return np.column_stack(tr_parts), np.column_stack(te_parts)


def ridge_predict(
    train: pd.DataFrame, test: pd.DataFrame, model: str, alpha: float
) -> np.ndarray:
    x_train, x_test = feature_matrix(train, test, model)
    scaler = StandardScaler()
    x_train = scaler.fit_transform(x_train)
    x_test = scaler.transform(x_test)
    fit = Ridge(alpha=float(alpha))
    fit.fit(x_train, train[TARGET].to_numpy(float))
    return fit.predict(x_test)


def local_predict(train: pd.DataFrame, test: pd.DataFrame, task: str) -> np.ndarray:
    result = []
    global_mean = float(train[TARGET].mean())
    for _, row in test.iterrows():
        same_combo = train[train["catalyst_id"] == row["catalyst_id"]].sort_values(
            "temperature_c"
        )
        same_temp = train[train["temperature_c"] == row["temperature_c"]]
        if task == "leave_combination_out":
            value = float(same_temp[TARGET].mean()) if len(same_temp) else global_mean
        elif len(same_combo) >= 2:
            x = same_combo["temperature_c"].to_numpy(float)
            y = same_combo[TARGET].to_numpy(float)
            value = float(np.interp(row["temperature_c"], x, y))
            if row["temperature_c"] < x.min() or row["temperature_c"] > x.max():
                nearest = np.argsort(np.abs(x - row["temperature_c"]))[:2]
                slope = (y[nearest[1]] - y[nearest[0]]) / (x[nearest[1]] - x[nearest[0]])
                value = float(y[nearest[0]] + slope * (row["temperature_c"] - x[nearest[0]]))
        elif len(same_temp):
            value = float(same_temp[TARGET].mean())
        else:
            value = global_mean
        result.append(value)
    return np.array(result)


def outer_splits(data: pd.DataFrame, task: str) -> list[tuple[str, np.ndarray, np.ndarray]]:
    splits = []
    if task == "interior_cell":
        for catalyst, group in data.groupby("catalyst_id"):
            lo, hi = group["temperature_c"].min(), group["temperature_c"].max()
            for idx in group.index[(group["temperature_c"] > lo) & (group["temperature_c"] < hi)]:
                test = np.array([idx])
                train = data.index[data.index != idx].to_numpy()
                splits.append((f"{catalyst}_{data.loc[idx, 'temperature_c']:g}", train, test))
    elif task == "leave_combination_out":
        for catalyst in sorted(data["catalyst_id"].unique()):
            test = data.index[data["catalyst_id"] == catalyst].to_numpy()
            train = data.index[data["catalyst_id"] != catalyst].to_numpy()
            splits.append((catalyst, train, test))
    elif task == "leave_temperature_out":
        for temp in sorted(data["temperature_c"].unique()):
            test = data.index[data["temperature_c"] == temp].to_numpy()
            train = data.index[data["temperature_c"] != temp].to_numpy()
            splits.append((f"{temp:g}", train, test))
    return splits


def inner_splits(train: pd.DataFrame, task: str) -> list[tuple[np.ndarray, np.ndarray]]:
    positions = np.arange(len(train))
    folds: list[np.ndarray] = []
    if task == "leave_combination_out":
        groups = sorted(train["catalyst_id"].unique())
        for k in range(5):
            chosen = set(groups[k::5])
            folds.append(positions[train["catalyst_id"].isin(chosen).to_numpy()])
    elif task == "leave_temperature_out":
        temps = sorted(train["temperature_c"].unique())
        for k in range(min(4, len(temps))):
            chosen = set(temps[k:: min(4, len(temps))])
            folds.append(positions[train["temperature_c"].isin(chosen).to_numpy()])
    else:
        rank = train.groupby("catalyst_id")["temperature_c"].rank(method="first").astype(int)
        for k in range(5):
            folds.append(positions[(rank.to_numpy() - 1) % 5 == k])
    result = []
    for valid in folds:
        if len(valid) == 0 or len(valid) == len(train):
            continue
        mask = np.ones(len(train), dtype=bool)
        mask[valid] = False
        result.append((positions[mask], valid))
    return result


def choose_alpha(train: pd.DataFrame, model: str, task: str) -> tuple[float, float]:
    scores = []
    splits = inner_splits(train, task)
    for alpha in ALPHAS:
        fold_errors = []
        for tr_pos, va_pos in splits:
            tr = train.iloc[tr_pos]
            va = train.iloc[va_pos]
            pred = ridge_predict(tr, va, model, float(alpha))
            fold_errors.extend(np.abs(va[TARGET].to_numpy(float) - pred))
        scores.append(float(np.mean(fold_errors)))
    best = int(np.argmin(scores))
    return float(ALPHAS[best]), scores[best]


def summarize(predictions: pd.DataFrame) -> dict:
    rows = []
    for (task, model), g in predictions.groupby(["task", "model"]):
        e = np.abs(g["observed"] - g["predicted"])
        rows.append(
            {
                "task": task,
                "model": model,
                "n": int(len(g)),
                "mae": float(e.mean()),
                "rmse": float(np.sqrt(np.mean((g["observed"] - g["predicted"]) ** 2))),
                "median_ae": float(e.median()),
                "max_ae": float(e.max()),
            }
        )
    metrics = pd.DataFrame(rows)
    for task in metrics["task"].unique():
        base = float(metrics[(metrics.task == task) & (metrics.model == "local_baseline")]["mae"].iloc[0])
        metrics.loc[metrics.task == task, "mae_change_vs_baseline_pct"] = (
            (metrics.loc[metrics.task == task, "mae"] - base) / base * 100
        )
    fold_rows = []
    for (task, fold_id), fold in predictions.groupby(["task", "fold_id"]):
        base = fold[fold.model == "local_baseline"]
        base_mae = float(np.mean(np.abs(base.observed - base.predicted)))
        for model, g in fold.groupby("model"):
            mae = float(np.mean(np.abs(g.observed - g.predicted)))
            fold_rows.append(
                {
                    "task": task,
                    "fold_id": str(fold_id),
                    "model": model,
                    "fold_mae": mae,
                    "baseline_fold_mae": base_mae,
                    "beats_baseline": bool(mae < base_mae - 1e-12),
                }
            )
    folds = pd.DataFrame(fold_rows)
    win_rows = []
    for (task, model), g in folds.groupby(["task", "model"]):
        win_rows.append(
            {
                "task": task,
                "model": model,
                "fold_count": int(len(g)),
                "folds_beating_baseline": int(g["beats_baseline"].sum()),
                "win_rate": float(g["beats_baseline"].mean()),
                "median_fold_mae_change": float(
                    np.median(g["fold_mae"] - g["baseline_fold_mae"])
                ),
            }
        )
    ranking_rows = []
    temp = predictions[predictions.task == "leave_temperature_out"]
    for (fold_id, model), g in temp.groupby(["fold_id", "model"]):
        if len(g) < 3:
            continue
        observed_top3 = set(g.nlargest(3, "observed")["catalyst_id"])
        predicted_top3 = set(g.nlargest(3, "predicted")["catalyst_id"])
        ranking_rows.append(
            {
                "temperature_c": float(fold_id),
                "model": model,
                "top1_correct": bool(
                    g.loc[g["observed"].idxmax(), "catalyst_id"]
                    == g.loc[g["predicted"].idxmax(), "catalyst_id"]
                ),
                "top3_overlap": int(len(observed_top3 & predicted_top3)),
                "rank_correlation": float(
                    g[["observed", "predicted"]].corr(method="spearman").iloc[0, 1]
                ),
            }
        )
    return {
        "metrics": metrics.sort_values(["task", "mae"]).to_dict(orient="records"),
        "fold_stability": pd.DataFrame(win_rows)
        .sort_values(["task", "model"])
        .to_dict(orient="records"),
        "leave_temperature_ranking": ranking_rows,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data = add_engineered_fields(pd.read_csv(INPUT)).reset_index(drop=True)
    models = ["temperature_only", "shared_combination_curve", "factor_surface"]
    prediction_rows = []
    setting_rows = []
    for task in ["interior_cell", "leave_combination_out", "leave_temperature_out"]:
        for fold_id, train_idx, test_idx in outer_splits(data, task):
            train, test = data.loc[train_idx], data.loc[test_idx]
            base = local_predict(train, test, task)
            for pos, (_, row) in enumerate(test.iterrows()):
                prediction_rows.append(
                    {
                        "task": task,
                        "fold_id": fold_id,
                        "model": "local_baseline",
                        "catalyst_id": row["catalyst_id"],
                        "temperature_c": row["temperature_c"],
                        "observed": row[TARGET],
                        "predicted": base[pos],
                    }
                )
            for model in models:
                alpha, inner_mae = choose_alpha(train, model, task)
                pred = ridge_predict(train, test, model, alpha)
                setting_rows.append(
                    {
                        "task": task,
                        "fold_id": fold_id,
                        "model": model,
                        "train_rows": len(train),
                        "test_rows": len(test),
                        "alpha": alpha,
                        "inner_mae": inner_mae,
                    }
                )
                for pos, (_, row) in enumerate(test.iterrows()):
                    prediction_rows.append(
                        {
                            "task": task,
                            "fold_id": fold_id,
                            "model": model,
                            "catalyst_id": row["catalyst_id"],
                            "temperature_c": row["temperature_c"],
                            "observed": row[TARGET],
                            "predicted": pred[pos],
                        }
                    )
    predictions = pd.DataFrame(prediction_rows)
    settings = pd.DataFrame(setting_rows)
    predictions.to_csv(OUT / "predictions.csv", index=False)
    settings.to_csv(OUT / "fold_settings.csv", index=False)
    summary = {
        "status": "candidate_only_not_approved",
        "input": str(INPUT.relative_to(ROOT)),
        "input_sha256": sha256(INPUT),
        "target": TARGET,
        "outer_tasks": {
            "interior_cell": "已有组合内遮住一个中间温度",
            "leave_combination_out": "整组遮住一种催化剂组合",
            "leave_temperature_out": "整块遮住一个温度",
        },
        "model_boundaries": {
            "local_baseline": "透明任务基线",
            "temperature_only": "只共享温度信息",
            "shared_combination_curve": "只适用于训练中出现过的完整组合",
            "factor_surface": "配方描述的预测候选，不作因果解释",
        },
        **summarize(predictions),
    }
    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"候选审计完成: {len(predictions)} 条逐模型预测")


if __name__ == "__main__":
    main()
