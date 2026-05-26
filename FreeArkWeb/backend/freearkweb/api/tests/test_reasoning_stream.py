# ===========================================================================
# Reasoning 流协议测试（US-RSN-010，freeark_lobster_reasoning_stream）
# ===========================================================================
#
# 测试目标：
#   - ChatConsumer v1.2 正确将 adapter (kind, text) 二元组路由为 WS 消息类型
#   - reasoning_token → reasoning_end → stream_token → stream_end 时序正确
#   - 无 reasoning 时，序列退化为 stream_token → stream_end（向后兼容）
#   - reasoning_end 最多发送一次（ARCH-C-004）
#
# 测试策略：
#   使用 channels.testing.WebsocketCommunicator（需 Django Channels >= 4.0，
#   且 daphne 已安装作为 ASGI test server）。
#   必须用 TransactionTestCase（Django Channels 的 sync_to_async 在 TestCase
#   的事务隔离下无法访问 ORM，C-005 约束）。
#   mock OpenClawAdapter.stream_chat 返回 AsyncGenerator，避免真实 WS 连接。
#
# 需求引用: REQ-FUNC-010, REQ-NFR-005, AC-010-01~05, AC-NFR-005-01
# US: US-RSN-010
# ===========================================================================

import asyncio
from unittest.mock import patch as _patch

from django.test import TransactionTestCase
from rest_framework.authtoken.models import Token as _Token

try:
    from channels.testing import WebsocketCommunicator
    from api.consumers import ChatConsumer
    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False


def _make_async_gen(*tuples):
    """将 (kind, text) 元组序列包装为 AsyncGenerator，用于 mock stream_chat。"""
    async def _gen():
        for item in tuples:
            yield item
    return _gen()


def _make_ws_app():
    """构建最简 ASGI app，用于 WebsocketCommunicator。"""
    from channels.routing import URLRouter
    from django.urls import re_path
    return URLRouter([
        re_path(r'^ws/chat/$', ChatConsumer.as_asgi()),
    ])


