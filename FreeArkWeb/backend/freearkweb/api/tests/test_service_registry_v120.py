"""
test_service_registry_v120.py — v1.2.0 服务注册表与看板完整化

覆盖：
  UT-REG-001  白名单全量纳管：16 个 .service + 4 个 .timer = 20 个单元（Pi 实测权威）
  UT-REG-002  此前漏掉的关键服务（fault-consumer/condensation-consumer/inspection-agent
              + cleanup/netwatch/wifi-watchdog + timers）均已纳入；保留全部既有项（含 plc-cleanup）
  UT-REG-003  _get_service_enabled 解析 enabled/disabled/static/unknown/异常/超时
  UT-DASH-001 /api/dashboard/services/ 每项含 enabled 字段（供前端四态显示）
  UT-DASH-002 dashboard_services 的 is_active 仍由 is-active 决定，enabled 独立呈现

注：systemctl 调用全部用 unittest.mock.patch 模拟，不依赖真实 systemd。
运行：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_service_registry_v120 \\
        --settings=freearkweb.test_settings --verbosity=2
"""

import subprocess
from unittest.mock import MagicMock, patch

from django.test import TestCase, tag
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CustomUser
from api.views import (
    MONITORED_SERVICES,
    _MONITORED_SERVICES_SET,
    _get_service_enabled,
)


def _make_authed_client(username="reg_v120_user"):
    user = CustomUser.objects.create_user(username=username, password="pass1234", role="operator")
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def _run_result(stdout='', returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m


# 本期决议的全量清单（Pi `systemctl list-unit-files 'freeark-*'` 实测）
EXPECTED_SERVICES = {
    'freeark-backend', 'freeark-mqtt-consumer', 'freeark-fault-consumer',
    'freeark-condensation-consumer', 'freeark-screen-heartbeat', 'freeark-daily-usage',
    'freeark-monthly-usage', 'freeark-plc-connection-monitor', 'freeark-task-scheduler',
    'freeark-inspection-agent', 'freeark-dph-cleanup', 'freeark-plc-cleanup',
    'freeark-fault-cleanup', 'freeark-condensation-cleanup', 'freeark-netwatch',
    'freeark-wifi-watchdog',
}
EXPECTED_TIMERS = {
    'freeark-fault-cleanup.timer', 'freeark-condensation-cleanup.timer',
    'freeark-netwatch.timer', 'freeark-wifi-watchdog.timer',
}
# 此前白名单缺失、本期补入的关键服务（含两个在跑的事件源）
NEWLY_ADDED = {
    'freeark-fault-consumer', 'freeark-condensation-consumer', 'freeark-inspection-agent',
    'freeark-fault-cleanup', 'freeark-condensation-cleanup', 'freeark-netwatch',
    'freeark-wifi-watchdog',
    'freeark-fault-cleanup.timer', 'freeark-condensation-cleanup.timer',
    'freeark-netwatch.timer', 'freeark-wifi-watchdog.timer',
}


@tag('unit')
class WhitelistCompletenessTest(TestCase):
    """UT-REG-001/002: 白名单全量纳管。"""

    def test_total_count_20(self):
        # 16 .service + 4 .timer = 20，且无重复
        self.assertEqual(len(MONITORED_SERVICES), 20)
        self.assertEqual(len(MONITORED_SERVICES), len(set(MONITORED_SERVICES)),
                         "白名单存在重复项")

    def test_all_expected_services_present(self):
        missing = (EXPECTED_SERVICES | EXPECTED_TIMERS) - _MONITORED_SERVICES_SET
        self.assertEqual(missing, set(), f"白名单缺失: {missing}")

    def test_newly_added_services_present(self):
        for name in NEWLY_ADDED:
            self.assertIn(name, _MONITORED_SERVICES_SET, f"{name} 未纳入白名单")

    def test_existing_services_retained(self):
        # 既有 9 项必须保留（含 plc-cleanup：disabled 但仍存在，非失效）
        for name in ('freeark-backend', 'freeark-mqtt-consumer', 'freeark-screen-heartbeat',
                     'freeark-daily-usage', 'freeark-monthly-usage', 'freeark-plc-cleanup',
                     'freeark-dph-cleanup', 'freeark-plc-connection-monitor',
                     'freeark-task-scheduler'):
            self.assertIn(name, _MONITORED_SERVICES_SET, f"既有服务 {name} 被误删")

    def test_no_non_freeark_services(self):
        # 不纳入 openclaw-gateway（用户服务）/ redis-server（apt 服务）
        for name in MONITORED_SERVICES:
            self.assertTrue(name.startswith('freeark-'), f"非 freeark-* 服务混入: {name}")
        self.assertNotIn('openclaw-gateway', _MONITORED_SERVICES_SET)
        self.assertNotIn('redis-server', _MONITORED_SERVICES_SET)

    def test_set_matches_list(self):
        self.assertEqual(set(MONITORED_SERVICES), _MONITORED_SERVICES_SET)


@tag('unit')
class GetServiceEnabledTest(TestCase):
    """UT-REG-003: _get_service_enabled 解析各种 is-enabled 输出。"""

    def test_enabled(self):
        with patch('subprocess.run', return_value=_run_result('enabled\n')):
            self.assertEqual(_get_service_enabled('freeark-backend'), 'enabled')

    def test_disabled(self):
        # disabled/static 时 systemctl 退出码非零，但 stdout 仍有状态字符串
        with patch('subprocess.run', return_value=_run_result('disabled\n', returncode=1)):
            self.assertEqual(_get_service_enabled('freeark-inspection-agent'), 'disabled')

    def test_static(self):
        with patch('subprocess.run', return_value=_run_result('static\n', returncode=1)):
            self.assertEqual(_get_service_enabled('freeark-fault-cleanup'), 'static')

    def test_empty_returns_unknown(self):
        with patch('subprocess.run', return_value=_run_result('')):
            self.assertEqual(_get_service_enabled('freeark-backend'), 'unknown')

    def test_exception_returns_unknown(self):
        with patch('subprocess.run', side_effect=OSError('not found')):
            self.assertEqual(_get_service_enabled('freeark-backend'), 'unknown')

    def test_timeout_returns_unknown(self):
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 5)):
            self.assertEqual(_get_service_enabled('freeark-backend'), 'unknown')


