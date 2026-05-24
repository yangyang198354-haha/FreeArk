"""
ChatConsumer — WebSocket 聊天代理（MOD-BE-01）

职责：
  - WebSocket 连接管理（握手鉴权、断开清理）
  - 生成并持有 session_key（UUID，连接内存，不落库）
  - 接收前端消息，调用 OpenClawAdapter 获取流式响应
  - 将流式 token 逐包发送给前端

v1.1 关键约束：
  - 不维护 self.chat_history（FreeArk 后端完全无状态）
  - 不写入 MySQL（满足 REQ-NFR-002，聊天历史零写入）
  - session_key 仅在连接内存中持有，连接关闭后随实例销毁
  - OpenClaw gateway token 仅在 OpenClawAdapter 内持有，不在此处暴露

项目: FreeArk_Openclaw
文档引用: module_design.md MOD-BE-01, architecture_design.md ADR-001, ADR-003
需求引用: REQ-FUNC-004, REQ-FUNC-006, REQ-FUNC-007, REQ-NFR-002, REQ-NFR-004
"""

import asyncio
import json
import logging
import uuid
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from api.openclaw_adapter import OpenClawAdapter, OpenClawUnavailableError

logger = logging.getLogger('api.consumers')


class ChatConsumer(AsyncWebsocketConsumer):
    """
    异步 WebSocket Consumer，实现 FreeArk 与 OpenClaw 之间的流式聊天代理。

    连接建立流程：
      1. 从 URL query string 解析 FreeArk userToken
      2. 用 Token.objects.get() 验证 token（DRF TokenAuthentication）
      3. token 无效 → close(code=4001)，连接拒绝
      4. token 有效 → 生成 session_key（UUID），发送 connected 消息

    消息处理流程：
      1. 接收前端 {"type": "chat_message", "message": "..."}
      2. 调用 OpenClawAdapter.stream_chat(message, session_key)
      3. 逐 token yield → send {"type": "stream_token", "token": "..."}
      4. 流结束 → send {"type": "stream_end"}
      5. 异常 → send {"type": "error", "code": "...", "message": "..."}
    """

    async def connect(self):
        """握手鉴权：验证 FreeArk token，通过后建立连接。"""
        # --- 1. 解析 URL query string 中的 token ---
        query_string = self.scope.get('query_string', b'')
        params = parse_qs(query_string)
        token_bytes = params.get(b'token', [None])[0]

        if token_bytes is None:
            logger.warning('ChatConsumer: 连接缺少 token 参数，拒绝')
            await self.close(code=4001)
            return

        token_key = token_bytes.decode('utf-8', errors='replace')

        # --- 2. 验证 FreeArk token（复用 DRF TokenAuthentication 的 Token 模型）---
        user = await self._get_user_by_token(token_key)
        if user is None:
            logger.warning('ChatConsumer: token 无效或已过期，拒绝连接')
            await self.close(code=4001)
            return

        # --- 3. 初始化连接状态（仅 session_key，无历史存储）---
        self.user = user
        # session_key：OpenClaw 据此维护多轮上下文，FreeArk 仅持有此标识符
        # 连接关闭后随实例销毁，无任何历史数据遗留
        self.session_key = str(uuid.uuid4())
        self._is_streaming = False  # 防止并发流式请求

        # --- 4. 接受连接，通知前端 ---
        await self.accept()
        await self.send(json.dumps({
            'type': 'connected',
            'session_id': self.session_key,  # 仅作前端 debug 用，不含敏感信息
        }))
        logger.info('ChatConsumer: 用户 %s 连接成功，session_key=%s',
                    user.username, self.session_key[:8] + '...')

    async def disconnect(self, close_code):
        """
        连接断开清理。
        session_key 随实例销毁，无历史数据需清理，无 MySQL 写入。
        """
        username = getattr(getattr(self, 'user', None), 'username', 'unknown')
        logger.info('ChatConsumer: 用户 %s 断开连接，code=%d', username, close_code)

    async def receive(self, text_data=None, bytes_data=None):
        """接收前端消息，驱动 OpenClaw 流式调用。"""
        if text_data is None:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            logger.warning('ChatConsumer: 收到无效 JSON，忽略')
            return

        # 只处理 chat_message 类型
        if data.get('type') != 'chat_message':
            return

        user_message = data.get('message', '').strip()
        if not user_message:
            return

        # 防止并发：同一连接同时只允许一个流式请求
        if self._is_streaming:
            await self.send(json.dumps({
                'type': 'error',
                'code': 'BUSY',
                'message': '方舟龙虾正在回复中，请等待当前回复完成',
            }))
            return

        self._is_streaming = True
        try:
            await self._handle_chat(user_message)
        finally:
            self._is_streaming = False

    async def _handle_chat(self, user_message: str):
        """
        核心聊天处理：调用 OpenClawAdapter，逐 token 转发给前端。

        不维护 chat_history，不构建 messages 数组，
        仅透传 session_key（OpenClaw 负责上下文管理）。

        CONFIRM-7 (lobster-agent-api-channel)：在消息前附加 chatuser 前缀，
        供 Agent 提取并在 Tier-2 写操作的 operator 字段中追溯到实际操作用户。
        前缀格式：[__freeark_user__:<username>]（对话文本对用户透明，Agent 感知）。
        """
        try:
            # CONFIRM-7: 注入 chatuser 前缀（约 3 行）
            chat_user = getattr(self.user, 'username', 'unknown')
            augmented_message = f"[__freeark_user__:{chat_user}] {user_message}"
            async for token in OpenClawAdapter.stream_chat(
                message=augmented_message,
                session_key=self.session_key,
            ):
                await self.send(json.dumps({
                    'type': 'stream_token',
                    'token': token,
                }))

            # 流正常结束
            await self.send(json.dumps({'type': 'stream_end'}))

        except OpenClawUnavailableError as exc:
            logger.warning('ChatConsumer: OpenClaw 不可用: %s', exc)
            await self.send(json.dumps({
                'type': 'error',
                'code': 'OPENCLAW_UNAVAILABLE',
                'message': '方舟龙虾暂时离线，请稍后再试',
            }))

        except asyncio.TimeoutError:
            logger.warning('ChatConsumer: OpenClaw 响应超时')
            await self.send(json.dumps({
                'type': 'error',
                'code': 'TIMEOUT',
                'message': '方舟龙虾响应超时，请重试',
            }))

        except Exception as exc:
            # 兜底：未预期异常，不把异常详情暴露给前端
            logger.exception('ChatConsumer: 未预期异常: %s', exc)
            await self.send(json.dumps({
                'type': 'error',
                'code': 'INTERNAL_ERROR',
                'message': '服务出现内部错误，请刷新页面后重试',
            }))

    @sync_to_async
    def _get_user_by_token(self, token_key: str):
        """
        通过 DRF Token 验证 FreeArk 用户身份。
        使用 sync_to_async 包装同步 ORM 查询。

        返回 User 对象（验证通过）或 None（验证失败）。
        不抛出异常。
        """
        if not token_key:
            return None
        try:
            from rest_framework.authtoken.models import Token
            return Token.objects.select_related('user').get(key=token_key).user
        except Token.DoesNotExist:
            return None
        except Exception as exc:
            logger.error('ChatConsumer._get_user_by_token 异常: %s', exc)
            return None
