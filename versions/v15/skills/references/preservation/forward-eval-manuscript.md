# V15 Candidate：稿件局部润色与 Q2 技术讲解前向评估

## 结论

**总体：FAIL（核心行为可达，但存在一个可复现的控制契约旁路）。**

- **PASS**：A 可被最小地识别为 G1 局部段落润色；阅读闭包、最早错误层、论证强度保持和 LaTeX 局部页验收均有完整程序，不要求全文重写或全文审计。
- **PASS**：B 可经模型结果解释能力到达完整的九项 Q2 技术讲解；其非论文身份、人工复述门和精确变更传播均明确可达。
- **PASS**：四个近反例均被当前活跃文本明确拒绝。
- **FAIL**：`manuscript-change-closure.json` 声明稿件步骤缺少五个 closure facts 必须阻断，但当前解析器只在 `facts` 已含 `change_class` 时才调用该检查；完全省略这些 facts 的稿件写步骤会被解析为 `resolved`。
- **UNVERIFIED**：九项顺序等讲解程序位于非规范 capability packet，当前没有专门 atom 对其逐项机器验收；这不妨碍 fresh Agent 按程序实施，但不能把解析器通过声称为九项内容已经通过。

本次仅依据候选包当前活跃入口、契约、router、命中 packets、命中 atoms 和解析器前向结果判断；未使用迁移/保存历史作为运行时依据，也未读取 `/tmp/skill_v15_audit`。

## 1. 两步路由与最小披露

### A. 结果段局部润色

**PASS。** 推荐内部语义步骤为：

- tier/mode：`G1_WORKING / mutate`
- route：`RT.MANUSCRIPT.LOCAL`
- action/event：`polish_paragraph / local_manuscript_edit`
- closure：`paragraph_polish`
- completion scope：`changed_paragraph_wording_only`
- facets：`wording`

解析器用完整 closure facts 实测可解析为 `RT.MANUSCRIPT.LOCAL`，检查面为 `changed_paragraph`、`adjacent_sentences`、`semantic_invariance`、`direct_reference_points`。证据：

- `references/route-contract.json`：route `RT.MANUSCRIPT.LOCAL`
- `references/manuscript-change-closure.json`：`closures.paragraph_polish`
- `SKILL.md`：**四级运行强度**、**G0/G1 日常工作**、**最小一致性闭包**

完整读取顺序应为：

1. `references/manuscript-method-notes.md`：**local-edit**；
2. `references/capability-packets/manuscript/reader-audit-and-local-edit.md`：**局部修改的完整程序**；
3. `references/capability-packets/manuscript/expression-and-argument.md`：**局部改写程序**。结果段含数字、模型含义和证明强度，属于需要实质表达判断的润色，不能只靠错字程序；
4. 因项目使用 LaTeX 且预计改变实际页面，内容闭合后完整读取 `references/capability-packets/manuscript/latex-and-finalization.md`，实际只执行其局部构建、日志和受影响页面范围。

这是每个真实阶段至多三个 packet：内容阶段读 reader/local + expression；页面验收阶段读 finalization。无需加载稿件结构包、全文 reader audit、最终交付包、恢复包或全部视觉创建包。若段落没有图表变化，也不应预载图表设计/生成 packets。

本 closure 直接命中的稿件 atoms 为：

- `rules/manuscript.json#MAN.LOCAL.SCOPE`
- `rules/manuscript.json#MAN.LOCAL.DEPENDENCIES`
- `rules/manuscript.json#MAN.LOCAL.NO_FULL_AUDIT`

它们分别限制修改面、核对直接依赖、禁止无依据全文审计。若实际改动了 claim、结果 identity、限制、符号或交叉引用，则已越过 `paragraph_polish` 的 semantic boundary，应改为 `local_substantive`，真实声明 `manuscript_write`，并增加 `MAN.CONTENT.CLAIM_EVIDENCE`、`MAN.CONTENT.NOTATION`、`MAN.CONTENT.EXPLANATION_TRACE`、`MAN.CONTENT.NO_DUMP`；本请求明确要求这些语义不变，所以不能预先把它升级为实质改写。

