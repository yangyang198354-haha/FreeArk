"""
业主管理 Sprint-2 功能测试套件
==============================

覆盖用户故事：
  US-01: 设备列表页回滚（page_size 上限 50、无同步按钮相关后端行为）
  US-02: 业主列表新增 room_count 字段（annotate 方案，无 N+1）
  US-03: 业主设备树查看 API（GET /api/owners/<pk>/device-tree/）
  US-04: 业主批量同步（全量，后端零改动验证）

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_owner_sprint2 --verbosity=2
"""

from django.test import TestCase, tag
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import (
    CustomUser, OwnerInfo,
    DeviceFloor, DeviceRoom, DeviceNode,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_admin(username='admin_s2', password='adminpass'):
    user = CustomUser.objects.create_user(username=username, password=password, role='admin')
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _make_user(username='user_s2', password='userpass'):
    user = CustomUser.objects.create_user(username=username, password=password, role='user')
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _make_owner(specific_part='1-1-2-201', **kwargs):
    defaults = {
        'location_name': '成都乐府（二仙桥）-1-1-201',
        'building': '1栋',
        'unit': '1单元',
        'floor': '2楼',
        'room_number': '201',
        'bind_status': '已绑定',
        'ip_address': '192.168.1.4',
        'unique_id': '89dbe11564b1a4e0',
        'plc_ip_address': '192.168.1.5',
    }
    defaults.update(kwargs)
    return OwnerInfo.objects.create(specific_part=specific_part, **defaults)


def _make_device_tree(owner, n_floors=2, n_rooms_per_floor=3, n_devices_per_room=2):
    """为指定业主创建完整设备树，返回 (floors, total_room_count, total_device_count)。"""
    total_rooms = 0
    for floor_no in range(1, n_floors + 1):
        floor = DeviceFloor.objects.create(
            owner=owner,
            floor_no=floor_no,
            floor_name=f'{floor_no}楼',
        )
        for room_idx in range(1, n_rooms_per_floor + 1):
            room = DeviceRoom.objects.create(
                floor=floor,
                room_name=f'房间{room_idx}',
                ori_room_name=f'Room{room_idx}',
                room_type=room_idx,
            )
            total_rooms += 1
            for dev_idx in range(1, n_devices_per_room + 1):
                DeviceNode.objects.create(
                    room=room,
                    device_sn=floor_no * 1000 + room_idx * 10 + dev_idx,
                    device_name=f'设备{dev_idx}',
                    system_flag=2 if dev_idx == 1 else 1,
                    product_code=f'P{dev_idx:04d}',
                    category_code=dev_idx,
                )
    return total_rooms


# ===========================================================================
# TC-US01: page_size 上限回滚验证（后端 device-list 接口）
# ===========================================================================

@tag('integration')
class DeviceListPageSizeTest(TestCase):
    """US-01: 设备列表接口 page_size 上限回滚至 50。"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        # 创建 60 条业主记录
        for i in range(1, 61):
            OwnerInfo.objects.create(
                specific_part=f'1-1-1-{100 + i}',
                building='1栋',
                unit='1单元',
                floor='1楼',
                room_number=str(100 + i),
            )

    def test_tc_us01_001_page_size_capped_at_50(self):
        """TC-US01-001: page_size=100 请求，实际返回最多 50 条。"""
        resp = self.client.get('/api/device-management/device-list/?page=1&page_size=100')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get('results', [])
        self.assertLessEqual(
            len(results), 50,
            f'期望最多 50 条，实际返回 {len(results)} 条'
        )

    def test_tc_us01_002_page_size_2000_capped_at_50(self):
        """TC-US01-002: page_size=2000 请求（BUG-FIX 前的值），实际返回最多 50 条。"""
        resp = self.client.get('/api/device-management/device-list/?page=1&page_size=2000')
        self.assertEqual(resp.status_code, 200)
        results = resp.json().get('results', [])
        self.assertLessEqual(len(results), 50)

    def test_tc_us01_003_page_size_20_normal(self):
        """TC-US01-003: page_size=20 正常返回 20 条（当总数 > 20）。"""
        resp = self.client.get('/api/device-management/device-list/?page=1&page_size=20')
        self.assertEqual(resp.status_code, 200)
        results = resp.json().get('results', [])
        self.assertEqual(len(results), 20)

    def test_tc_us01_004_page_size_50_boundary(self):
        """TC-US01-004: page_size=50 是允许的边界值，返回恰好 50 条。"""
        resp = self.client.get('/api/device-management/device-list/?page=1&page_size=50')
        self.assertEqual(resp.status_code, 200)
        results = resp.json().get('results', [])
        self.assertEqual(len(results), 50)

    def test_tc_us01_005_page_size_51_capped(self):
        """TC-US01-005: page_size=51 超过上限，实际等效 page_size=50。"""
        resp = self.client.get('/api/device-management/device-list/?page=1&page_size=51')
        self.assertEqual(resp.status_code, 200)
        results = resp.json().get('results', [])
        self.assertLessEqual(len(results), 50)


# ===========================================================================
# TC-US02: 业主列表 room_count 字段
# ===========================================================================

@tag('integration')
class OwnerRoomCountTest(TestCase):
    """US-02: /api/owners/ 列表响应含正确 room_count，无 N+1。"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

    def test_tc_us02_001_room_count_zero_no_tree(self):
        """TC-US02-001: 业主尚未同步设备树，room_count=0。"""
        _make_owner(specific_part='9-1-1-101', unique_id='')
        resp = self.client.get('/api/owners/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['room_count'], 0)

    def test_tc_us02_002_room_count_correct_single_floor(self):
        """TC-US02-002: 1 楼 3 房间，room_count=3。"""
        owner = _make_owner(specific_part='9-1-1-102')
        _make_device_tree(owner, n_floors=1, n_rooms_per_floor=3, n_devices_per_room=1)
        resp = self.client.get('/api/owners/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        owner_data = next(o for o in data if o['specific_part'] == '9-1-1-102')
        self.assertEqual(owner_data['room_count'], 3)

    def test_tc_us02_003_room_count_correct_multi_floor(self):
        """TC-US02-003: 2 楼各 3 房间，room_count=6。"""
        owner = _make_owner(specific_part='9-1-1-103')
        _make_device_tree(owner, n_floors=2, n_rooms_per_floor=3, n_devices_per_room=2)
        resp = self.client.get('/api/owners/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        owner_data = next(o for o in data if o['specific_part'] == '9-1-1-103')
        self.assertEqual(owner_data['room_count'], 6)

    def test_tc_us02_004_room_count_multiple_owners_independent(self):
        """TC-US02-004: 多业主各自 room_count 正确，互不影响。"""
        o1 = _make_owner(specific_part='9-1-1-111')
        o2 = _make_owner(specific_part='9-1-1-112')
        _make_device_tree(o1, n_floors=1, n_rooms_per_floor=2, n_devices_per_room=1)
        _make_device_tree(o2, n_floors=3, n_rooms_per_floor=4, n_devices_per_room=1)

        resp = self.client.get('/api/owners/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        rc = {o['specific_part']: o['room_count'] for o in data}
        self.assertEqual(rc['9-1-1-111'], 2)
        self.assertEqual(rc['9-1-1-112'], 12)

    def test_tc_us02_005_room_count_in_response_field(self):
        """TC-US02-005: room_count 字段存在于所有列表条目中。"""
        for i in range(3):
            _make_owner(specific_part=f'9-2-1-{200 + i}')
        resp = self.client.get('/api/owners/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        for item in data:
            self.assertIn('room_count', item, f'条目 {item["specific_part"]} 缺少 room_count 字段')

    def test_tc_us02_006_no_n_plus_1_query(self):
        """TC-US02-006: 验证 room_count 由 annotate 生成，非 N+1（使用 django.test.utils.CaptureQueriesContext）。"""
        # 创建 5 个业主，每个有 2 层 3 房间
        for i in range(5):
            o = _make_owner(specific_part=f'9-3-1-{300 + i}')
            _make_device_tree(o, n_floors=2, n_rooms_per_floor=3, n_devices_per_room=1)

        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get('/api/owners/?page=1&page_size=20')
        self.assertEqual(resp.status_code, 200)

        # annotate 方案：列表请求总查询数应 <= 5（认证+列表count+列表data等）
        # 非 annotate 方案在 5 个业主时将产生 5+5=10+ 额外查询
        query_count = len(ctx.captured_queries)
        self.assertLessEqual(
            query_count, 8,
            f'期望 ≤8 条 SQL（annotate 无 N+1），实际 {query_count} 条。\n'
            + '\n'.join(q['sql'][:120] for q in ctx.captured_queries)
        )


# ===========================================================================
# TC-US03: 业主设备树查看 API
# ===========================================================================

@tag('integration')
class OwnerDeviceTreeAPITest(TestCase):
    """US-03: GET /api/owners/<pk>/device-tree/ 权限与数据正确性。"""

    def setUp(self):
        self.client = APIClient()
        self.admin, self.admin_token = _make_admin()
        self.user, self.user_token = _make_user()

    def _auth_admin(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')

    def _auth_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token}')

    def _no_auth(self):
        self.client.credentials()

    def test_tc_us03_001_unauthenticated_returns_401(self):
        """TC-US03-001: 未认证请求返回 401。"""
        owner = _make_owner(specific_part='8-1-1-101')
        self._no_auth()
        resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(resp.status_code, 401)

    def test_tc_us03_002_regular_user_can_access(self):
        """TC-US03-002: 普通用户可访问（所有登录用户可见，Q-03-2）。"""
        owner = _make_owner(specific_part='8-1-1-102')
        self._auth_user()
        resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

    def test_tc_us03_003_admin_can_access(self):
        """TC-US03-003: 管理员可访问。"""
        owner = _make_owner(specific_part='8-1-1-103')
        self._auth_admin()
        resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(resp.status_code, 200)

    def test_tc_us03_004_not_found_returns_404(self):
        """TC-US03-004: 不存在的 pk 返回 404。"""
        self._auth_user()
        resp = self.client.get('/api/owners/999999/device-tree/')
        self.assertEqual(resp.status_code, 404)

    def test_tc_us03_005_empty_tree_no_floors(self):
        """TC-US03-005: 尚未同步的业主，floors 为空列表（空状态正确处理）。"""
        owner = _make_owner(specific_part='8-1-1-104')
        self._auth_user()
        resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(data['specific_part'], '8-1-1-104')
        self.assertEqual(data['floors'], [])

    def test_tc_us03_006_full_tree_structure(self):
        """TC-US03-006: 完整设备树数据结构正确（2 楼 × 3 房间 × 2 设备）。"""
        owner = _make_owner(specific_part='8-1-1-105')
        _make_device_tree(owner, n_floors=2, n_rooms_per_floor=3, n_devices_per_room=2)
        self._auth_user()
        resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']

        self.assertEqual(data['specific_part'], '8-1-1-105')
        self.assertEqual(len(data['floors']), 2)

        # 验证第一楼层
        floor1 = data['floors'][0]
        self.assertIn('floor_no', floor1)
        self.assertIn('floor_name', floor1)
        self.assertIn('rooms', floor1)
        self.assertEqual(len(floor1['rooms']), 3)

        # 验证第一房间第一设备
        room1 = floor1['rooms'][0]
        self.assertIn('room_name', room1)
        self.assertIn('devices', room1)
        self.assertEqual(len(room1['devices']), 2)

        dev1 = room1['devices'][0]
        self.assertIn('device_sn', dev1)
        self.assertIn('device_name', dev1)
        self.assertIn('system_flag', dev1)
        self.assertIn('product_code', dev1)
        self.assertIn('category_code', dev1)

    def test_tc_us03_007_response_contains_location_name(self):
        """TC-US03-007: 响应包含 location_name 字段。"""
        owner = _make_owner(specific_part='8-1-1-106', location_name='测试坐落地址')
        self._auth_user()
        resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['data']['location_name'], '测试坐落地址')

    def test_tc_us03_008_no_n_plus_1_prefetch(self):
        """TC-US03-008: prefetch_related 确保设备树查询无 N+1（floors×rooms×devices 均预取）。"""
        owner = _make_owner(specific_part='8-1-1-107')
        _make_device_tree(owner, n_floors=3, n_rooms_per_floor=4, n_devices_per_room=3)
        self._auth_user()

        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(resp.status_code, 200)

        # prefetch 方案：1(get_object) + 3(prefetch floors/rooms/devices) + auth = ~6
        #   auth 自 v0.9.0 起为滑动窗口认证：token SELECT + TokenActivity SELECT(+节流 UPDATE)，
        #   为 O(1) 常量开销，不随设备数增长，故阈值由 8 上调至 9（N+1 防护意图不变）。
        # N+1 方案：1 + floors*rooms*devices 量级（本例 3*4*3=36+，远超阈值）
        query_count = len(ctx.captured_queries)
        self.assertLessEqual(
            query_count, 9,
            f'期望 ≤9 条 SQL（prefetch_related 无 N+1），实际 {query_count} 条'
        )

    def test_tc_us03_009_device_system_flag_values(self):
        """TC-US03-009: system_flag=2 的设备为主机，system_flag=1 为子机，字段值正确透传。"""
        owner = _make_owner(specific_part='8-1-1-108')
        floor = DeviceFloor.objects.create(owner=owner, floor_no=1, floor_name='1楼')
        room = DeviceRoom.objects.create(floor=floor, room_name='客厅', ori_room_name='LivingRoom', room_type=1)
        DeviceNode.objects.create(
            room=room, device_sn=1001, device_name='主机', system_flag=2,
            product_code='MAIN', category_code=5
        )
        DeviceNode.objects.create(
            room=room, device_sn=1002, device_name='子机', system_flag=1,
            product_code='SUB', category_code=3
        )
        self._auth_user()
        resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        devices = resp.json()['data']['floors'][0]['rooms'][0]['devices']
        flags = {d['device_sn']: d['system_flag'] for d in devices}
        self.assertEqual(flags[1001], 2)
        self.assertEqual(flags[1002], 1)


# ===========================================================================
# TC-US04: 批量同步 — 后端行为验证
# ===========================================================================

@tag('integration')
class OwnerBatchSyncTest(TestCase):
    """US-04: POST /api/device-management/screen-device-tree/batch-sync/ 全量回退行为。"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

        # 创建 5 条有效 unique_id 的业主 + 2 条无 unique_id 的业主
        for i in range(5):
            _make_owner(
                specific_part=f'7-1-1-{100 + i}',
                unique_id=f'uid_valid_{i:04d}'
            )
        for j in range(2):
            _make_owner(
                specific_part=f'7-1-2-{200 + j}',
                unique_id=''
            )

    def test_tc_us04_001_no_auth_returns_401(self):
        """TC-US04-001: 未认证请求返回 401。"""
        self.client.credentials()
        resp = self.client.post(
            '/api/device-management/screen-device-tree/batch-sync/',
            {}, format='json'
        )
        self.assertEqual(resp.status_code, 401)

    def test_tc_us04_002_empty_body_triggers_full_sync(self):
        """TC-US04-002: 不传 specific_parts，后端用全量 OwnerInfo.exclude(unique_id='') 回退。
        返回 202，total = 有效 unique_id 的业主数（5）。
        """
        from unittest.mock import patch
        with patch('api.device_tree_sync.start_batch_sync') as mock_start:
            mock_start.return_value = ('fake-task-id', 5)
            resp = self.client.post(
                '/api/device-management/screen-device-tree/batch-sync/',
                {}, format='json'
            )
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn('task_id', data)
        self.assertEqual(data['total'], 5)

        # 验证 start_batch_sync 被调用时传入的 specific_parts 只含有 unique_id 非空的记录
        call_args = mock_start.call_args
        sp_arg = call_args[0][0]  # 第一个位置参数
        self.assertEqual(len(sp_arg), 5, f'期望 5 条，实际 {len(sp_arg)} 条: {sp_arg}')
        for sp in sp_arg:
            owner = OwnerInfo.objects.get(specific_part=sp)
            self.assertNotEqual(owner.unique_id, '', f'{sp} 的 unique_id 为空，不应参与同步')

    def test_tc_us04_003_explicit_specific_parts_overrides_full(self):
        """TC-US04-003: 传入 specific_parts 列表时，使用指定列表（不回退全量）。"""
        from unittest.mock import patch
        targets = ['7-1-1-100', '7-1-1-101']
        with patch('api.device_tree_sync.start_batch_sync') as mock_start:
            mock_start.return_value = ('fake-task-id-2', 2)
            resp = self.client.post(
                '/api/device-management/screen-device-tree/batch-sync/',
                {'specific_parts': targets}, format='json'
            )
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()['total'], 2)
        sp_arg = mock_start.call_args[0][0]
        self.assertEqual(sorted(sp_arg), sorted(targets))

    def test_tc_us04_004_task_status_endpoint_reachable(self):
        """TC-US04-004: GET /api/.../batch-sync/<task_id>/ 对不存在 task_id 返回 404。"""
        resp = self.client.get(
            '/api/device-management/screen-device-tree/batch-sync/nonexistent-task/'
        )
        self.assertEqual(resp.status_code, 404)

    def test_tc_us04_005_exclude_empty_unique_id(self):
        """TC-US04-005: 全量回退时，unique_id='' 的业主被排除在外（回退逻辑验证）。"""
        from unittest.mock import patch
        with patch('api.device_tree_sync.start_batch_sync') as mock_start:
            mock_start.return_value = ('task-x', 5)
            self.client.post(
                '/api/device-management/screen-device-tree/batch-sync/',
                {}, format='json'
            )
        sp_arg = mock_start.call_args[0][0]
        # 验证空 unique_id 对应的 specific_part 不在同步列表中
        for sp in ['7-1-2-200', '7-1-2-201']:
            self.assertNotIn(sp, sp_arg, f'{sp}（unique_id 为空）不应出现在同步列表中')


# ===========================================================================
# TC-INT: 集成测试 — 跨 US 场景
# ===========================================================================

@tag('integration')
class OwnerIntegrationTest(TestCase):
    """跨用户故事集成测试：验证 room_count + device-tree 的一致性。"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

    def test_tc_int_001_room_count_consistent_with_device_tree(self):
        """TC-INT-001: 列表的 room_count 与 device-tree 端点的 floors[*].rooms 总数一致。"""
        owner = _make_owner(specific_part='6-1-1-601')
        _make_device_tree(owner, n_floors=2, n_rooms_per_floor=4, n_devices_per_room=2)

        # 获取列表中的 room_count
        list_resp = self.client.get(f'/api/owners/?search={owner.specific_part}')
        self.assertEqual(list_resp.status_code, 200)
        list_data = list_resp.json()['data']
        self.assertEqual(len(list_data), 1)
        room_count_from_list = list_data[0]['room_count']

        # 获取 device-tree 中的实际房间数
        tree_resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(tree_resp.status_code, 200)
        floors = tree_resp.json()['data']['floors']
        room_count_from_tree = sum(len(f['rooms']) for f in floors)

        self.assertEqual(
            room_count_from_list, room_count_from_tree,
            f'列表 room_count={room_count_from_list} 与设备树实际房间数 {room_count_from_tree} 不一致'
        )

    def test_tc_int_002_room_count_zero_owner_has_empty_tree(self):
        """TC-INT-002: room_count=0 的业主，device-tree 接口返回 floors=[]。"""
        owner = _make_owner(specific_part='6-1-1-602')

        list_resp = self.client.get(f'/api/owners/?search={owner.specific_part}')
        room_count = list_resp.json()['data'][0]['room_count']
        self.assertEqual(room_count, 0)

        tree_resp = self.client.get(f'/api/owners/{owner.id}/device-tree/')
        self.assertEqual(tree_resp.json()['data']['floors'], [])

    def test_tc_int_003_owner_list_still_works_after_annotate(self):
        """TC-INT-003: 添加 annotate 后，原有过滤（building/unit/search）功能不受影响。"""
        owner_a = _make_owner(specific_part='6-2-1-611', building='3栋')
        owner_b = _make_owner(specific_part='6-2-1-612', building='4栋')
        _make_device_tree(owner_a, n_floors=1, n_rooms_per_floor=2, n_devices_per_room=1)

        resp = self.client.get('/api/owners/?building=3栋')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['specific_part'], '6-2-1-611')
        self.assertEqual(data[0]['room_count'], 2)
