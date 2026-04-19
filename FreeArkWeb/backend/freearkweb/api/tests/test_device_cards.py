"""
设备卡片面板功能测试套件 — REQ-FUNC-033 / REQ-FUNC-034

覆盖范围：
  - DeviceConfig 模型基本行为：单元测试
  - DeviceParamHistory 模型基本行为：单元测试
  - GET /api/devices/realtime-params/ API：集成测试
  - GET /api/devices/param-history/<device_id>/ API：集成测试

运行方式（在 FreeArkWeb/backend/freearkweb 目录下）：
    python manage.py test api.tests.test_device_cards --settings=freearkweb.test_settings --verbosity=2

测试环境：SQLite :memory:（由 test_settings.py 配置）
"""
from datetime import datetime, timedelta

from django.test import TestCase
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
    device_id='hvac-main-thermostat',
    display_name='主温控器',
    group='hvac',
    sub_type='main_thermostat',
    group_display='暖通',
    sub_type_display='主温控器',
    is_active=True,
):
    return DeviceConfig.objects.create(
        device_id=device_id,
        display_name=display_name,
        group=group,
        sub_type=sub_type,
        group_display=group_display,
        sub_type_display=sub_type_display,
        is_active=is_active,
    )


def make_plc_latest(device_id, param_name, value, collected_at=None):
    if collected_at is None:
        collected_at = datetime(2026, 4, 19, 10, 0, 0)
    return PLCLatestData.objects.create(
        specific_part=device_id,
        param_name=param_name,
        value=value,
        collected_at=collected_at,
    )


def make_history(device_id, param_name, value, collected_at=None):
    if collected_at is None:
        collected_at = datetime(2026, 4, 19, 10, 0, 0)
    return DeviceParamHistory.objects.create(
        device_id=device_id,
        param_name=param_name,
        value=value,
        collected_at=collected_at,
    )


# ---------------------------------------------------------------------------
# UNIT TESTS: DeviceConfig Model
# ---------------------------------------------------------------------------

class TestDeviceConfigModel(TestCase):
    """DeviceConfig 模型基本行为验证"""

    # GWT-DC-01: 创建设备配置
    def test_create_device_config(self):
        """
        Given: 提供完整字段
        When:  创建 DeviceConfig 实例
        Then:  记录持久化，device_id 唯一约束生效
        """
        cfg = make_device_config()
        self.assertEqual(DeviceConfig.objects.count(), 1)
        self.assertEqual(cfg.device_id, 'hvac-main-thermostat')
        self.assertEqual(cfg.group, 'hvac')
        self.assertEqual(cfg.sub_type, 'main_thermostat')
        self.assertTrue(cfg.is_active)

    # GWT-DC-02: device_id 唯一约束
    def test_device_id_unique_constraint(self):
        """
        Given: 已存在 device_id='hvac-main-thermostat' 的配置
        When:  尝试创建相同 device_id 的第二条记录
        Then:  抛出 IntegrityError（唯一约束违反）
        """
        make_device_config()
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            DeviceConfig.objects.create(
                device_id='hvac-main-thermostat',
                display_name='重复设备',
                group='hvac',
                sub_type='main_thermostat',
                group_display='暖通',
                sub_type_display='主温控器',
            )

    # GWT-DC-03: is_active 默认为 True
    def test_is_active_default_true(self):
        """
        Given: 创建 DeviceConfig 时不指定 is_active
        When:  保存记录
        Then:  is_active 默认为 True
        """
        cfg = DeviceConfig.objects.create(
            device_id='test-device',
            display_name='测试设备',
            group='hvac',
            sub_type='room_panel',
            group_display='暖通',
            sub_type_display='温控面板',
        )
        self.assertTrue(cfg.is_active)

    # GWT-DC-04: __str__ 返回预期格式
    def test_str_representation(self):
        """
        Given: 创建设备配置
        When:  调用 str()
        Then:  返回 "{display_name} ({device_id})" 格式
        """
        cfg = make_device_config()
        self.assertEqual(str(cfg), '主温控器 (hvac-main-thermostat)')


