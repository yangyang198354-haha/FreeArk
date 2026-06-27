"""
api.views_miniapp_device_settings — 小程序业主端·屏端 MQTT 参数配置 API（v1.10.0/v1.11.0）

挂载于 /api/miniapp/device-settings/（urls_miniapp.py 注册）。
架构：小程序**直连**厂端 MQTT broker 收发（DeviceWrite/DeviceStatusUpdate），
后端**不连 broker**，仅：
  GET  config/  下发 broker 连接参数 + 业主已绑定房间(含 screenMac) + 可写白名单/标签
  POST audit/   接收客户端尽力上报的写操作审计，落 PLCWriteRecord(channel='screen-mqtt')

v1.11.0 新增（/api/miniapp/owner/）:
  GET  owner/realtime-params/    业主实时参数（IsOwnerUser + OwnerUserBinding 归属过滤）
  POST owner/ondemand-refresh/   业主 PLC 按需采集代理（IsOwnerUser + 归属过滤）

安全（ADR-01/06/07，OQ-10 全租户风险已书面接受）：
  - 两端点均 IsOwnerUser；config 只下发业主**自己**已绑定房间的 screenMac；
  - audit 校验 screen_mac 必须属于请求业主的 active 绑定，否则 403；
  - 越权写无法在后端拦截（直连），此为已接受残余风险。

@module MOD-1100-BE, MOD-1110-BE-01, MOD-1110-BE-02
@implements REQ-FUNC-001/004/007/008（v1.10.0）；REQ-FUNC-001/003（v1.11.0）；REQ-NFUNC-004
"""

import logging
import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import OwnerUserBinding, PLCWriteRecord
from .screen_param_config import get_screen_param_config, is_writable_attr
from .utils_room_filter import get_available_sub_types, get_allowed_param_names
from .views import IsOwnerUser, _ondemand_inflight, _ONDEMAND_INFLIGHT_TTL

logger = logging.getLogger('api.views_miniapp_device_settings')

# 客户端上报的结果 → PLCWriteRecord.status（复用既有 choices，迁移仅加 channel）
_RESULT_TO_STATUS = {'success': 'success', 'timeout': 'timeout', 'failed': 'failed'}


def _owner_rooms(user):
    """返回业主自己 active 绑定的房间（specific_part/location_name/screen_mac）。"""
    bindings = (
        OwnerUserBinding.objects
        .filter(user=user, active=True)
        .select_related('owner')
        .order_by('bound_at')
    )
    return [
        {
            'specific_part': b.owner.specific_part,
            'location_name': b.owner.location_name,
            'screen_mac': b.owner.unique_id,
        }
        for b in bindings
    ]


@api_view(['GET'])
@permission_classes([IsOwnerUser])
def device_settings_config(request):
    """下发屏端 MQTT 连接参数 + 业主已绑定房间 + 可写配置。

    Response 200:
    {
      "broker": {protocol, host, port, path, username, password},
      "topics": {value_uplink, write_downlink},   # {screenMac} 占位由客户端替换
      "rooms":  [{specific_part, location_name, screen_mac}],   # 仅自己房间
      "config": {writable_attrs, product_code_role, mode_energy_link, link_product_codes}
    }
    """
    broker = {
        'protocol': getattr(settings, 'SCREEN_MQTT_PROTOCOL', 'wxs'),
        'host': getattr(settings, 'SCREEN_MQTT_HOST', ''),
        'port': getattr(settings, 'SCREEN_MQTT_PORT', 8084),
        'path': getattr(settings, 'SCREEN_MQTT_PATH', '/mqtt'),
        'username': getattr(settings, 'SCREEN_MQTT_USERNAME', ''),
        'password': getattr(settings, 'SCREEN_MQTT_PASSWORD', ''),
    }
    topics = {
        'value_uplink': '/screen/upload/screen/to/cloud/{screenMac}',
        'write_downlink': '/screen/service/cloud/to/screen/{screenMac}',
    }
    return Response({
        'broker': broker,
        'topics': topics,
        'rooms': _owner_rooms(request.user),
        'config': get_screen_param_config(),
    }, status=status.HTTP_200_OK)


