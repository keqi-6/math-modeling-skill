# 定向恢复、控制重建与项目交接

适用于新窗口接手、上下文压缩后续作、登记 identity 变化、状态缺失/损坏，以及用户要求暂停或交接。恢复层只决定为重新取得可信上下文必须读取多少材料；项目变化的失效传播、修改与验收仍由独立 ChangeSet 负责。R0/R1 不无因遍历全项目，命中 R2 时则必须完成全项目逐对象读取。

## 规范边界

本包不选择或改写恢复等级。正式 owner 是：

- `rules/governance.json` 中 `REC-R0-001`、`REC-R1-001`、`REC-R2-001` 和命中的状态/权限 atoms；
- `rules/evidence_delivery.json` 中 `DEL-HANDOFF-001`；
- `SKILL.md`、`references/runtime-policy.json`：窗口语义、R2 隔离边界、G1 pause 和比例性；
- `references/state.schema.json`、`references/state-machine.json`：状态 shape 与合法迁移；
- `references/recovery-receipt.schema.json`：R1/R2 单 episode 合并读取回执 shape；
- `scripts/assess_recovery.py`、`scripts/recovery_v14.py`、`scripts/state_manager.py`：当前解释器实现。

若 atom 的非规范 gloss 与 V14 控制器对允许动作、窗口或证据持久化的解释不同，以 `SKILL.md`、runtime policy 和机器契约为准。本包不授予求解、执行型验证、重算或晋级权限。

## 先判断当前动作是否需要恢复

只有当前动作依赖既有权威状态或登记 identity、用户明确要求续作/恢复、发现受保护 identity 变化，或声明的 G3 范围需要检查时，才进入恢复。

以下情况本身不要求恢复：

- G0 回答、解释、规划和无状态依赖的只读检查；
- 普通 G1 编辑只依赖用户本轮提供的当前文件；
- 未登记 working 文件、无关 dirty 文件或普通新增文件；
- 仅进入某阶段、做 S6 readiness、暂停或最终交付这个词本身。

先记录当前步骤的 `window_context` 和状态依赖。新窗口、未知窗口、上下文压缩/恢复或无法证明同一未中断会话时不能采用 R0；这只设置最低候选等级，不能自动证明 R1。随后仍须检查 baseline、变化归属和消费者闭包；不能证明时直接进入 R2。

## 三级分流

### R0：同窗口直接继续

仅在同一未中断窗口、权威状态结构有效、下一动作明确、当前 checkpoint identity 有效、此后相关变化全部属于已经记录的本窗口 ChangeSet、失效传播已经闭合且没有未解释外部变化时使用。R0 允许存在已经解释的 workspace delta；读取权威状态和当前动作声明的直接输入即可，不建立 recovery manifest 或 receipt，不遍历全项目，也不重放历史验证。

若出现未解释差异、窗口无法证明或 state/plan 不一致，停止采用 R0，重新评估 R1/R2。

### R1：新窗口或可定位变化的定向恢复

只在三个资格同时成立时使用：存在可信、当前且覆盖完整的全项目 baseline；每个相关新增、修改或删除都能定位到语义 owner；当前依赖图能证明完整传递消费者闭包。新/未知窗口只是排除 R0，不是这里的第四种资格。R1 既不是哈希标签，也不是全量复读；读取集合只包含当前步骤要求的权威事实、受影响闭包及其声明输入。

### R2：控制面缺失或冲突的隔离恢复

用户明确要求全量恢复时无条件使用。当前动作依赖的权威状态或项目 identity 缺失、损坏或冲突，baseline 缺失、过期或覆盖不全，相关变化无法定位，完整传递消费者闭包不能证明，或 R1 阅读中发现证明范围之外的相关对象时也使用。G3、未登记文件、局部工作完成、普通 dirty 工作区、缓存或无关新增文件不自动构成 R2。

判定固定按 `不适用 → 显式/结构性 R2 → 合格 R0 → 合格 R1 → R2` 执行。不能先把新窗口或任意变化判成 R1，再在 R1 中事后补齐它本应预先具备的资格。

## baseline 的资格

baseline 是一个可信时刻的全项目快照索引。它保留项目根 fingerprint、覆盖根、完整 inventory manifest、文件 identity、状态 revision、组件依赖图 identity、工件 registry identity 和建立它的 closed recovery 或可信同窗 execution。它不是项目副本，也不是 HANDOFF、旧结论摘要或几个 watch root 的散列集合。

状态中的 `workspace_baseline` 继续保持 path→`{sha256,size}` map；资格与来源单独保存在可选的 `workspace_baseline_meta`。旧 state 可以在没有 meta 时加载，但 assessor 必须以 `baseline_metadata_missing` 判为 R2。meta 一旦存在，`root_fingerprint`、`coverage_roots`、`coverage_complete`、`manifest_sha256`、`inventory_policy_sha256`、`captured_revision`、`component_graph_sha256`、`artifact_registry_sha256`、`established_by`、`file_count`、`unresolved` 和 `continuity_change_set` 全部必需。

