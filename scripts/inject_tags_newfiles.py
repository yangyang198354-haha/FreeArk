#!/usr/bin/env python3
"""
inject_tags_newfiles.py — tag the chat-session test files added to main after
the initial layering (PRs #34/#35): api/tests/test_chat_*, test_session_*,
test_ws_session_resolve.

Same atomic validate-all-first guard as inject_tags.py.
Usage (from repo root):  python scripts/inject_tags_newfiles.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, '..', 'FreeArkWeb', 'backend', 'freearkweb', 'api', 'tests')

PENDING = {}
ERRORS = []


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def inject_file(filename, import_patch, class_tags):
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        ERRORS.append(f'{filename}: FILE NOT FOUND')
        return
    content = PENDING[path] if path in PENDING else _read(path)
    old, new = import_patch
    if old not in content:
        ERRORS.append(f'{filename}: import line not found: {old!r}')
    else:
        content = content.replace(old, new, 1)
    for class_name, tag_str in class_tags:
        pattern = r'(^class ' + re.escape(class_name) + r'\()'
        replacement = f"@tag('{tag_str}')\n" + r'\1'
        new_content = re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)
        if new_content == content:
            ERRORS.append(f'{filename}: class not found: {class_name}')
        else:
            content = new_content
    PENDING[path] = content


def run():
    inject_file('test_chat_memory_session.py',
        ('from django.test import TestCase, override_settings',
         'from django.test import TestCase, override_settings, tag'),
        [('LoadHistoryBySessionEmptyTest', 'unit'),
         ('LoadHistoryBySessionBasicTest', 'unit'),
         ('LoadHistoryBySessionIsolationTest', 'unit'),
         ('LoadHistoryBySessionLimitTest', 'unit'),
         ('SoftDeleteSessionTest', 'unit'),
         ('GetSessionsExtendedTest', 'unit'),
         ('LoadHistoryLimitZeroTest', 'unit'),
         ('ResolveSessionTest', 'unit'),
         ('GetSessionsOrderTest', 'unit'),
         ('LoadHistoryBySessionOrderTest', 'unit')])

    inject_file('test_chat_session_e2e.py',
        ('from django.test import TransactionTestCase',
         'from django.test import TransactionTestCase, tag'),
        [('FullSessionLifecycleE2ETest', 'e2e')])

    inject_file('test_chat_session_feature.py',
        ('from django.test import TestCase, TransactionTestCase',
         'from django.test import TestCase, TransactionTestCase, tag'),
        [('GenerateTitleTruncateTest', 'unit'),
         ('GenerateTitleLlmAsyncTest', 'unit'),
         ('GetSessionHistoryTest', 'unit'),
         ('EnsureSessionCreatedTest', 'integration'),
         ('GetSessionsTitleFieldTest', 'unit'),
         ('SessionHistoryViewTest', 'integration'),
         ('GetSessionsTitleIntegrationTest', 'integration'),
         ('WsNoDbOnConnectTest', 'integration'),
         ('WsFirstMessageCreatesSessionTest', 'integration')])

    inject_file('test_session_delete_view.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('SessionDeleteViewTest', 'integration'),
         ('MyMemoryViewSessionKeyFullTest', 'integration')])

    inject_file('test_ws_session_resolve.py',
        ('from django.test import TransactionTestCase',
         'from django.test import TransactionTestCase, tag'),
        [('WsResolveSessionTest', 'integration')])


if __name__ == '__main__':
    run()
    if ERRORS:
        print(f'VALIDATION FAILED ({len(ERRORS)} problems) — NOTHING written:\n')
        for e in ERRORS:
            print('  - ' + e)
        sys.exit(1)
    for path, content in PENDING.items():
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print('WROTE ' + os.path.relpath(path, os.path.join(HERE, '..')))
    print(f'\nOK: {len(PENDING)} files tagged, 0 errors.')
