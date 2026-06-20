"""
test_memory_consumer_v13.py — ChatConsumer v1.3 集成测试

测试目标（GROUP_D / PHASE_07-08）：
  - connect 后 ChatSession 写入 DB
  - stream_end 后 ChatMessage(assistant) 写入 DB
  - 注入历史前缀格式正确（[历史记忆开始]...）
  - 跨用户隔离：用户 A 的历史不影响用户 B 的注入
  - DB 降级：create_session/append_message 失败时 WS 仍可用
  - CHAT_HISTORY_INJECT_TURNS=0 时，前缀为空（不破坏消息结构）
  - 空历史时（第一次对话），前缀为空
  - 回归：reasoning_token/reasoning_end/stream_token/stream_end 协议不变（ARCH-C-006）

需求引用: REQ-FUNC-013, REQ-FUNC-014, REQ-FUNC-016, REQ-NFR-013
US: US-MEM-001~004, US-MEM-005, US-MEM-007
ARCH-C-006 回归
"""
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

from django.test import TransactionTestCase, tag
from rest_framework.authtoken.models import Token

try:
    from channels.testing import WebsocketCommunicator
    from api.consumers import ChatConsumer
    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False

from api.models import ChatSession, ChatMessage
from django.contrib.auth import get_user_model

User = get_user_model()


def _make_async_gen(*tuples):
    """将 (kind, text) 元组序列包装为 AsyncGenerator，用于 mock stream_chat。"""
    async def _gen():
        for item in tuples:
            yield item
    return _gen()


def _make_ws_app():
    from channels.routing import URLRouter
    from django.urls import re_path
    return URLRouter([
        re_path(r'^ws/chat/$', ChatConsumer.as_asgi()),
    ])


_run_loop = None


def _run(coro):
    # Python 3.12：MainThread 无现存 loop 时 asyncio.get_event_loop() 抛 RuntimeError。
    # 懒建并复用一个进程级 loop，保留原"跨调用共享同一 loop"语义。
    global _run_loop
    if _run_loop is None or _run_loop.is_closed():
        _run_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_run_loop)
    return _run_loop.run_until_complete(coro)


@tag('integration')
class ConsumerSessionCreationTest(TransactionTestCase):
    """connect 后 ChatSession 应写入 DB。"""

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        self.user = User.objects.create_user(username='sess_conn_user', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_connect_creates_chat_session(self):
        """connect 成功后，DB 中存在该用户的 ChatSession。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            msg = await communicator.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'connected')
            session_id = msg.get('session_id')
            self.assertIsNotNone(session_id)

            await communicator.disconnect()

        _run(_inner())
        # 连接建立后 DB 中应有该用户的 ChatSession
        self.assertTrue(
            ChatSession.objects.filter(user=self.user).exists(),
            'connect 后应在 DB 中创建 ChatSession'
        )

    def test_disconnect_sets_ended_at(self):
        """disconnect 后 ChatSession.ended_at 应被设置。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)  # consume 'connected'
            await communicator.disconnect()

        _run(_inner())
        sess = ChatSession.objects.filter(user=self.user).first()
        self.assertIsNotNone(sess)
        self.assertIsNotNone(sess.ended_at, 'disconnect 后 ended_at 应被设置')


