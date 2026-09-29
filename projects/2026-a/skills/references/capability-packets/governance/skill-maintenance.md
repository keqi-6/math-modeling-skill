# Skill 维护、验证与兼容性报告

适用于用户明确要求审计、修改、增加、合并、废弃或发布本 Skill 的工作。普通数学建模项目中发现 Skill 缺陷时只报告；本包不把项目推进扩大成 Skill 自修改授权。

## 规范边界

本包是非规范性维护方法，不新增维护门或发布驱动。正式 owner 是：

- `SKILL.md`：Skill-only 授权隔离、维护/发布边界和活跃入口；
- `rules/maintenance.json`：`MNT-CLASSIFY-001`、`MNT-IMPACT-001`、`MNT-OWNER-001`、`MNT-EVAL-001`、`MNT-RELOAD-001`、`MNT-ROLLBACK-001` atoms；
- `rules/governance.json` 与 `references/ownership-contract.json`：授权、唯一 owner 和解释器边界；
- `references/runtime-policy.json`、`references/semantic-plan.schema.json`、`references/route-contract.json`：当前运行语义；
- `references/release-policy.json`：活跃发布驱动、行为证据标准、退役边界和冻结授权；
- 被改能力各自的 rule、contract、schema 或控制器 owner。

V10 单 operation change envelope、固定旧版本 oracle、逐 atom 同源生成测试和失效 legacy harness 已退出发布包；它们的取舍只以压缩后的 preservation disposition 保存。当前维护不提供这些旧接口，也不恢复一次一文件或全量 legacy gate。

## 进入维护前

1. 保存用户明确授权的原请求片段，并把 `skill_maintenance` 放入隔离的 Skill-only 计划；
2. 区分只读审计、候选修改、候选验证、冻结、安装与覆盖；前一项不自动授权后一项；
3. 确认目标 Skill 根、当前稳定版、候选根和允许写入范围；
4. 对只读审计只产出发现，不创建候选或运行会改变外部状态的动作；
5. 对修改先保留可读的旧版本身份，再在 base→candidate 上工作，不原地覆盖唯一稳定版。

若一个请求同时包含项目工作和 Skill 修改，拆成有依赖的独立步骤；Skill 步骤只继承明确指向 Skill 的授权，不借用“继续项目”“修一下”或沉默扩权。

## 把变更写成可观察差量

先从当前 owner 提取旧行为，再写：

- 旧效果：真实 `verb/target/value`、触发、scope、例外和当前可达 route；
- 新效果：一个可独立通过/失败的可观察行为；
- 保持项：不得随本次变化的邻接能力、权限、状态和失败边界；
- 变更类型：规范语义、触发/路由、运行时治理、schema/contract、方法包/文档、实现或测试；
- 风险：影响哪些实际请求、写入、状态、证据或发布结论。

多个效果可以在一个 ChangeSet 联合修改，但仍分别建模；能独立变化、独立失败或拥有不同 scope/trigger/exception/evidence 的效果不要塞进同一 atom。项目特例留在项目配置或方法说明，除非有跨项目证据支持升级。

历史 L0–L4 可用作影响估计，最终分类由当前 atom/contract 判断：

| 级别 | 典型变化 | 相称验证 |
|---|---|---|
| L0 | 无语义格式、错别字 | 解析、格式和精确 diff |
| L1 | 澄清、示例、非规范 capability packet | 引用/锚点、owner 边界和相关回归 |
| L2 | 领域规则、触发或 route 行为 | 影响闭包、自然语言正例、近似反例、混合/冲突场景 |
| L3 | 权限、状态、恢复、schema、runtime governance | 契约闭合、差分行为、迁移和临时真实项目场景 |
| L4 | 删除核心能力或改变维护/发布内核 | 新主版本、适用范围完整回归、独立回滚点和新调用验收 |

不要因为改动文件少就降级风险，也不要因为风险高就无差别运行全部历史脚本。

## 计算最小影响闭包

从真实 owner 向消费者追踪：

`owner effect → capability/semantic key → scope/trigger/exception → route/event → context packet/method note → contract/schema → interpreter → state/evidence → eval/scenario → release/migration/lineage`

至少检查：

