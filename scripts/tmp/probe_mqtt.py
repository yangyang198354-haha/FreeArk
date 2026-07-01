"""临时探针：订阅 60s 抓真实 MQTT 报文，用于诊断 fault_consumer 为何零捕获。"""
import json, sys, time
import paho.mqtt.client as mqtt

CFG_PATH = "/home/yangyang/Freeark/FreeArk/FreeArkWeb/backend/heartbeat_broker_config.json"
with open(CFG_PATH) as f:
    cfg = json.load(f)

print("[CFG] protocol=%s host=%s port=%s" % (cfg.get("protocol"), cfg.get("host"), cfg.get("port")), flush=True)
print("[CFG] topic=%s" % cfg.get("topic"), flush=True)
print("[CFG] fault_consumer_topic=%s" % cfg.get("fault_consumer_topic", "<MISSING-in-config>"), flush=True)

count = 0

def on_connect(c, u, f, rc):
    print("[CONN] rc=%s" % rc, flush=True)
    if rc == 0:
        sub_topic = cfg.get("topic", "/screen/upload/screen/to/cloud/#")
        c.subscribe(sub_topic)
        print("[SUB] %s" % sub_topic, flush=True)

def on_message(c, u, msg):
    global count
    count += 1
    if count > 5:
        return
    try:
        payload = msg.payload.decode("utf-8", errors="replace")
    except Exception:
        payload = repr(msg.payload[:300])
    print("", flush=True)
    print("=== MSG #%d topic=%s ===" % (count, msg.topic), flush=True)
    print(payload[:1500], flush=True)
    try:
        j = json.loads(payload)
        header = j.get("header") or {}
        data = j.get("data") or {}
        items = data.get("items") or []
        print("", flush=True)
        print("[HEADER.NAME] = %r" % header.get("name"), flush=True)
        print("[DATA.deviceSn] = %r" % data.get("deviceSn"), flush=True)
        print("[DATA.items count] = %d" % len(items), flush=True)
        for it in items[:10]:
            if isinstance(it, dict):
                pn = it.get("paramName")
                v = it.get("value")
                print("   - paramName=%r value=%r" % (pn, v), flush=True)
    except Exception as e:
        print("[PARSE-FAIL] %s" % e, flush=True)

protocol = cfg.get("protocol", "wss")
if protocol == "wss":
    client = mqtt.Client(client_id="probe-mqtt-debug", transport="websockets")
    client.tls_set()
    client.ws_set_options(path=cfg.get("path", "/mqtt"))
else:
    client = mqtt.Client(client_id="probe-mqtt-debug", transport="tcp")

client.username_pw_set(cfg.get("username"), cfg.get("password"))
client.on_connect = on_connect
client.on_message = on_message
client.connect(cfg.get("host"), int(cfg.get("port")), int(cfg.get("keepalive", 60)))
client.loop_start()
time.sleep(60)
client.loop_stop()
print("", flush=True)
print("[DONE] received %d messages in 60s" % count, flush=True)
