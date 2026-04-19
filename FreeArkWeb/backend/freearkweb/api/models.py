from django.db import models
from django.utils import timezone
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
    # 专有部分，格式为 "3-1-7-702"
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
    # 创建时间，自动设置为记录创建时的时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    # 更新时间，每次更新记录时自动设置为当前时间
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'usage_quantity_daily'  # 指定表名
        verbose_name = '每日用量数据'
        verbose_name_plural = '每日用量数据'
        # 创建索引以提高查询性能
        indexes = [
            # 单列索引
            models.Index(fields=['time_period']),
            models.Index(fields=['specific_part']),
            models.Index(fields=['energy_mode']),
            models.Index(fields=['time_period', 'energy_mode']),  # 新增复合索引以优化未提供specific_part时的查询
            # 组合索引
            models.Index(fields=['time_period', 'specific_part', 'energy_mode']),
        ]
    
    def __str__(self):
        return f"{self.specific_part} - {self.time_period} - {self.energy_mode}"


class UsageQuantityMonthly(models.Model):
    """每月用量数据表"""
    # 专有部分，格式为 "3-1-7-702"
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
    # 用量月度，格式为 "YYYY-MM"
    usage_month = models.CharField(max_length=7, verbose_name='用量月度')  # YYYY-MM格式
    # 创建时间，自动设置为记录创建时的时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    # 更新时间，每次更新记录时自动设置为当前时间
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    
    class Meta:
        db_table = 'usage_quantity_monthly'  # 指定表名
        verbose_name = '每月用量数据'
        verbose_name_plural = '每月用量数据'
        # 创建索引以提高查询性能
        indexes = [
            # 保留原有索引
            models.Index(fields=['specific_part', 'usage_month']),
            models.Index(fields=['building', 'unit', 'room_number']),
            # 新增索引
            models.Index(fields=['energy_mode']),
            models.Index(fields=['updated_at']),
            models.Index(fields=['specific_part', 'energy_mode', 'usage_month']),
        ]
    
    def __str__(self):
        return f"{self.specific_part} - {self.usage_month} - {self.energy_mode}"


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
    # 更新时间
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    # 计量日期
    usage_date = models.DateField(default=timezone.now, verbose_name='计量日期')
    
    class Meta:
        db_table = 'plc_data'  # 指定表名
        verbose_name = 'PLC数据'
        verbose_name_plural = 'PLC数据'
        # 创建索引以提高查询性能
        # 唯一约束：确保每个特定部分、能源模式和计量日期组合只有一条记录
        unique_together = [['specific_part', 'energy_mode', 'usage_date']]
        indexes = [
            # 单列索引
            models.Index(fields=['usage_date']),
            models.Index(fields=['specific_part']),
            models.Index(fields=['energy_mode']),
            models.Index(fields=['updated_at']),
            # 组合索引
            models.Index(fields=['usage_date', 'specific_part', 'energy_mode']),
            models.Index(fields=['usage_date', 'specific_part', 'energy_mode', 'updated_at']),
            # 保留原有索引
            models.Index(fields=['specific_part', 'energy_mode', 'created_at']),
            models.Index(fields=['plc_ip', 'created_at']),
            models.Index(fields=['building', 'unit', 'room_number']),
        ]
    
    def __str__(self):
        return f"{self.specific_part} - {self.energy_mode} - {self.created_at}"


class PLCConnectionStatus(models.Model):
    """PLC连接状态表模型，用于记录PLC设备的连接状态信息"""
    # 专有部分，格式为 "3-1-7-702"
    specific_part = models.CharField(max_length=20, verbose_name='专有部分', unique=True, db_index=True)
    # 连接状态，可选值为 "online" 或 "offline"
    CONNECTION_STATUS_CHOICES = (
        ('online', '在线'),
        ('offline', '离线'),
    )
    connection_status = models.CharField(max_length=10, choices=CONNECTION_STATUS_CHOICES, default='offline', verbose_name='连接状态')
    # 最后一次在线时间
    last_online_time = models.DateTimeField(null=True, blank=True, verbose_name='最后一次在线时间')
    # 楼栋，格式为 "3"
    building = models.CharField(max_length=10, verbose_name='楼栋', db_index=True)
    # 单元，格式为 "1"
    unit = models.CharField(max_length=10, verbose_name='单元', db_index=True)
    # 房号，格式为 "702"
    room_number = models.CharField(max_length=10, verbose_name='房号', db_index=True)
    # 记录创建时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='记录创建时间')
    # 记录更新时间
    updated_at = models.DateTimeField(auto_now=True, verbose_name='记录更新时间')
    
    class Meta:
        db_table = 'plc_connection_status'  # 指定表名
        verbose_name = 'PLC连接状态'
        verbose_name_plural = 'PLC连接状态'
        # 创建索引以提高查询性能
        indexes = [
            # 单列索引
            models.Index(fields=['connection_status']),
            models.Index(fields=['building']),
            models.Index(fields=['unit']),
            models.Index(fields=['last_online_time']),
            models.Index(fields=['updated_at']),
            # 组合索引
            models.Index(fields=['building', 'unit']),
            models.Index(fields=['connection_status', 'building', 'unit']),
        ]
    
    def __str__(self):
        return f"{self.specific_part} - {self.connection_status}"


