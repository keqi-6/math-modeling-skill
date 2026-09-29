#!/usr/bin/env python3
"""核对《59初稿》第一问表1显示值及图1—3文件完整性。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/q1/manuscript59"


def main() -> None:
    table = pd.read_csv(OUT / "table1_overall_linear_summary.csv")
    expected = {
        "ethanol_conversion_pct": (3.283, 16.574, 8.330, 4.183, 0.883),
        "c4_selectivity_pct": (1.292, 6.530, 5.068, 1.986, 0.943),
    }
    table_ok = True
    details = []
    for row in table.itertuples(index=False):
        actual = tuple(round(value, 3) for value in (
            row.slope_per_25c_min_pct_point,
            row.slope_per_25c_max_pct_point,
            row.median_slope_per_25c_pct_point,
            row.median_mae_pct_point,
            row.median_r_squared,
        ))
        table_ok &= actual == expected[row.response]
        details.append(f"{row.response}={actual}")
    figure_paths = [
        OUT / "figures" / f"{stem}.{extension}"
        for stem in (
            "figure1_standardized_adjacent_changes",
            "figure2_leave_one_out_slopes",
            "figure3_attachment2_time_changes",
        )
        for extension in ("png", "pdf")
    ]
    figures_ok = all(path.exists() and path.stat().st_size > 1000 for path in figure_paths)
    checks = [
        {"check": "底稿表1显示值", "passed": bool(table_ok), "detail": "; ".join(details)},
        {"check": "图1—3双格式非空", "passed": bool(figures_ok), "detail": f"files={len(figure_paths)}"},
    ]
    result = {
        "schema_version": "1.0",
        "passed": bool(all(item["passed"] for item in checks)),
        "checks_passed": int(sum(item["passed"] for item in checks)),
        "checks_total": len(checks),
        "checks": checks,
    }
    (OUT / "tables_figures_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
