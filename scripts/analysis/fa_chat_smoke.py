"""
fa_chat_smoke —— 生产 langgraph 聊天链路一次性回归（打 FreeArk ChatConsumer，非 OpenClaw gateway）

跑在 Pi 上，loopback 连 ws://127.0.0.1:8000/ws/chat/?token=<DRF token>。
token 从 freeark.env 读取 FREEARK_AGENT_TOKEN，**绝不打印**（仅打印长度校验）。

协议（见 api/consumers.py）：
  client→ {"type":"chat_message","message":...}
          {"type":"confirm_response","approved":bool}
  server→ reasoning_token / reasoning_end / stream_token / stream_end
          confirm_required{actions:[...]} / connected / error{code}

退出码 = 失败用例数（0=全绿）。写门只测「触发+拒绝」，对真实设备零副作用。

用法（Pi 上）：
  cd /home/yangyang/Freeark/FreeArk
  venv/bin/python scripts/analysis/fa_chat_smoke.py --token-file ~/.openclaw/freeark.env
"""
import argparse
import asyncio
import json
import re
import sys
import time

import aiohttp

URL = "ws://127.0.0.1:8000/ws/chat/?token={token}"
ORIGIN = "http://127.0.0.1:8000"   # 必在 ALLOWED_HOSTS（含 127.0.0.1），否则 OriginValidator 403


def _read_token(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    m = re.search(r"^\s*FREEARK_AGENT_TOKEN\s*=\s*(.+?)\s*$", raw, re.MULTILINE)
    tok = (m.group(1) if m else raw).strip().strip('"').strip("'")
    return tok


class Turn:
    """一次 chat_message 往返的收集结果。"""
    def __init__(self):
        self.reasoning = ""
        self.content = ""
        self.confirm_actions = None
        self.error = None
        self.ended = False
        self.elapsed = 0.0


async def _send_and_collect(ws, message: str, timeout: float) -> Turn:
    t = Turn()
    t0 = time.monotonic()
    await ws.send_json({"type": "chat_message", "message": message})
    while True:
        remaining = timeout - (time.monotonic() - t0)
        if remaining <= 0:
            t.error = "CLIENT_TIMEOUT"
            break
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
        except asyncio.TimeoutError:
            t.error = "CLIENT_TIMEOUT"
            break
        if msg.type != aiohttp.WSMsgType.TEXT:
            if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.ERROR):
                t.error = t.error or "WS_CLOSED"
                break
            continue
        f = json.loads(msg.data)
        ft = f.get("type")
        if ft == "reasoning_token":
            t.reasoning += f.get("token", "")
        elif ft == "stream_token":
            t.content += f.get("token", "")
        elif ft == "reasoning_end":
            pass
        elif ft == "confirm_required":
            t.confirm_actions = f.get("actions", [])
            break  # 等调用方决定 approve/reject
        elif ft == "stream_end":
            t.ended = True
            break
        elif ft == "error":
            t.error = f.get("code", "ERROR")
            break
    t.elapsed = time.monotonic() - t0
    return t


async def _resume_confirm(ws, approved: bool, timeout: float) -> Turn:
    t = Turn()
    t0 = time.monotonic()
    await ws.send_json({"type": "confirm_response", "approved": approved})
    while True:
        remaining = timeout - (time.monotonic() - t0)
        if remaining <= 0:
            t.error = "CLIENT_TIMEOUT"
            break
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=remaining)
        except asyncio.TimeoutError:
            t.error = "CLIENT_TIMEOUT"
            break
        if msg.type != aiohttp.WSMsgType.TEXT:
            continue
        f = json.loads(msg.data)
        ft = f.get("type")
        if ft == "stream_token":
            t.content += f.get("token", "")
        elif ft == "confirm_required":
            t.confirm_actions = f.get("actions", [])
            break
        elif ft == "stream_end":
            t.ended = True
            break
        elif ft == "error":
            t.error = f.get("code", "ERROR")
            break
    t.elapsed = time.monotonic() - t0
    return t


async def _open(sess, token):
    ws = await sess.ws_connect(URL.format(token=token), headers={"Origin": ORIGIN},
                               heartbeat=30)
    # 首帧应为 connected
    msg = await asyncio.wait_for(ws.receive(), timeout=10)
    f = json.loads(msg.data)
    if f.get("type") != "connected":
        await ws.close()
        raise RuntimeError(f"未收到 connected，首帧={f}")
    return ws


def _verdict(ok: bool) -> str:
    return "OK " if ok else "ERR"


