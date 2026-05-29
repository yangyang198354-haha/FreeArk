"""
test_fault_mgmt_v064_unit.py — v0.6.4-FM-ROOM 单元测试

覆盖范围：
  UT-C-001~005  constants.py 三字典结构验证 + VALID_ROOM_NAMES
  UT-RL-001~004 room_lookup.get_room_for_device 四场景
  UT-SM-001~002 state_machine._t1_insert room_lookup 调用验证
  UT-OR-001     oracle 反推表：3-1-602 error_code <-> device_sn <-> ori_room_name

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_fault_mgmt_v064_unit \\
        --settings=freearkweb.test_settings --verbosity=2

测试 DB：SQLite :memory:（test_settings.py 配置）
"""

import logging
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from api.fault_consumer.constants import (
    SUB_TYPE_ROOM_FILTER,
    SUB_TYPE_LABELS,
    SUB_TYPE_TO_FAULT_CODES,
    VALID_ROOM_NAMES,
)
from api.fault_consumer.room_lookup import get_room_for_device
from api.models import (
    FaultEvent, DeviceRoom, DeviceNode, DeviceFloor, OwnerInfo,
)


# ===========================================================================
# 辅助工厂函数
# ===========================================================================

def _make_owner(specific_part='3-1-6-602'):
    return OwnerInfo.objects.create(
        specific_part=specific_part,
        location_name=f'测试专有部分 {specific_part}',
    )


def _make_floor(owner, floor_no=6):
    return DeviceFloor.objects.create(owner=owner, floor_no=floor_no)


def _make_room(floor, ori_room_name, room_name=None, room_type=1):
    return DeviceRoom.objects.create(
        floor=floor,
        ori_room_name=ori_room_name,
        room_name=room_name or ori_room_name,
        room_type=room_type,
    )


def _make_node(room, device_sn, product_code='120003', device_name='温控面板'):
    return DeviceNode.objects.create(
        room=room,
        device_sn=device_sn,
        device_name=device_name,
        system_flag=1,
        product_code=product_code,
        category_code=1,
    )


def _make_fault_event(room_name=None, room_id=None, device_sn='22552', **kwargs):
    now = timezone.now()
    defaults = dict(
        specific_part='3-1-6-602',
        device_sn=device_sn,
        product_code='120003',
        fault_code='error_709',
        fault_type='comm',
        fault_message='通信故障',
        severity='error',
        first_seen_at=now - timedelta(hours=1),
        last_seen_at=now - timedelta(minutes=30),
        is_active=True,
        room_name=room_name,
        room_id=room_id,
    )
    defaults.update(kwargs)
    return FaultEvent.objects.create(**defaults)


# ===========================================================================
# UT-C: constants.py 结构验证
# ===========================================================================

