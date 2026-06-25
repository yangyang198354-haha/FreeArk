"""
v1.8.0_miniprogram_owner_account 测试套件——业主端账号体系 + 数据隔离。

覆盖：
  [unit]        UserScope 数据类（allows/is_unbound/is_multi_bound/is_owner 派生）
  [unit]        ScopeEnforcer.check_and_enforce（None 直通=零回归 / 豁免 / 屏蔽 / 注入 / 越权）
  [unit]        verify_write_scope（_gate 二次校验）
  [integration] build_user_scope（按 active 绑定查 specific_part 集）
  [integration] /api/miniapp/ 端点权限矩阵（IsOwnerUser / IsOperatorOrAbove / AllowAny）
  [integration] UserRoleApiGuardMiddleware 对 /api/miniapp/ 前缀放行（role=user 可访问）
  [integration] 注册强制 role=user（忽略客户端 role）/ 微信一键登录（mock code2session）
  [integration] 绑定/解绑/状态/业主管理列数据源

核心安全断言（NFR-ISO-001）：隔离由代码强制，user_scope=None（admin/operator）时
所有工具逐字直通，行为与 v1.7.0 完全一致——即"不改既有 web 行为"(C-01) 在代码层成立。

运行：
    cd FreeArkWeb/backend/freearkweb
    PYTHONUTF8=1 FREEARK_POC_MOCK=1 python manage.py test api.tests.test_miniapp_owner_v180 \
        --settings=freearkweb.test_settings --verbosity=2
"""
from unittest.mock import patch

from django.test import TestCase, tag
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import CustomUser, OwnerInfo, OwnerUserBinding, WechatBinding
from api.langgraph_chat.user_scope import UserScope, build_user_scope
from api.langgraph_chat.scope_enforcer import (
    check_and_enforce,
    verify_write_scope,
    ScopeViolationError,
)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _make(username, role):
    user = CustomUser.objects.create_user(username=username, password="pass1234", role=role)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _client(token_key=None):
    c = APIClient()
    if token_key:
        c.credentials(HTTP_AUTHORIZATION=f"Token {token_key}")
    return c


def _owner(specific_part, unique_id=None, **over):
    kwargs = dict(
        specific_part=specific_part,
        location_name=f"测试-{specific_part}",
        building="1栋", unit="1单元", floor="2楼",
        room_number=specific_part.split("-")[-1],
    )
    if unique_id is not None:
        kwargs["unique_id"] = unique_id
    kwargs.update(over)
    return OwnerInfo.objects.create(**kwargs)


# ===========================================================================
# UserScope 数据类（纯逻辑，无 DB）
# ===========================================================================

@tag('unit')
class UserScopeDataclassTest(TestCase):
    def test_owner_scope_is_owner_true(self):
        s = UserScope(role='user', bound_specific_parts=frozenset({'3-1-7-702'}))
        self.assertTrue(s.is_owner)

    def test_operator_scope_is_owner_false(self):
        s = UserScope(role='operator', bound_specific_parts=frozenset())
        self.assertFalse(s.is_owner)

    def test_allows_owner_only_bound(self):
        s = UserScope(role='user', bound_specific_parts=frozenset({'3-1-7-702'}))
        self.assertTrue(s.allows('3-1-7-702'))
        self.assertFalse(s.allows('9-9-9-999'))

    def test_allows_non_owner_always_true(self):
        s = UserScope(role='operator', bound_specific_parts=frozenset())
        self.assertTrue(s.allows('anything'))

    def test_is_unbound(self):
        self.assertTrue(UserScope('user', frozenset()).is_unbound())
        self.assertFalse(UserScope('user', frozenset({'a'})).is_unbound())

    def test_is_multi_bound(self):
        self.assertTrue(UserScope('user', frozenset({'a', 'b'})).is_multi_bound())
        self.assertFalse(UserScope('user', frozenset({'a'})).is_multi_bound())

    def test_frozen_immutable(self):
        s = UserScope('user', frozenset({'a'}))
        with self.assertRaises(Exception):
            s.role = 'admin'  # frozen dataclass 不可变


# ===========================================================================
# ScopeEnforcer.check_and_enforce —— 隔离核心逻辑
# ===========================================================================

