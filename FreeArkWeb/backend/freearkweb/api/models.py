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
    # 来源：mqtt=MQTT实时推送，monitor=超时巡检判定
    SOURCE_CHOICES = (
        ('mqtt', 'MQTT实时'),
        ('monitor', '超时巡检'),
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='mqtt', verbose_name='来源')
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
    """设备参数分组配置表，定义每个 param_name 属于哪个 group/sub_type"""
    # PLC 参数名，与 PLCLatestData.param_name 对应；同一参数可出现在多个 sub_type
    param_name = models.CharField(max_length=100, verbose_name='参数名')
    # 参数在 sub_type 内的显示名，如"客厅温度"（可选，用于前端展示）
    display_name = models.CharField(max_length=200, verbose_name='显示名称')
    # 系统分组，如 "hvac"
    group = models.CharField(max_length=50, verbose_name='设备分组', db_index=True)
    # 设备子类型，如 "main_thermostat"、"room_panel"
    sub_type = models.CharField(max_length=50, verbose_name='设备子类型', db_index=True)
    # 分组中文显示名称，如"暖通"
    group_display = models.CharField(max_length=100, verbose_name='分组显示名称')
    # 子类型中文显示名称，如"主温控器"
    sub_type_display = models.CharField(max_length=100, verbose_name='子类型显示名称')
    # 是否激活（未激活的参数不出现在卡片面板）
    is_active = models.BooleanField(default=True, verbose_name='是否激活', db_index=True)
    # 记录创建时间
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')

    class Meta:
        db_table = 'device_config'
        verbose_name = '设备配置'
        verbose_name_plural = '设备配置'
        ordering = ['group', 'sub_type', 'param_name']
        unique_together = [['param_name', 'sub_type']]

    def __str__(self):
        return f"{self.sub_type_display} - {self.param_name}"


class DeviceParamHistory(models.Model):
    """设备参数历史记录表（追加写入，时序数据）"""
    # 专有部分标识，格式如 9-1-31-3104，来自前端上下文
    # 注：不再单独建 db_index——该单列索引是 dev_hist_sp_cat_idx(specific_part, collected_at)
    # 与 dev_hist_sp_pn_cat_idx(specific_part, param_name, collected_at) 的最左前缀，冗余。
    # 删除以节省索引空间（见 migration 0031，2026-05-31 索引虚胖治理）。
    specific_part = models.CharField(max_length=50, verbose_name='专有部分')
    # 参数名称，与 PLCLatestData.param_name 对应
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
            models.Index(fields=['specific_part', 'collected_at'], name='dev_hist_sp_cat_idx'),
            models.Index(fields=['specific_part', 'param_name', 'collected_at'], name='dev_hist_sp_pn_cat_idx'),
        ]

    def __str__(self):
        return f"{self.specific_part} - {self.param_name} = {self.value} @ {self.collected_at}"


class ScreenConnectivityStatus(models.Model):
    """大屏连通性状态表（MOD-BE-02）
    每户一条记录（upsert），由心跳 MQTT consumer 写入。
    大屏每次上报心跳 → upsert last_seen_at。
    在线判断：last_seen_at 距今 ≤ 15 分钟。
    specific_part 格式为四段，如 "3-1-7-702"（与 OwnerInfo.specific_part 一致）。
    """
    # 四段专有部分标识，如 "3-1-7-702"；唯一约束确保 upsert 幂等
    specific_part = models.CharField(max_length=20, unique=True, db_index=True, verbose_name='专有部分')
    # 大屏最近一次心跳时间（由 screen_heartbeat_consumer 写入）
    last_seen_at = models.DateTimeField(verbose_name='最近心跳时间')
    # 记录更新时间，auto_now 由 ORM 维护
    updated_at = models.DateTimeField(auto_now=True, verbose_name='记录更新时间')

    class Meta:
        db_table = 'screen_connectivity_status'
        verbose_name = '大屏连通性状态'
        verbose_name_plural = '大屏连通性状态'

    def __str__(self):
        return f"{self.specific_part} - last_seen_at={self.last_seen_at}"


