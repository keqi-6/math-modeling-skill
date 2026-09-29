# 《59初稿》表图—代码映射

本文档把 `<未收录-队友材料>/59初稿.pdf` 的17张表和3张图映射到真实生产者。机器产物保存
完整精度，论文负责显示舍入。

| 稿件对象 | 生产脚本 | 冻结产物 | 验证 |
|---|---|---|---|
| 表1 分组回归总体统计 | `src/q1/05_manuscript59_tables_figures.py` | `output/q1/manuscript59/table1_overall_linear_summary.csv` | 新增2/2的一部分 |
| 表2 各组合回归参数 | `src/q1/01_question1_analysis.py` | `output/q1/tables/attachment1_linear_summaries.csv` | 既有19/19 |
| 表3 留一预测误差 | `src/q1/03_manuscript59_loo_prediction.py` | `output/q1/manuscript59/table3_loo_summary.csv` | 新增4/4 |
| 表4 每10分钟变化 | `src/eda/01_discrete_eda.py` | `output/eda/tables/attachment2_interval_changes.csv` | 既有10/10 |
| 表5 产物首末变化 | `src/q1/01_question1_analysis.py` | `output/q1/tables/attachment2_selectivity_summary.csv` | 既有19/19 |
| 表6 公共温度配对变化 | `src/q2/01_common_temperature_baseline.py` | `output/q2/tables/common_temperature_paired_change_summary.csv` | 既有5/5 |
| 表7 两指标平均排名 | 同上 | `output/q2/tables/common_temperature_rank_stability.csv` | 既有5/5 |
| 表8 相邻温度秩相关 | 同上 | `output/q2/tables/common_temperature_rank_pair_summary.csv` | 既有5/5 |
| 表9 组合偏差排序 | `src/q2/03_additive_effects.py` | `output/q2/tables/additive_combination_effects.csv` | 既有13/13 |
| 表10 双因素差异分解 | 同上 | `output/q2/tables/additive_decomposition.csv` | 既有13/13 |
| 表11 结构删除范围 | `src/q2/05_structural_robustness.py` | `output/q2/tables/robustness_leave_combination_out.csv`及`robustness_leave_temperature_out.csv` | 既有9/9 |
| 表12 一般情景实测前六 | `src/q3/03_formal_solution.py` | `output/q3/formal/d0_rankings.csv`中`general`前六 | 既有10/10 |
| 表13 严格低温实测前五 | 同上 | 同一文件中`strict_below_350`前五 | 既有10/10 |
| 表14 分量PCHIP缺口前五 | `src/q3/07_manuscript59_component_pchip.py` | `output/q3/manuscript59/table14_component_pchip_top5.csv` | 新增5/5 |
| 表15 三种插值缺口核查 | 同上 | `output/q3/manuscript59/table15_method_sensitivity.csv` | 新增5/5 |
| 表16 三种插值遮点误差 | 同上 | `output/q3/manuscript59/table16_holdout_metrics.csv` | 新增5/5 |
| 表17 五次补充实验 | `src/q4/01_build_formal_design.py` | `output/q4/formal/experiment_design.csv` | 既有12/12 |
| 图1 标准化相邻变化 | `src/q1/05_manuscript59_tables_figures.py` | `output/q1/manuscript59/figures/figure1_standardized_adjacent_changes.*` | 新增2/2的一部分 |
| 图2 删点斜率范围 | 同上 | `output/q1/manuscript59/figures/figure2_leave_one_out_slopes.*` | 新增2/2的一部分 |
| 图3 时间指标与产物组成 | 同上 | `output/q1/manuscript59/figures/figure3_attachment2_time_changes.*` | 新增2/2的一部分 |

统一重跑入口为 `python3 -B src/run_manuscript59_pipeline.py`。入口按依赖顺序重跑真实
生产者和独立验证，任何一步失败立即停止。第四问只重建设计，不生成未来实验响应。

