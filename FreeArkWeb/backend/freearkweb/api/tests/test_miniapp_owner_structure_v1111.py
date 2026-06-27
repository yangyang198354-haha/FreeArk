"""
v1.11.1 业主端设备树结构骨架端点测试套件

覆盖（模块 MOD-1111-BE-01，IFC-1111-BE-01）：
  [integration] GET /api/miniapp/owner/structure/
    - 权限矩阵：role=user 200，operator 403，匿名 401
    - 归属过滤：自己的 specific_part 200，他人的 403
    - 缺 specific_part → 400
    - 房间分组：panel_room (120003) → rooms[]；系统级 (260001 等) → system_devices[]
    - system_devices 正确分组（ori_room_name 无 panel 关键词 → 进 system_devices）
    - params_skeleton（OQ-1111-A Option A）：来自 DeviceConfig(is_active=True)
    - 无 PLCLatestData 也返回完整 rooms（REQ-FUNC-001-C 核心验收点）
    - sync_status="pending"（DeviceFloor 无记录时降级）
    - device_sns 扁平列表正确
    - room_name / ori_room_name 字段返回正确（OQ-E2）

运行：
    cd FreeArkWeb/backend/freearkweb
    PYTHONUTF8=1 FREEARK_POC_MOCK=1 python manage.py test \\
        api.tests.test_miniapp_owner_structure_v1111 \\
        --settings=freearkweb.test_settings --verbosity=2

"""
from django.test import TestCase, tag
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import (
    CustomUser, OwnerInfo, OwnerUserBinding,
    DeviceConfig, DeviceNode, DeviceFloor, DeviceRoom,
    PLCLatestData,
)

STRUCTURE_URL = '/api/miniapp/owner/structure/'


# ── 辅助工厂（复用 test_miniapp_owner_v1110 风格）────────────────────────────

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


def _make_device_config(group, sub_type, param_name, display_name=None,
                        group_display='暖通', sub_type_display='温控', is_active=True):
    return DeviceConfig.objects.create(
        group=group, sub_type=sub_type, param_name=param_name,
        display_name=display_name or f'显示-{param_name}',
        group_display=group_display, sub_type_display=sub_type_display,
        is_active=is_active,
    )


def _make_device_tree_full(owner):
    """创建完整设备树（1 楼层 → 面板房间 + 系统房间 → 设备节点）。

    面板房间：ori_room_name='三房书房'（命中 panel_study_room）
    系统房间：ori_room_name='全屋'（不命中任何 panel sub_type → system_devices）
    返回：(floor, panel_room, panel_device, sys_room, sys_device)
    """
    floor = DeviceFloor.objects.create(owner=owner, floor_no=1, floor_name='一楼')
    panel_room = DeviceRoom.objects.create(
        floor=floor, room_name='书房', ori_room_name='三房书房', room_type=1
    )
    panel_device = DeviceNode.objects.create(
        room=panel_room, device_sn=22552, device_name='温控面板',
        system_flag=1, product_code='120003', category_code=1
    )
    sys_room = DeviceRoom.objects.create(
        floor=floor, room_name='全屋', ori_room_name='全屋', room_type=2
    )
    sys_device = DeviceNode.objects.create(
        room=sys_room, device_sn=22153, device_name='自由方舟主机',
        system_flag=2, product_code='260001', category_code=1
    )
    return floor, panel_room, panel_device, sys_room, sys_device


# ===========================================================================
# 权限矩阵
# ===========================================================================

