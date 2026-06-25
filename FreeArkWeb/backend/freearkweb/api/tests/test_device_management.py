"""
设备管理功能测试套件 — GROUP_D (PHASE_07 单元测试 + PHASE_08 集成测试 + PHASE_09 E2E验收)

覆盖需求：US-001~007, NFR-001~005
REQ-FUNC-001~005

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_device_management --settings=freearkweb.test_settings --verbosity=2

测试数据库：SQLite in-memory（test_settings.py 强制配置）
"""

import json
import os
import socket
import sys
import threading
import unittest
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, patch, call

from django.test import TestCase, tag
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import (
    CustomUser,
    OwnerInfo,
    PLCConnectionStatus,
    PLCLatestData,
    ScreenConnectivityStatus,
)
from api.mqtt_handlers import ScreenConnectivityHandler

# ---------------------------------------------------------------------------
# Python 路径: 确保 datacollection 包可被导入
# 文件路径: FreeArkWeb/backend/freearkweb/api/tests/test_device_management.py
# 仓库根目录（含 datacollection/）: 从 tests/ 往上 5 层
# tests(1) -> api(2) -> freearkweb(3) -> backend(4) -> FreeArkWeb(5) -> FreeArk/
# ---------------------------------------------------------------------------
_FREEARK_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '..')
)
if _FREEARK_ROOT not in sys.path:
    sys.path.insert(0, _FREEARK_ROOT)


# ===========================================================================
# 测试辅助函数
# ===========================================================================

def _make_user(username="testuser", role="operator"):
    user = CustomUser.objects.create_user(username=username, password="pass1234", role=role)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _make_owner(specific_part="3-1-7-702", building="3", unit="1", room_number="702",
                ip_address="192.168.1.100"):
    return OwnerInfo.objects.create(
        specific_part=specific_part,
        location_name=f"测试坐落-{specific_part}",
        building=building,
        unit=unit,
        floor="7楼",
        room_number=room_number,
        bind_status="已绑定",
        ip_address=ip_address,
        unique_id=specific_part.replace("-", ""),
        plc_ip_address="192.168.2.100",
    )


def _make_screen_status(specific_part, status="online", checked_at=None):
    """创建 ScreenConnectivityStatus 记录。

    status="online"  → last_seen_at = now()（在阈值内，API 判定为 online）
    status="offline" → last_seen_at = 1 小时前（超过阈值，API 判定为 offline）
    """
    from django.utils import timezone as _tz
    from datetime import timedelta
    from api.views import ONLINE_THRESHOLD_MINUTES

    if status == "online":
        last_seen = checked_at if checked_at is not None else _tz.now()
    else:
        # offline：超出阈值，确保比 cutoff 还早
        last_seen = checked_at if checked_at is not None else (
            _tz.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES + 30)
        )
    return ScreenConnectivityStatus.objects.create(
        specific_part=specific_part,
        last_seen_at=last_seen,
    )


def _make_plc_latest(building, unit, room_number, param_name="system_switch", value=1):
    return PLCLatestData.objects.create(
        specific_part=f"{building}-1-{unit}-{room_number}",
        param_name=param_name,
        value=value,
        building=building,
        unit=unit,
        room_number=room_number,
        collected_at=datetime.now(),
    )


def _make_plc_connection_status(specific_part, connection_status="online", last_online_time=None):
    """创建 PLCConnectionStatus 记录。"""
    from django.utils import timezone as _tz
    parts = specific_part.split('-')
    building = parts[0] if len(parts) > 0 else ''
    unit = parts[1] if len(parts) > 1 else ''
    room_number = parts[3] if len(parts) > 3 else ''
    if last_online_time is None:
        last_online_time = _tz.now() if connection_status == 'online' else None
    return PLCConnectionStatus.objects.create(
        specific_part=specific_part,
        connection_status=connection_status,
        last_online_time=last_online_time,
        building=building,
        unit=unit,
        room_number=room_number,
    )


# ===========================================================================
# PHASE_07: 单元测试
# ===========================================================================

@tag('unit')
class TC_U_001_ScreenConnectivityStatusModel(TestCase):
    """TC-U-001: ScreenConnectivityStatus 模型基本 CRUD 与约束（已适配心跳方案）"""

    def test_create_status_record(self):
        """创建一条记录，字段存储正确"""
        now = timezone.now()
        obj = ScreenConnectivityStatus.objects.create(
            specific_part="3-1-7-702",
            last_seen_at=now,
        )
        self.assertIsNotNone(obj.id)
        self.assertEqual(obj.specific_part, "3-1-7-702")
        self.assertEqual(obj.last_seen_at, now)
        self.assertIsNotNone(obj.updated_at)

    def test_unique_specific_part_constraint(self):
        """specific_part 唯一约束：重复插入应抛出异常"""
        ScreenConnectivityStatus.objects.create(
            specific_part="3-1-7-702",
            last_seen_at=timezone.now(),
        )
        with self.assertRaises(Exception):
            ScreenConnectivityStatus.objects.create(
                specific_part="3-1-7-702",
                last_seen_at=timezone.now(),
            )

    def test_str_representation(self):
        """__str__ 包含 specific_part"""
        now = timezone.now()
        obj = ScreenConnectivityStatus.objects.create(
            specific_part="3-1-7-702",
            last_seen_at=now,
        )
        self.assertIn("3-1-7-702", str(obj))

    def test_upsert_via_update_or_create(self):
        """update_or_create 幂等：多次调用只产生一条记录，last_seen_at 被更新"""
        import time
        t1 = timezone.now()
        ScreenConnectivityStatus.objects.update_or_create(
            specific_part="3-1-7-702",
            defaults={"last_seen_at": t1},
        )
        time.sleep(0.05)
        t2 = timezone.now()
        ScreenConnectivityStatus.objects.update_or_create(
            specific_part="3-1-7-702",
            defaults={"last_seen_at": t2},
        )
        count = ScreenConnectivityStatus.objects.filter(specific_part="3-1-7-702").count()
        self.assertEqual(count, 1)
        latest = ScreenConnectivityStatus.objects.get(specific_part="3-1-7-702")
        self.assertGreaterEqual(latest.last_seen_at, t1)

    def test_model_has_last_seen_at_not_status(self):
        """模型字段：有 last_seen_at，没有 status 和 last_checked_at"""
        field_names = [f.name for f in ScreenConnectivityStatus._meta.get_fields()]
        self.assertIn('last_seen_at', field_names)
        self.assertNotIn('status', field_names)
        self.assertNotIn('last_checked_at', field_names)


