# 验证能力路由（非规范性）

本文件选择完整验证包；`rules/verification.json` 和状态机拥有 E1–E4、证据与 S6 效果。路由选择不证明领域 oracle 已执行。

## implementation-axis

实现符合性或数值解检查完整读取 [E1/E2：实现符合性与数值解验证](capability-packets/verification/implementation-axis.md)。退出码、哈希、字段存在和重复同值不能单独关闭该轴。

## model-axis

模型结构、假设、现实映射或用途确认完整读取 [E3/E4：模型结构检验与现实映射](capability-packets/verification/model-axis.md)。`validate_structure` 只执行 E3，`assess_reality` 只执行 E4，兼容动作 `validate_model` 才同时做两轴；不得为只做 E3 的任务伪造 E4 event 或 runtime action。

E3 先声明核心失败风险，再从约束、不变量、极限/特例、反例和敏感性中选择至少一个有信息增量的检验；每个专项事件只触发对应 atom，不能机械全选菜单，也不能完全不测。E4 仅在现实证据条件成立时触发。

## uncertainty-and-robustness

误差传播、参数/结构敏感性、情景稳健性或结论翻转边界完整读取 [误差、不确定性、敏感性与稳健性](capability-packets/verification/uncertainty-and-robustness.md)。它按实际风险进入 E2/E3/E4，但不替代其他轴。

## s6-closure

S6 readiness/close 同时读取当前实际涉及的包，并只核验当前 E1–E4 精确证据。E1 与 E3 必须由有效检验闭合；E2 只有在不存在数值近似、搜索、随机、离散化或比较风险时，E4 只有在没有可辩护现实比较器且明确禁止经验/部署有效性主张时，才可用结构化 `justified_not_triggered` 闭合。该记录必须绑定当前模型规格 artifact identity，并引用一个已解决的人工适用性决定，同时给出理由、适用性依据和主张边界；规格 identity 变化会使它失效。机器只核验结构、身份新鲜度与决定状态，理由是否诚实仍由人工审计。裸 N/A、把失败写成 N/A 或省略适用检验均不能过门。

实际关闭一个实质问题的 S6 时，还要按 [模型实现、求解、冻结结果与解释](capability-packets/modeling/implementation-solving-and-results.md) 核对该问固定路径下的队友讲解稿，并取得对当时文件的实际人工阅读与复述决定。这个决定是人类理解门，不是 E1–E4 之外的第五条技术轴：技术证据通过、文件存在、静态结构检查、提前授权或自然暂停都不能替代它。关闭证据绑定被审版本；S7 后纯表达调整不反向使技术轴失效，只有内容责任、结果或主张边界真实变化时才更新受影响接受闭包。

选中的包必须完整阅读；上下文不足时分轴推进并携带 input/claim identities、oracle、结果和证明边界，不把四轴压成一张总分表。
