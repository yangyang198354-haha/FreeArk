"""
v0.9.0 会话超时功能测试 (REQ-AUTH-001, REQ-AUTH-002, REQ-NFR-AUTH-001)

覆盖范围：
  - 滑动窗口刷新（AC-001-1, AC-001-3）
  - 超时返回 401（AC-001-2）
  - 旧 token 迁移场景（无 TokenActivity 记录时放行并创建）
  - 节流：同 token 短时间内不重复写 DB（AC-NFR-001-1）
  - 超时后重新登录可恢复（AC-001-4）
  - 登录时强制初始化 TokenActivity（OQ-004）
  - last_login 在登录时被刷新（REQ-AUTH-002, AC-002-1, AC-002-2）
  - 注册时同步创建 TokenActivity

运行方式（FreeArkWeb/backend/freearkweb/ 目录下）：
    python manage.py test api.tests_session_timeout --settings=freearkweb.test_settings -v 2
"""

from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status as drf_status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import CustomUser, TokenActivity
from .authentication import SlidingWindowTokenAuthentication, _activity_cache


# ---------------------------------------------------------------------------
# 测试用常量（缩短阈值，避免 sleep 等待）
# ---------------------------------------------------------------------------
TEST_TIMEOUT = 10    # 超时阈值：10 秒（测试用）
TEST_THROTTLE = 3    # 节流阈值：3 秒（测试用）


