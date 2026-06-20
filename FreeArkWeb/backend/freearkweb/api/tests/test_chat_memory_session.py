"""
test_chat_memory_session.py — FreeArk_ChatRebranding_SessionMgmt 单元测试

测试目标（GROUP_D / PHASE_07 单元测试）：
  - T-CRIT-01: 会话隔离（load_history_by_session 跨 session 不串味）
  - T-CRIT-02: 历史 20 轮上限（load_history_by_session limit 截断最近 N 轮）
  - T-CRIT-03a: 软删除过滤（get_sessions is_deleted=False 过滤）
  - T-CRIT-03b: soft_delete_session 归属校验
  - T-CRIT-03c: soft_delete_session 幂等保护（重复删除抛 ValueError）
  - T-UNIT-01 ~ T-UNIT-12: load_history_by_session / soft_delete_session / get_sessions 全路径

需求溯源:
  US-008 AC-008-01~03, US-009 AC-009-01~03, US-010 AC-010-01~03,
  US-011 AC-011-01~03, US-012 AC-012-01~02, US-013 AC-013-01~02
"""

import asyncio

from django.test import TestCase, override_settings, tag
from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from api.models import ChatSession, ChatMessage
from api import chat_memory

User = get_user_model()


def _user(username):
    return User.objects.create_user(username=username, password='testpass123')


def _session(user, key):
    return chat_memory.create_session(user, key)


def _msgs(session, n_turns):
    """向 session 写入 n_turns 轮消息（user + assistant）。"""
    for i in range(n_turns):
        chat_memory.append_message(session, 'user', f'user-msg-{i}')
        chat_memory.append_message(session, 'assistant', f'assistant-msg-{i}')


# ---------------------------------------------------------------------------
# T-UNIT-01: load_history_by_session — 空 session 返回空列表
# AC: US-012 AC-012-01 (会话内上下文保留，无历史时返回空)
# ---------------------------------------------------------------------------
@tag('unit')
class LoadHistoryBySessionEmptyTest(TestCase):
    def test_empty_session_returns_empty_list(self):
        """T-UNIT-01: 空 session（无消息）调用 load_history_by_session 返回空列表。"""
        user = _user('t_unit_01_user')
        sess = _session(user, 'sk-t-unit-01')
        result = chat_memory.load_history_by_session(sess)
        self.assertEqual(result, [])
        self.assertIsInstance(result, list)


# ---------------------------------------------------------------------------
# T-UNIT-02: load_history_by_session — 正常路径，返回升序列表
# AC: US-012 AC-012-01
# ---------------------------------------------------------------------------
@tag('unit')
class LoadHistoryBySessionBasicTest(TestCase):
    def setUp(self):
        self.user = _user('t_unit_02_user')
        self.sess = _session(self.user, 'sk-t-unit-02')
        chat_memory.append_message(self.sess, 'user', '你好')
        chat_memory.append_message(self.sess, 'assistant', '你好，有什么可以帮助你的？')
        chat_memory.append_message(self.sess, 'user', '帮我写代码')
        chat_memory.append_message(self.sess, 'assistant', '好的，请描述需求')

    def test_returns_messages_in_order(self):
        """T-UNIT-02: 正常路径，消息按升序返回，role 和 content 正确。"""
        result = chat_memory.load_history_by_session(self.sess)
        self.assertEqual(len(result), 4)
        self.assertEqual(result[0]['role'], 'user')
        self.assertEqual(result[0]['content'], '你好')
        self.assertEqual(result[-1]['role'], 'assistant')
        self.assertEqual(result[-1]['content'], '好的，请描述需求')

    def test_returns_list_of_dicts(self):
        """T-UNIT-02b: 返回值是 list[dict]，每项含 role 和 content 键。"""
        result = chat_memory.load_history_by_session(self.sess)
        for item in result:
            self.assertIn('role', item)
            self.assertIn('content', item)
            self.assertIn(item['role'], ('user', 'assistant'))


