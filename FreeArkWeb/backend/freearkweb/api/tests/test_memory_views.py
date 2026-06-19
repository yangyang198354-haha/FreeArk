"""
test_memory_views.py — memory API endpoint 测试

测试目标（GROUP_D / PHASE_07）：
  GET  /api/memory/me/              — 查看自己会话列表
  DELETE /api/memory/me/            — 清空自己历史
  GET  /api/admin/memory/<id>/      — admin 查看指定用户会话
  DELETE /api/admin/memory/<id>/    — admin 清空指定用户历史

权限校验：
  - 未认证用户 → 403/401
  - 普通用户访问 admin 端点 → 403
  - admin 用户 → 200

需求引用: REQ-FUNC-017a/b/c, REQ-NFR-010
US: US-MEM-008, US-MEM-009, US-MEM-011
MINOR-004：page_size 上界校验（≤ 100）
"""
from django.test import TestCase, tag
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient
from api.models import ChatSession, ChatMessage
from api import chat_memory

User = get_user_model()


def _make_user(username, is_staff=False, is_superuser=False):
    user = User.objects.create_user(username=username, password='testpass123')
    if is_staff:
        user.is_staff = True
        user.is_superuser = is_superuser
        user.save()
    return user


def _auth_client(user):
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


def _create_session_with_messages(user, key, n=2):
    sess = ChatSession.objects.create(user=user, session_key=key)
    for i in range(n):
        ChatMessage.objects.create(session=sess, role='user', content=f'q{i}')
        ChatMessage.objects.create(session=sess, role='assistant', content=f'a{i}')
    return sess


@tag('integration')
class MyMemoryViewGetTest(TestCase):
    """GET /api/memory/me/ — 查看自己的会话列表。"""

    def setUp(self):
        self.user = _make_user('my_mem_get_user')
        self.client = _auth_client(self.user)

    def test_get_returns_200(self):
        resp = self.client.get('/api/memory/me/')
        self.assertEqual(resp.status_code, 200)

    def test_get_returns_session_list(self):
        _create_session_with_messages(self.user, 'sk-view-1', n=1)
        _create_session_with_messages(self.user, 'sk-view-2', n=1)
        resp = self.client.get('/api/memory/me/')
        data = resp.json()
        self.assertIn('total', data)
        self.assertIn('sessions', data)
        self.assertEqual(data['total'], 2)

    def test_get_unauthenticated_returns_403(self):
        anon_client = APIClient()
        resp = anon_client.get('/api/memory/me/')
        self.assertIn(resp.status_code, [401, 403])

    def test_get_only_returns_own_sessions(self):
        """不返回其他用户的会话。"""
        other_user = _make_user('other_mem_user')
        _create_session_with_messages(self.user, 'sk-mine')
        _create_session_with_messages(other_user, 'sk-others')
        resp = self.client.get('/api/memory/me/')
        data = resp.json()
        self.assertEqual(data['total'], 1)

    def test_get_pagination_page_size(self):
        """分页参数有效。"""
        for i in range(5):
            _create_session_with_messages(self.user, f'sk-pag-{i}', n=1)
        resp = self.client.get('/api/memory/me/?page=1&page_size=3')
        data = resp.json()
        self.assertEqual(len(data['sessions']), 3)

    def test_get_page_size_capped_at_100(self):
        """MINOR-004：page_size 超过 100 时被 cap 为 100，不报错。"""
        for i in range(5):
            _create_session_with_messages(self.user, f'sk-cap-{i}', n=1)
        resp = self.client.get('/api/memory/me/?page_size=999999')
        # 不应报错，状态码 200
        self.assertEqual(resp.status_code, 200)

    def test_get_empty_returns_empty_list(self):
        resp = self.client.get('/api/memory/me/')
        data = resp.json()
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['sessions'], [])


