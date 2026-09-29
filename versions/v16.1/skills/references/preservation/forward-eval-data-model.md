# V15 Candidate 独立前向行为评估：数据审计—模型比较—S6 readiness

## 结论

**总体：FAIL。**

领域方法包本身大多能指导 fresh Agent 正确处理统计单位、重复采样、零值/空白语义、异常候选、copy-on-write、简单基线、规格、独立验证和不确定性边界；分阶段加载也可以控制在每步 1–3 个包。但有一个发布阻断级冲突：方法文本允许“无数值风险的 E2”和“无现实 comparator 的 E4”不触发或记为边界，而 `VER.S6.DUAL_AXIS`、`state-machine.json` 和 `state_manager.py` 只接受 E1–E4 四类 `pass`。诚实记录 `not_applicable` 无法通过状态门，伪写 `pass` 又违背方法语义。另有 E4 路由耦合、只读处理候选不可精确路由、纯比较不触发 baseline atom、E3 菜单 atoms 过宽等问题。

本评估只读 `/mnt/c/Users/35190/skills_v15_candidate`；未读取 `/tmp/skill_v15_audit` 或主开发历史。实际共享表格、权威状态和项目文件未提供，因此真实数据结论与真实 S6 当前状态均为 **UNVERIFIED**；本报告评估的是 skill 在该请求上的前向行为。

## 读取范围与分阶段加载

完整读取了：

- `SKILL.md`；
- `references/route-contract.json`、`references/capability-packet-registry.json`、`references/semantic-plan.schema.json`、`references/runtime-policy.json`、`references/state-machine.json`，以及 `state.schema.json`/`state_manager.py` 中与 evidence status 和迁移有关的部分；
- 三个短路由：`references/data-method-notes.md`、`references/modeling-method-notes.md`、`references/verification-method-notes.md`；
- 请求实际命中的 8 个完整能力包：
  - `references/capability-packets/data/identity-and-audit.md`
  - `references/capability-packets/data/treatment-and-freeze.md`
  - `references/capability-packets/modeling/problem-and-candidates.md`
  - `references/capability-packets/modeling/mathematical-specification.md`
  - `references/capability-packets/modeling/implementation-solving-and-results.md`
  - `references/capability-packets/verification/implementation-axis.md`
  - `references/capability-packets/verification/model-axis.md`
  - `references/capability-packets/verification/uncertainty-and-robustness.md`
- `rules/data.json` 中本请求的 audit/treatment/identity atoms、`rules/modeling.json` 中 compare/spec/implement/results atoms、`rules/verification.json` 中 E2/E3/E4/S6/uncertainty atoms，以及 `rules/governance.json#STATE.TRANSITION.GATED`。

建议的 fresh Agent 分段如下；每个真实阶段最多 3 包，**PASS：没有一次性过载，也没有截断必需程序**。

| 阶段 | route / 动作 | 完整读取包 | 阶段边界胶囊 |
|---|---|---|---|
| A1 数据身份与审计 | `RT.DATA.AUDIT/audit`, `data_audit` | DATA.IDENTITY_AUDIT | 原始 identity、站点/月/行的统计单位、覆盖、重复键、0/空白语义、异常候选、未决问题 |
| A2 处理候选与人工确认 | 语义上是只读候选设计；见下述 route 缺口 | DATA.TREAT_FREEZE（同时复用 A1 当前审计结论） | 候选含“不处理”基线、偏差/方差/样本量/主张影响、人工选择；确认前不改数据 |
| B1 确认后处理 | `RT.DATA.TREAT/treat`, `data_treatment` | DATA.IDENTITY_AUDIT + DATA.TREAT_FREEZE | 已确认规则、新候选 identity、lineage、原始 hash 不变 |
| B2 候选比较 | `RT.MODEL.COMPARE/compare`, `model_comparison`；若真的选模才另有 `model_selection` | MODEL.PROBLEM_CANDIDATES | 同一数据 identity、候选域、评价指标和预算；简单基线与整数优化的实质差异 |
| B3 规格与实现 | `RT.MODEL.SPEC/specify`，再 `RT.MODEL.IMPLEMENT/implement/solve`、`RT.MODEL.RESULTS` | MODEL.SPECIFICATION；随后 MODEL.IMPLEMENT_RESULTS | 已确认选择、完整 spec identity、实现/run/result identity、禁止主张 |
| C 验证与 readiness | `RT.VERIFY.IMPLEMENTATION`、`RT.VERIFY.MODEL`、最后只读 `RT.VERIFY.S6.READINESS` | VERIFY.IMPLEMENTATION + VERIFY.MODEL；数据/结构不确定性实际命中时再加 VERIFY.UNCERTAINTY | E1–E4 applicability、oracle、证据 identity、边界；readiness 不等于 close |

