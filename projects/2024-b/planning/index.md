# planning 目录权威地图（V11）

登记当前总计划、题意、数据、方法、交互决定与实时日志的唯一职责。待审分析放入
`analysis/`，阶段审计快照放入 `audits/`，被替代但需追溯的规划放入 `archive/`。
机器状态不再由本目录内的旧 JSON 推导；唯一机器权威是根目录
`.modeling/state.json`。本表只维护可读入口，不得把空模板或历史日志写成已完成权威。

格式边界：本目录只使用Markdown语法；数学关系用文字、代码、引用块或Markdown表格
表达。LaTeX语法只写入`paper/`目录树中的`.tex`源文件；内容草稿与正式论文的隔离、
产物准入和交付门以当前 `skills/SKILL.md` 及其 V11 合同为准。

## 当前权威入口

| 内容 | 当前入口 | 状态 |
|---|---|---|
| 项目机器状态 | `.modeling/state.json` | V11唯一机器权威；含精确证据绑定与受保护工件身份 |
| 项目暂停点与恢复顺序 | `HANDOFF.md`、`PROJECT.md` | 问题一至四均为S7关闭，`next_actions`为空；正式论文未启动 |
| 官方题意 | `B题/B题.pdf` | 唯一事实源 |
| 共享四问导航 | `planning/understanding.md`、`planning/task_matrix.md` | 当前有效 |
| 问题一 S1 | `planning/q1_understanding.md` | 重开后已确认，当前权威 |
| 问题一旧 S1 | `planning/archive/2026-08-23_q1_understanding_superseded.md` | 已失效，仅追溯 |
| 问题一旧 S2 至 S4 | `planning/analysis/README.md` 所列材料 | 已失效，仅追溯 |
| 问题一当前 S3 方法 | `planning/analysis/2026-08-23_q1_s3_approved_separate_sequential.md` | 已确认，当前方法权威 |
| 问题一数学合同审计 | `planning/analysis/2026-08-23_q1_separate_sequential_contract_audit.md` | 当前有效 |
| 问题一当前 S4 规格 | `planning/analysis/2026-08-23_q1_s4_separate_sequential_specification.md` | 已确认，当前数学合同权威 |
| 问题一完整动作空间重开决定 | `planning/analysis/2026-08-25_q1_full_action_redesign_decision.md` | 当前权威；加入事实双向停止并重开问题一 |
| 问题一当前S3方法 | `planning/analysis/2026-08-25_q1_s3_complete_action_decision.md` | 已确认；分情景统计动作+双侧事实停止 |
| 问题一当前S4规格 | `planning/analysis/2026-08-25_q1_s4_complete_action_specification.md`、`planning/audits/2026-08-25_q1_s4_complete_action_closure.md` | 已确认；当前数学合同权威 |
| 问题一当前S5实现 | `planning/analysis/2026-08-25_q1_s5_complete_action_implementation.md`、`src/q1/`、`output/q1/s5_results.json`、`s5_finite_closure.json`、`s5_acceptance.json` | 98/98同实现验收通过；N=10/23阈值类最优 |
| 问题一当前S6验证 | `planning/analysis/2026-08-25_q1_s6_independent_verification.md`、`output/q1/s6_independent_verification.json` | 394/394独立检查通过；已人工接受并关闭S6 |
| 问题一旧单向S1至S6 | `planning/q1_understanding.md`（题意仍权威）、`planning/archive/`与旧S5/S6产物 | 旧单向方法/规格/结果已失效，只供追溯 |
| 问题一主张映射 | `planning/q1_claim_test_paper_map.md` | 完整动作空间口径，已重写 |
| 问题一队友讲解稿 | `docs/q1/solution_brief.md` | 完整动作空间口径，已重写（44组编号公式） |
| 问题二 S1 | `planning/q2_understanding.md`、`planning/audits/2026-08-23_q2_s1_closure.md` | 已关闭；前者为唯一题意权威 |
| 问题二 S2 | `planning/analysis/2026-08-23_q2_s2_assessment.md`、`planning/audits/2026-08-23_q2_s2_closure.md` | 已关闭；数据、证据与基线权威 |
| 问题二 S3 | `planning/analysis/2026-08-23_q2_s3_approved_exact_recursion.md`、`planning/audits/2026-08-23_q2_s3_closure.md` | 已关闭；精确状态递推为方法权威 |
| 问题二 S4 | `planning/analysis/2026-08-23_q2_s4_specification.md`、`planning/audits/2026-08-23_q2_s4_closure.md` | 已关闭；前者为数学规格权威 |
| 问题二 S5 | `planning/analysis/2026-08-23_q2_s5_implementation.md`、`planning/audits/2026-08-23_q2_s5_closure.md`、`src/q2/`、`output/q2/` | 已关闭；冻结产物进入S6 |
| 问题二 S6 | `planning/analysis/2026-08-23_q2_s6_independent_verification.md`、`docs/q2/solution_brief.md`、`planning/audits/2026-08-24_q2_s6_closure.md`、`planning/q2_claim_test_paper_map.md` | 已关闭；条件性结果、讲解稿人工门和主张映射冻结 |
| 问题三 S1 | `planning/q3_understanding.md`、`planning/audits/2026-08-24_q3_s1_closure.md` | 已关闭；前者为唯一题意权威 |
| 问题三 S2 | `planning/analysis/2026-08-24_q3_s2_assessment.md`、`planning/analysis/2026-08-24_q3_s2_review.md`、`planning/audits/2026-08-24_q3_s2_closure.md` | 已关闭；前者为当前数据与证据权威 |
| 问题三 S3 | `planning/analysis/2026-08-24_q3_s3_approved_exact_graph_evaluation.md`、`planning/audits/2026-08-24_q3_s3_closure.md` | 已关闭；精确图状态评价为方法权威 |
| 问题三 S4 | `planning/analysis/2026-08-24_q3_s4_specification.md`、`planning/audits/2026-08-24_q3_s4_closure.md` | 已关闭；规格为当前数学合同 |
| 问题三 S5 | S5实现记录、关闭审计、`src/q3/`、`output/q3/` | 已关闭；冻结产物进入S6 |
| 问题三 S6 | S6分析、数值复算产物、`docs/q3/solution_brief.md`、主张映射、重构决定 | 25情形E1至E4与人工门闭合；组件已进入S7 |
| 问题四 S1 | `planning/understanding.md`的问题四S1节 | 已关闭；题意与范围权威 |
| 问题四 S2 | `planning/analysis/2026-08-24_q4_s2_wp1_wp2_audit.md`、`planning/analysis/2026-08-24_q4_s2_wp3_wp4_decision_package.md` | 四个工作包已闭合；不构成方法批准 |
| 问题四 S3 | `planning/analysis/2026-08-24_q4_s3_approved_light_loop.md`、`planning/audits/2026-08-24_q4_s3_closure.md` | 已批准问题一轻闭环；不含S4规格或样本情景 |
| 问题四 S4 | S4规格、审查与关闭审计 | 已关闭；单率区间、五组设置和完整离散传播为数学合同 |
| 问题四 S5 | S5实现记录、关闭审计、`src/q4/`、`output/q4/` | 已关闭；完整结果与38项同实现验收冻结 |
| 问题四 S6 | S6验证报告、`docs/q4/solution_brief.md`、主张映射、结构化结果及`planning/analysis/2026-08-25_q4_q1_interface_revalidation.md` | 已按问题三新名义策略复算、重绑定；问题一完整动作空间重开后完成定向接口重验，无需重算并恢复为`S7/closed` |
| 问题四历史候选 | `planning/analysis/2026-08-24_q4_two_sided_sampling_interface_candidate.md` | 未通过，只是S2审计输入之一 |

按V11状态机，问题一（完整动作空间口径）、问题二、问题三、问题四均为`S7/closed`；
机器状态中的`next_actions`为空。正式论文未启动，项目保持`P0`。旧问题二审计
`planning/audits/2026-08-23_q2_solution_brief_audit.md`、问题一旧单向动作空间的S3/S4/
S5/S6记录均已失效，只供追溯。

`planning/project_plan.md`与`planning/method_plan.md`保留问题四进入S1前的历史快照；
涉及问题四当前阶段时，以`.modeling/state.json`、本索引和`planning/understanding.md`为准。

控制器回退档案为`planning/archive/v10_project_state_2026-08-24.json`；旧根状态为
`planning/archive/legacy_project_state_pre_v9_rebuild.json`；本次迁移前V9状态为
`planning/archive/v9_project_state_2026-08-24_pre_v11.json`。三者都不是当前机器状态。
