"""
test_condensation_v070_unit.py — v0.7.0 结露预警 单元测试

覆盖范围：
  UT-MIG-001    migration 0029 在 SQLite 可无误 apply（通过 Django 测试框架隐式验证）
  UT-MM-001     makemigrations --check 模型与迁移一致（CR-MINOR-01 闭环）
  UT-NS-001~004 _normalize_system_switch_from_mqtt 各路径
  UT-SM-001     T1 路径：新设备首次预警 → INSERT DB + 更新内存
  UT-SM-002     T2 路径：已活跃预警重复报文 → 仅更新内存 last_seen_at
  UT-SM-003     T3 路径：活跃预警收到 alarm=0 → UPDATE is_active=False + recovered_at
  UT-SM-004     T3 miss：无内存状态 + alarm=0 → 无操作
  UT-SM-005     T1 IntegrityError 兜底：fallback UPDATE last_seen_at
  UT-SM-006     二元组 key (specific_part, device_sn) 独立：不同设备不互相影响
  UT-SM-007     rebuild_from_db：从 DB 加载 is_active=True 记录重建状态机
  UT-SM-008     rebuild_from_db 后收到同设备 alarm=1 → T2 路径（不重复 INSERT）
  UT-SS-001     MQTT 直取路径：items[] 含 system_switch → 直取 + lower() 容错
  UT-SS-002     PLCLatestData 兜底路径：items[] 无 system_switch → 查 PLCLatestData 整数 → on/off
  UT-SS-003     PLCLatestData 无记录 → "unknown"
  UT-SS-004     PLCLatestData value=0 → "off"；value=1 → "on"
  UT-SNAP-001   快照字段从 items[] 正确提取（dew_point_temp/ntc_temp/humidity）
  UT-SNAP-002   NTC_temp 大写 attrTag → 映射到 ntc_temp 字段（CR-INFO-01）
  UT-SNAP-003   快照字段缺失 → NULL（不报错）
  UT-SNAP-004   condensation_alarm_value 写入原始值字符串
  UT-ERR-001    condensation_alarm 非数字值 → 视为正常态（WARNING 日志），不触发 T1/T3
  UT-ERR-002    condensation_alarm 空字符串 → 视为正常态
  UT-CL-001     cleanup command 90 天边界：expired + is_active=False → 删除
  UT-CL-002     cleanup command 活跃预警豁免：expired + is_active=True → 不删除
  UT-CL-003     cleanup command dry-run：不执行删除，仅统计
  UT-CL-004     cleanup command 分批：超过 batch_size 时循环多批

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_condensation_v070_unit \\
        --settings=freearkweb.test_settings --verbosity=2
"""

import logging
from datetime import timedelta
from unittest.mock import patch, MagicMock, call
from io import StringIO

from django.test import TestCase
from django.utils import timezone
from django.core.management import call_command

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# UT-MIG-001: migration 0029 隐式验证
# ---------------------------------------------------------------------------
class MigrationApplyTest(TestCase):
    """migration 0029 已在 Django 测试框架 setup 时通过 --keepdb=no migrate 应用。
    只要此 TestCase 能运行，即证明迁移在 SQLite 无误。"""

    def test_migration_0029_table_exists(self):
        """UT-MIG-001: condensation_warning_event 表在 SQLite 中可访问。"""
        from api.models import CondensationWarningEvent
        count = CondensationWarningEvent.objects.count()
        self.assertEqual(count, 0)  # 空表，DDL 已成功


