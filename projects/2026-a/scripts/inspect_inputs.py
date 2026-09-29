"""Read-only platform diagnostics; never solves a model or changes source files."""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ['A题.pdf', '附件/附件1.xlsx', '附件/附件2.xlsx'] + [
    f'附件/附件3/result{i}.xlsx' for i in range(1, 5)
]
PACKAGES = ['numpy', 'scipy', 'pandas', 'matplotlib', 'openpyxl', 'pypdf', 'jsonschema']

# Display glosses only; acceptance rules belong to skills/references/state-machine.json.
STAGE_LABELS = {
    'P0': '项目进行中，必需组件尚未全部验收',
    'P1': '必需组件已就绪，待交付接受',
    'P2': '交付已接受',
    'S0': '尚未正式接受问题定义',
    'S1': '已接受范围与问题定义',
    'S2': '已接受证据计划；候选比较尚待正式接受',
    'S3': '已接受候选比较；模型规格与选择依据尚待接受',
    'S4': '已接受模型规格与选择依据',
    'S5': '已接受实现引用',
    'S6': '已接受实现与数值证据；技术验收尚未关闭',
    'S7': '技术验收已关闭',
    'D0': '输入身份与来源尚未正式接受',
    'D1': '已接受输入身份与来源',
    'D2': '已接受审计与处理决定',
    'D3': '已接受数据接口及其验证',
    'A0': '工作产物尚未正式接受',
    'A1': '已接受产物草稿',
    'A2': '已接受产物验证',
    'A3': '产物已正式接受',
}


def show_status(state):
    project = state['project']
    print(f"{project['id']} | {project['state']} {STAGE_LABELS.get(project['state'], '')}")
    print(f"状态来源：.modeling/state.json（版本 {state['revision']}）")
    print('\n各组件最后接受的阶段：')
    for name, component in state['components'].items():
        stage = component['state']
        print(f"  {name}: {stage} {STAGE_LABELS.get(stage, '')}")
        if component.get('status') in {'blocked', 'invalidated'}:
            print(f"    有效性：{component['status']}")
    print('说明：工作分析可以先完成；文件存在不等于正式验收或冻结。')
    pending = [item for item in state['open_decisions'] if item['status'] == 'open']
    print(f'\n当前待确认事项（{len(pending)}项；已解决的历史事项不重复列出）：')
    for item in pending:
        print(f"  [{item['id']}] {item['subject']}")
        for index, option in enumerate(item['options'], 1):
            print(f'    {index}. {option}')
    if not pending:
        print('  无。')
    print('\n下一动作：')
    for item in state['next_actions']:
        print(f"  {item['component_id']}: {item['action']}")
        if item['blocked_by']:
            print('    等待：' + '、'.join(item['blocked_by']))
    print('\n分析材料与图表入口：README.md；目录与复现说明：planning/platform.md')


def inventory():
    from openpyxl import load_workbook
    from pypdf import PdfReader

    items = []
    for name in INPUTS:
        path = ROOT / name
        item = {'path': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'bytes': path.stat().st_size}
        if path.suffix == '.pdf':
            item['pages'] = len(PdfReader(path).pages)
        else:
            book = load_workbook(path, read_only=True, data_only=False)
            try:
                item['sheets'] = []
                for sheet in book:
                    rows = list(sheet.values)
                    info = {'name': sheet.title, 'rows': sheet.max_row,
                            'columns': sheet.max_column, 'header': rows[0],
                            'first_data_row': rows[1], 'last_row': rows[-1],
                            'formula_cells': sum(isinstance(v, str) and v.startswith('=')
                                                 for row in rows for v in row)}
                    if name in INPUTS[1:3]:
                        times = [row[0] for row in rows[1:]]
                        info.update(data_rows=len(times), time_start_s=min(times),
                                    time_end_s=max(times),
                                    time_strictly_increasing=all(b > a for a, b in zip(times, times[1:])))
                    item['sheets'].append(info)
            finally:
                book.close()
        items.append(item)
    return {'scope': 'official_inputs_only', 'kind': 'working_structure_snapshot',
            'note': 'Not a data-quality acceptance or recovery baseline.', 'files': items}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['doctor', 'inputs', 'status'])
    parser.add_argument('--save-inventory', action='store_true',
                        help='Explicitly refresh planning/input_inventory.json; inputs action only.')
    args = parser.parse_args()
    if args.save_inventory and args.action != 'inputs':
        parser.error('--save-inventory requires inputs')
    if args.action == 'doctor':
        failures = []
        print('Python:', sys.version.split()[0], sys.executable)
        for package in PACKAGES:
            try:
                importlib.import_module(package)
                print(package, importlib.metadata.version(package), 'OK')
            except Exception as exc:
                failures.append(package)
                print(package, 'FAILED:', exc)
        if failures:
            return 1
    elif args.action == 'inputs':
        result = inventory()
        target = ROOT / 'planning/input_inventory.json'
        if args.save_inventory:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        elif target.exists():
            previous = {f['path']: f['sha256'] for f in json.loads(target.read_text(encoding='utf-8'))['files']}
            changed = [f['path'] for f in result['files'] if previous.get(f['path']) != f['sha256']]
            if changed:
                print('INPUT CHANGED:', ', '.join(changed))
                return 1
        for item in result['files']:
            print(item['path'], item['bytes'], 'bytes', item['sha256'][:12])
            for sheet in item.get('sheets', []):
                print(' ', sheet['name'], f"{sheet['rows']} rows x {sheet['columns']} columns")
    else:
        state = json.loads((ROOT / '.modeling/state.json').read_text(encoding='utf-8'))
        show_status(state)
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    raise SystemExit(main())
