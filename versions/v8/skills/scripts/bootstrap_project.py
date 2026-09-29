#!/usr/bin/env python3
"""Create a non-overwriting mathematical-modeling project skeleton."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path


STANDARD_DIRS = (
    "data",
    "references",
    "references/notes",
    "references/refs",
    "planning",
    "planning/analysis",
    "planning/audits",
    "planning/archive",
    "src",
    "src/_utils",
    "output",
    "docs",
    "paper",
    "paper/figures",
)

EXCLUDED_TOP_LEVEL = {
    ".git",
    ".obsidian",
    "__pycache__",
    "data",
    "docs",
    "output",
    "paper",
    "planning",
    "references",
    "skills",
    "src",
    "README.md",
    "project_state.json",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.name in EXCLUDED_TOP_LEVEL or child.name.startswith("."):
            continue
        if child.is_file():
            files.append(child)
        elif child.is_dir():
            files.extend(
                path
                for path in sorted(child.rglob("*"))
                if path.is_file() and "__pycache__" not in path.parts
            )
    return files


def write_if_missing(path: Path, content: str, created: list[str], skipped: list[str]) -> None:
    if path.exists():
        skipped.append(path.as_posix())
        return
    path.write_text(content, encoding="utf-8")
    created.append(path.as_posix())


def build_inventory(root: Path, files: list[Path]) -> str:
    lines = [
        "# 原始资料清单",
        "",
        f"- 建立日期：{date.today().isoformat()}",
        "- 状态：待逐文件阅读与人工确认",
        "- 原则：本表只登记文件事实，不根据文件名推断题目要求。",
        "",
        "| 相对路径 | 字节数 | SHA-256 | 初步类型 | 阅读状态 | 处理决定 |",
        "|---|---:|---|---|---|---|",
    ]
    for path in files:
        relative = path.relative_to(root).as_posix()
        suffix = path.suffix.lower().lstrip(".") or "无扩展名"
        lines.append(
            f"| `{relative}` | {path.stat().st_size} | `{sha256(path)}` | "
            f"{suffix} | 未读 | 待定 |"
        )
    if not files:
        lines.append("| — | 0 | — | 未发现原题文件 | 阻塞 | 请补充原始资料 |")
    lines.extend(
        [
            "",
            "## 下一步",
            "",
            "逐文件提取正文、表格、图形、工作表、格式规则和附件关系；对无法读取、临时锁文件、",
            "镜像、压缩包和来源不明材料分别说明，不得跳过。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a non-overwriting mathematical-modeling project skeleton."
    )
    parser.add_argument("--root", default=".", help="Project root; defaults to current directory.")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "skills").is_dir():
        raise SystemExit("Refusing to bootstrap: skills/ was not found under the project root.")

    files = source_files(root)
    created: list[str] = []
    skipped: list[str] = []

    for relative in STANDARD_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)

    write_if_missing(
        root / "README.md",
        """# 数学建模项目

## 项目状态

当前处于 S0_RECOVER。先恢复已有项目事实；若为全新项目，则确认竞赛、题目、期限、
交付物、团队资源和文件可用性，
再完整阅读原题和附件，进入题意、数据、文献、模型、求解、验证、论文和终稿审计。

## 目录职责

- `data/`：官方输入或其明确指针，不保存生成结论。
- `references/`：外部证据、书目、阅读状态和笔记。
- `planning/`：题意、方案、交互决策和工作日志。
- `src/`：可执行源码；共享工具放入 `src/_utils/`。
- `output/`：程序冻结的结构化结果，禁止手工改数。
- `docs/`：逐问生成供队友讲解的 `docs/<task-id>/solution_brief.md`；其模型建立与求解
  表达必须与真实代码、冻结结果和论文语言规则一致，但不冒充正式论文正文。
- `paper/`：最终论文、图表和编译产物。
- `skills/`：跨项目规则，不写入本题答案。

## 启动要求

从 `skills/SKILL.md` 开始，运行非覆盖初始化脚本后，先向用户报告原始资料清单、
任务地图、数据事实、歧义和逻辑缺口。未经建模方案交互确认，不创建题目专用求解代码。

