# 现行 Markdown 权威整理审计

## 触发原因

统一 LaTeX 草稿已经完成，但多个 Markdown 导航仍记录“第二问尚未开始、Markdown 是
正文入口、LaTeX 尚未建立”等旧状态。若不整理，队友或新会话会从错误断点继续工作。

## 处理原则

- 只修改当前权威、导航和读者说明。
- 历史交互日志、工作日志和日期审计保持原样，不把过去状态改写成从未发生。
- 已失去当前职责的 Markdown 正文移入可恢复归档，不删除。
- 技术文档保留复现所需的标准术语，同时补充与正文普通表述的对应关系。

## 已完成工作

- 重写根目录 `README.md` 和 `HANDOFF.md`，将当前状态统一为第一、二问完成、第三问
  待独立设计、统一 LaTeX 草稿 13 页。
- 更新 `planning/task_matrix.md`、`planning/project_plan.md` 和 `planning/README.md`。
- 将 `paper/drafts/` 中旧 Markdown 正文和阶段说明移至
  `paper/archive/2026-07-29_markdown_manuscript/`，并增加归档说明。
- 更新 `paper/`、`docs/`、`src/`、`output/` 的导航 README。
- 重写队友同步说明，使其覆盖第一、二问当前结果和第三问入口。
- 修正第一问报告中的现行术语；为第二问代码和输出 README 增加技术术语—普通语言
  对照。

## 检查结果

- 当前权威和导航中不再出现旧 Markdown 正文路径、第二问待选模、LaTeX 尚未建立、
  旧页数或“下一步进入第二问”等失效状态。
- 项目 Markdown 未发现 LaTeX 章节、环境、引用或数学定界语法混用；`~$附件1.xlsx`
  中的美元符号是 Excel 临时锁文件名，不是数学定界符。
- 历史日志中仍可见旧路径和当时决策，属于预期的时间记录。

## 当前入口

- 项目总览：`README.md`
- 跨会话恢复：`HANDOFF.md`
- 四问状态：`planning/task_matrix.md`
- 当前草稿：`paper/draft/manuscript_draft.tex`
- 队友说明：`docs/team_sync/README.md`
