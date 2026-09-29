#!/usr/bin/env python3
"""Build or check the manually reviewed V9-clause to V15-atom seal.

The review tables below are the semantic decision.  The generated artifact is
derived, but a changed rule cannot be re-sealed until both REVIEW and
EXPECTED_REVIEW_PROJECTION_SHA256 are explicitly updated.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from build_migration_coverage import canonical_sha256, semantic_atom_contract
from lib_v10 import SKILL_ROOT, dump_json, load_json, load_rules, sha256_file, sha256_text


REVIEW = {
    "decision_id": "V16-CLAUSE-REVIEW-002",
    "release": "V16.0.0-candidate",
    "previous_decision_id": "V16-CLAUSE-REVIEW-001",
    "rationale": (
        "Review and re-seal the user-approved V16 recovery-tier redesign after the prior "
        "teammate-solution-brief correction: R0 requires proven same-window continuity, R1 "
        "requires a trusted complete baseline plus attributable changes and a provable full "
        "consumer closure, and every remaining or explicitly requested case enters R2 with "
        "whole-project per-object reading. The redesign separates recovery read scope from "
        "ChangeSet invalidation, preserves one episode and receipt across R1-to-R2 escalation, "
        "and does not authorize solver execution, recomputation, manuscript promotion, or "
        "per-edit checkpointing."
    ),
}

# Set only after inspecting the complete review projection printed by --proposal.
EXPECTED_REVIEW_PROJECTION_SHA256 = "051498be47c0941d553431a4d21601cf5f1f09a59155fbef49b24d28ff2220d0"


PRESERVATION_REVIEW_SOURCES = (
    ("references/preservation/v1-v14-audit.md", "reviewed_disposition_overview"),
    ("references/preservation/audit-v1-v5.md", "v1_v5_rule_text_audit"),
    ("references/preservation/audit-v6-v10.md", "v6_v10_rule_text_audit"),
    ("references/preservation/audit-v11-v14.md", "v11_v14_runtime_and_release_audit"),
    (
        "references/preservation/v15-real-project-backfill-and-state-repair.md",
        "v15_bounded_backfill_and_state_repair",
    ),
    (
        "references/preservation/real-project-2025-a-rule-extraction.md",
        "real_project_rule_extraction",
    ),
    (
        "references/preservation/v16-real-project-2024-b-teammate-brief.md",
        "v16_teammate_brief_format_timing_and_location_extraction",
    ),
    (
        "references/preservation/v16-real-project-2025-a-live-window-rule-extraction.md",
        "v16_live_cross_window_teammate_and_propagation_rule_extraction",
    ),
    (
        "references/preservation/v16-recovery-tier-redesign.md",
        "v16_user_approved_recovery_tier_redesign",
    ),
)


def review_source_inventory(root: Path) -> list[dict[str, str]]:
    sources = []
    for relative, role in PRESERVATION_REVIEW_SOURCES:
        path = root / relative
        if not path.is_file():
            raise ValueError(f"preservation review source missing: {relative}")
        sources.append({"path": relative, "role": role, "sha256": sha256_file(path)})
    return sources


def reviewed_defects(root: Path) -> list[dict[str, Any]]:
    rows = []
    for defect_id in sorted(DEFECTS):
        source_bindings = []
        for relative in DEFECTS[defect_id].get("source_refs", []):
            path = root / relative
            if not path.is_file():
                raise ValueError(f"{defect_id}: preservation source missing: {relative}")
            source_bindings.append({"path": relative, "sha256": sha256_file(path)})
        if not source_bindings:
            raise ValueError(f"{defect_id}: preservation source binding missing")
        row = {key: value for key, value in DEFECTS[defect_id].items() if key != "source_refs"}
        rows.append({"id": defect_id, **row, "source_bindings": source_bindings})
    return rows


def _c(**fields: dict[str, str]) -> dict[str, dict[str, str]]:
    return fields


# Each item is an independently decidable normalized clause.  The exact frozen
# V9 field is separately hash-bound in the artifact; these labels do not replace
# the source text.
SOURCE_CLAUSES: dict[str, dict[str, dict[str, str]]] = {
    "GOV-MODE-001": _c(
        trigger={"request": "for every request"},
        expected={"mode_before_route": "select one execution mode before routing"},
        forbidden={
            "silence_write": "do not infer write permission from silence",
            "readonly_write": "do not infer write permission from a read-only request",
        },
    ),
    "GOV-AUTH-001": _c(
        trigger={"action": "for every action"},
        expected={
            "authorization": "keep authorization as its own decision dimension",
            "epistemic_truth": "keep epistemic truth as its own decision dimension",
            "project_choice": "keep project choice as its own decision dimension",
            "state": "keep component state as its own decision dimension",
            "procedure": "keep domain procedure as its own decision dimension",
        },
        forbidden={"total_priority": "do not resolve different authority dimensions with one total priority list"},
    ),
    "GOV-ROUTE-001": _c(
        trigger={"substantive_execution": "before substantive execution"},
        expected={
            "mode": "validate execution mode against the route contract",
            "object": "validate operation object against the route contract",
            "action": "validate user action against the route contract",
            "state": "validate current state against the route contract",
        },
        forbidden={
            "catchall": "do not use a catchall as proof of routing",
            "legacy_link": "do not use a transitive legacy link as proof of routing",
        },
    ),
    "GOV-OWNER-001": _c(
        trigger={
            "interpretation": "during rule interpretation",
            "maintenance": "during rule maintenance",
        },
        expected={"canonical_owner": "one canonical owner per semantic capability"},
        forbidden={"duplicate_owner": "do not duplicate normative ownership"},
    ),
    "GOV-RECEIPT-001": _c(
        trigger={"receipt": "for a structured execution receipt"},
        expected={
            "discriminated_contract": "use the discriminated V9 receipt contract",
            "route_consistency": "keep receipt modules route-consistent",
        },
        forbidden={"second_schema": "do not invent a second receipt schema"},
    ),
    "GOV-DECISION-001": _c(
        trigger={
            "design": "for a design decision",
            "frozen_change": "for a frozen-decision change",
        },
        expected={"closed_classification": "classify new_design, change_existing, or not_applicable"},
        forbidden={"greenfield_keep": "do not force greenfield work into keep_current"},
    ),
    "STATE-TYPED-001": _c(
        trigger={"read": "on project state read", "write": "on project state write"},
        expected={
            "question": "track question components with type-specific states",
            "shared_data": "track shared_data components with type-specific states",
            "artifact": "track artifact components with type-specific states",
            "project": "track project components with type-specific states",
        },
        forbidden={"one_stage": "do not treat one current_stage as project-wide authority"},
    ),
    "REC-R0-001": _c(
        trigger={
            "consistent_state": "state is consistent",
            "consistent_artifacts": "registered artifacts are consistent",
        },
        expected={
            "direct_state": "continue from direct authoritative state",
            "declared_inputs": "continue from declared inputs",
            "no_full_reread": "continue without a full reread",
        },
        forbidden={"ordinary_manifest": "do not create a recovery manifest for ordinary continuation"},
    ),
    "REC-R1-001": _c(
        trigger={"localizable_change": "changes are localizable"},
        expected={
            "affected_components": "review affected components",
            "consumers": "review affected consumers",
        },
        forbidden={"causeless_full_read": "do not escalate a local change to full-project reading without cause"},
    ),
    "REC-R2-001": _c(
        trigger={
            "invalid_state": "state is invalid",
            "identity_conflict": "an identity conflict exists",
            "unlocalizable_change": "a change cannot be localized",
            "explicit_full": "the user explicitly requests full recovery",
            "closure": "a closure requires global proof",
        },
        expected={"complete_evidence": "reconstruct complete evidence coverage"},
        forbidden={"narrative_only": "do not claim recovery from a narrative summary alone"},
    ),
    "ART-LAZY-001": _c(
        trigger={"before_creation": "before file creation"},
        expected={
            "consumer": "require a real consumer",
            "purpose": "require a purpose",
            "lifecycle": "require a lifecycle",
            "class": "require an artifact class",
            "authorization": "require an authorization basis",
        },
        forbidden={
            "placeholder": "do not create placeholder artifacts",
            "speculative_directory": "do not create speculative directories",
        },
    ),
    "ART-PROMOTE-001": _c(
        trigger={
            "temporary": "when promoting a temporary artifact",
            "working": "when promoting a working artifact",
        },
        expected={
            "validate": "validate the artifact",
            "registry": "update the state registry",
        },
        forbidden={"scratch": "do not promote unvalidated scratch output"},
    ),
    "PRJ-SCOPE-001": _c(
        trigger={"new_project": "for a new project", "scope_change": "for a scope change"},
        expected={
            "questions": "identify project questions",
            "shared_evidence": "identify shared evidence",
            "deliverables": "identify deliverables",
            "boundaries": "identify project boundaries",
        },
        forbidden={"unsupported_tasks": "do not invent unsupported tasks"},
    ),
    "PRJ-STRUCTURE-001": _c(
        trigger={"authorized_init": "during authorized project initialization"},
        expected={"consumed_structure": "materialize only immediately consumed structure"},
        forbidden={"legacy_scaffold": "do not eagerly create the full legacy scaffold"},
    ),
    "PRJ-PLAN-001": _c(
        trigger={"comprehensive_plan": "during comprehensive project planning"},
        expected={
            "work_packages": "link work packages",
            "dependencies": "link dependencies",
            "evidence": "link expected evidence",
            "deliverables": "link deliverables",
        },
        forbidden={
            "state_override": "do not let orchestration detail override the state contract",
            "recovery_override": "do not let orchestration detail override the recovery contract",
        },
    ),
    "EVD-LITERATURE-001": _c(
        trigger={
            "literature": "literature evidence is needed",
            "external_fact": "external factual evidence is needed",
        },
        expected={
            "authoritative_search": "search authoritative sources",
            "claim_use": "record claim-level source use",
        },
        forbidden={
            "snippet_primary": "do not treat search snippets as primary evidence",
            "ai_primary": "do not treat AI answers as primary evidence",
        },
    ),
    "EVD-PROVENANCE-001": _c(
        trigger={
            "external_data": "external data is used",
            "external_fact": "external facts are used",
            "external_figure": "external figures are used",
            "external_reference": "external references are used",
        },
        expected={
            "source": "record source identity",
            "license": "record license or terms",
            "identity": "record material identity",
            "claim_link": "record claim linkage",
        },
        forbidden={"abstract_fulltext": "do not claim full-text review when only an abstract was read"},
    ),
    "DATA-IDENTITY-001": _c(
        trigger={"any_use": "before any data use"},
        expected={
            "source": "establish data source",
            "schema": "establish data schema",
            "units": "establish units",
            "time_scope": "establish time scope",
            "space_scope": "establish space scope",
            "raw_identity": "establish immutable raw identity",
        },
        forbidden={"overwrite_raw": "do not silently overwrite raw data"},
    ),
    "DATA-AUDIT-001": _c(
        trigger={"d0": "at D0", "quality_question": "for a data-quality question"},
        expected={
            "completeness": "audit completeness",
            "validity": "audit validity",
            "duplicates": "audit duplicates",
            "missingness": "audit missingness",
            "outliers": "audit outliers",
            "semantic_consistency": "audit semantic consistency",
        },
        forbidden={"clean_before_evidence": "do not clean before documenting audit evidence"},
    ),
    "DATA-TREAT-001": _c(
        trigger={"d1_findings": "D1 findings require treatment"},
        expected={
            "decision": "decide the treatment",
            "justification": "justify the treatment",
            "alternatives": "assess sensitivity to treatment alternatives",
        },
        forbidden={"irreversible_without_decision": "do not apply irreversible treatment without a decision"},
    ),
    "DATA-FREEZE-001": _c(
        trigger={"d3_promotion": "on promotion to D3"},
        expected={
            "processed_identity": "freeze processed-data identity",
            "lineage": "freeze transformation lineage",
            "consumer_contract": "freeze the consumer contract",
        },
        forbidden={"change_without_invalidation": "do not change frozen data without invalidating consumers"},
    ),
    "MOD-RESTATE-001": _c(
        trigger={"model_design": "during model design"},
        expected={
            "objects": "translate the question into model objects",
            "variables": "translate the question into variables",
            "constraints": "translate the question into constraints",
            "objectives": "translate the question into objectives",
            "outputs": "translate the question into required outputs",
        },
        forbidden={"algorithm_first": "do not choose an algorithm before defining the mathematical problem"},
    ),
    "MOD-COMPARE-001": _c(
        trigger={"s2_s3": "during S2 to S3"},
        expected={
            "viable_candidates": "compare viable candidate models",
            "explicit_criteria": "use explicit comparison criteria",
        },
        forbidden={"single_method": "do not call one unexamined method a comparison"},
    ),
    "MOD-SPEC-001": _c(
        trigger={"s3_s4": "during S3 to S4"},
        expected={
            "assumptions": "freeze assumptions",
            "symbols": "freeze symbols",
            "equations": "freeze equations",
            "parameters": "freeze parameters",
            "units": "freeze units",
            "interfaces": "freeze interfaces",
        },
        forbidden={"ambiguous_implementation": "do not implement an ambiguous specification"},
    ),
    "MOD-IMPLEMENT-001": _c(
        trigger={"s4_s5": "during S4 to S5"},
        expected={
            "reproducible": "implement reproducibly",
            "deterministic_inputs": "use deterministic inputs or a declared stochastic contract",
            "inspectable_outputs": "produce inspectable outputs",
        },
        forbidden={"code_as_spec": "do not substitute code structure for model specification"},
    ),
    "MOD-RESULTS-001": _c(
        trigger={"interpret_output": "when interpreting model output"},
        expected={
            "question": "connect results to the question",
            "baseline": "connect results to a baseline",
            "limitations": "connect results to limitations",
        },
        forbidden={"number_list": "do not report unexplained number lists"},
    ),
    "VER-E1-001": _c(
        trigger={"implementation": "when an implementation exists"},
        expected={
            "code_paths": "check code paths",
            "interfaces": "check interfaces",
            "units": "check units",
            "boundaries": "check boundaries",
            "reproducibility": "check reproducibility",
        },
        forbidden={"exit_zero": "do not equate process exit zero with correctness"},
    ),
    "VER-E2-001": _c(
        trigger={"numerical_result": "when a numerical result exists"},
        expected={
            "recalculation": "check independent recalculation",
            "tolerances": "check tolerances",
            "convergence": "check convergence",
            "numerical_identity": "check numerical identity and stability",
        },
        forbidden={"format_mask": "do not hide numerical instability behind formatting"},
    ),
    "VER-E3-001": _c(
        trigger={"model_result": "when a model result exists"},
        expected={
            "constraints": "check constraints",
            "invariants": "check invariants",
            "limit_cases": "check limiting cases",
            "counterexamples": "check counterexamples",
            "sensitivity": "check sensitivity",
        },
        forbidden={"nominal_robustness": "do not claim robustness from one nominal run"},
    ),
    "VER-E4-001": _c(
        trigger={
            "use": "when a model is examined for use",
            "claim": "before a model claim",
        },
        expected={
            "assumptions": "check assumptions",
            "parameters": "check parameters",
            "scale": "check scale",
            "mechanisms": "check mechanisms",
            "reality_fit": "check reality fit",
        },
        forbidden={"implementation_substitute": "do not use implementation verification as a substitute for model examination"},
    ),
    "VER-S6-DUAL-001": _c(
        trigger={"s6_promotion": "during S6 promotion"},
        expected={
            "solution_verification": "complete solution verification",
            "model_examination": "complete model examination",
        },
        forbidden={"one_axis": "do not close S6 with only one axis"},
    ),
    "VER-UNCERTAINTY-001": _c(
        trigger={
            "uncertain_inputs": "when inputs are uncertain",
            "sensitive_parameters": "when decision-sensitive parameters exist",
        },
        expected={
            "quantify": "quantify uncertainty where supported",
            "bound": "otherwise bound uncertainty",
            "propagate": "propagate uncertainty to affected claims",
        },
        forbidden={"generic_prose": "do not attach generic limitation prose without analysis"},
    ),
    "VER-ROBUST-001": _c(
        trigger={"robustness_claim": "before a robustness claim"},
        expected={
            "perturbations": "define justified perturbations",
            "metrics": "define robustness metrics",
            "baselines": "define nominal baselines",
            "decision_impact": "measure decision impact",
        },
        forbidden={"visual_proxy": "do not call visual similarity a robustness proof"},
    ),
    "MAN-STRUCTURE-001": _c(
        trigger={"draft": "during manuscript drafting", "revision": "during structural revision"},
        expected={
            "responsibility": "give each section a question-facing responsibility",
            "dependency_order": "give sections a dependency order",
        },
        forbidden={
            "worklog": "do not mirror the work log in the paper",
            "internal_state": "do not mirror internal project state in the paper",
        },
    ),
    "MAN-CONTENT-001": _c(
        trigger={"write": "when writing paper content", "revise": "when revising paper content"},
        expected={
            "objects": "explain modeled objects for a reader",
            "data": "explain data for a reader",
            "derivation": "explain derivation for a reader",
            "results": "explain results for a reader",
            "meaning": "explain meaning for a reader",
        },
        forbidden={
            "formula_dump": "do not use formula dumping as explanation",
            "number_dump": "do not use number dumping as explanation",
        },
    ),
    "MAN-READER-001": _c(
        trigger={"audit": "during manuscript audit", "substantial_revision": "during substantial revision"},
        expected={"standalone": "audit comprehension without relying on code or internal notes"},
        forbidden={"meta_language": "do not leak audit meta-language into evaluator-visible prose"},
    ),
    "MAN-ACCEPT-001": _c(
        trigger={
            "section_complete": "when claiming a manuscript section complete",
            "paper_complete": "when claiming the full paper complete",
        },
        expected={
            "global": "apply global acceptance criteria",
            "section_specific": "apply section-specific acceptance criteria",
        },
        forbidden={"local_aggregate": "do not aggregate local passes into a full-paper pass without scope evidence"},
    ),
    "MAN-LOCAL-001": _c(
        trigger={"small_edit": "for a small local edit"},
        expected={"local_surface": "edit and recheck only the local dependency surface"},
        forbidden={"typo_full_audit": "do not force a full manuscript audit for a typo-only change"},
    ),
    "MAN-PROFILE-001": _c(
        trigger={
            "user_selects": "the user explicitly selects the profile",
            "project_selects": "the project explicitly selects the profile",
        },
        expected={
            "correctness": "profile application must not override correctness",
            "official_format": "profile application must not override official format",
        },
        forbidden={"default_activation": "do not activate a personal profile by default"},
    ),
    "VIS-DESIGN-001": _c(
        trigger={"figure": "on figure creation", "table": "on table creation"},
        expected={
            "appropriate_visual": "choose an appropriate visual",
            "reader_question": "the visual answers a defined reader question",
        },
        forbidden={"decorative": "do not create visuals without an information purpose"},
    ),
    "VIS-LAYOUT-001": _c(
        trigger={"paper_render": "during paper rendering", "layout": "during layout work"},
        expected={
            "readability": "verify readability",
            "fonts": "verify fonts",
            "pagination": "verify pagination",
            "captions": "verify captions",
            "placement": "verify placement",
        },
        forbidden={"source_only": "do not claim layout success from source inspection alone"},
    ),
    "VIS-IDENTITY-001": _c(
        trigger={
            "data_output": "when a visual consumes data",
            "model_output": "when a visual consumes model output",
        },
        expected={
            "data_identity": "preserve visual data identity",
            "units": "preserve units",
            "legend": "preserve legend identity",
            "provenance": "preserve visual provenance",
        },
        forbidden={"manual_values": "do not manually alter plotted values"},
    ),
    "DEL-FINAL-001": _c(
        trigger={"finalization": "during finalization", "promotion": "during delivery promotion"},
        expected={
            "required_files": "check required files",
            "reproducibility": "check reproducibility",
            "rendering": "check rendering",
            "submission_boundary": "check submission boundaries",
        },
        forbidden={
            "temporary": "do not deliver temporary artifacts",
            "unverified": "do not deliver unverified artifacts",
        },
    ),
    "DEL-PROVENANCE-001": _c(
        trigger={"external_material": "when delivery contains external material"},
        expected={
            "citation": "close citation provenance",
            "license": "close license provenance",
            "lineage": "close source lineage",
        },
        forbidden={"unverifiable": "do not ship unverifiable external assets"},
    ),
    "DEL-HANDOFF-001": _c(
        trigger={"pause": "on pause", "handoff": "on handoff", "closure": "on closure"},
        expected={
            "state": "synchronize authoritative state",
            "open_items": "synchronize open items",
            "next_action": "synchronize the next legal action",
        },
        forbidden={"narrative_only": "do not use a narrative summary as the only handoff"},
    ),
    "MNT-CLASSIFY-001": _c(
        trigger={"explicit_change": "for an explicit Skill change request"},
        expected={
            "change_type": "classify the change type",
            "risk": "classify L0-L4 risk",
        },
        forbidden={"append_only": "do not treat every edit as an append-only wording patch"},
    ),
    "MNT-IMPACT-001": _c(
        trigger={"l1_plus": "for an L1 or higher change"},
        expected={
            "capability": "calculate capability impact",
            "route": "calculate route impact",
            "state": "calculate state impact",
            "schema": "calculate schema impact",
            "module": "calculate module or interpreter impact",
            "test": "calculate test impact",
        },
        forbidden={
            "callers_first": "do not edit before checking callers",
            "conflicts_first": "do not edit before checking conflicts",
        },
    ),
    "MNT-OWNER-001": _c(
        trigger={"add": "on rule addition", "modify": "on rule modification"},
        expected={"canonical_owner": "modify or assign exactly one canonical owner"},
        forbidden={"second_copy": "do not add a second normative copy"},
    ),
    "MNT-EVAL-001": _c(
        trigger={"substantive_change": "for a substantive change"},
        expected={
            "positive": "add a positive case",
            "near_miss": "add a near-miss negative case",
            "mixed_conflict": "add mixed and conflict cases",
        },
        forbidden={"wording_only": "do not claim behavior from wording-only tests"},
    ),
    "MNT-RELOAD-001": _c(
        trigger={"runtime_change": "when runtime behavior changes"},
        expected={
            "fresh_invocation": "verify with a fresh invocation",
            "reload_candidate": "the fresh invocation reloads the changed Skill",
        },
        forbidden={"self_certify": "do not self-certify changed behavior in the editing context"},
    ),
    "MNT-ROLLBACK-001": _c(
        trigger={"l3": "for an L3 change", "l4": "for an L4 change"},
        expected={
            "prior_release": "preserve the prior release",
            "rollback_point": "preserve an explicit rollback point",
        },
        forbidden={"overwrite_stable": "do not overwrite the only stable release"},
    ),
}


def clause_id(capability_id: str, local: str) -> str:
    field, key = local.split(".", 1)
    return f"SRC.{capability_id}.{field.upper()}.{key.upper()}"


def atom_clause_map() -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}

    def bind(atoms: list[str], *locals_: str) -> None:
        for atom in atoms:
            if atom in mapping:
                raise ValueError(f"duplicate atom review mapping: {atom}")
            mapping[atom] = list(locals_)

    bind(["GOV.MODE.DERIVE"], "trigger.request", "expected.mode_before_route", "forbidden.silence_write", "forbidden.readonly_write")
    bind(["GOV.MODE.STABLE"], "trigger.request", "expected.mode_before_route")
    bind(["GOV.AUTH.WRITE_SCOPE"], "trigger.action", "expected.authorization")
    bind(["GOV.AUTH.CLAIM_SCOPE"], "trigger.action", "expected.epistemic_truth")
    bind(["GOV.AUTH.FROZEN_CHOICE"], "trigger.action", "expected.project_choice")
    bind(["GOV.AUTH.DIMENSION_SEPARATION"], "trigger.action", "expected.authorization", "expected.epistemic_truth", "expected.project_choice", "expected.state", "expected.procedure", "forbidden.total_priority")
    bind(["GOV.ROUTE.RAW_REQUEST"], "trigger.substantive_execution", "expected.action")
    bind(["GOV.ROUTE.STATE_BIND"], "trigger.substantive_execution", "expected.state")
    bind(["GOV.ROUTE.UNIQUE_WRITE"], "trigger.substantive_execution", "expected.mode", "expected.object", "expected.action", "expected.state")
    bind(["GOV.ROUTE.DECOMPOSE"], "expected.object", "expected.action")
    bind(["GOV.ROUTE.TUPLE"], "expected.mode", "expected.object", "expected.action", "expected.state")
    bind(["GOV.ROUTE.PROOF_SOURCE"], "forbidden.catchall", "forbidden.legacy_link")
    bind(["GOV.OWNER.UNIQUE"], "trigger.interpretation", "trigger.maintenance", "expected.canonical_owner", "forbidden.duplicate_owner")
    bind(["GOV.RECEIPT.START_MATCH", "GOV.RECEIPT.END_MATCH"], "trigger.receipt", "expected.discriminated_contract", "expected.route_consistency", "forbidden.second_schema")
    bind(["GOV.DECISION.CLASSIFY"], "trigger.design", "trigger.frozen_change", "expected.closed_classification", "forbidden.greenfield_keep")
    bind(["STATE.TYPE.MATCH"], "trigger.read", "trigger.write", "expected.question", "expected.shared_data", "expected.artifact", "expected.project", "forbidden.one_stage")
    bind(["STATE.EVIDENCE.TYPED", "STATE.TRANSITION.GATED", "STATE.ROUTE.RECORD"], "trigger.write", "expected.question", "expected.shared_data", "expected.artifact", "expected.project")
    bind(["REC.R0.CONTINUE"], "trigger.consistent_state", "trigger.consistent_artifacts", "expected.direct_state", "expected.no_full_reread")
    bind(["REC.R0.READ_SCOPE"], "expected.direct_state", "expected.declared_inputs", "expected.no_full_reread")
    bind(["REC.R0.NO_MANIFEST"], "forbidden.ordinary_manifest")
    bind(["REC.R1.ELIGIBILITY"], "trigger.localizable_change", "expected.affected_components", "expected.consumers", "forbidden.causeless_full_read")
    bind(["REC.R1.TRANSITIVE"], "trigger.localizable_change", "expected.affected_components", "expected.consumers")
    bind(["REC.R1.REVIEW_CLOSURE"], "expected.affected_components", "expected.consumers")
    bind(["REC.R1.READ_SCOPE"], "expected.affected_components", "expected.consumers", "forbidden.causeless_full_read")
    bind(["REC.R2.FULL"], "trigger.invalid_state", "trigger.identity_conflict", "trigger.unlocalizable_change", "trigger.explicit_full", "trigger.closure")
    bind(["REC.R2.FULL_READ"], "expected.complete_evidence")
    bind(["REC.R2.EVIDENCE_REBUILD"], "expected.complete_evidence")
    bind(["REC.R2.NO_NARRATIVE_ONLY"], "forbidden.narrative_only")
    bind(["ART.ADMIT.CONSUMER"], "trigger.before_creation", "expected.consumer")
    bind(["ART.ADMIT.PROPOSAL_FIELDS"], "trigger.before_creation", "expected.purpose", "expected.lifecycle", "expected.class", "expected.authorization")
    bind(["ART.ADMIT.NO_SPECULATION"], "trigger.before_creation", "forbidden.placeholder", "forbidden.speculative_directory")
    bind(["ART.ADMIT.MINIMAL"], "forbidden.placeholder", "forbidden.speculative_directory")
    bind(["ART.PROMOTE.VALIDATE"], "trigger.temporary", "trigger.working", "expected.validate", "forbidden.scratch", "@DEL-FINAL-001.forbidden.unverified")
    bind(["ART.REGISTER.IDENTITY"], "expected.registry")
    bind(["PRJ.SCOPE.BOUNDARY"], "trigger.new_project", "expected.deliverables", "expected.boundaries")
    bind(["PRJ.SCOPE.AMBIGUITY", "PRJ.SCOPE.SUCCESS"], "expected.boundaries")
    bind(["PRJ.SCOPE.INVENTORY"], "expected.questions", "expected.shared_evidence", "expected.deliverables", "expected.boundaries")
    bind(["PRJ.SCOPE.CONTROLLED_CHANGE"], "trigger.scope_change", "expected.questions", "expected.shared_evidence", "expected.deliverables", "expected.boundaries")
    bind(["PRJ.SCOPE.NO_UNSUPPORTED_TASK"], "forbidden.unsupported_tasks")
    bind(["PRJ.STRUCTURE.INSPECT", "PRJ.STRUCTURE.TOOLCHAIN"], "trigger.authorized_init", "expected.consumed_structure")
    bind(["PRJ.STRUCTURE.LAZY"], "trigger.authorized_init", "expected.consumed_structure", "forbidden.legacy_scaffold")
    bind(["PRJ.PLAN.COMPONENTS", "PRJ.PLAN.NEXT_ACTION"], "trigger.comprehensive_plan", "expected.work_packages")
    bind(["PRJ.PLAN.DEPENDENCIES"], "expected.dependencies")
    bind(["PRJ.PLAN.TRACE"], "expected.work_packages", "expected.dependencies", "expected.evidence", "expected.deliverables")
    bind(["PRJ.PLAN.OWNER_BOUNDARY"], "forbidden.state_override", "forbidden.recovery_override")
    bind(["EVD.SEARCH.CLAIM_FIRST", "EVD.SEARCH.COUNTEREVIDENCE"], "trigger.literature", "expected.authoritative_search")
    bind(["EVD.SEARCH.PRIMARY", "EVD.POLICY.CURRENT", "EVD.EXTERNAL.AUTHORITATIVE"], "trigger.external_fact", "expected.authoritative_search")
    bind(["EVD.SEARCH.FULLTEXT_SCOPE"], "expected.claim_use", "@EVD-PROVENANCE-001.forbidden.abstract_fulltext")
    bind(["EVD.EXTERNAL.NO_SNIPPET_AI"], "forbidden.snippet_primary", "forbidden.ai_primary")
    bind(["EVD.PROV.CLAIM_MAP"], "trigger.external_fact", "trigger.external_reference", "expected.claim_link")
    bind(["EVD.PROV.METADATA"], "trigger.external_data", "trigger.external_figure", "trigger.external_reference", "expected.source", "expected.license", "expected.identity")
    bind(["DATA.IDENTITY.SOURCE"], "expected.source")
    bind(["DATA.IDENTITY.CONTEXT"], "expected.units", "expected.time_scope", "expected.space_scope")
    bind(["DATA.IDENTITY.RAW_IMMUTABLE"], "expected.raw_identity", "forbidden.overwrite_raw")
    bind(["DATA.IDENTITY.BEFORE_USE"], "trigger.any_use", "expected.source", "expected.schema", "expected.units", "expected.time_scope", "expected.space_scope", "expected.raw_identity")
    bind(["DATA.AUDIT.SCHEMA"], "trigger.d0", "trigger.quality_question", "expected.validity", "@DATA-IDENTITY-001.expected.schema")
    bind(["DATA.AUDIT.COMPLETENESS"], "expected.completeness")
    bind(["DATA.AUDIT.MISSING"], "expected.missingness")
    bind(["DATA.AUDIT.ANOMALY"], "expected.outliers")
    bind(["DATA.AUDIT.DUPLICATE"], "expected.duplicates")
    bind(["DATA.AUDIT.SEMANTIC_CONSISTENCY"], "expected.semantic_consistency")
    bind(["DATA.AUDIT.LEAKAGE"], "expected.validity")
    bind(["DATA.AUDIT.BEFORE_TREATMENT"], "forbidden.clean_before_evidence")
    bind(["DATA.TREAT.DECIDE"], "trigger.d1_findings", "expected.decision", "expected.justification", "expected.alternatives", "forbidden.irreversible_without_decision")
    bind(["DATA.TREAT.COPY"], "expected.decision", "forbidden.irreversible_without_decision")
    bind(["DATA.TREAT.LINEAGE"], "expected.justification", "expected.alternatives")
    bind(["DATA.FREEZE.IDENTITY"], "trigger.d3_promotion", "expected.processed_identity")
    bind(["DATA.FREEZE.VALIDATE"], "expected.processed_identity", "expected.lineage")
    bind(["DATA.FREEZE.INVALIDATE"], "expected.consumer_contract", "forbidden.change_without_invalidation")
    bind(["MOD.RESTATE.OBJECTS"], "trigger.model_design", "expected.objects")
    bind(["MOD.RESTATE.UNKNOWN", "MOD.RESTATE.KNOWN"], "expected.variables")
    bind(["MOD.RESTATE.OBJECTIVE"], "expected.constraints", "expected.objectives")
    bind(["MOD.RESTATE.OUTPUTS"], "expected.outputs")
    bind(["MOD.RESTATE.BEFORE_ALGORITHM"], "forbidden.algorithm_first")
    bind(["MOD.COMPARE.BASELINE"], "trigger.s2_s3", "expected.viable_candidates", "forbidden.single_method")
    bind(["MOD.COMPARE.ASSUMPTIONS"], "expected.viable_candidates", "expected.explicit_criteria")
    bind(["MOD.COMPARE.SAME_EVIDENCE", "MOD.COMPARE.RATIONALE"], "expected.explicit_criteria")
    bind(["MOD.SPEC.ASSUMPTIONS"], "trigger.s3_s4", "expected.assumptions")
    bind(["MOD.SPEC.VARIABLES"], "expected.symbols", "expected.units")
    bind(["MOD.SPEC.EQUATIONS"], "expected.equations")
    bind(["MOD.SPEC.PARAMETERS"], "expected.parameters", "expected.units")
    bind(["MOD.SPEC.INTERFACE", "MOD.SPEC.ALGORITHM"], "expected.interfaces")
    bind(["MOD.SPEC.FREEZE"], "expected.assumptions", "expected.symbols", "expected.equations", "expected.parameters", "expected.units", "expected.interfaces")
    bind(["MOD.SPEC.READINESS"], "forbidden.ambiguous_implementation")
    bind(["MOD.IMPLEMENT.REPRODUCE"], "trigger.s4_s5", "expected.reproducible")
    bind(["MOD.IMPLEMENT.DETERMINISM"], "expected.deterministic_inputs")
    bind(["MOD.IMPLEMENT.OUTPUT_REGISTER"], "expected.inspectable_outputs")
    bind(["MOD.IMPLEMENT.SPEC_BIND"], "forbidden.code_as_spec")
    bind(["MOD.RESULTS.TRACE"], "trigger.interpret_output", "expected.question", "expected.baseline", "expected.limitations", "forbidden.number_list")
    bind(["MOD.RESULTS.IDENTITY", "MOD.RESULTS.INTERPRET"], "expected.question")
    bind(["MOD.RESULTS.FAILURES"], "expected.limitations")
    bind(["VER.E1.CODE_PATHS", "VER.E1.ERROR_PATHS"], "trigger.implementation", "expected.code_paths")
    bind(["VER.E1.INTERFACE"], "expected.interfaces")
    bind(["VER.E1.UNITS"], "expected.units")
    bind(["VER.E1.BOUNDARY"], "expected.boundaries")
    bind(["VER.E1.REPRODUCE"], "expected.reproducibility")
    bind(["VER.E1.EXIT_ZERO"], "forbidden.exit_zero")
    bind(["VER.E2.RECOMPUTE"], "trigger.numerical_result", "expected.recalculation")
    bind(["VER.E2.TOLERANCE"], "expected.tolerances")
    bind(["VER.E2.STABILITY"], "expected.numerical_identity")
    bind(["VER.E2.CONVERGENCE"], "expected.convergence", "expected.numerical_identity")
    bind(["VER.E2.NO_FORMAT_MASK"], "forbidden.format_mask")
    bind(["VER.E3.CONSTRAINT"], "trigger.model_result", "expected.constraints")
    bind(["VER.E3.INVARIANT"], "expected.invariants")
    bind(["VER.E3.LIMIT"], "expected.limit_cases")
    bind(["VER.E3.COUNTEREXAMPLE"], "expected.counterexamples")
    bind(["VER.E3.SENSITIVITY"], "expected.sensitivity", "forbidden.nominal_robustness")
    bind(["VER.E4.ASSUMPTIONS"], "trigger.use", "expected.assumptions")
    bind(["VER.E4.PARAMETERS"], "expected.parameters")
    bind(["VER.E4.SCALE"], "expected.scale")
    bind(["VER.E4.MECHANISM"], "expected.mechanisms")
    bind(["VER.E4.REALITY_FIT"], "expected.reality_fit")
    bind(["VER.E4.USE_CLAIM_GATE"], "trigger.claim", "expected.assumptions", "expected.parameters", "expected.scale", "expected.mechanisms", "expected.reality_fit", "forbidden.implementation_substitute")
    bind(["VER.S6.DUAL_AXIS"], "trigger.s6_promotion", "expected.solution_verification", "expected.model_examination", "forbidden.one_axis")
    bind(["VER.UNCERTAINTY.SOURCES"], "trigger.uncertain_inputs", "trigger.sensitive_parameters")
    bind(["VER.UNCERTAINTY.BOUND"], "expected.quantify", "expected.bound", "forbidden.generic_prose")
    bind(["VER.UNCERTAINTY.PROPAGATE", "VER.UNCERTAINTY.CLAIM_GATE"], "expected.propagate")
    bind(["VER.ROBUST.PERTURB"], "trigger.robustness_claim", "expected.perturbations", "expected.decision_impact")
    bind(["VER.ROBUST.METRIC"], "expected.metrics")
    bind(["VER.ROBUST.BASELINE"], "expected.baselines", "@VER-E3-001.forbidden.nominal_robustness")
    bind(["VER.ROBUST.FAILURE_REGION"], "expected.perturbations", "expected.decision_impact")
    bind(["VER.ROBUST.NO_VISUAL_PROXY"], "forbidden.visual_proxy")
    bind(["MAN.STRUCTURE.RESPONSIBILITY", "MAN.STRUCTURE.TRACE"], "trigger.draft", "trigger.revision", "expected.responsibility")
    bind(["MAN.STRUCTURE.DEPENDENCY"], "expected.dependency_order")
    bind(["MAN.STRUCTURE.NO_WORKLOG"], "forbidden.worklog", "forbidden.internal_state")
    bind(["MAN.STRUCTURE.REQUIREMENTS"], "expected.responsibility", "expected.dependency_order")
    bind(["MAN.CONTENT.EXPLANATION_TRACE"], "trigger.write", "trigger.revise", "expected.objects", "expected.data", "expected.derivation", "expected.results", "expected.meaning")
    bind(["MAN.CONTENT.CLAIM_EVIDENCE", "MAN.CONTENT.METHOD"], "expected.data", "expected.derivation")
    bind(["MAN.CONTENT.RESULT"], "expected.results")
    bind(["MAN.CONTENT.LIMITATION"], "expected.meaning")
    bind(["MAN.CONTENT.NOTATION"], "expected.objects", "expected.derivation")
    bind(["MAN.CONTENT.NO_DUMP"], "forbidden.formula_dump", "forbidden.number_dump")
    bind(["MAN.READER.STANDALONE", "MAN.READER.FLOW", "MAN.READER.FRONT", "MAN.READER.SCOPE"], "trigger.audit", "trigger.substantial_revision", "expected.standalone")
    bind(["MAN.READER.NO_META"], "forbidden.meta_language")
    bind(["MAN.ACCEPT.SECTION"], "trigger.section_complete", "expected.section_specific")
    bind(["MAN.ACCEPT.GLOBAL"], "trigger.paper_complete", "expected.global", "forbidden.local_aggregate")
    bind(["MAN.ACCEPT.CROSSREF", "MAN.ACCEPT.NO_PLACEHOLDER", "MAN.ACCEPT.RENDER"], "expected.global", "expected.section_specific")
    bind(["MAN.LOCAL.SCOPE", "MAN.LOCAL.DEPENDENCIES"], "trigger.small_edit", "expected.local_surface")
    bind(["MAN.LOCAL.NO_FULL_AUDIT"], "forbidden.typo_full_audit")
    bind(["MAN.LOCAL.REOPEN_A3"], "expected.local_surface")
    bind(["MAN.PROFILE.OPT_IN"], "trigger.user_selects", "trigger.project_selects", "forbidden.default_activation")
    bind(["MAN.PROFILE.TRUTH"], "expected.correctness")
    bind(["MAN.PROFILE.FORMAT"], "expected.official_format")
    bind(["VIS.DESIGN.QUESTION"], "trigger.figure", "trigger.table", "expected.reader_question", "forbidden.decorative")
    bind(["VIS.DESIGN.TYPE", "VIS.DESIGN.UNCERTAINTY"], "expected.appropriate_visual")
    bind(["VIS.LAYOUT.LEGIBILITY", "VIS.LAYOUT.COLOR"], "trigger.paper_render", "trigger.layout", "expected.readability")
    bind(["VIS.LAYOUT.LABELS"], "trigger.paper_render", "trigger.layout", "expected.readability", "@VIS-IDENTITY-001.expected.units", "@VIS-IDENTITY-001.expected.legend")
    bind(["VIS.LAYOUT.FONTS"], "expected.fonts")
    bind(["VIS.LAYOUT.PAGINATION"], "expected.pagination")
    bind(["VIS.LAYOUT.CAPTION"], "expected.captions")
    bind(["VIS.LAYOUT.PLACEMENT"], "expected.placement")
    bind(["VIS.IDENTITY.RENDER"], "expected.provenance", "@VIS-LAYOUT-001.forbidden.source_only")
    bind(["VIS.IDENTITY.DATA"], "trigger.data_output", "trigger.model_output", "expected.data_identity")
    bind(["VIS.IDENTITY.SYNC"], "expected.provenance")
    bind(["VIS.IDENTITY.NO_MANUAL_VALUES"], "forbidden.manual_values")
    bind(["DEL.FINAL.COVERAGE"], "trigger.finalization", "trigger.promotion", "expected.required_files")
    bind(["DEL.FINAL.REPRODUCE"], "expected.reproducibility")
    bind(["DEL.FINAL.RENDER"], "expected.rendering")
    bind(["DEL.FINAL.BOUNDARY"], "expected.submission_boundary")
    bind(["DEL.FINAL.NO_TEMP"], "forbidden.temporary")
    bind(["DEL.PROV.CITATIONS"], "trigger.external_material", "expected.citation")
    bind(["DEL.PROV.LICENSE"], "expected.license")
    bind(["DEL.PROV.LINEAGE", "DEL.PROV.WHITELIST"], "expected.lineage", "forbidden.unverifiable")
    bind(["DEL.HANDOFF.STATE"], "trigger.pause", "trigger.handoff", "trigger.closure", "expected.state", "expected.open_items", "expected.next_action", "forbidden.narrative_only")
    bind(["MNT.CLASSIFY.OLD", "MNT.CLASSIFY.NEW", "MNT.CLASSIFY.TRIGGER"], "trigger.explicit_change", "expected.change_type", "forbidden.append_only")
    bind(["MNT.CLASSIFY.RISK"], "expected.risk")
    bind(["MNT.IMPACT.TRANSITIVE"], "trigger.l1_plus", "expected.capability", "expected.route", "expected.state", "expected.schema", "expected.module", "expected.test", "forbidden.callers_first")
    bind(["MNT.IMPACT.ROUTE_REACH"], "expected.route", "forbidden.callers_first")
    bind(["MNT.IMPACT.CONFLICT_GRAPH"], "forbidden.conflicts_first")
    bind(["MNT.OWNER.CANONICAL"], "trigger.add", "trigger.modify", "expected.canonical_owner", "forbidden.second_copy")
    bind(["MNT.EVAL.POSITIVE"], "trigger.substantive_change", "expected.positive", "forbidden.wording_only")
    bind(["MNT.EVAL.NEAR_NEGATIVE"], "expected.near_miss", "forbidden.wording_only")
    bind(["MNT.EVAL.CONFLICT"], "expected.mixed_conflict", "forbidden.wording_only")
    bind(["MNT.RELOAD.ISOLATED"], "trigger.runtime_change", "expected.fresh_invocation", "expected.reload_candidate")
    bind(["MNT.RELOAD.INDEPENDENT_AGENT"], "forbidden.self_certify")
    bind(["MNT.ROLLBACK.PRESERVE"], "trigger.l3", "trigger.l4", "expected.prior_release", "expected.rollback_point", "forbidden.overwrite_stable")
    bind(["MNT.ROLLBACK.COMPATIBILITY"], "expected.prior_release", "expected.rollback_point")
    return mapping


DEFECTS = {
    "V10.DEFECT.MODEL.REDESIGN_CLOSED_STATE": {
        "description": "S4-S7 model replacement could retain stale implementation, result, or manuscript consumers.",
        "reproduction": "Select RT.MODEL.COMPARE for an S7 question and replace the frozen model without an S7-to-S2 reopen and transitive invalidation.",
        "atom_ids": ["MOD.RESTATE.REDESIGN"],
        "source_refs": ["references/preservation/audit-v6-v10.md", "references/preservation/audit-v11-v14.md"],
    },
    "V10.DEFECT.PROVENANCE.DEFAULT_FILE_BUNDLE": {
        "description": "A provenance action could recreate redundant fixed README/JSON/BIB/note/ref bundles.",
        "reproduction": "Resolve a literature provenance request with no project file consumer and observe fixed bundle creation.",
        "atom_ids": ["EVD.PROV.NO_FORCED_FILES"],
        "source_refs": ["references/preservation/audit-v6-v10.md"],
    },
    "V10.DEFECT.DELIVERY.SECRET_LEAK": {
        "description": "A recursively assembled delivery package could include credentials or private data despite valid external-material lineage.",
        "reproduction": "Build a package from a workspace containing a credential file and omit a sensitive-content scan.",
        "atom_ids": ["DEL.PROV.SECRETS"],
        "source_refs": ["references/preservation/audit-v6-v10.md"],
    },
    "V15.GAP.DATA.READONLY_TREATMENT_COLLAPSE": {
        "description": "A request for treatment options had no read-only route and could be promoted into a fictitious executed treatment decision.",
        "reproduction": "Ask only for alternatives at D1 in project_readonly mode; V14 returns no exact route or forces the mutating treatment contract.",
        "atom_ids": ["DATA.TREAT.OPTIONS"],
        "source_refs": ["references/preservation/audit-v11-v14.md", "references/preservation/real-project-2025-a-rule-extraction.md"],
    },
    "V15.GAP.EVIDENCE.CONSUMER_SCOPE": {
        "description": "External values recorded for internal regression could escape into teammate, manuscript, answer, or acceptance consumers.",
        "reproduction": "Register an external answer as an internal comparator and then reuse the same literal value as a formal result without a permitted-consumer check.",
        "atom_ids": ["EVD.PROV.CONSUMER_BOUNDARY"],
        "source_refs": ["references/preservation/audit-v6-v10.md", "references/preservation/real-project-2025-a-rule-extraction.md"],
    },
    "V15.GAP.MODEL.AUXILIARY_PROMOTION": {
        "description": "An internal auxiliary verifier could be expanded into a competing public model without reopening and freezing the model contract.",
        "reproduction": "Use a strong internal regression solver, then copy its full derivation into the manuscript while leaving the primary model specification unchanged.",
        "atom_ids": ["MOD.RESULTS.AUXILIARY_METHOD_VISIBILITY"],
        "source_refs": ["references/preservation/real-project-2025-a-rule-extraction.md"],
    },
    "V15.GAP.MODEL.TEAMMATE_HANDOFF": {
        "description": "A completed question could leave only code and manuscript fragments, with no current-identity brief that another teammate can restate and reproduce.",
        "reproduction": "Finish a substantive question, then ask an uninvolved teammate to explain its model, execution, evidence, conclusion, and boundary from the existing artifacts.",
        "atom_ids": ["MOD.RESULTS.TEAMMATE_BRIEF"],
        "source_refs": ["references/preservation/audit-v6-v10.md", "references/preservation/real-project-2025-a-rule-extraction.md"],
    },
    "V15.GAP.VERIFICATION.RISK_MATCH": {
        "description": "The E3 menu could be executed mechanically or skipped without mapping selected and excluded checks to the model's actual structural risks.",
        "reproduction": "Declare only the structural umbrella event, or run the same five checks for every model, without stating which error each check could falsify.",
        "atom_ids": ["VER.E3.RISK_MATCH"],
        "source_refs": ["references/preservation/audit-v6-v10.md", "references/preservation/audit-v11-v14.md", "references/preservation/real-project-2025-a-rule-extraction.md"],
    },
    "V15.GAP.VISUAL.SOURCE_FIDELITY": {
        "description": "Code-generated schematics could pass generic visual quality checks while inventing unsupported objects, topology, direction, or geometry.",
        "reproduction": "Generate a polished engineering diagram from a sparse source and allow default layout or domain priors to add connections that the source never states.",
        "atom_ids": ["VIS.DESIGN.SOURCE_FIDELITY"],
        "source_refs": ["references/preservation/audit-v6-v10.md", "references/preservation/forward-eval-visual.md"],
    },
}


BROADER_ATOMS = {
    "ART.ADMIT.MINIMAL", "DATA.AUDIT.LEAKAGE", "DATA.FREEZE.VALIDATE",
    "EVD.PROV.CLAIM_MAP",
    "GOV.MODE.STABLE", "MAN.ACCEPT.CROSSREF", "MAN.ACCEPT.NO_PLACEHOLDER",
    "MAN.ACCEPT.RENDER", "MAN.CONTENT.METHOD", "MAN.LOCAL.REOPEN_A3", "MAN.READER.FLOW",
    "MAN.READER.FRONT", "MAN.READER.SCOPE", "MAN.STRUCTURE.REQUIREMENTS",
    "MAN.STRUCTURE.RESPONSIBILITY", "MAN.STRUCTURE.TRACE",
    "MNT.ROLLBACK.COMPATIBILITY", "MOD.COMPARE.ASSUMPTIONS", "MOD.COMPARE.BASELINE",
    "MOD.COMPARE.RATIONALE",
    "MOD.COMPARE.SAME_EVIDENCE", "MOD.RESULTS.FAILURES", "MOD.RESULTS.IDENTITY",
    "MOD.RESULTS.INTERPRET", "MOD.SPEC.ALGORITHM", "PRJ.SCOPE.AMBIGUITY",
    "PRJ.SCOPE.SUCCESS", "PRJ.STRUCTURE.INSPECT", "PRJ.STRUCTURE.TOOLCHAIN",
    "REC.R1.ELIGIBILITY", "REC.R1.TRANSITIVE", "REC.R2.FULL_READ",
    "STATE.EVIDENCE.TYPED", "STATE.ROUTE.RECORD",
    "STATE.TRANSITION.GATED", "VER.E1.ERROR_PATHS", "VER.ROBUST.FAILURE_REGION",
    "VER.S6.DUAL_AXIS",
    "VIS.DESIGN.UNCERTAINTY", "VIS.LAYOUT.COLOR", "VIS.LAYOUT.LABELS",
}


# V9 compressed E3 into five unconditional-looking checks. The recovered
# detailed procedure shows that mechanically running all five is itself a
# defect: at least one falsifiable E3 check remains mandatory, while the menu
# is selected from stated structural risks. Record that corrective narrowing
# explicitly instead of mislabelling it equal or broader.
CORRECTED_SOURCE_CLAUSES = {
    "SRC.VER-E3-001.TRIGGER.MODEL_RESULT": {
        "relation": "corrected_binding_overconstraint",
        "gap_id": "V15.GAP.VERIFICATION.RISK_MATCH",
        "preserved_by_atom_ids": ["VER.E3.RISK_MATCH"],
        "preserved_by_contract_ref": "references/route-contract.json#action_contracts/validate_structure",
        "rationale": "The source trigger remains mandatory: a model-result structural check must select at least one risk-matched falsifiable E3 test. The corrected object is the compressed trigger-to-CONSTRAINT/menu binding, not the trigger itself.",
    },
    "SRC.VER-E3-001.EXPECTED.CONSTRAINTS": {
        "gap_id": "V15.GAP.VERIFICATION.RISK_MATCH",
        "rationale": "Constraint checks are mandatory when explicit constraints are a live structural risk; exclusion otherwise requires a recorded reason.",
    },
    "SRC.VER-E3-001.EXPECTED.INVARIANTS": {
        "gap_id": "V15.GAP.VERIFICATION.RISK_MATCH",
        "rationale": "Invariant checks are mandatory when an invariant exists and can falsify the model; exclusion otherwise requires a recorded reason.",
    },
    "SRC.VER-E3-001.EXPECTED.LIMIT_CASES": {
        "gap_id": "V15.GAP.VERIFICATION.RISK_MATCH",
        "rationale": "Limit checks are mandatory when a meaningful limit case bears on the claim; exclusion otherwise requires a recorded reason.",
    },
    "SRC.VER-E3-001.EXPECTED.COUNTEREXAMPLES": {
        "gap_id": "V15.GAP.VERIFICATION.RISK_MATCH",
        "rationale": "Counterexample checks are mandatory when they can falsify the claim's structural risk; exclusion otherwise requires a recorded reason.",
    },
    "SRC.VER-E3-001.EXPECTED.SENSITIVITY": {
        "gap_id": "V15.GAP.VERIFICATION.RISK_MATCH",
        "rationale": "Sensitivity checks are mandatory for variable inputs or structural choices, not as a fixed ritual for every model.",
    },
}


def _all_clause_ids() -> set[str]:
    return {
        clause_id(capability, f"{field}.{key}")
        for capability, fields in SOURCE_CLAUSES.items()
        for field, clauses in fields.items()
        for key in clauses
    }


def _resolve_clause(rule: dict[str, Any], local: str) -> str:
    if local.startswith("@"):
        capability, suffix = local[1:].split(".", 1)
        return clause_id(capability, suffix)
    return clause_id(rule["capability"], local)


def build_artifact(
    root: Path, baseline_override: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    baseline = (
        baseline_override
        if baseline_override is not None
        else load_json(root / "references/migration/v9-capability-baseline.json")
    )
    rules, by_id = load_rules(root)
    active = [rule for rule in rules if rule.get("status") == "active"]
    review_sources = review_source_inventory(root)
    defect_rows = reviewed_defects(root)
    baseline_by_id = {item["id"]: item for item in baseline["capabilities"]}
    if set(SOURCE_CLAUSES) != set(baseline_by_id):
        raise ValueError("source clause capability set differs from frozen V9 baseline")

    clauses: list[dict[str, Any]] = []
    for capability_id in sorted(SOURCE_CLAUSES):
        source = baseline_by_id[capability_id]
        for field in ("trigger", "expected", "forbidden"):
            normalized = SOURCE_CLAUSES[capability_id][field]
            if not normalized:
                raise ValueError(f"{capability_id}:{field}: empty decomposition")
            for key, text in sorted(normalized.items()):
                clauses.append({
                    "id": clause_id(capability_id, f"{field}.{key}"),
                    "capability_id": capability_id,
                    "source_field": field,
                    "source_field_sha256": sha256_text(source[field]),
                    "source_strength": source["strength"],
                    "normalized_clause": text,
                    "review_status": "reviewed",
                    "relation": None,
                    "correction": None,
                    "atom_ids": [],
                    "coverage_rationale": None,
                })
    clause_by_id = {item["id"]: item for item in clauses}
    mapping = atom_clause_map()
    defect_atoms = {atom for defect in DEFECTS.values() for atom in defect["atom_ids"]}
    current_ids = {rule["id"] for rule in active}
    if set(mapping) & defect_atoms:
        raise ValueError("an atom cannot use source-clause and defect necessity simultaneously")
    if set(mapping) | defect_atoms != current_ids:
        missing = sorted(current_ids - set(mapping) - defect_atoms)
        extra = sorted((set(mapping) | defect_atoms) - current_ids)
        raise ValueError(f"atom necessity mapping mismatch: missing={missing};extra={extra}")

    atom_to_clause_ids: dict[str, list[str]] = {}
    for atom_id, locals_ in mapping.items():
        rule = by_id[atom_id]
        resolved = [_resolve_clause(rule, local) for local in locals_]
        unknown = set(resolved) - set(clause_by_id)
        if unknown:
            raise ValueError(f"{atom_id}: unknown source clauses {sorted(unknown)}")
        atom_to_clause_ids[atom_id] = sorted(set(resolved))
        for source_clause_id in atom_to_clause_ids[atom_id]:
            clause_by_id[source_clause_id]["atom_ids"].append(atom_id)

    uncovered = sorted(item["id"] for item in clauses if not item["atom_ids"])
    if uncovered:
        raise ValueError("uncovered source clauses: " + ",".join(uncovered))
    for item in clauses:
        item["atom_ids"] = sorted(item["atom_ids"])
        correction = CORRECTED_SOURCE_CLAUSES.get(item["id"])
        if correction is not None:
            item["relation"] = correction.get("relation", "corrected_overconstraint")
            item["correction"] = correction
        else:
            item["relation"] = "broader" if any(atom in BROADER_ATOMS for atom in item["atom_ids"]) else "equal"
        item["coverage_rationale"] = (
            "Manually reviewed against the complete source field and the bound atoms' "
            "scope, trigger, strength, effect, evidence, exceptions, owner, and routes."
            if correction is None else
            (
                "Manually reviewed as a correction to a compressed legacy binding; the "
                "source trigger remains mandatory through the named atom and action contract."
                if item["relation"] == "corrected_binding_overconstraint" else
                "Manually reviewed as a corrective narrowing of a compressed legacy "
                "overconstraint; the named versioned gap preserves the non-mechanical intent."
            )
        )

    defect_by_atom = {
        atom: defect_id
        for defect_id, defect in DEFECTS.items()
        for atom in defect["atom_ids"]
    }
    rank = {"MAY": 0, "SHOULD": 1, "MUST": 2}
    atom_reviews = []
    for rule in sorted(active, key=lambda item: item["id"]):
        atom_id = rule["id"]
        source_ids = atom_to_clause_ids.get(atom_id, [])
        source_strengths = {clause_by_id[item]["source_strength"] for item in source_ids}
        if source_strengths and any(rank[rule["strength"]] < rank[item] for item in source_strengths):
            raise ValueError(f"{atom_id}: weaker than a bound source clause")
        origin = "legacy_family" if rule["capability"] in baseline_by_id else "native_v10"
        semantic_hash = canonical_sha256(semantic_atom_contract(rule, origin))
        if source_ids:
            necessity = {"kind": "source_clause", "source_clause_ids": source_ids, "defect_id": None}
        else:
            necessity = {"kind": "versioned_gap", "source_clause_ids": [], "defect_id": defect_by_atom[atom_id]}
        atom_reviews.append({
            "atom_id": atom_id,
            "origin": origin,
            "capability_id": rule["capability"],
            "domain": rule["domain"],
            "owner": rule["owner"],
            "revision": rule["revision"],
            "strength": rule["strength"],
            "routes": sorted(set(rule.get("routes", []))),
            "semantic_sha256": semantic_hash,
            "review_status": "reviewed",
            "necessity": necessity,
            "rationale": (
                "Retained only because the reviewed source clause or named reproducible "
                "versioned gap would otherwise lose an independently observable guarantee."
            ),
        })

    sealed_atom_reviews = [
        {
            "atom_id": item["atom_id"],
            "origin": item["origin"],
            "capability_id": item["capability_id"],
            "domain": item["domain"],
            "owner": item["owner"],
            "strength": item["strength"],
            "routes": item["routes"],
            "semantic_sha256": item["semantic_sha256"],
            "review_status": item["review_status"],
            "necessity": item["necessity"],
            "rationale": item["rationale"],
        }
        for item in atom_reviews
    ]
    review_projection = {
        "review": REVIEW,
        "source_baseline_payload_sha256": baseline["payload_sha256"],
        "review_sources": review_sources,
        "clauses": clauses,
        "atom_reviews": sealed_atom_reviews,
        "defects": defect_rows,
    }
    review_hash = canonical_sha256(review_projection)
    artifact_without_seal = {
        "schema_version": "15.0",
        "artifact_kind": "v9_clause_preservation_and_v15_atom_necessity",
        "claim_boundary": (
            "Only manually reviewed equal, broader, explicitly gap-backed corrective, or "
            "corrected-binding source-clause relations and named, audit-backed versioned gaps justify retention. "
            "Glosses, failure examples, keywords, and capability names are not preservation proof."
        ),
        "version_scope": {
            "source_baseline": "V9",
            "reviewed_target": "V16.0.0-candidate",
            "historical_artifact_kind_retained_for_compatibility": True,
            "defects_collection_semantics": "historical V10 defects plus post-V10 recovered or empirical gaps",
        },
        "review": REVIEW,
        "source_baseline_payload_sha256": baseline["payload_sha256"],
        "review_sources": review_sources,
        "review_source_inventory_sha256": canonical_sha256(review_sources),
        "review_projection_sha256": review_hash,
        "allowed_relations": ["equal", "broader", "corrected_overconstraint", "corrected_binding_overconstraint"],
        "blocking_relations": ["missing", "narrower", "weaker", "unreviewed"],
        "clauses": clauses,
        "atom_reviews": atom_reviews,
        "defects": review_projection["defects"],
        "summary": {
            "v9_capabilities": len(SOURCE_CLAUSES),
            "source_clauses": len(clauses),
            "target_active_atoms": len(active),
            "source_bound_atoms": len(atom_to_clause_ids),
            "defect_bound_atoms": len(defect_atoms),
        },
    }
    artifact = dict(artifact_without_seal)
    artifact["payload_sha256"] = canonical_sha256(artifact_without_seal)
    return artifact, review_hash


def check_artifact(root: Path) -> list[str]:
    errors: list[str] = []
    try:
        expected, review_hash = build_artifact(root)
    except Exception as exc:
        return [f"clause_review_build_error:{exc}"]
    if review_hash != EXPECTED_REVIEW_PROJECTION_SHA256:
        errors.append(
            "clause_review_requires_new_explicit_seal:"
            f"{review_hash}!={EXPECTED_REVIEW_PROJECTION_SHA256}"
        )
    path = root / "references/migration/clause-preservation.json"
    if not path.exists():
        errors.append("clause_preservation_artifact_missing")
    else:
        actual = load_json(path)
        if actual != expected:
            errors.append("clause_preservation_artifact_stale")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--proposal", action="store_true", help="print the proposed review hash without writing")
    parser.add_argument("--write", action="store_true", help="write only when the explicit review seal matches")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    artifact, review_hash = build_artifact(root)
    if args.proposal:
        print(json.dumps({"review_projection_sha256": review_hash, "summary": artifact["summary"]}, ensure_ascii=False, sort_keys=True))
        return 0
    if review_hash != EXPECTED_REVIEW_PROJECTION_SHA256:
        print(json.dumps({"status": "fail", "review_projection_sha256": review_hash, "expected": EXPECTED_REVIEW_PROJECTION_SHA256}, ensure_ascii=False, sort_keys=True))
        return 2
    if args.write:
        dump_json(root / "references/migration/clause-preservation.json", artifact)
    errors = check_artifact(root)
    print(json.dumps({"status": "fail" if errors else "pass", "errors": errors, "summary": artifact["summary"]}, ensure_ascii=False, sort_keys=True))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
