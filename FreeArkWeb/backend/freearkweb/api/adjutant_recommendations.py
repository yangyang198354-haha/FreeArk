"""副官页动态推荐问题。

能力引导来自受控题库；热门问题只从近期用户消息中做匿名聚合，绝不把原始
对话、用户标识或个人上下文返回给其他用户。
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
POPULAR_MIN_FREQUENCY = 2
POPULAR_LIMIT = 3
POPULAR_CACHE_KEY = "adjutant:popular-questions:v1"
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


def _popular_questions() -> list[str]:
    cached = cache.get(POPULAR_CACHE_KEY)
    if cached is not None:
        return cached

    since = timezone.now() - timedelta(days=POPULAR_WINDOW_DAYS)
    contents = ChatMessage.objects.filter(
        role="user",
        created_at__gte=since,
        session__is_deleted=False,
    ).order_by("-created_at").values_list("content", flat=True)[:POPULAR_SCAN_LIMIT]

    counts: Counter[str] = Counter()
    for content in contents:
        question = _normalise_question(content)
        if is_safe_common_question(question):
            counts[question] += 1

    popular = [
        question for question, frequency in counts.most_common()
        if frequency >= POPULAR_MIN_FREQUENCY
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
