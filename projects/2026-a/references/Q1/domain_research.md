# 问题1及收缩扩展：药材领域原始研究审阅

检索与阅读日期：2026-09-10。检索对象包括药用根片热湿传递、整根人参/三七干燥收缩、药材水分吸附平衡和甘草干燥。题面未说明药材品种，以下均为可比材料，不等于已经识别本题材料。基础守恒和坐标理论仍见[方法来源](method_sources.md)。

来源用途统一为候选结构提示与机理适用边界（`candidate_hint / mechanism_boundary`），不作为本题参数源、正确结果或验收真值。正文可读取不等于已逐图核对；以下明确记录阅读范围。没有复制论文图表或直接移植拟合系数。

## DOM-01：药用根片的温度—水分联合模型

Nguyen, X.-Q.; Le, A.-D.; Nguyen, N.-P.; Nguyen, H. (2019). **Thermal Diffusivity, Moisture Diffusivity, and Color Change of Codonopsis javanica with the Support of the Ultrasound for Drying**. *Journal of Food Quality*, 2019, 2623404. DOI: 10.1155/2019/2623404。[出版社全文](https://onlinelibrary.wiley.com/doi/10.1155/2019/2623404)。

- 对象与工况：C. javanica药用根片，直径20–25 mm、厚约5 mm；40/45/50°C、0.5 m/s，含无超声热风对照。与本题长圆柱的传输方向和尺度不同。
- 实证结构：厚度方向热与水分扩散；表面热收支含蒸发热；独立测量平衡含水率与水活度。称重及内部两个位置测温，三重复，再反演输运参数。
- 可支持：需要检查表面阻力、材料平衡关系及蒸发热。不能支持空气湿含量直接等于固体干基含水率，其传质系数单位kg/(m²·s)，不能替换题给m/s系数。
- 阅读：出版社正文§2.1–2.7、§3.2–3.3及相关表图说明；公式图片未逐个视觉核对。参数反演后的吻合主要是标定证据；未查得独立留出验证。§2.6与§3.2的平衡实验温度记载不同，不移用其吸附参数。

## DOM-02：药材吸附平衡的直接实验

Boki, K.; Yamada, Y.; Isetani, K. (2002). **Water Sorption Properties of Powdered Crude Drugs and Hydrophilic Function of Their Starches**. *Journal of Applied Glycoscience*, 49(1), 19–27. DOI: 10.5458/jag.49.19。[期刊PDF](https://www.jstage.jst.go.jp/article/jag1999/49/1/49_1_19/_pdf/-char/ja)。

- 人参、三七、半夏、泽泻等药材粉末及淀粉，在20/30°C进行重量法水分收着实验。含水量基于干粉/干淀粉质量，水活度是独立变量；讨论GAB等温线与组成影响。
- 可支持：气相状态与固体含水量之间需要材料关系，不能仅因同为kg/kg就作直接相减。粉末吸湿、低温条件与鲜整根热风解吸不同，系数不可直接补给本题。
- 阅读：英文摘要、日文PDF正文20–24页、公式1及图1–3的可提取文字；日文OCR不完整，未逐图视觉核验。本项目不据此逐式复现或引用数值系数。

## DOM-03：整根人参连续成像与收缩

Martynenko, A. I. (2011；2008在线发表). **Porosity Evaluation of Ginseng Roots from Real-Time Imaging and Mass Measurements**. *Food and Bioprocess Technology*, 4, 417–428. DOI: 10.1007/s11947-008-0158-7。[作者公开全文](https://www.researchgate.net/publication/226300171_Porosity_Evaluation_of_Ginseng_Roots_from_Real-Time_Imaging_and_Mass_Measurements)。

- 近圆柱整根人参，直径约10 mm、长120–130 mm；38/50°C、1 m/s、RH12%，初始含水率约2.4 kg/kg干基。连续称重、每分钟成像，体积置换校准，辅以SEM。
- 可支持：收缩—含水关系可能非线性且随工况和阶段变化，值得先画原始曲线。不能预设R与C全程线性，更不能仅凭曲线拐点认定结壳或孔隙变化。本题半径20 mm，约为研究样品的4倍，时间尺度不能照搬。
- 阅读：公开全文方法、收缩—含水关系与孔隙结果、校准及SEM相关正文；未逐图视觉核验。全文提供者为作者公开页面，题录和DOI核对一致。

## DOM-04：整根三七热风温湿条件与体积收缩

Jiang, D.; Li, C.; Zielinska, S.; Liu, Y.; Gao, Z.; Wang, R.; Zheng, Z. (2021). **Process performance and quality attributes of temperature and step-down relative humidity controlled hot air drying of Panax notoginseng roots**. *International Journal of Agricultural and Biological Engineering*, 14(6), 244–257. DOI: [10.25165/j.ijabe.20211406.6198](https://doi.org/10.25165/j.ijabe.20211406.6198)。[全文镜像](https://pdfs.semanticscholar.org/dce3/e281a5aa262119bc91ad547f17c41b498c64.pdf)。

- 整根三七，初始约2.19 g/g干基，40–70°C、0.3 m/s，比较排湿与阶段湿度；以液体置换测干燥前后体积。
- 可支持：收缩的解释需要考虑干燥工况。文中仅有前后体积，没有前30 min半径序列，不能提供本题早期R(t)，也不能由体积唯一换算半径。
- 阅读：14页原始论文镜像，重点§2.1–2.5、§3.3及表2；出版商访问失败，镜像作者、DOI、页码匹配。原文radius、长度和质量的组合存在疑点，收缩表%标记与小数表示也需谨慎；不移用这些量化结果，不私自更正原文尺寸。

## DOM-05：甘草热风有效扩散的应用边界

Zhu, L.; Li, M.; Yang, W.; Zhang, J.; Yang, X.; Zhang, Q.; Wang, H. (2023). **Effects of Different Drying Methods on Drying Characteristics and Quality of Glycyrrhiza uralensis (Licorice)**. *Foods*, 12, 1652. DOI: 10.3390/foods12081652。[出版社PDF](https://mdpi-res.com/d_attachment/foods/foods-12-01652/article_deploy/foods-12-01652.pdf)。

- 甘草片厚3–4 mm、直径15±3 mm；热风对照60°C、2.2 m/s，未报告RH设定。称重三重复，通过干基水分比与薄片扩散关系估计有效扩散率。
- 可支持：有效扩散在根类药材有实验应用；其平衡量仍是固体干基含水率。该工作不验证内部温度场，不支持直接使用空气湿含量作真实平衡量。
- 阅读：§2.1–2.4、§3.1–3.2及表2。图/表时间单位以及部分扩散数值存在不一致；不采用其数值作为本题参数或验证基准。

## DOM-06：薯蓣材料水活度—干基含水率实验

Owo, H. O.; Adebowale, A. A.; Sobukola, O. P.; Obadina, A. O.; Kajihausa, O. E.; Adegunwa, M. O.; Sanni, L. O.; Tomlins, K. (2017；2016在线). **Adsorption isotherms and thermodynamics properties of water yam flour**. *Quality Assurance and Safety of Crops & Foods*, 9(2), 221–227. DOI: 10.3920/QAS2015.0655。[期刊题录](https://www.qascf.com/index.php/qas/article/view/158)；[作者机构接受稿](https://gala.gre.ac.uk/id/eprint/17814/3/17814%20TOMLINS_Water_Yam_Flour_2016.pdf)。

- 薯蓣粉在25/35/45°C、不同水活度下吸附至恒重，比较五类平衡关系；三重复，含水率按干质量计。
- 可支持：需要材料专属平衡函数及温度条件。预处理粉末吸附与完整鲜根解吸不同，不移植参数或吸附热。
- 阅读：接受稿实验、拟合、热力学与结论，交叉核对期刊题录。

## 两篇补充来源及其边界

**DOM-07**：Ju, H.-Y.; Law, C.-L.; Fang, X.-M.; Xiao, H.-W.; Liu, Y.-H.; Gao, Z.-J. (2016). *Drying kinetics and evolution of the sample’s core temperature and moisture distribution of yam slices (Dioscorea alata L.) during convective hot-air drying*. *Drying Technology*, 34(11), 1297–1306. DOI: [10.1080/07373937.2015.1105814](https://www.tandfonline.com/doi/abs/10.1080/07373937.2015.1105814)。只取得出版社摘要：5/7/9 mm片，50–70°C、RH20–50%，有限元预测中心温度与水分分布并与实验比较。可支持考察空间分布；全文访问受限，不能声称核对了边界、潜热项或验证划分。

**DOM-08**：Zhu, L.; Xie, Y.; Li, M.; Zhang, X.; et al. (2024). *Design and optimization of heat pump with infrared drying for Glycyrrhiza uralensis (Licorice) processing*. *Frontiers in Nutrition*, 11, 1382296. DOI: [10.3389/fnut.2024.1382296](https://www.frontiersin.org/journals/nutrition/articles/10.3389/fnut.2024.1382296/full)。已读§2.3.2、§3.2–3.4、§4.1–4.4；设备设计分别计入预热显热和蒸发潜热。60°C、2.2 m/s并联用红外；主要模拟与验证对象为烘房气流，不能作为药材内部热质模型验证。仅支持分清能量项，不移植能耗比例。

## 在本题中的使用方式

以上保留原始研究的内容与阅读边界，供查证时回看。解题与论文以题给条件为主，引用优先支持三件事：有效扩散与表面交换的方法、含水率口径的正确表述、收缩数据的合理解读。相似材料的参数不直接移用。

论文的模型假设只简述题外省略项，不反复展开文献中的每一种附加机制。除非出现与题意、守恒或实际结果有关的具体矛盾，不把背景研究升级为独立模型、额外试验或推进前置条件。

本轮未运行干燥求解、参数拟合或敏感性实验。当前主线见[model_candidates.md](../../planning/Q1/model_candidates.md)，输入事实见[可视化审阅](../../planning/input_visual_review.md)。正式选择与下一动作仅记入`.modeling/state.json`。
