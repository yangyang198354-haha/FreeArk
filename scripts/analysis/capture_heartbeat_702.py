"""
capture_heartbeat_702.py — FreeArk 大屏心跳抓取脚本（3-1-702）

功能：
  - 通过 WSS 连接公网 Broker，订阅 /screen/upload/screen/to/cloud/#
  - 过滤 topic 末段属于目标 MAC 集合的消息
  - 持续 600 秒后自动断开退出
  - 原始消息落盘至 capture_raw_3-1-702.jsonl（每行一条 JSON）
  - 每 30 秒打印进度到控制台
  - 退出时打印 summary

目标设备：
  specific_part: 3-1-7-702
  unique_id (MAC): c5d29c52a237ade5

依赖：
  pip install "paho-mqtt>=1.6.1"

凭据：从环境变量读取，或加载同目录 .env.capture，fallback admin/public

用法（PowerShell）：
  # 先创建凭据文件
  Copy-Item scripts\\analysis\\.env.capture.template scripts\\analysis\\.env.capture
  # 编辑 .env.capture 填入真实凭据（如不同于 admin/public）

  # 直接运行（使用 fallback admin/public）
  python scripts\\analysis\\capture_heartbeat_702.py

  # 运行时注入凭据
  $env:MQTT_USERNAME="admin"; $env:MQTT_PASSWORD="public"
  python scripts\\analysis\\capture_heartbeat_702.py

  # 指定输出文件（可选，默认与脚本同目录）
  $env:CAPTURE_OUTPUT="C:\\path\\to\\output.jsonl"
  python scripts\\analysis\\capture_heartbeat_702.py
"""

import json
import os
import ssl
import sys
import time
import threading
from collections import Counter, defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 凭据与配置加载
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent.resolve()


def _load_dotenv(env_file: Path) -> None:
    """简易 .env 解析器（无需 python-dotenv 依赖）。"""
    if not env_file.exists():
        return
    with open(env_file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val


_load_dotenv(_SCRIPT_DIR / ".env.capture")

MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "admin")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "public")  # fallback — 生产 config 已有明文

# 目标 MAC 集合（来自 all_owner.json / owner_info 表，building=3 unit=1单元 room=702）
TARGET_MACS: set = {
    "c5d29c52a237ade5",   # specific_part=3-1-7-702, 楼层=7楼
}

# 订阅 topic
SUBSCRIBE_TOPIC = "/screen/upload/screen/to/cloud/#"

# 抓取持续时间（秒）
CAPTURE_DURATION = 600

# 控制台进度打印间隔（秒）
PROGRESS_INTERVAL = 30

# 输出文件
OUTPUT_FILE = Path(os.environ.get("CAPTURE_OUTPUT", str(_SCRIPT_DIR / "capture_raw_3-1-702.jsonl")))

# Broker 候选列表（按优先级排序）
BROKER_CANDIDATES = [
    {"host": "www.ttqingjiao.site", "port": 8084, "path": "/mqtt",
     "label": "wss://www.ttqingjiao.site:8084/mqtt"},
    {"host": "www.ttqingjiao.site", "port": 443,  "path": "/mqtt",
     "label": "wss://www.ttqingjiao.site:443/mqtt"},
    {"host": "www.ttqingjiao.site", "port": 8884, "path": "/mqtt",
     "label": "wss://www.ttqingjiao.site:8884/mqtt"},
]

# ---------------------------------------------------------------------------
# 状态（线程安全：GIL 足够，Counter/defaultdict 是简单赋值）
# ---------------------------------------------------------------------------

_state = {
    "target_count": 0,        # 目标 MAC 消息总数
    "total_count": 0,         # 所有消息总数
    "topic_counter": Counter(),
    "target_ts": defaultdict(list),  # mac -> [epoch_ms, ...]（用于频率分析）
    "connected_label": None,
    "connect_success": False,
    "connect_event": threading.Event(),
    "stop_event": threading.Event(),
    "output_file": None,      # 打开的文件句柄
    "start_ts": None,
    "end_ts": None,
}


# ---------------------------------------------------------------------------
# paho 回调
# ---------------------------------------------------------------------------

def _on_connect(client, userdata, flags, rc):
    broker_cfg = userdata["broker_cfg"]
    if rc == 0:
        _state["connected_label"] = broker_cfg["label"]
        _state["connect_success"] = True
        print(f"[连接成功] {broker_cfg['label']}")
        client.subscribe(SUBSCRIBE_TOPIC, qos=0)
        print(f"[订阅] {SUBSCRIBE_TOPIC}")
        _state["connect_event"].set()
    else:
        rc_messages = {
            1: "协议版本不支持",
            2: "客户端 ID 被拒绝",
            3: "Broker 不可用",
            4: "用户名/密码错误",
            5: "未授权",
        }
        msg = rc_messages.get(rc, f"未知错误 rc={rc}")
        print(f"[连接失败] {broker_cfg['label']} — {msg}")
        _state["connect_success"] = False
        _state["connect_event"].set()


def _on_disconnect(client, userdata, rc):
    if rc != 0 and not _state["stop_event"].is_set():
        print(f"[意外断开] rc={rc}，将自动重连...")


def _on_message(client, userdata, msg):
    ts_ms = int(time.time() * 1000)
    _state["total_count"] += 1
    _state["topic_counter"][msg.topic] += 1

    # 解析 topic 末段（MAC）
    parts = msg.topic.rstrip("/").split("/")
    mac = parts[-1] if parts else ""

    # 解析 payload
    try:
        payload_text = msg.payload.decode("utf-8", errors="replace")
    except Exception:
        payload_text = repr(msg.payload)

    # 落盘：仅目标 MAC 消息写入 JSONL
    if mac in TARGET_MACS:
        _state["target_count"] += 1
        _state["target_ts"][mac].append(ts_ms)

        record = {
            "ts": ts_ms,
            "topic": msg.topic,
            "payload_text": payload_text,
            "payload_size": len(msg.payload),
            "qos": msg.qos,
        }
        if _state["output_file"]:
            _state["output_file"].write(json.dumps(record, ensure_ascii=False) + "\n")
            _state["output_file"].flush()


