# V16 R0/R1/R2 恢复层重构决议

日期：2026-08-28  
状态：用户已批准、V16 candidate 实施中  
性质：历史与设计取舍记录；不是运行时规范 owner

## 授权与问题陈述

用户先明确纠正了恢复方向：

> “r2显式触发是在我要求下触发的，本来也应该全读。现在就是本该全读的地方它套r1所以不全读”

在审阅 R0/R1/R2 的新设计后，用户进一步明确授权：

> “确认批准你的r0r1r2设计，去接着修”

因此本次不是把显式 R2 缩小，也不是降低全量读取标准。要修复的是两个已经在真实项目中出现的断点：本应因 baseline 或影响闭包不可信而进入 R2 的情况被兜底到 R1；显式 R2 虽被分类器选中，顶层 barrier、receipt 和状态记录却没有共同保证全项目全读。

## 历史依据

- V1–V5 没有分级，新窗口采用全项目事实重建；它保留了摘要非权威、原生载体检查和重复内容 hash 去重，但日常成本过高。
- V6–V8 建立 R0/R1/R2。R0 是同窗小增量，R1 依赖可信 baseline 的定向恢复，R2 在来源/baseline/归属不可信或显式请求时执行全项目读取。
- V9/V10 保留“变化不能定位或归属则 R2”；V10 的实现又把普通未登记 workspace 文件也视为 unowned，触发过宽。
- V11 为避免上述过宽触发，删除了实质的 unowned/unlocalizable 判定；后续实现只要状态结构有效，就把任意 changed paths 和 baseline 缺失送入 R1。
- V14 为 R1 增加逐项读取回执和 baseline 绑定，却没有恢复 R1 的准入证明。结果是错误进入 R1 后，Agent 需要在恢复过程中回填 owner、消费者、identity 和多类门禁，成本高于实际实现。

现行历史审计文件保持原样；本文件记录用户批准的后续修正，不回写过去版本的事实。

## 批准后的语义

恢复层只回答“为了重新取得可信上下文，需要读取多少”。它不执行项目变化的失效传播，不替代 ChangeSet，也不因恢复等级自行重开题目生命周期。

### R0_CONTINUE

只用于同一未中断窗口。当前 checkpoint identity 必须有效；此后所有相关变化都来自已经记录的本窗口 ChangeSet，失效传播已经闭合，且没有未解释外部变化。已经解释的 workspace delta 不排除 R0。R0 不建立 recovery、manifest 或 receipt。

### R1_TARGETED

只有三项资格同时成立才可选择：

1. workspace baseline 可信、当前并覆盖完整项目；
2. 每个相关新增、修改或删除都可定位到语义 owner；
3. 当前依赖图能证明完整传递消费者闭包。

新窗口只排除 R0，不自动赋予 R1 资格。R1 完整读取变化项、owner、全部传递消费者及其声明输入；闭包外对象由 baseline identity 证明未变。读取中发现闭包外相关对象时，同一 recovery episode 升级为 R2。

### R2_FULL

用户显式要求全量恢复时必须选择。状态/项目 identity 异常、baseline 缺失/过期/覆盖不全、相关变化不可定位、消费者闭包不可证明，以及 R1 scope escape 也触发 R2。

R2 重新枚举整个项目。所有 live object 都进入 manifest；唯一文本、代码和配置读到 EOF；Office/PDF、图像、数据集与其他二进制按原生、结构化或视觉载体检查；重复内容可以 hash 绑定一个已完整读取的 canonical item；未知对象必须检查后分类。承载明细的 full manifest 位于项目根外，避免自指改变 inventory。

R2 不授权 solver、执行型 verifier、重算、论文实质改写、交付构建或状态晋级。它可以从现有材料重建控制 identity 和记录 gap。

## baseline、episode 与闭合

baseline 保留 path→hash/size manifest，并由独立 meta 证明 root fingerprint、全根覆盖、inventory policy、captured revision、组件图、工件 registry、来源、文件数、未决项以及同窗 ChangeSet 连续性。`workspace_baseline_meta` 顶层对旧 state 保持可选，但一旦存在，其资格字段必须完整；缺 meta 的旧 baseline 仍可作导航，并以 `baseline_metadata_missing` 进入 R2。`watch_roots` 只可作性能提示。

一个实际恢复步骤及其完整跨组件 scope 只建立一个 recovery id 和一份合并 receipt。不得按问题、文件、消费者或门禁重复开启。R1 升 R2 保持同一 id，并复用 identity 未变的已读项。

升级轨迹由 recovery record 的 `initial_recovery_level`、当前 `recovery_level`、`escalated_from` 与 `escalation_history` 绑定；R2 的外部清单只以 path/hash/固定计数写回状态。正式执行另记录恢复 decision、执行前后 manifest、实际 changed paths、ChangeSet provenance 完整性和 execution receipt hash，供下一窗口证明变化归属。

- `closed_ready`：规定读取覆盖完成，当前动作没有恢复发现的阻断；
- `closed_blocked`：规定读取同样完成，但存在明确 stale/missing/authorization gap。

两者都可以结束 R2 全局隔离；只有 ready 可以支持绑定的 checkpoint/formal execution。blocked 的 gap 继续阻断相应业务动作。读取完成不等于项目证据通过。

## 保留与拒绝

继续保留：

- 新窗口不得使用 R0；
- 普通 dirty/cache/无关 working 新增不单独触发 R2；
- G3、里程碑、最终关闭或 pause 本身不自动 R2；
- recovery receipt 与 plan/step/scope/revision 精确绑定；
- baseline 只吸收已复核范围；
- R2 隔离不派生项目执行授权；
- 队友讲解稿的路径、内容、人审与 S6 关闭规则不受本次恢复层修改影响。

明确拒绝：

- 回到“每个新窗口一律全项目复读”；
- 把任何未登记缓存都视为 R2；
- 在 R1 内一边补消费者图一边声称闭包已证明；
- 为每道题或每个门禁生成 recovery/receipt；
- 只因 state 结构恢复有效就提前关闭 R2；
- 把 `closed_blocked` 的已知 gap 写成 PASS。

## 当前 owner 与处置

| 事实 | 规范 owner | 处置 |
|---|---|---|
| 恢复判定优先级、R0/R1 资格、episode 与 barrier | `references/runtime-policy.json` | V16 重写 |
| R0/R1/R2 必须满足的原子效果 | `rules/governance.json#REC.*` | `REC-R0-001`、`REC-R1-001`、`REC-R2-001` 均为 preserve-semantics rewrite |
| baseline、recovery 与 execution provenance shape | `references/state.schema.json` | V16 扩展，旧 baseline meta 可缺省以触发一次 R2 |
| R1/R2 唯一合并回执 shape | `references/recovery-receipt.schema.json` | 保留 V14 R1 分支，新增 V16 R2 分支 |
| 实施步骤与失败修复 | `references/capability-packets/project/recovery-and-handoff.md` | 非规范方法更新 |

修改后的 atom binding、迁移 hash、active atom count 和行为场景必须随 candidate 重新生成或更新；旧 `preserve_verbatim` hash 不能继续证明已经重写的恢复 atoms。稳定版本安装、冻结和替换仍需要用户另行批准。