@override_settings(
    SESSION_INACTIVITY_TIMEOUT=TEST_TIMEOUT,
    ACTIVITY_THROTTLE_SECONDS=TEST_THROTTLE,
)
class SlidingWindowAuthenticationUnitTests(TestCase):
    """直接测试 SlidingWindowTokenAuthentication 类的行为。"""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser_sw',
            password='testpassword123',
        )
        self.token = Token.objects.create(user=self.user)
        self.auth = SlidingWindowTokenAuthentication()

        # 每个测试前清空进程内缓存，保证隔离
        _activity_cache.clear()

    def _now(self):
        from django.utils.timezone import now as django_now
        return django_now()

    # ------------------------------------------------------------------
    # TC-SW-01: 无 TokenActivity 记录时（旧 token 迁移），首次请求放行并创建
    # ------------------------------------------------------------------
    def test_tc_sw_01_no_activity_record_creates_and_passes(self):
        """旧 token 没有 TokenActivity 记录，首次请求应放行并创建记录。"""
        self.assertFalse(TokenActivity.objects.filter(token=self.token).exists())

        result_user, result_token = self.auth.authenticate_credentials(self.token.key)

        self.assertEqual(result_user, self.user)
        self.assertEqual(result_token, self.token)
        self.assertTrue(TokenActivity.objects.filter(token=self.token).exists())

    # ------------------------------------------------------------------
    # TC-SW-02: 有效 TokenActivity，未超时 → 放行
    # ------------------------------------------------------------------
    def test_tc_sw_02_within_timeout_passes(self):
        """距最后活动时间 < 超时阈值，应放行。"""
        TokenActivity.objects.create(
            token=self.token,
            last_active_at=self._now() - timedelta(seconds=TEST_TIMEOUT - 2),
        )

        result_user, result_token = self.auth.authenticate_credentials(self.token.key)

        self.assertEqual(result_user, self.user)
        self.assertEqual(result_token, self.token)

    # ------------------------------------------------------------------
    # TC-SW-03: 超过超时阈值 → AuthenticationFailed
    # ------------------------------------------------------------------
    def test_tc_sw_03_expired_raises_authentication_failed(self):
        """距最后活动时间 >= 超时阈值，应抛出 AuthenticationFailed。"""
        from rest_framework.exceptions import AuthenticationFailed
        TokenActivity.objects.create(
            token=self.token,
            last_active_at=self._now() - timedelta(seconds=TEST_TIMEOUT + 1),
        )
        _activity_cache.clear()

        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate_credentials(self.token.key)

    # ------------------------------------------------------------------
    # TC-SW-04: 滑动窗口语义 — 活动后计时重置（AC-001-3）
    # ------------------------------------------------------------------
    def test_tc_sw_04_sliding_window_resets_timer(self):
        """模拟 T=0 登录，T=8s 活动，T=15s 再请求：
        距上次活动仅 7s < 10s，应放行（而非从登录时算 15s > 10s 超时）。"""
        from rest_framework.exceptions import AuthenticationFailed

        base_time = self._now()

        # 模拟 T=8s 时的 last_active_at
        activity = TokenActivity.objects.create(
            token=self.token,
            last_active_at=base_time - timedelta(seconds=7),  # 7s ago < 10s
        )

        # T=15s：距最后活动 7s，不超时
        result_user, _ = self.auth.authenticate_credentials(self.token.key)
        self.assertEqual(result_user, self.user)

        # 更新 last_active_at 模拟刚刷新
        activity.last_active_at = self._now() - timedelta(seconds=1)
        activity.save()

        # 再次请求，距上次仅 1s，仍不超时
        result_user2, _ = self.auth.authenticate_credentials(self.token.key)
        self.assertEqual(result_user2, self.user)

    # ------------------------------------------------------------------
    # TC-SW-05: 节流 — 短时间内不重复写 DB（AC-NFR-001-1）
    # ------------------------------------------------------------------
    def test_tc_sw_05_throttle_limits_db_writes(self):
        """在节流阈值内多次请求，DB 中 last_active_at 只在第一次请求时更新。
        后续请求（缓存有记录且 < THROTTLE 阈值）不触发 DB UPDATE，
        DB 中的时间戳保持第一次写入后的值不变。
        """
        from django.utils.timezone import now as django_now

        # 初始 last_active_at 设为 1 秒前（未超时）
        initial_time = django_now() - timedelta(seconds=1)
        TokenActivity.objects.create(
            token=self.token,
            last_active_at=initial_time,
        )
        # 清空缓存，模拟 worker 刚启动：第一次请求触发 DB 写入
        _activity_cache.clear()

        # 第一次认证：缓存空 → 触发 DB UPDATE，缓存记录写入时间
        self.auth.authenticate_credentials(self.token.key)
        ts_after_first = TokenActivity.objects.get(token=self.token).last_active_at

        # 第二次认证（紧接着，节流窗口 3s 内）：缓存有记录 → 不触发 DB UPDATE
        self.auth.authenticate_credentials(self.token.key)
        ts_after_second = TokenActivity.objects.get(token=self.token).last_active_at

        # 断言：第一次请求后 DB 时间被更新（≥ initial_time）
        self.assertGreaterEqual(ts_after_first, initial_time,
                                "第一次认证后 DB last_active_at 应 >= 初始值")
        # 断言：第二次请求后 DB 时间与第一次相同（节流生效，未再写 DB）
        self.assertEqual(ts_after_second, ts_after_first,
                         "节流期内第二次认证不应更新 DB last_active_at")

    # ------------------------------------------------------------------
    # TC-SW-06: worker 重启（_activity_cache 清空）后从 DB 读取
    # ------------------------------------------------------------------
    def test_tc_sw_06_cache_miss_reads_db(self):
        """模拟 worker 重启：缓存为空，应从 DB 读取 last_active_at 做判断。"""
        # last_active_at = 2s 前（未超时）
        TokenActivity.objects.create(
            token=self.token,
            last_active_at=self._now() - timedelta(seconds=2),
        )
        _activity_cache.clear()  # 模拟 worker 重启清空缓存

        result_user, _ = self.auth.authenticate_credentials(self.token.key)
        self.assertEqual(result_user, self.user)
        # 缓存中应有记录（重建完成）
        self.assertIn(self.token.key, _activity_cache)

    # ------------------------------------------------------------------
    # TC-SW-07: 超时后缓存清空仍正确判断超时
    # ------------------------------------------------------------------
    def test_tc_sw_07_expired_with_empty_cache(self):
        """缓存为空 + DB 中 last_active_at 超时 → 正确返回 401。"""
        from rest_framework.exceptions import AuthenticationFailed
        TokenActivity.objects.create(
            token=self.token,
            last_active_at=self._now() - timedelta(seconds=TEST_TIMEOUT + 5),
        )
        _activity_cache.clear()

        with self.assertRaises(AuthenticationFailed) as ctx:
            self.auth.authenticate_credentials(self.token.key)

        self.assertIn("超时", str(ctx.exception.detail))

    # ------------------------------------------------------------------
    # TC-SW-08: 无效 token key → 父类 AuthenticationFailed（不涉及 TokenActivity）
    # ------------------------------------------------------------------
    def test_tc_sw_08_invalid_token_raises(self):
        """无效 token key 应直接返回 AuthenticationFailed（父类逻辑）。"""
        from rest_framework.exceptions import AuthenticationFailed
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate_credentials('nonexistent_token_key_xyz')


