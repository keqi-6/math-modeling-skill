# 项目平台与工件生命周期

适用于项目初始化、在现有项目中新建路径、选择工具链、产生工作输出，以及把候选结果提升为里程碑或交付工件。它说明操作顺序，不是一份固定目录模板。

## 规范边界

本包不复制角色、路径、class、字段枚举或提升门。当前值必须直接读取以下唯一 owner：

- `references/project-platform-contract.json`：G1 路径命名空间、正式工件的逻辑角色与路径/class 映射、新旧项目策略和物理懒创建边界；
- `references/artifact-contract.json`：准入字段、lifecycle、identity class、临时策略、提升与传播规则；
- `rules/project.json` 中 `PRJ-STRUCTURE-001` atoms；
- `rules/governance.json` 中 `ART-LAZY-001`、`ART-PROMOTE-001` atoms；
- `SKILL.md` 与 `references/runtime-policy.json`：G1 ChangeSet 和 G2/G3 正式登记的运行边界。

本包中的示例角色只表达判断问题，不形成第二套枚举。若文字与当前契约不一致，以契约为准。

历史 atom `PRJ.STRUCTURE.LAZY` 中的 “admitted artifact / 已准入文件” 在本包内按广义 retained path 理解：它要求父目录服务于一个已经通过命名空间准入、确实会被写入和消费的文件，不等于每个普通 G1 文件都要提交 `artifact proposal` 或取得正式 identity。这样保留其“禁止空脚手架”的能力，不把旧术语扩张成逐文件门禁。

## 先审计现有平台

在决定路径或工具之前，定向检查：

- 项目根、现有入口、官方输入位置和不可移动来源；
- 已有源码、结果、技术文档、稿件、图件、交付与控制数据的真实位置；
- 构建、运行、依赖管理、模板和团队协作方式；
- 忽略规则、缓存/临时输出、命名冲突和已有消费者；
- 当前正式工件及其生产者、验证状态和下游引用。

检查只覆盖当前动作需要判断的平台部分，不因初始化或新增一个文件而遍历全部内容。已有可用工具链优先沿用；只有用户或官方要求、现有工具不可用或会破坏交付时才提出替代，并说明迁移成本。

既有精确的普通 retained 路径在角色和位置不变时按当前契约 grandfather；版本库内部文件、控制器保留路径和工具管理的 transient 路径不借 grandfather 进入项目 ChangeSet。经定向检查确认已经存在的、非保留顶层目录，也可继续接收其真实工作流所需的新子文件，例如已有工具元数据或团队协作目录；这只延续一个已经存在的物理命名空间，不自动给新文件分配正式工件角色，也不授权建立另一个全新顶层目录。`.git`、`.hg`、`.svn`、`.codex`、`.agents` 新旧一律由项目 ChangeSet 拒绝；`.modeling` 只允许契约列出的 state authority，以及声明 `recovery_assessment` 事件时的 recovery 子树。版本库内部变更应通过相应 VCS 操作完成。新增顶层命名空间或整体迁移布局仍是独立变更，先列影响和回退，再取得用户批准。

## 判断是否真的需要工件

在创建项目路径前依次问：

1. 当前请求是否需要一个可复用、可交付或可跨步骤消费的持久结果；
2. 是否已有同目的、同消费者且仍当前的载体可更新；
3. 结果是否只是本轮短期计算，可放系统临时目录而不成为项目工件；
4. 若需要新工件，它的真实消费者、用途、生产者、生命周期和授权依据是什么；
5. 若它将成为正式工件，它明确选择哪个语义角色，路径与 class 是否同时匹配该角色；
6. 它是 working、milestone、frozen 还是 final，是否替代旧 identity；
7. 提升前要通过哪些与用途直接相关的验证。

无法回答消费者和用途时先不创建。不要用占位文件、空目录、默认 README、逐题 brief、冗余 manifest 或“以后也许用到”的报告替代设计。

## 一次 ChangeSet 的准入顺序

