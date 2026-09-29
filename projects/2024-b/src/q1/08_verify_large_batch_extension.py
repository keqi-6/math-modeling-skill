"""独立复核问题一大批量阈值候选；不导入主求解核心或扩展求解脚本。"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = Path(__file__).resolve()
INPUT_PATH = PROJECT_ROOT / "output/q1/s5_large_batch_extension.json"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/s6_large_batch_verification.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s6_large_batch_verification_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def from_payload(payload: dict[str, object]) -> Fraction:
    return Fraction(int(payload["numerator"]), int(payload["denominator"]))


def evaluate(
    n: int,
    d: int,
    scenario: str,
    thresholds: tuple[int, ...],
) -> dict[str, Fraction]:
    d0, d1 = n // 10, n // 10 + 1
    alive: dict[int, Fraction] = {0: Fraction(1)}
    accepted = Fraction(0)
    rejected = Fraction(0)
    early_asn = Fraction(0)
    for t in range(n):
        next_alive: dict[int, Fraction] = {}
        for x, mass in alive.items():
            action = 0
            if 1 <= t < n:
                if x + (n - t) <= d0:
                    action = 1
                elif x >= d1:
                    action = 2
                elif scenario == "R" and x >= thresholds[t - 1]:
                    action = 2
                elif scenario == "A" and x <= thresholds[t - 1]:
                    action = 1
            if action:
                early_asn += t * mass
                if action == 1:
                    accepted += mass
                else:
                    rejected += mass
                continue
            defect = Fraction(d - x, n - t)
            good = Fraction(n - d - t + x, n - t)
            if defect < 0 or good < 0 or defect + good != 1:
                raise AssertionError("独立递推遇到不可达正质量状态")
            if defect:
                next_alive[x + 1] = next_alive.get(x + 1, Fraction(0)) + mass * defect
            if good:
                next_alive[x] = next_alive.get(x, Fraction(0)) + mass * good
        alive = next_alive
    terminal = sum(alive.values(), Fraction(0))
    if accepted + rejected + terminal != 1:
        raise AssertionError("独立递推质量不守恒")
    return {"accepted": accepted, "rejected": rejected, "asn": early_asn + n * terminal, "terminal": terminal}


def validate_threshold_domain(n: int, scenario: str, thresholds: tuple[int, ...]) -> None:
    if len(thresholds) != n - 1:
        raise AssertionError("阈值长度不是N-1")
    d0 = n // 10
    for t, threshold in enumerate(thresholds, start=1):
        if scenario == "R":
            if threshold != t + 1 and not 0 <= threshold <= min(t, d0):
                raise AssertionError(f"R阈值越域: N={n},t={t}")
        elif threshold != -1 and not max(0, t - (n - d0) + 1) <= threshold <= min(t, d0):
            raise AssertionError(f"A阈值越域: N={n},t={t}")


def main() -> None:
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    payload = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    records = []
    checks = []
    for result in payload["results"]:
        n = int(result["N"])
        d0, d1 = n // 10, n // 10 + 1
        for scenario in ("R", "A"):
            frozen = result["scenarios"][scenario]
            thresholds = tuple(int(row["threshold"]) for row in frozen["thresholds"])
            validate_threshold_domain(n, scenario, thresholds)
            null_d, target_d = (d0, d1) if scenario == "R" else (d1, d0)
            risk_limit = Fraction(1, 20) if scenario == "R" else Fraction(1, 10)
            null = evaluate(n, null_d, scenario, thresholds)
            target = evaluate(n, target_d, scenario, thresholds)
            risk = null["rejected"] if scenario == "R" else null["accepted"]
            frozen_risk = from_payload(frozen["risk_at_composite_worst_point"])
            frozen_asn = from_payload(frozen["worst_target_ASN_upper_bound"])
            local_checks = {
                "threshold_domain": True,
                "null_mass_conservation": null["accepted"] + null["rejected"] + null["terminal"] == 1,
                "target_mass_conservation": target["accepted"] + target["rejected"] + target["terminal"] == 1,
                "risk_matches_frozen_exactly": risk == frozen_risk,
                "asn_matches_frozen_exactly": target["asn"] == frozen_asn,
                "risk_limit_satisfied": risk <= risk_limit,
                "ratio_identity": from_payload(frozen["average_inspection_ratio"]) == frozen_asn / n,
            }
            if not all(local_checks.values()):
                raise AssertionError(f"独立验证失败: N={n},scenario={scenario},{local_checks}")
            checks.extend(f"N={n}:{scenario}:{name}" for name in local_checks)
            records.append(
                {
                    "N": n,
                    "scenario": scenario,
                    "risk_numerator": risk.numerator,
                    "risk_denominator": risk.denominator,
                    "asn_numerator": target["asn"].numerator,
                    "asn_denominator": target["asn"].denominator,
                    "checks": local_checks,
                }
            )

    result = {
        "schema_version": "1.0",
        "artifact_status": "s6_independent_numerical_verification",
        "producer": "src/q1/08_verify_large_batch_extension.py",
        "input_path": str(INPUT_PATH.relative_to(PROJECT_ROOT)),
        "input_sha256": sha256(INPUT_PATH),
        "independence_boundary": "does not import src/q1/core.py or src/q1/07_large_batch_extension.py",
        "check_count": len(checks),
        "all_checks_passed": True,
        "checks": checks,
        "records": records,
        "claim_boundary": "verifies exact feasibility and frozen metrics, not global optimality of projected thresholds",
    }
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s6_verification_run_identity",
        "producer": "src/q1/08_verify_large_batch_extension.py",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT)), *sys.argv[1:]],
        "environment": {"python": sys.version, "platform": platform.platform(), "random_seed": None},
        "inputs": {
            str(INPUT_PATH.relative_to(PROJECT_ROOT)): sha256(INPUT_PATH),
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
        },
        "outputs": {str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH)},
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "checks": len(checks), "output": str(OUTPUT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
