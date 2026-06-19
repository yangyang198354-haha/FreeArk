#!/usr/bin/env python3
"""
inject_tags.py — FreeArk test suite @tag injection (2026-06-19)

Strictly additive. For each Django test file under api/tests/ it:
  1. Adds `tag` to the `from django.test import ...` line (or adds
     `from django.test import tag` after `import unittest`).
  2. Inserts `@tag('unit'|'integration'|'e2e')` directly above each test class.

Safety model: VALIDATE-ALL-FIRST, ATOMIC.
  - All edits are computed in memory and validated.
  - If ANY import/class is not found, the script writes NOTHING and lists
    every problem at once (exit 1).
  - Files are written only when zero errors remain.

Usage (from repo root):  python scripts/inject_tags.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(HERE, '..', 'FreeArkWeb', 'backend', 'freearkweb', 'api', 'tests')

PENDING = {}   # path -> new content
ERRORS = []    # list of human-readable problems


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def _current(path):
    return PENDING[path] if path in PENDING else _read(path)


def inject_file(filename, import_patch, class_tags):
    """import_patch = (old_str, new_str) or None; class_tags = [(class_name, tag), ...]"""
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        ERRORS.append(f'{filename}: FILE NOT FOUND')
        return
    content = _current(path)

    if import_patch:
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


def inject_no_django_test_import(filename, class_tags):
    """For files whose only test import is `import unittest`."""
    path = os.path.join(BASE, filename)
    if not os.path.exists(path):
        ERRORS.append(f'{filename}: FILE NOT FOUND')
        return
    content = _current(path)

    if 'from django.test import tag' not in content:
        new_content = re.sub(
            r'^(import unittest\b.*)',
            r'\1\nfrom django.test import tag',
            content, count=1, flags=re.MULTILINE,
        )
        if new_content == content:
            ERRORS.append(f"{filename}: 'import unittest' line not found")
        else:
            content = new_content

    for class_name, tag_str in class_tags:
        pattern = r'(^class ' + re.escape(class_name) + r'\()'
        replacement = f"@tag('{tag_str}')\n" + r'\1'
        new_content = re.sub(pattern, replacement, content, count=1, flags=re.MULTILINE)
        if new_content == content:
            ERRORS.append(f'{filename}: class not found: {class_name}')
        else:
            content = new_content

    PENDING[path] = content


def run_injections():
    # ── Group A: @tag('unit') pure files ──────────────────────────────────
    inject_file('test_device_settings.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('PLCWriteRecordModelTests', 'unit'),
         ('PLCWriteRecordSerializerTests', 'unit'),
         ('NormalizeSelectValuesTests', 'unit'),
         ('IsWritableTests', 'unit'),
         ('HandleWriteAckTests', 'unit')])

    inject_file('test_condensation_v070_unit.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('MigrationApplyTest', 'unit'),
         ('MakeMigrationsCheckTest', 'unit'),
         ('NormalizeSystemSwitchTest', 'unit'),
         ('StateMachineT1T2T3Test', 'unit'),
         ('StateMachineT2ThrottledPersistTest', 'unit'),
         ('SystemSwitchDualSourceTest', 'unit'),
         ('SnapshotFieldTest', 'unit'),
         ('ErrorToleranceTest', 'unit'),
         ('CleanupCommandTest', 'unit')])

    inject_file('test_fault_mgmt_v064_unit.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestConstantsStructure', 'unit'),
         ('TestRoomLookup', 'unit'),
         ('TestStateMachineT1RoomLookup', 'unit'),
         ('TestOracleReverseTable', 'unit')])

    inject_file('test_openclaw_unit.py',
        ('from django.test import TestCase, override_settings',
         'from django.test import TestCase, override_settings, tag'),
        [('TestUrlNormalization', 'unit'),
         ('TestConnectFrameBuilder', 'unit'),
         ('TestChatSendFrameBuilder', 'unit'),
         ('TestStreamChat', 'unit'),
         ('TestGetUserByToken', 'unit')])

    inject_file('test_inspection_agent_v110.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('WriteAuthPolicyTest', 'unit'),
         ('EventPollerTest', 'unit'),
         ('WorkOrderCreateTest', 'unit'),
         ('AuditLogTest', 'unit')])

    inject_file('test_inspection_agent_loop_v110.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('DecisionLoopTest', 'unit')])

    inject_file('test_inspection_workorder_v110.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('SchemaTest', 'unit'),
         ('InspectionStatusDefaultTest', 'unit'),
         ('WorkOrderModelTest', 'unit')])

    inject_file('test_langgraph_phase_a.py',
        ('from django.test import SimpleTestCase, override_settings',
         'from django.test import SimpleTestCase, override_settings, tag'),
        [('PromptLoadingTests', 'unit'),
         ('RouterClassifierTests', 'unit'),
         ('ChatBackendFactoryTests', 'unit'),
         ('OrchestratorRoutingTests', 'unit'),
         ('FaDirectRoutingTests', 'unit'),
         ('FaDirectConnectionHealthTests', 'unit'),
         ('UsageDailyParamMappingTests', 'unit'),
         ('DateHintInjectionTests', 'unit'),
         ('LangGraphAdapterTests', 'unit'),
         ('OrchestratorWriteGateTests', 'unit')])

    inject_file('test_langgraph_phase_g.py',
        ('from django.test import SimpleTestCase, override_settings',
         'from django.test import SimpleTestCase, override_settings, tag'),
        [('ReadKnowledgeDelegationTests', 'unit'),
         ('WriteDelegationGateTests', 'unit')])

    inject_file('test_memory_models.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('ChatSessionCRUDTest', 'unit'),
         ('ChatSessionCascadeTest', 'unit'),
         ('ChatSessionIsolationTest', 'unit'),
         ('ChatSessionIndexTest', 'unit'),
         ('ChatMessageCRUDTest', 'unit'),
         ('ChatMessageCascadeTest', 'unit'),
         ('ChatMessageIndexTest', 'unit'),
         ('ChatMessageRelatedManagerTest', 'unit')])

    inject_file('test_memory_chat_memory.py',
        ('from django.test import TestCase, override_settings',
         'from django.test import TestCase, override_settings, tag'),
        [('CreateSessionTest', 'unit'),
         ('CloseSessionTest', 'unit'),
         ('AppendMessageTest', 'unit'),
         ('LoadHistoryTest', 'unit'),
         ('LoadHistoryDegradationTest', 'unit'),
         ('BuildInjectPrefixTest', 'unit'),
         ('ClearMemoryTest', 'unit'),
         ('GetSessionsTest', 'unit')])

    inject_no_django_test_import('test_memory_skeleton_guard_sh.py',
        [('SkeletonGuardInitTest', 'unit'),
         ('SkeletonGuardVerifyTest', 'unit'),
         ('SkeletonGuardStatusTest', 'unit'),
         ('SkeletonGuardInvalidCommandTest', 'unit')])

    inject_file('test_mqtt_worker_conn_poison_heal.py',
        ('from django.test import SimpleTestCase', 'from django.test import SimpleTestCase, tag'),
        [('TestIsDbConnectionError', 'unit'),
         ('TestWorkerLoopHeal', 'unit')])

    inject_file('test_dph_cleanup_service.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TC_U_DPH_001_OperationalError_Graceful', 'unit'),
         ('TC_U_DPH_002_GenericException_Graceful', 'unit'),
         ('TC_U_DPH_003_CronLoop_RunCleanup_Error', 'unit'),
         ('TC_U_DPH_004_CronLoop_ScheduleError', 'unit'),
         ('TC_U_DPH_005_OnceModeOperationalError', 'unit'),
         ('TC_U_DPH_006_OnceModeGenericException', 'unit'),
         ('TC_U_DPH_007_DryRun', 'unit'),
         ('TC_U_DPH_008_NoExpiredData', 'unit'),
         ('TC_U_DPH_009_NormalDeletion', 'unit'),
         ('TC_U_DPH_012_SetupScheduleValid', 'unit'),
         ('TC_U_DPH_013_SetupScheduleInvalid', 'unit'),
         ('TC_U_DPH_014_ApplyDbTimeout', 'unit'),
         ('TC_U_DPH_015_ApplyDbTimeout_NoOp', 'unit'),
         ('TC_U_DPH_016_ApplyDbTimeout_ClosesConnection', 'unit'),
         ('TC_U_DPH_017_MaxBatchesCap', 'unit'),
         ('TC_U_DPH_018_MaxBatchesUnlimited', 'unit'),
         ('TC_U_DPH_019_HandlePassesMaxBatches', 'unit')])

    inject_file('test_device_name_cache_v061.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestGetDeviceNameBySnHit', 'unit'),
         ('TestGetDeviceNameBySnMiss', 'unit'),
         ('TestTtlExpiry', 'unit'),
         ('TestInvalidateCache', 'unit'),
         ('TestLoadCacheExceptionSafety', 'unit')])

    inject_file('test_connection_status_cache_coherence_v058.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestCacheCoherenceFixV058', 'unit'),
         ('TestCacheCoherenceLoggingV058', 'unit')])

    inject_no_django_test_import('test_waitress_config_v052.py',
        [('TestWaitressConfigEnvironmentVariables', 'unit'),
         ('TestWaitressConfigServeCallSignature', 'unit'),
         ('TestWaitressConfigM3NoChange', 'unit')])

    inject_file('test_daily_usage_calculator.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TC01_NextDayInitialEnergyWritten', 'unit'),
         ('TC02_TodayRunDoesNotCreateTomorrowRecord', 'unit'),
         ('TC03_UsageQuantityCalculation', 'unit'),
         ('TC04_TodayRecordCreatedWithZeroUsage', 'unit'),
         ('TC05_IdempotencyForToday', 'unit'),
         ('TC06_ExistingNextDayInitialEnergyNotOverwritten', 'unit'),
         ('TC07_HourlyScheduleRegistered', 'unit')])

    inject_file('test_redis_cache_pretest.py',
        ('from django.test import TestCase, RequestFactory, override_settings',
         'from django.test import TestCase, RequestFactory, override_settings, tag'),
        [('DummyCacheBaselineTest', 'unit')])

    # ── Group A: @tag('integration') pure files ───────────────────────────
    inject_file('test_device_settings_integration.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('GetParamsTests', 'integration'),
         ('PostWriteTests', 'integration'),
         ('GetRecordsTests', 'integration')])

    inject_file('test_condensation_v070_integration.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('HandleMessageIntegrationTest', 'integration'),
         ('CondensationAPITest', 'integration')])

    inject_file('test_fault_mgmt_v064_integration.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestMigration0028Backfill', 'integration'),
         ('TestFaultConsumerWritePath', 'integration'),
         ('TestFaultEventRoomNameFilter', 'integration'),
         ('TestKeyRegressionScenarios', 'integration')])

    # CORRECTED import (actual file imports TestCase, TransactionTestCase, override_settings)
    inject_file('test_openclaw_integration.py',
        ('from django.test import TestCase, TransactionTestCase, override_settings',
         'from django.test import TestCase, TransactionTestCase, override_settings, tag'),
        [('TestChatConsumerIntegration', 'integration')])

    inject_file('test_inspection_ondemand_v130.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('AuditDoubleWriteTest', 'integration'),
         ('TriggerApiTest', 'integration'),
         ('StatusApiTest', 'integration'),
         ('LogsApiTest', 'integration'),
         ('RunThreadTest', 'integration')])

    inject_file('test_workorder_v131.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('CreateWorkOrderProposalTest', 'integration'),
         ('ListDetailTest', 'integration'),
         ('ApproveWriteTest', 'integration'),
         ('ResolveTest', 'integration')])

    inject_file('test_memory_views.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('MyMemoryViewGetTest', 'integration'),
         ('MyMemoryViewDeleteTest', 'integration'),
         ('AdminMemoryViewGetTest', 'integration'),
         ('AdminMemoryViewDeleteTest', 'integration')])

    inject_file('test_memory_consumer_v13.py',
        ('from django.test import TransactionTestCase', 'from django.test import TransactionTestCase, tag'),
        [('ConsumerSessionCreationTest', 'integration'),
         ('ConsumerMessageWriteTest', 'integration'),
         ('ConsumerHistoryInjectionTest', 'integration'),
         ('ConsumerCrossUserIsolationTest', 'integration'),
         ('ConsumerDegradationTest', 'integration'),
         ('ConsumerInjectTurnsZeroTest', 'integration'),
         ('ConsumerReasoningStreamRegressionTest', 'integration')])

    inject_file('test_reasoning_stream.py',
        ('from django.test import TestCase, TransactionTestCase',
         'from django.test import TestCase, TransactionTestCase, tag'),
        [('ChatConsumerReasoningProtocolTest', 'integration'),
         ('ChatConsumerNoReasoningCompatTest', 'integration'),
         ('AdapterDeltaParseLogicTest', 'integration'),
         ('AdapterBuildChatSendFrameTest', 'integration'),
         ('AdapterReasoningEffortWarningTest', 'integration'),
         ('AdapterGetConfigReasoningEffortTest', 'integration'),
         ('AdapterToWsUrlTest', 'integration'),
         ('AdapterStatLogTest', 'integration'),
         ('ChatConsumerEdgeCasesTest', 'integration')])

    inject_file('test_device_tree_sync_lock_fix.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('SingleOwnerSyncTest', 'integration'),
         ('ConcurrentSyncLockTest', 'integration'),
         ('AttrDefFallbackTest', 'integration')])

    inject_file('test_fault_event_serializer_v061.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestSerializerNewFieldsPresent', 'integration'),
         ('TestSerializerMainPath', 'integration'),
         ('TestSerializerFallbackOne', 'integration'),
         ('TestSerializerFallbackTwo', 'integration'),
         ('TestSerializerEdgeCases', 'integration')])

    inject_file('test_owner_sprint2.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('DeviceListPageSizeTest', 'integration'),
         ('OwnerRoomCountTest', 'integration'),
         ('OwnerDeviceTreeAPITest', 'integration'),
         ('OwnerBatchSyncTest', 'integration'),
         ('OwnerIntegrationTest', 'integration')])

    # CORRECTED import (actual file imports TestCase, Client)
    inject_file('test_csrf_relogin.py',
        ('from django.test import TestCase, Client', 'from django.test import TestCase, Client, tag'),
        [('GetCSRFTokenEndpointTest', 'integration'),
         ('LoginLogoutLoginFlowTest', 'integration'),
         ('CSRFEnforcedLoginLogoutTest', 'integration'),
         ('TokenRotationAfterLoginTest', 'integration'),
         ('SessionAuthCSRFRegressionTest', 'integration')])

    inject_file('test_v100_dashboard_redesign.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('DeviceListCondensationFieldTest', 'integration'),
         ('FaultSummaryAPITest', 'integration'),
         ('DeviceFaultSummaryAPITest', 'integration'),
         ('NewAPIAuthTest', 'integration')])

    # ── Group A: @tag('e2e') pure files ───────────────────────────────────
    inject_file('test_condensation_v070_e2e.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('US01PersistenceE2ETest', 'e2e'),
         ('APIFilterE2ETest', 'e2e'),
         ('CleanupE2ETest', 'e2e'),
         ('FrontendColumnCheckE2ETest', 'e2e')])

    inject_file('test_device_settings_e2e.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('E2EHappyPathTest', 'e2e'),
         ('E2EPLCWriteFailTest', 'e2e'),
         ('E2EMQTTUnreachableTest', 'e2e'),
         ('E2EIdempotentAckTest', 'e2e')])

    # ── Group B: mixed files (per-class) ──────────────────────────────────
    inject_file('test_main.py',
        ('from django.test import TestCase, Client', 'from django.test import TestCase, Client, tag'),
        [('CustomUserModelTest', 'unit'),
         ('PLCDataModelTest', 'unit'),
         ('UsageQuantityDailyModelTest', 'unit'),
         ('UsageQuantityMonthlyModelTest', 'unit'),
         ('PLCConnectionStatusModelTest', 'unit'),
         ('PLCStatusChangeHistoryModelTest', 'unit'),
         ('OwnerInfoUniqueIdTest', 'unit'),
         ('ParseSpecificPartTest', 'unit'),
         ('DailyUsageCalculatorTest', 'unit'),
         ('MonthlyUsageCalculatorTest', 'unit'),
         ('PLCDataCleanerTest', 'unit'),
         ('PLCDataHandlerTest', 'unit'),
         ('ConnectionStatusHandlerTest', 'unit'),
         ('HealthCheckAPITest', 'integration'),
         ('AuthAPITest', 'integration'),
         ('ChangePasswordAPITest', 'integration'),
         ('UserManagementAPITest', 'integration'),
         ('UsageQuantityAPITest', 'integration'),
         ('UsageQuantitySpecificTimePeriodAPITest', 'integration'),
         ('UsageQuantityMonthlyAPITest', 'integration'),
         ('PLCConnectionStatusAPITest', 'integration'),
         ('BillingAPITest', 'integration'),
         ('UserRegisterAPITest', 'integration'),
         ('DashboardTotalEnergyAPITest', 'integration'),
         ('DashboardSummaryAPITest', 'integration'),
         ('DashboardPLCOnlineRateAPITest', 'integration'),
         ('DashboardTrendAPITest', 'integration'),
         ('DashboardServicesAPITest', 'integration'),
         ('DashboardActivitiesAPITest', 'integration'),
         ('CSRFTokenAPITest', 'integration'),
         ('UserDetailAPITest', 'integration'),
         ('PLCStatusHistoryPaginationTest', 'integration'),
         ('UsageQuantityMonthlyFilterTest', 'integration'),
         ('IntegrationTestPLCToUsagePipeline', 'integration'),
         ('IntegrationTestUserLifecycle', 'integration'),
         ('IntegrationTestPLCStatusFlow', 'integration'),
         ('IntegrationTestBillingCalculation', 'integration'),
         ('E2ETestAuthProtection', 'e2e'),
         ('E2ETestBillingFlow', 'e2e'),
         ('E2ETestPaginationConsistency', 'e2e'),
         ('E2ETestFilterCombinations', 'e2e'),
         ('E2ETestPLCStatisticsConsistency', 'e2e'),
         ('IntegrationTestManagementCommands', 'integration'),
         ('DphCleanupServiceWhitelistTest', 'unit')])

    inject_file('test_device_management.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TC_U_001_ScreenConnectivityStatusModel', 'unit'),
         ('TC_U_002_ScreenConnectivityHandler', 'unit'),
         ('TC_U_003_ScreenConnectivityChecker', 'unit'),
         ('TC_U_004_DeviceListViewFiltering', 'unit'),
         ('TC_I_001_DeviceListAPIAuth', 'integration'),
         ('TC_I_002_DeviceListAPIResponseSchema', 'integration'),
         ('TC_I_003_DeviceListAPIScreenStatusValues', 'integration'),
         ('TC_I_004_DeviceListAPISystemSwitch', 'integration'),
         ('TC_I_005_DeviceListAPIPagination', 'integration'),
         ('TC_I_006_MQTTHandlerIntegration', 'integration'),
         ('TC_E2E_US001_NavigationStructure', 'e2e'),
         ('TC_E2E_US002_DisplayAllDevices', 'e2e'),
         ('TC_E2E_US003_RoomNumberFilter', 'e2e'),
         ('TC_E2E_US004_ScreenStatusFilter', 'e2e'),
         ('TC_E2E_US005_SystemSwitchFilter', 'e2e'),
         ('TC_E2E_US006_ScreenStatusPipelineIntegration', 'e2e'),
         ('TC_E2E_US007_DevicePanelEntry', 'e2e'),
         ('TC_E2E_NFR_Performance', 'e2e'),
         ('TC_I_007_DeviceListAPIPlcStatusFields', 'integration'),
         ('TC_I_008_DeviceListAPIPlcStatusFilter', 'integration'),
         ('TC_I_009_PlcStatusUnknownDegradation', 'integration'),
         ('TC_I_010_OperationModeField', 'integration'),
         ('TC_E2E_US103_OperationModeColumn', 'e2e'),
         ('TC_I_011_RoomNoFilterBuildingUnit', 'integration'),
         ('TC_I_012_OperationModeFilter', 'integration')])

    inject_file('test_service_management.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TC_U_SM_001_WhitelistConstants', 'unit'),
         ('TC_U_SM_002_GetServiceStatus', 'unit'),
         ('TC_U_SM_003_GetServiceDetail', 'unit'),
         ('TC_I_SM_001_ServiceListAPIAuth', 'integration'),
         ('TC_I_SM_002_ServiceListAPIResponse', 'integration'),
         ('TC_I_SM_003_ServiceDetailAPI', 'integration'),
         ('TC_I_SM_004_ServiceActionAPI', 'integration'),
         ('TC_I_SM_005_SecurityInjection', 'integration'),
         ('TC_E2E_SM_US001_ServiceList', 'e2e'),
         ('TC_E2E_SM_US002_ServiceDetail', 'e2e'),
         ('TC_E2E_SM_US003_ServiceAction', 'e2e'),
         ('TC_E2E_SM_NFR_AdminOnlyWrite', 'e2e')])

    inject_file('test_device_settings_v050.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('IsWritableV050Tests', 'unit'),
         ('ParamValueLabelTests', 'unit'),
         ('SeedDeviceConfigIdempotencyTests', 'unit'),
         ('ReqFunc001SystemSwitchTests', 'integration'),
         ('ReqFunc002OperationModeTests', 'integration'),
         ('ReqFunc003AwayEnergySavingTests', 'integration'),
         ('ReqFunc004DirtyFieldsTests', 'integration'),
         ('RegressionProtectionTests', 'integration'),
         ('FR001InputNumberUndefinedTests', 'integration'),
         ('V051ModeEnumAlignmentTests', 'integration'),
         ('V051CentralEnergySupplyWriteTests', 'integration'),
         ('SerializerV050CompatibilityTests', 'integration'),
         ('FR001HotfixVerificationTests', 'integration')])

    inject_file('test_service_registry_v120.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('WhitelistCompletenessTest', 'unit'),
         ('GetServiceEnabledTest', 'unit'),
         ('DashboardServicesEnabledTest', 'integration')])

    inject_file('test_device_cards.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestDeviceConfigModel', 'unit'),
         ('TestDeviceParamHistoryModel', 'unit'),
         ('TestDeviceRealtimeParamsAPI', 'integration'),
         ('TestDeviceParamHistoryAPI', 'integration')])

    inject_file('test_plc_latest.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestPLCLatestDataHandlerBasic', 'unit'),
         ('TestHistoryHourlyDedup', 'unit'),
         ('TestPLCLatestDataAPI', 'integration')])

    inject_file('test_screen_heartbeat.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('OnMessageTest', 'unit'),
         ('OnlineStatusTest', 'unit'),
         ('MacCacheTest', 'unit'),
         ('MigrationFieldTest', 'unit'),
         ('DeviceListAPITest', 'integration')])

    inject_file('test_owner.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('OwnerInfoModelTest', 'unit'),
         ('OwnerInfoSerializerTest', 'unit'),
         ('OwnerAPITest', 'integration'),
         ('ImportAllOwnersCommandTest', 'integration')])

    inject_file('test_heartbeat_broker_config.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestReadHbcConfig', 'unit'),
         ('TestWriteHbcConfig', 'unit'),
         ('TestHostPatternValidation', 'unit'),
         ('TestPasswordPreservation', 'unit'),
         ('TestRestartService', 'unit'),
         ('TestLoadHeartbeatConfig', 'unit'),
         ('TestHeartbeatBrokerConfigGetAPI', 'integration'),
         ('TestHeartbeatBrokerConfigPutMqttAPI', 'integration'),
         ('TestHeartbeatBrokerConfigPutWssAPI', 'integration'),
         ('TestHeartbeatBrokerConfigRestartIntegration', 'integration'),
         ('TestLegacyMqttCompatibility', 'integration')])

    inject_file('test_connection_status_lock_opt_v055.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestConnectionStatusLockOpt', 'unit'),
         ('TestConnectionStatusHandleIntegration', 'integration')])

    inject_file('test_device_list_fault_filter.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        [('TestFaultStatusFilterLogicUnit', 'unit'),
         ('TestFaultStatusFilterIntegration', 'integration'),
         ('TestFaultStatusFilterE2E', 'e2e')])

    inject_file('test_room_filter_v057.py',
        ('from django.test import TestCase', 'from django.test import TestCase, tag'),
        # RoomFilterTestBase is intentionally NOT tagged: it is a shared base for
        # both unit and integration subclasses; a tag would propagate via
        # inheritance and double-count those subclasses across layers.
        [('TestMatchPanelSubTypes', 'unit'),
         ('TestGetAvailableSubTypes', 'unit'),
         ('TestGetPanelParamBlocklist', 'unit'),
         ('TestPLCLatestDataHandlerRoomFilter', 'unit'),
         ('TestOndemandCollectSubscriberAllowedParams', 'unit'),
         ('TestGetDeviceRealtimeParamsWithRoomFilter', 'integration'),
         ('TestDeviceSettingsParamsWithRoomFilter', 'integration'),
         ('TestDeviceTreeSyncCacheInvalidation', 'integration'),
         ('TestOndemandRefreshAllowedParamsInjection', 'integration'),
         ('TestEdgeCases', 'integration')])

    inject_file('test_dashboard_power_status_v053.py',
        ('from django.test import TestCase, RequestFactory',
         'from django.test import TestCase, RequestFactory, tag'),
        [('TestPowerStatusBasic', 'integration'),
         ('TestPowerStatusModeDistribution', 'integration'),
         ('TestPowerStatusUnknownMode', 'integration'),
         ('TestPowerStatusBoundaries', 'integration'),
         ('TestPowerStatusResponseStructure', 'integration'),
         ('TestPowerStatusQueryCount', 'integration'),
         ('TestPowerStatusURL', 'integration'),
         ('TestFrontendCodeReview', 'integration')])


if __name__ == '__main__':
    run_injections()
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
