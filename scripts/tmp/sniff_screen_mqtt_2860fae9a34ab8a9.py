#!/usr/bin/env python3
"""
临时诊断脚本：嗅探大屏 2860fae9a34ab8a9 的 MQTT 报文
======================================================
目标 broker : ttqingjiao.site:8084 (默认 WebSocket 协议)
目标 topic  :
  /screen/log/screen/to/cloud/2860fae9a34ab8a9
  /screen/event/status/change/2860fae9a34ab8a9
  /screen/service/cloud/to/screen/2860fae9a34ab8a9
运行时长    : 10 分钟（可通过 --duration 覆盖）
输出格式    : NDJSON，每行一条报文

注意：此脚本仅用于临时排查，不进生产部署流水线。
"""

import argparse
import base64
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# 依赖检测
# ---------------------------------------------------------------------------
try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("[ERROR] 缺少 paho-mqtt 依赖。请先安装：")
    print("    pip install paho-mqtt")
    print("若使用 WebSocket 传输（默认），还需确保 paho-mqtt >= 1.6.0 版本。")
    sys.exit(1)

# ---------------------------------------------------------------------------
# 命令行参数
# ---------------------------------------------------------------------------
SCREEN_MAC = "2860fae9a34ab8a9"
DEFAULT_TOPICS = [
    f"/screen/service/screen/to/cloud/{SCREEN_MAC}",
    f"/screen/upload/screen/to/cloud/{SCREEN_MAC}",
    f"/screen/log/screen/to/cloud/{SCREEN_MAC}",
    f"/screen/event/status/change/{SCREEN_MAC}",
]

parser = argparse.ArgumentParser(
    description=f"嗅探大屏 {SCREEN_MAC} 的 MQTT 报文，10 分钟后自动退出"
)
parser.add_argument("--host",      default="ttqingjiao.site",  help="Broker 主机名")
parser.add_argument("--port",      default=8084,  type=int,    help="Broker 端口（默认 8084）")
parser.add_argument("--transport", default="websockets",
                    choices=["websockets", "tcp"],
                    help="传输协议：websockets（默认，适合 8084）或 tcp")
parser.add_argument("--tls",       action="store_true",         help="开启 TLS（WSS / MQTTS）")
parser.add_argument("--username",  default=None,                help="MQTT 用户名（匿名时不填）")
parser.add_argument("--password",  default=None,                help="MQTT 密码（匿名时不填）")
parser.add_argument("--duration",  default=600, type=int,       help="监听时长（秒，默认 600=10分钟）")
parser.add_argument("--output",    default=None,
                    help="输出 NDJSON 文件路径（默认：脚本目录下 sniff_<mac>_<ts>.ndjson）")
args = parser.parse_args()

# ---------------------------------------------------------------------------
# 输出文件
# ---------------------------------------------------------------------------
if args.output:
    OUTPUT_FILE = args.output
else:
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    script_dir = os.path.dirname(os.path.abspath(__file__))
    OUTPUT_FILE = os.path.join(script_dir, f"sniff_{SCREEN_MAC}_{ts_str}.ndjson")

# ---------------------------------------------------------------------------
# 全局状态
# ---------------------------------------------------------------------------
_counters: dict[str, int] = {t: 0 for t in DEFAULT_TOPICS}
_lock = threading.Lock()
_start_time = time.monotonic()
_stop_event = threading.Event()
_output_fh = None  # 文件句柄，在 on_connect 之前打开

# ---------------------------------------------------------------------------
# MQTT 回调
# ---------------------------------------------------------------------------

def on_connect(client, userdata, flags, rc, properties=None):
    rc_messages = {
        0: "连接成功",
        1: "连接被拒绝：协议版本不接受",
        2: "连接被拒绝：客户端标识符不合法",
        3: "连接被拒绝：服务器不可用",
        4: "连接被拒绝：用户名或密码错误",
        5: "连接被拒绝：未授权",
    }
    # paho v1: rc 是 int；paho v2: rc 是 ReasonCode 对象（.value 才是 int）
    if hasattr(rc, "value"):
        rc_int = rc.value
        is_success = not getattr(rc, "is_failure", rc_int != 0)
    else:
        rc_int = rc if isinstance(rc, int) else -1
        is_success = (rc_int == 0)
    msg = rc_messages.get(rc_int, f"reason={rc} (code={rc_int})")
    if is_success:
        print(f"[{_iso_now()}] [INFO] Broker 连接成功，正在订阅 {len(DEFAULT_TOPICS)} 个 topic ...")
        for topic in DEFAULT_TOPICS:
            client.subscribe(topic, qos=1)
            print(f"[{_iso_now()}] [INFO]   已订阅: {topic}")
    else:
        print(f"[{_iso_now()}] [ERROR] 连接失败: {msg}")


def on_disconnect(client, userdata, *args, **kwargs):
    # 兼容 paho v1 (rc) 与 v2 (disconnect_flags, reason_code, properties)
    if _stop_event.is_set():
        return
    rc = args[-1] if args else kwargs.get("reason_code", "?")
    print(f"[{_iso_now()}] [WARN] 与 Broker 断开（rc={rc}），等待自动重连 ...")


