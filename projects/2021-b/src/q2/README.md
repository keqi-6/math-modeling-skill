# 第二问代码

- `01_common_temperature_baseline.py`：S5描述性基线，只计算共同温度配对、同温分布、
  排名稳定性和匹配补充，不拟合正式影响模型。
- `02_verify_common_temperature_baseline.py`：从清洁数据独立复算覆盖、配对计数、分布和
  增量。
- `03_additive_effects.py`：按S8规格实现正式B层加和分解、表格、图件、摘要和清单。
- `04_verify_additive_effects.py`：不导入正式程序，独立复算S8规定的10组验证命题。
- `candidates/`：S6隔离候选诊断与独立核对，不是正式求解模型。

正式方法由两层组成：A层直接比较同一组合的温度变化和同一温度的组合差异；B层将
观测拆成总体水平、组合平均偏差、温度平均偏差和未解释变化。代码中的“加和分解”
是标准技术名称，正文先用上述普通语言解释其计算含义。

`05_structural_robustness.py` 与 `06_verify_structural_robustness.py` 分别执行和独立
复算整组、整温度删除检查。候选目录不得导入正式实现。
