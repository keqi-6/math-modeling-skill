# 建模方案导航

问题一已完成 S3 方法决定，当前权威为：

- `planning/analysis/2026-08-23_q1_s3_approved_separate_sequential.md`；
- 数学继承与撤销审计：
  `planning/analysis/2026-08-23_q1_separate_sequential_contract_audit.md`。

批准结构是共同的有限总体无放回工具层，以及两个严格独立的单向序贯方案：情景 1 使用
`pi_R,T_R,W_R*(N)`，情景 2 使用 `pi_A,T_A,W_A*(N)`。两者不共用风险、停止时刻或
目标；`2/22` 仅保留为固定时点最早证书基线，联合错误与 `0.85N` 不属于当前方案。

问题一 S4 规格、S5 实现求解和S6验证均已由用户确认关闭，当前为
`S6_VERIFY/complete`。数学合同为
`planning/analysis/2026-08-23_q1_s4_separate_sequential_specification.md`。其中两个情景
分别采用上、下计数阈值；共同耦合已把风险和目标 ASN 的复合最坏点严格缩减到相邻整数
边界。当前实现见`src/q1/`，冻结基线与未验证结果见`output/q1/`，求解记录见
`planning/analysis/2026-08-23_q1_s5_implementation.md`。求解层同时报告可行上界、Bellman
对偶下界和间隙。用户已确认“有限闭合、及时止损”：代表批量以固定节点和墙钟预算执行
证书化分支定界，`N=10`两个情景已证明确定性阈值类全局最优，`N=23,50`在上限处保留
严格间隙；不得把后者写成已闭合。独立验证入口为
`planning/analysis/2026-08-23_q1_s6_independent_verification.md`；当前风险、ASN、宽类界、
V3、`N=10`完整枚举和`N=23,50`强化前沿界均已独立通过。完整队友讲解稿位于
`docs/q1/solution_brief.md`；旧稿不能让零基础成员就近理解公式，故旧表达审计保持失效。
当前稿已按正规论文职责链全文重建，并由
`planning/audits/2026-08-23_q1_solution_brief_reader_rewrite.md`完成逐段、逐式和数字复审；
人工门与S6关闭记录见`planning/audits/2026-08-23_q1_s6_closure.md`。问题二也已完成
S6关闭，当前冻结入口为`planning/audits/2026-08-24_q2_s6_closure.md`。问题三、问题四
也已完成实现、E1至E4、统一论文口径讲解稿与人工接受，四问现均为V11 `S7/closed`。
本文件不得
用S2基线或静态分层近似替代当前方法权威，实现若需改合同必须回到S4。
