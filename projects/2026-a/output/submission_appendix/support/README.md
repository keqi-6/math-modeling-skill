# 数值计算程序与原始输入

使用 Python 3.12，在本目录运行：

```text
python -m pip install -r code/requirements.txt
python code/run_models.py --case all --output recomputed
```

程序按相同的一维径向有限体积离散和分段 BDF/NDF 积分重算四问。`q1_model.py`分别计算问题一两场；`q23_model.py`联合计算附录3两场，导出问题二前三小时以及问题三全域达标结果；`q4_model.py`采用附录4与观测半径的材料坐标模型。`common.py`读取原始附件并统一单位，`export_results.py`依据原模板填写工作簿。

默认问题一5120个径向等分，问题二至四10240个径向等分。环境观测之间采用分段线性插值；问题三、四在4小时后使用最后1小时的时间均值，半径在观测之间采用线性插值。温度和含水率均按规定保留四位小数，计算与阈值判断使用未舍入值。

随包的`results/`保留已有参考表格；默认重算写入独立的`recomputed/`目录，不覆盖参考文件。

单独计算及已有对照设置：

```text
python code/run_models.py --case q1 --output results_q1
python code/run_models.py --case q23 --output results_q23
python code/run_models.py --case q4 --output results_q4
python code/run_models.py --case q23 --n 5120 --tight --output results_grid
python code/run_models.py --case q4 --radius pchip --output results_pchip
python code/run_models.py --case q4 --tail last_value --output results_last
```

每次使用新的输出目录。`--n`用于径向网格对照，`--tight`收紧已有时间精度设置，`--tail last_value`和`--radius pchip`只用于相应对照计算；不应与默认方案混报。`--radius constant`可作固定半径几何对照，其输出可能在72小时观测范围内尚未达标，此时程序不会生成成功结果。程序不覆盖现有结果；单次命令总墙钟限时3300秒，`--case all`中的各问共享此预算，超时停止。重算时间受计算机性能影响。

输出包括未舍入场值`q1.npz`、`q23.npz`、`q4.npz`及相应参数记录，并生成：

| 文件 | 内容 |
|---|---|
| result1.xlsx | 问题一1～1800秒，每秒、每0.1 cm的温度与含水率 |
| result2.xlsx | 问题二1～10800秒，每秒、每0.1 cm的温度与含水率 |
| result3.xlsx | 问题三每60秒及结束时刻、每0.1 cm的含水率 |
| result4.xlsx | 问题四每60秒及结束时刻的含水率；固定位置域外留空，实际表面独立列出 |

输入位于`data/附件1.xlsx`、`data/附件2.xlsx`，时间单位均为秒，附件2半径厘米转换为米。`data/templates/`保存四个原始输出模板。所有路径均相对本目录，可整体移动后运行。程序只依赖公开的NumPy、SciPy、openpyxl及Python标准库。

如需重新绘图，另安装`code/requirements_figures.txt`中的依赖，并按`figures/README.md`中的说明使用随包数据或新计算的NPZ绘制。图件目录另附可编辑的SVG示意图。
