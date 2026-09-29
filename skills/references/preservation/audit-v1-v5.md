# V1–V5 规则文本能力审计（为下一次重构保留“完整能力”，不是保留文件堆）

## 0. 审计范围、口径与谱系警告

- 基准目录：`/mnt/d/AI/AI_program/2021（第四题）/总skill/`。
- 只读覆盖：`skills`、`skills_v2`、`skills_v3`、`skills_v4`、`skills_v5` 中的 `SKILL.md`、规则 Markdown、`references`、`source-portfolios` 和根 `skills/` 的顶层编号规则；脚本只用于理解调用、验证和路由语义，不计入本报告的规则文本数。
- 覆盖总数：**173 个逻辑规则/参考文本，73 个独立内容哈希**。分版本为：`skills` 61、`skills_v2` 30、`skills_v3` 33、`skills_v4` 8、`skills_v5` 41。
- 相同 SHA-256 的文本只逐字审计一次，但下文列出其全部版本身份；因此“合并”不是漏读。

根 `skills/` 不是一个纯净的单一年代快照，必须拆开理解：

1. `skills/SKILL.md` 与顶层 `skills/01-...md` 至 `skills/16-...md` 是 V1 的 17 个历史权威文本；`skills_v5/references/v1-integration-map.json:4-24` 也以这组文件为 V1 来源。
2. `skills/rules/` 同时包含 V5 的回填副本、V3/V4 验收层，以及后来的 V6/2026-08 修补；`skills/references/migration-ledger.md:143-254` 明写 V5-native、V6 和 2026-08-18 修复。
3. 所以报告把顶层 17 个文本称为“V1 权威集”，把根 `skills/rules/` 的额外内容称为“后续根快照修复”，不把 `rules/36`、`rules/37` 或 2026-08 增补倒算成 V1 能力。

处置标签：

- `preserve_verbatim`：保留短句/短段原文；不是把整篇复制到运行时。
- `preserve_semantics_rewrite`：能力、程序、例外或失败修复必须保留，但重写为当前清晰口径。
- `merge`：与其他来源合成一个完整能力包；源文本留在迁移档案，不再作为并列运行权威。
- `retire`：从活动运行规则退出；历史档案可以保留。通常因为过时、题型/年份绑定、把检查手段当能力、或门禁成本显著高于风险。

## 1. 总结论

### 1.1 真正发生的不是单向“优化”，而是两次相反的失衡

1. **V2/V3/V4 的问题是“文本仍在，能力不可达”。** V2 把长规则放进 `source-portfolios/`，并在 `skills_v2/SKILL.md:13-23,175-209` 限制其日常执行；V3 又明确 `references/rule-sources/` 不能作活动规则替代（`skills_v3/SKILL.md:19-21,175-181`）。V4 进一步把详细知识降为历史参考（`skills_v4/SKILL.md:19-22,222-224`）。因此不能以“档案里还有原文”证明 agent 实际获得了数据清洗、绘图构造、文献检索、求解叙述等能力。
2. **V5 的问题是“内容恢复了，但按整文件叠加加载”。** V5 论文路由一次要求 12 个文件，共 **2371 行**（`skills_v5/SKILL.md:288` 对应的文件）；绘图路由要求 `04+27+34`，共 **426 行**（`skills_v5/SKILL.md:289`）。这恢复了字节，却没有形成能被一次完整执行的能力单元。
3. **V4 的压缩最伤“怎么做”。** 例如 V1 图件规则 `skills/04-figure-generator.md` 为 205 行，V4 `skills_v4/rules/visuals-layout.md` 只有 33 行；数据从 `skills/16-data-audit-methodology.md` 的 153 行缩为 `skills_v4/rules/data.md` 的 34 行。V4 仍能说出“应当正确、可读、可追溯”，但大量触发、步骤、例外、反例和修复路径消失。
4. **V5 的精确回填证明“哈希相等”，不证明“使用时可执行”。** `skills_v5/references/migration-ledger.md:50-68` 的 exact acceptance repair 很适合防止静默删义，却不能替代按能力重组；同一语义同时出现在详细层、V3 验收层和 V4 minimum 层，增加注意力竞争。

### 1.2 绘图弱项的根因比“提示词压缩”更具体

- V1 `04` 已经很好地规定了图的**信息职责、载体选择、共享视觉语义、正文闭环和三轮验收**（`skills/04-figure-generator.md:13-205`），但它主要回答“什么图合格”，对复杂工程示意图的**几何复原、拓扑真值、投影选择、线型层级、标签约束和像素级迭代**回答不足。
- V3 `V-07`–`V-09`（`skills_v3/rules/30-figures-tables-layout.md:103-161`）把上述内容压成验收条款；V4 又压为 19 行视觉要求（`skills_v4/rules/visuals-layout.md:5-20`）。agent 即使全部遵守，也未必知道如何从题面画出正确而漂亮的工程图。
- 后续根快照的 `skills/rules/37-scientific-figure-design.md:22-42,46-70,88-123,137-169` 恰好补上了这块：题面对象到图元的真实性映射、工程线型、工具选择、代表性样板、人审边界、原题投影复原与最终像素验收。它是**缺失能力后来被真实失败重新逼出来**的直接证据。
- 因此下一版不能只有一个“visual atom”。至少要有两个完整实施包：`FIG-DATA`（数据/结果图）与 `FIG-SCHEMATIC`（结构/受力/机理/工程图），再共享 `FIG-STYLE` 和 `FIG-AUDIT`。验收原子负责判断，实施包负责真的画。

### 1.3 控制面结论

当前审计不建议全面重写控制器。值得保留的是单一权限源、人类决定、最早错误层回退和正式发布确认；应避免把 V3/V5 的“每个实质任务都写回执”“每轮改一句都重新全文读规则”“每个跳过项都留结构证明”重新扩张为日常默认。

- `preserve_verbatim`：V4 的权限公式（`skills_v4/SKILL.md:56-67`）和“理解不等于批准”的边界（`skills_v4/SKILL.md:119-135`）。
- `preserve_semantics_rewrite`：恢复、回执和完整阅读改为风险分级；普通续作/局部低风险编辑使用增量证据，高风险接管、权威变更和正式交付才使用完整清单。
- `retire`（日常强制身份）：V3 `R-03` 对所有未触发规则逐项证明（`skills_v3/rules/01-execution-receipt.md:28-40`）、V5 每个实质任务机械回执（`skills_v5/SKILL.md:10-17,224-271`）、后续根快照每条新改稿指令重新读取全部论文规则（`skills/rules/20-execution-gates.md:12-20`）。这些可保留为高风险审计模式，不应成为能力执行本身。

## 2. 推荐组织：原子作索引，能力包保留完整动作

建议不把“能力原子化”理解成把段落压成一句，而采用四层结构：

| 层 | 职责 | 允许内容 | 不允许内容 |
|---|---|---|---|
| `SKILL.md` 控制器 | 权限、状态、人类确认、回退、任务路由 | 极短且唯一 | 详细写作/绘图/数据教程；重复验收表 |
| `atoms/*.md` 验收原子 | 稳定 ID、触发、通过/失败、指向能力包 | 1 个可独立判定语义 | 用一句话冒充完整实施方法 |
| `capabilities/*.md` 完整能力包 | 从输入到产物的完整执行知识 | 触发、前置、步骤、例外、失败修复、正反例、人审点、验收 | 被任意摘要；跨多个包重复同一权威语义 |
| `assets/`、`scripts/`、`archive/` | 确定性机械件、样例、历史 | 模板、样式、SVG primitives、检查器、迁移图 | 让脚本替代语义/审美/数学判断 |

建议能力包及主要来源：

