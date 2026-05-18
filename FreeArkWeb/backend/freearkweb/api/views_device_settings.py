import json
import logging
import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import DeviceConfig, DeviceAttrDef, PLCLatestData, OwnerInfo, PLCWriteRecord
from .serializers_device_settings import PLCWriteRecordSerializer, DeviceSettingWriteSerializer

logger = logging.getLogger(__name__)

WRITABLE_SUFFIXES = ('_temp_setting', '_switch')
READONLY_SUFFIXES = ('_temperature', '_humidity', '_dew_point_setting', '_error', '_alert', '_fault')


def _is_writable(param_name: str) -> bool:
    if any(param_name.endswith(s) for s in READONLY_SUFFIXES):
        return False
    return any(param_name.endswith(s) for s in WRITABLE_SUFFIXES)


def _get_mqtt_client():
    from .mqtt_consumer import mqtt_consumer
    return mqtt_consumer.client


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def device_settings_params(request, specific_part):
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
    attr_defs = {
        d.attr_tag: d
        for d in DeviceAttrDef.objects.filter(attr_tag__in=attr_tags)
    }

    groups = {}
    for cfg in configs:
        key = cfg.sub_type
        if key not in groups:
            groups[key] = {
                'sub_type': cfg.sub_type,
                'sub_type_display': cfg.sub_type_display,
                'params': [],
            }
        attr_def = attr_defs.get(cfg.param_name)
        raw_val = latest_map.get(cfg.param_name)
        groups[key]['params'].append({
            'param_name': cfg.param_name,
            'display_name': cfg.display_name,
            'current_value': raw_val,
            'is_writable': _is_writable(cfg.param_name),
            'attr_value_type': attr_def.attr_value_type if attr_def else None,
            'num_value_json': attr_def.num_value_json if attr_def else '',
            'select_values_json': attr_def.select_values_json if attr_def else '',
        })

    return Response({
        'specific_part': specific_part,
        'groups': list(groups.values()),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def device_settings_write(request):
    ser = DeviceSettingWriteSerializer(data=request.data)
    if not ser.is_valid():
        return Response(ser.errors, status=400)

    specific_part = ser.validated_data['specific_part']
    param_name = ser.validated_data['param_name']
    new_value = ser.validated_data['new_value']

    if not _is_writable(param_name):
        return Response({'error': f'参数 {param_name} 不在可写白名单中'}, status=400)

    old_value_qs = PLCLatestData.objects.filter(
        specific_part=specific_part, param_name=param_name
    ).values_list('value', flat=True).first()
    old_value = str(old_value_qs) if old_value_qs is not None else ''

    try:
        owner = OwnerInfo.objects.get(specific_part=specific_part)
        plc_ip = owner.plc_ip_address
    except OwnerInfo.DoesNotExist:
        return Response({'error': f'未找到 specific_part={specific_part} 对应的设备信息'}, status=404)

    request_id = str(uuid.uuid4())

    with transaction.atomic():
        PLCWriteRecord.objects.create(
            request_id=request_id,
            specific_part=specific_part,
            param_name=param_name,
            old_value=old_value,
            new_value=str(new_value),
            operator=request.user.username,
            status='pending',
        )

    payload = json.dumps({
        'request_id': request_id,
        'specific_part': specific_part,
        'plc_ip': plc_ip,
        'param_name': param_name,
        'new_value': new_value,
        'operator': request.user.username,
    })
    topic = f'/datacollection/plc/write/command/{specific_part}'

    try:
        client = _get_mqtt_client()
        result = client.publish(topic, payload, qos=1)
        if result.rc != 0:
            raise RuntimeError(f'paho rc={result.rc}')
    except Exception as e:
        logger.error('MQTT publish 失败: %s', e)
        PLCWriteRecord.objects.filter(request_id=request_id).update(
            status='failed',
            error_message='MQTT broker 不可达',
        )
        return Response({'error': '下发通道异常，请稍后重试'}, status=503)

    return Response({'request_id': request_id, 'status': 'pending'}, status=202)


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
