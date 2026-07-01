#!/usr/bin/env python3
"""
OQ-03 实测抓包：屏端参数读写 MQTT 报文采集 + 映射自动汇总
============================================================
目标：为「微信小程序通过 MQTT 配置参数」(v1.10.0) 抓取屏端真实报文，
      确定 param_name ↔ (deviceSn / attrTag / productCode) 映射、attrValue 表示
      （OQ-07 ×10 缩放）、以及写操作是否回执（OQ-05）。

接入点 : wss://www.ttqingjiao.site:8084  (WebSocket + TLS, path=/mqtt)
订阅   : 双向
  下行(云→屏) /screen/service/cloud/to/screen/{mac}   ← DeviceWrite / DeviceStatusRead（写命令，金矿）
  上行(屏→云) /screen/service/screen/to/cloud/{mac}   ← DeviceStatusUpdate（设备值主动推送，回显）/ 写回执
  (可选)      /screen/upload/screen/to/cloud/{mac}     ← 批量数据上报
  (可选)      /screen/event/status/change/{mac}        ← 操作事件
默认 mac = '#' 通配（抓所有屏）；用 --mac 钉到具体屏（如 2860fae9a34ab8a9）。

产物（脚本目录下，文件名带时间戳）：
  *.ndjson        每行一条原始报文（含 base64 原文，便于复盘）
  *_mapping.json  自动汇总：按 (screenMac, deviceSn) → {productCode, attrs:{attrTag: 最后值/样例}}
  控制台          实时预览 + 退出时打印 DeviceWrite / DeviceStatusUpdate 摘要

如何抓到一条真实写命令(DeviceWrite)：
  本脚本运行期间，用「原厂云/App 或屏端原生途径」对某参数做一次修改，
  写命令会经 cloud→screen 主题下发，被本脚本捕获。
  （注意：FreeArk web 版改参数走的是 S7/datacollection，不经此 broker，抓不到。）

依赖：pip install paho-mqtt>=1.6
仅用于临时排查，不进生产部署流水线。
"""

import argparse
import base64
import json
import os
import ssl
import sys
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("[ERROR] 缺少 paho-mqtt：pip install paho-mqtt")
    sys.exit(1)


# --------------------------------------------------------------------------- #
# 参数
# --------------------------------------------------------------------------- #
p = argparse.ArgumentParser(description="屏端参数读写 MQTT 抓包 + 映射汇总 (OQ-03)")
p.add_argument("--host", default="www.ttqingjiao.site", help="Broker 主机名")
p.add_argument("--port", default=8084, type=int, help="端口（默认 8084）")
p.add_argument("--transport", default="websockets", choices=["websockets", "tcp"])
p.add_argument("--path", default="/mqtt", help="WebSocket 路径（默认 /mqtt）")
p.add_argument("--tls", dest="tls", action="store_true", default=True,
               help="开启 TLS（wss，默认开）")
p.add_argument("--no-tls", dest="tls", action="store_false", help="关闭 TLS（ws）")
p.add_argument("--insecure", action="store_true",
               help="TLS 不校验证书（自签名时用）")
p.add_argument("--username", default="admin", help="MQTT 用户名（默认 admin）")
p.add_argument("--password", default="public", help="MQTT 密码（默认 public）")
p.add_argument("--mac", default="#",
               help="屏 MAC；默认 '#' 抓所有屏，可指定如 2860fae9a34ab8a9")
p.add_argument("--extra-topics", action="store_true",
               help="额外订阅 upload / event 主题")
p.add_argument("--duration", default=600, type=int, help="监听秒数（默认 600）")
p.add_argument("--qos", default=1, type=int)
p.add_argument("--output", default=None, help="NDJSON 输出路径（默认自动命名）")
args = p.parse_args()


def _topics():
    mac = args.mac
    t = [
        f"/screen/service/cloud/to/screen/{mac}",   # 下行：DeviceWrite（写命令）
        f"/screen/service/screen/to/cloud/{mac}",   # 上行：DeviceStatusUpdate / 回执
    ]
    if args.extra_topics:
        t += [
            f"/screen/upload/screen/to/cloud/{mac}",
            f"/screen/event/status/change/{mac}",
        ]
    return t


TOPICS = _topics()