只有 `coverage_roots=["."]`、coverage complete、manifest 与当前 root/identity policy 可核、unresolved 为空，且来源与 revision 可追溯时，baseline 才能支持 R1。旧式 path→hash map 仍可帮助比较，但缺少合格 meta 时只能作导航并触发 R2。缓存、控制器内部文件和其他非语义对象可以按 inventory policy 分类排除；排除必须被表示，不能靠未扫描目录实现。

## R1 的完整操作闭包

按同一 plan、step 和 scope 完成：

1. 明确当前动作、组件、窗口和所依赖的正式 identity；
2. 先机器核对 baseline meta、实际 workspace delta、变化归属和完整传递消费者闭包；三项资格任何一项未知或失败，不开启一个伪 R1，而是直接开启 R2；
3. 取得变化路径、owner、受影响组件和基础必读集，在阅读前开启一个 recovery，封存精确必读路径及 revision；
4. 对每个条目执行与语义角色相称的读取，而不只比较哈希；
5. 把 changed、missing、unreadable 和 consistent 分开记录；
6. 从变化 owner 沿已经证明当前的依赖图复核全部传递消费者、当前证据和下一动作；恢复只复核，不在这里执行组件失效；
7. 如果读取暴露未纳入 manifest 的相关路径、无法解释的变化或闭包外消费者，保持同一 recovery id，将最终等级升级为 R2，并复用 identity 未变的已读条目；
8. 按当前 schema 为整个 episode 提交一份合并读取回执和 `ready/blocked` 结论，未读条目不能伪装为 consistent；
9. 关闭 recovery 前重新确认复核后 identity 未变化；
10. 后续 checkpoint/execution 绑定同一 recovery id、最终等级、窗口、assessment 和唯一回执；
11. baseline 只吸收该回执实际覆盖、且 revision 仍精确一致的变化路径。

同一 episode 的 state record 使用 `initial_recovery_level`、当前 `recovery_level`、nullable `escalated_from`、`escalation_history`、nullable `decision_id` 以及 R2 的 `full_manifest_path` / `full_manifest_sha256` / `full_manifest_counts`。R1→R2 的 history item 固定记录 `from_level`、`to_level`、`reason`、`at_revision` 与 `at`，不新建第二个 recovery id。

基础必读集按当前步骤裁剪，通常从以下角色中选择：

- 权威状态；
- 官方题面、附件和未登记但确属官方的输入；
- 目标、上游和受影响组件的 milestone/frozen/final 规划、流程与证据；
- 当前正式 identity 的身份与验证摘要；
- 与当前闭包有关的 workspace delta 和证据源。

题面与冻结流程做内容或结构化语义读取；图像或渲染件在其含义相关时视觉复核；其他正式 identity 至少读取身份与验证摘要。`hash_only`、文件名存在或旧 handoff 的“已验证”都不能完成 R1。

R1 不读取无依赖的项目区域。消费者图不完整、依赖 identity 过期或必须边读边发现闭包时，说明“有界”尚未证明，必须进入 R2；不能让 R1 事后回填它自己的准入条件。

## R2 中可以做什么

R2 是隔离控制面，不是“重跑一切”的授权。按一个 episode 完成：

1. 从项目根重新枚举 live inventory；所有当前文件必须在 full manifest 中出现，缓存、控制器内部项、重复件和未知件也要有分类，不能靠 watch roots 静默消失；
2. 把唯一文本、代码和配置从头读到 EOF，记录完整 identity 与读取结论；
3. Office 与 PDF 使用原生/结构化提取并在版面或图形语义相关时做视觉检查；图像做视觉检查；数据集和其他二进制使用与格式相称的结构、元数据、内容与可读性检查；
4. 内容重复件可以按 hash 指向一个已经完整读取的 canonical item，不重复消耗上下文；未知类型必须先检查再分类；
5. 从全读材料重建组件、依赖、identity 和 provenance，复用仍与当前 identity 一致的证据；
6. 如实登记 missing/stale/authorization gap 和下一合法动作；这些项目 gap 不得伪装成读取遗漏；
7. 复核 manifest 后的 live inventory 未变化，封存同一 recovery id 的唯一合并回执。

full manifest 是恢复过程的外部证据，不得写入被它自己枚举的项目根造成自指变化；状态只保存其 project-external path、hash 和固定计数。R2 的逐对象回执可以保存在 full manifest 中，顶层 recovery receipt 不要求复制全部明细。

R2 打开时不执行模型、solver、执行型 verifier、既有结果重算、论文实质改写、交付构建或状态晋级。旧版“rebuild commands”在 V14 中只指身份、结构和一致性检查，不等于运行项目代码。

R2 不能因为控制状态刚恢复为结构有效就提前关闭。只有 inventory complete、canonical item complete、所有当前对象 classified、unresolved count 为零且唯一回执封存后，才能结束为：

- `closed_ready`：规定读取全部完成，当前动作没有恢复所发现的阻断；
- `closed_blocked`：规定读取同样全部完成，但有明确的 stale/missing/authorization gap，当前业务动作仍被阻断。

