"""
滑动窗口 Token 认证类（v0.9.0, REQ-AUTH-001, REQ-NFR-AUTH-001）

ADR-v090-001: 继承 DRF TokenAuthentication，在 authenticate_credentials 末尾
追加滑动窗口超时检查，最小侵入现有认证链路。

ADR-v090-003: 进程内节流字典 _activity_cache 避免每请求写 DB。
单 worker (--workers 1) 场景下 Python GIL 保证 dict 读写原子性。
"""

from django.conf import settings
from django.utils.timezone import now as django_now
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

# ---------------------------------------------------------------------------
# 进程内节流缓存（模块级，跨请求共享）
# 键: token key (str)
# 值: 上次写入 DB 的时间 (datetime)
# Worker 重启后清空 → 降级从 DB 重读（满足 AC-NFR-001-3：保守判定）
# ---------------------------------------------------------------------------
_activity_cache: dict = {}


def _get_timeout() -> int:
    """从 settings 读取超时阈值（秒），默认 1800。"""
    return getattr(settings, 'SESSION_INACTIVITY_TIMEOUT', 1800)


def _get_extended_timeout() -> int:
    """从 settings 读取"7天保持登录"延长超时阈值（秒），默认 604800（7天）。"""
    return getattr(settings, 'SESSION_EXTENDED_TIMEOUT', 604800)


def _get_throttle() -> int:
    """从 settings 读取节流阈值（秒），默认 300。"""
    return getattr(settings, 'ACTIVITY_THROTTLE_SECONDS', 300)


class SlidingWindowTokenAuthentication(TokenAuthentication):
    """
    DRF TokenAuthentication 的滑动窗口超时扩展。

    认证流程：
      1. 调用 super().authenticate_credentials(key) 验证 token 存在性
      2. 获取或创建 TokenActivity 记录（旧 token 首次访问时自动创建并放行）
      3. 检查 now - last_active_at >= 超时阈值 → AuthenticationFailed
         阈值按 TokenActivity.extended_session 选择：
           False → SESSION_INACTIVITY_TIMEOUT（默认 30 分钟）
           True  → SESSION_EXTENDED_TIMEOUT（"7天保持登录"，默认 7 天）
      4. 节流更新：距上次 DB 写入 >= ACTIVITY_THROTTLE_SECONDS 才触发 UPDATE
         否则仅在进程内缓存中记录（不写 DB）

    配置项（settings.py）：
      SESSION_INACTIVITY_TIMEOUT  - 默认超时阈值（秒，默认 1800 = 30 分钟）
      SESSION_EXTENDED_TIMEOUT    - 延长会话超时阈值（秒，默认 604800 = 7 天）
      ACTIVITY_THROTTLE_SECONDS   - 节流阈值（秒，默认 300 = 5 分钟）
    """

    def authenticate_credentials(self, key: str):
        # Step 1: 验证 token 存在（父类负责，不存在时抛 AuthenticationFailed）
        user, token = super().authenticate_credentials(key)

        # Step 1.5: 服务账号豁免不活跃超时。
        # 机器令牌（如 energy-agent，供 freeark-expert 写设备参数）长期低频调用——
        # 读工具走进程内直调不带 token、只有写才带 token，写又罕见，导致 last_active_at
        # 轻易超过阈值被「人类会话超时」误杀（→ 401「会话已超时」）。服务账号不应被
        # 不活跃超时判过期，故在此直接放行（不读写 TokenActivity）。
        service_accounts = getattr(settings, 'SERVICE_ACCOUNT_USERNAMES', [])
        if user.username in service_accounts:
            return (user, token)

        # 延迟导入，避免在模块加载时触发 ORM（App Registry 尚未就绪的场景）
        from .models import TokenActivity

        now = django_now()
        throttle_seconds = _get_throttle()

        # Step 2: 获取或创建 TokenActivity 记录
        activity, created = TokenActivity.objects.get_or_create(
            token=token,
            defaults={'last_active_at': now}
        )
        if created:
            # 旧 token 迁移场景：首次访问，写入缓存并放行
            _activity_cache[key] = now
            return (user, token)

        # Step 3: 超时检查（基于 DB 值，保证 worker 重启后正确判定）
        # "7天保持登录"会话使用延长阈值，否则使用默认不活动超时
        timeout_seconds = (
            _get_extended_timeout() if activity.extended_session else _get_timeout()
        )
        elapsed = (now - activity.last_active_at).total_seconds()
        if elapsed >= timeout_seconds:
            raise AuthenticationFailed("会话已超时，请重新登录")

        # Step 4: 节流更新
        last_db_write = _activity_cache.get(key)
        if last_db_write is None or (now - last_db_write).total_seconds() >= throttle_seconds:
            # 触发 DB 写入（单条 UPDATE，极轻量）
            TokenActivity.objects.filter(token=token).update(last_active_at=now)
            _activity_cache[key] = now
        # 否则：距上次 DB 写入未满节流阈值，跳过 DB 写入（满足 REQ-NFR-AUTH-001）

        return (user, token)
