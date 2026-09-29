#!/usr/bin/env python3
"""Exercise the V16 R0/R1/R2 decision boundaries in disposable projects.

These scenarios deliberately test observable recovery outcomes instead of the
classifier's internal branch names.  They share the established V16 project
fixture, but every mutation is confined to a fresh temporary directory.
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
from typing import Any, Callable

from assess_recovery import assess
from lib_v10 import build_workspace_manifest, root_fingerprint, sha256_file, sha256_text
from lib_v11 import canonical_json, resolve
from recovery_v14 import required_recovery_reads
from recovery_manifest import inventory as full_inventory, verify_manifest
from run_v16_gate_scenarios import create_project, plan as compatible_plan


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def read_state(project: Path) -> dict[str, Any]:
    return json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))


def write_state(project: Path, state: dict[str, Any]) -> None:
    (project / ".modeling/state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def run(script: Path, *arguments: str) -> tuple[int, dict[str, Any], str]:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    process = subprocess.run(
        [sys.executable, "-B", str(script), *arguments],
        text=True, capture_output=True, check=False, timeout=20,
        env=environment,
    )
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        payload = {}
    return process.returncode, payload, (process.stderr + process.stdout)[-1600:]


def complete_full_manifest(project: Path) -> tuple[dict[str, Any], dict[str, int]]:
    """Create a full R2 manifest whose canonical objects all have dispositions."""
    manifest = full_inventory(project)
    for item in manifest["files"]:
        if item.get("duplicate_of") is not None:
            continue
        representation = item.get("representation")
        if representation in {"cache", "lock", "vendor", "control"}:
            item["inspection"] = {
                "status": "classified",
                "findings": ["Classified as a non-canonical project execution input."],
            }
        elif representation == "text":
            line_count = item.get("line_count", 0)
            item["inspection"] = {
                "status": "complete",
                "truncated": False,
                "read_ranges": [] if line_count == 0 else [[1, line_count]],
                "findings": ["Read from the first line through EOF."],
            }
        else:
            item["inspection"] = {
                "status": "complete",
                "truncated": False,
                "method": "native_or_structured_carrier_inspection",
                "inspected_units": ["whole_object"],
                "findings": ["The complete object was inspected in its declared carrier."],
            }
    errors, counts = verify_manifest(project, manifest)
    if errors:
        raise RuntimeError("fixture full manifest invalid: " + ";".join(errors))
    return manifest, counts


def _component_graph_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        component_id: {
            "dependencies": sorted(component.get("dependencies", [])),
            "consumers": sorted(component.get("consumers", [])),
        }
        for component_id, component in sorted(state.get("components", {}).items())
        if isinstance(component, dict)
    }


def _artifact_registry_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        path: {
            "sha256": artifact.get("sha256"),
            "producer": artifact.get("producer"),
            "consumers": sorted(artifact.get("consumers", [])),
            "identity_class": artifact.get("identity_class"),
            "status": artifact.get("status"),
        }
        for path, artifact in sorted(state.get("artifacts", {}).items())
        if isinstance(artifact, dict)
    }


def _fallback_baseline_meta(
    project: Path,
    state: dict[str, Any],
    manifest: dict[str, Any],
    established_by: dict[str, str],
) -> dict[str, Any]:
    """Mirror the public V16 baseline shape while older runtimes are inspected."""
    source = {
        "kind": established_by.get("kind", "trusted_same_window_checkpoint"),
    }
    if established_by.get("id"):
        source["source_id"] = established_by["id"]
    return {
        "root_fingerprint": root_fingerprint(project),
        "coverage_roots": ["."],
        "coverage_complete": True,
        "manifest_sha256": sha256_text(canonical_json(manifest)),
        "inventory_policy_sha256": sha256_text("v16-canonical-project-inventory"),
        "captured_revision": state.get("revision"),
        "component_graph_sha256": sha256_text(
            canonical_json(_component_graph_payload(state))
        ),
        "artifact_registry_sha256": sha256_text(
            canonical_json(_artifact_registry_payload(state))
        ),
        "established_by": source,
        "file_count": len(manifest),
        "unresolved": [],
        "continuity_change_set": {
            "paths": [], "component_ids": [], "facets": [],
            "propagation_complete": True,
        },
    }


def install_trusted_baseline(
    project: Path,
    *,
    roots: list[str] | None = None,
    established_id: str = "fixture-checkpoint",
) -> dict[str, Any]:
    """Install a complete baseline using the runtime's public builder when present."""
    state = read_state(project)
    coverage_roots = roots or ["."]
    state["watch_roots"] = coverage_roots
    manifest = build_workspace_manifest(project, coverage_roots)
    state["workspace_baseline"] = manifest
    established_by = {
        "kind": "trusted_same_window_checkpoint",
        "id": established_id,
    }
    try:
        from assess_recovery import build_workspace_baseline_meta

        meta = build_workspace_baseline_meta(
            project, state, manifest, established_by=established_by
        )
    except (ImportError, TypeError):
        meta = _fallback_baseline_meta(project, state, manifest, established_by)
    state["workspace_baseline_meta"] = meta
    write_state(project, state)
    return state


def prepare_runtime_project(workspace: Path, name: str) -> Path:
    """Create a valid S5 question fixture for an explicitly guarded solver."""
    project = create_project(workspace / name)
    state = read_state(project)
    state["components"]["Q1"]["state"] = "S5"
    state["components"]["Q1"]["status"] = "active"
    state["components"]["Q1"]["invalidated_at_revision"] = None
    write_state(project, state)
    install_trusted_baseline(project)
    return project