`SKILL.md`“能力双层与无损渐进披露”、三个 `*-method-notes.md` 的“完整性边界”以及 `capability-packet-registry.json#loading_policy` 对这种分段是一致的。

## 数据行为

### PASS：统计单位和重复采样

证据：`references/capability-packets/data/identity-and-audit.md`，标题“先确定统计单位”。它要求先列实体、观测/实验单位、重复测量、时间/空间单元、批次和场景，再计算统计量，并明确警告不能把同一实体的多条记录当独立实体。对本例必须先判断“行”是重复采样、重复录入还是一个需保留的站点—月份内观测；不能仅凭 `(site, month)` 重复就去重。

`rules/data.json#DATA.AUDIT.DUPLICATE` 要求按业务键和记录语义检查，`DATA.AUDIT.SCHEMA`/`SEMANTIC_CONSISTENCY` 又约束键、单位和时空口径。atom 没有单独的 `statistical_unit` 字段，但完整包补足了实施程序；fresh Agent 依包执行可得到正确行为。

### PASS：结构性缺失、合法零值和空白未观测

证据：同一包标题“分开六种异常状态”，明确区分真正缺失、结构性不存在、审查/截尾、合法零、合理极端和解析错误；“审计图”还要求空白、零值和结构性不存在用不同编码。`DATA.AUDIT.MISSING` 检查 rate/structure/mechanism，`DATA.AUDIT.COMPLETENESS` 单独检查应有站点—月份覆盖。

因此近反例“把 0 全当缺失”应被拒绝：停运零值应保留其状态语义，空白作为未观测，除非权威字段定义另有说明；二者不能统一填补或删除。

### PASS：异常 candidate 不等于 authority

证据：同一包标题“分开六种异常状态”明确写明“异常算法只产生候选”，要求记录总体、分组、样本量、阈值、被标记录和失败条件；高价值/边界/稀有值不得仅因极端而删。`rules/data.json#DATA.AUDIT.ANOMALY` 的 target 也是 `anomaly_set`，证据字段为 `method/candidates/domain_bounds`。

### PASS：候选先行、人工确认、copy-on-write

证据：`references/capability-packets/data/treatment-and-freeze.md`，标题“候选先于正式接口”“不可变输入与显式转换”。删除、插补、纠正、合并、重编码等必须成组说明问题证据、含“不处理”的备选、偏差/方差/样本量/主张影响及消费者；人工确认后才成为正式接口。原始输入只读，新建候选 identity。

规范 atoms 也闭合：`DATA.AUDIT.BEFORE_TREATMENT`、`DATA.TREAT.DECIDE`、`DATA.IDENTITY.RAW_IMMUTABLE`、`DATA.TREAT.COPY`、`DATA.TREAT.LINEAGE`。因此确认前只审计/标记/提案，确认后批量执行获批规则，不逐行再问。

### FAIL：只读“提出处理候选”没有精确 route

`route-contract.json#RT.DATA.TREAT` 只允许 `mode=mutate`，动作 `clean/preprocess/treat` 都要求 `data_treatment`；没有 advisory/project_readonly 的 `propose_treatment` 动作。模拟 `object=data, action=treat, mode=project_readonly` 得到 `no_exact_route:data:treat:project_readonly`。而 `data-method-notes.md` 的完整性边界把“处理候选—人工决定”明确列为真实阶段。

可退回 `RT.DATA.AUDIT` 并把候选放在审计建议中，且人工方法文本仍能救场，但这会让候选阶段没有精确 route/atom 激活，和“route_step 为选择单元”不完全一致。

## 建模行为

### PASS：简单基线、候选、规格、实现与解释方法

`references/capability-packets/modeling/problem-and-candidates.md` 的“先建立简单基线”明确要求基线可手检并暴露复杂模型要修复的具体不足；不能因候选更复杂、更新颖、流行或内部指标略优就淘汰基线。“候选比较表”要求同题意映射、假设、数据支持、候选域、验证路径、失败风险、解释性、成本和最优性边界。

因此近反例“整数优化更先进所以胜出”在方法层 **PASS（被拒绝）**。必须在相同数据 identity、候选域、指标和预算下比较，且复杂模型只有在改善预定风险/主张边界时才胜出。

`mathematical-specification.md` 完整覆盖现实对象→集合/索引/变量、单位/域、目标与硬软约束、参数/边界、假设、候选域、I/O、失败信号、算法、验证 oracle 和禁止主张；`implementation-solving-and-results.md` 又要求实现绑定规格，明确穷举候选域和全局最优证明边界，并把结果分为计算事实、模型内含义、现实外推。相应 `MOD.SPEC.*`、`MOD.IMPLEMENT.*`、`MOD.RESULTS.*` atoms 基本一致。

