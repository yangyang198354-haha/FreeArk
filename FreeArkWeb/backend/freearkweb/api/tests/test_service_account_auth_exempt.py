"""
服务账号豁免滑动窗口不活跃超时（SlidingWindowTokenAuthentication）。

背景：energy-agent（机器服务账号，供 freeark-expert 写设备参数）长期低频调用，
被「人类会话」不活跃超时误杀 → 写操作 401「会话已超时」。修复：settings
SERVICE_ACCOUNT_USERNAMES 白名单内的账号豁免超时检查、永不过期。

覆盖：
  TC-SA-001 普通用户 token 活跃超期 → AuthenticationFailed（控制组，证明超时仍生效）
  TC-SA-002 服务账号 token 同样超期 → 放行（豁免，不抛）
  TC-SA-003 服务账号即使从无 TokenActivity 行也放行（不依赖该表）
  TC-SA-004 非白名单普通用户即使活跃也照常走超时逻辑（回归保护）
"""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import AuthenticationFailed

from api.authentication import SlidingWindowTokenAuthentication, _activity_cache
from api.models import TokenActivity

User = get_user_model()


@override_settings(
    SERVICE_ACCOUNT_USERNAMES=['energy-agent'],
    SESSION_INACTIVITY_TIMEOUT=1800,
    SESSION_EXTENDED_TIMEOUT=604800,
)
class ServiceAccountAuthExemptTest(TestCase):

    def setUp(self):
        _activity_cache.clear()
        self.auth = SlidingWindowTokenAuthentication()

        self.human = User.objects.create_user(username='alice', password='x')
        self.human_token = Token.objects.create(user=self.human)

        self.agent = User.objects.create_user(username='energy-agent', password='x')
        self.agent_token = Token.objects.create(user=self.agent)

    def tearDown(self):
        _activity_cache.clear()

    def _set_stale(self, token, seconds_ago):
        TokenActivity.objects.update_or_create(
            token=token,
            defaults={
                'last_active_at': timezone.now() - timedelta(seconds=seconds_ago),
                'extended_session': False,
            },
        )

    # ── TC-SA-001：普通用户超期 → 抛 AuthenticationFailed（证明机制本身有效）──
    def test_TC_SA_001_human_stale_token_raises(self):
        self._set_stale(self.human_token, 3600)  # 1h > 30min 阈值
        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate_credentials(self.human_token.key)

    # ── TC-SA-002：服务账号同样超期 → 放行（豁免）──────────────────────────
    def test_TC_SA_002_service_account_stale_token_passes(self):
        self._set_stale(self.agent_token, 30 * 24 * 3600)  # 30 天，远超 7 天
        user, token = self.auth.authenticate_credentials(self.agent_token.key)
        self.assertEqual(user.username, 'energy-agent')
        self.assertEqual(token, self.agent_token)

    # ── TC-SA-003：服务账号无 TokenActivity 行也放行（不依赖该表）──────────
    def test_TC_SA_003_service_account_without_activity_row_passes(self):
        self.assertFalse(TokenActivity.objects.filter(token=self.agent_token).exists())
        user, token = self.auth.authenticate_credentials(self.agent_token.key)
        self.assertEqual(user.username, 'energy-agent')
        # 豁免路径不应为服务账号创建 TokenActivity 行（直接放行）
        self.assertFalse(TokenActivity.objects.filter(token=self.agent_token).exists())

    # ── TC-SA-004：非白名单普通用户在阈值内 → 正常放行（回归保护）──────────
    def test_TC_SA_004_human_within_window_passes(self):
        self._set_stale(self.human_token, 60)  # 1min < 30min
        user, token = self.auth.authenticate_credentials(self.human_token.key)
        self.assertEqual(user.username, 'alice')
