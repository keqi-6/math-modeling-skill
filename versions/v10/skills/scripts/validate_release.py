#!/usr/bin/env python3
"""Run the complete V10 release gate in fresh, side-effect-free subprocesses."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    Draft202012Validator = None  # type: ignore[assignment]
    FormatChecker = None  # type: ignore[assignment]


REQUIRED_DRIVERS = (
    "quick_package", "contracts", "behavior", "atomic",
    "scenario", "maintenance", "change", "transaction", "migration",
)
QUICK_CHECK_IDS = (
    "PKG.REQUIRED", "PKG.CLEAN_TREE", "PKG.NO_SYMLINKS", "PKG.JSON_PARSE",
    "PKG.JSON_SCHEMA_META", "PKG.SCHEMA_INSTANCES", "PKG.PYTHON_COMPILE",
    "PKG.REFERENCES", "PKG.EVAL_REGISTRY", "PKG.RELEASE_METADATA",
)
EXPECTED_DRIVER_DECLARATIONS: dict[str, dict[str, Any]] = {
    "quick_package": {
        "id": "quick_package", "script": "scripts/quick_validate.py",
        "registry": {"kind": "declared_ids", "ids": list(QUICK_CHECK_IDS)},
    },
    "contracts": {
        "id": "contracts", "script": "scripts/validate_contracts.py",
        "registry": {"kind": "metrics", "paths": [
            "metrics.active_rules", "metrics.capabilities", "metrics.routes", "metrics.test_ids",
        ]},
    },
    "behavior": {
        "id": "behavior", "script": "scripts/run_behavior_evals.py",
        "registry": {"kind": "cases", "files": ["evals/behavior-cases.json"], "filters": {"kind": "route"}},
    },
    "atomic": {
        "id": "atomic", "script": "scripts/run_atomic_rule_evals.py",
        "args": ["--mutation-check"],
        "registry": {"kind": "cases", "files": ["evals/atomic-rule-cases.json"], "filters": {}},
    },
    "scenario": {
        "id": "scenario", "script": "scripts/run_scenario_tests.py",
        "registry": {"kind": "cases_recursive", "glob": "evals/**/*.json", "filters": {"kind": "scenario", "driver": "scenario_tests"}},
    },
    "maintenance": {
        "id": "maintenance", "script": "scripts/run_maintenance_tests.py",
        "registry": {"kind": "cases_recursive", "glob": "evals/**/*.json", "filters": {"kind": "scenario", "driver": "maintenance_tests"}},
    },
    "change": {
        "id": "change", "script": "scripts/run_change_evals.py",
        "registry": {"kind": "cases", "files": ["evals/change-cases.json"], "filters": {}},
    },
    "transaction": {
        "id": "transaction", "script": "scripts/run_transaction_tests.py", "requires_v9_root": True,
        "registry": {"kind": "metrics", "paths": [
            "metrics.successful_transactions", "metrics.production_gates_executed",
        ]},
    },
    "migration": {
        "id": "migration", "script": "scripts/validate_migration.py", "requires_v9_root": True,
        "registry": {"kind": "metrics", "paths": [
            "metrics.v9_capabilities", "metrics.v10_active_rules", "metrics.reviewed_source_clauses",
            "metrics.reviewed_active_atoms", "metrics.legacy_entries", "metrics.native_entries",
        ]},
    },
}
REQUIRED_UNVERIFIED_BOUNDARIES = (
    "No external signing key or third-party transparency log is available; the frozen manifest is tamper-evident and independently re-gated, not identity-signed.",
    "External services, future dependency versions, and operating systems other than the release host are outside this local gate.",
    "Migration lineage proves registered dispositions and hashes; semantic preservation is bounded by the versioned clause-review seal and executable local gates.",
    "JSON Schema and compilation establish structure and syntax, not arbitrary domain truth beyond the executed scenarios.",
)
PLAN_PATH = Path("evals/release/release-plan.json")
STATE_PATH = Path("evals/release/release-state.json")
MANIFEST_PATH = Path("evals/release/frozen-manifest.json")
MANIFEST_SCHEMA_PATH = Path("references/release-manifest.schema.json")
RELEASE_TREE_EXCLUSIONS = {MANIFEST_PATH.as_posix()}
ISOLATED_LAUNCHER = (
    "import runpy,sys;"
    "sys.path.insert(0,sys.argv[1]);"
    "target=sys.argv[2];"
    "sys.argv=[target,*sys.argv[3:]];"
    "runpy.run_path(target,run_name='__main__')"
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def tree_manifest(root: Path, excluded: set[str] | None = None) -> dict[str, Any]:
    excluded = excluded or set()
    files: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if relative in excluded or not path.is_file():
            continue
        if path.is_symlink():
            encoded = os.readlink(path).encode("utf-8")
            files.append({"path": relative, "sha256": sha256_bytes(b"SYMLINK\0" + encoded), "size": len(encoded)})
        else:
            files.append({"path": relative, "sha256": sha256_file(path), "size": path.stat().st_size})
    return {
        "sha256": sha256_bytes(canonical_bytes(files)),
        "file_count": len(files),
        "files": files,
    }


def validator_hashes(root: Path) -> dict[str, str]:
    paths: set[Path] = set((root / "scripts").glob("*.py"))
    # JSON references are machine contracts, registries, schemas, or frozen
    # migration inputs consumed by the validators; hash all of them instead of
    # maintaining a brittle hand-written subset.
    paths.update((root / "references").rglob("*.json"))
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in sorted(paths, key=lambda item: item.relative_to(root).as_posix())
        if path.is_file() and not path.is_symlink()
    }


def load_plan(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    try:
        plan = read_json(root / PLAN_PATH)
    except Exception as exc:
        return None, [f"release_plan_unreadable:{type(exc).__name__}:{exc}"]
    if not isinstance(plan, dict):
        return None, ["release_plan_not_object"]
    allowed = {"schema_version", "release_id", "required_drivers", "drivers", "unverified_boundaries"}
    if set(plan) != allowed:
        errors.append("release_plan_shape")
    if plan.get("schema_version") != "10.0" or plan.get("release_id") != "V10.0.0":
        errors.append("release_plan_identity")
    declared_required = plan.get("required_drivers")
    if not isinstance(declared_required, list) or tuple(declared_required) != REQUIRED_DRIVERS:
        errors.append("required_driver_order_or_set_mismatch")
    drivers = plan.get("drivers")
    if not isinstance(drivers, list):
        errors.append("driver_declarations_not_array")
    else:
        ids = [item.get("id") for item in drivers if isinstance(item, dict)]
        if tuple(ids) != REQUIRED_DRIVERS:
            errors.append("driver_declaration_order_or_set_mismatch")
        if len(ids) != len(set(ids)):
            errors.append("duplicate_driver_declaration")
        for item in drivers:
            if not isinstance(item, dict):
                errors.append("driver_declaration_not_object")
                continue
            if set(item) - {"id", "script", "args", "registry", "requires_v9_root"}:
                errors.append(f"{item.get('id')}:driver_declaration_extra_fields")
            if not isinstance(item.get("registry"), dict):
                errors.append(f"{item.get('id')}:registry_missing")
            script = item.get("script")
            if not isinstance(script, str) or not script.startswith("scripts/") or ".." in Path(script).parts:
                errors.append(f"{item.get('id')}:script_invalid")
            driver_id = item.get("id")
            if driver_id in EXPECTED_DRIVER_DECLARATIONS and item != EXPECTED_DRIVER_DECLARATIONS[driver_id]:
                errors.append(f"{driver_id}:driver_contract_drift")
    boundaries = plan.get("unverified_boundaries")
    if not isinstance(boundaries, list) or not boundaries or not all(isinstance(item, str) and len(item) >= 8 for item in boundaries):
        errors.append("unverified_boundaries_invalid")
    elif tuple(boundaries) != REQUIRED_UNVERIFIED_BOUNDARIES:
        errors.append("unverified_boundaries_drift")
    return plan, errors


def case_matches(case: dict[str, Any], filters: dict[str, Any]) -> bool:
    return all(case.get(key) == value for key, value in filters.items())


def expected_registry(root: Path, registry: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    kind = registry.get("kind")
    if kind == "declared_ids":
        ids = registry.get("ids")
        if not isinstance(ids, list) or not all(isinstance(item, str) and item for item in ids):
            return {"kind": kind, "ids": []}, ["declared_ids_invalid"]
        if len(ids) != len(set(ids)):
            errors.append("duplicate_declared_id")
        return {"kind": kind, "ids": ids}, errors
    if kind in {"cases", "cases_recursive"}:
        filters = registry.get("filters", {})
        if not isinstance(filters, dict):
            return {"kind": kind, "ids": []}, ["case_filters_invalid"]
        paths: list[Path] = []
        if kind == "cases":
            files = registry.get("files")
            if not isinstance(files, list) or not files:
                return {"kind": kind, "ids": []}, ["case_files_invalid"]
            for relative in files:
                if not isinstance(relative, str) or ".." in Path(relative).parts:
                    errors.append(f"case_file_invalid:{relative}")
                else:
                    paths.append(root / relative)
        else:
            pattern = registry.get("glob")
            if not isinstance(pattern, str) or not pattern.startswith("evals/") or ".." in Path(pattern).parts:
                return {"kind": kind, "ids": []}, ["case_glob_invalid"]
            paths = sorted(root.glob(pattern))
        ids: list[str] = []
        sources: dict[str, str] = {}
        for path in paths:
            if not path.is_file():
                errors.append(f"case_registry_missing:{path.relative_to(root).as_posix()}")
                continue
            try:
                payload = read_json(path)
            except Exception as exc:
                errors.append(f"case_registry_unreadable:{path.relative_to(root).as_posix()}:{exc}")
                continue
            if kind == "cases_recursive" and isinstance(payload, dict) and "cases" not in payload:
                continue
            cases = payload.get("cases") if isinstance(payload, dict) else None
            if not isinstance(cases, list):
                errors.append(f"case_registry_shape:{path.relative_to(root).as_posix()}")
                continue
            for case in cases:
                if not isinstance(case, dict) or not case_matches(case, filters):
                    continue
                identifier = case.get("id")
                if not isinstance(identifier, str) or not identifier:
                    errors.append(f"case_missing_id:{path.relative_to(root).as_posix()}")
                    continue
                ids.append(identifier)
                sources[identifier] = path.relative_to(root).as_posix()
        duplicates = sorted({identifier for identifier in ids if ids.count(identifier) > 1})
        if duplicates:
            errors.append("duplicate_expected_cases:" + ",".join(duplicates))
        return {"kind": kind, "ids": ids, "sources": sources}, errors
    if kind == "metrics":
        paths = registry.get("paths")
        if not isinstance(paths, list) or not paths or not all(isinstance(item, str) and item for item in paths):
            return {"kind": kind, "paths": []}, ["metric_paths_invalid"]
        if len(paths) != len(set(paths)):
            errors.append("duplicate_metric_path")
        return {"kind": kind, "paths": paths}, errors
    return {"kind": kind}, [f"unknown_registry_kind:{kind}"]


def nested_value(value: Any, dotted: str) -> Any:
    current = value
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def reconcile_result(expected: dict[str, Any], observed: Any) -> tuple[int, list[str], list[str], list[str]]:
    errors: list[str] = []
    executed_ids: list[str] = []
    missing: list[str] = []
    unexpected: list[str] = []
    if not isinstance(observed, dict):
        return 0, ["driver_output_not_object"], missing, unexpected
    if observed.get("status") != "pass":
        errors.append(f"driver_reported_status:{observed.get('status')}")
    kind = expected.get("kind")
    if kind == "metrics":
        paths = expected.get("paths", [])
        for path in paths:
            value = nested_value(observed, path)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                errors.append(f"metric_not_positive:{path}:{value!r}")
        executed_count = len(paths)
        if executed_count == 0:
            errors.append("zero_metric_assertions")
        return executed_count, errors, missing, unexpected
    expected_ids = list(expected.get("ids", []))
    results = observed.get("results")
    if not isinstance(results, list):
        return 0, errors + ["driver_results_not_array"], expected_ids, unexpected
    for index, item in enumerate(results):
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            errors.append(f"executed_result_missing_id:{index}")
            continue
        executed_ids.append(item["id"])
        if item.get("status") != "pass":
            errors.append(f"case_failed:{item['id']}")
    duplicate_executions = sorted({identifier for identifier in executed_ids if executed_ids.count(identifier) > 1})
    if duplicate_executions:
        errors.append("duplicate_executed_case:" + ",".join(duplicate_executions))
    missing = sorted(set(expected_ids) - set(executed_ids))
    unexpected = sorted(set(executed_ids) - set(expected_ids))
    if missing:
        errors.append("unexecuted_cases:" + ",".join(missing))
    if unexpected:
        errors.append("undeclared_executions:" + ",".join(unexpected))
    if len(executed_ids) == 0 or len(expected_ids) == 0:
        errors.append("zero_case_false_pass_rejected")
    reported_total = observed.get("total", observed.get("executed"))
    reported_passed = observed.get("passed")
    reported_failed = observed.get("failed")
    if reported_failed is None and isinstance(reported_passed, int):
        reported_failed = len(executed_ids) - reported_passed
    if reported_total != len(executed_ids):
        errors.append(f"reported_total_mismatch:{reported_total}!={len(executed_ids)}")
    if reported_passed != len(executed_ids) or reported_failed != 0:
        errors.append("reported_pass_fail_counts_mismatch")
    if "mutation_executed" in observed:
        if observed.get("mutation_executed") != len(expected_ids):
            errors.append("mutation_execution_count_mismatch")
        if observed.get("mutation_passed") != len(expected_ids):
            errors.append("mutation_pass_count_mismatch")
    return len(executed_ids), errors, missing, unexpected


def safe_script(root: Path, relative: str) -> Path | None:
    path = root / relative
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() and not path.is_symlink() else None


def run_driver(
    root: Path,
    declaration: dict[str, Any],
    v9_root: Path | None,
    timeout: int,
) -> dict[str, Any]:
    driver_id = str(declaration.get("id"))
    registry, registry_errors = expected_registry(root, declaration.get("registry", {}))
    errors = list(registry_errors)
    relative_script = str(declaration.get("script", ""))
    script = safe_script(root, relative_script)
    target_script = script or (root / relative_script)
    command = [
        sys.executable, "-I", "-B", "-c", ISOLATED_LAUNCHER,
        str(root / "scripts"), str(target_script), "--root", str(root),
    ]
    declared_args = declaration.get("args", [])
    if isinstance(declared_args, list) and all(isinstance(item, str) for item in declared_args):
        command.extend(declared_args)
    elif declared_args:
        errors.append("driver_args_invalid")
    if declaration.get("requires_v9_root"):
        if v9_root is None:
            errors.append("v9_root_required")
        else:
            command.extend(["--v9-root", str(v9_root)])
    before = tree_manifest(root)
    started_at = utc_now()
    start = time.monotonic()
    returncode: int | None = None
    stdout = ""
    stderr = ""
    observed: Any = None
    if script is None:
        errors.append(f"driver_waiting_for_script:{relative_script}")
    elif declaration.get("requires_v9_root") and v9_root is None:
        errors.append("driver_not_executed_without_v9_root")
    else:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["V10_RELEASE_GATE_FRESH_PROCESS"] = driver_id
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
            returncode = process.returncode
            stdout = process.stdout
            stderr = process.stderr
            if returncode != 0:
                errors.append(f"nonzero_exit:{returncode}")
            try:
                observed = json.loads(stdout)
            except json.JSONDecodeError as exc:
                errors.append(f"stdout_not_single_json_document:{exc}")
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            errors.append(f"driver_timeout:{timeout}s")
        except OSError as exc:
            errors.append(f"driver_launch_failed:{type(exc).__name__}:{exc}")
    after = tree_manifest(root)
    if before != after:
        errors.append("candidate_mutated_during_driver")
    executed_count = 0
    missing: list[str] = []
    unexpected: list[str] = []
    if observed is not None:
        executed_count, reconciliation, missing, unexpected = reconcile_result(registry, observed)
        errors.extend(reconciliation)
    elif registry.get("kind") != "metrics" and not registry.get("ids"):
        errors.append("zero_declared_cases")
    elapsed_ms = int((time.monotonic() - start) * 1000)
    auxiliary_executed_count = (
        observed.get("mutation_executed", 0) if isinstance(observed, dict) else 0
    )
    expected_auxiliary_count = (
        len(registry.get("ids", [])) if "--mutation-check" in command else 0
    )
    if auxiliary_executed_count != expected_auxiliary_count:
        errors.append(
            f"auxiliary_execution_count_mismatch:{auxiliary_executed_count}!={expected_auxiliary_count}"
        )
    return {
        "id": driver_id,
        "status": "pass" if not errors else "fail",
        "fresh_subprocess": returncode is not None,
        "command": command,
        "command_sha256": sha256_bytes(canonical_bytes(command)),
        "started_at": started_at,
        "finished_at": utc_now(),
        "duration_ms": elapsed_ms,
        "exit_code": returncode,
        "expected_count": len(registry.get("ids", registry.get("paths", []))),
        "executed_count": executed_count,
        "expected_auxiliary_count": expected_auxiliary_count,
        "auxiliary_executed_count": auxiliary_executed_count,
        "missing_case_ids": missing,
        "unexpected_case_ids": unexpected,
        "stdout_sha256": sha256_bytes(stdout.encode("utf-8")),
        "stdout_bytes": len(stdout.encode("utf-8")),
        "stderr_tail": stderr[-4000:],
        "tree_before_sha256": before["sha256"],
        "tree_after_sha256": after["sha256"],
        "errors": sorted(set(errors)),
    }


def manifest_digest(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("manifest_sha256", None)
    return sha256_bytes(canonical_bytes(payload))


def verify_release_state(root: Path, current_validators: dict[str, str], plan: dict[str, Any] | None) -> list[str]:
    errors: list[str] = []
    try:
        state = read_json(root / STATE_PATH)
    except Exception as exc:
        return [f"release_state_unreadable:{type(exc).__name__}:{exc}"]
    if not isinstance(state, dict):
        return ["release_state_not_object"]
    status = state.get("status")
    manifest_path = root / MANIFEST_PATH
    if status == "candidate":
        if manifest_path.exists():
            errors.append("candidate_has_frozen_manifest")
        return errors
    if status != "stable":
        return [f"release_state_invalid_status:{status}"]
    if not manifest_path.is_file():
        return ["stable_release_manifest_missing"]
    try:
        manifest = read_json(manifest_path)
        schema = read_json(root / MANIFEST_SCHEMA_PATH)
    except Exception as exc:
        return [f"frozen_manifest_unreadable:{type(exc).__name__}:{exc}"]
    if not isinstance(manifest, dict):
        return ["frozen_manifest_not_object"]
    if Draft202012Validator is None:
        errors.append("jsonschema_dependency_missing")
    else:
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for issue in validator.iter_errors(manifest):
            location = "/".join(str(part) for part in issue.absolute_path) or "$"
            errors.append(f"frozen_manifest_schema:{location}:{issue.message}")
    if manifest.get("manifest_sha256") != manifest_digest(manifest):
        errors.append("frozen_manifest_self_digest_mismatch")
    release_tree = tree_manifest(root, RELEASE_TREE_EXCLUSIONS)
    if manifest.get("release_tree") != release_tree:
        errors.append("frozen_release_tree_mismatch")
    if manifest.get("validator_hashes") != current_validators:
        errors.append("frozen_validator_hashes_mismatch")
    validators_digest = sha256_bytes(canonical_bytes(current_validators))
    if nested_value(manifest, "pre_freeze_gate.validator_hashes_sha256") != validators_digest:
        errors.append("frozen_pre_gate_validator_digest_mismatch")
    if state.get("frozen_at") != manifest.get("generated_at"):
        errors.append("frozen_timestamp_binding_mismatch")
    if state.get("pre_freeze_gate_report_sha256") != nested_value(manifest, "pre_freeze_gate.report_sha256"):
        errors.append("frozen_gate_report_binding_mismatch")
    if plan is not None and manifest.get("unverified_boundaries") != plan.get("unverified_boundaries"):
        errors.append("frozen_boundaries_mismatch")
    declared = [item.get("id") for item in manifest.get("pre_freeze_gate", {}).get("drivers", []) if isinstance(item, dict)]
    if tuple(declared) != REQUIRED_DRIVERS:
        errors.append("frozen_driver_attestations_incomplete")
    return errors


def write_external_report(path: Path, root: Path, report: dict[str, Any]) -> None:
    target = path.resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise ValueError("release report path must be outside the candidate root")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate(root: Path, v9_root: Path | None, timeout: int) -> dict[str, Any]:
    generated_at = utc_now()
    initial_tree = tree_manifest(root)
    validators = validator_hashes(root)
    plan, errors = load_plan(root)
    errors.extend(verify_release_state(root, validators, plan))
    if v9_root is None:
        errors.append("v9_root_not_supplied")
    else:
        required_v9 = [
            v9_root / "references/capability-registry.json",
            v9_root / "references/migration/v1-v9-capability-ledger.json",
            v9_root / "references/migration/native-capabilities.json",
        ]
        for path in required_v9:
            if not path.is_file():
                errors.append(f"v9_source_missing:{path}")
    drivers: list[dict[str, Any]] = []
    if plan is not None and isinstance(plan.get("drivers"), list):
        for declaration in plan["drivers"]:
            if isinstance(declaration, dict):
                drivers.append(run_driver(root, declaration, v9_root, timeout))
    else:
        errors.append("no_driver_plan_executed")
    observed_ids = tuple(item["id"] for item in drivers)
    if observed_ids != REQUIRED_DRIVERS:
        errors.append("not_all_required_drivers_executed")
    for item in drivers:
        if item["status"] != "pass":
            errors.append(f"driver_failed:{item['id']}")
        if not item["fresh_subprocess"]:
            errors.append(f"driver_not_fresh_subprocess:{item['id']}")
        if item["executed_count"] <= 0:
            errors.append(f"driver_zero_executions:{item['id']}")
    final_tree = tree_manifest(root)
    if final_tree != initial_tree:
        errors.append("candidate_tree_changed_during_release_gate")
    report: dict[str, Any] = {
        "schema_version": "10.0",
        "release_id": plan.get("release_id") if plan else None,
        "status": "pass" if not errors else "fail",
        "generated_at": generated_at,
        "fresh_process_policy": "one isolated python interpreter per declared driver",
        "plan_sha256": sha256_file(root / PLAN_PATH) if (root / PLAN_PATH).is_file() else None,
        "tree": initial_tree,
        "tree_unchanged": final_tree == initial_tree,
        "validator_hashes": validators,
        "validator_hashes_sha256": sha256_bytes(canonical_bytes(validators)),
        "drivers": drivers,
        "test_totals": {
            "declared_drivers": len(REQUIRED_DRIVERS),
            "executed_drivers": len(drivers),
            "declared_assertions": sum(item["expected_count"] + item["expected_auxiliary_count"] for item in drivers),
            "executed_assertions": sum(item["executed_count"] + item["auxiliary_executed_count"] for item in drivers),
        },
        "unverified_boundaries": plan.get("unverified_boundaries", []) if plan else [],
        "environment": {
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
        },
        "errors": sorted(set(errors)),
    }
    report["report_sha256"] = sha256_bytes(canonical_bytes(report))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--v9-root", type=Path)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--report", type=Path, help="Optional report path outside the candidate tree")
    args = parser.parse_args()
    root = args.root.resolve()
    v9_root = args.v9_root.resolve() if args.v9_root else None
    report = validate(root, v9_root, args.timeout)
    if args.report is not None:
        try:
            write_external_report(args.report, root, report)
        except (OSError, ValueError) as exc:
            report["status"] = "fail"
            report["errors"] = sorted(set(report["errors"] + [f"external_report_write_failed:{exc}"]))
            report.pop("report_sha256", None)
            report["report_sha256"] = sha256_bytes(canonical_bytes(report))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
