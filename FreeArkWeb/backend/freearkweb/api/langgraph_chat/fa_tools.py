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

文档引用：agents/langgraph-poc/PHASE3_ROLLOUT.md 阶段 A/B, [[lobster-agent-architecture]]
"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
from pathlib import Path
from typing import Optional

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
    """统一调用入口：mock 模式返回 canned 数据，否则调真 handler。"""
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


def execute_write(tool_name: str, args: dict, operator_override: str) -> dict:
    """gate 节点批准后真执行写操作：注入 operator_override，调 TIER2_HANDLERS（恒走 HTTP）。
    mock 模式返回 canned 数据。未知工具/handler 返回失败信封。"""
    handler_name = _WRITE_TOOL_TO_HANDLER.get(tool_name)
    if handler_name is None:
        return {"success": False, "error": f"未知写工具: {tool_name}"}
    params = dict(args or {})
    params["operator_override"] = operator_override
    if _MOCK:
        return _MOCK_WRITE_PAYLOADS.get(
            handler_name, {"success": True, "summary": f"{handler_name}(mock)", "data": {}})
    handler = TIER2_HANDLERS.get(handler_name)
    if handler is None:
        return {"success": False, "error": f"写 handler 不可用: {handler_name}"}
    return handler(params)


@tool
def set_device_params(specific_part: str, items: list) -> dict:
    """[写操作·需用户确认] 修改三恒设备参数（如温度设定值下发到 PLC）。
    specific_part 形如 '3-1-7-702'；items 形如 [{"param_name":"设定温度","new_value":"24"}]。
    用户请求控制/设定类操作时调用本工具发起请求；系统会拦截进入用户确认门，确认后才真执行。"""
    return execute_write("set_device_params",
                         {"specific_part": specific_part, "items": items}, "")


@tool
def trigger_refresh(specific_part: str) -> dict:
    """[写操作·需用户确认] 触发指定设备的按需数据采集刷新。specific_part 形如 '3-1-7-702'。
    用户请求刷新/重新采集时调用；系统会拦截进入用户确认门，确认后才真执行。"""
    return execute_write("trigger_refresh", {"specific_part": specific_part}, "")


# ── 按专家分组的工具表（供 orchestrator 绑定到各 agent 节点）────────────
# 能耗专家=「操控和查询」：读工具 + Tier-2 写工具（写经 gate 确认门）。
ENERGY_TOOLS = [get_dashboard_summary, get_usage_daily, get_realtime_params,
                set_device_params, trigger_refresh]
INSPECTION_TOOLS = [get_plc_status, get_fault_summary, get_realtime_params]


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
    "energy-expert": ENERGY_TOOLS,
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
