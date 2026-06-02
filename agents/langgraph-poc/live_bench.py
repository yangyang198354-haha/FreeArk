"""
langgraph-poc — 真机端到端墙钟基准（真实 deepseek-v4-flash）

跑法（Pi 上，env 已注入 DEEPSEEK_API_KEY / FREEARK_AGENT_TOKEN 等）：
    FREEARK_POC_LIVE=1 .venv/bin/python live_bench.py

对打目标：OpenClaw 单专家委派 ~31s、串行三专家 ~93s（detailed_design §1.2.3 实测）。
本基准用同一模型、同一工具，测 LangGraph 进程内编排的真实墙钟：
  - 单专家（route→1 expert→aggregate）
  - 复合三专家·并行（Send fan-out）
  - 复合三专家·串行（run_serial，等价 OpenClaw 顺序委派）
"""

import asyncio
import os
import time

from orchestrator import Orchestrator


async def _timed(coro):
    t0 = time.perf_counter()
    r = await coro
    return time.perf_counter() - t0, r


async def main():
    orch = Orchestrator()  # live：FREEARK_POC_LIVE=1 → ChatOpenAI(deepseek)
    model = os.environ.get("POC_MODEL", "deepseek-v4-flash")
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    print(f"=== live bench  model={model}  base={base} ===")

    tw, _ = await _timed(orch.run("你好"))  # warm：建连/首 token，不计正式
    print(f"[warm]        {tw:6.2f}s")

    t1, r1 = await _timed(orch.run("看一下今天的能耗看板，给一句简短判断"))
    print(f"[单专家]      {t1:6.2f}s  experts={r1['experts']}")
    print(f"              answer={r1['answer'][:120]!r}")

    q = "对比一下能耗看板与 PLC 故障巡检情况，并解释三恒系统的基本原理"
    tp, rp = await _timed(orch.run(q))         # 并行 fan-out
    print(f"[并行三专家]  {tp:6.2f}s  experts={rp['experts']}")

    ts, rs = await _timed(orch.run_serial(q))  # 串行（等价 OpenClaw 顺序委派）
    print(f"[串行三专家]  {ts:6.2f}s  experts={rs['experts']}")

    spd = ts / tp if tp else 0
    print(f"\n[对比]  并行 {tp:.2f}s  vs  串行 {ts:.2f}s  →  加速 {spd:.2f}×")
    print(f"[对打]  OpenClaw：单专家委派 ~31s / 串行三专家 ~93s")
    print(f"[净收益] 消除 CLI 冷启动+gateway 跳转+子进程工具；复合意图并行")


if __name__ == "__main__":
    asyncio.run(main())
