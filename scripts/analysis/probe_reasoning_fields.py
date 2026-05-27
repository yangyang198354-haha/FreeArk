"""
Reasoning-field probe: dump every event:chat delta payload's full structure,
optionally with reasoning_effort = low/medium/high.

Two questions answered:
  Q1. Does DeepSeek v4-flash return reasoning at all (with/without reasoning_effort)?
  Q2. If yes, under what field name? Confirm/refute openclaw_adapter._REASONING_FIELD.

Usage (on Pi):
    venv/bin/python /tmp/probe_reasoning_fields.py \
        --token-file ~/.openclaw_gateway_token \
        --reasoning-effort low \
        --prompt "9.11 和 9.8 哪个大？给出推理过程"
"""
import argparse
import asyncio
import json
import time
import uuid
import sys

import aiohttp


async def probe(token, prompt, url, reasoning_effort, timeout):
    cid = uuid.uuid4().hex
    rid = uuid.uuid4().hex
    idem = uuid.uuid4().hex
    sk = uuid.uuid4().hex

    started = False
    delta_count = 0
    field_keys_seen = set()
    sample_payloads = []

    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        async with s.ws_connect(url, headers=headers, heartbeat=30) as ws:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                f = json.loads(msg.data)
                ftype = f.get("type")
                if ftype == "event":
                    ev = f.get("event")
                    pl = f.get("payload") or {}
                    if ev == "connect.challenge":
                        await ws.send_json({
                            "type": "req", "id": cid, "method": "connect",
                            "params": {
                                "minProtocol": 4, "maxProtocol": 4,
                                "client": {"id": "gateway-client", "version": "freeark-probe",
                                           "platform": "linux", "mode": "backend"},
                                "caps": [], "auth": {"token": token},
                                "role": "operator",
                                "scopes": ["operator.read", "operator.write", "operator.admin"],
                            },
                        })
                    elif ev == "chat" and started:
                        st = pl.get("state")
                        if st == "delta":
                            delta_count += 1
                            for k in pl.keys():
                                field_keys_seen.add(k)
                            if len(sample_payloads) < 5:
                                # Truncate long string values
                                trimmed = {k: (v[:80] + "...(+%d)" % (len(v)-80) if isinstance(v, str) and len(v) > 80 else v) for k, v in pl.items()}
                                sample_payloads.append(trimmed)
                        elif st in ("final", "aborted", "error"):
                            print(f"[end] state={st}")
                            break
                elif ftype == "res":
                    fid = f.get("id")
                    if fid == cid:
                        if not f.get("ok"):
                            print("connect rejected:", f); return
                        params = {
                            "sessionKey": sk, "message": prompt,
                            "idempotencyKey": idem,
                        }
                        if reasoning_effort:
                            params["reasoningEffort"] = reasoning_effort
                        await ws.send_json({
                            "type": "req", "id": rid, "method": "chat.send",
                            "params": params,
                        })
                    elif fid == rid:
                        if not f.get("ok"):
                            print("chat.send rejected:", f); return
                        started = True
                        print(f"[chat.send ack] reasoning_effort={reasoning_effort!r}")

    print(f"\ntotal delta frames: {delta_count}")
    print(f"field keys ever seen in delta payloads: {sorted(field_keys_seen)}")
    print(f"\nfirst 5 sample payloads:")
    for i, p in enumerate(sample_payloads):
        print(f"  [{i}] {json.dumps(p, ensure_ascii=False)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", required=True)
    ap.add_argument("--prompt", default="9.11 和 9.8 哪个大？给出推理过程")
    ap.add_argument("--reasoning-effort", default="", choices=["", "low", "medium", "high"])
    ap.add_argument("--url", default="ws://127.0.0.1:18789/")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    with open(args.token_file) as f:
        token = f.read().strip()
    asyncio.run(probe(token, args.prompt, args.url,
                      args.reasoning_effort or None, args.timeout))


if __name__ == "__main__":
    main()
