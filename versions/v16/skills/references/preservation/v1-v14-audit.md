# V1–V14 规则文本总审计与 V15 Candidate 组织决议

审计日期：2026-08-27  
源根：`/mnt/d/AI/AI_program/2021（第四题）/总skill`  
候选根：`/mnt/c/Users/35190/skills_v15_candidate`  
状态：候选重组，未冻结、未安装、未覆盖任何历史版本。

本文件是三份逐段审计的总索引，不替代其逐文件、逐规则与逐 atom 处置：

- [V1–V5 全量文本审计](audit-v1-v5.md)：691 行；173 个逻辑规则/参考文本、73 个独立内容哈希；
- [V6–V10 全量文本与运行链审计](audit-v6-v10.md)：440 行；覆盖 V8 38/38 规则文件、270/270 个 H2 规则群，V9 10/10 modules、V10 206/206 atoms；
- [V11–V14 atom、方法与可达性审计](audit-v11-v14.md)：418 行；覆盖 51/51 capabilities、206/206 atoms、7/7 method notes 及其直接机器契约与解释器。

三份报告分别按 `preserve_verbatim`、`preserve_semantics_rewrite`、`merge`、`retire` 给出处置与来源位置。历史文件始终只读；同哈希副本只逐字审计一次，但其全部版本身份均在报告中登记。

## 一、总判断：问题不是原子化，而是用摘要替代了原子背后的完整方法

V1–V14 的演化不是“越来越好”或“越来越短”的单线过程，而是在可达性、上下文负担和语义保真之间摆动：

| 版本段 | 实际进步 | 实际损失或风险 | 本候选的取舍 |
|---|---|---|---|
| V1 | 数据、模型、写作、图表、审计和人类决策的具体方法很丰富 | 文件巨大、重复 owner、旧目录/年份/模板混入规则 | 提取完整程序、例外、反例与修复；退役项目绑定常量和重复控制 |
| V2–V4 | 稳定 ID、职责验收、权限表达逐步清晰 | 详细正文虽留在 portfolio/archive，却从活动路由失联；V4 图件 205→33 行、数据 153→34 行，主要丢失“如何做” | 原子保留验收，能力包恢复实施，不以“档案里仍有”冒充可达 |
| V5 | 通过哈希回填恢复了详细文本 | 论文一次加载 2,371 行、绘图一次加载 426 行；多层重复争夺注意力 | 不恢复整文件叠加，按真实能力重组 |
| V6–V8 | V7 建立渐进披露/谱系纪律，V8 形成 38 份、7,356 行的成熟详细规则并补双轴验证与科学图件 | 控制、状态、回执仍有重复；若全读仍很重 | 以 V8 详细 clauses 为主要方法基线，逐项裁掉固定门禁 |
| V9 | 34 个 V8 活动详细源 7,038 行几乎逐字进入 10 个 modules；控制明显变轻 | 模块级 route 太粗，solution brief、稿件审计、结构化结果、Skill 反馈迁移、图件 validator 等出现“文本存在但任务不可达” | 保留轻控制与局部完成，路由改指短 router，再指完整 packet |
| V10 | 51 capabilities 被拆成 206 个唯一 owner atoms；完整 envelope、typed state、lazy artifact、R0/R1/R2 和离线维护链很优秀 | 迁移基线取 51 条 capability gloss，而不是 V8 详细正文；7 份 notes 仅 216 行、约为 V8 活动详细层的 3.1%；条件适用性也被过度收紧 | 206 atoms 继续作规范触发/验收层；gloss 永不再充当完整方法 |
| V11–V14 | G0–G3 比例激活、自然语言多步骤计划、逻辑平台、sealed ChangeSet、void execution、Skill 授权隔离、R1 读取回执与 baseline 精确绑定成熟 | 领域 notes 仍只有 251 行，visual 仅 20 行；V12–V14 rules 全部字节不变，方法能力没有随控制面升级；0 atom 使用 `context_ref` | 完整继承 V14 控制哲学，本轮不加门，只重建方法层与可达索引 |

