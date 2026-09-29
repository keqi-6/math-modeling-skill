# Skills V6–V10 全量规则审计与下一轮保真迁移建议

审计日期：2026-08-27  
审计范围：`/mnt/d/AI/AI_program/2021（第四题）/总skill/skills_v6` 至 `skills_v10`  
性质：只读审计；源版本未修改。本文件是唯一新增文件。

## 0. 结论先行

V9 的控制架构是一次明显进步，V10 的原子 owner、全语义 envelope、事务与维护验证也很强；但“迁移证明通过”不能推出“V8 的领域做法仍可达”。主要原因不是简单删字，而是迁移基线分辨率发生了两次下降：

1. V9 虽把 34 份 V8 详细规则、7,038 行文本逐字装入 10 个模块，但路由只到模块级，若一份规则横跨多个任务语境，文本可以存在却在正确时机不可达。
2. V10 的语义迁移权威从 V9 的 51 条 capability registry 摘要出发，而不是从 V8 的 7,038 行方法条款出发。V10 自己也明确：V1–V6 谱系不是逐行 V10 等价证明（`skills_v10/skills/references/migration/legacy-coverage.json:5`），crosswalk 不自行声称语义等价（`.../capability-crosswalk.json:4,41`）。
3. V10 只有 216 行、6,547 字符的方法提示，相当于 V8 活动详细规则方法文本的约 3.1%。206 个 atom 的 `effect` 共约 18,896 个 JSON 字符，能保存“必须得到什么”，但大量丢失“如何做、先后顺序、例外、修复路径、例子、何时人审”。
4. V10 的 206 个 atom 中 205 个为 `MUST`、仅 1 个 `SHOULD`；190 个没有 trigger predicate，169 个没有 exception，157 个二者都没有，而 206 个都写了 `outcomes.not_applicable`。但 `outcomes` 被声明为非规范说明（`skills_v10/skills/SKILL.md:16`、`references/ownership-contract.json:19-24`），不能弥补规范 trigger/exception。结果是“写了不适用”不等于运行时可合法不适用。
5. 最严重的可执行回归是 S6：V8 明确 E2 只在数值风险触发，E3 每问强制，E4 在无现实对照时可 `not_triggered`（`skills_v8/skills/rules/32-verification-minimum.md:7-18`；`09-robustness-checker.md:14-23`）。V10 状态机却要求 S5→S6 必须有 E1+E2、S6→S7 必须有 E1+E2+E3+E4（`skills_v10/skills/references/state-machine.json:15-17`），且状态管理器只把 `status=pass` 计入门禁（`scripts/state_manager.py:214-227,317-320`）。这不是文字模糊，而是把 V8 的条件例外改成了不可通过的硬门。
6. V7 新增的逐问 `solution_brief` 是另一个确定性迁移缺口：V8 有专门 route、固定九项解释顺序和队友人审（`skills_v8/skills/rules/01-contest-project-pattern.md:48-73`；`references/routing-registry.json:87-107`）。V9 文本仍在 `references/modules/project-platform.md:63-86`，但 23 条 route 无 solution-brief route，V7 native ledger 的 9 项也没有它（`skills_v9/skills/references/migration/native-capabilities.json:4-12`）；V10 完全无对应 atom/route，并把 `solution_brief.md` 列为默认不创建（`skills_v10/skills/references/artifact-contract.json:18-27`）。

下一轮不应回到“所有细节常驻上下文”，也不应继续用一句 capability gloss 代替细节。建议采用“轻量 atom + 可寻址完整 capability packet + 任务组合 manifest”：atom 只拥有后果和适用性；packet 无损保存顺序、选项、例外、例子、失败修复、人审边界；route 返回 atom envelope 后，按 capability ID 装配完整 packet。详细方案见第 9 节。

## 1. 范围、口径与覆盖统计

### 1.1 实际覆盖

- V6/V7/V8：`SKILL.md`、38 份 `rules/*.md`、全部 `references/*.md|json`，以及用于理解路由、回执、迁移、图件验证和状态链的脚本。
- V9：`SKILL.md`、10 份生成模块、3 份短方法/控制 Markdown、全部 route/state/artifact/receipt/capability/migration JSON 和关键构建、解析脚本。
- V10：`SKILL.md`、9 份 atom JSON（206 atoms）、7 份 method notes、全部 machine/migration/release contract，以及 resolver/state/release/eval 的关键实现。
- V8 规则共 38 文件、7,356 行、270 个二级标题、451 个二至四级标题。下面的文件级 ledger 逐一列出全部二级规则群；其行段 disposition 同时覆盖标题下所有子标题、列表、例子与反模式。
- V6/V7/V8 `SKILL.md + rules + Markdown references` 的全部标题数分别为 523、575、582。V6→V8 多数详细规则逐字继承；因此用 V8 作为共同正文基线，并另列所有 V6→V7、V7→V8 差异，避免重复三遍同一规则。

### 1.2 规模

| 版本 | 全包文件 | Markdown | JSON | Python | 全包行数 | 规则/方法核心 |
|---|---:|---:|---:|---:|---:|---|
| V6 | 69 | 41 | 4 | 16 | 11,407 | 38 rules / 7,196 行 |
| V7 | 92 | 44 | 11 | 31 | 59,434 | 38 rules / 7,260 行；新增 45k 行能力账本 |
| V8 | 98 | 44 | 11 | 33 | 59,874 | 38 rules / 7,356 行 |
| V9 | 53 | 14 | 19 | 19 | 66,587 | 10 modules / 7,284 行，由 34 个 V8 活动源生成 |
| V10 | 61 | 8 | 30 | 22 | 70,298 | 206 atoms / 15,795 JSON 行；7 notes / 216 行 |

迁移压缩的可比口径：V8 的 34 个 V9 活动详细源为 7,038 行、212,020 Unicode 字符；V9 模块为 7,284 行、216,336 字符（增加生成头，正文近乎无损）；V10 七份方法提示仅 216 行、6,547 字符。V10 规则 JSON 的大体积主要来自重复的 scope/evidence/routes/tests 元数据，不等价于方法细节。

### 1.3 disposition 定义

- `preserve_verbatim`：措辞本身表达了不可轻易改写的顺序、例外、边界或反模式；原文应进入完整 packet 或谱系档案。
- `preserve_semantics_rewrite`：独立能力必须保留，但应去除旧路径、旧版本、固定模板或重复控制权，并改写为当前 owner 的清晰条款。
- `merge`：与其他文件描述同一能力的建设面、验收面或最低交叉检查；合并到一个 capability packet，但保留不同视角的 checklist/negative example，不能只留一句摘要。
- `retire`：从运行时规范退出；通常仍在 immutable lineage 中原样保留。退休理由包括第二控制器、过时 schema、固定脚手架、无条件全文复读、旧路径/版本声明或没有独立信息增量。

## 2. V6→V8 谱系与版本增量

### 2.1 共同基线与实际改动面

38 份规则中，V6/V7/V8 三版逐字相同的有 21 份：`02,04,05,06,07,08,10,12,13,15,21,22,23,24,26,28,30,31,34,35,37`。V6→V7 改动后 V8 未再改的有 `00,01,11,14,16,17,18,19,20,27,29`；V7→V8 新改 `09,25,32,33`；`03,36` 两轮都改。

V8 自身仍有版本身份漂移：`skills_v8/skills/SKILL.md:6` 标题仍写 “Controller V7”，且没有 V8 metadata。V9 冲突决议 C-001 才修复这一点（`skills_v9/skills/references/migration/conflict-decisions.json:6`）。

### 2.2 V6→V7 的重要新增/修复

| 增量 | 源 | disposition | 审计判断 |
|---|---|---|---|
| R0/R1/R2 比例恢复，普通“继续”不强制全量 | `skills_v7/skills/SKILL.md:89-105`; `rules/14:31-58` | `preserve_semantics_rewrite` | V9/V10 保留并做得更好；应继续作为核心控制能力。 |
| 逐问 `solution_brief`、九项顺序、技术交接≠论文 | `rules/01:48-73`; `SKILL:323-332,349` | `preserve_verbatim` | V9 字节存在但 route 失联；V10 无 owner。下一版必须恢复为条件触发的完整 packet。 |
| 产物类别与 planning/docs/paper 边界 | `SKILL:323-332` | `preserve_semantics_rewrite` | V10 lazy artifact 更比例；保留职责，不恢复固定目录和默认文件。 |
| 机器可读 routing registry 与 route reachability | `SKILL:334-359`; `references/routing-registry.json` | `preserve_semantics_rewrite` | V9/V10 强化；但必须从“模块可达”提升为“capability packet 可达”。 |
| 假设应在每问 S4 冻结，而非做完第一问后补写 | `rules/03`，决议 `responsibility-decisions.md:134-139` | `preserve_verbatim` | 典型有价值 repair，V10 的 spec assumptions 只保留结果，未保留该失败史。 |
| 待审数据方法是 candidate，不是 authority | `rules/16:27-28`; 决议 `responsibility-decisions.md:104-109` | `preserve_verbatim` | 应进入 data-treatment packet。 |
| 能力映射证明行为，不冻结历史字节 | `SKILL:389-393`; `responsibility-decisions.md:151-161` | `preserve_verbatim` | V10 采用；下一轮要把基线提升到完整 V8 source clauses。 |
| 无消费者工件/固定脚手架收敛 | `responsibility-decisions.md:177-196` | `preserve_semantics_rewrite` | V9/V10 的最优秀比例性改进之一。 |