# ---------------------------------------------------------------------------
# 设备树同步 — 来自屏侧 floor-room-device/list 接口
# 表关系：OwnerInfo 1:N DeviceFloor 1:N DeviceRoom 1:N DeviceNode
#         DeviceNode N:M DeviceAttrDef  (经由 DeviceAttrBinding)
# ---------------------------------------------------------------------------


class DeviceFloor(models.Model):
    """同步自屏接口的楼层节点，挂在 OwnerInfo 之下。"""
    owner = models.ForeignKey(
        OwnerInfo, on_delete=models.CASCADE, related_name='floors', verbose_name='所属业主'
    )
    floor_no = models.IntegerField(verbose_name='楼层号')
    floor_name = models.CharField(max_length=20, verbose_name='楼层名')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='最后同步时间')

    class Meta:
        db_table = 'device_floor'
        verbose_name = '设备楼层'
        verbose_name_plural = '设备楼层'
        constraints = [
            models.UniqueConstraint(fields=['owner', 'floor_no'], name='uniq_floor_owner_no'),
        ]
        indexes = [
            models.Index(fields=['owner']),
        ]

    def __str__(self):
        return f"{self.owner.specific_part} / floor={self.floor_no}"


class DeviceRoom(models.Model):
    """同步自屏接口的房间节点，挂在 DeviceFloor 之下。"""
    floor = models.ForeignKey(
        DeviceFloor, on_delete=models.CASCADE, related_name='rooms', verbose_name='所属楼层'
    )
    room_name = models.CharField(max_length=50, verbose_name='房间名')
    ori_room_name = models.CharField(max_length=50, verbose_name='原始房间名')
    room_type = models.IntegerField(verbose_name='房间类型')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='最后同步时间')

    class Meta:
        db_table = 'device_room'
        verbose_name = '设备房间'
        verbose_name_plural = '设备房间'
        constraints = [
            models.UniqueConstraint(fields=['floor', 'ori_room_name'], name='uniq_room_floor_oriname'),
        ]
        indexes = [
            models.Index(fields=['floor']),
            models.Index(fields=['room_type']),
        ]

    def __str__(self):
        return f"{self.floor} / {self.room_name}"


class DeviceNode(models.Model):
    """同步自屏接口的设备节点，挂在 DeviceRoom 之下。"""
    room = models.ForeignKey(
        DeviceRoom, on_delete=models.CASCADE, related_name='devices', verbose_name='所属房间'
    )
    device_sn = models.IntegerField(verbose_name='设备SN')
    device_name = models.CharField(max_length=50, verbose_name='设备名')
    system_flag = models.SmallIntegerField(verbose_name='系统标识')  # 1=子设备 2=主机
    related_device_sn = models.IntegerField(null=True, blank=True, verbose_name='所属主机SN')
    product_code = models.CharField(max_length=20, verbose_name='产品编码')
    category_code = models.IntegerField(verbose_name='品类编码')
    protocol = models.SmallIntegerField(null=True, blank=True, verbose_name='通信协议')
    address_code = models.SmallIntegerField(null=True, blank=True, verbose_name='总线地址')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='最后同步时间')

    attrs = models.ManyToManyField(
        'DeviceAttrDef',
        through='DeviceAttrBinding',
        related_name='devices',
        verbose_name='设备属性',
    )

    class Meta:
        db_table = 'device_node'
        verbose_name = '设备节点'
        verbose_name_plural = '设备节点'
        constraints = [
            models.UniqueConstraint(fields=['room', 'device_sn'], name='uniq_node_room_sn'),
        ]
        indexes = [
            models.Index(fields=['room']),
            models.Index(fields=['device_sn']),
            models.Index(fields=['product_code']),
            models.Index(fields=['related_device_sn']),
        ]

    def __str__(self):
        return f"{self.room} / sn={self.device_sn} {self.device_name}"