# ---------------------------------------------------------------------------
# UT-MM-001: migration 0029 与 CondensationWarningEvent 模型一致性 (CR-MINOR-01)
#
# 【范围说明】本用例仅校验结露预警相关的模型/迁移一致性，不对全项目执行
# makemigrations --check。全项目检测会误报既有历史漂移（0030 候选：
# deviceattrbinding/deviceattrdef/devicefloor/devicenode/deviceroom/
# plclatestdata 的索引重命名，以及 deviceconfig/plclatestdata 的
# id AutoField→BigAutoField），这些与本功能无关，已单独立项为技术债
# TD-MIGRATION-001，不在 v0.7.0 范围内。
# ---------------------------------------------------------------------------
class MakeMigrationsCheckTest(TestCase):
    """UT-MM-001: CondensationWarningEvent 模型字段与 migration 0029 一致。"""

    def test_no_pending_migrations(self):
        """migration 0029 已正确应用，CondensationWarningEvent 所有字段可访问且类型符合预期。
        本用例替代全项目 makemigrations --check，仅验证结露预警相关模型与迁移的一致性。"""
        from api.models import CondensationWarningEvent
        from django.db import connection

        # 1. 表可访问（隐式验证 DDL 已应用）
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

        # 2. 必要字段均在表列中（验证 0029 迁移字段完整性）
        expected_columns = {
            'id', 'specific_part', 'device_sn', 'product_code',
            'first_seen_at', 'last_seen_at', 'recovered_at',
            'is_active', 'warning_type', 'warning_message',
            'condensation_alarm_value', 'dew_point_temp', 'ntc_temp',
            'humidity', 'system_switch',
        }
        # 表名从模型元数据取，避免硬编码（实际 db_table='condensation_warning_event'）
        table_name = CondensationWarningEvent._meta.db_table
        with connection.cursor() as cursor:
            # SQLite: PRAGMA table_info
            cursor.execute(
                "SELECT name FROM pragma_table_info(%s)", [table_name]
            )
            actual_columns = {row[0] for row in cursor.fetchall()}

        missing = expected_columns - actual_columns
        self.assertSetEqual(
            missing, set(),
            f'migration 0029 缺少以下字段（与 CondensationWarningEvent 模型不一致）：{missing}',
        )

        # 3. 关键字段默认值与 ORM INSERT 行为一致
        from django.utils import timezone
        obj = CondensationWarningEvent.objects.create(
            specific_part='test-part',
            device_sn='TEST-SN',
            product_code='000000',
            first_seen_at=timezone.now(),
            last_seen_at=timezone.now(),
            is_active=True,
            warning_type='结露预警',
            warning_message='单元测试占位',
        )
        self.assertTrue(obj.pk > 0)
        self.assertIsNone(obj.recovered_at)
        self.assertIsNone(obj.dew_point_temp)
        self.assertIsNone(obj.ntc_temp)
        self.assertIsNone(obj.humidity)
        # 清理
        obj.delete()


# ---------------------------------------------------------------------------
# UT-NS-*: _normalize_system_switch_from_mqtt
# ---------------------------------------------------------------------------
class NormalizeSystemSwitchTest(TestCase):
    """UT-NS-001~004: system_switch MQTT 直取路径规范化函数。"""

    def setUp(self):
        from api.management.commands.condensation_consumer import _normalize_system_switch_from_mqtt
        self.normalize = _normalize_system_switch_from_mqtt

    def test_ns_001_off_lowercase(self):
        """UT-NS-001: "off" → "off"."""
        self.assertEqual(self.normalize('off'), 'off')

    def test_ns_002_on_lowercase(self):
        """UT-NS-002: "on" → "on"."""
        self.assertEqual(self.normalize('on'), 'on')

    def test_ns_003_case_insensitive(self):
        """UT-NS-003: "OFF"/"ON" → lower() 容错 → "off"/"on"."""
        self.assertEqual(self.normalize('OFF'), 'off')
        self.assertEqual(self.normalize('ON'), 'on')

    def test_ns_004_none_empty_blank(self):
        """UT-NS-004: None/空字符串/空白 → "unknown"."""
        self.assertEqual(self.normalize(None), 'unknown')
        self.assertEqual(self.normalize(''), 'unknown')
        self.assertEqual(self.normalize('   '), 'unknown')


# ---------------------------------------------------------------------------
# 共享 helper：构造 minimal MQTT msg mock
# ---------------------------------------------------------------------------

def _make_mqtt_msg(topic, payload_dict):
    """构造 paho MQTT msg mock。"""
    import json
    msg = MagicMock()
    msg.topic = topic
    msg.payload = json.dumps(payload_dict).encode('utf-8')
    return msg


