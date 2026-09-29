#!/usr/bin/env python3
"""Run the release-policy drivers in fresh subprocesses without mutating the candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


POLICY = Path("references/release-policy.json")
PLAN = Path("evals/release/release-plan.json")
STATE = Path("evals/release/release-state.json")
MANIFEST = Path("evals/release/frozen-manifest.json")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def tree_identity(root: Path) -> str:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(root).as_posix()
        files.append([relative, sha256(path.read_bytes()), path.stat().st_size])
    return sha256(canonical(files))


def load_object(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"{label}_unreadable:{exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label}_not_object")
        return {}
    return value


def release_id_for(schema_version: Any, declared_release_id: Any) -> str | None:
    schema_match = re.fullmatch(r"([1-9][0-9]*)\.(0|[1-9][0-9]*)", str(schema_version))
    release_match = re.fullmatch(
        r"V([1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",
        str(declared_release_id),
    )
    if schema_match is None or release_match is None:
        return None
    if tuple(map(int, schema_match.groups())) != tuple(map(int, release_match.groups()[:2])):
        return None
    return str(declared_release_id)


def policy_contract(
    root: Path, policy: dict[str, Any], errors: list[str]
) -> tuple[str | None, str | None, list[dict[str, Any]], list[str]]:
    schema_version = policy.get("schema_version")
    declared_release_id = policy.get("release_id")
    release_id = release_id_for(schema_version, declared_release_id)
    if re.fullmatch(r"([1-9][0-9]*)\.(0|[1-9][0-9]*)", str(schema_version)) is None:
        errors.append("release_policy_schema_version_invalid")
    elif release_id is None:
        errors.append("release_policy_identity_invalid")

    raw_drivers = policy.get("active_drivers")
    if not isinstance(raw_drivers, list) or not raw_drivers:
        errors.append("release_policy_active_drivers_invalid")
        raw_drivers = []
    drivers: list[dict[str, Any]] = []
    seen_driver_ids: set[str] = set()
    for index, item in enumerate(raw_drivers):
        if not isinstance(item, dict):
            errors.append(f"release_policy_driver_not_object:{index}")
            continue
        driver_id = item.get("id")
        script = item.get("script")
        if not isinstance(driver_id, str) or not driver_id:
            errors.append(f"release_policy_driver_id_invalid:{index}")
            continue
        if driver_id in seen_driver_ids:
            errors.append(f"release_policy_driver_id_duplicate:{driver_id}")
            continue
        seen_driver_ids.add(driver_id)
        if not isinstance(script, str) or not script:
            errors.append(f"release_policy_driver_script_invalid:{driver_id}")
            continue
        relative = Path(script)
        candidate = (root / relative).resolve()
        scripts_root = (root / "scripts").resolve()
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or scripts_root not in candidate.parents
            or not candidate.is_file()
            or candidate.is_symlink()
        ):
            errors.append(f"release_policy_driver_script_invalid:{driver_id}:{script}")
            continue
        drivers.append({"id": driver_id, "script": relative.as_posix(), "path": candidate, "policy": item})

    required_case_ids = policy.get("required_case_ids")
    if not isinstance(required_case_ids, list) or not required_case_ids:
        errors.append("release_policy_required_case_ids_invalid")
        required_case_ids = []
    elif any(not isinstance(item, str) or not item for item in required_case_ids):
        errors.append("release_policy_required_case_id_invalid")
        required_case_ids = [item for item in required_case_ids if isinstance(item, str) and item]
    if len(required_case_ids) != len(set(required_case_ids)):
        errors.append("release_policy_required_case_ids_duplicate")

    budget = policy.get("budget", {})
    if not isinstance(budget, dict):
        errors.append("release_policy_budget_invalid")
        budget = {}
    declared_count = budget.get("active_driver_count")
    if declared_count is not None and declared_count != len(raw_drivers):
        errors.append("release_policy_driver_budget_drift")
    return str(schema_version) if schema_version is not None else None, release_id, drivers, required_case_ids


def result_cases(payload: dict[str, Any]) -> list[dict[str, Any]]:
    cases = payload.get("cases")
    if isinstance(cases, list):
        return [item for item in cases if isinstance(item, dict)]
    results = payload.get("results")
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict)]
    return []


def string_list(value: Any, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{label}:must_be_nonempty_string_array")
        return []
    if not value:
        errors.append(f"{label}:must_not_be_empty")
    if len(value) != len(set(value)):
        errors.append(f"{label}:duplicates")
    return value


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
        value: Any = json.loads(candidate.read_text(encoding="utf-8"))
    except Exception:
        return None
    for token in fragment.strip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if not isinstance(value, dict) or token not in value:
            return None
        value = value[token]
    return value


def validate_change_review(
    root: Path, plan: dict[str, Any], required_case_ids: list[str], errors: list[str]
) -> list[str]:
    review = plan.get("change_review")
    if not isinstance(review, dict):
        errors.append("change_review_missing")
        return []
    required_fields = {
        "review_kind", "review_status", "risk", "old_behavior", "new_observable_effects",
        "preserved", "retired_or_merged", "unverified", "impact_surfaces",
        "rollback_identity", "authorization", "evidence",
    }
    if set(review) != required_fields:
        errors.append("change_review_field_set_invalid")
    if review.get("review_kind") != "human_reviewed_release_change":
        errors.append("change_review_kind_invalid")
    if review.get("review_status") != "reviewed":
        errors.append("change_review_not_reviewed")
    for field in (
        "risk", "old_behavior", "new_observable_effects", "preserved",
        "retired_or_merged", "unverified",
    ):
        string_list(review.get(field), f"change_review:{field}", errors)

    evidence = review.get("evidence")
    if not isinstance(evidence, dict) or set(evidence) != {"case_ids", "check_ids"}:
        errors.append("change_review_evidence_shape_invalid")
        evidence = {}
    case_ids = string_list(evidence.get("case_ids"), "change_review:case_ids", errors)
    check_ids = string_list(evidence.get("check_ids"), "change_review:check_ids", errors)
    if case_ids != required_case_ids:
        errors.append("change_review_case_binding_drift")
    declared_evidence_ids = set(case_ids) | set(check_ids)

    surfaces = review.get("impact_surfaces")
    if not isinstance(surfaces, list) or not surfaces:
        errors.append("change_review_impact_surfaces_invalid")
        surfaces = []
    surface_names: list[str] = []
    for item in surfaces:
        if not isinstance(item, dict) or set(item) != {"surface", "effect", "evidence_ids"}:
            errors.append("change_review_impact_surface_shape_invalid")
            continue
        surface, effect = item.get("surface"), item.get("effect")
        if not isinstance(surface, str) or not surface or not isinstance(effect, str) or not effect:
            errors.append("change_review_impact_surface_value_invalid")
            continue
        surface_names.append(surface)
        ids = string_list(item.get("evidence_ids"), f"change_review:surface:{surface}", errors)
        if set(ids) - declared_evidence_ids:
            errors.append(f"change_review_impact_evidence_unknown:{surface}")
    if len(surface_names) != len(set(surface_names)):
        errors.append("change_review_impact_surface_duplicate")

    authorization = review.get("authorization")
    if not isinstance(authorization, dict) or set(authorization) != {"quote", "quote_sha256"}:
        errors.append("change_review_authorization_shape_invalid")
    else:
        quote, claimed = authorization.get("quote"), authorization.get("quote_sha256")
        if not isinstance(quote, str) or len(quote.strip()) < 2:
            errors.append("change_review_authorization_quote_invalid")
        elif claimed != sha256(quote.encode("utf-8")):
            errors.append("change_review_authorization_hash_mismatch")

    rollback = review.get("rollback_identity")
    rollback_fields = {"kind", "tree_sha256", "binding_ref", "strategy"}
    if not isinstance(rollback, dict) or set(rollback) != rollback_fields:
        errors.append("change_review_rollback_shape_invalid")
    else:
        for field in ("kind", "binding_ref", "strategy"):
            if not isinstance(rollback.get(field), str) or not rollback[field].strip():
                errors.append(f"change_review_rollback_{field}_invalid")
        tree_hash = rollback.get("tree_sha256")
        if not isinstance(tree_hash, str) or re.fullmatch(r"[0-9a-f]{64}", tree_hash) is None:
            errors.append("change_review_rollback_hash_invalid")
        bound = referenced_json_value(root, rollback.get("binding_ref"))
        if not isinstance(bound, dict):
            errors.append("change_review_rollback_binding_invalid")
        elif bound.get("tree_sha256") != tree_hash:
            errors.append("change_review_rollback_binding_mismatch")
    return check_ids


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--timeout", type=int, default=None,
        help="optional per-driver timeout override; otherwise use release-policy budget",
    )
    args = parser.parse_args()
    root = skill_root(args.root)
    errors: list[str] = []
    before = tree_identity(root)

    policy = load_object(root / POLICY, "release_policy", errors)
    plan = load_object(root / PLAN, "release_plan", errors)
    release_state = load_object(root / STATE, "release_state", errors)
    schema_version, release_id, drivers, required_case_ids = policy_contract(root, policy, errors)

    policy_driver_projection = [
        {"id": item["id"], "script": item["script"]} for item in drivers
    ]
    policy_driver_ids = [item["id"] for item in drivers]
    plan_driver_projection = [
        {"id": item.get("id"), "script": item.get("script")}
        for item in plan.get("drivers", []) if isinstance(item, dict)
    ]
    if plan.get("policy") != POLICY.as_posix():
        errors.append("release_plan_policy_invalid")
    if plan.get("schema_version") != schema_version or plan.get("release_id") != release_id:
        errors.append("release_plan_identity_invalid")
    if plan.get("required_drivers") != policy_driver_ids or plan_driver_projection != policy_driver_projection:
        errors.append("release_plan_driver_contract_drift")
    if plan.get("required_case_ids") != required_case_ids:
        errors.append("release_plan_required_case_contract_drift")
    if plan.get("legacy_diagnostic_suites_are_active_drivers") is not False:
        errors.append("release_plan_legacy_chain_not_retired")
    review_check_ids = validate_change_review(root, plan, required_case_ids, errors)

    if (
        release_state.get("schema_version") != schema_version
        or release_state.get("release_id") != release_id
    ):
        errors.append("release_state_identity_invalid")
    if release_state.get("status") != "candidate" or release_state.get("frozen_at") is not None:
        errors.append("validation_requires_unfrozen_candidate")
    if release_state.get("gate_report_sha256") is not None:
        errors.append("candidate_gate_report_must_be_unsealed")
    if release_state.get("manifest") != MANIFEST.as_posix():
        errors.append("release_state_manifest_path_invalid")
    if (root / MANIFEST).exists():
        errors.append("candidate_contains_frozen_manifest")

    budget = policy.get("budget", {}) if isinstance(policy.get("budget"), dict) else {}
    policy_timeout = budget.get("default_timeout_seconds_per_driver", 30)
    if not isinstance(policy_timeout, int) or isinstance(policy_timeout, bool) or policy_timeout <= 0:
        errors.append("release_policy_default_timeout_invalid")
        policy_timeout = 30
    if args.timeout is not None and args.timeout <= 0:
        errors.append("timeout_override_invalid")

    results: list[dict[str, Any]] = []
    observations: dict[str, list[tuple[str, str]]] = {}
    observed_checks: set[str] = set()
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"

    if not errors:
        for declaration in drivers:
            driver_id = declaration["id"]
            configured_timeout = declaration["policy"].get("timeout_seconds", policy_timeout)
            timeout = args.timeout if args.timeout is not None else configured_timeout
            if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
                results.append({
                    "id": driver_id, "status": "fail", "fresh_subprocess": True,
                    "errors": ["driver_timeout_contract_invalid"],
                })
                errors.append(f"driver_timeout_contract_invalid:{driver_id}")
                continue
            command = [sys.executable, "-B", str(declaration["path"]), "--root", str(root)]
            try:
                process = subprocess.run(
                    command,
                    cwd=root,
                    env=environment,
                    text=True,
                    capture_output=True,
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                results.append({
                    "id": driver_id, "status": "fail", "fresh_subprocess": True,
                    "timeout_seconds": timeout, "errors": ["timeout"],
                })
                errors.append(f"driver_timeout:{driver_id}")
                continue
            except OSError as exc:
                results.append({
                    "id": driver_id, "status": "fail", "fresh_subprocess": True,
                    "timeout_seconds": timeout, "errors": [f"process_error:{exc}"],
                })
                errors.append(f"driver_process_error:{driver_id}")
                continue

            try:
                decoded = json.loads(process.stdout)
                payload = decoded if isinstance(decoded, dict) else {}
            except json.JSONDecodeError:
                payload = {}
            cases = result_cases(payload)
            for case in cases:
                case_id, case_status = case.get("id"), case.get("status")
                if isinstance(case_id, str) and isinstance(case_status, str):
                    observations.setdefault(case_id, []).append((driver_id, case_status))

            stable_ids = payload.get("checks")
            has_checks = (
                isinstance(stable_ids, list)
                and bool(stable_ids)
                and all(isinstance(item, str) and item for item in stable_ids)
            )
            output_contract_valid = has_checks or bool(cases)
            if has_checks:
                observed_checks.update(stable_ids)
            passed = (
                process.returncode == 0
                and payload.get("status") == "pass"
                and payload.get("driver") == driver_id
                and payload.get("schema_version") == schema_version
                and output_contract_valid
            )
            driver_errors = payload.get("errors", [])
            if not isinstance(driver_errors, list):
                driver_errors = ["driver_errors_not_array"]
                passed = False
            results.append({
                "id": driver_id,
                "script": declaration["script"],
                "status": "pass" if passed else "fail",
                "fresh_subprocess": True,
                "timeout_seconds": timeout,
                "exit_code": process.returncode,
                "checks": payload.get("checks", []),
                "cases": cases,
                "evidence": payload.get("evidence", {}),
                "errors": driver_errors,
                "stderr": process.stderr[-500:],
                "stdout_tail": "" if payload else process.stdout[-500:],
            })
            if not passed:
                errors.append(f"driver_failed:{driver_id}")

        for case_id, seen in sorted(observations.items()):
            if len(seen) > 1:
                errors.append(f"case_id_reported_multiple_times:{case_id}")
        for case_id in required_case_ids:
            seen = observations.get(case_id, [])
            if not seen:
                errors.append(f"required_case_missing:{case_id}")
            elif len(seen) != 1 or seen[0][1] != "pass":
                errors.append(f"required_case_not_pass:{case_id}")
        for check_id in review_check_ids:
            if check_id not in observed_checks:
                errors.append(f"change_review_check_not_observed:{check_id}")

    after = tree_identity(root)
    if after != before:
        errors.append("release_gate_mutated_candidate")
    report = {
        "schema_version": schema_version,
        "release_id": release_id,
        "status": "pass" if not errors else "fail",
        "policy": POLICY.as_posix(),
        "policy_sha256": sha256(canonical(policy)) if policy else None,
        "tree_sha256": before,
        "active_driver_ids": policy_driver_ids,
        "required_case_ids": required_case_ids,
        "drivers": results,
        "errors": errors,
    }
    report["report_sha256"] = sha256(canonical(report))
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
