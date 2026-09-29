# 传热传质机理示意图候选稿

本图用于解释问题二、三中“局部物性耦合—内部径向传递—侧表面交换”的对应关系。为待用户审阅的单幅样板，不改变现有讲解稿、已接受图件或求解结果。

## 文件与修改

- `fig_mechanism_q2_q3.tex`：可编辑的 LaTeX/TikZ 主源，使用 XeLaTeX 编译。
- 同名 PDF：适合论文直接插入的单页矢量图；PNG：审阅图；SVG：矢量编辑/缩放版本（文字转路径，文字内容宜在 TeX 源中改）。
- `page_preview.tex/pdf`：实际 A4 页宽下的图、邻近引导段和图注样例。
- `source_map.json`：项目内部的来源与图形含义核对，不作为论文附件。

在本目录运行：

```powershell
xelatex -interaction=nonstopmode -halt-on-error fig_mechanism_q2_q3.tex
xelatex -interaction=nonstopmode -halt-on-error page_preview.tex
xelatex -interaction=nonstopmode -halt-on-error page_preview.tex
```

需要同步 SVG 与 PNG 时，在本目录继续运行（要求已安装 dvisvgm 和 Poppler）：

```powershell
xelatex -no-pdf -interaction=nonstopmode -halt-on-error -jobname=svg_export '\def\pgfsysdriver{pgfsys-dvisvgm.def}\input{fig_mechanism_q2_q3.tex}'
dvisvgm --no-fonts --bbox=papersize --output=fig_mechanism_q2_q3.svg svg_export.xdv
pdftoppm -r 300 -png -singlefile fig_mechanism_q2_q3.pdf fig_mechanism_q2_q3
```

主色为热量橙红 `#D95319`、含水率交换蓝 `#0072BD`，线条和箭头均有文字及方向冗余。图内没有整图标题；(a)–(c) 是必要的分面标签。改字、物理符号和布局优先编辑 TeX 后重新导出，不单独修改 PNG。

## 推荐放置

放在问题二“两场耦合及控制方程”处，问题三简短引用。本图把耦合关系和边界条件集中呈现，属于表达上的改进，并不构成新的算法、物理模型或额外验证证据。若篇幅紧，现有图01已经交代了几何与离散，本图可省略；选用时可压缩正文重复的几何介绍。图01仍负责问题一的径向几何与控制体，图06仍负责问题四的收缩坐标。

## 可供正文采用的图注

**固定半径下药材的径向传热传质与局部物性耦合示意。** 图中几何未按比例绘制，同心虚线仅表示径向位置。箭头示意 T∞>θs、Cs>Ceq 时的传递方向；qin 取热量传入为正，jC 取含水率向外交换为正。C 为干基含水率，jC 对应本模型的含水率扩散通量；等效边界输入采用 Ceq:=Y∞。本图适用于问题二、三的固定半径模型。

## 数学含义核对

1. 内部热方程为 ρ(C)cp(C)θt，而非对 ρcpθ 整体求时间导数；变系数保留在散度内。
2. 水分扩散用局部 D(C,θ)，两条依赖关系分别指出 C 对热响应以及局部温湿状态对扩散的影响。
3. 图中 qin=h(T∞−θs)=k(Cs)θr(R,t)，向内为正；这与正文采用的向外热通量 −kθr=h(θs−T∞) 等价。
4. 图中 jC=hm(Cs−Ceq)=−D(Cs,θs)Cr(R,t)，向外为正，单位为 m/s×干基含水率单位，不将其标成真实水质量通量 kg/(m²·s)。
5. 右图仅画局部界面和外法向，不引入气膜厚度、气相求解域或额外气相方程；取样引线起于圆柱侧表面。
6. Q1 的常数热物性与 D(C) 不具有本图的双向物性反馈；Q4 的收缩在专图中表达，不混入本图。

## 审阅记录

2026-09-11 已实际打开 PDF 渲染图、SVG 的独立渲染图、灰度图及 A4 页宽预览。修正了分面标签与热箭头标签间距、局部引线与 r=R 标签的避让，以及预览中图注说明被浮动图打断的问题；另补表面状态的界面定位引线。单图 PDF 为 178.0×96.5 mm，PNG 为 2103×1140 px（300 dpi）；A4 预览按 164 mm 宽等比插入，缩放比例为 92.13%，图内主文字约 9.21 pt。主要箭头缩印后约 1.57 pt，灰度下仍可依靠文字和方向区分。PDF 字体全部嵌入，无 Type 3 字体；SVG 无栅格图像。最终编译日志无缺字、未定义引用或越界提示。渲染临时件不放入正式图件目录。样板不等同于用户已认可入稿。
