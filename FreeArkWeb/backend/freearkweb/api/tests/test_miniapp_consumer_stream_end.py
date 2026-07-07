"""
test_miniapp_consumer_stream_end.py — MiniAppChatConsumer 首轮回复后必发 stream_end 帧（真实 WS 集成测试）

回归背景（BUG）：
  MiniAppChatConsumer._handle_chat() 整段覆盖了父类 ChatConsumer._handle_chat()（为注入
  user_scope），但父类的 stream_end 帧是由 _finalize_turn() 发送的，而本覆盖改成内联持久化、
  未调用 _finalize_turn，也未补发 stream_end。后果：小程序聊天页凭 stream_end 帧把 assistant
  占位气泡的 streaming 置否、解禁底部输入框；缺帧导致 isStreaming 恒真，「对话一次后输入框
  无法编辑」。本文件锁定该契约，防止再次回归。

  父类 /ws/chat/ 的 stream_end 已被 test_chat_session_e2e 覆盖，但此前没有任何测试驱动
  /ws/miniapp/chat/ 跑完整聊天流，故此 bug 一直潜伏（与 connected 帧漏发同源）。

关键约束：
  - 信道层 InMemoryChannelLayer（无需 Redis）
  - LLM 调用全部 mock，不发真实请求
  - TransactionTestCase（WS 测试跨事务边界）
"""
import asyncio

from unittest.mock import patch, AsyncMock, MagicMock

from django.test import TransactionTestCase, tag
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model

try:
    from channels.testing import WebsocketCommunicator
    from api.consumers import MiniAppChatConsumer
    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False

User = get_user_model()


def _make_ws_app():
    from channels.routing import URLRouter
    from django.urls import re_path
    return URLRouter([
        re_path(r'^ws/miniapp/chat/$', MiniAppChatConsumer.as_asgi()),
    ])


_MINIAPP_WS_LOOP = None


def _run(coro):
    # 自给自足的进程级 loop（与 test_miniapp_consumer_connected 同款）：按需懒建并复用，不关闭。
    global _MINIAPP_WS_LOOP
    if _MINIAPP_WS_LOOP is None or _MINIAPP_WS_LOOP.is_closed():
        _MINIAPP_WS_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_MINIAPP_WS_LOOP)
    return _MINIAPP_WS_LOOP.run_until_complete(coro)


@tag('integration')
class MiniAppConsumerStreamEndTest(TransactionTestCase):

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        # role=user（业主，小程序主用户；user_scope 走 OwnerUserBinding 查询分支，无绑定亦可）
        self.owner = User.objects.create_user(
            username='miniapp_owner_se', password='pass', role='user')
        self.owner_token, _ = Token.objects.get_or_create(user=self.owner)

    def _run_one_turn(self, user_text, llm_response):
        """连接 /ws/miniapp/chat/，发一条消息，消费到 stream_end，返回 (received_types, session_key)。"""
        async def _mock_stream(*args, **kwargs):
            yield ('content', llm_response)

        captured = {}

        async def _inner():
            app = _make_ws_app()
            comm = WebsocketCommunicator(app, f'/ws/miniapp/chat/?token={self.owner_token.key}')
            connected, _ = await comm.connect()
            self.assertTrue(connected, 'WS 应连接成功')

            connect_msg = await comm.receive_json_from(timeout=3)
            self.assertEqual(connect_msg['type'], 'connected')
            captured['session_key'] = connect_msg.get('session_key')

            with patch('api.consumers.get_chat_adapter') as mock_adapter, \
                 patch('api.chat_memory.generate_title_llm_async', new_callable=AsyncMock):
                adapter_instance = MagicMock()
                adapter_instance.stream_chat.return_value = _mock_stream()
                mock_adapter.return_value = adapter_instance

                await comm.send_json_to({'type': 'chat_message', 'message': user_text})

                received_types = []
                for _ in range(30):
                    try:
                        msg = await asyncio.wait_for(comm.receive_json_from(), timeout=5)
                        received_types.append(msg.get('type'))
                        if msg.get('type') == 'stream_end':
                            break
                    except asyncio.TimeoutError:
                        break

            # disconnect 尽力而为：异步标题任务（create_task）在 teardown 期可能引发
            # CancelledError（channels/asgiref 测试态竞态，与被测契约无关），显式吞掉。
            # 注意 Py3.12 下 CancelledError 继承 BaseException，须单列捕获。
            try:
                await comm.disconnect()
            except (asyncio.CancelledError, Exception):
                pass
            return received_types

        return _run(_inner()), captured['session_key']

    def test_chat_turn_sends_stream_end(self):
        """回归核心：role=user 经 /ws/miniapp/chat/ 发一条消息 → mock LLM 回复后必须收到 stream_end。
        缺帧即小程序「对话一次后输入框永久无法编辑」（本 bug）。"""
        received_types, _ = self._run_one_turn('你好', '这是模拟的助手回复内容')
        self.assertIn('stream_token', received_types,
                      f'应收到 stream_token，实际：{received_types}')
        self.assertIn('stream_end', received_types,
                      f'首轮回复必须以 stream_end 收尾（缺帧→输入框灰显），实际：{received_types}')

    def test_chat_turn_persists_user_and_assistant_messages(self):
        """回归：首轮对话后 user 与 assistant 消息都须落库（按 session 对象写入）。
        此前本覆盖漏写 user 消息、assistant 误传 session_key 字符串 → /history/ 历史残缺。"""
        from api.models import ChatSession, ChatMessage

        user_text = '业主你好，请问今天的能耗'
        llm_response = '这是模拟的助手回复内容'
        _, session_key = self._run_one_turn(user_text, llm_response)
        self.assertTrue(session_key, 'connected 帧应带 session_key')

        session = ChatSession.objects.get(user=self.owner, session_key=session_key)
        msgs = list(ChatMessage.objects.filter(session=session).order_by('created_at'))
        roles = [m.role for m in msgs]
        self.assertIn('user', roles, f'user 消息应落库，实际角色：{roles}')
        self.assertIn('assistant', roles, f'assistant 消息应落库，实际角色：{roles}')

        user_msg = next(m for m in msgs if m.role == 'user')
        self.assertEqual(user_msg.content, user_text, 'user 消息应存原始文本（不含注入前缀）')
        # v1.12.0 加入人格问候语后，新会话首次发言会自动写入问候语为首条 assistant 消息，
        # 因此 LLM 回复不再是唯一的 assistant 消息——改用「内容包含」断言。
        assistant_contents = [m.content for m in msgs if m.role == 'assistant']
        self.assertIn(llm_response, assistant_contents,
                      f'LLM 回复的内容应存在于 assistant 消息中，实际内容：{assistant_contents}')