@tag('unit')
class TC_U_002_ScreenConnectivityHandler(TestCase):
    """TC-U-002: ScreenConnectivityHandler 单元测试（已适配心跳方案）

    新行为：
    - online payload → upsert last_seen_at = now()
    - offline payload → no-op（离线由阈值判断）
    - 非法 payload → 丢弃
    """

    def setUp(self):
        self.handler = ScreenConnectivityHandler()

    # --- 正常路径 ---

    def test_handle_online_payload_writes_last_seen_at(self):
        """合法 online payload → upsert last_seen_at（视为刚刚心跳）"""
        before = timezone.now()
        payload = {
            "specific_part": "3-1-7-702",
            "status": "online",
            "checked_at": "2026-04-27T10:00:00",
        }
        self.handler.handle("/datacollection/screen/connectivity", payload)
        obj = ScreenConnectivityStatus.objects.get(specific_part="3-1-7-702")
        # last_seen_at 应为 now()，不是 checked_at（新行为）
        self.assertIsNotNone(obj.last_seen_at)
        self.assertGreaterEqual(obj.last_seen_at, before)

    def test_handle_offline_payload_noop(self):
        """offline payload → 不写入任何记录（离线由阈值判断）"""
        payload = {
            "specific_part": "3-1-7-801",
            "status": "offline",
            "checked_at": "2026-04-27T10:01:00",
        }
        self.handler.handle("/datacollection/screen/connectivity", payload)
        # offline 不写入
        self.assertEqual(ScreenConnectivityStatus.objects.count(), 0)

    def test_handle_online_updates_existing_record(self):
        """对已存在记录的 online payload 执行 upsert，只保留一条记录"""
        ScreenConnectivityStatus.objects.create(
            specific_part="3-1-7-702",
            last_seen_at=timezone.now(),
        )
        payload = {
            "specific_part": "3-1-7-702",
            "status": "online",
            "checked_at": "2026-04-27T10:02:00",
        }
        self.handler.handle("/datacollection/screen/connectivity", payload)
        self.assertEqual(ScreenConnectivityStatus.objects.count(), 1)

    # --- 异常/边界路径 ---

    def test_handle_non_dict_payload_is_ignored(self):
        """payload 非 dict 时，不写入任何记录"""
        self.handler.handle("/datacollection/screen/connectivity", "invalid_string")
        self.assertEqual(ScreenConnectivityStatus.objects.count(), 0)

    def test_handle_missing_specific_part_is_ignored(self):
        """specific_part 为空时，丢弃消息，不写入"""
        payload = {"specific_part": "", "status": "online", "checked_at": "2026-04-27T10:00:00"}
        self.handler.handle("/datacollection/screen/connectivity", payload)
        self.assertEqual(ScreenConnectivityStatus.objects.count(), 0)

    def test_handle_invalid_status_is_ignored(self):
        """status 非 online/offline 时，丢弃消息，不写入"""
        payload = {"specific_part": "3-1-7-702", "status": "unknown", "checked_at": "2026-04-27T10:00:00"}
        self.handler.handle("/datacollection/screen/connectivity", payload)
        self.assertEqual(ScreenConnectivityStatus.objects.count(), 0)


@tag('unit')
class TC_U_003_ScreenConnectivityChecker(TestCase):
    """TC-U-003: ScreenConnectivityChecker 探测逻辑单元测试"""

    def setUp(self):
        # 不实际发起网络连接，全部 mock
        from datacollection.screen_connectivity_checker import ScreenConnectivityChecker
        self.checker = ScreenConnectivityChecker(max_workers=5, timeout=1)

    def test_probe_single_returns_true_on_success(self):
        """probe_single: ping returncode=0（主机可达）返回 True"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("subprocess.run", return_value=mock_result):
            result = self.checker.probe_single("192.168.1.100")
        self.assertTrue(result)

    def test_probe_single_returns_false_on_nonzero_returncode(self):
        """probe_single: ping returncode!=0（主机不可达）返回 False"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            result = self.checker.probe_single("192.168.1.100")
        self.assertFalse(result)

    def test_probe_single_returns_false_on_timeout(self):
        """probe_single: socket.timeout（主机不可达）返回 False"""
        with patch("socket.create_connection", side_effect=socket.timeout()):
            result = self.checker.probe_single("192.168.1.100")
        self.assertFalse(result)

    def test_probe_single_returns_false_on_oserror(self):
        """probe_single: OSError（网络不可达）返回 False"""
        with patch("socket.create_connection", side_effect=OSError()):
            result = self.checker.probe_single("192.168.1.100")
        self.assertFalse(result)

    def test_check_all_skips_empty_ip(self):
        """check_all: ip_address 为空字符串的条目被跳过，不出现在结果中"""
        owner_list = [
            {"specific_part": "3-1-7-702", "ip_address": ""},
            {"specific_part": "3-1-7-703", "ip_address": "   "},
        ]
        results = self.checker.check_all(owner_list)
        self.assertEqual(results, [])

    def test_check_all_returns_empty_list_for_empty_input(self):
        """check_all: 输入为空列表时返回空列表"""
        results = self.checker.check_all([])
        self.assertEqual(results, [])

    def test_check_all_online_result(self):
        """check_all: 单个 IP 探测在线，结果含 status=online"""
        owner_list = [{"specific_part": "3-1-7-702", "ip_address": "192.168.1.100"}]
        with patch.object(self.checker, "probe_single", return_value=True):
            results = self.checker.check_all(owner_list)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["specific_part"], "3-1-7-702")
        self.assertEqual(results[0]["status"], "online")
        self.assertIn("checked_at", results[0])

    def test_check_all_offline_result(self):
        """check_all: 单个 IP 探测离线，结果含 status=offline"""
        owner_list = [{"specific_part": "3-1-7-702", "ip_address": "192.168.1.100"}]
        with patch.object(self.checker, "probe_single", return_value=False):
            results = self.checker.check_all(owner_list)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "offline")

    def test_check_all_multiple_ips(self):
        """check_all: 多个 IP 并发探测，结果数量与有效 IP 数相同"""
        owner_list = [
            {"specific_part": f"3-1-7-{700+i}", "ip_address": f"192.168.1.{100+i}"}
            for i in range(5)
        ]
        side_effects = [True, False, True, True, False]
        with patch.object(self.checker, "probe_single", side_effect=side_effects):
            results = self.checker.check_all(owner_list)
        self.assertEqual(len(results), 5)
        # 验证字段完整性
        for r in results:
            self.assertIn("specific_part", r)
            self.assertIn("status", r)
            self.assertIn("checked_at", r)
            self.assertIn(r["status"], ("online", "offline"))

    def test_check_all_exception_in_probe_treated_as_offline(self):
        """check_all: 探测异常时，该条结果 status=offline（不崩溃）"""
        owner_list = [{"specific_part": "3-1-7-702", "ip_address": "192.168.1.100"}]
        with patch.object(self.checker, "probe_single", side_effect=RuntimeError("mock error")):
            results = self.checker.check_all(owner_list)
        # check_all 捕获了异常，结果中该条记录 status=offline
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], "offline")


