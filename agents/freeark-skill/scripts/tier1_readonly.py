"""
FreeArk Skill — Tier-1 只读 Tool 实现（14 个 function）

Tier-1 特性：
  - 只读 GET 操作，Agent 可自主调用，无需用户确认
  - 超时 5 秒（freeark_client.py 控制）
  - 返回格式化的 JSON 结果，对 Agent 友好

文档引用：ARCH-LOBSTER-002 §附录 API 端点映射, MOD-SK-01, CONFIRM-2
移植来源：agents/freeark-skill/tools/tier1_readonly.js (v1)
版本：2.0.0（Python 重写，逻辑等价于 v1）
"""

import sys
import os

# 支持从 SKILL.md 定义的 exec 路径直接调用（绝对路径运行时 lib/ 在同级）
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LIB_DIR = os.path.join(os.path.dirname(_SCRIPT_DIR), "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from freeark_client import FreeArkClient


def _client() -> FreeArkClient:
    """惰性初始化客户端（每次 tool 调用重建，适用独立进程模式）。"""
    return FreeArkClient()


# ──────────────────────────────────────────────────────────────────────
# Tool 1: freeark_get_realtime_params
# GET /api/devices/realtime-params/?specific_part=<id>
# ──────────────────────────────────────────────────────────────────────
def freeark_get_realtime_params(params: dict) -> dict:
    """
    查询设备实时传感器参数（温度、湿度、CO₂浓度、风量等）。

    Args:
        params.specific_part: 设备 ID，格式 <楼>-<单元>-<房号前缀>-<设备ID>，如 "3-1-7-702"

    移植自：tier1_readonly.js freeark_get_realtime_params
    """
    specific_part = params.get("specific_part")
    if not specific_part:
        return {
            "success": False,
            "error": "缺少必要参数 specific_part，格式为 '<楼>-<单元>-<房号前缀>-<设备ID>'，如 '3-1-7-702'",
        }
    result = _client().get("/api/devices/realtime-params/", {"specific_part": specific_part})
    if not result["success"]:
        return result
    data = result["data"]
    count = len(data) if isinstance(data, list) else "?"
    return {
        "success": True,
        "data": data,
        "summary": f"设备 {specific_part} 实时参数查询成功，共 {count} 条参数",
    }


# ──────────────────────────────────────────────────────────────────────
# Tool 2: freeark_get_usage_daily
# GET /api/usage/quantity/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_usage_daily(params: dict) -> dict:
    """
    查询日用量数据，支持分页和时间过滤。

    Args (all optional except specific_part):
        specific_part, energy_mode, start_date, end_date, page

    移植自：tier1_readonly.js freeark_get_usage_daily
    """
    query = {}
    for key in ("specific_part", "energy_mode", "start_date", "end_date", "page"):
        if params.get(key):
            query[key] = params[key]

    result = _client().get("/api/usage/quantity/", query)
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": "日用量数据查询成功"}


# ──────────────────────────────────────────────────────────────────────
# Tool 3: freeark_get_usage_period
# GET /api/usage/quantity/specifictimeperiod/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_usage_period(params: dict) -> dict:
    """
    查询指定时间段汇总用量。

    Args: specific_part（必须）, energy_mode, start_time, end_time

    移植自：tier1_readonly.js freeark_get_usage_period
    """
    query = {}
    for key in ("specific_part", "energy_mode", "start_time", "end_time"):
        if params.get(key):
            query[key] = params[key]

    result = _client().get("/api/usage/quantity/specifictimeperiod/", query)
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": "时间段用量汇总查询成功"}


# ──────────────────────────────────────────────────────────────────────
# Tool 4: freeark_get_usage_monthly
# GET /api/usage/quantity/monthly/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_usage_monthly(params: dict) -> dict:
    """
    查询月度用量数据。

    Args: specific_part, energy_mode, year_month (YYYY-MM，注意 v1 用 year_month 不是 month)

    移植自：tier1_readonly.js freeark_get_usage_monthly
    注：v1 参数名为 year_month，MOD-SK-02 SKILL.md 预设写的是 month——以 v1 JS 逻辑为准，
        参数名统一用 year_month（与 Django API 实际参数名一致）。
    """
    query = {}
    for key in ("specific_part", "energy_mode", "year_month"):
        if params.get(key):
            query[key] = params[key]
    # 兼容 SKILL.md 预设中写成 month 的情况
    if not query.get("year_month") and params.get("month"):
        query["year_month"] = params["month"]

    result = _client().get("/api/usage/quantity/monthly/", query)
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": "月度用量查询成功"}


# ──────────────────────────────────────────────────────────────────────
# Tool 5: freeark_get_plc_status
# GET /api/plc/connection-status/ 或 /api/plc/connection-status/<id>/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_plc_status(params: dict) -> dict:
    """
    查询 PLC 连接状态（在线/离线）。
    specific_part 不填则返回所有 PLC 状态。

    移植自：tier1_readonly.js freeark_get_plc_status
    """
    specific_part = params.get("specific_part")
    if specific_part:
        path = f"/api/plc/connection-status/{specific_part}/"
        desc = f"设备 {specific_part} 的 PLC 连接状态查询成功"
    else:
        path = "/api/plc/connection-status/"
        desc = "PLC 连接状态全量查询成功"

    result = _client().get(path)
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": desc}


# ──────────────────────────────────────────────────────────────────────
# Tool 6: freeark_get_plc_status_single
# GET /api/plc/connection-status/<id>/（单设备，与 freeark_get_plc_status 合用路由）
# ──────────────────────────────────────────────────────────────────────
def freeark_get_plc_status_single(params: dict) -> dict:
    """
    查询单个设备的 PLC 连接状态（specific_part 必须）。

    注：v1 没有独立区分 freeark_get_plc_status_single，
    这里拆分以匹配 ARCH-LOBSTER-002 §10 API 覆盖表中的 freeark_get_plc_status_single。
    """
    specific_part = params.get("specific_part")
    if not specific_part:
        return {"success": False, "error": "缺少必要参数 specific_part"}
    return freeark_get_plc_status({"specific_part": specific_part})


# ──────────────────────────────────────────────────────────────────────
# Tool 7: freeark_get_dashboard_summary
# GET /api/dashboard/summary/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_dashboard_summary(params: dict) -> dict:
    """
    获取系统仪表盘摘要数据（总能耗、在线率等）。
    PoC 首选 tool（来自用户编排 Step 3 指定）。

    移植自：tier1_readonly.js freeark_get_dashboard_summary
    """
    result = _client().get("/api/dashboard/summary/")
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": "看板摘要查询成功"}


# ──────────────────────────────────────────────────────────────────────
# Tool 8: freeark_get_services_status
# GET /api/dashboard/services/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_services_status(params: dict) -> dict:
    """
    获取 FreeArk 系统各服务的运行状态。

    移植自：tier1_readonly.js freeark_get_services_status
    """
    result = _client().get("/api/dashboard/services/")
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": "系统服务状态查询成功"}


# ──────────────────────────────────────────────────────────────────────
# Tool 9: freeark_get_power_status
# GET /api/dashboard/power-status/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_power_status(params: dict) -> dict:
    """
    获取各区域的供电状态。

    移植自：tier1_readonly.js freeark_get_power_status
    """
    result = _client().get("/api/dashboard/power-status/")
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": "供电状态查询成功"}


# ──────────────────────────────────────────────────────────────────────
# Tool 10: freeark_get_device_params
# GET /api/device-settings/params/<id>/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_device_params(params: dict) -> dict:
    """
    查询指定设备的可写参数列表（含当前值）。

    Args: specific_part（必须）

    移植自：tier1_readonly.js freeark_get_device_params
    """
    specific_part = params.get("specific_part")
    if not specific_part:
        return {"success": False, "error": "缺少必要参数 specific_part"}
    path = f"/api/device-settings/params/{specific_part}/"
    result = _client().get(path)
    if not result["success"]:
        return result
    return {
        "success": True,
        "data": result["data"],
        "summary": f"设备 {specific_part} 可写参数查询成功",
    }


# ──────────────────────────────────────────────────────────────────────
# Tool 11: freeark_get_write_records
# GET /api/device-settings/records/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_write_records(params: dict) -> dict:
    """
    查询设备参数写操作历史记录。

    Args (all optional): specific_part, operator, status, start_time, end_time

    移植自：tier1_readonly.js freeark_get_write_records
    """
    query = {}
    for key in ("specific_part", "operator", "status", "start_time", "end_time"):
        if params.get(key):
            query[key] = params[key]

    result = _client().get("/api/device-settings/records/", query)
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": "写操作记录查询成功"}


# ──────────────────────────────────────────────────────────────────────
# Tool 12: freeark_get_device_tree
# GET /api/owners/<pk>/device-tree/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_device_tree(params: dict) -> dict:
    """
    获取指定业主的设备树（所有下属设备列表）。

    Args: owner_id（必须）

    移植自：tier1_readonly.js freeark_get_device_tree
    """
    owner_id = params.get("owner_id")
    if not owner_id:
        return {"success": False, "error": "缺少必要参数 owner_id（业主 ID）"}
    path = f"/api/owners/{owner_id}/device-tree/"
    result = _client().get(path)
    if not result["success"]:
        return result
    return {
        "success": True,
        "data": result["data"],
        "summary": f"业主 ID={owner_id} 的设备树查询成功",
    }


# ──────────────────────────────────────────────────────────────────────
# Tool 13: freeark_get_service_detail
# GET /api/services/<name>/detail/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_service_detail(params: dict) -> dict:
    """
    获取单个系统服务的详细状态信息。

    Args: service_name（必须），如 "freeark-backend"

    移植自：tier1_readonly.js freeark_get_service_detail
    """
    service_name = params.get("service_name")
    if not service_name:
        return {"success": False, "error": "缺少必要参数 service_name（服务名称）"}
    path = f"/api/services/{service_name}/detail/"
    result = _client().get(path)
    if not result["success"]:
        return result
    return {
        "success": True,
        "data": result["data"],
        "summary": f"服务 {service_name} 详情查询成功",
    }


# ──────────────────────────────────────────────────────────────────────
# Tool 14: freeark_get_plc_latest
# GET /api/plc-latest/
# ──────────────────────────────────────────────────────────────────────
def freeark_get_plc_latest(params: dict) -> dict:
    """
    获取所有 PLC 的最新参数（全量快照），可选按 specific_part 过滤。

    移植自：tier1_readonly.js freeark_get_plc_latest
    """
    query = {}
    if params.get("specific_part"):
        query["specific_part"] = params["specific_part"]

    result = _client().get("/api/plc-latest/", query)
    if not result["success"]:
        return result
    return {"success": True, "data": result["data"], "summary": "PLC 最新参数查询成功"}


# ──────────────────────────────────────────────────────────────────────
# Handler 映射（供 freeark_tool.py dispatch 使用）
# ──────────────────────────────────────────────────────────────────────
TIER1_HANDLERS = {
    "freeark_get_realtime_params": freeark_get_realtime_params,
    "freeark_get_usage_daily": freeark_get_usage_daily,
    "freeark_get_usage_period": freeark_get_usage_period,
    "freeark_get_usage_monthly": freeark_get_usage_monthly,
    "freeark_get_plc_status": freeark_get_plc_status,
    "freeark_get_plc_status_single": freeark_get_plc_status_single,
    "freeark_get_dashboard_summary": freeark_get_dashboard_summary,
    "freeark_get_services_status": freeark_get_services_status,
    "freeark_get_power_status": freeark_get_power_status,
    "freeark_get_device_params": freeark_get_device_params,
    "freeark_get_write_records": freeark_get_write_records,
    "freeark_get_device_tree": freeark_get_device_tree,
    "freeark_get_service_detail": freeark_get_service_detail,
    "freeark_get_plc_latest": freeark_get_plc_latest,
}