因此，真正的因果链是：

`详细能力 → 被压成目录/验收摘要 → 以摘要而非详细 clause 作为迁移基线 → atom 能选中“要做到什么”，但 Agent 失去“怎样做到”`

原子化本身没有错。错误是把原子同时当成索引、规范、教程、例外库和失败修复手册，最终只能保留一个 gloss。正确结构是让原子保持小而可判定，让完整方法成为被原子/route 精确选中的独立能力包。

## 二、谱系与证据边界

### 根 `skills/` 是混合年代快照

顶层 `skills/SKILL.md` 与 `skills/01-...md` 至 `16-...md` 构成 V1 权威集；同目录 `skills/rules/` 还混有 V3/V4/V5 副本、V6 规则和 2026-08 修复。后来的 `rules/36`、`rules/37` 不能倒算成 V1 原生能力，但它们是旧能力在真实失败后被补回的有效证据。

### 现存迁移账本的证明范围

候选已补回 V14 清单引用但包内缺失的两项 V9 历史源：

- `references/migration/v1-v9-capability-ledger.json`：SHA-256 `c44427ba0829e71d37c4f6f6012c35760e70647b0022fee6b239190fab13166e`，1,924 entries / 1,859 source spans；
- `references/migration/native-capabilities.json`：SHA-256 `c160257539667dd727bd19653599de17c9343f7d3d6cd9185ebe6eab17873ce6`。

它们保存原文 span、哈希、owner family 和历史 disposition，能防止来源静默消失；它们不能证明当前 route 可达、方法仍完整或行为正确。运行时不加载这些大账本，只有审计、能力恢复或发布迁移时定向读取。

## 三、保留原文的 canonical 表达

以下短句或短段因为同时包含边界、失败模式或顺序信息，保留原文或极近语义；它们不是装饰性金句，而是能力的压缩锚点。完整出处和周边程序见三份分段报告。

### 控制、授权与恢复

> Use the stages as a reasoning map, not as an autonomous workflow engine.

> Cross-question consistency means compatible facts and interfaces agree; it does not mean methods, formulas, validation tests or section structures must look alike.

> Correct the earliest faulty layer, regenerate every downstream artifact, and then revise the paper.

> 创建空目录只证明脚本执行过，不证明项目已经初始化完成。

保留 V4 的权限合取：当前状态允许、前置/退出证据成立、兼容的人工决定已经明确、用户请求授权当前动作；四者不能互相代替。保留“理解不等于批准”“摘要只是导航”“叙述不是权威事实”和局部完成不冒充全局完成。

### 数据、模型与验证

> 解析器必须显式失败，不能静默猜测；结构性空值与缺失值必须分开。

> 不能用摘要数字相等代替逐字段对账，也不能用主脚本再次读取自己的输出证明自身正确。

> ±5%、±10%、±20%只能作为缺少先验时探索网格，不能冒充现实不确定性。

保留“异常候选不是处理 authority”“固定原方案代入与重新优化必须分开”“每问 E3 选择真实失败风险而不是机械运行同名实验”“现实对照不存在时不得伪造 E4 能力”等完整程序。具体试验菜单作为方法选项，不升级为固定配额。

### 论文、证据与表达

> 问题分析解释“这是什么问题、为什么这样分问、通常怎样处理、本文为何选择当前方向”，但不提前展开具体算法实现。

> 逐句审计不能只问“这句话是否正确”，还要问“它在当前位置承担什么职责、前一句能否推出它、后一句是否仍需要它”。

> 公式解释的审计单位是数学职能，不是 LaTeX 环境、编号或换行数量。

> 论文是数学论证，不是程序运行报告。

> 建模论文的基本表达单元不是显得专业的长句，而是来意、定义、动作、理由、证据和落点。

> 代码很复杂、运行很久或使用规范算法名，不自动取得摘要席位。

> 禁止为了模仿优秀语气而全段重写。

> 不得先凭常识固定模型，再只寻找支持既定选择的文献。

> 文献调查通过只证明证据准备充分，不替用户选择模型。

