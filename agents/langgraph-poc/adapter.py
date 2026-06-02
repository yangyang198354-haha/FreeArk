"""
langgraph-poc — ChatConsumer 的 drop-in 适配器

与 api/openclaw_adapter.py 的 OpenClawAdapter.stream_chat 保持**完全相同签名**：
    async def stream_chat(message: str, session_key: str)
        -> AsyncGenerator[tuple[str, str], None]   # (kind, text)，kind ∈ {reasoning,content}

迁移只需在 consumers.py 改一行 import：
    from api.openclaw_adapter import OpenClawAdapter      # 旧
    from api.langgraph_adapter import LangGraphAdapter as OpenClawAdapter  # 新

编排图在模块加载时编译一次并常驻（_ORCH），因此：
  - 无 gateway WS 跳转、无 openclaw CLI 子进程冷启动
  - 工具进程内直调
  - 复合意图并行 fan-out

流式：用 graph.astream(stream_mode="messages") 拿 aggregate 节点的 token 增量，
逐块 yield ('content', delta)。假模型非流式时退化为整段一次 yield，语义不变。
"""

from __future__ import annotations

from typing import AsyncGenerator

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from orchestrator import Orchestrator

# 进程常驻单例（warm）。生产里在 Django apps.ready() 或模块级构造。
_ORCH = Orchestrator()


class LangGraphAdapter:
    @classmethod
    async def stream_chat(cls, message: str,
                          session_key: str) -> AsyncGenerator[tuple[str, str], None]:
        seen_any = False
        async for chunk, meta in _ORCH.graph.astream(
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
            result = await _ORCH.run(message)
            yield ("content", result["answer"])
