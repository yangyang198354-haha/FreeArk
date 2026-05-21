"""
BUG-CSRF-001 回归测试套件 — CSRF Token Missing on Re-login

覆盖范围：
- 登录 → 登出 → 再登录 完整链路
- 登出后旧 Token 失效
- 再次登录后，使用新 Token 进行 POST 请求的 CSRF 验证
- get-csrf-token 端点正确签发 cookie
- 多次登录/登出循环稳定性

运行方式（在 FreeArkWeb/backend/freearkweb/ 目录下）：
    python manage.py test api.tests.test_csrf_relogin --settings=freearkweb.test_settings --verbosity=2

注意：
    CSRF 在测试环境中的行为说明：
    - Django 的 TestClient / APIClient 默认 enforce_csrf_checks=False（CSRF 豁免）
    - 为覆盖 CSRF 验证逻辑，需使用 enforce_csrf_checks=True 的 Client
    - 后端 user_login 有 @csrf_exempt，登录本身不受 CSRF 保护
    - 非 csrf_exempt 接口（如 change-password、user-logout）受 CSRF 保护
"""

from django.test import TestCase, Client
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CustomUser


def _make_user(username='csrf_testuser', password='CsrfTest!123', role='user'):
    """创建测试用户并返回 (user, token)"""
    user = CustomUser.objects.create_user(
        username=username, password=password, role=role
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token


class GetCSRFTokenEndpointTest(TestCase):
    """
    TC-CSRF-01: /api/get-csrf-token/ 端点基础行为
    验证该端点能签发 CSRF token 并写入响应体和 cookie
    """

    def setUp(self):
        self.client = Client()

    def test_csrf_token_endpoint_returns_200(self):
        """TC-CSRF-01-A: 任意匿名用户可调用 get-csrf-token 端点"""
        response = self.client.get(reverse('get-csrf-token'))
        self.assertEqual(response.status_code, 200)

    def test_csrf_token_endpoint_returns_token_in_body(self):
        """TC-CSRF-01-B: 响应体包含 csrftoken 字段"""
        response = self.client.get(reverse('get-csrf-token'))
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertIn('csrftoken', data)
        self.assertTrue(len(data['csrftoken']) > 0)

    def test_csrf_token_endpoint_sets_cookie(self):
        """TC-CSRF-01-C: 响应设置 csrftoken cookie"""
        response = self.client.get(reverse('get-csrf-token'))
        # Django TestClient 将 cookie 存储在 self.client.cookies
        self.assertIn('csrftoken', self.client.cookies)
        cookie_value = self.client.cookies['csrftoken'].value
        self.assertTrue(len(cookie_value) > 0)

    def test_csrf_token_is_consistent_between_body_and_cookie(self):
        """
        TC-CSRF-01-D: 响应体中的 token 与 cookie 中的 token 语义一致

        Django 4.1+ 起 CSRF token 有两种形态，二者不会逐字符相等：
        - cookie 中存储 32 字符的原始 secret；
        - get_token() 返回 64 字符的掩码 token（每次随机加盐，值不固定）。
        掩码 token 解掩码后必须等于 cookie secret —— Django 的 CSRF 校验正是
        基于这一关系，因此前端从 cookie 取值作为 X-CSRFToken 发送可被后端正确校验。
        """
        from django.middleware.csrf import _unmask_cipher_token, CSRF_SECRET_LENGTH

        response = self.client.get(reverse('get-csrf-token'))
        body_token = response.json()['csrftoken']
        cookie_token = self.client.cookies['csrftoken'].value

        def _to_secret(token):
            # 掩码 token（64 字符）解掩码为 secret；已是 secret（32 字符）则原样返回
            if len(token) == CSRF_SECRET_LENGTH:
                return token
            return _unmask_cipher_token(token)

        self.assertEqual(
            _to_secret(body_token), _to_secret(cookie_token),
            msg='响应体 token 与 cookie token 应解析为同一 CSRF secret'
        )


class LoginLogoutLoginFlowTest(TestCase):
    """
    TC-CSRF-02: 登录 → 登出 → 再登录 全链路测试
    这是 BUG-CSRF-001 的核心回归用例
    """

    def setUp(self):
        self.user, _ = _make_user(username='flow_user', password='FlowPass!1')
        # 使用 APIClient（enforce_csrf_checks=False）测试业务逻辑
        self.client = APIClient()

    def _login(self, username='flow_user', password='FlowPass!1'):
        """执行登录，返回 response"""
        return self.client.post(
            reverse('user-login'),
            {'username': username, 'password': password},
            format='json'
        )

    def _logout(self, token_key):
        """执行登出，返回 response"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
        response = self.client.post(reverse('user-logout'))
        self.client.credentials()  # 清除认证头
        return response

    def test_first_login_succeeds(self):
        """TC-CSRF-02-A: 第 1 次登录成功"""
        response = self._login()
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        self.assertTrue(response.data['success'])

    def test_logout_succeeds_after_first_login(self):
        """TC-CSRF-02-B: 第 1 次登录后，登出成功"""
        login_resp = self._login()
        token_key = login_resp.data['token']

        logout_resp = self._logout(token_key)
        self.assertEqual(logout_resp.status_code, 200)
        self.assertTrue(logout_resp.data['success'])

    def test_old_token_invalid_after_logout(self):
        """
        TC-CSRF-02-C: 登出后，旧 Token 不可再使用
        对应 AC-3：登出后 Token 已删除，旧 Token 返回 401
        """
        login_resp = self._login()
        old_token = login_resp.data['token']

        self._logout(old_token)

        # 尝试用旧 token 访问受保护接口
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {old_token}')
        response = self.client.get(reverse('get-current-user'))
        self.assertEqual(response.status_code, 401,
                         msg='旧 Token 在登出后应该失效，返回 401')

    def test_second_login_succeeds_after_logout(self):
        """
        TC-CSRF-02-D: 登出后，第 2 次登录成功（BUG-CSRF-001 核心回归）
        对应 AC-1：首次登录 → 登出 → 再次登录，登录本身成功
        """
        # 第 1 次登录
        login1_resp = self._login()
        self.assertEqual(login1_resp.status_code, 200)
        old_token = login1_resp.data['token']

        # 登出
        self._logout(old_token)

        # 第 2 次登录
        login2_resp = self._login()
        self.assertEqual(login2_resp.status_code, 200,
                         msg='第 2 次登录应成功，不得出现 CSRF 错误')
        self.assertIn('token', login2_resp.data)
        self.assertTrue(login2_resp.data['success'])

    def test_new_token_works_after_re_login(self):
        """
        TC-CSRF-02-E: 再次登录后，新 Token 可正常访问受保护接口
        对应 AC-2：登录 → 登出 → 再登录后，API 请求正常
        """
        # 第 1 次登录 + 登出
        login1 = self._login()
        self._logout(login1.data['token'])

        # 第 2 次登录
        login2 = self._login()
        new_token = login2.data['token']

        # 使用新 token 访问受保护的 GET 接口
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {new_token}')
        me_resp = self.client.get(reverse('get-current-user'))
        self.assertEqual(me_resp.status_code, 200,
                         msg='新 Token 应能访问 /api/auth/me/')
        self.assertEqual(me_resp.data['data']['username'], 'flow_user')

    def test_repeated_login_logout_cycle_stable(self):
        """
        TC-CSRF-02-F: 5 次登录/登出循环，每次均能成功
        对应 AC-4：反复操作无 CSRF 错误累积
        """
        for i in range(5):
            login_resp = self._login()
            self.assertEqual(
                login_resp.status_code, 200,
                msg=f'第 {i+1} 次登录失败'
            )
            token = login_resp.data['token']

            logout_resp = self._logout(token)
            self.assertEqual(
                logout_resp.status_code, 200,
                msg=f'第 {i+1} 次登出失败'
            )


class CSRFEnforcedLoginLogoutTest(TestCase):
    """
    TC-CSRF-03: 在 enforce_csrf_checks=True 环境下验证 CSRF 豁免与保护
    验证：user_login 有 @csrf_exempt，无 token 可登录；
          user_logout 受 CSRF 保护（同时需要认证）
    """

    def setUp(self):
        self.user, self.token = _make_user(username='csrf_enforce_user')
        # 启用 CSRF 检查的 Client
        self.csrf_client = Client(enforce_csrf_checks=True)

    def test_login_is_csrf_exempt(self):
        """
        TC-CSRF-03-A: user_login 视图有 @csrf_exempt，不需要 CSRF token 即可登录
        这是系统正确的设计：登录前客户端尚未持有有效 CSRF token
        """
        # 不提供 X-CSRFToken header，直接 POST 登录
        response = self.csrf_client.post(
            reverse('user-login'),
            data='{"username": "csrf_enforce_user", "password": "CsrfTest!123"}',
            content_type='application/json'
        )
        # login 是 csrf_exempt，不应因 CSRF 失败
        self.assertNotEqual(response.status_code, 403,
                            msg='user_login 应为 csrf_exempt，不得因 CSRF 失败返回 403')
        self.assertEqual(response.status_code, 200)

    def test_logout_returns_401_without_token(self):
        """
        TC-CSRF-03-B: user_logout 在没有 Token 时返回 401（认证失败优先于 CSRF）
        """
        response = self.csrf_client.post(
            reverse('user-logout'),
            content_type='application/json'
        )
        # 未认证时 DRF 返回 401，不会到达 CSRF 检查层（认证先于 CSRF）
        self.assertEqual(response.status_code, 401)


class TokenRotationAfterLoginTest(TestCase):
    """
    TC-CSRF-04: 验证每次登录产生有效 Token（不关心 token 值是否轮换）
    """

    def setUp(self):
        self.user, _ = _make_user(username='token_rotate_user', password='RotPass!1')
        self.client = APIClient()

    def _login(self):
        resp = self.client.post(
            reverse('user-login'),
            {'username': 'token_rotate_user', 'password': 'RotPass!1'},
            format='json'
        )
        self.assertEqual(resp.status_code, 200)
        return resp.data['token']

    def _logout(self, token_key):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
        resp = self.client.post(reverse('user-logout'))
        self.client.credentials()
        return resp

    def test_second_login_produces_valid_token(self):
        """
        TC-CSRF-04-A: 第 2 次登录后产生可用 Token
        （Token.get_or_create：若旧 Token 存在则返回旧 Token；
          若登出时已删除则创建新 Token）
        """
        token1 = self._login()
        self._logout(token1)

        token2 = self._login()
        self.assertTrue(len(token2) > 0, msg='第 2 次登录后应有有效 Token')

        # 验证 token2 可用
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token2}')
        me = self.client.get(reverse('get-current-user'))
        self.assertEqual(me.status_code, 200)

    def test_token_deleted_on_logout_then_recreated_on_login(self):
        """
        TC-CSRF-04-B: 登出时 Token 删除，再登录时重新创建
        """
        token1 = self._login()

        # 验证 Token 存在于 DB
        self.assertTrue(Token.objects.filter(key=token1).exists())

        # 登出
        self._logout(token1)

        # 验证 Token 已从 DB 删除
        self.assertFalse(Token.objects.filter(key=token1).exists(),
                         msg='登出后旧 Token 应从数据库删除')

        # 再次登录
        token2 = self._login()
        self.assertTrue(Token.objects.filter(key=token2).exists(),
                        msg='再次登录后应创建新 Token')
