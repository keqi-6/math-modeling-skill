# 源码导航

《59初稿》的统一复现入口为 `run_manuscript59_pipeline.py`，17表3图与真实生产者的
逐项映射见 `docs/59_draft_code_map.md`。

| 路径 | 职责 | 当前状态 |
|---|---|---|
| `data_audit/` | 从官方Excel生成清洁表、审计表和数据图 | 已实现并独立核对 |
| `eda/` | 在批准的离散研究边界内进行共享探索 | 已实现并独立核对 |
| `q1/` | 第一问相邻变化、逐组合回归、图件和独立核对 | 已完成，19项复算通过 |
| `q2/` | 第二问直接比较、加和分解、结构删除检查及独立复算 | 已完成，5+13+9项复算通过 |
| `q3/candidates/` | 第三问统一模型可行性隔离候选及独立复算 | 候选审计完成，未批准为正式模型 |
| `q3/candidates/03_narrow_pchip_candidate.py`、`04_verify_narrow_pchip_candidate.py` | 第三问同组合窄PCHIP候选及独立复算 | S6完成，等待S7决定 |
| `q3/01_observed_baseline.py`、`q3/02_verify_observed_baseline.py` | 第三问两种情景的D0实测枚举与独立复算 | S5基线实现 |
| `q4/01_build_formal_design.py` | 第四问正式五次实验设计、证据映射和更新规则 | S9实现，等待S10独立验证 |
| `q4/02_verify_formal_design.py` | 第四问正式设计的独立复算与边界检查 | S10独立验证 |
| `q4/03_robustness_and_explanation.py`、`q4/04_verify_robustness.py` | 第四问删点、替代政策和设备边界稳健性及独立复核 | S11 |
| `_utils/` | 跨问题共享工具 | 按需使用 |

第二问正式实现位于 `q2/03_additive_effects.py` 和 `q2/05_structural_robustness.py`；
`q2/candidates/` 只保留未进入正式方法的候选比较。
`q3/candidates/` 同样只用于正式方法决定前的分块预测审计，不产生论文推荐。

每个产生结论的脚本必须把结果写入 `../output/`，不能只在控制台打印。
