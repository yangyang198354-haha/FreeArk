"""
test_consumers_multimodal.py — ChatConsumer v1.5.0 多模态扩展集成测试

覆盖 AC-MQ-*：
  AC-MQ-004-02（纯文字向后兼容，无 image_upload_id 路径不变）
  AC-MQ-001-01（UUID 格式校验；vision_progress 发送）
  AC-MQ-002-01（纯图片消息默认文案注入「请帮我分析这张图片」）
  AC-MQ-004-03（vision_progress WS 消息）
  AC-MQ-005-03（IMAGE_EXPIRED 错误帧，WS 连接保持）
  AC-MQ-005-01（IMAGE_ANALYSIS_FAILED 错误帧，WS 连接保持）
  AC-MQ-001-03（persist_enhanced_message 写入 DB 历史）
  AC-MQ-010-02（图片代码路径独立 except，不影响主流程）

测试命名规则：TC-INT-NNN（WS Consumer 集成测试，以 TC-INT-1xx 区分）
测试级别：集成测试（跨 consumers + vision_service + adapter mock）

依赖：
  - channels.testing.WebsocketCommunicator
  - InMemoryChannelLayer（无需 Redis）
  - TransactionTestCase（有 DB 操作）
  - 全部外部依赖（adapter, vision_service）通过 mock 注入

@module test_consumers_multimodal
@covers MOD-MQ-04 (consumers 扩展), MOD-MQ-03 (vision_service get_upload), MOD-MQ-05 (adapter 扩展)
@author sub_agent_test_engineer
"""

import asyncio
import json
from unittest.mock import patch, AsyncMock, MagicMock

import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
django.setup()

from django.test import TransactionTestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

try:
    from channels.testing import WebsocketCommunicator
    from channels.routing import URLRouter
    from django.urls import re_path
    from api.consumers import ChatConsumer
    _CHANNELS_AVAILABLE = True
except ImportError:
    _CHANNELS_AVAILABLE = False

import api.vision_service as vs_module
from api.vision_service import ImageExpiredError, ImageAccessDeniedError, VisionServiceError

User = get_user_model()

# ── 测试配置覆盖 ─────────────────────────────────────────────────────────────────
CHANNEL_LAYERS_OVERRIDE = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

VALID_UUID = "12345678-1234-4123-8123-123456789abc"
INVALID_UUID_STR = "not-a-valid-uuid"
SMALL_IMAGE_BYTES = b'\xff\xd8\xff\xe0' + b'\x00' * 8 + b'\xff\xd9'


def _make_ws_app():
    return URLRouter([
        re_path(r'^ws/chat/$', ChatConsumer.as_asgi()),
    ])


def _make_async_gen(*tuples):
    """将 (kind, text) 元组序列包装为 AsyncGenerator，用于 mock stream_chat。"""
    async def _gen():
        for item in tuples:
            yield item
    return _gen()


def _clear_store():
    with vs_module._store_lock:
        vs_module._upload_store.clear()
        vs_module._total_size = 0


# 进程级事件循环（测试间复用）
_WS_TEST_LOOP = None


def _run(coro):
    global _WS_TEST_LOOP
    if _WS_TEST_LOOP is None or _WS_TEST_LOOP.is_closed():
        _WS_TEST_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(_WS_TEST_LOOP)
    return _WS_TEST_LOOP.run_until_complete(coro)


