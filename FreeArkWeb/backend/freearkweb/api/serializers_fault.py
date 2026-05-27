"""
serializers_fault.py — FaultEvent DRF 序列化器（MOD-BE-FM-09，v0.6.0-FM）

提供只读序列化器，供 views_fault.py 中的 fault_event_list 接口使用。
时间字段以 ISO8601 格式输出（由 Django TIME_ZONE 设置控制时区）。
null 的 recovered_at 序列化为 null（JSON），前端显示为 "-"。
"""

from rest_framework import serializers
from .models import FaultEvent


class FaultEventSerializer(serializers.ModelSerializer):
    """FaultEvent 只读序列化器。

    所有字段均为只读（此接口不支持写入）。
    """

    class Meta:
        model = FaultEvent
        fields = [
            'id',
            'specific_part',
            'device_sn',
            'product_code',
            'fault_code',
            'fault_type',
            'fault_message',
            'severity',
            'first_seen_at',
            'last_seen_at',
            'recovered_at',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields
