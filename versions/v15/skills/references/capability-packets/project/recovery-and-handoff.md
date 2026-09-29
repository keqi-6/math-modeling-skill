# 定向恢复、控制重建与项目交接

适用于新窗口接手、上下文压缩后续作、登记 identity 变化、状态缺失/损坏，以及用户要求暂停或交接。恢复的目标是取得当前动作所需的可信事实，不是把全项目一次塞入上下文。

## 规范边界

本包不选择或改写恢复等级。正式 owner 是：

- `rules/governance.json` 中 `REC-R0-001`、`REC-R1-001`、`REC-R2-001` 和命中的状态/权限 atoms；
- `rules/evidence_delivery.json` 中 `DEL-HANDOFF-001`；
- `SKILL.md`、`references/runtime-policy.json`：窗口语义、R2 隔离边界、G1 pause 和比例性；
- `references/state.schema.json`、`references/state-machine.json`：状态 shape 与合法迁移；
- `references/recovery-receipt.schema.json`：R1 读取回执 shape；
- `scripts/assess_recovery.py`、`scripts/recovery_v14.py`、`scripts/state_manager.py`：当前解释器实现。

若 atom 的非规范 gloss 与 V14 控制器对允许动作、窗口或证据持久化的解释不同，以 `SKILL.md`、runtime policy 和机器契约为准。本包不授予求解、执行型验证、重算或晋级权限。

## 先判断当前动作是否需要恢复

只有当前动作依赖既有权威状态或登记 identity、用户明确要求续作/恢复、发现受保护 identity 变化，或声明的 G3 范围需要检查时，才进入恢复。

以下情况本身不要求恢复：

- G0 回答、解释、规划和无状态依赖的只读检查；
- 普通 G1 编辑只依赖用户本轮提供的当前文件；
- 未登记 working 文件、无关 dirty 文件或普通新增文件；
- 仅进入某阶段、做 S6 readiness、暂停或最终交付这个词本身。

先记录当前步骤的 `window_context` 和状态依赖。新窗口、未知窗口、上下文压缩/恢复或无法证明同一未中断会话时，最低按 R1；只有同一未中断窗口才有资格评估 R0。

## 三级分流

### R0：同窗口直接继续

仅在同一未中断窗口、权威状态结构有效、下一动作明确、当前依赖的登记正式 identity 一致、相关差异为空时使用。读取权威状态和当前动作声明的直接输入即可；不建立 recovery manifest，不遍历全项目，也不重放历史验证。

若出现未解释差异、窗口无法证明或 state/plan 不一致，停止采用 R0，重新评估 R1/R2。

### R1：新窗口或可定位变化的定向恢复

用于新/未知窗口，或状态有效且变化能归属到 owner 和消费者的情况。它既不是哈希标签，也不是全量复读。读取集合只包含当前步骤要求的权威事实、受影响闭包及其声明输入。

### R2：控制面缺失或冲突的隔离恢复

只在当前动作依赖的权威状态缺失/损坏、重要登记 identity 冲突无法归属，或用户明确要求全量恢复时使用。G3、未登记文件、局部工作完成或普通 dirty 工作区不自动构成 R2。

## R1 的完整操作闭包

按同一 plan、step 和 scope 完成：

1. 明确当前动作、组件、窗口和所依赖的正式 identity；
2. 运行恢复评估，取得变化路径、owner、受影响组件和基础必读集；
3. 在阅读前开启同一 recovery，封存精确必读路径及 revision；
4. 对每个条目执行与语义角色相称的读取，而不只比较哈希；
5. 把 changed、missing、unreadable 和 consistent 分开记录；
6. 从变化 owner 沿声明依赖扩展到全部传递消费者，逐项复核其当前证据和下一动作；
7. 按当前 schema 提交读取回执和 `ready/blocked` 结论，未读条目不能伪装为 consistent；
8. 关闭 recovery 前重新确认复核后 identity 未变化；
9. 后续 checkpoint/execution 绑定同一 recovery id、窗口、assessment 和回执；
10. baseline 只吸收该回执实际覆盖、且 revision 仍精确一致的变化路径。

基础必读集按当前步骤裁剪，通常从以下角色中选择：

- 权威状态；
- 官方题面、附件和未登记但确属官方的输入；
- 目标、上游和受影响组件的 milestone/frozen/final 规划、流程与证据；
- 当前正式 identity 的身份与验证摘要；
- 与当前闭包有关的 workspace delta 和证据源。

题面与冻结流程做内容或结构化语义读取；图像或渲染件在其含义相关时视觉复核；其他正式 identity 至少读取身份与验证摘要。`hash_only`、文件名存在或旧 handoff 的“已验证”都不能完成 R1。

R1 不读取无依赖的项目区域。某局部变化的消费者图不完整时，先尝试从生产者、实际读写和主张引用补图；只有重要冲突仍无法归属时才考虑 R2。

## R2 中可以做什么

