"""
test_session_delete_view.py — SessionDeleteView 集成测试

测试目标（GROUP_D / PHASE_08 集成测试）：
  - T-INT-01: DELETE /api/memory/session/{key}/ 正常软删除 → HTTP 200
  - T-INT-02: 删除他人 session → HTTP 404（归属校验，防信息泄露）
  - T-INT-03: 删除不存在 session → HTTP 404
  - T-INT-04: 重复删除（幂等保护）→ HTTP 404
  - T-INT-05: 未认证请求 → HTTP 401/403
  - T-INT-06: GET /api/memory/me/ 软删除过滤 + session_key_full 字段
  - T-INT-07: GET /api/memory/me/ 空状态返回
  - T-INT-08: GET /api/memory/me/ 分页

需求溯源:
  US-008 AC-008-01~03, US-011 AC-011-01~03
"""

from django.test import TestCase, tag
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model
from api.models import ChatSession
from api import chat_memory

User = get_user_model()


def _make_user_with_token(username):
    user = User.objects.create_user(username=username, password='testpass123')
    token = Token.objects.create(user=user)
    return user, token.key


def _auth_client(token_key):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
    return client


def _session(user, key):
    return chat_memory.create_session(user, key)


# ---------------------------------------------------------------------------
# T-INT-01~04: SessionDeleteView DELETE 端点
# AC: US-011 AC-011-01, AC-011-02, AC-011-03
# ---------------------------------------------------------------------------
@tag('integration')
class SessionDeleteViewTest(TestCase):
    """集成测试：DELETE /api/memory/session/{session_key}/"""

    def setUp(self):
        self.user, self.token = _make_user_with_token('t_int_delete_user')
        self.client = _auth_client(self.token)
        self.sess = _session(self.user, 'sk-t-int-delete-session-key-xxxx')

    def test_delete_own_session_returns_200(self):
        """T-INT-01 (AC-011-01): 删除自己的 session 返回 HTTP 200，响应含 message 字段。"""
        url = f'/api/memory/session/{self.sess.session_key}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('message', data)
        self.assertEqual(data['message'], '会话已删除')
        self.assertEqual(data['session_key'], self.sess.session_key)

    def test_delete_marks_session_as_deleted_in_db(self):
        """T-INT-01b (AC-011-02): 删除后 DB 中 is_deleted=True。"""
        url = f'/api/memory/session/{self.sess.session_key}/'
        self.client.delete(url)
        self.sess.refresh_from_db()
        self.assertTrue(self.sess.is_deleted)

    def test_delete_removed_from_session_list(self):
        """T-INT-01c (AC-011-01): 删除后 GET /api/memory/me/ 不再返回该 session。"""
        url = f'/api/memory/session/{self.sess.session_key}/'
        self.client.delete(url)
        list_response = self.client.get('/api/memory/me/')
        self.assertEqual(list_response.status_code, 200)
        sessions = list_response.json()['sessions']
        session_keys = [s['session_key_full'] for s in sessions]
        self.assertNotIn(self.sess.session_key, session_keys)

    def test_delete_other_user_session_returns_404(self):
        """T-INT-02 (AC-011-03 归属校验): 删除他人 session 返回 HTTP 404（不泄露存在性）。"""
        other_user, _ = _make_user_with_token('t_int_delete_other_user')
        other_sess = _session(other_user, 'sk-t-int-delete-other-session-key-x')
        url = f'/api/memory/session/{other_sess.session_key}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)

    def test_delete_nonexistent_session_returns_404(self):
        """T-INT-03: 删除不存在的 session_key 返回 HTTP 404。"""
        url = '/api/memory/session/key-that-does-not-exist-at-all/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, 404)

    def test_delete_idempotent_second_call_returns_404(self):
        """T-INT-04 (幂等保护): 对已删除 session 再次 DELETE 返回 HTTP 404。"""
        url = f'/api/memory/session/{self.sess.session_key}/'
        first = self.client.delete(url)
        self.assertEqual(first.status_code, 200)
        second = self.client.delete(url)
        self.assertEqual(second.status_code, 404)

    def test_delete_unauthenticated_returns_401(self):
        """T-INT-05: 未认证请求返回 HTTP 401 或 403。"""
        anon_client = APIClient()
        url = f'/api/memory/session/{self.sess.session_key}/'
        response = anon_client.delete(url)
        self.assertIn(response.status_code, (401, 403))