| 包 | 完整能力 | 主要保留源 |
|---|---|---|
| `RECOVERY` | 接管、证据分级、重复文件、未知/二进制材料、恢复失败 | V1 `SKILL`、`01`、`14`；V3 K-01/K-02；V4 S0 |
| `PROJECT-LINEAGE` | 初始化、目录职责、代码/冻结产物、producer-consumer、变更传播 | V1 `01`、`10`；V3 E；V4 provenance |
| `QUESTION-LIFECYCLE` | 逐问解释、基线、候选、人工决定、规格、求解、冻结 | V1 `15`、V3 L、V4 S1–S6 |
| `LITERATURE-EVIDENCE` | 文献触发、四轮检索、来源身份、主张挂载 | V1 `08`、`12`；V3 E-03 |
| `DATA-AUDIT` | 统计单位、结构化解析、对账、异常候选、数据能力、独立复核 | V1 `16`、V4 data |
| `MODEL-SPEC` | 对象映射、假设、目标/约束、辅助变量、多目标、反事实 | V1 `03`、`07`；V3 S-02–S-06；V4 modeling |
| `SOLVE-RESULT` | 算法回放、停止/覆盖、答案还原、结果机制、正文/复现边界 | V1 `03`；V3 S-07/S-08/S-10–S-12 |
| `VERIFY-UNCERTAINTY` | 独立验证、风险匹配测试、不确定性来源、固定方案/重优化、声明边界 | V1 `09`；V3 S-09；V4 verification；后续 `36` |
| `MANUSCRIPT-STRUCTURE` | 背景/重述/分析/假设/章节职责、逐问可见链 | V1 `03`、V2 `17`、V3 B/A/M/S |
| `MANUSCRIPT-EXPRESSION` | 摘要、术语、六类句子、因果闭合、结果/结论、局部修复 | V1 `03`、`13`；V3 M/F/C |
| `FIG-DATA` | 图表任务、载体、比较/单位/不确定性、图注正文闭环 | V1 `04`、V3 V-07–V-09 |
| `FIG-SCHEMATIC` | 结构/受力/机理/流程图的真值映射、几何和图元约束 | 后续根 `37:22-70,137-169`，并吸收 V1 `04` 通用部分 |
| `FIG-STYLE-AUDIT` | 样式系统、可访问性、代表样板、人审、最终尺寸/退化/PDF 三轮检查 | V1 `04`；V3 V-09；后续根 `37:72-123` |
| `LATEX-RENDER` | 唯一源、模板边界、字体探测、样张、编译与逐页检查 | V1 `02`；V3 V-01–V-06/V-10–V-12 |
| `DELIVERY-COMPLIANCE` | 草稿/正式隔离、当届规则核验、打包与正式推广 | V1 `11`、`12`；V3 H；V4 provenance |
| `SKILL-EVOLUTION` | 反馈只读沉淀、个案→判据、逐义务迁移、负例回归 | V1 `12:113-145`；V3/V4/V5 migration ledgers |

每个能力包的固定内部结构建议为：`何时加载 → 所需权威输入 → 完整程序 → 条件分支/例外 → 常见失败及回退 → 正反例 → 人工确认点 → 产物/证据 → 验收原子`。这样原子化的是**路由和判定**，不是把实施知识削短。

## 3. 精确重复与版本身份（覆盖全部别名）

以下同哈希家族统一按对应 canonical 行号审计：

- `01`、`04`、`06`–`16`：`skills/NN-*.md` = `skills/rules/NN-*.md` = `skills_v2/source-portfolios/NN-*.md` = `skills_v3/references/rule-sources/NN-*.md` = `skills_v5/rules/NN-*.md`。这些副本全部标为 `merge`，仅一个能力包正文保留权威语义。
- `02`：V1 原文为 `skills/02-latex-setup.md`，等于 `skills/rules/02...` 与 V5 `rules/02...`；V2/V3 source 版本只多了迁移说明（V2 `source-portfolios/02...:187-214`），该说明指向已不存在的相对位置，见后文 `retire`。
- `03`：`skills/03-paper-content-rules.md` 是 V1 原文；V2 source、V3 rule-source、V5 `rules/03` 是加入 reader-first 起草门的同一 987 行版本；根 `skills/rules/03` 是 1143 行后续超集。
- `05`：`skills/05-audit-protocol.md` 是 V1 原文；V2 source、V3 rule-source、V5 `rules/05` 和根 `skills/rules/05` 是加入 reader-first 审计门的同一超集。
- `17`：V2 source = V3 rule-source = V5 `rules/17`；根 `skills/rules/17` 是加入元话语、传播矩阵和物理推导回归项的后续超集。
- `legacy-SKILL`：V2 `source-portfolios/legacy-SKILL.md` = V3 `references/rule-sources/legacy-SKILL.md`；它等于 V1 `skills/SKILL.md` 加入 V2 reader-first 入口段，不是第二控制器。
- V3 新规则：V3 `rules/01` = V5 `rules/18`；V3 `rules/05` = 根/V5 `rules/19`；V3 `rules/00` = V5 `rules/20`（根 `rules/20` 后来增补）。
- V3 9 个稳定-ID质量文件 `rules/10,20–24,30,40,50` 分别等于根/V5 `rules/21–29`。
- V4 六个质量文件分别等于根/V5 `rules/30–35`。

## 4. V1 权威集逐文件/逐规则族审计

### 4.1 `skills/SKILL.md`（同 V5 `rules/00-project-orchestration.md`）

| 源范围 | 处置 | 去向与判断 |
|---|---|---|
| `:8-61` 架构、owner、A–E 强度、删除治理 | `preserve_semantics_rewrite` + `merge` | `KERNEL`/`SKILL-EVOLUTION`。保留权威优先级、条件规则与“独立语义不得静默删除”；不在运行时重复 owner 表和删除流程。 |
| `:63-88` 两次全量复读 | `preserve_semantics_rewrite`；部分 `retire` | `RECOVERY`。保留“摘要只是导航”“按原生载体检查”“哈希去重”；退役里程碑/局部任务一律全项目复读，改为风险级别与增量证据。 |
| `:98-162` 人工主导、知情批准、读者层、术语最小化 | `preserve_verbatim`（关键短段）+ `merge` | `KERNEL`/`QUESTION-LIFECYCLE`。这是 V1 最成熟的人工参与设计之一。 |
| `:164-246` 首次动作、项目目录合同 | `preserve_semantics_rewrite` | `PROJECT-LINEAGE`。作为新项目/缺失结构的条件程序；已有有效结构不强制迁移。 |
| `:248-285` 源语法边界与规划卫生 | `preserve_semantics_rewrite` | `PROJECT-LINEAGE`/`LATEX-RENDER`。Markdown 禁 LaTeX 的绝对化做法应改为“按项目渲染契约”，避免把格式偏好当真理。 |
| `:287-296` 阶段是 reasoning map | `preserve_verbatim` | `KERNEL`。直接防止控制器自动流水线化。 |
| `:298-468` ORIENT/SOURCE/UNDERSTAND/DATA/EVIDENCE_DESIGN | `merge` | 分入 `RECOVERY`、`LITERATURE-EVIDENCE`、`DATA-AUDIT`、`MODEL-SPEC`；不能压成阶段名。 |
| `:469-525` 逐问纵切与独立性反事实 | `preserve_verbatim`（核心短段）+ `merge` | `QUESTION-LIFECYCLE`。尤其保留“跨问一致不等于方法/公式/验证相同”。 |
| `:503-598` SOLVE/INTEGRATE、缺陷分类与最早层修复 | `preserve_verbatim`（`:559-567`）+ `merge` | `SOLVE-RESULT`/`VERIFY-UNCERTAINTY`。沟通遗漏、实现错配、建模遗漏三分法非常有效。 |
| `:600-693` COMMUNICATE/AUDIT_SUBMIT | `merge` | `MANUSCRIPT-*`、`FIG-*`、`DELIVERY`；去除与 03/05/11 的重复。 |
| `:695-759` 交互、建文件、路由、停止条件 | `preserve_semantics_rewrite` | `KERNEL`。停止条件保留；固定路径/全文件路由改为能力包路由。 |

### 4.2 `skills/01-contest-project-pattern.md`

| 源范围 | 处置 | 去向与判断 |
|---|---|---|
| `:16-29` 接管反模式与证据层级 | `preserve_verbatim`（反模式）+ `merge` | `RECOVERY`/`EVIDENCE`。 |
| `:31-67` 目录及“初始化不等于建空目录”、技术计划 | `preserve_semantics_rewrite` | `PROJECT-LINEAGE`。目录树是默认模板而非硬编码；`:48-54` 非破坏性副本/指针清单应保留。 |
| `:69-100` 注释、冻结输出、产物分区 | `preserve_semantics_rewrite` | `PROJECT-LINEAGE`。固定三行头只是推荐样例，转为 asset。 |
| `:104-145` 源格式、数字身份、导航文件 | `merge` | `PROJECT-LINEAGE`/`MANUSCRIPT-EXPRESSION`。数字身份五分法值得保留；Markdown 绝对禁数学定界符需按实际渲染环境改写。 |
| `:148-167` 脚本/论文交付清单 | `merge` | 各能力包末尾验收，不保留总清单副本。 |
| `:170-182` 引用与 2025 AI 合规 | `preserve_semantics_rewrite` + `retire` 旧文本 | `DELIVERY-COMPLIANCE`。保留“当届官方优先、每次重新核验”；退役固定年份、旧 URL 结论和过度宽泛的“每个主张必须有文献”。 |
| `:184-200` 人工主导与 provisional 草稿 | `preserve_semantics_rewrite` + `merge` | `KERNEL`/`PROJECT-LINEAGE`。方向改变点须人工确认；普通机械执行不重复确认。 |

### 4.3 `skills/02-latex-setup.md`

