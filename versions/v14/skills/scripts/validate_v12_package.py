#!/usr/bin/env python3
"""Small V12 package-load gate: existence, JSON parsing, Python compilation, links."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REQUIRED = (
    "SKILL.md",
    "agents/openai.yaml",
    "references/ownership-contract.json",
    "references/project-platform-contract.json",
    "references/artifact-contract.json",
    "references/release-policy.json",
    "references/migration/platform-restoration.json",
    "evals/platform-outcomes.json",
    "evals/release/release-plan.json",
    "evals/release/release-state.json",
    "scripts/artifact_guard.py",
    "scripts/state_manager.py",
    "scripts/validate_release.py",
)


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    errors: list[str] = []
    evidence: dict[str, int] = {}

    missing = [item for item in REQUIRED if not (root / item).is_file()]
    errors.extend(f"required_missing:{item}" for item in missing)
    evidence["required_files"] = len(REQUIRED) - len(missing)

    json_count = 0
    for path in sorted(root.rglob("*.json")):
        if path.is_symlink():
            errors.append(f"symlink_forbidden:{path.relative_to(root).as_posix()}")
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
            json_count += 1
        except Exception as exc:
            errors.append(f"json_unreadable:{path.relative_to(root).as_posix()}:{exc}")
    evidence["json_files_parsed"] = json_count

    python_count = 0
    for path in sorted((root / "scripts").glob("*.py")):
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, path.as_posix(), "exec", dont_inherit=True)
            python_count += 1
        except Exception as exc:
            errors.append(f"python_unloadable:{path.name}:{exc}")
    evidence["python_files_compiled_in_memory"] = python_count

    skill = (root / "SKILL.md").read_text(encoding="utf-8") if (root / "SKILL.md").is_file() else ""
    linked = sorted(set(re.findall(r"\]\(([^)#]+)(?:#[^)]+)?\)", skill)))
    for relative in linked:
        if relative.startswith(("http://", "https://")):
            continue
        if not (root / relative).exists():
            errors.append(f"skill_link_missing:{relative}")
    evidence["skill_links_checked"] = len(linked)

    result = {
        "schema_version": "12.0",
        "driver": "package",
        "status": "pass" if not errors else "fail",
        "checks": ["PACKAGE.REQUIRED", "PACKAGE.JSON", "PACKAGE.PYTHON", "PACKAGE.SKILL_LINKS"],
        "evidence": evidence,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
