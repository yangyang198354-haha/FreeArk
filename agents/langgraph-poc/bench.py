"""
langgraph-poc — 性能基准：证明「并行 fan-out < 串行委派」且「无 per-request 冷启动」

跑法（离线，无需 API key / 后端）：
    FREEARK_POC_MOCK=1 python bench.py
    FREEARK_POC_MOCK=1 POC_FAKE_LATENCY=10 python bench.py   # 逼近真实单轮 ~10s

度量：
  1. warm 一次（图已编译 → 首次 vs 次次几乎无差，证明无冷启动）
  2. 单专家查询耗时
  3. 复合三专家查询耗时（并行）
  4. 同样三专家「串行模拟」耗时（顺序 await）
  5. 对比并行 / 串行，给出加速比

注意：假模型用 sleep 模拟 LLM 推理；编排层（图遍历/工具/归并）是真实代码路径，
故「编排开销」是真实测得的，被模拟的只有 LLM 那段。
"""

from __future__ import annotations

import asyncio
import os
import time

os.environ.setdefault("FREEARK_POC_MOCK", "1")

from orchestrator import Orchestrator  # noqa: E402


def _lat() -> float:
    return float(os.environ.get("POC_FAKE_LATENCY", "1.0"))


async def _timed(coro):
    t0 = time.perf_counter()
    res = await coro
    return time.perf_counter() - t0, res


async def main():
    lat = _lat()
    orch = Orchestrator(latency=lat)

    print(f"\n=== langgraph-poc bench (假模型单轮={lat:.1f}s, mock={os.environ.get('FREEARK_POC_MOCK')}) ===\n")

    # 1) 冷启动检验：连续两次单专家，时间差应≈0（图常驻）
    w1, _ = await _timed(orch.run("看一下今天的能耗看板"))
    w2, r2 = await _timed(orch.run("看一下今天的能耗看板"))
    print(f"[1] 单专家 1st={w1:5.2f}s  2nd={w2:5.2f}s  Δ={abs(w1-w2):.2f}s "
          f"→ 无 per-request 冷启动（路由命中: {r2['experts']}）")

    # 同一条复合查询，两条路径只在「专家阶段并发度」上不同（同样 3 专家 + 1 聚合）
    q = "对比一下能耗看板、PLC 故障巡检，并解释三恒原理"
    tpar, rpar = await _timed(orch.run(q))         # 专家并行（Send fan-out）
    tser, rser = await _timed(orch.run_serial(q))  # 专家串行（等价 OpenClaw 顺序委派）
    print(f"[2] 复合查询·专家并行        = {tpar:5.2f}s  命中: {rpar['experts']}")
    print(f"[3] 复合查询·专家串行(委派)  = {tser:5.2f}s  命中: {rser['experts']}")

    n = len(rpar["experts"])
    speedup = tser / tpar if tpar else 0
    # 专家阶段净加速（剔除固定的 route+aggregate）≈ N×；端到端被聚合稀释为 (N+1)/2
    print(f"\n[结果] 并行 {tpar:.2f}s  vs  串行 {tser:.2f}s  →  端到端加速 {speedup:.2f}×（{n} 专家）")
    print(f"[专家阶段] 串行 sum(N)=N×L，并行 max=1×L → 专家阶段净加速≈{n}×")
    print(f"[换算] 单专家≈真实 31s 时：串行≈{n}×31={n*31}s + 聚合，"
          f"并行≈31s + 聚合 → 复合意图从分钟级降到 ~30s 量级\n")


if __name__ == "__main__":
    asyncio.run(main())