| 源范围 | 处置 | 去向与判断 |
|---|---|---|
| `:19-41` 官方优先、唯一主稿、草稿/正式隔离 | `preserve_semantics_rewrite` | `LATEX-RENDER`/`DELIVERY`。 |
| `:43-89` 语法边界、按稳定章节职责拆源 | `preserve_semantics_rewrite` | `LATEX-RENDER`。保留唯一入口和职责边界；“每一级标题必须恰一文件”只作大型正文/协作冲突时的条件策略。 |
| `:91-156` 明示模板、符号表、外部图像规范 | `preserve_semantics_rewrite` | `LATEX-RENDER`。所有具体字号/字体/模板条款必须标成“已确认项目 profile”，不能成为跨赛事常量。 |
| `:158-207` XeLaTeX preamble | `merge` 到 asset | 作为可复制模板/样张，不占能力正文；字体与文档类在运行环境探测后替换。 |
| `:209-249` 编译、文件组织、图表落点 | `preserve_semantics_rewrite` | `LATEX-RENDER`；与 V3 V-02–V-12 合并。 |
| `:251-275` 版面冲突的修改权限与编辑安全 | `preserve_semantics_rewrite` | `LATEX-RENDER`。仅删除证据、改官方版式、覆盖正式稿等高影响动作要求人工确认；普通可逆排版修复不逐项设门。 |

### 4.4 `skills/03-paper-content-rules.md`（V1 982 行）

这个文件不应整体进入一次运行上下文；应按下列完整职责分包，且每包保留例外与反例。

| 源范围 | 处置 | 去向与判断 |
|---|---|---|
| `:37-68` 首次正文起草门 | `preserve_semantics_rewrite` | `MANUSCRIPT-STRUCTURE`。优秀论文只能校准信息组织；不要求每次局部编辑重新走首次起草门。 |
| `:69-311` 摘要、A/B/C准入、双向术语/数字/现实锚定 | `merge`，关键句 `preserve_verbatim` | `MANUSCRIPT-EXPRESSION` 的 abstract 子包。保留删减顺序、盲读、双向追踪；固定“1–3亮点”等数量改为启发。 |
| `:312-451` 问题分析、概念限定、方法定位、逐句最小修复 | `preserve_semantics_rewrite` | `MANUSCRIPT-STRUCTURE`。`:314-315` 的章节职责句原样保留；`:440-448` grep 仅作定位示例，不作自动判错。 |
| `:452-537` 假设分类、相邻章节职责 | `preserve_semantics_rewrite` | `MODEL-SPEC`/`MANUSCRIPT-STRUCTURE`。题面事实≠假设、删除检验、下游实际用途均保留。 |
| `:538-602` 局部因果链、逐问主证据 | `preserve_verbatim`（`:540-556` 中核心句）+ `merge` | `MANUSCRIPT-EXPRESSION`/`EVIDENCE`。按“问题—主证据—直接答案—必要检验—边界”收束很强。 |
| `:603-646` 数据叙事、AI模板化表达、关系驱动衔接 | `preserve_semantics_rewrite` | `MANUSCRIPT-EXPRESSION`。不能把若干禁词变成词法门；必须结合句子功能。 |
| `:647-741` 公式推导链、展开尺度、标题 | `preserve_verbatim`（`:657-662`）+ `merge` | `MODEL-SPEC`/`SOLVE-RESULT`。公式审计单位是“数学职能”而不是环境/公式数量，原样保留。 |
| `:742-902` 求解可复推、八功能、辅助约束、参数变化、多目标、证明边界、正反例 | `preserve_semantics_rewrite`，保留正反例 | `SOLVE-RESULT`/`MODEL-SPEC`/`VERIFY`。这是不能被 V4 minimum 替代的实施知识。 |
| `:903-982` 精度、参考文献、结论、摘要平衡、支撑材料 | `merge` | `MANUSCRIPT-EXPRESSION`/`DELIVERY`。 |

### 4.5 `skills/04-figure-generator.md`

| 源范围 | 处置 | 去向与判断 |
|---|---|---|
| `:13-31` 不可替代信息职责与 Nature 原则 | `preserve_verbatim`（`:15`）+ `preserve_semantics_rewrite` | `FIG-DATA`/`FIG-STYLE-AUDIT`。外部规范 URL 要在使用时核验，不硬编码为跨项目最高权威。 |
| `:32-68` 共享视觉语义与 Okabe–Ito 色板 | `merge` 到 `FIG-STYLE` + asset | 色板和语义表作为可复用 preset；具体对象—颜色不应成为所有题型默认。 |
| `:70-98` 格式、载体、布局、唯一安全自动调整 | `preserve_semantics_rewrite` | `FIG-STYLE-AUDIT`。最终尺寸优先；自动只改显示尺寸是历史安全策略，当前可允许可逆重绘候选但不能静默替换。 |
| `:100-111` 图注/正文四功能 | `preserve_semantics_rewrite` | `FIG-DATA`。 |
| `:113-159` 完整性/载体、内容/证据、呈现/技术三组独立审计 | `preserve_verbatim`（`:115-117`）+ `merge` | `FIG-AUDIT`。三组不能互相抵消是高价值表达。 |
| `:160-194` 独立图件、最终 PDF、退化三轮检查 | `preserve_semantics_rewrite` | `FIG-AUDIT`。保留修复后重生成/重编译/再看。 |
| `:196-205` 追溯字段 | `merge` | `PROJECT-LINEAGE`/图件 registry。 |

能力缺口：本文件几乎没有工程构图的正例、投影视角选择、图元布局约束、SVG/CAD 实施程序；不能单靠增加“更严格的美观门”补齐，必须由 `FIG-SCHEMATIC` 提供做法和参考资产。

### 4.6 `skills/05-audit-protocol.md`

| 源范围 | 处置 | 去向与判断 |
|---|---|---|
| `:35-175` 概念/规划/端到端链、缺陷三分、隐含可执行性、最早层修复 | `preserve_semantics_rewrite`，三分法 `preserve_verbatim` | `EVIDENCE`/`VERIFY`。 |
| `:176-341` 数字、文风、摘要与可理解性 | `merge` | `MANUSCRIPT-EXPRESSION`；不再与 `03`、`13` 并列重复。 |
| `:342-388` 修复循环、图表三组审计 | `merge` | 通用 audit loop + `FIG-AUDIT`。 |
| `:389-520` 标题、公式/代码、解释、段落闭环、常量、离散/连续 | `merge` | `MODEL-SPEC`、`SOLVE-RESULT`、`MANUSCRIPT-*`。 |
| `:521-638` 图表信息增量、逐问主链、全文语言、留白浮动 | `merge` | `FIG-*`、`MANUSCRIPT-*`、`LATEX-RENDER`。 |
| `:639-678` 脚本、源格式、数字追踪 | `merge` | `PROJECT-LINEAGE`/`LATEX-RENDER`。 |

通用审计包只应保留：`声明/产物 → 双向证据链 → 缺陷类型 → 最早错误层 → 修复 → 重生成消费者 → 再验收`。其余专业检查回到专业能力包，避免审计协议成为第二本全 skill。

### 4.7 `skills/06-weiwei-norms.md`

- `:22-51` 引用挂载、编号集合核对：`preserve_semantics_rewrite`，并入 `LITERATURE-EVIDENCE`/`DELIVERY`。
- `:55-114` 人称、时态、小节/公式/图表观察：`merge` 到 `MANUSCRIPT-EXPRESSION`/`LATEX-RENDER`；“通常结构”只能是条件建议。
- `:118-133` 支撑材料与“评委三大误区”：前者 `merge` 到交付，后者 `retire` 为来源话术；只保留“评委可见证据不能被后台工作替代”的通用语义。

### 4.8 `skills/07-algorithm-reference.md`

- `:14-65` 最短路/MST/指派/0-1：`preserve_semantics_rewrite` 为按需参考，重点保留适用边界，不进核心运行规则。
- `:66-90` 排序法、多目标、熵权/灰色关联：`preserve_semantics_rewrite`，保留“评价排序不等于优化”和权重证据要求。
- `:91-119` 精确法优先、启发式、随机性、多目标：`preserve_semantics_rewrite` 到 `MODEL-SPEC` 的选择附录；不能把算法清单当候选生成权威。
- `:121-136` Python 库速查：`retire` 出规则正文，改为可更新的技术 reference；API/库名有时效性。

### 4.9 `skills/08-literature-search.md`

- `:15-36` 逐问触发与禁止事后找支持文献：`preserve_verbatim`（`:27-36` 中短段）+ `merge` 到 `LITERATURE-EVIDENCE`。
- `:38-53` 语义/选模/规格/边界四轮搜索：`preserve_semantics_rewrite`，这是“检索不是一次性阶段”的完整程序。
- `:55-99` 查询、纳入、显性记录：`preserve_semantics_rewrite`；固定文件名变为推荐 schema/asset。
- `:101-128` 来源角色、产出、完成门：`preserve_semantics_rewrite`；`:128`“文献准备不替用户选模”保留原句。

### 4.10 `skills/09-robustness-checker.md`

