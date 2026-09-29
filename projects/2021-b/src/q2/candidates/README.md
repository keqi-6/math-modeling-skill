# 第二问候选诊断代码

本目录只保存S6候选充分性比较代码，不是正式求解实现。

- `01_compare_candidate_information.py`：在84个共同温度单元上比较加和分解与
  组合特异直线的信息压缩、参数规模和逐单元留一误差。
- `02_verify_candidate_information.py`：不导入候选主程序，独立复算平方和分解与
  闭合关系。
- `03_controlled_factor_sequences.py`：补齐队友提出的四条近似单因素对照序列和
  两组完全匹配装料方式比较，只生成候选证据。
- `04_verify_controlled_factor_sequences.py`：不导入候选主程序，独立复算对照合同、
  四温度均值、端点差、删温度方向、匹配配方差和产物哈希。

S7负责人决定前，这些结果不得替换S5基线、写入正式论文或作为最终模型输出。
