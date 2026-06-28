"""
test_miniapp_consumer_connected.py — MiniAppChatConsumer.connect() 必发 connected 帧（真实 WS 集成测试）

回归背景（BUG）：
  MiniAppChatConsumer 整段覆盖了父类 ChatConsumer.connect()（为放行 role=user、构造
  user_scope），但复制时漏发了父类 accept() 后的 connected 帧。后果：小程序聊天页
  凭 connected 帧（而非 onOpen）才把 wsConnected 置真、解禁输入框；缺帧导致输入框
  永久灰显、无法输入。本文件锁定该契约，防止再次回归。

  父类 /ws/chat/ 的 connected 帧已被 test_ws_session_resolve 等覆盖，但此前没有任何
  测试连 /ws/miniapp/chat/，故此 bug 一直潜伏。

只测 connect() 路径，不触发聊天流，无需 mock 任何 chat adapter。
信道层为 InMemoryChannelLayer，无需 Redis。
"""
import asyncio

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
    # 自给自足的进程级 loop（与 test_ws_session_resolve 同款）：按需懒建并复用，不关闭，
    # 避免 Py3.12 下全局 loop 已被其它用例关闭的污染问题。
    global _MINIAPP_WS_LOOP
    if _MINIAPP_WS_LOOP is None or _MINIAPP_WS_LOOP.is_closed():
        _MINIAPP_WS_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_MINIAPP_WS_LOOP)
    return _MINIAPP_WS_LOOP.run_until_complete(coro)


async def _connect_and_get_first_frame(token_key, session_key=None):
    """连接 /ws/miniapp/chat/，返回首帧（应为 connected），然后断开。"""
    app = _make_ws_app()
    url = f'/ws/miniapp/chat/?token={token_key}'
    if session_key is not None:
        url += f'&session_key={session_key}'
    communicator = WebsocketCommunicator(app, url)
    connected, _ = await communicator.connect()
    assert connected, 'WS 应连接成功'
    msg = await communicator.receive_json_from(timeout=3)
    await communicator.disconnect()
    return msg


@tag('integration')
class MiniAppConsumerConnectedFrameTest(TransactionTestCase):

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        # role=user（业主，小程序主用户；user_scope 走 OwnerUserBinding 查询分支）
        self.owner = User.objects.create_user(
            username='miniapp_owner', password='pass', role='user')
        self.owner_token, _ = Token.objects.get_or_create(user=self.owner)
        # role=operator（user_scope=None 直通分支，向后兼容）
        self.operator = User.objects.create_user(
            username='miniapp_operator', password='pass', role='operator')
        self.operator_token, _ = Token.objects.get_or_create(user=self.operator)

    def test_owner_connect_sends_connected_frame(self):
        """回归核心：role=user 连接 /ws/miniapp/chat/ → 必须收到 connected 帧且 session_key 非空。
        缺帧即小程序输入框永久灰显（本 bug）。"""
        msg = _run(_connect_and_get_first_frame(self.owner_token.key))
        self.assertEqual(msg['type'], 'connected', 'accept() 后必须发 connected 帧')
        self.assertTrue(msg.get('session_key'), 'connected 应包含非空 session_key')

    def test_operator_connect_sends_connected_frame(self):
        """admin/operator 经小程序 consumer 连接（user_scope=None 直通）同样必须收到 connected 帧。"""
        msg = _run(_connect_and_get_first_frame(self.operator_token.key))
        self.assertEqual(msg['type'], 'connected')
        self.assertTrue(msg.get('session_key'))

    def test_connect_echoes_passed_session_key(self):
        """传入 session_key → connected 帧原样回显（恢复已有会话场景）。"""
        msg = _run(_connect_and_get_first_frame(
            self.owner_token.key, session_key='miniapp-existing-key-001'))
        self.assertEqual(msg['type'], 'connected')
        self.assertEqual(msg['session_key'], 'miniapp-existing-key-001')
