"""
ConnectionStatusHandler Cache/DB 一致性修复专项测试 (v0.5.8 F2)

覆盖范围：
  - F2 修复的核心 bug 场景：快路径 online 分支 cache/DB 不一致时回退慢路径
  - 常态快路径不受影响（行为与修复前完全相同）
  - Cache miss 慢路径行为不变
  - Cache='offline' 状态变化慢路径行为不变

需求溯源：
  REQ-FUNC-v0.5.8-01：cache/DB 不一致时回退慢路径，写 source='mqtt'/status='online' history
  REQ-FUNC-v0.5.8-02：WARNING 日志可观测性
  REQ-NFUNC-v0.5.8-02：常态快路径无额外 SQL 查询

验收标准：
  AC-v0.5.8-01-01 ~ AC-v0.5.8-01-04（US-v0.5.8-01）
  AC-v0.5.8-02-01 ~ AC-v0.5.8-02-02（US-v0.5.8-02）

用例编号：T-F2-01 ~ T-F2-04（新场景）+ 回归验证

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_connection_status_cache_coherence_v058 \\
        --settings=freearkweb.test_settings --verbosity=2
"""

from django.db import connection
from django.test import TestCase, tag
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from api.models import PLCConnectionStatus, PLCStatusChangeHistory
from api.mqtt_handlers import ConnectionStatusHandler
import api.mqtt_handlers as _handlers_module


# ---------------------------------------------------------------------------
# 测试常量
# ---------------------------------------------------------------------------

DEV = '5-2-3-301'         # 专项测试设备（与 v0.5.5 测试套件使用不同标识符，避免干扰）
BUILDING, UNIT, ROOM = '5', '2', '301'


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_device_online(dev=DEV, building=BUILDING, unit=UNIT, room=ROOM):
    """在 DB 中建立 connection_status='online' 的记录，模拟 PLC 正常运行状态。"""
    obj, _ = PLCConnectionStatus.objects.get_or_create(
        specific_part=dev,
        defaults={
            'connection_status': 'online',
            'building': building,
            'unit': unit,
            'room_number': room,
            'last_online_time': timezone.now(),
        }
    )
    if obj.connection_status != 'online':
        obj.connection_status = 'online'
        obj.save(update_fields=['connection_status'])
    return obj


def _make_device_offline_by_monitor(dev=DEV, building=BUILDING, unit=UNIT, room=ROOM):
    """
    模拟 Path B（plc_connection_monitor）将设备置为 offline：
    直接操作 DB，不通过 mqtt_handlers（不更新 cache），
    以复现 cache='online' 但 DB='offline' 的不一致状态。
    """
    PLCConnectionStatus.objects.filter(specific_part=dev).update(
        connection_status='offline'
    )
    PLCStatusChangeHistory.objects.create(
        specific_part=dev,
        status='offline',
        building=building,
        unit=unit,
        room_number=room,
        source='monitor',
    )


# ---------------------------------------------------------------------------
# T-F2 专项测试：F2 修复核心场景
# ---------------------------------------------------------------------------

