"""
FreeArk API 单元测试

覆盖范围：
- 数据模型（CustomUser, PLCData, UsageQuantityDaily, UsageQuantityMonthly,
           PLCConnectionStatus, PLCStatusChangeHistory, SpecificPartInfo）
- DailyUsageCalculator 核心计算逻辑
- MonthlyUsageCalculator 核心计算逻辑
- PLCDataHandler / ConnectionStatusHandler（MQTT 消息处理）
- plc_data_cleaner 清理函数
- 所有 REST API 视图（认证、用量查询、账单、PLC 状态）

运行方式（在 FreeArkWeb/backend/freearkweb/ 目录下）：
    python manage.py test api.tests --settings=freearkweb.settings
"""

from datetime import date, timedelta, datetime
from unittest.mock import patch, MagicMock

from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import (
    CustomUser,
    PLCData,
    UsageQuantityDaily,
    UsageQuantityMonthly,
    PLCConnectionStatus,
    PLCStatusChangeHistory,
    SpecificPartInfo,
)
from .daily_usage_calculator import DailyUsageCalculator
from .monthly_usage_calculator import MonthlyUsageCalculator
from .plc_data_cleaner import clean_old_plc_data
from .mqtt_handlers import PLCDataHandler, ConnectionStatusHandler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username="testuser", role="user", password="testpass123"):
    """创建并返回一个测试用户及其 Token"""
    user = CustomUser.objects.create_user(
        username=username,
        password=password,
        role=role,
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token


def make_daily_record(
    specific_part="3-1-7-702",
    energy_mode="制冷",
    time_period=None,
    initial_energy=1000,
    final_energy=1100,
    usage_quantity=100,
):
    if time_period is None:
        time_period = date.today()
    return UsageQuantityDaily.objects.create(
        specific_part=specific_part,
        building=specific_part.split("-")[0],
        unit=specific_part.split("-")[1],
        room_number=specific_part.split("-")[3] if len(specific_part.split("-")) == 4 else specific_part.split("-")[2],
        energy_mode=energy_mode,
        initial_energy=initial_energy,
        final_energy=final_energy,
        usage_quantity=usage_quantity,
        time_period=time_period,
    )


def make_monthly_record(
    specific_part="3-1-7-702",
    energy_mode="制冷",
    usage_month="2025-01",
    initial_energy=1000,
    final_energy=1100,
    usage_quantity=100,
):
    return UsageQuantityMonthly.objects.create(
        specific_part=specific_part,
        building=specific_part.split("-")[0],
        unit=specific_part.split("-")[1],
        room_number=specific_part.split("-")[3] if len(specific_part.split("-")) == 4 else specific_part.split("-")[2],
        energy_mode=energy_mode,
        initial_energy=initial_energy,
        final_energy=final_energy,
        usage_quantity=usage_quantity,
        usage_month=usage_month,
    )


# ===========================================================================
# 一、数据模型测试
# ===========================================================================

class CustomUserModelTest(TestCase):
    """CustomUser 模型基本功能测试"""

    def test_create_user_default_role(self):
        """新建用户默认角色为 user"""
        user = CustomUser.objects.create_user(username="alice", password="pwd")
        self.assertEqual(user.role, "user")

    def test_create_admin_user(self):
        """创建 admin 角色用户"""
        user = CustomUser.objects.create_user(username="bob", password="pwd", role="admin")
        self.assertEqual(user.role, "admin")

    def test_str_returns_username(self):
        """__str__ 应返回用户名"""
        user = CustomUser.objects.create_user(username="carol", password="pwd")
        self.assertEqual(str(user), "carol")

    def test_department_and_position_optional(self):
        """department 和 position 字段允许为空"""
        user = CustomUser.objects.create_user(username="dave", password="pwd")
        self.assertIsNone(user.department)
        self.assertIsNone(user.position)


class PLCDataModelTest(TestCase):
    """PLCData 模型约束测试"""

    def test_create_plc_data(self):
        """正常创建 PLCData 记录"""
        record = PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            value=12345,
            usage_date=date.today(),
        )
        self.assertEqual(record.specific_part, "3-1-7-702")
        self.assertEqual(record.value, 12345)

    def test_unique_together_constraint(self):
        """同一 specific_part + energy_mode + usage_date 不能重复"""
        today = date.today()
        PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            value=100,
            usage_date=today,
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            PLCData.objects.create(
                specific_part="3-1-7-702",
                building="3",
                unit="1",
                room_number="702",
                energy_mode="制冷",
                value=200,
                usage_date=today,
            )

    def test_str_representation(self):
        """__str__ 包含 specific_part 和 energy_mode"""
        record = PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制热",
            value=500,
            usage_date=date.today(),
        )
        self.assertIn("3-1-7-702", str(record))
        self.assertIn("制热", str(record))


class UsageQuantityDailyModelTest(TestCase):
    """UsageQuantityDaily 模型测试"""

    def test_create_record(self):
        record = make_daily_record()
        self.assertEqual(record.usage_quantity, 100)

    def test_str_representation(self):
        record = make_daily_record(specific_part="3-1-7-702", energy_mode="制冷")
        self.assertIn("3-1-7-702", str(record))
        self.assertIn("制冷", str(record))


class UsageQuantityMonthlyModelTest(TestCase):
    """UsageQuantityMonthly 模型测试"""

    def test_create_record(self):
        record = make_monthly_record()
        self.assertEqual(record.usage_month, "2025-01")
        self.assertEqual(record.usage_quantity, 100)

    def test_str_representation(self):
        record = make_monthly_record(specific_part="3-1-7-702", energy_mode="制冷", usage_month="2025-01")
        self.assertIn("3-1-7-702", str(record))
        self.assertIn("2025-01", str(record))


class PLCConnectionStatusModelTest(TestCase):
    """PLCConnectionStatus 模型测试"""

    def test_create_online_status(self):
        obj = PLCConnectionStatus.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            connection_status="online",
        )
        self.assertEqual(obj.connection_status, "online")

    def test_default_status_is_offline(self):
        obj = PLCConnectionStatus.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
        )
        self.assertEqual(obj.connection_status, "offline")

    def test_specific_part_unique(self):
        """specific_part 唯一约束"""
        PLCConnectionStatus.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
        )
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            PLCConnectionStatus.objects.create(
                specific_part="3-1-7-702",
                building="3",
                unit="1",
                room_number="702",
            )


class PLCStatusChangeHistoryModelTest(TestCase):
    """PLCStatusChangeHistory 模型测试"""

    def test_create_history_record(self):
        record = PLCStatusChangeHistory.objects.create(
            specific_part="3-1-7-702",
            status="online",
            building="3",
            unit="1",
            room_number="702",
        )
        self.assertEqual(record.status, "online")
        self.assertEqual(record.specific_part, "3-1-7-702")


class SpecificPartInfoModelTest(TestCase):
    """SpecificPartInfo 模型测试"""

    def setUp(self):
        SpecificPartInfo.objects.create(
            screenMAC="00:11:22:33:44:55",
            specific_part="1-1-2-201",
        )

    def test_creation(self):
        obj = SpecificPartInfo.objects.get(screenMAC="00:11:22:33:44:55")
        self.assertEqual(obj.specific_part, "1-1-2-201")

    def test_screenmac_unique(self):
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            SpecificPartInfo.objects.create(
                screenMAC="00:11:22:33:44:55",
                specific_part="1-1-2-202",
            )

    def test_str_representation(self):
        obj = SpecificPartInfo.objects.get(screenMAC="00:11:22:33:44:55")
        self.assertIn("00:11:22:33:44:55", str(obj))
        self.assertIn("1-1-2-201", str(obj))


# ===========================================================================
# 二、DailyUsageCalculator 测试
# ===========================================================================

class ParseSpecificPartTest(TestCase):
    """DailyUsageCalculator.parse_specific_part 解析逻辑测试"""

    def test_three_part_format(self):
        """楼栋-单元-房号 格式"""
        building, unit, room_number = DailyUsageCalculator.parse_specific_part("3-1-702")
        self.assertEqual(building, "3")
        self.assertEqual(unit, "1")
        self.assertEqual(room_number, "702")

    def test_four_part_format(self):
        """楼栋-单元-楼层-房号 格式"""
        building, unit, room_number = DailyUsageCalculator.parse_specific_part("3-1-7-702")
        self.assertEqual(building, "3")
        self.assertEqual(unit, "1")
        self.assertEqual(room_number, "702")

    def test_invalid_format_returns_defaults(self):
        """无法解析的格式：room_number 设为原始字符串"""
        building, unit, room_number = DailyUsageCalculator.parse_specific_part("invalid")
        self.assertEqual(building, "")
        self.assertEqual(unit, "")
        self.assertEqual(room_number, "invalid")

    def test_empty_string(self):
        """空字符串不抛异常"""
        building, unit, room_number = DailyUsageCalculator.parse_specific_part("")
        self.assertEqual(building, "")


class DailyUsageCalculatorTest(TestCase):
    """DailyUsageCalculator.calculate_daily_usage 集成测试（使用内存数据库）"""

    def setUp(self):
        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)

    def _make_plc(self, specific_part, energy_mode, value, usage_date=None):
        if usage_date is None:
            usage_date = self.today
        PLCData.objects.create(
            specific_part=specific_part,
            building=specific_part.split("-")[0],
            unit=specific_part.split("-")[1],
            room_number=specific_part.split("-")[3] if len(specific_part.split("-")) == 4 else specific_part.split("-")[2],
            energy_mode=energy_mode,
            value=value,
            usage_date=usage_date,
        )

    def test_creates_new_daily_record_when_none_exists(self):
        """当日无已有记录时，新建 UsageQuantityDaily"""
        self._make_plc("3-1-7-702", "制冷", 5000)
        result = DailyUsageCalculator.calculate_daily_usage(self.today)
        self.assertEqual(result["created_count"], 1)
        record = UsageQuantityDaily.objects.get(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=self.today,
        )
        # 首次创建时 initial = final = value，usage_quantity = 0
        self.assertEqual(record.initial_energy, 5000)
        self.assertEqual(record.final_energy, 5000)
        self.assertEqual(record.usage_quantity, 0)

    def test_updates_existing_daily_record(self):
        """当日已有记录时，更新 final_energy 和 usage_quantity"""
        # 先创建当日记录
        UsageQuantityDaily.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            initial_energy=4000,
            final_energy=4000,
            usage_quantity=0,
            time_period=self.today,
        )
        # PLC 读数更新为 4500
        self._make_plc("3-1-7-702", "制冷", 4500)
        result = DailyUsageCalculator.calculate_daily_usage(self.today)
        self.assertEqual(result["updated_count"], 1)
        record = UsageQuantityDaily.objects.get(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=self.today,
        )
        self.assertEqual(record.final_energy, 4500)
        self.assertEqual(record.usage_quantity, 500)

    def test_creates_next_day_record(self):
        """计算时应同步创建次日的 initial_energy 预留记录"""
        self._make_plc("3-1-7-702", "制冷", 5000)
        DailyUsageCalculator.calculate_daily_usage(self.today)
        tomorrow = self.today + timedelta(days=1)
        next_day_record = UsageQuantityDaily.objects.filter(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=tomorrow,
        ).first()
        self.assertIsNotNone(next_day_record)
        self.assertEqual(next_day_record.initial_energy, 5000)
        self.assertIsNone(next_day_record.final_energy)

    def test_fills_previous_day_incomplete_records(self):
        """补全前一天 final_energy 为 None 的记录"""
        UsageQuantityDaily.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            initial_energy=3000,
            final_energy=None,
            usage_quantity=None,
            time_period=self.yesterday,
        )
        self._make_plc("3-1-7-702", "制冷", 3500)
        DailyUsageCalculator.calculate_daily_usage(self.today)
        yesterday_record = UsageQuantityDaily.objects.get(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=self.yesterday,
        )
        self.assertEqual(yesterday_record.final_energy, 3000)
        self.assertEqual(yesterday_record.usage_quantity, 0)

    def test_no_plc_data_returns_zero_processed(self):
        """目标日期无 PLCData 时返回 processed_count=0"""
        result = DailyUsageCalculator.calculate_daily_usage(self.today)
        self.assertEqual(result["processed_count"], 0)
        self.assertEqual(result["created_count"], 0)

    def test_multiple_rooms_and_modes(self):
        """多个房间、多种能源模式均被处理"""
        self._make_plc("3-1-7-702", "制冷", 1000)
        self._make_plc("3-1-7-702", "制热", 2000)
        self._make_plc("3-1-7-801", "制冷", 3000)
        result = DailyUsageCalculator.calculate_daily_usage(self.today)
        self.assertEqual(result["created_count"], 3)

    def test_accepts_date_object(self):
        """可以直接传入 date 对象（不是 datetime）"""
        self._make_plc("3-1-7-702", "制冷", 100)
        result = DailyUsageCalculator.calculate_daily_usage(self.today)
        self.assertIn("processed_count", result)


