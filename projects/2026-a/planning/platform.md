# 项目平台

## 平台职责与依据

平台服务于题面“药材的烘干问题”的四问求解：从原始资料、题意与数据审阅、模型选择、实现和验证，形成论文及规定的结果工作簿。本文件说明目录职责、生产关系和复现入口；当前阶段、人工决定和下一动作只在[项目状态](../.modeling/state.json)保存，不在导航文件中维护第二份状态表。

规范依据为[项目平台契约](../skills/references/project-platform-contract.json)及[平台与工件能力包](../skills/references/capability-packets/project/platform-and-artifacts.md)。skill要求按实际职责使用目录、在实际产物出现时创建父目录，不要求预先搭齐空目录。已有官方输入保持原位，属于既有项目位置的保留规则。

## 输入与职责

| 路径 | 作用与消费者 |
|---|---|
| `A题.pdf` | 四问题意、参数公式和输出要求的原始依据 |
| `附件/附件1.xlsx` | 烘房温度、水分浓度随时间变化；四问环境条件的来源 |
| `附件/附件2.xlsx` | 药材半径随时间变化；问题4的几何数据来源 |
| `附件/附件3/result1.xlsx` 至 `result4.xlsx` | 四问结果模板，供后续导出程序读取结构 |
| `skills/` | 用户提供的跨项目控制器，不存放本题模型和结果 |
| `planning/input_inventory.json` | 官方输入的工作快照，供平台检查和后续数据审阅使用 |
| `.modeling/state.json` | 当前组件、依赖、待决问题和下一动作的唯一权威 |
| `scripts/project.ps1`、`scripts/inspect_inputs.py` | 平台操作、输入身份检查及只读状态展示 |
| `scripts/plot_inputs.py` | 当前输入诊断的工作生成器，属于允许的项目支持路径 |
| `planning/Q1/` | 问题1定义、输出要求、验证计划和候选分析 |
| `planning/Q2/` | 问题2定义、附录3核验、验证计划，以及变物性模型和长期边界候选 |
| `planning/ENV/data_audit.md` | 附件1全量结构及数值审计 |
| `planning/input_visual_review.md` | 输入图表的观察、解释与复核记录 |
| `planning/model_explanation_corrections.md` | 原运行规格的定位勘误及当前解释，供四问工作文稿和历史规格联读 |
| `references/Q1/` | 外部方法来源、药材领域原始研究及阅读边界 |
| `output/diagnostics/` | 输入诊断图、可复核数值及本轮内部审视数据；不是官方提交工作簿 |

原始文件保持原位置，不复制为另一套“原始数据”。输入快照仅证明所读文件的身份与表结构，不表示数据验收通过，也不是全项目恢复基线。

后续出现实际产物时按项目 skill 使用 `src/<task-id>/` 存代码、`src/_utils/` 存共用工具、`output/<task-id>/` 存机器结果、`docs/<task-id>/solution_brief.md` 存完整队友讲解稿、`paper/` 存论文、`delivery/` 存获准交付包。这些目录不提前建空壳。正式结果不得覆盖 `附件/` 中的模板。

`scripts/**`是契约明确允许的项目支持命名空间；普通工作生成器不因位于此处就违规。若它将成为正式登记的模型源码，则按正式`code`角色统一放到`src/**`并同步消费者。`output/diagnostics/**`保存输入诊断及内部对账数据，无需拆成多个重复目录。本轮题意、数理及输出复核见[全项目审视报告](full_project_review.md)，不代替状态中的正式接受。四问讲解稿已直接修正；历史冻结规格与选择记录保留原字节，须联读[模型解释修订说明](model_explanation_corrections.md)，以区别计算身份和后来澄清的文字。

## 平台核对与整理结果（2026-09-10）

本次针对平台职责与阶段展示检查，未发现现有业务路径的硬性准入违例，也未发现已登记工件的角色与路径冲突。实际修正的是入口与说明：补齐已有分析、图表和文献链接，更新公式核对范围，并让状态命令只展示当前待决项，避免把历史已解决事项再次显示为待确认。

原题、附件、已有成果及skill均保留原位；没有复制第二套原始输入，也没有添加空目录。`.venv/`、`.cache/`由运行环境和忽略规则管理，不作为研究结果或正式工件登记。普通工作文件与正式接受分开：后者须有skill要求的当前证据和相应接受过程，不能由目录名称或文件数量代替。

## 已有产物的生产与阅读关系

| 生产依据 | 工作产物 | 直接消费者 |
|---|---|---|
| 原始题面、附件及模板 | `planning/input_inventory.json` | 输入身份检查、后续数据审阅 |
| 题面问题1与附录2、result1模板 | `planning/Q1/problem_definition.md` | 候选比较、之后的模型规格及输出核对 |
| 附件1逐点读取 | `planning/ENV/data_audit.md` | 环境接口选择与Q1建模 |
| 附件1/2 → `scripts/plot_inputs.py` | `output/diagnostics/*` | `planning/input_visual_review.md`、候选分析、用户审阅 |
| 外部原始研究和基础方法资料 | `references/Q1/*.md` | 方法适用性与题内解释 |
| 题意、数据审计、图形与来源 | `planning/Q1/model_candidates.md` | 人工选模及之后的数学规格 |
| 问题2、附录3、原始环境与result2模板 | `planning/Q2/problem_definition.md` | Q2候选、规格和输出核对 |
| Q2定义、环境后段统计、领域方法资料 | `planning/Q2/model_candidates.md` | 本问选模、长期输入与完整输出范围决定 |

