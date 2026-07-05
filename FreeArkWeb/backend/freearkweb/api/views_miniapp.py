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
  POST /api/miniapp/profile/update/       更新头像和昵称（v1.12.0, REQ-PROFILE-004）

安全约束：
  - 注册/微信登录：AllowAny（role 强制 user，不依赖客户端传参）
  - 绑定/解绑/状态：IsOwnerUser（仅 role=user 且已登录）
  - admin/owner-bindings：IsOperatorOrAbove（仅 admin/operator）
  - 频率限制：当前版本无 DRF throttle（项目无现成 throttle 配置，不引新依赖）；
    建议未来在 nginx 层或增加 DRF throttle 类后补充。OPEN-01（遗留项）

@module MOD-180-03
@implements REQ-AUTH-001, REQ-AUTH-002, REQ-BIND-001 ~ REQ-BIND-004, REQ-OWNER-001
"""

import base64
import json
import logging
import os
import uuid
import mimetypes
import requests as http_requests

from django.conf import settings
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.authtoken.models import Token

from .models import OwnerInfo, OwnerUserBinding, WechatBinding
from .serializers import UserRegistrationSerializer, PersonaSerializer
from .views import IsOwnerUser, IsOperatorOrAbove

logger = logging.getLogger('api.views_miniapp')


# ── 内部工具函数 ──────────────────────────────────────────────────────────────

def _issue_token(user, extended_session: bool = False) -> str:
    """签发/获取 rest_framework.authtoken.Token，更新 TokenActivity。

    v1.12.0: extended_session 参数决定 TokenActivity.extended_session 值，
    控制会话超时阈值（False→30min, True→7天）。向前兼容——默认 False 保持旧行为。
    """
    from django.utils.timezone import now as django_now
    token, _ = Token.objects.get_or_create(user=user)
    # 复用现有 TokenActivity 机制（v0.9.0 会话超时基础设施）
    try:
        from .models import TokenActivity
        defaults = {'last_active_at': django_now()}
        if extended_session:
            defaults['extended_session'] = True
        TokenActivity.objects.update_or_create(
            token=token,
            defaults=defaults,
        )
    except Exception as exc:
        logger.warning('views_miniapp: TokenActivity 更新失败（非致命）: %s', exc)
    return token.key


def _user_info(user) -> dict:
    """返回标准用户信息摘要（不含敏感字段）。v1.12.0 增加 avatar_url 和 nickname。"""
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': user.role,
        'avatar_url': user.avatar_url or None,
        'nickname': user.nickname or None,
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

    # v1.12.0: 读取"记住我"参数（默认 False），决定会话超时阈值
    remember_me = request.data.get('remember_me', False)
    if isinstance(remember_me, str):
        remember_me = remember_me.lower() in ('true', '1', 'yes')

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

    token_key = _issue_token(user, extended_session=remember_me)
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


# ── 更新头像和昵称（v1.12.0, REQ-PROFILE-004）────────────────────────────────

# 允许的头像图片 MIME 类型
_PROFILE_AVATAR_ALLOWED_CONTENT_TYPES = {
    'image/png', 'image/jpeg', 'image/gif', 'image/webp',
}
# 头像最大文件大小（字节）
_PROFILE_AVATAR_MAX_SIZE = 2 * 1024 * 1024  # 2MB

# content_type → 文件扩展名映射（用于 UUID 重命名时保留正确扩展名）
_PROFILE_AVATAR_EXT_MAP = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/gif': '.gif',
    'image/webp': '.webp',
}


@api_view(['POST'])
@permission_classes([permissions.IsAuthenticated])
def miniapp_profile_update(request):
    # v1.12.0: 使用 IsAuthenticated 而非 IsOwnerUser——头像昵称是用户自身资料，
    # 不应限制 role。端点仅写入 request.user，无横向越权风险。
    """更新当前用户的头像和/或昵称（v1.12.0）。

    Request (multipart/form-data):
      - avatar: File (optional) — 头像图片文件，最大 2MB，仅 PNG/JPG/GIF/WebP
      - nickname: String (optional) — 用户昵称，最大 100 字符

    Response 200: {avatar_url: str|null, nickname: str|null}
    Response 400: {detail: "..."}  参数缺失/非法
    Response 401: {detail: "..."}  未认证
    """
    avatar_file = request.FILES.get('avatar') if hasattr(request, 'FILES') else None
    nickname = (request.data.get('nickname') or '').strip() or None

    # 校验：至少提供一个参数
    if avatar_file is None and nickname is None:
        return Response(
            {'detail': '请至少提供 avatar 或 nickname 其中一项'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user
    avatar_url_out = None

    # 处理头像文件
    if avatar_file is not None:
        # 校验 MIME 类型
        content_type = getattr(avatar_file, 'content_type', '') or ''
        if content_type not in _PROFILE_AVATAR_ALLOWED_CONTENT_TYPES:
            # 尝试验证实际 content_type（multipart 中可能为 application/octet-stream）
            guessed, _ = mimetypes.guess_type(getattr(avatar_file, 'name', ''))
            if guessed and guessed in _PROFILE_AVATAR_ALLOWED_CONTENT_TYPES:
                content_type = guessed
            else:
                return Response(
                    {'detail': '仅支持 PNG、JPG、GIF、WebP 格式的图片'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # 校验文件大小
        if avatar_file.size > _PROFILE_AVATAR_MAX_SIZE:
            return Response(
                {'detail': '图片大小不能超过 2MB'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # UUID 重命名 + 保留原始扩展名
        ext = _PROFILE_AVATAR_EXT_MAP.get(content_type, '.png')
        filename = f'{uuid.uuid4().hex}{ext}'

        # 确保 MEDIA_ROOT/avatars/ 目录存在
        media_root = getattr(settings, 'MEDIA_ROOT', None)
        if media_root is None:
            logger.error('miniapp_profile_update: MEDIA_ROOT 未配置')
            return Response(
                {'detail': '服务器存储配置错误，请联系管理员'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        avatars_dir = os.path.join(str(media_root), 'avatars')
        os.makedirs(avatars_dir, exist_ok=True)

        file_path = os.path.join(avatars_dir, filename)

        # 删除旧头像文件（若存在）
        if user.avatar_url:
            try:
                # 从旧 URL 反推文件路径（MEDIA_URL + 'avatars/' + old_filename）
                media_url = getattr(settings, 'MEDIA_URL', '/media/')
                old_rel = user.avatar_url
                # 处理绝对 URL：去掉 MEDIA_URL 前缀获取相对路径
                if old_rel.startswith(media_url):
                    old_rel = old_rel[len(media_url):]
                if old_rel.startswith('avatars/'):
                    old_file = os.path.join(str(media_root), old_rel)
                    if os.path.isfile(old_file):
                        os.remove(old_file)
            except Exception as exc:
                logger.warning(
                    'miniapp_profile_update: 删除旧头像文件失败（非致命）: %s', exc,
                )

        # 保存新文件
        with open(file_path, 'wb+') as dest:
            for chunk in avatar_file.chunks():
                dest.write(chunk)

        # 构造 avatar_url（绝对路径 = MEDIA_URL + 相对路径）
        media_url = getattr(settings, 'MEDIA_URL', '/media/')
        avatar_url_out = f'{media_url}avatars/{filename}'
        user.avatar_url = avatar_url_out

    # 处理昵称
    nickname_out = None
    if nickname is not None:
        if len(nickname) > 100:
            return Response(
                {'detail': '昵称不能超过 100 个字符'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.nickname = nickname
        nickname_out = nickname

    user.save(update_fields=[f for f in ['avatar_url', 'nickname']
                              if (avatar_file is not None and f == 'avatar_url')
                              or (nickname is not None and f == 'nickname')])

    logger.info(
        'miniapp_profile_update: 资料更新 user=%s avatar=%s nickname=%s',
        user.username,
        avatar_url_out or '(未更新)',
        nickname_out or '(未更新)',
    )

    return Response({
        'avatar_url': avatar_url_out or user.avatar_url or None,
        'nickname': nickname_out or user.nickname or None,
    }, status=status.HTTP_200_OK)


# ── v1.12.0 人格偏好 ──────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsOwnerUser])
def miniapp_persona_get(request):
    """读取当前用户的人格偏好。

    Response 200: {greeting_style: str|null, tone_style: str|null}
        未设置时两个字段均为 null（前端据此判断是否展示首次设置引导）。
    """
    user = request.user
    persona = user.persona if isinstance(user.persona, dict) else {}
    return Response({
        'greeting_style': persona.get('greeting_style') or None,
        'tone_style': persona.get('tone_style') or None,
    })


@api_view(['PUT'])
@permission_classes([IsOwnerUser])
def miniapp_persona_update(request):
    """更新当前用户的人格偏好。

    Request body (JSON): {greeting_style?: str, tone_style?: str}
        至少一个非空，max 50 chars each。
    Response 200: {greeting_style: str|null, tone_style: str|null}
    Response 400: {detail: "..."} 参数校验失败
    """
    serializer = PersonaSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(
            {'detail': '; '.join(
                f'{k}: {", ".join(v) if isinstance(v, list) else v}'
                for k, v in serializer.errors.items())},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = request.user
    validated = serializer.validated_data
    current = user.persona if isinstance(user.persona, dict) else {}

    # 只更新传入的非空字段，未传入的保留原值
    if 'greeting_style' in validated and validated['greeting_style']:
        current['greeting_style'] = validated['greeting_style']
    if 'tone_style' in validated and validated['tone_style']:
        current['tone_style'] = validated['tone_style']

    user.persona = current
    user.save(update_fields=['persona', 'updated_at'])

    return Response({
        'greeting_style': current.get('greeting_style') or None,
        'tone_style': current.get('tone_style') or None,
    })


# ── v1.12.0 语音识别 ──────────────────────────────────────────────────────────

_VOICE_MAX_BYTES = 10 * 1024 * 1024  # 最大 10MB（60s WAV ≈ 1.9MB）


@api_view(['POST'])
@permission_classes([IsOwnerUser])
def miniapp_voice_recognize(request):
    """语音识别端点（v1.12.0 MOD-P1208 方案B）。

    支持两种提交方式：
      1. multipart/form-data: audio_file=<WAV 文件>（旧版 uploadFile，需 uploadFile 白名单）
      2. application/json: {"audio_base64": "...", "format": "wav"}（新版，走 request 白名单）

    Response 200: {text: "识别结果文字"}
    Response 400: {detail: "..."} 参数缺失/格式错误
    Response 503: {detail: "语音识别服务暂不可用"} ASR 未就绪
    """
    wav_bytes = None

    # 方式1：multipart（旧版 uploadFile）
    audio_file = request.FILES.get('audio_file') if hasattr(request, 'FILES') else None
    if audio_file is not None:
        if audio_file.size > _VOICE_MAX_BYTES:
            return Response(
                {'detail': f'音频文件不能超过 {_VOICE_MAX_BYTES // 1024 // 1024}MB'},
                status=400,
            )
        wav_bytes = audio_file.read()

    # 方式2：base64 JSON（新版，绕过 uploadFile 域名限制）
    if wav_bytes is None and hasattr(request, 'data'):
        body = request.data
        if isinstance(body, dict) and body.get('audio_base64'):
            b64_str = body['audio_base64']
            if len(b64_str) > _VOICE_MAX_BYTES * 1.4:  # base64 比原始大 ~33%
                return Response(
                    {'detail': f'音频数据不能超过 {_VOICE_MAX_BYTES // 1024 // 1024}MB'},
                    status=400,
                )
            try:
                wav_bytes = base64.b64decode(b64_str)
            except Exception:
                return Response(
                    {'detail': '音频数据格式错误（base64 解码失败）'},
                    status=400,
                )

    if wav_bytes is None:
        return Response(
            {'detail': '请提供音频数据（audio_file 或 audio_base64）'},
            status=400,
        )

    try:
        from .asr_service import get_recognizer
        recognizer = get_recognizer()
        if recognizer is None:
            return Response(
                {'detail': '语音识别服务暂不可用，请稍后重试或使用文字输入'},
                status=503,
            )
        text = recognizer.recognize(wav_bytes)
        if not text:
            return Response(
                {'detail': '未识别到语音内容，请确保语音清晰后重试'},
                status=422,
            )
        return Response({'text': text})
    except ValueError as exc:
        return Response(
            {'detail': f'音频格式不支持：{exc}'},
            status=400,
        )
    except Exception as exc:
        logger.exception('miniapp_voice_recognize: 识别异常')
        return Response(
            {'detail': '语音识别处理失败，请使用文字输入'},
            status=500,
        )
