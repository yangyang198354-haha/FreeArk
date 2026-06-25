"""
FreeArk Skill — Tier-2 写操作 Tool 实现（5 个 function）

Tier-2 特性（来自 CONFIRM-2, CONFIRM-3）：
  - 所有写操作端点均需二次确认
  - 安全层 1（Agent system prompt 规则）+ 安全层 2（SKILL.md description [Tier-2] 标注）
  - operator_override 字段追溯 chatuser（已上线，views_device_settings.py 已支持）
  - 超时 8 秒（含 MQTT ACK 等待）

文档引用：ARCH-LOBSTER-002 §3.2 (Tier-2 调用链), MOD-SK-01, CONFIRM-2/CONFIRM-3
移植来源：agents/freeark-skill/tools/tier2_write.js (v1)
版本：2.0.0（Python 重写，逻辑等价于 v1）

注意（v2 vs v1 差异）：
  v1 JS 在代码层做了 confirmed !== true 的硬拦截（requireConfirmation 函数）。
  v2 Python 中，二次确认机制由 SKILL.md 中 Tier-2 tool 的 description [Tier-2] 标注
  + system prompt 安全规则双重保障（ARCH-LOBSTER-002 ADR-002 §v2更新）。
  Python 实现不再做 confirmed 参数检查，由 Agent 层保证只在用户确认后调用。
  operator_override 仍由调用方（Agent）通过参数传入。
"""

import sys
import os
import re

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from freeark_client import FreeArkClient


def _client() -> FreeArkClient:
    return FreeArkClient()


def _build_operator(operator_override: str) -> str:
    """
    验证并清洗 operator_override 字段（来自 Agent 传入，格式 energy-agent::<chatuser>）。

    移植自：tier2_write.js buildOperator
    v2 注意：chatuser 已由 ChatConsumer 注入 [__freeark_user__:<username>] 前缀，
    Agent 从 system prompt 规则中提取并构造该字段。
    """
    if not operator_override:
        return "energy-agent::unknown"
    # 清洗非法字符，限长 80
    safe = re.sub(r"[^a-zA-Z0-9_@.:/-]", "_", operator_override)[:80]
    return safe


# ──────────────────────────────────────────────────────────────────────
# Tool 1: freeark_write_device_params
# POST /api/device-settings/write/
# 风险：CRITICAL — 直接下发 PLC 写命令（经 MQTT 路由到三恒设备）
# ──────────────────────────────────────────────────────────────────────
def freeark_write_device_params(params: dict) -> dict:
    """
    [Tier-2 写操作] 修改三恒设备参数（温控参数下发）。

    Args:
        specific_part: 设备标识符，如 "3-1-7-702"（必须）
        items: 参数变更列表，每项 {param_name, new_value}（必须）
        operator_override: "energy-agent::<chatuser>"（由 Agent 从 chatuser 前缀提取构造）

    移植自：tier2_write.js freeark_write_device_params
    """
    specific_part = params.get("specific_part")
    items = params.get("items")
    operator_override = params.get("operator_override", "")

    if not specific_part:
        return {"success": False, "error": "缺少 specific_part 参数", "http_status": 400}
    if not items or not isinstance(items, list) or len(items) == 0:
        return {
            "success": False,
            "error": "缺少 items 参数（要修改的参数列表，格式 [{param_name, new_value}]）",
            "http_status": 400,
        }

    operator = _build_operator(operator_override)

    body = {
        "specific_part": specific_part,
        "items": [
            {"param_name": str(i.get("param_name", "")), "new_value": str(i.get("new_value", ""))}
            for i in items
        ],
        "operator_override": operator,
    }

    result = _client().post("/api/device-settings/write/", body, timeout=8)
    if not result["success"]:
        return result

    data = result["data"]
    batch_id = data.get("batch_request_id", "?")
    item_count = data.get("item_count", len(items))
    return {
        "success": True,
        "data": data,
        "summary": (
            f"设备 {specific_part} 参数写操作已下发，"
            f"batch_request_id={batch_id}，共 {item_count} 项，"
            f"operator={operator}，状态=pending（设备响应需 10-30 秒）"
        ),
    }


