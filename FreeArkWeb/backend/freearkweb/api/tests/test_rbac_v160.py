"""
v1.6.0 三角色 RBAC 测试套件。

覆盖：
  - IsOperatorOrAbove 权限类（admin/operator 放行，user/匿名拒绝）
  - UserRoleApiGuardMiddleware（user 角色除白名单外 /api 全 403；operator/admin/匿名放行）
  - 业主接口对 operator 开放（OQ-02）、对 user 拒绝
  - 服务管理接口仅 admin（operator/user 403）（OQ-01）
  - 能耗等原 AllowAny 业务接口升级为需鉴权（匿名被拒）
  - 管理员创建用户：role 必填 + 三值校验 + 非法值 400（OQ-04）
  - 数据迁移函数：role='user' → 'operator'，可回滚（OQ-05）
  - /api/auth/me/ 对各角色（白名单）放行

运行：
    cd FreeArkWeb/backend/freearkweb
    PYTHONUTF8=1 python manage.py test api.tests.test_rbac_v160 --verbosity=2
"""
import importlib
from unittest.mock import patch

from django.apps import apps as django_apps
from django.test import TestCase, tag
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import CustomUser, OwnerInfo
from api.views import IsOperatorOrAbove


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


class _FakeRequest:
    def __init__(self, user):
        self.user = user


# ---------------------------------------------------------------------------
# 权限类单元测试
# ---------------------------------------------------------------------------

@tag('unit')
class IsOperatorOrAboveTest(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(username="p_admin", password="x", role="admin")
        self.operator = CustomUser.objects.create_user(username="p_op", password="x", role="operator")
        self.owner = CustomUser.objects.create_user(username="p_user", password="x", role="user")

    def _check(self, user):
        return IsOperatorOrAbove().has_permission(_FakeRequest(user), None)

    def test_admin_allowed(self):
        self.assertTrue(self._check(self.admin))

    def test_operator_allowed(self):
        self.assertTrue(self._check(self.operator))

    def test_user_denied(self):
        self.assertFalse(self._check(self.owner))

    def test_anonymous_denied(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertFalse(self._check(AnonymousUser()))


# ---------------------------------------------------------------------------
# 中间件 + 端点权限集成测试
# ---------------------------------------------------------------------------

@tag('integration')
class RoleApiAccessTest(TestCase):
    def setUp(self):
        _, self.admin_t = _make("rbac_admin", "admin")
        _, self.op_t = _make("rbac_op", "operator")
        _, self.user_t = _make("rbac_user", "user")
        OwnerInfo.objects.create(
            specific_part="1-1-2-201", location_name="测试-201", building="1栋",
            unit="1单元", floor="2楼", room_number="201",
        )

    # ---- 业主接口（admin+operator 开放，user 拒绝，匿名 401） ----
    def test_owners_admin_200(self):
        self.assertEqual(_client(self.admin_t).get("/api/owners/").status_code, 200)

    def test_owners_operator_200(self):
        self.assertEqual(_client(self.op_t).get("/api/owners/").status_code, 200)

    def test_owners_user_403(self):
        # 中间件拦截 user 角色
        self.assertEqual(_client(self.user_t).get("/api/owners/").status_code, 403)

    def test_owners_anonymous_401(self):
        self.assertIn(_client().get("/api/owners/").status_code, (401, 403))

    def test_owners_operator_can_write(self):
        # OQ-02：operator 对业主信息有完整 CRUD
        payload = {
            "specific_part": "1-1-3-301", "location_name": "测试-301", "building": "1栋",
            "unit": "1单元", "floor": "3楼", "room_number": "301",
        }
        resp = _client(self.op_t).post("/api/owners/", payload, format="json")
        self.assertEqual(resp.status_code, 201)

    # ---- 服务管理（仅 admin） ----
    def test_services_user_403(self):
        self.assertEqual(_client(self.user_t).get("/api/services/list/").status_code, 403)

    def test_services_operator_403(self):
        self.assertEqual(_client(self.op_t).get("/api/services/list/").status_code, 403)

    @patch("subprocess.run")
    def test_services_admin_not_forbidden(self, mock_run):
        mock_run.return_value = type("R", (), {"stdout": "active\n", "returncode": 0})()
        resp = _client(self.admin_t).get("/api/services/list/")
        self.assertNotIn(resp.status_code, (401, 403))

    # ---- 能耗等原 AllowAny 接口已收紧为 IsOperatorOrAbove（匿名+业主均拒） ----
    def test_usage_anonymous_blocked(self):
        # v1.6.0（用户确认收紧）：匿名访问能耗接口被拒
        self.assertIn(_client().get("/api/usage/quantity/").status_code, (401, 403))

    def test_usage_user_403(self):
        # 普通业主被 UserRoleApiGuardMiddleware 拦截
        self.assertEqual(_client(self.user_t).get("/api/usage/quantity/").status_code, 403)

    def test_usage_operator_not_forbidden(self):
        # operator 可访问（具体 200/400 取决于查询参数，但不应是 403）
        self.assertNotEqual(_client(self.op_t).get("/api/usage/quantity/").status_code, 403)

    # ---- 白名单：user 可访问自身信息 ----
    def test_auth_me_user_200(self):
        resp = _client(self.user_t).get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["role"], "user")

    def test_auth_me_operator_role(self):
        resp = _client(self.op_t).get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["data"]["role"], "operator")

    # ---- v1.10.0：/api/memory/ 放行 user（业主端方舟智能体问答会话列表/历史，按 user 隔离） ----
    def test_memory_me_user_not_blocked(self):
        # 中间件不再拦截 user 访问 /api/memory/；会话列表按 user 隔离，应 200 而非 403
        resp = _client(self.user_t).get("/api/memory/me/")
        self.assertNotEqual(resp.status_code, 403)
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# 用户创建：角色校验
# ---------------------------------------------------------------------------