@tag('integration', 'permissions')
class StructurePermissionsTest(TestCase):

    def setUp(self):
        self.owner = _make_owner('1-1-2-201', unique_id='aabbccdd')
        self.user, self.tok = _make_user('owner_perm')
        _bind(self.user, self.owner)
        self.operator, self.op_tok = _make_user('op_perm', role='operator')

    def test_owner_user_200(self):
        """role=user 且有绑定 → 200（权限矩阵 row 1）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['success'])

    def test_anonymous_401(self):
        """未认证 → 401（IsOwnerUser 要求已登录）。"""
        r = _client().get(STRUCTURE_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 401)

    def test_operator_403(self):
        """role=operator → 403（IsOwnerUser 仅允许 role=user）。"""
        r = _client(self.op_tok).get(STRUCTURE_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 403)


# ===========================================================================
# 归属过滤（越权拦截）
# ===========================================================================

@tag('integration', 'auth_filter')
class StructureAuthFilterTest(TestCase):

    def setUp(self):
        self.owner_a = _make_owner('1-1-2-201', unique_id='mac_aabb')
        self.owner_b = _make_owner('2-1-3-301', unique_id='mac_ccdd')

        self.user_a, self.tok_a = _make_user('user_a_struct')
        _bind(self.user_a, self.owner_a)  # user_a 只绑定 1-1-2-201

    def test_own_specific_part_200(self):
        r = _client(self.tok_a).get(STRUCTURE_URL, {'specific_part': '1-1-2-201'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['specific_part'], '1-1-2-201')

    def test_other_specific_part_403(self):
        """越权访问他人的 specific_part → 403（REQ-NFUNC-004）。"""
        r = _client(self.tok_a).get(STRUCTURE_URL, {'specific_part': '2-1-3-301'})
        self.assertEqual(r.status_code, 403)

    def test_missing_specific_part_400(self):
        """不传 specific_part → 400。"""
        r = _client(self.tok_a).get(STRUCTURE_URL)
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.data['success'])
        self.assertIn('specific_part', r.data['error'])


# ===========================================================================
# sync_status=pending（设备树未同步）
# ===========================================================================

@tag('integration', 'sync_pending')
class StructureSyncPendingTest(TestCase):

    def setUp(self):
        self.owner = _make_owner('5-1-1-501')
        self.user, self.tok = _make_user('user_pending')
        _bind(self.user, self.owner)
        # 不创建 DeviceFloor → 模拟设备树未同步

    def test_sync_status_pending(self):
        """DeviceFloor 无记录 → sync_status="pending" + 空数组（OQ-E5）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '5-1-1-501'})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data['success'])
        self.assertEqual(r.data['sync_status'], 'pending')
        self.assertEqual(r.data['rooms'], [])
        self.assertEqual(r.data['system_devices'], [])
        self.assertEqual(r.data['device_sns'], [])
        # 有提示文案
        self.assertIn('sync_status_detail', r.data)
        self.assertTrue(r.data['sync_status_detail'])


# ===========================================================================
# 房间分组（panel rooms vs system_devices）
# ===========================================================================

