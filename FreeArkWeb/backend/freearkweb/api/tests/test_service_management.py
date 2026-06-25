"""
服务管理功能测试套件 — Service Management

涵盖阶段：PHASE_07 单元测试 + PHASE_08 集成测试 + PHASE_09 E2E 验收

覆盖需求：
  US-SM-001: 查看服务列表（GET /api/services/list/）
  US-SM-002: 查看服务详情（GET /api/services/<name>/detail/）
  US-SM-003: 执行服务操作（POST /api/services/<name>/action/）
  NFR-SM-001: 白名单安全校验（服务名、操作名）
  NFR-SM-002: 身份认证保护（未登录用户不可访问）

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_service_management \\
        --settings=freearkweb.test_settings --verbosity=2

测试数据库：SQLite in-memory（test_settings.py 强制配置）
systemctl 调用全部通过 unittest.mock.patch 模拟，不依赖真实 systemd。
"""

import subprocess
from unittest.mock import MagicMock, patch, call

from django.test import TestCase, tag
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CustomUser
from api.views import (
    MONITORED_SERVICES,
    _MONITORED_SERVICES_SET,
    _ALLOWED_ACTIONS,
    _get_service_status,
    _get_service_detail,
)


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_user(username="svc_testuser", role="admin"):  # v1.6.0: 服务管理仅 admin，happy-path 默认用 admin
    user = CustomUser.objects.create_user(
        username=username, password="pass1234", role=role
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _make_authed_client(token_key):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token_key}")
    return client


# ---------------------------------------------------------------------------
# PHASE_07: 单元测试
# ---------------------------------------------------------------------------

@tag('unit')
class TC_U_SM_001_WhitelistConstants(TestCase):
    """TC-U-SM-001: 白名单常量完整性验证"""

    def test_monitored_services_is_list(self):
        """MONITORED_SERVICES 是列表，且非空"""
        self.assertIsInstance(MONITORED_SERVICES, list)
        self.assertGreater(len(MONITORED_SERVICES), 0)

    def test_monitored_services_set_matches_list(self):
        """_MONITORED_SERVICES_SET 与 MONITORED_SERVICES 内容一致"""
        self.assertEqual(set(MONITORED_SERVICES), _MONITORED_SERVICES_SET)

    def test_allowed_actions_contains_required(self):
        """_ALLOWED_ACTIONS 包含 start, stop, restart"""
        for action in ('start', 'stop', 'restart'):
            self.assertIn(action, _ALLOWED_ACTIONS)

    def test_known_service_names_in_whitelist(self):
        """已知服务名（freeark-backend 等）在白名单内"""
        expected_services = [
            'freeark-backend',
            'freeark-mqtt-consumer',
            'freeark-daily-usage',
            'freeark-monthly-usage',
        ]
        for svc in expected_services:
            self.assertIn(svc, _MONITORED_SERVICES_SET, f"{svc} 不在白名单中")


@tag('unit')
class TC_U_SM_002_GetServiceStatus(TestCase):
    """TC-U-SM-002: _get_service_status 辅助函数单元测试"""

    def _make_run_result(self, stdout='', returncode=0):
        mock = MagicMock()
        mock.stdout = stdout
        mock.returncode = returncode
        return mock

    def test_returns_active_when_systemctl_outputs_active(self):
        """systemctl is-active 输出 'active' 时返回 'active'"""
        with patch('subprocess.run', return_value=self._make_run_result('active\n')):
            result = _get_service_status('freeark-backend')
        self.assertEqual(result, 'active')

    def test_returns_inactive_when_systemctl_outputs_inactive(self):
        """systemctl is-active 输出 'inactive' 时返回 'inactive'"""
        with patch('subprocess.run', return_value=self._make_run_result('inactive\n')):
            result = _get_service_status('freeark-backend')
        self.assertEqual(result, 'inactive')

    def test_returns_failed_when_systemctl_outputs_failed(self):
        """systemctl is-active 输出 'failed' 时返回 'failed'"""
        with patch('subprocess.run', return_value=self._make_run_result('failed\n')):
            result = _get_service_status('freeark-backend')
        self.assertEqual(result, 'failed')

    def test_returns_unknown_on_exception(self):
        """subprocess.run 抛出异常时返回 'unknown'"""
        with patch('subprocess.run', side_effect=OSError('command not found')):
            result = _get_service_status('freeark-backend')
        self.assertEqual(result, 'unknown')

    def test_returns_unknown_on_timeout(self):
        """subprocess.TimeoutExpired 时返回 'unknown'"""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 5)):
            result = _get_service_status('freeark-backend')
        self.assertEqual(result, 'unknown')

    def test_empty_stdout_returns_unknown(self):
        """stdout 为空字符串时返回 'unknown'"""
        with patch('subprocess.run', return_value=self._make_run_result('')):
            result = _get_service_status('freeark-backend')
        self.assertEqual(result, 'unknown')


