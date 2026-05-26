"""
chat_memory — 记忆管理业务逻辑层（MOD-BE-MEM）

所有函数为同步实现，由调用方（consumers.py）用 sync_to_async 包装。
ADR-009 方案 D：FreeArk MySQL 存历史，OpenClaw 端无状态。
ADR-010 方案 10-A：完整日志 + 最近 N=20 轮截断注入。
ADR-013 方案 13-B：chat_session + chat_message 两表。
"""

import logging
from django.conf import settings
from django.utils import timezone
from .models import ChatSession, ChatMessage

logger = logging.getLogger('api.chat_memory')

# N 轮 = 2N 条消息（user + assistant 各一条）
_INJECT_LIMIT = getattr(settings, 'CHAT_HISTORY_INJECT_TURNS', 20)


def create_session(user, session_key: str) -> ChatSession:
    return ChatSession.objects.create(user=user, session_key=session_key)


def close_session(session: ChatSession) -> None:
    session.ended_at = timezone.now()
    session.save(update_fields=['ended_at'])


def append_message(session: ChatSession, role: str, content: str) -> ChatMessage:
    if role not in ('user', 'assistant'):
        raise ValueError(f"role must be 'user' or 'assistant', got {role!r}")
    return ChatMessage.objects.create(session=session, role=role, content=content)


def load_history(user, limit: int = None) -> list:
    """
    返回用户最近 limit 轮对话，按时间升序排列。
    跨 session 查询（JOIN session → filter user），避免只看最后一个 session。
    limit=None 时从 settings 读取（支持 override_settings）。
    """
    if limit is None:
        limit = getattr(settings, 'CHAT_HISTORY_INJECT_TURNS', _INJECT_LIMIT)
    rows = (
        ChatMessage.objects
        .filter(session__user=user)
        .order_by('-created_at', '-id')
        .values('role', 'content')[:limit * 2]
    )
    # 倒序取到的结果重新升序排列后返回
    return list(reversed([{'role': r['role'], 'content': r['content']} for r in rows]))


def clear_memory(user) -> int:
    deleted, _ = ChatSession.objects.filter(user=user).delete()
    return deleted


def get_sessions(user, page: int = 1, page_size: int = 20) -> dict:
    qs = ChatSession.objects.filter(user=user).order_by('-started_at')
    total = qs.count()
    offset = (page - 1) * page_size
    sessions = []
    for s in qs[offset:offset + page_size]:
        sessions.append({
            'id': s.id,
            'session_key': s.session_key[:8] + '...',
            'started_at': s.started_at.isoformat() if s.started_at else None,
            'ended_at': s.ended_at.isoformat() if s.ended_at else None,
            'message_count': s.messages.count(),
        })
    return {'total': total, 'page': page, 'sessions': sessions}


def build_inject_prefix(history: list) -> str:
    if not history:
        return ''
    lines = ['[历史记忆开始]']
    for msg in history:
        role_label = '用户' if msg['role'] == 'user' else '助手'
        lines.append(f"{role_label}: {msg['content']}")
    lines.append('[历史记忆结束]')
    return '\n'.join(lines) + '\n'