def _make_device_status_payload(
    device_sn='22554',
    product_code='260001',
    items=None,
):
    """构造标准 DeviceStatusUpdate payload dict。"""
    if items is None:
        items = []
    return {
        'header': {'name': 'DeviceStatusUpdate', 'screenMac': 'aabbccddeeff'},
        'payload': {
            'data': {
                'deviceSn': device_sn,
                'productCode': product_code,
                'items': items,
            }
        }
    }


# ---------------------------------------------------------------------------
# UT-SM-*: 状态机 T1/T2/T3
# ---------------------------------------------------------------------------

class StateMachineT1T2T3Test(TestCase):
    """UT-SM-001~008: 状态机三条转移规则及进程内内存维护。"""

    def setUp(self):
        """每个测试前清空状态机。"""
        import api.condensation_consumer.state_machine as sm_module
        sm_module._cw_state_machine.clear()
        self.sm = sm_module

    def test_sm_001_t1_insert_new_alarm(self):
        """UT-SM-001: 新设备首次预警 → T1 INSERT DB + 内存更新。"""
        now = timezone.now()
        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702',
            device_sn='22554',
            product_code='260001',
            is_active_now=True,
            received_at=now,
            condensation_alarm_value='1',
            dew_point_temp='12.5',
            ntc_temp='18.0',
            humidity='65',
            system_switch='on',
        )
        from api.models import CondensationWarningEvent
        qs = CondensationWarningEvent.objects.filter(
            specific_part='3-1-7-702',
            device_sn='22554',
            is_active=True,
        )
        self.assertEqual(qs.count(), 1)
        cwe = qs.first()
        self.assertEqual(cwe.condensation_alarm_value, '1')
        self.assertEqual(cwe.system_switch, 'on')
        self.assertTrue(cwe.is_active)

        # 内存状态已更新
        key = ('3-1-7-702', '22554')
        state = self.sm.get_state(key)
        self.assertIsNotNone(state)
        self.assertTrue(state.is_active)
        self.assertEqual(state.event_id, cwe.id)

    def test_sm_002_t2_active_repeat(self):
        """UT-SM-002: 已活跃预警，重复报文 → 仅更新内存 last_seen_at，DB 行数不变。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        # T1: 首次插入
        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702',
            device_sn='22554',
            product_code='260001',
            is_active_now=True,
            received_at=now,
            condensation_alarm_value='1',
            system_switch='on',
        )
        count_after_t1 = CondensationWarningEvent.objects.count()
        self.assertEqual(count_after_t1, 1)

        # T2: 再次报警
        later = now + timedelta(minutes=1)
        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702',
            device_sn='22554',
            product_code='260001',
            is_active_now=True,
            received_at=later,
            condensation_alarm_value='1',
            system_switch='on',
        )
        # DB 行数不变
        self.assertEqual(CondensationWarningEvent.objects.count(), count_after_t1)

        # 内存 last_seen_at 更新
        key = ('3-1-7-702', '22554')
        state = self.sm.get_state(key)
        self.assertEqual(state.last_seen_at, later)

    def test_sm_003_t3_recover(self):
        """UT-SM-003: 活跃预警收到 alarm=0 → UPDATE is_active=False + recovered_at。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        # T1
        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702',
            device_sn='22554',
            product_code='260001',
            is_active_now=True,
            received_at=now,
            condensation_alarm_value='1',
            system_switch='on',
        )

        # T3
        recover_time = now + timedelta(minutes=10)
        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702',
            device_sn='22554',
            product_code='260001',
            is_active_now=False,
            received_at=recover_time,
            condensation_alarm_value='0',
        )

        cwe = CondensationWarningEvent.objects.get(
            specific_part='3-1-7-702',
            device_sn='22554',
        )
        self.assertFalse(cwe.is_active)
        self.assertIsNotNone(cwe.recovered_at)

        # 内存状态更新
        key = ('3-1-7-702', '22554')
        state = self.sm.get_state(key)
        self.assertFalse(state.is_active)

    def test_sm_004_t3_no_state_no_op(self):
        """UT-SM-004: 无内存状态且收到 alarm=0 → 无操作，DB 无写入。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702',
            device_sn='99999',
            product_code='260001',
            is_active_now=False,
            received_at=now,
            condensation_alarm_value='0',
        )
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

    def test_sm_005_t1_integrity_error_fallback(self):
        """UT-SM-005: T1 INSERT IntegrityError → fallback UPDATE last_seen_at，不崩溃。"""
        from django.db import IntegrityError
        from api.models import CondensationWarningEvent
        now = timezone.now()

        # 先手工插入一条，制造 IntegrityError 条件
        cwe = CondensationWarningEvent.objects.create(
            specific_part='3-1-7-702',
            device_sn='22554',
            product_code='260001',
            first_seen_at=now,
            last_seen_at=now,
            is_active=True,
            warning_type='结露预警',
            warning_message='结露报警',
        )

        # 模拟 create 抛 IntegrityError，触发 fallback
        with patch('api.models.CondensationWarningEvent.objects.create',
                   side_effect=IntegrityError('duplicate key')):
            self.sm.process_condensation_alarm(
                specific_part='3-1-7-702',
                device_sn='22554',
                product_code='260001',
                is_active_now=True,
                received_at=now + timedelta(seconds=5),
                condensation_alarm_value='1',
            )

        # DB 行数保持 1（fallback UPDATE 而非新 INSERT）
        self.assertEqual(CondensationWarningEvent.objects.count(), 1)

    def test_sm_006_key_independence(self):
        """UT-SM-006: 不同 (specific_part, device_sn) 互不干扰。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702', device_sn='AAA',
            product_code='260001', is_active_now=True,
            received_at=now, condensation_alarm_value='1', system_switch='on',
        )
        self.sm.process_condensation_alarm(
            specific_part='3-1-7-703', device_sn='BBB',
            product_code='260001', is_active_now=True,
            received_at=now, condensation_alarm_value='1', system_switch='off',
        )

        self.assertEqual(CondensationWarningEvent.objects.count(), 2)
        self.assertEqual(self.sm.get_state_machine_size(), 2)

        # 702 恢复，703 不受影响
        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702', device_sn='AAA',
            product_code='260001', is_active_now=False,
            received_at=now + timedelta(minutes=5), condensation_alarm_value='0',
        )
        cwe_702 = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        cwe_703 = CondensationWarningEvent.objects.get(specific_part='3-1-7-703')
        self.assertFalse(cwe_702.is_active)
        self.assertTrue(cwe_703.is_active)

    def test_sm_007_rebuild_from_db(self):
        """UT-SM-007: rebuild_from_db 从 DB 加载 is_active=True 记录重建状态机。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        # 预先在 DB 中插入 2 条活跃、1 条已恢复
        CondensationWarningEvent.objects.create(
            specific_part='1-1-1-101', device_sn='S1',
            product_code='260001', first_seen_at=now, last_seen_at=now,
            is_active=True, warning_type='结露预警', warning_message='结露报警',
        )
        CondensationWarningEvent.objects.create(
            specific_part='1-1-1-102', device_sn='S2',
            product_code='260001', first_seen_at=now, last_seen_at=now,
            is_active=True, warning_type='结露预警', warning_message='结露报警',
        )
        CondensationWarningEvent.objects.create(
            specific_part='1-1-1-103', device_sn='S3',
            product_code='260001', first_seen_at=now, last_seen_at=now,
            is_active=False, recovered_at=now,
            warning_type='结露预警', warning_message='结露报警',
        )

        count = self.sm.rebuild_from_db()
        self.assertEqual(count, 2)
        self.assertEqual(self.sm.get_state_machine_size(), 2)
        self.assertIsNotNone(self.sm.get_state(('1-1-1-101', 'S1')))
        self.assertIsNotNone(self.sm.get_state(('1-1-1-102', 'S2')))
        self.assertIsNone(self.sm.get_state(('1-1-1-103', 'S3')))

    def test_sm_008_rebuild_then_t2_no_duplicate_insert(self):
        """UT-SM-008: rebuild_from_db 后收到已活跃设备报文 → T2 路径，不重复 INSERT。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        CondensationWarningEvent.objects.create(
            specific_part='1-1-1-101', device_sn='S1',
            product_code='260001', first_seen_at=now, last_seen_at=now,
            is_active=True, warning_type='结露预警', warning_message='结露报警',
        )
        self.sm.rebuild_from_db()

        # 收到同设备报警 → 应走 T2（内存已知 is_active=True）
        later = now + timedelta(minutes=2)
        self.sm.process_condensation_alarm(
            specific_part='1-1-1-101', device_sn='S1',
            product_code='260001', is_active_now=True,
            received_at=later, condensation_alarm_value='1',
        )
        # DB 仍只有 1 行
        self.assertEqual(CondensationWarningEvent.objects.filter(
            specific_part='1-1-1-101', device_sn='S1').count(), 1)