@tag('unit')
class TC_U_004_DeviceListViewFiltering(TestCase):
    """TC-U-004: device_management_device_list 视图过滤逻辑单元测试（不通过 HTTP）"""

    def setUp(self):
        from api.views import device_management_device_list
        self.view = device_management_device_list

        # 创建认证用户
        self.user, self.token = _make_user("dm_unit_user")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 创建测试数据：4 条 OwnerInfo
        _make_owner("3-1-7-701", building="3", unit="1", room_number="701", ip_address="192.168.1.1")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702", ip_address="192.168.1.2")
        _make_owner("3-2-7-301", building="3", unit="2", room_number="301", ip_address="192.168.1.3")
        _make_owner("4-1-5-501", building="4", unit="1", room_number="501", ip_address="192.168.1.4")

    def test_room_no_filter_building_only(self):
        """room_no=3 只过滤 building=3 的记录"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        for item in data["results"]:
            self.assertEqual(item["building"], "3")

    def test_room_no_filter_building_and_unit(self):
        """room_no=3-1 过滤 building=3, unit=1"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for item in data["results"]:
            self.assertEqual(item["building"], "3")
            self.assertEqual(item["unit"], "1")

    def test_room_no_filter_three_segments(self):
        """room_no=3-1-702 过滤到单条记录"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-702")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "702")

    def test_room_no_invalid_format_returns_400(self):
        """room_no 超过3段返回 400"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-7-702")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("error", resp.json())

    def test_room_no_empty_segment_returns_400(self):
        """room_no 含空段（如 3--702）返回 400"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3--702")
        self.assertEqual(resp.status_code, 400)

    def test_no_filter_returns_all(self):
        """无过滤参数返回所有记录"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 4)


# ===========================================================================
# PHASE_08: 集成测试
# ===========================================================================

@tag('integration')
class TC_I_001_DeviceListAPIAuth(TestCase):
    """TC-I-001: 设备列表 API 认证与权限集成测试"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = _make_user("dm_int_user")
        _make_owner("3-1-7-702")

    def test_unauthenticated_request_returns_401(self):
        """未认证请求返回 401（US-001: 需要登录）"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_user_gets_200(self):
        """认证用户请求返回 200（普通用户亦可访问）"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)

    def test_post_method_not_allowed(self):
        """POST 方法不允许，返回 405"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")
        resp = self.client.post("/api/device-management/device-list/", {})
        self.assertEqual(resp.status_code, 405)


