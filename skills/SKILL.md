---
name: mathematical-modeling-project-controller
description: 端到端管理数学建模竞赛或研究项目，覆盖范围、文献证据、数据、建模、实现、验证、论文、图表、交付、接手恢复，以及用户明确授权时的 Skill 规则维护。用于完整项目、现有项目续作或有项目语境的局部任务；不用于孤立普通数学题、无项目语境的通用排版，或未获授权的 Skill 自修改。
metadata:
  version: "16.2.0"
  release: "stable"
---

# 数学建模项目控制器 V16.2.0

V16.2 延续 V16.1 的控制契约，依据完整项目回顾，澄清整题语境承接、证明对象、连续模型可计算化、队友稿表达、精度与归因、图件及交付故障的方法实例。规则强度、状态、权限、正式验收门和活跃发布驱动不变。本次差量与未纳入事项见[本次经验审计](references/preservation/v16-2-cumcm2026-lessons.md)，仅在维护审阅时读取。

## 目标与不变量

V16 以 V15.0.1 的能力双层、平台准入、ChangeSet、恢复绑定和执行生命周期为基线，修复真实项目中“一个跨题兼容实现补丁被放大为十几次状态迁移与回执”的控制缺陷。新增的是兼容变更 validity overlay 和原子闭包对账，不是新状态节点、证据等级、逐文件门禁或自动流水线；模型合同一旦变化，仍回到普通最早层 reopen。

必须分开处理五个维度：规则强度、实际适用性、检查时机、证据是否持久化、变化的失效范围。`MUST` 只表示规则实际适用时，不满足就不能接受相应结果；它不表示每次请求都要激活、写回执、重建证据或使整个组件失效。该运行时解释由 [runtime-policy.json](references/runtime-policy.json) 拥有。

[ownership-contract.json](references/ownership-contract.json) 继续保证每个规范事实只有一个 owner。Agent 和脚本不得复制或改写规则语义；脚本只验证内部计划、状态和证据结构。

## 能力双层与无损渐进披露

不要把“上下文短”误解成“能力文字也必须短”。V16 延续一个能力的四层结构，各层职责不可互换：

1. `rules/*.json` 的 atom：拥有适用条件、强度、规范 effect 和验收边界，回答“何时必须做到什么”；
2. `SKILL.md` 与机器契约：拥有权限、路由、状态、证据和执行边界；
3. 方法路由与 `references/capability-packets/`：保存完整实施程序、判断依据、例外、失败修复和人工确认点，回答“怎样可靠地做到”；
4. `references/migration/` 与 `references/preservation/`：保存历史原文、谱系和取舍理由，只在审计或能力恢复时读取。

atom 的 `instruction_gloss` 只是定位提示，不是完整做法。任何需要实际实施的领域能力，都不得只凭 gloss、标题或短摘要执行：先由 route 选中短方法路由，再按路由完整读取所需能力包。能力包是非规范性实施知识，不能扩大授权、增强 atom、增加状态门或把建议变成新的 `MUST`。映射和边界由 [capability-packet-registry.json](references/capability-packet-registry.json) 统一记录。

一个步骤通常完整读取一至三个能力包，不常驻加载全部资料。如果真实任务需要更多包，按数据准备、规格、实现、验证、表达等真实阶段拆分；在阶段边界保留一个简短续接胶囊，至少记录当前目标、已读能力包、已确认决定、权威输入/产物、未完成风险和下一能力包。不得截断必需程序，也不得把各包的摘要拼接成一个新的压缩版替代原文。

人工确认只放在会改变研究方向或正式责任的节点，例如范围取舍、数据处理、模型选择、高风险科学示意图样板和最终交付。相关选项应成组说明，已确认决定在前提未变化时不重复询问；准备性分析和不依赖该决定的工作可以继续。这些确认点服务于人工深度参与，不把项目改造成每一步都等待放行的自动流水线。

## 自然语言与内部语义计划

先理解用户完整意图，不按关键词、固定口令或一次只能做一件事来解释请求。用户可以用通俗语言确认检查通过、要求推进、同时安排后续工作；标准 route、mode、tier 和 event 词汇只供内部使用。