### 2.3 V7→V8 的核心修复

V8 的唯一重大能力新增是 S6 双轴模型检验：

- E1：实现符合性；E2：只有存在近似、离散、迭代、搜索、容差或舍入风险时触发。
- E3：每问必须针对一种实质结构失败风险执行风险匹配检验，不得 `not_triggered`。
- E4：只在实测、实验、留出观测或可靠现实基准存在时触发；否则允许 `not_triggered`，但必须限制现实域声明。
- 每问论文至少可见一项实质模型检验，但不强制同名章节、统一灵敏度或固定方法。

最佳原文在 `skills_v8/skills/rules/32-verification-minimum.md:7-18,30-59`、`09-robustness-checker.md:14-23,67-73`、`36-uncertainty-error-analysis.md:42-50,107-144`，迁移决议在 `references/responsibility-decisions.md:198-210`。disposition：E2/E4 的触发例外和 E3 的“至少一种风险匹配、非固定配额”应 `preserve_verbatim`；具体试验菜单 `preserve_semantics_rewrite`；多文件重复 `merge` 成一个验证 packet。

## 3. V8 38 份规则的逐文件/逐规则 disposition ledger

缩写：`V`=`preserve_verbatim`，`S`=`preserve_semantics_rewrite`，`M`=`merge`，`R`=`retire`。一项同时标 `S/M` 表示独立语义保留、但并入共同 packet；`R/M` 表示原文件或原 owner 退休、语义并入新 owner。

### 3.1 控制、工程、排版、论文与图表（00–09）

| 文件 | 全部二级规则群及 disposition | 建议能力包 |
|---|---|---|
| `00-project-orchestration.md` 771 行 | `R` 18 架构/路由；`S/M` 101 启动条件、175 首次动作、239 目录合同、298 十阶段工作图、728 文件创建、738 router；`V/S` 109 人工治理、707 交互、760 失败条件 | `project-orientation`、`human-decision`、`work-map`、`artifact-admission`；十阶段只能作工作地图，不作第二状态机。 |
| `01-contest-project-pattern.md` 229 行 | `S` 10 职责、16 接手、29 证据位阶；`S/M` 33 目录、98 代码、133 文档、177 交付检查、199 引用；`V` 48–73 逐问讲解稿、147–160 数字身份、213–229 人工主导；`S` 203 时变 AI 合规 | `solution-brief`、`engineering-conventions`、`numeric-lineage`、`human-control`；路径/格式按项目配置。 |
| `02-latex-setup.md` 275 行 | `V/S` 19 官方优先、43 源语法、209 编译、251 修改权限、268 编辑安全；`S/M` 23 主稿、146 图规、225 文件、236 排版；`R/recipe` 91 固定模板、158 固定 preamble | `latex-source-boundary`、`font-probe`、`compile-and-page-audit`；年份、字体文件名、模板值放 project profile。 |
| `03-paper-content-rules.md` 1,156 行 | `S` 13 强度、37 首稿门、97 摘要、359 问题分析、499 假设、652 叙述、709 推导、787 标题、865 求解、1077 精度、1094 引用、1109 结论、1124 摘要平衡、1153 支撑；`M` 23 文件导航、1115 优秀论文学习；`R` 每轮无条件全读/固定旧路径；`V` 关键修复 499–550、709–786、847–864、993–1060 | `manuscript-content` 下按 `abstract/problem-analysis/assumptions/derivation/solve/results/conclusion` 拆 packet，保留例子和反模式。 |
| `04-figure-generator.md` 205 行 | `V/S` 13 信息职责、85 载体选择、100 图后解释、113 三组审计、160 三轮视觉审计、196 追溯；`S/M` 32 视觉语义、70 格式；`R/recipe` 固定 Nature 采用、固定色值/点数/DPI 作为普适硬门 | `visual-common`、`visual-human-audit`、`visual-trace`; 与 27/34/37 合并但不压成 14 条 gloss。 |
| `05-audit-protocol.md` 688 行 | `S/M` 14 强度、20 导航、33 执行步骤及其全部审计子流程、649 脚本、665 源格式、675 数字追踪；`R` 全读/权限/固定路径控制语义 | `manuscript-audit`、`model-impact-repair`、`script-output-audit`。V9 把它误装进 verification module，导致稿件审计 route 不可达。 |
| `06-weiwei-norms.md` 133 行 | `S/M` 22 引用、63 表述、97 公式、107 图表、118 支撑；`S/profile` 55 人称时态、73 小节结构、127 评委误区；`R` 将来源偏好整体当硬门 | `writing-profile-weiwei`（显式 opt-in）+ 通用 citation/formula packet。 |
| `07-algorithm-reference.md` 136 行 | `S/recipe` 14 图网络、50 整数规划、66 评价决策、91 元启发式、109 多目标；`V` 非负边、MST≠最短路、TOPSIS≠生成方案、精确优先等误用边界；`R/recipe` 121 固定 Python API 未经当前版本核验 | `method-library/graph`、`integer`、`MCDM`、`metaheuristic`、`multiobjective`，只作为候选库，不获选模权。 |
| `08-literature-search.md` 128 行 | `V/S` 13 四轮检索和逐问触发顺序、38 来源职责、55 关键词、59 纳入、101 证据位阶、116 完成门；`S/M` 69 记录、107 产出；`R` 73–77 固定五文件 bundle | `evidence-search`、`source-reading-state`、`literature-orientation`；保存顺序与跳过反例，记录载体可按现有系统。 |
| `09-robustness-checker.md` 82 行 | `V` 14–23 V3/E4 边界、26 固定百分比不是现实依据、36 同口径比较、40–50 风险匹配、67–73 claim→failure→test；`S/M` 12 检查菜单、54 执行、77 反模式；`R/recipe` 固定脚本名/JSON 示例 | `verification-model-axis`、`robustness-design`，与 32/36 合并。 |

### 3.2 产物、交付、来源、理解、数据与旧控制（10–19）

| 文件 | 全部二级规则群及 disposition | 建议能力包 |
|---|---|---|
| `10-json-handoff.md` 96 行 | `V/S` 13 生产者—消费者/数据图与示意图来源、27 依赖、50 基线、61 审计、80 run identity、89 日志真实性；`S/M` 32 头部规范；`R` JSON 名称及 `project_state.json.invalidation_queue` 具体实现 | `artifact-lineage`、`run-manifest`、`nondata-visual-source`。V9 无 structured-output route，模型实现时不可达。 |
| `11-paper-finalizer.md` 258 行 | `S/M` 10 强度、15 结构示例、76 官方提交、145 内容自检、227 摘要版本、246 反模式；`R` 固定章节/年份/路径成为硬门 | `delivery-finalize`、`official-compliance-current`、`draft-vs-final`。 |
| `12-source-audit-and-provenance.md` 284 行 | `V/S` 18 规则位阶、49 审计字段、71 迁移规则、113 反馈只读沉淀、149 人工主导、247 披露颗粒度、262 污染、275 交付；`S` 时变政策链接；`R` 全项目复读控制与固定旧状态 | `skill-knowledge-migration`、`human-ai-control`、`ai-disclosure-current`、`feedback-to-rule`。V9 skill-maintenance route 未加载此模块，是重要失联。 |
| `13-excellent-paper-expression.md` 347 行 | `V` 51 六功能链、113–145 术语就地解释、173–185 双向追踪、200–260 建模/求解/结果/验证信息顺序、262–284 因果闭合；`S/M` 27 使用原则、67 各部分次序、286 句法、297 对照、312 定稿；`R/reference-only` 322 未核实样本线索作门 | `reader-explanation`、`claim-language`、`section-expression-recipes`；为 solution brief 与稿件分别设适用清单。 |
| `14-session-handoff.md` 137 行 | `S/M` 3 职责、10 目的、15 handoff 字段、31 R0/R1/R2、60 checkpoint、110 管道连续、123 评审可见、131 安全；`R` 独立状态 owner、每次暂停写固定文件、旧 `HANDOFF.md/project_state.json` 路径要求 | `recovery-handoff` packet；机器状态 owner 唯一，但保留“导航不等于事实”和评审可见性。 |
| `15-pipeline-methodology.md` 331 行 | `V/S` 61 逐问纵向闭环（含 78–127 独立性、144–179 可执行子阶段）、181 双完成与理解、194–239 文本化解释/术语预算、290 决定继承、311 时间取舍；`S/M` 19 来源、42 十类工作、241 轻记录、321 论文映射；`R` 十阶段作状态、固定文件 | `per-question-loop`、`human-understanding`、`terminology-budget`、`decision-inheritance`。这是 V10 丢失最严重的“顺序+人审”来源之一。 |
| `16-data-audit-methodology.md` 153 行 | `V/S` 12 进入条件、30 统计单位/伪重复、49 原始—清洁分类、67 全字段对账、82 异常候选与处理授权、95 证据能力、108 审计图、129 相似≠身份、141 独立复核；`R` 固定 planning 文件与表图数量 | `data-identity`、`statistical-unit`、`raw-clean-reconciliation`、`treatment-decision`、`audit-visuals`、`data-independent-check`。 |
| `17-reader-first-manuscript-audit.md` 219 行 | `V/S` 33 结构职责、61 背景、73 段落表、92 首次术语、109 白话复述、133 数据解释、168 失败传播、181 回归、205 人审证据；`M/R` 17 完整阅读证明、148 七级镜像状态；`R` 每次全文读取与第二状态机 | `reader-audit` + `human-promotion`; 保留“机器通过不能替代表达/人工”，退休七级 machine mirror。 |
| `18-execution-receipt.md` 85 行 | `R/M` 全部 R-01 至 R-05；保留开始/结束不同、跳过需证据、validator 不等于事实的语义，退休独立 schema/owner | 合并到唯一 `execution-transaction` 契约。 |
| `19-project-lifecycle.md` 64 行 | `R/M` L-01 至 L-07 作为第二线性生命周期；`S` 逐问状态、文献触发、人工理解、候选晋升、传播的独立语义 | 分别并入 `typed-state`、`literature-trigger`、`human-understanding`、`impact-propagation`。 |