class PLCStatusChangeHistory(models.Model):
    """PLC状态变化历史表模型，用于记录PLC设备的状态变化事件"""
    # 专有部分，格式为 "3-1-7-702"
    specific_part = models.CharField(max_length=20, verbose_name='专有部分', db_index=True)
    # 状态变化类型，可选值为 "online" 或 "offline"
    STATUS_CHOICES = (
        ('online', '上线'),
        ('offline', '离线'),
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, verbose_name='状态变化类型')
    # 变化时间戳
    change_time = models.DateTimeField(auto_now_add=True, verbose_name='状态变化时间', db_index=True)
    # 楼栋，格式为 "3"
    building = models.CharField(max_length=10, verbose_name='楼栋', db_index=True, default='')
    # 单元，格式为 "1"
    unit = models.CharField(max_length=10, verbose_name='单元', db_index=True, default='')
    # 房号，格式为 "702"
    room_number = models.CharField(max_length=10, verbose_name='房号', db_index=True, default='')
    # 记录创建时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='记录创建时间')
    
    class Meta:
        db_table = 'plc_status_change_history'  # 指定表名
        verbose_name = 'PLC状态变化历史'
        verbose_name_plural = 'PLC状态变化历史'
        # 创建索引以提高查询性能
        indexes = [
            # 单列索引
            models.Index(fields=['specific_part']),
            models.Index(fields=['status']),
            models.Index(fields=['change_time']),
            models.Index(fields=['building']),
            models.Index(fields=['unit']),
            # 组合索引
            models.Index(fields=['specific_part', 'change_time']),
            models.Index(fields=['building', 'unit', 'change_time']),
            models.Index(fields=['status', 'change_time']),
        ]
    
    def __str__(self):
        return f"{self.specific_part} - {self.status} - {self.change_time}"


class OwnerInfo(models.Model):
    """业主信息表，持久化 all_owner.json 中的业主数据"""
    # 专有部分标识符，格式为 "楼-单-层-户"，如 "1-1-2-201"
    specific_part = models.CharField(max_length=20, verbose_name='专有部分', unique=True, db_index=True)
    # 专有部分坐落描述
    location_name = models.CharField(max_length=100, verbose_name='专有部分坐落', blank=True)
    # 楼栋，如 "1栋"
    building = models.CharField(max_length=10, verbose_name='楼栋', db_index=True)
    # 单元，如 "1单元"
    unit = models.CharField(max_length=10, verbose_name='单元', db_index=True)
    # 楼层，如 "2楼"
    floor = models.CharField(max_length=10, verbose_name='楼层', blank=True)
    # 户号，如 "201"
    room_number = models.CharField(max_length=10, verbose_name='户号')
    # 绑定状态，如 "已绑定" / "未绑定"
    bind_status = models.CharField(max_length=20, verbose_name='绑定状态', blank=True, db_index=True)
    # 设备 IP 地址
    ip_address = models.CharField(max_length=50, verbose_name='IP地址', blank=True)
    # 唯一标识符（screenMAC）
    unique_id = models.CharField(max_length=50, verbose_name='唯一标识符', blank=True, db_index=True)
    # PLC 设备 IP 地址
    plc_ip_address = models.CharField(max_length=50, verbose_name='PLC IP地址', blank=True)
    # 记录创建时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='记录创建时间')
    # 记录更新时间
    updated_at = models.DateTimeField(auto_now=True, verbose_name='记录更新时间')

    class Meta:
        db_table = 'owner_info'
        verbose_name = '业主信息'
        verbose_name_plural = '业主信息'
        indexes = [
            models.Index(fields=['building'], name='owner_info_building_idx'),
            models.Index(fields=['unit'], name='owner_info_unit_idx'),
            models.Index(fields=['bind_status'], name='owner_info_bind_status_idx'),
            models.Index(fields=['building', 'unit'], name='owner_info_building_unit_idx'),
            models.Index(fields=['building', 'unit', 'bind_status'], name='owner_info_bldg_unit_bind_idx'),
        ]

    def __str__(self):
        return f"{self.specific_part} - {self.location_name}"


