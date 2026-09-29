# 数学建模项目控制器 · Skill 与实战项目集

一套用于数学建模竞赛与研究项目的**人机协作 Skill 规则包**，加上四次完整竞赛项目的实践记录。

规则不是一次写成的：它从 V2 的一份规则清单出发，经过 17 个版本、每轮项目结束后的复盘逐步长成
现在的 V16.2，每次取舍、失败与回退都留在 `versions/` 里；过程中也综合了几套公开工作流范式
（来源见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)）。

四个项目实践（2021 B / 2024 B / 2025 A / 2026 A）各对应一档版本，且都留有权威项目状态
（`.modeling/state.json`）——即真正在长周期、真实返工的项目里跑完了状态机，而不只是套用了目录结构。

## 仓库内容

| 路径 | 内容 | 规模 |
|---|---|---|
| [`skills/`](skills/) | **主技能**：数学建模项目控制器 V16.2.0（stable，2026-09-13 冻结） | 119 文件 / 5.9 MB |
| [`versions/`](versions/) | V2 → V16.2 的 17 个版本，含各版本发布元数据与 V16.2 冻结记录 | 1490 文件 / 50 MB |
| [`legacy/bootstrap/`](legacy/bootstrap/) | V1 主线 `math-modeling-project-bootstrap`，V4 起由 controller 取代 | 86 文件 / 1 MB |
| [`projects/`](projects/) | 四次竞赛项目实践（2021 B / 2024 B / 2025 A / 2026 A） | 1800 文件 / 151 MB |
| [`projects/registry.json`](projects/registry.json) | 本机 17 个同源项目的登记表（版本、问题、规模、状态） | — |
| [`docs/`](docs/) | [版本阅读指南](docs/VERSIONS.md)、[项目盘点](docs/PROJECT-INVENTORY.md) | — |

## 技能：数学建模项目控制器

- 入口 [`skills/SKILL.md`](skills/SKILL.md)，发布状态 [`skills/evals/release/release-state.json`](skills/evals/release/release-state.json)
- 组成：`rules/*.json`（原子规则）、`references/`（方法包、契约与谱系）、`scripts/`（路由、状态、恢复、校验）、`evals/`（发布门与回归用例）
- 版本经验与未修事项：[v16-2-cumcm2026-lessons.md](skills/references/preservation/v16-2-cumcm2026-lessons.md)

核心主张是把"每一步都上锁的流水线"换成分级的**最小一致性闭包**：只有动作真实跨越边界时才升强度
（G0 建议 / G1 工作 / G2 检查点 / G3 发布），日常修改不写回执、不铺状态，正式声明必须有类型化证据。
规则只由真实动作触发，Skill 自身的维护必须获得显式授权。

## 版本谱系

V2 的单一规则清单 → V4 的规则分域 → V10 的能力双层与工作检查点 → V15 的平台准入与发布门 →
V16 的兼容变更闭包与恢复合同 → V16.2 的稳定发布。每一步的取舍都保留原文，包括失败与回退记录。

各版本目录的内层结构并不统一（V10 及以后为 `<版本>/skills/...`，早期版本把技能树直接放在版本
根目录），完整说明见 [`docs/VERSIONS.md`](docs/VERSIONS.md)。

## 项目实践

每个项目一个子目录，均保留 `planning/ src/ output/ paper/ docs/` 的完整链路：

| 项目 | 技能版本 | 研究问题 | 规模 |
|---|---|---|---|
| [`projects/2021-b/`](projects/2021-b/) | V1 | 催化剂组合与温度关系（四问） | 482 文件 / 24 MB |
| [`projects/2024-b/`](projects/2024-b/) | V11 | 2024 国赛 B 题（Q1–Q4） | 276 文件 / 8 MB |
| [`projects/2025-a/`](projects/2025-a/) | V16.0 | 2025 国赛 A 题（Q1–Q5） | 355 文件 / 22 MB |
| [`projects/2026-a/`](projects/2026-a/) | V16.1 | 2026 国赛 A 题（ENV/GEOMETRY + Q1–Q4） | 705 文件 / 100 MB |

四个项目各覆盖一档版本，另 13 个同源项目（2011 B、2022 A、集训第六题等）登记在
[`projects/registry.json`](projects/registry.json) 与 [`docs/PROJECT-INVENTORY.md`](docs/PROJECT-INVENTORY.md)，
可按版本查阅每个项目用了哪一代规则。

## 怎么用

**当技能包安装。** 把 `skills/` 放进宿主工具的 skill 发现路径（例如 `~/.agents/skills/<name>/`），
入口是 `SKILL.md`。技能按渐进披露设计：路由先选中短方法路由，再按需完整读取 1–3 个能力包，
不常驻加载全部资料。

**当项目模板。** 照 `projects/2021-b/` 的目录约定（`planning/ src/ output/ docs/ paper/`）起步，
用 `skills/scripts/bootstrap_project.py` 初始化，用 `skills/scripts/state_manager.py` 维护跨轮次
状态与恢复检查点。

**当规则来源。** `skills/rules/*.json` 的原子规则带适用条件、强度（A/B/C/D/E）、规范 effect 与
验收边界，可单独抽出来做检查清单；`skills/references/` 的方法包是可读的实施程序，不是强制条款。

## 关于内容的说明

- 项目中的验证计数（如数据审计 23/23、第一问 19/19）是**项目当时的运行记录**；本次整理未重新
  运行全部计算，请按"可复现证据"理解，而不是"本次已复核"。
- 技能保留三处已知未修的控制面问题，见 v16.2 经验文件；"检查通过"不等于问题已修复，也不保证
  适用任何具体赛事、评分标准或未来题目。
- 各项目的论文与规划记录按当时的真实过程保留，未作事后修饰。

## 许可

- 代码（`**/*.py`）与脚本化配置：**MIT**，见 [`LICENSE`](LICENSE)。
- 文档、规则、方法包与论文文本：**CC BY 4.0**，见 [`LICENSES/CC-BY-4.0.txt`](LICENSES/CC-BY-4.0.txt)。
- 题目原文、附件与评阅要点等官方材料的著作权归全国大学生数学建模竞赛组织方；引用与再分发
  边界见 [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)。
