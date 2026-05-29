"""
test_fault_mgmt_v064_integration.py — v0.6.4-FM-ROOM 集成测试

覆盖范围：
  IT-MIG-001~002  migration 0028 数据回填（构造 fixture，验证 room_name 填充率）
  IT-FC-001~002   fault_consumer 写入路径（mock DeviceNode，验证 _t1_insert room 写入）
  IT-VF-001~006   views_fault.py room_name 过滤参数（API 级别集成测试）
  IT-SER-001~002  序列化器 room_name/room_id 字段
  关键回归场景    3-1-602 四房各房间过滤 + 1-1-16-1601 三房书房返回 0 条

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_fault_mgmt_v064_integration \\
        --settings=freearkweb.test_settings --verbosity=2

测试 DB：SQLite :memory:
注意：migration 0028 回填测试使用 call_command('migrate') 模拟，在 :memory: SQLite 下执行。
"""

from datetime import timedelta
from unittest.mock import patch, MagicMock, call

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model

from api.models import (
    FaultEvent, DeviceRoom, DeviceNode, DeviceFloor, OwnerInfo,
)
import api.device_name_cache as cache_module

User = get_user_model()


# ===========================================================================
# 辅助工厂
# ===========================================================================

def _make_admin(username):
    user = User.objects.create_user(username=username, password='testpass123', role='admin')
    token = Token.objects.create(user=user)
    return user, token.key


def _make_owner(specific_part):
    return OwnerInfo.objects.create(
        specific_part=specific_part,
        location_name=f'测试 {specific_part}',
    )


def _make_floor(owner, floor_no=6):
    return DeviceFloor.objects.create(owner=owner, floor_no=floor_no)


def _make_room(floor, ori_room_name):
    return DeviceRoom.objects.create(
        floor=floor,
        ori_room_name=ori_room_name,
        room_name=ori_room_name,
        room_type=1,
    )


def _make_node(room, device_sn, product_code='120003'):
    return DeviceNode.objects.create(
        room=room,
        device_sn=device_sn,
        device_name='温控面板',
        system_flag=1,
        product_code=product_code,
        category_code=1,
    )


def _make_fault_event(specific_part='3-1-6-602', device_sn='22552',
                      fault_code='error_709', room_name=None, room_id=None,
                      hours_ago=1, **kwargs):
    now = timezone.now()
    defaults = dict(
        specific_part=specific_part,
        device_sn=device_sn,
        product_code='120003',
        fault_code=fault_code,
        fault_type='comm',
        fault_message='通信故障',
        severity='error',
        first_seen_at=now - timedelta(hours=hours_ago),
        last_seen_at=now - timedelta(minutes=30),
        is_active=True,
        room_name=room_name,
        room_id=room_id,
    )
    defaults.update(kwargs)
    return FaultEvent.objects.create(**defaults)


def _reset_cache():
    cache_module._cache = {}
    cache_module._cache_loaded_at = 0.0


# ===========================================================================
# IT-MIG: migration 0028 数据回填测试
# ===========================================================================

