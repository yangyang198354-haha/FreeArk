"""
api.persona_intent —— 从自然语言里识别"改称呼/改语气"意图并抽取结构化偏好（v1.13.0）

对应 US-003 AC-003-01/02（v1.12.0 标为 Could Have 且"待 PM 确认"，当时未纳入范围，
2026-08-22 确认补做）。

## 为什么放在 consumer 层而不是做成 LangGraph 工具

1. `_general`（域外/闲聊）节点明确**不绑定任何工具**（纯 LLM 自然语言，token 经
   adapter._drive 直接 user-stream）。而"以后叫我胖子熊大人"这类话几乎必然被路由
   判为域外落到该节点——给 general 挂工具会动到它的流式契约。
2. 人格是**用户档案**，不是设备操作，不该混进受写确认门（_gate interrupt）管辖的
   工具集里；走工具还得为它单开一条免确认通道。
3. 放在 stream_chat 之前处理，能保证**本轮回复就用新称呼**，而不是下一轮才生效。

## 两级设计（成本控制）

- 一级：廉价正则预筛。绝大多数消息（查能耗、报故障…）在这里就被挡掉，零 LLM 开销。
- 二级：命中预筛才调一次 temperature 0 的小模型做结构化抽取，输出 JSON。

预筛是"宁可漏、不可滥"——漏判只是这次没改成（用户会再说一次或走设置页），
滥判则会莫名其妙改掉用户的称呼。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

from .persona import MAX_FIELD_LEN, normalize_persona

logger = logging.getLogger('api.persona_intent')

#: 一级预筛：出现这些说法才可能是在谈"怎么称呼/什么语气"。
#: 命中即进二级抽取；未命中直接放行（零开销）。
_PREFILTER = re.compile(
    r'(叫我|称呼我|喊我|别叫我|不要叫我|改口|以后叫|换个称呼|怎么称呼'
    r'|你的名字|你叫什么|你以后是|你就是我的'
    r'|语气|口吻|说话风格|回复风格|正式一点|随意一点|简短一点|啰嗦'
    r'|恢复默认|重置人格|默认称呼|默认风格)'
)

_EXTRACT_PROMPT = (
    "你是一个意图抽取器。判断用户这句话是否在要求改变 AI 助手对他的**称呼**、"
    "AI 助手的**自称身份**，或对话的**语气风格**。\n"
    "只输出一个 JSON 对象，不要任何解释、不要代码围栏。字段：\n"
    '  "action": "set" | "reset" | "none"\n'
    '  "address": 用户希望被怎么称呼（如"胖子熊大人"），没提就省略\n'
    '  "identity": 用户希望 AI 自称什么（如"管家"），没提就省略\n'
    '  "tone": 用户希望的语气风格（如"简洁"、"轻松"），没提就省略\n'
    "规则：\n"
    "- 明确要求恢复默认/重置 → action=\"reset\"，不带其它字段。\n"
    "- 只是提到名字但不是要求改称呼（如问「你叫什么」、「张三家的设备」）→ action=\"none\"。\n"
    "- 用户说「叫我X」「称呼我为X」「以后喊我X」→ address=\"X\"。\n"
    "- 用户说「你以后是我的X」「你就叫X」（指 AI 自己）→ identity=\"X\"。\n"
    "- 抽取出的值只保留称谓本身，不要带「叫我」「称呼我」等动词。\n"
    "- 无法确定时一律 action=\"none\"，不要猜。\n"
    "示例：\n"
    '  「以后叫我胖子熊大人」→ {"action":"set","address":"胖子熊大人"}\n'
    '  「别叫舰长了，叫我老板，语气随意点」→ {"action":"set","address":"老板","tone":"随意"}\n'
    '  「恢复默认的副官风格」→ {"action":"reset"}\n'
    '  「查一下今天的能耗」→ {"action":"none"}\n'
)

_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)


def looks_like_persona_change(message: str) -> bool:
    """一级预筛：这句话是否**可能**在谈称呼/语气。未命中则完全不调 LLM。"""
    return bool(_PREFILTER.search(message or ''))


def _parse(text: str) -> Optional[dict]:
    """解析模型输出——对 ```json 围栏、前后散文、非法字段鲁棒。"""
    m = _JSON_RE.search(text or '')
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    action = data.get('action')
    if action == 'reset':
        return {'action': 'reset'}
    if action != 'set':
        return None

    out: dict = {'action': 'set'}
    for key in ('identity', 'address', 'tone'):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[:MAX_FIELD_LEN]
    # action=set 却一个字段都没抽到 → 视为无效，不改任何东西
    return out if len(out) > 1 else None


async def detect_persona_change(message: str, llm) -> Optional[dict]:
    """识别并抽取人格变更意图。

    返回 {'action': 'reset'} / {'action': 'set', 'address'?, 'identity'?, 'tone'?}；
    非人格变更或任何异常 → None（fail-open：绝不因为抽取失败把聊天打挂）。
    """
    if not looks_like_persona_change(message):
        return None
    if llm is None:
        return None
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        ai = await llm.ainvoke([
            SystemMessage(content=_EXTRACT_PROMPT),
            HumanMessage(content=message),
        ])
        return _parse(getattr(ai, 'content', '') or '')
    except Exception as exc:  # noqa: BLE001
        logger.warning('persona 意图抽取失败（按无变更处理）: %s', exc)
        return None


def apply_persona_change(current: Optional[dict], change: dict) -> dict:
    """把抽取结果合并进现有 persona，返回**规范形态**的新 persona。

    reset → 清空（回落默认人格）；set → 只覆盖抽到的键，其余保留。
    """
    if change.get('action') == 'reset':
        return {}
    merged = normalize_persona(current)
    for key in ('identity', 'address', 'tone'):
        if change.get(key):
            merged[key] = change[key]
    return merged