### 3.3 稿件验收、最低交叉检查、不确定性与科研图（20–37）

| 文件 | 全部二级规则群及 disposition | 建议能力包 |
|---|---|---|
| `20-execution-gates.md` 104 行 | `R/M` G-01…G-08 作为第二入口/七级状态 owner；`S` 结构先于句改、失败传播、人工门语义 | 合并进 `reader-audit` 与唯一 artifact state。 |
| `21-global-manuscript-acceptance.md` 180 行 | `S/M` M-01、02、04、05、06、07、08、09、10、11、12 全部保留为验收视角；`R` 无条件全文连续阅读作普通局部门 | `manuscript-global-acceptance`；保留 stable checklist，不再复制建设过程。 |
| `22-front-matter-acceptance.md` 76 行 | `S/M` F-01 题目、F-02 摘要、F-03 盲读、F-04 关键词 | `front-matter` packet。 |
| `23-background-analysis-acceptance.md` 59 行 | `S/M` B-01 背景、B-02 重述、B-03 分析 | `problem-framing-manuscript` packet。 |
| `24-assumptions-data-acceptance.md` 43 行 | `S/M` A-01 假设、A-02 符号、A-03 预处理 | `assumptions-notation-data-writeup` packet。 |
| `25-model-results-acceptance.md` 181 行 | `V/S/M` S-01 每问链、S-02 建模、S-06 选模解释、S-07 求解、S-08 结果、S-09 验证、S-10 直接回答、S-11 离散/连续、S-12 论文/复现边界；其中 148–164 双轴例外 `V` | `model-to-paper` + `verification-visible`。V9 验证 route 未加载本模块，需双向 route。 |
| `26-conclusion-references-acceptance.md` 38 行 | `S/M` C-01 评价、C-02 改进、C-03 结论、C-04 引用 | `conclusion-and-references`。 |
| `27-visual-layout-acceptance.md` 188 行 | `S/M` V-01 模板/标题逻辑、V-02 字体门（含 V-03…06）、V-07 图表、V-10 源边界、V-11 分页、V-12 编译；`V` 20–33 环境字体边界、119–125 三层检查；`R/recipe` 固定 Windows 字体 preamble | `latex-font`、`visual-selection`、`render-page-audit`; 与 02/04/34/37 合并。 |
| `28-evidence-acceptance.md` 52 行 | `S/M` E-01 双向链、E-02 数据代码、E-03 来源、E-04 一修全修 | `claim-evidence-lineage`。 |
| `29-governance-acceptance.md` 32 行 | `R/M` 独立治理 owner；`S` H-01 人工、H-02 草稿/正式、H-03 状态/交接、H-04 影响、H-05 回归 | 并入 governance/maintenance 唯一 owner。 |
| `30-data-minimum.md` 34 行 | `M` Data identity、Transformation、Evidence capacity、Outputs 全部保留为 data packet 的 concise acceptance view | `data` packet 的 `acceptance.md`。 |
| `31-modeling-minimum.md` 43 行 | `M` Assessment、Specification、Solving 全部保留为 modeling packet 的 concise acceptance view | `modeling` packet 的 `acceptance.md`。 |
| `32-verification-minimum.md` 66 行 | `V` 5–18 双轴条件、48–59 风险匹配/逐问可见；`S/M` V1/V2、V3/V4 菜单与 claim strength | `verification` packet 的规范核心与 acceptance view。 |
| `33-manuscript-minimum.md` 60 行 | `S/M` Whole-paper chain、Reader-first、Sections、Consistency 全部 | `manuscript` packet 的 acceptance view。 |
| `34-visuals-minimum.md` 33 行 | `S/M` Visual evidence、Technical quality、LaTeX/PDF 全部 | `visual` packet 的 acceptance view。 |
| `35-provenance-delivery-minimum.md` 41 行 | `S/M` Evidence chain、Authority、Propagation、Draft/formal 全部 | `evidence-delivery` packet 的 acceptance view。 |
| `36-uncertainty-error-analysis.md` 180 行 | `V` U-02 来源分类、U-03A E3/E4 边界、U-06 五种合法状态、U-07 反模式；`S/M` U-01 适用、U-03 分责、U-04 规格、U-05 执行、U-07 写作、U-07A 每问闭环、U-08 来源；`R` 把固定外部标准/版本当运行权威 | `uncertainty-source`、`propagation`、`robustness`、`claim-gate`; 与 09/32 合并。 |
| `37-scientific-figure-design.md` 169 行 | `V` 22–42 真实性映射、101–110 样板顺序、116–123 自动/人工边界、137–169 像素/复原/非覆盖；`S/M` 7 职责卡、44 图类、72 视觉系统、88 工具/复现、125 登记；`R/recipe` 工具偏好仅作默认，不作硬禁 | `visual-schematic-engineering`、`visual-data-statistical`、`visual-human-review`。这是 V10 “示意图能力”缺失的主要来源。 |

### 3.4 V8 ledger 的覆盖判断

- 38/38 文件、270/270 二级规则群已在上表有 disposition；子标题、列表、代码例和反模式随所属行段继承处置。
- 没有建议把任何领域文件整份删除。整份可退休为运行 owner 的只有 `18/19/20/29`，且其独立语义均迁入唯一控制/验收 packet。
- `30–35` 不应继续作为六个独立“大路由模块”，但也不应丢失；最佳位置是各 domain packet 的 `acceptance.md`，作为建设说明之外的异构验收视角。
- 最需要逐字保护的不是所有段落，而是条件例外、固定顺序、失败修复和人工边界：solution brief 九项；E2/E3/E4 条件；图件真实性映射与样板门；数据全字段对账；逐问纵向闭环；术语首用/白话复述；不确定性合法状态。

## 4. V6–V8 references、脚本与控制文本 disposition

### 4.1 逐文件 references ledger

以下表覆盖 V6 的 6 份 reference 文本以及 V7/V8 新增的 10 份 reference 文本（合计 16 份）；V7、V8 同名且内容一致者合并列示。JSON 的 disposition 指其规范语义和将来运行地位，不建议删除历史快照。