# ---------------------------------------------------------------------------
# T-CRIT-01 / T-UNIT-03: 会话隔离
# AC: US-013 AC-013-01, US-013 AC-013-02, US-010 AC-010-02
# ---------------------------------------------------------------------------
@tag('unit')
class LoadHistoryBySessionIsolationTest(TestCase):
    """T-CRIT-01: load_history_by_session 确保跨 session 历史不串味。"""

    def setUp(self):
        self.user = _user('t_crit_01_user')
        self.sess_a = _session(self.user, 'sk-t-crit-01-a')
        self.sess_b = _session(self.user, 'sk-t-crit-01-b')

        chat_memory.append_message(self.sess_a, 'user', 'SESSION-A-USER-MSG')
        chat_memory.append_message(self.sess_a, 'assistant', 'SESSION-A-ASSISTANT-MSG')
        chat_memory.append_message(self.sess_b, 'user', 'SESSION-B-USER-MSG')
        chat_memory.append_message(self.sess_b, 'assistant', 'SESSION-B-ASSISTANT-MSG')

    def test_session_a_does_not_contain_session_b_messages(self):
        """T-CRIT-01a: Session A 的历史中不含 Session B 的消息。"""
        history_a = chat_memory.load_history_by_session(self.sess_a)
        contents_a = [m['content'] for m in history_a]
        self.assertIn('SESSION-A-USER-MSG', contents_a)
        self.assertIn('SESSION-A-ASSISTANT-MSG', contents_a)
        self.assertNotIn('SESSION-B-USER-MSG', contents_a)
        self.assertNotIn('SESSION-B-ASSISTANT-MSG', contents_a)

    def test_session_b_does_not_contain_session_a_messages(self):
        """T-CRIT-01b: Session B 的历史中不含 Session A 的消息。"""
        history_b = chat_memory.load_history_by_session(self.sess_b)
        contents_b = [m['content'] for m in history_b]
        self.assertIn('SESSION-B-USER-MSG', contents_b)
        self.assertNotIn('SESSION-A-USER-MSG', contents_b)

    def test_isolation_with_multiple_users(self):
        """T-CRIT-01c: 不同用户的 session 消息也互相隔离。"""
        user_b = _user('t_crit_01_user_b')
        sess_b_user_b = _session(user_b, 'sk-t-crit-01-b-user-b')
        chat_memory.append_message(sess_b_user_b, 'user', 'USER-B-DIFFERENT-USER-MSG')

        history_a = chat_memory.load_history_by_session(self.sess_a)
        contents_a = [m['content'] for m in history_a]
        self.assertNotIn('USER-B-DIFFERENT-USER-MSG', contents_a)


# ---------------------------------------------------------------------------
# T-CRIT-02 / T-UNIT-04: 历史 20 轮上限
# AC: US-012 AC-012-01 (20 轮截断)
# ---------------------------------------------------------------------------
@tag('unit')
class LoadHistoryBySessionLimitTest(TestCase):
    """T-CRIT-02: 写入 25 轮，load_history_by_session(limit=20) 返回最近 20 轮（40条）。"""

    def setUp(self):
        self.user = _user('t_crit_02_user')
        self.sess = _session(self.user, 'sk-t-crit-02')
        _msgs(self.sess, 25)

    def test_limit_20_returns_at_most_40_messages(self):
        """T-CRIT-02a: 25 轮消息，limit=20 最多返回 40 条。"""
        result = chat_memory.load_history_by_session(self.sess, limit=20)
        self.assertLessEqual(len(result), 40)

    def test_limit_20_returns_most_recent_messages(self):
        """T-CRIT-02b: 返回的是最近的消息（第 24 轮末），不是前 40 条（第 0-19 轮）。"""
        result = chat_memory.load_history_by_session(self.sess, limit=20)
        contents = [m['content'] for m in result]
        # 最后一条应是最近的 assistant 消息
        self.assertEqual(result[-1]['content'], 'assistant-msg-24')
        # 最早的 user-msg-0 不应在结果中（被截断）
        self.assertNotIn('user-msg-0', contents)
        self.assertNotIn('assistant-msg-0', contents)

    def test_exactly_20_turns_returned(self):
        """T-CRIT-02c: limit=20 时，应恰好返回 40 条（20 轮 × 2）。"""
        result = chat_memory.load_history_by_session(self.sess, limit=20)
        self.assertEqual(len(result), 40)

    def test_limit_default_reads_from_settings(self):
        """T-UNIT-04: limit=None 时从 settings 读取 CHAT_HISTORY_INJECT_TURNS。"""
        with override_settings(CHAT_HISTORY_INJECT_TURNS=5):
            result = chat_memory.load_history_by_session(self.sess)
            self.assertLessEqual(len(result), 10)

    def test_limit_exact_match(self):
        """T-UNIT-04b: limit=25 时，25 轮 50 条全部返回。"""
        result = chat_memory.load_history_by_session(self.sess, limit=25)
        self.assertEqual(len(result), 50)