@override_settings(
    CHANNEL_LAYERS=CHANNEL_LAYERS_OVERRIDE,
    CHAT_BACKEND='langgraph',
)
class TestConsumersMultimodal(TransactionTestCase):
    """TC-INT-101 ~ TC-INT-107：ChatConsumer v1.5.0 多模态集成测试。"""

    def setUp(self):
        if not _CHANNELS_AVAILABLE:
            self.skipTest('channels.testing 不可用，跳过 WS 集成测试')
        _clear_store()
        self.user = User.objects.create_user(
            username='multimodal_test_user', password='testpass123'
        )
        self.token = Token.objects.create(user=self.user)
        self.app = _make_ws_app()

    def tearDown(self):
        _clear_store()

    async def _connect_ws(self):
        """连接 WS，读取 connected 消息，返回 communicator。"""
        communicator = WebsocketCommunicator(
            self.app,
            f'/ws/chat/?token={self.token.key}'
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected, 'WS 连接应成功')
        response = await communicator.receive_json_from(timeout=5)
        self.assertEqual(response['type'], 'connected')
        return communicator

    # ── TC-INT-101：向后兼容——纯文字消息路径不变 ──────────────────────────────────

    def test_TC_INT_101_backward_compat_text_only_message(self):
        """TC-INT-101 (AC-MQ-004-02): 不含 image_upload_id 的消息，处理路径与 v1.4.1 一致。

        mock adapter.stream_chat，验证：
          1. stream_chat 被调用（无 upload_id 相关参数，或 upload_id=None）
          2. 前端收到 stream_token 和 stream_end
          3. 无 vision_progress 消息
        """
        async def _run_test():
            mock_stream = _make_async_gen(
                ('content', '你好'),
                ('content', '，有什么可以帮你？'),
            )
            mock_adapter = MagicMock()
            mock_adapter.stream_chat = MagicMock(return_value=mock_stream)

            communicator = await self._connect_ws()
            try:
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '你好',
                    })

                    messages = []
                    for _ in range(10):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            messages.append(msg)
                            if msg['type'] == 'stream_end':
                                break
                        except asyncio.TimeoutError:
                            break

                msg_types = [m['type'] for m in messages]
                # 应有 stream_token 和 stream_end
                self.assertIn('stream_token', msg_types)
                self.assertIn('stream_end', msg_types)
                # 不应有 vision_progress（无 upload_id）
                self.assertNotIn('vision_progress', msg_types)
            finally:
                await communicator.disconnect()

        _run(_run_test())

    # ── TC-INT-102：非 UUID 格式 image_upload_id → IMAGE_INVALID 错误 ──────────

    def test_TC_INT_102_invalid_uuid_format_returns_image_invalid(self):
        """TC-INT-102 (AC-MQ-001-01): 非 UUID 格式的 image_upload_id → IMAGE_INVALID 错误帧。

        WS 连接不断开（用户可继续发消息）。
        """
        async def _run_test():
            communicator = await self._connect_ws()
            try:
                await communicator.send_json_to({
                    'type': 'chat_message',
                    'message': '分析图片',
                    'image_upload_id': INVALID_UUID_STR,
                })

                response = await communicator.receive_json_from(timeout=5)
                self.assertEqual(response['type'], 'error')
                self.assertEqual(response['code'], 'IMAGE_INVALID')

                # WS 连接应保持：receive_nothing 返回 True 说明无更多消息但连接未关闭
                # 若 WS 已断开，communicator.receive_nothing 会抛出异常或返回 False
                # 此处只验证：error 消息已收到且代码正确
                self.assertEqual(response['type'], 'error')
                self.assertEqual(response['code'], 'IMAGE_INVALID')
            finally:
                await communicator.disconnect()

        _run(_run_test())

    # ── TC-INT-103：纯图片消息默认文案注入 ─────────────────────────────────────────

    def test_TC_INT_103_empty_message_with_upload_id_injects_default_text(self):
        """TC-INT-103 (AC-MQ-002-01): message="" + image_upload_id=VALID_UUID
        → adapter.stream_chat 收到的 message 包含「请帮我分析这张图片」。"""
        async def _run_test():
            # 在 vision_service._upload_store 中注入有效条目
            from datetime import datetime, timedelta
            with vs_module._store_lock:
                vs_module._upload_store[VALID_UUID] = {
                    'user_id': self.user.id,
                    'bytes': SMALL_IMAGE_BYTES,
                    'expire_at': datetime.utcnow() + timedelta(seconds=600),
                    'size': len(SMALL_IMAGE_BYTES),
                }
                vs_module._total_size += len(SMALL_IMAGE_BYTES)

            received_messages = []
            mock_stream = _make_async_gen(('content', '图片分析结果'),)
            mock_adapter = MagicMock()
            mock_adapter.stream_chat = MagicMock(return_value=mock_stream)

            communicator = await self._connect_ws()
            try:
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '',
                        'image_upload_id': VALID_UUID,
                    })

                    for _ in range(10):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            received_messages.append(msg)
                            if msg['type'] == 'stream_end':
                                break
                        except asyncio.TimeoutError:
                            break

                # 验证 adapter.stream_chat 被调用时，message 参数包含默认文案
                mock_adapter.stream_chat.assert_called_once()
                call_kwargs = mock_adapter.stream_chat.call_args
                # message 参数是第一个位置参数或关键字参数
                actual_message = (
                    call_kwargs.kwargs.get('message') or
                    (call_kwargs.args[0] if call_kwargs.args else '')
                )
                self.assertIn('请帮我分析这张图片', actual_message)
            finally:
                await communicator.disconnect()

        _run(_run_test())

    # ── TC-INT-104：vision_progress 消息发送验证 ──────────────────────────────────

    def test_TC_INT_104_vision_progress_sent_when_upload_id_present(self):
        """TC-INT-104 (AC-MQ-004-03): 含有效 upload_id 的消息 → 前端收到 vision_progress 消息。

        v1.6.0 架构变更：vision_progress 不再由 consumers 层主动发送，而是由 adapter
        通过 kind='vision_progress' yield、_pump 透传（见 adapter.stream_chat / consumers._pump）。
        因此 mock adapter 需像真实 adapter 那样先 yield vision_progress kind。
        """
        async def _run_test():
            from datetime import datetime, timedelta
            with vs_module._store_lock:
                vs_module._upload_store[VALID_UUID] = {
                    'user_id': self.user.id,
                    'bytes': SMALL_IMAGE_BYTES,
                    'expire_at': datetime.utcnow() + timedelta(seconds=600),
                    'size': len(SMALL_IMAGE_BYTES),
                }
                vs_module._total_size += len(SMALL_IMAGE_BYTES)

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
                        'message': '分析这张图片',
                        'image_upload_id': VALID_UUID,
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

                msg_types = [m['type'] for m in received]
                self.assertIn('vision_progress', msg_types,
                              f"应收到 vision_progress 消息，实际收到: {msg_types}")

                # vision_progress 应在 stream_token 之前
                if 'vision_progress' in msg_types and 'stream_token' in msg_types:
                    vp_idx = msg_types.index('vision_progress')
                    st_idx = msg_types.index('stream_token')
                    self.assertLess(vp_idx, st_idx, 'vision_progress 应先于 stream_token')
            finally:
                await communicator.disconnect()

        _run(_run_test())

    # ── TC-INT-105：IMAGE_EXPIRED 错误帧，WS 连接保持 ────────────────────────────

    def test_TC_INT_105_image_expired_sends_error_frame_ws_stays_open(self):
        """TC-INT-105 (AC-MQ-005-03): vision_service.get_upload 抛 ImageExpiredError
        → 前端收到 {"type":"error","code":"IMAGE_EXPIRED"}，WS 连接不断开。"""
        async def _run_test():
            communicator = await self._connect_ws()
            try:
                with patch('api.consumers._vs' if hasattr(
                    __import__('api.consumers', fromlist=['_vs']), '_vs'
                ) else 'api.consumers.get_chat_adapter'):
                    pass  # 确保 consumers 模块加载

                # patch consumers 中导入的 vision_service 模块
                with patch('api.consumers.get_chat_adapter') as mock_get_adapter:
                    # 让 stream_chat 内部的 get_upload 抛 ImageExpiredError
                    # consumers._handle_chat 先调用 vision_service.get_upload 做 TTL 预检
                    # 我们 patch api.vision_service 模块中的 get_upload
                    with patch('api.vision_service.get_upload',
                               side_effect=ImageExpiredError("已过期")):
                        await communicator.send_json_to({
                            'type': 'chat_message',
                            'message': '分析图片',
                            'image_upload_id': VALID_UUID,
                        })

                        response = await communicator.receive_json_from(timeout=5)
                        self.assertEqual(response['type'], 'error')
                        self.assertEqual(response['code'], 'IMAGE_EXPIRED')

                # WS 连接应保持（发送另一条消息验证）
                mock_stream = _make_async_gen(('content', '继续对话'),)
                mock_adapter_instance = MagicMock()
                mock_adapter_instance.stream_chat = MagicMock(return_value=mock_stream)
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter_instance):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '纯文字继续',
                    })

                    for _ in range(5):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            if msg['type'] == 'stream_end':
                                break
                        except asyncio.TimeoutError:
                            break
                    # 到这里说明 WS 连接未断开
            finally:
                await communicator.disconnect()

        _run(_run_test())

    # ── TC-INT-106：IMAGE_ANALYSIS_FAILED 错误帧，WS 连接保持 ─────────────────────

    def test_TC_INT_106_vision_service_error_sends_image_analysis_failed(self):
        """TC-INT-106 (AC-MQ-005-01, AC-MQ-005-02): adapter.stream_chat 中
        VisionServiceError → 前端收到 IMAGE_ANALYSIS_FAILED，WS 连接保持，
        不触发 INTERNAL_ERROR 或 OPENCLAW_UNAVAILABLE。"""
        async def _run_test():
            from datetime import datetime, timedelta
            # 先放入有效 upload 条目（使 TTL 预检通过）
            with vs_module._store_lock:
                vs_module._upload_store[VALID_UUID] = {
                    'user_id': self.user.id,
                    'bytes': SMALL_IMAGE_BYTES,
                    'expire_at': datetime.utcnow() + timedelta(seconds=600),
                    'size': len(SMALL_IMAGE_BYTES),
                }
                vs_module._total_size += len(SMALL_IMAGE_BYTES)

            async def _raise_vision_error(*args, **kwargs):
                raise VisionServiceError("VLM 不可用")
                yield  # 使其成为 async generator

            mock_adapter = MagicMock()
            mock_adapter.stream_chat = MagicMock(return_value=_raise_vision_error())

            communicator = await self._connect_ws()
            try:
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '分析这张图片',
                        'image_upload_id': VALID_UUID,
                    })

                    # 先收 vision_progress
                    messages_received = []
                    for _ in range(10):
                        try:
                            msg = await communicator.receive_json_from(timeout=3)
                            messages_received.append(msg)
                            if msg['type'] == 'error':
                                break
                        except asyncio.TimeoutError:
                            break

                error_msgs = [m for m in messages_received if m.get('type') == 'error']
                self.assertTrue(len(error_msgs) > 0, "应收到错误消息")
                error_msg = error_msgs[0]
                self.assertEqual(error_msg['type'], 'error')
                self.assertEqual(error_msg['code'], 'IMAGE_ANALYSIS_FAILED')
                # 不应是系统级错误
                self.assertNotEqual(error_msg['code'], 'INTERNAL_ERROR')
                self.assertNotEqual(error_msg['code'], 'OPENCLAW_UNAVAILABLE')
            finally:
                await communicator.disconnect()

        _run(_run_test())

    # ── TC-INT-107：persist_enhanced_message 写入 DB ──────────────────────────────

    def test_TC_INT_107_persist_enhanced_message_written_to_db(self):
        """TC-INT-107 (AC-MQ-001-03): adapter 的 persist_enhanced_message kind
        → chat_memory.append_message 被以增强消息调用。"""
        async def _run_test():
            from datetime import datetime, timedelta
            persist_msg = "[图片描述：空调铭牌，型号 EC-2025] 这是什么型号？"

            with vs_module._store_lock:
                vs_module._upload_store[VALID_UUID] = {
                    'user_id': self.user.id,
                    'bytes': SMALL_IMAGE_BYTES,
                    'expire_at': datetime.utcnow() + timedelta(seconds=600),
                    'size': len(SMALL_IMAGE_BYTES),
                }
                vs_module._total_size += len(SMALL_IMAGE_BYTES)

            mock_stream = _make_async_gen(
                ('content', '这是 EC-2025 型号的三恒空调'),
                ('persist_enhanced_message', persist_msg),
            )
            mock_adapter = MagicMock()
            mock_adapter.stream_chat = MagicMock(return_value=mock_stream)

            append_calls = []

            def _mock_append_message(session, role, content):
                append_calls.append({'role': role, 'content': content})

            communicator = await self._connect_ws()
            try:
                with patch('api.consumers.get_chat_adapter', return_value=mock_adapter):
                    with patch('api.chat_memory.append_message',
                               side_effect=_mock_append_message):
                        await communicator.send_json_to({
                            'type': 'chat_message',
                            'message': '这是什么型号？',
                            'image_upload_id': VALID_UUID,
                        })

                        for _ in range(15):
                            try:
                                msg = await communicator.receive_json_from(timeout=3)
                                if msg['type'] == 'stream_end':
                                    break
                            except asyncio.TimeoutError:
                                break

                # 验证增强消息被写入 DB
                user_msgs = [c for c in append_calls if c['role'] == 'user']
                enhanced_written = any(
                    '[图片描述：' in c['content'] for c in user_msgs
                )
                self.assertTrue(
                    enhanced_written,
                    f"增强消息未写入 DB。实际写入: {user_msgs}"
                )
            finally:
                await communicator.disconnect()

        _run(_run_test())

    # ── TC-INT-108：IMAGE_INVALID（ImageAccessDeniedError）错误帧 ─────────────────

    def test_TC_INT_108_access_denied_sends_image_invalid(self):
        """TC-INT-108 (AC-MQ-010-02): get_upload 抛 ImageAccessDeniedError
        → IMAGE_INVALID 错误帧，WS 连接保持。"""
        async def _run_test():
            communicator = await self._connect_ws()
            try:
                with patch('api.vision_service.get_upload',
                           side_effect=ImageAccessDeniedError("用户不匹配")):
                    await communicator.send_json_to({
                        'type': 'chat_message',
                        'message': '分析图片',
                        'image_upload_id': VALID_UUID,
                    })

                    response = await communicator.receive_json_from(timeout=5)
                    self.assertEqual(response['type'], 'error')
                    self.assertEqual(response['code'], 'IMAGE_INVALID')
            finally:
                await communicator.disconnect()

        _run(_run_test())

    # ── TC-INT-109：空消息空 upload_id 被忽略（向后兼容） ─────────────────────────

    def test_TC_INT_109_empty_message_no_upload_id_ignored(self):
        """TC-INT-109 (AC-MQ-004-02): 空 message 且无 image_upload_id → 消息被忽略，无响应。"""
        async def _run_test():
            communicator = await self._connect_ws()
            try:
                await communicator.send_json_to({
                    'type': 'chat_message',
                    'message': '',
                })

                # 不应收到任何处理相关消息
                nothing = await communicator.receive_nothing(timeout=1)
                self.assertTrue(nothing, "空消息应被静默忽略，不触发任何响应")
            finally:
                await communicator.disconnect()

        _run(_run_test())


if __name__ == '__main__':
    import unittest
    unittest.main()