class DeviceAttrDef(models.Model):
    """全局设备属性定义池。按 (product_code, attr_tag) 唯一去重。"""
    product_code = models.CharField(max_length=20, verbose_name='产品编码')
    attr_tag = models.CharField(max_length=50, verbose_name='属性标签')
    attr_value_type = models.SmallIntegerField(verbose_name='取值类型')  # 1=枚举 2=数值
    attr_constraint = models.SmallIntegerField(verbose_name='约束')
    # 原文 JSON 存为字符串，跨数据库（SQLite / MySQL）兼容
    select_values_json = models.TextField(blank=True, default='', verbose_name='枚举值JSON')
    num_value_json = models.TextField(blank=True, default='', verbose_name='数值范围JSON')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='最后同步时间')

    class Meta:
        db_table = 'device_attr_def'
        verbose_name = '设备属性定义'
        verbose_name_plural = '设备属性定义'
        constraints = [
            models.UniqueConstraint(fields=['product_code', 'attr_tag'], name='uniq_attr_def_prod_tag'),
        ]
        indexes = [
            models.Index(fields=['product_code']),
            models.Index(fields=['attr_tag']),
        ]

    def __str__(self):
        return f"{self.product_code}.{self.attr_tag}"


class DeviceAttrBinding(models.Model):
    """设备 ↔ 属性定义 的 M:N 绑定表，用于完整还原屏接口的 attrs 列表。"""
    device = models.ForeignKey(
        DeviceNode, on_delete=models.CASCADE, related_name='attr_bindings', verbose_name='设备'
    )
    attr_def = models.ForeignKey(
        DeviceAttrDef, on_delete=models.CASCADE, related_name='bindings', verbose_name='属性定义'
    )

    class Meta:
        db_table = 'device_attr_binding'
        verbose_name = '设备属性绑定'
        verbose_name_plural = '设备属性绑定'
        constraints = [
            models.UniqueConstraint(fields=['device', 'attr_def'], name='uniq_binding_dev_def'),
        ]
        indexes = [
            models.Index(fields=['device']),
            models.Index(fields=['attr_def']),
        ]

    def __str__(self):
        return f"{self.device_id} <-> {self.attr_def_id}"


# ---------------------------------------------------------------------------
# 记忆隔离模型（freeark_lobster_memory_isolation，ADR-013 方案 13-B）
# ---------------------------------------------------------------------------


class ChatSession(models.Model):
    """per-user 对话会话，对应一次 WS 连接生命周期。"""
    user = models.ForeignKey(
        'api.CustomUser',
        on_delete=models.CASCADE,
        related_name='chat_sessions',
    )
    session_key = models.CharField(max_length=36)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'api_chat_session'
        indexes = [
            models.Index(fields=['user', 'started_at'], name='chat_sess_user_start_idx'),
        ]

    def __str__(self):
        return f"ChatSession user={self.user_id} key={self.session_key[:8]}..."


class ChatMessage(models.Model):
    """per-session 消息记录；只存 content，不存 reasoning。"""
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    role = models.CharField(max_length=20)   # 'user' | 'assistant'
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'api_chat_message'
        indexes = [
            models.Index(fields=['session', 'created_at'], name='chat_msg_sess_time_idx'),
        ]

    def __str__(self):
        return f"ChatMessage session={self.session_id} role={self.role}"


class PLCWriteRecord(models.Model):
    STATUS_CHOICES = (
        ('pending', '待回执'),
        ('success', '写入成功'),
        ('failed', '写入失败'),
        ('timeout', '超时未回执'),
    )
    request_id = models.CharField(max_length=64, unique=True)
    batch_request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True, verbose_name='批量请求ID')
    specific_part = models.CharField(max_length=20, db_index=True)
    param_name = models.CharField(max_length=100)
    old_value = models.CharField(max_length=50, default='')
    new_value = models.CharField(max_length=50)
    operator = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    acked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'plc_write_record'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['specific_part', 'created_at'], name='plcwr_sp_cat_idx'),
            models.Index(fields=['status', 'created_at'], name='plcwr_status_cat_idx'),
            models.Index(fields=['operator'], name='plcwr_operator_idx'),
        ]

    def __str__(self):
        return f"{self.request_id} {self.specific_part}/{self.param_name} {self.status}"


