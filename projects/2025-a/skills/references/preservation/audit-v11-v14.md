# V11–V14 全量只读审计：规范 atom、执行方法与运行时可达性

审计日期：2026-08-27  
审计根目录：`/mnt/d/AI/AI_program/2021（第四题）/总skill`  
审计范围：`skills_v11`、`skills_v12`、`skills_v13`、`skills_v14` 中的 `SKILL.md`、全部 `rules/*.json`、7 个 `*-method-notes.md`、route/runtime/ownership/state/release/migration contracts，以及解析器和直接解释这些契约的脚本。  
写入边界：未修改任何被审计版本；本文件是唯一审计产物。

## 1. 结论先行

V11–V14 的最佳资产不是“大控制器”，而是三组很成熟的边界设计：

1. **强规则、比例激活**：`MUST`、适用性、检查时机、证据持久化和失效范围被拆开；G0–G3 只按真实风险升级。证据见 `skills_v14/skills/references/runtime-policy.json:4-15,17-34,127-189`，以及 `skills_v14/skills/SKILL.md:15,39-52,54-89`。
2. **权限与状态绑定**：自然语言由 Agent 理解，机器只验证语义计划；危险动作需要精确请求片段、ChangeSet、state effect、execution 和 receipt 共同绑定。证据见 `skills_v14/skills/SKILL.md:21-37,125-149`、`skills_v14/skills/references/semantic-plan.schema.json:7-16,58-90`。
3. **精确证据与定向恢复**：证据绑定 exact input identity/claim，R1 只读受影响闭包并有逐项回执，baseline 只能吸收已复核路径。证据见 `skills_v14/skills/references/evidence-method-notes.md:13-40`、`skills_v14/skills/references/runtime-policy.json:44-65`、`skills_v14/skills/SKILL.md:101-123,139-149`。

但当前存在一个结构性断点：**atom 能被正确选中，不等于 Agent 能取得完成该 atom 所需的完整方法**。V14 的规则选择是 atom 级，方法加载却只由 route 给出；206 个 atom 中 `context_ref` 使用数为 0，resolver 也不按 `depends_on` 扩展规则闭包。结果是“规范接受条件”大体保真，“如何可靠完成”经常只剩 20–54 行的领域摘要。

因此 V15 不应把详细操作塞回 atom，也不应让 Agent 一次读完整领域手册。最小修正是：

> atom 继续承载一个规范不变量；每个 atom 绑定一个小型 capability packet 片段；运行时取 `route 基础上下文 + 被选 atom + 适用依赖 atom + 对应 packet 片段` 的去重闭包。

## 2. 覆盖统计与版本稳定性

### 2.1 V14 规则结构

| 指标 | 结果 |
|---|---:|
| rule bundle | 9 |
| capability | 51 |
| active atom | 206 / 206 |
| 唯一 rule id / owner / semantic key | 206 / 206 / 206 |
| `MUST` / `SHOULD` | 205 / 1 |
| `runtime_guard / behavior_verified` | 35 |
| `agent_obligation / selection_verified` | 171 |
| 带 `depends_on` 的 atom / dependency edge | 57 / 99 |
| 跨 capability dependency edge | 15 |
| 带 `context_ref` 的 atom | **0** |
| 有显式 conflict 的 atom / edge | 5 / 8 |
| 空 routes / 空 tests / 悬空 dependency | 0 / 0 / 0 |

按 domain：data 18、evidence_delivery 21、governance 35、maintenance 15、manuscript 29、modeling 27、project 14、verification 33、visuals 14。所有领域质量 atom（data/modeling/verification/manuscript/visuals）都是 `agent_obligation / selection_verified`；机器证明的是选择和结构，不是领域 oracle 已实际完成。这一边界在 `skills_v14/skills/references/verification-method-notes.md:30-32` 被正确说明。

### 2.2 method notes 覆盖

| 方法包 | atom 数 | 行数 | 字节数 | 主要问题 |
|---|---:|---:|---:|---|
| project | 14 | 44 | 3,658 | 范围、平台、恢复有骨架；计划/验收操作仍薄 |
| data | 18 | 37 | 2,836 | 有诊断矩阵；缺按数据类型展开的操作闭包 |
| modeling | 27 | 43 | 3,893 | 有候选族索引；规格、比较、实现只到摘要级 |
| verification | 33 | 32 | 2,774 | E1–E4 边界优秀；具体测试设计与失败修复不足 |
| manuscript | 29 | 21 | 1,872 | 只有内容链、reader audit、local edit 摘要 |
| visual | 14 | 20 | 1,091 | 最明显压缩；工程图、可复现制图、逐轮验收均无完整操作包 |
| evidence/delivery | 21 | 54 | 4,377 | 七包中最完整，仍缺 route 跨域闭包 |
| **合计** | 156（另有 governance 35、maintenance 15 无方法包） | **251** | **20,501** | 无 atom 级绑定 |