@tag('integration')
class TC_I_002_DeviceListAPIResponseSchema(TestCase):
    """TC-I-002: 响应 schema 完整性测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_schema_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        owner = _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        _make_screen_status("3-1-7-702", status="online")
        PLCLatestData.objects.create(
            specific_part="3-1-7-702",
            param_name="system_switch",
            value=1,
            building="3",
            unit="1",
            room_number="702",
            collected_at=datetime.now(),
        )

    def test_response_top_level_keys(self):
        """响应顶层字段：count, page, page_size, results"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for key in ("count", "page", "page_size", "results"):
            self.assertIn(key, data, f"缺少顶层字段: {key}")

    def test_result_item_fields(self):
        """results 中每条记录含所有必需字段，且不含已移除的 screen_last_checked_at"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        self.assertGreater(len(data["results"]), 0)
        item = data["results"][0]
        required_fields = [
            "specific_part", "building", "unit", "room_number",
            "screen_status", "screen_last_seen_at",
            "system_switch_value", "system_switch_display",
            "plc_status", "plc_last_online_time",
        ]
        for f in required_fields:
            self.assertIn(f, item, f"result 条目缺少字段: {f}")
        # screen_last_checked_at 已移除，不应出现在响应中
        self.assertNotIn("screen_last_checked_at", item)

    def test_screen_status_is_online(self):
        """有近期 last_seen_at 的记录，screen_status 返回 online"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        item = next(r for r in data["results"] if r["specific_part"] == "3-1-7-702")
        self.assertEqual(item["screen_status"], "online")
        self.assertIsNotNone(item["screen_last_seen_at"])

    def test_system_switch_display_on(self):
        """system_switch_value=1 时，system_switch_display 返回 '开'"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        item = next(r for r in data["results"] if r["specific_part"] == "3-1-7-702")
        self.assertEqual(item["system_switch_display"], "开")
        self.assertEqual(item["system_switch_value"], 1)


@tag('integration')
class TC_I_003_DeviceListAPIScreenStatusValues(TestCase):
    """TC-I-003: 大屏状态三种值（online/offline/unknown）集成测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_screen_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        _make_owner("3-1-7-703", building="3", unit="1", room_number="703")

        _make_screen_status("3-1-7-701", status="online")
        _make_screen_status("3-1-7-702", status="offline")
        # 703 无 ScreenConnectivityStatus 记录 → unknown

    def test_screen_status_online(self):
        """有 online 记录的户，screen_status=online"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-701")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["screen_status"], "online")

    def test_screen_status_offline(self):
        """有 offline 记录的户，screen_status=offline"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-702")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["screen_status"], "offline")

    def test_screen_status_unknown_when_no_record(self):
        """无 ScreenConnectivityStatus 记录的户，screen_status=unknown"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-703")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["screen_status"], "unknown")
        self.assertIsNone(data["results"][0]["screen_last_seen_at"])

    def test_filter_by_screen_status_online(self):
        """screen_status=online 过滤：只返回在线记录"""
        resp = self.client.get("/api/device-management/device-list/?screen_status=online")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["screen_status"], "online")

    def test_filter_by_screen_status_offline(self):
        """screen_status=offline 过滤：只返回离线记录"""
        resp = self.client.get("/api/device-management/device-list/?screen_status=offline")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["screen_status"], "offline")

    def test_filter_by_screen_status_unknown(self):
        """screen_status=unknown 过滤：只返回无记录（unknown）的户"""
        resp = self.client.get("/api/device-management/device-list/?screen_status=unknown")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["screen_status"], "unknown")


@tag('integration')
class TC_I_004_DeviceListAPISystemSwitch(TestCase):
    """TC-I-004: 系统开关过滤集成测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_switch_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        _make_owner("3-1-7-703", building="3", unit="1", room_number="703")

        # 701: system_switch=1（开）
        PLCLatestData.objects.create(
            specific_part="3-1-7-701", param_name="system_switch", value=1,
            building="3", unit="1", room_number="701", collected_at=datetime.now(),
        )
        # 702: system_switch=0（关）
        PLCLatestData.objects.create(
            specific_part="3-1-7-702", param_name="system_switch", value=0,
            building="3", unit="1", room_number="702", collected_at=datetime.now(),
        )
        # 703: 无记录（未知）

    def test_system_switch_on_display(self):
        """value=1 → system_switch_display='开'"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-701")
        data = resp.json()
        self.assertEqual(data["results"][0]["system_switch_display"], "开")

    def test_system_switch_off_display(self):
        """value=0 → system_switch_display='关'"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-702")
        data = resp.json()
        self.assertEqual(data["results"][0]["system_switch_display"], "关")

    def test_system_switch_unknown_display(self):
        """无记录 → system_switch_display='未知'"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-703")
        data = resp.json()
        self.assertEqual(data["results"][0]["system_switch_display"], "未知")
        self.assertIsNone(data["results"][0]["system_switch_value"])

    def test_filter_system_switch_on(self):
        """system_switch=on 过滤：只返回 value!=0 且非空的记录"""
        resp = self.client.get("/api/device-management/device-list/?system_switch=on")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "701")

    def test_filter_system_switch_off(self):
        """system_switch=off 过滤：返回 value=0 或无记录的户"""
        resp = self.client.get("/api/device-management/device-list/?system_switch=off")
        data = resp.json()
        # 702 (value=0) + 703 (无记录，IS NULL 也视为 off)
        self.assertEqual(data["count"], 2)
        room_numbers = {r["room_number"] for r in data["results"]}
        self.assertIn("702", room_numbers)
        self.assertIn("703", room_numbers)


@tag('integration')
class TC_I_005_DeviceListAPIPagination(TestCase):
    """TC-I-005: 分页功能集成测试（NFR-003: 每页默认20，最大2000）

    BUG-FIX: 原 page_size 上限为50，导致批量同步只能取到第一页50条。
    修复后上限为2000，分页 UI 行为不变（仍使用 10/20/50）。
    """

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_page_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 创建 25 条记录
        for i in range(1, 26):
            OwnerInfo.objects.create(
                specific_part=f"3-1-7-{700 + i}",
                location_name=f"测试-{i}",
                building="3",
                unit="1",
                floor="7楼",
                room_number=str(700 + i),
                bind_status="已绑定",
                ip_address=f"192.168.1.{i}",
                unique_id=f"uid{i:05d}",
                plc_ip_address=f"192.168.2.{i}",
            )

    def test_default_page_size_is_20(self):
        """无分页参数时，page=1，page_size=20，results 最多20条"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 20)
        self.assertEqual(len(data["results"]), 20)
        self.assertEqual(data["count"], 25)

    def test_page_2_returns_remaining(self):
        """page=2&page_size=20：返回剩余5条"""
        resp = self.client.get("/api/device-management/device-list/?page=2&page_size=20")
        data = resp.json()
        self.assertEqual(data["page"], 2)
        self.assertEqual(len(data["results"]), 5)

    def test_page_size_10(self):
        """page_size=10：每页10条"""
        resp = self.client.get("/api/device-management/device-list/?page_size=10")
        data = resp.json()
        self.assertEqual(data["page_size"], 10)
        self.assertEqual(len(data["results"]), 10)

    def test_page_size_large_value_capped_at_50(self):
        """page_size=9999：被 cap 到 50（device-list 分页上限为 50，见 views.py）。

        当前 25 条数据 < 50，故一页可取完。
        """
        resp = self.client.get("/api/device-management/device-list/?page_size=9999")
        data = resp.json()
        self.assertEqual(data["page_size"], 50)
        # 25 条数据 < 50，一页取完
        self.assertEqual(len(data["results"]), 25)
        self.assertEqual(data["count"], 25)

    def test_page_size_over_cap_capped_at_50(self):
        """page_size=2000：超过上限被 cap 到 50（25 条 < 50，一页取完）。"""
        resp = self.client.get("/api/device-management/device-list/?page=1&page_size=2000")
        data = resp.json()
        self.assertEqual(data["page_size"], 50)
        self.assertEqual(data["count"], 25)
        self.assertEqual(len(data["results"]), 25)

    def test_invalid_page_defaults_to_1(self):
        """page=abc 非法：回退到 page=1"""
        resp = self.client.get("/api/device-management/device-list/?page=abc")
        data = resp.json()
        self.assertEqual(data["page"], 1)

    def test_invalid_page_size_defaults_to_20(self):
        """page_size=xyz 非法：回退到 page_size=20"""
        resp = self.client.get("/api/device-management/device-list/?page_size=xyz")
        data = resp.json()
        self.assertEqual(data["page_size"], 20)

    def test_results_sorted_by_building_unit_room(self):
        """结果按 building/unit/room_number 升序排列"""
        resp = self.client.get("/api/device-management/device-list/?page_size=25")
        data = resp.json()
        room_numbers = [r["room_number"] for r in data["results"]]
        self.assertEqual(room_numbers, sorted(room_numbers))

    def test_count_field_reflects_total_not_page_results(self):
        """resp.count 反映全量总数，而非当页 results 的长度

        BUG-FIX 验证：前端应使用 resp.count 获知总户数，
        而非 resp.results.length（后者仅为当页条数）。
        """
        resp = self.client.get("/api/device-management/device-list/?page=1&page_size=10")
        data = resp.json()
        # 当页 results 只有10条，但 count 应反映全部25条
        self.assertEqual(len(data["results"]), 10)
        self.assertEqual(data["count"], 25,
            "count 字段应为全量总数25，不应与 results.length(10) 相同")


