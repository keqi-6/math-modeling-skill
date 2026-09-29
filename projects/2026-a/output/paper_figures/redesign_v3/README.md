# 图件重设计候选稿

本目录回应2026-09-11的配色、图形重复、去文字可读性和三维示意图意见。用户已确认“图不错，可以先保留并入到队友讲解稿中”。三张图现已并入Q2、Q4的唯一讲解稿：Q2图2-1为剖切、图2-2为时空图；Q4图4-2为六截面序列。图源文件名沿用原路径，避免改名造成引用断链；sources.json保留生成当时的候选身份记录。最终论文的编排由队伍负责。

## 直接查看

- `redesign_review.pdf`：上一轮供用户选图的15.8厘米版心样稿；当前逐问解释以`docs/Q2/solution_brief.md`、`docs/Q4/solution_brief.md`为准。
- `redesign_review.tex`：可修改的LaTeX排版源，使用同目录图件，XeLaTeX编译。
- `fig_mechanism_cutaway.pdf/png/svg`：真实三维网格的中部短段剖切，剖面用Q2已有0.5小时含水率着色。
- `fig04_q2_fields_sample.pdf/png/svg`：Q2暖色温度与蓝色含水率时空图。
- `fig07_q4_sections_sample.pdf/png/svg`：Q4同尺度六截面，突出外形收缩与未达标区域的退缩。
- `cutaway_textfree.png`、`fig04_q2_fields_textfree.png`、`fig07_q4_sections_textfree.png`：隐藏文字的内部审看版本，不作为论文插图。

三维图的SVG/PDF是混合格式：几何为高分辨率渲染图，文字和色标为矢量；Q2色场为栅格，轮廓线和标签为矢量；Q4的圆盘色场与轮廓为矢量。不要将三个图一概称为全矢量图。

## 图件分工与约束

Q2展示空间与时间的温湿响应差异；Q3保留全程曲线及阈值终点；Q4用截面序列展示变化边界及内部场，不重复承担Q3曲线的职责。剖切图用于问题二结果段，承接0.5小时的摘要数值，不能将其变物性耦合背景原样泛用到问题一。

三维图沿长度方向只是展示中部短段，不表示新增三维求解。外壁灰色仅区分几何面，不代表附加壳层。红、蓝箭头分别表达所选时刻的热量传入和水分迁出，长度不编码通量。Q4的0.15虚线仅为含水率等值线，不是相界面。

全部含水率图使用同一线性0～2.55 kg/kg色标。后期颜色差异较小是这种可比尺度下的真实表现，未逐帧拉伸颜色。Q4圆外透明，各帧均按相同厘米尺度绘制，未将收缩后的截面重新放大填满面板。

## 编辑与复现

从项目根目录运行：

```powershell
.\.venv\Scripts\python.exe -B scripts/build_q2_field_sample.py
.\.venv\Scripts\python.exe -B scripts/build_q4_section_sample.py
.\.venv\Scripts\python.exe -B scripts/prepare_cutaway_data.py
& '~/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' scripts/render_cutaway.cjs
```

三维几何、材质、光照及相机在本目录`cutaway_scene.html`；图例与导出尺寸在`../../../scripts/render_cutaway.cjs`。该脚本使用本机Edge无头模式、捆绑Playwright和本地固定Three.js 0.180.0，不依赖在线页面。Three.js模块及MIT许可证保存在`../../../scripts/vendor/three`；依赖来自官方npm包且已核验完整性。

从本目录编译排版：

```powershell
& 'D:/latex/texlive/2026/bin/windows/xelatex.exe' -interaction=nonstopmode -halt-on-error redesign_review.tex
```

正式维护时可把编译中间文件输出到临时目录。生成图只读取已有结果，不调用求解器。

## 数据与审看记录

- `cutaway_data.json`及`cutaway_sources.json`：完整径向数据、来源哈希、显示规则、三维网格参数与导出身份。
- `q2_sample_sources.json`：Q2采样、色标、显示内插、等值线及导出身份。
- `q4_sample_sources.json`：Q4各帧实际半径、中心/表面含水率、阈值内圈半径及导出身份。
- `../../../planning/visual_redesign_review.md`：本项目去文字检查、新图分工、工具选择及本轮检查结果。

外部截图只作为内部构图启发；本目录所有数值和物理判断均来自本项目已有模型与结果。图中无外部答案数据。