@tag('unit')
class CheckAndEnforceTest(TestCase):
    OWNER = UserScope(role='user', bound_specific_parts=frozenset({'3-1-7-702'}))
    MULTI = UserScope(role='user', bound_specific_parts=frozenset({'3-1-7-702', '5-2-1-101'}))
    UNBOUND = UserScope(role='user', bound_specific_parts=frozenset())
    OPERATOR = UserScope(role='operator', bound_specific_parts=frozenset())

    # ---- 零回归：None / 非 owner 全直通（行为与 v1.7.0 逐字一致）----
    def test_none_scope_passthrough(self):
        args = {'specific_part': '9-9-9-999'}
        new_args, msg = check_and_enforce('set_device_params', args, None)
        self.assertEqual(new_args, args)
        self.assertIsNone(msg)

    def test_operator_scope_passthrough(self):
        args = {'specific_part': '9-9-9-999'}
        new_args, msg = check_and_enforce('get_dashboard_summary', args, self.OPERATOR)
        self.assertEqual(new_args, args)
        self.assertIsNone(msg)

    # ---- 豁免：三恒知识库对 user 也直通 ----
    def test_sanheng_exempt_for_owner(self):
        args = {'query': '结露'}
        new_args, msg = check_and_enforce('search_sanheng_knowledge', args, self.OWNER)
        self.assertEqual(new_args, args)
        self.assertIsNone(msg)

    def test_sanheng_exempt_even_unbound(self):
        new_args, msg = check_and_enforce('search_sanheng_knowledge', {}, self.UNBOUND)
        self.assertIsNone(msg)

    # ---- 未绑定用户：非豁免工具一律提示先绑定 ----
    def test_unbound_blocked(self):
        new_args, msg = check_and_enforce('get_realtime_params', {}, self.UNBOUND)
        self.assertIsNone(new_args)
        self.assertIn('绑定', msg)

    # ---- 全局看板：对 user 屏蔽 ----
    def test_dashboard_blocked_for_owner(self):
        new_args, msg = check_and_enforce('get_dashboard_summary', {}, self.OWNER)
        self.assertIsNone(new_args)
        self.assertIsNotNone(msg)

    # ---- 带 specific_part 工具：范围内直通 ----
    def test_scoped_read_in_range(self):
        args = {'specific_part': '3-1-7-702'}
        new_args, msg = check_and_enforce('get_usage_daily', args, self.OWNER)
        self.assertEqual(new_args['specific_part'], '3-1-7-702')
        self.assertIsNone(msg)

    # ---- 带 specific_part 工具：越权只读 → 拒绝（返回 message）----
    def test_scoped_read_out_of_range_denied(self):
        args = {'specific_part': '9-9-9-999'}
        new_args, msg = check_and_enforce('get_usage_daily', args, self.OWNER)
        self.assertIsNone(new_args)
        self.assertIn('9-9-9-999', msg)

    # ---- 写工具越权 → 抛 ScopeViolationError ----
    def test_scoped_write_out_of_range_raises(self):
        args = {'specific_part': '9-9-9-999'}
        with self.assertRaises(ScopeViolationError):
            check_and_enforce('set_device_params', args, self.OWNER)

    # ---- 单绑定未填 sp → 自动注入 ----
    def test_scoped_single_autofill(self):
        new_args, msg = check_and_enforce('get_realtime_params', {}, self.OWNER)
        self.assertEqual(new_args['specific_part'], '3-1-7-702')
        self.assertIsNone(msg)

    # ---- 多绑定未填 sp → 要求澄清（不调工具）----
    def test_scoped_multi_needs_clarify(self):
        new_args, msg = check_and_enforce('get_realtime_params', {}, self.MULTI)
        self.assertIsNone(new_args)
        self.assertIsNotNone(msg)

    # ---- 全局列表工具：注入 _owner_specific_parts ----
    def test_filtered_summary_injects_parts(self):
        new_args, msg = check_and_enforce('get_fault_summary', {'building': '1栋'}, self.OWNER)
        self.assertIsNone(msg)
        self.assertIn('_owner_specific_parts', new_args)
        self.assertEqual(set(new_args['_owner_specific_parts']), {'3-1-7-702'})

    def test_plc_status_injects_parts(self):
        new_args, msg = check_and_enforce('get_plc_status', {}, self.MULTI)
        self.assertEqual(set(new_args['_owner_specific_parts']), {'3-1-7-702', '5-2-1-101'})

    # ---- 未知工具：保守直通 ----
    def test_unknown_tool_passthrough(self):
        new_args, msg = check_and_enforce('some_future_tool', {'x': 1}, self.OWNER)
        self.assertEqual(new_args, {'x': 1})
        self.assertIsNone(msg)


