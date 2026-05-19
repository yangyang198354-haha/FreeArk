"""
PLCWriteSubscriber 单元测试套件 (v0.4.0 批量协议)
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
    },
    'living_room_switch': {
        'db_num': 1,
        'offset': 20,
        'data_type': 'int16',
    },
}


def _make_batch_cmd(request_id='batch-001', specific_part='3-1-7-702',
                    plc_ip='10.0.0.1', items=None):
    if items is None:
        items = [
            {'param_name': 'living_room_temp_setting', 'new_value': '24'},
            {'param_name': 'living_room_switch', 'new_value': '1'},
        ]
    return json.dumps({
        'request_id': request_id,
        'specific_part': specific_part,
        'plc_ip': plc_ip,
        'items': items,
    })


class TestOnCommandBatchPath:

    def test_ut_sub_01_batch_calls_write_plc_for_each_item(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))
        sub._publish_ack = MagicMock()

        sub._on_command('topic', _make_batch_cmd())

        assert sub._write_plc.call_count == 2

    def test_ut_sub_02_incomplete_missing_items_skips(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock()
        sub._publish_ack = MagicMock()

        incomplete = json.dumps({'request_id': 'req-001', 'specific_part': '3-1-7-702', 'plc_ip': '10.0.0.1'})
        sub._on_command('topic', incomplete)

        sub._write_plc.assert_not_called()
        sub._publish_ack.assert_not_called()

    def test_ut_sub_03_unknown_param_in_items_produces_failure_result(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))

        cmd = _make_batch_cmd(items=[
            {'param_name': 'nonexistent_param', 'new_value': '1'},
        ])
        sub._on_command('topic', cmd)

        sub._client.publish.assert_called_once()
        _, body = sub._client.publish.call_args[0][:2]
        assert body['success'] is False
        assert body['items'][0]['success'] is False

    def test_ut_sub_04_idempotent_second_batch_call_skipped(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))
        sub._publish_ack = MagicMock()

        cmd = _make_batch_cmd(request_id='dup-batch')
        sub._on_command('topic', cmd)
        sub._on_command('topic', cmd)

        assert sub._write_plc.call_count == 2  # only first call

    def test_ut_sub_05_all_success_publishes_overall_success(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))

        sub._on_command('topic', _make_batch_cmd())

        sub._client.publish.assert_called_once()
        _, body = sub._client.publish.call_args[0][:2]
        assert body['success'] is True
        assert all(i['success'] for i in body['items'])

    def test_ut_sub_06_partial_failure_publishes_overall_failure(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        call_count = [0]

        def _write_side(plc_ip, db_num, offset, value, data_type):
            call_count[0] += 1
            if call_count[0] == 1:
                return True, None
            return False, 'snap7 连接失败'

        sub._write_plc = MagicMock(side_effect=_write_side)

        sub._on_command('topic', _make_batch_cmd())

        sub._client.publish.assert_called_once()
        _, body = sub._client.publish.call_args[0][:2]
        assert body['success'] is False
        successes = [i['success'] for i in body['items']]
        assert True in successes
        assert False in successes

    def test_ut_sub_07_ack_topic_format(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))

        sub._on_command('topic', _make_batch_cmd(specific_part='3-1-7-702'))

        sub._client.publish.assert_called_once()
        called_topic = sub._client.publish.call_args[0][0]
        assert called_topic == '/datacollection/plc/write/ack/3-1-7-702'

    def test_ut_sub_08_bytes_payload_decoded(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))
        sub._publish_ack = MagicMock()

        payload_bytes = _make_batch_cmd().encode('utf-8')
        sub._on_command('topic', payload_bytes)

        assert sub._write_plc.call_count == 2

    def test_ut_sub_09_ack_body_contains_items_array(self):
        sub = _make_subscriber(SAMPLE_CONFIG)
        sub._write_plc = MagicMock(return_value=(True, None))

        sub._on_command('topic', _make_batch_cmd())

        _, body = sub._client.publish.call_args[0][:2]
        assert 'items' in body
        assert isinstance(body['items'], list)
        assert len(body['items']) == 2
        for item in body['items']:
            assert 'param_name' in item
            assert 'success' in item


class TestPublishAckBody:

    def test_ack_body_contains_required_fields(self):
        sub = _make_subscriber(SAMPLE_CONFIG)

        item_results = [
            {'param_name': 'living_room_temp_setting', 'success': True},
            {'param_name': 'living_room_switch', 'success': True},
        ]
        sub._publish_ack('3-1-7-702', 'batch-001', True, item_results)

        sub._client.publish.assert_called_once()
        topic, body = sub._client.publish.call_args[0][:2]
        assert topic == '/datacollection/plc/write/ack/3-1-7-702'
        assert body['request_id'] == 'batch-001'
        assert body['specific_part'] == '3-1-7-702'
        assert body['success'] is True
        assert 'written_at' in body
        assert 'items' in body
        assert len(body['items']) == 2

    def test_ack_body_failure_contains_error_in_items(self):
        sub = _make_subscriber(SAMPLE_CONFIG)

        item_results = [
            {'param_name': 'living_room_temp_setting', 'success': False, 'error_message': 'timeout'},
        ]
        sub._publish_ack('3-1-7-702', 'batch-001', False, item_results)

        _, body = sub._client.publish.call_args[0][:2]
        assert body['success'] is False
        assert body['items'][0]['error_message'] == 'timeout'
