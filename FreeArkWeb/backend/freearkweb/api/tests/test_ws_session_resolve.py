"""
test_ws_session_resolve.py — v1.4 ChatConsumer.connect() session_key 解析的真实 WS 集成测试

填补的覆盖缺口：
  原 test_chat_memory_session.py 只同步调用 _resolve_session()，未经过 ASGI connect()
  + sync_to_async 的真实异步路径。本文件用 WebsocketCommunicator 驱动真实 connect()，
  验证 query param `session_key` 的 4 种解析结果：

    1. 不传 session_key            → 新建 session，connected 回 session_key
    2. 传有效且归属本人的 session  → 复用该 session（connected.session_key 一致），不新建
    3. 传已软删除的 session        → 降级新建（key 与传入不同），原会话保持 is_deleted
    4. 传他人的 session            → 降级新建，不跨用户访问（不复用他人 key）

只测 connect() 路径，不触发聊天流，因此无需 mock 任何 chat adapter。
信道层为 InMemoryChannelLayer（生产同款，单 worker），无需 Redis。

需求引用: REQ-FUNC-009/010/012/013, AC-009/010, ADR-Q7
"""
import asyncio

from django.test import TransactionTestCase, tag
from rest_framework.authtoken.models import Token

try:
    from channels.testing import WebsocketCommunicator
    from api.consumers import ChatConsumer
    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False

from api.models import ChatSession
from django.contrib.auth import get_user_model

User = get_user_model()


def _make_ws_app():
    from channels.routing import URLRouter
    from django.urls import re_path
    return URLRouter([
        re_path(r'^ws/chat/$', ChatConsumer.as_asgi()),
    ])


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def _connect_and_get_session_key(token_key, session_key=None):
    """连接 WS，返回 connected 消息里的 session_key，然后断开。"""
    app = _make_ws_app()
    url = f'/ws/chat/?token={token_key}'
    if session_key is not None:
        url += f'&session_key={session_key}'
    communicator = WebsocketCommunicator(app, url)
    connected, _ = await communicator.connect()
    assert connected, 'WS 应连接成功'
    msg = await communicator.receive_json_from(timeout=3)
    await communicator.disconnect()
    return msg


@tag('integration')
class WsResolveSessionTest(TransactionTestCase):

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        self.user = User.objects.create_user(username='ws_resolve_user', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.other = User.objects.create_user(username='ws_resolve_other', password='pass')
        self.other_token, _ = Token.objects.get_or_create(user=self.other)

    def test_no_session_key_creates_new(self):
        """T-WS-01: 不传 session_key → 新建 session，connected 回非空 session_key。"""
        msg = _run(_connect_and_get_session_key(self.token.key))
        self.assertEqual(msg['type'], 'connected')
        self.assertTrue(msg.get('session_key'), 'connected 应包含非空 session_key')
        self.assertTrue(
            ChatSession.objects.filter(
                user=self.user, session_key=msg['session_key'], is_deleted=False
            ).exists(),
            'connect 后应在 DB 中新建该 session',
        )

    def test_valid_own_session_key_reused(self):
        """T-WS-02: 传有效且归属本人的 session → 复用，不新建。"""
        existing = ChatSession.objects.create(user=self.user, session_key='ws-existing-key-001')
        before = ChatSession.objects.filter(user=self.user).count()

        msg = _run(_connect_and_get_session_key(self.token.key, session_key=existing.session_key))

        self.assertEqual(msg['session_key'], existing.session_key, '应复用传入的 session_key')
        after = ChatSession.objects.filter(user=self.user).count()
        self.assertEqual(after, before, '复用已有 session 不应新建记录')

    def test_deleted_session_key_falls_back_to_new(self):
        """T-WS-03: 传已软删除的 session → 降级新建（key 不同），原会话保持 is_deleted。"""
        deleted = ChatSession.objects.create(
            user=self.user, session_key='ws-deleted-key-001', is_deleted=True
        )

        msg = _run(_connect_and_get_session_key(self.token.key, session_key=deleted.session_key))

        self.assertNotEqual(
            msg['session_key'], deleted.session_key,
            '已删除的 session 不应被复用，应降级新建',
        )
        # 新 key 对应一条未删除的新 session
        self.assertTrue(
            ChatSession.objects.filter(
                user=self.user, session_key=msg['session_key'], is_deleted=False
            ).exists()
        )
        # 原已删除会话不被复活
        deleted.refresh_from_db()
        self.assertTrue(deleted.is_deleted, '原会话应仍为 is_deleted=True')

    def test_other_users_session_key_falls_back_to_new(self):
        """T-WS-04: 传他人的 session → 降级新建，不跨用户复用。"""
        foreign = ChatSession.objects.create(user=self.other, session_key='ws-foreign-key-001')

        msg = _run(_connect_and_get_session_key(self.token.key, session_key=foreign.session_key))

        self.assertNotEqual(
            msg['session_key'], foreign.session_key,
            '不应复用他人 session_key（跨用户隔离）',
        )
        # 他人会话归属不变
        foreign.refresh_from_db()
        self.assertEqual(foreign.user_id, self.other.id, '他人会话归属不应被改动')
        # 新建的 session 归属当前用户
        self.assertTrue(
            ChatSession.objects.filter(
                user=self.user, session_key=msg['session_key'], is_deleted=False
            ).exists()
        )