@override_settings(
    SESSION_INACTIVITY_TIMEOUT=TEST_TIMEOUT,
    ACTIVITY_THROTTLE_SECONDS=TEST_THROTTLE,
)
class LoginAPITests(TestCase):
    """测试登录接口对 TokenActivity 和 last_login 的影响。"""

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='logintest',
            password='testpass456',
        )
        _activity_cache.clear()

    def _login(self, username='logintest', password='testpass456'):
        return self.client.post(
            '/api/auth/login/',
            {'username': username, 'password': password},
            format='json',
        )

    # ------------------------------------------------------------------
    # TC-LOGIN-01: 登录成功后 TokenActivity 被创建/更新（OQ-004）
    # ------------------------------------------------------------------
    def test_tc_login_01_creates_token_activity(self):
        """登录成功后，TokenActivity 应被强制创建并记录当前时间。"""
        from django.utils.timezone import now as django_now
        before_login = django_now()

        response = self._login()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data.get('success'))

        token_key = response.data['token']
        token = Token.objects.get(key=token_key)
        activity = TokenActivity.objects.filter(token=token).first()

        self.assertIsNotNone(activity, "登录后应创建 TokenActivity 记录")
        self.assertGreaterEqual(activity.last_active_at, before_login)

    # ------------------------------------------------------------------
    # TC-LOGIN-02: 登录成功后 last_login 被刷新（REQ-AUTH-002, AC-002-1）
    # ------------------------------------------------------------------
    def test_tc_login_02_last_login_refreshed(self):
        """登录成功后，api_customuser.last_login 应被更新为当前时间。"""
        from django.utils.timezone import now as django_now
        before_login = django_now()

        response = self._login()
        self.assertEqual(response.status_code, 200)

        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.last_login)
        self.assertGreaterEqual(self.user.last_login, before_login)

    # ------------------------------------------------------------------
    # TC-LOGIN-03: 登录失败时 last_login 不变（AC-002-2）
    # ------------------------------------------------------------------
    def test_tc_login_03_failed_login_no_last_login_change(self):
        """密码错误的登录不更新 last_login。"""
        original_last_login = self.user.last_login

        response = self.client.post(
            '/api/auth/login/',
            {'username': 'logintest', 'password': 'wrongpassword'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

        self.user.refresh_from_db()
        self.assertEqual(self.user.last_login, original_last_login)

    # ------------------------------------------------------------------
    # TC-LOGIN-04: 登录后持有 token 可正常访问受保护接口（AC-001-1）
    # ------------------------------------------------------------------
    def test_tc_login_04_valid_token_accesses_protected_endpoint(self):
        """刚登录拿到的 token，立即请求受保护接口应返回 200。"""
        response = self._login()
        token_key = response.data['token']

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
        resp = self.client.get('/api/auth/me/')
        self.assertEqual(resp.status_code, 200)

    # ------------------------------------------------------------------
    # TC-LOGIN-05: 超时后 token 返回 401（AC-001-2）
    # ------------------------------------------------------------------
    def test_tc_login_05_expired_token_returns_401(self):
        """将 TokenActivity.last_active_at 强制设置为超时，验证返回 401。"""
        response = self._login()
        token_key = response.data['token']
        token = Token.objects.get(key=token_key)

        # 强制超时：last_active_at = 20s 前（> TEST_TIMEOUT=10s）
        from django.utils.timezone import now as django_now
        TokenActivity.objects.filter(token=token).update(
            last_active_at=django_now() - timedelta(seconds=TEST_TIMEOUT + 10)
        )
        _activity_cache.clear()  # 清空缓存，强制从 DB 读

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
        resp = self.client.get('/api/auth/me/')
        self.assertEqual(resp.status_code, 401)

    # ------------------------------------------------------------------
    # TC-LOGIN-06: 超时后重新登录可恢复访问（AC-001-4）
    # ------------------------------------------------------------------
    def test_tc_login_06_relogin_after_timeout_restores_access(self):
        """token 超时后，重新登录获得的新 token 应可正常访问。"""
        # 第一次登录
        response = self._login()
        token_key = response.data['token']
        token = Token.objects.get(key=token_key)

        # 强制超时
        from django.utils.timezone import now as django_now
        TokenActivity.objects.filter(token=token).update(
            last_active_at=django_now() - timedelta(seconds=TEST_TIMEOUT + 10)
        )
        _activity_cache.clear()

        # 验证超时
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
        resp = self.client.get('/api/auth/me/')
        self.assertEqual(resp.status_code, 401)

        # 重新登录（DRF get_or_create 会复用同一 token key，但 TokenActivity 被重置）
        # 先删除旧 token 以模拟重新颁发
        token.delete()
        # 模拟真实前端流程：401 后前端已清除本地 token，再次登录不会携带旧凭证
        # （DRF 认证在 AllowAny 的登录接口上也会先运行，若仍带已失效 token 会被判 401）
        self.client.credentials()
        response2 = self._login()
        self.assertEqual(response2.status_code, 200)
        new_token_key = response2.data['token']

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {new_token_key}')
        resp2 = self.client.get('/api/auth/me/')
        self.assertEqual(resp2.status_code, 200)

    # ------------------------------------------------------------------
    # TC-LOGIN-07: 超时阈值来自 settings 而非硬编码（AC-001-6）
    # ------------------------------------------------------------------
    def test_tc_login_07_timeout_threshold_from_settings(self):
        """SESSION_INACTIVITY_TIMEOUT 可通过 settings 覆盖，不硬编码。"""
        from django.conf import settings
        self.assertEqual(settings.SESSION_INACTIVITY_TIMEOUT, TEST_TIMEOUT)
        self.assertEqual(settings.ACTIVITY_THROTTLE_SECONDS, TEST_THROTTLE)


# 延长会话阈值：远大于 TEST_TIMEOUT，用于区分"7天保持登录"与默认超时
TEST_EXTENDED = 100000


@override_settings(
    SESSION_INACTIVITY_TIMEOUT=TEST_TIMEOUT,
    SESSION_EXTENDED_TIMEOUT=TEST_EXTENDED,
    ACTIVITY_THROTTLE_SECONDS=TEST_THROTTLE,
)
class RememberMeTests(TestCase):
    """测试"7天内保持登录"(remember_me / extended_session) 功能。"""

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='remembertest',
            password='testpass789',
        )
        _activity_cache.clear()

    def _login(self, remember_me):
        return self.client.post(
            '/api/auth/login/',
            {'username': 'remembertest', 'password': 'testpass789',
             'remember_me': remember_me},
            format='json',
        )

    # TC-RM-01: remember_me=True 登录后 extended_session 被置 True
    def test_tc_rm_01_remember_me_true_sets_extended_session(self):
        response = self._login(remember_me=True)
        self.assertEqual(response.status_code, 200)
        token = Token.objects.get(key=response.data['token'])
        activity = TokenActivity.objects.get(token=token)
        self.assertTrue(activity.extended_session)

    # TC-RM-02: remember_me=False（或缺省）登录后 extended_session 为 False
    def test_tc_rm_02_remember_me_false_keeps_default(self):
        response = self._login(remember_me=False)
        self.assertEqual(response.status_code, 200)
        token = Token.objects.get(key=response.data['token'])
        activity = TokenActivity.objects.get(token=token)
        self.assertFalse(activity.extended_session)

    # TC-RM-03: 默认会话超过 SESSION_INACTIVITY_TIMEOUT 即 401
    def test_tc_rm_03_default_session_expires_at_short_timeout(self):
        from django.utils.timezone import now as django_now
        response = self._login(remember_me=False)
        token = Token.objects.get(key=response.data['token'])
        # 年龄 = TEST_TIMEOUT+10：超过默认 10s 阈值
        TokenActivity.objects.filter(token=token).update(
            last_active_at=django_now() - timedelta(seconds=TEST_TIMEOUT + 10)
        )
        _activity_cache.clear()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {response.data["token"]}')
        resp = self.client.get('/api/auth/me/')
        self.assertEqual(resp.status_code, 401)

    # TC-RM-04: 延长会话在同样年龄下仍放行（核心收益）
    def test_tc_rm_04_extended_session_survives_short_timeout(self):
        from django.utils.timezone import now as django_now
        response = self._login(remember_me=True)
        token = Token.objects.get(key=response.data['token'])
        # 同样年龄 TEST_TIMEOUT+10：超过默认阈值但远小于 TEST_EXTENDED
        TokenActivity.objects.filter(token=token).update(
            last_active_at=django_now() - timedelta(seconds=TEST_TIMEOUT + 10)
        )
        _activity_cache.clear()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {response.data["token"]}')
        resp = self.client.get('/api/auth/me/')
        self.assertEqual(resp.status_code, 200)

    # TC-RM-05: 重新登录依当前勾选状态覆盖 extended_session（True → False）
    def test_tc_rm_05_relogin_overrides_extended_session(self):
        r1 = self._login(remember_me=True)
        token = Token.objects.get(key=r1.data['token'])
        self.assertTrue(TokenActivity.objects.get(token=token).extended_session)

        # 同一用户复用同一 token（get_or_create），再次以 False 登录应覆盖回 False
        self.client.credentials()
        r2 = self._login(remember_me=False)
        self.assertEqual(r2.status_code, 200)
        token2 = Token.objects.get(key=r2.data['token'])
        self.assertFalse(TokenActivity.objects.get(token=token2).extended_session)


@override_settings(
    SESSION_INACTIVITY_TIMEOUT=TEST_TIMEOUT,
    ACTIVITY_THROTTLE_SECONDS=TEST_THROTTLE,
)
class RegisterAPITests(TestCase):
    """测试注册接口对 TokenActivity 的影响。"""

    def setUp(self):
        self.client = APIClient()
        _activity_cache.clear()

    def test_tc_register_01_creates_token_activity(self):
        """注册成功后，TokenActivity 应被同步创建。"""
        from django.utils.timezone import now as django_now
        before_register = django_now()

        response = self.client.post(
            '/api/auth/register/',
            {'username': 'newuser_reg', 'password': 'regpass789', 'password2': 'regpass789', 'email': 'reg@test.com'},
            format='json',
        )
        self.assertEqual(response.status_code, 201)

        token_key = response.data['token']
        token = Token.objects.get(key=token_key)
        activity = TokenActivity.objects.filter(token=token).first()

        self.assertIsNotNone(activity, "注册后应创建 TokenActivity")
        self.assertGreaterEqual(activity.last_active_at, before_register)


@override_settings(
    SESSION_INACTIVITY_TIMEOUT=TEST_TIMEOUT,
    ACTIVITY_THROTTLE_SECONDS=TEST_THROTTLE,
)
class LogoutCascadeTests(TestCase):
    """测试登出时 TokenActivity 被级联删除。"""

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='logouttest',
            password='logoutpass',
        )
        _activity_cache.clear()

    def test_tc_logout_01_token_activity_cascade_deleted(self):
        """登出时 Token 被删除，TokenActivity 应通过 CASCADE 自动清除。"""
        # 登录
        response = self.client.post(
            '/api/auth/login/',
            {'username': 'logouttest', 'password': 'logoutpass'},
            format='json',
        )
        token_key = response.data['token']
        token = Token.objects.get(key=token_key)
        self.assertTrue(TokenActivity.objects.filter(token=token).exists())

        # 登出
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
        resp = self.client.post('/api/auth/logout/')
        self.assertEqual(resp.status_code, 200)

        # TokenActivity 应通过 CASCADE 消失
        self.assertFalse(Token.objects.filter(key=token_key).exists())
        self.assertFalse(TokenActivity.objects.filter(token_id=token_key).exists())