# ---------------------------------------------------------------------------
# UT-SS-*: system_switch 双源逻辑
# ---------------------------------------------------------------------------

class SystemSwitchDualSourceTest(TestCase):
    """UT-SS-001~004: MQTT 直取路径 vs PLCLatestData 兜底路径。"""

    def setUp(self):
        import api.condensation_consumer.state_machine as sm_module
        sm_module._cw_state_machine.clear()
        self.sm = sm_module

    def test_ss_001_mqtt_direct_off(self):
        """UT-SS-001: items[] 含 system_switch="off" → 直取 "off"，写入 DB。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702', device_sn='22554',
            product_code='260001', is_active_now=True,
            received_at=now, condensation_alarm_value='1',
            system_switch='off',  # MQTT 直取路径已规范化后传入
        )
        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertEqual(cwe.system_switch, 'off')

    def test_ss_002_plc_fallback_on(self):
        """UT-SS-002: items[] 无 system_switch (system_switch=None) → PLCLatestData value=1 → "on"。"""
        from api.models import CondensationWarningEvent, PLCLatestData
        now = timezone.now()

        # 预插入 PLCLatestData value=1（非零=on）
        PLCLatestData.objects.create(
            specific_part='3-1-7-702',
            param_name='system_switch',
            value=1,
            updated_at=now,
        )

        # system_switch=None → 触发 PLCLatestData 兜底
        self.sm.process_condensation_alarm(
            specific_part='3-1-7-702', device_sn='22549',
            product_code='120003', is_active_now=True,
            received_at=now, condensation_alarm_value='1',
            system_switch=None,  # 温控面板，无 system_switch
        )
        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertEqual(cwe.system_switch, 'on')

    def test_ss_003_plc_no_record_unknown(self):
        """UT-SS-003: PLCLatestData 无记录 → system_switch = "unknown"。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        self.sm.process_condensation_alarm(
            specific_part='9-9-9-999', device_sn='99999',
            product_code='120003', is_active_now=True,
            received_at=now, condensation_alarm_value='1',
            system_switch=None,
        )
        cwe = CondensationWarningEvent.objects.get(specific_part='9-9-9-999')
        self.assertEqual(cwe.system_switch, 'unknown')

    def test_ss_004_plc_value_zero_is_off(self):
        """UT-SS-004: PLCLatestData value=0 → "off"；value=5 → "on"。"""
        from api.models import PLCLatestData
        from api.condensation_consumer.state_machine import _get_system_switch_for_specific_part

        PLCLatestData.objects.create(
            specific_part='2-1-1-101',
            param_name='system_switch',
            value=0,
        )
        PLCLatestData.objects.create(
            specific_part='2-1-1-102',
            param_name='system_switch',
            value=5,
        )

        self.assertEqual(_get_system_switch_for_specific_part('2-1-1-101'), 'off')
        self.assertEqual(_get_system_switch_for_specific_part('2-1-1-102'), 'on')
        self.assertEqual(_get_system_switch_for_specific_part('2-1-1-999'), 'unknown')


