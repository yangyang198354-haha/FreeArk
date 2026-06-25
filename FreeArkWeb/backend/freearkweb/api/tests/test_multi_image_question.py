"""
test_multi_image_question.py — v1.9.0 多图提问（Multi-Image Question）扩展单元/集成测试

覆盖 AC-MI-*（v1.9.0 新增验收标准）：
  AC-MI-001：analyze_images_batch 批量分析（全成功、部分失败、全失败、空列表）
  AC-MI-002：analyze_images_batch 90s 整体超时保护
  AC-MI-003：on_progress 回调逐图触发
  AC-MI-004：consumers.receive() ADR-MI-003 三路解析（image_upload_ids 优先）
  AC-MI-005：IMAGE_TOO_MANY 超限（>5 张）
  AC-MI-006：多图无文字时注入默认文案「请帮我分析这些图片」
  AC-MI-007：单图无文字默认文案不变「请帮我分析这张图片」
  AC-MI-008：adapter.stream_chat upload_id 向后兼容（包装为单元素列表）
  AC-MI-009：adapter.stream_chat upload_ids 多图 → 调用 analyze_images_batch
  AC-MI-010：_pump 新 kind vision_progress 转发 WS 帧
  AC-MI-011：_pump 新 kind image_analysis_partial 发送 IMAGE_ANALYSIS_PARTIAL 错误帧

测试命名规则：
  TC-UNIT-MI-NNN  单元测试（单个函数/类，无跨模块依赖）
  TC-INT-MI-NNN   集成测试（跨模块 consumers + vision_service + adapter mock）

@module test_multi_image_question
@covers MOD-MI-03 (vision_service.analyze_images_batch),
        MOD-MI-04 (consumers 多图扩展),
        MOD-MI-05 (adapter 多图扩展)
@since v1.9.0
"""

from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

# ── PIL 可用性检测（与 test_vision_service.py 保持一致）────────────────────────
try:
    import PIL  # noqa: F401
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

import api.vision_service as vs_module
from api.vision_service import (
    VisionServiceError,
    ImageExpiredError,
    ImageAccessDeniedError,
    analyze_images_batch,
    store_upload,
)

# ── 共用测试数据 ──────────────────────────────────────────────────────────────
SMALL_IMAGE = b'\xff\xd8\xff\xe0' + b'\x00' * 8 + b'\xff\xd9'
USER_A = 1

VALID_UUID_1 = "11111111-1111-4111-8111-111111111111"
VALID_UUID_2 = "22222222-2222-4222-8222-222222222222"
VALID_UUID_3 = "33333333-3333-4333-8333-333333333333"
INVALID_UUID = "not-a-valid-uuid"


def _clear_store():
    with vs_module._store_lock:
        vs_module._upload_store.clear()
        vs_module._total_size = 0


def _inject_upload(uid: str, image_bytes: bytes = SMALL_IMAGE, user_id: int = USER_A):
    """直接注入 upload 条目（绕过 store_upload，避免容量限制干扰）。"""
    from datetime import datetime, timedelta
    with vs_module._store_lock:
        vs_module._upload_store[uid] = {
            "user_id": user_id,
            "bytes": image_bytes,
            "expire_at": datetime.utcnow() + timedelta(seconds=600),
            "size": len(image_bytes),
        }
        vs_module._total_size += len(image_bytes)