def on_message(client, userdata, msg):
    ts = _iso_now()

    # payload 处理
    raw_bytes: bytes = msg.payload if msg.payload else b""
    payload_b64 = base64.b64encode(raw_bytes).decode("ascii")
    try:
        payload_text = raw_bytes.decode("utf-8")
    except (UnicodeDecodeError, AttributeError):
        payload_text = None

    record = {
        "ts_iso":           ts,
        "topic":            msg.topic,
        "payload_raw_b64":  payload_b64,
        "payload_text":     payload_text,
        "qos":              msg.qos,
        "retain":           bool(msg.retain),
        "mid":              msg.mid,
    }

    # 写文件
    global _output_fh
    if _output_fh:
        try:
            _output_fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            _output_fh.flush()
        except Exception as e:
            print(f"[{ts}] [ERROR] 写文件失败: {e}")

    # 更新计数
    with _lock:
        if msg.topic in _counters:
            _counters[msg.topic] += 1
        else:
            _counters[msg.topic] = 1

    # stdout 预览（前 120 个字符）
    preview = (payload_text or payload_b64)[:120]
    short_topic = msg.topic.split("/")[-2] + "/" + msg.topic.split("/")[-1]
    print(f"[{ts}] [MSG] qos={msg.qos} retain={int(msg.retain)} "
          f"topic=.../{short_topic}  {preview}")


def on_subscribe(client, userdata, mid, granted_qos, properties=None):
    pass  # 已在 on_connect 打印订阅信息


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _build_client() -> mqtt.Client:
    """构造 paho Client，兼容 paho-mqtt v1.x 和 v2.x。"""
    # paho v2.x 引入了 CallbackAPIVersion
    try:
        from paho.mqtt.enums import CallbackAPIVersion
        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"sniff_{SCREEN_MAC}_{int(time.time())}",
            transport=args.transport,
        )
    except (ImportError, AttributeError):
        # paho v1.x
        client = mqtt.Client(
            client_id=f"sniff_{SCREEN_MAC}_{int(time.time())}",
            transport=args.transport,
        )

    if args.username:
        client.username_pw_set(args.username, args.password)

    if args.tls:
        import ssl
        client.tls_set(cert_reqs=ssl.CERT_REQUIRED)
        client.tls_insecure_set(False)

    # WebSocket path —— paho 默认是 /mqtt，可按需改
    if args.transport == "websockets":
        client.ws_set_options(path="/mqtt")

    client.reconnect_delay_set(min_delay=2, max_delay=30)

    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.on_subscribe  = on_subscribe

    return client


# ---------------------------------------------------------------------------
# 超时定时器
# ---------------------------------------------------------------------------

def _timeout_handler(client: mqtt.Client):
    """10 分钟（或 --duration 指定时长）后触发，优雅停止。"""
    _stop_event.set()
    print(f"\n[{_iso_now()}] [INFO] 已到达 {args.duration} 秒监听时长，正在退出 ...")
    client.disconnect()


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------

def main():
    global _output_fh

    print("=" * 70)
    print(f"  MQTT 嗅探器 — 大屏 {SCREEN_MAC}")
    _scheme = {
        ("websockets", False): "ws",
        ("websockets", True):  "wss",
        ("tcp",        False): "mqtt",
        ("tcp",        True):  "mqtts",
    }.get((args.transport, args.tls), args.transport)
    print(f"  Broker  : {_scheme}://{args.host}:{args.port}")
    print(f"  凭据    : {'匿名' if not args.username else args.username}")
    print(f"  时长    : {args.duration} 秒")
    print(f"  输出    : {OUTPUT_FILE}")
    print("=" * 70)

    # 打开输出文件
    os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_FILE)), exist_ok=True)
    _output_fh = open(OUTPUT_FILE, "w", encoding="utf-8")

    client = _build_client()

    # 设置超时定时器
    timer = threading.Timer(args.duration, _timeout_handler, args=(client,))
    timer.daemon = True
    timer.start()

    print(f"[{_iso_now()}] [INFO] 正在连接 {args.host}:{args.port} ...")
    try:
        client.connect(args.host, args.port, keepalive=60)
    except Exception as e:
        print(f"[{_iso_now()}] [ERROR] 初始连接失败: {e}")
        print()
        print("常见原因：")
        print("  1. 端口 8084 是 WebSocket，请确认 Broker 确实监听此端口且路径正确")
        print("     （若是原生 TCP，请加 --transport tcp --port 1883）")
        print("  2. Broker 要求认证，请加 --username xxx --password yyy")
        print("  3. 需要 TLS，请加 --tls（WSS 通常使用 443 或 8084 TLS）")
        timer.cancel()
        if _output_fh:
            _output_fh.close()
        sys.exit(1)

    try:
        client.loop_forever()
    except KeyboardInterrupt:
        print(f"\n[{_iso_now()}] [INFO] 用户中断（Ctrl+C），正在退出 ...")
        _stop_event.set()
        timer.cancel()
        client.disconnect()
    finally:
        if _output_fh:
            _output_fh.close()

    # 打印最终统计
    elapsed = time.monotonic() - _start_time
    total = sum(_counters.values())
    file_size = os.path.getsize(OUTPUT_FILE) if os.path.exists(OUTPUT_FILE) else 0

    print()
    print("=" * 70)
    print(f"  嗅探结束  |  实际运行: {elapsed:.1f} 秒  |  共收到: {total} 条报文")
    print("-" * 70)
    for topic, cnt in _counters.items():
        short = "..." + topic[-50:] if len(topic) > 50 else topic
        print(f"  {cnt:>5} 条  {short}")
    print("-" * 70)
    print(f"  输出文件 : {OUTPUT_FILE}")
    print(f"  文件大小 : {file_size:,} 字节 ({file_size / 1024:.1f} KB)")
    print("=" * 70)


if __name__ == "__main__":
    main()
