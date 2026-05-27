"""
设备列表故障状态过滤功能测试 — freeark_device_list_fault_filter
GROUP_D: PHASE_07 单元测试 + PHASE_08 集成测试

覆盖：US-FFF-001~007，REQ-FUNC-FFF-01/02/03，REQ-NFR-FFF-01
ADR-FFF-001（Python 层过滤）、ADR-FFF-002（screen_status 先于 fault_status）、
ADR-FFF-003（fault_count=None 两侧排除）

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_device_list_fault_filter \
        --settings=freearkweb.test_settings --verbosity=2
"""

from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import (
    CustomUser,
    OwnerInfo,
    PLCLatestData,
    ScreenConnectivityStatus,
    PLCConnectionStatus,
)


# ---------------------------------------------------------------------------
# Fixtures helpers
# ---------------------------------------------------------------------------

def _make_user(username="u_fff", role="user"):
    user = CustomUser.objects.create_user(username=username, password="pass_fff", role=role)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _make_owner(specific_part, building="1", unit="1", room_number="101"):
    return OwnerInfo.objects.get_or_create(
        specific_part=specific_part,
        defaults=dict(
            location_name=f"测试-{specific_part}",
            building=building,
            unit=unit,
            floor="1楼",
            room_number=room_number,
            bind_status="已绑定",
            ip_address="192.168.1.1",
            unique_id=specific_part.replace("-", ""),
            plc_ip_address="192.168.2.1",
        ),
    )[0]


def _make_plc_latest(specific_part, param_name, value):
    obj, _ = PLCLatestData.objects.update_or_create(
        specific_part=specific_part,
        param_name=param_name,
        defaults={"value": value},
    )
    return obj


# ---------------------------------------------------------------------------
# 单元测试：Python 层过滤逻辑直接针对视图函数行为
# ---------------------------------------------------------------------------


