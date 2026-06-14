"""
langgraph-poc — 跨 agent 委托（sub-delegation）离线自检

验证 inspection-expert 在 ReAct 过程中可委托同侪并拿回结果续推理（对应
inspection-expert/SYSTEM_PROMPT 的 delegations 契约）：
  - delegate_knowledge → 路由到 sanheng-knowledge（原理/概念分析，只读）
  - delegate_read      → 路由到 energy-expert（只读取数）
  - delegate_write     → 经确认门：批准 → 由 energy-expert 执行；拒绝 → USER_CANCELLED

并验证：①深度限 1（目标专家不再带委托工具，不递归）；②非委托专家不暴露委托工具；
③确认门默认拒绝（无确认即不执行）。

全程 fake LLM + mock 工具，无 key / 无后端。用法：
    FREEARK_POC_MOCK=1 python test_delegation.py
退出码 = 失败用例数（0 = 全绿）。
"""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("FREEARK_POC_MOCK", "1")

from orchestrator import Orchestrator  # noqa: E402

# 巡检专家脚本化委托链：先查故障，再依次委托 知识/取数/写
CHAIN = ("巡检 3-1-7-702 "
         "TOOLCALL:get_fault_summary "
         "TOOLCALL:delegate_knowledge "
         "TOOLCALL:delegate_read "
         "TOOLCALL:delegate_write")


def _intents(delegations):
    return [(d["target_agent"], d["intent"], d["status"]) for d in delegations]


async def main() -> int:
    fails = 0

    # 用例 1：写操作获批准 → 委托全链成功，写=EXECUTED
    orch_ok = Orchestrator(latency=0.0, confirm_write=lambda d: True)
    r = await orch_ok._run_expert("inspection-expert", CHAIN, allow_delegation=True)
    got = _intents(r["expert_results"][0]["delegations"])
    want = [
        ("sanheng-knowledge", "knowledge_query", "OK"),
        ("energy-expert", "read_query", "OK"),
        ("energy-expert", "write_command", "EXECUTED"),
    ]
    ok = got == want
    print(f"[{'OK ' if ok else 'ERR'}] approve   delegations={got}")
    fails += 0 if ok else 1

    # 用例 2：默认确认门（拒绝）→ 写=USER_CANCELLED，知识/取数仍成功
    orch_deny = Orchestrator(latency=0.0)  # 默认 confirm_write 拒绝
    r2 = await orch_deny._run_expert("inspection-expert", CHAIN, allow_delegation=True)
    got2 = _intents(r2["expert_results"][0]["delegations"])
    want2 = [
        ("sanheng-knowledge", "knowledge_query", "OK"),
        ("energy-expert", "read_query", "OK"),
        ("energy-expert", "write_command", "USER_CANCELLED"),
    ]
    ok2 = got2 == want2
    print(f"[{'OK ' if ok2 else 'ERR'}] deny      delegations={got2}")
    fails += 0 if ok2 else 1

    # 用例 3：非委托专家不暴露委托工具（energy 自身不 sub-delegate，脚本里的
    # delegate_write 因未绑定被过滤 → 无委托发生）
    r3 = await orch_deny._run_expert(
        "energy-expert", "TOOLCALL:delegate_write", allow_delegation=False)
    d3 = r3["expert_results"][0]["delegations"]
    ok3 = d3 == []
    print(f"[{'OK ' if ok3 else 'ERR'}] no-deleg  energy delegations={d3}")
    fails += 0 if ok3 else 1

    # 用例 4：确认回调抛异常 → 安全缺省视为未确认（写不执行）
    orch_err = Orchestrator(
        latency=0.0, confirm_write=lambda d: (_ for _ in ()).throw(RuntimeError("x")))
    r4 = await orch_err._run_expert(
        "inspection-expert", "TOOLCALL:delegate_write", allow_delegation=True)
    st4 = r4["expert_results"][0]["delegations"][0]["status"]
    ok4 = st4 == "USER_CANCELLED"
    print(f"[{'OK ' if ok4 else 'ERR'}] confirm-exc write status={st4}")
    fails += 0 if ok4 else 1

    print(f"=== delegation routing: {'ALL OK' if not fails else str(fails) + ' FAIL'} ===")
    return fails


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
