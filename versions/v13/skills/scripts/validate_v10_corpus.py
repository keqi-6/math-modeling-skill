#!/usr/bin/env python3
"""Prove that V11 preserves the frozen V10 rule corpus byte for byte."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def skill_root(root: Path) -> Path:
    if (root / "rules").is_dir():
        return root
    if (root / "skills" / "rules").is_dir():
        return root / "skills"
    return root


def rules_dir(root: Path) -> Path:
    return skill_root(root) / "rules"


def roots_overlap(left: Path, right: Path) -> bool:
    left = left.resolve()
    right = right.resolve()
    return left == right or left in right.parents or right in left.parents


def tree_manifest(root: Path, excluded: set[str]) -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded or not path.is_file():
            continue
        if path.is_symlink():
            encoded = os.readlink(path).encode("utf-8")
            digest = sha256_bytes(b"SYMLINK\0" + encoded)
            size = len(encoded)
        else:
            digest = sha256_file(path)
            size = path.stat().st_size
        files.append({"path": relative, "sha256": digest, "size": size})
    return {
        "sha256": sha256_bytes(canonical_bytes(files)),
        "file_count": len(files),
        "files": files,
    }


def validate_frozen_v10(candidate_root: Path, v10_root: Path) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    seal_path = candidate_root / "references/v10-lineage-seal.json"
    if not seal_path.is_file():
        return {}, ["v10_lineage_seal_missing"]
    try:
        seal = read_json(seal_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {}, [f"v10_lineage_seal_unreadable:{type(exc).__name__}:{exc}"]
    if seal.get("schema_version") != "11.0" or seal.get("artifact_kind") != "official_frozen_v10_lineage_seal":
        errors.append("v10_lineage_seal_identity_invalid")

    manifest_path = v10_root / str(seal.get("frozen_manifest_path", ""))
    state_path = v10_root / str(seal.get("release_state_path", ""))
    if not manifest_path.is_file():
        errors.append("v10_frozen_manifest_missing")
        return seal, errors
    if sha256_file(manifest_path) != seal.get("frozen_manifest_file_sha256"):
        errors.append("v10_frozen_manifest_file_hash_mismatch")
    if not state_path.is_file():
        errors.append("v10_release_state_missing")
    elif sha256_file(state_path) != seal.get("release_state_file_sha256"):
        errors.append("v10_release_state_file_hash_mismatch")

    try:
        manifest = read_json(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        errors.append(f"v10_frozen_manifest_unreadable:{type(exc).__name__}:{exc}")
        return seal, errors
    claimed_self_hash = manifest.get("manifest_sha256")
    self_payload = dict(manifest)
    self_payload.pop("manifest_sha256", None)
    calculated_self_hash = sha256_bytes(canonical_bytes(self_payload))
    if claimed_self_hash != calculated_self_hash:
        errors.append("v10_frozen_manifest_self_hash_mismatch")
    if claimed_self_hash != seal.get("frozen_manifest_self_sha256"):
        errors.append("v10_frozen_manifest_not_official_identity")
    if (
        manifest.get("schema_version") != "10.0"
        or manifest.get("release_id") != seal.get("release_id")
        or manifest.get("status") != seal.get("release_status")
    ):
        errors.append("v10_frozen_manifest_release_identity_mismatch")
    exclusions = set(manifest.get("manifest_policy", {}).get("excluded_paths", []))
    if exclusions != {str(seal.get("frozen_manifest_path"))}:
        errors.append("v10_frozen_manifest_exclusions_mismatch")
    actual_tree = tree_manifest(v10_root, exclusions)
    if manifest.get("release_tree") != actual_tree:
        errors.append("v10_frozen_release_tree_mismatch")
    if (
        actual_tree.get("sha256") != seal.get("release_tree_sha256")
        or actual_tree.get("file_count") != seal.get("release_tree_file_count")
    ):
        errors.append("v10_frozen_release_tree_not_official_identity")

    if state_path.is_file():
        try:
            state = read_json(state_path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"v10_release_state_unreadable:{type(exc).__name__}:{exc}")
        else:
            if (
                state.get("schema_version") != "10.0"
                or state.get("release_id") != seal.get("release_id")
                or state.get("status") != "stable"
                or state.get("manifest") != seal.get("frozen_manifest_path")
            ):
                errors.append("v10_release_state_identity_mismatch")
    return seal, errors


def inventory(directory: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    errors: list[str] = []
    entries: dict[str, dict[str, Any]] = {}
    if not directory.is_dir():
        return entries, [f"rules_directory_missing:{directory}"]
    for path in sorted(directory.iterdir(), key=lambda item: item.name):
        if not path.is_file() or path.suffix != ".json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}:unreadable:{type(exc).__name__}:{exc}")
            continue
        rules = payload.get("rules") if isinstance(payload, dict) else None
        if not isinstance(rules, list):
            errors.append(f"{path.name}:rules_not_array")
            active = None
            identifiers: list[str] = []
        else:
            active = sum(
                isinstance(rule, dict) and rule.get("status") == "active"
                for rule in rules
            )
            identifiers = sorted(
                str(rule.get("id"))
                for rule in rules
                if isinstance(rule, dict) and isinstance(rule.get("id"), str)
            )
        entries[path.name] = {
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "active_rules": active,
            "rule_ids": identifiers,
        }
    if not entries:
        errors.append("no_rule_bundles")
    return entries, errors


def validate(root: Path, v10_root: Path) -> dict[str, Any]:
    candidate_root = skill_root(root.resolve())
    baseline_root = skill_root(v10_root.resolve())
    errors: list[str] = []
    if roots_overlap(candidate_root, baseline_root):
        errors.append("candidate_v10_roots_overlap")
    seal, identity_errors = validate_frozen_v10(candidate_root, baseline_root)
    errors.extend(identity_errors)
    current, current_errors = inventory(rules_dir(candidate_root))
    errors.extend(current_errors)
    baseline, baseline_errors = inventory(rules_dir(baseline_root))
    errors.extend(f"v10:{item}" for item in baseline_errors)

    current_names = set(current)
    baseline_names = set(baseline)
    for name in sorted(baseline_names - current_names):
        errors.append(f"missing_rule_bundle:{name}")
    for name in sorted(current_names - baseline_names):
        errors.append(f"unexpected_rule_bundle:{name}")
    changed: list[str] = []
    for name in sorted(current_names & baseline_names):
        if current[name]["sha256"] != baseline[name]["sha256"]:
            changed.append(name)
            errors.append(f"rule_bundle_not_byte_identical:{name}")

    current_ids = [identifier for item in current.values() for identifier in item["rule_ids"]]
    baseline_ids = [identifier for item in baseline.values() for identifier in item["rule_ids"]]
    if len(current_ids) != len(set(current_ids)):
        errors.append("candidate_duplicate_rule_ids")
    if len(baseline_ids) != len(set(baseline_ids)):
        errors.append("v10_duplicate_rule_ids")
    if sorted(current_ids) != sorted(baseline_ids):
        errors.append("rule_id_set_changed")

    active_rules = sum(
        int(item["active_rules"] or 0) for item in current.values()
    )
    baseline_active_rules = sum(
        int(item["active_rules"] or 0) for item in baseline.values()
    )
    if active_rules != baseline_active_rules:
        errors.append(
            f"active_rule_count_changed:{active_rules}!={baseline_active_rules}"
        )

    baseline_digest = hashlib.sha256(canonical_bytes(baseline)).hexdigest()
    if baseline_digest != seal.get("rule_inventory_sha256"):
        errors.append("v10_rule_inventory_not_official_identity")
    if len(baseline) != seal.get("rule_file_count"):
        errors.append("v10_rule_file_count_not_official_identity")
    if baseline_active_rules != seal.get("active_rule_count"):
        errors.append("v10_active_rule_count_not_official_identity")
    return {
        "schema_version": "11.0",
        "status": "pass" if not errors else "fail",
        "driver": "v10_corpus",
        "errors": sorted(set(errors)),
        "metrics": {
            "rule_files": len(current),
            "exact_files": len(current_names & baseline_names) - len(changed),
            "active_rules": active_rules,
            "v10_active_rules": baseline_active_rules,
            "v10_inventory_sha256": baseline_digest,
            "v10_manifest_sha256": seal.get("frozen_manifest_self_sha256"),
            "v10_release_tree_sha256": seal.get("release_tree_sha256"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--v10-root", type=Path, required=True)
    args = parser.parse_args()
    report = validate(args.root.resolve(), args.v10_root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
