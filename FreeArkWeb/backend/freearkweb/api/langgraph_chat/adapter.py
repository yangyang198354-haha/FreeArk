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
from typing import AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

# 复用 OpenClaw 适配层的异常类型，使 ChatConsumer 的 except 分支零改动即可接管降级。
from api.openclaw_adapter import OpenClawUnavailableError

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
    async def stream_chat(cls, message: str,
                          session_key: str) -> AsyncGenerator[tuple[str, str], None]:
        orch = _get_orch()  # 构造失败 → OpenClawUnavailableError，交由 consumers 降级
        config = orch._cfg(session_key)  # thread_id=session_key：interrupt/resume 同线程
        try:
            async for kind, text in _drive(
                    orch, {"messages": [HumanMessage(content=message)]}, config):
                yield (kind, text)
        except asyncio.TimeoutError:
            raise  # 透传 → ChatConsumer 映射 TIMEOUT（与 OpenClaw 路径一致）
        except OpenClawUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("LangGraph 流式失败 session=%s: %s",
                         (session_key or "")[:8], exc)
            raise OpenClawUnavailableError(f"LangGraph 编排失败: {exc}") from exc

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
            logger.error("LangGraph resume 失败 session=%s: %s",
                         (session_key or "")[:8], exc)
            raise OpenClawUnavailableError(f"LangGraph 恢复失败: {exc}") from exc