# ===========================================================================
# 三、MonthlyUsageCalculator 测试
# ===========================================================================

class MonthlyUsageCalculatorTest(TestCase):
    """MonthlyUsageCalculator.calculate_monthly_usage 测试"""

    def _make_daily(self, specific_part, energy_mode, time_period, initial, final, quantity):
        parts = specific_part.split("-")
        building = parts[0]
        unit = parts[1]
        room_number = parts[3] if len(parts) == 4 else parts[2]
        UsageQuantityDaily.objects.create(
            specific_part=specific_part,
            building=building,
            unit=unit,
            room_number=room_number,
            energy_mode=energy_mode,
            initial_energy=initial,
            final_energy=final,
            usage_quantity=quantity,
            time_period=time_period,
        )

    def test_basic_monthly_aggregation(self):
        """基本月度聚合：月用量 = max(final) - min(initial)"""
        self._make_daily("3-1-7-702", "制冷", date(2025, 1, 1), 1000, 1050, 50)
        self._make_daily("3-1-7-702", "制冷", date(2025, 1, 15), 1050, 1100, 50)
        self._make_daily("3-1-7-702", "制冷", date(2025, 1, 31), 1100, 1200, 100)

        result = MonthlyUsageCalculator.calculate_monthly_usage(date(2025, 1, 1))
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["created"], 1)

        monthly = UsageQuantityMonthly.objects.get(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-01",
        )
        self.assertEqual(monthly.initial_energy, 1000)
        self.assertEqual(monthly.final_energy, 1200)
        self.assertEqual(monthly.usage_quantity, 200)

    def test_updates_existing_monthly_record(self):
        """当月度记录已存在时应更新而非重复创建"""
        self._make_daily("3-1-7-702", "制冷", date(2025, 1, 1), 1000, 1100, 100)
        MonthlyUsageCalculator.calculate_monthly_usage(date(2025, 1, 1))

        # 再次运行（模拟重新触发）
        self._make_daily("3-1-7-702", "制冷", date(2025, 1, 31), 1100, 1300, 200)
        result = MonthlyUsageCalculator.calculate_monthly_usage(date(2025, 1, 1))
        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["created"], 0)
        monthly = UsageQuantityMonthly.objects.get(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-01",
        )
        self.assertEqual(monthly.usage_quantity, 300)

    def test_skips_when_no_daily_data(self):
        """目标月份没有日用量数据时返回 skipped=True"""
        result = MonthlyUsageCalculator.calculate_monthly_usage(date(2025, 6, 1))
        self.assertTrue(result["skipped"])
        self.assertEqual(result["processed"], 0)

    def test_clamps_negative_usage_to_zero(self):
        """当 final_energy < initial_energy（数据异常）时 usage_quantity 设为 0"""
        self._make_daily("3-1-7-702", "制冷", date(2025, 1, 1), 5000, 3000, 0)
        # 手动制造一个 final < initial 的情况（正常 daily 数据 initial <= final，
        # 但跨天聚合时 min(initial) 可能大于 max(final)——此处直接构造）
        # 通过直接覆盖 initial_energy 使其大于 final_energy
        UsageQuantityDaily.objects.filter(
            specific_part="3-1-7-702",
            energy_mode="制冷",
        ).update(initial_energy=9999, final_energy=100)

        result = MonthlyUsageCalculator.calculate_monthly_usage(date(2025, 1, 1))
        monthly = UsageQuantityMonthly.objects.get(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-01",
        )
        self.assertEqual(monthly.usage_quantity, 0)

    def test_invalid_date_type_returns_error(self):
        """传入非 date 类型参数时返回 error 字段"""
        result = MonthlyUsageCalculator.calculate_monthly_usage("2025-01-01")
        self.assertIn("error", result)


# ===========================================================================
# 四、plc_data_cleaner 测试
# ===========================================================================

class PLCDataCleanerTest(TestCase):
    """clean_old_plc_data 函数测试

    注意：clean_old_plc_data 根据 PLCData.created_at（auto_now_add）过滤，
    而 created_at 由数据库在 INSERT 时设置为当前时间，无法直接在 create() 中覆盖。
    测试策略：
    - 使用 days=0 触发"立即过期"（cutoff = now，all records < now 会被删）
    - 或通过 patch datetime.now 模拟时间前移
    """

    def _create_plc(self, energy_mode, specific_part="3-1-7-702"):
        return PLCData.objects.create(
            specific_part=specific_part,
            building=specific_part.split("-")[0],
            unit=specific_part.split("-")[1],
            room_number=specific_part.split("-")[3] if len(specific_part.split("-")) == 4 else specific_part.split("-")[2],
            energy_mode=energy_mode,
            value=100,
            usage_date=date.today(),
        )

    def test_cleans_all_when_days_zero(self):
        """days=0 时 cutoff=now，所有已存在记录的 created_at 均在 now 之前，应全部删除"""
        self._create_plc("制冷")
        self._create_plc("制热")
        # patch datetime.now() 返回1秒后的时间，避免与 auto_now_add 的计时竞争
        future_now = datetime.now() + timedelta(seconds=1)
        with patch("api.plc_data_cleaner.datetime") as mock_dt:
            mock_dt.now.return_value = future_now
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
            result = clean_old_plc_data(days=0)
        self.assertEqual(PLCData.objects.count(), 0)
        self.assertGreater(result["deleted_count"], 0)
        self.assertIn("成功删除", result["message"])

    def test_no_records_to_delete_with_large_days(self):
        """days=3650 时 cutoff 在 10 年前，今天的记录不应被删除"""
        self._create_plc("制冷")
        result = clean_old_plc_data(days=3650)
        self.assertEqual(result["deleted_count"], 0)
        self.assertIn("没有找到", result["message"])
        self.assertEqual(PLCData.objects.count(), 1)

    def test_no_records_at_all(self):
        """数据库中无记录时返回 deleted_count=0"""
        result = clean_old_plc_data(days=7)
        self.assertEqual(result["deleted_count"], 0)

    def test_deletes_old_records_via_mock(self):
        """通过 mock datetime.now 模拟时间前移，验证 7 天前的记录被删除"""
        self._create_plc("制冷", specific_part="3-1-7-702")
        self._create_plc("制热", specific_part="3-1-7-801")
        # 将"当前时间"前移到 10 天后，使已有记录看起来是 10 天前的
        future_now = datetime.now() + timedelta(days=10)
        with patch("api.plc_data_cleaner.datetime") as mock_dt:
            mock_dt.now.return_value = future_now
            mock_dt.side_effect = lambda *args, **kw: datetime(*args, **kw)
            result = clean_old_plc_data(days=7)
        self.assertGreater(result["deleted_count"], 0)
        self.assertEqual(PLCData.objects.count(), 0)


# ===========================================================================
# 五、MQTT Handlers 测试
# ===========================================================================

class PLCDataHandlerTest(TestCase):
    """PLCDataHandler.batch_save_plc_data 测试"""

    def setUp(self):
        self.handler = PLCDataHandler()
        self.today = date.today()

    def test_saves_valid_data_point(self):
        """有效数据点应写入 PLCData 表"""
        batch = [{
            "specific_part": "3-1-7-702",
            "energy_mode": "制冷",
            "plc_ip": "192.168.1.1",
            "param_value": 5000,
            "success": True,
            "message": "ok",
            "timestamp": self.today.strftime("%Y-%m-%d") + " 10:00:00",
        }]
        self.handler.batch_save_plc_data(batch)
        self.assertEqual(PLCData.objects.filter(specific_part="3-1-7-702").count(), 1)

    def test_skips_failed_data_point(self):
        """success=False 的数据点不写入数据库"""
        batch = [{
            "specific_part": "3-1-7-702",
            "energy_mode": "制冷",
            "plc_ip": "192.168.1.1",
            "param_value": None,
            "success": False,
            "message": "连接失败",
            "timestamp": self.today.strftime("%Y-%m-%d") + " 10:00:00",
        }]
        self.handler.batch_save_plc_data(batch)
        self.assertEqual(PLCData.objects.count(), 0)

    def test_upsert_updates_value_for_same_key(self):
        """相同 (specific_part, energy_mode, usage_date) 的数据点更新而非重复创建"""
        batch_first = [{
            "specific_part": "3-1-7-702",
            "energy_mode": "制冷",
            "plc_ip": "192.168.1.1",
            "param_value": 1000,
            "success": True,
            "message": "ok",
            "timestamp": self.today.strftime("%Y-%m-%d") + " 08:00:00",
        }]
        self.handler.batch_save_plc_data(batch_first)
        self.assertEqual(PLCData.objects.filter(specific_part="3-1-7-702").count(), 1)

        batch_second = [{
            "specific_part": "3-1-7-702",
            "energy_mode": "制冷",
            "plc_ip": "192.168.1.1",
            "param_value": 1500,
            "success": True,
            "message": "ok",
            "timestamp": self.today.strftime("%Y-%m-%d") + " 12:00:00",
        }]
        self.handler.batch_save_plc_data(batch_second)
        self.assertEqual(PLCData.objects.filter(specific_part="3-1-7-702").count(), 1)
        self.assertEqual(PLCData.objects.get(specific_part="3-1-7-702").value, 1500)

    def test_missing_specific_part_is_skipped(self):
        """缺少 specific_part 字段的数据点跳过"""
        batch = [{
            "energy_mode": "制冷",
            "param_value": 100,
            "success": True,
            "message": "ok",
        }]
        self.handler.batch_save_plc_data(batch)
        self.assertEqual(PLCData.objects.count(), 0)

    def test_parses_building_info_from_four_part_specific_part(self):
        """4 段 specific_part 正确解析 building/unit/room_number"""
        batch = [{
            "specific_part": "5-2-6-601",
            "energy_mode": "制热",
            "plc_ip": "192.168.1.2",
            "param_value": 300,
            "success": True,
            "message": "ok",
            "timestamp": self.today.strftime("%Y-%m-%d") + " 09:00:00",
        }]
        self.handler.batch_save_plc_data(batch)
        record = PLCData.objects.get(specific_part="5-2-6-601")
        self.assertEqual(record.building, "5")
        self.assertEqual(record.unit, "2")
        self.assertEqual(record.room_number, "601")

    def test_handle_improved_format(self):
        """处理 improved_data_collection_manager 格式的消息"""
        payload = {
            "3-1-7-702": {
                "PLC IP地址": "192.168.1.1",
                "data": {
                    "total_cold_quantity": {
                        "success": True,
                        "value": 9999,
                        "message": "ok",
                        "timestamp": self.today.strftime("%Y-%m-%d") + " 10:00:00",
                    },
                    "total_hot_quantity": {
                        "success": True,
                        "value": 8888,
                        "message": "ok",
                        "timestamp": self.today.strftime("%Y-%m-%d") + " 10:00:00",
                    }
                }
            }
        }
        topic = "/datacollection/plc/to/collector/3#"
        self.handler.handle(topic, payload)
        # total_cold_quantity -> 制冷，total_hot_quantity -> 制热
        self.assertEqual(PLCData.objects.filter(specific_part="3-1-7-702").count(), 2)
        cold = PLCData.objects.get(specific_part="3-1-7-702", energy_mode="制冷")
        self.assertEqual(cold.value, 9999)


class ConnectionStatusHandlerTest(TestCase):
    """ConnectionStatusHandler 测试"""

    def setUp(self):
        self.handler = ConnectionStatusHandler()

    def test_marks_online_when_any_success(self):
        """有成功数据项时标记为 online"""
        payload = {
            "3-1-7-702": {
                "data": {
                    "total_cold_quantity": {"success": True, "value": 100},
                    "total_hot_quantity": {"success": False, "value": None},
                }
            }
        }
        self.handler.handle("/topic", payload)
        status = PLCConnectionStatus.objects.get(specific_part="3-1-7-702")
        self.assertEqual(status.connection_status, "online")

    def test_marks_offline_when_all_failed(self):
        """所有数据项失败时标记为 offline"""
        payload = {
            "3-1-7-702": {
                "data": {
                    "total_cold_quantity": {"success": False, "value": None},
                    "total_hot_quantity": {"success": False, "value": None},
                }
            }
        }
        self.handler.handle("/topic", payload)
        status = PLCConnectionStatus.objects.get(specific_part="3-1-7-702")
        self.assertEqual(status.connection_status, "offline")

    def test_creates_history_on_status_change(self):
        """状态变化时写入 PLCStatusChangeHistory"""
        # 先标记为 online
        PLCConnectionStatus.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            connection_status="online",
        )
        # 然后标记为 offline
        payload = {
            "3-1-7-702": {
                "data": {
                    "total_cold_quantity": {"success": False, "value": None},
                }
            }
        }
        self.handler.handle("/topic", payload)
        history = PLCStatusChangeHistory.objects.filter(
            specific_part="3-1-7-702",
            status="offline",
        )
        self.assertTrue(history.exists())

    def test_no_history_when_status_unchanged(self):
        """状态未变化时不重复写入历史"""
        PLCConnectionStatus.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            connection_status="offline",
        )
        payload = {
            "3-1-7-702": {
                "data": {
                    "total_cold_quantity": {"success": False, "value": None},
                }
            }
        }
        self.handler.handle("/topic", payload)
        self.handler.handle("/topic", payload)
        # 第一次（创建记录后）状态已经是 offline，两次发送都不应产生新历史
        count = PLCStatusChangeHistory.objects.filter(
            specific_part="3-1-7-702",
            status="offline",
        ).count()
        # 初始创建时 get_or_create created=False（记录已存在），
        # 再次调用时 old_status==status，不写历史
        self.assertEqual(count, 0)

    def test_parse_four_part_specific_part(self):
        """4 段格式 specific_part 解析正确"""
        building, unit, room_number = self.handler._parse_building_info("3-1-7-702")
        self.assertEqual(building, "3")
        self.assertEqual(unit, "1")
        self.assertEqual(room_number, "702")

    def test_parse_three_part_specific_part(self):
        """3 段格式 specific_part 解析正确"""
        building, unit, room_number = self.handler._parse_building_info("3-1-702")
        self.assertEqual(building, "3")
        self.assertEqual(unit, "1")
        self.assertEqual(room_number, "702")