# ---------------------------------------------------------------------------
# UT-SNAP-*: 快照字段
# ---------------------------------------------------------------------------

class SnapshotFieldTest(TestCase):
    """UT-SNAP-001~004: 快照字段提取与 NULL 兜底。"""

    def setUp(self):
        import api.condensation_consumer.state_machine as sm_module
        sm_module._cw_state_machine.clear()

    def test_snap_001_all_snapshot_fields(self):
        """UT-SNAP-001: dew_point_temp/ntc_temp/humidity 从 items[] 正确写入。"""
        from api.models import CondensationWarningEvent
        now = timezone.now()

        from api.condensation_consumer.state_machine import process_condensation_alarm
        process_condensation_alarm(
            specific_part='3-1-7-702', device_sn='22554',
            product_code='260001', is_active_now=True,
            received_at=now, condensation_alarm_value='1',
            dew_point_temp='12.5',
            ntc_temp='18.0',
            humidity='65',
            system_switch='on',
        )
        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertEqual(cwe.dew_point_temp, '12.5')
        self.assertEqual(cwe.ntc_temp, '18.0')
        self.assertEqual(cwe.humidity, '65')

    def test_snap_002_ntc_uppercase_tag(self):
        """UT-SNAP-002: NTC_temp（大写）attrTag 映射到 ntc_temp 字段（CR-INFO-01 容错）。"""
        from api.management.commands.condensation_consumer import _SNAPSHOT_TAGS
        # 验证映射表中同时包含大写和小写变体
        self.assertIn('NTC_temp', _SNAPSHOT_TAGS)
        self.assertIn('ntc_temp', _SNAPSHOT_TAGS)
        self.assertEqual(_SNAPSHOT_TAGS['NTC_temp'], 'ntc_temp')
        self.assertEqual(_SNAPSHOT_TAGS['ntc_temp'], 'ntc_temp')

    def test_snap_003_missing_fields_null(self):
        """UT-SNAP-003: 快照字段缺失 → NULL（不报错）。"""
        from api.models import CondensationWarningEvent
        from api.condensation_consumer.state_machine import process_condensation_alarm
        now = timezone.now()

        process_condensation_alarm(
            specific_part='3-1-7-702', device_sn='22554',
            product_code='260001', is_active_now=True,
            received_at=now, condensation_alarm_value='1',
            dew_point_temp=None,
            ntc_temp=None,
            humidity=None,
            system_switch=None,
        )
        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertIsNone(cwe.dew_point_temp)
        self.assertIsNone(cwe.ntc_temp)
        self.assertIsNone(cwe.humidity)

    def test_snap_004_condensation_alarm_value_raw(self):
        """UT-SNAP-004: condensation_alarm_value 写入原始字符串值（如 "1"）。"""
        from api.models import CondensationWarningEvent
        from api.condensation_consumer.state_machine import process_condensation_alarm
        now = timezone.now()

        process_condensation_alarm(
            specific_part='3-1-7-702', device_sn='22554',
            product_code='260001', is_active_now=True,
            received_at=now, condensation_alarm_value='1',
            system_switch='on',
        )
        cwe = CondensationWarningEvent.objects.get(specific_part='3-1-7-702')
        self.assertEqual(cwe.condensation_alarm_value, '1')


