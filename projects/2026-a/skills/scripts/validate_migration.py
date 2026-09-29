#!/usr/bin/env python3
"""Validate V15 semantic preservation and legacy lineage without eval self-proof."""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from build_migration_coverage import (
    BLOCKING_DISPOSITIONS,
    FINAL_DISPOSITIONS,
    NATIVE_V7_V8_DISPOSITIONS,
    STRENGTH_WAIVERS,
    SPAN_RECORD_FIELDS,
    SPAN_STATUS_CODEBOOK,
    TRUSTED_V1_V6_LINEAGE_PROJECTION_SHA256,
    TRUSTED_V7_V8_NATIVE_PROJECTION_SHA256,
    TRUSTED_V9_LEDGER_SHA256,
    TRUSTED_V9_NATIVE_SHA256,
    TRUSTED_V9_REGISTRY_PROJECTION_SHA256,
    TRUSTED_V9_REGISTRY_SHA256,
    atom_contract,
    build_baseline,
    build_crosswalk,
    build_lineage,
    canonical_sha256,
    capability_disposition,
    capability_contract,
    origin_assignment_projection,
    semantic_atom_contract,
    semantic_binding_projection,
    strength_waiver,
    verify_trusted_sources,
)
from lib_v10 import SKILL_ROOT, json_output, load_json, load_rules, sha256_file, sha256_text


HEX64 = re.compile(r"^[0-9a-f]{64}$")


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def verify_seal(name: str, artifact: Any, errors: list[str]) -> None:
    if not isinstance(artifact, dict):
        errors.append(f"{name}:not_object")
        return
    stored = artifact.get("payload_sha256")
    payload = {key: value for key, value in artifact.items() if key != "payload_sha256"}
    if not valid_hash(stored) or stored != canonical_sha256(payload):
        errors.append(f"{name}:payload_tampered")


def validate_baseline(baseline: dict[str, Any], errors: list[str]) -> dict[str, dict[str, Any]]:
    if baseline.get("schema_version") != "10.1" or baseline.get("artifact_kind") != "v9_reviewed_capability_baseline":
        errors.append("baseline:identity")
    if baseline.get("source_file_sha256") != TRUSTED_V9_REGISTRY_SHA256:
        errors.append("baseline:v9_registry_source_hash")
    if baseline.get("source_projection_sha256") != TRUSTED_V9_REGISTRY_PROJECTION_SHA256:
        errors.append("baseline:v9_registry_projection_hash")
    if baseline.get("review_basis") != "inherited_v9_capability_registry":
        errors.append("baseline:review_basis")
    capabilities = baseline.get("capabilities")
    if not isinstance(capabilities, list) or len(capabilities) != 51:
        errors.append("baseline:capability_count")
        capabilities = capabilities if isinstance(capabilities, list) else []
    by_id: dict[str, dict[str, Any]] = {}
    for item in capabilities:
        if not isinstance(item, dict):
            errors.append("baseline:capability_not_object")
            continue
        capability_id = item.get("id")
        if not isinstance(capability_id, str):
            errors.append("baseline:capability_id_missing")
            continue
        if capability_id in by_id:
            errors.append(f"baseline:duplicate_capability:{capability_id}")
        by_id[capability_id] = item
        try:
            contract = capability_contract(item)
        except KeyError as exc:
            errors.append(f"{capability_id}:baseline_contract_field_missing:{exc.args[0]}")
            continue
        if not all(isinstance(contract[field], str) and contract[field] for field in contract):
            errors.append(f"{capability_id}:baseline_contract_empty")
        if item.get("contract_sha256") != canonical_sha256(contract):
            errors.append(f"{capability_id}:baseline_contract_tampered")
    projection = [capability_contract(item) for item in capabilities if isinstance(item, dict) and all(field in item for field in ("id", "domain", "owner", "strength", "trigger", "expected", "forbidden"))]
    if canonical_sha256(projection) != TRUSTED_V9_REGISTRY_PROJECTION_SHA256:
        errors.append("baseline:trusted_projection_content_mismatch")
    return by_id