| reference | 关键独立规则/字段 | disposition 与建议 packet |
|---|---|---|
| V6–V8 `references/migration-ledger.md` | 历史来源、迁移去向、完整性说明 | `preserve_semantics_rewrite/archive`：留作 provenance，不装入普通任务上下文；迁移结论须由可执行 source-clause coverage 重算。 |
| V6–V8 `references/qualified-skill-standard.md:3-35` | 13 条合格 skill 标准：单控制器、领域完整、可恢复、可验证、人机边界等 | 除逐字 hash 门外均 `preserve_semantics_rewrite/merge` 到 `maintenance/acceptance`；`:29-31` 的整文件 hash/旧文本不变要求 `retire`，改为语义、例外、顺序和 reachability 检验。 |
| V6–V8 `references/start_receipt.schema.json`、`end_receipt.schema.json` | 开始/结束收据字段和状态匹配 | 独立双 schema `retire/merge`；“开始事实不同于结束事实、跳过需证据、结束须绑定同一事务” `preserve_verbatim` 到唯一 transaction packet。V9/V10 已正确收敛。 |
| V6–V8 `references/v1-integration-map.json` | V1 来源→当前 owner | `preserve_semantics_rewrite/archive`；作为 lineage seed，不作为“当前能力仍可达”的证明。 |
| V6–V8 `references/version-delta-map.json` | 相邻版本变更声明 | `preserve_semantics_rewrite/archive`；下一版必须增加 `source_clause_id → packet_id → route_case → eval_id`。 |
| V7/V8 `references/v7-architecture-decision.md:17-25,35-56` | 渐进披露是减载而非减能力；禁止一句话替代方法、顺序、例外、失败和例子；五层结构 | `preserve_verbatim`，是下一版架构公理；V10 违背的正是“原子 gloss 不能替代完整能力”。 |
| 同上 `:60-102,104-121` | 原子账本、route registry、行为回归；先映射后改写；禁止 simplification | `preserve_verbatim/merge` 到 maintenance packet；source baseline 必须从 51 条 V9 gloss 回升到 V8 独立规则。 |
| V7/V8 `references/responsibility-decisions.md` | D01–D23 逐项冲突/修复裁决 | `preserve_semantics_rewrite/archive`，但 D14 solution brief (`:119-126`)、D19 测试 ID (`:151-155`)、D20 不冻结全文 hash (`:157-161`)、D23 S6 双轴 (`:198-210`) `preserve_verbatim` 并进入相应 packet。 |
| V7/V8 `references/v7-full-capability-review.md:3-14,46-49` | 1,859 candidates；1,300 capabilities、559 context；1,269 exact、31 rewrite；无 merge/delete 授权 | `preserve_verbatim/archive`。它证明 V7 的 review 结论，不证明 V10 的 206 原子具备同等细节。 |
| V7/V8 `references/capability-ledger.schema.json`、`v6-capability-ledger.json` | clause 级来源、分类、owner、rewrite treatment | schema 思路 `preserve_semantics_rewrite`；大账本 `archive`，普通 route `retire`。下一版复用 clause 粒度但新增 sequence/exception/example/human-gate/reachability 字段。 |
| V7/V8 `references/routing-registry.json` | stage/task→必读规则，含 S6 solution brief route (`:87-107`) | `preserve_semantics_rewrite` 为 capability packet registry；退休“整文件必读”，保留 solution brief 等 route 意图并增加 trigger/predicate。 |
| V7/V8 `references/scaffold-artifact-contract.json` | 默认脚手架、owner/consumer/activation | 固定空文件 bundle `retire`；consumer、activation、禁止 speculative artifact `preserve_verbatim/merge` 到 artifact-admission。 |
| V7/V8 `references/manuscript-audit-states.json` | 七级稿件审计镜像状态 | 独立状态机 `retire`；机器/独立 AI/人工三类证据不可互换的区分 `preserve_semantics_rewrite` 到 manuscript promotion gate。 |
| V7/V8 `references/capability-test-registry.json` | rule/capability→测试绑定 | `preserve_semantics_rewrite/merge`；将“文件存在/字符串命中”升级为 packet 装配、近负例、例外、人审提示可达性测试。 |
| V7/V8 `references/responsibility-overlap-report.json` | owner 重叠扫描 | `archive`；冲突图思想 `preserve_semantics_rewrite` 到 maintenance，结果本身不作当前事实。 |

### 4.2 脚本链路的保留与退休边界

- V6/V7/V8 `scripts/validate_figure_assets.py:30-115` 是少数真正执行图件机械质量检查的实现：源/SVG/PDF/PNG 存在性、SVG `viewBox`/矢量与栅格、渐变、PNG 尺寸、PDF 签名/页数、Type 3 字体。脚本与检查项应 `preserve_semantics_rewrite` 到 visual mechanical QA；依赖不可用时输出 `unverified`，不得把未运行写成通过。
- V8 `rules/37-scientific-figure-design.md:116-123` 正确规定机械检查不替代拓扑、受力、数据真实性和审美的人审；这一边界 `preserve_verbatim`。V9 模块仍声称脚本可用（`references/modules/visuals-layout.md:851`），但包内已无此脚本；V10 也没有等价 validator。这是运行依赖悬空，不是可接受的“压缩”。
- V7/V8 capability ledger、routing、single-controller、S6 验证脚本的结构思想 `preserve_semantics_rewrite`；历史脚本不应直接成为下一版 runtime gate。下一版只需一个离线 `lint_packets`、一个 route assembler、一个行为回归 runner。
- bootstrap、checkpoint、receipt、manuscript mirror 等旧脚本的第二 owner 身份 `retire`；仍有价值的输入校验、事务一致性和恢复证据逻辑并入 V10 的单状态 owner。

## 5. V9：完整文本仍在，但模块级路由使若干能力失联

### 5.1 新增且应保留的控制设计

V9 的控制层不是失败，反而是后续应继承的骨架：

- `SKILL.md:13-25` 把授权、证据、冻结选择、状态与领域步骤分开且禁止静默合并冲突；`preserve_verbatim` 到 `governance-core`。
- `SKILL.md:27-39` 的五模式及只读默认值，特别是“继续看看/审计/建议”不等于写授权；`preserve_verbatim`。
- `SKILL.md:41-68` 的 route tuple、唯一写 route、不可递归与“导入领域细节仍有效”；前半 `preserve_semantics_rewrite`，后一句须用可达性测试兑现。
- `SKILL.md:58-60,85-93` 与 `references/recovery-governance.md:7-29` 的 R0/R1/R2 比例恢复、fidelity 优先；`preserve_verbatim/merge` 到 `recovery` packet。
- `SKILL.md:95-105` 的决定分类和惰性工件、`:107-111` 不为每轮制造收据文件、`:139-143` 局部完成≠全局完成；均 `preserve_verbatim`。
- `references/manuscript-local.md:1-17` 的局部稿件边界与依赖闭包；`preserve_verbatim` 到 `manuscript-local-edit`。
- `references/maintenance-contract.md:7-39` 的 L0–L4、positive/near-negative/conflict、fresh reload、canonical owner；`preserve_verbatim/merge` 到 maintenance packet。
- `references/context-budget.json:4-10` 的“Capability fidelity precedes compression”原则 `preserve_verbatim`；固定 1/3/4 modules 和 100/3000/5000 行仅 `preserve_semantics_rewrite` 为动态预算。
- `references/route-contract.json:1-18` 的 `transitive=false`、catchall 不算 reachability；`preserve_verbatim`。这是发现下面失联的正确判据。

### 5.2 V9 逐文件 disposition

| 文件/组 | disposition | 审计结论与下一版位置 |
|---|---|---|
| `SKILL.md` | 控制语义 `preserve_verbatim`；固定模块列表 `retire/merge` | 保留单 owner、模式、状态、比例恢复、局部完成；改由 packet assembler 返回 clause-level closure。 |
| `references/modules/{data,modeling,verification,manuscript-content,manuscript-acceptance,visuals-layout,evidence-delivery,project-platform,orchestration-detail,writing-profile}.md` | 领域正文 `preserve_verbatim/source-corpus`；十个运行 monolith `retire` | `scripts/build_modules.py:12-98,133-180` 把 34 个 V8 文件原样拼成 10 模块（7,038→7,284 行），字节基本没丢；但粒度过粗、映射错误和 route 不全。应拆为完整 packets，而不是再摘要。 |
| `references/capability-registry.json` | `retire` 为语义基线；`preserve_semantics_rewrite` 为检索索引 | 51 条低分辨率 capability 只能当目录。例：`DATA-AUDIT` (`:29`)、`VER-S6-DUAL` (`:43`)、`VIS-DESIGN/LAYOUT` (`:54-55`) 无法承载 V8 的顺序、例外和例子。 |
| `references/route-contract.json` | `preserve_semantics_rewrite` | 23 routes 是好骨架，但应路由到 packet 条款而非十个模块；补 solution brief、structured output、skill knowledge migration、paper audit、schematic。 |
| `references/state-contract.json`、`receipt.schema.json` | `preserve_semantics_rewrite/merge` | 保留 typed state、证据与事务一致性；避免让运行状态替代领域事实。 |
| `references/artifact-contract.json` | `preserve_verbatim` 核心，schema 细节 `merge` | 惰性工件/consumer/activation 优秀，补 `solution_brief` 的条件注册。 |
| `references/recovery-governance.md`、`manuscript-local.md`、`maintenance-contract.md` | `preserve_verbatim/merge` | 分别成为 recovery、local edit、maintenance packets。 |
| `references/context-budget.json` | 原则 `preserve_verbatim`，数字 `preserve_semantics_rewrite` | 预算作用于选装的 examples/recipes，不得截断 normative core、exceptions、sequence、human gates。 |
| `references/migration/{conflict-decisions,module-source-manifest,native-capabilities,release-manifest,rule-disposition,v1-v9-capability-ledger,v9-release-report}.json` | `archive`；有价值决议 `preserve_verbatim` | C-001/C-002/C-009/C-015/C-016（`conflict-decisions.json:6-21`）保留；release 的“0 unmapped”只表示 registry 映射，不表示 route 可达或方法等价。 |
| `evals/*.json` | `preserve_semantics_rewrite/archive` | 将路径/计数/字符串型用例升级为 request→assembled clauses→例外→行为的 fresh-context tests。 |
| `scripts/{resolve_route,state_manager,assess_recovery,analyze_rule_change,freeze_release,validate_*}.py` | `preserve_semantics_rewrite` | 复用确定性解析、状态和发布思想；不保留 module 粒度。 |
| `scripts/build_modules.py`、`build_migration_ledger.py` | `retire` runtime，`archive` lineage | 下一版由 clause→packet compiler 取代。 |
| `scripts/init_project.py` | `preserve_semantics_rewrite` | 保留惰性初始化，只创建唯一状态且不得预造无消费者工件。 |