# ---------------------------------------------------------------------------
# T-CRIT-03 / T-UNIT-05~07: 软删除隔离
# AC: US-011 AC-011-01, AC-011-02, AC-011-03
# ---------------------------------------------------------------------------
@tag('unit')
class SoftDeleteSessionTest(TestCase):
    """T-CRIT-03: soft_delete_session 和 get_sessions 的软删除行为。"""

    def setUp(self):
        self.user = _user('t_crit_03_user')
        self.sess = _session(self.user, 'sk-t-crit-03')
        chat_memory.append_message(self.sess, 'user', 'some-message')

    def test_get_sessions_excludes_deleted(self):
        """T-CRIT-03a / T-UNIT-05: 软删除后 get_sessions 不再返回该 session。"""
        result_before = chat_memory.get_sessions(self.user)
        self.assertEqual(result_before['total'], 1)

        chat_memory.soft_delete_session(self.user, 'sk-t-crit-03')

        result_after = chat_memory.get_sessions(self.user)
        self.assertEqual(result_after['total'], 0)
        session_keys = [s['session_key_full'] for s in result_after['sessions']]
        self.assertNotIn('sk-t-crit-03', session_keys)

    def test_soft_delete_sets_is_deleted_flag(self):
        """T-UNIT-05b: 软删除后 is_deleted 字段为 True（DB 层验证）。"""
        chat_memory.soft_delete_session(self.user, 'sk-t-crit-03')
        self.sess.refresh_from_db()
        self.assertTrue(self.sess.is_deleted)

    def test_soft_delete_returns_true(self):
        """T-UNIT-05c: 成功软删除返回 True。"""
        result = chat_memory.soft_delete_session(self.user, 'sk-t-crit-03')
        self.assertTrue(result)

    def test_soft_delete_idempotent_raises_value_error(self):
        """T-CRIT-03b / T-UNIT-06: 对已软删除 session 再次调用抛 ValueError（幂等保护）。"""
        chat_memory.soft_delete_session(self.user, 'sk-t-crit-03')
        with self.assertRaises(ValueError) as ctx:
            chat_memory.soft_delete_session(self.user, 'sk-t-crit-03')
        self.assertIn('not found or not owned', str(ctx.exception))

    def test_soft_delete_wrong_user_raises_value_error(self):
        """T-CRIT-03c / T-UNIT-07: 归属校验——other_user 尝试删除他人 session 抛 ValueError。"""
        other_user = _user('t_crit_03_other_user')
        with self.assertRaises(ValueError):
            chat_memory.soft_delete_session(other_user, 'sk-t-crit-03')

    def test_soft_delete_nonexistent_key_raises_value_error(self):
        """T-UNIT-07b: 不存在的 session_key 抛 ValueError。"""
        with self.assertRaises(ValueError):
            chat_memory.soft_delete_session(self.user, 'key-that-does-not-exist')