def runtime_plan(*, explicit_full: bool = False) -> dict[str, Any]:
    """Return one formal model step with a real high-risk runtime action."""
    request = "完成窗口恢复并精确登记执行后，运行 Q1 模型。"
    facts: dict[str, Any] = {}
    if explicit_full:
        facts["request_explicit_full_recovery"] = True
    return {
        "schema_version": "11.0",
        "plan_id": "v16-recovery-runtime-binding",
        "request": request,
        "window_context": "new_window",
        "steps": [{
            "id": "solve-q1",
            "tier": "G2_CHECKPOINT",
            "mode": "mutate",
            "object": "model",
            "action": "solve",
            "component_id": "Q1",
            "events": ["recovery_assessment", "model_execution"],
            "facts": facts,
            "depends_on": [],
            "change_set": {
                "paths": ["results/q1-runtime.txt"],
                "facets": ["computation"],
                "claim_refs": [],
            },
            "runtime_actions": [{
                "id": "run-q1",
                "kind": "project_model_execution",
                "event": "model_execution",
                "repetition": "first_run",
                "scope": {
                    "kind": "component",
                    "component_ids": ["Q1"],
                    "input_paths": ["data/problem.pdf", "src/q1.py"],
                    "output_paths": ["results/q1-runtime.txt"],
                },
                "command": {
                    "argv": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "Path('results/q1-runtime.txt').write_text('ran', "
                            "encoding='utf-8')"
                        ),
                    ],
                    "cwd": ".",
                },
                "authorization": {
                    "source": "direct_user_request",
                    "request_excerpt": "运行 Q1 模型",
                },
            }],
        }],
    }


def r0_two_stage_runtime_plan() -> dict[str, Any]:
    """Use two declared outputs to test live same-window execution continuity."""
    selected = runtime_plan()
    selected["plan_id"] = "v16-r0-two-stage-runtime"
    selected["request"] = "在同一窗口运行 Q1 模型第一阶段和第二阶段。"
    selected["window_context"] = "same_window"
    step = selected["steps"][0]
    step["change_set"]["paths"] = [
        "results/q1-runtime-a.txt", "results/q1-runtime-b.txt",
    ]
    first = step["runtime_actions"][0]
    first["id"] = "run-q1-a"
    first["scope"]["output_paths"] = ["results/q1-runtime-a.txt"]
    first["command"]["argv"][2] = (
        "from pathlib import Path; "
        "Path('results/q1-runtime-a.txt').write_text('stage-a', encoding='utf-8')"
    )
    first["authorization"]["request_excerpt"] = "运行 Q1 模型第一阶段"
    second = deepcopy(first)
    second["id"] = "run-q1-b"
    second["scope"]["output_paths"] = ["results/q1-runtime-b.txt"]
    second["command"]["argv"][2] = (
        "from pathlib import Path; "
        "Path('results/q1-runtime-b.txt').write_text('stage-b', encoding='utf-8')"
    )
    second["authorization"]["request_excerpt"] = "第二阶段"
    step["runtime_actions"].append(second)
    return selected


def r1_receipt(
    project: Path,
    opened: dict[str, Any],
    recovery_id: str,
) -> dict[str, Any]:
    mode_by_requirement = {
        "content": "content",
        "semantic": "structured_extract",
        "identity": "identity_plus_validation_summary",
        "existence": "missing_review",
    }
    reads: list[dict[str, Any]] = []
    for requirement in opened.get("required_reads", []):
        live = project / requirement["path"]
        exists = live.is_file()
        reads.append({
            "path": requirement["path"],
            "semantic_role": requirement["semantic_role"],
            "read_mode": mode_by_requirement[requirement["required_mode"]],
            "sha256": sha256_file(live) if exists else None,
            "size": live.stat().st_size if exists else None,
            "review_result": "consistent" if exists else "missing",
            "note": "Reviewed against the sealed targeted-recovery snapshot.",
        })
    return {
        "schema_version": "16.0",
        "receipt_type": "r1_targeted_recovery",
        "recovery_id": recovery_id,
        "project_root": str(project.resolve()),
        "read_receipts": reads,
        "changed_paths": opened["assessment"].get("changed_paths", []),
        "affected_components": opened["assessment"].get(
            "affected_components", []
        ),
        "conclusion": {
            "status": "ready",
            "inconsistencies": [],
            "next_legal_action": "Bind the reviewed step to one formal execution.",
        },
    }


def r2_receipt(
    project: Path,
    opened: dict[str, Any],
    recovery_id: str,
    manifest_path: Path,
    counts: dict[str, int],
    *,
    outcome: str,
) -> dict[str, Any]:
    inconsistencies = (
        [] if outcome == "ready"
        else ["A known project gap still blocks model execution."]
    )
    return {
        "schema_version": "16.0",
        "receipt_type": "r2_full_recovery",
        "recovery_id": recovery_id,
        "project_root": str(project.resolve()),
        "full_manifest_path": str(manifest_path.resolve()),
        "full_manifest_sha256": sha256_file(manifest_path),
        "full_manifest_counts": counts,
        "read_receipts": [],
        "changed_paths": opened["assessment"].get("changed_paths", []),
        "affected_components": opened["assessment"].get(
            "affected_components", []
        ),
        "conclusion": {
            "status": outcome,
            "inconsistencies": inconsistencies,
            "next_legal_action": (
                "Resolve the exact bound step after R2 closure."
                if outcome == "ready"
                else "Resolve the recorded gap before any model execution."
            ),
        },
    }


