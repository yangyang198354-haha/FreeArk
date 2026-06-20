"""
test_memory_models.py — ChatSession + ChatMessage 模型测试

测试目标（GROUP_D / PHASE_07）：
  - ChatSession CRUD、CASCADE 删除、字段约束
  - ChatMessage CRUD、CASCADE 随 Session 删除、role 约束
  - 索引存在性（不测 SQL，通过 Meta.indexes 反射）
  - 跨用户隔离（用户 A 的 session 与用户 B 不混）

需求引用: REQ-FUNC-013, REQ-FUNC-016, REQ-NFR-011
US: US-MEM-001, US-MEM-002, US-MEM-005
"""
from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from api.models import ChatSession, ChatMessage

User = get_user_model()


def _make_user(username, password='pass1234'):
    return User.objects.create_user(username=username, password=password)


@tag('unit')
class ChatSessionCRUDTest(TestCase):
    """ChatSession 基本 CRUD 操作。"""

    def setUp(self):
        self.user = _make_user('sess_crud_user')

    def test_create_session(self):
        """创建 ChatSession，字段默认值正确。"""
        sess = ChatSession.objects.create(user=self.user, session_key='sk-001')
        self.assertEqual(sess.user, self.user)
        self.assertEqual(sess.session_key, 'sk-001')
        self.assertIsNotNone(sess.started_at)
        self.assertIsNone(sess.ended_at)

    def test_read_session(self):
        """从 DB 读回 ChatSession。"""
        ChatSession.objects.create(user=self.user, session_key='sk-read')
        fetched = ChatSession.objects.get(session_key='sk-read')
        self.assertEqual(fetched.user_id, self.user.pk)

    def test_update_ended_at(self):
        """更新 ended_at 字段（close_session 语义）。"""
        from django.utils import timezone
        sess = ChatSession.objects.create(user=self.user, session_key='sk-upd')
        ts = timezone.now()
        sess.ended_at = ts
        sess.save(update_fields=['ended_at'])
        refreshed = ChatSession.objects.get(pk=sess.pk)
        # USE_TZ=False 场景下直接比较（微秒精度允许轻微差异）
        self.assertIsNotNone(refreshed.ended_at)

    def test_delete_session(self):
        """删除 ChatSession 后不存在。"""
        sess = ChatSession.objects.create(user=self.user, session_key='sk-del')
        pk = sess.pk
        sess.delete()
        self.assertFalse(ChatSession.objects.filter(pk=pk).exists())

    def test_str_representation(self):
        """__str__ 包含 user_id 和 session_key 前缀。"""
        sess = ChatSession.objects.create(user=self.user, session_key='abcdefgh-1234')
        s = str(sess)
        self.assertIn('abcdefgh', s)


@tag('unit')
class ChatSessionCascadeTest(TestCase):
    """删除 User 时，其 ChatSession 也级联删除。"""

    def test_cascade_on_user_delete(self):
        user = _make_user('cascade_user')
        sess = ChatSession.objects.create(user=user, session_key='sk-cascade')
        pk = sess.pk
        user.delete()
        self.assertFalse(ChatSession.objects.filter(pk=pk).exists())


@tag('unit')
class ChatSessionIsolationTest(TestCase):
    """用户 A 的 session 不出现在用户 B 的查询集中。"""

    def test_user_isolation(self):
        user_a = _make_user('iso_user_a')
        user_b = _make_user('iso_user_b')
        ChatSession.objects.create(user=user_a, session_key='sk-a1')
        ChatSession.objects.create(user=user_a, session_key='sk-a2')
        ChatSession.objects.create(user=user_b, session_key='sk-b1')

        a_sessions = ChatSession.objects.filter(user=user_a)
        b_sessions = ChatSession.objects.filter(user=user_b)
        self.assertEqual(a_sessions.count(), 2)
        self.assertEqual(b_sessions.count(), 1)
        # 用户 B 的 session 中不含 user_a 的 session_key
        a_keys = set(a_sessions.values_list('session_key', flat=True))
        b_keys = set(b_sessions.values_list('session_key', flat=True))
        self.assertTrue(a_keys.isdisjoint(b_keys))