# ---------------------------------------------------------------------------
# UNIT TESTS: DeviceParamHistory Model
# ---------------------------------------------------------------------------

class TestDeviceParamHistoryModel(TestCase):
    """DeviceParamHistory 模型基本行为验证"""

    # GWT-DH-01: 创建历史记录
    def test_create_history_record(self):
        """
        Given: 提供 device_id, param_name, value, collected_at
        When:  创建 DeviceParamHistory 实例
        Then:  记录持久化，字段值正确
        """
        ts = datetime(2026, 4, 19, 10, 0, 0)
        record = make_history('hvac-main-thermostat', 'room_temp', 245, ts)
        self.assertEqual(DeviceParamHistory.objects.count(), 1)
        self.assertEqual(record.device_id, 'hvac-main-thermostat')
        self.assertEqual(record.param_name, 'room_temp')
        self.assertEqual(record.value, 245)

    # GWT-DH-02: 同一设备同一参数可有多条记录（追加写入，无唯一约束）
    def test_multiple_records_same_device_param(self):
        """
        Given: 同一 (device_id, param_name) 组合
        When:  写入两条不同时间的记录
        Then:  两条记录都存在（不触发 unique_together 约束）
        """
        ts1 = datetime(2026, 4, 19, 10, 0, 0)
        ts2 = datetime(2026, 4, 19, 10, 5, 0)
        make_history('hvac-main-thermostat', 'room_temp', 240, ts1)
        make_history('hvac-main-thermostat', 'room_temp', 245, ts2)
        count = DeviceParamHistory.objects.filter(
            device_id='hvac-main-thermostat', param_name='room_temp'
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
            device_id='test-dev',
            param_name='status',
            value=None,
            collected_at=datetime(2026, 4, 19, 10, 0, 0),
        )
        self.assertIsNone(record.value)

    # GWT-DH-04: __str__ 包含关键字段
    def test_str_representation(self):
        """
        Given: 创建历史记录
        When:  调用 str()
        Then:  返回字符串包含 device_id 和 param_name
        """
        ts = datetime(2026, 4, 19, 10, 0, 0)
        record = make_history('hvac-main-thermostat', 'room_temp', 245, ts)
        s = str(record)
        self.assertIn('hvac-main-thermostat', s)
        self.assertIn('room_temp', s)


# ---------------------------------------------------------------------------
# INTEGRATION TESTS: GET /api/devices/realtime-params/
# ---------------------------------------------------------------------------