V9 发布报告确实给出一组扎实的结构检查：`references/migration/v9-release-report.json:11-37` 记录 1,859 条 V1–V6、9 条 V7 native、5 条 V8 native、51 条 V9 operational、合计 1,924、`unmapped=0`；34 个细则文件/7,038 行被带入；23 routes、42 evals、24 deterministic tests；初始化从 15 文件降到 1 文件；结果 PASS。disposition：计数事实 `preserve_verbatim/archive`，但“完整迁移”的解释必须 `preserve_semantics_rewrite` 为“文本收录完整，操作可达性未证明”。

### 5.3 五个可复现的 route-level 失联/错装

1. **solution brief 完整文本在模块中、操作上却不可达。** V8 的九项逐问讲解顺序与人工验收在 `rules/01-contest-project-pattern.md:48-73`，V8 route 在 `references/routing-registry.json:87-107`；V9 文本仍在 `references/modules/project-platform.md:63-86`，但 `capability-registry.json` 无 solution capability，S6 routes 只在 `route-contract.json:76-93` 加 verification，project-platform 只由初始化/规划 `:26-33` 加载。V10 更无匹配项，且 `artifact-contract.json:18-27` 默认只有 state。结论：不是内容不存在，而是 **不可被正确任务装配**。
2. **稿件审计错装到 verification。** `scripts/build_modules.py:43-50` 将 688 行 `rules/05-audit-protocol.md` 放进 verification；稿件审计 route `route-contract.json:106-108` 却加载 manuscript-content/acceptance/visuals/evidence，不加载 verification。因此修稿时无法得到其逐步审计和影响传播规则。
3. **结构化结果生产不可达。** V8 `rules/10-json-handoff.md:13-25,61-87` 的 producer→consumer、数据图/示意图来源、run identity 被放在 evidence-delivery；V9 model implement route `route-contract.json:71-73` 只加载 modeling，且无 structured-output route/capability。
4. **skill 反馈迁移不可达。** V8 `rules/12-source-audit-and-provenance.md:49-149,247-275` 的反馈→规则、人工控制、披露、污染边界被放在 evidence-delivery；V9 skill audit/change routes `route-contract.json:126-133` 只加载 maintenance contract。
5. **图件 validator 悬空。** V9 `references/modules/visuals-layout.md:851` 仍要求 `scripts/validate_figure_assets.py`，但 V9 package 无该脚本；V10 也无 `viewBox`、PNG dimension、Type 3/font、PDF signature/pages 的等价检查。机械 QA 从“可运行能力”退化成了一句遗留引用。

这五项说明 `unmapped=0`、模块有文本、route 有模块三者不能推出能力可执行。下一版必须测 `raw request → selected packet → required clause IDs → tool/ref availability → human gate` 全链路。

## 6. V10：原子控制精细，领域语义却以 V9 gloss 为基线

### 6.1 真正优秀的新增设计

- `SKILL.md:13-23` 明确唯一 owner，且只有 atom `effect` 是规范文本，gloss/failure/outcomes 非规范；诚实地区分“route 已选”与“领域事实已证明”。`preserve_verbatim`。
- `SKILL.md:31-55` 的 raw request→route→applicability→完整 envelope，以及 resolver `scripts/resolve_route.py:448-462` 返回 effect、failure、enforcement、scope、trigger、evidence、outcomes、exceptions、conflicts、dependencies、owner；数据结构 `preserve_verbatim`。
- `SKILL.md:57-69,71-116,135-150` 的比例恢复、事务/工件和 evidence-bounded completion；`preserve_verbatim/merge`，但领域 N/A 必须进入判定器。
- `references/ownership-contract.json:1-108` 的唯一 owner、原子拆分、non-normative supporting refs；尤其 `:87-103` 的原子性边界 `preserve_verbatim`。
- `references/artifact-contract.json:7-30` 的 proposal 字段、默认只建 state、绝不默认造 README/规划/讲解稿等；`preserve_verbatim`，再加按 consumer 激活 solution brief。
- 发布前测试面广：`evals/release/frozen-manifest.json` 记录 quick 10、contract 4、behavior 97、atomic 206+aux 206、scenario 46、maintenance 12、change 5、transaction 2、migration 6 均 exit 0。`preserve_semantics_rewrite` 为下一版基础；manifest `:404-408` 自己也正确承认 lineage 只到 clause review、schema/syntax 不能证明任意领域真值。

### 6.2 为什么“206 原子全覆盖”仍不等于 V8 能力无损

V10 的迁移基线是 V9 的 51 条 capability gloss，而不是 V8 的 270 个二级规则群/7,038 行领域正文：

- `references/migration/legacy-coverage.json:5` 明示不主张 V10 line-by-line semantic equivalence；`:17643-17650` 是 1,859 legacy spans（1,300 confirmed、559 context）加 14 条 V7/V8 native。
- `references/migration/clause-preservation.json:8895-8899` 报告 51 个 V9 capabilities、302 source clauses、206 active atoms、203 source-bound、3 defect；所谓 source clause 仍是 V9 低分辨率 capability 文本。
- `references/migration/capability-crosswalk.json:4,41` 明示只是 structural assignment，`semantic_equivalence_claimed=false`。
- 七份 method notes 合计仅 216 行/6,547 字符；V8 被 V9 收录的 active detail 是 7,038 行/212,020 字符，前者约为后者 3.1%。更关键的不是长度，而是 notes 被 `ownership-contract.json:105-108` 定义为 non-normative，不能补足 atom effect 的条件与顺序。

原子本身也表现出过度普适化：206 条中 205 `MUST`、1 `SHOULD`；190 条没有 predicates，169 条没有 exceptions，157 条二者都没有；虽每条都有 `outcomes.not_applicable`，但该字段不是规范文本，也未被运行判定使用。99 条 dependency edges、34 runtime guards 和 172 agent obligations 证明控制链很细，却没有弥补适用性事实。

### 6.3 九个 rules JSON、206 个原子的完整 disposition ledger

下表逐文件列出所有 atom ID。除明确标 `V`/`R` 的例外外，同组默认 disposition 即覆盖每个列出的独立 atom；因此覆盖为 206/206。

