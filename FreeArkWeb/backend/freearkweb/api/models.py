from django.db import models
from django.contrib.auth.models import AbstractUser
from django.db.models.signals import post_save
from django.dispatch import receiver

class CustomUser(AbstractUser):
    """自定义用户模型，扩展Django默认用户模型"""
    ROLE_CHOICES = (
        ('admin', '管理员'),
        ('user', '普通用户'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    department = models.CharField(max_length=100, blank=True, null=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # 添加related_name以避免与默认auth.User冲突
    groups = models.ManyToManyField(
        'auth.Group',
        verbose_name='groups',
        blank=True,
        help_text='The groups this user belongs to.',
        related_name='customuser_groups',
        related_query_name='user',
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        verbose_name='user permissions',
        blank=True,
        help_text='Specific permissions for this user.',
        related_name='customuser_permissions',
        related_query_name='user',
    )

    def __str__(self):
        return self.username

# 移除不再使用的模型

# 设置Django使用自定义用户模型
# 在settings.py中还需要设置AUTH_USER_MODEL = 'api.CustomUser'


class UsageQuantityDaily(models.Model):
    """每日用量数据表"""
    # 专有部分，格式为 "3-1-702"
    specific_part = models.CharField(max_length=20, verbose_name='专有部分')
    # 楼栋，格式为 "3"
    building = models.CharField(max_length=10, verbose_name='楼栋')
    # 单元，格式为 "1"
    unit = models.CharField(max_length=10, verbose_name='单元')
    # 房号，格式为 "702"
    room_number = models.CharField(max_length=10, verbose_name='房号')
    # 供能模式，可选值为 "制冷" 或 "制热"
    ENERGY_MODE_CHOICES = (
        ('制冷', '制冷'),
        ('制热', '制热'),
    )
    energy_mode = models.CharField(max_length=10, choices=ENERGY_MODE_CHOICES, verbose_name='供能模式')
    # 初期能耗，单位kWh
    initial_energy = models.IntegerField(verbose_name='初期能耗(kWh)')
    # 末期能耗，单位kWh
    final_energy = models.IntegerField(verbose_name='末期能耗(kWh)', null=True, blank=True)
    # 使用量，单位kWh
    usage_quantity = models.IntegerField(verbose_name='使用量(kWh)', null=True, blank=True)
    # 时间段，格式为 "YYYY-MM-DD"
    time_period = models.DateField(verbose_name='时间段')
    
    class Meta:
        db_table = 'usage_quantity_daily'  # 指定表名
        verbose_name = '每日用量数据'
        verbose_name_plural = '每日用量数据'
    
    def __str__(self):
        return f"{self.specific_part} - {self.time_period} - {self.energy_mode}"


class PLCData(models.Model):
    """PLC数据存储模型，用于存储从MQTT接收到的PLC数据"""
    # 专有部分，格式为 "3-1-702"
    specific_part = models.CharField(max_length=20, verbose_name='专有部分', db_index=True, default='')
        # PLC设备IP地址
    plc_ip = models.CharField(max_length=50, verbose_name='PLC IP地址', db_index=True, null=True, blank=True)
    # 楼栋，格式为 "3"
    building = models.CharField(max_length=10, verbose_name='楼栋', db_index=True, default='')
    # 单元，格式为 "1"
    unit = models.CharField(max_length=10, verbose_name='单元', db_index=True, default='')
    # 房号，格式为 "702"
    room_number = models.CharField(max_length=10, verbose_name='房号', db_index=True, default='')
    # 功能模式
    energy_mode = models.CharField(max_length=100, verbose_name='功能模式', db_index=True, default='未知')
    # 参数值（使用BigIntegerField以支持大整数）
    value = models.BigIntegerField(verbose_name='参数值', null=True, blank=True)
    # 创建时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    
    class Meta:
        db_table = 'plc_data'  # 指定表名
        verbose_name = 'PLC数据'
        verbose_name_plural = 'PLC数据'
        # 创建复合索引以提高查询性能
        indexes = [
            models.Index(fields=['specific_part', 'energy_mode', 'created_at']),
            models.Index(fields=['plc_ip', 'created_at']),
            models.Index(fields=['building', 'unit', 'room_number']),
        ]
    
    def __str__(self):
        return f"{self.specific_part} - {self.energy_mode} - {self.created_at}"