方法包明确自称“非规范性”，例如 `project-method-notes.md:1-3`、`data-method-notes.md:1-3`；这是正确分层。问题不在非规范性，而在内容过薄且与 atom 无确定绑定。

### 2.3 V11→V14 实际变化

| 版本 | 目标 | 实际规则变化 | 值得保留的新增能力 |
|---|---|---|---|
| V11 | 修复日常过度触发 | 206 个 V10 atom 原样继承 | 分级运行、真实 event 激活、精确证据/失效、多步骤计划。`skills_v11/skills/SKILL.md:13-17` |
| V12 | 恢复统一项目平台；用可观察结果替代测试数量 | 仅 `PRJ.STRUCTURE.LAZY` revision 1→2；其余 8 bundle 未变 | 逻辑平台强制、物理目录懒创建、既有项目 grandfathering。`skills_v12/skills/SKILL.md:13`，`skills_v12/skills/rules/project.json:598-669`，`skills_v12/skills/references/project-method-notes.md:5-13` |
| V13 | 补状态迁移 route、路径预准入、sealed ChangeSet、void execution | 9 bundle 均不变 | `RT.STATE.TRANSITION`、identity preflight、execution lifecycle、Skill 授权隔离。`skills_v13/skills/SKILL.md:13,34-36,92-94,138-147` |
| V14 | 补 R1 新窗口读取回执和 baseline 绑定 | 9 bundle 均不变 | closed-ready recovery、逐项 read receipt、一次消费、baseline 精确合并。`skills_v14/skills/SKILL.md:13,101-123` |

哈希核对结论：

- V12、V13、V14 的 9 个 rule bundle 全部字节一致。
- V11→V12 只有 `rules/project.json` 变化；其余 8 个 bundle 字节一致。
- V12→V14 的 7 个 method notes 全部字节一致；V11→V12 只改了 `project-method-notes.md`。
- `capability-crosswalk.json`、`clause-preservation.json`、`legacy-coverage.json` 在 V11–V14 四版中分别保持同一 SHA-256。

这说明 V11–V14 的新能力主要进入 SKILL/contract/script，而未进入 51-capability / 206-atom 目录。V15 必须同时盘点“继承 atom 能力”和“V11–V14 native control 能力”，否则后者会继续游离在迁移清单之外。

## 3. 当前运行时究竟能取到什么

### 3.1 实际链路

1. Agent 写完整 semantic plan；schema 要求原始 `request` 和 ordered steps：`semantic-plan.schema.json:7-20`。
2. resolver 读取全部 206 atom 到 Python 控制面，但按 route、scope、真实 event、predicate 逐条选择：`scripts/lib_v11.py:905-1023`。
3. 返回给 Agent 的每条 atom 只投影以下字段：`id, strength, domain, owner, instruction_gloss, effect, evidence, outcomes, exceptions, conflicts_with, depends_on, failure_example, enforcement`：`scripts/lib_v11.py:64-77`。
4. 每步 `context_refs` 只来自 route；最终只去重合并字符串引用：`scripts/lib_v11.py:1143-1158,1443,1480-1511`。
5. resolver 不读取 method-note 内容，也不验证 Agent 已读取相应片段；它只返回路径/anchor。

这套结构的优点是：控制面可扫描 206 个小 JSON，而 LLM 不必一次吞下全部规则。缺点是：方法闭包没有随被选 atom 一起形成。

### 3.2 route 层覆盖

V14 有 31 个 route、30 个 context item；28 个 route 有 context，以下 3 个没有：

- `RT.PROJECT.ADVISE`
- `RT.SKILL.AUDIT`
- `RT.SKILL.CHANGE`

其中前者是 G0 建议，空 context 可以接受；两个 Skill route 命中 15 个 maintenance atom，却没有 active maintenance method packet，是实质缺口。

典型跨域失配：

- `RT.VISUAL.CREATE` 的 route context 只有 `visual-method-notes.md`（`route-contract.json:569-575`），但显式可能命中 DATA-IDENTITY、VER-E4、VER-UNCERTAINTY 和三组 VIS capability。
- `RT.MANUSCRIPT.AUDIT` 只给 reader-audit 和条件 visual-audit（`route-contract.json:561-567`），但显式可能命中 data、evidence、artifact、manuscript、model-results、verification、visuals 七个 domain。
- `RT.DELIVERY.FINAL` 只给 `evidence-method-notes.md#delivery`（`route-contract.json:585-591`），但显式可能命中 10 个 capability，包括 manuscript acceptance、E4/uncertainty 和 visual identity。

