"""
v1.11.0 业主端 miniapp 新端点测试套件

覆盖：
  [unit]        _publish_ondemand_mqtt 防重入逻辑（mock MQTT publish）
  [integration] GET  /api/miniapp/owner/realtime-params/
                  - 归属过滤命中（200 含 data/screen_mac/device_sns）
                  - 越权 specific_part → 403
                  - specific_part 缺失 → 400
                  - 权限矩阵：role=user 200，operator 403，匿名 401
                  - 房间分组正确（panel_* sub_type 由 get_available_sub_types 过滤）
  [integration] POST /api/miniapp/owner/ondemand-refresh/
                  - 归属过滤命中 → 202 accepted（mock MQTT）
                  - 越权 specific_part → 403
                  - specific_part 缺失 → 400
                  - 权限矩阵：role=user 202，operator 403，匿名 401
                  - 防重入：25s 内重复调用 → 202 duplicate

运行：
    cd FreeArkWeb/backend/freearkweb
    PYTHONUTF8=1 FREEARK_POC_MOCK=1 python manage.py test \\
        api.tests.test_miniapp_owner_v1110 \\
        --settings=freearkweb.test_settings --verbosity=2
"""
import time
from unittest.mock import patch, MagicMock

from django.test import TestCase, tag
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import (
    CustomUser, OwnerInfo, OwnerUserBinding,
    PLCLatestData, DeviceConfig, DeviceNode, DeviceFloor, DeviceRoom,
)
from api.views_miniapp_device_settings import _owner_ondemand_inflight


# ── 辅助工厂 ──────────────────────────────────────────────────────────────────

def _make_user(username, role='user'):
    user = CustomUser.objects.create_user(username=username, password='pass1234', role=role)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _client(token_key=None):
    c = APIClient()
    if token_key:
        c.credentials(HTTP_AUTHORIZATION=f'Token {token_key}')
    return c


def _make_owner(specific_part, unique_id='', location_name=None):
    return OwnerInfo.objects.create(
        specific_part=specific_part,
        location_name=location_name or f'测试-{specific_part}',
        building='1栋', unit='1单元', floor='2楼',
        room_number=specific_part.split('-')[-1],
        unique_id=unique_id,
    )


def _bind(user, owner):
    return OwnerUserBinding.objects.create(user=user, owner=owner, active=True)


def _make_device_config(group, sub_type, param_name, group_display='暖通', sub_type_display='书房'):
    return DeviceConfig.objects.create(
        group=group,
        sub_type=sub_type,
        param_name=param_name,
        display_name=f'显示-{param_name}',
        group_display=group_display,
        sub_type_display=sub_type_display,
        is_active=True,
    )


def _make_plc_data(specific_part, param_name, value=100):
    return PLCLatestData.objects.create(
        specific_part=specific_part,
        param_name=param_name,
        value=value,
    )


REALTIME_URL = '/api/miniapp/owner/realtime-params/'
ONDEMAND_URL = '/api/miniapp/owner/ondemand-refresh/'


# ===========================================================================
# GET /api/miniapp/owner/realtime-params/ — 权限矩阵
# ===========================================================================

@tag('integration', 'permissions')
class RealtimeParamsPermissionsTest(TestCase):

    def setUp(self):
        self.owner_info = _make_owner('1-1-2-201', unique_id='aabbccdd')
        self.user, self.tok = _make_user('owner_a')
        _bind(self.user, self.owner_info)
        self.operator, self.op_tok = _make_user('op_b', role='operator')

    def test_owner_200(self):
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 200)

    def test_anonymous_401(self):
        r = _client().get(REALTIME_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 401)

    def test_operator_403(self):
        # IsOwnerUser 仅允许 role=user
        r = _client(self.op_tok).get(REALTIME_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 403)


# ===========================================================================
# GET /api/miniapp/owner/realtime-params/ — 归属过滤
# ===========================================================================

@tag('integration', 'auth_filter')
class RealtimeParamsAuthFilterTest(TestCase):

    def setUp(self):
        self.owner_a = _make_owner('1-1-2-201', unique_id='mac_aabb')
        self.owner_b = _make_owner('2-1-3-301', unique_id='mac_ccdd')

        self.user_a, self.tok_a = _make_user('user_a')
        _bind(self.user_a, self.owner_a)  # user_a 只绑定 1-1-2-201

    def test_own_part_200(self):
        r = _client(self.tok_a).get(REALTIME_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['success'])
        self.assertEqual(r.data['specific_part'], '1-1-2-201')

    def test_other_part_403(self):
        """越权访问他人的 specific_part，必须返回 403（REQ-NFUNC-004）。"""
        r = _client(self.tok_a).get(REALTIME_URL, {'specific_part': '2-1-3-301'})
        self.assertEqual(r.status_code, 403)

    def test_missing_specific_part_400(self):
        r = _client(self.tok_a).get(REALTIME_URL)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.data['success'])

    def test_screen_mac_returned(self):
        """screen_mac 应从 OwnerInfo.unique_id 取得（ADR-1110-02）。"""
        r = _client(self.tok_a).get(REALTIME_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['screen_mac'], 'mac_aabb')

    def test_device_sns_empty_when_no_tree(self):
        """无 DeviceNode 记录时 device_sns 返回空列表（设备树未同步降级场景）。"""
        r = _client(self.tok_a).get(REALTIME_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['device_sns'], [])


