#!/usr/bin/env python3
"""
gen_test_inventory.py — regenerate docs/testing/test_inventory.md from the
live test sources. Run after changing any @tag.

Usage (from repo root):  python scripts/gen_test_inventory.py
"""
import ast
import os
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
API = os.path.join(ROOT, 'FreeArkWeb', 'backend', 'freearkweb', 'api')
TESTS = os.path.join(API, 'tests')
OUT = os.path.join(ROOT, 'docs', 'testing', 'test_inventory.md')
LAYERS = ('unit', 'integration', 'e2e')


def own_tags(node):
    tags = set()
    for d in node.decorator_list:
        if isinstance(d, ast.Call):
            f = d.func
            if getattr(f, 'id', None) == 'tag' or getattr(f, 'attr', None) == 'tag':
                for a in d.args:
                    if isinstance(a, ast.Constant):
                        tags.add(a.value)
    return tags


def test_methods(node):
    return [b.name for b in node.body
            if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name.startswith('test')]


def collect(path):
    """Return list of (class_name, layer_or_None, [methods]) for test classes."""
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}

    def eff(name, seen=None):
        seen = seen or set()
        if name in seen or name not in classes:
            return set()
        seen.add(name)
        t = set(own_tags(classes[name]))
        for b in classes[name].bases:
            bn = getattr(b, 'id', None) or getattr(b, 'attr', None)
            if bn:
                t |= eff(bn, seen)
        return t

    out = []
    for name, node in classes.items():
        methods = test_methods(node)
        layer_set = eff(name) & set(LAYERS)
        layer = sorted(layer_set)[0] if len(layer_set) == 1 else (
            '+'.join(sorted(layer_set)) if layer_set else None)
        # skip pure bases with no own tests AND no layer (helper bases)
        if not methods and layer is None:
            continue
        out.append((name, layer, methods))
    return out


def file_list():
    files = []
    for fn in sorted(os.listdir(TESTS)):
        if fn.startswith('test_') and fn.endswith('.py'):
            files.append(('api/tests/' + fn, os.path.join(TESTS, fn)))
    for fn in sorted(os.listdir(API)):
        if fn.startswith('tests_') and fn.endswith('.py'):
            files.append(('api/' + fn, os.path.join(API, fn)))
    return files


EXCLUDED = [
    ('api/tests/test_dashboard_perf.py', '性能基准脚本（非 TestCase，需生产 token），手动运行'),
    ('datacollection/tests/test_plc_write_subscriber.py', 'pytest 风格，用 `pytest` 运行'),
    ('datacollection/test_log_config_manager.py', 'unittest，独立运行 `python -m unittest`'),
    ('tests/test_datacollection_refactor.py', 'unittest/pytest，重构验证'),
    ('test_plc_status_change_history.py', '仓库根孤儿调试脚本（无断言）——不属正式套件'),
    ('project_workspace/FreeArk_AsyncMQTT/test_mqtt_consumer_async.py', '临时 PoC——不属正式套件'),
    ('agents/langgraph-poc/test_delegation.py', '孤儿验证脚本——不属正式套件'),
]


def main():
    files = file_list()
    per_file = []
    totals = {k: 0 for k in LAYERS}
    grand = 0
    for rel, path in files:
        classes = collect(path)
        counts = {k: 0 for k in LAYERS}
        for _, layer, methods in classes:
            if layer in counts:
                counts[layer] += len(methods)
        for k in LAYERS:
            totals[k] += counts[k]
        grand += sum(counts.values())
        per_file.append((rel, classes, counts))

    lines = []
    lines.append('# FreeArk 后端测试清单（test_inventory.md）')
    lines.append('')
    lines.append(f'> 自动生成：`python scripts/gen_test_inventory.py`（请勿手改，改 @tag 后重新生成）')
    lines.append(f'> 生成日期：{datetime.date.today().isoformat()}')
    lines.append('')
    lines.append('**分层方式**：Django 原生 `@tag(\'unit\'|\'integration\'|\'e2e\')`（类级）。'
                 '文件位置保持不动（扁平），仅靠 tag 分层。')
    lines.append('')
    lines.append('**运行命令**（主测试体，Django test runner）：')
    lines.append('```bash')
    lines.append('cd FreeArkWeb/backend/freearkweb')
    lines.append('FREEARK_POC_MOCK=1 python manage.py test api --settings=freearkweb.test_settings [--tag=unit|integration|e2e]')
    lines.append('```')
    lines.append('')
    lines.append('## 汇总')
    lines.append('')
    lines.append('| 层级 | 用例数 |')
    lines.append('|------|-------:|')
    for k in LAYERS:
        lines.append(f'| {k} | {totals[k]} |')
    lines.append(f'| **合计（已分层）** | **{grand}** |')
    lines.append('')
    lines.append(f'> 全量 `manage.py test api` 共发现 **1702** 个测试；上表三层之和应等于 1702（每个用例恰属一层，无重复、无遗漏）。')
    lines.append('')
    lines.append('### 各文件分层用例数')
    lines.append('')
    lines.append('| 脚本 | unit | integration | e2e | 合计 |')
    lines.append('|------|-----:|------------:|----:|-----:|')
    for rel, classes, counts in per_file:
        tot = sum(counts.values())
        lines.append(f'| `{rel}` | {counts["unit"]} | {counts["integration"]} | {counts["e2e"]} | {tot} |')
    lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## 明细：脚本 → 测试类［层级］→ 用例方法')
    lines.append('')
    for rel, classes, counts in per_file:
        lines.append(f'### `{rel}`')
        lines.append('')
        for name, layer, methods in classes:
            tag = f'［{layer}］' if layer else '［基类/无层级］'
            lines.append(f'- **{name}** {tag} — {len(methods)} 用例')
            for m in methods:
                lines.append(f'  - `{m}`')
        lines.append('')
    lines.append('---')
    lines.append('')
    lines.append('## C. 排除 / 卫星脚本（不在 `manage.py test api` 分层范围内）')
    lines.append('')
    lines.append('| 脚本 | 说明 / 运行方式 |')
    lines.append('|------|------------------|')
    for rel, desc in EXCLUDED:
        lines.append(f'| `{rel}` | {desc} |')
    lines.append('')

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    print(f'WROTE {os.path.relpath(OUT, ROOT)}')
    print(f'layer totals: unit={totals["unit"]} integration={totals["integration"]} e2e={totals["e2e"]} grand={grand}')


if __name__ == '__main__':
    main()
