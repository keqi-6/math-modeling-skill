# 第一问候选方法代码

本目录只保存未被批准为主体模型的比较代码，不改变 `src/q1/01_question1_analysis.py`
和现有冻结结果。

- `01_compare_theilsen.py`：按队友公式计算Theil–Sen斜率，并与现行最小二乘结果比较。
- `02_verify_theilsen_comparison.py`：独立复算42组斜率、留一方向，并用SciPy实现交叉核对。
