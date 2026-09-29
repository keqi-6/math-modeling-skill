#!/usr/bin/env python3
"""Validate and freeze a policy-bound candidate into a new destination."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:  # the contracts driver reports the same release dependency
    Draft202012Validator = None  # type: ignore[assignment,misc]
    FormatChecker = None  # type: ignore[assignment,misc]


POLICY = Path("references/release-policy.json")
PLAN = Path("evals/release/release-plan.json")
STATE = Path("evals/release/release-state.json")
MANIFEST = Path("evals/release/frozen-manifest.json")
MANIFEST_SCHEMA = Path("references/release-manifest.schema.json")


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def root_for(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def within(path: Path, parent: Path) -> bool:
    path, parent = path.resolve(), parent.resolve()
    return path == parent or parent in path.parents


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


def tree_manifest(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if (
            not path.is_file()
            or path.is_symlink()
            or relative == MANIFEST.as_posix()
            or "__pycache__" in path.parts
            or path.suffix == ".pyc"
        ):
            continue
        files.append({"path": relative, "sha256": digest(path.read_bytes()), "size": path.stat().st_size})
    return {
        "algorithm": "sha256-canonical-file-list-v1",
        "file_count": len(files),
        "sha256": digest(canonical(files)),
        "files": files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument(
        "--authorization", required=True,
        help="separately supplied verbatim user authorization for this freeze",
    )
    parser.add_argument("--timeout", type=int, default=None, help="optional per-driver timeout override")
    parser.add_argument("--dry-run", action="store_true", help="validate all freeze prerequisites without copying")
    args = parser.parse_args()
    source = root_for(args.root)
    destination = args.destination.resolve()
    if len(args.authorization.strip()) < 2:
        raise SystemExit("freeze refused: authorization is missing or too short")
    if destination.exists():
        raise SystemExit("freeze refused: destination already exists")
    if within(destination, source) or within(source, destination):
        raise SystemExit("freeze refused: source and destination overlap")

    policy = json.loads((source / POLICY).read_text(encoding="utf-8"))
    plan = json.loads((source / PLAN).read_text(encoding="utf-8"))
    manifest_schema = json.loads((source / MANIFEST_SCHEMA).read_text(encoding="utf-8"))
    schema_version = policy.get("schema_version")
    release_id = release_id_for(schema_version, policy.get("release_id"))
    if release_id is None:
        raise SystemExit("freeze refused: release-policy identity is invalid")
    policy_driver_ids = [
        item.get("id") for item in policy.get("active_drivers", []) if isinstance(item, dict)
    ]
    policy_driver_projection = [
        {"id": item.get("id"), "script": item.get("script")}
        for item in policy.get("active_drivers", []) if isinstance(item, dict)
    ]
    required_case_ids = policy.get("required_case_ids", [])
    if (
        plan.get("schema_version") != schema_version
        or plan.get("release_id") != release_id
        or plan.get("required_drivers") != policy_driver_ids
        or plan.get("drivers") != policy_driver_projection
        or plan.get("required_case_ids") != required_case_ids
    ):
        raise SystemExit("freeze refused: release plan does not mirror policy")
    review = plan.get("change_review")
    review_authorization = review.get("authorization", {}) if isinstance(review, dict) else {}
    review_quote = review_authorization.get("quote")
    if (
        not isinstance(review_quote, str)
        or len(review_quote.strip()) < 2
        or review_authorization.get("quote_sha256") != digest(review_quote.encode("utf-8"))
    ):
        raise SystemExit("freeze refused: reviewed change authorization is invalid")
    manifest_properties = manifest_schema.get("properties", {}) if isinstance(manifest_schema, dict) else {}
    if (
        manifest_properties.get("schema_version", {}).get("const") != schema_version
        or manifest_properties.get("release_id", {}).get("const") != release_id
    ):
        raise SystemExit("freeze refused: manifest schema identity does not match policy")
    if Draft202012Validator is None or FormatChecker is None:
        raise SystemExit("freeze refused: jsonschema is unavailable")
    try:
        Draft202012Validator.check_schema(manifest_schema)
    except Exception as exc:
        raise SystemExit(f"freeze refused: manifest schema is invalid: {exc}") from exc

    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-B", str(source / "scripts/validate_release.py"), "--root", str(source)]
    if args.timeout is not None:
        command.extend(["--timeout", str(args.timeout)])
    budget = policy.get("budget")
    default_timeout = budget.get("default_timeout_seconds_per_driver", 30) if isinstance(budget, dict) else 30
    configured_timeouts = [
        item.get("timeout_seconds", default_timeout)
        for item in policy.get("active_drivers", []) if isinstance(item, dict)
    ]
    total_driver_timeout = (
        args.timeout * max(1, len(policy_driver_ids))
        if args.timeout is not None
        else sum(item for item in configured_timeouts if isinstance(item, int) and item > 0)
    )
    try:
        gate = subprocess.run(
            command,
            cwd=source,
            env=environment,
            text=True,
            capture_output=True,
            timeout=max(60, total_driver_timeout + 30),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SystemExit("freeze refused: release gate timed out") from exc
    try:
        report = json.loads(gate.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"freeze refused: release gate did not return JSON: {exc}") from exc
    claimed = report.get("report_sha256")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    report_bound = (
        report.get("schema_version") == schema_version
        and report.get("release_id") == release_id
        and report.get("policy_sha256") == digest(canonical(policy))
        and report.get("active_driver_ids") == policy_driver_ids
        and report.get("required_case_ids") == required_case_ids
    )
    if (
        gate.returncode != 0
        or report.get("status") != "pass"
        or claimed != digest(canonical(unsigned))
        or not report_bound
    ):
        raise SystemExit(f"freeze refused: release gate failed: {report.get('errors', [])}")

    if args.dry_run:
        print(json.dumps({
            "schema_version": schema_version,
            "release_id": release_id,
            "status": "candidate",
            "dry_run": True,
            "would_freeze_to": str(destination),
            "gate_report_sha256": claimed,
            "candidate_tree_sha256": report.get("tree_sha256"),
        }, ensure_ascii=False, sort_keys=True))
        return 0

    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / f".{destination.name}.staging-{uuid.uuid4().hex}"
    try:
        shutil.copytree(
            source,
            staging,
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        skill_path = staging / "SKILL.md"
        skill = skill_path.read_text(encoding="utf-8")
        stable, count = re.subn(
            r'(?m)^(\s{2}release:\s*)["\']?candidate["\']?\s*$',
            r'\1"stable"',
            skill,
        )
        if count != 1:
            raise RuntimeError("candidate release marker is missing or ambiguous")
        skill_path.write_text(stable, encoding="utf-8")

        frozen_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        state_path = staging / STATE
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state.get("schema_version") != schema_version or state.get("release_id") != release_id:
            raise RuntimeError("candidate state identity changed after validation")
        state.update({"status": "stable", "frozen_at": frozen_at, "gate_report_sha256": claimed})
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        release_tree = tree_manifest(staging)
        manifest = {
            "schema_version": schema_version,
            "release_id": release_id,
            "status": "stable",
            "generated_at": frozen_at,
            "authorization_sha256": digest(args.authorization.encode("utf-8")),
            "source_gate": {
                "report_sha256": claimed,
                "candidate_tree_sha256": report.get("tree_sha256"),
                "policy_sha256": report.get("policy_sha256"),
                "active_driver_ids": report.get("active_driver_ids"),
                "required_case_ids": report.get("required_case_ids"),
            },
            "release_tree": release_tree,
            "external_signature": None,
        }
        manifest["manifest_sha256"] = digest(canonical(manifest))
        manifest_errors = sorted(
            Draft202012Validator(manifest_schema, format_checker=FormatChecker()).iter_errors(manifest),
            key=lambda item: list(item.absolute_path),
        )
        if manifest_errors:
            details = "; ".join(
                f"{'/'.join(map(str, item.absolute_path)) or '<root>'}:{item.message}"
                for item in manifest_errors
            )
            raise RuntimeError(f"generated release manifest is invalid: {details}")
        manifest_path = staging / MANIFEST
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.rename(staging, destination)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    print(json.dumps({
        "schema_version": schema_version,
        "release_id": release_id,
        "status": "stable",
        "destination": str(destination),
        "manifest_sha256": manifest["manifest_sha256"],
        "gate_report_sha256": claimed,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
