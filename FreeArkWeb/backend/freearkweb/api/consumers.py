"""
ChatConsumer — WebSocket 聊天代理（MOD-BE-CONS v1.5）

v1.5.0 变更（相对 v1.4，实现多模态提问 MOD-MQ-04）：
  - connect()：新增初始化 self._vision_persist_message = ''
  - receive()：新增读取 image_upload_id；UUID 格式校验；纯图片消息默认文案注入
  - _handle_chat()：签名扩展 upload_id 参数；vision_progress WS 通知；
    VisionServiceError / ImageExpiredError 降级错误消息；
    持久化步骤使用 _vision_persist_message 替换原始 user_message（若有）
  - _pump()：新增识别 "persist_enhanced_message" kind → 存入 _vision_persist_message，
    不转发 WS（透明内部协议）
  - 新增 _send_error() 辅助方法（统一 WS 错误帧构造）
  - 新增 _is_valid_uuid() 模块函数（upload_id 格式校验）

v1.4 变更（保持不变）：
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

@module MOD-BE-CONS, MOD-MQ-04
@implements IFC-CONS-001, IFC-CONS-002, IFC-CONS-003, IFC-CONS-004,
            IFC-MQ-04-001 (receive 扩展), IFC-MQ-04-002 (_handle_chat 扩展),
            IFC-MQ-04-003 (_pump 扩展)
@depends MOD-BE-MEM, MOD-MQ-03 (vision_service), MOD-MQ-05 (adapter 扩展)
@author sub_agent_software_developer

项目: FreeArk_ChatSession / v1.5.0_multimodal_question
文档引用: module_design.md MOD-MQ-04, architecture_design.md ADR-MQ-001
需求引用: REQ-FUNC-003, REQ-FUNC-006, REQ-FUNC-007, REQ-NFR-004
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
# v1.5.0 多模态提问（MOD-MQ-04）：VLM 异常类型
from api.vision_service import ImageExpiredError, ImageAccessDeniedError, VisionServiceError

logger = logging.getLogger('api.consumers')


def _is_valid_uuid(value: str) -> bool:
    """校验字符串是否为合法 UUID4 格式（upload_id 入口校验）。"""
    try:
        uuid.UUID(value, version=4)
        return True
    except (ValueError, AttributeError):
        return False


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
        # ── v1.5.0 新增（MOD-MQ-04）────────────────────────────────────────────
        # adapter 流结束后通过 "persist_enhanced_message" kind 回传含 VLM 描述的持久化消息；
        # _pump 识别后存入此字段；_handle_chat 持久化步骤使用此值替代原始 user_message
        self._vision_persist_message: str = ''

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

        # v1.6.0 RBAC：普通业主（role='user'）无业务功能权限，拒绝聊天 WS 连接。
        # WS 握手不经 HTTP 中间件（UserRoleApiGuardMiddleware 拦不到），故在此显式拦截，二者对齐。
        if getattr(user, 'role', None) == 'user':
            logger.warning('ChatConsumer: 普通业主(role=user)无聊天权限，拒绝连接')
            await self.close(code=4003)
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
        # v1.5.0：读取可选的 image_upload_id（REQ-FUNC-003，MOD-MQ-04）
        upload_id = data.get('image_upload_id')

        # upload_id 格式校验（若存在）：防止非 UUID 字符串进入 vision_service
        if upload_id is not None:
            if not isinstance(upload_id, str) or not _is_valid_uuid(upload_id):
                await self._send_error("IMAGE_INVALID", "图片引用无效")
                return

        # 纯图片消息（message 为空但有 upload_id）：后端注入默认提问文案（OQ-MQ-003）
        if upload_id and not user_message:
            user_message = "请帮我分析这张图片"

        # 向后兼容：不含 upload_id 且消息为空 → 与 v1.4.1 行为一致
        if not user_message and not upload_id:
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
            await self._handle_chat(user_message, upload_id=upload_id)
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

    async def _handle_chat(self, user_message: str, upload_id: str = None):
        """
        核心聊天处理（v1.5.0）：在 v1.4 基础上支持多模态图文消息。

        v1.5.0 新增（相对 v1.4，MOD-MQ-04）：
          1. upload_id 参数（默认 None，向后兼容）
          2. 若 upload_id 非空，预先校验 TTL（ImageExpiredError → 发错误帧，return）
          3. 若 upload_id 非空，在调用 adapter 前向前端发送 vision_progress 进度通知
          4. adapter.stream_chat 增加 upload_id + user_id 参数
          5. _pump 识别 "persist_enhanced_message" kind → 存入 _vision_persist_message
          6. 持久化步骤：若 _vision_persist_message 非空，使用该值代替 user_message
          7. 捕获 VisionServiceError → 发 IMAGE_ANALYSIS_FAILED 错误帧（WS 连接保持）
          8. 捕获 ImageExpiredError → 发 IMAGE_EXPIRED 错误帧（WS 连接保持）

        v1.4 不变点（ARCH-C-006）：
          - reasoning_token / reasoning_end / stream_token / stream_end 发送逻辑不变
          - ADR-001 / ADR-002 首行创建 session + 异步 LLM 标题逻辑不变

        @implements IFC-CONS-003, IFC-MQ-04-002
        """
        # 重置本轮视觉持久化消息（防上轮残留）
        self._vision_persist_message = ''

        try:
            # ── v1.5.0：upload_id 存在时先做 TTL 预检（consumers 层，减少后续失败概率）
            if upload_id is not None:
                try:
                    from api import vision_service as _vs
                    _vs.get_upload(upload_id, self.user.id)
                except ImageExpiredError:
                    await self._send_error("IMAGE_EXPIRED", "图片已过期，请重新上传")
                    return
                except ImageAccessDeniedError:
                    await self._send_error("IMAGE_INVALID", "图片引用无效")
                    return

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

            # v1.3 / v1.5.0：写入用户消息记录（REQ-FUNC-007，MOD-MQ-04）
            # 向后兼容策略：
            #   - upload_id 为 None（纯文字消息）：立即写原始 user_message（与 v1.4 一致）
            #   - upload_id 存在（含图消息）：跳过，由 _pump 收到 persist_enhanced_message
            #     后设置 self._vision_persist_message，流结束后统一写入增强消息（含 VLM 描述前缀）
            if self.chat_session is not None and upload_id is None:
                try:
                    await sync_to_async(chat_memory.append_message)(
                        self.chat_session, 'user', user_message,
                    )
                except Exception as exc:
                    logger.error('ChatConsumer: append_message(user) 失败: %s', exc)

            # ── v1.5.0：含图消息发送 vision_progress 进度通知（在 adapter 调用前）
            if upload_id is not None:
                await self.send(json.dumps({
                    'type': 'vision_progress',
                    'message': '正在分析图片，请稍候…',
                }))

            adapter = get_chat_adapter()  # 按 CHAT_BACKEND 选 OpenClaw / LangGraph
            status, accumulated_content = await self._pump(
                adapter.stream_chat(
                    message=augmented_message,
                    session_key=self.session_key,
                    upload_id=upload_id,
                    user_id=self.user.id if upload_id else None,
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

            # ── v1.5.0：含图消息持久化增强（MOD-MQ-04，REQ-FUNC-007）
            # 若 _pump 从 adapter 收到 "persist_enhanced_message"，使用增强消息覆盖已写入的
            # user 消息记录（含 VLM 描述前缀，格式：[图片描述：<VLM输出>] <原始文字>）
            if self._vision_persist_message and self.chat_session is not None:
                try:
                    # 先删除刚才写入的原始 user 消息，再写入含 VLM 描述的增强消息
                    # 注：chat_memory 若不支持更新，则重新 append 一条（历史会有两条 user msg）
                    # 根据现有实现，采用 append 方式补写增强消息（覆盖语义由前端展示逻辑处理）
                    # TODO: 如果 chat_memory 支持 update_last_user_message 则改为更新
                    await sync_to_async(chat_memory.append_message)(
                        self.chat_session, 'user', self._vision_persist_message,
                    )
                except Exception as exc:
                    logger.error('ChatConsumer: 写入含图增强消息失败（非致命）: %s', exc)
                finally:
                    self._vision_persist_message = ''  # 清空，防下轮残留
            # ─────────────────────────────────────────────────────────────────────

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

        # ── v1.5.0：VLM 相关异常降级处理（独立 except 块，不与主流程合并）──────
        except VisionServiceError as exc:
            # doubao-vision 2 次调用均失败（超时/5xx）→ 降级提示，WS 连接保持
            logger.error('ChatConsumer: VLM 分析失败: %s', exc)
            self._is_streaming = False
            await self._send_error(
                "IMAGE_ANALYSIS_FAILED",
                "图片分析暂时不可用，您可以用文字描述图片内容后重试",
            )
            return

        except ImageExpiredError as exc:
            # upload_id TTL 在 adapter 层再次取图时已过期（预检之后极少发生）
            logger.info('ChatConsumer: 图片引用已过期（adapter 层）: %s', exc)
            self._is_streaming = False
            await self._send_error("IMAGE_EXPIRED", "图片已过期，请重新上传")
            return

        except ImageAccessDeniedError as exc:
            logger.warning('ChatConsumer: 图片访问被拒绝（upload_id 用户不匹配）: %s', exc)
            self._is_streaming = False
            await self._send_error("IMAGE_INVALID", "图片引用无效")
            return
        # ─────────────────────────────────────────────────────────────────────────

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
            elif kind == 'persist_enhanced_message':
                # v1.5.0 新增（MOD-MQ-04，IFC-MQ-04-003）：
                # adapter 在 VLM 流完成后 yield 此 kind，携带含 VLM 描述的持久化消息。
                # 存入实例变量，由 _handle_chat 持久化步骤使用（不转发前端）。
                self._vision_persist_message = text
            # else: 未知 kind，静默忽略（前向兼容）
        return ('done', accumulated)

    async def _send_error(self, code: str, message: str) -> None:
        """
        v1.5.0 辅助方法（MOD-MQ-04）：构造并发送统一格式的 WS 错误帧。
        不关闭 WS 连接，用户可继续发消息（REQ-NFR-004 fail-open）。
        """
        await self.send(json.dumps({
            'type': 'error',
            'code': code,
            'message': message,
        }))

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