> 不得为补齐档案而虚构过去的时间戳或操作。只能把可由 identity/依赖支持的内容标为事后重建。

> 不能把“已有文件”误当成“可靠知识”。

> 人工主导不是在终稿阶段补一句“已审核”，而是在人会改变研究方向的节点真正拥有知情选择权。

### 图表与科学示意图

> 图像必须独立承担一种不可由相邻表格或正文替代的表达任务。

> 好看不能批准内容错误，正确也不能批准最终尺寸下难读的图。

> 三组独立判定，不能用高清、美观或排版整齐掩盖内容错误，也不能以数值正确为由接受最终尺寸下不可读或表达形式不合适的载体。

保留完整真实性映射：

`题面对象 → 几何/拓扑 → 数学变量 → 力/作用/信息流 → 图中元素`

公式只能约束或解释题面已经支持的结构，不能替题意发明缺失几何。自动检查只能处理文件、结构、像素、字体和基础碰撞；不能判断拓扑是否忠于题面、力是否正确、数据是否支持结论、标签是否真的拥挤或图是否美观。

## 四、保留语义但重写/合并的内容

以下内容的能力必须保留，但旧表达与当前项目、版本或控制器耦合，已重写并合入一个当前 owner：

- 固定目录树改为逻辑 platform role、consumer、identity 和按需物化；
- 固定章节名、标题层级、字数、图表数改为任务—主张—证据—读者职责；
- 固定字体、页边距、颜色、DPI 和外部“风格权威”改为当前官方/profile + 实际环境探测 + 最终尺寸验收；
- 算法目录改为候选库与误用边界，不能取得选模权；
- 逐文件/逐段验收表改为一个语义 ChangeSet 的最小直接消费者闭包；
- 多份 handoff、receipt 和状态 owner 收敛到当前 typed state/正式 execution；
- 文献、AI 披露、赛事规则和提交规范改为运行时重新核验当前官方材料；
- V8 大规则和 V9 大 module 合并为按任务读取的完整 packet，不作为并列运行权威；
- solution brief 的九项技术解释顺序、非论文身份和人工复述已经恢复到模型实现/结果包；不默认创建固定 `docs/<task>/solution_brief.md`。

## 五、从活动运行时退休的旧做法

`retire` 不表示删除历史原文，而是禁止它继续作为日常强制行为：

- 每次启动、局部改稿、暂停或里程碑都全项目/全规则复读；
- 普通 G1 的逐文件 proposal、start/end receipt、execution ledger 和全工作区 manifest；
- 为每条未触发规则逐项证明“为何跳过”；
- 每段固定八字段、稿件七级镜像状态、固定日程或一次只能改一个文件；
- 固定年份、旧政策 URL、特定赛事模板、固定目录、字体、页边距、颜色、图表数量和章节配额；
- 用 regex、标题、关键词、文件存在、退出码、断言数或 mutation 数充当领域正确性；
- 把十阶段工作地图或稿件验收表变成第二状态机；
- 没有消费者的默认 README、讲解稿、报告、manifest、空目录或占位文件；
- 把自动脚本、AI 自审或发布 gate 当作人类技术/审美/正式责任的替代品；
- 已被当前契约声明为 legacy-only 的 V10 change-envelope 接口继续冒充活动维护入口。

## 六、V15 Candidate 的四层组织

| 层 | 当前载体 | 责任 | 运行时读取 |
|---|---|---|---|
| 控制与机器契约 | `SKILL.md`、runtime/route/state/artifact/ownership contracts | 权限、状态、强度、证据持久化、动作边界 | 只按当前 tier/route 需要 |
| 规范 atom | `rules/*.json` | 何时适用、必须产生什么 effect、证据与接受边界 | resolver 选择的小集合 |
| 方法能力 | 8 个短 router + `references/capability-packets/` | 完整步骤、决策树、例外、修复、正反例、人工确认 | router 选择 1–3 个包并完整读取 |
| 谱系档案 | `references/migration/`、`references/preservation/` | 原文、hash、版本身份、disposition、审计报告 | 仅审计/迁移/恢复能力时读取 |

