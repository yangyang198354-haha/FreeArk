import json
import logging
import time
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import DeviceConfig, DeviceAttrDef, PLCLatestData, OwnerInfo, PLCWriteRecord
from .param_value_label import get_value_options, get_display_value
from .serializers_device_settings import PLCWriteRecordSerializer, DeviceSettingsBatchWriteSerializer

logger = logging.getLogger(__name__)

WRITABLE_SUFFIXES = ('_temp_setting', '_switch')
READONLY_SUFFIXES = ('_temperature', '_humidity', '_dew_point_setting', '_error', '_alert', '_fault')

_BROKER_CONFIG_WARNED = False
_LAZY_CONNECT_TRIGGERED = False


def _is_writable(param_name: str) -> bool:
    if any(param_name.endswith(s) for s in READONLY_SUFFIXES):
        return False
    return any(param_name.endswith(s) for s in WRITABLE_SUFFIXES)


def _normalize_select_values(raw_json: str) -> str:
    """规范化 select_values_json：确保返回给前端的始终是数组格式。

    H1 兼容方案：
    - 若原值已是数组 JSON → 直接返回
    - 若原值是对象 JSON（如 {"0":"关","1":"开"}）→ 转换为数组
    - 其他格式（空字符串、null、非法 JSON）→ 返回 '[]'
    """
    if not raw_json:
        return '[]'
    try:
        parsed = json.loads(raw_json)
        if isinstance(parsed, list):
            normalized = []
            for item in parsed:
                if isinstance(item, dict):
                    normalized.append(item)
                else:
                    normalized.append({"label": str(item), "value": item})
            return json.dumps(normalized, ensure_ascii=False)
        if isinstance(parsed, dict):
            arr = [{"value": k, "label": v} for k, v in parsed.items()]
            return json.dumps(arr, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass
    return '[]'


def _get_mqtt_client():
    global _LAZY_CONNECT_TRIGGERED
    from .mqtt_consumer import mqtt_consumer
    client = mqtt_consumer.client

    # v0.4.2 Bug C: backend (waitress) 进程 import 单例时不会自动 connect，
    # 只有 freeark-mqtt-consumer 进程才通过 start_mqtt_consumer 触发 loop_forever。
    # 首次调用 lazy 触发 connect_async + loop_start（异步、幂等）。
    if not _LAZY_CONNECT_TRIGGERED and not client.is_connected():
        try:
            client.connect_async(mqtt_consumer.mqtt_broker, mqtt_consumer.mqtt_port, keepalive=60)
            client.loop_start()
            _LAZY_CONNECT_TRIGGERED = True
            logger.warning('MQTT client lazy connect 触发: %s:%s',
                           mqtt_consumer.mqtt_broker, mqtt_consumer.mqtt_port)
        except Exception as e:
            logger.warning('MQTT client lazy connect 失败: %s', e, exc_info=True)

    # P2 加固：等待 MQTT client 连接就绪，最多 3s
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        try:
            if client.is_connected():
                break
        except Exception:
            pass
        time.sleep(0.1)

    if not client.is_connected():
        logger.warning('MQTT client 未处于 connected 状态，publish 可能失败')

    return client


def _check_broker_config_consistency():
    """P2 加固：启动时（首次调用时）校验 mqtt_consumer 与 plc_write_subscriber 的 broker 配置是否一致。
    仅 log warning，不阻断请求处理。
    """
    global _BROKER_CONFIG_WARNED
    if _BROKER_CONFIG_WARNED:
        return
    _BROKER_CONFIG_WARNED = True
    try:
        from .mqtt_consumer import mqtt_consumer
        backend_broker = f"{mqtt_consumer.mqtt_broker}:{mqtt_consumer.mqtt_port}"
        logger.info('P2 broker 一致性检查 — 后端 mqtt_consumer broker: %s', backend_broker)
        if '32795' in backend_broker or '31.97' in backend_broker:
            logger.warning(
                'P2 broker 配置警告：后端 mqtt_consumer 使用旧 fallback broker (%s)，'
                '应为 192.168.31.98:32788（与 PLCWriteSubscriber 一致），命令将无法路由',
                backend_broker,
            )
    except Exception as e:
        logger.warning('P2 broker 一致性检查失败: %s', e)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_settings_params(request, specific_part):
    _check_broker_config_consistency()

    configs = (
        DeviceConfig.objects
        .filter(is_active=True)
        .order_by('sub_type', 'param_name')
    )

    latest_map = {
        r.param_name: r.value
        for r in PLCLatestData.objects.filter(specific_part=specific_part)
    }

    attr_tags = [c.param_name for c in configs]

    # H2 兼容：同时尝试宽松匹配（去前缀大小写）
    attr_defs_by_tag = {}
    for d in DeviceAttrDef.objects.filter(attr_tag__in=attr_tags):
        attr_defs_by_tag.setdefault(d.attr_tag, []).append(d)

    # H3 兼容：若同一 attr_tag 有多行，需选最合适的一行
    # 当前优先取第一行（product_code 优先级由 upsert 顺序决定，暂不引入更复杂逻辑）
    attr_defs = {}
    for tag, rows in attr_defs_by_tag.items():
        attr_defs[tag] = rows[0]

    groups = {}
    for cfg in configs:
        # P5 后端过滤：不返回只读参数
        if not _is_writable(cfg.param_name):
            continue

        key = cfg.sub_type
        if key not in groups:
            groups[key] = {
                'sub_type': cfg.sub_type,
                'sub_type_display': cfg.sub_type_display,
                'params': [],
            }

        attr_def = attr_defs.get(cfg.param_name)
        raw_val = latest_map.get(cfg.param_name)

        # P3：human-readable 映射
        display_val = get_display_value(cfg.param_name, raw_val)
        value_options = get_value_options(cfg.param_name)

        # H1 兼容：规范化 select_values_json 为数组格式
        raw_select_json = attr_def.select_values_json if attr_def else ''
        normalized_select_json = _normalize_select_values(raw_select_json)

        groups[key]['params'].append({
            'param_name': cfg.param_name,
            'display_name': cfg.display_name,
            'current_value': raw_val,
            'display_value': display_val,
            'is_writable': True,
            'attr_value_type': attr_def.attr_value_type if attr_def else None,
            'num_value_json': attr_def.num_value_json if attr_def else '',
            'select_values_json': normalized_select_json,
            'value_options': value_options,
        })

    return Response({
        'specific_part': specific_part,
        'groups': list(groups.values()),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def device_settings_write(request):
    ser = DeviceSettingsBatchWriteSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=400)

    specific_part = ser.validated_data['specific_part']
    items = ser.validated_data['items']

    # 校验所有 item 的 param_name 可写性
    for item in items:
        if not _is_writable(item['param_name']):
            return Response(
                {'error': f"参数 {item['param_name']} 不在可写白名单中"},
                status=400,
            )

    try:
        owner = OwnerInfo.objects.get(specific_part=specific_part)
        plc_ip = owner.plc_ip_address
    except OwnerInfo.DoesNotExist:
        return Response({'error': f'未找到 specific_part={specific_part} 对应的设备信息'}, status=404)

    batch_request_id = str(uuid.uuid4())

    # 预取当前值快照
    param_names = [item['param_name'] for item in items]
    old_value_map = {
        r.param_name: str(r.value)
        for r in PLCLatestData.objects.filter(
            specific_part=specific_part, param_name__in=param_names
        )
    }

    records = []
    with transaction.atomic():
        for item in items:
            param_name = item['param_name']
            new_value = item['new_value']
            old_value = old_value_map.get(param_name, '')
            row_request_id = str(uuid.uuid4())
            rec = PLCWriteRecord.objects.create(
                request_id=row_request_id,
                batch_request_id=batch_request_id,
                specific_part=specific_part,
                param_name=param_name,
                old_value=old_value,
                new_value=str(new_value),
                operator=request.user.username,
                status='pending',
            )
            records.append(rec)

    payload = json.dumps({
        'request_id': batch_request_id,
        'specific_part': specific_part,
        'plc_ip': plc_ip,
        'operator': request.user.username,
        'submitted_at': timezone.now().isoformat(),
        'items': [
            {'param_name': item['param_name'], 'new_value': item['new_value']}
            for item in items
        ],
    })
    topic = f'/datacollection/plc/write/command/{specific_part}'

    try:
        client = _get_mqtt_client()
        result = client.publish(topic, payload, qos=1)
        if result.rc != 0:
            raise RuntimeError(f'paho rc={result.rc}')
    except Exception as e:
        logger.error('MQTT publish 失败: %s', e)
        PLCWriteRecord.objects.filter(batch_request_id=batch_request_id).update(
            status='failed',
            error_message='MQTT broker 不可达',
        )
        return Response({'error': '下发通道异常，请稍后重试'}, status=503)

    logger.info(
        'P4 批量下发成功: batch_request_id=%s specific_part=%s item_count=%d publish_rc=%s',
        batch_request_id, specific_part, len(items), result.rc,
    )

    return Response({
        'batch_request_id': batch_request_id,
        'item_count': len(items),
        'status': 'pending',
    }, status=202)


class WriteRecordPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_settings_records(request):
    qs = PLCWriteRecord.objects.all()

    specific_part = request.query_params.get('specific_part')
    if specific_part:
        qs = qs.filter(specific_part=specific_part)

    operator = request.query_params.get('operator')
    if operator:
        qs = qs.filter(operator=operator)

    status = request.query_params.get('status')
    if status:
        qs = qs.filter(status=status)

    start_time = request.query_params.get('start_time')
    if start_time:
        qs = qs.filter(created_at__gte=start_time)

    end_time = request.query_params.get('end_time')
    if end_time:
        qs = qs.filter(created_at__lte=end_time)

    paginator = WriteRecordPagination()
    page = paginator.paginate_queryset(qs, request)
    serializer = PLCWriteRecordSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)
