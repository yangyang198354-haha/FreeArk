"""
panel_calib_capture — 温控面板标定 · 阶段 1：采集屏端遥测

背景：
  屏端 DeviceStatusUpdate 的值不落库（后端不连厂端 broker，小程序直连），
  故标定所需的「屏端一侧」数据必须现场采集。本命令订阅厂端 broker，
  把温控面板（product_code=120003）的 temp/humidity/temp_set/dew_point_temp/switch
  写成 JSONL，供 panel_calib_correlate 使用。

只读保证：
  - 只 subscribe，绝不 publish（不下发任何 DeviceWrite）。
  - DB 只 SELECT OwnerInfo（做 MAC → specific_part 映射），不写任何表。
  - 使用独立 client_id，不与 freeark-fault-consumer / screen-heartbeat 冲突。

用法：
  # 采集 2 小时（推荐；温度缓慢漂移，样本越多配对越稳）
  python manage.py panel_calib_capture --duration 7200 --out /tmp/panel_calib.jsonl

  # 只采某一户
  python manage.py panel_calib_capture --duration 1800 --specific-part 3-1-7-702 \
      --out /tmp/panel_calib_702.jsonl

参见：api/panel_calibration.py
"""

import json
import logging
import os
import threading
import time
from typing import Optional

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from api.panel_calibration import (
    PANEL_PRODUCT_CODE,
    screen_attr_tags,
    write_capture_record,
)

logger = logging.getLogger(__name__)

# 复用 fault_consumer 的 broker 配置文件（同一厂端 broker）
_HBC_CONFIG_PATH = os.path.join(
    os.path.dirname(
    os.path.dirname(
    os.path.dirname(
    os.path.dirname(
    os.path.dirname(
    os.path.abspath(__file__)))))),
    'heartbeat_broker_config.json',
)

_FALLBACK_CONFIG: dict = {
    'protocol': 'wss',
    'host': 'www.ttqingjiao.site',
    'port': 8084,
    'path': '/mqtt',
    'username': 'admin',
    'password': 'public',
    'keepalive': 60,
    'fault_consumer_topic': '/screen/upload/screen/to/cloud/+',
}

CACHE_REFRESH_INTERVAL = 300