class ChatConsumerReasoningProtocolTest(TransactionTestCase):
    """
    US-RSN-010 场景 A/B/C：reasoning + content 双流时的消息时序验证。

    验收标准：AC-010-01, AC-010-02, AC-010-03, AC-010-04
    """

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        from api.models import CustomUser
        self.user = CustomUser.objects.create_user(
            username='rsn_test_user', password='testpass123'
        )
        self.token, _ = _Token.objects.get_or_create(user=self.user)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_reasoning_then_content_message_sequence(self):
        """
        场景 A（AC-010-01/02/03/04）：
        adapter yield ('reasoning','r1'), ('content','c1')
        期望消息序列：reasoning_token → reasoning_end → stream_token → stream_end
        """
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(
                app, f'/ws/chat/?token={self.token.key}'
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected, '连接应成功建立')

            # 收 connected 消息
            msg = await communicator.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'connected')

            # mock stream_chat 返回 reasoning + content 序列
            with _patch(
                'api.consumers.OpenClawAdapter.stream_chat',
                return_value=_make_async_gen(
                    ('reasoning', '思考片段1'),
                    ('reasoning', '思考片段2'),
                    ('content', '回答片段1'),
                    ('content', '回答片段2'),
                ),
            ):
                await communicator.send_json_to(
                    {'type': 'chat_message', 'message': '测试问题'}
                )

                # 收 reasoning_token × 2
                msg1 = await communicator.receive_json_from(timeout=5)
                self.assertEqual(msg1['type'], 'reasoning_token')
                self.assertEqual(msg1['token'], '思考片段1')

                msg2 = await communicator.receive_json_from(timeout=5)
                self.assertEqual(msg2['type'], 'reasoning_token')
                self.assertEqual(msg2['token'], '思考片段2')

                # 收 reasoning_end（切换到 content 前的一次性信号）
                msg3 = await communicator.receive_json_from(timeout=5)
                self.assertEqual(msg3['type'], 'reasoning_end',
                                 f'期望 reasoning_end，实际收到 {msg3}')

                # 收 stream_token × 2
                msg4 = await communicator.receive_json_from(timeout=5)
                self.assertEqual(msg4['type'], 'stream_token')
                self.assertEqual(msg4['token'], '回答片段1')

                msg5 = await communicator.receive_json_from(timeout=5)
                self.assertEqual(msg5['type'], 'stream_token')
                self.assertEqual(msg5['token'], '回答片段2')

                # 收 stream_end
                msg6 = await communicator.receive_json_from(timeout=5)
                self.assertEqual(msg6['type'], 'stream_end')

            await communicator.disconnect()

        self._run(_inner())

    def test_reasoning_end_sent_only_once(self):
        """
        ARCH-C-004：reasoning_end 最多发送一次。
        即使多个 reasoning 之后才切换 content，reasoning_end 只出现一次。
        """
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(
                app, f'/ws/chat/?token={self.token.key}'
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            msg = await communicator.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'connected')

            with _patch(
                'api.consumers.OpenClawAdapter.stream_chat',
                return_value=_make_async_gen(
                    ('reasoning', 'r1'),
                    ('reasoning', 'r2'),
                    ('reasoning', 'r3'),
                    ('content', 'c1'),
                ),
            ):
                await communicator.send_json_to(
                    {'type': 'chat_message', 'message': '问题'}
                )

                received_types = []
                for _ in range(6):  # r1 r2 r3 reasoning_end c1 stream_end
                    m = await communicator.receive_json_from(timeout=5)
                    received_types.append(m['type'])

            reasoning_end_count = received_types.count('reasoning_end')
            self.assertEqual(reasoning_end_count, 1,
                             f'reasoning_end 应只出现 1 次，实际出现 {reasoning_end_count} 次')

            await communicator.disconnect()

        self._run(_inner())


class ChatConsumerNoReasoningCompatTest(TransactionTestCase):
    """
    US-RSN-010 场景 B：无 reasoning 时的向后兼容验证。

    adapter 只 yield ('content', ...) 时，消息序列退化为
    stream_token × N → stream_end，不出现 reasoning_token / reasoning_end。
    验收标准：AC-010-02, AC-010-04, AC-010-05, AC-NFR-005-01
    """

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        from api.models import CustomUser
        self.user = CustomUser.objects.create_user(
            username='rsn_compat_user', password='testpass456'
        )
        self.token, _ = _Token.objects.get_or_create(user=self.user)

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_no_reasoning_sequence_is_compat(self):
        """
        无 reasoning 流时，WS 消息序列与 v1.1 完全一致：
        stream_token × N → stream_end
        无 reasoning_token，无 reasoning_end。
        """
        async def _inner():
            app = _make_ws_app()
            communicator = WebsocketCommunicator(
                app, f'/ws/chat/?token={self.token.key}'
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)

            msg = await communicator.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'connected')

            with _patch(
                'api.consumers.OpenClawAdapter.stream_chat',
                return_value=_make_async_gen(
                    ('content', 'token1'),
                    ('content', 'token2'),
                    ('content', 'token3'),
                ),
            ):
                await communicator.send_json_to(
                    {'type': 'chat_message', 'message': '问题'}
                )

                received = []
                for _ in range(4):  # 3 stream_token + 1 stream_end
                    m = await communicator.receive_json_from(timeout=5)
                    received.append(m)

            types = [m['type'] for m in received]
            self.assertNotIn('reasoning_token', types,
                             '无 reasoning 流时不应发送 reasoning_token')
            self.assertNotIn('reasoning_end', types,
                             '无 reasoning 流时不应发送 reasoning_end')
            self.assertEqual(types.count('stream_token'), 3)
            self.assertEqual(types[-1], 'stream_end')

            await communicator.disconnect()

        self._run(_inner())