class PLCLatestData(models.Model):
    """PLC最新参数数据表，每个设备每个参数只保留最新一条记录（非时序）"""
    # 专有部分，格式为 "3-1-7-702"
    specific_part = models.CharField(max_length=20, verbose_name='专有部分', db_index=True)
    # 参数名称，如 "living_room_temperature"
    param_name = models.CharField(max_length=100, verbose_name='参数名称')
    # 参数值（BigIntegerField 可容纳整数/浮点转整数/字节表示的整数）
    value = models.BigIntegerField(verbose_name='参数值', null=True, blank=True)
    # 最新采集时间戳，来自消息的 timestamp 字段
    collected_at = models.DateTimeField(verbose_name='采集时间', null=True, blank=True)
    # PLC 设备 IP 地址
    plc_ip = models.CharField(max_length=50, verbose_name='PLC IP地址', blank=True, default='')
    # 楼栋
    building = models.CharField(max_length=10, verbose_name='楼栋', blank=True, default='')
    # 单元
    unit = models.CharField(max_length=10, verbose_name='单元', blank=True, default='')
    # 房号
    room_number = models.CharField(max_length=10, verbose_name='房号', blank=True, default='')
    # 记录更新时间（由 ORM auto_now 维护，反映最后一次 upsert 时间）
    updated_at = models.DateTimeField(auto_now=True, verbose_name='记录更新时间')

    class Meta:
        db_table = 'plc_latest_data'
        verbose_name = 'PLC最新参数数据'
        verbose_name_plural = 'PLC最新参数数据'
        # 唯一约束：每个设备每个参数只有一条记录
        unique_together = [['specific_part', 'param_name']]
        indexes = [
            models.Index(fields=['specific_part']),
            models.Index(fields=['param_name']),
            models.Index(fields=['specific_part', 'param_name']),
            models.Index(fields=['collected_at']),
        ]

    def __str__(self):
        return f"{self.specific_part} - {self.param_name} = {self.value}"


class DeviceConfig(models.Model):
    """非专有部分设备配置表，定义设备分组和子类型元数据"""
    # 设备唯一标识，对应 PLCLatestData.specific_part 中存储的自定义 device_id
    device_id = models.CharField(max_length=100, unique=True, verbose_name='设备标识')
    # 卡片显示名称，如"书房-温控面板"
    display_name = models.CharField(max_length=200, verbose_name='显示名称')
    # 系统分组，如 "hvac"
    group = models.CharField(max_length=50, verbose_name='设备分组', db_index=True)
    # 设备子类型，如 "main_thermostat"、"room_panel"
    sub_type = models.CharField(max_length=50, verbose_name='设备子类型', db_index=True)
    # 分组中文显示名称，如"暖通"
    group_display = models.CharField(max_length=100, verbose_name='分组显示名称')
    # 子类型中文显示名称，如"主温控器"
    sub_type_display = models.CharField(max_length=100, verbose_name='子类型显示名称')
    # 是否激活（未激活的设备不出现在卡片面板）
    is_active = models.BooleanField(default=True, verbose_name='是否激活', db_index=True)
    # 记录创建时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'device_config'
        verbose_name = '设备配置'
        verbose_name_plural = '设备配置'
        ordering = ['group', 'sub_type', 'display_name']

    def __str__(self):
        return f"{self.display_name} ({self.device_id})"


class DeviceParamHistory(models.Model):
    """非专有部分设备参数历史记录表（追加写入，时序数据）"""
    # 设备标识，对应 DeviceConfig.device_id
    device_id = models.CharField(max_length=100, verbose_name='设备标识', db_index=True)
    # 参数名称
    param_name = models.CharField(max_length=100, verbose_name='参数名称')
    # 参数值（TextField 兼容整数和字符串，如 "正常"、"关闭"、"26.0"）
    value = models.TextField(null=True, blank=True, verbose_name='参数值')
    # 采集时间戳（来自 MQTT 消息）
    collected_at = models.DateTimeField(verbose_name='采集时间', db_index=True)
    # 记录写入时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='记录创建时间')

    class Meta:
        db_table = 'device_param_history'
        verbose_name = '设备参数历史'
        verbose_name_plural = '设备参数历史'
        indexes = [
            models.Index(fields=['device_id', 'collected_at'], name='dev_hist_did_cat_idx'),
            models.Index(fields=['device_id', 'param_name', 'collected_at'], name='dev_hist_did_pn_cat_idx'),
        ]

    def __str__(self):
        return f"{self.device_id} - {self.param_name} = {self.value} @ {self.collected_at}"
