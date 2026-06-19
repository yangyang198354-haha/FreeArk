"""
test_inspection_workorder_v110.py — v1.1.0-AIA（方案 B）增量① 单元测试

覆盖范围（地基：migration 0033 + 模型）：
  UT-MIG-001   migration 0033 在 SQLite 可无误 apply（测试框架 setup 隐式验证）
  UT-SCHEMA-001 fault_event 新增 inspection_status / inspection_started_at 列
  UT-SCHEMA-002 condensation_warning_event 新增同样两列
  UT-SCHEMA-003 inspection_work_order 表存在且列完整
  UT-DEFAULT-001 FaultEvent.inspection_status 默认 PENDING、started_at 为 None
  UT-DEFAULT-002 CondensationWarningEvent 同上
  UT-WO-001    WorkOrder 创建 + __str__
  UT-WO-002    条件唯一约束：同一来源事件第二条活跃工单(OPEN/IN_PROGRESS)→ IntegrityError
  UT-WO-003    第一条置为 RESOLVED 后，同来源事件可再建活跃工单（非活跃不计入约束）
  UT-WO-004    不同来源事件各自的活跃工单互不冲突

注：全项目 makemigrations --check 会因既有历史漂移（TD-MIGRATION-001：若干模型索引
    重命名 + id AutoField→BigAutoField）误报，与本增量无关；此处沿用 v0.7.0 UT-MM-001
    做法，用 PRAGMA table_info 直接核验本增量涉及的表/列与迁移一致。

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_inspection_workorder_v110 \\
        --settings=freearkweb.test_settings --verbosity=2
"""

from django.db import IntegrityError, connection, transaction
from django.test import TestCase, tag
from django.utils import timezone

from api.models import FaultEvent, CondensationWarningEvent, WorkOrder


def _make_fault_event(**overrides):
    now = timezone.now()
    defaults = dict(
        specific_part='3-1-7-702',
        device_sn='SN-FAULT-001',
        product_code='PC-001',
        fault_code='E101',
        fault_type='comm',
        fault_message='通信中断',
        severity='error',
        first_seen_at=now,
        last_seen_at=now,
    )
    defaults.update(overrides)
    return FaultEvent.objects.create(**defaults)


def _make_cw_event(**overrides):
    now = timezone.now()
    defaults = dict(
        specific_part='3-1-7-702',
        device_sn='SN-CW-001',
        product_code='PC-001',
        first_seen_at=now,
        last_seen_at=now,
    )
    defaults.update(overrides)
    return CondensationWarningEvent.objects.create(**defaults)


def _make_work_order(ticket_id, source_event_type='fault_event',
                     source_event_id=1, status='OPEN', **overrides):
    defaults = dict(
        ticket_id=ticket_id,
        severity='warning',
        source_event_type=source_event_type,
        source_event_id=source_event_id,
        affected_device='SN-FAULT-001 / 3-1-7-702',
        symptom='通信中断',
        status=status,
    )
    defaults.update(overrides)
    return WorkOrder.objects.create(**defaults)


def _columns(table_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM pragma_table_info(%s)", [table_name])
        return {row[0] for row in cursor.fetchall()}


@tag('unit')
class SchemaTest(TestCase):
    """UT-SCHEMA-*: migration 0033 在 SQLite 应用后表/列符合预期。"""

    def test_fault_event_has_inspection_columns(self):
        cols = _columns(FaultEvent._meta.db_table)
        self.assertIn('inspection_status', cols)
        self.assertIn('inspection_started_at', cols)

    def test_cw_event_has_inspection_columns(self):
        cols = _columns(CondensationWarningEvent._meta.db_table)
        self.assertIn('inspection_status', cols)
        self.assertIn('inspection_started_at', cols)

    def test_work_order_table_columns(self):
        cols = _columns(WorkOrder._meta.db_table)
        expected = {
            'id', 'ticket_id', 'severity', 'source_event_type', 'source_event_id',
            'affected_device', 'symptom', 'diagnosis', 'recommended_action',
            'status', 'created_at', 'updated_at', 'resolved_at', 'resolved_by',
        }
        self.assertTrue(expected.issubset(cols),
                        f"缺列: {expected - cols}")


@tag('unit')
class InspectionStatusDefaultTest(TestCase):
    """UT-DEFAULT-*: 新字段默认值正确（自治巡检初始态 PENDING）。"""

    def test_fault_event_default_pending(self):
        fe = _make_fault_event()
        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'PENDING')
        self.assertIsNone(fe.inspection_started_at)

    def test_cw_event_default_pending(self):
        cw = _make_cw_event()
        cw.refresh_from_db()
        self.assertEqual(cw.inspection_status, 'PENDING')
        self.assertIsNone(cw.inspection_started_at)


@tag('unit')
class WorkOrderModelTest(TestCase):
    """UT-WO-*: WorkOrder 基本行为与防重复建单约束。"""

    def test_create_and_str(self):
        wo = _make_work_order('WO-20260615-000001')
        self.assertEqual(wo.status, 'OPEN')
        self.assertEqual(wo.diagnosis, '')          # blank 默认空串
        self.assertIsNone(wo.resolved_at)
        self.assertIn('WO-20260615-000001', str(wo))
        self.assertIn('OPEN', str(wo))

    def test_duplicate_active_workorder_blocked(self):
        # UT-WO-002: 同一来源事件第二条活跃工单触发条件唯一约束
        _make_work_order('WO-20260615-000001',
                         source_event_type='fault_event', source_event_id=42)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _make_work_order('WO-20260615-000002',
                                 source_event_type='fault_event', source_event_id=42)

    def test_inactive_workorder_not_counted(self):
        # UT-WO-003: 第一条置 RESOLVED 后，同来源事件可再建活跃工单
        wo1 = _make_work_order('WO-20260615-000001',
                               source_event_type='fault_event', source_event_id=42)
        wo1.status = 'RESOLVED'
        wo1.resolved_at = timezone.now()
        wo1.save(update_fields=['status', 'resolved_at', 'updated_at'])
        # 不应抛异常
        wo2 = _make_work_order('WO-20260615-000003',
                               source_event_type='fault_event', source_event_id=42)
        self.assertEqual(wo2.status, 'OPEN')

    def test_different_events_independent(self):
        # UT-WO-004: 不同来源事件（不同 id 或不同 type）的活跃工单互不冲突
        _make_work_order('WO-A', source_event_type='fault_event', source_event_id=1)
        _make_work_order('WO-B', source_event_type='fault_event', source_event_id=2)
        _make_work_order('WO-C', source_event_type='condensation_warning_event',
                         source_event_id=1)
        self.assertEqual(WorkOrder.objects.filter(status='OPEN').count(), 3)