class TestConstantsStructure(TestCase):
    """UT-C-001~005：constants.py 三字典结构验证。"""

    def test_sub_type_room_filter_new_keys_present(self):
        """UT-C-001：SUB_TYPE_ROOM_FILTER 包含所有 5 个新温控 key + 4 个非温控 key。"""
        expected_thermostat_keys = {
            'living_room_main',
            'master_bedroom_panel',
            'secondary_bedroom_panel',
            'children_room_panel',
            'study_room_panel',
        }
        expected_non_thermostat_keys = {
            'fresh_air_unit',
            'hydraulic_module',
            'energy_meter',
            'air_quality_sensor',
        }
        actual_keys = set(SUB_TYPE_ROOM_FILTER.keys())
        self.assertTrue(
            expected_thermostat_keys.issubset(actual_keys),
            f'缺少温控类 key：{expected_thermostat_keys - actual_keys}',
        )
        self.assertTrue(
            expected_non_thermostat_keys.issubset(actual_keys),
            f'缺少非温控类 key：{expected_non_thermostat_keys - actual_keys}',
        )

    def test_old_thermostat_keys_absent(self):
        """UT-C-002：旧 thermostat 命名的 key 不在 SUB_TYPE_ROOM_FILTER 中。"""
        old_keys = {
            'living_room_thermostat',
            'study_room_thermostat',
            'bedroom_thermostat',
            'children_room_thermostat',
            'fourth_children_room_thermostat',
        }
        for key in old_keys:
            self.assertNotIn(
                key, SUB_TYPE_ROOM_FILTER,
                f'旧 key "{key}" 不应出现在 SUB_TYPE_ROOM_FILTER（v0.6.4 已重组）',
            )

    def test_sub_type_labels_keys_match_room_filter(self):
        """UT-C-003：SUB_TYPE_LABELS keys 与 SUB_TYPE_ROOM_FILTER keys 完全一致。"""
        self.assertEqual(
            set(SUB_TYPE_LABELS.keys()),
            set(SUB_TYPE_ROOM_FILTER.keys()),
            'SUB_TYPE_LABELS 和 SUB_TYPE_ROOM_FILTER 的 key 集合不一致',
        )

    def test_valid_room_names_correct(self):
        """UT-C-004：VALID_ROOM_NAMES 包含且仅包含 5 个房间名。"""
        expected = frozenset(['客厅', '主卧', '次卧', '儿童房', '书房'])
        self.assertEqual(VALID_ROOM_NAMES, expected)
        self.assertIsInstance(VALID_ROOM_NAMES, frozenset)

    def test_study_room_panel_room_keywords(self):
        """UT-C-005：study_room_panel 的 room_keywords 仅含 '书房'（不含次卧）。"""
        product_codes, room_keywords = SUB_TYPE_ROOM_FILTER['study_room_panel']
        self.assertEqual(room_keywords, ['书房'],
                         'study_room_panel 的 room_keywords 应仅包含 "书房"')
        self.assertNotIn('次卧', room_keywords,
                         'study_room_panel 不应包含 "次卧"（旧 study_room_thermostat 的遗留）')

    def test_sub_type_to_fault_codes_new_keys(self):
        """SUB_TYPE_TO_FAULT_CODES 包含所有新 sub_type key（向后兼容 OR 路径）。"""
        new_keys = {
            'living_room_main',
            'master_bedroom_panel',
            'secondary_bedroom_panel',
            'children_room_panel',
            'study_room_panel',
        }
        for key in new_keys:
            self.assertIn(
                key, SUB_TYPE_TO_FAULT_CODES,
                f'新 key "{key}" 应在 SUB_TYPE_TO_FAULT_CODES 中',
            )

    def test_sub_type_labels_study_room_panel_label(self):
        """SUB_TYPE_LABELS['study_room_panel'] 标签为 '书房温控面板'。"""
        self.assertEqual(SUB_TYPE_LABELS['study_room_panel'], '书房温控面板')

    def test_sub_type_labels_no_fourth_children_thermostat(self):
        """'第四儿童房温控面板' label 不应出现在 SUB_TYPE_LABELS 中。"""
        for label in SUB_TYPE_LABELS.values():
            self.assertNotEqual(label, '第四儿童房温控面板',
                                '旧标签"第四儿童房温控面板"不应出现在 v0.6.4 的 SUB_TYPE_LABELS 中')


# ===========================================================================
# UT-RL: room_lookup.py 单元测试
# ===========================================================================

class TestRoomLookup(TestCase):
    """UT-RL-001~004：get_room_for_device 四场景。"""

    def setUp(self):
        # 创建测试数据：3-1-6-602 四房 — 书房设备 device_sn=22552
        self.owner = _make_owner('3-1-6-602')
        self.floor = _make_floor(self.owner, floor_no=6)
        self.room_study = _make_room(self.floor, '书房')
        self.node_study = _make_node(self.room_study, device_sn=22552, product_code='120003')

    def test_normal_device_sn_returns_room_info(self):
        """UT-RL-001：正常 device_sn，DeviceNode 存在且有 room，返回 (ori_room_name, room_id)。"""
        result = get_room_for_device('22552')
        self.assertEqual(result, ('书房', self.room_study.id),
                         f'期望 ("书房", {self.room_study.id})，实际 {result}')

    def test_nonexistent_device_sn_returns_none_none(self):
        """UT-RL-002：device_sn 在 DeviceNode 不存在，返回 (None, None)，不抛异常。"""
        result = get_room_for_device('999999999')
        self.assertEqual(result, (None, None),
                         f'期望 (None, None)，实际 {result}')

    def test_non_integer_device_sn_returns_none_none(self):
        """UT-RL-003：device_sn 为非整数字符串（如 'abc'），返回 (None, None)，不抛异常。"""
        result = get_room_for_device('abc')
        self.assertEqual(result, (None, None))

    def test_db_exception_returns_none_none(self):
        """UT-RL-004：DB 查询抛出异常（mock），返回 (None, None)，不上抛异常。"""
        with patch('api.models.DeviceNode.objects') as mock_objects:
            mock_objects.select_related.return_value.filter.side_effect = Exception('DB crash')
            result = get_room_for_device('22552')
        self.assertEqual(result, (None, None),
                         'DB 异常时 get_room_for_device 应返回 (None, None) 不上抛')

    def test_empty_string_device_sn_returns_none_none(self):
        """空字符串 device_sn，返回 (None, None)，不抛异常。"""
        result = get_room_for_device('')
        self.assertEqual(result, (None, None))

    def test_multiple_nodes_same_sn_returns_first(self):
        """多个 DeviceNode 同 device_sn（异常数据），.first() 返回第一个，不崩溃。"""
        room2 = _make_room(self.floor, '主卧')
        # 同一 device_sn 在另一个房间创建（绕过 unique_together 通过不同 room）
        _make_node(room2, device_sn=22999, product_code='120003')
        _make_node(self.floor.rooms.first(), device_sn=22999, product_code='260001')

        result = get_room_for_device('22999')
        # 不崩溃，返回有效的 (ori_room_name, room_id) 或 (None, None)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