atom projection 能告诉 Agent“必须满足什么”，却未必告诉 Agent“怎样完成跨域检查”。

### 3.3 三个具体闭包缺口

#### A. 已有 `context_ref` 机制完全闲置

`rule-atom.schema.json:154` 已允许 atom 携带单个 `context_ref`，但 206 个 atom 使用数为 0；`runtime_rule_projection` 也不输出该字段。无需发明复杂新控制器，激活现有字段即可。

#### B. `depends_on` 只被展示，不被解析器闭包展开

99 条 dependency edge 中有 15 条跨 capability，例如：

- `MOD.SPEC.INTERFACE → MOD.RESTATE.OUTPUTS`
- `MOD.RESTATE.REDESIGN → GOV.AUTH.FROZEN_CHOICE + STATE.TRANSITION.GATED`
- `DEL.PROV.CITATIONS → EVD.PROV.CLAIM_MAP`
- `VIS.IDENTITY.NO_MANUAL_VALUES → VIS.IDENTITY.DATA + VIS.IDENTITY.SYNC`

resolver 在 `scripts/lib_v11.py:1379-1413` 只把独立匹配到的 rule 加入结果；`depends_on` 仅在 projection 字段列表 `:73-75` 中被回传。若依赖 atom 的 trigger 本步没独立命中，规范/方法依赖不会自动进入最小完整闭包。

#### C. 条件 context 的 `when_any` 没有按其内容求值

`RT.MANUSCRIPT.AUDIT` 声明 `when_any: [图, 表, figure, table]`（`route-contract.json:567`），但 `context_refs_for_step` 不读取这些 term；它只看 ref 路径是否含 `recovery`/`visual`，再检查 event 前缀（`scripts/lib_v11.py:1143-1157`）。这与“机器不做原文关键词分类”本身不冲突，正确做法应是把条件改成结构化 `when_events` / `when_facets`，而不是保留一个看似生效、实则未消费的词表。

## 4. 优秀设计：V15 应原样继承的原则

### 4.1 比例性

- `MUST` 只在实际适用时阻断接受：`runtime-policy.json:5-15`。
- route + scope + actual event + predicate 四项同时满足：`runtime-policy.json:17-34`。
- G0/G1 不被 G2/G3 的回执、状态和持久证据拖累：`runtime-policy.json:127-174`。
- 闭包按本次 claim/identity 的真实消费者扩展，不用“全项目重做”兜底：`runtime-policy.json:175-189`。

建议：保留这些文字和机器语义，不把 capability packet 读取变成每次全域加载。

### 4.2 权限

- `skill_maintenance` 必须是隔离计划且需要 exact user quote：`semantic-plan.schema.json:43-65`。
- 危险 runtime action 保留 exact request excerpt，但不由关键词自动授权：`runtime-policy.json:111-125`。
- 一个请求可有多个 step-local mode，避免“一个请求只能一种模式”：`runtime-policy.json:36-42`。
- V13/V14 在执行前封存 ChangeSet、state effect 和 identity 路径；失败 execution 可 void 而不是伪造成功：`SKILL.md:147-149`。

### 4.3 证据与状态

- evidence 用 `input_refs + claim_refs + binding_hash` 精确绑定：`evidence-method-notes.md:13-23`。
- working identity 变化只定点失效；milestone/frozen/final 才传播到真实消费者：`evidence-method-notes.md:25-36`。
- state transition 有单一 route，覆盖 state-machine 全边：`SKILL.md:147`；`route-contract.json:52-58,408-415`。
- execution lifecycle 是 open/closed/void，而不是只有成功路径：`state.schema.json#/$defs/execution/properties/status`。

### 4.4 恢复

- 新窗口最低 R1，但不自动升级 R2：`runtime-policy.json:44-65`。
- R1 有角色化必读集、逐项回执、同 plan/step/scope 绑定和一次消费：`SKILL.md:110-121`。
- baseline 只能合并 receipt 已复核路径：`runtime-policy.json:54-64`。
- R2 只在状态损坏、冲突不可归属或显式全量恢复时启用：`runtime-policy.json:180-189`。

这些是 V11–V14 中最值得吸收的非领域能力。

## 5. 高风险与仅存档、运行时不可达内容

### 5.1 领域执行语义被压成摘要，但 migration 只封了粗粒度 source clause

`clause-preservation.json:1-22` 声称它是 V9→V10 的语义保留权威，统计为 51 capability、302 source clause、206 atom；但 clause 由 capability registry 的 `trigger/expected/forbidden` 拆出，而非详细 method procedure。`legacy-coverage.json:5,21-31` 又明确只证明 hash/owner-family lineage，不声称逐行语义等价。