一个请求可以拆成多个有序步骤，每个步骤拥有自己的 mode、tier、对象、动作、组件和真实事件。只有存在依赖的后续步骤受前一步失败影响；独立步骤可以继续。不要因为一个子句需要澄清而阻断整个请求。

步骤拆分只是内部依赖模型，不是“一步一卡”的交互协议。一个自然语言请求已经授权的连续步骤可以在同一轮依次完成；不得在每步后要求用户改用标准口令、先单独关闭、再另发推进指令。只有后续动作超出原请求范围或出现真实用户取舍时才停下来询问。

G0/G1 若不需要或尚未建立权威项目状态，可以在计划中声明经过检查的 `working_context`（组件类型与当前阶段）；它只服务本轮适用性判断，不能冒充持久状态。G2/G3 不接受该替代，必须读取权威状态。

G1 及以上工作或复杂多步骤请求使用 [semantic-plan.schema.json](references/semantic-plan.schema.json) 形成内部计划，再由解析器验证：

```bash
python3 -B scripts/resolve_route.py --plan "<plan.json>" [--project-root "<root>"]
```

解析器不从用户原话猜 mode、权限或 route。它只验证 Agent 已形成的计划是否与真实状态、route contract、动作事件词表和依赖顺序一致。原请求保留用于审计与哈希，不作为机器口令。

`skill_maintenance` 必须是隔离的 Skill-only 计划，并携带 `skill_authorization`，记录当前请求或更早的明确用户授权原话。普通项目计划不得混入 Skill 修改步骤；项目推进发现 Skill 缺陷时，只完成仍合法的项目步骤并报告阻断，不能把“继续项目”扩张成维护授权。

## 规则只由真实动作触发

规则进入某一步的检查集合，必须同时满足：

1. route selector 与该步匹配；
2. 对象、组件类型和真实状态在 scope 内；
3. 该步实际发生的 event 与 trigger 相交；
4. predicate 与 runtime exception 的事实成立。

不得为每个请求合成全局事件，不得为每个写请求合成所有可写事件，也不得把某 route 可能执行的全部动作提前广播。`manuscript_audit`、`writing_profile_apply`、`state_transition`、`artifact_register`、`recovery_assessment` 等事件只有在该动作真实发生时才能出现。

冻结 V10 atom 的少数 event 名称兼作旧版语义 token。V16 继承 V15 的边界：只可把本步明确声明、实际写入或实际审计覆盖的 facet 正规化成对应 token，并记录来源；不得由 facet 直接点名规则，也不得借正规化广播未覆盖的动作。最终仍由 atom 自身的 route、scope、trigger 和 predicate 决定适用性。

普通 G0/G1 步骤中，领域 `agent_obligation` 缺少事实时只延迟相应验收声明；Agent 继续调查或完成不依赖它的工作。涉及动作安全的 `runtime_guard` 仍只阻断受影响步骤。G2/G3 的 `MUST` 验收条件缺少当前事实或证据时，才阻断相应 checkpoint 或 release。

## 四级运行强度

| Tier | 用途 | 强制机制 |
|---|---|---|
| `G0_ADVISORY` | 回答、解释、规划、无状态依赖的只读检查 | 无项目状态、恢复、回执或工件事务 |
| `G1_WORKING` | 日常分析、实现、论文编辑和多文件联动修改 | 一个 ChangeSet、受影响闭包验证、简短结果摘要 |
| `G2_CHECKPOINT` | 状态迁移、冻结决定、里程碑 identity、章节或阶段验收 | 目标恢复检查、类型化精确证据、checkpoint 回执 |
| `G3_RELEASE` | 最终交付或 Skill 发布 | 声明交付范围的完整审计、正式工件和封印回执 |

高 tier 的机制不得下沉成低 tier 的默认前置动作。只有实际动作跨越相应边界时升级；S6 就绪检查本身可以只读，关闭 S6 才是 G2；论文日常改写是 G1，声明章节或全文完成才进入 G2，最终交付才进入 G3。

