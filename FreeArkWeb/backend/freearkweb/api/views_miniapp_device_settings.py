"""
api.views_miniapp_device_settings — 小程序业主端·屏端 MQTT 参数配置 API（v1.10.0/v1.11.0/v1.11.1/v1.11.2）

挂载于 /api/miniapp/device-settings/（urls_miniapp.py 注册）。
架构：小程序**直连**厂端 MQTT broker 收发（DeviceWrite/DeviceStatusUpdate），
后端**不连 broker**，仅：
  GET  config/  下发 broker 连接参数 + 业主已绑定房间(含 screenMac) + 可写白名单/标签
  POST audit/   接收客户端尽力上报的写操作审计，落 PLCWriteRecord(channel='screen-mqtt')

v1.11.0 新增（/api/miniapp/owner/）:
  GET  owner/realtime-params/    业主实时参数（IsOwnerUser + OwnerUserBinding 归属过滤）
  POST owner/ondemand-refresh/   业主 PLC 按需采集代理（IsOwnerUser + 归属过滤）

v1.11.1 新增（/api/miniapp/owner/）:
  GET  owner/structure/          业主设备树结构骨架（IsOwnerUser + 归属过滤，不含 PLCLatestData）
                                 结构与实时数据完全解耦，REQ-FUNC-001-C 结构完整性保证。

v1.11.2 变更：
  GET  owner/realtime-params/ — 新增 PANEL_DISPLAY_MAP，对 panel_* sub_type 的 display
       字段覆写为纯房间名（书房/次卧/主卧/儿童房），去除"-温控面板"后缀。
       系统级 sub_type（main_thermostat 等）通过 fallback 保持 DB 原值。
       不修改 DB 字段 sub_type_display，Web 端视图路径天然不受影响。
       @implements REQ-FUNC-001/002（v1.11.2）；REQ-NFUNC-001/002/003/004

安全（ADR-01/06/07，OQ-10 全租户风险已书面接受）：
  - 两端点均 IsOwnerUser；config 只下发业主**自己**已绑定房间的 screenMac；
  - audit 校验 screen_mac 必须属于请求业主的 active 绑定，否则 403；
  - 越权写无法在后端拦截（直连），此为已接受残余风险。

@module MOD-1100-BE, MOD-1110-BE-01, MOD-1110-BE-02, MOD-1111-BE-01, MOD-1120-BE
@implements REQ-FUNC-001/004/007/008（v1.10.0）；REQ-FUNC-001/003（v1.11.0）；
            REQ-FUNC-001（v1.11.1修订版）/REQ-FUNC-001-C/REQ-FUNC-006；REQ-NFUNC-004；
            REQ-FUNC-001/002（v1.11.2）；REQ-NFUNC-001/002/003/004（v1.11.2）
"""

import logging
import uuid
from datetime import datetime, timedelta

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import (
    OwnerUserBinding, PLCWriteRecord,
    PLCLatestData, DeviceConfig, DeviceNode, OwnerInfo,
    DeviceFloor, DeviceRoom,
)
from .screen_param_config import get_screen_param_config, is_writable_attr
from .utils_room_filter import (
    get_available_sub_types, get_allowed_param_names,
    _match_panel_sub_types,  # ADR-1111-02: 面板 sub_type 推导（只读复用）
)
from .views import (
    IsOwnerUser, _ondemand_inflight, _ONDEMAND_INFLIGHT_TTL,
    _load_ondemand_broker_config,
)

logger = logging.getLogger('api.views_miniapp_device_settings')

# 客户端上报的结果 → PLCWriteRecord.status（复用既有 choices，迁移仅加 channel）
_RESULT_TO_STATUS = {'success': 'success', 'timeout': 'timeout', 'failed': 'failed'}