# ===========================================================================
# GET /api/miniapp/owner/realtime-params/ — 房间分组正确性
# ===========================================================================

@tag('integration', 'grouping')
class RealtimeParamsGroupingTest(TestCase):
    """
    验证参数分组复用 get_available_sub_types + DeviceConfig 逻辑。
    使用 SYSTEM_LEVEL_SUB_TYPES 中的 main_thermostat（始终可用，无需房间验证）
    以绕过 get_available_sub_types 的房间同步依赖，专注测试分组结构。
    """

    def setUp(self):
        # 准备业主 + 绑定
        self.owner = _make_owner('3-1-1-101', unique_id='mac_test')
        self.user, self.tok = _make_user('grouper')
        _bind(self.user, self.owner)

        # 使用系统级 sub_type（main_thermostat），始终出现在 available_sub_types
        self.cfg = _make_device_config(
            group='hvac',
            sub_type='main_thermostat',
            param_name='temp',
            group_display='暖通',
            sub_type_display='主机温控',
        )
        _make_plc_data('3-1-1-101', 'temp', value=250)

    def test_data_structure(self):
        """响应的 data 字段具有正确的嵌套结构 group → sub_type → params。"""
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': '3-1-1-101'})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']
        self.assertIn('hvac', data)
        self.assertIn('main_thermostat', data['hvac']['sub_types'])
        params = data['hvac']['sub_types']['main_thermostat']['params']
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]['param_name'], 'temp')
        self.assertEqual(params[0]['value'], 250)
        self.assertEqual(params[0]['display_name'], '显示-temp')

    def test_inactive_config_excluded(self):
        """is_active=False 的 DeviceConfig 不出现在响应中。"""
        DeviceConfig.objects.filter(pk=self.cfg.pk).update(is_active=False)
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': '3-1-1-101'})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']
        # 无有效参数时 group 会被清理
        self.assertNotIn('hvac', data)

    def test_no_plc_data_excluded(self):
        """无对应 PLCLatestData 的参数不出现在 params 中（只展示有数据的参数）。"""
        PLCLatestData.objects.filter(param_name='temp').delete()
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': '3-1-1-101'})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']
        self.assertNotIn('hvac', data)


# ===========================================================================
# GET /api/miniapp/owner/realtime-params/ — device_sn 集成
# ===========================================================================

@tag('integration', 'device_sn')
class RealtimeParamsDeviceSnTest(TestCase):

    def setUp(self):
        self.owner = _make_owner('4-1-1-401', unique_id='mac_dsn')
        self.user, self.tok = _make_user('dsn_user')
        _bind(self.user, self.owner)

        # 建 DeviceFloor → DeviceRoom → DeviceNode
        floor = DeviceFloor.objects.create(owner=self.owner, floor_no=1, floor_name='一层')
        room = DeviceRoom.objects.create(floor=floor, room_name='书房', ori_room_name='书房', room_type=1)
        DeviceNode.objects.create(room=room, device_sn=10001, device_name='温控面板', system_flag=1, product_code='PC01', category_code=1)
        DeviceNode.objects.create(room=room, device_sn=10002, device_name='温控面板2', system_flag=1, product_code='PC01', category_code=1)

    def test_device_sns_returned(self):
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': '4-1-1-401'})
        self.assertEqual(r.status_code, 200)
        sns = r.data['device_sns']
        self.assertIn(10001, sns)
        self.assertIn(10002, sns)


# ===========================================================================
# POST /api/miniapp/owner/ondemand-refresh/ — 权限矩阵
# ===========================================================================

@tag('integration', 'permissions')
class OndemandRefreshPermissionsTest(TestCase):

    def setUp(self):
        self.owner_info = _make_owner('5-1-2-201')
        self.user, self.tok = _make_user('owner_c')
        _bind(self.user, self.owner_info)
        self.operator, self.op_tok = _make_user('op_c', role='operator')

    @patch('api.views_miniapp_device_settings._publish_ondemand_mqtt')
    def test_owner_202(self, mock_pub):
        mock_pub.return_value = ('accepted', '')
        r = _client(self.tok).post(ONDEMAND_URL, {'specific_part': '5-1-2-201'}, format='json')
        self.assertEqual(r.status_code, 202)

    def test_anonymous_401(self):
        r = _client().post(ONDEMAND_URL, {'specific_part': '5-1-2-201'}, format='json')
        self.assertEqual(r.status_code, 401)

    def test_operator_403(self):
        r = _client(self.op_tok).post(ONDEMAND_URL, {'specific_part': '5-1-2-201'}, format='json')
        self.assertEqual(r.status_code, 403)