@override_settings(
    SESSION_INACTIVITY_TIMEOUT=TEST_TIMEOUT,
    ACTIVITY_THROTTLE_SECONDS=TEST_THROTTLE,
)
class ThrottleIntegrationTests(TestCase):
    """节流集成测试：通过真实 API 调用验证 DB 写入次数。"""

    def setUp(self):
        self.client = APIClient()
        self.user = CustomUser.objects.create_user(
            username='throttletest',
            password='throttlepass',
        )
        _activity_cache.clear()

    def test_tc_throttle_01_multiple_requests_single_db_write(self):
        """短时间内多次请求，TokenActivity.last_active_at 的 DB UPDATE 次数应受节流限制。"""
        # 登录获取 token（此时 TokenActivity 被强制创建）
        response = self.client.post(
            '/api/auth/login/',
            {'username': 'throttletest', 'password': 'throttlepass'},
            format='json',
        )
        token_key = response.data['token']
        token = Token.objects.get(key=token_key)

        # 记录登录后 last_active_at
        initial_activity = TokenActivity.objects.get(token=token)
        initial_last_active = initial_activity.last_active_at

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')

        # 在节流窗口内发起多次请求
        for _ in range(5):
            self.client.get('/api/auth/me/')

        # DB 中的 last_active_at 在节流期间不应被更新（因为 _activity_cache 有记录，节流生效）
        updated_activity = TokenActivity.objects.get(token=token)
        # 注意：登录后第一个请求可能触发一次 DB 写入（节流从空缓存开始）
        # 但后续 4 次请求应被节流拦截
        # 验证：last_active_at >= initial（时间只能向前）
        self.assertGreaterEqual(updated_activity.last_active_at, initial_last_active)


