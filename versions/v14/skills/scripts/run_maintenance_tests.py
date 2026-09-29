#!/usr/bin/env python3
"""Mutation-test the V11 runtime boundaries that prevent V10 over-triggering."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any


DOCUMENTS = {
    "runtime": "references/runtime-policy.json",
    "route": "references/route-contract.json",
    "artifact": "references/artifact-contract.json",
    "state_machine": "references/state-machine.json",
    "manuscript": "references/manuscript-change-closure.json",
    "receipt": "references/receipt.schema.json",
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_policy(documents: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    runtime = documents["runtime"]
    route = documents["route"]
    artifact = documents["artifact"]
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
    delivery = actions.get("RT.DELIVERY.FINAL", {})
    if any(details.get("minimum_tier") != "G3_RELEASE" for details in delivery.values()):
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
    ):
        errors.append("skill_package_boundary_not_isolated")
    non_derivation = set(runtime_actions.get("non_derivation_actions", []))
    if not {"resume", "recover", "handoff", "pause", "close_s6"}.issubset(non_derivation):
        errors.append("control_action_can_derive_dangerous_command")
    controller_only = set(route.get("event_prerequisites", {}).get("controller_only_events", []))
    if not {"request_received", "route_resolution", "route_execution", "before_write", "before_file_creation"}.issubset(controller_only):
        errors.append("controller_events_user_declarable")
    skill_adapter = route.get("legacy_scope_adapters", {}).get("skill_state", {})
    if skill_adapter.get("actual_state") != "V11" or skill_adapter.get("frozen_scope_token") != "V10":
        errors.append("maintenance_scope_adapter_missing")
    data_adapter = route.get("legacy_trigger_adapters", {}).get("DATA.IDENTITY.BEFORE_USE", {})
    if data_adapter.get("coarse_controller_event") != "route_execution" or data_adapter.get("when_fact_true") != "consumes_data":
        errors.append("data_use_trigger_adapter_missing")

    tiers = runtime.get("tiers", {})
    g0 = tiers.get("G0_ADVISORY", {})
    g1 = tiers.get("G1_WORKING", {})
    if g0.get("project_state") != "not_required":
        errors.append("g0_project_state_required")
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
    reconstruction = barrier.get("identity_reconstruction", {})
    if reconstruction.get("recomputation_authorized") is not False:
        errors.append("r2_recomputation_implicitly_authorized")
    if barrier.get("allowed_write_paths") != [".modeling/state.json"]:
        errors.append("r2_control_write_scope_expanded")
    dangerous = runtime.get("dangerous_runtime_actions", {})
    if dangerous.get("ordinary_g1_affected") is not False or dangerous.get("grant_persistence_at_g1") != "none":
        errors.append("dangerous_guard_became_g1_ledger")

    artifact_policy = artifact.get("policy", {})
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
    facet_map = manuscript.get("facet_to_legacy_event")
    required_facets = {
        "method": "method_section_write",
        "result": "result_section_write",
        "conclusion": "conclusion_write",
        "structure": "manuscript_structure",
    }
    if not isinstance(facet_map, dict) or any(facet_map.get(key) != value for key, value in required_facets.items()):
        errors.append("manuscript_facet_event_adapter_missing")

    receipt_tiers = receipt.get("$defs", {}).get("tier", {}).get("enum")
    if receipt_tiers != ["G2_CHECKPOINT", "G3_RELEASE"]:
        errors.append("receipt_tier_scope_not_g2_g3")
    return sorted(set(errors))


def set_path(document: Any, path: list[str], value: Any) -> None:
    current = document
    for key in path[:-1]:
        if not isinstance(current, dict) or key not in current:
            raise KeyError("/".join(path))
        current = current[key]
    if not isinstance(current, dict) or not path:
        raise KeyError("/".join(path))
    current[path[-1]] = value


def run(root: Path, selected: set[str] | None = None) -> dict[str, Any]:
    documents = {name: read_json(root / relative) for name, relative in DOCUMENTS.items()}
    base_errors = validate_policy(documents)
    payload = read_json(root / "evals/runtime-policy-cases.json")
    all_cases = payload.get("cases", []) if isinstance(payload, dict) else []
    cases = [
        case for case in all_cases
        if isinstance(case, dict) and (selected is None or case.get("id") in selected)
    ]
    results: list[dict[str, Any]] = []
    for case in cases:
        failures: list[str] = []
        mutated = copy.deepcopy(documents)
        try:
            set_path(
                mutated[case["document"]],
                case["mutation"]["path"],
                case["mutation"]["value"],
            )
            observed = validate_policy(mutated)
        except (KeyError, TypeError) as exc:
            observed = []
            failures.append(f"mutation_invalid:{exc}")
        expected = case.get("expected_error")
        if expected not in observed:
            failures.append(f"expected_error_not_detected:{expected}")
        results.append({
            "id": case.get("id", "<missing>"),
            "status": "pass" if not failures else "fail",
            "failures": failures,
            "expected_error": expected,
        })
    ids = [case.get("id") for case in all_cases if isinstance(case, dict)]
    declaration_errors: list[str] = []
    if not ids or len(ids) != len(set(ids)):
        declaration_errors.append("policy_case_ids_invalid")
    if base_errors:
        declaration_errors.extend("base_policy:" + item for item in base_errors)
    failed = [item for item in results if item["status"] != "pass"]
    return {
        "schema_version": "11.0",
        "status": "pass" if not declaration_errors and not failed else "fail",
        "driver": "runtime_policy_mutations",
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed) + len(declaration_errors),
        "errors": declaration_errors,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    report = run(args.root.resolve(), set(args.case) if args.case else None)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