## 四问工作关联

| 组件 | 依据与工作目标 | 输入关系 | 后续应取得的证据和产物 |
|---|---|---|---|
| ENV | 附件1，环境时间序列 | 原始工作簿 | 单位、时间轴与后段边界解释，供四问共用 |
| GEOMETRY | 附件2，收缩半径时间序列 | 原始工作簿 | 单位、插值与定义域说明，供Q4使用 |
| Q1 | 题面问题1和附录2，预热平衡模型 | ENV | 温度及水分分布、独立验证、表1–2、result1.xlsx |
| Q2 | 问题2和附录3，整个烘干过程模型 | ENV | 变物性模型及验证、3小时摘要表3–4、result2.xlsx |
| Q3 | 问题3，确定各处水分浓度均低于0.15的时刻 | Q2 | 全域终止判据及时间精度验证、表5、result3.xlsx |
| Q4 | 问题4和附录4，考虑尺寸变化 | ENV、GEOMETRY | 收缩域模型及验证、表6、result4.xlsx |

Q1可以为Q2提供实现经验，但当前不把Q1数值结果设为Q2的必要输入；Q4也不依赖Q3计算出的结束时刻。上述为初始化关联，具体代码复用产生实际消费者时再补充精确依赖。

## 已核对的格式要求

- 题面共4页。附件1有241条数据，时间0–14400 s；附件2有145条数据，时间0–259200 s。
- Q1：输出1–1800 s，步长1 s；固定半径0–2 cm，间隔0.1 cm。论文摘要时刻为100、300、600、900、1200、1500、1800 s。
- Q2：论文摘要为0.5、1、1.5、2、2.5、3 h；result2为1～10800 s、时间间隔1 s、空间间隔0.1 cm的双场结果。全程适用模型在Q2说明，全程干燥时长及分钟水分表在Q3呈现。
- Q3、Q4：完整水分结果时间间隔60 s、空间间隔0.1 cm，论文每6 h并包含烘干结束时间。
- result1和result2包含“温度”“水分浓度”两张表；result3和result4为“Sheet1”。A列是秒，第1行是厘米；result4最后一列表头是“药材表面”。
- 所有结果保留四位小数；计算过程保留足够精度，展示与导出时再处理。
- 模板仅有5行6列且包含省略号，须按题面展开，不能把模板当前尺寸当作完整输出尺寸。

问题1及附录2的分式指数已对照原PDF视觉核对，定位与参数见[问题1定义](Q1/problem_definition.md)。问题2及附录3也已逐式视觉核验，定位、温标和从t=0统一使用附录3的解释见[问题2定义](Q2/problem_definition.md)。这不代替问题3、4各自的任务分析或验证。摄氏温度与含温度扩散公式中的开尔文温度须按对应附录处理。

## 使用与环境重建

使用Windows、Python 3.12项目虚拟环境。依赖实际安装版本及间接依赖固定在根目录 `requirements.txt`。NumPy/SciPy用于数值计算，pandas/openpyxl用于数据读取，Matplotlib用于科学图表，pypdf用于题面提取，jsonschema供项目控制器使用。

```powershell
.\scripts\project.ps1 doctor
.\scripts\project.ps1 inputs
.\scripts\project.ps1 status
```

以上分别检查依赖导入、原始输入身份与结构、显示当前状态，不执行模型或更新状态。从任意工作目录调用此脚本均会定位项目根目录。

输入诊断图复现入口为：

```powershell
.\.venv\Scripts\python.exe -B scripts/plot_inputs.py
```

该命令由附件1/2重建`output/diagnostics/`的两张图及数值记录。图表已做过工作层面的数值和视觉检查；若选入论文，还需核对实际嵌入页面。它不运行四问求解，也不改变正式接受状态。

若迁移计算机，在新项目根目录使用本机Python 3.12路径重建环境（不要复制旧 `.venv`）：

```powershell
uv --cache-dir .cache/uv venv --python '本机Python3.12的完整路径' .venv
uv --cache-dir .cache/uv pip install --python .venv/Scripts/python.exe -r requirements.txt
```

仅在确认官方资料有意更新后，才用 `.venv/Scripts/python.exe -B scripts/inspect_inputs.py inputs --save-inventory` 更新工作快照。它不接受数据处理决定，也不刷新正式工件身份。

项目状态通过 `skills/scripts/state_manager.py` 管理。日常平台检查不调用求解器或skill全包测试；正式状态迁移、模型运行和证据接受遵循项目skill。论文工具链待实际写作要求明确后选择，未假设已具备官方论文格式文件。
