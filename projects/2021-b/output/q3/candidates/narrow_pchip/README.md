# 第三问S6窄插值候选

本目录只保存同一已有组合自身实测温度区间内的PCHIP插值候选证据。

- `interior_holdout_predictions.csv`：72次内部遮点的局部直线与PCHIP预测；
- `missing_325_candidate_predictions.csv`：11个未测325摄氏度单元的候选预测；
- `temperature_ranking_checks.csv`：各内部温度的最高候选与前三名检查；
- `summary.json`：候选误差、低温推荐影响和边界；
- `verification.json`：8项独立复算。

候选预测不是观测值，不得在S7决定前进入正式第三问结果或论文。
