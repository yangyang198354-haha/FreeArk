"""
api.views_miniapp — 微信小程序业主端 API 视图（v1.8.0_miniprogram_owner_account）

所有视图均挂载于 /api/miniapp/ 命名空间（由 urls_miniapp.py 注册）。
UserRoleApiGuardMiddleware 对 /api/miniapp/ 前缀整体放行，
各端点通过 IsOwnerUser 或 IsOperatorOrAbove 进行精细权限控制。

端点清单：
  POST /api/miniapp/auth/register/        账号密码注册（REQ-AUTH-001）
  POST /api/miniapp/auth/wechat/          微信一键登录/注册（REQ-AUTH-002）
  POST /api/miniapp/bind/                 绑定专有部分（REQ-BIND-001/002）
  POST /api/miniapp/unbind/               自助解绑（REQ-BIND-003 解绑）
  GET  /api/miniapp/bind/status/          查询绑定状态（REQ-BIND-004）
  GET  /api/miniapp/admin/owner-bindings/ 业主管理页账号绑定列（REQ-OWNER-001）

安全约束：
  - 注册/微信登录：AllowAny（role 强制 user，不依赖客户端传参）
  - 绑定/解绑/状态：IsOwnerUser（仅 role=user 且已登录）
  - admin/owner-bindings：IsOperatorOrAbove（仅 admin/operator）
  - 频率限制：当前版本无 DRF throttle（项目无现成 throttle 配置，不引新依赖）；
    建议未来在 nginx 层或增加 DRF throttle 类后补充。OPEN-01（遗留项）

@module MOD-180-03
@implements REQ-AUTH-001, REQ-AUTH-002, REQ-BIND-001 ~ REQ-BIND-004, REQ-OWNER-001
"""

import logging
import requests as http_requests

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .models import OwnerInfo, OwnerUserBinding, WechatBinding
from .serializers import UserRegistrationSerializer
from .views import IsOwnerUser, IsOperatorOrAbove

logger = logging.getLogger('api.views_miniapp')


# ── 内部工具函数 ──────────────────────────────────────────────────────────────

def _issue_token(user) -> str:
    """签发/获取 rest_framework.authtoken.Token，更新 TokenActivity。"""
    from django.utils.timezone import now as django_now
    token, _ = Token.objects.get_or_create(user=user)
    # 复用现有 TokenActivity 机制（v0.9.0 会话超时基础设施）
    try:
        from .models import TokenActivity
        TokenActivity.objects.update_or_create(
            token=token,
            defaults={'last_active_at': django_now()},
        )
    except Exception as exc:
        logger.warning('views_miniapp: TokenActivity 更新失败（非致命）: %s', exc)
    return token.key


def _user_info(user) -> dict:
    """返回标准用户信息摘要（不含敏感字段）。"""
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
    }


# ── 注册（账号密码，REQ-AUTH-001）──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def miniapp_register(request):
    """小程序账号密码注册。role 强制为 'user'（由 UserRegistrationSerializer 保证）。

    Request body: {username, password, password2, email(可选)}
    Response 201: {token, user: {id, username, email, role}}
    Response 400: {errors}
    """
    serializer = UserRegistrationSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    user = serializer.save()
    token_key = _issue_token(user)
    logger.info('miniapp_register: 新用户注册 username=%s', user.username)
    return Response(
        {'token': token_key, 'user': _user_info(user)},
        status=status.HTTP_201_CREATED,
    )


# ── 微信一键登录/注册（REQ-AUTH-002）──────────────────────────────────────────

def _wx_code2session(code: str) -> dict:
    """调用微信 jscode2session API，返回 {openid, session_key, [unionid]}。

    失败时抛 ValueError（包含错误描述），调用方捕获后返回 400/503。
    超时阈值 5s（REQ-AUTH-002 安全约束）。
    """
    appid = getattr(settings, 'WECHAT_MINIAPP_APPID', '')
    secret = getattr(settings, 'WECHAT_MINIAPP_SECRET', '')
    if not appid or not secret:
        raise ValueError('微信小程序 AppID/Secret 未配置，请联系管理员')

    url = 'https://api.weixin.qq.com/sns/jscode2session'
    params = {
        'appid': appid,
        'secret': secret,
        'js_code': code,
        'grant_type': 'authorization_code',
    }
    try:
        resp = http_requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
    except http_requests.Timeout:
        raise ValueError('微信服务器响应超时，请重试')
    except Exception as exc:
        raise ValueError(f'微信服务不可用: {exc}')

    if 'errcode' in data and data['errcode'] != 0:
        raise ValueError(f"微信授权失败（errcode={data['errcode']}）：{data.get('errmsg','')}")

    openid = data.get('openid', '')
    if not openid:
        raise ValueError('微信返回数据异常：缺少 openid')

    return {
        'openid': openid,
        'unionid': data.get('unionid', '') or '',
    }