普通 G1 工作按整个 retained ChangeSet 处理，不为每个文件制造 proposal 文件、register/refresh 回执或执行账本。这里的路径准入只决定“能否在项目中落盘”，不在路径重叠时猜测或分配正式工件角色：

1. 汇总本次会新出现的全部路径；已有普通业务文件不重新分配 namespace/role，但 repository/controller 内部路径与 transient 路径仍先检查 allowlist，不能借 grandfather 绕过；
2. 为每个新路径在内存计划中写明目的、消费者和授权，并核对当前工件契约；
3. 用当前平台契约确认每个新路径至少命中一个 canonical semantic placement，或属于明确的 project support namespace，或位于已经存在的非保留顶层目录中；`paper/**`、`output/**` 同时与 visual placement 重叠是合法的，不要求 G1 全局唯一角色；
4. 排除重复用途、占位、推测性目录、脱离消费者的输出和范围外文件；
5. 在写入前一次性完成新路径 preflight；任一路径失败只阻断包含它的步骤；
6. 只有真正写入合格文件时才创建必要父目录链；
7. 生产后执行与用途相称的检查，并报告实际 ChangeSet 与结果。

ChangeSet、runtime `input_paths`/`output_paths` 和 `cwd` 使用 canonical relative POSIX 路径。除 `cwd` 可精确为 `.` 外，`./x`、`a//b`、反斜杠、绝对/盘符路径、`.`/`..` segment 和尾随斜杠都是非法 alias；先按 raw 是否等于 `PurePosixPath(raw).as_posix()` 阻断，再做冲突、包含关系或授权比较，不能让同一文件借两种文本拼写逃逸。

canonical spelling 仍不足以识别既有 symlink：例如 `paper-link/main.tex` 与 `paper/main.tex` 都是合法文本路径，却可能指向同一文件。因此只对当前计划已经声明的 ChangeSet 路径，以 `project_root / canonical_path` 的 `resolve(strict=False)` 结果作为第二层 physical conflict key；不扫描项目，也不逐文件登记。一个仍落在项目根内、且只被声明一次的 symlink 路径可以正常使用；同一步两个不同路径指向同一 target，或无依赖的两步写向同一 target，都必须阻断并同时报告路径与物理 target。显式依赖维持原有顺序写语义，指向项目外的 symlink 则仍由 containment 门直接拒绝。

fresh 顶层若不属于上述 namespace，`unknown_namespace` 只阻断包含它的 ChangeSet，并触发一次有范围、有影响说明和回退的人工作平台扩展决定；它不是“项目以后永远不能生成这种文件”。这是少见的架构边界，不是普通 G1 的逐文件门：只在实际 unknown path 所在 step 提供严格的 `facts.platform_extension`，逐字绑定当前 `plan.request` 中去除首尾空白后至少两个字符、且含非空白字符的人工批准原文，一次列出本 step 所需的唯一顶层 namespace，以及有实质内容的 purpose 与 rollback。一个 namespace 可以是 `logs` 这样的目录，也可以是 `setup.cfg` 这样的根文件；授权只覆盖同一步中首段精确相等的 unknown path。没有 unknown path 却携带 extension fact 会作为 stale/unused authorization 拒绝。reserved、transient 和 noncanonical path 永远不能靠 extension 绕过。获批扩展只增加已确认工作流所需的有界物理 namespace，不为路径问题凭空发明 semantic role。

若当前工具要求传入 artifact proposal，直接使用 `artifact-contract.json` 的当前 shape 临时构造并校验；不要复制字段清单到新文档，也不要仅为了留痕保存 proposal。