@tag('integration')
class TC_I_006_MQTTHandlerIntegration(TestCase):
    """TC-I-006: ScreenConnectivityHandler 与数据库集成测试（已适配心跳方案）"""

    def setUp(self):
        self.handler = ScreenConnectivityHandler()

    def test_multiple_online_messages_upsert_single_record(self):
        """同一 specific_part 多条 online 消息只保留最新一条 DB 记录"""
        for i in range(3):
            payload = {
                "specific_part": "3-1-7-702",
                "status": "online",
                "checked_at": f"2026-04-27T10:0{i}:00",
            }
            self.handler.handle("/datacollection/screen/connectivity", payload)

        count = ScreenConnectivityStatus.objects.filter(specific_part="3-1-7-702").count()
        self.assertEqual(count, 1)

    def test_different_specific_parts_create_separate_records(self):
        """不同 specific_part 各自独立建行"""
        for sp in ["3-1-7-701", "3-1-7-702", "3-1-7-703"]:
            payload = {"specific_part": sp, "status": "online", "checked_at": "2026-04-27T10:00:00"}
            self.handler.handle("/datacollection/screen/connectivity", payload)

        self.assertEqual(ScreenConnectivityStatus.objects.count(), 3)

    def test_api_reflects_online_status(self):
        """Handler 写入 online → API 响应返回 online（端到端链路验证）"""
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        payload = {"specific_part": "3-1-7-702", "status": "online", "checked_at": "2026-04-27T10:00:00"}
        self.handler.handle("/datacollection/screen/connectivity", payload)

        client = APIClient()
        _, token = _make_user("dm_e2e_user")
        client.credentials(HTTP_AUTHORIZATION=f"Token {token}")
        resp = client.get("/api/device-management/device-list/?room_no=3-1-702")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["screen_status"], "online")


# ===========================================================================
# PHASE_09: E2E 验收测试（US-* 覆盖）
# ===========================================================================

@tag('e2e')
class TC_E2E_US001_NavigationStructure(TestCase):
    """TC-E2E-US001: US-001 — 设备管理导航入口存在（路由可访问）"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_us001")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")
        _make_owner("3-1-7-702")

    def test_device_list_url_is_accessible(self):
        """GET /api/device-management/device-list/ 路由已注册且可访问（200）"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)

    def test_url_not_found_for_wrong_path(self):
        """错误路径返回 404，确认路由无歧义"""
        resp = self.client.get("/api/device-management/")
        self.assertIn(resp.status_code, (404, 405))


@tag('e2e')
class TC_E2E_US002_DisplayAllDevices(TestCase):
    """TC-E2E-US002: US-002 — 设备列表展示所有专有部分"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_us002")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 创建具代表性的多条记录
        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        _make_owner("4-2-5-501", building="4", unit="2", room_number="501")

    def test_all_owners_returned(self):
        """无过滤时，返回所有 OwnerInfo 记录"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        self.assertEqual(data["count"], 3)

    def test_results_contain_specific_part(self):
        """每条结果包含 specific_part"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        sps = {r["specific_part"] for r in data["results"]}
        self.assertIn("3-1-7-701", sps)
        self.assertIn("3-1-7-702", sps)
        self.assertIn("4-2-5-501", sps)


@tag('e2e')
class TC_E2E_US003_RoomNumberFilter(TestCase):
    """TC-E2E-US003: US-003 — 房号过滤（三段格式）"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_us003")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        for r in ["701", "702", "703"]:
            _make_owner(f"3-1-7-{r}", building="3", unit="1", room_number=r)
        _make_owner("4-1-5-501", building="4", unit="1", room_number="501")

    def test_filter_by_building_segment(self):
        """room_no=3 仅返回 building=3 的记录"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3")
        data = resp.json()
        self.assertEqual(data["count"], 3)

    def test_filter_by_building_unit(self):
        """room_no=3-1 仅返回 building=3, unit=1 的记录"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1")
        data = resp.json()
        self.assertEqual(data["count"], 3)

    def test_filter_exact_room(self):
        """room_no=3-1-702 精确到单条"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-702")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "702")


@tag('e2e')
class TC_E2E_US004_ScreenStatusFilter(TestCase):
    """TC-E2E-US004: US-004 — 大屏状态过滤"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_us004")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        _make_owner("3-1-7-703", building="3", unit="1", room_number="703")

        _make_screen_status("3-1-7-701", "online")
        _make_screen_status("3-1-7-702", "offline")

    def test_filter_online(self):
        resp = self.client.get("/api/device-management/device-list/?screen_status=online")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "701")

    def test_filter_offline(self):
        resp = self.client.get("/api/device-management/device-list/?screen_status=offline")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "702")

    def test_filter_unknown(self):
        resp = self.client.get("/api/device-management/device-list/?screen_status=unknown")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "703")


@tag('e2e')
class TC_E2E_US005_SystemSwitchFilter(TestCase):
    """TC-E2E-US005: US-005 — 系统开关过滤"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_us005")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        for room, sw_val in [("701", 1), ("702", 0)]:
            _make_owner(f"3-1-7-{room}", building="3", unit="1", room_number=room)
            PLCLatestData.objects.create(
                specific_part=f"3-1-7-{room}", param_name="system_switch",
                value=sw_val, building="3", unit="1", room_number=room,
                collected_at=datetime.now(),
            )
        # 703: 无记录
        _make_owner("3-1-7-703", building="3", unit="1", room_number="703")

    def test_filter_on(self):
        resp = self.client.get("/api/device-management/device-list/?system_switch=on")
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "701")

    def test_filter_off_includes_zero_and_null(self):
        resp = self.client.get("/api/device-management/device-list/?system_switch=off")
        data = resp.json()
        # 702 (value=0) + 703 (NULL)
        self.assertEqual(data["count"], 2)


@tag('e2e')
class TC_E2E_US006_ScreenStatusPipelineIntegration(TestCase):
    """TC-E2E-US006: US-006 — 大屏状态写入管道（heartbeat→DB→API）集成（已适配心跳方案）"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_us006")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")

    def test_handler_pipeline_online_status_visible_in_api(self):
        """Handler 写入 online → API 返回 online（last_seen_at = now，在阈值内）"""
        handler = ScreenConnectivityHandler()
        payload = {"specific_part": "3-1-7-702", "status": "online", "checked_at": "2026-04-27T12:00:00"}
        handler.handle("/datacollection/screen/connectivity", payload)

        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-702")
        data = resp.json()
        self.assertEqual(data["results"][0]["screen_status"], "online")

    def test_old_heartbeat_becomes_offline(self):
        """last_seen_at 超过阈值 → API 返回 offline"""
        from api.views import ONLINE_THRESHOLD_MINUTES
        from datetime import timedelta
        ScreenConnectivityStatus.objects.create(
            specific_part="3-1-7-702",
            last_seen_at=timezone.now() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES + 30),
        )
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-702")
        data = resp.json()
        self.assertEqual(data["results"][0]["screen_status"], "offline")


