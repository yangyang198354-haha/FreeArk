"""
v1.10.0_miniprogram_param_settings 测试套件——屏端 MQTT 参数配置 config/audit。

覆盖：
  [unit]        screen_param_config：白名单判定 / 配置块结构 / mode 联动表
  [integration] GET  config/：仅返回业主自己房间(含 screen_mac) / 无绑定空列表 /
                            权限矩阵(user 200, operator/admin 403, 匿名 401) / broker+config 块
  [integration] POST audit/：成功落 PLCWriteRecord(channel='screen-mqtt') / 越权 screen_mac 403 /
                            非白名单 attr 400 / 缺 items 400 / result→status 映射
  [integration] 回归：web 路径建的 PLCWriteRecord channel 默认 's7'（C-01 零回归）

运行：
    cd FreeArkWeb/backend/freearkweb
    PYTHONUTF8=1 FREEARK_POC_MOCK=1 python manage.py test \
        api.tests.test_miniapp_device_settings_v1100 \
        --settings=freearkweb.test_settings --verbosity=2
"""
from django.test import TestCase, tag
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import CustomUser, OwnerInfo, OwnerUserBinding, PLCWriteRecord
from api.screen_param_config import (
    is_writable_attr,
    get_screen_param_config,
    SCREEN_WRITABLE_ATTRS,
    MODE_ENERGY_LINK,
)


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def _make(username, role):
    user = CustomUser.objects.create_user(username=username, password="pass1234", role=role)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _client(token_key=None):
    c = APIClient()
    if token_key:
        c.credentials(HTTP_AUTHORIZATION=f"Token {token_key}")
    return c


def _owner(specific_part, unique_id, **over):
    kwargs = dict(
        specific_part=specific_part,
        location_name=f"测试-{specific_part}",
        building="1栋", unit="1单元", floor="2楼",
        room_number=specific_part.split("-")[-1],
        unique_id=unique_id,
    )
    kwargs.update(over)
    return OwnerInfo.objects.create(**kwargs)


def _bind(user, owner):
    return OwnerUserBinding.objects.create(user=user, owner=owner, active=True)


CONFIG_URL = "/api/miniapp/device-settings/config/"
AUDIT_URL = "/api/miniapp/device-settings/audit/"


# ===========================================================================
# 单元：screen_param_config
# ===========================================================================

@tag('unit')
class ScreenParamConfigTest(TestCase):
    def test_writable_whitelist(self):
        for tag_ in ['switch', 'system_switch', 'temp_set', 'out_temp_set',
                     'mode', 'energy_supply_mode', 'energy_saving_sign']:
            self.assertTrue(is_writable_attr(tag_), tag_)

    def test_readonly_not_writable(self):
        for tag_ in ['temp', 'humidity', 'dew_point_temp', 'condensation_alarm',
                     'error_673', 'comm_fault_timeout', 'pm25', 'total_hot_quantity']:
            self.assertFalse(is_writable_attr(tag_), tag_)

    def test_config_block_structure(self):
        cfg = get_screen_param_config()
        self.assertIn('writable_attrs', cfg)
        self.assertIn('product_code_role', cfg)
        self.assertIn('mode_energy_link', cfg)
        self.assertIn('link_product_codes', cfg)

    def test_mode_options_full_enum(self):
        opts = {o['value'] for o in SCREEN_WRITABLE_ATTRS['mode']['options']}
        self.assertEqual(opts, {'cold', 'hot', 'wind', 'dehumidification'})

    def test_energy_supply_options_full_enum(self):
        opts = {o['value'] for o in SCREEN_WRITABLE_ATTRS['energy_supply_mode']['options']}
        self.assertEqual(opts, {'cold', 'hot', 'no'})

    def test_mode_energy_link_wind_is_no(self):
        # 实测：通风时无能源供应（ADR-08）
        self.assertEqual(MODE_ENERGY_LINK['wind'], 'no')
        self.assertEqual(MODE_ENERGY_LINK['cold'], 'cold')
        self.assertEqual(MODE_ENERGY_LINK['hot'], 'hot')


# ===========================================================================
# 集成：GET config/
# ===========================================================================

