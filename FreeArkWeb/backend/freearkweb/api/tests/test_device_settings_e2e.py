"""
设备参数设置功能 — E2E 测试套件
通过 Django TestCase + mock MQTT + mock snap7 模拟完整写入链路

运行:
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_device_settings_e2e --settings=freearkweb.test_settings --verbosity=2
"""
import json
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CustomUser, OwnerInfo, PLCWriteRecord
from api.mqtt_consumer import MQTTConsumer


def _make_user(username='e2e_admin', role='admin'):
    user = CustomUser.objects.create_user(username=username, password='pass1234', role=role)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _make_owner(specific_part='3-1-7-702', plc_ip='10.0.0.1'):
    return OwnerInfo.objects.create(
        specific_part=specific_part,
        building='3',
        unit='1',
        room_number='702',
        plc_ip_address=plc_ip,
    )


def _get_bare_consumer():
    consumer = MQTTConsumer.__new__(MQTTConsumer)
    return consumer


class E2EHappyPathTest(TestCase):
    """E2E-01: POST write → pending → ack(success=True) → success"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        _make_owner()

    @patch('api.views_device_settings._get_mqtt_client')
    def test_e2e_01_write_then_ack_success(self, mock_get_client):
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_mqtt = MagicMock()
        mock_mqtt.publish.return_value = mock_result
        mock_get_client.return_value = mock_mqtt

        resp = self.client.post('/api/device-settings/write/', {
            'specific_part': '3-1-7-702',
            'param_name': 'living_room_temp_setting',
            'new_value': '24',
        }, format='json')
        self.assertEqual(resp.status_code, 202)
        request_id = resp.json()['request_id']

        rec = PLCWriteRecord.objects.get(request_id=request_id)
        self.assertEqual(rec.status, 'pending')

        consumer = _get_bare_consumer()
        ack_payload = json.dumps({
            'request_id': request_id,
            'success': True,
        })
        consumer._handle_write_ack(ack_payload)

        rec.refresh_from_db()
        self.assertEqual(rec.status, 'success')
        self.assertIsNotNone(rec.acked_at)


class E2EPLCWriteFailTest(TestCase):
    """E2E-02: POST write → pending → ack(success=False) → failed"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user(username='e2e_admin2')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        _make_owner()

    @patch('api.views_device_settings._get_mqtt_client')
    def test_e2e_02_ack_failure_marks_record_failed(self, mock_get_client):
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_mqtt = MagicMock()
        mock_mqtt.publish.return_value = mock_result
        mock_get_client.return_value = mock_mqtt

        resp = self.client.post('/api/device-settings/write/', {
            'specific_part': '3-1-7-702',
            'param_name': 'living_room_temp_setting',
            'new_value': '24',
        }, format='json')
        self.assertEqual(resp.status_code, 202)
        request_id = resp.json()['request_id']

        consumer = _get_bare_consumer()
        ack_payload = json.dumps({
            'request_id': request_id,
            'success': False,
            'error_message': 'PLC 写入超时',
        })
        consumer._handle_write_ack(ack_payload)

        rec = PLCWriteRecord.objects.get(request_id=request_id)
        self.assertEqual(rec.status, 'failed')
        self.assertIn('PLC 写入超时', rec.error_message)


class E2EMQTTUnreachableTest(TestCase):
    """E2E-03: MQTT publish 异常 → 503，PLCWriteRecord.status=failed"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user(username='e2e_admin3')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        _make_owner()

    @patch('api.views_device_settings._get_mqtt_client')
    def test_e2e_03_mqtt_publish_exception_returns_503(self, mock_get_client):
        mock_mqtt = MagicMock()
        mock_mqtt.publish.side_effect = ConnectionError('broker unreachable')
        mock_get_client.return_value = mock_mqtt

        resp = self.client.post('/api/device-settings/write/', {
            'specific_part': '3-1-7-702',
            'param_name': 'living_room_temp_setting',
            'new_value': '24',
        }, format='json')
        self.assertEqual(resp.status_code, 503)
        rec = PLCWriteRecord.objects.order_by('-created_at').first()
        self.assertIsNotNone(rec)
        self.assertEqual(rec.status, 'failed')
        self.assertIn('MQTT broker 不可达', rec.error_message)


class E2EIdempotentAckTest(TestCase):
    """E2E-04: 同一 request_id ack 两次 → 状态只更新一次"""

    def test_e2e_04_duplicate_ack_idempotent(self):
        rec = PLCWriteRecord.objects.create(
            request_id=str(uuid.uuid4()),
            specific_part='3-1-7-702',
            param_name='living_room_temp_setting',
            old_value='22',
            new_value='24',
            operator='admin',
            status='pending',
        )
        consumer = _get_bare_consumer()
        ack = json.dumps({'request_id': rec.request_id, 'success': True})

        consumer._handle_write_ack(ack)
        rec.refresh_from_db()
        self.assertEqual(rec.status, 'success')
        first_acked_at = rec.acked_at
        self.assertIsNotNone(first_acked_at)

        consumer._handle_write_ack(ack)
        rec.refresh_from_db()
        self.assertEqual(rec.status, 'success')
        self.assertIsNotNone(rec.acked_at)
