"""
心跳 Broker 配置功能测试套件 — v0.5.9

覆盖需求：
  US-HBC-001: 查看当前心跳 Broker 配置
  US-HBC-002: 编辑并保存心跳 Broker 配置
  US-HBC-003: 协议切换（mqtt vs wss）
  US-HBC-004: 重启服务生效
  US-HBC-005: 配置错误时的回退与可观测性
  US-HBC-006: 权限校验
  REQ-FUNC-001~006, REQ-NFUNC-001~005

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_heartbeat_broker_config \\
        --settings=freearkweb.test_settings --verbosity=2

测试数据库：SQLite in-memory（test_settings.py 强制配置）
subprocess / 文件 I/O 通过 unittest.mock 模拟，不依赖真实文件系统和 systemd。
"""

import json
import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch, call

from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CustomUser
import api.views_heartbeat_config as hbc_views


# ---------------------------------------------------------------------------
# 测试辅助
# ---------------------------------------------------------------------------

def _make_user(username='hbc_testuser', role='user', suffix=''):
    user = CustomUser.objects.create_user(
        username=username + suffix, password='pass1234', role=role
    )
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


_VALID_CONFIG = {
    'protocol': 'mqtt',
    'host': '47.117.41.184',
    'port': 11883,
    'path': '/mqtt',
    'username': 'admin',
    'password': 'public',
    'topic': '/screen/upload/screen/to/cloud/#',
    'client_id': 'freeark-screen-heartbeat',
    'keepalive': 60,
}

_WSS_CONFIG = {
    'protocol': 'wss',
    'host': 'www.ttqingjiao.site',
    'port': 8084,
    'path': '/mqtt',
    'username': 'admin',
    'password': 'secret',
    'topic': '/screen/upload/screen/to/cloud/#',
    'client_id': 'freeark-screen-heartbeat',
    'keepalive': 60,
}


# ===========================================================================
# 1. 单元测试：工具函数
# ===========================================================================

class TestReadHbcConfig(TestCase):
    """_read_hbc_config() 单元测试"""

    def test_reads_existing_file(self):
        """正常读取已存在的配置文件"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            json.dump(_VALID_CONFIG, f)
            tmp_path = f.name
        try:
            with patch.object(hbc_views, '_HBC_CONFIG_PATH', tmp_path):
                result = hbc_views._read_hbc_config()
            self.assertEqual(result['host'], '47.117.41.184')
            self.assertEqual(result['port'], 11883)
            self.assertEqual(result['protocol'], 'mqtt')
        finally:
            os.unlink(tmp_path)

    def test_returns_default_when_file_missing(self):
        """文件不存在时返回默认配置"""
        with patch.object(hbc_views, '_HBC_CONFIG_PATH', '/nonexistent/path.json'):
            result = hbc_views._read_hbc_config()
        self.assertEqual(result['host'], '47.117.41.184')
        self.assertEqual(result['port'], 11883)
        self.assertEqual(result['protocol'], 'mqtt')

    def test_returns_default_on_json_decode_error(self):
        """JSON 解析失败时返回默认配置"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            f.write('NOT VALID JSON {{{')
            tmp_path = f.name
        try:
            with patch.object(hbc_views, '_HBC_CONFIG_PATH', tmp_path):
                result = hbc_views._read_hbc_config()
            self.assertEqual(result['protocol'], 'mqtt')
        finally:
            os.unlink(tmp_path)


