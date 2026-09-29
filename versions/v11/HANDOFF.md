# V11 运行时补丁交接（2026-08-24）

状态：V11.0.0 运行时补丁已完成并通过完整发布验证。`skills_v11/skills/` 是真实迭代副本，`v11_candidate_20260824/skills/` 保持同内容镜像；本补丁不触碰任何生产论文项目，也不以恢复或暂停为理由运行项目求解、实验或全量验证。

## 本次问题与修复边界

问题不在 206 条领域和论文规则本身，而在 V11 对运行时动作的触发与授权形式。补丁只收紧“什么时候可以触发重动作”，不降低论文书写、证据、模型、验证或交付规则的规范强度：

- R2 只恢复项目控制身份：读取、解析、比对、复用已有 identity，并写入 `.modeling/state.json` 或 `.modeling/recovery/`。R2 明确禁止求解、实验重算、执行型验证、论文推进和交付；恢复出有效状态后在同一轮重新解析原请求，不要求用户再发推进口令。
- “暂停、收尾、今天先到这里”固定为最高 `G1_WORKING`，且只允许 `handoff` 控制事件。不得借暂停触发 checkpoint、S6 验证、全项目审计、Skill 自检、求解器或结果重算。
- 普通工作、连续步骤和多文件 ChangeSet 不增加逐步授权、逐文件登记或 G1 执行账本。一个自然语言请求已经覆盖的连续动作可在同一轮完成，不得恢复“一步一卡”。
- 只有真正危险的运行时命令才使用显式动作授权和同进程执行包装器：项目模型执行、执行型验证、重算已有结果、Skill 定向/整包验证和全项目审计。控制动作不能推导这些命令，授权不能跨步骤、命令、项目根或恢复状态复用。
- `quick_validate.py` 只允许在明确的 Skill 审计、维护或发布上下文运行；生产项目的恢复、续作、暂停和普通收尾不构成 Skill 自检上下文。
- 旧 V9/V10 状态的缺失、损坏或旧结构输入改为总函数处理，不再因列表、空值或旧字段形状崩溃，也不会把旧状态误当成授权重跑实验的依据。

## 不得回退的负向约束

后续维护必须同时保留以下性质：

1. 不得为普通 G1 工作增加危险动作门、执行 ledger 或逐步用户确认。
2. 不得把通俗自然语言改造成标准口令要求，也不得要求“先关闭、再另发推进”。
3. 不得让 `pause` 高于 G1，或让暂停扩展到其他题目、组件、S6、验证、交付及全项目检查。
4. 不得让 R2 运行求解器、实验、重算、执行型验证或业务写入；R2 只恢复控制身份。
5. 不得以恢复、暂停或收尾为由运行 `quick_validate.py`、`validate_release.py` 或项目全量审计。
6. 不得通过修改 `rules/*.json` 获得流畅性；九个冻结规则文件继续与 V10 字节一致。

## 验证结果

- 完整发布门：9/9 驱动、561/561 声明断言通过。
- 分项：quick package 10/10、contracts 4/4、V10 corpus 3/3、behavior 36/36、atomic 206/206、scenario 35/35、maintenance 33/33、migration 6/6、forward acceptance 22/22。
- 新增实执行回归包括：R2 同计划阻断求解、有效状态后同轮续作、暂停 G2/G3 升级被拒、Q3 关闭后同轮暂停且不触碰 Q4、危险命令只执行一次、未授权命令零执行、Skill 自检缺失上下文时在扫描前失败。
- V9/V10 基线树在验证前后均未变化；九个 `rules/*.json` 未修改，206/206 活跃规则保持可达。
- 补丁 Skill 树：75 个文件，SHA-256 `9b6d6100f7d88965766b62ae204a01357b4d577329bb18988ccd7306e0c7f4db`。
- 发布报告自校验 SHA-256：`7d5e1dddfcf0cdd85a1e713e9970dafca64a558b685582baec4266363f01b136`。

完整报告文件：`release-validation-runtime-patch-20260824.json`。

## 已知边界

自然语言语义仍由 Agent 理解，精确请求摘录用于绑定危险动作授权，但不能独立证明语义理解正确；因此运行时继续依赖代表性正例、反例与混合计划回归，不能引入关键词口令解析器来替代语义判断。

---

## 追加：跨窗口 R0 缺陷修复（2026-08-25）

### 问题

V8 明确：`R0_INCREMENTAL_CHECKPOINT` 只允许 same uninterrupted session；`R1_HASH_DELTA_RECOVERY` 用于 new window or context recovery。V9→V10→V11 在迁移中丢掉了“新窗口至少 R1”的约束，导致跨窗口续作时只要 `.modeling/state.json` 一致就错误返回 `R0_CONTINUE`。