- `:14-18` 范围必须来自机制，固定 ± 网格只可探索：`preserve_verbatim`。
- `:20-40` 基线、扰动、约束、穷举：`preserve_semantics_rewrite` 到 `VERIFY-UNCERTAINTY`。
- `:44-60` 从声明到失效机制、固定方案与重优化分开：`preserve_verbatim`（`:57-60`）+ `merge`。
- `:64-69` 反模式：保留为负例；不能单独承担完整不确定性分析，需与后续 `36` 合并。

### 4.11 `skills/10-json-handoff.md`

- `:13-25` producer/consumer/schema、数据图与非数据图来源：`preserve_semantics_rewrite`；标题改为 `artifact lineage`，不以 JSON 为中心。
- `:27-59` 依赖、头部示例、基线：`merge` 到 `PROJECT-LINEAGE`；头部格式作为 asset/例子。
- `:61-87` 清单、运行身份、失效传播：`preserve_semantics_rewrite`。
- `:89-96` 历史真实性：`preserve_verbatim`；禁止为补档伪造时间线，事后重建必须标明。

### 4.12 `skills/11-paper-finalizer.md`

- `:15-74` 论文结构示例：`merge` 到示例资产，`retire` 其固定目录权威身份。
- `:76-143` 官方提交和 AI 使用：`preserve_semantics_rewrite`；任何当届条款、期刊政策和年份必须实时核验，旧文字不直接执行。
- `:145-225` 大型终稿清单：`merge` 到各包验收，不保留总重复表。
- `:227-258` 工作摘要/终稿与反模式：`merge` 到 `MANUSCRIPT-EXPRESSION`/`DELIVERY`。

### 4.13 `skills/12-source-audit-and-provenance.md`

- `:14-47` 规则位阶与解释来源：`:16` `preserve_verbatim`；其余 `preserve_semantics_rewrite`，外部链接/政策按当前版本核验。
- `:49-111` 逐文件审计与知识迁移：`merge` 到 `SKILL-EVOLUTION`；按哈希去重有用，但“整项目复读”风险分级。
- `:113-145` 反馈只读沉淀：`preserve_verbatim`（`:126-136` 可分短段保留）。这是本轮 V15 迁移最直接的优秀程序：现象/理由/推论分离、个案→判据、先查已有、只补最小缺口、只读不扩权。
- `:149-245` 人工主导、实质控制、掌握自检：`preserve_semantics_rewrite` + `merge` 到 `KERNEL`/`QUESTION-LIFECYCLE`；自检不得包装为认证。
- `:247-284` 披露粒度、污染信号、交付：`preserve_semantics_rewrite` 到 `DELIVERY`/`SKILL-EVOLUTION`。

### 4.14 `skills/13-excellent-paper-expression.md`

- `:27-49` 学结构不抄文本、审计不授权修改：`preserve_semantics_rewrite`。
- `:51-65` 来意/定义/动作/理由/证据/落点六功能：`preserve_verbatim`，作为诊断语言而非句子配额。
- `:69-185` 摘要准入、自足、删除、双向追踪：`merge` 到 abstract 子包；`:110-111`“成本不自动取得摘要席位”原样保留。
- `:187-260` 各部分表达次序：`merge` 到相应 manuscript 子包。
- `:262-285` 判断—理由—证据闭环：`preserve_semantics_rewrite`，高风险才生成结构记录；`:282-284` 已明确常态不强制五字段，应保留这个例外。
- `:286-320` 句法、三列局部改写、定稿：`preserve_verbatim`（`:309-310`）+ `merge`；避免为模仿优秀语气整段重写。
- `:322-347` 研究依据：保留在 provenance，不进运行提示。

### 4.15 `skills/14-session-handoff.md`

- `:14-29` 交接字段：`preserve_semantics_rewrite` 到 `RECOVERY`。
- `:30-75` 新会话恢复与持续检查点：保留事实重建、摘要非权威、准确暂停位置；改为 R0/R1/R2 风险级恢复。
- `:77-99` 主动收尾一律全项目复读：`retire` 其日常硬门身份；里程碑/正式交付可触发高风险模式。
- `:100-127` 管道连续性、评审可见、安全：`merge` 到 `PROJECT-LINEAGE`/`DELIVERY`。

### 4.16 `skills/15-pipeline-methodology.md`

- `:9-40` 目的/外部方法论取舍：`:11-13` `preserve_verbatim`；阶段不是自动求解器/评分器。
- `:42-94` 十类工作、逐问纵切、避免横向认知过载：`preserve_semantics_rewrite` 到 `QUESTION-LIFECYCLE`。
- `:95-179` 逐问独立性、路由、可执行清单：`preserve_verbatim`（`:121-122` 等短句）+ `merge`。
- `:181-239` 技术完成/理解完成、文本化读者层、术语最小化：`merge` 到人工决定能力。
- `:241-289` 任务矩阵、声明台账、变更影响：`preserve_semantics_rewrite`；按项目复杂度启用，不强制三套账同时存在。
- `:290-309` 已批准决定兼容继承：`preserve_verbatim`；不要把兼容已批准决定反复包装成新批准问题。
- `:311-331` 项目状态边界、流程≠论文目录：`preserve_semantics_rewrite`。

### 4.17 `skills/16-data-audit-methodology.md`

- `:12-29` 数据方法文件先于主脚本、只读诊断边界：`preserve_semantics_rewrite`。
- `:30-48` 统计单位与伪重复：`preserve_semantics_rewrite`，不可被 `data minimum` 压掉。
- `:49-65` 原始/结构化/派生/纠正/设置、解析显式失败、结构空值≠缺失：`:61-65` `preserve_verbatim`。
- `:67-80` 逐字段对账、独立性：`:80` `preserve_verbatim`。
- `:82-94` 异常只生成候选、数据处理需人审：`preserve_semantics_rewrite`，保留默认不因极端删除。
- `:95-127` 证据能力与审计图：`merge` 到 `DATA-AUDIT`/`FIG-DATA`。
- `:129-153` 相似性不等于身份、独立复核、完成门：`preserve_semantics_rewrite`。

## 5. V2 逐文件/逐规则族审计

### 5.1 `skills_v2/SKILL.md`

| 源范围 | 处置 | 判断 |
|---|---|---|
| `:8-26` concise rule authority/source portfolio 边界 | `preserve_semantics_rewrite` | “一个日常权威、历史不反向授权”正确；但把详细 manuscript/figure/LaTeX 程序先迁移才可执行，造成能力不可达，应改为 atoms 指向完整 capability，而不是历史层。 |
| `:28-45` A–E 与迁移治理 | `merge` | 并入 `SKILL-EVOLUTION`，不在每次工作加载。 |
| `:47-74` 新会话/里程碑全项目恢复 | `preserve_semantics_rewrite` | 保留证据类型与同步证明；退役所有 milestone 一律读完全部唯一文本的日常硬门。 |
| `:76-107` 每次 manuscript 开始完整读多文件、整稿读全部 rules | `retire` 默认硬门；保留高风险模式 | 这是后续控制面过重的起点之一。改为按被改职责加载完整包，并在跨包/正式审计时扩大。 |
| `:109-147` 非跳过流程、逐问证据链 | `preserve_semantics_rewrite` + `merge` | 并入 `QUESTION-LIFECYCLE`。 |
| `:149-173` 人工决定/理解/授权边界 | `preserve_verbatim`（关键边界）+ `merge` | 与 V1/V4 controller 合并；不重复多份。 |
| `:175-209` source portfolio 路由与“先迁移再应用” | `retire` 旧架构 | 保存迁移来源功能；运行时改为从 atom 直接读取完整 capability。 |

### 5.2 V2 concise active rules

V2 `rules/10,20–24,30,40,50` 与 V3 对应文件的区别基本只是尚未加入稳定 ID；处置按独立规则如下：

