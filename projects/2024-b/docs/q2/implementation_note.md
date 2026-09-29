# 问题二 S5 复现说明

> 身份：S5实现复现材料，不是队友讲解稿、独立验证报告或论文正文。

## 输入与职责

`src/q2/01_solve.py`直接解析
`planning/analysis/2026-08-23_q2_s2_assessment.md`中的冻结表1接口，并按已批准的
`planning/analysis/2026-08-23_q2_s4_specification.md`调用`src/q2/core.py`。

核心程序生成每个情景的全部16种四元方案，先作硬可行性判定；只对可行方案求精确事件
期望、成本和利润。状态方程使用Python标准库`Fraction`做精确有理数高斯消元，不使用
随机数、循环截断、数值容差、伪逆或启发式搜索。

## 复现命令

在项目根目录执行：

```bash
python3 -B src/q2/01_solve.py
```

程序生成：

- `output/q2/s5_results.json`：六情景、96个候选记录、最优集合及S5同实现检查；
- `output/q2/s5_run_manifest.json`：输入、规格、代码、输出哈希和运行环境。

## 结果身份

S5输出本身保留`s5_frozen_unverified`生产身份；后续独立验证不会回写或改名该原始产物。
当前S6验证身份见`docs/q2/verification_note.md`和
`output/q2/s6_independent_verification.json`。即使S6技术检查通过，也不能自动写成现实
有效性或未经人工批准的论文结果。
