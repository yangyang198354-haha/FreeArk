"""
v1.11.2 miniapp 温控面板房间名显示测试套件

覆盖：
  [unit]        PANEL_DISPLAY_MAP 常量正确性（TC-UNIT-001 / TC-UNIT-002 / TC-UNIT-003）
  [integration] panel_* sub_type display 字段覆写正确性（TC-INTG-001 ~ TC-INTG-008）

关联需求：
  US-01 (AC-01-01, AC-01-02, AC-01-03)
  US-02 (AC-02-01, AC-02-02, AC-02-03, AC-02-04)
  US-03 (AC-03-01, AC-03-02)

运行：
    cd FreeArkWeb/backend/freearkweb
    PYTHONUTF8=1 FREEARK_POC_MOCK=1 python manage.py test \\
        api.tests.test_miniapp_owner_v1120 \\
        --settings=freearkweb.test_settings --verbosity=2
"""

from django.test import TestCase, tag
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import (
    CustomUser, OwnerInfo, OwnerUserBinding,
    PLCLatestData, DeviceConfig, DeviceFloor, DeviceRoom,
)
from api.views_miniapp_device_settings import PANEL_DISPLAY_MAP
from api.utils_room_filter import invalidate_room_filter_cache

REALTIME_URL = '/api/miniapp/owner/realtime-params/'


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


def _make_device_config(group, sub_type, param_name, group_display='暖通', sub_type_display='测试'):
    return DeviceConfig.objects.create(
        group=group, sub_type=sub_type, param_name=param_name,
        display_name=f'显示-{param_name}', group_display=group_display,
        sub_type_display=sub_type_display, is_active=True,
    )


def _make_plc_data(specific_part, param_name, value=100):
    return PLCLatestData.objects.create(
        specific_part=specific_part, param_name=param_name, value=value,
    )


def _setup_three_room_floors(owner):
    """三房户型：次卧 / 主卧 / 儿童房（无书房）。
    触发: panel_study_room（次卧）, panel_bedroom（主卧）, panel_children_room（儿童房/主卧）
    不触发: panel_fourth_children（需书房）
    """
    floor = DeviceFloor.objects.create(owner=owner, floor_no=1, floor_name='一层')
    DeviceRoom.objects.create(floor=floor, room_name='次卧', ori_room_name='次卧', room_type=1)
    DeviceRoom.objects.create(floor=floor, room_name='主卧', ori_room_name='主卧', room_type=1)
    DeviceRoom.objects.create(floor=floor, room_name='儿童房', ori_room_name='儿童房', room_type=1)
    return floor


def _setup_four_room_floors(owner):
    """四房户型：书房 / 次卧 / 主卧 / 儿童房。
    触发: panel_study_room（书房/次卧）, panel_bedroom（主卧）,
          panel_children_room（儿童房/主卧）, panel_fourth_children（书房+儿童房）
    """
    floor = DeviceFloor.objects.create(owner=owner, floor_no=1, floor_name='一层')
    DeviceRoom.objects.create(floor=floor, room_name='书房', ori_room_name='书房', room_type=1)
    DeviceRoom.objects.create(floor=floor, room_name='次卧', ori_room_name='次卧', room_type=1)
    DeviceRoom.objects.create(floor=floor, room_name='主卧', ori_room_name='主卧', room_type=1)
    DeviceRoom.objects.create(floor=floor, room_name='儿童房', ori_room_name='儿童房', room_type=1)
    return floor


def _extract_sub_display(response_data, sub_key):
    """从 API 响应 data 中提取指定 sub_type 的 display 值（跨所有 group 查找）。"""
    for group_val in response_data.values():
        if sub_key in group_val.get('sub_types', {}):
            return group_val['sub_types'][sub_key]['display']
    return None


# ===========================================================================
# 单元测试：PANEL_DISPLAY_MAP 常量正确性
# ===========================================================================

