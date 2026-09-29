#!/usr/bin/env python3
"""Validate V15 current contracts, reachability, and reviewed preservation seals."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # reported as a release-contract failure below
    Draft202012Validator = None  # type: ignore[assignment,misc]
    FormatChecker = None  # type: ignore[assignment,misc]


SCHEMA_VERSION = "15.0"
RELEASE_ID = "V15.0.1"
CLAUSE_REVIEW_RELEASE = "V16.0.0-candidate"
TIERS = ("G0_ADVISORY", "G1_WORKING", "G2_CHECKPOINT", "G3_RELEASE")
TIER_RANK = {tier: index for index, tier in enumerate(TIERS)}
MODES = {
    "advisory_readonly", "project_readonly", "mutate", "promote", "skill_maintenance"
}
ROUTE_SELECTORS = {"*", "@write", "@recovery"}
CHECK_IDS = {
    "PACKAGE.V15.REQUIRED", "PACKAGE.V15.JSON", "PACKAGE.V15.PYTHON",
    "PACKAGE.V15.IDENTITY_AND_LINKS", "CONTRACT.V15.RELEASE_BINDING",
    "CONTRACT.V15.CONTROL_BINDINGS", "CONTRACT.V15.ATOM_INVENTORY",
    "CONTRACT.V15.ROUTE_REACHABILITY", "CONTRACT.V15.CAPABILITY_PACKET_REACHABILITY",
    "CONTRACT.V15.RUNTIME_NEAR_NEGATIVES", "MIGRATION.V15.CLAUSE_PRESERVATION",
}
DOCUMENTS = {
    "runtime": "references/runtime-policy.json",
    "route": "references/route-contract.json",
    "artifact": "references/artifact-contract.json",
    "project_platform": "references/project-platform-contract.json",
    "state_machine": "references/state-machine.json",
    "manuscript": "references/manuscript-change-closure.json",
    "receipt": "references/receipt.schema.json",
}
LINK_RE = re.compile(r"\]\(([^)#]+)(?:#[^)]+)?\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
CANONICAL_IDENTITY_PATH_PATTERN = (
    r"^(?!/)(?![A-Za-z]:)(?!.*\u0000)(?!.*\\)(?!.*//)"
    r"(?!.*(?:^|/)\.{1,2}(?:/|$))[^/]+(?:/[^/]+)*$"
)


POLICY_MUTATIONS: tuple[tuple[str, str, tuple[str, ...], Any, str], ...] = (
    ("POLICY.NO_RAW_KEYWORD_ROUTER", "route", ("selection_policy", "raw_request_classification"), True, "raw_request_machine_classification_enabled"),
    ("POLICY.NO_EVENT_BROADCAST", "route", ("event_policy", "broadcast"), True, "route_event_broadcast_enabled"),
    ("POLICY.NO_GLOBAL_MODE", "route", ("selection_policy", "single_global_mode"), True, "single_global_mode_enabled"),
    ("POLICY.DEPENDENCY_LOCAL", "route", ("selection_policy", "dependency_policy"), "block_entire_plan", "dependency_policy_not_branch_local"),
    ("POLICY.G0.STATELESS", "runtime", ("tiers", "G0_ADVISORY", "project_state"), "required", "g0_project_state_required"),
    ("POLICY.G1.NO_MANIFEST", "runtime", ("tiers", "G1_WORKING", "identity_check_scope"), "registered_checkpoint_identities_only", "g1_identity_scope_expanded"),
    ("POLICY.G1.NO_FORMAL_RECEIPT", "runtime", ("tiers", "G1_WORKING", "receipt"), "start_end_receipts", "g1_formal_receipt_enabled"),
    ("POLICY.G1.MULTIFILE", "runtime", ("tiers", "G1_WORKING", "multi_file_changes"), False, "g1_multifile_disabled"),
    ("POLICY.NATURAL_LANGUAGE", "runtime", ("activation", "standard_vocabulary_role"), "user_required", "internal_vocabulary_made_user_gate"),
    ("POLICY.INDEPENDENT_STEPS_CONTINUE", "runtime", ("activation", "independent_step_policy"), "block_entire_plan", "independent_steps_globally_blocked"),
    ("POLICY.NEW_ARTIFACT_NO_INVALIDATION", "artifact", ("policy", "registration_rule"), "invalidate_producer_and_consumers", "new_registration_can_invalidate"),
    ("POLICY.ARTIFACT.CANONICAL.PATH", "artifact", ("properties", "path", "pattern"), r"^(?!/).+$", "artifact_canonical_path_boundary_invalid"),
    ("POLICY.WORKING.IDENTITY.LOCAL", "state_machine", ("invalidation", "on_working_identity_change"), "invalidate_all_transitive_consumers", "working_identity_can_invalidate_components"),
    ("POLICY.NO_UPSTREAM_REBIND", "state_machine", ("invalidation", "upstream_rebinding"), "always_rebind_upstream", "upstream_rebinding_enabled"),
    ("POLICY.MANUSCRIPT.MULTIFILE", "manuscript", ("global_invariants", "one_file_at_a_time_forbidden"), False, "manuscript_single_file_gate_enabled"),
    ("POLICY.MANUSCRIPT.NO_RULE_WEAKEN", "manuscript", ("global_invariants", "normative_strength_does_not_imply_per_turn_evidence"), False, "normative_strength_recoupled_to_runtime_burden"),
    ("POLICY.ACTION.IMPLEMENT.CORE_EVENT", "route", ("action_contracts", "RT.MODEL.IMPLEMENT", "implement", "required_all_events"), ["result_record"], "implement_core_event_not_exact"),
    ("POLICY.S6.NO_VERIFICATION_REPLAY", "route", ("action_contracts", "RT.VERIFY.S6.CLOSE", "close_s6", "required_all_events"), ["s6_readiness", "s6_close", "implementation_verification"], "s6_close_replays_readiness_or_verification"),
    ("POLICY.DELIVERY.G3.MINIMUM", "route", ("action_contracts", "RT.DELIVERY.FINAL", "deliver", "minimum_tier"), "G2_CHECKPOINT", "delivery_minimum_tier_not_g3"),
    ("POLICY.SKILL_RELEASE.G3.MINIMUM", "route", ("action_contracts", "RT.SKILL.CHANGE", "release", "minimum_tier"), "G1_WORKING", "skill_release_minimum_tier_not_g3"),
    ("POLICY.CONTROLLER.EVENTS.INTERNAL", "route", ("event_prerequisites", "controller_only_events"), ["request_received", "route_resolution", "route_execution", "before_write"], "controller_events_user_declarable"),
    ("POLICY.MAINTENANCE.V10_SCOPE.ADAPTER", "route", ("legacy_scope_adapters", "skill_state", "actual_state"), "V10", "maintenance_scope_adapter_missing"),
    ("POLICY.DATA.ACTUAL_USE.ADAPTER", "route", ("legacy_trigger_adapters", "DATA.IDENTITY.BEFORE_USE", "when_fact_true"), None, "data_use_trigger_adapter_missing"),
    ("POLICY.MANUSCRIPT.MULTIFILE.MINIMUM", "manuscript", ("closures", "multi_file_substantive", "change_set_constraints", "minimum_paths"), 1, "manuscript_multifile_minimum_missing"),
    ("POLICY.MANUSCRIPT.RULE_COUNT.TELEMETRY_ONLY", "manuscript", ("closures", "typo", "rule_count_telemetry", "runtime_effect"), "hard_block", "manuscript_rule_count_runtime_gate:typo"),
    ("POLICY.RULE.DELIVERY.COMPACT", "route", ("selection_policy", "rule_delivery"), "full_frozen_envelopes_every_step", "runtime_rule_delivery_not_compact"),
    ("POLICY.PAUSE.G1.CEILING", "route", ("action_contracts", "RT.PROJECT.RESUME", "pause", "maximum_tier"), "G3_RELEASE", "pause_g1_ceiling_missing"),
    ("POLICY.PAUSE.NO.DANGEROUS.DERIVATION", "route", ("runtime_action_policy", "non_derivation_actions"), ["resume", "recover", "handoff", "close_s6"], "control_action_can_derive_dangerous_command"),
    ("POLICY.RUNTIME.GUARD.NOT.ORDINARY.G1", "route", ("runtime_action_policy", "ordinary_work_requires_runtime_action"), True, "dangerous_guard_expanded_to_ordinary_work"),
    ("POLICY.SKILL.PACKAGE.ISOLATED", "route", ("runtime_action_policy", "skill_package_boundary", "object"), "project", "skill_package_boundary_not_isolated"),
    ("POLICY.MULTISTEP.NO.SECOND.COMMAND", "runtime", ("decomposed_request_semantics", "multi_step_continuation"), "", "multi_step_continuation_removed"),
    ("POLICY.R2.NO.RECOMPUTATION", "runtime", ("recovery_execution_barrier", "identity_reconstruction", "recomputation_authorized"), True, "r2_recomputation_implicitly_authorized"),
    ("POLICY.R2.BLOCKS.MODEL.EXECUTION", "runtime", ("recovery_execution_barrier", "blocked_events"), ["manuscript_write", "final_delivery"], "r2_execution_barrier_incomplete"),
    ("POLICY.RUNTIME.NO.G1.LEDGER", "runtime", ("dangerous_runtime_actions", "grant_persistence_at_g1"), "state_ledger", "dangerous_guard_became_g1_ledger"),
    ("POLICY.NEW_WINDOW.MINIMUM_R1", "runtime", ("window_recovery_policy", "new_window_minimum_level"), "R0_CONTINUE", "new_window_minimum_not_r1"),
    ("POLICY.PLATFORM.TRANSIENT.NOT_RETAINED", "project_platform", ("path_namespaces", "tool_managed_transient", "retained_change_set"), "allowed", "project_platform_transient_boundary_invalid"),
    ("POLICY.PLATFORM.CANONICAL.RAW", "project_platform", ("path_syntax", "comparison"), "resolve_then_compare", "project_platform_path_syntax_invalid"),
    ("POLICY.PLATFORM.PHYSICAL.ALIAS", "project_platform", ("path_syntax", "physical_alias_policy", "unordered_steps_distinct_paths_one_target"), "allowed", "project_platform_physical_alias_policy_invalid"),
    ("POLICY.ARTIFACT.ADMISSION.FIRST_ONLY", "route", ("event_policy", "controller_events", "formal_artifact_events"), ["artifact_register", "artifact_refresh", "artifact_promotion"], "formal_artifact_controller_boundary_invalid"),
)


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_seal(label: str, value: Any, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label}:not_object")
        return
    claimed = value.get("payload_sha256")
    unsigned = {key: item for key, item in value.items() if key != "payload_sha256"}
    if not isinstance(claimed, str) or HEX64_RE.fullmatch(claimed) is None:
        errors.append(f"{label}:seal_missing")
    elif claimed != canonical_sha256(unsigned):
        errors.append(f"{label}:seal_mismatch")


def markdown_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    for heading in HEADING_RE.findall(text):
        plain = re.sub(r"[`*_~]", "", heading).strip().lower()
        plain = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", plain)
        anchors.add(re.sub(r"-+", "-", plain.replace(" ", "-")))
    return anchors


def reference_exists(root: Path, reference: Any) -> bool:
    if not isinstance(reference, str) or not reference:
        return False
    path_text, _, anchor = reference.partition("#")
    if "*" in path_text:
        return bool(list(root.glob(path_text)))
    path = root / path_text
    if not path.is_file():
        return False
    if anchor and path.suffix.lower() == ".md":
        return anchor.lower() in markdown_anchors(path.read_text(encoding="utf-8"))
    return True


def referenced_json_value(root: Path, reference: Any) -> Any | None:
    if not isinstance(reference, str) or not reference or "#" not in reference:
        return None
    path_text, fragment = reference.split("#", 1)
    relative = Path(path_text)
    candidate = (root / relative).resolve()
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or root.resolve() not in candidate.parents
        or not candidate.is_file()
        or candidate.suffix.lower() != ".json"
        or not fragment
    ):
        return None
    try:
        value: Any = load(candidate)
    except Exception:
        return None
    for token in fragment.strip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            return None
        value = value[token]
    return value


def set_path(document: Any, path: tuple[str, ...], value: Any) -> None:
    current = document
    for key in path[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise KeyError("/".join(path))
        current = current[key]
    if not isinstance(current, dict) or not path:
        raise KeyError("/".join(path))
    current[path[-1]] = value


def runtime_boundary_errors(documents: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    runtime = documents["runtime"]
    route = documents["route"]
    artifact = documents["artifact"]
    project_platform = documents["project_platform"]
    state_machine = documents["state_machine"]
    manuscript = documents["manuscript"]
    receipt = documents["receipt"]

    selection = route.get("selection_policy", {})
    if selection.get("raw_request_classification") is not False:
        errors.append("raw_request_machine_classification_enabled")
    if selection.get("single_global_mode") is not False:
        errors.append("single_global_mode_enabled")
    if selection.get("rule_delivery") != "deduplicated_runtime_semantic_projections_once":
        errors.append("runtime_rule_delivery_not_compact")
    if selection.get("dependency_policy") != "block_descendants_only":
        errors.append("dependency_policy_not_branch_local")
    if route.get("event_policy", {}).get("broadcast") is not False:
        errors.append("route_event_broadcast_enabled")
    actions = route.get("action_contracts", {})
    if actions.get("RT.MODEL.IMPLEMENT", {}).get("implement", {}).get("required_all_events") != ["model_implementation"]:
        errors.append("implement_core_event_not_exact")
    if actions.get("RT.VERIFY.S6.CLOSE", {}).get("close_s6", {}).get("required_all_events") != ["s6_close"]:
        errors.append("s6_close_replays_readiness_or_verification")
    if any(item.get("minimum_tier") != "G3_RELEASE" for item in actions.get("RT.DELIVERY.FINAL", {}).values()):
        errors.append("delivery_minimum_tier_not_g3")
    if actions.get("RT.SKILL.CHANGE", {}).get("release", {}).get("minimum_tier") != "G3_RELEASE":
        errors.append("skill_release_minimum_tier_not_g3")
    pause = actions.get("RT.PROJECT.RESUME", {}).get("pause", {})
    if (
        pause.get("minimum_tier") != "G1_WORKING"
        or pause.get("maximum_tier") != "G1_WORKING"
        or pause.get("required_mode") != "mutate"
        or pause.get("required_all_events") != ["handoff"]
    ):
        errors.append("pause_g1_ceiling_missing")
    runtime_actions = route.get("runtime_action_policy", {})
    if runtime_actions.get("ordinary_work_requires_runtime_action") is not False:
        errors.append("dangerous_guard_expanded_to_ordinary_work")
    skill_boundary = runtime_actions.get("skill_package_boundary", {})
    if (
        skill_boundary.get("object") != "skill"
        or skill_boundary.get("tier") != "G3_RELEASE"
        or skill_boundary.get("scope_kind") != "skill_candidate"
        or skill_boundary.get("change_set_admission")
        != "relative_paths_within_candidate_root_not_project_platform_roles"
    ):
        errors.append("skill_package_boundary_not_isolated")
    platform_applicability = project_platform.get("applicability", {})
    if (
        platform_applicability.get("object") != "project"
        or platform_applicability.get("skill_candidate_packages")
        != "excluded_and_governed_by_route_contract_skill_package_boundary"
    ):
        errors.append("project_platform_scope_expanded_to_skill_candidate")
    path_syntax = project_platform.get("path_syntax", {})
    if (
        path_syntax.get("form") != "canonical_relative_posix"
        or set(path_syntax.get("forbidden_aliases", [])) != {
            "absolute", "drive_prefixed", "backslash", "dot_segment",
            "dotdot_segment", "empty_segment", "trailing_slash",
        }
        or path_syntax.get("comparison")
        != "validate_raw_equals_PurePosixPath_raw_as_posix_before_containment_or_conflict_checks"
    ):
        errors.append("project_platform_path_syntax_invalid")
    physical_alias_policy = path_syntax.get("physical_alias_policy", {})
    if (
        path_syntax.get("lexical_conflict_key") != "canonical_relative_posix_path"
        or path_syntax.get("physical_conflict_key")
        != "project_root_join_canonical_path_resolve_strict_false_then_relative_to_resolved_project_root"
        or physical_alias_policy != {
            "single_internal_symlink_path": (
                "allowed_if_the_resolved_target_remains_inside_project_root"
            ),
            "same_step_distinct_paths_one_target": "blocked",
            "unordered_steps_distinct_paths_one_target": "blocked_for_both_steps",
            "ordered_steps": "dependency_order_preserves_existing_sequential_write_semantics",
            "external_symlink": "blocked_by_project_root_containment",
            "inspection_scope": "only_declared_change_set_paths_no_project_wide_scan",
        }
    ):
        errors.append("project_platform_physical_alias_policy_invalid")
    platform_namespaces = project_platform.get("path_namespaces", {})
    canonical_namespace = platform_namespaces.get("canonical_semantic", {})
    if canonical_namespace.get("overlapping_patterns") != (
        "allowed_at_g1_and_resolved_only_when_a_formal_artifact_explicitly_selects_its_semantic_role"
    ):
        errors.append("project_platform_g1_role_overlap_forbidden")
    if (
        canonical_namespace.get("source") != "roles.*.path_patterns"
        or canonical_namespace.get("new_path_admission") != "one_or_more_role_path_patterns"
        or canonical_namespace.get("role_assignment_at_g1") is not False
    ):
        errors.append("project_platform_g1_namespace_policy_invalid")
    support_namespace = platform_namespaces.get("project_support", {})
    if (
        not support_namespace.get("path_patterns")
        or support_namespace.get("formal_artifact_role_inferred") is not False
    ):
        errors.append("project_platform_support_namespace_invalid")
    established_namespace = platform_namespaces.get("established_project", {})
    established_exclusions = set(established_namespace.get("excluded_top_levels", []))
    if (
        established_namespace.get("top_level_directory_must_already_exist") is not True
        or established_namespace.get("target_must_be_a_child_path") is not True
        or not {".modeling", ".git", ".hg", ".svn", ".codex", ".agents"}.issubset(
            established_exclusions
        )
    ):
        errors.append("project_platform_established_namespace_invalid")
    extension_namespace = platform_namespaces.get("manual_platform_extension", {})
    extension_shape = extension_namespace.get("fact_shape", {})
    if (
        extension_namespace.get("frequency")
        != "rare_architecture_boundary_not_an_ordinary_per_file_gate"
        or extension_namespace.get("fact") != "step.facts.platform_extension"
        or extension_shape.get("additional_properties") is not False
        or set(extension_shape.get("required", []))
        != {"approval_quote", "top_level_namespaces", "purpose", "rollback"}
        or extension_shape.get("approval_quote")
        != "trimmed_length_at_least_2_contains_nonwhitespace_and_is_an_exact_substring_of_plan.request"
        or extension_shape.get("top_level_namespaces")
        != "nonempty_unique_canonical_single_POSIX_top_level_names_only"
        or extension_shape.get("purpose") != "trimmed_length_at_least_8"
        or extension_shape.get("rollback") != "trimmed_length_at_least_8"
        or extension_namespace.get("scope")
        != "only_unknown_paths_in_the_same_step_whose_first_path_component_exactly_equals_an_approved_top_level_namespace"
        or extension_namespace.get("unused_fact")
        != "reject_to_prevent_stale_or_speculative_authorization"
        or set(extension_namespace.get("never_overrides", []))
        != {"reserved", "tool_managed_transient", "noncanonical_path"}
    ):
        errors.append("project_platform_extension_boundary_invalid")
    transient_namespace = platform_namespaces.get("tool_managed_transient", {})
    if (
        not transient_namespace.get("path_patterns")
        or transient_namespace.get("retained_change_set") != "forbidden"
        or transient_namespace.get("per_file_proposal_or_registration") != "forbidden"
        or transient_namespace.get("runtime_action_output_paths")
        != "exclude_unretained_cache_and_build_side_effects"
    ):
        errors.append("project_platform_transient_boundary_invalid")
    reserved_namespace = platform_namespaces.get("reserved", {})
    controller_allowlist = reserved_namespace.get("controller_path_allowlist", {})
    if (
        not reserved_namespace.get("repository_internal_patterns")
        or not reserved_namespace.get("controller_metadata_patterns")
        or reserved_namespace.get("established_namespace_admission") != "forbidden"
        or reserved_namespace.get("existing_path_grandfathering") != "forbidden"
        or controller_allowlist.get("always") != [".modeling/state.json"]
        or controller_allowlist.get("recovery_assessment_event_required_patterns")
        != [r"^\.modeling/recovery/[^/].*"]
    ):
        errors.append("project_platform_reserved_boundary_invalid")
    non_derivation = set(runtime_actions.get("non_derivation_actions", []))
    if not {"resume", "recover", "handoff", "pause", "close_s6"}.issubset(non_derivation):
        errors.append("control_action_can_derive_dangerous_command")
    controller_only = set(route.get("event_prerequisites", {}).get("controller_only_events", []))
    if not {"request_received", "route_resolution", "route_execution", "before_write", "before_file_creation"}.issubset(controller_only):
        errors.append("controller_events_user_declarable")
    controller_event_policy = route.get("event_policy", {}).get("controller_events", {})
    if (
        controller_event_policy.get("formal_artifact_events") != ["artifact_register"]
        or controller_event_policy.get("before_formal_artifact_admission")
        != ["before_file_creation"]
    ):
        errors.append("formal_artifact_controller_boundary_invalid")
    skill_adapter = route.get("legacy_scope_adapters", {}).get("skill_state", {})
    if skill_adapter.get("actual_state") != "V11" or skill_adapter.get("frozen_scope_token") != "V10":
        errors.append("maintenance_scope_adapter_missing")
    data_adapter = route.get("legacy_trigger_adapters", {}).get("DATA.IDENTITY.BEFORE_USE", {})
    if data_adapter.get("coarse_controller_event") != "route_execution" or data_adapter.get("when_fact_true") != "consumes_data":
        errors.append("data_use_trigger_adapter_missing")

    tiers = runtime.get("tiers", {})
    if tiers.get("G0_ADVISORY", {}).get("project_state") != "not_required":
        errors.append("g0_project_state_required")
    g1 = tiers.get("G1_WORKING", {})
    if g1.get("identity_check_scope") != "none":
        errors.append("g1_identity_scope_expanded")
    if g1.get("receipt") != "automatic_change_summary":
        errors.append("g1_formal_receipt_enabled")
    if g1.get("multi_file_changes") is not True:
        errors.append("g1_multifile_disabled")
    activation = runtime.get("activation", {})
    if activation.get("standard_vocabulary_role") != "internal_only":
        errors.append("internal_vocabulary_made_user_gate")
    if activation.get("independent_step_policy") != "unaffected ordered steps may continue":
        errors.append("independent_steps_globally_blocked")
    decomposed = runtime.get("decomposed_request_semantics", {})
    if not decomposed.get("multi_step_continuation") or not decomposed.get("no_one_step_gate"):
        errors.append("multi_step_continuation_removed")
    window_policy = runtime.get("window_recovery_policy", {})
    if window_policy.get("new_window_minimum_level") != "R1_TARGETED":
        errors.append("new_window_minimum_not_r1")
    if window_policy.get("unknown_default") != "new_window":
        errors.append("new_window_unknown_default_not_new_window")
    natural_pause = runtime.get("natural_pause", {})
    if natural_pause.get("tier") != "G1_WORKING" or natural_pause.get("does_not_imply") is None:
        errors.append("natural_pause_boundary_missing")
    barrier = runtime.get("recovery_execution_barrier", {})
    blocked = set(barrier.get("blocked_events", []))
    if not {
        "model_execution", "implementation_verification", "numerical_verification",
        "structural_verification", "reality_verification", "manuscript_write",
        "delivery_package_build", "final_delivery",
    }.issubset(blocked):
        errors.append("r2_execution_barrier_incomplete")
    if barrier.get("identity_reconstruction", {}).get("recomputation_authorized") is not False:
        errors.append("r2_recomputation_implicitly_authorized")
    if barrier.get("allowed_write_paths") != [".modeling/state.json"]:
        errors.append("r2_control_write_scope_expanded")
    dangerous = runtime.get("dangerous_runtime_actions", {})
    if dangerous.get("ordinary_g1_affected") is not False or dangerous.get("grant_persistence_at_g1") != "none":
        errors.append("dangerous_guard_became_g1_ledger")

    artifact_path = artifact.get("properties", {}).get("path", {})
    artifact_policy = artifact.get("policy", {})
    artifact_path_pattern = artifact_path.get("pattern")
    artifact_path_boundary_valid = (
        artifact_path.get("type") == "string"
        and artifact_path.get("minLength") == 1
        and artifact_path_pattern == CANONICAL_IDENTITY_PATH_PATTERN
        and artifact_policy.get("path_rule")
        == "canonical_relative_posix_raw_equals_PurePosixPath_as_posix_before_resolved_containment"
        and set(artifact_policy.get("path_forbidden_aliases", []))
        == {
            "absolute", "drive_prefixed", "backslash", "dot_segment",
            "dotdot_segment", "empty_segment", "trailing_slash", "nul",
        }
    )
    try:
        artifact_path_re = re.compile(str(artifact_path_pattern))
    except re.error:
        artifact_path_boundary_valid = False
        artifact_path_re = re.compile(r"(?!)")
    for witness in ("paper/main.tex", ".modeling/state.json", "setup.cfg"):
        if artifact_path_re.fullmatch(witness) is None:
            artifact_path_boundary_valid = False
    for witness in (
        "./paper/main.tex", "paper/./main.tex", "paper//main.tex",
        "paper/main.tex/", r"paper\main.tex", "/paper/main.tex",
        "C:/paper/main.tex", "paper/../main.tex", "paper/\x00main.tex",
    ):
        if artifact_path_re.fullmatch(witness) is not None:
            artifact_path_boundary_valid = False
    if not artifact_path_boundary_valid:
        errors.append("artifact_canonical_path_boundary_invalid")

    if artifact_policy.get("registration_rule") != "registering_a_new_identity_never_invalidates_prior_evidence":
        errors.append("new_registration_can_invalidate")
    invalidation = state_machine.get("invalidation", {})
    if invalidation.get("on_working_identity_change") != "stale_only_evidence_exactly_bound_to_old_identity":
        errors.append("working_identity_can_invalidate_components")
    if invalidation.get("upstream_rebinding") != "forbidden_unless_a_new_upstream_identity_or_claim_change_is_observed":
        errors.append("upstream_rebinding_enabled")

    invariants = manuscript.get("global_invariants", {})
    if invariants.get("one_file_at_a_time_forbidden") is not True:
        errors.append("manuscript_single_file_gate_enabled")
    if invariants.get("normative_strength_does_not_imply_per_turn_evidence") is not True:
        errors.append("normative_strength_recoupled_to_runtime_burden")
    if manuscript.get("change_set_policy", {}).get("path_count_limit", "missing") is not None:
        errors.append("manuscript_path_count_limit_enabled")
    if manuscript.get("closures", {}).get("multi_file_substantive", {}).get("change_set_constraints", {}).get("minimum_paths") != 2:
        errors.append("manuscript_multifile_minimum_missing")
    for name, closure in manuscript.get("closures", {}).items():
        if "exact_manuscript_rule_ids" in closure:
            errors.append(f"manuscript_rule_whitelist_present:{name}")
        telemetry = closure.get("rule_count_telemetry")
        if isinstance(telemetry, dict) and telemetry.get("runtime_effect") != "none":
            errors.append(f"manuscript_rule_count_runtime_gate:{name}")
    required_facets = {
        "method": "method_section_write", "result": "result_section_write",
        "conclusion": "conclusion_write", "structure": "manuscript_structure",
    }
    facet_map = manuscript.get("facet_to_legacy_event")
    if not isinstance(facet_map, dict) or any(facet_map.get(key) != value for key, value in required_facets.items()):
        errors.append("manuscript_facet_event_adapter_missing")
    if receipt.get("$defs", {}).get("tier", {}).get("enum") != ["G2_CHECKPOINT", "G3_RELEASE"]:
        errors.append("receipt_tier_scope_not_g2_g3")
    return sorted(set(errors))


def validate_runtime_near_negatives(root: Path) -> tuple[int, list[str]]:
    documents = {name: load(root / relative) for name, relative in DOCUMENTS.items()}
    errors = ["runtime_base:" + item for item in runtime_boundary_errors(documents)]
    ids = [item[0] for item in POLICY_MUTATIONS]
    if len(POLICY_MUTATIONS) != 39 or len(ids) != len(set(ids)):
        errors.append("runtime_mutation_inventory_invalid")
    passed = 0
    for identifier, document, path, value, expected_error in POLICY_MUTATIONS:
        mutated = copy.deepcopy(documents)
        try:
            set_path(mutated[document], path, value)
            observed = runtime_boundary_errors(mutated)
        except (KeyError, TypeError) as exc:
            errors.append(f"runtime_mutation_invalid:{identifier}:{exc}")
            continue
        if expected_error not in observed:
            errors.append(f"runtime_mutation_not_detected:{identifier}:{expected_error}")
        else:
            passed += 1
    return passed, errors


def string_list(value: Any, label: str, errors: list[str], *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{label}:must_be_string_array")
        return []
    if nonempty and not value:
        errors.append(f"{label}:must_not_be_empty")
    if len(value) != len(set(value)):
        errors.append(f"{label}:duplicates")
    return value


def minimum_tier(route: dict[str, Any], action: str, mode: str, runtime: dict[str, Any]) -> str:
    minimum = runtime.get("minimum_tiers", {})
    if route.get("id") == "RT.DELIVERY.FINAL":
        return minimum.get("final_delivery", "G3_RELEASE")
    if route.get("id") == "RT.SKILL.CHANGE" and action == "release":
        return minimum.get("skill_release", "G3_RELEASE")
    return minimum.get(mode, "G0_ADVISORY")


def action_is_feasible(
    route: dict[str, Any],
    action: str,
    details: dict[str, Any],
    contract: dict[str, Any],
    runtime: dict[str, Any],
) -> bool:
    prerequisites = contract.get("event_prerequisites", {}).get("events", {})
    tier_policy = contract.get("tier_policy", {})
    all_events = set(details.get("required_all_events", []))
    any_events = set(details.get("required_any_events", []))
    choices: list[str | None] = sorted(any_events) if any_events else [None]
    for mode in route.get("modes", []):
        required_mode = details.get("required_mode")
        if required_mode is not None and mode != required_mode:
            continue
        for choice in choices:
            events = set(all_events)
            if choice is not None:
                events.add(choice)
            minimum = minimum_tier(route, action, mode, runtime)
            maximum = details.get("maximum_tier")
            action_minimum = details.get("minimum_tier")
            if action_minimum in TIER_RANK and TIER_RANK[action_minimum] > TIER_RANK.get(minimum, 0):
                minimum = action_minimum
            compatible = True
            for event in events:
                requirement = prerequisites.get(event, {})
                event_mode = requirement.get("required_mode")
                if event_mode is not None and event_mode != mode:
                    compatible = False
                    break
                event_minimum = requirement.get("minimum_tier")
                if event_minimum in TIER_RANK and TIER_RANK[event_minimum] > TIER_RANK.get(minimum, 0):
                    minimum = event_minimum
                event_maximum = requirement.get("maximum_tier")
                if event_maximum in TIER_RANK and (
                    maximum not in TIER_RANK or TIER_RANK[event_maximum] < TIER_RANK[maximum]
                ):
                    maximum = event_maximum
            if not compatible or minimum not in TIER_RANK:
                continue
            for tier in TIERS:
                if mode not in tier_policy.get(tier, []):
                    continue
                if TIER_RANK[tier] < TIER_RANK[minimum]:
                    continue
                if maximum in TIER_RANK and TIER_RANK[tier] > TIER_RANK[maximum]:
                    continue
                return True
    return False


def validate_route_contract(
    root: Path, runtime: dict[str, Any]
) -> tuple[dict[str, Any], set[str], set[str], int, list[str]]:
    contract = load(root / "references/route-contract.json")
    errors: list[str] = []
    if contract.get("semantic_plan_schema") != "references/semantic-plan.schema.json":
        errors.append("route_semantic_plan_ref_invalid")
    selection = contract.get("selection_policy", {})
    if (
        selection.get("input") != "agent_semantic_plan"
        or selection.get("raw_request_classification") is not False
        or selection.get("single_global_mode") is not False
    ):
        errors.append("route_selection_boundary_invalid")

    tier_policy = contract.get("tier_policy", {})
    if not isinstance(tier_policy, dict) or set(tier_policy) != set(TIERS):
        errors.append("route_tier_policy_keyset_invalid")
        tier_policy = {}
    for tier, modes in tier_policy.items():
        values = string_list(modes, f"route_tier:{tier}", errors)
        unknown = set(values) - MODES
        if unknown:
            errors.append(f"route_tier_unknown_modes:{tier}:" + ",".join(sorted(unknown)))

    event_policy = contract.get("event_policy", {})
    known_events = set(string_list(event_policy.get("known_events"), "route_known_events", errors))
    if event_policy.get("source") != "semantic_plan.steps[].events" or event_policy.get("broadcast") is not False:
        errors.append("route_event_source_or_broadcast_invalid")
    control_events = set(event_policy.get("control_events", []))
    controller = event_policy.get("controller_events", {})
    controller_events = set(controller.get("per_step", [])) | set(controller.get("before_writable_step", []))
    if control_events - known_events or controller_events - known_events:
        errors.append("route_controller_or_control_event_unknown")

    routes = contract.get("routes")
    if not isinstance(routes, list) or not routes:
        return contract, set(), known_events, 0, errors + ["route_list_invalid"]
    route_ids = {
        item.get("id") for item in routes
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if len(route_ids) != len(routes):
        errors.append("route_ids_duplicate_or_missing")
    allowed_by_route = event_policy.get("route_allowed_events", {})
    if not isinstance(allowed_by_route, dict) or set(allowed_by_route) != route_ids:
        errors.append("route_allowed_event_keyset_invalid")
        allowed_by_route = {}
    action_contracts = contract.get("action_contracts", {})
    if not isinstance(action_contracts, dict) or set(action_contracts) != route_ids:
        errors.append("route_action_contract_keyset_invalid")
        action_contracts = {}

    prerequisites_container = contract.get("event_prerequisites", {})
    prerequisites = prerequisites_container.get("events", {})
    if not isinstance(prerequisites, dict) or set(prerequisites) - known_events:
        errors.append("route_event_prerequisite_keyset_invalid")
        prerequisites = {}
    controller_only = set(prerequisites_container.get("controller_only_events", []))
    if controller_only - known_events:
        errors.append("route_controller_only_event_unknown")
    for event, details in prerequisites.items():
        if not isinstance(details, dict):
            errors.append(f"route_event_prerequisite_invalid:{event}")
            continue
        minimum, maximum, mode = (
            details.get("minimum_tier"), details.get("maximum_tier"), details.get("required_mode")
        )
        if minimum is not None and minimum not in TIERS:
            errors.append(f"route_event_minimum_tier_invalid:{event}")
        if maximum is not None and maximum not in TIERS:
            errors.append(f"route_event_maximum_tier_invalid:{event}")
        if minimum in TIER_RANK and maximum in TIER_RANK and TIER_RANK[minimum] > TIER_RANK[maximum]:
            errors.append(f"route_event_tier_interval_invalid:{event}")
        if mode is not None and mode not in MODES:
            errors.append(f"route_event_mode_invalid:{event}")

    witness_count = 0
    for route in routes:
        if not isinstance(route, dict):
            errors.append("route_not_object")
            continue
        route_id = str(route.get("id", "<missing>"))
        modes = string_list(route.get("modes"), f"route_modes:{route_id}", errors)
        intents = string_list(route.get("intents"), f"route_intents:{route_id}", errors)
        string_list(route.get("component_types"), f"route_component_types:{route_id}", errors)
        string_list(route.get("states"), f"route_states:{route_id}", errors)
        if set(modes) - MODES:
            errors.append(f"route_unknown_modes:{route_id}")
        allowed = set(string_list(allowed_by_route.get(route_id), f"route_events:{route_id}", errors, nonempty=False))
        if allowed - known_events:
            errors.append(f"route_unknown_allowed_events:{route_id}")
        declarations = action_contracts.get(route_id, {})
        if not isinstance(declarations, dict) or set(declarations) != set(intents):
            errors.append(f"route_action_intent_mismatch:{route_id}")
            declarations = {}
        available = allowed | control_events | controller_events
        for action, details in declarations.items():
            if not isinstance(details, dict):
                errors.append(f"route_action_invalid:{route_id}:{action}")
                continue
            all_events = set(string_list(
                details.get("required_all_events", []),
                f"route_action_all_events:{route_id}:{action}", errors, nonempty=False,
            ))
            any_events = set(string_list(
                details.get("required_any_events", []),
                f"route_action_any_events:{route_id}:{action}", errors, nonempty=False,
            ))
            if (all_events | any_events) - known_events:
                errors.append(f"route_action_unknown_events:{route_id}:{action}")
            if all_events - available or (any_events and not (any_events & available)):
                errors.append(f"route_action_event_unavailable:{route_id}:{action}")
            minimum, maximum, required_mode = (
                details.get("minimum_tier"), details.get("maximum_tier"), details.get("required_mode")
            )
            if minimum is not None and minimum not in TIERS:
                errors.append(f"route_action_minimum_tier_invalid:{route_id}:{action}")
            if maximum is not None and maximum not in TIERS:
                errors.append(f"route_action_maximum_tier_invalid:{route_id}:{action}")
            if minimum in TIER_RANK and maximum in TIER_RANK and TIER_RANK[minimum] > TIER_RANK[maximum]:
                errors.append(f"route_action_tier_interval_invalid:{route_id}:{action}")
            if required_mode is not None and required_mode not in modes:
                errors.append(f"route_action_mode_unavailable:{route_id}:{action}")
            if action_is_feasible(route, action, details, contract, runtime):
                witness_count += 1
            else:
                errors.append(f"route_action_no_tier_witness:{route_id}:{action}")
        for context in route.get("context_refs", []):
            reference = context.get("ref") if isinstance(context, dict) else None
            if not reference_exists(root, reference):
                errors.append(f"route_context_ref_invalid:{route_id}:{reference}")

    runtime_actions = contract.get("runtime_action_policy", {})
    guarded = set(runtime_actions.get("guarded_kinds", []))
    kind_events = runtime_actions.get("kind_events", {})
    if (
        not isinstance(kind_events, dict)
        or guarded != set(kind_events)
        or runtime_actions.get("ordinary_work_requires_runtime_action") is not False
        or runtime_actions.get("execution_entry") != "scripts/run_authorized_action.py"
        or not reference_exists(root, runtime_actions.get("execution_entry"))
    ):
        errors.append("route_runtime_action_policy_invalid")
    elif any(set(events) - known_events for events in kind_events.values() if isinstance(events, list)):
        errors.append("route_runtime_action_event_unknown")

    transition = next((item for item in routes if item.get("id") == "RT.STATE.TRANSITION"), {})
    machine = load(root / "references/state-machine.json")
    route_types = set(transition.get("component_types", []))
    route_states = set(transition.get("states", []))
    for component_type, edges in machine.get("transitions", {}).items():
        for edge in edges:
            if component_type not in route_types or edge.get("from") not in route_states:
                errors.append(f"state_edge_without_route:{component_type}:{edge.get('from')}:{edge.get('to')}")
    return contract, route_ids, known_events, witness_count, sorted(set(errors))


def rule_matches_route(rule: dict[str, Any], route: dict[str, Any], mode: str) -> bool:
    selectors = set(rule.get("routes", []))
    if "*" in selectors or route.get("id") in selectors:
        return True
    if "@recovery" in selectors and route.get("recovery"):
        return True
    return "@write" in selectors and mode in {"mutate", "promote", "skill_maintenance"}


def load_rule_corpus(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    rules: list[dict[str, Any]] = []
    schema = load(root / "references/rule-atom.schema.json")
    validator = None
    if Draft202012Validator is None or FormatChecker is None:
        errors.append("jsonschema_dependency_missing")
    else:
        try:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema, format_checker=FormatChecker())
        except Exception as exc:
            errors.append(f"rule_atom_schema_invalid:{exc}")
    for path in sorted((root / "rules").glob("*.json")):
        bundle = load(path)
        relative = path.relative_to(root).as_posix()
        if validator is not None:
            for violation in validator.iter_errors(bundle):
                location = "/".join(str(item) for item in violation.absolute_path) or "$"
                errors.append(f"atom_schema:{relative}:{location}:{violation.validator}")
        if not isinstance(bundle.get("rules"), list):
            errors.append(f"rule_bundle_invalid:{relative}")
            continue
        for rule in bundle["rules"]:
            if not isinstance(rule, dict):
                errors.append(f"rule_not_object:{relative}")
                continue
            item = dict(rule)
            item["__path"] = relative
            rules.append(item)
    return rules, errors


def validate_rule_inventory(
    root: Path,
    rules: list[dict[str, Any]],
    route_ids: set[str],
    known_events: set[str],
    policy_case_ids: set[str],
    expected_active_count: int,
) -> tuple[dict[str, int], list[str]]:
    errors: list[str] = []
    known_rule_ids = {str(rule.get("id")) for rule in rules}
    ids = [str(rule.get("id")) for rule in rules]
    semantic_keys = [str(rule.get("semantic_key")) for rule in rules]
    for duplicate, count in Counter(ids).items():
        if count > 1:
            errors.append(f"duplicate_rule_id:{duplicate}")
    for duplicate, count in Counter(semantic_keys).items():
        if count > 1:
            errors.append(f"duplicate_rule_semantic_key:{duplicate}")
    known_evidence_ids = CHECK_IDS | policy_case_ids
    for rule in rules:
        rule_id = str(rule.get("id", "<missing>"))
        relative = str(rule.get("__path"))
        if rule.get("owner") != f"{relative}#{rule_id}":
            errors.append(f"rule_owner_mismatch:{rule_id}")
        if rule.get("domain") != load(root / relative).get("domain"):
            errors.append(f"rule_bundle_domain_mismatch:{rule_id}")
        unknown_routes = set(rule.get("routes", [])) - route_ids - ROUTE_SELECTORS
        if unknown_routes:
            errors.append(f"rule_unknown_routes:{rule_id}:" + ",".join(sorted(unknown_routes)))
        unknown_events = set(rule.get("trigger", {}).get("events", [])) - known_events
        if unknown_events:
            errors.append(f"rule_unknown_events:{rule_id}:" + ",".join(sorted(unknown_events)))
        tests = rule.get("tests", [])
        if not isinstance(tests, list) or not tests:
            errors.append(f"rule_evidence_ids_missing:{rule_id}")
        else:
            unknown_tests = set(tests) - known_evidence_ids
            if unknown_tests:
                errors.append(f"rule_evidence_id_unknown:{rule_id}:" + ",".join(sorted(unknown_tests)))
        enforcement = rule.get("enforcement", {})
        expected_assurance = (
            "behavior_verified" if enforcement.get("kind") == "runtime_guard"
            else "selection_verified"
        )
        if enforcement.get("assurance") != expected_assurance:
            errors.append(f"rule_enforcement_assurance_invalid:{rule_id}")
        for reference in enforcement.get("refs", []):
            if not reference_exists(root, reference):
                errors.append(f"rule_enforcement_ref_missing:{rule_id}:{reference}")
        for field in ("conflicts_with", "refines", "depends_on"):
            unknown = set(rule.get(field, [])) - known_rule_ids
            if unknown:
                errors.append(f"rule_relation_unknown:{rule_id}:{field}:" + ",".join(sorted(unknown)))
    active = [rule for rule in rules if rule.get("status") == "active"]
    if len(active) != expected_active_count:
        errors.append(f"active_rule_count_invalid:{len(active)}!={expected_active_count}")
    active_events = {
        event for rule in active for event in rule.get("trigger", {}).get("events", [])
    }
    if active_events != known_events:
        errors.append(
            "active_rule_event_vocabulary_drift:missing=" + ",".join(sorted(known_events - active_events))
            + ":extra=" + ",".join(sorted(active_events - known_events))
        )
    return {
        "rules": len(rules), "active_rules": len(active),
        "active_capabilities": len({rule.get("capability") for rule in active}),
        "trigger_events": len(active_events),
    }, sorted(set(errors))


def validate_active_reachability(
    rules: list[dict[str, Any]], contract: dict[str, Any], runtime: dict[str, Any]
) -> tuple[int, list[str]]:
    routes = contract.get("routes", [])
    allowed_by_route = contract.get("event_policy", {}).get("route_allowed_events", {})
    control_events = set(contract.get("event_policy", {}).get("control_events", []))
    controller = contract.get("event_policy", {}).get("controller_events", {})
    controller_events = (
        set(controller.get("per_step", []))
        | set(controller.get("before_writable_step", []))
        | set(controller.get("before_formal_artifact_admission", []))
    )
    action_contracts = contract.get("action_contracts", {})
    scope_adapters = contract.get("legacy_scope_adapters", {})
    trigger_adapters = contract.get("legacy_trigger_adapters", {})
    unreachable: list[str] = []
    active = [rule for rule in rules if rule.get("status") == "active"]
    for rule in active:
        witness = False
        scope = rule.get("scope", {})
        for route in routes:
            objects = set(scope.get("objects", []))
            if "*" not in objects and route.get("object") not in objects:
                continue
            for mode in route.get("modes", []):
                if not rule_matches_route(rule, route, mode):
                    continue
                rule_types = set(scope.get("component_types", []))
                if "none" not in rule_types and not (rule_types & set(route.get("component_types", []))):
                    continue
                rule_states = set(scope.get("states", []))
                route_states = set(route.get("states", []))
                state_ok = "*" in rule_states or bool(rule_states & route_states)
                if not state_ok:
                    adapter = scope_adapters.get("skill_state", {})
                    state_ok = (
                        rule.get("domain") == adapter.get("domain")
                        and route.get("object") == "skill"
                        and adapter.get("actual_state") in route_states
                        and adapter.get("frozen_scope_token") in rule_states
                    )
                if not state_ok:
                    continue
                available = set(allowed_by_route.get(route.get("id"), [])) | control_events | controller_events
                target_events = set(rule.get("trigger", {}).get("events", [])) & available
                adapter = trigger_adapters.get(rule.get("id"))
                if isinstance(adapter, dict):
                    coarse = adapter.get("coarse_controller_event")
                    if coarse in target_events and not adapter.get("when_fact_true") and not (
                        set(adapter.get("when_any_actual_event", []))
                        & set(allowed_by_route.get(route.get("id"), []))
                    ):
                        target_events.discard(coarse)
                if not target_events:
                    continue
                for action in route.get("intents", []):
                    details = action_contracts.get(route.get("id"), {}).get(action, {})
                    if action_is_feasible(route, action, details, contract, runtime):
                        witness = True
                        break
                if witness:
                    break
            if witness:
                break
        if not witness:
            unreachable.append(str(rule.get("id")))
    return len(active) - len(unreachable), [
        "active_rule_unreachable:" + item for item in sorted(unreachable)
    ]


def validate_capability_packets(
    root: Path, rules: list[dict[str, Any]], route_contract: dict[str, Any]
) -> tuple[dict[str, int], list[str]]:
    errors: list[str] = []
    registry = load(root / "references/capability-packet-registry.json")
    if registry.get("schema_version") != SCHEMA_VERSION:
        errors.append("packet_registry_identity_invalid")
    active = [rule for rule in rules if rule.get("status") == "active"]
    active_capabilities = {
        item.get("capability") for item in active
        if isinstance(item.get("capability"), str) and item.get("capability")
    }

    packet_ids: set[str] = set()
    packet_paths: set[str] = set()
    packet_capabilities: set[str] = set()
    router_to_packets: dict[str, set[str]] = defaultdict(set)
    packets = registry.get("packets", [])
    if not isinstance(packets, list) or not packets:
        errors.append("packet_registry_packets_invalid")
        packets = []
    for packet in packets:
        if not isinstance(packet, dict):
            errors.append("packet_declaration_not_object")
            continue
        packet_id, path, router = packet.get("id"), packet.get("path"), packet.get("router")
        if not isinstance(packet_id, str) or not packet_id:
            errors.append("packet_id_invalid")
            continue
        if packet_id in packet_ids:
            errors.append(f"packet_id_duplicate:{packet_id}")
        packet_ids.add(packet_id)
        if not isinstance(path, str) or not path.startswith("references/capability-packets/"):
            errors.append(f"packet_path_invalid:{packet_id}:{path}")
        else:
            if path in packet_paths:
                errors.append(f"packet_path_duplicate:{path}")
            packet_paths.add(path)
            if not (root / path).is_file():
                errors.append(f"packet_file_missing:{packet_id}:{path}")
        if not isinstance(router, str) or not (root / router).is_file():
            errors.append(f"packet_router_missing:{packet_id}:{router}")
        elif isinstance(path, str):
            router_to_packets[router].add(path)
        capabilities = packet.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities or any(
            not isinstance(item, str) or not item for item in capabilities
        ):
            errors.append(f"packet_capabilities_invalid:{packet_id}")
        else:
            packet_capabilities.update(capabilities)

    actual_packet_paths = {
        path.relative_to(root).as_posix()
        for path in (root / "references/capability-packets").rglob("*.md")
        if path.is_file()
    }
    if actual_packet_paths != packet_paths:
        for item in sorted(actual_packet_paths - packet_paths):
            errors.append(f"packet_file_unregistered:{item}")
        for item in sorted(packet_paths - actual_packet_paths):
            errors.append(f"packet_registration_without_file:{item}")

    contract_capabilities: set[str] = set()
    coverage_ids: set[str] = set()
    for coverage in registry.get("contract_coverage", []):
        if not isinstance(coverage, dict):
            errors.append("packet_contract_coverage_not_object")
            continue
        coverage_id = coverage.get("id")
        if not isinstance(coverage_id, str) or coverage_id in coverage_ids:
            errors.append(f"packet_contract_coverage_id_invalid:{coverage_id}")
        else:
            coverage_ids.add(coverage_id)
        capabilities = coverage.get("capabilities", [])
        if not isinstance(capabilities, list):
            errors.append(f"packet_contract_capabilities_invalid:{coverage_id}")
            capabilities = []
        contract_capabilities.update(item for item in capabilities if isinstance(item, str))
        for resource in coverage.get("resources", []):
            if not reference_exists(root, resource):
                errors.append(f"packet_contract_resource_missing:{coverage_id}:{resource}")

    covered = packet_capabilities | contract_capabilities
    for capability in sorted(active_capabilities - covered):
        errors.append(f"active_capability_without_packet_or_contract:{capability}")
    for capability in sorted(covered - active_capabilities):
        errors.append(f"packet_registry_unknown_capability:{capability}")

    declared_routers = registry.get("routers", [])
    if not isinstance(declared_routers, list) or len(declared_routers) != len(set(declared_routers)):
        errors.append("packet_router_inventory_invalid")
        declared_routers = []
    if set(router_to_packets) - set(declared_routers):
        errors.append("packet_router_undeclared")
    for router in declared_routers:
        router_path = root / router
        if not router_path.is_file():
            errors.append(f"packet_declared_router_missing:{router}")
            continue
        linked: set[str] = set()
        for target in LINK_RE.findall(router_path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://")):
                continue
            try:
                linked.add((router_path.parent / target).resolve().relative_to(root).as_posix())
            except ValueError:
                errors.append(f"packet_router_link_outside_package:{router}:{target}")
        for packet_path in sorted(router_to_packets.get(router, set()) - linked):
            errors.append(f"packet_unreachable_from_router:{router}:{packet_path}")

    for route in route_contract.get("routes", []):
        route_id = route.get("id")
        for context in route.get("context_refs", []):
            reference = context.get("ref") if isinstance(context, dict) else None
            if not reference_exists(root, reference):
                errors.append(f"packet_route_context_invalid:{route_id}:{reference}")
    for source in registry.get("historical_sources", []):
        path = source.get("path") if isinstance(source, dict) else None
        if not isinstance(path, str) or not (root / path).is_file():
            errors.append(f"packet_historical_source_missing:{path}")
            continue
        expected = source.get("sha256")
        if expected is not None and file_sha256(root / path) != expected:
            errors.append(f"packet_historical_source_hash_mismatch:{path}")
    return {
        "packets": len(packet_ids),
        "routers": len(declared_routers),
        "packet_capabilities": len(packet_capabilities),
        "contract_capabilities": len(contract_capabilities),
    }, sorted(set(errors))


def atom_contract(rule: dict[str, Any]) -> dict[str, Any]:
    """Mirror the current migration inventory projection without eval back-references."""
    return {
        "id": rule["id"], "revision": rule["revision"], "status": rule["status"],
        "capability": rule["capability"], "domain": rule["domain"], "owner": rule["owner"],
        "strength": rule["strength"], "semantic_key": rule["semantic_key"],
        "scope": rule["scope"], "trigger": rule["trigger"], "effect": rule["effect"],
        "instruction_gloss": str(rule.get("instruction_gloss", rule.get("instruction", ""))),
        "failure_example": str(rule.get("failure_example", rule.get("forbidden", ""))),
        "evidence": rule["evidence"], "outcomes": rule["outcomes"],
        "exceptions": rule.get("exceptions", []), "conflicts_with": rule.get("conflicts_with", []),
        "refines": rule.get("refines", []), "depends_on": rule.get("depends_on", []),
        "supersedes": rule.get("supersedes", []), "legacy_refs": rule.get("legacy_refs", []),
        "routes": rule.get("routes", []), "enforcement": rule.get("enforcement"),
    }


def semantic_atom_contract(rule: dict[str, Any], origin: str) -> dict[str, Any]:
    return {
        "atom_id": rule["id"], "atom_status": rule["status"], "origin": origin,
        "capability_id": rule["capability"], "domain": rule["domain"],
        "owner": rule["owner"], "legacy_refs": rule.get("legacy_refs", []),
        "semantic_key": rule["semantic_key"], "strength": rule["strength"],
        "scope": rule["scope"], "trigger": rule["trigger"], "effect": rule["effect"],
        "evidence": rule["evidence"],
        "exceptions": rule.get("exceptions", []), "conflicts_with": rule.get("conflicts_with", []),
        "refines": rule.get("refines", []), "depends_on": rule.get("depends_on", []),
        "supersedes": rule.get("supersedes", []),
        "routes": rule.get("routes", []), "enforcement": rule.get("enforcement"),
    }


def strength_relation(source_strength: str, current_strengths: list[str]) -> str:
    rank = {"MAY": 0, "SHOULD": 1, "MUST": 2}
    if source_strength not in rank or not current_strengths or any(item not in rank for item in current_strengths):
        return "unbound"
    values = {rank[item] for item in current_strengths}
    source = rank[source_strength]
    if values == {source}:
        return "same"
    if min(values) >= source:
        return "contains_stronger"
    return "contains_weaker"


def validate_preservation(
    root: Path, rules: list[dict[str, Any]], policy_case_ids: set[str]
) -> tuple[dict[str, int], list[str]]:
    errors: list[str] = []
    ledger = load(root / "references/migration/v15-preservation-ledger.json")
    baseline = load(root / "references/migration/v9-capability-baseline.json")
    legacy = load(root / "references/migration/legacy-coverage.json")
    crosswalk = load(root / "references/migration/capability-crosswalk.json")
    clauses = load(root / "references/migration/clause-preservation.json")
    for label, artifact in (
        ("v15_preservation_ledger", ledger), ("v9_capability_baseline", baseline),
        ("legacy_coverage", legacy), ("capability_crosswalk", crosswalk),
        ("clause_preservation", clauses),
    ):
        verify_seal(label, artifact, errors)
    if (
        ledger.get("schema_version") != SCHEMA_VERSION
        or ledger.get("artifact_kind") != "v15_current_preservation_index"
        or ledger.get("release_id") != RELEASE_ID
    ):
        errors.append("v15_preservation_ledger_identity_invalid")

    for source in ledger.get("source_seals", []):
        if not isinstance(source, dict):
            errors.append("v15_source_seal_not_object")
            continue
        path, field, expected = source.get("path"), source.get("seal_field"), source.get("payload_sha256")
        if not isinstance(path, str) or not (root / path).is_file():
            errors.append(f"v15_source_seal_path_missing:{path}")
            continue
        payload = load(root / path)
        if field != "payload_sha256" or payload.get(field) != expected:
            errors.append(f"v15_source_seal_binding_mismatch:{path}")

    baseline_capabilities = baseline.get("capabilities", [])
    baseline_by_id = {
        item.get("id"): item for item in baseline_capabilities
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    if len(baseline_by_id) != len(baseline_capabilities):
        errors.append("v9_baseline_capability_ids_invalid")
    for capability_id, item in baseline_by_id.items():
        contract = {
            field: item.get(field)
            for field in ("id", "domain", "owner", "strength", "trigger", "expected", "forbidden")
        }
        if item.get("contract_sha256") != canonical_sha256(contract):
            errors.append(f"v9_baseline_contract_hash_mismatch:{capability_id}")

    active_rules = [rule for rule in rules if rule.get("status") == "active"]
    active_by_id = {rule.get("id"): rule for rule in active_rules}
    active_by_capability: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for rule in active_rules:
        if isinstance(rule.get("capability"), str):
            active_by_capability[rule["capability"]].append(rule)

    inherited = ledger.get("inherited_capabilities", {})
    dispositions = inherited.get("dispositions", {})
    allowed_dispositions = set(ledger.get("allowed_dispositions", []))
    if not isinstance(dispositions, dict) or set(dispositions) != allowed_dispositions:
        errors.append("v15_inherited_disposition_keyset_invalid")
        dispositions = {}
    disposition_ids: list[str] = []
    for disposition, capability_ids in dispositions.items():
        if not isinstance(capability_ids, list):
            errors.append(f"v15_inherited_disposition_list_invalid:{disposition}")
            continue
        disposition_ids.extend(item for item in capability_ids if isinstance(item, str))
    if len(disposition_ids) != len(set(disposition_ids)):
        errors.append("v15_inherited_capability_duplicate")
    if set(disposition_ids) != set(baseline_by_id):
        errors.append("v15_inherited_capability_set_drift")
    if inherited.get("expected_count") != len(baseline_by_id):
        errors.append("v15_inherited_capability_count_drift")
    if inherited.get("expected_active_atom_count") != len(active_rules):
        errors.append("v15_inherited_atom_count_drift")
    if set(active_by_capability) != set(baseline_by_id):
        errors.append("v15_active_capability_baseline_drift")
    for reference in inherited.get("evidence_refs", []):
        if not reference_exists(root, reference):
            errors.append(f"v15_inherited_evidence_ref_missing:{reference}")
    for check_id in inherited.get("evidence_check_ids", []):
        if check_id not in CHECK_IDS:
            errors.append(f"v15_inherited_check_id_unknown:{check_id}")
    if not reference_exists(root, inherited.get("packet_binding_ref")):
        errors.append("v15_inherited_packet_binding_missing")

    native = ledger.get("native_capabilities", [])
    native_ids = [item.get("id") for item in native if isinstance(item, dict)]
    if len(native) != 10 or len(native_ids) != 10 or len(set(native_ids)) != 10:
        errors.append("v15_native_capability_inventory_invalid")
    for item in native:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id", "<missing>")
        if item.get("disposition") not in allowed_dispositions:
            errors.append(f"v15_native_disposition_invalid:{identifier}")
        owner_refs = item.get("owner_refs", [])
        if not isinstance(owner_refs, list) or not owner_refs:
            errors.append(f"v15_native_owner_refs_invalid:{identifier}")
        else:
            for reference in owner_refs:
                if not reference_exists(root, reference):
                    errors.append(f"v15_native_owner_ref_missing:{identifier}:{reference}")
        evidence_cases = item.get("evidence_case_ids", [])
        if not isinstance(evidence_cases, list) or not evidence_cases:
            errors.append(f"v15_native_case_refs_invalid:{identifier}")
        else:
            for case_id in evidence_cases:
                if case_id not in policy_case_ids:
                    errors.append(f"v15_native_case_ref_not_required:{identifier}:{case_id}")
        evidence_checks = item.get("evidence_check_ids", [])
        if not isinstance(evidence_checks, list) or not evidence_checks:
            errors.append(f"v15_native_check_refs_invalid:{identifier}")
        else:
            for check_id in evidence_checks:
                if check_id not in CHECK_IDS:
                    errors.append(f"v15_native_check_ref_unknown:{identifier}:{check_id}")

    if clauses.get("source_baseline_payload_sha256") != baseline.get("payload_sha256"):
        errors.append("clause_preservation_baseline_binding_mismatch")
    review = clauses.get("review", {})
    if review.get("release") != CLAUSE_REVIEW_RELEASE or not str(review.get("decision_id", "")).startswith("V16-"):
        errors.append("clause_preservation_review_identity_invalid")
    try:
        from build_clause_preservation import (
            EXPECTED_REVIEW_PROJECTION_SHA256,
            build_artifact as build_clause_preservation_artifact,
            review_source_inventory,
        )

        current_review_sources = review_source_inventory(root)
        if clauses.get("review_sources") != current_review_sources:
            errors.append("clause_preservation_review_sources_stale")
        if clauses.get("review_source_inventory_sha256") != canonical_sha256(current_review_sources):
            errors.append("clause_preservation_review_source_inventory_hash_mismatch")
        expected_clause_artifact, current_review_projection = build_clause_preservation_artifact(
            root, baseline
        )
        if current_review_projection != EXPECTED_REVIEW_PROJECTION_SHA256:
            errors.append("clause_preservation_review_requires_versioned_reseal")
        if clauses != expected_clause_artifact:
            errors.append("clause_preservation_compiled_content_stale")
    except Exception as exc:
        errors.append(f"clause_preservation_rebuild_failed:{exc}")
    allowed_relations = set(clauses.get("allowed_relations", []))
    blocking_relations = set(clauses.get("blocking_relations", []))
    if not allowed_relations or allowed_relations & blocking_relations:
        errors.append("clause_preservation_relation_codebook_invalid")
    clause_rows = clauses.get("clauses", [])
    for row in clause_rows:
        if not isinstance(row, dict):
            errors.append("clause_preservation_row_not_object")
            continue
        if row.get("review_status") != "reviewed" or row.get("relation") not in allowed_relations:
            errors.append(f"clause_preservation_blocking_row:{row.get('id')}")
        atom_ids = row.get("atom_ids", [])
        if not isinstance(atom_ids, list) or not atom_ids or set(atom_ids) - set(active_by_id):
            errors.append(f"clause_preservation_atom_binding_invalid:{row.get('id')}")
    if clauses.get("clause_count") not in (None, len(clause_rows)):
        errors.append("clause_preservation_count_drift")

    atom_reviews = clauses.get("atom_reviews", [])
    review_by_id = {
        row.get("atom_id"): row for row in atom_reviews
        if isinstance(row, dict) and isinstance(row.get("atom_id"), str)
    }
    if len(review_by_id) != len(atom_reviews) or set(review_by_id) != set(active_by_id):
        errors.append("clause_preservation_atom_review_bijection_invalid")
    for atom_id, rule in active_by_id.items():
        row = review_by_id.get(atom_id, {})
        expected_origin = "legacy_family" if rule.get("capability") in baseline_by_id else "native_v10"
        if row.get("review_status") != "reviewed" or row.get("origin") != expected_origin:
            errors.append(f"clause_preservation_atom_review_invalid:{atom_id}")
        if row.get("revision") != rule.get("revision") or row.get("strength") != rule.get("strength"):
            errors.append(f"clause_preservation_atom_identity_drift:{atom_id}")
        if row.get("semantic_sha256") != canonical_sha256(semantic_atom_contract(rule, expected_origin)):
            errors.append(f"clause_preservation_atom_semantics_drift:{atom_id}")

    crosswalk_rows = crosswalk.get("capabilities", [])
    crosswalk_by_id = {
        row.get("capability_id"): row for row in crosswalk_rows
        if isinstance(row, dict) and isinstance(row.get("capability_id"), str)
    }
    if len(crosswalk_by_id) != len(crosswalk_rows) or set(crosswalk_by_id) != set(baseline_by_id):
        errors.append("capability_crosswalk_bijection_invalid")
    blocking_dispositions = set(crosswalk.get("blocking_dispositions", []))
    for capability_id, source in baseline_by_id.items():
        row = crosswalk_by_id.get(capability_id, {})
        bound_rules = sorted(active_by_capability.get(capability_id, []), key=lambda item: item["id"])
        relation = strength_relation(source.get("strength"), [item.get("strength") for item in bound_rules])
        if relation in {"unbound", "contains_weaker"}:
            errors.append(f"capability_strength_regression:{capability_id}:{relation}")
        if row.get("strength_relation") != relation:
            errors.append(f"capability_strength_relation_drift:{capability_id}")
        if row.get("atom_ids") != [item["id"] for item in bound_rules]:
            errors.append(f"capability_atom_binding_drift:{capability_id}")
        if row.get("disposition") in blocking_dispositions:
            errors.append(f"capability_blocking_disposition:{capability_id}")
        binding_by_id = {
            item.get("atom_id"): item for item in row.get("atom_bindings", [])
            if isinstance(item, dict)
        }
        for rule in bound_rules:
            binding = binding_by_id.get(rule["id"], {})
            if binding.get("revision") != rule.get("revision") or binding.get("strength") != rule.get("strength"):
                errors.append(f"capability_atom_identity_drift:{rule['id']}")
            if binding.get("atom_contract_sha256") != canonical_sha256(atom_contract(rule)):
                errors.append(f"capability_atom_contract_drift:{rule['id']}")

    reverse_rows = crosswalk.get("reverse_atoms", [])
    reverse_by_id = {
        row.get("atom_id"): row for row in reverse_rows
        if isinstance(row, dict) and isinstance(row.get("atom_id"), str)
    }
    if len(reverse_by_id) != len(reverse_rows) or set(reverse_by_id) != set(active_by_id):
        errors.append("capability_reverse_atom_bijection_invalid")
    for atom_id, rule in active_by_id.items():
        row = reverse_by_id.get(atom_id, {})
        if (
            row.get("atom_status") != rule.get("status")
            or row.get("capability_id") != rule.get("capability")
            or row.get("atom_contract_sha256") != canonical_sha256(atom_contract(rule))
        ):
            errors.append(f"capability_reverse_atom_drift:{atom_id}")

    for source in legacy.get("sources", {}).values():
        if not isinstance(source, dict):
            errors.append("legacy_source_declaration_invalid")
            continue
        path, expected = source.get("path"), source.get("sha256")
        if not isinstance(path, str) or not (root / path).is_file():
            errors.append(f"legacy_source_missing:{path}")
        elif file_sha256(root / path) != expected:
            errors.append(f"legacy_source_hash_mismatch:{path}")
    for row in legacy.get("v7_v8_dispositions", []):
        if not isinstance(row, dict):
            errors.append("legacy_native_disposition_not_object")
            continue
        if row.get("disposition") in {"gap", "pending", "unreviewed"}:
            errors.append(f"legacy_native_blocking_disposition:{row.get('legacy_id')}")
        if set(row.get("atom_ids", [])) - set(active_by_id):
            errors.append(f"legacy_native_atom_binding_invalid:{row.get('legacy_id')}")
        for reference in row.get("artifact_refs", []):
            if not reference_exists(root, reference):
                errors.append(f"legacy_native_artifact_ref_missing:{row.get('legacy_id')}:{reference}")
    return {
        "inherited_capabilities": len(baseline_by_id),
        "native_capabilities": len(native),
        "reviewed_clauses": len(clause_rows),
        "reviewed_atoms": len(atom_reviews),
    }, sorted(set(errors))


def validate_release_and_control_bindings(root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    policy = load(root / "references/release-policy.json")
    plan = load(root / "evals/release/release-plan.json")
    state = load(root / "evals/release/release-state.json")
    manifest_schema = load(root / "references/release-manifest.schema.json")
    policy_drivers = [
        {"id": item.get("id"), "script": item.get("script")}
        for item in policy.get("active_drivers", []) if isinstance(item, dict)
    ]
    plan_drivers = [
        {"id": item.get("id"), "script": item.get("script")}
        for item in plan.get("drivers", []) if isinstance(item, dict)
    ]
    driver_ids = [item["id"] for item in policy_drivers]
    required_cases = policy.get("required_case_ids", [])
    if policy.get("schema_version") != SCHEMA_VERSION or policy.get("release_id") != RELEASE_ID:
        errors.append("release_policy_identity_invalid")
    if not policy_drivers or len(driver_ids) != len(set(driver_ids)):
        errors.append("release_policy_driver_inventory_invalid")
    for item in policy_drivers:
        if not isinstance(item.get("id"), str) or not reference_exists(root, item.get("script")):
            errors.append(f"release_policy_driver_invalid:{item}")
    if not isinstance(required_cases, list) or not required_cases or len(required_cases) != len(set(required_cases)):
        errors.append("release_policy_required_cases_invalid")
        required_cases = []
    if policy.get("budget", {}).get("active_driver_count") != len(policy_drivers):
        errors.append("release_policy_driver_budget_drift")
    if (
        plan.get("schema_version") != SCHEMA_VERSION
        or plan.get("release_id") != RELEASE_ID
        or plan.get("policy") != "references/release-policy.json"
    ):
        errors.append("release_plan_identity_invalid")
    if plan.get("required_drivers") != driver_ids or plan_drivers != policy_drivers:
        errors.append("release_plan_driver_binding_drift")
    if plan.get("required_case_ids") != required_cases:
        errors.append("release_plan_case_binding_drift")
    if plan.get("legacy_diagnostic_suites_are_active_drivers") is not False:
        errors.append("release_plan_legacy_chain_active")
    if (
        state.get("schema_version") != SCHEMA_VERSION
        or state.get("release_id") != RELEASE_ID
        or state.get("status") != "candidate"
        or state.get("frozen_at") is not None
        or state.get("gate_report_sha256") is not None
    ):
        errors.append("release_state_candidate_identity_invalid")
    manifest_properties = manifest_schema.get("properties", {})
    if (
        manifest_properties.get("schema_version", {}).get("const") != SCHEMA_VERSION
        or manifest_properties.get("release_id", {}).get("const") != RELEASE_ID
        or manifest_properties.get("status", {}).get("const") != "stable"
    ):
        errors.append("release_manifest_schema_identity_invalid")

    skill = (root / "SKILL.md").read_text(encoding="utf-8")
    if not re.search(r'(?m)^\s{2}version:\s*["\']15\.0\.1["\']\s*$', skill):
        errors.append("skill_version_identity_invalid")
    if not re.search(r'(?m)^\s{2}release:\s*["\']candidate["\']\s*$', skill):
        errors.append("skill_candidate_identity_invalid")

    ownership = load(root / "references/ownership-contract.json")
    classes = ownership.get("classes", {})
    preservation_owner = classes.get("capability_preservation_contract", {})
    if preservation_owner.get("owner") != "references/migration/v15-preservation-ledger.json":
        errors.append("preservation_owner_invalid")
    for class_id, details in classes.items():
        if not isinstance(details, dict):
            errors.append(f"ownership_class_invalid:{class_id}")
            continue
        references: set[str] = set()
        for key, value in details.items():
            if key in {"owner", "shape_owner", "selection_contract", "selection_driver", "interpreter", "semantic_interpreter"} and isinstance(value, str):
                references.add(value)
            elif key in {"interpreters", "semantic_interpreters"} and isinstance(value, list):
                references.update(item for item in value if isinstance(item, str))
        for reference in references:
            if not reference_exists(root, reference):
                errors.append(f"ownership_reference_missing:{class_id}:{reference}")

    platform = load(root / "references/project-platform-contract.json")
    artifact = load(root / "references/artifact-contract.json")
    if (
        platform.get("$id")
        != "https://local.invalid/modeling-controller-v15/project-platform-contract.json"
        or platform.get("schema_version") != SCHEMA_VERSION
    ):
        errors.append("project_platform_contract_identity_invalid")
    roles = platform.get("roles", {})
    artifact_roles = set(artifact.get("properties", {}).get("platform_role", {}).get("enum", []))
    if set(roles) != artifact_roles:
        errors.append("platform_artifact_role_drift")
    artifact_required = set(artifact.get("required", []))
    if not {"path", "platform_role", "class"}.issubset(artifact_required):
        errors.append("platform_artifact_explicit_role_or_class_missing")
    artifact_classes = set(artifact.get("properties", {}).get("class", {}).get("enum", []))
    for role, details in roles.items():
        if not details.get("path_patterns") or not details.get("classes"):
            errors.append(f"platform_role_declaration_incomplete:{role}")
        if set(details.get("classes", [])) - artifact_classes:
            errors.append(f"platform_role_class_unknown:{role}")
        for pattern in details.get("path_patterns", []):
            try:
                re.compile(pattern)
            except re.error as exc:
                errors.append(f"platform_path_pattern_invalid:{role}:{exc}")

    namespaces = platform.get("path_namespaces", {})
    namespace_pattern_fields = {
        "project_support": ("path_patterns",),
        "tool_managed_transient": ("path_patterns",),
        "reserved": ("repository_internal_patterns", "controller_metadata_patterns"),
    }
    compiled_namespace_patterns: dict[str, list[re.Pattern[str]]] = defaultdict(list)
    for namespace, fields in namespace_pattern_fields.items():
        declaration = namespaces.get(namespace, {})
        for field in fields:
            patterns = declaration.get(field, [])
            if not isinstance(patterns, list) or not patterns:
                errors.append(f"platform_namespace_patterns_missing:{namespace}:{field}")
                continue
            for pattern in patterns:
                if not isinstance(pattern, str) or not pattern:
                    errors.append(f"platform_namespace_pattern_invalid:{namespace}:{field}")
                    continue
                try:
                    compiled_namespace_patterns[namespace].append(re.compile(pattern))
                except re.error as exc:
                    errors.append(
                        f"platform_namespace_pattern_invalid:{namespace}:{field}:{exc}"
                    )

    def namespace_matches(namespace: str, relative: str) -> bool:
        return any(
            pattern.fullmatch(relative)
            for pattern in compiled_namespace_patterns.get(namespace, [])
        )

    for relative in (
        "pyproject.toml", "requirements-dev.txt", ".gitignore",
        "tests/test_model.py", "notebooks/eda.ipynb", "config/settings.yml",
    ):
        if not namespace_matches("project_support", relative):
            errors.append(f"platform_support_witness_rejected:{relative}")
    for relative in (
        ".pytest_cache/v/cache/nodeids", "src/q1/__pycache__/solver.pyc", "build/report.tmp",
        ".venv/bin/activate", "venv/bin/python", ".tox/py/bin/python",
        ".nox/tests/bin/python", "notebooks/.ipynb_checkpoints/eda.ipynb",
    ):
        if not namespace_matches("tool_managed_transient", relative):
            errors.append(f"platform_transient_witness_rejected:{relative}")
    for relative in (
        ".git/config", ".modeling/state.json", ".codex/session.json",
        ".agents/session.json",
    ):
        if not namespace_matches("reserved", relative):
            errors.append(f"platform_reserved_witness_rejected:{relative}")
        if namespace_matches("project_support", relative):
            errors.append(f"platform_reserved_leaked_into_support:{relative}")

    overlap_witnesses = {
        "paper/main.tex": {"manuscript", "visual"},
        "output/q3/result.json": {"result", "visual"},
    }
    for relative, expected_roles in overlap_witnesses.items():
        matched_roles = {
            role for role, details in roles.items()
            if any(re.fullmatch(pattern, relative) for pattern in details.get("path_patterns", []))
        }
        if not expected_roles.issubset(matched_roles):
            errors.append(f"platform_role_overlap_witness_missing:{relative}")
    required_invariants = {
        "g1 path admission does not assign a semantic platform_role",
        "role path patterns may overlap and one_or_more matches are valid at g1",
        "one formally admitted artifact explicitly selects exactly one platform_role",
        "a formal artifact path and class must match its selected role",
        "tool managed transient side effects are neither retained change_set paths nor claim or delivery authorities",
    }
    if not required_invariants.issubset(set(platform.get("cross_role_invariants", []))):
        errors.append("platform_selected_role_or_namespace_invariants_missing")

    semantic_plan = load(root / "references/semantic-plan.schema.json")
    plan_defs = semantic_plan.get("$defs", {})
    canonical_path_schema = plan_defs.get("canonical_relative_path", {})
    canonical_namespace_schema = plan_defs.get("canonical_top_level_namespace", {})
    canonical_path_pattern = canonical_path_schema.get("pattern")
    canonical_namespace_pattern = canonical_namespace_schema.get("pattern")
    try:
        canonical_path_re = re.compile(str(canonical_path_pattern))
        canonical_namespace_re = re.compile(str(canonical_namespace_pattern))
    except re.error as exc:
        errors.append(f"semantic_plan_canonical_path_pattern_invalid:{exc}")
        canonical_path_re = re.compile(r"(?!)")
        canonical_namespace_re = re.compile(r"(?!)")
    if (
        canonical_path_schema.get("type") != "string"
        or canonical_path_schema.get("minLength") != 1
        or canonical_namespace_schema.get("type") != "string"
        or canonical_namespace_schema.get("minLength") != 1
    ):
        errors.append("semantic_plan_canonical_path_shape_invalid")
    for witness in ("paper/main.tex", ".modeling/state.json", "setup.cfg"):
        if canonical_path_re.fullmatch(witness) is None:
            errors.append(f"semantic_plan_canonical_path_rejects_valid:{witness}")
    for witness in (
        "/absolute", "C:/drive", r"paper\main.tex", "paper//main.tex",
        "paper/./main.tex", "paper/../main.tex", "paper/",
    ):
        if canonical_path_re.fullmatch(witness) is not None:
            errors.append(f"semantic_plan_canonical_path_accepts_alias:{witness}")
    for witness in ("logs", "setup.cfg"):
        if canonical_namespace_re.fullmatch(witness) is None:
            errors.append(f"semantic_plan_extension_namespace_rejects_valid:{witness}")
    for witness in ("logs/run", "..", r"logs\run"):
        if canonical_namespace_re.fullmatch(witness) is not None:
            errors.append(f"semantic_plan_extension_namespace_accepts_invalid:{witness}")

    extension_schema = plan_defs.get("platform_extension", {})
    extension_properties = extension_schema.get("properties", {})
    if (
        extension_schema.get("type") != "object"
        or extension_schema.get("additionalProperties") is not False
        or set(extension_schema.get("required", []))
        != {"approval_quote", "top_level_namespaces", "purpose", "rollback"}
        or set(extension_properties)
        != {"approval_quote", "top_level_namespaces", "purpose", "rollback"}
        or extension_properties.get("approval_quote", {}).get("type") != "string"
        or extension_properties.get("approval_quote", {}).get("minLength") != 2
        or extension_properties.get("approval_quote", {}).get("pattern") != r"\S"
        or extension_properties.get("top_level_namespaces", {}).get("type") != "array"
        or extension_properties.get("top_level_namespaces", {}).get("minItems") != 1
        or extension_properties.get("top_level_namespaces", {}).get("uniqueItems") is not True
        or extension_properties.get("top_level_namespaces", {}).get("items", {}).get("$ref")
        != "#/$defs/canonical_top_level_namespace"
        or extension_properties.get("purpose", {}).get("type") != "string"
        or extension_properties.get("purpose", {}).get("minLength") != 8
        or extension_properties.get("purpose", {}).get("pattern") != r"\S"
        or extension_properties.get("rollback", {}).get("type") != "string"
        or extension_properties.get("rollback", {}).get("minLength") != 8
        or extension_properties.get("rollback", {}).get("pattern") != r"\S"
    ):
        errors.append("semantic_plan_platform_extension_shape_invalid")

    step_properties = plan_defs.get("step", {}).get("properties", {})
    if "state" not in step_properties.get("object", {}).get("enum", []):
        errors.append("semantic_plan_state_object_missing")
    if (
        step_properties.get("facts", {}).get("properties", {}).get(
            "platform_extension", {}
        ).get("$ref")
        != "#/$defs/platform_extension"
    ):
        errors.append("semantic_plan_platform_extension_fact_unbound")
    change_set_paths = plan_defs.get("change_set", {}).get("properties", {}).get("paths", {})
    runtime_scope = plan_defs.get("runtime_action_scope", {}).get("properties", {})
    runtime_cwd = (
        plan_defs.get("runtime_action", {}).get("properties", {})
        .get("command", {}).get("properties", {}).get("cwd", {})
    )
    if (
        change_set_paths.get("items", {}).get("$ref")
        != "#/$defs/canonical_relative_path"
        or runtime_scope.get("input_paths", {}).get("items", {}).get("$ref")
        != "#/$defs/canonical_relative_path"
        or runtime_scope.get("output_paths", {}).get("items", {}).get("$ref")
        != "#/$defs/canonical_relative_path"
        or runtime_cwd.get("anyOf")
        != [{"const": "."}, {"$ref": "#/$defs/canonical_relative_path"}]
    ):
        errors.append("semantic_plan_canonical_path_consumers_unbound")
    if "skill_authorization" not in semantic_plan.get("properties", {}):
        errors.append("semantic_plan_skill_authorization_missing")
    state_schema = load(root / "references/state.schema.json")
    state_identity_path = state_schema.get("$defs", {}).get(
        "canonical_project_relative_path", {}
    )
    artifact_key_schema = (
        state_schema.get("properties", {}).get("artifacts", {}).get("propertyNames", {})
    )
    baseline_key_schema = (
        state_schema.get("properties", {}).get("workspace_baseline", {})
        .get("propertyNames", {})
    )
    state_identity_pattern = state_identity_path.get("pattern")
    state_identity_binding_valid = (
        state_identity_path.get("type") == "string"
        and state_identity_path.get("minLength") == 1
        and state_identity_pattern == CANONICAL_IDENTITY_PATH_PATTERN
        and artifact_key_schema.get("$ref")
        == "#/$defs/canonical_project_relative_path"
        and baseline_key_schema.get("$ref")
        == "#/$defs/canonical_project_relative_path"
    )
    try:
        state_identity_re = re.compile(str(state_identity_pattern))
    except re.error:
        state_identity_binding_valid = False
        state_identity_re = re.compile(r"(?!)")
    for witness in ("paper/main.tex", ".modeling/state.json", "setup.cfg"):
        if state_identity_re.fullmatch(witness) is None:
            state_identity_binding_valid = False
    for witness in (
        "./paper/main.tex", "paper/./main.tex", "paper//main.tex",
        "paper/main.tex/", r"paper\main.tex", "/paper/main.tex",
        "C:/paper/main.tex", "paper/../main.tex", "paper/\x00main.tex",
    ):
        if state_identity_re.fullmatch(witness) is not None:
            state_identity_binding_valid = False
    if not state_identity_binding_valid:
        errors.append("state_identity_path_boundary_invalid")
    execution = state_schema.get("$defs", {}).get("execution", {}).get("properties", {})
    if set(execution.get("status", {}).get("enum", [])) != {"open", "closed", "void"}:
        errors.append("execution_lifecycle_invalid")
    for field in (
        "change_set", "recovery_protocol_version", "window_context", "recovery_run_id",
        "recovery_receipt_hash", "recovery_assessment_hash", "checkpoint_revision",
    ):
        if field not in execution:
            errors.append(f"execution_binding_missing:{field}")
    recovery_receipt = load(root / "references/recovery-receipt.schema.json")
    if recovery_receipt.get("properties", {}).get("receipt_type", {}).get("const") != "r1_targeted_recovery":
        errors.append("recovery_receipt_contract_invalid")
    return policy, sorted(set(errors))


def validate_change_review(
    root: Path, plan: dict[str, Any], required_case_ids: list[str]
) -> list[str]:
    errors: list[str] = []
    review = plan.get("change_review")
    if not isinstance(review, dict):
        return ["change_review_missing"]
    required_fields = {
        "review_kind", "review_status", "risk", "old_behavior", "new_observable_effects",
        "preserved", "retired_or_merged", "unverified", "impact_surfaces",
        "rollback_identity", "authorization", "evidence",
    }
    if set(review) != required_fields:
        errors.append("change_review_field_set_invalid")
    if review.get("review_kind") != "human_reviewed_release_change" or review.get("review_status") != "reviewed":
        errors.append("change_review_identity_invalid")
    for field in (
        "risk", "old_behavior", "new_observable_effects", "preserved",
        "retired_or_merged", "unverified",
    ):
        string_list(review.get(field), f"change_review:{field}", errors)

    evidence = review.get("evidence", {})
    if not isinstance(evidence, dict) or set(evidence) != {"case_ids", "check_ids"}:
        errors.append("change_review_evidence_shape_invalid")
        evidence = {}
    case_ids = string_list(evidence.get("case_ids"), "change_review:case_ids", errors)
    check_ids = string_list(evidence.get("check_ids"), "change_review:check_ids", errors)
    if case_ids != required_case_ids:
        errors.append("change_review_case_binding_drift")
    if not set(check_ids).issubset(CHECK_IDS):
        errors.append("change_review_check_id_unknown")
    required_checks = {
        "CONTRACT.V15.ATOM_INVENTORY", "CONTRACT.V15.ROUTE_REACHABILITY",
        "CONTRACT.V15.CAPABILITY_PACKET_REACHABILITY", "MIGRATION.V15.CLAUSE_PRESERVATION",
    }
    if not required_checks.issubset(check_ids):
        errors.append("change_review_key_checks_missing")
    known_evidence_ids = set(case_ids) | set(check_ids)

    surfaces = review.get("impact_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        errors.append("change_review_impact_surfaces_invalid")
        surfaces = []
    surface_ids: list[str] = []
    for item in surfaces:
        if not isinstance(item, dict) or set(item) != {"surface", "effect", "evidence_ids"}:
            errors.append("change_review_impact_surface_shape_invalid")
            continue
        surface, effect = item.get("surface"), item.get("effect")
        if not isinstance(surface, str) or not surface or not isinstance(effect, str) or not effect:
            errors.append("change_review_impact_surface_value_invalid")
            continue
        surface_ids.append(surface)
        ids = string_list(item.get("evidence_ids"), f"change_review:surface:{surface}", errors)
        if set(ids) - known_evidence_ids:
            errors.append(f"change_review_impact_evidence_unknown:{surface}")
    if len(surface_ids) != len(set(surface_ids)):
        errors.append("change_review_impact_surface_duplicate")

    authorization = review.get("authorization")
    if not isinstance(authorization, dict) or set(authorization) != {"quote", "quote_sha256"}:
        errors.append("change_review_authorization_shape_invalid")
    else:
        quote, claimed = authorization.get("quote"), authorization.get("quote_sha256")
        if not isinstance(quote, str) or len(quote.strip()) < 2:
            errors.append("change_review_authorization_quote_invalid")
        elif claimed != hashlib.sha256(quote.encode("utf-8")).hexdigest():
            errors.append("change_review_authorization_hash_mismatch")

    rollback = review.get("rollback_identity")
    rollback_fields = {"kind", "tree_sha256", "binding_ref", "strategy"}
    if not isinstance(rollback, dict) or set(rollback) != rollback_fields:
        errors.append("change_review_rollback_shape_invalid")
    else:
        if rollback.get("kind") != "external_pre_release_candidate_checkpoint":
            errors.append("change_review_rollback_kind_invalid")
        if HEX64_RE.fullmatch(str(rollback.get("tree_sha256"))) is None:
            errors.append("change_review_rollback_hash_invalid")
        binding_ref = rollback.get("binding_ref")
        bound = referenced_json_value(root, binding_ref)
        if not isinstance(bound, dict):
            errors.append("change_review_rollback_binding_ref_invalid")
        elif bound.get("tree_sha256") != rollback.get("tree_sha256"):
            errors.append("change_review_rollback_binding_mismatch")
        if not isinstance(rollback.get("strategy"), str) or len(rollback["strategy"].strip()) < 12:
            errors.append("change_review_rollback_strategy_invalid")
    return sorted(set(errors))


def validate(root: Path) -> dict[str, Any]:
    all_errors: list[str] = []
    evidence: dict[str, Any] = {}

    policy, binding_errors = validate_release_and_control_bindings(root)
    all_errors.extend(f"CONTRACT.V15.RELEASE_BINDING:{item}" for item in binding_errors)
    policy_case_ids = {
        item for item in policy.get("required_case_ids", []) if isinstance(item, str)
    }
    plan = load(root / "evals/release/release-plan.json")
    review_errors = validate_change_review(root, plan, policy.get("required_case_ids", []))
    all_errors.extend(f"CONTRACT.V15.RELEASE_BINDING:{item}" for item in review_errors)

    runtime = load(root / "references/runtime-policy.json")
    route_contract, route_ids, known_events, route_witnesses, route_errors = validate_route_contract(
        root, runtime
    )
    all_errors.extend(f"CONTRACT.V15.ROUTE_REACHABILITY:{item}" for item in route_errors)

    rules, load_errors = load_rule_corpus(root)
    all_errors.extend(f"CONTRACT.V15.ATOM_INVENTORY:{item}" for item in load_errors)
    ledger = load(root / "references/migration/v15-preservation-ledger.json")
    expected_active = ledger.get("inherited_capabilities", {}).get("expected_active_atom_count", -1)
    rule_metrics, rule_errors = validate_rule_inventory(
        root, rules, route_ids, known_events, policy_case_ids, expected_active
    )
    all_errors.extend(f"CONTRACT.V15.ATOM_INVENTORY:{item}" for item in rule_errors)
    reachable, reachability_errors = validate_active_reachability(rules, route_contract, runtime)
    all_errors.extend(f"CONTRACT.V15.ROUTE_REACHABILITY:{item}" for item in reachability_errors)
    rule_metrics["reachable_active_rules"] = reachable
    evidence["rule_inventory"] = rule_metrics
    evidence["route_actions_with_witnesses"] = route_witnesses
    evidence["routes"] = len(route_ids)
    evidence["known_events"] = len(known_events)

    packet_metrics, packet_errors = validate_capability_packets(root, rules, route_contract)
    all_errors.extend(
        f"CONTRACT.V15.CAPABILITY_PACKET_REACHABILITY:{item}" for item in packet_errors
    )
    evidence["capability_packets"] = packet_metrics

    mutation_passed, mutation_errors = validate_runtime_near_negatives(root)
    all_errors.extend(f"CONTRACT.V15.RUNTIME_NEAR_NEGATIVES:{item}" for item in mutation_errors)
    evidence["runtime_near_negative_cases"] = {
        "declared": len(POLICY_MUTATIONS), "passed": mutation_passed
    }

    preservation_metrics, preservation_errors = validate_preservation(root, rules, policy_case_ids)
    all_errors.extend(
        f"MIGRATION.V15.CLAUSE_PRESERVATION:{item}" for item in preservation_errors
    )
    evidence["preservation"] = preservation_metrics

    errors = sorted(set(all_errors))
    return {
        "schema_version": SCHEMA_VERSION,
        "driver": "contracts",
        "status": "pass" if not errors else "fail",
        "checks": [
            "CONTRACT.V15.RELEASE_BINDING",
            "CONTRACT.V15.CONTROL_BINDINGS",
            "CONTRACT.V15.ATOM_INVENTORY",
            "CONTRACT.V15.ROUTE_REACHABILITY",
            "CONTRACT.V15.CAPABILITY_PACKET_REACHABILITY",
            "CONTRACT.V15.RUNTIME_NEAR_NEGATIVES",
            "MIGRATION.V15.CLAUSE_PRESERVATION",
        ],
        "evidence": evidence,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    try:
        result = validate(root)
    except Exception as exc:
        result = {
            "schema_version": SCHEMA_VERSION,
            "driver": "contracts",
            "status": "fail",
            "checks": sorted(CHECK_IDS - {
                "PACKAGE.V15.REQUIRED", "PACKAGE.V15.JSON", "PACKAGE.V15.PYTHON",
                "PACKAGE.V15.IDENTITY_AND_LINKS",
            }),
            "evidence": {},
            "errors": [f"CONTRACT.V15.INTERNAL:{type(exc).__name__}:{exc}"],
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
