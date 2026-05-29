"""
serializers_condensation.py — CondensationWarningEvent DRF 序列化器（MOD-BE-CW-07，v0.7.0-CW）

镜像 serializers_fault.py 结构（ADR-CW-06），但字段不同：
  - 无 device_name / device_type_label（结露预警不需要设备名映射）
  - 新增快照字段：condensation_alarm_value / dew_point_temp / ntc_temp / humidity / system_switch
  - is_screen_online 不在此序列化器中声明（由视图层 _inject_screen_online 注入到 dict，避免 N+1 查询）

时区处理：first_seen_at/last_seen_at/recovered_at 均为 DateTimeField，
USE_TZ=True 时序列化为 ISO8601 含时区字符串；与故障管理序列化器行为一致。
"""

from rest_framework import serializers
from .models import CondensationWarningEvent


class CondensationWarningEventSerializer(serializers.ModelSerializer):
    """CondensationWarningEvent 只读序列化器。

    is_screen_online 由视图层 _inject_screen_online 注入到 dict 中，
    不在序列化器中声明（避免 N+1 查询，与 ADR-CW-05 一致）。
    """

    # room_id 输出为整数（FK id），与 FaultEventSerializer 的处理方式一致
    room_id = serializers.IntegerField(source='room_id_id', allow_null=True, read_only=True)

    class Meta:
        model = CondensationWarningEvent
        fields = [
            'id',
            'specific_part',
            'room_name',
            'room_id',
            'device_sn',
            'product_code',
            'warning_type',
            'warning_message',
            'condensation_alarm_value',
            'dew_point_temp',
            'ntc_temp',
            'humidity',
            'system_switch',
            'first_seen_at',
            'last_seen_at',
            'recovered_at',
            'is_active',
        ]
        read_only_fields = fields
