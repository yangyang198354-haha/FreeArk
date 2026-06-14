"""
langgraph-poc — 离线确定性假模型（带可调延迟）

目的：在没有 DeepSeek API key 的环境里，依然能真实跑通 LangGraph 的图遍历、
工具调用、并行 fan-out，从而度量「编排层自身开销」并证明并行 < 串行。

它是一个合规的 langchain_core BaseChatModel 子类，因此 bind_tools / ainvoke /
graph.astream 全链路都按真实代码路径走——唯一被替换的是「LLM 推理耗时」，
用 asyncio.sleep(FAKE_LATENCY) 模拟（默认对齐实测 deepseek-v4-flash 单轮 ~10s）。

脚本化行为：
  - 收到的最后一条 HumanMessage 文本含 "TOOLCALL:<name>" → 返回一次 tool_call
  - 收到 ToolMessage（工具已回结果）→ 返回最终自然语言答复
  - 否则 → 直接返回一句最终答复
这足以驱动 ReAct 单专家节点 与 supervisor 路由。
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

# 默认单轮延迟（秒）。实测 deepseek-v4-flash 经 OpenClaw 端到端单专家 ~20.9s，
# 其中纯推理约一半。PoC 取 1.0s 让 bench 快速跑完；改 FAKE_LATENCY 可逼近真值。
_DEFAULT_LATENCY = float(os.environ.get("POC_FAKE_LATENCY", "1.0"))


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
        # 解析最后一条用户消息中的 TOOLCALL:<name> 链（按出现顺序，支持多轮/委托链）。
        # 以「已回来的 ToolMessage 数」作为游标定位下一个待发起的工具调用。
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
        text = (last_human.content if last_human else "") or ""
        valid = {getattr(t, "name", None) for t in self.tools}
        requested = [
            tok.split()[0].strip() for tok in text.split("TOOLCALL:")[1:]
        ] if "TOOLCALL:" in text else []
        requested = [n for n in requested if n in valid]  # 仅保留已绑定的工具
        done = sum(1 for m in messages if isinstance(m, ToolMessage))
        if done < len(requested):
            name = requested[done]
            return AIMessage(
                content="",
                tool_calls=[{"name": name, "args": {}, "id": f"call_poc_{done + 1}"}],
            )
        # 脚本耗尽（或本无工具脚本）→ 最终答复
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
