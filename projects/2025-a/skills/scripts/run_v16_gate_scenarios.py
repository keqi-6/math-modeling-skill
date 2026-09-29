#!/usr/bin/env python3
"""Exercise the V16 compatible-change gate against disposable projects."""

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
from state_v11 import evidence_binding_hash, validate_state_semantics
from validate_receipt import checkpoint_pair_hash


PREFIX_LEVELS = [
    "scope", "problem_definition", "evidence_plan", "candidate_set",
    "model_spec", "selection_rationale",
]
TAIL_LEVELS = [
    "implementation_ref", "E1_IMPLEMENTATION", "E2_NUMERICAL",
    "E3_STRUCTURAL", "E4_REALITY",
]


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
    return process.returncode, payload, (process.stderr + process.stdout)[-1200:]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def observation(component_id: str, identifier: str, level: str, revision: int = 1) -> dict[str, Any]:
    refs: list[dict[str, str]] = []
    claims = [f"claim:{component_id}:{level}"]
    return {
        "id": identifier, "level": level, "status": "pass", "kind": "observation",
        "locator": {
            "subject": component_id,
            "method": "disposable independent scenario",
            "value": "verified",
        },
        "claim": f"{level} is current for {component_id}.",
        "observed_at": "2026-08-28T00:00:00Z", "producer": "v16-scenario",
        "subject_id": component_id, "input_refs": refs, "claim_refs": claims,
        "binding_hash": evidence_binding_hash(component_id, level, refs, claims),
        "recorded_revision": revision,
    }


def file_record(
    project: Path, component_id: str, identifier: str, level: str, relative: str,
) -> dict[str, Any]:
    refs: list[dict[str, str]] = []
    claims = [f"claim:{component_id}:{level}:v2"]
    return {
        "id": identifier, "level": level, "status": "pass", "kind": "file",
        "locator": {"path": relative, "sha256": sha256_file(project / relative)},
        "claim": f"The compatible {level} identity is current for {component_id}.",
        "observed_at": "2026-08-28T01:00:00Z", "producer": "v16-scenario",
        "subject_id": component_id, "input_refs": refs, "claim_refs": claims,
        "binding_hash": evidence_binding_hash(component_id, level, refs, claims),
    }


def command_record(
    project: Path, component_id: str, identifier: str, level: str, relative: str,
) -> dict[str, Any]:
    refs: list[dict[str, str]] = []
    claims = [f"claim:{component_id}:{level}:v2"]
    return {
        "id": identifier, "level": level, "status": "pass", "kind": "command",
        "locator": {
            "command_hash": sha256_text(f"verify:{component_id}:{level}"),
            "exit_code": 0, "output_ref": relative,
            "output_sha256": sha256_file(project / relative),
        },
        "claim": f"The compatible {level} check passed for {component_id}.",
        "observed_at": "2026-08-28T01:00:00Z", "producer": "v16-scenario",
        "subject_id": component_id, "input_refs": refs, "claim_refs": claims,
        "binding_hash": evidence_binding_hash(component_id, level, refs, claims),
    }


