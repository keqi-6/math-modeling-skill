---
name: mathematical-modeling-project-controller
description: 端到端管理数学建模竞赛或研究项目，覆盖范围、文献证据、数据、建模、实现、验证、论文、图表、交付、接手恢复，以及用户明确授权时的 Skill 规则维护。用于完整项目、现有项目续作或有项目语境的局部任务；不用于孤立普通数学题、无项目语境的通用排版，或未获授权的 Skill 自修改。
metadata:
  version: "10.0.0"
  release: "stable"
---

# 数学建模项目控制器 V10

## 规范所有权与可验证边界

V10 不把同一规则复制到多个文件。[ownership-contract.json](references/ownership-contract.json) 定义“每个规范事实只有一个 owner”：

- 本文件只拥有入口、授权边界和失败关闭协议；
- `rules/*.json` 的每个活动 atom 只有 `effect` 是该 atom 的规范后果；`instruction_gloss`、`failure_example` 和 `outcomes` 是非规范性解释；
- 路由、状态、工件、回执和规则变更的结构事实，分别由对应的 machine contract 拥有；
- `scripts/*.py` 是契约解释器，不是另一份独立规则；
- `*-method-notes.md` 只提供被路由按需加载的方法选项。V1–V9 只用于谱系与保真审核，运行时不加载。

规则文本也必须原子化：一个 atom 只拥有一个可独立决定的 `effect`。只有同一记录结构、同一合取门或同一封闭选项集，且其 scope、trigger、strength、exception、evidence、enforcement 和 outcome 全部相同时，`value` 才可包含多个成员；任一成员能被单独修改、单独通过或单独失败时必须拆成不同 atom。该判据由 [ownership-contract.json](references/ownership-contract.json) 唯一定义。

`enforcement.kind=runtime_guard` 表示效果有机器守卫和行为测试；`agent_obligation` 表示解析器可验证该 atom 已被选中并完整交付给 Agent，但领域推理的实际质量仍需证据验收。不得把“已路由”声称成“效果已自动证明”。

## 每次请求的必经协议

### 1. 从原始请求求解授权和路由

回答、解释、建议和审计默认只读。创建、修改、修复、续作、提升或发布，只授权完整请求的合理边界。普通项目任务可以报告 Skill 缺陷，不得顺便改写 Skill。

把未改写的用户原文交给解析器：

```bash
python3 -B scripts/resolve_route.py \
  --request "<用户原始请求>" \
  [--project-root "<项目根目录>"] \
  [--component-id "<单一默认组件>"] \
  [--component-map '{"RT.MODEL.IMPLEMENT":"q1","RT.VERIFY.IMPLEMENTATION":"q2"}']
```

`--component-map` 在一个请求同时作用于多个组件时使用；键是 route ID 或 object，值是真实 component ID。不要向解析器伪造 mode、state 或 recovery。

只有每个实质子句都得到合法 route，所有组件都能唯一绑定，且 `status=resolved` 时才能继续。`blocked` 或 `ambiguous` 时，先做不依赖歧义的只读检查；仍会改变结果时才请用户补充。不得用 catchall 、被排除候选或未覆盖子句伪装路由成功。

### 2. 执行 atom 适用性结果

解析器对 route selector、object、component type/state、event、predicate 和 runtime exception 逐项求值，并返回 `applicability_evidence`。

- `applicable`：该 atom 是当前规范集的一部分；
- `not_applicable`：保留排除证据，不执行该 effect；
- `needs_fact`：谓词事实不足；可写请求中的 MUST 会自动阻断；
- `decision_required` 例外：Agent 必须核对 `condition_key`；若例外实际触发，记录决定与证据后才采用 disposition；
- `conflict`：停止受影响的写入或提升，报告冲突 ID。只有结构化的 `conflicts_with`、`refines`、`depends_on` 或 `supersedes` 关系可用于解决，不得把互斥 effect 静默拼接。

执行时以返回的 `rules` 语义 envelope 为准，不只看 ID 或摘要；方法资料只在 `context_refs` 命中时读取。

### 3. 先判断恢复，再动现有项目

依赖既有项目状态时运行：

```bash
python3 -B scripts/assess_recovery.py --project-root "<项目根目录>"
```

- `R0_CONTINUE`：状态、登记工件和工作区一致；从下一合法动作继续。
- `R1_TARGETED`：变化可归属；只恢复变化 owner 及其传递消费者。
- `R2_FULL`：状态缺失/损坏、身份冲突、变化无法归属，或用户明确要求全量恢复；重建必要的全局证据。

