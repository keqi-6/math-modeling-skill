# 真实项目规则提取审计：2025 CUMCM A 题逐问队友讲解稿

> 记录类型：V15 候选的只读真实项目规则提取记录。  
> 定稿时间：2026-08-27T11:51:48+08:00。  
> 真实项目：`/mnt/d/AI/AI_program/2025（第八题）/A题`。  
> 审计对象：逐问队友讲解稿、写作边界、结果与验证消费者政策，以及它们在 V15 中的最小归属。  
> 变更边界：本轮未修改真实 A 题、其 `.modeling/state.json`、结果、代码或验证材料；除本文件外，本审计动作未修改 `skills_v15_candidate` 的其他文件。  
> preservation 边界：未读取本目录既有审计记录；仅确认本目标路径原先不存在后新建本文件。

## 1. 读取范围与 live state

### 1.1 完整读取

- `docs/q1/solution_brief.md`；
- `planning/00_scope_and_problem.md` 至 `planning/08_q2_problem_definition.md`；
- `.modeling/state.json` 中 Q1/Q2 组件、相关 evidence、open decisions、next actions 和对应 history；
- `docs/q1_implementation_and_verification.md`、`docs/q1_validation_report.md`、`docs/q1_model_validation_report.md`；
- `docs/q1_result.json` 中正式结果身份、未舍入结果、warning 与 run identity；
- V15 当前的模型实现/结果能力包、能力包登记、建模与项目路由、项目平台与工件合同、相关 modeling/delivery atoms。

### 1.2 定向读取的必要代码

- `src/q1/solve.py` 的报告生成、正式输出写入和 CLI 入口；
- `src/q1/verify.py` 的验证输出与 CLI 入口；
- `src/q1/validate_model.py` 的 E3/E4 报告生成、writing boundary 和输出入口；
- `src/q1/model.py` 的对象、主求值、区间求解和独立验证接口位置。

项目范围搜索没有发现生成或验证 `docs/q1/solution_brief.md` 的代码路径；现有 `build_report` 只生成内部技术报告。因此该 brief 是人工组织的技术说明，不是机器结果或 verifier 输出。

### 1.3 live state 观察

- 审计时权威状态为 revision `137`：`.modeling/state.json:L1-L6`。
- Q1 当前为 `S7/closed`：`.modeling/state.json:L172-L179`。
- revision 118 的 Q1 `S6→S7` 只要求 `E1_IMPLEMENTATION`、`E2_NUMERICAL`、`E3_STRUCTURAL`、`E4_REALITY`：`.modeling/state.json:L3035-L3052`。
- S7 后 next action 已直接转向 Q2：`.modeling/state.json:L3065-L3087`。
- `watch_roots` 只有 `data` 与 `planning`，没有 `docs`：`.modeling/state.json:L1022-L1025`。
- 状态中没有以 brief 为 subject 的 evidence、artifact、next action、transition 或完成门。

由此只能推出：A 项目真实产生了一份 Q1 队友讲解稿，但当时平台没有把它建模成 S7 晋级门或控制状态 owner。不能由文件存在反推“旧状态机已经强制每问 brief”。

## 2. 三类规则来源必须分开

### 2.1 可泛化规则

下列原则可从 A 项目抽象为跨题工作方法：

1. 队友讲解稿是面向人的技术交接物，必须让未参与细节的人理解对象、机制、证据、结论和边界；它不是论文草稿、内部验证报告或控制状态摘要。
2. 模型建立负责自含模型公式、可计算化变形和由公式推出的主求解逻辑；模型求解引用前述内容说明实际输入、初始化、参数、停止条件和结果生成；模型检验摘要对象、设置、指标、结果与结论，不另起独立数学合同。
3. 展示值可以合理舍入，但必须追溯到未舍入机器结果；舍入参数若用于复现或交付，应按舍入值重新核验。
4. 内部验证器可以提供强证据，但其长推导、反例明细、逐点残差和回归流水不自动进入讲解稿或论文。
5. 讲解稿可以复用已批准公式、结果、表格和图，但通过人工复述不等于论文内容获批，也不允许整篇自动晋升。
6. 模型、结果、术语或证据 identity 变化时，只重审真实依赖变化的讲解闭包。
7. 若持久化，讲解稿属于 `technical_documentation`；路径和载体由现有平台、真实消费者及生命周期决定，不需要新的 artifact role。

### 2.2 用户本轮新增 norm

用户本轮明确新增：**每一问必须写队友讲解稿。**

这是一项新的、有效的用户授权和项目工作规范，应与 A 项目旧状态没有门禁化的事实并存，而不能相互覆盖：

