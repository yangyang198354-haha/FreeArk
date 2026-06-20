"""
设备卡片面板功能测试套件 — REQ-FUNC-033 / REQ-FUNC-034

覆盖范围：
  - DeviceConfig 模型基本行为：单元测试（param_name -> group/sub_type 映射）
  - DeviceParamHistory 模型基本行为：单元测试（specific_part 时序存储）
  - GET /api/devices/realtime-params/?specific_part=... API：集成测试
  - GET /api/devices/param-history/?specific_part=... API：集成测试

运行方式（在 FreeArkWeb/backend/freearkweb 目录下）：
    python manage.py test api.tests.test_device_cards --settings=freearkweb.test_settings --verbosity=2

测试环境：SQLite :memory:（由 test_settings.py 配置）
"""
from datetime import datetime, timedelta

from django.test import TestCase, tag
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import CustomUser, PLCLatestData, DeviceConfig, DeviceParamHistory


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def make_admin(username='admin_cards', password='adminpass123'):
    user = CustomUser.objects.create_user(
        username=username, password=password, role='admin'
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def make_device_config(
    param_name='living_room_temperature',
    display_name='客厅实际温度',
    group='hvac',
    sub_type='main_thermostat',
    group_display='暖通',
    sub_type_display='主温控器',
    is_active=True,
):
    """创建一条 DeviceConfig 记录（param_name -> group/sub_type 映射）"""
    return DeviceConfig.objects.create(
        param_name=param_name,
        display_name=display_name,
        group=group,
        sub_type=sub_type,
        group_display=group_display,
        sub_type_display=sub_type_display,
        is_active=is_active,
    )


def make_plc_latest(specific_part, param_name, value, collected_at=None):
    """创建一条 PLCLatestData 记录"""
    if collected_at is None:
        collected_at = datetime(2026, 4, 19, 10, 0, 0)
    return PLCLatestData.objects.create(
        specific_part=specific_part,
        param_name=param_name,
        value=value,
        collected_at=collected_at,
    )


def make_history(specific_part, param_name, value, collected_at=None):
    """创建一条 DeviceParamHistory 记录"""
    if collected_at is None:
        collected_at = datetime(2026, 4, 19, 10, 0, 0)
    return DeviceParamHistory.objects.create(
        specific_part=specific_part,
        param_name=param_name,
        value=value,
        collected_at=collected_at,
    )


# ---------------------------------------------------------------------------
# UNIT TESTS: DeviceConfig Model
# ---------------------------------------------------------------------------

@tag('unit')
class TestDeviceConfigModel(TestCase):
    """DeviceConfig 模型基本行为验证（param_name -> group/sub_type 映射语义）"""

    # GWT-DC-01: 创建设备配置
    def test_create_device_config(self):
        """
        Given: 提供完整字段（param_name 作为唯一键）
        When:  创建 DeviceConfig 实例
        Then:  记录持久化，param_name 唯一约束生效，group/sub_type 正确
        """
        cfg = make_device_config()
        self.assertEqual(DeviceConfig.objects.count(), 1)
        self.assertEqual(cfg.param_name, 'living_room_temperature')
        self.assertEqual(cfg.group, 'hvac')
        self.assertEqual(cfg.sub_type, 'main_thermostat')
        self.assertTrue(cfg.is_active)

    # GWT-DC-02: (param_name, sub_type) 联合唯一约束
    def test_param_name_sub_type_unique_constraint(self):
        """
        Given: 已存在 param_name='living_room_temperature', sub_type='main_thermostat' 的配置
        When:  尝试创建相同 (param_name, sub_type) 的第二条记录
        Then:  抛出 IntegrityError（联合唯一约束违反）
        """
        make_device_config()
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            DeviceConfig.objects.create(
                param_name='living_room_temperature',
                display_name='重复参数',
                group='hvac',
                sub_type='main_thermostat',
                group_display='暖通',
                sub_type_display='主温控器',
            )

    # GWT-DC-06: 同一 param_name 可出现在不同 sub_type（系统开关双面板场景）
    def test_same_param_in_different_subtypes(self):
        """
        Given: param_name='system_switch' 已在 main_thermostat 下配置
        When:  在 hydraulic_module 下创建相同 param_name 的配置
        Then:  成功创建，两条记录共存（(param_name, sub_type) 联合唯一，不同 sub_type 不冲突）
        """
        make_device_config(param_name='system_switch', sub_type='main_thermostat',
                           display_name='系统开关')
        DeviceConfig.objects.create(
            param_name='system_switch',
            display_name='系统开关',
            group='hvac',
            sub_type='hydraulic_module',
            group_display='暖通',
            sub_type_display='水力模块',
        )
        self.assertEqual(DeviceConfig.objects.filter(param_name='system_switch').count(), 2)

    # GWT-DC-03: is_active 默认为 True
    def test_is_active_default_true(self):
        """
        Given: 创建 DeviceConfig 时不指定 is_active
        When:  保存记录
        Then:  is_active 默认为 True
        """
        cfg = DeviceConfig.objects.create(
            param_name='water_temp',
            display_name='出水温度',
            group='hvac',
            sub_type='hydraulic_module',
            group_display='暖通',
            sub_type_display='水力模块',
        )
        self.assertTrue(cfg.is_active)

    # GWT-DC-04: __str__ 返回预期格式
    def test_str_representation(self):
        """
        Given: 创建设备配置
        When:  调用 str()
        Then:  返回 "{sub_type_display} - {param_name}" 格式
        """
        cfg = make_device_config()
        self.assertEqual(str(cfg), '主温控器 - living_room_temperature')

    # GWT-DC-05: 同一 sub_type 下可有多条 param_name
    def test_multiple_params_in_same_sub_type(self):
        """
        Given: 两个 param_name 同属 main_thermostat
        When:  创建两条 DeviceConfig
        Then:  两条记录都存在，sub_type 相同
        """
        make_device_config(param_name='living_room_temperature', display_name='客厅实际温度')
        make_device_config(param_name='living_room_humidity', display_name='客厅相对湿度')
        count = DeviceConfig.objects.filter(sub_type='main_thermostat').count()
        self.assertEqual(count, 2)


# ---------------------------------------------------------------------------
# UNIT TESTS: DeviceParamHistory Model
# ---------------------------------------------------------------------------

@tag('unit')
class TestDeviceParamHistoryModel(TestCase):
    """DeviceParamHistory 模型基本行为验证（specific_part 时序存储）"""

    # GWT-DH-01: 创建历史记录
    def test_create_history_record(self):
        """
        Given: 提供 specific_part, param_name, value, collected_at
        When:  创建 DeviceParamHistory 实例
        Then:  记录持久化，字段值正确
        """
        ts = datetime(2026, 4, 19, 10, 0, 0)
        record = make_history('9-1-31-3104', 'living_room_temperature', 245, ts)
        self.assertEqual(DeviceParamHistory.objects.count(), 1)
        self.assertEqual(record.specific_part, '9-1-31-3104')
        self.assertEqual(record.param_name, 'living_room_temperature')
        self.assertEqual(record.value, 245)

    # GWT-DH-02: 同一 specific_part+param_name 可有多条记录（追加写入，无唯一约束）
    def test_multiple_records_same_specific_part_param(self):
        """
        Given: 同一 (specific_part, param_name) 组合
        When:  写入两条不同时间的记录
        Then:  两条记录都存在（不触发 unique_together 约束）
        """
        ts1 = datetime(2026, 4, 19, 10, 0, 0)
        ts2 = datetime(2026, 4, 19, 10, 5, 0)
        make_history('9-1-31-3104', 'living_room_temperature', 240, ts1)
        make_history('9-1-31-3104', 'living_room_temperature', 245, ts2)
        count = DeviceParamHistory.objects.filter(
            specific_part='9-1-31-3104', param_name='living_room_temperature'
        ).count()
        self.assertEqual(count, 2)

    # GWT-DH-03: value 允许为 None
    def test_value_can_be_null(self):
        """
        Given: value=None
        When:  创建记录
        Then:  成功保存，value 字段为 None
        """
        record = DeviceParamHistory.objects.create(
            specific_part='9-1-31-3104',
            param_name='system_switch',
            value=None,
            collected_at=datetime(2026, 4, 19, 10, 0, 0),
        )
        self.assertIsNone(record.value)

    # GWT-DH-04: __str__ 包含 specific_part 和 param_name
    def test_str_representation(self):
        """
        Given: 创建历史记录
        When:  调用 str()
        Then:  返回字符串包含 specific_part 和 param_name
        """
        ts = datetime(2026, 4, 19, 10, 0, 0)
        record = make_history('9-1-31-3104', 'living_room_temperature', 245, ts)
        s = str(record)
        self.assertIn('9-1-31-3104', s)
        self.assertIn('living_room_temperature', s)

    # GWT-DH-05: 不同 specific_part 的记录可以共存
    def test_multiple_specific_parts_isolated(self):
        """
        Given: 两个不同 specific_part 写入相同 param_name
        When:  按 specific_part 过滤
        Then:  各自只查到自己的数据
        """
        make_history('9-1-31-3104', 'living_room_temperature', 245)
        make_history('9-1-32-3201', 'living_room_temperature', 260)
        count_3104 = DeviceParamHistory.objects.filter(specific_part='9-1-31-3104').count()
        count_3201 = DeviceParamHistory.objects.filter(specific_part='9-1-32-3201').count()
        self.assertEqual(count_3104, 1)
        self.assertEqual(count_3201, 1)


# ---------------------------------------------------------------------------
# INTEGRATION TESTS: GET /api/devices/realtime-params/
# ---------------------------------------------------------------------------

SPECIFIC_PART = '9-1-31-3104'


@tag('integration')
class TestDeviceRealtimeParamsAPI(TestCase):
    """测试实时参数卡片接口的响应格式与过滤逻辑"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = make_admin()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

        # 创建两个 param_name -> sub_type 的映射
        self.cfg_temp = make_device_config(
            param_name='living_room_temperature',
            display_name='客厅实际温度',
            group='hvac',
            sub_type='main_thermostat',
            group_display='暖通',
            sub_type_display='主温控器',
        )
        self.cfg_humidity = make_device_config(
            param_name='living_room_humidity',
            display_name='客厅相对湿度',
            group='hvac',
            sub_type='main_thermostat',
            group_display='暖通',
            sub_type_display='主温控器',
        )
        # 第二个 sub_type 必须是 v0.5.7 房型过滤认可的合法 sub_type，否则会被
        # get_available_sub_types() 过滤掉（room_panel 既非系统级也非 panel_* 命名，
        # 且本用例未建 DeviceFloor，available 退化为仅系统级）。改用系统级 fresh_air。
        self.cfg_study = make_device_config(
            param_name='study_room_temperature',
            display_name='书房实际温度',
            group='hvac',
            sub_type='fresh_air',
            group_display='暖通',
            sub_type_display='新风',
        )

        # 为 SPECIFIC_PART 写入 PLCLatestData（10 分钟内，非超时）
        now_fresh = datetime.now() - timedelta(minutes=5)
        make_plc_latest(SPECIFIC_PART, 'living_room_temperature', 245, now_fresh)
        make_plc_latest(SPECIFIC_PART, 'living_room_humidity', 60, now_fresh)
        make_plc_latest(SPECIFIC_PART, 'study_room_temperature', 230, now_fresh)

    # GWT-API-01: 缺少 specific_part 返回 400
    def test_missing_specific_part_returns_400(self):
        """
        Given: 不传 specific_part
        When:  GET /api/devices/realtime-params/
        Then:  返回 400，success=false
        """
        resp = self.client.get('/api/devices/realtime-params/')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    # GWT-API-02: 基础响应结构
    def test_response_structure(self):
        """
        Given: specific_part 有 PLCLatestData，DeviceConfig 已配置
        When:  GET /api/devices/realtime-params/?specific_part=9-1-31-3104
        Then:  返回 200，success=true，data 包含 hvac 分组，specific_part 在响应中
        """
        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['specific_part'], SPECIFIC_PART)
        self.assertIn('hvac', data['data'])

    # GWT-API-03: 分组嵌套结构正确（params 直接在 sub_type 下）
    def test_nested_structure(self):
        """
        Given: hvac 分组下有 main_thermostat 和 fresh_air 两个子类型
        When:  GET /api/devices/realtime-params/?specific_part=9-1-31-3104
        Then:  data.hvac.sub_types 包含两个子类型键，每个有 params 列表
        """
        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        hvac = resp.json()['data']['hvac']
        self.assertEqual(hvac['display'], '暖通')
        self.assertIn('main_thermostat', hvac['sub_types'])
        self.assertIn('fresh_air', hvac['sub_types'])
        # params 直接在 sub_type 下，没有 devices 列表
        self.assertIn('params', hvac['sub_types']['main_thermostat'])
        self.assertNotIn('devices', hvac['sub_types']['main_thermostat'])

    # GWT-API-04: params 列表包含正确数量和字段
    def test_params_listed_correctly(self):
        """
        Given: main_thermostat 有 2 个参数（living_room_temperature, living_room_humidity）
        When:  GET /api/devices/realtime-params/?specific_part=9-1-31-3104
        Then:  main_thermostat.params 长度为 2，每条含 param_name、display_name、value、is_stale
        """
        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        params = resp.json()['data']['hvac']['sub_types']['main_thermostat']['params']
        self.assertEqual(len(params), 2)
        param_names = {p['param_name'] for p in params}
        self.assertIn('living_room_temperature', param_names)
        self.assertIn('living_room_humidity', param_names)
        # 验证每条参数有 display_name 字段
        for p in params:
            self.assertIn('display_name', p)
            self.assertIn('value', p)
            self.assertIn('is_stale', p)

    # GWT-API-05: group 过滤参数生效
    def test_group_filter(self):
        """
        Given: 只有 hvac 分组的配置
        When:  GET /api/devices/realtime-params/?specific_part=...&group=hvac
        Then:  返回 data 中包含 hvac，无其他分组
        """
        resp = self.client.get('/api/devices/realtime-params/', {
            'specific_part': SPECIFIC_PART,
            'group': 'hvac',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('hvac', data)

    # GWT-API-06: group 过滤不存在的分组返回空 data
    def test_group_filter_no_match(self):
        """
        Given: 只有 hvac 分组
        When:  GET /api/devices/realtime-params/?specific_part=...&group=nonexistent
        Then:  返回 200，data 为空字典
        """
        resp = self.client.get('/api/devices/realtime-params/', {
            'specific_part': SPECIFIC_PART,
            'group': 'nonexistent',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data'], {})

    # GWT-API-07: is_active=False 的参数配置不出现在响应中
    def test_inactive_config_excluded(self):
        """
        Given: 新增一个 is_active=False 的 param_name 配置，并写入 PLCLatestData
        When:  GET /api/devices/realtime-params/?specific_part=...
        Then:  该 param_name 不出现在响应中
        """
        make_device_config(
            param_name='fresh_air_fault_status',
            display_name='新风机故障状态',
            group='hvac',
            sub_type='fresh_air',
            group_display='暖通',
            sub_type_display='新风',
            is_active=False,
        )
        make_plc_latest(SPECIFIC_PART, 'fresh_air_fault_status', 0)
        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        data = resp.json()['data']
        fresh_air = data.get('hvac', {}).get('sub_types', {}).get('fresh_air', {})
        params = fresh_air.get('params', [])
        param_names = [p['param_name'] for p in params]
        self.assertNotIn('fresh_air_fault_status', param_names)

    # GWT-API-08: 超过 10 分钟未更新的参数标注 is_stale=True
    def test_stale_params_flagged(self):
        """
        Given: 写入超过 10 分钟前的 PLCLatestData
        When:  GET /api/devices/realtime-params/?specific_part=...
        Then:  该参数的 is_stale = true
        """
        make_device_config(
            param_name='operation_mode',
            display_name='运行模式',
            group='hvac',
            sub_type='main_thermostat',
            group_display='暖通',
            sub_type_display='主温控器',
        )
        stale_time = datetime.now() - timedelta(minutes=15)
        make_plc_latest(SPECIFIC_PART, 'operation_mode', 1, stale_time)

        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        params = resp.json()['data']['hvac']['sub_types']['main_thermostat']['params']
        stale_param = next((p for p in params if p['param_name'] == 'operation_mode'), None)
        self.assertIsNotNone(stale_param)
        self.assertTrue(stale_param['is_stale'])

    # GWT-API-09: 10 分钟内更新的参数 is_stale=False
    def test_fresh_params_not_stale(self):
        """
        Given: PLCLatestData collected_at 为 5 分钟前
        When:  GET /api/devices/realtime-params/?specific_part=...
        Then:  参数的 is_stale = false
        """
        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        params = resp.json()['data']['hvac']['sub_types']['main_thermostat']['params']
        for param in params:
            self.assertFalse(param['is_stale'])

    # GWT-API-10: specific_part 隔离——另一个 specific_part 的数据不出现
    def test_specific_part_isolation(self):
        """
        Given: 另一个 specific_part=9-1-32-3201 有相同 param_name 的 PLCLatestData
        When:  GET /api/devices/realtime-params/?specific_part=9-1-31-3104
        Then:  响应数据来自 9-1-31-3104，不受 9-1-32-3201 影响
        """
        make_plc_latest('9-1-32-3201', 'living_room_temperature', 999)
        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        params = resp.json()['data']['hvac']['sub_types']['main_thermostat']['params']
        temp_param = next(p for p in params if p['param_name'] == 'living_room_temperature')
        self.assertEqual(str(temp_param['value']), '245')  # 来自 9-1-31-3104，不是 999

    # GWT-API-11: DeviceConfig 中有配置但 PLCLatestData 无对应数据时，该 sub_type 不出现
    def test_param_without_plc_data_excluded(self):
        """
        Given: 新增 param_name 有 DeviceConfig 配置，但 specific_part=9-1-31-3104 无对应 PLCLatestData
        When:  GET /api/devices/realtime-params/?specific_part=9-1-31-3104
        Then:  该 param_name 所在 sub_type 不出现（或 params 为空的 sub_type 被移除）
        """
        make_device_config(
            param_name='system_switch',
            display_name='系统开关',
            group='hvac',
            sub_type='control',
            group_display='暖通',
            sub_type_display='系统控制',
        )
        # 不为 SPECIFIC_PART 写入 system_switch 的 PLCLatestData
        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        data = resp.json()['data']
        # control sub_type 应不存在（因为 params 为空被过滤掉）
        control = data.get('hvac', {}).get('sub_types', {}).get('control')
        self.assertIsNone(control)

    # GWT-API-13: 能耗表参数（total_hot_quantity / total_cold_quantity）出现在设备面板
    def test_energy_meter_params_in_device_panel(self):
        """
        Given: total_hot_quantity / total_cold_quantity 已写入 PLCLatestData，
               DeviceConfig 已将两个参数配置到 energy_meter 子类型
        When:  GET /api/devices/realtime-params/?specific_part=9-1-31-3104
        Then:  energy_meter.params 中包含两个参数，值正确，is_stale=False
        """
        make_device_config(
            param_name='total_hot_quantity',
            display_name='累计制热量',
            group='hvac',
            sub_type='energy_meter',
            group_display='暖通',
            sub_type_display='能耗表',
        )
        make_device_config(
            param_name='total_cold_quantity',
            display_name='累计制冷量',
            group='hvac',
            sub_type='energy_meter',
            group_display='暖通',
            sub_type_display='能耗表',
        )
        now_fresh = datetime.now() - timedelta(minutes=5)
        make_plc_latest(SPECIFIC_PART, 'total_hot_quantity', 9455, now_fresh)
        make_plc_latest(SPECIFIC_PART, 'total_cold_quantity', 11726, now_fresh)

        resp = self.client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        self.assertEqual(resp.status_code, 200)
        energy_meter = (resp.json()['data']
                        .get('hvac', {})
                        .get('sub_types', {})
                        .get('energy_meter', {}))
        self.assertIn('params', energy_meter)
        param_names = {p['param_name'] for p in energy_meter['params']}
        self.assertIn('total_hot_quantity', param_names)
        self.assertIn('total_cold_quantity', param_names)
        hot = next(p for p in energy_meter['params'] if p['param_name'] == 'total_hot_quantity')
        self.assertEqual(str(hot['value']), '9455')
        self.assertFalse(hot['is_stale'])

    # GWT-API-12: 未认证用户可以访问（AllowAny）
    def test_unauthenticated_access_allowed(self):
        """
        Given: 未附带认证 Token 的请求
        When:  GET /api/devices/realtime-params/?specific_part=...
        Then:  返回 200（AllowAny 权限）
        """
        anon_client = APIClient()
        resp = anon_client.get('/api/devices/realtime-params/', {'specific_part': SPECIFIC_PART})
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# INTEGRATION TESTS: GET /api/devices/param-history/
# ---------------------------------------------------------------------------

@tag('integration')
class TestDeviceParamHistoryAPI(TestCase):
    """测试历史参数查询接口的过滤、分页和排序逻辑"""

    def setUp(self):
        self.client = APIClient()
        # AllowAny 接口，无需认证

        # 写入 5 条 living_room_temperature 历史记录，时间间隔 5 分钟
        base_ts = datetime(2026, 4, 19, 10, 0, 0)
        for i in range(5):
            ts = base_ts + timedelta(minutes=i * 5)
            make_history(SPECIFIC_PART, 'living_room_temperature', 240 + i, ts)

        # 再写入 3 条 living_room_humidity 记录
        for i in range(3):
            ts = base_ts + timedelta(minutes=i * 3)
            make_history(SPECIFIC_PART, 'living_room_humidity', 60 + i, ts)

        # 另一个 specific_part 的数据（用于隔离测试）
        make_history('9-1-32-3201', 'living_room_temperature', 999, base_ts)

        # 创建 sub_type 配置（用于 sub_type 过滤测试）
        make_device_config(
            param_name='living_room_temperature',
            display_name='客厅实际温度',
            sub_type='main_thermostat',
            group='hvac',
            group_display='暖通',
            sub_type_display='主温控器',
        )
        make_device_config(
            param_name='living_room_humidity',
            display_name='客厅相对湿度',
            sub_type='main_thermostat',
            group='hvac',
            group_display='暖通',
            sub_type_display='主温控器',
        )

    # GWT-HIST-01: 缺少 specific_part 返回 400
    def test_missing_specific_part_returns_400(self):
        """
        Given: 不传 specific_part
        When:  GET /api/devices/param-history/
        Then:  返回 400，success=false
        """
        resp = self.client.get('/api/devices/param-history/')
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    # GWT-HIST-02: 基础分页响应
    def test_basic_paginated_response(self):
        """
        Given: specific_part=9-1-31-3104 有 8 条历史记录
        When:  GET /api/devices/param-history/?specific_part=9-1-31-3104
        Then:  返回 200，count=8，results 非空，specific_part 在响应中
        """
        resp = self.client.get('/api/devices/param-history/', {'specific_part': SPECIFIC_PART})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['specific_part'], SPECIFIC_PART)
        self.assertEqual(data['count'], 8)
        self.assertIsInstance(data['results'], list)

    # GWT-HIST-03: 倒序排序（collected_at DESC）
    def test_results_ordered_by_collected_at_desc(self):
        """
        Given: 5 条 living_room_temperature 记录，时间递增
        When:  GET 不带 param_name 过滤
        Then:  results 的 collected_at 严格倒序排列
        """
        resp = self.client.get('/api/devices/param-history/', {'specific_part': SPECIFIC_PART})
        results = resp.json()['results']
        timestamps = [r['collected_at'] for r in results]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    # GWT-HIST-04: param_name 过滤
    def test_param_name_filter(self):
        """
        Given: 8 条记录，其中 5 条 living_room_temperature，3 条 living_room_humidity
        When:  GET ?specific_part=...&param_name=living_room_temperature
        Then:  count=5，所有 results 的 param_name == 'living_room_temperature'
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'param_name': 'living_room_temperature',
        })
        data = resp.json()
        self.assertEqual(data['count'], 5)
        for r in data['results']:
            self.assertEqual(r['param_name'], 'living_room_temperature')

    # GWT-HIST-05: sub_type 过滤（通过 DeviceConfig 找 param_name 列表）
    def test_sub_type_filter(self):
        """
        Given: main_thermostat 包含 living_room_temperature 和 living_room_humidity
        When:  GET ?specific_part=...&sub_type=main_thermostat
        Then:  count=8（两个参数共 8 条），两个 param_name 都出现
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'sub_type': 'main_thermostat',
        })
        data = resp.json()
        self.assertEqual(data['count'], 8)
        param_names = {r['param_name'] for r in data['results']}
        self.assertIn('living_room_temperature', param_names)
        self.assertIn('living_room_humidity', param_names)

    # GWT-HIST-06: sub_type 不存在时返回空
    def test_sub_type_filter_no_match(self):
        """
        Given: sub_type='nonexistent' 在 DeviceConfig 中无配置
        When:  GET ?specific_part=...&sub_type=nonexistent
        Then:  count=0，results=[]
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'sub_type': 'nonexistent',
        })
        data = resp.json()
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])

    # GWT-HIST-07: start_time 过滤
    def test_start_time_filter(self):
        """
        Given: living_room_temperature 记录时间从 10:00 到 10:20，间隔 5 分钟（共 5 条）
        When:  GET ?param_name=living_room_temperature&start_time=2026-04-19 10:10:00
        Then:  仅返回 10:10、10:15、10:20 三条记录（count=3）
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'param_name': 'living_room_temperature',
            'start_time': '2026-04-19 10:10:00',
        })
        data = resp.json()
        self.assertEqual(data['count'], 3)

    # GWT-HIST-08: end_time 过滤
    def test_end_time_filter(self):
        """
        Given: living_room_temperature 记录时间从 10:00 到 10:20
        When:  GET ?param_name=living_room_temperature&end_time=2026-04-19 10:09:59
        Then:  仅返回 10:00、10:05 两条记录（count=2）
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'param_name': 'living_room_temperature',
            'end_time': '2026-04-19 10:09:59',
        })
        data = resp.json()
        self.assertEqual(data['count'], 2)

    # GWT-HIST-09: 分页 page / page_size
    def test_pagination(self):
        """
        Given: 8 条记录
        When:  GET ?page=1&page_size=3
        Then:  results 长度为 3，count=8，page=1，page_size=3
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'page': 1,
            'page_size': 3,
        })
        data = resp.json()
        self.assertEqual(len(data['results']), 3)
        self.assertEqual(data['count'], 8)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['page_size'], 3)

    # GWT-HIST-10: 第二页分页
    def test_pagination_page_2(self):
        """
        Given: 8 条记录，page_size=5
        When:  GET ?page=2&page_size=5
        Then:  results 长度为 3（第二页剩余）
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'page': 2,
            'page_size': 5,
        })
        data = resp.json()
        self.assertEqual(len(data['results']), 3)

    # GWT-HIST-11: specific_part 不存在时返回空列表（非 404）
    def test_nonexistent_specific_part_returns_empty_list(self):
        """
        Given: specific_part 在历史表中不存在
        When:  GET /api/devices/param-history/?specific_part=nonexistent
        Then:  返回 200，count=0，results=[]
        """
        resp = self.client.get('/api/devices/param-history/', {'specific_part': 'nonexistent-sp'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])

    # GWT-HIST-12: 跨 specific_part 隔离
    def test_specific_part_data_isolation(self):
        """
        Given: 9-1-32-3201 有 1 条历史记录
        When:  GET /api/devices/param-history/?specific_part=9-1-31-3104
        Then:  结果中不包含 9-1-32-3201 的数据（count 不变 8）
        """
        resp = self.client.get('/api/devices/param-history/', {'specific_part': SPECIFIC_PART})
        data = resp.json()
        self.assertEqual(data['count'], 8)
        # 所有 results 都属于 9-1-31-3104
        for r in data['results']:
            self.assertIn(r['param_name'], ['living_room_temperature', 'living_room_humidity'])

    # GWT-HIST-13: 响应字段格式验证
    def test_response_field_format(self):
        """
        Given: 有历史记录
        When:  GET /api/devices/param-history/?specific_part=...&page_size=1
        Then:  results[0] 包含 id, param_name, value, collected_at 字段
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'page_size': 1,
        })
        data = resp.json()
        self.assertGreater(len(data['results']), 0)
        record = data['results'][0]
        self.assertIn('id', record)
        self.assertIn('param_name', record)
        self.assertIn('value', record)
        self.assertIn('collected_at', record)

    # GWT-HIST-14: collected_at 格式为 YYYY-MM-DD HH:MM:SS
    def test_collected_at_format(self):
        """
        Given: 历史记录 collected_at = datetime(2026, 4, 19, 10, 0, 0)
        When:  GET ?param_name=living_room_temperature&page_size=1&page=5（最早一条）
        Then:  collected_at 格式为 '2026-04-19 10:00:00'
        """
        resp = self.client.get('/api/devices/param-history/', {
            'specific_part': SPECIFIC_PART,
            'param_name': 'living_room_temperature',
            'page_size': 1,
            'page': 5,
        })
        data = resp.json()
        self.assertEqual(len(data['results']), 1)
        collected_at = data['results'][0]['collected_at']
        self.assertEqual(collected_at, '2026-04-19 10:00:00')

    # GWT-HIST-15: 未认证用户可以访问（AllowAny）
    def test_unauthenticated_access_allowed(self):
        """
        Given: 未附带认证 Token 的请求
        When:  GET /api/devices/param-history/?specific_part=...
        Then:  返回 200（AllowAny 权限）
        """
        anon_client = APIClient()
        resp = anon_client.get('/api/devices/param-history/', {'specific_part': SPECIFIC_PART})
        self.assertEqual(resp.status_code, 200)

    # GWT-HIST-16: page_size 默认值为 50
    def test_default_page_size_is_50(self):
        """
        Given: 8 条记录
        When:  GET 不带 page_size 参数
        Then:  响应中 page_size=50，results 返回所有 8 条
        """
        resp = self.client.get('/api/devices/param-history/', {'specific_part': SPECIFIC_PART})
        data = resp.json()
        self.assertEqual(data['page_size'], 50)
        self.assertEqual(len(data['results']), 8)

    # GWT-HIST-17: specific_part 字段包含在响应中
    def test_specific_part_in_response(self):
        """
        Given: 查询 9-1-31-3104 的历史
        When:  GET /api/devices/param-history/?specific_part=9-1-31-3104
        Then:  响应中 specific_part 字段值为 '9-1-31-3104'
        """
        resp = self.client.get('/api/devices/param-history/', {'specific_part': SPECIFIC_PART})
        data = resp.json()
        self.assertEqual(data['specific_part'], SPECIFIC_PART)
