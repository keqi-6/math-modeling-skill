# Verification and model-examination quality

Apply this file after an implementation or claim exists and the controller permits `S6_VERIFY`.

## S6双轴最低合同

每问建立并分别关闭：

1. `solution_verification`：V1实现符合性；存在数值近似、离散、迭代、搜索、容差或舍入
   风险时，再完成V2数值解验证。
2. `model_examination`：V3模型结构检验为强制出口；V4现实模型确认只在存在实测、实验、
   留出观测或可靠外部基准时触发。缺少这些证据时，V4可按题面理想用途记为
   `not_triggered`，但必须写明现实域未确认。

V3没有`not_triggered`状态。它必须从本问模型主张识别实质失败风险，并至少完成一种能够
击中该风险的量纲/不变量、退化/极限、对称/守恒、单调/边界、已知解、反例、约束消融、
支配/排序反转或其他等价结构检验。纯哈希、字段对账、再次代入同一公式、另一实现同值和
一句“符合常识”均不能单独关闭V3。

## V1/V2 solution verification

- Recompute critical inputs, constraints, objectives, rankings, and headline values independently
  of the primary summary.
- Verify manifests, hashes, dimensions, units, tolerances, and producer identities.
- Test a small case by hand or exhaustive enumeration when feasible.
- Treat agreement with another implementation as corroboration, not proof of global optimality.

This agreement also does not prove model adequacy or real-world confirmation.

## V3/V4 risk-matched model examination

Choose tests for the actual failure mode:

- parameter sensitivity for policy or calibration dependence;
- deletion, resampling, or perturbation for sampling fragility;
- alternative baselines for method dependence;
- constraint relaxation or tightening for feasibility dependence;
- holdout or blocked validation for prediction;
- rank, confounding, or identifiability diagnostics for effect claims;
- boundary and adversarial cases for algorithms.

Also choose model-structure tests by model family: geometric or physical models need necessary
invariants, limits, symmetries, conservation, feasible intersections, or known cases; optimization
models need feasibility, bounds, constraint counterexamples, or decision-switch checks; predictive
models need baselines and holdout/calibration evidence; inferential models need identification,
confounding, distributional, or residual diagnostics. This menu is not a fixed quota.

For every test state the object, operation, criterion, result, and proof boundary. A failed test
must reopen the earliest affected state; do not conceal it by weakening prose.

For V3, the recorded operation must also name the mathematical relation or necessary model property.

For every question maintain `model claim → structural failure risk → V3 test → criterion → result
→ proof boundary → intended paper location`. The evaluator-visible paper must show at least one
substantive model examination for each question, without requiring a same-named section. Internal
engineering checks do not satisfy this paper-visible minimum.

正式论文每一问至少展示一项有实质信息增量的模型检验；本要求检查逐问证据可见性，
不要求设置同名章节或采用统一检验方法。

## Claim strength

Keep numerical correctness, model adequacy, stability, statistical uncertainty, causal meaning,
optimality, and real-world feasibility separate. State what each check proves and does not prove.
V1/V2 agreement cannot close V3 or V4; V3 structural success cannot be written as V4 real-world
confirmation.