在 V11–V14 中，历史详细模块正文不在 active references；迁移 JSON 只有身份、span、hash 和 disposition。它们是重要审计档案，但不能给运行中的 Agent 提供详细操作能力。

### 5.2 V13/V14 主发布门不再保护 9 个 rule bundle 的语义/基线哈希

- V11 主 gate 明确运行 `validate_v10_corpus.py`、atomic mutation、migration 和 forward acceptance：`skills_v11/skills/scripts/validate_release.py:35-85`。
- V12 仍有 active migration driver，并逐项校验 8 个未改 rule hash 与唯一 project rule delta：`skills_v12/skills/references/release-policy.json:7-27`、`skills_v12/skills/scripts/validate_v12_migration.py:37-45`。
- V14 active drivers 仅 package/contracts/scenarios，六个 required case 全是平台、状态、identity、R1、Skill 授权：`skills_v14/skills/references/release-policy.json:7-40`。
- `validate_v14_package.py:49-73` 只检查文件存在、JSON 可解析和 Python 可编译；`validate_v14_contracts.py:29-178` 不加载 9 个 rule bundle、三个 migration seal 或 method notes。
- V14 把 `validate_migration.py`、`validate_v10_corpus.py` 明确列为 inactive legacy stack：`release-policy.json:41-50`。

所以当前观察到 V12–V14 bundle 字节一致，是审计事实，不是 V14 主 gate 的保证。下一版至少要恢复一个轻量 semantic inventory driver：校验 9 bundle 的 declared delta、206 atom semantic projection、atom→packet mapping 和 packet anchors；不必恢复 V11 的全部大型测试栈。

### 5.3 maintenance atom 的“behavior_verified”绑定到非活跃 V10 工具

15 个 maintenance atom 中 14 个是 `runtime_guard / behavior_verified`；大多 enforcement refs 指向 `apply_rule_change.py`、`run_change_evals.py`、`change-envelope.schema.json`，例如 `rules/maintenance.json:71-78,376-383,453-460,693-700,1077-1084`。但 ownership contract 将这些标成 `legacy_v10_only` 且 active interpreter 为空：`ownership-contract.json:140-175`；SKILL 也声明它们不是 V14 活跃接口：`SKILL.md:171-173`。

这不是语义应删除，而是 enforcement assurance 已失真：active `RT.SKILL.CHANGE` 能选到 atom，却没有 active method packet/guard 实际实现这些 L0–L4、impact、eval、reload、rollback 程序。

### 5.4 state_manager 仍不是并发安全的 CAS mutator

V14 `commit()` 是普通 read-modify-write：先 `require_state()`，内存 revision +1，再 `dump_json()`（`scripts/state_manager.py:32-59`）。`dump_json()` 使用固定 `<state>.tmp` 后 `os.replace`（`scripts/lib_v10.py:73-82`），全项目没有 state lock；只有 checkpoint 与 baseline 子命令显式检查 expected revision（`state_manager.py:919-920,1333-1345`）。

后果：两个普通 G1 mutator 可同时读取 revision N、各自写 N+1，造成 lost update；固定 `.tmp` 还会产生 writer 间覆盖/replace 竞争。V15 应保留 typed-state 语义，但把持久化层改为统一锁 + 全命令 expected revision/CAS + 唯一临时文件 + 文件和父目录 fsync。这是实现层修正，不需要增加业务控制器复杂度。

### 5.5 完整 raw request 的审计价值与隐私边界未分离

- semantic plan 强制完整 `request`：`semantic-plan.schema.json:7-11`。
- resolver 输出完整 request：`scripts/lib_v11.py:1489-1496`。
- execution state 强制保存完整 request：`state.schema.json:232-240`。
- start/end receipt 同时保存完整 request 与完整 semantic plan：`receipt.schema.json:34-47,65-80`。
- CLI 还允许 `--plan-json` inline（`scripts/resolve_route.py:37-51`），会把包含 request 的计划暴露在进程参数中。

代码和契约中没有 request redaction / sensitivity policy。建议保留“Agent 语义源必须是完整请求”和 exact authorization excerpt，但默认持久化只保存 `request_hash + protected request_ref + 必需授权片段`；敏感原文是否落 state/receipt 由明确策略决定。CLI 默认只允许受限权限的 plan file 或 stdin，废弃生产用途的 inline JSON。

### 5.6 ownership contract 对规范 atom envelope 的定义过窄

`ownership-contract.json:17-26` 只把 `effect` 标成 `normative_field`，并明确 gloss/failure/outcomes 非规范；但实际接受行为还由 strength、scope、trigger、routes、exceptions、evidence 和 enforcement 决定。迁移审计也正是按这些字段比较。V15 应把“normative atom envelope”列成显式字段集合，避免 route/trigger/evidence 变化被误判为非语义改动。

