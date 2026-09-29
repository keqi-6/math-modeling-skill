# 建模能力路由（非规范性）

本文件只选择完整作业包。`rules/modeling.json` 拥有比较、规格、实现和结果规则；atom 的短说明不能代替方法程序。

## 选择规则

| 当前工作 | 必读能力包 |
|---|---|
| 重述当前问、建立基线、生成/比较候选、人工选模 | [问题重述、基线、候选比较与人工选模](capability-packets/modeling/problem-and-candidates.md) |
| 定义变量、目标、约束、接口、算法和允许主张，或冻结/修改规格 | [可实现、可验证的数学规格](capability-packets/modeling/mathematical-specification.md) |
| 按规格实现、运行求解、登记/解释结果或更新消费者 | [模型实现、求解、冻结结果与解释](capability-packets/modeling/implementation-solving-and-results.md) |

比较、规格和实现是可以连续推进但不可互相替代的阶段。已有冻结规格的纯实现任务不必重读全部候选知识；结果解释仍需读取实现结果包并绑定当前规格与验证。

## specification

规格设计、修改或冻结完整读取 [可实现、可验证的数学规格](capability-packets/modeling/mathematical-specification.md)。如果规格选择仍未决定，同时读取候选比较包；不能把未确认的候选偷偷写成冻结规格。

## implementation

实现或求解完整读取 [模型实现、求解、冻结结果与解释](capability-packets/modeling/implementation-solving-and-results.md)，并以当前数学规格为入口。只有规格缺失、冲突或确实变化时才回到规格包，不因实现细节机械重做选模。

## results

结果汇总与解释完整读取 [模型实现、求解、冻结结果与解释](capability-packets/modeling/implementation-solving-and-results.md)，同时绑定实际验证结论；不从代码复杂度、运行时长或漂亮图形推导主张强度。

`prepare_teammate_brief` 复用同一包，为每个实质问题在 `docs/<task-id>/solution_brief.md` 写一份十节完整建模稿。它可以在 S5 结果可解释后用 G1 起草，通常随 S6 技术验证完成，并在实际关闭该问 S6 前由人阅读当时文件、复述对象—机制—证据—结论—边界。该要求是 S6 的人类理解出口，不是第五条技术验证轴；文件存在或静态审计不能替代人审。S7 后纯表达更新仍是 G1，只有数学合同、结果或主张边界变化才重审受影响闭包。主稿、可选复现旁注和未来论文的职责边界见实现结果包。

## 完整性边界

选中的包完整读取。若上下文不足，按“当前问与候选—冻结规格—实现求解—验证解释”分阶段，并携带已确认决定、规格 identity、结果 identity 和未决风险；不得只留下模型名、公式清单或软件接口。
