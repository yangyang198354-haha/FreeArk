"""
api.persona —— 副官人格偏好的规范形态与归一化（v1.13.0）

## 为什么需要这个模块

v1.12.0 的 persona 只有两个键，语义是混的：

  - `greeting_style` 名为"问候风格"，实际承载的是**副官自己的身份**（默认"副官"）
  - `tone_style` 在默认分支被当作**对用户的称呼**（"尊敬的舰长大人"），
    在自定义分支却被拼成"请以'X'风格与当前用户交流"，变成了**语气**

后果（2026-08-22 生产实测）：把 tone_style 设成"胖子熊大人"，注入的提示是
"请以'胖子熊大人'风格与当前用户交流"，模型直接把它当成自己的名字，答
"我是胖子熊大人，智能方舟的副官"——与用户意图完全相反。

本模块把 persona 拆成三个语义单一的键，并对历史键做只读兼容：

  | 键         | 含义             | 默认               |
  |------------|------------------|--------------------|
  | `identity` | 副官自称         | 智能方舟的副官     |
  | `address`  | 如何称呼用户     | 尊敬的舰长大人     |
  | `tone`     | 语气风格         | 无                 |

历史键映射（只读兼容，写入一律用新键）：
  `greeting_style` → `identity`；`tone_style` → `address`

⚠️ 迁移风险为零：改造时生产库 126 个用户中 persona 非空的为 **0** 个
   （该字段自 v1.12.0 上线从未被写入过——写入通路当时就没接通）。
   故无需数据迁移，只保留 API 层的入参兼容。
"""

from __future__ import annotations

import re
from typing import Optional

DEFAULT_IDENTITY = '智能方舟的副官'
DEFAULT_ADDRESS = '尊敬的舰长大人'

#: 规范键；写入 DB 与对外 API 一律只用这三个
CANONICAL_KEYS = ('identity', 'address', 'tone')

#: 历史键 → 规范键（只读兼容）
_LEGACY_KEY_MAP = {
    'greeting_style': 'identity',
    'tone_style': 'address',
}

#: 单字段长度上限（与 PersonaSerializer 保持一致）
MAX_FIELD_LEN = 50

#: 提示注入风险模式——命中则拒绝写入
_INJECTION_PATTERNS = re.compile(
    r'(?:忽略|无视|ignore|disregard|system\s*prompt|系统提示|'
    r'你现在是|you\s+are\s+now|角色扮演|role.?play|'
    r'输出以上|reveal.*(?:system|prompt|instruction)|'
    r'停止遵循|stop\s*following)',
    re.IGNORECASE,
)

#: 控制字符（含换行/制表/零宽）——persona 值不允许包含
_CONTROL_CHARS = re.compile(r'[\r\n\t\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u2028\u2029]')


class PersonaInjectionError(ValueError):
    """persona 值命中提示注入模式，拒绝写入。"""


def sanitize_persona_value(val: str) -> str:
    """对 persona 单字段值做安全净化。

    1. 剔除控制字符与换行（防止指令分隔符注入）
    2. 检测注入风险模式（忽略指令/角色扮演/泄露系统提示等）
    3. 截断到 MAX_FIELD_LEN

    Raises:
        PersonaInjectionError: 值命中注入模式
    """
    if not isinstance(val, str):
        return ''
    cleaned = _CONTROL_CHARS.sub(' ', val).strip()
    if _INJECTION_PATTERNS.search(cleaned):
        raise PersonaInjectionError(
            '该设置值包含不允许的内容（可能被误认为系统指令），请换一种表述。'
        )
    return cleaned[:MAX_FIELD_LEN]


