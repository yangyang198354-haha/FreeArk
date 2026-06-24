"""
test_vision_service.py — api.vision_service 单元测试（v1.5.0 多模态提问）

覆盖 AC-MQ-*：
  AC-MQ-001-01（store_upload / get_upload 正常路径）
  AC-MQ-005-01（analyze_image 超时/重试/降级）
  AC-MQ-005-02（VLM 降级后只抛 VisionServiceError，不抛系统级异常）
  AC-MQ-005-03（TTL 超期 → ImageExpiredError）
  AC-MQ-007-02（存储容量上限 → StorageCapacityError）
  AC-MQ-008-02（analyze_image 日志中不含 base64 字符串）
  AC-MQ-009-01（单次调用超时保护；重试逻辑）
  AC-MQ-009-02（2 次均失败 → VisionServiceError）

测试命名规则：TC-UNIT-NNN
测试级别：UNIT（全部在 vision_service 模块内，无外部服务）

@module test_vision_service
@covers MOD-MQ-03 (vision_service)
@author sub_agent_test_engineer
"""

import asyncio
import unittest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

from api.vision_service import (
    ImageAccessDeniedError,
    ImageExpiredError,
    StorageCapacityError,
    VisionServiceError,
    _upload_store,
    _evict_expired_locked,
    check_capacity,
    delete_upload,
    get_upload,
    store_upload,
    analyze_image,
    _store_lock,
)
import api.vision_service as vs_module


# ── 测试数据 ────────────────────────────────────────────────────────────────────
SMALL_IMAGE = b'\xff\xd8\xff\xe0' + b'\x00' * 8 + b'\xff\xd9'  # 最小 JPEG
USER_A = 1
USER_B = 2


def _clear_store():
    """测试辅助：清空全局存储状态（防用例间污染）。"""
    with vs_module._store_lock:
        vs_module._upload_store.clear()
        vs_module._total_size = 0


# ── TC-UNIT-001 ~ TC-UNIT-005：store_upload ─────────────────────────────────────

class TestStoreUpload(unittest.TestCase):
    """TC-UNIT-001 ~ TC-UNIT-005：store_upload 接口单元测试。"""

    def setUp(self):
        _clear_store()

    def tearDown(self):
        _clear_store()

    def test_TC_UNIT_001_returns_uuid_format(self):
        """TC-UNIT-001 (AC-MQ-001-01): store_upload 成功返回 UUID4 格式字符串。"""
        upload_id = store_upload(SMALL_IMAGE, USER_A)
        self.assertIsInstance(upload_id, str)
        # UUID4 格式：8-4-4-4-12 十六进制字符
        import uuid
        try:
            parsed = uuid.UUID(upload_id, version=4)
        except ValueError:
            self.fail(f"upload_id={upload_id!r} 不是合法 UUID4")
        self.assertEqual(str(parsed), upload_id)

    def test_TC_UNIT_002_stored_entry_retrievable(self):
        """TC-UNIT-002 (AC-MQ-001-01): store_upload 后条目在存储中可取回。"""
        upload_id = store_upload(SMALL_IMAGE, USER_A)
        retrieved = get_upload(upload_id, USER_A)
        self.assertEqual(retrieved, SMALL_IMAGE)

    def test_TC_UNIT_003_raises_storage_capacity_error_when_full(self):
        """TC-UNIT-003 (AC-MQ-007-02): 总量超限时 raise StorageCapacityError。"""
        big_data = b'\x00' * (51 * 1024 * 1024)  # 51 MB
        with self.assertRaises(StorageCapacityError):
            store_upload(big_data, USER_A)

    def test_TC_UNIT_004_lazy_eviction_frees_space_before_capacity_check(self):
        """TC-UNIT-004 (AC-MQ-007-02): 惰性清理：先插入 TTL=0 条目，再 store_upload 时
        过期条目被清理、新存储成功。"""
        # 直接操作 _upload_store 注入一条已过期条目（模拟"存满"但实际已过期）
        fake_id = "deadbeef-dead-beef-dead-deadbeefcafe"
        # 假设接近上限但不超：45MB 已占用
        big_expired_bytes = b'\x01' * (45 * 1024 * 1024)
        with vs_module._store_lock:
            vs_module._upload_store[fake_id] = {
                "user_id": USER_A,
                "bytes": big_expired_bytes,
                "expire_at": datetime.utcnow() - timedelta(seconds=1),
                "size": len(big_expired_bytes),
            }
            vs_module._total_size += len(big_expired_bytes)

        # 此时直接 store 10MB 会超限（45+10=55 > 50）
        # 但 store_upload 先做惰性清理，应能成功
        medium_data = b'\x02' * (10 * 1024 * 1024)  # 10MB
        upload_id = store_upload(medium_data, USER_A)
        self.assertIsNotNone(upload_id)
        # 过期条目应已被清理
        with vs_module._store_lock:
            self.assertNotIn(fake_id, vs_module._upload_store)

    def test_TC_UNIT_005_total_size_updated_correctly(self):
        """TC-UNIT-005 (AC-MQ-001-01): store_upload 后 _total_size 正确增加。"""
        before = vs_module._total_size
        store_upload(SMALL_IMAGE, USER_A)
        after = vs_module._total_size
        self.assertEqual(after - before, len(SMALL_IMAGE))