| 文件（数量） | atom IDs | disposition、原因与 packet |
|---|---|---|
| `rules/governance.json` (35) | `GOV.MODE.{DERIVE,STABLE}`; `GOV.AUTH.{WRITE_SCOPE,CLAIM_SCOPE,FROZEN_CHOICE,DIMENSION_SEPARATION}`; `GOV.ROUTE.{RAW_REQUEST,STATE_BIND,UNIQUE_WRITE,DECOMPOSE,TUPLE,PROOF_SOURCE}`; `GOV.OWNER.UNIQUE`; `GOV.RECEIPT.{START_MATCH,END_MATCH}`; `GOV.DECISION.CLASSIFY`; `STATE.TYPE.MATCH`; `STATE.EVIDENCE.TYPED`; `STATE.TRANSITION.GATED`; `STATE.ROUTE.RECORD`; `REC.R0.{CONTINUE,READ_SCOPE,NO_MANIFEST}`; `REC.R1.{TRANSITIVE,REVIEW_CLOSURE,READ_SCOPE}`; `REC.R2.{FULL,EVIDENCE_REBUILD,NO_NARRATIVE_ONLY}`; `ART.ADMIT.{CONSUMER,PROPOSAL_FIELDS,NO_SPECULATION,MINIMAL}`; `ART.PROMOTE.VALIDATE`; `ART.REGISTER.IDENTITY` | 全组控制语义 `V/M` 到 `governance-core`、`recovery`、`artifact-admission` 三包；receipt/proposal 的固定 envelope `S` 为仅 stateful/high-risk 事务。无语义退休项。 |
| `rules/project.json` (14) | `PRJ.SCOPE.{BOUNDARY,AMBIGUITY,SUCCESS,INVENTORY,CONTROLLED_CHANGE,NO_UNSUPPORTED_TASK}`; `PRJ.STRUCTURE.{INSPECT,LAZY,TOOLCHAIN}`; `PRJ.PLAN.{COMPONENTS,DEPENDENCIES,TRACE,OWNER_BOUNDARY,NEXT_ACTION}` | 全组 `S/M` 到 `project-orientation`、`plan`；`STRUCTURE.LAZY`、scope 边界和 no-unsupported-task 可 `V`。`TOOLCHAIN` 是全库唯一 SHOULD，保留其比例性；补 V8 的逐问闭环/solution brief route，而非扩写成固定十阶段。 |
| `rules/data.json` (18) | `DATA.IDENTITY.{SOURCE,RAW_IMMUTABLE,CONTEXT,BEFORE_USE}`; `DATA.AUDIT.{SCHEMA,MISSING,ANOMALY,DUPLICATE,LEAKAGE,COMPLETENESS,SEMANTIC_CONSISTENCY,BEFORE_TREATMENT}`; `DATA.TREAT.{DECIDE,COPY,LINEAGE}`; `DATA.FREEZE.{IDENTITY,VALIDATE,INVALIDATE}` | 全组 `S/M` 到 `data-audit-core`；RAW immutable、before treatment、copy、lineage、freeze invalidate 可 `V`。须恢复 V8 `rules/16:30-153` 的统计单位、全字段 reconciliation、candidate≠authority、证据能力、审计图与独立人审；否则只有检查名，没有 how-to。 |
| `rules/modeling.json` (27) | `MOD.RESTATE.{KNOWN,UNKNOWN,OBJECTIVE,OBJECTS,OUTPUTS,REDESIGN,BEFORE_ALGORITHM}`; `MOD.COMPARE.{BASELINE,SAME_EVIDENCE,ASSUMPTIONS,RATIONALE}`; `MOD.SPEC.{VARIABLES,EQUATIONS,PARAMETERS,ALGORITHM,ASSUMPTIONS,INTERFACE,FREEZE,READINESS}`; `MOD.IMPLEMENT.{SPEC_BIND,REPRODUCE,DETERMINISM,OUTPUT_REGISTER}`; `MOD.RESULTS.{IDENTITY,INTERPRET,FAILURES,TRACE}` | 全组 `S/M` 到 `model-restatement`、`candidate-comparison`、`specification`、`implementation/results`；`SAME_EVIDENCE` 改写为“同一口径或显式声明不可比差异”，不能强迫异构候选共享不适用证据。恢复 V8 method library 的误用边界与 per-question sequencing。 |
| `rules/verification.json` (33) | `VER.E1.{INTERFACE,UNITS,BOUNDARY,REPRODUCE,CODE_PATHS,ERROR_PATHS,EXIT_ZERO}`; `VER.E2.{RECOMPUTE,TOLERANCE,STABILITY,CONVERGENCE,NO_FORMAT_MASK}`; `VER.E3.{CONSTRAINT,INVARIANT,LIMIT,COUNTEREXAMPLE,SENSITIVITY}`; `VER.E4.{ASSUMPTIONS,SCALE,PARAMETERS,MECHANISM,REALITY_FIT,USE_CLAIM_GATE}`; `VER.S6.DUAL_AXIS`; `VER.UNCERTAINTY.{SOURCES,PROPAGATE,BOUND,CLAIM_GATE}`; `VER.ROBUST.{METRIC,BASELINE,NO_VISUAL_PROXY,PERTURB,FAILURE_REGION}` | 全组 `S/M`，且 E2/E3/E4/S6 必须重写。E1 菜单按实现风险选装；E2 仅数值风险触发；E3 是“至少一个风险匹配试验”，不是五项全做；E4 仅有现实 comparator 时触发；S6 允许有证据的 N/A。`NO_FORMAT_MASK`、claim gate、no visual proxy 可 `V`。包：`verification-core` + `numeric-risk` + `structural-risk-choice` + `external-validity` + `uncertainty/robustness`。 |
| `rules/manuscript.json` (29) | `MAN.STRUCTURE.{REQUIREMENTS,TRACE,RESPONSIBILITY,DEPENDENCY,NO_WORKLOG}`; `MAN.CONTENT.{CLAIM_EVIDENCE,NOTATION,METHOD,RESULT,LIMITATION,EXPLANATION_TRACE,NO_DUMP}`; `MAN.READER.{SCOPE,FRONT,FLOW,STANDALONE,NO_META}`; `MAN.ACCEPT.{NO_PLACEHOLDER,CROSSREF,RENDER,SECTION,GLOBAL}`; `MAN.LOCAL.{SCOPE,DEPENDENCIES,REOPEN_A3,NO_FULL_AUDIT}`; `MAN.PROFILE.{OPT_IN,TRUTH,FORMAT}` | 全组 `S/M` 到 structure/content/reader/acceptance/local/profile packets；local boundary、profile opt-in/truth、no-worklog 可 `V`。须恢复 V8 中摘要—问题分析—假设—推导—结果的具体顺序、首次术语、白话复述、数字身份、七类人审证据；acceptance 原子不能替代建设方法。 |
| `rules/visuals.json` (14) | `VIS.DESIGN.{QUESTION,TYPE,UNCERTAINTY}`; `VIS.LAYOUT.{LABELS,LEGIBILITY,COLOR,CAPTION,FONTS,PAGINATION,PLACEMENT}`; `VIS.IDENTITY.{DATA,RENDER,SYNC,NO_MANUAL_VALUES}` | QUESTION/TYPE/LABELS/LEGIBILITY/COLOR/CAPTION/RENDER/SYNC/FONTS/PAGINATION/PLACEMENT `V/S/M` 到 visual-common；UNCERTAINTY、DATA、NO_MANUAL_VALUES `S` 为有 predicate/exception 的数据图规则。新增 `visual-schematic-engineering` packet，恢复 V8 `rules/37:22-42,101-123,137-169`；非数据示意图不得被数据 identity/uncertainty 硬门误杀。 |
| `rules/evidence_delivery.json` (21) | `EVD.SEARCH.{CLAIM_FIRST,PRIMARY,FULLTEXT_SCOPE,COUNTEREVIDENCE}`; `EVD.POLICY.CURRENT`; `EVD.PROV.{CLAIM_MAP,METADATA,NO_FORCED_FILES}`; `EVD.EXTERNAL.{AUTHORITATIVE,NO_SNIPPET_AI}`; `DEL.FINAL.{COVERAGE,REPRODUCE,RENDER,BOUNDARY,NO_TEMP}`; `DEL.PROV.{LICENSE,WHITELIST,SECRETS,CITATIONS,LINEAGE}`; `DEL.HANDOFF.STATE` | 全组 `S/M` 到 evidence-search/provenance/delivery；CURRENT、NO_SNIPPET_AI、NO_FORCED_FILES、SECRETS、LINEAGE 可 `V`。恢复 V8 四轮检索顺序、反馈→规则、人工 AI 治理与披露 packet；policy URL 必须运行时核验。 |
| `rules/maintenance.json` (15) | `MNT.CLASSIFY.{OLD,NEW,TRIGGER,RISK}`; `MNT.IMPACT.{TRANSITIVE,ROUTE_REACH,CONFLICT_GRAPH}`; `MNT.OWNER.CANONICAL`; `MNT.EVAL.{POSITIVE,NEAR_NEGATIVE,CONFLICT}`; `MNT.RELOAD.{ISOLATED,INDEPENDENT_AGENT}`; `MNT.ROLLBACK.{PRESERVE,COMPATIBILITY}` | 全组 `V/M` 到 release-only `maintenance` packet；不应成为普通任务重型 gate。补 source-clause fidelity、packet reachability、exception/sequence/example/human-gate preservation eval。 |

### 6.4 V10 references、method notes、evals 与脚本 disposition

| 文件/组 | disposition | 结论 |
|---|---|---|
| `references/ownership-contract.json`、`rule-atom.schema.json`、`effect-target-registry.json` | `preserve_verbatim` 核心，`preserve_semantics_rewrite` schema | unique owner、target vocabulary、完整 envelope 可直接成为下一版原子层。新增 packet/section/source-clause/sequence-group 字段。 |
| `references/route-contract.json` | `preserve_semantics_rewrite` | 30 routes 和 route event model (`:15-45`) 保留；路由目标从 atom+短 note 改为 packet closure。补缺失 routes，optional context 不能由中英文关键词脆弱命中决定唯一可达性。 |
| `references/state-machine.json`、`state.schema.json`、`receipt.schema.json` | `preserve_semantics_rewrite/merge` | 保留 typed evidence、事务；删除 E2/E4 无条件要求，加入 `not_applicable_with_reason` 可满足有条件门。 |
| `references/artifact-contract.json` | `preserve_verbatim` 核心 | 保留惰性工件；为讲解稿、图件 registry 等提供有 consumer 时的 proposal 模板。 |
| `references/{data,modeling,verification,manuscript,project,evidence,visual}-method-notes.md` | `merge` 为 packet `quick.md`，不可作完整方法 owner | notes 可作快速提醒。visual note `:1-20` 只有选图、不确定性、四层审计和“概念示意图标非数据”，丢失工程真实性、受力、工具选择、样板门、自动/人审边界、像素复核与非覆盖修复。 |
| `references/migration/{v9-capability-baseline,capability-crosswalk,clause-preservation,legacy-coverage}.json` | `archive`；compiler 思路 `preserve_semantics_rewrite` | 不再拿 51 gloss 当语义基线；以 V8 270 H2 + 必要子条款/例外为 source clauses，记录明确 disposition。 |
| `references/change-envelope.schema.json`、`release-manifest.schema.json` | `preserve_semantics_rewrite` | 加 `semantic_diff`, `lost_exception`, `route_reachability`, `tool_availability`, `human_gate`。 |
| `evals/atomic-rule-cases.json` | `retire` 自动生成同义自证；框架 `preserve_semantics_rewrite` | 172 条是 `selection_and_semantic_delivery_only`、34 条 runtime guard，主要证明自有 JSON 可被自身 resolver 选中；应换成人工标注 raw requests 与跨版本 oracle。 |
| `evals/behavior-cases.json`、`contract-cases.json`、`change-cases.json`、`evals/release/*` | `preserve_semantics_rewrite` | 保留 fresh release 和冻结机制；加入 near-negative applicability 与 V8 golden clauses。 |
| `scripts/lib_v10.py`、`resolve_route.py` | `preserve_semantics_rewrite` | 保留确定性 full-envelope 装配；修复 applicability 使用 predicate/exception/N/A，支持 packet closure 和预算层。 |
| `scripts/state_manager.py`、`artifact_guard.py`、`assess_recovery.py` | `preserve_semantics_rewrite` | typed state、artifact guard、比例恢复有价值；state manager 不得把条件轴固定成 pass 配额。 |
| `scripts/analyze_rule_change.py`、`apply_rule_change.py`、`run_*evals.py`、`freeze_release.py`、`validate_*`、`quick_validate.py` | `preserve_semantics_rewrite/merge` | 留作离线维护链，而非每任务 runtime gate；semantic review 与 independent human sign-off 必须外生，不能由生成器自证。 |