## G0/G1 日常工作

G0 不要求项目存在 `.modeling/state.json`，也不调用 recovery、receipt、artifact 或 evidence persistence 工具。

G1 以一个 ChangeSet 执行用户要求的完整修改面。ChangeSet 可以同时包含多个相关文件；“一次只能改一个文件”不是安全不变量。开始前识别实际语义 facets、目标 claims 和直接消费者，成组修改后一次验证。普通工作文件不需要逐文件 proposal、register、refresh，也不需要 execution ledger、start/end receipt 或全工作区 manifest。

G1 的证据可以是本轮实际检查结果、命令输出、diff、编译结果或人工推理记录，不必全部写入项目状态。只有要支持 G2/G3 声明的证据才持久化为严格结构。

每个实质问题的队友讲解稿固定写在 `docs/<task-id>/solution_brief.md`。它是逐问、完整的建模说明，不是九项交接清单、运行手册或论文正文。可在 S5 结果已可解释时用 G1 起草，通常在 S6 技术验证期间完成；实际关闭该问 S6 前，必须由人阅读当时的完整文件并确认能够复述对象、机制、证据、结论和边界。文件存在、静态结构通过、提前授权、自然暂停或技术四轴通过都不能冒充这次人审。该人工门只在 S6 关闭时结算，不把日常编辑升级成 checkpoint：S7 后的纯表达同步仍是 G1，也不使已关闭技术证据失效；只有数学合同、结果或主张边界真实变化时，才按其最早变化层更新受影响稿件与接受闭包。

当后做题目产生的新实现技巧要回传到前题，先把探索留在来源题，用预定指标与来源题 E1/E2 确认它确有正收益且没有改变模型合同；未证实的技巧不传播。若问题解释、数据合同、假设、目标、约束、可行域、候选集、模型选择、数学规格和主张边界都不变，把整个回传声明为一个 `compatible_implementation_change`。G1 使用 `RT.PROJECT.COMPATIBLE_CHANGE / propagate_compatible`，在一个跨组件 ChangeSet 中连续修改全部直接目标和消费者；讲解稿、配图和说明只有内容或引用实际受影响时才进入该闭包。不为每道题重开状态、不刷新正式 identity、不写持久 evidence/ledger/receipt。`effects.changed_facets` 的并集必须与 ChangeSet facets 完全相等，`effects` 只列真正受影响的后规格 evidence levels；额外 facet、模型前缀 level 或恢复评估发现的闭包外组件都会退出快车道。

需要正式接受这批回传时，只执行一个 `G2_CHECKPOINT / reconcile_compatible`：一次 target identity checkpoint、一次 execution、一个 [compatible-change-bundle.schema.json](references/compatible-change-bundle.schema.json) bundle。execution 同时封存目标与来源题的 `state/status/invalidated_at_revision`；reconcile 先实时核对复用的模型前缀与来源题证据，再把所有实际 protected registered identity delta 与 `artifact_updates` 做闭世界对账，全局扫描旧 file/command locator 和 artifact input ref 的 exact consumers，并要求新的 file/command replacement locator 位于 ChangeSet。只有 claim identity 确实变化时才在可选 `claim_updates` 中声明旧/新 producer evidence `claim` 文本的 SHA-256，并核对旧 identity 的 typed claim consumers 及其新绑定；普通实现回传不回填未变化 claim。随后原子地 stale 旧的受影响 levels、安装每个 level 的新 PASS、刷新声明 identity，并在原状态复验全部目标。无 exact evidence 绑定的无关 working artifact 漂移不阻断本批。若 bundle 缺证、漏报 identity/path、显式 claim producer/consumer 越界、触及未声明 consumer、组件有效性漂移，或变化实际进入模型合同/候选选择/主张边界，整笔拒绝且不部分落盘，按最早真实变化层走普通 reopen。快车道减少控制回填，不减少 E1/E2 和实际受影响的 E3/E4 技术验证。