### B. 给新队友的 Q2 技术讲解

**PASS。** 最小 route 不是论文 route，也不是项目恢复 route，而是：

- route：`RT.MODEL.RESULTS`
- action/event：`interpret / result_interpretation`
- component：Q2，类型 `question`
- router：`references/modeling-method-notes.md`：**results**
- 完整 packet：`references/capability-packets/modeling/implementation-solving-and-results.md`

解析器前向实测可解析为 `RT.MODEL.RESULTS`，命中核心 atoms：

- `rules/modeling.json#MOD.RESULTS.INTERPRET`
- `rules/modeling.json#MOD.RESULTS.TRACE`

若讲解实际陈述模型用途、现实外推或受不确定性影响的新主张，还应真实声明 `before_claim`，从而命中 `rules/verification.json#VER.E4.USE_CLAIM_GATE`、`#VER.UNCERTAINTY.CLAIM_GATE`；若实际使用数据，`rules/data.json#DATA.IDENTITY.BEFORE_USE` 也适用。不能用编译、代码退出码或数值复算替代这些内容证据。

“给新接手的队友”在这里描述受众，不等同于 Agent 正在恢复项目控制状态。因此默认不加载 `RT.PROJECT.RESUME`、R1/R2 或 `project/recovery-and-handoff.md`。证据：`references/project-method-notes.md` 的 **recovery** 明确区分控制状态交接与某一问技术方案，并把后者指向 modeling implementation/results packet。

载体可为当轮说明或已有文档；packet 明确不强制创建固定 `solution_brief.md`。若用户/项目确实要求新文件，才按 `SKILL.md` 的新路径平台准入检查选择合法角色和路径，不能自行发明默认目录。这样既完整，也避免不必要的平台控制面。

## 2. A 的阅读闭包、最早错误层与验收

### 局部阅读闭包

**PASS。** 应读取并核对：

- 目标句所在完整结果段；
- 涉及承接、定义、因果或结论时的必要相邻段；
- 直接引用该句/claim 的位置；
- 改写前后的语义不变量：每个数字、单位、舍入口径、结果 identity、模型对象与机制、假设/条件、比较基准、验证类型、证明与外推强度；
- 只有真实 identity/claim 改变时才扩展到其直接消费者。

若上述语义均不变，闭包止于目标段、必要邻接和直接引用点；不进入无关章节、上游代码、全项目恢复或全文审计。证据：

- `SKILL.md`：**最小一致性闭包**
- `references/manuscript-change-closure.json`：`closures.paragraph_polish`
- `reader-audit-and-local-edit.md`：**先选正确审计范围**、**画出最小依赖面**

### 最早错误层

**PASS。** `reader-audit-and-local-edit.md` 的 **判定缺陷属于哪一层** 给出可执行分流：

1. 模型和证据正确、只是对象/理由/边界/落点表达不清：在稿件层作最小修复；
2. 正文与公式、代码、数据口径、冻结结果或图表 identity 冲突：先定位实现/规格/identity 的最早错误层，不能靠润色掩盖；
3. 模型或证据本身缺变量、机制、验证或支持能力：只报告缺口或收窄主张，不凭文字补造能力；
4. 本次没有修改上游的授权时，只做诊断或候选措辞，不静默改规格、代码、正式结果，也不反向使未变化的上游证据失效。

### 论证验收

**PASS。** 改写前后逐项比较：对象、条件、数字、基准、方向、精度、原因、验证动作、可证明范围和禁止外推。结果段仍应按“对象/条件—基准/指标—方向/量级—形成机制—代价/例外—题目含义”闭合。只有功能顺序整体错误才可整段结构性重写；本请求不授权这种扩大。

证据：`expression-and-argument.md` 的 **判断—理由—证据—边界**、**结果、比较与证明强度**、**局部改写程序**。