# ===========================================================================
# UT-SM: state_machine._t1_insert 验证
# ===========================================================================

class TestStateMachineT1RoomLookup(TestCase):
    """UT-SM-001~002：_t1_insert 调用 room_lookup 并写入 FaultEvent。"""

    def setUp(self):
        # 创建基础测试数据
        self.owner = _make_owner('3-1-6-602')
        self.floor = _make_floor(self.owner, floor_no=6)
        self.room_master = _make_room(self.floor, '主卧')
        self.node_master = _make_node(self.room_master, device_sn=22554)

    def _call_t1_insert(self, device_sn='22554'):
        """辅助方法：直接调用 _t1_insert 内部逻辑。

        close_old_connections() 在测试环境（SQLite :memory:）会关闭测试事务连接，
        导致后续 ORM 操作打开新的空内存 DB（无表），触发 OperationalError 被 except
        吞掉，FaultEvent 无法写入。
        解决：patch 掉 state_machine 模块内的 close_old_connections，使其无操作。
        """
        from api.fault_consumer.state_machine import _t1_insert
        import api.fault_consumer.state_machine as sm_module
        # 清空状态机避免干扰
        sm_module._state_machine = {}
        now = timezone.now()
        # patch close_old_connections 防止其关闭 SQLite :memory: 测试连接
        with patch('api.fault_consumer.state_machine.close_old_connections'):
            _t1_insert(
                key=('3-1-6-602', device_sn, 'error_769'),
                specific_part='3-1-6-602',
                device_sn=device_sn,
                product_code='120003',
                fault_code='error_769',
                fault_type='comm',
                severity='error',
                fault_message='通信故障',
                received_at=now,
            )

    def test_t1_insert_writes_room_name(self):
        """UT-SM-001：T1 INSERT 后 FaultEvent.room_name 为 '主卧'（DeviceNode 22554 关联主卧）。"""
        self._call_t1_insert('22554')
        fe = FaultEvent.objects.filter(device_sn='22554', fault_code='error_769').first()
        self.assertIsNotNone(fe, 'T1 INSERT 后应有 FaultEvent 记录')
        self.assertEqual(fe.room_name, '主卧',
                         f'期望 room_name="主卧"，实际="{fe.room_name}"')
        self.assertEqual(fe.room_id_id, self.room_master.id,
                         f'期望 room_id={self.room_master.id}，实际={fe.room_id_id}')

    def test_t1_insert_room_lookup_failure_still_creates_fault_event(self):
        """UT-SM-002：T1 INSERT 时 room_lookup 返回 (None, None)，FaultEvent 仍正常写入，room_name=None。"""
        # device_sn='99999' 不在 DeviceNode 中，room_lookup 返回 (None, None)
        self._call_t1_insert('99999')
        fe = FaultEvent.objects.filter(device_sn='99999', fault_code='error_769').first()
        self.assertIsNotNone(fe, 'room_lookup 失败时 FaultEvent 仍应写入')
        self.assertIsNone(fe.room_name,
                          f'room_lookup 失败时 room_name 应为 None，实际="{fe.room_name}"')
        self.assertIsNone(fe.room_id_id,
                          f'room_lookup 失败时 room_id 应为 None，实际={fe.room_id_id}')

    def test_t1_insert_calls_room_lookup_once(self):
        """UT-SM-001 扩展：验证 _t1_insert 调用 get_room_for_device 恰好 1 次。"""
        # get_room_for_device 是 state_machine 的模块级名称，可直接 patch
        with patch(
            'api.fault_consumer.state_machine.get_room_for_device',
            return_value=('主卧', self.room_master.id),
        ) as mock_lookup:
            self._call_t1_insert('22554')
        mock_lookup.assert_called_once_with('22554')


# ===========================================================================
# UT-OR: oracle 反推表验证
# ===========================================================================

