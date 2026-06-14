"""
ChatConsumer — WebSocket 聊天代理（MOD-BE-01 v1.3）

v1.3 变更（相对 v1.2）：
  - connect()：鉴权成功后调用 chat_memory.create_session()，新增 self.chat_session
  - disconnect()：调用 chat_memory.close_session()；若有 _pending_assistant_content 则先写入
  - _handle_chat()：
      a. 开始时 load_history() + build_inject_prefix()，前缀追加到 augmented_message 前
      b. 发送给 OpenClaw 前 append_message('user', ...)
      c. 流结束后 append_message('assistant', accumulated_content)
  - 新增实例变量：self.chat_session / self._pending_assistant_content
  - 所有 DB 操作失败均降级（记日志，WS 不中断），满足 ARCH-C-011

v1.2 关键约束（保持不变）：
  - (kind, text) 协议不变（ARCH-C-006，C-008）
  - reasoning_token / reasoning_end / stream_token / stream_end 消息类型不变
  - _get_user_by_token 不变
  - OpenClawAdapter.stream_chat 调用签名不变

项目: FreeArk_Openclaw
文档引用: module_design.md MOD-BE-01 v1.3, architecture_design.md ADR-009/010/013
需求引用: REQ-FUNC-013, REQ-FUNC-016, REQ-NFR-013
"""

import asyncio
import json
import logging
import uuid
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

# OpenClawUnavailableError 仍作为统一降级异常（LangGraphAdapter 失败时也抛它）；
# 具体适配器（OpenClaw / LangGraph）由 chat_backend 工厂按 settings.CHAT_BACKEND 选择。
from api.openclaw_adapter import OpenClawUnavailableError
from api.chat_backend import get_chat_adapter
from api import chat_memory

logger = logging.getLogger('api.consumers')