@tag('unit')
class VerifyWriteScopeTest(TestCase):
    def test_none_noop(self):
        verify_write_scope('any', None)  # 不抛

    def test_operator_noop(self):
        verify_write_scope('any', UserScope('operator', frozenset()))  # 不抛

    def test_owner_in_range_ok(self):
        verify_write_scope('3-1-7-702', UserScope('user', frozenset({'3-1-7-702'})))

    def test_owner_out_of_range_raises(self):
        with self.assertRaises(ScopeViolationError):
            verify_write_scope('9-9-9-999', UserScope('user', frozenset({'3-1-7-702'})))


# ===========================================================================
# build_user_scope —— DB 查询
# ===========================================================================

@tag('integration')
class BuildUserScopeTest(TestCase):
    def setUp(self):
        self.owner_user = CustomUser.objects.create_user(username="bs_user", password="x", role="user")
        self.operator = CustomUser.objects.create_user(username="bs_op", password="x", role="operator")
        self.o1 = _owner("3-1-7-702", unique_id="MAC0001")
        self.o2 = _owner("5-2-1-101", unique_id="MAC0002")

    def test_operator_returns_none(self):
        self.assertIsNone(build_user_scope(self.operator))

    def test_user_no_binding_empty_scope(self):
        s = build_user_scope(self.owner_user)
        self.assertIsNotNone(s)
        self.assertTrue(s.is_owner)
        self.assertEqual(s.bound_specific_parts, frozenset())

    def test_user_active_bindings(self):
        OwnerUserBinding.objects.create(user=self.owner_user, owner=self.o1, active=True)
        OwnerUserBinding.objects.create(user=self.owner_user, owner=self.o2, active=True)
        s = build_user_scope(self.owner_user)
        self.assertEqual(s.bound_specific_parts, frozenset({'3-1-7-702', '5-2-1-101'}))

    def test_inactive_binding_excluded(self):
        OwnerUserBinding.objects.create(user=self.owner_user, owner=self.o1, active=True)
        OwnerUserBinding.objects.create(user=self.owner_user, owner=self.o2, active=False)
        s = build_user_scope(self.owner_user)
        self.assertEqual(s.bound_specific_parts, frozenset({'3-1-7-702'}))


# ===========================================================================
# 注册 / 微信登录
# ===========================================================================

