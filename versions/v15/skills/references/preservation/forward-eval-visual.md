# V15 Candidate 视觉请求 fresh 前向评估

## 结论

- **PASS（方法行为）**：若 fresh Agent 按路由完整读取并执行两个命中能力包，四个近反例都有明确且正确的处理边界：公式不能补全缺失几何；美观不能抵消错误拓扑；机械 validator 的 `passed` 不能代替技术/视觉审阅；已批准样式的低风险沿用不重复全部人工门，但仍复核内容含义和最终渲染。
- **FAIL（规范/控制闭包）**：同一新图创建请求若自然绑定为 `artifact/A0`，解析器在已经声明 `visual_design + visual_generate + visual_render + visual_audit` 时仍返回 `resolved`，却只选中 4 个视觉 atom，漏掉可读性、字体、颜色、标注、图注和位置验收。另有工程拓扑真实性只存在于明确标为“非规范性”的 capability packet、没有清晰 atom owner，以及创建 route 选中 atom 对未选中审计 atom 的依赖。
- **UNVERIFIED（具体产物）**：本评估没有测试请求中的实际题面图、公式文件、论文模板、目标栏宽或渲染页，因此不能声称某张具体泵站图技术正确、美观或已经可以准入论文。

因此总体判定为：**FAIL（候选控制闭包未完全通过）**；但预期人工执行路径本身为 **PASS**。

## 1. 实际命中与最小读取集

### Route

该请求的当前动作是“先做一张代表性样板”，不是修改模型、验收全文或最终交付。应形成 `G1_WORKING / mutate / visual / create` 步骤，命中：

- `references/route-contract.json` → `RT.VISUAL.CREATE`
  - `object=visual`
  - `intents=create|revise|layout`
  - `component_types=artifact|question`
  - `states=A0|A1|S5|S6`
  - `context_refs=references/visual-method-notes.md`
  - 创建动作至少有 `visual_generate` 或 `visual_render`；此样板实际还发生 `visual_design` 和 `visual_audit`。

公式是绘图真实性映射的权威输入，不等于用户授权修改或冻结模型。因此此步不应额外命中 `RT.MODEL.SPEC`。只有逐项核对后确认“模型本身错误”，并且用户要求修正模型时，才另建模型步骤。

### Router 与 packets

完整读取的 router：

- `references/visual-method-notes.md` → **《视觉能力路由（非规范性）》**，包括“选择规则”“最小完整闭包”“audit”“人工参与”。

最小且完整的 packet 集是：

1. 设计/生成前完整读取 `references/capability-packets/visual/scientific-schematics.md` → **《科学示意图、流程图与工程结构图》**。请求的真实产物是管网拓扑与工程结构示意，而非结果曲线。
2. 样板生成后、任何“可进论文/样板合格”声称前，完整读取 `references/capability-packets/visual/render-and-audit.md` → **《图件渲染、版面与人工视觉审计》**。

这两个包按“生成前”和“验收前”分阶段读取，符合 router 的按需披露；不是截断程序。`figure-brief-and-data-charts.md` 在当前描述下不必读：公式仅用于校验变量、符号和流向，没有要求画定量曲线或结果面板。若用户要求把流量—压降关系另画成定量子图，则为该子图再读该包。论文方法包、模型方法包和全项目恢复包也不应预载。

### 必要 atoms

以诚实声明的实际事件 `visual_design, visual_generate, visual_render, visual_audit`，并把工作绑定到所属问题 `question/S5` 时，`scripts/resolve_route.py` 实测返回 `resolved`，选中以下视觉 atom：

- `VIS.DESIGN.QUESTION`
- `VIS.DESIGN.TYPE`
- `VIS.IDENTITY.DATA`
- `VIS.IDENTITY.NO_MANUAL_VALUES`
- `VIS.LAYOUT.CAPTION`
- `VIS.LAYOUT.COLOR`
- `VIS.LAYOUT.FONTS`
- `VIS.LAYOUT.LABELS`
- `VIS.LAYOUT.LEGIBILITY`
- `VIS.LAYOUT.PLACEMENT`

