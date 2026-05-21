"""
ConnectionStatusHandler 行锁路径优化测试套件 (v0.5.5 P2)

覆盖范围：
  - ConnectionStatusHandler._update_connection_status()：快/慢路径分离
  - _conn_status_cache 进程内缓存的命中/失效/重建行为
  - PLCStatusChangeHistory 写入不漏记
  - SQLite 测试环境下 select_for_update() 的兼容性
  - 异常处理：DB 写入失败时缓存不更新

对应设计文档：docs/requirements/v0.5.5_connection_status_lock_opt/module_design.md §2.1
用例编号 T-P2-01 ~ T-P2-08。

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_connection_status_lock_opt_v055 --verbosity=2
"""
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from api.models import PLCConnectionStatus, PLCStatusChangeHistory
from api.mqtt_handlers import ConnectionStatusHandler
import api.mqtt_handlers as _handlers_module


# ---------------------------------------------------------------------------
# 测试常量
# ---------------------------------------------------------------------------

DEV = '3-1-7-702'        # 标准测试设备
BUILDING, UNIT, ROOM = '3', '1', '702'


# ---------------------------------------------------------------------------
# 单元测试：ConnectionStatusHandler 快/慢路径
# ---------------------------------------------------------------------------

class TestConnectionStatusLockOpt(TestCase):
    """验证 v0.5.5 P2 的快/慢路径分离逻辑"""

    def setUp(self):
        # 每个用例前清空进程内缓存，避免用例间互相干扰
        _handlers_module._conn_status_cache.clear()
        self.handler = ConnectionStatusHandler()

    def _call(self, status, specific_part=DEV):
        """便捷调用 _update_connection_status。"""
        self.handler._update_connection_status(
            specific_part, status, BUILDING, UNIT, ROOM
        )

    # ------------------------------------------------------------------
    # T-P2-01：新设备首次调用（缓存 miss，created=True）
    # ------------------------------------------------------------------
    def test_p2_01_new_device_first_call(self):
        """
        Given: _conn_status_cache 为空，两张表均无该设备
        When:  调用 _update_connection_status(DEV, 'online', ...)
        Then:  PLCConnectionStatus 新增一行；PLCStatusChangeHistory 新增一行
               （status='online', source='mqtt'）；缓存写入 DEV->'online'
        """
        self._call('online')

        self.assertEqual(PLCConnectionStatus.objects.filter(specific_part=DEV).count(), 1)
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'online')
        self.assertEqual(row.building, BUILDING)
        self.assertEqual(row.unit, UNIT)
        self.assertEqual(row.room_number, ROOM)
        self.assertIsNotNone(row.last_online_time)

        hist = PLCStatusChangeHistory.objects.filter(specific_part=DEV)
        self.assertEqual(hist.count(), 1)
        self.assertEqual(hist.first().status, 'online')
        self.assertEqual(hist.first().source, 'mqtt')

        self.assertEqual(_handlers_module._conn_status_cache.get(DEV), 'online')

    # ------------------------------------------------------------------
    # T-P2-02：同设备第二次调用，状态无变化（online->online，快路径）
    # ------------------------------------------------------------------
    def test_p2_02_no_change_online_fast_path(self):
        """
        Given: 设备已存在且缓存为 online
        When:  再次以 status='online' 调用
        Then:  PLCStatusChangeHistory 不新增；last_online_time 被刷新；
               仅产生 1 条 UPDATE 查询（无事务、无 SELECT FOR UPDATE）
        """
        self._call('online')  # 慢路径建仓
        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 1)

        # 把 last_online_time 改成一天前，便于验证刷新
        old_time = timezone.now() - timedelta(days=1)
        PLCConnectionStatus.objects.filter(specific_part=DEV).update(last_online_time=old_time)

        with CaptureQueriesContext(connection) as ctx:
            self._call('online')  # 快路径

        # 快路径只有一条 UPDATE 查询
        self.assertEqual(len(ctx.captured_queries), 1)
        self.assertTrue(ctx.captured_queries[0]['sql'].upper().lstrip().startswith('UPDATE'))

        # 历史不新增
        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 1)
        # last_online_time 已刷新
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertGreater(row.last_online_time, old_time)

    # ------------------------------------------------------------------
    # T-P2-03：同设备调用，状态无变化（offline->offline，快路径）
    # ------------------------------------------------------------------
    def test_p2_03_no_change_offline_fast_path(self):
        """
        Given: 设备已存在且缓存为 offline
        When:  再次以 status='offline' 调用
        Then:  PLCStatusChangeHistory 不新增；零 DB 写入（0 条查询）
        """
        self._call('offline')  # 慢路径建仓
        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 1)

        with CaptureQueriesContext(connection) as ctx:
            self._call('offline')  # 快路径

        # 快路径 offline：零 DB 写入
        self.assertEqual(len(ctx.captured_queries), 0)
        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 1)

    # ------------------------------------------------------------------
    # T-P2-04：状态变化（online->offline，慢路径）
    # ------------------------------------------------------------------
    def test_p2_04_change_online_to_offline_slow_path(self):
        """
        Given: 设备已存在且缓存为 online
        When:  以 status='offline' 调用
        Then:  PLCStatusChangeHistory 新增一行（status='offline'）；
               PLCConnectionStatus.connection_status 更新为 offline；缓存更新为 offline
        """
        self._call('online')
        self.assertEqual(_handlers_module._conn_status_cache.get(DEV), 'online')

        self._call('offline')

        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 2)
        last_hist = PLCStatusChangeHistory.objects.filter(specific_part=DEV).order_by('-id').first()
        self.assertEqual(last_hist.status, 'offline')

        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'offline')
        self.assertEqual(_handlers_module._conn_status_cache.get(DEV), 'offline')

    # ------------------------------------------------------------------
    # T-P2-05：状态变化（offline->online，慢路径）
    # ------------------------------------------------------------------
    def test_p2_05_change_offline_to_online_slow_path(self):
        """
        Given: 设备已存在且缓存为 offline
        When:  以 status='online' 调用
        Then:  PLCStatusChangeHistory 新增一行（status='online'）；
               PLCConnectionStatus 更新为 online；last_online_time 推进；缓存更新为 online
        """
        self._call('offline')
        old_row = PLCConnectionStatus.objects.get(specific_part=DEV)
        old_online_time = old_row.last_online_time  # offline 建仓时为 None

        self._call('online')

        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 2)
        last_hist = PLCStatusChangeHistory.objects.filter(specific_part=DEV).order_by('-id').first()
        self.assertEqual(last_hist.status, 'online')

        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'online')
        self.assertIsNotNone(row.last_online_time)
        self.assertNotEqual(row.last_online_time, old_online_time)
        self.assertEqual(_handlers_module._conn_status_cache.get(DEV), 'online')

    # ------------------------------------------------------------------
    # T-P2-06：服务重启模拟（缓存清空后全量走慢路径）
    # ------------------------------------------------------------------
    def test_p2_06_restart_cache_cleared_slow_path_no_dup_history(self):
        """
        Given: 设备已存在于 DB（online），随后清空 _conn_status_cache（模拟服务重启）
        When:  对该设备以相同 status='online' 调用
        Then:  走慢路径；DB 中状态未变化 -> 不写 PLCStatusChangeHistory；缓存被重建
        """
        self._call('online')
        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 1)

        # 模拟服务重启：进程内缓存清空
        _handlers_module._conn_status_cache.clear()
        self.assertIsNone(_handlers_module._conn_status_cache.get(DEV))

        self._call('online')  # 缓存 miss -> 慢路径，但 DB 状态未变

        # 状态未变化，不应重复写入变更历史
        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 1)
        # 缓存被重建
        self.assertEqual(_handlers_module._conn_status_cache.get(DEV), 'online')

    # ------------------------------------------------------------------
    # T-P2-07：SQLite 环境下慢路径 select_for_update 不抛 DatabaseError
    # ------------------------------------------------------------------
    def test_p2_07_sqlite_select_for_update_no_error(self):
        """
        Given: 测试库为 SQLite
        When:  连续触发慢路径（新建 + 状态变化），内部使用 select_for_update()
        Then:  全程不抛 DatabaseError 或 SQLite 兼容异常，数据写入正确
        """
        self.assertEqual(connection.vendor, 'sqlite')
        # 新建（慢路径）
        self._call('online')
        # 状态变化（慢路径） x2
        self._call('offline')
        self._call('online')

        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'online')
        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 3)

    # ------------------------------------------------------------------
    # T-P2-08：异常处理——DB 写入失败时缓存不更新
    # ------------------------------------------------------------------
    def test_p2_08_db_failure_does_not_update_cache(self):
        """
        Given: get_or_create 在慢路径中抛出异常
        When:  调用 _update_connection_status
        Then:  logger.error 被调用；_conn_status_cache 不写入该 key，下次仍走慢路径
        """
        with patch('api.mqtt_handlers.PLCConnectionStatus') as mock_model:
            mock_model.objects.select_for_update.return_value.get_or_create.side_effect = \
                Exception('simulated db error')
            with self.assertLogs('api.mqtt_handlers', level='ERROR') as log_ctx:
                self._call('online')

        # 错误被记录
        self.assertTrue(any('更新连接状态失败' in line for line in log_ctx.output))
        # 缓存未更新——异常路径保留 miss 状态
        self.assertNotIn(DEV, _handlers_module._conn_status_cache)


