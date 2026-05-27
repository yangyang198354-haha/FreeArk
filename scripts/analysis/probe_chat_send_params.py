"""Probe which reasoning-related param names chat.send accepts."""
import asyncio
import json
import uuid
import sys
import aiohttp


async def main():
    token = open("/home/yangyang/.openclaw_gateway_token").read().strip()
    candidates = sys.argv[1].split(",") if len(sys.argv) > 1 else ["reasoning"]

    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(
            "ws://127.0.0.1:18789/",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            cid = uuid.uuid4().hex
            connected = False
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                f = json.loads(msg.data)
                if f.get("type") == "event" and f.get("event") == "connect.challenge":
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
                elif f.get("type") == "res" and f.get("id") == cid:
                    connected = True
                    break
            if not connected:
                print("connect failed"); return

            for name in candidates:
                rid = uuid.uuid4().hex
                base = {
                    "sessionKey": uuid.uuid4().hex,
                    "message": "hi",
                    "idempotencyKey": uuid.uuid4().hex,
                }
                if name == "thinking":
                    base["thinking"] = "high"
                elif name == "reasoning":
                    base["reasoning"] = "high"
                elif name == "thinkingEffort":
                    base["thinkingEffort"] = "high"
                elif name == "reasoningMode":
                    base["reasoningMode"] = "stream"
                elif name == "model.reasoningEffort":
                    base["model"] = {"reasoningEffort": "high"}
                elif name == "options.reasoning_effort":
                    base["options"] = {"reasoning_effort": "high"}
                elif name == "options.thinking":
                    base["options"] = {"thinking": "high"}
                await ws.send_json({"type": "req", "id": rid, "method": "chat.send", "params": base})
                print(f"trying {name}: sent")
                # Wait for the ack response
                async for m2 in ws:
                    if m2.type != aiohttp.WSMsgType.TEXT:
                        continue
                    f2 = json.loads(m2.data)
                    if f2.get("type") == "res" and f2.get("id") == rid:
                        if f2.get("ok"):
                            run_id = (f2.get("payload") or {}).get("runId")
                            print(f"  -> ACCEPTED runId={run_id}")
                            # Drain frames until final/aborted/error so we can move on
                            async for m3 in ws:
                                if m3.type != aiohttp.WSMsgType.TEXT:
                                    continue
                                f3 = json.loads(m3.data)
                                if f3.get("type") == "event" and f3.get("event") == "chat":
                                    st = (f3.get("payload") or {}).get("state")
                                    if st in ("final", "aborted", "error"):
                                        break
                        else:
                            err = f2.get("error", {})
                            print(f"  -> REJECTED: {err.get('message')}")
                        break


if __name__ == "__main__":
    asyncio.run(main())
