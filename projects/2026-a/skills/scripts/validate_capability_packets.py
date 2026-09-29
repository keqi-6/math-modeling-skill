#!/usr/bin/env python3
"""Validate V15 capability coverage, packet reachability, and archive integrity."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


LINK_RE = re.compile(r"\]\(([^)#]+)(?:#[^)]+)?\)")
HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def skill_root(raw: Path) -> Path:
    root = raw.resolve()
    return root / "skills" if (root / "skills/SKILL.md").is_file() else root


def markdown_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    for heading in HEADING_RE.findall(text):
        plain = re.sub(r"[`*_~]", "", heading).strip().lower()
        plain = re.sub(r"[^\w\u4e00-\u9fff\- ]", "", plain)
        anchors.add(re.sub(r"-+", "-", plain.replace(" ", "-")))
    return anchors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = skill_root(args.root)
    errors: list[str] = []

    registry_path = root / "references/capability-packet-registry.json"
    if not registry_path.is_file():
        print(json.dumps({"status": "fail", "errors": ["registry_missing"]}, sort_keys=True))
        return 1
    registry = load(registry_path)

    active_capabilities: set[str] = set()
    active_atoms = 0
    for rule_path in sorted((root / "rules").glob("*.json")):
        bundle = load(rule_path)
        for atom in bundle.get("rules", []):
            if atom.get("status") == "active":
                active_atoms += 1
                capability = atom.get("capability")
                if not isinstance(capability, str) or not capability:
                    errors.append(f"active_atom_without_capability:{rule_path.name}:{atom.get('id')}")
                else:
                    active_capabilities.add(capability)

    route_contract = load(root / "references/route-contract.json")
    route_ids = {item.get("id") for item in route_contract.get("routes", [])}
    packet_ids: set[str] = set()
    packet_paths: set[str] = set()
    packet_capabilities: set[str] = set()
    router_to_packets: dict[str, set[str]] = {}

    for packet in registry.get("packets", []):
        packet_id = packet.get("id")
        path = packet.get("path")
        router = packet.get("router")
        if packet_id in packet_ids:
            errors.append(f"duplicate_packet_id:{packet_id}")
        packet_ids.add(packet_id)
        if path in packet_paths:
            errors.append(f"duplicate_packet_path:{path}")
        packet_paths.add(path)
        if not isinstance(path, str) or not path.startswith("references/capability-packets/"):
            errors.append(f"packet_outside_packet_tree:{packet_id}:{path}")
        elif not (root / path).is_file():
            errors.append(f"packet_missing:{packet_id}:{path}")
        if not isinstance(router, str) or not (root / router).is_file():
            errors.append(f"router_missing:{packet_id}:{router}")
        else:
            router_to_packets.setdefault(router, set()).add(path)
        capabilities = packet.get("capabilities", [])
        if not capabilities:
            errors.append(f"packet_without_capability:{packet_id}")
        packet_capabilities.update(item for item in capabilities if isinstance(item, str))

    contract_capabilities: set[str] = set()
    for coverage in registry.get("contract_coverage", []):
        contract_capabilities.update(
            item for item in coverage.get("capabilities", []) if isinstance(item, str)
        )
        for resource in coverage.get("resources", []):
            if not (root / resource).is_file():
                errors.append(f"contract_resource_missing:{coverage.get('id')}:{resource}")

    covered = packet_capabilities | contract_capabilities
    for capability in sorted(active_capabilities - covered):
        errors.append(f"active_capability_uncovered:{capability}")
    for capability in sorted(covered - active_capabilities):
        errors.append(f"registry_unknown_capability:{capability}")

    declared_routers = set(registry.get("routers", []))
    for router in sorted(declared_routers):
        router_path = root / router
        if not router_path.is_file():
            errors.append(f"declared_router_missing:{router}")
            continue
        linked: set[str] = set()
        for target in LINK_RE.findall(router_path.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://")):
                continue
            try:
                linked.add((router_path.parent / target).resolve().relative_to(root).as_posix())
            except ValueError:
                errors.append(f"router_link_outside_skill:{router}:{target}")
        for packet_path in sorted(router_to_packets.get(router, set()) - linked):
            errors.append(f"packet_unreachable_from_router:{router}:{packet_path}")

    for route in route_contract.get("routes", []):
        route_id = route.get("id")
        if not isinstance(route_id, str):
            errors.append(f"invalid_route_id:{route_id}")
        for context in route.get("context_refs", []):
            ref = context.get("ref")
            if not isinstance(ref, str):
                errors.append(f"invalid_context_ref:{route_id}:{ref}")
                continue
            path_text, _, anchor = ref.partition("#")
            context_path = root / path_text
            if not context_path.is_file():
                errors.append(f"route_context_missing:{route_id}:{path_text}")
                continue
            if anchor and context_path.suffix.lower() == ".md":
                anchors = markdown_anchors(context_path.read_text(encoding="utf-8"))
                if anchor.lower() not in anchors:
                    errors.append(f"route_context_anchor_missing:{route_id}:{ref}")

    for source in registry.get("historical_sources", []):
        path = source.get("path")
        source_path = root / path if isinstance(path, str) else root / "__invalid__"
        if not source_path.is_file():
            errors.append(f"historical_source_missing:{path}")
            continue
        expected = source.get("sha256")
        if expected and sha256(source_path) != expected:
            errors.append(f"historical_source_hash_mismatch:{path}")

    result = {
        "schema_version": "15.0",
        "driver": "capability_packets",
        "status": "pass" if not errors else "fail",
        "checks": [
            "PACKETS.ACTIVE_CAPABILITY_COVERAGE",
            "PACKETS.ROUTER_REACHABILITY",
            "PACKETS.CONTRACT_BOUNDARY",
            "PACKETS.HISTORICAL_ARCHIVE_INTEGRITY"
        ],
        "evidence": {
            "active_atoms": active_atoms,
            "active_capabilities": len(active_capabilities),
            "packet_count": len(packet_ids),
            "packet_covered_capabilities": len(packet_capabilities),
            "contract_covered_capabilities": len(contract_capabilities),
            "declared_routers": len(declared_routers),
            "known_routes": len(route_ids)
        },
        "errors": sorted(set(errors))
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