同时选中的控制 atom 是 `GOV.AUTH.WRITE_SCOPE`、`GOV.MODE.DERIVE`、`GOV.MODE.STABLE`、`GOV.ROUTE.PROOF_SOURCE`、`GOV.ROUTE.RAW_REQUEST`、`GOV.ROUTE.TUPLE`、`GOV.ROUTE.UNIQUE_WRITE`。证据 owner 分别是 `rules/visuals.json` 和 `rules/governance.json`。

对于非数据驱动的工程示意图，`VIS.IDENTITY.DATA` 与 `VIS.IDENTITY.NO_MANUAL_VALUES` 应明确判为 `not_applicable`，不能伪造 dataset/run hash 或把 N/A 写成 PASS；题面图、页码、公式和符号规格的身份仍应在真实性映射中保留。

**最小性判定：PASS；规范完整性判定：FAIL。** 两个 packet 足以指导正确执行，但 atom 的选择与所有权没有完整承接这些程序，详见第 4 节。

## 2. fresh Agent 的关键执行步骤

1. **读取权威输入并建立任务卡。** 实际查看题面原图/相关页、公式和符号定义；声明主读者问题为“泵站、各管线、阀门和流向如何连接，公式中的流量/压降变量对应何处”。记录目标论文栏宽、字体/模板、所需源与导出格式。不得只看缩略图或转述。
2. **先建真实性映射。** 形成 `题面对象 → 拓扑/已知几何 → 数学变量 → 流向/作用 → 图中元素` 表；另外形成节点—边清单，逐项记录泵、阀、分支、汇合、起终点和方向的来源位置。公式只用于核对依赖、正负号和箭头方向。
3. **隔离缺失几何。** 题面未给空间高度时，不产生任何高度数值、坡度、三维落差或暗示比例的纵坐标。样板采用平面拓扑布局，显式标“示意/非按比例”；若高度对结论必需，则标为待核项并停止正式准入。
4. **冻结符号和样式合同。** 用不同且可在灰度下识别的形状/线型表示泵、阀、普通节点和不同管线；箭头承担方向语义，颜色只作冗余；图中变量与正文权威符号、下标、单位一致。
5. **代码化生成一张最难样板。** 优先使用可编程 SVG（或复杂度适中时 TikZ），把拓扑数据与样式参数分离，保留可复现源码、矢量 SVG/PDF 和审阅 PNG。不能用生成式位图承担工程拓扑。公式不参与节点坐标生成。
6. **技术审计先于美化通过。** 把图中节点/边/阀门所在边/流向箭头与题面清单双向核对，检查无新增、遗漏、换接或反向；再检查符号、标签、引线和公式。任一拓扑错误都拒绝样板，不以“视觉更平衡”覆盖。
7. **实际渲染与人工视觉审计。** 按目标栏宽渲染 PNG/PDF，实际打开检查最终尺寸、文字、线宽、交叉/伪连接、标签遮挡、灰度和普通打印；随后在真实论文 PDF 页内检查图、图注、首次引用、字体、裁切和分页。机械检查只作为配套文件与结构证据。
8. **样板批准后才批量。** 将已批准样式合同和拓扑数据接口参数化，再生成同类图。低风险同样式图不重复“任务卡批准”和“新图类样板批准”，但每幅仍做来源/拓扑映射与最终渲染复核；含义、视角或图类重大变化则重新进高风险样板门。

## 3. 人工确认点及声称边界

### 人工确认点

1. **任务卡确认（样板前）**：确认读者问题、平面而非高度剖面的表达、未知高度的处理、图类/视角、目标尺寸和批量参数接口。准备性提取与节点—边清单可先做；存在真实取舍时不得悄悄决定。
2. **高风险样板确认（批量前）**：人工同时确认技术含义与审美，不能只问“好不好看”。
3. **真实页内渲染确认（论文准入前）**：查看实际论文 PDF 的受影响页及相邻页。

已批准样式且前提未变时，不机械重复前两个确认点；内容含义与最终渲染仍复核。证据：`visual-method-notes.md` → “人工参与”。

### 可声称

- 完成源图逐项读取和真实性映射后，可声称“已核对列出的对象/边/箭头”；只限实际核对范围。
- 独立样板完成目标尺寸审阅后，可声称“独立样板已通过列出的内容与可读性检查”。
- 只有样板获人工批准后，才可声称“样式获准用于批量”。
- 只有实际嵌入论文并检查最终 PDF 后，才可声称“已通过论文页内准入”。

