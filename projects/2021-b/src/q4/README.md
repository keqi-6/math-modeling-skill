# 第四问程序

- `01_build_formal_design.py`：按S8冻结规格生成正式五次实验、证据映射、观测后更新规则、
  条件序贯备选、摘要和产物清单；不生成未来实验响应。
- `02_verify_formal_design.py`：不导入S9实现，独立复核正式条件、配方、温度包围、职责、
  上游锚点、未来响应禁令、序贯预算和产物哈希。
- `03_robustness_and_explanation.py`：检查删去任一实验、替代政策和设备精度边界。
- `04_verify_robustness.py`：不导入S11实现，独立复核结构敏感性和哈希。

正式产物写入`output/q4/formal/`。S10通过前只标记为待验证设计。
