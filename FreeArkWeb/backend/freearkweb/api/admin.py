from django.contrib import admin
from .models import OwnerInfo, WorkOrder


@admin.register(OwnerInfo)
class OwnerInfoAdmin(admin.ModelAdmin):
    list_display = ['specific_part', 'location_name', 'building', 'unit', 'floor', 'room_number', 'ip_address', 'plc_ip_address']
    search_fields = ['specific_part', 'location_name', 'room_number', 'unique_id']
    list_filter = ['building', 'unit']
    ordering = ['building', 'unit', 'room_number']


@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    """巡检工单后台（v1.1.0-AIA，方案 B）—— 本期人工处置入口（仅落库 + Admin）。"""
    list_display = ['ticket_id', 'status', 'severity', 'source_event_type',
                    'affected_device', 'created_at', 'resolved_at', 'resolved_by']
    list_filter = ['status', 'severity', 'source_event_type']
    search_fields = ['ticket_id', 'affected_device', 'symptom', 'source_event_id']
    ordering = ['-created_at']
    readonly_fields = ['ticket_id', 'severity', 'source_event_type', 'source_event_id',
                       'affected_device', 'symptom', 'diagnosis', 'recommended_action',
                       'created_at', 'updated_at']
    fieldsets = [
        ('工单', {'fields': ['ticket_id', 'status', 'severity']}),
        ('来源事件', {'fields': ['source_event_type', 'source_event_id', 'affected_device']}),
        ('诊断', {'fields': ['symptom', 'diagnosis', 'recommended_action']}),
        ('处置', {'fields': ['resolved_at', 'resolved_by']}),
        ('时间', {'fields': ['created_at', 'updated_at']}),
    ]
