from rest_framework import serializers
from .models import PLCWriteRecord


class PLCWriteRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = PLCWriteRecord
        fields = [
            'id', 'request_id', 'specific_part', 'param_name',
            'old_value', 'new_value', 'operator', 'status',
            'error_message', 'created_at', 'acked_at',
        ]


class DeviceSettingWriteSerializer(serializers.Serializer):
    specific_part = serializers.CharField(max_length=20)
    param_name = serializers.CharField(max_length=100)
    new_value = serializers.CharField(max_length=50)
