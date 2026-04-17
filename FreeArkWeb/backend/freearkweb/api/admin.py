from django.contrib import admin
from .models import OwnerInfo


@admin.register(OwnerInfo)
class OwnerInfoAdmin(admin.ModelAdmin):
    list_display = ['specific_part', 'location_name', 'building', 'unit', 'floor', 'room_number', 'bind_status', 'ip_address', 'plc_ip_address']
    search_fields = ['specific_part', 'location_name', 'room_number', 'unique_id']
    list_filter = ['building', 'unit', 'bind_status']
    ordering = ['building', 'unit', 'room_number']