## 7. V8→V9→V10 的语义损失矩阵

| 能力 | V8 完整来源 | V9 状态 | V10 状态 | disposition/修复 |
|---|---|---|---|---|
| 逐问 solution brief 九项顺序、非论文、人工复述验收 | `rules/01:48-73`; route `routing-registry:87-107` | 字节在 project module，但 S6 route 不加载 | 无 atom、route、artifact 类型 | `preserve_verbatim`，建 `solution-brief` packet 和有 consumer 的 lazy artifact proposal。 |
| 每问纵向闭环、独立性、文本化理解、决定继承 | `rules/15:61-239,290-319` | 在 orchestration-detail，大模块只部分 routes | 只剩 planning/restatement/manuscript gloss | `preserve_semantics_rewrite`，sequence group 作为 packet normative section；不能散成无序 MUST。 |
| 数据统计单位、全字段对账、处理授权、证据能力、独立人审 | `rules/16:30-153` | 原文在 data module，可达 | 18 原子只列检查名；例子与审计顺序不规范 | core 条件和顺序 `preserve_verbatim`，how-to/examples `S`；`data-audit` packet。 |
| 稿件逐步审计、脚本输出审计、失败传播 | `rules/05:33-688` | 错装 verification，manuscript audit route 不可达 | manuscript atoms 只给结果门 | `S/M` 到 `manuscript-audit` packet，route 同时加载 impact closure。 |
| 首次术语/白话复述/双向追踪/模型→求解→结果→验证顺序 | `rules/13:51-65,113-145,173-284`; `17:92-205` | 文本可达性依 route 而异 | 零散解释/trace atoms，无例子与人审证据 | 关键顺序/人审 `V`，表达 recipe `S`；reader-explanation packet。 |
| 图件真实性：题意对象→几何/拓扑→变量→力/信息流→图；公式不得发明几何 | `rules/37:22-42` | 原文在 visuals module | 14 atoms 与 20 行 note 无此链 | `preserve_verbatim`，`schematic.truth-map` normative core。 |
| 图件先选难样板→技术审→用户审→再批量；自动与人工检查分界 | `rules/37:101-123` | 原文仍在 module | 完全消失 | `preserve_verbatim`，做 `schematic.sample-gate` 与 human review receipt；不可自动 self-pass。 |
| 原 PDF 复原、symbol contract、分视图、最终像素检查、修复不得覆盖原件 | `rules/37:137-169` | 原文仍在 module，validator 悬空 | 完全消失 | `V/S`，分入 recovery/tool/human-review sections；恢复可执行 validator 或诚实降级。 |
| 数据图与非数据示意图来源区分 | `rules/10:13-25`; `37:22-42` | evidence module/visual module 分离，model route 不全 | `VIS.IDENTITY.DATA` 与 NO_MANUAL_VALUES 易对非数据图过触发 | `preserve_verbatim`；加 `visual_kind ∈ {data, computed, engineering_schematic, conceptual}` predicate。 |
| 四轮检索的顺序、反证与人类定位 | `rules/08:13-116` | 原文 evidence module | 21 evidence/delivery atoms保目标、不保过程 | 顺序与 skip conditions `V/S`，固定五文件 bundle `R`。 |
| 反馈→规则迁移、AI 人工主导、披露、污染 | `rules/12:49-149,247-275` | 文本在 evidence module，skill change route 不加载 | 只剩来源/交付/maintenance controls | 人机边界 `V`，时变政策 `S`；skill-knowledge-migration packet。 |
| S6 条件双轴 | `rules/32:7-18,30-59`; `09:14-23`; `36:42-50,107-144` | 原文可达 verification | E1–E4 固定 pass 配额；N/A 不规范且不计通过 | 条件/例外 `preserve_verbatim`，试验菜单 `merge`，修复状态机和 resolver。 |

### 7.1 V10 applicability 的具体故障

这不是理论风险，而是由当前代码路径直接产生：

- `scripts/lib_v10.py:636-646` 给 route 发出全局/writable/promote/recovery 加 route events；`:677-748` 只按 scope/event/predicate 排除原子，`outcomes.not_applicable` 从未参与；`:751-771` 将剩余项标 applicable/needs_fact。`scripts/resolve_route.py:393-400` 只因 unresolved MUST 阻断，不判断领域事实。
- visual route 总发 `uncertain_result_visualization`（`references/route-contract.json:41-42`）。`VIS.DESIGN.UNCERTAINTY`（`rules/visuals.json:165-242`）是 MUST、无 predicate/exception；“结果精确时 N/A”只在 non-normative outcome，因此所有 visual create/audit 都选择它。
- `evals/atomic-rule-cases.json:4507-4527` 甚至用仅检查“论文 PDF 字体、分页和图表位置”的 `BEH.MANUSCRIPT.RENDER` 证明 `VIS.DESIGN.UNCERTAINTY` applicable；这是过选择被测试固化，而非测试发现问题。
- `VIS.IDENTITY.DATA` 对示意图设 decision exception，但 `VIS.IDENTITY.NO_MANUAL_VALUES` 没有非数据例外。工程概念图若没有数据值，本应验证拓扑/变量/作用关系，而非被当作“缺数据 identity”。

建议所有领域原子至少拥有一个可执行 `applicability`：事实可知则 boolean predicate；事实未知则返回 `needs_fact` 并列一条澄清；合法 N/A 必须带 reason/evidence 且参与 state gate。不要用关键词命中代替领域适用性。

### 7.2 S6 的确定性回归

- V10 `references/state-machine.json:15-17` 将 E2、E4 无条件列为 required；`scripts/state_manager.py:214-227,317-320` 只有 latest `status=pass` 才计数，missing 会阻断。
- `rules/verification.json:558+` 的 E2 recompute 无 numerical-risk predicate；`:1366+` 的 E4 assumptions 无 comparator predicate；`VER.S6.DUAL_AXIS` (`:1870-1941`) 要 E1–E4 全部通过且无 exception；`SKILL.md:137` 同样写成四类 strong evidence 全 pass。
- E3 五个方法 atom 又都由 structural verification event 触发，容易把 V8 的“至少一种风险匹配检验”改成 constraint/invariant/limit/counterexample/sensitivity 五项配额。

修复 acceptance：纯解析模型+无现实 comparator 的 fixture 应得到 `E1=pass, E2=not_applicable(reason=no_numeric_risk), E3=pass(one risk-matched test), E4=not_applicable(reason=no_reality_comparator)`，S6 总体通过但现实域 claim 自动收窄；数值搜索模型则 E2 必须通过；有实测基准才激活 E4。

## 8. 应原样保留的最佳表达（canonical clauses）

为避免下一轮再次“保了意思、丢了约束”，建议以下源段直接作为 canonical clause，允许外包 quick gloss，但不改 normative core：

1. V7 架构公理：`references/v7-architecture-decision.md:17-25,35-46`——渐进披露减少一次加载，不减少能力；不得用一句话代替步骤、公式、例外、失败处理和例子。
2. solution brief：`rules/01-contest-project-pattern.md:48-73`——九项固定信息顺序、面向人类理解、不得伪装为论文正文、人工复述验收。
3. 假设 repair：`rules/03-paper-content-rules.md:499-550` 与 `responsibility-decisions.md:134-139`——假设在每问 S4 冻结，而非第一问完成后补填。
4. S6 条件边界：`rules/32-verification-minimum.md:7-18,30-59` 与 `responsibility-decisions.md:198-210`——E2/E4 有条件、E3 不可空但只需风险匹配之一。
5. 数据处理授权：`rules/16-data-audit-methodology.md:67-106`——全字段 reconciliation、异常仅是 candidate、先说明再授权处理、处理后重算证据能力。
6. 图件真实性：`rules/37-scientific-figure-design.md:22-42`——题意对象到几何/拓扑、变量、力/信息流和最终图的闭环；公式不能替题意发明空间结构。
7. 图件样板与人审：同文件 `:101-123`——先最难样板、技术验收、用户技术/审美验收、再批量；机械检查不能替代拓扑/受力/数据/审美。
8. 图件复原非覆盖：同文件 `:137-169`——原件只读、symbol contract、必要时拆图、最终尺寸像素检查、修复生成新 candidate 并重新授权。
9. 读者解释链：`rules/13-excellent-paper-expression.md:51-65,113-145,173-185,200-284`——六功能链、术语首用、双向 trace、方法与结果的因果闭合。
10. 局部完成边界：V9 `SKILL.md:139-143` 与 `references/manuscript-local.md:1-17`——局部任务可完成而不冒充全局验收。
11. 恢复比例性：V9 `SKILL.md:58-60,85-93`/V10 `SKILL.md:57-69`——只在证据需要时扩大读取，但 fidelity 优先于预算。
12. V10 原子所有权与完整 envelope：`SKILL.md:13-23,31-55`、`references/ownership-contract.json:87-108`——唯一 normative owner、完整 effect 而非 gloss、支持材料不冒充规范。

