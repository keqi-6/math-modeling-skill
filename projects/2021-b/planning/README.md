# planning 目录权威地图

本目录保存当前项目的人工决策、题意、数据、方法与执行计划。聊天记录、根目录
`README.md` 和 `project_state.json` 只用于导航，不能替代这里的证据与决定。

格式规则：本目录所有 `.md` 文件只使用 Markdown 语法。数学关系使用普通文字、代码
片段、Markdown表格或引用块表达，不嵌入LaTeX命令；仅最终 `paper/*.tex` 使用LaTeX。

| 文件 | 职责 | 当前状态 |
|---|---|---|
| `project_plan.md` | 全项目必要步骤、每问S1—S12子阶段清单、阶段门、排程与完成判据 | 当前执行权威 |
| `source_inventory.md` | 官方输入、规则来源、哈希、阅读与归档状态 | 数据内容审计完成 |
| `understanding.md` | 题意、概念、已知量、未知量、歧义与数据能力边界 | 第1步已由用户确认 |
| `task_matrix.md` | 原题四问的输入、输出、依赖、模型与验证状态 | 第1步已由用户确认 |
| `terminology.md` | 正文、图表、方法文档和交付镜像采用的唯一术语与表述口径 | 当前执行权威 |
| `data_audit_methodology.md` | 第2步审计、预处理、异常诊断、制图和独立复核方法 | 已由用户确认并完成实现 |
| `inspiration.md` | 文献和方法启发及其证据边界 | 按当前问题逐问补充 |
| `method_plan.md` | 各问候选模型、比较、数学规格、验证和依赖 | 按第（1）问至第（4）问依次建立；重要选择须由用户确认 |
| `interaction_log.md` | 会改变范围、模型、参数、验证、论文或交付的用户决策 | 持续记录 |
| `ai_usage_log.md` | AI工具用途、关键交互、采纳与人工修改的实时底稿 | 持续记录 |
| `work_log.md` | 实际执行、产物、验证与未解决问题 | 持续记录 |

第三问当前复审入口为
`analysis/2026-07-29_question3_s11_robustness_and_review.md`；负责人已完成S12确认，
对应正文位于`paper/draft/body_q3_analysis.tex`和`body_q3_model.tex`。

## 子目录约定

- `analysis/`：尚未获批的候选分析；不得直接进入论文或冻结结果。
- `audits/`：带日期的阶段性审计快照；文件更新后不能自动视为仍然有效。
- `archive/`：已经被新版本取代但为追溯而保留的规划。

当前审计：

- `audits/2026-07-31_manuscript59_authority_and_code_intake.md`：负责人确认以《59初稿》
  为底稿后的当前权威，记录代码接管标准、第一批新增脚本和验证结果。
- `audits/2026-07-31_teammate_59_draft_admission_audit.md`：新增28页队友初稿的方法、
  数字、术语、摘要、篇章和版面准入审计；这是用户决定前的风险记录，其中“不作为
  底稿”的建议已被后续明确决定取代。
- `audits/2026-07-31_full_recovery_and_teammate_draft_intake.md`：本窗口全项目恢复、当前
  导航修复、缺失镜像确认及新增 `<未收录-队友材料>/59初稿.pdf` 的接收与准入边界；这是当前
  恢复审计入口。
- `audits/2026-07-30_full_manuscript_module_audit.md`：第一至四问统一正文的逐模块职责、
  交叉引用、结论强度、编译和逐页审计；这是当前正文综合审计入口。
- `audits/2026-07-30_terminology_neighbor_explanation_audit.md`：当前19页正文的术语首次
  实质使用、邻近解释、去术语复述和页面复核；这是当前术语表达审计入口。
- `audits/2026-07-29_full_draft_language_rewrite.md`：当时第一、二问统一草稿的语言审计，
  现仅作历史阶段记录。

- `audits/2026-07-28_stage0_skill_gap.md`：第0步项目建立暴露的跨项目skill缺口、修正与验证。
- `audits/2026-07-28_stage2_skill_gap.md`：第2步数据方法论暴露的跨项目skill缺口、迁移边界与验证。
- `audits/2026-07-28_cross_question_workflow_skill_gap.md`：四问横向齐步造成认知过载的
  流程缺口、逐问纵向闭环修正与skill迁移。
- `audits/2026-07-28_literature_routing_skill_gap.md`：文献规则存在但逐问路由和初始化
  模板脱节的根因、四层修复与验证。
- `audits/2026-07-28_teammate_data_processing_review.md`：队友数据处理Word的只读取证、
  独立复算、方法缺陷与待用户采纳决定。
- `audits/2026-07-29_per_question_substage_skill_gap.md`：逐问清单未落地造成乱序的
  根因、skill四层修正、修改后重读与验证。
- `audits/2026-07-29_per_question_independence_skill_gap.md`：逐问执行仍可能复制上一问
  思维形状的缺口、必要独立性门、第二问回退和修订边界。
- `audits/2026-07-29_q1_freeze_and_markdown_rewrite.md`：第一问S12确认、核心证据哈希、
  旧稿归档和当时的 Markdown 正文决定；该决定后来已被统一 LaTeX 草稿取代，只作历史
  快照。