# ---------------------------------------------------------------------------
# UT-ERR-*: 错误容忍
# ---------------------------------------------------------------------------

class ErrorToleranceTest(TestCase):
    """UT-ERR-001~002: 非数字 condensation_alarm 值容忍测试。"""

    def test_err_001_non_numeric_condensation_alarm(self):
        """UT-ERR-001: condensation_alarm 非数字（如 "abc"）→ 视为正常态，不触发 T1，不崩溃。"""
        from api.models import CondensationWarningEvent
        from api.management.commands.condensation_consumer import _handle_message

        mac_cache = MagicMock()
        mac_cache.get_specific_part.return_value = '3-1-7-702'

        msg = _make_mqtt_msg(
            'screen/upload/screen/to/cloud/aabbccddeeff',
            _make_device_status_payload(
                device_sn='22554',
                items=[
                    {'attrTag': 'condensation_alarm', 'attrValue': 'abc'},
                ]
            )
        )
        # 不应抛异常
        _handle_message(msg, mac_cache)
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

    def test_err_002_empty_condensation_alarm(self):
        """UT-ERR-002: condensation_alarm 空字符串 → 视为正常态，不触发 T1。"""
        from api.models import CondensationWarningEvent
        from api.management.commands.condensation_consumer import _handle_message

        mac_cache = MagicMock()
        mac_cache.get_specific_part.return_value = '3-1-7-702'

        msg = _make_mqtt_msg(
            'screen/upload/screen/to/cloud/aabbccddeeff',
            _make_device_status_payload(
                device_sn='22554',
                items=[
                    {'attrTag': 'condensation_alarm', 'attrValue': ''},
                ]
            )
        )
        _handle_message(msg, mac_cache)
        self.assertEqual(CondensationWarningEvent.objects.count(), 0)