### FAIL：纯 compare 不触发 baseline atom

对 `RT.MODEL.COMPARE/compare` + `events=[model_comparison]` 的 resolver 模拟只选择 `MOD.COMPARE.SAME_EVIDENCE` 和 `MOD.COMPARE.ASSUMPTIONS`（以及数据 identity/governance）；`MOD.COMPARE.BASELINE` 和 `MOD.COMPARE.RATIONALE` 的 trigger 都只有 `model_selection`。

本请求明确是“比较”两个模型，尚不一定发生“选择”。不能为了得到 baseline 规则而伪造 `model_selection` 事件。完整方法包仍会指导正确行为，但 atom 层对 compare-only 请求缺少“基线必须存在/复杂不自动胜出”的规范保护。

## E1–E4、误差与不确定性

### PASS：E1 和独立 oracle；拒绝自证循环

`references/capability-packets/verification/implementation-axis.md` 的“先写风险和 oracle”“E1：实现符合性”要求规格条款→实现路径→风险→输入→独立判据→主张，明确说退出码、哈希、重复同值和测试脚本自报通过不是 oracle；测试应直接读权威输入和正式输出，避免调用被测实现的同一辅助函数。

`data/identity-and-audit.md`“对账顺序”更直接写明“主脚本再次读取自己的输出也不是独立证明”；`data/treatment-and-freeze.md`“独立复核”禁止导入主处理实现或复用其解析函数。因此近反例“主脚本读自身输出自证” **PASS（被拒绝）**。

### FAIL（阻断级）：无数值风险的 E2 在方法、atoms、state gate 之间不一致

证据链：

1. `verification/implementation-axis.md` 标题“E2：数值或求解可信度”写明“E2 在存在数值风险时”；本例是确定性精确小规模枚举，无容差、离散近似、随机搜索或收敛风险。
2. `rules/verification.json` 中 `VER.E2.TOLERANCE` 的 N/A 是“精确离散结果”，`VER.E2.STABILITY` 是“非数值近似”，`VER.E2.CONVERGENCE` 是“精确离散计算且无迭代、近似或采样误差”，`VER.E2.NO_FORMAT_MASK` 是“没有数值近似结果”。这支持 E2 的 N/A 边界；但 `VER.E2.RECOMPUTE` 的 N/A 仅写“没有数值结果”，且所有 E2 atoms 都无 `numerical_risk_present` predicate。
3. `rules/verification.json#VER.S6.DUAL_AXIS` 要求 E1–E4 四类“通过证据”，无 justified-N/A 语义。
4. `references/state-machine.json`：`S5→S6` 强制 `E1_IMPLEMENTATION + E2_NUMERICAL`，`S6→S7` 强制 E1–E4。
5. `scripts/state_manager.py#current_evidence_levels` 只返回最新 `status == "pass"` 的 level；`do_transition` 用该集合计算缺失项。`not_applicable` 在 schema 中合法，但不满足迁移。
6. `rules/governance.json#STATE.TRANSITION.GATED` 的 effect 也是 `all_required_pass_evidence`。

所以 honest Agent 只能把数值 E2 记为 N/A，却永远不能通过 S5→S6；或者把“不存在风险”伪造成 E2 `pass`。两者都不合格。

### FAIL（阻断级）：无现实 comparator 的 E4 同样不一致且 route 不可达

`references/capability-packets/verification/model-axis.md`“E4：现实映射与用途确认”明确写明：没有实测、实验、留出观测或可靠现实基准时，E4 可以按题面理想用途记为不触发，但必须保留“现实适用性未确认”的边界，不能把 E3 升级成现实证明。

但：

- `route-contract.json#action_contracts/RT.VERIFY.MODEL/validate_model` 强制同时声明 `structural_verification` 和 `reality_verification`。模拟只想做结构验证、明确无 comparator 的步骤，会因缺少 reality runtime action 而报 `missing_runtime_action_for_event:reality_verification`；没有 E3-only 的 model-axis action。
- `VER.E4.ASSUMPTIONS/SCALE/PARAMETERS/MECHANISM/REALITY_FIT` 全部由 `reality_verification` 激活且 predicates 为空。尤其 `REALITY_FIT` 的 N/A 只允许“抽象演示且不作现实映射”；本例显然有站点需求决策的现实映射，只是没有外部 comparator。
- `VER.S6.DUAL_AXIS`、`state-machine.json` 和 `state_manager.py` 仍要求 `E4_REALITY` 为 `pass`，不接受“未触发但边界已登记”。

因此本例无法诚实达到 S6 ready/close。S6 readiness 本身作为只读 G0 route 是可达的，但应报告 **FAIL/NOT READY**，不是通过。

