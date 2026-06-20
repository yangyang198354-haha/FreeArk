#!/usr/bin/env python3
"""
inject_tags_extra.py — tag the 4 `tests_*.py` files that live directly under
api/ (NOT api/tests/) but are still discovered by `manage.py test api`.

Same atomic validate-all-first guard as inject_tags.py: writes nothing unless
every import/class is matched.
Usage (from repo root):  python scripts/inject_tags_extra.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, '..', 'FreeArkWeb', 'backend', 'freearkweb', 'api')

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
    inject_file('tests_fault_count.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('CountFaultsForRowTest', 'unit'),
         ('IsFaultParamTest', 'unit'),
         ('ComputeFaultCountV2Test', 'unit'),
         ('ComputeFromDbBatchTest', 'unit'),
         ('SubTypeFilterTest', 'unit'),
         ('FaultCacheTest', 'unit'),
         ('DeviceFaultCountViewTest', 'integration'),
         ('DeviceFaultSummaryViewTest', 'integration'),
         ('DeviceListFaultCountFieldTest', 'integration'),
         ('FaultCountPerformanceTest', 'integration')])

    inject_file('tests_fault_event.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestIsFaultCandidate', 'unit'),
         ('TestIsFaultActive', 'unit'),
         ('TestGetFaultTypeAndSeverity', 'unit'),
         ('TestGetFaultMessage', 'unit'),
         ('TestStateMachineTransitions', 'unit'),
         ('TestT2ThrottledPersist', 'unit'),
         ('TestRebuildFromDb', 'unit'),
         ('FaultViewTestBase', 'integration'),
         ('TestFaultEventListAuth', 'integration'),
         ('TestFaultEventListPagination', 'integration'),
         ('TestFaultEventListFilters', 'integration'),
         ('TestFaultEventListDefaultTimeRange', 'integration'),
         ('TestFaultEventCategories', 'integration'),
         ('TestFaultEventSerializer', 'integration'),
         ('TestFaultCleanupCommand', 'unit'),
         ('TestHandleMessageIntegration', 'integration'),
         ('TestFaultEventAPIIntegration', 'integration'),
         ('TestFaultFilterParamFormatCompat', 'integration'),
         ('TestBugFM004RoomNumberSegments', 'integration'),
         ('TestBugFM005SubTypeProductCodeFilter', 'integration'),
         ('TestBugFM006RoomFilter', 'integration'),
         ('TestBugFM007DeviceNameOverride', 'integration'),
         ('TestBugFM008FaultMessageZh', 'unit')])

    inject_file('tests_session_timeout.py',
        ('from django.test import TestCase, override_settings',
         'from django.test import TestCase, override_settings, tag'),
        [('SlidingWindowAuthenticationUnitTests', 'unit'),
         ('LoginAPITests', 'integration'),
         ('RememberMeTests', 'integration'),
         ('RegisterAPITests', 'integration'),
         ('LogoutCascadeTests', 'integration'),
         ('ThrottleIntegrationTests', 'integration'),
         ('TokenActivityModelTests', 'unit')])

    inject_file('tests_rag.py',
        ('from django.test import TestCase, override_settings',
         'from django.test import TestCase, override_settings, tag'),
        [('TestRagDocumentModel', 'unit'),
         ('TestRagUploadAPI', 'integration'),
         ('TestRagService', 'unit'),
         ('TestSearchTool', 'unit'),
         ('TestRagIntegration', 'integration'),
         ('TestSystemPromptRAG', 'unit'),
         ('TestRagSerializer', 'unit')])


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
