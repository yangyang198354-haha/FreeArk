#!/usr/bin/env python3
"""Report module-level test classes in api/tests/ that lack a @tag decorator."""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, '..', '..', 'FreeArkWeb', 'backend', 'freearkweb', 'api', 'tests')


def is_test_class(node):
    # has a test_* method, or subclasses something *TestCase
    for b in node.body:
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name.startswith('test'):
            return True
    for base in node.bases:
        name = ''
        if isinstance(base, ast.Name):
            name = base.id
        elif isinstance(base, ast.Attribute):
            name = base.attr
        if 'TestCase' in name:
            return True
    return False


def has_tag(node):
    for d in node.decorator_list:
        f = d.func if isinstance(d, ast.Call) else d
        nm = getattr(f, 'id', None) or getattr(f, 'attr', None)
        if nm == 'tag':
            return True
    return False


def count_tests(node):
    return sum(
        1 for b in node.body
        if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name.startswith('test')
    )


total_untagged_methods = 0
for fn in sorted(os.listdir(BASE)):
    if not (fn.startswith('test_') and fn.endswith('.py')):
        continue
    path = os.path.join(BASE, fn)
    with open(path, encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError as e:
            print(f'!! SYNTAX ERROR in {fn}: {e}')
            continue
    untagged = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and is_test_class(node) and not has_tag(node):
            untagged.append((node.name, count_tests(node)))
    if untagged:
        s = sum(n for _, n in untagged)
        total_untagged_methods += s
        print(f'\n{fn}  ({s} untagged test methods in {len(untagged)} classes):')
        for name, n in untagged:
            print(f'    {name}  ({n} tests)')

print(f'\n==== TOTAL untagged direct test methods: {total_untagged_methods} ====')
print('(note: inherited/base-class test methods are not counted here)')
