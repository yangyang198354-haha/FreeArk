import json
import logging
import os
import queue
import re
import time
import threading
from datetime import datetime
import paho.mqtt.client as mqtt
import MySQLdb
from django.conf import settings
from django.db import connection as django_connection
from django.db import transaction, close_old_connections
from django.db.utils import OperationalError as DjangoOperationalError
from django.utils import timezone
from .models import PLCData, PLCWriteRecord, PLCLatestData
from .mqtt_handlers import PLCDataHandler, ConnectionStatusHandler, PLCLatestDataHandler, ScreenConnectivityHandler, OndemandPLCLatestDataHandler

# 获取logger
logger = logging.getLogger(__name__)

# 获取配置文件路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MQTT_CONFIG_PATH = os.path.join(BASE_DIR, 'mqtt_config.json')


def load_mqtt_config(config_path=MQTT_CONFIG_PATH):
    """加载MQTT配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        logger.info(f"成功加载MQTT配置文件: {config_path}")
        return config
    except FileNotFoundError:
        logger.warning(f"MQTT配置文件不存在: {config_path}，使用默认配置")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"MQTT配置文件解析错误: {e}")
        return {}
    except Exception as e:
        logger.error(f"加载MQTT配置文件时发生错误: {e}")
        return {}



# energy 消息 ~580B，general 消息 ~11KB；以 2000B 为分界线路由到不同队列
_ENERGY_PAYLOAD_MAX_SIZE = 2000
NUM_ENERGY_WORKERS = 3
NUM_GENERAL_WORKERS = 6
# v0.5.6：按需采集独立队列 + 1 个专属 worker（OQ-002 决议：1 个线程串行入库）
NUM_ONDEMAND_WORKERS = 1
ONDEMAND_RESULT_TOPIC_PREFIX = '/datacollection/plc/ondemand/result/'
ONDEMAND_DONE_TOPIC_PREFIX = '/datacollection/plc/ondemand/done/'
# 每个 worker 每处理 N 条消息才调用一次 close_old_connections，避免频繁 MySQL 握手
_CLOSE_CONN_EVERY_N = 50


class MQTTConsumer:
    def __init__(self, num_energy_workers=NUM_ENERGY_WORKERS,
                 num_general_workers=NUM_GENERAL_WORKERS,
                 queue_maxsize=2000):
        # 加载MQTT配置
        mqtt_config = load_mqtt_config()

        # MQTT配置 - 从配置文件读取，环境变量作为备份
        # fallback 与生产 broker 保持一致（192.168.31.98:32788，同 PLCWriteSubscriber）
        self.mqtt_broker = os.environ.get('MQTT_BROKER', mqtt_config.get('host', '192.168.31.98'))
        self.mqtt_port = int(os.environ.get('MQTT_PORT', mqtt_config.get('port', 32788)))
        self.mqtt_username = os.environ.get('MQTT_USERNAME', mqtt_config.get('username', ''))
        self.mqtt_password = os.environ.get('MQTT_PASSWORD', mqtt_config.get('password', ''))
        self.mqtt_topic = os.environ.get('MQTT_TOPIC', mqtt_config.get('topic', '/datacollection/plc/to/collector/#'))
        self.mqtt_client_id = os.environ.get('MQTT_CLIENT_ID', f'django-mqtt-client-{os.getpid()}')
        self.keepalive = int(os.environ.get('MQTT_KEEPALIVE', mqtt_config.get('keepalive', 60)))
        self.qos = mqtt_config.get('qos', 1)
        self.retain = mqtt_config.get('retain', False)
        self.tls_enabled = mqtt_config.get('tls_enabled', False)

        # 创建MQTT客户端
        self.client = mqtt.Client(client_id=self.mqtt_client_id, clean_session=True)

        # 设置回调函数
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.on_log = self.on_log

        # 设置用户名和密码
        if self.mqtt_username and self.mqtt_password:
            self.client.username_pw_set(self.mqtt_username, self.mqtt_password)

        # 数据库连接维护配置
        self.db_maintenance_interval = 300  # 定期检查数据库连接的间隔（秒）
        self.db_maintenance_thread = None
        self.db_maintenance_running = False

        # 消息处理器：energy 消息含连接状态更新，general 消息跳过（节省 ~150ms/条）
        self.energy_handlers = [
            PLCDataHandler(),
            ConnectionStatusHandler(),
            PLCLatestDataHandler(),
        ]
        self.general_handlers = [
            PLCDataHandler(),
            PLCLatestDataHandler(),
        ]

        # --- 双队列 + 专用 Worker 线程池 ---
        # energy 队列：小消息（~580B），3 个专用 worker
        # general 队列：大消息（~11KB），6 个专用 worker，避免被 energy 消息阻塞
        self._energy_queue = queue.Queue(maxsize=queue_maxsize)
        self._general_queue = queue.Queue(maxsize=queue_maxsize)
        self._num_energy_workers = num_energy_workers
        self._num_general_workers = num_general_workers
        # v0.5.6: 按需采集独立队列（MOD-BE-04），1 个 worker，完全与 energy/general 解耦
        self._ondemand_queue = queue.Queue(maxsize=100)
        self._num_ondemand_workers = NUM_ONDEMAND_WORKERS
        self.ondemand_handlers = [
            OndemandPLCLatestDataHandler(),
        ]
        self._worker_threads = []
        # 停止信号：set() 后 worker 在队列清空时退出
        self.stop_event = threading.Event()

    # MQTT topic for screen connectivity (MOD-MQTT-01)
    SCREEN_CONNECTIVITY_TOPIC = '/datacollection/screen/connectivity'
    # MQTT topic prefix for PLC write ack (FR4/FR5)
    WRITE_ACK_TOPIC_PREFIX = '/datacollection/plc/write/ack/'
    # v0.5.6: 按需采集 topic 前缀（MOD-BE-04）
    ONDEMAND_RESULT_TOPIC_PREFIX = ONDEMAND_RESULT_TOPIC_PREFIX
    ONDEMAND_DONE_TOPIC_PREFIX = ONDEMAND_DONE_TOPIC_PREFIX

    def on_connect(self, client, userdata, flags, rc):
        """连接到MQTT代理后的回调函数"""
        if rc == 0:
            logger.info(f"成功连接到MQTT代理: {self.mqtt_broker}:{self.mqtt_port}")
            # 订阅主题，使用配置的QoS
            client.subscribe(self.mqtt_topic, qos=self.qos)
            logger.info(f"已订阅主题: {self.mqtt_topic} (QoS: {self.qos})")
            # 订阅大屏连通性 topic（MOD-MQTT-01）
            client.subscribe(self.SCREEN_CONNECTIVITY_TOPIC, qos=self.qos)
            logger.info(f"已订阅主题: {self.SCREEN_CONNECTIVITY_TOPIC} (QoS: {self.qos})")
            # 订阅 PLC 写入回执 topic（FR4/FR5）
            client.subscribe('/datacollection/plc/write/ack/#', qos=self.qos)
            logger.info("已订阅主题: /datacollection/plc/write/ack/# (QoS: %s)", self.qos)
            # v0.5.6: 订阅按需采集结果 topic（MOD-BE-04）
            client.subscribe('/datacollection/plc/ondemand/result/#', qos=self.qos)
            logger.info("已订阅主题: /datacollection/plc/ondemand/result/# (ondemand 按需采集结果)")
        else:
            logger.error(f"连接到MQTT代理失败，返回代码: {rc}")

    def _safe_json_parse(self, json_str):
        """增强的JSON解析功能，专门处理格式错误的JSON字符串"""
        try:
            # 尝试直接解析
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON解析错误: {str(e)}，消息内容前200字节: {json_str[:200]}")
            logger.error(f"错误位置上下文: '{json_str[max(0, e.pos-20):e.pos+20]}' (位置: {e.pos})")

            # 1. 尝试使用简单的修复方法 - 专注于已知的问题点
            try:
                # 直接使用手动解析方法，因为这是最可靠的方式
                # 从日志中我们知道消息格式是相对固定的

                # 提取device_id（格式如"9-1-31-3104"）
                device_id_match = re.search(r'"([0-9\-]+)"\s*:\s*\{', json_str)
                if not device_id_match:
                    raise ValueError("无法提取device_id")
                device_id = device_id_match.group(1)
                logger.info(f"提取到device_id: {device_id}")

                # 提取PLC IP地址
                plc_ip_match = re.search(r'"PLC IP地址"\s*:\s*"([^"]*)"', json_str)
                plc_ip = plc_ip_match.group(1) if plc_ip_match else "未知"
                logger.debug(f"提取到PLC IP地址: {plc_ip}")

                # 提取total_hot_quantity相关信息
                hot_value_match = re.search(r'"total_hot_quantity"\s*:\s*\{[^}]*"value"\s*:\s*([^,}]*)', json_str)
                hot_success_match = re.search(r'"total_hot_quantity"\s*:\s*\{[^}]*"success"\s*:\s*([^,}]*)', json_str)
                hot_message_match = re.search(r'"total_hot_quantity"\s*:\s*\{[^}]*"message"\s*:\s*"([^"]*)"', json_str)

                # 提取total_cold_quantity相关信息
                cold_value_match = re.search(r'"total_cold_quantity"\s*:\s*\{[^}]*"value"\s*:\s*([^,}]*)', json_str)
                cold_success_match = re.search(r'"total_cold_quantity"\s*:\s*\{[^}]*"success"\s*:\s*([^,}]*)', json_str)
                cold_message_match = re.search(r'"total_cold_quantity"\s*:\s*\{[^}]*"message"\s*:\s*"([^"]*)"', json_str)

                # 提取时间戳
                timestamp_match = re.search(r'"timestamp"\s*:\s*"([^"]*)"', json_str)
                timestamp = timestamp_match.group(1) if timestamp_match else datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # 构建完整的结果字典
                manual_result = {
                    device_id: {
                        "PLC IP地址": plc_ip,
                        "data": {}
                    }
                }

                # 添加制热数据
                if hot_value_match:
                    hot_value = hot_value_match.group(1).strip()
                    manual_result[device_id]["data"]["total_hot_quantity"] = {
                        "value": None if hot_value == "null" else int(hot_value) if hot_value.isdigit() else hot_value,
                        "success": hot_success_match and hot_success_match.group(1).strip() == "true",
                        "message": hot_message_match.group(1) if hot_message_match else "",
                        "timestamp": timestamp
                    }
                    logger.debug(f"提取到制热数据: value={manual_result[device_id]['data']['total_hot_quantity']['value']}, success={manual_result[device_id]['data']['total_hot_quantity']['success']}")

                # 添加制冷数据
                if cold_value_match:
                    cold_value = cold_value_match.group(1).strip()
                    manual_result[device_id]["data"]["total_cold_quantity"] = {
                        "value": None if cold_value == "null" else int(cold_value) if cold_value.isdigit() else cold_value,
                        "success": cold_success_match and cold_success_match.group(1).strip() == "true",
                        "message": cold_message_match.group(1) if cold_message_match else "",
                        "timestamp": timestamp
                    }
                    logger.debug(f"提取到制冷数据: value={manual_result[device_id]['data']['total_cold_quantity']['value']}, success={manual_result[device_id]['data']['total_cold_quantity']['success']}")

                logger.debug("成功通过手动解析构建JSON数据")
                return manual_result

            except Exception as e:
                logger.error(f"手动解析过程中发生错误: {str(e)}")

                # 作为最后的备选方案，尝试直接从字符串中提取关键信息
                try:
                    # 最简单的方法：只提取我们真正需要的数据
                    device_id = re.search(r'"([0-9\-]+)"\s*:\s*\{', json_str)
                    if device_id:
                        device_id = device_id.group(1)
                        # 返回一个最小化但可用的结构
                        minimal_result = {
                            device_id: {
                                "PLC IP地址": "手动解析",
                                "data": {
                                    "total_hot_quantity": {"value": 0, "success": False},
                                    "total_cold_quantity": {"value": 0, "success": False}
                                }
                            }
                        }
                        logger.warning(f"返回最小化结构: device_id={device_id}")
                        return minimal_result
                except Exception:
                    logger.error("最小化解析也失败")

            # 所有修复尝试都失败
            logger.error("所有JSON解析修复尝试都失败")
            raise

    # ------------------------------------------------------------------
    # 核心修改：on_message 仅入队，零阻塞网络线程
    # ------------------------------------------------------------------
    def on_message(self, client, userdata, msg):
        """收到MQTT消息后的回调函数。

        仅将原始 payload 放入对应队列并立即返回（目标 < 1ms），
        不执行任何 I/O 或 DB 操作，确保 paho 网络线程不被阻塞，
        从而能持续发送 PINGREQ，避免 EMQX rc=16 断连。

        路由规则：screen/connectivity → general_queue（避免被 PLC 消息挤满的 energy 队列丢弃）；
        其余 payload < 2000B → energy_queue，否则 → general_queue。
        """
        payload_size = len(msg.payload)
        # v0.5.6: 按需采集结果消息优先路由到独立 ondemand 队列，确保零等待（MOD-BE-04）
        if msg.topic.startswith(self.ONDEMAND_RESULT_TOPIC_PREFIX):
            target_queue = self._ondemand_queue
            queue_name = 'ondemand'
        elif msg.topic == self.SCREEN_CONNECTIVITY_TOPIC:
            target_queue = self._general_queue
            queue_name = 'general'
        elif msg.topic.startswith(self.WRITE_ACK_TOPIC_PREFIX):
            target_queue = self._general_queue
            queue_name = 'general'
        else:
            is_general = payload_size >= _ENERGY_PAYLOAD_MAX_SIZE
            target_queue = self._general_queue if is_general else self._energy_queue
            queue_name = 'general' if is_general else 'energy'
        try:
            target_queue.put_nowait((msg.topic, msg.payload, msg.qos))
            logger.debug("消息入队: topic=%s, size=%d bytes, queue=%s", msg.topic, payload_size, queue_name)
        except queue.Full:
            logger.warning("消息队列已满(%s, maxsize=%d)，丢弃消息: topic=%s",
                           queue_name, target_queue.maxsize, msg.topic)

    # ------------------------------------------------------------------
    # 新增：_dispatch — 原 on_message 的解码+解析+分发逻辑，由 worker 调用
    # ------------------------------------------------------------------
    def _dispatch(self, topic: str, payload_bytes: bytes, is_general: bool = False):
        """解码 payload 并调用 process_message，在 worker 线程中执行。

        close_old_connections/ensure_connection 由调用方 _worker_loop 负责，
        已在进入此方法前完成，无需在此重复调用。
        """
        logger.info(f"[dispatch] 处理消息: 主题={topic}, 长度={len(payload_bytes)}字节")

        # 解码
        payload_str = None
        try:
            try:
                payload_str = payload_bytes.decode('utf-8')
            except UnicodeDecodeError:
                payload_str = payload_bytes.decode('latin-1')
            logger.debug(f"消息内容: {payload_str[:500]}{'...' if len(payload_str) > 500 else ''}")
        except UnicodeDecodeError as e:
            logger.error(f"消息解码错误: {e}，原始字节: {str(payload_bytes[:100])}")
            return

        # JSON 解析
        try:
            payload = self._safe_json_parse(payload_str)
            logger.debug(f"成功解析JSON，数据类型: {type(payload).__name__}")

            # 记录 payload 摘要（与原 on_message 保持一致）
            if isinstance(payload, dict) and len(payload) == 1:
                _dbg_device_id = next(iter(payload))
                _dbg_device_info = payload[_dbg_device_id]
                if isinstance(_dbg_device_info, dict) and 'data' in _dbg_device_info:
                    _dbg_params = _dbg_device_info['data']
                    _dbg_total = len(_dbg_params) if isinstance(_dbg_params, dict) else 0
                    _dbg_success = sum(
                        1 for p in _dbg_params.values()
                        if isinstance(p, dict) and p.get('success')
                    ) if isinstance(_dbg_params, dict) else 0
                    _dbg_failed = _dbg_total - _dbg_success
                    logger.debug(
                        f"[dispatch] payload 解析摘要: device_id={_dbg_device_id}, "
                        f"param_count={_dbg_total}, success={_dbg_success}, failed={_dbg_failed}"
                    )

            # 调用原有的 process_message（含重试 + handler 分发）
            self.process_message(topic, payload, is_general=is_general)

        except json.JSONDecodeError as e:
            content_preview = payload_str[:200] if payload_str else "无法解码"
            logger.error(f"JSON解析错误: {e}，消息内容前200字节: {content_preview}")
            error_pos = min(e.pos, len(payload_str) - 1) if payload_str and hasattr(e, 'pos') else 0
            context_start = max(0, error_pos - 20)
            context_end = min(len(payload_str), error_pos + 20) if payload_str else 0
            if payload_str:
                logger.error(f"错误位置上下文: '{payload_str[context_start:context_end]}' (位置: {error_pos})")
                logger.debug(f"完整消息内容: {payload_str}")

        except Exception as e:
            logger.error(f"[dispatch] 处理消息时发生意外错误: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # 新增：_worker_loop — worker 线程入口
    # ------------------------------------------------------------------
    def _worker_loop(self, msg_queue: queue.Queue, is_general: bool):
        """Worker 线程主循环：从队列取消息 → _dispatch → task_done。

        每个 worker 线程持有独立的 Django thread-local DB 连接。
        stop_event.set() 后，继续消费直到队列清空再退出。

        close_old_connections 降频：每处理 _CLOSE_CONN_EVERY_N 条消息调用一次，
        避免每条消息都触发 MySQL 握手重建（节省约 10ms/次）。
        """
        thread_name = threading.current_thread().name
        close_old_connections()
        django_connection.ensure_connection()
        logger.info(f"[{thread_name}] Worker 线程启动 (类型={'general' if is_general else 'energy'})")

        msg_counter = 0
        while not self.stop_event.is_set() or not msg_queue.empty():
            try:
                topic, payload_bytes, qos = msg_queue.get(timeout=1)
            except queue.Empty:
                continue

            t_start = time.monotonic()
            try:
                msg_counter += 1
                if msg_counter % _CLOSE_CONN_EVERY_N == 0:
                    close_old_connections()
                django_connection.ensure_connection()

                self._dispatch(topic, payload_bytes, is_general=is_general)
            except Exception as e:
                logger.error(
                    f"[{thread_name}] 处理消息异常: topic={topic}, error={e}",
                    exc_info=True
                )
            finally:
                msg_queue.task_done()
                elapsed_ms = (time.monotonic() - t_start) * 1000
                logger.info(f"[{thread_name}] 消息处理完成: topic={topic}, 耗时={elapsed_ms:.1f}ms")

        logger.info(f"[{thread_name}] Worker 线程退出")

    def _handle_write_ack(self, payload):
        """处理 PLC 写入回执消息，更新 plc_write_record 状态（FR4-5，P4 批量适配）

        v0.4.0 批量回执格式：
        {
            "request_id": "<batch_request_id>",
            "specific_part": "...",
            "success": false,
            "items": [
                {"param_name": "x", "success": true},
                {"param_name": "y", "success": false, "error_message": "..."}
            ]
        }
        按 batch_request_id + param_name 定位各行，逐项更新状态。
        """
        try:
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode('utf-8')
            if isinstance(payload, str):
                data = json.loads(payload)
            else:
                data = payload

            batch_request_id = data.get('request_id')
            if not batch_request_id:
                logger.warning('write ack 消息缺少 request_id，跳过')
                return

            now = timezone.now()
            items = data.get('items')

            if items and isinstance(items, list):
                # P4 批量回执：按 param_name 逐项更新
                for item in items:
                    param_name = item.get('param_name')
                    if not param_name:
                        continue
                    item_success = item.get('success', False)
                    item_status = 'success' if item_success else 'failed'
                    item_err = item.get('error_message', '') if not item_success else None

                    # v0.4.7: 写成功时同步 plc_latest_data，让 UI 立即看到新值（不依赖 PLC 采集周期）
                    # 先 SELECT 拿 new_value + specific_part，再 update plc_write_record
                    pending_recs = list(PLCWriteRecord.objects.filter(
                        batch_request_id=batch_request_id,
                        param_name=param_name,
                        status='pending',
                    ).values('new_value', 'specific_part'))

                    updated = PLCWriteRecord.objects.filter(
                        batch_request_id=batch_request_id,
                        param_name=param_name,
                        status='pending',
                    ).update(
                        status=item_status,
                        acked_at=now,
                        error_message=item_err,
                    )
                    logger.info(
                        'write ack item 更新: batch=%s param=%s status=%s updated=%d',
                        batch_request_id, param_name, item_status, updated,
                    )

                    if item_success and pending_recs:
                        rec = pending_recs[0]
                        try:
                            int_val = int(float(rec['new_value']))
                        except (ValueError, TypeError):
                            int_val = None
                        if int_val is not None:
                            n = PLCLatestData.objects.filter(
                                specific_part=rec['specific_part'],
                                param_name=param_name,
                            ).update(value=int_val, collected_at=now)
                            logger.info(
                                'plc_latest_data 同步: sp=%s param=%s value=%s n=%d',
                                rec['specific_part'], param_name, int_val, n,
                            )
            else:
                # 兼容旧版单字段回执（v0.3.0 legacy，不应再出现，保留防御）
                success = data.get('success', False)
                new_status = 'success' if success else 'failed'
                updated = PLCWriteRecord.objects.filter(
                    request_id=batch_request_id, status='pending'
                ).update(
                    status=new_status,
                    acked_at=now,
                    error_message=data.get('error_message', '') if not success else None,
                )
                logger.info(
                    'write ack legacy 更新: request_id=%s status=%s updated=%d',
                    batch_request_id, new_status, updated,
                )

        except Exception as e:
            logger.error('_handle_write_ack 异常: %s', e, exc_info=True)

    def on_disconnect(self, client, userdata, rc):
        """与MQTT代理断开连接后的回调函数"""
        if rc != 0:
            logger.warning(f"意外断开与MQTT代理的连接，返回代码: {rc}")
        else:
            logger.info("已断开与MQTT代理的连接")

    def on_log(self, client, userdata, level, buf):
        """MQTT日志回调函数"""
        # 可以根据需要调整日志级别
        if level == mqtt.MQTT_LOG_ERR:
            logger.error(f"MQTT错误: {buf}")
        elif level == mqtt.MQTT_LOG_WARNING:
            logger.warning(f"MQTT警告: {buf}")
        elif level == mqtt.MQTT_LOG_INFO:
            logger.info(f"MQTT信息: {buf}")
        elif level == mqtt.MQTT_LOG_DEBUG and settings.DEBUG:
            logger.debug(f"MQTT调试: {buf}")

    def process_message(self, topic, payload, is_general: bool = False):
        """处理接收到的消息并保存到数据库"""
        logger.debug(f"开始处理消息: 主题={topic}, 消息大小={len(str(payload))}字节")

        # FR4/FR5: PLC 写入回执 topic，更新 plc_write_record 状态
        if topic.startswith(self.WRITE_ACK_TOPIC_PREFIX):
            self._handle_write_ack(payload)
            return

        # MOD-MQTT-01: 大屏连通性 topic 独立路由，由 ScreenConnectivityHandler 处理
        if topic == self.SCREEN_CONNECTIVITY_TOPIC:
            try:
                handler = ScreenConnectivityHandler()
                handler.handle(topic, payload)
            except Exception as e:
                logger.error(
                    f"ScreenConnectivityHandler 处理消息时发生错误: {e}", exc_info=True
                )
            return

        # general 消息跳过 ConnectionStatusHandler，节省约 150ms/条
        handlers = self.general_handlers if is_general else self.energy_handlers

        max_retries = 3  # 最大重试次数
        retry_count = 0

        while retry_count <= max_retries:
            try:
                logger.debug(f" 开始处理消息内容: 主题={topic}, 重试次数={retry_count}")

                # 从topic中提取楼栋文件名（如果存在）
                building_file = None
                topic_parts = topic.split('/')
                logger.debug(f"主题解析: 部分数量={len(topic_parts)}, 内容={topic_parts}")

                if len(topic_parts) > 4:
                    building_file = topic_parts[4]  # 假设格式为 /datacollection/plc/to/collector/[building_file]
                    logger.debug(f"从主题提取楼栋文件名: {building_file}")

                # 使用Handler机制处理消息
                for handler in handlers:
                    try:
                        handler.handle(topic, payload, building_file)
                    except Exception as e:
                        logger.error(f"处理器 {handler.__class__.__name__} 处理消息时发生错误: {e}", exc_info=True)

                # 处理成功
                logger.info(f"✅ 消息处理完成: 主题={topic}")
                break  # 成功处理，跳出循环

            except (MySQLdb.OperationalError, MySQLdb.InterfaceError,
                    DjangoOperationalError, ConnectionResetError,
                    ConnectionAbortedError, BrokenPipeError) as e:
                error_msg = str(e)
                logger.error(f"❌ 数据库操作错误: {error_msg}")
                logger.debug(f"当前连接状态: connection_id={id(django_connection)}")
                # 如果是连接已断开的错误，尝试重新连接
                if ('2006' in error_msg \
                        or 'server has gone away' in error_msg.lower() \
                        or 'connection reset by peer' in error_msg.lower()
                        or 'broken pipe' in error_msg.lower()
                        or 'connection aborted' in error_msg.lower()
                        or isinstance(e, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError))):
                    retry_count += 1
                    if retry_count <= max_retries:
                        logger.warning(f"🔄 数据库连接已断开，尝试重新连接并重试消息处理... (重试 {retry_count}/{max_retries})")
                        logger.debug(f"重试前连接状态: connection_id={id(django_connection)}")
                        # 尝试重新连接
                        if self._check_and_reconnect_db(with_diagnostic=False):
                            logger.info("✅ 数据库连接已重新建立，准备重试消息处理")
                            logger.debug(f"重连后连接状态: connection_id={id(django_connection)}")
                            # 等待一小段时间确保连接稳定
                            time.sleep(0.5)
                            continue  # 重试当前消息
                        else:
                            logger.error("❌ 数据库重新连接失败")
                    else:
                        logger.error("❌ 达到最大重试次数，放弃处理此消息")
                else:
                    logger.error("❌ 非连接类数据库错误，不重试")
                break  # 跳出循环

            except Exception as e:
                # 处理其他错误
                logger.error(f"处理消息时发生错误: {e}", exc_info=True)
                break  # 跳出循环

    def _check_and_reconnect_db(self, with_diagnostic=True):
        """检查数据库连接并在需要时重新连接，增强版包含重试机制和完整连接重置"""
        max_reconnect_attempts = 3  # 保持足够的重试次数
        reconnect_delay = 1  # 保持合适的初始重连延迟

        logger.debug(f"开始检查数据库连接状态，当前线程ID: {threading.get_ident()}")
        logger.debug(f"初始连接状态: connection_id={id(django_connection)}")

        def is_connection_valid():
            """更彻底地检查连接有效性，包括实际执行SQL查询"""
            try:
                django_connection.ensure_connection()
                # 执行一个简单的SQL查询来验证连接是否真正可用
                with django_connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    logger.debug(f"连接验证查询结果: {result}")

                    # 获取连接ID信息
                    cursor.execute("SELECT CONNECTION_ID()")
                    connection_id = cursor.fetchone()[0]
                    logger.debug(f"数据库连接ID: {connection_id}")
                logger.info(f"✓ 数据库连接正常 [ID: {id(django_connection)}, DB ID: {connection_id}]")
                return True
            except Exception as e:
                logger.debug(f"连接验证失败: {e}")
                return False

        for attempt in range(max_reconnect_attempts):
            try:
                if is_connection_valid():
                    return True

                logger.error(f"✗ 数据库连接检查失败 (尝试 {attempt+1}/{max_reconnect_attempts})")

                if attempt == max_reconnect_attempts - 1:
                    # 最后一次尝试失败
                    logger.warning("✗ 所有数据库连接检查尝试都失败，准备强制重建连接")
                    break

                # 等待后重试
                wait_time = reconnect_delay * (2 ** attempt)
                logger.debug(f"⏱ 等待 {wait_time} 秒后尝试重新检查数据库连接...")
                time.sleep(wait_time)
            except Exception as e:
                logger.error(f"连接检查尝试中发生错误: {e}")
                if attempt == max_reconnect_attempts - 1:
                    logger.warning("✗ 所有数据库连接检查尝试都失败，准备强制重建连接")
                    break
                wait_time = reconnect_delay * (2 ** attempt)
                logger.debug(f"⏱ 等待 {wait_time} 秒后尝试重新检查数据库连接...")
                time.sleep(wait_time)

        try:
            # 1. 关闭旧连接
            logger.info("🔄 正在关闭旧的数据库连接...")
            old_connection_id = id(django_connection)
            logger.debug(f"旧连接ID: {old_connection_id}")
            django_connection.close()
            logger.info(f"✅ 已关闭旧的数据库连接 [ID: {old_connection_id}]")

            # 2. 清除连接状态，确保完全重置
            if hasattr(django_connection, '_cursor') and django_connection._cursor:
                logger.debug("关闭并重置连接游标...")
                django_connection._cursor.close()
                django_connection._cursor = None
                logger.debug("✅ 游标已重置")

            # 3. 清除连接池中的其他可能失效连接
            if hasattr(django_connection, '_connections'):
                conn_count = len(django_connection._connections)
                django_connection._connections.clear()
                logger.debug(f"✅ 已清除连接池中的 {conn_count} 个连接")

            # 4. 延迟一下，给数据库服务器时间处理连接关闭
            logger.debug("等待数据库服务器处理连接关闭...")
            time.sleep(0.5)

            # 5. 尝试重新建立连接
            logger.info("🔄 正在尝试重新建立数据库连接...")
            django_connection.connect()
            new_connection_id = id(django_connection)
            logger.info(f"✅ 数据库连接已成功重新建立 [新ID: {new_connection_id}]")

            # 6. 验证新连接是否真正可用
            logger.debug("验证新连接有效性...")
            if is_connection_valid():
                logger.info("✅ 新连接验证成功")
            else:
                logger.error("❌ 新连接验证失败")
                return False

            # 7. 可选的诊断功能（仅在调试模式下或显式请求时启用）
            if with_diagnostic and settings.DEBUG:
                try:
                    logger.debug("🔍 正在使用原始MySQLdb连接进行诊断...")
                    db_config = settings.DATABASES['default']

                    direct_conn = MySQLdb.connect(
                        host=db_config['HOST'],
                        port=int(db_config['PORT']) if db_config['PORT'] else 3306,
                        user=db_config['USER'],
                        password=db_config['PASSWORD'],
                        database=db_config['NAME'],
                        charset=db_config.get('OPTIONS', {}).get('charset', 'utf8')
                    )
                    direct_conn.ping()
                    direct_conn.close()
                    logger.debug("✅ 原始MySQLdb连接诊断成功")
                except Exception as diag_error:
                    logger.debug(f"⚠️ 原始MySQLdb连接诊断失败: {diag_error}")

            return True

        except Exception as re_conn_error:
            logger.error(f"✗ 数据库重新连接失败: {re_conn_error}", exc_info=True)

            # 仅在调试模式下进行详细诊断
            if with_diagnostic and settings.DEBUG:
                try:
                    logger.debug("🔍 正在进行详细的数据库连接诊断...")
                    from django.conf import settings
                    db_config = settings.DATABASES['default']

                    direct_conn = MySQLdb.connect(
                        host=db_config['HOST'],
                        port=int(db_config['PORT']) if db_config['PORT'] else 3306,
                        user=db_config['USER'],
                        password=db_config['PASSWORD'],
                        database=db_config['NAME'],
                        charset=db_config.get('OPTIONS', {}).get('charset', 'utf8')
                    )
                    direct_conn.ping()
                    direct_conn.close()
                    logger.debug("✅ 原始MySQLdb连接诊断成功")
                except Exception as diag_error:
                    logger.debug(f"⚠️ 原始MySQLdb连接诊断失败: {diag_error}")
                    logger.error("✗ 数据库连接问题可能与网络、认证或数据库服务器配置有关")

            return False

    def _db_maintenance_thread(self):
        """数据库连接维护线程，定期检查连接可用性"""
        logger.info(f"启动数据库连接维护线程，间隔 {self.db_maintenance_interval} 秒")

        while self.db_maintenance_running:
            try:
                logger.debug("执行定期数据库连接检查...")
                # 执行简单的连接检查
                with django_connection.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                logger.debug(f"定期连接检查结果: {result}")

            except (MySQLdb.OperationalError, MySQLdb.InterfaceError,
                    DjangoOperationalError, ConnectionResetError,
                    ConnectionAbortedError, BrokenPipeError) as e:
                error_msg = str(e)
                logger.error(f"定期数据库连接检查失败: {error_msg}")
                # 尝试重新连接
                logger.warning("🔄 定期检查发现连接断开，尝试重新连接...")
                self._check_and_reconnect_db(with_diagnostic=False)

            except Exception as e:
                logger.error(f"定期数据库连接检查发生未知错误: {e}")

            # 等待下一次检查
            for _ in range(self.db_maintenance_interval):
                if not self.db_maintenance_running:
                    break
                time.sleep(1)

        logger.info("数据库连接维护线程已停止")

    def connect(self):
        """连接到MQTT代理"""
        try:
            logger.info(f"正在连接到MQTT代理: {self.mqtt_broker}:{self.mqtt_port}")

            # 如果启用了TLS，则配置TLS
            if self.tls_enabled:
                logger.info("启用TLS连接")
                # 可以根据需要添加ca_certs、certfile、keyfile等参数
                self.client.tls_set()

            # 连接到MQTT代理
            self.client.connect(self.mqtt_broker, self.mqtt_port, self.keepalive)
            return True
        except Exception as e:
            logger.error(f"连接到MQTT代理失败: {e}")
            return False

    # ------------------------------------------------------------------
    # v0.5.6 新增：ondemand worker 循环及辅助方法（MOD-BE-04）
    # ------------------------------------------------------------------

    def _ondemand_worker_loop(self):
        """Ondemand worker 主循环（串行，1 个线程，OQ-002）。

        - 从 _ondemand_queue 取消息
        - 调用 OndemandPLCLatestDataHandler.handle()（只写 plc_latest_data，不写历史）
        - 完成后发布 done 通知至 /datacollection/plc/ondemand/done/<specific_part>
        """
        close_old_connections()
        django_connection.ensure_connection()
        thread_name = threading.current_thread().name
        logger.info(f"[{thread_name}] Ondemand worker 启动")

        msg_counter = 0
        while not self.stop_event.is_set() or not self._ondemand_queue.empty():
            try:
                topic, payload_bytes, qos = self._ondemand_queue.get(timeout=1)
            except queue.Empty:
                continue

            t_start = time.monotonic()
            try:
                msg_counter += 1
                if msg_counter % _CLOSE_CONN_EVERY_N == 0:
                    close_old_connections()
                django_connection.ensure_connection()

                self._dispatch_ondemand(topic, payload_bytes)
            except Exception as e:
                logger.error(f"[{thread_name}] ondemand 消息处理异常: {e}", exc_info=True)
            finally:
                self._ondemand_queue.task_done()
                elapsed_ms = (time.monotonic() - t_start) * 1000
                logger.info(f"[{thread_name}] ondemand 消息处理完成: topic={topic}, 耗时={elapsed_ms:.1f}ms")

        logger.info(f"[{thread_name}] Ondemand worker 退出")

    def _dispatch_ondemand(self, topic: str, payload_bytes: bytes):
        """解码 payload，调用 ondemand handler，完成后发布 done 通知。"""
        try:
            payload_str = payload_bytes.decode('utf-8')
            payload = self._safe_json_parse(payload_str)
        except Exception as e:
            logger.error(f"[ondemand] 消息解码/解析失败: topic={topic}, error={e}")
            return

        # 调用 OndemandPLCLatestDataHandler（只写 plc_latest_data，不写 device_param_history）
        for handler in self.ondemand_handlers:
            try:
                handler.handle(topic, payload)
            except Exception as e:
                logger.error(f"[ondemand] handler 处理失败: {e}", exc_info=True)

        # 提取 specific_part 并发布 done 通知（QoS=0，OQ-004 决议）
        specific_part = self._extract_specific_part_from_topic(topic, self.ONDEMAND_RESULT_TOPIC_PREFIX)
        if specific_part:
            self._publish_ondemand_done(specific_part, payload)

    def _extract_specific_part_from_topic(self, topic: str, prefix: str) -> str:
        """从 topic 中提取 specific_part（prefix 之后的部分）。"""
        if topic.startswith(prefix):
            return topic[len(prefix):]
        return ''

    def _publish_ondemand_done(self, specific_part: str, payload: dict):
        """发布 done 通知至 /datacollection/plc/ondemand/done/<specific_part>（QoS=0）。"""
        collected_at = self._extract_max_collected_at(payload)
        done_topic = f"{self.ONDEMAND_DONE_TOPIC_PREFIX}{specific_part}"
        done_payload = json.dumps({
            'specific_part': specific_part,
            'collected_at': collected_at or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        })
        try:
            # QoS=0（最多一次），前端 30 秒轮询兜底（OQ-004 决议）
            self.client.publish(done_topic, done_payload, qos=0)
            logger.info(f"[ondemand] done 通知已发布: topic={done_topic}")
        except Exception as e:
            logger.error(f"[ondemand] done 通知发布失败: topic={done_topic}, error={e}")

    def _extract_max_collected_at(self, payload: dict) -> str:
        """从 payload 中提取所有参数 timestamp 的最大值。

        Payload 结构：{device_id: {data: {param: {timestamp: "...", ...}, ...}, ...}}
        """
        max_ts = None
        if not isinstance(payload, dict):
            return max_ts
        for device_info in payload.values():
            if not isinstance(device_info, dict):
                continue
            data = device_info.get('data', {})
            if not isinstance(data, dict):
                continue
            for param_data in data.values():
                if not isinstance(param_data, dict):
                    continue
                ts = param_data.get('timestamp')
                if ts and (max_ts is None or ts > max_ts):
                    max_ts = ts
        return max_ts

    def start(self):
        """启动MQTT客户端循环"""
        try:
            if not self.connect():
                return False

            # 重置停止信号（支持重启场景）
            self.stop_event.clear()

            # 启动 worker 线程（在 paho loop_start 之前，确保 worker 就绪）
            self._worker_threads = []
            for i in range(self._num_energy_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    args=(self._energy_queue, False),
                    name=f"mqtt-energy-worker-{i}",
                    daemon=True,
                )
                t.start()
                self._worker_threads.append(t)
            for i in range(self._num_general_workers):
                t = threading.Thread(
                    target=self._worker_loop,
                    args=(self._general_queue, True),
                    name=f"mqtt-general-worker-{i}",
                    daemon=True,
                )
                t.start()
                self._worker_threads.append(t)
            # v0.5.6: 启动 ondemand worker（1 个，串行）
            for i in range(self._num_ondemand_workers):
                t = threading.Thread(
                    target=self._ondemand_worker_loop,
                    name=f"mqtt-ondemand-worker-{i}",
                    daemon=True,
                )
                t.start()
                self._worker_threads.append(t)
            logger.info(
                f"已启动 {self._num_energy_workers} 个 energy worker + "
                f"{self._num_general_workers} 个 general worker + "
                f"{self._num_ondemand_workers} 个 ondemand worker"
            )

            logger.info("启动MQTT客户端循环")
            # 使用loop_start()在后台线程中运行MQTT客户端
            self.client.loop_start()

            # 启动数据库连接维护线程
            self.db_maintenance_running = True
            self.db_maintenance_thread = threading.Thread(
                target=self._db_maintenance_thread,
                name="db-maintenance",
                daemon=True,
            )
            self.db_maintenance_thread.start()

            return True
        except Exception as e:
            logger.error(f"启动MQTT客户端时发生错误: {e}")
            return False

    def stop(self):
        """停止MQTT客户端（优雅关闭）。

        停止顺序：
        1. 通知 worker 不再接受新消息（stop_event.set）
        2. 停止 paho 网络线程（不再产生新消息入队）
        3. 等待队列中剩余消息全部消费完毕（queue.join，最长 30s）
        4. 等待 worker 线程退出
        5. 停止 db_maintenance_thread
        """
        try:
            logger.info("开始优雅关闭 MQTT 消费者...")

            # 1. 通知 worker 进入"消费完即退出"模式
            self.stop_event.set()
            logger.info("stop_event 已设置，worker 将在队列清空后退出")

            # 2. 停止 paho 网络线程（不再产生新的入队消息）
            logger.info("停止 paho 网络线程...")
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("paho 已停止")

            # 3. 等待三个队列均清空（最长 30s）
            energy_size = self._energy_queue.qsize()
            general_size = self._general_queue.qsize()
            ondemand_size = self._ondemand_queue.qsize()
            if energy_size + general_size + ondemand_size > 0:
                logger.info(
                    f"等待队列消息处理完毕（energy={energy_size}, general={general_size}, "
                    f"ondemand={ondemand_size}，最长 30s）..."
                )
            deadline = time.monotonic() + 30
            while (not self._energy_queue.empty() or not self._general_queue.empty()
                   or not self._ondemand_queue.empty()) and time.monotonic() < deadline:
                time.sleep(0.2)
            remaining = (self._energy_queue.qsize() + self._general_queue.qsize()
                         + self._ondemand_queue.qsize())
            if remaining > 0:
                logger.warning(f"优雅关闭超时(30s)，仍有 {remaining} 条消息未处理，强制退出")
            else:
                logger.info("队列已清空，优雅关闭完成")

            # 4. 等待 worker 线程退出
            for t in self._worker_threads:
                t.join(timeout=5)
                if t.is_alive():
                    logger.warning(f"worker 线程 {t.name} 未在 5s 内退出")
            logger.info("所有 worker 线程已退出")

            # 5. 停止数据库连接维护线程
            logger.info("停止数据库连接维护线程")
            self.db_maintenance_running = False
            if self.db_maintenance_thread:
                self.db_maintenance_thread.join(timeout=5)
                if self.db_maintenance_thread.is_alive():
                    logger.warning("数据库连接维护线程未能在超时内停止")

            logger.info("MQTT 消费者已完全停止")
            return True
        except Exception as e:
            logger.error(f"停止MQTT客户端时发生错误: {e}")
            return False


# 创建全局MQTT客户端实例
mqtt_consumer = MQTTConsumer()


def start_mqtt_consumer():
    """启动MQTT消费者"""
    return mqtt_consumer.start()


def stop_mqtt_consumer():
    """停止MQTT消费者"""
    return mqtt_consumer.stop()
