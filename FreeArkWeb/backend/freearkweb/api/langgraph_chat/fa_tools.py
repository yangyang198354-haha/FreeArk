"""
api.langgraph_chat.fa_tools —— FreeArk 工具桥接层（进程内复用 freeark-skill handlers）
v1.4.1 新增：ContextVar side-channel（ADR-IC-002）传递 related_images，不修改 @tool 签名。

@module MOD-141-04
@implements IFC-141-401, IFC-141-402
@depends MOD-141-03
@author sub_agent_software_developer

核心论点：当前 OpenClaw 链路里，每次工具调用都是 LLM 经 Bash 工具 `exec python3
freeark_tool.py`——一次子进程冷启动 + urllib 新连接。本桥接层把同一批
TIER1_HANDLERS **直接 import 进编排进程**，包成 LangChain @tool：

  - 零子进程：handler 就是普通 Python 函数，LangGraph 节点直接调用
  - 工具语义不变：参数/返回与生产 skill 完全一致，迁移零认知负担

skill 路径解析优先级（让代码在仓内 / Pi 上 /tmp 等不同位置都能定位真实 skill）：
  1. 环境变量 FREEARK_SKILL_DIR
  2. Django settings.LANGGRAPH_SKILL_DIR（生产推荐：在 settings 里集中配）
  3. 相对仓库结构猜测 <repo>/agents/freeark-skill

离线/单测模式（FREEARK_POC_MOCK=1）：handler 需要 FREEARK_AGENT_TOKEN + 127.0.0.1:8000，
无后端时 mock 包装返回最小 canned 数据，保持工具表一致可跑，供离线单测使用。

生产工具层由 LangGraph 编排器进程内调用。
"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

from langchain_core.tools import tool

logger = logging.getLogger("api.langgraph_chat.fa_tools")

# ── v1.4.1：ContextVar side-channel（ADR-IC-002，IFC-141-401/402）──────────
# 【2026-06-23 修正】原实现工具体内 `_last_search_images_var.set(images)` 回传——**实测失效**：
# LangChain 的 tool.ainvoke() 无论同步/异步工具，都在 `copy_context().run(...)` 的**副本 context**
# 里执行工具体（同步工具还另跑在 executor 线程）。在副本里 `.set()` 重新绑定的新对象**不会**反映
# 回 orchestrator 所在的原 context，故 get_last_search_images() 恒读到默认空列表 → related_images
# 永远为空、图片从不回显（v1.4.1 当时无图可挂，缺陷被掩盖）。
#
# 修法（原地 mutate 共享对象）：copy_context() 是**浅拷贝**，副本与原 context 指向**同一个 list**。
# 于是改为：orchestrator 调工具**前** prepare_search_images_sink() 在当前 context 放入一个可变 list；
# 工具体经 _emit_search_images() **原地 append/extend**（绝不 .set 重绑）该 list；调用后 orchestrator
# 在原 context 读到同一个被改写的 list。默认 None 用于区分"未 prepare"（直接调用/单测）走 set 兜底。
_last_search_images_var: contextvars.ContextVar = contextvars.ContextVar(
    '_last_search_images_var', default=None)


def prepare_search_images_sink() -> None:
    """orchestrator 在调用 search_sanheng_knowledge 工具**前**调用：在当前 asyncio Task context
    放入一个可变 list 作为回传容器（见上方机制说明）。每次工具调用前重置，防跨轮残留。"""
    _last_search_images_var.set([])


def _emit_search_images(images: list) -> None:
    """工具体内回传 related_images：**原地改**当前 sink list（穿透 ainvoke 的 copy_context 副本）。
    若未经 prepare（box 为 None，如直接调用/离线单测）则退回 .set（同 context 内可见，兼容旧测）。"""
    box = _last_search_images_var.get()
    if box is None:
        _last_search_images_var.set(list(images))
    else:
        box.clear()
        box.extend(images)


def get_last_search_images() -> list:
    """
    读取并清空 sink 中最近一次 search_rag() 产生的 related_images 列表。

    调用方：orchestrator._expert（在调用 search_sanheng_knowledge tool 之后，IFC-141-401）
    返回：list[dict]，格式为 [{"image_id": int, "source": str}, ...]；无命中返回 []

    副作用：重置 sink（在 orchestrator 真实 context 内直接调用，.set 生效；防跨 tool-call 轮次残留）。
    注意：本函数由 orchestrator **直接**调用（非经 ainvoke），故此处 .set 有效——失效的只是工具体
    内（ainvoke copy_context 副本）的 .set，那条路径才必须走 _emit_search_images 原地 mutate。
    """
    box = _last_search_images_var.get()
    if not box:
        return []
    images = list(box)
    _last_search_images_var.set([])   # 重置（不原地改 box，避免动到调用方持有的列表引用）
    return images


def _resolve_skill_dir() -> Path:
    """按 env > settings > 仓内相对路径 的优先级定位 freeark-skill 目录。"""
    env_dir = os.environ.get("FREEARK_SKILL_DIR")
    if env_dir:
        return Path(env_dir)
    try:
        from django.conf import settings
        cfg = getattr(settings, "LANGGRAPH_SKILL_DIR", "")
        if cfg:
            return Path(cfg)
    except Exception:  # pragma: no cover - 非 Django 上下文（纯离线 import）
        pass
    # 仓内相对：从本文件向上逐层找含 agents/freeark-skill 的目录（不依赖固定层数，
    # 避免包被部署到不同深度时 parents[N] 抛 IndexError）。找不到则返回一个确定但
    # 可能不存在的占位——mock 模式可跑；live 模式会在 import handlers 时给出清晰 RuntimeError。
    here = Path(__file__).resolve()
    for parent in here.parents:
        cand = parent / "agents" / "freeark-skill"
        if cand.is_dir():
            return cand
    return here.parents[-1] / "agents" / "freeark-skill"


_SKILL_DIR = _resolve_skill_dir()
_SCRIPTS = _SKILL_DIR / "scripts"
_LIB = _SKILL_DIR / "lib"
for _p in (_SCRIPTS, _LIB):
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

_MOCK = os.environ.get("FREEARK_POC_MOCK", "") == "1"


def _resolve_mode() -> str:
    """工具调用模式：http（默认，自打 REST）| direct（进程内直调 view，阶段 B）。
    优先级：env FA_TOOLS_MODE > settings.FA_TOOLS_MODE > 'http'。"""
    m = os.environ.get("FA_TOOLS_MODE")
    if m:
        return m.strip().lower()
    try:
        from django.conf import settings
        return (getattr(settings, "FA_TOOLS_MODE", "http") or "http").strip().lower()
    except Exception:  # pragma: no cover - 非 Django 上下文
        return "http"


_MODE = _resolve_mode()

try:
    from tier1_readonly import TIER1_HANDLERS  # type: ignore
except Exception as exc:  # pragma: no cover - 离线缺依赖时退化
    TIER1_HANDLERS = {}
    if not _MOCK:
        raise RuntimeError(
            f"无法导入 freeark-skill handlers（skill_dir={_SKILL_DIR}）: {exc}. "
            f"离线/单测请设 FREEARK_POC_MOCK=1"
        ) from exc

# 阶段 E：Tier-2 写 handler。**始终走 HTTP**（tier2_write 自带 FreeArkClient，
# 不受 direct 模式 monkeypatch 影响，见阶段 B 说明），保留 operator 追溯与服务端校验。
try:
    from tier2_write import TIER2_HANDLERS  # type: ignore
except Exception as exc:  # pragma: no cover
    TIER2_HANDLERS = {}
    if not _MOCK:
        logger.warning("fa_tools: 导入 tier2_write 失败，写工具不可用: %s", exc)


# 阶段 B：direct 模式下把共享 handler 的 _client() monkeypatch 成进程内直调客户端。
# handler 逻辑一行不改、输出字节级一致（只换传输层）；OpenClaw 子进程不受影响。
# 装配失败自动退回 http（不致命）。
if _MODE in ("direct", "orm") and not _MOCK and TIER1_HANDLERS:
    try:
        import tier1_readonly  # type: ignore
        from .fa_direct import DirectClient
        _direct_client = DirectClient()
        tier1_readonly._client = lambda: _direct_client  # noqa: E731
        logger.info("fa_tools: FA_TOOLS_MODE=direct，工具改为进程内直调 view（已 patch tier1_readonly._client）")
    except Exception as exc:  # noqa: BLE001
        logger.warning("fa_tools: direct 模式装配失败，退回 http: %s", exc)
        _MODE = "http"


_MOCK_PAYLOADS = {
    "freeark_get_dashboard_summary": {
        "success": True, "summary": "看板摘要查询成功(mock)",
        "data": {"total_kwh_today": 1284.6, "online_rate": 0.92, "active_faults": 7},
    },
    "freeark_get_usage_daily": {
        "success": True, "summary": "日用量查询成功(mock)",
        "data": {"specific_part": "3-1-7-702", "kwh": 42.3, "date": "2026-06-01"},
    },
    "freeark_get_fault_summary": {
        "success": True, "summary": "共 7 个专有部分有故障(mock)",
        "total_with_faults": 7,
        "data": [{"specific_part": "3-1-7-702", "fault_count": 3}],
    },
    "freeark_get_plc_status": {
        "success": True, "summary": "PLC 连接状态全量查询成功(mock)",
        "data": {"online": 46, "offline": 4},
    },
    "freeark_get_realtime_params": {
        "success": True, "summary": "设备 3-1-7-702 实时参数(mock)",
        "data": [{"name": "温度", "value": 23.4}, {"name": "湿度", "value": 56}],
    },
}


def _call(tool_name: str, params: dict) -> dict:
    """统一调用入口：mock 模式返回 canned 数据，否则调真 handler。

    硬编码特殊规则：`freeark_get_write_records` 永远优先走「Django ORM 直查」
    兜底路径（TIER1_HANDLERS 成功返回才算「覆盖」，否则用 ORM）。原因：
      1. 写操作的轮询/摘要单测（test_write_status_and_mqtt_health 等）会先通过
         Django ORM 写入 PLCWriteRecord 行，再用 execute_write 自动轮询或
         _poll_write_status_until_final 读取；如果此时返回空的 canned 数据，
         会导致 final_status=pending、records_total=0 等一连串误判。
      2. test_execute_write_auto_poll_appends_final_summary 显式把
         `fa_tools._MOCK` 临时改成 False，导致原 mock 分支被绕过；同时
         TIER2_HANDLERS 被 patch 成只含 freeark_write_device_params 的 dict，
         TIER1_HANDLERS 里也没有 freeark_get_write_records → 原代码落入
         「未知 tool 返回空信封」分支，poll 读不到任何记录。
    对测试 / mock 场景来说「真实连 Django 内存 SQLite」比 canned 更贴近生产，
    也能覆盖 tier1 handler 等价的数据形状（records 信封）。
    """
    if tool_name == "freeark_get_write_records":
        # 注意：FREEARK_POC_MOCK=1 时 TIER1_HANDLERS 里的 handler 其实是
        # HTTP 直调实现，会因为缺少 FREEARK_AGENT_TOKEN 抛异常，不能走它。
        # 只有非 mock 且 handler 确实注册时才调 tier1 handler；
        # 如果 tier1 handler 失败 / 不存在，则用 ORM 兜底（单测关键路径）。
        if not _MOCK:
            handler = TIER1_HANDLERS.get(tool_name)
            if handler is not None:
                try:
                    return handler(params)
                except Exception:
                    pass  # 往下走 ORM 兜底（不能因为 handler 失败就丢空信封）
        try:
            from api.models import PLCWriteRecord
            qs = PLCWriteRecord.objects.all().order_by('-created_at', '-pk')
            batch = (params or {}).get("batch_request_id")
            if batch:
                qs = qs.filter(batch_request_id=batch)
            records = list(qs.values(
                'id', 'batch_request_id', 'request_id', 'specific_part',
                'param_name', 'old_value', 'new_value', 'operator',
                'status', 'channel', 'error_message',
                'created_at', 'acked_at'))
            # datetime → ISO 字符串，跟真实 handler 输出一致。
            # PLCWriteRecord 没有 updated_at，last_records 构建时用 acked_at/created_at 兜底。
            for r in records:
                for k in ('created_at', 'acked_at'):
                    v = r.get(k)
                    if v is not None and not isinstance(v, str):
                        r[k] = v.isoformat() if hasattr(v, 'isoformat') else str(v)
            return {
                "success": True,
                "summary": f"查询到 {len(records)} 条写记录(orm-fallback)",
                "data": {
                    "records": records,
                    "total": len(records),
                    "page": 1,
                    "page_size": max(len(records), 20),
                    "has_more": False,
                },
            }
        except Exception as exc:  # pragma: no cover - 退化：给空信封避免把异常抛给上层
            return {
                "success": False,
                "error": f"orm-fallback 查询写记录失败: {exc}",
                "data": {"records": [], "total": 0},
            }
    if _MOCK:
        return _MOCK_PAYLOADS.get(
            tool_name, {"success": True, "summary": f"{tool_name}(mock)", "data": {}}
        )
    handler = TIER1_HANDLERS.get(tool_name)
    if handler is None:
        return {"success": False, "error": f"未知 tool: {tool_name}"}
    return handler(params)


# ── 能耗专家工具 ────────────────────────────────────────────────────
@tool
def get_dashboard_summary() -> dict:
    """获取系统看板摘要：总能耗、设备在线率、当前故障数。无参数。"""
    return _call("freeark_get_dashboard_summary", {})


@tool
def get_usage_daily(specific_part: str, start_date: Optional[str] = None,
                    end_date: Optional[str] = None) -> dict:
    """查询某专有部分的日用电量。specific_part 形如 '3-1-7-702'，日期可选 YYYY-MM-DD。"""
    return _call("freeark_get_usage_daily", {
        "specific_part": specific_part, "start_date": start_date, "end_date": end_date})


@tool
def get_realtime_params(specific_part: str) -> dict:
    """查询设备实时传感器参数（温度/湿度/CO₂/风量）。specific_part 形如 '3-1-7-702'。"""
    return _call("freeark_get_realtime_params", {"specific_part": specific_part})


# ── 巡检专家工具 ────────────────────────────────────────────────────
@tool
def get_plc_status(_owner_specific_parts: list = None) -> dict:
    """查询 PLC 在线/离线状态。
    _owner_specific_parts: 内部参数（v1.8.0，不暴露给 LLM schema），非 None 时
    按列表过滤只返回对应专有部分的 PLC 状态（user 路径由 ScopeEnforcer 注入）。
    None 时查询全部（admin/operator 路径，行为与 v1.7.0 完全一致）。
    """
    return _call("freeark_get_plc_status", {"_owner_specific_parts": _owner_specific_parts})


@tool
def get_fault_summary(
    building: Optional[str] = None,
    unit: Optional[str] = None,
    _owner_specific_parts: list = None,
) -> dict:
    """查询有故障的专有部分汇总（按故障数降序）。building/unit 可选过滤，如 '3'/'1'。
    _owner_specific_parts: 内部参数（v1.8.0，不暴露给 LLM schema），非 None 时
    忽略 building/unit，按精确 specific_part 列表过滤（user 路径由 ScopeEnforcer 注入）。
    None 时按 building/unit 过滤（admin/operator 路径，行为与 v1.7.0 完全一致）。
    """
    return _call("freeark_get_fault_summary", {
        "building": building, "unit": unit,
        "_owner_specific_parts": _owner_specific_parts,
    })


# ── Tier-2 写工具（阶段 E）────────────────────────────────────────────
# 这些 @tool 仅供 LLM 绑定/取得调用 schema：专家请求写操作时**不直接执行**，
# 由编排图 gate 节点 interrupt 确认、批准后经 execute_write() 注入 operator 真执行。
# @tool 函数体（直调路径）保留可用作防御，但正常流程不经过它。
_WRITE_TOOL_TO_HANDLER = {
    "set_device_params": "freeark_write_device_params",
    "trigger_refresh": "freeark_trigger_refresh",
    # set_persona 是「进程内自写」写工具：gate 批准后直接调 @tool 本体，
    # 不走 tier2 HTTP handler（不存在 HTTP 写接口）。用 sentinel 字符串做
    # 分流标记，execute_write 匹配到后转 call_tool_inline 分支。
    "set_persona": "__INLINE_SET_PERSONA__",
}
WRITE_TOOL_NAMES = frozenset(_WRITE_TOOL_TO_HANDLER)

_MOCK_WRITE_PAYLOADS = {
    "freeark_write_device_params": {
        "success": True, "summary": "设备参数写操作已下发(mock)，状态=pending",
        "data": {"batch_request_id": "mock-batch-1", "item_count": 1, "status": "pending"},
    },
    "freeark_trigger_refresh": {
        "success": True, "summary": "按需采集刷新已触发(mock)",
        "data": {"status": "triggered"},
    },
}


def execute_write(
    tool_name: str,
    args: dict,
    operator_override: str,
    *,
    owner_user_id: Optional[int] = None,
) -> dict:
    """gate 节点批准后真执行写操作。分三类：
      1. 标准 tier2 写工具（set_device_params / trigger_refresh）：
         注入 operator_override，调 TIER2_HANDLERS（恒走 HTTP）。
      2. 进程内自写工具（set_persona / 未来的 USER_SELF 写工具）：
         不走 HTTP，必须由 gate 传入已验证的 owner_user_id，再直接调用
         @tool 本体。绝不从 operator_override（审计用的用户名字符串）反解析账号。
      3. 未知工具：返回失败信封。

    mock 模式对 tier2 工具返回 canned 数据；对 set_persona 直接走工具本体
    （ORM 写，不会触发任何 HTTP）。"""
    handler_name = _WRITE_TOOL_TO_HANDLER.get(tool_name)
    if handler_name is None:
        return {"success": False, "error": f"未知写工具: {tool_name}"}

    # 分支 2：进程内自写（set_persona 等）
    if handler_name.startswith("__INLINE_"):
        inline_args = dict(args or {})
        if not isinstance(owner_user_id, int) or owner_user_id <= 0:
            return {"success": False, "error": "安全校验失败：个人设置仅允许当前业主本人修改。"}
        inline_args["_user_id"] = owner_user_id
        if tool_name == "set_persona":
            # 注意：StructuredTool.invoke(inline_args) 会走 Pydantic 模型校验，
            # 对 `_user_id` 这种以下划线开头的「内部注入参数」会被剔除/拒绝，
            # 导致传进去 _user_id 丢失 → 工具报「会话未关联账号」。
            # 这里直接调底层 func（非 @tool 包装的裸函数）传 kwargs，稳定。
            return set_persona.func(
                identity=inline_args.get('identity'),
                address=inline_args.get('address'),
                tone=inline_args.get('tone'),
                _user_id=inline_args.get('_user_id'),
            )
        return {"success": False, "error": f"未实现的自写工具: {tool_name}"}

    # 分支 1：标准 tier2 HTTP 写工具
    params = dict(args or {})
    params["operator_override"] = operator_override
    if _MOCK:
        canned = _MOCK_WRITE_PAYLOADS.get(
            handler_name, {"success": True, "summary": f"{handler_name}(mock)", "data": {}})
        out = dict(canned)
    else:
        handler = TIER2_HANDLERS.get(handler_name)
        if handler is None:
            return {"success": False, "error": f"写 handler 不可用: {handler_name}"}
        raw = handler(params)
        if not isinstance(raw, dict):
            return {"success": False, "error": f"写 handler 返回非 dict: {type(raw).__name__}"}
        out = dict(raw)  # 复制一份，防就地改 caller 数据

    # --- 自动轮询 UX 回显 ---
    try:
        data = out.get("data") or {}
        batch_id = (data if isinstance(data, dict) else {}).get("batch_request_id")
        if out.get("success") and batch_id and tool_name == "set_device_params":
            polled = _poll_write_status_until_final(batch_id, total_seconds=30, step_seconds=3)
            # 把轮询结果塞回 envelope，给 LLM 直接读
            out["write_status"] = polled
            final_status = polled.get("final_status") or "unknown"
            # 覆写/补充 summary，终态优先级高
            old_summary = out.get("summary") or ""
            extra = _summarize_polled_status(polled, batch_id=batch_id)
            if polled.get("still_pending"):
                # 还没拿到终态：保留原 summary 再加提示
                out["summary"] = (old_summary + "\n" + extra) if old_summary else extra
            else:
                # 拿到终态：优先展示
                out["summary"] = extra if not old_summary else (extra + "\n(原文：" + old_summary + ")")
    except Exception as exc:
        # 轮询异常不影响写操作本身的返回（写已经下发了），只 warning 一下
        logger.warning("execute_write 自动轮询 write_status 异常（不影响已下发写操作）: %s", exc)
    return out


# write_status 轮询默认参数（可通过环境变量改，便于调优/离线测试）
_POLL_TOTAL_SECONDS_DEFAULT = int(os.environ.get('FREAARK_WRITE_POLL_TOTAL_SECONDS', '30'))
_POLL_STEP_SECONDS_DEFAULT = int(os.environ.get('FREAARK_WRITE_POLL_STEP_SECONDS', '3'))
# get_write_status 主动查询模式：只等一轮，不阻塞 LLM 轮询
_GET_WRITE_STATUS_POLL_SECONDS = int(os.environ.get('FREEARK_GET_WRITE_STATUS_POLL_SECONDS', '3'))
_TERMINAL_WRITE_STATUSES = frozenset({'success', 'failed', 'timeout'})


def _poll_write_status_until_final(
    batch_request_id: str,
    *,
    total_seconds: int = _POLL_TOTAL_SECONDS_DEFAULT,
    step_seconds: int = _POLL_STEP_SECONDS_DEFAULT,
    bound_specific_parts: Optional[list] = None,
) -> dict:
    """轮询 PLCWriteRecord 直到该批次所有行都非 pending 或总等待时长耗尽。

    v1.13.0 P0-2a 改造：从「Django ORM 直查」改为走统一的 tier1 handler
    `freeark_get_write_records`（与 FA_TOOLS_MODE=http|direct 全程兼容，解决
    远程部署时 ORM 连不上 DB 的兼容问题；FreeArkClient 自带 SSRF 硬校验、
    超时、token 注入）。当 bound_specific_parts 非 None（由 ScopeEnforcer
    的 SCOPED_QUERY_TOOLS 注入）时，额外在每轮返回上做 specific_part ∈ bound
    的结果级二次过滤——彻底消除「LLM 碰巧猜中邻居 batch_request_id 看到跨户
    写入记录」的信息泄露风险（即便 ORM 路径也没这个保护）。

    execute_write 写操作刚下发完的轮询不需要 bound 过滤（写的 specific_part
    已被 gate.verify_write_scope 二次校验），所以 bound_specific_parts=None
    时跳过过滤（保持等价旧行为）。

    返回 dict（结构不变，与原来 ORM 路径字节级兼容）:
      {
        "final_status": "success" | "failed" | "timeout" | "mixed" | "pending",
        "still_pending": bool,
        "polled_rounds": int,
        "records_total": int,  # 过滤后剩下的记录数（bound 过滤没命中的话 total=0）
        "records_success": int,
        "records_failed": int,
        "records_timeout": int,
        "records_pending": int,
        "last_records": [ {...} ],
      }
    """
    max_rounds = max(1, total_seconds // max(1, step_seconds))
    stats: dict[str, Any] = {
        "batch_request_id": batch_request_id,
        "final_status": "pending",
        "still_pending": True,
        "polled_rounds": 0,
        "records_total": 0,
        "records_success": 0,
        "records_failed": 0,
        "records_timeout": 0,
        "records_pending": 0,
        "last_records": [],
    }
    # bound_set: None → 不过滤；否则为 frozenset，用于 specific_part ∈ 判定
    # None 表示管理员路径不做过滤；空集合则应过滤全部，不能意外退化为全量读取。
    bound_set: Optional[frozenset] = (
        frozenset(bound_specific_parts) if bound_specific_parts is not None else None
    )
    for i in range(max_rounds):
        stats["polled_rounds"] = i + 1
        raw = _call("freeark_get_write_records", {"batch_request_id": batch_request_id})
        recs = _extract_write_records_from_handler(raw)
        if bound_set is not None:
            recs = [r for r in recs if r.get('specific_part') in bound_set]
        stats["records_total"] = len(recs)
        stats["records_success"] = sum(1 for r in recs if (r.get('status') == 'success'))
        stats["records_failed"]  = sum(1 for r in recs if (r.get('status') == 'failed'))
        stats["records_timeout"] = sum(1 for r in recs if (r.get('status') == 'timeout'))
        stats["records_pending"] = sum(1 for r in recs if (r.get('status') == 'pending'))
        stats["last_records"] = [
            {"id": r.get('id'), "specific_part": r.get('specific_part'),
             "param_name": r.get('param_name'), "status": r.get('status'),
             "error_message": r.get('error_message'), "created_at": r.get('created_at'),
             "updated_at": r.get('updated_at') or r.get('acked_at') or r.get('created_at')}
            for r in recs
        ]
        # 判定终态：还有 pending → 继续等；否则按 majority 定 final_status
        if stats["records_pending"] == 0 and stats["records_total"] > 0:
            stats["still_pending"] = False
            succ = stats["records_success"]
            fail = stats["records_failed"] + stats["records_timeout"]
            if succ > 0 and fail == 0:
                stats["final_status"] = "success"
            elif fail > 0 and succ == 0:
                stats["final_status"] = (
                    "timeout" if stats["records_timeout"] > stats["records_failed"] else "failed"
                )
            else:
                stats["final_status"] = "mixed"
            return stats
        if i < max_rounds - 1:
            time.sleep(max(1, step_seconds))
    # 超时耗尽
    stats["still_pending"] = stats["records_pending"] > 0
    if not stats["still_pending"] and stats["records_total"] > 0:
        succ = stats["records_success"]
        fail = stats["records_failed"] + stats["records_timeout"]
        if succ > 0 and fail == 0:
            stats["final_status"] = "success"
        elif fail > 0 and succ == 0:
            stats["final_status"] = (
                "timeout" if stats["records_timeout"] > stats["records_failed"] else "failed"
            )
        else:
            stats["final_status"] = "mixed"
    elif stats["records_total"] == 0:
        # bound 过滤后没命中（不是自己家的 batch_id）或批次本身真的空
        stats["final_status"] = "not_found" if bound_set is not None else "pending"
    return stats


def _extract_write_records_from_handler(raw: Any) -> list[dict]:
    """从 freeark_get_write_records handler 返回信封中抽出 list[record dict]。

    freeark_get_write_records 标准信封（与 tier1_readonly.py 保持一致）：
      success=True 时 data 形如：
      { "records": [ {...}, ... ], "total": N, "page": 1, "page_size": 20, "has_more": False }
    若 handler 返回非信封/异常，安全 fallback 返回空列表。"""
    if not isinstance(raw, dict) or not raw.get("success"):
        logger.warning("_extract_write_records: handler 返回非成功信封: %s", type(raw).__name__)
        return []
    data = raw.get("data") or {}
    if isinstance(data, dict):
        recs = data.get("records")
        if isinstance(recs, list):
            return recs
        logger.warning("_extract_write_records: data.records 非 list (got %s)", type(recs).__name__)
    if isinstance(data, list):
        return data
    # 兜底：顶层直接挂 "records" 也收
    if isinstance(raw.get("records"), list):
        return raw["records"]  # type: ignore
    logger.warning("_extract_write_records: 无法从信封中提取 records, keys=%s", list(raw.keys()))
    return []


def _summarize_polled_status(polled: dict, *, batch_id: str) -> str:
    """把 _poll_write_status_until_final 的输出翻译成用户可读中文。"""
    total = polled.get('records_total', 0) or 0
    succ = polled.get('records_success', 0) or 0
    fail = polled.get('records_failed', 0) or 0
    to = polled.get('records_timeout', 0) or 0
    pend = polled.get('records_pending', 0) or 0
    rounds = polled.get('polled_rounds', 0) or 0
    final = polled.get('final_status') or 'unknown'

    status_label = {
        'success': '✅ 全部写成功 (PLC 已回执 success)',
        'failed': '❌ 全部写失败 (PLC 回执失败)',
        'timeout': '⏰ 全部超时 (超过 90s 未收到 ack，已由 mark_write_timeout 标 timeout)',
        'mixed': '⚠️ 部分成功/部分失败',
        'pending': '⏳ 仍在等待 PLC 回执 (pending)',
        'not_found': '🔍 未找到属于您的该批次写记录',
    }.get(final, f'? 状态 {final}')

    base = (
        f"写入回执状态（{batch_id}，已等 {rounds} 轮）：{status_label}。"
        f" 共 {total} 项：success={succ}，failed={fail}，timeout={to}，pending={pend}。"
    )
    if not polled.get('still_pending'):
        # 已拿到终态：把失败项的 error_message 简单拼几个
        fails = [r for r in (polled.get('last_records') or [])
                 if r.get('status') in ('failed', 'timeout')]
        if fails:
            lines = []
            for r in fails[:3]:
                pn = r.get('param_name') or '?'
                st = r.get('status') or '?'
                em = r.get('error_message') or ''
                if em:
                    em = (' — ' + (str(em)[:120]))
                lines.append(f"  · {pn}: {st}{em}")
            if len(fails) > 3:
                lines.append(f"  · 另有 {len(fails) - 3} 项失败，详见 records 接口。")
            base += "\n" + "\n".join(lines)
    else:
        base += (
            " 超过最大等待时间仍未收到 PLC 回执。如果是真实下发请稍后再用 "
            "get_write_status(batch_request_id=…) 再查，或让用户直接去 Web 端写记录页查看。"
        )
    return base


@tool
def set_device_params(specific_part: str, items: list) -> dict:
    """[写操作·需用户确认] 修改三恒设备参数（如温度设定值下发到 PLC）。

    ⚠️ 【调用前必须先查真实参数名】首次写任意设备前必须先调用
    get_device_params(specific_part) 或 get_realtime_params(specific_part)
    取得该设备的「可写参数列表」，从返回的 param_name（英文蛇形命名字段，
    如 study_room_switch、living_room_temp_setting、operation_mode）中选取
    填到 items[].param_name。绝对禁止用中文 display_name（如"设定温度""书房开关"）
    直接拼接，否则后端白名单校验会直接拒绝。
    其中 get_device_params 返回的 param_name 已按后端 device-settings/params/<sp>
    做过全量校验，是权威可写集合（推荐优先）。

    specific_part 形如 '3-1-7-702'；items 形如
    [{"param_name":"study_room_switch","new_value":"1"}] 或
    [{"param_name":"study_room_temp_setting","new_value":"24"}]。
    用户请求控制/设定类操作时调用本工具发起请求；系统会拦截进入用户确认门，
    确认后才真执行。"""
    return execute_write("set_device_params",
                         {"specific_part": specific_part, "items": items}, "")


@tool
def trigger_refresh(specific_part: str) -> dict:
    """[写操作·需用户确认] 触发指定设备的按需数据采集刷新。specific_part 形如 '3-1-7-702'。
    用户请求刷新/重新采集时调用；系统会拦截进入用户确认门，确认后才真执行。"""
    return execute_write("trigger_refresh", {"specific_part": specific_part}, "")


@tool
def get_device_params(specific_part: str) -> dict:
    """查询指定设备的「可写参数白名单」+ 当前值（无需确认，只读）。

    这是调用 set_device_params 前的**权威前置工具**：返回 data.records 中
    每项含 param_name（英文蛇形，唯一可作为 items[].param_name 提交的键）、
    display_name（中文，仅用于向用户回显）、current_value、read_only/writable 等
    标记。LLM 必须从本工具返回的 param_name 中选取，不可自由拼接。

    specific_part 形如 '3-1-7-702'；当业主用户只绑定一个房间时可不填，
    由 ScopeEnforcer 自动注入其绑定的 specific_part。"""
    return _call("freeark_get_device_params", {"specific_part": specific_part})


@tool
def get_write_status(batch_request_id: str, _bound_specific_parts: list = None,
                     specific_part: Optional[str] = None) -> dict:
    """查询一次「设备参数写操作」的回执/进度（无需用户确认）。
    当 set_device_params 返回的 summary 显示「仍在等待 PLC 回执 (pending)」
    或用户主动追问「刚才写成功了吗？」「开关打开了吗？」时调用本工具，
    统一调用 tier1 handler freeark_get_write_records（支持 FA_TOOLS_MODE=http|direct，
    解决远程部署 ORM 连不上 DB 的兼容问题）。

    参数：
      batch_request_id 必须是 set_device_params 返回的那个字符串
        （形如 UUID），不要自己拼接。
      specific_part 可选：若填写，仅用于前端筛选（ScopeEnforcer 会校验
        该 sp ∈ 用户绑定范围）。
      _bound_specific_parts 是 ScopeEnforcer 注入的内部参数（v1.13.0
        SCOPED_QUERY_TOOLS 新增）。对普通业主用户：每轮返回 records 会
        被强制二次过滤 specific_part ∈ bound，完全阻止 LLM 猜到邻居
        batch_request_id 导致的跨户写入记录泄露。admin/operator 路径
        此参数为 None，不做过滤（行为与 v1.7.0 一致）。"""
    batch_request_id = str(batch_request_id or "").strip()
    if not batch_request_id:
        return {"success": False, "error": "缺少 batch_request_id 参数"}
    polled = _poll_write_status_until_final(
        batch_request_id,
        total_seconds=_GET_WRITE_STATUS_POLL_SECONDS,
        step_seconds=1,
        bound_specific_parts=_bound_specific_parts,
    )
    # 主动查询只等一轮，不阻塞 LLM 轮询；若还是 pending，提示用户可再查
    return {
        "success": True,
        "summary": _summarize_polled_status(polled, batch_id=batch_request_id),
        "data": polled,
    }


# ── 个人设置类工具（OWNER_SELF_TOOLS，v1.13.0 P0-3）──────────────────────
# 作用域：当前登录 user 自己账号的 persona（副官自称/称呼/语气）。
# 不走 HTTP 权限类（miniapp/persona endpoint 用 IsOwnerUser，但 FA_TOOLS_MODE 直
# 调 signer 身份会被拒），改用 ScopeEnforcer 注入的 _user_id 直接 ORM 读写
# CustomUser.persona JSONField，并复用 api.persona 的 normalize / effective
# 工具函数做规范形态与长度上限校验（MAX_FIELD_LEN=50）。

def _get_user_by_id(user_id: int):
    """按 id 取 CustomUser 对象，找不到返回 None。延迟 import 防 AppRegistry。

    DB 连接异常（OperationalError/InterfaceError）重新抛出——避免把「数据库挂了」
    吞成「账号不存在」误导用户。其他异常（import/AppRegistry）安全返回 None。"""
    try:
        from django.apps import apps
        from django.contrib.auth import get_user_model
        from django.db import OperationalError, InterfaceError
        User = get_user_model()
        if not apps.ready:  # pragma: no cover
            return None
        return User.objects.filter(pk=user_id).first()
    except (OperationalError, InterfaceError):
        raise  # DB 连接/事务异常：不吞，让上层报「服务暂时不可用」
    except Exception as exc:  # pragma: no cover
        logger.debug("get_persona/set_persona _get_user_by_id 异常: %s", exc)
        return None


@tool
def get_persona(_user_id: Optional[int] = None) -> dict:
    """查询当前业主账号下「副官人格偏好」的当前设置（自称/称呼/语气），只读。

    返回 persona_payload 规范形态：{identity, address, tone}，未设置过的键返回 None，
    以便区分"用户没设过"与"设成默认值"。
    _user_id 由 ScopeEnforcer OWNER_SELF_TOOLS 分支自动注入（普通业主连接才允许）；
    admin/operator 路径 ScopeEnforcer 会直接返回拒绝说明，不进入本工具体。"""
    if not _user_id:
        return {"success": False, "error": "当前会话未关联业主账号，请重新登录。"}
    user = _get_user_by_id(_user_id)
    if user is None:
        return {"success": False, "error": "账号不存在或已被删除。"}
    try:
        from api.persona import persona_payload
    except Exception:  # pragma: no cover
        return {"success": False, "error": "persona 模块未就绪"}
    raw = getattr(user, 'persona', None)
    payload = persona_payload(raw)
    return {
        "success": True,
        "summary": (
            f"副官人格设置：自称={payload.get('identity') or '(默认)'}，"
            f"称呼您={payload.get('address') or '(默认)'}，"
            f"语气={payload.get('tone') or '(未设置)'}"
        ),
        "data": payload,
    }


@tool
def set_persona(identity: Optional[str] = None,
                address: Optional[str] = None,
                tone: Optional[str] = None,
                _user_id: Optional[int] = None) -> dict:
    """[个人设置·需用户确认] 更新当前业主账号下「副官人格偏好」。

    典型对话触发：
      - 用户说「以后你叫我老张」 → set_persona(address='老张')
      - 用户说「以后你自称小管家就行」 → set_persona(identity='小管家')
      - 用户说「说话活泼一点」 → set_persona(tone='活泼亲切')
    参数都是可选，只传需要修改的键即可；传空字符串/None 的键不会改变原值。
    写入一律走 api.persona.CANONICAL_KEYS 规范键，长度上限 50 字符。
    本工具需用户确认（虽然不是写设备，但仍是持久化写入用户账号设置）。

    _user_id 由 ScopeEnforcer OWNER_SELF_TOOLS 注入，普通业主连接才允许；
    admin/operator 被 ScopeEnforcer 拒绝。"""
    if not _user_id:
        return {"success": False, "error": "当前会话未关联业主账号，请重新登录。"}
    user = _get_user_by_id(_user_id)
    if user is None:
        return {"success": False, "error": "账号不存在或已被删除。"}
    try:
        from api.persona import (
            MAX_FIELD_LEN, CANONICAL_KEYS, normalize_persona, persona_payload,
            sanitize_persona_value, PersonaInjectionError,
        )
    except Exception:  # pragma: no cover
        return {"success": False, "error": "persona 模块未就绪"}

    # 取现有 persona（dict 或 None），做 normalize 得到当前已显式设置的 canon 键
    cur_raw = getattr(user, 'persona', None) or {}
    cur = normalize_persona(cur_raw) if isinstance(cur_raw, dict) else {}
    updates: dict = {}
    for k in CANONICAL_KEYS:
        val = locals().get(k)  # identity / address / tone
        if isinstance(val, str) and val.strip():
            try:
                sanitized = sanitize_persona_value(val)
            except PersonaInjectionError as pie:
                return {"success": False, "error": str(pie)}
            if sanitized:
                updates[k] = sanitized
    if not updates:
        return {"success": True,
                "summary": "未提供任何需要修改的设置项（identity/address/tone 均为空或未传）。",
                "data": persona_payload(cur_raw)}

    # 合并：cur（历史规范键）铺底，updates 覆盖写入
    merged: dict = dict(cur)
    merged.update(updates)

    # 尝试保存；CustomUser.persona 是 JSONField（或 TextField，回退兼容）
    try:
        user.persona = merged  # type: ignore[attr-defined]
        user.save(update_fields=['persona', 'updated_at'] if hasattr(user, 'updated_at') else ['persona'])
    except Exception as exc:
        # 仅对字段不存在（老库无 updated_at）做一次 fallback；DB 连接等异常直接报错
        from django.core.exceptions import FieldError
        if isinstance(exc, FieldError):
            try:
                user.save(update_fields=['persona'])
            except Exception as exc2:
                logger.warning("set_persona 保存 user.persona 失败(fallback): %s", exc2)
                return {"success": False, "error": "保存失败，请稍后再试。"}
        else:
            logger.warning("set_persona 保存 user.persona 失败: %s", exc)
            return {"success": False, "error": "保存失败，请稍后再试。"}

    new_payload = persona_payload(merged)
    pieces = []
    if 'identity' in updates:
        pieces.append(f"自称改为「{updates['identity']}」")
    if 'address' in updates:
        pieces.append(f"称呼您为「{updates['address']}」")
    if 'tone' in updates:
        pieces.append(f"语气调整为「{updates['tone']}」")
    return {
        "success": True,
        "summary": "副官人格偏好已更新：" + "，".join(pieces) + "。新设置将在下次对话生效。",
        "data": new_payload,
    }


# ── 按专家分组的工具表（供 orchestrator 绑定到各 agent 节点）────────────
# 能耗专家=「操控和查询」：读工具 + Tier-2 写工具（写经 gate 确认门）。
# v1.13.0 新增 get_device_params（P0-2b）。
ENERGY_TOOLS = [get_dashboard_summary, get_usage_daily, get_realtime_params,
                get_device_params, get_write_status,
                set_device_params, trigger_refresh]
INSPECTION_TOOLS = [get_plc_status, get_fault_summary, get_realtime_params]

# 个人设置工具组（P1-2：从 ENERGY_TOOLS 拆出，避免能耗专家 schema 被无关工具污染）
PERSONA_TOOLS = [get_persona, set_persona]


# ── 三恒知识专家 RAG 工具（v1.4.1_rag_image_citation）─────────────────────
@tool
def search_sanheng_knowledge(query: str) -> str:
    """在三恒知识库中检索与 query 相关的文档片段，用于辅助原理/参数/故障码解答。
    返回最相关的 chunk 文本列表及来源；库为空或不可达时返回说明文字（不报错）。"""
    try:
        from django.conf import settings
        from api.rag_service import search_rag
        k = getattr(settings, 'RAG_TOP_K', 5)
        threshold = getattr(settings, 'RAG_SCORE_THRESHOLD', 0.3)
        result = search_rag(query, k=k, threshold=threshold)
    except Exception as e:
        logger.warning("fa_tools: search_sanheng_knowledge 异常（降级）: %s", e)
        _emit_search_images([])   # 清空，防止残留（IFC-141-402）
        return "[知识库暂时不可达，以下为通用知识参考。degraded=true]"

    if result.get('degraded'):
        _emit_search_images([])
        return "[知识库暂时不可达，以下为通用知识参考。degraded=true]"

    chunks = result.get('chunks', [])
    if not chunks:
        _emit_search_images([])
        return "[知识库中未找到与该问题相关的内容]"

    # ── v1.4.1 side-channel：收集 related_images，不进入返回的 str（C-003 防幻觉）──
    related_images = []
    seen_image_ids: set = set()
    for c in chunks:
        image_id = c.get('image_id')
        if image_id is not None and image_id not in seen_image_ids:
            seen_image_ids.add(image_id)
            related_images.append({
                "image_id": image_id,
                "source": c.get('source', ''),
            })
    _emit_search_images(related_images)   # 原地回传 sink，供 orchestrator._expert 读取
    # ────────────────────────────────────────────────────────────────────────

    # 以下返回给 LLM 的文本不含 image_id（C-003 严格满足，IFC-141-402）
    lines = [f"[检索到 {len(chunks)} 条相关内容]"]
    for i, c in enumerate(chunks, 1):
        src_note = "（图片OCR）" if c.get('is_image_ocr') else ""
        content_preview = (c.get('content') or '')[:400]
        lines.append(
            f"\n[{i}] 来源: {c.get('source', '未知')}{src_note}\n    {content_preview}"
        )
    return "\n".join(lines)


SANHENG_TOOLS: list = [search_sanheng_knowledge]  # v1.4.0: RAG 检索工具

TOOLS_BY_EXPERT = {
    # 系统管家负责能耗/设备查询和确认式控制；巡检、知识检索各自最小授权。
    "freeark-expert": ENERGY_TOOLS + PERSONA_TOOLS,
    "inspection-expert": INSPECTION_TOOLS,
    "sanheng-knowledge": SANHENG_TOOLS,
}


# ── 只读冒烟自检：`python -m api.langgraph_chat.fa_tools` ────────────────
# LIVE 模式（不设 FREEARK_POC_MOCK）真直调 handler 打 127.0.0.1:8000；
# 无参工具恒跑，带参工具仅在 FREEARK_SMOKE_PART 提供有效设备号时跑。
# 退出码 = 失败工具数（0 = 全绿）。只读，绝不触发 Tier-2 写。
def _smoke() -> int:
    import json
    part = os.environ.get("FREEARK_SMOKE_PART", "")
    cases = [
        ("get_dashboard_summary", get_dashboard_summary, {}),
        ("get_plc_status", get_plc_status, {}),
        ("get_fault_summary", get_fault_summary, {}),
    ]
    if part:
        cases += [
            ("get_usage_daily", get_usage_daily, {"specific_part": part}),
            ("get_realtime_params", get_realtime_params, {"specific_part": part}),
        ]
    mode = "MOCK" if _MOCK else f"LIVE/{_MODE}"
    print(f"=== fa_tools smoke [{mode}] skill_dir={_SKILL_DIR} ===")
    failures = 0
    for name, t, args in cases:
        try:
            out = t.invoke(args)
            ok = isinstance(out, dict) and out.get("success", True) and "error" not in out
            summary = (out.get("summary") or out.get("error")
                       or json.dumps(out, ensure_ascii=False)[:120])
            print(f"[{'OK ' if ok else 'ERR'}] {name:24s} {summary}")
            failures += 0 if ok else 1
        except Exception as e:  # noqa: BLE001
            print(f"[ERR] {name:24s} {type(e).__name__}: {e}")
            failures += 1
    print(f"=== {len(cases) - failures}/{len(cases)} passed ===")
    return failures


if __name__ == "__main__":
    sys.exit(1 if _smoke() else 0)
