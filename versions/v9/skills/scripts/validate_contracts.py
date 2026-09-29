#!/usr/bin/env python3
"""Cross-validate V9 versions, owners, routes, states, modules, evals and migration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path


RELEASE = "9.0.0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot read JSON {path}: {exc}")
        return {}


def path_part(owner: str) -> str:
    return owner.split("#", 1)[0]


def validate(skill_root: Path, source_root: Path | None = None) -> list[str]:
    errors: list[str] = []
    skill_root = skill_root.resolve()
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "references/state-contract.json",
        "references/route-contract.json",
        "references/capability-registry.json",
        "references/artifact-contract.json",
        "references/context-budget.json",
        "references/receipt.schema.json",
        "references/maintenance-contract.md",
        "references/recovery-governance.md",
        "evals/registry.json",
        "evals/forward-results.json",
        "evals/differential-results.json",
    ]
    for relative in required:
        if not (skill_root / relative).is_file():
            errors.append(f"missing required file: {relative}")

    skill_text = (skill_root / "SKILL.md").read_text(encoding="utf-8") if (skill_root / "SKILL.md").exists() else ""
    if 'version: "9.0.0"' not in skill_text or "V9.0.0" not in skill_text:
        errors.append("SKILL.md does not consistently identify V9.0.0")
    ui_text = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8") if (skill_root / "agents" / "openai.yaml").exists() else ""
    if "V9" not in ui_text or "$mathematical-modeling-project-controller" not in ui_text:
        errors.append("openai.yaml identity/default prompt is not aligned with V9")

    state = load(skill_root / "references" / "state-contract.json", errors)
    routes_doc = load(skill_root / "references" / "route-contract.json", errors)
    caps_doc = load(skill_root / "references" / "capability-registry.json", errors)
    artifacts = load(skill_root / "references" / "artifact-contract.json", errors)
    context_budget = load(skill_root / "references" / "context-budget.json", errors)
    receipt = load(skill_root / "references" / "receipt.schema.json", errors)
    eval_doc = load(skill_root / "evals" / "registry.json", errors)
    forward_results = load(skill_root / "evals" / "forward-results.json", errors)
    differential_results = load(skill_root / "evals" / "differential-results.json", errors)
    disposition = load(skill_root / "references" / "migration" / "rule-disposition.json", errors)
    conflicts = load(skill_root / "references" / "migration" / "conflict-decisions.json", errors)
    module_manifest = load(skill_root / "references" / "migration" / "module-source-manifest.json", errors)
    ledger = load(skill_root / "references" / "migration" / "v1-v9-capability-ledger.json", errors)

    versions = {
        "state": state.get("contract_version"),
        "routes": routes_doc.get("release"),
        "capabilities": caps_doc.get("release"),
        "receipt": receipt.get("release"),
        "evals": eval_doc.get("release"),
        "ledger": ledger.get("release"),
        "modules": module_manifest.get("release"),
        "context_budget": context_budget.get("contract_version"),
        "forward_results": forward_results.get("release"),
        "differential_results": differential_results.get("release"),
    }
    for name, version in versions.items():
        if version != RELEASE:
            errors.append(f"{name} release is {version!r}, expected {RELEASE}")
    if routes_doc.get("status") != "stable" or caps_doc.get("status") != "stable":
        errors.append("route and capability contracts must be stable for release")
    if conflicts.get("unresolved") != 0:
        errors.append("unresolved conflict count is not zero")

    forward_scenarios = forward_results.get("scenarios", [])
    if forward_results.get("status") != "PASS" or len(forward_scenarios) < 6:
        errors.append("independent forward validation is incomplete")
    if forward_results.get("method", {}).get("independent_fresh_invocations", 0) < 8:
        errors.append("insufficient fresh forward-validation invocations")
    if any(item.get("final_status") != "PASS" for item in forward_scenarios):
        errors.append("a forward-validation scenario did not pass")
    for issue in forward_results.get("issues_found_and_fixed", []):
        if not issue.get("verified") or not issue.get("resolution") or not issue.get("verified_by"):
            errors.append(f"forward-validation issue lacks a verified resolution: {issue.get('id')}")

    differential = differential_results.get("measurement", {})
    v8_bootstrap = differential.get("v8_bootstrap", {})
    v9_init = differential.get("v9_explicit_initialization", {})
    if differential_results.get("status") != "PASS":
        errors.append("V8/V9 differential validation did not pass")
    if v9_init.get("files_created") != 1 or v9_init.get("created_file") != ".modeling/state.json":
        errors.append("V9 initialization differential does not match the artifact contract")
    if v9_init.get("files_created", 10**9) >= v8_bootstrap.get("files_created", -1):
        errors.append("V9 initialization did not reduce file creation relative to V8")
    if not all(differential_results.get("assertions", {}).values()):
        errors.append("a V8/V9 differential assertion failed")

    capabilities = caps_doc.get("capabilities", [])
    cap_ids = [cap.get("id") for cap in capabilities]
    duplicates = [key for key, count in Counter(cap_ids).items() if count > 1]
    if duplicates:
        errors.append(f"duplicate capability IDs: {duplicates}")
    for cap in capabilities:
        for field in ("id", "domain", "owner", "strength", "trigger", "expected", "forbidden"):
            if not cap.get(field):
                errors.append(f"capability {cap.get('id')} missing {field}")
        owner = path_part(cap.get("owner", ""))
        if owner and not (skill_root / owner).is_file():
            errors.append(f"capability {cap.get('id')} owner missing: {owner}")
        if cap.get("strength") not in {"MUST", "SHOULD", "MAY", "RETIRED"}:
            errors.append(f"capability {cap.get('id')} has invalid strength")

    routes = routes_doc.get("routes", [])
    route_ids = [route.get("id") for route in routes]
    route_duplicates = [key for key, count in Counter(route_ids).items() if count > 1]
    if route_duplicates:
        errors.append(f"duplicate route IDs: {route_duplicates}")
    if routes_doc.get("transitive_loading") is not False:
        errors.append("transitive route loading must be disabled")
    if routes_doc.get("catchalls_count_for_reachability") is not False:
        errors.append("catchalls must not count for reachability")
    recovery_policy = routes_doc.get("recovery_policy", {})
    if recovery_policy.get("default") != "if_project_state_exists":
        errors.append("route recovery default must be if_project_state_exists")
    recovery_overrides = recovery_policy.get("overrides", {})
    for required_route in ("RT-ADVISORY-PROJECT", "RT-PROJECT-INIT", "RT-SKILL-AUDIT", "RT-SKILL-CHANGE"):
        if recovery_overrides.get(required_route) != "not_applicable":
            errors.append(f"{required_route} must have not_applicable recovery")
    if recovery_overrides.get("RT-PROJECT-RESUME") != "required":
        errors.append("RT-PROJECT-RESUME must require recovery assessment")

    valid_modes = set(state.get("execution_modes", {}))
    valid_states = {"UNINITIALIZED", "V9"}
    for component in state.get("component_types", {}).values():
        states = component.get("states", [])
        valid_states.update(states)
        if component.get("terminal") not in states:
            errors.append("component terminal state is not in its state list")
        for before, afters in component.get("transitions", {}).items():
            if before not in states or any(after not in states for after in afters):
                errors.append(f"invalid transition in component state contract: {before}->{afters}")

    evals = eval_doc.get("evals", [])
    eval_ids = {item.get("id") for item in evals}
    covered_caps = {cap for item in evals for cap in item.get("capabilities", [])}
    selector_owners: dict[tuple[str, str, str, str], str] = {}
    routed_modules: set[str] = set()
    optional_modules: set[str] = set()
    for route in routes:
        route_id = route.get("id", "<missing>")
        for field in ("modes", "object", "actions", "states", "modules", "capabilities", "allowed_actions", "write_allowed", "expected_outputs", "exclusions", "tests"):
            if field not in route:
                errors.append(f"route {route_id} missing {field}")
        if not set(route.get("modes", [])).issubset(valid_modes):
            errors.append(f"route {route_id} has invalid mode")
        if not set(route.get("states", [])).issubset(valid_states):
            errors.append(f"route {route_id} has invalid state")
        if not set(route.get("capabilities", [])).issubset(set(cap_ids)):
            errors.append(f"route {route_id} references unknown capability")
        if not set(route.get("tests", [])).issubset(eval_ids):
            errors.append(f"route {route_id} references unknown eval")
        for module in route.get("modules", []):
            routed_modules.add(module)
            if any(char in module for char in "*?["):
                errors.append(f"route {route_id} uses wildcard module: {module}")
            if not (skill_root / module).is_file():
                errors.append(f"route {route_id} module missing: {module}")
        for module in route.get("optional_modules", []):
            optional_modules.add(module)
            if any(char in module for char in "*?["):
                errors.append(f"route {route_id} uses wildcard optional module: {module}")
            if not (skill_root / module).is_file():
                errors.append(f"route {route_id} optional module missing: {module}")
        modes = route.get("modes", [])
        has_readonly = any(not state["execution_modes"][mode]["writes"] for mode in modes if mode in valid_modes)
        has_write = any(state["execution_modes"][mode]["writes"] for mode in modes if mode in valid_modes)
        declared_write = route.get("write_allowed")
        if has_readonly and not has_write and declared_write is not False:
            errors.append(f"read-only route {route_id} is not write_allowed=false")
        if has_readonly and has_write and declared_write != "mode_dependent":
            errors.append(f"mixed-mode route {route_id} must be mode_dependent")
        if "skill_maintenance" in modes and route.get("object") != "skill":
            errors.append(f"maintenance route {route_id} targets non-skill object")
        for mode in modes:
            for action in route.get("actions", []):
                for route_state in route.get("states", []):
                    key = (mode, route.get("object"), action, route_state)
                    prior = selector_owners.get(key)
                    if prior:
                        errors.append(f"ambiguous selector {key}: {prior}, {route_id}")
                    selector_owners[key] = route_id

        budget = context_budget.get("overrides", {}).get(route_id, {})
        max_modules = budget.get("max_modules", context_budget.get("default_max_modules", 0))
        max_lines = budget.get("max_lines", context_budget.get("default_max_lines", 0))
        direct_lines = sum(
            len((skill_root / module).read_text(encoding="utf-8").splitlines())
            for module in route.get("modules", [])
            if (skill_root / module).is_file()
        )
        if len(route.get("modules", [])) > max_modules:
            errors.append(f"route {route_id} exceeds direct module budget")
        if direct_lines > max_lines:
            errors.append(f"route {route_id} exceeds direct line budget: {direct_lines}>{max_lines}")

    for cap in capabilities:
        if cap.get("strength") == "MUST" and cap.get("id") not in covered_caps:
            errors.append(f"MUST capability lacks eval coverage: {cap.get('id')}")

    module_paths = {entry.get("module") for entry in module_manifest.get("modules", [])}
    if module_paths != {path for path in routed_modules | optional_modules if path.startswith("references/modules/")}:
        errors.append("generated module set and routed/optional module set differ")
    for entry in module_manifest.get("modules", []):
        path = skill_root / entry.get("module", "")
        if not path.is_file():
            errors.append(f"generated module missing: {entry.get('module')}")
            continue
        if sha256(path) != entry.get("sha256"):
            errors.append(f"generated module hash mismatch: {entry.get('module')}")
        first_lines = "\n".join(path.read_text(encoding="utf-8").splitlines()[:10])
        if "全局权限" not in first_lines or "不触发递归加载" not in first_lines:
            errors.append(f"module boundary missing: {entry.get('module')}")

    dispositions = disposition.get("entries", [])
    if len(dispositions) != 38 or len({entry.get("source") for entry in dispositions}) != 38:
        errors.append("V8 rule disposition must contain exactly 38 unique rule files")
    active_sources = {entry.get("source") for entry in dispositions if entry.get("active_detail") is True}
    manifest_sources = {source.get("path") for module in module_manifest.get("modules", []) for source in module.get("sources", [])}
    if active_sources != manifest_sources:
        errors.append("active V8 sources and generated module sources differ")
    if source_root and source_root.is_dir():
        for module in module_manifest.get("modules", []):
            for source in module.get("sources", []):
                path = source_root / source["path"]
                if not path.is_file() or sha256(path) != source.get("sha256"):
                    errors.append(f"frozen V8 source mismatch: {source.get('path')}")

    coverage = ledger.get("coverage", {})
    if coverage.get("v1_v6_atomic_entries", 0) < 1859 or coverage.get("unmapped_entries") != 0:
        errors.append("legacy capability coverage is incomplete")
    if coverage.get("v7_native_entries", 0) < 9 or coverage.get("v8_native_entries", 0) < 5:
        errors.append("V7/V8 native capability coverage is incomplete")
    ledger_entries = ledger.get("entries", [])
    ledger_ids = [entry.get("capability_id") for entry in ledger_entries]
    if len(ledger_ids) != len(set(ledger_ids)):
        errors.append("migration ledger contains duplicate capability IDs")
    for entry in ledger_entries:
        owner = path_part(entry.get("v9_owner", ""))
        if owner and not (skill_root / owner).exists():
            errors.append(f"migration entry {entry.get('capability_id')} owner missing: {owner}")
            if len(errors) > 100:
                break

    if artifacts.get("minimal_project_initialization") != [".modeling/state.json"]:
        errors.append("minimal initialization is not exactly .modeling/state.json")
    if artifacts.get("readonly_creates_files") is not False:
        errors.append("read-only artifact policy must forbid file creation")

    markdown_link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for target in markdown_link_pattern.findall(skill_text):
        if target.startswith(("http://", "https://", "#")):
            continue
        if not (skill_root / target.split("#", 1)[0]).exists():
            errors.append(f"SKILL.md link target missing: {target}")

    pycache = list(skill_root.rglob("__pycache__")) + list(skill_root.rglob("*.pyc"))
    if pycache:
        errors.append("release contains Python cache artifacts")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    errors = validate(args.skill_root, args.source_root)
    if errors:
        print(json.dumps({"status": "FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "release": RELEASE}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
