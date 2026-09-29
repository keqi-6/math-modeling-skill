# 参考文献与AI说明合稿指引

本文件仅供队员合稿使用，不放入官方支撑材料。参考文献不是阅读清单：终稿实际引用什么，才收录什么。当前六条主选是可引用候选；其中 Teleken 等的论文是否保留，应由终稿作者根据正文是否使用其研究背景或启发决定。没有相应引用时可缩为五条。

## 引用入口与排版

- `references.tex` 是编号悬挂式的可插入片段，适合直接合入现有 LaTeX 主文档。主文档需加载 `url` 或 `hyperref`。
- `references.bib` 是同六条的结构化元数据。若终稿使用 BibTeX/BibLaTeX，使用此库并正常引用；不再插入 `references.tex`，也不使用 `\nocite{*}`。
- `optional_references.bib` 单列四条选用项。只有保留对应论述、核对原文并实际引用时才移入终稿。
- 文献按正文首次出现顺序重排，正文引用键与书目键一致。当前片段编号只是组装顺序。
- 排版参考既有 2025 定稿的 `[序号]` 与条目悬挂缩进；声明的位置依据当前 2026 官方规则。

## 六条主选的依据与适用边界

| 引用键 | 当前本地使用证据 | 可支撑的正文内容 | 不可由该文献推得的内容 |
|---|---|---|---|
| `nistdlmf` | `docs/Q1/verification_note.md` 的贝塞尔函数校核 | 贝塞尔函数导数、积分与正交关系；用于问题一解析参照解 | 不能称为药材实验验证或模型实测精度证明 |
| `shampine1997ode` | Q1讲解稿时间推进说明与实际 BDF/NDF 启动公式 | NDF 方法、非线性隐式方程及求解背景 | 本项目使用 Python/SciPy，不得因此写成使用 MATLAB 求解 |
| `virtanen2020scipy` | Q1—Q4 求解程序使用 SciPy；本地版本为 1.18.1 | 数值计算软件及求解实现的引用 | 论文标题中的 SciPy 1.0 不是本项目的安装版本；软件引用不替代问题自身的精度检验 |
| `teleken2025shrimp` | `references/Q1/teammate_papers_review.md`、`planning/Q2/model_candidates.md` | 对流干燥中内部热质传输、局部状态相关物性的领域背景与启发 | 对象为虾；不可直接搬用材料参数、几何条件或结果，也不是本题各假设唯一性的证明 |
| `brasiello2021drying` | `docs/Q4/solution_brief.md` 的收缩模型讨论 | 非等温干燥中移动边界、材料运动与传输方程的一致处理 | 不证明本题均匀径向收缩闭合唯一，不能替代题给半径数据 |
| `adrover2020pears` | `docs/Q4/solution_brief.md`、Q4模型候选记录 | 连续与间歇干燥中的移动边界建模背景 | 文献对象和速度闭合与本题不同，不能表述为直接照用原模型 |

NIST 引用使用第10.6节和第10.22节，未为动态网页虚构出版年或固定版本。Foods 的428、1577是文章编号，不是起始页。Shampine论文的期刊出版年是1997，不能误用网页上线日期。

## 选用项

| 引用键 | 适合保留的情形 | 当前采用边界 |
|---|---|---|
| `fritsch1984pchip` | 终稿模型检验确实保留 PCHIP 插值对照 | PCHIP 是辅助对照；不能写成主方案，也不能仅由光滑性断言其更准确。原刊名含 “and Statistical Computing” |
| `nguyen2019codonopsis` | 引言保留药用根茎干燥的具体领域背景 | 该文涉及超声辅助及党参切片，未将其参数、超声条件或拟合方法移入本题主模型 |
| `nistfipy` | 有限体积法介绍需要直接的公开资料 | 引用控制体积积分与面通量离散的解释；本项目没有使用 FiPy 软件 |
| `scipybdf` | 正文具体说明 BDF 的变阶、容差或雅可比接口 | 是软件文档，可与方法原论文分工，也可为精简而不单列。网页稳定版与本地小版本不必相同 |

未直接采用的潜热、吸附等温线、超声、红外等内容不为凑参考文献而加回正文。仅从他文参考文献表得知但本项目未查阅的教材、专著不列为已使用来源。现有来源不支持“环境末小时均值是唯一延续”“均匀收缩是唯一物理模型”“全部数值已保证四位小数准确”等更强结论。

## 元数据核验入口

核验日期：2026-09-12。以下是出版社、期刊、机构或官方文档入口。

- [NIST DLMF 10.6](https://dlmf.nist.gov/10.6)、[10.22](https://dlmf.nist.gov/10.22)。
- [Shampine与Reichelt，SIAM](https://epubs.siam.org/doi/10.1137/S1064827594276424)；[MathWorks提供的原论文](https://www.mathworks.com/help/pdf_doc/otherdocs/ode_suite.pdf)。
- [SciPy官方建议引用及完整作者元数据](https://scipy.org/citing-scipy/)。
- [Teleken等，Foods](https://doi.org/10.3390/foods14030428)；[机构保存的原文](https://escholarship.org/content/qt51f9p2qx/qt51f9p2qx.pdf)。
- [Brasiello等，Chemical Engineering Transactions](https://www.cetjournal.it/cet/21/87/033.pdf)。
- [Adrover等，Foods](https://doi.org/10.3390/foods9111577)；[Sapienza机构元数据](https://iris.uniroma1.it/handle/11573/1450238)。
- [Fritsch与Butland，SIAM](https://doi.org/10.1137/0905021)。
- [Nguyen等，Wiley](https://onlinelibrary.wiley.com/doi/10.1155/2019/2623404)。
- [NIST FiPy有限体积说明](https://pages.nist.gov/fipy/en/stable/numerical/discret.html)、[SciPy BDF文档](https://docs.scipy.org/doc/scipy/reference/generated/scipy.integrate.BDF.html)。

## AI声明与使用详情的合稿说明

2026官方规则要求论文中的“AI工具使用声明”放在参考文献之前，并在支撑材料中提供命名为 `<未收录-AI工具使用详情>.` 的完整文件。规则入口：[全国大学生数学建模竞赛人工智能工具使用规定（2026年试行）](https://www.mcm.edu.cn/html_cn/node/fef94648f2836ab6cc81586f4c38512b.html)。

完整详情采用队伍共同商讨并明确指定的`docs/<未收录-AI工具使用详情>.pdf`，在材料包中原样保存为`../support/<未收录-AI工具使用详情>.`。该报告包含各队员的AI使用信息，以队伍提供的完整记录为依据。

`ai_statement.tex`的正文逐字采用该报告第5节“团队声明”，供接入论文参考文献之前。完整PDF不重排、不补写、不修改元数据。当前没有收到这版报告的LaTeX源稿；旧的`ai_usage_details.tex`不属于这版PDF，已退出合稿包。
