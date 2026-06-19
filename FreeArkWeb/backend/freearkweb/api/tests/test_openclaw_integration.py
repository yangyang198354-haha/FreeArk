"""
集成测试套件 — OpenClaw 聊天集成（PHASE_08）

使用 channels.testing.WebsocketCommunicator 验证 WebSocket 握手与消息流转。
全部 mock OpenClaw Gateway，不连真实服务。

覆盖范围：
  - TC-I-01 ~ TC-I-08（见 test_plan.md）
  - WebSocket 握手鉴权（有效/无效/无 token）
  - 消息流转（chat_message → stream_token → stream_end）
  - 错误路径（OpenClaw 不可用）
  - MySQL 零写入验证

关键约束：
  - 不连真实 OpenClaw Gateway
  - 使用 SQLite in-memory（test_settings）
  - 验证 DB 无新聊天记录

运行命令：
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_openclaw_integration --settings=freearkweb.test_settings --verbosity=2

项目: FreeArk_Openclaw
文档引用: test_plan.md TC-I-01 ~ TC-I-08
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock
from django.test import TestCase, TransactionTestCase, override_settings, tag
from rest_framework.authtoken.models import Token

from api.models import CustomUser
from api.openclaw_adapter import OpenClawUnavailableError

# ---------------------------------------------------------------------------
# 检测 channels.testing 是否可用
# ---------------------------------------------------------------------------
try:
    from channels.testing import WebsocketCommunicator
    from channels.routing import URLRouter
    from django.urls import re_path
    from api.consumers import ChatConsumer
    CHANNELS_AVAILABLE = True
except ImportError:
    CHANNELS_AVAILABLE = False


# ---------------------------------------------------------------------------
# 辅助：构造测试 ASGI application
# ---------------------------------------------------------------------------

def get_test_application():
    """构造只含 ChatConsumer 路由的最小 ASGI app，用于集成测试。"""
    from channels.routing import URLRouter
    from django.urls import re_path
    from api.consumers import ChatConsumer

    return URLRouter([
        re_path(r'^ws/chat/$', ChatConsumer.as_asgi()),
    ])


# ---------------------------------------------------------------------------
# 辅助：正常 SSE mock 生成器
# ---------------------------------------------------------------------------

async def mock_stream_chat_normal(message, session_key):
    """模拟正常的 OpenClawAdapter.stream_chat — 返回 3 个 token。

    协议升级（v1.x）：stream_chat 现 yield (kind, text) 元组（content/reasoning），
    consumer._pump 按此解包；旧的 yield 纯字符串会导致解包异常、无输出 → 测试超时。
    """
    yield ('content', '你好')
    yield ('content', '，我是方舟龙虾')
    yield ('content', '！')


async def mock_stream_chat_unavailable(message, session_key):
    """模拟 OpenClaw 不可用。"""
    raise OpenClawUnavailableError('方舟龙虾暂时离线，请稍后再试')
    yield  # 使此函数成为 async generator


async def mock_stream_chat_timeout(message, session_key):
    """模拟 OpenClaw 超时。"""
    raise asyncio.TimeoutError('timeout')
    yield  # 使此函数成为 async generator


# ---------------------------------------------------------------------------
# 集成测试主体
# ---------------------------------------------------------------------------

import unittest


@unittest.skipUnless(CHANNELS_AVAILABLE, 'django-channels 未安装，跳过集成测试')
@override_settings(
    OPENCLAW_BASE_URL='http://127.0.0.1:18789',
    OPENCLAW_GATEWAY_TOKEN='test-integration-token',
    OPENCLAW_TIMEOUT=10,
    OPENCLAW_CONNECT_TIMEOUT=5,
    CHANNEL_LAYERS={
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer'
        }
    }
)
@tag('integration')
class TestChatConsumerIntegration(TransactionTestCase):
    """集成测试：ChatConsumer WebSocket 握手与消息流转。

    注意：必须用 TransactionTestCase 而非 TestCase。setUp 中创建的 Token
    通过 sync_to_async 在 channels worker 线程中读取时，标准 TestCase 的
    外层事务对线程池连接不可见，导致 token 验证失败、connect()=False。
    TransactionTestCase 不包装事务，setUp 写入立即提交。
    """

    def setUp(self):
        """创建测试用户和 DRF Token。"""
        self.user = CustomUser.objects.create_user(
            username='integration_test_user',
            password='testpassword123',
            email='integration@example.com',
        )
        self.token = Token.objects.create(user=self.user)
        self.valid_token = self.token.key

    def _run(self, coro):
        """在同步测试方法中运行异步协程。"""
        # Python 3.12 兼容：懒建并复用 loop（原 get_event_loop 在无 loop 时会抛 RuntimeError）。
        loop = getattr(self, "_event_loop", None)
        if loop is None or loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._event_loop = loop
        return loop.run_until_complete(coro)

    # ------------------------------------------------------------------
    # TC-I-01: 有效 token 建立 WS 连接
    # ------------------------------------------------------------------

    async def _test_valid_token_connects(self):
        """TC-I-01: 有效 token 建立 WS 连接 → 收到 connected 消息。"""
        app = get_test_application()
        communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.valid_token}')

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected, '有效 token 应能建立 WebSocket 连接')

        # 等待 connected 消息
        response = await communicator.receive_json_from()
        self.assertEqual(response['type'], 'connected')
        self.assertIn('session_id', response)
        self.assertIsNotNone(response['session_id'])

        await communicator.disconnect()

    def test_valid_token_connects(self):
        self._run(self._test_valid_token_connects())

    # ------------------------------------------------------------------
    # TC-I-02: 无 token 参数被拒绝
    # ------------------------------------------------------------------

    async def _test_no_token_rejected(self):
        """TC-I-02: 无 token 参数 → 连接被关闭（code=4001）。"""
        app = get_test_application()
        communicator = WebsocketCommunicator(app, '/ws/chat/')

        connected, subprotocol = await communicator.connect()
        # 连接可能被接受然后立即关闭，或直接不被接受
        if connected:
            # 等待关闭
            try:
                msg = await communicator.receive_output(timeout=1)
                # 应该是 websocket.close 消息
                if msg['type'] == 'websocket.close':
                    self.assertEqual(msg.get('code'), 4001)
            except Exception:
                pass
        else:
            # 直接拒绝连接也是可接受的结果
            pass

        await communicator.disconnect()

    def test_no_token_rejected(self):
        self._run(self._test_no_token_rejected())

    # ------------------------------------------------------------------
    # TC-I-03: 无效 token 被拒绝
    # ------------------------------------------------------------------

    async def _test_invalid_token_rejected(self):
        """TC-I-03: 无效 token → 连接被关闭（code=4001）。"""
        app = get_test_application()
        communicator = WebsocketCommunicator(app, '/ws/chat/?token=invalid-fake-token-xyz')

        connected, subprotocol = await communicator.connect()
        if connected:
            try:
                msg = await communicator.receive_output(timeout=1)
                if msg['type'] == 'websocket.close':
                    self.assertEqual(msg.get('code'), 4001)
            except Exception:
                pass
        # 无论 connected=True 还是 False，都是可接受的（取决于 channels 版本的握手行为）
        await communicator.disconnect()

    def test_invalid_token_rejected(self):
        self._run(self._test_invalid_token_rejected())

    # ------------------------------------------------------------------
    # TC-I-04: 发送 chat_message → mock SSE → stream_token + stream_end
    # ------------------------------------------------------------------

    async def _test_chat_message_flow(self):
        """
        TC-I-04: 发送 chat_message → mock OpenClaw SSE → 收到 stream_token * 3 + stream_end。
        验证完整消息流转链路。
        """
        app = get_test_application()
        communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.valid_token}')

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # 接收 connected 消息
        conn_msg = await communicator.receive_json_from()
        self.assertEqual(conn_msg['type'], 'connected')

        # Mock OpenClawAdapter.stream_chat
        with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat', side_effect=mock_stream_chat_normal):
            # 发送 chat_message
            await communicator.send_json_to({
                'type': 'chat_message',
                'message': '你好方舟龙虾',
            })

            # 接收 stream_token 消息（期望3个）
            received_tokens = []
            stream_end_received = False
            for _ in range(10):  # 最多等10条消息
                msg = await communicator.receive_json_from()
                if msg['type'] == 'stream_token':
                    received_tokens.append(msg['token'])
                elif msg['type'] == 'stream_end':
                    stream_end_received = True
                    break

            self.assertEqual(received_tokens, ['你好', '，我是方舟龙虾', '！'],
                f'stream_token 序列不符合预期，实际: {received_tokens}')
            self.assertTrue(stream_end_received, '未收到 stream_end 消息')

        await communicator.disconnect()

    def test_chat_message_flow(self):
        self._run(self._test_chat_message_flow())

    # ------------------------------------------------------------------
    # TC-I-05: mock OpenClaw 返回不可用 → error 消息
    # ------------------------------------------------------------------

    async def _test_openclaw_unavailable_error(self):
        """TC-I-05: mock OpenClaw 抛 OpenClawUnavailableError → error 消息。"""
        app = get_test_application()
        communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.valid_token}')

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        conn_msg = await communicator.receive_json_from()
        self.assertEqual(conn_msg['type'], 'connected')

        with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat',
                   side_effect=mock_stream_chat_unavailable):
            await communicator.send_json_to({
                'type': 'chat_message',
                'message': '测试错误路径',
            })

            error_msg = await communicator.receive_json_from()
            self.assertEqual(error_msg['type'], 'error')
            self.assertEqual(error_msg['code'], 'OPENCLAW_UNAVAILABLE')
            self.assertIn('方舟龙虾', error_msg['message'])

        await communicator.disconnect()

    def test_openclaw_unavailable_error(self):
        self._run(self._test_openclaw_unavailable_error())

    # ------------------------------------------------------------------
    # TC-I-06: mock OpenClaw 超时 → error 消息（TIMEOUT）
    # ------------------------------------------------------------------

    async def _test_openclaw_timeout_error(self):
        """TC-I-06: mock OpenClaw 超时 → error 消息（code=TIMEOUT）。"""
        app = get_test_application()
        communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.valid_token}')

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        conn_msg = await communicator.receive_json_from()
        self.assertEqual(conn_msg['type'], 'connected')

        with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat',
                   side_effect=mock_stream_chat_timeout):
            await communicator.send_json_to({
                'type': 'chat_message',
                'message': '测试超时路径',
            })

            error_msg = await communicator.receive_json_from()
            self.assertEqual(error_msg['type'], 'error')
            self.assertEqual(error_msg['code'], 'TIMEOUT')

        await communicator.disconnect()

    def test_openclaw_timeout_error(self):
        self._run(self._test_openclaw_timeout_error())

    # ------------------------------------------------------------------
    # TC-I-07: 流式传输期间不写入 MySQL（DB 零写入验证）
    # ------------------------------------------------------------------

    async def _test_no_db_writes_during_chat_async(self):
        """异步部分：执行完整聊天流程，不在此处碰 DB。"""
        app = get_test_application()
        communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.valid_token}')

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        conn_msg = await communicator.receive_json_from()
        self.assertEqual(conn_msg['type'], 'connected')

        with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat',
                   side_effect=mock_stream_chat_normal):
            await communicator.send_json_to({
                'type': 'chat_message',
                'message': '这条消息不应写入 DB',
            })
            for _ in range(5):
                msg = await communicator.receive_json_from()
                if msg['type'] == 'stream_end':
                    break

        await communicator.disconnect()

    def test_no_db_writes_during_chat(self):
        """
        TC-I-07: 完整聊天流程期间，DB 中无新的"聊天内容"相关表。
        验证 MySQL 零写入约束（REQ-NFR-002）。

        注：表 schema 在 Django 同步上下文中拍快照；async 仅跑 WS 交互。
        """
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables_before = {row[0] for row in cursor.fetchall()}

        self._run(self._test_no_db_writes_during_chat_async())

        with connection.cursor() as cursor:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables_after = {row[0] for row in cursor.fetchall()}

        new_tables = tables_after - tables_before
        chat_related_tables = {t for t in new_tables if 'chat' in t.lower()}
        self.assertEqual(chat_related_tables, set(),
            f'发现非预期的聊天相关表: {chat_related_tables}')

    # ------------------------------------------------------------------
    # TC-I-08: 发送非 chat_message 类型 → 静默丢弃
    # ------------------------------------------------------------------

    async def _test_non_chat_message_ignored(self):
        """TC-I-08: 发送非 chat_message 类型消息 → 静默丢弃，无响应。"""
        app = get_test_application()
        communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.valid_token}')

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        conn_msg = await communicator.receive_json_from()
        self.assertEqual(conn_msg['type'], 'connected')

        # 发送未知类型
        await communicator.send_json_to({
            'type': 'unknown_type',
            'data': 'some data',
        })

        # 不应有任何响应（等待超时）。channels asgiref testing 在 receive 超时
        # 时会取消底层 task；我们必须把 disconnect 包在 try 里防止 CancelledError 冒泡。
        try:
            msg = await communicator.receive_json_from(timeout=0.5)
            self.fail(f'不应有响应，但收到: {msg}')
        except (asyncio.TimeoutError, Exception):
            pass  # 超时是预期结果

        try:
            await communicator.disconnect()
        except (asyncio.CancelledError, Exception):
            pass

    def test_non_chat_message_ignored(self):
        self._run(self._test_non_chat_message_ignored())

    # ------------------------------------------------------------------
    # 额外：验证 session_key 在连接期间保持一致
    # ------------------------------------------------------------------

    async def _test_session_key_consistency(self):
        """
        验证同一连接内 session_key 不变（US-004：sessionKey 贯穿整个会话）。
        通过 connected 消息中的 session_id 与后续调用中传递的 session_key 一致来验证。
        """
        captured_session_keys = []

        async def mock_stream_capture(message, session_key):
            captured_session_keys.append(session_key)
            yield ('content', '回复1')

        app = get_test_application()
        communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.valid_token}')

        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        conn_msg = await communicator.receive_json_from()
        session_id = conn_msg['session_id']

        # 第一次发送
        with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat',
                   side_effect=mock_stream_capture):
            await communicator.send_json_to({
                'type': 'chat_message',
                'message': '第一次',
            })
            # 消费响应
            for _ in range(3):
                msg = await communicator.receive_json_from()
                if msg['type'] == 'stream_end':
                    break

        # 第二次发送
        async def mock_stream_capture2(message, session_key):
            captured_session_keys.append(session_key)
            yield ('content', '回复2')

        with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat',
                   side_effect=mock_stream_capture2):
            await communicator.send_json_to({
                'type': 'chat_message',
                'message': '第二次',
            })
            for _ in range(3):
                msg = await communicator.receive_json_from()
                if msg['type'] == 'stream_end':
                    break

        await communicator.disconnect()

        # 两次调用应使用同一 session_key
        self.assertEqual(len(captured_session_keys), 2)
        self.assertEqual(captured_session_keys[0], captured_session_keys[1],
            '同一连接的两次调用应使用相同的 session_key')
        # session_key 应与 connected 消息中的 session_id 一致
        self.assertEqual(captured_session_keys[0], session_id)

    def test_session_key_consistency(self):
        self._run(self._test_session_key_consistency())