### 修改点（本工作副本）

- `references/semantic-plan.schema.json`：新增顶层 `window_context`；含 `recovery_assessment` 的计划必须声明它。
- `references/runtime-policy.json`：新增 `window_recovery_policy`，`new_window_minimum_level=R1_TARGETED`，`unknown_default=new_window`。
- `references/route-contract.json`：`semantic_plan_policy.window_context` 声明 R0 仅限 `same_window`。
- `scripts/assess_recovery.py`：新增 `new_window` 参数；状态一致时若为 new window 返回 `R1_TARGETED`，不再给 R0。
- `scripts/lib_v11.py`：从 `window_context` 推导 `new_window` 并传给恢复评估；缺省视为 new window。
- `scripts/validate_contracts.py` / `scripts/run_maintenance_tests.py`：校验该策略，防回归。
- `evals/behavior-cases.json`：原 R0 用例显式声明 `same_window`；新增 new-window 必须 R1 的用例。
- `evals/runtime-policy-cases.json`：新增 mutation 用例，禁止把 new window 最低级别改成 R0。
- `scripts/run_scenario_tests.py`：内部 recovery plan 补 `window_context`。

### 验证

在 `/home/ke_qi/deepseek/v11_work_20260825/skills` 上运行完整发布门：

- 9/9 驱动通过
- 563/563 声明断言通过
- quick 10/10、contracts 4/4、v10 corpus 3/3、behavior 37/37、atomic 206/206、scenario 35/35、maintenance 34/34、migration 6/6、forward 22/22

### 注意

D 盘当前以只读方式挂载，无法直接写回 `D:\...\总skill\skills_v11`。本工作副本在 `/home/ke_qi/deepseek/v11_work_20260825/`；如需落地，请从该目录把 `skills/` 同步回 `skills_v11/skills` 与 `v11_candidate_20260824/skills`，并重新生成 release report。

---

## 追加：P0 生产安全补强（2026-08-25 第二轮）

### 修复内容

1. **危险事件强制 runtime_actions**
   - `model_execution`、`implementation_verification`、`numerical_verification`、`structural_verification`、`reality_verification`、`robustness_analysis`、`uncertainty_analysis`、`release_candidate_validation` 必须至少绑定一个对应 `runtime_actions`，否则 step 直接 blocked。
   - 这不是用户交互门禁，Agent 在同一 semantic plan 内自动声明即可。

2. **新窗口/未知窗口续作必须带 recovery_assessment**
   - `window_context != same_window` 时，`resume`/`recover`/`handoff` 必须声明 `recovery_assessment`，否则 blocked。
   - 这样“继续”不会静默跳过恢复；但仍可同一轮完成“恢复 + 后续步骤”。

3. **R1 工作区轻量基线**
   - 新增 `state.watch_roots` 与 `state.workspace_baseline`（可选字段）。
   - `state_manager init` 默认建立基线；已有项目可用 `state_manager update-baseline` 补建。
   - `new_window` 恢复时对比基线，普通文件的 added/modified/deleted 也会进入 `changed_paths`，不再只查受保护 identity。
   - 没有基线时 new_window 至少 R1，不会错误 R0。

### 验证

完整发布门在 `/home/ke_qi/deepseek/v11_work_20260825/skills` 通过：

- 9/9 驱动通过
- 564/564 声明断言通过
- quick 10/10、contracts 4/4、v10 corpus 3/3、behavior 38/38、atomic 206/206、scenario 35/35、maintenance 34/34、migration 6/6、forward 22/22

---

## 追加：open decision 与中断前检查点补齐（2026-08-25 第三轮）

### 新增命令

```bash
# 新增待确认决定，只写 .modeling/state.json
python3 -B skills/scripts/state_manager.py add-open-decision \
  --project-root <root> \
  --decision-id DEC-003 \
  --subject "Q3 最终方案选择" \
  --option A3-400 --option A2-325 \
  --affects q3

# 解决待确认决定
python3 -B skills/scripts/state_manager.py resolve-open-decision \
  --project-root <root> \
  --decision-id DEC-003 \
  --selected A3-400

# 上下文压缩/中断前写控制检查点，仍只写 .modeling/state.json
python3 -B skills/scripts/state_manager.py checkpoint-before-interrupt \
  --project-root <root> \
  --reason "context window near limit"
```

### 验证

- 新增 2 个 scenario 用例：
  - `V11.OPEN_DECISION.LIFECYCLE`
  - `V11.CHECKPOINT.BEFORE_INTERRUPT.SINGLE_FILE`
- 完整发布门通过：
  - 566/566 断言
  - 9/9 驱动
  - scenario 37/37