“今天先到这”“做收尾整理”“暂停并记下后续”等自然表达执行为一个 `G1_WORKING` 的 project `pause`，只声明实际 `handoff` event：同步本轮已经发生的控制状态变化、open decisions、next legal actions 和已经观察到的登记 identity 变化。暂停不是 checkpoint、S6 验证、final delivery、全项目审计或 Skill 自检，不得由它派生求解器、重算或执行型验证。若同一请求明确要求“关闭 Q3 S6 后暂停”，形成一个有依赖的 `Q3 close_s6(G2) → project pause(G1)` 计划并在本轮完成；暂停步不得把 scope 扩到 Q4 或其他组件。

open decisions 和 next actions 都只写入 `.modeling/state.json`：`state_manager.py add-open-decision` / `resolve-open-decision` 负责待确认决定，`set-next` 负责下一动作。进入上下文压缩、长工具调用或可能中断的边界前，使用 `state_manager.py checkpoint-before-interrupt` 在同一状态文件中落一次控制检查点；不生成 HANDOFF、manifest、receipt 或其他同步文件。

## 最小一致性闭包

验收单位是本次修改的最小一致性闭包，而不是当前 route 的所有规则，也不是整个项目：

- 不改含义的错字、标点和润色：目标句、完整段落、直接引用点；
- 术语、符号、单位、数字、数据 identity、结论强度或图表含义变化：所有直接使用这些 identity 或 claim 的消费者；
- 模型、接口、冻结参数或上游结果变化：真实下游代码、结果、论文和交付消费者；
- 章节完成声明：该章节的通用与专项验收规则；
- 全文完成、里程碑或交付：相应完整范围。

修改时先汇集闭包内全部适用约束，联合设计改动，再联合验收。不得先逐条打补丁、把多次局部 `pass` 相加成整体通过，也不得为避免遗漏而把所有规则常驻激活。论文闭包的结构化边界见 [manuscript-change-closure.json](references/manuscript-change-closure.json)。

若两个实际适用的 `MUST` 在同一维度无法同时满足，先用更窄 scope、当前证据、`refines` 或 `supersedes` 关系解析；仍有真实取舍时只停止受冲突影响的动作并提交用户决定。不要把不同维度压成一张总优先表。

## 状态、恢复和工件

统一项目平台是逻辑契约，不是预生成目录树；先区分“普通 G1 路径能否落盘”和“工件是否取得正式语义身份”。writable semantic step 在执行前只对 ChangeSet 中有意保留的新路径做命名空间 preflight：路径使用唯一的 canonical POSIX 相对写法，必须位于项目内，并至少命中一个 canonical semantic placement、明确的 project-support namespace，或已存在且非保留的项目顶层目录。`paper/**`、`output/**` 等同时匹配多个 placement 是合法的；G1 不靠路径猜测 `platform_role`，也不为普通文件逐个创建 proposal。缓存、虚拟环境、编译中间物和未保留工具副作用不得冒充 ChangeSet 或 runtime `output_paths` 中的保留产物。对本计划已声明的 ChangeSet 路径，还要在 canonical 文本键之外比较其项目内 resolved physical target：一个内部 symlink 路径可单独使用，但同一步或无依赖步骤不能用两个不同写法并发指向同一 target；此检查只覆盖已声明路径，不扫描整个项目。

只有路径进入 artifact proposal，或工件跨入 milestone、frozen、final 等正式身份边界时，才必须由用途、消费者和人工审计明确选择 [project-platform-contract.json](references/project-platform-contract.json) 中的一个 `platform_role`，并让 canonical、contained 的 proposal path 与 class 匹配所选角色；正式登记不能重新接受 `./`、重复分隔符、反斜杠或尾分隔符等文本别名。普通 namespace-admitted G1 新文件不得仅因“首次创建”而选中 proposal/consumer/no-bypass atoms；这组三项首次准入义务只在步骤真实声明 `artifact_register` 时激活，后续 refresh 与 promotion 分别沿用自己的 identity/promotion controls，不重跑首次登记门。路径还能匹配其他角色不是冲突；所选角色与真实职责不一致才阻断。只有准入通过且确实要写入时才创建必要父目录，不能把“懒创建”解释为自由命名、预铺脚手架或事后登记整批缓存。

