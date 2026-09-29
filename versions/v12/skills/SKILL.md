---
name: mathematical-modeling-project-controller
description: 端到端管理数学建模竞赛或研究项目，覆盖范围、文献证据、数据、建模、实现、验证、论文、图表、交付、接手恢复，以及用户明确授权时的 Skill 规则维护。用于完整项目、现有项目续作或有项目语境的局部任务；不用于孤立普通数学题、无项目语境的通用排版，或未获授权的 Skill 自修改。
metadata:
  version: "12.0.0"
  release: "candidate"
---

# 数学建模项目控制器 V12

## 目标与不变量

V12 保留 V11 的领域规则、规范强度、唯一 owner、类型化状态和风险分层，修复两个系统性缺口：统一项目平台被“按需创建”误删，以及发布门以测试数量代替真实能力验证。`rules/*.json` 继续继承冻结语义；本次主版本升级不删除、不弱化无关规则，也不把 `MUST` 改成建议。

必须分开处理五个维度：规则强度、实际适用性、检查时机、证据是否持久化、变化的失效范围。`MUST` 只表示规则实际适用时，不满足就不能接受相应结果；它不表示每次请求都要激活、写回执、重建证据或使整个组件失效。该运行时解释由 [runtime-policy.json](references/runtime-policy.json) 拥有。

[ownership-contract.json](references/ownership-contract.json) 继续保证每个规范事实只有一个 owner。Agent 和脚本不得复制或改写规则语义；脚本只验证内部计划、状态和证据结构。

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

## 规则只由真实动作触发

规则进入某一步的检查集合，必须同时满足：

1. route selector 与该步匹配；
2. 对象、组件类型和真实状态在 scope 内；
3. 该步实际发生的 event 与 trigger 相交；
4. predicate 与 runtime exception 的事实成立。

不得为每个请求合成全局事件，不得为每个写请求合成所有可写事件，也不得把某 route 可能执行的全部动作提前广播。`manuscript_audit`、`writing_profile_apply`、`state_transition`、`artifact_register`、`recovery_assessment` 等事件只有在该动作真实发生时才能出现。

冻结 V10 atom 的少数 event 名称兼作旧版语义 token。V12 只可把本步明确声明、实际写入或实际审计覆盖的 facet 正规化成对应 token，并记录来源；不得由 facet 直接点名规则，也不得借正规化广播未覆盖的动作。最终仍由 atom 自身的 route、scope、trigger 和 predicate 决定适用性。

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

统一项目平台是逻辑契约，不是预生成目录树。新项目的每项工件都必须先归入 [project-platform-contract.json](references/project-platform-contract.json) 的唯一 `platform_role`，其路径与 class 必须匹配该角色；只有工件通过准入且确实要创建时，才建立所需父目录。不得把“懒创建”解释为自由命名或自由放置。

既有项目先识别现状，不自动移动、改名或重排用户文件；既有非规范路径在其角色与位置不变时可继续读取。此后新增文件使用规范路径。需要向非规范路径新增文件或整体迁移布局时，将其作为独立变更提交用户批准，不借初始化或普通实现暗中改造。

`.modeling/state.json` 只保存需要跨轮次延续的当前事实、正式 identity、决定和 checkpoint 证据。日常 G1 工作不因为缺少状态而失败，也不为了留下过程痕迹频繁改写状态。

恢复仅在动作依赖既有权威状态、用户明确要求续作/恢复、检测到登记的受保护 identity 变化，或 G3 交付检查时运行：

```bash
python3 -B scripts/assess_recovery.py --project-root "<root>" --gate G1
```

- `R0_CONTINUE`：所依赖的登记 identity 当前；只允许同一未中断会话内的连续工作。
- `R1_TARGETED`：变化可归属，只恢复精确引用它的证据和真实下游消费者；跨窗口/新会话/上下文恢复至少按此级别。
- `R2_FULL`：当前动作依赖的权威状态缺失或损坏、关键 identity 冲突无法归属，或用户明确要求全量恢复。

跨窗口协作、新会话、上下文压缩/恢复或无法证明同一会话时，Agent 不能因为状态文件“看起来一致”就采用 R0。含 `recovery_assessment` 的 semantic plan 必须声明 `window_context`（`same_window`/`new_window`/`unknown`）；缺省按 `new_window` 处理，最低为 `R1_TARGETED`，只有 `same_window` 才允许 R0。

