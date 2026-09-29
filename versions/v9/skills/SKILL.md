---
name: mathematical-modeling-project-controller
description: 端到端管理数学建模竞赛或研究型建模项目，包括题意审计、数据、建模、验证、论文、图表、交付、恢复，以及用户明确要求时维护本 Skill。用于完整项目或现有项目工作；不要用于孤立的普通数学题、无项目语境的通用 LaTeX 编辑，或未获授权的自动自修改。
metadata:
  version: "9.0.0"
  release: "stable"
---

# 数学建模项目控制器 V9.0.0

## 1. 目标与控制边界

在不越过用户授权的前提下，把数学建模项目推进为可复核、可恢复、可交付的结果。本文件是运行时唯一控制入口；详细模块只拥有各自领域的操作方法和验收知识，不得另行决定全局权限、状态、恢复等级、路由或文件创建。

本 Skill 同时保留 V1–V8 的有效领域能力，但不继承以下缺陷行为：冲突控制权、无条件全量复读、不可达路由、叙述性状态漂移、无需求的项目脚手架，以及只匹配固定措辞的伪行为测试。

系统、开发者和工具约束始终高于本 Skill。本 Skill 内部不要用一条混合优先级处理所有冲突，而要分开判断：

1. 用户当前请求和明确授权决定允许做什么；
2. 数学、数据和可核验证据决定可以声称什么；
3. 已冻结项目决策决定当前采用什么；
4. 组件状态决定现在可以执行什么动作；
5. 领域模块决定动作具体如何完成。

同一维度出现冲突时停止受冲突影响的动作，指出冲突并使用当前明确、证据更强且作用域更窄的有效决定。不得静默拼接相互矛盾的规则。

## 2. 执行模式

每个请求先选择一个模式，并保持到用户请求或授权发生实质变化：

| 模式 | 含义 | 默认写权限 |
|---|---|---|
| `advisory_readonly` | 回答、解释、方案讨论或独立审计 | 无 |
| `project_readonly` | 检查现有项目与产物 | 无 |
| `mutate` | 用户要求创建或修改项目内容 | 仅请求范围内 |
| `promote` | 冻结阶段、发布、打包或交付 | 仅经验证的目标 |
| `skill_maintenance` | 用户明确要求修改本 Skill | 仅本 Skill 及隔离评测区 |

“继续”“看看”“审计一下”“给意见”不自动授权写文件。用户明确要求创建、修改、修复、完成、更新或发布时，可在该任务的合理范围内执行相应写操作。普通项目运行中可以记录 Skill 缺陷，但不得自行进入 `skill_maintenance`。

## 3. 请求分类与路由

路由使用四元组：

```text
执行模式 × 操作对象 × 用户动作 × 当前状态
```

操作对象包括 `project`、`literature`、`data`、`model`、`verification`、`manuscript`、`visual`、`delivery`、`skill`。先依据用户完整意图分类，不按单个关键词决定。然后运行：

```bash
python3 scripts/resolve_route.py \
  --mode <mode> --object <object> --action <action> --state <state>
```

只有解析器返回唯一合法路由后才执行写操作。读取解析器返回的直接模块，不根据模块内部的旧路径提示继续递归加载。任何导入的 V8 详细文本中关于全局控制、路由、状态、回执、项目初始化、强制复读或“第一入口”的句子均是迁移上下文，由 V9 契约取代；其中的领域步骤、数学判据、失败条件和验收细节仍有效。

恢复评估不是所有请求的前置动作。未初始化项目的咨询、项目初始化和 Skill 审计/维护使用 `not_applicable`；不得因为这些请求没有 `.modeling/state.json` 就宣称发生 R2。只有继续现有项目或动作依赖既有项目状态时才评估 R0/R1/R2。

路由以能力保真为前提控制直接模块数量和文本预算；局部任务使用专用小契约，完整审计可以使用经声明的较大预算。预算见 [references/context-budget.json](references/context-budget.json)，不得为了满足行数指标删减必要领域步骤。

若没有唯一匹配：

- 只读任务可继续做不依赖歧义的检查，并说明假设；
- 写任务必须缩小对象、动作或状态后重新解析；
- 不得使用 closure 或维护 catchall 假装路由成功。

机器路由契约见 [references/route-contract.json](references/route-contract.json)。

## 4. 状态模型

不要用单一 `current_stage` 代表整个项目。状态按组件类型记录：

- 问题组件：`S0` 发现、`S1` 定义、`S2` 证据就绪、`S3` 方案比较、`S4` 规格冻结、`S5` 实现、`S6` 验证、`S7` 交付；
- 共享数据：`D0` 登记、`D1` 审计、`D2` 处理决定冻结、`D3` 可复用；
- 产物：`A0` 计划、`A1` 草拟、`A2` 验证、`A3` 发布；
- 项目：`P0` 活跃、`P1` 可交付、`P2` 关闭。

只有问题组件走完整 S0–S7。共享数据和产物不得被伪装成 S7 问题。阶段提升必须满足状态契约的进入条件和证据要求；失败只回退受影响组件及其消费者。

权威项目状态只有 `.modeling/state.json`。它仅在用户授权创建或修改项目时建立；咨询和只读审计不得为了使用本 Skill 创建它。详细契约见 [references/state-contract.json](references/state-contract.json)。