路径一旦进入 artifact proposal（包括工具明确要求登记的 working identity），或跨入 milestone、frozen、final 等正式身份边界，就必须显式选择一个 semantic `platform_role`，并用该角色自己的 path/class 约束验证。proposal path 本身仍须是 canonical POSIX 项目相对路径并在 resolve 后留在项目内；不得先用 `./`、重复分隔符、反斜杠或尾分隔符归一化，再把别名作为正式身份保留下来。`ART.ADMIT.CONSUMER`、`ART.ADMIT.PROPOSAL_FIELDS` 与 `ART.ADMIT.NO_SPECULATION` 只随真实声明的首次 `artifact_register` 激活；控制器不得因 ordinary G1 ChangeSet 中出现一个尚不存在的文件，就合成正式 proposal 义务。后续 `artifact_refresh` 与 `artifact_promotion` 分别沿用 `ART.REGISTER.IDENTITY` 与 `ART.PROMOTE.VALIDATE` 等专门控制，不重跑首次登记门。路径同时匹配其他角色不是冲突；真正需要澄清的是所选角色是否符合用途、消费者和职责。project support 文件和普通 working 文件不因通过 G1 路径准入而被冒充成正式工件。

## 从候选到正式 identity

候选、working、milestone/frozen 和 final 是不同身份，不靠复制、重命名或放进正式目录自动晋升。

建议顺序：

1. 在系统临时空间或现有工作流的 working 位置生成候选；
2. 核对实际输入、生产者、参数/版本、schema、单位、大小和内容；
3. 运行声明的用途验证，记录通过、失败和未验证边界；
4. 对将成为正式 identity 的实际文件重新计算路径、哈希和大小；
5. 确认消费者、替代关系和传播范围；
6. 只有真实跨越 milestone/frozen/final 边界时，按当前状态与工件契约提升和登记；
7. 让精确引用旧 identity 的消费者 stale，未引用变化 identity 的证据保持有效。

普通 working 文件不因每次保存而登记；新增正式 identity 不使生产者或消费者自动失效。已有正式 identity 发生变化时才按精确绑定传播。不要用整个组件 epoch 或全工作区 dirty 状态代替消费者关系。

## 路径设计的职责检查

准备正式选择契约角色时，再检查位置是否表达真实职责：

- 官方输入与原始附件保持只读和来源身份；
- 外部证据与项目自产结果分开；
- 规划/技术说明不冒充评审者可见稿件；
- 代码、机器结果、图件源和渲染件之间有生产者—消费者链；
- 交付 staging 不是工作权威，不能从交付副本反向更新结果；
- 控制状态只保存跨轮次当前事实，不承担项目正文或过程档案；
- Skill 支持内容不混入题目专用参数、结果和答案；
- 导航文件只指向权威材料，不成为证据或状态 owner。

这些是用契约选路后的检查问题，不是要求项目预先拥有所有角色或目录。

## 临时输出、缓存和构建中间物

- 短期探查默认使用系统临时目录；失败或放弃时不登记为项目结果。
- 现有工具必须在项目内产生缓存时，沿用其既有 ignore/clean 机制，并避免与正式路径重名。工具管理的缓存、编译中间物和未保留副作用不逐文件写进 retained ChangeSet，也不逐文件建立 proposal 或 identity。
- runtime action 的 `output_paths` 只列本步有意保留或交给下游消费的输出，不列解释器缓存、测试缓存、构建缓存等工具副作用。
- 需要人工比较的候选可以保留为 working，但必须有消费者和清晰状态，不能混入正式交付。
- 正式结果不得只存在于 stdout；一旦支撑下游或主张，选择适合结构的持久载体。
- 未保留的工具副作用由有界的工具命名空间与 ignore/clean 规则管理，不能直接支撑 claim 或 delivery。某个临时输出一旦要被保留、引用为证据或交给下游，必须在后续 ChangeSet 中按普通路径重新准入和验证；不能事后把整批缓存登记为合法。
- 运行意外生成了不属于已知工具副作用的持久路径时，先停止提升，盘点真实写入，再决定删除候选、补充合法准入或修改生产配置。

## 例外与人工复核点

以下情况需要人审或独立决定：

- 新建此前不存在的顶层命名空间，或迁移现有文件；
- 官方模板、现有工具链和平台契约发生真实冲突；
- 新工件会替换正式 identity、改变冻结决定或扩大交付范围；
- 正式 artifact proposal 所选角色与真实用途、消费者或 class 不一致，即使路径还能匹配另一个角色也不能借此绕过；
- 外部材料复制、隐私、许可或再分发边界不明确；
- 候选验证失败但业务方仍希望带条件晋升。

