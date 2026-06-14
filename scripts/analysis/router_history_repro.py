"""
router_history_repro —— 复现 F-03 误路由：会话记忆注入污染路由分类。

orchestrator._route 在「历史前缀 + [__freeark_user__:] 标签 + 当前问题」整块上做分类，
历史里的能耗/PLC 内容可能把当前的知识性问题带偏到 energy/inspection。

对比：裸当前问题 vs 生产真实 augmented（含历史前缀）。只读 LLM 调用，无副作用。

用法（Pi 上）：DJANGO_SETTINGS_MODULE=freearkweb.settings python /tmp/router_history_repro.py
"""
import asyncio

import django
django.setup()

from api.chat_memory import build_inject_prefix             # noqa: E402
from api.langgraph_chat.orchestrator import Orchestrator     # noqa: E402
from api.langgraph_chat.router import classify_experts       # noqa: E402

# 模拟 smoke 里 F-03 之前的历史（F-01 能耗 + F-02 PLC 故障）
HISTORY = [
    {"role": "user", "content": "现在系统总能耗和设备在线率是多少？"},
    {"role": "assistant", "content": "当前今日总能耗约 8647 kWh；设备在线率与 PLC 状态见巡检。"},
    {"role": "user", "content": "现在有多少台PLC在线？有哪些设备存在故障？"},
    {"role": "assistant", "content": "共 48 个专有部分存在故障，PLC 部分在线部分离线。"},
]

CURRENT = "三恒系统恒温恒湿恒氧的工作原理是什么？请简述。"


async def main():
    orch = Orchestrator()
    prefix = build_inject_prefix(HISTORY)
    augmented = f"{prefix}[__freeark_user__:openclaw-agent] {CURRENT}"

    bare = await classify_experts(orch.router_llm, CURRENT)
    poll = await classify_experts(orch.router_llm, augmented)

    print("=== F-03 路由：裸问题 vs 生产 augmented（含历史）===")
    print(f"[裸问题]        -> {bare}")
    print(f"[含历史前缀]     -> {poll}")
    print(f"\n期望都是 ['sanheng-knowledge']")
    print(f"裸问题正确={bare == ['sanheng-knowledge']}  "
          f"含历史正确={poll == ['sanheng-knowledge']}")
    if bare == ['sanheng-knowledge'] and poll != ['sanheng-knowledge']:
        print(">>> 复现成功：历史注入污染了路由分类（根因坐实）")
    elif poll == ['sanheng-knowledge']:
        print(">>> 未复现（含历史也正确）——F-03 误路由可能是 temp0 残余抖动/其他")

    # 顺带打印 augmented 全文供核对
    print("\n--- augmented 全文 ---")
    print(augmented)


if __name__ == "__main__":
    asyncio.run(main())