def assessment_text(value: dict[str, Any]) -> str:
    return json.dumps(
        {
            "level": value.get("level"),
            "reasons": value.get("reasons", []),
            "baseline_status": value.get("baseline_status"),
            "baseline_proof": value.get("baseline_proof"),
            "changed_paths": value.get("changed_paths", []),
            "unowned_changes": value.get("unowned_changes", []),
            "ignored_changes": value.get("ignored_changes", []),
            "affected_components": value.get("affected_components", []),
            "closure_proof": value.get("closure_proof"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )[-1400:]


def recovery_level(resolution: dict[str, Any], step_id: str) -> str | None:
    step = next(
        (item for item in resolution.get("steps", []) if item.get("id") == step_id),
        {},
    )
    recovery = step.get("recovery")
    return recovery.get("level") if isinstance(recovery, dict) else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    cases: list[dict[str, str]] = []

    def record(identifier: str, passed: bool, evidence: str) -> None:
        cases.append({
            "id": identifier,
            "status": "pass" if passed else "fail",
            "evidence": evidence[-1800:],
        })

    def exercise(identifier: str, body: Callable[[], tuple[bool, str]]) -> None:
        try:
            passed, evidence = body()
        except Exception as exc:  # keep the release report complete and diagnostic
            passed, evidence = False, f"{type(exc).__name__}:{exc}"
        record(identifier, passed, evidence)

    with tempfile.TemporaryDirectory(prefix="v16-recovery-") as raw:
        workspace = Path(raw)

        def same_window_r0() -> tuple[bool, str]:
            project = create_project(workspace / "r0")
            install_trusted_baseline(project)
            before = read_state(project)
            observed = assess(project, new_window=False, gate="G1")
            after = read_state(project)
            passed = (
                observed.get("level") == "R0_CONTINUE"
                and observed.get("state_valid") is True
                and before.get("revision") == after.get("revision")
                and before.get("recoveries", {}) == after.get("recoveries", {})
            )
            return passed, assessment_text(observed)

        exercise("SCENARIO.V16.RECOVERY.R0.SAME_WINDOW", same_window_r0)

        def clean_new_window_r1() -> tuple[bool, str]:
            project = create_project(workspace / "r1-clean")
            install_trusted_baseline(project)
            observed = assess(project, new_window=True, gate="G1")
            baseline_proof = observed.get("baseline_proof", {})
            passed = (
                observed.get("level") == "R1_TARGETED"
                and observed.get("state_valid") is True
                and not observed.get("changed_paths")
                and (
                    not isinstance(baseline_proof, dict)
                    or baseline_proof.get("valid", True) is True
                )
            )
            return passed, assessment_text(observed)

        exercise("SCENARIO.V16.RECOVERY.R1.CLEAN_NEW_WINDOW", clean_new_window_r1)

        def missing_baseline_r2() -> tuple[bool, str]:
            project = create_project(workspace / "r2-baseline-missing")
            install_trusted_baseline(project)
            state = read_state(project)
            state.pop("workspace_baseline", None)
            state.pop("workspace_baseline_meta", None)
            write_state(project, state)
            observed = assess(project, new_window=True, gate="G1")
            return observed.get("level") == "R2_FULL", assessment_text(observed)

        exercise("SCENARIO.V16.RECOVERY.R2.BASELINE_MISSING", missing_baseline_r2)

        def incomplete_baseline_r2() -> tuple[bool, str]:
            project = create_project(workspace / "r2-baseline-incomplete")
            install_trusted_baseline(project, roots=["src"])
            observed = assess(project, new_window=True, gate="G1")
            return observed.get("level") == "R2_FULL", assessment_text(observed)

        exercise(
            "SCENARIO.V16.RECOVERY.R2.BASELINE_COVERAGE_INCOMPLETE",
            incomplete_baseline_r2,
        )

        def graph_drift_r2() -> tuple[bool, str]:
            project = create_project(workspace / "r2-graph-drift")
            install_trusted_baseline(project)
            state = read_state(project)
            state["components"]["Q2"]["dependencies"] = ["Q1"]
            state["components"]["Q1"]["consumers"] = sorted(
                set(state["components"]["Q1"]["consumers"]) | {"Q2"}
            )
            write_state(project, state)
            observed = assess(project, new_window=True, gate="G1")
            return observed.get("level") == "R2_FULL", assessment_text(observed)

        exercise("SCENARIO.V16.RECOVERY.R2.COMPONENT_GRAPH_DRIFT", graph_drift_r2)

        def relevant_unattributed_r2() -> tuple[bool, str]:
            project = create_project(workspace / "r2-unattributed")
            state = read_state(project)
            target = project / "src/q3.py"
            state["artifacts"]["src/q3.py"] = {
                "sha256": sha256_file(target),
                "size": target.stat().st_size,
                "media_type": "text/x-python",
                "role": "code",
                "class": "code",
                "purpose": "Protected Q3 source used by the recovery boundary scenario.",
                "authorization_basis": "scenario fixture",
                "lifecycle": "milestone",
                "identity_class": "milestone",
                "producer": "Q3",
                "consumers": ["Q1", "Q2"],
                "status": "registered",
                "validated_at": None,
                "validation_evidence_id": None,
                "supersedes": None,
            }
            write_state(project, state)
            install_trusted_baseline(project)
            target.write_text(
                "def pruning_window(): return 'changed outside an authorized ChangeSet'\n",
                encoding="utf-8",
            )
            observed = assess(
                project, new_window=True, gate="G1", scope_paths=["src/q3.py"]
            )
            unowned = observed.get("unowned_changes", [])
            passed = (
                observed.get("level") == "R2_FULL"
                and (not isinstance(unowned, list) or "src/q3.py" in unowned)
            )
            return passed, assessment_text(observed)

        exercise(
            "SCENARIO.V16.RECOVERY.R2.RELEVANT_UNATTRIBUTED_CHANGE",
            relevant_unattributed_r2,
        )

        def explicit_r2_barrier() -> tuple[bool, str]:
            project = create_project(workspace / "r2-explicit")
            unknown = project / "misc/unknown.bin"
            unknown.parent.mkdir(parents=True, exist_ok=True)
            unknown.write_bytes(b"unknown but project-owned recovery fixture")
            install_trusted_baseline(project)
            selected = compatible_plan(
                "reconcile_compatible", "G2_CHECKPOINT", "promote", "evidence_record"
            )
            selected["window_context"] = "new_window"
            selected["steps"][0]["facts"]["request_explicit_full_recovery"] = True
            observed = resolve(selected, project, root)
            step = observed.get("steps", [{}])[0]
            recovery = step.get("recovery", {})
            if not isinstance(recovery, dict):
                return False, json.dumps(
                    {
                        "status": observed.get("status"),
                        "posture": observed.get("recovery_posture"),
                        "step": step,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            required_paths = set(recovery.get("required_paths", []))
            known_project_paths = {
                ".modeling/state.json",
                "data/problem.pdf",
                "misc/unknown.bin",
                "specs/Q1.md",
                "src/q1.py",
            }
            passed = (
                recovery.get("level") == "R2_FULL"
                and recovery.get("execution_boundary", {}).get("barrier_open") is True
                and observed.get("recovery_posture") == "R2_OPEN"
                and not observed.get("action_grants")
                and known_project_paths.issubset(required_paths)
            )
            evidence = json.dumps(
                {
                    "status": observed.get("status"),
                    "posture": observed.get("recovery_posture"),
                    "step_status": step.get("status"),
                    "recovery": recovery,
                    "action_grants": observed.get("action_grants"),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            return passed, evidence

        exercise("SCENARIO.V16.RECOVERY.R2.EXPLICIT_BARRIER", explicit_r2_barrier)

        def explicit_r2_full_roundtrip() -> tuple[bool, str]:
            project = create_project(workspace / "r2-full-roundtrip")
            unknown = project / "misc/unknown.bin"
            unknown.parent.mkdir(parents=True, exist_ok=True)
            unknown.write_bytes(b"unknown whole-project recovery fixture")
            install_trusted_baseline(project)
            selected = compatible_plan(
                "reconcile_compatible", "G2_CHECKPOINT", "promote", "evidence_record"
            )
            selected["window_context"] = "new_window"
            selected["steps"][0]["facts"]["request_explicit_full_recovery"] = True
            selected["steps"][0]["facts"]["window_context"] = "new_window"
            plan_path = workspace / "r2-full-roundtrip-plan.json"
            write_json(plan_path, selected)
            manager = root / "scripts/state_manager.py"
            recovery_id = "REC-V16-EXPLICIT-FULL"
            begin_code, _, begin_log = run(
                manager, "begin-recovery", "--project-root", str(project),
                "--plan", str(plan_path), "--step-id", "reconcile_compatible",
                "--recovery-id", recovery_id,
            )
            if begin_code != 0:
                return False, "begin=" + begin_log
            opened = read_state(project)["recoveries"][recovery_id]
            manifest, counts = complete_full_manifest(project)
            manifest_path = workspace / "r2-full-roundtrip-manifest.json"
            write_json(manifest_path, manifest)
            receipt = {
                "schema_version": "16.0",
                "receipt_type": "r2_full_recovery",
                "recovery_id": recovery_id,
                "project_root": str(project.resolve()),
                "full_manifest_path": str(manifest_path.resolve()),
                "full_manifest_sha256": sha256_file(manifest_path),
                "full_manifest_counts": counts,
                "read_receipts": [],
                "changed_paths": opened["assessment"].get("changed_paths", []),
                "affected_components": opened["assessment"].get(
                    "affected_components", []
                ),
                "conclusion": {
                    "status": "ready",
                    "inconsistencies": [],
                    "next_legal_action": "Resolve the bound step after R2 closure.",
                },
            }
            receipt_path = workspace / "r2-full-roundtrip-receipt.json"
            write_json(receipt_path, receipt)
            close_code, _, close_log = run(
                manager, "close-recovery", "--project-root", str(project),
                "--receipt", str(receipt_path),
            )
            closed_state = read_state(project)
            closed = closed_state.get("recoveries", {}).get(recovery_id, {})
            rerouted = resolve(selected, project, root)
            step = rerouted.get("steps", [{}])[0]
            recovery = step.get("recovery", {})
            passed = (
                close_code == 0
                and closed.get("status") == "closed"
                and closed.get("outcome") == "ready"
                and closed.get("recovery_level") == "R2_FULL"
                and closed.get("full_manifest_counts") == counts
                and isinstance(recovery, dict)
                and recovery.get("level") == "R2_FULL"
                and recovery.get("satisfied_by_recovery_id") == recovery_id
                and recovery.get("execution_boundary", {}).get("barrier_open") is False
                and rerouted.get("recovery_posture") == "R2_CLOSED_READY"
            )
            return passed, json.dumps(
                {
                    "begin": begin_code, "close": close_code,
                    "closed": closed, "rerouted_status": rerouted.get("status"),
                    "posture": rerouted.get("recovery_posture"),
                    "recovery": recovery, "close_log": close_log,
                },
                ensure_ascii=False,
                sort_keys=True,
            )[-1800:]

        exercise(
            "SCENARIO.V16.RECOVERY.R2.FULL_ROUNDTRIP",
            explicit_r2_full_roundtrip,
        )

        def incomplete_r2_read_rejected() -> tuple[bool, str]:
            project = create_project(workspace / "r2-incomplete-read")
            install_trusted_baseline(project)
            selected = compatible_plan(
                "reconcile_compatible", "G2_CHECKPOINT", "promote",
                "evidence_record",
            )
            selected["window_context"] = "new_window"
            selected["steps"][0]["facts"]["request_explicit_full_recovery"] = True
            plan_path = workspace / "r2-incomplete-read-plan.json"
            write_json(plan_path, selected)
            manager = root / "scripts/state_manager.py"
            recovery_id = "REC-V16-INCOMPLETE-FULL"
            begin_code, _, begin_log = run(
                manager, "begin-recovery", "--project-root", str(project),
                "--plan", str(plan_path), "--step-id", "reconcile_compatible",
                "--recovery-id", recovery_id,
            )
            if begin_code != 0:
                return False, "begin=" + begin_log
            opened = read_state(project)["recoveries"][recovery_id]
            manifest, counts = complete_full_manifest(project)
            omitted_path = None
            for item in manifest["files"]:
                if item.get("duplicate_of") is None:
                    omitted_path = item["path"]
                    item["inspection"] = None
                    break
            manifest_path = workspace / "r2-incomplete-read-manifest.json"
            write_json(manifest_path, manifest)
            receipt = r2_receipt(
                project, opened, recovery_id, manifest_path, counts,
                outcome="ready",
            )
            receipt_path = workspace / "r2-incomplete-read-receipt.json"
            write_json(receipt_path, receipt)
            close_code, _, close_log = run(
                manager, "close-recovery", "--project-root", str(project),
                "--receipt", str(receipt_path),
            )
            after = read_state(project)["recoveries"][recovery_id]
            rerouted = resolve(selected, project, root)
            passed = (
                omitted_path is not None
                and close_code != 0
                and after.get("status") == "open"
                and after.get("outcome") == "pending"
                and after.get("full_manifest_sha256") is None
                and rerouted.get("recovery_posture") == "R2_OPEN"
                and not rerouted.get("action_grants")
                and "canonical_inspection_missing" in close_log
            )
            return passed, json.dumps(
                {
                    "begin": begin_code,
                    "close": close_code,
                    "omitted_path": omitted_path,
                    "record": after,
                    "posture": rerouted.get("recovery_posture"),
                    "action_grants": rerouted.get("action_grants"),
                    "close_log": close_log,
                },
                ensure_ascii=False,
                sort_keys=True,
            )[-1800:]

        exercise(
            "SCENARIO.V16.RECOVERY.R2.INCOMPLETE_FULL_READ.REJECTED",
            incomplete_r2_read_rejected,
        )

        def closed_blocked_has_no_runtime_grant() -> tuple[bool, str]:
            project = prepare_runtime_project(workspace, "r2-closed-blocked")
            selected = runtime_plan(explicit_full=True)
            plan_path = workspace / "r2-closed-blocked-plan.json"
            write_json(plan_path, selected)
            manager = root / "scripts/state_manager.py"
            recovery_id = "REC-V16-CLOSED-BLOCKED"
            opened_resolution = resolve(selected, project, root)
            begin_code, _, begin_log = run(
                manager, "begin-recovery", "--project-root", str(project),
                "--plan", str(plan_path), "--step-id", "solve-q1",
                "--recovery-id", recovery_id,
            )
            if begin_code != 0:
                return False, "begin=" + begin_log
            opened = read_state(project)["recoveries"][recovery_id]
            manifest, counts = complete_full_manifest(project)
            manifest_path = workspace / "r2-closed-blocked-manifest.json"
            write_json(manifest_path, manifest)
            receipt = r2_receipt(
                project, opened, recovery_id, manifest_path, counts,
                outcome="blocked",
            )
            receipt_path = workspace / "r2-closed-blocked-receipt.json"
            write_json(receipt_path, receipt)
            close_code, _, close_log = run(
                manager, "close-recovery", "--project-root", str(project),
                "--receipt", str(receipt_path),
            )
            closed = read_state(project)["recoveries"][recovery_id]
            rerouted = resolve(selected, project, root)
            action_code, action_payload, action_log = run(
                root / "scripts/run_authorized_action.py",
                "--plan", str(plan_path), "--project-root", str(project),
                "--step-id", "solve-q1", "--action-id", "run-q1",
                "--root", str(root), "--dry-run",
            )
            step = rerouted.get("steps", [{}])[0]
            recovery = rerouted.get("recovery", {})
            passed = (
                opened_resolution.get("recovery_posture") == "R2_OPEN"
                and not opened_resolution.get("action_grants")
                and close_code == 0
                and closed.get("status") == "closed"
                and closed.get("outcome") == "blocked"
                and rerouted.get("recovery_posture") == "R2_CLOSED_BLOCKED"
                and isinstance(recovery, dict)
                and recovery.get("satisfied_by_recovery_id") == recovery_id
                and recovery.get("closure_outcome") == "blocked"
                and step.get("status") == "blocked"
                and not rerouted.get("action_grants")
                and action_code != 0
                and action_payload.get("status") == "blocked"
                and not (project / "results/q1-runtime.txt").exists()
            )
            return passed, json.dumps(
                {
                    "begin": begin_code,
                    "close": close_code,
                    "closed": closed,
                    "posture": rerouted.get("recovery_posture"),
                    "step": step,
                    "action_grants": rerouted.get("action_grants"),
                    "action_code": action_code,
                    "action_payload": action_payload,
                    "logs": (close_log + action_log)[-800:],
                },
                ensure_ascii=False,
                sort_keys=True,
            )[-1800:]

        exercise(
            "SCENARIO.V16.RECOVERY.R2.CLOSED_BLOCKED.NO_RUNTIME_GRANT",
            closed_blocked_has_no_runtime_grant,
        )

        def r1_runtime_grant_requires_exact_execution() -> tuple[bool, str]:
            project = prepare_runtime_project(workspace, "r1-runtime-binding")
            selected = runtime_plan()
            plan_path = workspace / "r1-runtime-binding-plan.json"
            write_json(plan_path, selected)
            manager = root / "scripts/state_manager.py"
            runner = root / "scripts/run_authorized_action.py"
            recovery_id = "REC-V16-R1-RUNTIME"
            execution_id = "EXEC-V16-R1-RUNTIME"

            initial = resolve(selected, project, root)
            pre_code, pre_payload, pre_log = run(
                runner, "--plan", str(plan_path), "--project-root", str(project),
                "--step-id", "solve-q1", "--action-id", "run-q1",
                "--root", str(root), "--dry-run",
            )
            begin_code, _, begin_log = run(
                manager, "begin-recovery", "--project-root", str(project),
                "--plan", str(plan_path), "--step-id", "solve-q1",
                "--recovery-id", recovery_id,
            )
            if begin_code != 0:
                return False, "begin=" + begin_log
            opened = read_state(project)["recoveries"][recovery_id]
            receipt_path = workspace / "r1-runtime-binding-receipt.json"
            write_json(receipt_path, r1_receipt(project, opened, recovery_id))
            close_code, _, close_log = run(
                manager, "close-recovery", "--project-root", str(project),
                "--receipt", str(receipt_path),
            )
            closed_unbound = resolve(selected, project, root)
            unbound_code, unbound_payload, unbound_log = run(
                runner, "--plan", str(plan_path), "--project-root", str(project),
                "--step-id", "solve-q1", "--action-id", "run-q1",
                "--root", str(root), "--dry-run",
            )
            state = read_state(project)
            checkpoint_code, _, checkpoint_log = run(
                manager, "checkpoint", "--project-root", str(project),
                "--expected-revision", str(state["revision"]), "--gate", "G2",
                "--plan", str(plan_path), "--step-id", "solve-q1",
                "--recovery-id", recovery_id,
            )
            route_code, _, route_log = run(
                manager, "record-route", "--project-root", str(project),
                "--plan", str(plan_path), "--step-id", "solve-q1",
                "--execution-id", execution_id, "--recovery-id", recovery_id,
            )
            bound = resolve(selected, project, root)
            bound_code, bound_payload, bound_log = run(
                runner, "--plan", str(plan_path), "--project-root", str(project),
                "--step-id", "solve-q1", "--action-id", "run-q1",
                "--root", str(root), "--dry-run",
            )
            final_state = read_state(project)
            grant = next(iter(bound.get("action_grants", [])), {})
            bound_recovery = bound.get("recovery", {})
            passed = (
                initial.get("status") == "resolved"
                and recovery_level(initial, "solve-q1") == "R1_TARGETED"
                and not initial.get("action_grants")
                and pre_code != 0
                and pre_payload.get("status") == "blocked"
                and close_code == 0
                and closed_unbound.get("status") == "resolved"
                and not closed_unbound.get("action_grants")
                and unbound_code != 0
                and unbound_payload.get("status") == "blocked"
                and checkpoint_code == 0
                and route_code == 0
                and bound.get("status") == "resolved"
                and isinstance(bound_recovery, dict)
                and bound_recovery.get("closure_outcome") == "ready"
                and bound_recovery.get("satisfied_by_recovery_id") == recovery_id
                and bound_recovery.get("satisfied_by_execution_id") == execution_id
                and grant.get("recovery_id") == recovery_id
                and grant.get("recovery_execution_id") == execution_id
                and isinstance(grant.get("recovery_receipt_sha256"), str)
                and bound_code == 0
                and bound_payload.get("status") == "authorized"
                and final_state["recoveries"][recovery_id].get(
                    "consumed_by_execution"
                ) == execution_id
                and final_state["executions"][execution_id].get("status") == "open"
                and not (project / "results/q1-runtime.txt").exists()
            )
            return passed, json.dumps(
                {
                    "initial": {
                        "status": initial.get("status"),
                        "level": recovery_level(initial, "solve-q1"),
                        "grants": initial.get("action_grants"),
                    },
                    "pre": {"code": pre_code, "payload": pre_payload},
                    "begin": begin_code,
                    "close": close_code,
                    "closed_unbound_grants": closed_unbound.get("action_grants"),
                    "unbound": {"code": unbound_code, "payload": unbound_payload},
                    "checkpoint": checkpoint_code,
                    "route": route_code,
                    "bound_recovery": bound_recovery,
                    "grant": grant,
                    "bound_action": {"code": bound_code, "payload": bound_payload},
                    "logs": (
                        pre_log + close_log + unbound_log + checkpoint_log
                        + route_log + bound_log
                    )[-900:],
                },
                ensure_ascii=False,
                sort_keys=True,
            )[-1800:]

        exercise(
            "SCENARIO.V16.RECOVERY.R1.RUNTIME_GRANT.EXACT_EXECUTION",
            r1_runtime_grant_requires_exact_execution,
        )

        def r0_open_execution_continuity() -> tuple[bool, str]:
            project = prepare_runtime_project(workspace, "r0-open-execution")
            selected = r0_two_stage_runtime_plan()
            plan_path = workspace / "r0-open-execution-plan.json"
            write_json(plan_path, selected)
            manager = root / "scripts/state_manager.py"
            runner = root / "scripts/run_authorized_action.py"
            execution_id = "EXEC-V16-R0-TWO-STAGE"
            initial = resolve(selected, project, root)
            state = read_state(project)
            checkpoint_code, _, checkpoint_log = run(
                manager, "checkpoint", "--project-root", str(project),
                "--expected-revision", str(state["revision"]), "--gate", "G2",
                "--plan", str(plan_path), "--step-id", "solve-q1",
            )
            route_code, _, route_log = run(
                manager, "record-route", "--project-root", str(project),
                "--plan", str(plan_path), "--step-id", "solve-q1",
                "--execution-id", execution_id,
            )
            opened = resolve(selected, project, root)
            first_code, first_payload, first_log = run(
                runner, "--plan", str(plan_path), "--project-root", str(project),
                "--step-id", "solve-q1", "--action-id", "run-q1-a",
                "--root", str(root),
            )
            after_first = resolve(selected, project, root)
            second_code, second_payload, second_log = run(
                runner, "--plan", str(plan_path), "--project-root", str(project),
                "--step-id", "solve-q1", "--action-id", "run-q1-b",
                "--root", str(root), "--dry-run",
            )
            rogue = project / "misc/unsealed-runtime-delta.txt"
            rogue.parent.mkdir(parents=True, exist_ok=True)
            rogue.write_text(
                "This live delta is outside the exact open execution ChangeSet.\n",
                encoding="utf-8",
            )
            escaped = resolve(selected, project, root)
            escaped_code, escaped_payload, escaped_log = run(
                runner, "--plan", str(plan_path), "--project-root", str(project),
                "--step-id", "solve-q1", "--action-id", "run-q1-b",
                "--root", str(root), "--dry-run",
            )
            opened_grants = {
                item.get("runtime_action_id")
                for item in opened.get("action_grants", [])
                if isinstance(item, dict)
            }
            after_first_grants = {
                item.get("runtime_action_id")
                for item in after_first.get("action_grants", [])
                if isinstance(item, dict)
            }
            passed = (
                recovery_level(initial, "solve-q1") == "R0_CONTINUE"
                and checkpoint_code == 0
                and route_code == 0
                and recovery_level(opened, "solve-q1") == "R0_CONTINUE"
                and {"run-q1-a", "run-q1-b"}.issubset(opened_grants)
                and first_code == 0
                and first_payload.get("status") == "pass"
                and (project / "results/q1-runtime-a.txt").read_text(
                    encoding="utf-8"
                ) == "stage-a"
                and recovery_level(after_first, "solve-q1") == "R0_CONTINUE"
                and "run-q1-b" in after_first_grants
                and second_code == 0
                and second_payload.get("status") == "authorized"
                and recovery_level(escaped, "solve-q1") == "R2_FULL"
                and escaped.get("recovery_posture") == "R2_OPEN"
                and not escaped.get("action_grants")
                and escaped_code != 0
                and escaped_payload.get("status") == "blocked"
            )
            return passed, json.dumps(
                {
                    "initial_level": recovery_level(initial, "solve-q1"),
                    "checkpoint": checkpoint_code,
                    "route": route_code,
                    "opened_level": recovery_level(opened, "solve-q1"),
                    "opened_grants": sorted(opened_grants),
                    "first": {"code": first_code, "payload": first_payload},
                    "after_first_level": recovery_level(after_first, "solve-q1"),
                    "after_first_grants": sorted(after_first_grants),
                    "second": {"code": second_code, "payload": second_payload},
                    "escaped_level": recovery_level(escaped, "solve-q1"),
                    "escaped_posture": escaped.get("recovery_posture"),
                    "escaped_grants": escaped.get("action_grants"),
                    "escaped_action": {
                        "code": escaped_code, "payload": escaped_payload,
                    },
                    "logs": (
                        checkpoint_log + route_log + first_log + second_log
                        + escaped_log
                    )[-900:],
                },
                ensure_ascii=False,
                sort_keys=True,
            )[-1800:]

        exercise(
            "SCENARIO.V16.RECOVERY.R0.OPEN_EXECUTION_CONTINUITY",
            r0_open_execution_continuity,
        )

        def r1_scope_escape_escalates() -> tuple[bool, str]:
            project = create_project(workspace / "r1-escalates")
            trusted = install_trusted_baseline(project)
            selected = compatible_plan(
                "reconcile_compatible", "G2_CHECKPOINT", "promote", "evidence_record"
            )
            selected["window_context"] = "new_window"
            selected["steps"][0]["facts"]["window_context"] = "new_window"
            plan_path = workspace / "r1-escalates-plan.json"
            write_json(plan_path, selected)
            manager = root / "scripts/state_manager.py"
            recovery_id = "REC-V16-R1-ESCAPE"
            begin_code, _, begin_log = run(
                manager, "begin-recovery", "--project-root", str(project),
                "--plan", str(plan_path), "--step-id", "reconcile_compatible",
                "--recovery-id", recovery_id,
            )
            if begin_code != 0:
                return False, "begin=" + begin_log
            opened = read_state(project)["recoveries"][recovery_id]
            mode_by_requirement = {
                "content": "content",
                "semantic": "structured_extract",
                "identity": "identity_plus_validation_summary",
                "existence": "missing_review",
            }
            reads: list[dict[str, Any]] = []
            for requirement in opened.get("required_reads", []):
                live = project / requirement["path"]
                exists = live.is_file()
                reads.append({
                    "path": requirement["path"],
                    "semantic_role": requirement["semantic_role"],
                    "read_mode": mode_by_requirement[requirement["required_mode"]],
                    "sha256": sha256_file(live) if exists else None,
                    "size": live.stat().st_size if exists else None,
                    "review_result": "consistent" if exists else "missing",
                    "note": "Reviewed against the sealed targeted-recovery snapshot.",
                })
            receipt = {
                "schema_version": "16.0",
                "receipt_type": "r1_targeted_recovery",
                "recovery_id": recovery_id,
                "project_root": str(project.resolve()),
                "read_receipts": reads,
                "changed_paths": opened["assessment"].get("changed_paths", []),
                "affected_components": opened["assessment"].get(
                    "affected_components", []
                ),
                "conclusion": {
                    "status": "ready",
                    "inconsistencies": [],
                    "next_legal_action": "Run the bound checkpoint.",
                },
            }
            receipt_path = workspace / "r1-escalates-receipt.json"
            write_json(receipt_path, receipt)
            escaped = project / "src/q3/new_unsealed_consumer.py"
            escaped.parent.mkdir(parents=True, exist_ok=True)
            escaped.write_text(
                "# Relevant source discovered outside the sealed R1 closure.\n",
                encoding="utf-8",
            )
            close_code, _, close_log = run(
                manager, "close-recovery", "--project-root", str(project),
                "--receipt", str(receipt_path),
            )
            escalated_state = read_state(project)
            record = escalated_state.get("recoveries", {}).get(recovery_id, {})
            escalation_history = record.get("escalation_history", [])
            passed = (
                close_code == 0
                and len(escalated_state.get("recoveries", {})) == 1
                and record.get("status") == "open"
                and record.get("initial_recovery_level") == "R1_TARGETED"
                and record.get("recovery_level") == "R2_FULL"
                and record.get("escalated_from") == "R1_TARGETED"
                and isinstance(escalation_history, list)
                and bool(escalation_history)
                and record.get("baseline_revision") is None
                and escalated_state.get("workspace_baseline")
                == trusted.get("workspace_baseline")
                and any(
                    item.get("event") == "recovery_escalated"
                    and item.get("subject") == recovery_id
                    for item in escalated_state.get("history", [])
                )
            )
            return passed, json.dumps(
                {
                    "begin": begin_code, "close": close_code,
                    "record": record, "close_log": close_log,
                },
                ensure_ascii=False,
                sort_keys=True,
            )[-1800:]

        exercise(
            "SCENARIO.V16.RECOVERY.R1.ESCALATES_TO_R2",
            r1_scope_escape_escalates,
        )

        def cache_is_ignored() -> tuple[bool, str]:
            project = create_project(workspace / "cache")
            install_trusted_baseline(project)
            cache = project / "src/__pycache__/q3.cpython-313.pyc"
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(b"disposable bytecode cache")
            pytest_cache = project / ".pytest_cache/v/cache/nodeids"
            pytest_cache.parent.mkdir(parents=True, exist_ok=True)
            pytest_cache.write_text("[]\n", encoding="utf-8")
            same = assess(project, new_window=False, gate="G1")
            fresh = assess(project, new_window=True, gate="G1")
            changed = set(same.get("changed_paths", [])) | set(
                fresh.get("changed_paths", [])
            )
            passed = (
                same.get("level") == "R0_CONTINUE"
                and fresh.get("level") == "R1_TARGETED"
                and not any("__pycache__" in item or ".pytest_cache" in item for item in changed)
            )
            return passed, "same=" + assessment_text(same) + ";new=" + assessment_text(fresh)

        exercise("BEH.V16.RECOVERY.TRANSIENT_CACHE_IGNORED", cache_is_ignored)

        def q3_same_window() -> tuple[bool, str]:
            project = create_project(workspace / "q3-same")
            install_trusted_baseline(project)
            selected = compatible_plan(
                "reconcile_compatible", "G2_CHECKPOINT", "promote", "evidence_record"
            )
            selected["window_context"] = "same_window"
            before = read_state(project)
            observed = resolve(selected, project, root)
            after = read_state(project)
            step = observed.get("steps", [{}])[0]
            passed = (
                observed.get("status") == "resolved"
                and step.get("component_ids") == ["Q1", "Q2"]
                and recovery_level(observed, "reconcile_compatible") == "R0_CONTINUE"
                and step.get("change_set") == selected["steps"][0]["change_set"]
                and before.get("revision") == after.get("revision")
                and before.get("recoveries", {}) == after.get("recoveries", {})
            )
            return passed, json.dumps(step, ensure_ascii=False, sort_keys=True)[-1600:]

        exercise(
            "SCENARIO.V16.RECOVERY.Q3_TO_Q1_Q2.SAME_WINDOW",
            q3_same_window,
        )

        def q3_new_window() -> tuple[bool, str]:
            project = create_project(workspace / "q3-new")
            install_trusted_baseline(project)
            selected = compatible_plan(
                "reconcile_compatible", "G2_CHECKPOINT", "promote", "evidence_record"
            )
            selected["window_context"] = "new_window"
            observed = resolve(selected, project, root)
            step = observed.get("steps", [{}])[0]
            reads: list[tuple[str, str]] = []
            if isinstance(step.get("recovery"), dict):
                state = read_state(project)
                reads = [
                    (item["path"], item["required_mode"])
                    for item in required_recovery_reads(
                        project, state, step, step["recovery"]
                    )
                ]
            required = {
                ("specs/Q1.md", "semantic"),
                ("specs/Q2.md", "semantic"),
                ("specs/Q3.md", "semantic"),
                ("src/q3.py", "semantic"),
                ("results/q3-e1.txt", "semantic"),
                ("results/q3-e2.txt", "semantic"),
            }
            passed = (
                observed.get("status") == "resolved"
                and step.get("component_ids") == ["Q1", "Q2"]
                and recovery_level(observed, "reconcile_compatible") == "R1_TARGETED"
                and required.issubset(set(reads))
            )
            return passed, json.dumps(
                {"step": step, "reads": reads}, ensure_ascii=False, sort_keys=True
            )[-1800:]

        exercise(
            "SCENARIO.V16.RECOVERY.Q3_TO_Q1_Q2.NEW_WINDOW",
            q3_new_window,
        )

    report = {
        "schema_version": "16.0",
        "driver": "run_v16_recovery_scenarios.py",
        "status": "pass" if all(item["status"] == "pass" for item in cases) else "fail",
        "passed": sum(item["status"] == "pass" for item in cases),
        "total": len(cases),
        "cases": cases,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