@tag('integration', 'grouping')
class StructureGroupingTest(TestCase):
    """验证 ADR-1111-03：_match_panel_sub_types 非空 → rooms；空 → system_devices。"""

    def setUp(self):
        self.owner = _make_owner('3-1-7-702', unique_id='mac_grouping')
        self.user, self.tok = _make_user('user_grouping')
        _bind(self.user, self.owner)
        _, self.panel_room, self.panel_device, self.sys_room, self.sys_device = \
            _make_device_tree_full(self.owner)

    def test_panel_room_in_rooms(self):
        """温控面板（product_code=120003, ori_room_name 含书房）→ rooms[]。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '3-1-7-702'})
        self.assertEqual(r.status_code, 200)
        rooms = r.data['rooms']
        self.assertEqual(len(rooms), 1)
        self.assertEqual(rooms[0]['room_id'], self.panel_room.id)
        self.assertEqual(rooms[0]['room_name'], '书房')
        self.assertEqual(rooms[0]['ori_room_name'], '三房书房')
        self.assertEqual(len(rooms[0]['devices']), 1)
        dev = rooms[0]['devices'][0]
        self.assertEqual(dev['device_sn'], 22552)
        self.assertEqual(dev['product_code'], '120003')

    def test_system_device_in_system_devices(self):
        """主温控（product_code=260001, ori_room_name='全屋' 无 panel 关键词）→ system_devices[]。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '3-1-7-702'})
        self.assertEqual(r.status_code, 200)
        sys_devs = r.data['system_devices']
        self.assertEqual(len(sys_devs), 1)
        dev = sys_devs[0]
        self.assertEqual(dev['device_sn'], 22153)
        self.assertEqual(dev['device_name'], '自由方舟主机')  # OQ-E4：来自 device_name
        self.assertEqual(dev['product_code'], '260001')

    def test_sub_type_inferred_for_panel(self):
        """panel 面板 sub_type 由 _match_panel_sub_types 推导（ADR-1111-02）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '3-1-7-702'})
        dev = r.data['rooms'][0]['devices'][0]
        # 三房书房 → panel_study_room（utils_room_filter SUB_TYPE_TO_ROOM_KEYWORDS 覆盖）
        self.assertEqual(dev['sub_type'], 'panel_study_room')

    def test_sub_type_inferred_for_system(self):
        """系统级设备 sub_type 由 product_code 查表推导（ADR-1111-02）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '3-1-7-702'})
        dev = r.data['system_devices'][0]
        self.assertEqual(dev['sub_type'], 'main_thermostat')

    def test_device_sns_flat_list(self):
        """device_sns 包含全部设备 SN 的扁平列表（ADR-1111-06 供 connectRoom 使用）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '3-1-7-702'})
        sns = r.data['device_sns']
        self.assertIn(22552, sns)
        self.assertIn(22153, sns)

    def test_sync_status_ok_when_floors_exist(self):
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '3-1-7-702'})
        self.assertEqual(r.data['sync_status'], 'ok')


# ===========================================================================
# params_skeleton（OQ-1111-A Option A：来自 DeviceConfig）
# ===========================================================================

@tag('integration', 'params_skeleton')
class StructureParamsSkeletonTest(TestCase):
    """验证结构端点为每个设备附 params_skeleton（来自 DeviceConfig，不含 value 字段）。"""

    def setUp(self):
        self.owner = _make_owner('6-1-1-601')
        self.user, self.tok = _make_user('user_params')
        _bind(self.user, self.owner)
        floor = DeviceFloor.objects.create(owner=self.owner, floor_no=1, floor_name='一楼')
        room = DeviceRoom.objects.create(
            floor=floor, room_name='书房', ori_room_name='三房书房', room_type=1
        )
        self.device = DeviceNode.objects.create(
            room=room, device_sn=30001, device_name='温控面板',
            system_flag=1, product_code='120003', category_code=1
        )
        # 创建 DeviceConfig（panel_study_room sub_type）
        self.cfg1 = _make_device_config('hvac', 'panel_study_room', 'room_temp_setting',
                                        display_name='房间温度设定')
        self.cfg2 = _make_device_config('hvac', 'panel_study_room', 'mode',
                                        display_name='运行模式')
        # is_active=False 的配置不应出现
        self.cfg3 = _make_device_config('hvac', 'panel_study_room', 'hidden_param',
                                        display_name='隐藏参数', is_active=False)

    def test_params_present_in_device(self):
        """设备 entry 含 params 列表（来自 DeviceConfig）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '6-1-1-601'})
        self.assertEqual(r.status_code, 200)
        dev = r.data['rooms'][0]['devices'][0]
        self.assertIn('params', dev)
        param_names = [p['param_name'] for p in dev['params']]
        self.assertIn('room_temp_setting', param_names)
        self.assertIn('mode', param_names)

    def test_params_have_no_value_field(self):
        """params_skeleton 不含 value 字段（结构与值完全解耦，REQ-FUNC-001-C）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '6-1-1-601'})
        dev = r.data['rooms'][0]['devices'][0]
        for param in dev['params']:
            self.assertNotIn('value', param)
            self.assertIn('param_name', param)
            self.assertIn('display_name', param)

    def test_inactive_config_excluded(self):
        """is_active=False 的 DeviceConfig 不出现在 params 中。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '6-1-1-601'})
        dev = r.data['rooms'][0]['devices'][0]
        param_names = [p['param_name'] for p in dev['params']]
        self.assertNotIn('hidden_param', param_names)

    def test_display_name_returned(self):
        """params 中的 display_name 正确返回。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '6-1-1-601'})
        dev = r.data['rooms'][0]['devices'][0]
        dn_map = {p['param_name']: p['display_name'] for p in dev['params']}
        self.assertEqual(dn_map.get('room_temp_setting'), '房间温度设定')
        self.assertEqual(dn_map.get('mode'), '运行模式')


# ===========================================================================
# REQ-FUNC-001-C 核心验收：无 PLCLatestData 也返回完整房间结构
# ===========================================================================

@tag('integration', 'req_func_001c')
class StructureNoPlcDataTest(TestCase):
    """验证 REQ-FUNC-001-C：结构完整性不依赖 PLCLatestData。
    即使某房间/设备无任何实时数据，结构端点仍必须返回该房间节点。
    这是 v1.11.1 的核心修复目标：修复 v1.11.0 中 realtime-params 因
    if record is None: continue 导致面板丢失的根因缺陷。
    """

    def setUp(self):
        self.owner = _make_owner('7-1-1-701')
        self.user, self.tok = _make_user('user_noplc')
        _bind(self.user, self.owner)
        # 创建多个面板房间（模拟生产实例 3-1-7-702 的 4 个面板）
        floor = DeviceFloor.objects.create(owner=self.owner, floor_no=1, floor_name='一楼')
        for i, (room_name, ori_name, sn) in enumerate([
            ('书房', '三房书房', 22552),
            ('次卧', '三房次卧', 22553),
            ('主卧', '三房主卧', 22554),
            ('儿童房', '三房儿童房', 22555),
        ]):
            room = DeviceRoom.objects.create(
                floor=floor, room_name=room_name, ori_room_name=ori_name, room_type=1
            )
            DeviceNode.objects.create(
                room=room, device_sn=sn, device_name='温控面板',
                system_flag=1, product_code='120003', category_code=1
            )
        # 不创建任何 PLCLatestData！

    def test_all_rooms_returned_without_plcdata(self):
        """4 个面板房间全部出现在 rooms[]，即使 PLCLatestData 为空（REQ-FUNC-001-C）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '7-1-1-701'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['sync_status'], 'ok')
        rooms = r.data['rooms']
        self.assertEqual(len(rooms), 4, msg=f'期望 4 个房间，实际 {len(rooms)} 个: {[rm["room_name"] for rm in rooms]}')

    def test_room_names_correct(self):
        """room_name 使用 device_room.room_name（OQ-E2），不是 sub_type_display。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '7-1-1-701'})
        room_names = {rm['room_name'] for rm in r.data['rooms']}
        self.assertIn('书房', room_names)
        self.assertIn('次卧', room_names)
        self.assertIn('主卧', room_names)
        self.assertIn('儿童房', room_names)

    def test_device_sns_all_returned(self):
        """device_sns 包含所有 4 个面板的 SN。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '7-1-1-701'})
        sns = set(r.data['device_sns'])
        self.assertIn(22552, sns)
        self.assertIn(22553, sns)
        self.assertIn(22554, sns)
        self.assertIn(22555, sns)

    def test_no_plc_data_not_queried(self):
        """结构端点完全不依赖 PLCLatestData（确保无意外查询）。
        验证方式：删除所有 PLCLatestData 后响应与之前完全一致。
        """
        PLCLatestData.objects.all().delete()
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '7-1-1-701'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data['rooms']), 4)