用户明确的“完整/全量恢复”由原请求路由将 R0/R1 提升为 R2；不得反向降级。R0/R1 不得退化为每轮全文重读，自然语言交接不是权威状态。

### 4. 可写工作必须是一个可核验事务

项目状态的唯一载体是 `.modeling/state.json`。只有用户授权初始化项目且命中 `RT.PROJECT.INIT` 时才可以创建它：

```bash
python3 -B scripts/state_manager.py init --project-root "<root>" --project-id "<id>" --watch-root .
```

每次继续前先只读取得 revision、workspace manifest hash、recovery 和 component subject hash：

```bash
python3 -B scripts/state_manager.py inspect --project-root "<root>"
```

可写路由在任何项目或工件变更前必须登记唯一 execution：

```bash
python3 -B scripts/state_manager.py record-route \
  --project-root "<root>" --request "<原始请求>" --execution-id "<unique-id>" \
  [--component-id "<id>"] [--component-map '{"data":"data-main"}']
```

检查 execution 中的 `write_authorized`。若为 false，除非当前路由本身是已授权的 R1/R2 恢复，不得改变状态或工件；未授权 execution 的任何实际 delta 都会被结束回执拒绝。

只读请求不得调用 `record-route`，因为记录 execution 本身会写项目。只读回执使用 `execution_id=null`，且只在状态 revision 未变、无 delta 并仍为 R0 时验证通过。

开始和结束回执都使用 [receipt.schema.json](references/receipt.schema.json) 的唯一结构：

```bash
python3 -B scripts/validate_receipt.py --receipt "<receipt.json>"
python3 -B scripts/state_manager.py close-execution --project-root "<root>" --receipt "<end-receipt.json>"
```

回执文件放入系统临时目录，最终内容通常直接写入回复；不在项目内每轮生成回执文件。开始回执必须匹配重算后的 request hash、route/rule/component、state revision 和 recovery；结束回执必须匹配实际 revision、工件 delta、状态迁移和证据历史，且不可重放。

### 5. 先准入工件，再创建文件

正式文件创建前先提交 [artifact-contract.json](references/artifact-contract.json) 要求的 proposal：

```bash
python3 -B scripts/artifact_guard.py --project-root "<root>" --proposal "<proposal.json>"
```

合格 proposal 必须有真实 consumer、purpose、lifecycle、class、authorization basis 和 replacement 决定。默认项目控制面只有 `.modeling/state.json`；没有消费者的占位文件、空目录、重复清单、无需求 README、默认逐题 brief 和固定大脚手架不能通过准入。临时计算放系统临时目录；只登记已存在、身份可验证且有消费者的文件。

登记、验证、更新或替换工件只通过 `state_manager.py` 的对应子命令。新 identity 必须使生产者和所有传递消费者失效；不得用 checkpoint 洗白未归属变化。

### 6. 只记录类型化、绑定当前 identity 的证据

证据 JSON 必须精确包含 `id`、`level`、`status`、`kind`、`locator`、`claim`、`observed_at`、`producer`、`subject_id` 和当前 `subject_hash`。`inspect` 输出可用的 subject hash。字段多一个、少一个或 hash 陈旧都会失败。

- file locator：`path` + `sha256`；
- command locator：`command_hash` + `exit_code` + `output_ref` + `output_sha256`；通过证据的退出码必须为 0 且输出文件 hash 匹配；
- citation locator：`uri` + `accessed_at`；
- observation locator：`subject` + `method` + `value`；
- decision locator：`decision_id` + `recorded_at`，且该决定已在状态中 resolved。

```bash
python3 -B scripts/state_manager.py record-evidence \
  --project-root "<root>" --component-id "<id>" --evidence "<evidence.json>"
```

已关闭组件不能补写“旧证据”。重开 D3/A3/S7 必须用终态之后的新决定证据，旧 pass 证据转为 stale，新 epoch 的累积门禁必须重新满足。合法状态集和迁移门只从 [state-machine.json](references/state-machine.json) 读取，不从本文复制推断。

### 7. 以证据范围收尾

E1–E4 分别是实现、数值、结构和现实轴。S6 的实际关闭必须四轴强证据全部通过；实现验证不能代替模型验证。具体等级、门和累积条件以 state machine 为唯一 owner。