本候选现有 22 个完整能力包、2,447 行正文；8 个短 router、180 行；总计 2,627 行。它不是把 V8 的 7,000 多行重新常驻，而是按真实任务组合：

| 领域 | packet 数 | 主要能力 |
|---|---:|---|
| project | 3 | 范围与计划、平台/工件、R0/R1/R2 与交接 |
| data | 2 | identity/统计单位/对账/能力审计、处理/冻结/传播 |
| modeling | 3 | 重述/基线/候选/人工选模、数学规格、实现/结果/逐问技术讲解 |
| verification | 3 | E1/E2、E3/E4、不确定性/稳健性 |
| manuscript | 4 | 结构职责、表达论证、读者/局部编辑、LaTeX/终稿 |
| visual | 3 | 数据结果图、科学/工程示意图、渲染与人工视觉审计 |
| evidence | 3 | 检索/来源、provenance/handoff、正式交付/合规 |
| governance | 1 | Skill 审计、变更、独立验证与回滚 |

[能力包映射表](../capability-packet-registry.json)覆盖当前 51 个 active capability：44 个由方法包实现，7 个治理/状态能力直接由规范控制契约完整拥有，避免再用 prose 复制第二套控制权。每个已选 packet 必须完整读取；需要更多包时按真实阶段拆分并携带续接胶囊，不能把它们重新摘要成一个万能 checklist。

## 七、绘图能力的专门修复

旧 visual gloss 的主要问题不是“不够严格”，而是只说正确、美观、可读，却没有从题面构造示意图的工作程序。本候选分为：

1. [图件任务卡与数据结果图](../capability-packets/visual/figure-brief-and-data-charts.md)：先定义读者问题和 delete test，再定义比较、单位、数据 identity、图类、共享视觉语义、图注与正文闭环；
2. [科学示意图、流程图与工程结构图](../capability-packets/visual/scientific-schematics.md)：先做真实性映射，再处理工程视图/线型/受力、算法流程、symbol contract、工具分流和高风险样板；
3. [图件渲染、版面与人工视觉审计](../capability-packets/visual/render-and-audit.md)：独立图件、真实 PDF 页内尺寸、灰度/退化三轮检查，字体/LaTeX、局部修复与机械/人工边界。

正式关键图、新图类或批量视觉系统只保留三个实质人工点：任务卡、最难/最高风险样板、最终页内渲染。沿用已批准样式的低风险图不机械重复前两门。候选同时恢复 V8 的 `scripts/validate_figure_assets.py`，用于 SVG/PNG/PDF/字体等机械检查；脚本通过不能批准技术真实性或审美。

## 八、明确未在本轮改动的控制面与规范缺口

用户已经决定当前控制器使用体验尚可，本轮只做规则文本审计与方法架构恢复。因此下列发现保留为未来独立提案，不声称已修复：