@tag('unit')
class TC_U_SM_003_GetServiceDetail(TestCase):
    """TC-U-SM-003: _get_service_detail 辅助函数单元测试"""

    SAMPLE_STATUS_OUTPUT = """\
* freeark-backend.service - FreeArk Backend
     Loaded: loaded (/etc/systemd/system/freeark-backend.service; enabled; vendor preset: enabled)
     Active: active (running) since Fri 2026-05-01 10:00:00 CST; 1h ago
   Main PID: 1234 (python)
      Tasks: 4 (limit: 9257)
     Memory: 45.6M
     CGroup: /system.slice/freeark-backend.service
"""

    def _make_run_result(self, stdout='', stderr='', returncode=0):
        mock = MagicMock()
        mock.stdout = stdout
        mock.stderr = stderr
        mock.returncode = returncode
        return mock

    def test_parses_active_state(self):
        """解析出 active_state=active"""
        with patch('subprocess.run', return_value=self._make_run_result(stdout=self.SAMPLE_STATUS_OUTPUT)):
            detail = _get_service_detail('freeark-backend')
        self.assertEqual(detail['active_state'], 'active')

    def test_parses_sub_state(self):
        """解析出 sub_state=running"""
        with patch('subprocess.run', return_value=self._make_run_result(stdout=self.SAMPLE_STATUS_OUTPUT)):
            detail = _get_service_detail('freeark-backend')
        self.assertEqual(detail['sub_state'], 'running')

    def test_parses_pid(self):
        """解析出 PID=1234"""
        with patch('subprocess.run', return_value=self._make_run_result(stdout=self.SAMPLE_STATUS_OUTPUT)):
            detail = _get_service_detail('freeark-backend')
        self.assertEqual(detail['pid'], 1234)

    def test_parses_memory(self):
        """解析出 memory=45.6M"""
        with patch('subprocess.run', return_value=self._make_run_result(stdout=self.SAMPLE_STATUS_OUTPUT)):
            detail = _get_service_detail('freeark-backend')
        self.assertEqual(detail['memory'], '45.6M')

    def test_raw_output_present(self):
        """raw_output 字段存在且非空"""
        with patch('subprocess.run', return_value=self._make_run_result(stdout=self.SAMPLE_STATUS_OUTPUT)):
            detail = _get_service_detail('freeark-backend')
        self.assertIn('raw_output', detail)
        self.assertTrue(detail['raw_output'])

    def test_raw_output_limited_to_4096(self):
        """raw_output 最多截取 4096 字符"""
        long_output = 'x' * 10000
        with patch('subprocess.run', return_value=self._make_run_result(stdout=long_output)):
            detail = _get_service_detail('freeark-backend')
        self.assertLessEqual(len(detail['raw_output']), 4096)

    def test_timeout_returns_error_dict(self):
        """超时时返回含 error 字段的字典"""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 10)):
            detail = _get_service_detail('freeark-backend')
        self.assertIn('error', detail)
        self.assertIn('超时', detail['error'])

    def test_exception_returns_error_dict(self):
        """其他异常时返回含 error 字段的字典"""
        with patch('subprocess.run', side_effect=RuntimeError('mock error')):
            detail = _get_service_detail('freeark-backend')
        self.assertIn('error', detail)


# ---------------------------------------------------------------------------
# PHASE_08: 集成测试
# ---------------------------------------------------------------------------

