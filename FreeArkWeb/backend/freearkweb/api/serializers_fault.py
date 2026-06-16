"""
serializers_fault.py — FaultEvent DRF 序列化器（MOD-BE-FM-09 / MOD-BE-UX-03，v0.6.3-FM）

提供只读序列化器，供 views_fault.py 中的 fault_event_list 接口使用。
时间字段以 ISO8601 格式输出（由 Django TIME_ZONE 设置控制时区）。
null 的 recovered_at 序列化为 null（JSON），前端显示为 "-"。

v0.6.1-FM-UX 新增字段（MOD-BE-UX-03）：
  device_name      — 主路径：进程内缓存 dict 查表，O(1)，无 ORM JOIN
  device_type_label — 兜底一：PRODUCT_CODE_LABELS[product_code]

三级降级逻辑（前端负责最终渲染决策）：
  device_name 非 null   → 显示 device_name
  device_type_label 非 null → 显示 device_type_label
  均 null              → 显示 device_sn + "（未识别）"角标
"""

from rest_framework import serializers
from .models import FaultEvent
from .device_name_cache import get_device_name_by_sn          # v0.6.1-FM-UX
from .fault_consumer.constants import (
    PRODUCT_CODE_LABELS,   # v0.6.1-FM-UX
    DEVICE_NAME_OVERRIDE,  # v0.6.3-FM BUG-FM-007
)


class FaultEventSerializer(serializers.ModelSerializer):
    """FaultEvent 只读序列化器。

    所有字段均为只读（此接口不支持写入）。

    v0.6.1-FM-UX 新增字段：
      device_name      — 主路径：进程内缓存 dict 查表，O(1)，无 ORM JOIN
      device_type_label — 兜底一：PRODUCT_CODE_LABELS[product_code]

    v0.6.4-FM-ROOM 新增字段：
      room_name        — 冗余列，FaultEvent.room_name，null 可
      room_id          — FK 外键 id，FaultEvent.room_id_id，null 可
    """

    # 新增（v0.6.1-FM-UX，MOD-BE-UX-03）
    device_name = serializers.SerializerMethodField()
    device_type_label = serializers.SerializerMethodField()

    # 新增（v0.6.4-FM-ROOM，MOD-v0.6.4-08）
    room_id = serializers.IntegerField(source='room_id_id', allow_null=True, read_only=True)

    def get_device_name(self, obj):
        """主路径：device_sn（str）→ int → dict 查表 → device_name。

        v0.6.3-FM（BUG-FM-007）：在返回前检查 DEVICE_NAME_OVERRIDE。
        若 product_code 在覆盖字典中，且 device_name_cache 有值，
        则用覆盖值替代（如 130004 "新风" → "新风机"）。

        O(1) 无 IO（进程内 dict 缓存，TTL=60s 自动刷新）。
        转换失败（非数字 device_sn）返回 None，进入兜底逻辑。
        """
        try:
            sn = int(obj.device_sn)
        except (ValueError, TypeError):
            return None
        raw = get_device_name_by_sn(sn)  # None 表示 dict 未命中
        if raw is not None:
            override = DEVICE_NAME_OVERRIDE.get(str(obj.product_code))
            if override:
                return override
        return raw

    def get_device_type_label(self, obj):
        """兜底一：product_code → PRODUCT_CODE_LABELS 友好名。

        dict.get() O(1)，无 IO。
        未命中返回 None，前端展示兜底二：device_sn + "（未识别）"。
        """
        return PRODUCT_CODE_LABELS.get(str(obj.product_code))

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
            'inspection_status',  # 新增（v1.3.0-AOW）巡检处置状态，前端「智能体巡检」按钮据此显示
            'device_name',        # 新增（v0.6.1-FM-UX）主路径，可 null
            'device_type_label',  # 新增（v0.6.1-FM-UX）兜底一，可 null
            'room_name',          # 新增（v0.6.4-FM-ROOM）冗余房间名，可 null
            'room_id',            # 新增（v0.6.4-FM-ROOM）房间 FK id，可 null
        ]
        read_only_fields = fields