# ══════════════════════════════════════════════════════════════════════════════
# TC-UNIT-MI-001 ~ TC-UNIT-MI-006 : analyze_images_batch 单元测试
# ══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeImagesBatch(unittest.IsolatedAsyncioTestCase):
    """analyze_images_batch 单元测试（异步）。全部 mock analyze_image，不发真实网络请求。"""

    def setUp(self):
        _clear_store()

    def tearDown(self):
        _clear_store()

    # ── TC-UNIT-MI-001：2 图全成功 ──────────────────────────────────────────

    async def test_TC_UNIT_MI_001_two_images_success_returns_list_of_str(self):
        """TC-UNIT-MI-001 (AC-MI-001): 2 张图片均成功 → 返回 list[str]，长度 2，顺序对应。"""
        desc1 = "图片1：空调铭牌，型号 EC-2025"
        desc2 = "图片2：控制面板，显示温度 24°C"

        call_count = 0

        async def _mock_analyze(image_bytes, user_text):
            nonlocal call_count
            call_count += 1
            if image_bytes == b"img1":
                return desc1
            return desc2

        with patch("api.vision_service.analyze_image", side_effect=_mock_analyze):
            results = await analyze_images_batch([b"img1", b"img2"], "分析这些图片")

        self.assertEqual(len(results), 2)
        self.assertIsInstance(results[0], str)
        self.assertIsInstance(results[1], str)
        self.assertEqual(results[0], desc1)
        self.assertEqual(results[1], desc2)
        self.assertEqual(call_count, 2, "两张图片应各调用一次 analyze_image")

    # ── TC-UNIT-MI-002：首图失败（返回 None），第二图成功 ────────────────────

    async def test_TC_UNIT_MI_002_partial_failure_first_none_second_str(self):
        """TC-UNIT-MI-002 (AC-MI-001): 首图抛异常 → results[0]=None；第二图成功 → results[1]=str。"""
        desc2 = "第二张图片正常分析完成"

        async def _mock_analyze(image_bytes, user_text):
            if image_bytes == b"img1":
                raise VisionServiceError("VLM 调用失败")
            return desc2

        with patch("api.vision_service.analyze_image", side_effect=_mock_analyze):
            results = await analyze_images_batch([b"img1", b"img2"], "分析")

        self.assertEqual(len(results), 2)
        self.assertIsNone(results[0], "首图失败应返回 None")
        self.assertEqual(results[1], desc2, "第二图成功应返回描述字符串")

    # ── TC-UNIT-MI-003：全部失败 → [None, None] ──────────────────────────────

    async def test_TC_UNIT_MI_003_all_failure_returns_all_none(self):
        """TC-UNIT-MI-003 (AC-MI-001): 所有图片均抛异常 → 返回全 None 列表。"""
        async def _always_fail(image_bytes, user_text):
            raise VisionServiceError("VLM 全部失败")

        with patch("api.vision_service.analyze_image", side_effect=_always_fail):
            results = await analyze_images_batch([b"img1", b"img2", b"img3"], "")

        self.assertEqual(results, [None, None, None])

    # ── TC-UNIT-MI-004：空列表 → 立即返回空列表 ─────────────────────────────

    async def test_TC_UNIT_MI_004_empty_list_returns_empty(self):
        """TC-UNIT-MI-004 (AC-MI-001): 空输入列表 → 返回空列表，不调用 analyze_image。"""
        with patch("api.vision_service.analyze_image") as mock_analyze:
            results = await analyze_images_batch([], "任意文字")

        self.assertEqual(results, [])
        mock_analyze.assert_not_called()

    # ── TC-UNIT-MI-005：整体 90s 超时 → 抛 TimeoutError ────────────────────

    async def test_TC_UNIT_MI_005_batch_timeout_raises_timeout_error(self):
        """TC-UNIT-MI-005 (AC-MI-002): asyncio.timeout 超时 → 抛 asyncio.TimeoutError。

        mock asyncio.timeout 令其立即触发超时，验证 analyze_images_batch 传播该异常。
        """
        async def _slow_analyze(image_bytes, user_text):
            # 模拟极慢的 VLM（实际上 timeout 会在 gather 之前触发）
            await asyncio.sleep(1000)
            return "不会到这里"

        # patch _get_vision_config 使 batch_timeout=0（立即超时）
        original_cfg = vs_module._get_vision_config

        def _cfg_with_zero_timeout():
            cfg = original_cfg()
            cfg["batch_timeout"] = 0
            return cfg

        with patch("api.vision_service._get_vision_config", side_effect=_cfg_with_zero_timeout):
            with patch("api.vision_service.analyze_image", side_effect=_slow_analyze):
                with self.assertRaises(asyncio.TimeoutError):
                    await analyze_images_batch([b"img1"], "测试超时")

    # ── TC-UNIT-MI-006：on_progress 回调逐图调用 ─────────────────────────────

    async def test_TC_UNIT_MI_006_on_progress_called_per_image(self):
        """TC-UNIT-MI-006 (AC-MI-003): on_progress 对每张图调用一次，参数为 (index, total)。"""
        async def _mock_analyze(image_bytes, user_text):
            return "描述"

        progress_calls = []

        async def _on_progress(index: int, total: int):
            progress_calls.append((index, total))

        with patch("api.vision_service.analyze_image", side_effect=_mock_analyze):
            results = await analyze_images_batch(
                [b"img1", b"img2", b"img3"], "分析", on_progress=_on_progress
            )

        self.assertEqual(len(results), 3)
        self.assertEqual(len(progress_calls), 3, "3 张图应调用 on_progress 3 次")
        # 验证参数：每次调用 total=3，index 从 0 到 2
        for i, (idx, total) in enumerate(progress_calls):
            self.assertEqual(total, 3, f"第{i}次回调 total 应为 3")
        indices = [c[0] for c in progress_calls]
        self.assertEqual(set(indices), {0, 1, 2}, "索引应覆盖 0,1,2（并发，顺序不保证）")

    # ── TC-UNIT-MI-007：on_progress 回调失败不影响 VLM 调用 ──────────────────

    async def test_TC_UNIT_MI_007_on_progress_failure_does_not_abort_batch(self):
        """TC-UNIT-MI-007 (AC-MI-003): on_progress 抛异常 → 静默忽略，VLM 调用正常完成。"""
        desc = "正常分析结果"

        async def _mock_analyze(image_bytes, user_text):
            return desc

        async def _bad_progress(index: int, total: int):
            raise RuntimeError("进度回调故意失败")

        with patch("api.vision_service.analyze_image", side_effect=_mock_analyze):
            results = await analyze_images_batch(
                [b"img1"], "分析", on_progress=_bad_progress
            )

        self.assertEqual(results, [desc], "on_progress 失败不应影响结果")

    # ── TC-UNIT-MI-008：结果顺序与输入顺序一致 ──────────────────────────────

    async def test_TC_UNIT_MI_008_result_order_matches_input_order(self):
        """TC-UNIT-MI-008 (AC-MI-001 REQ-MI-004): 结果列表顺序与输入一致（即使并发执行）。"""
        descriptions = [f"第{i}张图片的描述" for i in range(5)]

        call_map = {bytes([i]): descriptions[i] for i in range(5)}

        async def _mock_analyze(image_bytes, user_text):
            # 按字节值识别图片身份
            return call_map[image_bytes]

        image_list = [bytes([i]) for i in range(5)]

        with patch("api.vision_service.analyze_image", side_effect=_mock_analyze):
            results = await analyze_images_batch(image_list, "分析")

        self.assertEqual(results, descriptions, "结果顺序应与输入完全一致")


# ══════════════════════════════════════════════════════════════════════════════
# TC-UNIT-MI-010 ~ TC-UNIT-MI-016 : consumers.receive() 路由逻辑单元测试
# ══════════════════════════════════════════════════════════════════════════════

