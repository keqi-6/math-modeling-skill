# V15 候选：真实项目规范回填与状态机最小修复

> 记录类型：V15 候选实现与验证报告。  
> 记录时间：2026-08-27T12:59:33+08:00。  
> 候选目录：`/mnt/c/Users/35190/skills_v15_candidate`。  
> 真实项目：`/mnt/d/AI/AI_program/2025（第八题）/A题`，全程只读。  
> 生产 Skill：真实项目内的 `skills/`，本轮未修改。  
> 设计边界：修复已复现的选择、闭合与表达缺口；不增加状态节点、证据等级、发布门或自动化流水线。

## 1. 结论

本轮在独立 V15 候选中完成了以下闭环：

1. S6 能接受结构完整、身份当前、决定已解决的诚实 `not_applicable`，同时拒绝裸 N/A、E3 整轴 N/A、陈旧身份和未解决决定。
2. A0 视觉创建补回设计、来源忠实、渲染身份、同步、标签、字体、色彩与可读性等验收 atom；数据图再加载数据身份与禁止手填数值，概念示意图不会误背数据图规则。
3. 所有 manuscript step 都必须先闭合 change class、completion scope、profile、published revision 与 existing paths 五项事实，不能通过省略 `change_class` 绕开 closure contract。
4. 修复只读数据处理建议、compare-only 缺 baseline、E3 五项机械全选、E4-only 无法诚实路由、队友讲解稿身份缺失以及若干 route/atom 误选或漏选。
5. 把 A 题形成的逐问讲解稿、模型建立/求解/检验职责、辅助验证器消费者边界回填到能力包和 atom；不把它们变成新的状态机或发布流水线。
6. 重新封存 V1–V14 规则文本迁移：302 条历史子句覆盖 212 个现行 atom，0 个未豁免强度退化。

## 2. 控制面保持轻量

本轮没有新增状态、transition、evidence level、artifact role 或 release gate。机器控制只处理可稳定判断的结构事实：

- schema 形状、布尔分类和必填字段；
- 当前 artifact/run/spec identity；
- 已登记且已解决的 decision；
- route/action/event 的闭集与组件绑定；
- manuscript closure 事实是否齐全且相互一致。

下列判断仍由 agent 与人工复审承担：

- N/A 理由是否真实、边界是否足够；
- E3 风险是否抓住当前模型的实质失败方式；
- 图是否忠实表达源结构、方向和几何；
- 队友能否复述模型、证据、结论和限制；
- 稿件中的职责划分是否在语义上成立。

因此本轮是“少量 fail-closed 结构检查 + 完整能力文本 + 人工确认”，不是把每项规范编成昂贵的自动门禁。

明确未进入本轮的对象：CAS/锁与并发语义、原始请求持久化与隐私、对冻结规则包新增发布保护、全面自动化 release pipeline。

## 3. 状态机与路由修复

### 3.1 S6 的诚实 N/A

`scripts/state_v11.py` 现在拥有统一的 current-evidence 判定，`scripts/state_manager.py` 与 resolver 共用该语义，且同一 evidence level 以最新记录为准。

N/A 只有在以下条件同时成立时才可满足 E2 或 E4：

- 顶层 `status = not_applicable`；
- `applicability` 含 disposition、rationale、basis 与 boundaries；
- evidence kind 为 `decision`；
- decision 在当前 state 中存在且 resolved；
- 至少有一个当前 spec artifact 引用；
- 该引用未因 spec identity 变化而失效。

E1 与 E3 仍不能以整轴 N/A 关闭。机器只核对形状、身份和决定状态；“为何确实不适用”的真值由人工负责。

### 3.2 E3/E4 的真实边界

- `validate_structure` 只执行 E3，`assess_reality` 只执行 E4；兼容动作 `validate_model` 仍可同时执行两轴。
- E3 先声明粗粒度 structural verification，再按当前风险选择 constraint、invariant、limit、counterexample 或 sensitivity 专项事件。
- `VER.E3.RISK_MATCH` 要求记录主张、失败风险、选中检验、未选理由与结论影响，避免用机械五项全跑冒充风险覆盖。
- 旧 V9/V10 的五项菜单子句标为 `corrected_overconstraint`；“模型结果触发 E3”本身仍保持 MUST，仅把旧 trigger→CONSTRAINT/menu 绑定标为 `corrected_binding_overconstraint`。因此纠正的是机械绑定，不是删除 E3 触发义务。

### 3.3 其他 route/atom 缺口

