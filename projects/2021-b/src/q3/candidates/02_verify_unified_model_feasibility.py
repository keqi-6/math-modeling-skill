#!/usr/bin/env python3
# 输入: output/data_audit/tables/cleaned_attachment1.csv,
#       output/q3/candidates/unified_model_audit/predictions.csv,
#       output/q3/candidates/unified_model_audit/fold_settings.csv,
#       output/q3/candidates/unified_model_audit/summary.json
# 输出: output/q3/candidates/unified_model_audit/verification.json
# 职责: 独立复算候选误差、外层分块结构和调参范围，不导入候选主程序

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "output/q3/candidates/unified_model_audit"
DATA = pd.read_csv(ROOT / "output/data_audit/tables/cleaned_attachment1.csv")
PRED = pd.read_csv(OUT / "predictions.csv")
SETTINGS = pd.read_csv(OUT / "fold_settings.csv")
SUMMARY = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    checks = []
    expected_models = {
        "local_baseline",
        "temperature_only",
        "shared_combination_curve",
        "factor_surface",
    }
    checks.append(
        {
            "check": "模型与任务覆盖",
            "passed": set(PRED.model) == expected_models
            and set(PRED.task)
            == {"interior_cell", "leave_combination_out", "leave_temperature_out"},
        }
    )
    no_duplicates = not PRED.duplicated(
        ["task", "fold_id", "model", "catalyst_id", "temperature_c"]
    ).any()
    checks.append({"check": "逐预测记录唯一", "passed": bool(no_duplicates)})
    alpha_ok = SETTINGS["alpha"].isin([0.01, 0.1, 1, 10, 100, 1000]).all()
    checks.append({"check": "正则强度仅来自预设网格", "passed": bool(alpha_ok)})
    metric_errors = []
    for item in SUMMARY["metrics"]:
        g = PRED[(PRED.task == item["task"]) & (PRED.model == item["model"])]
        err = g.observed - g.predicted
        values = {
            "mae": np.abs(err).mean(),
            "rmse": np.sqrt(np.mean(err**2)),
            "median_ae": np.median(np.abs(err)),
            "max_ae": np.max(np.abs(err)),
        }
        metric_errors.extend(abs(values[k] - item[k]) for k in values)
    checks.append(
        {
            "check": "汇总误差独立复算",
            "passed": bool(max(metric_errors) < 1e-12),
            "detail": f"max_abs_error={max(metric_errors):.3e}",
        }
    )
    combo_rows = PRED[PRED.task == "leave_combination_out"]
    combo_fold_ok = all(
        g["catalyst_id"].nunique() == 1 and g["catalyst_id"].iloc[0] == str(fold)
        for fold, g in combo_rows.groupby("fold_id")
    )
    checks.append({"check": "整组合外层测试块", "passed": bool(combo_fold_ok)})
    temp_rows = PRED[PRED.task == "leave_temperature_out"]
    temp_fold_ok = all(
        g["temperature_c"].nunique() == 1
        and float(g["temperature_c"].iloc[0]) == float(fold)
        for fold, g in temp_rows.groupby("fold_id")
    )
    checks.append({"check": "整温度外层测试块", "passed": bool(temp_fold_ok)})
    finite = np.isfinite(PRED[["observed", "predicted"]].to_numpy()).all()
    checks.append({"check": "预测有限且非缺失", "passed": bool(finite)})
    verification = {
        "status": "candidate_verification",
        "passed": all(x["passed"] for x in checks),
        "check_count": len(checks),
        "checks": checks,
        "note": "通过只证明候选比较产物内部一致，不批准模型或预测范围。",
        "artifacts": [
            {
                "path": str(path.relative_to(ROOT)),
                "sha256": sha256(path),
                "producer": "src/q3/candidates/01_unified_model_feasibility.py",
                "consumer": "本验证与统一模型可行性审计报告",
            }
            for path in [
                OUT / "predictions.csv",
                OUT / "fold_settings.csv",
                OUT / "summary.json",
            ]
        ],
    }
    (OUT / "verification.json").write_text(
        json.dumps(verification, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"候选独立验证: {sum(x['passed'] for x in checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