- 对当前及后续受该授权约束的项目，每个实质子问都必须有一次完整的九项讲解闭包；不再以“是否有临时交接需求”决定该问是否需要讲解。
- 最轻量触发点是：某问已经形成可解释的当前解答或需要把当前技术状态交给人时。正式完成的子问应在进入论文写作、最终交付或转入下一问的人类工作闭包前完成讲解。
- 未完成子问可以形成 provisional 讲解，但必须标明缺失结果、未通过验证和待决定项；它不能伪装成完成稿。
- “每问必写”是人类理解与交付完整性要求，不自动成为数学模型 `S6→S7` 的第五项证据，也不要求新建状态、组件、transition 或 evidence level。
- 用户已给出真实消费者和用途，因而不再属于无消费者的默认脚手架；但仍可复用现有技术文档或一份按问组织的载体，不要求固定文件名或每问新建平行控制文件。

### 2.3 A 题局部特例

以下内容不得提升为通用 V15 规则：

- FY1、M1、完整圆柱、有限视线段、烟幕半径与下沉速度等题目对象；
- `g=9.8`、`4096/8192` 角网格、`1e-3/5e-4 s` 时间网格、根容差与 Q1 数值；
- `docs/q1/solution_brief.md` 的十节论文式 Markdown、式号和表号；
- 临界角多项式实根法、高密度圆周采样等特定辅助验证器；
- A 项目依用户和指导教师确认的“外部公开数值不进入论文或队友讲解稿”绝对政策；其他项目可以在来源、用途和主张边界清楚时引用外部基准。

## 3. 九项语义覆盖与 A 题实例

九项是内容覆盖清单，不是固定标题模板。

| # | 通用语义 | A 题 Q1 的实际覆盖 | 审计结论 |
|---:|---|---|---|
| 1 | 本问要求、题意解释和边界 | 问题重述及三段计算链：`docs/q1/solution_brief.md:L3-L16`；完整圆柱与有限线段分析：`L18-L32` | 已覆盖 |
| 2 | 现实对象到变量、参数、关系、目标和约束的映射 | 符号表：`L49-L69`；轨迹、遮蔽余量和时间集合：`L71-L224` | 已覆盖，但分散在多个章节 |
| 3 | 关键假设、依据及影响 | 六项假设及不可外推边界：`L34-L47` | 已覆盖 |
| 4 | 模型建立，包括符号、公式/计算关系及作用 | 解析运动学、有限线段、完整圆柱、连续时间与可计算化：`L71-L243` | 已覆盖 |
| 5 | 模型求解，包括输入、算法、参数、停止/可行/最优性判据 | 实际执行链、网格和根求精：`L245-L284` | 已覆盖；Q1 是计算而非优化 |
| 6 | 关键结果、单位及现实含义 | 结果表和区间解释：`L286-L311`；结论：`L349-L369` | 已覆盖 |
| 7 | 独立验证、稳健性/不确定性、适用边界与禁止宣称 | 检验设置、指标与结论：`L313-L331`；优缺点及适用范围：`L333-L347` | 已覆盖为摘要，符合边界 |
| 8 | 对应代码、当前正式/工作输出、identity 状态和复现路径 | brief 中没有“代码、复现、路径、SHA、identity”内容；这些信息位于 `docs/q1_implementation_and_verification.md:L5-L17`、`docs/q1_result.json:L3-L6,L392-L400` | A brief 的明确缺口；V15 九项是有意增强 |
| 9 | 队友必须能复述的最小结论，以及仍待决定的问题 | 最小结论位于 `docs/q1/solution_brief.md:L349-L369`；没有显式“待决定/无待决定”字段 | 结论已覆盖，未决项需补“无”或实际问题 |

A 文件采用十个章节：问题重述、问题分析、模型假设、符号、模型建立、模型求解、结果、检验与敏感性、评价、结论。V15 不应把这十个标题误写成所有项目的固定格式；九项清单通过归并符号/评价并新增复现与未决项得到。

## 4. 内容载体与权威边界

| 载体 | 正确消费者与内容 | 不得承担 |
|---|---|---|
| 队友讲解稿 | 队友、答辩者、接手者、论文作者；主问题、必要公式、主求解链、结果、验证摘要、边界、复现导航和未决项 | 论文定稿身份、内部 verifier 的完整数学合同、状态权威 |
| 论文 | 面向评审的自含论证、经批准的表图与主张；模型建立—求解—检验按章节职责组织 | 调试日志、逐点残差、未经批准的整篇 brief、状态副本 |
| 内部验证 | 独立实现、反例、完整表面复核、残差、收敛序列、外部回归告警和失败路径 | 面向评审/队友的主体叙事 |
| 机器结果 | 未舍入参数、指标、单位、schema、run/spec/input identity | 通过人工改写成为题意或状态 owner |
| 状态 | 当前阶段、正式 identity、已决/未决事项、next legal action 和 blocker | 模型公式、讲解正文、验证报告或论文正文 |

