from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import CustomUser, UsageQuantityDaily, UsageQuantityMonthly, PLCConnectionStatus, OwnerInfo, PLCLatestData, DeviceConfig, DeviceParamHistory

class UserSerializer(serializers.ModelSerializer):
    """用户序列化器"""
    password = serializers.CharField(write_only=True, required=False, style={'input_type': 'password'})
    
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'department', 'position', 'created_at', 'updated_at', 'password']
        read_only_fields = ['id', 'created_at', 'updated_at', 'username']
    
    def update(self, instance, validated_data):
        # 提取密码（如果提供）
        password = validated_data.pop('password', None)
        
        # 更新其他字段
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        # 如果提供了密码，则更新密码
        if password:
            instance.set_password(password)
        
        instance.save()
        return instance

class UserRegistrationSerializer(serializers.ModelSerializer):
    """用户注册序列化器"""
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name', 'role', 'department', 'position']

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "两次输入的密码不匹配"})
        return attrs

    def create(self, validated_data):
        validated_data.pop('password2')
        # v1.6.0 安全：公开自助注册强制为最小权限"普通业主"，忽略客户端传入的 role，
        # 防止任何人自助注册为 operator/admin 绕过 RBAC。需要更高权限由管理员显式创建。
        validated_data['role'] = 'user'
        user = CustomUser.objects.create_user(**validated_data)
        return user

class UserLoginSerializer(serializers.Serializer):
    """用户登录序列化器"""
    username = serializers.CharField()
    password = serializers.CharField(style={'input_type': 'password'})

    def validate(self, attrs):
        username = attrs.get('username')
        password = attrs.get('password')

        if username and password:
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError('用户名或密码错误')
            if not user.is_active:
                raise serializers.ValidationError('用户账户已被禁用')
        else:
            raise serializers.ValidationError('必须提供用户名和密码')

        attrs['user'] = user
        return attrs

class UserCreateSerializer(serializers.ModelSerializer):
    """管理员创建用户序列化器"""
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    # v1.6.0 (OQ-04)：创建用户必须显式选择角色（admin/operator/user），不沿用模型默认值。
    # 非法值由 ChoiceField 校验，返回 400。
    role = serializers.ChoiceField(choices=CustomUser.ROLE_CHOICES, required=True)

    class Meta:
        model = CustomUser
        fields = ['username', 'email', 'password', 'first_name', 'last_name', 'role', 'department', 'position']

    def create(self, validated_data):
        user = CustomUser.objects.create_user(**validated_data)
        return user


class UsageQuantityDailySerializer(serializers.ModelSerializer):
    """每日用量数据序列化器"""
    class Meta:
        model = UsageQuantityDaily
        fields = [
            'id', 'specific_part', 'building', 'unit', 'room_number', 
            'energy_mode', 'initial_energy', 'final_energy', 'usage_quantity', 'time_period'
        ]
        read_only_fields = ['id']


class UsageQuantityMonthlySerializer(serializers.ModelSerializer):
    """每月用量数据序列化器"""
    class Meta:
        model = UsageQuantityMonthly
        fields = [
            'id', 'specific_part', 'building', 'unit', 'room_number',
            'energy_mode', 'initial_energy', 'final_energy', 'usage_quantity', 'usage_month'
        ]
        read_only_fields = ['id']


class PLCConnectionStatusSerializer(serializers.ModelSerializer):
    """PLC连接状态序列化器"""
    class Meta:
        model = PLCConnectionStatus
        fields = [
            'id', 'specific_part', 'connection_status', 'last_online_time',
            'building', 'unit', 'room_number', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class OwnerInfoSerializer(serializers.ModelSerializer):
    """业主信息序列化器"""
    # US-02: 房间数量由 OwnerListCreateView.get_queryset() 的 annotate 注入，
    # 详情/编辑接口不含此 annotate，default=0 避免 AttributeError。
    room_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = OwnerInfo
        fields = [
            'id', 'specific_part', 'location_name', 'building', 'unit',
            'floor', 'room_number', 'bind_status', 'ip_address',
            'unique_id', 'plc_ip_address', 'room_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'room_count', 'created_at', 'updated_at']


class PLCLatestDataParamSerializer(serializers.ModelSerializer):
    """单个参数条目序列化器（用于 PLCLatestData 列表响应中的 params 数组）"""
    collected_at = serializers.SerializerMethodField()

    class Meta:
        model = PLCLatestData
        fields = ['param_name', 'value', 'collected_at']

    def get_collected_at(self, obj):
        if obj.collected_at is None:
            return None
        # 返回与 MQTT 消息中 timestamp 字段格式一致的字符串
        return obj.collected_at.strftime('%Y-%m-%d %H:%M:%S')


class DeviceConfigSerializer(serializers.ModelSerializer):
    """设备配置序列化器（只读）"""
    class Meta:
        model = DeviceConfig
        fields = ['param_name', 'display_name', 'group', 'sub_type', 'group_display', 'sub_type_display', 'is_active']
        read_only_fields = fields


class DeviceParamHistorySerializer(serializers.ModelSerializer):
    """设备参数历史记录序列化器"""
    collected_at = serializers.SerializerMethodField()

    class Meta:
        model = DeviceParamHistory
        fields = ['id', 'param_name', 'value', 'collected_at']

    def get_collected_at(self, obj):
        if obj.collected_at is None:
            return None
        return obj.collected_at.strftime('%Y-%m-%d %H:%M:%S')