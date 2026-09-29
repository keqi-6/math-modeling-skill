#!/usr/bin/env python3
"""Compile the V15 migration fidelity layer from frozen, reviewed inputs.

The compiler deliberately keeps three claims separate:

* the 51 reviewed V9 capability contracts are the behavioural baseline;
* the 1,859 V1-V6 spans prove source/hash/owner-family lineage only;
* the 14 V7/V8 native records use an explicit, curated disposition table;
* current atoms are bound by their semantic envelope, owner, strength, and routes.

No eval registry, lexical mapper, keyword mapper, or fallback mapper is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from lib_v10 import SKILL_ROOT, dump_json, load_json, load_rules, sha256_file, sha256_text


TRUSTED_V9_REGISTRY_SHA256 = "71c2d308f9a1cda6c7ac6f1c163967a23256bd52a79792efd8abf14005cacf0b"
TRUSTED_V9_LEDGER_SHA256 = "c44427ba0829e71d37c4f6f6012c35760e70647b0022fee6b239190fab13166e"
TRUSTED_V9_NATIVE_SHA256 = "c160257539667dd727bd19653599de17c9343f7d3d6cd9185ebe6eab17873ce6"
TRUSTED_V9_REGISTRY_PROJECTION_SHA256 = "6d77f0814ada5a910705cf1511180b4992c74f2123a16fd6fa0029d3bdf07fe8"
TRUSTED_V1_V6_LINEAGE_PROJECTION_SHA256 = "0a0ee21611f7c4ad846ba76504277cdba13cd0524013fbf93e538ce23595e45a"
TRUSTED_V7_V8_NATIVE_PROJECTION_SHA256 = "d3f7cefbcc370ebf8212f97b9e20796dd65f6f9bc1c33cd7553e3108dd5a9425"
FINAL_DISPOSITIONS = {
    "preserved_exactly",
    "split_into",
    "merged_with",
    "transformed",
    "retired_conflict",
    "retired_project_preference",
    "context_only",
}
BLOCKING_DISPOSITIONS = {"pending", "unreviewed", "gap"}
MIGRATION_RELEASE = "V15.0.0"
# A waiver is intentionally a code-reviewed, release-bound decision rather than
# a flag in generated output. No waiver is approved for this release.
STRENGTH_WAIVERS: dict[str, dict[str, str]] = {}
GENERATED_MIGRATION_ARTIFACTS = {
    "references/migration/v9-capability-baseline.json",
    "references/migration/capability-crosswalk.json",
    "references/migration/clause-preservation.json",
    "references/migration/legacy-coverage.json",
}
V9_CAPABILITY_FIELDS = (
    "id", "domain", "owner", "strength", "trigger", "expected", "forbidden"
)
SPAN_RECORD_FIELDS = (
    "legacy_id", "start_line", "end_line", "text_sha256",
    "v9_review_status_code", "v9_treatment_code", "v9_migration_status_code",
)
SPAN_STATUS_CODEBOOK = {
    "v9_review_status": {"C": "confirmed_capability", "X": "context_only"},
    "v9_treatment": {"P": "preserve", "W": "rewrite"},
    "v9_migration_status": {"N": "normalized", "R": "retained", "S": "superseded"},
}
SPAN_STATUS_ENCODERS = {
    field: {value: code for code, value in values.items()}
    for field, values in SPAN_STATUS_CODEBOOK.items()
}


# These mappings are decisions, not similarity-search output. The V7/V8 source
# facts and their original migration_status are read from V9; this table only
# records where that already-reviewed native capability lives in V15.
NATIVE_V7_V8_DISPOSITIONS: dict[str, dict[str, Any]] = {
    "V7-ARCH-001": {
        "disposition": "transformed",
        "atom_ids": ["GOV.OWNER.UNIQUE", "GOV.ROUTE.RAW_REQUEST"],
        "artifact_refs": ["SKILL.md", "references/rule-atom.schema.json"],
        "rationale": "The single controller remains discoverable while runtime ownership is split into typed atom owners.",
    },
    "V7-ARCH-002": {
        "disposition": "transformed",
        "atom_ids": ["GOV.ROUTE.DECOMPOSE", "GOV.OWNER.UNIQUE"],
        "artifact_refs": ["SKILL.md", "references/route-contract.json", "references/rule-atom.schema.json"],
        "rationale": "Progressive disclosure is represented by a thin controller, route contract, and domain atom bundles.",
    },
    "V7-ROUTE-001": {
        "disposition": "split_into",
        "atom_ids": ["GOV.ROUTE.RAW_REQUEST", "GOV.ROUTE.STATE_BIND", "GOV.ROUTE.UNIQUE_WRITE", "GOV.ROUTE.DECOMPOSE"],
        "artifact_refs": ["references/route-contract.json"],
        "rationale": "The machine-readable registry remains, with routing obligations split into four executable atoms.",
    },
    "V7-CAP-001": {
        "disposition": "transformed",
        "atom_ids": ["MNT.OWNER.CANONICAL", "MNT.EVAL.POSITIVE"],
        "artifact_refs": [
            "references/migration/v9-capability-baseline.json",
            "references/migration/capability-crosswalk.json",
            "references/migration/legacy-coverage.json",
        ],
        "rationale": "The old span ledger is lineage-only; reviewed capabilities now bind directly and bidirectionally to sealed V15 semantic envelopes.",
    },
    "V7-OWN-001": {
        "disposition": "split_into",
        "atom_ids": ["GOV.OWNER.UNIQUE", "MNT.OWNER.CANONICAL", "MNT.IMPACT.CONFLICT_GRAPH"],
        "artifact_refs": ["references/rule-atom.schema.json"],
        "rationale": "Canonical ownership and conflict analysis are separate observable obligations.",
    },
    "V7-STATE-001": {
        "disposition": "split_into",
        "atom_ids": ["STATE.TYPE.MATCH", "STATE.EVIDENCE.TYPED", "STATE.TRANSITION.GATED", "STATE.ROUTE.RECORD"],
        "artifact_refs": ["references/state-machine.json"],
        "rationale": "Component typing, evidence, transition gating, and route recording are independently enforced.",
    },
    "V7-REC-001": {
        "disposition": "split_into",
        "atom_ids": ["REC.R0.CONTINUE", "REC.R1.TRANSITIVE", "REC.R2.FULL"],
        "artifact_refs": ["references/state-machine.json"],
        "rationale": "R0, R1, and R2 remain distinct recovery dispositions.",
    },
    "V7-RECEIPT-001": {
        "disposition": "split_into",
        "atom_ids": ["GOV.RECEIPT.START_MATCH", "GOV.RECEIPT.END_MATCH"],
        "artifact_refs": ["references/receipt.schema.json"],
        "rationale": "Start and end receipt authenticity remain separately checked.",
    },
    "V7-SCAFFOLD-001": {
        "disposition": "split_into",
        "atom_ids": ["PRJ.STRUCTURE.INSPECT", "PRJ.STRUCTURE.LAZY", "ART.ADMIT.CONSUMER", "ART.ADMIT.MINIMAL"],
        "artifact_refs": ["references/artifact-contract.json"],
        "rationale": "Scaffold control is preserved as inspection, lazy structure, consumer admission, and minimal creation.",
    },
    "V8-S6-001": {
        "disposition": "preserved_exactly",
        "atom_ids": ["VER.S6.DUAL_AXIS"],
        "artifact_refs": ["references/state-machine.json"],
        "rationale": "The dual-axis S6 requirement has one direct V10 owner.",
    },
    "V8-S6-002": {
        "disposition": "split_into",
        "atom_ids": [
            "VER.E1.INTERFACE", "VER.E1.UNITS", "VER.E1.BOUNDARY", "VER.E1.REPRODUCE",
            "VER.E2.RECOMPUTE", "VER.E2.TOLERANCE", "VER.E2.STABILITY",
        ],
        "artifact_refs": ["references/state-machine.json"],
        "rationale": "Implementation and numerical verification are decomposed into E1 and E2 atoms.",
    },
    "V8-S6-003": {
        "disposition": "split_into",
        "atom_ids": [
            "VER.E3.CONSTRAINT", "VER.E3.INVARIANT", "VER.E3.LIMIT", "VER.E3.COUNTEREXAMPLE",
            "VER.E4.ASSUMPTIONS", "VER.E4.SCALE", "VER.E4.PARAMETERS",
        ],
        "artifact_refs": ["references/state-machine.json"],
        "rationale": "Structural and reality examination are decomposed into E3 and E4 atoms.",
    },
    "V8-S6-004": {
        "disposition": "transformed",
        "atom_ids": ["VER.S6.DUAL_AXIS", "STATE.TRANSITION.GATED"],
        "artifact_refs": ["references/route-contract.json", "references/state-machine.json"],
        "rationale": "Dual-axis evidence is now bound at both route selection and typed state-transition gates.",
    },
    "V8-S6-005": {
        "disposition": "transformed",
        "atom_ids": ["VER.S6.DUAL_AXIS"],
        "artifact_refs": [
            "references/state-machine.json",
            "references/preservation/audit-v11-v14.md",
        ],
        "rationale": "The former dedicated regression guard is retained as a reviewed S6 semantic envelope and typed state gate, not as a legacy eval dependency.",
    },
}


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def seal(payload: dict[str, Any]) -> dict[str, Any]:
    sealed = dict(payload)
    sealed["payload_sha256"] = canonical_sha256(payload)
    return sealed


def verify_trusted_sources(registry_path: Path, ledger_path: Path, native_path: Path) -> None:
    actual = {
        "registry": sha256_file(registry_path),
        "ledger": sha256_file(ledger_path),
        "native": sha256_file(native_path),
    }
    expected = {
        "registry": TRUSTED_V9_REGISTRY_SHA256,
        "ledger": TRUSTED_V9_LEDGER_SHA256,
        "native": TRUSTED_V9_NATIVE_SHA256,
    }
    mismatches = [f"{name}:{actual[name]}!={digest}" for name, digest in expected.items() if actual[name] != digest]
    if mismatches:
        raise ValueError("untrusted V9 migration source: " + ";".join(mismatches))


def capability_contract(capability: dict[str, Any]) -> dict[str, Any]:
    return {field: capability[field] for field in V9_CAPABILITY_FIELDS}


def rule_gloss(rule: dict[str, Any]) -> str:
    return str(rule.get("instruction_gloss", rule.get("instruction", "")))


def rule_failure(rule: dict[str, Any]) -> str:
    return str(rule.get("failure_example", rule.get("forbidden", "")))


def atom_contract(rule: dict[str, Any]) -> dict[str, Any]:
    """Return the current rule inventory projection used for tamper checks.

    Eval back-references are deliberately excluded.  Migration fidelity is
    sealed against the rule's current identity and semantic contract, not the
    lifecycle or naming of a particular test harness.
    """
    return {
        "id": rule["id"],
        "revision": rule["revision"],
        "status": rule["status"],
        "capability": rule["capability"],
        "domain": rule["domain"],
        "owner": rule["owner"],
        "strength": rule["strength"],
        "semantic_key": rule["semantic_key"],
        "scope": rule["scope"],
        "trigger": rule["trigger"],
        "effect": rule["effect"],
        "instruction_gloss": rule_gloss(rule),
        "failure_example": rule_failure(rule),
        "evidence": rule["evidence"],
        "outcomes": rule["outcomes"],
        "exceptions": rule.get("exceptions", []),
        "conflicts_with": rule.get("conflicts_with", []),
        "refines": rule.get("refines", []),
        "depends_on": rule.get("depends_on", []),
        "supersedes": rule.get("supersedes", []),
        "legacy_refs": rule.get("legacy_refs", []),
        "routes": rule.get("routes", []),
        "enforcement": rule.get("enforcement"),
    }


def origin_assignment_projection(
    rules: list[dict[str, Any]], baseline_ids: set[str]
) -> list[dict[str, Any]]:
    projection = []
    for rule in sorted(rules, key=lambda item: item["id"]):
        capability_id = rule["capability"]
        if capability_id in baseline_ids:
            origin = "legacy_family"
        elif str(capability_id).startswith("V10-"):
            origin = "native_v10"
        else:
            origin = "gap"
        projection.append({
            "atom_id": rule["id"],
            "atom_status": rule["status"],
            "origin": origin,
            "capability_id": capability_id,
            "legacy_refs": rule.get("legacy_refs", []),
        })
    return projection


def semantic_atom_contract(rule: dict[str, Any], origin: str) -> dict[str, Any]:
    """Project only fields whose change can alter normative runtime behaviour.

    Revision counters, eval back-references, explanatory glosses, failure
    examples, and outcome prose do not masquerade as V1-V14 semantic loss.
    Evidence requirements, owner, routes, and enforcement are included because
    changing any of them can change whether or how an obligation is accepted.
    """
    return {
        "atom_id": rule["id"],
        "atom_status": rule["status"],
        "origin": origin,
        "capability_id": rule["capability"],
        "domain": rule["domain"],
        "owner": rule["owner"],
        "legacy_refs": rule.get("legacy_refs", []),
        "semantic_key": rule["semantic_key"],
        "strength": rule["strength"],
        "scope": rule["scope"],
        "trigger": rule["trigger"],
        "effect": rule["effect"],
        "evidence": rule["evidence"],
        "exceptions": rule.get("exceptions", []),
        "conflicts_with": rule.get("conflicts_with", []),
        "refines": rule.get("refines", []),
        "depends_on": rule.get("depends_on", []),
        "supersedes": rule.get("supersedes", []),
        "routes": rule.get("routes", []),
        "enforcement": rule.get("enforcement"),
    }


def semantic_binding_projection(
    rules: list[dict[str, Any]], baseline_ids: set[str]
) -> list[dict[str, Any]]:
    assignments = {
        item["atom_id"]: item for item in origin_assignment_projection(rules, baseline_ids)
    }
    return [
        semantic_atom_contract(rule, assignments[rule["id"]]["origin"])
        for rule in sorted(rules, key=lambda item: item["id"])
    ]


def build_baseline(registry: dict[str, Any]) -> dict[str, Any]:
    capabilities = []
    for source in registry["capabilities"]:
        contract = capability_contract(source)
        capabilities.append({**contract, "contract_sha256": canonical_sha256(contract)})
    projection = [capability_contract(item) for item in capabilities]
    return seal({
        "schema_version": "10.1",
        "artifact_kind": "v9_reviewed_capability_baseline",
        "source_release": "V9.0.0",
        "source_file": "references/capability-registry.json",
        "source_file_sha256": TRUSTED_V9_REGISTRY_SHA256,
        "source_projection_sha256": canonical_sha256(projection),
        "review_basis": "inherited_v9_capability_registry",
        "capabilities": capabilities,
    })


def validate_sealed_baseline(baseline: dict[str, Any]) -> None:
    stored = baseline.get("payload_sha256")
    payload = {key: value for key, value in baseline.items() if key != "payload_sha256"}
    if stored != canonical_sha256(payload):
        raise ValueError("sealed V9 capability baseline was modified")
    capabilities = baseline.get("capabilities", [])
    projection = [capability_contract(item) for item in capabilities]
    if (
        baseline.get("source_file_sha256") != TRUSTED_V9_REGISTRY_SHA256
        or baseline.get("source_projection_sha256") != TRUSTED_V9_REGISTRY_PROJECTION_SHA256
        or canonical_sha256(projection) != TRUSTED_V9_REGISTRY_PROJECTION_SHA256
    ):
        raise ValueError("sealed V9 capability baseline is not the trusted reviewed projection")


def strength_relation(source_strength: str, atom_strengths: list[str]) -> str:
    rank = {"MAY": 0, "SHOULD": 1, "MUST": 2}
    values = {rank[item] for item in atom_strengths}
    source = rank[source_strength]
    if values == {source}:
        return "same"
    if min(values) >= source:
        return "contains_stronger"
    return "contains_weaker"


def capability_disposition(atom_count: int, relation: str) -> str:
    if atom_count == 0:
        return "gap"
    if relation != "same":
        return "transformed"
    if atom_count == 1:
        return "preserved_exactly"
    return "split_into"


def strength_waiver(capability_id: str, relation: str) -> dict[str, str] | None:
    waiver = STRENGTH_WAIVERS.get(capability_id)
    if waiver is None:
        return None
    required = {"waiver_id", "capability_id", "release", "relation", "rationale", "decision_ref"}
    if set(waiver) != required:
        raise ValueError(f"{capability_id}: malformed strength waiver")
    if waiver["capability_id"] != capability_id or waiver["release"] != MIGRATION_RELEASE or waiver["relation"] != relation:
        raise ValueError(f"{capability_id}: strength waiver is not bound to this release and relation")
    if relation != "contains_weaker" or len(waiver["rationale"]) < 20 or not waiver["decision_ref"]:
        raise ValueError(f"{capability_id}: strength waiver lacks a reviewable decision")
    return waiver


def build_crosswalk(
    baseline: dict[str, Any], rules: list[dict[str, Any]], clause_artifact: dict[str, Any],
) -> dict[str, Any]:
    active_rules = [rule for rule in rules if rule.get("status") == "active"]
    by_capability: dict[str, list[dict[str, Any]]] = defaultdict(list)
    baseline_ids = {item["id"] for item in baseline["capabilities"]}
    for rule in active_rules:
        by_capability[rule["capability"]].append(rule)

    capability_rows = []
    for source in baseline["capabilities"]:
        atoms = sorted(by_capability.get(source["id"], []), key=lambda item: item["id"])
        relation = strength_relation(source["strength"], [item["strength"] for item in atoms]) if atoms else "unbound"
        disposition = capability_disposition(len(atoms), relation)
        waiver = strength_waiver(source["id"], relation)
        bindings = []
        for atom in atoms:
            origin = "legacy_family" if atom["capability"] in baseline_ids else "native_v10"
            bindings.append({
                "atom_id": atom["id"],
                "revision": atom["revision"],
                "strength": atom["strength"],
                "owner": atom["owner"],
                "routes": sorted(set(atom.get("routes", []))),
                "effect_sha256": canonical_sha256(atom["effect"]),
                "semantic_sha256": canonical_sha256(semantic_atom_contract(atom, origin)),
                "atom_contract_sha256": canonical_sha256(atom_contract(atom)),
            })
        capability_rows.append({
            "capability_id": source["id"],
            "disposition": disposition,
            "mapping_basis": "explicit_rule_capability_field",
            "source_contract_sha256": source["contract_sha256"],
            "expected_sha256": sha256_text(source["expected"]),
            "forbidden_sha256": sha256_text(source["forbidden"]),
            "strength_relation": relation,
            "disposition_basis": (
                "explicit_one_to_one_binding" if disposition == "preserved_exactly"
                else "explicit_atom_split" if disposition == "split_into"
                else "normative_strength_changed" if disposition == "transformed"
                else "no_active_atom"
            ),
            "semantic_equivalence_claimed": False,
            "semantic_preservation_basis": "reviewed_clause_preservation_artifact",
            "strength_waiver_id": waiver["waiver_id"] if waiver else None,
            "atom_ids": [item["id"] for item in atoms],
            "atom_bindings": bindings,
        })

    assignment_projection = origin_assignment_projection(rules, baseline_ids)
    semantic_projection = semantic_binding_projection(rules, baseline_ids)
    assignment_by_id = {item["atom_id"]: item for item in assignment_projection}
    reverse_atoms = []
    for rule in sorted(rules, key=lambda item: item["id"]):
        assignment = assignment_by_id[rule["id"]]
        reverse_atoms.append({
            "atom_id": rule["id"],
            "atom_status": rule["status"],
            "origin": assignment["origin"],
            "capability_id": assignment["capability_id"],
            "owner": rule["owner"],
            "routes": sorted(set(rule.get("routes", []))),
            "semantic_sha256": canonical_sha256(semantic_atom_contract(rule, assignment["origin"])),
            "atom_contract_sha256": canonical_sha256(atom_contract(rule)),
        })

    inventory = [atom_contract(item) for item in sorted(rules, key=lambda item: item["id"])]
    disposition_counts = Counter(item["disposition"] for item in capability_rows)
    origin_counts = Counter(item["origin"] for item in reverse_atoms)
    capability_binding_sha256 = canonical_sha256(capability_rows)
    return seal({
        "schema_version": "15.0",
        "artifact_kind": "v9_to_v15_capability_crosswalk",
        "claim_boundary": (
            "This crosswalk asserts structural assignment, strength, owner, route, and current "
            "semantic-envelope binding. It has no dependency on an eval registry. "
            "It does not itself claim semantic equivalence; the reviewed clause-preservation "
            "artifact is the sole V9-to-V15 semantic-preservation authority."
        ),
        "source_baseline_projection_sha256": baseline["source_projection_sha256"],
        "clause_preservation_ref": {
            "path": "references/migration/clause-preservation.json",
            "payload_sha256": clause_artifact["payload_sha256"],
            "review_projection_sha256": clause_artifact["review_projection_sha256"],
            "review_source_inventory_sha256": clause_artifact["review_source_inventory_sha256"],
            "review_decision_id": clause_artifact["review"]["decision_id"],
        },
        "origin_assignment_sha256": canonical_sha256(assignment_projection),
        "capability_binding_sha256": capability_binding_sha256,
        "semantic_binding_sha256": canonical_sha256(semantic_projection),
        "rule_inventory_sha256": canonical_sha256(inventory),
        "allowed_dispositions": sorted(FINAL_DISPOSITIONS),
        "blocking_dispositions": sorted(BLOCKING_DISPOSITIONS),
        "strength_waivers": [STRENGTH_WAIVERS[key] for key in sorted(STRENGTH_WAIVERS)],
        "capabilities": capability_rows,
        "reverse_atoms": reverse_atoms,
        "summary": {
            "v9_capability_count": len(capability_rows),
            "target_atom_count": len(rules),
            "target_active_atom_count": len(active_rules),
            "disposition_counts": dict(sorted(disposition_counts.items())),
            "reverse_origin_counts": dict(sorted(origin_counts.items())),
        },
    })


def compact_span_groups(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for entry in entries:
        grouped[str(entry["v9_owner"])][str(entry["source_file"])].append(entry)
    owners = []
    for owner in sorted(grouped):
        files = []
        owner_entries: list[dict[str, Any]] = []
        for source_file in sorted(grouped[owner]):
            source_entries = sorted(
                grouped[owner][source_file],
                key=lambda item: (item["source_lines"], item["capability_id"]),
            )
            hashes = {entry["source_sha256"] for entry in source_entries}
            if len(hashes) != 1:
                raise ValueError(f"inconsistent source hash for {source_file}")
            owner_entries.extend(source_entries)
            files.append({
                "source_file": source_file,
                "source_sha256": next(iter(hashes)),
                "span_count": len(source_entries),
                "spans": [
                    [
                        entry["capability_id"],
                        entry["source_lines"][0],
                        entry["source_lines"][1],
                        sha256_text(str(entry.get("source_text", ""))),
                        SPAN_STATUS_ENCODERS["v9_review_status"][entry.get("review_status")],
                        SPAN_STATUS_ENCODERS["v9_treatment"][entry.get("treatment")],
                        SPAN_STATUS_ENCODERS["v9_migration_status"][entry.get("migration_status")],
                    ]
                    for entry in source_entries
                ],
            })
        owners.append({
            "v9_owner_family": owner,
            "disposition": "context_only",
            "semantic_equivalence_claimed": False,
            "span_count": len(owner_entries),
            "v9_review_counts": dict(sorted(Counter(item.get("review_status") for item in owner_entries).items())),
            "source_files": files,
        })
    return owners


def build_native_dispositions(
    native_entries: list[dict[str, Any]], by_id: dict[str, dict[str, Any]], output_root: Path
) -> list[dict[str, Any]]:
    source_ids = {item["capability_id"] for item in native_entries}
    decision_ids = set(NATIVE_V7_V8_DISPOSITIONS)
    if source_ids != decision_ids:
        missing = sorted(source_ids - decision_ids)
        extra = sorted(decision_ids - source_ids)
        raise ValueError(f"V7/V8 disposition table mismatch: missing={missing};extra={extra}")
    rows = []
    for source in sorted(native_entries, key=lambda item: item["capability_id"]):
        decision = NATIVE_V7_V8_DISPOSITIONS[source["capability_id"]]
        for atom_id in decision["atom_ids"]:
            if atom_id not in by_id:
                raise ValueError(f"{source['capability_id']}: unknown current atom {atom_id}")
        for artifact in decision["artifact_refs"]:
            if not (output_root / artifact).exists() and artifact not in GENERATED_MIGRATION_ARTIFACTS:
                raise ValueError(f"{source['capability_id']}: missing current artifact {artifact}")
        atom_bindings = []
        for atom_id in decision["atom_ids"]:
            atom = by_id[atom_id]
            origin = "legacy_family"
            atom_bindings.append({
                "atom_id": atom_id,
                "owner": atom["owner"],
                "strength": atom["strength"],
                "routes": sorted(set(atom.get("routes", []))),
                "semantic_sha256": canonical_sha256(semantic_atom_contract(atom, origin)),
            })
        rows.append({
            "legacy_id": source["capability_id"],
            "introduced_in": source["introduced_in"],
            "source_capability": source["capability"],
            "source": source["source"],
            "v9_owner": source["v9_owner"],
            "v9_migration_status": source["migration_status"],
            "disposition": decision["disposition"],
            "review_basis": "inherited_v9_native_registry",
            "mapping_basis": "explicit_v15_semantic_binding",
            "atom_ids": decision["atom_ids"],
            "atom_bindings": atom_bindings,
            "artifact_refs": decision["artifact_refs"],
            "rationale": decision["rationale"],
        })
    return rows


def build_lineage(
    ledger: dict[str, Any], native: dict[str, Any], by_id: dict[str, dict[str, Any]], output_root: Path
) -> dict[str, Any]:
    spans = [entry for entry in ledger["entries"] if "source_file" in entry]
    ledger_native = [entry for entry in ledger["entries"] if "source_file" not in entry]
    owner_groups = compact_span_groups(spans)
    native_rows = build_native_dispositions(native["entries"], by_id, output_root)
    span_projection_sha256 = canonical_sha256(owner_groups)
    native_projection_sha256 = canonical_sha256(sorted(native["entries"], key=lambda item: item["capability_id"]))
    disposition_counts = Counter(item["disposition"] for item in native_rows)
    return seal({
        "schema_version": "15.0",
        "artifact_kind": "legacy_lineage_and_v15_dispositions",
        "source_release": "V1-V9",
        "claim_boundary": (
            "V1-V6 spans establish hash integrity and V9 owner-family lineage only. "
            "They are not claimed as line-by-line V15 semantic equivalents. V7/V8 "
            "dispositions bind directly to the current atom semantic envelopes."
        ),
        "sources": {
            "v9_ledger": {
                "path": "references/migration/v1-v9-capability-ledger.json",
                "sha256": TRUSTED_V9_LEDGER_SHA256,
                "entry_count": len(ledger["entries"]),
                "source_span_count": len(spans),
                "native_or_registry_count": len(ledger_native),
            },
            "v7_v8_native": {
                "path": "references/migration/native-capabilities.json",
                "sha256": TRUSTED_V9_NATIVE_SHA256,
                "projection_sha256": native_projection_sha256,
                "entry_count": len(native["entries"]),
            },
        },
        "v1_v6_lineage": {
            "disposition": "context_only",
            "semantic_equivalence_claimed": False,
            "span_record_fields": list(SPAN_RECORD_FIELDS),
            "status_codebook": SPAN_STATUS_CODEBOOK,
            "span_count": len(spans),
            "owner_family_count": len(owner_groups),
            "projection_sha256": span_projection_sha256,
            "owner_families": owner_groups,
        },
        "v7_v8_dispositions": native_rows,
        "summary": {
            "v1_v6_spans": len(spans),
            "v1_v6_confirmed_in_v9": sum(item.get("review_status") == "confirmed_capability" for item in spans),
            "v1_v6_context_in_v9": sum(item.get("review_status") == "context_only" for item in spans),
            "v7_v8_entries": len(native_rows),
            "v7_v8_disposition_counts": dict(sorted(disposition_counts.items())),
        },
    })


def build(v9_root: Path | None, output_root: Path) -> dict[str, Any]:
    migration_root = output_root / "references/migration"
    if v9_root is not None:
        registry_path = v9_root / "references/capability-registry.json"
        ledger_path = v9_root / "references/migration/v1-v9-capability-ledger.json"
        native_path = v9_root / "references/migration/native-capabilities.json"
        verify_trusted_sources(registry_path, ledger_path, native_path)
        baseline = build_baseline(load_json(registry_path))
    else:
        ledger_path = migration_root / "v1-v9-capability-ledger.json"
        native_path = migration_root / "native-capabilities.json"
        if sha256_file(ledger_path) != TRUSTED_V9_LEDGER_SHA256:
            raise ValueError("local V1-V9 ledger is not the trusted source")
        if sha256_file(native_path) != TRUSTED_V9_NATIVE_SHA256:
            raise ValueError("local V7/V8 native archive is not the trusted source")
        baseline = load_json(migration_root / "v9-capability-baseline.json")
        validate_sealed_baseline(baseline)
    ledger = load_json(ledger_path)
    native = load_json(native_path)
    rules, by_id = load_rules(output_root)
    from build_clause_preservation import (
        EXPECTED_REVIEW_PROJECTION_SHA256,
        build_artifact as build_clause_artifact,
    )

    clause_artifact, clause_review_hash = build_clause_artifact(output_root, baseline)
    if clause_review_hash != EXPECTED_REVIEW_PROJECTION_SHA256:
        raise ValueError(
            "normative V9-to-V15 semantics changed without a versioned migration re-seal: "
            f"clause_review:{clause_review_hash}!={EXPECTED_REVIEW_PROJECTION_SHA256}"
        )
    crosswalk = build_crosswalk(baseline, rules, clause_artifact)
    lineage = build_lineage(ledger, native, by_id, output_root)
    projection_checks = {
        "registry": (baseline["source_projection_sha256"], TRUSTED_V9_REGISTRY_PROJECTION_SHA256),
        "v1_v6_lineage": (
            lineage["v1_v6_lineage"]["projection_sha256"],
            TRUSTED_V1_V6_LINEAGE_PROJECTION_SHA256,
        ),
        "v7_v8_native": (
            lineage["sources"]["v7_v8_native"]["projection_sha256"],
            TRUSTED_V7_V8_NATIVE_PROJECTION_SHA256,
        ),
    }
    projection_mismatches = [
        f"{name}:{actual}!={expected}"
        for name, (actual, expected) in projection_checks.items()
        if actual != expected
    ]
    if projection_mismatches:
        raise ValueError("trusted migration projection changed: " + ";".join(projection_mismatches))
    if any(item["origin"] == "gap" for item in crosswalk["reverse_atoms"]):
        raise ValueError("current atom-origin assignment contains a release-blocking gap")
    dump_json(migration_root / "v9-capability-baseline.json", baseline)
    dump_json(migration_root / "clause-preservation.json", clause_artifact)
    dump_json(migration_root / "capability-crosswalk.json", crosswalk)
    dump_json(migration_root / "legacy-coverage.json", lineage)
    unwaived_strength_regressions = [
        item["capability_id"]
        for item in crosswalk["capabilities"]
        if item["strength_relation"] == "contains_weaker" and item["strength_waiver_id"] is None
    ]
    return {
        "v9_capabilities": len(baseline["capabilities"]),
        "v15_atoms": len(rules),
        "reviewed_source_clauses": clause_artifact["summary"]["source_clauses"],
        "v1_v6_spans": lineage["summary"]["v1_v6_spans"],
        "v7_v8_entries": lineage["summary"]["v7_v8_entries"],
        "blocking_capability_dispositions": sum(
            item["disposition"] in BLOCKING_DISPOSITIONS for item in crosswalk["capabilities"]
        ),
        "unwaived_strength_regressions": len(unwaived_strength_regressions),
        "unwaived_strength_regression_ids": unwaived_strength_regressions,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--v9-root", type=Path,
        help="optional authenticated V9 tree; otherwise use the sealed local baseline and archives",
    )
    parser.add_argument("--output-root", type=Path, default=SKILL_ROOT)
    args = parser.parse_args()
    metrics = build(args.v9_root.resolve() if args.v9_root else None, args.output_root.resolve())
    from lib_v10 import json_output
    failed = bool(metrics["blocking_capability_dispositions"] or metrics["unwaived_strength_regressions"])
    json_output({
        "schema_version": "15.0", "status": "fail" if failed else "pass",
        "metrics": metrics,
        "errors": [
            "unwaived_strength_regressions:" + ",".join(metrics["unwaived_strength_regression_ids"])
        ] if metrics["unwaived_strength_regressions"] else [],
    })
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