@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def miniapp_wechat_login(request):
    """微信一键登录/注册。

    Request body: {code: str}  # wx.login() 返回的临时 code
    Response 200: {token, user: {id, username, email, role}, is_new: false}（已有账号）
    Response 201: {token, user: {id, username, email, role}, is_new: true}（新建账号）
    Response 400: {detail: "..."}（code 无效或微信授权失败）
    Response 503: {detail: "..."}（微信服务不可用）
    """
    code = (request.data.get('code') or '').strip()
    if not code:
        return Response({'detail': '缺少 code 参数'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        wx_data = _wx_code2session(code)
    except ValueError as exc:
        logger.warning('miniapp_wechat_login: code2session 失败: %s', exc)
        err_msg = str(exc)
        if '超时' in err_msg or '不可用' in err_msg:
            return Response({'detail': err_msg}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({'detail': err_msg}, status=status.HTTP_400_BAD_REQUEST)

    openid = wx_data['openid']
    unionid = wx_data.get('unionid', '') or ''

    # 查已有绑定
    binding = WechatBinding.objects.filter(openid=openid).select_related('user').first()
    if binding:
        user = binding.user
        is_new = False
        resp_status = status.HTTP_200_OK
        logger.info('miniapp_wechat_login: 已有账号登录 username=%s', user.username)
    else:
        # 新建 User + WechatBinding
        from django.contrib.auth import get_user_model
        User = get_user_model()
        username = f'wx_{openid[:12]}'
        # 防用户名冲突（极罕见，openid[:12] 碰撞时追加后缀）
        if User.objects.filter(username=username).exists():
            username = f'wx_{openid[:20]}'
        user = User.objects.create_user(
            username=username,
            role='user',          # 强制业主角色
            password=None,        # 微信登录无密码（不可密码登录）
        )
        WechatBinding.objects.create(
            user=user,
            openid=openid,
            unionid=unionid or None,
        )
        is_new = True
        resp_status = status.HTTP_201_CREATED
        logger.info('miniapp_wechat_login: 新账号注册 username=%s openid=%s...', username, openid[:8])

    token_key = _issue_token(user)
    return Response(
        {'token': token_key, 'user': _user_info(user), 'is_new': is_new},
        status=resp_status,
    )


# ── 绑定专有部分（REQ-BIND-001 / REQ-BIND-002）────────────────────────────────

@api_view(['POST'])
@permission_classes([IsOwnerUser])
def miniapp_bind(request):
    """扫码/输入 MAC 地址绑定专有部分。

    Request body: {unique_id: str}  # screenMAC（OwnerInfo.unique_id）
    Response 200: {specific_part, location_name, bound_at}
    Response 400: {detail: "..."}（unique_id 格式非法或为空）
    Response 404: {detail: "..."}（unique_id 在系统中不存在）
    Response 409: {detail: "..."}（已绑定该专有部分）
    """
    unique_id = (request.data.get('unique_id') or '').strip()
    if not unique_id:
        return Response({'detail': 'unique_id 不能为空'}, status=status.HTTP_400_BAD_REQUEST)
    if len(unique_id) > 50:
        return Response(
            {'detail': 'unique_id 格式不正确（长度超限）'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    owner = OwnerInfo.objects.filter(unique_id=unique_id).first()
    if owner is None:
        return Response(
            {'detail': '未找到对应的专有部分，请确认二维码或 MAC 地址是否有效'},
            status=status.HTTP_404_NOT_FOUND,
        )

    # 检查是否已绑定（同一用户对同一 owner 已有 active 记录）
    if OwnerUserBinding.objects.filter(
        user=request.user, owner=owner, active=True
    ).exists():
        return Response(
            {'detail': '您已绑定该专有部分'},
            status=status.HTTP_409_CONFLICT,
        )

    binding = OwnerUserBinding.objects.create(
        user=request.user,
        owner=owner,
        active=True,
    )
    logger.info(
        'miniapp_bind: 绑定成功 user=%s specific_part=%s',
        request.user.username, owner.specific_part,
    )
    return Response({
        'specific_part': owner.specific_part,
        'location_name': owner.location_name,
        'bound_at': binding.bound_at.isoformat(),
    }, status=status.HTTP_200_OK)


# ── 解绑（REQ-BIND-003 解绑，自助）──────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsOwnerUser])
def miniapp_unbind(request):
    """业主自助解绑专有部分。

    Request body: {unique_id: str} 或 {specific_part: str}（二选一）
    Response 200: {detail: "解绑成功", specific_part}
    Response 400: {detail: "..."}（参数缺失）
    Response 404: {detail: "..."}（无有效绑定记录）
    """
    unique_id = (request.data.get('unique_id') or '').strip()
    specific_part_input = (request.data.get('specific_part') or '').strip()

    if not unique_id and not specific_part_input:
        return Response(
            {'detail': '请提供 unique_id 或 specific_part'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if unique_id:
        owner = OwnerInfo.objects.filter(unique_id=unique_id).first()
    else:
        owner = OwnerInfo.objects.filter(specific_part=specific_part_input).first()

    if owner is None:
        return Response(
            {'detail': '未找到对应的专有部分'},
            status=status.HTTP_404_NOT_FOUND,
        )

    binding = OwnerUserBinding.objects.filter(
        user=request.user, owner=owner, active=True
    ).first()
    if binding is None:
        return Response(
            {'detail': '未找到有效绑定记录'},
            status=status.HTTP_404_NOT_FOUND,
        )

    binding.active = False
    binding.unbound_at = timezone.now()
    binding.save(update_fields=['active', 'unbound_at'])
    logger.info(
        'miniapp_unbind: 解绑成功 user=%s specific_part=%s',
        request.user.username, owner.specific_part,
    )
    return Response({
        'detail': '解绑成功',
        'specific_part': owner.specific_part,
    }, status=status.HTTP_200_OK)


# ── 查询绑定状态（REQ-BIND-004）──────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsOwnerUser])
def miniapp_bind_status(request):
    """查询当前用户的专有部分绑定状态。

    Response 200:
    {
      "bound": true/false,
      "bindings": [
        {"specific_part": "3-1-7-702", "location_name": "...", "bound_at": "ISO8601"},
        ...
      ]
    }
    """
    active_bindings = (
        OwnerUserBinding.objects
        .filter(user=request.user, active=True)
        .select_related('owner')
        .order_by('bound_at')
    )
    bindings_data = [
        {
            'specific_part': b.owner.specific_part,
            'location_name': b.owner.location_name,
            'bound_at': b.bound_at.isoformat(),
        }
        for b in active_bindings
    ]
    return Response({
        'bound': len(bindings_data) > 0,
        'bindings': bindings_data,
    }, status=status.HTTP_200_OK)


# ── 业主管理页账号绑定列数据源（REQ-OWNER-001，web 端 admin/operator）────────

@api_view(['GET'])
@permission_classes([IsOperatorOrAbove])
def owner_binding_list(request):
    """web 端业主管理页"账号绑定"列数据源。

    返回所有 OwnerInfo 的账号绑定情况（仅 active 绑定）。
    权限：IsOperatorOrAbove（admin/operator 可见，user 不可访问此端点）。

    Response 200:
    {
      "results": [
        {
          "owner_id": int,
          "specific_part": "3-1-7-702",
          "bound_users": [
            {"username": "wx_abc12345", "bound_at": "ISO8601"}
          ]
        },
        ...（仅返回有 active 绑定的 owner，未绑定的不在列表中）
      ]
    }

    前端 OwnerManagementView.vue 用 owner_id 做 join 展示"已关联/未关联"标签。
    """
    # 查询所有 active 绑定，按 owner 分组
    bindings = (
        OwnerUserBinding.objects
        .filter(active=True)
        .select_related('owner', 'user')
        .order_by('owner__specific_part', 'bound_at')
    )

    # 以 owner_id 为 key 聚合
    owner_map: dict = {}
    for b in bindings:
        oid = b.owner.id
        if oid not in owner_map:
            owner_map[oid] = {
                'owner_id': oid,
                'specific_part': b.owner.specific_part,
                'bound_users': [],
            }
        owner_map[oid]['bound_users'].append({
            'username': b.user.username,
            'bound_at': b.bound_at.isoformat(),
        })

    return Response({'results': list(owner_map.values())}, status=status.HTTP_200_OK)