@tag('integration')
class MiniappAuthTest(TestCase):
    def test_register_creates_user_role(self):
        resp = _client().post('/api/miniapp/auth/register/', {
            'username': 'mp_owner1', 'password': 'Testpass123', 'password2': 'Testpass123',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertIn('token', resp.json())
        self.assertEqual(CustomUser.objects.get(username='mp_owner1').role, 'user')

    def test_register_ignores_client_role(self):
        # 安全：客户端传 role=admin 必须被忽略，强制 user（防自助提权）
        resp = _client().post('/api/miniapp/auth/register/', {
            'username': 'mp_evil', 'password': 'Testpass123', 'password2': 'Testpass123',
            'role': 'admin',
        }, format='json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CustomUser.objects.get(username='mp_evil').role, 'user')

    def test_register_password_mismatch_400(self):
        resp = _client().post('/api/miniapp/auth/register/', {
            'username': 'mp_x', 'password': 'Testpass123', 'password2': 'different',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    @patch('api.views_miniapp._wx_code2session', return_value={'openid': 'openid_aaa', 'unionid': ''})
    def test_wechat_login_new_user(self, _mock):
        resp = _client().post('/api/miniapp/auth/wechat/', {'code': 'wxcode'}, format='json')
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body['is_new'])
        self.assertEqual(body['user']['role'], 'user')
        self.assertTrue(WechatBinding.objects.filter(openid='openid_aaa').exists())

    @patch('api.views_miniapp._wx_code2session', return_value={'openid': 'openid_bbb', 'unionid': ''})
    def test_wechat_login_existing_user(self, _mock):
        u = CustomUser.objects.create_user(username='wx_existing', password=None, role='user')
        WechatBinding.objects.create(user=u, openid='openid_bbb')
        resp = _client().post('/api/miniapp/auth/wechat/', {'code': 'wxcode'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()['is_new'])

    def test_wechat_login_missing_code_400(self):
        resp = _client().post('/api/miniapp/auth/wechat/', {}, format='json')
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# 绑定 / 解绑 / 状态 + 权限矩阵 + 中间件放行
# ===========================================================================

@tag('integration')
class MiniappBindTest(TestCase):
    def setUp(self):
        self.user, self.user_t = _make("bind_user", "user")
        _, self.op_t = _make("bind_op", "operator")
        _, self.admin_t = _make("bind_admin", "admin")
        self.o1 = _owner("3-1-7-702", unique_id="MACAAAA")

    # ---- 中间件放行：role=user 能进 /api/miniapp/（对照：进不了 /api/owners/）----
    def test_middleware_allows_user_on_miniapp(self):
        resp = _client(self.user_t).get('/api/miniapp/bind/status/')
        self.assertEqual(resp.status_code, 200)

    def test_middleware_still_blocks_user_on_web(self):
        # C-01 回归保护：user 仍被中间件挡在 web 业务接口外
        self.assertEqual(_client(self.user_t).get('/api/owners/').status_code, 403)

    # ---- 绑定 ----
    def test_bind_success(self):
        resp = _client(self.user_t).post('/api/miniapp/bind/', {'unique_id': 'MACAAAA'}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['specific_part'], '3-1-7-702')
        self.assertTrue(OwnerUserBinding.objects.filter(user=self.user, owner=self.o1, active=True).exists())

    def test_bind_unknown_mac_404(self):
        resp = _client(self.user_t).post('/api/miniapp/bind/', {'unique_id': 'NOPE'}, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_bind_duplicate_409(self):
        OwnerUserBinding.objects.create(user=self.user, owner=self.o1, active=True)
        resp = _client(self.user_t).post('/api/miniapp/bind/', {'unique_id': 'MACAAAA'}, format='json')
        self.assertEqual(resp.status_code, 409)

    def test_bind_rejects_operator(self):
        # IsOwnerUser：operator 不是 user → 403
        resp = _client(self.op_t).post('/api/miniapp/bind/', {'unique_id': 'MACAAAA'}, format='json')
        self.assertEqual(resp.status_code, 403)

    def test_bind_rejects_anonymous(self):
        resp = _client().post('/api/miniapp/bind/', {'unique_id': 'MACAAAA'}, format='json')
        self.assertIn(resp.status_code, (401, 403))

    # ---- 解绑 ----
    def test_unbind_success(self):
        OwnerUserBinding.objects.create(user=self.user, owner=self.o1, active=True)
        resp = _client(self.user_t).post('/api/miniapp/unbind/', {'specific_part': '3-1-7-702'}, format='json')
        self.assertEqual(resp.status_code, 200)
        b = OwnerUserBinding.objects.get(user=self.user, owner=self.o1)
        self.assertFalse(b.active)
        self.assertIsNotNone(b.unbound_at)

    def test_unbind_no_binding_404(self):
        resp = _client(self.user_t).post('/api/miniapp/unbind/', {'specific_part': '3-1-7-702'}, format='json')
        self.assertEqual(resp.status_code, 404)

    # ---- 状态 ----
    def test_bind_status_reflects_active(self):
        OwnerUserBinding.objects.create(user=self.user, owner=self.o1, active=True)
        resp = _client(self.user_t).get('/api/miniapp/bind/status/')
        body = resp.json()
        self.assertTrue(body['bound'])
        self.assertEqual(len(body['bindings']), 1)
        self.assertEqual(body['bindings'][0]['specific_part'], '3-1-7-702')


@tag('integration')
class OwnerBindingListTest(TestCase):
    def setUp(self):
        self.user, self.user_t = _make("obl_user", "user")
        _, self.op_t = _make("obl_op", "operator")
        self.o1 = _owner("3-1-7-702", unique_id="MACBBBB")
        OwnerUserBinding.objects.create(user=self.user, owner=self.o1, active=True)

    def test_operator_sees_bindings(self):
        resp = _client(self.op_t).get('/api/miniapp/admin/owner-bindings/')
        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['specific_part'], '3-1-7-702')
        self.assertEqual(results[0]['bound_users'][0]['username'], 'obl_user')

    def test_user_denied_on_admin_endpoint(self):
        # IsOperatorOrAbove：role=user 不可访问业主管理数据源（防越权读全量绑定）
        resp = _client(self.user_t).get('/api/miniapp/admin/owner-bindings/')
        self.assertEqual(resp.status_code, 403)

    def test_inactive_binding_not_listed(self):
        OwnerUserBinding.objects.filter(user=self.user, owner=self.o1).update(active=False)
        resp = _client(self.op_t).get('/api/miniapp/admin/owner-bindings/')
        self.assertEqual(resp.json()['results'], [])
