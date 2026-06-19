"""
设备参数设置功能 — 单元测试套件
覆盖: PLCWriteRecord 模型 / 序列化器 / _is_writable / _handle_write_ack

运行:
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_device_settings --settings=freearkweb.test_settings --verbosity=2
"""
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from django.utils import timezone
from rest_framework.authtoken.models import Token

from api.models import PLCWriteRecord
from api.serializers_device_settings import (
    PLCWriteRecordSerializer,
    DeviceSettingsBatchWriteSerializer,
)
from api.views_device_settings import _is_writable, _normalize_select_values


def _make_record(**kwargs):
    defaults = dict(
        request_id=str(uuid.uuid4()),
        specific_part='3-1-7-702',
        param_name='living_room_temp_setting',
        old_value='22',
        new_value='24',
        operator='admin',
        status='pending',
    )
    defaults.update(kwargs)
    return PLCWriteRecord.objects.create(**defaults)


@tag('unit')
class PLCWriteRecordModelTests(TestCase):

    def test_ut_m_01_default_status_pending(self):
        rec = PLCWriteRecord.objects.create(
            request_id=str(uuid.uuid4()),
            specific_part='3-1-7-702',
            param_name='living_room_temp_setting',
            old_value='22',
            new_value='24',
            operator='admin',
        )
        self.assertEqual(rec.status, 'pending')

    def test_ut_m_02_request_id_unique(self):
        from django.db import IntegrityError
        rid = str(uuid.uuid4())
        PLCWriteRecord.objects.create(
            request_id=rid,
            specific_part='3-1-7-702',
            param_name='living_room_temp_setting',
            old_value='',
            new_value='24',
            operator='admin',
        )
        with self.assertRaises(IntegrityError):
            PLCWriteRecord.objects.create(
                request_id=rid,
                specific_part='3-1-7-702',
                param_name='living_room_temp_setting',
                old_value='',
                new_value='25',
                operator='admin',
            )

    def test_ut_m_03_str_method(self):
        rid = str(uuid.uuid4())
        rec = PLCWriteRecord.objects.create(
            request_id=rid,
            specific_part='3-1-7-702',
            param_name='living_room_temp_setting',
            old_value='',
            new_value='24',
            operator='admin',
        )
        s = str(rec)
        self.assertIn(rid, s)
        self.assertIn('3-1-7-702', s)
        self.assertIn('living_room_temp_setting', s)
        self.assertIn('pending', s)

    def test_ut_m_04_status_choices(self):
        for st in ('pending', 'success', 'failed', 'timeout'):
            rec = PLCWriteRecord.objects.create(
                request_id=str(uuid.uuid4()),
                specific_part='3-1-7-702',
                param_name='living_room_temp_setting',
                old_value='',
                new_value='24',
                operator='admin',
                status=st,
            )
            self.assertEqual(rec.status, st)

    def test_ut_m_05_acked_at_nullable_and_updatable(self):
        rec = _make_record()
        self.assertIsNone(rec.acked_at)
        now = timezone.now()
        rec.acked_at = now
        rec.save()
        rec.refresh_from_db()
        self.assertIsNotNone(rec.acked_at)


@tag('unit')
class PLCWriteRecordSerializerTests(TestCase):

    def test_ut_s_01_serializes_all_fields(self):
        rec = _make_record()
        data = PLCWriteRecordSerializer(rec).data
        expected_fields = {
            'id', 'request_id', 'batch_request_id', 'specific_part', 'param_name',
            'old_value', 'new_value', 'operator', 'status',
            'error_message', 'created_at', 'acked_at',
        }
        self.assertEqual(set(data.keys()), expected_fields)

    def test_ut_s_02_batch_write_serializer_valid(self):
        ser = DeviceSettingsBatchWriteSerializer(data={
            'specific_part': '3-1-7-702',
            'items': [
                {'param_name': 'living_room_temp_setting', 'new_value': '24'},
                {'param_name': 'living_room_switch', 'new_value': '1'},
            ],
        })
        self.assertTrue(ser.is_valid(), ser.errors)

    def test_ut_s_03_rejects_empty_specific_part(self):
        ser = DeviceSettingsBatchWriteSerializer(data={
            'specific_part': '',
            'items': [{'param_name': 'living_room_temp_setting', 'new_value': '24'}],
        })
        self.assertFalse(ser.is_valid())
        self.assertIn('specific_part', ser.errors)

    def test_ut_s_04_rejects_empty_items(self):
        ser = DeviceSettingsBatchWriteSerializer(data={
            'specific_part': '3-1-7-702',
            'items': [],
        })
        self.assertFalse(ser.is_valid())
        self.assertIn('items', ser.errors)

    def test_ut_s_05_rejects_too_long_new_value(self):
        ser = DeviceSettingsBatchWriteSerializer(data={
            'specific_part': '3-1-7-702',
            'items': [{'param_name': 'living_room_temp_setting', 'new_value': 'x' * 51}],
        })
        self.assertFalse(ser.is_valid())


