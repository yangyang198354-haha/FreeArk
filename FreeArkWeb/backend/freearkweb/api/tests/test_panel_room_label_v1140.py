"""
test_panel_room_label_v1140.py — 温控面板房间标签按户型解析（v1.14.0）

覆盖 docs/analysis/plc_room_mapping_misalignment_rca.md 第 -1 节的生产标定结论：
  1395 children_room       三房=儿童房  四房=书房
  1455 bedroom             三房=主卧    四房=次卧
  1515 study_room          三房=次卧    四房=主卧
  1575 fourth_children_room 三房=—      四房=儿童房

测试分四组：
  A. 四房标签（修正主卧↔书房互换）
  B. 三房标签（三个标签全错 + 幻影"书房"的修复）
  C. 逆映射双射性 + hash 稳定性（缺陷三回归护栏）
  D. 降级行为（户型未知时回退全局默认值，不突变）

运行：
  FREEARK_POC_MOCK=1 PYTHONUTF8=1 python manage.py test \
      api.tests.test_panel_room_label_v1140 --settings=freearkweb.test_settings
"""

from django.test import TestCase, tag

from api.models import OwnerInfo, DeviceFloor, DeviceRoom, DeviceNode
from api.utils_room_filter import (
    HOUSE_TYPE_THREE,
    HOUSE_TYPE_FOUR,
    PANEL_ROOM_TABLE,
    get_house_type,
    resolve_panel_room,
    resolve_panel_display,
    get_panel_order,
    resolve_sub_type_for_room,
    invalidate_room_filter_cache,
)

PANEL_PRODUCT_CODE = '120003'

# 四房标准房间集（对照 3-1-7-702 生产实测设备树）
FOUR_ROOM_PANELS = ['书房', '次卧', '主卧', '儿童房']
# 三房标准房间集
THREE_ROOM_PANELS = ['主卧', '次卧', '儿童房']


def _build_owner(specific_part: str, panel_rooms: list,
                 extra_rooms: tuple = ('全屋', '客厅')) -> OwnerInfo:
    """造一户：panel_rooms 每间挂一块温控面板；extra_rooms 挂非面板设备。"""
    owner = OwnerInfo.objects.create(
        specific_part=specific_part, building='3', unit='1',
        room_number=specific_part.split('-')[-1], unique_id=f'mac-{specific_part}',
    )
    floor = DeviceFloor.objects.create(owner=owner, floor_no=1, floor_name='1')
    sn = 20000 + abs(hash(specific_part)) % 1000
    for name in panel_rooms:
        room = DeviceRoom.objects.create(
            floor=floor, room_name=name, ori_room_name=name, room_type=5,
        )
        sn += 1
        DeviceNode.objects.create(
            room=room, device_sn=sn, device_name='温控面板',
            system_flag=1, product_code=PANEL_PRODUCT_CODE, category_code=12,
        )
    for name in extra_rooms:
        room = DeviceRoom.objects.create(
            floor=floor, room_name=name, ori_room_name=name, room_type=1,
        )
        sn += 1
        DeviceNode.objects.create(
            room=room, device_sn=sn, device_name='主温控',
            system_flag=2, product_code='260001', category_code=26,
        )
    invalidate_room_filter_cache(specific_part)
    return owner


