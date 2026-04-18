"""
PLCLatestData 功能测试套件

覆盖范围：
  - PLCLatestDataHandler.handle()：单元测试
  - GET /api/plc-latest/ API：集成测试

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_plc_latest --verbosity=2
"""
from datetime import datetime

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import PLCLatestData, CustomUser
from api.mqtt_handlers import PLCLatestDataHandler


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_payload(device_id, params):
    """构造 improved_data_collection_manager 格式的 MQTT payload。

    params: dict[param_name, (value, success, timestamp)]
    """
    data = {}
    for param_name, (value, success, ts) in params.items():
        data[param_name] = {
            'value': value,
            'success': success,
            'message': '读取成功' if success else '读取失败',
            'timestamp': ts,
        }
    return {
        device_id: {
            'PLC IP地址': '192.168.7.83',
            'IP地址': '192.168.7.83',
            '专有部分坐落': '成都-3-1-7-702',
            'data': data,
            'status': 'success',
            'timestamp': '2026-04-18 10:42:55',
        }
    }


def make_admin(username='admin_plc', password='adminpass123'):
    user = CustomUser.objects.create_user(
        username=username, password=password, role='admin'
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


TS = '2026-04-18 10:42:55'
DEVICE = '3-1-7-702'


# ---------------------------------------------------------------------------
# 单元测试：PLCLatestDataHandler
# ---------------------------------------------------------------------------

class TestPLCLatestDataHandlerBasic(TestCase):
    """测试 handler 的核心写入逻辑"""

    def setUp(self):
        self.handler = PLCLatestDataHandler()

    # GWT-01: 正常参数写入
    def test_success_params_are_persisted(self):
        """
        Given: MQTT 消息中包含 3 个 success=true 的参数
        When:  handler.handle() 被调用
        Then:  PLCLatestData 表中存在对应的 3 条记录
        """
        payload = _make_payload(DEVICE, {
            'living_room_temperature': (245, True, TS),
            'living_room_switch': (1, True, TS),
            'hot_water_temperature': (600, True, TS),
        })
        self.handler.handle('/datacollection/plc/to/collector/' + DEVICE, payload)
        self.assertEqual(PLCLatestData.objects.filter(specific_part=DEVICE).count(), 3)

    # GWT-02: success=false 的参数丢弃
    def test_failed_params_are_discarded(self):
        """
        Given: MQTT 消息中一个参数 success=false
        When:  handler.handle() 被调用
        Then:  该参数不写入 PLCLatestData
        """
        payload = _make_payload(DEVICE, {
            'living_room_temperature': (245, True, TS),
            'living_room_switch': (None, False, TS),
        })
        self.handler.handle('/datacollection/plc/to/collector/' + DEVICE, payload)
        self.assertEqual(PLCLatestData.objects.filter(specific_part=DEVICE).count(), 1)
        self.assertFalse(
            PLCLatestData.objects.filter(specific_part=DEVICE, param_name='living_room_switch').exists()
        )

    # GWT-03: 排除 total_hot_quantity / total_cold_quantity
    def test_excluded_params_not_written(self):
        """
        Given: MQTT 消息包含 total_hot_quantity 和 total_cold_quantity（success=true）
        When:  handler.handle() 被调用
        Then:  PLCLatestData 表中不存在这两个参数
        """
        payload = _make_payload(DEVICE, {
            'total_hot_quantity': (12345, True, TS),
            'total_cold_quantity': (67890, True, TS),
            'living_room_temperature': (245, True, TS),
        })
        self.handler.handle('/datacollection/plc/to/collector/' + DEVICE, payload)
        self.assertFalse(
            PLCLatestData.objects.filter(param_name='total_hot_quantity').exists()
        )
        self.assertFalse(
            PLCLatestData.objects.filter(param_name='total_cold_quantity').exists()
        )
        self.assertEqual(PLCLatestData.objects.filter(specific_part=DEVICE).count(), 1)

    # GWT-04: upsert 逻辑——重复写入应更新而不新增
    def test_upsert_updates_existing_record(self):
        """
        Given: 同一 (specific_part, param_name) 已有记录（value=100）
        When:  新消息到达，value=200
        Then:  记录数仍为 1，value 更新为 200
        """
        PLCLatestData.objects.create(
            specific_part=DEVICE,
            param_name='living_room_temperature',
            value=100,
            collected_at=timezone.now(),
        )
        payload = _make_payload(DEVICE, {
            'living_room_temperature': (200, True, TS),
        })
        self.handler.handle('/datacollection/plc/to/collector/' + DEVICE, payload)
        self.assertEqual(PLCLatestData.objects.filter(specific_part=DEVICE).count(), 1)
        record = PLCLatestData.objects.get(specific_part=DEVICE, param_name='living_room_temperature')
        self.assertEqual(record.value, 200)

    # GWT-05: specific_part 解析
    def test_building_info_parsed_from_specific_part(self):
        """
        Given: device_id 为 "3-1-7-702"
        When:  handler.handle() 被调用
        Then:  building=3, unit=1, room_number=702
        """
        payload = _make_payload(DEVICE, {
            'living_room_temperature': (245, True, TS),
        })
        self.handler.handle('/datacollection/plc/to/collector/' + DEVICE, payload)
        record = PLCLatestData.objects.get(specific_part=DEVICE, param_name='living_room_temperature')
        self.assertEqual(record.building, '3')
        self.assertEqual(record.unit, '1')
        self.assertEqual(record.room_number, '702')

    # GWT-06: collected_at 正确解析
    def test_collected_at_is_parsed(self):
        """
        Given: timestamp 字段为 "2026-04-18 10:42:55"
        When:  handler.handle() 被调用
        Then:  collected_at 等于该时间点
        """
        payload = _make_payload(DEVICE, {
            'living_room_temperature': (245, True, TS),
        })
        self.handler.handle('/datacollection/plc/to/collector/' + DEVICE, payload)
        record = PLCLatestData.objects.get(specific_part=DEVICE, param_name='living_room_temperature')
        self.assertIsNotNone(record.collected_at)
        self.assertEqual(record.collected_at.strftime('%Y-%m-%d %H:%M:%S'), TS)

    # GWT-07: 非目标格式 payload 被安全忽略
    def test_unsupported_payload_format_ignored(self):
        """
        Given: payload 包含 'data' 顶层键（非 improved_data_collection_manager 格式）
        When:  handler.handle() 被调用
        Then:  PLCLatestData 表无新记录，不抛出异常
        """
        payload = {
            'data': {'living_room_temperature': {'value': 245, 'success': True, 'timestamp': TS}},
            'PLC IP地址': '192.168.7.83',
        }
        self.handler.handle('/datacollection/plc/to/collector/' + DEVICE, payload)
        self.assertEqual(PLCLatestData.objects.count(), 0)

    # GWT-08: 所有参数全部失败时无记录写入
    def test_all_failed_params_writes_nothing(self):
        """
        Given: 所有参数 success=false
        When:  handler.handle() 被调用
        Then:  PLCLatestData 表无新记录
        """
        payload = _make_payload(DEVICE, {
            'living_room_temperature': (None, False, TS),
            'living_room_switch': (None, False, TS),
        })
        self.handler.handle('/datacollection/plc/to/collector/' + DEVICE, payload)
        self.assertEqual(PLCLatestData.objects.count(), 0)


# ---------------------------------------------------------------------------
# 集成测试：GET /api/plc-latest/
# ---------------------------------------------------------------------------

class TestPLCLatestDataAPI(TestCase):
    """测试查询 API 的响应格式与过滤逻辑"""

    def setUp(self):
        _, self.token = make_admin()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

        # 预填表数据
        now = datetime(2026, 4, 18, 10, 42, 55)
        PLCLatestData.objects.bulk_create([
            PLCLatestData(specific_part=DEVICE, param_name='living_room_temperature',
                          value=245, collected_at=now, plc_ip='192.168.7.83',
                          building='3', unit='1', room_number='702'),
            PLCLatestData(specific_part=DEVICE, param_name='hot_water_temperature',
                          value=600, collected_at=now, plc_ip='192.168.7.83',
                          building='3', unit='1', room_number='702'),
            PLCLatestData(specific_part='3-1-7-703', param_name='living_room_temperature',
                          value=220, collected_at=now, plc_ip='192.168.7.84',
                          building='3', unit='1', room_number='703'),
        ])

    # GWT-09: 按 specific_part 查询全部参数
    def test_list_all_params_for_device(self):
        """
        Given: PLCLatestData 表有 DEVICE 的 2 条参数记录
        When:  GET /api/plc-latest/?specific_part=3-1-7-702
        Then:  返回 200，params 列表长度为 2，specific_part 字段正确
        """
        resp = self.client.get('/api/plc-latest/', {'specific_part': DEVICE})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['specific_part'], DEVICE)
        self.assertEqual(len(data['params']), 2)

    # GWT-10: 按 specific_part + param_name 查询单个参数
    def test_filter_by_param_name(self):
        """
        Given: PLCLatestData 表有 DEVICE 的 living_room_temperature 记录（value=245）
        When:  GET /api/plc-latest/?specific_part=3-1-7-702&param_name=living_room_temperature
        Then:  返回 200，params 列表长度为 1，value=245
        """
        resp = self.client.get('/api/plc-latest/', {
            'specific_part': DEVICE,
            'param_name': 'living_room_temperature',
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['params']), 1)
        self.assertEqual(data['params'][0]['param_name'], 'living_room_temperature')
        self.assertEqual(data['params'][0]['value'], 245)

    # GWT-11: 响应格式包含 collected_at 字符串
    def test_collected_at_format_in_response(self):
        """
        Given: PLCLatestData 记录 collected_at = 2026-04-18 10:42:55
        When:  GET /api/plc-latest/?specific_part=3-1-7-702&param_name=living_room_temperature
        Then:  collected_at 字段值为 "2026-04-18 10:42:55"
        """
        resp = self.client.get('/api/plc-latest/', {
            'specific_part': DEVICE,
            'param_name': 'living_room_temperature',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['params'][0]['collected_at'], '2026-04-18 10:42:55')

    # GWT-12: specific_part 不存在时返回空列表（非 404）
    def test_unknown_device_returns_empty_params(self):
        """
        Given: PLCLatestData 表中不存在 specific_part="9-9-9-999"
        When:  GET /api/plc-latest/?specific_part=9-9-9-999
        Then:  返回 200，params 为空列表
        """
        resp = self.client.get('/api/plc-latest/', {'specific_part': '9-9-9-999'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['params'], [])

    # GWT-13: 缺少 specific_part 参数时返回 400
    def test_missing_specific_part_returns_400(self):
        """
        Given: 请求中未提供 specific_part
        When:  GET /api/plc-latest/
        Then:  返回 400
        """
        resp = self.client.get('/api/plc-latest/')
        self.assertEqual(resp.status_code, 400)

    # GWT-14: 未认证时返回 401
    def test_unauthenticated_request_returns_401(self):
        """
        Given: 请求中未附带认证 Token
        When:  GET /api/plc-latest/?specific_part=3-1-7-702
        Then:  返回 401
        """
        anon_client = APIClient()
        resp = anon_client.get('/api/plc-latest/', {'specific_part': DEVICE})
        self.assertEqual(resp.status_code, 401)

    # GWT-15: 跨设备隔离（不同 specific_part 数据不混淆）
    def test_device_data_isolation(self):
        """
        Given: 表中有 3-1-7-702 和 3-1-7-703 两个设备的数据
        When:  GET /api/plc-latest/?specific_part=3-1-7-703
        Then:  仅返回 3-1-7-703 的记录
        """
        resp = self.client.get('/api/plc-latest/', {'specific_part': '3-1-7-703'})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['specific_part'], '3-1-7-703')
        self.assertEqual(len(data['params']), 1)
        self.assertEqual(data['params'][0]['value'], 220)
