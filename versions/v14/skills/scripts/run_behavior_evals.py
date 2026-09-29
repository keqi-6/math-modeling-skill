#!/usr/bin/env python3
"""Run V11 semantic-plan behavior registries without raw-prompt routing."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from lib_v10 import SKILL_ROOT, dump_json, json_output, load_json, now_iso
from state_v11 import evidence_binding_hash


MANUSCRIPT_CLOSURE_REF = "references/manuscript-change-closure.json"
EXPECTATION_SECTIONS = ("required", "forbidden", "exact", "budgets")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rules(path: Path) -> list[dict[str, Any]]:
    payload = load_json(path)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("rules"), list):
        return payload["rules"]
    raise ValueError(f"rule file has no rules array: {path}")


def validate_manuscript_contract(skill_root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    """Prove the closure preserves the complete frozen manuscript inventory."""
    path = skill_root / MANUSCRIPT_CLOSURE_REF
    if not path.is_file():
        return None, ["manuscript_change_closure_contract_missing"]
    contract = load_json(path)
    errors: list[str] = []
    if contract.get("schema_version") != "11.0":
        errors.append("manuscript_closure_schema_version")
    inventory = contract.get("semantic_inventory", {})
    source = skill_root / str(inventory.get("source", "rules/manuscript.json"))
    if not source.is_file():
        return contract, errors + ["manuscript_inventory_source_missing"]
    if inventory.get("source_sha256") != _sha256(source):
        errors.append("manuscript_inventory_hash_mismatch")
    active = {rule["id"] for rule in _rules(source) if rule.get("status") == "active"}
    grouped = {
        rule_id
        for values in inventory.get("rule_groups", {}).values()
        for rule_id in values
    }
    if active != grouped:
        errors.append(
            "manuscript_inventory_group_mismatch:missing="
            + ",".join(sorted(active - grouped))
            + ":extra=" + ",".join(sorted(grouped - active))
        )
    if inventory.get("active_rule_count") != len(active):
        errors.append("manuscript_inventory_count_mismatch")
    if "exact_manuscript_rule_ids" in json.dumps(contract, sort_keys=True):
        errors.append("manuscript_runtime_allowlist_forbidden")

    derived: set[str] = set()
    for name, closure in contract.get("closures", {}).items():
        closure_ids = set(closure.get("derived_expected_manuscript_rule_ids", []))
        closure_ids.update(closure.get("base_derived_expected_manuscript_rule_ids", []))
        closure_ids.update(
            rule_id
            for values in closure.get("derived_expected_rule_overlays_by_legacy_event", {}).values()
            for rule_id in values
        )
        unknown = closure_ids - active
        if unknown:
            errors.append(f"manuscript_closure_unknown_rules:{name}:" + ",".join(sorted(unknown)))
        derived.update(closure_ids)
        evaluation = set(closure.get("required_evaluation_manuscript_rule_ids", []))
        evaluation.update(closure.get("base_required_evaluation_manuscript_rule_ids", []))
        evaluation.update(
            rule_id
            for values in closure.get("required_evaluation_rule_overlays_by_event", {}).values()
            for rule_id in values
        )
        evaluation.update(closure.get("expected_not_applicable_manuscript_rule_ids", []))
        if evaluation - closure_ids:
            errors.append(f"manuscript_evaluation_outside_derived_selection:{name}")
    if derived != active:
        errors.append(
            "manuscript_closure_union_mismatch:missing="
            + ",".join(sorted(active - derived))
            + ":extra=" + ",".join(sorted(derived - active))
        )
    if contract.get("facet_to_legacy_event") != {
        "method": "method_section_write",
        "result": "result_section_write",
        "conclusion": "conclusion_write",
        "structure": "manuscript_structure",
    }:
        errors.append("manuscript_facet_legacy_event_mapping_mismatch")
    return contract, sorted(set(errors))


def make_fixture(root: Path, fixture: dict[str, Any]) -> None:
    """Create a minimal V11 state with exact reverse dependency edges."""
    if fixture.get("missing_state"):
        return
    for relative in fixture.get("files", []):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("V11 semantic-plan behavior fixture.\n", encoding="utf-8")
    timestamp = now_iso()
    declarations = fixture.get("components", [])
    known = {item["id"] for item in declarations}
    components: dict[str, dict[str, Any]] = {}
    for item in declarations:
        dependencies = list(item.get("dependencies", []))
        if set(dependencies) - known:
            raise ValueError(f"unknown dependencies for fixture component {item['id']}")
        terminal = item["state"] in {"S7", "D3", "A3"}
        components[item["id"]] = {
            "type": item["type"],
            "state": item["state"],
            "status": item.get("status", "closed" if terminal else "active"),
            "dependencies": dependencies,
            "consumers": [],
            "evidence": [],
            "decisions": [],
            "invalidated_at_revision": None,
            "updated_at": timestamp,
        }
    for component_id, component in components.items():
        for dependency in component["dependencies"]:
            components[dependency]["consumers"].append(component_id)
    for component in components.values():
        component["consumers"] = sorted(set(component["consumers"]))
    for declaration in fixture.get("evidence", []):
        component_id = declaration["component_id"]
        level = declaration["level"]
        if component_id not in components:
            raise ValueError(f"unknown evidence component {component_id}")
        evidence_id = declaration.get("id", f"EV-{component_id}-{level}")
        target = root / ".modeling/evidence-files" / f"{evidence_id}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"verified {level}\n", encoding="utf-8")
        claims = [f"claim:{component_id}:{level}"]
        components[component_id]["evidence"].append({
            "id": evidence_id,
            "level": level,
            "status": "pass",
            "kind": "file",
            "locator": {
                "path": target.relative_to(root).as_posix(),
                "sha256": _sha256(target),
            },
            "claim": f"{level} is current for {component_id}",
            "observed_at": timestamp,
            "producer": "v11_behavior_fixture",
            "subject_id": component_id,
            "input_refs": [],
            "claim_refs": claims,
            "binding_hash": evidence_binding_hash(component_id, level, [], claims),
            "recorded_revision": 1,
        })
    state = {
        "schema_version": "11.0",
        "revision": 1,
        "project": {
            "id": "eval-project",
            "state": fixture.get("project_state", "P0"),
            "required_components": sorted(components),
            "created_at": timestamp,
            "updated_at": timestamp,
        },
        "components": components,
        "artifacts": {},
        "open_decisions": [],
        "next_actions": [],
        "last_route": None,
        "executions": {},
        "history": [{
            "revision": 1,
            "event": "semantic_plan_eval_fixture",
            "at": timestamp,
            "subject": "eval-project",
            "details": {},
        }],
    }
    dump_json(root / ".modeling/state.json", state)


def _step_map(observed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(step.get("id")): step
        for step in observed.get("steps", [])
        if isinstance(step, dict) and step.get("id") is not None
    }


def _flatten(groups: Iterable[Iterable[str]]) -> set[str]:
    return {item for group in groups for item in group}


def _recovery(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("level", value.get("status", "object")))
    return str(value)


def _normalized_events(step: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    mapping = contract.get("facet_to_legacy_event", {})
    facets = (step.get("change_set") or {}).get("facets", [])
    return sorted({mapping[facet] for facet in facets if facet in mapping})


def _oracle(name: str, normalized: Iterable[str], contract: dict[str, Any]) -> set[str]:
    closure = contract.get("closures", {}).get(name)
    if not isinstance(closure, dict):
        raise ValueError(f"unknown manuscript closure oracle: {name}")
    if "derived_expected_manuscript_rule_ids" in closure:
        return set(closure["derived_expected_manuscript_rule_ids"])
    result = set(closure.get("base_derived_expected_manuscript_rule_ids", []))
    overlays = closure.get("derived_expected_rule_overlays_by_legacy_event", {})
    for event in normalized:
        result.update(overlays.get(event, []))
    return result


def _missing(expected: Iterable[str], actual: Iterable[str]) -> list[str]:
    return sorted(set(expected) - set(actual))


def _prefixed(values: Iterable[str], prefixes: Iterable[str]) -> list[str]:
    return sorted(value for value in set(values) if any(value.startswith(p) for p in prefixes))


def validate_case(case: dict[str, Any]) -> list[str]:
    if case.get("kind") != "semantic_plan":
        return ["legacy_raw_case_requires_semantic_plan"]
    errors: list[str] = []
    if not isinstance(case.get("plan"), dict):
        errors.append("semantic_plan_missing")
    expected = case.get("expected")
    if not isinstance(expected, dict):
        return errors + ["expectations_missing"]
    for section in EXPECTATION_SECTIONS:
        if not isinstance(expected.get(section), dict) or not expected[section]:
            errors.append(f"expectation_section_missing_or_empty:{section}")
    return errors


def assert_required(expected: dict[str, Any], observed: dict[str, Any], failures: list[str]) -> None:
    steps = observed.get("steps", [])
    values = {
        "step_ids": [step.get("id") for step in steps],
        "route_ids": [step.get("route_id") for step in steps],
        "rule_ids": observed.get("rule_ids", []),
        "events": _flatten(step.get("events", []) for step in steps),
        "component_ids": _flatten(step.get("component_ids", []) for step in steps),
        "context_refs": observed.get("context_refs", []),
    }
    if observed.get("status") != expected.get("status"):
        failures.append(f"required_status:{observed.get('status')!r}!={expected.get('status')!r}")
    for field, actual in values.items():
        missing = _missing(expected.get(field, []), actual)
        if missing:
            failures.append(f"required_{field}_missing:" + ",".join(missing))


def assert_forbidden(expected: dict[str, Any], observed: dict[str, Any], failures: list[str]) -> None:
    steps = observed.get("steps", [])
    values = {
        "route_ids": [step.get("route_id") for step in steps],
        "rule_ids": observed.get("rule_ids", []),
        "events": _flatten(
            list(step.get("events", []))
            + list(step.get("controller_events", []))
            + list(step.get("normalized_legacy_events", []))
            for step in steps
        ),
        "component_ids": _flatten(step.get("component_ids", []) for step in steps),
        "context_refs": observed.get("context_refs", []),
    }
    for field, actual in values.items():
        found = sorted(set(expected.get(field, [])) & set(actual))
        if found:
            failures.append(f"forbidden_{field}:" + ",".join(found))
    bad = _prefixed(values["rule_ids"], expected.get("rule_prefixes", []))
    if bad:
        failures.append("forbidden_rule_prefixes:" + ",".join(bad))
    by_step = _step_map(observed)
    for step_id, prefixes in expected.get("rule_prefixes_by_step", {}).items():
        bad = _prefixed(by_step.get(step_id, {}).get("rule_ids", []), prefixes)
        if bad:
            failures.append(f"forbidden_rule_prefixes_by_step:{step_id}:" + ",".join(bad))
    recoveries = {_recovery(step.get("recovery", "not_applicable")) for step in steps}
    found_recovery = sorted(set(expected.get("recovery_values", [])) & recoveries)
    if found_recovery:
        failures.append("forbidden_recovery_values:" + ",".join(found_recovery))


def assert_exact(
    expected: dict[str, Any],
    plan: dict[str, Any],
    observed: dict[str, Any],
    contract: dict[str, Any],
    failures: list[str],
) -> None:
    steps = observed.get("steps", [])
    by_step = _step_map(observed)
    planned = {step["id"]: step for step in plan.get("steps", [])}
    actual_ids = [step.get("id") for step in steps]
    if actual_ids != expected.get("step_ids"):
        failures.append(f"exact_step_ids:{actual_ids!r}!={expected.get('step_ids')!r}")
    for expectation, field in {
        "route_ids_by_step": "route_id",
        "modes_by_step": "mode",
        "tiers_by_step": "tier",
        "actions_by_step": "action",
        "component_ids_by_step": "component_ids",
        "events_by_step": "events",
        "change_sets_by_step": "change_set",
        "depends_on_by_step": "depends_on",
        "status_by_step": "status",
    }.items():
        wanted = expected.get(expectation, {})
        actual = {step_id: by_step.get(step_id, {}).get(field) for step_id in wanted}
        if actual != wanted:
            failures.append(f"exact_{expectation}:{actual!r}!={wanted!r}")
    wanted_reason_fragments = expected.get("reason_contains_by_step", {})
    for step_id, fragment in wanted_reason_fragments.items():
        reasons = by_step.get(step_id, {}).get("reasons", [])
        if not any(fragment in str(reason) for reason in reasons):
            failures.append(
                f"exact_reason_contains:{step_id}:missing={fragment!r}:reasons={reasons!r}"
            )
    wanted_recovery = expected.get("recovery_by_step", {})
    actual_recovery = {
        step_id: _recovery(by_step.get(step_id, {}).get("recovery", "not_applicable"))
        for step_id in wanted_recovery
    }
    if actual_recovery != wanted_recovery:
        failures.append(f"exact_recovery_by_step:{actual_recovery!r}!={wanted_recovery!r}")

    wanted_normalized = expected.get("normalized_legacy_events_by_step", {})
    actual_normalized: dict[str, list[str]] = {}
    for step_id in wanted_normalized:
        derived = _normalized_events(planned.get(step_id, {}), contract)
        resolver_value = by_step.get(step_id, {}).get("normalized_legacy_events")
        if resolver_value is not None and sorted(resolver_value) != derived:
            failures.append(
                f"resolver_normalized_legacy_events:{step_id}:{sorted(resolver_value)!r}!={derived!r}"
            )
        actual_normalized[step_id] = derived
    if actual_normalized != wanted_normalized:
        failures.append(
            f"exact_normalized_legacy_events_by_step:{actual_normalized!r}!={wanted_normalized!r}"
        )

    for step_id, closure_name in expected.get("manuscript_closures_by_step", {}).items():
        step = by_step.get(step_id, {})
        actual_name = (step.get("manuscript_closure") or {}).get("change_class")
        if actual_name != closure_name:
            failures.append(
                f"exact_manuscript_closure_name:{step_id}:{actual_name!r}!={closure_name!r}"
            )
        normalized = actual_normalized.get(step_id, _normalized_events(planned.get(step_id, {}), contract))
        oracle = _oracle(closure_name, normalized, contract)
        selected = {rule_id for rule_id in step.get("rule_ids", []) if rule_id.startswith("MAN.")}
        if selected != oracle:
            failures.append(
                f"exact_manuscript_rules:{step_id}:missing="
                + ",".join(sorted(oracle - selected))
                + ":extra=" + ",".join(sorted(selected - oracle))
            )


def assert_budgets(
    budgets: dict[str, Any], observed: dict[str, Any], output_bytes: int, failures: list[str]
) -> None:
    rules = observed.get("rule_ids", [])
    steps = observed.get("steps", [])
    if len(rules) > budgets.get("max_total_rules", len(rules)):
        failures.append(f"budget_total_rules:{len(rules)}>{budgets['max_total_rules']}")
    by_step = _step_map(observed)
    for step_id, limit in budgets.get("max_rules_by_step", {}).items():
        count = len(by_step.get(step_id, {}).get("rule_ids", []))
        if count > limit:
            failures.append(f"budget_step_rules:{step_id}:{count}>{limit}")
    if len(observed.get("context_refs", [])) > budgets.get("max_context_refs", 10**9):
        failures.append(
            f"budget_context_refs:{len(observed.get('context_refs', []))}>{budgets['max_context_refs']}"
        )
    if len(steps) > budgets.get("max_steps", 10**9):
        failures.append(f"budget_steps:{len(steps)}>{budgets['max_steps']}")
    if output_bytes > budgets.get("max_output_bytes", 10**18):
        failures.append(f"budget_output_bytes:{output_bytes}>{budgets['max_output_bytes']}")


def run_case(case: dict[str, Any], skill_root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    failures = validate_case(case)
    if failures:
        return {"id": case.get("id", "unnamed-case"), "status": "fail", "failures": failures}
    plan = case["plan"]
    with tempfile.TemporaryDirectory(prefix="v11-semantic-eval-") as directory:
        project_root = Path(directory)
        fixture = case.get("fixture")
        if fixture is not None:
            try:
                make_fixture(project_root, fixture)
            except (OSError, ValueError) as exc:
                return {"id": case["id"], "status": "fail", "failures": ["fixture_error:" + str(exc)]}
        command = [
            sys.executable,
            str(skill_root / "scripts/resolve_route.py"),
            "--plan-json",
            json.dumps(plan, ensure_ascii=False, sort_keys=True),
        ]
        if fixture is not None:
            command.extend(["--project-root", str(project_root)])
        process = subprocess.run(command, text=True, capture_output=True, cwd=skill_root, check=False)
        output_bytes = len(process.stdout.encode("utf-8"))
        try:
            observed = json.loads(process.stdout)
        except json.JSONDecodeError:
            return {
                "id": case["id"],
                "status": "fail",
                "failures": ["resolver_output_not_json", process.stderr.strip()],
                "observed": process.stdout,
            }
        if observed.get("request") != plan.get("request"):
            failures.append("raw_request_not_preserved")
        if len(observed.get("request_hash", "")) != 64:
            failures.append("request_hash_missing")
        if observed.get("schema_version") != "11.0":
            failures.append("resolver_schema_version")
        expected = case["expected"]
        assert_required(expected["required"], observed, failures)
        assert_forbidden(expected["forbidden"], observed, failures)
        assert_exact(expected["exact"], plan, observed, contract, failures)
        assert_budgets(expected["budgets"], observed, output_bytes, failures)
        expected_exit = {
            "resolved": 0,
            "partial": 3,
            "blocked": 2,
        }[expected["required"].get("status")]
        if process.returncode != expected_exit:
            failures.append(f"exit_code:{process.returncode}!={expected_exit}")
        return {
            "id": case["id"],
            "status": "pass" if not failures else "fail",
            "failures": failures,
            "observed": {
                "status": observed.get("status"),
                "step_statuses": {step.get("id"): step.get("status") for step in observed.get("steps", [])},
                "route_ids": [step.get("route_id") for step in observed.get("steps", [])],
                "rule_count": len(observed.get("rule_ids", [])),
                "rules_by_step": {
                    step.get("id"): len(step.get("rule_ids", [])) for step in observed.get("steps", [])
                },
                "context_ref_count": len(observed.get("context_refs", [])),
                "output_bytes": output_bytes,
            },
        }


def discover_registries(skill_root: Path, requested: list[Path]) -> list[Path]:
    if requested:
        return [path if path.is_absolute() else skill_root / path for path in requested]
    return sorted((skill_root / "evals").glob("*behavior-cases.json"))


def load_registries(
    skill_root: Path, paths: list[Path]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    cases: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    loaded: list[str] = []
    for path in paths:
        try:
            relative = str(path.relative_to(skill_root))
        except ValueError:
            relative = str(path)
        loaded.append(relative)
        if not path.is_file():
            failures.append({"id": "REGISTRY:" + relative, "status": "fail", "failures": ["registry_missing"]})
            continue
        try:
            payload = load_json(path)
        except (OSError, ValueError) as exc:
            failures.append({"id": "REGISTRY:" + relative, "status": "fail", "failures": ["registry_invalid:" + str(exc)]})
            continue
        if payload.get("schema_version") != "11.0":
            failures.append({
                "id": "REGISTRY:" + relative,
                "status": "fail",
                "failures": ["legacy_registry_requires_semantic_plan_migration"],
            })
        entries = payload.get("cases")
        if not isinstance(entries, list):
            failures.append({"id": "REGISTRY:" + relative, "status": "fail", "failures": ["registry_cases_not_array"]})
            continue
        for case in entries:
            if not isinstance(case, dict):
                failures.append({"id": "REGISTRY:" + relative, "status": "fail", "failures": ["registry_case_not_object"]})
                continue
            copied = dict(case)
            copied["_registry"] = relative
            cases.append(copied)
    return cases, failures, loaded


def run(
    skill_root: Path,
    selected: set[str] | None = None,
    requested_registries: list[Path] | None = None,
) -> dict[str, Any]:
    contract, contract_errors = validate_manuscript_contract(skill_root)
    paths = discover_registries(skill_root, requested_registries or [])
    cases, results, loaded = load_registries(skill_root, paths)
    ids = [case.get("id") for case in cases]
    duplicates = sorted({identifier for identifier in ids if ids.count(identifier) > 1})
    if duplicates:
        results.append({
            "id": "REGISTRY:DUPLICATE_CASE_IDS",
            "status": "fail",
            "failures": ["duplicate_case_ids:" + ",".join(str(item) for item in duplicates)],
        })
    if contract_errors:
        results.append({"id": "CONTRACT:MANUSCRIPT_CLOSURE", "status": "fail", "failures": contract_errors})
    known_ids = {str(case.get("id")) for case in cases}
    if selected is not None:
        unknown = sorted(selected - known_ids)
        if unknown:
            results.append({
                "id": "SELECTION:UNKNOWN_CASES",
                "status": "fail",
                "failures": ["unknown_case_ids:" + ",".join(unknown)],
            })
        cases = [case for case in cases if case.get("id") in selected]
    if contract is not None and not contract_errors:
        results.extend(run_case(case, skill_root, contract) for case in cases)
    failed = [item for item in results if item["status"] != "pass"]
    return {
        "schema_version": "11.0",
        "status": "pass" if not failed else "fail",
        "driver": "fresh_process_semantic_plans_only",
        "raw_prompt_routing": False,
        "registries": loaded,
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=SKILL_ROOT)
    parser.add_argument("--registry", action="append", type=Path, default=[])
    parser.add_argument("--case", action="append", default=[])
    args = parser.parse_args()
    result = run(args.root.resolve(), set(args.case) if args.case else None, args.registry)
    json_output(result)
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
