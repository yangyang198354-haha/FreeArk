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


# 能力引导题库（REQ-FUNC-001：6 → 20 条）。前 6 条为原有文案，逐字保留且次序不变（向后兼容；
# 其中第 2 条同时是 api/views_miniapp.py 降级兜底文案的成员资格锚点，见 ADR-08）；后 14 条为本
# 次新增。每条问题的「副官能力依据（文件:符号）」对照如下（REQ-FUNC-003 / AC-FUNC-003-01；依据
# 取自 requirements_spec.md 第 3 节映射表，符号均已核实存在）：
#    1. 我的房间现在有哪些设备异常？               → langgraph_chat/fa_tools.py:get_fault_summary；langgraph_chat/experts.py:inspection-expert
#    2. 帮我看看今天的能耗情况。                   → langgraph_chat/fa_tools.py:get_dashboard_summary / get_usage_daily
#    3. 空调制冷效果不好时，我可以先检查什么？     → agents/inspection-expert/SYSTEM_PROMPT.langgraph.md（最小数据收集流程）；sanheng-knowledge RAG
#    4. 新风系统怎样使用更节能？                   → agents/freeark-expert/SYSTEM_PROMPT.langgraph.md（节能建议）；agents/sanheng-knowledge/SYSTEM_PROMPT.langgraph.md（新风）
#    5. 帮我解释一下设备故障提示的含义。           → agents/sanheng-knowledge/SYSTEM_PROMPT.langgraph.md（故障码）；langgraph_chat/fa_tools.py:search_sanheng_knowledge
#    6. 离家时怎样设置设备更省心？                 → langgraph_chat/fa_tools.py:set_device_params；本模块 _INTENT_RULES 的「离家/回家模式」受控意图
#    7. 我家今天用了多少电？                       → langgraph_chat/fa_tools.py:get_usage_daily（日用量）
#    8. 帮我看看这周的用电趋势。                   → langgraph_chat/fa_tools.py:get_usage_daily（start_date / end_date 时段）
#    9. 有什么省电的用法建议吗？                   → agents/freeark-expert/SYSTEM_PROMPT.langgraph.md（「节能建议」职责项）
#   10. 我房间现在的温度和湿度是多少？             → langgraph_chat/fa_tools.py:get_realtime_params（温度 / 湿度）
#   11. 室内二氧化碳浓度现在正常吗？               → langgraph_chat/fa_tools.py:get_realtime_params（CO₂）；agents/freeark-skill/SKILL.md（恒氧 ≤1000 ppm）
#   12. 我房间的空调有哪些参数可以调？             → langgraph_chat/fa_tools.py:get_device_params（可写参数白名单）
#   13. 帮我把房间温度设定成 24 度。               → langgraph_chat/fa_tools.py:set_device_params（写操作确认门见 freeark-expert 系统提示词）
#   14. 怎么把房间的空调关掉？                     → langgraph_chat/fa_tools.py:set_device_params（开关下发）
#   15. 刚才让你调的参数生效了吗？                 → langgraph_chat/fa_tools.py:get_write_status
#   16. 我房间的数据好像没更新，可以重新采集一次吗？ → langgraph_chat/fa_tools.py:trigger_refresh
#   17. 我家的设备现在都在线吗？                   → langgraph_chat/fa_tools.py:get_plc_status（业主路径按绑定范围过滤）
#   18. 帮我巡检一下我家的设备，看看有没有异常。   → langgraph_chat/experts.py:inspection-expert；agents/inspection-expert/SYSTEM_PROMPT.langgraph.md
#   19. 新风滤网多久需要更换一次？                 → agents/sanheng-knowledge/SYSTEM_PROMPT.langgraph.md（先检索后作答）
#   20. 三恒系统的恒温恒湿恒氧分别是什么意思？     → langgraph_chat/experts.py:sanheng-knowledge（三恒 / 恒温 / 恒湿 / 恒氧 / 原理）
# 「工单 / 账单 / 缴费 / 报修派单 / 服务启停 / 设备树同步」不在业主端副官的能力范围内，不得加入
# 本题库（REQ-FUNC-002-03；依据 langgraph_chat/scope_enforcer.py 的 FILTERED_OWNER_WORKORDER_TOOLS
# 为空集、langgraph_chat/fa_tools.py 的 TOOLS_BY_EXPERT 无此类工具）。
CAPABILITY_QUESTIONS = (
    "我的房间现在有哪些设备异常？",
    "帮我看看今天的能耗情况。",
    "空调制冷效果不好时，我可以先检查什么？",
    "新风系统怎样使用更节能？",
    "帮我解释一下设备故障提示的含义。",
    "离家时怎样设置设备更省心？",
    "我家今天用了多少电？",
    "帮我看看这周的用电趋势。",
    "有什么省电的用法建议吗？",
    "我房间现在的温度和湿度是多少？",
    "室内二氧化碳浓度现在正常吗？",
    "我房间的空调有哪些参数可以调？",
    "帮我把房间温度设定成 24 度。",
    "怎么把房间的空调关掉？",
    "刚才让你调的参数生效了吗？",
    "我房间的数据好像没更新，可以重新采集一次吗？",
    "我家的设备现在都在线吗？",
    "帮我巡检一下我家的设备，看看有没有异常。",
    "新风滤网多久需要更换一次？",
    "三恒系统的恒温恒湿恒氧分别是什么意思？",
)

