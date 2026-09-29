# 稿件能力路由（非规范性）

本文件只选择完整能力包；`rules/manuscript.json` 拥有结构、内容、读者、验收、局部编辑和写作 profile 的规范效果。不要用本路由建立固定章节模板，也不要只凭 atom gloss 起草或验收论文。

## draft

- 新稿、结构性重写、章节职责或逐问回答链：完整读取 [论文结构与章节职责合同](capability-packets/manuscript/structure-and-section-contracts.md)。
- 摘要、方法、结果、评价、结论、术语、公式或实质论证：完整读取 [论文表达与论证闭合](capability-packets/manuscript/expression-and-argument.md)。
- 任务同时涉及结构与实质文字时两个包都读；只调整不改变结构责任的一段论证时不预载结构包。
- 当前项目使用 LaTeX 且修改会改变页面时，在内容闭合后读取 [LaTeX、渲染与终稿收口](capability-packets/manuscript/latex-and-finalization.md) 的相应范围。

## reader-audit

章节或全文审计、首次阅读可懂性、稿件完成声称，完整读取 [读者审计与局部修改](capability-packets/manuscript/reader-audit-and-local-edit.md)。它先确定真实审计范围，再按首次阅读、逐问证据与跨载体 identity 检查；发现结构或论证缺陷时，定向回读相应建设包，不以验收清单代替修复方法。

## local-edit

错字、句法、段落润色、术语/数字/主张的局部变化或已发布稿重开后修改，完整读取 [读者审计与局部修改](capability-packets/manuscript/reader-audit-and-local-edit.md) 的局部程序。实质表达变化同时读取 [论文表达与论证闭合](capability-packets/manuscript/expression-and-argument.md)；纯错字且语义不变时不加载全文结构和终稿包。A3 重开权限仍由控制器决定。

局部修改会改变实际 LaTeX 页面时，在内容闭合后完整读取 [LaTeX、渲染与终稿收口](capability-packets/manuscript/latex-and-finalization.md) 的局部构建、日志与受影响页面程序；这不把局部修改升级为全文审计或正式发布。

## render

LaTeX 建设、字体、编译、分页、局部版面或终稿 PDF，完整读取 [LaTeX、渲染与终稿收口](capability-packets/manuscript/latex-and-finalization.md)，并按实际图表范围读取视觉渲染审计包。源完整、构建成功、渲染通过和正式就绪是四个不同结论。

## 完整性边界

选中的包完整读取。整稿候选通常按“结构—论证—读者审计—渲染—交付”分阶段；局部任务只读取其真实闭包。阶段间携带当前稿件 identity、已确认语义、主张/结果引用、未决缺口和下一能力包，不能把四包摘要成一个通用稿件 checklist。