def validate_current_inventory(
    root: Path,
    rules: list[dict[str, Any]],
    baseline_ids: set[str],
    errors: list[str],
) -> set[str]:
    """Validate current atom identity without consulting an eval registry."""
    route_contract = load_json(root / "references/route-contract.json")
    route_ids = {
        item.get("id") for item in route_contract.get("routes", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    allowed_route_selectors = {"*", "@write", "@recovery"}
    active = [rule for rule in rules if rule.get("status") == "active"]
    if len(active) != 214:
        errors.append(f"inventory:active_atom_count:{len(active)}!=214")
    for rule in rules:
        atom_id = rule.get("id", "<missing>")
        bundle = rule.get("_bundle")
        expected_owner = f"{bundle}#{atom_id}"
        if rule.get("owner") != expected_owner:
            errors.append(f"{atom_id}:owner_mismatch:{rule.get('owner')}!={expected_owner}")
        if not isinstance(bundle, str) or not (root / bundle).is_file():
            errors.append(f"{atom_id}:owner_bundle_missing:{bundle}")
        elif rule.get("domain") != load_json(root / bundle).get("domain"):
            errors.append(f"{atom_id}:owner_bundle_domain_mismatch")
        if rule.get("strength") not in {"MUST", "SHOULD", "MAY"}:
            errors.append(f"{atom_id}:strength_invalid")
        routes = rule.get("routes", [])
        if not isinstance(routes, list) or not routes:
            errors.append(f"{atom_id}:routes_missing")
        else:
            unknown = set(routes) - route_ids - allowed_route_selectors
            if unknown:
                errors.append(f"{atom_id}:routes_unknown:{','.join(sorted(unknown))}")
        capability = rule.get("capability")
        if capability not in baseline_ids:
            errors.append(f"{atom_id}:capability_outside_reviewed_baseline:{capability}")
        enforcement = rule.get("enforcement", {})
        refs = enforcement.get("refs", []) if isinstance(enforcement, dict) else []
        if not isinstance(refs, list) or not refs:
            errors.append(f"{atom_id}:enforcement_refs_missing")
        else:
            for reference in refs:
                relative = str(reference).split("#", 1)[0]
                if not (root / relative).is_file():
                    errors.append(f"{atom_id}:enforcement_ref_missing:{reference}")
        origin = "legacy_family" if capability in baseline_ids else "gap"
        if not valid_hash(canonical_sha256(semantic_atom_contract(rule, origin))):
            errors.append(f"{atom_id}:semantic_projection_invalid")
    return route_ids


def validate_clause_preservation(
    root: Path,
    baseline: dict[str, Any],
    clause_artifact: dict[str, Any],
    rules: list[dict[str, Any]],
    errors: list[str],
) -> None:
    """Make the independently reviewed clause seal the semantic migration gate."""
    from build_clause_preservation import (
        EXPECTED_REVIEW_PROJECTION_SHA256,
        REVIEW,
        build_artifact,
        review_source_inventory,
    )

    if (
        clause_artifact.get("schema_version") != "15.0"
        or clause_artifact.get("artifact_kind") != "v9_clause_preservation_and_v15_atom_necessity"
    ):
        errors.append("clause_preservation:identity")
    if clause_artifact.get("source_baseline_payload_sha256") != baseline.get("payload_sha256"):
        errors.append("clause_preservation:baseline_binding")
    if clause_artifact.get("review") != REVIEW:
        errors.append("clause_preservation:review_record")
    expected_review_sources = review_source_inventory(root)
    if clause_artifact.get("review_sources") != expected_review_sources:
        errors.append("clause_preservation:review_sources")
    if clause_artifact.get("review_source_inventory_sha256") != canonical_sha256(expected_review_sources):
        errors.append("clause_preservation:review_source_inventory_hash")
    current_match = re.fullmatch(r"V([0-9]+)-CLAUSE-REVIEW-([0-9]{3})", str(REVIEW.get("decision_id", "")))
    previous_match = re.fullmatch(r"V([0-9]+)-CLAUSE-REVIEW-([0-9]{3})", str(REVIEW.get("previous_decision_id", "")))
    review_sequence_valid = False
    if current_match is not None and previous_match is not None:
        current_major, current_sequence = map(int, current_match.groups())
        previous_major, previous_sequence = map(int, previous_match.groups())
        review_sequence_valid = (
            (current_major == previous_major and current_sequence == previous_sequence + 1)
            or (current_major > previous_major and current_sequence == 1)
        )
    if (
        current_match is None
        or previous_match is None
        or not review_sequence_valid
        or REVIEW.get("release") != f"V{current_match.group(1)}.0.0-candidate"
        or not isinstance(REVIEW.get("rationale"), str)
        or len(REVIEW["rationale"]) < 20
    ):
        errors.append("clause_preservation:review_identity_or_sequence")

    try:
        expected, review_hash = build_artifact(root, baseline)
    except Exception as exc:
        errors.append(f"clause_preservation:build_error:{exc}")
        return
    if review_hash != EXPECTED_REVIEW_PROJECTION_SHA256:
        errors.append("clause_preservation:normative_semantics_require_versioned_reseal")
    if clause_artifact.get("review_projection_sha256") != review_hash:
        errors.append("clause_preservation:review_projection_hash")
    if clause_artifact != expected:
        errors.append("clause_preservation:compiled_content_tampered_or_stale")

    allowed = set(clause_artifact.get("allowed_relations", []))
    blocking = set(clause_artifact.get("blocking_relations", []))
    if allowed != {"equal", "broader", "corrected_overconstraint", "corrected_binding_overconstraint"} or blocking != {"missing", "narrower", "weaker", "unreviewed"}:
        errors.append("clause_preservation:relation_codebook")
    clauses = clause_artifact.get("clauses", [])
    if not isinstance(clauses, list) or len(clauses) != 302:
        errors.append("clause_preservation:source_clause_count")
        clauses = clauses if isinstance(clauses, list) else []
    for clause in clauses:
        if not isinstance(clause, dict):
            errors.append("clause_preservation:clause_not_object")
            continue
        if clause.get("review_status") != "reviewed" or clause.get("relation") not in allowed:
            errors.append(f"{clause.get('id', '<missing>')}:blocking_clause_relation")
        if not clause.get("atom_ids"):
            errors.append(f"{clause.get('id', '<missing>')}:uncovered_source_clause")

    active = {rule["id"]: rule for rule in rules if rule.get("status") == "active"}
    atom_rows = clause_artifact.get("atom_reviews", [])
    if not isinstance(atom_rows, list):
        errors.append("clause_preservation:atom_reviews_not_array")
        atom_rows = []
    if {row.get("atom_id") for row in atom_rows if isinstance(row, dict)} != set(active):
        errors.append("clause_preservation:active_atom_bijection")
    baseline_ids = {item["id"] for item in baseline.get("capabilities", []) if isinstance(item, dict)}
    for row in atom_rows:
        if not isinstance(row, dict):
            continue
        atom_id = row.get("atom_id")
        rule = active.get(atom_id)
        if rule is None:
            continue
        expected_origin = "legacy_family" if rule["capability"] in baseline_ids else "native_v10"
        if row.get("origin") != expected_origin:
            errors.append(f"{atom_id}:clause_review_origin")
        if row.get("semantic_sha256") != canonical_sha256(semantic_atom_contract(rule, expected_origin)):
            errors.append(f"{atom_id}:clause_review_semantic_hash")
        expected_fields = {
            "capability_id": rule["capability"],
            "domain": rule["domain"],
            "owner": rule["owner"],
            "revision": rule["revision"],
            "strength": rule["strength"],
            "routes": sorted(set(rule.get("routes", []))),
        }
        for field, expected_value in expected_fields.items():
            if row.get(field) != expected_value:
                errors.append(f"{atom_id}:clause_review_{field}")
        if row.get("review_status") != "reviewed":
            errors.append(f"{atom_id}:clause_review_status")
    for defect in clause_artifact.get("defects", []):
        if not isinstance(defect, dict):
            errors.append("clause_preservation:defect_not_object")
            continue
        defect_id = defect.get("id", "<missing>")
        if not defect.get("atom_ids"):
            errors.append(f"{defect_id}:defect_atom_binding_missing")
        for atom_id in defect.get("atom_ids", []):
            if atom_id not in active:
                errors.append(f"{defect_id}:defect_atom_missing:{atom_id}")
        bindings = defect.get("source_bindings", [])
        if not bindings:
            errors.append(f"{defect_id}:defect_source_binding_missing")
        for binding in bindings:
            relative = binding.get("path") if isinstance(binding, dict) else None
            path = root / relative if isinstance(relative, str) else root / "__invalid__"
            if not path.is_file() or binding.get("sha256") != sha256_file(path):
                errors.append(f"{defect_id}:defect_source_binding_invalid:{relative}")


def validate_crosswalk(
    root: Path,
    baseline: dict[str, Any],
    baseline_by_id: dict[str, dict[str, Any]],
    clause_artifact: dict[str, Any],
    crosswalk: dict[str, Any],
    rules: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    if crosswalk.get("schema_version") != "15.0" or crosswalk.get("artifact_kind") != "v9_to_v15_capability_crosswalk":
        errors.append("crosswalk:identity")
    if crosswalk.get("source_baseline_projection_sha256") != baseline.get("source_projection_sha256"):
        errors.append("crosswalk:baseline_binding")
    assignment_projection = origin_assignment_projection(rules, set(baseline_by_id))
    assignment_sha256 = canonical_sha256(assignment_projection)
    if crosswalk.get("origin_assignment_sha256") != assignment_sha256:
        errors.append("crosswalk:origin_assignment_content_hash")
    semantic_sha256 = canonical_sha256(semantic_binding_projection(rules, set(baseline_by_id)))
    if crosswalk.get("semantic_binding_sha256") != semantic_sha256:
        errors.append("crosswalk:semantic_binding_content_hash")
    expected_clause_ref = {
        "path": "references/migration/clause-preservation.json",
        "payload_sha256": clause_artifact.get("payload_sha256"),
        "review_projection_sha256": clause_artifact.get("review_projection_sha256"),
        "review_source_inventory_sha256": clause_artifact.get("review_source_inventory_sha256"),
        "review_decision_id": clause_artifact.get("review", {}).get("decision_id"),
    }
    if crosswalk.get("clause_preservation_ref") != expected_clause_ref:
        errors.append("crosswalk:clause_preservation_binding")
    if set(crosswalk.get("allowed_dispositions", [])) != FINAL_DISPOSITIONS:
        errors.append("crosswalk:allowed_dispositions")
    if set(crosswalk.get("blocking_dispositions", [])) != BLOCKING_DISPOSITIONS:
        errors.append("crosswalk:blocking_dispositions")
    expected_waivers = [STRENGTH_WAIVERS[key] for key in sorted(STRENGTH_WAIVERS)]
    if crosswalk.get("strength_waivers") != expected_waivers:
        errors.append("crosswalk:strength_waivers_tampered")

    expected_crosswalk = build_crosswalk(baseline, rules, clause_artifact)
    if crosswalk != expected_crosswalk:
        errors.append("crosswalk:compiled_content_tampered_or_stale")
    if crosswalk.get("rule_inventory_sha256") != canonical_sha256(
        [atom_contract(item) for item in sorted(rules, key=lambda item: item["id"])]
    ):
        errors.append("crosswalk:rule_inventory_hash")

    rows = crosswalk.get("capabilities", [])
    if not isinstance(rows, list):
        errors.append("crosswalk:capabilities_not_array")
        rows = []
    calculated_binding_sha256 = canonical_sha256(rows)
    if crosswalk.get("capability_binding_sha256") != calculated_binding_sha256:
        errors.append("crosswalk:capability_binding_content_hash")
    row_ids = [item.get("capability_id") for item in rows if isinstance(item, dict)]
    if len(row_ids) != len(set(row_ids)):
        errors.append("crosswalk:duplicate_capability")
    if set(row_ids) != set(baseline_by_id):
        errors.append("crosswalk:capability_set_mismatch")
    active_by_capability: dict[str, list[str]] = defaultdict(list)
    for rule in rules:
        if rule.get("status") == "active":
            active_by_capability[rule["capability"]].append(rule["id"])

    for row in rows:
        if not isinstance(row, dict):
            continue
        capability_id = row.get("capability_id", "<missing>")
        source = baseline_by_id.get(capability_id)
        disposition = row.get("disposition")
        if disposition in BLOCKING_DISPOSITIONS:
            errors.append(f"{capability_id}:blocking_disposition:{disposition}")
        elif disposition not in FINAL_DISPOSITIONS:
            errors.append(f"{capability_id}:unknown_disposition:{disposition}")
        if source is None:
            continue
        if row.get("mapping_basis") != "explicit_rule_capability_field":
            errors.append(f"{capability_id}:mapping_basis_not_explicit")
        if row.get("source_contract_sha256") != source.get("contract_sha256"):
            errors.append(f"{capability_id}:source_contract_hash")
        if row.get("expected_sha256") != sha256_text(source["expected"]):
            errors.append(f"{capability_id}:expected_contract_hash")
        if row.get("forbidden_sha256") != sha256_text(source["forbidden"]):
            errors.append(f"{capability_id}:forbidden_contract_hash")
        atom_ids = row.get("atom_ids", [])
        expected_atom_ids = sorted(active_by_capability.get(capability_id, []))
        if atom_ids != expected_atom_ids:
            errors.append(f"{capability_id}:atom_mapping_not_exact")
        if not atom_ids:
            errors.append(f"{capability_id}:no_active_atom")
        expected_disposition = capability_disposition(len(atom_ids), row.get("strength_relation", "unbound"))
        if disposition != expected_disposition:
            errors.append(f"{capability_id}:structural_disposition:{disposition}!={expected_disposition}")
        expected_basis = (
            "explicit_one_to_one_binding" if disposition == "preserved_exactly"
            else "explicit_atom_split" if disposition == "split_into"
            else "normative_strength_changed" if disposition == "transformed"
            else "no_active_atom"
        )
        if row.get("disposition_basis") != expected_basis:
            errors.append(f"{capability_id}:disposition_basis")
        if row.get("semantic_equivalence_claimed") is not False:
            errors.append(f"{capability_id}:semantic_equivalence_claim")
        if row.get("semantic_preservation_basis") != "reviewed_clause_preservation_artifact":
            errors.append(f"{capability_id}:semantic_preservation_basis")
        try:
            waiver = strength_waiver(capability_id, row.get("strength_relation", "unbound"))
        except ValueError as exc:
            errors.append(str(exc))
            waiver = None
        expected_waiver_id = waiver["waiver_id"] if waiver else None
        if row.get("strength_waiver_id") != expected_waiver_id:
            errors.append(f"{capability_id}:strength_waiver_binding")
        if row.get("strength_relation") == "contains_weaker" and waiver is None:
            errors.append(f"{capability_id}:unwaived_strength_regression")
        bindings = row.get("atom_bindings", [])
        binding_ids = [item.get("atom_id") for item in bindings if isinstance(item, dict)]
        if binding_ids != atom_ids:
            errors.append(f"{capability_id}:atom_bindings_not_bijective")
        for binding in bindings:
            if not isinstance(binding, dict):
                errors.append(f"{capability_id}:atom_binding_not_object")
                continue
            atom_id = binding.get("atom_id")
            atom = by_id.get(atom_id)
            if atom is None or atom.get("status") != "active" or atom.get("capability") != capability_id:
                errors.append(f"{capability_id}:{atom_id}:binding_target_invalid")
                continue
            checks = {
                "revision": atom["revision"],
                "strength": atom["strength"],
                "owner": atom["owner"],
                "routes": sorted(set(atom.get("routes", []))),
                "effect_sha256": canonical_sha256(atom["effect"]),
                "semantic_sha256": canonical_sha256(semantic_atom_contract(atom, "legacy_family")),
                "atom_contract_sha256": canonical_sha256(atom_contract(atom)),
            }
            for field, expected in checks.items():
                if binding.get(field) != expected:
                    errors.append(f"{capability_id}:{atom_id}:{field}_mismatch")

    reverse = crosswalk.get("reverse_atoms", [])
    if not isinstance(reverse, list):
        errors.append("crosswalk:reverse_atoms_not_array")
        reverse = []
    reverse_ids = [item.get("atom_id") for item in reverse if isinstance(item, dict)]
    if len(reverse_ids) != len(set(reverse_ids)) or set(reverse_ids) != set(by_id):
        errors.append("crosswalk:reverse_atoms_not_bijective")
    for item in reverse:
        if not isinstance(item, dict):
            continue
        atom_id = item.get("atom_id")
        atom = by_id.get(atom_id)
        if atom is None:
            continue
        capability_id = atom["capability"]
        if capability_id in baseline_by_id:
            expected_origin = "legacy_family"
            if capability_id not in atom.get("legacy_refs", []):
                errors.append(f"{atom_id}:legacy_family_missing_legacy_ref")
        elif capability_id.startswith("V10-"):
            expected_origin = "native_v10"
            if atom.get("legacy_refs"):
                errors.append(f"{atom_id}:native_v10_has_legacy_refs")
        else:
            expected_origin = "gap"
        if item.get("origin") != expected_origin:
            errors.append(f"{atom_id}:reverse_origin:{item.get('origin')}!={expected_origin}")
        if expected_origin == "gap":
            errors.append(f"{atom_id}:reverse_origin_gap")
        if item.get("capability_id") != capability_id:
            errors.append(f"{atom_id}:reverse_capability_mismatch")
        if item.get("atom_status") != atom["status"]:
            errors.append(f"{atom_id}:reverse_status_mismatch")
        expected_projection = {
            "owner": atom["owner"],
            "routes": sorted(set(atom.get("routes", []))),
            "semantic_sha256": canonical_sha256(semantic_atom_contract(atom, expected_origin)),
        }
        for field, expected_value in expected_projection.items():
            if item.get(field) != expected_value:
                errors.append(f"{atom_id}:reverse_{field}_mismatch")
        if item.get("atom_contract_sha256") != canonical_sha256(atom_contract(atom)):
            errors.append(f"{atom_id}:reverse_contract_hash")


def flatten_lineage_groups(lineage: dict[str, Any], errors: list[str]) -> list[dict[str, Any]]:
    section = lineage.get("v1_v6_lineage", {})
    if section.get("disposition") != "context_only" or section.get("semantic_equivalence_claimed") is not False:
        errors.append("lineage:v1_v6_claim_boundary")
    if section.get("span_record_fields") != list(SPAN_RECORD_FIELDS):
        errors.append("lineage:span_record_fields")
    if section.get("status_codebook") != SPAN_STATUS_CODEBOOK:
        errors.append("lineage:status_codebook")
    groups = section.get("owner_families", [])
    if not isinstance(groups, list):
        errors.append("lineage:owner_families_not_array")
        return []
    spans: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for group in groups:
        owner = group.get("v9_owner_family") if isinstance(group, dict) else None
        if not isinstance(owner, str) or not owner:
            errors.append("lineage:owner_family_missing")
            continue
        if group.get("disposition") != "context_only" or group.get("semantic_equivalence_claimed") is not False:
            errors.append(f"lineage:{owner}:claim_boundary")
        owner_spans: list[dict[str, Any]] = []
        for source in group.get("source_files", []):
            source_file = source.get("source_file")
            source_hash = source.get("source_sha256")
            if not isinstance(source_file, str) or not source_file or not valid_hash(source_hash):
                errors.append(f"lineage:{owner}:source_identity")
            file_spans = source.get("spans", [])
            if source.get("span_count") != len(file_spans):
                errors.append(f"lineage:{owner}:{source_file}:span_count")
            for raw_span in file_spans:
                if not isinstance(raw_span, list) or len(raw_span) != len(SPAN_RECORD_FIELDS):
                    errors.append(f"lineage:{owner}:{source_file}:span_shape")
                    continue
                legacy_id, start_line, end_line, text_hash, review_code, treatment_code, migration_code = raw_span
                if not isinstance(legacy_id, str) or legacy_id in seen_ids:
                    errors.append(f"lineage:duplicate_or_missing_span:{legacy_id}")
                else:
                    seen_ids.add(legacy_id)
                if not all(isinstance(value, int) and value >= 1 for value in (start_line, end_line)) or start_line > end_line:
                    errors.append(f"lineage:{legacy_id}:lines")
                if not valid_hash(text_hash):
                    errors.append(f"lineage:{legacy_id}:text_hash")
                if review_code not in SPAN_STATUS_CODEBOOK["v9_review_status"]:
                    errors.append(f"lineage:{legacy_id}:review_status")
                if treatment_code not in SPAN_STATUS_CODEBOOK["v9_treatment"]:
                    errors.append(f"lineage:{legacy_id}:treatment")
                if migration_code not in SPAN_STATUS_CODEBOOK["v9_migration_status"]:
                    errors.append(f"lineage:{legacy_id}:migration_status")
                span = {
                    "legacy_id": legacy_id,
                    "start_line": start_line,
                    "end_line": end_line,
                    "text_sha256": text_hash,
                    "v9_review_status": SPAN_STATUS_CODEBOOK["v9_review_status"].get(review_code),
                    "v9_treatment": SPAN_STATUS_CODEBOOK["v9_treatment"].get(treatment_code),
                    "v9_migration_status": SPAN_STATUS_CODEBOOK["v9_migration_status"].get(migration_code),
                }
                owner_spans.append(span)
                spans.append(span)
        if group.get("span_count") != len(owner_spans):
            errors.append(f"lineage:{owner}:owner_span_count")
        observed_counts = Counter(item.get("v9_review_status") for item in owner_spans)
        if group.get("v9_review_counts") != dict(sorted(observed_counts.items())):
            errors.append(f"lineage:{owner}:review_counts")
    if section.get("span_count") != len(spans) or len(spans) != 1859:
        errors.append(f"lineage:v1_v6_span_count:{len(spans)}")
    if section.get("owner_family_count") != len(groups):
        errors.append("lineage:owner_family_count")
    calculated_projection = canonical_sha256(groups)
    if section.get("projection_sha256") != calculated_projection:
        errors.append("lineage:v1_v6_projection_tampered")
    if calculated_projection != TRUSTED_V1_V6_LINEAGE_PROJECTION_SHA256:
        errors.append("lineage:v1_v6_projection_not_trusted")
    return spans


def validate_native_dispositions(
    root: Path,
    lineage: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    rows = lineage.get("v7_v8_dispositions", [])
    if not isinstance(rows, list):
        errors.append("lineage:v7_v8_not_array")
        return
    row_ids = [item.get("legacy_id") for item in rows if isinstance(item, dict)]
    if len(row_ids) != len(set(row_ids)) or set(row_ids) != set(NATIVE_V7_V8_DISPOSITIONS):
        errors.append("lineage:v7_v8_id_set")
    source_projection = []
    for row in rows:
        if not isinstance(row, dict):
            errors.append("lineage:v7_v8_row_not_object")
            continue
        legacy_id = row.get("legacy_id", "<missing>")
        decision = NATIVE_V7_V8_DISPOSITIONS.get(legacy_id)
        source_projection.append({
            "capability_id": row.get("legacy_id"),
            "introduced_in": row.get("introduced_in"),
            "capability": row.get("source_capability"),
            "source": row.get("source"),
            "v9_owner": row.get("v9_owner"),
            "migration_status": row.get("v9_migration_status"),
        })
        disposition = row.get("disposition")
        if disposition in BLOCKING_DISPOSITIONS:
            errors.append(f"{legacy_id}:blocking_disposition:{disposition}")
        elif disposition not in FINAL_DISPOSITIONS:
            errors.append(f"{legacy_id}:unknown_disposition:{disposition}")
        if row.get("review_basis") != "inherited_v9_native_registry" or row.get("mapping_basis") != "explicit_v15_semantic_binding":
            errors.append(f"{legacy_id}:review_or_mapping_basis")
        if decision is None:
            continue
        for field in ("disposition", "atom_ids", "artifact_refs", "rationale"):
            if row.get(field) != decision[field]:
                errors.append(f"{legacy_id}:{field}_decision_tampered")
        bindings = row.get("atom_bindings", [])
        binding_ids = [item.get("atom_id") for item in bindings if isinstance(item, dict)]
        if binding_ids != row.get("atom_ids", []):
            errors.append(f"{legacy_id}:atom_bindings_not_bijective")
        for atom_id in row.get("atom_ids", []):
            atom = by_id.get(atom_id)
            if atom is None or atom.get("status") != "active":
                errors.append(f"{legacy_id}:atom_inactive_or_missing:{atom_id}")
        for binding in bindings:
            if not isinstance(binding, dict):
                errors.append(f"{legacy_id}:atom_binding_not_object")
                continue
            atom_id = binding.get("atom_id")
            atom = by_id.get(atom_id)
            if atom is None:
                continue
            expected = {
                "owner": atom["owner"],
                "strength": atom["strength"],
                "routes": sorted(set(atom.get("routes", []))),
                "semantic_sha256": canonical_sha256(semantic_atom_contract(atom, "legacy_family")),
            }
            for field, expected_value in expected.items():
                if binding.get(field) != expected_value:
                    errors.append(f"{legacy_id}:{atom_id}:{field}_mismatch")
        for artifact in row.get("artifact_refs", []):
            if not isinstance(artifact, str) or not (root / artifact).is_file():
                errors.append(f"{legacy_id}:artifact_missing:{artifact}")
        if not isinstance(row.get("rationale"), str) or len(row["rationale"]) < 20:
            errors.append(f"{legacy_id}:rationale_missing")
    source_projection.sort(key=lambda item: str(item["capability_id"]))
    if canonical_sha256(source_projection) != TRUSTED_V7_V8_NATIVE_PROJECTION_SHA256:
        errors.append("lineage:v7_v8_source_projection_not_trusted")


def validate_lineage(
    root: Path,
    lineage: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    if lineage.get("schema_version") != "15.0" or lineage.get("artifact_kind") != "legacy_lineage_and_v15_dispositions":
        errors.append("lineage:identity")
    sources = lineage.get("sources", {})
    ledger = sources.get("v9_ledger", {})
    native = sources.get("v7_v8_native", {})
    if ledger.get("sha256") != TRUSTED_V9_LEDGER_SHA256:
        errors.append("lineage:v9_ledger_source_hash")
    ledger_path = root / str(ledger.get("path", ""))
    if not ledger_path.is_file() or sha256_file(ledger_path) != TRUSTED_V9_LEDGER_SHA256:
        errors.append("lineage:v9_ledger_local_identity")
    if ledger.get("entry_count") != 1924 or ledger.get("source_span_count") != 1859 or ledger.get("native_or_registry_count") != 65:
        errors.append("lineage:v9_ledger_counts")
    if native.get("sha256") != TRUSTED_V9_NATIVE_SHA256:
        errors.append("lineage:v7_v8_source_hash")
    native_path = root / str(native.get("path", ""))
    if not native_path.is_file() or sha256_file(native_path) != TRUSTED_V9_NATIVE_SHA256:
        errors.append("lineage:v7_v8_local_identity")
    if native.get("projection_sha256") != TRUSTED_V7_V8_NATIVE_PROJECTION_SHA256 or native.get("entry_count") != 14:
        errors.append("lineage:v7_v8_source_identity")
    spans = flatten_lineage_groups(lineage, errors)
    validate_native_dispositions(root, lineage, by_id, errors)
    summary = lineage.get("summary", {})
    expected_summary = {
        "v1_v6_spans": len(spans),
        "v1_v6_confirmed_in_v9": sum(item.get("v9_review_status") == "confirmed_capability" for item in spans),
        "v1_v6_context_in_v9": sum(item.get("v9_review_status") == "context_only" for item in spans),
        "v7_v8_entries": len(lineage.get("v7_v8_dispositions", [])),
        "v7_v8_disposition_counts": dict(sorted(Counter(item.get("disposition") for item in lineage.get("v7_v8_dispositions", []) if isinstance(item, dict)).items())),
    }
    if summary != expected_summary:
        errors.append("lineage:summary_mismatch")


def compare_with_v9_sources(
    root: Path,
    v9_root: Path,
    baseline: dict[str, Any],
    clause_artifact: dict[str, Any],
    crosswalk: dict[str, Any],
    lineage: dict[str, Any],
    rules: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    errors: list[str],
) -> None:
    registry_path = v9_root / "references/capability-registry.json"
    ledger_path = v9_root / "references/migration/v1-v9-capability-ledger.json"
    native_path = v9_root / "references/migration/native-capabilities.json"
    try:
        verify_trusted_sources(registry_path, ledger_path, native_path)
    except (OSError, ValueError) as exc:
        errors.append(f"source_authentication_failed:{exc}")
        return
    expected_baseline = build_baseline(load_json(registry_path))
    expected_crosswalk = build_crosswalk(expected_baseline, rules, clause_artifact)
    expected_lineage = build_lineage(load_json(ledger_path), load_json(native_path), by_id, root)
    if baseline != expected_baseline:
        errors.append("baseline:differs_from_authenticated_v9_source")
    if crosswalk != expected_crosswalk:
        errors.append("crosswalk:differs_from_authenticated_v9_and_v15_sources")
    if lineage != expected_lineage:
        errors.append("lineage:differs_from_authenticated_v9_source")
    if sha256_file(registry_path) != TRUSTED_V9_REGISTRY_SHA256:
        errors.append("source:v9_registry_changed")
    if sha256_file(ledger_path) != TRUSTED_V9_LEDGER_SHA256:
        errors.append("source:v9_ledger_changed")
    if sha256_file(native_path) != TRUSTED_V9_NATIVE_SHA256:
        errors.append("source:v9_native_changed")


def validate(root: Path, v9_root: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    migration_root = root / "references/migration"
    baseline = load_json(migration_root / "v9-capability-baseline.json")
    clause_artifact = load_json(migration_root / "clause-preservation.json")
    crosswalk = load_json(migration_root / "capability-crosswalk.json")
    lineage = load_json(migration_root / "legacy-coverage.json")
    for name, artifact in (
        ("baseline", baseline), ("clause_preservation", clause_artifact),
        ("crosswalk", crosswalk), ("lineage", lineage),
    ):
        verify_seal(name, artifact, errors)

    rules, by_id = load_rules(root)
    baseline_by_id = validate_baseline(baseline, errors)
    route_ids = validate_current_inventory(root, rules, set(baseline_by_id), errors)
    validate_clause_preservation(root, baseline, clause_artifact, rules, errors)
    validate_crosswalk(
        root, baseline, baseline_by_id, clause_artifact, crosswalk, rules, by_id,
        errors,
    )
    validate_lineage(root, lineage, by_id, errors)
    if v9_root is not None:
        compare_with_v9_sources(
            root, v9_root, baseline, clause_artifact, crosswalk, lineage, rules, by_id, errors,
        )

    capability_rows = crosswalk.get("capabilities", []) if isinstance(crosswalk, dict) else []
    native_rows = lineage.get("v7_v8_dispositions", []) if isinstance(lineage, dict) else []
    blocking = [
        f"{item.get('capability_id')}:{item.get('disposition')}"
        for item in capability_rows if isinstance(item, dict) and item.get("disposition") in BLOCKING_DISPOSITIONS
    ] + [
        f"{item.get('legacy_id')}:{item.get('disposition')}"
        for item in native_rows if isinstance(item, dict) and item.get("disposition") in BLOCKING_DISPOSITIONS
    ]
    if blocking:
        errors.append("release_blocking_dispositions:" + ",".join(sorted(blocking)))
    unwaived_strength = [
        item.get("capability_id") for item in capability_rows
        if isinstance(item, dict)
        and item.get("strength_relation") == "contains_weaker"
        and item.get("strength_waiver_id") is None
    ]

    active_rules = [rule for rule in rules if rule.get("status") == "active"]
    result_rows = [
        {
            "id": "MIG.V15.RULE_INVENTORY",
            "status": "pass" if not any(
                error.startswith("inventory:")
                or re.match(r"^[A-Z][A-Z0-9_.]+:(owner|routes|strength|capability|enforcement|semantic)", error)
                for error in errors
            ) else "fail",
        },
        {
            "id": "MIG.V9.CAPABILITIES",
            "status": "pass" if not any("baseline" in error or "crosswalk" in error or re.match(r"^[A-Z]+-[A-Z0-9-]+:", error) for error in errors) else "fail",
        },
        {
            "id": "MIG.V9.CLAUSE_PRESERVATION",
            "status": "pass" if not any("clause_preservation" in error or "clause_review" in error or "source_clause" in error for error in errors) else "fail",
        },
        {
            "id": "MIG.V1_V6.LINEAGE",
            "status": "pass" if not any("lineage:v1_v6" in error or "lineage:owner" in error or "lineage:duplicate_or_missing_span" in error for error in errors) else "fail",
        },
        {
            "id": "MIG.V7_V8.DISPOSITIONS",
            "status": "pass" if not any("v7_v8" in error or error.startswith(("V7-", "V8-")) for error in errors) else "fail",
        },
        {
            "id": "MIG.TAMPER.SEALS",
            "status": "pass" if not any("tampered" in error or "not_trusted" in error or "differs_from_authenticated" in error for error in errors) else "fail",
        },
    ]
    return {
        "schema_version": "15.0",
        "status": "pass" if not errors else "fail",
        "driver": "migration_fidelity",
        "metrics": {
            "v9_capabilities": len(baseline_by_id),
            "v15_active_atoms": len(active_rules),
            "known_routes": len(route_ids),
            "reviewed_source_clauses": clause_artifact.get("summary", {}).get("source_clauses", 0),
            "reviewed_active_atoms": len(clause_artifact.get("atom_reviews", [])),
            "legacy_entries": lineage.get("summary", {}).get("v1_v6_spans", 0),
            "native_entries": len(native_rows),
            "reverse_atoms": len(crosswalk.get("reverse_atoms", [])),
            "blocking_dispositions": len(blocking),
            "unwaived_strength_regressions": len(unwaived_strength),
            "semantic_atom_bindings": len(crosswalk.get("reverse_atoms", [])),
        },
        "results": result_rows,
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--v9-root", type=Path)
    args = parser.parse_args()
    result = validate(args.root.resolve(), args.v9_root.resolve() if args.v9_root else None)
    json_output(result)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