def create_project(root: Path) -> Path:
    project = root / "project"
    for relative, content in {
        "src/q1.py": "def solve(): return 1  # baseline exhaustive search\n",
        "src/q2.py": "def solve(): return 2  # baseline exhaustive search\n",
        "src/q3.py": "def pruning_window(): return True\n",
        "results/q1-e1.txt": "implementation verification pass\n",
        "results/q1-e2.txt": "numerical equivalence pass\n",
        "results/q2-e1.txt": "implementation verification pass\n",
        "results/q2-e2.txt": "numerical equivalence pass\n",
        "results/q3-e1.txt": "source implementation verification pass\n",
        "results/q3-e2.txt": "source numerical equivalence pass\n",
        "specs/Q1.md": "Q1 mathematical specification\n",
        "specs/Q2.md": "Q2 mathematical specification\n",
        "specs/Q3.md": "Q3 mathematical specification\n",
        "data/problem.pdf": "official problem identity\n",
    }.items():
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    timestamp = "2026-08-28T00:00:00Z"
    components: dict[str, Any] = {}
    for component_id in ("Q1", "Q2", "Q3"):
        records = []
        for level in PREFIX_LEVELS + TAIL_LEVELS:
            record = observation(component_id, f"{component_id}-{level}-v1", level)
            if level == "model_spec":
                relative = f"specs/{component_id}.md"
                record = file_record(project, component_id, record["id"], level, relative)
                record["recorded_revision"] = 1
            elif level == "implementation_ref":
                relative = f"src/{component_id.lower()}.py"
                record = file_record(project, component_id, record["id"], level, relative)
                record["recorded_revision"] = 1
            elif level in {"E1_IMPLEMENTATION", "E2_NUMERICAL"}:
                suffix = "e1" if level == "E1_IMPLEMENTATION" else "e2"
                relative = f"results/{component_id.lower()}-{suffix}.txt"
                record = file_record(project, component_id, record["id"], level, relative)
                record["recorded_revision"] = 1
            elif level in {
                "E3_STRUCTURAL", "E4_REALITY",
            }:
                relative = f"evidence/{component_id}-{level}.txt"
                evidence_path = project / relative
                evidence_path.parent.mkdir(parents=True, exist_ok=True)
                evidence_path.write_text(f"baseline {component_id} {level} pass\n", encoding="utf-8")
                record = file_record(project, component_id, record["id"], level, relative)
                record["recorded_revision"] = 1
            records.append(record)
        components[component_id] = {
            "type": "question", "state": "S7", "status": "closed",
            "dependencies": ["Q1", "Q2"] if component_id == "Q3" else [],
            "consumers": ["Q3"] if component_id in {"Q1", "Q2"} else [],
            "evidence": records, "decisions": [], "invalidated_at_revision": None,
            "updated_at": timestamp,
        }
    official = project / "data/problem.pdf"
    state = {
        "schema_version": "11.0", "revision": 1,
        "project": {
            "id": "V16-DEMO", "state": "P0",
            "required_components": ["Q1", "Q2", "Q3"],
            "created_at": timestamp, "updated_at": timestamp,
        },
        "components": components,
        "artifacts": {
            "data/problem.pdf": {
                "sha256": sha256_file(official), "size": official.stat().st_size,
                "media_type": "application/pdf", "role": "official_input", "class": "source",
                "purpose": "Official problem identity for the disposable scenario.",
                "authorization_basis": "scenario fixture", "lifecycle": "milestone",
                "identity_class": "frozen", "producer": "V16-DEMO",
                "consumers": ["Q1", "Q2", "Q3"], "status": "registered",
                "validated_at": None, "validation_evidence_id": None, "supersedes": None,
            }
        },
        "open_decisions": [], "next_actions": [], "recoveries": {},
        "watch_roots": ["."],
        "workspace_baseline": {},
        "history": [{
            "revision": 1, "event": "project_initialized", "at": timestamp,
            "subject": "V16-DEMO", "details": {"gate": "G1"},
        }],
    }
    state["workspace_baseline"] = build_workspace_manifest(project, ["."])
    state["workspace_baseline_meta"] = make_baseline_meta(
        project,
        state,
        state["workspace_baseline"],
        captured_revision=1,
        established_kind="project_init",
        source_id="V16-DEMO",
        coverage_roots=["."],
        coverage_complete=True,
    )
    errors = validate_state_semantics(state, project, check_files=True)
    if errors:
        raise RuntimeError("invalid disposable state: " + ";".join(errors))
    write_json(project / ".modeling/state.json", state)
    return project


def seal_fixture_baseline(project: Path, source_id: str) -> None:
    """Declare completed fixture setup as the trusted pre-scenario checkpoint."""
    state_path = project / ".modeling/state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
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
    write_json(state_path, state)


def compatible_change() -> dict[str, Any]:
    return {
        "id": "CC-Q3-Q12", "classification": "compatible_implementation_change",
        "source_component_id": "Q3",
        "effects": [
            {
                "component_id": component_id, "role": "implementation_target",
                "changed_facets": ["implementation", "performance"],
                "affected_levels": [
                    "implementation_ref", "E1_IMPLEMENTATION", "E2_NUMERICAL",
                ],
            }
            for component_id in ("Q1", "Q2")
        ],
        "fallback": "reopen_at_earliest_changed_layer",
    }


def plan(
    action: str,
    tier: str,
    mode: str,
    event: str,
    *,
    closure_attested: bool = True,
) -> dict[str, Any]:
    events = [event]
    if tier == "G2_CHECKPOINT":
        events.insert(0, "recovery_assessment")
    return {
        "schema_version": "11.0", "plan_id": f"plan-{action}",
        "request": "把 Q3 已验证的实现等价剪枝回传到 Q1/Q2，并一次完成闭包验收。",
        "window_context": "same_window",
        "steps": [{
            "id": action, "tier": tier, "mode": mode, "object": "project",
            "action": action, "component_id": None, "events": events,
            "facts": {
                "compatible_change": compatible_change(),
                **(
                    {
                        "change_set_complete": True,
                        "propagation_complete": True,
                    }
                    if closure_attested else {}
                ),
            },
            "depends_on": [],
            "change_set": {
                "paths": [
                    "results/q1-e1.txt", "results/q1-e2.txt",
                    "results/q2-e1.txt", "results/q2-e2.txt",
                    "src/q1.py", "src/q2.py",
                ],
                "facets": ["implementation", "performance"], "claim_refs": [],
            },
        }],
    }