# ===========================================================================
# 六、REST API 视图测试
# ===========================================================================

class HealthCheckAPITest(TestCase):
    """健康检查接口测试"""

    def test_health_check_returns_200(self):
        client = Client()
        response = client.get(reverse("health-check"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


class AuthAPITest(TestCase):
    """认证相关 API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = make_user(username="authuser", password="StrongPass!1")

    def test_login_success(self):
        response = self.client.post(
            reverse("user-login"),
            {"username": "authuser", "password": "StrongPass!1"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["username"], "authuser")

    def test_login_wrong_password(self):
        response = self.client.post(
            reverse("user-login"),
            {"username": "authuser", "password": "WrongPass"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_login_missing_fields(self):
        response = self.client.post(
            reverse("user-login"),
            {"username": "authuser"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_logout_success(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        response = self.client.post(reverse("user-logout"))
        self.assertEqual(response.status_code, 200)
        # Token 应被删除
        self.assertFalse(Token.objects.filter(user=self.user).exists())

    def test_logout_requires_auth(self):
        response = self.client.post(reverse("user-logout"))
        self.assertEqual(response.status_code, 401)

    def test_get_current_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        response = self.client.get(reverse("get-current-user"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["username"], "authuser")

    def test_get_current_user_unauthenticated(self):
        response = self.client.get(reverse("get-current-user"))
        self.assertEqual(response.status_code, 401)


class ChangePasswordAPITest(TestCase):
    """修改密码 API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = make_user(username="pwduser", password="OldPass123!")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def test_change_password_success(self):
        response = self.client.post(
            reverse("change-password"),
            {"current_password": "OldPass123!", "new_password": "NewPass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

    def test_change_password_wrong_current(self):
        response = self.client.post(
            reverse("change-password"),
            {"current_password": "WrongOld!", "new_password": "NewPass456!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

    def test_change_password_missing_fields(self):
        response = self.client.post(
            reverse("change-password"),
            {"current_password": "OldPass123!"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class UserManagementAPITest(TestCase):
    """用户管理 API 测试（仅管理员）"""

    def setUp(self):
        self.client = APIClient()
        self.admin, self.admin_token = make_user(username="admin1", role="admin", password="AdminPass1!")
        self.regular, self.regular_token = make_user(username="regular1", role="user", password="UserPass1!")

    def test_admin_can_list_users(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        response = self.client.get(reverse("user-list"))
        self.assertEqual(response.status_code, 200)

    def test_regular_cannot_list_users(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.regular_token.key}")
        response = self.client.get(reverse("user-list"))
        self.assertEqual(response.status_code, 403)

    def test_admin_create_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        response = self.client.post(
            reverse("admin-user-create"),
            {"username": "newuser", "password": "NewUser123!", "role": "user"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(CustomUser.objects.filter(username="newuser").exists())

    def test_admin_create_duplicate_username(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        # 先创建一次
        self.client.post(
            reverse("admin-user-create"),
            {"username": "dupeuser", "password": "Dupepass1!", "role": "user"},
            format="json",
        )
        # 再创建同名用户
        response = self.client.post(
            reverse("admin-user-create"),
            {"username": "dupeuser", "password": "Dupepass2!", "role": "user"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("已存在", response.data.get("error", ""))

    def test_regular_cannot_create_user(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.regular_token.key}")
        response = self.client.post(
            reverse("admin-user-create"),
            {"username": "anotheruser", "password": "Pass123!", "role": "user"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)


class UsageQuantityAPITest(TestCase):
    """日用量查询 API 测试"""

    def setUp(self):
        self.client = Client()
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=date(2025, 1, 10),
            initial_energy=1000,
            final_energy=1100,
            usage_quantity=100,
        )
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            time_period=date(2025, 1, 10),
            initial_energy=2000,
            final_energy=2200,
            usage_quantity=200,
        )
        make_daily_record(
            specific_part="3-1-7-801",
            energy_mode="制冷",
            time_period=date(2025, 2, 5),
            initial_energy=500,
            final_energy=600,
            usage_quantity=100,
        )

    def test_get_all_records_no_filter(self):
        response = self.client.get(reverse("get-usage-quantity"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 3)

    def test_filter_by_specific_part(self):
        response = self.client.get(
            reverse("get-usage-quantity"),
            {"specific_part": "3-1-7-702"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 2)
        for item in data["data"]:
            self.assertEqual(item["specific_part"], "3-1-7-702")

    def test_filter_by_energy_mode(self):
        response = self.client.get(
            reverse("get-usage-quantity"),
            {"energy_mode": "制冷"},
        )
        data = response.json()
        self.assertEqual(data["total"], 2)
        for item in data["data"]:
            self.assertEqual(item["energy_mode"], "制冷")

    def test_filter_by_date_range(self):
        response = self.client.get(
            reverse("get-usage-quantity"),
            {"start_time": "2025-01-01", "end_time": "2025-01-31"},
        )
        data = response.json()
        self.assertEqual(data["total"], 2)

    def test_pagination(self):
        response = self.client.get(
            reverse("get-usage-quantity"),
            {"page": 1, "page_size": 2},
        )
        data = response.json()
        self.assertEqual(len(data["data"]), 2)
        self.assertEqual(data["total"], 3)

    def test_sorted_by_time_period(self):
        response = self.client.get(reverse("get-usage-quantity"))
        data = response.json()["data"]
        periods = [item["time_period"] for item in data]
        self.assertEqual(periods, sorted(periods))


class UsageQuantitySpecificTimePeriodAPITest(TestCase):
    """特定时间段汇总查询 API 测试"""

    def setUp(self):
        self.client = Client()
        # 同一房间一月份三条日记录
        for day, initial, final in [(1, 1000, 1050), (15, 1050, 1080), (31, 1080, 1200)]:
            make_daily_record(
                specific_part="3-1-7-702",
                energy_mode="制冷",
                time_period=date(2025, 1, day),
                initial_energy=initial,
                final_energy=final,
                usage_quantity=final - initial,
            )

    def test_aggregation_returns_min_initial_max_final(self):
        response = self.client.get(
            reverse("get-usage-quantity-specific-time-period"),
            {
                "specific_part": "3-1-7-702",
                "energy_mode": "制冷",
                "start_time": "2025-01-01",
                "end_time": "2025-01-31",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        item = data[0]
        self.assertEqual(item["initial_energy"], 1000)
        self.assertEqual(item["final_energy"], 1200)
        self.assertEqual(item["usage_quantity"], 200)

    def test_empty_result_when_no_data(self):
        response = self.client.get(
            reverse("get-usage-quantity-specific-time-period"),
            {
                "specific_part": "9-9-9-999",
                "start_time": "2025-01-01",
                "end_time": "2025-01-31",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)

    def test_energy_mode_filter_isolation(self):
        """供能模式过滤应严格隔离，不返回其他模式数据"""
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            time_period=date(2025, 1, 1),
            initial_energy=3000,
            final_energy=3500,
            usage_quantity=500,
        )
        response = self.client.get(
            reverse("get-usage-quantity-specific-time-period"),
            {
                "specific_part": "3-1-7-702",
                "energy_mode": "制冷",
                "start_time": "2025-01-01",
                "end_time": "2025-01-31",
            },
        )
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["energy_mode"], "制冷")


class UsageQuantityMonthlyAPITest(TestCase):
    """月度用量查询 API 测试"""

    def setUp(self):
        self.client = Client()
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-01",
            initial_energy=1000,
            final_energy=1200,
            usage_quantity=200,
        )
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            usage_month="2025-02",
            initial_energy=2000,
            final_energy=2300,
            usage_quantity=300,
        )
        make_monthly_record(
            specific_part="3-1-7-801",
            energy_mode="制冷",
            usage_month="2025-01",
            initial_energy=500,
            final_energy=600,
            usage_quantity=100,
        )

    def test_get_all_records(self):
        response = self.client.get(reverse("get-usage-quantity-monthly"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 3)

    def test_filter_by_specific_part(self):
        response = self.client.get(
            reverse("get-usage-quantity-monthly"),
            {"specific_part": "3-1-7-702"},
        )
        self.assertEqual(response.json()["total"], 2)

    def test_filter_by_energy_mode(self):
        response = self.client.get(
            reverse("get-usage-quantity-monthly"),
            {"energy_mode": "制冷"},
        )
        data = response.json()
        self.assertEqual(data["total"], 2)

    def test_filter_by_usage_month(self):
        response = self.client.get(
            reverse("get-usage-quantity-monthly"),
            {"usage_month": "2025-01"},
        )
        self.assertEqual(response.json()["total"], 2)

    def test_filter_by_month_range(self):
        response = self.client.get(
            reverse("get-usage-quantity-monthly"),
            {"start_month": "2025-02", "end_month": "2025-02"},
        )
        self.assertEqual(response.json()["total"], 1)

    def test_pagination(self):
        response = self.client.get(
            reverse("get-usage-quantity-monthly"),
            {"page": 1, "page_size": 2},
        )
        data = response.json()
        self.assertEqual(len(data["data"]), 2)
        self.assertEqual(data["total"], 3)


class PLCConnectionStatusAPITest(TestCase):
    """PLC 连接状态 API 测试"""

    def setUp(self):
        self.client = Client()
        PLCConnectionStatus.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            connection_status="online",
            last_online_time=datetime.now(),
        )
        PLCConnectionStatus.objects.create(
            specific_part="3-1-7-801",
            building="3",
            unit="1",
            room_number="801",
            connection_status="offline",
        )
        PLCConnectionStatus.objects.create(
            specific_part="5-2-6-601",
            building="5",
            unit="2",
            room_number="601",
            connection_status="online",
        )

    def test_list_all_devices(self):
        response = self.client.get(reverse("get-plc-connection-status"))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total"], 3)

    def test_statistics_included(self):
        response = self.client.get(reverse("get-plc-connection-status"))
        stats = response.json()["statistics"]
        self.assertEqual(stats["online_count"], 2)
        self.assertEqual(stats["offline_count"], 1)
        self.assertEqual(stats["total_devices"], 3)
        self.assertAlmostEqual(stats["online_rate"], 66.67, places=1)

    def test_filter_by_connection_status(self):
        response = self.client.get(
            reverse("get-plc-connection-status"),
            {"connection_status": "offline"},
        )
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["data"][0]["specific_part"], "3-1-7-801")

    def test_filter_by_building(self):
        response = self.client.get(
            reverse("get-plc-connection-status"),
            {"building": "5"},
        )
        self.assertEqual(response.json()["total"], 1)

    def test_detail_returns_device(self):
        response = self.client.get(
            reverse("get-plc-connection-status-detail", kwargs={"specific_part": "3-1-7-702"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["specific_part"], "3-1-7-702")

    def test_detail_not_found(self):
        response = self.client.get(
            reverse("get-plc-connection-status-detail", kwargs={"specific_part": "99-9-9-999"})
        )
        self.assertEqual(response.status_code, 404)

    def test_status_history_empty(self):
        response = self.client.get(
            reverse("get-plc-status-change-history", kwargs={"specific_part": "3-1-7-702"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 0)

    def test_status_history_ordered_descending(self):
        PLCStatusChangeHistory.objects.create(
            specific_part="3-1-7-702",
            status="online",
            building="3",
            unit="1",
            room_number="702",
        )
        PLCStatusChangeHistory.objects.create(
            specific_part="3-1-7-702",
            status="offline",
            building="3",
            unit="1",
            room_number="702",
        )
        response = self.client.get(
            reverse("get-plc-status-change-history", kwargs={"specific_part": "3-1-7-702"})
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data), 2)
        # 第一条应为最新的（change_time 倒序）
        self.assertEqual(data[0]["status"], "offline")


class BillingAPITest(TestCase):
    """历史用能账单 API 测试"""

    def setUp(self):
        self.client = Client()
        SpecificPartInfo.objects.create(
            screenMAC="AA:BB:CC:DD:EE:FF",
            specific_part="3-1-7-702",
        )
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-01",
            initial_energy=1000,
            final_energy=1100,
            usage_quantity=100,
        )
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            usage_month="2025-02",
            initial_energy=2000,
            final_energy=2150,
            usage_quantity=150,
        )

    def _post(self, data, screenmac="AA:BB:CC:DD:EE:FF"):
        kwargs = {"content_type": "application/json"}
        if screenmac:
            kwargs["HTTP_SCREENMAC"] = screenmac
        return self.client.post(
            reverse("get-bill-list"),
            data=data,
            **kwargs,
        )

    def test_success_returns_200_with_data(self):
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-02"})
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["code"], 200)
        self.assertEqual(len(body["data"]), 2)

    def test_missing_screenmac_returns_400(self):
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-02"}),
            screenmac=None,
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], 400)

    def test_unknown_screenmac_returns_404(self):
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-02"}),
            screenmac="99:99:99:99:99:99",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["code"], 404)

    def test_energy_type_filter_cooling(self):
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-02", "energyType": "制冷"})
        )
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["modeName"], "制冷")

    def test_energy_type_filter_heating(self):
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-02", "energyType": "制热"})
        )
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["modeName"], "制热")

    def test_bill_amount_calculation(self):
        """billAmount = usage_quantity * 0.28"""
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-01", "energyType": "制冷"})
        )
        body = response.json()
        item = body["data"][0]
        self.assertEqual(item["usageAmount"], "100")
        self.assertEqual(item["billAmount"], "28.00")
        self.assertEqual(item["basicPrice"], "0.28")

    def test_billing_cycle_format(self):
        """billingCycle 格式应为 YYYY年MM月"""
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-01"})
        )
        item = response.json()["data"][0]
        self.assertEqual(item["billingCycle"], "2025年01月")

    def test_billing_date_is_last_day_of_month(self):
        """billingDate 应为月末日期"""
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-01"})
        )
        item = response.json()["data"][0]
        self.assertEqual(item["billingDate"], "2025-01-31")

    def test_date_format_yyyymm_conversion(self):
        """startDate/endDate 支持 YYYYMM（6 位）格式"""
        import json
        response = self._post(
            json.dumps({"startDate": "202501", "endDate": "202501"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.json()["data"]), 0)

    def test_family_name_format(self):
        """familyName 应为 X栋X单元XXX"""
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-01"})
        )
        item = response.json()["data"][0]
        # specific_part="3-1-7-702": building=3, unit=1, room=702
        self.assertEqual(item["familyName"], "3栋1单元702")

    def test_charge_items_format(self):
        """chargeItems 应为 制冷费 或 制热费"""
        import json
        response = self._post(
            json.dumps({"startDate": "2025-01", "endDate": "2025-02"})
        )
        for item in response.json()["data"]:
            self.assertIn(item["chargeItems"], ["制冷费", "制热费"])

    def test_no_data_returns_empty_list(self):
        """时间范围内无数据时 data 为空列表，code 仍为 200"""
        import json
        response = self._post(
            json.dumps({"startDate": "2020-01", "endDate": "2020-12"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["code"], 200)
        self.assertEqual(response.json()["data"], [])


# ===========================================================================
# 七、用户注册 API 测试（补充 US-004 / AC-004-*）
# ===========================================================================

class UserRegisterAPITest(TestCase):
    """用户注册 API 测试 — US-004"""

    def setUp(self):
        self.client = APIClient()

    def test_register_success_returns_201_with_token(self):
        """AC-004-01: 正常注册返回 201，包含 token，role=user"""
        response = self.client.post(
            reverse("user-register"),
            {
                "username": "newreg",
                "password": "RegPass123!",
                "password2": "RegPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["role"], "user")
        self.assertTrue(CustomUser.objects.filter(username="newreg").exists())

    def test_register_password_mismatch_returns_400(self):
        """AC-004-02: password 与 password2 不一致时返回 400"""
        response = self.client.post(
            reverse("user-register"),
            {
                "username": "mismatch",
                "password": "PassA123!",
                "password2": "PassB999!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_register_missing_password_returns_400(self):
        """注册时缺少必填字段返回 400"""
        response = self.client.post(
            reverse("user-register"),
            {"username": "nopass"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_register_duplicate_username_returns_400(self):
        """注册已存在的用户名返回 400"""
        CustomUser.objects.create_user(username="existing", password="pwd")
        response = self.client.post(
            reverse("user-register"),
            {
                "username": "existing",
                "password": "NewPass123!",
                "password2": "NewPass123!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)


# ===========================================================================
# 八、看板 Dashboard API 测试
# ===========================================================================

class DashboardTotalEnergyAPITest(TestCase):
    """看板 API 1：总电量查询测试"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = make_user(username="dash_total_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        today = date.today()
        # 创建本年度制冷数据：usage_quantity=200
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=date(today.year, 1, 15),
            usage_quantity=200,
        )
        # 创建本年度制热数据：usage_quantity=150
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            time_period=date(today.year, 1, 16),
            usage_quantity=150,
        )

    def test_default_returns_current_year(self):
        """未传日期参数时默认返回当年汇总"""
        response = self.client.get(reverse("dashboard-total-energy"))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total_kwh"], 350)
        self.assertEqual(data["cooling_kwh"], 200)
        self.assertEqual(data["heating_kwh"], 150)

    def test_custom_date_range(self):
        """指定日期范围时只统计范围内数据"""
        today = date.today()
        response = self.client.get(
            reverse("dashboard-total-energy"),
            {"start_date": f"{today.year}-01-15", "end_date": f"{today.year}-01-15"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total_kwh"], 200)
        self.assertEqual(data["cooling_kwh"], 200)
        self.assertEqual(data["heating_kwh"], 0)

    def test_no_data_returns_zeros(self):
        """无数据时返回全 0，不报错"""
        response = self.client.get(
            reverse("dashboard-total-energy"),
            {"start_date": "2000-01-01", "end_date": "2000-12-31"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total_kwh"], 0)
        self.assertEqual(data["cooling_kwh"], 0)
        self.assertEqual(data["heating_kwh"], 0)

    def test_unauthenticated_returns_401(self):
        """未登录时返回 401"""
        client = APIClient()
        response = client.get(reverse("dashboard-total-energy"))
        self.assertEqual(response.status_code, 401)

    def test_invalid_start_date_returns_400(self):
        """非法 start_date 格式返回 400"""
        response = self.client.get(
            reverse("dashboard-total-energy"),
            {"start_date": "not-a-date"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_invalid_end_date_returns_400(self):
        """非法 end_date 格式返回 400"""
        response = self.client.get(
            reverse("dashboard-total-energy"),
            {"end_date": "20250101"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_response_contains_date_fields(self):
        """响应包含 start_date 和 end_date 字段"""
        response = self.client.get(reverse("dashboard-total-energy"))
        data = response.json()["data"]
        self.assertIn("start_date", data)
        self.assertIn("end_date", data)


class DashboardSummaryAPITest(TestCase):
    """看板 API 2：今日/本月累计用电量测试"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = make_user(username="dash_summary_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        today = date.today()
        month_start = date(today.year, today.month, 1)

        # 今日数据：100 kWh
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=today,
            usage_quantity=100,
        )
        # 本月月初数据：80 kWh
        if month_start != today:
            make_daily_record(
                specific_part="3-1-7-702",
                energy_mode="制热",
                time_period=month_start,
                usage_quantity=80,
            )

    def test_today_kwh(self):
        """today_kwh 等于今日所有用量之和"""
        response = self.client.get(reverse("dashboard-summary"))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["today_kwh"], 100)

    def test_month_kwh_includes_today(self):
        """month_kwh 包含当月所有数据（含今日）"""
        response = self.client.get(reverse("dashboard-summary"))
        data = response.json()["data"]
        today = date.today()
        month_start = date(today.year, today.month, 1)
        if month_start != today:
            self.assertEqual(data["month_kwh"], 180)
        else:
            self.assertEqual(data["month_kwh"], 100)

    def test_no_data_returns_zeros(self):
        """数据库无数据时返回全 0"""
        UsageQuantityDaily.objects.all().delete()
        response = self.client.get(reverse("dashboard-summary"))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["today_kwh"], 0)
        self.assertEqual(data["month_kwh"], 0)

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get(reverse("dashboard-summary"))
        self.assertEqual(response.status_code, 401)

    def test_response_contains_date_and_month(self):
        """响应包含 date 和 month 字段"""
        response = self.client.get(reverse("dashboard-summary"))
        data = response.json()["data"]
        self.assertIn("date", data)
        self.assertIn("month", data)


class DashboardPLCOnlineRateAPITest(TestCase):
    """看板 API 3：PLC 系统运行率测试"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = make_user(username="dash_plc_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    def _make_plc(self, specific_part, status_val):
        parts = specific_part.split("-")
        PLCConnectionStatus.objects.create(
            specific_part=specific_part,
            building=parts[0],
            unit=parts[1],
            room_number=parts[-1],
            connection_status=status_val,
        )

    def test_all_online(self):
        """全部在线时 rate=100.0"""
        self._make_plc("3-1-7-701", "online")
        self._make_plc("3-1-7-702", "online")
        response = self.client.get(reverse("dashboard-plc-online-rate"))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["rate"], 100.0)
        self.assertEqual(data["online_count"], 2)
        self.assertEqual(data["offline_count"], 0)
        self.assertEqual(data["total_count"], 2)

    def test_mixed_status(self):
        """混合状态时 rate 正确计算"""
        self._make_plc("3-1-7-701", "online")
        self._make_plc("3-1-7-702", "offline")
        response = self.client.get(reverse("dashboard-plc-online-rate"))
        data = response.json()["data"]
        self.assertEqual(data["rate"], 50.0)
        self.assertEqual(data["online_count"], 1)
        self.assertEqual(data["offline_count"], 1)

    def test_no_devices_returns_zero_rate(self):
        """无设备时 rate=0，不报错"""
        response = self.client.get(reverse("dashboard-plc-online-rate"))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["rate"], 0.0)
        self.assertEqual(data["total_count"], 0)

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get(reverse("dashboard-plc-online-rate"))
        self.assertEqual(response.status_code, 401)


class DashboardTrendAPITest(TestCase):
    """看板 API 4：近 N 天用电量趋势测试"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = make_user(username="dash_trend_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        today = date.today()
        # 昨日数据：制冷 50，制热 30
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=today - timedelta(days=1),
            usage_quantity=50,
        )
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            time_period=today - timedelta(days=1),
            usage_quantity=30,
        )
        # 今日数据：制冷 70
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=today,
            usage_quantity=70,
        )

    def test_default_7_days_returns_7_items(self):
        """默认 days=7 时返回 7 条记录"""
        response = self.client.get(reverse("dashboard-trend"))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data), 7)

    def test_custom_days(self):
        """自定义 days=3 时返回 3 条记录"""
        response = self.client.get(reverse("dashboard-trend"), {"days": "3"})
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(len(data), 3)

    def test_today_total_correct(self):
        """今日合计值正确"""
        response = self.client.get(reverse("dashboard-trend"), {"days": "2"})
        data = response.json()["data"]
        today_str = str(date.today())
        today_item = next(item for item in data if item["date"] == today_str)
        self.assertEqual(today_item["total_kwh"], 70)
        self.assertEqual(today_item["cooling_kwh"], 70)
        self.assertEqual(today_item["heating_kwh"], 0)

    def test_yesterday_total_correct(self):
        """昨日合计值正确（制冷+制热）"""
        response = self.client.get(reverse("dashboard-trend"), {"days": "2"})
        data = response.json()["data"]
        yesterday_str = str(date.today() - timedelta(days=1))
        yesterday_item = next(item for item in data if item["date"] == yesterday_str)
        self.assertEqual(yesterday_item["total_kwh"], 80)
        self.assertEqual(yesterday_item["cooling_kwh"], 50)
        self.assertEqual(yesterday_item["heating_kwh"], 30)

    def test_missing_day_filled_with_zeros(self):
        """无数据的日期填充为 0，不缺少记录"""
        UsageQuantityDaily.objects.all().delete()
        response = self.client.get(reverse("dashboard-trend"), {"days": "5"})
        data = response.json()["data"]
        self.assertEqual(len(data), 5)
        for item in data:
            self.assertEqual(item["total_kwh"], 0)
            self.assertEqual(item["cooling_kwh"], 0)
            self.assertEqual(item["heating_kwh"], 0)

    def test_invalid_days_returns_400(self):
        """非法 days 参数返回 400"""
        response = self.client.get(reverse("dashboard-trend"), {"days": "abc"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_days_zero_returns_400(self):
        """days=0 返回 400"""
        response = self.client.get(reverse("dashboard-trend"), {"days": "0"})
        self.assertEqual(response.status_code, 400)

    def test_days_exceeds_365_returns_400(self):
        """days=366 返回 400"""
        response = self.client.get(reverse("dashboard-trend"), {"days": "366"})
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get(reverse("dashboard-trend"))
        self.assertEqual(response.status_code, 401)

    def test_result_ordered_by_date_ascending(self):
        """返回结果按日期升序排列"""
        response = self.client.get(reverse("dashboard-trend"), {"days": "5"})
        data = response.json()["data"]
        dates = [item["date"] for item in data]
        self.assertEqual(dates, sorted(dates))


class DashboardServicesAPITest(TestCase):
    """看板 API 5：系统服务状态测试（Mock subprocess）"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = make_user(username="dash_services_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

    @patch("api.views.subprocess.run")
    def test_all_services_active(self, mock_run):
        """所有服务均 active 时 is_active=True"""
        mock_result = MagicMock()
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result

        response = self.client.get(reverse("dashboard-services"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        services = body["data"]
        # 有 5 个受监控服务
        self.assertEqual(len(services), 5)
        for svc in services:
            self.assertTrue(svc["is_active"])
            self.assertEqual(svc["status"], "active")

    @patch("api.views.subprocess.run")
    def test_service_inactive(self, mock_run):
        """服务 inactive 时 is_active=False"""
        mock_result = MagicMock()
        mock_result.stdout = "inactive\n"
        mock_run.return_value = mock_result

        response = self.client.get(reverse("dashboard-services"))
        services = response.json()["data"]
        for svc in services:
            self.assertFalse(svc["is_active"])
            self.assertEqual(svc["status"], "inactive")

    @patch("api.views.subprocess.run", side_effect=Exception("systemctl not found"))
    def test_subprocess_exception_returns_unknown(self, mock_run):
        """subprocess 异常时状态为 unknown，不抛出 500"""
        response = self.client.get(reverse("dashboard-services"))
        self.assertEqual(response.status_code, 200)
        services = response.json()["data"]
        for svc in services:
            self.assertEqual(svc["status"], "unknown")
            self.assertFalse(svc["is_active"])

    @patch("api.views.subprocess.run")
    def test_service_names_in_response(self, mock_run):
        """响应中包含所有受监控的服务名"""
        mock_result = MagicMock()
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result

        response = self.client.get(reverse("dashboard-services"))
        service_names = [svc["name"] for svc in response.json()["data"]]
        for expected_name in [
            "freeark-prod-web",
            "freeark-prod-mqtt",
            "freeark-prod-daily",
            "freeark-prod-monthly",
            "freeark-prod-cleanup",
        ]:
            self.assertIn(expected_name, service_names)

    @patch("api.views.subprocess.run")
    def test_subprocess_called_for_each_service(self, mock_run):
        """每个服务都触发了一次 subprocess.run 调用"""
        mock_result = MagicMock()
        mock_result.stdout = "active\n"
        mock_run.return_value = mock_result

        self.client.get(reverse("dashboard-services"))
        self.assertEqual(mock_run.call_count, 5)

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get(reverse("dashboard-services"))
        self.assertEqual(response.status_code, 401)


class DashboardActivitiesAPITest(TestCase):
    """看板 API 6：最近活动测试"""

    def setUp(self):
        self.client = APIClient()
        self.user, self.token = make_user(username="dash_activities_user")
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        # 创建 3 条 PLC 状态变化历史
        for i in range(3):
            PLCStatusChangeHistory.objects.create(
                specific_part=f"3-1-7-70{i+1}",
                status="online" if i % 2 == 0 else "offline",
                building="3",
                unit="1",
                room_number=f"70{i+1}",
            )

    def test_returns_activities(self):
        """正常返回最近活动列表"""
        response = self.client.get(reverse("dashboard-activities"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertIsInstance(body["data"], list)

    def test_default_limit_20(self):
        """默认 limit=20"""
        response = self.client.get(reverse("dashboard-activities"))
        body = response.json()
        self.assertLessEqual(len(body["data"]), 20)

    def test_custom_limit(self):
        """自定义 limit=1 时最多返回 1 条"""
        response = self.client.get(reverse("dashboard-activities"), {"limit": "1"})
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()["data"]), 1)

    def test_activity_structure(self):
        """活动记录包含必要字段"""
        response = self.client.get(reverse("dashboard-activities"))
        activities = response.json()["data"]
        if activities:
            item = activities[0]
            self.assertIn("type", item)
            self.assertIn("timestamp", item)
            self.assertIn("message", item)

    def test_no_data_returns_empty_list(self):
        """无 PLC 历史记录时返回空列表，不报错"""
        PLCStatusChangeHistory.objects.all().delete()
        response = self.client.get(reverse("dashboard-activities"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], [])

    def test_invalid_limit_returns_400(self):
        """非法 limit 参数返回 400"""
        response = self.client.get(reverse("dashboard-activities"), {"limit": "abc"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])

    def test_limit_zero_returns_400(self):
        """limit=0 返回 400"""
        response = self.client.get(reverse("dashboard-activities"), {"limit": "0"})
        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_returns_401(self):
        client = APIClient()
        response = client.get(reverse("dashboard-activities"))
        self.assertEqual(response.status_code, 401)

    def test_plc_status_change_appears_in_activities(self):
        """PLC 状态变化事件出现在活动列表中"""
        response = self.client.get(reverse("dashboard-activities"))
        data = response.json()["data"]
        types = [item["type"] for item in data]
        self.assertIn("plc_status", types)


# ===========================================================================
# 八、CSRF Token 接口测试
# ===========================================================================

class CSRFTokenAPITest(TestCase):
    """CSRF Token 获取接口测试"""

    def setUp(self):
        self.client = Client()

    def test_get_csrf_token_returns_200(self):
        """GET /api/get-csrf-token/ 返回 200，包含 csrftoken 字段"""
        response = self.client.get(reverse("get-csrf-token"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertIn("csrftoken", body)
        self.assertTrue(len(body["csrftoken"]) > 0)

    def test_get_csrf_token_sets_cookie(self):
        """CSRF Token 同时写入响应 Cookie"""
        response = self.client.get(reverse("get-csrf-token"))
        self.assertEqual(response.status_code, 200)
        # Django test client stores cookies; csrftoken should be present
        self.assertIn("csrftoken", response.cookies)


# ===========================================================================
# 九、用户管理详情 API 测试（补充 US-006 / AC-006、AC-007 遗漏场景）
# ===========================================================================

class UserDetailAPITest(TestCase):
    """用户详情 API 测试 — UserDetail 视图（仅管理员）"""

    def setUp(self):
        self.client = APIClient()
        self.admin, self.admin_token = make_user(
            username="admin_det", role="admin", password="AdminDet1!"
        )
        self.target, self.target_token = make_user(
            username="target_user", role="user", password="TargetPass1!"
        )

    def test_admin_can_retrieve_user(self):
        """管理员可获取指定用户详情"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        response = self.client.get(
            reverse("user-detail", kwargs={"pk": self.target.pk})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "target_user")

    def test_admin_can_update_user(self):
        """管理员可更新用户信息（email）"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        response = self.client.patch(
            reverse("user-detail", kwargs={"pk": self.target.pk}),
            {"email": "updated@example.com"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "updated@example.com")

    def test_admin_can_delete_user(self):
        """管理员可删除用户"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        pk = self.target.pk
        response = self.client.delete(
            reverse("user-detail", kwargs={"pk": pk})
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(CustomUser.objects.filter(pk=pk).exists())

    def test_regular_user_cannot_access_detail(self):
        """普通用户无法访问用户详情接口（403）"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.target_token.key}")
        response = self.client.get(
            reverse("user-detail", kwargs={"pk": self.admin.pk})
        )
        self.assertEqual(response.status_code, 403)

    def test_nonexistent_user_returns_404(self):
        """查询不存在的用户 ID 返回 404"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        response = self.client.get(
            reverse("user-detail", kwargs={"pk": 99999})
        )
        self.assertEqual(response.status_code, 404)


# ===========================================================================
# 十、PLC 状态变化历史分页测试（补充 AC-014-* 分页场景）
# ===========================================================================

class PLCStatusHistoryPaginationTest(TestCase):
    """PLC 状态变化历史分页测试"""

    def setUp(self):
        self.client = Client()
        # 创建 5 条历史记录
        for i in range(5):
            PLCStatusChangeHistory.objects.create(
                specific_part="3-1-7-702",
                status="online" if i % 2 == 0 else "offline",
                building="3",
                unit="1",
                room_number="702",
            )

    def test_pagination_page_size(self):
        """分页参数 page_size 生效"""
        response = self.client.get(
            reverse(
                "get-plc-status-change-history",
                kwargs={"specific_part": "3-1-7-702"},
            ),
            {"page": 1, "page_size": 3},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 5)
        self.assertEqual(len(body["data"]), 3)

    def test_second_page(self):
        """第二页返回剩余记录"""
        response = self.client.get(
            reverse(
                "get-plc-status-change-history",
                kwargs={"specific_part": "3-1-7-702"},
            ),
            {"page": 2, "page_size": 3},
        )
        body = response.json()
        self.assertEqual(len(body["data"]), 2)


# ===========================================================================
# 十一、月度用量额外过滤场景测试（补充 AC-011-*）
# ===========================================================================

class UsageQuantityMonthlyFilterTest(TestCase):
    """月度用量按 building/unit/room_number 过滤测试"""

    def setUp(self):
        self.client = Client()
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-03",
            initial_energy=100,
            final_energy=200,
            usage_quantity=100,
        )
        make_monthly_record(
            specific_part="5-2-6-601",
            energy_mode="制冷",
            usage_month="2025-03",
            initial_energy=300,
            final_energy=400,
            usage_quantity=100,
        )

    def test_filter_by_building(self):
        """按 building 过滤月度用量"""
        response = self.client.get(
            reverse("get-usage-quantity-monthly"),
            {"building": "3"},
        )
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["data"][0]["building"], "3")

    def test_filter_by_room_number(self):
        """按 room_number 过滤月度用量"""
        response = self.client.get(
            reverse("get-usage-quantity-monthly"),
            {"room_number": "601"},
        )
        data = response.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["data"][0]["specific_part"], "5-2-6-601")


# ===========================================================================
# 十二、集成测试 — 跨模块数据流验证
# ===========================================================================

class IntegrationTestPLCToUsagePipeline(TestCase):
    """
    集成测试：PLC 数据写入 → 日用量计算 → 月用量计算 → API 查询完整链路

    验证从 MQTT 数据接收到最终 API 可查到聚合结果的完整数据流。
    """

    def setUp(self):
        self.handler = PLCDataHandler()
        self.today = date.today()
        self.month_start = date(self.today.year, self.today.month, 1)

    def _send_plc_message(self, specific_part, cold_value, hot_value, usage_date=None):
        """构造并发送一条 improved_data_collection_manager 格式的 MQTT 消息"""
        if usage_date is None:
            usage_date = self.today
        ts = usage_date.strftime("%Y-%m-%d") + " 10:00:00"
        payload = {
            specific_part: {
                "PLC IP地址": "192.168.1.10",
                "data": {
                    "total_cold_quantity": {
                        "success": True,
                        "value": cold_value,
                        "message": "ok",
                        "timestamp": ts,
                    },
                    "total_hot_quantity": {
                        "success": True,
                        "value": hot_value,
                        "message": "ok",
                        "timestamp": ts,
                    },
                },
            }
        }
        self.handler.handle("/datacollection/plc/to/collector/3#", payload)

    def test_plc_data_persisted_after_mqtt_message(self):
        """MQTT 消息处理后 PLCData 表中应有对应记录"""
        self._send_plc_message("3-1-7-702", cold_value=5000, hot_value=3000)
        self.assertEqual(
            PLCData.objects.filter(specific_part="3-1-7-702", energy_mode="制冷").count(), 1
        )
        self.assertEqual(
            PLCData.objects.filter(specific_part="3-1-7-702", energy_mode="制热").count(), 1
        )

    def test_daily_usage_generated_from_plc_data(self):
        """PLCData 写入后，DailyUsageCalculator 能生成对应的日用量记录"""
        self._send_plc_message("3-1-7-702", cold_value=5000, hot_value=3000)
        result = DailyUsageCalculator.calculate_daily_usage(self.today)
        self.assertGreaterEqual(result["processed_count"], 2)
        # 当日记录应被创建（initial_energy = final_energy = PLC value，usage_quantity = 0）
        daily_cold = UsageQuantityDaily.objects.filter(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=self.today,
        ).first()
        self.assertIsNotNone(daily_cold)
        self.assertEqual(daily_cold.initial_energy, 5000)

    def test_monthly_usage_aggregated_from_daily_data(self):
        """日用量记录经 MonthlyUsageCalculator 聚合后，月用量表有正确结果"""
        # 模拟同一房间在本月1日和今天各有一条日用量记录
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=self.month_start,
            initial_energy=1000,
            final_energy=1000,
            usage_quantity=0,
        )
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=self.today,
            initial_energy=1000,
            final_energy=1500,
            usage_quantity=500,
        )
        result = MonthlyUsageCalculator.calculate_monthly_usage(self.month_start)
        self.assertFalse(result.get("skipped", True))
        monthly = UsageQuantityMonthly.objects.get(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month=self.month_start.strftime("%Y-%m"),
        )
        self.assertEqual(monthly.initial_energy, 1000)
        self.assertEqual(monthly.final_energy, 1500)
        self.assertEqual(monthly.usage_quantity, 500)

    def test_api_returns_daily_data_after_full_pipeline(self):
        """完整管道执行后，GET /api/usage/quantity/ 能查到日用量数据"""
        self._send_plc_message("3-1-7-702", cold_value=5000, hot_value=3000)
        DailyUsageCalculator.calculate_daily_usage(self.today)

        client = Client()
        response = client.get(
            reverse("get-usage-quantity"),
            {"specific_part": "3-1-7-702", "energy_mode": "制冷"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["total"], 0)

    def test_api_returns_monthly_data_after_full_pipeline(self):
        """完整管道执行后，GET /api/usage/quantity/monthly/ 能查到月用量数据"""
        make_daily_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            time_period=self.month_start,
            initial_energy=2000,
            final_energy=2200,
            usage_quantity=200,
        )
        MonthlyUsageCalculator.calculate_monthly_usage(self.month_start)

        client = Client()
        response = client.get(
            reverse("get-usage-quantity-monthly"),
            {"specific_part": "3-1-7-702"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json()["total"], 0)

    def test_multiple_rooms_full_pipeline(self):
        """多房间多模式数据经完整管道后，API 各自返回正确记录"""
        rooms = [("3-1-7-702", 5000, 3000), ("3-1-7-801", 4000, 2000)]
        for sp, cold, hot in rooms:
            self._send_plc_message(sp, cold_value=cold, hot_value=hot)

        DailyUsageCalculator.calculate_daily_usage(self.today)

        for sp, _, _ in rooms:
            daily_cold = UsageQuantityDaily.objects.filter(
                specific_part=sp, energy_mode="制冷", time_period=self.today
            ).exists()
            self.assertTrue(daily_cold, f"房间 {sp} 缺少制冷日用量记录")


class IntegrationTestUserLifecycle(TestCase):
    """
    集成测试：用户生命周期完整流程

    管理员创建用户 → 用户登录获取 Token → 使用 Token 查询受保护接口
    → 修改密码 → 旧 Token 仍有效（DRF Token 认证不因密码修改而失效）
    → 管理员删除用户 → 被删用户的 Token 无法访问受保护接口
    """

    def setUp(self):
        self.client = APIClient()
        self.admin, self.admin_token = make_user(
            username="lifecycle_admin", role="admin", password="AdminLife1!"
        )

    def _admin_headers(self):
        return {"HTTP_AUTHORIZATION": f"Token {self.admin_token.key}"}

    def test_full_user_lifecycle(self):
        # Step 1: 管理员创建普通用户
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        create_resp = self.client.post(
            reverse("admin-user-create"),
            {"username": "lifecycle_user", "password": "UserLife1!", "role": "user"},
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201)
        new_user_id = create_resp.data["id"]
        self.assertTrue(CustomUser.objects.filter(id=new_user_id).exists())

        # Step 2: 新用户使用账密登录，获取 Token
        self.client.credentials()  # 清除凭证
        login_resp = self.client.post(
            reverse("user-login"),
            {"username": "lifecycle_user", "password": "UserLife1!"},
            format="json",
        )
        self.assertEqual(login_resp.status_code, 200)
        user_token = login_resp.data["token"]
        self.assertIsNotNone(user_token)

        # Step 3: 使用 Token 查询受保护接口（GET /api/auth/me/）
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {user_token}")
        me_resp = self.client.get(reverse("get-current-user"))
        self.assertEqual(me_resp.status_code, 200)
        self.assertEqual(me_resp.data["data"]["username"], "lifecycle_user")

        # Step 4: 修改密码
        pwd_resp = self.client.post(
            reverse("change-password"),
            {"current_password": "UserLife1!", "new_password": "NewLife99!"},
            format="json",
        )
        self.assertEqual(pwd_resp.status_code, 200)
        self.assertTrue(pwd_resp.data["success"])

        # Step 5: 旧 Token 仍有效（DRF Token 认证不因密码修改失效）
        me_resp2 = self.client.get(reverse("get-current-user"))
        self.assertEqual(me_resp2.status_code, 200)

        # Step 6: 管理员删除用户
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        del_resp = self.client.delete(
            reverse("user-detail", kwargs={"pk": new_user_id})
        )
        self.assertEqual(del_resp.status_code, 204)
        self.assertFalse(CustomUser.objects.filter(id=new_user_id).exists())

        # Step 7: 被删用户的旧 Token 现在无法访问受保护接口（Token 随用户删除而失效）
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {user_token}")
        me_resp3 = self.client.get(reverse("get-current-user"))
        self.assertEqual(me_resp3.status_code, 401)

    def test_deleted_user_cannot_login(self):
        """删除后的用户无法再登录"""
        user = CustomUser.objects.create_user(
            username="del_me", password="DelPass1!"
        )
        user.delete()
        self.client.credentials()
        resp = self.client.post(
            reverse("user-login"),
            {"username": "del_me", "password": "DelPass1!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_username_rejected_by_admin_create(self):
        """管理员创建用户时，重复用户名被拒绝（400），DB 中仍只有一个同名用户"""
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.admin_token.key}")
        self.client.post(
            reverse("admin-user-create"),
            {"username": "uniq_user", "password": "Pass1!", "role": "user"},
            format="json",
        )
        resp2 = self.client.post(
            reverse("admin-user-create"),
            {"username": "uniq_user", "password": "Pass2!", "role": "user"},
            format="json",
        )
        self.assertEqual(resp2.status_code, 400)
        self.assertEqual(CustomUser.objects.filter(username="uniq_user").count(), 1)


class IntegrationTestPLCStatusFlow(TestCase):
    """
    集成测试：PLC 在线/离线状态切换 + 历史记录联动

    ConnectionStatusHandler 处理在线消息 → PLCConnectionStatus 创建/更新
    → PLCStatusChangeHistory 新增记录 → 再处理离线消息 → 状态切换
    → 历史再增一条 → API 查询结果正确
    """

    def setUp(self):
        self.handler = ConnectionStatusHandler()
        self.client = Client()

    def _online_payload(self, specific_part):
        return {
            specific_part: {
                "data": {
                    "total_cold_quantity": {"success": True, "value": 100},
                }
            }
        }

    def _offline_payload(self, specific_part):
        return {
            specific_part: {
                "data": {
                    "total_cold_quantity": {"success": False, "value": None},
                    "total_hot_quantity": {"success": False, "value": None},
                }
            }
        }

    def test_online_creates_status_and_history(self):
        """收到在线消息后 PLCConnectionStatus 应创建为 online，历史表新增 1 条"""
        sp = "3-1-7-702"
        self.handler.handle("/topic", self._online_payload(sp))

        status_obj = PLCConnectionStatus.objects.get(specific_part=sp)
        self.assertEqual(status_obj.connection_status, "online")

        history_count = PLCStatusChangeHistory.objects.filter(
            specific_part=sp, status="online"
        ).count()
        self.assertEqual(history_count, 1)

    def test_offline_after_online_updates_status_and_adds_history(self):
        """先在线再离线：状态更新为 offline，历史表共 2 条（online + offline）"""
        sp = "3-1-7-702"
        self.handler.handle("/topic", self._online_payload(sp))
        self.handler.handle("/topic", self._offline_payload(sp))

        status_obj = PLCConnectionStatus.objects.get(specific_part=sp)
        self.assertEqual(status_obj.connection_status, "offline")

        history_count = PLCStatusChangeHistory.objects.filter(specific_part=sp).count()
        self.assertEqual(history_count, 2)

    def test_repeated_online_no_extra_history(self):
        """连续发送两次在线消息，状态不变，历史仅保留 1 条"""
        sp = "3-1-7-702"
        self.handler.handle("/topic", self._online_payload(sp))
        self.handler.handle("/topic", self._online_payload(sp))

        history_count = PLCStatusChangeHistory.objects.filter(
            specific_part=sp, status="online"
        ).count()
        self.assertEqual(history_count, 1)

    def test_api_connection_status_reflects_handler_result(self):
        """handler 更新后，GET /api/plc/connection-status/ 能查到最新状态"""
        sp = "3-1-7-702"
        self.handler.handle("/topic", self._online_payload(sp))

        response = self.client.get(reverse("get-plc-connection-status"))
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        found = [d for d in data if d["specific_part"] == sp]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["connection_status"], "online")

    def test_api_history_reflects_both_status_changes(self):
        """GET /api/plc/status-change-history/<sp>/ 返回在线和离线的历史各 1 条"""
        sp = "3-1-7-702"
        self.handler.handle("/topic", self._online_payload(sp))
        self.handler.handle("/topic", self._offline_payload(sp))

        response = self.client.get(
            reverse("get-plc-status-change-history", kwargs={"specific_part": sp})
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        statuses = {item["status"] for item in body["data"]}
        self.assertIn("online", statuses)
        self.assertIn("offline", statuses)

    def test_last_online_time_set_when_online(self):
        """设备在线后 last_online_time 应被更新"""
        sp = "3-1-7-702"
        self.handler.handle("/topic", self._online_payload(sp))
        status_obj = PLCConnectionStatus.objects.get(specific_part=sp)
        self.assertIsNotNone(status_obj.last_online_time)


class IntegrationTestBillingCalculation(TestCase):
    """
    集成测试：账单金额计算端到端验证

    预置 SpecificPartInfo + UsageQuantityMonthly → POST /api/billing/list/
    验证 billAmount、billingCycle、chargeItems 等字段计算正确，覆盖制冷/制热两种场景。
    """

    UNIT_PRICE = 0.28

    def setUp(self):
        self.client = Client()
        self.screen_mac = "BB:CC:DD:EE:FF:00"
        SpecificPartInfo.objects.create(
            screenMAC=self.screen_mac,
            specific_part="3-1-7-702",
        )

    def _post_billing(self, body):
        import json
        return self.client.post(
            reverse("get-bill-list"),
            data=json.dumps(body),
            content_type="application/json",
            HTTP_SCREENMAC=self.screen_mac,
        )

    def test_cooling_bill_amount_correct(self):
        """制冷账单金额 = usage_quantity * 0.28，保留两位小数"""
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-03",
            initial_energy=1000,
            final_energy=1200,
            usage_quantity=200,
        )
        resp = self._post_billing({"startDate": "2025-03", "endDate": "2025-03", "energyType": "制冷"})
        self.assertEqual(resp.status_code, 200)
        items = resp.json()["data"]
        self.assertEqual(len(items), 1)
        item = items[0]
        expected_amount = round(200 * self.UNIT_PRICE, 2)
        self.assertEqual(item["billAmount"], f"{expected_amount:.2f}")
        self.assertEqual(item["modeName"], "制冷")
        self.assertEqual(item["chargeItems"], "制冷费")
        self.assertEqual(item["usageAmount"], "200")

    def test_heating_bill_amount_correct(self):
        """制热账单金额 = usage_quantity * 0.28"""
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            usage_month="2025-03",
            initial_energy=3000,
            final_energy=3150,
            usage_quantity=150,
        )
        resp = self._post_billing({"startDate": "2025-03", "endDate": "2025-03", "energyType": "制热"})
        items = resp.json()["data"]
        self.assertEqual(len(items), 1)
        item = items[0]
        expected_amount = round(150 * self.UNIT_PRICE, 2)
        self.assertEqual(item["billAmount"], f"{expected_amount:.2f}")
        self.assertEqual(item["chargeItems"], "制热费")

    def test_both_modes_returned_without_energy_type_filter(self):
        """不传 energyType 时制冷和制热账单均返回"""
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-04",
            initial_energy=100,
            final_energy=300,
            usage_quantity=200,
        )
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            usage_month="2025-04",
            initial_energy=200,
            final_energy=400,
            usage_quantity=200,
        )
        resp = self._post_billing({"startDate": "2025-04", "endDate": "2025-04"})
        items = resp.json()["data"]
        self.assertEqual(len(items), 2)
        modes = {item["modeName"] for item in items}
        self.assertIn("制冷", modes)
        self.assertIn("制热", modes)

    def test_billing_cycle_and_date_format(self):
        """billingCycle 为 YYYY年MM月，billingDate 为该月最后一天"""
        import calendar as cal
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-02",
            initial_energy=0,
            final_energy=100,
            usage_quantity=100,
        )
        resp = self._post_billing({"startDate": "2025-02", "endDate": "2025-02"})
        item = resp.json()["data"][0]
        self.assertEqual(item["billingCycle"], "2025年02月")
        last_day = cal.monthrange(2025, 2)[1]
        self.assertEqual(item["billingDate"], f"2025-02-{last_day:02d}")

    def test_zero_usage_gives_zero_bill(self):
        """usage_quantity=0 时 billAmount=0.00"""
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-05",
            initial_energy=500,
            final_energy=500,
            usage_quantity=0,
        )
        resp = self._post_billing({"startDate": "2025-05", "endDate": "2025-05"})
        item = resp.json()["data"][0]
        self.assertEqual(item["billAmount"], "0.00")
        self.assertEqual(item["usageAmount"], "0")