| V2 文件/范围 | 处置 | 能力包 |
|---|---|---|
| `rules/00-execution-gates.md` 全文 | `preserve_semantics_rewrite` | 结构优先、失败传播、人工推广并入 `MANUSCRIPT-STRUCTURE`/`KERNEL`；完整阅读证明、七级状态和第6级全套证据只留 full-audit 模式。 |
| `rules/10-global-manuscript-rules.md` 段落、术语、数据、现实锚定、证明强度、跨载体、章节职责、连续阅读 | `merge`；M-02/M-05/M-07/M-08 语义必须保留 | `MANUSCRIPT-EXPRESSION`/`EVIDENCE`。每段强制八字段表退役为普通编辑默认，只在高风险段/专项审计启用。 |
| `rules/20-front-matter.md` | `merge`，摘要链/盲读保留 | abstract 子包；不保留独立重复权威。 |
| `rules/21-background-restatement-analysis.md` | `merge` | `MANUSCRIPT-STRUCTURE`。保留背景/重述/分析职责差异和“难点→结构→方向→理由→边界”。 |
| `rules/22-assumptions-symbols-data.md` | `merge` | `MODEL-SPEC`/`DATA-AUDIT`。假设分类、符号稳定、处理可追溯。 |
| `rules/23-model-solution-results.md` | `merge` | `MODEL-SPEC`/`SOLVE-RESULT`/`VERIFY`；这是简洁验收层，不是足够的实施教程。 |
| `rules/24-evaluation-conclusion-references.md` | `merge` | `MANUSCRIPT-EXPRESSION`/`LITERATURE-EVIDENCE`。 |
| `rules/30-figures-tables-layout.md` | `merge`，字体探测程序保留 | `FIG-*`/`LATEX-RENDER`。V-02–V-06 的“声明字体≠实际嵌入”很强；硬编码 Windows 字体示例移 asset。 |
| `rules/40-evidence-provenance.md` | `preserve_semantics_rewrite` + `merge` | `PROJECT-LINEAGE`/`EVIDENCE`。正反向链和一修全修保留。 |
| `rules/50-governance-handoff.md` | `merge` | `KERNEL`/`RECOVERY`/`DELIVERY`；草稿/正式、用户确认、变更传播。 |
| `rules/rule-ownership-map.md` | `merge` 到机器可读 conservation map | 其“一个语义一个 owner”保留；不把来源 detail 降为不可执行档案。 |

### 5.3 V2 source portfolios 的新增与处置

- `source-portfolios/01,04,06–16`：与 V1 同哈希，全部 `merge`，具体判断见第4节。
- `source-portfolios/02-latex-setup.md:187-214`：只加入“规则已迁到 `../rules/30`”的历史说明。`retire`；相对职责随目录重构即失真，真实字体程序直接归 `LATEX-RENDER`。
- `source-portfolios/03-paper-content-rules.md:37-57`：加入 reader-first 起草/结构门，`preserve_semantics_rewrite` 到 `MANUSCRIPT-STRUCTURE`；结构失败不应靠句子润色掩盖。
- `source-portfolios/05-audit-protocol.md:35-44`：加入 reader-first audit 与七级状态要求。结构先于局部审计 `preserve_semantics_rewrite`；“全部模块强制七级状态”`retire` 日常身份。
- `source-portfolios/17-reader-first-manuscript-audit.md`：
  - `:3-15` 结构、术语、机器证据/表达、人审边界：`preserve_semantics_rewrite`。
  - `:17-31` 全规则完整阅读证明：仅保留 full-skill/full-manuscript audit 模式，日常 `retire`。
  - `:33-71` 全文职责与问题背景：`merge` 到 `MANUSCRIPT-STRUCTURE`。
  - `:73-90` 每段八字段记录：`retire` 常态硬门；改为高风险段落/抽样审计模板。
  - `:92-140` 术语首用、无术语复述、数据—解释：`preserve_semantics_rewrite`；`:123-124` 明确“复述是审计工具，不机械写入论文”，应保留。
  - `:141-168` 七级状态与失败传播：失败传播保留；七级统一状态合并为较轻的 draft/reviewed/approved + defect state。
  - `:170-200` 每次编译回归表与第6级九项证据：转为正式整稿审计 checklist，退出普通编辑路径。
- `source-portfolios/legacy-SKILL.md`：`merge`/archive。它保存 V1 全编排并加入 reader-first 入口，不能成为第二控制器；其详细 stage 内容按第4节拆入能力包。

## 6. V3 逐文件/逐规则族审计

### 6.1 `skills_v3/SKILL.md`

- `:8-21` 每个实质请求先回执、读所有路由规则：`preserve_semantics_rewrite`；退役普通任务强制 receipt，保留任务分类与完整包读取。
- `:25-30` K-01 summaries only as hypotheses：`preserve_verbatim`。
- `:31-43` K-02 全读门：`preserve_semantics_rewrite` 到风险级 `RECOVERY`。
- `:45-53` K-03 earliest invalid layer：`preserve_verbatim`/`merge` 到 controller。
- `:55-66` K-04 人工理解与兼容继承：`preserve_verbatim`/`merge`。
- `:68-85` K-05/K-06 逐问职能和 no unproved skip：逐问职能 `preserve_semantics_rewrite`；对每条条件规则强制举证跳过 `retire` 为日常门。
- `:87-96` K-07 evaluator-visible chain：`preserve_verbatim`/`merge` 到 manuscript atom。
- `:98-115` 路由矩阵：`retire` 旧文件路由，迁移成 atom→capability dependency graph。
- `:117-161` start/execute/close 与轻/重段落审计：`preserve_semantics_rewrite`。`:156-158` 的风险分层思想比“所有段同样重审”更值得继承。
- `:163-181` stop/report 与历史源：停止条件保留；“先恢复进 active owner 才可使用历史 detail”由 capability 包取代。

### 6.2 V3 新执行规则

| 文件 | 独立规则处置 |
|---|---|
| `rules/00-execution-gates.md:5-90` | G-03 结构门、G-06 失败传播、G-08 人工门 `merge`；G-02 全读证据、G-04 七级状态、G-05全套证据改为 full-audit 模式；G-07 真实复发转回归 `preserve_semantics_rewrite`。 |
| `rules/01-execution-receipt.md:3-63` | R-01/R-02/R-04 的 scope、allowed/prohibited、completion scope 语义保留到 controller 内部；R-03 每个跳过项证明和“每个实质任务落盘”退出常态；R-05 validator 只用于 skill release/高风险节点。 |
| `rules/05-project-lifecycle.md:3-63` | L-01 恢复合并；L-02 题目身份保留；L-03 十二职能表 `preserve_semantics_rewrite` 为 per-question task card；L-04 文献触发、L-05双层理解、L-06候选准入、L-07传播均保留。该文件是 V3 最成功的能力索引之一。 |
| `rules/rule-ownership-map.md:1-23` | `preserve_semantics_rewrite` 到 conservation map；`:19-23`“历史存在不能证明活动覆盖”原样保留。 |

### 6.3 V3 稳定-ID质量层

| 文件/规则 | 处置 | 去向 |
|---|---|---|
| `rules/10-global-manuscript-rules.md` M-01–M-12 | `merge` | 作为 manuscript atoms；M-01 全段表只在高风险/整稿模式触发，M-02–M-10 保留语义。 |
| `rules/20-front-matter.md` F-01–F-04 | `merge` | abstract/front-matter atoms。 |
| `rules/21-background-restatement-analysis.md` B-01–B-03 | `merge` | manuscript structure atoms；B-03 的边界反例和选模理由保留。 |
| `rules/22-assumptions-symbols-data.md` A-01–A-03 | `merge` | assumptions/data atoms。 |
| `rules/23-model-solution-results.md` S-01–S-12 | `merge`，稳定 ID 可继承 | model/solve/result/verify atoms；不能替代 V1 的推导、反事实与算法回放程序。 |
| `rules/24-evaluation-conclusion-references.md` C-01–C-04 | `merge` | evaluation/conclusion/reference atoms。 |
| `rules/30-figures-tables-layout.md` V-01–V-12 | `merge` | V-02–V-06 的字体探测步骤进入 `LATEX-RENDER` 完整包；V-07–V-09 作为 visual atoms/审计；V-10–V-12 进入 render。 |
| `rules/40-evidence-provenance.md` E-01–E-04 | `preserve_semantics_rewrite` + `merge` | 双向链、冻结输出、来源身份、一修全修。 |
| `rules/50-governance-handoff.md` H-01–H-05 | `merge` | controller/receipt/delivery；避免重复批准语言。 |

### 6.4 V3 references

- `references/rule-sources/01–17,legacy-SKILL.md`：全部 `merge`/archive，内容处置见第4、5节。**不要再作为无法正常路由的“细节坟场”**。
- `references/migration-ledger.md:1-31`：`preserve_semantics_rewrite` 为 conservation map；“按独立可触发/判定规则族迁移”正确。
- 同文件 `:33-45`：缺口修复记录留 archive；V3 的 receipt/稳定 ID 并非所有场景都需要活动化。
- 同文件 `:46-59`：`:52`“历史规则能构造活动规则无法阻止的真实失败”是极好 reopen 条件，`preserve_verbatim`；`:57-59` 明确结构脚本不能替代真实前向行为测试，也应保留。

## 7. V4 逐文件/逐规则族审计

### 7.1 `skills_v4/SKILL.md`