A 项目已明确机器结果、队友讲解稿和论文是不同角色，不能互相冒充权威来源：`planning/07_q2_scope.md:L73-L74`。

V15 的既有 artifact owner 已足够：

- `references/project-platform-contract.json:L46-L50` 将 `docs/` 定义为 `technical_documentation`，职责已含 teammate-facing technical explanation；
- `references/capability-packets/project/platform-and-artifacts.md:L31-L43` 要求先确认真实消费者，禁止无需求默认生成逐题 brief；用户本轮的新授权提供了消费者，但不取消路径准入和复用检查；
- `references/artifact-contract.json:L34-L49` 继续负责生命周期、重复、临时和传播规则；不需要新 `solution_brief` artifact type。

人工编写的持久讲解通常可使用：

```text
platform_role = technical_documentation
class         = source
lifecycle     = working
identity_class= working
```

只有它被真实下游作为稳定输入消费时才提升；普通保存不登记新的正式 identity。若已有同用途载体，优先更新既有载体。

## 5. 模型建立、求解、检验的职责

A 项目已解决决定 `OD-WRITING-MATH-CONTRACT-BOUNDARY`：

- 决定主题、两个选项和最终选择：`.modeling/state.json:L942-L958`；
- 该决定作用于 Q1–Q5，而不是只作用于 Q1；
- 同一边界在 `planning/01_evidence_baseline.md:L49-L66` 和 `planning/02_workplan.md:L99-L107` 展开。

抽象后的职责为：

### 5.1 模型建立

- 自含对象、变量、参数、目标、约束、假设和公式；
- 立即给出必要的可计算化变形；
- 说明主算法为什么由这些公式合法推出；
- 决定模型身份和主算法合法性的数学内容不得推迟。

### 5.2 模型求解

- 引用模型建立中的公式和步骤，不重建第二套数学合同；
- 报告实际输入、初始化、算法参数、停止条件、失败/不可行处置和结果生成；
- 如涉及优化，准确说明得到的是可行、局部、近优、有界保证还是全局最优。

### 5.3 模型检验

- 对人类材料报告“检验对象—设置—指标—观测结果—结论边界”；
- 独立 verifier 的长推导、反例构造和逐点明细留在内部证据；
- 摘要必须足以支持结论，但不能用“多个算法得到同一数字”替代结构、约束、假设与稳健性证据。

Q1 brief 的实际分工可见：

- 模型建立内完成两层搜索与两次求精：`docs/q1/solution_brief.md:L226-L243`；
- 模型求解只承接第 5 节并给实际步骤与参数：`L261-L272`；
- 模型检验明确“只列设置、指标与结论”：`L313-L326`。

## 6. 外部数值与辅助验证器消费者政策

### 6.1 A 项目的已决政策

- 外部公开论文、官方讲评或复现数值只用于内部回归告警，不进入论文正文、摘要、表图、附录或队友讲解稿：`planning/02_workplan.md:L104-L107`。
- 官方临界角多项式实根法和高密度圆周采样作为独立交叉路径保留在内部技术验证，不替代正式主求值器：`planning/01_evidence_baseline.md:L53-L66`。
- 内部 E3/E4 报告直接声明“不是论文或队友讲解稿”，并规定只允许摘要检验对象、设置、指标与结论：`docs/q1_model_validation_report.md:L1-L3,L21-L23`。
- 生成该报告的代码把 writing boundary 写入结构化结果：`src/q1/validate_model.py:L459-L486,L498-L504`。

### 6.2 可泛化的消费者规则

- 主模型、正式结果和用户可见结论必须由当前冻结规格与正式输出支撑；
- 辅助验证器是 verification consumer/producer，不因精度更高自动变成主模型或论文算法；
- 外部数值按 `external_evidence` 或内部 comparison 使用，不能冒充题面、正式输入或唯一真值；
- 是否在论文/讲解稿显示外部基准由用户、竞赛规则、引用许可和叙事目的决定。A 项目的绝对排除不得无条件推广；
- 即使不展示内部验证器数学细节，也必须在人类材料中如实摘要验证对象、设置、指标、结果与局限。

## 7. V15 最轻量但可靠的归属

### 7.1 Packet

唯一主要 owner 继续使用：

