#!/usr/bin/env python3
"""Freeze a V10 candidate only after two immutable, complete release gates."""

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
    read_json,
    sha256_bytes,
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


def run_gate(root: Path, v9_root: Path, timeout: int) -> dict[str, Any]:
    script = root / "scripts/validate_release.py"
    command = [
        sys.executable, "-I", "-B", "-c", ISOLATED_LAUNCHER,
        str(root / "scripts"), str(script),
        "--root", str(root), "--v9-root", str(v9_root), "--timeout", str(timeout),
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["V10_FREEZE_FRESH_GATE"] = "1"
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


def run_gate_on_mirror(root: Path, v9_root: Path, timeout: int) -> dict[str, Any]:
    """Gate an exact disposable mirror so validators cannot mutate the source candidate."""
    source_before = tree_manifest(root)
    with tempfile.TemporaryDirectory(prefix="v10-freeze-gate-") as directory:
        mirror = Path(directory) / "skills"
        shutil.copytree(root, mirror, symlinks=True)
        mirrored = tree_manifest(mirror)
        source_after_copy = tree_manifest(root)
        if source_after_copy != source_before:
            raise FreezeError("candidate_changed_while_creating_gate_mirror")
        if mirrored != source_before:
            raise FreezeError("gate_mirror_does_not_match_candidate")
        report = run_gate(mirror, v9_root, timeout)
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


def write_external_report(path: Path, root: Path, report: dict[str, Any]) -> None:
    target = path.resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        pass
    else:
        raise FreezeError("freeze report path must be outside the candidate root")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def freeze(root: Path, v9_root: Path, timeout: int, external_report: Path | None = None) -> dict[str, Any]:
    state_path = root / STATE_PATH
    manifest_path = root / MANIFEST_PATH
    skill_path = root / "SKILL.md"
    if not state_path.is_file():
        raise FreezeError("release_state_missing")
    if not skill_path.is_file():
        raise FreezeError("skill_file_missing")
    original_state_bytes = state_path.read_bytes()
    original_skill_bytes = skill_path.read_bytes()
    frozen_skill_bytes = stable_skill_bytes(original_skill_bytes)
    state = read_json(state_path)
    if not isinstance(state, dict) or state.get("status") != "candidate":
        raise FreezeError(f"release_not_candidate:{state.get('status') if isinstance(state, dict) else None}")
    if manifest_path.exists():
        raise FreezeError("candidate_manifest_already_exists")
    if not v9_root.is_dir():
        raise FreezeError(f"v9_root_missing:{v9_root}")

    candidate_before = tree_manifest(root)
    first_gate = run_gate_on_mirror(root, v9_root, timeout)
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
        manifest: dict[str, Any] = {
            "schema_version": "10.0",
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
            "unverified_boundaries": plan["unverified_boundaries"],
            "attestation": {
                "kind": "self_hash_plus_fresh_independent_regate",
                "digest_algorithm": "sha256",
                "external_signature": None,
            },
        }
        manifest["manifest_sha256"] = manifest_digest(manifest)
        validate_manifest_schema(root, manifest)
        atomic_json_write(manifest_path, manifest)
        wrote_manifest = True

        frozen_before_gate = tree_manifest(root)
        second_gate = run_gate_on_mirror(root, v9_root, timeout)
        frozen_after_gate = tree_manifest(root)
        if frozen_after_gate != frozen_before_gate:
            raise FreezeError("second_gate_mutated_frozen_candidate")
        if second_gate.get("validator_hashes") != current_validators:
            raise FreezeError("validator_changed_during_second_gate")
        if second_gate.get("tree", {}).get("sha256") != frozen_before_gate["sha256"]:
            raise FreezeError("second_gate_tree_attestation_mismatch")
        result = {
            "schema_version": "10.0",
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
        if external_report is not None:
            write_external_report(external_report, root, result)
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
    parser.add_argument("--v9-root", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--report", type=Path, help="Optional report path outside the candidate tree")
    args = parser.parse_args()
    root = args.root.resolve()
    v9_root = args.v9_root.resolve()
    try:
        report = freeze(root, v9_root, args.timeout, args.report)
        exit_code = 0
    except Exception as exc:
        report = {
            "schema_version": "10.0",
            "release_id": "V10.0.0",
            "status": "fail",
            "release_status": "candidate",
            "errors": [f"{type(exc).__name__}:{exc}"],
        }
        exit_code = 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