## 文件格式边界

项目中的README、HANDOFF、planning和docs下的Markdown文件只使用Markdown语法；数学
关系用文字、代码、引用块或Markdown表格表达。LaTeX语法只写入`paper/`目录树中的
`.tex`源文件。内容草稿与正式论文的入口、命名、标记和迁入边界按
`skills/rules/02-latex-setup.md`执行。
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "README.md",
        """# planning 目录权威地图

登记当前总计划、题意、数据、方法、交互决定与实时日志的唯一职责。待审分析放入
`analysis/`，阶段审计快照放入 `audits/`，被替代但需追溯的规划放入 `archive/`。
初始化后根据实际文件补全本表，不得把空模板写成已完成权威。

格式边界：本目录只使用Markdown语法；数学关系用文字、代码、引用块或Markdown表格
表达。LaTeX语法只写入`paper/`目录树中的`.tex`源文件；内容草稿与正式论文的隔离按
`skills/rules/02-latex-setup.md`执行。
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "project_plan.md",
        """# 技术建模步骤清单

本文件主体回答“当前题目怎样做出来”，不要用项目管理阶段名替代技术动作。根据原题
建立并由用户确认以下依赖链：

1. 题意拆解与任务依赖；
2. 先冻结数据方法论，再执行原始数据审计、结构化预处理、审计制图和独立对账；
3. 探索性分析；
4. 按任务依赖一次只打开一个问题，对该问执行：题意与数据事实复核、领域背景与方法
   文献调查、文献启发整理、简单基线、候选模型比较、用户确认、数学规格、求解、
   独立验证、稳健性、解释与冻结；
5. 当前问题冻结后再打开其依赖问题，不提前要求用户决定后续问题的方法；
6. 全部问题完成后执行跨问整合、论文、全链复现和终稿审计。

为每一步补充本题具体动作、产物、完成判据和状态。还必须为原题每一问及具有独立输出
的每个小问或情景建立可勾选子阶段，至少分别显示：本问题意、数据接口、文献导向、
证据重审、简单基线、候选与充分性比较、用户方法决定、数学规格、实现、独立验证、
稳健解释、人工复审/冻结、队友讲解稿、论文映射。每项记录当前状态、关闭证据和未关闭时禁止的动作。
通用流程段落或整问一个状态不能替代该清单；已有下游代码或验证不能反向关闭被跳过的
用户决定和数学规格。

时间排程、协作治理和提交合规放入附录或并列保障项，除非用户明确要求管理优先。每问
若涉及陌生领域、辅助变量、现实机理、外部方法谱系、参数或评价依据，必须在基线和选模
前完成文献导向门，并将来源、阅读状态、支撑主张和限制同步到 `references/`。

## 每问子阶段状态

从原题逐字建立任务行，不根据目录名猜题号。示例结构：

| 任务 | 当前子阶段 | 最近关闭证据 | 下一阶段门 |
|---|---|---|---|
| 待从原题填写 | S1 本问题意 | 未关闭 | 题意确认前不得提出正式模型 |
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "source_inventory.md",
        build_inventory(root, files),
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "understanding.md",
        """# 问题理解（S1 解释权威）

## 原题任务地图

待完整阅读原题后，逐项填写：题目要求、交付结果、已知量、未知量、约束和评价标准。

## 数据事实

只记录从原始资料直接核验的维度、单位、范围、缺失、重复、连通性或样例手算。

## 歧义与逻辑缺口

区分题目明确事实、必要建模假设和会改变答案的待决条件。

## 与用户的首次确认

在此记录用户对任务范围、关键解释和下一阶段的意见。
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "task_matrix.md",
        """# 子问题任务矩阵（跨问导航与状态索引）

在与用户完成题意深交互后填写。每个子问记录题面动作与量词、输入、输出、上游依赖、
当前模型与验证状态以及预期论文落点。这里是导航表，不替代 `understanding.md` 中的
术语、语义边界和完整题意，也不替代方法文档。