R2 是隔离控制面，不是“重跑一切”的授权。安全工作限于：

- 枚举、读取、哈希、解析、视觉检查和比较已有材料；
- 从权威输入与实际文件重建组件、依赖、identity 和 provenance 元数据；
- 复用仍与当前 identity 一致的证据；
- 如实登记 missing/stale/unreadable gap 和下一合法动作；
- 只在恢复控制位置写结构化恢复材料和权威状态。

R2 打开时不执行模型、solver、执行型 verifier、既有结果重算、论文实质改写、交付构建或状态晋级。旧版“rebuild commands”在 V14 中只指身份、结构和一致性检查，不等于运行项目代码。

当控制状态已重建为结构有效且冲突得到可归属结论时，在同一用户轮次重新解析原计划。仍需重算的证据作为明确 gap 保留；关闭隔离后，只有原请求已授权相应 runtime action 才单独执行。不能把有 gap 的恢复声称为完整通过。

## 暂停与交接

“今天先到这”“暂停并记下后续”按 G1 project pause 处理，只同步已经发生的控制状态变化：

- 本轮真实完成和未完成的边界；
- open decisions 及各自需要谁决定；
- 每个活动组件的 next legal action 和 blocker；
- 本轮已观察到的登记 identity 变化；
- 最近一次实际验证及其精确范围，不把历史或局部 pass 扩大。

这些事实写入权威状态已有字段；进入可能中断的长调用或上下文边界前，可在同一状态文件中做一次控制检查点。不默认生成 `HANDOFF.md`、recovery manifest、全工作区清单、receipt 或第二份状态文件。

项目已有导航文件且用户要求维护时，可以更新为指向权威状态和真实证据的摘要；它永远不覆盖状态、题面、代码、结果或验证。摘要冲突时沿证据链定位最早错误层，而不是选择“看起来最新”的文字。

pause/handoff 不派生 checkpoint、S6 close、final delivery、全项目审计、Skill 自检、solver、verifier 或重算权限。若同一请求明确要求先关闭一个 G2 节点再暂停，按依赖计划完成两个步骤，暂停步不扩大组件范围。

## 人工复核点

只在以下情况请求决定或扩大授权：

- 两个权威候选无法判断哪个 identity 当前；
- 关键官方输入缺失、损坏或来源身份不明；
- 恢复将改变冻结决定、正式 scope 或消费者关系；
- gap 的补算需要运行原请求未授权的 solver/verifier/recompute；
- 需要把非规范导航文件迁移为当前机器状态；
- baseline 合并范围存在未复核路径或 revision 已变化。

状态一致且同一请求已授权的恢复闭合，不要求用户再发“继续”标准口令。

## 常见失败与修复

| 失败 | 修复 |
|---|---|
| 新窗口因 state 哈希一致而使用 R0 | 改为 R1，声明窗口并完成语义读取回执 |
| R1 只读变化文件 | 补变化 owner、全部传递消费者及其声明输入 |
| 一个局部变化触发全项目遍历 | 以依赖图裁剪受影响闭包，删除无因读取 |
| 用哈希、mtime 或文件存在证明内容已读 | 采用内容、结构化、视觉或 identity+验证摘要读取 |
| 复核后文件又变化仍消费旧回执 | 阻断，重新评估并生成新的精确 recovery |
| baseline 吞入整个 dirty 工作区 | 只合并回执覆盖且 revision 未变的路径 |
| 把 G3 或 pause 自动升级成 R2 | 回到真实触发条件和声明范围重新分类 |
| R2 中运行 solver/verifier“重建证据” | 记录 gap，先重建控制面；关闭隔离后再按授权执行 |
| 旧 HANDOFF 叙述覆盖实际文件 | 把它降为线索，从权威输入和 identity 重建事实 |
| 暂停生成多份同步文件 | 收敛到权威状态；导航仅在已有需求下更新 |
| 把局部 pass 写成项目已恢复/已验证 | 将声称缩到实际复核的 component、identity 和 tier |
| recovery id 被跨 plan/step 复用 | 作废旧绑定，为当前步骤重新开启恢复 |

## 来源保留说明

本包保留 V1–V7 经 V8 `14-session-handoff.md` 形成的“叙述非权威、从最早失效层继续、交接记录真实暂停点”原则；保留 V9 `recovery-governance.md` 的 R0/R1/R2 分工与暂停最小状态；以 V10 的 `REC-R0-001`、`REC-R1-001`、`REC-R2-001`、`DEL-HANDOFF-001` atoms 为规范锚点。V11–V13 的状态、ChangeSet、权限和执行绑定继续有效，V14 进一步要求新窗口最低 R1、逐项语义读取回执、同 plan/step/scope 消费以及 baseline 精确覆盖。已明确废弃 V8/V9 的无条件全量启动复读、里程碑自动 R2、R2 内执行型重算、固定 HANDOFF 文件和逐步继续口令。
