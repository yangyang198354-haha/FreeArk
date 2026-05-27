"""
One-shot WS probe to measure real delta-frame timing OpenClaw → client.

Runs ON THE PI (loopback to gateway). Mimics FreeArk adapter handshake,
sends a chat.send, captures per-delta timestamps, prints histogram.

Usage (on Pi):
    cd /home/yangyang/Freeark/FreeArk
    venv/bin/python scripts/analysis/probe_stream_timing.py \
        --token-file ~/.openclaw_gateway_token \
        --prompt "用一句话介绍你自己"
"""
import argparse
import asyncio
import json
import time
import uuid
import sys

import aiohttp


async def probe(token: str, prompt: str, url: str, timeout: int):
    connect_id = uuid.uuid4().hex
    chat_id = uuid.uuid4().hex
    idem = uuid.uuid4().hex
    session_key = uuid.uuid4().hex

    deltas = []  # (ts_rel, kind, char_count)
    t0 = None
    chat_started = False

    headers = {"Authorization": f"Bearer {token}"}
    client_timeout = aiohttp.ClientTimeout(total=timeout, sock_connect=10)

    async with aiohttp.ClientSession(timeout=client_timeout) as sess:
        async with sess.ws_connect(url, headers=headers, heartbeat=30) as ws:
            t_send = time.monotonic()
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                frame = json.loads(msg.data)
                ftype = frame.get("type")
                if ftype == "event":
                    ev = frame.get("event")
                    payload = frame.get("payload") or {}
                    if ev == "connect.challenge":
                        await ws.send_json({
                            "type": "req", "id": connect_id, "method": "connect",
                            "params": {
                                "minProtocol": 4, "maxProtocol": 4,
                                "client": {"id": "gateway-client", "version": "freeark-probe",
                                           "platform": "linux", "mode": "backend"},
                                "caps": [], "auth": {"token": token},
                                "role": "operator",
                                "scopes": ["operator.read", "operator.write", "operator.admin"],
                            },
                        })
                        continue
                    if ev == "chat" and chat_started:
                        state = payload.get("state")
                        now = time.monotonic()
                        if t0 is None:
                            t0 = now
                        rel = (now - t0) * 1000
                        if state == "delta":
                            r = payload.get("reasoningDelta") or ""
                            if not r and payload.get("kind") == "reasoning":
                                r = payload.get("deltaText") or ""
                                c = ""
                            else:
                                c = payload.get("deltaText") or ""
                            if r:
                                deltas.append((rel, "reasoning", len(r)))
                            if c:
                                deltas.append((rel, "content", len(c)))
                        elif state in ("final", "aborted", "error"):
                            print(f"[stream end] state={state} at t+{rel:.0f}ms")
                            break
                elif ftype == "res":
                    rid = frame.get("id")
                    if rid == connect_id:
                        if not frame.get("ok"):
                            print(f"connect rejected: {frame}")
                            return
                        await ws.send_json({
                            "type": "req", "id": chat_id, "method": "chat.send",
                            "params": {
                                "sessionKey": session_key,
                                "message": prompt,
                                "idempotencyKey": idem,
                            },
                        })
                        t_send = time.monotonic()
                    elif rid == chat_id:
                        if not frame.get("ok"):
                            print(f"chat.send rejected: {frame}")
                            return
                        chat_started = True
                        ack_ms = (time.monotonic() - t_send) * 1000
                        print(f"[chat.send ack] t+{ack_ms:.0f}ms runId={(frame.get('payload') or {}).get('runId')}")

    # ---- Analysis ----
    if not deltas:
        print("NO DELTAS RECEIVED")
        return
    print(f"\n=== Summary ===")
    print(f"total deltas: {len(deltas)}")
    reasoning = [d for d in deltas if d[1] == "reasoning"]
    content = [d for d in deltas if d[1] == "content"]
    print(f"  reasoning: {len(reasoning)} frames, {sum(d[2] for d in reasoning)} chars")
    print(f"  content:   {len(content)} frames, {sum(d[2] for d in content)} chars")
    print(f"first delta at: t+{deltas[0][0]:.0f}ms")
    print(f"last delta at:  t+{deltas[-1][0]:.0f}ms")
    span = deltas[-1][0] - deltas[0][0]
    print(f"streaming span: {span:.0f}ms")
    if len(deltas) >= 2:
        gaps = [deltas[i+1][0] - deltas[i][0] for i in range(len(deltas) - 1)]
        gaps_sorted = sorted(gaps)
        median = gaps_sorted[len(gaps_sorted) // 2]
        p90 = gaps_sorted[int(len(gaps_sorted) * 0.9)]
        p99 = gaps_sorted[int(len(gaps_sorted) * 0.99)]
        print(f"inter-frame gap (ms): min={min(gaps):.0f} p50={median:.0f} p90={p90:.0f} p99={p99:.0f} max={max(gaps):.0f}")
        # Burstiness: how many frames came within 50ms of previous?
        bursty = sum(1 for g in gaps if g < 50)
        print(f"frames arriving <50ms after previous: {bursty}/{len(gaps)} ({100*bursty/len(gaps):.0f}%)")

    print(f"\n=== Verdict ===")
    if not deltas:
        print("FAIL: no streaming at all")
    elif span < 200 and len(deltas) > 20:
        print(f"BUFFERED: {len(deltas)} frames squeezed into {span:.0f}ms — NOT true streaming")
    elif span > 1000 and len(deltas) > 10:
        print(f"TRUE STREAMING: {len(deltas)} frames over {span:.0f}ms (avg {span/len(deltas):.0f}ms/frame)")
    else:
        print(f"INCONCLUSIVE: {len(deltas)} frames over {span:.0f}ms (short reply?)")

    # First-token latency
    print(f"\nTime-to-first-delta (TTFT including ack): {deltas[0][0]:.0f}ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--prompt", default="用一句话介绍你自己")
    ap.add_argument("--url", default="ws://127.0.0.1:18789/")
    ap.add_argument("--timeout", type=int, default=60)
    args = ap.parse_args()
    with open(args.token_file) as f:
        token = f.read().strip()
    if not token:
        print("empty token", file=sys.stderr)
        sys.exit(1)
    asyncio.run(probe(token, args.prompt, args.url, args.timeout))


if __name__ == "__main__":
    main()
