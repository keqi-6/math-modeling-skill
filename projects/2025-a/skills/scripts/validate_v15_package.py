#!/usr/bin/env python3
"""Validate that the V15 release package is loadable, linked, and candidate-bound."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/ownership-contract.json",
    "references/runtime-policy.json",
    "references/project-platform-contract.json",
    "references/artifact-contract.json",
    "references/semantic-plan.schema.json",
    "references/route-contract.json",
    "references/state-machine.json",
    "references/state.schema.json",
    "references/receipt.schema.json",
    "references/recovery-receipt.schema.json",
    "references/rule-atom.schema.json",
    "references/capability-packet-registry.json",
    "references/release-policy.json",
    "references/release-manifest.schema.json",
    "references/migration/v9-capability-baseline.json",
    "references/migration/legacy-coverage.json",
    "references/migration/capability-crosswalk.json",
    "references/migration/clause-preservation.json",
    "references/migration/v15-preservation-ledger.json",
    "references/preservation/legacy-executable-retirement.json",
    "references/preservation/v15-0-1-platform-hotfix.json",
    "evals/v15-regression-cases.json",
    "evals/release/release-plan.json",
    "evals/release/release-state.json",
    "scripts/validate_v15_package.py",
    "scripts/validate_v15_contracts.py",
    "scripts/run_v15_scenarios.py",
    "scripts/validate_release.py",
    "scripts/freeze_release.py",
)
LINK_RE = re.compile(r"\]\(([^)#]+)(?:#[^)]+)?\)")


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    errors: list[str] = []
    evidence: dict[str, int | str] = {}

    missing = [item for item in REQUIRED if not (root / item).is_file()]
    errors.extend(f"required_missing:{item}" for item in missing)
    evidence["required_files"] = len(REQUIRED) - len(missing)

    retirement_path = root / "references/preservation/legacy-executable-retirement.json"
    retired_paths: list[str] = []
    if retirement_path.is_file():
        try:
            retirement = json.loads(retirement_path.read_text(encoding="utf-8"))
            for group in retirement.get("retired_groups", []):
                if isinstance(group, dict):
                    retired_paths.extend(
                        item for item in group.get("paths", []) if isinstance(item, str)
                    )
        except Exception as exc:
            errors.append(f"retirement_decision_unreadable:{exc}")
    revived = sorted({item for item in retired_paths if (root / item).exists()})
    errors.extend(f"retired_path_still_shipped:{item}" for item in revived)
    evidence["retired_paths_declared"] = len(set(retired_paths))
    evidence["retired_paths_still_shipped"] = len(revived)

    symlinks = [
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*")) if path.is_symlink()
    ]
    errors.extend(f"symlink_forbidden:{item}" for item in symlinks)
    evidence["symlinks"] = len(symlinks)

    bytecode_artifacts = [
        path.relative_to(root).as_posix()
        for path in sorted(root.rglob("*"))
        if path.name == "__pycache__" or (path.is_file() and path.suffix == ".pyc")
    ]
    errors.extend(f"bytecode_artifact_forbidden:{item}" for item in bytecode_artifacts)
    evidence["bytecode_artifacts"] = len(bytecode_artifacts)

    json_count = 0
    for path in sorted(root.rglob("*.json")):
        if path.is_symlink():
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
            json_count += 1
        except Exception as exc:
            errors.append(f"json_unreadable:{path.relative_to(root).as_posix()}:{exc}")
    evidence["json_files_parsed"] = json_count

    python_count = 0
    scripts = root / "scripts"
    if scripts.is_dir():
        for path in sorted(scripts.glob("*.py")):
            try:
                source = path.read_text(encoding="utf-8")
                compile(source, path.as_posix(), "exec", dont_inherit=True)
                python_count += 1
            except Exception as exc:
                errors.append(f"python_unloadable:{path.name}:{exc}")
    evidence["python_files_compiled_in_memory"] = python_count

    skill_path = root / "SKILL.md"
    skill = skill_path.read_text(encoding="utf-8") if skill_path.is_file() else ""
    frontmatter = skill.split("---", 2)[1] if skill.startswith("---") and skill.count("---") >= 2 else ""
    versions = re.findall(r'(?m)^\s{2}version:\s*["\']?([^"\'\s]+)["\']?\s*$', frontmatter)
    releases = re.findall(r'(?m)^\s{2}release:\s*["\']?([^"\'\s]+)["\']?\s*$', frontmatter)
    if versions != ["15.0.1"] or releases != ["candidate"]:
        errors.append("skill_candidate_identity_invalid")
    evidence["skill_version"] = versions[0] if len(versions) == 1 else "invalid"

    linked = sorted(set(LINK_RE.findall(skill)))
    for relative in linked:
        if relative.startswith(("http://", "https://")):
            continue
        target = (root / relative).resolve()
        if root not in target.parents and target != root:
            errors.append(f"skill_link_outside_package:{relative}")
        elif not target.exists():
            errors.append(f"skill_link_missing:{relative}")
    evidence["skill_links_checked"] = len(linked)

    agent_path = root / "agents/openai.yaml"
    agent = agent_path.read_text(encoding="utf-8") if agent_path.is_file() else ""
    if "V15.0.1" not in agent:
        errors.append("agent_candidate_identity_invalid")
    if (root / "evals/release/frozen-manifest.json").exists():
        errors.append("candidate_contains_frozen_manifest")

    result = {
        "schema_version": "15.0",
        "driver": "package",
        "status": "pass" if not errors else "fail",
        "checks": [
            "PACKAGE.V15.REQUIRED",
            "PACKAGE.V15.JSON",
            "PACKAGE.V15.PYTHON",
            "PACKAGE.V15.IDENTITY_AND_LINKS",
        ],
        "evidence": evidence,
        "errors": sorted(set(errors)),
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
