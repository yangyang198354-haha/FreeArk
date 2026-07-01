#!/usr/bin/env python3
"""Find test classes whose EFFECTIVE tag set (own + inherited from in-file
bases) spans more than one layer — those tests get double-counted across
--tag runs. Also report per-class own test-method counts."""
import ast
import os

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.join(HERE, '..', '..', 'FreeArkWeb', 'backend', 'freearkweb', 'api')
LAYERS = {'unit', 'integration', 'e2e'}


def class_own_tags(node):
    tags = set()
    for d in node.decorator_list:
        if isinstance(d, ast.Call):
            f = d.func
            if getattr(f, 'id', None) == 'tag' or getattr(f, 'attr', None) == 'tag':
                for a in d.args:
                    if isinstance(a, ast.Constant):
                        tags.add(a.value)
    return tags


def own_test_methods(node):
    return [b.name for b in node.body
            if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)) and b.name.startswith('test')]


def scan(path):
    with open(path, encoding='utf-8') as f:
        tree = ast.parse(f.read())
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    base_names = {}
    for n in classes.values():
        bn = []
        for b in n.bases:
            if isinstance(b, ast.Name):
                bn.append(b.id)
            elif isinstance(b, ast.Attribute):
                bn.append(b.attr)
        base_names[n.name] = bn

    def effective_tags(name, seen=None):
        seen = seen or set()
        if name in seen or name not in classes:
            return set()
        seen.add(name)
        tags = set(class_own_tags(classes[name]))
        for b in base_names.get(name, []):
            tags |= effective_tags(b, seen)
        return tags

    results = []
    for name, node in classes.items():
        tags = effective_tags(name)
        layers = tags & LAYERS
        methods = own_test_methods(node)
        if len(layers) > 1:
            results.append((name, sorted(layers), len(methods)))
    return results


total = 0
for fn in sorted(os.listdir(API)):
    if not (fn.startswith('test') and fn.endswith('.py')):
        continue
    res = scan(os.path.join(API, fn))
    if res:
        print(f'\n{fn}:')
        for name, layers, nm in res:
            print(f'    {name}  effective_layers={layers}  own_test_methods={nm}')
            total += nm

print(f'\n==== classes spanning >1 layer; sum of their OWN test methods = {total} ====')
