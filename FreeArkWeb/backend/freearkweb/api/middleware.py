"""
v1.6.0 三角色 RBAC —— user（普通业主/住户）角色 API 访问兜底拦截中间件。

背景：本项目 DRF 配置仅启用 Token 认证（settings.REST_FRAMEWORK 已移除
SessionAuthentication），故普通 Django 中间件中 request.user 对 API 客户端恒为
匿名用户，无法据此鉴权。业务接口分散在 10+ 个视图文件、40+ 个端点，逐一改
permission_classes 既冗长又易漏（漏一个即越权）。因此在中间件层集中实现"user
角色除登录/登出/自身信息等白名单外，禁止访问任何 /api/ 端点"这一粗粒度规则——
单点可审计、对未来新增端点自动生效。

判定逻辑：
  - 仅作用于 path 以 '/api/' 开头且不在白名单内的请求；其余一律放行。
  - 通过 Authorization: Token <key> 解析当前用户（与 DRF TokenAuthentication 同一
    Token 模型）；解析不到（匿名/非 Token）则放行——匿名访问由各端点自身的
    permission_classes 决定，本中间件只针对"已登录的 user 角色"。
  - 解析到的用户 role=='user' → 返回 403。admin/operator 放行。

确认依据：用户 2026-06-24 确认 OQ-06（user 登录后不能访问任何现有业务页面/功能，
后端强制 403）。
"""
from django.http import JsonResponse


class UserRoleApiGuardMiddleware:
    """拦截 role='user'（业主）对业务 API 的访问；放行 admin/operator/匿名。"""

    # user 角色允许访问的 API 路径白名单（登录态自助 + 鉴权基础设施）
    ALLOWLIST = frozenset({
        '/api/get-csrf-token/',
        '/api/auth/login/',
        '/api/auth/logout/',
        '/api/auth/me/',
        '/api/change-password/',
        '/api/health/',
    })

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_block(request):
            return JsonResponse(
                {'detail': '无权访问：该账号无业务功能访问权限'},
                status=403,
            )
        return self.get_response(request)

    def _should_block(self, request):
        path = request.path
        if not path.startswith('/api/'):
            return False
        if path in self.ALLOWLIST:
            return False
        user = self._resolve_token_user(request)
        return user is not None and getattr(user, 'role', None) == 'user'

    @staticmethod
    def _resolve_token_user(request):
        """从 Authorization: Token <key> 头解析用户；失败返回 None（视为匿名）。"""
        auth = request.META.get('HTTP_AUTHORIZATION', '')
        if not auth.startswith('Token '):
            return None
        key = auth[len('Token '):].strip()
        if not key:
            return None
        # 延迟导入，避免 App Registry 未就绪
        from rest_framework.authtoken.models import Token
        try:
            return Token.objects.select_related('user').get(key=key).user
        except Token.DoesNotExist:
            return None
