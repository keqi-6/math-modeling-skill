# 论文图件、数据与重绘

本目录保存四问当前选用的8幅图，每幅均有PDF、SVG和PNG。文件名前缀对应逐问图号，论文连续编号由队伍统一。图按约15.8 cm宽制作，图片内部不另加论文式标题。PDF适合LaTeX，SVG便于矢量编辑，PNG便于兼容插图；时空色场包含栅格层，其坐标与标注为矢量。

| 图号 | 内容 | 修改入口 |
|---|---|---|
| 1-1 | 圆环控制体、径向节点与共享面 | Python：restructured |
| 1-2 | 径向与时间交点网格 | 原SVG |
| 1-3 | 五时刻径向剖面 | Python：core |
| 2-1 | 前三小时温度与含水率时空分布 | Python：fields |
| 2-2 | 扩散系数对数变化的升温项、失水项与净值 | Python：restructured |
| 3-1 | 21个规定半径的达标进程 | Python：restructured |
| 4-1 | 实测半径与材料坐标对应 | Python：coordinates |
| 4-2 | 同一厘米尺度的六个含水率截面 | Python：sections |

## 重绘

在支撑材料根目录运行（合并素材包中先进入support）：

```text
python -m pip install -r code/requirements_figures.txt
python code/redraw_figures.py --output redrawn_figures
```

默认生成除图1-2外七幅图的三种格式。`--only 1-3 2-1`选择部分图；`--font 字体文件路径`指定中文字体。原图使用Microsoft YaHei，不分发系统字体。跨平台字体或软件版本会影响文字布局，应按最终页内尺寸检查。重绘目录必须与随附原图分开。

`figure_data`保存未舍入的绘图数值：Q1五时刻×21半径、Q2前三小时逐秒×21半径、Q4六份完整径向快照；`radius_observations.json`保存题给半径节点。`restructured_figure_data.json`包含图2-2的六个主解状态及对数分解、图3-1各规定半径首个严格达标秒和全节点终点。来源、单位与提取口径随数据保存，文件校验值见`data_manifest.json`。图件说明与文件对应见`figure_manifest.json`。

如已有新的同格式结果，可以仅提取画图数据后重绘，无需再次求解：

```text
python code/extract_figure_data.py --q1 generated/q1.npz --q2 generated/q23.npz --q4 generated/q4.npz --output new_figure_data
python code/redraw_figures.py --data new_figure_data --output new_figures
```

三个输入参数均指定实际文件。提取器读取已有场值及全节点最大值，Q4需保存0、6、18、36、48 h和最终时刻的完整径向快照；半径观测改变时，以`--observations 新JSON路径`同步。程序只做数值摘取与一致性核对，不能验证替换后结果的物理模型。

## 图形含义

图1-1的圆环、径向控制体和图1-2的时空交点都是算法示意。显示节点数不等于实际网格数，时间层间距不代表固定步长；图1-1说明空间通量共享，图1-2说明隐式时间层中的关系。图1-2完整编辑源为SVG。

图2-2按附录3的指数本构精确分解主解沿程的对数变化；两项分别由实际温度与含水率变化计算，不是相互独立的因果效应，也不代表最终干燥时间的分项贡献。图3-1只显示题给21个半径的达标顺序，完整干燥终点仍取全部数值节点的最大含水率；提取时核对显示位置在首次达标之后没有越回阈值。

Q4材料环对应均匀径向收缩假设，不是内部位移观测；六截面按实际半径使用相同厘米尺度，圆外不填零，阈值虚线是含水率等值线。所有图注与正文解释由队伍合稿时统一。