1. **V10/V14 applicability**：206 atoms 中 205 个 `MUST`，多数缺 predicate/exception；non-normative `outcomes.not_applicable` 未进入 resolver 判定。
2. **S6 条件语义**：V8 的 E2/E4 条件触发与 E3 风险匹配 one-of，在 V10 state gate 中被收紧为 E1–E4 全 pass；`RT.VERIFY.MODEL` 还把结构验证与现实验证强制绑在同一动作中。本候选方法包恢复正确判断方法，但未修改 atom/state machine，正式 checkpoint 仍需后续单独决议。
3. **适用性与 route 粒度**：只读“提出数据处理候选”没有精确 route；compare-only 不触发 baseline atom；同一结构验证事件会选择全部 E3 菜单 atoms。这些都可能迫使 Agent 多做、伪造事件或只靠非规范方法包自律。
4. **依赖与视觉闭包**：99 个 `depends_on` edge 仍只被展示，不由 resolver 展开；route 的部分 `when_any` 仍没有结构化消费。新图绑定 `artifact/A0` 时会漏选布局、字体与可读性 atoms，工程拓扑真实性没有明确规范 owner，CREATE 的 identity 依赖也不闭合。本轮只补方法 route 与 manuscript render context，不重写 resolver。
5. **稿件 closure 旁路**：`manuscript-change-closure.json` 要求稿件步骤缺少五个 facts 时阻断，但当前解析器只在已有 `change_class` 时调用检查，`facts={}` 的稿件写步骤仍可解析为 `resolved`。本轮保留证据，不顺手改 V14 解析器。
6. **状态并发**：普通 state mutator 尚无统一 lock/CAS，固定 `.tmp` 可能产生 lost update/竞争。
7. **请求隐私**：semantic plan、execution/state、receipt 和 inline CLI 对完整 raw request 的持久化/脱敏边界尚未定义。
8. **发布保护**：V14 三个活动 driver 不直接保护 9 个 rule bundle 的 semantic projection 或方法包行为；本次新增覆盖/anchor/hash validator 只是迁移定向证据，不自动扩成永久发布门。
9. **视觉参照资产**：已恢复完整提示和机械 validator，但仓库没有一组经用户认可的工程示意图正例/近反例资产；技术真实性与审美仍需要真实项目中的人工样板积累。
10. **solution brief 可达性**：九项程序已恢复到 modeling packet，尚未新增专门 atom/route/artifact identity，以避免本轮顺手改控制面。

这些项目不会作为普通数学建模任务的额外门禁。若未来真实使用再次暴露相应故障，应按具体失败、最小影响闭包和用户独立授权逐项处理。

## 九、独立 fresh-context 前向评估

三名未读取本总审计、迁移档案或开发结论的评估者，分别从实际请求出发解析 route、完整读取命中 packet、推演正反例并运行只读 resolver 探针：

- [数据—模型—S6 评估](forward-eval-data-model.md)：数据语义、候选处理、copy-on-write、简单基线、独立 oracle 和不确定性方法通过；总体 `FAIL` 来自 E2/E4 的诚实 N/A 无法通过 S6、model-axis 强绑 E3/E4，以及若干 route/atom 过宽或缺失。
- [稿件局部修改与 Q2 技术讲解评估](forward-eval-manuscript.md)：局部阅读闭包、最早错误层、论证不变量、受影响页面验收、九项讲解、非论文身份和四个近反例通过；总体 `FAIL` 来自可复现的 closure-facts 校验旁路。评估指出的 local-edit→LaTeX 包交叉引用缺口已在方法路由补齐，不改变控制面。
- [工程示意图评估](forward-eval-visual.md)：真实性映射、公式不补几何、拓扑优先于美观、机械 validator 边界和低风险复用均通过；总体控制闭包 `FAIL`，原因是 `artifact/A0` 漏选验收 atoms、拓扑真实性缺规范 owner 和 CREATE identity 依赖不闭合。没有实际题面、公式与论文页，因此具体图件质量仍为 `UNVERIFIED`。

这组结果支持一个更窄但更可信的结论：能力包确实恢复了 fresh Agent 的实施判断，而且没有要求一次加载全部规则；它同时证明“方法行为可用”不能冒充“V14 控制器已经闭合”。本轮依用户决定只修内容层明确遗漏，其余失败全部保留为可复现的未来变更输入。

## 十、当前候选的验收边界

本轮可以声称：V1–V14 规则文本已按三个年代段完成逐文件/逐规则族审计；历史原文与哈希谱系可追；当前 51 capabilities 均有明确的规范 owner 和方法/契约去向；详细“如何做”已经从 gloss 恢复为按需可读能力包；旧的固定门禁没有重新进入日常控制器。

本轮不能声称：所有历史句子都应继续活动化；V15 已发布/安装；控制器已解决 applicability、并发、隐私或发布语义保护；代码生成的科学示意图已在所有题型达到“完美”；文件和 anchor 存在本身已经证明行为能力。

冻结前还需要带真实项目工件的端到端试用与用户人工审阅，尤其是一张真实工程示意图、实际数据异常处理及无现实 comparator 的 checkpoint。只有用户明确批准，候选才进入冻结或安装。