- `PKT.MODEL.IMPLEMENT_RESULTS`：`references/capability-packet-registry.json:L75-L79`；
- 逐问讲解程序位于 `references/capability-packets/modeling/implementation-solving-and-results.md:L65-L79`。

九项属于现有规格、实现、结果、验证与交接能力的组合程序，不需要独立 packet。

### 7.2 Atoms

复用现有 atoms，不新增控制实体：

- 主锚点 `MOD.RESULTS.TRACE`：`rules/modeling.json:L2120-L2193`；
- 结果身份 `MOD.RESULTS.IDENTITY`：`rules/modeling.json:L1883-L1945`；
- 运行复现 `MOD.IMPLEMENT.REPRODUCE`：`rules/modeling.json:L1636-L1684`；
- 对应规格与验证 atoms 继续拥有变量/公式/假设和 E1–E4 证据。

不要让 `DEL.HANDOFF.STATE` 拥有技术讲解正文；它的 effect 只负责 `state_next_actions_open_decisions`：`rules/evidence_delivery.json:L1106-L1157`。

### 7.3 Routes

- 写作或更新逐问讲解的主 route 使用 `RT.MODEL.RESULTS`：`references/route-contract.json:L491-L496`；
- 若同一请求还包含真正的跨窗口项目交接，再增加 `RT.PROJECT.RESUME`，但它只负责恢复/状态：`references/route-contract.json:L400-L405`；
- `references/project-method-notes.md:L13-L17` 已明确技术方案交接要同时读取 model results packet，不能用 handoff 摘要替代。

不需要新增 `RT.SOLUTION.BRIEF`。

### 7.4 最小可靠落实方式

在不加重控制面的前提下，建议未来变更只做以下范围：

1. 在现有 model results packet 中把用户本轮 norm 明确为“每个实质子问均需完成九项讲解闭包”；
2. 保留载体可复用、路径不固定、持久化时走 `technical_documentation` 准入；
3. 把完成检查放在既有结果解释/人工复审清单，而不是增加 S-state、evidence level、artifact role 或 release gate；
4. 增加一个行为验收场景：多问任务中不得只写最后一问，九项至少逐问可定位；代码/输出身份和未决项缺失时失败；
5. 用户没有要求独立文件时，可以在同一技术文档中按问分节，但每问必须可独立定位和复述；用户要求独立稿时再按真实 ChangeSet 新建文件。

## 8. 本轮发现的控制问题；均未在本审计中修复

1. A 项目状态没有 brief evidence、artifact、next action 或 gate；这与用户本轮新增 norm 不冲突，但说明不能把旧 state 当作已落实证明。
2. 当前 V15 packet 的触发措辞是“当某一问需要交给队友理解、答辩、接手，或……技术核对时”，尚未显式写成用户新增的“每问必须”；本审计没有修改该段。
3. 当前 `MOD.RESULTS.TRACE` 只强制 question/baseline/limitations trace，没有单独枚举九项或人工复述；本审计没有修改 atom。
4. `RT.MODEL.RESULTS` 的 route patterns 没有显式列出“队友讲解稿/答辩讲解”，虽然 agent-authored semantic plan 可选择该 route；本审计没有修改 route。
5. A 题 Q1 brief 缺代码/输出/reproduction identity，且未显式写“待决定问题：无”；本审计没有修改真实项目。
6. 项目代码没有 solution brief generator 或 validator；这不要求新增生成器，但意味着不能用程序退出码宣称 brief 完成。
7. `references/artifact-contract.json:L38-L41` 仍拦截旧式 `question_[0-9]+/solution_brief.md` 路径。该规则可继续防止默认脚手架；真实持久稿应走 canonical `docs/` 或复用现有载体。本审计没有修改合同。
8. 当前没有行为验收证明“多问任务逐问覆盖且九项完整”；本审计只记录建议，没有新增或运行 eval。

## 9. 精确源索引

### 9.1 真实 A 项目

