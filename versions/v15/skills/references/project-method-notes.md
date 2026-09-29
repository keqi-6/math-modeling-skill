# 项目能力路由（非规范性）

本文件只选择完整能力包；`rules/project.json`、`rules/governance.json`、`SKILL.md` 与机器契约继续拥有范围、权限、状态、恢复和工件效果。不得把本路由当作固定项目阶段或目录模板。

## minimal-platform

项目初始化、现有布局审计、新路径、工具链、working 产物或正式工件提升，完整读取 [项目平台与工件生命周期](capability-packets/project/platform-and-artifacts.md)。当前角色、路径、class 和准入字段直接读取机器契约，本能力包不复制枚举。

## scope-and-decomposition

问题定义、范围、计划、重规划、组件拆分或混合请求，完整读取 [项目范围与可执行计划](capability-packets/project/scope-and-plan.md)。它以请求依据、失效边界和生产者—消费者关系组织工作，不建立第二状态机。

## recovery

新窗口续作、上下文恢复、登记 identity 变化、状态缺失/损坏、暂停或交接，完整读取 [定向恢复、控制重建与项目交接](capability-packets/project/recovery-and-handoff.md)。恢复等级和允许动作仍由当前控制契约判定，本包不能授予 solver、verifier、重算或晋级。

若交接对象不是控制状态而是某一问的技术方案，同时读取 [模型实现、求解、冻结结果与解释](capability-packets/modeling/implementation-solving-and-results.md) 中的逐问技术讲解程序；不要用 handoff 摘要替代模型、结果、验证和复现链。

## 完整性边界

新项目的范围与首个工件同时相关时读前两个包；接手后重规划时先读恢复包，再在取得可信事实后读范围包。选中的包完整读取。若三包都需要，按“恢复事实—范围/计划—实际工件”分阶段，并携带当前目标、已确认决定、权威 identity、未决 gap 和下一能力包；不一次预载全部领域资料。