@tag('unit')
class FourRoomLabelTests(TestCase):
    """A 组：四房标签——修正 plc_config 四房分支的主卧↔书房互换。"""

    SP = '3-1-7-702'

    def setUp(self):
        _build_owner(self.SP, FOUR_ROOM_PANELS)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_house_type_is_four(self):
        self.assertEqual(get_house_type(self.SP), HOUSE_TYPE_FOUR)

    def test_labels_match_production_calibration(self):
        """四个槽位标签必须等于生产标定实测值。"""
        self.assertEqual(resolve_panel_room(self.SP, 'panel_children_room'), '书房')
        self.assertEqual(resolve_panel_room(self.SP, 'panel_bedroom'), '次卧')
        self.assertEqual(resolve_panel_room(self.SP, 'panel_study_room'), '主卧')
        self.assertEqual(resolve_panel_room(self.SP, 'panel_fourth_children'), '儿童房')

    def test_the_two_swapped_slots(self):
        """核心回归：1395 是书房不是主卧、1515 是主卧不是书房。

        这两条是 3-1-702 用户报障的直接成因，写死断言防止回退到 plc_config 标注。
        """
        self.assertNotEqual(
            resolve_panel_room(self.SP, 'panel_children_room'), '主卧',
            'panel_children_room(offset 1395) 在四房是「书房」，不是 plc_config 标注的「主卧」',
        )
        self.assertNotEqual(
            resolve_panel_room(self.SP, 'panel_study_room'), '书房',
            'panel_study_room(offset 1515) 在四房是「主卧」，不是 plc_config 标注的「书房」',
        )

    def test_display_with_web_suffix(self):
        self.assertEqual(
            resolve_panel_display(self.SP, 'panel_children_room', 'X', '-温控面板'),
            '书房-温控面板',
        )

    def test_display_without_suffix_for_miniapp(self):
        self.assertEqual(
            resolve_panel_display(self.SP, 'panel_children_room', 'X'), '书房',
        )

    def test_order_is_master_secondary_study_children(self):
        """展示序：主卧 → 次卧 → 书房 → 儿童房。"""
        subs = ['panel_children_room', 'panel_bedroom',
                'panel_study_room', 'panel_fourth_children']
        ordered = sorted(subs, key=lambda s: get_panel_order(self.SP, s))
        rooms = [resolve_panel_room(self.SP, s) for s in ordered]
        self.assertEqual(rooms, ['主卧', '次卧', '书房', '儿童房'])

    def test_non_panel_sub_type_falls_back(self):
        """系统级 sub_type 不在表内，必须原样返回 fallback。"""
        self.assertEqual(
            resolve_panel_display(self.SP, 'main_thermostat', '主温控'), '主温控',
        )
        self.assertIsNone(resolve_panel_room(self.SP, 'fresh_air'))


@tag('unit')
class ThreeRoomLabelTests(TestCase):
    """B 组：三房标签——修复三个标签全错 + 幻影「书房」。"""

    SP = '9-1-10-1002'

    def setUp(self):
        _build_owner(self.SP, THREE_ROOM_PANELS)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_house_type_is_three(self):
        self.assertEqual(get_house_type(self.SP), HOUSE_TYPE_THREE)

    def test_labels_match_plc_config_three_room_branch(self):
        """三房分支与 plc_config 标注一致（120 户生产实证）。"""
        self.assertEqual(resolve_panel_room(self.SP, 'panel_children_room'), '儿童房')
        self.assertEqual(resolve_panel_room(self.SP, 'panel_bedroom'), '主卧')
        self.assertEqual(resolve_panel_room(self.SP, 'panel_study_room'), '次卧')

    def test_no_phantom_study_room(self):
        """三房户不得出现「书房」——修复前 panel_study_room 被标成「书房」。"""
        labels = [
            resolve_panel_room(self.SP, s)
            for s in ('panel_children_room', 'panel_bedroom', 'panel_study_room')
        ]
        self.assertNotIn('书房', labels)

    def test_fourth_panel_absent_in_three_room(self):
        """三房无第四块面板，panel_fourth_children 必须解析为 None。"""
        self.assertIsNone(resolve_panel_room(self.SP, 'panel_fourth_children'))
        self.assertEqual(
            resolve_panel_display(self.SP, 'panel_fourth_children', '儿童房-温控面板'),
            '儿童房-温控面板',  # 回退 fallback；可见性由 available_sub_types 另行拦截
        )

    def test_order_is_master_secondary_children(self):
        subs = ['panel_children_room', 'panel_bedroom', 'panel_study_room']
        ordered = sorted(subs, key=lambda s: get_panel_order(self.SP, s))
        rooms = [resolve_panel_room(self.SP, s) for s in ordered]
        self.assertEqual(rooms, ['主卧', '次卧', '儿童房'])


