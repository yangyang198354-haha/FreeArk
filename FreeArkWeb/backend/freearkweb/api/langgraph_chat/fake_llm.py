"""
api.langgraph_chat.fake_llm —— 离线确定性假模型（带可调延迟）

目的：在没有 DeepSeek API key 的环境（CI / 本地单测）里，依然能真实跑通
LangGraph 的图遍历、工具调用、并行 fan-out，从而验证编排接线并度量编排层自身
开销。它是合规的 langchain_core BaseChatModel 子类，bind_tools / ainvoke /
graph.astream 全链路都按真实代码路径走——唯一被替换的是「LLM 推理耗时」，
用 asyncio.sleep(latency) 模拟。

由 settings.LANGGRAPH_USE_FAKE_LLM=True 启用（见 orchestrator._make_llm）。

脚本化行为：
  - 收到的最后一条 HumanMessage 文本含 "TOOLCALL:<name>" → 返回一次 tool_call
  - 收到 ToolMessage（工具已回结果）→ 返回最终自然语言答复
  - 否则 → 直接返回一句最终答复
这足以驱动 ReAct 单专家节点与 supervisor 路由。
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any, List, Optional

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun, CallbackManagerForLLMRun)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

_DEFAULT_LATENCY = float(os.environ.get("LANGGRAPH_FAKE_LATENCY", "0.05"))


class LatencyFakeChat(BaseChatModel):
    """带模拟延迟的脚本化假聊天模型。"""

    latency: float = _DEFAULT_LATENCY
    tools: List[Any] = []
    final_text: str = "（已综合各专家结论给出回复）"

    @property
    def _llm_type(self) -> str:
        return "latency-fake-chat"

    def bind_tools(self, tools: List[Any], **kwargs: Any) -> "LatencyFakeChat":
        return self.model_copy(update={"tools": list(tools)})

    def _script(self, messages: List[BaseMessage]) -> AIMessage:
        # 已经有工具结果回来了 → 给最终答复
        if any(isinstance(m, ToolMessage) for m in messages):
            return AIMessage(content=self.final_text)
        # 找最后一条用户消息，看是否要求触发工具
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        text = (last_human.content if last_human else "") or ""
        if "TOOLCALL:" in text and self.tools:
            name = text.split("TOOLCALL:", 1)[1].split()[0].strip()
            valid = {getattr(t, "name", None) for t in self.tools}
            if name in valid:
                return AIMessage(
                    content="",
                    tool_calls=[{"name": name, "args": {}, "id": "call_fake_1"}],
                )
        return AIMessage(content=self.final_text)

    def _generate(self, messages: List[BaseMessage],
                  stop: Optional[List[str]] = None,
                  run_manager: Optional[CallbackManagerForLLMRun] = None,
                  **kwargs: Any) -> ChatResult:
        time.sleep(self.latency)
        return ChatResult(generations=[ChatGeneration(message=self._script(messages))])

    async def _agenerate(self, messages: List[BaseMessage],
                         stop: Optional[List[str]] = None,
                         run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
                         **kwargs: Any) -> ChatResult:
        await asyncio.sleep(self.latency)
        return ChatResult(generations=[ChatGeneration(message=self._script(messages))])