- 当前 owner 是否唯一，编辑的是 owner 还是生成视图/旧版本；
- 同 capability 的 atoms 是否仍能分别判定，ID/revision/retirement 是否正确；
- route 是否由当前显式契约可达，而不是 catchall 或旧版传递链接；
- context packet 是否只提供方法、能从命中 route 到达、引用锚点存在且没有复制规范枚举；
- effect target 与相同 scope 上的其他语义是否重叠或冲突；
- schema、状态、回执、工件、恢复和授权消费者是否需要同步；
- 脚本是否只是实现，是否仍忠于 owner；
- 正例、近似反例、冲突/状态绑定例是否观测真实结果；
- migration、compatibility、manifest 或安装身份是否受影响。

先完成影响分析再编辑。若影响扩展到原请求未授权的控制面，只记录为独立提案或阻断项，不顺手修复。

## 在候选中实施

1. 记录 base 的版本、根和必要 identity；高风险变更保留不可变回滚点；
2. 在隔离 candidate 中编辑 canonical owner；需要联动的消费者放入同一 ChangeSet；
   Skill-only ChangeSet 的新路径必须是 candidate 根内的相对路径，由 `route-contract.json` 的 `skill_package_boundary` 约束；它不套用数学建模项目的 `project-platform-contract.json` 目录角色；
3. 规则语义只写在一个 owner，其他文件使用 ID、链接或解释，不复制控制权；
4. 更新 route/contract/schema/实现只限于新效果的真实影响闭包；
5. 为删除、合并或 supersede 记录去向，不让已确认能力静默消失；
6. 不修改已发布旧版本，不在候选验证阶段冻结或安装；
7. 项目工作区存在无关改动时保留它们，不把清理工作区混入 Skill ChangeSet。

方法包改动尤其要检查“可达且非规范”：它应让当前步骤获得一个最小完整操作闭包，但不能让 Agent 启动时一次加载全部包，也不能把包内解释当作新 atom。

## 分层验证

### 结构和契约

验证包可解析、声明的活跃文件存在、owner 唯一、rule/route/event/context/contract/schema 映射闭合，并直接复算规则 inventory、历史能力 disposition 与能力包可达性。检查当前候选真实内容，不让 validator 只读取自己刚写给自己的证明文件，也不从当前规则自动生成 oracle 再回验同一规则。

### 行为

对实质行为变化至少观察：

- 原始自然语言正例能触发目标行为；
- 只有细微差异的近似反例不会误触发；
- 混合请求只影响相关步骤；
- 冲突、状态和授权边界没有被绕过；
- 保持项继续成立，旧缺陷确实失败后修复。

断言数、标题、关键词、文件存在、mutation 数或退出码零都不能单独证明行为。测试预分类 JSON 只能检查接口，不能代替自然语言到可观察结果。

### 重载与独立性

从 candidate 根启动 fresh subprocess，证明新进程实际加载候选。高风险且环境提供、用户授权独立调用时，再让独立重载 Agent 执行前向场景；不可用时如实列为未验证边界，并保留新进程证据，不能伪造结果文件。

### 发布

候选达到发布阶段时按当前 `release-policy.json` 运行三个活跃 gate，并逐个核对稳定 outcome/case id 和证据。发布计划同时保存本次人工审定的旧行为、新效果、保持项、retired/merged、未验证边界、影响面和回滚身份；脚本只校验结构、引用和 gate 绑定，不替代人工判断。已退役测试不得重新进入包内可执行面。冻结和安装分别需要明确授权；发布 gate 通过本身不构成安装授权。

## 兼容性与交付报告

报告按能力而不是按文件数量组织：

- `preserved`：行为和可达性由本次证据确认；
- `changed`：旧/新效果、触发、例外、消费者和迁移后果；
- `retired/merged`：旧 ID、去向、替代 owner 和兼容边界；
- `unverified`：未运行、环境不可用或证据不足的真实边界；
- `conflicts`：发现、裁决依据和仍需人工决定的同维度冲突；
- `rollback`：旧版本身份和安全恢复位置；
- `files/tests`：实际 ChangeSet、命令、场景及失败/通过结果。

报告不得用硬编码 PASS、断言总数或“全量验证”替代逐能力证据。只读审计的结论不能冒充候选已实现；候选已实现也不能冒充已冻结或已安装。