# ──────────────────────────────────────────────────────────────────────
# Tool 2: freeark_trigger_refresh
# POST /api/devices/ondemand-refresh/
# 风险：MEDIUM — 触发边缘任务，无硬件风险
# ──────────────────────────────────────────────────────────────────────
def freeark_trigger_refresh(params: dict) -> dict:
    """
    [Tier-2 写操作] 触发指定设备的按需数据采集刷新。

    Args:
        specific_part（必须）
        operator_override（可选）

    移植自：tier2_write.js freeark_trigger_refresh
    """
    specific_part = params.get("specific_part")
    if not specific_part:
        return {"success": False, "error": "缺少 specific_part 参数", "http_status": 400}

    operator = _build_operator(params.get("operator_override", ""))
    body = {"specific_part": specific_part, "operator": operator}

    result = _client().post("/api/devices/ondemand-refresh/", body, timeout=8)
    if not result["success"]:
        return result
    return {
        "success": True,
        "data": result["data"],
        "summary": f"设备 {specific_part} 按需采集任务已触发，operator={operator}",
    }


# ──────────────────────────────────────────────────────────────────────
# Tool 3: freeark_service_action
# POST /api/services/<name>/action/
# 风险：CRITICAL — 可停止/重启生产服务
# ──────────────────────────────────────────────────────────────────────
def freeark_service_action(params: dict) -> dict:
    """
    [Tier-2 写操作，高危] 对 FreeArk 系统服务执行管理操作（start/stop/restart）。

    Args:
        service_name（必须）
        action: "start" | "stop" | "restart"（必须）
        operator_override（可选）

    移植自：tier2_write.js freeark_service_action
    """
    service_name = params.get("service_name")
    action = params.get("action")

    if not service_name:
        return {"success": False, "error": "缺少 service_name 参数", "http_status": 400}
    if action not in ("start", "stop", "restart"):
        return {
            "success": False,
            "error": "action 必须为 start、stop 或 restart",
            "http_status": 400,
        }

    operator = _build_operator(params.get("operator_override", ""))
    body = {"action": action, "operator": operator}

    result = _client().post(f"/api/services/{service_name}/action/", body, timeout=8)
    if not result["success"]:
        return result
    return {
        "success": True,
        "data": result["data"],
        "summary": f"服务 {service_name} 执行 {action} 成功，operator={operator}",
    }


# ──────────────────────────────────────────────────────────────────────
# Tool 4: freeark_sync_device_tree
# POST /api/device-management/screen-device-tree/sync/
# 风险：MEDIUM — 单户同步
# ──────────────────────────────────────────────────────────────────────
def freeark_sync_device_tree(params: dict) -> dict:
    """
    [Tier-2 写操作] 触发单户设备树同步操作。

    Args:
        specific_part（可选，不填则全量）
        operator_override（可选）

    移植自：tier2_write.js freeark_sync_device_tree
    注：v1 用 owner_id，ARCH-LOBSTER-002 §10 API 映射写的是 specific_part，
        以架构文档为准（specific_part 可选）。
    """
    operator = _build_operator(params.get("operator_override", ""))
    body = {"operator": operator}
    if params.get("specific_part"):
        body["specific_part"] = params["specific_part"]

    result = _client().post(
        "/api/device-management/screen-device-tree/sync/", body, timeout=8
    )
    if not result["success"]:
        return result

    target = params.get("specific_part", "全量同步")
    return {
        "success": True,
        "data": result["data"],
        "summary": f"设备树同步任务已提交（{target}），operator={operator}",
    }


# ──────────────────────────────────────────────────────────────────────
# Tool 5: freeark_batch_sync_device_tree
# POST /api/device-management/screen-device-tree/batch-sync/
# 风险：MEDIUM — 批量同步，影响范围较大
# ──────────────────────────────────────────────────────────────────────
def freeark_batch_sync_device_tree(params: dict) -> dict:
    """
    [Tier-2 写操作] 批量设备树同步操作（影响范围广，请谨慎使用）。

    Args:
        owner_ids: 业主 ID 列表（必须，来自 ARCH-LOBSTER-002 §10）
        operator_override（可选）

    移植自：tier2_write.js freeark_batch_sync_device_tree
    """
    operator = _build_operator(params.get("operator_override", ""))
    body = {"operator": operator}
    if params.get("owner_ids"):
        body["owner_ids"] = params["owner_ids"]

    result = _client().post(
        "/api/device-management/screen-device-tree/batch-sync/", body, timeout=8
    )
    if not result["success"]:
        return result
    return {
        "success": True,
        "data": result["data"],
        "summary": f"批量设备树同步任务已提交，operator={operator}",
    }


# ──────────────────────────────────────────────────────────────────────
# Handler 映射（供 freeark_tool.py dispatch 使用）
# ──────────────────────────────────────────────────────────────────────
TIER2_HANDLERS = {
    "freeark_write_device_params": freeark_write_device_params,
    "freeark_trigger_refresh": freeark_trigger_refresh,
    "freeark_service_action": freeark_service_action,
    "freeark_sync_device_tree": freeark_sync_device_tree,
    "freeark_batch_sync_device_tree": freeark_batch_sync_device_tree,
}
