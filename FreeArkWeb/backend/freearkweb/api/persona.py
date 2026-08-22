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