def _load_config() -> dict:
    """加载 broker 配置，缺失时降级到 fallback（与 fault_consumer 同源）。"""
    try:
        with open(_HBC_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning('panel_calib_capture: 配置文件未找到 (%s)，使用默认配置',
                       _HBC_CONFIG_PATH)
        return dict(_FALLBACK_CONFIG)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning('panel_calib_capture: 配置读取失败，使用默认配置: %s', exc)
        return dict(_FALLBACK_CONFIG)


class _MacCache:
    """内存缓存 mac → specific_part，定期从 OwnerInfo 刷新（只读）。"""

    def __init__(self):
        self._cache: dict = {}
        self._last_refresh: float = 0.0

    def _refresh(self):
        from api.models import OwnerInfo
        close_old_connections()
        try:
            self._cache = {
                row['unique_id']: row['specific_part']
                for row in OwnerInfo.objects
                .filter(unique_id__isnull=False)
                .exclude(unique_id='')
                .values('unique_id', 'specific_part')
            }
            self._last_refresh = time.time()
            logger.info('_MacCache: 刷新完成，共 %d 条映射', len(self._cache))
        except Exception as exc:
            logger.warning('_MacCache: 刷新失败，继续使用旧缓存: %s', exc)

    def get_specific_part(self, mac: str) -> Optional[str]:
        if time.time() - self._last_refresh > CACHE_REFRESH_INTERVAL:
            self._refresh()
        return self._cache.get(mac)


class Command(BaseCommand):
    help = '温控面板标定阶段 1：订阅厂端 broker 采集屏端面板遥测到 JSONL（只订阅不下发）'

    def add_arguments(self, parser):
        parser.add_argument('--duration', type=int, default=1800,
                            help='采集时长（秒），默认 1800')
        parser.add_argument('--out', required=True,
                            help='输出 JSONL 路径')
        parser.add_argument('--specific-part', default=None,
                            help='只采集该户；不填则采集全部')

    def handle(self, *args, **options):
        import paho.mqtt.client as mqtt

        duration = options['duration']
        out_path = options['out']
        only_sp = options.get('specific_part')

        cfg = _load_config()
        protocol  = cfg.get('protocol', 'wss')
        host      = cfg.get('host', 'www.ttqingjiao.site')
        port      = int(cfg.get('port', 8084))
        path      = cfg.get('path', '/mqtt')
        username  = cfg.get('username', 'admin')
        password  = cfg.get('password', 'public')
        keepalive = int(cfg.get('keepalive', 60))
        topic     = cfg.get('fault_consumer_topic', '/screen/upload/screen/to/cloud/+')
        client_id = 'freeark-panel-calib'

        wanted_tags = set(screen_attr_tags())
        mac_cache = _MacCache()
        stats = {'msgs': 0, 'records': 0, 'panels': set(), 'owners': set()}
        stop_evt = threading.Event()

        self.stdout.write(
            f'采集启动：broker={host}:{port} topic={topic} '
            f'时长={duration}s 输出={out_path}'
        )
        self.stdout.write('仅订阅，不会下发任何写指令。')
        if only_sp:
            self.stdout.write(f'过滤：只保留 {only_sp}')

        fh = open(out_path, 'a', encoding='utf-8')

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info('已连接 Broker %s:%d，订阅 %s', host, port, topic)
                client.subscribe(topic)
            else:
                logger.warning('Broker 连接失败，rc=%d', rc)

        def on_message(client, userdata, msg):
            try:
                self._handle(msg, mac_cache, fh, wanted_tags, only_sp, stats)
            except Exception as exc:
                logger.exception('on_message 未处理异常: %s', exc)

        def on_disconnect(client, userdata, rc):
            if rc != 0:
                logger.warning('与 Broker 断开，rc=%d，paho 将自动重连', rc)

        if protocol == 'wss':
            client = mqtt.Client(client_id=client_id, transport='websockets')
            client.tls_set()
            client.ws_set_options(path=path)
        else:
            client = mqtt.Client(client_id=client_id, transport='tcp')

        client.username_pw_set(username, password)
        client.on_connect = on_connect
        client.on_message = on_message
        client.on_disconnect = on_disconnect
        client.connect(host, port, keepalive)
        client.loop_start()

        # 进度打印 + 到时停止
        deadline = time.time() + duration
        try:
            while time.time() < deadline and not stop_evt.is_set():
                time.sleep(10)
                self.stdout.write(
                    f'  [{int(deadline - time.time()):>5}s 剩余] '
                    f'报文={stats["msgs"]} 记录={stats["records"]} '
                    f'面板={len(stats["panels"])} 住户={len(stats["owners"])}'
                )
        except KeyboardInterrupt:
            self.stdout.write('收到中断，提前结束采集。')
        finally:
            client.loop_stop()
            client.disconnect()
            fh.close()

        self.stdout.write('')
        self.stdout.write(
            f'采集完成：报文 {stats["msgs"]} 条，落盘 {stats["records"]} 条记录，'
            f'覆盖 {len(stats["panels"])} 块面板 / {len(stats["owners"])} 户'
        )
        self.stdout.write(f'输出：{out_path}')
        self.stdout.write('')
        self.stdout.write('下一步：')
        self.stdout.write(
            f'  python manage.py panel_calib_correlate --capture {out_path}'
            + (f' --specific-part {only_sp}' if only_sp else '')
        )

    # -----------------------------------------------------------------

    def _handle(self, msg, mac_cache, fh, wanted_tags, only_sp, stats):
        """解析一条 DeviceStatusUpdate，落盘面板设备的关心属性。

        报文结构（与 fault_consumer 同源，生产 EMQX 实测）：
          {"header": {"name": "DeviceStatusUpdate", "screenMac": "<mac>"},
           "payload": {"data": {"deviceSn": <int>, "productCode": <int>,
                                "items": [{"attrTag": "<t>", "attrValue": "<v>"}]}}}
        """
        stats['msgs'] += 1

        try:
            root = json.loads(msg.payload.decode('utf-8', errors='replace'))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(root, dict):
            return

        header = root.get('header') or {}
        if header.get('name') != 'DeviceStatusUpdate':
            return

        # MAC → specific_part（优先 topic 末段，回退 header.screenMac，与 fault_consumer 一致）
        mac = msg.topic.rsplit('/', 1)[-1] if msg.topic else ''
        sp = mac_cache.get_specific_part(mac)
        if sp is None:
            mac = str(header.get('screenMac', '') or '')
            sp = mac_cache.get_specific_part(mac)
        if sp is None:
            return
        if only_sp is not None and sp != only_sp:
            return

        data = (root.get('payload') or {}).get('data') or {}
        product_code = str(data.get('productCode', ''))
        if product_code != PANEL_PRODUCT_CODE:
            return

        device_sn = str(data.get('deviceSn', ''))
        if not device_sn:
            return

        now_iso = timezone.now().isoformat()
        for item in (data.get('items') or []):
            tag = item.get('attrTag')
            if tag not in wanted_tags:
                continue
            write_capture_record(
                fh, sp, device_sn, product_code,
                tag, item.get('attrValue'), now_iso,
            )
            stats['records'] += 1
            stats['panels'].add((sp, device_sn))
            stats['owners'].add(sp)

        fh.flush()
