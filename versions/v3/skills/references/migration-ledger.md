# V1/V2 → V3 迁移台账

本台账按“可独立触发和判定的规则族”迁移。活动规则使用稳定 ID；历史文件保存原始措辞、
例子和来源，不再独立决定是否执行。若历史细节揭示活动规则没有覆盖的独立义务，必须
重新打开本台账。

## 来源模块处置

| 来源模块 | V3 活动 owner | 处置 | 保留在历史层的内容 |
|---|---|---|---|
| `01-contest-project-pattern` | K-01—K-05、L-01—L-03、E-02、H-01 | active | 工程示例与旧目录措辞 |
| `02-latex-setup` | V-01—V-06、V-10—V-12 | active | 具体 LaTeX 示例 |
| `03-paper-content-rules` | M-01—M-12、F-*、B-*、A-*、S-*、C-* | active | 长例、反例和历史演化 |
| `04-figure-generator` | V-07—V-09、M-05、E-01 | active | 绘图实现示例 |
| `05-audit-protocol` | K-02、K-03、K-07、M-*、S-*、V-*、E-* | active | 审计命令示例和扩展检查表 |
| `06-weiwei-norms` | M-*、F-*、B-*、A-*、S-*、C-*、V-* | classified | D/E 级来源观察只作参考 |
| `07-algorithm-reference` | L-03、L-04、S-06 | classified | 算法族介绍，不作选模权威 |
| `08-literature-search` | L-04、E-03 | active | 检索式示例 |
| `09-robustness-checker` | S-09、E-01 | active | 风险类型示例 |
| `10-json-handoff` | E-02、H-03、H-04 | active | JSON 模板细节 |
| `11-paper-finalizer` | K-02、V-*、H-02—H-05 | active | 打包命令示例 |
| `12-source-audit-and-provenance` | E-03、E-04、H-01、H-05 | active | 来源调查记录 |
| `13-excellent-paper-expression` | M-*、B-03、S-06、S-08、C-03 | classified | 优秀论文观察和拒绝点 |
| `14-session-handoff` | K-02、L-01、L-07、H-03—H-05 | active | 检查点脚本说明 |
| `15-pipeline-methodology` | K-03—K-05、L-02—L-07 | active | 十阶段认知地图解释 |
| `16-data-audit-methodology` | K-03、L-03、E-01—E-02、V-07—V-09 | active | 数据题型示例 |
| `17-reader-first-manuscript-audit` | K-07、M-*、F-*、B-*、S-*、C-* | active | 审计表扩展示例 |
| `legacy-SKILL` | K-*、路由矩阵、L-*、H-* | superseded | V1 完整编排历史 |

`classified` 表示其中 A/B/C 级可执行义务已经迁入相应 owner，D/E 级观察留在历史层；
不是待办状态。`superseded` 表示整体入口已被 V3 取代，但原文仍可追溯。

## 关键缺口修复

| V2 暴露的缺口 | V3 owner | 关闭依据 |
|---|---|---|
| 活动入口没有人工理解门 | K-04、L-05 | 明确区分理解、模型、参数、实现和论文批准 |
| 没有逐问子阶段硬门 | K-05、L-03 | 十二项职能、关闭证据和越级禁止 |
| 文献导向可被自由跳过 | L-04、R-03 | 触发检查与有证据免检 |
| 缺少执行证明 | R-01—R-05 | 开始、跳过、结束回执 |
| 来源档案承担活动规则 | 入口、ownership map | 活动 owner 与历史层分离 |
| 候选成果永久留在后台 | L-06 | 验证后按信息增量重新准入 |
| 正确代码被误当完整论文 | K-07、S-01、S-06、S-10 | 每问评审可见完整链 |
| 唯一归属导致触发次数不足 | routing matrix | 入口重复触发，不复制规则正文 |

## 重新打开条件

出现以下任一情况时，迁移重新标记为不完整：

1. 活动规则标题缺少或重复稳定 ID；
2. 新增历史来源模块但没有处置行；
3. 历史规则能构造活动规则无法阻止的真实失败案例；
4. 活动 owner 删除语义但没有迁移记录；
5. 已知回归案例能够绕过路由或回执；
6. 用户拒绝某项合并、降级或删除判断。

运行 `scripts/validate_skill_v3.py --require-complete-migration` 检查结构完整性，并
运行 `scripts/test_skill_regressions.py` 检查已知失败模式。脚本通过只证明登记、路由
和已知回归覆盖闭合；真实任务的前向测试仍负责检验行为是否可靠。