| 任务 | 题面动作与量词 | 输入 | 输出 | 上游依赖 | 模型状态 | 验证状态 | 论文落点 |
|---|---|---|---|---|---|---|---|
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "inspiration.md",
        """# 文献与方法启发（条件性权威）

状态：未触发。仅在陌生领域、外部参数、方法谱系或评价依据需要外部证据时启用。

共享背景和跨问方法启发记录在这里；问题专属文献导向按当前问题依次建立，不同时打开
所有问题。每条记录说明来源、阅读状态、支持主张、不能支持的主张，以及它对变量解释、
派生指标、图表、基线、候选模型、验证和论文背景产生的实际影响。文献未同步进入
`references/README.md`、`literature.json`、`references.bib` 和对应阅读笔记前，不得
把搜索结果或聊天内容当成项目证据。
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "method_plan.md",
        """# 建模方案（S3 决策权威）

状态：未到达 S3，不得把模板视为已完成方案。

在题意和证据阶段完成后填写。按任务比较候选模型，说明现实对象映射、变量、参数、
目标、约束、求解逻辑、验证方式、输入输出依赖和最终选择理由。
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "interaction_log.md",
        """# 关键交互与决策日志

只记录会改变题目解释、模型、参数、验证命题、论文结论或交付形式的实质性决定；
不重复登记普通执行动作，后者进入 `work_log.md`。

| 日期 | 阶段 | 证据与问题 | 备选方案 | 用户决定 | 影响文件 |
|---|---|---|---|---|---|
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "ai_usage_log.md",
        """# AI 工具使用实时记录

从项目开始如实记录工具与版本、用途和环节、关键交互、AI候选、用户决定、采纳与人工
修改、验证证据。该文件是最终AI使用详情的事实底稿，不得在终稿阶段凭记忆补造。
若项目未使用AI，则明确标记“不适用”，不得伪造记录。
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "planning" / "work_log.md",
        """# 工作日志

记录实际执行、产物和验证证据；不替代 `interaction_log.md` 中的用户语义或方法决定。

| 日期 | 阶段 | 实际操作 | 产物 | 验证结果 | 尚存问题 |
|---|---|---|---|---|---|
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "references" / "README.md",
        """# 文献证据库

状态：未触发。触发文献调查后，本文件才成为人类可读索引；机器条目同步到
`literature.json`，正式引用同步到 `references.bib`。

记录题名、作者、年份、DOI或原始URL、访问日期、阅读状态、支持主张和适用边界。
搜索结果页、聊天记录和未核验转述不作为正式证据。

| ID | 标题 | 作者 | 年份 | DOI/原始URL | 访问日期 | 阅读状态 | 支撑主张 | 限制 |
|---|---|---|---:|---|---|---|---|---|
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "references" / "literature.json",
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "not_triggered",
                "updated_at": None,
                "entries": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        created,
        skipped,
    )
    write_if_missing(
        root / "references" / "references.bib",
        """% 只登记已经核验并将在正文实质引用的来源。
% 每条应与 references/literature.json 和 references/notes/<id>.md 对应。
""",
        created,
        skipped,
    )
    write_if_missing(
        root / "project_state.json",
        json.dumps(
            {
                "schema_version": "2.0",
                "components": {
                    "shared_project": {
                        "stage": "S0_RECOVER",
                        "status": "in_progress",
                        "evidence": ["planning/source_inventory.md"],
                        "unresolved": ["official inputs and project constraints require review"],
                    },
                    "delivery": {
                        "stage": "S7_PUBLISH",
                        "status": "not_started",
                        "evidence": [],
                        "unresolved": ["all question components must be frozen first"],
                    },
                },
                "project_summary": {"earliest_open_state": "S0_RECOVER"},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        created,
        skipped,
    )

    print(
        json.dumps(
            {
                "root": root.as_posix(),
                "source_file_count": len(files),
                "created": created,
                "skipped_existing": skipped,
                "next_action": (
                    "Realize every directory responsibility, place confirmed official inputs or "
                    "explicit pointers in data/, then complete the technical project plan, source "
                    "inventory, understanding and task matrix with the user."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