def normalize_persona(raw: Optional[dict]) -> dict:
    """把任意历史形态的 persona 归一为规范 dict。

    只保留**显式设置过**的键——未设置的键不出现，便于区分"用户没设过"
    （据此决定是否主动询问偏好，见 US-001 AC-001-02）与"用户设成了默认值"。

    新键优先于历史键：同时存在 identity 与 greeting_style 时以 identity 为准。
    """
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    # 先铺历史键，再让新键覆盖
    for legacy, canon in _LEGACY_KEY_MAP.items():
        val = raw.get(legacy)
        if isinstance(val, str) and val.strip():
            out[canon] = val.strip()[:MAX_FIELD_LEN]
    for key in CANONICAL_KEYS:
        val = raw.get(key)
        if isinstance(val, str) and val.strip():
            out[key] = val.strip()[:MAX_FIELD_LEN]
    return out


def effective_persona(raw: Optional[dict]) -> dict:
    """归一化并补齐默认值——供提示词构造使用（identity/address 恒非空）。"""
    p = normalize_persona(raw)
    return {
        'identity': p.get('identity') or DEFAULT_IDENTITY,
        'address': p.get('address') or DEFAULT_ADDRESS,
        'tone': p.get('tone') or None,
    }


def persona_payload(raw: Optional[dict]) -> dict:
    """对外（WS connected / persona_updated 帧、REST 响应）的统一载荷。

    未设置的键返回 None，让前端能区分"未设置"并据此决定是否展示引导。
    """
    p = normalize_persona(raw)
    return {
        'identity': p.get('identity') or None,
        'address': p.get('address') or None,
        'tone': p.get('tone') or None,
    }


def has_user_set_address(raw: Optional[dict]) -> bool:
    """用户是否显式设置过称呼——US-001 首次询问偏好的判据之一。"""
    return bool(normalize_persona(raw).get('address'))


def build_persona_instruction(
    persona: Optional[dict] = None,
    ask_preference: bool = False,
) -> str:
    """构造喂给 LLM 的人格指令文本（纯字符串，不依赖 langchain）。

    2026-08-22 从 langgraph_chat.orchestrator 迁入——反转依赖方向。此前编排层
    `from api.persona import effective_persona`，是编排层对宿主 App 的唯一一条
    反向依赖；人格属于领域策略，不该由通用编排骨架来懂。现在改为：**调用方**
    （consumers）构造好指令文本，经 adapter 透传进 State，编排层只负责把它包成
    SystemMessage 注入，对人格的 schema 与默认值一无所知。

    三条约束（对应 2026-08-22 生产实测的三层缺陷）：

    1. **字段语义单一**。identity(自称) / address(称呼用户) / tone(语气) 各司其职。
       旧版 tone_style 在默认分支当"称呼"、自定义分支拼成"以X风格交流"，实测把它
       设成"胖子熊大人"后模型答"我是胖子熊大人"，把用户的称呼当成了自己的名字。
    2. **身份与称呼分层**。旧版一句"保持该角色定位贯穿整个对话"把两者一起锁死，
       导致用户说"以后叫我胖子熊大人"时副官答"我必须遵循守则"。现在身份不可变、
       称呼与语气可由用户改。
    3. **首次询问偏好**（ask_preference，US-001 AC-001-02）：要求把询问放在正常
       回答之后，不得打断。
    """
    eff = effective_persona(persona)
    parts = [
        f"你的身份是「{eff['identity']}」，请始终以该身份自居，不得自称其它名字。",
        f"请称呼当前用户为「{eff['address']}」。",
    ]
    if eff['tone']:
        parts.append(f"请以「{eff['tone']}」的语气与用户交流。")
    parts.append(
        "身份设定贯穿整个对话、不可更改；但称呼与语气属于用户偏好——"
        "若用户要求换一个称呼或调整语气，不要以「守则」「设定」为由拒绝，"
        "直接接受并从本次回复起改用新称呼。"
    )
    if ask_preference:
        parts.append(
            "另外，该用户尚未设置过称呼偏好且这是其首次对话："
            "请在本次回复的末尾用一句话自然地询问他希望被如何称呼。"
            "该询问必须放在正常回答之后，不得打断或替代对用户当前问题的回答。"
        )
    return "".join(parts)