class TestConsumersReceiveRouting(unittest.IsolatedAsyncioTestCase):
    """
    consumers.receive() ADR-MI-003 三路解析逻辑单元测试。

    直接测试 ChatConsumer._is_valid_uuid（模块函数）和 receive() 的分支逻辑，
    通过 mock WS send() 和 _handle_chat() 隔离外部依赖。
    """

    def setUp(self):
        _clear_store()

    def tearDown(self):
        _clear_store()

    # ── TC-UNIT-MI-010：_is_valid_uuid 函数 ──────────────────────────────────

    def test_TC_UNIT_MI_010_is_valid_uuid_accepts_valid_uuid4(self):
        """TC-UNIT-MI-010 (AC-MI-004): _is_valid_uuid 对合法 UUID4 返回 True。"""
        from api.consumers import _is_valid_uuid
        self.assertTrue(_is_valid_uuid(VALID_UUID_1))
        self.assertTrue(_is_valid_uuid(VALID_UUID_2))

    def test_TC_UNIT_MI_010b_is_valid_uuid_rejects_invalid_strings(self):
        """TC-UNIT-MI-010b (AC-MI-004): _is_valid_uuid 对非 UUID 字符串返回 False。"""
        from api.consumers import _is_valid_uuid
        self.assertFalse(_is_valid_uuid("not-a-uuid"))
        self.assertFalse(_is_valid_uuid(""))
        self.assertFalse(_is_valid_uuid("12345678"))
        self.assertFalse(_is_valid_uuid("00000000-0000-0000-0000-000000000000"))  # version 0

    # ── TC-UNIT-MI-011：image_upload_ids 列表优先于 image_upload_id 字符串 ──

    async def test_TC_UNIT_MI_011_upload_ids_list_takes_priority_over_string(self):
        """TC-UNIT-MI-011 (AC-MI-004 ADR-MI-003): image_upload_ids 非空列表优先于 image_upload_id 字符串。

        构造一个 ChatConsumer 实例，mock _handle_chat 捕获 upload_ids 参数。
        """
        from api.consumers import ChatConsumer

        consumer = ChatConsumer.__new__(ChatConsumer)
        # 最小化初始化
        consumer._is_streaming = False
        consumer._awaiting_confirm = False
        consumer.channel_layer = None

        handle_chat_calls = []

        async def _mock_handle_chat(user_message, upload_ids=None):
            handle_chat_calls.append(upload_ids)

        consumer._handle_chat = _mock_handle_chat

        sent_messages = []

        async def _mock_send(text_data):
            sent_messages.append(json.loads(text_data))

        consumer.send = _mock_send

        # image_upload_ids 列表含 2 个有效 UUID
        text_data = json.dumps({
            "type": "chat_message",
            "message": "分析图片",
            "image_upload_ids": [VALID_UUID_1, VALID_UUID_2],
            "image_upload_id": "should-be-ignored",  # 旧字段，应被忽略
        })

        await consumer.receive(text_data=text_data)

        self.assertEqual(len(handle_chat_calls), 1)
        self.assertEqual(handle_chat_calls[0], [VALID_UUID_1, VALID_UUID_2],
                         "image_upload_ids 列表应优先于 image_upload_id 字符串")

    # ── TC-UNIT-MI-012：旧 image_upload_id 字符串包装为单元素列表 ─────────────

    async def test_TC_UNIT_MI_012_old_upload_id_string_wrapped_as_single_list(self):
        """TC-UNIT-MI-012 (AC-MI-008 向后兼容): 仅 image_upload_id（字符串）时，upload_ids=[uid]。"""
        from api.consumers import ChatConsumer

        consumer = ChatConsumer.__new__(ChatConsumer)
        consumer._is_streaming = False
        consumer._awaiting_confirm = False
        consumer.channel_layer = None

        handle_chat_calls = []

        async def _mock_handle_chat(user_message, upload_ids=None):
            handle_chat_calls.append(upload_ids)

        consumer._handle_chat = _mock_handle_chat

        async def _mock_send(text_data):
            pass

        consumer.send = _mock_send

        text_data = json.dumps({
            "type": "chat_message",
            "message": "分析图片",
            "image_upload_id": VALID_UUID_1,
        })

        await consumer.receive(text_data=text_data)

        self.assertEqual(len(handle_chat_calls), 1)
        self.assertEqual(handle_chat_calls[0], [VALID_UUID_1],
                         "旧字段 image_upload_id 应被包装为 [uuid]")

    # ── TC-UNIT-MI-013：IMAGE_TOO_MANY 超限（>5 张）────────────────────────────

    async def test_TC_UNIT_MI_013_image_too_many_when_more_than_5(self):
        """TC-UNIT-MI-013 (AC-MI-005 REQ-MI-002): 6 张图 → 发送 IMAGE_TOO_MANY 错误，不进 _handle_chat。"""
        from api.consumers import ChatConsumer

        consumer = ChatConsumer.__new__(ChatConsumer)
        consumer._is_streaming = False
        consumer._awaiting_confirm = False
        consumer.channel_layer = None

        handle_chat_called = []

        async def _mock_handle_chat(user_message, upload_ids=None):
            handle_chat_called.append(True)

        consumer._handle_chat = _mock_handle_chat

        sent_messages = []

        async def _mock_send(text_data):
            sent_messages.append(json.loads(text_data))

        consumer.send = _mock_send

        # 6 个 UUID
        uuids_6 = [
            f"0000000{i}-0000-4000-8000-000000000000" for i in range(1, 7)
        ]
        text_data = json.dumps({
            "type": "chat_message",
            "message": "分析",
            "image_upload_ids": uuids_6,
        })

        await consumer.receive(text_data=text_data)

        self.assertEqual(len(handle_chat_called), 0, "_handle_chat 不应被调用")
        self.assertTrue(len(sent_messages) > 0, "应发送错误帧")
        error_msg = sent_messages[0]
        self.assertEqual(error_msg.get("type"), "error")
        self.assertEqual(error_msg.get("code"), "IMAGE_TOO_MANY")

    # ── TC-UNIT-MI-014：invalid UUID in list → IMAGE_INVALID ─────────────────

    async def test_TC_UNIT_MI_014_invalid_uuid_in_list_sends_image_invalid(self):
        """TC-UNIT-MI-014 (AC-MI-004): 列表中含非 UUID 字符串 → IMAGE_INVALID 错误帧。"""
        from api.consumers import ChatConsumer

        consumer = ChatConsumer.__new__(ChatConsumer)
        consumer._is_streaming = False
        consumer._awaiting_confirm = False
        consumer.channel_layer = None

        handle_chat_called = []

        async def _mock_handle_chat(user_message, upload_ids=None):
            handle_chat_called.append(True)

        consumer._handle_chat = _mock_handle_chat

        sent_messages = []

        async def _mock_send(text_data):
            sent_messages.append(json.loads(text_data))

        consumer.send = _mock_send

        text_data = json.dumps({
            "type": "chat_message",
            "message": "分析",
            "image_upload_ids": [VALID_UUID_1, INVALID_UUID],
        })

        await consumer.receive(text_data=text_data)

        self.assertEqual(len(handle_chat_called), 0)
        self.assertTrue(len(sent_messages) > 0)
        error_msg = sent_messages[0]
        self.assertEqual(error_msg.get("code"), "IMAGE_INVALID")

    # ── TC-UNIT-MI-015：空列表视为无图纯文字路径 ─────────────────────────────

    async def test_TC_UNIT_MI_015_empty_list_treated_as_no_image(self):
        """TC-UNIT-MI-015 (AC-MI-004): image_upload_ids=[] 视为无图路径，upload_ids=None。"""
        from api.consumers import ChatConsumer

        consumer = ChatConsumer.__new__(ChatConsumer)
        consumer._is_streaming = False
        consumer._awaiting_confirm = False
        consumer.channel_layer = None

        handle_chat_calls = []

        async def _mock_handle_chat(user_message, upload_ids=None):
            handle_chat_calls.append({"message": user_message, "upload_ids": upload_ids})

        consumer._handle_chat = _mock_handle_chat

        async def _mock_send(text_data):
            pass

        consumer.send = _mock_send

        text_data = json.dumps({
            "type": "chat_message",
            "message": "纯文字消息",
            "image_upload_ids": [],  # 空列表
        })

        await consumer.receive(text_data=text_data)

        self.assertEqual(len(handle_chat_calls), 1)
        self.assertIsNone(handle_chat_calls[0]["upload_ids"],
                          "空列表应使 upload_ids=None（纯文字路径）")

    # ── TC-UNIT-MI-016：多图无文字 → 默认文案「请帮我分析这些图片」 ───────────

    async def test_TC_UNIT_MI_016_multi_image_no_text_injects_default_text(self):
        """TC-UNIT-MI-016 (AC-MI-006 OQ-MI-004): 2 张图 + 无文字 → 注入「请帮我分析这些图片」。"""
        from api.consumers import ChatConsumer

        consumer = ChatConsumer.__new__(ChatConsumer)
        consumer._is_streaming = False
        consumer._awaiting_confirm = False
        consumer.channel_layer = None

        handle_chat_calls = []

        async def _mock_handle_chat(user_message, upload_ids=None):
            handle_chat_calls.append({"message": user_message, "upload_ids": upload_ids})

        consumer._handle_chat = _mock_handle_chat

        async def _mock_send(text_data):
            pass

        consumer.send = _mock_send

        text_data = json.dumps({
            "type": "chat_message",
            "message": "",  # 无文字
            "image_upload_ids": [VALID_UUID_1, VALID_UUID_2],
        })

        await consumer.receive(text_data=text_data)

        self.assertEqual(len(handle_chat_calls), 1)
        self.assertIn("请帮我分析这些图片", handle_chat_calls[0]["message"],
                      "多图无文字时应注入多图默认文案")

    # ── TC-UNIT-MI-017：单图无文字 → 默认文案不变「请帮我分析这张图片」 ────────

    async def test_TC_UNIT_MI_017_single_image_no_text_keeps_original_default(self):
        """TC-UNIT-MI-017 (AC-MI-007 OQ-MI-004): 单图 + 无文字 → 注入「请帮我分析这张图片」（不变）。"""
        from api.consumers import ChatConsumer

        consumer = ChatConsumer.__new__(ChatConsumer)
        consumer._is_streaming = False
        consumer._awaiting_confirm = False
        consumer.channel_layer = None

        handle_chat_calls = []

        async def _mock_handle_chat(user_message, upload_ids=None):
            handle_chat_calls.append({"message": user_message, "upload_ids": upload_ids})

        consumer._handle_chat = _mock_handle_chat

        async def _mock_send(text_data):
            pass

        consumer.send = _mock_send

        text_data = json.dumps({
            "type": "chat_message",
            "message": "",  # 无文字
            "image_upload_id": VALID_UUID_1,  # 单图，使用旧字段
        })

        await consumer.receive(text_data=text_data)

        self.assertEqual(len(handle_chat_calls), 1)
        self.assertIn("请帮我分析这张图片", handle_chat_calls[0]["message"],
                      "单图无文字时应注入单图默认文案（不变）")
        self.assertNotIn("这些图片", handle_chat_calls[0]["message"],
                         "单图不应注入多图文案")


