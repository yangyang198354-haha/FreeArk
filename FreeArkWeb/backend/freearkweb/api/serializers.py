from rest_framework import serializers
from django.contrib.auth import authenticate
from .models import CustomUser, UsageQuantityDaily, UsageQuantityMonthly

class UserSerializer(serializers.ModelSerializer):
    """用户序列化器"""
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'role', 'department', 'position', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

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