# V16 保全：2024 CUMCM B 题队友讲解稿真实落盘审计

> 记录类型：V16 候选的只读真实项目保全与取舍依据。  
> 审查时间：2026-08-28。  
> 真实项目：`/mnt/d/AI/AI_program/2024（第七题）/CUMCM2024Problems/B题`。  
> 审查方式：真实项目全程只读；本轮只新增本保全文件。  
> 规范边界：本文件记录真实落盘事实、消费者边界和设计取舍依据，不是新的规范 owner，
> 不创建 route、atom、packet、状态、证据等级、工件角色或论文门禁。现行义务仍只能由
> V16 的 capability packet、method notes、rules、route contract 及用户明确授权共同拥有。

## 1. 审查目的与结论

本轮用于纠正把队友讲解稿误写成“状态头 + 九项交接清单 + 复现入口”的理解。2024 B 题
当前真实落盘显示：队友讲解稿是一问一份、采用正规数学建模论文职责链的自含 Markdown
解答；工程复现、验证隔离、状态和产物身份属于旁注或内部证据；未来论文只选择性迁移已
冻结主张，不直接吞入整份讲解稿。

真实项目的共同主结构是：

```text
问题重述 → 问题分析 → 模型假设 → 主要符号说明 → 模型建立
→ 模型求解 → 模型结果 → 模型检验与敏感性分析 → 模型评价 → 本问结论
```

该观察是 V16 取舍的历史实证。它不授权把本题的公式、数值、文件状态、行数或局部实现
复制成跨项目规则，也不允许本保全文件覆盖真正的规范 owner。

## 2. 证据范围

### 2.1 完整读取的主稿与旁注

- `docs/q1/solution_brief.md`；
- `docs/q2/solution_brief.md`；
- `docs/q3/solution_brief.md`；
- `docs/q4/solution_brief.md`；
- `docs/q2/implementation_note.md`；
- `docs/q2/verification_note.md`；
- `docs/q3/implementation_note.md`。

### 2.2 定向读取的职责与追溯材料

- `README.md`、`PROJECT.md`、`HANDOFF.md`；
- `planning/index.md`、`planning/work_log.md`、`planning/interaction_log.md`；
- `planning/audits/2026-08-23_q1_solution_brief_reader_rewrite.md`；
- `planning/audits/2026-08-23_q2_solution_brief_reader_rewrite.md`；
- `planning/audits/2026-08-24_q3_solution_brief_reader_rewrite.md`；
- `planning/q1_claim_test_paper_map.md` 至 `planning/q4_claim_test_paper_map.md`；
- Q1、Q2 中登记讲解稿消费者的结果或验证 manifest；
- `src/figures/build_explanatory_figures.py`、`docs/figures/README.md`、
  `docs/figures/figure_manifest.json`；
- `paper/` 文件清单及 `paper/support/<未收录-AI工具使用详情>.`；
- `<未收录-队友材料>/问题一的建模与求解.docx` 至
  `<未收录-队友材料>/问题四的建模与求解.docx`、
  `<未收录-队友材料>/整篇论文附录_代码与文件列表.docx`；
- `<未收录-队友材料>/2024B.pdf` 的文件身份、页数、生成元数据及正文结构抽查。

本审查没有把归档状态、旧审计或参考稿当成当前数学权威；它们只用于辨认文件职责和演化
原因。没有根据外部 PDF 的相似内容臆造不存在的构建依赖。

## 3. 四份 canonical 队友讲解稿

| 实质子问 | canonical 文件 | 当前观察到的载体 |
|---|---|---|
| 问题一 | `docs/q1/solution_brief.md` | 独立 Markdown 主稿 |
| 问题二 | `docs/q2/solution_brief.md` | 独立 Markdown 主稿 |
| 问题三 | `docs/q3/solution_brief.md` | 独立 Markdown 主稿 |
| 问题四 | `docs/q4/solution_brief.md` | 独立 Markdown 主稿 |

`PROJECT.md` 将 `docs/<task-id>/solution_brief.md` 明确定义为逐问、供队友讲解的技术文档；
`planning/index.md` 和 `HANDOFF.md` 也分别登记四份入口。因此本项目采用“一问一份主稿”，
不是四问合并成一个交接文件，也不是用 implementation 或 verification note 代替主稿。

四份主稿的具体长度、公式数量和二三级小标题随问题复杂度变化。它们说明共同的是章节
职责，而不是强制各问等长、等式数量相同或拥有相同数量的表图。

## 4. 十节共同结构及各节职责

