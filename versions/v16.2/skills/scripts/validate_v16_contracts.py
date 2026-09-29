#!/usr/bin/env python3
"""Validate V16 release bindings and the inherited V15 semantic envelope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import validate_v15_contracts as base


SCHEMA_VERSION = "16.0"
RELEASE_SCHEMA_VERSION = "16.2"
RELEASE_ID = "V16.2.0"
CHECKS = [
    "CONTRACT.V16.RELEASE_BINDING",
    "CONTRACT.V16.BASE_PRESERVATION",
    "CONTRACT.V16.COMPATIBLE_CHANGE_BINDING",
    "CONTRACT.V16.ATOMIC_RECONCILIATION",
    "CONTRACT.V16.TARGETED_RECOVERY",
    "CONTRACT.V16.RECOVERY_BOUNDARY",
    "CONTRACT.V16.TEAMMATE_BRIEF_STANDARD",
]


def load(root: Path, relative: str) -> Any:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def value_at(value: Any, *path: str) -> Any:
    current = value
    for token in path:
        if not isinstance(current, dict):
            return None
        current = current.get(token)
    return current


def validate_release_binding(root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    policy = load(root, "references/release-policy.json")
    plan = load(root, "evals/release/release-plan.json")
    state = load(root, "evals/release/release-state.json")
    manifest = load(root, "references/release-manifest.schema.json")
    drivers = [
        {"id": item.get("id"), "script": item.get("script")}
        for item in policy.get("active_drivers", []) if isinstance(item, dict)
    ]
    expected_drivers = [
        {"id": "package", "script": "scripts/validate_v16_package.py"},
        {"id": "contracts", "script": "scripts/validate_v16_contracts.py"},
        {"id": "scenarios", "script": "scripts/run_v16_scenarios.py"},
    ]
    if policy.get("schema_version") != RELEASE_SCHEMA_VERSION or policy.get("release_id") != RELEASE_ID:
        errors.append("release_policy_identity_invalid")
    if drivers != expected_drivers:
        errors.append("release_policy_driver_binding_invalid")
    if policy.get("budget", {}).get("active_driver_count") != 3:
        errors.append("release_policy_driver_budget_invalid")
    required_cases = policy.get("required_case_ids", [])
    if not isinstance(required_cases, list) or len(required_cases) != len(set(required_cases)):
        errors.append("release_policy_case_inventory_invalid")
        required_cases = []
    required_v16 = {
        "BEH.V16.COMPATIBLE.G1.ONE_CHANGESET",
        "SCENARIO.V16.COMPATIBLE.MISSING_R0_ATTESTATION.R1",
        "BEH.V16.COMPATIBLE.MIXED.G1_G2",
        "BEH.V16.COMPATIBLE.MODEL_CONTRACT.REJECTED",
        "BEH.V16.COMPATIBLE.FACET_SMUGGLE.REJECTED",
        "SCENARIO.V16.COMPATIBLE.ATOMIC_RECONCILIATION",
        "SCENARIO.V16.COMPATIBLE.MISSING_EVIDENCE.NO_PARTIAL_COMMIT",
        "SCENARIO.V16.COMPATIBLE.PREFIX_IDENTITY_CHANGE.REJECTED",
        "SCENARIO.V16.COMPATIBLE.OMITTED_ARTIFACT_UPDATE.REJECTED",
        "SCENARIO.V16.COMPATIBLE.UNREGISTERED_CONSUMER.REJECTED",
        "SCENARIO.V16.COMPATIBLE.CLAIM_CONSUMER.REJECTED",
        "SCENARIO.V16.COMPATIBLE.COMPONENT_DRIFT.REJECTED",
        "SCENARIO.V16.COMPATIBLE.UNDECLARED_PATH_DELTA.REJECTED",
        "BEH.V16.COMPATIBLE.UNRELATED_WORKING_DRIFT.IGNORED",
        "SCENARIO.V16.COMPATIBLE.UNDECLARED_EXACT_CONSUMER.REJECTED",
        "BEH.V16.COMPATIBLE.R1.TARGETED_READ_SET",
        "SCENARIO.V16.RECOVERY.R0.SAME_WINDOW",
        "SCENARIO.V16.RECOVERY.R0.OPEN_EXECUTION_CONTINUITY",
        "SCENARIO.V16.RECOVERY.R1.CLEAN_NEW_WINDOW",
        "SCENARIO.V16.RECOVERY.R2.BASELINE_MISSING",
        "SCENARIO.V16.RECOVERY.R2.BASELINE_COVERAGE_INCOMPLETE",
        "SCENARIO.V16.RECOVERY.R2.COMPONENT_GRAPH_DRIFT",
        "SCENARIO.V16.RECOVERY.R2.RELEVANT_UNATTRIBUTED_CHANGE",
        "SCENARIO.V16.RECOVERY.R2.EXPLICIT_BARRIER",
        "SCENARIO.V16.RECOVERY.R2.FULL_ROUNDTRIP",
        "SCENARIO.V16.RECOVERY.R2.INCOMPLETE_FULL_READ.REJECTED",
        "SCENARIO.V16.RECOVERY.R2.CLOSED_BLOCKED.NO_RUNTIME_GRANT",
        "SCENARIO.V16.RECOVERY.R1.RUNTIME_GRANT.EXACT_EXECUTION",
        "SCENARIO.V16.RECOVERY.R1.ESCALATES_TO_R2",
        "BEH.V16.RECOVERY.TRANSIENT_CACHE_IGNORED",
        "SCENARIO.V16.RECOVERY.Q3_TO_Q1_Q2.SAME_WINDOW",
        "SCENARIO.V16.RECOVERY.Q3_TO_Q1_Q2.NEW_WINDOW",
        "BEH.V16.TEAMMATE_BRIEF.G1.CANONICAL_PATH",
        "BEH.V16.TEAMMATE_BRIEF.G1.WRONG_PATH.REJECTED",
        "BEH.V16.TEAMMATE_BRIEF.STRUCTURE.TEN_SECTION",
        "BEH.V16.TEAMMATE_BRIEF.STRUCTURE.NINE_ITEM.REJECTED",
        "BEH.V16.TEAMMATE_BRIEF.STRUCTURE.META_OR_SAFETY_HEADING.REJECTED",
        "BEH.V16.TEAMMATE_BRIEF.S6.HUMAN_GATE_SELECTED",
    }
    if not required_v16.issubset(set(required_cases)):
        errors.append("release_policy_v16_cases_missing")
    if (
        plan.get("schema_version") != RELEASE_SCHEMA_VERSION
        or plan.get("release_id") != RELEASE_ID
        or plan.get("required_drivers") != ["package", "contracts", "scenarios"]
        or plan.get("drivers") != expected_drivers
        or plan.get("required_case_ids") != required_cases
    ):
        errors.append("release_plan_binding_invalid")
    if (
        state.get("schema_version") != RELEASE_SCHEMA_VERSION
        or state.get("release_id") != RELEASE_ID
        or state.get("status") != "candidate"
        or state.get("frozen_at") is not None
        or state.get("gate_report_sha256") is not None
    ):
        errors.append("release_state_candidate_identity_invalid")
    properties = manifest.get("properties", {})
    if (
        value_at(properties, "schema_version", "const") != RELEASE_SCHEMA_VERSION
        or value_at(properties, "release_id", "const") != RELEASE_ID
    ):
        errors.append("release_manifest_identity_invalid")
    return {
        "drivers": len(drivers), "required_cases": len(required_cases),
        "required_v16_cases": len(required_v16),
    }, errors


def validate_base(root: Path, policy_case_ids: set[str]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    runtime = load(root, "references/runtime-policy.json")
    route, route_ids, known_events, witnesses, route_errors = base.validate_route_contract(
        root, runtime
    )
    errors.extend("route:" + item for item in route_errors)
    rules, load_errors = base.load_rule_corpus(root)
    errors.extend("rules:" + item for item in load_errors)
    ledger = load(root, "references/migration/v15-preservation-ledger.json")
    expected_active = ledger.get("inherited_capabilities", {}).get(
        "expected_active_atom_count", -1
    )
    metrics, inventory_errors = base.validate_rule_inventory(
        root, rules, route_ids, known_events, policy_case_ids, expected_active
    )
    errors.extend("inventory:" + item for item in inventory_errors)
    reachable, reachability_errors = base.validate_active_reachability(
        rules, route, runtime
    )
    errors.extend("reachability:" + item for item in reachability_errors)
    packet_metrics, packet_errors = base.validate_capability_packets(root, rules, route)
    errors.extend("packets:" + item for item in packet_errors)
    mutation_passed, mutation_errors = base.validate_runtime_near_negatives(root)
    errors.extend("near_negative:" + item for item in mutation_errors)
    preservation_metrics, preservation_errors = base.validate_preservation(
        root, rules, policy_case_ids
    )
    errors.extend("preservation:" + item for item in preservation_errors)
    return {
        "routes": len(route_ids), "known_events": len(known_events),
        "route_actions_with_witnesses": witnesses,
        "active_rules": metrics.get("active_rules"), "reachable_active_rules": reachable,
        "runtime_near_negatives": mutation_passed,
        "capability_packets": packet_metrics,
        "preservation": preservation_metrics,
    }, errors


def validate_compatible_contract(root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    semantic = load(root, "references/semantic-plan.schema.json")
    route = load(root, "references/route-contract.json")
    runtime = load(root, "references/runtime-policy.json")
    machine = load(root, "references/state-machine.json")
    state_schema = load(root, "references/state.schema.json")
    bundle = load(root, "references/compatible-change-bundle.schema.json")
    compatible_def = value_at(semantic, "$defs", "compatible_change")
    effect_def = value_at(semantic, "$defs", "compatible_change_effect")
    if not isinstance(compatible_def, dict) or not isinstance(effect_def, dict):
        errors.append("semantic_compatible_change_definition_missing")
    affected_enum = set(value_at(effect_def, "properties", "affected_levels", "items", "enum") or [])
    forbidden_prefix = {
        "scope", "problem_definition", "evidence_plan", "candidate_set",
        "model_spec", "selection_rationale",
    }
    if affected_enum & forbidden_prefix:
        errors.append("compatible_change_can_invalidate_model_contract_prefix")
    actions = value_at(route, "action_contracts", "RT.PROJECT.COMPATIBLE_CHANGE")
    if not isinstance(actions, dict) or set(actions) != {
        "propagate_compatible", "reconcile_compatible",
    }:
        errors.append("compatible_change_action_contract_missing")
    else:
        g1 = actions["propagate_compatible"]
        g2 = actions["reconcile_compatible"]
        if (
            g1.get("minimum_tier") != "G1_WORKING"
            or g1.get("maximum_tier") != "G1_WORKING"
            or g1.get("required_mode") != "mutate"
        ):
            errors.append("compatible_change_g1_boundary_invalid")
        if (
            g2.get("minimum_tier") != "G2_CHECKPOINT"
            or g2.get("maximum_tier") != "G2_CHECKPOINT"
            or g2.get("required_mode") != "promote"
            or g2.get("requires_state_effect") is True
        ):
            errors.append("compatible_change_g2_boundary_invalid")
    policy = runtime.get("compatible_cross_component_change", {})
    if (
        value_at(policy, "g1", "state_mutation") != "none"
        or value_at(policy, "g1", "persistent_evidence") != "none"
        or value_at(policy, "g2", "execution_envelopes") != 1
        or value_at(policy, "g2", "identity_checkpoints") != 1
    ):
        errors.append("compatible_change_proportional_runtime_invalid")
    overlay = machine.get("compatible_change_overlay", {})
    if (
        overlay.get("lifecycle_effect") != "preserve_each_component_state"
        or overlay.get("failure")
        != "reject_the_atomic_bundle_without_partial_commit_and_reopen_at_the_earliest_actually_changed_layer"
    ):
        errors.append("compatible_change_state_overlay_invalid")
    execution_properties = value_at(state_schema, "$defs", "execution", "properties") or {}
    for field in (
        "compatible_change", "component_states", "component_snapshots",
        "compatible_change_reconciled_revision", "execution_receipt_sha256",
    ):
        if field not in execution_properties:
            errors.append("compatible_execution_field_missing:" + field)
    if bundle.get("properties", {}).get("schema_version", {}).get("const") != SCHEMA_VERSION:
        errors.append("compatible_bundle_schema_identity_invalid")
    claim_updates = bundle.get("properties", {}).get("claim_updates")
    if (
        "claim_updates" in bundle.get("required", [])
        or not isinstance(claim_updates, dict)
        or claim_updates.get("type") != "array"
        or set(value_at(claim_updates, "items", "required") or [])
        != {"claim_id", "expected_old_identity", "new_identity"}
    ):
        errors.append("compatible_optional_claim_update_contract_invalid")
    manager_source = (root / "scripts/state_manager.py").read_text(encoding="utf-8")
    resolver_source = (root / "scripts/lib_v11.py").read_text(encoding="utf-8")
    recovery_source = (root / "scripts/recovery_v14.py").read_text(encoding="utf-8")
    if "reconcile-compatible-change" not in manager_source or "deepcopy(original)" not in manager_source:
        errors.append("atomic_reconciliation_entry_missing")
    if "compatible_change" not in recovery_source or '"identity" if compatible_change' not in recovery_source:
        errors.append("compatible_targeted_recovery_branch_missing")
    for required_guard in (
        "compatible bundle omitted registered identity delta",
        "compatible change frozen contract identity changed",
        "changed path reaches undeclared or preserved evidence",
        "exact evidence identity delta lies outside sealed ChangeSet",
        "compatible replacement locator lies outside sealed ChangeSet",
        "changed claim reaches undeclared or preserved evidence",
        "compatible claim consumer replacement does not bind new identity",
        "changed claim has undeclared, preserved, or conflicting producer",
        "compatible change cannot hide component validity drift",
        "compatible change execution state advanced before reconciliation",
    ):
        if required_guard not in manager_source:
            errors.append("compatible_closed_world_guard_missing:" + required_guard)
    if "compatible_change_changeset_facet_mismatch" not in resolver_source:
        errors.append("compatible_facet_closed_world_missing")
    if "compatible_change_recovery_closure_mismatch" not in resolver_source:
        errors.append("compatible_recovery_closure_guard_missing")
    if "source_component" not in recovery_source or "E2_NUMERICAL" not in recovery_source:
        errors.append("compatible_source_recovery_anchor_missing")
    return {
        "affected_post_spec_levels": len(affected_enum),
        "g2_execution_envelopes": value_at(policy, "g2", "execution_envelopes"),
        "g2_identity_checkpoints": value_at(policy, "g2", "identity_checkpoints"),
        "closed_world_guards": 12,
    }, errors


def validate_recovery_contract(root: Path) -> tuple[dict[str, Any], list[str]]:
    """Validate the structured R0/R1/R2 contract, not Python source tokens."""
    errors: list[str] = []
    runtime = load(root, "references/runtime-policy.json")
    state_schema = load(root, "references/state.schema.json")
    receipt = load(root, "references/recovery-receipt.schema.json")
    governance = load(root, "rules/governance.json")
    policy = runtime.get("window_recovery_policy", {})

    precedence = policy.get("classification_precedence", [])
    if (
        not isinstance(precedence, list)
        or len(precedence) != 6
        or precedence[-1] != "R2_FULL_for_every_remaining_case"
    ):
        errors.append("recovery_classification_precedence_invalid")
    expected_same_window = {
        "same_uninterrupted_session",
        "current_context_has_direct_continuity",
        "current_checkpoint_identity_is_valid",
        "every_relevant_change_since_the_checkpoint_is_recorded_in_the_current_ChangeSet",
        "invalidation_propagation_is_complete",
        "no_unexplained_external_change_exists",
    }
    if set(policy.get("same_window_requires", [])) != expected_same_window:
        errors.append("r0_same_window_proof_contract_invalid")
    r0 = policy.get("r0_protocol", {})
    if (
        r0.get("recovery_episode") != "none"
        or r0.get("receipt") != "none"
        or r0.get("allows_recorded_workspace_delta") is not True
        or r0.get("unexplained_delta_must_be_empty") is not True
    ):
        errors.append("r0_proportional_protocol_invalid")

    eligibility = policy.get("r1_eligibility", {})
    expected_r1_proofs = {
        "workspace_baseline_is_trusted_current_and_complete_for_the_live_project",
        "every_relevant_added_changed_or_deleted_object_is_localizable_to_a_semantic_owner",
        "the_dependency_identity_is_current_and_the_complete_transitive_consumer_closure_is_provable",
    }
    if (
        set(eligibility.get("all_required", [])) != expected_r1_proofs
        or eligibility.get("unknown_or_false_disposition") != "R2_FULL"
        or eligibility.get("scope_escape_during_reading")
        != "upgrade_the_same_recovery_episode_to_R2_FULL"
    ):
        errors.append("r1_eligibility_contract_invalid")

    baseline = policy.get("baseline_contract", {})
    expected_baseline_bindings = {
        "root_fingerprint", "coverage_roots", "coverage_complete",
        "manifest_sha256", "inventory_policy_sha256", "captured_revision",
        "component_graph_sha256", "artifact_registry_sha256",
        "established_by", "file_count", "unresolved",
        "continuity_change_set",
    }
    if (
        set(baseline.get("required_bindings", [])) != expected_baseline_bindings
        or baseline.get("watch_roots_role") != "performance_hint_only"
        or baseline.get("legacy_or_partial_baseline")
        != "readable_as_navigation_but_ineligible_for_R1"
    ):
        errors.append("trusted_baseline_contract_invalid")

    episode = policy.get("episode_protocol", {})
    if (
        episode.get("recovery_ids") != 1
        or episode.get("consolidated_receipts") != 1
        or episode.get("forbid_nested_episode_per_component_file_consumer_or_gate")
        is not True
        or episode.get("r1_to_r2_escalation")
        != "retain_the_same_recovery_id_and_reuse_fully_read_entries_whose_identity_is_unchanged"
        or set(episode.get("closure_states", []))
        != {"closed_ready", "closed_blocked"}
        or episode.get("formal_execution_requires")
        != "same_plan_step_scope_revision_and_closed_ready_episode"
    ):
        errors.append("single_recovery_episode_contract_invalid")

    r2 = policy.get("r2_protocol", {})
    expected_r2_coverage = {
        "enumerate_and_classify_every_live_object",
        "read_every_unique_text_code_and_configuration_object_to_EOF",
        "inspect_Office_PDF_image_dataset_and_other_binary_objects_with_their_native_structured_or_visual_carrier",
        "represent_duplicates_by_hash_and_a_fully_read_canonical_object",
        "leave_no_missing_truncated_or_unclassified_live_object",
    }
    if (
        r2.get("scope") != "the_entire_live_project"
        or set(r2.get("required_coverage", [])) != expected_r2_coverage
        or r2.get("receipt") != "references/recovery-receipt.schema.json"
    ):
        errors.append("r2_full_read_contract_invalid")

    atoms = {
        item.get("id"): item
        for item in governance.get("rules", [])
        if isinstance(item, dict)
    }
    required_atoms = {
        "REC.R0.CONTINUE",
        "REC.R1.ELIGIBILITY",
        "REC.R1.TRANSITIVE",
        "REC.R2.FULL",
        "REC.R2.FULL_READ",
        "REC.R2.EVIDENCE_REBUILD",
    }
    if not required_atoms.issubset(atoms):
        errors.append("recovery_atom_inventory_incomplete")
    transitive_effect = value_at(atoms.get("REC.R1.TRANSITIVE", {}), "effect") or {}
    if (
        transitive_effect.get("verb") != "require"
        or transitive_effect.get("target") != "recovery_consumer_closure"
        or transitive_effect.get("value")
        != "changed_owner_plus_all_transitive_consumers"
    ):
        errors.append("recovery_invalidation_not_separated_from_changeset")
    full_read_effect = value_at(atoms.get("REC.R2.FULL_READ", {}), "effect") or {}
    if (
        full_read_effect.get("verb") != "require"
        or full_read_effect.get("target") != "full_project_read_coverage"
    ):
        errors.append("r2_full_read_atom_invalid")

    state_properties = state_schema.get("properties", {})
    meta_schema = value_at(state_schema, "$defs", "workspace_baseline_meta") or {}
    expected_meta_fields = {
        "root_fingerprint", "coverage_roots", "coverage_complete",
        "manifest_sha256", "inventory_policy_sha256", "captured_revision",
        "component_graph_sha256",
        "artifact_registry_sha256", "established_by", "file_count",
        "unresolved", "continuity_change_set",
    }
    if set(meta_schema.get("required", [])) != expected_meta_fields:
        errors.append("workspace_baseline_meta_contract_invalid")

    recovery_def = value_at(state_schema, "$defs", "recovery") or {}
    recovery_properties = recovery_def.get("properties", {})
    recovery_level_schema = recovery_properties.get("recovery_level", {})
    if set(recovery_level_schema.get("enum", [])) != {"R1_TARGETED", "R2_FULL"}:
        errors.append("state_recovery_level_contract_invalid")
    for field in (
        "initial_recovery_level", "escalated_from", "escalation_history",
        "decision_id",
        "full_manifest_path", "full_manifest_sha256", "full_manifest_counts",
    ):
        if field not in recovery_properties:
            errors.append("state_recovery_binding_missing:" + field)

    receipt_defs = receipt.get("$defs", {})
    receipt_refs = {
        item.get("$ref") for item in receipt.get("oneOf", [])
        if isinstance(item, dict)
    }
    if receipt_refs != {"#/$defs/r1_receipt", "#/$defs/r2_receipt"}:
        errors.append("recovery_receipt_level_union_invalid")
    r1_receipt = receipt_defs.get("r1_receipt", {})
    r2_receipt = receipt_defs.get("r2_receipt", {})
    if value_at(r1_receipt, "properties", "receipt_type", "const") != "r1_targeted_recovery":
        errors.append("r1_recovery_receipt_identity_invalid")
    if value_at(r2_receipt, "properties", "receipt_type", "const") != "r2_full_recovery":
        errors.append("r2_recovery_receipt_identity_invalid")
    for field in (
        "full_manifest_path", "full_manifest_sha256", "full_manifest_counts",
        "changed_paths", "affected_components", "conclusion",
    ):
        if field not in r2_receipt.get("properties", {}):
            errors.append("r2_recovery_receipt_binding_missing:" + field)
    counts = receipt_defs.get("full_manifest_counts", {}).get("properties", {})
    expected_count_fields = {
        "inventory_file_count", "canonical_item_count",
        "completed_canonical_count", "classified_canonical_count",
        "unresolved_count",
    }
    if set(counts) != expected_count_fields:
        errors.append("recovery_full_manifest_counts_invalid")

    return {
        "classification_branches": len(precedence) if isinstance(precedence, list) else 0,
        "same_window_proofs": len(expected_same_window),
        "r1_eligibility_proofs": len(expected_r1_proofs),
        "r2_coverage_obligations": len(expected_r2_coverage),
        "recovery_atoms": len(required_atoms & set(atoms)),
        "baseline_meta_fields": len(expected_meta_fields),
        "full_manifest_count_fields": len(expected_count_fields),
    }, errors


def validate_teammate_brief_contract(root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    modeling = load(root, "rules/modeling.json")
    route = load(root, "references/route-contract.json")
    rules = {
        item.get("id"): item
        for item in modeling.get("rules", [])
        if isinstance(item, dict)
    }
    rule = rules.get("MOD.RESULTS.TEAMMATE_BRIEF")
    if not isinstance(rule, dict):
        return {}, ["teammate_brief_rule_missing"]
    if (
        rule.get("revision") != 3
        or set(value_at(rule, "scope", "objects") or []) != {"model", "verification"}
        or value_at(rule, "scope", "component_types") != ["question"]
        or set(value_at(rule, "trigger", "events") or [])
        != {"teammate_brief_write", "s6_close"}
        or set(rule.get("routes", []))
        != {"RT.MODEL.RESULTS", "RT.VERIFY.S6.CLOSE"}
    ):
        errors.append("teammate_brief_rule_activation_invalid")
    if value_at(rule, "effect", "value") != (
        "canonical_per_question_ten_section_modeling_brief_current_at_s6_human_review"
    ):
        errors.append("teammate_brief_effect_invalid")
    expected_fields = {
        "canonical_path",
        "ten_section_responsibility_chain",
        "current_spec_result_and_verification_binding",
        "formula_local_explanation",
        "result_mechanism_and_claim_boundary",
        "main_brief_and_optional_sidecar_separation",
        "reviewed_file_identity",
        "human_read_and_restatement_decision",
    }
    if set(value_at(rule, "evidence", "fields") or []) != expected_fields:
        errors.append("teammate_brief_evidence_fields_invalid")

    action = value_at(
        route, "action_contracts", "RT.MODEL.RESULTS", "prepare_teammate_brief"
    )
    if (
        not isinstance(action, dict)
        or action.get("minimum_tier") != "G1_WORKING"
        or action.get("maximum_tier") != "G1_WORKING"
        or action.get("required_mode") != "mutate"
        or action.get("component_id_must_be_non_null") is not True
        or action.get("allowed_change_path_prefixes") != ["docs/"]
        or action.get("required_change_path_templates")
        != ["docs/{component_id}/solution_brief.md"]
    ):
        errors.append("teammate_brief_g1_path_contract_invalid")
    routes = {
        item.get("id"): item
        for item in route.get("routes", [])
        if isinstance(item, dict)
    }
    close_route = routes.get("RT.VERIFY.S6.CLOSE", {})
    close_refs = {
        item.get("ref")
        for item in close_route.get("context_refs", [])
        if isinstance(item, dict)
    }
    if "references/modeling-method-notes.md#results" not in close_refs:
        errors.append("s6_close_teammate_brief_method_route_missing")

    packet = (
        root / "references/capability-packets/modeling/implementation-solving-and-results.md"
    ).read_text(encoding="utf-8")
    required_packet_fragments = [
        "docs/<task-id>/solution_brief.md",
        "## 1 问题重述",
        "## 5 模型建立",
        "## 6 模型求解",
        "## 8 模型检验与敏感性分析",
        "## 10 问题X结论",
        "S6→S7",
        "关闭证据记录被审文件 identity",
        "不设“贯穿全文定位”",
        "不另堆“安全声明”",
        "一条可解释的正式求解链",
    ]
    missing_fragments = [item for item in required_packet_fragments if item not in packet]
    if missing_fragments:
        errors.append(
            "teammate_brief_packet_responsibility_missing:" + ",".join(missing_fragments)
        )
    if "九项语义覆盖" in packet or "不强制固定文件名" in packet:
        errors.append("retired_teammate_brief_format_still_active")
    resolver_source = (root / "scripts/lib_v11.py").read_text(encoding="utf-8")
    if (
        "required_change_path_templates" not in resolver_source
        or "action_required_change_path_missing" not in resolver_source
    ):
        errors.append("canonical_brief_path_enforcement_missing")
    return {
        "rule_revision": rule.get("revision"),
        "evidence_fields": len(expected_fields),
        "canonical_path_template": (
            action.get("required_change_path_templates", [None])[0]
            if isinstance(action, dict)
            else None
        ),
        "s6_method_refs": len(close_refs),
    }, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = base.skill_root(args.root)
    errors: list[str] = []
    evidence: dict[str, Any] = {}
    try:
        release_metrics, release_errors = validate_release_binding(root)
        evidence["release"] = release_metrics
        errors.extend("CONTRACT.V16.RELEASE_BINDING:" + item for item in release_errors)
        required_cases = set(load(root, "references/release-policy.json").get("required_case_ids", []))
        base_metrics, base_errors = validate_base(root, required_cases)
        evidence["base"] = base_metrics
        errors.extend("CONTRACT.V16.BASE_PRESERVATION:" + item for item in base_errors)
        compatible_metrics, compatible_errors = validate_compatible_contract(root)
        evidence["compatible_change"] = compatible_metrics
        errors.extend("CONTRACT.V16.COMPATIBLE_CHANGE_BINDING:" + item for item in compatible_errors)
        recovery_metrics, recovery_errors = validate_recovery_contract(root)
        evidence["recovery"] = recovery_metrics
        errors.extend("CONTRACT.V16.RECOVERY_BOUNDARY:" + item for item in recovery_errors)
        teammate_metrics, teammate_errors = validate_teammate_brief_contract(root)
        evidence["teammate_brief"] = teammate_metrics
        errors.extend("CONTRACT.V16.TEAMMATE_BRIEF_STANDARD:" + item for item in teammate_errors)
    except Exception as exc:
        errors.append(f"CONTRACT.V16.INTERNAL:{type(exc).__name__}:{exc}")
    result = {
        "schema_version": RELEASE_SCHEMA_VERSION, "driver": "contracts",
        "status": "pass" if not errors else "fail", "checks": CHECKS,
        "evidence": evidence, "errors": sorted(set(errors)),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