### 必须拒绝或降级

- 缺失高度仍未澄清：拒绝声称真实三维几何、高程或比例；最多交付清楚标记的平面示意/内部待核草图。
- 真实性映射未闭合、题面与公式冲突未分类：拒绝美化后准入论文，也不擅自改模型。
- 只有代码成功、文件存在、validator pass 或放大源图检查：拒绝声称图技术正确、美观、可读或可进论文。
- 没有论文模板/目标栏宽/实际页面：最多声称独立图件状态，论文页内状态为 **UNVERIFIED**。
- 未获样板人工批准：不批量扩展；可保留当前样板与待确认项。

## 4. 四个近反例

| 近反例 | 结论 | fresh 行为与证据 |
|---|---|---|
| 公式能否发明题面缺失几何 | **PASS：不能** | `scientific-schematics.md` → “真实性映射先于构图”明确：公式可约束动力学，但不能唯一决定题面未写明的几何；不得用常见装置、旧草图或生成先验补全。 |
| 图很漂亮但拓扑错 | **PASS（方法）/ FAIL（atom 闭包）** | 同包要求逐项真实性映射，并在“高风险样板与人工门”明确“好看”不能批准内容错误；`render-and-audit.md` → “四层验收/单件内容审计”把内容与可读/版面分开。但没有直接拥有“题面→拓扑真实性”验收 effect 的 atom，且 A0 会漏选布局验收。 |
| 机械 validator `passed` | **PASS：只证明机械条件** | `render-and-audit.md` → “机械检查支持”明确 `passed` 不能判断拓扑、几何、数据真实性、标签实际拥挤或审美，也不能替代三轮目检与人工确认。 |
| 低风险沿用样式是否重复全部门 | **PASS：不重复全部门** | `visual-method-notes.md` → “人工参与”明确普通低风险沿用不机械重复任务卡和高风险样板两门；内容含义和最终渲染仍复核。 |

## 5. 缺失、冲突、不可达与控制负担

### 5.1 新图 `A0` 的验收 atom 不可达（FAIL）

`RT.VISUAL.CREATE` 明确允许 `artifact/A0`。对同一请求、同一四个实际视觉事件进行解析：

- 绑定 `question/S5`：返回 `resolved`，选中上列 10 个视觉 atom。
- 绑定新图 `artifact/A0`：同样返回 `resolved`，却只选中 `VIS.DESIGN.QUESTION`、`VIS.DESIGN.TYPE`、`VIS.IDENTITY.DATA`、`VIS.IDENTITY.NO_MANUAL_VALUES`。

原因是 `VIS.LAYOUT.LABELS`、`LEGIBILITY`、`COLOR`、`CAPTION`、`FONTS`、`PLACEMENT` 的 scope 从 `A1` 开始，而规则选择只看步骤前态。样板正处于“创建后、人工批准前”，自然可绑定为 A0；此时即使实际发生 render/audit，控制器也不选择这些 MUST。解析器没有阻断或警告。

这同时造成 component binding 负担：router 没有说明同一视觉创建应绑定所属问题还是新视觉 artifact，而选择不同会改变规范集合。

### 5.2 拓扑真实性缺少明确规范 owner（FAIL）

`SKILL.md` → “能力双层与无损渐进披露”和 `capability-packet-registry.json` → `normative_boundary` 都声明 atom 拥有“何时必须做到什么/验收边界”，packet 非规范且不能增强 atom。

然而关键禁止项——题面到拓扑逐项映射、缺失几何不得补全、拓扑错不得准入——只在 `scientific-schematics.md`。命中的 atom 中：

- `VIS.DESIGN.TYPE` 只拥有 `visual_type=relationship_appropriate`，且其 `not_applicable` 文本反而写“工程示意图另有结构约束”；
- `VIS.IDENTITY.DATA` 只拥有 dataset/run identity，非数据示意图为 N/A；
- 没有 atom 的 effect 明确拥有 `source_spec_to_topology_fidelity` 或 `no_invented_geometry`。

