# LaTeX 内容草稿

本目录只用于编写和编译可持续修改的论文内容草稿。

- `manuscript_draft.tex`：当前唯一编译入口，连续纳入第一问至第四问。
- `manuscript_draft.pdf`：当前唯一内部审阅 PDF，内容按论文正文格式编排。
- `body_problem_restatement.tex`：第 1 章问题重述。
- `body_problem_analysis.tex`：第 2 章问题分析的统一入口。
- `body_q2_analysis.tex`：第二问分析的子模块，由第 2 章在正确位置调用。
- `body_q3_analysis.tex`：第三问分析的子模块，由第 2 章在正确位置调用。
- `body_model_assumptions.tex`：第 3 章模型假设。
- `body_symbol_definitions.tex`：第 4 章符号说明。
- `body_data_preprocessing.tex`：第 5 章数据预处理。
- `body_q1_model.tex`：第 6.1 节第一问模型建立、求解、检验和结论。
- `body_q2_model.tex`：第 6.2 节第二问模型建立、求解、检验和结论。
- `body_q3_model.tex`：第 6.3 节第三问实测推荐、缺测核查、检验和结论。
- `body_q4_analysis.tex`：第四问分析的子模块，由第 2 章在正确位置调用。
- `body_q4_model.tex`：第 6.4 节第四问五次补充实验设计、更新规则、检验和边界。
- `body_model_evaluation.tex`：第 7 章模型评价与适用范围。
- `body_conclusion.tex`：第 8 章四问结论。
- `references_all.tex`：统一草稿的文后参考文献。

上述分文件只为明确源码职责，不代表对外存在多份草稿。

旧的分问入口、PDF、专用参考文献和编译产物已经移至
`paper/archive/2026-07-29_split_question_drafts/`，当前目录不再保留并列草稿。

草稿身份由 `*_draft` 文件名、LaTeX 源码声明和 PDF 元数据共同标明，不再在正文首页、
标题或页眉中插入内部管理提示。草稿不得改名为 `paper.tex`，也不得复制为正式提交 PDF。
未来实际论文的唯一入口固定为
`paper/paper.tex`；它只在全文内容达到正式组装阶段后建立，并从已经确认的草稿中选择性
吸收内容，不能自动引用本目录。

经负责人确认，当前正文草稿不写摘要，直接从问题重述开始。摘要在四问全部完成、主要
结果和检验稳定后统一撰写；这是一项阶段性内容决定，不改变终稿“摘要与关键词位于首
页”的格式要求。

当前项目已由用户确认四边页边距统一为 2.5 cm。该值是本项目版式决定，不表述为竞赛
官方或模板正文的强制要求；未来正式论文沿用该项目决定，除非用户再次修改。

编译命令：

```bash
cd paper/draft
latexmk -xelatex manuscript_draft.tex
```

原 Markdown 正文已经完成迁移核对，并归档到
`paper/archive/2026-07-29_markdown_manuscript/`，不再作为当前草稿继续编辑。
