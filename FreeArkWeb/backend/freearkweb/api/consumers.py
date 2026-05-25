"""
ChatConsumer — WebSocket 聊天代理（MOD-BE-01 v1.2）

职责：
  - WebSocket 连接管理（握手鉴权、断开清理）
  - 生成并持有 session_key（UUID，连接内存，不落库）
  - 接收前端消息，调用 OpenClawAdapter 获取流式响应
  - 将流式 token 逐包发送给前端（按 kind 分类：reasoning_token / stream_token）

v1.2 变更（相对 v1.1）：
  - `_handle_chat` 解包 adapter 的 (kind, text) 二元组
  - 按 kind 路由：'reasoning' → reasoning_token，'content' → stream_token
  - 在 reasoning→content 切换时发送 reasoning_end 信号（仅一次，ARCH-C-004）
  - connect/disconnect/receive/_get_user_by_token 方法不变

v1.2 关键约束：
  - 不维护 self.chat_history（FreeArk 后端完全无状态）
  - 不写入 MySQL（满足 REQ-NFR-002，聊天历史零写入）
  - reasoning 状态变量为 _handle_chat 局部变量，不跨请求持久化（REQ-NFR-009）
  - session_key 仅在连接内存中持有，连接关闭后随实例销毁
  - OpenClaw gateway token 仅在 OpenClawAdapter 内持有，不在此处暴露
  - adapter v1.3 和本 consumer v1.2 必须同批次部署（ARCH-C-002）

项目: FreeArk_Openclaw
文档引用: module_design.md MOD-BE-01 v1.2, architecture_design.md ADR-007
需求引用: REQ-FUNC-010, REQ-NFR-005, REQ-NFR-009
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

    消息处理流程（v1.2）：
      1. 接收前端 {"type": "chat_message", "message": "..."}
      2. 调用 OpenClawAdapter.stream_chat(message, session_key)
         → 返回 AsyncGenerator[tuple[str, str], None]
      3. kind='reasoning' → send {"type": "reasoning_token", "token": "..."}
      4. 首次 kind='content'（且之前有 reasoning）→ send {"type": "reasoning_end"}
         然后 → send {"type": "stream_token", "token": "..."}
      5. 后续 kind='content' → send {"type": "stream_token", "token": "..."}
      6. 流结束 → send {"type": "stream_end"}
      7. 异常 → send {"type": "error", "code": "...", "message": "..."}

    WebSocket 协议 v1.1（本期新增消息类型）：
      reasoning_token × N → reasoning_end × 1 → stream_token × M → stream_end × 1
      无 reasoning 时：stream_token × M → stream_end × 1（向后兼容旧前端）
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
        核心聊天处理（v1.2）：调用 OpenClawAdapter，按 kind 分类转发给前端。

        不维护 chat_history，不构建 messages 数组，
        仅透传 session_key（OpenClaw 负责上下文管理）。

        CONFIRM-7 (lobster-agent-api-channel)：在消息前附加 chatuser 前缀，
        供 Agent 提取并在 Tier-2 写操作的 operator 字段中追溯到实际操作用户。
        前缀格式：[__freeark_user__:<username>]（对话文本对用户透明，Agent 感知）。

        v1.2 状态变量（局部，不跨调用持久化，满足 REQ-NFR-009 多用户隔离）：
          _in_reasoning: bool — 当前是否在 reasoning 阶段
          _reasoning_ended: bool — 是否已发过 reasoning_end（防重复，ARCH-C-004）
        """
        try:
            # CONFIRM-7: 注入 chatuser 前缀（约 3 行）
            chat_user = getattr(self.user, 'username', 'unknown')
            augmented_message = f"[__freeark_user__:{chat_user}] {user_message}"

            # v1.2 内部状态（局部变量，每次 _handle_chat 调用独立，不是实例变量）
            _in_reasoning = False      # 当前是否在 reasoning 阶段
            _reasoning_ended = False   # 是否已发送过 reasoning_end（防重复）

            async for kind, text in OpenClawAdapter.stream_chat(
                message=augmented_message,
                session_key=self.session_key,
            ):
                if kind == 'reasoning':
                    _in_reasoning = True
                    await self.send(json.dumps({
                        'type': 'reasoning_token',
                        'token': text,
                    }))

                elif kind == 'content':
                    # 首次收到 content 且之前有过 reasoning：先发 reasoning_end
                    if _in_reasoning and not _reasoning_ended:
                        await self.send(json.dumps({'type': 'reasoning_end'}))
                        _reasoning_ended = True
                        _in_reasoning = False
                    await self.send(json.dumps({
                        'type': 'stream_token',
                        'token': text,
                    }))

                # else: 未知 kind，静默忽略（前向兼容）

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
