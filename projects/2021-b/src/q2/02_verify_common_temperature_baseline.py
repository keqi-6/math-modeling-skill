#!/usr/bin/env python3
"""独立复算第二问S5基线的覆盖、配对计数和关键摘要。"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "output" / "data_audit" / "tables" / "cleaned_attachment1.csv"
OUT = ROOT / "output" / "q2"
TABLES = OUT / "tables"
COMMON = [250.0, 275.0, 300.0, 350.0]
RESPONSES = ("ethanol_conversion_pct", "c4_selectivity_pct")


def main() -> None:
    data = pd.read_csv(INPUT)
    distributions = pd.read_csv(TABLES / "common_temperature_distributions.csv")
    changes = pd.read_csv(TABLES / "common_temperature_paired_changes.csv")
    supplemental = pd.read_csv(TABLES / "supplemental_matched_changes.csv")
    checks = []

    common = data[data["temperature_c"].isin(COMMON)]
    coverage = common.groupby("temperature_c")["catalyst_id"].nunique().to_dict()
    checks.append({
        "check": "共同温度覆盖",
        "passed": coverage == {temperature: 21 for temperature in COMMON}
        and len(common) == 84,
        "detail": f"cells={len(common)}, coverage={coverage}",
    })
    checks.append({
        "check": "主体配对记录数",
        "passed": len(changes) == 3 * 21 * 2,
        "detail": f"rows={len(changes)}, expected=126",
    })
    checks.append({
        "check": "补充配对记录数",
        "passed": len(supplemental) == (10 + 10 + 19 + 1) * 2,
        "detail": f"rows={len(supplemental)}, expected=80",
    })

    max_errors = []
    for row in distributions.itertuples(index=False):
        values = common[common["temperature_c"] == row.temperature_c][row.response]
        max_errors.extend([
            abs(float(values.mean()) - row.mean_pct),
            abs(float(values.median()) - row.median_pct),
            abs(float(values.min()) - row.min_pct),
            abs(float(values.max()) - row.max_pct),
        ])
    checks.append({
        "check": "同温分布独立复算",
        "passed": max(max_errors) < 1e-10,
        "detail": f"max_abs_error={max(max_errors):.3e}",
    })

    change_errors = []
    for row in changes.itertuples(index=False):
        before = data[
            (data["catalyst_id"] == row.catalyst_id)
            & (data["temperature_c"] == row.temperature_from_c)
        ][row.response].iloc[0]
        after = data[
            (data["catalyst_id"] == row.catalyst_id)
            & (data["temperature_c"] == row.temperature_to_c)
        ][row.response].iloc[0]
        change_errors.append(abs(float(after - before) - row.change_pct_point))
    checks.append({
        "check": "主体配对增量独立复算",
        "passed": max(change_errors) < 1e-10,
        "detail": f"max_abs_error={max(change_errors):.3e}",
    })

    result = {
        "status": "s5_baseline_independent_verification",
        "passed": bool(all(item["passed"] for item in checks)),
        "checks": checks,
    }
    (OUT / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
