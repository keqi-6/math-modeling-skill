# 第一问程序

- `03_manuscript59_loo_prediction.py`：生成《59初稿》表3的228次留一预测和三级汇总。
- `04_verify_manuscript59_loo_prediction.py`：不导入主程序，独立复算并核对显示值。
- `05_manuscript59_tables_figures.py`：按底稿口径生成表1和图1—3。
- `06_verify_manuscript59_tables_figures.py`：核对表1舍入值与六个图件文件。
- `01_question1_analysis.py`：生成离散变化、42组受限线性概括及决定系数、后台辅助
  诊断、228次逐点删除稳健性、附件2时间概括和六种图；其中图5综合表达逐组斜率、
  决定系数和局部例外。
- `02_verify_question1.py`：不导入主脚本，重新读取输入并完成19项独立核对。

输入只来自 `output/data_audit/tables/` 中已核对的数据，输出写入 `output/q1/`。
程序不做高阶曲线、普通显著性推断或未测条件预测。