# ---------------------------------------------------------------------------
# 集成测试：通过 handle() 接口验证调用链未受影响
# ---------------------------------------------------------------------------

class TestConnectionStatusHandleIntegration(TestCase):
    """验证 handle() -> _update_connection_status() 调用接口在 P2 优化后保持不变"""

    def setUp(self):
        _handlers_module._conn_status_cache.clear()
        self.handler = ConnectionStatusHandler()

    def _make_payload(self, device_id, has_success):
        """构造 improved_data_collection_manager 格式的连接状态 payload。"""
        return {
            device_id: {
                'PLC IP地址': '192.168.7.83',
                'data': {
                    'living_room_temperature': {
                        'value': 245 if has_success else None,
                        'success': has_success,
                        'message': '读取成功' if has_success else '读取失败',
                        'timestamp': '2026-05-21 10:00:00',
                    }
                },
            }
        }

    # T-P2-09: handle() 中有成功数据项 -> 标记 online
    def test_handle_marks_device_online(self):
        """
        Given: payload 含 success=true 的数据项
        When:  handler.handle() 被调用
        Then:  设备被标记为 online，PLCConnectionStatus / PLCStatusChangeHistory 正确写入
        """
        self.handler.handle('/topic/' + DEV, self._make_payload(DEV, has_success=True))
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'online')
        self.assertEqual(PLCStatusChangeHistory.objects.filter(specific_part=DEV).count(), 1)

    # T-P2-10: handle() 中无成功数据项 -> 标记 offline
    def test_handle_marks_device_offline(self):
        """
        Given: payload 中所有数据项 success=false
        When:  handler.handle() 被调用
        Then:  设备被标记为 offline
        """
        self.handler.handle('/topic/' + DEV, self._make_payload(DEV, has_success=False))
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'offline')
