"""独立核对第二问S6候选诊断的关键恒等式与数值。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[3]
INPUT = ROOT / "output/data_audit/tables/cleaned_attachment1.csv"
SUMMARY = ROOT / "output/q2/candidates/candidate_information_comparison.csv"
OUTPUT = ROOT / "output/q2/candidates/verification.json"
TEMPERATURES = [250.0, 275.0, 300.0, 350.0]
RESPONSES = ["ethanol_conversion_pct", "c4_selectivity_pct"]


def main() -> None:
    data = pd.read_csv(INPUT)
    data = data[data["temperature_c"].isin(TEMPERATURES)].copy()
    saved = pd.read_csv(SUMMARY).set_index("response")
    checks = []

    checks.append(
        {
            "check": "平衡主体覆盖",
            "passed": bool(
                len(data) == 84
                and data.groupby("temperature_c")["catalyst_id"].nunique().eq(21).all()
            ),
            "detail": f"rows={len(data)}",
        }
    )
    for response in RESPONSES:
        grand = data[response].mean()
        combination_mean = data.groupby("catalyst_id")[response].mean()
        temperature_mean = data.groupby("temperature_c")[response].mean()
        total = float(((data[response] - grand) ** 2).sum())
        combination = float(4 * ((combination_mean - grand) ** 2).sum())
        temperature = float(21 * ((temperature_mean - grand) ** 2).sum())
        residual = total - combination - temperature
        row = saved.loc[response]
        errors = [
            abs(total - row["total_ss"]),
            abs(combination - row["combination_ss"]),
            abs(temperature - row["temperature_ss"]),
            abs(residual - row["additive_nonadditive_ss"]),
        ]
        checks.append(
            {
                "check": f"{response}平方和独立复算",
                "passed": bool(max(errors) < 1e-9),
                "detail": f"max_abs_error={max(errors):.3e}",
            }
        )
        checks.append(
            {
                "check": f"{response}正交分解闭合",
                "passed": bool(
                    abs(total - combination - temperature - residual) < 1e-9
                ),
                "detail": f"closure_error={abs(total - combination - temperature - residual):.3e}",
            }
        )

    payload = {
        "status": "s6_candidate_diagnostic_independent_verification",
        "passed": bool(all(bool(item["passed"]) for item in checks)),
        "checks": checks,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if not payload["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
