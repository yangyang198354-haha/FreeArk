"""
api.langgraph_chat.fa_tools —— FreeArk 工具桥接层（进程内复用 freeark-skill handlers）

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

import os
import sys
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool


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

try:
    from tier1_readonly import TIER1_HANDLERS  # type: ignore
except Exception as exc:  # pragma: no cover - 离线缺依赖时退化
    TIER1_HANDLERS = {}
    if not _MOCK:
        raise RuntimeError(
            f"无法导入 freeark-skill handlers（skill_dir={_SKILL_DIR}）: {exc}. "
            f"离线/单测请设 FREEARK_POC_MOCK=1"
        ) from exc


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
def get_plc_status() -> dict:
    """查询全部 PLC 在线/离线状态。无参数。"""
    return _call("freeark_get_plc_status", {})


@tool
def get_fault_summary(building: Optional[str] = None, unit: Optional[str] = None) -> dict:
    """查询有故障的专有部分汇总（按故障数降序）。building/unit 可选过滤，如 '3'/'1'。"""
    return _call("freeark_get_fault_summary", {"building": building, "unit": unit})


# ── 按专家分组的工具表（供 orchestrator 绑定到各 agent 节点）────────────
ENERGY_TOOLS = [get_dashboard_summary, get_usage_daily, get_realtime_params]
INSPECTION_TOOLS = [get_plc_status, get_fault_summary, get_realtime_params]
SANHENG_TOOLS: list = []  # 三恒知识专家纯文本，不查 API

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
    mode = "MOCK" if _MOCK else "LIVE"
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