# ===========================================================================
# POST /api/miniapp/owner/ondemand-refresh/ — 归属过滤
# ===========================================================================

@tag('integration', 'auth_filter')
class OndemandRefreshAuthFilterTest(TestCase):

    def setUp(self):
        self.owner_a = _make_owner('6-1-2-201')
        self.owner_b = _make_owner('7-1-3-301')
        self.user_a, self.tok_a = _make_user('user_d')
        _bind(self.user_a, self.owner_a)  # 只绑定 6-1-2-201

    @patch('api.views_miniapp_device_settings._publish_ondemand_mqtt')
    def test_own_part_202(self, mock_pub):
        mock_pub.return_value = ('accepted', '')
        r = _client(self.tok_a).post(ONDEMAND_URL, {'specific_part': '6-1-2-201'}, format='json')
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.data['status'], 'accepted')
        self.assertEqual(r.data['specific_part'], '6-1-2-201')

    def test_other_part_403(self):
        """越权触发他人的 ondemand-refresh，必须返回 403（REQ-NFUNC-004）。"""
        r = _client(self.tok_a).post(ONDEMAND_URL, {'specific_part': '7-1-3-301'}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_missing_specific_part_400(self):
        r = _client(self.tok_a).post(ONDEMAND_URL, {}, format='json')
        self.assertEqual(r.status_code, 400)

    @patch('api.views_miniapp_device_settings._publish_ondemand_mqtt')
    def test_duplicate_202(self, mock_pub):
        mock_pub.return_value = ('duplicate', 'inflight')
        r = _client(self.tok_a).post(ONDEMAND_URL, {'specific_part': '6-1-2-201'}, format='json')
        self.assertEqual(r.status_code, 202)
        self.assertEqual(r.data['status'], 'duplicate')

    @patch('api.views_miniapp_device_settings._publish_ondemand_mqtt')
    def test_mqtt_error_503(self, mock_pub):
        mock_pub.return_value = ('error', 'Connection refused')
        r = _client(self.tok_a).post(ONDEMAND_URL, {'specific_part': '6-1-2-201'}, format='json')
        self.assertEqual(r.status_code, 503)
        self.assertIn('MQTT broker', r.data['detail'])


# ===========================================================================
# _publish_ondemand_mqtt 防重入单元测试
# ===========================================================================

@tag('unit')
class PublishOndemandMqttTest(TestCase):
    """
    测试 _publish_ondemand_mqtt 防重入逻辑（mock MQTT，不实际发布）。
    注意：_owner_ondemand_inflight 是模块级字典，测试间需手动清理。
    """

    def setUp(self):
        # 清理防重入缓存，避免测试间污染
        _owner_ondemand_inflight.clear()

    def tearDown(self):
        _owner_ondemand_inflight.clear()

    @patch('api.views_miniapp_device_settings.get_allowed_param_names', return_value=[])
    @patch('paho.mqtt.publish.single')
    def test_first_call_accepted(self, mock_single, mock_allowed):
        from api.views_miniapp_device_settings import _publish_ondemand_mqtt
        outcome, detail = _publish_ondemand_mqtt('9-1-1-901')
        self.assertEqual(outcome, 'accepted')
        mock_single.assert_called_once()

    @patch('api.views_miniapp_device_settings.get_allowed_param_names', return_value=[])
    @patch('paho.mqtt.publish.single')
    def test_second_call_within_ttl_is_duplicate(self, mock_single, mock_allowed):
        from api.views_miniapp_device_settings import _publish_ondemand_mqtt
        sp = '9-1-1-902'
        # 第一次
        _publish_ondemand_mqtt(sp)
        # 第二次（在 25s TTL 内）
        outcome, _ = _publish_ondemand_mqtt(sp)
        self.assertEqual(outcome, 'duplicate')
        # MQTT publish 只调用了一次
        self.assertEqual(mock_single.call_count, 1)

    @patch('api.views_miniapp_device_settings.get_allowed_param_names', return_value=[])
    @patch('paho.mqtt.publish.single', side_effect=Exception('Connection refused'))
    def test_mqtt_failure_returns_error(self, mock_single, mock_allowed):
        from api.views_miniapp_device_settings import _publish_ondemand_mqtt
        outcome, detail = _publish_ondemand_mqtt('9-1-1-903')
        self.assertEqual(outcome, 'error')
        self.assertIn('Connection refused', detail)
