"""
ChatConsumer — WebSocket 聊天代理（MOD-BE-CONS v1.4）

v1.4 变更（相对 v1.3，实现 ADR-001 策略 A + ADR-002 异步标题）：
  - connect()：移除立即创建 DB 会话的逻辑；仅保存 self.session_key（字符串）；
    新增初始化 self._session_created = False, self._first_round_done = False
  - 新增 _ensure_session_created()：首条 user 消息到达时幂等创建 ChatSession，
    写入截断标题（generate_title_truncate），设 self.chat_session
  - _handle_chat()：
      a. 首行调用 await self._ensure_session_created(user_message)
      b. 首轮（user+assistant各一条）完成后触发 asyncio.create_task(generate_title_llm_async)
  - disconnect()：self.chat_session is None 时跳过所有 DB 操作（满足 ADR-001）
  - 删除 _resolve_session() 方法（职责已内联进 connect()）

v1.3 变更（保持不变）：
  - (kind, text) 协议不变（ARCH-C-006，C-008）
  - reasoning_token / reasoning_end / stream_token / stream_end 消息类型不变
  - _get_user_by_token 不变
  - OpenClawAdapter.stream_chat 调用签名不变

@module MOD-BE-CONS
@implements IFC-CONS-001, IFC-CONS-002, IFC-CONS-003, IFC-CONS-004
@depends MOD-BE-MEM
@author sub_agent_software_developer

项目: FreeArk_ChatSession
文档引用: module_design.md MOD-BE-CONS v1.4, architecture_design.md ADR-001/002/003
需求引用: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-NFR-004
"""

import asyncio
import json
import logging
import uuid
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from django.db import IntegrityError

# OpenClawUnavailableError 仍作为统一降级异常（LangGraphAdapter 失败时也抛它）；
# 具体适配器（OpenClaw / LangGraph）由 chat_backend 工厂按 settings.CHAT_BACKEND 选择。
from api.openclaw_adapter import OpenClawUnavailableError
from api.chat_backend import get_chat_adapter
from api import chat_memory

logger = logging.getLogger('api.consumers')