@tag('integration')
class DeviceSettingsConfigTest(TestCase):
    def setUp(self):
        self.owner_user, self.owner_token = _make("wx_owner_a", "user")
        self.other_user, _ = _make("wx_owner_b", "user")
        self.o1 = _owner("3-1-7-702", "c5d29c52a237ade5")
        self.o2 = _owner("3-1-7-703", "aaaa1111bbbb2222")  # 他人房间
        _bind(self.owner_user, self.o1)
        _bind(self.other_user, self.o2)

    def test_owner_gets_only_own_room_with_screenmac(self):
        resp = _client(self.owner_token).get(CONFIG_URL)
        self.assertEqual(resp.status_code, 200)
        rooms = resp.data['rooms']
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]['specific_part'], "3-1-7-702")
        self.assertEqual(rooms[0]['screen_mac'], "c5d29c52a237ade5")

    def test_other_room_screenmac_not_leaked(self):
        resp = _client(self.owner_token).get(CONFIG_URL)
        macs = {r['screen_mac'] for r in resp.data['rooms']}
        self.assertNotIn("aaaa1111bbbb2222", macs)

    def test_broker_and_config_blocks_present(self):
        resp = _client(self.owner_token).get(CONFIG_URL)
        self.assertIn('broker', resp.data)
        self.assertIn('protocol', resp.data['broker'])
        self.assertIn('writable_attrs', resp.data['config'])
        self.assertIn('value_uplink', resp.data['topics'])

    def test_unbound_owner_empty_rooms(self):
        _u, tok = _make("wx_owner_unbound", "user")
        resp = _client(tok).get(CONFIG_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['rooms'], [])

    def test_operator_forbidden(self):
        _u, tok = _make("op1", "operator")
        self.assertEqual(_client(tok).get(CONFIG_URL).status_code, 403)

    def test_admin_forbidden(self):
        _u, tok = _make("adm1", "admin")
        self.assertEqual(_client(tok).get(CONFIG_URL).status_code, 403)

    def test_anonymous_unauthorized(self):
        self.assertIn(_client().get(CONFIG_URL).status_code, (401, 403))


# ===========================================================================
# 集成：POST audit/
# ===========================================================================

@tag('integration')
class DeviceSettingsAuditTest(TestCase):
    def setUp(self):
        self.owner_user, self.owner_token = _make("wx_owner_a", "user")
        self.o1 = _owner("3-1-7-702", "c5d29c52a237ade5")
        _bind(self.owner_user, self.o1)

    def _payload(self, **over):
        p = dict(
            request_id="batch-uuid-1",
            specific_part="3-1-7-702",
            screen_mac="c5d29c52a237ade5",
            device_sn="22154",
            result="success",
            items=[{"attr_tag": "mode", "attr_value": "cold", "old_value": "hot"}],
        )
        p.update(over)
        return p

    def test_audit_creates_record_with_channel(self):
        resp = _client(self.owner_token).post(AUDIT_URL, self._payload(), format='json')
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.data['recorded'], 1)
        rec = PLCWriteRecord.objects.get(param_name="mode")
        self.assertEqual(rec.channel, 'screen-mqtt')
        self.assertEqual(rec.new_value, 'cold')
        self.assertEqual(rec.old_value, 'hot')
        self.assertEqual(rec.operator, 'wx_owner_a')
        self.assertEqual(rec.status, 'success')
        self.assertEqual(rec.batch_request_id, 'batch-uuid-1')

    def test_audit_multi_items(self):
        items = [
            {"attr_tag": "mode", "attr_value": "cold"},
            {"attr_tag": "energy_supply_mode", "attr_value": "cold"},
        ]
        resp = _client(self.owner_token).post(AUDIT_URL, self._payload(items=items), format='json')
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(PLCWriteRecord.objects.filter(channel='screen-mqtt').count(), 2)

    def test_audit_cross_tenant_screenmac_forbidden(self):
        resp = _client(self.owner_token).post(
            AUDIT_URL, self._payload(screen_mac="ffffffffffffffff"), format='json')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(PLCWriteRecord.objects.count(), 0)

    def test_audit_non_whitelist_attr_rejected(self):
        resp = _client(self.owner_token).post(
            AUDIT_URL, self._payload(items=[{"attr_tag": "temp", "attr_value": "26"}]),
            format='json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(PLCWriteRecord.objects.count(), 0)

    def test_audit_missing_items_rejected(self):
        resp = _client(self.owner_token).post(
            AUDIT_URL, self._payload(items=[]), format='json')
        self.assertEqual(resp.status_code, 400)

    def test_audit_result_timeout_maps_status(self):
        resp = _client(self.owner_token).post(
            AUDIT_URL, self._payload(result="timeout"), format='json')
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(PLCWriteRecord.objects.get(param_name="mode").status, 'timeout')

    def test_audit_operator_forbidden(self):
        _u, tok = _make("op1", "operator")
        self.assertEqual(_client(tok).post(AUDIT_URL, self._payload(), format='json').status_code, 403)


# ===========================================================================
# 回归：web 路径 PLCWriteRecord channel 默认 's7'（C-01）
# ===========================================================================

@tag('integration')
class ChannelDefaultRegressionTest(TestCase):
    def test_plcwriterecord_default_channel_s7(self):
        rec = PLCWriteRecord.objects.create(
            request_id="r-1", specific_part="3-1-7-702",
            param_name="main_thermostat_temp_setting", old_value="260",
            new_value="265", operator="op1", status="pending",
        )
        self.assertEqual(rec.channel, 's7')