# ---------------------------------------------------------------------------
# 故障事件模型（v0.6.0-FM，ADR-FM-04）
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 自治巡检 Agent（v1.1.0-AIA，方案 B）—— 巡检处置状态机
# 共享于 FaultEvent / CondensationWarningEvent 两张事件表：
#   PENDING(待巡检) → IN_PROGRESS(巡检处理中) → DONE(已处置) / SKIPPED(已跳过)
# freeark-inspection-agent 据此 DB 轮询取用、并在重启时把 IN_PROGRESS 重置为
# PENDING，保证零漏单/零重单（OD-02 事件接入、OD-03 状态持久化）。
# ---------------------------------------------------------------------------
INSPECTION_STATUS_CHOICES = [
    ('PENDING', '待巡检'),
    ('IN_PROGRESS', '巡检处理中'),
    ('DONE', '已处置'),
    ('SKIPPED', '已跳过'),
]


class FaultEvent(models.Model):
    """故障事件表。

    由 freeark-fault-consumer 服务写入，记录 MQTT 上报的故障事件生命周期。
    写入模式（ADR-FM-03）：
      - 首次出现：INSERT(is_active=True)
      - 故障持续：无 DB 操作（仅更新进程内内存）
      - 故障恢复：UPDATE(is_active=False, recovered_at=now())

    严禁：查询 device_param_history（3766 万行）；此表与 plc_latest_data 语义独立。
    """
    specific_part = models.CharField(max_length=64, verbose_name='房号')
    device_sn = models.CharField(max_length=64, verbose_name='设备序列号')
    product_code = models.CharField(max_length=32, verbose_name='产品编码')
    fault_code = models.CharField(max_length=64, verbose_name='故障码')
    fault_type = models.CharField(
        max_length=16,
        choices=[
            ('comm',        '通信故障'),
            ('sensor',      '传感器故障'),
            ('fresh_air',   '新风故障'),
            ('other_error', '其他故障'),
        ],
        verbose_name='故障大类',
    )
    fault_message = models.CharField(max_length=255, verbose_name='故障描述')
    severity = models.CharField(
        max_length=8,
        choices=[('error', 'Error'), ('warning', 'Warning')],
        verbose_name='严重级别',
    )
    first_seen_at = models.DateTimeField(verbose_name='首次出现时间')
    last_seen_at = models.DateTimeField(verbose_name='最后活跃时间')
    recovered_at = models.DateTimeField(null=True, blank=True, verbose_name='恢复时间')
    is_active = models.BooleanField(default=True, verbose_name='是否活跃')
    # v0.6.4-FM-ROOM: 冗余房间字段，fault_consumer T1 写入时填充，历史数据由 migration 0028 回填
    room_name = models.CharField(
        max_length=50, null=True, blank=True,
        verbose_name='房间名称',
        help_text='冗余字段，存储 device_room.ori_room_name，fault_consumer T1 写入时填充',
    )
    room_id = models.ForeignKey(
        'DeviceRoom',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='fault_events',
        verbose_name='所属房间',
        db_column='room_id',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    # v1.1.0-AIA（方案 B）：自治巡检处置状态，由 freeark-inspection-agent 维护；
    # 现有 fault_consumer 不读写这两个字段，新增对其零影响（migration 0033，非破坏）。
    inspection_status = models.CharField(
        max_length=16, choices=INSPECTION_STATUS_CHOICES, default='PENDING',
        db_index=True, verbose_name='巡检处置状态',
    )
    inspection_started_at = models.DateTimeField(
        null=True, blank=True, verbose_name='巡检开始时间',
    )

    class Meta:
        db_table = 'fault_event'
        verbose_name = '故障事件'
        verbose_name_plural = '故障事件'
        constraints = [
            models.UniqueConstraint(
                fields=['specific_part', 'device_sn', 'fault_code', 'first_seen_at'],
                name='uq_fault_event_key_time',
            )
        ]
        indexes = [
            models.Index(
                fields=['specific_part', 'is_active'],
                name='idx_fault_sp_active',
            ),
            models.Index(
                fields=['first_seen_at', 'is_active'],
                name='idx_fault_time_active',
            ),
        ]

    def __str__(self):
        status = 'ACTIVE' if self.is_active else 'RECOVERED'
        return f"{self.specific_part} / {self.fault_code} [{status}] @ {self.first_seen_at}"


class CondensationWarningEvent(models.Model):
    """结露预警事件表（v0.7.0-CW，MOD-BE-CW-05）。

    由 freeark-condensation-consumer 服务写入，记录结露报警事件生命周期。
    写入模式与 FaultEvent 相同（T1/T2/T3 状态机）。

    system_switch 字段来源（ADR-CW-01，ARCH-PENDING-01 选定方案 A，RISK-CW-ARCH-01 已闭环）：
      优先取触发报文同 deviceSn 的 system_switch attrTag（MQTT 直取，已是 on/off 字符串）；
      不存在时查 PLCLatestData(specific_part, param_name='system_switch')（整数 0→off/非0→on）；
      均无则写 'unknown'。
    """
    specific_part  = models.CharField(max_length=64, verbose_name='房号', db_index=True)
    device_sn      = models.CharField(max_length=64, verbose_name='设备序列号')
    product_code   = models.CharField(max_length=32, verbose_name='产品编码')
    room_name      = models.CharField(max_length=50, null=True, blank=True, verbose_name='房间名')
    room_id        = models.ForeignKey(
        'DeviceRoom',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        db_column='room_id',
        related_name='condensation_warning_events',
        verbose_name='房间外键',
    )
    warning_type    = models.CharField(max_length=32, default='结露预警', verbose_name='预警类型')
    warning_message = models.CharField(max_length=255, default='结露报警', verbose_name='预警内容')
    condensation_alarm_value = models.CharField(
        max_length=16, null=True, blank=True, verbose_name='触发时 condensation_alarm 原始值'
    )
    dew_point_temp = models.CharField(max_length=16, null=True, blank=True, verbose_name='露点温度快照')
    ntc_temp       = models.CharField(max_length=16, null=True, blank=True, verbose_name='NTC温度快照')
    humidity       = models.CharField(max_length=16, null=True, blank=True, verbose_name='湿度快照')
    system_switch  = models.CharField(
        max_length=8, null=True, blank=True,
        verbose_name='系统开关状态快照（on/off/unknown）'
    )
    first_seen_at  = models.DateTimeField(verbose_name='预警首次出现时间', db_index=True)
    last_seen_at   = models.DateTimeField(verbose_name='最近活跃时间（进程内维护）')
    recovered_at   = models.DateTimeField(null=True, blank=True, verbose_name='恢复时间')
    is_active      = models.BooleanField(default=True, verbose_name='是否活跃', db_index=True)
    created_at     = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at     = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    # v1.1.0-AIA（方案 B）：自治巡检处置状态，由 freeark-inspection-agent 维护；
    # 现有 condensation_consumer 不读写这两个字段，新增对其零影响（migration 0033，非破坏）。
    inspection_status = models.CharField(
        max_length=16, choices=INSPECTION_STATUS_CHOICES, default='PENDING',
        db_index=True, verbose_name='巡检处置状态',
    )
    inspection_started_at = models.DateTimeField(
        null=True, blank=True, verbose_name='巡检开始时间',
    )

    class Meta:
        db_table = 'condensation_warning_event'
        verbose_name = '结露预警事件'
        verbose_name_plural = '结露预警事件'
        constraints = [
            models.UniqueConstraint(
                fields=['specific_part', 'device_sn', 'first_seen_at'],
                name='uniq_cw_sp_sn_first_seen',
            ),
        ]
        indexes = [
            models.Index(fields=['specific_part', 'is_active'], name='idx_cw_sp_active'),
            models.Index(fields=['first_seen_at', 'is_active'], name='idx_cw_time_active'),
        ]

    def __str__(self):
        return f"{self.specific_part} device={self.device_sn} active={self.is_active}"


# ---------------------------------------------------------------------------
# 会话滑动窗口超时（v0.9.0, REQ-AUTH-001, ADR-v090-002）
# ---------------------------------------------------------------------------


class TokenActivity(models.Model):
    """记录 DRF Token 的最后有效活动时间，用于滑动窗口超时判断。

    表名：api_token_activity
    与 authtoken_token 为 OneToOne 关系（token_id 作为 PK），
    Token 删除时级联删除（on_delete=CASCADE）。

    写入策略（满足 REQ-NFR-AUTH-001）：
      - 登录/注册时：views.py 强制 update_or_create（绕过节流）
      - 认证时：authentication.py 节流写入（ACTIVITY_THROTTLE_SECONDS 内最多 1 次）
    """
    token = models.OneToOneField(
        'authtoken.Token',
        on_delete=models.CASCADE,
        related_name='activity',
        primary_key=True,
        verbose_name='关联 Token',
    )
    last_active_at = models.DateTimeField(
        verbose_name='最后活动时间',
        db_index=True,
    )
    # "7天内保持登录"：登录时按勾选状态写入，决定滑动窗口超时阈值
    #   False → SESSION_INACTIVITY_TIMEOUT（默认 30 分钟）
    #   True  → SESSION_EXTENDED_TIMEOUT（默认 7 天）
    extended_session = models.BooleanField(
        default=False,
        verbose_name='延长会话（7天保持登录）',
    )

    class Meta:
        db_table = 'api_token_activity'
        verbose_name = 'Token 活动记录'
        verbose_name_plural = 'Token 活动记录'

    def __str__(self):
        return f"TokenActivity(token={self.token_id[:8]}..., last_active={self.last_active_at})"


# ---------------------------------------------------------------------------
# 自治巡检工单（v1.1.0-AIA，方案 B，ARCH §7）
# ---------------------------------------------------------------------------


class WorkOrder(models.Model):
    """巡检工单表（freeark-inspection-agent 的人工处置出口）。

    创建时机（决策循环 ARCH §5）：
      - 预警判定"不可自动处置" → 建单待人工；
      - LLM 生成写提案但被 WriteAuthPolicy 拦截（策略 B 下全部拦截）→ 建单，
        recommended_action 记录被拦截的写提案；
      - 决策超时/步数耗尽/委托异常等兜底路径 → 建单，不丢单。
    本期仅落库 + Django Admin 查看（用户拍板：不做前端 UI、不做通知，见 requirements_spec
    REQ-FUNC-009/010）。

    防重复建单：同一来源事件在 OPEN/IN_PROGRESS 下只允许一条活跃工单
    （uniq_active_workorder_per_event 条件唯一约束兜底 + 代码层先查后建）。
    """
    SOURCE_EVENT_TYPES = [
        ('fault_event', '故障事件'),
        ('condensation_warning_event', '结露预警事件'),
    ]
    STATUS_CHOICES = [
        ('OPEN', '待处理'),
        ('IN_PROGRESS', '处理中'),
        ('RESOLVED', '已解决'),
        ('CANCELLED', '已取消'),
    ]

    ticket_id = models.CharField(
        max_length=32, unique=True, verbose_name='工单编号',
        help_text='人可读编号，格式 WO-YYYYMMDD-NNNNNN',
    )
    severity = models.CharField(max_length=16, verbose_name='严重级别')
    source_event_type = models.CharField(
        max_length=32, choices=SOURCE_EVENT_TYPES, verbose_name='来源事件类型',
    )
    source_event_id = models.BigIntegerField(db_index=True, verbose_name='来源事件ID')
    affected_device = models.CharField(
        max_length=100, verbose_name='受影响设备',
        help_text='格式 "{device_sn} / {specific_part}"',
    )
    symptom = models.TextField(verbose_name='症状', help_text='来自事件 fault_message / warning_message')
    diagnosis = models.TextField(blank=True, verbose_name='诊断', help_text='来自 delegate_knowledge 分析摘要')
    recommended_action = models.TextField(
        blank=True, verbose_name='建议处置', help_text='来自 LLM 结论或被拦截的写提案',
    )
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default='OPEN',
        db_index=True, verbose_name='工单状态',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='解决时间')
    resolved_by = models.CharField(max_length=100, blank=True, verbose_name='解决人')

    class Meta:
        db_table = 'inspection_work_order'
        verbose_name = '巡检工单'
        verbose_name_plural = '巡检工单'
        constraints = [
            models.UniqueConstraint(
                fields=['source_event_type', 'source_event_id'],
                condition=models.Q(status__in=['OPEN', 'IN_PROGRESS']),
                name='uniq_active_workorder_per_event',
            ),
        ]
        indexes = [
            models.Index(fields=['status', 'created_at'], name='wo_status_time_idx'),
            models.Index(fields=['source_event_type', 'source_event_id'], name='wo_source_idx'),
        ]

    def __str__(self):
        return f"{self.ticket_id} [{self.status}] {self.affected_device}"