## 6. 51 个继承 capability 的 V15 disposition

定义：

- `preserve_verbatim`：atom 的规范 envelope 可原样继承；允许新增 packet 绑定或实现修复，但不改其接受语义。
- `preserve_semantics_rewrite`：保留能力与强度，重写 atom envelope、route binding、enforcement 或 method packet，使其可达且完整。
- `merge`：不删除原有接受点；把多个高度耦合 capability 合并到一个 capability packet / active workflow，由各 atom 继续作为独立验收点。
- `retire`：能力不再适合 active V15。此次 **51 个规范 capability 中没有证据支持直接 retire**；只建议退役失效的旧执行接口。

### 6.1 governance / artifact / recovery / state（12）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| ART-LAZY-001 | preserve_verbatim | `rules/governance.json#ART.ADMIT.*` | 绑定 `artifact-lifecycle#admission`；保留消费者、授权、最小化、非投机四门 |
| ART-PROMOTE-001 | preserve_verbatim | `#ART.PROMOTE.VALIDATE`, `#ART.REGISTER.IDENTITY` | 绑定 promotion packet，与 state execution 复用 |
| GOV-AUTH-001 | preserve_verbatim | `#GOV.AUTH.*` | 原样保留写入/主张/frozen choice/维度分离 |
| GOV-DECISION-001 | preserve_verbatim | `#GOV.DECISION.CLASSIFY` | 放入轻量 decision packet；不把普通实现升级为用户门 |
| GOV-MODE-001 | preserve_verbatim | `#GOV.MODE.*` | 保持 step-local mode |
| GOV-OWNER-001 | preserve_verbatim | `#GOV.OWNER.UNIQUE` | 与 ownership contract 静态校验绑定 |
| GOV-RECEIPT-001 | preserve_verbatim | `#GOV.RECEIPT.*` | 仅 G2/G3 / formal execution 加载 receipt packet |
| GOV-ROUTE-001 | preserve_semantics_rewrite | `#GOV.ROUTE.*` | 保留原请求与状态绑定；补 request privacy policy，清理未消费 regex/when_any 元数据 |
| REC-R0-001 | preserve_verbatim | `#REC.R0.*` | packet `recovery#r0` |
| REC-R1-001 | preserve_semantics_rewrite | `#REC.R1.*` | 把 V14 closed-ready receipt、required-read roles、一次消费纳入 active envelope/packet |
| REC-R2-001 | preserve_verbatim | `#REC.R2.*` | packet `recovery#r2`，保持窄触发，不扩成默认全读 |
| STATE-TYPED-001 | preserve_semantics_rewrite | `#STATE.*` | 保留 typed/evidence/transition 语义；重写存储层为 lock+CAS，补 raw-request 保留策略 |

### 6.2 project（3）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| PRJ-SCOPE-001 | preserve_verbatim | `rules/project.json#PRJ.SCOPE.*` | packet `project-scope#boundary-success-inventory-change` |
| PRJ-PLAN-001 | preserve_verbatim | `#PRJ.PLAN.*` | packet `project-plan#components-dependencies-trace-next` |
| PRJ-STRUCTURE-001 | preserve_verbatim | `#PRJ.STRUCTURE.*` | 以 V12 revision 2 为基线；逻辑平台 + 懒物化不可再被压缩 |

### 6.3 data（4）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| DATA-IDENTITY-001 | preserve_verbatim | `rules/data.json#DATA.IDENTITY.*` | packet `data#identity-before-use`；保留 raw immutable/context/before-use |
| DATA-AUDIT-001 | preserve_semantics_rewrite | `#DATA.AUDIT.*` | 按 schema/missing/anomaly/duplicate/leakage/completeness/semantics 分片，补可执行检查与 failure repair |
| DATA-TREAT-001 | preserve_semantics_rewrite | `#DATA.TREAT.*` | packet 明确候选处理、比较标准、copy-on-write、lineage、审计先后 |
| DATA-FREEZE-001 | preserve_verbatim | `#DATA.FREEZE.*` | packet `data#freeze`，与 artifact/state identity 联动 |

### 6.4 modeling（5）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| MOD-RESTATE-001 | preserve_semantics_rewrite | `rules/modeling.json#MOD.RESTATE.*` | packet `modeling#restate`，含对象/已知/未知/目标/输出/重开决策树 |
| MOD-COMPARE-001 | preserve_semantics_rewrite | `#MOD.COMPARE.*` | packet `modeling#compare`，含同证据比较、baseline、假设与选择 rationale |
| MOD-SPEC-001 | preserve_semantics_rewrite | `#MOD.SPEC.*` | packet `modeling#spec`，完整变量—方程—参数—算法—接口—冻结核销 |
| MOD-IMPLEMENT-001 | preserve_semantics_rewrite | `#MOD.IMPLEMENT.*` | packet `modeling#implementation`，含 deterministic/stochastic 分支和可复现输出登记 |
| MOD-RESULTS-001 | preserve_semantics_rewrite | `#MOD.RESULTS.*` | packet `modeling#results`，含失败运行、解释层级与 claim trace |