未登记 working 文件、无关 dirty 文件、普通新增文件、进入 S6、完成局部工作或仅仅进入 G3 都不能单独触发 R2。G1/G2 默认只核对已登记的 milestone、frozen、final identity；G3 对声明的交付范围做完整性审计，并依据实际 identity 状态得到 R0/R1/R2，而不是把 tier 本身等同于 R2，也不把整个工作区当成洁净门。

普通文件由 ChangeSet 批量管理。只有 milestone、frozen、final 工件需要正式准入和登记。新登记工件建立 identity，但不使生产者或消费者失效；已有工件 identity 变化时才按精确绑定传播。

R2 是恢复控制面和真实证据缺口的隔离态，不是重跑项目的许可。R2 中可以读取、枚举、哈希、解析和比较已有文件，重建组件/依赖/identity/provenance 元数据，复用仍一致的证据，并如实登记 missing/stale gap；只能写 `.modeling/state.json` 与 `.modeling/recovery/` 下的恢复材料。冻结 atom 所说的 evidence rebuild 或 rebuild commands 在这里指上述身份与一致性检查，不等于运行 solver 或 verifier。R2 打开时禁止模型实现与执行、执行型验证、论文实质写入、交付构建和状态晋级。

控制状态重建为结构有效的 V12 state（继续兼容 V11 schema）后，在同一用户轮次内重新解析原计划即可关闭 R2；不要求用户再发“关闭恢复”或“继续”口令。确有 stale/missing 证据需要重算时，先如实记录缺口，R2 关闭后再把重算作为原请求明确授权的独立 runtime action 执行。

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

## 领域方法按需读取

route 只返回当前步骤需要的 `context_refs`。不要为了完整性一次加载所有方法资料。

- 项目范围与恢复：[project-method-notes.md](references/project-method-notes.md)
- 数据：[data-method-notes.md](references/data-method-notes.md)
- 建模：[modeling-method-notes.md](references/modeling-method-notes.md)
- 验证：[verification-method-notes.md](references/verification-method-notes.md)
- 论文：[manuscript-method-notes.md](references/manuscript-method-notes.md)
- 图表：[visual-method-notes.md](references/visual-method-notes.md)
- 来源与证据：[evidence-method-notes.md](references/evidence-method-notes.md)

领域质量标准仍由命中的 atom 完整执行。编译成功、退出码为零、标题齐全、视觉相似或固定短语都不能单独证明正确；只声称实际检查过的 effect、scope、identity 和 tier。

## Skill 维护与发布

只有用户明确要求修改 Skill 时才进入 `skill_maintenance`。规则语义变更、触发/路由变更和运行时治理变更分别分析；不得把触发修复伪装成规则弱化，也不得把一次真实失败推广成无关任务的通用硬步骤。

`validate_release.py` 和 `freeze_release.py` 是 Skill 包维护/发布工具，不是数学建模项目的恢复、续作、暂停或收尾自检。普通 project route 永不运行它们，也不以项目里的 `skills/` 副本为对象扫描缓存。

V12 维护继续使用隔离 base→candidate。活跃发布门只包含四类可解释检查：包可加载、契约相互一致、关键结果在临时真实项目中成立、版本迁移没有丢失已确认能力。测试以独立可观察结果为准，不以断言数、关键词存在、全规则逐项 mutation 或脚本彼此调用形成的自证循环作为质量指标。历史大型测试可以按故障调查需要单独运行，但不再常驻发布主链。

V10 的单 operation `change-envelope` 与旧 `run_*tests.py`、`quick_validate.py`、`validate_contracts.py` 仅作为兼容、诊断和历史回归材料保留，不是 V12 活跃发布接口，也不得据此把一次 Skill 维护限制成一次只改一个文件。V12 活跃入口仍是完整用户请求形成的多步骤 semantic plan；发布证据由 [release-policy.json](references/release-policy.json) 定义。

发布前运行精简 gate；任何已确认能力从活跃规范降为背景资料，都必须有明确迁移判定和独立结果测试。V12 candidate 不覆盖 V11/V10/V9；只有用户明确批准冻结和安装后，才生成 V12 manifest 并复制到独立安装目录。

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
- G2/G3 回执：[receipt.schema.json](references/receipt.schema.json)
- V10 规则变更兼容格式（非 V12 活跃入口）：[change-envelope.schema.json](references/change-envelope.schema.json)
- 发布 manifest：[release-manifest.schema.json](references/release-manifest.schema.json)