class TestDeviceRealtimeParamsAPI(TestCase):
    """测试实时参数卡片接口的响应格式与过滤逻辑"""

    def setUp(self):
        self.client = APIClient()
        # 该接口为 AllowAny，无需认证，但测试时可选择带 token
        _, self.token = make_admin()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

        # 创建两个设备配置
        self.cfg_main = make_device_config(
            device_id='hvac-main-thermostat',
            display_name='主温控器',
            group='hvac',
            sub_type='main_thermostat',
            group_display='暖通',
            sub_type_display='主温控器',
        )
        self.cfg_room = make_device_config(
            device_id='hvac-room-shufang',
            display_name='书房-温控面板',
            group='hvac',
            sub_type='room_panel',
            group_display='暖通',
            sub_type_display='温控面板',
        )

        # 写入 PLCLatestData（10 分钟内，非超时）
        now_fresh = datetime.now() - timedelta(minutes=5)
        make_plc_latest('hvac-main-thermostat', 'room_temp', 245, now_fresh)
        make_plc_latest('hvac-main-thermostat', 'water_temp', 600, now_fresh)
        make_plc_latest('hvac-room-shufang', 'set_temp', 220, now_fresh)

    # GWT-API-01: 基础响应结构
    def test_response_structure(self):
        """
        Given: 2 个 DeviceConfig，均有 PLCLatestData
        When:  GET /api/devices/realtime-params/
        Then:  返回 200，success=true，data 包含 hvac 分组
        """
        resp = self.client.get('/api/devices/realtime-params/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('hvac', data['data'])

    # GWT-API-02: 分组嵌套结构正确
    def test_nested_structure(self):
        """
        Given: hvac 分组下有 main_thermostat 和 room_panel 两个子类型
        When:  GET /api/devices/realtime-params/
        Then:  data.hvac.sub_types 包含两个子类型键
        """
        resp = self.client.get('/api/devices/realtime-params/')
        hvac = resp.json()['data']['hvac']
        self.assertEqual(hvac['display'], '暖通')
        self.assertIn('main_thermostat', hvac['sub_types'])
        self.assertIn('room_panel', hvac['sub_types'])

    # GWT-API-03: 设备参数列表正确
    def test_device_params_listed(self):
        """
        Given: hvac-main-thermostat 有 2 个参数
        When:  GET /api/devices/realtime-params/
        Then:  对应设备的 params 列表长度为 2
        """
        resp = self.client.get('/api/devices/realtime-params/')
        devices = resp.json()['data']['hvac']['sub_types']['main_thermostat']['devices']
        device = next((d for d in devices if d['device_id'] == 'hvac-main-thermostat'), None)
        self.assertIsNotNone(device)
        self.assertEqual(len(device['params']), 2)

    # GWT-API-04: group 过滤参数生效
    def test_group_filter(self):
        """
        Given: 只有 hvac 分组的设备
        When:  GET /api/devices/realtime-params/?group=hvac
        Then:  返回 data 中包含 hvac，无其他分组
        """
        resp = self.client.get('/api/devices/realtime-params/', {'group': 'hvac'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertIn('hvac', data)

    # GWT-API-05: group 过滤不存在的分组返回空 data
    def test_group_filter_no_match(self):
        """
        Given: 只有 hvac 分组
        When:  GET /api/devices/realtime-params/?group=nonexistent
        Then:  返回 200，data 为空字典
        """
        resp = self.client.get('/api/devices/realtime-params/', {'group': 'nonexistent'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data'], {})

    # GWT-API-06: is_active=False 的设备不出现在响应中
    def test_inactive_device_excluded(self):
        """
        Given: 新增一个 is_active=False 的设备配置，并写入 PLCLatestData
        When:  GET /api/devices/realtime-params/
        Then:  该设备不出现在响应中
        """
        make_device_config(
            device_id='hvac-inactive-device',
            display_name='停用设备',
            group='hvac',
            sub_type='main_thermostat',
            group_display='暖通',
            sub_type_display='主温控器',
            is_active=False,
        )
        make_plc_latest('hvac-inactive-device', 'room_temp', 100)
        resp = self.client.get('/api/devices/realtime-params/')
        data = resp.json()['data']
        devices = data.get('hvac', {}).get('sub_types', {}).get('main_thermostat', {}).get('devices', [])
        device_ids = [d['device_id'] for d in devices]
        self.assertNotIn('hvac-inactive-device', device_ids)

    # GWT-API-07: 超过 10 分钟未更新的参数标注 is_stale=True
    def test_stale_params_flagged(self):
        """
        Given: hvac-stale-device 有参数，collected_at 超过 10 分钟前
        When:  GET /api/devices/realtime-params/
        Then:  该参数的 is_stale = true
        """
        make_device_config(
            device_id='hvac-stale-device',
            display_name='超时设备',
            group='hvac',
            sub_type='main_thermostat',
            group_display='暖通',
            sub_type_display='主温控器',
        )
        stale_time = datetime.now() - timedelta(minutes=15)
        make_plc_latest('hvac-stale-device', 'room_temp', 200, stale_time)

        resp = self.client.get('/api/devices/realtime-params/')
        devices = resp.json()['data']['hvac']['sub_types']['main_thermostat']['devices']
        stale_dev = next((d for d in devices if d['device_id'] == 'hvac-stale-device'), None)
        self.assertIsNotNone(stale_dev)
        stale_param = next((p for p in stale_dev['params'] if p['param_name'] == 'room_temp'), None)
        self.assertIsNotNone(stale_param)
        self.assertTrue(stale_param['is_stale'])

    # GWT-API-08: 10 分钟内更新的参数 is_stale=False
    def test_fresh_params_not_stale(self):
        """
        Given: hvac-main-thermostat 的参数，collected_at 为 5 分钟前
        When:  GET /api/devices/realtime-params/
        Then:  参数的 is_stale = false
        """
        resp = self.client.get('/api/devices/realtime-params/')
        devices = resp.json()['data']['hvac']['sub_types']['main_thermostat']['devices']
        device = next((d for d in devices if d['device_id'] == 'hvac-main-thermostat'), None)
        for param in device['params']:
            self.assertFalse(param['is_stale'])

    # GWT-API-09: history_url 字段存在且格式正确
    def test_history_url_present(self):
        """
        Given: 设备 hvac-main-thermostat
        When:  GET /api/devices/realtime-params/
        Then:  设备 dict 包含 history_url 字段，值为 /device-history/hvac-main-thermostat
        """
        resp = self.client.get('/api/devices/realtime-params/')
        devices = resp.json()['data']['hvac']['sub_types']['main_thermostat']['devices']
        device = next((d for d in devices if d['device_id'] == 'hvac-main-thermostat'), None)
        self.assertIn('history_url', device)
        self.assertEqual(device['history_url'], '/device-history/hvac-main-thermostat')

    # GWT-API-10: 无 PLCLatestData 的设备，params 为空列表
    def test_device_without_plc_data_has_empty_params(self):
        """
        Given: 新增设备配置，但无对应 PLCLatestData 记录
        When:  GET /api/devices/realtime-params/
        Then:  该设备的 params 为空列表
        """
        make_device_config(
            device_id='hvac-no-data',
            display_name='无数据设备',
            group='hvac',
            sub_type='room_panel',
            group_display='暖通',
            sub_type_display='温控面板',
        )
        resp = self.client.get('/api/devices/realtime-params/')
        devices = resp.json()['data']['hvac']['sub_types']['room_panel']['devices']
        no_data_dev = next((d for d in devices if d['device_id'] == 'hvac-no-data'), None)
        self.assertIsNotNone(no_data_dev)
        self.assertEqual(no_data_dev['params'], [])

    # GWT-API-11: 未认证用户可以访问（AllowAny）
    def test_unauthenticated_access_allowed(self):
        """
        Given: 未附带认证 Token 的请求
        When:  GET /api/devices/realtime-params/
        Then:  返回 200（AllowAny 权限）
        """
        anon_client = APIClient()
        resp = anon_client.get('/api/devices/realtime-params/')
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# INTEGRATION TESTS: GET /api/devices/param-history/<device_id>/
# ---------------------------------------------------------------------------

class TestDeviceParamHistoryAPI(TestCase):
    """测试历史参数查询接口的过滤、分页和排序逻辑"""

    def setUp(self):
        self.client = APIClient()
        # AllowAny 接口，无需认证

        DEVICE = 'hvac-main-thermostat'
        self.device_id = DEVICE

        # 写入 5 条历史记录，时间间隔 5 分钟
        base_ts = datetime(2026, 4, 19, 10, 0, 0)
        for i in range(5):
            ts = base_ts + timedelta(minutes=i * 5)
            make_history(DEVICE, 'room_temp', 240 + i, ts)

        # 再写入 3 条不同参数
        for i in range(3):
            ts = base_ts + timedelta(minutes=i * 3)
            make_history(DEVICE, 'water_temp', 600 + i, ts)

        # 另一个设备的数据（用于隔离测试）
        make_history('other-device', 'pressure', 100, base_ts)

    # GWT-HIST-01: 基础分页响应
    def test_basic_paginated_response(self):
        """
        Given: device_id='hvac-main-thermostat' 有 8 条历史记录
        When:  GET /api/devices/param-history/hvac-main-thermostat/
        Then:  返回 200，count=8，results 非空
        """
        resp = self.client.get(f'/api/devices/param-history/{self.device_id}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 8)
        self.assertIsInstance(data['results'], list)

    # GWT-HIST-02: 倒序排序（collected_at DESC）
    def test_results_ordered_by_collected_at_desc(self):
        """
        Given: 5 条 room_temp 记录，时间递增
        When:  GET 不带 param_name 过滤
        Then:  results 的 collected_at 严格倒序排列
        """
        resp = self.client.get(f'/api/devices/param-history/{self.device_id}/')
        results = resp.json()['results']
        timestamps = [r['collected_at'] for r in results]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))

    # GWT-HIST-03: param_name 过滤
    def test_param_name_filter(self):
        """
        Given: 8 条记录，其中 5 条 room_temp，3 条 water_temp
        When:  GET ?param_name=room_temp
        Then:  count=5，所有 results 的 param_name == 'room_temp'
        """
        resp = self.client.get(
            f'/api/devices/param-history/{self.device_id}/',
            {'param_name': 'room_temp'}
        )
        data = resp.json()
        self.assertEqual(data['count'], 5)
        for r in data['results']:
            self.assertEqual(r['param_name'], 'room_temp')

    # GWT-HIST-04: start_time 过滤
    def test_start_time_filter(self):
        """
        Given: room_temp 记录时间从 10:00 到 10:20，间隔 5 分钟（共 5 条）
        When:  GET ?param_name=room_temp&start_time=2026-04-19 10:10:00
        Then:  仅返回 10:10、10:15、10:20 三条记录（count=3）
        """
        resp = self.client.get(
            f'/api/devices/param-history/{self.device_id}/',
            {
                'param_name': 'room_temp',
                'start_time': '2026-04-19 10:10:00',
            }
        )
        data = resp.json()
        self.assertEqual(data['count'], 3)

    # GWT-HIST-05: end_time 过滤
    def test_end_time_filter(self):
        """
        Given: room_temp 记录时间从 10:00 到 10:20
        When:  GET ?param_name=room_temp&end_time=2026-04-19 10:09:59
        Then:  仅返回 10:00、10:05 两条记录（count=2）
        """
        resp = self.client.get(
            f'/api/devices/param-history/{self.device_id}/',
            {
                'param_name': 'room_temp',
                'end_time': '2026-04-19 10:09:59',
            }
        )
        data = resp.json()
        self.assertEqual(data['count'], 2)

    # GWT-HIST-06: 分页 page / page_size
    def test_pagination(self):
        """
        Given: 8 条记录
        When:  GET ?page=1&page_size=3
        Then:  results 长度为 3，count=8，page=1，page_size=3
        """
        resp = self.client.get(
            f'/api/devices/param-history/{self.device_id}/',
            {'page': 1, 'page_size': 3}
        )
        data = resp.json()
        self.assertEqual(len(data['results']), 3)
        self.assertEqual(data['count'], 8)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['page_size'], 3)

    # GWT-HIST-07: 第二页分页
    def test_pagination_page_2(self):
        """
        Given: 8 条记录，page_size=5
        When:  GET ?page=2&page_size=5
        Then:  results 长度为 3（第二页剩余）
        """
        resp = self.client.get(
            f'/api/devices/param-history/{self.device_id}/',
            {'page': 2, 'page_size': 5}
        )
        data = resp.json()
        self.assertEqual(len(data['results']), 3)

    # GWT-HIST-08: 设备不存在时返回空列表（非 404）
    def test_nonexistent_device_returns_empty_list(self):
        """
        Given: device_id 在历史表中不存在
        When:  GET /api/devices/param-history/nonexistent-device/
        Then:  返回 200，count=0，results=[]
        """
        resp = self.client.get('/api/devices/param-history/nonexistent-device/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['count'], 0)
        self.assertEqual(data['results'], [])

    # GWT-HIST-09: 跨设备隔离
    def test_device_data_isolation(self):
        """
        Given: other-device 有 1 条历史记录
        When:  GET /api/devices/param-history/hvac-main-thermostat/
        Then:  结果中不包含 other-device 的数据
        """
        resp = self.client.get(f'/api/devices/param-history/{self.device_id}/')
        data = resp.json()
        for r in data['results']:
            # 所有 results 都应属于 hvac-main-thermostat（device_id 不在响应中，通过 count 和 param 验证）
            self.assertIn(r['param_name'], ['room_temp', 'water_temp'])
        # other-device 的 pressure 参数不应出现
        param_names = [r['param_name'] for r in data['results']]
        self.assertNotIn('pressure', param_names)

    # GWT-HIST-10: 响应字段格式验证
    def test_response_field_format(self):
        """
        Given: 有历史记录
        When:  GET /api/devices/param-history/hvac-main-thermostat/?page_size=1
        Then:  results[0] 包含 id, param_name, value, collected_at 字段
        """
        resp = self.client.get(
            f'/api/devices/param-history/{self.device_id}/',
            {'page_size': 1}
        )
        data = resp.json()
        self.assertGreater(len(data['results']), 0)
        record = data['results'][0]
        self.assertIn('id', record)
        self.assertIn('param_name', record)
        self.assertIn('value', record)
        self.assertIn('collected_at', record)

    # GWT-HIST-11: collected_at 格式为 YYYY-MM-DD HH:MM:SS
    def test_collected_at_format(self):
        """
        Given: 历史记录 collected_at = datetime(2026, 4, 19, 10, 0, 0)
        When:  GET ?param_name=room_temp&page_size=1&page=5 (最早一条)
        Then:  collected_at 格式为 '2026-04-19 10:00:00'
        """
        resp = self.client.get(
            f'/api/devices/param-history/{self.device_id}/',
            {'param_name': 'room_temp', 'page_size': 1, 'page': 5}
        )
        data = resp.json()
        self.assertEqual(len(data['results']), 1)
        collected_at = data['results'][0]['collected_at']
        self.assertEqual(collected_at, '2026-04-19 10:00:00')

    # GWT-HIST-12: 未认证用户可以访问（AllowAny）
    def test_unauthenticated_access_allowed(self):
        """
        Given: 未附带认证 Token 的请求
        When:  GET /api/devices/param-history/hvac-main-thermostat/
        Then:  返回 200（AllowAny 权限）
        """
        anon_client = APIClient()
        resp = anon_client.get(f'/api/devices/param-history/{self.device_id}/')
        self.assertEqual(resp.status_code, 200)

    # GWT-HIST-13: page_size 默认值为 50
    def test_default_page_size_is_50(self):
        """
        Given: 8 条记录
        When:  GET 不带 page_size 参数
        Then:  响应中 page_size=50，results 返回所有 8 条
        """
        resp = self.client.get(f'/api/devices/param-history/{self.device_id}/')
        data = resp.json()
        self.assertEqual(data['page_size'], 50)
        self.assertEqual(len(data['results']), 8)

    # GWT-HIST-14: device_id 字段包含在响应中
    def test_device_id_in_response(self):
        """
        Given: 查询 hvac-main-thermostat 的历史
        When:  GET /api/devices/param-history/hvac-main-thermostat/
        Then:  响应中 device_id 字段值为 'hvac-main-thermostat'
        """
        resp = self.client.get(f'/api/devices/param-history/{self.device_id}/')
        data = resp.json()
        self.assertEqual(data['device_id'], 'hvac-main-thermostat')
