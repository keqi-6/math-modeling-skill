#!/usr/bin/env python3
"""Validate the V2–V4 additions integrated into V5."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

EXACT_ACTIVE_DELTAS = {
    "skills_v3/rules/10-global-manuscript-rules.md": "rules/21-global-manuscript-acceptance.md",
    "skills_v3/rules/20-front-matter.md": "rules/22-front-matter-acceptance.md",
    "skills_v3/rules/21-background-restatement-analysis.md": "rules/23-background-analysis-acceptance.md",
    "skills_v3/rules/22-assumptions-symbols-data.md": "rules/24-assumptions-data-acceptance.md",
    "skills_v3/rules/23-model-solution-results.md": "rules/25-model-results-acceptance.md",
    "skills_v3/rules/24-evaluation-conclusion-references.md": "rules/26-conclusion-references-acceptance.md",
    "skills_v3/rules/30-figures-tables-layout.md": "rules/27-visual-layout-acceptance.md",
    "skills_v3/rules/40-evidence-provenance.md": "rules/28-evidence-acceptance.md",
    "skills_v3/rules/50-governance-handoff.md": "rules/29-governance-acceptance.md",
    "skills_v4/rules/data.md": "rules/30-data-minimum.md",
    "skills_v4/rules/modeling.md": "rules/31-modeling-minimum.md",
    "skills_v4/rules/verification.md": "rules/32-verification-minimum.md",
    "skills_v4/rules/manuscript.md": "rules/33-manuscript-minimum.md",
    "skills_v4/rules/visuals-layout.md": "rules/34-visuals-minimum.md",
    "skills_v4/rules/provenance-delivery.md": "rules/35-provenance-delivery-minimum.md",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(root: Path = ROOT, history_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    map_path = root / "references/version-delta-map.json"
    try:
        payload = json.loads(map_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read version delta map: {exc}"]
    if payload.get("schema_version") != "1.0":
        errors.append("unsupported version-delta schema")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return errors + ["version delta entries must be a list"]
    seen: set[tuple[str, str]] = set()
    versions: set[str] = set()
    skill_text = (root / "SKILL.md").read_text(encoding="utf-8")
    tests = (root / "scripts/test_regressions.py").read_text(encoding="utf-8")
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"delta entry {index} is not an object")
            continue
        required = {
            "introduced_in", "source", "source_sha256",
            "owner", "treatment", "route", "reason",
        }
        missing = sorted(required - entry.keys())
        if missing:
            errors.append(f"delta entry {index} missing fields: {missing}")
            continue
        key = (entry["introduced_in"], entry["source"])
        if key in seen:
            errors.append(f"duplicate version delta: {key}")
        seen.add(key)
        versions.add(entry["introduced_in"])
        owner = root / entry["owner"]
        if not owner.is_file():
            errors.append(f"{entry['source']}: integrated delta owner missing")
        active_hash = entry.get("active_sha256")
        if active_hash and owner.is_file() and sha256(owner) != active_hash:
            errors.append(f"{entry['source']}: integrated delta hash mismatch")
        if entry["owner"] != "SKILL.md" and entry["owner"] not in skill_text:
            errors.append(f"{entry['source']}: delta owner not routed in SKILL.md")
        if not isinstance(entry["reason"], str) or not entry["reason"].strip():
            errors.append(f"{entry['source']}: delta treatment has no reason")
        exact_owner = EXACT_ACTIVE_DELTAS.get(entry["source"])
        if exact_owner is not None:
            if entry["owner"] != exact_owner:
                errors.append(f"{entry['source']}: exact active owner changed")
            if entry["treatment"] not in {
                "exact_active_acceptance", "exact_active_crosscheck",
            }:
                errors.append(f"{entry['source']}: exact integration was downgraded")
            if active_hash != entry["source_sha256"]:
                errors.append(f"{entry['source']}: active hash must equal historical hash")
        if history_root is not None:
            source = history_root / entry["source"]
            if not source.is_file():
                errors.append(f"{entry['source']}: historical source missing")
            elif sha256(source) != entry["source_sha256"]:
                errors.append(f"{entry['source']}: historical source hash mismatch")
    if versions != {"V2", "V3", "V4"}:
        errors.append(f"delta map must cover V2, V3, and V4; found {sorted(versions)}")
    expected = {
        "skills_v2/source-portfolios/17-reader-first-manuscript-audit.md",
        "skills_v2/source-portfolios/03-paper-content-rules.md",
        "skills_v2/source-portfolios/05-audit-protocol.md",
        "skills_v2/source-portfolios/02-latex-setup.md",
        "skills_v2/scripts/bootstrap_project.py",
        *{f"skills_v3/rules/{name}" for name in [
            "00-execution-gates.md", "01-execution-receipt.md",
            "05-project-lifecycle.md", "10-global-manuscript-rules.md",
            "20-front-matter.md", "21-background-restatement-analysis.md",
            "22-assumptions-symbols-data.md", "23-model-solution-results.md",
            "24-evaluation-conclusion-references.md",
            "30-figures-tables-layout.md", "40-evidence-provenance.md",
            "50-governance-handoff.md", "rule-ownership-map.md",
        ]},
        "skills_v4/SKILL.md", "skills_v4/agents/openai.yaml",
        "skills_v4/references/migration-ledger.md",
        *{f"skills_v4/rules/{name}.md" for name in [
            "data", "modeling", "verification", "manuscript",
            "visuals-layout", "provenance-delivery",
        ]},
        *{f"skills_v4/scripts/{name}.py" for name in [
            "validate_receipt", "validate_skill", "test_regressions",
        ]},
    }
    mapped = {entry["source"] for entry in entries if isinstance(entry, dict)}
    missing_deltas = sorted(expected - mapped)
    if missing_deltas:
        errors.append(f"unadjudicated V2-V4 deltas: {missing_deltas}")
    missing_exact = sorted(set(EXACT_ACTIVE_DELTAS) - mapped)
    if missing_exact:
        errors.append(f"missing exact active deltas: {missing_exact}")
    for guard in [
        "S0_RECOVER", "implementation_allowed", "keep_current",
        "External-guidance boundary", "full_read_gate",
    ]:
        if guard not in skill_text:
            errors.append(f"V4 controller guard missing from V5: {guard}")
    for regression in [
        "rubric_to_model_jump", "continue_is_not_approval",
        "verified_candidate_not_auto_promoted",
    ]:
        if regression not in tests:
            errors.append(f"V4 behavioral regression missing: {regression}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--history-root", type=Path,
        help="Optional directory containing skills_v2, skills_v3, and skills_v4.",
    )
    args = parser.parse_args()
    errors = validate(history_root=args.history_root)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: V2 reader gates, V3 execution gates, and V4 controller deltas are integrated")


if __name__ == "__main__":
    main()