@tag('unit')
class PanelDisplayMapConstantTest(TestCase):
    """
    TC-UNIT-001 / TC-UNIT-002 / TC-UNIT-003
    直接 import PANEL_DISPLAY_MAP，验证常量的正确性与 fallback 行为。
    不需要数据库访问。
    """

    # ── TC-UNIT-001 ────────────────────────────────────────────────────────────
    def test_tc_unit_001_constant_existence_and_correctness(self):
        """TC-UNIT-001: PANEL_DISPLAY_MAP 共 4 个键，每个映射值正确。
        关联 US: US-02 / 关联 AC: AC-02-01, AC-02-02, AC-02-03, AC-02-04
        """
        # 键数量正确
        self.assertEqual(
            len(PANEL_DISPLAY_MAP), 4,
            f"PANEL_DISPLAY_MAP 应有 4 个键，实际 {len(PANEL_DISPLAY_MAP)} 个: {list(PANEL_DISPLAY_MAP.keys())}",
        )

        # 四个映射值正确
        self.assertEqual(PANEL_DISPLAY_MAP['panel_study_room'], '书房')
        self.assertEqual(PANEL_DISPLAY_MAP['panel_bedroom'], '次卧')
        self.assertEqual(PANEL_DISPLAY_MAP['panel_children_room'], '主卧')
        self.assertEqual(PANEL_DISPLAY_MAP['panel_fourth_children'], '儿童房')

        # 系统级 sub_type 不在 map 中
        self.assertNotIn('main_thermostat', PANEL_DISPLAY_MAP)
        self.assertNotIn('fresh_air', PANEL_DISPLAY_MAP)
        self.assertNotIn('energy_meter', PANEL_DISPLAY_MAP)

    # ── TC-UNIT-002 ────────────────────────────────────────────────────────────
    def test_tc_unit_002_counterintuitive_mapping_assertions(self):
        """TC-UNIT-002: 反直觉映射专项断言（最高风险防串房）。
        panel_bedroom 必须是'次卧'而非'主卧'；
        panel_children_room 必须是'主卧'而非'儿童房'。
        关联 US: US-02 / 关联 AC: AC-02-02, AC-02-03
        """
        # panel_bedroom → 次卧（非主卧）—— 最高风险串房场景
        self.assertEqual(
            PANEL_DISPLAY_MAP['panel_bedroom'], '次卧',
            "panel_bedroom 映射值必须是'次卧'（反直觉，代码名易误读为主卧）",
        )
        self.assertNotEqual(
            PANEL_DISPLAY_MAP['panel_bedroom'], '主卧',
            "panel_bedroom 映射值不得为'主卧'（串房防御 AC-02-02）",
        )

        # panel_children_room → 主卧（非儿童房）—— 第二高风险串房场景
        self.assertEqual(
            PANEL_DISPLAY_MAP['panel_children_room'], '主卧',
            "panel_children_room 映射值必须是'主卧'（反直觉，代码名含 children_room）",
        )
        self.assertNotEqual(
            PANEL_DISPLAY_MAP['panel_children_room'], '儿童房',
            "panel_children_room 映射值不得为'儿童房'（串房防御 AC-02-03）",
        )

    # ── TC-UNIT-003 ────────────────────────────────────────────────────────────
    def test_tc_unit_003_fallback_behavior_for_non_panel_keys(self):
        """TC-UNIT-003: PANEL_DISPLAY_MAP.get() fallback 行为——非 panel 键返回 fallback 值。
        关联 US: US-03 / 关联 AC: AC-03-01, AC-03-02
        """
        # 系统级 sub_type 不在 map，.get() 返回提供的 fallback 值
        self.assertEqual(PANEL_DISPLAY_MAP.get('main_thermostat', '主温控'), '主温控')
        self.assertEqual(PANEL_DISPLAY_MAP.get('fresh_air', '新风机组'), '新风机组')
        self.assertEqual(PANEL_DISPLAY_MAP.get('energy_meter', '能耗表'), '能耗表')

        # 确认这些键确实不在 map 中（而非 map 中值恰好与 fallback 相同）
        self.assertNotIn('main_thermostat', PANEL_DISPLAY_MAP)
        self.assertNotIn('fresh_air', PANEL_DISPLAY_MAP)
        self.assertNotIn('energy_meter', PANEL_DISPLAY_MAP)

        # 未知键也返回 fallback
        self.assertEqual(PANEL_DISPLAY_MAP.get('unknown_sub_type', 'DB原值'), 'DB原值')