_ts0 = time.monotonic()
_lock = threading.Lock()
_stop = threading.Event()
_fh = None
_counts = defaultdict(int)          # header.name -> count
_topic_counts = defaultdict(int)    # topic -> count
# (screenMac, deviceSn) -> {"productCode":x, "attrs":{attrTag: value}, "seen_in": set(name)}
_mapping = {}
_device_writes = []                 # 抓到的 DeviceWrite 原始摘要（金矿）


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _extract(j):
    """从报文里尽量取出 header.name, screenMac, deviceSn, productCode, items。
    兼容 payload.data 与顶层 data；items 兼容 attrTag/attrValue 与 paramName/value。"""
    header = (j.get("header") or {}) if isinstance(j, dict) else {}
    name = header.get("name")
    screen_mac = header.get("screenMac")
    payload = j.get("payload") if isinstance(j, dict) else None
    data = {}
    if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        data = payload["data"]
    elif isinstance(j, dict) and isinstance(j.get("data"), dict):
        data = j["data"]
    # 实测：deviceSn 同时出现在 header.sn 与 payload.data.deviceSn（字符串）
    device_sn = data.get("deviceSn", header.get("sn"))
    product_code = data.get("productCode")
    raw_items = data.get("items") if isinstance(data.get("items"), list) else []
    items = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        tag = it.get("attrTag", it.get("paramName"))
        val = it.get("attrValue", it.get("value"))
        items.append({"attrTag": tag, "attrValue": val})
    return name, screen_mac, device_sn, product_code, items


def on_connect(client, userdata, flags, rc, properties=None):
    rc_int = rc.value if hasattr(rc, "value") else (rc if isinstance(rc, int) else -1)
    if rc_int == 0:
        print(f"[{_now()}] [INFO] 连接成功，订阅 {len(TOPICS)} 个 topic：")
        for t in TOPICS:
            client.subscribe(t, qos=args.qos)
            print(f"           ↳ {t}")
    else:
        reasons = {1: "协议版本不接受", 2: "clientId 非法", 3: "服务器不可用",
                   4: "用户名/密码错误", 5: "未授权"}
        print(f"[{_now()}] [ERROR] 连接失败 rc={rc_int} {reasons.get(rc_int, '')}")


def on_disconnect(client, userdata, *a, **k):
    if not _stop.is_set():
        print(f"[{_now()}] [WARN] 断开，等待重连…")


def on_message(client, userdata, msg):
    ts = _now()
    raw = msg.payload or b""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = None

    rec = {
        "ts_iso": ts, "topic": msg.topic,
        "payload_text": text,
        "payload_raw_b64": base64.b64encode(raw).decode("ascii"),
        "qos": msg.qos, "retain": bool(msg.retain),
    }
    if _fh:
        _fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        _fh.flush()

    name = direction = None
    sn = pc = mac = None
    items = []
    if text:
        try:
            j = json.loads(text)
            name, mac, sn, pc, items = _extract(j)
        except (json.JSONDecodeError, AttributeError):
            pass

    # 方向：topic 倒数第 3 段判断
    direction = "cloud→screen" if "/cloud/to/screen/" in msg.topic else (
        "screen→cloud" if "/screen/to/cloud/" in msg.topic else "?")
    # MAC 兜底：从 topic 末段取
    if not mac:
        mac = msg.topic.rstrip("/").split("/")[-1]

    with _lock:
        _topic_counts[msg.topic] += 1
        _counts[name or "<unparsed>"] += 1
        # 汇总映射（任何带 deviceSn+items 的报文都贡献）
        if sn is not None and items:
            key = f"{mac}::{sn}"
            entry = _mapping.setdefault(
                key, {"screenMac": mac, "deviceSn": sn,
                      "productCode": pc, "attrs": {}, "seen_in": []})
            if pc is not None:
                entry["productCode"] = pc
            if name and name not in entry["seen_in"]:
                entry["seen_in"].append(name)
            for it in items:
                if it["attrTag"] is not None:
                    entry["attrs"][str(it["attrTag"])] = it["attrValue"]
        # 写命令单独留底（OQ-03/07 金矿）
        if name == "DeviceWrite":
            _device_writes.append(
                {"ts": ts, "screenMac": mac, "deviceSn": sn, "items": items})

    flag = "  ★DeviceWrite" if name == "DeviceWrite" else ""
    preview = (text or "")[:100]
    print(f"[{ts}] [{direction}] name={name} sn={sn} items={len(items)}{flag}  {preview}")


