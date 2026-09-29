# 问题一 S4：完整动作空间规格关闭审计

## 关闭对象

问题一在 `Q1-FULL-ACTION-REDESIGN-20260825` 重开后，从 `S3` 迁移至 `S4`
的规格阶段关闭。规格权威为
`planning/analysis/2026-08-25_q1_s4_complete_action_specification.md`。

## 用户授权

负责人 2026-08-25 在审阅规格要点后明确选择"确认规格，进入 S5"，授权冻结该数学
合同并开始 S5 实现。授权记录于本轮对话；机器侧由 `Q1-COMPLETE-ACTION-SPEC-20260825`
（model_spec）与 `Q1-COMPLETE-ACTION-SELECTION-20260825`（selection_rationale）
证据承载。

## 规格要点（冻结内容）

1. 输入 `N`、`p0=0.1`、`D0=floor(N/10)`、`D1=D0+1`；无放回随机检测，状态 `(t,x)`。
2. 零风险事实动作（两情景共用，不占统计错误预算）：
   - 事实拒收：`x >= D1`；
   - 事实接收：`x + (N-t) <= D0`。
3. 情景 R：上阈值 `r_t ∈ {0,...,min(t,D0)} ∪ {t+1}`，统计拒收 `x >= r_t`，
   风险 `max_{D<=D0} P_D(提前拒收) <= 0.05`，目标 `min max_{D>=D1} ASN(D)`。
4. 情景 A：下阈值 `a_t ∈ {-1} ∪ {max(0, t-(N-D0)+1),...,min(t,D0)}`，统计接收
   `x <= a_t`，风险 `max_{D>=D1} P_D(提前接收) <= 0.10`，目标
   `min max_{D<=D0} ASN(D)`。
5. 事实动作优先于统计阈值；首次 A/R 后停止；`t=N` 为事实终点。
6. 精确有理数概率流，四类概率质量守恒；目标侧最坏点仍为 `D1`/`D0`；全 D ASN
   不再声称单调。
7. 求解用可行阈值候选、坐标改进、拉格朗日 Bellman 下界与有限分支定界；上下界相等
   只声明新规范阈值类最优；不移植旧证书。
8. 必过测试：`(9,9)` 不可继续、`(9,0)` 立即事实接收、事实动作零错误预算、
   `N∈{1,2,3,9,10,20,23,50}` 概率守恒与全 D 曲线、独立验证器不导入主核心并完整
   枚举 `N=10`。

## 失效边界

旧单向动作空间（R/C、A/C）的 gap、全 D ASN 单调性与相关证书在新求解完成前失效。
问题四作为登记消费者保持 invalidated，待问题一新结果闭合后定向重验；问题二、三
不受影响。

## 机器状态

- `.modeling/state.json` revision 65：q1 组件 `S4/active`；
- 登记工件：`planning/analysis/2026-08-25_q1_s4_complete_action_specification.md`
  （role control，frozen）；
- 证据：`Q1-COMPLETE-ACTION-SELECTION-20260825`、
  `Q1-COMPLETE-ACTION-SPEC-20260825` 均 pass；
- G1、G2 校验均 pass。
