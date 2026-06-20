"""
chat_memory — 记忆管理业务逻辑层（MOD-BE-MEM）

所有函数为同步实现，由调用方（consumers.py）用 sync_to_async 包装。
标题生成异步函数（generate_title_llm_async）为 async def，供 asyncio.create_task() 调用。

ADR-009 方案 D：FreeArk MySQL 存历史，OpenClaw 端无状态。
ADR-010 方案 10-A：完整日志 + 最近 N=20 轮截断注入。
ADR-013 方案 13-B：chat_session + chat_message 两表。

@module MOD-BE-MEM
@implements IFC-MEM-001, IFC-MEM-002, IFC-MEM-003, IFC-MEM-004
@depends MOD-BE-MODEL
@author sub_agent_software_developer
"""

import logging
from asgiref.sync import sync_to_async
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
    from django.db.models import Count
    qs = (
        ChatSession.objects
        .filter(user=user, is_deleted=False)
        .annotate(message_count=Count('messages'))
        .order_by('-started_at')
    )
    total = qs.count()
    offset = (page - 1) * page_size
    sessions = []
    for s in qs[offset:offset + page_size]:
        sessions.append({
            'id': s.id,
            'session_key': s.session_key[:8] + '...',
            'session_key_full': s.session_key,
            'started_at': s.started_at.isoformat() if s.started_at else None,
            'ended_at': s.ended_at.isoformat() if s.ended_at else None,
            'message_count': s.message_count,
            'title': s.title,  # IFC-MEM-001: 新增 title 字段（可为 None）
        })
    return {'total': total, 'page': page, 'sessions': sessions}


def load_history_by_session(session: ChatSession, limit: int = None) -> list:
    """
    返回指定 session 的最近 limit 轮对话，按时间升序排列。
    仅查询 session 内消息（session 隔离），不跨 session 查询。
    limit=None 时从 settings 读取（支持 override_settings）。
    """
    if limit is None:
        limit = getattr(settings, 'CHAT_HISTORY_INJECT_TURNS', _INJECT_LIMIT)
    rows = (
        ChatMessage.objects
        .filter(session=session)
        .order_by('-created_at', '-id')
        .values('role', 'content')[:limit * 2]
    )
    return list(reversed([{'role': r['role'], 'content': r['content']} for r in rows]))


def soft_delete_session(user, session_key: str) -> bool:
    """
    软删除指定 session：校验 user 归属且 is_deleted=False，然后设 is_deleted=True。
    找不到或不属于该 user 时抛 ValueError。
    返回 True 表示软删除成功。
    """
    try:
        session = ChatSession.objects.get(
            user=user,
            session_key=session_key,
            is_deleted=False,
        )
    except ChatSession.DoesNotExist:
        raise ValueError('session not found or not owned by user')
    session.is_deleted = True
    session.save(update_fields=['is_deleted'])
    return True


def build_inject_prefix(history: list) -> str:
    if not history:
        return ''
    lines = ['[历史记忆开始]']
    for msg in history:
        role_label = '用户' if msg['role'] == 'user' else '助手'
        lines.append(f"{role_label}: {msg['content']}")
    lines.append('[历史记忆结束]')
    return '\n'.join(lines) + '\n'


# ---------------------------------------------------------------------------
# IFC-MEM-002: generate_title_truncate — 截断标题生成（同步）
# ---------------------------------------------------------------------------

def generate_title_truncate(content: str, max_len: int = 30) -> str:
    """
    截断首条 user 消息内容作即时标题。

    参数：
        content: 首条 user 消息原文
        max_len: 最大字符数（默认 30）

    返回：截断后的字符串，超长则截断到 max_len-3 字符并追加"..."（总长 max_len 字符）。
    空内容返回空字符串。
    """
    if not content:
        return ''
    content = content.strip()
    if len(content) <= max_len:
        return content
    # 截断到 max_len-3 字符，追加"..."，总长 max_len
    return content[:max_len - 3] + '...'


# ---------------------------------------------------------------------------
# IFC-MEM-003: generate_title_llm_async — 异步 LLM 标题生成（fire-and-forget）
# ---------------------------------------------------------------------------