## 人工复核点

以下变化在实施或推进前提交人审：

- 改变 `MUST` 效果、scope、trigger、exception、证据要求或允许主张；
- 改变授权、状态迁移、恢复等级、危险命令或写入边界；
- 删除/合并已确认能力、复用 ID 或改变 canonical owner；
- 真实同维度冲突无法由 scope、证据、refines/supersedes 解析；
- 需要发布、冻结、安装、覆盖旧版本或改变回滚点；
- 独立测试需要额外服务、账号、成本或外部写入权限。

不要把每个文件保存、每个测试或每个内部步骤变成人工逐步批准。

## 失败与修复

| 失败 | 修复 |
|---|---|
| 编辑摘要、生成视图或旧版本期待生效 | 找到当前 canonical owner，在 candidate 中重做 |
| 用第二段强规则“修复”冲突 | 合并到唯一 owner，显式 retire/refine/supersede |
| 只看编辑文件，没有查 route/contract/消费者 | 重建传递影响闭包后再实施 |
| atom 存在但 route 或 context 不可达 | 检查当前显式 route 与最小方法闭包；不靠 catchall |
| 只测正例或预分类标签 | 增加近似反例、混合/冲突和状态绑定观察 |
| 编辑进程自行宣称新 Skill 生效 | 从 candidate 根启动 fresh subprocess |
| validator 和被验证材料同源自证 | 增加独立 outcome、真实临时项目或外部观察 |
| 用断言数、mutation 数或标题数证明质量 | 改为稳定 case id、输入、观察结果和证据 |
| 一次真实故障被推广成所有请求的硬步骤 | 把修复限制在真实 trigger/scope/exception |
| 为追求兼容而恢复已退役 legacy suite | 从 preservation disposition 找到仍有价值的行为，把它迁入当前 owner 或稳定场景；不要恢复旧入口 |
| 覆盖唯一稳定版后才发现回归 | 保留 base 身份，在 candidate 修复并验证回滚 |
| 项目缺陷报告被当作 Skill 写授权 | 停止写入，提交独立 Skill 变更请求 |

## 需要独立授权的影响审计对象

下列对象只登记为未来影响审计，不在本包或无关维护 ChangeSet 中选择方案、增加字段、修改脚本/契约或声称已修复。必须由用户对具体对象、目标行为、兼容与迁移边界作独立明确授权后，才能设计和实施：

- **状态并发、CAS 与锁语义**：普通 G1 mutator、revision 前置条件、跨进程锁、固定 `.tmp` 路径、崩溃恢复及 Windows/Unix 行为的完整闭包；
- **原始 request 留存与脱敏**：完整请求、精确授权片段、request hash 在 semantic plan、state/execution ledger、命令行与持久证据中的用途、访问、保留期限和敏感信息处置；
- **resolver 与最小上下文闭包**：atom/capability 到 route、capability packet、section anchor 和依赖闭包的可达性、去重、失败策略及加载预算；
- **发布内核与历史保护策略变更**：活跃 driver 数量、冻结规则 inventory、迁移差量、manifest identity 或旧能力 disposition 的保护方式。

未获具体授权时只记录这些对象的 owner、调用者、风险、现状证据和待决定问题；不要把建议实现细节写成既定规范，也不要捎带进入无关维护范围。

## 来源保留说明

本包保留 V1–V8 经 V9 `maintenance-contract.md` 收敛的显式触发、L0–L4 风险、owner-first、正/近反/冲突测试、新调用重载和回滚原则；以 MNT atoms 和唯一 owner/冲突图为规范锚点。V11 的完整多步骤 ChangeSet 取消单 operation 限制，V12 的 outcome gate 与平台契约强调可观察结果，V13 加入 Skill-only 精确授权与执行生命周期，V14 将活跃发布链收敛为包、契约和临时真实项目场景，V15 把仍有价值的 legacy 行为迁入当前驱动后删除旧可执行链，并以能力包与历史 disposition 保护无损披露。已明确不恢复全量启动读取、逐步回执、一次一文件、固定目录、断言/关键词计数、逐 atom 同源 oracle 或重型历史门禁。