# ===========================================================================
# 集成测试：panel_* sub_type display 字段覆写
# ===========================================================================

@tag('integration', 'panel_display')
class TC_INTG_001_PanelStudyRoomDisplayTest(TestCase):
    """
    TC-INTG-001: panel_study_room → display='书房'
    关联 US: US-01, US-02 / 关联 AC: AC-02-01
    使用三房户型 data setup（次卧/主卧/儿童房），次卧关键词触发 panel_study_room。
    """

    def setUp(self):
        invalidate_room_filter_cache()
        sp = 'TI01-1-1-101'
        self.sp = sp
        self.owner = _make_owner(sp, unique_id='mac_ti01')
        self.user, self.tok = _make_user('ti01_user')
        _bind(self.user, self.owner)
        _setup_three_room_floors(self.owner)
        # panel_study_room 的 DeviceConfig + PLCLatestData（DB 中含'-温控面板'后缀）
        _make_device_config('hvac', 'panel_study_room', 'ti01_study_temp',
                            sub_type_display='书房-温控面板')
        _make_plc_data(sp, 'ti01_study_temp', 220)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_panel_study_room_display_is_shufang(self):
        """panel_study_room display 应为'书房'，不含'-温控面板'后缀。
        关联 AC: AC-02-01
        """
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': self.sp})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']

        sub_display = _extract_sub_display(data, 'panel_study_room')
        self.assertIsNotNone(sub_display,
                             "panel_study_room 应出现在响应中（三房户型次卧触发）")
        self.assertEqual(sub_display, '书房',
                         f"panel_study_room display 期望'书房'，实际'{sub_display}'")
        self.assertNotIn('-温控面板', sub_display,
                         "display 不得含'-温控面板'后缀（OQ-04 已确认去除后缀）")


@tag('integration', 'panel_display')
class TC_INTG_002_PanelBedroomDisplayTest(TestCase):
    """
    TC-INTG-002: panel_bedroom → display='次卧'（最高风险防串房）
    关联 US: US-02 / 关联 AC: AC-02-02
    使用三房户型 data setup，主卧关键词触发 panel_bedroom。
    """

    def setUp(self):
        invalidate_room_filter_cache()
        sp = 'TI02-1-1-101'
        self.sp = sp
        self.owner = _make_owner(sp, unique_id='mac_ti02')
        self.user, self.tok = _make_user('ti02_user')
        _bind(self.user, self.owner)
        _setup_three_room_floors(self.owner)
        _make_device_config('hvac', 'panel_bedroom', 'ti02_bedroom_temp',
                            sub_type_display='次卧-温控面板')
        _make_plc_data(sp, 'ti02_bedroom_temp', 215)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_panel_bedroom_display_is_ciwu_not_zhuwu(self):
        """panel_bedroom display 应为'次卧'，且明确不为'主卧'（最高风险串房场景）。
        关联 AC: AC-02-02
        """
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': self.sp})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']

        sub_display = _extract_sub_display(data, 'panel_bedroom')
        self.assertIsNotNone(sub_display,
                             "panel_bedroom 应出现在响应中（三房户型主卧触发）")
        self.assertEqual(sub_display, '次卧',
                         f"panel_bedroom display 期望'次卧'，实际'{sub_display}'")
        # 串房防御断言（AC-02-02 核心）
        self.assertNotEqual(sub_display, '主卧',
                            "BLOCKER: panel_bedroom display 不得为'主卧'（发生串房！）")


