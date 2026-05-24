#!/usr/bin/env python3
"""
FreeArk Skill PoC — freeark_get_dashboard_summary 单 tool 脚本

PoC 阶段专用：独立脚本，仅实现 GET /api/dashboard/summary/ 这一个 tool。
用于验证 SKILL.md CLI exec 调用链是否工作正常（REQ-NFR-006 PoC 第一里程碑）。

用法（OpenClaw 调用，取决于 SKILL.md exec 字段和 §7 实测结果）：
  独立进程模式（stdin 传 JSON）：
    echo '{}' | python3 freeark_get_dashboard_summary.py

  独立进程模式（argv 传 JSON，部分 OpenClaw 版本）：
    python3 freeark_get_dashboard_summary.py '{}'

输出（stdout，JSON）：
  成功：{"success": true, "data": {...}, "summary": "看板摘要查询成功"}
  失败：{"success": false, "error": "..."}

退出码：0（成功或可恢复错误）；1（环境配置错误）

文档引用：MOD-PoC, ARCH-LOBSTER-002 §9, 用户 Step 3 编排指令
"""

import sys
import json
import os

# ── 路径设置（兼容 OpenClaw 以任意 cwd 启动此脚本）──────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_SCRIPT_DIR)
_LIB_DIR = os.path.join(_SKILL_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

try:
    from freeark_client import FreeArkClient
except ImportError as e:
    print(json.dumps({"success": False, "error": f"导入 freeark_client 失败: {e}"}))
    sys.exit(1)


def get_dashboard_summary() -> dict:
    """调用 FreeArk GET /api/dashboard/summary/ 并返回结构化结果。"""
    try:
        client = FreeArkClient()
    except RuntimeError as e:
        return {"success": False, "error": str(e)}

    result = client.get("/api/dashboard/summary/")
    if not result["success"]:
        return result
    return {
        "success": True,
        "data": result["data"],
        "summary": "看板摘要查询成功",
    }


def main():
    # PoC：忽略输入参数（此 tool 不需要任何参数）
    # 尝试解析 stdin 或 argv，但不依赖其内容
    _input = {}
    if len(sys.argv) > 1:
        try:
            _input = json.loads(sys.argv[1])
        except (json.JSONDecodeError, IndexError):
            pass
    else:
        raw = sys.stdin.read().strip()
        if raw:
            try:
                _input = json.loads(raw)
            except json.JSONDecodeError:
                pass

    result = get_dashboard_summary()
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