# ---------------------------------------------------------------------------
# 巡检智能体决策日志（v1.3.0-AOW，REQ-FUNC-WL-001）
# ---------------------------------------------------------------------------


class InspectionLog(models.Model):
    """巡检智能体决策步骤日志（freeark-inspection-agent 决策过程可追溯）。

    现有 inspection_agent/audit.py 仅写 journald（网页不可查）；本表为**新增双写**目标，
    记录每次 process_event 的关键决策步骤（开始/委托/写提案被拦截/建单/兜底/完成），供
    「巡检智能体工作日志」页面查询。DB 写入失败不阻断主决策流程（REQ-NFR-006）。
    step_detail 经 audit._scrub() 脱敏，绝不存凭证（REQ-NFR-009）。
    """
    SOURCE_EVENT_TYPES = [
        ('fault_event', '故障事件'),
        ('condensation_warning_event', '结露预警事件'),
    ]
    STEP_CHOICES = [
        ('PROCESS_STARTED', '开始处理'),
        ('EVENT_SKIPPED', '事件已恢复跳过'),
        ('DELEGATION_CALLED', '子专家委托'),
        ('DELEGATION_ERROR', '委托异常'),
        ('WRITE_PROPOSAL', 'LLM写提案'),
        ('WRITE_BLOCKED', '写提案被拦截'),
        ('WRITE_EXECUTED', '写操作执行'),
        ('WORKORDER_CREATED', '工单创建'),
        ('WORKORDER_EXISTED', '工单已存在'),
        ('DECISION_TIMEOUT', '决策超时兜底'),
        ('DECISION_ERROR', '决策异常兜底'),
        ('PROCESS_COMPLETED', '处置完成'),
    ]
    RESULT_CHOICES = [
        ('INFO', '信息'),
        ('SUCCESS', '成功'),
        ('BLOCKED', '已拦截'),
        ('ERROR', '错误'),
        ('SKIPPED', '已跳过'),
    ]

    source_event_type = models.CharField(
        max_length=32, choices=SOURCE_EVENT_TYPES, verbose_name='来源事件类型')
    source_event_id = models.BigIntegerField(db_index=True, verbose_name='来源事件ID')
    specific_part = models.CharField(max_length=64, db_index=True, verbose_name='房号')
    event_type_display = models.CharField(max_length=32, blank=True, verbose_name='事件类型(人读)')
    step = models.CharField(max_length=32, choices=STEP_CHOICES, verbose_name='决策步骤')
    step_detail = models.JSONField(default=dict, blank=True, verbose_name='步骤详情')
    result = models.CharField(max_length=16, default='INFO', verbose_name='结果')
    work_order_ticket = models.CharField(max_length=32, blank=True, verbose_name='关联工单编号')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True, verbose_name='记录时间')

    class Meta:
        db_table = 'inspection_log'
        verbose_name = '巡检决策日志'
        verbose_name_plural = '巡检决策日志'
        indexes = [
            models.Index(fields=['source_event_type', 'source_event_id'], name='ilog_source_idx'),
            models.Index(fields=['specific_part', 'created_at'], name='ilog_part_time_idx'),
        ]

    def __str__(self):
        return f"[{self.step}/{self.result}] {self.specific_part} #{self.source_event_id} @ {self.created_at}"