@tag('integration', 'panel_display')
class TC_INTG_003_PanelChildrenRoomDisplayTest(TestCase):
    """
    TC-INTG-003: panel_children_room → display='主卧'（第二高风险防串房）
    关联 US: US-02 / 关联 AC: AC-02-03
    使用三房户型 data setup，儿童房/主卧关键词触发 panel_children_room。
    """

    def setUp(self):
        invalidate_room_filter_cache()
        sp = 'TI03-1-1-101'
        self.sp = sp
        self.owner = _make_owner(sp, unique_id='mac_ti03')
        self.user, self.tok = _make_user('ti03_user')
        _bind(self.user, self.owner)
        _setup_three_room_floors(self.owner)
        _make_device_config('hvac', 'panel_children_room', 'ti03_children_temp',
                            sub_type_display='主卧-温控面板')
        _make_plc_data(sp, 'ti03_children_temp', 210)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_panel_children_room_display_is_zhuwu_not_ertongfang(self):
        """panel_children_room display 应为'主卧'，且明确不为'儿童房'（第二高风险串房场景）。
        关联 AC: AC-02-03
        """
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': self.sp})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']

        sub_display = _extract_sub_display(data, 'panel_children_room')
        self.assertIsNotNone(sub_display,
                             "panel_children_room 应出现在响应中（三房户型儿童房/主卧触发）")
        self.assertEqual(sub_display, '主卧',
                         f"panel_children_room display 期望'主卧'，实际'{sub_display}'")
        # 串房防御断言（AC-02-03 核心）
        self.assertNotEqual(sub_display, '儿童房',
                            "BLOCKER: panel_children_room display 不得为'儿童房'（发生串房！）")


@tag('integration', 'panel_display')
class TC_INTG_004_PanelFourthChildrenDisplayTest(TestCase):
    """
    TC-INTG-004: panel_fourth_children → display='儿童房'
    关联 US: US-02 / 关联 AC: AC-02-04
    使用四房户型 data setup（书房+儿童房，触发 panel_fourth_children）。
    """

    def setUp(self):
        invalidate_room_filter_cache()
        sp = 'TI04-1-1-101'
        self.sp = sp
        self.owner = _make_owner(sp, unique_id='mac_ti04')
        self.user, self.tok = _make_user('ti04_user')
        _bind(self.user, self.owner)
        _setup_four_room_floors(self.owner)
        _make_device_config('hvac', 'panel_fourth_children', 'ti04_fourth_temp',
                            sub_type_display='儿童房-温控面板')
        _make_plc_data(sp, 'ti04_fourth_temp', 205)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_panel_fourth_children_display_is_ertongfang(self):
        """panel_fourth_children display 应为'儿童房'（四房户型专属）。
        关联 AC: AC-02-04
        """
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': self.sp})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']

        sub_display = _extract_sub_display(data, 'panel_fourth_children')
        self.assertIsNotNone(sub_display,
                             "panel_fourth_children 应出现在响应中（四房户型书房+儿童房触发）")
        self.assertEqual(sub_display, '儿童房',
                         f"panel_fourth_children display 期望'儿童房'，实际'{sub_display}'")


@tag('integration', 'panel_display')
class TC_INTG_005_MainThermostatFallbackTest(TestCase):
    """
    TC-INTG-005: main_thermostat fallback——display 保持 DB 原值，不被 PANEL_DISPLAY_MAP 覆写。
    关联 US: US-03 / 关联 AC: AC-03-01
    系统级 sub_type，始终出现在 available_sub_types，无需 DeviceFloor/DeviceRoom。
    """

    def setUp(self):
        invalidate_room_filter_cache()
        sp = 'TI05-1-1-101'
        self.sp = sp
        self.owner = _make_owner(sp, unique_id='mac_ti05')
        self.user, self.tok = _make_user('ti05_user')
        _bind(self.user, self.owner)
        # 不创建 DeviceFloor/DeviceRoom，系统级 sub_type 不受影响
        _make_device_config('hvac', 'main_thermostat', 'ti05_main_temp',
                            sub_type_display='主温控')
        _make_plc_data(sp, 'ti05_main_temp', 250)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_main_thermostat_display_is_db_value(self):
        """main_thermostat display 应保持 DB 原值'主温控'，不被 PANEL_DISPLAY_MAP 覆写。
        关联 AC: AC-03-01
        """
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': self.sp})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']

        sub_display = _extract_sub_display(data, 'main_thermostat')
        self.assertIsNotNone(sub_display, "main_thermostat 应出现在响应中（系统级 sub_type 始终可用）")
        self.assertEqual(sub_display, '主温控',
                         f"main_thermostat display 期望 DB 原值'主温控'，实际'{sub_display}'")


