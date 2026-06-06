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

    多模式流：
      - messages 模式：透传 aggregate 节点的最终回复 token → ('content', delta)
      - updates 模式：捕获 __interrupt__（Tier-2 写确认门）→ ('confirm', json) 后立即返回
    非流式模型（如 fake / 单专家 passthrough）无 aggregate token 时，读最终态整段补发。
    """
    seen_any = False
    interrupted = False
    async for mode, data in orch.graph.astream(
            payload, config, stream_mode=["updates", "messages"]):
        if mode == "messages":
            chunk, meta = data
            if meta.get("langgraph_node") != "aggregate":
                continue
            if isinstance(chunk, (AIMessage, AIMessageChunk)) and chunk.content:
                seen_any = True
                yield ("content", chunk.content)
        elif mode == "updates" and isinstance(data, dict) and "__interrupt__" in data:
            intr = data["__interrupt__"]
            val = intr[0].value if isinstance(intr, (list, tuple)) and intr else intr
            interrupted = True
            yield ("confirm", json.dumps(val, ensure_ascii=False))
            return  # 暂停，等待 resume_chat

    if not seen_any and not interrupted:
        # 非流式兜底：从最终态取整段答复（不重跑图，避免重复副作用）
        snap = await orch.graph.aget_state(config)
        msgs = (snap.values or {}).get("messages", []) if snap else []
        if msgs and getattr(msgs[-1], "content", None):
            yield ("content", msgs[-1].content)


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