### FAIL：E3 方法说按风险选择，atoms 却把五项菜单全选

`verification/model-axis.md` 标题“从主张的实质失败风险选择检验”明确禁止每题机械做灵敏度、交叉验证或固定百分比扰动，并只要求每问至少一项针对核心风险的实质 E3。

然而 `VER.E3.CONSTRAINT/INVARIANT/LIMIT/COUNTEREXAMPLE/SENSITIVITY` 全是 MUST、同一 `structural_verification` trigger、predicates 为空、同一 route/state scope。按 `runtime-policy.json#activation`，一旦真的发生结构验证，五项全部选中。各自 N/A 条件可减少实际执行，但对有显式约束、可变需求和高影响决策的整数优化，本例至少 constraint/limit/counterexample/sensitivity 会同时成为硬义务；这比“按核心风险选择有信息增量的检验”更重。

因此近反例“所有 E3 菜单都机械执行”在方法文本上被拒绝，但在原子选择层 **FAIL（冲突）**。

### PASS：不确定性来源与主张边界（但不能修复 E2/E4 门禁）

`verification/uncertainty-and-robustness.md` 正确区分数据/观测、参数、结构和数值不确定性，禁止统一 ±5%/±10%，要求抽样单位匹配实体/区组/时间依赖，并区分固定方案代入与重新优化。

本例“无数值近似风险”只排除数值误差；重复采样身份、停运零值编码、未观测空白和获批处理方案仍可能造成数据/结构不确定性。正确做法是以站点（必要时站点整条月份序列）为依赖单位，对有依据的处理候选/情景传播，并在要声称“决策是否切换”时重新优化。`VER.UNCERTAINTY.SOURCES/PROPAGATE/BOUND` 与此一致。该包不能把缺失的 E2/E4 pass 变出来。

## 近反例汇总

| 近反例 | 判定 | 证据 |
|---|---|---|
| 把所有 0 当缺失 | PASS：明确拒绝 | DATA.IDENTITY_AUDIT“分开六种异常状态”“审计图”；DATA.TREAT_FREEZE 禁止结构性不存在与未知缺失统一插补 |
| 主脚本读自身输出自证 | PASS：明确拒绝 | DATA.IDENTITY_AUDIT“对账顺序”；DATA.TREAT_FREEZE“独立复核”；VERIFY.IMPLEMENTATION“E1” |
| 复杂模型因更先进而胜出 | PASS（方法）/FAIL（compare atom 覆盖） | MODEL.PROBLEM_CANDIDATES“先建立简单基线”；`MOD.COMPARE.BASELINE` 只在 `model_selection` 触发 |
| 所有 E3 菜单机械执行 | FAIL：方法拒绝但 atoms 全选 | VERIFY.MODEL“从主张的实质失败风险选择检验”；五个 `VER.E3.*` 同 trigger、空 predicates |

## 最小修正建议（按优先级）

1. **统一 axis closure 语义。** 为 E2/E4 定义类型化 `pass | justified_not_triggered_with_boundary | fail/stale`（或等价结构），并让 `VER.S6.DUAL_AXIS`、`state-machine.json`、`state.schema.json`、`state_manager.py` 使用同一 owner 语义。只能在明确 applicability 证据、理由和 claim boundary 齐全时把 justified-N/A 视为“axis closed”，不能把任意 N/A 当 pass。
2. **给 E2/E4 加实际适用性 predicate。** E2 至少区分 `numerical_or_search_risk_present`；E4 至少区分 `reliable_reality_comparator_available` 与仅题面理想用途。无 comparator 时要求边界记录，禁止现实适用性主张。
3. **拆开 model-axis action。** 增加 `validate_structure`（只要求 `structural_verification`）和 `assess_reality`（条件性 `reality_verification`），或把 `validate_model` 的双事件改成按事实选择，避免为 E3-only 验证伪造 E4 event/runtime action。
4. **补只读处理候选 route。** 在 data route 增加 `propose_treatment`/`design_treatment` 的 advisory/project_readonly 动作，加载两个 data 包但不声明 `data_treatment`、不写数据；实际 mutate 仍须人工决定。
5. **修正 compare 原子触发。** `MOD.COMPARE.BASELINE` 应同时由 `model_comparison` 激活；`RATIONALE` 可继续只在真实 selection 激活。增加“复杂/新颖本身不是胜出标准”的可验收 effect。
6. **收窄 E3 atoms。** 使用模型风险/结构 predicates，或以一个 umbrella atom 要求“至少一项可推翻核心主张的 E3 检验”，再由方法包选择 constraint/invariant/limit/counterexample/sensitivity，避免同一事件机械全选。

在第 1–3 项修复前，这个候选对题设场景的领域建议可用，但不能声称 S6 readiness 控制闭合。
