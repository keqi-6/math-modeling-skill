# 文献证据库

状态：项目级证据库；问题三S3方法定向证据已完成并随推荐整包获批，当前进入S4规格阶段。
机器条目同步到 `literature.json`，引用条目同步到 `references.bib`，逐条阅读
边界记录在 `notes/`。

记录题名、作者、年份、DOI或原始URL、访问日期、阅读状态、支持主张和适用边界。
搜索结果页、聊天记录和未核验转述不作为正式证据。

| ID | 标题 | 作者/机构 | 年份 | DOI/原始URL | 访问日期 | 阅读状态 | 支撑主张 | 限制 |
|---|---|---|---:|---|---|---|---|---|
| `nist-las-definition` | What is Acceptance Sampling? | NIST/SEMATECH | 不详 | [原始页](https://www.itl.nist.gov/div898/handbook/pmc/section2/pmc21.htm) | 2026-08-23 | 相关网页全文 | 属性型批次抽检的问题类别与处置目标 | 方法说明不是本题事实，网页未给本题参数 |
| `nist-las-oc` | Choosing a Sampling Plan with a given OC Curve | NIST/SEMATECH | 不详 | [原始页](https://www.itl.nist.gov/div898/handbook/pmc/section2/pmc222.htm) | 2026-08-23 | 相关网页全文 | 二项近似条件；OC 设计需要两个质量点和两类风险 | 大批量近似；示例数值不可照搬 |
| `nist-las-sequential` | What is a Sequential Sampling Plan? | NIST/SEMATECH | 不详 | [原始页](https://www.itl.nist.gov/div898/handbook/pmc/section2/pmc26.htm) | 2026-08-23 | 相关网页全文 | 顺序边界的输入；样本数依路径；用 ASN 衡量效率 | 页面给近似边界和经验截尾，不证明本题最优性 |
| `nist-exact-binomial` | Exact Binomial Confidence Limits | NIST | 2010 | [原始页](https://www.itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbici.htm) | 2026-08-23 | 相关网页全文 | 小样本精确二项限及单侧构造 | 软件说明不比较所有区间方法 |
| `howard-2021-confidence-sequences` | Time-uniform, nonparametric, nonasymptotic confidence sequences | Howard 等 | 2021 | [10.1214/20-AOS1991](https://doi.org/10.1214/20-AOS1991) | 2026-08-23 | 摘要与首页信息 | 置信序列在不定时间范围内统一有效 | 未阅读全文，不支持具体边界实现或最优性主张 |
| `neyman-pearson-1933` | On the Problem of the Most Efficient Tests of Statistical Hypotheses | Neyman；Pearson | 1933 | [10.1098/rsta.1933.0009](https://royalsocietypublishing.org/doi/10.1098/rsta.1933.0009) | 2026-08-23 | 书目与相关全文段落 | 简单假设间似然比最强检验与临界层随机化 | 不替代本题超几何、复合风险或ASN推导 |
| `arrow-blackwell-girshick-1949` | Bayes and Minimax Solutions of Sequential Decision Problems | Arrow；Blackwell；Girshick | 1949 | [10.2307/1905525](https://doi.org/10.2307/1905525) | 2026-08-23 | 摘要与书目 | 停止/继续递归及Bayes/minimax序贯决策谱系 | 不照搬其分布、成本和时域 |
| `kiefer-weiss-1957` | Some Properties of Generalized Sequential Probability Ratio Tests | Kiefer；Weiss | 1957 | [10.1214/aoms/1177707037](https://doi.org/10.1214/aoms/1177707037) | 2026-08-23 | 摘要与书目 | 错误、样本量分布和可容许性需分别证明 | 未阅读全文；不把GSPRT直接用于本题 |
| `waudby-smith-ramdas-2020-wor` | Confidence Sequences for Sampling Without Replacement | Waudby-Smith；Ramdas | 2020 | [NeurIPS原始页](https://proceedings.neurips.cc/paper/2020/hash/e96c7de8f6390b1e6c71556e4e0a4959-Abstract.html) | 2026-08-23 | 摘要、引言与问题定义 | 无放回有限总体的逐时有效推断需专门处理 | 不支持本题最少次数或ASN最优性 |
| `xue-2024-cumcm-b-lecture` | 2024全国大学生数学建模竞赛B题讲评：生产过程中的决策问题 | 薛毅；中国大学生在线 | 2024 | [原始页](https://dxs.moe.gov.cn/zx/a/hd_sxjm_sxjmstjp_2024sxjmstjp/241127/1980968.shtml) | 2026-08-23 | 问题一幻灯片全文，关键页原图复核 | 四参数OC、SPRT/截尾、DQL及`p1=0.20`的`(109,16)`示例 | 多种解法而非唯一答案；不转载幻灯片 |
| `xue-2025-cumcm-b-analysis` | “生产过程中的决策问题”的问题解析 | 薛毅 | 2025 | [10.19943/j.2095-3070.jmmia.2025.01.08](https://doi.org/10.19943/j.2095-3070.jmmia.2025.01.08) | 2026-08-23 | 摘要、关键词、参考文献与出版信息 | 确认赛后解析的方法谱系 | 未读正文，不支撑具体公式或数值 |
| `gu-etal-2024-cumcm-b-public-project` | CUMCM24-ProblemB-SimulationApproach | 顾国勤；杨子慧；吕阳 | 2024 | [仓库](https://github.com/BoNing-Gu/CUMCM24-ProblemB-SimulationApproach) | 2026-08-23 | README全文 | 作者自报国二并明确问题一选序贯抽样 | 无问题一完整推导，奖项等级来自作者自报 |
| `cumcm-2024-official-award-list` | 2024高教社杯全国大学生数学建模竞赛获奖名单 | 全国大学生数学建模竞赛组委会 | 2024 | [官方页](https://www.mcm.edu.cn/html_cn/node/3aa4e9fc4c5a755da53b343660cdaf59.html) | 2026-08-23 | 相关团队条目 | 核验顾国勤、杨子慧、吕阳团队获奖身份 | 不支撑模型正确性 |
| `henryers-2024-cumcm-b-provincial-first` | 2024全国大学生数学建模竞赛B题（省一） | Henryers公开团队 | 2024 | [仓库](https://github.com/Henryers/mathmodel-24B) | 2026-08-23 | README及论文问题一全文 | Cochran公式、题外`E=5%`与98/60结果 | 奖项自报；估计精度不等于完整OC合同 |
| `rxw2023-2024-cumcm-b-provincial-second` | 2024高教社杯数学建模国赛B题方案 | rxw2023公开团队 | 2024 | [仓库](https://github.com/rxw2023/CUMCM-2024B) | 2026-08-23 | README全文 | 正态近似单尾检验是常见参赛基线 | 奖项自报；未核验完整公式与参数 |
| `bertsekas-tsitsiklis-1991-ssp` | An Analysis of Stochastic Shortest Path Problems | Bertsekas；Tsitsiklis | 1991 | [10.1287/moor.16.3.580](https://doi.org/10.1287/moor.16.3.580) | 2026-08-24 | 出版页摘要、作者稿首页与问题定义相关段落 | 有限状态无折扣累计成本与终止状态的随机最短路谱系 | 不替本题定义状态、质量律或策略域 |
| `bertsekas-2011-dp-vol2-ch6` | Dynamic Programming and Optimal Control, Volume II, Chapter 6 | Bertsekas | 2011 | [作者公开章节](https://web.mit.edu/dimitrib/www/dpchapter.pdf) | 2026-08-24 | 首页、目录及171--172页相关段落 | 固定策略方程、次随机转移与吸收终止解释 | 只使用相关有限状态段落，不采用章节中的近似算法 |
| `nilim-elghaoui-2005-robust-mdp` | Robust Control of Markov Decision Processes with Uncertain Transition Matrices | Nilim；El Ghaoui | 2005 | [10.1287/opre.1050.0216](https://doi.org/10.1287/opre.1050.0216) | 2026-08-24 | 摘要与出版信息 | 稳健转移模型需要显式不确定集合 | 未阅读全文；不能由本题边际率推出唯一联合集合 |
