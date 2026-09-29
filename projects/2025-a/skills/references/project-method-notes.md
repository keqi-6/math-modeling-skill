# 项目能力路由（非规范性）

本文件只选择完整能力包；`rules/project.json`、`rules/governance.json`、`SKILL.md` 与机器契约继续拥有范围、权限、状态、恢复和工件效果。不得把本路由当作固定项目阶段或目录模板。

## minimal-platform

项目初始化、现有布局审计、新路径、工具链、working 产物或正式工件提升，完整读取 [项目平台与工件生命周期](capability-packets/project/platform-and-artifacts.md)。当前角色、路径、class 和准入字段直接读取机器契约，本能力包不复制枚举。

## scope-and-decomposition

问题定义、范围、计划、重规划、组件拆分或混合请求，完整读取 [项目范围与可执行计划](capability-packets/project/scope-and-plan.md)。它以请求依据、失效边界和生产者—消费者关系组织工作，不建立第二状态机。

## recovery

新窗口续作、上下文恢复、登记 identity 变化、状态缺失/损坏、暂停或交接，完整读取 [定向恢复、控制重建与项目交接](capability-packets/project/recovery-and-handoff.md)。恢复等级和允许动作仍由当前控制契约判定，本包不能授予 solver、verifier、重算或晋级。

若交接对象不是控制状态而是某一问的技术方案，同时读取 [模型实现、求解、冻结结果与解释](capability-packets/modeling/implementation-solving-and-results.md) 中的逐问技术讲解程序；不要用 handoff 摘要替代模型、结果、验证和复现链。

## compatible-cross-component-change

当后做题目中的实现技巧要回传到前题，并且问题解释、数据合同、假设、目标、约束、可行域、候选集、选中模型、数学规格和主张边界都不变时，使用兼容变更快车道：

1. 先在来源题按预定指标验证新技巧确有正收益，并取得当前 E1/E2；来源题中的未证实探索不进入目标题。随后在一个 G1 ChangeSet 中写明来源题、实际目标题、改变的实现 facet 和每个目标真正受影响的后规格 evidence level；连续完成代码、直接消费者和本轮验证，不改状态、不登记 working identity、不写持久回执。讲解稿、配图和说明仅在其内容或引用真实变化时列为消费者，不机械全量刷新。
2. 只有需要接受新的 milestone/frozen identity 或阶段完成声明时才进入 G2。一个 `reconcile_compatible` 步骤覆盖整个目标集合，只做一次身份 checkpoint 和一次 execution。
3. 将新的 `implementation_ref`、E1、E2 以及实际受影响的更高层证据放进一个 compatible-change bundle；其中新的 file/command locator 必须落在 ChangeSet。控制器先 live-validate 复用的模型前缀与来源题证据，再把实际 protected registered identity delta 与 `artifact_updates` 闭世界对账，原子地 stale 旧绑定、安装全部替代、刷新声明 identity 并原位复验。
4. 未被 effect 点名的组件默认不受影响。控制器全局扫描旧 file/command locator 和 artifact input refs；只有 claim identity 实际变化时才填写可选 `claim_updates`，其 old/new identity 是旧/新 producer evidence `claim` 文本的 SHA-256。控制器同时核对所有当前 producer、旧 identity 的 typed consumers，并要求闭包内替代 evidence 绑定 new identity。普通实现回传不自动扩散或回填未变化 claim。若 exact identity/显式 claim update 证明另有生产者或消费者、存在漏报 identity/path，或目标/来源题的 state、status、invalidation marker 在 execution 内漂移，bundle 整体拒绝，先补全闭包或退出快车道。无 exact evidence 绑定的无关 working artifact 不阻断本批；不沿粗粒度 component consumer 边生成“先失效、再证明无影响”的文档。
5. 若实现等价性失败，或 delta 实际触及模型规格、候选/选择、假设、目标、约束、可行域或主张边界，退出快车道，按最早真实变化层走普通 reopen；不得把合同变化伪装成性能优化。

这条路径减少的是重复控制提交，不减少技术验证。对同一批回传，安全边界仍是一次明确授权、一次基线身份、一个精确影响闭包和一次最终接受。

## 完整性边界

新项目的范围与首个工件同时相关时读前两个包；接手后重规划时先读恢复包，再在取得可信事实后读范围包。选中的包完整读取。若三包都需要，按“恢复事实—范围/计划—实际工件”分阶段，并携带当前目标、已确认决定、权威 identity、未决 gap 和下一能力包；不一次预载全部领域资料。