POPULAR_WINDOW_DAYS = 30
POPULAR_SCAN_LIMIT = 1200
POPULAR_MIN_FREQUENCY = 3
POPULAR_MIN_UNIQUE_USERS = 2
POPULAR_LIMIT = 3
# POPULAR_CACHE_KEY 的版本号 = 热门问题「归一化口径」的版本：该 key 缓存的是「按某套意图规则
# 归一化后的榜单」，规则集合或受控文案口径一旦变更就必须 bump 版本号，否则上线后最长
# POPULAR_CACHE_TTL_SECONDS 内仍会读到旧口径榜单（ADR-04）。本次规则 7 → 23 条、受控文案集合
# 随之改变，故 v2 → v3；旧 v2 键不得再被任何代码路径读取（AC-FUNC-009-01）。
POPULAR_CACHE_KEY = "adjutant:popular-questions:v3"
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
# 意图归一化规则（REQ-FUNC-004：7 → 23 条，与 module_design.md 第 3 节 R01~R23 一一对应且同序）。
# 本元组的**次序即优先级** —— _question_intent 先命中先返回，故排列必须遵守 ADR-01 的顺序契约
# （具体 → 宽泛）：①含设备/载体限定（空调 / 新风 / 主机 / 室内机 / 地暖 / 房间）者优先；②含动作
# 或工况限定（设定 / 开关 / 刷新 / 回执、制冷 / 制热）者次之；③仅含宽泛业务域词者（R14 运行状态、
# R15 故障、R20 离家场景）排在其所覆盖的具体规则之后。每条末尾的 R## 标记指向该设计清单的行号序。
#
# 两条**不得违反**的分工约束：
#   · 禁用裸主题词：R01/R02 必须同时含载体词与**工况化症状词**，不得出现「制冷」「制热」可单独
#     触发的分支。现状曾用裸 `制冷|制热`，会让「制冷耗电多少」这类能耗问法被温控规则抢先命中，
#     损害 AC-FUNC-004-05 与 AC-FUNC-006-02（ADR-01 的遮蔽例证）。
#   · R04/R05 必须先于 R09/R10：含载体词的开关问法归 R04/R05，无载体词的「系统 / 设备」泛问归
#     R09/R10；顺序颠倒会让泛规则抢走具体问法。
# 已知张力（详见 development/code_review_report.md 的遗留问题登记，代码侧不得自行改判）：
#   · R16 按表序排在 R15 之后，而 R15 的故障词（含「异常」）为宽泛匹配，故为 R16 构造样本时不得
#     使用含裸故障词的问法；该文案原文不作 canonical 样本（T-04 须改用不含故障词的巡检动作问法）。
#   · R13 的受控文案曾含「我家」而违反 AC-NFR-001-03（缺陷 G-009）；已于 module_design.md v0.1.2
#     修订为「设备现在都在线吗？」，本注释保留以备审计。
_INTENT_RULES = (
    (
        "空调制冷效果不好怎么办？",  # R01 温控 · 制冷效果异常（载体词 + 工况化症状词）
        re.compile(
            r"(?:空调|主机|室内机).{0,12}"
            r"(?:不制冷|不凉|不够冷|制冷效果不好|制冷不好|制冷效果差|制冷效果不理想)"
            r"|(?:不制冷|不凉|不够冷|制冷效果不好|制冷不好|制冷效果差|制冷效果不理想)"
            r".{0,12}(?:空调|主机|室内机)",
            re.IGNORECASE,
        ),
    ),
    (
        "空调制热效果不好怎么办？",  # R02 温控 · 制热效果异常（与 R01 以工况词互斥）
        re.compile(
            r"(?:空调|主机|地暖).{0,12}"
            r"(?:不制热|不热|不够暖|制热效果不好|制热不好|制热效果差|制热效果不理想)"
            r"|(?:不制热|不热|不够暖|制热效果不好|制热不好|制热效果差|制热效果不理想)"
            r".{0,12}(?:空调|主机|地暖)",
            re.IGNORECASE,
        ),
    ),
    (
        "怎么把房间温度设定成我想要的值？",  # R03 温控 · 温度设定下发
        re.compile(
            r"(?:设定|设置为|设为|调到|调成|改成|改到).{0,12}(?:温度|温控|度数)"
            r"|(?:温度|温控|度数).{0,12}(?:设定|设置为|设为|调到|调成|改成|改到)",
            re.IGNORECASE,
        ),
    ),
    (
        "怎么把房间的空调关掉？",  # R04 温控 · 开关下发（关，含载体词；须先于 R09/R10）
        re.compile(
            r"(?:关掉|关闭|关上|停止|停用).{0,12}(?:空调|新风|主机|地暖|房间)"
            r"|(?:空调|新风|主机|地暖|房间).{0,12}(?:关掉|关闭|关上|停止|停用)",
            re.IGNORECASE,
        ),
    ),
    (
        "怎么把房间的空调打开？",  # R05 温控 · 开关下发（开，含载体词；须先于 R09/R10）
        re.compile(
            r"(?:打开|开启|启动|开机).{0,12}(?:空调|新风|主机|地暖|房间)"
            r"|(?:空调|新风|主机|地暖|房间).{0,12}(?:打开|开启|启动|开机)",
            re.IGNORECASE,
        ),
    ),
    (
        "我房间的空调有哪些参数可以调？",  # R06 温控 · 可写参数发现
        re.compile(
            r"(?:可以调|能调|可调|可设|可以设置|有哪些参数|有什么参数)"
            r".{0,12}(?:空调|新风|主机|地暖|温控|设备)"
            r"|(?:空调|新风|主机|地暖|温控).{0,12}"
            r"(?:可以调|能调|可调|可设|可以设置|有哪些参数|有什么参数)",
            re.IGNORECASE,
        ),
    ),
    (
        "刚才让你调的参数生效了吗？",  # R07 温控 · 写操作回执
        re.compile(
            r"(?:生效|成功|写进去|改好了|写成功|改成功).{0,12}(?:刚才|刚刚|上次|已经)"
            r"|(?:刚才|刚刚|上次|已经).{0,12}(?:生效|成功|写进去|改好了|写成功|改成功)",
            re.IGNORECASE,
        ),
    ),
    (
        "数据好像没更新，可以重新采集吗？",  # R08 设备状态 · 按需采集刷新
        re.compile(r"刷新|重新采集|更新一下|同步一次|重新同步|重新获取", re.IGNORECASE),
    ),
    (
        "如何开启设备系统？",  # R09 设备状态 · 全屋/系统开（无载体词泛问；须在 R04/R05 之后）
        re.compile(
            r"(?:开启|打开|启动|开机).{0,12}(?:系统|设备)"
            r"|(?:系统|设备).{0,12}(?:开启|打开|启动|开机)",
            re.IGNORECASE,
        ),
    ),
    (
        "怎样关闭设备系统？",  # R10 设备状态 · 全屋/系统关（无载体词泛问；须在 R04/R05 之后）
        re.compile(
            r"(?:关闭|关掉|关上|停止|停用).{0,12}(?:系统|设备)"
            r"|(?:系统|设备).{0,12}(?:关闭|关掉|关上|停止|停用)",
            re.IGNORECASE,
        ),
    ),
    (
        "我房间现在的温度和湿度是多少？",  # R11 实时参数 · 温湿度
        re.compile(
            r"(?:温度|湿度).{0,12}(?:多少|几度|现在)"
            r"|(?:多少|几度|现在).{0,12}(?:温度|湿度)",
            re.IGNORECASE,
        ),
    ),
    (
        "室内二氧化碳浓度正常吗？",  # R12 实时参数 · 空气质量（CO₂ / 含氧量）
        re.compile(r"二氧化碳|CO₂|CO2|空气质量|含氧量", re.IGNORECASE),
    ),
    (
        "设备现在都在线吗？",  # R13 设备状态 · PLC 在线/离线（文案 v0.1.2 修订，正则未动）
        re.compile(
            r"(?:在线|离线|连不上|掉线|断连).{0,12}(?:设备|主机|空调|机组)"
            r"|(?:设备|主机|空调|机组).{0,12}(?:在线|离线|连不上|掉线|断连)",
            re.IGNORECASE,
        ),
    ),
    (
        "如何查看设备当前运行状态？",  # R14 设备状态 · 运行状态总览（保留现状第 7 条，正则逐字不改）
        re.compile(r"(?:运行|设备|系统).{0,12}(?:状态|情况)|状态.{0,12}(?:查看|查询)", re.IGNORECASE),
    ),
    (
        "设备出现故障或异常时该怎么办？",  # R15 故障与巡检 · 故障提示释义（保留现状第 3 条，正则逐字不改）
        re.compile(r"故障|异常|报错|告警|坏了|失灵|不工作", re.IGNORECASE),
    ),
    (
        "帮我巡检一下家里的设备有没有异常。",  # R16 故障与巡检 · 自主巡检
        re.compile(r"巡检|检查一遍|排查|体检", re.IGNORECASE),
    ),
    (
        "今天用了多少电？",  # R17 能耗 · 日用量（电量词 + 日粒度词）
        re.compile(
            r"(?:用了多少电|用电量|用电|耗电|用了多少度电|用电多少)"
            r".{0,12}(?:今天|昨天|今日|当日|当天)"
            r"|(?:今天|昨天|今日|当日|当天).{0,12}"
            r"(?:用了多少电|用电量|用电|耗电|用了多少度电|用电多少)",
            re.IGNORECASE,
        ),
    ),
    (
        "这周的用电趋势怎么样？",  # R18 能耗 · 时段趋势（电量词 + 时段词）
        re.compile(
            r"(?:用了多少电|用电量|用电|耗电|用了多少度电|用电多少)"
            r".{0,12}(?:这周|本周|这星期|这个月|本月|最近|趋势|这几天|近几天)"
            r"|(?:这周|本周|这星期|这个月|本月|最近|趋势|这几天|近几天)"
            r".{0,12}(?:用了多少电|用电量|用电|耗电|用了多少度电|用电多少)",
            re.IGNORECASE,
        ),
    ),
    (
        "有什么省电的用法建议吗？",  # R19 场景节能 · 节能建议（节能词 + 建议语气）
        re.compile(
            r"(?:省电|节能|省一点|省点电|费电).{0,12}(?:建议|有没有|怎么办|办法|方法|推荐)"
            r"|(?:建议|有没有|怎么办|办法|方法|推荐).{0,12}(?:省电|节能|省一点|省点电|费电)",
            re.IGNORECASE,
        ),
    ),
    (
        "怎样设置离家节能模式？",  # R20 场景节能 · 离家/回家模式（保留现状第 5 条）
        re.compile(r"离家|节能模式|回家模式|无人时", re.IGNORECASE),
    ),
    (
        "新风滤网多久需要更换？",  # R21 新风与知识 · 滤网耗材（保留现状第 4 条；文案逐字不改 —— 既有测试锚点）
        re.compile(
            r"新风.{0,12}(?:滤网|滤芯).{0,12}(?:换|更换|多久)"
            r"|(?:滤网|滤芯).{0,12}(?:换|更换|多久)",
            re.IGNORECASE,
        ),
    ),
    (
        "三恒系统的恒温恒湿恒氧是什么意思？",  # R22 新风与知识 · 三恒原理
        re.compile(r"三恒|恒温|恒湿|恒氧|原理|是什么意思|为什么", re.IGNORECASE),
    ),
    (
        "以后请叫我的昵称。",  # R23 人格偏好 · 称呼/语气
        re.compile(r"叫我|称呼我|叫我名字|昵称|别这么正式|称呼我为", re.IGNORECASE),
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