def bundle(project: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for component_id, lower in (("Q1", "q1"), ("Q2", "q2")):
        for record in (
            file_record(project, component_id, f"{component_id}-implementation-v2", "implementation_ref", f"src/{lower}.py"),
            command_record(project, component_id, f"{component_id}-e1-v2", "E1_IMPLEMENTATION", f"results/{lower}-e1.txt"),
            command_record(project, component_id, f"{component_id}-e2-v2", "E2_NUMERICAL", f"results/{lower}-e2.txt"),
        ):
            records.append({"component_id": component_id, "evidence": record})
    return {
        "schema_version": "16.0", "change_id": "CC-Q3-Q12",
        "records": records, "artifact_updates": [],
    }


def validation(component_id: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record["id"], "component_id": component_id, "level": record["level"],
        "status": "pass",
        "evidence_ref": f"state:components/{component_id}/evidence/{record['id']}",
        "input_refs": record["input_refs"], "claim_refs": record["claim_refs"],
        "binding_hash": record["binding_hash"],
    }


def begin_formal(
    manager: Path, skill_root: Path, project: Path, workspace: Path,
    selected_plan: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path, list[str]]:
    semantic_plan = selected_plan or plan(
        "reconcile_compatible", "G2_CHECKPOINT", "promote", "evidence_record",
    )
    plan_path = workspace / "plan.json"
    write_json(plan_path, semantic_plan)
    resolution = resolve(semantic_plan, project, skill_root)
    logs: list[str] = []
    state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
    code, _, log = run(
        manager, "checkpoint", "--project-root", str(project),
        "--expected-revision", str(state["revision"]), "--gate", "G2",
        "--plan", str(plan_path), "--step-id", "reconcile_compatible",
    )
    logs.append(f"checkpoint={code}:{log}")
    code, _, log = run(
        manager, "record-route", "--project-root", str(project),
        "--plan", str(plan_path), "--step-id", "reconcile_compatible",
        "--execution-id", "exec-compatible",
    )
    logs.append(f"start={code}:{log}")
    return semantic_plan, resolution, plan_path, logs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    skill_root = args.root.resolve()
    manager = skill_root / "scripts/state_manager.py"
    cases: list[dict[str, str]] = []

    def record(identifier: str, passed: bool, evidence: str) -> None:
        cases.append({"id": identifier, "status": "pass" if passed else "fail", "evidence": evidence})

    with tempfile.TemporaryDirectory(prefix="v16-gate-") as raw:
        workspace = Path(raw)
        project = create_project(workspace / "positive")

        g1 = plan(
            "propagate_compatible", "G1_WORKING", "mutate",
            "model_implementation",
        )
        g1_resolution = resolve(g1, project, skill_root)
        record(
            "BEH.V16.COMPATIBLE.G1.ONE_CHANGESET",
            g1_resolution.get("status") == "resolved"
            and g1_resolution["steps"][0].get("component_ids") == ["Q1", "Q2"]
            and json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))["revision"] == 1,
            json.dumps(g1_resolution.get("steps", []), ensure_ascii=False)[-800:],
        )

        missing_closure_project = create_project(workspace / "missing-closure")
        (missing_closure_project / "src/q1.py").write_text(
            "def solve(): return 1  # declared delta without closure proofs\n",
            encoding="utf-8",
        )
        missing_closure = plan(
            "reconcile_compatible", "G2_CHECKPOINT", "promote",
            "evidence_record", closure_attested=False,
        )
        missing_closure_result = resolve(
            missing_closure, missing_closure_project, skill_root
        )
        missing_closure_recovery = missing_closure_result.get("recovery", {})
        record(
            "SCENARIO.V16.COMPATIBLE.MISSING_R0_ATTESTATION.R1",
            isinstance(missing_closure_recovery, dict)
            and missing_closure_recovery.get("level") == "R1_TARGETED"
            and missing_closure_result.get("recovery_posture") == "NORMAL"
            and not missing_closure_result.get("action_grants")
            and "r1_proofs_complete" in missing_closure_recovery.get(
                "reasons", []
            ),
            json.dumps(
                {
                    "status": missing_closure_result.get("status"),
                    "posture": missing_closure_result.get("recovery_posture"),
                    "recovery": missing_closure_recovery,
                },
                ensure_ascii=False,
                sort_keys=True,
            )[-1000:],
        )

        mixed = {
            **deepcopy(g1), "plan_id": "mixed-compatible",
            "steps": [
                deepcopy(g1["steps"][0]),
                {
                    **deepcopy(plan(
                        "reconcile_compatible", "G2_CHECKPOINT", "promote",
                        "evidence_record",
                    )["steps"][0]),
                    "depends_on": ["propagate_compatible"],
                },
            ],
        }
        mixed_resolution = resolve(mixed, project, skill_root)
        record(
            "BEH.V16.COMPATIBLE.MIXED.G1_G2",
            mixed_resolution.get("status") == "resolved"
            and mixed_resolution.get("route_ids") == [
                "RT.PROJECT.COMPATIBLE_CHANGE", "RT.PROJECT.COMPATIBLE_CHANGE",
            ],
            json.dumps(mixed_resolution.get("steps", []), ensure_ascii=False)[-1000:],
        )

        bad_plan = deepcopy(g1)
        bad_plan["steps"][0]["facts"]["compatible_change"]["effects"][0]["affected_levels"].append("model_spec")
        bad_resolution = resolve(bad_plan, project, skill_root)
        record(
            "BEH.V16.COMPATIBLE.MODEL_CONTRACT.REJECTED",
            bad_resolution.get("status") == "blocked"
            and "model_spec" in json.dumps(bad_resolution.get("errors", [])),
            json.dumps(bad_resolution, ensure_ascii=False)[-800:],
        )

        facet_smuggle = deepcopy(g1)
        facet_smuggle["steps"][0]["change_set"]["facets"].append("model_spec")
        facet_resolution = resolve(facet_smuggle, project, skill_root)
        record(
            "BEH.V16.COMPATIBLE.FACET_SMUGGLE.REJECTED",
            facet_resolution.get("status") == "blocked"
            and "compatible_change_changeset_facet_mismatch" in json.dumps(
                facet_resolution, ensure_ascii=False
            ),
            json.dumps(facet_resolution, ensure_ascii=False)[-800:],
        )

        # The G1 implementation delta is real; G2 below only reconciles its
        # multi-question evidence and identities.
        (project / "src/q1.py").write_text(
            "def solve(): return 1  # compatible time-window pruning\n",
            encoding="utf-8",
        )
        (project / "src/q2.py").write_text(
            "def solve(): return 2  # compatible time-window pruning\n",
            encoding="utf-8",
        )
        for relative, content in {
            "results/q1-e1.txt": "new pruning implementation verification pass\n",
            "results/q1-e2.txt": "new pruning numerical equivalence pass\n",
            "results/q2-e1.txt": "new pruning implementation verification pass\n",
            "results/q2-e2.txt": "new pruning numerical equivalence pass\n",
        }.items():
            (project / relative).write_text(content, encoding="utf-8")

        semantic_plan, resolution, _, logs = begin_formal(
            manager, skill_root, project, workspace / "positive",
        )
        bundle_value = bundle(project)
        bundle_path = workspace / "positive/bundle.json"
        write_json(bundle_path, bundle_value)
        reconcile_code, _, reconcile_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(project),
            "--execution-id", "exec-compatible", "--bundle", str(bundle_path),
        )
        state = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        installed = {
            item["id"]: item
            for component in state["components"].values()
            for item in component["evidence"]
        }
        validations = [
            validation(item["component_id"], installed[item["evidence"]["id"]])
            for item in bundle_value["records"]
        ]
        execution = state["executions"]["exec-compatible"]
        step = resolution["steps"][0]
        receipt = {
            "receipt_type": "end", "schema_version": "11.0",
            "request": semantic_plan["request"], "request_hash": sha256_text(semantic_plan["request"]),
            "semantic_plan": semantic_plan, "plan_hash": sha256_text(canonical_json(semantic_plan)),
            "step_id": step["id"], "execution_id": "exec-compatible",
            "pair_hash": checkpoint_pair_hash(execution), "project_root": str(project.resolve()),
            "tier": step["tier"], "mode": step["mode"], "route_ids": [step["route_id"]],
            "rule_ids": step["rule_ids"], "component_ids": step["component_ids"],
            "before_revision": execution["start_revision"], "after_revision": state["revision"],
            "change_set": step["change_set"], "changed_identities": [],
            "validations": validations, "state_transitions": [], "open_issues": [],
        }
        receipt_path = workspace / "positive/receipt.json"
        write_json(receipt_path, receipt)
        close_code, _, close_log = run(
            manager, "close-execution", "--project-root", str(project),
            "--receipt", str(receipt_path),
        )
        closed = json.loads((project / ".modeling/state.json").read_text(encoding="utf-8"))
        tail_events = [entry["event"] for entry in closed["history"][-4:]]
        record(
            "SCENARIO.V16.COMPATIBLE.ATOMIC_RECONCILIATION",
            reconcile_code == 0 and close_code == 0
            and tail_events == [
                "identity_checkpoint", "execution_started",
                "compatible_change_reconciled", "execution_closed",
            ]
            and all(closed["components"][item]["state"] == "S7" for item in ("Q1", "Q2", "Q3"))
            and all(closed["components"][item]["status"] == "closed" for item in ("Q1", "Q2", "Q3")),
            f"events={tail_events};logs={logs};reconcile={reconcile_log};close={close_log}",
        )

        negative_project = create_project(workspace / "negative")
        _, _, _, negative_logs = begin_formal(
            manager, skill_root, negative_project, workspace / "negative",
        )
        incomplete = bundle(negative_project)
        incomplete["records"] = [
            item for item in incomplete["records"]
            if not (
                item["component_id"] == "Q2"
                and item["evidence"]["level"] == "E2_NUMERICAL"
            )
        ]
        incomplete_path = workspace / "negative/incomplete.json"
        write_json(incomplete_path, incomplete)
        before = json.loads((negative_project / ".modeling/state.json").read_text(encoding="utf-8"))["revision"]
        negative_code, _, negative_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(negative_project),
            "--execution-id", "exec-compatible", "--bundle", str(incomplete_path),
        )
        after_state = json.loads((negative_project / ".modeling/state.json").read_text(encoding="utf-8"))
        record(
            "SCENARIO.V16.COMPATIBLE.MISSING_EVIDENCE.NO_PARTIAL_COMMIT",
            negative_code != 0 and after_state["revision"] == before
            and not any(entry["event"] == "compatible_change_reconciled" for entry in after_state["history"]),
            f"logs={negative_logs};error={negative_log}",
        )

        prefix_project = create_project(workspace / "prefix-negative")
        (prefix_project / "specs/Q1.md").write_text(
            "Q1 mathematical specification changed constraints\n", encoding="utf-8",
        )
        seal_fixture_baseline(prefix_project, "prefix-negative-fixture")
        _, _, _, prefix_logs = begin_formal(
            manager, skill_root, prefix_project, workspace / "prefix-negative",
        )
        prefix_bundle_path = workspace / "prefix-negative/bundle.json"
        write_json(prefix_bundle_path, bundle(prefix_project))
        prefix_before = json.loads(
            (prefix_project / ".modeling/state.json").read_text(encoding="utf-8")
        )["revision"]
        prefix_code, _, prefix_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(prefix_project),
            "--execution-id", "exec-compatible", "--bundle", str(prefix_bundle_path),
        )
        prefix_after = json.loads(
            (prefix_project / ".modeling/state.json").read_text(encoding="utf-8")
        )
        prefix_spec = next(
            item for item in prefix_after["components"]["Q1"]["evidence"]
            if item["level"] == "model_spec"
        )
        record(
            "SCENARIO.V16.COMPATIBLE.PREFIX_IDENTITY_CHANGE.REJECTED",
            prefix_code != 0 and prefix_after["revision"] == prefix_before
            and prefix_spec["status"] == "pass"
            and "frozen contract identity changed" in prefix_log,
            f"logs={prefix_logs};error={prefix_log}",
        )

        omitted_project = create_project(workspace / "omitted-artifact-negative")
        omitted_state_path = omitted_project / ".modeling/state.json"
        omitted_state = json.loads(omitted_state_path.read_text(encoding="utf-8"))
        omitted_old_hash = sha256_file(omitted_project / "src/q1.py")
        omitted_state["artifacts"]["src/q1.py"] = {
            "sha256": omitted_old_hash,
            "size": (omitted_project / "src/q1.py").stat().st_size,
            "media_type": "text/x-python", "role": "code", "class": "code",
            "purpose": "Milestone Q1 implementation consumed directly by Q3.",
            "authorization_basis": "scenario fixture", "lifecycle": "milestone",
            "identity_class": "milestone", "producer": "Q1", "consumers": ["Q3"],
            "status": "registered", "validated_at": None,
            "validation_evidence_id": None, "supersedes": None,
        }
        omitted_q3_e1 = next(
            item for item in omitted_state["components"]["Q3"]["evidence"]
            if item["level"] == "E1_IMPLEMENTATION"
        )
        omitted_q3_e1["input_refs"] = [{
            "kind": "artifact", "id": "src/q1.py", "identity": omitted_old_hash,
            "facet": "content",
        }]
        omitted_q3_e1["binding_hash"] = evidence_binding_hash(
            "Q3", omitted_q3_e1["level"], omitted_q3_e1["input_refs"],
            omitted_q3_e1["claim_refs"],
        )
        write_json(omitted_state_path, omitted_state)
        seal_fixture_baseline(omitted_project, "omitted-artifact-fixture")
        _, _, _, omitted_logs = begin_formal(
            manager, skill_root, omitted_project, workspace / "omitted-artifact-negative",
        )
        (omitted_project / "src/q1.py").write_text(
            "def solve(): return 1  # unreported identity delta\n", encoding="utf-8",
        )
        omitted_bundle_path = workspace / "omitted-artifact-negative/bundle.json"
        write_json(omitted_bundle_path, bundle(omitted_project))
        omitted_before = json.loads(omitted_state_path.read_text(encoding="utf-8"))["revision"]
        omitted_code, _, omitted_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(omitted_project),
            "--execution-id", "exec-compatible", "--bundle", str(omitted_bundle_path),
        )
        omitted_after = json.loads(omitted_state_path.read_text(encoding="utf-8"))
        record(
            "SCENARIO.V16.COMPATIBLE.OMITTED_ARTIFACT_UPDATE.REJECTED",
            omitted_code != 0 and omitted_after["revision"] == omitted_before
            and omitted_after["artifacts"]["src/q1.py"]["sha256"] == omitted_old_hash
            and omitted_q3_e1["status"] == "pass"
            and "omitted registered identity delta" in omitted_log,
            f"logs={omitted_logs};error={omitted_log}",
        )

        locator_project = create_project(workspace / "locator-negative")
        locator_state_path = locator_project / ".modeling/state.json"
        locator_state = json.loads(locator_state_path.read_text(encoding="utf-8"))
        locator_old_hash = sha256_file(locator_project / "src/q1.py")
        preserved_q1_e3 = next(
            item for item in locator_state["components"]["Q1"]["evidence"]
            if item["level"] == "E3_STRUCTURAL"
        )
        preserved_q1_e3["kind"] = "file"
        preserved_q1_e3["locator"] = {
            "path": "src/q1.py", "sha256": locator_old_hash,
        }
        write_json(locator_state_path, locator_state)
        seal_fixture_baseline(locator_project, "locator-negative-fixture")
        _, _, _, locator_logs = begin_formal(
            manager, skill_root, locator_project, workspace / "locator-negative",
        )
        (locator_project / "src/q1.py").write_text(
            "def solve(): return 1  # touches preserved E3 locator\n", encoding="utf-8",
        )
        locator_bundle_path = workspace / "locator-negative/bundle.json"
        write_json(locator_bundle_path, bundle(locator_project))
        locator_before = json.loads(locator_state_path.read_text(encoding="utf-8"))["revision"]
        locator_code, _, locator_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(locator_project),
            "--execution-id", "exec-compatible", "--bundle", str(locator_bundle_path),
        )
        locator_after = json.loads(locator_state_path.read_text(encoding="utf-8"))
        record(
            "SCENARIO.V16.COMPATIBLE.UNREGISTERED_CONSUMER.REJECTED",
            locator_code != 0 and locator_after["revision"] == locator_before
            and "changed path reaches undeclared or preserved evidence: Q1:E3_STRUCTURAL"
            in locator_log,
            f"logs={locator_logs};error={locator_log}",
        )

        claim_project = create_project(workspace / "claim-consumer-negative")
        claim_state_path = claim_project / ".modeling/state.json"
        claim_state = json.loads(claim_state_path.read_text(encoding="utf-8"))
        q1_implementation = next(
            item for item in claim_state["components"]["Q1"]["evidence"]
            if item["level"] == "implementation_ref"
        )
        changed_claim_id = q1_implementation["claim_refs"][0]
        preserved_q3_e3 = next(
            item for item in claim_state["components"]["Q3"]["evidence"]
            if item["level"] == "E3_STRUCTURAL"
        )
        preserved_q3_e3["input_refs"] = [{
            "kind": "claim", "id": changed_claim_id,
            "identity": sha256_text(q1_implementation["claim"]),
            "facet": "claim",
        }]
        preserved_q3_e3["binding_hash"] = evidence_binding_hash(
            "Q3", preserved_q3_e3["level"], preserved_q3_e3["input_refs"],
            preserved_q3_e3["claim_refs"],
        )
        write_json(claim_state_path, claim_state)
        seal_fixture_baseline(claim_project, "claim-negative-fixture")
        _, _, _, claim_logs = begin_formal(
            manager, skill_root, claim_project, workspace / "claim-consumer-negative",
        )
        claim_bundle = bundle(claim_project)
        replacement_claim = "Q1 compatible pruning implementation is current."
        next(
            item["evidence"] for item in claim_bundle["records"]
            if item["component_id"] == "Q1"
            and item["evidence"]["level"] == "implementation_ref"
        )["claim"] = replacement_claim
        claim_bundle["claim_updates"] = [{
            "claim_id": changed_claim_id,
            "expected_old_identity": sha256_text(q1_implementation["claim"]),
            "new_identity": sha256_text(replacement_claim),
        }]
        claim_bundle_path = workspace / "claim-consumer-negative/bundle.json"
        write_json(claim_bundle_path, claim_bundle)
        claim_before = json.loads(claim_state_path.read_text(encoding="utf-8"))["revision"]
        claim_code, _, claim_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(claim_project),
            "--execution-id", "exec-compatible", "--bundle", str(claim_bundle_path),
        )
        claim_after = json.loads(claim_state_path.read_text(encoding="utf-8"))
        record(
            "SCENARIO.V16.COMPATIBLE.CLAIM_CONSUMER.REJECTED",
            claim_code != 0 and claim_after["revision"] == claim_before
            and "changed claim reaches undeclared or preserved evidence: Q3:E3_STRUCTURAL"
            in claim_log,
            f"logs={claim_logs};error={claim_log}",
        )

        drift_project = create_project(workspace / "component-drift-negative")
        drift_state_path = drift_project / ".modeling/state.json"
        _, _, _, drift_logs = begin_formal(
            manager, skill_root, drift_project, workspace / "component-drift-negative",
        )
        drift_state = json.loads(drift_state_path.read_text(encoding="utf-8"))
        drift_state["components"]["Q1"]["status"] = "invalidated"
        drift_state["components"]["Q1"]["invalidated_at_revision"] = drift_state["revision"]
        write_json(drift_state_path, drift_state)
        drift_bundle_path = workspace / "component-drift-negative/bundle.json"
        write_json(drift_bundle_path, bundle(drift_project))
        drift_code, _, drift_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(drift_project),
            "--execution-id", "exec-compatible", "--bundle", str(drift_bundle_path),
        )
        drift_after = json.loads(drift_state_path.read_text(encoding="utf-8"))
        record(
            "SCENARIO.V16.COMPATIBLE.COMPONENT_DRIFT.REJECTED",
            drift_code != 0 and drift_after["revision"] == drift_state["revision"]
            and drift_after["components"]["Q1"]["status"] == "invalidated"
            and "cannot hide component validity drift" in drift_log,
            f"logs={drift_logs};error={drift_log}",
        )

        outside_project = create_project(workspace / "outside-path-negative")
        outside_plan = plan(
            "reconcile_compatible", "G2_CHECKPOINT", "promote", "evidence_record",
        )
        outside_plan["steps"][0]["change_set"]["paths"].remove("src/q1.py")
        _, _, _, outside_logs = begin_formal(
            manager, skill_root, outside_project, workspace / "outside-path-negative",
            outside_plan,
        )
        (outside_project / "src/q1.py").write_text(
            "def solve(): return 1  # omitted unregistered path delta\n",
            encoding="utf-8",
        )
        outside_bundle_path = workspace / "outside-path-negative/bundle.json"
        write_json(outside_bundle_path, bundle(outside_project))
        outside_state_path = outside_project / ".modeling/state.json"
        outside_before = json.loads(outside_state_path.read_text(encoding="utf-8"))["revision"]
        outside_code, _, outside_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(outside_project),
            "--execution-id", "exec-compatible", "--bundle", str(outside_bundle_path),
        )
        outside_after = json.loads(outside_state_path.read_text(encoding="utf-8"))
        record(
            "SCENARIO.V16.COMPATIBLE.UNDECLARED_PATH_DELTA.REJECTED",
            outside_code != 0 and outside_after["revision"] == outside_before
            and (
                "exact evidence identity delta lies outside sealed ChangeSet" in outside_log
                or "compatible replacement locator lies outside sealed ChangeSet" in outside_log
            ),
            f"logs={outside_logs};error={outside_log}",
        )

        working_project = create_project(workspace / "unrelated-working-positive")
        working_note = working_project / "notes/working.md"
        working_note.parent.mkdir(parents=True, exist_ok=True)
        working_note.write_text("unrelated working note v1\n", encoding="utf-8")
        working_state_path = working_project / ".modeling/state.json"
        working_state = json.loads(working_state_path.read_text(encoding="utf-8"))
        working_state["artifacts"]["notes/working.md"] = {
            "sha256": sha256_file(working_note), "size": working_note.stat().st_size,
            "media_type": "text/markdown", "role": "planning", "class": "control",
            "purpose": "Unrelated project-only working note for the near-negative.",
            "authorization_basis": "scenario fixture", "lifecycle": "working",
            "identity_class": "working", "producer": "V16-DEMO",
            "consumers": ["V16-DEMO"], "status": "registered",
            "validated_at": None, "validation_evidence_id": None, "supersedes": None,
        }
        write_json(working_state_path, working_state)
        seal_fixture_baseline(working_project, "unrelated-working-fixture")
        _, _, _, working_logs = begin_formal(
            manager, skill_root, working_project, workspace / "unrelated-working-positive",
        )
        working_note.write_text("unrelated working note v2\n", encoding="utf-8")
        working_bundle_path = workspace / "unrelated-working-positive/bundle.json"
        write_json(working_bundle_path, bundle(working_project))
        working_code, _, working_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(working_project),
            "--execution-id", "exec-compatible", "--bundle", str(working_bundle_path),
        )
        working_after = json.loads(working_state_path.read_text(encoding="utf-8"))
        record(
            "BEH.V16.COMPATIBLE.UNRELATED_WORKING_DRIFT.IGNORED",
            working_code == 0
            and working_after["artifacts"]["notes/working.md"]["sha256"]
            == working_state["artifacts"]["notes/working.md"]["sha256"]
            and any(
                entry["event"] == "compatible_change_reconciled"
                for entry in working_after["history"]
            ),
            f"logs={working_logs};reconcile={working_log}",
        )

        consumer_project = create_project(workspace / "consumer-negative")
        consumer_state_path = consumer_project / ".modeling/state.json"
        consumer_state = json.loads(consumer_state_path.read_text(encoding="utf-8"))
        old_code_hash = sha256_file(consumer_project / "src/q1.py")
        consumer_state["artifacts"]["src/q1.py"] = {
            "sha256": old_code_hash,
            "size": (consumer_project / "src/q1.py").stat().st_size,
            "media_type": "text/x-python", "role": "code", "class": "code",
            "purpose": "Milestone Q1 implementation consumed directly by Q3.",
            "authorization_basis": "scenario fixture", "lifecycle": "milestone",
            "identity_class": "milestone", "producer": "Q1", "consumers": ["Q3"],
            "status": "registered", "validated_at": None,
            "validation_evidence_id": None, "supersedes": None,
        }
        q3_e1 = next(
            item for item in consumer_state["components"]["Q3"]["evidence"]
            if item["level"] == "E1_IMPLEMENTATION"
        )
        q3_e1["input_refs"] = [{
            "kind": "artifact", "id": "src/q1.py", "identity": old_code_hash,
            "facet": "content",
        }]
        q3_e1["binding_hash"] = evidence_binding_hash(
            "Q3", q3_e1["level"], q3_e1["input_refs"], q3_e1["claim_refs"],
        )
        write_json(consumer_state_path, consumer_state)
        seal_fixture_baseline(consumer_project, "consumer-negative-fixture")
        _, _, _, consumer_logs = begin_formal(
            manager, skill_root, consumer_project, workspace / "consumer-negative",
        )
        (consumer_project / "src/q1.py").write_text(
            "def solve(): return 1  # a second compatible pruning variant\n",
            encoding="utf-8",
        )
        consumer_bundle = bundle(consumer_project)
        consumer_bundle["artifact_updates"] = [{
            "path": "src/q1.py", "expected_old_sha256": old_code_hash,
        }]
        consumer_bundle_path = workspace / "consumer-negative/bundle.json"
        write_json(consumer_bundle_path, consumer_bundle)
        consumer_before = json.loads(consumer_state_path.read_text(encoding="utf-8"))["revision"]
        consumer_code, _, consumer_log = run(
            manager, "reconcile-compatible-change", "--project-root", str(consumer_project),
            "--execution-id", "exec-compatible", "--bundle", str(consumer_bundle_path),
        )
        consumer_after = json.loads(consumer_state_path.read_text(encoding="utf-8"))
        record(
            "SCENARIO.V16.COMPATIBLE.UNDECLARED_EXACT_CONSUMER.REJECTED",
            consumer_code != 0 and consumer_after["revision"] == consumer_before
            and consumer_after["components"]["Q3"]["status"] == "closed"
            and consumer_after["artifacts"]["src/q1.py"]["sha256"] == old_code_hash,
            f"logs={consumer_logs};error={consumer_log}",
        )

        new_window_plan = plan(
            "reconcile_compatible", "G2_CHECKPOINT", "promote",
            "evidence_record",
        )
        new_window_plan["window_context"] = "new_window"
        new_window_resolution = resolve(new_window_plan, negative_project, skill_root)
        read_paths: list[tuple[str, str]] = []
        if new_window_resolution.get("status") == "resolved":
            from recovery_v14 import required_recovery_reads
            current = json.loads((negative_project / ".modeling/state.json").read_text(encoding="utf-8"))
            resolved_step = new_window_resolution["steps"][0]
            read_paths = [
                (item["path"], item["required_mode"])
                for item in required_recovery_reads(
                    negative_project, current, resolved_step, resolved_step["recovery"],
                )
            ]
        record(
            "BEH.V16.COMPATIBLE.R1.TARGETED_READ_SET",
            ("data/problem.pdf", "identity") in read_paths
            and ("specs/Q1.md", "semantic") in read_paths
            and ("specs/Q2.md", "semantic") in read_paths
            and ("specs/Q3.md", "semantic") in read_paths
            and ("src/q3.py", "semantic") in read_paths
            and ("results/q3-e1.txt", "semantic") in read_paths
            and ("results/q3-e2.txt", "semantic") in read_paths
            and not any(
                path in {"src/q1.py", "src/q2.py"}
                for path, _ in read_paths
            ),
            json.dumps(read_paths, ensure_ascii=False),
        )

    report = {
        "schema_version": "16.0", "driver": "run_v16_gate_scenarios.py",
        "status": "pass" if all(item["status"] == "pass" for item in cases) else "fail",
        "passed": sum(item["status"] == "pass" for item in cases),
        "total": len(cases), "cases": cases,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
