"""
阶段 A 真机离线自检（Pi / aarch64）：fake LLM + mock 工具，验证 LangGraph 编排图
（StateGraph / Send 并行 fan-out / operator.add reducer / astream）在 aarch64 + Py3.13 跑通。

不连真 DeepSeek、不连真后端、不碰生产 venv/repo（在 /tmp 一次性 venv 里跑）。
用法：python pi_validate.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["FREEARK_POC_MOCK"] = "1"  # 工具返回 canned 数据，离线验证编排接线

from django.conf import settings  # noqa: E402

if not settings.configured:
    settings.configure(LANGGRAPH_USE_FAKE_LLM=True)

from langgraph_chat.orchestrator import Orchestrator  # noqa: E402


async def main() -> int:
    orch = Orchestrator(latency=0.0)
    fails = 0

    r1 = await orch.run("看一下今天的能耗看板")
    ok = r1["experts"] == ["energy-expert"] and bool(r1["answer"])
    print(f"[{'OK ' if ok else 'ERR'}] single    experts={r1['experts']} answer_len={len(r1['answer'])}")
    fails += 0 if ok else 1

    q = "对比能耗看板与PLC故障巡检并解释三恒原理"
    rp = await orch.run(q)
    rs = await orch.run_serial(q)
    triple = {"energy-expert", "inspection-expert", "sanheng-knowledge"}
    ok = set(rp["experts"]) == set(rs["experts"]) == triple
    print(f"[{'OK ' if ok else 'ERR'}] parallel  experts={sorted(rp['experts'])}")
    print(f"[{'OK ' if ok else 'ERR'}] serial    experts={sorted(rs['experts'])}")
    fails += 0 if ok else 1

    print(f"=== orchestrator graph on aarch64: {'ALL OK' if not fails else str(fails) + ' FAIL'} ===")
    return fails


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