@tag('integration')
class ConsumerMessageWriteTest(TransactionTestCase):
    """stream_end 后 ChatMessage(assistant) 应写入 DB。"""

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        self.user = User.objects.create_user(username='msg_write_user', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_stream_end_writes_assistant_message(self):
        """流正常结束后，DB 中应有 role=assistant 的 ChatMessage。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)  # connected

            with patch(
                'api.openclaw_adapter.OpenClawAdapter.stream_chat',
                return_value=_make_async_gen(
                    ('content', '回答片段一'),
                    ('content', '回答片段二'),
                ),
            ):
                await communicator.send_json_to({'type': 'chat_message', 'message': '你好'})
                # user message write + 2 stream_token + stream_end
                msgs = []
                for _ in range(3):
                    m = await communicator.receive_json_from(timeout=5)
                    msgs.append(m)
                types = [m['type'] for m in msgs]
                self.assertIn('stream_token', types)
                self.assertIn('stream_end', types)

            await communicator.disconnect()

        _run(_inner())

        sess = ChatSession.objects.filter(user=self.user).first()
        self.assertIsNotNone(sess)
        assistant_msgs = ChatMessage.objects.filter(session=sess, role='assistant')
        self.assertTrue(assistant_msgs.exists(), '流结束后应写入 assistant 消息')
        # 内容是两个片段拼接
        content = assistant_msgs.first().content
        self.assertIn('回答片段一', content)
        self.assertIn('回答片段二', content)

    def test_user_message_written_before_stream(self):
        """用户消息应在发给 OpenClaw 前写入 DB。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch(
                'api.openclaw_adapter.OpenClawAdapter.stream_chat',
                return_value=_make_async_gen(('content', '回复')),
            ):
                await communicator.send_json_to({'type': 'chat_message', 'message': '用户输入'})
                for _ in range(2):
                    await communicator.receive_json_from(timeout=5)

            await communicator.disconnect()

        _run(_inner())
        user_msgs = ChatMessage.objects.filter(session__user=self.user, role='user')
        self.assertTrue(user_msgs.exists(), '用户消息应写入 DB')
        self.assertEqual(user_msgs.first().content, '用户输入')


@tag('integration')
class ConsumerHistoryInjectionTest(TransactionTestCase):
    """历史注入格式验证：[历史记忆开始]...[历史记忆结束]。"""

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        self.user = User.objects.create_user(username='hist_inject_user', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_history_prefix_passed_to_openclaw(self):
        """沿用已有历史的 session 时，发给 OpenClaw 的 message 包含 [历史记忆开始] 前缀。

        v1.4 起历史按 session 隔离（load_history_by_session）：必须用 ?session_key=
        沿用持有历史的那个 session，新建的空 session 不会注入旧历史（见 session 隔离测试）。
        """
        # 先建立一个已有历史的 session
        from api.models import ChatSession, ChatMessage
        old_sess = ChatSession.objects.create(user=self.user, session_key='sk-old-hist')
        ChatMessage.objects.create(session=old_sess, role='user', content='历史问题')
        ChatMessage.objects.create(session=old_sess, role='assistant', content='历史回答')

        captured_messages = []

        async def mock_stream_chat(message, session_key):
            captured_messages.append(message)
            yield ('content', '当前回答')

        async def _inner():
            app = _make_ws_app()
            # v1.4: 沿用持有历史的 session（session 隔离下唯一能取到旧历史的方式）
            communicator = WebsocketCommunicator(
                app, f'/ws/chat/?token={self.token.key}&session_key={old_sess.session_key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat', side_effect=mock_stream_chat):
                await communicator.send_json_to({'type': 'chat_message', 'message': '当前问题'})
                for _ in range(2):
                    await communicator.receive_json_from(timeout=5)

            await communicator.disconnect()

        _run(_inner())
        self.assertTrue(len(captured_messages) > 0, '应有消息被发送给 OpenClaw')
        msg = captured_messages[0]
        self.assertIn('[历史记忆开始]', msg, '注入前缀应包含 [历史记忆开始]')
        self.assertIn('[历史记忆结束]', msg, '注入前缀应包含 [历史记忆结束]')
        self.assertIn('历史问题', msg)
        self.assertIn('历史回答', msg)

    def test_empty_history_no_prefix(self):
        """无历史时，发给 OpenClaw 的 message 不含历史前缀标记。"""
        captured_messages = []

        async def mock_stream_chat(message, session_key):
            captured_messages.append(message)
            yield ('content', '回复')

        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat', side_effect=mock_stream_chat):
                await communicator.send_json_to({'type': 'chat_message', 'message': '第一次对话'})
                for _ in range(2):
                    await communicator.receive_json_from(timeout=5)

            await communicator.disconnect()

        _run(_inner())
        self.assertTrue(len(captured_messages) > 0)
        msg = captured_messages[0]
        self.assertNotIn('[历史记忆开始]', msg, '无历史时不应注入历史前缀')


@tag('integration')
class ConsumerCrossUserIsolationTest(TransactionTestCase):
    """跨用户隔离：用户 A 的历史不注入到用户 B 的消息中。"""

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        self.user_a = User.objects.create_user(username='iso_user_a_v13', password='pass')
        self.user_b = User.objects.create_user(username='iso_user_b_v13', password='pass')
        self.token_a, _ = Token.objects.get_or_create(user=self.user_a)
        self.token_b, _ = Token.objects.get_or_create(user=self.user_b)

    def test_user_b_does_not_see_user_a_history(self):
        """用户 A 有历史，用户 B 连接后发送消息，注入的历史中不含用户 A 的内容。"""
        # 建立用户 A 的历史记录
        sess_a = ChatSession.objects.create(user=self.user_a, session_key='sk-a-iso')
        ChatMessage.objects.create(session=sess_a, role='user', content='用户A的秘密问题')
        ChatMessage.objects.create(session=sess_a, role='assistant', content='用户A的秘密回答')

        captured_b_messages = []

        async def mock_stream_chat(message, session_key):
            captured_b_messages.append(message)
            yield ('content', '用户B的回复')

        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token_b.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch('api.openclaw_adapter.OpenClawAdapter.stream_chat', side_effect=mock_stream_chat):
                await communicator.send_json_to({'type': 'chat_message', 'message': '用户B的问题'})
                for _ in range(2):
                    await communicator.receive_json_from(timeout=5)

            await communicator.disconnect()

        _run(_inner())
        self.assertTrue(len(captured_b_messages) > 0)
        msg_b = captured_b_messages[0]
        self.assertNotIn('用户A的秘密问题', msg_b, '用户A的历史不应出现在用户B的注入中')
        self.assertNotIn('用户A的秘密回答', msg_b, '用户A的历史不应出现在用户B的注入中')


@tag('integration')
class ConsumerDegradationTest(TransactionTestCase):
    """
    降级路径：DB 操作失败时，WS 连接不中断。

    ARCH-C-011：所有 DB 操作失败均降级（记日志，WS 不中断）。
    """

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        self.user = User.objects.create_user(username='degrade_user_v13', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_create_session_failure_ws_still_connects(self):
        """create_session DB 失败时，WS 仍成功建立连接。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')

            with patch('api.chat_memory.create_session', side_effect=Exception('DB down')):
                connected, _ = await communicator.connect()
                self.assertTrue(connected, 'create_session 失败后 WS 仍应能连接')
                msg = await communicator.receive_json_from(timeout=3)
                self.assertEqual(msg['type'], 'connected')

            await communicator.disconnect()

        _run(_inner())

    def test_load_history_failure_chat_still_works(self):
        """load_history 失败时，WS 聊天仍能进行（使用空历史降级）。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch('api.consumers.chat_memory.load_history', side_effect=Exception('DB timeout')), \
                 patch('api.openclaw_adapter.OpenClawAdapter.stream_chat',
                       return_value=_make_async_gen(('content', '降级回复'))):
                await communicator.send_json_to({'type': 'chat_message', 'message': '测试降级'})
                received = []
                for _ in range(2):
                    m = await communicator.receive_json_from(timeout=5)
                    received.append(m)
                types = [m['type'] for m in received]
                self.assertIn('stream_end', types, 'load_history 失败后流仍应正常结束')

            await communicator.disconnect()

        _run(_inner())

    def test_append_message_failure_chat_continues(self):
        """append_message(assistant) 失败时，WS 消息流仍正常发送给前端。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch('api.consumers.chat_memory.append_message', side_effect=Exception('write failed')), \
                 patch('api.openclaw_adapter.OpenClawAdapter.stream_chat',
                       return_value=_make_async_gen(('content', '内容'))):
                await communicator.send_json_to({'type': 'chat_message', 'message': '测试'})
                received = []
                for _ in range(2):
                    m = await communicator.receive_json_from(timeout=5)
                    received.append(m)
                types = [m['type'] for m in received]
                self.assertIn('stream_end', types, 'append_message 失败后流仍应正常结束')

            await communicator.disconnect()

        _run(_inner())


@tag('integration')
class ConsumerInjectTurnsZeroTest(TransactionTestCase):
    """CHAT_HISTORY_INJECT_TURNS=0 时，前缀为空，不破坏消息结构。"""

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        self.user = User.objects.create_user(username='turns_zero_user', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_inject_turns_zero_no_prefix(self):
        """将 load_history 的返回 mock 为空（模拟 turns=0 效果），注入前缀应为空。"""
        captured_messages = []

        async def mock_stream_chat(message, session_key):
            captured_messages.append(message)
            yield ('content', '回复')

        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            # mock load_history 返回空列表（等效于 INJECT_TURNS=0）
            with patch('api.consumers.chat_memory.load_history', return_value=[]), \
                 patch('api.openclaw_adapter.OpenClawAdapter.stream_chat', side_effect=mock_stream_chat):
                await communicator.send_json_to({'type': 'chat_message', 'message': '问题'})
                for _ in range(2):
                    await communicator.receive_json_from(timeout=5)

            await communicator.disconnect()

        _run(_inner())
        self.assertTrue(len(captured_messages) > 0)
        msg = captured_messages[0]
        self.assertNotIn('[历史记忆开始]', msg, 'turns=0 时不应注入历史前缀')
        # 消息结构完整：应包含 [__freeark_user__:...] 前缀
        self.assertIn('[__freeark_user__:', msg)


@tag('integration')
class ConsumerReasoningStreamRegressionTest(TransactionTestCase):
    """
    回归测试 — ARCH-C-006：consumers.py v1.3 不破坏 reasoning 协议。

    验证：reasoning_token/reasoning_end/stream_token/stream_end 时序正确。
    这是 GROUP_D 对 reasoning_stream 功能的回归验证（不修改 test_reasoning_stream.py）。
    """

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        self.user = User.objects.create_user(username='regress_v13_user', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_reasoning_token_sequence_unchanged(self):
        """v1.3 中 reasoning_token → reasoning_end → stream_token → stream_end 时序不变。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch(
                'api.openclaw_adapter.OpenClawAdapter.stream_chat',
                return_value=_make_async_gen(
                    ('reasoning', '思考'),
                    ('content', '回答'),
                ),
            ):
                await communicator.send_json_to({'type': 'chat_message', 'message': '测试'})
                received = []
                for _ in range(4):  # reasoning_token + reasoning_end + stream_token + stream_end
                    m = await communicator.receive_json_from(timeout=5)
                    received.append(m)

            types = [m['type'] for m in received]
            self.assertEqual(types[0], 'reasoning_token', 'reasoning_token 应排第一')
            self.assertEqual(types[1], 'reasoning_end', 'reasoning_end 应排第二')
            self.assertEqual(types[2], 'stream_token', 'stream_token 应排第三')
            self.assertEqual(types[3], 'stream_end', 'stream_end 应排最后')

            await communicator.disconnect()

        _run(_inner())

    def test_no_reasoning_sequence_compat(self):
        """无 reasoning 时退化为 stream_token → stream_end，无 reasoning_token/end。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch(
                'api.openclaw_adapter.OpenClawAdapter.stream_chat',
                return_value=_make_async_gen(
                    ('content', 't1'),
                    ('content', 't2'),
                ),
            ):
                await communicator.send_json_to({'type': 'chat_message', 'message': '无reasoning'})
                received = []
                for _ in range(3):  # 2 stream_token + 1 stream_end
                    m = await communicator.receive_json_from(timeout=5)
                    received.append(m)

            types = [m['type'] for m in received]
            self.assertNotIn('reasoning_token', types)
            self.assertNotIn('reasoning_end', types)
            self.assertEqual(types.count('stream_token'), 2)
            self.assertEqual(types[-1], 'stream_end')

            await communicator.disconnect()

        _run(_inner())

    def test_reasoning_end_only_once(self):
        """ARCH-C-004：多个 reasoning 块后，reasoning_end 只出现一次。"""
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.receive_json_from(timeout=3)

            with patch(
                'api.openclaw_adapter.OpenClawAdapter.stream_chat',
                return_value=_make_async_gen(
                    ('reasoning', 'r1'),
                    ('reasoning', 'r2'),
                    ('content', 'c1'),
                ),
            ):
                await communicator.send_json_to({'type': 'chat_message', 'message': '多段思考'})
                received = []
                for _ in range(5):  # r1 r2 reasoning_end c1 stream_end
                    m = await communicator.receive_json_from(timeout=5)
                    received.append(m)

            types = [m['type'] for m in received]
            self.assertEqual(types.count('reasoning_end'), 1,
                             f'reasoning_end 应只出现 1 次，实际: {types}')

            await communicator.disconnect()

        _run(_inner())