@tag('e2e')
class TC_E2E_US007_DevicePanelEntry(TestCase):
    """TC-E2E-US007: US-007 — 设备面板入口（specific_part 在响应中可用）"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_us007")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")

    def test_specific_part_in_each_result(self):
        """每条结果包含 specific_part，可作为设备面板入口参数"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        for item in data["results"]:
            self.assertIn("specific_part", item)
            self.assertTrue(item["specific_part"])  # 非空

    def test_specific_part_format_four_segments(self):
        """specific_part 格式为四段（楼-单-层-户）"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        for item in data["results"]:
            parts = item["specific_part"].split("-")
            self.assertEqual(len(parts), 4, f"specific_part 格式错误: {item['specific_part']}")


@tag('e2e')
class TC_E2E_NFR_Performance(TestCase):
    """TC-E2E-NFR: NFR-003 — 响应时间与分页性能（50条以内，无严格时间要求于测试环境）"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_nfr")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 创建 50 条测试数据（模拟真实数据量）
        for i in range(1, 51):
            OwnerInfo.objects.create(
                specific_part=f"3-1-{i}-{700+i}",
                location_name=f"NFR测试-{i}",
                building="3",
                unit="1",
                floor=f"{i}楼",
                room_number=str(700 + i),
                bind_status="已绑定",
                ip_address=f"192.168.{i//256}.{i%256}",
                unique_id=f"nfr{i:05d}",
                plc_ip_address=f"10.0.{i//256}.{i%256}",
            )

    def test_50_records_returned_with_page_size_50(self):
        """50 条数据可在单页返回（NFR-003 分页上限）"""
        resp = self.client.get("/api/device-management/device-list/?page_size=50")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 50)
        self.assertEqual(len(data["results"]), 50)

    def test_combined_filters_work_together(self):
        """多个过滤条件同时生效（room_no + screen_status）"""
        # 给前5条设置 online 状态（last_seen_at = now，在阈值内）
        for i in range(1, 6):
            ScreenConnectivityStatus.objects.create(
                specific_part=f"3-1-{i}-{700+i}",
                last_seen_at=timezone.now(),
            )

        resp = self.client.get("/api/device-management/device-list/?room_no=3-1&screen_status=online")
        data = resp.json()
        self.assertEqual(data["count"], 5)
        for item in data["results"]:
            self.assertEqual(item["screen_status"], "online")


# ===========================================================================
# 新增：PLC 状态字段与过滤测试（2026-05-01）
# ===========================================================================

@tag('integration')
class TC_I_007_DeviceListAPIPlcStatusFields(TestCase):
    """TC-I-007: 设备列表 API — plc_status / plc_last_online_time 字段测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_plc_field_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        _make_owner("3-1-7-703", building="3", unit="1", room_number="703")

        # 701: PLC online，有 last_online_time
        _make_plc_connection_status("3-1-7-701", connection_status="online")
        # 702: PLC offline，last_online_time=None
        _make_plc_connection_status("3-1-7-702", connection_status="offline", last_online_time=None)
        # 703: 无 PLCConnectionStatus 记录 → unknown

    def test_plc_status_online(self):
        """有 online PLCConnectionStatus 记录时，plc_status=online"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-701")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        item = data["results"][0]
        self.assertEqual(item["plc_status"], "online")
        self.assertIsNotNone(item["plc_last_online_time"])

    def test_plc_status_offline(self):
        """有 offline PLCConnectionStatus 记录时，plc_status=offline"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-702")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        item = data["results"][0]
        self.assertEqual(item["plc_status"], "offline")
        self.assertIsNone(item["plc_last_online_time"])

    def test_plc_status_unknown_when_no_record(self):
        """无 PLCConnectionStatus 记录时，plc_status=unknown，plc_last_online_time=null"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-703")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        item = data["results"][0]
        self.assertEqual(item["plc_status"], "unknown")
        self.assertIsNone(item["plc_last_online_time"])

    def test_screen_last_checked_at_not_in_response(self):
        """响应中不含已移除的 screen_last_checked_at 字段"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for item in data["results"]:
            self.assertNotIn("screen_last_checked_at", item)

    def test_plc_fields_present_in_all_results(self):
        """所有结果条目均含 plc_status 和 plc_last_online_time 字段"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for item in data["results"]:
            self.assertIn("plc_status", item)
            self.assertIn("plc_last_online_time", item)