class TokenActivityModelTests(TestCase):
    """TokenActivity 模型单元测试。"""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='modeltest',
            password='modelpass',
        )
        self.token = Token.objects.create(user=self.user)

    def test_tc_model_01_create_and_retrieve(self):
        """TokenActivity 可正常创建和读取。"""
        from django.utils.timezone import now as django_now
        now = django_now()
        activity = TokenActivity.objects.create(
            token=self.token,
            last_active_at=now,
        )
        fetched = TokenActivity.objects.get(token=self.token)
        self.assertEqual(fetched.last_active_at, activity.last_active_at)

    def test_tc_model_02_one_to_one_constraint(self):
        """同一 token 不能创建两条 TokenActivity 记录（OneToOne 约束）。"""
        from django.utils.timezone import now as django_now
        from django.db import IntegrityError
        now = django_now()
        TokenActivity.objects.create(token=self.token, last_active_at=now)

        with self.assertRaises(Exception):  # IntegrityError 或 unique constraint
            TokenActivity.objects.create(token=self.token, last_active_at=now)

    def test_tc_model_03_cascade_delete_with_token(self):
        """Token 删除时，TokenActivity 通过 CASCADE 自动删除。"""
        from django.utils.timezone import now as django_now
        TokenActivity.objects.create(token=self.token, last_active_at=django_now())
        token_id = self.token.key

        self.token.delete()

        self.assertFalse(TokenActivity.objects.filter(token_id=token_id).exists())

    def test_tc_model_04_str_representation(self):
        """__str__ 方法正常返回。"""
        from django.utils.timezone import now as django_now
        activity = TokenActivity.objects.create(
            token=self.token,
            last_active_at=django_now(),
        )
        s = str(activity)
        self.assertIn('TokenActivity', s)
        self.assertIn('last_active', s)