# ---------------------------------------------------------------------------
# T-INT-06~08: MyMemoryView GET 端点（集成验证）
# AC: US-008 AC-008-01~03
# ---------------------------------------------------------------------------
@tag('integration')
class MyMemoryViewSessionKeyFullTest(TestCase):
    """集成测试：GET /api/memory/me/ 返回 session_key_full + is_deleted 过滤。"""

    def setUp(self):
        self.user, self.token = _make_user_with_token('t_int_memory_me_user')
        self.client = _auth_client(self.token)

    def test_returns_session_key_full_field(self):
        """T-INT-06a (AC-008-01): GET /api/memory/me/ 返回 session_key_full 字段。"""
        _session(self.user, 'sk-t-int-me-full-key-0001-xxxx-xx')
        response = self.client.get('/api/memory/me/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('sessions', data)
        self.assertGreater(len(data['sessions']), 0)
        sess = data['sessions'][0]
        self.assertIn('session_key_full', sess)
        self.assertEqual(sess['session_key_full'], 'sk-t-int-me-full-key-0001-xxxx-xx')

    def test_deleted_sessions_excluded_from_list(self):
        """T-INT-06b (AC-011-02 软删除过滤): 已删 session 不在 GET /api/memory/me/ 结果中。"""
        sess_active = _session(self.user, 'sk-t-int-me-active-key-xxxxxxxx')
        sess_deleted = _session(self.user, 'sk-t-int-me-deleted-key-xxxxxxx')
        chat_memory.soft_delete_session(self.user, 'sk-t-int-me-deleted-key-xxxxxxx')

        response = self.client.get('/api/memory/me/')
        data = response.json()
        session_keys_full = [s['session_key_full'] for s in data['sessions']]
        self.assertIn('sk-t-int-me-active-key-xxxxxxxx', session_keys_full)
        self.assertNotIn('sk-t-int-me-deleted-key-xxxxxxx', session_keys_full)

    def test_empty_session_list_returns_empty_state(self):
        """T-INT-07 (AC-008-03): 无会话时返回 total=0，sessions=[]（空状态）。"""
        response = self.client.get('/api/memory/me/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['total'], 0)
        self.assertEqual(data['sessions'], [])

    def test_pagination_works(self):
        """T-INT-08 (AC-008-02): 分页参数 page_size 生效。"""
        for i in range(5):
            _session(self.user, f'sk-t-int-me-page-{i:04d}-xx-xxxxxxxxx')
        response = self.client.get('/api/memory/me/?page=1&page_size=3')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data['sessions']), 3)
        self.assertEqual(data['total'], 5)
        self.assertEqual(data['page'], 1)

    def test_unauthenticated_returns_401(self):
        """T-INT-05b: 未认证 GET /api/memory/me/ 返回 401/403。"""
        anon_client = APIClient()
        response = anon_client.get('/api/memory/me/')
        self.assertIn(response.status_code, (401, 403))

    def test_session_contains_required_fields(self):
        """T-INT-06c (AC-008-01): 每条 session 包含所有必要字段。"""
        _session(self.user, 'sk-t-int-me-fields-key-0001-xxx')
        response = self.client.get('/api/memory/me/')
        data = response.json()
        sess = data['sessions'][0]
        for field in ('id', 'session_key', 'session_key_full', 'started_at', 'message_count'):
            self.assertIn(field, sess, f"缺少字段: {field}")
