#!/usr/bin/env python3
"""Freeze a V11 candidate only after two immutable, complete release gates."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

# Freezing must remain possible when invoked without ``python -B``: importing
# the local gate module must never create a cache file that the package gate
# would correctly reject as release contamination.
sys.dont_write_bytecode = True

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    Draft202012Validator = None  # type: ignore[assignment]
    FormatChecker = None  # type: ignore[assignment]

from validate_release import (
    ISOLATED_LAUNCHER,
    MANIFEST_PATH,
    MANIFEST_SCHEMA_PATH,
    RELEASE_TREE_EXCLUSIONS,
    REQUIRED_DRIVERS,
    STATE_PATH,
    canonical_bytes,
    manifest_digest,
    path_is_within,
    read_json,
    roots_overlap,
    sha256_bytes,
    skill_root,
    tree_manifest,
    utc_now,
    validator_hashes,
)


class FreezeError(RuntimeError):
    """Raised when a release cannot be frozen without weakening the gate."""


def report_digest(report: dict[str, Any]) -> str:
    payload = dict(report)
    claimed = payload.pop("report_sha256", None)
    calculated = sha256_bytes(canonical_bytes(payload))
    if claimed != calculated:
        raise FreezeError("gate_report_self_digest_mismatch")
    return calculated


def run_gate(root: Path, v10_root: Path, v9_root: Path, timeout: int) -> dict[str, Any]:
    script = root / "scripts/validate_release.py"
    command = [
        sys.executable, "-I", "-B", "-c", ISOLATED_LAUNCHER,
        str(root / "scripts"), str(script),
        "--root", str(root), "--v10-root", str(v10_root),
        "--v9-root", str(v9_root), "--timeout", str(timeout),
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["V11_FREEZE_FRESH_GATE"] = "1"
    try:
        process = subprocess.run(
            command,
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
            timeout=max(timeout * len(REQUIRED_DRIVERS) + 60, 600),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FreezeError(f"release_gate_timeout:{exc}") from exc
    except OSError as exc:
        raise FreezeError(f"release_gate_launch_failed:{exc}") from exc
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise FreezeError(f"release_gate_output_not_json:{exc};stderr={process.stderr[-1000:]}") from exc
    if not isinstance(report, dict):
        raise FreezeError("release_gate_report_not_object")
    report_digest(report)
    if process.returncode != 0 or report.get("status") != "pass":
        errors = report.get("errors", [])
        raise FreezeError(f"release_gate_failed:exit={process.returncode}:errors={errors}")
    drivers = report.get("drivers")
    if not isinstance(drivers, list) or tuple(item.get("id") for item in drivers if isinstance(item, dict)) != REQUIRED_DRIVERS:
        raise FreezeError("release_gate_driver_attestation_incomplete")
    for item in drivers:
        if (
            not isinstance(item, dict)
            or item.get("status") != "pass"
            or item.get("fresh_subprocess") is not True
            or not isinstance(item.get("executed_count"), int)
            or item["executed_count"] <= 0
        ):
            raise FreezeError(f"release_gate_driver_invalid:{item}")
    return report


def run_gate_on_mirror(
    root: Path, v10_root: Path, v9_root: Path, timeout: int
) -> dict[str, Any]:
    """Gate an exact disposable mirror so validators cannot mutate the source candidate."""
    source_before = tree_manifest(root)
    with tempfile.TemporaryDirectory(prefix="v11-freeze-gate-") as directory:
        mirror = Path(directory) / "skills"
        shutil.copytree(root, mirror, symlinks=True)
        mirrored = tree_manifest(mirror)
        source_after_copy = tree_manifest(root)
        if source_after_copy != source_before:
            raise FreezeError("candidate_changed_while_creating_gate_mirror")
        if mirrored != source_before:
            raise FreezeError("gate_mirror_does_not_match_candidate")
        report = run_gate(mirror, v10_root, v9_root, timeout)
        if report.get("tree") != mirrored:
            raise FreezeError("gate_report_does_not_attest_mirror")
    if tree_manifest(root) != source_before:
        raise FreezeError("candidate_changed_while_running_mirrored_gate")
    return report


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".freeze.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def atomic_bytes_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".freeze.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)


def stable_skill_bytes(payload: bytes) -> bytes:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FreezeError(f"skill_metadata_not_utf8:{exc}") from exc
    frontmatter = re.match(r"\A---\r?\n(?P<body>.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if frontmatter is None:
        raise FreezeError("skill_frontmatter_missing")
    body = frontmatter.group("body")
    releases = list(re.finditer(r'^(?P<prefix>\s{2}release:\s*)["\']?candidate["\']?\s*$', body, re.MULTILINE))
    if len(releases) != 1:
        raise FreezeError(f"skill_candidate_release_field_count:{len(releases)}")
    match = releases[0]
    stable_body = body[:match.start()] + match.group("prefix") + '"stable"' + body[match.end():]
    stable_text = text[:frontmatter.start("body")] + stable_body + text[frontmatter.end("body"):]
    return stable_text.encode("utf-8")


def validate_manifest_schema(root: Path, manifest: dict[str, Any]) -> None:
    if Draft202012Validator is None:
        raise FreezeError("jsonschema_dependency_missing")
    schema = read_json(root / MANIFEST_SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    issues = sorted(validator.iter_errors(manifest), key=lambda item: list(item.absolute_path))
    if issues:
        rendered = [
            f"{'/'.join(str(part) for part in issue.absolute_path) or '$'}:{issue.message}"
            for issue in issues
        ]
        raise FreezeError("frozen_manifest_schema_failed:" + "|".join(rendered))


def driver_attestations(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": item["id"],
            "command_sha256": item["command_sha256"],
            "exit_code": item["exit_code"],
            "executed_count": item["executed_count"],
            "auxiliary_executed_count": item["auxiliary_executed_count"],
            "stdout_sha256": item["stdout_sha256"],
        }
        for item in report["drivers"]
    ]


def write_external_report(
    path: Path,
    root: Path,
    report: dict[str, Any],
    protected_roots: tuple[Path, ...],
) -> None:
    target = path.resolve()
    if path_is_within(target, root):
        raise FreezeError("freeze report path must be outside the candidate root")
    for protected in protected_roots:
        if path_is_within(target, protected):
            raise FreezeError(f"freeze report path must be outside protected baseline:{protected}")
    if target.exists():
        raise FreezeError("freeze report path already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def baseline_snapshot(v10_skill_root: Path, v9_skill_root: Path) -> dict[str, dict[str, Any]]:
    return {
        "v10": tree_manifest(v10_skill_root),
        "v9": tree_manifest(v9_skill_root),
    }


def assert_baselines_unchanged(
    baseline_before: dict[str, dict[str, Any]],
    v10_skill_root: Path,
    v9_skill_root: Path,
) -> None:
    if baseline_snapshot(v10_skill_root, v9_skill_root) != baseline_before:
        raise FreezeError("baseline_changed_during_freeze")


def assert_gate_attests_baselines(
    report: dict[str, Any], baseline_before: dict[str, dict[str, Any]]
) -> None:
    observed = report.get("baseline_integrity")
    if not isinstance(observed, dict):
        raise FreezeError("gate_baseline_attestation_missing")
    for name, manifest in baseline_before.items():
        item = observed.get(name)
        if not isinstance(item, dict) or (
            item.get("tree_sha256") != manifest.get("sha256")
            or item.get("file_count") != manifest.get("file_count")
            or item.get("unchanged") is not True
        ):
            raise FreezeError(f"gate_baseline_attestation_mismatch:{name}")


def freeze(
    root: Path,
    v10_root: Path,
    v9_root: Path,
    timeout: int,
    external_report: Path | None = None,
) -> dict[str, Any]:
    state_path = root / STATE_PATH
    manifest_path = root / MANIFEST_PATH
    skill_path = root / "SKILL.md"
    if not state_path.is_file():
        raise FreezeError("release_state_missing")
    if not skill_path.is_file():
        raise FreezeError("skill_file_missing")
    if external_report is None:
        raise FreezeError("external_freeze_receipt_path_required")
    original_state_bytes = state_path.read_bytes()
    original_skill_bytes = skill_path.read_bytes()
    frozen_skill_bytes = stable_skill_bytes(original_skill_bytes)
    state = read_json(state_path)
    if not isinstance(state, dict) or state.get("status") != "candidate":
        raise FreezeError(f"release_not_candidate:{state.get('status') if isinstance(state, dict) else None}")
    if manifest_path.exists():
        raise FreezeError("candidate_manifest_already_exists")
    if not v10_root.is_dir():
        raise FreezeError(f"v10_root_missing:{v10_root}")
    if not v9_root.is_dir():
        raise FreezeError(f"v9_root_missing:{v9_root}")
    v10_skill_root = skill_root(v10_root)
    v9_skill_root = skill_root(v9_root)
    if roots_overlap(root, v10_skill_root):
        raise FreezeError("candidate_v10_roots_overlap")
    if roots_overlap(root, v9_skill_root):
        raise FreezeError("candidate_v9_roots_overlap")
    if roots_overlap(v10_skill_root, v9_skill_root):
        raise FreezeError("v10_v9_roots_overlap")
    protected_report_roots_list = [
        root.resolve(), v10_root.resolve(), v9_root.resolve(),
        v10_skill_root.resolve(), v9_skill_root.resolve(),
    ]
    # Callers may pass either a version directory or its nested ``skills``
    # directory.  In the latter form, protect the version directory too so an
    # external receipt cannot be written beside the frozen skill and silently
    # mutate the baseline package.
    for supplied, normalized in ((v10_root, v10_skill_root), (v9_root, v9_skill_root)):
        if supplied.resolve() == normalized.resolve() and supplied.name == "skills":
            protected_report_roots_list.append(supplied.parent.resolve())
    protected_report_roots = tuple(dict.fromkeys(protected_report_roots_list))
    report_target = external_report.resolve()
    if any(path_is_within(report_target, protected) for protected in protected_report_roots):
        raise FreezeError("external_freeze_receipt_path_overlaps_candidate_or_baseline")
    if report_target.exists():
        raise FreezeError("external_freeze_receipt_path_already_exists")
    baseline_before = baseline_snapshot(v10_skill_root, v9_skill_root)

    candidate_before = tree_manifest(root)
    try:
        first_gate = run_gate_on_mirror(root, v10_root, v9_root, timeout)
    finally:
        assert_baselines_unchanged(baseline_before, v10_skill_root, v9_skill_root)
    assert_gate_attests_baselines(first_gate, baseline_before)
    candidate_after_gate = tree_manifest(root)
    if candidate_after_gate != candidate_before:
        raise FreezeError("first_gate_mutated_candidate")
    first_gate_hash = report_digest(first_gate)

    generated_at = utc_now()
    stable_state = dict(state)
    stable_state.update({
        "status": "stable",
        "frozen_at": generated_at,
        "pre_freeze_gate_report_sha256": first_gate_hash,
    })
    wrote_state = False
    wrote_skill = False
    wrote_manifest = False
    try:
        atomic_bytes_write(skill_path, frozen_skill_bytes)
        wrote_skill = True
        atomic_json_write(state_path, stable_state)
        wrote_state = True
        current_validators = validator_hashes(root)
        if current_validators != first_gate.get("validator_hashes"):
            raise FreezeError("validator_changed_between_gate_and_freeze")
        release_tree = tree_manifest(root, RELEASE_TREE_EXCLUSIONS)
        plan = read_json(root / "evals/release/release-plan.json")
        corpus_driver = next(
            item for item in first_gate["drivers"] if item.get("id") == "v10_corpus"
        )
        corpus_metrics = corpus_driver.get("observed_metrics", {})
        manifest: dict[str, Any] = {
            "schema_version": "11.0",
            "release_id": state.get("release_id"),
            "status": "stable",
            "generated_at": generated_at,
            "source_status": "candidate",
            "manifest_policy": {
                "algorithm": "sha256-canonical-file-list-v1",
                "excluded_paths": sorted(RELEASE_TREE_EXCLUSIONS),
            },
            "release_tree": release_tree,
            "validator_hashes": current_validators,
            "pre_freeze_gate": {
                "report_sha256": first_gate_hash,
                "tree_sha256": first_gate["tree"]["sha256"],
                "validator_hashes_sha256": first_gate["validator_hashes_sha256"],
                "drivers": driver_attestations(first_gate),
            },
            "inherited_v10_rule_corpus": {
                "rule_files": corpus_metrics.get("rule_files"),
                "exact_files": corpus_metrics.get("exact_files"),
                "active_rules": corpus_metrics.get("active_rules"),
                "v10_active_rules": corpus_metrics.get("v10_active_rules"),
                "v10_inventory_sha256": corpus_metrics.get("v10_inventory_sha256"),
                "v10_manifest_sha256": corpus_metrics.get("v10_manifest_sha256"),
                "v10_release_tree_sha256": corpus_metrics.get("v10_release_tree_sha256"),
                "driver_stdout_sha256": corpus_driver.get("stdout_sha256"),
            },
            "compatibility_boundary": plan["compatibility_boundary"],
            "unverified_boundaries": plan["unverified_boundaries"],
            "attestation": {
                "kind": "self_hash_plus_fresh_mirrored_regate",
                "digest_algorithm": "sha256",
                "external_signature": None,
            },
        }
        manifest["manifest_sha256"] = manifest_digest(manifest)
        validate_manifest_schema(root, manifest)
        atomic_json_write(manifest_path, manifest)
        wrote_manifest = True

        frozen_before_gate = tree_manifest(root)
        try:
            second_gate = run_gate_on_mirror(root, v10_root, v9_root, timeout)
        finally:
            assert_baselines_unchanged(baseline_before, v10_skill_root, v9_skill_root)
        assert_gate_attests_baselines(second_gate, baseline_before)
        frozen_after_gate = tree_manifest(root)
        if frozen_after_gate != frozen_before_gate:
            raise FreezeError("second_gate_mutated_frozen_candidate")
        if second_gate.get("validator_hashes") != current_validators:
            raise FreezeError("validator_changed_during_second_gate")
        if second_gate.get("tree", {}).get("sha256") != frozen_before_gate["sha256"]:
            raise FreezeError("second_gate_tree_attestation_mismatch")
        baseline_after = baseline_snapshot(v10_skill_root, v9_skill_root)
        if baseline_after != baseline_before:
            raise FreezeError("baseline_changed_during_freeze")
        result = {
            "schema_version": "11.0",
            "release_id": state.get("release_id"),
            "status": "pass",
            "release_status": "stable",
            "frozen_at": generated_at,
            "manifest_path": MANIFEST_PATH.as_posix(),
            "manifest_sha256": manifest["manifest_sha256"],
            "release_tree_sha256": release_tree["sha256"],
            "first_gate_report_sha256": first_gate_hash,
            "second_gate_report_sha256": report_digest(second_gate),
            "second_gate_tree_unchanged": frozen_after_gate == frozen_before_gate,
            "attestation": "self_hash_plus_fresh_mirrored_regate",
            "external_freeze_receipt": str(external_report.resolve()),
            "baseline_integrity": {
                name: {
                    "tree_sha256": manifest["sha256"],
                    "file_count": manifest["file_count"],
                    "unchanged": baseline_after[name] == manifest,
                }
                for name, manifest in sorted(baseline_before.items())
            },
            "compatibility_boundary": plan["compatibility_boundary"],
            "drivers": [
                {
                    "id": item["id"], "status": item["status"],
                    "executed_count": item["executed_count"],
                    "auxiliary_executed_count": item["auxiliary_executed_count"],
                }
                for item in second_gate["drivers"]
            ],
            "unverified_boundaries": plan["unverified_boundaries"],
        }
        result["report_sha256"] = sha256_bytes(canonical_bytes(result))
        write_external_report(external_report, root, result, protected_report_roots)
        return result
    except Exception:
        if wrote_manifest and manifest_path.is_file():
            manifest_path.unlink()
        if wrote_state:
            atomic_bytes_write(state_path, original_state_bytes)
        if wrote_skill:
            atomic_bytes_write(skill_path, original_skill_bytes)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--v10-root", type=Path, required=True)
    parser.add_argument("--v9-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--report", type=Path, required=True,
        help="Required new freeze receipt path outside the candidate and V10/V9 roots",
    )
    args = parser.parse_args()
    root = args.root.resolve()
    v10_root = args.v10_root.resolve()
    v9_root = args.v9_root.resolve()
    try:
        report = freeze(root, v10_root, v9_root, args.timeout, args.report)
        exit_code = 0
    except Exception as exc:
        report = {
            "schema_version": "11.0",
            "release_id": "V11.0.0",
            "status": "fail",
            "release_status": "candidate",
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
        exit_code = 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