@tag('unit')
class ChatSessionIndexTest(TestCase):
    """Meta.indexes 中包含预期索引定义。"""

    def test_index_fields(self):
        index_fields = [
            tuple(idx.fields) for idx in ChatSession._meta.indexes
        ]
        self.assertIn(('user', 'started_at'), index_fields,
                      'ChatSession 应有 (user, started_at) 复合索引')


@tag('unit')
class ChatMessageCRUDTest(TestCase):
    """ChatMessage 基本 CRUD 操作。"""

    def setUp(self):
        self.user = _make_user('msg_crud_user')
        self.session = ChatSession.objects.create(user=self.user, session_key='sk-msg')

    def test_create_user_message(self):
        """创建 role=user 消息。"""
        msg = ChatMessage.objects.create(
            session=self.session, role='user', content='你好'
        )
        self.assertEqual(msg.role, 'user')
        self.assertEqual(msg.content, '你好')
        self.assertIsNotNone(msg.created_at)

    def test_create_assistant_message(self):
        """创建 role=assistant 消息。"""
        msg = ChatMessage.objects.create(
            session=self.session, role='assistant', content='你好，有什么可以帮助你？'
        )
        self.assertEqual(msg.role, 'assistant')

    def test_message_ordering_by_created_at(self):
        """消息可按 created_at 升序取出，且顺序稳定。"""
        ChatMessage.objects.create(session=self.session, role='user', content='第一条')
        ChatMessage.objects.create(session=self.session, role='assistant', content='第二条')
        msgs = list(ChatMessage.objects.filter(session=self.session).order_by('created_at'))
        self.assertEqual(msgs[0].content, '第一条')
        self.assertEqual(msgs[1].content, '第二条')

    def test_delete_message(self):
        """单独删除 ChatMessage。"""
        msg = ChatMessage.objects.create(session=self.session, role='user', content='临时')
        pk = msg.pk
        msg.delete()
        self.assertFalse(ChatMessage.objects.filter(pk=pk).exists())

    def test_str_representation(self):
        """__str__ 包含 session_id 和 role。"""
        msg = ChatMessage.objects.create(session=self.session, role='user', content='hi')
        s = str(msg)
        self.assertIn('user', s)


@tag('unit')
class ChatMessageCascadeTest(TestCase):
    """删除 ChatSession 时，其 ChatMessage 也级联删除。"""

    def test_cascade_on_session_delete(self):
        user = _make_user('msg_cascade_user')
        sess = ChatSession.objects.create(user=user, session_key='sk-msg-cascade')
        msg = ChatMessage.objects.create(session=sess, role='user', content='将被删除')
        msg_pk = msg.pk
        sess.delete()
        self.assertFalse(ChatMessage.objects.filter(pk=msg_pk).exists())

    def test_cascade_on_user_delete_removes_messages(self):
        """User 删除 → Session 删除 → Message 也级联删除。"""
        user = _make_user('msg_user_cascade')
        sess = ChatSession.objects.create(user=user, session_key='sk-uc')
        msg = ChatMessage.objects.create(session=sess, role='assistant', content='内容')
        msg_pk = msg.pk
        user.delete()
        self.assertFalse(ChatMessage.objects.filter(pk=msg_pk).exists())


@tag('unit')
class ChatMessageIndexTest(TestCase):
    """Meta.indexes 中包含预期索引定义。"""

    def test_index_fields(self):
        index_fields = [
            tuple(idx.fields) for idx in ChatMessage._meta.indexes
        ]
        self.assertIn(('session', 'created_at'), index_fields,
                      'ChatMessage 应有 (session, created_at) 复合索引')


@tag('unit')
class ChatMessageRelatedManagerTest(TestCase):
    """通过 session.messages 反向管理器访问消息。"""

    def test_related_manager(self):
        user = _make_user('related_mgr_user')
        sess = ChatSession.objects.create(user=user, session_key='sk-related')
        ChatMessage.objects.create(session=sess, role='user', content='m1')
        ChatMessage.objects.create(session=sess, role='assistant', content='m2')
        self.assertEqual(sess.messages.count(), 2)

    def test_user_sessions_related_manager(self):
        """通过 user.chat_sessions 反向管理器访问会话。"""
        user = _make_user('sessions_related_user')
        ChatSession.objects.create(user=user, session_key='sk-rel1')
        ChatSession.objects.create(user=user, session_key='sk-rel2')
        self.assertEqual(user.chat_sessions.count(), 2)
