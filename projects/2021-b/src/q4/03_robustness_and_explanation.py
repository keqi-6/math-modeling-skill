#!/usr/bin/env python3
"""第四问S11：检查删去实验、替代重复和设备精度下的职责变化。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FORMAL = ROOT / "output" / "q4" / "formal" / "experiment_design.csv"
OUT = ROOT / "output" / "q4" / "robustness"
SCRIPT = Path(__file__).resolve()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def effective_roles(design: pd.DataFrame) -> set[str]:
    roles = {
        code
        for value in design["responsibility_codes"]
        for code in value.split("|")
    }
    has_pair = (
        ((design["catalyst_id"] == "A3") & (design["temperature_c"] == 375)).any()
        and
        ((design["catalyst_id"] == "A4") & (design["temperature_c"] == 375)).any()
    )
    if not has_pair:
        roles.discard("G5")
    return roles


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    design = pd.read_csv(FORMAL)
    required = {"G1", "G2", "G3", "G4", "G5"}
    base_roles = effective_roles(design)
    if base_roles != required:
        raise ValueError("正式设计未覆盖G1—G5")

    omission_rows = []
    for experiment_id in design["experiment_id"]:
        retained = design[design["experiment_id"] != experiment_id]
        roles = effective_roles(retained)
        omission_rows.append(
            {
                "omitted_experiment_id": experiment_id,
                "retained_experiment_count": len(retained),
                "retained_responsibility_codes": "|".join(sorted(roles)),
                "lost_responsibility_codes": "|".join(sorted(required - roles)),
                "all_five_responsibilities_retained": roles == required,
            }
        )
    omission = pd.DataFrame(omission_rows)
    omission_path = OUT / "leave_one_experiment_out.csv"
    omission.to_csv(omission_path, index=False)

    alternatives = pd.DataFrame(
        [
            {
                "policy": "A_formal_one_shot",
                "experiment_conditions": "A3@375|A3@425|A2@337.5|A3@400_repeat|A4@375",
                "responsibilities": "G1|G2|G3|G4|G5",
                "general_best_replicated": True,
                "strict_low_best_replicated": False,
                "new_same_temperature_competitor": True,
                "requires_feedback": False,
                "disposition": "formal",
            },
            {
                "policy": "B_conditional_three_plus_two",
                "experiment_conditions": "A3@375|A3@425|A2@337.5|conditional_run4|conditional_run5",
                "responsibilities": "G1|G2|G3|G4|G5_conditionally",
                "general_best_replicated": True,
                "strict_low_best_replicated": True,
                "new_same_temperature_competitor": True,
                "requires_feedback": True,
                "disposition": "conditional_alternative",
            },
            {
                "policy": "C_symmetric_replication",
                "experiment_conditions": "A3@375|A3@425|A2@337.5|A3@400_repeat|A2@325_repeat",
                "responsibilities": "G1|G2|G3|G4",
                "general_best_replicated": True,
                "strict_low_best_replicated": True,
                "new_same_temperature_competitor": False,
                "requires_feedback": False,
                "disposition": "rejected_loses_G5",
            },
        ]
    )
    alternatives_path = OUT / "policy_comparison.csv"
    alternatives.to_csv(alternatives_path, index=False)

    equipment = pd.DataFrame(
        [
            {
                "condition": "equipment_supports_337_5C",
                "formal_design_executable": True,
                "required_action": "execute_S8_design",
                "claim_boundary": "setpoint_support_does_not_prove_temperature_accuracy",
            },
            {
                "condition": "equipment_does_not_support_337_5C",
                "formal_design_executable": False,
                "required_action": "reopen_S8_and_choose_supported_interior_setpoint",
                "claim_boundary": "do_not_silently_round_or_claim_equal_bisection",
            },
            {
                "condition": "later_experiment_results_available_before_runs_4_5",
                "formal_design_executable": True,
                "required_action": "optionally_use_policy_B_branch_rules",
                "claim_boundary": "do_not_combine_A_and_B_as_seven_runs",
            },
            {
                "condition": "all_five_runs_must_be_scheduled_together",
                "formal_design_executable": True,
                "required_action": "use_policy_A",
                "claim_boundary": "no_adaptive_claim",
            },
        ]
    )
    equipment_path = OUT / "execution_boundary_checks.csv"
    equipment.to_csv(equipment_path, index=False)

    summary = {
        "schema_version": "1.0",
        "status": "q4_s11_structural_robustness_generated",
        "formal_responsibilities": sorted(base_roles),
        "leave_one_out": {
            "case_count": int(len(omission)),
            "cases_retaining_all_responsibilities": int(
                omission["all_five_responsibilities_retained"].sum()
            ),
            "interpretation": (
                "五次预算下每项实验都承担不可替代职责；删去任一项都会失去至少一项G职责"
            ),
        },
        "policy_result": {
            "formal": "A_formal_one_shot",
            "conditional": "B_conditional_three_plus_two",
            "rejected": "C_symmetric_replication",
            "reason_C_rejected": "失去A3/A4新增同温竞争G5",
        },
        "execution_gate": {
            "337_5C_requires_device_confirmation": True,
            "silent_rounding_allowed": False,
            "unsupported_setpoint_action": "reopen_S8",
        },
        "interpretation_boundaries": [
            "删一敏感说明职责紧凑，不证明所选温度数学唯一最优",
            "一次重复不能估计全域误差",
            "方案B的优势依赖真实反馈权限",
            "设备不支持337.5摄氏度时必须回退规格而非静默舍入",
            "未来观测无论高低都按预先更新规则解释",
        ],
        "generated_at": datetime.now().astimezone().isoformat(),
    }
    summary_path = OUT / "robustness_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    rows = []
    for path, role in [
        (FORMAL, "input"),
        (SCRIPT, "source"),
        (omission_path, "output"),
        (alternatives_path, "output"),
        (equipment_path, "output"),
        (summary_path, "output"),
    ]:
        rows.append(
            {
                "path": str(path.relative_to(ROOT)),
                "role": role,
                "sha256": sha256(path),
                "size_bytes": path.stat().st_size,
            }
        )
    pd.DataFrame(rows).to_csv(OUT / "artifact_manifest.csv", index=False)
    print("第四问S11结构稳健性生成完成")
    print(omission.to_string(index=False))


if __name__ == "__main__":
    main()