| 源范围 | 处置 | 判断 |
|---|---|---|
| `:8-22` 单一控制器/质量文件不授权 | `preserve_semantics_rewrite` | 控制面与能力面的分离正确。 |
| `:24-41` S0–S7、按组件状态 | `preserve_semantics_rewrite` | 组件态优于单一全局态；不要求每个微任务显式写全状态。 |
| `:43-67` action table 与 permission formula | `preserve_verbatim`（`:56-67`） | 这是最值得继承的控制器表达；用户授权、阶段许可、前置证据、人工决定四者同时满足。 |
| `:69-85` 全量恢复 | `preserve_semantics_rewrite` | 按风险分级，保留摘要非证据、原生载体和重复哈希。 |
| `:87-149` 决策包/keep_current/外部指导边界 | `preserve_semantics_rewrite`，关键边界原样保留 | `QUESTION-LIFECYCLE`。完整 YAML 不必每次落盘；方向性决定使用精简 decision card。 |
| `:151-171` rollback mapping/消费者 | `preserve_verbatim`（核心）+ `merge` | controller kernel。 |
| `:173-206` 每个实质任务 receipts | `retire` 日常强制；保留高风险 | 回执记录证据但不产生证据的句子保留。 |
| `:208-224` smallest quality routing | `preserve_semantics_rewrite` | 思想正确，目标应是最小“完整能力包”而非 33 行 summary。 |
| `:226-239` completion | `preserve_semantics_rewrite` | 正式交付仍保留人审/渲染/证据链。 |

### 7.2 V4 六个 quality files

- `rules/data.md:5-33`：`merge` 为 DATA 验收 atoms；身份/清理/证据能力/输出都正确，但缺解析分支、异常修复、对账程序，不能取代 V1 `16`。
- `rules/modeling.md:6-42`：`merge` 为 MODEL atoms；基线→缺陷→复杂化、`keep_current`、spec 字段、`object → relation → formula → role` 均保留。缺完整推导与求解叙述。
- `rules/verification.md:5-31`：`merge` 为 VERIFY atoms；独立复算、风险匹配、证明边界清晰。缺不确定性来源和范围证据程序。
- `rules/manuscript.md:5-53`：`merge` 为 manuscript atoms；整稿链、masking test、章节职责很好。它是验收纲要，不是写作能力包。
- `rules/visuals-layout.md:5-32`：`merge` 为 visual/render atoms；只规定任务、可读、可访问、编译/逐页看，**没有复杂图件如何构造**。不能作为绘图主模块。
- `rules/provenance-delivery.md:5-40`：`preserve_semantics_rewrite` + `merge`；双向链、authority、change propagation、draft/formal 很强。

### 7.3 `skills_v4/references/migration-ledger.md`

- `:5-36` 架构与责任映射：保留 archive/迁移依据。
- `:38-50` deliberate removals：`retire` 作为迁移原则。它把工具示例、目录树、算法目录、重复审计和来源依据整体视作可移除，却没有逐义务证明；V5 后来在 `skills_v5/references/migration-ledger.md:98-116` 明确撤回这一说法。
- `:52-64` known-risk coverage：作为测试意图保留，但表里“有规则即已覆盖”的判断不能等同真实行为覆盖。
- `:66-75` future migration rule：`preserve_semantics_rewrite`；“先找具体失败、分 permission/quality、加行为回归”保留，“避免恢复长段”必须增加前提：完整动作、例外和修复均已进入能力包。

## 8. V5 逐文件/逐规则族审计

### 8.1 `skills_v5/SKILL.md`

- `:8-38` controller/资源解析/详细层与验收层：单控制器和相对根解析 `preserve_semantics_rewrite`；详细+V3+V4“全部累计满足”改成 capability + atoms，不再并列全文。
- `:40-83` 状态/权限：与 V4 相同，`preserve_verbatim`（权限公式）/`merge`。
- `:85-136` recovery manifest：`preserve_semantics_rewrite` 为高风险 R2；普通续作不创建全清单。`:127-130`“清单不能证明私有认知”原样保留。
- `:138-200` 决策门：`preserve_semantics_rewrite`；keep-current 与批准范围保留。
- `:202-223` rollback：`preserve_verbatim`/`merge`。
- `:224-271` 回执与 validator：`retire` 日常必经身份，保留高风险恢复/正式推广/skill release。
- `:273-294` 详细文件路由：`retire` 现有文件堆路由；用 atoms 的 dependency closure 路由 1–3 个完整能力包。
- `:296-313` 精确哈希覆盖：迁入 `SKILL-EVOLUTION`/release tooling，不在项目工作运行时读取。
- `:315-327` completion：`preserve_semantics_rewrite`。

### 8.2 V5 rules 全覆盖处置

| V5 范围 | 文件身份 | 处置 |
|---|---|---|
| `rules/00` | V1 `SKILL.md` 精确副本 | `merge`；能力拆分见4.1，不保留第二入口。 |
| `rules/01–17` | V1/V2详细规则精确或 reader-first 超集 | `merge` 到完整能力包；逐文件判断见第4、5节。 |
| `rules/18–20` | V3 receipt/lifecycle/gates | `merge`；lifecycle 保留，receipts/gates风险分级，见第6节。 |
| `rules/21–29` | V3 stable-ID acceptance 精确副本 | `merge` 成 `atoms/`；稳定 ID 可继承，重复全文不再独立加载。 |
| `rules/30–35` | V4 minimum 精确副本 | `merge` 成 cross-check atoms；若与 21–29 同义则合一，并记录来源映射。 |

V5 的 exact integration 是安全的临时恢复策略，不应成为最终运行架构。特别是 `skills_v5/references/migration-ledger.md:57-68` 把 byte-for-byte 当作安全 baseline，这适合迁移阶段；下一版应在保留 atomic conservation map 和负例测试的条件下消除运行时重复。

### 8.3 V5 references

- `references/migration-ledger.md:5-35` 四层修复标准：`preserve_semantics_rewrite`，只用于**权限、恢复、证据身份、正式发布等可机械表示的高风险失败**；不能要求审美、写作逻辑、模型适切性都具备 schema+validator。
- `:37-74` 架构/exact acceptance：`merge` 到迁移档案。
- `:76-116` responsibility/preserved detail：`:110-116`“progressive routing 不等于删文本”原意保留，但实现改成完整能力包，不再精确全文累加。
- `:118-141` known risks/future migration：保留具体失败→owner→行为回归程序；不要把测试覆盖误写成全部能力覆盖。
- `references/qualified-skill-standard.md:3-35`：
  - `:3-4`“合格不是写得很严” `preserve_verbatim`。
  - `:6-22` 权威、状态、证据、权限、诚实边界 `preserve_semantics_rewrite`。
  - `:23-24` 可执行不过载 `preserve_verbatim`。
  - `:25-31` 迁移/前向/精确验收 `preserve_semantics_rewrite`；精确哈希只是临时保守策略，不作为永久双层运行要求。
  - `:33-35` “软约束”判定只适用权限/恢复/正式交付，不应泛化到审美与推理质量。
- `references/v1-integration-map.json`：`merge` 到 archive conservation map。哈希/来源/owner 很有用；`source-preserving-active-file` 不能证明逐义务语义和运行可达。
- `references/version-delta-map.json`：`merge` 到 archive conservation map。30 条 delta 的 source/owner/treatment/reason 字段保留；`reason` 不能单独证明合并无损。

## 9. 根 `skills/` 中后续修复：作为“V1–V5哪里仍不够”的证据

这些文件不归因于 V1，但既然位于审计目录，逐项处置如下。

### 9.1 `skills/rules/03-paper-content-rules.md` 后续增补

- `:56-64` 每条新改稿指令重读全部论文规则：`retire` 日常硬门；这是典型控制面过拟合。
- `:65-95` LaTeX 正文按一级标题唯一 owner：`preserve_semantics_rewrite`，仅在多文件正文、结构重写或协作冲突时触发。
- `:250-282` 摘要向全文传播矩阵：保留章节职责/禁止细节的语义；跨两个标题一律建矩阵和基线只用于高风险结构重写。
- `:682-693` 审计元话语不入正文：`preserve_semantics_rewrite`；保留上下文例外，不能靠关键词删除。
- `:707-783` 多步模型可跟随推导、物理来源桥：`preserve_semantics_rewrite` 到 `MODEL-SPEC`，这是 V1–V5 后来暴露的真实缺口。
- `:823-836` 共享基础不能替代逐问闭环：`preserve_verbatim`（短段）到 `MANUSCRIPT-STRUCTURE`/`SOLVE-RESULT`。
- `:845-906` 优化语义闭合与算法回放：`preserve_semantics_rewrite`；不固定标签、编号、每步一式。
- `:908-1047` 八功能、反事实、参数/多目标、命题边界：与 V1 既有内容 `merge`，消除重复。
- 根 ledger `skills/references/migration-ledger.md:232-243` 记录了先强制标签/编号/公式配额、后发现像操作手册并撤回的过程。此案例应作为 `SKILL-EVOLUTION` 的负例：**保存语义完整，不保存表面模板配额。**

### 9.2 `skills/rules/17-reader-first-manuscript-audit.md` 后续超集

- `:126-132` 审计工具不入正文：`preserve_semantics_rewrite`，合并到 manuscript meta-language atom。
- `:180-193` 增加传播、元话语和物理推导回归项：各自路由到对应能力包；不要把所有回归项永久塞进一个全稿清单。
- `:194-204` 跨章节修改强制回归表：仅保留高风险结构重写模式；普通局部改写 `retire`。