# ===========================================================================
# 十三、E2E 测试 — 完整 HTTP 场景
# ===========================================================================

class E2ETestAuthProtection(TestCase):
    """
    E2E 测试：所有需认证的接口，在未携带 Token 时均返回 401

    覆盖所有 permission_classes=[permissions.IsAuthenticated] 的端点。
    """

    def setUp(self):
        self.client = APIClient()

    def _assert_401(self, method, url_name, **kwargs):
        """不带认证发请求，断言返回 401"""
        func = getattr(self.client, method)
        response = func(reverse(url_name, **kwargs), format="json")
        self.assertEqual(
            response.status_code,
            401,
            f"{method.upper()} {url_name} 未认证应返回 401，实际: {response.status_code}",
        )

    def test_logout_requires_auth(self):
        self._assert_401("post", "user-logout")

    def test_get_current_user_requires_auth(self):
        self._assert_401("get", "get-current-user")

    def test_change_password_requires_auth(self):
        self._assert_401("post", "change-password")

    def test_user_list_requires_auth(self):
        """user-list 要求 admin 权限，未认证应返回 401"""
        response = self.client.get(reverse("user-list"))
        self.assertEqual(response.status_code, 401)

    def test_admin_user_create_requires_auth(self):
        """admin-user-create 要求 admin 权限，未认证应返回 401"""
        response = self.client.post(
            reverse("admin-user-create"),
            {"username": "x", "password": "y"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_user_detail_requires_auth(self):
        """user-detail 要求 admin 权限，未认证应返回 401"""
        user = CustomUser.objects.create_user(username="tmp_det", password="p")
        response = self.client.get(
            reverse("user-detail", kwargs={"pk": user.pk})
        )
        self.assertEqual(response.status_code, 401)


class E2ETestBillingFlow(TestCase):
    """
    E2E 测试：完整账单查询流程

    登录 → 获取 CSRF Token → 查账单（带正确 screenMac、日期范围）
    → 验证账单金额和结构正确
    """

    def setUp(self):
        self.client = Client()
        self.api_client = APIClient()
        # 预置数据
        self.screen_mac = "CC:DD:EE:FF:00:11"
        SpecificPartInfo.objects.create(
            screenMAC=self.screen_mac,
            specific_part="3-1-7-702",
        )
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-06",
            initial_energy=1000,
            final_energy=1250,
            usage_quantity=250,
        )
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制热",
            usage_month="2025-06",
            initial_energy=2000,
            final_energy=2100,
            usage_quantity=100,
        )

    def test_login_then_query_billing(self):
        """
        用户登录获取 Token → 查询账单接口，账单数量、金额正确
        （账单接口本身不需要 Token，此处重点验证登录流程与账单流程可串联）
        """
        import json

        # Step 1: 登录
        _, token = make_user(username="billing_e2e", password="BillingE2E1!")
        self.api_client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        # Step 2: 确认当前用户已认证（验证 Token 有效）
        me_resp = self.api_client.get(reverse("get-current-user"))
        self.assertEqual(me_resp.status_code, 200)

        # Step 3: 查询账单（账单接口 AllowAny，使用普通 client）
        bill_resp = self.client.post(
            reverse("get-bill-list"),
            data=json.dumps({"startDate": "2025-06", "endDate": "2025-06"}),
            content_type="application/json",
            HTTP_SCREENMAC=self.screen_mac,
        )
        self.assertEqual(bill_resp.status_code, 200)
        body = bill_resp.json()
        self.assertEqual(body["code"], 200)
        self.assertEqual(len(body["data"]), 2)

        # Step 4: 验证账单金额
        amounts = {item["modeName"]: float(item["billAmount"]) for item in body["data"]}
        self.assertAlmostEqual(amounts["制冷"], round(250 * 0.28, 2), places=2)
        self.assertAlmostEqual(amounts["制热"], round(100 * 0.28, 2), places=2)

    def test_csrf_then_billing(self):
        """先获取 CSRF Token，再携带 screenMAC 查账单，验证端到端流程"""
        import json

        # Step 1: 获取 CSRF Token
        csrf_resp = self.client.get(reverse("get-csrf-token"))
        self.assertEqual(csrf_resp.status_code, 200)
        self.assertIn("csrftoken", csrf_resp.json())

        # Step 2: 查询账单（账单接口 csrf_exempt，不需要 CSRF Token，流程仍通）
        bill_resp = self.client.post(
            reverse("get-bill-list"),
            data=json.dumps({"startDate": "2025-06", "endDate": "2025-06"}),
            content_type="application/json",
            HTTP_SCREENMAC=self.screen_mac,
        )
        self.assertEqual(bill_resp.status_code, 200)
        self.assertEqual(len(bill_resp.json()["data"]), 2)

    def test_billing_flow_with_energy_type_filter(self):
        """只查制冷账单，制热账单不出现"""
        import json
        bill_resp = self.client.post(
            reverse("get-bill-list"),
            data=json.dumps({"startDate": "2025-06", "endDate": "2025-06", "energyType": "制冷"}),
            content_type="application/json",
            HTTP_SCREENMAC=self.screen_mac,
        )
        data = bill_resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["modeName"], "制冷")
        self.assertAlmostEqual(float(data[0]["billAmount"]), round(250 * 0.28, 2), places=2)