@api_view(['POST'])
@permission_classes([IsOwnerUser])
def device_settings_audit(request):
    """接收客户端尽力上报的屏端写操作审计。

    Request body:
    {
      "request_id": "<uuid>",          # 批次 id（客户端生成）
      "specific_part": "3-1-7-702",
      "screen_mac": "c5d29c52a237ade5",
      "device_sn": "22154",
      "result": "success|timeout|failed",   # 客户端确认结果（默认 success）
      "items": [{"attr_tag": "mode", "attr_value": "cold", "old_value": "hot"}]
    }
    Response 202: {recorded: n}
    Response 400: 参数缺失 / attr_tag 非白名单
    Response 403: screen_mac 不属于该业主
    """
    data = request.data or {}
    batch_id = (data.get('request_id') or '').strip()
    specific_part = (data.get('specific_part') or '').strip()
    screen_mac = (data.get('screen_mac') or '').strip()
    device_sn = str(data.get('device_sn') or '').strip()
    result = (data.get('result') or 'success').strip()
    items = data.get('items')

    if not screen_mac or not isinstance(items, list) or len(items) == 0:
        return Response({'detail': '缺少 screen_mac 或 items'},
                        status=status.HTTP_400_BAD_REQUEST)

    # 隔离校验：screen_mac 必须属于请求业主的 active 绑定（owner.unique_id）
    owner_macs = {
        b.owner.unique_id
        for b in OwnerUserBinding.objects
        .filter(user=request.user, active=True)
        .select_related('owner')
    }
    if screen_mac not in owner_macs:
        logger.warning('device_settings_audit: 越权 screen_mac=%s user=%s',
                       screen_mac, request.user.username)
        return Response({'detail': '无权操作该设备'}, status=status.HTTP_403_FORBIDDEN)

    # 白名单校验
    for it in items:
        if not isinstance(it, dict) or not is_writable_attr(it.get('attr_tag', '')):
            return Response(
                {'detail': f"attr_tag {it.get('attr_tag') if isinstance(it, dict) else it} 不在可写白名单"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    rec_status = _RESULT_TO_STATUS.get(result, 'success')
    created = 0
    for it in items:
        PLCWriteRecord.objects.create(
            request_id=str(uuid.uuid4()),
            batch_request_id=batch_id or None,
            specific_part=specific_part,
            param_name=it.get('attr_tag', ''),
            old_value=str(it.get('old_value', '') or ''),
            new_value=str(it.get('attr_value', '') or ''),
            operator=request.user.username,
            status=rec_status,
            channel='screen-mqtt',
        )
        created += 1

    logger.info(
        'device_settings_audit: user=%s screen_mac=%s device_sn=%s result=%s items=%d',
        request.user.username, screen_mac, device_sn, rec_status, created,
    )
    return Response({'recorded': created}, status=status.HTTP_202_ACCEPTED)


# ===========================================================================
# v1.11.0 业主端实时参数 + 按需采集（IsOwnerUser + OwnerUserBinding 归属过滤）
# ===========================================================================

# ---------------------------------------------------------------------------
# MOD-1110-BE-01: miniapp_owner_realtime_params
# IFC-1110-BE-01: GET /api/miniapp/owner/realtime-params/?specific_part=X
# @depends: IsOwnerUser, OwnerUserBinding, PLCLatestData, DeviceConfig,
#           DeviceNode, OwnerInfo, get_available_sub_types
# ---------------------------------------------------------------------------

@api_view(['GET'])
@permission_classes([IsOwnerUser])
def miniapp_owner_realtime_params(request):
    """业主专属实时参数端点，含归属过滤 + device_sn 下发。

    GET /api/miniapp/owner/realtime-params/?specific_part=1-1-2-201

    - 严格校验 specific_part 属于请求业主的 active 绑定（REQ-NFUNC-004）。
    - 复用 get_device_realtime_params 的核心分组逻辑（不重复实现）。
    - 额外返回 screen_mac（OwnerInfo.unique_id）和 device_sns（DeviceNode.device_sn 列表），
      供前端决定走路径 A（MQTT）还是路径 B（ondemand-refresh）。

    Response 200: {
      "success": true,
      "specific_part": str,
      "screen_mac": str,       # 空字符串 = 无屏端，走路径 B
      "device_sns": [int],     # 空列表 = 设备树未同步，走路径 B
      "data": { group → sub_type → { display, params:[{param_name,display_name,value,collected_at,is_stale}] } }
    }
    Response 400: {"success": false, "error": "specific_part 参数为必填项"}
    Response 403: {"detail": "无权访问该专有部分"}
    """
    from datetime import datetime as _dt, timedelta as _td
    from .models import PLCLatestData, DeviceConfig, DeviceNode, OwnerInfo

    specific_part = request.GET.get('specific_part', '').strip()
    if not specific_part:
        return Response(
            {'success': False, 'error': 'specific_part 参数为必填项'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── 归属校验（REQ-NFUNC-004，D-05）────────────────────────────────────────
    allowed_parts = {
        b.owner.specific_part
        for b in OwnerUserBinding.objects
        .filter(user=request.user, active=True)
        .select_related('owner')
    }
    if specific_part not in allowed_parts:
        logger.warning(
            'miniapp_owner_realtime_params: 越权访问 specific_part=%s user=%s',
            specific_part, request.user.username,
        )
        return Response({'detail': '无权访问该专有部分'}, status=status.HTTP_403_FORBIDDEN)

    # ── 核心分组逻辑（复用 get_device_realtime_params，ADR-1110-01）─────────────
    available_sub_types = get_available_sub_types(specific_part)

    latest_data_qs = PLCLatestData.objects.filter(specific_part=specific_part)
    latest_by_param = {record.param_name: record for record in latest_data_qs}

    configs_qs = DeviceConfig.objects.filter(is_active=True).order_by('id')

    _STALE_MINUTES = 10
    _stale_cutoff = _dt.now() - _td(minutes=_STALE_MINUTES)

    result = {}
    for cfg in configs_qs:
        group_key = cfg.group
        sub_key = cfg.sub_type

        if sub_key not in available_sub_types:
            continue

        if group_key not in result:
            result[group_key] = {'display': cfg.group_display, 'sub_types': {}}
        if sub_key not in result[group_key]['sub_types']:
            result[group_key]['sub_types'][sub_key] = {
                'display': cfg.sub_type_display,
                'params': [],
            }

        record = latest_by_param.get(cfg.param_name)
        if record is None:
            continue

        is_stale = bool(record.collected_at and record.collected_at < _stale_cutoff)
        result[group_key]['sub_types'][sub_key]['params'].append({
            'param_name': cfg.param_name,
            'display_name': cfg.display_name,
            'value': record.value,
            'collected_at': record.collected_at.strftime('%Y-%m-%d %H:%M:%S') if record.collected_at else None,
            'is_stale': is_stale,
        })

    # 移除无参数的 sub_type / group
    for group_key in list(result.keys()):
        sub_types = result[group_key]['sub_types']
        for sub_key in [k for k, v in sub_types.items() if not v['params']]:
            del sub_types[sub_key]
        if not sub_types:
            del result[group_key]

    # ── screen_mac（ADR-1110-02）─────────────────────────────────────────────
    try:
        owner_info = OwnerInfo.objects.get(specific_part=specific_part)
        screen_mac = owner_info.unique_id or ''
    except OwnerInfo.DoesNotExist:
        screen_mac = ''

    # ── device_sns（ADR-1110-02，D-02）──────────────────────────────────────
    device_sns = list(
        DeviceNode.objects
        .filter(room__floor__owner__specific_part=specific_part)
        .values_list('device_sn', flat=True)
        .distinct()
    )

    return Response({
        'success': True,
        'specific_part': specific_part,
        'screen_mac': screen_mac,
        'device_sns': device_sns,
        'data': result,
    })


# ---------------------------------------------------------------------------
# MOD-1110-BE-02: miniapp_owner_ondemand_refresh
# IFC-1110-BE-02: POST /api/miniapp/owner/ondemand-refresh/
# @depends: IsOwnerUser, OwnerUserBinding, _publish_ondemand_mqtt（提取自 views.py）
# ---------------------------------------------------------------------------

# 进程内防重入缓存（FND-003 修复）：与 views.py device_ondemand_refresh **共用同一字典对象**，
# 使 operator 入口(views.device_ondemand_refresh)与 owner 入口(本模块)跨入口防重入生效——
# 同一 specific_part 在 TTL 内无论从哪个入口触发都只发布一次 MQTT。
# 保留 _owner_ondemand_inflight 名称作为别名，向后兼容既有单测。
_owner_ondemand_inflight: dict = _ondemand_inflight
_OWNER_ONDEMAND_INFLIGHT_TTL = _ONDEMAND_INFLIGHT_TTL


def _publish_ondemand_mqtt(specific_part: str):
    """提取自 device_ondemand_refresh 的 MQTT publish 私有工具函数（ADR-1110-03）。

    向 /datacollection/plc/ondemand/request/{specific_part} 发布按需采集指令。
    返回 ("accepted"|"duplicate"|"error", detail_str)。

    防重入：25s 内同一 specific_part 重复调用直接返回 "duplicate"。
    """
    import time as _time
    import json as _json
    import os as _os
    import datetime as _dt_mod
    import paho.mqtt.publish as mqtt_publish

    now = _time.monotonic()
    last_ts = _owner_ondemand_inflight.get(specific_part)
    if last_ts is not None and (now - last_ts) < _OWNER_ONDEMAND_INFLIGHT_TTL:
        logger.info(
            '_publish_ondemand_mqtt: 防重入幂等返回 duplicate: specific_part=%s', specific_part
        )
        return 'duplicate', 'inflight'

    mqtt_config_path = _os.path.join(
        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
        'mqtt_config.json',
    )
    try:
        with open(mqtt_config_path, 'r', encoding='utf-8') as f:
            mqtt_cfg = _json.load(f)
    except Exception:
        mqtt_cfg = {}

    broker_host = mqtt_cfg.get('host', '192.168.31.98')
    broker_port = int(mqtt_cfg.get('port', 32788))
    broker_user = mqtt_cfg.get('username') or None
    broker_pass = mqtt_cfg.get('password') or None

    request_topic = f'/datacollection/plc/ondemand/request/{specific_part}'

    _allowed_params = get_allowed_param_names(specific_part)
    payload_dict = {
        'specific_part': specific_part,
        'requested_at': _dt_mod.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
    }
    if _allowed_params:
        payload_dict['allowed_params'] = _allowed_params

    auth = {'username': broker_user, 'password': broker_pass} if broker_user else None
    try:
        mqtt_publish.single(
            request_topic,
            payload=_json.dumps(payload_dict),
            qos=1,
            hostname=broker_host,
            port=broker_port,
            auth=auth,
        )
        logger.info(
            '_publish_ondemand_mqtt: 已发布 MQTT: topic=%s specific_part=%s',
            request_topic, specific_part,
        )
    except Exception as e:
        logger.error(
            '_publish_ondemand_mqtt: MQTT 发布失败: specific_part=%s error=%s',
            specific_part, e, exc_info=True,
        )
        return 'error', str(e)

    _owner_ondemand_inflight[specific_part] = now
    return 'accepted', ''


@api_view(['POST'])
@permission_classes([IsOwnerUser])
def miniapp_owner_ondemand_refresh(request):
    """业主 PLC 按需采集代理端点，含归属过滤（ADR-1110-03）。

    POST /api/miniapp/owner/ondemand-refresh/
    Request body: {"specific_part": "1-1-2-201"}

    - 校验 specific_part 属于请求业主的 active 绑定（REQ-NFUNC-004）。
    - 归属通过后执行与 device_ondemand_refresh 相同的 MQTT publish 逻辑。

    Response 202: {"status": "accepted"|"duplicate", "specific_part": str}
    Response 400: {"detail": "specific_part 为必填项"}
    Response 403: {"detail": "无权操作该专有部分"}
    Response 503: {"detail": "MQTT broker 不可达，无法提交采集请求"}
    """
    from .models import OwnerUserBinding as _OUB

    specific_part = (request.data.get('specific_part') or '').strip()
    if not specific_part:
        return Response({'detail': 'specific_part 为必填项'}, status=status.HTTP_400_BAD_REQUEST)

    # ── 归属校验（REQ-NFUNC-004，D-05）────────────────────────────────────────
    allowed_parts = {
        b.owner.specific_part
        for b in _OUB.objects
        .filter(user=request.user, active=True)
        .select_related('owner')
    }
    if specific_part not in allowed_parts:
        logger.warning(
            'miniapp_owner_ondemand_refresh: 越权操作 specific_part=%s user=%s',
            specific_part, request.user.username,
        )
        return Response({'detail': '无权操作该专有部分'}, status=status.HTTP_403_FORBIDDEN)

    # ── 触发 MQTT 按需采集（复用提取的私有工具函数）──────────────────────────
    outcome, detail = _publish_ondemand_mqtt(specific_part)

    if outcome == 'error':
        return Response(
            {'detail': f'MQTT broker 不可达，无法提交采集请求: {detail}'},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    # outcome == 'accepted' 或 'duplicate'，均返回 202
    return Response({'status': outcome, 'specific_part': specific_part},
                    status=status.HTTP_202_ACCEPTED)
