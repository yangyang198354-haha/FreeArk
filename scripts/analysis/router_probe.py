"""
router_probe —— 用生产同款 router_llm（temp 0）实测意图分类，定位 F-03 误路由。

只读 LLM 调用（真 DeepSeek），无 DB 写、无设备副作用。打印每条 query 的分类结果。

用法（Pi 上，PYTHONPATH 指向 backend/freearkweb）：
  DJANGO_SETTINGS_MODULE=freearkweb.settings python /tmp/router_probe.py
"""
import asyncio

import django
django.setup()

from api.langgraph_chat.orchestrator import Orchestrator   # noqa: E402
from api.langgraph_chat.router import classify_experts      # noqa: E402

# (query, 期望专家)
CASES = [
    ("三恒系统恒温恒湿恒氧的工作原理是什么？请简述。", "sanheng-knowledge"),
    ("三恒系统的恒氧是指什么？", "sanheng-knowledge"),
    ("为什么三恒系统要控制湿度？", "sanheng-knowledge"),
    ("恒温恒湿的原理是什么", "sanheng-knowledge"),
    ("三恒里的恒温是怎么实现的", "sanheng-knowledge"),
    ("当前系统总能耗和在线率是多少", "energy-expert"),
    ("3-1-7-702 这台设备的实时温度湿度是多少", "energy-expert"),   # 真·传感器数据查询
    ("现在有哪些设备故障", "inspection-expert"),
    ("对比一下能耗和PLC故障情况", "energy-expert+inspection-expert"),
]


async def main():
    orch = Orchestrator()
    print("=== router 分类实测（router_llm temp 0）===")
    hits = 0
    for q, expect in CASES:
        try:
            got = await classify_experts(orch.router_llm, q)
        except Exception as e:  # noqa: BLE001
            got = [f"EXC:{type(e).__name__}:{e}"]
        got_set = set(got)
        exp_set = set(expect.split("+"))
        ok = got_set == exp_set
        hits += 1 if ok else 0
        print(f"[{'OK ' if ok else 'ERR'}] {q[:30]:32s} 期望={expect:35s} 实得={got}")
    print(f"=== {hits}/{len(CASES)} 命中 ===")


if __name__ == "__main__":
    asyncio.run(main())