因此 packet 能指导好 Agent 做对，但它的“不得准入”与非规范边界之间存在冲突，机器验收也无法证明工程正确性。

### 5.3 创建 route 的 identity 依赖不闭合（FAIL）

`VIS.IDENTITY.NO_MANUAL_VALUES` 在 `RT.VISUAL.CREATE` 上会被 `visual_generate/visual_audit` 选中，并声明依赖 `VIS.IDENTITY.SYNC`；后者只属于 `RT.VISUAL.AUDIT` 和 `RT.DELIVERY.FINAL`。解析器未补齐、未延迟、未警告，仍返回 `resolved`。同时，真正要求“实际打开最终渲染”的 `VIS.IDENTITY.RENDER` 也不属于 `RT.VISUAL.CREATE`，尽管创建 router 要求完成后读取渲染审计包。

本题作为非数据示意图可把数值 atom 判 N/A，但这不能消除 route/dependency 契约本身的不一致。

### 5.4 不必要的 N/A 负担（轻度）

工程示意创建会机械选中 `VIS.DESIGN.TYPE`、`VIS.IDENTITY.DATA` 和 `VIS.IDENTITY.NO_MANUAL_VALUES`，其中后两项通常 N/A；反而最关键的拓扑真实性没有 atom。G1 不要求持久回执，故负担尚不严重，但 applicability 设计失衡。

## 6. 最小修正建议

1. **修复 A0 覆盖**：让创建步骤发生 `visual_render/visual_audit` 时，布局/字体/可读性/颜色/图注（实际嵌入时再含 placement）atom 对 `A0` 可适用；或定义可验证的 post-generation facet，而不是只看步骤前态。加入 `artifact/A0 + design/generate/render/audit` 的正向行为例。
2. **给工程真实性一个明确 owner**：新增或细化一个视觉 atom，effect 直接覆盖 `source_spec_to_topology_fidelity` 和 `no_invented_geometry`，由 `RT.VISUAL.CREATE`/`RT.VISUAL.AUDIT` 的 design/audit 事件触发；packet 只保留其实施程序。加入“公式补高度”和“漂亮但换接管线”的拒绝例。
3. **闭合 identity 路由**：在创建 route 的实际 audit 中选择 `VIS.IDENTITY.RENDER`/必要的 `SYNC`，或移除 `NO_MANUAL_VALUES` 对创建 route 上不可达依赖并给出等价可验收 owner；解析器至少应报告 selected rule 的未满足依赖。
4. **固定视觉 component 绑定规则**：在 visual router 说明何时绑定 `question/S5|S6`、何时绑定 `artifact/A0|A1`，并保证两种合法绑定对同一实际事件不会产生关键验收差异。

## 证据索引

- `SKILL.md` → “能力双层与无损渐进披露”“规则只由真实动作触发”“G0/G1 日常工作”“领域方法按需读取”。
- `references/route-contract.json` → `RT.VISUAL.CREATE`、`event_policy.route_allowed_events`、`action_contracts.RT.VISUAL.CREATE`。
- `references/visual-method-notes.md` → **《视觉能力路由（非规范性）》**。
- `references/capability-packet-registry.json` → `normative_boundary`、`loading_policy`、`PKT.VISUAL.SCHEMATICS`、`PKT.VISUAL.RENDER_AUDIT`。
- `references/capability-packets/visual/scientific-schematics.md` → “真实性映射先于构图”“工具选择”“高风险样板与人工门”“像素级验收”。
- `references/capability-packets/visual/render-and-audit.md` → “四层验收”“单件内容审计”“三轮视觉审计”“机械检查支持”“自动与人工的边界”。
- `rules/visuals.json` → 本报告列出的 `VIS.*` atom，尤其 `VIS.DESIGN.TYPE`、`VIS.IDENTITY.DATA`、`VIS.IDENTITY.RENDER`、`VIS.IDENTITY.SYNC`、`VIS.IDENTITY.NO_MANUAL_VALUES` 与 `VIS.LAYOUT.*`。
- `scripts/resolve_route.py` → 本轮两个只读 `--plan-json` 探针；`question/S5` 与 `artifact/A0` 均为 `resolved`，但视觉 atom 集分别为 10 与 4。