@tag('unit')
class TestCacheCoherenceFixV058(TestCase):
    """
    验证 v0.5.8 F2 修复的核心 bug 场景：
    快路径 online 分支检测到 cache/DB 不一致时，
    正确回退慢路径并写入 source='mqtt'/status='online' history。
    """

    def setUp(self):
        _handlers_module._conn_status_cache.clear()
        self.handler = ConnectionStatusHandler()

    def _call(self, status, specific_part=DEV):
        self.handler._update_connection_status(
            specific_part, status, BUILDING, UNIT, ROOM
        )

    # ------------------------------------------------------------------
    # T-F2-01：S1 场景 — cache='online'，DB='online'，status='online'
    #           → 快路径，rows=1，不写 history，无 WARNING
    # ------------------------------------------------------------------
    def test_f2_01_cache_online_db_online_fast_path_no_regression(self):
        """
        Given: cache[DEV]='online'，DB.connection_status='online'
        When:  _update_connection_status(DEV, 'online', ...) 被调用
        Then:  UPDATE rows=1，快路径，last_online_time 刷新，
               不走慢路径，PLCStatusChangeHistory 无新增，无 WARNING 日志

        对应 AC-v0.5.8-01-02：验证常态快路径行为与修复前完全相同（REQ-NFUNC-v0.5.8-02）
        """
        # 建立 DB 记录：connection_status='online'
        _make_device_online()
        history_count_before = PLCStatusChangeHistory.objects.filter(
            specific_part=DEV
        ).count()

        # 设置 cache='online'
        _handlers_module._conn_status_cache[DEV] = 'online'

        # 捕获 SQL 查询数量，验证只有 1 条 UPDATE（无额外 SELECT）
        with CaptureQueriesContext(connection) as ctx:
            with self.assertLogs('api.mqtt_handlers', level='DEBUG') as log_ctx:
                self._call('online')

        # 断言 1：仅执行 1 条 SQL（带守卫的 UPDATE）
        self.assertEqual(
            len(ctx.captured_queries), 1,
            f"常态快路径应只有 1 条 SQL，实际: {len(ctx.captured_queries)}\n"
            f"SQL: {[q['sql'] for q in ctx.captured_queries]}"
        )
        update_sql = ctx.captured_queries[0]['sql'].upper()
        self.assertIn('UPDATE', update_sql, "应为 UPDATE 语句")

        # 断言 2：history 无新增
        history_count_after = PLCStatusChangeHistory.objects.filter(
            specific_part=DEV
        ).count()
        self.assertEqual(
            history_count_after, history_count_before,
            "常态快路径不应写入新的 PLCStatusChangeHistory"
        )

        # 断言 3：无 WARNING 日志
        warning_lines = [l for l in log_ctx.output if 'WARNING' in l]
        self.assertEqual(
            len(warning_lines), 0,
            f"常态快路径不应产生 WARNING 日志，实际: {warning_lines}"
        )

        # 断言 4：DB 的 connection_status 仍为 'online'
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'online')

        # 断言 5：cache 仍为 'online'
        self.assertEqual(_handlers_module._conn_status_cache.get(DEV), 'online')

    # ------------------------------------------------------------------
    # T-F2-02：S2 场景 — cache='online'，DB='offline'（Path B 置过），status='online'
    #           → 快路径 UPDATE rows=0 → 回退慢路径 → 写 history，cache 翻回 online
    # ------------------------------------------------------------------
    def test_f2_02_cache_online_db_offline_by_monitor_triggers_fallback(self):
        """
        Given: cache[DEV]='online'，DB.connection_status='offline'（被 Path B 置过）
        When:  _update_connection_status(DEV, 'online', ...) 被调用
        Then:  快路径 UPDATE rows=0（守卫条件不满足）；
               logger.warning 记录（含 specific_part 和"cache/DB 不一致"字样）；
               cache 失效（pop 后由慢路径重建）；
               慢路径执行：DB.connection_status 翻回 'online'；
               PLCStatusChangeHistory 新增 1 条 source='mqtt', status='online'；
               cache[DEV]='online'

        这是 F2 修复的核心验证：AC-v0.5.8-01-01（US-v0.5.8-01）
        """
        # 建立 DB 记录：先 online，再由"monitor"置为 offline
        _make_device_online()
        history_count_before = PLCStatusChangeHistory.objects.filter(
            specific_part=DEV
        ).count()
        _make_device_offline_by_monitor()

        # 确认 DB 此时为 offline
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'offline', "测试前置条件：DB 应为 offline")

        # 设置 cache='online'（模拟 Path B 置 offline 时未通知 mqtt-consumer 进程）
        _handlers_module._conn_status_cache[DEV] = 'online'

        # 调用（捕获 WARNING 日志）
        with self.assertLogs('api.mqtt_handlers', level='WARNING') as log_ctx:
            self._call('online')

        # 断言 1：WARNING 日志被触发，含 specific_part 和关键字
        warning_lines = [l for l in log_ctx.output if 'WARNING' in l]
        self.assertGreater(
            len(warning_lines), 0,
            "cache/DB 不一致时应记录 WARNING 日志"
        )
        warning_text = ' '.join(warning_lines)
        self.assertIn(
            DEV, warning_text,
            f"WARNING 日志应包含 specific_part={DEV}"
        )
        self.assertTrue(
            '不一致' in warning_text or 'inconsist' in warning_text.lower(),
            f"WARNING 日志应包含'不一致'或类似字样，实际: {warning_text}"
        )

        # 断言 2：DB.connection_status 已翻回 'online'
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(
            row.connection_status, 'online',
            "慢路径应将 DB.connection_status 翻回 'online'"
        )

        # 断言 3：PLCStatusChangeHistory 新增 1 条 source='mqtt', status='online'
        new_histories = PLCStatusChangeHistory.objects.filter(
            specific_part=DEV,
            source='mqtt',
            status='online',
        ).order_by('-id')
        self.assertGreater(
            new_histories.count(), history_count_before,
            "慢路径应写入 source='mqtt', status='online' 的 history 记录"
        )
        latest = new_histories.first()
        self.assertEqual(latest.source, 'mqtt')
        self.assertEqual(latest.status, 'online')

        # 断言 4：cache 已由慢路径重建为 'online'
        self.assertEqual(
            _handlers_module._conn_status_cache.get(DEV), 'online',
            "慢路径完成后 cache 应重建为 'online'"
        )

    # ------------------------------------------------------------------
    # T-F2-03：S3 场景 — cache=None（miss），status='online'
    #           → 慢路径（与修复前相同）
    # ------------------------------------------------------------------
    def test_f2_03_cache_miss_status_online_slow_path_unchanged(self):
        """
        Given: _conn_status_cache 中无 DEV（cache miss），DB.connection_status='offline'
        When:  _update_connection_status(DEV, 'online', ...) 被调用
        Then:  不进入快路径；走慢路径；DB 翻回 'online'；
               写入 source='mqtt', status='online' history；cache 重建为 'online'

        对应 AC-v0.5.8-01-03：验证 cache miss 慢路径行为与修复前完全相同
        """
        _make_device_online()
        _make_device_offline_by_monitor()
        # 确认 cache 为空
        self.assertIsNone(_handlers_module._conn_status_cache.get(DEV))

        history_count_before = PLCStatusChangeHistory.objects.filter(
            specific_part=DEV
        ).count()

        self._call('online')

        # DB 翻回 online
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'online')

        # history 写入
        new_count = PLCStatusChangeHistory.objects.filter(
            specific_part=DEV, source='mqtt', status='online'
        ).count()
        self.assertGreater(new_count, 0)

        # cache 重建
        self.assertEqual(_handlers_module._conn_status_cache.get(DEV), 'online')

    # ------------------------------------------------------------------
    # T-F2-04：S4 场景 — cache='offline'，status='online'（状态变化）
    #           → 慢路径（与修复前相同）
    # ------------------------------------------------------------------
    def test_f2_04_cache_offline_status_online_slow_path_unchanged(self):
        """
        Given: cache[DEV]='offline'，DB.connection_status='offline'，status='online'（状态变化）
        When:  _update_connection_status(DEV, 'online', ...) 被调用
        Then:  cached != status，不进入快路径；走慢路径；
               DB 翻回 'online'；写入 source='mqtt', status='online' history；
               cache 更新为 'online'

        对应 AC-v0.5.8-01-04：验证状态变化慢路径行为与修复前完全相同
        """
        _make_device_online()
        _make_device_offline_by_monitor()
        # 设置 cache='offline'（模拟 Path A 之前正确处理过 offline 事件）
        _handlers_module._conn_status_cache[DEV] = 'offline'

        history_count_before = PLCStatusChangeHistory.objects.filter(
            specific_part=DEV
        ).count()

        self._call('online')

        # DB 翻回 online
        row = PLCConnectionStatus.objects.get(specific_part=DEV)
        self.assertEqual(row.connection_status, 'online')

        # history 写入（offline→online 状态变化）
        new_count = PLCStatusChangeHistory.objects.filter(
            specific_part=DEV, source='mqtt', status='online'
        ).count()
        self.assertGreater(new_count, 0)

        # cache 更新为 online
        self.assertEqual(_handlers_module._conn_status_cache.get(DEV), 'online')