系统临时目录中的短期输出不作为项目工件；用户逐项要求附加文件时仍需合法角色、用途和消费者。不要把这些例外推广成自由命名或预建脚手架的许可。

## 常见失败与修复

| 失败 | 修复 |
|---|---|
| 初始化时铺满目录和模板 | 回到真实首个工件，只保留其父目录链 |
| 无视已有项目另建平行平台 | 定向盘点入口和消费者，沿用或提交独立迁移提案 |
| 把 G1 路径准入误解为已经分配正式角色 | 先按 namespace 准入；只在正式身份边界显式选择并验证一个 role/path/class |
| 普通首次创建仍偷偷选中 proposal/consumer atoms | 只在声明首次 artifact register 的步骤合成正式准入事件；普通 G1 仅做路径命名空间 preflight，refresh/promotion 使用各自专门控制 |
| 因 `paper/**` 或 `output/**` 同时匹配 visual 而阻断普通落盘 | 接受一个或多个 canonical placement；在正式 artifact proposal 中按真实职责选择角色 |
| 见到既有工具/协作目录便要求逐文件平台迁移 | 定向确认顶层目录确已存在且非保留，然后仅延续其真实工作流；新顶层仍单独审批 |
| 把人工平台扩展做成每个新文件的审批 | 只在 fresh unknown 顶层出现时一次批量绑定当前请求、用途和回退；普通 canonical/support/established 路径不读取该事实 |
| 用 `./x`、双斜杠或反斜杠制造同一路径的另一拼写 | 在任何比较前拒绝非 canonical POSIX raw path |
| 用两个合法 symlink/直达路径绕过 ChangeSet 冲突 | 对已声明路径追加 resolved physical key；同一步或无依赖步骤命中同一 target 即阻断 |
| 每次普通编辑都生成 proposal、receipt 和 registry 更新 | 合并为一个 G1 ChangeSet，只在正式身份边界登记 |
| 为将来可能需要创建报告或 manifest | 删除推测性载体；等真实消费者出现再准入 |
| 工具链来自 Skill 个人偏好 | 核对现有可用工具和官方/用户要求，说明替换依据 |
| 把 scratch 复制到正式目录当作提升 | 回到原始输入与生产者，执行声明验证并登记实际 identity |
| 登记不存在、空文件或旧哈希 | 从实际文件重算身份，失败则保持 working/blocked |
| 新 identity 使全项目失效 | 只传播到精确引用旧 identity 的真实消费者 |
| 运行产生额外未声明文件 | 暂停晋升，盘点真实写入并修正 ChangeSet 或生产配置 |
| 把缓存逐个写入 ChangeSet 或 runtime `output_paths` | 从 retained 输出中排除工具副作用；若后续要消费，再以新 ChangeSet 晋升 |
| 交付副本被当作当前工作权威 | 回到生产链 owner，重新构建或同步 staging |

## 来源保留说明

本包保留 V1–V7 经 V8 `01-contest-project-pattern.md` 冻结的目录职责、工具链适配、生产者—消费者和候选/正式边界，但把当年的固定树降为职责线索；保留 V9 `modules/project-platform.md` 的逻辑平台与 lazy artifact 边界；以 V10 的 `ART-LAZY-001`、`ART-PROMOTE-001` 和 `PRJ-STRUCTURE-001` atoms 为规范锚点。V11 只保住物理懒创建的历史缺口由 V12 `project-platform-contract.json` 的统一角色/路径恢复修复，V13–V14 延续其语义，并加入 ChangeSet、精确 identity 与比例性运行边界。V15.0.1 修复了把“G1 物理落盘”与“正式语义角色”错误合并为路径唯一推断的问题：保留逻辑职责与人工正式准入，同时把普通路径准入降为命名空间边界。已明确不恢复固定目录树、空脚手架、逐文件持久回执、默认五件套或全工作区登记。