### 6.5 verification（7）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| VER-E1-001 | preserve_semantics_rewrite | `rules/verification.json#VER.E1.*` | packet `verification#e1`，按接口/单位/边界/复现/路径/错误/退出状态给操作配方 |
| VER-E2-001 | preserve_semantics_rewrite | `#VER.E2.*` | packet `#e2`，含独立重算、容差来源、加严序列、收敛失败处理 |
| VER-E3-001 | preserve_semantics_rewrite | `#VER.E3.*` | packet `#e3`，含约束、守恒/单调/对称、极限、反例、敏感性 |
| VER-E4-001 | preserve_semantics_rewrite | `#VER.E4.*` | packet `#e4`，含现实机制、尺度、参数识别、用途主张门 |
| VER-UNCERTAINTY-001 | preserve_semantics_rewrite | `#VER.UNCERTAINTY.*` | packet `#uncertainty`，按信息条件选择传播法并绑定 claim |
| VER-ROBUST-001 | preserve_semantics_rewrite | `#VER.ROBUST.*` | packet `#robustness`，预注册 metric/baseline/perturbation，报告翻转边界 |
| VER-S6-DUAL-001 | preserve_verbatim | `#VER.S6.DUAL_AXIS` | packet `#s6-closure`；保持 E1–E4 双轴闭合而不吞并结果/交付门 |

### 6.6 manuscript（6）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| MAN-STRUCTURE-001 | preserve_semantics_rewrite | `rules/manuscript.json#MAN.STRUCTURE.*` | packet `manuscript#structure`，从任务—主张—证据生成结构，不镜像工作日志 |
| MAN-CONTENT-001 | preserve_semantics_rewrite | `#MAN.CONTENT.*` | packet `#content`，含 notation/method/result/limitation/trace/no-dump 的写作闭环 |
| MAN-READER-001 | preserve_semantics_rewrite | `#MAN.READER.*` | packet `#reader-audit`，给首次阅读顺序、scope receipt、修复回归面 |
| MAN-ACCEPT-001 | preserve_semantics_rewrite | `#MAN.ACCEPT.*` | packet `#acceptance`，分 section/global/render/crossref/placeholder，禁止局部 pass 相加 |
| MAN-LOCAL-001 | preserve_verbatim | `#MAN.LOCAL.*` | packet `#local-edit`，继续用直接依赖闭包，不强迫全文审计 |
| MAN-PROFILE-001 | preserve_verbatim | `#MAN.PROFILE.*` | 独立 opt-in packet；不让风格覆盖事实与官方格式 |

### 6.7 visuals（3）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| VIS-DESIGN-001 | preserve_semantics_rewrite | `rules/visuals.json#VIS.DESIGN.*` | 至少拆 `reader-question / chart-choice / engineering-diagram / uncertainty` packet；恢复图类决策、真实性映射和可复现工作流 |
| VIS-IDENTITY-001 | preserve_semantics_rewrite | `#VIS.IDENTITY.*` | packet `visual#identity`，绑定数据/run/source/render/sync/no-manual-values 完整链 |
| VIS-LAYOUT-001 | preserve_semantics_rewrite | `#VIS.LAYOUT.*` | packet `visual#audit`，逐独立图件、最终页尺寸、退化/灰度三轮验收，并覆盖字体/分页/放置/图注 |

### 6.8 evidence / delivery（5）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| EVD-LITERATURE-001 | preserve_semantics_rewrite | `rules/evidence_delivery.json#EVD.SEARCH/POLICY/EXTERNAL.*` | packet `evidence#search`，补 claim-first query、全文范围、反证、时效与来源等级的执行模板 |
| EVD-PROVENANCE-001 | preserve_verbatim | `#EVD.PROV.*` | packet `evidence#provenance`，复用现有 exact identity 设计 |
| DEL-FINAL-001 | preserve_semantics_rewrite | `#DEL.FINAL.*` | delivery packet 必须拉入实际选中 manuscript/visual/verification 片段，而非只读白名单摘要 |
| DEL-PROVENANCE-001 | preserve_verbatim | `#DEL.PROV.*` | packet `delivery#provenance`，与 EVD provenance 共享底层身份但保持交付阶段独立门 |
| DEL-HANDOFF-001 | preserve_verbatim | `#DEL.HANDOFF.STATE` | packet `recovery#handoff`，不把 narrative summary 当唯一状态 |