| 顺序 | 共同标题 | 真实项目中的主要职责 |
|---:|---|---|
| 1 | 问题重述 | 用题目语言说明本问要决定、计算或回答什么，并明确核算对象和范围 |
| 2 | 问题分析 | 解释结构难点、错误简化及为何选择当前建模路线，不提前堆放结果 |
| 3 | 模型假设 | 写成立条件及失效影响，不把假设伪装成现实事实 |
| 4 | 主要符号说明 | 只索引跨节主要符号；局部变量仍须在公式附近解释 |
| 5 | 模型建立 | 连续建立对象、变量、关系、目标、约束、状态、可行性和计算关系 |
| 6 | 模型求解 | 说明候选生成、算法、结构化化简、排序、停止与最优性口径 |
| 7 | 模型结果 | 报告有单位的主结果，并解释形成机制、并列和实际执行含义 |
| 8 | 模型检验与敏感性分析 | 报告结构不变量、边界攻击、敏感性、证据强度和适用范围 |
| 9 | 模型评价 | 总结真实结构优势、计算限制和现实局限，不写空泛自评 |
| 10 | 本问结论 | 直接回答本问，并把候选域、条件和禁止外推与结论放在一起 |

真实项目的重写审计还显示两条重要表达边界：公式必须就近解释对象、变量、用途和不能推出
的结论；模型结果不能只复制机器表格，主表之后仍需解释机制、条件与结论强度。

## 5. 主稿、sidecar、论文与队友意见的边界

### 5.1 主稿

`solution_brief.md` 承担面向队友的完整数学叙事：题意、建模、求解、结果、检验、评价和
直接结论。当前统一稿没有状态头、spec/result ID、TODO、运行命令、哈希清单或“队友最小
复述”元章节。`planning/work_log.md` 记录四问统一时删除了工作流内部过程。

### 5.2 Sidecar

当前只存在 Q2 的 implementation/verification 两份旁注和 Q3 的 implementation 旁注；
Q1、Q4 没有同名旁注。这种不对称说明 sidecar 是按实际复现需要形成的辅助材料，不是
“每问必须补齐两份”的主稿格式。

- implementation note 保存生产实现职责、运行命令、输出文件和结果身份；
- verification note 保存独立验证的输入输出、隔离方法、运行方式和证据职责；
- 状态、规格、实现和验证的完整权威仍分布在 `planning/`、`src/`、`output/` 及 manifest。

Q2 旁注分别明确声明自己不是队友讲解稿或正式论文。Q3 旁注保留了后来已变化的阶段文字，
也证明旁注不能替代当前项目状态或 canonical 主稿。

### 5.3 正式论文

项目职责文件明确把 `docs/` 与 `paper/` 分开：讲解稿必须符合论文语言规则，但不冒充论文
正文；Markdown 关系式留在 docs，正式 LaTeX 只进入 `paper/**/*.tex`，且论文入口需要
另行授权。

四份 `planning/q*_claim_test_paper_map.md` 承担未来论文的选择性迁移接口：它们记录可写
主张、模型或结果依据、验证、边界和拟落点，同时都声明自己不是论文正文。由此可见，正确
链路是挑选并重写已冻结内容，而不是把整份 brief 自动提升或直接 include。

审查时 `paper/` 只有独立的 AI 工具使用说明源和渲染物，没有受控的主论文源。
`<未收录-队友材料>/2024B.pdf` 虽是完整论文形态，但项目内没有主源、构建脚本、manifest 或依赖
登记将它绑定到四份 brief。因此只能记录其内容相似或可能经过人工整合，不能据此宣称
存在可追溯的直接机器消费链。

### 5.4 队友意见目录

`<未收录-队友材料>/问题一至四的建模与求解.docx` 是参考或人工协作材料，不是 canonical 主稿。
现有审计明确说明只学习其写作节奏和结构，不继承冲突模型或未批准数学内容。该目录中的
PDF、DOCX、PPTX 和附录也不自动获得题意、模型、结果或论文 source-of-truth 身份。

## 6. 结果进入讲解稿的来源链

真实项目呈现的方向是：

```text
题意与批准规格
→ src/q* 主实现
→ output/q* 冻结结构化结果与运行 manifest
→ 独立验证和结构检验
→ 人工组织的 docs/q*/solution_brief.md
→ planning/q*_claim_test_paper_map.md
→ 未来论文中的选择性迁移
```

Q1、Q2 的部分结果或验证产物把相应 `solution_brief.md` 登记为 downstream consumer；没有
求解脚本把 brief 当作数值输入，也没有发现 brief-to-paper 转换脚本。重写审计逐项核对
公式、显示数字、精确结果、单位、并列和声明强度，说明讲解稿应读取已冻结证据后人工表达，
不能成为手工改数的第二结果源。

表格直接以 Markdown 写在符号、结果或敏感性章节；主结果表之后仍有逐情景或逐机制解释。
展示小数服务阅读，排序、并列或风险判定仍以冻结的精确结果为依据。