# 小程序端温控面板 sub_type → 纯房间名（不含"-温控面板"后缀）
# 来源：utils_room_filter.py SUB_TYPE_TO_ROOM_KEYWORDS 注释 +
#        Web RoomHistoryView.vue ROOM_TABS 对照（study_room→书房 / bedroom→次卧 / children_room→主卧）
# ⚠ 注意：panel_bedroom → 次卧（非主卧），panel_children_room → 主卧（非儿童房）
#   此反直觉映射已由业务方最终确认（REQ-FUNC-002 关键陷阱，v1.11.2 2026-06-28）
PANEL_DISPLAY_MAP: dict[str, str] = {
    'panel_study_room':      '书房',
    'panel_bedroom':         '次卧',   # ⚠ 非"主卧"
    'panel_children_room':   '主卧',   # ⚠ 非"儿童房"
    'panel_fourth_children': '儿童房',
}


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
    _stale_cutoff = datetime.now() - timedelta(minutes=_STALE_MINUTES)

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
                'display': PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display),
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
    owner_info = OwnerInfo.objects.filter(specific_part=specific_part).first()
    screen_mac = (owner_info.unique_id or '') if owner_info else ''

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
    import paho.mqtt.publish as mqtt_publish

    now = _time.monotonic()
    last_ts = _owner_ondemand_inflight.get(specific_part)
    if last_ts is not None and (now - last_ts) < _OWNER_ONDEMAND_INFLIGHT_TTL:
        logger.info(
            '_publish_ondemand_mqtt: 防重入幂等返回 duplicate: specific_part=%s', specific_part
        )
        return 'duplicate', 'inflight'

    # FND-004：broker 配置加载复用 views._load_ondemand_broker_config，消除与
    # device_ondemand_refresh 的路径/解析重复（两入口同一份 mqtt_config.json 逻辑）。
    broker_host, broker_port, broker_user, broker_pass = _load_ondemand_broker_config()

    request_topic = f'/datacollection/plc/ondemand/request/{specific_part}'

    _allowed_params = get_allowed_param_names(specific_part)
    payload_dict = {
        'specific_part': specific_part,
        'requested_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
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


# ===========================================================================
# v1.11.1 业主设备树结构骨架端点（IsOwnerUser + OwnerUserBinding 归属过滤）
# 与实时数据完全解耦，不含任何 PLCLatestData 字段（REQ-FUNC-001-C）
# ===========================================================================

# ---------------------------------------------------------------------------
# MOD-1111-BE-01: miniapp_owner_structure
# IFC-1111-BE-01: GET /api/miniapp/owner/structure/?specific_part=X
# @depends: IsOwnerUser, OwnerUserBinding, DeviceFloor, DeviceRoom, DeviceNode,
#           DeviceConfig, _match_panel_sub_types（utils_room_filter，只读）
# ---------------------------------------------------------------------------

# sub_type 推导常量（ADR-1111-02）
# 来源：fault_consumer/constants.py SUB_TYPE_ROOM_FILTER 实测验证
_PRODUCT_CODE_TO_SUB_TYPE: dict = {
    '260001': 'main_thermostat',
    '130004': 'fresh_air',
    '270001': 'hydraulic_module',
    '250001': 'energy_meter',
    '100007': 'air_quality',
}
_PANEL_PRODUCT_CODE: str = '120003'


def _infer_sub_type(product_code: str, ori_room_name: str) -> str:
    """推导 DeviceNode → sub_type（ADR-1111-02）。

    面板设备（product_code='120003'）：调用 _match_panel_sub_types([ori_room_name]) 取首个结果。
    系统级设备：查 _PRODUCT_CODE_TO_SUB_TYPE 字典。
    未知 product_code：返回空字符串（前端叠加时跳过，不影响骨架展示）。
    """
    if product_code == _PANEL_PRODUCT_CODE:
        matched = _match_panel_sub_types([ori_room_name])
        return next(iter(matched), '')
    return _PRODUCT_CODE_TO_SUB_TYPE.get(product_code, '')


@api_view(['GET'])
@permission_classes([IsOwnerUser])
def miniapp_owner_structure(request):
    """业主专属设备树结构骨架端点（v1.11.1，MOD-1111-BE-01）。

    GET /api/miniapp/owner/structure/?specific_part=3-1-7-702

    - 严格归属校验：specific_part 必须属于请求业主的 active 绑定（REQ-NFUNC-004）。
    - 遍历 DeviceFloor → DeviceRoom → DeviceNode（prefetch_related，2 次 DB 往返）。
    - sub_type 推导：ADR-1111-02（product_code 查表 / _match_panel_sub_types）。
    - 分组：is_panel_room（_match_panel_sub_types 非空）→ rooms[]；其余 → system_devices[]（ADR-1111-03）。
    - params_skeleton（OQ-1111-A 选 Option A）：批量查 DeviceConfig，为每个设备附 params 定义列表。
    - 不含任何 PLCLatestData 字段（REQ-FUNC-001-C）。
    - 设备树未同步（DeviceFloor 无记录）→ sync_status="pending" + 空数组（OQ-E5）。

    Response 200:
    {
      "success": true,
      "specific_part": str,
      "sync_status": "ok" | "pending",
      "sync_status_detail": str,     # sync_status="pending" 时填充
      "rooms": [{room_id, room_name, ori_room_name,
                 devices:[{device_sn, device_name, sub_type, product_code,
                           params:[{param_name, display_name}]}]}],
      "system_devices": [{device_sn, device_name, sub_type, product_code,
                          params:[{param_name, display_name}]}],
      "device_sns": [int],           # 所有设备 SN 扁平列表，供前端 connectRoom 使用
    }
    Response 400: {"success": false, "error": "specific_part 参数为必填项"}
    Response 403: {"detail": "无权访问该专有部分"}
    """
    specific_part = request.GET.get('specific_part', '').strip()
    if not specific_part:
        return Response(
            {'success': False, 'error': 'specific_part 参数为必填项'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # ── 归属校验（REQ-NFUNC-004，与 miniapp_owner_realtime_params 范式一致）────
    allowed_parts = {
        b.owner.specific_part
        for b in OwnerUserBinding.objects
        .filter(user=request.user, active=True)
        .select_related('owner')
    }
    if specific_part not in allowed_parts:
        logger.warning(
            'miniapp_owner_structure: 越权访问 specific_part=%s user=%s',
            specific_part, request.user.username,
        )
        return Response({'detail': '无权访问该专有部分'}, status=status.HTTP_403_FORBIDDEN)

    # ── 设备树遍历（prefetch_related，一次批量查询）────────────────────────────
    floors = list(
        DeviceFloor.objects
        .filter(owner__specific_part=specific_part)
        .prefetch_related('rooms__devices')
        .select_related('owner')
    )

    sync_status = 'ok' if floors else 'pending'

    rooms_list = []
    system_devices = []
    all_device_sns = []

    # device_entries_by_sub_type：sub_type → 待附 params 的 entry 列表
    # 用于批量填充 params_skeleton（OQ-1111-A Option A）
    device_entries_by_sub_type: dict = {}
    all_sub_types_seen: set = set()

    for floor in floors:
        for room in floor.rooms.all():
            # 分组判定（ADR-1111-03）：_match_panel_sub_types 非空 → 面板房间
            panel_sub_types = _match_panel_sub_types([room.ori_room_name])
            is_panel_room = bool(panel_sub_types)

            room_devices = []
            for device in room.devices.all():
                sub_type = _infer_sub_type(device.product_code, room.ori_room_name)
                entry = {
                    'device_sn': device.device_sn,
                    'device_name': device.device_name,
                    'sub_type': sub_type,
                    'product_code': device.product_code,
                    'params': [],  # 下方批量填充（OQ-1111-A）
                }
                all_device_sns.append(device.device_sn)
                if sub_type:
                    all_sub_types_seen.add(sub_type)
                    device_entries_by_sub_type.setdefault(sub_type, []).append(entry)

                if is_panel_room:
                    room_devices.append(entry)
                else:
                    system_devices.append(entry)

            if is_panel_room:
                rooms_list.append({
                    'room_id': room.id,
                    'room_name': room.room_name or '',
                    'ori_room_name': room.ori_room_name or '',
                    'devices': room_devices,
                })

    # ── params_skeleton（OQ-1111-A Option A）────────────────────────────────
    # 批量查 DeviceConfig，按 sub_type 分组后附到各 device entry。
    # 不查 PLCLatestData，不含 value 字段——骨架仅含 param_name/display_name。
    if all_sub_types_seen:
        configs_qs = (
            DeviceConfig.objects
            .filter(sub_type__in=all_sub_types_seen, is_active=True)
            .order_by('id')
            .values('sub_type', 'param_name', 'display_name')
        )
        sub_type_params_map: dict = {}
        for cfg in configs_qs:
            sub_type_params_map.setdefault(cfg['sub_type'], []).append({
                'param_name': cfg['param_name'],
                'display_name': cfg['display_name'],
            })

        for sub_type, entries in device_entries_by_sub_type.items():
            params = sub_type_params_map.get(sub_type, [])
            for entry in entries:
                entry['params'] = params

    # ── 构造响应 ─────────────────────────────────────────────────────────────
    resp: dict = {
        'success': True,
        'specific_part': specific_part,
        'sync_status': sync_status,
        'rooms': rooms_list,
        'system_devices': system_devices,
        'device_sns': all_device_sns,
    }
    if sync_status == 'pending':
        resp['sync_status_detail'] = '设备树尚未同步，请稍后刷新'

    logger.info(
        'miniapp_owner_structure: user=%s specific_part=%s sync_status=%s '
        'rooms=%d system_devices=%d device_sns=%d',
        request.user.username, specific_part, sync_status,
        len(rooms_list), len(system_devices), len(all_device_sns),
    )
    return Response(resp)
