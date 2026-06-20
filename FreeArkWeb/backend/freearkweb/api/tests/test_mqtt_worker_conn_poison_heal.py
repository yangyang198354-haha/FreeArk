"""
MQTT worker 连接中毒自愈测试套件（2026-06-01 PLC 在线率暴跌 RCA 修复）

背景：
  energy worker 的 Django thread-local 连接若在 ConnectionStatusHandler 的
  transaction.atomic() 块内因 2006(server has gone away)/2013(lost connection,
  read_timeout=60) 断连，会被遗留成 connection=None 且 in_atomic_block 卡死的脏状态。
  此后该 worker 每条消息在 _worker_loop 的 ensure_connection() 处抛
  ProgrammingError("Cannot open a new connection in an atomic block")，永久失败、
  不再刷新 last_online_time，直到进程重启——这是生产 PLC 在线率被 monitor 误判暴跌的真因。

修复（api/mqtt_consumer.py）：
  - 新增 _is_db_connection_error()：识别连接断开 / atomic 中毒类异常（含上述 ProgrammingError）。
  - _worker_loop 的 except 分支：命中连接类错误时调用 _check_and_reconnect_db() 强制重建连接
    （内部 connection.connect() 会重置 in_atomic_block 等事务状态），把"需人工重启"降级为
    "丢 1 条消息后自愈"。

覆盖：
  - T-HEAL-01 _is_db_connection_error 对 atomic 中毒 ProgrammingError 返回 True
  - T-HEAL-02 _is_db_connection_error 对 2006/2013/OperationalError 返回 True
  - T-HEAL-03 _is_db_connection_error 对非连接错误（ValueError/JSON 等）返回 False
  - T-HEAL-04 worker 遇 atomic 中毒错误时触发 _check_and_reconnect_db（自愈路径）
  - T-HEAL-05 worker 遇普通业务错误时不触发重建（避免无谓重连）

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_mqtt_worker_conn_poison_heal --verbosity=2
"""
import queue
from unittest.mock import MagicMock, patch

from django.db.utils import ProgrammingError, OperationalError
from django.test import SimpleTestCase, tag

from api.mqtt_consumer import MQTTConsumer, _is_db_connection_error


# 生产实测中毒异常文本（来自 mqtt_consumer.log 堆栈）
ATOMIC_POISON = ProgrammingError("Cannot open a new connection in an atomic block.")
GONE_AWAY = OperationalError(2006, "Server has gone away")
LOST_DURING_QUERY = OperationalError(2013, "Lost connection to server during query")


@tag('unit')
class TestIsDbConnectionError(SimpleTestCase):
    """_is_db_connection_error 的识别逻辑（纯函数，无需 DB）。"""

    def test_atomic_block_poison_is_connection_error(self):
        # T-HEAL-01：中毒后 ensure_connection 抛的 ProgrammingError 必须被识别
        self.assertTrue(_is_db_connection_error(ATOMIC_POISON))

    def test_operational_errors_are_connection_errors(self):
        # T-HEAL-02：2006/2013 及任意 OperationalError 都需重建
        self.assertTrue(_is_db_connection_error(GONE_AWAY))
        self.assertTrue(_is_db_connection_error(LOST_DURING_QUERY))
        self.assertTrue(_is_db_connection_error(OperationalError("some other op error")))

    def test_business_errors_are_not_connection_errors(self):
        # T-HEAL-03：业务/解析类错误不应触发重连
        self.assertFalse(_is_db_connection_error(ValueError("bad json")))
        self.assertFalse(_is_db_connection_error(KeyError("missing field")))
        self.assertFalse(_is_db_connection_error(Exception("无法提取device_id")))


@patch('api.mqtt_consumer.django_connection')
@patch('api.mqtt_consumer.close_old_connections')
@tag('unit')
class TestWorkerLoopHeal(SimpleTestCase):
    """_worker_loop 在连接中毒时的自愈行为（连接调用全部 mock，不触碰真实 DB）。"""

    def _run_one_message(self, consumer, exc):
        """投递一条消息、令 _dispatch 抛 exc、设 stop_event 使 loop 处理完即退出。"""
        consumer._dispatch = MagicMock(side_effect=exc)
        consumer._check_and_reconnect_db = MagicMock(return_value=True)
        q = queue.Queue()
        q.put(("/datacollection/plc/to/collector/abc", b"{}", 0))
        consumer.stop_event.set()  # 队列清空后立即退出循环
        consumer._worker_loop(q, is_general=False)
        return consumer

    def test_worker_heals_on_atomic_poison(self, _mock_close, _mock_conn):
        # T-HEAL-04：中毒错误 → 触发一次强制重建
        consumer = MQTTConsumer()
        self._run_one_message(consumer, ATOMIC_POISON)
        consumer._check_and_reconnect_db.assert_called_once_with(with_diagnostic=False)

    def test_worker_heals_on_server_gone_away(self, _mock_close, _mock_conn):
        # T-HEAL-04b：2006 同样触发重建
        consumer = MQTTConsumer()
        self._run_one_message(consumer, GONE_AWAY)
        consumer._check_and_reconnect_db.assert_called_once_with(with_diagnostic=False)

    def test_worker_does_not_reconnect_on_business_error(self, _mock_close, _mock_conn):
        # T-HEAL-05：普通业务错误 → 不重建（避免无谓重连开销）
        consumer = MQTTConsumer()
        self._run_one_message(consumer, ValueError("bad json"))
        consumer._check_and_reconnect_db.assert_not_called()