# ---------------------------------------------------------------------------
# Broker 连接（带回退）
# ---------------------------------------------------------------------------

def _try_connect_broker(candidate: dict) -> "mqtt.Client | None":
    """尝试连接单个 broker，成功返回 client，失败返回 None。"""
    import paho.mqtt.client as mqtt

    print(f"\n[尝试连接] {candidate['label']} ...")

    client = mqtt.Client(
        client_id=f"capture-3-1-702-{int(time.time())}",
        transport="websockets",
        callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
    )
    client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

    # TLS — Let's Encrypt 公网证书
    ssl_ctx = ssl.create_default_context()
    client.tls_set_context(ssl_ctx)
    client.ws_set_options(path=candidate["path"])

    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    client.user_data_set({"broker_cfg": candidate})

    _state["connect_event"].clear()
    _state["connect_success"] = False

    try:
        client.connect(candidate["host"], candidate["port"], keepalive=60)
    except Exception as exc:
        print(f"[连接异常] {candidate['label']} — {exc}")
        return None

    client.loop_start()

    # 等待 on_connect 回调（最多 15 秒）
    _state["connect_event"].wait(timeout=15)

    if _state["connect_success"]:
        return client
    else:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# 进度打印线程
# ---------------------------------------------------------------------------

def _progress_printer():
    while not _state["stop_event"].is_set():
        _state["stop_event"].wait(timeout=PROGRESS_INTERVAL)
        if _state["start_ts"] is not None:
            elapsed = int(time.time() - _state["start_ts"])
            remaining = max(0, CAPTURE_DURATION - elapsed)
            print(
                f"[进度 {elapsed:4d}s / {CAPTURE_DURATION}s | 剩余 {remaining}s] "
                f"目标消息: {_state['target_count']} 条 / 总消息: {_state['total_count']} 条"
            )


# ---------------------------------------------------------------------------
# summary 输出
# ---------------------------------------------------------------------------

def _print_summary():
    print("\n" + "=" * 60)
    print("抓取完成 — Summary")
    print("=" * 60)
    print(f"Broker    : {_state['connected_label']}")
    print(f"订阅 Topic : {SUBSCRIBE_TOPIC}")
    print(f"持续时间  : {CAPTURE_DURATION}s")
    print(f"总消息数  : {_state['total_count']}")
    print(f"目标消息数: {_state['target_count']}")
    print(f"输出文件  : {OUTPUT_FILE}")

    print("\n--- 目标 MAC 详情 ---")
    for mac in sorted(TARGET_MACS):
        tss = _state["target_ts"][mac]
        count = len(tss)
        if count == 0:
            print(f"  {mac}  →  本次抓取未收到消息")
        else:
            intervals = [tss[i + 1] - tss[i] for i in range(len(tss) - 1)]
            if intervals:
                avg_ms = sum(intervals) / len(intervals)
                sorted_iv = sorted(intervals)
                p50 = sorted_iv[len(sorted_iv) // 2]
                p95 = sorted_iv[int(len(sorted_iv) * 0.95)]
                print(f"  {mac}  →  {count} 条")
                print(f"    平均间隔: {avg_ms/1000:.1f}s  P50: {p50/1000:.1f}s  P95: {p95/1000:.1f}s")
            else:
                print(f"  {mac}  →  {count} 条（仅1条，无法计算间隔）")

    print("\n--- 非目标 Topic Top-5 ---")
    non_target = {
        t: c for t, c in _state["topic_counter"].items()
        if t.rstrip("/").split("/")[-1] not in TARGET_MACS
    }
    for topic, count in sorted(non_target.items(), key=lambda x: -x[1])[:5]:
        print(f"  {count:6d}x  {topic}")

    print("=" * 60)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("FreeArk 大屏心跳抓取脚本 v1.0")
    print(f"目标 MAC 集合: {TARGET_MACS}")
    print(f"抓取持续时间 : {CAPTURE_DURATION}s")
    print(f"输出文件     : {OUTPUT_FILE}")
    print("=" * 60)

    # 确保输出目录存在
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 尝试按序连接 broker
    client = None
    for candidate in BROKER_CANDIDATES:
        client = _try_connect_broker(candidate)
        if client is not None:
            break

    if client is None:
        print("\n[错误] 所有 Broker 候选均连接失败，请检查：")
        print("  1. 网络连通性（ping www.ttqingjiao.site）")
        print("  2. 凭据是否正确（.env.capture 或环境变量）")
        print("  3. Broker 是否在线")
        sys.exit(1)

    # 打开输出文件
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fh:
        _state["output_file"] = fh
        _state["start_ts"] = time.time()

        # 启动进度打印线程
        progress_thread = threading.Thread(target=_progress_printer, daemon=True)
        progress_thread.start()

        print(f"\n[开始抓取] 持续 {CAPTURE_DURATION}s，按 Ctrl+C 提前终止...")

        try:
            time.sleep(CAPTURE_DURATION)
        except KeyboardInterrupt:
            print("\n[用户中断]")

        _state["end_ts"] = time.time()
        _state["stop_event"].set()

    # 停止 MQTT
    client.loop_stop()
    try:
        client.disconnect()
    except Exception:
        pass

    _print_summary()


if __name__ == "__main__":
    main()