### 9.3 `skills/rules/18-execution-receipt.md` 与 `20-execution-gates.md` 后续超集

- `rules/18:28-46` 每轮规则哈希/范围/矩阵/基线：`retire` 普通 manuscript 任务必经身份；保留 formal audit 或高风险跨章节 mutation 模式。
- `rules/20:18-20,38-41` 同一窗口每条改稿重读、跨两标题一律矩阵：同上。
- `rules/20:43-100` 七级状态、九项证据、回归、正式人审：结构/失败传播/正式推广语义保留；七级和全证据只在完整论文审计使用。

### 9.4 `skills/rules/36-uncertainty-error-analysis.md`

- `:3-11` 每问来源审查但不机械做同一种试验：`preserve_verbatim`。
- `:13-29` 输入/数值/求解/模型形式四类来源：`preserve_semantics_rewrite` 到 `VERIFY-UNCERTAINTY`。
- `:31-40` verification/validation/uncertainty/sensitivity/robustness 分责：`preserve_verbatim`（可分短段）。
- `:42-65` S4 规格与 S6 闭环、固定方案/重优化、联合变化：`preserve_semantics_rewrite`。
- `:67-78` `not_triggered/quantified/bounded/tested/unresolved`：`preserve_semantics_rewrite`；作为证据状态，不扩张为项目状态机。
- `:80-95` 写作反模式：保留负例。
- `:97-159` 每问可信度链、方法—数理关系、摘要/正文、内部交叉求解边界：`preserve_semantics_rewrite`。重点保留“另一实现同值只是实现审计，除非产生误差/收敛/传播/决策新信息”。
- `:160-165` 外部标准：保留 provenance，使用时重新核验，不硬编码当前解释。

### 9.5 `skills/rules/37-scientific-figure-design.md`

- `:7-20` 图件任务卡与删除检验：`preserve_semantics_rewrite` 到 `FIG-DATA`/`FIG-SCHEMATIC`。
- `:22-42` 真实性映射与受力双向核对：`preserve_verbatim`（核心关系和“公式不能补题面几何”短段）。这是整个审计中最值得抢救的绘图能力。
- `:44-70` 工程/流程/数据图分类型范式：`preserve_semantics_rewrite`；反例与图类选择保留。
- `:72-86` 视觉系统：`merge` 到 `FIG-STYLE`。
- `:88-99` 工具选择：`preserve_semantics_rewrite`。Matplotlib、SVG/CAD/TikZ按对象选择；生成式位图不得承载精确几何/数值/拓扑。
- `:101-115` 高风险样板、人审、candidate admission≠replacement：`preserve_verbatim`（核心边界）+ `merge`。
- `:116-123` 自动/人工边界：`preserve_verbatim`；脚本不能判拓扑、力、证据和美感。
- `:125-135` 图件 registry 与论文闭环：`merge` 到 lineage/figure audit。
- `:137-169` 原题投影复原、符号合同、拆图、最终像素验收、非破坏替换：`preserve_semantics_rewrite` 到 `FIG-SCHEMATIC`，并配套 SVG primitives、碰撞检查和正反例资产。

### 9.6 根 references

- `skills/references/migration-ledger.md`：`merge` 到 archive；`:143-254` 必须保留版本标签，防止后续修复被误认成 V1。
- `skills/references/qualified-skill-standard.md`：与 V5 同哈希，处置见8.3。
- `skills/references/v1-integration-map.json`、`version-delta-map.json`：`merge` 到 conservation archive；根版本含后续 owner/hash，不作为纯历史快照。
- `skills/references/start_receipt.schema.json:3-19`、`end_receipt.schema.json:3-13`：V6 schema。`retire` 普通任务强制调用；保留为 R2/high-risk/formal release 的确定性 asset。字段有 `additionalProperties: true`，验证器也无法证明审美、理解或诚实执行。

## 10. 绘图模块下一版应怎样保存“完整能力”

### 10.1 `FIG-DATA`：数据、结果、优化与统计图

完整包必须包含而不是只列验收词：

1. **输入合同**：支持声明、冻结数据/模型、对象集合、基准、指标、单位、条件、误差/区间、正文位置。
2. **载体决策**：精确查询→表；趋势/分布/空间/权衡→图；简单结论→正文；图表并存时写不可替代职责（源 `skills/04:85-98,119-132`）。
3. **图类选择分支**：时间响应、分布、参数扫描、多目标、空间/拓扑分别给建议图类、禁止误导动作、何时例外（补源 `skills/rules/37:63-70`）。
4. **视觉编码程序**：先定义对象→视觉通道映射，再画；颜色有线型/形状/标签冗余；把 Okabe–Ito preset、线宽/字号 profile 放 `assets/styles/`，不在规则反复抄色值。
5. **正文闭环**：首次引用→可观察关系→本问结论→边界，不让“由图可知”代替推理。
6. **失败修复**：信息重复则删/换载体；最终尺寸过密则拆 panel、换表、减少非必要标签；数据/正文不一致先回证据层，不做美化补救。
7. **人审点**：新视觉系统/高风险图类只先审一张代表样板；相同系统批量图不逐张重复方向批准，但每张仍做内容与最终尺寸检查。

### 10.2 `FIG-SCHEMATIC`：结构、受力、机理、流程和工程图

建议以 `skills/rules/37` 为骨架，补齐 V1–V5 从未完整拥有的实施层：

1. **真值提取**：原题图/文字/附件/冻结公式逐项建立 `题面对象 → 几何/拓扑 → 数学变量 → 作用/信息流 → 图元`；来源不明项标 `unknown`，不能用常见装置脑补。
2. **视图规划**：决定主视图、局部视图、剖面/投影；若一张图不能同时说清正交关系，拆“主几何＋局部结构”，不把所有信息挤在一图。
3. **语义骨架**：先画无样式骨架（对象、连接、坐标、力/流向），逐项与题面和方程双向核对；真实性未闭合只能内部草图。
4. **图元语法**：工程轮廓/内部构件/轴线/剖线各有线型层级；流程箭头只表示因果/依赖/数据流/循环；标签引线只指唯一对象；角弧、质心、铰点、力向量均有几何约束。
5. **工具分流**：数值图 Matplotlib；精确布局/工程标注优先 SVG；复杂投影可 CAD/矢量编辑；TikZ 仅在适配时；生成式位图不得承载精确几何、拓扑、受力或数据事实。
6. **约束化代码绘图**：用 `figure_spec.yaml/json` 保存对象、连接、锚点、符号、层级和最终尺寸；SVG 元素按 semantic group/id 输出，允许检查 bbox、文本/线碰撞、引线终点、像素偏差。脚本负责机械碰撞，不负责判断拓扑真伪或审美。
7. **样板与人工确认**：高风险代表样板依次审内容→图类→层级→最终尺寸→灰度→用户技术/审美确认，再批量；候选通过、准入目录、替换正文引用是三个不同动作。
8. **最终像素循环**：渲染真实交付尺寸 PNG，查看而不是只读 SVG 坐标；修复→重渲染→检查新碰撞；最后进入 PDF 页内再验收。
9. **正反例资产**：至少建立一套“正确/错误受力箭头”“错误脑补几何”“标签指向歧义”“源图清楚但页内不可读”“流程线无语义”“拆图前/后”的小图库。V1–V5 几乎没有这些视觉正反例，这是不能靠规则文字补完的资产缺口。

### 10.3 `FIG-AUDIT` 只留四个独立判定，不再重复整本规则

1. **truth**：对象/拓扑/力/数据是否真；
2. **information**：是否承担不可替代声明；
3. **visual**：最终尺寸、层级、碰撞、灰度是否可读；
4. **integration**：题注/正文/PDF/来源/版本是否闭环。

自动检查只能支持第3和第4的一部分。人工确认集中在真值歧义、审美样板、准入与替换，不把每次颜色或坐标微调都升级为控制器决策。

## 11. 最值得原样保留的短句/短段

以下只摘最小独立表达，其他内容按上文语义重写：

1. `skills/SKILL.md:289-292`

   > Use the stages as a reasoning map, not as an autonomous workflow engine. … Do not impose scoring, automatic progression, fixed artifact counts, or tool-driven decisions on the user.

2. `skills/SKILL.md:523-525`

   > Cross-question consistency means compatible facts and interfaces agree; it does not mean methods, formulas, validation tests or section structures must look alike.

3. `skills/SKILL.md:559-567`

   > Classify it as a communication omission, implementation/specification mismatch, or modeling omission before choosing a fix. … Correct the earliest faulty layer, regenerate every downstream artifact, and then revise the paper.

4. `skills/01-contest-project-pattern.md:48-54`

   > 创建空目录只证明脚本执行过，不证明项目已经初始化完成。

