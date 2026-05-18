import datetime
import json
import os
import sys
import threading

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
        self._client = MQTTClient(
            host=self._broker,
            port=self._port,
            client_id=f'plc-write-sub-{os.getpid()}',
        )
        if not self._client.connect():
            logger.error('PLCWriteSubscriber: 无法连接到 MQTT broker %s:%s', self._broker, self._port)
            return
        self._client.subscribe(COMMAND_TOPIC, qos=1, callback=self._on_command)
        logger.info('PLCWriteSubscriber 已订阅 %s', COMMAND_TOPIC)
        self._client.client.loop_forever()

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
            param_name = cmd.get('param_name', '')
            new_value = cmd.get('new_value')

            if not all([request_id, specific_part, plc_ip, param_name, new_value is not None]):
                logger.warning('write command 字段不完整，跳过: %s', cmd)
                return

            with self._lock:
                if request_id in self._processed:
                    logger.info('幂等跳过已处理 request_id: %s', request_id)
                    return

            if param_name not in self._plc_config:
                logger.warning('param_name %s 不在 plc_config，发布失败回执', param_name)
                self._publish_ack(specific_part, request_id, success=False,
                                  error_message=f'param_name {param_name} 未在 plc_config.json 中定义')
                return

            cfg = self._plc_config[param_name]
            db_num = cfg['db_num']
            offset = cfg['offset']
            data_type = cfg['data_type']

            ok, err_msg = self._write_plc(plc_ip, db_num, offset, new_value, data_type)
            self._publish_ack(specific_part, request_id, success=ok,
                              value=new_value, error_message=err_msg)

            with self._lock:
                self._processed.add(request_id)

        except Exception as e:
            logger.error('PLCWriteSubscriber._on_command 异常: %s', e, exc_info=True)

    def _write_plc(self, plc_ip: str, db_num: int, offset: int, value, data_type: str):
        try:
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

    def _publish_ack(self, specific_part: str, request_id: str, success: bool,
                     value=None, error_message: str = None):
        topic = ACK_TOPIC_TEMPLATE.format(specific_part=specific_part)
        body = {
            'request_id': request_id,
            'specific_part': specific_part,
            'success': success,
            'written_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        if success and value is not None:
            body['value'] = value
        if not success and error_message:
            body['error_message'] = error_message
        if self._client:
            self._client.publish(topic, body, qos=1)
            logger.info('发布写入回执: topic=%s success=%s', topic, success)