# ---------------------------------------------------------------------------
# T-UNIT-08: get_sessions 分页 + session_key_full 字段
# AC: US-008 AC-008-01, AC-008-02, AC-008-03
# ---------------------------------------------------------------------------
@tag('unit')
class GetSessionsExtendedTest(TestCase):
    """T-UNIT-08: get_sessions 返回 session_key_full 字段，分页正确，is_deleted 过滤。"""

    def setUp(self):
        self.user = _user('t_unit_08_user')
        for i in range(5):
            _session(self.user, f'sk-t-unit-08-{i:04d}-xxxx-xxxx-xxxxxxxxxxxx')

    def test_session_key_full_field_present(self):
        """T-UNIT-08a: 返回的每条 session 包含 session_key_full 字段（完整 key）。"""
        result = chat_memory.get_sessions(self.user)
        for s in result['sessions']:
            self.assertIn('session_key_full', s)
            # session_key_full 应是完整 key，不截断
            full = s['session_key_full']
            self.assertFalse(full.endswith('...'), f"session_key_full 不应截断: {full}")

    def test_session_key_is_truncated_for_display(self):
        """T-UNIT-08b: session_key（展示用）以 '...' 结尾（已截断）。"""
        result = chat_memory.get_sessions(self.user)
        for s in result['sessions']:
            self.assertTrue(s['session_key'].endswith('...'))

    def test_is_deleted_filter_only_returns_active_sessions(self):
        """T-UNIT-08c: 软删除 2 条后，get_sessions 只返回剩余 3 条。"""
        chat_memory.soft_delete_session(self.user, 'sk-t-unit-08-0000-xxxx-xxxx-xxxxxxxxxxxx')
        chat_memory.soft_delete_session(self.user, 'sk-t-unit-08-0001-xxxx-xxxx-xxxxxxxxxxxx')
        result = chat_memory.get_sessions(self.user)
        self.assertEqual(result['total'], 3)
        self.assertEqual(len(result['sessions']), 3)

    def test_empty_user_returns_empty(self):
        """T-UNIT-08d (AC-008-03): 无会话用户返回 total=0，sessions=[]。"""
        empty_user = _user('t_unit_08_empty_user')
        result = chat_memory.get_sessions(empty_user)
        self.assertEqual(result['total'], 0)
        self.assertEqual(result['sessions'], [])

    def test_pagination_page2(self):
        """T-UNIT-08e (AC-008-02): 分页正常工作，page=2 返回余下条目。"""
        result = chat_memory.get_sessions(self.user, page=2, page_size=3)
        self.assertEqual(len(result['sessions']), 2)

    def test_returns_message_count(self):
        """T-UNIT-08f (AC-008-01): 每条 session 有 message_count 字段。"""
        result = chat_memory.get_sessions(self.user, page=1, page_size=1)
        self.assertIn('message_count', result['sessions'][0])


# ---------------------------------------------------------------------------
# T-UNIT-09: load_history_by_session — limit=0 返回空列表
# AC: US-012 AC-012-01 (边界情况)
# ---------------------------------------------------------------------------
@tag('unit')
class LoadHistoryLimitZeroTest(TestCase):
    def test_limit_zero_returns_empty(self):
        """T-UNIT-09: limit=0 时返回空列表（注入窗口为 0）。"""
        user = _user('t_unit_09_user')
        sess = _session(user, 'sk-t-unit-09')
        chat_memory.append_message(sess, 'user', 'some msg')
        chat_memory.append_message(sess, 'assistant', 'some reply')
        result = chat_memory.load_history_by_session(sess, limit=0)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# T-UNIT-10: 会话解析/创建逻辑（ADR-001 改写）
