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

`prepare_teammate_brief` 复用同一包，为每个实质子问写九项语义覆盖并安排人工复述。它可以在一份技术文档中按问组织，不要求固定文件名，不属于 S7 证据门，也不能整篇自动晋升为论文；进入稿件写作前必须有当前身份下的逐问讲解闭包。

## 完整性边界

选中的包完整读取。若上下文不足，按“当前问与候选—冻结规格—实现求解—验证解释”分阶段，并携带已确认决定、规格 identity、结果 identity 和未决风险；不得只留下模型名、公式清单或软件接口。
