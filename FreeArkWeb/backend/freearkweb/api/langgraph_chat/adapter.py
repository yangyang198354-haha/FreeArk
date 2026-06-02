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
import logging
from typing import AsyncGenerator, Optional

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

# 复用 OpenClaw 适配层的异常类型，使 ChatConsumer 的 except 分支零改动即可接管降级。
from api.openclaw_adapter import OpenClawUnavailableError

logger = logging.getLogger("api.langgraph_chat.adapter")

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


class LangGraphAdapter:
    @classmethod
    async def stream_chat(cls, message: str,
                          session_key: str) -> AsyncGenerator[tuple[str, str], None]:
        orch = _get_orch()  # 构造失败 → OpenClawUnavailableError，交由 consumers 降级
        seen_any = False
        try:
            async for chunk, meta in orch.graph.astream(
                {"messages": [HumanMessage(content=message)]},
                stream_mode="messages",
            ):
                # 只透传聚合节点产出的最终回复 token，避免把专家中间态吐给用户
                if meta.get("langgraph_node") != "aggregate":
                    continue
                if isinstance(chunk, (AIMessage, AIMessageChunk)) and chunk.content:
                    seen_any = True
                    yield ("content", chunk.content)

            if not seen_any:
                # 非流式模型兜底：取最终态整段返回
                result = await orch.run(message)
                yield ("content", result["answer"])
        except asyncio.TimeoutError:
            # 透传给 ChatConsumer，映射为 TIMEOUT（与 OpenClaw 路径一致）
            raise
        except OpenClawUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("LangGraph 流式失败 session=%s: %s",
                         (session_key or "")[:8], exc)
            raise OpenClawUnavailableError(f"LangGraph 编排失败: {exc}") from exc