# ══════════════════════════════════════════════════════════════════════════════
# TC-UNIT-MI-020 ~ TC-UNIT-MI-025 : adapter.stream_chat 向后兼容与多图路径
# ══════════════════════════════════════════════════════════════════════════════

class TestAdapterStreamChatMultiImage(unittest.IsolatedAsyncioTestCase):
    """LangGraphAdapter.stream_chat 多图路径单元测试。

    mock _get_orch 和 vision_service，仅测试 adapter 内的分支逻辑。
    """

    def setUp(self):
        _clear_store()

    def tearDown(self):
        _clear_store()

    def _make_orch_mock(self):
        """构造最小化 orchestrator mock。"""
        orch = MagicMock()
        orch._cfg.return_value = {"configurable": {"thread_id": "test-session"}}

        # _drive 默认产出一条 content token 然后结束
        async def _mock_drive(*args, **kwargs):
            yield ("content", "模拟回复内容")

        orch.graph = MagicMock()
        return orch

    # ── TC-UNIT-MI-020：upload_id（旧单数参数）向后兼容，自动包装为列表 ────────

    async def test_TC_UNIT_MI_020_upload_id_single_param_wrapped_as_list(self):
        """TC-UNIT-MI-020 (AC-MI-008): upload_id='uuid' → 内部包装为 upload_ids=['uuid']，
        后续 VLM 路径以单元素列表运行。"""
        _inject_upload(VALID_UUID_1)

        analyze_batch_calls = []

        async def _mock_batch(image_bytes_list, user_text, on_progress=None):
            analyze_batch_calls.append(image_bytes_list)
            return ["分析结果"]

        with patch("api.langgraph_chat.adapter._get_orch") as mock_get_orch:
            orch = self._make_orch_mock()

            # _drive 需要返回 async generator
            async def _fake_drive(orch_inst, payload, config):
                yield ("content", "回复")

            with patch("api.langgraph_chat.adapter._drive", side_effect=_fake_drive):
                mock_get_orch.return_value = orch

                with patch("api.vision_service.analyze_images_batch",
                           side_effect=_mock_batch):
                    from api.langgraph_chat.adapter import LangGraphAdapter
                    results = []
                    async for kind, text in LangGraphAdapter.stream_chat(
                        message="分析图片",
                        session_key="test-session",
                        upload_id=VALID_UUID_1,  # 旧参数（单数）
                        user_id=USER_A,
                    ):
                        results.append((kind, text))

        self.assertEqual(len(analyze_batch_calls), 1, "应调用一次 analyze_images_batch")
        self.assertEqual(len(analyze_batch_calls[0]), 1, "单图包装后列表长度为 1")

    # ── TC-UNIT-MI-021：upload_ids 多图 → 调用 analyze_images_batch ───────────

    async def test_TC_UNIT_MI_021_upload_ids_multi_invokes_analyze_images_batch(self):
        """TC-UNIT-MI-021 (AC-MI-009): upload_ids=['uuid1','uuid2'] → 调用 analyze_images_batch。"""
        _inject_upload(VALID_UUID_1)
        _inject_upload(VALID_UUID_2)

        analyze_batch_calls = []

        async def _mock_batch(image_bytes_list, user_text, on_progress=None):
            analyze_batch_calls.append(len(image_bytes_list))
            return ["描述1", "描述2"]

        with patch("api.langgraph_chat.adapter._get_orch") as mock_get_orch:
            orch = self._make_orch_mock()

            async def _fake_drive(orch_inst, payload, config):
                yield ("content", "多图回复")

            with patch("api.langgraph_chat.adapter._drive", side_effect=_fake_drive):
                mock_get_orch.return_value = orch

                with patch("api.vision_service.analyze_images_batch",
                           side_effect=_mock_batch):
                    from api.langgraph_chat.adapter import LangGraphAdapter
                    results = []
                    async for kind, text in LangGraphAdapter.stream_chat(
                        message="分析两张图片",
                        session_key="test-session",
                        upload_ids=[VALID_UUID_1, VALID_UUID_2],
                        user_id=USER_A,
                    ):
                        results.append((kind, text))

        self.assertEqual(len(analyze_batch_calls), 1)
        self.assertEqual(analyze_batch_calls[0], 2, "应传入 2 张图片的字节列表")

    # ── TC-UNIT-MI-022：多图先 yield vision_progress 帧（每图一帧）────────────

    async def test_TC_UNIT_MI_022_multi_image_yields_vision_progress_frames(self):
        """TC-UNIT-MI-022 (AC-MI-010): 2 张图 → 先 yield 2 个 vision_progress 帧。"""
        _inject_upload(VALID_UUID_1)
        _inject_upload(VALID_UUID_2)

        async def _mock_batch(image_bytes_list, user_text, on_progress=None):
            return ["描述1", "描述2"]

        with patch("api.langgraph_chat.adapter._get_orch") as mock_get_orch:
            orch = self._make_orch_mock()

            async def _fake_drive(orch_inst, payload, config):
                yield ("content", "回复")

            with patch("api.langgraph_chat.adapter._drive", side_effect=_fake_drive):
                mock_get_orch.return_value = orch

                with patch("api.vision_service.analyze_images_batch",
                           side_effect=_mock_batch):
                    from api.langgraph_chat.adapter import LangGraphAdapter
                    items = []
                    async for kind, text in LangGraphAdapter.stream_chat(
                        message="",
                        session_key="test-session",
                        upload_ids=[VALID_UUID_1, VALID_UUID_2],
                        user_id=USER_A,
                    ):
                        items.append((kind, text))

        vision_progress_items = [(k, t) for k, t in items if k == "vision_progress"]
        self.assertEqual(len(vision_progress_items), 2,
                         f"2 张图应产生 2 个 vision_progress 帧，实际: {items}")

    # ── TC-UNIT-MI-023：部分失败 → yield image_analysis_partial ─────────────

    async def test_TC_UNIT_MI_023_partial_failure_yields_image_analysis_partial(self):
        """TC-UNIT-MI-023 (AC-MI-009 ADR-MI-004): 首图失败 → yield image_analysis_partial，
        包含 failed_indices=[0], total=2。"""
        _inject_upload(VALID_UUID_1)
        _inject_upload(VALID_UUID_2)

        async def _mock_batch(image_bytes_list, user_text, on_progress=None):
            return [None, "描述2"]  # 首图失败

        with patch("api.langgraph_chat.adapter._get_orch") as mock_get_orch:
            orch = self._make_orch_mock()

            async def _fake_drive(orch_inst, payload, config):
                yield ("content", "部分成功回复")

            with patch("api.langgraph_chat.adapter._drive", side_effect=_fake_drive):
                mock_get_orch.return_value = orch

                with patch("api.vision_service.analyze_images_batch",
                           side_effect=_mock_batch):
                    from api.langgraph_chat.adapter import LangGraphAdapter
                    items = []
                    async for kind, text in LangGraphAdapter.stream_chat(
                        message="分析",
                        session_key="test-session",
                        upload_ids=[VALID_UUID_1, VALID_UUID_2],
                        user_id=USER_A,
                    ):
                        items.append((kind, text))

        partial_items = [(k, t) for k, t in items if k == "image_analysis_partial"]
        self.assertEqual(len(partial_items), 1,
                         f"部分失败应 yield 1 个 image_analysis_partial，实际: {items}")
        partial_data = json.loads(partial_items[0][1])
        self.assertIn("failed_indices", partial_data)
        self.assertIn(0, partial_data["failed_indices"])
        self.assertEqual(partial_data["total"], 2)

    # ── TC-UNIT-MI-024：全部失败 → raise VisionServiceError ──────────────────

    async def test_TC_UNIT_MI_024_all_failure_raises_vision_service_error(self):
        """TC-UNIT-MI-024 (AC-MI-009): 所有图片 VLM 均失败 → raise VisionServiceError。"""
        _inject_upload(VALID_UUID_1)
        _inject_upload(VALID_UUID_2)

        async def _mock_batch(image_bytes_list, user_text, on_progress=None):
            return [None, None]  # 全部失败

        with patch("api.langgraph_chat.adapter._get_orch") as mock_get_orch:
            orch = self._make_orch_mock()

            async def _fake_drive(orch_inst, payload, config):
                yield ("content", "不应到达这里")

            with patch("api.langgraph_chat.adapter._drive", side_effect=_fake_drive):
                mock_get_orch.return_value = orch

                with patch("api.vision_service.analyze_images_batch",
                           side_effect=_mock_batch):
                    from api.langgraph_chat.adapter import LangGraphAdapter

                    with self.assertRaises(VisionServiceError):
                        async for _ in LangGraphAdapter.stream_chat(
                            message="分析",
                            session_key="test-session",
                            upload_ids=[VALID_UUID_1, VALID_UUID_2],
                            user_id=USER_A,
                        ):
                            pass

    # ── TC-UNIT-MI-025：多图持久化消息格式验证 ────────────────────────────────

    async def test_TC_UNIT_MI_025_persist_message_format_multi_image(self):
        """TC-UNIT-MI-025 (AC-MI-009 REQ-MI-008): 2 图成功 → persist_enhanced_message 格式
        为「[图片1描述：<d1>] [图片2描述：<d2>] <原始文字>」。"""
        _inject_upload(VALID_UUID_1)
        _inject_upload(VALID_UUID_2)
        d1 = "空调铭牌型号 EC-2025"
        d2 = "控制面板温度 24°C"

        async def _mock_batch(image_bytes_list, user_text, on_progress=None):
            return [d1, d2]

        with patch("api.langgraph_chat.adapter._get_orch") as mock_get_orch:
            orch = self._make_orch_mock()

            async def _fake_drive(orch_inst, payload, config):
                yield ("content", "回复")

            with patch("api.langgraph_chat.adapter._drive", side_effect=_fake_drive):
                mock_get_orch.return_value = orch

                with patch("api.vision_service.analyze_images_batch",
                           side_effect=_mock_batch):
                    from api.langgraph_chat.adapter import LangGraphAdapter
                    items = []
                    async for kind, text in LangGraphAdapter.stream_chat(
                        message="请分析",
                        session_key="test-session",
                        upload_ids=[VALID_UUID_1, VALID_UUID_2],
                        user_id=USER_A,
                    ):
                        items.append((kind, text))

        persist_items = [(k, t) for k, t in items if k == "persist_enhanced_message"]
        self.assertEqual(len(persist_items), 1, "应 yield 一条 persist_enhanced_message")
        persist_text = persist_items[0][1]
        self.assertIn("[图片1描述：", persist_text)
        self.assertIn("[图片2描述：", persist_text)
        self.assertIn(d1, persist_text)
        self.assertIn(d2, persist_text)
        self.assertIn("请分析", persist_text)