- 新增 `RT.DATA.TREAT.PROPOSE` 与 `DATA.TREAT.OPTIONS`：只给可选处理方案、影响、风险和采用条件，不形成 treatment decision、processed identity 或 mutation。
- compare-only 现在选择 `MOD.COMPARE.BASELINE`、`MOD.COMPARE.SAME_EVIDENCE` 与 `MOD.COMPARE.ASSUMPTIONS`，但不选择只有真正 selection 才需要的 rationale。
- `prepare_teammate_brief` 必须绑定一个精确 question component；空 component 不再生成游离讲解稿。
- `MOD.RESULTS.AUXILIARY_METHOD_VISIBILITY` 只在结果解释或讲解稿事件下加载，普通 manuscript audit 不再误带模型结果规则。

## 4. 视觉模块修复

### 4.1 A0 创建时的验收闭包

视觉创建不再只有“生成一张图”的粗规则。A0 创建会选择：

- 读者问题与图型选择；
- 源拓扑、方向和几何忠实；
- render identity 与 source/render 同步；
- 标签、字体、色彩和缩放后可读性。

若 `data_driven_visual = true`，再选择数据身份和禁止手工重写数值；若为 `false`，工程示意图不会误加载这两项。`visual_generate` 与 standalone `visual_audit` 对 visual object 都要求显式布尔分类，缺失即在 route prerequisite 处阻断；manuscript 内嵌图审计不受该对象级前置条件误伤。

### 4.2 代码绘图能力的保留方式

详细的图形构思、来源忠实、工程示意图拓扑、数据图身份、字体/标签/色彩、缩放和稿件嵌入程序保留在 visual capability packets；atom 只负责选择正确的小闭包。这样避免把完整绘图能力压成几个短 effect，也避免每次绘图读取整个历史总规则。

`VIS.DESIGN.SOURCE_FIDELITY` 的证据字段要求数据驱动分类、源实体/关系、方向、拓扑与几何映射，防止“代码能渲染”被误当成“示意图正确”。这仍是人工视觉审计，不是像素级自动评分器。

## 5. 真实项目规范回填

### 5.1 每问队友讲解稿

`MOD.RESULTS.TEAMMATE_BRIEF` 要求每个实质子问形成可独立定位的讲解闭包，覆盖：

1. 题意、要求和边界；
2. 现实对象到变量、关系、目标和约束的映射；
3. 假设、依据和影响；
4. 模型建立及公式作用；
5. 求解输入、算法、参数与停止/可行/最优性判据；
6. 关键结果、单位和意义；
7. 验证、稳健性/不确定性与禁止宣称；
8. 代码、输出 identity 和复现路径；
9. 队友必须能复述的最小结论与未决项。

还必须有人类复述检查。九项是语义清单，不是固定标题；可以一份文档按问分节，也可复用现有 technical documentation。该规范不成为 S6→S7 的第五个验证轴，也不强制新文件名或独立 artifact component。

### 5.2 模型建立、求解、检验

这里采用“通用基线 + 专项覆盖”，不是双重叠加：

- `MAN.STRUCTURE.DEPENDENCY` 恢复 V14 revision 1 的通用语义，只负责“定义—证据—推导—结论”的全稿依赖。
- `MAN.CONTENT.METHOD` revision 2 以 `refines: [MAN.STRUCTURE.DEPENDENCY]` 明确成为方法内容的专项规则。
- 在方法内容的重合范围，以“数学合同与可计算化 → 本次执行 → 检验证据”这一更具体职责链为准；不要求同时满足两套平行章节措辞。
- 方法节单独改写只选择专项 atom；全稿审计可同时看到两者，但分别审查全稿依赖和方法内部职责。

模型建立首次闭合对象、变量、假设、关系、目标、约束、可计算化及主求解逻辑；模型求解只实例化当前输入、参数、步骤、停止和失败处置；模型检验报告对象、设置、判据、结果、结论强度和边界，不用第二套长数学合同取代证据摘要。

### 5.3 辅助方法与消费者边界

新增的 visibility/provenance 规则区分 `primary_model`、`primary_solver` 与 `auxiliary_validator`。辅助方法的完整强合同留在内部技术证据；论文和讲解稿读取检验对象、设置、指标、结果和边界。若辅助方法实际承担正式答案、共同求解或核心证明，就必须提升其方法角色，不能一面依赖、一面隐藏。

## 6. Manuscript closure 防旁路

所有 manuscript step 都会调用 closure activation，不再以“facts 里恰好出现 change_class”作为入口。schema 与 runtime 双重要求：

- `change_class`：字符串；
- `completion_scope`：字符串；
- `profile_selected`：布尔；
- `published_revision`：布尔；
- `existing_paths_only`：布尔。

