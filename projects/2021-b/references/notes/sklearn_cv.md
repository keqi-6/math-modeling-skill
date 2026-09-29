# sklearn_cv

- 标题：Cross-validation: evaluating estimator performance
- 作者：scikit-learn developers
- 年份：2026
- 原始链接：<https://scikit-learn.org/stable/modules/cross_validation.html>
- 阅读状态：官方文档中交叉验证、分组结构和留一法相关节已核对

## 支撑主张

验证方案应匹配数据生成结构。若样本来自不同对象、实验或设备等分组，分组交叉验证比
随机抽行更安全；留一法可能具有较高方差。

## 本题用途与限制

用于区分组合内遮点、整组合遮挡和整温度遮挡。软件文档只支持验证结构与接口，不证明
模型适用，也不把分类示例的具体设置移植到本题。