@tag('integration')
class TC_I_SM_001_ServiceListAPIAuth(TestCase):
    """TC-I-SM-001: 服务列表 API 认证与权限集成测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user("sm_int_user")

    def test_unauthenticated_returns_401(self):
        """未认证请求 GET /api/services/list/ 返回 401"""
        resp = self.client.get('/api/services/list/')
        self.assertEqual(resp.status_code, 401)

    def test_authenticated_returns_200(self):
        """已认证请求返回 200"""
        client = _make_authed_client(self.token)
        with patch('api.views._get_service_status', return_value='active'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='enabled\n', returncode=0)
            resp = client.get('/api/services/list/')
        self.assertEqual(resp.status_code, 200)

    def test_post_not_allowed_on_list(self):
        """POST 方法不允许，返回 405"""
        client = _make_authed_client(self.token)
        resp = client.post('/api/services/list/', {})
        self.assertEqual(resp.status_code, 405)


@tag('integration')
class TC_I_SM_002_ServiceListAPIResponse(TestCase):
    """TC-I-SM-002: 服务列表 API 响应格式验证"""

    def setUp(self):
        _, self.token = _make_user("sm_resp_user")
        self.client = _make_authed_client(self.token)

    def test_response_success_field(self):
        """响应包含 success=true"""
        with patch('api.views._get_service_status', return_value='active'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='enabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        data = resp.json()
        self.assertTrue(data['success'])

    def test_response_data_is_list(self):
        """响应 data 字段是列表"""
        with patch('api.views._get_service_status', return_value='inactive'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='disabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        data = resp.json()
        self.assertIsInstance(data['data'], list)

    def test_response_data_count_equals_monitored_services(self):
        """响应 data 条数等于 MONITORED_SERVICES 数量"""
        with patch('api.views._get_service_status', return_value='active'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='enabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        data = resp.json()
        self.assertEqual(len(data['data']), len(MONITORED_SERVICES))

    def test_each_item_has_required_fields(self):
        """每条服务记录包含所有必需字段"""
        with patch('api.views._get_service_status', return_value='active'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='enabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        data = resp.json()
        required = {'name', 'active_state', 'is_active', 'enabled'}
        for item in data['data']:
            missing = required - set(item.keys())
            self.assertFalse(missing, f"条目缺少字段: {missing}")

    def test_all_service_names_in_whitelist(self):
        """响应中的所有服务名均在白名单内"""
        with patch('api.views._get_service_status', return_value='active'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='enabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        data = resp.json()
        for item in data['data']:
            self.assertIn(item['name'], _MONITORED_SERVICES_SET)

    def test_is_active_true_when_active_state_active(self):
        """active_state=active 时 is_active=True"""
        with patch('api.views._get_service_status', return_value='active'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='enabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        data = resp.json()
        for item in data['data']:
            self.assertTrue(item['is_active'])

    def test_is_active_false_when_active_state_inactive(self):
        """active_state=inactive 时 is_active=False"""
        with patch('api.views._get_service_status', return_value='inactive'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='disabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        data = resp.json()
        for item in data['data']:
            self.assertFalse(item['is_active'])


@tag('integration')
class TC_I_SM_003_ServiceDetailAPI(TestCase):
    """TC-I-SM-003: 服务详情 API 集成测试"""

    def setUp(self):
        _, self.token = _make_user("sm_detail_user")
        self.client = _make_authed_client(self.token)

    def test_unauthenticated_detail_returns_401(self):
        """未认证请求详情接口返回 401"""
        anon = APIClient()
        resp = anon.get('/api/services/freeark-backend/detail/')
        self.assertEqual(resp.status_code, 401)

    def test_valid_service_detail_returns_200(self):
        """合法服务名返回 200"""
        sample_detail = {
            'active_state': 'active',
            'sub_state': 'running',
            'pid': 1234,
            'memory': '45.6M',
            'raw_output': 'sample output',
        }
        with patch('api.views._get_service_detail', return_value=sample_detail):
            resp = self.client.get('/api/services/freeark-backend/detail/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], 'freeark-backend')
        self.assertIn('detail', data)

    def test_invalid_service_name_returns_400(self):
        """非白名单服务名返回 400"""
        resp = self.client.get('/api/services/malicious-service/detail/')
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('白名单', data['error'])

    def test_detail_contains_required_fields(self):
        """详情响应包含 active_state, sub_state, pid, memory, raw_output"""
        sample_detail = {
            'active_state': 'active',
            'sub_state': 'running',
            'pid': 1234,
            'memory': '45.6M',
            'raw_output': 'sample output',
        }
        with patch('api.views._get_service_detail', return_value=sample_detail):
            resp = self.client.get('/api/services/freeark-backend/detail/')
        data = resp.json()
        for key in ('active_state', 'sub_state', 'pid', 'memory', 'raw_output'):
            self.assertIn(key, data['detail'], f"详情缺少字段: {key}")


@tag('integration')
class TC_I_SM_004_ServiceActionAPI(TestCase):
    """TC-I-SM-004: 服务操作 API 集成测试"""

    def setUp(self):
        _, self.token = _make_user("sm_action_user")
        self.client = _make_authed_client(self.token)

    def _mock_run_success(self, new_stdout='active\n'):
        """构造 subprocess.run 的双重 mock：第一次（sudo systemctl）成功，第二次（is-active）返回 new_stdout"""
        first_call = MagicMock(returncode=0, stdout='', stderr='')
        second_call = MagicMock(returncode=0, stdout=new_stdout, stderr='')
        return [first_call, second_call]

    def test_unauthenticated_action_returns_401(self):
        """未认证用户操作接口返回 401"""
        anon = APIClient()
        resp = anon.post('/api/services/freeark-backend/action/', {'action': 'restart'}, format='json')
        self.assertEqual(resp.status_code, 401)

    def test_invalid_service_name_returns_400(self):
        """非白名单服务名返回 400"""
        resp = self.client.post(
            '/api/services/evil-service/action/', {'action': 'start'}, format='json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    def test_invalid_action_returns_400(self):
        """非法操作名返回 400"""
        resp = self.client.post(
            '/api/services/freeark-backend/action/', {'action': 'kill'}, format='json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    def test_empty_action_returns_400(self):
        """action 为空时返回 400"""
        resp = self.client.post(
            '/api/services/freeark-backend/action/', {'action': ''}, format='json'
        )
        self.assertEqual(resp.status_code, 400)

    def test_start_action_succeeds(self):
        """start 操作成功，返回 200 且 success=true"""
        side_effects = self._mock_run_success('active\n')
        with patch('subprocess.run', side_effect=side_effects):
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'start'}, format='json'
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['new_status'], 'active')

    def test_stop_action_succeeds(self):
        """stop 操作成功，new_status=inactive"""
        side_effects = self._mock_run_success('inactive\n')
        with patch('subprocess.run', side_effect=side_effects):
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'stop'}, format='json'
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['new_status'], 'inactive')

    def test_restart_action_succeeds(self):
        """restart 操作成功，new_status=active"""
        side_effects = self._mock_run_success('active\n')
        with patch('subprocess.run', side_effect=side_effects):
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'restart'}, format='json'
            )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])

    def test_systemctl_failure_returns_500(self):
        """systemctl 返回非零 returncode 时，返回 500"""
        mock_fail = MagicMock(returncode=1, stdout='', stderr='Failed to start service: Permission denied')
        with patch('subprocess.run', return_value=mock_fail):
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'start'}, format='json'
            )
        self.assertEqual(resp.status_code, 500)
        self.assertFalse(resp.json()['success'])

    def test_systemctl_timeout_returns_504(self):
        """subprocess.TimeoutExpired 返回 504"""
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('cmd', 30)):
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'restart'}, format='json'
            )
        self.assertEqual(resp.status_code, 504)
        self.assertFalse(resp.json()['success'])
        self.assertIn('超时', resp.json()['error'])

    def test_sudo_is_called_with_correct_args(self):
        """sudo systemctl <action> <service> 以正确参数被调用"""
        side_effects = self._mock_run_success('active\n')
        with patch('subprocess.run', side_effect=side_effects) as mock_run:
            self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'restart'}, format='json'
            )
        first_call_args = mock_run.call_args_list[0]
        cmd = first_call_args[0][0]
        self.assertEqual(cmd, ['sudo', 'systemctl', 'restart', 'freeark-backend'])

    def test_status_action_is_rejected(self):
        """action=status 不允许通过操作接口（应走 detail 接口），返回 400"""
        resp = self.client.post(
            '/api/services/freeark-backend/action/', {'action': 'status'}, format='json'
        )
        self.assertEqual(resp.status_code, 400)


@tag('integration')
class TC_I_SM_005_SecurityInjection(TestCase):
    """TC-I-SM-005: 命令注入安全测试"""

    def setUp(self):
        _, self.token = _make_user("sm_security_user")
        self.client = _make_authed_client(self.token)

    def test_service_name_with_shell_injection_rejected(self):
        """服务名含 shell 注入字符被白名单拒绝（400）"""
        dangerous_names = [
            'freeark-backend; rm -rf /',
            'freeark-backend && shutdown -h now',
            '../etc/passwd',
            'freeark-backend`id`',
        ]
        for name in dangerous_names:
            from urllib.parse import quote
            resp = self.client.get(f'/api/services/{quote(name)}/detail/')
            # URL 路由本身可能返回 404（含斜杠的 name），或白名单拦截返回 400
            self.assertIn(
                resp.status_code, (400, 404),
                f"注入服务名 '{name}' 应被拒绝，实际状态码: {resp.status_code}",
            )

    def test_action_injection_rejected(self):
        """action 字段含注入内容被白名单拒绝"""
        dangerous_actions = [
            'start; rm -rf /',
            '$(id)',
            'start && shutdown',
        ]
        for action in dangerous_actions:
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': action}, format='json'
            )
            self.assertEqual(resp.status_code, 400, f"注入 action '{action}' 应被拒绝")

    def test_whitelist_service_name_not_injectable(self):
        """合法白名单服务名仅含安全字符（自验）。

        允许点号 `.`（.timer 等单元后缀需要）；点号非 shell 元字符，且 subprocess 以
        argv 形式调用（无 shell），故不构成注入风险。仍排除空格 / 分号 / 反引号 / 斜杠等。
        """
        import re
        safe_pattern = re.compile(r'^[a-zA-Z0-9_.\-]+$')
        for name in MONITORED_SERVICES:
            self.assertTrue(
                safe_pattern.match(name),
                f"服务名 '{name}' 含非法字符",
            )


# ---------------------------------------------------------------------------
# PHASE_09: E2E 验收测试
# ---------------------------------------------------------------------------

@tag('e2e')
class TC_E2E_SM_US001_ServiceList(TestCase):
    """TC-E2E-SM-US001: US-SM-001 — 已登录用户可查看服务列表"""

    def setUp(self):
        _, self.token = _make_user("sm_e2e_001")
        self.client = _make_authed_client(self.token)

    def test_service_list_url_accessible(self):
        """GET /api/services/list/ 路由已注册且可访问（200）"""
        with patch('api.views._get_service_status', return_value='active'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='enabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        self.assertEqual(resp.status_code, 200)

    def test_all_monitored_services_appear_in_list(self):
        """响应中包含所有受监控服务名"""
        with patch('api.views._get_service_status', return_value='active'), \
             patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(stdout='enabled\n', returncode=0)
            resp = self.client.get('/api/services/list/')
        data = resp.json()
        names = {item['name'] for item in data['data']}
        for expected in MONITORED_SERVICES:
            self.assertIn(expected, names, f"服务 {expected} 未出现在列表中")


@tag('e2e')
class TC_E2E_SM_US002_ServiceDetail(TestCase):
    """TC-E2E-SM-US002: US-SM-002 — 已登录用户可查看服务详情"""

    def setUp(self):
        _, self.token = _make_user("sm_e2e_002")
        self.client = _make_authed_client(self.token)

    def test_detail_returns_raw_output(self):
        """详情接口返回 raw_output 字段"""
        sample = {
            'active_state': 'active', 'sub_state': 'running',
            'pid': 999, 'memory': '30.0M', 'raw_output': 'Active: active (running)',
        }
        with patch('api.views._get_service_detail', return_value=sample):
            resp = self.client.get('/api/services/freeark-backend/detail/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('raw_output', resp.json()['detail'])

    def test_detail_for_each_monitored_service(self):
        """每个受监控服务都可以正常调用详情接口"""
        sample = {
            'active_state': 'inactive', 'sub_state': 'dead',
            'pid': None, 'memory': None, 'raw_output': '',
        }
        for service in MONITORED_SERVICES:
            with patch('api.views._get_service_detail', return_value=sample):
                resp = self.client.get(f'/api/services/{service}/detail/')
            self.assertEqual(resp.status_code, 200, f"服务 {service} 详情接口应返回 200")


@tag('e2e')
class TC_E2E_SM_US003_ServiceAction(TestCase):
    """TC-E2E-SM-US003: US-SM-003 — 已登录用户可执行服务操作"""

    def setUp(self):
        _, self.token = _make_user("sm_e2e_003")
        self.client = _make_authed_client(self.token)

    def _mock_action_success(self, new_state='active'):
        success_run = MagicMock(returncode=0, stdout='', stderr='')
        status_run = MagicMock(returncode=0, stdout=f'{new_state}\n', stderr='')
        return [success_run, status_run]

    def test_start_reflects_in_new_status(self):
        """start 操作后 new_status 反映最新状态"""
        with patch('subprocess.run', side_effect=self._mock_action_success('active')):
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'start'}, format='json'
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['new_status'], 'active')

    def test_stop_reflects_in_new_status(self):
        """stop 操作后 new_status=inactive"""
        with patch('subprocess.run', side_effect=self._mock_action_success('inactive')):
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'stop'}, format='json'
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['new_status'], 'inactive')

    def test_restart_reflects_in_new_status(self):
        """restart 操作后 new_status=active"""
        with patch('subprocess.run', side_effect=self._mock_action_success('active')):
            resp = self.client.post(
                '/api/services/freeark-backend/action/', {'action': 'restart'}, format='json'
            )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['new_status'], 'active')

    def test_action_response_contains_message(self):
        """操作成功响应包含 message 字段"""
        with patch('subprocess.run', side_effect=self._mock_action_success()):
            resp = self.client.post(
                '/api/services/freeark-mqtt-consumer/action/', {'action': 'restart'}, format='json'
            )
        data = resp.json()
        self.assertIn('message', data)
        self.assertIn('freeark-mqtt-consumer', data['message'])

    def test_unauthenticated_cannot_execute_action(self):
        """未登录用户不能执行任何服务操作（NFR-SM-002）"""
        anon = APIClient()
        resp = anon.post(
            '/api/services/freeark-backend/action/', {'action': 'restart'}, format='json'
        )
        self.assertEqual(resp.status_code, 401)


@tag('e2e')
class TC_E2E_SM_NFR_AdminOnlyWrite(TestCase):
    """TC-E2E-SM-NFR: v1.6.0 服务管理仅 admin——operator/普通业主不可操作。"""

    def test_operator_cannot_call_action(self):
        """v1.6.0 (OQ-01)：运维人员（role=operator）不能调用服务操作接口，返回 403"""
        _, token = _make_user("sm_operator_user", role="operator")
        client = _make_authed_client(token)

        # 权限在视图执行前拦截，subprocess 不会被调用，断言 403 即可
        resp = client.post(
            '/api/services/freeark-backend/action/', {'action': 'restart'}, format='json'
        )
        self.assertEqual(resp.status_code, 403)

    def test_user_cannot_call_action(self):
        """v1.6.0：普通业主（role=user）不能调用服务操作接口，返回 403（中间件拦截）"""
        _, token = _make_user("sm_owner_user", role="user")
        client = _make_authed_client(token)
        resp = client.post(
            '/api/services/freeark-backend/action/', {'action': 'restart'}, format='json'
        )
        self.assertEqual(resp.status_code, 403)

    def test_admin_user_can_call_action(self):
        """管理员用户（role=admin）可调用服务操作接口"""
        _, token = _make_user("sm_admin_user", role="admin")
        client = _make_authed_client(token)

        success_run = MagicMock(returncode=0, stdout='', stderr='')
        status_run = MagicMock(returncode=0, stdout='active\n', stderr='')
        with patch('subprocess.run', side_effect=[success_run, status_run]):
            resp = client.post(
                '/api/services/freeark-backend/action/', {'action': 'start'}, format='json'
            )
        self.assertEqual(resp.status_code, 200)
