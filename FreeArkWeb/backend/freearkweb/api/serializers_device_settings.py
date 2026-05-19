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