async def run(token: str, timeout: float):
    results = []  # (tc, ok, detail, elapsed)
    timeout_cplx = timeout * 1.8

    async with aiohttp.ClientSession() as sess:
        # ── 读 / 路由 / 复合 ───────────────────────────────
        read_cases = [
            ("F-01 能耗读", "现在系统总能耗和设备在线率是多少？", timeout),
            ("F-02 巡检读", "现在有多少台PLC在线？有哪些设备存在故障？", timeout),
            ("F-03 知识问答", "三恒系统恒温恒湿恒氧的工作原理是什么？请简述。", timeout),
            ("F-04 复合意图", "请对比一下当前的总能耗情况和PLC故障情况。", timeout_cplx),
        ]
        for tc, prompt, tmo in read_cases:
            try:
                ws = await _open(sess, token)
                t = await _send_and_collect(ws, prompt, tmo)
                await ws.close()
                ok = t.ended and not t.error and len(t.content.strip()) >= 10
                detail = (f"err={t.error}" if t.error
                          else f"{len(t.content)}字 / {t.content.strip()[:34]}…")
                results.append((tc, ok, detail, t.elapsed))
            except Exception as e:  # noqa: BLE001
                results.append((tc, False, f"{type(e).__name__}: {e}", 0.0))

        # ── 会话记忆（同连接两轮）─────────────────────────
        tc = "F-09 会话记忆"
        try:
            ws = await _open(sess, token)
            await _send_and_collect(ws, "请记住：我的设备代号是「蓝鲸-4417」。", timeout)
            t2 = await _send_and_collect(ws, "我刚才告诉你的设备代号是什么？", timeout)
            await ws.close()
            ok = t2.ended and not t2.error and "4417" in t2.content
            detail = (f"err={t2.error}" if t2.error
                      else ("记住了4417" if "4417" in t2.content else f"未命中: {t2.content[:34]}…"))
            results.append((tc, ok, detail, t2.elapsed))
        except Exception as e:  # noqa: BLE001
            results.append((tc, False, f"{type(e).__name__}: {e}", 0.0))

        # ── Tier-2 写门：触发 + 拒绝（对设备零副作用）──────
        tc = "F-07 写门·触发+拒绝"
        try:
            ws = await _open(sess, token)
            t = await _send_and_collect(ws, "请触发设备 3-1-7-702 的按需数据采集刷新。", timeout)
            if t.confirm_actions is not None:
                gate_fired = len(t.confirm_actions) >= 1
                tr = await _resume_confirm(ws, approved=False, timeout=timeout)
                await ws.close()
                cancelled = tr.ended and not tr.error and ("取消" in tr.content or "未执行" in tr.content)
                ok = gate_fired and cancelled
                preview = (t.confirm_actions[0].get("preview", "") if gate_fired else "")
                detail = (f"门触发(preview={preview[:24]}…) + 拒绝回执「{tr.content.strip()[:24]}…」"
                          if ok else
                          f"gate_fired={gate_fired} cancelled={cancelled} err={tr.error}")
                results.append((tc, ok, detail, t.elapsed + tr.elapsed))
            else:
                await ws.close()
                detail = (f"未触发确认门（err={t.error}；内容={t.content[:30]}…）"
                          "— 模型未调用写工具，inconclusive")
                results.append((tc, False, detail, t.elapsed))
        except Exception as e:  # noqa: BLE001
            results.append((tc, False, f"{type(e).__name__}: {e}", 0.0))

        # ── 并发（2 连接同时，验单 worker 无串扰）──────────
        tc = "F-10 并发(2路)"
        try:
            async def one(prompt):
                ws = await _open(sess, token)
                t = await _send_and_collect(ws, prompt, timeout)
                await ws.close()
                return t
            t_a, t_b = await asyncio.gather(
                one("当前设备在线率是多少？"),
                one("三恒系统的恒氧是指什么？"),
            )
            ok = (t_a.ended and not t_a.error and len(t_a.content) >= 10 and
                  t_b.ended and not t_b.error and len(t_b.content) >= 10)
            detail = (f"A={'ok' if t_a.ended and not t_a.error else t_a.error} "
                      f"B={'ok' if t_b.ended and not t_b.error else t_b.error}")
            results.append((tc, ok, detail, max(t_a.elapsed, t_b.elapsed)))
        except Exception as e:  # noqa: BLE001
            results.append((tc, False, f"{type(e).__name__}: {e}", 0.0))

    # ── 汇总 ─────────────────────────────────────────────
    print("\n=== FreeArk langgraph 生产聊天回归 ===")
    fails = 0
    for tc, ok, detail, elapsed in results:
        if not ok:
            fails += 1
        print(f"[{_verdict(ok)}] {tc:22s} {elapsed:6.1f}s  {detail}")
    print(f"=== {len(results) - fails}/{len(results)} passed ===")
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--timeout", type=float, default=75.0)
    args = ap.parse_args()
    token = _read_token(args.token_file)
    if not token:
        print("empty token", file=sys.stderr)
        sys.exit(2)
    print(f"token loaded (len={len(token)})")  # 仅长度，不回显 token
    fails = asyncio.run(run(token, args.timeout))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