@tag('integration')
class UserCreateRoleValidationTest(TestCase):
    def setUp(self):
        _, self.admin_t = _make("uc_admin", "admin")
        self.c = _client(self.admin_t)

    def _payload(self, **over):
        p = {
            "username": "newbie", "email": "n@e.com", "password": "Abcd1234",
            "first_name": "三", "last_name": "张", "department": "", "position": "",
        }
        p.update(over)
        return p

    def test_role_required(self):
        # 不传 role → 400（OQ-04 强制选择）
        resp = self.c.post("/api/users/create/", self._payload(), format="json")
        self.assertEqual(resp.status_code, 400)

    def test_role_operator_created(self):
        resp = self.c.post("/api/users/create/", self._payload(username="op1", role="operator"), format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CustomUser.objects.get(username="op1").role, "operator")

    def test_role_user_created(self):
        resp = self.c.post("/api/users/create/", self._payload(username="ow1", role="user"), format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(CustomUser.objects.get(username="ow1").role, "user")

    def test_invalid_role_rejected(self):
        resp = self.c.post("/api/users/create/", self._payload(username="bad1", role="superuser"), format="json")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# 数据迁移函数
# ---------------------------------------------------------------------------

@tag('unit')
class MigrationDataTest(TestCase):
    def setUp(self):
        self.mod = importlib.import_module("api.migrations.0040_rbac_add_operator_role")

    def test_forward_user_to_operator(self):
        CustomUser.objects.create_user(username="m_user1", password="x", role="user")
        CustomUser.objects.create_user(username="m_admin1", password="x", role="admin")
        self.mod.migrate_user_to_operator(django_apps, None)
        self.assertEqual(CustomUser.objects.filter(role="user").count(), 0)
        self.assertEqual(CustomUser.objects.get(username="m_user1").role, "operator")
        # admin 不受影响
        self.assertEqual(CustomUser.objects.get(username="m_admin1").role, "admin")

    def test_reverse_operator_to_user(self):
        CustomUser.objects.create_user(username="m_op1", password="x", role="operator")
        self.mod.reverse_operator_to_user(django_apps, None)
        self.assertEqual(CustomUser.objects.get(username="m_op1").role, "user")