### LaTeX 一页验收

**PASS。** 顺序必须是：

1. 用项目真实唯一入口和构建方式编译；
2. 检查退出状态、当前入口、日志中的致命错误/缺字/未定义引用/越界盒，以及 PDF 是否来自当前源；
3. 独立完成上述内容与证明强度核对，编译成功不替代内容通过；
4. 打开实际 PDF 的受影响页，检查改动出现、无乱码/裁切/丢字、局部字号/缩进/编号/对齐正常、无孤题/异常空白/越界；
5. 只有分页、浮动、标题、脚注或跨页内容有传播迹象时才查看必要相邻页；无传播则停止，不逐页审计全文；
6. 结论只写“该段内容闭合且受影响页渲染通过”，不能升级为章节/全文/正式就绪。

证据：`reader-audit-and-local-edit.md` 的 **按依赖验收**；`latex-and-finalization.md` 的 **构建与日志检查**、**最终页面怎样检查/局部修改**、**分层完成标准**。

## 3. Q2 技术讲解可达性

**PASS（人工行为可达）；UNVERIFIED（无专门机器逐项证明）。**

`implementation-solving-and-results.md` 的 **逐问技术讲解与人工复述** 明确要求按以下顺序完整说明：

1. 本问要求、题意解释和边界；
2. 现实对象到变量、参数、关系、目标、约束的映射；
3. 关键假设、依据和影响；
4. 模型建立：符号、公式/计算关系及作用；
5. 模型求解：输入、算法、参数、停止/可行性/最优性判据；
6. 关键结果、单位和现实含义；
7. 独立验证、不确定性/稳健性、适用边界和禁止宣称；
8. 代码、冻结输出和复现路径；
9. 队友必须能复述的最小结论及仍待决定事项。

同一标题还明确规定：它是技术交接物而非论文草稿；不得使用摘要、论文节号、评阅者话术或正式结论语气伪装成正文；讲解通过不等于论文获批，不得整篇自动晋升。未参与细节的人应能复述对象、机制、证据、结论和边界；若只能重复模型名或指标，回到最早缺失层。模型、结果、术语或证据 identity 变化时，只重审受影响讲解闭包。

因此九项顺序、非论文身份、人工复述和精确变更传播都可由 fresh Agent 直接执行。但 `references/capability-packet-registry.json` 的 **normative_boundary** 明确 packets 为非规范实施知识；当前 `MOD.RESULTS.INTERPRET/TRACE` 只规范陈述层级及结果—问题—基线—限制 trace，不能由解析器输出证明九项全部存在、顺序正确或真人已经理解。最终只能报告实际人工复述结果，不能从 route/脚本通过推导。

## 4. 近反例

| 近反例 | 判定 | 当前拦截证据 |
|---|---|---|
| 修一个词却触发全文审计 | **PASS：拒绝** | `MAN.LOCAL.NO_FULL_AUDIT`；`reader-audit-and-local-edit.md` 的局部范围表和常见失败“修一个错字却启动全文审计” |
| 为“优秀语气”整段重写 | **PASS：拒绝** | `MAN.LOCAL.SCOPE`；`expression-and-argument.md` 的 **局部改写程序** 明文禁止为了模仿优秀语气全段重写 |
| 编译成功即内容通过 | **PASS：拒绝** | `latex-and-finalization.md` 区分源完整、构建成功、渲染通过、正式就绪；`reader-audit-and-local-edit.md` 明确任何层级均不以编译通过为充分条件 |
| Q2 讲解稿自动晋升论文 | **PASS：拒绝** | `implementation-solving-and-results.md` 的 **逐问技术讲解与人工复述** 明文规定非论文、讲解通过不等于论文批准且不得整篇自动晋升；route 保持 `RT.MODEL.RESULTS`，未产生 `manuscript_promotion` |

## 5. 缺失、冲突与控制面负担

### F1 — 缺失 closure facts 可旁路强制检查