@tag('integration')
class TC_I_008_DeviceListAPIPlcStatusFilter(TestCase):
    """TC-I-008: 设备列表 API — plc_status 过滤参数测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_plc_filter_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        _make_owner("3-1-7-703", building="3", unit="1", room_number="703")

        _make_plc_connection_status("3-1-7-701", connection_status="online")
        _make_plc_connection_status("3-1-7-702", connection_status="offline", last_online_time=None)
        # 703: 无记录 → unknown，不被 online/offline 过滤命中

    def test_filter_plc_status_online(self):
        """plc_status=online 过滤：只返回 PLCConnectionStatus.connection_status=online 的记录"""
        resp = self.client.get("/api/device-management/device-list/?plc_status=online")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "701")
        self.assertEqual(data["results"][0]["plc_status"], "online")

    def test_filter_plc_status_offline(self):
        """plc_status=offline 过滤：只返回 PLCConnectionStatus.connection_status=offline 的记录"""
        resp = self.client.get("/api/device-management/device-list/?plc_status=offline")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "702")
        self.assertEqual(data["results"][0]["plc_status"], "offline")

    def test_filter_plc_status_does_not_include_unknown(self):
        """plc_status=online/offline 均不返回无 PLCConnectionStatus 记录（unknown）的户"""
        resp_online = self.client.get("/api/device-management/device-list/?plc_status=online")
        resp_offline = self.client.get("/api/device-management/device-list/?plc_status=offline")

        online_rooms = {r["room_number"] for r in resp_online.json()["results"]}
        offline_rooms = {r["room_number"] for r in resp_offline.json()["results"]}

        self.assertNotIn("703", online_rooms)
        self.assertNotIn("703", offline_rooms)

    def test_no_plc_filter_returns_all(self):
        """不传 plc_status 参数时，返回全部3条记录"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)

    def test_combined_plc_status_and_room_no_filter(self):
        """plc_status=online AND room_no=3-1 同时生效"""
        resp = self.client.get("/api/device-management/device-list/?plc_status=online&room_no=3-1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "701")


@tag('integration')
class TC_I_009_PlcStatusUnknownDegradation(TestCase):
    """TC-I-009: PLCConnectionStatus 无记录时的 unknown 降级测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_plc_unknown_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

    def test_owner_with_no_plc_record_returns_unknown_status(self):
        """OwnerInfo 存在但 PLCConnectionStatus 无记录，plc_status=unknown"""
        _make_owner("5-2-3-301", building="5", unit="2", room_number="301")
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        item = data["results"][0]
        self.assertEqual(item["plc_status"], "unknown")
        self.assertIsNone(item["plc_last_online_time"])

    def test_multiple_owners_mixed_plc_records(self):
        """部分户有 PLCConnectionStatus，部分没有；unknown 降级不影响其他户的正常返回"""
        _make_owner("5-2-3-301", building="5", unit="2", room_number="301")
        _make_owner("5-2-3-302", building="5", unit="2", room_number="302")
        _make_owner("5-2-3-303", building="5", unit="2", room_number="303")

        _make_plc_connection_status("5-2-3-301", connection_status="online")
        # 302, 303 无记录

        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)

        items_by_room = {item["room_number"]: item for item in data["results"]}
        self.assertEqual(items_by_room["301"]["plc_status"], "online")
        self.assertEqual(items_by_room["302"]["plc_status"], "unknown")
        self.assertEqual(items_by_room["303"]["plc_status"], "unknown")


# ===========================================================================
# v2 新增：运行模式列测试（AC-103~105, US-101~104）
# ===========================================================================

@tag('integration')
class TC_I_010_OperationModeField(TestCase):
    """TC-I-010: 运行模式字段 operation_mode_value / operation_mode_display — 集成测试（AC-103~105）"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_opmode_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 四个户：覆盖四种枚举值 + 无记录
        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        _make_owner("3-1-7-703", building="3", unit="1", room_number="703")
        _make_owner("3-1-7-704", building="3", unit="1", room_number="704")
        _make_owner("3-1-7-705", building="3", unit="1", room_number="705")

        # 701: operation_mode=1 → 制冷
        PLCLatestData.objects.create(
            specific_part="3-1-7-701", param_name="operation_mode", value=1,
            building="3", unit="1", room_number="701", collected_at=datetime.now(),
        )
        # 702: operation_mode=2 → 制热
        PLCLatestData.objects.create(
            specific_part="3-1-7-702", param_name="operation_mode", value=2,
            building="3", unit="1", room_number="702", collected_at=datetime.now(),
        )
        # 703: operation_mode=3 → 通风
        PLCLatestData.objects.create(
            specific_part="3-1-7-703", param_name="operation_mode", value=3,
            building="3", unit="1", room_number="703", collected_at=datetime.now(),
        )
        # 704: operation_mode=4 → 除湿
        PLCLatestData.objects.create(
            specific_part="3-1-7-704", param_name="operation_mode", value=4,
            building="3", unit="1", room_number="704", collected_at=datetime.now(),
        )
        # 705: 无 operation_mode 记录 → 未知

    def _get_item(self, room_number):
        resp = self.client.get(f"/api/device-management/device-list/?room_no=3-1-{room_number}")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        return data["results"][0]

    def test_operation_mode_1_cooling(self):
        """AC-103: value=1 → operation_mode_display='制冷', value=1"""
        item = self._get_item("701")
        self.assertEqual(item["operation_mode_value"], 1)
        self.assertEqual(item["operation_mode_display"], "制冷")

    def test_operation_mode_2_heating(self):
        """AC-103: value=2 → operation_mode_display='制热'"""
        item = self._get_item("702")
        self.assertEqual(item["operation_mode_value"], 2)
        self.assertEqual(item["operation_mode_display"], "制热")

    def test_operation_mode_3_ventilation(self):
        """AC-105: value=3 → operation_mode_display='通风'"""
        item = self._get_item("703")
        self.assertEqual(item["operation_mode_value"], 3)
        self.assertEqual(item["operation_mode_display"], "通风")

    def test_operation_mode_4_dehumidification(self):
        """AC-105: value=4 → operation_mode_display='除湿'"""
        item = self._get_item("704")
        self.assertEqual(item["operation_mode_value"], 4)
        self.assertEqual(item["operation_mode_display"], "除湿")

    def test_operation_mode_null_when_no_record(self):
        """AC-104: 无 operation_mode 记录 → operation_mode_value=null, display='未知'"""
        item = self._get_item("705")
        self.assertIsNone(item["operation_mode_value"])
        self.assertEqual(item["operation_mode_display"], "未知")

    def test_operation_mode_fields_present_in_all_results(self):
        """NFR-102: 所有结果条目均含 operation_mode_value 和 operation_mode_display 字段"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        for item in data["results"]:
            self.assertIn("operation_mode_value", item, f"缺少 operation_mode_value: {item}")
            self.assertIn("operation_mode_display", item, f"缺少 operation_mode_display: {item}")

    def test_existing_fields_not_removed(self):
        """NFR-102: 新增字段不删除原有字段（向后兼容）"""
        resp = self.client.get("/api/device-management/device-list/")
        data = resp.json()
        item = data["results"][0]
        for field in ("specific_part", "building", "unit", "room_number",
                      "screen_status", "system_switch_value", "system_switch_display",
                      "plc_status", "plc_last_online_time"):
            self.assertIn(field, item, f"原有字段被移除: {field}")

    def test_operation_mode_unknown_integer_displays_unknown(self):
        """AC-105: 枚举范围外的整数（如 99）→ display='未知'"""
        _make_owner("3-1-7-799", building="3", unit="1", room_number="799")
        PLCLatestData.objects.create(
            specific_part="3-1-7-799", param_name="operation_mode", value=99,
            building="3", unit="1", room_number="799", collected_at=datetime.now(),
        )
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-799")
        data = resp.json()
        item = data["results"][0]
        self.assertEqual(item["operation_mode_display"], "未知")


@tag('e2e')
class TC_E2E_US103_OperationModeColumn(TestCase):
    """TC-E2E-US103: US-103/104 E2E验收 — 运行模式列在设备列表中展示"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_e2e_us103")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 多户：含有 operation_mode 和无记录的混合场景
        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")

        PLCLatestData.objects.create(
            specific_part="3-1-7-701", param_name="operation_mode", value=2,
            building="3", unit="1", room_number="701", collected_at=datetime.now(),
        )
        # 702: 无记录

    def test_us103_mode_display_when_data_exists(self):
        """US-103: PLC 有 operation_mode 数据 → 显示对应中文（制热）"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-701")
        data = resp.json()
        item = data["results"][0]
        self.assertEqual(item["operation_mode_display"], "制热")
        self.assertEqual(item["operation_mode_value"], 2)

    def test_us104_mode_display_when_no_data(self):
        """US-104: PLCLatestData 无 operation_mode 记录 → 显示'未知'"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1-702")
        data = resp.json()
        item = data["results"][0]
        self.assertEqual(item["operation_mode_display"], "未知")
        self.assertIsNone(item["operation_mode_value"])

    def test_no_model_changes(self):
        """NFR-103: 无 migration 变更，运行模式来自现有 PLCLatestData 表"""
        # 直接查询 PLCLatestData 验证数据可访问
        om_record = PLCLatestData.objects.get(
            specific_part="3-1-7-701", param_name="operation_mode"
        )
        self.assertEqual(om_record.value, 2)


