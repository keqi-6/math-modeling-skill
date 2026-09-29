#!/usr/bin/env python3
"""独立复核第四问S11结构稳健性产物；不导入S11实现。"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FORMAL = ROOT / "output" / "q4" / "formal" / "experiment_design.csv"
OUT = ROOT / "output" / "q4" / "robustness"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    design = read_csv(FORMAL)
    omission = read_csv(OUT / "leave_one_experiment_out.csv")
    policies = read_csv(OUT / "policy_comparison.csv")
    boundaries = read_csv(OUT / "execution_boundary_checks.csv")
    summary = json.loads((OUT / "robustness_summary.json").read_text(encoding="utf-8"))
    manifest = read_csv(OUT / "artifact_manifest.csv")
    checks = []

    expected_loss = {
        "E1": {"G2", "G5"},
        "E2": {"G3"},
        "E3": {"G4"},
        "E4": {"G1"},
        "E5": {"G5"},
    }
    actual_loss = {
        row["omitted_experiment_id"]:
        set(row["lost_responsibility_codes"].split("|"))
        for row in omission
    }
    checks.append(("five_omission_cases", len(design) == len(omission) == 5))
    checks.append(("independent_loss_pattern", actual_loss == expected_loss))
    checks.append((
        "no_omission_retains_all_roles",
        all(row["all_five_responsibilities_retained"] == "False" for row in omission),
    ))
    policy_map = {row["policy"]: row for row in policies}
    checks.append((
        "formal_policy_retains_G1_G5",
        policy_map["A_formal_one_shot"]["responsibilities"] == "G1|G2|G3|G4|G5",
    ))
    checks.append((
        "symmetric_policy_loses_competitor",
        policy_map["C_symmetric_replication"]["new_same_temperature_competitor"]
        == "False",
    ))
    boundary_map = {row["condition"]: row for row in boundaries}
    checks.append((
        "unsupported_337_5_reopens_spec",
        boundary_map["equipment_does_not_support_337_5C"]["required_action"]
        == "reopen_S8_and_choose_supported_interior_setpoint",
    ))
    checks.append((
        "batch_execution_uses_A",
        boundary_map["all_five_runs_must_be_scheduled_together"]["required_action"]
        == "use_policy_A",
    ))
    checks.append((
        "summary_matches",
        summary["leave_one_out"]["cases_retaining_all_responsibilities"] == 0
        and summary["execution_gate"]["silent_rounding_allowed"] is False,
    ))
    checks.append((
        "manifest_hashes",
        all(
            (ROOT / row["path"]).exists()
            and sha256(ROOT / row["path"]) == row["sha256"]
            and (ROOT / row["path"]).stat().st_size == int(row["size_bytes"])
            for row in manifest
        ),
    ))
    failed = [name for name, passed in checks if not passed]
    result = {
        "schema_version": "1.0",
        "status": "q4_s11_independent_verification_passed" if not failed else "failed",
        "independent_of_s11_import": True,
        "verification_count": len(checks),
        "passed_count": len(checks) - len(failed),
        "all_passed": not failed,
        "checks": [{"name": name, "passed": passed} for name, passed in checks],
    }
    (OUT / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if failed:
        raise AssertionError(f"S11验证失败：{failed}")
    print(f"第四问S11独立验证：{len(checks)}/{len(checks)}通过")


if __name__ == "__main__":
    main()
