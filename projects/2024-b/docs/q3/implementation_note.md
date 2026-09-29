# 问题三 S5 复现说明

在项目根目录运行：

```bash
python3 src/q3/01_solve.py
```

程序从`planning/analysis/2026-08-24_q3_s2_assessment.md`读取表2参数，按S4规范位序完整
生成65536套策略，并在名义情形与12个节点各自正负5个百分点的24个OAT情形下分别完整
评价。结果写入`output/q3/`：汇总见`s5_results.json`，1638400条候选见
`s5_candidates.jsonl.gz`，18项同实现验收见
`s5_acceptance.json`，文件哈希与运行环境见`s5_run_manifest.json`。

所有排序使用精确有理数。压缩账本可用`gzip -cd output/q3/s5_candidates.jsonl.gz`读取。
这些产物属于S5；其后已由`src/q3/02_verify_independent.py`完成不导入主核心的S6独立
复算，结果见`output/q3/s6_independent_verification.json`。当前V11问题三组件推进到
`S6/active`人工审阅门；负责人尚未确认本次重构结果，因此不得关闭到S7。