## 9. 下一轮建议：无损原子 + capability packet + 渐进披露

### 9.1 最小目录形态

```text
skills/
  SKILL.md                       # 模式、授权、状态、装配协议；不放领域大正文
  atoms/*.json                   # 小而完整的触发/义务/证据/例外/依赖
  packets/<capability>/
    manifest.json                # owner、routes、clause IDs、依赖、预算层
    core.md                      # 规范：顺序、条件、例外、人审门；不可截断
    howto.md                     # 操作步骤与修复路径
    acceptance.md                # 异构验收视角
    examples.md                  # 正例、近负例、失败例
    tools.json                   # 可用工具、探测、降级、输出证据
  routes.json                    # raw request/event→packet roots
  lineage/source-clauses.json    # V8 clause→packet/section/disposition/eval
  evals/golden-requests.json     # 人工标注请求→必达/禁达 clause IDs
```

一个 atom 不应只是 `effect + gloss`，而应至少有：

```json
{
  "id": "VIS.SCHEMATIC.TRUTH_MAP",
  "owner": "visual-schematic-engineering",
  "trigger": {"event": "visual_create", "predicate": "visual_kind in [engineering_schematic, conceptual]"},
  "effect": "Before rendering, map problem objects to topology/geometry, variables, interactions or information flow, and visible elements; equations may constrain but may not invent unsupported geometry.",
  "sequence_group": "schematic_design",
  "sequence_index": 2,
  "evidence": ["responsibility_card", "symbol_contract"],
  "exceptions": [{"when": "mapping_unresolved", "outcome": "internal_sketch_only"}],
  "human_gate": "technical_truth_review",
  "packet_sections": ["core", "howto", "examples"],
  "source_clauses": ["V8-R37-L22-L42"]
}
```

### 9.2 装配算法（无重型 runtime gate）

1. 从 raw request 推导 mode、write scope、stage/task/artifact、已知 domain facts；V10 的 route tuple 可直接复用。
2. routes 只选 packet roots，不直接选 206 条散 atom。解析 packet 依赖闭包，拒绝 catchall 充当 reachability。
3. 对每个 atom 运行结构化 predicate：`true` 装入，`false` 记录 N/A reason，`unknown` 只提出最小事实问题；exception 优先于默认 effect。
4. 始终装配每个已选 packet 的 `core.md` 全文及 tools 降级；绝不截断 core 中的顺序、例外、人审门。随后按预算依次加入 `howto → relevant examples → acceptance`。
5. 若超预算，先去重同一 source clause、移除不相关 examples、把低风险 acceptance 延迟到验收阶段；不能把 core 摘成 gloss。若 core 仍超限，拆任务/分阶段，不静默压缩。
6. 输出一份轻量 assembly receipt：route、packet、clause IDs、N/A/unknown、缺失工具、人审门；普通只读回答可仅在响应中呈现，不落盘。

运行时只需 schema load、route match、predicate/exception、DAG closure、token estimate 五步；语义 diff、lineage coverage、独立 agent reload、全量 206 eval 仅在 skill 维护/发布时运行，因此不会形成重型 gate。

### 9.3 上下文预算策略

- **不可压缩层**：selected packet `core`、适用 exceptions、sequence、required tool fallback、human gates。预算预留 45–60%。
- **任务方法层**：与当前阶段匹配的 `howto`，20–35%。
- **例证层**：优先 near-negative/repair，再正例；10–20%，可延迟加载。
- **验收层**：写作/产物生成阶段只装局部 acceptance；promotion/audit 再装全局 acceptance。避免建设规则和验收规则同时全量入场。
- **恢复层**：R0 只读当前 receipt；R1 加 transitive packet closure；R2 才加载 lineage/source corpus。保留 V9/V10 的比例性。

## 10. 下一次迭代的优先遗留项与验收门

按风险/收益排序：

1. **先修 S6 applicability/state machine（阻断发布）。** 恢复 E2/E4 条件 N/A 和 E3 one-of risk matching；加纯解析、数值搜索、有/无现实 comparator 四个近负例。
2. **把 V8 作为语义 baseline，而非 V9 51 gloss。** 为 270/270 H2 群建立 clause IDs，并对子段的顺序、例外、repair、example、human gate 单独切 clause；每条显式 disposition。
3. **补五个失联 routes。** solution brief、paper audit、structured output/run identity、skill feedback migration、engineering/conceptual schematic；golden request 必须证明 clause IDs 实际装配。
4. **先做 visual-schematic packet。** 它是当前最明显弱项：恢复 truth mapping、force/info flow、symbol contract、sample gate、技术/审美人审、最终像素检查、原件非覆盖；区分 data/computed/schematic/conceptual 四类。
5. **恢复机械图件 validator 或诚实降级。** 无依赖时 `unverified`；机械 PASS 与人审 PASS 分栏。不要保留不存在脚本的引用。
6. **把 method notes 定位为 quick view。** 216 行 notes 保留，但所有 packet manifest 必须证明 `core` 可达，notes 不得独占能力。
7. **修 resolver 的 predicate/exception/N/A。** `outcomes.not_applicable` 必须规范化、可计入 conditional gate；unknown 触发最小澄清而不是把所有 MUST 加载。
8. **升级 eval oracle。** 至少包含 positive、near-negative、conflict、route-unreachable、tool-missing、human-gate-unmet、sequence-preserved；golden expectation 由 V8 source clauses 人审签署，不由生成脚本自我推导。
9. **保留比例性优秀设计。** 唯一 owner、readonly default、lazy artifact、local≠global、R0/R1/R2、catchall≠reachability、fresh release tests 全部不得回退。

发布 acceptance 建议设置为：

- source coverage：V8 270/270 H2 群有 disposition，关键子 clause 全覆盖，`unmapped=0`；
- operational reachability：每个 `preserve_*` clause 至少一个 positive route，且 catchall 不计；
- negative precision：每个 conditional clause 至少一个 near-negative，不适用时不得入场；
- sequence fidelity：solution brief、data audit、per-question loop、schematic sample gate、S6 的顺序/one-of 用机器断言；
- exception fidelity：E2/E4、non-data schematic、local edit、tool missing、no comparator 全部可产出有原因 N/A/unverified；
- human boundary：涉及技术真实性、审美、异常处理授权、AI 迁移和正式晋升的 atom 不得由同一 agent 自行标 pass；
- dependency integrity：packet 声明的脚本/reference 必须存在并可探测；不可用时有显式 fallback；
- budget fidelity：在最小上下文预算下仍包含 selected packet 全 core，不以 gloss 替换。

## 11. 覆盖统计、谱系结论与审计限制

### 11.1 本报告覆盖

- V6/V7/V8：38/38 规则文件，270/270 二级规则群；21 个三版完全不变文件、11 个 V6→V7 后稳定文件、4 个 V7→V8 修复文件、2 个两段都变化文件均已归入谱系。
- V6–V8 references：V6 6/6；V7/V8 16/16 文件/文件组（同内容合并审计）；SKILL 控制、关键脚本链和迁移决议均有 disposition。
- V9：1/1 SKILL、10/10 modules、26/26 reference/迁移文件、6/6 eval 文件组、19/19 scripts 按功能组给出 disposition；确认 34 个 V8 active-detail 文件原样拼接，但发现 5 个 route/tool 可达性缺陷。
- V10：1/1 SKILL、9/9 rules JSON、206/206 atom、21/21 references/迁移/schema/method-note 文件、7/7 eval/release 文件、22/22 scripts 按功能组给出 disposition。

### 11.2 相邻版本谱系总判断

```text
V6  大而全正文 + 多 owner/重恢复
 │  V7：修复控制冲突、引入 capability ledger/route/人机决议；领域正文基本保留
 ▼
V8  在 V7 上补 S6 条件双轴；38 rules = 最完整、经裁决的领域 source corpus
 │  V9：34 active-detail files 原样并入 10 modules；控制显著变轻，但 module route 粗、出现失联
 ▼
V9  文本保真较高，操作分辨率较低
 │  V10：从 51 capability gloss 生成 206 atoms；owner/applicability envelope/测试链更精细
 ▼
V10 控制原子化成功，领域原子化不无损；条件适用性和完整方法 packet 尚未建立
```

因此，下一轮不应在 V8 与 V10 二选一，也不应把 V8 重新整包塞回上下文。正确合成是：**V10 的唯一 owner/原子 envelope/状态/比例恢复 + V9 的轻量控制与局部完成 + V8 经 disposition 审核的完整领域 clauses + V7 的 anti-compression/lineage discipline**。

### 11.3 限制

本审计是静态、只读审计；没有修改或重新发布任何版本。规模统计按当前目录内文本/JSON/Python 计数；“字符比例”仅用于展示压缩量，不把篇幅当作质量替代指标。报告没有宣称逐字审定 1,859 个 legacy candidate 的历史真值，而是完整覆盖当前 V8 38 个规则文件的 270 个二级规则群、V9 的实际模块/路由链和 V10 的 206 个 active atom，并对关键子条款做了行级追踪。所有建议修改均留待下一轮实施与独立人审。
