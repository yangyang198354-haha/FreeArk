"""
test_chat_session_feature.py — FreeArk_ChatSession 功能测试（单元 + 集成）

测试目标：
  GROUP_D 单元测试：
    - TC-UNIT-001~004: generate_title_truncate（截断逻辑）
    - TC-UNIT-005~007: generate_title_llm_async（mock LLM，DB 更新/保留截断标题）
    - TC-UNIT-008~010: get_session_history（正常/不存在/跨用户）
    - TC-UNIT-011~012: _ensure_session_created（首次创建/幂等）
    - TC-UNIT-013~014: get_sessions title 字段

  GROUP_D 集成测试：
    - TC-INT-001~004: GET /api/memory/session/{key}/history/（正常/空/404/401）
    - TC-INT-005~006: GET /api/memory/me/ title 字段
    - TC-INT-007~008: WS connect 不落库 / 首条消息落库（InMemory channel layer）

需求溯源：
  US-001 AC-001-02, US-002 AC-002-01, US-003 AC-003-01/03,
  US-004 AC-004-01/02, US-005 AC-005-01, US-006 AC-006-01, US-007 AC-007-01
"""

import asyncio
import uuid
from unittest.mock import patch, AsyncMock, MagicMock

from django.test import TestCase, TransactionTestCase, tag
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import ChatSession, ChatMessage
from api import chat_memory

User = get_user_model()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_user(username):
    return User.objects.create_user(username=username, password='testpass123')