## 7. 图件进入讲解稿的来源链

工作图链路与主稿分开：

```text
output/q* 冻结结果和验证结果
→ src/figures/build_explanatory_figures.py
→ docs/figures/*.png + *.svg
→ docs/figures/figure_manifest.json
→ 被某份 solution_brief 明确引用时才成为该主稿消费者
→ 被正式论文源明确引用时才成为论文消费者
```

`docs/figures/README.md` 将这些产物标为 working visuals，并明确禁止在绘图软件中手工修改
数值。生成脚本直接读取冻结 JSON；manifest 保存输入哈希、单位、解释边界和 PNG/SVG 输出
哈希。SVG 面向未来排版，PNG 用于快速预览或 Markdown 嵌入。

审查时五类工作图均已生成，但四份主稿中只有 Q1 的平均检测比例图被相对路径实际嵌入。
其余图“已生成”不等于“已被讲解稿消费”，更不等于“已进入正式论文”。因此图件完整性
应按真实引用关系判断，不能由目录中存在图片反推消费者闭合。

## 8. 可保全的设计取舍与禁止泛化

本真实项目支持以下 V16 取舍依据：

1. 队友讲解稿应与状态交接清单、实现复现说明和独立验证说明分工；
2. 每个实质子问应有可独立定位的 canonical 主稿；
3. 本项目采用十节正规建模职责链，并以公式就近解释、结果机制说明和条件边界作为表达
   质量基准；
4. sidecar 按真实复现消费者生成，不机械要求每问齐套；
5. 结果和图件应从冻结机器产物单向进入讲解稿，讲解稿不成为第二数值 owner；
6. 正式论文通过主张映射选择性迁移，不能自动晋升整份 brief；
7. 文件存在、临时渲染通过或人类能够复述，均不能替代正式论文授权与论文验收。

下列对象只属于本项目，不得由本文件提升为通用规则：

- 四问各自的数学模型、公式、参数、方案编码、结果和验证计数；
- 当前文件行数、公式数量、图表数量及某问是否恰有 sidecar；
- 项目内部阶段、历史状态、回执和失效审计；
- `<未收录-队友材料>`目录中的具体写法、外部 PDF 排版或人工整合过程；
- “所有项目必须使用相同文件名、完全相同十个标题或同样数量图表”的推论。

若 V16 要把本轮观察转化为通用义务，必须在真正的规范 owner 中以跨项目语义重写，并由
相应 contract/eval 验证；不得把本 preservation 记录当成运行时规则引用。

## 9. 精确证据索引

### 9.1 落盘与职责

- `PROJECT.md`：项目定位、`docs/`逐问讲解职责、`paper/`职责和格式边界；
- `README.md`：项目当前论文边界；
- `planning/index.md`：四份 current solution brief 的逐问入口；
- `HANDOFF.md`：四问证据链、讲解稿入口及论文/交付边界；
- `planning/work_log.md`：讲解稿从教程式结构统一到正规论文职责链的历史；
- `planning/interaction_log.md`：用户对主稿结构、公式邻近解释和参考稿边界的纠正。

### 9.2 主稿、旁注与审计

- `docs/q1/solution_brief.md` 至 `docs/q4/solution_brief.md`；
- `docs/q2/implementation_note.md`、`docs/q2/verification_note.md`、
  `docs/q3/implementation_note.md`；
- `planning/audits/2026-08-23_q1_solution_brief_reader_rewrite.md`；
- `planning/audits/2026-08-23_q2_solution_brief_reader_rewrite.md`；
- `planning/audits/2026-08-24_q3_solution_brief_reader_rewrite.md`。

### 9.3 结果、论文迁移与图件

- `output/q1/s5_results.json`、`output/q1/s6_independent_verification.json`；
- `output/q2/s5_run_manifest.json`、
  `output/q2/s6_independent_verification_manifest.json`；
- `planning/q1_claim_test_paper_map.md` 至 `planning/q4_claim_test_paper_map.md`；
- `src/figures/build_explanatory_figures.py`；
- `docs/figures/README.md`、`docs/figures/figure_manifest.json`；
- `paper/support/<未收录-AI工具使用详情>.`；
- `<未收录-队友材料>/2024B.pdf`、四份逐问 DOCX 及附录 DOCX。

## 10. 保全结论

2024 B 题证明了一种清晰且实际使用过的分工：每问一份正规建模职责链讲解稿，工程复现与
独立验证留在按需 sidecar 和内部证据，结果与图从冻结产物单向进入主稿，论文则通过主张
映射选择性重写。V16 可以把这组事实作为纠错与设计取舍证据，但本文件永久保持
preservation 身份，不取得规范解释权、运行时选择权或发布门所有权。
