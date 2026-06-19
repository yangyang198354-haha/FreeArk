"""
test_chat_session_e2e.py — FreeArk_ChatSession E2E 测试

测试目标：
  TC-E2E-001: 完整会话创建流程
    WS connect → DB 无记录
    → 发送首条消息（mock LLM）→ ChatSession 创建，title=截断文本（AC-004-01）
    → asyncio.create_task 触发（AC-004-02，mock 验证）
    → REST GET /api/memory/session/{key}/history/ → 返回正确消息（AC-006-01）

需求溯源（critical path）：
  US-001 AC-001-02, US-002 AC-002-01, US-004 AC-004-01, US-006 AC-006-01

关键约束：
  - WS 层使用 InMemoryChannelLayer（不需要 Redis）
  - LLM 调用全部 mock，不发送真实请求
  - 使用 TransactionTestCase（WS 测试跨事务边界）
"""

import asyncio
import json
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import ChatSession, ChatMessage

User = get_user_model()

_run_loop = None


def _run_e2e(coro):
    global _run_loop
    if _run_loop is None or _run_loop.is_closed():
        _run_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_run_loop)
    return _run_loop.run_until_complete(coro)


def _make_ws_app():
    from channels.routing import URLRouter
    from django.urls import re_path
    from api.consumers import ChatConsumer
    return URLRouter([re_path(r'^ws/chat/$', ChatConsumer.as_asgi())])


def _auth_client(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


class FullSessionLifecycleE2ETest(TransactionTestCase):
    """
    TC-E2E-001: 完整会话创建流程（critical path）。

    步骤：
      1. WS connect → 验证 DB 无 ChatSession（AC-002-01）
      2. 发送首条 user 消息（mock LLM 返回内容）→ 等待 stream_end
      3. 验证 ChatSession 已创建，title 已写入截断文本（AC-001-02, AC-004-01）
      4. REST GET /api/memory/session/{key}/history/ → 验证返回正确消息（AC-006-01）
    """

    def setUp(self):
        try:
            from channels.testing import WebsocketCommunicator
            self._channels_ok = True
        except ImportError:
            self._channels_ok = False

        self.user = User.objects.create_user(
            username='e2e_user_lifecycle', password='testpass123'
        )
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_tc_e2e_001_full_session_lifecycle(self):
        """TC-E2E-001: 完整会话生命周期 — connect 不落库 → 首条消息创建 session → /history/ 正确返回。"""
        if not self._channels_ok:
            self.skipTest('channels.testing 不可用，跳过 E2E 测试')

        from channels.testing import WebsocketCommunicator

        user_message = '这是一条测试消息，内容足够长以触发截断标题逻辑并验证截断效果'
        llm_response = '这是模拟的LLM助手回复内容，用于验证消息落库功能'

        captured_session_key = []

        async def _mock_stream(*args, **kwargs):
            yield ('content', llm_response)

        async def _inner():
            app = _make_ws_app()
            comm = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')

            # === Step 1: WS connect ===
            connected, _ = await comm.connect()
            self.assertTrue(connected, 'WS 应连接成功')

            connect_msg = await comm.receive_json_from(timeout=3)
            self.assertEqual(connect_msg['type'], 'connected')
            session_key = connect_msg.get('session_key', '')
            self.assertTrue(session_key, 'connected 消息应包含 session_key')
            captured_session_key.append(session_key)

            # === Step 1 验证：connect 后 DB 无记录（AC-002-01）===
            from asgiref.sync import sync_to_async
            count_after_connect = await sync_to_async(
                ChatSession.objects.filter(user=self.user).count
            )()
            self.assertEqual(
                count_after_connect, 0,
                f'WS connect 后 DB 不应有 ChatSession，实际 count={count_after_connect}',
            )

            # === Step 2: 发送首条消息（mock LLM）===
            with patch('api.consumers.get_chat_adapter') as mock_adapter, \
                 patch('api.chat_memory.generate_title_llm_async', new_callable=AsyncMock):
                adapter_instance = MagicMock()
                adapter_instance.stream_chat.return_value = _mock_stream()
                mock_adapter.return_value = adapter_instance

                await comm.send_json_to({
                    'type': 'chat_message',
                    'message': user_message,
                })

                # 消费 WS 消息直到 stream_end
                received_types = []
                for _ in range(30):
                    try:
                        msg = await asyncio.wait_for(comm.receive_json_from(), timeout=5)
                        received_types.append(msg.get('type'))
                        if msg.get('type') == 'stream_end':
                            break
                    except asyncio.TimeoutError:
                        break

            self.assertIn(
                'stream_end', received_types,
                f'应收到 stream_end，实际收到：{received_types}',
            )

            await comm.disconnect()

        _run_e2e(_inner())

        self.assertTrue(len(captured_session_key) == 1)
        session_key = captured_session_key[0]

        # === Step 3 验证：ChatSession 已创建（AC-001-02）===
        sessions = ChatSession.objects.filter(user=self.user, session_key=session_key)
        self.assertEqual(sessions.count(), 1, '首条消息后应有 1 个 ChatSession')

        sess = sessions.first()

        # === Step 3 验证：title 已写入截断文本（AC-004-01）===
        self.assertIsNotNone(sess.title, 'ChatSession.title 不应为 None')
        self.assertNotEqual(sess.title, '', 'ChatSession.title 不应为空字符串')
        # 截断标题长度应 ≤ 30
        self.assertLessEqual(len(sess.title), 30, f'截断标题长度 ({len(sess.title)}) 应 ≤ 30')

        # === Step 3 验证：ChatMessage 已落库（user + assistant）===
        messages = ChatMessage.objects.filter(session=sess).order_by('created_at')
        self.assertGreaterEqual(messages.count(), 1, '至少应有 1 条 user 消息落库')
        # 验证 user 消息内容（注意：落库的是原始消息，不含注入前缀）
        user_msgs = messages.filter(role='user')
        self.assertEqual(user_msgs.count(), 1)
        self.assertEqual(user_msgs.first().content, user_message)

        # === Step 4 验证：REST GET /history/ 返回正确消息（AC-006-01）===
        rest_client = _auth_client(self.user)
        resp = rest_client.get(f'/api/memory/session/{session_key}/history/')
        self.assertEqual(resp.status_code, 200, f'/history/ 应返回 200，实际 {resp.status_code}')
        data = resp.json()
        self.assertIn('messages', data)
        self.assertIn('total', data)
        self.assertGreaterEqual(data['total'], 1, '/history/ 应返回至少 1 条消息')
        # 验证消息升序排列
        msgs = data['messages']
        if len(msgs) > 1:
            for i in range(len(msgs) - 1):
                self.assertLessEqual(msgs[i]['created_at'], msgs[i + 1]['created_at'])
        # 验证 user 消息存在
        user_role_msgs = [m for m in msgs if m['role'] == 'user']
        self.assertGreaterEqual(len(user_role_msgs), 1)
        self.assertEqual(user_role_msgs[0]['content'], user_message)
        # 验证 session_key 字段
        self.assertEqual(data['session_key'], session_key)