class TestFaultStatusFilterLogicUnit(TestCase):
    """
    PHASE_07 单元测试：直接测试 device_management_device_list 视图中
    fault_status 参数解析与过滤的核心逻辑，mock get_fault_count_batch_cached。
    """

    def setUp(self):
        self.user, self.token = _make_user()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 建立 3 个 owner：有故障(2条)、无故障(1条)、None(1条)
        self.sp_has = "1-1-1-101"   # fault_count=3
        self.sp_none_ = "1-1-1-102"  # fault_count=5 (also has_fault)
        self.sp_zero = "1-1-1-103"  # fault_count=0
        self.sp_null = "1-1-1-104"  # fault_count=None

        for idx, sp in enumerate([self.sp_has, self.sp_none_, self.sp_zero, self.sp_null], 1):
            _make_owner(sp, building="1", unit="1", room_number=f"10{idx}")

        # mock 返回的故障数字典
        self.fault_map = {
            self.sp_has: 3,
            self.sp_none_: 5,
            self.sp_zero: 0,
            self.sp_null: None,
        }

    def _get(self, params):
        return self.client.get("/api/device-management/device-list/", params)

    # UT-FFF-01: has_fault 只返回 fault_count > 0 的设备
    def test_has_fault_returns_only_positive_fault_count(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "has_fault", "page_size": 50})
        self.assertEqual(resp.status_code, 200)
        sps = {r["specific_part"] for r in resp.data["results"]}
        self.assertIn(self.sp_has, sps)
        self.assertIn(self.sp_none_, sps)
        self.assertNotIn(self.sp_zero, sps)
        self.assertNotIn(self.sp_null, sps)

    # UT-FFF-02: no_fault 只返回 fault_count == 0 的设备
    def test_no_fault_returns_only_zero_fault_count(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "no_fault", "page_size": 50})
        self.assertEqual(resp.status_code, 200)
        sps = {r["specific_part"] for r in resp.data["results"]}
        self.assertIn(self.sp_zero, sps)
        self.assertNotIn(self.sp_has, sps)
        self.assertNotIn(self.sp_none_, sps)
        self.assertNotIn(self.sp_null, sps)

    # UT-FFF-03: ADR-FFF-003 — fault_count=None 在 has_fault 侧不出现
    def test_none_device_excluded_from_has_fault(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "has_fault", "page_size": 50})
        sps = {r["specific_part"] for r in resp.data["results"]}
        self.assertNotIn(self.sp_null, sps)

    # UT-FFF-04: ADR-FFF-003 — fault_count=None 在 no_fault 侧不出现
    def test_none_device_excluded_from_no_fault(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "no_fault", "page_size": 50})
        sps = {r["specific_part"] for r in resp.data["results"]}
        self.assertNotIn(self.sp_null, sps)

    # UT-FFF-05: 无 fault_status 参数时行为与 v0.5.3-FCC 一致，fault_count=None 正常出现
    def test_no_fault_status_param_returns_all_owners_with_null_fault_count(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"page_size": 50})
        self.assertEqual(resp.status_code, 200)
        sps = {r["specific_part"] for r in resp.data["results"]}
        self.assertIn(self.sp_null, sps)
        # fault_count 字段值为 None（前端展示 —）
        null_row = next(r for r in resp.data["results"] if r["specific_part"] == self.sp_null)
        self.assertIsNone(null_row["fault_count"])

    # UT-FFF-06: 非法 fault_status 值静默忽略，返回全量（4条）
    def test_invalid_fault_status_value_is_ignored(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "invalid_value", "page_size": 50})
        self.assertEqual(resp.status_code, 200)
        # 非法值静默忽略，不过滤，返回全量 4 条
        self.assertEqual(resp.data["count"], 4)

    # UT-FFF-07: REQ-FUNC-FFF-03 — has_fault 时 count 等于过滤后总数
    def test_count_reflects_filtered_total_has_fault(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "has_fault", "page_size": 50})
        # sp_has(3) 和 sp_none_(5) 满足条件，共 2 条
        self.assertEqual(resp.data["count"], 2)

    # UT-FFF-08: REQ-FUNC-FFF-03 — no_fault 时 count 等于过滤后总数
    def test_count_reflects_filtered_total_no_fault(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "no_fault", "page_size": 50})
        # 只有 sp_zero(0) 满足条件，共 1 条
        self.assertEqual(resp.data["count"], 1)


# ---------------------------------------------------------------------------
# 集成测试：分页联动 + AND 叠加
# ---------------------------------------------------------------------------