# ══════════════════════════════════════════════════════════════════════════════
# TC-UNIT-MI-030 ~ TC-UNIT-MI-034 : _pump 新 kind 处理单元测试
# ══════════════════════════════════════════════════════════════════════════════

class TestPumpNewKinds(unittest.IsolatedAsyncioTestCase):
    """ChatConsumer._pump 中 v1.9.0 新增 kind 的处理逻辑单元测试。

    直接实例化 ChatConsumer，mock send()，驱动 _pump 消费 async generator。
    """

    def _make_consumer(self):
        """创建最小化 ChatConsumer 实例（不需要 WS 连接）。"""
        from api.consumers import ChatConsumer
        consumer = ChatConsumer.__new__(ChatConsumer)
        consumer._related_images = []
        consumer._vision_persist_message = ""
        consumer.chat_session = None
        consumer._is_streaming = False

        self.sent_messages = []

        async def _mock_send(text_data):
            self.sent_messages.append(json.loads(text_data))

        consumer.send = _mock_send
        return consumer

    # ── TC-UNIT-MI-030：vision_progress kind → 转发 WS vision_progress 帧 ───

    async def test_TC_UNIT_MI_030_vision_progress_kind_emits_ws_frame(self):
        """TC-UNIT-MI-030 (AC-MI-010): _pump 收到 kind='vision_progress' → 发 WS vision_progress 帧。"""
        consumer = self._make_consumer()

        async def _gen():
            yield ("vision_progress", "正在分析第1/2张图片，请稍候…")
            yield ("content", "回复内容")

        status, accumulated = await consumer._pump(_gen())

        vp_msgs = [m for m in self.sent_messages if m.get("type") == "vision_progress"]
        self.assertEqual(len(vp_msgs), 1)
        self.assertEqual(vp_msgs[0]["message"], "正在分析第1/2张图片，请稍候…")

    # ── TC-UNIT-MI-031：vision_progress 不累积到 accumulated ────────────────

    async def test_TC_UNIT_MI_031_vision_progress_not_accumulated(self):
        """TC-UNIT-MI-031 (AC-MI-010): vision_progress 帧不计入 accumulated（不落库）。"""
        consumer = self._make_consumer()

        async def _gen():
            yield ("vision_progress", "进度消息")
            yield ("content", "正文内容")

        status, accumulated = await consumer._pump(_gen())

        self.assertNotIn("进度消息", accumulated)
        self.assertIn("正文内容", accumulated)

    # ── TC-UNIT-MI-032：image_analysis_partial → 发送 IMAGE_ANALYSIS_PARTIAL 错误帧 ──

    async def test_TC_UNIT_MI_032_image_analysis_partial_sends_error_frame(self):
        """TC-UNIT-MI-032 (AC-MI-011 ADR-MI-004): _pump 收到 image_analysis_partial →
        发送 code='IMAGE_ANALYSIS_PARTIAL' 错误帧（非阻塞，不中断流）。"""
        consumer = self._make_consumer()

        partial_payload = json.dumps({"failed_indices": [0], "total": 2})

        async def _gen():
            yield ("image_analysis_partial", partial_payload)
            yield ("content", "部分成功后的回复")

        status, accumulated = await consumer._pump(_gen())

        partial_errors = [
            m for m in self.sent_messages
            if m.get("type") == "error" and m.get("code") == "IMAGE_ANALYSIS_PARTIAL"
        ]
        self.assertEqual(len(partial_errors), 1,
                         f"应发送 IMAGE_ANALYSIS_PARTIAL 错误帧，实际消息: {self.sent_messages}")

        # 流应继续（content 正常累积）
        self.assertIn("部分成功后的回复", accumulated)
        self.assertEqual(status, "done")

    # ── TC-UNIT-MI-033：image_analysis_partial 不中断流（非阻塞） ─────────────

    async def test_TC_UNIT_MI_033_image_analysis_partial_does_not_abort_stream(self):
        """TC-UNIT-MI-033 (AC-MI-011 REQ-MI-009): partial 错误帧发送后流继续，
        后续 content token 正常累积到 accumulated。"""
        consumer = self._make_consumer()

        partial_payload = json.dumps({"failed_indices": [2], "total": 3})

        async def _gen():
            yield ("content", "第一段")
            yield ("image_analysis_partial", partial_payload)
            yield ("content", "第二段")

        status, accumulated = await consumer._pump(_gen())

        self.assertEqual(status, "done")
        self.assertIn("第一段", accumulated)
        self.assertIn("第二段", accumulated)

    # ── TC-UNIT-MI-034：image_analysis_partial 解析失败（bad JSON）→ 静默忽略 ──

    async def test_TC_UNIT_MI_034_malformed_partial_payload_silently_ignored(self):
        """TC-UNIT-MI-034 (AC-MI-011): image_analysis_partial 的 JSON 解析失败 → 静默忽略，流继续。"""
        consumer = self._make_consumer()

        async def _gen():
            yield ("image_analysis_partial", "{invalid json!!!")
            yield ("content", "流继续")

        # 不应抛异常
        status, accumulated = await consumer._pump(_gen())

        self.assertEqual(status, "done")
        self.assertIn("流继续", accumulated)

    # ── TC-UNIT-MI-035：多个 vision_progress 帧依次转发 ──────────────────────

    async def test_TC_UNIT_MI_035_multiple_vision_progress_frames_all_forwarded(self):
        """TC-UNIT-MI-035 (AC-MI-010): 连续 N 个 vision_progress 帧均被转发为 WS 消息。"""
        consumer = self._make_consumer()

        async def _gen():
            yield ("vision_progress", "正在分析第1/3张图片，请稍候…")
            yield ("vision_progress", "正在分析第2/3张图片，请稍候…")
            yield ("vision_progress", "正在分析第3/3张图片，请稍候…")
            yield ("content", "最终回复")

        status, accumulated = await consumer._pump(_gen())

        vp_msgs = [m for m in self.sent_messages if m.get("type") == "vision_progress"]
        self.assertEqual(len(vp_msgs), 3, "3 个进度帧应各自转发一次")
        msg_texts = [m["message"] for m in vp_msgs]
        self.assertIn("正在分析第1/3张图片，请稍候…", msg_texts)
        self.assertIn("正在分析第2/3张图片，请稍候…", msg_texts)
        self.assertIn("正在分析第3/3张图片，请稍候…", msg_texts)