class ChatConsumer(AsyncWebsocketConsumer):
    """
    异步 WebSocket Consumer，实现 FreeArk 与 OpenClaw 之间的流式聊天代理。

    v1.3 新增实例变量：
      self.chat_session: ChatSession | None — DB 会话对象，connect 时创建
      self._pending_assistant_content: str — 当前未写入 DB 的 assistant content
    """

    async def connect(self):
        """握手鉴权：验证 FreeArk token，通过后建立连接并创建 DB 会话记录。"""
        # 提前初始化实例属性：connect 在无/无效 token 时会 close()+return，但 Channels
        # 仍会调用 disconnect()，其中访问 self.chat_session / self._pending_assistant_content。
        # 若不先置默认值，早期拒绝路径会抛 AttributeError（'ChatConsumer' object has no
        # attribute 'chat_session'）。在任何 early-return 之前先兜底。
        self.chat_session = None
        self._pending_assistant_content = ''
        # 阶段 E：Tier-2 写确认门状态。_awaiting_confirm=True 表示图已 interrupt、
        # 正等前端 confirm_response；_confirm_accumulated 暂存确认前已流式的内容。
        self._awaiting_confirm = False
        self._confirm_accumulated = ''

        query_string = self.scope.get('query_string', b'')
        params = parse_qs(query_string)
        token_bytes = params.get(b'token', [None])[0]

        if token_bytes is None:
            logger.warning('ChatConsumer: 连接缺少 token 参数，拒绝')
            await self.close(code=4001)
            return

        token_key = token_bytes.decode('utf-8', errors='replace')

        user = await self._get_user_by_token(token_key)
        if user is None:
            logger.warning('ChatConsumer: token 无效或已过期，拒绝连接')
            await self.close(code=4001)
            return

        self.user = user
        self.session_key = str(uuid.uuid4())
        self._is_streaming = False
        # self.chat_session / self._pending_assistant_content 已在 connect 顶部初始化

        # v1.3: 创建 DB 会话记录（失败则降级，WS 仍正常建立）
        try:
            self.chat_session = await sync_to_async(
                chat_memory.create_session
            )(self.user, self.session_key)
        except Exception as exc:
            logger.warning('ChatConsumer: create_session 失败，记忆功能降级: %s', exc)

        await self.accept()
        await self.send(json.dumps({
            'type': 'connected',
            'session_id': self.session_key,
        }))
        logger.info('ChatConsumer: 用户 %s 连接成功，session_key=%s',
                    user.username, self.session_key[:8] + '...')

    async def disconnect(self, close_code):
        """连接断开：写入 pending assistant 内容，关闭 DB 会话记录。"""
        username = getattr(getattr(self, 'user', None), 'username', 'unknown')
        logger.info('ChatConsumer: 用户 %s 断开连接，code=%d', username, close_code)

        # v1.3: 关闭会话记录（含 pending content 写入）
        if self.chat_session is not None:
            if self._pending_assistant_content:
                try:
                    await sync_to_async(chat_memory.append_message)(
                        self.chat_session, 'assistant',
                        self._pending_assistant_content,
                    )
                except Exception as exc:
                    logger.error('ChatConsumer: disconnect 写 pending assistant 失败: %s', exc)
            try:
                await sync_to_async(chat_memory.close_session)(self.chat_session)
            except Exception as exc:
                logger.warning('ChatConsumer: close_session 失败: %s', exc)

    async def receive(self, text_data=None, bytes_data=None):
        """接收前端消息，驱动 OpenClaw 流式调用。"""
        if text_data is None:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            logger.warning('ChatConsumer: 收到无效 JSON，忽略')
            return

        msg_type = data.get('type')

        # 阶段 E：用户对 Tier-2 写操作的确认/取消（恢复已 interrupt 的图）。
        if msg_type == 'confirm_response':
            if not self._awaiting_confirm:
                return  # 无待确认动作，忽略（防重复/乱序）
            if self._is_streaming:
                return
            self._is_streaming = True
            try:
                await self._handle_confirm(bool(data.get('approved')))
            finally:
                self._is_streaming = False
            return

        if msg_type != 'chat_message':
            return

        user_message = data.get('message', '').strip()
        if not user_message:
            return

        if self._is_streaming or self._awaiting_confirm:
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
        核心聊天处理（v1.3）：注入历史记忆，调用 OpenClawAdapter，写入 DB 记录。

        变更点（相对 v1.2）：
          1. 构建 augmented_message 前先 load_history + build_inject_prefix
          2. 发送给 OpenClaw 前 append_message('user', ...)
          3. 累积 kind=='content' 的 text → accumulated_content
          4. 流结束后 append_message('assistant', accumulated_content)

        不变点（ARCH-C-006）：
          - reasoning_token / reasoning_end / stream_token / stream_end 发送逻辑不变
          - stream_chat 调用签名不变（message + session_key）
        """
        try:
            # v1.3: 加载历史记忆并构建注入前缀
            inject_prefix = ''
            if self.chat_session is not None:
                try:
                    history = await sync_to_async(chat_memory.load_history)(self.user)
                    inject_prefix = chat_memory.build_inject_prefix(history)
                except Exception as exc:
                    logger.warning('ChatConsumer: load_history 失败，以空历史继续: %s', exc)

            # CONFIRM-7（不变）: 注入 chatuser 前缀
            chat_user = getattr(self.user, 'username', 'unknown')
            augmented_message = (
                f"{inject_prefix}"
                f"[__freeark_user__:{chat_user}] {user_message}"
            )

            # v1.3: 写入用户消息记录
            if self.chat_session is not None:
                try:
                    await sync_to_async(chat_memory.append_message)(
                        self.chat_session, 'user', user_message,
                    )
                except Exception as exc:
                    logger.error('ChatConsumer: append_message(user) 失败: %s', exc)

            adapter = get_chat_adapter()  # 按 CHAT_BACKEND 选 OpenClaw / LangGraph
            status, accumulated_content = await self._pump(
                adapter.stream_chat(
                    message=augmented_message,
                    session_key=self.session_key,
                ))

            # 阶段 E：遇 Tier-2 写确认门 → 已发 confirm_required，暂停等前端 confirm_response
            if status == 'confirm':
                self._awaiting_confirm = True
                self._confirm_accumulated = accumulated_content
                return  # 不发 stream_end、不写 assistant 记录（确认后再终结本轮）

            await self._finalize_turn(accumulated_content)

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
            logger.exception('ChatConsumer: 未预期异常: %s', exc)
            await self.send(json.dumps({
                'type': 'error',
                'code': 'INTERNAL_ERROR',
                'message': '服务出现内部错误，请刷新页面后重试',
            }))

    async def _pump(self, agen, accumulated_prefix: str = ''):
        """消费适配器的 (kind, text) 流，转发为 WS 消息，累积 content。

        返回 (status, accumulated):
          - ('done', 文本)    流正常结束
          - ('confirm', 文本) 遇 Tier-2 写确认门（已发 confirm_required，未发 stream_end）

        kind 协议（ARCH-C-006 不变）：reasoning / content；阶段 E 新增 confirm。"""
        _in_reasoning = False
        _reasoning_ended = False
        accumulated = accumulated_prefix
        async for kind, text in agen:
            if kind == 'reasoning':
                _in_reasoning = True
                await self.send(json.dumps({'type': 'reasoning_token', 'token': text}))
            elif kind == 'content':
                if _in_reasoning and not _reasoning_ended:
                    await self.send(json.dumps({'type': 'reasoning_end'}))
                    _reasoning_ended = True
                    _in_reasoning = False
                accumulated += text
                await self.send(json.dumps({'type': 'stream_token', 'token': text}))
            elif kind == 'confirm':
                try:
                    payload = json.loads(text)
                except (ValueError, TypeError):
                    payload = {}
                await self.send(json.dumps({
                    'type': 'confirm_required',
                    'actions': payload.get('actions', []),
                }))
                return ('confirm', accumulated)
            elif kind == 'status':
                # 静默期进度提示（分类/查询/生成阶段），不计入 accumulated、不落库
                await self.send(json.dumps({'type': 'status_update', 'message': text}))
            # else: 未知 kind，静默忽略（前向兼容）
        return ('done', accumulated)

    async def _finalize_turn(self, accumulated_content: str):
        """结束一轮：发 stream_end，写入 assistant 记录（失败则存 pending）。"""
        await self.send(json.dumps({'type': 'stream_end'}))
        if self.chat_session is not None and accumulated_content:
            try:
                await sync_to_async(chat_memory.append_message)(
                    self.chat_session, 'assistant', accumulated_content,
                )
                self._pending_assistant_content = ''
            except Exception as exc:
                self._pending_assistant_content = accumulated_content
                logger.error('ChatConsumer: append_message(assistant) 失败，保存 pending: %s', exc)
        else:
            self._pending_assistant_content = ''

    async def _handle_confirm(self, approved: bool):
        """阶段 E：收到 confirm_response → 恢复图执行（批准则真写，拒绝则取消）。"""
        self._awaiting_confirm = False
        prefix = self._confirm_accumulated
        self._confirm_accumulated = ''
        try:
            adapter = get_chat_adapter()
            resume = getattr(adapter, 'resume_chat', None)
            if resume is None:
                # 当前后端（OpenClaw）不支持写确认门——正常不会走到此分支
                await self.send(json.dumps({
                    'type': 'error', 'code': 'INTERNAL_ERROR',
                    'message': '当前后端不支持写确认',
                }))
                return
            status, accumulated = await self._pump(
                resume(self.session_key, {'approved': approved}), prefix)
            if status == 'confirm':
                # 多个写门：再次暂停等下一轮确认
                self._awaiting_confirm = True
                self._confirm_accumulated = accumulated
                return
            await self._finalize_turn(accumulated)
        except OpenClawUnavailableError as exc:
            logger.warning('ChatConsumer: confirm resume 不可用: %s', exc)
            await self.send(json.dumps({
                'type': 'error', 'code': 'OPENCLAW_UNAVAILABLE',
                'message': '方舟龙虾暂时离线，请稍后再试',
            }))
        except asyncio.TimeoutError:
            logger.warning('ChatConsumer: confirm resume 超时')
            await self.send(json.dumps({
                'type': 'error', 'code': 'TIMEOUT',
                'message': '方舟龙虾响应超时，请重试',
            }))
        except Exception as exc:
            logger.exception('ChatConsumer: confirm resume 异常: %s', exc)
            await self.send(json.dumps({
                'type': 'error', 'code': 'INTERNAL_ERROR',
                'message': '服务出现内部错误，请刷新页面后重试',
            }))

    @sync_to_async
    def _get_user_by_token(self, token_key: str):
        """通过 DRF Token 验证 FreeArk 用户身份（不变）。"""
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