# ── TC-UNIT-006 ~ TC-UNIT-011：get_upload ───────────────────────────────────────

class TestGetUpload(unittest.TestCase):
    """TC-UNIT-006 ~ TC-UNIT-011：get_upload 接口单元测试。"""

    def setUp(self):
        _clear_store()

    def tearDown(self):
        _clear_store()

    def test_TC_UNIT_006_returns_bytes_for_valid_id(self):
        """TC-UNIT-006 (AC-MQ-001-01): 合法 upload_id 返回正确 bytes。"""
        uid = store_upload(SMALL_IMAGE, USER_A)
        result = get_upload(uid, USER_A)
        self.assertEqual(result, SMALL_IMAGE)

    def test_TC_UNIT_007_nonexistent_id_raises_image_expired(self):
        """TC-UNIT-007 (AC-MQ-005-03): 不存在的 upload_id → raise ImageExpiredError。"""
        with self.assertRaises(ImageExpiredError):
            get_upload("00000000-0000-4000-a000-000000000000", USER_A)

    def test_TC_UNIT_008_expired_ttl_raises_image_expired(self):
        """TC-UNIT-008 (AC-MQ-005-03): TTL 超期（expire_at 在过去） → raise ImageExpiredError。"""
        uid = store_upload(SMALL_IMAGE, USER_A)
        # 手动修改 expire_at 为过去
        with vs_module._store_lock:
            vs_module._upload_store[uid]["expire_at"] = datetime.utcnow() - timedelta(seconds=1)

        with self.assertRaises(ImageExpiredError):
            get_upload(uid, USER_A)

    def test_TC_UNIT_009_expired_entry_evicted_from_store(self):
        """TC-UNIT-009 (AC-MQ-005-03): TTL 超期条目被惰性清理，后续不再存在。"""
        uid = store_upload(SMALL_IMAGE, USER_A)
        with vs_module._store_lock:
            vs_module._upload_store[uid]["expire_at"] = datetime.utcnow() - timedelta(seconds=1)

        with self.assertRaises(ImageExpiredError):
            get_upload(uid, USER_A)

        with vs_module._store_lock:
            self.assertNotIn(uid, vs_module._upload_store)

    def test_TC_UNIT_010_wrong_user_id_raises_access_denied(self):
        """TC-UNIT-010 (AC-MQ-010-02): user_id 不匹配 → raise ImageAccessDeniedError。"""
        uid = store_upload(SMALL_IMAGE, USER_A)
        with self.assertRaises(ImageAccessDeniedError):
            get_upload(uid, USER_B)

    def test_TC_UNIT_011_same_id_retrievable_multiple_times(self):
        """TC-UNIT-011 (AC-MQ-001-01): 同一 upload_id 在 TTL 内可多次取回（不删除）。"""
        uid = store_upload(SMALL_IMAGE, USER_A)
        for _ in range(3):
            result = get_upload(uid, USER_A)
            self.assertEqual(result, SMALL_IMAGE)


# ── TC-UNIT-012 ~ TC-UNIT-014：delete_upload ─────────────────────────────────────

class TestDeleteUpload(unittest.TestCase):
    """TC-UNIT-012 ~ TC-UNIT-014：delete_upload 接口单元测试。"""

    def setUp(self):
        _clear_store()

    def tearDown(self):
        _clear_store()

    def test_TC_UNIT_012_delete_reduces_total_size(self):
        """TC-UNIT-012 (AC-MQ-001-01): 删除后 _total_size 正确减少。"""
        uid = store_upload(SMALL_IMAGE, USER_A)
        size_after_store = vs_module._total_size
        delete_upload(uid)
        self.assertEqual(vs_module._total_size, size_after_store - len(SMALL_IMAGE))

    def test_TC_UNIT_013_delete_removes_from_store(self):
        """TC-UNIT-013 (AC-MQ-001-01): 删除后 upload_id 不再可取回。"""
        uid = store_upload(SMALL_IMAGE, USER_A)
        delete_upload(uid)
        with self.assertRaises(ImageExpiredError):
            get_upload(uid, USER_A)

    def test_TC_UNIT_014_delete_nonexistent_id_no_exception(self):
        """TC-UNIT-014 (AC-MQ-010-02): 删除不存在的 id 不抛异常（静默忽略）。"""
        try:
            delete_upload("nonexistent-id-that-does-not-exist")
        except Exception as exc:
            self.fail(f"delete_upload 对不存在的 id 不应抛异常，实际抛: {exc}")


