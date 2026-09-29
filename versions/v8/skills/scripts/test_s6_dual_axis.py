#!/usr/bin/env python3
"""Behavior regressions for mandatory V3, bounded V4, and paper visibility."""
from pathlib import Path
from validate_s6_dual_axis import validate

def main():
    root=Path(__file__).resolve().parents[1]; errors=validate(root)
    if errors: raise AssertionError(f"live S6 dual-axis contract failed: {errors}")
    v=(root/"rules/32-verification-minimum.md").read_text(encoding="utf-8"); m=(root/"rules/25-model-results-acceptance.md").read_text(encoding="utf-8"); p=(root/"rules/03-paper-content-rules.md").read_text(encoding="utf-8"); u=(root/"rules/36-uncertainty-error-analysis.md").read_text(encoding="utf-8")
    cases={"v3_not_optional":"V3没有`not_triggered`状态" in v and "若没有V3证据，不得关闭S6" in m,"v1_v2_not_v4":"不得用代码同值、数值误差界" in u,"paper_each_question":"每问至少一项实质模型检验" in p and "模型评价章节也不能替代" in p,"sensitivity_not_mandatory":"灵敏度分析不是固定必选项" in p,"engineering_checks_do_not_count":"内部哈希、字段对账、再次代入同一公式" in p}
    failed=[k for k,x in cases.items() if not x]
    if failed: raise AssertionError(f"S6 behavior guards missing: {failed}")
    print("PASS: S6 rejects optional V3, false V4, engineering-only paper checks, and mandatory sensitivity")
if __name__=="__main__": main()