@tag('integration', 'panel_display')
class TC_INTG_006_FreshAirFallbackTest(TestCase):
    """
    TC-INTG-006: fresh_air fallback——display 保持 DB 原值'新风机组'，不被 PANEL_DISPLAY_MAP 覆写。
    关联 US: US-03 / 关联 AC: AC-03-02
    系统级 sub_type，始终出现在 available_sub_types，无需 DeviceFloor/DeviceRoom。
    """

    def setUp(self):
        invalidate_room_filter_cache()
        sp = 'TI06-1-1-101'
        self.sp = sp
        self.owner = _make_owner(sp, unique_id='mac_ti06')
        self.user, self.tok = _make_user('ti06_user')
        _bind(self.user, self.owner)
        _make_device_config('hvac', 'fresh_air', 'ti06_fresh_temp',
                            sub_type_display='新风机组')
        _make_plc_data(sp, 'ti06_fresh_temp', 200)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_fresh_air_display_is_db_value(self):
        """fresh_air display 应保持 DB 原值'新风机组'，不被 PANEL_DISPLAY_MAP 覆写。
        关联 AC: AC-03-02
        """
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': self.sp})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']

        sub_display = _extract_sub_display(data, 'fresh_air')
        self.assertIsNotNone(sub_display, "fresh_air 应出现在响应中（系统级 sub_type 始终可用）")
        self.assertEqual(sub_display, '新风机组',
                         f"fresh_air display 期望 DB 原值'新风机组'，实际'{sub_display}'")


@tag('integration', 'panel_display')
class TC_INTG_007_FourRoomAllPanelsDisplayTest(TestCase):
    """
    TC-INTG-007: 四房户型同时出现 4 个 panel sub_type，各自 display 正确且互不重复。
    关联 US: US-01, US-02 / 关联 AC: AC-01-02, AC-02-01, AC-02-02, AC-02-03, AC-02-04
    四房户型 data setup（书房/次卧/主卧/儿童房）。
    """

    def setUp(self):
        invalidate_room_filter_cache()
        sp = 'TI07-1-1-101'
        self.sp = sp
        self.owner = _make_owner(sp, unique_id='mac_ti07')
        self.user, self.tok = _make_user('ti07_user')
        _bind(self.user, self.owner)
        _setup_four_room_floors(self.owner)
        # 4 个 DeviceConfig（sub_type_display 均含"-温控面板"后缀，用于验证覆写）
        _make_device_config('hvac', 'panel_study_room', 'ti07_study',
                            sub_type_display='书房-温控面板')
        _make_device_config('hvac', 'panel_bedroom', 'ti07_bedroom',
                            sub_type_display='次卧-温控面板')
        _make_device_config('hvac', 'panel_children_room', 'ti07_children',
                            sub_type_display='主卧-温控面板')
        _make_device_config('hvac', 'panel_fourth_children', 'ti07_fourth',
                            sub_type_display='儿童房-温控面板')
        # 4 个 PLCLatestData（保证 sub_type 不被视图清理掉）
        _make_plc_data(sp, 'ti07_study', 221)
        _make_plc_data(sp, 'ti07_bedroom', 222)
        _make_plc_data(sp, 'ti07_children', 223)
        _make_plc_data(sp, 'ti07_fourth', 224)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_all_four_panels_display_correct_and_distinct(self):
        """四房户型：4 个 panel sub_type 的 display 均正确，且互不相同（完整防串房验证）。
        关联 AC: AC-01-02, AC-02-01~AC-02-04
        """
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': self.sp})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']

        # 收集 4 个 panel 的 display 值
        panel_keys = ['panel_study_room', 'panel_bedroom',
                      'panel_children_room', 'panel_fourth_children']
        displays = {}
        for sub_key in panel_keys:
            display = _extract_sub_display(data, sub_key)
            if display is not None:
                displays[sub_key] = display

        # 验证 4 个 sub_type 均出现（全覆盖）
        self.assertIn('panel_study_room', displays,
                      "四房户型应含 panel_study_room")
        self.assertIn('panel_bedroom', displays,
                      "四房户型应含 panel_bedroom")
        self.assertIn('panel_children_room', displays,
                      "四房户型应含 panel_children_room")
        self.assertIn('panel_fourth_children', displays,
                      "四房户型应含 panel_fourth_children")

        # 验证各 display 值正确
        self.assertEqual(displays['panel_study_room'], '书房',
                         f"panel_study_room display 期望'书房'，实际'{displays.get('panel_study_room')}'")
        self.assertEqual(displays['panel_bedroom'], '次卧',
                         f"panel_bedroom display 期望'次卧'，实际'{displays.get('panel_bedroom')}'")
        self.assertEqual(displays['panel_children_room'], '主卧',
                         f"panel_children_room display 期望'主卧'，实际'{displays.get('panel_children_room')}'")
        self.assertEqual(displays['panel_fourth_children'], '儿童房',
                         f"panel_fourth_children display 期望'儿童房'，实际'{displays.get('panel_fourth_children')}'")

        # 完整防串房验证：4 个 display 值互不相同
        all_displays = list(displays.values())
        self.assertEqual(
            len(all_displays), len(set(all_displays)),
            f"BLOCKER: 4 个 panel 的 display 值发生重复（串房）！当前映射: {displays}",
        )