def _auth_client(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _session(user, key=None):
    k = key or str(uuid.uuid4())
    return ChatSession.objects.create(user=user, session_key=k)


def _msgs(session, n):
    """向 session 写入 n 条 user 消息 + n 条 assistant 消息（共 2n 条）。"""
    for i in range(n):
        ChatMessage.objects.create(session=session, role='user', content=f'user-msg-{i}')
        ChatMessage.objects.create(session=session, role='assistant', content=f'asst-msg-{i}')


# ============================================================================
# 单元测试：generate_title_truncate
# ============================================================================

@tag('unit')
class GenerateTitleTruncateTest(TestCase):
    """TC-UNIT-001~004: generate_title_truncate 截断逻辑。"""

    def test_tc_unit_001_truncates_long_content(self):
        """TC-UNIT-001 (AC-004-01): 内容超过 max_len，截断并追加 '...'。"""
        content = 'A' * 40
        result = chat_memory.generate_title_truncate(content, max_len=30)
        self.assertLessEqual(len(result), 30)
        self.assertTrue(result.endswith('...'), f'截断结果应以 ... 结尾，实际：{result!r}')
        # 截断内容应是前 27 字符 + '...'
        self.assertEqual(result, 'A' * 27 + '...')

    def test_tc_unit_002_no_truncation_for_short_content(self):
        """TC-UNIT-002 (AC-004-01): 内容 ≤ max_len，原样返回。"""
        content = '短消息'
        result = chat_memory.generate_title_truncate(content, max_len=30)
        self.assertEqual(result, '短消息')
        self.assertFalse(result.endswith('...'))

    def test_tc_unit_003_empty_string_returns_empty(self):
        """TC-UNIT-003 (AC-004-01): 空字符串输入返回空字符串。"""
        result = chat_memory.generate_title_truncate('', max_len=30)
        self.assertEqual(result, '')

    def test_tc_unit_004_exactly_max_len_not_truncated(self):
        """TC-UNIT-004 (AC-004-01): 长度恰好等于 max_len，原样返回（不截断）。"""
        content = 'B' * 30
        result = chat_memory.generate_title_truncate(content, max_len=30)
        self.assertEqual(result, content)
        self.assertFalse(result.endswith('...'))

    def test_truncate_default_max_len_is_30(self):
        """边界：不传 max_len 时默认为 30。"""
        content = 'C' * 31
        result = chat_memory.generate_title_truncate(content)
        self.assertLessEqual(len(result), 30)
        self.assertTrue(result.endswith('...'))


# ============================================================================
# 单元测试：generate_title_llm_async
# ============================================================================

@tag('unit')
class GenerateTitleLlmAsyncTest(TransactionTestCase):
    """TC-UNIT-005~007: generate_title_llm_async（mock LLM）。

    使用 TransactionTestCase 以支持 sync_to_async（跨线程 DB 操作需要真实事务可见性）。
    """

    def setUp(self):
        self.user = _make_user('llm_async_user')
        self.session = _session(self.user, 'sk-llm-test-0001')
        # 预写截断标题（LLM 失败时应保留此值）
        self.session.title = '截断标题'
        self.session.save(update_fields=['title'])

    def _run_async(self, coro):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_tc_unit_005_llm_success_updates_title(self):
        """TC-UNIT-005 (AC-004-02): LLM 成功，DB title 被更新为 LLM 返回的标题。

        使用 TransactionTestCase 级别的直接 DB 验证：
        通过 ChatSession.objects.filter().update() 验证 sync_to_async 内部 ORM 写入。
        由于 generate_title_llm_async 用 sync_to_async 包装 _update_title，
        在 TestCase 事务边界内验证跨线程 ORM 更新需要 ATOMIC_REQUESTS=False。
        此测试验证 LLM 成功时 _update_title 被调用，且不抛异常。
        """
        import sys
        mock_choice = MagicMock()
        mock_choice.message.content = '这是LLM生成的标题'
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        mock_openai_module = MagicMock()
        mock_openai_module.AsyncOpenAI.return_value = mock_client

        original = sys.modules.get('openai')
        sys.modules['openai'] = mock_openai_module
        exception_raised = []
        try:
            with patch.object(
                __import__('django.conf', fromlist=['settings']).settings,
                'DEEPSEEK_API_KEY', 'fake-api-key', create=True
            ):
                # 验证函数正常执行，不抛异常（LLM 成功路径）
                try:
                    self._run_async(
                        chat_memory.generate_title_llm_async(
                            session_id=self.session.pk,
                            first_user_msg='测试用户消息',
                            first_assistant_msg='测试助手回复',
                        )
                    )
                except Exception as e:
                    exception_raised.append(str(e))
        finally:
            if original is None:
                sys.modules.pop('openai', None)
            else:
                sys.modules['openai'] = original

        # 验证 LLM 成功路径不抛异常（函数有全局 except 兜底）
        self.assertEqual(exception_raised, [], f'generate_title_llm_async 不应向外抛异常: {exception_raised}')
        # 验证 LLM 被正确调用（mock 对象被调用）
        mock_client.chat.completions.create.assert_called_once()
        # 验证 DB 更新（通过直接查询，sync_to_async 在同一事件循环中执行）
        self.session.refresh_from_db()
        # LLM 成功时 title 应被更新为生成标题
        self.assertEqual(
            self.session.title, '这是LLM生成的标题',
            f'LLM 成功时 title 应为 LLM 返回值，实际：{self.session.title!r}',
        )

    def test_tc_unit_006_llm_exception_preserves_truncated_title(self):
        """TC-UNIT-006 (AC-005-01): LLM 抛异常，截断标题不被清空。"""
        original_title = self.session.title  # '截断标题'

        import sys
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(
            side_effect=Exception('LLM 网络超时')
        )
        mock_openai_module = MagicMock()
        mock_openai_module.AsyncOpenAI.return_value = mock_client

        original = sys.modules.get('openai')
        sys.modules['openai'] = mock_openai_module
        try:
            with patch.object(
                __import__('django.conf', fromlist=['settings']).settings,
                'DEEPSEEK_API_KEY', 'fake-api-key', create=True
            ):
                self._run_async(
                    chat_memory.generate_title_llm_async(
                        session_id=self.session.pk,
                        first_user_msg='用户消息',
                        first_assistant_msg='助手回复',
                    )
                )
        finally:
            if original is None:
                del sys.modules['openai']
            else:
                sys.modules['openai'] = original

        self.session.refresh_from_db()
        self.assertEqual(
            self.session.title, original_title,
            f'LLM 异常时应保留截断标题，实际 title={self.session.title!r}',
        )

    def test_tc_unit_007_llm_empty_string_preserves_truncated_title(self):
        """TC-UNIT-007 (AC-005-01): LLM 返回空字符串，截断标题不被清空。"""
        original_title = self.session.title  # '截断标题'

        import sys
        mock_choice = MagicMock()
        mock_choice.message.content = ''  # LLM 返回空字符串
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        mock_openai_module = MagicMock()
        mock_openai_module.AsyncOpenAI.return_value = mock_client

        original = sys.modules.get('openai')
        sys.modules['openai'] = mock_openai_module
        try:
            with patch.object(
                __import__('django.conf', fromlist=['settings']).settings,
                'DEEPSEEK_API_KEY', 'fake-api-key', create=True
            ):
                self._run_async(
                    chat_memory.generate_title_llm_async(
                        session_id=self.session.pk,
                        first_user_msg='用户消息',
                        first_assistant_msg='助手回复',
                    )
                )
        finally:
            if original is None:
                del sys.modules['openai']
            else:
                sys.modules['openai'] = original

        self.session.refresh_from_db()
        self.assertEqual(
            self.session.title, original_title,
            f'LLM 返回空字符串时应保留截断标题，实际 title={self.session.title!r}',
        )

    def test_tc_unit_no_api_key_no_update(self):
        """AC-005-01 降级：DEEPSEEK_API_KEY 未配置时，不更新 title，不抛异常。"""
        original_title = self.session.title

        with patch.object(
            __import__('django.conf', fromlist=['settings']).settings,
            'DEEPSEEK_API_KEY', '', create=True
        ):
            self._run_async(
                chat_memory.generate_title_llm_async(
                    session_id=self.session.pk,
                    first_user_msg='测试消息',
                    first_assistant_msg='测试回复',
                )
            )

        self.session.refresh_from_db()
        self.assertEqual(self.session.title, original_title)


# ============================================================================
# 单元测试：get_session_history
# ============================================================================

@tag('unit')
class GetSessionHistoryTest(TestCase):
    """TC-UNIT-008~010: get_session_history（归属校验、顺序、跨用户）。"""

    def setUp(self):
        self.user = _make_user('hist_user')
        self.session = _session(self.user, 'sk-hist-0001')
        _msgs(self.session, 3)  # 6 条消息

    def test_tc_unit_008_normal_returns_ordered_messages(self):
        """TC-UNIT-008 (AC-006-01): 正常返回，按 created_at 升序，role 字段正确。"""
        result = chat_memory.get_session_history(self.user, 'sk-hist-0001', limit=40)
        self.assertEqual(len(result), 6)
        # 验证升序
        for i in range(len(result) - 1):
            self.assertLessEqual(result[i]['created_at'], result[i + 1]['created_at'])
        # 验证第一条是 user 消息
        self.assertEqual(result[0]['role'], 'user')
        self.assertEqual(result[0]['content'], 'user-msg-0')
        # 验证字段存在
        for msg in result:
            self.assertIn('role', msg)
            self.assertIn('content', msg)
            self.assertIn('created_at', msg)
            self.assertIn(msg['role'], ('user', 'assistant'))

    def test_tc_unit_009_nonexistent_session_raises_valueerror(self):
        """TC-UNIT-009 (US-007): session 不存在，抛 ValueError。"""
        with self.assertRaises(ValueError):
            chat_memory.get_session_history(self.user, 'sk-does-not-exist', limit=40)

    def test_tc_unit_010_other_user_session_raises_valueerror(self):
        """TC-UNIT-010 (AC-006-01 安全性): 跨用户访问抛 ValueError。"""
        other_user = _make_user('hist_other_user')
        with self.assertRaises(ValueError):
            chat_memory.get_session_history(other_user, 'sk-hist-0001', limit=40)

    def test_history_limit_respected(self):
        """AC-006-01: limit=40 时，45 条消息只返回 40 条。"""
        # 创建含 25 轮（50 条）消息的 session
        big_session = _session(self.user, 'sk-hist-big')
        _msgs(big_session, 25)  # 50 条
        result = chat_memory.get_session_history(self.user, 'sk-hist-big', limit=40)
        self.assertLessEqual(len(result), 40)

    def test_empty_session_returns_empty_list(self):
        """AC-007-01: 无消息 session 返回空列表。"""
        empty_session = _session(self.user, 'sk-hist-empty')
        result = chat_memory.get_session_history(self.user, 'sk-hist-empty', limit=40)
        self.assertEqual(result, [])

    def test_soft_deleted_session_raises_valueerror(self):
        """软删除 session 不可访问。"""
        deleted = _session(self.user, 'sk-hist-deleted')
        deleted.is_deleted = True
        deleted.save(update_fields=['is_deleted'])
        with self.assertRaises(ValueError):
            chat_memory.get_session_history(self.user, 'sk-hist-deleted', limit=40)


# ============================================================================
# 单元测试：_ensure_session_created（mock DB）
# ============================================================================

@tag('integration')
class EnsureSessionCreatedTest(TransactionTestCase):
    """TC-UNIT-011~012: _ensure_session_created 首次创建和幂等。"""

    def setUp(self):
        try:
            from channels.testing import WebsocketCommunicator
            from api.consumers import ChatConsumer
            self._channels_ok = True
        except ImportError:
            self._channels_ok = False

    def _run(self, coro):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def test_tc_unit_011_first_call_creates_session(self):
        """TC-UNIT-011 (AC-001-02): 首次调用 _ensure_session_created，创建 ChatSession。"""
        if not self._channels_ok:
            self.skipTest('channels 不可用')
        from api.consumers import ChatConsumer

        user = User.objects.create_user(username='esc_test_user_011', password='pass')
        sk = str(uuid.uuid4())

        consumer = ChatConsumer()
        consumer.user = user
        consumer.session_key = sk
        consumer.chat_session = None
        consumer._session_created = False

        self._run(consumer._ensure_session_created('这是首条用户消息，内容比较长一些方便测试截断逻辑'))

        # 验证 ChatSession 被创建
        self.assertTrue(
            ChatSession.objects.filter(user=user, session_key=sk).exists(),
            '首次调用应创建 ChatSession',
        )
        # 验证 _session_created 标记已设置
        self.assertTrue(consumer._session_created)
        # 验证 chat_session 实例变量已设置
        self.assertIsNotNone(consumer.chat_session)
        # 验证 title 已写入（截断标题）
        session_obj = ChatSession.objects.get(session_key=sk)
        self.assertIsNotNone(session_obj.title)
        self.assertNotEqual(session_obj.title, '')

    def test_tc_unit_012_idempotent_second_call(self):
        """TC-UNIT-012 (AC-001-02 幂等): _session_created=True 时重复调用不重复创建。"""
        if not self._channels_ok:
            self.skipTest('channels 不可用')
        from api.consumers import ChatConsumer

        user = User.objects.create_user(username='esc_test_user_012', password='pass')
        sk = str(uuid.uuid4())
        existing = ChatSession.objects.create(user=user, session_key=sk)

        consumer = ChatConsumer()
        consumer.user = user
        consumer.session_key = sk
        consumer.chat_session = existing
        consumer._session_created = True  # 已创建

        self._run(consumer._ensure_session_created('第二次调用'))

        # 不应新增 ChatSession
        count = ChatSession.objects.filter(user=user, session_key=sk).count()
        self.assertEqual(count, 1, '_session_created=True 时不应重复创建')


# ============================================================================
# 单元测试：get_sessions title 字段
# ============================================================================

@tag('unit')
class GetSessionsTitleFieldTest(TestCase):
    """TC-UNIT-013~014: get_sessions 返回 title 字段。"""

    def setUp(self):
        self.user = _make_user('title_field_user')

    def test_tc_unit_013_title_field_present_and_correct(self):
        """TC-UNIT-013 (AC-003-01): get_sessions 返回 title 字段，值与 DB 一致。"""
        sess = _session(self.user, 'sk-title-test-01')
        sess.title = '测试标题内容'
        sess.save(update_fields=['title'])

        result = chat_memory.get_sessions(self.user)
        self.assertEqual(result['total'], 1)
        session_data = result['sessions'][0]
        self.assertIn('title', session_data)
        self.assertEqual(session_data['title'], '测试标题内容')

    def test_tc_unit_014_old_session_title_is_null(self):
        """TC-UNIT-014 (AC-003-03): 旧会话（title=None）的 title 字段为 None（不报错）。"""
        _session(self.user, 'sk-title-test-02')  # 不设 title，默认 None

        result = chat_memory.get_sessions(self.user)
        self.assertEqual(result['total'], 1)
        session_data = result['sessions'][0]
        self.assertIn('title', session_data)
        self.assertIsNone(session_data['title'])


# ============================================================================
# 集成测试：GET /api/memory/session/{key}/history/
# ============================================================================

@tag('integration')
class SessionHistoryViewTest(TestCase):
    """TC-INT-001~004: SessionHistoryView REST 端点。"""

    def setUp(self):
        self.user = _make_user('hist_view_user')
        self.client = _auth_client(self.user)
        self.session = _session(self.user, 'sk-hist-view-0001')
        _msgs(self.session, 5)  # 10 条消息

    def test_tc_int_001_normal_returns_200_with_ordered_messages(self):
        """TC-INT-001 (AC-006-01): 正常返回 200，messages 按升序，total 正确。"""
        resp = self.client.get(f'/api/memory/session/{self.session.session_key}/history/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('session_key', data)
        self.assertIn('messages', data)
        self.assertIn('total', data)
        self.assertEqual(data['total'], len(data['messages']))
        self.assertEqual(data['total'], 10)
        # 验证升序
        msgs = data['messages']
        for i in range(len(msgs) - 1):
            self.assertLessEqual(msgs[i]['created_at'], msgs[i + 1]['created_at'])
        # 验证 role 字段
        for msg in msgs:
            self.assertIn(msg['role'], ('user', 'assistant'))

    def test_tc_int_001_limit_40_for_large_session(self):
        """TC-INT-001 (AC-006-01): 消息超过 40 条时只返回 40 条。"""
        big_session = _session(self.user, 'sk-hist-view-big')
        _msgs(big_session, 25)  # 50 条
        resp = self.client.get(f'/api/memory/session/{big_session.session_key}/history/')
        data = resp.json()
        self.assertLessEqual(data['total'], 40)

    def test_tc_int_002_empty_session_returns_empty_list(self):
        """TC-INT-002 (AC-007-01): 无消息 session 返回空列表，total=0。"""
        empty = _session(self.user, 'sk-hist-view-empty')
        resp = self.client.get(f'/api/memory/session/{empty.session_key}/history/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['messages'], [])
        self.assertEqual(data['total'], 0)

    def test_tc_int_003_other_user_session_returns_404(self):
        """TC-INT-003 (AC-006-01 安全): 非归属用户访问返回 404。"""
        other_user = _make_user('hist_view_other')
        other_client = _auth_client(other_user)
        resp = other_client.get(f'/api/memory/session/{self.session.session_key}/history/')
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertIn('detail', data)

    def test_tc_int_004_unauthenticated_returns_401_or_403(self):
        """TC-INT-004 (AC-006-01 认证): 未认证访问返回 401/403。"""
        anon_client = APIClient()
        resp = anon_client.get(f'/api/memory/session/{self.session.session_key}/history/')
        self.assertIn(resp.status_code, [401, 403])

    def test_nonexistent_session_returns_404(self):
        """不存在的 session_key 返回 404。"""
        resp = self.client.get('/api/memory/session/nonexistent-key/history/')
        self.assertEqual(resp.status_code, 404)


# ============================================================================
# 集成测试：GET /api/memory/me/ title 字段
# ============================================================================

@tag('integration')
class GetSessionsTitleIntegrationTest(TestCase):
    """TC-INT-005~006: GET /api/memory/me/ 新增 title 字段。"""

    def setUp(self):
        self.user = _make_user('sessions_title_view_user')
        self.client = _auth_client(self.user)

    def test_tc_int_005_sessions_contain_title_field(self):
        """TC-INT-005 (AC-003-01): sessions 数组中每个 session 含 title 字段，值正确。"""
        sess = _session(self.user, 'sk-int-title-01')
        sess.title = '集成测试标题'
        sess.save(update_fields=['title'])

        resp = self.client.get('/api/memory/me/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['total'], 1)
        session_data = data['sessions'][0]
        self.assertIn('title', session_data)
        self.assertEqual(session_data['title'], '集成测试标题')

    def test_tc_int_006_old_session_title_null(self):
        """TC-INT-006 (AC-003-03): 旧会话（title=None）的 API 响应 title=null。"""
        _session(self.user, 'sk-int-title-02')  # 不设 title

        resp = self.client.get('/api/memory/me/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        session_data = data['sessions'][0]
        self.assertIn('title', session_data)
        self.assertIsNone(session_data['title'])


# ============================================================================
# 集成测试：WS connect 不落库 / 首条消息落库
# ============================================================================

_run_loop = None


def _run_ws(coro):
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


@tag('integration')
class WsNoDbOnConnectTest(TransactionTestCase):
    """TC-INT-007: WS connect 不产生 DB 记录（ADR-001 策略 A）。"""

    def setUp(self):
        try:
            from channels.testing import WebsocketCommunicator
            self._channels_ok = True
        except ImportError:
            self._channels_ok = False
        self.user = User.objects.create_user(username='ws_no_db_user', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_tc_int_007_connect_no_db_record(self):
        """TC-INT-007 (AC-002-01): WS connect 不创建 ChatSession，disconnect 后 DB 无记录。"""
        if not self._channels_ok:
            self.skipTest('channels.testing 不可用')
        from channels.testing import WebsocketCommunicator

        async def _inner():
            app = _make_ws_app()
            comm = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await comm.connect()
            self.assertTrue(connected)
            # 接收 connected 消息
            msg = await comm.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'connected')
            # 不发送任何消息，直接断开
            await comm.disconnect()

        _run_ws(_inner())
        # 验证 DB 中无 ChatSession 记录
        count = ChatSession.objects.filter(user=self.user).count()
        self.assertEqual(count, 0, f'connect 但不发消息时，DB 应无 ChatSession，实际 count={count}')


@tag('integration')
class WsFirstMessageCreatesSessionTest(TransactionTestCase):
    """TC-INT-008: 发送首条消息后，ChatSession 存在且 title 非空。"""

    def setUp(self):
        try:
            from channels.testing import WebsocketCommunicator
            self._channels_ok = True
        except ImportError:
            self._channels_ok = False
        self.user = User.objects.create_user(username='ws_first_msg_user', password='pass')
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_tc_int_008_first_message_creates_session_with_title(self):
        """TC-INT-008 (AC-001-02, AC-004-01): 首条消息后 ChatSession 创建，title 为截断文本。"""
        if not self._channels_ok:
            self.skipTest('channels.testing 不可用')
        import json
        from channels.testing import WebsocketCommunicator

        mock_response_content = '这是模拟的LLM回复内容'

        async def _mock_stream(*args, **kwargs):
            yield ('content', mock_response_content)

        async def _inner():
            app = _make_ws_app()
            comm = WebsocketCommunicator(app, f'/ws/chat/?token={self.token.key}')
            connected, _ = await comm.connect()
            self.assertTrue(connected)

            # 接收 connected 消息
            msg = await comm.receive_json_from(timeout=3)
            self.assertEqual(msg['type'], 'connected')

            # mock LLM adapter（避免真实 LLM 调用）
            # 同时 mock generate_title_llm_async 避免异步 LLM 标题生成
            with patch('api.consumers.get_chat_adapter') as mock_adapter, \
                 patch('api.chat_memory.generate_title_llm_async', new_callable=AsyncMock) as mock_title:
                adapter_instance = MagicMock()
                adapter_instance.stream_chat.return_value = _mock_stream()
                mock_adapter.return_value = adapter_instance

                # 发送首条用户消息
                await comm.send_json_to({
                    'type': 'chat_message',
                    'message': '这是首条测试消息，内容比较长用于测试截断标题功能',
                })

                # 消费 WS 消息流直到收到 stream_end
                received = []
                for _ in range(20):
                    try:
                        msg = await asyncio.wait_for(comm.receive_json_from(), timeout=5)
                        received.append(msg)
                        if msg.get('type') == 'stream_end':
                            break
                    except asyncio.TimeoutError:
                        break

            await comm.disconnect()

        _run_ws(_inner())

        # 验证 DB 中存在 ChatSession
        sessions = ChatSession.objects.filter(user=self.user)
        self.assertEqual(sessions.count(), 1, '首条消息后应有 1 个 ChatSession')
        sess = sessions.first()
        # 验证 title 已写入截断文本（非空）
        self.assertIsNotNone(sess.title, 'ChatSession.title 不应为 None（应写入截断标题）')
        self.assertNotEqual(sess.title, '', 'ChatSession.title 不应为空字符串')
