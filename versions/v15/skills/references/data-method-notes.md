# 数据能力路由（非规范性）

本文件负责选择完整方法包；`rules/data.json` 拥有适用性、规则强度、证据和冻结效果。不得只凭 `instruction_gloss` 执行数据工作。

## 选择规则

| 当前工作 | 必读能力包 |
|---|---|
| 首次读取、身份核对、结构/缺失/异常诊断、设计能力判断 | [数据身份、结构与证据能力审计](capability-packets/data/identity-and-audit.md) |
| 只读提出清洗/插补/异常处置备选，不执行或登记决定 | [数据处理、转换与冻结](capability-packets/data/treatment-and-freeze.md) |
| 执行清洗、插补、纠正、合并、派生字段、接口晋升或冻结 | [数据处理、转换与冻结](capability-packets/data/treatment-and-freeze.md) |

处理任务必须先取得当前输入 identity 和审计结论，因此通常两个包都读；纯只读审计不预先加载处理细节。冻结前重新核对处理决定、schema、泄漏与消费者。

## treatment

`RT.DATA.TREAT.PROPOSE` 只读列出包括“不处理”在内的备选、影响、风险和选择条件；它不写数据、不生成候选 identity、不登记 `treatment_decision`，也不能满足 D1→D2。建议必须明确依据的是已知审计发现、当前样本观察还是尚待审计的假设，不能把猜测写成已证实的数据问题。

真正清洗、插补、纠正、合并或派生字段时使用 `RT.DATA.TREAT`：先完整读取 [数据身份、结构与证据能力审计](capability-packets/data/identity-and-audit.md)，再完整读取 [数据处理、转换与冻结](capability-packets/data/treatment-and-freeze.md)。如果身份审计已在同一未中断步骤内完成且输入未变，可复用其结论。只读 proposal 不能替代人工确认后的正式处理决定。

## freeze

冻结或晋升正式数据接口时，完整读取 [数据处理、转换与冻结](capability-packets/data/treatment-and-freeze.md)，并复核其引用的当前输入 identity、处理决定、独立检查和消费者传播；历史“已通过”不能替代当前候选的这些绑定。

## 完整性边界

选中的能力包完整读取。上下文紧张时按“身份—审计—处理候选—人工决定—冻结”分阶段推进，携带输入 identity、已确认处理和未决问题；不得截掉统计单位、结构性缺失、原始可追溯或独立复核要求。