可用时使用 `scripts/state_manager.py` 原子地增加组件、推进状态、登记产物和设置下一动作；不要手工编辑一半后留下不可解析状态。状态推进必须提供目标状态要求的证据键及其项目内引用。

## 5. 恢复与接手

先检查权威状态和已登记产物，再选择恢复等级：

- `R0_CONTINUE`：状态可读，登记产物身份一致，无未解释外部变化；直接继续下一合法动作。
- `R1_TARGETED`：变化可定位到有限组件；只重读和复核受影响组件及直接消费者。
- `R2_FULL`：状态缺失或损坏、核心身份冲突、变化无法定位、用户明确要求完整恢复，或里程碑/最终闭合需要全局证明；执行全量恢复。

R0/R1 不得被旧模块中的“启动必须全文重读”覆盖。自然语言交接仅供人阅读，不是权威状态。恢复细节见 [references/recovery-governance.md](references/recovery-governance.md)，确定性检查使用 `scripts/assess_recovery.py`。

## 6. 决策与写入

区分三类决定：

- `new_design`：绿地设计，没有可保持的当前方案；
- `change_existing`：已有冻结方案，比较保持与改变；
- `not_applicable`：机械修复、只读分析或不需要方案选择。

只有会改变冻结模型、官方数据口径、交付边界或用户已确认结构的操作才要求显式决策。普通实现细节在已授权范围内可自主完成。

创建文件前必须满足产物准入条件：明确消费者、目的、生命周期、授权和正式/临时类别。没有消费者的占位文件、空目录、重复清单和每轮独立回执文件不得创建。草稿计算优先进入临时目录，验证后才提升为正式产物。见 [references/artifact-contract.json](references/artifact-contract.json)。

## 7. 回执

回执是对执行的结构化描述，不等于在项目中创建新文件。通常在回复和权威状态中表达；只有用户或现有工作流明确要求独立回执文件时才落盘。

开始回执说明模式、对象、动作、组件状态、恢复等级、路由和计划产物；结束回执说明实际变更、验证、状态变化、开放问题和下一动作。两者使用同一判别联合 Schema：[references/receipt.schema.json](references/receipt.schema.json)。`routed_rules` 必须与解析器输出一致。

## 8. 领域模块

解析器只加载当前路由列出的模块：

- 项目结构与完整方案：[references/modules/project-platform.md](references/modules/project-platform.md)、[references/modules/orchestration-detail.md](references/modules/orchestration-detail.md)
- 文献与证据交付：[references/modules/evidence-delivery.md](references/modules/evidence-delivery.md)
- 数据：[references/modules/data.md](references/modules/data.md)
- 建模：[references/modules/modeling.md](references/modules/modeling.md)
- 实现验证、模型检验、稳健性与不确定性：[references/modules/verification.md](references/modules/verification.md)
- 论文内容与读者审计：[references/modules/manuscript-content.md](references/modules/manuscript-content.md)
- 论文验收：[references/modules/manuscript-acceptance.md](references/modules/manuscript-acceptance.md)
- 论文局部修改：[references/manuscript-local.md](references/manuscript-local.md)
- 图表与排版：[references/modules/visuals-layout.md](references/modules/visuals-layout.md)
- 可选写作风格：[references/modules/writing-profile.md](references/modules/writing-profile.md)

验证层级统一称为：

- `E1_IMPLEMENTATION`：代码、接口、单位、边界和复现；
- `E2_NUMERICAL`：数值一致性、误差、重复计算；
- `E3_STRUCTURAL`：约束、守恒、极限、反例和敏感性；
- `E4_REALITY`：假设、参数、尺度、现实适配和可解释性。

不得再使用 V1–V4 表示验证层级，以免与 Skill 版本混淆。S6 必须同时覆盖“实现是否正确”和“模型是否合理”，二者不能互相替代。

只读判断“是否具备关闭 S6 的条件”使用双轴就绪审计，不修改状态；只有用户授权实际推进且双轴证据均闭合时，才使用 `promote` 路由关闭 S6。

## 9. 完成与交付

局部完成只要求受影响组件、直接消费者和声明范围闭合。只有用户要求里程碑、最终交付或全项目结论时，才执行全局审计。编译成功、脚本退出码为零、标题齐全或验证器找到固定短语，都不能单独证明结果正确。

最终交付至少核对：请求覆盖、数学与数据证据、代码/结果可复现性、论文主张、图表身份、来源许可、文件边界和状态一致性。只声称实际验证过的范围。

## 10. Skill 维护模式

用户明确要求新增、修改、合并、废弃或发布本 Skill 的规则时，读取 [references/maintenance-contract.md](references/maintenance-contract.md)。维护流程必须：

1. 把请求解释为旧行为、新行为、触发、例外和风险等级；
2. 搜索现有能力、唯一 owner、重复与冲突；
3. 生成影响集合：能力、路由、状态、Schema、模块和评测；
4. 只修改 canonical owner，摘要和索引从事实源同步；
5. 添加正例、近似反例和冲突场景；
6. 运行完整契约与回归验证；
7. 用重新加载新版 Skill 的新调用验证实质行为变化；
8. 报告兼容性、证据和回滚点。

同一上下文编辑磁盘文件后，不得以“当前 Agent 感觉规则已生效”作为行为验收。维护内核、权限、状态机或删除核心能力属于高风险变更，必须保留旧版本并使用新主版本或明确迁移记录。
