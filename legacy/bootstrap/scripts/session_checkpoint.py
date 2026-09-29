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

    if current_stage is None and legacy_stage is not None:
        state["current_stage"] = legacy_stage
    if current_status is None and legacy_status is not None:
        state["stage_status"] = legacy_status

    updates = {
        "current_stage": resolved_stage,
        "stage_status": resolved_status,
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

    state.pop("current_phase", None)
    state.pop("phase_status", None)
    state["schema_version"] = "1.2"
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
