# 第三方与官方材料

本仓库中非作者原创的材料及其来源如下。

## 技能吸收的公开工作流

技能的方法论综合了以下公开项目，吸收的是工作流思路，不是它们的代码或规范文本。这些仓库是
启发来源，不构成竞赛规则或数学正确性的权威；正式要求以当届官方文件为准。

| 来源 | 吸收的内容 | 未吸收的内容 |
|---|---|---|
| [`handsomeZR-netizen/mathmodel-skill`](https://github.com/handsomeZR-netizen/mathmodel-skill) | 定向启动、题目选择、逐子问局部回修、环境预检、提交合规意识 | 评分状态机、自动 verdict、固定图表数、固定变量数、默认扰动幅度 |
| [`usail-hkust/LLM-MM-Agent`](https://github.com/usail-hkust/LLM-MM-Agent) | "问题分析—结构化建模—计算求解—报告生成"的核心分解，按问题检索模型知识 | 其概述中较弱的独立验证、语义审计、声明边界与变更失效，本仓库补入了这些 |
| [`xiaomacoltai/math-modeling-skill`](https://github.com/xiaomacoltai/math-modeling-skill) | 建模、编程、论文三角色之间的回退条件与复现清单 | 固定交付格式、每问模型数量限制 |

吸收与不吸收的具体条目保留在 [`legacy/bootstrap/15-pipeline-methodology.md`](legacy/bootstrap/15-pipeline-methodology.md)。

## 技能规则的来源

`skills/rules/` 与 `skills/references/` 中的部分规则，来自公开课程讲授、公开论文与公开写作
指导的归纳（例如 `06-weiwei-norms.md`、`13-excellent-paper-expression.md` 对应的规则组合）。
这些文本由本仓库作者重新组织、分类与改写，原始材料著作权归各自作者，引用仅用于方法说明，
不构成对原文的系统性转载。

## 竞赛官方题面与附件

著作权归全国大学生数学建模竞赛组织委员会。本仓库用于教学、复现与技能演示，不代表组织方
认可本仓库内容。

| 位置 | 内容 |
|---|---|
| [`projects/2021-b/data/`](projects/2021-b/data/) | 2021 年 B 题题目原文、附件 1–2 |
| [`projects/2025-a/data/`](projects/2025-a/data/) | 2025 年 A 题题目原文、结果表模板 |
| [`projects/2026-a/`](projects/2026-a/) | 2026 年 A 题题目原文（`A题.pdf`）、附件 1–2 |
| [`projects/2021-b/references/official_guidance/`](projects/2021-b/references/official_guidance/) | 2021 年 B 题评阅要点 |

2024 年 B 题的题目与附件未随本项目收录，可按赛事官方渠道获取。

## 项目内的第三方材料

各项目实践由多人团队完成，队友提交的稿件、意见与队伍内部的 AI 使用报告属于团队材料，未随
本仓库公开。项目文档中提到的官方讲评等外部资料，仅以链接与归纳方式引用，不转载原文。

## 依赖

仓库代码为项目自研，未捆绑第三方库源码；运行依赖（Python 科学计算栈、LaTeX 宏包等）由使用
者按各自许可自行安装。
