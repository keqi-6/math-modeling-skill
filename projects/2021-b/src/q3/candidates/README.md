# 第三问隔离候选

本目录只保存第三问正式方法决定前的可行性审计代码。

- `01_unified_model_feasibility.py`：以三类分块外层任务比较局部基线、共享组合曲线和
  配方因素曲面；正则强度只在外层训练数据内选择。
- `02_verify_unified_model_feasibility.py`：不导入主程序，独立复算误差与外层分块结构。
- `03_narrow_pchip_candidate.py`：只在同一组合自身实测区间内比较局部直线与PCHIP。
- `04_verify_narrow_pchip_candidate.py`：独立复算72次遮点、11个325摄氏度缺口和排名。

这里的运行结果不得直接进入论文、正式第三问输出或推荐结论。
