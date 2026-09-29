# A题：药材的烘干问题


本项目使用随项目提供的[数学建模项目 skill](skills/SKILL.md)。本页是阅读入口；阶段、决定和下一动作由[项目状态](.modeling/state.json)统一记录。

## 从这里阅读

| 要了解什么 | 阅读入口 |
|---|---|
| 完整交付队友（本轮统一入口） | [队友交付包阅读入口](<未收录-队友交付包_20260913>/00_从这里开始.html)、[完整压缩包](<未收录-队友交付包_20260913>.zip)：四问讲解与源稿、初稿修改清单、8幅图、四份结果、计算与绘图代码及数据、文献与新版附录、队伍锁定AI报告；先整体解压再打开阅读入口 |
| 四问讲解稿打包阅读 | [四问HTML讲解稿](output/teammate_briefs/队友讲解稿_四问.zip)：四问按各自问题重组论证与检验；主算法在Q1解释，后问复用并展开新增关系，8幅图随文内嵌 |
| 队伍确认的AI使用报告 | [AI工具使用详情](docs/<未收录-AI工具使用详情>.pdf)：队伍共同商讨提供，包含队友使用信息；只原样使用整合，不修改。材料包中的同名PDF与此文件逐字节一致 |
| 论文附录与支撑材料 | [本轮附录与文献入口](<未收录-队友交付包_20260913>/05_文献与附录/阅读说明.html)、[新版附录PDF](<未收录-队友交付包_20260913>/05_文献与附录/附录.pdf)：可编辑LaTeX随包提供，程序中已补入四情境对照入口；旧submission_appendix合稿素材保留为历史版本，本轮交付从上述统一入口取用 |
| 队友上传的稿件与意见 | [队友意见](<未收录-队友材料>/)：固定接收队友原稿、修改稿及反馈，按当次请求审阅；保留队友原文件，论文取舍由队伍决定 |
| 论文需要哪些图、怎样绘制 | [配图方案与绘制规范](planning/paper_figure_plan.md)：逐图信息职责、数据来源、分问范围及官方要求与团队建议 |
| 已绘制的论文图件 | [当前图件索引](output/paper_figures/current/index.md)、[当前A4图册](output/paper_figures/current/figure_catalog.pdf)、[当前图件打包](output/paper_figures/current/论文图件_当前选用.zip)：由四问讲解稿实际引用同步生成；旧v1图册仅作历史留档 |
| 本轮新增与改绘 | [圆环空间离散](output/paper_figures/structural_rebuild_20260912/fig01_annular_control_volumes.png)、[扩散系数正负贡献](output/paper_figures/structural_rebuild_20260912/fig09_q2_diffusivity_decomposition.png)、[径向达标进程](output/paper_figures/structural_rebuild_20260912/fig05_q3_completion_progress.png)；检验对照以邻近小表解释 |
| 全项目重新复核的结论与限制 | [题意、数理与结果复核](planning/full_project_review.md)：逐句题意解释、数理核对及修正结果 |
| 如何联读原运行规格与当前解释 | [模型解释修订说明](planning/model_explanation_corrections.md)：共同条件、分问职责、推导勘误与原版本身份 |
| 问题1的完整解题思路 | [队友讲解稿](docs/Q1/solution_brief.md)：第5.4—5.5节说明初始通量、首步计算及图1-2交点网格；第7.2节图1-3含五个时刻；[单文件HTML阅读版](output/teammate_briefs/问题1_队友讲解稿.html)内嵌全部配图 |
| 问题1的计算结果 | [题目要求的result1.xlsx](output/Q1/result1.xlsx)、[图1-3五时刻径向剖面](output/paper_figures/reading/fig03_q1_profiles_d98d193909de.png) |
| 结果是否算得可靠 | [独立验证说明](docs/Q1/verification_note.md)、[数值验证报告](output/Q1/verification_report.json)、[表格核验](output/Q1/workbook_audit.json) |
| 附件有哪些信息 | [原始数据图表与解读](planning/input_visual_review.md)：环境变化、半径收缩、诊断边界 |
| 问题1要算什么 | [问题定义与输出要求](planning/Q1/problem_definition.md) |
| 问题1采用什么方法 | [已确认的模型比较](planning/Q1/model_candidates.md)与[数学数值规格](planning/Q1/model_spec.md) |
| 问题2的完整解题思路 | [队友讲解稿](docs/Q2/solution_brief.md)：局部耦合模型、固定网格证明及前三小时结果 |
| 问题2的计算结果 | [前三小时result2.xlsx](output/Q2/result2.xlsx)、[前三小时时空分布图](output/paper_figures/redesign_v3/fig04_q2_fields_sample.png) |
| 问题2的验证证据 | [独立验证与复算说明](docs/Q2/verification_note.md)、[实现与数值检验](output/Q2/verification_implementation.json)、[结构与敏感性检验](output/Q2/verification_structure.json)、[前三小时独立检查](output/Q2/submission_verification.json)、[工作簿核验](output/Q2/workbook_audit.json) |
| 问题2要算什么、有哪些新选择 | [题意、附录3与验证计划](planning/Q2/problem_definition.md)、[模型及长期边界候选比较](planning/Q2/model_candidates.md) |
| 问题2采用的主方案及范围 | [选择说明](planning/Q2/selection_rationale.md)、[数学数值规格及存在唯一性证明](planning/Q2/model_spec.md)、[当前官方输出范围补充](planning/Q2/output_scope_revision.md) |
| 问题3的完整解题思路 | [队友讲解稿](docs/Q3/solution_brief.md)：完整干燥过程、全域停止判据与表5 |
| 问题3的提交与核验 | [result3.xlsx](output/Q3/result3.xlsx)、[径向达标进程图](output/paper_figures/structural_rebuild_20260912/fig05_q3_completion_progress.png)、[逐格独立核验](output/Q3/workbook_audit.json) |
| 问题4的完整解题思路 | [队友讲解稿](docs/Q4/solution_brief.md)：实测收缩、附录4物性、固定位置与实际表面、表6及检验 |
| 问题4的提交与核验 | [result4.xlsx](output/Q4/result4.xlsx)、[同尺度含水率截面](output/paper_figures/redesign_v3/fig07_q4_sections_sample.png)、[逐格独立核验](output/Q4/workbook_audit.json) |
| 本次论文规范反馈 | [已有规范、遗漏职责及后续迭代归属记录](planning/writing_requirements_review.md) |
| 方法有哪些领域依据 | [药材领域原始研究](references/Q1/domain_research.md)、[队友两篇论文的评阅](references/Q1/teammate_papers_review.md)及[基础方法来源](references/Q1/method_sources.md) |
| 环境数据是否读对 | [附件1全量审计](planning/ENV/data_audit.md)及[输入身份快照](planning/input_inventory.json) |
| 文件怎么组织、如何复现 | [平台职责与四问资料索引](planning/platform.md) |
| 本机绘图工具怎样调用 | [绘图工具入口](planning/graphics_toolchain.md)：Inkscape 便携版矢量导出、已有 Three.js 三维渲染及统一调用配置；供内部制作使用 |
| 官方要求是什么 | [原始题面](A题.pdf)、[原始附件与模板](附件/) |

上述分析和图表供当前工作与审阅使用；文件存在不等于模型、数据接口或结果已正式接受。

我方队友讲解稿只维护docs/Q1—Q4中的Markdown源稿和output/teammate_briefs中的HTML阅读版；阅读压缩包只含四份HTML。队友意见中的DOCX、PDF是队友提供的输入原稿，不作为我方讲解稿的导出格式。独立图件PDF及其他专门要求的PDF文件按各自用途保留。

四问讲解稿已直接纳入本轮解释修正。绑定历史运行的规格及选择记录保留原字节，阅读时联读上述修订说明；旧运行与验证身份不被文字清稿改写。

## 查看状态与检查输入

在项目根目录的 PowerShell 中运行：

```powershell
.\scripts\project.ps1 doctor
.\scripts\project.ps1 inputs
.\scripts\project.ps1 status
```

无需激活环境。入口自动使用本项目 `.venv`，不会启动求解或重算结果。环境重建方法见平台说明。