既有项目先识别现状，不自动移动、改名或重排用户文件；既有精确路径在角色与位置不变时继续 grandfather，但 repository/controller 内部路径与 transient 路径先于 grandfather 检查。经定向检查确认已经存在的非保留顶层目录，可以继续接收其真实工作流所需的新子文件，但这不自动赋予正式工件角色，也不授权建立另一个全新顶层目录。

若当前真实工具流确实需要一个契约尚未覆盖的 fresh 顶层，只阻断受影响的 ChangeSet，并取得一次有界人工批准；该步才在 `facts.platform_extension` 中记录当前 request 内的批准原话、精确 `top_level_namespaces`、用途和回滚。批准只对同一步这些顶层下的 unknown path 生效，不能覆盖 noncanonical、reserved 或 transient 拒绝；canonical/support/既有命名空间的普通 G1 步骤不得携带这层额外门禁。`.modeling/state.json` 与绑定 recovery assessment 的恢复材料按明确 allowlist 管理，其他 `.modeling`、版本库内部目录和控制器元数据目录不能借角色、grandfather 或 existing-project 规则泛化开放。

`.modeling/state.json` 只保存需要跨轮次延续的当前事实、正式 identity、决定和 checkpoint 证据。日常 G1 工作不因为缺少状态而失败，也不为了留下过程痕迹频繁改写状态。

恢复仅在动作依赖既有权威状态、用户明确要求续作/恢复、检测到登记的受保护 identity 变化，或 G3 交付检查时运行：

```bash
python3 -B scripts/assess_recovery.py --project-root "<root>" --gate G1 --new-window
```

- `R0_CONTINUE`：只用于同一未中断窗口中的直接连续工作。当前 checkpoint 必须仍有效；此后所有相关变化都来自本窗口已经记录的 ChangeSet，且失效传播已经闭合、没有未解释的外部变化。R0 可以面对已经解释的 workspace delta，不要求工作区字节不变；它不建立 recovery、manifest 或读取回执。
- `R1_TARGETED`：只用于可信、当前且覆盖完整的 workspace baseline 上的可证明有界增量。每个相关新增、修改或删除都必须能定位到语义 owner，依赖图必须足以给出完整传递消费者闭包；随后完整读取变化项、owner、闭包消费者及其声明输入，闭包外对象只由 baseline identity 证明未变。
- `R2_FULL`：用户明确要求全量恢复时无条件采用；状态或项目 identity 缺失、损坏或冲突，baseline 缺失、过期或覆盖不全，相关变化不能归属，消费者闭包不能证明完整，或 R1 阅读中发现范围外漂移时也采用。R2 重新取得整个项目的可信上下文，而不是一个更大的 R1。

判定顺序固定为：不依赖既有项目事实则恢复不适用；显式全量恢复或状态/项目 identity 异常先判 R2；否则只有满足同窗连续条件才判 R0；不满足 R0 后，只有 baseline、变化归属和消费者闭包三项资格同时成立才判 R1；其余一律判 R2。跨窗口协作、新会话、上下文压缩/恢复或无法证明同一会话只负责排除 R0，不能单凭“新窗口”证明 R1 有资格。含 `recovery_assessment` 的 semantic plan 必须声明 `window_context`（`same_window`/`new_window`/`unknown`）；缺省按 `new_window` 处理。

workspace baseline 是一个可信时刻的全项目快照索引，不是项目副本、HANDOFF 摘要、若干 `watch_roots` 或“字段存在”的同义词。它至少绑定项目根 identity、状态 revision、完整 live inventory、各条目的路径/类别/大小/hash、明确排除项、依赖图版本以及创建它的 closed recovery 或可信同窗 execution。扫描提示可以优化遍历，但不能缩小正确性范围；旧式或部分 baseline 仍可读取为线索，不能授予 R1 资格。

