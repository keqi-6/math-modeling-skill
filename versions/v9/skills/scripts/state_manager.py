#!/usr/bin/env python3
"""Atomically validate and update the single V9 project state."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_contract() -> dict[str, Any]:
    return json.loads((SKILL_ROOT / "references" / "state-contract.json").read_text(encoding="utf-8"))


def load_state(root: Path) -> tuple[Path, dict[str, Any]]:
    path = root.resolve() / ".modeling" / "state.json"
    if not path.is_file():
        raise FileNotFoundError(f"state does not exist: {path}")
    state = json.loads(path.read_text(encoding="utf-8"))
    validate_state(state)
    return path, state


def validate_state(state: dict[str, Any]) -> None:
    contract = load_contract()
    missing = [field for field in contract["project_state_required_fields"] if field not in state]
    if missing:
        raise ValueError(f"missing state fields: {missing}")
    seen: set[str] = set()
    for component in state["components"]:
        component_id = component.get("id")
        component_type = component.get("type")
        component_state = component.get("state")
        if not component_id or component_id in seen:
            raise ValueError(f"missing or duplicate component id: {component_id}")
        seen.add(component_id)
        if component_type not in contract["component_types"]:
            raise ValueError(f"unknown component type: {component_type}")
        if component_state not in contract["component_types"][component_type]["states"]:
            raise ValueError(f"invalid state {component_state} for {component_type}")


def atomic_write(path: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    validate_state(state)
    payload = json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    fd, temporary = tempfile.mkstemp(prefix="state.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def require_authorized(authorized: bool) -> None:
    if not authorized:
        raise PermissionError("state mutation requires --authorized")


def add_component(root: Path, component_id: str, component_type: str, state_name: str, authorized: bool) -> None:
    require_authorized(authorized)
    path, state = load_state(root)
    contract = load_contract()
    if component_type not in contract["component_types"]:
        raise ValueError(f"unknown component type: {component_type}")
    states = contract["component_types"][component_type]["states"]
    if state_name != states[0]:
        raise ValueError(f"new {component_type} component must start at {states[0]}")
    if any(item["id"] == component_id for item in state["components"]):
        raise ValueError(f"component already exists: {component_id}")
    state["components"].append({"id": component_id, "type": component_type, "state": state_name, "evidence": {}, "consumers": []})
    atomic_write(path, state)


def parse_evidence(values: list[str]) -> dict[str, str]:
    evidence: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"evidence must be key=reference: {value}")
        key, reference = value.split("=", 1)
        if not key or not reference:
            raise ValueError(f"evidence must be key=reference: {value}")
        evidence[key] = reference
    return evidence


def transition(root: Path, component_id: str, target: str, evidence_values: list[str], authorized: bool) -> None:
    require_authorized(authorized)
    path, state = load_state(root)
    contract = load_contract()
    component = next((item for item in state["components"] if item["id"] == component_id), None)
    if component is None:
        raise ValueError(f"unknown component: {component_id}")
    machine = contract["component_types"][component["type"]]
    before = component["state"]
    if target not in machine["transitions"].get(before, []):
        raise ValueError(f"illegal transition: {before}->{target}")
    evidence = parse_evidence(evidence_values)
    required = set(machine.get("entry_evidence", {}).get(target, []))
    if not required.issubset(evidence):
        raise ValueError(f"missing transition evidence: {sorted(required - set(evidence))}")
    component.setdefault("evidence", {}).update(evidence)
    component["state"] = target
    atomic_write(path, state)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def register_artifact(
    root: Path,
    relative: str,
    artifact_class: str,
    consumer: str,
    purpose: str,
    lifecycle: str,
    authorization_basis: str,
    component_ids: list[str],
    validations: list[str],
    authorized: bool,
) -> None:
    require_authorized(authorized)
    root = root.resolve()
    path, state = load_state(root)
    artifact_contract = json.loads((SKILL_ROOT / "references" / "artifact-contract.json").read_text(encoding="utf-8"))
    if artifact_class not in artifact_contract["artifact_classes"]:
        raise ValueError(f"unknown artifact class: {artifact_class}")
    candidate = (root / relative).resolve()
    try:
        relative_path = candidate.relative_to(root).as_posix()
    except ValueError as exc:
        raise ValueError("artifact must stay inside project root") from exc
    if not candidate.is_file():
        raise FileNotFoundError(f"artifact does not exist: {candidate}")
    known_components = {item["id"] for item in state["components"]}
    if not component_ids or not set(component_ids).issubset(known_components):
        raise ValueError("artifact component_ids must reference existing components")
    if artifact_class == "formal" and not validations:
        raise ValueError("formal artifact requires at least one validation reference")
    if any(item.get("path") == relative_path for item in state["artifacts"]):
        raise ValueError(f"artifact already registered: {relative_path}")
    state["artifacts"].append(
        {
            "path": relative_path,
            "sha256": file_sha256(candidate),
            "artifact_class": artifact_class,
            "consumer": consumer,
            "purpose": purpose,
            "lifecycle": lifecycle,
            "authorization_basis": authorization_basis,
            "component_ids": sorted(set(component_ids)),
            "validation": validations,
        }
    )
    atomic_write(path, state)


def set_next_action(root: Path, component_id: str, action: str, authorized: bool) -> None:
    require_authorized(authorized)
    path, state = load_state(root)
    if component_id not in {item["id"] for item in state["components"]}:
        raise ValueError(f"unknown component: {component_id}")
    state["next_actions"] = [item for item in state["next_actions"] if item.get("component_id") != component_id]
    state["next_actions"].append({"component_id": component_id, "action": action})
    atomic_write(path, state)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    validate_parser = sub.add_parser("validate")
    validate_parser.add_argument("--root", type=Path, required=True)

    add = sub.add_parser("add-component")
    add.add_argument("--root", type=Path, required=True)
    add.add_argument("--id", required=True)
    add.add_argument("--type", required=True)
    add.add_argument("--state", required=True)
    add.add_argument("--authorized", action="store_true")

    move = sub.add_parser("transition")
    move.add_argument("--root", type=Path, required=True)
    move.add_argument("--id", required=True)
    move.add_argument("--to", required=True)
    move.add_argument("--evidence", action="append", default=[])
    move.add_argument("--authorized", action="store_true")

    artifact = sub.add_parser("register-artifact")
    artifact.add_argument("--root", type=Path, required=True)
    artifact.add_argument("--path", required=True)
    artifact.add_argument("--artifact-class", required=True)
    artifact.add_argument("--consumer", required=True)
    artifact.add_argument("--purpose", required=True)
    artifact.add_argument("--lifecycle", required=True)
    artifact.add_argument("--authorization-basis", required=True)
    artifact.add_argument("--component", action="append", default=[])
    artifact.add_argument("--validation", action="append", default=[])
    artifact.add_argument("--authorized", action="store_true")

    next_parser = sub.add_parser("set-next-action")
    next_parser.add_argument("--root", type=Path, required=True)
    next_parser.add_argument("--id", required=True)
    next_parser.add_argument("--action", required=True)
    next_parser.add_argument("--authorized", action="store_true")
    args = parser.parse_args()

    try:
        if args.command == "validate":
            _, state = load_state(args.root)
            print(json.dumps({"status":"PASS","components":len(state["components"]),"artifacts":len(state["artifacts"])}, ensure_ascii=False))
        elif args.command == "add-component":
            add_component(args.root, args.id, args.type, args.state, args.authorized)
            print(json.dumps({"status":"PASS","action":"add-component","id":args.id}, ensure_ascii=False))
        elif args.command == "transition":
            transition(args.root, args.id, args.to, args.evidence, args.authorized)
            print(json.dumps({"status":"PASS","action":"transition","id":args.id,"to":args.to}, ensure_ascii=False))
        elif args.command == "register-artifact":
            register_artifact(args.root, args.path, args.artifact_class, args.consumer, args.purpose, args.lifecycle, args.authorization_basis, args.component, args.validation, args.authorized)
            print(json.dumps({"status":"PASS","action":"register-artifact","path":args.path}, ensure_ascii=False))
        elif args.command == "set-next-action":
            set_next_action(args.root, args.id, args.action, args.authorized)
            print(json.dumps({"status":"PASS","action":"set-next-action","id":args.id}, ensure_ascii=False))
    except (PermissionError, FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status":"FAIL","error":str(exc)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

