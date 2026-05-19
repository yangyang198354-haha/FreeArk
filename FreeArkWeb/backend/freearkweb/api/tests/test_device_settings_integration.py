"""
设备参数设置功能 — 集成测试套件
覆盖: DRF 路由 / Django ORM + SQLite / 真实序列化器

运行:
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_device_settings_integration --settings=freearkweb.test_settings --verbosity=2
"""
import json
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import (
    CustomUser,
    DeviceAttrDef,
    DeviceConfig,
    OwnerInfo,
    PLCLatestData,
    PLCWriteRecord,
)


def _make_user(username='testadmin', role='admin'):
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


def _make_device_config(param_name, sub_type='main_thermostat', is_active=True, display_name=None):
    return DeviceConfig.objects.create(
        param_name=param_name,
        display_name=display_name or param_name,
        group='hvac',
        sub_type=sub_type,
        group_display='暖通',
        sub_type_display='主温控器',
        is_active=is_active,
    )


def _make_attr_def(attr_tag, attr_value_type=2, product_code='hvac_001'):
    return DeviceAttrDef.objects.create(
        product_code=product_code,
        attr_tag=attr_tag,
        attr_value_type=attr_value_type,
        attr_constraint=0,
        num_value_json='{"min":16,"max":30,"step":1}',
        select_values_json='',
    )


def _make_latest(specific_part, param_name, value=22):
    return PLCLatestData.objects.create(
        specific_part=specific_part,
        param_name=param_name,
        value=value,
        building='3',
        unit='1',
        room_number='702',
    )


class GetParamsTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

    def test_it_params_01_returns_grouped_params(self):
        _make_device_config('living_room_temp_setting')
        _make_latest('3-1-7-702', 'living_room_temp_setting', 22)
        resp = self.client.get('/api/device-settings/params/3-1-7-702/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('groups', data)
        self.assertGreater(len(data['groups']), 0)

    def test_it_params_02_current_value_null_when_no_latest(self):
        _make_device_config('living_room_temp_setting')
        resp = self.client.get('/api/device-settings/params/3-1-7-702/')
        self.assertEqual(resp.status_code, 200)
        params = resp.json()['groups'][0]['params']
        param = next(p for p in params if p['param_name'] == 'living_room_temp_setting')
        self.assertIsNone(param['current_value'])

    def test_it_params_03_readonly_excluded_p5(self):
        _make_device_config('living_room_temp_setting')
        _make_device_config('living_room_temperature')
        resp = self.client.get('/api/device-settings/params/3-1-7-702/')
        self.assertEqual(resp.status_code, 200)
        all_param_names = [p['param_name'] for g in resp.json()['groups'] for p in g['params']]
        self.assertIn('living_room_temp_setting', all_param_names)
        # P5: 只读参数不返回
        self.assertNotIn('living_room_temperature', all_param_names)

    def test_it_params_04_unauthenticated_returns_401(self):
        anon = APIClient()
        resp = anon.get('/api/device-settings/params/3-1-7-702/')
        self.assertEqual(resp.status_code, 401)

    def test_it_params_05_inactive_configs_excluded(self):
        _make_device_config('living_room_temp_setting', is_active=True)
        _make_device_config('hidden_switch', is_active=False)
        resp = self.client.get('/api/device-settings/params/3-1-7-702/')
        self.assertEqual(resp.status_code, 200)
        all_param_names = [
            p['param_name']
            for g in resp.json()['groups']
            for p in g['params']
        ]
        self.assertNotIn('hidden_switch', all_param_names)

    def test_it_params_06_attr_def_fields_present(self):
        _make_device_config('living_room_temp_setting')
        _make_attr_def('living_room_temp_setting')
        resp = self.client.get('/api/device-settings/params/3-1-7-702/')
        self.assertEqual(resp.status_code, 200)
        params = resp.json()['groups'][0]['params']
        param = next(p for p in params if p['param_name'] == 'living_room_temp_setting')
        self.assertIn('attr_value_type', param)
        self.assertIn('num_value_json', param)
        self.assertIn('select_values_json', param)
        self.assertIn('value_options', param)
        self.assertIn('display_value', param)
        self.assertEqual(param['attr_value_type'], 2)

    def test_it_params_07_switch_value_options_returned(self):
        _make_device_config('living_room_switch')
        resp = self.client.get('/api/device-settings/params/3-1-7-702/')
        self.assertEqual(resp.status_code, 200)
        params = resp.json()['groups'][0]['params']
        param = next(p for p in params if p['param_name'] == 'living_room_switch')
        self.assertIsInstance(param['value_options'], list)
        self.assertGreater(len(param['value_options']), 0)

    def test_it_params_08_select_values_object_normalized_to_array(self):
        _make_device_config('living_room_temp_setting')
        import json as _json
        DeviceAttrDef.objects.create(
            product_code='test_001',
            attr_tag='living_room_temp_setting',
            attr_value_type=1,
            attr_constraint=0,
            select_values_json=_json.dumps({"0": "关", "1": "开"}),
        )
        resp = self.client.get('/api/device-settings/params/3-1-7-702/')
        self.assertEqual(resp.status_code, 200)
        params = resp.json()['groups'][0]['params']
        param = next(p for p in params if p['param_name'] == 'living_room_temp_setting')
        parsed = _json.loads(param['select_values_json'])
        self.assertIsInstance(parsed, list)


class PostWriteTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')
        _make_owner()

    def _batch_payload(self, items=None):
        return {
            'specific_part': '3-1-7-702',
            'items': items or [
                {'param_name': 'living_room_temp_setting', 'new_value': '24'},
                {'param_name': 'living_room_switch', 'new_value': '1'},
            ],
        }

    @patch('api.views_device_settings._get_mqtt_client')
    def test_it_write_01_valid_batch_returns_202_and_creates_records(self, mock_get_client):
        mock_result = MagicMock()
        mock_result.rc = 0
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.publish.return_value = mock_result
        mock_get_client.return_value = mock_client

        resp = self.client.post('/api/device-settings/write/', self._batch_payload(), format='json')
        self.assertEqual(resp.status_code, 202)
        data = resp.json()
        self.assertIn('batch_request_id', data)
        self.assertEqual(data['item_count'], 2)
        self.assertEqual(data['status'], 'pending')
        batch_id = data['batch_request_id']
        self.assertEqual(PLCWriteRecord.objects.filter(batch_request_id=batch_id).count(), 2)

    def test_it_write_02_readonly_param_returns_400(self):
        resp = self.client.post('/api/device-settings/write/', {
            'specific_part': '3-1-7-702',
            'items': [{'param_name': 'living_room_temperature', 'new_value': '25'}],
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_it_write_03_unknown_specific_part_returns_404(self):
        resp = self.client.post('/api/device-settings/write/', {
            'specific_part': '9-9-9-999',
            'items': [{'param_name': 'living_room_temp_setting', 'new_value': '24'}],
        }, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_it_write_04_missing_items_returns_400(self):
        resp = self.client.post('/api/device-settings/write/', {
            'specific_part': '3-1-7-702',
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_it_write_04b_empty_items_returns_400(self):
        resp = self.client.post('/api/device-settings/write/', {
            'specific_part': '3-1-7-702',
            'items': [],
        }, format='json')
        self.assertEqual(resp.status_code, 400)

    @patch('api.views_device_settings._get_mqtt_client')
    def test_it_write_05_mqtt_failure_returns_503_and_records_failed(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.is_connected.return_value = True
        mock_client.publish.side_effect = RuntimeError('broker down')
        mock_get_client.return_value = mock_client

        resp = self.client.post('/api/device-settings/write/', self._batch_payload(), format='json')
        self.assertEqual(resp.status_code, 503)
        failed_count = PLCWriteRecord.objects.filter(status='failed').count()
        self.assertGreater(failed_count, 0)

    def test_it_write_06_unauthenticated_returns_401(self):
        anon = APIClient()
        resp = anon.post('/api/device-settings/write/', self._batch_payload(), format='json')
        self.assertEqual(resp.status_code, 401)


class GetRecordsTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

    def _make_record(self, specific_part='3-1-7-702', operator='admin', status='pending'):
        return PLCWriteRecord.objects.create(
            request_id=str(uuid.uuid4()),
            batch_request_id=str(uuid.uuid4()),
            specific_part=specific_part,
            param_name='living_room_temp_setting',
            old_value='22',
            new_value='24',
            operator=operator,
            status=status,
        )

    def test_it_records_01_returns_all_records_paginated(self):
        self._make_record()
        self._make_record()
        resp = self.client.get('/api/device-settings/records/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('count', data)
        self.assertEqual(data['count'], 2)

    def test_it_records_02_filter_by_specific_part(self):
        self._make_record(specific_part='3-1-7-702')
        self._make_record(specific_part='3-1-7-703')
        resp = self.client.get('/api/device-settings/records/?specific_part=3-1-7-702')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)

    def test_it_records_03_filter_by_status(self):
        self._make_record(status='pending')
        self._make_record(status='success')
        resp = self.client.get('/api/device-settings/records/?status=success')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['status'], 'success')

    def test_it_records_04_filter_by_operator(self):
        self._make_record(operator='alice')
        self._make_record(operator='bob')
        resp = self.client.get('/api/device-settings/records/?operator=alice')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['count'], 1)

    def test_it_records_05_filter_by_time_range(self):
        self._make_record()
        resp = self.client.get('/api/device-settings/records/?start_time=2000-01-01&end_time=2099-12-31')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreater(data['count'], 0)

    def test_it_records_06_page_size_param(self):
        for _ in range(5):
            self._make_record()
        resp = self.client.get('/api/device-settings/records/?page_size=2')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data['results']), 2)

    def test_it_records_07_unauthenticated_returns_401(self):
        anon = APIClient()
        resp = anon.get('/api/device-settings/records/')
        self.assertEqual(resp.status_code, 401)
