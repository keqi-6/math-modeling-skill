# 机理示意图第二版

本版响应用户“让色彩承载信息、减少文字依赖”的意见。两行表示同一药材、同一1800 s时刻的温度与干基含水率；中部截面颜色使用Q2原有10241节点快照，橙红越深表示温度越高，蓝色越深表示含水率越高。金色侧体表示材料，箭头突出热入和水分向外交换。完整PDE仍在正文，此图仅保留两条表面交换关系。

## 修改与再生成

布局在 `fig_mechanism_v2.tex` 中直接编辑；截面数据色块在 `field_colors.tex` 中，由项目根 `scripts/build_mechanism_fields.py` 从已存在的未舍入结果生成。需要改变取样时刻或色标时改生成器并重新运行，不手工编造色环值。仅调整布局时不必再次读取计算结果。

以 XeLaTeX 编译单图和页宽预览。SVG 导出使用 dvisvgm 驱动：

```powershell
xelatex -interaction=nonstopmode -halt-on-error fig_mechanism_v2.tex
xelatex -interaction=nonstopmode -halt-on-error page_preview.tex
xelatex -interaction=nonstopmode -halt-on-error page_preview.tex
xelatex -no-pdf -interaction=nonstopmode -halt-on-error -jobname=svg_export '\def\pgfsysdriver{pgfsys-dvisvgm.def}\input{fig_mechanism_v2.tex}'
dvisvgm --no-fonts --bbox=papersize --output=fig_mechanism_v2.svg svg_export.xdv
pdftoppm -r 300 -png -singlefile fig_mechanism_v2.pdf fig_mechanism_v2
```

## 使用位置与范围

候选图用于Q2模型建立或首次解释两场分布处；Q3按需引用。它以一个真实时刻解释空间关系，fig04则负责前三小时的时间演变。Q1解耦和Q4收缩不混入本图。

本图是中部剖切示意，不是实验照片或三维求解结果。切面的64个色环取自完整径向快照的对应中点节点，不增加观测或计算分辨率。箭头粗细不编码通量大小，水滴和温度计只作物理量图例符号。右侧的外法向定义各局部交换图的方向，没有引入气膜厚度或气相方程。

`source_map.json` 仅供项目内部追溯，记录数据身份及色环取值，不作为论文附件。当前是供用户审阅的候选稿，尚未插入队友讲解稿。

## 本轮核对

已核对1800 s完整快照与规定输出半径值完全一致，表面温度35.4130°C低于同刻环境41.513°C，表面含水率1.6486高于环境输入0.03307，图示热入与水分向外的方向符合本次状态。已实看单图、SVG独立渲染、去文字图、灰度图及A4实际页宽预览，并修复色标单位与箭头重叠。单图164×105.5 mm，论文预览按160 mm宽插入，图内主体文字约9.76 pt、色标刻度约8.29 pt；PNG为1937×1247 px（300 dpi），PDF字体全部嵌入，无Type 3字体和栅格图片。图内不放整图标题。候选稿的审美与最终采用仍由队伍判断。