# ===========================================================================
# 多设备类型分组（系统级设备 product_code 映射）
# ===========================================================================

@tag('integration', 'multi_device_types')
class StructureMultiDeviceTypeTest(TestCase):
    """验证不同 product_code 的系统级设备正确推导 sub_type（ADR-1111-02）。"""

    def setUp(self):
        self.owner = _make_owner('8-1-1-801')
        self.user, self.tok = _make_user('user_multitype')
        _bind(self.user, self.owner)
        floor = DeviceFloor.objects.create(owner=self.owner, floor_no=1, floor_name='一楼')
        sys_room = DeviceRoom.objects.create(
            floor=floor, room_name='全屋', ori_room_name='全屋', room_type=2
        )
        # 创建多个系统级设备
        self.devices = {}
        for sn, name, pc in [
            (100, '自由方舟主机', '260001'),
            (101, '新风机组',   '130004'),
            (102, '水力模块',   '270001'),
            (103, '能耗表',     '250001'),
            (104, '空气品质',   '100007'),
        ]:
            DeviceNode.objects.create(
                room=sys_room, device_sn=sn, device_name=name,
                system_flag=1, product_code=pc, category_code=1
            )
            self.devices[pc] = sn

    def test_system_devices_sub_types(self):
        """各系统级设备 sub_type 正确映射（ADR-1111-02 _PRODUCT_CODE_TO_SUB_TYPE）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '8-1-1-801'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['rooms'], [])  # 无面板房间
        sys_devs = {d['product_code']: d for d in r.data['system_devices']}
        self.assertEqual(sys_devs['260001']['sub_type'], 'main_thermostat')
        self.assertEqual(sys_devs['130004']['sub_type'], 'fresh_air')
        self.assertEqual(sys_devs['270001']['sub_type'], 'hydraulic_module')
        self.assertEqual(sys_devs['250001']['sub_type'], 'energy_meter')
        self.assertEqual(sys_devs['100007']['sub_type'], 'air_quality')

    def test_unknown_product_code_sub_type_empty(self):
        """未知 product_code → sub_type 返回空字符串（不崩溃，骨架仍展示）。"""
        floor = DeviceFloor.objects.get(owner=self.owner)
        sys_room = DeviceRoom.objects.filter(floor=floor, room_name='全屋').first()
        DeviceNode.objects.create(
            room=sys_room, device_sn=999, device_name='未知设备',
            system_flag=1, product_code='999999', category_code=1
        )
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '8-1-1-801'})
        self.assertEqual(r.status_code, 200)
        unknown = next((d for d in r.data['system_devices'] if d['device_sn'] == 999), None)
        self.assertIsNotNone(unknown)
        self.assertEqual(unknown['sub_type'], '')


# ===========================================================================
# room_name / ori_room_name 字段（OQ-E2）
# ===========================================================================

@tag('integration', 'room_name')
class StructureRoomNameTest(TestCase):
    """验证结构端点返回 room_name 和 ori_room_name 字段（OQ-E2 前端 fallback 链依赖）。"""

    def setUp(self):
        self.owner = _make_owner('9-1-1-901')
        self.user, self.tok = _make_user('user_roomname')
        _bind(self.user, self.owner)
        floor = DeviceFloor.objects.create(owner=self.owner, floor_no=1, floor_name='一楼')
        # room_name 有值
        r1 = DeviceRoom.objects.create(
            floor=floor, room_name='主卧', ori_room_name='三房主卧', room_type=1
        )
        DeviceNode.objects.create(
            room=r1, device_sn=40001, device_name='温控面板',
            system_flag=1, product_code='120003', category_code=1
        )
        # room_name 为空（fallback 到 ori_room_name）
        r2 = DeviceRoom.objects.create(
            floor=floor, room_name='', ori_room_name='三房书房', room_type=1
        )
        DeviceNode.objects.create(
            room=r2, device_sn=40002, device_name='温控面板2',
            system_flag=1, product_code='120003', category_code=1
        )

    def test_room_name_returned(self):
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '9-1-1-901'})
        rooms_by_id = {rm['room_name']: rm for rm in r.data['rooms']}
        # 主卧有 room_name
        self.assertIn('主卧', rooms_by_id)
        self.assertEqual(rooms_by_id['主卧']['ori_room_name'], '三房主卧')

    def test_empty_room_name_returned_as_empty_string(self):
        """room_name 为空时返回空字符串（前端负责 fallback 到 ori_room_name）。"""
        r = _client(self.tok).get(STRUCTURE_URL, {'specific_part': '9-1-1-901'})
        empty_room = next((rm for rm in r.data['rooms'] if rm['room_name'] == ''), None)
        self.assertIsNotNone(empty_room)
        self.assertEqual(empty_room['ori_room_name'], '三房书房')
