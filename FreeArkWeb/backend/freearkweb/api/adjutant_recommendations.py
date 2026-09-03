"""副官页动态推荐问题。

能力引导来自受控题库；热门问题只从近期业主消息中按意图做匿名聚合，绝不
把原始对话、用户标识或个人上下文返回给其他用户。
"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
import re
import secrets

from django.core.cache import cache
from django.utils import timezone

from .models import ChatMessage


CAPABILITY_QUESTIONS = (
    "我的房间现在有哪些设备异常？",
    "帮我看看今天的能耗情况。",
    "空调制冷效果不好时，我可以先检查什么？",
    "新风系统怎样使用更节能？",
    "帮我解释一下设备故障提示的含义。",
    "离家时怎样设置设备更省心？",
)

POPULAR_WINDOW_DAYS = 30
POPULAR_SCAN_LIMIT = 1200
POPULAR_MIN_FREQUENCY = 3
POPULAR_MIN_UNIQUE_USERS = 2
POPULAR_LIMIT = 3
POPULAR_CACHE_KEY = "adjutant:popular-questions:v2"
POPULAR_CACHE_TTL_SECONDS = 10 * 60

# 只要命中任一模式就不参与跨用户推荐。宁可少推荐，也不能泄露个人上下文。
_SENSITIVE_PATTERNS = (
    re.compile(r"\b1\d{10}\b"),                         # 手机号
    re.compile(r"\b\d{15}(?:\d{2}[0-9Xx])?\b"),         # 身份证号
    re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"),        # IP
    re.compile(r"\b[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}\b"),  # MAC
    re.compile(r"\b\d{1,3}(?:-\d{1,3}){3}\b"),          # 专有部分
    re.compile(r"\d{4,}"),                                # 房号、设备编号等长数字
)
_PERSONAL_CONTEXT_RE = re.compile(
    r"我家|我的(?:房|空调|设备|账户|账号)|本(?:房|户)|"
    r"房号|楼栋|单元|住址|地址|姓名|密码|验证码|"
    r"设备(?:编号|号|序列号)|(?:mac|ip)地址",
    re.IGNORECASE,
)
_UNSAFE_CONTROL_RE = re.compile(r"忽略.*(?:指令|提示)|系统提示|开发者消息", re.IGNORECASE)
_NON_OWNER_USERNAME_MARKERS = ("test", "demo", "mock", "sample", "example")

# 仅使用受控的本地规则归纳常见意图：不将原始问题发送给外部模型，也不依赖
# 语义向量服务。未命中规则的问题仅按标准化后的原文计数，仍需通过隐私过滤。
_INTENT_RULES = (
    (
        "如何开启或关闭设备系统？",
        re.compile(
            r"(?:开启|打开|启动|开机|关闭|关掉|停止|停用).{0,12}"
            r"(?:系统|设备|空调|新风|主机)|"
            r"(?:系统|设备|空调|新风|主机).{0,12}"
            r"(?:开启|打开|启动|开机|关闭|关掉|停止|停用)",
            re.IGNORECASE,
        ),
    ),
    (
        "空调制冷或制热效果不好怎么办？",
        re.compile(r"(?:空调|主机).{0,12}(?:不制冷|不制热|不凉|不热)|制冷|制热", re.IGNORECASE),
    ),
    (
        "设备出现故障或异常时该怎么办？",
        re.compile(r"故障|异常|报错|告警|坏了|失灵|不工作", re.IGNORECASE),
    ),
    (
        "新风滤网多久需要更换？",
        re.compile(r"新风.{0,12}(?:滤网|滤芯).{0,12}(?:换|更换|多久)|(?:滤网|滤芯).{0,12}(?:换|更换|多久)", re.IGNORECASE),
    ),
    (
        "怎样设置离家节能模式？",
        re.compile(r"离家|节能模式|回家模式", re.IGNORECASE),
    ),
    (
        "如何查看设备能耗情况？",
        re.compile(r"能耗|耗电|用电量|耗能", re.IGNORECASE),
    ),
    (
        "如何查看设备当前运行状态？",
        re.compile(r"(?:运行|设备|系统).{0,12}(?:状态|情况)|状态.{0,12}(?:查看|查询)", re.IGNORECASE),
    ),
)


def _normalise_question(content: str) -> str:
    """标准化展示/计数键；不改变问题本身的业务含义。"""
    question = " ".join((content or "").strip().split())
    return question.rstrip("？?。！!；;")


def is_safe_common_question(content: str) -> bool:
    """判断问题是否可作为跨用户匿名热门问题展示。"""
    question = _normalise_question(content)
    if not question or len(question) > 60 or len(question) < 4:
        return False
    if "[" in question or "]" in question:  # 图片/系统标记等非自然语言消息
        return False
    if _PERSONAL_CONTEXT_RE.search(question) or _UNSAFE_CONTROL_RE.search(question):
        return False
    return not any(pattern.search(question) for pattern in _SENSITIVE_PATTERNS)


def _question_intent(question: str) -> str:
    """返回可展示的通用意图；同义表达映射到同一个受控文案。"""
    for label, pattern in _INTENT_RULES:
        if pattern.search(question):
            return label
    return question


def _is_real_owner_username(username: str) -> bool:
    """排除演示、自动化测试账号，避免它们影响业主推荐。"""
    normalized = (username or "").casefold()
    return not any(marker in normalized for marker in _NON_OWNER_USERNAME_MARKERS)


def _popular_questions() -> list[str]:
    cached = cache.get(POPULAR_CACHE_KEY)
    if cached is not None:
        return cached

    since = timezone.now() - timedelta(days=POPULAR_WINDOW_DAYS)
    messages = ChatMessage.objects.filter(
        role="user",
        created_at__gte=since,
        session__is_deleted=False,
        session__user__role="user",
        session__user__is_active=True,
        session__user__is_staff=False,
        session__user__is_superuser=False,
    ).order_by("-created_at").values_list(
        "content", "session__user_id", "session__user__username",
    )[:POPULAR_SCAN_LIMIT]

    counts: Counter[str] = Counter()
    users_by_intent: dict[str, set[int]] = {}
    for content, user_id, username in messages:
        question = _normalise_question(content)
        if not is_safe_common_question(question) or not _is_real_owner_username(username):
            continue
        intent = _question_intent(question)
        counts[intent] += 1
        users_by_intent.setdefault(intent, set()).add(user_id)

    popular = [
        intent for intent, frequency in counts.most_common()
        if frequency >= POPULAR_MIN_FREQUENCY
        and len(users_by_intent[intent]) >= POPULAR_MIN_UNIQUE_USERS
    ][:POPULAR_LIMIT]
    cache.set(POPULAR_CACHE_KEY, popular, POPULAR_CACHE_TTL_SECONDS)
    return popular


def get_adjutant_recommendations() -> dict:
    """返回副官能力引导和匿名化热门问题；热门聚合失败时安全降级。"""
    try:
        popular_questions = _popular_questions()
    except Exception:
        # 推荐功能不可影响聊天页或暴露底层错误；调用方记录异常即可。
        popular_questions = []

    return {
        "capability_question": secrets.choice(CAPABILITY_QUESTIONS),
        "popular_questions": popular_questions,
    }