@tag('unit')
class NormalizeSelectValuesTests(TestCase):

    def test_ut_norm_01_array_passthrough(self):
        raw = '[{"value": 0, "label": "关"}, {"value": 1, "label": "开"}]'
        result = _normalize_select_values(raw)
        import json
        parsed = json.loads(result)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 2)

    def test_ut_norm_02_object_converted_to_array(self):
        raw = '{"0": "关", "1": "开"}'
        result = _normalize_select_values(raw)
        import json
        parsed = json.loads(result)
        self.assertIsInstance(parsed, list)
        self.assertEqual(len(parsed), 2)
        keys = {str(item['value']) for item in parsed}
        self.assertIn('0', keys)
        self.assertIn('1', keys)

    def test_ut_norm_03_empty_string_returns_empty_array(self):
        self.assertEqual(_normalize_select_values(''), '[]')

    def test_ut_norm_04_invalid_json_returns_empty_array(self):
        self.assertEqual(_normalize_select_values('not json'), '[]')


@tag('unit')
class IsWritableTests(TestCase):

    def test_ut_w_01_temp_setting_writable(self):
        self.assertTrue(_is_writable('living_room_temp_setting'))

    def test_ut_w_02_switch_writable(self):
        self.assertTrue(_is_writable('panel_1_switch'))

    def test_ut_w_03_temperature_readonly(self):
        self.assertFalse(_is_writable('living_room_temperature'))

    def test_ut_w_04_humidity_readonly(self):
        self.assertFalse(_is_writable('living_room_humidity'))

    def test_ut_w_05_dew_point_setting_readonly(self):
        self.assertFalse(_is_writable('living_room_dew_point_setting'))

    def test_ut_w_06_error_readonly(self):
        self.assertFalse(_is_writable('panel_1_error'))

    def test_ut_w_07_alert_readonly(self):
        self.assertFalse(_is_writable('panel_1_alert'))

    def test_ut_w_08_unknown_suffix_readonly(self):
        self.assertFalse(_is_writable('living_room_unknown_field'))


@tag('unit')
class HandleWriteAckTests(TestCase):

    def _get_consumer(self):
        from api.mqtt_consumer import MQTTConsumer
        consumer = MQTTConsumer.__new__(MQTTConsumer)
        return consumer

    def _make_batch_record(self, batch_request_id, param_name='living_room_temp_setting', status='pending'):
        return PLCWriteRecord.objects.create(
            request_id=str(uuid.uuid4()),
            batch_request_id=batch_request_id,
            specific_part='3-1-7-702',
            param_name=param_name,
            old_value='22',
            new_value='24',
            operator='admin',
            status=status,
        )

    def test_ut_ack_01_batch_items_success_updates_status(self):
        batch_id = str(uuid.uuid4())
        rec1 = self._make_batch_record(batch_id, 'living_room_temp_setting')
        rec2 = self._make_batch_record(batch_id, 'living_room_switch')
        consumer = self._get_consumer()
        import json
        payload = json.dumps({
            'request_id': batch_id,
            'success': True,
            'items': [
                {'param_name': 'living_room_temp_setting', 'success': True},
                {'param_name': 'living_room_switch', 'success': True},
            ],
        })
        consumer._handle_write_ack(payload)
        rec1.refresh_from_db()
        rec2.refresh_from_db()
        self.assertEqual(rec1.status, 'success')
        self.assertEqual(rec2.status, 'success')
        self.assertIsNotNone(rec1.acked_at)

    def test_ut_ack_02_batch_partial_failure_updates_correctly(self):
        batch_id = str(uuid.uuid4())
        rec1 = self._make_batch_record(batch_id, 'living_room_temp_setting')
        rec2 = self._make_batch_record(batch_id, 'living_room_switch')
        consumer = self._get_consumer()
        import json
        payload = json.dumps({
            'request_id': batch_id,
            'success': False,
            'items': [
                {'param_name': 'living_room_temp_setting', 'success': True},
                {'param_name': 'living_room_switch', 'success': False, 'error_message': 'snap7 失败'},
            ],
        })
        consumer._handle_write_ack(payload)
        rec1.refresh_from_db()
        rec2.refresh_from_db()
        self.assertEqual(rec1.status, 'success')
        self.assertEqual(rec2.status, 'failed')
        self.assertEqual(rec2.error_message, 'snap7 失败')

    def test_ut_ack_03_missing_request_id_silently_skipped(self):
        rec = _make_record(status='pending')
        consumer = self._get_consumer()
        import json
        payload = json.dumps({'success': True, 'items': []})
        consumer._handle_write_ack(payload)
        rec.refresh_from_db()
        self.assertEqual(rec.status, 'pending')

    def test_ut_ack_04_idempotent_non_pending_not_updated(self):
        batch_id = str(uuid.uuid4())
        rec = self._make_batch_record(batch_id, status='success')
        consumer = self._get_consumer()
        import json
        payload = json.dumps({
            'request_id': batch_id,
            'success': False,
            'items': [{'param_name': 'living_room_temp_setting', 'success': False}],
        })
        consumer._handle_write_ack(payload)
        rec.refresh_from_db()
        self.assertEqual(rec.status, 'success')

    def test_ut_ack_05_bytes_payload_decoded(self):
        batch_id = str(uuid.uuid4())
        rec = self._make_batch_record(batch_id, 'living_room_temp_setting')
        consumer = self._get_consumer()
        import json
        payload = json.dumps({
            'request_id': batch_id,
            'success': True,
            'items': [{'param_name': 'living_room_temp_setting', 'success': True}],
        }).encode('utf-8')
        consumer._handle_write_ack(payload)
        rec.refresh_from_db()
        self.assertEqual(rec.status, 'success')
