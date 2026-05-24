from rest_framework import serializers
from .models import PLCWriteRecord


class PLCWriteRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PLCWriteRecord
        fields = [
            'id', 'request_id', 'batch_request_id', 'specific_part', 'param_name',
            'old_value', 'new_value', 'operator', 'status',
            'error_message', 'created_at', 'acked_at',
        ]


class WriteItemSerializer(serializers.Serializer):
    param_name = serializers.CharField(max_length=100)
    new_value = serializers.CharField(max_length=50)


class DeviceSettingsBatchWriteSerializer(serializers.Serializer):
    specific_part = serializers.CharField(max_length=20)
    items = WriteItemSerializer(many=True, min_length=1)
    # CONFIRM-7 (lobster-agent-api-channel): 允许 openclaw-agent 覆盖 operator 字段
    # 格式要求: "openclaw-agent::<chatuser>"，仅当认证用户为 openclaw-agent 时视图层才采用此值
    operator_override = serializers.CharField(max_length=150, required=False, allow_blank=True, default='')
