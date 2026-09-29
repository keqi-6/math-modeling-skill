"""独立复核问题一 N=1000 不同质量状态下的精确平均检测量。"""

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
THRESHOLD_PATH = PROJECT_ROOT / "output/q1/s5_large_batch_extension.json"
EVALUATION_PATH = PROJECT_ROOT / "output/q1/s7_quality_state_evaluation.json"
OUTPUT_PATH = PROJECT_ROOT / "output/q1/s7_quality_state_verification.json"
MANIFEST_PATH = PROJECT_ROOT / "output/q1/s7_quality_state_verification_manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def as_fraction(payload: dict[str, object]) -> Fraction:
    return Fraction(int(payload["numerator"]), int(payload["denominator"]))


def independent_flow(n: int, d: int, scenario: str, thresholds: tuple[int, ...]) -> tuple[Fraction, Fraction, Fraction, Fraction]:
    """独立实现的状态概率流；不导入主评价脚本或 q1 核心。"""

    d0, d1 = n // 10, n // 10 + 1
    current = {0: Fraction(1)}
    p_accept = Fraction(0)
    p_reject = Fraction(0)
    expected = Fraction(0)
    for inspected in range(n):
        following: dict[int, Fraction] = {}
        for defects, probability in current.items():
            if 0 < inspected < n:
                fact_accept = defects + n - inspected <= d0
                fact_reject = defects >= d1
                statistical = (
                    defects >= thresholds[inspected - 1]
                    if scenario == "R"
                    else defects <= thresholds[inspected - 1]
                )
                if fact_accept or fact_reject or statistical:
                    expected += inspected * probability
                    if fact_accept or (scenario == "A" and not fact_reject and statistical):
                        p_accept += probability
                    else:
                        p_reject += probability
                    continue

            defect_numerator = d - defects
            good_numerator = n - d - inspected + defects
            denominator = n - inspected
            if defect_numerator:
                following[defects + 1] = following.get(defects + 1, Fraction(0)) + probability * Fraction(defect_numerator, denominator)
            if good_numerator:
                following[defects] = following.get(defects, Fraction(0)) + probability * Fraction(good_numerator, denominator)
        current = following

    p_terminal = sum(current.values(), Fraction(0))
    expected += n * p_terminal
    if p_accept + p_reject + p_terminal != 1:
        raise AssertionError(f"独立概率质量不守恒: D={d}, scenario={scenario}")
    return p_accept, p_reject, p_terminal, expected


def main() -> None:
    started_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    thresholds_payload = json.loads(THRESHOLD_PATH.read_text(encoding="utf-8"))
    evaluation = json.loads(EVALUATION_PATH.read_text(encoding="utf-8"))
    frozen = next(row for row in thresholds_payload["results"] if int(row["N"]) == int(evaluation["N"]))
    n = int(evaluation["N"])
    checks: list[str] = []
    records = []

    for scenario in ("R", "A"):
        thresholds = tuple(int(row["threshold"]) for row in frozen["scenarios"][scenario]["thresholds"])
        points = evaluation["scenarios"][scenario]["points"]
        for point in points:
            d = int(point["D"])
            p_accept, p_reject, p_terminal, expected = independent_flow(n, d, scenario, thresholds)
            comparisons = {
                "accept_probability": p_accept == as_fraction(point["accept_probability"]),
                "reject_probability": p_reject == as_fraction(point["reject_probability"]),
                "terminal_probability": p_terminal == as_fraction(point["terminal_probability"]),
                "average_inspected_items": expected == as_fraction(point["average_inspected_items"]),
                "ratio_identity": expected / n == as_fraction(point["average_inspection_ratio"]),
                "mass_conservation": p_accept + p_reject + p_terminal == 1,
            }
            if not all(comparisons.values()):
                raise AssertionError(f"独立复核不一致: scenario={scenario},D={d},{comparisons}")
            checks.extend(f"{scenario}:D={d}:{name}" for name in comparisons)
            records.append({"scenario": scenario, "D": d, "checks": comparisons})

        endpoint_zero = next(point for point in points if int(point["D"]) == 0)
        endpoint_full = next(point for point in points if int(point["D"]) == n)
        if not (as_fraction(endpoint_zero["terminal_probability"]) == 0 and as_fraction(endpoint_full["terminal_probability"]) == 0):
            raise AssertionError(f"端点批次应确定性提前停止: scenario={scenario}")
        checks.extend([f"{scenario}:D=0:deterministic_early_stop", f"{scenario}:D={n}:deterministic_early_stop"])

    result = {
        "schema_version": "1.0",
        "artifact_status": "s7_independent_exact_quality_state_verification",
        "producer": "src/q1/10_verify_quality_state_evaluation.py",
        "independence_boundary": "does not import src/q1/core.py or src/q1/09_quality_state_evaluation.py",
        "input_identities": {
            str(THRESHOLD_PATH.relative_to(PROJECT_ROOT)): sha256(THRESHOLD_PATH),
            str(EVALUATION_PATH.relative_to(PROJECT_ROOT)): sha256(EVALUATION_PATH),
        },
        "check_count": len(checks),
        "all_checks_passed": True,
        "checks": checks,
        "records": records,
        "claim_boundary": "confirms exact plotted expectations and probability identities; does not claim the frozen N=1000 thresholds are globally optimal",
    }
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    finished_at = datetime.now(ZoneInfo("Asia/Shanghai"))
    manifest = {
        "schema_version": "1.0",
        "artifact_status": "s7_verification_run_identity",
        "producer": "src/q1/10_verify_quality_state_evaluation.py",
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "command": [sys.executable, str(SCRIPT_PATH.relative_to(PROJECT_ROOT)), *sys.argv[1:]],
        "environment": {"python": sys.version, "platform": platform.platform(), "random_seed": None},
        "inputs": {
            str(THRESHOLD_PATH.relative_to(PROJECT_ROOT)): sha256(THRESHOLD_PATH),
            str(EVALUATION_PATH.relative_to(PROJECT_ROOT)): sha256(EVALUATION_PATH),
            str(SCRIPT_PATH.relative_to(PROJECT_ROOT)): sha256(SCRIPT_PATH),
        },
        "outputs": {str(OUTPUT_PATH.relative_to(PROJECT_ROOT)): sha256(OUTPUT_PATH)},
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "checks": len(checks), "output": str(OUTPUT_PATH)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