async def generate_title_llm_async(
    session_id: int,
    first_user_msg: str,
    first_assistant_msg: str,
) -> None:
    """
    异步协程：调用 LLM 为会话生成概括标题，成功时更新 ChatSession.title。
    供 asyncio.create_task() 调用，fire-and-forget，不向外抛出异常。

    LLM 配置：复用 settings.DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / LANGGRAPH_MODEL。
    配置缺失时仅记录 warning，保留截断标题（REQ-FUNC-005 降级）。

    所有 ORM 操作通过 sync_to_async 包装（RISK-003 缓解）。

    @implements IFC-MEM-003
    """
    try:
        # 读取 LLM 配置（复用现有 deepseek 配置，DEV-002 偏差已记录）
        api_key = getattr(settings, 'DEEPSEEK_API_KEY', '')
        api_base = getattr(settings, 'DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
        model = getattr(settings, 'LANGGRAPH_MODEL', 'deepseek-chat')

        if not api_key:
            logger.warning(
                'generate_title_llm_async: DEEPSEEK_API_KEY 未配置，保留截断标题 session_id=%d',
                session_id,
            )
            return

        # 构造 LLM prompt
        prompt = (
            f"请为以下对话生成一个简洁的中文标题，不超过20个字，直接输出标题文字，不加引号和说明：\n"
            f"用户：{first_user_msg[:200]}\n"
            f"助手：{first_assistant_msg[:200]}"
        )

        # 使用 openai SDK 调用（已在 LangGraph 依赖中，无需新增依赖）
        import openai  # noqa: PLC0415

        client = openai.AsyncOpenAI(
            api_key=api_key,
            base_url=api_base,
            timeout=10.0,  # RISK-002 缓解：10s 超时
        )

        response = await client.chat.completions.create(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=50,
            temperature=0.3,
        )

        generated_title = response.choices[0].message.content.strip()
        # 截断保护：LLM 标题最多 100 字（model 字段 max_length=100）
        if len(generated_title) > 97:
            generated_title = generated_title[:97] + '...'

        if not generated_title:
            logger.warning(
                'generate_title_llm_async: LLM 返回空标题，保留截断标题 session_id=%d',
                session_id,
            )
            return

        # ORM 写入（必须用 sync_to_async 包装，RISK-003）
        def _update_title():
            try:
                ChatSession.objects.filter(pk=session_id).update(title=generated_title)
            except Exception as inner_exc:
                logger.warning(
                    'generate_title_llm_async: ORM update 失败，保留截断标题 session_id=%d: %s',
                    session_id, inner_exc,
                )

        await sync_to_async(_update_title)()
        logger.info(
            'generate_title_llm_async: 标题已更新 session_id=%d title=%r',
            session_id, generated_title,
        )

    except Exception as exc:
        # RISK-002/RISK-005 兜底：任何异常（超时/网络/API错误）均只记 warning，不向外抛出
        logger.warning(
            'generate_title_llm_async: LLM 标题生成失败，保留截断标题 session_id=%d: %s',
            session_id, exc,
        )


# ---------------------------------------------------------------------------
# IFC-MEM-004: get_session_history — 历史消息查询（同步）
# ---------------------------------------------------------------------------

def get_session_history(user, session_key: str, limit: int = 40) -> list:
    """
    查询指定会话的最近 limit 条历史消息，按 created_at 升序排列。

    参数：
        user: 请求用户（CustomUser），用于归属校验
        session_key: 完整 UUID 字符串
        limit: 返回条数上限（默认 40）

    返回：消息列表 [{'role': str, 'content': str, 'created_at': str}]
    抛出：ValueError — session_key 不存在或不属于该 user

    @implements IFC-MEM-004
    """
    try:
        session = ChatSession.objects.get(
            user=user,
            session_key=session_key,
            is_deleted=False,
        )
    except ChatSession.DoesNotExist:
        raise ValueError(f'session_key={session_key!r} 不存在或不属于当前用户')

    messages = (
        ChatMessage.objects
        .filter(session=session)
        .order_by('created_at')[:limit]
    )
    return [
        {
            'role': msg.role,
            'content': msg.content,
            'created_at': msg.created_at.isoformat(),
        }
        for msg in messages
    ]
