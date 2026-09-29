#!/usr/bin/env python3
"""Validate the S6 solution-verification/model-examination contract."""
from __future__ import annotations
import json
from pathlib import Path

def validate(root: Path) -> list[str]:
    errors=[]
    paths={"controller":root/"SKILL.md","verification":root/"rules/32-verification-minimum.md","model":root/"rules/25-model-results-acceptance.md","paper":root/"rules/03-paper-content-rules.md","manuscript":root/"rules/33-manuscript-minimum.md","uncertainty":root/"rules/36-uncertainty-error-analysis.md"}
    texts={k:p.read_text(encoding="utf-8") for k,p in paths.items()}
    required={"controller":["mandatory V3 model-structure examination","close a question without V3 evidence","claim-to-model-test"],"verification":["S6双轴最低合同","V3没有`not_triggered`状态","V4可按题面理想用途记为","每一问至少展示一项"],"model":["S-09A S6双轴与模型结构硬门","若没有V3证据，不得关闭S6","内部哈希、字段对账、重复"],"paper":["每问至少一项实质模型检验","灵敏度分析不是固定必选项","模型评价章节也不能替代"],"manuscript":["substantive model examination","for every question show at least one test","do not force a section named"],"uncertainty":["U-03A 与S6模型检验双轴的边界","V3不得记为`not_triggered`","V4记为`not_triggered`","至少一项实质模型检验"]}
    for owner,phrases in required.items():
        for phrase in phrases:
            if phrase not in texts[owner]: errors.append(f"{owner} missing S6 dual-axis guard: {phrase}")
    registry=json.loads((root/"references/routing-registry.json").read_text(encoding="utf-8")); route=next((x for x in registry["triggers"] if x["trigger_id"]=="TR-VERIFY"),None)
    if route is None: errors.append("routing registry missing TR-VERIFY")
    else:
        evidence=" ".join(route.get("expected_evidence",[]))
        for phrase in ("V1 implementation-conformity","mandatory V3 model-structure","V4 reality-confirmation","claim-to-model-test"):
            if phrase not in evidence: errors.append(f"TR-VERIFY missing evidence guard: {phrase}")
    return errors

def main():
    errors=validate(Path(__file__).resolve().parents[1])
    if errors:
        for error in errors: print(f"FAIL: {error}")
        raise SystemExit(1)
    print("PASS: S6 dual-axis, mandatory V3, bounded V4, and per-question paper visibility")
if __name__=="__main__": main()