- `docs/q1/solution_brief.md:L3-L369`：Q1 完整讲解正文；关键区段见第 3 节表。
- `planning/01_evidence_baseline.md:L49-L66`：官方方法与当前规格对照、内部验证器和写作边界。
- `planning/02_workplan.md:L87-L107`：论文主线及模型建立—求解—检验边界。
- `planning/07_q2_scope.md:L58-L87`：机器结果、讲解稿、论文角色分离及 Q2 成功标准。
- `planning/08_q2_problem_definition.md:L120-L176`：结果格式、展示舍入、证据计划与讲解稿验证摘要边界。
- `.modeling/state.json:L172-L179`：Q1 `S7/closed`。
- `.modeling/state.json:L942-L958`：`OD-WRITING-MATH-CONTRACT-BOUNDARY`。
- `.modeling/state.json:L3035-L3087`：Q1 S7 门与转入 Q2 的历史。
- `docs/q1_implementation_and_verification.md:L3-L17,L29-L43`：内部技术证据身份、正式结果与收敛边界。
- `docs/q1_validation_report.md:L1-L28`：E1/E2 内部报告及门禁范围。
- `docs/q1_model_validation_report.md:L1-L23`：E3/E4 内部报告与讲解/论文消费者边界。
- `docs/q1_result.json:L3-L6,L29,L388-L400`：正式结果、warning 和 run identity。
- `src/q1/solve.py:L60-L109,L113-L227,L231-L248`：内部报告与机器结果生成入口；不生成 brief。
- `src/q1/verify.py:L490-L534`：验证身份与输出入口。
- `src/q1/validate_model.py:L459-L524,L528-L557`：E3/E4 内部报告、writing boundary 和 CLI。

### 9.2 V15 当前 owner

- `references/capability-packets/modeling/implementation-solving-and-results.md:L65-L79`：当前九项讲解与人工复述程序。
- `references/capability-packet-registry.json:L75-L79`：`PKT.MODEL.IMPLEMENT_RESULTS` 登记。
- `references/modeling-method-notes.md:L19-L25`：implementation/results 路由到该 packet。
- `references/project-method-notes.md:L13-L17`：状态交接与技术方案交接分流。
- `references/project-platform-contract.json:L46-L50,L81-L88`：technical documentation role 和跨角色边界。
- `references/capability-packets/project/platform-and-artifacts.md:L31-L43,L75-L86`：真实消费者、反默认工件和路径职责。
- `references/artifact-contract.json:L34-L49`：工件准入、重复、传播与旧式 brief 路径拦截。
- `references/route-contract.json:L400-L405,L491-L496`：PROJECT.RESUME 与 MODEL.RESULTS。
- `rules/modeling.json:L1636-L1684,L1883-L1945,L2120-L2193`：复现、结果身份与结果 trace atoms。
- `rules/evidence_delivery.json:L1106-L1157`：状态 handoff atom 的严格边界。

## 10. 审计结论

A 题真实实践支持一套清晰的“模型—求解—结果—验证摘要—边界”人类讲解语义，但不支持声称旧平台已经将逐问 brief 设为默认工件或状态门。用户本轮新增的“每问必须写讲解稿”现在提供了新的强制授权；其最轻量、可靠的落实方式是复用现有 `PKT.MODEL.IMPLEMENT_RESULTS`、`MOD.RESULTS.TRACE` 组合、`RT.MODEL.RESULTS` 和 `technical_documentation`，以逐问九项覆盖和人工复述作为完成条件，同时不新增状态机节点、artifact role、route 或独立控制文件。

本文件仅保存规则提取、证据边界和未修复控制问题，不构成上述 V15 变更已经实现、验证或发布的声明。

## 11. 后续实现状态（2026-08-27）

本节是原始只读提取之后的实现回填；保留第 8 节原文作为当时审计快照，不追写历史判断。

- 第 8.2 项已在 V15 candidate 修复：model results packet 明确每个实质子问 MUST 有讲解稿。
- 第 8.3 项已由新 atom `MOD.RESULTS.TEAMMATE_BRIEF` 修复：九项语义、当前 identity 和人工复述均有明确字段；没有把它并入 `MOD.RESULTS.TRACE` 或 S7 gate。
- 第 8.4 项已修复：`RT.MODEL.RESULTS` 加入 `prepare_teammate_brief` intent、讲解稿 patterns、`teammate_solution_brief` 输出和专用事件；动作必须绑定精确 question component。
- 第 8.8 项由 V15 正式 scenarios 的建模—交接正反例覆盖：正例要求讲解 atom，空 question identity 的近负例必须 block；规则存在性、route 可达性、能力包映射与历史能力处置分别由 V15 contracts 和 migration 检查直接证明，不再使用同源 atomic mutation 自证。
- 第 8.1、8.5、8.6、8.7 项仍保持原边界：真实 A 项目没有被回写，Q1 brief 的内容缺口没有补写，也没有新增 generator、validator 或 artifact role。
- 模型建立—求解—检验的新增规则采用专项覆盖：通用 `MAN.STRUCTURE.DEPENDENCY` 保留 V14 语义，`MAN.CONTENT.METHOD` 在方法内容重合处以更具体职责 `refines` 它，不机械叠加两套顺序。

完整实现与验证记录见 `references/preservation/v15-real-project-backfill-and-state-repair.md`。这仍是候选实现，不是正式发布声明。
