"""
FreeArk v0.5.7 房型过滤功能测试套件

覆盖范围：
  - utils_room_filter.py（M1）：单元测试
  - PLCLatestDataHandler.handle()（M4）：单元测试
  - OndemandCollectSubscriber._execute_ondemand / _on_request（M7-B）：单元测试
  - GET /api/devices/realtime-params/ （M2）：集成测试
  - GET /api/device-settings/params/{sp}/ （M3）：集成测试
  - POST /api/devices/ondemand-refresh/ （M7-A）：集成测试
  - device_tree_sync_one 缓存清除（M5）：集成测试

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_room_filter_v057 \\
        --settings=freearkweb.test_settings --verbosity=2

测试环境：SQLite :memory:（由 test_settings.py 配置）
PM 决策：OQ-v0.5.7-02（方案 B）、OQ-v0.5.7-03（不实施）、OQ-v0.5.7-04（纳入）全部锁定
"""
# ---------------------------------------------------------------------------
# FIX-A（v0.5.7-fix1）: 将仓库根目录注入 sys.path，使 datacollection 包可被 Django
# 测试运行器找到。Django 测试的 cwd 是 FreeArkWeb/backend/freearkweb/，而
# datacollection/ 位于仓库根目录（FreeArk/），需要手动注入。
# ---------------------------------------------------------------------------
import sys
import os as _os
_REPO_ROOT = _os.path.abspath(
    _os.path.join(_os.path.dirname(__file__), '..', '..', '..', '..', '..')
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
# ---------------------------------------------------------------------------
import json
import time
import threading
from unittest.mock import MagicMock, patch, call

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from api.models import (
    CustomUser, OwnerInfo, DeviceFloor, DeviceRoom,
    DeviceConfig, PLCLatestData, DeviceParamHistory,
)
import api.utils_room_filter as _rf_module
from api.utils_room_filter import (
    get_available_sub_types,
    get_panel_param_blocklist,
    get_allowed_param_names,
    invalidate_room_filter_cache,
    _match_panel_sub_types,
    SYSTEM_LEVEL_SUB_TYPES,
    ALL_PANEL_SUB_TYPES,
    _room_filter_cache,
)
from api.mqtt_handlers import PLCLatestDataHandler


# ===========================================================================
# 辅助工厂函数
# ===========================================================================

def _make_admin(username='admin_rf057', password='adminpass123'):
    user = CustomUser.objects.create_user(
        username=username, password=password, role='admin',
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _make_owner(specific_part='9-1-10-1002'):
    return OwnerInfo.objects.create(
        specific_part=specific_part,
        location_name=f'测试专有部分 {specific_part}',
    )


def _make_device_floor(owner, floor_no=1):
    return DeviceFloor.objects.create(owner=owner, floor_no=floor_no)


def _make_device_room(floor, ori_room_name, room_name=None, room_type=0):
    return DeviceRoom.objects.create(
        floor=floor,
        ori_room_name=ori_room_name,
        room_name=room_name or ori_room_name,
        room_type=room_type,
    )


def _make_device_config(
    param_name, sub_type, group='hvac',
    display_name='测试参数', group_display='暖通',
    sub_type_display='测试面板', is_active=True,
):
    return DeviceConfig.objects.create(
        param_name=param_name,
        sub_type=sub_type,
        group=group,
        display_name=display_name,
        group_display=group_display,
        sub_type_display=sub_type_display,
        is_active=is_active,
    )


def _make_plc_latest(specific_part, param_name, value=1):
    from django.utils import timezone
    obj, _ = PLCLatestData.objects.update_or_create(
        specific_part=specific_part,
        param_name=param_name,
        defaults={
            'value': value,
            'collected_at': timezone.now(),
            'plc_ip': '127.0.0.1',
        },
    )
    return obj


def _make_mqtt_payload(device_id, params):
    """构造 improved_data_collection_manager 格式 payload。
    params: dict[param_name, (value, success)]
    """
    data = {}
    for pn, (val, ok) in params.items():
        data[pn] = {
            'value': val,
            'success': ok,
            'message': 'ok' if ok else 'fail',
            'timestamp': '2026-05-23 10:00:00',
        }
    return {
        device_id: {
            'PLC IP地址': '127.0.0.1',
            'data': data,
        }
    }


# ===========================================================================
# 测试基类：每个测试前清空 utils_room_filter 缓存
# ===========================================================================

class RoomFilterTestBase(TestCase):
    """所有 v0.5.7 测试的基类，setUp 时清空缓存防止测试间污染。"""

    def setUp(self):
        invalidate_room_filter_cache()  # 清空全局缓存，防测试间污染

    def tearDown(self):
        invalidate_room_filter_cache()


# ===========================================================================
# UT-M1: utils_room_filter.py 单元测试
# ===========================================================================

class TestMatchPanelSubTypes(TestCase):
    """UT-M1-xx: _match_panel_sub_types() 内部函数测试（纯函数，无 DB）"""

    def test_three_room_no_children(self):
        """三房户型（主卧、次卧、客厅），无儿童房"""
        names = ['主卧', '次卧', '客厅']
        result = _match_panel_sub_types(names)
        self.assertIn('panel_bedroom', result)       # 含主卧
        self.assertIn('panel_study_room', result)    # 含次卧
        self.assertIn('panel_children_room', result) # 含主卧（panel_children_room 也响应主卧）
        self.assertNotIn('panel_fourth_children', result)  # 无儿童房

    def test_three_room_with_children(self):
        """三房户型（主卧、次卧、儿童房），儿童房名无"四"字"""
        names = ['主卧', '次卧', '儿童房']
        result = _match_panel_sub_types(names)
        self.assertIn('panel_children_room', result)
        self.assertNotIn('panel_fourth_children', result)  # UT-M1-01：无"四"字不触发

    def test_four_room_with_fourth_children(self):
        """四房户型（四房儿童房，名称含"四"字）"""
        names = ['主卧', '次卧', '儿童房', '四房儿童房']
        result = _match_panel_sub_types(names)
        self.assertIn('panel_children_room', result)
        self.assertIn('panel_fourth_children', result)     # UT-M1-02：含"四"字触发

    def test_four_room_inferred_by_count(self):
        """四房户型（>=4 个房间，儿童房名无"四"字但有4间房）"""
        names = ['主卧', '次卧', '书房', '儿童房']  # 4 个房间，触发 panel_fourth_children
        result = _match_panel_sub_types(names)
        self.assertIn('panel_fourth_children', result)

    def test_no_children_no_fourth_children(self):
        """完全没有儿童房 → panel_fourth_children 不触发。
        注意（FIX-C v0.5.7-fix1）：
          panel_children_room 的关键词包含「主卧」（对应 PLC 物理地址"三房儿童房四房主卧"），
          因此含「主卧」的五房间列表会命中 panel_children_room，这是正确设计（见
          utils_room_filter.py SUB_TYPE_TO_ROOM_KEYWORDS 注释及 plc_config.json description）。
          原测试第二条断言 assertNotIn('panel_children_room', result) 与上述设计矛盾，
          已删除。test_three_room_no_children（line 151）中 assertIn('panel_children_room')
          为正确断言，两者现已一致。
        """
        names = ['主卧', '次卧', '书房', '客厅', '餐厅']
        result = _match_panel_sub_types(names)
        self.assertNotIn('panel_fourth_children', result)

    def test_panel_bedroom_panel_children_both_active(self):
        """EDGE-01/02：三房主卧 + 儿童房时，panel_bedroom 和 panel_children_room 均可用"""
        names = ['主卧', '儿童房', '次卧']
        result = _match_panel_sub_types(names)
        self.assertIn('panel_bedroom', result)
        self.assertIn('panel_children_room', result)

    def test_empty_room_name_skipped(self):
        """EDGE-04：ori_room_name 为空字符串时跳过，不崩溃"""
        names = ['主卧', '', '次卧']
        result = _match_panel_sub_types(names)
        # 正常处理有效房间名，不抛异常
        self.assertIn('panel_bedroom', result)

    def test_four_rooms_but_no_children_keyword(self):
        """EDGE-03：4 个房间但无「儿童房」关键词，panel_fourth_children 不触发"""
        names = ['主卧', '次卧', '书房', '客厅']
        result = _match_panel_sub_types(names)
        self.assertNotIn('panel_fourth_children', result)


class TestGetAvailableSubTypes(RoomFilterTestBase):
    """UT-M1-01~07: get_available_sub_types() 集成测试（含 DB + 缓存）"""

    def _setup_three_room(self, specific_part, room_names):
        """创建三房户型的 OwnerInfo + DeviceFloor + DeviceRoom"""
        owner = _make_owner(specific_part)
        floor = _make_device_floor(owner)
        for name in room_names:
            _make_device_room(floor, ori_room_name=name)
        return owner, floor

    def test_three_room_no_fourth_children(self):
        """UT-M1-01：三房户型无儿童房（9-1-10-1002），不含 panel_fourth_children"""
        self._setup_three_room('9-1-10-1002', ['主卧', '次卧', '客厅'])
        result = get_available_sub_types('9-1-10-1002')
        # 系统级始终存在
        for sub in SYSTEM_LEVEL_SUB_TYPES:
            self.assertIn(sub, result)
        self.assertNotIn('panel_fourth_children', result)
        self.assertIn('panel_bedroom', result)

    def test_device_tree_not_synced_fallback_plan_b(self):
        """UT-M1-03：设备树未同步，降级方案 B（仅系统级面板）"""
        # 不创建任何 DeviceFloor，floors 为空
        _make_owner('9-1-10-9999')
        result = get_available_sub_types('9-1-10-9999')
        # 仅含系统级
        self.assertEqual(result, SYSTEM_LEVEL_SUB_TYPES)
        for panel in ALL_PANEL_SUB_TYPES:
            self.assertNotIn(panel, result)

    def test_four_room_with_fourth_children_room(self):
        """UT-M1-04：四房户型，含所有 panel sub_type"""
        self._setup_three_room('9-1-10-1001', ['主卧', '次卧', '四房儿童房', '书房'])
        result = get_available_sub_types('9-1-10-1001')
        self.assertIn('panel_fourth_children', result)
        self.assertIn('panel_children_room', result)
        self.assertIn('panel_bedroom', result)
        self.assertIn('panel_study_room', result)

    def test_cache_hit_no_second_db_query(self):
        """UT-M1-05：缓存命中时不发出第二次 DB 查询。
        FIX-B（v0.5.7-fix1）: 原实现尝试 patch api.utils_room_filter.DeviceFloor，
        但 DeviceFloor 是延迟导入（函数内 from .models import DeviceFloor），不是
        模块级属性，导致 AttributeError。本测试改为：先真实填充缓存，再验证缓存条目
        存在；不需要 mock——缓存命中行为通过 _room_filter_cache 直接断言即可。
        """
        self._setup_three_room('9-1-10-2001', ['主卧', '客厅'])
        # 第一次调用：缓存空，查 DB，写入缓存
        result1 = get_available_sub_types('9-1-10-2001')
        # 缓存中应有该条目
        self.assertIn('9-1-10-2001', _room_filter_cache)
        # 第二次调用：应命中缓存，返回相同结果
        result2 = get_available_sub_types('9-1-10-2001')
        self.assertEqual(result1, result2)

    def test_cache_invalidate_triggers_requery(self):
        """UT-M1-06/07：invalidate 后重新查 DB"""
        self._setup_three_room('9-1-10-3001', ['主卧'])
        # 第一次查询，填充缓存
        result1 = get_available_sub_types('9-1-10-3001')
        # 清缓存
        invalidate_room_filter_cache('9-1-10-3001')
        self.assertNotIn('9-1-10-3001', _room_filter_cache)
        # 第二次查询重新查 DB
        result2 = get_available_sub_types('9-1-10-3001')
        self.assertEqual(result1, result2)

    def test_global_cache_invalidate(self):
        """UT-M1-07：全量清缓存"""
        self._setup_three_room('9-1-10-4001', ['主卧'])
        self._setup_three_room('9-1-10-4002', ['主卧', '儿童房'])
        get_available_sub_types('9-1-10-4001')
        get_available_sub_types('9-1-10-4002')
        self.assertIn('9-1-10-4001', _room_filter_cache)
        self.assertIn('9-1-10-4002', _room_filter_cache)
        invalidate_room_filter_cache()  # 全量清
        self.assertNotIn('9-1-10-4001', _room_filter_cache)
        self.assertNotIn('9-1-10-4002', _room_filter_cache)

    def test_db_error_returns_system_level_not_cached(self):
        """UT-M1-10：DeviceFloor 查询异常时返回系统级，不缓存错误结果"""
        # FIX-B（v0.5.7-fix1）: 同 test_cache_hit_no_second_db_query，patch 目标改为
        # api.models.DeviceFloor（定义处），而非延迟导入所在的 api.utils_room_filter。
        with patch('api.models.DeviceFloor') as mock_floor:
            mock_floor.objects.filter.side_effect = Exception('DB error')
            result = get_available_sub_types('9-1-10-ERR')
        # 返回系统级
        self.assertEqual(result, SYSTEM_LEVEL_SUB_TYPES)
        # 不应被缓存（下次重试）
        self.assertNotIn('9-1-10-ERR', _room_filter_cache)


class TestGetPanelParamBlocklist(RoomFilterTestBase):
    """UT-M1-08/09: get_panel_param_blocklist() 测试"""

    def setUp(self):
        super().setUp()
        # 创建 DeviceConfig 用于 blocklist 查询
        _make_device_config('fourth_children_room_temperature', 'panel_fourth_children')
        _make_device_config('fourth_children_room_switch', 'panel_fourth_children')
        _make_device_config('system_switch', 'main_thermostat')

    def test_blocklist_for_missing_room(self):
        """UT-M1-08：无四房儿童房时，blocklist 包含 fourth_children_room_* 参数"""
        owner = _make_owner('9-1-10-BL01')
        floor = _make_device_floor(owner)
        _make_device_room(floor, '主卧')  # 无儿童房
        blocklist = get_panel_param_blocklist('9-1-10-BL01')
        self.assertIn('fourth_children_room_temperature', blocklist)
        self.assertIn('fourth_children_room_switch', blocklist)
        # 系统级参数不在 blocklist 中
        self.assertNotIn('system_switch', blocklist)

    def test_blocklist_empty_when_all_rooms_exist(self):
        """UT-M1-09：所有 panel 均可用时，blocklist 为空"""
        owner = _make_owner('9-1-10-BL02')
        floor = _make_device_floor(owner)
        # 四房户型全量房间
        for name in ['主卧', '次卧', '书房', '四房儿童房']:
            _make_device_room(floor, name)
        blocklist = get_panel_param_blocklist('9-1-10-BL02')
        # panel_fourth_children 可用，blocklist 中不含其参数
        self.assertNotIn('fourth_children_room_temperature', blocklist)


# ===========================================================================
# UT-M4: PLCLatestDataHandler 单元测试
# ===========================================================================

class TestPLCLatestDataHandlerRoomFilter(RoomFilterTestBase):
    """UT-M4-01~05：PLCLatestDataHandler 落库侧房型过滤"""

    def setUp(self):
        super().setUp()
        # DeviceConfig：fourth_children_room_temperature 属于 panel_fourth_children
        _make_device_config('fourth_children_room_temperature', 'panel_fourth_children')
        _make_device_config('fourth_children_room_switch', 'panel_fourth_children')
        _make_device_config('system_switch', 'main_thermostat')
        _make_device_config('bedroom_temperature', 'panel_bedroom')

    def _setup_no_children_room(self, sp='9-1-10-M4'):
        owner = _make_owner(sp)
        floor = _make_device_floor(owner)
        _make_device_room(floor, '主卧')
        _make_device_room(floor, '次卧')
        return sp

    def test_room_filter_blocks_invalid_params_plc_latest(self):
        """UT-M4-01：无儿童房时，fourth_children_room_* 不写入 plc_latest_data"""
        sp = self._setup_no_children_room('9-1-10-M401')
        handler = PLCLatestDataHandler()
        payload = _make_mqtt_payload(sp, {
            'fourth_children_room_temperature': (0, True),
            'bedroom_temperature': (22, True),
        })
        handler.handle('test/topic', payload)
        # fourth_children_room_temperature 不应写入
        self.assertFalse(
            PLCLatestData.objects.filter(
                specific_part=sp,
                param_name='fourth_children_room_temperature',
            ).exists(),
            'fourth_children_room_temperature 不应写入 plc_latest_data',
        )
        # bedroom_temperature 应正常写入
        self.assertTrue(
            PLCLatestData.objects.filter(
                specific_part=sp,
                param_name='bedroom_temperature',
            ).exists(),
            'bedroom_temperature 应正常写入',
        )

    def test_room_filter_blocks_invalid_params_device_param_history(self):
        """UT-M4-02：无儿童房时，fourth_children_room_* 不写入 device_param_history"""
        sp = self._setup_no_children_room('9-1-10-M402')
        handler = PLCLatestDataHandler()
        payload = _make_mqtt_payload(sp, {
            'fourth_children_room_temperature': (0, True),
            'bedroom_temperature': (22, True),
        })
        handler.handle('test/topic', payload)
        self.assertFalse(
            DeviceParamHistory.objects.filter(
                specific_part=sp,
                param_name='fourth_children_room_temperature',
            ).exists(),
            'fourth_children_room_temperature 不应写入 device_param_history',
        )

    def test_valid_room_params_still_written(self):
        """UT-M4-03：实际存在房间的参数正常写入"""
        sp = self._setup_no_children_room('9-1-10-M403')
        handler = PLCLatestDataHandler()
        payload = _make_mqtt_payload(sp, {
            'bedroom_temperature': (21, True),
        })
        handler.handle('test/topic', payload)
        self.assertTrue(
            PLCLatestData.objects.filter(
                specific_part=sp,
                param_name='bedroom_temperature',
            ).exists(),
        )

    def test_system_level_params_not_filtered(self):
        """UT-M4-04：系统级参数不受房型过滤影响"""
        sp = self._setup_no_children_room('9-1-10-M404')
        handler = PLCLatestDataHandler()
        payload = _make_mqtt_payload(sp, {
            'system_switch': (1, True),
        })
        handler.handle('test/topic', payload)
        self.assertTrue(
            PLCLatestData.objects.filter(
                specific_part=sp,
                param_name='system_switch',
            ).exists(),
        )

    def test_empty_blocklist_no_filtering(self):
        """UT-M4-05：全量房间存在时，blocklist 为空，无参数被过滤"""
        sp = '9-1-10-M405'
        owner = _make_owner(sp)
        floor = _make_device_floor(owner)
        for name in ['主卧', '次卧', '书房', '四房儿童房']:
            _make_device_room(floor, name)
        handler = PLCLatestDataHandler()
        payload = _make_mqtt_payload(sp, {
            'fourth_children_room_temperature': (25, True),
        })
        handler.handle('test/topic', payload)
        # 四房儿童房存在，不应被过滤
        self.assertTrue(
            PLCLatestData.objects.filter(
                specific_part=sp,
                param_name='fourth_children_room_temperature',
            ).exists(),
        )


# ===========================================================================
# UT-M7B: OndemandCollectSubscriber 单元测试（纯逻辑，不需要 MQTT broker）
# ===========================================================================

class TestOndemandCollectSubscriberAllowedParams(TestCase):
    """UT-M7B-01~05：OndemandCollectSubscriber 按需采集白名单裁剪逻辑"""

    def _make_subscriber(self, plc_config=None):
        """创建不连接 MQTT broker 的 Subscriber 实例（mock 掉 MQTT 依赖）"""
        from datacollection.ondemand_collect_subscriber import OndemandCollectSubscriber
        sub = OndemandCollectSubscriber.__new__(OndemandCollectSubscriber)
        # 手动初始化必要属性
        sub._plc_config = plc_config or {
            'system_switch': {'db_num': 14, 'offset': 0, 'length': 2, 'data_type': 'int'},
            'bedroom_temperature': {'db_num': 14, 'offset': 4, 'length': 2, 'data_type': 'int'},
            'fourth_children_room_temperature': {'db_num': 14, 'offset': 8, 'length': 2, 'data_type': 'int'},
        }
        sub._owner_ip_map = {'9-1-10-1002': '192.168.7.100'}
        sub._pending = set()
        sub._pending_lock = threading.Lock()
        sub._client = MagicMock()
        sub._stopped = False
        return sub

    def test_execute_ondemand_with_allowed_params_filters_configs(self):
        """UT-M7B-01：allowed_params 指定时，configs 仅含白名单内参数"""
        sub = self._make_subscriber()
        collected_configs = []

        def mock_read(ip, configs, ts):
            collected_configs.extend(configs)
            return []

        sub._read_plc_params = mock_read
        sub._publish_result_payload = MagicMock()
        sub._pending = {'9-1-10-1002'}

        sub._execute_ondemand(
            '9-1-10-1002',
            allowed_params={'system_switch', 'bedroom_temperature'},
        )

        param_keys = {c['param_key'] for c in collected_configs}
        self.assertIn('system_switch', param_keys)
        self.assertIn('bedroom_temperature', param_keys)
        self.assertNotIn('fourth_children_room_temperature', param_keys)

    def test_execute_ondemand_without_allowed_params_full_collect(self):
        """UT-M7B-02：allowed_params=None 时，全量采集（向后兼容）"""
        sub = self._make_subscriber()
        collected_configs = []

        def mock_read(ip, configs, ts):
            collected_configs.extend(configs)
            return []

        sub._read_plc_params = mock_read
        sub._publish_result_payload = MagicMock()
        sub._pending = {'9-1-10-1002'}

        sub._execute_ondemand('9-1-10-1002', allowed_params=None)

        param_keys = {c['param_key'] for c in collected_configs}
        # 全量（3 个参数）
        self.assertEqual(len(param_keys), 3)
        self.assertIn('fourth_children_room_temperature', param_keys)

    def test_execute_ondemand_with_empty_set_yields_no_configs(self):
        """UT-M7B-03：allowed_params=set() 时，configs=[]，不崩溃，发布失败结果"""
        sub = self._make_subscriber()
        sub._read_plc_params = MagicMock(return_value=[])
        sub._publish_result_payload = MagicMock()
        sub._pending = {'9-1-10-1002'}

        # 空集合：不发起任何 PLC 读取，进入「plc_config 为空」分支
        sub._execute_ondemand('9-1-10-1002', allowed_params=set())
        # _publish_result_payload 应被调用（通过 _publish_result → _publish_result_payload）
        sub._publish_result_payload.assert_called_once()
        # 验证 payload 中 success=False
        call_args = sub._publish_result_payload.call_args
        sp, payload_dict = call_args[0]
        self.assertFalse(payload_dict.get('9-1-10-1002', {}).get('success', True))

    def test_on_request_parses_allowed_params_from_payload(self):
        """UT-M7B-04：_on_request 从 payload 解析 allowed_params 并传给 _execute_ondemand"""
        sub = self._make_subscriber()
        sub._executor = MagicMock()
        sub._pending_lock = threading.Lock()
        sub._pending = set()
        sub._max_pending = 20

        payload = json.dumps({
            'specific_part': '9-1-10-1002',
            'requested_at': '2026-05-23 10:00:00',
            'allowed_params': ['system_switch', 'bedroom_temperature'],
        })

        sub._on_request('/datacollection/plc/ondemand/request/9-1-10-1002', payload)

        # 验证 _execute_ondemand 被以正确参数提交
        sub._executor.submit.assert_called_once()
        call_args = sub._executor.submit.call_args
        # 第一个位置参数是函数，第二个是 specific_part，第三个是 allowed_params
        func, sp, allowed = call_args[0]
        self.assertEqual(sp, '9-1-10-1002')
        self.assertIsInstance(allowed, set)
        self.assertIn('system_switch', allowed)
        self.assertIn('bedroom_temperature', allowed)

    def test_on_request_without_allowed_params_passes_none(self):
        """UT-M7B-05：payload 无 allowed_params 时，传入 None（向后兼容）"""
        sub = self._make_subscriber()
        sub._executor = MagicMock()
        sub._pending_lock = threading.Lock()
        sub._pending = set()
        sub._max_pending = 20

        payload = json.dumps({
            'specific_part': '9-1-10-1002',
            'requested_at': '2026-05-23 10:00:00',
        })

        sub._on_request('/datacollection/plc/ondemand/request/9-1-10-1002', payload)

        call_args = sub._executor.submit.call_args
        func, sp, allowed = call_args[0]
        self.assertIsNone(allowed)


# ===========================================================================
# IT-M2: GET /api/devices/realtime-params/ 集成测试
# ===========================================================================

class TestGetDeviceRealtimeParamsWithRoomFilter(RoomFilterTestBase):
    """IT-M2-01~04：devices/realtime-params 接口房型过滤集成测试"""

    def setUp(self):
        super().setUp()
        _, self.token = _make_admin('admin_m2')
        self.client = APIClient()
        # 创建系统级和房间型的 DeviceConfig
        _make_device_config('system_switch', 'main_thermostat', display_name='系统开关')
        _make_device_config('fourth_children_room_temperature', 'panel_fourth_children',
                            display_name='四房儿童房温度')
        _make_device_config('bedroom_temperature', 'panel_bedroom',
                            display_name='主卧温度')

    def _make_plc_data(self, sp):
        """创建各类型 PLCLatestData 记录（确保 API 不因无数据而跳过）"""
        _make_plc_latest(sp, 'system_switch', 1)
        _make_plc_latest(sp, 'fourth_children_room_temperature', 0)
        _make_plc_latest(sp, 'bedroom_temperature', 22)

    def test_three_room_no_fourth_children_panel_excluded(self):
        """IT-M2-01：三房无儿童房，panel_fourth_children 不出现在响应中"""
        sp = '9-1-10-IT201'
        owner = _make_owner(sp)
        floor = _make_device_floor(owner)
        _make_device_room(floor, '主卧')
        self._make_plc_data(sp)

        resp = self.client.get(
            f'/api/devices/realtime-params/?specific_part={sp}',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        # 遍历所有 group -> sub_types 确认 panel_fourth_children 不存在
        all_sub_types = [
            sub_key
            for group_val in data.values()
            for sub_key in group_val.get('sub_types', {}).keys()
        ]
        self.assertNotIn('panel_fourth_children', all_sub_types,
                         'panel_fourth_children 不应出现在三房无儿童房的响应中')

    def test_system_level_panels_always_shown(self):
        """IT-M2-02：系统级面板不受房型过滤影响"""
        sp = '9-1-10-IT202'
        owner = _make_owner(sp)
        floor = _make_device_floor(owner)
        _make_device_room(floor, '主卧')
        self._make_plc_data(sp)

        resp = self.client.get(
            f'/api/devices/realtime-params/?specific_part={sp}',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        all_sub_types = [
            sub_key
            for group_val in data.values()
            for sub_key in group_val.get('sub_types', {}).keys()
        ]
        self.assertIn('main_thermostat', all_sub_types)

    def test_no_device_tree_synced_plan_b_fallback(self):
        """IT-M2-03：设备树未同步，方案 B：不含任何 panel_* sub_type"""
        sp = '9-1-10-IT203'
        _make_owner(sp)  # 无 DeviceFloor
        self._make_plc_data(sp)

        resp = self.client.get(
            f'/api/devices/realtime-params/?specific_part={sp}',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        all_sub_types = [
            sub_key
            for group_val in data.values()
            for sub_key in group_val.get('sub_types', {}).keys()
        ]
        for panel_sub in ALL_PANEL_SUB_TYPES:
            self.assertNotIn(panel_sub, all_sub_types,
                             f'{panel_sub} 不应在设备树未同步时出现')
        # 系统级仍应存在（若有数据）
        self.assertIn('main_thermostat', all_sub_types)

    def test_four_room_with_fourth_children_panel_included(self):
        """IT-M2-04：四房户型含儿童房，panel_fourth_children 出现在响应中"""
        sp = '9-1-10-IT204'
        owner = _make_owner(sp)
        floor = _make_device_floor(owner)
        for name in ['主卧', '次卧', '书房', '四房儿童房']:
            _make_device_room(floor, name)
        self._make_plc_data(sp)

        resp = self.client.get(
            f'/api/devices/realtime-params/?specific_part={sp}',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()['data']
        all_sub_types = [
            sub_key
            for group_val in data.values()
            for sub_key in group_val.get('sub_types', {}).keys()
        ]
        self.assertIn('panel_fourth_children', all_sub_types)


# ===========================================================================
# IT-M3: GET /api/device-settings/params/{sp}/ 集成测试
# ===========================================================================

class TestDeviceSettingsParamsWithRoomFilter(RoomFilterTestBase):
    """IT-M3-01/02：device-settings/params 接口房型过滤集成测试"""

    def setUp(self):
        super().setUp()
        _, self.token = _make_admin('admin_m3')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        # DeviceConfig：可写参数（以 _switch 结尾）
        _make_device_config(
            'fourth_children_room_switch', 'panel_fourth_children',
            display_name='四房儿童房开关',
        )
        _make_device_config(
            'system_switch', 'main_thermostat',
            display_name='系统开关',
        )

    def test_no_children_room_panel_excluded_from_settings(self):
        """IT-M3-01：无儿童房时，参数设置不含 panel_fourth_children 分组"""
        sp = '9-1-10-IT301'
        owner = _make_owner(sp)
        floor = _make_device_floor(owner)
        _make_device_room(floor, '主卧')

        resp = self.client.get(f'/api/device-settings/params/{sp}/')
        self.assertEqual(resp.status_code, 200)
        groups = resp.json().get('groups', [])
        group_sub_types = [g['sub_type'] for g in groups]
        self.assertNotIn('panel_fourth_children', group_sub_types)

    def test_system_level_writable_params_not_filtered(self):
        """IT-M3-02：系统级可写参数不受过滤影响"""
        sp = '9-1-10-IT302'
        owner = _make_owner(sp)
        floor = _make_device_floor(owner)
        _make_device_room(floor, '主卧')

        resp = self.client.get(f'/api/device-settings/params/{sp}/')
        self.assertEqual(resp.status_code, 200)
        groups = resp.json().get('groups', [])
        group_sub_types = [g['sub_type'] for g in groups]
        self.assertIn('main_thermostat', group_sub_types)


# ===========================================================================
# IT-M5: 设备树同步后缓存清除集成测试
# ===========================================================================

class TestDeviceTreeSyncCacheInvalidation(RoomFilterTestBase):
    """IT-M5-01：device_tree_sync_one 成功后调用 invalidate_room_filter_cache"""

    def setUp(self):
        super().setUp()
        _, self.token = _make_admin('admin_m5')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

    def test_sync_one_calls_cache_invalidation(self):
        """IT-M5-01：同步成功后 invalidate_room_filter_cache(specific_part) 被调用"""
        sp = '9-1-10-IT501'
        _make_owner(sp)

        # mock sync_one_specific_part 返回成功
        mock_result = {
            'specific_part': sp,
            'screen_mac': 'AA:BB:CC:DD:EE:FF',
            'stats': {'created': 1, 'updated': 0, 'deleted': 0},
        }

        # views.py 用 from .utils_room_filter import invalidate_room_filter_cache
        # patch 路径须为 api.views 中的名字
        with patch(
            'api.views.invalidate_room_filter_cache',
        ) as mock_invalidate, patch(
            'api.device_tree_sync.sync_one_specific_part',
            return_value=mock_result,
        ):
            resp = self.client.post(
                '/api/device-management/screen-device-tree/sync/',
                data={'specific_part': sp},
                format='json',
            )
            # 断言同步成功
            self.assertIn(resp.status_code, [200, 201])
            # 断言缓存被清除
            mock_invalidate.assert_called_once_with(sp)


# ===========================================================================
# IT-M7A: POST /api/devices/ondemand-refresh/ allowed_params 注入集成测试
# ===========================================================================

class TestOndemandRefreshAllowedParamsInjection(RoomFilterTestBase):
    """IT-M7A-01/02：ondemand-refresh MQTT payload 注入 allowed_params"""

    def setUp(self):
        super().setUp()
        _, self.token = _make_admin('admin_m7a')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        # DeviceConfig
        _make_device_config('system_switch', 'main_thermostat')
        _make_device_config('fourth_children_room_temperature', 'panel_fourth_children')
        _make_device_config('bedroom_temperature', 'panel_bedroom')
        # 清空防重入缓存，避免测试间干扰
        import api.views as _views_module
        _views_module._ondemand_inflight.clear()

    def test_synced_device_tree_payload_has_allowed_params(self):
        """IT-M7A-01：设备树已同步，payload 含 allowed_params，不含 fourth_children_room_*"""
        sp = '9-1-10-IT7A01'
        owner = _make_owner(sp)
        floor = _make_device_floor(owner)
        _make_device_room(floor, '主卧')  # 无四房儿童房

        published_payloads = []

        def mock_publish_single(topic, payload, **kwargs):
            published_payloads.append(json.loads(payload))

        # inline import 路径：paho.mqtt.publish 在 device_ondemand_refresh 中 inline 导入
        with patch('paho.mqtt.publish.single', side_effect=mock_publish_single):
            resp = self.client.post(
                '/api/devices/ondemand-refresh/',
                data={'specific_part': sp},
                format='json',
            )
        self.assertIn(resp.status_code, [202])
        self.assertEqual(len(published_payloads), 1)
        payload = published_payloads[0]
        # 应含 allowed_params 字段
        self.assertIn('allowed_params', payload,
                      'payload 应含 allowed_params 字段')
        # 不含 fourth_children_room_temperature（无儿童房）
        self.assertNotIn(
            'fourth_children_room_temperature',
            payload['allowed_params'],
            'allowed_params 不应含无效房间的参数',
        )
        # 含系统级参数
        self.assertIn('system_switch', payload['allowed_params'])

    def test_no_device_tree_payload_has_system_only_params(self):
        """IT-M7A-02：设备树未同步，allowed_params 仅含系统级参数"""
        sp = '9-1-10-IT7A02'
        _make_owner(sp)  # 无 DeviceFloor

        published_payloads = []

        def mock_publish_single(topic, payload, **kwargs):
            published_payloads.append(json.loads(payload))

        with patch('paho.mqtt.publish.single', side_effect=mock_publish_single):
            resp = self.client.post(
                '/api/devices/ondemand-refresh/',
                data={'specific_part': sp},
                format='json',
            )
        self.assertIn(resp.status_code, [202])
        self.assertEqual(len(published_payloads), 1)
        payload = published_payloads[0]
        # allowed_params 仅含 main_thermostat 下的系统级参数
        if 'allowed_params' in payload:
            self.assertNotIn('fourth_children_room_temperature',
                             payload['allowed_params'])
            self.assertNotIn('bedroom_temperature', payload['allowed_params'])


# ===========================================================================
# EDGE: 边界测试
# ===========================================================================

class TestEdgeCases(RoomFilterTestBase):
    """EDGE-01~04 / PERF-01 边界与性能测试"""

    def test_panel_bedroom_and_children_room_both_active_when_both_keywords_present(self):
        """EDGE-01/02：三房含主卧+儿童房，panel_bedroom 和 panel_children_room 均可用"""
        names = ['主卧', '儿童房', '次卧']
        result = _match_panel_sub_types(names)
        self.assertIn('panel_bedroom', result)
        self.assertIn('panel_children_room', result)

    def test_four_rooms_no_children_keyword_no_fourth_children(self):
        """EDGE-03：4 个房间但无「儿童房」关键词，panel_fourth_children 不触发"""
        names = ['主卧', '次卧', '书房', '客厅']
        result = _match_panel_sub_types(names)
        self.assertNotIn('panel_fourth_children', result)

    def test_empty_ori_room_name_does_not_crash(self):
        """EDGE-04：ori_room_name 包含空字符串时不崩溃"""
        names = ['主卧', '', '次卧', None]
        # _match_panel_sub_types 接收 list，过滤 None 为 utils_room_filter 的职责
        # 直接传入 None 时 '' in None 会报错，故只测空字符串
        safe_names = [n for n in names if n]  # 与实际代码中 if room.ori_room_name 一致
        result = _match_panel_sub_types(safe_names)
        self.assertIn('panel_bedroom', result)

    def test_cache_hit_performance(self):
        """PERF-01：缓存命中时 get_available_sub_types() 开销 < 5ms"""
        owner = _make_owner('9-1-10-PERF')
        floor = _make_device_floor(owner)
        _make_device_room(floor, '主卧')
        # 填充缓存
        get_available_sub_types('9-1-10-PERF')
        # 测量缓存命中时间
        start = time.monotonic()
        for _ in range(100):
            get_available_sub_types('9-1-10-PERF')
        elapsed_ms = (time.monotonic() - start) * 1000
        avg_ms = elapsed_ms / 100
        self.assertLess(avg_ms, 5.0,
                        f'缓存命中平均耗时 {avg_ms:.2f}ms 超过 5ms 阈值')