class ChatConsumer(AsyncWebsocketConsumer):
    """
    异步 WebSocket Consumer，实现 FreeArk 与 OpenClaw/LangGraph 之间的流式聊天代理。

    v1.4 实例变量：
      self.chat_session: ChatSession | None — DB 会话对象（首条消息后才赋值，ADR-001）
      self._pending_assistant_content: str — 当前未写入 DB 的 assistant content
      self._session_created: bool — 标记当前连接内 session 是否已创建（幂等守卫）
      self._first_round_done: bool — 标记首轮对话（user+assistant各一条）是否已完成
    """

    async def connect(self):
        """
        握手鉴权：验证 FreeArk token，通过后建立连接。

        ADR-001 策略 A：connect 不创建 DB 记录，仅保存 session_key 字符串到实例变量。
        首条 user 消息到达时才由 _ensure_session_created() 幂等创建 ChatSession。

        @implements IFC-CONS-001
        """
        # 提前初始化所有实例属性：connect 在无/无效 token 时会 close()+return，但 Channels
        # 仍会调用 disconnect()，需要所有属性已初始化，否则抛 AttributeError。
        self.chat_session = None
        self._pending_assistant_content = ''
        self._session_created = False   # ADR-001：首条消息后才设为 True
        self._first_round_done = False  # ADR-002：首轮完成后才设为 True
        # 阶段 E：Tier-2 写确认门状态。
        self._awaiting_confirm = False
        self._confirm_accumulated = ''
        # ── v1.4.1 新增（IFC-141-701，MOD-141-07）──────────────────────────────
        self._related_images: list = []   # 存储本轮 related_images（实时，不持久化，OQ-IC-004）

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
        self._is_streaming = False

        # ADR-001：从 query param 解析 session_key（可选），仅保存字符串，不查 DB
        session_key_param_bytes = params.get(b'session_key', [None])[0]
        session_key_param = (
            session_key_param_bytes.decode('utf-8', errors='replace')
            if session_key_param_bytes is not None else None
        )

        # ADR-001：保留传入的 session_key（用于恢复已有会话），否则生成新 UUID
        # connect 不做 DB 查询，session_key 有效性在首条消息时验证（_ensure_session_created）
        self.session_key = session_key_param if session_key_param else str(uuid.uuid4())

        await self.accept()
        await self.send(json.dumps({
            'type': 'connected',
            'session_id': self.session_key,
            'session_key': self.session_key,
        }))
        logger.info('ChatConsumer: 用户 %s 连接成功，session_key=%s',
                    user.username, self.session_key[:8] + '...')

    async def disconnect(self, close_code):
        """
        连接断开：写入 pending assistant 内容，关闭 DB 会话记录。

        ADR-001：若 self.chat_session is None（从未发言，session 未创建），
        跳过所有 DB 操作，满足"connect 不落库"策略。

        @implements IFC-CONS-004
        """
        username = getattr(getattr(self, 'user', None), 'username', 'unknown')
        logger.info('ChatConsumer: 用户 %s 断开连接，code=%d', username, close_code)

        # ADR-001：chat_session 为 None 表示用户从未发消息，无需任何 DB 操作
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
        """接收前端消息，驱动 OpenClaw/LangGraph 流式调用。"""
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
                'message': '方舟智能体正在回复中，请等待当前回复完成',
            }))
            return

        self._is_streaming = True
        try:
            await self._handle_chat(user_message)
        finally:
            self._is_streaming = False

    async def _ensure_session_created(self, user_message: str) -> None:
        """
        幂等地创建 ChatSession 并写入截断标题。

        触发时机：_handle_chat() 首行调用，在任何 DB 写操作之前。
        幂等性：
          1. 主守卫：self._session_created=True 时直接返回（避免重复调用）。
          2. DB 层守卫：session_key 有 unique=True 约束，IntegrityError 时查询并复用已有 session。

        副作用：设置 self.chat_session, self._session_created = True。

        @implements IFC-CONS-002
        """
        # 主幂等守卫（RISK-001 缓解）
        if self._session_created:
            return

        from .models import ChatSession  # noqa: PLC0415

        try:
            # 尝试创建会话（ORM 操作必须用 sync_to_async，RISK-003）
            session_obj = await sync_to_async(chat_memory.create_session)(
                self.user, self.session_key
            )
        except IntegrityError:
            # session_key 唯一约束冲突（极罕见并发重传场景，RISK-001 兜底）
            logger.warning(
                'ChatConsumer._ensure_session_created: session_key=%s 已存在，查询并复用',
                self.session_key[:8] + '...',
            )
            try:
                session_obj = await sync_to_async(
                    lambda: ChatSession.objects.get(
                        user=self.user,
                        session_key=self.session_key,
                        is_deleted=False,
                    )
                )()
            except Exception as exc:
                logger.error(
                    'ChatConsumer._ensure_session_created: 复用 session 失败，记忆功能降级: %s', exc
                )
                return
        except Exception as exc:
            logger.warning(
                'ChatConsumer._ensure_session_created: create_session 失败，记忆功能降级: %s', exc
            )
            return

        # 生成截断标题并立即写入（同步计算，无 DB IO）
        truncated_title = chat_memory.generate_title_truncate(user_message, max_len=30)
        if truncated_title:
            try:
                await sync_to_async(
                    lambda: ChatSession.objects.filter(pk=session_obj.pk).update(
                        title=truncated_title
                    )
                )()
                # 更新本地对象保持一致
                session_obj.title = truncated_title
            except Exception as exc:
                logger.warning(
                    'ChatConsumer._ensure_session_created: 写入截断标题失败（非致命）: %s', exc
                )

        self.chat_session = session_obj
        self._session_created = True

    async def _handle_chat(self, user_message: str):
        """
        核心聊天处理（v1.4）：ADR-001 首行确保 session 已创建，ADR-002 首轮后触发异步标题。

        变更点（相对 v1.3）：
          1. 首行调用 await self._ensure_session_created(user_message)（ADR-001）
          2. _finalize_turn 成功后，首轮完成时 asyncio.create_task 异步 LLM 标题（ADR-002）
          3. 历史注入保持不变（self.chat_session 可能仍为 None 时跳过）

        不变点（ARCH-C-006）：
          - reasoning_token / reasoning_end / stream_token / stream_end 发送逻辑不变
          - stream_chat 调用签名不变（message + session_key）

        @implements IFC-CONS-003
        """
        try:
            # ADR-001：首条消息到达时幂等创建 session（已创建则直接返回）
            await self._ensure_session_created(user_message)

            # v1.3: 加载历史记忆并构建注入前缀
            inject_prefix = ''
            if self.chat_session is not None:
                try:
                    history = await sync_to_async(chat_memory.load_history_by_session)(self.chat_session)
                    inject_prefix = chat_memory.build_inject_prefix(history)
                except Exception as exc:
                    logger.warning('ChatConsumer: load_history_by_session 失败，以空历史继续: %s', exc)

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

            # ── v1.4.1：取出本轮收集的 related_images，立即重置防下轮残留（IFC-141-703）──
            related_images = self._related_images
            self._related_images = []   # 重置
            # ────────────────────────────────────────────────────────────────────────
            await self._finalize_turn(accumulated_content, related_images=related_images)

            # ADR-002：首轮完成后异步生成 LLM 标题（user+assistant各一条）
            if (
                self.chat_session is not None
                and not self._first_round_done
                and accumulated_content
            ):
                self._first_round_done = True
                asyncio.create_task(
                    chat_memory.generate_title_llm_async(
                        session_id=self.chat_session.pk,
                        first_user_msg=user_message,
                        first_assistant_msg=accumulated_content,
                    )
                )
                logger.info(
                    'ChatConsumer: 已触发异步 LLM 标题生成 session_id=%d',
                    self.chat_session.pk,
                )

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
            elif kind == 'related_images':
                # v1.4.1 新增（IFC-141-702）：存入实例变量，不转发 WS
                # 通过 _finalize_turn 的 stream_end 统一发送给前端（OQ-IC-004）
                try:
                    self._related_images = json.loads(text) or []
                except (ValueError, TypeError):
                    self._related_images = []
                    logger.warning(
                        "ChatConsumer._pump: related_images 解析失败，忽略: %s", text[:200])
            # else: 未知 kind，静默忽略（前向兼容）
        return ('done', accumulated)

    async def _finalize_turn(self, accumulated_content: str,
                             related_images: list | None = None):
        """结束一轮：发 stream_end（v1.4.1 新增 related_images 字段），写入 assistant 记录。

        related_images 格式：[{"image_id": int, "source": str}, ...] 或 []
        OQ-IC-004 决策：related_images 不持久化到 chat_memory.append_message，
                       仅随 stream_end 实时发送给前端。

        IFC-141-704，MOD-141-07
        """
        # 构造 stream_end 载荷（related_images 为空时不加字段，向后兼容）
        payload: dict = {'type': 'stream_end'}
        if related_images:
            payload['related_images'] = related_images
        await self.send(json.dumps(payload))

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
            # v1.4.1：confirm 路径（写确认门）不涉及知识专家，related_images 恒为空（DEV-002）
            await self._finalize_turn(accumulated, related_images=[])
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
            from rest_framework.authtoken.models import Token  # noqa: PLC0415
            return Token.objects.select_related('user').get(key=token_key).user
        except Token.DoesNotExist:
            return None
        except Exception as exc:
            logger.error('ChatConsumer._get_user_by_token 异常: %s', exc)
            return None