class TestOracleReverseTable(TestCase):
    """UT-OR-001：3-1-602（4 房）error_code 反推表 oracle 验证。

    来源：架构文档附录 F（db_evidence.md 查询 3 反向验证）。
    本测试通过构造 fixture 模拟生产 device_sn <-> ori_room_name 对应关系，
    验证 SUB_TYPE_ROOM_FILTER 的 ori_room_name 关键词能正确命中各房间设备。
    """

    # oracle 表（架构文档附录 F）
    ORACLE = [
        # (error_code, device_sn, ori_room_name, sub_type)
        ('error_679', 22158, '客厅', 'living_room_main'),
        ('error_709', 22552, '书房', 'study_room_panel'),
        ('error_739', 22553, '次卧', 'secondary_bedroom_panel'),
        ('error_769', 22554, '主卧', 'master_bedroom_panel'),
        ('error_799', 22555, '儿童房', 'children_room_panel'),
    ]

    def setUp(self):
        """构造 3-1-6-602 四房 fixture（5 台设备）。"""
        import re
        owner = _make_owner('3-1-6-602')
        floor = _make_floor(owner, floor_no=6)
        self.rooms = {}
        self.nodes = {}

        room_data = [
            ('客厅', 22158, '260001'),
            ('书房', 22552, '120003'),
            ('次卧', 22553, '120003'),
            ('主卧', 22554, '120003'),
            ('儿童房', 22555, '120003'),
        ]
        for ori_room_name, device_sn, product_code in room_data:
            room = _make_room(floor, ori_room_name)
            node = _make_node(room, device_sn, product_code)
            self.rooms[ori_room_name] = room
            self.nodes[device_sn] = node

    def test_oracle_device_sn_to_ori_room_name(self):
        """oracle 验证：每个 device_sn 对应的 ori_room_name 符合 oracle 表。"""
        for error_code, device_sn, expected_room, sub_type in self.ORACLE:
            result = get_room_for_device(str(device_sn))
            self.assertIsNotNone(result[0],
                                 f'{error_code}（device_sn={device_sn}）应能反查 room_name')
            self.assertEqual(
                result[0], expected_room,
                f'oracle 失败：device_sn={device_sn} 期望 ori_room_name="{expected_room}"，'
                f'实际="{result[0]}"',
            )

    def test_oracle_sub_type_room_keywords_match(self):
        """oracle 验证：每个 sub_type 的 room_keywords 应覆盖对应的 ori_room_name。"""
        for error_code, device_sn, ori_room_name, sub_type in self.ORACLE:
            product_codes, room_keywords = SUB_TYPE_ROOM_FILTER[sub_type]
            node = self.nodes[device_sn]
            room = self.rooms[ori_room_name]

            if room_keywords:
                # 验证 ori_room_name 在 room_keywords 中（OR 匹配逻辑）
                import re
                pattern = '|'.join(map(re.escape, room_keywords))
                self.assertIsNotNone(
                    re.search(pattern, ori_room_name),
                    f'oracle 失败：sub_type="{sub_type}" room_keywords={room_keywords} '
                    f'不能匹配 ori_room_name="{ori_room_name}"',
                )
            else:
                # room_keywords 为空，靠 product_code 过滤（living_room_main）
                self.assertIn(
                    str(node.product_code), product_codes,
                    f'oracle 失败：sub_type="{sub_type}" product_code="{node.product_code}" '
                    f'不在 {product_codes} 中',
                )

    def test_three_room_1601_no_study_room(self):
        """oracle 验证（3 房补充）：1-1-16-1601 无书房设备 → study_room_panel 过滤后 0 台设备。

        注意：setUp 已创建 3-1-6-602 四房 fixture（含书房 device_sn=22552）。
        本测试查询不限 owner，若不清除 setUp 数据会命中 setUp 中的书房节点。
        因此在方法开始时清除所有 OwnerInfo（级联删除 Floor/Room/Node）后，
        仅构造 1-1-16-1601 三房 fixture，确保隔离。
        """
        # 清除 setUp 创建的 3-1-6-602 数据（Cascade: OwnerInfo→Floor→Room→Node）
        OwnerInfo.objects.all().delete()

        # 构造 1-1-16-1601 三房 fixture（4 台：客厅/主卧/次卧/儿童房，无书房）
        owner = _make_owner('1-1-16-1601')
        floor = _make_floor(owner, floor_no=16)
        room_data = [
            ('客厅', 22001, '260001'),
            ('主卧', 22550, '120003'),
            ('次卧', 22551, '120003'),
            ('儿童房', 22549, '120003'),
        ]
        for ori_room_name, device_sn, product_code in room_data:
            room = _make_room(floor, ori_room_name)
            _make_node(room, device_sn, product_code)

        # 查找 study_room_panel 的设备（ori_room_name IN ['书房']）
        product_codes, room_keywords = SUB_TYPE_ROOM_FILTER['study_room_panel']
        import re
        pattern = '|'.join(map(re.escape, room_keywords))  # '书房'
        matching_sns = list(
            DeviceNode.objects.filter(
                product_code__in=product_codes,
                room__ori_room_name__regex=pattern,
            ).values_list('device_sn', flat=True)
        )
        self.assertEqual(
            len(matching_sns), 0,
            f'3 房 1-1-16-1601 无书房设备，study_room_panel 应返回 0 个 device_sn，'
            f'实际 {len(matching_sns)} 个：{matching_sns}',
        )
