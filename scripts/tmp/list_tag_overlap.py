#!/usr/bin/env python3
"""Enumerate test IDs per tag via Django's runner and report overlaps.
Run from FreeArkWeb/backend/freearkweb (where manage.py lives)."""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.test_settings')
os.environ['FREEARK_POC_MOCK'] = '1'
django.setup()

from django.test.runner import DiscoverRunner


def ids(tags=None):
    r = DiscoverRunner(tags=set(tags) if tags else None, verbosity=0)
    suite = r.build_suite(['api'])
    return set(t.id() for t in suite)


allt = ids(None)
u = ids(['unit'])
i = ids(['integration'])
e = ids(['e2e'])

print(f'total={len(allt)}  unit={len(u)}  integration={len(i)}  e2e={len(e)}')
print(f'sum layers = {len(u) + len(i) + len(e)}')
print(f'\nu & i  ({len(u & i)}):')
for x in sorted(u & i):
    print('   ', x)
print(f'\nu & e  ({len(u & e)}):')
for x in sorted(u & e):
    print('   ', x)
print(f'\ni & e  ({len(i & e)}):')
for x in sorted(i & e):
    print('   ', x)

untagged = allt - u - i - e
print(f'\nUNTAGGED (in full run, no layer)  ({len(untagged)}):')
for x in sorted(untagged):
    print('   ', x)