### 6.9 maintenance（6）

| capability | disposition | 规范 atom | 执行方法处理 |
|---|---|---|---|
| MNT-CLASSIFY-001 | merge | `rules/maintenance.json#MNT.CLASSIFY.*` | 与 IMPACT、OWNER 合入 active `skill-change-analysis` packet；保留各 atom 验收点 |
| MNT-IMPACT-001 | merge | `#MNT.IMPACT.*` | 同上；显式计算 atom→route→contract→script→packet→eval 影响闭包 |
| MNT-OWNER-001 | merge | `#MNT.OWNER.CANONICAL` | 同上；owner 检查由 V15 active tool 实现 |
| MNT-EVAL-001 | merge | `#MNT.EVAL.*` | 与 RELOAD 合入 `skill-change-validation` packet；保留 positive/near-negative/conflict 三类观察 |
| MNT-RELOAD-001 | merge | `#MNT.RELOAD.*` | 同上；fresh process 与可用时独立 Agent 是两个证据等级 |
| MNT-ROLLBACK-001 | preserve_semantics_rewrite | `#MNT.ROLLBACK.*` | 绑定 active base→candidate→freeze/release 流程，移除对 legacy change-envelope 的 behavior-verified 声明 |

Disposition 统计：`preserve_verbatim=20`、`preserve_semantics_rewrite=26`、`merge=5`、`retire=0`，合计 51。

## 7. V11–V14 native control capability disposition

这些能力不完整落在 51 个继承 capability 中，V15 应单独登记：

| native capability | 来源 | disposition | 说明 |
|---|---|---|---|
| proportional activation / G0–G3 | V11 runtime policy | preserve_verbatim | V15 的总原则 |
| exact evidence binding / precise invalidation | V11 state/evidence | preserve_verbatim | 避免 epoch 式全重做 |
| multi-step semantic plan / step-local mode | V11 | preserve_verbatim | 保留 Agent 理解、机器验证边界 |
| logical canonical platform + lazy materialization | V12 | preserve_verbatim | 防止“懒创建”退化成任意路径 |
| outcome-focused release evidence | V12 | preserve_semantics_rewrite | 原理保留；恢复 rule/packet semantic inventory driver |
| total state-transition route | V13 | preserve_verbatim | 单 route + 全边场景 |
| path admission + sealed ChangeSet + identity preflight | V13 | preserve_verbatim | 在写前阻断越界 |
| execution void lifecycle | V13 | preserve_verbatim | 失败可审计终止 |
| isolated Skill authorization | V13 | preserve_verbatim | 不把项目请求扩权为 Skill 维护 |
| R1 read receipt / one-shot recovery / baseline binding | V14 | preserve_verbatim | 只读最小受影响闭包 |

## 8. 建议的 atom→capability packet 映射

建议新增一个薄索引（或直接使用现有 atom `context_ref`），而不是扩大 route controller：

```text
selected atom
  ├─ normative envelope: strength/scope/trigger/effect/evidence/exceptions/enforcement
  ├─ hard semantic dependencies: depends_on
  └─ context_ref: references/capability-packets/<packet>.md#<section>
```

建议 packet 集合：

| packet | 绑定 capability |
|---|---|
| `governance-routing` | GOV-MODE, GOV-AUTH, GOV-DECISION, GOV-OWNER, GOV-ROUTE |
| `artifact-lifecycle` | ART-LAZY, ART-PROMOTE, PRJ-STRUCTURE, DATA-FREEZE |
| `state-evidence` | STATE-TYPED, GOV-RECEIPT, EVD-PROVENANCE |
| `recovery` | REC-R0/R1/R2, DEL-HANDOFF |
| `project-scope-plan` | PRJ-SCOPE, PRJ-PLAN |
| `data` | DATA-IDENTITY/AUDIT/TREAT/FREEZE，按 anchor 分片 |
| `modeling` | MOD-RESTATE/COMPARE/SPEC/IMPLEMENT/RESULTS，按 anchor 分片 |
| `verification` | E1/E2/E3/E4/UNCERTAINTY/ROBUST/S6，按 anchor 分片 |
| `manuscript` | STRUCTURE/CONTENT/READER/ACCEPT/LOCAL/PROFILE |
| `visual` | DESIGN/IDENTITY/LAYOUT，并进一步分数据图、工程图、渲染审计 |
| `evidence-delivery` | LITERATURE/PROVENANCE/FINAL |
| `skill-maintenance` | change-analysis、change-validation、release-rollback |

每个 packet section 应承载：

1. 适用前提与输入身份；
2. 操作步骤或决策树；
3. 可选工具与人工判断边界；
4. 产出/证据 recipe；
5. 常见失败、修复和复检；
6. 例外与 not-applicable 判断；
7. 反向列出所实现的 atom ids。