# ── TC-UNIT-015 ~ TC-UNIT-018：check_capacity ────────────────────────────────────

class TestCheckCapacity(unittest.TestCase):
    """TC-UNIT-015 ~ TC-UNIT-018：check_capacity 接口单元测试。"""

    def setUp(self):
        _clear_store()

    def tearDown(self):
        _clear_store()

    def test_TC_UNIT_015_empty_store_returns_true(self):
        """TC-UNIT-015 (AC-MQ-007-02): 空存储 → check_capacity 返回 True。"""
        self.assertTrue(check_capacity())

    def test_TC_UNIT_016_full_store_returns_false(self):
        """TC-UNIT-016 (AC-MQ-007-02): 手动填满 _total_size → check_capacity 返回 False。"""
        # 直接设置 _total_size 为上限
        with vs_module._store_lock:
            vs_module._total_size = 50 * 1024 * 1024  # 50 MB = 上限
        self.assertFalse(check_capacity())

    def test_TC_UNIT_017_eviction_frees_capacity(self):
        """TC-UNIT-017 (AC-MQ-007-02): 清理过期后空间释放，check_capacity 恢复 True。"""
        fake_id = "expired-cap-test-0000-000000000000"
        big_data = b'\x00' * (49 * 1024 * 1024)  # 49MB，不触发 StorageCapacityError
        with vs_module._store_lock:
            vs_module._upload_store[fake_id] = {
                "user_id": USER_A,
                "bytes": big_data,
                "expire_at": datetime.utcnow() - timedelta(seconds=1),
                "size": len(big_data),
            }
            vs_module._total_size += len(big_data)

        # 此时接近满容（49MB），直接设满
        with vs_module._store_lock:
            vs_module._total_size = 50 * 1024 * 1024
        # 调用 check_capacity 应触发惰性清理并返回 True（过期条目清掉后空间释放）
        # 注：check_capacity 先清理再判断
        result = check_capacity()
        self.assertTrue(result)

    def test_TC_UNIT_018_check_capacity_triggers_eviction(self):
        """TC-UNIT-018 (AC-MQ-007-02): check_capacity 会清理过期条目（副作用验证）。"""
        fake_id = "test-evict-on-check-0000000000000"
        with vs_module._store_lock:
            vs_module._upload_store[fake_id] = {
                "user_id": USER_A,
                "bytes": b'\x00',
                "expire_at": datetime.utcnow() - timedelta(seconds=1),
                "size": 1,
            }
            vs_module._total_size += 1

        check_capacity()
        with vs_module._store_lock:
            self.assertNotIn(fake_id, vs_module._upload_store)


# ── TC-UNIT-019 ~ TC-UNIT-025：analyze_image（异步）──────────────────────────────