class TestMigration0028Backfill(TestCase):
    """IT-MIG-001~002：migration 0028 回填逻辑验证（直接测试 backfill_room 函数）。"""

    def setUp(self):
        # 构造 3-1-6-602 四房 fixture（5 台设备）
        self.owner = _make_owner('3-1-6-602')
        self.floor = _make_floor(self.owner, floor_no=6)
        room_data = [
            ('客厅', 22158, '260001'),
            ('书房', 22552, '120003'),
            ('次卧', 22553, '120003'),
            ('主卧', 22554, '120003'),
            ('儿童房', 22555, '120003'),
        ]
        self.rooms = {}
        self.nodes = {}
        for ori_room_name, device_sn, product_code in room_data:
            room = _make_room(self.floor, ori_room_name)
            node = _make_node(room, device_sn, product_code)
            self.rooms[ori_room_name] = room
            self.nodes[device_sn] = node

        # 构造 10 条 FaultEvent（room_name=NULL，模拟历史数据）
        self.fault_events = []
        for i, (error_code, device_sn, ori_room_name, _) in enumerate([
            ('error_679', 22158, '客厅', 'living_room_main'),
            ('error_709', 22552, '书房', 'study_room_panel'),
            ('error_739', 22553, '次卧', 'secondary_bedroom_panel'),
            ('error_769', 22554, '主卧', 'master_bedroom_panel'),
            ('error_799', 22555, '儿童房', 'children_room_panel'),
            # 重复几条（测试批量处理）
            ('error_709', 22552, '书房', 'study_room_panel'),
            ('error_739', 22553, '次卧', 'secondary_bedroom_panel'),
            ('error_769', 22554, '主卧', 'master_bedroom_panel'),
            ('error_799', 22555, '儿童房', 'children_room_panel'),
            ('error_679', 22158, '客厅', 'living_room_main'),
        ], start=1):
            now = timezone.now()
            fe = FaultEvent.objects.create(
                specific_part='3-1-6-602',
                device_sn=str(device_sn),
                product_code='120003',
                fault_code=error_code,
                fault_type='comm',
                fault_message='通信故障',
                severity='error',
                first_seen_at=now - timedelta(hours=i),
                last_seen_at=now - timedelta(minutes=i * 10),
                is_active=True,
                room_name=None,
                room_id=None,
            )
            self.fault_events.append((fe, str(device_sn), ori_room_name))

    def _run_backfill(self):
        """直接调用 migration 0028 的 backfill_room 函数（不通过 migrate 命令）。

        migration 文件名以数字开头，无法用 import 语法直接导入，使用 importlib。
        """
        import importlib.util
        import os
        migration_path = os.path.join(
            os.path.dirname(__file__), '..', 'migrations',
            '0028_fault_event_backfill_room.py',
        )
        migration_path = os.path.abspath(migration_path)
        spec = importlib.util.spec_from_file_location('_mig0028', migration_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # MockApps：让 migration 使用真实 Django Model（测试 DB）
        class MockApps:
            @staticmethod
            def get_model(app_label, model_name):
                if model_name == 'FaultEvent':
                    return FaultEvent
                if model_name == 'DeviceNode':
                    return DeviceNode
                raise ValueError(f'Unknown model: {model_name}')

        mod.backfill_room(MockApps(), None)

    def test_backfill_fills_room_name_for_all_connectable_rows(self):
        """IT-MIG-001：回填后所有可关联行（device_sn 有 DeviceNode）的 room_name 非 NULL。"""
        # 回填前验证均为 NULL
        null_count_before = FaultEvent.objects.filter(room_name__isnull=True).count()
        self.assertEqual(null_count_before, 10, '回填前所有行 room_name 应为 NULL')

        self._run_backfill()

        # 回填后验证
        null_count_after = FaultEvent.objects.filter(room_name__isnull=True).count()
        filled_count = FaultEvent.objects.filter(room_name__isnull=False).count()

        self.assertEqual(null_count_after, 0,
                         f'回填后应无 room_name=NULL 行（全部 device_sn 可关联），实际 NULL={null_count_after}')
        self.assertEqual(filled_count, 10, '全部 10 行应已回填')

    def test_backfill_correct_room_name_per_device_sn(self):
        """IT-MIG-001 详细：回填后各 device_sn 对应的 room_name 正确。"""
        self._run_backfill()

        expected = {
            '22158': '客厅',
            '22552': '书房',
            '22553': '次卧',
            '22554': '主卧',
            '22555': '儿童房',
        }
        for device_sn, expected_room in expected.items():
            fes = FaultEvent.objects.filter(device_sn=device_sn)
            for fe in fes:
                self.assertEqual(
                    fe.room_name, expected_room,
                    f'device_sn={device_sn} 回填后 room_name 期望="{expected_room}"，'
                    f'实际="{fe.room_name}"',
                )

    def test_backfill_room_id_valid_fk(self):
        """IT-MIG-001：回填后 room_id 外键有效（指向真实 DeviceRoom.id）。"""
        self._run_backfill()
        for fe in FaultEvent.objects.all():
            self.assertIsNotNone(fe.room_id_id,
                                 f'device_sn={fe.device_sn} 的 room_id 应非 NULL')
            # 验证外键有效
            self.assertTrue(
                DeviceRoom.objects.filter(id=fe.room_id_id).exists(),
                f'room_id={fe.room_id_id} 对应的 DeviceRoom 不存在',
            )

    def test_backfill_orphan_device_sn_remains_null(self):
        """IT-MIG-002：无 DeviceNode 关联的孤立 device_sn，回填后 room_name 仍为 NULL。"""
        # 创建孤立 FaultEvent（device_sn='99999' 无 DeviceNode）
        now = timezone.now()
        orphan_fe = FaultEvent.objects.create(
            specific_part='3-1-6-602',
            device_sn='99999',
            product_code='120003',
            fault_code='error_999',
            fault_type='comm',
            fault_message='孤立设备故障',
            severity='error',
            first_seen_at=now - timedelta(hours=99),
            last_seen_at=now - timedelta(hours=98),
            is_active=False,
            room_name=None,
            room_id=None,
        )

        self._run_backfill()

        orphan_fe.refresh_from_db()
        self.assertIsNone(orphan_fe.room_name,
                          '孤立 device_sn 回填后 room_name 应仍为 NULL')
        self.assertIsNone(orphan_fe.room_id_id,
                          '孤立 device_sn 回填后 room_id 应仍为 NULL')


# ===========================================================================
# IT-FC: fault_consumer 写入路径集成测试
# ===========================================================================

class TestFaultConsumerWritePath(TestCase):
    """IT-FC-001~002：fault_consumer T1 INSERT 写入路径 room_name 集成测试。"""

    def setUp(self):
        _reset_cache()
        self.owner = _make_owner('3-1-6-602')
        self.floor = _make_floor(self.owner, floor_no=6)
        self.room_master = _make_room(self.floor, '主卧')
        self.node_master = _make_node(self.room_master, device_sn=22554)

    def tearDown(self):
        _reset_cache()
        import api.fault_consumer.state_machine as sm_module
        sm_module._state_machine = {}

    def _invoke_t1(self, device_sn='22554', fault_code='error_769'):
        from api.fault_consumer.state_machine import _t1_insert
        import api.fault_consumer.state_machine as sm_module
        sm_module._state_machine = {}
        now = timezone.now()
        # patch close_old_connections: SQLite :memory: 测试连接不能被关闭，
        # 否则下次 ORM 操作会打开空的新内存 DB（无表），触发 OperationalError 被
        # state_machine 的 except 块静默吞掉，导致 FaultEvent 写入失败。
        with patch('api.fault_consumer.state_machine.close_old_connections'):
            _t1_insert(
                key=('3-1-6-602', device_sn, fault_code),
                specific_part='3-1-6-602',
                device_sn=device_sn,
                product_code='120003',
                fault_code=fault_code,
                fault_type='comm',
                severity='error',
                fault_message='通信故障',
                received_at=now,
            )

    def test_t1_insert_calls_room_lookup_once(self):
        """IT-FC-001：mock DeviceNode 查询，验证 _t1_insert 调用 get_room_for_device 一次。"""
        with patch(
            'api.fault_consumer.state_machine.get_room_for_device',
            return_value=('主卧', self.room_master.id),
        ) as mock_lookup:
            self._invoke_t1('22554')

        mock_lookup.assert_called_once_with('22554')

    def test_t1_insert_stores_room_in_fault_event(self):
        """IT-FC-001：T1 INSERT 后，FaultEvent 的 room_name 和 room_id 正确写入。"""
        self._invoke_t1('22554')
        fe = FaultEvent.objects.filter(device_sn='22554', fault_code='error_769').first()
        self.assertIsNotNone(fe)
        self.assertEqual(fe.room_name, '主卧')
        self.assertEqual(fe.room_id_id, self.room_master.id)

    def test_t1_insert_room_lookup_db_exception_fault_event_still_created(self):
        """IT-FC-002：DeviceNode 查询失败（mock Exception），FaultEvent 仍写入，room_name=None。"""
        with patch(
            'api.fault_consumer.state_machine.get_room_for_device',
            return_value=(None, None),
        ):
            self._invoke_t1('99999', fault_code='error_000')

        fe = FaultEvent.objects.filter(device_sn='99999', fault_code='error_000').first()
        self.assertIsNotNone(fe, 'room_lookup 失败时 FaultEvent 仍应写入')
        self.assertIsNone(fe.room_name)
        self.assertIsNone(fe.room_id_id)


# ===========================================================================
# IT-VF: views_fault.py room_name 过滤集成测试
# ===========================================================================

class TestFaultEventRoomNameFilter(TestCase):
    """IT-VF-001~006：GET /api/devices/fault-events/?room_name=xxx 过滤集成测试。"""

    def setUp(self):
        _reset_cache()
        _, token = _make_admin('admin_vf')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.list_url = '/api/devices/fault-events/'

        # 构造 3-1-6-602 四房 fixture
        owner = _make_owner('3-1-6-602')
        floor = _make_floor(owner, floor_no=6)
        room_data = [
            ('客厅', 22158, '260001'),
            ('书房', 22552, '120003'),
            ('次卧', 22553, '120003'),
            ('主卧', 22554, '120003'),
            ('儿童房', 22555, '120003'),
        ]
        self.rooms = {}
        self.nodes = {}
        for ori_room_name, device_sn, product_code in room_data:
            room = _make_room(floor, ori_room_name)
            node = _make_node(room, device_sn, product_code)
            self.rooms[ori_room_name] = room
            self.nodes[device_sn] = node

        now = timezone.now()
        # 创建每个房间 2 条 FaultEvent（room_name 已填充）
        self.fe_by_room = {}
        for ori_room_name, device_sn, _ in room_data:
            fes = []
            for i in range(2):
                fe = FaultEvent.objects.create(
                    specific_part='3-1-6-602',
                    device_sn=str(device_sn),
                    product_code='120003',
                    fault_code=f'error_{device_sn + i}',
                    fault_type='comm',
                    fault_message='通信故障',
                    severity='error',
                    first_seen_at=now - timedelta(hours=i + 1),
                    last_seen_at=now - timedelta(minutes=(i + 1) * 30),
                    is_active=True,
                    room_name=ori_room_name,
                    room_id_id=self.rooms[ori_room_name].id,
                )
                fes.append(fe)
            self.fe_by_room[ori_room_name] = fes

    def tearDown(self):
        _reset_cache()

    def _get_all(self, params=''):
        """辅助：GET 全量（不限时间范围）。"""
        resp = self.client.get(
            self.list_url + '?page_size=100'
            + '&first_seen_after=2000-01-01T00:00:00'
            + (f'&{params}' if params else ''),
        )
        self.assertEqual(resp.status_code, 200, f'API 返回非 200：{resp.status_code}')
        return resp.json()['results']

    def test_room_name_filter_single_room(self):
        """IT-VF-001：room_name=主卧 仅返回主卧 FaultEvent。"""
        results = self._get_all('room_name=主卧')
        for r in results:
            self.assertEqual(r['room_name'], '主卧',
                             f'过滤 room_name=主卧，结果中出现 room_name="{r["room_name"]}"')
        self.assertEqual(len(results), 2, f'期望 2 条主卧记录，实际 {len(results)} 条')

    def test_room_name_filter_multiple_rooms(self):
        """IT-VF-002：room_name=主卧&room_name=次卧（多值），返回主卧+次卧合集。"""
        results = self._get_all('room_name=主卧&room_name=次卧')
        room_names_in_result = {r['room_name'] for r in results}
        self.assertSetEqual(room_names_in_result, {'主卧', '次卧'},
                            f'结果应只含主卧和次卧，实际：{room_names_in_result}')
        self.assertEqual(len(results), 4, f'期望 4 条（主卧2+次卧2），实际 {len(results)} 条')

    def test_invalid_room_name_not_in_whitelist(self):
        """IT-VF-003：无效 room_name 值（卫生间）被白名单过滤，不添加 filter 条件，返回全量。"""
        results = self._get_all('room_name=卫生间')
        # 无效值被过滤后，valid_room_names 为空，不添加 filter，返回全量
        self.assertEqual(len(results), 10,
                         f'无效 room_name 应返回全量 10 条，实际 {len(results)} 条')

    def test_no_room_name_param_returns_all(self):
        """IT-VF-004：不传 room_name 参数，返回全部记录（10 条）。"""
        results = self._get_all()
        self.assertEqual(len(results), 10, f'不传 room_name 应返回全量 10 条，实际 {len(results)} 条')

    def test_room_name_field_in_response(self):
        """IT-SER-001/002：序列化器响应中包含 room_name 和 room_id 字段。"""
        results = self._get_all()
        self.assertGreater(len(results), 0)
        first = results[0]
        self.assertIn('room_name', first, '响应缺少 room_name 字段')
        self.assertIn('room_id', first, '响应缺少 room_id 字段')

    def test_room_name_null_serialized_as_null(self):
        """IT-SER-002：FaultEvent room_name=NULL 序列化后 room_name 字段值为 null。"""
        # 创建一条 room_name=NULL 的 FaultEvent
        now = timezone.now()
        FaultEvent.objects.create(
            specific_part='3-1-6-602',
            device_sn='99999',
            product_code='120003',
            fault_code='error_null_room',
            fault_type='comm',
            fault_message='测试',
            severity='error',
            first_seen_at=now - timedelta(hours=0, minutes=5),
            last_seen_at=now - timedelta(minutes=3),
            is_active=True,
            room_name=None,
            room_id=None,
        )
        results = self._get_all()
        null_room_results = [r for r in results if r.get('fault_code') == 'error_null_room']
        self.assertEqual(len(null_room_results), 1)
        self.assertIsNone(null_room_results[0]['room_name'],
                          'room_name=NULL 的 FaultEvent 序列化后应为 null')
        self.assertIsNone(null_room_results[0]['room_id'],
                          'room_id=NULL 的 FaultEvent 序列化后应为 null')


# ===========================================================================
# IT-REG: 关键回归场景（主线 PM 要求，oracle 驱动）
# ===========================================================================

class TestKeyRegressionScenarios(TestCase):
    """关键回归测试：3-1-602 四房各 sub_type 过滤 + 1-1-16-1601 三房书房返回 0 条。

    这些场景测试 views_fault.py 的 sub_type 过滤逻辑（SUB_TYPE_ROOM_FILTER）是否正确。
    使用 Oracle 表数据（架构文档附录 F）构造 fixture。

    注意：这些场景基于 device_sn → device_node → device_room.ori_room_name 路径，
    与生产数据中 error_NNN 通用码的实际过滤路径一致。
    """

    def setUp(self):
        _reset_cache()
        _, token = _make_admin('admin_reg')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        self.list_url = '/api/devices/fault-events/'

        # 构造 3-1-6-602 四房 fixture
        owner_4room = _make_owner('3-1-6-602')
        floor_4room = _make_floor(owner_4room, floor_no=6)
        room_data_4room = [
            ('客厅', 22158, '260001'),
            ('书房', 22552, '120003'),
            ('次卧', 22553, '120003'),
            ('主卧', 22554, '120003'),
            ('儿童房', 22555, '120003'),
        ]
        self.rooms_4room = {}
        self.nodes_4room = {}
        for ori_room_name, device_sn, product_code in room_data_4room:
            room = _make_room(floor_4room, ori_room_name)
            node = _make_node(room, device_sn, product_code)
            self.rooms_4room[ori_room_name] = room
            self.nodes_4room[device_sn] = node

        # 构造 1-1-16-1601 三房 fixture（无书房）
        owner_3room = _make_owner('1-1-16-1601')
        floor_3room = _make_floor(owner_3room, floor_no=16)
        room_data_3room = [
            ('客厅', 22001, '260001'),
            ('主卧', 22550, '120003'),
            ('次卧', 22551, '120003'),
            ('儿童房', 22549, '120003'),
        ]
        self.rooms_3room = {}
        self.nodes_3room = {}
        for ori_room_name, device_sn, product_code in room_data_3room:
            room = _make_room(floor_3room, ori_room_name)
            node = _make_node(room, device_sn, product_code)
            self.rooms_3room[ori_room_name] = room
            self.nodes_3room[device_sn] = node

        now = timezone.now()
        # 为 3-1-6-602 各设备创建 FaultEvent（1 条）
        self.fe_4room = {}
        oracle = [
            ('error_679', 22158, '客厅'),
            ('error_709', 22552, '书房'),
            ('error_739', 22553, '次卧'),
            ('error_769', 22554, '主卧'),
            ('error_799', 22555, '儿童房'),
        ]
        for i, (error_code, device_sn, ori_room_name) in enumerate(oracle):
            pc = '260001' if device_sn == 22158 else '120003'
            fe = FaultEvent.objects.create(
                specific_part='3-1-6-602',
                device_sn=str(device_sn),
                product_code=pc,
                fault_code=error_code,
                fault_type='comm',
                fault_message='通信故障',
                severity='error',
                first_seen_at=now - timedelta(hours=i + 1),
                last_seen_at=now - timedelta(minutes=(i + 1) * 10),
                is_active=True,
            )
            self.fe_4room[ori_room_name] = fe

        # 为 1-1-16-1601 各设备创建 FaultEvent（1 条，无书房）
        self.fe_3room = {}
        oracle_3room = [
            ('error_601', 22001, '客厅', '260001'),
            ('error_703', 22550, '主卧', '120003'),
            ('error_733', 22551, '次卧', '120003'),
            ('error_763', 22549, '儿童房', '120003'),
        ]
        for i, (error_code, device_sn, ori_room_name, pc) in enumerate(oracle_3room):
            fe = FaultEvent.objects.create(
                specific_part='1-1-16-1601',
                device_sn=str(device_sn),
                product_code=pc,
                fault_code=error_code,
                fault_type='comm',
                fault_message='通信故障',
                severity='error',
                first_seen_at=now - timedelta(hours=i + 1),
                last_seen_at=now - timedelta(minutes=(i + 1) * 10),
                is_active=True,
            )
            self.fe_3room[ori_room_name] = fe

    def tearDown(self):
        _reset_cache()

    def _get(self, params):
        resp = self.client.get(
            self.list_url + '?page_size=100'
            + '&first_seen_after=2000-01-01T00:00:00'
            + f'&{params}',
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()['results']

    def test_4room_study_room_panel_returns_1(self):
        """关键回归：3-1-602 点书房温控面板 -> 1 条（device_sn=22552，ori_room_name='书房'）。"""
        results = self._get('specific_part=3-1-602&sub_type=study_room_panel')
        self.assertEqual(
            len(results), 1,
            f'3-1-602 + study_room_panel 期望 1 条，实际 {len(results)} 条',
        )
        self.assertEqual(results[0]['device_sn'], '22552')

    def test_4room_children_room_panel_returns_1(self):
        """关键回归：3-1-602 点儿童房温控面板 -> 1 条（device_sn=22555，ori_room_name='儿童房'）。"""
        results = self._get('specific_part=3-1-602&sub_type=children_room_panel')
        self.assertEqual(
            len(results), 1,
            f'3-1-602 + children_room_panel 期望 1 条，实际 {len(results)} 条',
        )
        self.assertEqual(results[0]['device_sn'], '22555')

    def test_4room_master_bedroom_panel_returns_1(self):
        """关键回归：3-1-602 点主卧温控面板 -> 1 条（device_sn=22554，ori_room_name='主卧'）。"""
        results = self._get('specific_part=3-1-602&sub_type=master_bedroom_panel')
        self.assertEqual(
            len(results), 1,
            f'3-1-602 + master_bedroom_panel 期望 1 条，实际 {len(results)} 条',
        )
        self.assertEqual(results[0]['device_sn'], '22554')

    def test_4room_secondary_bedroom_panel_returns_1(self):
        """关键回归：3-1-602 点次卧温控面板 -> 1 条（device_sn=22553，ori_room_name='次卧'）。"""
        results = self._get('specific_part=3-1-602&sub_type=secondary_bedroom_panel')
        self.assertEqual(
            len(results), 1,
            f'3-1-602 + secondary_bedroom_panel 期望 1 条，实际 {len(results)} 条',
        )
        self.assertEqual(results[0]['device_sn'], '22553')

    def test_3room_study_room_panel_returns_0(self):
        """关键回归：1-1-16-1601（3 房）点书房温控面板 -> 0 条（3 房无书房设备）。"""
        results = self._get('specific_part=1-1-16-1601&sub_type=study_room_panel')
        self.assertEqual(
            len(results), 0,
            f'3 房 1-1-16-1601 + study_room_panel 期望 0 条，实际 {len(results)} 条',
        )