class TestWriteHbcConfig(TestCase):
    """_write_hbc_config() 单元测试"""

    def test_writes_and_reads_back(self):
        """写入后可正确读回"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'heartbeat_broker_config.json')
            with patch.object(hbc_views, '_HBC_CONFIG_PATH', config_path):
                hbc_views._write_hbc_config(_VALID_CONFIG)
                with open(config_path, encoding='utf-8') as f:
                    loaded = json.load(f)
            self.assertEqual(loaded['host'], '47.117.41.184')
            self.assertEqual(loaded['protocol'], 'mqtt')

    def test_atomic_write_no_tmp_left_on_success(self):
        """成功写入后临时文件应被删除"""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'heartbeat_broker_config.json')
            with patch.object(hbc_views, '_HBC_CONFIG_PATH', config_path):
                hbc_views._write_hbc_config(_VALID_CONFIG)
            self.assertFalse(os.path.exists(config_path + '.tmp'))
            self.assertTrue(os.path.exists(config_path))

    def test_utf8_encoding(self):
        """文件内容应为 UTF-8 编码"""
        cfg = dict(_VALID_CONFIG)
        cfg['client_id'] = '测试客户端'
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'heartbeat_broker_config.json')
            with patch.object(hbc_views, '_HBC_CONFIG_PATH', config_path):
                hbc_views._write_hbc_config(cfg)
            with open(config_path, encoding='utf-8') as f:
                text = f.read()
            self.assertIn('测试客户端', text)


class TestHostPatternValidation(TestCase):
    """host 字段正则校验单元测试 (REQ-NFUNC-001)"""

    def _match(self, host):
        return bool(hbc_views._HOST_PATTERN.match(host))

    # 合法值
    def test_valid_ipv4(self):
        self.assertTrue(self._match('47.117.41.184'))

    def test_valid_ipv4_localhost_style(self):
        self.assertTrue(self._match('192.168.1.1'))

    def test_valid_domain(self):
        self.assertTrue(self._match('www.ttqingjiao.site'))

    def test_valid_subdomain(self):
        self.assertTrue(self._match('broker.example.com'))

    def test_valid_single_label_tld(self):
        self.assertTrue(self._match('example.io'))

    # 非法值（注入防御）
    def test_invalid_shell_injection(self):
        self.assertFalse(self._match('example.com; rm -rf /'))

    def test_invalid_ampersand(self):
        self.assertFalse(self._match('example.com&whoami'))

    def test_invalid_backtick(self):
        self.assertFalse(self._match('`hostname`'))

    def test_invalid_spaces(self):
        self.assertFalse(self._match('exam ple.com'))

    def test_invalid_empty(self):
        self.assertFalse(self._match(''))

    def test_invalid_path_traversal(self):
        self.assertFalse(self._match('../etc/passwd'))


class TestPasswordPreservation(TestCase):
    """OQ-004: password 空字符串时保留原值的逻辑"""

    def test_empty_password_preserves_original(self):
        """PUT 请求中 password='' 时，最终配置中 password 应为文件中原值"""
        original_config = dict(_VALID_CONFIG)
        original_config['password'] = 'original_secret'

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'heartbeat_broker_config.json')
            # 写入初始配置
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(original_config, f)

            with patch.object(hbc_views, '_HBC_CONFIG_PATH', config_path):
                current = hbc_views._read_hbc_config()
            # 模拟 PUT 请求中 password = ''
            password_input = ''
            password = password_input if password_input else current.get('password', '')
        self.assertEqual(password, 'original_secret')

    def test_nonempty_password_overwrites(self):
        """PUT 请求中 password='newpass' 时，最终配置中 password 应被覆盖"""
        original_config = dict(_VALID_CONFIG)
        original_config['password'] = 'original_secret'

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, 'heartbeat_broker_config.json')
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(original_config, f)

            with patch.object(hbc_views, '_HBC_CONFIG_PATH', config_path):
                current = hbc_views._read_hbc_config()
            password_input = 'newpass'
            password = password_input if password_input else current.get('password', '')
        self.assertEqual(password, 'newpass')


class TestRestartService(TestCase):
    """_restart_heartbeat_service() 单元测试"""

    @patch('api.views_heartbeat_config.subprocess.run')
    def test_success_returns_true(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='')
        ok, msg = hbc_views._restart_heartbeat_service()
        self.assertTrue(ok)
        mock_run.assert_called_once_with(
            ['sudo', 'systemctl', 'restart', 'freeark-screen-heartbeat'],
            capture_output=True, text=True, timeout=30,
        )

    @patch('api.views_heartbeat_config.subprocess.run')
    def test_nonzero_returncode_returns_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr='Service failed', stdout='')
        ok, msg = hbc_views._restart_heartbeat_service()
        self.assertFalse(ok)
        self.assertIn('Service failed', msg)

    @patch('api.views_heartbeat_config.subprocess.run')
    def test_timeout_returns_false(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=['sudo', 'systemctl', 'restart', 'freeark-screen-heartbeat'],
            timeout=30,
        )
        ok, msg = hbc_views._restart_heartbeat_service()
        self.assertFalse(ok)
        self.assertIn('超时', msg)


# ===========================================================================
# 2. 单元测试：Consumer 配置加载 (_load_heartbeat_config)
# ===========================================================================

class TestLoadHeartbeatConfig(TestCase):
    """_load_heartbeat_config() 单元测试（screen_heartbeat_consumer.py 中的函数）"""

    def _get_loader(self):
        """动态导入 Management Command 中的 _load_heartbeat_config"""
        import importlib
        import api.management.commands.screen_heartbeat_consumer as mod
        importlib.reload(mod)
        return mod._load_heartbeat_config, mod._HBC_CONFIG_PATH

    def test_loads_valid_config_file(self):
        loader, _ = self._get_loader()
        import api.management.commands.screen_heartbeat_consumer as mod
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            json.dump(_VALID_CONFIG, f)
            tmp_path = f.name
        try:
            with patch.object(mod, '_HBC_CONFIG_PATH', tmp_path):
                cfg = mod._load_heartbeat_config()
            self.assertEqual(cfg['host'], '47.117.41.184')
            self.assertEqual(cfg['port'], 11883)
        finally:
            os.unlink(tmp_path)

    def test_fallback_on_missing_file(self):
        import api.management.commands.screen_heartbeat_consumer as mod
        with patch.object(mod, '_HBC_CONFIG_PATH', '/nonexistent/abc.json'):
            cfg = mod._load_heartbeat_config()
        self.assertEqual(cfg['host'], '47.117.41.184')
        self.assertEqual(cfg['protocol'], 'mqtt')

    def test_fallback_on_bad_json(self):
        import api.management.commands.screen_heartbeat_consumer as mod
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.json', delete=False, encoding='utf-8'
        ) as f:
            f.write('{bad json}')
            tmp_path = f.name
        try:
            with patch.object(mod, '_HBC_CONFIG_PATH', tmp_path):
                cfg = mod._load_heartbeat_config()
            self.assertEqual(cfg['protocol'], 'mqtt')
        finally:
            os.unlink(tmp_path)


# ===========================================================================
# 3. 集成测试：GET API
# ===========================================================================

class TestHeartbeatBrokerConfigGetAPI(TestCase):
    """GET /api/heartbeat-broker-config/ 集成测试"""

    def setUp(self):
        self.client = APIClient()
        _, self.token = _make_user(username='hbc_get_user', role='user', suffix='')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token}')

    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_get_returns_config_with_empty_password(self, mock_read):
        """GET 返回配置，password 字段为空字符串（OQ-004）"""
        resp = self.client.get('/api/heartbeat-broker-config/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['data']['password'], '')
        self.assertEqual(data['data']['host'], '47.117.41.184')
        self.assertEqual(data['data']['protocol'], 'mqtt')

    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_get_returns_all_fields(self, mock_read):
        """GET 返回完整字段集"""
        resp = self.client.get('/api/heartbeat-broker-config/')
        data = resp.json()['data']
        for key in ('protocol', 'host', 'port', 'path', 'username', 'topic', 'client_id', 'keepalive'):
            self.assertIn(key, data, f'缺少字段: {key}')

    def test_get_requires_authentication(self):
        """未登录用户应返回 401"""
        client = APIClient()
        resp = client.get('/api/heartbeat-broker-config/')
        self.assertEqual(resp.status_code, 401)


# ===========================================================================
# 4. 集成测试：PUT API — mqtt 协议路径
# ===========================================================================

class TestHeartbeatBrokerConfigPutMqttAPI(TestCase):
    """PUT /api/heartbeat-broker-config/update/ 集成测试 — mqtt 协议路径"""

    def setUp(self):
        self.client = APIClient()
        _, self.admin_token = _make_user(username='hbc_admin_mqtt', role='admin', suffix='')
        _, self.user_token = _make_user(username='hbc_user_mqtt', role='user', suffix='')

    def _admin_client(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')
        return c

    def _user_client(self):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token}')
        return c

    @patch.object(hbc_views, '_restart_heartbeat_service', return_value=(True, 'ok'))
    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_admin_put_mqtt_success(self, mock_read, mock_write, mock_restart):
        """admin 用户 PUT mqtt 配置成功"""
        resp = self._admin_client().put(
            '/api/heartbeat-broker-config/update/',
            data=_VALID_CONFIG,
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        self.assertIn('配置已保存', data['message'])
        mock_write.assert_called_once()
        mock_restart.assert_called_once()

    @patch.object(hbc_views, '_restart_heartbeat_service', return_value=(True, 'ok'))
    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_put_writes_correct_config_fields(self, mock_read, mock_write, mock_restart):
        """PUT 写入的配置包含正确字段值"""
        self._admin_client().put(
            '/api/heartbeat-broker-config/update/',
            data=_VALID_CONFIG,
            format='json',
        )
        written = mock_write.call_args[0][0]
        self.assertEqual(written['host'], '47.117.41.184')
        self.assertEqual(written['port'], 11883)
        self.assertEqual(written['protocol'], 'mqtt')

    def test_non_admin_put_returns_403(self):
        """非 admin 用户 PUT 应返回 403 (US-HBC-006)"""
        resp = self._user_client().put(
            '/api/heartbeat-broker-config/update/',
            data=_VALID_CONFIG,
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()['success'])

    def test_unauthenticated_put_returns_401(self):
        """未登录用户 PUT 返回 401"""
        resp = APIClient().put(
            '/api/heartbeat-broker-config/update/',
            data=_VALID_CONFIG,
            format='json',
        )
        self.assertEqual(resp.status_code, 401)

    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_invalid_host_returns_400(self, mock_read):
        """host 含注入字符时返回 400 (REQ-NFUNC-001, US-HBC-006)"""
        bad = dict(_VALID_CONFIG)
        bad['host'] = '47.117.41.184; rm -rf /'
        resp = self._admin_client().put(
            '/api/heartbeat-broker-config/update/',
            data=bad,
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()['success'])

    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_invalid_port_returns_400(self, mock_read):
        """port 超出范围时返回 400"""
        bad = dict(_VALID_CONFIG)
        bad['port'] = 99999
        resp = self._admin_client().put(
            '/api/heartbeat-broker-config/update/',
            data=bad,
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_invalid_protocol_returns_400(self, mock_read):
        """protocol 非法值时返回 400"""
        bad = dict(_VALID_CONFIG)
        bad['protocol'] = 'tcp'
        resp = self._admin_client().put(
            '/api/heartbeat-broker-config/update/',
            data=bad,
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    @patch.object(hbc_views, '_restart_heartbeat_service', return_value=(True, 'ok'))
    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_empty_password_preserves_original(self, mock_read, mock_write, mock_restart):
        """PUT 中 password='' 时写入配置中 password 保留文件中原值（OQ-004）"""
        payload = dict(_VALID_CONFIG)
        payload['password'] = ''
        self._admin_client().put(
            '/api/heartbeat-broker-config/update/',
            data=payload,
            format='json',
        )
        written = mock_write.call_args[0][0]
        # _read_hbc_config mock 返回 _VALID_CONFIG，其 password='public'
        self.assertEqual(written['password'], 'public')

    @patch.object(hbc_views, '_restart_heartbeat_service', return_value=(True, 'ok'))
    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_nonempty_password_overwrites(self, mock_read, mock_write, mock_restart):
        """PUT 中 password='newpass' 时写入配置中 password 被覆盖（OQ-004）"""
        payload = dict(_VALID_CONFIG)
        payload['password'] = 'newpass'
        self._admin_client().put(
            '/api/heartbeat-broker-config/update/',
            data=payload,
            format='json',
        )
        written = mock_write.call_args[0][0]
        self.assertEqual(written['password'], 'newpass')


# ===========================================================================
# 5. 集成测试：PUT API — wss 协议路径
# ===========================================================================

class TestHeartbeatBrokerConfigPutWssAPI(TestCase):
    """PUT /api/heartbeat-broker-config/update/ 集成测试 — wss 协议路径"""

    def setUp(self):
        self.client = APIClient()
        _, self.admin_token = _make_user(username='hbc_admin_wss', role='admin', suffix='')
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')

    @patch.object(hbc_views, '_restart_heartbeat_service', return_value=(True, 'ok'))
    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_wss_config_accepted(self, mock_read, mock_write, mock_restart):
        """wss 协议配置被接受并正确写入"""
        resp = self.client.put(
            '/api/heartbeat-broker-config/update/',
            data=_WSS_CONFIG,
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        written = mock_write.call_args[0][0]
        self.assertEqual(written['protocol'], 'wss')
        self.assertEqual(written['host'], 'www.ttqingjiao.site')
        self.assertEqual(written['port'], 8084)
        self.assertEqual(written['path'], '/mqtt')

    @patch.object(hbc_views, '_restart_heartbeat_service', return_value=(True, 'ok'))
    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_wss_triggers_service_restart(self, mock_read, mock_write, mock_restart):
        """wss 配置保存后触发服务重启"""
        self.client.put(
            '/api/heartbeat-broker-config/update/',
            data=_WSS_CONFIG,
            format='json',
        )
        mock_restart.assert_called_once()


# ===========================================================================
# 6. 集成测试：PUT API — restart 触发（mock subprocess）
# ===========================================================================

class TestHeartbeatBrokerConfigRestartIntegration(TestCase):
    """PUT 触发 restart 调用的集成测试（mock subprocess）"""

    def setUp(self):
        _, self.admin_token = _make_user(username='hbc_admin_restart', role='admin', suffix='')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')

    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    @patch('api.views_heartbeat_config.subprocess.run')
    def test_subprocess_called_with_correct_args(self, mock_run, mock_read, mock_write):
        """PUT 后 subprocess.run 以正确参数调用 systemctl restart"""
        mock_run.return_value = MagicMock(returncode=0, stderr='', stdout='')
        self.client.put(
            '/api/heartbeat-broker-config/update/',
            data=_VALID_CONFIG,
            format='json',
        )
        mock_run.assert_called_once_with(
            ['sudo', 'systemctl', 'restart', 'freeark-screen-heartbeat'],
            capture_output=True, text=True, timeout=30,
        )

    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    @patch('api.views_heartbeat_config.subprocess.run')
    def test_restart_failure_returns_500_with_config_saved(self, mock_run, mock_read, mock_write):
        """restart 失败时返回 500，但配置文件已落盘（US-HBC-004）"""
        mock_run.return_value = MagicMock(returncode=1, stderr='Failed to restart', stdout='')
        resp = self.client.put(
            '/api/heartbeat-broker-config/update/',
            data=_VALID_CONFIG,
            format='json',
        )
        self.assertEqual(resp.status_code, 500)
        data = resp.json()
        self.assertFalse(data['success'])
        self.assertIn('配置已保存', data['error'])
        # 配置写入已发生
        mock_write.assert_called_once()

    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    @patch('api.views_heartbeat_config.subprocess.run')
    def test_restart_timeout_returns_500(self, mock_run, mock_read, mock_write):
        """restart 超时时返回 500（US-HBC-004）"""
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=['sudo', 'systemctl', 'restart', 'freeark-screen-heartbeat'],
            timeout=30,
        )
        resp = self.client.put(
            '/api/heartbeat-broker-config/update/',
            data=_VALID_CONFIG,
            format='json',
        )
        self.assertEqual(resp.status_code, 500)
        self.assertFalse(resp.json()['success'])


# ===========================================================================
# 7. 集成测试：兼容性 — 旧 mqtt 地址 (US-HBC-007)
# ===========================================================================

class TestLegacyMqttCompatibility(TestCase):
    """旧 mqtt+47.x.x.x 地址应被接受（REQ-NFUNC-002, US-HBC-007）"""

    def setUp(self):
        _, self.admin_token = _make_user(username='hbc_legacy', role='admin', suffix='')
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token}')

    @patch.object(hbc_views, '_restart_heartbeat_service', return_value=(True, 'ok'))
    @patch.object(hbc_views, '_write_hbc_config')
    @patch.object(hbc_views, '_read_hbc_config', return_value=dict(_VALID_CONFIG))
    def test_legacy_mqtt_address_accepted(self, mock_read, mock_write, mock_restart):
        """mqtt + 47.117.41.184:11883 作为合法配置被接受"""
        resp = self.client.put(
            '/api/heartbeat-broker-config/update/',
            data=_VALID_CONFIG,
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
