#!/usr/bin/env python3
"""原子更新数学建模项目的机器可读会话检查点。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--component", default="shared_project")
    parser.add_argument("--stage")
    parser.add_argument("--stage-status")
    # 兼容旧调用；内部统一迁移为 stage 字段，不再写入 phase 字段。
    parser.add_argument("--phase")
    parser.add_argument("--phase-status")
    parser.add_argument("--last-completed")
    parser.add_argument("--pause-point")
    parser.add_argument("--next-action")
    parser.add_argument("--pending", action="append")
    parser.add_argument("--authority-audit")
    parser.add_argument("--affected-file", action="append")
    parser.add_argument("--timezone", default="Asia/Shanghai")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state_path = args.root.resolve() / "project_state.json"
    state = {}
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))

    legacy_stage = state.get("current_phase")
    current_stage = state.get("current_stage")
    if (
        legacy_stage is not None
        and current_stage is not None
        and legacy_stage != current_stage
    ):
        raise SystemExit(
            "状态冲突：current_stage 与旧字段 current_phase 不一致，请先人工裁决。"
        )

    legacy_status = state.get("phase_status")
    current_status = state.get("stage_status")
    if (
        legacy_status is not None
        and current_status is not None
        and legacy_status != current_status
    ):
        raise SystemExit(
            "状态冲突：stage_status 与旧字段 phase_status 不一致，请先人工裁决。"
        )

    if args.stage is not None and args.phase is not None and args.stage != args.phase:
        raise SystemExit("--stage 与兼容参数 --phase 不一致。")
    if (
        args.stage_status is not None
        and args.phase_status is not None
        and args.stage_status != args.phase_status
    ):
        raise SystemExit("--stage-status 与兼容参数 --phase-status 不一致。")

    resolved_stage = args.stage if args.stage is not None else args.phase
    resolved_status = (
        args.stage_status if args.stage_status is not None else args.phase_status
    )
    allowed_stages = {
        "S0_RECOVER", "S1_INTERPRET", "S2_ASSESS", "S3_DECIDE",
        "S4_SPECIFY", "S5_IMPLEMENT", "S6_VERIFY", "S7_PUBLISH",
    }
    allowed_statuses = {"not_started", "in_progress", "complete", "blocked"}
    if resolved_stage is not None and resolved_stage not in allowed_stages:
        raise SystemExit(f"无效阶段：{resolved_stage}")
    if resolved_status is not None and resolved_status not in allowed_statuses:
        raise SystemExit(f"无效状态：{resolved_status}")

    components = state.setdefault("components", {})
    component = components.setdefault(args.component, {})
    migrated_stage = current_stage if current_stage is not None else legacy_stage
    migrated_status = current_status if current_status is not None else legacy_status
    if "stage" not in component and migrated_stage is not None:
        component["stage"] = migrated_stage
    if "status" not in component and migrated_status is not None:
        component["status"] = migrated_status

    updates = {
        "last_completed_action": args.last_completed,
        "pause_point": args.pause_point,
        "next_action": args.next_action,
        "pending_user_decisions": args.pending,
        "current_authority_audit": args.authority_audit,
        "affected_files": args.affected_file,
    }
    for key, value in updates.items():
        if value is not None:
            state[key] = value

    if resolved_stage is not None:
        component["stage"] = resolved_stage
    if resolved_status is not None:
        component["status"] = resolved_status

    state.pop("current_phase", None)
    state.pop("phase_status", None)
    state.pop("current_stage", None)
    state.pop("stage_status", None)
    ordered = [
        "S0_RECOVER", "S1_INTERPRET", "S2_ASSESS", "S3_DECIDE",
        "S4_SPECIFY", "S5_IMPLEMENT", "S6_VERIFY", "S7_PUBLISH",
    ]
    rank = {stage: index for index, stage in enumerate(ordered)}
    open_stages = [
        item.get("stage") for item in components.values()
        if isinstance(item, dict)
        and item.get("stage") in rank
        and item.get("status") != "complete"
    ]
    earliest = min(open_stages, key=rank.get) if open_stages else "S7_PUBLISH"
    state["project_summary"] = {"earliest_open_state": earliest}
    state["schema_version"] = "2.0"
    state["checkpoint_updated_at"] = datetime.now(
        ZoneInfo(args.timezone)
    ).isoformat(timespec="seconds")

    temporary_path = state_path.with_suffix(".json.tmp")
    temporary_path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary_path, state_path)


if __name__ == "__main__":
    main()