def _build(tls):
    try:
        from paho.mqtt.enums import CallbackAPIVersion
        c = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2,
                        client_id=f"oq03-sniff-{int(time.time())}",
                        transport=args.transport)
    except (ImportError, AttributeError):
        c = mqtt.Client(client_id=f"oq03-sniff-{int(time.time())}",
                        transport=args.transport)
    if args.username:
        c.username_pw_set(args.username, args.password)
    if tls:
        c.tls_set(cert_reqs=ssl.CERT_NONE if args.insecure else ssl.CERT_REQUIRED)
        if args.insecure:
            c.tls_insecure_set(True)
    if args.transport == "websockets":
        c.ws_set_options(path=args.path)
    c.reconnect_delay_set(min_delay=2, max_delay=30)
    c.on_connect, c.on_disconnect, c.on_message = on_connect, on_disconnect, on_message
    return c


def _connect_with_fallback():
    """先按 --tls 连；失败则自动尝试相反的 TLS 设置，省去手动试错。"""
    order = [args.tls, not args.tls]
    last_err = None
    for tls in order:
        c = _build(tls)
        try:
            print(f"[{_now()}] [INFO] 尝试连接 "
                  f"{'wss' if tls else 'ws'}://{args.host}:{args.port}{args.path} …")
            c.connect(args.host, args.port, keepalive=60)
            print(f"[{_now()}] [INFO] TCP/TLS 握手 OK（TLS={'on' if tls else 'off'}）")
            return c
        except Exception as e:                       # noqa: BLE001
            last_err = e
            print(f"[{_now()}] [WARN] TLS={'on' if tls else 'off'} 连接失败：{e}")
    raise last_err


def _dump_mapping(out_path):
    summary = {
        "captured_at": _now(),
        "broker": f"{'wss' if args.tls else 'ws'}://{args.host}:{args.port}{args.path}",
        "mac_filter": args.mac,
        "header_name_counts": dict(_counts),
        "topic_counts": dict(_topic_counts),
        "device_write_samples": _device_writes,
        "device_attr_mapping": list(_mapping.values()),
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    return summary


def main():
    global _fh
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    here = os.path.dirname(os.path.abspath(__file__))
    out_ndjson = args.output or os.path.join(here, f"screen_param_rw_{ts_str}.ndjson")
    out_mapping = os.path.splitext(out_ndjson)[0] + "_mapping.json"

    print("=" * 72)
    print("  屏端参数读写抓包 (OQ-03)")
    print(f"  Broker : {'wss' if args.tls else 'ws'}://{args.host}:{args.port}{args.path}")
    print(f"  凭据   : {args.username}/{'*' * len(args.password)}   MAC过滤: {args.mac}")
    print(f"  时长   : {args.duration}s")
    print(f"  NDJSON : {out_ndjson}")
    print(f"  映射   : {out_mapping}")
    print("=" * 72)

    os.makedirs(os.path.dirname(os.path.abspath(out_ndjson)), exist_ok=True)
    _fh = open(out_ndjson, "w", encoding="utf-8")

    try:
        client = _connect_with_fallback()
    except Exception as e:                            # noqa: BLE001
        print(f"[{_now()}] [ERROR] 连接彻底失败：{e}")
        print("  排查：①确认 8084 是 ws 还是 wss（试 --no-tls）"
              " ②证书问题加 --insecure ③认证 --username/--password ④路径 --path")
        _fh.close()
        sys.exit(1)

    timer = threading.Timer(args.duration, lambda: (_stop.set(), client.disconnect()))
    timer.daemon = True
    timer.start()

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[{_now()}] [INFO] Ctrl+C，退出…")
        _stop.set()
        timer.cancel()
        client.disconnect()
    finally:
        _fh.close()

    summary = _dump_mapping(out_mapping)
    total = sum(_topic_counts.values())
    print("\n" + "=" * 72)
    print(f"  结束 | 运行 {time.monotonic() - _ts0:.0f}s | 共 {total} 条报文")
    print(f"  header.name 分布 : {dict(_counts)}")
    print(f"  抓到 DeviceWrite : {len(_device_writes)} 条"
          + ("  ← OQ-03/07 可用！" if _device_writes else "  ← 未抓到，需在运行期触发一次写"))
    print(f"  设备属性映射条目 : {len(summary['device_attr_mapping'])} 个 (deviceSn)")
    print(f"  映射汇总文件     : {out_mapping}")
    print("=" * 72)
    # 控制台直接给一份可读映射预览（前若干条）
    for m in summary["device_attr_mapping"][:8]:
        tags = ", ".join(f"{k}={v}" for k, v in list(m["attrs"].items())[:6])
        more = "…" if len(m["attrs"]) > 6 else ""
        print(f"  [{m['screenMac']}] sn={m['deviceSn']} pc={m['productCode']} "
              f"seen_in={m['seen_in']}\n      {tags}{more}")


if __name__ == "__main__":
    main()
