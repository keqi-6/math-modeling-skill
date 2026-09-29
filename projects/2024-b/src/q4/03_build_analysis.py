#!/usr/bin/env python3
"""从问题四S5完整映射构造可解释的25/81/27情景层和论文摘要。"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import gzip
import hashlib
import json


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "output/q4"
REP = OUT / "s5_q3_representatives.jsonl.gz"
SUMMARY = OUT / "s5_q3_summary.json"
TARGET = OUT / "s5_q3_diagnostics.json"
MANIFEST = OUT / "s5_analysis_manifest.json"
SETTINGS = ("N200_n100", "N500_n20", "N500_n100", "N500_n200", "N1000_n100")
BIT_NAMES = ("iP1", "iP2", "iP3", "iP4", "iP5", "iP6", "iP7", "iP8", "iS1", "iS2", "iS3", "iF", "dS1", "dS2", "dS3", "dF")
RATE_NAMES = ("P1", "P2", "P3", "S1", "P4", "P5", "P6", "S2", "P7", "P8", "S3", "F")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def swap_policy(pid: str) -> str:
    bits = list(pid)
    for left, right in ((0, 3), (1, 4), (2, 5), (8, 9), (12, 13)):
        bits[left], bits[right] = bits[right], bits[left]
    return "".join(bits)


def optimal_bit_domains(ids: tuple[str, ...]) -> dict[str, str]:
    return {name: "".join(sorted({pid[index] for pid in ids})) for index, name in enumerate(BIT_NAMES)}


def target_codes() -> tuple[set[str], dict[str, list[str]]]:
    nominal = "1" * 12
    diagnostic = [nominal]
    for index in range(12):
        for level in "02":
            diagnostic.append(nominal[:index] + level + nominal[index + 1:])
    m1 = ["".join(bits) + "1" * 8 for bits in __import__("itertools").product("012", repeat=4)]
    m2 = ["1" * 4 + "".join(bits) + "1" * 4 for bits in __import__("itertools").product("012", repeat=4)]
    m3 = ["1" * 8 + "".join(bits) + "1" for bits in __import__("itertools").product("012", repeat=3)]
    groups = {"single_node_25": diagnostic, "M1_81": m1, "M2_81": m2, "M3_27": m3}
    return set().union(*map(set, groups.values())), groups


def main() -> int:
    wanted_codes, groups = target_codes()
    found: dict[tuple[str, str], dict[str, object]] = {}
    with gzip.open(REP, "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            setting = row["setting_id"]
            canonical = row["canonical_rate_code"]
            swapped = row["swapped_rate_code"]
            if canonical in wanted_codes:
                found[(setting, canonical)] = {
                    "best_policy_ids": tuple(row["best_policy_ids"]),
                    "best_cost": row["best_cost"],
                    "best_profit": row["best_profit"],
                }
            if swapped in wanted_codes:
                found[(setting, swapped)] = {
                    "best_policy_ids": tuple(row["swapped_best_policy_ids"]),
                    "best_cost": row["best_cost"],
                    "best_profit": row["best_profit"],
                }
    expected = {(setting, code) for setting in SETTINGS for code in wanted_codes}
    if set(found) != expected:
        raise AssertionError(f"diagnostic coverage missing={len(expected-set(found))}, extra={len(set(found)-expected)}")

    full_summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    result = {
        "status": "s5_interpretive_projection_from_complete_mapping",
        "rate_code_order": RATE_NAMES,
        "decision_bit_order": BIT_NAMES,
        "settings": {},
    }
    for setting in SETTINGS:
        nominal_ids = found[(setting, "1" * 12)]["best_policy_ids"]
        nominal_domains = optimal_bit_domains(nominal_ids)
        setting_result = {
            "nominal": {
                **found[(setting, "1" * 12)],
                "best_policy_ids": list(nominal_ids),
                "optimal_bit_domains": nominal_domains,
            },
            "layers": {},
            "full_domain": {
                "representative_scenario_count": full_summary["settings"][setting]["representative_scenario_count"],
                "expanded_labeled_scenario_count": full_summary["settings"][setting]["expanded_labeled_scenario_count"],
                "switch_scenario_count": full_summary["settings"][setting]["switch_scenario_count"],
                "best_profit_min": full_summary["settings"][setting]["best_profit_min"],
                "best_profit_max": full_summary["settings"][setting]["best_profit_max"],
                "distinct_optimal_policy_sets": len(full_summary["settings"][setting]["policy_set_counts"]),
                "most_frequent_optimal_policy_sets": sorted(
                    full_summary["settings"][setting]["policy_set_counts"].items(), key=lambda item: (-item[1], item[0])
                )[:10],
            },
        }
        for group_name, codes in groups.items():
            rows = []
            switch_count = 0
            changed_bits = Counter()
            for code in codes:
                current = found[(setting, code)]
                ids = current["best_policy_ids"]
                domains = optimal_bit_domains(ids)
                changed = [name for name in BIT_NAMES if domains[name] != nominal_domains[name]]
                switched = ids != nominal_ids
                switch_count += switched
                changed_bits.update(changed)
                rows.append({
                    "rate_code": code,
                    "best_policy_ids": list(ids),
                    "best_cost": current["best_cost"],
                    "best_profit": current["best_profit"],
                    "switched_from_nominal_set": switched,
                    "changed_optimal_bit_domains": changed,
                })
            setting_result["layers"][group_name] = {
                "scenario_count": len(codes),
                "switch_scenario_count": switch_count,
                "changed_bit_frequency": dict(sorted(changed_bits.items())),
                "rows": rows,
            }

        # S4冻结的M1实算/M2严格重标记合同。
        for m1_code in groups["M1_81"]:
            block = m1_code[:4]
            m2_code = "1111" + block + "1111"
            left = found[(setting, m1_code)]
            right = found[(setting, m2_code)]
            mapped = tuple(sorted(swap_policy(pid) for pid in left["best_policy_ids"]))
            if left["best_cost"] != right["best_cost"] or mapped != right["best_policy_ids"]:
                raise AssertionError(f"M1/M2 relabel:{setting}:{block}")
        setting_result["m1_m2_strict_relabel_check"] = "pass:81/81"
        result["settings"][setting] = setting_result

    TARGET.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    MANIFEST.write_text(json.dumps({
        "command": "python3 src/q4/03_build_analysis.py",
        "inputs_sha256": {path.relative_to(ROOT).as_posix(): sha256(path) for path in (REP, SUMMARY)},
        "source_sha256": sha256(Path(__file__)),
        "output_sha256": sha256(TARGET),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "unique_target_codes_per_setting": len(wanted_codes)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