5. `skills/03-paper-content-rules.md:314-315`

   > 问题分析解释“这是什么问题、为什么这样分问、通常怎样处理、本文为何选择当前方向”，但不提前展开具体算法实现。

6. `skills/03-paper-content-rules.md:540-541`

   > 逐句审计不能只问“这句话是否正确”，还要问“它在当前位置承担什么职责、前一句能否推出它、后一句是否仍需要它”。

7. `skills/03-paper-content-rules.md:657-662`

   > 公式解释的审计单位是数学职能，不是 LaTeX 环境、编号或换行数量。

8. `skills/03-paper-content-rules.md:742-745`

   > 论文是数学论证，不是程序运行报告。

9. `skills/04-figure-generator.md:15`

   > 图像必须独立承担一种不可由相邻表格或正文替代的表达任务。

10. `skills/04-figure-generator.md:115-117`

    > 三组独立判定，不能用高清、美观或排版整齐掩盖内容错误，也不能以数值正确为由接受最终尺寸下不可读或表达形式不合适的载体。

11. `skills/08-literature-search.md:32-33`

    > 不得先凭常识固定模型，再只寻找支持既定选择的文献。

12. `skills/08-literature-search.md:128`

    > 文献调查通过只证明证据准备充分，不替用户选择模型。

13. `skills/09-robustness-checker.md:16`

    > ±5%、±10%、±20% 只能作为缺少先验时的探索网格，不能冒充现实不确定性。

14. `skills/10-json-handoff.md:91-95`

    > 不得为补齐档案而虚构过去的时间戳或操作。只能根据文件哈希、运行清单和产物依赖重建“可确认的历史”，并显式标为事后重建。

15. `skills/12-source-audit-and-provenance.md:16`

    > 不能把“已有文件”误当成“可靠知识”。

16. `skills/12-source-audit-and-provenance.md:126-129`

    > 对每条反馈执行“个案—判据”转换……只有现有规则无法触发、无法执行或无法验证时才补充最小规则。

17. `skills/12-source-audit-and-provenance.md:170-171`

    > 人工主导不是在终稿阶段补一句“已审核”，而是在人会改变研究方向的节点真正拥有知情选择权。

18. `skills/13-excellent-paper-expression.md:53-60`

    > 建模论文的基本表达单元不是“显得专业的长句”，而是……来意、定义、动作、理由、证据和落点。

19. `skills/13-excellent-paper-expression.md:110-111`

    > 代码很复杂、运行很久或使用了规范算法名，不自动取得摘要席位。

20. `skills/13-excellent-paper-expression.md:309-310`

    > 禁止为了模仿“优秀语气”而全段重写。

21. `skills/16-data-audit-methodology.md:61-65`

    > 解析器必须显式失败，不能静默猜测。……结构性空值与缺失值必须分开。

22. `skills/16-data-audit-methodology.md:80`

    > 不能用“摘要数字相等”代替逐字段对账，也不能用主脚本再次读取自己的输出证明自身正确。

23. `skills_v3/references/migration-ledger.md:52-54`

    > 历史规则能构造活动规则无法阻止的真实失败案例〔时，迁移重新标记为不完整〕。

24. `skills_v4/SKILL.md:56-67`

    > action is allowed in current state AND required exit evidence from earlier states exists AND required human decision is explicit and compatible AND the user's request authorizes the action.

25. `skills_v5/references/qualified-skill-standard.md:3-4,23-24`

    > 合格 Skill 不是“写得很严”……；可执行且不过载。

26. `skills/rules/36-uncertainty-error-analysis.md:9-11`

    > 每问都执行来源审查，但不机械执行同一种试验，也不强制建立名为“误差分析”的章节。

27. `skills/rules/37-scientific-figure-design.md:26-30`

    > 题面对象 → 几何/拓扑关系 → 数学变量 → 作用或信息流 → 图中元素。……公式可以约束动力学关系，但不能唯一确定题面未写明的……几何。

28. `skills/rules/37-scientific-figure-design.md:112-114`

    > “好看”不能批准内容错误，“正确”也不能批准最终尺寸下难读的图。候选图……准入项目仍是一次独立变更。

29. `skills/rules/37-scientific-figure-design.md:118-123`

    > 自动检查不能判断拓扑是否忠于原题、力是否正确、数据是否支持结论、标签是否真正拥挤或图是否美观。

## 12. 明确退役清单（退出活动运行，不删除历史）

1. 每个实质任务都必须产生 start/end receipt。
2. 每条用户局部改稿指令都重新读取全部论文规则并记录哈希/行段。
3. 每个未触发的条件规则都逐项写“不触发证明”。
4. 每个自然段都强制八字段审计表；改为高风险段/专项整稿模式。
5. 七级 manuscript 状态机作为所有模块的唯一状态；保留结构失败/表达失败/待人审等少数有行为差异的状态即可。
6. V3、V4、V1详细层三套同义 acceptance 全文同时加载。
7. 固定年份竞赛 AI 条款、固定外部政策结论、固定网址即当前权威。
8. 固定目录树、固定一级标题文件数、固定句数/标题/算法编号/每步公式配额作为跨项目硬规则。
9. 关键词/grep 命中自动判错；搜索只能定位候选并结合上下文。
10. generic algorithm catalogue 作为每次选模必读；改为题型触发的按需 reference。
11. 用结构 validator、文件存在、哈希相等或测试数量证明 agent 真正理解、审美合格、模型适切。
12. 把 source portfolio/reference 设为“文本可存但能力不可执行”的历史层；历史 provenance 与完整运行 capability 分开。

## 13. 覆盖核对与未决项

### 覆盖核对

| 目录 | 逻辑文本数 | 本报告覆盖方式 |
|---|---:|---|
| `skills` | 61 | `SKILL.md`、顶层01–16逐文件；`rules/` exact家族/后续超集/36/37；6个 references |
| `skills_v2` | 30 | `SKILL.md`；11个 active rules；18个 source portfolios（含17与legacy） |
| `skills_v3` | 33 | `SKILL.md`；13个 rules/ownership；migration ledger；18个 rule-sources |
| `skills_v4` | 8 | `SKILL.md`；6个 quality rules；migration ledger |
| `skills_v5` | 41 | `SKILL.md`；rules/00–35；4个 references |
| **合计** | **173** | **73 个独立内容哈希全部判定** |

### 未决项

1. **根快照精确年代**：`skills/` 混合了 V1 authority 与 V5/V6/2026-08 修复。若要生成法证级逐提交时间线，需要 Git/备份元数据；本报告只按文件内 ledger 和哈希可证事实归类。
2. **`rules/36` 的细分年代**：文件自称 V5 新增（`:5`），根 ledger 又记录 V6 四段链修复（`:164-173`）。应把 `U-01–U-07` 与 `U-07A` 后续段分开标版本，避免整文件误归 V5。
3. **V6–V14 当前控制器对接**：本报告不替代其他版本审计。V15 应先比较当前 controller 是否已实现 R0/R1/R2、组件态和人工门，再决定哪些历史控制语义只需 conservation mapping，不重复写入。
4. **视觉正反例资产缺失**：V1–V5 没有足够的用户认可工程图、代码与最终 PDF 成对样例。下一次迭代前最好收集 3–5 组“被用户接受/拒绝”的图件及原因；否则只能完整保留规则，无法校准“完美示意图”的审美分布。
5. **官方/外部政策时效**：本审计没有验证 2025/2026 竞赛 AI、Nature、字体和提交链接的当前有效性；这些必须转为运行时取证任务，而不是迁移旧结论。
6. **人审颗粒度**：历史文本在“方向决定、跨章节重构、版面变化、候选准入、正式替换”多处设确认。建议保留方向/模型现实/高风险图样板/正式发布四类实质确认；普通可逆局部修复的确认密度需用真实使用反馈定标。
7. **脚本范围**：按任务要求，脚本只用于理解规则语义和调用关系，未在本报告逐行评判其代码质量。未来重构确定新 schemas/assets 后，再审计哪些验证器仍有必要。

## 14. 给下一次迭代的最小实施顺序

1. 先建 machine-readable conservation map：`source path + line/rule ID → disposition → capability/atom/asset → regression/例子`。
2. 优先做四个最容易验证完整性的包：`DATA-AUDIT`、`MODEL-SPEC/SOLVE-RESULT`、`MANUSCRIPT-EXPRESSION`、`FIG-SCHEMATIC`。
3. 每个包从上表迁移完整“动作—例外—失败修复—正反例—人审点”，再写短 atom；严禁先写 atom 后凭印象补包。
4. 用 V3/V4 acceptance 做反向 coverage checklist，但合并同义条款，不按哈希继续保留三层活动副本。
5. 选真实任务做 forward test：只加载 controller + 相关 atoms + 1–3 个完整包；测试能否实际产出、解释失败并修复。通过后才退休旧活动路由，旧全文仍留 archive。