@tag('integration')
class TC_I_011_RoomNoFilterBuildingUnit(TestCase):
    """TC-I-011: room_no 仅传楼栋或楼栋+单元的过滤（US-101/102，REQ-FUNC-001）"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_roomno_bu_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 楼栋3，单元1：2户
        _make_owner("3-1-7-701", building="3", unit="1", room_number="701")
        _make_owner("3-1-7-702", building="3", unit="1", room_number="702")
        # 楼栋3，单元2：1户
        _make_owner("3-2-7-301", building="3", unit="2", room_number="301")
        # 楼栋4：1户
        _make_owner("4-1-5-501", building="4", unit="1", room_number="501")

    def test_room_no_building_only_returns_all_in_building(self):
        """US-101: room_no=3 返回所有 building=3 的户（共3户）"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 3)
        for item in data["results"]:
            self.assertIn(item["building"], ("3", "3栋"))

    def test_room_no_building_unit_returns_correct_unit(self):
        """US-102: room_no=3-1 返回 building=3, unit=1 的户（共2户）"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 2)
        for item in data["results"]:
            self.assertIn(item["building"], ("3", "3栋"))
            self.assertIn(item["unit"], ("1", "1单元"))

    def test_room_no_building_unit_excludes_other_units(self):
        """US-102: room_no=3-2 只返回单元2的户"""
        resp = self.client.get("/api/device-management/device-list/?room_no=3-2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "301")

    def test_room_no_building_excludes_other_buildings(self):
        """US-101: room_no=4 只返回 building=4 的户"""
        resp = self.client.get("/api/device-management/device-list/?room_no=4")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "501")


# ===========================================================================
# 新增：运行模式过滤参数测试（2026-05-04）
# ===========================================================================

@tag('integration')
class TC_I_012_OperationModeFilter(TestCase):
    """TC-I-012: 设备列表 API — operation_mode 过滤参数测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("dm_opmode_filter_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 701: operation_mode=1 制冷
        # 702: operation_mode=2 制热
        # 703: operation_mode=3 通风
        # 704: operation_mode=4 除湿
        # 705: 无 operation_mode 记录
        for room, om_val in [("701", 1), ("702", 2), ("703", 3), ("704", 4)]:
            _make_owner(f"3-1-7-{room}", building="3", unit="1", room_number=room)
            PLCLatestData.objects.create(
                specific_part=f"3-1-7-{room}", param_name="operation_mode",
                value=om_val, building="3", unit="1", room_number=room,
                collected_at=datetime.now(),
            )
        _make_owner("3-1-7-705", building="3", unit="1", room_number="705")

    def test_filter_operation_mode_1_cooling(self):
        """operation_mode=1 只返回制冷的户（701）"""
        resp = self.client.get("/api/device-management/device-list/?operation_mode=1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "701")
        self.assertEqual(data["results"][0]["operation_mode_display"], "制冷")

    def test_filter_operation_mode_2_heating(self):
        """operation_mode=2 只返回制热的户（702）"""
        resp = self.client.get("/api/device-management/device-list/?operation_mode=2")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "702")
        self.assertEqual(data["results"][0]["operation_mode_display"], "制热")

    def test_filter_operation_mode_3_ventilation(self):
        """operation_mode=3 只返回通风的户（703）"""
        resp = self.client.get("/api/device-management/device-list/?operation_mode=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "703")
        self.assertEqual(data["results"][0]["operation_mode_display"], "通风")

    def test_filter_operation_mode_4_dehumidification(self):
        """operation_mode=4 只返回除湿的户（704）"""
        resp = self.client.get("/api/device-management/device-list/?operation_mode=4")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "704")
        self.assertEqual(data["results"][0]["operation_mode_display"], "除湿")

    def test_filter_operation_mode_excludes_null_records(self):
        """operation_mode=1 不返回无 operation_mode 记录的户（705）"""
        resp = self.client.get("/api/device-management/device-list/?operation_mode=1")
        data = resp.json()
        room_numbers = {r["room_number"] for r in data["results"]}
        self.assertNotIn("705", room_numbers)

    def test_no_operation_mode_filter_returns_all(self):
        """不传 operation_mode 参数时，返回全部5条记录"""
        resp = self.client.get("/api/device-management/device-list/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 5)

    def test_invalid_operation_mode_returns_all(self):
        """operation_mode=abc 非法值被忽略，返回全部5条记录"""
        resp = self.client.get("/api/device-management/device-list/?operation_mode=abc")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 5)

    def test_combined_operation_mode_and_room_no_filter(self):
        """operation_mode=2 AND room_no=3-1 同时生效，只返回702"""
        resp = self.client.get("/api/device-management/device-list/?operation_mode=2&room_no=3-1")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["count"], 1)
        self.assertEqual(data["results"][0]["room_number"], "702")