R1 不是哈希检查标签。其基础必读集由当前步骤确定，只包含权威状态、官方题面与附件、目标/上游/受影响组件的 milestone/frozen/final 规划流程、相关 current file evidence，以及实际 workspace delta；不扩成全项目内容复读。一般 R1 对题面与冻结流程进行内容或结构化语义读取，其他正式 identity 至少读取其身份与验证摘要。兼容变更对账是窄例外：未变题面只核 identity，语义复读限于目标题当前 `model_spec`/`selection_rationale`、来源题的规格/实现/E1/E2 来源和实际 delta；不能重复读取全项目官方附件或所有旧 PASS 文件来证明同一个实现补丁。恢复评估若发现 effects 或消费者超出已经证明完整的闭包，不允许在 R1 内一边补图一边宣称范围有界；在同一 recovery episode 升级为 R2。`hash_only` 仍不能代替需要语义检查的项目。

所有依赖项目状态的 G2/G3 项目步骤必须显式声明 `recovery_assessment`。R1 或 R2 只为一个实际恢复 episode 建立一个 recovery id，并由 [recovery-receipt.schema.json](references/recovery-receipt.schema.json) 提交一份合并回执；不得按问题、文件、消费者或门禁重复开启。R1 升级 R2 时沿用同一 id，已经完整读取且复核后 identity 未变的条目直接进入最终回执。`closed_ready` 表示读取覆盖完成且当前动作没有恢复所发现的阻断；`closed_blocked` 表示同样完成了规定读取，但存在已明确登记的 stale/missing/authorization gap。只有同 plan、step 和 scope 的 `closed_ready` recovery 才能进入 checkpoint；`closed_blocked` 可以结束恢复隔离，但相应业务动作仍被 gap 阻断。`record-route` 把 recovery id、最终等级、窗口上下文、assessment hash 和唯一回执 hash 封存在 execution ledger。

workspace baseline 只能吸收最终合并回执实际覆盖、revision 仍精确一致且 inventory coverage 完整的路径；无 recovery id、无精确 revision、存在未分类 live item 或复核后 manifest 已变化时必须拒绝。R2 的读取覆盖完整但项目证据存在已知 gap 时，可以保存精确快照 baseline；该 baseline 不把 gap 变成 PASS。正常正式执行也可在消费同一 `closed_ready` recovery 的 `execution_started` commit 中合并这些已复核路径，不能整体吞入未复核工作区。

未登记 working 文件、无关 dirty 文件、普通新增文件、进入 S6、完成局部工作或仅仅进入 G3 都不能单独触发 R2。G1/G2 默认只核对已登记的 milestone、frozen、final identity；G3 对声明的交付范围做完整性审计，并依据实际 identity 状态得到 R0/R1/R2，而不是把 tier 本身等同于 R2，也不把整个工作区当成洁净门。

普通文件由 ChangeSet 批量管理。只有 milestone、frozen、final 工件需要正式准入和登记。新登记工件建立 identity，但不使生产者或消费者失效；已有工件 identity 变化时才按精确绑定传播。

R2 是恢复控制面和真实证据缺口的隔离态，不是重跑项目的许可。R2 先重新枚举项目根下的 live inventory，使每个当前对象都被表示并归类；所有唯一文本、代码和配置必须从头读到 EOF，Office/PDF、图像、数据集与其他二进制按原生、结构化或视觉载体检查，内容重复件可以用 hash 指向已完整读取的 canonical 对象，未知对象必须检查后分类。随后从实际材料重建组件、依赖、identity 与 provenance，复用仍一致的证据，并如实登记 missing/stale gap。承载逐对象明细的 full manifest 必须位于项目根之外，避免清单写入改变它正在证明的 inventory；项目状态只记录其 path、hash 和计数。R2 在项目内只能写 `.modeling/state.json` 与 allowlist 中的恢复绑定材料；冻结 atom 所说的 evidence rebuild 或 rebuild commands 只指上述枚举、读取、身份与一致性检查，不等于运行 solver 或 verifier。R2 打开时禁止模型实现与执行、执行型验证、论文实质写入、交付构建和状态晋级。

