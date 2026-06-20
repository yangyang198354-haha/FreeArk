"""
test_ws_session_resolve.py — ChatConsumer.connect() 的 session_key 处理（真实 WS 集成测试）

ADR-001 策略 A 改写说明：
  connect() 不再创建 DB 记录、也不解析/校验 session_key（_resolve_session 已删除），
  仅把传入的 session_key 原样保存为字符串（未传则生成新 UUID）。会话的解析/复用/降级
  全部延后到首条消息时由 _ensure_session_created() 完成。
  因此本文件用 WebsocketCommunicator 驱动真实 connect()，验证 connect 的契约：

    1. 不传 session_key            → connected 回非空 session_key，DB 无记录（不落库）
    2. 传有效且归属本人的 session  → connected 原样回该 key，connect 不新建记录
    3. 传已软删除的 session        → connected 原样回该 key，connect 不查/不写 DB，原会话保持 is_deleted
    4. 传他人的 session            → connected 原样回该 key（仅回显字符串），不访问/改动他人会话

  首条消息时的复用/降级（含跨用户隔离、已删除不复活）见
  test_chat_memory_session.ResolveSessionTest（_ensure_session_created 单元覆盖）。

只测 connect() 路径，不触发聊天流，因此无需 mock 任何 chat adapter。
信道层为 InMemoryChannelLayer（生产同款，单 worker），无需 Redis。

需求引用: REQ-FUNC-009/010/012/013, AC-009/010, ADR-001
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


_WS_RESOLVE_LOOP = None


def _run(coro):
    # 自给自足的进程级 loop：不依赖 asyncio.get_event_loop()（Py3.12 下且其它用例
    # 可能已关闭全局 loop），按需懒建并复用，不关闭，避免跨用例污染。
    global _WS_RESOLVE_LOOP
    if _WS_RESOLVE_LOOP is None or _WS_RESOLVE_LOOP.is_closed():
        _WS_RESOLVE_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_WS_RESOLVE_LOOP)
    return _WS_RESOLVE_LOOP.run_until_complete(coro)


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

    def test_no_session_key_connect_no_db(self):
        """T-WS-01（ADR-001 改写）：不传 session_key → connected 回非空 session_key，
        但 connect 不落库（首条消息前 DB 无记录）。"""
        msg = _run(_connect_and_get_session_key(self.token.key))
        self.assertEqual(msg['type'], 'connected')
        self.assertTrue(msg.get('session_key'), 'connected 应包含非空 session_key')
        # ADR-001 策略 A：connect 不创建 DB 记录
        self.assertFalse(
            ChatSession.objects.filter(user=self.user).exists(),
            'ADR-001：connect 但未发消息时不应创建 ChatSession',
        )

    def test_valid_own_session_key_reused(self):
        """T-WS-02: 传有效且归属本人的 session → 复用，不新建。"""
        existing = ChatSession.objects.create(user=self.user, session_key='ws-existing-key-001')
        before = ChatSession.objects.filter(user=self.user).count()

        msg = _run(_connect_and_get_session_key(self.token.key, session_key=existing.session_key))

        self.assertEqual(msg['session_key'], existing.session_key, '应复用传入的 session_key')
        after = ChatSession.objects.filter(user=self.user).count()
        self.assertEqual(after, before, '复用已有 session 不应新建记录')

    def test_deleted_session_key_returned_asis_no_db(self):
        """T-WS-03（ADR-001 改写）：传已软删除的 session_key → connect 原样回该 key 且不查/不写 DB；
        复用/降级延后到首条消息（见 ResolveSessionTest）。原会话保持 is_deleted。"""
        deleted = ChatSession.objects.create(
            user=self.user, session_key='ws-deleted-key-001', is_deleted=True
        )

        msg = _run(_connect_and_get_session_key(self.token.key, session_key=deleted.session_key))

        # ADR-001：connect 不解析，原样回传 key
        self.assertEqual(msg['session_key'], deleted.session_key)
        # connect 不落库：不应新建未删除的同 key 会话
        self.assertFalse(
            ChatSession.objects.filter(
                session_key='ws-deleted-key-001', is_deleted=False
            ).exists(),
            'connect 不应创建会话',
        )
        # 原已删除会话不被复活
        deleted.refresh_from_db()
        self.assertTrue(deleted.is_deleted, '原会话应仍为 is_deleted=True')

    def test_foreign_session_key_returned_asis_no_db(self):
        """T-WS-04（ADR-001 改写）：传他人的 session_key → connect 原样回传且不访问 DB；
        跨用户隔离在首条消息时通过降级实现（见 ResolveSessionTest）。他人会话不受影响。"""
        foreign = ChatSession.objects.create(user=self.other, session_key='ws-foreign-key-001')

        msg = _run(_connect_and_get_session_key(self.token.key, session_key=foreign.session_key))

        # ADR-001：connect 不解析，原样回传（仅回显字符串，未读取任何他人数据）
        self.assertEqual(msg['session_key'], foreign.session_key)
        # connect 不落库：不应为当前用户新建该 key 的会话
        self.assertFalse(
            ChatSession.objects.filter(
                user=self.user, session_key='ws-foreign-key-001'
            ).exists(),
            'connect 不应为当前用户创建会话',
        )
        # 他人会话归属不变
        foreign.refresh_from_db()
        self.assertEqual(foreign.user_id, self.other.id, '他人会话归属不应被改动')
