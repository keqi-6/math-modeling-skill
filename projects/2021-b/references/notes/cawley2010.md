# cawley2010

- 标题：On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation
- 作者：Gavin C. Cawley；Nicola L. C. Talbot
- 年份：2010
- 来源：Journal of Machine Learning Research 11:2079–2107
- 原始链接：<https://www.jmlr.org/papers/v11/cawley10a.html>
- 阅读状态：期刊开放页面、摘要、结论和相关方法段已核对

## 支撑主张

有限样本上的模型选择准则具有方差；反复优化该准则可能使模型选择过程本身过拟合。
使用同一评价结果进行选择并报告性能会产生偏乐观的选择偏差。调参与外部评价应分层。

## 本题用途与限制

用于第三问候选比较的验证设计：若模型需要调参，在外层训练数据内部选择参数，再用
外层未见数据评价。论文不证明任何特定回归、正则化或曲线适合本题，也不提供固定折数。