@tag('integration', 'panel_display')
class TC_INTG_008_ThreeRoomNoPanelFourthChildrenTest(TestCase):
    """
    TC-INTG-008: 三房户型不含 panel_fourth_children（无书房关键词，不触发四房条件）。
    关联 US: US-01 / 关联 AC: AC-01-03
    三房户型 data setup（次卧/主卧/儿童房），三个 panel sub_type 正常出现。
    """

    def setUp(self):
        invalidate_room_filter_cache()
        sp = 'TI08-1-1-101'
        self.sp = sp
        self.owner = _make_owner(sp, unique_id='mac_ti08')
        self.user, self.tok = _make_user('ti08_user')
        _bind(self.user, self.owner)
        _setup_three_room_floors(self.owner)
        # 三房的三个 panel sub_type（不创建 panel_fourth_children 的 config）
        _make_device_config('hvac', 'panel_study_room', 'ti08_study',
                            sub_type_display='书房-温控面板')
        _make_device_config('hvac', 'panel_bedroom', 'ti08_bedroom',
                            sub_type_display='次卧-温控面板')
        _make_device_config('hvac', 'panel_children_room', 'ti08_children',
                            sub_type_display='主卧-温控面板')
        _make_plc_data(sp, 'ti08_study', 210)
        _make_plc_data(sp, 'ti08_bedroom', 211)
        _make_plc_data(sp, 'ti08_children', 212)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_three_room_has_no_panel_fourth_children(self):
        """三房户型（无书房）不应返回 panel_fourth_children sub_type。
        同时验证三房的 3 个 panel sub_type 均正确出现。
        关联 AC: AC-01-03
        """
        r = _client(self.tok).get(REALTIME_URL, {'specific_part': self.sp})
        self.assertEqual(r.status_code, 200)
        data = r.data['data']

        # 核心断言：panel_fourth_children 不应出现
        for group_val in data.values():
            self.assertNotIn(
                'panel_fourth_children',
                group_val.get('sub_types', {}),
                "三房户型（无书房）不应含 panel_fourth_children sub_type（AC-01-03）",
            )

        # 附加验证：三房的 3 个 panel sub_type 均正确出现且 display 正确
        displays = {
            'panel_study_room': _extract_sub_display(data, 'panel_study_room'),
            'panel_bedroom': _extract_sub_display(data, 'panel_bedroom'),
            'panel_children_room': _extract_sub_display(data, 'panel_children_room'),
        }
        self.assertEqual(displays['panel_study_room'], '书房',
                         f"panel_study_room display 期望'书房'，实际'{displays['panel_study_room']}'")
        self.assertEqual(displays['panel_bedroom'], '次卧',
                         f"panel_bedroom display 期望'次卧'，实际'{displays['panel_bedroom']}'")
        self.assertEqual(displays['panel_children_room'], '主卧',
                         f"panel_children_room display 期望'主卧'，实际'{displays['panel_children_room']}'")