@tag('integration')
class MyMemoryViewDeleteTest(TestCase):
    """DELETE /api/memory/me/ — 清空自己的历史。"""

    def setUp(self):
        self.user = _make_user('my_mem_del_user')
        self.client = _auth_client(self.user)

    def test_delete_clears_own_memory(self):
        _create_session_with_messages(self.user, 'sk-del-1')
        _create_session_with_messages(self.user, 'sk-del-2')
        resp = self.client.delete('/api/memory/me/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('deleted_sessions', data)
        self.assertGreater(data['deleted_sessions'], 0)
        self.assertEqual(ChatSession.objects.filter(user=self.user).count(), 0)

    def test_delete_unauthenticated_returns_403(self):
        anon_client = APIClient()
        resp = anon_client.delete('/api/memory/me/')
        self.assertIn(resp.status_code, [401, 403])

    def test_delete_does_not_affect_other_users(self):
        """DELETE /memory/me/ 只清空自己的，不影响他人。"""
        other_user = _make_user('other_del_user')
        _create_session_with_messages(self.user, 'sk-self')
        _create_session_with_messages(other_user, 'sk-other-keep')
        self.client.delete('/api/memory/me/')
        self.assertEqual(ChatSession.objects.filter(user=other_user).count(), 1)

    def test_delete_empty_memory_ok(self):
        """没有 session 时 DELETE 也正常返回，deleted_sessions=0。"""
        resp = self.client.delete('/api/memory/me/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['deleted_sessions'], 0)

    def test_delete_returns_message_field(self):
        resp = self.client.delete('/api/memory/me/')
        self.assertIn('message', resp.json())


@tag('integration')
class AdminMemoryViewGetTest(TestCase):
    """GET /api/admin/memory/<user_id>/ — admin 查看指定用户会话。"""

    def setUp(self):
        self.admin = _make_user('admin_get_user', is_staff=True, is_superuser=True)
        self.target = _make_user('admin_target_user')
        self.normal_user = _make_user('normal_get_user')
        self.admin_client = _auth_client(self.admin)
        self.normal_client = _auth_client(self.normal_user)

    def test_admin_get_target_user_sessions(self):
        _create_session_with_messages(self.target, 'sk-admin-get-1')
        resp = self.admin_client.get(f'/api/admin/memory/{self.target.pk}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('total', data)
        self.assertIn('target_user', data)
        self.assertEqual(data['target_user'], self.target.username)

    def test_normal_user_access_admin_returns_403(self):
        """普通用户访问 admin 端点 → 403。"""
        resp = self.normal_client.get(f'/api/admin/memory/{self.target.pk}/')
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_access_admin_returns_403(self):
        anon_client = APIClient()
        resp = anon_client.get(f'/api/admin/memory/{self.target.pk}/')
        self.assertIn(resp.status_code, [401, 403])

    def test_admin_get_nonexistent_user_returns_404(self):
        resp = self.admin_client.get('/api/admin/memory/99999/')
        self.assertEqual(resp.status_code, 404)

    def test_admin_get_pagination(self):
        for i in range(3):
            _create_session_with_messages(self.target, f'sk-adm-pag-{i}', n=1)
        resp = self.admin_client.get(f'/api/admin/memory/{self.target.pk}/?page=1&page_size=2')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['sessions']), 2)

    def test_admin_get_page_size_capped(self):
        """page_size 超过 100 时被 cap，不报错。"""
        resp = self.admin_client.get(f'/api/admin/memory/{self.target.pk}/?page_size=99999')
        self.assertEqual(resp.status_code, 200)


@tag('integration')
class AdminMemoryViewDeleteTest(TestCase):
    """DELETE /api/admin/memory/<user_id>/ — admin 清空指定用户历史（含审计日志）。"""

    def setUp(self):
        self.admin = _make_user('admin_del_user', is_staff=True, is_superuser=True)
        self.target = _make_user('admin_del_target')
        self.normal_user = _make_user('normal_del_user')
        self.admin_client = _auth_client(self.admin)
        self.normal_client = _auth_client(self.normal_user)

    def test_admin_delete_target_user_sessions(self):
        _create_session_with_messages(self.target, 'sk-admin-del-1')
        _create_session_with_messages(self.target, 'sk-admin-del-2')
        resp = self.admin_client.delete(f'/api/admin/memory/{self.target.pk}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('deleted_sessions', data)
        self.assertGreater(data['deleted_sessions'], 0)
        self.assertEqual(ChatSession.objects.filter(user=self.target).count(), 0)

    def test_normal_user_admin_delete_returns_403(self):
        resp = self.normal_client.delete(f'/api/admin/memory/{self.target.pk}/')
        self.assertEqual(resp.status_code, 403)

    def test_admin_delete_nonexistent_user_returns_404(self):
        resp = self.admin_client.delete('/api/admin/memory/99999/')
        self.assertEqual(resp.status_code, 404)

    def test_admin_delete_returns_target_user_field(self):
        """响应包含 target_user 字段（便于审计确认）。"""
        resp = self.admin_client.delete(f'/api/admin/memory/{self.target.pk}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('target_user', data)
        self.assertEqual(data['target_user'], self.target.username)

    def test_admin_delete_does_not_affect_other_users(self):
        """admin DELETE target 不影响第三方用户的 session。"""
        third_user = _make_user('third_user_del')
        _create_session_with_messages(self.target, 'sk-target-todel')
        _create_session_with_messages(third_user, 'sk-third-keep')
        self.admin_client.delete(f'/api/admin/memory/{self.target.pk}/')
        self.assertEqual(ChatSession.objects.filter(user=third_user).count(), 1)