@tag('integration')
class DashboardServicesEnabledTest(TestCase):
    """UT-DASH-001/002: 看板服务接口暴露 enabled 字段（供四态显示）。"""

    def setUp(self):
        self.client = _make_authed_client("dash_v120_user")

    def test_each_item_has_enabled_field(self):
        with patch('api.views._get_service_status', return_value='active'), \
             patch('api.views._get_service_enabled', return_value='enabled'):
            resp = self.client.get('/api/dashboard/services/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(len(data['data']), len(MONITORED_SERVICES))
        for item in data['data']:
            self.assertIn('enabled', item)
            self.assertIn('status', item)
            self.assertIn('is_active', item)

    def test_is_active_independent_of_enabled(self):
        # inactive + static（定时服务正常待机）：is_active=False 但 enabled=static 可被前端识别
        with patch('api.views._get_service_status', return_value='inactive'), \
             patch('api.views._get_service_enabled', return_value='static'):
            resp = self.client.get('/api/dashboard/services/')
        data = resp.json()
        for item in data['data']:
            self.assertFalse(item['is_active'])
            self.assertEqual(item['enabled'], 'static')

    def test_disabled_service_reported(self):
        # inactive + disabled（如 inspection-agent 主动停用）
        with patch('api.views._get_service_status', return_value='inactive'), \
             patch('api.views._get_service_enabled', return_value='disabled'):
            resp = self.client.get('/api/dashboard/services/')
        data = resp.json()
        for item in data['data']:
            self.assertEqual(item['enabled'], 'disabled')
            self.assertFalse(item['is_active'])
