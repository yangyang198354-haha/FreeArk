import datetime
import json
import os
import sys
import threading
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datacollection.log_config_manager import get_logger
from datacollection.mqtt_client import MQTTClient
from datacollection.multi_thread_plc_handler import PLCReadWriter

logger = get_logger('plc_write_subscriber')

COMMAND_TOPIC = '/datacollection/plc/write/command/#'
ACK_TOPIC_TEMPLATE = '/datacollection/plc/write/ack/{specific_part}'


def _load_plc_config():
    possible = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'plc_config.json'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resource', 'plc_config.json'),
        os.path.join(os.getcwd(), 'plc_config.json'),
    ]
    for p in possible:
        p = os.path.normpath(p)
        if os.path.exists(p):
            with open(p, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            logger.info('加载 plc_config.json: %s', p)
            return cfg.get('parameters', {})
    logger.warning('未找到 plc_config.json，PLCWriteSubscriber 参数映射为空')
    return {}


class PLCWriteSubscriber:
    def __init__(self, mqtt_broker: str, mqtt_port: int):
        self._broker = mqtt_broker
        self._port = mqtt_port
        self._plc_config = _load_plc_config()
        self._processed: set = set()
        self._lock = threading.Lock()
        self._client: MQTTClient | None = None

    def start(self):
        t = threading.Thread(target=self._run, daemon=True, name='PLCWriteSubscriber')
        t.start()
        logger.info('PLCWriteSubscriber 线程已启动')

    def _run(self):
        # 连接重试：初次连不上不再让线程直接 return 而永久死掉（历史教训：
        # broker 启动时刻不可用 → 线程退出 → 写命令订阅彻底缺失、写操作永久 pending）。
        # 连上后 paho loop_start 维持自动重连，叠加 MQTTClient._on_connect 的订阅恢复，
        # 之后任何 broker 中断都能自愈，无需重启服务。
        while True:
            self._client = MQTTClient(
                host=self._broker,
                port=self._port,
                client_id=f'plc-write-sub-{os.getpid()}',
            )
            if self._client.connect():
                break
            logger.error('PLCWriteSubscriber: 无法连接到 MQTT broker %s:%s，10s 后重试',
                         self._broker, self._port)
            try:
                self._client.disconnect()  # 停掉失败实例的 loop 线程，避免泄漏
            except Exception:
                pass
            time.sleep(10)
        self._client.subscribe(COMMAND_TOPIC, qos=1, callback=self._on_command)
        logger.info('PLCWriteSubscriber 已连接并订阅 %s (broker=%s:%s)',
                    COMMAND_TOPIC, self._broker, self._port)
        # v0.4.3 Bug D: MQTTClient.connect() 内部已经 loop_start() 启动后台 paho 线程。
        # 再调用 loop_forever() 会触发"双 loop"冲突（paho _thread is not None 时立即返回/raise），
        # 导致 _on_message 回调无法触发，订阅消息全部丢失。
        # 删除多余的 loop_forever，依赖 loop_start 的 daemon thread 持续处理消息。

    def _on_command(self, topic: str, payload):
        try:
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode('utf-8')
            if isinstance(payload, str):
                cmd = json.loads(payload)
            else:
                cmd = payload

            request_id = cmd.get('request_id', '')
            specific_part = cmd.get('specific_part', '')
            plc_ip = cmd.get('plc_ip', '')
            items = cmd.get('items')

            # P2 诊断：实锤消息到达
            item_count = len(items) if isinstance(items, list) else 0
            logger.info(
                '收到写命令: request_id=%s specific_part=%s plc_ip=%s items=%d topic=%s',
                request_id, specific_part, plc_ip, item_count, topic,
            )

            if not all([request_id, specific_part, plc_ip]):
                logger.warning('write command 字段不完整（缺 request_id/specific_part/plc_ip），跳过: %s', cmd)
                return

            if not isinstance(items, list) or len(items) == 0:
                logger.warning('write command 缺少 items 或 items 为空，跳过: %s', cmd)
                return

            with self._lock:
                if request_id in self._processed:
                    logger.info('幂等跳过已处理 request_id: %s', request_id)
                    return

            results = []
            for item in items:
                param_name = item.get('param_name', '')
                new_value = item.get('new_value')

                if not param_name or new_value is None:
                    logger.warning('items 中某项字段不完整，跳过: %s', item)
                    results.append({
                        'param_name': param_name,
                        'success': False,
                        'error_message': 'item 字段不完整',
                    })
                    continue

                if param_name not in self._plc_config:
                    logger.warning('param_name %s 不在 plc_config，发布失败结果', param_name)
                    results.append({
                        'param_name': param_name,
                        'success': False,
                        'error_message': f'param_name {param_name} 未在 plc_config.json 中定义',
                    })
                    continue

                cfg = self._plc_config[param_name]
                db_num = cfg['db_num']
                offset = cfg['offset']
                data_type = cfg['data_type']

                ok, err_msg = self._write_plc(plc_ip, db_num, offset, new_value, data_type)
                result_entry = {'param_name': param_name, 'success': ok}
                if not ok and err_msg:
                    result_entry['error_message'] = err_msg
                results.append(result_entry)

            overall_success = all(r['success'] for r in results)
            self._publish_ack(specific_part, request_id, overall_success, results)

            with self._lock:
                self._processed.add(request_id)

        except Exception as e:
            logger.error('PLCWriteSubscriber._on_command 异常: %s', e, exc_info=True)

    def _write_plc(self, plc_ip: str, db_num: int, offset: int, value, data_type: str):
        try:
            logger.info(
                '_write_plc: ip=%s db=%s offset=%s val=%s type=%s',
                plc_ip, db_num, offset, value, data_type,
            )
            reader = PLCReadWriter(plc_ip)
            if not reader.connect():
                return False, f'snap7 连接 {plc_ip} 失败'
            try:
                success, message = reader.write_db_data(db_num, offset, value, data_type)
                return success, message if not success else None
            finally:
                reader.disconnect()
        except Exception as e:
            return False, str(e)

    def _publish_ack(self, specific_part: str, request_id: str, overall_success: bool,
                     item_results: list):
        topic = ACK_TOPIC_TEMPLATE.format(specific_part=specific_part)
        body = {
            'request_id': request_id,
            'specific_part': specific_part,
            'success': overall_success,
            'written_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'items': item_results,
        }
        if self._client:
            self._client.publish(topic, body, qos=1)
            logger.info(
                '发布写入回执: topic=%s overall_success=%s item_count=%d',
                topic, overall_success, len(item_results),
            )