class TestFaultStatusFilterIntegration(TestCase):
    """
    PHASE_08 集成测试：分页 total 正确性、与 screen_status AND 叠加、
    REQ-NFR-FFF-01（不重复调用 get_fault_count_batch_cached）。
    """

    def setUp(self):
        self.user, self.token = _make_user(username="u_fff_int")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        # 建立 5 个 owner（楼栋 2）
        self.owners = []
        for i in range(1, 6):
            sp = f"2-1-1-20{i}"
            owner = _make_owner(sp, building="2", unit="1", room_number=f"20{i}")
            self.owners.append(owner)

        # fault_map: owner[0]=5, [1]=0, [2]=None, [3]=2, [4]=0
        self.fault_map = {
            "2-1-1-201": 5,
            "2-1-1-202": 0,
            "2-1-1-203": None,
            "2-1-1-204": 2,
            "2-1-1-205": 0,
        }

    def _get(self, params):
        return self.client.get("/api/device-management/device-list/", params)

    # IT-FFF-01: 分页 total 正确（全 5 条，has_fault 有 2 条，page_size=1 时翻页）
    def test_pagination_total_correct_has_fault(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "has_fault", "page": 1, "page_size": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)   # 201(5) + 204(2)
        self.assertEqual(len(resp.data["results"]), 1)  # page_size=1

    def test_pagination_total_correct_no_fault(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "no_fault", "page": 1, "page_size": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)   # 202(0) + 205(0)
        self.assertEqual(len(resp.data["results"]), 1)

    # IT-FFF-02: ADR-FFF-002 — screen_status + fault_status AND 叠加
    # 设备 201 大屏 online + fault_count=5 → 满足；203 online + None → 排除
    def test_screen_status_and_fault_status_combination(self):
        # 让 201 大屏 online，其余无 ScreenConnectivity 记录（unknown）
        ScreenConnectivityStatus.objects.create(
            specific_part="2-1-1-201",
            last_seen_at=timezone.now(),
        )
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({
                "screen_status": "online",
                "fault_status": "has_fault",
                "page_size": 50,
            })
        self.assertEqual(resp.status_code, 200)
        sps = {r["specific_part"] for r in resp.data["results"]}
        # 只有 201（online AND has_fault）满足
        self.assertEqual(sps, {"2-1-1-201"})
        self.assertEqual(resp.data["count"], 1)

    # IT-FFF-03: REQ-NFR-FFF-01 — fault_status 存在时 get_fault_count_batch_cached 只调用一次
    def test_no_extra_db_query_when_fault_status_present(self):
        call_count = {"n": 0}
        original_map = dict(self.fault_map)

        def mock_cached(specific_parts):
            call_count["n"] += 1
            return {sp: original_map.get(sp) for sp in specific_parts}

        with patch("api.views.get_fault_count_batch_cached", side_effect=mock_cached):
            resp = self._get({"fault_status": "has_fault", "page_size": 50})

        self.assertEqual(resp.status_code, 200)
        # step 8b（全量查）后 step 9a 直接复用，不应再次调用
        self.assertEqual(call_count["n"], 1, "get_fault_count_batch_cached 应只调用一次（REQ-NFR-FFF-01）")

    # IT-FFF-04: no_fault 时 get_fault_count_batch_cached 也只调用一次
    def test_no_extra_db_query_no_fault(self):
        call_count = {"n": 0}
        original_map = dict(self.fault_map)

        def mock_cached(specific_parts):
            call_count["n"] += 1
            return {sp: original_map.get(sp) for sp in specific_parts}

        with patch("api.views.get_fault_count_batch_cached", side_effect=mock_cached):
            resp = self._get({"fault_status": "no_fault", "page_size": 50})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(call_count["n"], 1, "get_fault_count_batch_cached 应只调用一次（REQ-NFR-FFF-01）")

    # IT-FFF-05: 无 fault_status 时依然使用原有逻辑（page_rows 级别查询，call_count=1）
    def test_no_fault_status_still_queries_page_rows(self):
        call_count = {"n": 0}
        original_map = dict(self.fault_map)

        def mock_cached(specific_parts):
            call_count["n"] += 1
            return {sp: original_map.get(sp) for sp in specific_parts}

        with patch("api.views.get_fault_count_batch_cached", side_effect=mock_cached):
            resp = self._get({"page_size": 50})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(call_count["n"], 1)

    # IT-FFF-06: US-FFF-007 AC-FFF-007-01 — 总数 45 条场景模拟（page_size=20，count 正确）
    def test_page1_count_correct_simulates_45_devices(self):
        """
        模拟更大数据集：45 台有故障，验证 page=1 count=45，results=5（page_size=5）。
        本测试仅用 5 条实际 owner，但通过 mock 让全部 5 条 fault_count>0，
        验证 count=5 / results=page_size 的正确性（与 45 条等比缩小的等效场景）。
        """
        all_has_fault = {sp: (i + 1) for i, sp in enumerate(self.fault_map.keys())}
        with patch("api.views.get_fault_count_batch_cached", return_value=all_has_fault):
            resp = self._get({"fault_status": "has_fault", "page": 1, "page_size": 3})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 5)
        self.assertEqual(len(resp.data["results"]), 3)

    # IT-FFF-07: 越界分页（page=999）时结果 results 为空，count 不变
    def test_out_of_range_page_returns_empty_results(self):
        with patch("api.views.get_fault_count_batch_cached", return_value=self.fault_map):
            resp = self._get({"fault_status": "has_fault", "page": 999, "page_size": 20})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["results"], [])
        self.assertEqual(resp.data["count"], 2)  # 总数不变