packet 不复制 atom 的规范 effect/strength；atom 也不承载教程、长 checklist 或工具说明。

## 9. 运行时最小完整闭包

建议 resolver 只做以下轻量集合运算：

1. 按现有 route/scope/event/predicate 选择 atom。
2. 对 selected atom 的 `depends_on` 做传递闭包；每个依赖仍需经过适用性判断，不适用则记录 N/A，缺事实则按现有 tier 规则 deferred/block。
3. 收集 route base refs；它们只提供当前工作面的共同上下文。
4. 收集 selected/applicable dependency atom 的 `context_ref` anchor。
5. 收集 packet 声明的 shared prerequisite refs，去重后输出 manifest：`rule_ids + refs + reason + content_sha256`。
6. Agent 只读取 manifest 指向的片段；若某个 applicable MUST atom 标记 `method_required` 却缺 packet/anchor，则不能声称完成其 effect。

不建议：按 route 一次加载整领域、把所有 206 atom 常驻上下文、按 request 关键词选 packet、或让 controller 判断领域 oracle。

## 10. V15 最小发布证据

主 gate 建议保持精简，但必须覆盖当前空白：

1. **semantic inventory**：9 bundle 的 semantic projection hash；每项 delta 必须有 disposition。
2. **packet closure**：206 atom 中每个 active atom 满足 `self_contained=true` 或有效 `context_ref`；anchor 存在，反向 mapping 一致。
3. **dependency closure**：99 edge 全部可解析；至少覆盖 15 个跨 capability edge 的代表性正/反场景。
4. **route-context scenario**：visual create、manuscript audit、final delivery、skill change 四个跨域案例证明只加载最小完整 packet 闭包。
5. **method loss mutation**：删除/改名一个 required packet section，gate 必须失败；这比检查 heading 数量更有意义。
6. **maintenance active binding**：所有 `behavior_verified` ref 必须属于 active interpreter/driver，禁止指向明确 inactive 的 legacy stack。
7. **state concurrency**：两个普通 G1 mutator 从同一 revision 出发，只允许一个成功或安全重试，不能 lost update；并验证无固定 `.tmp` 竞争。
8. **request privacy**：plan/receipt/state/argv 的 raw request 留存符合明确策略；authorization excerpt 仍可验证。
9. **既有六个 V14 scenario**：平台、全边迁移、identity preflight+void、R1 新窗口、Skill 授权继续保留。

## 11. 建议 retire 的不是能力，而是失效接口/伪契约

1. 从 active assurance 中 retire `change-envelope`、`apply_rule_change.py`、`run_change_evals.py` 等 legacy V10 绑定；文件可保留为历史诊断，但不能继续证明 V15 behavior。
2. route 的 `patterns` / `exclude_patterns` 当前不被 resolver 使用。二选一：明确标成 Agent vocabulary hints，或从 machine contract retire；不要继续让其看似是执行路由器。
3. retire 生产环境的 inline `--plan-json`；保留 file/stdin。
4. migration JSON、V10 lineage seal 不应删除；应保留为 archive，并由轻量 active semantic inventory driver 消费其必要投影。

## 12. 未决项

1. `context_ref` 是直接写入每个 atom，还是放在独立 `capability-packet-index.json`？前者绑定最强，后者可在不改冻结 atom effect 的前提下快速补齐。建议 V15 先用独立索引，再把字段纳入下一次 schema revision。
2. `depends_on` 是硬语义前置、证据前置，还是仅解释关系？当前字段无类型。建议先给 99 edge 分类，否则闭包扩展可能过载或漏门。
3. raw request 哪些场景必须持久化全文？Skill authorization 和危险命令需要 exact excerpt，但这不等于 execution/state/双 receipt 都必须保存全文。
4. method packet 的规范地位：建议仍非规范；release 只保护“存在、映射、anchor、hash 与行为案例”，不把示例和工具偏好误升为 MUST。
5. V15 是否继续要求与 V10 bundle 字节一致？建议改为 semantic projection + declared disposition，而不是永久 byte freeze；但 V15 发布基线一旦确认，应重新封印其 own rule+packet inventory。

## 13. 最终判断

V11–V14 的控制哲学总体优秀：比例性、权限、精确证据、typed state、定向恢复均应成为 V15 主骨架。下一轮的首要工作不是再加一层控制器，而是修复两条断开的边：

1. **selected atom → 完整但小型的 capability packet**；
2. **declared semantic preservation → active release gate 的可观察证据**。

同时把 state 持久化改为真正的 lock/CAS，并明确 raw request 的审计与脱敏边界。完成这四项后，才能既保留能力，又不让 Agent 每次读取超长上下文。
