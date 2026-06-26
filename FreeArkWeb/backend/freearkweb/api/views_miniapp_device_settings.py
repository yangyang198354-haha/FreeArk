"""
api.views_miniapp_device_settings — 小程序业主端·屏端 MQTT 参数配置 API（v1.10.0）

挂载于 /api/miniapp/device-settings/（urls_miniapp.py 注册）。
架构：小程序**直连**厂端 MQTT broker 收发（DeviceWrite/DeviceStatusUpdate），
后端**不连 broker**，仅：
  GET  config/  下发 broker 连接参数 + 业主已绑定房间(含 screenMac) + 可写白名单/标签
  POST audit/   接收客户端尽力上报的写操作审计，落 PLCWriteRecord(channel='screen-mqtt')

安全（ADR-01/06/07，OQ-10 全租户风险已书面接受）：
  - 两端点均 IsOwnerUser；config 只下发业主**自己**已绑定房间的 screenMac；
  - audit 校验 screen_mac 必须属于请求业主的 active 绑定，否则 403；
  - 越权写无法在后端拦截（直连），此为已接受残余风险。

@module MOD-1100-BE
@implements REQ-FUNC-001/004/007/008（v1.10.0）
"""

import logging
import uuid

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .models import OwnerUserBinding, PLCWriteRecord
from .screen_param_config import get_screen_param_config, is_writable_attr
from .views import IsOwnerUser

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