# ══════════════════════════════════════════════════════════════════════════════
# TC-INT-MI-040 ~ TC-INT-MI-044 : consumers + vision_service 集成测试（WS）
# ══════════════════════════════════════════════════════════════════════════════

try:
    from channels.testing import WebsocketCommunicator
    from channels.routing import URLRouter
    from django.urls import re_path
    from api.consumers import ChatConsumer
    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False

from django.test import TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()

CHANNEL_LAYERS_OVERRIDE = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

_WS_TEST_LOOP = None


def _run_ws(coro):
    global _WS_TEST_LOOP
    if _WS_TEST_LOOP is None or _WS_TEST_LOOP.is_closed():
        _WS_TEST_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_WS_TEST_LOOP)
    return _WS_TEST_LOOP.run_until_complete(coro)


def _make_ws_app():
    return URLRouter([
        re_path(r'^ws/chat/$', ChatConsumer.as_asgi()),
    ])


def _make_async_gen(*tuples):
    async def _gen():
        for item in tuples:
            yield item
    return _gen()


@override_settings(
    CHANNEL_LAYERS=CHANNEL_LAYERS_OVERRIDE,
    CHAT_BACKEND='langgraph',
)
class TestConsumersMultiImageIntegration(TransactionTestCase):
    """TC-INT-MI-040 ~ TC-INT-MI-044：consumers + adapter mock WS 集成测试（v1.9.0 多图）。"""

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        _clear_store()
        self.user = User.objects.create_user(
            username='mi_test_user', password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.app = _make_ws_app()

    def tearDown(self):
        _clear_store()

    async def _connect_ws(self):
        communicator = WebsocketCommunicator(
            self.app,
            f'/ws/chat/?token={self.token.key}'
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        response = await communicator.receive_json_from(timeout=5)
        self.assertEqual(response['type'], 'connected')
        return communicator

    # ── TC-INT-MI-040：image_upload_ids 列表触发多图流程 ──────────────────────

    def test_TC_INT_MI_040_upload_ids_list_triggers_multi_image_flow(self):
        """TC-INT-MI-040 (AC-MI-004): image_upload_ids=[uuid1,uuid2] → adapter.stream_chat
        被调用时 upload_ids 参数为列表。"""
        async def _run_test():
            _inject_upload(VALID_UUID_1, user_id=self.user.id)
            _inject_upload(VALID_UUID_2, user_id=self.user.id)

            stream_chat_call_kwargs = {}

            def _capture_stream_chat(**kwargs):
                stream_chat_call_kwargs.update(kwargs)
                return _make_async_gen(('content', '多图回复'))

            mock_adapter = MagicMock()
            mock_adapter.stream_chat = MagicMock(side_effect=_capture_stream_chat)

            communicator = await self._connect_ws()
            try:
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '分析这些图片',
                        'image_upload_ids': [VALID_UUID_1, VALID_UUID_2],
                    })

                    for _ in range(10):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            if msg['type'] == 'stream_end':
                                break
                        except asyncio.TimeoutError:
                            break

                # 验证 adapter.stream_chat 被调用时 upload_ids 是正确的列表
                self.assertIn('upload_ids', stream_chat_call_kwargs,
                              "stream_chat 应收到 upload_ids 参数")
                self.assertEqual(stream_chat_call_kwargs['upload_ids'],
                                 [VALID_UUID_1, VALID_UUID_2])
            finally:
                await communicator.disconnect()

        _run_ws(_run_test())

    # ── TC-INT-MI-041：vision_progress kind 转发到 WS 前端 ────────────────────

    def test_TC_INT_MI_041_vision_progress_forwarded_to_ws_client(self):
        """TC-INT-MI-041 (AC-MI-010): adapter 产出 vision_progress kind → 前端收到 vision_progress WS 帧。"""
        async def _run_test():
            _inject_upload(VALID_UUID_1, user_id=self.user.id)

            mock_stream = _make_async_gen(
                ('vision_progress', '正在分析第1/1张图片，请稍候…'),
                ('content', '分析完成'),
            )
            mock_adapter = MagicMock()
            mock_adapter.stream_chat = MagicMock(return_value=mock_stream)

            communicator = await self._connect_ws()
            try:
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '分析图片',
                        'image_upload_id': VALID_UUID_1,
                    })

                    received = []
                    for _ in range(10):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            received.append(msg)
                            if msg['type'] == 'stream_end':
                                break
                        except asyncio.TimeoutError:
                            break

                vp_msgs = [m for m in received if m['type'] == 'vision_progress']
                self.assertTrue(len(vp_msgs) >= 1,
                                f"应收到 vision_progress WS 帧，实际: {[m['type'] for m in received]}")
                self.assertIn('message', vp_msgs[0])
            finally:
                await communicator.disconnect()

        _run_ws(_run_test())

    # ── TC-INT-MI-042：IMAGE_TOO_MANY WS 集成测试 ─────────────────────────────

    def test_TC_INT_MI_042_image_too_many_ws_error_frame(self):
        """TC-INT-MI-042 (AC-MI-005 REQ-MI-002): 6 张图 → 前端收到 IMAGE_TOO_MANY 错误帧。"""
        async def _run_test():
            uuids_6 = [
                f"0000000{i}-0000-4000-8000-000000000000" for i in range(1, 7)
            ]

            communicator = await self._connect_ws()
            try:
                await communicator.send_json_to({
                    'type': 'chat_message',
                    'message': '分析',
                    'image_upload_ids': uuids_6,
                })

                response = await communicator.receive_json_from(timeout=5)
                self.assertEqual(response['type'], 'error')
                self.assertEqual(response['code'], 'IMAGE_TOO_MANY')

                # WS 连接应保持（继续可用）
                mock_stream = _make_async_gen(('content', '继续对话'),)
                mock_adapter = MagicMock()
                mock_adapter.stream_chat = MagicMock(return_value=mock_stream)
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '纯文字消息',
                    })
                    for _ in range(5):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            if msg['type'] == 'stream_end':
                                break
                        except asyncio.TimeoutError:
                            break
            finally:
                await communicator.disconnect()

        _run_ws(_run_test())

    # ── TC-INT-MI-043：image_analysis_partial WS 集成测试 ────────────────────

    def test_TC_INT_MI_043_image_analysis_partial_ws_error_frame(self):
        """TC-INT-MI-043 (AC-MI-011): adapter 产出 image_analysis_partial → 前端收到
        IMAGE_ANALYSIS_PARTIAL 错误帧，后续 content 流仍正常到达。"""
        async def _run_test():
            _inject_upload(VALID_UUID_1, user_id=self.user.id)
            _inject_upload(VALID_UUID_2, user_id=self.user.id)

            partial_payload = json.dumps({"failed_indices": [0], "total": 2})
            mock_stream = _make_async_gen(
                ('vision_progress', '正在分析第1/2张图片，请稍候…'),
                ('vision_progress', '正在分析第2/2张图片，请稍候…'),
                ('image_analysis_partial', partial_payload),
                ('content', '部分成功回复内容'),
            )
            mock_adapter = MagicMock()
            mock_adapter.stream_chat = MagicMock(return_value=mock_stream)

            communicator = await self._connect_ws()
            try:
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '分析这些图片',
                        'image_upload_ids': [VALID_UUID_1, VALID_UUID_2],
                    })

                    received = []
                    for _ in range(15):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            received.append(msg)
                            if msg['type'] == 'stream_end':
                                break
                        except asyncio.TimeoutError:
                            break

                msg_types = [m['type'] for m in received]
                # 应有 IMAGE_ANALYSIS_PARTIAL 错误帧
                partial_errors = [
                    m for m in received
                    if m.get('type') == 'error' and m.get('code') == 'IMAGE_ANALYSIS_PARTIAL'
                ]
                self.assertTrue(len(partial_errors) >= 1,
                                f"应收到 IMAGE_ANALYSIS_PARTIAL，实际消息: {received}")
                # 后续 content 仍到达
                self.assertIn('stream_token', msg_types,
                              "部分失败后 content 流应正常继续")
                self.assertIn('stream_end', msg_types,
                              "stream_end 应正常到达")
            finally:
                await communicator.disconnect()

        _run_ws(_run_test())

    # ── TC-INT-MI-044：多图默认文案 WS 集成测试 ──────────────────────────────

    def test_TC_INT_MI_044_multi_image_default_text_ws_integration(self):
        """TC-INT-MI-044 (AC-MI-006 OQ-MI-004): 多图 + 空文字 → adapter.stream_chat 的
        message 参数包含「请帮我分析这些图片」。"""
        async def _run_test():
            _inject_upload(VALID_UUID_1, user_id=self.user.id)
            _inject_upload(VALID_UUID_2, user_id=self.user.id)

            stream_chat_message = []

            def _capture(**kwargs):
                stream_chat_message.append(kwargs.get('message', ''))
                return _make_async_gen(('content', '回复'))

            mock_adapter = MagicMock()
            mock_adapter.stream_chat = MagicMock(side_effect=_capture)

            communicator = await self._connect_ws()
            try:
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '',  # 无文字
                        'image_upload_ids': [VALID_UUID_1, VALID_UUID_2],
                    })

                    for _ in range(10):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            if msg['type'] == 'stream_end':
                                break
                        except asyncio.TimeoutError:
                            break

                self.assertTrue(len(stream_chat_message) > 0,
                                "stream_chat 应被调用")
                self.assertIn('请帮我分析这些图片', stream_chat_message[0],
                              f"多图默认文案未注入，实际 message: {stream_chat_message[0]!r}")
            finally:
                await communicator.disconnect()

        _run_ws(_run_test())


if __name__ == '__main__':
    unittest.main()