两种闭合都可以在同一用户轮次结束 R2 隔离，不要求第二条“继续”口令。仍需重算的证据作为 `closed_blocked` gap 保留；关闭隔离后，只有原请求已授权相应 runtime action 才单独执行。全读完成与项目已经验证通过是两个不同结论。

## 并行窗口的写面

用户要求多个窗口并行时，先把共享只读前提、每个窗口的精确写路径、冻结保护面、依赖和停止条件写成有界 scope；该说明是授权导航，不替代权威状态。写面应互斥，同一路径不能由两个活动窗口同时修改；`.modeling/state.json` 等权威控制文件在并行期只指定一个 writer，其他窗口只读并把需要的状态变化交给该 writer 归并。唯一 state writer 不自动获得其他窗口的领域写权限。

公共设计、题面和冻结组件可以被各窗口只读复用。某窗口只做已经关闭组件的文字/讲解稿同步时，不得顺便修改其模型、代码、结果或正式 identity；需要扩面就先报告影响并重新划界。发现另一个窗口正在写同一路径、权威状态出现无法归属的并发变化，或本步必须触及冻结保护面时，只停止冲突步骤；不让一个窗口的冲突阻断其他独立窗口，也不靠 mtime 猜哪份写入应获胜。

## 暂停与交接

“今天先到这”“暂停并记下后续”按 G1 project pause 处理，只同步已经发生的控制状态变化：

- 本轮真实完成和未完成的边界；
- open decisions 及各自需要谁决定；
- 每个活动组件的 next legal action 和 blocker；
- 本轮已观察到的登记 identity 变化；
- 最近一次实际验证及其精确范围，不把历史或局部 pass 扩大。

这些事实写入权威状态已有字段；进入可能中断的长调用或上下文边界前，可在同一状态文件中做一次控制检查点。不默认生成 `HANDOFF.md`、recovery manifest、全工作区清单、receipt 或第二份状态文件。

V16 formal execution 另外绑定 `recovery_decision_id`、执行前后 workspace manifest hash、`observed_changed_paths`、`change_set_provenance_complete` 和结束时的 `execution_receipt_sha256`，使下一窗口可以验证实际 delta 是否仍属于声明的 ChangeSet；这些 provenance 字段不改变本节“普通自然暂停不生成额外文件”的原则。

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
| 新窗口因 state 哈希一致而使用 R0 | 排除 R0，再检查 R1 三项资格；合格才 R1，否则 R2 |
| baseline 缺失或只覆盖 watch roots 仍使用 R1 | 将旧 baseline 降为线索，进入 R2 建立完整快照 |
| R1 只读变化文件 | 补变化 owner、全部传递消费者及其声明输入 |
| R1 边读边补消费者图并宣称范围有界 | 保持同一 recovery id 升级 R2，不重开逐题回执 |
| 一个局部变化触发全项目遍历 | 以依赖图裁剪受影响闭包，删除无因读取 |
| 用哈希、mtime 或文件存在证明内容已读 | 采用内容、结构化、视觉或 identity+验证摘要读取 |
| 复核后文件又变化仍消费旧回执 | 阻断，重新评估并生成新的精确 recovery |
| baseline 吞入整个 dirty 工作区 | 只合并回执覆盖且 revision 未变的路径 |
| 把 G3 或 pause 自动升级成 R2 | 回到真实触发条件和声明范围重新分类 |
| R2 中运行 solver/verifier“重建证据” | 记录 gap，先重建控制面；关闭隔离后再按授权执行 |
| R2 只读登记 identity 或状态重建后立即关闭 | 完成全项目 manifest、逐对象规定读取和唯一合并回执 |
| 每个问题、文件或门禁各建 recovery/receipt | 收敛为当前跨组件 episode 的一个 recovery id 和一份回执 |
| 旧 HANDOFF 叙述覆盖实际文件 | 把它降为线索，从权威输入和 identity 重建事实 |
| 暂停生成多份同步文件 | 收敛到权威状态；导航仅在已有需求下更新 |
| 把局部 pass 写成项目已恢复/已验证 | 将声称缩到实际复核的 component、identity 和 tier |
| recovery id 被跨 plan/step 复用 | 作废旧绑定，为当前步骤重新开启恢复 |

## 来源保留说明

本包保留 V1–V7 经 V8 `14-session-handoff.md` 形成的“叙述非权威、从最早失效层继续、交接记录真实暂停点”原则，并恢复 V7/V8 在真正命中 R2 后的全项目逐对象读取合同；保留 V9/V10 对“变化不可定位或 baseline 不可信则 R2”的边界；以 `REC-R0-001`、`REC-R1-001`、`REC-R2-001`、`DEL-HANDOFF-001` 为规范锚点。V11–V13 的状态、ChangeSet、权限和执行绑定继续有效，V14 的读取回执被收敛为当前 episode 的唯一合并回执。仍明确废弃每次新窗口或里程碑无条件全量复读、R2 内执行型重算、固定 HANDOFF 文件和逐步继续口令；恢复 R2 全读不等于恢复这些旧门禁。
