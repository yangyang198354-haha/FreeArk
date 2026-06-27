"""
api.langgraph_chat.adapter —— ChatConsumer 的 drop-in 适配器

与 api.openclaw_adapter.OpenClawAdapter.stream_chat **完全相同签名**：
    async def stream_chat(message: str, session_key: str)
        -> AsyncGenerator[tuple[str, str], None]   # (kind, text)，kind ∈ {reasoning,content}

阶段 A 切换：由 api.chat_backend.get_chat_adapter() 按 settings.CHAT_BACKEND 选中本类，
ChatConsumer 调用点与异常处理完全复用——失败时 raise 同一个 OpenClawUnavailableError，
让 consumers.py 既有降级路径（OPENCLAW_UNAVAILABLE / TIMEOUT）原样接管。

编排图惰性单例（_get_orch），首次使用时构造并常驻；也可由 api.apps.ApiConfig.ready()
在 worker 启动时预热（warm()）。因此：
  - 无 gateway WS 跳转、无 openclaw CLI 子进程冷启动
  - 工具进程内直调
  - 复合意图并行 fan-out

流式：用 graph.astream(stream_mode="messages") 拿 aggregate 节点的 token 增量，
逐块 yield ('content', delta)。假模型/非流式时退化为整段一次 yield，语义不变。

文档引用：PHASE3_ROLLOUT.md 阶段 A.2/A.3
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncGenerator, Optional

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

# 统一降级异常（v1.7.0 迁移自 api.openclaw_adapter → api.chat_exceptions），
# 使 ChatConsumer 的 except 分支零改动接管降级（WS 错误码向后兼容）。
from api.chat_exceptions import OpenClawUnavailableError
# v1.5.0：VLM 服务（MOD-MQ-03）。ImageExpiredError/ImageAccessDeniedError 由调用方捕获。
from api import vision_service
from api.vision_service import ImageExpiredError, ImageAccessDeniedError, VisionServiceError

logger = logging.getLogger("api.langgraph_chat.adapter")

# 委托子专家等「内部生成」的流式抑制标签：orchestrator 给这类 LLM 调用打此 tag，
# _drive 据 meta["tags"] 跳过——它们的原始产物不应流给用户（仅供发起方整合）。
# 定义在本（始终可导入、无 langgraph 依赖的）模块，由 orchestrator 反向 import，
# 既单一真源、又不破坏 openclaw 回退路径下 adapter 的可导入性。
INTERNAL_NOSTREAM_TAG = "fa_internal_nostream"

# 思考过程（折叠框）展示用：专家内部 id → 面向用户的中文标签。阶段(b) 编排步骤进度。
# 仅用于 reasoning 流（可折叠的"思考过程"），绝不进入正式答复——答复保持第一人称、
# 不暴露内部分工（见 PR#46 orchestrator._aggregate 的"严禁提及专家/路由"约束）。
_EXPERT_CN = {
    "energy-expert": "能耗分析",
    "inspection-expert": "巡检诊断",
    "sanheng-knowledge": "三恒知识",
}


def _expert_cn(name: str) -> str:
    return _EXPERT_CN.get(name, name)


def _classify_stream_failure(exc: Exception,
                             session_key: Optional[str]) -> Optional[OpenClawUnavailableError]:
    """把 _drive/astream 抛出的底层异常分类成面向用户的降级异常。

    动机：原先 `except Exception` 一律包成"方舟智能体暂时离线"，把代码 bug
    （如 langchain-openai 0.3.x 删函数引发的 AttributeError）也伪装成"离线"，
    严重误导排查。此处按可识别特征分流：

    返回值：
      - OpenClawUnavailableError（带 user_message/code）：可归类的运行时失败，
        consumers 据此给用户具体提示（context 超限 / 限流 / 配置错误 / 真·暂时不可用）。
      - None：判定为代码级 bug / 未知内部错误——**不应伪装成"离线"**，调用方
        原样 re-raise，由 consumers 的通用 except 映射为 INTERNAL_ERROR，便于暴露。

    分类仅靠异常类型 + 文本特征（不硬依赖 openai SDK 异常类，避免导入耦合）。
    """
    sk = (session_key or "")[:8]

    # 代码级 bug：类型/属性/导入等——这些不是"后端离线"，原样上抛以便被发现
    if isinstance(exc, (AttributeError, TypeError, ImportError, NameError,
                        KeyError, IndexError, AssertionError)):
        return None

    msg = str(exc).lower()

    # 1. context / token 超限（多图描述 + 历史过长最常见）——用户可精简后重试
    if any(k in msg for k in (
        "context length", "context_length", "maximum context", "context window",
        "maximum tokens", "max tokens", "too many tokens", "reduce the length",
        "string too long", "exceeds the maximum",
    )):
        logger.warning("LangGraph 流式失败 session=%s [CONTEXT_LENGTH_EXCEEDED]: %s", sk, exc)
        return OpenClawUnavailableError(
            f"context length exceeded: {exc}",
            user_message="本轮内容过长（含图片描述/历史对话），超出 AI 单次处理上限，"
                         "请减少图片数量或精简问题后重试",
            code="CONTEXT_LENGTH_EXCEEDED",
        )

    # 2. 限流 429 —— 稍候重试
    if "rate limit" in msg or "ratelimit" in msg or "429" in msg or "too many requests" in msg:
        logger.warning("LangGraph 流式失败 session=%s [RATE_LIMITED]: %s", sk, exc)
        return OpenClawUnavailableError(
            f"rate limited: {exc}",
            user_message="AI 服务当前繁忙（请求过多），请稍候片刻再重试",
            code="RATE_LIMITED",
        )

    # 3. 鉴权 / 配置错误 401/403 —— 非用户可修，提示联系管理员（运维看日志 ERROR）
    if any(k in msg for k in (
        "authentication", "invalid api key", "invalid_api_key", "incorrect api key",
        "401", "403", "permission denied", "unauthorized",
    )):
        logger.error("LangGraph 流式失败 session=%s [LLM_CONFIG_ERROR]: %s", sk, exc)
        return OpenClawUnavailableError(
            f"auth/config error: {exc}",
            user_message="AI 服务配置异常，请联系管理员",
            code="LLM_CONFIG_ERROR",
        )

    # 4. 其它（5xx / 连接 / 超时类 / 未识别）—— 真·暂时不可用，走默认"离线"文案
    logger.error("LangGraph 流式失败 session=%s: %s", sk, exc)
    return OpenClawUnavailableError(
        f"LangGraph 编排失败: {exc}",
        user_message=None,  # consumers 用默认"方舟智能体暂时离线，请稍后再试"
        code="OPENCLAW_UNAVAILABLE",
    )


_ORCH = None  # 进程常驻单例（惰性构造）


def _get_orch():
    """惰性构造编排器单例。构造失败抛 OpenClawUnavailableError（统一降级通道）。"""
    global _ORCH
    if _ORCH is None:
        try:
            from .orchestrator import Orchestrator
            _ORCH = Orchestrator()
        except Exception as exc:  # noqa: BLE001
            logger.error("LangGraph 编排器构造失败: %s", exc)
            raise OpenClawUnavailableError(f"LangGraph 编排器不可用: {exc}") from exc
    return _ORCH


def warm() -> bool:
    """供 AppConfig.ready() 在 worker 启动时预热。失败仅记日志、不抛（不阻断启动）。"""
    try:
        _get_orch()
        logger.info("LangGraph 编排器已预热")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("LangGraph 编排器预热失败（将在首个请求重试）: %s", exc)
        return False


async def _drive(orch, payload, config) -> AsyncGenerator[tuple[str, str], None]:
    """驱动一次 graph.astream（payload 为初始输入 dict 或 Command(resume=...)）。

    流式策略（2026-06-14 改：让用户尽快、持续看到增量，消灭长静默）：
      - **单专家**：透传 `expert` 节点的 token（即最终答复，逐 token 流）；aggregate 只会把
        同一整段再发一次 → 跳过避免重复。
      - **多专家**：expert 们并行 token 会交错、语义混乱 → 跳过；改流 `aggregate` 的融合结果。
      - 专家数由 `route` 节点的 plan 得知（updates 流，先于 expert token 到达）。
      - `route` 节点自身的 token（JSON 分类结果）一律不透传给用户。
      - 编排步骤进度（理解/路由分工/生成）下发 ('reasoning', 文案)，作为"思考过程"
        进入前端折叠框（阶段b）；首个 content 到达时 consumers 自动发 reasoning_end 折叠。
      - updates 捕获 __interrupt__（Tier-2 写确认门）→ ('confirm', json) 后立即返回。
    无任何 content 流出时（异常/退化）读最终态整段补发。
    """
    seen_any = False
    interrupted = False
    num_experts = None  # 由 route 的 plan 得知；None=route 未完成
    # 起步即反馈，消灭最初 1~2s 的纯静默；作为思考过程首行进入折叠框（阶段b）
    yield ("reasoning", "🔍 正在理解你的问题…\n")
    async for mode, data in orch.graph.astream(
            payload, config, stream_mode=["updates", "messages"]):
        if mode == "messages":
            chunk, meta = data
            node = meta.get("langgraph_node")
            # 委托子专家等内部生成（带 INTERNAL_NOSTREAM_TAG）一律不透传：否则委托型
            # 专家会把「子专家完整答案 + 自身整合终稿」两份近似内容流给用户（2026-06-22）。
            if INTERNAL_NOSTREAM_TAG in (meta.get("tags") or ()):
                continue
            # 只透传流式增量（AIMessageChunk）；排除节点返回的终态整条 AIMessage。
            # AIMessageChunk 是 AIMessage 子类——若两者均放行，多专家 aggregate 会把
            # 融合答复发两遍（流式增量 + 终态整条），落库即逐字 2 倍（2026-06-22 修复）。
            # 非流式模型只产终态 AIMessage 时全被挡掉 → 由循环后 seen_any 兜底补发一次。
            if not isinstance(chunk, AIMessageChunk):
                continue
            # 仅透传"会呈现给用户"的节点：单专家透 expert token，多专家透 aggregate。
            is_user_stream = (
                (node == "expert" and num_experts == 1)
                or (node == "aggregate" and num_experts != 1)
            )
            if not is_user_stream:
                continue
            # (a) 模型原生思考：先透传 reasoning_content（思考阶段 content 多为空）。
            # 由 _ReasoningChatOpenAI 注回 additional_kwargs（langchain 默认丢弃）；
            # 首个 content 到达时 consumers 自动发 reasoning_end → 折叠思考框。
            rc = (chunk.additional_kwargs or {}).get("reasoning_content")
            if rc:
                yield ("reasoning", rc)
            if chunk.content:
                seen_any = True
                yield ("content", chunk.content)
            # route 等其他节点的 token 不透传
        elif mode == "updates" and isinstance(data, dict):
            if "__interrupt__" in data:
                intr = data["__interrupt__"]
                val = intr[0].value if isinstance(intr, (list, tuple)) and intr else intr
                interrupted = True
                yield ("confirm", json.dumps(val, ensure_ascii=False))
                return  # 暂停，等待 resume_chat
            route_out = data.get("route")
            if isinstance(route_out, dict) and "plan" in route_out:
                plan = route_out.get("plan") or []
                num_experts = len(plan) or None
                # 阶段(b)：把路由分工作为思考过程展示在折叠框（仅 reasoning 流，不进答复）。
                names = [
                    _expert_cn(item[0])
                    for item in plan
                    if isinstance(item, (list, tuple)) and item and item[0]
                ]
                if names:
                    yield ("reasoning", "🧭 已确定方向：" + "、".join(names) + "\n")
                yield ("reasoning", "📊 正在调取数据并生成回复…\n")

    # ── v1.4.1：在 astream 完成后，从最终 State 取 related_images（IFC-141-601）──
    # 与 seen_any 兜底的 aget_state 合并为一次调用，避免两次 DB round-trip（ADR-IC-002）。
    # 同时处理 related_images yield 和 非流式兜底内容补发：
    if not interrupted:
        try:
            snap = await orch.graph.aget_state(config)
        except Exception as snap_exc:   # noqa: BLE001 — aget_state 失败不影响主流程
            logger.warning("_drive: aget_state 失败（非致命）: %s", snap_exc)
            snap = None

        # related_images：从最终 State 读取（aggregate 节点已统一汇聚去重）
        try:
            related_images = (snap.values or {}).get("related_images", []) if snap else []
            if related_images:
                yield ("related_images", json.dumps(related_images, ensure_ascii=False))
        except Exception as ri_exc:   # noqa: BLE001 — 图片引用提取失败不影响主流程
            logger.warning("_drive: 提取 related_images 失败（非致命）: %s", ri_exc)

        # 非流式兜底（seen_any=False 时补发最终答复）
        if not seen_any:
            msgs = (snap.values or {}).get("messages", []) if snap else []
            if msgs and getattr(msgs[-1], "content", None):
                yield ("content", msgs[-1].content)
    # ──────────────────────────────────────────────────────────────────────────


class LangGraphAdapter:
    @classmethod
    async def stream_chat(
        cls,
        message: str,
        session_key: str,
        upload_ids: Optional[list] = None,  # v1.9.0 新参数（list[str]）
        upload_id: Optional[str] = None,    # v1.5.0 旧参数（向后兼容保留）
        user_id: Optional[int] = None,
        user_scope=None,  # v1.8.0 新增（MOD-180-10）：UserScope or None，向后兼容默认 None
    ) -> AsyncGenerator[tuple[str, str], None]:
        """
        流式聊天入口（v1.9.0 扩展）。

        v1.9.0 变更（相对 v1.5.0）：
          - 新增 upload_ids: list[str] 参数（多图路径，ADR-MI-001）
          - 旧参数 upload_id: str 保留（向后兼容，自动包装为 upload_ids=[upload_id]）
          - 多图 VLM：先 yield 所有进度帧，再并发分析（analyze_images_batch）
          - 部分失败：占位文字注入（ADR-MI-004），yield image_analysis_partial kind
          - 全部失败：raise VisionServiceError（与 v1.5.0 路径一致）
          - 持久化：多图格式 "[图片1描述：<d1>] [图片2描述：<d2>] ... <原始文字>"

        向后兼容：upload_ids=None, upload_id=None 时行为与 v1.4.1 完全一致。
        """
        import json as _json

        orch = _get_orch()  # 构造失败 → OpenClawUnavailableError，交由 consumers 降级
        config = orch._cfg(session_key)  # thread_id=session_key：interrupt/resume 同线程

        # 向后兼容：旧参数 upload_id（单数）→ upload_ids 列表
        if upload_ids is None and upload_id is not None:
            upload_ids = [upload_id]

        enhanced_message = message
        persist_msg: Optional[str] = None  # 多图持久化消息（流结束后 yield）

        # ── VLM 前置调用（仅当 upload_ids 非空，ADR-MI-001）──────────────────
        if upload_ids is not None and user_id is not None:
            total = len(upload_ids)

            # 1. 逐图取字节（ImageExpiredError / ImageAccessDeniedError 由 consumers 捕获）
            image_bytes_list = []
            for uid in upload_ids:
                image_bytes_list.append(vision_service.get_upload(uid, user_id))

            # 2. 先 yield 所有进度帧（最简方案，无 Queue 协调复杂度，ADR-MI-001 注释）
            #    进度帧立即发出（给用户期待感），然后 VLM 并发运行
            for i in range(total):
                yield ("vision_progress", f"正在分析第{i+1}/{total}张图片，请稍候…")

            # 3. 并发调用 VLM（ADR-MI-001：asyncio.gather with return_exceptions=True）
            try:
                results = await vision_service.analyze_images_batch(
                    image_bytes_list, message
                )
            finally:
                # 4. 立即释放图片字节引用（REQ-NFR-002 内存约束）
                del image_bytes_list

            # 5. 逐图清理临时存储（VLM 完成后释放 dict 内存）
            for uid in upload_ids:
                vision_service.delete_upload(uid)

            # 6. 构建注入 LangGraph 的增强消息（REQ-MI-005，ADR-MI-004 格式）
            failed_indices = []
            desc_lines = []
            for i, result in enumerate(results):
                if result is None:
                    failed_indices.append(i)
                    desc_lines.append(f"[用户图片{i+1}分析：图片分析失败，已跳过]")
                else:
                    desc_lines.append(f"[用户图片{i+1}分析：{result}]")

            enhanced_message = "\n".join(desc_lines) + f"\n\n{message}"

            # 7. 全部失败：raise VisionServiceError（与 v1.5.0 全失败降级路径一致）
            if len(failed_indices) == total:
                raise VisionServiceError(
                    "图片分析暂时不可用，您可以用文字描述图片内容后重试"
                )

            # 8. 部分失败通知（非阻塞 kind，ADR-MI-004，REQ-MI-009）
            #    consumers._pump 识别后发 IMAGE_ANALYSIS_PARTIAL WS 错误帧（非阻塞）
            if failed_indices:
                yield ("image_analysis_partial", _json.dumps({
                    "failed_indices": failed_indices,
                    "total": total,
                }, ensure_ascii=False))

            # 9. 构建持久化消息（REQ-MI-008：有序多图格式）
            persist_parts = []
            for i, result in enumerate(results):
                if result is None:
                    persist_parts.append(f"[图片{i+1}描述：图片分析失败]")
                else:
                    persist_parts.append(f"[图片{i+1}描述：{result}]")
            persist_msg = " ".join(persist_parts) + f" {message}"
        # ── VLM 前置调用结束 ───────────────────────────────────────────────────

        try:
            # 多图场景不再使用单图 vision_description 字段（描述已注入 enhanced_message）
            _payload: dict = {
                "messages": [HumanMessage(content=enhanced_message)],
                "vision_description": None,
            }
            # v1.8.0（MOD-180-10）：若 user_scope 非 None，写入初始 State（数据隔离）
            if user_scope is not None:
                _payload["user_scope"] = user_scope
            async for kind, text in _drive(orch, _payload, config):
                yield (kind, text)

            # 10. 流结束后，通过特殊 kind 回传持久化用的增强消息（REQ-MI-008）
            if persist_msg is not None:
                yield ("persist_enhanced_message", persist_msg)

        except asyncio.TimeoutError:
            raise  # 透传 → ChatConsumer 映射 TIMEOUT（与 OpenClaw 路径一致）
        except OpenClawUnavailableError:
            raise
        except (ImageExpiredError, ImageAccessDeniedError, VisionServiceError):
            raise  # VLM 相关异常透传给 consumers 的专用 except 块
        except Exception as exc:  # noqa: BLE001
            classified = _classify_stream_failure(exc, session_key)
            if classified is None:
                # 代码级 bug：保留完整 traceback，原样上抛 → consumers INTERNAL_ERROR
                logger.exception("LangGraph 流式异常(代码级) session=%s: %s",
                                 (session_key or "")[:8], exc)
                raise
            raise classified from exc

    @classmethod
    async def resume_chat(cls, session_key: str,
                          decision: dict) -> AsyncGenerator[tuple[str, str], None]:
        """阶段 E：用户确认后恢复图执行。decision 形如 {"approved": True/False}。
        必须与 stream_chat 同进程（同一 WS 连接），MemorySaver 持有该 thread 的检查点。"""
        from langgraph.types import Command
        orch = _get_orch()
        config = orch._cfg(session_key)
        try:
            async for kind, text in _drive(orch, Command(resume=decision), config):
                yield (kind, text)
        except asyncio.TimeoutError:
            raise
        except OpenClawUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            classified = _classify_stream_failure(exc, session_key)
            if classified is None:
                logger.exception("LangGraph resume 异常(代码级) session=%s: %s",
                                 (session_key or "")[:8], exc)
                raise
            raise classified from exc