同时核对 action、tier、events、facets、paths 与声明 scope；published revision 的布尔值必须与 change class 一致，existing paths 也在运行时检查。缺失或类型错误直接 block，不向最宽 closure 猜测。

rule-count budget 继续只是回归遥测，不是运行时 gate；本轮没有把稿件工作变成全自动流水线。

## 7. 能力原子化与完整保留

V15 采用三层分工：

1. atom 保存最小、可独立选择的 MUST/SHOULD 义务和证据字段；
2. capability packet 保存完整程序、判断方法、反例、边界和人机分工；
3. route 只加载当前步骤相关 atom 与 packet，不广播全部历史规则。

为防止再次发生“原子化后只剩短标签”，V15 定向驱动还检查五类关键 atom 的详细 evidence field 合同：data treatment options、method writing、teammate brief、E3 risk match、visual source fidelity。原子删除 mutation 对 212/212 个 atom 全部能被测试发现。

迁移账本的最终封存为：

- review：`V15-CLAUSE-REVIEW-001`；
- projection SHA-256：`9caef60bf3e3e337f08206b8b1dcc02f4e2739347416bb295556584d8b6f658b`；
- 302 条 source clauses：240 equal、56 broader、5 corrected_overconstraint、1 corrected_binding_overconstraint；
- 212 个 active atoms：203 个 source-bound，9 个 versioned-gap-bound；
- 六个 V15 gap：只读 treatment、consumer scope、辅助方法晋升、逐问 handoff、E3 risk match、视觉 source fidelity；
- blocking disposition 0，未豁免强度退化 0。

六个新增 atom 没有强行绑定到被压缩后已不含其详细语义的 V9 clause，而是诚实登记为可复现的 `versioned_gap`。

## 8. 验证结果

### 8.1 当前正式/定向驱动

| 驱动 | 结果 |
|---|---:|
| V15 targeted regressions | 29/29 pass |
| Core behavior | 38/38 pass |
| Manuscript behavior | 22/22 pass |
| Atomic selection | 212/212 pass |
| Atomic deletion mutation | 212/212 pass |
| Migration fidelity | pass；302 clauses、212 atoms、0 strength regressions |
| Contract validation | pass |
| V14 package compatibility | pass |
| V14 contract compatibility | pass |
| V14 official scenarios | pass |
| Capability packet coverage | pass；22 packets、51 capabilities、32 routes、212 atoms |
| Maintenance policy tests | 34/34 pass |

### 8.2 继承的旧 harness 漂移

下列失败与生产 V14 的失败集合逐项相同，不作为本轮“修复成功”证据，也不在本轮越界改造：

- `run_scenario_tests.py`：候选与 V14 均为 12/37，完全相同的 25 个旧用例失败；
- `run_forward_acceptance.py`：候选与 V14 均为 15/22，完全相同的 7 个旧用例失败；
- `run_v12_outcome_tests.py`：候选与 V14 均为 5/6，均是旧 `register-artifact` fixture 缺 `execution-id`；
- `run_transaction_tests.py`：候选与 V14 均在旧 L0 staged transaction fixture 回滚；
- `quick_validate.py`：候选为 7/10；三个实质失败类别与 V14 相同，分别是两条旧 forward fixture 缺 `skill_authorization`、六条旧 platform outcome 未登记、冻结的 V14 release metadata 与 V15 candidate 不匹配。生产目录还存在其原有 `__pycache__`，本轮未删除。

这些结果说明新改动没有扩大旧 harness 的失败集合，但也不能声称整个历史测试体系全绿。

## 9. 真实 A 项目只读回放

回放时 live state 已推进到 revision `181`：Q1 为 S7、Q2 为 S4、Q3–Q5 为 S0。

- 用 V15 candidate validator 检查 G1：pass；
- 检查 G2：只失败 `component:Q1:evidence_file_hash_mismatch`；
- 根因仍是 Q1 evidence locator 绑定了旧的 `planning/02_workplan.md` 哈希，不是本轮候选规则造成；
- 未写入真实项目、`.modeling/state.json`、生产 `skills/`、结果、代码或稿件。

## 10. 剩余边界

本候选仍不是正式 V15 release：冻结 release metadata 保持 V14 身份，因此 release-oriented quick check 会诚实失败。是否清理旧 harness、更新发布元数据和正式替换生产 Skill，应作为独立发布动作由人工确认。

真实 A 项目的 Q1 讲解稿仍缺当前代码/输出 identity 和显式未决项；本轮只把由它发现的通用规范回填到候选，不追写真实项目内容。