class E2ETestPaginationConsistency(TestCase):
    """
    E2E 测试：分页一致性验证

    同一查询条件分多页请求，total 不变，每页数据不重叠，所有页合并后等于总量。
    """

    def setUp(self):
        self.client = Client()
        # 创建 7 条日用量记录（同一 specific_part，不同日期）
        for i in range(7):
            UsageQuantityDaily.objects.create(
                specific_part="3-1-7-702",
                building="3",
                unit="1",
                room_number="702",
                energy_mode="制冷",
                initial_energy=1000 + i * 50,
                final_energy=1050 + i * 50,
                usage_quantity=50,
                time_period=date(2025, 1, i + 1),
            )

    def test_daily_pagination_total_consistent(self):
        """分两页查询，两次 total 相同"""
        params = {"specific_part": "3-1-7-702", "energy_mode": "制冷", "page_size": 4}

        resp1 = self.client.get(reverse("get-usage-quantity"), {**params, "page": 1})
        resp2 = self.client.get(reverse("get-usage-quantity"), {**params, "page": 2})

        body1 = resp1.json()
        body2 = resp2.json()

        self.assertEqual(body1["total"], body2["total"])
        self.assertEqual(body1["total"], 7)

    def test_daily_pagination_no_overlap(self):
        """第一页和第二页的数据不重叠"""
        params = {"specific_part": "3-1-7-702", "energy_mode": "制冷", "page_size": 4}

        resp1 = self.client.get(reverse("get-usage-quantity"), {**params, "page": 1})
        resp2 = self.client.get(reverse("get-usage-quantity"), {**params, "page": 2})

        ids1 = {item["id"] for item in resp1.json()["data"]}
        ids2 = {item["id"] for item in resp2.json()["data"]}
        self.assertEqual(len(ids1 & ids2), 0)

    def test_daily_pagination_all_pages_cover_total(self):
        """所有页合并后，ID 集合大小等于 total"""
        params = {"specific_part": "3-1-7-702", "energy_mode": "制冷", "page_size": 3}
        total = 7
        all_ids = set()

        for page in range(1, (total // 3) + 2):
            resp = self.client.get(reverse("get-usage-quantity"), {**params, "page": page})
            for item in resp.json()["data"]:
                all_ids.add(item["id"])

        self.assertEqual(len(all_ids), total)

    def test_monthly_pagination_total_consistent(self):
        """月度用量分两页查询，total 一致"""
        for i in range(5):
            UsageQuantityMonthly.objects.create(
                specific_part="3-1-7-702",
                building="3",
                unit="1",
                room_number="702",
                energy_mode="制冷",
                initial_energy=1000,
                final_energy=1100,
                usage_quantity=100,
                usage_month=f"2025-{i + 1:02d}",
            )

        params = {"specific_part": "3-1-7-702", "energy_mode": "制冷", "page_size": 3}
        resp1 = self.client.get(reverse("get-usage-quantity-monthly"), {**params, "page": 1})
        resp2 = self.client.get(reverse("get-usage-quantity-monthly"), {**params, "page": 2})

        self.assertEqual(resp1.json()["total"], resp2.json()["total"])
        self.assertEqual(resp1.json()["total"], 5)


class E2ETestFilterCombinations(TestCase):
    """
    E2E 测试：多条件组合过滤正确性

    building + unit + room_number + energy_mode + 日期范围组合过滤，
    结果集严格符合所有指定条件。
    """

    def setUp(self):
        self.client = Client()
        # 构造多种组合的测试数据
        data_points = [
            ("3-1-7-702", "3", "1", "702", "制冷", date(2025, 1, 10)),
            ("3-1-7-702", "3", "1", "702", "制热", date(2025, 1, 10)),
            ("3-1-7-702", "3", "1", "702", "制冷", date(2025, 2, 10)),
            ("5-2-6-601", "5", "2", "601", "制冷", date(2025, 1, 10)),
            ("5-2-6-601", "5", "2", "601", "制热", date(2025, 1, 10)),
        ]
        for sp, bld, unt, rm, mode, tp in data_points:
            UsageQuantityDaily.objects.create(
                specific_part=sp,
                building=bld,
                unit=unt,
                room_number=rm,
                energy_mode=mode,
                initial_energy=1000,
                final_energy=1100,
                usage_quantity=100,
                time_period=tp,
            )

    def test_filter_building_only(self):
        """仅按 building 过滤，结果全部属于该楼栋"""
        # 日用量接口按 specific_part 过滤，不直接支持 building 参数
        # 改用月度接口（支持 building 参数）验证
        for sp, bld, unt, rm, mode, tp in [
            ("3-1-7-702", "3", "1", "702", "制冷", "2025-01"),
            ("5-2-6-601", "5", "2", "601", "制冷", "2025-01"),
        ]:
            UsageQuantityMonthly.objects.create(
                specific_part=sp,
                building=bld,
                unit=unt,
                room_number=rm,
                energy_mode=mode,
                initial_energy=1000,
                final_energy=1100,
                usage_quantity=100,
                usage_month=tp,
            )
        resp = self.client.get(reverse("get-usage-quantity-monthly"), {"building": "3"})
        data = resp.json()["data"]
        self.assertTrue(all(item["building"] == "3" for item in data))
        self.assertGreater(len(data), 0)

    def test_filter_energy_mode_and_date_range(self):
        """energy_mode + 日期范围组合过滤，结果严格满足两个条件"""
        resp = self.client.get(
            reverse("get-usage-quantity"),
            {
                "energy_mode": "制冷",
                "start_time": "2025-01-01",
                "end_time": "2025-01-31",
            },
        )
        body = resp.json()
        for item in body["data"]:
            self.assertEqual(item["energy_mode"], "制冷")
            self.assertGreaterEqual(item["time_period"], "2025-01-01")
            self.assertLessEqual(item["time_period"], "2025-01-31")

    def test_filter_specific_part_and_energy_mode(self):
        """specific_part + energy_mode 组合过滤返回唯一结果"""
        resp = self.client.get(
            reverse("get-usage-quantity"),
            {
                "specific_part": "3-1-7-702",
                "energy_mode": "制热",
            },
        )
        body = resp.json()
        # 3-1-7-702 制热只有 1 条
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["data"][0]["specific_part"], "3-1-7-702")
        self.assertEqual(body["data"][0]["energy_mode"], "制热")

    def test_specific_time_period_filter_combinations(self):
        """特定时间段接口多条件组合：specific_part + energy_mode + 日期范围"""
        resp = self.client.get(
            reverse("get-usage-quantity-specific-time-period"),
            {
                "specific_part": "3-1-7-702",
                "energy_mode": "制冷",
                "start_time": "2025-01-01",
                "end_time": "2025-03-31",
            },
        )
        body = resp.json()
        self.assertEqual(body["success"], True)
        # 3-1-7-702 制冷 在1月和2月各 1 条，组合后应出现 1 个 specific_part 结果
        self.assertEqual(len(body["data"]), 1)
        item = body["data"][0]
        self.assertEqual(item["specific_part"], "3-1-7-702")
        self.assertEqual(item["energy_mode"], "制冷")
        # usage_quantity = max(final) - min(initial) = 1100 - 1000 = 100
        self.assertEqual(item["usage_quantity"], 100)

    def test_monthly_building_unit_room_energy_combination(self):
        """月度接口 building+unit+room_number+energy_mode 组合过滤"""
        make_monthly_record(
            specific_part="3-1-7-702",
            energy_mode="制冷",
            usage_month="2025-07",
            initial_energy=100,
            final_energy=200,
            usage_quantity=100,
        )
        make_monthly_record(
            specific_part="5-2-6-601",
            energy_mode="制冷",
            usage_month="2025-07",
            initial_energy=300,
            final_energy=400,
            usage_quantity=100,
        )
        resp = self.client.get(
            reverse("get-usage-quantity-monthly"),
            {
                "building": "3",
                "unit": "1",
                "room_number": "702",
                "energy_mode": "制冷",
                "usage_month": "2025-07",
            },
        )
        body = resp.json()
        self.assertEqual(body["total"], 1)
        item = body["data"][0]
        self.assertEqual(item["building"], "3")
        self.assertEqual(item["room_number"], "702")
        self.assertEqual(item["energy_mode"], "制冷")


class E2ETestPLCStatisticsConsistency(TestCase):
    """
    E2E 测试：PLC 状态查询统计数据内部一致性

    验证 online_count + offline_count = total_devices，
    online_rate 计算正确，过滤后分页数据与统计字段一致。
    """

    def setUp(self):
        self.client = Client()

    def _create_devices(self, online_count, offline_count):
        for i in range(online_count):
            PLCConnectionStatus.objects.create(
                specific_part=f"3-1-7-{700 + i}",
                building="3",
                unit="1",
                room_number=str(700 + i),
                connection_status="online",
            )
        for j in range(offline_count):
            PLCConnectionStatus.objects.create(
                specific_part=f"5-2-6-{600 + j}",
                building="5",
                unit="2",
                room_number=str(600 + j),
                connection_status="offline",
            )

    def test_online_plus_offline_equals_total(self):
        """online_count + offline_count 必须等于 total_devices"""
        self._create_devices(online_count=3, offline_count=2)
        resp = self.client.get(reverse("get-plc-connection-status"))
        stats = resp.json()["statistics"]
        self.assertEqual(
            stats["online_count"] + stats["offline_count"],
            stats["total_devices"],
        )

    def test_online_rate_calculation(self):
        """online_rate = online_count / total_devices * 100，精确到两位小数"""
        self._create_devices(online_count=2, offline_count=3)
        resp = self.client.get(reverse("get-plc-connection-status"))
        stats = resp.json()["statistics"]
        expected_rate = round(2 / 5 * 100, 2)
        self.assertAlmostEqual(stats["online_rate"], expected_rate, places=1)

    def test_all_online_rate_is_100(self):
        """全部在线时 online_rate = 100.0"""
        self._create_devices(online_count=4, offline_count=0)
        resp = self.client.get(reverse("get-plc-connection-status"))
        stats = resp.json()["statistics"]
        self.assertEqual(stats["online_rate"], 100.0)
        self.assertEqual(stats["offline_count"], 0)

    def test_all_offline_rate_is_0(self):
        """全部离线时 online_rate = 0"""
        self._create_devices(online_count=0, offline_count=3)
        resp = self.client.get(reverse("get-plc-connection-status"))
        stats = resp.json()["statistics"]
        self.assertEqual(stats["online_rate"], 0)
        self.assertEqual(stats["online_count"], 0)

    def test_empty_devices_rate_is_0(self):
        """无设备时 online_rate = 0，不产生除零错误"""
        resp = self.client.get(reverse("get-plc-connection-status"))
        stats = resp.json()["statistics"]
        self.assertEqual(stats["total_devices"], 0)
        self.assertEqual(stats["online_rate"], 0)

    def test_statistics_stable_across_pages(self):
        """统计字段在分页查询中保持稳定（不受分页影响）"""
        self._create_devices(online_count=3, offline_count=2)
        resp1 = self.client.get(
            reverse("get-plc-connection-status"), {"page": 1, "page_size": 2}
        )
        resp2 = self.client.get(
            reverse("get-plc-connection-status"), {"page": 2, "page_size": 2}
        )
        stats1 = resp1.json()["statistics"]
        stats2 = resp2.json()["statistics"]
        self.assertEqual(stats1["total_devices"], stats2["total_devices"])
        self.assertEqual(stats1["online_count"], stats2["online_count"])
        self.assertEqual(stats1["online_rate"], stats2["online_rate"])


# ===========================================================================
# 十四、Management Command 集成测试
# ===========================================================================

class IntegrationTestManagementCommands(TestCase):
    """
    Management Command 集成测试

    仅测试 --run-once / --once 单次执行路径，不触发 while 循环。
    通过 call_command() 驱动 Command.handle()，验证 Command 正确调用
    了底层计算器/清理函数并最终写入数据库。
    """

    def setUp(self):
        self.today = date.today()
        self.yesterday = self.today - timedelta(days=1)
        # 上个月的第一天（供月度服务测试）
        if self.today.month == 1:
            self.last_month_start = date(self.today.year - 1, 12, 1)
        else:
            self.last_month_start = date(self.today.year, self.today.month - 1, 1)

    # ------------------------------------------------------------------
    # daily_usage_service
    # ------------------------------------------------------------------

    def test_daily_usage_service_run_once_processes_data(self):
        """
        daily_usage_service --run-once 应调用 DailyUsageCalculator
        并在数据库中产生日用量记录
        """
        from django.core.management import call_command

        # 预置昨天的 PLCData
        PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            value=5000,
            usage_date=self.yesterday,
        )

        # 执行命令（--run-once，计算昨天的数据，默认 --date 为昨天）
        call_command("daily_usage_service", "--run-once")

        # 断言至少产生了昨天的日用量记录
        self.assertTrue(
            UsageQuantityDaily.objects.filter(
                specific_part="3-1-7-702",
                energy_mode="制冷",
                time_period=self.yesterday,
            ).exists()
        )

    def test_daily_usage_service_run_once_with_explicit_date(self):
        """
        daily_usage_service --run-once --date YYYY-MM-DD 使用指定日期
        """
        from django.core.management import call_command

        target = date(2025, 3, 15)
        PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制热",
            value=8000,
            usage_date=target,
        )

        call_command("daily_usage_service", "--run-once", f"--date=2025-03-15")

        self.assertTrue(
            UsageQuantityDaily.objects.filter(
                specific_part="3-1-7-702",
                energy_mode="制热",
                time_period=target,
            ).exists()
        )

    def test_daily_usage_service_no_plc_data_does_not_crash(self):
        """
        daily_usage_service --run-once 在没有 PLCData 时不崩溃，正常退出
        """
        from django.core.management import call_command

        # 不插入任何 PLCData，command 应安静地返回
        try:
            call_command("daily_usage_service", "--run-once")
        except Exception as e:
            self.fail(f"daily_usage_service --run-once 不应抛出异常: {e}")

    def test_daily_usage_service_invalid_date_returns_gracefully(self):
        """
        daily_usage_service --run-once --date 传入非法格式，Command 不崩溃
        （内部调用 self.stdout.write(style.ERROR(...)) 并 return 1，不 raise）
        """
        from django.core.management import call_command

        # 这里不断言异常，只断言 call_command 调用本身不向外抛出
        try:
            call_command("daily_usage_service", "--run-once", "--date=bad-date")
        except SystemExit:
            pass  # 部分 management command 错误会 sys.exit，允许
        except Exception as e:
            self.fail(f"daily_usage_service 不应抛出非 SystemExit 异常: {e}")

    # ------------------------------------------------------------------
    # monthly_usage_service
    # ------------------------------------------------------------------

    def test_monthly_usage_service_run_once_processes_data(self):
        """
        monthly_usage_service --run-once 应调用 MonthlyUsageCalculator
        并在数据库中产生月度用量记录
        """
        from django.core.management import call_command

        # 预置上个月的日用量记录
        UsageQuantityDaily.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            initial_energy=1000,
            final_energy=1200,
            usage_quantity=200,
            time_period=self.last_month_start,
        )

        call_command("monthly_usage_service", "--run-once")

        expected_month = self.last_month_start.strftime("%Y-%m")
        self.assertTrue(
            UsageQuantityMonthly.objects.filter(
                specific_part="3-1-7-702",
                energy_mode="制冷",
                usage_month=expected_month,
            ).exists()
        )

    def test_monthly_usage_service_run_once_with_explicit_month(self):
        """
        monthly_usage_service --run-once --month YYYY-MM 使用指定月份
        """
        from django.core.management import call_command

        # 预置 2025-03 的日用量记录
        UsageQuantityDaily.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制热",
            initial_energy=3000,
            final_energy=3300,
            usage_quantity=300,
            time_period=date(2025, 3, 15),
        )

        call_command("monthly_usage_service", "--run-once", "--month=2025-03")

        self.assertTrue(
            UsageQuantityMonthly.objects.filter(
                specific_part="3-1-7-702",
                energy_mode="制热",
                usage_month="2025-03",
            ).exists()
        )

    def test_monthly_usage_service_no_data_does_not_crash(self):
        """
        monthly_usage_service --run-once 在没有日用量数据时不崩溃（返回 skipped=True）
        """
        from django.core.management import call_command

        try:
            call_command("monthly_usage_service", "--run-once")
        except Exception as e:
            self.fail(f"monthly_usage_service --run-once 不应抛出异常: {e}")

    def test_monthly_usage_service_calculate_method_called(self):
        """
        直接调用 Command.calculate_monthly_usage()，验证其委托给
        MonthlyUsageCalculator.calculate_monthly_usage() 并返回结果字典
        """
        from api.management.commands.monthly_usage_service import Command

        # 预置日用量数据
        UsageQuantityDaily.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            initial_energy=500,
            final_energy=700,
            usage_quantity=200,
            time_period=date(2025, 4, 1),
        )

        cmd = Command()
        # 调用内部方法，不触发 schedule 循环
        cmd.calculate_monthly_usage(date(2025, 4, 1))

        self.assertTrue(
            UsageQuantityMonthly.objects.filter(
                specific_part="3-1-7-702",
                energy_mode="制冷",
                usage_month="2025-04",
            ).exists()
        )

    # ------------------------------------------------------------------
    # plc_data_clean_up_service
    # ------------------------------------------------------------------

    def test_plc_cleanup_service_once_deletes_old_data(self):
        """
        plc_data_clean_up_service --once 应删除超过指定天数的 PLCData 记录
        （使用 days=0 + mock 时间使记录立刻过期）
        """
        from django.core.management import call_command
        from unittest.mock import patch

        PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            value=100,
            usage_date=self.today,
        )
        self.assertEqual(PLCData.objects.count(), 1)

        # 将 plc_data_cleaner 模块中的 datetime.now() 前移 1 秒，使记录立即过期
        future_now = datetime.now() + timedelta(seconds=1)
        with patch("api.plc_data_cleaner.datetime") as mock_dt:
            mock_dt.now.return_value = future_now
            mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
            call_command("plc_data_clean_up_service", "--once", "--days=0")

        self.assertEqual(PLCData.objects.count(), 0)

    def test_plc_cleanup_service_once_no_data_does_not_crash(self):
        """
        plc_data_clean_up_service --once 在无数据时不崩溃
        """
        from django.core.management import call_command

        try:
            call_command("plc_data_clean_up_service", "--once", "--days=7")
        except Exception as e:
            self.fail(f"plc_data_clean_up_service --once 不应抛出异常: {e}")

    def test_plc_cleanup_service_days_parameter_respected(self):
        """
        --days 参数正确传递给 clean_old_plc_data：
        days=3650 时今天的数据不应被删除
        """
        from django.core.management import call_command

        PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            value=100,
            usage_date=self.today,
        )

        call_command("plc_data_clean_up_service", "--once", "--days=3650")

        # 保留天数很大，今天的记录不应被删除
        self.assertEqual(PLCData.objects.count(), 1)

    def test_plc_cleanup_command_run_cleanup_task_method(self):
        """
        直接调用 Command.run_cleanup_task()，验证 days 参数被正确传递
        给 clean_old_plc_data，且正常返回而不崩溃
        """
        from api.management.commands.plc_data_clean_up_service import Command

        PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制热",
            value=200,
            usage_date=self.today,
        )

        cmd = Command()
        # days=3650：保留时间很长，记录不被删除
        cmd.run_cleanup_task(days=3650)
        self.assertEqual(PLCData.objects.count(), 1)

    def test_daily_usage_service_calculate_method_called(self):
        """
        直接调用 Command.calculate_daily_usage()，验证其委托给
        DailyUsageCalculator.calculate_daily_usage() 并写入 DB
        """
        from api.management.commands.daily_usage_service import Command

        PLCData.objects.create(
            specific_part="3-1-7-702",
            building="3",
            unit="1",
            room_number="702",
            energy_mode="制冷",
            value=6000,
            usage_date=self.yesterday,
        )

        cmd = Command()
        cmd.calculate_daily_usage(self.yesterday)

        self.assertTrue(
            UsageQuantityDaily.objects.filter(
                specific_part="3-1-7-702",
                energy_mode="制冷",
                time_period=self.yesterday,
            ).exists()
        )