**FAIL。** `references/manuscript-change-closure.json` 的 `plan_contract` 要求每个稿件步骤提供：

`change_class`、`completion_scope`、`profile_selected`、`published_revision`、`existing_paths_only`，并声明 missing contract 应 `block_step`。

但 `scripts/lib_v11.py` 仅在：

`step["object"] == "manuscript" and "change_class" in step.get("facts", {})`

时调用 `manuscript_activation(...)`。前向复现中，一个 `facts: {}` 的 G1 `polish_paragraph` 步骤被解析为 `resolved`，且没有 `manuscript_closure`、missing-facts error 或 warning；同一计划中的 render 步骤也被放行。这与契约直接冲突，使 closure 的事件白名单、semantic boundary、scope 和 completion claim 可以被意外跳过。

**最小修正：** 对所有 `object == manuscript` 的步骤无条件调用 `manuscript_activation`；让该函数现有的 `manuscript_required_facts_missing:*` 与 `unknown_manuscript_change_class:*` 逻辑负责阻断。无需新增 atom、route 或状态门。

### F2 — local-edit 对 LaTeX finalization 的路由提示位置含糊

**UNVERIFIED。** `manuscript-method-notes.md` 的 LaTeX 页面变化触发 finalization 的明文位于 **draft** 小节，而 **local-edit** 小节没有重复这一条件；reader/local packet 只用一句话要求“涉及 LaTeX 时编译并查看受影响页”。本次按“完整读取 router”能够正确找到 finalization，但只按 context ref 锚点读取 `#local-edit` 的 Agent 可能漏掉更完整的构建/日志/页面程序。

**最小修正：** 在 **local-edit** 下增加一条交叉引用：当局部改动改变实际页面时，内容闭合后完整读取 `latex-and-finalization.md` 的局部范围。不要新增 route、atom 或全文渲染门。

### F3 — 单独建 render/layout route 会产生可避免的控制面

**PASS（可避免），但需保持实现克制。** 若把局部段落的普通编译与页面查看拆成独立 `RT.MANUSCRIPT.RENDER` 的 `render_output + layout_check` 步骤，解析器会再选择一组图件 labels/color/caption/placement atoms，其中多项对纯文字页只能判不适用，并要求额外 closure facts/facets。`SKILL.md` 已明确普通编译、排版渲染和局部非执行检查不走危险命令门；本请求可在局部 ChangeSet 的验收阶段完成编译和一页查看，不必制造图件审计或全文 route。只有用户真正要求独立版面审计、图表嵌入或 PDF 产物步骤时才拆 route。

### F4 — Q2 九项没有专门 atom

**UNVERIFIED，不判为不可达。** route → router →完整 modeling packet 链已闭合，程序可执行；但机器选择结果不会逐项证明九项、非论文身份或真人复述。若发布方希望声称“该能力已被前向验证”，最小增强应是增加一个外部可观察的行为用例：输入技术交接请求，检查九项顺序、非论文标记、人工复述请求、禁止自动晋升和 identity 局部失效；不宜为此增加日常 route、状态或逐项回执。

## 最终判定矩阵

| 评估项 | 状态 |
|---|---|
| A/B 语义拆分与 route 最小性 | PASS |
| 局部阅读闭包与禁止全文扩张 | PASS |
| 最早错误层与上游权限边界 | PASS |
| 数字/模型含义/证明强度不变 | PASS（由用户不变量 + closure/packets 联合执行） |
| LaTeX 受影响页验收 | PASS |
| Q2 九项、非论文、人工复述、变更传播可达 | PASS |
| 九项内容的机器级验收证明 | UNVERIFIED |
| 四个近反例 | PASS |
| closure facts 强制执行与契约一致性 | FAIL |
| 日常控制面比例性 | PASS，带 F2/F3 注意项 |

在修复 F1 前，不建议把 candidate 评价为完全通过；F1 是最小且确定的解析器修正，不需要改变本次已经良好的领域程序。