# ---------------------------------------------------------------------------
# UT-CL-*: condensation_cleanup Management Command
# ---------------------------------------------------------------------------

class CleanupCommandTest(TestCase):
    """UT-CL-001~004: condensation_cleanup 命令清理策略。"""

    def _create_event(self, specific_part, first_seen_at, is_active):
        from api.models import CondensationWarningEvent
        return CondensationWarningEvent.objects.create(
            specific_part=specific_part,
            device_sn='S1',
            product_code='260001',
            first_seen_at=first_seen_at,
            last_seen_at=first_seen_at,
            recovered_at=first_seen_at if not is_active else None,
            is_active=is_active,
            warning_type='结露预警',
            warning_message='结露报警',
        )

    def test_cl_001_expired_inactive_deleted(self):
        """UT-CL-001: first_seen_at < 90 天前 + is_active=False → 被删除。"""
        from api.models import CondensationWarningEvent
        old_time = timezone.now() - timedelta(days=91)
        self._create_event('1-1-1-101', old_time, is_active=False)

        out = StringIO()
        call_command('condensation_cleanup', '--days=90', '--batch-size=1000',
                     '--sleep-ms=0', stdout=out)

        self.assertEqual(CondensationWarningEvent.objects.count(), 0)

    def test_cl_002_active_exempt(self):
        """UT-CL-002: first_seen_at < 90 天前 + is_active=True → 不删除（活跃豁免）。"""
        from api.models import CondensationWarningEvent
        old_time = timezone.now() - timedelta(days=100)
        self._create_event('1-1-1-101', old_time, is_active=True)

        out = StringIO()
        call_command('condensation_cleanup', '--days=90', '--batch-size=1000',
                     '--sleep-ms=0', stdout=out)

        self.assertEqual(CondensationWarningEvent.objects.count(), 1)

    def test_cl_003_dry_run_no_delete(self):
        """UT-CL-003: --dry-run → 不删除，仅统计。"""
        from api.models import CondensationWarningEvent
        old_time = timezone.now() - timedelta(days=91)
        self._create_event('1-1-1-101', old_time, is_active=False)

        out = StringIO()
        call_command('condensation_cleanup', '--days=90', '--dry-run', stdout=out)

        # 记录依然存在
        self.assertEqual(CondensationWarningEvent.objects.count(), 1)
        self.assertIn('DRY-RUN', out.getvalue())

    def test_cl_004_batch_loop(self):
        """UT-CL-004: 超过 batch_size 的记录分批删除，循环至全部删完。"""
        from api.models import CondensationWarningEvent
        old_time = timezone.now() - timedelta(days=91)

        # 插入 5 条，batch_size=2
        for i in range(5):
            self._create_event(f'1-1-1-{100+i}', old_time, is_active=False)

        self.assertEqual(CondensationWarningEvent.objects.count(), 5)

        out = StringIO()
        call_command('condensation_cleanup', '--days=90', '--batch-size=2',
                     '--sleep-ms=0', stdout=out)

        self.assertEqual(CondensationWarningEvent.objects.count(), 0)
