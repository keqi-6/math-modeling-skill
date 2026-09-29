#!/usr/bin/env python3
"""Structural checks for the V5 skill."""

from __future__ import annotations

from pathlib import Path

from validate_v1_migration import validate as validate_v1_migration
from validate_version_deltas import validate as validate_version_deltas
from validate_internal_paths import validate as validate_internal_paths


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"
RULES = {
    "00-project-orchestration.md",
    "01-contest-project-pattern.md", "02-latex-setup.md",
    "03-paper-content-rules.md", "04-figure-generator.md",
    "05-audit-protocol.md", "06-weiwei-norms.md",
    "07-algorithm-reference.md", "08-literature-search.md",
    "09-robustness-checker.md", "10-json-handoff.md",
    "11-paper-finalizer.md", "12-source-audit-and-provenance.md",
    "13-excellent-paper-expression.md", "14-session-handoff.md",
    "15-pipeline-methodology.md", "16-data-audit-methodology.md",
    "17-reader-first-manuscript-audit.md", "18-execution-receipt.md",
    "19-project-lifecycle.md", "20-execution-gates.md",
    "21-global-manuscript-acceptance.md", "22-front-matter-acceptance.md",
    "23-background-analysis-acceptance.md", "24-assumptions-data-acceptance.md",
    "25-model-results-acceptance.md", "26-conclusion-references-acceptance.md",
    "27-visual-layout-acceptance.md", "28-evidence-acceptance.md",
    "29-governance-acceptance.md", "30-data-minimum.md",
    "31-modeling-minimum.md", "32-verification-minimum.md",
    "33-manuscript-minimum.md", "34-visuals-minimum.md",
    "35-provenance-delivery-minimum.md",
}


def main() -> None:
    errors: list[str] = []
    errors.extend(validate_v1_migration(ROOT))
    errors.extend(validate_version_deltas(ROOT))
    errors.extend(validate_internal_paths(ROOT))
    text = SKILL.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        errors.append("missing YAML frontmatter")
    for field in ["name:", "description:"]:
        if field not in text.split("---", 2)[1]:
            errors.append(f"missing frontmatter field {field}")
    if len(text.splitlines()) > 500:
        errors.append("SKILL.md exceeds 500 lines")
    for state in [
        "S0_RECOVER", "S1_INTERPRET", "S2_ASSESS", "S3_DECIDE",
        "S4_SPECIFY", "S5_IMPLEMENT", "S6_VERIFY", "S7_PUBLISH",
    ]:
        if state not in text:
            errors.append(f"missing state {state}")
    for phrase in [
        "implementation_allowed",
        "keep_current",
        "External-guidance boundary",
        "Silence",
        "full-read",
        "Recovery evidence contract",
        "recovery_manifest.json",
        "truncated: false",
        "`S0_RECOVER` is open",
        "V5 owns its detailed rules directly",
        "may strengthen quality within an allowed action",
        "stable-ID criteria and V4's concise cross-checks",
    ]:
        if phrase not in text:
            errors.append(f"missing controller guard: {phrase}")

    actual_rules = {path.name for path in (ROOT / "rules").glob("*.md")}
    if actual_rules != RULES:
        errors.append(
            f"rule set mismatch: expected={sorted(RULES)}, actual={sorted(actual_rules)}"
        )

    required = [
        ROOT / "references/migration-ledger.md",
        ROOT / "references/qualified-skill-standard.md",
        ROOT / "references/v1-integration-map.json",
        ROOT / "references/version-delta-map.json",
        ROOT / "scripts/validate_receipt.py",
        ROOT / "scripts/recovery_manifest.py",
        ROOT / "scripts/test_regressions.py",
        ROOT / "scripts/validate_v1_migration.py",
        ROOT / "scripts/test_v1_migration.py",
        ROOT / "scripts/validate_version_deltas.py",
        ROOT / "scripts/test_version_deltas.py",
        ROOT / "scripts/validate_internal_paths.py",
        ROOT / "scripts/test_internal_paths.py",
        ROOT / "scripts/forward_test_recovery.py",
        ROOT / "agents/openai.yaml",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    validator = (ROOT / "scripts/validate_receipt.py").read_text(encoding="utf-8")
    for phrase in [
        "GATES =", "verify_manifest", "manifest_sha256",
        "S0 mutation prohibition violated",
    ]:
        if phrase not in validator:
            errors.append(f"receipt validator missing recovery guard: {phrase}")

    tests = (ROOT / "scripts/test_regressions.py").read_text(encoding="utf-8")
    for case in [
        "custom_gate_value", "closed_without_evidence", "count_mismatch",
        "s0_mutation", "truncated_output", "unresolved_item", "stale_inventory",
    ]:
        if case not in tests:
            errors.append(f"missing recovery regression: {case}")

    delta_tests = (ROOT / "scripts/test_version_deltas.py").read_text(encoding="utf-8")
    for case in [
        "altered_v3_stable_id_acceptance", "missing_v4_quality_crosscheck",
        "semantic_only_downgrade", "unrouted_exact_delta",
    ]:
        if case not in delta_tests:
            errors.append(f"missing exact-delta regression: {case}")

    forward_test = (ROOT / "scripts/forward_test_recovery.py").read_text(encoding="utf-8")
    for phrase in ["--self-test", "build_fixture", "project_unchanged"]:
        if phrase not in forward_test:
            errors.append(f"forward-test interface missing: {phrase}")

    migration_validator = (
        ROOT / "scripts/validate_v1_migration.py"
    ).read_text(encoding="utf-8")
    for phrase in [
        "integrated active hash mismatch", "unmapped active V5 files",
        "active routing absent", "shadow V1 preservation directory",
    ]:
        if phrase not in migration_validator:
            errors.append(f"migration validator missing guard: {phrase}")

    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: V5 structure, recovery guards, controller precedence, and integrated detailed rules")


if __name__ == "__main__":
    main()