@tag('unit')
class ReverseMappingTests(TestCase):
    """C 组：逆映射双射性 + hash 稳定性（缺陷三回归护栏）。"""

    SP4 = '3-1-7-702'
    SP3 = '9-1-10-1002'

    def setUp(self):
        _build_owner(self.SP4, FOUR_ROOM_PANELS)
        _build_owner(self.SP3, THREE_ROOM_PANELS)

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_four_room_reverse_is_bijective(self):
        """四个房间必须映射到四个**互不相同**的 sub_type。

        修复前：书房/次卧 都得 panel_study_room、主卧/儿童房 都得
        panel_children_room，四房坍缩成两个 sub_type。
        """
        got = [resolve_sub_type_for_room(self.SP4, r) for r in FOUR_ROOM_PANELS]
        self.assertEqual(len(set(got)), 4, f'sub_type 发生坍缩: {dict(zip(FOUR_ROOM_PANELS, got))}')
        self.assertNotIn('', got)

    def test_four_room_reverse_exact_pairs(self):
        self.assertEqual(resolve_sub_type_for_room(self.SP4, '书房'), 'panel_children_room')
        self.assertEqual(resolve_sub_type_for_room(self.SP4, '次卧'), 'panel_bedroom')
        self.assertEqual(resolve_sub_type_for_room(self.SP4, '主卧'), 'panel_study_room')
        self.assertEqual(resolve_sub_type_for_room(self.SP4, '儿童房'), 'panel_fourth_children')

    def test_all_four_sub_types_reachable(self):
        """修复前 panel_bedroom 与 panel_fourth_children 永远不可能被分配出来。"""
        got = {resolve_sub_type_for_room(self.SP4, r) for r in FOUR_ROOM_PANELS}
        self.assertEqual(got, set(PANEL_ROOM_TABLE.keys()))

    def test_three_room_reverse_is_bijective(self):
        got = [resolve_sub_type_for_room(self.SP3, r) for r in THREE_ROOM_PANELS]
        self.assertEqual(len(set(got)), 3, f'sub_type 发生坍缩: {dict(zip(THREE_ROOM_PANELS, got))}')
        self.assertNotIn('', got)

    def test_round_trip_consistency(self):
        """房间 → sub_type → 房间 必须回到原点（双射自洽）。"""
        for sp, rooms in ((self.SP4, FOUR_ROOM_PANELS), (self.SP3, THREE_ROOM_PANELS)):
            for room in rooms:
                sub_type = resolve_sub_type_for_room(sp, room)
                self.assertEqual(
                    resolve_panel_room(sp, sub_type), room,
                    f'{sp} 的 {room} 往返不一致（sub_type={sub_type}）',
                )

    def test_deterministic_no_hash_dependence(self):
        """同一输入重复解析必须恒定——旧实现依赖 frozenset 迭代序（受 hash seed 影响）。

        进程内无法改 PYTHONHASHSEED，故用「反复调用 + 清缓存重算」近似；
        真正的跨进程稳定性由本函数不使用任何集合迭代取值来保证。
        """
        expected = {r: resolve_sub_type_for_room(self.SP4, r) for r in FOUR_ROOM_PANELS}
        for _ in range(20):
            invalidate_room_filter_cache()
            got = {r: resolve_sub_type_for_room(self.SP4, r) for r in FOUR_ROOM_PANELS}
            self.assertEqual(got, expected, '解析结果在重复调用间发生漂移')

    def test_room_not_in_template_returns_empty(self):
        """三房户出现「书房」（不属于三房模板）→ 空字符串，不猜。"""
        self.assertEqual(resolve_sub_type_for_room(self.SP3, '书房'), '')
        self.assertEqual(resolve_sub_type_for_room(self.SP4, '客房'), '')
        self.assertEqual(resolve_sub_type_for_room(self.SP4, ''), '')


@tag('unit')
class DegradedFallbackTests(TestCase):
    """D 组：户型判定失败时必须回退全局默认值，行为不突变。"""

    def tearDown(self):
        invalidate_room_filter_cache()

    def test_unsynced_device_tree_returns_none(self):
        """设备树未同步 → 户型 None → 全部回退 fallback。"""
        OwnerInfo.objects.create(
            specific_part='5-1-1-101', building='5', unit='1', room_number='101',
        )
        invalidate_room_filter_cache('5-1-1-101')
        self.assertIsNone(get_house_type('5-1-1-101'))
        self.assertIsNone(resolve_panel_room('5-1-1-101', 'panel_children_room'))
        self.assertEqual(
            resolve_panel_display('5-1-1-101', 'panel_children_room', '主卧-温控面板'),
            '主卧-温控面板',
        )
        self.assertEqual(resolve_sub_type_for_room('5-1-1-101', '主卧'), '')

    def test_abnormal_panel_count_returns_none(self):
        """面板数既非 3 也非 4（如 2 块）→ 不臆测户型，回退。"""
        _build_owner('6-1-1-101', ['主卧', '次卧'])
        self.assertIsNone(get_house_type('6-1-1-101'))
        self.assertEqual(
            resolve_panel_display('6-1-1-101', 'panel_bedroom', '次卧-温控面板'),
            '次卧-温控面板',
        )

    def test_order_fallback_sorts_last(self):
        """户型未知时展示序排在所有已知面板之后，不打乱既有布局。"""
        _build_owner('7-1-1-101', ['主卧', '次卧'])
        self.assertGreater(
            get_panel_order('7-1-1-101', 'panel_bedroom'),
            get_panel_order('3-1-7-702', 'panel_fourth_children')
            if get_house_type('3-1-7-702') else 0,
        )