# AC: US-014 AC-014-01, AC-014-02, US-010 AC-010-01
#
# ADR-001 策略 A：ChatConsumer._resolve_session() 已删除，connect() 不再创建/解析
# 会话；解析、复用与降级职责移入 _ensure_session_created()（首条消息时触发）。
# 本类直接驱动 _ensure_session_created()，覆盖四种 session_key 结果：
#   全新 key → 创建；有效本人 key → 复用；已删除 key → 降级（不建会话）；
#   他人 key → 降级（不跨用户复用）。
# 需用 TransactionTestCase 以支持 sync_to_async（跨线程 DB 可见性）。
# ---------------------------------------------------------------------------
@tag('unit')
class ResolveSessionTest(TransactionTestCase):
    """T-UNIT-10（ADR-001）：_ensure_session_created 的四种 session_key 解析行为。"""

    def setUp(self):
        from api.consumers import ChatConsumer  # noqa: F401  确认 consumer 可导入
        self.user = _user('t_unit_10_user')

    _loop = None

    def _run(self, coro):
        # 复用进程级 loop 且不关闭，避免污染其它用例的 asyncio.get_event_loop()（Py3.12）
        cls = type(self)
        if cls._loop is None or cls._loop.is_closed():
            cls._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(cls._loop)
        return cls._loop.run_until_complete(coro)

    def _consumer(self, session_key):
        from api.consumers import ChatConsumer
        c = ChatConsumer()
        c.user = self.user
        c.session_key = session_key
        c.chat_session = None
        c._session_created = False
        return c

    def test_fresh_key_creates_session(self):
        """T-UNIT-10a（AC-014-01）：全新 session_key → 首条消息时创建新 session。"""
        c = self._consumer('sk-t-unit-10-fresh')
        self._run(c._ensure_session_created('首条消息'))
        self.assertIsNotNone(c.chat_session)
        self.assertEqual(c.chat_session.user_id, self.user.id)
        self.assertTrue(c._session_created)

    def test_valid_own_key_reused(self):
        """T-UNIT-10b（AC-010-01）：有效且归属本人的 session_key → 复用，不新建。"""
        existing = _session(self.user, 'sk-t-unit-10-existing')
        c = self._consumer('sk-t-unit-10-existing')
        self._run(c._ensure_session_created('首条消息'))
        self.assertIsNotNone(c.chat_session)
        self.assertEqual(c.chat_session.pk, existing.pk)
        self.assertEqual(
            ChatSession.objects.filter(
                user=self.user, session_key='sk-t-unit-10-existing'
            ).count(),
            1, '复用已有 session 不应新建记录',
        )

    def test_deleted_key_degrades_without_session(self):
        """T-UNIT-10c（ADR-001）：已软删除的 session_key → 降级（chat_session 仍为 None），
        不复活原会话、不新建同 key 的未删除会话。"""
        sess = _session(self.user, 'sk-t-unit-10-deleted')
        chat_memory.soft_delete_session(self.user, 'sk-t-unit-10-deleted')
        c = self._consumer('sk-t-unit-10-deleted')
        self._run(c._ensure_session_created('首条消息'))
        self.assertIsNone(c.chat_session, '已删除 key 应降级，不应建立会话')
        self.assertFalse(c._session_created)
        sess.refresh_from_db()
        self.assertTrue(sess.is_deleted, '原会话应仍为 is_deleted=True')
        self.assertFalse(
            ChatSession.objects.filter(
                session_key='sk-t-unit-10-deleted', is_deleted=False
            ).exists(),
            '不应新建未删除的同 key 会话',
        )

    def test_foreign_key_degrades_without_cross_user(self):
        """T-UNIT-10d（AC-014 安全）：他人的 session_key → 降级，不跨用户复用、不改他人会话。"""
        other_user = _user('t_unit_10_other_user')
        other_sess = _session(other_user, 'sk-t-unit-10-other-user-key')
        c = self._consumer('sk-t-unit-10-other-user-key')
        self._run(c._ensure_session_created('首条消息'))
        self.assertIsNone(c.chat_session, '他人 key 应降级，不应复用')
        self.assertFalse(c._session_created)
        other_sess.refresh_from_db()
        self.assertEqual(other_sess.user_id, other_user.id, '他人会话归属不应被改动')
        self.assertFalse(other_sess.is_deleted)


# ---------------------------------------------------------------------------
# T-UNIT-11: get_sessions — 按 started_at 降序排列（最新会话在前）
# AC: US-009 AC-009-03 (新建会话出现在列表顶部)
# ---------------------------------------------------------------------------
@tag('unit')
class GetSessionsOrderTest(TestCase):
    def test_sessions_ordered_by_started_at_desc(self):
        """T-UNIT-11 (AC-009-03): get_sessions 返回按 started_at 倒序排列的会话。"""
        import time
        user = _user('t_unit_11_user')
        s1 = _session(user, 'sk-t-unit-11-first')
        time.sleep(0.01)   # 确保时间差（SQLite 精度）
        s2 = _session(user, 'sk-t-unit-11-second')

        result = chat_memory.get_sessions(user)
        # 第一条应是最新创建的 s2
        self.assertEqual(result['sessions'][0]['session_key_full'], 'sk-t-unit-11-second')
        self.assertEqual(result['sessions'][1]['session_key_full'], 'sk-t-unit-11-first')


# ---------------------------------------------------------------------------
# T-UNIT-12: load_history_by_session — 验证 result 升序（最旧消息在前）
# AC: US-012 AC-012-01
# ---------------------------------------------------------------------------
@tag('unit')
class LoadHistoryBySessionOrderTest(TestCase):
    def test_messages_returned_in_ascending_order(self):
        """T-UNIT-12: 消息按 created_at 升序排列（最旧在前，最新在后）。"""
        user = _user('t_unit_12_user')
        sess = _session(user, 'sk-t-unit-12')
        for i in range(5):
            chat_memory.append_message(sess, 'user', f'msg-{i}')
            chat_memory.append_message(sess, 'assistant', f'reply-{i}')

        result = chat_memory.load_history_by_session(sess, limit=5)
        contents = [m['content'] for m in result]
        # 第一条是最早的
        self.assertEqual(contents[0], 'msg-0')
        # 最后一条是最新的
        self.assertEqual(contents[-1], 'reply-4')
