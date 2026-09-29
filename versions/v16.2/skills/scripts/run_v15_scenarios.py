#!/usr/bin/env python3
"""Run the active disposable V15 release scenarios.

The driver owns the retained V14 filesystem outcomes and the V15 behavior
boundaries that must survive retirement of the historical diagnostic runners.
Every project used here is created inside a fresh temporary directory.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from lib_v10 import build_workspace_manifest, sha256_file, sha256_text
from lib_v11 import canonical_json, resolve
from recovery_v16 import make_baseline_meta
from state_v11 import current_evidence_levels, evidence_binding_hash
from validate_receipt import checkpoint_pair_hash


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def directory_alias_fixture(link: Path, target: Path) -> str:
    """Exercise real resolved-path aliases without requiring Windows symlink privilege."""
    kind = "directory_symlink"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt" or getattr(exc, "winerror", None) != 1314:
            raise
        import _winapi
        _winapi.CreateJunction(str(target.resolve()), str(link))
        kind = "windows_directory_junction"
    if not link.is_dir() or link.resolve() != target.resolve():
        raise RuntimeError("directory alias fixture did not resolve to its intended target")
    return kind


def run(script: Path, *arguments: str) -> tuple[int, dict[str, Any], str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, "-B", str(script), *arguments],
        text=True, capture_output=True, check=False, timeout=15, env=environment,
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {}
    return process.returncode, payload, (process.stderr + process.stdout)[-800:]


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def read_state(project: Path) -> dict[str, Any]:
    return json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))


def seal_fixture_baseline(project: Path, source_id: str) -> None:
    """Seal completed disposable setup without inventing a recovery receipt."""
    state = read_state(project)
    state["watch_roots"] = ["."]
    state["workspace_baseline"] = build_workspace_manifest(project, ["."])
    state["workspace_baseline_meta"] = make_baseline_meta(
        project,
        state,
        state["workspace_baseline"],
        captured_revision=state["revision"],
        established_kind="trusted_same_window_checkpoint",
        source_id=source_id,
        coverage_roots=["."],
        coverage_complete=True,
    )
    write_json(project / ".modeling/state.json", state)


def resolution_errors(value: dict[str, Any]) -> str:
    return json.dumps(
        {
            "errors": value.get("errors", []),
            "steps": [
                {"id": step.get("id"), "status": step.get("status"), "reasons": step.get("reasons", [])}
                for step in value.get("steps", [])
            ],
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def file_evidence(
    project: Path,
    component_id: str,
    identifier: str,
    level: str,
    relative_path: str,
    *,
    input_refs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    refs = input_refs or []
    claims = [f"claim:{component_id}:{level}:{identifier}"]
    return {
        "id": identifier,
        "level": level,
        "status": "pass",
        "kind": "file",
        "locator": {"path": relative_path, "sha256": sha256_file(project / relative_path)},
        "claim": f"{level} is bound to the observed disposable-project file.",
        "observed_at": "2026-08-27T00:00:00Z",
        "producer": "v15-scenario",
        "subject_id": component_id,
        "input_refs": refs,
        "claim_refs": claims,
        "binding_hash": evidence_binding_hash(component_id, level, refs, claims),
    }


def not_applicable_evidence(
    component_id: str,
    identifier: str,
    level: str,
    decision_id: str,
    spec_path: str,
    spec_identity: str,
) -> dict[str, Any]:
    refs = [{
        "kind": "artifact", "id": spec_path, "identity": spec_identity,
        "facet": "specification",
    }]
    claims = [f"claim:{component_id}:{level}:{identifier}"]
    return {
        "id": identifier,
        "level": level,
        "status": "not_applicable",
        "kind": "decision",
        "locator": {"decision_id": decision_id, "recorded_at": "2026-08-27T00:00:00Z"},
        "claim": f"{level} is not triggered within the frozen specification boundary.",
        "observed_at": "2026-08-27T00:00:00Z",
        "producer": "v15-scenario",
        "subject_id": component_id,
        "input_refs": refs,
        "claim_refs": claims,
        "binding_hash": evidence_binding_hash(component_id, level, refs, claims),
        "applicability": {
            "disposition": "justified_not_triggered",
            "rationale": f"The frozen specification does not trigger the {level} risk.",
            "applicability_basis": ["current frozen specification and registered claim scope"],
            "claim_boundaries": ["do not claim validity outside the reviewed specification"],
        },
    }


def evidence(component_id: str, identifier: str, level: str) -> dict[str, Any]:
    refs: list[dict[str, str]] = []
    claims: list[str] = []
    return {
        "id": identifier,
        "level": level,
        "status": "pass",
        "kind": "observation",
        "locator": {
            "subject": component_id,
            "method": "independent disposable scenario inspection",
            "value": "verified",
        },
        "claim": f"{level} is verified in the disposable scenario.",
        "observed_at": "2026-08-26T00:00:00Z",
        "producer": "v14-scenario",
        "subject_id": component_id,
        "input_refs": refs,
        "claim_refs": claims,
        "binding_hash": evidence_binding_hash(component_id, level, refs, claims),
    }


def validation(component_id: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"],
        "component_id": component_id,
        "level": record["level"],
        "status": "pass",
        "evidence_ref": f"state:components/{component_id}/evidence/{record['id']}",
        "input_refs": record["input_refs"],
        "claim_refs": record["claim_refs"],
        "binding_hash": record["binding_hash"],
    }


def end_receipt(
    project: Path, plan: dict[str, Any], resolution: dict[str, Any],
    execution_id: str, validations: list[dict[str, Any]],
    changed_identities: list[dict[str, str]],
) -> dict[str, Any]:
    state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
    execution = state["executions"][execution_id]
    step = resolution["steps"][0]
    transitions = []
    for entry in state["history"]:
        if not execution["start_revision"] < entry["revision"] <= state["revision"]:
            continue
        if entry["event"] in {"component_transition", "project_transition"}:
            transitions.append({
                "component_id": entry["subject"],
                "from": entry["details"]["from"],
                "to": entry["details"]["to"],
            })
    return {
        "receipt_type": "end", "schema_version": "11.0",
        "request": plan["request"], "request_hash": sha256_text(plan["request"]),
        "semantic_plan": plan, "plan_hash": sha256_text(canonical_json(plan)),
        "step_id": step["id"], "execution_id": execution_id,
        "pair_hash": checkpoint_pair_hash(execution),
        "project_root": str(project.resolve()), "tier": step["tier"], "mode": step["mode"],
        "route_ids": [step["route_id"]], "rule_ids": step["rule_ids"],
        "component_ids": step["component_ids"],
        "before_revision": execution["start_revision"], "after_revision": state["revision"],
        "change_set": step["change_set"], "changed_identities": changed_identities,
        "validations": validations, "state_transitions": transitions,
        "open_issues": sorted(item["id"] for item in state["open_decisions"] if item["status"] == "open"),
    }


def identity_plan(component_id: str, paths: list[str], plan_id: str) -> dict[str, Any]:
    return {
        "schema_version": "11.0",
        "plan_id": plan_id,
        "request": "登记或刷新声明身份并检查精确消费者边界",
        "window_context": "same_window",
        "steps": [{
            "id": "identity",
            "tier": "G2_CHECKPOINT",
            "mode": "mutate",
            "object": "data",
            "action": "audit",
            "component_id": component_id,
            "events": ["recovery_assessment", "data_audit", "dataset_register"],
            "facts": {
                "predictive_or_evaluative_use": False,
                "change_set_complete": True,
                "propagation_complete": True,
            },
            "depends_on": [],
            "change_set": {"paths": paths, "facets": ["data_identity"], "claim_refs": []},
        }],
    }


def begin_formal(
    manager: Path,
    root: Path,
    project: Path,
    workspace: Path,
    plan: dict[str, Any],
    execution_id: str,
) -> tuple[dict[str, Any], Path, list[tuple[str, int, str]]]:
    plan_path = workspace / f"{execution_id}-plan.json"
    write_json(plan_path, plan)
    resolution = resolve(plan, project, root)
    state = read_state(project)
    checkpoint_code, _, checkpoint_log = run(
        manager,
        "checkpoint", "--project-root", str(project),
        "--expected-revision", str(state["revision"]), "--gate", "G2",
        "--plan", str(plan_path), "--step-id", "identity",
    )
    start_code, _, start_log = run(
        manager,
        "record-route", "--project-root", str(project),
        "--plan", str(plan_path), "--step-id", "identity",
        "--execution-id", execution_id,
    )
    return resolution, plan_path, [
        ("checkpoint", checkpoint_code, checkpoint_log),
        ("start", start_code, start_log),
    ]


def close_formal(
    manager: Path,
    project: Path,
    workspace: Path,
    plan: dict[str, Any],
    resolution: dict[str, Any],
    execution_id: str,
    validations: list[dict[str, Any]],
    changed_identities: list[dict[str, str]],
) -> tuple[int, str, Path]:
    path = workspace / f"{execution_id}-receipt.json"
    state = read_state(project)
    execution = state.get("executions", {}).get(execution_id)
    if not isinstance(execution, dict):
        return (
            2,
            "fixture_precondition_failed: formal execution was not opened; "
            "inspect checkpoint/start stage logs",
            path,
        )
    receipt = end_receipt(
        project, plan, resolution, execution_id, validations, changed_identities,
    )
    write_json(path, receipt)
    code, _, log = run(
        manager, "close-execution", "--project-root", str(project),
        "--receipt", str(path),
    )
    return code, log, path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    manager = root / "scripts/state_manager.py"
    receipt_validator = root / "scripts/validate_receipt.py"
    cases: list[dict[str, Any]] = []

    def record(identifier: str, passed: bool, evidence_text: str) -> None:
        cases.append({"id": identifier, "status": "pass" if passed else "fail", "evidence": evidence_text})

    def record_registry_case(case: dict[str, Any], project_root: Path) -> None:
        """Run the retained human-curated V15 route oracle in the active driver."""
        observed = resolve(case["plan"], project_root, root)
        expected = case["expected"]
        failures: list[str] = []
        if observed.get("status") != expected["status"]:
            failures.append(f"status:{observed.get('status')}!={expected['status']}")
        if observed.get("route_ids", []) != expected.get("route_ids_exact", []):
            failures.append("route_ids:" + json.dumps(observed.get("route_ids", []), ensure_ascii=False))
        actual_rules = set(observed.get("rule_ids", []))
        for rule_id in expected.get("rule_ids_include", []):
            if rule_id not in actual_rules:
                failures.append("missing_rule:" + rule_id)
        for rule_id in expected.get("rule_ids_exclude", []):
            if rule_id in actual_rules:
                failures.append("unexpected_rule:" + rule_id)
        actual_components = {
            step.get("id"): step.get("component_ids", [])
            for step in observed.get("steps", [])
        }
        for step_id, component_ids in expected.get("component_ids_by_step_exact", {}).items():
            if actual_components.get(step_id) != component_ids:
                failures.append(
                    "component_ids:" + step_id + ":"
                    + json.dumps(actual_components.get(step_id), ensure_ascii=False)
                )
        grant_events = {
            grant.get("event") for grant in observed.get("action_grants", [])
            if isinstance(grant, dict)
        }
        for event in expected.get("action_grant_events_include", []):
            if event not in grant_events:
                failures.append("missing_action_grant_event:" + event)
        error_text = resolution_errors(observed)
        for token in expected.get("error_contains", []):
            if token not in error_text:
                failures.append("missing_error_token:" + token)
        record(
            case["id"], not failures,
            "failures=" + json.dumps(failures, ensure_ascii=False)
            + ";status=" + str(observed.get("status"))
            + ";routes=" + json.dumps(observed.get("route_ids", []), ensure_ascii=False)
            + ";focus_rules=" + json.dumps(sorted(
                rule_id for rule_id in actual_rules
                if rule_id.startswith(("DATA.", "MOD.", "VER.", "VIS.", "EVD.", "MAN."))
            ), ensure_ascii=False),
        )

    with tempfile.TemporaryDirectory(prefix="v15-scenarios-") as raw:
        workspace = Path(raw)
        routing_project = workspace / "routing-project"
        routing_project.mkdir()
        project = workspace / "project"
        init_code, _, init_log = run(manager, "init", "--project-root", str(project), "--project-id", "demo")
        add_code, _, add_log = run(
            manager, "add-component", "--project-root", str(project),
            "--component-id", "INPUTS", "--type", "shared_data",
        )
        relative_files = sorted(path.relative_to(project).as_posix() for path in project.rglob("*") if path.is_file())
        record(
            "SCENARIO.PLATFORM.INIT_CONTROL_ONLY",
            init_code == 0 and add_code == 0 and relative_files == [".modeling/state.json"],
            f"files={relative_files};log={init_log}{add_log}",
        )

        def platform_plan(
            relative_path: str,
            identifier: str,
            *,
            request: str = "在受控项目命名空间内写入一个保留产物。",
            facts: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return {
                "schema_version": "11.0", "plan_id": identifier,
                "request": request,
                "window_context": "same_window",
                "steps": [{
                    "id": "write", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "project", "action": "plan", "component_id": None,
                    "events": ["project_planning"], "facts": facts or {}, "depends_on": [],
                    "change_set": {
                        "paths": [relative_path], "facets": ["project_plan"],
                        "claim_refs": [],
                    },
                }],
            }

        def platform_extension(
            quote: str, namespaces: list[str]
        ) -> dict[str, Any]:
            return {
                "approval_quote": quote,
                "top_level_namespaces": namespaces,
                "purpose": "承载项目已明确需要保留的运行支持产物。",
                "rollback": "回滚时删除该次批准的物理命名空间。",
            }

        def recovery_control_plan(
            relative_path: str, identifier: str, events: list[str]
        ) -> dict[str, Any]:
            return {
                "schema_version": "11.0", "plan_id": identifier,
                "request": "恢复项目控制状态并记录恢复评估。",
                "window_context": "same_window",
                "steps": [{
                    "id": "recover", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "project", "action": "recover", "component_id": None,
                    "events": events, "facts": {}, "depends_on": [],
                    "change_set": {
                        "paths": [relative_path], "facets": ["identity_inventory"],
                        "claim_refs": [],
                    },
                }],
            }

        established_file = project / "<未收录-队友材料>/Graph2.png"
        established_file.parent.mkdir(parents=True)
        established_file.write_bytes(b"existing project convention\n")
        existing_reserved = project / ".git/config"
        existing_reserved.parent.mkdir(parents=True)
        existing_reserved.write_text("[core]\n", encoding="utf-8")
        existing_transient = project / ".pytest_cache/v/cache/nodeids"
        existing_transient.parent.mkdir(parents=True)
        existing_transient.write_text("[]\n", encoding="utf-8")
        existing_boundary_project = workspace / "platform-existing-boundaries"
        for relative, content in (
            (".modeling/new-evil.json", "{}\n"),
            (".codex/existing.json", "{}\n"),
            (".venv/bin/activate", "existing environment\n"),
        ):
            target = existing_boundary_project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        outside_project = workspace / "platform-outside"
        outside_project.mkdir()
        escape_alias_kind = directory_alias_fixture(project / "escape-link", outside_project)
        physical_paper = project / "paper"
        physical_paper.mkdir()
        internal_alias_kind = directory_alias_fixture(project / "paper-link", physical_paper)

        platform_positive_paths = [
            "planning/01_scope.md",
            "paper/main.tex",
            "paper-link/one.tex",
            "output/q3/result.json",
            "paper/figures/system.svg",
            "output/q3/result-chart.png",
            "pyproject.toml",
            "requirements.txt",
            ".gitignore",
            "tests/test_model.py",
            "notebooks/eda.ipynb",
            "config/settings.yml",
            "figures/overview.svg",
            "<未收录-队友材料>/Graph3.png",
        ]
        platform_positive = {
            path: resolve(platform_plan(path, f"platform-positive-{index}"), project, root)
            for index, path in enumerate(platform_positive_paths)
        }
        logs_quote = "批准 logs 作为运行日志命名空间"
        setup_quote = "批准 setup.cfg 作为根级配置文件"
        platform_manual_positive = {
            "manual-logs": resolve(
                platform_plan(
                    "logs/run.log", "platform-manual-logs",
                    request=logs_quote + "，仅保留本项目的必要运行日志。",
                    facts={"platform_extension": platform_extension(logs_quote, ["logs"])},
                ),
                project, root,
            ),
            "manual-root-setup": resolve(
                platform_plan(
                    "setup.cfg", "platform-manual-setup",
                    request=setup_quote + "，仅用于项目工具配置。",
                    facts={
                        "platform_extension": platform_extension(setup_quote, ["setup.cfg"])
                    },
                ),
                project, root,
            ),
        }
        platform_controller_positive = {
            "controller-state": resolve(
                recovery_control_plan(
                    ".modeling/state.json", "platform-controller-state",
                    ["recovery_assessment"],
                ),
                routing_project, root,
            ),
            "controller-recovery": resolve(
                recovery_control_plan(
                    ".modeling/recovery/session.json", "platform-controller-recovery",
                    ["recovery_assessment"],
                ),
                routing_project, root,
            ),
        }

        wrong_quote_extension = platform_extension(logs_quote, ["logs"])
        wrong_scope_extension = platform_extension(logs_quote, ["logs"])
        reserved_extension = platform_extension("批准 git 命名空间", [".git"])
        transient_extension = platform_extension("批准 venv 命名空间", [".venv"])
        alias_conflict_plan = {
            "schema_version": "11.0", "plan_id": "platform-alias-conflict",
            "request": "两个无依赖步骤声明同一稿件路径。",
            "window_context": "same_window",
            "steps": [
                {
                    **deepcopy(platform_plan("paper/main.tex", "canonical")["steps"][0]),
                    "id": "canonical",
                },
                {
                    **deepcopy(platform_plan("paper/./main.tex", "alias")["steps"][0]),
                    "id": "alias",
                },
            ],
        }
        physical_alias_unordered_plan = {
            "schema_version": "11.0", "plan_id": "platform-physical-alias-unordered",
            "request": "两个无依赖步骤通过不同的项目内路径声明同一物理稿件。",
            "window_context": "same_window",
            "steps": [
                {
                    **deepcopy(platform_plan("paper/main.tex", "physical-canonical")["steps"][0]),
                    "id": "physical-canonical",
                },
                {
                    **deepcopy(platform_plan("paper-link/main.tex", "physical-link")["steps"][0]),
                    "id": "physical-link",
                },
            ],
        }
        physical_alias_same_step_plan = platform_plan(
            "paper/main.tex", "physical-same-step"
        )
        physical_alias_same_step_plan["request"] = (
            "同一步骤通过两个项目内路径声明同一物理稿件。"
        )
        physical_alias_same_step_plan["steps"][0]["change_set"]["paths"] = [
            "paper/main.tex", "paper-link/main.tex",
        ]
        platform_negative_specs: list[tuple[str, dict[str, Any], Path, str]] = [
            (
                "fresh-scratch",
                platform_plan("scratch/notes.md", "platform-negative-scratch"),
                project, "unknown_namespace:scratch/notes.md",
            ),
            (
                "fresh-arbitrary",
                platform_plan("new-arbitrary/notes.md", "platform-negative-arbitrary"),
                project, "unknown_namespace:new-arbitrary/notes.md",
            ),
            (
                "manual-missing",
                platform_plan("logs/no-approval.log", "platform-manual-missing"),
                project, "unknown_namespace:logs/no-approval.log",
            ),
            (
                "manual-wrong-quote",
                platform_plan(
                    "logs/wrong-quote.log", "platform-manual-wrong-quote",
                    request="当前请求不包含所声称的批准原文。",
                    facts={"platform_extension": wrong_quote_extension},
                ),
                project, "platform_extension_quote_not_in_request",
            ),
            (
                "manual-wrong-root",
                platform_plan(
                    "reports/run.log", "platform-manual-wrong-root",
                    request=logs_quote + "，但该批准不能用于其他根目录。",
                    facts={"platform_extension": wrong_scope_extension},
                ),
                project, "platform_extension_scope_mismatch:reports/run.log",
            ),
            (
                "manual-unused",
                platform_plan(
                    "planning/extension-not-needed.md", "platform-manual-unused",
                    request=logs_quote + "，但当前路径本已属于规范命名空间。",
                    facts={
                        "platform_extension": platform_extension(logs_quote, ["logs"])
                    },
                ),
                project, "platform_extension_unused",
            ),
            (
                "manual-reserved",
                platform_plan(
                    ".git/config", "platform-manual-reserved",
                    request="批准 git 命名空间，尝试扩展保留路径。",
                    facts={"platform_extension": reserved_extension},
                ),
                project, "reserved_namespace:.git/config",
            ),
            (
                "manual-transient",
                platform_plan(
                    ".venv/bin/activate", "platform-manual-transient",
                    request="批准 venv 命名空间，尝试扩展保留路径。",
                    facts={"platform_extension": transient_extension},
                ),
                project, "transient_declared_retained:.venv/bin/activate",
            ),
            (
                "existing-transient",
                platform_plan(
                    ".pytest_cache/v/cache/nodeids", "platform-existing-transient"
                ),
                project, "transient_declared_retained:.pytest_cache/v/cache/nodeids",
            ),
            (
                "existing-git",
                platform_plan(".git/config", "platform-existing-git"),
                project, "reserved_namespace:.git/config",
            ),
            (
                "fresh-git",
                platform_plan(".git/hooks/pre-commit", "platform-fresh-git"),
                project, "reserved_namespace:.git/hooks/pre-commit",
            ),
            (
                "fresh-modeling-evil",
                platform_plan(".modeling/new-evil.json", "platform-fresh-modeling"),
                project, "reserved_namespace:.modeling/new-evil.json",
            ),
            (
                "existing-modeling-evil",
                platform_plan(".modeling/new-evil.json", "platform-existing-modeling"),
                existing_boundary_project, "reserved_namespace:.modeling/new-evil.json",
            ),
            (
                "existing-codex",
                platform_plan(".codex/existing.json", "platform-existing-codex"),
                existing_boundary_project, "reserved_namespace:.codex/existing.json",
            ),
            (
                "fresh-venv",
                platform_plan(".venv/bin/activate", "platform-fresh-venv"),
                project, "transient_declared_retained:.venv/bin/activate",
            ),
            (
                "existing-venv",
                platform_plan(".venv/bin/activate", "platform-existing-venv"),
                existing_boundary_project, "transient_declared_retained:.venv/bin/activate",
            ),
            (
                "recovery-without-event",
                recovery_control_plan(
                    ".modeling/recovery/session.json", "platform-recovery-without-event", []
                ),
                routing_project, "reserved_namespace:.modeling/recovery/session.json",
            ),
            (
                "dot-alias",
                platform_plan("paper/./main.tex", "platform-dot-alias"),
                project, "schema:steps/0/change_set/paths/0:pattern",
            ),
            (
                "empty-segment-alias",
                platform_plan("paper//main.tex", "platform-empty-segment-alias"),
                project, "schema:steps/0/change_set/paths/0:pattern",
            ),
            (
                "backslash-alias",
                platform_plan(r"paper\main.tex", "platform-backslash-alias"),
                project, "schema:steps/0/change_set/paths/0:pattern",
            ),
            (
                "unordered-alias-conflict",
                alias_conflict_plan,
                project, "schema:steps/1/change_set/paths/0:pattern",
            ),
            (
                "unordered-physical-alias",
                physical_alias_unordered_plan,
                project, "unordered_physical_alias_overlap:",
            ),
            (
                "same-step-physical-alias",
                physical_alias_same_step_plan,
                project, "same_step_physical_alias_overlap:",
            ),
            (
                "symlink-escape",
                platform_plan("escape-link/out.txt", "platform-symlink-escape"),
                project, "path_escapes_project_root:escape-link/out.txt",
            ),
        ]
        platform_negative = {
            label: (resolve(plan, case_root, root), expected)
            for label, plan, case_root, expected in platform_negative_specs
        }
        platform_positive_results = {
            **platform_positive,
            **platform_manual_positive,
            **platform_controller_positive,
        }
        admission_atoms = {
            "ART.ADMIT.CONSUMER",
            "ART.ADMIT.PROPOSAL_FIELDS",
            "ART.ADMIT.NO_SPECULATION",
        }
        ordinary_rule_leaks = {
            path: sorted(admission_atoms & set(platform_positive[path].get("rule_ids", [])))
            for path in (
                "paper/main.tex", "pyproject.toml", "tests/test_model.py",
                "<未收录-队友材料>/Graph3.png",
            )
            if admission_atoms & set(platform_positive[path].get("rule_ids", []))
        }
        platform_positive_failures = {
            path: resolution_errors(result)
            for path, result in platform_positive_results.items()
            if result.get("status") != "resolved"
        }
        platform_negative_failures = {
            path: resolution_errors(result)
            for path, (result, expected) in platform_negative.items()
            if (
                result.get("status") != "blocked"
                or expected not in resolution_errors(result)
            )
        }
        record(
            "SCENARIO.PLATFORM.PLAN_PREFLIGHT",
            not platform_positive_failures
            and not platform_negative_failures
            and not ordinary_rule_leaks,
            f"directory_alias_fixtures={escape_alias_kind},{internal_alias_kind};positive_failures="
            + json.dumps(platform_positive_failures, ensure_ascii=False, sort_keys=True)
            + ";ordinary_rule_leaks="
            + json.dumps(ordinary_rule_leaks, ensure_ascii=False, sort_keys=True)
            + ";negative_failures="
            + json.dumps(platform_negative_failures, ensure_ascii=False, sort_keys=True)
            + ";negative="
            + json.dumps(
                {
                    path: {
                        "status": result.get("status"),
                        "expected": expected,
                        "observed": expected in resolution_errors(result),
                    }
                    for path, (result, expected) in platform_negative.items()
                },
                ensure_ascii=False, sort_keys=True,
            ),
        )

        for identifier, level in (("EV-DATA-ID", "data_identity"), ("EV-PROV", "provenance")):
            path = workspace / f"{identifier}.json"
            write_json(path, evidence("INPUTS", identifier, level))
            run(
                manager, "record-evidence", "--project-root", str(project),
                "--component-id", "INPUTS", "--evidence", str(path),
            )

        transition_plan = {
            "schema_version": "11.0", "request": "证据满足后推进 INPUTS 到 D1", "window_context": "same_window",
            "steps": [{
                "id": "promote-inputs", "tier": "G2_CHECKPOINT", "mode": "promote",
                "object": "state", "action": "transition", "component_id": "INPUTS",
                "events": ["recovery_assessment", "state_transition"], "facts": {}, "depends_on": [],
                "change_set": {"paths": [".modeling/state.json"], "facets": ["shared_data_state"], "claim_refs": []},
                "state_effect": {"component_id": "INPUTS", "from": "D0", "to": "D1"},
            }],
        }
        transition_path = workspace / "transition-plan.json"
        write_json(transition_path, transition_plan)
        transition_result = resolve(transition_plan, project, root)
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        checkpoint_code, _, checkpoint_log = run(
            manager, "checkpoint", "--project-root", str(project),
            "--expected-revision", str(state["revision"]), "--gate", "G2",
            "--plan", str(transition_path), "--step-id", "promote-inputs",
        )
        start_code, _, start_log = run(
            manager, "record-route", "--project-root", str(project), "--plan", str(transition_path),
            "--step-id", "promote-inputs", "--execution-id", "EXEC-TRANSITION",
        )
        transition_code, _, transition_log = run(
            manager, "transition", "--project-root", str(project), "--component-id", "INPUTS",
            "--to", "D1", "--execution-id", "EXEC-TRANSITION",
        )
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        stored = {item["level"]: item for item in state["components"]["INPUTS"]["evidence"]}
        receipt = end_receipt(
            project, transition_plan, transition_result, "EXEC-TRANSITION",
            [validation("INPUTS", stored["data_identity"]), validation("INPUTS", stored["provenance"])], [],
        )
        receipt_path = workspace / "transition-receipt.json"
        write_json(receipt_path, receipt)
        close_code, _, close_log = run(
            manager, "close-execution", "--project-root", str(project), "--receipt", str(receipt_path),
        )
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        record(
            "SCENARIO.STATE.D0_D1_ROUNDTRIP",
            transition_result.get("status") == "resolved" and checkpoint_code == 0
            and start_code == 0 and transition_code == 0
            and close_code == 0 and state["components"]["INPUTS"]["state"] == "D1"
            and state["executions"]["EXEC-TRANSITION"]["status"] == "closed",
            f"resolve={transition_result.get('status')};checkpoint={checkpoint_code};start={start_code};transition={transition_code};close={close_code};log={checkpoint_log}{start_log}{transition_log}{close_log}",
        )

        data_file = project / "data/input.csv"
        data_file.parent.mkdir(parents=True)
        data_file.write_text("x\n1\n", encoding="utf-8")
        proposal = {
            "path": "data/input.csv", "platform_role": "official_input",
            "purpose": "Official disposable input for identity binding test.",
            "consumer_ids": ["INPUTS"], "lifecycle": "milestone", "identity_class": "frozen",
            "class": "data", "authorization_basis": "authorized scenario fixture", "replaces": None,
        }
        proposal_path = workspace / "proposal.json"
        write_json(proposal_path, proposal)
        seal_fixture_baseline(project, "identity-admission-fixture")

        def audit_plan(paths: list[str], identifier: str) -> dict[str, Any]:
            return {
                "schema_version": "11.0", "plan_id": identifier,
                "request": "登记并审计正式输入", "window_context": "same_window",
                "steps": [{
                    "id": "audit", "tier": "G2_CHECKPOINT", "mode": "mutate",
                    "object": "data", "action": "audit", "component_id": "INPUTS",
                    "events": ["recovery_assessment", "data_audit", "dataset_register"],
                    "facts": {"predictive_or_evaluative_use": False}, "depends_on": [],
                    "change_set": {"paths": paths, "facets": ["data_identity"], "claim_refs": []},
                }],
            }

        bad_plan = audit_plan(["planning/inputs.md"], "bad-identity-plan")
        bad_path = workspace / "bad-plan.json"
        write_json(bad_path, bad_plan)
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        bad_checkpoint, _, bad_checkpoint_log = run(
            manager, "checkpoint", "--project-root", str(project),
            "--expected-revision", str(state["revision"]), "--gate", "G2",
            "--plan", str(bad_path), "--step-id", "audit",
        )
        bad_start, _, _ = run(
            manager, "record-route", "--project-root", str(project), "--plan", str(bad_path),
            "--step-id", "audit", "--execution-id", "EXEC-BAD-IDENTITY",
        )
        bad_register, _, bad_log = run(
            manager, "register-artifact", "--project-root", str(project), "--proposal", str(proposal_path),
            "--producer", "INPUTS", "--execution-id", "EXEC-BAD-IDENTITY",
        )
        void_code, _, void_log = run(
            manager, "void-execution", "--project-root", str(project),
            "--execution-id", "EXEC-BAD-IDENTITY", "--failure-code", "CHANGE_SET_OMISSION",
            "--reason", "Formal identity path was omitted from the sealed ChangeSet.",
        )
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        record(
            "SCENARIO.IDENTITY.PREFLIGHT_AND_VOID",
            bad_checkpoint == 0 and bad_start == 0 and bad_register != 0 and "outside sealed ChangeSet" in bad_log
            and void_code == 0 and state["executions"]["EXEC-BAD-IDENTITY"]["status"] == "void",
            f"checkpoint={bad_checkpoint};register={bad_register};void={void_code};log={bad_checkpoint_log}{bad_log}{void_log}",
        )

        good_plan = audit_plan(["data/input.csv"], "good-identity-plan")
        good_path = workspace / "good-plan.json"
        write_json(good_path, good_plan)
        good_result = resolve(good_plan, project, root)
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        good_checkpoint, _, good_checkpoint_log = run(
            manager, "checkpoint", "--project-root", str(project),
            "--expected-revision", str(state["revision"]), "--gate", "G2",
            "--plan", str(good_path), "--step-id", "audit",
        )
        good_start, _, good_start_log = run(
            manager, "record-route", "--project-root", str(project), "--plan", str(good_path),
            "--step-id", "audit", "--execution-id", "EXEC-GOOD-IDENTITY",
        )
        good_register, _, good_register_log = run(
            manager, "register-artifact", "--project-root", str(project), "--proposal", str(proposal_path),
            "--producer", "INPUTS", "--execution-id", "EXEC-GOOD-IDENTITY",
        )
        good_close = 99
        good_close_log = "close_not_attempted"
        good_receipt_validate = 99
        forged_receipt_validate = 99
        replay_close = 99
        good_receipt_validate_log = "validate_not_attempted"
        forged_receipt_log = "forge_not_attempted"
        replay_close_log = "replay_not_attempted"
        if good_start == 0 and good_register == 0:
            identity = {"kind": "artifact", "id": "data/input.csv", "identity": sha256_file(data_file), "facet": "content"}
            receipt = end_receipt(
                project, good_plan, good_result, "EXEC-GOOD-IDENTITY",
                [validation("INPUTS", stored["data_identity"])], [identity],
            )
            good_receipt_path = workspace / "good-receipt.json"
            write_json(good_receipt_path, receipt)
            good_receipt_validate, _, good_receipt_validate_log = run(
                receipt_validator, "--receipt", str(good_receipt_path),
            )
            forged_receipt = deepcopy(receipt)
            forged_receipt["after_revision"] += 1
            forged_receipt["validations"][0]["binding_hash"] = "0" * 64
            forged_receipt["changed_identities"].append({
                "kind": "artifact", "id": "data/undeclared.csv",
                "identity": "0" * 64, "facet": "content",
            })
            forged_receipt_path = workspace / "forged-good-receipt.json"
            write_json(forged_receipt_path, forged_receipt)
            forged_receipt_validate, _, forged_receipt_log = run(
                receipt_validator, "--receipt", str(forged_receipt_path),
            )
            good_close, _, good_close_log = run(
                manager, "close-execution", "--project-root", str(project), "--receipt", str(good_receipt_path),
            )
            replay_close, _, replay_close_log = run(
                manager, "close-execution", "--project-root", str(project), "--receipt", str(good_receipt_path),
            )
        record(
            "SCENARIO.IDENTITY.DECLARED_ROUNDTRIP",
            good_result.get("status") == "resolved" and good_checkpoint == 0
            and good_start == 0 and good_register == 0 and good_close == 0,
            f"resolve={good_result.get('status')}:{good_result.get('steps', [{}])[0].get('reasons')}:blocking={good_result.get('steps', [{}])[0].get('blocking_rule_ids')};checkpoint={good_checkpoint};start={good_start};register={good_register};close={good_close};log={good_checkpoint_log}{good_start_log}{good_register_log}{good_close_log}",
        )
        record(
            "SCENARIO.RECEIPT.CLOSED_WORLD_AND_REPLAY",
            bad_register != 0 and "outside sealed ChangeSet" in bad_log
            and good_receipt_validate == 0
            and forged_receipt_validate != 0
            and "after_revision_mismatch" in forged_receipt_log
            and "validation_binding_hash_mismatch" in forged_receipt_log
            and "changed_identity_outside_change_set" in forged_receipt_log
            and good_close == 0 and replay_close != 0,
            f"preflight={bad_register}:{bad_log};valid={good_receipt_validate}:{good_receipt_validate_log}"
            + f";forged={forged_receipt_validate}:{forged_receipt_log}"
            + f";close={good_close};replay={replay_close}:{replay_close_log}",
        )

        # Real new-window chain: registered statement + frozen process must be
        # semantically reread and closed under one R1 receipt before D0 -> D1.
        r1_project = workspace / "r1-project"
        run(manager, "init", "--project-root", str(r1_project), "--project-id", "r1-demo")
        run(
            manager, "add-component", "--project-root", str(r1_project),
            "--component-id", "INPUTS", "--type", "shared_data",
        )
        problem_file = r1_project / "data/problem.txt"
        frozen_flow = r1_project / "planning/frozen_flow.md"
        problem_file.parent.mkdir(parents=True)
        frozen_flow.parent.mkdir(parents=True)
        problem_file.write_text("Official problem statement for targeted recovery.\n", encoding="utf-8")
        frozen_flow.write_text("Frozen and accepted INPUTS workflow.\n", encoding="utf-8")
        for identifier, level in (("R1-DATA-ID", "data_identity"), ("R1-PROV", "provenance")):
            evidence_path = workspace / f"{identifier}.json"
            write_json(evidence_path, evidence("INPUTS", identifier, level))
            run(
                manager, "record-evidence", "--project-root", str(r1_project),
                "--component-id", "INPUTS", "--evidence", str(evidence_path),
            )

        fixture_plan = {
            "schema_version": "11.0", "plan_id": "r1-fixture",
            "request": "登记恢复场景的正式题面和冻结流程", "window_context": "same_window",
            "steps": [{
                "id": "fixture", "tier": "G2_CHECKPOINT", "mode": "mutate",
                "object": "data", "action": "audit", "component_id": "INPUTS",
                "events": ["recovery_assessment", "data_audit", "dataset_register"],
                "facts": {
                    "predictive_or_evaluative_use": False,
                    "change_set_complete": True,
                    "propagation_complete": True,
                },
                "depends_on": [],
                "change_set": {
                    "paths": ["data/problem.txt", "planning/frozen_flow.md"],
                    "facets": ["data_identity"], "claim_refs": [],
                },
            }],
        }
        fixture_plan_path = workspace / "r1-fixture-plan.json"
        write_json(fixture_plan_path, fixture_plan)
        fixture_resolution = resolve(fixture_plan, r1_project, root)
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        fixture_checkpoint, _, _ = run(
            manager, "checkpoint", "--project-root", str(r1_project),
            "--expected-revision", str(r1_state["revision"]), "--gate", "G2",
            "--plan", str(fixture_plan_path), "--step-id", "fixture",
        )
        fixture_start, _, _ = run(
            manager, "record-route", "--project-root", str(r1_project),
            "--plan", str(fixture_plan_path), "--step-id", "fixture",
            "--execution-id", "EXEC-R1-FIXTURE",
        )
        proposals = [
            {
                "path": "data/problem.txt", "platform_role": "official_input",
                "purpose": "Official problem statement for recovery context.",
                "consumer_ids": ["INPUTS"], "lifecycle": "milestone",
                "identity_class": "frozen", "class": "source",
                "authorization_basis": "authorized recovery scenario fixture", "replaces": None,
            },
            {
                "path": "planning/frozen_flow.md", "platform_role": "planning",
                "purpose": "Frozen accepted workflow for INPUTS recovery.",
                "consumer_ids": ["INPUTS"], "lifecycle": "milestone",
                "identity_class": "frozen", "class": "control",
                "authorization_basis": "authorized recovery scenario fixture", "replaces": None,
            },
        ]
        fixture_register_codes: list[int] = []
        for index, proposal_item in enumerate(proposals):
            proposal_path = workspace / f"r1-proposal-{index}.json"
            write_json(proposal_path, proposal_item)
            code, _, _ = run(
                manager, "register-artifact", "--project-root", str(r1_project),
                "--proposal", str(proposal_path), "--producer", "INPUTS",
                "--execution-id", "EXEC-R1-FIXTURE",
            )
            fixture_register_codes.append(code)
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        fixture_stored = {item["level"]: item for item in r1_state["components"]["INPUTS"]["evidence"]}
        fixture_identities = [
            {"kind": "artifact", "id": path, "identity": r1_state["artifacts"][path]["sha256"], "facet": "content"}
            for path in ("data/problem.txt", "planning/frozen_flow.md")
        ]
        fixture_receipt = end_receipt(
            r1_project, fixture_plan, fixture_resolution, "EXEC-R1-FIXTURE",
            [validation("INPUTS", fixture_stored["data_identity"])], fixture_identities,
        )
        fixture_receipt_path = workspace / "r1-fixture-receipt.json"
        write_json(fixture_receipt_path, fixture_receipt)
        fixture_close, _, fixture_close_log = run(
            manager, "close-execution", "--project-root", str(r1_project),
            "--receipt", str(fixture_receipt_path),
        )

        r1_plan = {
            "schema_version": "11.0", "plan_id": "r1-transition",
            "request": "新窗口恢复后推进 INPUTS 到 D1", "window_context": "new_window",
            "steps": [{
                "id": "promote", "tier": "G2_CHECKPOINT", "mode": "promote",
                "object": "state", "action": "transition", "component_id": "INPUTS",
                "events": ["recovery_assessment", "state_transition"],
                "facts": {}, "depends_on": [],
                "change_set": {"paths": [".modeling/state.json"], "facets": ["shared_data_state"], "claim_refs": []},
                "state_effect": {"component_id": "INPUTS", "from": "D0", "to": "D1"},
            }],
        }
        r1_plan_path = workspace / "r1-transition-plan.json"
        write_json(r1_plan_path, r1_plan)
        r1_resolution = resolve(r1_plan, r1_project, root)
        r1_begin, r1_begin_payload, r1_begin_log = run(
            manager, "begin-recovery", "--project-root", str(r1_project),
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        recovery_record = r1_state["recoveries"]["REC-R1-NEW-WINDOW"]

        def recovery_read(requirement: dict[str, Any]) -> dict[str, Any]:
            live = r1_project / requirement["path"]
            required_mode = requirement["required_mode"]
            mode = {
                "content": "content", "semantic": "structured_extract",
                "identity": "identity_plus_validation_summary", "existence": "missing_review",
            }[required_mode]
            return {
                "path": requirement["path"],
                "semantic_role": requirement["semantic_role"],
                "read_mode": mode,
                "sha256": sha256_file(live) if live.is_file() else None,
                "size": live.stat().st_size if live.is_file() else None,
                "review_result": "consistent" if live.is_file() else "missing",
                "note": "Content and project meaning were reviewed against the current target.",
            }

        all_reads = [recovery_read(item) for item in recovery_record["required_reads"]]
        incomplete_receipt = {
            "schema_version": "14.0", "receipt_type": "r1_targeted_recovery",
            "recovery_id": "REC-R1-NEW-WINDOW", "project_root": str(r1_project.resolve()),
            "read_receipts": [
                item for item in all_reads if item["path"] != "planning/frozen_flow.md"
            ],
            "changed_paths": recovery_record["assessment"]["changed_paths"],
            "affected_components": recovery_record["assessment"]["affected_components"],
            "conclusion": {"status": "ready", "inconsistencies": [], "next_legal_action": "Run the bound G2 checkpoint."},
        }
        incomplete_path = workspace / "r1-incomplete-receipt.json"
        write_json(incomplete_path, incomplete_receipt)
        incomplete_close, _, incomplete_log = run(
            manager, "close-recovery", "--project-root", str(r1_project),
            "--receipt", str(incomplete_path),
        )
        preclose_checkpoint, _, preclose_log = run(
            manager, "checkpoint", "--project-root", str(r1_project),
            "--expected-revision", str(r1_state["revision"]), "--gate", "G2",
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        unbound_baseline, _, unbound_baseline_log = run(
            manager, "update-baseline", "--project-root", str(r1_project),
        )

        complete_receipt = dict(incomplete_receipt)
        complete_receipt["read_receipts"] = all_reads
        complete_path = workspace / "r1-complete-receipt.json"
        write_json(complete_path, complete_receipt)
        complete_close, _, complete_close_log = run(
            manager, "close-recovery", "--project-root", str(r1_project),
            "--receipt", str(complete_path),
        )
        reviewed_flow = frozen_flow.read_text(encoding="utf-8")
        frozen_flow.write_text(reviewed_flow + "unreviewed change\n", encoding="utf-8")
        postclose_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        changed_after_review_baseline, _, changed_after_review_log = run(
            manager, "update-baseline", "--project-root", str(r1_project),
            "--recovery-id", "REC-R1-NEW-WINDOW",
            "--expected-revision", str(postclose_state["revision"]),
        )
        frozen_flow.write_text(reviewed_flow, encoding="utf-8")
        no_checkpoint_start, _, no_checkpoint_log = run(
            manager, "record-route", "--project-root", str(r1_project),
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--execution-id", "EXEC-R1-NO-CHECKPOINT",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        r1_checkpoint, _, r1_checkpoint_log = run(
            manager, "checkpoint", "--project-root", str(r1_project),
            "--expected-revision", str(r1_state["revision"]), "--gate", "G2",
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        r1_start, _, r1_start_log = run(
            manager, "record-route", "--project-root", str(r1_project),
            "--plan", str(r1_plan_path), "--step-id", "promote",
            "--execution-id", "EXEC-R1-TRANSITION",
            "--recovery-id", "REC-R1-NEW-WINDOW",
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        r1_execution = r1_state["executions"].get("EXEC-R1-TRANSITION", {})
        r1_start_resolution = resolve(r1_plan, r1_project, root)
        r1_start_step = r1_start_resolution["steps"][0]
        r1_start_receipt = {
            "receipt_type": "start", "schema_version": "11.0",
            "request": r1_plan["request"], "request_hash": sha256_text(r1_plan["request"]),
            "semantic_plan": r1_plan, "plan_hash": sha256_text(canonical_json(r1_plan)),
            "step_id": "promote", "execution_id": "EXEC-R1-TRANSITION",
            "pair_hash": checkpoint_pair_hash(r1_execution),
            "project_root": str(r1_project.resolve()), "tier": "G2_CHECKPOINT",
            "mode": "promote", "route_ids": [r1_start_step["route_id"]],
            "rule_ids": r1_start_step["rule_ids"], "component_ids": r1_start_step["component_ids"],
            "state_revision": r1_execution.get("start_revision"), "recovery": "R1_TARGETED",
            "change_set": r1_start_step["change_set"],
            "required_identities": [
                {
                    "kind": "artifact", "id": path,
                    "identity": r1_state["artifacts"][path]["sha256"], "facet": "content",
                }
                for path in ("data/problem.txt", "planning/frozen_flow.md")
            ],
            "blocked": False,
        }
        r1_start_receipt_path = workspace / "r1-start-receipt.json"
        write_json(r1_start_receipt_path, r1_start_receipt)
        r1_start_receipt_code, _, r1_start_receipt_log = run(
            receipt_validator, "--receipt", str(r1_start_receipt_path),
        )
        tampered_start = dict(r1_start_receipt)
        tampered_start["recovery"] = "R0_CONTINUE"
        tampered_start_path = workspace / "r1-start-receipt-tampered.json"
        write_json(tampered_start_path, tampered_start)
        tampered_start_code, _, tampered_start_log = run(
            receipt_validator, "--receipt", str(tampered_start_path),
        )
        r1_transition, _, r1_transition_log = run(
            manager, "transition", "--project-root", str(r1_project),
            "--component-id", "INPUTS", "--to", "D1",
            "--execution-id", "EXEC-R1-TRANSITION",
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        r1_stored = {item["level"]: item for item in r1_state["components"]["INPUTS"]["evidence"]}
        r1_end = end_receipt(
            r1_project, r1_plan, r1_resolution, "EXEC-R1-TRANSITION",
            [
                validation("INPUTS", r1_stored["data_identity"]),
                validation("INPUTS", r1_stored["provenance"]),
            ], [],
        )
        r1_end_path = workspace / "r1-transition-receipt.json"
        write_json(r1_end_path, r1_end)
        r1_close, _, r1_close_log = run(
            manager, "close-execution", "--project-root", str(r1_project),
            "--receipt", str(r1_end_path),
        )
        r1_state = json.loads((r1_project / ".modeling/state.json").read_text(encoding="utf-8"))
        required_roles = {
            item["semantic_role"] for item in recovery_record["required_reads"]
        }
        record(
            "SCENARIO.RECOVERY.R1_NEW_WINDOW_ROUNDTRIP",
            fixture_checkpoint == 0 and fixture_start == 0
            and fixture_register_codes == [0, 0] and fixture_close == 0
            and r1_resolution.get("status") == "resolved"
            and r1_resolution["steps"][0]["recovery"]["level"] == "R1_TARGETED"
            and {
                "REC.R1.READ_SCOPE", "REC.R1.REVIEW_CLOSURE", "REC.R1.TRANSITIVE",
            }.issubset(set(r1_resolution["steps"][0]["rule_ids"]))
            and r1_begin == 0 and incomplete_close != 0 and preclose_checkpoint != 0
            and unbound_baseline != 0 and complete_close == 0
            and changed_after_review_baseline != 0
            and no_checkpoint_start != 0 and r1_checkpoint == 0 and r1_start == 0
            and r1_start_receipt_code == 0 and tampered_start_code != 0
            and r1_transition == 0 and r1_close == 0
            and {"authoritative_state", "official_input", "frozen_process"}.issubset(required_roles)
            and r1_state["executions"]["EXEC-R1-TRANSITION"]["recovery"] == "R1_TARGETED"
            and r1_state["recoveries"]["REC-R1-NEW-WINDOW"]["consumed_by_execution"] == "EXEC-R1-TRANSITION"
            and set(r1_state.get("workspace_baseline", {})) == {
                "data/problem.txt", "planning/frozen_flow.md"
            }
            and r1_state["components"]["INPUTS"]["state"] == "D1",
            "fixture=" + str((fixture_checkpoint, fixture_start, fixture_register_codes, fixture_close))
            + ";r1=" + str((r1_begin, incomplete_close, preclose_checkpoint, unbound_baseline, complete_close, changed_after_review_baseline, no_checkpoint_start, r1_checkpoint, r1_start, r1_start_receipt_code, tampered_start_code, r1_transition, r1_close))
            + ";roles=" + str(sorted(required_roles))
            + ";log=" + (fixture_close_log + r1_begin_log + incomplete_log + preclose_log + unbound_baseline_log + complete_close_log + changed_after_review_log + no_checkpoint_log + r1_checkpoint_log + r1_start_log + r1_start_receipt_log + tampered_start_log + r1_transition_log + r1_close_log)[-1200:],
        )

        # R2 is an execution barrier, not a narrative warning.  Start from a
        # fresh current state, make only its control schema incompatible, and
        # prove that neither the guarded command nor an out-of-scope recovery
        # write can run.  Replacing the control state with the saved current
        # shape must not bypass the now-required full-read R2 receipt.
        r2_project = workspace / "r2-project"
        run(manager, "init", "--project-root", str(r2_project), "--project-id", "r2-demo")
        run(
            manager, "add-component", "--project-root", str(r2_project),
            "--component-id", "q1", "--type", "question",
        )
        repaired_state = read_state(r2_project)
        repaired_state["components"]["q1"]["state"] = "S4"
        incompatible_state = deepcopy(repaired_state)
        incompatible_state["schema_version"] = "9.0"
        write_json(r2_project / ".modeling/state.json", incompatible_state)
        r2_marker = "output/q1/r2-executed.txt"
        r2_marker_path = r2_project / r2_marker
        r2_marker_path.parent.mkdir(parents=True)
        r2_marker_path.write_text("not-ran", encoding="utf-8")
        (r2_project / "paper.tex").write_text("existing project content\n", encoding="utf-8")
        r2_request = "修复控制状态；修复完成后运行第一问模型。"
        r2_plan = {
            "schema_version": "11.0", "plan_id": "v15-r2-roundtrip",
            "request": r2_request, "window_context": "new_window",
            "steps": [
                {
                    "id": "recover", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "project", "action": "recover", "component_id": None,
                    "events": ["recovery_assessment"], "facts": {},
                    "working_context": {"component_type": "project", "state": "P0"},
                    "depends_on": [],
                    "change_set": {
                        "paths": [".modeling/state.json"],
                        "facets": ["identity_inventory", "known_gaps"], "claim_refs": [],
                    },
                },
                {
                    "id": "solve", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "model", "action": "solve", "component_id": "q1",
                    "events": ["model_execution"], "facts": {},
                    "working_context": {"component_type": "question", "state": "S4"},
                    "depends_on": ["recover"],
                    "change_set": {
                        "paths": [r2_marker], "facets": ["computation"], "claim_refs": [],
                    },
                    "runtime_actions": [{
                        "id": "run-q1", "kind": "project_model_execution",
                        "event": "model_execution", "repetition": "first_run",
                        "scope": {
                            "kind": "component", "component_ids": ["q1"],
                            "input_paths": [], "output_paths": [r2_marker],
                        },
                        "command": {
                            "argv": [
                                sys.executable, "-c",
                                "from pathlib import Path; p=Path('output/q1/r2-executed.txt'); p.parent.mkdir(parents=True, exist_ok=True); p.write_text('ran', encoding='utf-8')",
                            ],
                            "cwd": ".",
                        },
                        "authorization": {
                            "source": "direct_user_request",
                            "request_excerpt": "运行第一问模型",
                        },
                    }],
                },
            ],
        }
        r2_plan_path = workspace / "r2-plan.json"
        write_json(r2_plan_path, r2_plan)
        r2_open = resolve(r2_plan, r2_project, root)
        r2_execute_blocked, _, r2_execute_blocked_log = run(
            root / "scripts/run_authorized_action.py",
            "--plan", str(r2_plan_path), "--project-root", str(r2_project),
            "--step-id", "solve", "--action-id", "run-q1", "--root", str(root),
        )
        blocked_marker_content = r2_marker_path.read_text(encoding="utf-8")
        forbidden_recovery = deepcopy(r2_plan)
        forbidden_recovery["steps"] = [deepcopy(r2_plan["steps"][0])]
        forbidden_recovery["steps"][0]["change_set"]["paths"] = ["paper.tex"]
        forbidden_result = resolve(forbidden_recovery, r2_project, root)
        write_json(r2_project / ".modeling/state.json", repaired_state)
        r2_repaired = resolve(r2_plan, r2_project, root)
        r2_execute_ok, _, r2_execute_ok_log = run(
            root / "scripts/run_authorized_action.py",
            "--plan", str(r2_plan_path), "--project-root", str(r2_project),
            "--step-id", "solve", "--action-id", "run-q1", "--root", str(root),
        )
        r2_open_steps = {item["id"]: item for item in r2_open.get("steps", [])}
        forbidden_text = resolution_errors(forbidden_result)
        record(
            "SCENARIO.RECOVERY.R2_BARRIER_ROUNDTRIP",
            r2_open.get("recovery_posture") == "R2_OPEN"
            and r2_open_steps.get("recover", {}).get("status") == "resolved"
            and r2_open_steps.get("solve", {}).get("status") == "blocked"
            and "r2_recovery_open" in resolution_errors(r2_open)
            and r2_open.get("action_grants") == []
            and r2_execute_blocked != 0 and blocked_marker_content == "not-ran"
            and forbidden_result.get("status") == "blocked"
            and "r2_recovery_write_outside_control_scope:paper.tex" in forbidden_text
            and r2_repaired.get("recovery_posture") == "R2_OPEN"
            and [item.get("status") for item in r2_repaired.get("steps", [])]
            == ["resolved", "blocked"]
            and r2_repaired.get("action_grants") == []
            and r2_execute_ok != 0
            and r2_marker_path.read_text(encoding="utf-8") == "not-ran",
            "open=" + resolution_errors(r2_open)
            + f";blocked_exec={r2_execute_blocked};forbidden={forbidden_text}"
            + ";state_shape_only_without_receipt=" + resolution_errors(r2_repaired)
            + f";ok_exec={r2_execute_ok};log={(r2_execute_blocked_log + r2_execute_ok_log)[-700:]}",
        )

        def setup_identity_project(name: str) -> tuple[Path, dict[str, Any]]:
            project_root = workspace / name
            run(manager, "init", "--project-root", str(project_root), "--project-id", name)
            run(
                manager, "add-component", "--project-root", str(project_root),
                "--component-id", "INPUTS", "--type", "shared_data",
            )
            run(
                manager, "add-component", "--project-root", str(project_root),
                "--component-id", "model", "--type", "question", "--dependency", "INPUTS",
            )
            run(
                manager, "add-component", "--project-root", str(project_root),
                "--component-id", "paper", "--type", "artifact", "--dependency", "model",
            )
            run(
                manager, "add-component", "--project-root", str(project_root),
                "--component-id", "appendix", "--type", "artifact", "--dependency", "paper",
            )
            run(
                manager, "add-component", "--project-root", str(project_root),
                "--component-id", "unrelated", "--type", "question", "--optional",
            )
            data_record = evidence("INPUTS", f"EV-{name}-DATA-ID", "data_identity")
            data_record_path = workspace / f"{name}-data-identity.json"
            write_json(data_record_path, data_record)
            run(
                manager, "record-evidence", "--project-root", str(project_root),
                "--component-id", "INPUTS", "--evidence", str(data_record_path),
            )
            stored_state = read_state(project_root)
            stored_record = next(
                item for item in stored_state["components"]["INPUTS"]["evidence"]
                if item["id"] == data_record["id"]
            )
            return project_root, stored_record

        def register_scenario_artifact(
            project_root: Path,
            input_record: dict[str, Any],
            relative: str,
            identity_class: str,
            execution_id: str,
        ) -> tuple[str, list[tuple[str, int, str]], dict[str, Any], dict[str, Any]]:
            target = project_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("identity version one\n", encoding="utf-8")
            lifecycle = "working" if identity_class == "working" else "milestone"
            proposal = {
                "path": relative, "platform_role": "result",
                "purpose": "Disposable exact-identity propagation result.",
                "consumer_ids": ["paper"], "lifecycle": lifecycle,
                "identity_class": identity_class, "class": "result",
                "authorization_basis": "authorized V15 disposable scenario", "replaces": None,
            }
            proposal_path = workspace / f"{execution_id}-proposal.json"
            write_json(proposal_path, proposal)
            plan = identity_plan("INPUTS", [relative], f"{execution_id}-plan")
            resolution, _, stages = begin_formal(
                manager, root, project_root, workspace, plan, execution_id,
            )
            register_code, _, register_log = run(
                manager, "register-artifact", "--project-root", str(project_root),
                "--proposal", str(proposal_path), "--producer", "model",
                "--execution-id", execution_id,
            )
            stages.append(("register", register_code, register_log))
            registered = read_state(project_root)
            identity = registered.get("artifacts", {}).get(relative, {}).get("sha256", "")
            close_code, close_log, _ = close_formal(
                manager, project_root, workspace, plan, resolution, execution_id,
                [validation("INPUTS", input_record)],
                [{"kind": "artifact", "id": relative, "identity": identity, "facet": "content"}],
            )
            stages.append(("close", close_code, close_log))
            return identity, stages, plan, resolution

        working_project, working_input_record = setup_identity_project("working-identity")
        working_path = "output/q1/working.txt"
        working_old, working_register_stages, _, _ = register_scenario_artifact(
            working_project, working_input_record, working_path, "working", "EXEC-WORK-REGISTER",
        )
        working_ref = [{
            "kind": "artifact", "id": working_path,
            "identity": working_old, "facet": "result",
        }]
        working_bound_path = workspace / "working-bound-evidence.json"
        write_json(
            working_bound_path,
            file_evidence(
                working_project, "model", "EV-WORKING-OLD", "result_claims",
                working_path, input_refs=working_ref,
            ),
        )
        run(
            manager, "record-evidence", "--project-root", str(working_project),
            "--component-id", "model", "--evidence", str(working_bound_path),
        )
        unrelated_evidence_file = working_project / ".modeling/evidence-files/unrelated.txt"
        unrelated_evidence_file.parent.mkdir(parents=True, exist_ok=True)
        unrelated_evidence_file.write_text("independent evidence\n", encoding="utf-8")
        unrelated_record_path = workspace / "working-unrelated-evidence.json"
        write_json(
            unrelated_record_path,
            file_evidence(
                working_project, "paper", "EV-WORKING-UNREFERENCED", "artifact_draft",
                ".modeling/evidence-files/unrelated.txt",
            ),
        )
        run(
            manager, "record-evidence", "--project-root", str(working_project),
            "--component-id", "paper", "--evidence", str(unrelated_record_path),
        )
        working_refresh_plan = identity_plan("INPUTS", [working_path], "working-refresh")
        working_refresh_resolution, _, working_refresh_stages = begin_formal(
            manager, root, working_project, workspace, working_refresh_plan, "EXEC-WORK-REFRESH",
        )
        wrong_working_refresh, _, wrong_working_log = run(
            manager, "refresh-artifact", "--project-root", str(working_project),
            "--path", working_path, "--expected-old-sha256", "f" * 64,
            "--execution-id", "EXEC-WORK-REFRESH",
        )
        (working_project / working_path).write_text("identity version two\n", encoding="utf-8")
        working_refresh_code, _, working_refresh_log = run(
            manager, "refresh-artifact", "--project-root", str(working_project),
            "--path", working_path, "--expected-old-sha256", working_old,
            "--execution-id", "EXEC-WORK-REFRESH",
        )
        working_refreshed_state = read_state(working_project)
        working_new = working_refreshed_state["artifacts"][working_path]["sha256"]
        working_close_code, working_close_log, _ = close_formal(
            manager, working_project, workspace, working_refresh_plan,
            working_refresh_resolution, "EXEC-WORK-REFRESH",
            [validation("INPUTS", working_input_record)],
            [{"kind": "artifact", "id": working_path, "identity": working_new, "facet": "content"}],
        )
        working_refresh_event = next(
            item for item in reversed(working_refreshed_state["history"])
            if item["event"] == "artifact_refreshed"
        )
        working_evidence_status = {
            item["id"]: item["status"]
            for component in working_refreshed_state["components"].values()
            for item in component["evidence"]
        }
        working_component_status = {
            key: value["status"] for key, value in working_refreshed_state["components"].items()
        }
        record(
            "SCENARIO.IDENTITY.WORKING_REFRESH_EXACT",
            all(code == 0 for _, code, _ in working_register_stages)
            and all(code == 0 for _, code, _ in working_refresh_stages)
            and wrong_working_refresh != 0 and "expected old hash" in wrong_working_log
            and working_refresh_code == 0 and working_close_code == 0
            and working_old != working_new
            and working_evidence_status.get("EV-WORKING-OLD") == "stale"
            and working_evidence_status.get("EV-WORKING-UNREFERENCED") == "pass"
            and set(working_component_status.values()) == {"active"}
            and working_refresh_event["details"]["stale_evidence_ids"] == ["EV-WORKING-OLD"]
            and working_refresh_event["details"]["affected_components"] == [],
            f"register={[(name, code) for name, code, _ in working_register_stages]}"
            + f";wrong={wrong_working_refresh};refresh={working_refresh_code};close={working_close_code}"
            + f";old={working_old};new={working_new};evidence={working_evidence_status}"
            + f";components={working_component_status};details={working_refresh_event['details']}"
            + f";log={(working_refresh_log + working_close_log)[-500:]}",
        )

        protected_project, protected_input_record = setup_identity_project("protected-identity")
        protected_path = "output/q1/milestone.txt"
        protected_old, protected_register_stages, _, _ = register_scenario_artifact(
            protected_project, protected_input_record, protected_path,
            "milestone", "EXEC-PROTECTED-REGISTER",
        )
        protected_refresh_plan = identity_plan("INPUTS", [protected_path], "protected-refresh")
        protected_refresh_resolution, _, protected_refresh_stages = begin_formal(
            manager, root, protected_project, workspace,
            protected_refresh_plan, "EXEC-PROTECTED-REFRESH",
        )
        (protected_project / protected_path).write_text("protected identity version two\n", encoding="utf-8")
        protected_refresh_code, _, protected_refresh_log = run(
            manager, "refresh-artifact", "--project-root", str(protected_project),
            "--path", protected_path, "--expected-old-sha256", protected_old,
            "--execution-id", "EXEC-PROTECTED-REFRESH",
        )
        protected_refreshed_state = read_state(protected_project)
        protected_new = protected_refreshed_state["artifacts"][protected_path]["sha256"]
        protected_close_code, protected_close_log, _ = close_formal(
            manager, protected_project, workspace, protected_refresh_plan,
            protected_refresh_resolution, "EXEC-PROTECTED-REFRESH",
            [validation("INPUTS", protected_input_record)],
            [{"kind": "artifact", "id": protected_path, "identity": protected_new, "facet": "content"}],
        )
        protected_refresh_event = next(
            item for item in reversed(protected_refreshed_state["history"])
            if item["event"] == "artifact_refreshed"
        )
        protected_statuses = {
            key: value["status"] for key, value in protected_refreshed_state["components"].items()
        }
        record(
            "SCENARIO.IDENTITY.PROTECTED_DOWNSTREAM_EXACT",
            all(code == 0 for _, code, _ in protected_register_stages)
            and all(code == 0 for _, code, _ in protected_refresh_stages)
            and protected_refresh_code == 0 and protected_close_code == 0
            and protected_old != protected_new
            and protected_statuses == {
                "INPUTS": "active", "model": "invalidated", "paper": "invalidated",
                "appendix": "invalidated", "unrelated": "active",
            }
            and protected_refresh_event["details"]["affected_components"] == [
                "appendix", "model", "paper",
            ],
            f"register={[(name, code) for name, code, _ in protected_register_stages]}"
            + f";refresh_stages={[(name, code) for name, code, _ in protected_refresh_stages]}"
            + f";refresh={protected_refresh_code};close={protected_close_code}"
            + f";statuses={protected_statuses};details={protected_refresh_event['details']}"
            + f";log={(protected_refresh_log + protected_close_log)[-500:]}",
        )

        delta_project, delta_input_record = setup_identity_project("delta-revalidation")
        delta_path = "output/q1/revalidation-milestone.txt"
        delta_old, delta_register_stages, _, _ = register_scenario_artifact(
            delta_project, delta_input_record, delta_path,
            "milestone", "EXEC-DELTA-REGISTER",
        )
        baseline_file = delta_project / ".modeling/evidence-files/model-baseline.txt"
        baseline_file.parent.mkdir(parents=True, exist_ok=True)
        baseline_file.write_text("stable independent model evidence\n", encoding="utf-8")
        for level in (
            "scope", "problem_definition", "evidence_plan", "candidate_set",
            "model_spec", "selection_rationale",
        ):
            record_path = workspace / f"delta-{level}.json"
            write_json(record_path, evidence("model", f"EV-DELTA-{level}", level))
            run(
                manager, "record-evidence", "--project-root", str(delta_project),
                "--component-id", "model", "--evidence", str(record_path),
            )
        for level in ("implementation_ref", "E1_IMPLEMENTATION"):
            record_path = workspace / f"delta-{level}.json"
            write_json(
                record_path,
                file_evidence(
                    delta_project, "model", f"EV-DELTA-{level}", level,
                    ".modeling/evidence-files/model-baseline.txt",
                ),
            )
            run(
                manager, "record-evidence", "--project-root", str(delta_project),
                "--component-id", "model", "--evidence", str(record_path),
            )
        delta_old_ref = [{
            "kind": "artifact", "id": delta_path,
            "identity": delta_old, "facet": "result",
        }]
        delta_e2_path = workspace / "delta-E2.json"
        write_json(
            delta_e2_path,
            file_evidence(
                delta_project, "model", "EV-DELTA-E2", "E2_NUMERICAL",
                delta_path, input_refs=delta_old_ref,
            ),
        )
        run(
            manager, "record-evidence", "--project-root", str(delta_project),
            "--component-id", "model", "--evidence", str(delta_e2_path),
        )
        delta_before = read_state(delta_project)
        delta_before["components"]["model"]["state"] = "S6"
        write_json(delta_project / ".modeling/state.json", delta_before)
        untouched_before = {
            item["id"]: (item["status"], item["recorded_revision"], item["binding_hash"])
            for item in delta_before["components"]["model"]["evidence"]
            if item["id"] != "EV-DELTA-E2"
        }
        delta_refresh_plan = identity_plan("INPUTS", [delta_path], "delta-refresh")
        delta_refresh_resolution, _, delta_refresh_stages = begin_formal(
            manager, root, delta_project, workspace,
            delta_refresh_plan, "EXEC-DELTA-REFRESH",
        )
        (delta_project / delta_path).write_text("delta identity version two\n", encoding="utf-8")
        delta_refresh_code, _, delta_refresh_log = run(
            manager, "refresh-artifact", "--project-root", str(delta_project),
            "--path", delta_path, "--expected-old-sha256", delta_old,
            "--execution-id", "EXEC-DELTA-REFRESH",
        )
        delta_refreshed = read_state(delta_project)
        delta_new = delta_refreshed["artifacts"][delta_path]["sha256"]
        delta_close_code, delta_close_log, _ = close_formal(
            manager, delta_project, workspace, delta_refresh_plan,
            delta_refresh_resolution, "EXEC-DELTA-REFRESH",
            [validation("INPUTS", delta_input_record)],
            [{"kind": "artifact", "id": delta_path, "identity": delta_new, "facet": "content"}],
        )
        delta_revalidate_blocked, _, delta_revalidate_blocked_log = run(
            manager, "revalidate-component", "--project-root", str(delta_project),
            "--component-id", "model",
        )
        delta_new_ref = [{
            "kind": "artifact", "id": delta_path,
            "identity": delta_new, "facet": "result",
        }]
        write_json(
            delta_e2_path,
            file_evidence(
                delta_project, "model", "EV-DELTA-E2", "E2_NUMERICAL",
                delta_path, input_refs=delta_new_ref,
            ),
        )
        delta_record_new_code, _, delta_record_new_log = run(
            manager, "record-evidence", "--project-root", str(delta_project),
            "--component-id", "model", "--evidence", str(delta_e2_path), "--replace",
        )
        delta_revalidate_code, _, delta_revalidate_log = run(
            manager, "revalidate-component", "--project-root", str(delta_project),
            "--component-id", "model",
        )
        delta_after = read_state(delta_project)
        untouched_after = {
            item["id"]: (item["status"], item["recorded_revision"], item["binding_hash"])
            for item in delta_after["components"]["model"]["evidence"]
            if item["id"] != "EV-DELTA-E2"
        }
        delta_latest_e2 = next(
            item for item in delta_after["components"]["model"]["evidence"]
            if item["id"] == "EV-DELTA-E2"
        )
        record(
            "SCENARIO.STATE.DELTA_REVALIDATION",
            all(code == 0 for _, code, _ in delta_register_stages)
            and all(code == 0 for _, code, _ in delta_refresh_stages)
            and delta_refresh_code == 0 and delta_close_code == 0
            and delta_refreshed["components"]["model"]["status"] == "invalidated"
            and delta_revalidate_blocked != 0
            and "E2_NUMERICAL" in delta_revalidate_blocked_log
            and "E1_IMPLEMENTATION" not in delta_revalidate_blocked_log
            and "scope" not in delta_revalidate_blocked_log
            and delta_record_new_code == 0 and delta_revalidate_code == 0
            and delta_after["components"]["model"]["status"] == "active"
            and untouched_after == untouched_before
            and delta_latest_e2["status"] == "pass"
            and delta_latest_e2["input_refs"] == delta_new_ref,
            f"register={[(name, code) for name, code, _ in delta_register_stages]}"
            + f";refresh={delta_refresh_code};close={delta_close_code}"
            + f";blocked={delta_revalidate_blocked}:{delta_revalidate_blocked_log}"
            + f";record_new={delta_record_new_code};revalidate={delta_revalidate_code}"
            + f";untouched_equal={untouched_after == untouched_before};latest={delta_latest_e2}"
            + f";log={(delta_refresh_log + delta_close_log + delta_record_new_log + delta_revalidate_log)[-600:]}",
        )

        na_project, na_input_record = setup_identity_project("s6-na")
        spec_path = "planning/q1_model_spec.md"
        spec_file = na_project / spec_path
        spec_file.parent.mkdir(parents=True, exist_ok=True)
        spec_file.write_text("Frozen specification for honest applicability review.\n", encoding="utf-8")
        spec_proposal = {
            "path": spec_path, "platform_role": "planning",
            "purpose": "Frozen model specification for S6 applicability decisions.",
            "consumer_ids": ["model"], "lifecycle": "milestone",
            "identity_class": "frozen", "class": "control",
            "authorization_basis": "authorized V15 disposable scenario", "replaces": None,
        }
        spec_proposal_path = workspace / "s6-na-spec-proposal.json"
        write_json(spec_proposal_path, spec_proposal)
        spec_plan = identity_plan("INPUTS", [spec_path], "s6-na-spec-register")
        spec_resolution, _, spec_stages = begin_formal(
            manager, root, na_project, workspace, spec_plan, "EXEC-NA-SPEC",
        )
        spec_register_code, _, spec_register_log = run(
            manager, "register-artifact", "--project-root", str(na_project),
            "--proposal", str(spec_proposal_path), "--producer", "model",
            "--execution-id", "EXEC-NA-SPEC",
        )
        spec_state = read_state(na_project)
        spec_identity = spec_state.get("artifacts", {}).get(spec_path, {}).get("sha256", "")
        spec_close_code, spec_close_log, _ = close_formal(
            manager, na_project, workspace, spec_plan, spec_resolution, "EXEC-NA-SPEC",
            [validation("INPUTS", na_input_record)],
            [{"kind": "artifact", "id": spec_path, "identity": spec_identity, "facet": "content"}],
        )
        spec_stages.extend([
            ("register", spec_register_code, spec_register_log),
            ("close", spec_close_code, spec_close_log),
        ])
        for level in ("E2_NUMERICAL", "E4_REALITY"):
            decision_id = f"DEC-NA-{level}"
            run(
                manager, "add-open-decision", "--project-root", str(na_project),
                "--decision-id", decision_id, "--subject", f"Applicability of {level}",
                "--option", "applicable", "--option", "not_applicable", "--affects", "model",
            )
            run(
                manager, "resolve-open-decision", "--project-root", str(na_project),
                "--decision-id", decision_id, "--selected", "not_applicable",
            )
        na_axis_file = na_project / ".modeling/evidence-files/s6-axis.txt"
        na_axis_file.parent.mkdir(parents=True, exist_ok=True)
        na_axis_file.write_text("independent implementation and structural observations\n", encoding="utf-8")
        axis_records: dict[str, dict[str, Any]] = {}
        for level in ("E1_IMPLEMENTATION", "E3_STRUCTURAL"):
            identifier = f"EV-NA-{level}"
            record_payload = file_evidence(
                na_project, "model", identifier, level,
                ".modeling/evidence-files/s6-axis.txt",
            )
            path = workspace / f"{identifier}.json"
            write_json(path, record_payload)
            run(
                manager, "record-evidence", "--project-root", str(na_project),
                "--component-id", "model", "--evidence", str(path),
            )
            axis_records[level] = record_payload
        for level in ("E2_NUMERICAL", "E4_REALITY"):
            identifier = f"EV-NA-{level}"
            record_payload = not_applicable_evidence(
                "model", identifier, level, f"DEC-NA-{level}", spec_path, spec_identity,
            )
            path = workspace / f"{identifier}.json"
            write_json(path, record_payload)
            record_code, _, record_log = run(
                manager, "record-evidence", "--project-root", str(na_project),
                "--component-id", "model", "--evidence", str(path),
            )
            spec_stages.append((f"record-{level}", record_code, record_log))
        na_gate_state = read_state(na_project)
        na_gate_state["components"]["model"]["state"] = "S6"
        write_json(na_project / ".modeling/state.json", na_gate_state)
        na_plan = {
            "schema_version": "11.0", "plan_id": "s6-honest-na-close",
            "request": "在诚实适用性决定下关闭模型的 S6。", "window_context": "same_window",
            "steps": [{
                "id": "close", "tier": "G2_CHECKPOINT", "mode": "promote",
                "object": "verification", "action": "close_s6", "component_id": "model",
                "events": ["recovery_assessment", "s6_close"], "facts": {}, "depends_on": [],
                "change_set": {
                    "paths": [".modeling/state.json"],
                    "facets": ["question_state"], "claim_refs": [],
                },
                "state_effect": {"component_id": "model", "from": "S6", "to": "S7"},
            }],
        }
        na_positive = resolve(na_plan, na_project, root)
        na_positive_levels = current_evidence_levels(na_gate_state, "model")

        def resolve_na_variant(state_value: dict[str, Any]) -> dict[str, Any]:
            write_json(na_project / ".modeling/state.json", state_value)
            return resolve(na_plan, na_project, root)

        bare_na = deepcopy(na_gate_state)
        next(
            item for item in bare_na["components"]["model"]["evidence"]
            if item["level"] == "E4_REALITY"
        ).pop("applicability")
        bare_levels = current_evidence_levels(bare_na, "model")
        bare_result = resolve_na_variant(bare_na)
        e3_na = deepcopy(na_gate_state)
        e3_index = next(
            index for index, item in enumerate(e3_na["components"]["model"]["evidence"])
            if item["level"] == "E3_STRUCTURAL"
        )
        e3_record = not_applicable_evidence(
            "model", "EV-NA-E3_STRUCTURAL", "E3_STRUCTURAL",
            "DEC-NA-E2_NUMERICAL", spec_path, spec_identity,
        )
        e3_record["recorded_revision"] = e3_na["components"]["model"]["evidence"][e3_index]["recorded_revision"]
        e3_na["components"]["model"]["evidence"][e3_index] = e3_record
        e3_levels = current_evidence_levels(e3_na, "model")
        e3_result = resolve_na_variant(e3_na)
        unresolved_na = deepcopy(na_gate_state)
        next(
            item for item in unresolved_na["open_decisions"]
            if item["id"] == "DEC-NA-E4_REALITY"
        )["status"] = "open"
        unresolved_levels = current_evidence_levels(unresolved_na, "model")
        unresolved_result = resolve_na_variant(unresolved_na)
        stale_na = deepcopy(na_gate_state)
        stale_na["artifacts"][spec_path]["sha256"] = "f" * 64
        stale_levels = current_evidence_levels(stale_na, "model")
        stale_result = resolve_na_variant(stale_na)
        failed_na = deepcopy(na_gate_state)
        failed_e2 = next(
            item for item in failed_na["components"]["model"]["evidence"]
            if item["level"] == "E2_NUMERICAL"
        )
        failed_e2["status"] = "fail"
        failed_e2.pop("applicability")
        failed_levels = current_evidence_levels(failed_na, "model")
        failed_result = resolve_na_variant(failed_na)
        write_json(na_project / ".modeling/state.json", na_gate_state)
        na_rules = set(na_positive.get("rule_ids", []))
        negative_results = {
            "bare": bare_result, "e3_axis": e3_result,
            "unresolved": unresolved_result, "stale_spec": stale_result,
            "latest_fail": failed_result,
        }
        record(
            "SCENARIO.STATE.S6_JUSTIFIED_NA",
            all(code == 0 for _, code, _ in spec_stages)
            and na_positive.get("status") == "resolved"
            and "VER.S6.DUAL_AXIS" in na_rules
            and na_positive_levels == {
                "E1_IMPLEMENTATION", "E2_NUMERICAL", "E3_STRUCTURAL", "E4_REALITY",
            }
            and all(result.get("status") == "blocked" for result in negative_results.values())
            and "E4_REALITY" not in bare_levels
            and "E3_STRUCTURAL" not in e3_levels
            and "E4_REALITY" not in unresolved_levels
            and not ({"E2_NUMERICAL", "E4_REALITY"} & stale_levels)
            and "E2_NUMERICAL" not in failed_levels,
            f"setup={[(name, code) for name, code, _ in spec_stages]}"
            + f";positive={resolution_errors(na_positive)};levels={sorted(na_positive_levels)}"
            + ";negative=" + json.dumps(
                {key: resolution_errors(value) for key, value in negative_results.items()},
                ensure_ascii=False, sort_keys=True,
            )
            + ";negative_levels=" + json.dumps({
                "bare": sorted(bare_levels), "e3_axis": sorted(e3_levels),
                "unresolved": sorted(unresolved_levels), "stale_spec": sorted(stale_levels),
                "latest_fail": sorted(failed_levels),
            }, sort_keys=True),
        )

        # Retained tier semantics: G0 can resolve without requiring project
        # state, G1 may
        # describe one coherent multi-file mutation without manufacturing a
        # formal execution ledger, failures remain branch-local, unknown
        # events fail closed, and G2 cannot substitute declared context for
        # authoritative state.
        g0_plan = {
            "schema_version": "11.0", "plan_id": "v15-g0-stateless",
            "request": "先解释下一步怎么安排。",
            "steps": [{
                "id": "advise", "tier": "G0_ADVISORY", "mode": "advisory_readonly",
                "object": "project", "action": "advise", "component_id": None,
                "events": [], "facts": {}, "depends_on": [],
            }],
        }
        g0_result = resolve(g0_plan, routing_project, root)
        tier_project = workspace / "tier-boundaries"
        run(manager, "init", "--project-root", str(tier_project), "--project-id", "tier-demo")
        run(
            manager, "add-component", "--project-root", str(tier_project),
            "--component-id", "paper", "--type", "artifact",
        )
        run(
            manager, "add-component", "--project-root", str(tier_project),
            "--component-id", "q1", "--type", "question",
        )
        tier_state = read_state(tier_project)
        tier_state["components"]["paper"]["state"] = "A1"
        tier_state["components"]["q1"]["state"] = "S4"
        write_json(tier_project / ".modeling/state.json", tier_state)
        for relative in ("src/q1/model.py", "src/q1/solver.py", "src/q1/report.py"):
            target = tier_project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("existing manuscript content\n", encoding="utf-8")
        g1_plan = {
            "schema_version": "11.0", "plan_id": "v15-g1-multifile",
            "request": "在一个步骤里同步实现模型、求解器和结果整理代码。",
            "steps": [{
                "id": "edit-related-files", "tier": "G1_WORKING", "mode": "mutate",
                "object": "model", "action": "implement", "component_id": "q1",
                "events": ["model_implementation"], "facts": {},
                "working_context": {"component_type": "question", "state": "S4"},
                "depends_on": [],
                "change_set": {
                    "paths": [
                        "src/q1/model.py", "src/q1/solver.py", "src/q1/report.py",
                    ],
                    "facets": ["implementation"], "claim_refs": [],
                },
            }],
        }
        tier_state_before = (tier_project / ".modeling/state.json").read_bytes()
        tier_control_before = sorted(
            path.relative_to(tier_project).as_posix()
            for path in (tier_project / ".modeling").rglob("*") if path.is_file()
        )
        g1_result = resolve(g1_plan, tier_project, root)
        tier_state_after = read_state(tier_project)
        tier_control_after = sorted(
            path.relative_to(tier_project).as_posix()
            for path in (tier_project / ".modeling").rglob("*") if path.is_file()
        )
        branch_plan = {
            "schema_version": "11.0", "plan_id": "v15-branch-local",
            "request": "解释项目；无效步骤之后再规划；同时独立比较模型。",
            "steps": [
                {
                    "id": "bad", "tier": "G0_ADVISORY", "mode": "advisory_readonly",
                    "object": "project", "action": "advise", "component_id": None,
                    "events": ["unknown_global_gate"], "facts": {}, "depends_on": [],
                },
                {
                    "id": "child", "tier": "G0_ADVISORY", "mode": "advisory_readonly",
                    "object": "project", "action": "plan", "component_id": None,
                    "events": ["project_planning"], "facts": {},
                    "working_context": {"component_type": "project", "state": "P0"},
                    "depends_on": ["bad"],
                },
                {
                    "id": "independent", "tier": "G0_ADVISORY", "mode": "advisory_readonly",
                    "object": "model", "action": "compare", "component_id": "q1",
                    "events": ["model_comparison"], "facts": {},
                    "working_context": {"component_type": "question", "state": "S3"},
                    "depends_on": [],
                },
            ],
        }
        branch_result = resolve(branch_plan, routing_project, root)
        branch_steps = {item["id"]: item for item in branch_result.get("steps", [])}
        g2_context_plan = {
            "schema_version": "11.0", "plan_id": "v15-g2-context-reject",
            "request": "关闭 S6。", "window_context": "same_window",
            "steps": [{
                "id": "close", "tier": "G2_CHECKPOINT", "mode": "promote",
                "object": "verification", "action": "close_s6", "component_id": "q1",
                "events": ["recovery_assessment", "s6_close"], "facts": {},
                "working_context": {"component_type": "question", "state": "S6"},
                "depends_on": [],
                "change_set": {
                    "paths": [], "facets": ["question_state"], "claim_refs": [],
                },
                "state_effect": {"component_id": "q1", "from": "S6", "to": "S7"},
            }],
        }
        g2_context_result = resolve(g2_context_plan, routing_project, root)
        record(
            "SCENARIO.ROUTING.TIER_AND_BRANCH_BOUNDARIES",
            g0_result.get("status") == "resolved"
            and g0_result.get("route_ids") == ["RT.PROJECT.ADVISE"]
            and g1_result.get("status") == "resolved"
            and g1_result.get("route_ids") == ["RT.MODEL.IMPLEMENT"]
            and len(g1_result["steps"][0]["change_set"]["paths"]) == 3
            and tier_state_before == (tier_project / ".modeling/state.json").read_bytes()
            and tier_control_before == tier_control_after == [".modeling/state.json"]
            and "executions" not in tier_state_after
            and "workspace_manifest" not in tier_state_after
            and branch_result.get("status") == "partial"
            and branch_steps.get("bad", {}).get("status") == "blocked"
            and "unknown_event:unknown_global_gate" in resolution_errors(branch_result)
            and branch_steps.get("child", {}).get("status") == "dependency_blocked"
            and branch_steps.get("independent", {}).get("status") == "resolved"
            and g2_context_result.get("status") == "blocked"
            and "working_context_cannot_replace_authoritative_checkpoint_state" in resolution_errors(g2_context_result),
            f"g0={resolution_errors(g0_result)};g1={resolution_errors(g1_result)}"
            + f";control_before={tier_control_before};control_after={tier_control_after}"
            + f";branch={resolution_errors(branch_result)};g2={resolution_errors(g2_context_result)}",
        )

        visual_plan = {
            "schema_version": "11.0", "plan_id": "v15-visual-a0",
            "request": "创建、渲染并审计新的工程示意图。",
            "steps": [{
                "id": "figure", "tier": "G1_WORKING", "mode": "mutate",
                "object": "visual", "action": "create", "component_id": None,
                "working_context": {"component_type": "artifact", "state": "A0"},
                "events": ["visual_design", "visual_generate", "visual_render", "visual_audit"],
                "facts": {"data_driven_visual": False}, "depends_on": [],
                "change_set": {
                    "paths": ["paper/figures/system.svg"],
                    "facets": ["visual"], "claim_refs": [],
                },
            }],
        }
        visual_result = resolve(visual_plan, routing_project, root)
        data_visual_plan = deepcopy(visual_plan)
        data_visual_plan["plan_id"] = "v15-visual-a0-data"
        data_visual_plan["request"] = "从已登记结果数据创建、渲染并审计新图表。"
        data_visual_plan["steps"][0]["facts"]["data_driven_visual"] = True
        data_visual_result = resolve(data_visual_plan, routing_project, root)
        unclassified_visual = deepcopy(visual_plan)
        unclassified_visual["plan_id"] = "v15-visual-a0-unclassified"
        unclassified_visual["steps"][0]["facts"] = {}
        unclassified_result = resolve(unclassified_visual, routing_project, root)
        concept_rules = set(visual_result.get("rule_ids", []))
        data_visual_rules = set(data_visual_result.get("rule_ids", []))
        record(
            "SCENARIO.VISUAL.A0_ACCEPTANCE",
            visual_result.get("status") == "resolved"
            and visual_result.get("route_ids") == ["RT.VISUAL.CREATE"]
            and {
                "VIS.DESIGN.SOURCE_FIDELITY", "VIS.IDENTITY.RENDER", "VIS.IDENTITY.SYNC",
                "VIS.LAYOUT.LABELS", "VIS.LAYOUT.LEGIBILITY",
                "VIS.LAYOUT.COLOR", "VIS.LAYOUT.FONTS",
            }.issubset(concept_rules)
            and not {"VIS.IDENTITY.DATA", "VIS.IDENTITY.NO_MANUAL_VALUES"} & concept_rules
            and data_visual_result.get("status") == "resolved"
            and {"VIS.IDENTITY.DATA", "VIS.IDENTITY.NO_MANUAL_VALUES"}.issubset(data_visual_rules)
            and unclassified_result.get("status") == "blocked"
            and "event_boolean_fact_required:visual_generate:data_driven_visual" in resolution_errors(unclassified_result),
            f"concept={sorted(concept_rules)};data={sorted(data_visual_rules)}"
            + f";unclassified={resolution_errors(unclassified_result)}",
        )

        model_request = "建立第一问模型、实现并求解，再做结构检验并写队友讲解稿。"
        model_chain = {
            "schema_version": "11.0", "plan_id": "v15-model-responsibility-chain",
            "request": model_request,
            "steps": [
                {
                    "id": "establish", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "model", "action": "specify", "component_id": "q1",
                    "working_context": {"component_type": "question", "state": "S3"},
                    "events": ["model_specification"], "facts": {}, "depends_on": [],
                    "change_set": {
                        "paths": ["planning/q1_model_spec.md"],
                        "facets": ["model_spec"], "claim_refs": [],
                    },
                },
                {
                    "id": "implement", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "model", "action": "implement", "component_id": "q1",
                    "working_context": {"component_type": "question", "state": "S4"},
                    "events": ["model_implementation"], "facts": {},
                    "depends_on": ["establish"],
                    "change_set": {
                        "paths": ["src/q1/solve.py"],
                        "facets": ["implementation"], "claim_refs": [],
                    },
                },
                {
                    "id": "solve", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "model", "action": "solve", "component_id": "q1",
                    "working_context": {"component_type": "question", "state": "S5"},
                    "events": ["model_execution", "result_record"], "facts": {},
                    "depends_on": ["implement"],
                    "change_set": {
                        "paths": ["output/q1/result.json"],
                        "facets": ["computation", "result_identity"], "claim_refs": [],
                    },
                    "runtime_actions": [{
                        "id": "run-solve", "kind": "project_model_execution",
                        "event": "model_execution", "repetition": "first_run",
                        "scope": {
                            "kind": "component", "component_ids": ["q1"],
                            "input_paths": [], "output_paths": ["output/q1/result.json"],
                        },
                        "command": {"argv": ["python3", "-c", "print('solve')"], "cwd": "."},
                        "authorization": {
                            "source": "direct_user_request",
                            "request_excerpt": "实现并求解",
                        },
                    }],
                },
                {
                    "id": "verify", "tier": "G0_ADVISORY", "mode": "project_readonly",
                    "object": "verification", "action": "validate_structure", "component_id": "q1",
                    "working_context": {"component_type": "question", "state": "S6"},
                    "events": ["structural_verification", "constraint_verification"],
                    "facts": {}, "depends_on": ["solve"],
                    "runtime_actions": [{
                        "id": "run-constraint", "kind": "project_verification_execution",
                        "event": "constraint_verification", "repetition": "first_run",
                        "scope": {
                            "kind": "component", "component_ids": ["q1"],
                            "input_paths": [], "output_paths": [],
                        },
                        "command": {"argv": ["python3", "-c", "print('verify')"], "cwd": "."},
                        "authorization": {
                            "source": "direct_user_request",
                            "request_excerpt": "结构检验",
                        },
                    }],
                },
                {
                    "id": "brief", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "model", "action": "prepare_teammate_brief", "component_id": "q1",
                    "working_context": {"component_type": "question", "state": "S7"},
                    "events": ["teammate_brief_write"], "facts": {},
                    "depends_on": ["verify"],
                    "change_set": {
                        "paths": ["docs/q1/solution_brief.md"],
                        "facets": ["technical_handoff"], "claim_refs": [],
                    },
                },
            ],
        }
        model_positive = resolve(model_chain, routing_project, root)
        model_steps = {item["id"]: item for item in model_positive.get("steps", [])}
        bad_establish = deepcopy(model_chain)
        bad_establish["steps"] = [deepcopy(model_chain["steps"][0])]
        bad_establish["steps"][0]["events"] = []
        bad_establish_result = resolve(bad_establish, routing_project, root)
        bad_solve = deepcopy(model_chain)
        bad_solve["steps"] = [deepcopy(model_chain["steps"][2])]
        bad_solve["steps"][0]["depends_on"] = []
        bad_solve["steps"][0]["events"] = ["result_record"]
        bad_solve["steps"][0].pop("runtime_actions")
        bad_solve_result = resolve(bad_solve, routing_project, root)
        bad_verify = deepcopy(model_chain)
        bad_verify["steps"] = [deepcopy(model_chain["steps"][3])]
        bad_verify["steps"][0]["depends_on"] = []
        bad_verify["steps"][0]["events"] = ["structural_verification"]
        bad_verify["steps"][0].pop("runtime_actions")
        bad_verify_result = resolve(bad_verify, routing_project, root)
        bad_brief = deepcopy(model_chain)
        bad_brief["steps"] = [deepcopy(model_chain["steps"][4])]
        bad_brief["steps"][0]["depends_on"] = []
        bad_brief["steps"][0]["component_id"] = None
        bad_brief_result = resolve(bad_brief, routing_project, root)
        establish_rules = set(model_steps.get("establish", {}).get("rule_ids", []))
        implement_rules = set(model_steps.get("implement", {}).get("rule_ids", []))
        solve_rules = set(model_steps.get("solve", {}).get("rule_ids", []))
        verify_rules = set(model_steps.get("verify", {}).get("rule_ids", []))
        brief_rules = set(model_steps.get("brief", {}).get("rule_ids", []))
        record(
            "SCENARIO.MODELING.ESTABLISH_SOLVE_VERIFY_HANDOFF",
            model_positive.get("status") == "resolved"
            and model_positive.get("execution_order") == [
                "establish", "implement", "solve", "verify", "brief",
            ]
            and {"MOD.SPEC.VARIABLES", "MOD.SPEC.EQUATIONS", "MOD.SPEC.ALGORITHM", "MOD.SPEC.ASSUMPTIONS"}.issubset(establish_rules)
            and {"MOD.SPEC.READINESS", "MOD.IMPLEMENT.SPEC_BIND"}.issubset(implement_rules)
            and {"MOD.IMPLEMENT.REPRODUCE", "MOD.IMPLEMENT.DETERMINISM", "MOD.IMPLEMENT.OUTPUT_REGISTER", "MOD.RESULTS.IDENTITY"}.issubset(solve_rules)
            and {"VER.E3.RISK_MATCH", "VER.E3.CONSTRAINT"}.issubset(verify_rules)
            and not {"VER.E3.INVARIANT", "VER.E3.LIMIT", "VER.E3.COUNTEREXAMPLE", "VER.E3.SENSITIVITY", "VER.E4.ASSUMPTIONS"} & verify_rules
            and {"MOD.RESULTS.TEAMMATE_BRIEF", "MOD.RESULTS.AUXILIARY_METHOD_VISIBILITY"}.issubset(brief_rules)
            and model_steps.get("brief", {}).get("component_ids") == ["q1"]
            and all(result.get("status") == "blocked" for result in (
                bad_establish_result, bad_solve_result, bad_verify_result, bad_brief_result,
            ))
            and "action_required_event_missing:model_specification" in resolution_errors(bad_establish_result)
            and "action_required_event_missing:model_execution" in resolution_errors(bad_solve_result)
            and "action_required_any_event_missing" in resolution_errors(bad_verify_result)
            and "action_component_id_required" in resolution_errors(bad_brief_result),
            f"positive={resolution_errors(model_positive)}"
            + ";rules=" + json.dumps({
                "establish": sorted(establish_rules), "implement": sorted(implement_rules),
                "solve": sorted(solve_rules), "verify": sorted(verify_rules),
                "brief": sorted(brief_rules),
            }, ensure_ascii=False, sort_keys=True)
            + ";negative=" + json.dumps({
                "establish": resolution_errors(bad_establish_result),
                "solve": resolution_errors(bad_solve_result),
                "verify": resolution_errors(bad_verify_result),
                "brief": resolution_errors(bad_brief_result),
            }, ensure_ascii=False, sort_keys=True),
        )

        manuscript_project = workspace / "manuscript-closure"
        run(
            manager, "init", "--project-root", str(manuscript_project),
            "--project-id", "manuscript-demo",
        )
        run(
            manager, "add-component", "--project-root", str(manuscript_project),
            "--component-id", "paper", "--type", "artifact",
        )
        manuscript_state = read_state(manuscript_project)
        manuscript_state["components"]["paper"]["state"] = "A1"
        write_json(manuscript_project / ".modeling/state.json", manuscript_state)
        for relative in (
            "paper/paper.tex", "paper/sections/method.tex",
            "paper/sections/results.tex", "paper/sections/conclusion.tex",
        ):
            target = manuscript_project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("existing manuscript content\n", encoding="utf-8")

        def manuscript_plan(
            plan_id: str,
            request: str,
            action: str,
            events: list[str],
            change_class: str,
            completion_scope: str,
            path: str,
            facets: list[str],
            *,
            profile_selected: bool = False,
        ) -> dict[str, Any]:
            return {
                "schema_version": "11.0", "plan_id": plan_id, "request": request,
                "steps": [{
                    "id": plan_id, "tier": "G1_WORKING", "mode": "mutate",
                    "object": "manuscript", "action": action, "component_id": "paper",
                    "events": events,
                    "facts": {
                        "change_class": change_class,
                        "completion_scope": completion_scope,
                        "profile_selected": profile_selected,
                        "published_revision": False,
                        "existing_paths_only": True,
                    },
                    "depends_on": [],
                    "change_set": {
                        "paths": [path], "facets": facets,
                        "claim_refs": [] if "orthography" in facets else [f"claim:{plan_id}"],
                    },
                }],
            }

        typo_plan = manuscript_plan(
            "fix-typo", "修正稿件中的一个错别字。", "local_edit",
            ["local_manuscript_edit"], "typo", "changed_scope_only",
            "paper/paper.tex", ["orthography"],
        )
        method_plan = manuscript_plan(
            "rewrite-method", "重写方法节并保持计算职责清楚。", "rewrite",
            ["manuscript_write"], "section_substantive", "section_working_change_only",
            "paper/sections/method.tex", ["explanation", "method", "notation"],
        )
        result_plan = manuscript_plan(
            "rewrite-result", "重写结果节并绑定结果身份。", "rewrite",
            ["manuscript_write"], "section_substantive", "section_working_change_only",
            "paper/sections/results.tex", ["explanation", "notation", "result"],
        )
        conclusion_plan = manuscript_plan(
            "rewrite-conclusion", "重写结论节并保持主张边界。", "rewrite",
            ["manuscript_write"], "section_substantive", "section_working_change_only",
            "paper/sections/conclusion.tex", ["conclusion", "explanation", "notation"],
        )
        profile_plan = manuscript_plan(
            "apply-profile", "按明确选中的写作画像润色这一段。", "local_edit",
            ["local_manuscript_edit", "writing_profile_apply"],
            "profile_local", "profiled_local_change_only",
            "paper/paper.tex", ["writing_profile"], profile_selected=True,
        )
        manuscript_positive = {
            "typo": resolve(typo_plan, manuscript_project, root),
            "method": resolve(method_plan, manuscript_project, root),
            "result": resolve(result_plan, manuscript_project, root),
            "conclusion": resolve(conclusion_plan, manuscript_project, root),
            "profile": resolve(profile_plan, manuscript_project, root),
        }
        missing_facts = deepcopy(method_plan)
        missing_facts["steps"][0]["facts"] = {}
        missing_facts_result = resolve(missing_facts, manuscript_project, root)
        wrong_type = deepcopy(method_plan)
        wrong_type["steps"][0]["facts"]["profile_selected"] = "false"
        wrong_type_result = resolve(wrong_type, manuscript_project, root)
        missing_path = deepcopy(method_plan)
        missing_path["steps"][0]["change_set"]["paths"] = ["paper/sections/missing.tex"]
        missing_path_result = resolve(missing_path, manuscript_project, root)
        implicit_profile = deepcopy(profile_plan)
        implicit_profile["steps"][0]["facts"]["profile_selected"] = False
        implicit_profile_result = resolve(implicit_profile, manuscript_project, root)
        manuscript_rules = {
            key: set(value.get("rule_ids", [])) for key, value in manuscript_positive.items()
        }
        manuscript_closures = {
            key: (
                value.get("steps", [{}])[0].get("manuscript_closure", {}).get("change_class")
                if value.get("steps") else None
            )
            for key, value in manuscript_positive.items()
        }
        missing_facts_text = resolution_errors(missing_facts_result)
        record(
            "SCENARIO.MANUSCRIPT.CLOSURE_FACTS",
            all(value.get("status") == "resolved" for value in manuscript_positive.values())
            and manuscript_closures == {
                "typo": "typo", "method": "section_substantive",
                "result": "section_substantive", "conclusion": "section_substantive",
                "profile": "profile_local",
            }
            and {"MAN.LOCAL.SCOPE", "MAN.LOCAL.NO_FULL_AUDIT"}.issubset(manuscript_rules["typo"])
            and not any(item.startswith("MAN.CONTENT.") for item in manuscript_rules["typo"])
            and "MAN.CONTENT.METHOD" in manuscript_rules["method"]
            and "MAN.CONTENT.RESULT" not in manuscript_rules["method"]
            and "MAN.CONTENT.RESULT" in manuscript_rules["result"]
            and "MAN.CONTENT.METHOD" not in manuscript_rules["result"]
            and "MAN.CONTENT.LIMITATION" in manuscript_rules["conclusion"]
            and not {"MAN.CONTENT.METHOD", "MAN.CONTENT.RESULT"} & manuscript_rules["conclusion"]
            and {"MAN.PROFILE.OPT_IN", "MAN.PROFILE.TRUTH", "MAN.PROFILE.FORMAT"}.issubset(manuscript_rules["profile"])
            and missing_facts_result.get("status") == "blocked"
            and all(field in missing_facts_text for field in (
                "change_class", "completion_scope", "profile_selected",
                "published_revision", "existing_paths_only",
            ))
            and wrong_type_result.get("status") == "blocked"
            and "boolean" in resolution_errors(wrong_type_result)
            and missing_path_result.get("status") == "blocked"
            and "manuscript_existing_path_missing:paper/sections/missing.tex" in resolution_errors(missing_path_result)
            and implicit_profile_result.get("status") == "blocked"
            and "profile" in resolution_errors(implicit_profile_result),
            "positive=" + json.dumps(
                {key: resolution_errors(value) for key, value in manuscript_positive.items()},
                ensure_ascii=False, sort_keys=True,
            )
            + ";closures=" + json.dumps(manuscript_closures, sort_keys=True)
            + ";rules=" + json.dumps(
                {key: sorted(value) for key, value in manuscript_rules.items()},
                ensure_ascii=False, sort_keys=True,
            )
            + ";negative=" + json.dumps({
                "missing_facts": missing_facts_text,
                "wrong_type": resolution_errors(wrong_type_result),
                "missing_path": resolution_errors(missing_path_result),
                "implicit_profile": resolution_errors(implicit_profile_result),
            }, ensure_ascii=False, sort_keys=True),
        )

        overlapping_role_proposals = [
            {
                "path": "paper/main.tex", "platform_role": "manuscript",
                "purpose": "Evaluator-facing manuscript selected explicitly from an overlapping path.",
                "consumer_ids": ["INPUTS"], "lifecycle": "working",
                "identity_class": "working", "class": "manuscript",
                "authorization_basis": "authorized positive scenario", "replaces": None,
            },
            {
                "path": "paper/figures/system.svg", "platform_role": "visual",
                "purpose": "Publication visual selected explicitly from an overlapping path.",
                "consumer_ids": ["INPUTS"], "lifecycle": "working",
                "identity_class": "working", "class": "visual",
                "authorization_basis": "authorized positive scenario", "replaces": None,
            },
            {
                "path": "output/q3/result.json", "platform_role": "result",
                "purpose": "Machine result selected explicitly from an overlapping output path.",
                "consumer_ids": ["INPUTS"], "lifecycle": "working",
                "identity_class": "working", "class": "result",
                "authorization_basis": "authorized positive scenario", "replaces": None,
            },
            {
                "path": "output/q3/result-chart.png", "platform_role": "visual",
                "purpose": "Result visual selected explicitly from an overlapping output path.",
                "consumer_ids": ["INPUTS"], "lifecycle": "working",
                "identity_class": "working", "class": "visual",
                "authorization_basis": "authorized positive scenario", "replaces": None,
            },
        ]
        overlapping_role_results: list[tuple[str, int, list[str], str]] = []
        for index, proposal_item in enumerate(overlapping_role_proposals):
            proposal_file = workspace / f"overlapping-role-{index}.json"
            write_json(proposal_file, proposal_item)
            code, payload, log = run(
                root / "scripts/artifact_guard.py",
                "--project-root", str(project), "--proposal", str(proposal_file),
            )
            overlapping_role_results.append(
                (
                    proposal_item["path"], code, payload.get("errors", []),
                    log if code != 0 else "",
                )
            )

        canonical_spelling_proposal = {
            "path": "paper/canonical-artifact.tex", "platform_role": "manuscript",
            "purpose": "Canonical artifact path spelling accepted before resolved containment.",
            "consumer_ids": ["INPUTS"], "lifecycle": "working",
            "identity_class": "working", "class": "manuscript",
            "authorization_basis": "authorized canonical path scenario", "replaces": None,
        }
        canonical_spelling_path = workspace / "canonical-artifact-path.json"
        write_json(canonical_spelling_path, canonical_spelling_proposal)
        canonical_spelling_code, canonical_spelling_payload, canonical_spelling_log = run(
            root / "scripts/artifact_guard.py",
            "--project-root", str(project), "--proposal", str(canonical_spelling_path),
        )
        noncanonical_artifact_paths = {
            "dot_segment": "paper/./canonical-artifact.tex",
            "double_slash": "paper//canonical-artifact.tex",
            "trailing_slash": "paper/canonical-artifact.tex/",
            "backslash": r"paper\canonical-artifact.tex",
            "absolute": "/paper/canonical-artifact.tex",
            "drive_prefixed": "C:/paper/canonical-artifact.tex",
            "parent_segment": "paper/../canonical-artifact.tex",
            "nul": "paper/\x00canonical-artifact.tex",
        }
        noncanonical_artifact_results: list[tuple[str, int, list[str], str]] = []
        for label, relative_path in noncanonical_artifact_paths.items():
            proposal_item = dict(canonical_spelling_proposal)
            proposal_item["path"] = relative_path
            proposal_file = workspace / f"noncanonical-artifact-{label}.json"
            write_json(proposal_file, proposal_item)
            code, payload, log = run(
                root / "scripts/artifact_guard.py",
                "--project-root", str(project), "--proposal", str(proposal_file),
            )
            noncanonical_artifact_results.append(
                (label, code, payload.get("errors", []), log if code == 0 else "")
            )

        escaping_artifact_proposal = dict(canonical_spelling_proposal)
        escaping_artifact_proposal["path"] = "escape-link/artifact.tex"
        escaping_artifact_path = workspace / "escaping-artifact-path.json"
        write_json(escaping_artifact_path, escaping_artifact_proposal)
        escaping_artifact_code, escaping_artifact_payload, escaping_artifact_log = run(
            root / "scripts/artifact_guard.py",
            "--project-root", str(project), "--proposal", str(escaping_artifact_path),
        )

        selected_path_mismatch_proposal = {
            "path": "paper/main.tex", "platform_role": "code",
            "purpose": "Selected code role must not borrow a path match from another role.",
            "consumer_ids": ["INPUTS"], "lifecycle": "working",
            "identity_class": "working", "class": "code",
            "authorization_basis": "authorized negative scenario", "replaces": None,
        }
        selected_path_mismatch_path = workspace / "selected-role-path-mismatch.json"
        write_json(selected_path_mismatch_path, selected_path_mismatch_proposal)
        selected_path_mismatch_code, selected_path_mismatch_payload, selected_path_mismatch_log = run(
            root / "scripts/artifact_guard.py",
            "--project-root", str(project), "--proposal", str(selected_path_mismatch_path),
        )

        mismatch_proposal = {
            "path": "src/q1/input.csv", "platform_role": "code",
            "purpose": "Deliberately mismatched role and class for admission rejection.",
            "consumer_ids": ["INPUTS"], "lifecycle": "working",
            "identity_class": "working", "class": "source",
            "authorization_basis": "authorized negative scenario", "replaces": None,
        }
        mismatch_proposal_path = workspace / "role-class-mismatch.json"
        write_json(mismatch_proposal_path, mismatch_proposal)
        mismatch_code, mismatch_payload, mismatch_log = run(
            root / "scripts/artifact_guard.py",
            "--project-root", str(project), "--proposal", str(mismatch_proposal_path),
        )

        formal_project = workspace / "formal-artifact-events"
        formal_init, _, formal_init_log = run(
            manager, "init", "--project-root", str(formal_project),
            "--project-id", "formal-artifact-demo",
        )
        formal_add, _, formal_add_log = run(
            manager, "add-component", "--project-root", str(formal_project),
            "--component-id", "INPUTS", "--type", "shared_data",
        )
        existing_first_artifact = formal_project / "data/existing-first.csv"
        existing_first_artifact.parent.mkdir(parents=True)
        existing_first_artifact.write_text("x\n1\n", encoding="utf-8")
        formal_validation_file = formal_project / "planning/formal-validation.txt"
        formal_validation_file.parent.mkdir(parents=True)
        formal_validation_file.write_text("artifact validation passed\n", encoding="utf-8")
        formal_evidence_records = [
            evidence("INPUTS", "EV-FORMAL-DATA-AUDIT", "data_audit"),
            evidence("INPUTS", "EV-FORMAL-TREATMENT", "treatment_decision"),
            file_evidence(
                formal_project, "INPUTS", "EV-FORMAL-ARTIFACT-VALIDATION",
                "artifact_validation", "planning/formal-validation.txt",
            ),
        ]
        formal_evidence_codes: list[int] = []
        for record_item in formal_evidence_records:
            record_path = workspace / f"{record_item['id']}.json"
            write_json(record_path, record_item)
            code, _, _ = run(
                manager, "record-evidence", "--project-root", str(formal_project),
                "--component-id", "INPUTS", "--evidence", str(record_path),
            )
            formal_evidence_codes.append(code)
        formal_state = read_state(formal_project)
        formal_state["components"]["INPUTS"]["state"] = "D2"
        write_json(formal_project / ".modeling/state.json", formal_state)
        seal_fixture_baseline(formal_project, "formal-artifact-events-fixture")

        def formal_data_audit_plan(
            event: str, relative_path: str, identifier: str
        ) -> dict[str, Any]:
            return {
                "schema_version": "11.0", "plan_id": identifier,
                "request": "在明确的正式产物边界登记或刷新数据产物。",
                "window_context": "same_window",
                "steps": [{
                    "id": "formal", "tier": "G1_WORKING", "mode": "mutate",
                    "object": "data", "action": "audit", "component_id": "INPUTS",
                    "events": ["data_audit", event],
                    "facts": {"predictive_or_evaluative_use": False},
                    "depends_on": [],
                    "change_set": {
                        "paths": [relative_path], "facets": ["data_identity"],
                        "claim_refs": [],
                    },
                }],
            }

        formal_register_results = {
            "new-first-register": resolve(
                formal_data_audit_plan(
                    "artifact_register", "data/new-first.csv",
                    "formal-new-first-register",
                ),
                formal_project, root,
            ),
            "existing-first-register": resolve(
                formal_data_audit_plan(
                    "artifact_register", "data/existing-first.csv",
                    "formal-existing-first-register",
                ),
                formal_project, root,
            ),
        }
        formal_refresh_result = resolve(
            formal_data_audit_plan(
                "artifact_refresh", "data/existing-first.csv", "formal-refresh"
            ),
            formal_project, root,
        )
        formal_promotion_plan = {
            "schema_version": "11.0", "plan_id": "formal-promotion",
            "request": "在证据齐备后晋升数据产物。",
            "window_context": "same_window",
            "steps": [{
                "id": "formal", "tier": "G2_CHECKPOINT", "mode": "promote",
                "object": "data", "action": "freeze", "component_id": "INPUTS",
                "events": [
                    "recovery_assessment", "dataset_freeze", "artifact_promotion",
                ],
                "facts": {"predictive_or_evaluative_use": False},
                "depends_on": [],
                "change_set": {
                    "paths": ["data/promoted.csv"], "facets": ["data_identity"],
                    "claim_refs": [],
                },
            }],
        }
        formal_promotion_result = resolve(
            formal_promotion_plan, formal_project, root,
        )

        def formal_surface(result: dict[str, Any]) -> dict[str, Any]:
            step = result.get("steps", [{}])[0]
            return {
                "status": result.get("status"),
                "controller_events": step.get("controller_events", []),
                "artifact_rules": sorted(
                    rule_id for rule_id in step.get("rule_ids", [])
                    if rule_id.startswith("ART.")
                ),
                "reasons": step.get("reasons", []),
            }

        register_surfaces = {
            key: formal_surface(value) for key, value in formal_register_results.items()
        }
        refresh_surface = formal_surface(formal_refresh_result)
        promotion_surface = formal_surface(formal_promotion_result)

        legacy_project = workspace / "existing-noncanonical"
        legacy_solver = legacy_project / "legacy_code/solver.py"
        legacy_solver.parent.mkdir(parents=True, exist_ok=True)
        legacy_solver.write_text("print('legacy')\n", encoding="utf-8")
        legacy_init, _, legacy_init_log = run(
            manager, "init", "--project-root", str(legacy_project),
            "--project-id", "existing-noncanonical",
        )
        freeze_destination = workspace / "unauthorized-release"
        freeze_code, _, freeze_log = run(
            root / "scripts/freeze_release.py",
            "--root", str(root), "--destination", str(freeze_destination),
        )
        record(
            "SCENARIO.PLATFORM.ARTIFACT_ADMISSION_BOUNDARIES",
            all(code == 0 and not errors for _, code, errors, _ in overlapping_role_results)
            and canonical_spelling_code == 0
            and not canonical_spelling_payload.get("errors", [])
            and all(
                code != 0
                and any("artifact_path_noncanonical" in error for error in errors)
                for _, code, errors, _ in noncanonical_artifact_results
            )
            and escaping_artifact_code != 0
            and any(
                "path escapes project root" in error
                for error in escaping_artifact_payload.get("errors", [])
            )
            and selected_path_mismatch_code != 0
            and "platform_role_path_mismatch" in selected_path_mismatch_payload.get("errors", [])
            and "platform_role_class_mismatch" not in selected_path_mismatch_payload.get("errors", [])
            and mismatch_code != 0
            and "platform_role_class_mismatch" in mismatch_payload.get("errors", [])
            and not (project / "src/q1/input.csv").exists()
            and formal_init == 0
            and formal_add == 0
            and all(code == 0 for code in formal_evidence_codes)
            and all(
                surface["status"] == "resolved"
                and "before_file_creation" in surface["controller_events"]
                and admission_atoms.issubset(set(surface["artifact_rules"]))
                and "ART.REGISTER.IDENTITY" in surface["artifact_rules"]
                for surface in register_surfaces.values()
            )
            and refresh_surface["status"] == "resolved"
            and "before_file_creation" not in refresh_surface["controller_events"]
            and not admission_atoms & set(refresh_surface["artifact_rules"])
            and "ART.REGISTER.IDENTITY" in refresh_surface["artifact_rules"]
            and promotion_surface["status"] == "resolved"
            and "before_file_creation" not in promotion_surface["controller_events"]
            and not admission_atoms & set(promotion_surface["artifact_rules"])
            and "ART.PROMOTE.VALIDATE" in promotion_surface["artifact_rules"]
            and legacy_init == 0
            and legacy_solver.read_text(encoding="utf-8") == "print('legacy')\n"
            and not (legacy_project / "src").exists()
            and freeze_code != 0 and not freeze_destination.exists(),
            f"overlap={overlapping_role_results}"
            + f";canonical_spelling={canonical_spelling_code}:"
            + f"{canonical_spelling_payload.get('errors')}:{canonical_spelling_log}"
            + f";noncanonical_spelling={noncanonical_artifact_results}"
            + f";escaping_spelling={escaping_artifact_code}:"
            + f"{escaping_artifact_payload.get('errors')}:{escaping_artifact_log}"
            + f";selected_path_mismatch={selected_path_mismatch_code}:"
            + f"{selected_path_mismatch_payload.get('errors')}:{selected_path_mismatch_log}"
            + f";mismatch={mismatch_code}:{mismatch_payload.get('errors')}:{mismatch_log}"
            + ";formal="
            + json.dumps(
                {
                    "setup": [formal_init, formal_add, *formal_evidence_codes],
                    "register": register_surfaces,
                    "refresh": refresh_surface,
                    "promotion": promotion_surface,
                },
                ensure_ascii=False, sort_keys=True,
            )
            + f";legacy={legacy_init}:src_exists={(legacy_project / 'src').exists()}:{legacy_init_log}"
            + f";freeze={freeze_code}:destination={freeze_destination.exists()}:{freeze_log}",
        )

        pause_plan = {
            "schema_version": "11.0", "plan_id": "v15-pause",
            "request": "今天先到这里，做收尾整理并记下下一步。",
            "steps": [{
                "id": "pause", "tier": "G1_WORKING", "mode": "mutate",
                "object": "project", "action": "pause", "component_id": None,
                "events": ["handoff"], "facts": {}, "depends_on": [],
                "change_set": {
                    "paths": [], "facets": ["open_decisions", "next_actions"],
                    "claim_refs": [],
                },
            }],
        }
        pause_only = resolve(pause_plan, na_project, root)
        g2_pause_plan = deepcopy(pause_plan)
        g2_pause_plan["steps"][0]["tier"] = "G2_CHECKPOINT"
        g2_pause_result = resolve(g2_pause_plan, na_project, root)
        close_then_pause_plan = deepcopy(na_plan)
        close_then_pause_plan["plan_id"] = "v15-close-then-pause"
        close_then_pause_plan["request"] = "确认关闭当前 S6，然后暂停并记录下一步。"
        dependent_pause = deepcopy(pause_plan["steps"][0])
        dependent_pause["depends_on"] = ["close"]
        close_then_pause_plan["steps"].append(dependent_pause)
        close_then_pause = resolve(close_then_pause_plan, na_project, root)
        close_pause_steps = {
            item["id"]: item for item in close_then_pause.get("steps", [])
        }
        forbidden_replays = {
            "model_execution", "implementation_verification", "numerical_verification",
            "structural_verification", "reality_verification", "s6_readiness",
        }
        observed_close_pause_events = {
            event for item in close_then_pause.get("steps", []) for event in item.get("events", [])
        }
        record(
            "SCENARIO.PROJECT.PAUSE_NO_VERIFICATION_REPLAY",
            pause_only.get("status") == "resolved"
            and pause_only.get("route_ids") == ["RT.PROJECT.RESUME"]
            and pause_only["steps"][0].get("events") == ["handoff"]
            and pause_only["steps"][0].get("component_ids") == []
            and pause_only.get("action_grants") == []
            and g2_pause_result.get("status") == "blocked"
            and "action_maximum_tier" in resolution_errors(g2_pause_result)
            and close_then_pause.get("status") == "resolved"
            and close_then_pause.get("execution_order") == ["close", "pause"]
            and close_pause_steps.get("pause", {}).get("events") == ["handoff"]
            and close_pause_steps.get("pause", {}).get("component_ids") == []
            and close_pause_steps.get("close", {}).get("events") == [
                "recovery_assessment", "s6_close",
            ]
            and not forbidden_replays & observed_close_pause_events
            and close_then_pause.get("action_grants") == [],
            f"pause={resolution_errors(pause_only)};g2={resolution_errors(g2_pause_result)}"
            + f";combined={resolution_errors(close_then_pause)}"
            + f";events={sorted(observed_close_pause_events)}",
        )

        unauthorized = {
            "schema_version": "11.0", "request": "继续项目",
            "steps": [{
                "id": "skill", "tier": "G1_WORKING", "mode": "skill_maintenance",
                "object": "skill", "action": "change_route", "component_id": None,
                "events": ["rule_load", "rule_change_request", "rule_change_analysis", "rule_change", "normative_behavior_change"],
                "facts": {}, "depends_on": [],
                "change_set": {
                    "paths": [
                        "references/route-contract.json",
                        "evals/release/frozen-manifest.json",
                    ],
                    "facets": ["route", "release_freeze"],
                    "claim_refs": [],
                },
            }],
        }
        authorized = json.loads(json.dumps(unauthorized))
        authorized["request"] = "去修之前明确指出的 Skill 问题"
        authorized["skill_authorization"] = {
            "source": "prior_explicit_user_request", "quote": "去修", "target": "skill"
        }
        mixed = json.loads(json.dumps(authorized))
        mixed["steps"].insert(0, {
            "id": "project", "tier": "G0_ADVISORY", "mode": "advisory_readonly",
            "object": "project", "action": "advise", "component_id": None,
            "events": [], "facts": {}, "depends_on": [],
        })
        unauthorized_result = resolve(unauthorized, root, root)
        authorized_result = resolve(authorized, root, root)
        mixed_result = resolve(mixed, root, root)
        mixed_skill = next(item for item in mixed_result.get("steps", []) if item.get("id") == "skill")
        record(
            "SCENARIO.SKILL.EXPLICIT_AUTHORIZATION",
            unauthorized_result.get("status") == "blocked"
            and authorized_result.get("status") == "resolved"
            and mixed_skill.get("status") == "blocked"
            and "skill_maintenance_must_be_isolated_plan" in mixed_skill.get("reasons", []),
            f"unauthorized={unauthorized_result.get('errors')};authorized={authorized_result.get('status')};mixed={mixed_skill.get('reasons')}",
        )

        registry = json.loads(
            (root / "evals/v15-regression-cases.json").read_text(encoding="utf-8")
        )
        for registry_case in registry.get("cases", []):
            record_registry_case(registry_case, routing_project)

        machine = json.loads((root / "references/state-machine.json").read_text(encoding="utf-8"))
        edge_failures: list[str] = []
        edge_count = 0
        terminal = {"question": "S7", "shared_data": "D3", "artifact": "A3"}
        for component_type, transitions in machine.get("transitions", {}).items():
            for index, edge in enumerate(transitions):
                edge_count += 1
                edge_project = workspace / f"edge-{component_type}-{index}"
                project_id = f"edge-{index}"
                init_edge, _, init_edge_log = run(
                    manager, "init", "--project-root", str(edge_project), "--project-id", project_id,
                )
                component_id = project_id
                if component_type != "project":
                    component_id = "component"
                    add_edge, _, add_edge_log = run(
                        manager, "add-component", "--project-root", str(edge_project),
                        "--component-id", component_id, "--type", component_type,
                    )
                    if add_edge != 0:
                        edge_failures.append(f"{component_type}:{edge['from']}->{edge['to']}:fixture:{add_edge_log}")
                        continue
                if init_edge != 0:
                    edge_failures.append(f"{component_type}:{edge['from']}->{edge['to']}:init:{init_edge_log}")
                    continue
                state_path = edge_project / ".modeling/state.json"
                edge_state = json.loads(state_path.read_text(encoding="utf-8"))
                if component_type == "project":
                    edge_state["project"]["state"] = edge["from"]
                else:
                    edge_state["components"][component_id]["state"] = edge["from"]
                    edge_state["components"][component_id]["status"] = (
                        "closed" if edge["from"] == terminal[component_type] else "active"
                    )
                write_json(state_path, edge_state)
                edge_plan = {
                    "schema_version": "11.0", "request": "验证状态机迁移路由闭合",
                    "window_context": "same_window",
                    "steps": [{
                        "id": "edge", "tier": "G2_CHECKPOINT", "mode": "promote",
                        "object": "state", "action": "transition", "component_id": component_id,
                        "events": ["recovery_assessment", "state_transition"], "facts": {}, "depends_on": [],
                        "change_set": {"paths": [".modeling/state.json"], "facets": ["state"], "claim_refs": []},
                        "state_effect": {"component_id": component_id, "from": edge["from"], "to": edge["to"]},
                    }],
                }
                edge_result = resolve(edge_plan, edge_project, root)
                if edge_result.get("status") != "resolved":
                    edge_failures.append(
                        f"{component_type}:{edge['from']}->{edge['to']}:"
                        + ",".join(edge_result.get("steps", [{}])[0].get("reasons", []))
                    )
        record(
            "SCENARIO.STATE.ALL_EDGES_RESOLVE",
            edge_count > 0 and not edge_failures,
            f"edges={edge_count};failures={edge_failures}",
        )

    errors = [item["id"] for item in cases if item["status"] != "pass"]
    result = {
        "schema_version": "15.0", "driver": "scenarios",
        "status": "pass" if not errors else "fail", "cases": cases, "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