# ---------------------------------------------------------------------------
# E2E 验收测试：通过实际 PLCLatestData 数据验证端到端行为
# ---------------------------------------------------------------------------


class TestFaultStatusFilterE2E(TestCase):
    """
    PHASE_09 E2E 验收测试：种入真实 PLCLatestData，验证 get_fault_count_batch_cached
    在真实 SQLite 下的行为与接口返回的一致性。
    不 mock get_fault_count_batch_cached（E2E 层真实调用）。
    """

    def setUp(self):
        self.user, self.token = _make_user(username="u_fff_e2e")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token}")

        self.sp_faulty = "9-1-1-901"
        self.sp_healthy = "9-1-1-902"
        self.sp_nodata = "9-1-1-903"

        _make_owner(self.sp_faulty, building="9", unit="1", room_number="901")
        _make_owner(self.sp_healthy, building="9", unit="1", room_number="902")
        _make_owner(self.sp_nodata, building="9", unit="1", room_number="903")

        # sp_faulty 有故障（fault_count 由 get_fault_count_batch_cached 从 PLCLatestData 计算）
        # 使用真实的故障参数名（来自 fault_utils.FAULT_PARAM_NAMES）
        from api.fault_utils import FAULT_PARAM_NAMES
        # 种入两个故障参数（value 非零）
        fault_params = list(FAULT_PARAM_NAMES)[:2] if len(FAULT_PARAM_NAMES) >= 2 else list(FAULT_PARAM_NAMES)
        for pname in fault_params:
            _make_plc_latest(self.sp_faulty, pname, 1)  # value=1 → 有故障位

        # sp_healthy 种入所有故障参数为 0（无故障）
        for pname in FAULT_PARAM_NAMES:
            _make_plc_latest(self.sp_healthy, pname, 0)

        # sp_nodata 不种入任何 PLCLatestData 记录

    def _get(self, params):
        return self.client.get("/api/device-management/device-list/", params)

    # E2E-FFF-01: has_fault 真实数据验证
    def test_e2e_has_fault_with_real_data(self):
        resp = self._get({"fault_status": "has_fault", "page_size": 50})
        self.assertEqual(resp.status_code, 200)
        sps = {r["specific_part"] for r in resp.data["results"]}
        self.assertIn(self.sp_faulty, sps)
        self.assertNotIn(self.sp_healthy, sps)
        self.assertNotIn(self.sp_nodata, sps)

    # E2E-FFF-02: no_fault 真实数据验证
    def test_e2e_no_fault_with_real_data(self):
        resp = self._get({"fault_status": "no_fault", "page_size": 50})
        self.assertEqual(resp.status_code, 200)
        sps = {r["specific_part"] for r in resp.data["results"]}
        self.assertIn(self.sp_healthy, sps)
        self.assertNotIn(self.sp_faulty, sps)
        self.assertNotIn(self.sp_nodata, sps)

    # E2E-FFF-03: 无 fault_status 时 nodata 设备出现且 fault_count=None
    def test_e2e_nodata_device_appears_without_filter(self):
        resp = self._get({"page_size": 50})
        self.assertEqual(resp.status_code, 200)
        sps = {r["specific_part"] for r in resp.data["results"]}
        self.assertIn(self.sp_nodata, sps)
        nodata_row = next(r for r in resp.data["results"] if r["specific_part"] == self.sp_nodata)
        self.assertIsNone(nodata_row["fault_count"])

    # E2E-FFF-04: US-FFF-006 AC-FFF-006-01/02 — nodata 在两侧均不出现
    def test_e2e_nodata_excluded_from_both_sides(self):
        for fault_status in ("has_fault", "no_fault"):
            with self.subTest(fault_status=fault_status):
                resp = self._get({"fault_status": fault_status, "page_size": 50})
                sps = {r["specific_part"] for r in resp.data["results"]}
                self.assertNotIn(self.sp_nodata, sps,
                                 msg=f"sp_nodata 不应出现在 fault_status={fault_status} 结果中")
