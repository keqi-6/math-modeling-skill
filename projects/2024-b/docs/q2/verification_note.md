# 问题二 S6 独立验证复现说明

本文件只说明验证程序怎样复现，不是问题二解答正文或正式论文。

## 输入与输出

独立验证入口为`src/q2/02_verify_independent.py`。它直接读取：

- `planning/analysis/2026-08-23_q2_s2_assessment.md`中的六行情景参数；
- `planning/analysis/2026-08-23_q2_s4_specification.md`中的批准合同；
- `output/q2/s5_results.json`，但只在独立结果形成后用于逐字段对账。

程序写出：

- `output/q2/s6_independent_verification.json`；
- `output/q2/s6_independent_verification_manifest.json`。

## 隔离与运行

验证程序只导入Python标准库，不导入`src/q2/core.py`、`src/q2/01_solve.py`或它们的任何
函数。主路线使用精确几何更新闭式式，不复用生产实现的有限状态高斯消元。

在项目根目录运行：

```bash
python3 -B src/q2/02_verify_independent.py
```

随机性为`none`，所有核心计算使用`Fraction`。显示小数不参与门判定、排序或并列判断。

## 证据职责

结构化结果记录96条候选的930个精确字段比较、336项流量和费用不变量、V1至V4身份、
退化边界以及零件联合质量边界内的连续重新优化。运行清单冻结输入、验证代码、输出、
环境和维度哈希。

这些产物用于S6技术审计、队友讲解稿和主张映射。它们不构成真实工厂实验验证，也不
自动批准S6关闭或正式论文。
