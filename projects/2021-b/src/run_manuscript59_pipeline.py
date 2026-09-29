#!/usr/bin/env python3
"""统一重跑《59初稿》17张表、3张图及对应独立验证。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = [
    "src/data_audit/01_audit_and_visualize.py",
    "src/data_audit/02_verify_audit.py",
    "src/eda/01_discrete_eda.py",
    "src/eda/02_verify_eda.py",
    "src/q1/01_question1_analysis.py",
    "src/q1/02_verify_question1.py",
    "src/q1/03_manuscript59_loo_prediction.py",
    "src/q1/04_verify_manuscript59_loo_prediction.py",
    "src/q1/05_manuscript59_tables_figures.py",
    "src/q1/06_verify_manuscript59_tables_figures.py",
    "src/q2/01_common_temperature_baseline.py",
    "src/q2/02_verify_common_temperature_baseline.py",
    "src/q2/03_additive_effects.py",
    "src/q2/04_verify_additive_effects.py",
    "src/q2/05_structural_robustness.py",
    "src/q2/06_verify_structural_robustness.py",
    "src/q3/03_formal_solution.py",
    "src/q3/04_verify_formal_solution.py",
    "src/q3/07_manuscript59_component_pchip.py",
    "src/q3/08_verify_manuscript59_component_pchip.py",
    "src/q4/01_build_formal_design.py",
    "src/q4/02_verify_formal_design.py",
    "src/q4/03_robustness_and_explanation.py",
    "src/q4/04_verify_robustness.py",
]


def main() -> None:
    for index, relative_path in enumerate(SCRIPTS, start=1):
        print(f"[{index:02d}/{len(SCRIPTS):02d}] {relative_path}", flush=True)
        subprocess.run([sys.executable, "-B", relative_path], cwd=ROOT, check=True)
    print("《59初稿》全篇代码流水线运行完成。")


if __name__ == "__main__":
    main()

