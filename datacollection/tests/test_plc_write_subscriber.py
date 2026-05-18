"""
PLCWriteSubscriber 单元测试套件
全量 mock: snap7 / paho MQTT / log_config_manager

运行（从项目根目录）:
    python -m pytest datacollection/tests/test_plc_write_subscriber.py -v
"""
import json
import sys
import os
import threading
from unittest.mock import MagicMock, patch, call

import pytest

FREEARK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if FREEARK_ROOT not in sys.path:
    sys.path.insert(0, FREEARK_ROOT)

from datacollection.plc_write_subscriber import PLCWriteSubscriber


def _make_subscriber(plc_config=None):
    """构造 PLCWriteSubscriber via __new__，跳过 __init__，直接注入依赖。"""
    sub = PLCWriteSubscriber.__new__(PLCWriteSubscriber)
    sub._broker = 'localhost'
    sub._port = 1883
    sub._plc_config = plc_config or {}
    sub._processed = set()
    sub._lock = threading.Lock()
    sub._client = MagicMock()
    return sub


SAMPLE_CONFIG = {
    'living_room_temp_setting': {
        'db_num': 1,
        'offset': 10,
        'data_type': 'int',
    }
}


def _make_cmd(request_id='req-001', specific_part='3-1-7-702',
              plc_ip='10.0.0.1', param_name='living_room_temp_setting', new_value='24'):
    return json.dumps({
        'request_id': request_id,
        'specific_part': specific_part,
        'plc_ip': plc_ip,
        'param_name': param_name,
        'new_value': new_value,
    })


class TestOnCommandNormalPath:

    def test_ut_sub_01_valid_command_calls_write_plc(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))
        sub._publish_ack = MagicMock()

        sub._on_command('topic', _make_cmd())

        sub._write_plc.assert_called_once()
        args = sub._write_plc.call_args[0]
        assert args[0] == '10.0.0.1'
        assert args[1] == 1
        assert args[2] == 10
        assert args[3] == '24'
        assert args[4] == 'int'

    def test_ut_sub_02_incomplete_fields_skips_write(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock()
        sub._publish_ack = MagicMock()

        incomplete = json.dumps({'request_id': 'req-001', 'specific_part': '3-1-7-702'})
        sub._on_command('topic', incomplete)

        sub._write_plc.assert_not_called()

    def test_ut_sub_03_unknown_param_publishes_failure_ack(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock()
        sub._publish_ack = MagicMock()

        cmd = _make_cmd(param_name='nonexistent_param')
        sub._on_command('topic', cmd)

        sub._write_plc.assert_not_called()
        sub._publish_ack.assert_called_once()
        call_kwargs = sub._publish_ack.call_args
        assert call_kwargs[1]['success'] is False

    def test_ut_sub_04_idempotent_second_call_skipped(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))
        sub._publish_ack = MagicMock()

        cmd = _make_cmd(request_id='dup-req')
        sub._on_command('topic', cmd)
        sub._on_command('topic', cmd)

        assert sub._write_plc.call_count == 1

    def test_ut_sub_05_write_plc_success_publishes_success_ack(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))
        sub._publish_ack = MagicMock()

        sub._on_command('topic', _make_cmd())

        sub._publish_ack.assert_called_once()
        assert sub._publish_ack.call_args[1]['success'] is True

    def test_ut_sub_06_write_plc_failure_publishes_failure_ack(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(False, 'snap7 连接失败'))
        sub._publish_ack = MagicMock()

        sub._on_command('topic', _make_cmd())

        sub._publish_ack.assert_called_once()
        kw = sub._publish_ack.call_args[1]
        assert kw['success'] is False
        assert 'snap7' in kw['error_message']

    def test_ut_sub_07_publish_ack_topic_format(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))

        sub._on_command('topic', _make_cmd(specific_part='3-1-7-702'))

        sub._client.publish.assert_called_once()
        called_topic = sub._client.publish.call_args[0][0]
        assert called_topic == '/datacollection/plc/write/ack/3-1-7-702'

    def test_ut_sub_08_bytes_payload_decoded_and_processed(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))
        sub._publish_ack = MagicMock()

        payload_bytes = _make_cmd().encode('utf-8')
        sub._on_command('topic', payload_bytes)

        sub._write_plc.assert_called_once()
        args = sub._write_plc.call_args[0]
        assert args[0] == '10.0.0.1'
        assert args[1] == 1
        assert args[2] == 10
        assert args[3] == '24'
        assert args[4] == 'int'


class TestPublishAckBody:

    def test_ack_body_contains_required_fields(self):
        sub = _make_subscriber(SAMPLE_CONFIG)

        sub._publish_ack('3-1-7-702', 'req-001', success=True, value='24')

        sub._client.publish.assert_called_once()
        topic, body = sub._client.publish.call_args[0][:2]
        assert topic == '/datacollection/plc/write/ack/3-1-7-702'
        assert body['request_id'] == 'req-001'
        assert body['specific_part'] == '3-1-7-702'
        assert body['success'] is True
        assert 'written_at' in body
        assert body['value'] == '24'

    def test_ack_body_failure_contains_error_message(self):
        sub = _make_subscriber(SAMPLE_CONFIG)

        sub._publish_ack('3-1-7-702', 'req-001', success=False, error_message='timeout')

        sub._client.publish.assert_called_once()
        _, body = sub._client.publish.call_args[0][:2]
        assert body['success'] is False
        assert body['error_message'] == 'timeout'
        assert 'value' not in body
