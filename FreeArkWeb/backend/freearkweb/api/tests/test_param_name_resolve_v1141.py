"""
test_param_name_resolve_v1141.py — 中文→param_name 逆向翻译的户型正确性（v1.14.1）

背景：v1.14.0 把**展示**路径的面板房间标签改成按户型查 PANEL_ROOM_TABLE 实测真值，
但 views_device_settings._resolve_param_name()（LLM/agent 传中文时的兜底翻译层）
当时漏改，仍拿中文往 DeviceConfig.sub_type_display 这张全局静态表上匹配。
该静态表只有四房分支、且四房分支把主卧与书房标反，后果：
  · 四房户说"主卧设定温度" → 译成 children_room_temp_setting（实为书房）
  · 三房户三个房间标签全错，且会匹配到该户根本不存在的 panel_fourth_children

本测试锁住修复后的行为：翻译结果必须与 PANEL_ROOM_TABLE 实测真值一致。
一旦有人把 _resolve_param_name 改回读静态 sub_type_display，这里会红。

分三组：
  A. 四房逆向翻译（主卧↔书房不再互换）
  B. 三房逆向翻译（三个房间全对 + 不会译到不存在的 panel_fourth_children）
  C. 安全边界（户型未知时不崩、白名单不放宽、无关词仍被拒）

运行：
  FREEARK_POC_MOCK=1 PYTHONUTF8=1 python manage.py test \
      api.tests.test_param_name_resolve_v1141 --settings=freearkweb.test_settings
"""

from django.test import TestCase, tag

from api.models import OwnerInfo, DeviceFloor, DeviceRoom, DeviceNode, DeviceConfig
from api.management.commands.seed_device_config import HVAC_PARAM_CONFIGS
from api.utils_room_filter import invalidate_room_filter_cache
from api.views_device_settings import _resolve_param_name, _is_writable

PANEL_PRODUCT_CODE = '120003'
FOUR_ROOM_PANELS = ['书房', '次卧', '主卧', '儿童房']
THREE_ROOM_PANELS = ['主卧', '次卧', '儿童房']


def _seed_device_configs():
    """按 seed_device_config 的真实清单建 DeviceConfig（翻译层的候选集来源）。"""
    DeviceConfig.objects.bulk_create([
        DeviceConfig(
            param_name=c['param_name'], display_name=c['display_name'],
            group=c['group'], group_display=c['group_display'],
            sub_type=c['sub_type'], sub_type_display=c['sub_type_display'],
            is_active=c.get('is_active', True),
        )
        for c in HVAC_PARAM_CONFIGS
    ])


def _build_owner(specific_part: str, panel_rooms: list) -> OwnerInfo:
    """造一户：panel_rooms 每间挂一块温控面板，另加客厅主温控（判户型看面板数）。"""
    owner = OwnerInfo.objects.create(
        specific_part=specific_part, building='3', unit='1',
        room_number=specific_part.split('-')[-1], unique_id=f'mac-{specific_part}',
    )
    floor = DeviceFloor.objects.create(owner=owner, floor_no=1, floor_name='1')
    sn = 22550
    for name in panel_rooms:
        room = DeviceRoom.objects.create(
            floor=floor, room_name=name, ori_room_name=name, room_type=5,
        )
        sn += 1
        DeviceNode.objects.create(
            room=room, device_sn=sn, device_name='温控面板',
            system_flag=1, product_code=PANEL_PRODUCT_CODE, category_code=12,
        )
    room = DeviceRoom.objects.create(
        floor=floor, room_name='客厅', ori_room_name='客厅', room_type=1,
    )
    DeviceNode.objects.create(
        room=room, device_sn=sn + 1, device_name='主温控',
        system_flag=2, product_code='260001', category_code=26,
    )
    invalidate_room_filter_cache(specific_part)
    return owner


@tag('integration')
class FourRoomResolveTests(TestCase):
    """A 组：四房——offset 1395=书房、1515=主卧（生产标定真值）。"""

    SP = '3-1-7-702'

    def setUp(self):
        _seed_device_configs()
        _build_owner(self.SP, FOUR_ROOM_PANELS)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_master_bedroom_maps_to_study_room_prefix(self):
        """四房「主卧」→ study_room_*（PLC offset 1515），不是 children_room_*。"""
        self.assertEqual(
            _resolve_param_name('主卧设定温度', self.SP), 'study_room_temp_setting')
        self.assertEqual(
            _resolve_param_name('主卧开关', self.SP), 'study_room_switch')

    def test_study_maps_to_children_room_prefix(self):
        """四房「书房」→ children_room_*（PLC offset 1395），不是 study_room_*。"""
        self.assertEqual(
            _resolve_param_name('书房设定温度', self.SP), 'children_room_temp_setting')
        self.assertEqual(
            _resolve_param_name('书房开关', self.SP), 'children_room_switch')

    def test_secondary_bedroom_and_children_room_unchanged(self):
        """四房次卧/儿童房本就正确，回归护栏。"""
        self.assertEqual(
            _resolve_param_name('次卧设定温度', self.SP), 'bedroom_temp_setting')
        self.assertEqual(
            _resolve_param_name('儿童房开关', self.SP),
            'fourth_children_room_switch')


@tag('integration')
class ThreeRoomResolveTests(TestCase):
    """B 组：三房——静态表只有四房分支，三个房间修复前全错。"""

    SP = '9-1-10-1002'

    def setUp(self):
        _seed_device_configs()
        _build_owner(self.SP, THREE_ROOM_PANELS)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_three_room_labels_follow_calibration(self):
        cases = {
            '主卧设定温度':  'bedroom_temp_setting',        # offset 1455
            '主卧开关':      'bedroom_switch',
            '次卧设定温度':  'study_room_temp_setting',     # offset 1515
            '次卧开关':      'study_room_switch',
            '儿童房设定温度': 'children_room_temp_setting',  # offset 1395
            '儿童房开关':    'children_room_switch',
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(_resolve_param_name(phrase, self.SP), expected)

    def test_never_resolves_to_panel_absent_in_this_house(self):
        """三房没有 panel_fourth_children，任何说法都不该译到它的参数上。"""
        for phrase in ('儿童房开关', '儿童房设定温度', '主卧开关', '书房开关'):
            with self.subTest(phrase=phrase):
                self.assertFalse(
                    _resolve_param_name(phrase, self.SP).startswith(
                        'fourth_children_room'),
                    '三房不应译到四房专属面板参数',
                )


@tag('integration')
class ResolveSafetyTests(TestCase):
    """C 组：安全边界——翻译层不得放宽白名单、不得因户型未知而崩。"""

    SP_UNKNOWN = '1-1-1-101'

    def setUp(self):
        _seed_device_configs()

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_already_valid_param_name_passes_through(self):
        self.assertEqual(
            _resolve_param_name('study_room_switch', self.SP_UNKNOWN),
            'study_room_switch')

    def test_unknown_house_type_does_not_raise(self):
        """设备树未同步（无 DeviceFloor）时不抛异常，走原兜底路径。"""
        result = _resolve_param_name('主卧开关', self.SP_UNKNOWN)
        self.assertIsInstance(result, str)

    def test_never_returns_unwritable_param(self):
        """无论输入什么，返回值要么原样，要么是可写参数——白名单不被绕过。"""
        for phrase in ('主卧温度', '客厅湿度', '凝露提醒', '通讯故障', '随便什么词'):
            with self.subTest(phrase=phrase):
                out = _resolve_param_name(phrase, self.SP_UNKNOWN)
                self.assertTrue(
                    out == phrase or _is_writable(out),
                    f'翻译层返回了不可写参数 {out}',
                )
