"""Send with thinking=high and dump every delta payload's full keys + values."""
import argparse
import asyncio
import json
import uuid
import aiohttp


async def main(token, prompt, thinking, timeout):
    cid = uuid.uuid4().hex
    rid = uuid.uuid4().hex

    started = False
    delta_count = 0
    field_keys_seen = set()
    first_payloads = []
    state_keys_seen = set()
    saw_reasoning_text = False

    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
        async with s.ws_connect(
            "ws://127.0.0.1:18789/",
            headers={"Authorization": f"Bearer {token}"},
            heartbeat=30,
        ) as ws:
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
                                "client": {"id": "gateway-client", "version": "x",
                                           "platform": "linux", "mode": "backend"},
                                "caps": [], "auth": {"token": token},
                                "role": "operator",
                                "scopes": ["operator.read", "operator.write", "operator.admin"],
                            },
                        })
                    elif ev == "chat" and started:
                        st = pl.get("state")
                        state_keys_seen.add(st)
                        if st == "delta":
                            delta_count += 1
                            for k in pl.keys():
                                field_keys_seen.add(k)
                            # heuristic: anything that looks like reasoning
                            for k, v in pl.items():
                                if "reason" in k.lower() or "think" in k.lower() or "trace" in k.lower():
                                    saw_reasoning_text = True
                            if len(first_payloads) < 8:
                                trimmed = {}
                                for k, v in pl.items():
                                    if isinstance(v, str) and len(v) > 100:
                                        trimmed[k] = v[:100] + f"...(+{len(v) - 100})"
                                    elif isinstance(v, dict):
                                        trimmed[k] = {kk: (str(vv)[:80] if isinstance(vv, (str, int, float, bool)) else type(vv).__name__) for kk, vv in v.items()}
                                    else:
                                        trimmed[k] = v
                                first_payloads.append(trimmed)
                        elif st in ("final", "aborted", "error"):
                            # Dump final payload too
                            print(f"\n[end] state={st}")
                            print(f"final payload keys: {sorted(pl.keys())}")
                            # Show full message content (truncated)
                            m = pl.get("message", {})
                            if isinstance(m, dict):
                                for k, v in m.items():
                                    if isinstance(v, str) and len(v) > 200:
                                        print(f"  final.message.{k}: {v[:200]}...")
                                    elif isinstance(v, list):
                                        print(f"  final.message.{k}: [{len(v)} items] first item keys: {list(v[0].keys()) if v else '(empty)'}")
                                    else:
                                        print(f"  final.message.{k}: {v!r}")
                            break
                elif ftype == "res":
                    fid = f.get("id")
                    if fid == cid:
                        if not f.get("ok"):
                            print("connect rejected"); return
                        params = {
                            "sessionKey": uuid.uuid4().hex,
                            "message": prompt,
                            "idempotencyKey": uuid.uuid4().hex,
                        }
                        if thinking:
                            params["thinking"] = thinking
                        await ws.send_json({"type": "req", "id": rid, "method": "chat.send", "params": params})
                    elif fid == rid:
                        if not f.get("ok"):
                            print("chat.send rejected:", f); return
                        started = True
                        print(f"[chat.send ack] thinking={thinking!r}")

    print(f"\n=== summary ===")
    print(f"delta frames: {delta_count}")
    print(f"state values seen: {sorted(state_keys_seen)}")
    print(f"field keys ever in delta payloads: {sorted(field_keys_seen)}")
    print(f"any 'reason/think/trace' field seen: {saw_reasoning_text}")
    print(f"\nfirst {min(8, len(first_payloads))} delta payloads:")
    for i, p in enumerate(first_payloads):
        print(f"  [{i}] {json.dumps(p, ensure_ascii=False)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--token-file", default="/home/yangyang/.openclaw_gateway_token")
    ap.add_argument("--prompt", default="9.11 和 9.8 哪个大？详细推理")
    ap.add_argument("--thinking", default="high")
    ap.add_argument("--timeout", type=int, default=120)
    args = ap.parse_args()
    token = open(args.token_file).read().strip()
    asyncio.run(main(token, args.prompt, args.thinking, args.timeout))
