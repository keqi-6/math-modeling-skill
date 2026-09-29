#!/usr/bin/env python3
"""Perform fast, side-effect-free structural validation of a V11 skill package."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # reported as a failed check instead of silently skipping schemas
    Draft202012Validator = None  # type: ignore[assignment]
    FormatChecker = None  # type: ignore[assignment]


REQUIRED_FILES = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/artifact-contract.json",
    "references/change-envelope.schema.json",
    "references/migration/clause-preservation.json",
    "references/manuscript-change-closure.json",
    "references/receipt.schema.json",
    "references/release-manifest.schema.json",
    "references/route-contract.json",
    "references/runtime-policy.json",
    "references/rule-atom.schema.json",
    "references/semantic-plan.schema.json",
    "references/state-machine.json",
    "references/state.schema.json",
    "references/v10-lineage-seal.json",
    "evals/behavior-cases.json",
    "evals/manuscript-behavior-cases.json",
    "evals/v10-behavior-oracles.json",
    "evals/v10-contract-oracles.json",
    "evals/runtime-policy-cases.json",
    "evals/forward-acceptance-cases.json",
    "evals/change-cases.json",
    "evals/contract-cases.json",
    "evals/release/release-plan.json",
    "evals/release/release-state.json",
    "scripts/quick_validate.py",
    "scripts/run_authorized_action.py",
    "scripts/validate_release.py",
    "scripts/freeze_release.py",
    "scripts/run_forward_acceptance.py",
    "scripts/state_v11.py",
    "scripts/validate_v10_corpus.py",
}
REQUIRED_DRIVERS = {
    "quick_package", "contracts", "v10_corpus", "behavior", "atomic",
    "scenario", "maintenance", "migration", "forward",
}
EXPECTED_DRIVER_SCRIPTS = {
    "quick_package": "scripts/quick_validate.py",
    "contracts": "scripts/validate_contracts.py",
    "v10_corpus": "scripts/validate_v10_corpus.py",
    "behavior": "scripts/run_behavior_evals.py",
    "atomic": "scripts/run_atomic_rule_evals.py",
    "scenario": "scripts/run_scenario_tests.py",
    "maintenance": "scripts/run_maintenance_tests.py",
    "migration": "scripts/validate_migration.py",
    "forward": "scripts/run_forward_acceptance.py",
}
QUICK_RELEASE_ARGS = ["--invocation-context", "skill-release"]
CONTAMINATED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
CONTAMINATED_NAMES = {".DS_Store"}
CONTAMINATED_SUFFIXES = (".pyc", ".pyo", ".tmp", ".temp", ".swp", ".bak", "~")
REFERENCE_PREFIXES = ("scripts/", "references/", "rules/", "evals/", "agents/")
ROOT_REFERENCE_KEYS = {
    "ref", "context_ref", "script", "owner", "owner_pattern", "selection_contract",
    "selection_driver", "shape_owner", "interpreter", "semantic_interpreter",
    "semantic_plan_schema",
}
ROOT_REFERENCE_LIST_KEYS = {"refs", "interpreters", "semantic_interpreters"}


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def result(check_id: str, errors: Iterable[str], metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    unique = sorted(set(str(item) for item in errors))
    item: dict[str, Any] = {
        "id": check_id,
        "status": "pass" if not unique else "fail",
        "errors": unique,
    }
    if metrics is not None:
        item["metrics"] = metrics
    return item


def all_paths(root: Path) -> list[Path]:
    return sorted(root.rglob("*"), key=lambda path: path.relative_to(root).as_posix())


def check_required(root: Path) -> dict[str, Any]:
    missing = [path for path in REQUIRED_FILES if not (root / path).is_file()]
    return result("PKG.REQUIRED", [f"missing:{path}" for path in missing], {"required": len(REQUIRED_FILES)})


def check_clean_tree(root: Path) -> dict[str, Any]:
    contaminated: list[str] = []
    for path in all_paths(root):
        relative = path.relative_to(root).as_posix()
        if any(part in CONTAMINATED_DIRS for part in path.relative_to(root).parts):
            contaminated.append(relative)
        elif path.name in CONTAMINATED_NAMES or path.name.endswith(CONTAMINATED_SUFFIXES):
            contaminated.append(relative)
    allowed_top_level = {"SKILL.md", "agents", "evals", "references", "rules", "scripts"}
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if path.name not in allowed_top_level:
            contaminated.append(f"unknown_top_level:{path.name}")
    for path in all_paths(root):
        if path.is_dir() and not path.is_symlink():
            try:
                next(path.iterdir())
            except StopIteration:
                contaminated.append(f"empty_directory:{path.relative_to(root).as_posix()}")
    return result("PKG.CLEAN_TREE", [f"transient_or_cache:{path}" for path in contaminated], {"contaminated": len(set(contaminated))})


def check_symlinks(root: Path) -> dict[str, Any]:
    links = [path.relative_to(root).as_posix() for path in all_paths(root) if path.is_symlink()]
    return result("PKG.NO_SYMLINKS", [f"symlink:{path}" for path in links], {"symlinks": len(links)})


def load_json_documents(root: Path) -> tuple[dict[Path, Any], list[str]]:
    documents: dict[Path, Any] = {}
    errors: list[str] = []
    for path in sorted(root.rglob("*.json")):
        if path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        try:
            documents[path] = read_json(path)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{relative}:{type(exc).__name__}:{exc}")
    return documents, errors


def check_json_parse(root: Path, documents: dict[Path, Any], errors: list[str]) -> dict[str, Any]:
    expected = sum(1 for path in root.rglob("*.json") if not path.is_symlink())
    if len(documents) != expected and not errors:
        errors = [f"document_count:{len(documents)}!={expected}"]
    return result("PKG.JSON_PARSE", errors, {"documents": len(documents), "expected": expected})


def schema_documents(documents: dict[Path, Any]) -> dict[Path, dict[str, Any]]:
    return {
        path: payload for path, payload in documents.items()
        if isinstance(payload, dict)
        and payload.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        and any(key in payload for key in ("type", "oneOf", "allOf", "anyOf", "$ref"))
    }


def check_schema_meta(root: Path, documents: dict[Path, Any]) -> dict[str, Any]:
    errors: list[str] = []
    schemas = schema_documents(documents)
    if Draft202012Validator is None:
        errors.append("jsonschema_dependency_missing")
    else:
        for path, schema in schemas.items():
            try:
                Draft202012Validator.check_schema(schema)
            except Exception as exc:
                errors.append(f"{path.relative_to(root).as_posix()}:{type(exc).__name__}:{exc}")
    if not schemas:
        errors.append("no_draft_2020_12_schemas")
    return result("PKG.JSON_SCHEMA_META", errors, {"schemas": len(schemas)})


def validation_messages(schema: dict[str, Any], instance: Any) -> list[str]:
    if Draft202012Validator is None:
        return ["jsonschema_dependency_missing"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    messages: list[str] = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.absolute_path)):
        location = "/".join(str(part) for part in error.absolute_path) or "$"
        messages.append(f"{location}:{error.message}")
    return messages


def check_schema_instances(root: Path, documents: dict[Path, Any]) -> dict[str, Any]:
    errors: list[str] = []
    validated = 0
    rule_schema = documents.get(root / "references/rule-atom.schema.json")
    if not isinstance(rule_schema, dict):
        errors.append("rule_atom_schema_unavailable")
    else:
        for path in sorted((root / "rules").glob("*.json")):
            payload = documents.get(path)
            if payload is None:
                continue
            validated += 1
            errors.extend(
                f"{path.relative_to(root).as_posix()}:{message}"
                for message in validation_messages(rule_schema, payload)
            )
    plan_schema = documents.get(root / "references/semantic-plan.schema.json")
    if isinstance(plan_schema, dict):
        for relative in (
            "evals/behavior-cases.json",
            "evals/manuscript-behavior-cases.json",
            "evals/forward-acceptance-cases.json",
        ):
            payload = documents.get(root / relative)
            if not isinstance(payload, dict):
                continue
            for case in payload.get("cases", []):
                if not isinstance(case, dict) or not isinstance(case.get("plan"), dict):
                    continue
                validated += 1
                errors.extend(
                    f"{relative}:{case.get('id', '<missing>')}:{message}"
                    for message in validation_messages(plan_schema, case["plan"])
                )
    else:
        errors.append("semantic_plan_schema_unavailable")
    manifest_path = root / "evals/release/frozen-manifest.json"
    if manifest_path.exists() and manifest_path in documents:
        manifest_schema = documents.get(root / "references/release-manifest.schema.json")
        if isinstance(manifest_schema, dict):
            validated += 1
            errors.extend(
                f"evals/release/frozen-manifest.json:{message}"
                for message in validation_messages(manifest_schema, documents[manifest_path])
            )
        else:
            errors.append("release_manifest_schema_unavailable")
    if validated == 0:
        errors.append("no_schema_instances_validated")
    return result("PKG.SCHEMA_INSTANCES", errors, {"instances": validated})


def check_python_compile(root: Path) -> dict[str, Any]:
    errors: list[str] = []
    count = 0
    for path in sorted((root / "scripts").rglob("*.py")):
        count += 1
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, path.relative_to(root).as_posix(), "exec", dont_inherit=True)
        except (OSError, UnicodeError, SyntaxError) as exc:
            errors.append(f"{path.relative_to(root).as_posix()}:{type(exc).__name__}:{exc}")
    if count == 0:
        errors.append("no_python_scripts")
    return result("PKG.PYTHON_COMPILE", errors, {"scripts": count})


def normalized_reference(raw: str) -> str | None:
    value = raw.strip()
    if value.startswith(("http://", "https://", "#")):
        return None
    if ":" in value and not value.startswith(REFERENCE_PREFIXES):
        suffix = value.split(":", 1)[1]
        if suffix.startswith(REFERENCE_PREFIXES):
            value = suffix
    path = value.partition("#")[0]
    return path if path == "SKILL.md" or path.startswith(REFERENCE_PREFIXES) else None


def iter_references(value: Any, source: Path) -> Iterable[tuple[Path, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "$ref" and isinstance(child, str) and not child.startswith(("#", "http://", "https://")):
                yield source.parent / child.partition("#")[0], child
            elif key in ROOT_REFERENCE_KEYS and isinstance(child, str):
                normalized = normalized_reference(child)
                if normalized is not None:
                    # Package references use paths relative to the skill root.
                    yield Path(normalized), child
            elif key in ROOT_REFERENCE_LIST_KEYS and isinstance(child, list):
                for item in child:
                    if isinstance(item, str):
                        normalized = normalized_reference(item)
                        if normalized is not None:
                            # Marker consumed by check_references, which resolves from package root.
                            yield Path(normalized), item
            yield from iter_references(child, source)
    elif isinstance(value, list):
        for child in value:
            yield from iter_references(child, source)


def check_references(root: Path, documents: dict[Path, Any]) -> dict[str, Any]:
    errors: list[str] = []
    checked: set[tuple[str, str]] = set()
    for source, payload in documents.items():
        if source.relative_to(root).parts[:2] == ("references", "migration"):
            # Frozen V9 snapshots intentionally retain V9-local owner strings;
            # validate_migration resolves them against the explicit --v9-root.
            continue
        for unresolved, raw in iter_references(payload, source):
            # $ref paths are relative to their schema; all other package references are root-relative.
            if str(unresolved).startswith(str(root)):
                target = unresolved
            else:
                target = root / unresolved
            key = (source.relative_to(root).as_posix(), raw)
            if key in checked:
                continue
            checked.add(key)
            try:
                target.resolve().relative_to(root.resolve())
            except ValueError:
                errors.append(f"{key[0]}:reference_escapes_root:{raw}")
                continue
            target_text = target.relative_to(root).as_posix()
            if any(marker in target_text for marker in ("*", "?", "[")):
                if not any(item.is_file() for item in root.glob(target_text)):
                    errors.append(f"{key[0]}:missing_reference_pattern:{raw}")
            elif not target.is_file():
                errors.append(f"{key[0]}:missing_reference:{raw}")
    return result("PKG.REFERENCES", errors, {"references": len(checked)})


def check_eval_registry(root: Path, documents: dict[Path, Any]) -> dict[str, Any]:
    errors: list[str] = []
    case_locations: list[tuple[str, str]] = []
    registries = 0
    assigned = 0
    for path, payload in documents.items():
        if "evals" not in path.relative_to(root).parts or not isinstance(payload, dict) or "cases" not in payload:
            continue
        registries += 1
        cases = payload.get("cases")
        if not isinstance(cases, list):
            errors.append(f"{path.relative_to(root).as_posix()}:cases_not_array")
            continue
        for index, case in enumerate(cases):
            if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
                errors.append(f"{path.relative_to(root).as_posix()}:case_{index}_missing_id")
                continue
            case_locations.append((case["id"], path.relative_to(root).as_posix()))
            relative = path.relative_to(root).as_posix()
            claimed = (
                (relative in {"evals/behavior-cases.json", "evals/manuscript-behavior-cases.json"} and case.get("kind") == "semantic_plan")
                or (relative == "evals/v10-behavior-oracles.json" and case.get("kind") == "route")
                or (relative == "evals/v10-contract-oracles.json" and case.get("kind") == "legacy_v10_oracle" and case.get("driver") == "v10_lineage")
                or (relative == "evals/atomic-rule-cases.json" and case.get("kind") == "atomic_rule" and case.get("driver") == "atomic_rule_evals")
                or (relative == "evals/runtime-policy-cases.json" and case.get("kind") == "policy_mutation" and case.get("driver") == "maintenance_tests")
                or (relative == "evals/forward-acceptance-cases.json" and case.get("kind") == "forward_acceptance")
                or (relative == "evals/change-cases.json" and case.get("kind") in {"positive", "near_negative", "conflict", "state_binding"})
                or (case.get("kind") == "scenario" and case.get("driver") in {"scenario_tests", "maintenance_tests"})
            )
            if claimed:
                assigned += 1
            else:
                errors.append(f"unclaimed_eval_case:{case['id']}:{relative}")
    counts = Counter(identifier for identifier, _ in case_locations)
    for identifier, count in counts.items():
        if count > 1:
            locations = sorted(path for case_id, path in case_locations if case_id == identifier)
            errors.append(f"duplicate_case_id:{identifier}:{','.join(locations)}")
    if registries == 0 or not case_locations:
        errors.append("empty_eval_registry")
    if assigned != len(case_locations):
        errors.append(f"eval_assignment_count:{assigned}!={len(case_locations)}")
    return result(
        "PKG.EVAL_REGISTRY", errors,
        {"registries": registries, "cases": len(case_locations), "assigned": assigned},
    )


def check_release_metadata(root: Path, documents: dict[Path, Any]) -> dict[str, Any]:
    errors: list[str] = []
    plan = documents.get(root / "evals/release/release-plan.json")
    state = documents.get(root / "evals/release/release-state.json")
    manifest_path = root / "evals/release/frozen-manifest.json"
    skill_path = root / "SKILL.md"
    skill_version: str | None = None
    skill_release: str | None = None
    try:
        skill_text = skill_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(f"skill_metadata_unreadable:{type(exc).__name__}:{exc}")
    else:
        frontmatter = re.match(r"\A---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)", skill_text, re.DOTALL)
        if frontmatter is None:
            errors.append("skill_frontmatter_missing")
        else:
            body = frontmatter.group("body")
            versions = re.findall(r'^\s{2}version:\s*["\']?([^"\'\s]+)["\']?\s*$', body, re.MULTILINE)
            releases = re.findall(r'^\s{2}release:\s*["\']?([^"\'\s]+)["\']?\s*$', body, re.MULTILINE)
            if len(versions) != 1 or len(releases) != 1:
                errors.append("skill_release_metadata_shape")
            else:
                skill_version = versions[0]
                skill_release = releases[0]
                if skill_version != "11.0.0":
                    errors.append(f"skill_version_mismatch:{skill_version}")
    if not isinstance(plan, dict):
        errors.append("release_plan_unavailable")
    else:
        required = plan.get("required_drivers")
        drivers = plan.get("drivers")
        if not isinstance(required, list) or set(required) != REQUIRED_DRIVERS or len(required) != len(REQUIRED_DRIVERS):
            errors.append("required_drivers_mismatch")
        if not isinstance(drivers, list):
            errors.append("drivers_not_array")
        else:
            ids = [item.get("id") for item in drivers if isinstance(item, dict)]
            if set(ids) != REQUIRED_DRIVERS or len(ids) != len(REQUIRED_DRIVERS):
                errors.append("driver_declarations_mismatch")
            for item in drivers:
                if not isinstance(item, dict) or set(item) - {"id", "script", "args", "registry", "requires_v9_root", "requires_v10_root"}:
                    errors.append("driver_declaration_shape")
                    continue
                script = item.get("script")
                if not isinstance(script, str) or not script.startswith("scripts/") or ".." in Path(script).parts:
                    errors.append(f"driver_script_invalid:{item.get('id')}")
                elif EXPECTED_DRIVER_SCRIPTS.get(str(item.get("id"))) != script:
                    errors.append(f"driver_script_drift:{item.get('id')}")
                if item.get("id") == "quick_package" and item.get("args") != QUICK_RELEASE_ARGS:
                    errors.append("quick_package_invocation_context_drift")
    if not isinstance(state, dict):
        errors.append("release_state_unavailable")
    else:
        expected_keys = {
            "schema_version", "release_id", "status", "frozen_at", "manifest",
            "pre_freeze_gate_report_sha256",
        }
        if set(state) != expected_keys:
            errors.append("release_state_shape")
        if state.get("schema_version") != "11.0" or state.get("release_id") != "V11.0.0":
            errors.append("release_state_identity")
        if state.get("manifest") != "evals/release/frozen-manifest.json":
            errors.append("release_state_manifest_path")
        if skill_release is not None and skill_release != state.get("status"):
            errors.append(f"skill_release_state_mismatch:{skill_release}!={state.get('status')}")
        if state.get("status") == "candidate":
            if state.get("frozen_at") is not None or state.get("pre_freeze_gate_report_sha256") is not None:
                errors.append("candidate_has_freeze_attestation")
            if manifest_path.exists():
                errors.append("candidate_has_frozen_manifest")
        elif state.get("status") == "stable":
            if not isinstance(state.get("frozen_at"), str):
                errors.append("stable_missing_frozen_at")
            if not re.fullmatch(r"[0-9a-f]{64}", str(state.get("pre_freeze_gate_report_sha256", ""))):
                errors.append("stable_missing_gate_hash")
            if not manifest_path.is_file():
                errors.append("stable_missing_manifest")
        else:
            errors.append("release_state_status")
    return result("PKG.RELEASE_METADATA", errors)


def validate(root: Path) -> dict[str, Any]:
    documents, parse_errors = load_json_documents(root)
    results = [
        check_required(root),
        check_clean_tree(root),
        check_symlinks(root),
        check_json_parse(root, documents, parse_errors),
        check_schema_meta(root, documents),
        check_schema_instances(root, documents),
        check_python_compile(root),
        check_references(root, documents),
        check_eval_registry(root, documents),
        check_release_metadata(root, documents),
    ]
    failed = [item for item in results if item["status"] != "pass"]
    return {
        "schema_version": "11.0",
        "status": "pass" if not failed else "fail",
        "driver": "quick_package",
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--invocation-context",
        required=True,
        choices=["skill-audit", "skill-maintenance", "skill-release"],
        help="Explicit Skill-package context; project runtime is not a valid context.",
    )
    args = parser.parse_args()
    authorized_package = bool(os.environ.get("V11_AUTHORIZED_SKILL_PACKAGE_VALIDATION"))
    if args.invocation_context == "skill-release":
        authorized = (
            os.environ.get("V11_RELEASE_GATE_FRESH_PROCESS") == "quick_package"
            or authorized_package
        )
    elif args.invocation_context == "skill-maintenance":
        authorized = (
            os.environ.get("V11_SKILL_MAINTENANCE_PROCESS") == "1"
            or authorized_package
        )
    else:
        authorized = authorized_package
    if not authorized:
        print(json.dumps({
            "schema_version": "11.0", "status": "blocked", "driver": "quick_package",
            "error": "skill_package_validation_not_authorized_for_invocation_context",
            "invocation_context": args.invocation_context,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    root = args.root.resolve()
    report = validate(root)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
