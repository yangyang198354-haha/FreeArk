#!/usr/bin/env python3
"""
FreeArk Skill — 统一 CLI 执行体（dispatch 入口）

功能：接收 OpenClaw 的 tool_call 请求，dispatch 到对应的 Tier-1/Tier-2 处理函数。

调用模式（取决于 §7 实测结果，PoC 后根据 FACT-11~19 更新）：
  模式 A（独立进程，stdin JSON）：
    echo '{"tool": "freeark_get_dashboard_summary", "params": {}}' | python3 freeark_tool.py

  模式 B（独立进程，argv JSON）：
    python3 freeark_tool.py '{"tool": "freeark_get_dashboard_summary", "params": {}}'

  模式 C（长驻进程，每行一条 JSON request）：
    （持续从 stdin 读取，每行一条请求，每行输出一条响应）

输出（stdout，JSON）：
  成功：{"success": true, "data": {...}, "summary": "..."}
  失败：{"success": false, "error": "..."}

退出码：0；失败时也返回 0（错误通过 JSON 上报），除非 CLI 本身参数错误返回 1

文档引用：MOD-SK-01 (CLI 执行体接口规范，预设方案 A/B), ARCH-LOBSTER-002 §4.1
版本：2.0.0（PoC 通过后此文件替换 freeark_get_dashboard_summary.py）
"""

import sys
import json
import os

# ── 路径设置 ────────────────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.dirname(_SCRIPT_DIR)
_LIB_DIR = os.path.join(_SKILL_DIR, "lib")
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

try:
    from tier1_readonly import TIER1_HANDLERS
    from tier2_write import TIER2_HANDLERS
except ImportError as e:
    print(json.dumps({"success": False, "error": f"模块导入失败: {e}"}))
    sys.exit(1)

ALL_HANDLERS = {**TIER1_HANDLERS, **TIER2_HANDLERS}


def dispatch(call: dict) -> dict:
    """根据 tool 字段 dispatch 到对应处理函数。"""
    tool_name = call.get("tool")
    params = call.get("params", {})

    if not tool_name:
        return {"success": False, "error": "缺少 'tool' 字段"}

    handler = ALL_HANDLERS.get(tool_name)
    if not handler:
        return {
            "success": False,
            "error": f"未知 tool: {tool_name}。可用 tool 列表: {sorted(ALL_HANDLERS.keys())}",
        }

    try:
        return handler(params)
    except Exception as e:
        return {"success": False, "error": f"tool 执行异常: {type(e).__name__}: {e}"}


def read_input() -> dict:
    """
    从 stdin 或 argv 读取调用请求。
    自动检测调用模式：
      - argv[1] 有内容 → 模式 B（argv JSON）
      - 否则读 stdin → 模式 A（stdin JSON）
    """
    if len(sys.argv) > 1:
        raw = sys.argv[1]
    else:
        raw = sys.stdin.read().strip()

    if not raw:
        return None

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"JSON 解析失败: {e}，原始输入: {raw[:100]}"}))
        sys.exit(1)


def main_single():
    """模式 A/B：单次调用，处理后退出。"""
    call = read_input()
    if call is None:
        print(json.dumps({"success": False, "error": "无输入参数"}))
        sys.exit(1)

    result = dispatch(call)
    print(json.dumps(result, ensure_ascii=False))


def main_persistent():
    """
    模式 C：长驻进程，每行一条 JSON 请求，每行输出一条 JSON 响应。
    使用方式：在 SKILL.md exec 字段加 --persistent 标志时激活。
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            call = json.loads(line)
            result = dispatch(call)
        except json.JSONDecodeError as e:
            result = {"success": False, "error": f"JSON 解析失败: {e}"}
        except Exception as e:
            result = {"success": False, "error": f"未知异常: {e}"}
        print(json.dumps(result, ensure_ascii=False), flush=True)


def main():
    # 若 argv 中有 --persistent 标志则使用长驻模式（§7 实测后确认是否需要）
    if "--persistent" in sys.argv:
        main_persistent()
    else:
        main_single()


if __name__ == "__main__":
    main()