R2 只有在全项目 inventory 已覆盖、所有当前对象都有规定读取结果、没有漏读/截断/未分类对象且唯一合并回执已封存后，才可关闭为 `closed_ready` 或 `closed_blocked`。控制状态结构有效本身不能提前关闭 R2。恢复闭合后可在同一用户轮次重新解析原计划，不要求用户再发“关闭恢复”或“继续”口令；确有 stale/missing 证据需要重算时，先作为 `closed_blocked` 的已知 gap 保留，只有原请求已授权相应 runtime action 时才在隔离关闭后单独执行。

## 仅危险命令的执行绑定

普通读取、编辑、多文件 ChangeSet、编译、排版渲染和不执行项目代码的局部检查不走额外门禁，也不产生 G1 ledger 或回执。只有项目求解、执行型验证、既有结果重算、Skill 定向测试、Skill 全包自检和全项目审计需要在相关 step 的可选 `runtime_actions` 中声明精确 component scope、argv/cwd、输出范围与授权来源，并通过：

```bash
python3 -B scripts/run_authorized_action.py --plan "<plan.json>" --project-root "<root>" --step-id "<step>" --action-id "<action>"
```

该入口在启动命令前于同一进程重新解析计划，核对 request/plan/step/component/root/command/state/recovery 绑定，然后直接执行；它不是“先发 token、再等用户确认”的双门。`resume`、`recover`、`handoff`、`pause`、S6 readiness/close 和 final delivery 本身都不能派生 solver、verifier、重算或 Skill 包自检权限。代理不得绕开该入口直接启动这些危险命令。

直接用户授权保留原请求中的精确片段用于审计，但解析器不把片段当标准口令，也不对自然语言做关键词分类。脚本因此能验证来源、scope 和实际命令绑定，不能独立证明 Agent 的全部语义理解；代表性正反例与混合请求测试负责约束这一边界，而不是增加逐步确认。

## 类型化证据与精确失效

G2/G3 证据使用 [state.schema.json](references/state.schema.json) 的类型化结构，并通过 `input_refs`、`claim_refs` 和 `binding_hash` 绑定实际输入。`evidence.required=true` 表示接受该 atom 效果前需要合适证据，不表示 G1 每轮必须在状态中生成一条记录。

工件刷新只把精确引用旧 `(path, sha256)` identity 的证据置为 stale。working identity 变化不自动改变组件或项目状态；milestone、frozen、final identity 变化时，才使相应 owner 和真实下游消费者失效。下游论文修改不得反向使数据、模型、代码或 E1–E4 证据失效。

重新验证只补当前 checkpoint 所需的 stale/missing 证据；未引用变化 identity 的既有 pass 保持有效，不按组件 epoch 重做全部历史门。

每条 [state-machine.json](references/state-machine.json) 生命周期迁移统一由 `RT.STATE.TRANSITION` 承载，使用 `G2_CHECKPOINT + promote + state_effect`；启动执行时封存 exact state effect，`state_manager.py transition` 必须携带对应 execution id。状态机中的每条边都必须通过静态全覆盖检查，并至少有一条临时真实项目的端到端迁移场景。兼容实现变更不是迁移边：它由 `RT.PROJECT.COMPATIBLE_CHANGE` 的 validity overlay 保持原状态，并以多组件 effect closure 一次原位对账；不得为了复用迁移工具而伪造 S7→S2 或失败证据。

G2/G3 启动执行时把完整 ChangeSet 封存在 execution ledger。`register-artifact`、`refresh-artifact` 和 `transition` 必须绑定同一条 open execution；identity 路径不在封存 ChangeSet 中时，在写状态前拒绝。无法完成的 open execution 使用 `void-execution` 审计式终止，保留 plan hash、开始 revision、failure code 和原因；不得改写旧计划或伪造结束回执。

## 领域方法按需读取

route 的 `context_refs` 只返回当前步骤需要的短方法路由；方法路由再选完整能力包。不要为了完整性一次加载所有资料，也不要只读路由而跳过它选中的能力包。