# ---------------------------------------------------------------------------
# T-F2 可观测性测试：WARNING 日志格式验证
# ---------------------------------------------------------------------------

@tag('unit')
class TestCacheCoherenceLoggingV058(TestCase):
    """
    验证 WARNING 日志格式满足 REQ-FUNC-v0.5.8-02 / AC-v0.5.8-02-01 ~ 02-02
    """

    def setUp(self):
        _handlers_module._conn_status_cache.clear()
        self.handler = ConnectionStatusHandler()

    def _call(self, status, specific_part=DEV):
        self.handler._update_connection_status(
            specific_part, status, BUILDING, UNIT, ROOM
        )

    def test_warning_log_format_on_cache_db_mismatch(self):
        """
        AC-v0.5.8-02-01：cache/DB 不一致时 WARNING 日志格式正确
        """
        _make_device_online()
        _make_device_offline_by_monitor()
        _handlers_module._conn_status_cache[DEV] = 'online'

        with self.assertLogs('api.mqtt_handlers', level='WARNING') as log_ctx:
            self._call('online')

        warning_lines = [l for l in log_ctx.output if 'WARNING' in l]
        self.assertGreater(len(warning_lines), 0)

        combined = ' '.join(warning_lines)
        # 必须包含 specific_part
        self.assertIn(DEV, combined, "WARNING 日志必须包含 specific_part")
        # 必须包含"不一致"字样
        self.assertIn('不一致', combined, "WARNING 日志必须包含'不一致'字样")
        # 必须包含"回退慢路径"字样
        self.assertIn('回退慢路径', combined, "WARNING 日志必须包含'回退慢路径'字样")

    def test_no_warning_on_normal_fast_path(self):
        """
        AC-v0.5.8-02-02：常态快路径（rows=1）无 WARNING 日志
        """
        _make_device_online()
        _handlers_module._conn_status_cache[DEV] = 'online'

        import logging
        with self.assertLogs('api.mqtt_handlers', level='DEBUG') as log_ctx:
            # 需要至少一条日志（DEBUG）才不会抛 AssertionError
            self._call('online')

        warning_lines = [l for l in log_ctx.output if 'WARNING' in l]
        self.assertEqual(
            len(warning_lines), 0,
            f"常态快路径不应产生 WARNING 日志，实际: {warning_lines}"
        )
