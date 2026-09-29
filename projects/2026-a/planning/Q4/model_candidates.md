# 问题4：领域依据及候选比较

当前物理解释参见[数学物理说明勘误](../model_explanation_corrections.md)；冻结计算规格及历史运行身份按原记录保留。

## 1 领域资料如何约束候选

以下均为原始模型研究或领域实验资料，角色为 method_reference / mechanism_boundary，不提供本题材料参数，不作为Q4答案或E4真值。访问日期2026-09-11。没有检索或使用本届题目答案。

| 来源 | 本次实际阅读范围 | 对当前决定的作用与限制 |
|---|---|---|
| Brasiello, A.; Venditti, C.; Adrover, A. (2021). Non-Isothermal Moving-Boundary Model for Food Drying. Chemical Engineering Transactions 87,193–198. DOI [10.3303/CET2187033](https://doi.org/10.3303/CET2187033)，[期刊6页全文](https://www.cetjournal.it/cet/21/87/033.pdf) | 复用Q1完整阅读和公式原生核对，本次重新读取期刊全文文字及§2–3 | 以番石榴薄片的局部收缩速度耦合水分、温度与边界；其水变量是单位体积水浓度，并用产品专属平衡关系。支持明确速度、坐标、储存变量；不能把体积浓度方程直接改名为本题干基C。 |
| Adrover, A.; Venditti, C.; Brasiello, A. (2020). A Non-Isothermal Moving-Boundary Model for Continuous and Intermittent Drying of Pears. Foods 9(11),1577. DOI [10.3390/foods9111577](https://doi.org/10.3390/foods9111577)，[作者机构公开PDF](https://iris.uniroma1.it/retrieve/e3835328-38d0-15e8-e053-a505fe0a3de9/Adrover_A-non-isothermal_2020.pdf) | 23页论文中实际阅读第1–7页的对象/实验与§3完整控制方程、边界及数值方法；不是全文逐页审阅 | 梨近球形，文中用水通量决定内部速度及表面位置，采用ALE有限元和BDF。可借鉴运动与输运一致处理、边界突变分段；本题已经给R(t)，不宜再套另一套未经标定的速度—水通量收缩方程。其储热方程也与本题采用s(C)=ρ(C)cp(C)的温度方程不同，不直接照搬。 |
| Viollaz, P. E.; Rovedo, C. O. (2002). A drying model for three-dimensional shrinking bodies. Journal of Food Engineering 52(2),149–153. DOI [10.1016/S0260-8774(01)00097-8](https://doi.org/10.1016/S0260-8774(01)00097-8)，[出版社预览](https://www.sciencedirect.com/science/article/abs/pii/S0260877401000978) | 出版社摘要、引言、Theory及Results的可见片段，未取得完整正文 | 讨论三向收缩、体积平均速度与对流项，特别指出干基变量的参考坐标必须明确。支持防止“换了坐标就默认完成守恒”；不支持把其平板三维形变参数移到本题。 |
| Adrover, A.; Brasiello, A. (2019). A moving boundary model for food isothermal drying and shrinkage: One-dimensional versus two-dimensional approaches. Journal of Food Process Engineering 42(6),e13178. DOI [10.1111/jfpe.13178](https://doi.org/10.1111/jfpe.13178) | 出版社摘要与机构题录，全文访问受限 | 比较几何降维误差，提醒长圆柱近似仍有适用条件。其扩散率反演误差不是本题温湿场误差界；不能把论文中某个长径比阈值转换成本题已证明的精度。 |

药材领域已有 references/Q1/domain_research.md 的DOM-03整根人参成像及DOM-04整根三七热风实验，继续支持“收缩随材料、工况、阶段变化；体积不能在未知轴向变化时唯一换成半径”。本题直接使用自己的R(t)，不从人参/三七论文反推C(t)、干燥终点或内部应变。既有来源不再重复下载。

这些来源支持采用题给半径驱动的径向热质模型，并明确内部均匀径向应变属于运动近似。ρ、cp、k、D仍按附录4的密度、比热容、导热系数和扩散系数含义使用；文献只提供方法依据，不替换题给参数。

## 2 少数真正可比较的候选

| 候选 | 结构和能支持的输出 | 主要问题 | 处置 |
|---|---|---|---|
| 固定R0、附录4物性 | 可计算无收缩参照，便于分离几何作用 | 不消费附件2，不能作为Q4正式答案 | 仅辅助“关闭收缩”结构参照；不是Q3结果，因为物性仍为附录4 |
| 已知R(t)，径向均匀收缩，材料坐标热质方程 | 全部实测节点直接控制域，使用附录4物性计算局部温湿场和全域终点 | 需说明内部均匀径向应变及简化输运方程的适用范围 | 推荐主方案 |
| 已知移动表面，但C_t在固定物理位置等于扩散，无材料输运 | 计算上可写，变换后出现ξR′/R的项 | 使用了不同的内部运动闭合，不能仅凭坐标变化认作当前随体模型 | 仅用于辨明不同闭合，不作为“同一模型的另一写法” |
| 自由边界/多相守恒或孔隙力学 | 由水分、应变及应力同时预测内部形变与R(t) | 需要本题未提供的额外本构，并须与已给R(t)相容；不宜另用未经标定的收缩规律重复决定R(t) | 不作为比赛主方案；文献只说明可扩展方向 |

主方案是数据条件、题给经验式和计算预算下的明确选择，不是文献证明“只能这样建模”。


反事实检查：即使隐藏既有Q2/Q3代码，当前题面仍给动态半径、局部温度依赖D及径向含水率要求，因而仍选择两场移动域。继承的是已核验几何离散和求解经验，附录4物性、运动闭合和域外采样必须单独验证。