class TestAnalyzeImage(unittest.IsolatedAsyncioTestCase):
    """TC-UNIT-019 ~ TC-UNIT-025：analyze_image VLM 调用单元测试（异步）。

    全部 mock AsyncOpenAI，测试不发真实网络请求。
    """

    def setUp(self):
        _clear_store()

    def tearDown(self):
        _clear_store()

    def _make_mock_response(self, content: str):
        """构造 mock 的 openai ChatCompletion 响应对象。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message = MagicMock()
        mock_response.choices[0].message.content = content
        return mock_response

    async def test_TC_UNIT_019_success_returns_description(self):
        """TC-UNIT-019 (AC-MQ-001-01): Mock AsyncOpenAI 成功 → 返回 description 字符串。

        vision_service.py 在函数内部惰性 import openai.AsyncOpenAI，
        需 patch 'openai.AsyncOpenAI'（模块级）以拦截该惰性 import。
        """
        mock_resp = self._make_mock_response("这是一台三恒空调，型号 XYZ-3000。")

        with patch("openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            MockAsyncOpenAI.return_value = mock_client

            result = await analyze_image(SMALL_IMAGE, "这是什么型号？")

        self.assertEqual(result, "这是一台三恒空调，型号 XYZ-3000。")

    async def test_TC_UNIT_020_retry_on_timeout_succeeds(self):
        """TC-UNIT-020 (AC-MQ-009-01): 首次 TimeoutError，第二次成功 → 返回 description。"""
        mock_resp = self._make_mock_response("空调型号：EC-2025。")

        call_count = 0

        async def _fake_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError("模拟超时")
            return mock_resp

        with patch("openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = _fake_create
            MockAsyncOpenAI.return_value = mock_client
            # 覆盖 asyncio.sleep 避免实际等待
            with patch("api.vision_service.asyncio.sleep", new_callable=AsyncMock):
                result = await analyze_image(SMALL_IMAGE, "分析图片")

        self.assertEqual(result, "空调型号：EC-2025。")
        self.assertEqual(call_count, 2)

    async def test_TC_UNIT_021_two_timeouts_raise_vision_service_error(self):
        """TC-UNIT-021 (AC-MQ-009-02): 两次 TimeoutError → raise VisionServiceError。"""
        async def _always_timeout(**kwargs):
            raise asyncio.TimeoutError("持续超时")

        with patch("openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = _always_timeout
            MockAsyncOpenAI.return_value = mock_client
            with patch("api.vision_service.asyncio.sleep", new_callable=AsyncMock):
                with self.assertRaises(VisionServiceError):
                    await analyze_image(SMALL_IMAGE, "")

    async def test_TC_UNIT_022_4xx_raises_immediately_no_retry(self):
        """TC-UNIT-022 (AC-MQ-005-02): 4xx HTTP 错误 → 直接 raise VisionServiceError，不重试。"""
        call_count = 0

        async def _fake_4xx(**kwargs):
            nonlocal call_count
            call_count += 1
            exc = Exception("Bad Request")
            exc.status_code = 400
            raise exc

        with patch("openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = _fake_4xx
            MockAsyncOpenAI.return_value = mock_client

            with self.assertRaises(VisionServiceError):
                await analyze_image(SMALL_IMAGE, "")

        self.assertEqual(call_count, 1, "4xx 错误不应重试，应只调用 1 次")

    async def test_TC_UNIT_023_empty_vlm_response_returns_placeholder(self):
        """TC-UNIT-023 (AC-MQ-001-01): VLM 返回空字符串 → 返回占位文案，不抛异常。"""
        mock_resp = self._make_mock_response("")

        with patch("openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            MockAsyncOpenAI.return_value = mock_client

            result = await analyze_image(SMALL_IMAGE, "分析")

        self.assertIsInstance(result, str)
        self.assertTrue(len(result) > 0, "空 VLM 响应应返回占位文案，不应为空")

    async def test_TC_UNIT_024_no_base64_in_logs(self):
        """TC-UNIT-024 (AC-MQ-008-02): analyze_image 日志中不含 base64 字符串。

        捕获 api.vision_service logger 的所有输出，检查无 base64 字符串特征。
        """
        import base64
        import logging

        mock_resp = self._make_mock_response("图片分析完成")

        with patch("openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)
            MockAsyncOpenAI.return_value = mock_client

            log_records = []

            class CaptureHandler(logging.Handler):
                def emit(self, record):
                    log_records.append(self.format(record))

            handler = CaptureHandler()
            vs_logger = logging.getLogger("api.vision_service")
            vs_logger.addHandler(handler)
            try:
                await analyze_image(SMALL_IMAGE, "请分析")
            finally:
                vs_logger.removeHandler(handler)

        # 计算 base64 字符串
        b64 = base64.b64encode(SMALL_IMAGE).decode("utf-8")
        for record in log_records:
            self.assertNotIn(
                b64, record,
                f"日志中不应包含 base64 字符串，但发现于: {record[:100]}"
            )

    async def test_TC_UNIT_025_non_4xx_error_retries_then_fails(self):
        """TC-UNIT-025 (AC-MQ-009-02): 非 4xx 异常（如连接错误）触发重试，两次均失败则 raise VisionServiceError。"""
        call_count = 0

        async def _fake_connection_err(**kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("连接失败")

        with patch("openai.AsyncOpenAI") as MockAsyncOpenAI:
            mock_client = MagicMock()
            mock_client.chat = MagicMock()
            mock_client.chat.completions = MagicMock()
            mock_client.chat.completions.create = _fake_connection_err
            MockAsyncOpenAI.return_value = mock_client
            with patch("api.vision_service.asyncio.sleep", new_callable=AsyncMock):
                with self.assertRaises(VisionServiceError):
                    await analyze_image(SMALL_IMAGE, "")

        # 应该尝试 2 次（1 次原始 + 1 次重试，max_retries 默认 1）
        self.assertEqual(call_count, 2, f"非 4xx 应重试 1 次，共调用 2 次，实际: {call_count}")


if __name__ == "__main__":
    unittest.main()
