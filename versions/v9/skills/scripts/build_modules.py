#!/usr/bin/env python3
"""Build deterministic V9 domain modules from the frozen V8 detailed rules."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


MODULES = {
    "orchestration-detail.md": {
        "title": "完整项目编排细节",
        "sources": ["00-project-orchestration.md"],
        "boundary": "保留任务分解、依赖关系和完整项目方法；旧全局控制权、路由、回执与无条件全文复读不执行。",
    },
    "project-platform.md": {
        "title": "项目平台与目录职责",
        "sources": ["01-contest-project-pattern.md"],
        "boundary": "目录职责和项目分层仍有效；实际创建受 lazy artifact contract 控制，不默认生成完整脚手架。",
    },
    "visuals-layout.md": {
        "title": "图表、科学可视化、LaTeX 与版面",
        "sources": [
            "02-latex-setup.md",
            "04-figure-generator.md",
            "27-visual-layout-acceptance.md",
            "34-visuals-minimum.md",
            "37-scientific-figure-design.md",
        ],
        "boundary": "图表、渲染和版面程序及验收条款有效；旧路径跳转与全局路由声明不执行。",
    },
    "manuscript-content.md": {
        "title": "论文内容、表达与读者审计",
        "sources": [
            "03-paper-content-rules.md",
            "13-excellent-paper-expression.md",
            "17-reader-first-manuscript-audit.md",
        ],
        "boundary": "内容与读者可理解性规则有效；局部修改是否升级为全文审计由 V9 路由和完成范围决定。",
    },
    "verification.md": {
        "title": "实现验证、模型检验、稳健性与不确定性",
        "sources": [
            "05-audit-protocol.md",
            "09-robustness-checker.md",
            "32-verification-minimum.md",
            "36-uncertainty-error-analysis.md",
        ],
        "boundary": "验证判据和审计细节有效；验证层级统一解释为 E1-E4，读取范围和恢复等级由 V9 契约决定。",
    },
    "writing-profile.md": {
        "title": "可选写作风格配置",
        "sources": ["06-weiwei-norms.md"],
        "boundary": "仅在用户或项目明确选择该写作配置时生效，不覆盖官方格式、数学事实或项目冻结决定。",
    },
    "modeling.md": {
        "title": "模型设计、算法与实现流水线",
        "sources": [
            "07-algorithm-reference.md",
            "15-pipeline-methodology.md",
            "31-modeling-minimum.md",
        ],
        "boundary": "模型与算法程序有效；状态提升、写权限和方案批准由 V9 控制器决定。",
    },
    "evidence-delivery.md": {
        "title": "文献、来源、数据交接、论文终结与交付",
        "sources": [
            "08-literature-search.md",
            "10-json-handoff.md",
            "11-paper-finalizer.md",
            "12-source-audit-and-provenance.md",
            "28-evidence-acceptance.md",
            "35-provenance-delivery-minimum.md",
        ],
        "boundary": "文献、来源、跨脚本数据契约和交付细节有效；JSON handoff 不再拥有项目会话状态。",
    },
    "data.md": {
        "title": "数据身份、审计、处理与冻结",
        "sources": ["16-data-audit-methodology.md", "30-data-minimum.md"],
        "boundary": "数据方法完整保留；数据状态采用 D0-D3，原始数据不得被静默覆盖。",
    },
    "manuscript-acceptance.md": {
        "title": "论文全局与分节验收",
        "sources": [
            "20-execution-gates.md",
            "21-global-manuscript-acceptance.md",
            "22-front-matter-acceptance.md",
            "23-background-analysis-acceptance.md",
            "24-assumptions-data-acceptance.md",
            "25-model-results-acceptance.md",
            "26-conclusion-references-acceptance.md",
            "33-manuscript-minimum.md",
        ],
        "boundary": "验收条款有效；20 文件的“第一入口”、路由和全局控制权声明已退休。",
    },
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, help="V8 skills directory")
    parser.add_argument("--skill-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()

    skill_root = args.skill_root.resolve()
    source_root = (args.source_root or (skill_root.parents[1] / "skills_v8" / "skills")).resolve()
    rules_root = source_root / "rules"
    out_root = skill_root / "references" / "modules"
    out_root.mkdir(parents=True, exist_ok=True)

    disposition_path = skill_root / "references" / "migration" / "rule-disposition.json"
    disposition = json.loads(disposition_path.read_text(encoding="utf-8"))
    required_active = {
        Path(entry["source"]).name
        for entry in disposition["entries"]
        if entry.get("active_detail") is True
    }
    configured = {name for spec in MODULES.values() for name in spec["sources"]}
    missing_config = sorted(required_active - configured)
    extra_config = sorted(configured - required_active)
    if missing_config or extra_config:
        raise SystemExit(f"module mapping mismatch: missing={missing_config}, extra={extra_config}")

    seen: set[str] = set()
    manifest_modules = []
    for output_name, spec in MODULES.items():
        chunks = [
            f"# {spec['title']}",
            "",
            "> 本文件由 `scripts/build_modules.py` 从冻结的 V8 详细规则确定性生成。",
            "> 下列来源块中的领域步骤、数学判据、失败条件和验收细节继续生效；",
            "> 任何关于全局权限、状态、路由、回执、项目初始化、强制复读、版本身份或第一入口的旧指令均不执行，由 V9 `SKILL.md` 与机器契约唯一负责。",
            "> 旧文件路径仅表示迁移谱系，不触发递归加载。",
            "",
            f"**模块边界：** {spec['boundary']}",
            "",
        ]
        source_records = []
        for source_name in spec["sources"]:
            if source_name in seen:
                raise SystemExit(f"source imported more than once: {source_name}")
            seen.add(source_name)
            path = rules_root / source_name
            if not path.is_file():
                raise SystemExit(f"missing source: {path}")
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            chunks.extend(
                [
                    "---",
                    "",
                    f"## V8 来源：`rules/{source_name}`",
                    "",
                    text.rstrip(),
                    "",
                ]
            )
            source_records.append(
                {
                    "path": f"rules/{source_name}",
                    "sha256": sha256_bytes(raw),
                    "lines": len(text.splitlines()),
                }
            )
        output_text = "\n".join(chunks).rstrip() + "\n"
        output_path = out_root / output_name
        output_path.write_text(output_text, encoding="utf-8", newline="\n")
        manifest_modules.append(
            {
                "module": f"references/modules/{output_name}",
                "sha256": sha256_bytes(output_text.encode("utf-8")),
                "lines": len(output_text.splitlines()),
                "sources": source_records,
            }
        )

    manifest = {
        "schema_version": "1.0",
        "release": "9.0.0",
        "source_release": "V8",
        "source_root_hint": "../../skills_v8/skills",
        "source_count": len(seen),
        "modules": manifest_modules,
    }
    manifest_path = skill_root / "references" / "migration" / "module-source-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"built {len(MODULES)} modules from {len(seen)} V8 detailed files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