局部任务只闭合受影响组件和传递消费者；只有里程碑、发布或全项目结论才做全局闭合。退出码 0、编译成功、标题齐全、视觉相似或固定短语都不能单独证明正确。完成声称必须限于已通过的 effect、组件、证据等级和工件 identity。

## 领域闭环（由命中 atom 决定具体效果）

- 范围：区分给定、观测、推导、未知、目标、约束、验收边界和会改变结果的歧义。
- 外部证据：把关键主张绑定到已实际访问的来源；时变政策在执行当日核对官方来源，不用 Skill 中的旧年份信息。
- 数据：先登记身份和来源，再审计结构、缺失、异常、单位、时空口径、重复和泄漏；原始数据不可静默覆写。
- 建模与实现：先定义数学问题并比较可行候选/基线，再冻结变量、目标、约束、参数、单位、算法和失效条件；代码必须绑定冻结规格。
- 结果与稳健性：数值、图表和稿件主张绑定同一运行 identity；分开计算结果、解释和外推，报告敏感区、失效区和不确定性。
- 论文：主张—证据一致性先于文风；局部修改检查直接依赖，完整审计才覆盖全稿。
- 图表：验证渲染结果、数据 identity、坐标/单位、图例、可读性和导出边界；不只看源码宣称通过。
- 交付：只打包已声明、已验证且许可清晰的文件，排除缓存、临时产物、秘密信息和无法复现的外部资产。

## Skill 规则维护协议

只有用户明确要求新增、修改、拆分、合并、废弃或发布 Skill 规则时才进入 `skill_maintenance`：

```bash
python3 -B scripts/analyze_rule_change.py --request "<原始维护请求>"
```

维护是 base→staging→candidate→stable 事务，不是直接改稳定版。每个变更 envelope 必须绑定 base version/tree hash、目标 owner/revision/hash、旧行为、新行为、触发、例外和测试。工具根据实际 diff 计算最低风险，声明风险只能提高，不能低报。

变更必须同时完成：

1. 定位唯一 owner，检查同 target、作用域重叠、冲突、精化、依赖、替代和所有可达 route；
2. 生成对 rule、capability、effect target registry、route/event、state/Schema、解释器、测试和迁移证明的传递影响闭包；
3. 为目标 atom 添加真实原始语言正例、只改一个关键维度的近似反例、具名冲突例、状态绑定例以及 `ATOM.<RULE.ID>` 语义 envelope 断言；
4. 删除或反转被改 atom 时，至少一个目标测试必须失败；新行为必须至少区分一个 base/candidate 可观测结果；
5. 在隔离 staging 中运行非空 change eval、维护攻击场景和全发布门禁；任何失败丢弃 staging，不局部回滚稳定树；
6. L4 权限、路由、状态机、维护内核、MUST 弱化/删除只能进入新主版本 fork，不在 V10 原地发布。

不得把空测试集、未知 expected 字段、固定文字匹配、文件存在或“磁盘已改”当成行为生效证明。可用时，还要由重新加载 candidate 的独立 Agent 做前向测试；不可用时必须如实记录未验证边界。

## 发布门禁与关键契约

候选版本发布前运行：

```bash
python3 -B scripts/validate_release.py --root "<candidate/skills>" --v9-root "<skills_v9/skills>"
```

只有 package/contracts/behavior/atomic mutation/scenario/maintenance/change/real transaction/migration 全部由新进程执行、声明 case 与执行 case 完全核销、逐条款迁移封印有效、V9 源 hash 不变、候选树前后 hash 不变时才能 freeze。稳定版与旧主版本并列保留；安装/复制后还要在新进程重跑门禁。

- 规范所有权：[ownership-contract.json](references/ownership-contract.json)
- atom Schema：[rule-atom.schema.json](references/rule-atom.schema.json)
- effect target 封闭词表：[effect-target-registry.json](references/effect-target-registry.json)
- 路由/event：[route-contract.json](references/route-contract.json)
- 状态结构与迁移：[state.schema.json](references/state.schema.json)、[state-machine.json](references/state-machine.json)
- 工件准入：[artifact-contract.json](references/artifact-contract.json)
- 回执：[receipt.schema.json](references/receipt.schema.json)
- 规则变更：[change-envelope.schema.json](references/change-envelope.schema.json)
- 逐条款迁移保真：[clause-preservation.json](references/migration/clause-preservation.json)
- 发布 manifest：[release-manifest.schema.json](references/release-manifest.schema.json)