- 项目范围与恢复：[project-method-notes.md](references/project-method-notes.md)
- 数据：[data-method-notes.md](references/data-method-notes.md)
- 建模：[modeling-method-notes.md](references/modeling-method-notes.md)
- 验证：[verification-method-notes.md](references/verification-method-notes.md)
- 论文：[manuscript-method-notes.md](references/manuscript-method-notes.md)
- 图表：[visual-method-notes.md](references/visual-method-notes.md)
- 来源与证据：[evidence-method-notes.md](references/evidence-method-notes.md)
- Skill 审计与维护（仅在明确授权后）：[maintenance-method-notes.md](references/maintenance-method-notes.md)

每个被选中的能力包都应完整读取；若同一步命中多个领域，按真实依赖顺序读取，不用一个领域的包替代另一个领域。领域质量标准仍由命中的 atom 完整执行。编译成功、退出码为零、标题齐全、视觉相似或固定短语都不能单独证明正确；只声称实际检查过的 effect、scope、identity 和 tier。

## Skill 维护与发布

只有用户明确要求修改 Skill 时才进入 `skill_maintenance`。规则语义变更、触发/路由变更和运行时治理变更分别分析；不得把触发修复伪装成规则弱化，也不得把一次真实失败推广成无关任务的通用硬步骤。

`validate_release.py` 和 `freeze_release.py` 是 Skill 包维护/发布工具，不是数学建模项目的恢复、续作、暂停或收尾自检。普通 project route 永不运行它们，也不以项目里的 `skills/` 副本为对象扫描缓存。

V16 维护继续使用隔离 base→candidate。正式发布仍只有三个控制面驱动：包可加载、跨契约与历史能力闭合、临时真实项目场景。状态迁移总覆盖、平台准入、identity 前置拒绝、执行 void、Skill 授权边界、R1 新窗口、R2 隔离、精确失效、兼容变更原子性以及本版修复必须由契约或真实场景直接证明。能力包覆盖与迁移封印只在 Skill 维护和发布时检查，不下沉为普通项目门禁。测试以独立可观察结果为准，不以断言数、关键词存在、逐 atom 同源 mutation 或脚本彼此调用形成的自证循环作为质量指标。

当前维护入口是完整用户请求形成的多步骤 semantic plan、规范 owner 的人工影响审计，以及发布计划中的结构化兼容性处置。V10 单 operation 变更链、固定旧版本 oracle 和失效 legacy harness 已退役，不再作为可执行兼容接口随包发布；其来源、取舍和替代证据仅保存在 `references/preservation/` 与 `references/migration/`。不得为了兼容旧工具恢复一次一文件、自动重建同源 oracle 或全量 legacy gate。

发布前运行 [release-policy.json](references/release-policy.json) 定义的精简 gate；任何已确认能力被合并或退役，都必须有明确 disposition、替代 owner 和独立结果证据。候选不覆盖 V14 或更早版本；只有用户明确批准冻结后，才生成 manifest 并复制到独立发布目录。安装或覆盖正在使用的 Skill 仍需另行明确授权。

## 关键契约

- 运行时分级：[runtime-policy.json](references/runtime-policy.json)
- 内部语义计划：[semantic-plan.schema.json](references/semantic-plan.schema.json)
- 轻量 route 与实际事件：[route-contract.json](references/route-contract.json)
- 危险命令的同进程执行绑定：[run_authorized_action.py](scripts/run_authorized_action.py)
- 规范所有权：[ownership-contract.json](references/ownership-contract.json)
- atom Schema：[rule-atom.schema.json](references/rule-atom.schema.json)
- 状态与迁移：[state.schema.json](references/state.schema.json)、[state-machine.json](references/state-machine.json)
- 工件：[artifact-contract.json](references/artifact-contract.json)
- 统一项目平台：[project-platform-contract.json](references/project-platform-contract.json)
- 精简发布策略：[release-policy.json](references/release-policy.json)
- 能力包映射与无损披露：[capability-packet-registry.json](references/capability-packet-registry.json)
- G2/G3 回执：[receipt.schema.json](references/receipt.schema.json)
- 发布 manifest：[release-manifest.schema.json](references/release-manifest.schema.json)
