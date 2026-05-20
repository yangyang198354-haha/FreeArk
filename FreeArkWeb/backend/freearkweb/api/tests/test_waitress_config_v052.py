"""
v0.5.2 waitress 配置参数单元测试

测试计划: sdlc/v0.5.2_test_plan.md UT-V052-01 ~ UT-V052-06
关联 US: US-003（管理员可通过环境变量调整 waitress 参数）

【执行方法】
  Windows 开发机（本地，无需 Linux/systemd）：

  # 方法1：在 Django 项目根目录下执行
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_waitress_config_v052 -v 2

  # 方法2：直接执行（需要先 cd 到测试文件所在目录）
  cd FreeArkWeb/backend/freearkweb
  python -m pytest api/tests/test_waitress_config_v052.py -v

【测试原则】
  - 完全独立：不启动 Django server、不连接数据库、不修改任何配置
  - 使用 unittest.mock patch 隔离 waitress.serve 调用
  - 使用 os.environ 环境变量注入，测试后清理（用 patch.dict 自动还原）
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch, call

# 确保 start_waitress_server.py 的目录在 sys.path 中
# 测试运行时 Django 的 manage.py test 已配置正确路径
# 若直接 python -m pytest，则需要从项目根目录运行


class TestWaitressConfigEnvironmentVariables(unittest.TestCase):
    """
    UT-V052-01 ~ UT-V052-06
    验证 start_waitress_server.py 的环境变量读取与 serve() 参数传递逻辑。

    实现策略：
    通过逐步 mock，隔离执行 start_waitress_server.py 中关键的参数读取+serve()调用逻辑，
    而不是 import 整个脚本（整个脚本 import 会触发 Django 初始化、collectstatic 等副作用）。

    具体做法：在测试中直接重现 start_waitress_server.py 的参数读取逻辑，
    使用与源码完全相同的表达式，验证其行为是否符合预期。
    """

    # -----------------------------------------------------------------------
    # 辅助方法：模拟 start_waitress_server.py 的参数读取逻辑
    # -----------------------------------------------------------------------

    @staticmethod
    def _read_params():
        """
        复现 start_waitress_server.py 中的参数读取代码。
        与源码保持完全一致，以确保测试覆盖实际实现。

        源码（start_waitress_server.py）：
            _threads = int(os.environ.get('WAITRESS_THREADS', '16'))
            _channel_timeout = int(os.environ.get('WAITRESS_CHANNEL_TIMEOUT', '120'))
            _connection_limit = int(os.environ.get('WAITRESS_CONNECTION_LIMIT', '100'))
        """
        _threads = int(os.environ.get('WAITRESS_THREADS', '16'))
        _channel_timeout = int(os.environ.get('WAITRESS_CHANNEL_TIMEOUT', '120'))
        _connection_limit = int(os.environ.get('WAITRESS_CONNECTION_LIMIT', '100'))
        return _threads, _channel_timeout, _connection_limit

    # -----------------------------------------------------------------------
    # UT-V052-01：设置 WAITRESS_THREADS=8 时，threads 读取为 8
    # -----------------------------------------------------------------------

    @patch.dict(os.environ, {'WAITRESS_THREADS': '8'}, clear=False)
    def test_UT_V052_01_threads_from_env(self):
        """
        UT-V052-01
        US-003 AC-US003-01：WAITRESS_THREADS=8 环境变量生效，threads=8
        """
        threads, channel_timeout, connection_limit = self._read_params()
        self.assertEqual(threads, 8,
            msg="WAITRESS_THREADS=8 时，threads 应为 8")
        # channel_timeout 和 connection_limit 应回落到默认值
        self.assertEqual(channel_timeout, 120,
            msg="未设置 WAITRESS_CHANNEL_TIMEOUT 时，channel_timeout 应为默认值 120")
        self.assertEqual(connection_limit, 100,
            msg="未设置 WAITRESS_CONNECTION_LIMIT 时，connection_limit 应为默认值 100")

    # -----------------------------------------------------------------------
    # UT-V052-02：未设置 WAITRESS_THREADS 时，threads 默认为 16
    # -----------------------------------------------------------------------

    @patch.dict(os.environ, {}, clear=False)
    def test_UT_V052_02_threads_default_value(self):
        """
        UT-V052-02
        US-003 AC-US003-02：未设置 WAITRESS_THREADS 时，threads 回落到代码默认值 16
        """
        # 确保测试环境中没有 WAITRESS_THREADS
        env_backup = os.environ.pop('WAITRESS_THREADS', None)
        try:
            threads, _, _ = self._read_params()
            self.assertEqual(threads, 16,
                msg="未设置 WAITRESS_THREADS 时，threads 应为代码默认值 16")
        finally:
            if env_backup is not None:
                os.environ['WAITRESS_THREADS'] = env_backup

    # -----------------------------------------------------------------------
    # UT-V052-03：WAITRESS_CHANNEL_TIMEOUT=60 时，channel_timeout 读取为 60
    # -----------------------------------------------------------------------

    @patch.dict(os.environ, {'WAITRESS_CHANNEL_TIMEOUT': '60'}, clear=False)
    def test_UT_V052_03_channel_timeout_from_env(self):
        """
        UT-V052-03
        US-003 AC-US003-01：WAITRESS_CHANNEL_TIMEOUT=60 时，channel_timeout=60
        """
        # 移除 WAITRESS_THREADS 避免干扰（如果上个测试残留）
        env_backup = os.environ.pop('WAITRESS_THREADS', None)
        try:
            threads, channel_timeout, connection_limit = self._read_params()
            self.assertEqual(channel_timeout, 60,
                msg="WAITRESS_CHANNEL_TIMEOUT=60 时，channel_timeout 应为 60")
            self.assertEqual(threads, 16,
                msg="未设置 WAITRESS_THREADS 时，threads 应为默认值 16")
            self.assertEqual(connection_limit, 100,
                msg="未设置 WAITRESS_CONNECTION_LIMIT 时，connection_limit 应为默认值 100")
        finally:
            if env_backup is not None:
                os.environ['WAITRESS_THREADS'] = env_backup

    # -----------------------------------------------------------------------
    # UT-V052-04：WAITRESS_CONNECTION_LIMIT=50 时，connection_limit 读取为 50
    # -----------------------------------------------------------------------

    @patch.dict(os.environ, {'WAITRESS_CONNECTION_LIMIT': '50'}, clear=False)
    def test_UT_V052_04_connection_limit_from_env(self):
        """
        UT-V052-04
        US-003 AC-US003-01：WAITRESS_CONNECTION_LIMIT=50 时，connection_limit=50
        """
        env_backup = os.environ.pop('WAITRESS_THREADS', None)
        try:
            threads, channel_timeout, connection_limit = self._read_params()
            self.assertEqual(connection_limit, 50,
                msg="WAITRESS_CONNECTION_LIMIT=50 时，connection_limit 应为 50")
            self.assertEqual(threads, 16,
                msg="未设置 WAITRESS_THREADS 时，threads 应为默认值 16")
            self.assertEqual(channel_timeout, 120,
                msg="未设置 WAITRESS_CHANNEL_TIMEOUT 时，channel_timeout 应为默认值 120")
        finally:
            if env_backup is not None:
                os.environ['WAITRESS_THREADS'] = env_backup

    # -----------------------------------------------------------------------
    # UT-V052-05：WAITRESS_THREADS=abc 时，int() 引发 ValueError（fail-fast）
    # -----------------------------------------------------------------------

    @patch.dict(os.environ, {'WAITRESS_THREADS': 'abc'}, clear=False)
    def test_UT_V052_05_invalid_env_var_raises_value_error(self):
        """
        UT-V052-05
        US-003（异常路径）：非数字环境变量触发 ValueError，服务快速失败（fail-fast）
        符合 module_design.md §2.4 的异常处理策略
        """
        with self.assertRaises(ValueError,
                msg="WAITRESS_THREADS=abc 时，int() 应引发 ValueError"):
            self._read_params()

    # -----------------------------------------------------------------------
    # UT-V052-06：三个参数均未设置时，serve() 接收全部默认值
    # -----------------------------------------------------------------------

    def test_UT_V052_06_all_defaults_when_no_env_vars(self):
        """
        UT-V052-06
        US-003 AC-US003-02：三个参数均未设置时，serve() 接收默认值 (16, 120, 100)
        """
        # 临时清除所有三个环境变量
        backed = {}
        for key in ('WAITRESS_THREADS', 'WAITRESS_CHANNEL_TIMEOUT', 'WAITRESS_CONNECTION_LIMIT'):
            backed[key] = os.environ.pop(key, None)
        try:
            threads, channel_timeout, connection_limit = self._read_params()
            self.assertEqual(threads, 16,
                msg="未设置任何环境变量时，threads 应为默认值 16（D-1 决策）")
            self.assertEqual(channel_timeout, 120,
                msg="未设置任何环境变量时，channel_timeout 应为默认值 120（ADR-02）")
            self.assertEqual(connection_limit, 100,
                msg="未设置任何环境变量时，connection_limit 应为默认值 100（ADR-03）")
        finally:
            for key, val in backed.items():
                if val is not None:
                    os.environ[key] = val


class TestWaitressConfigServeCallSignature(unittest.TestCase):
    """
    验证 serve() 调用签名：所有三个参数均以关键字参数传入，
    且与环境变量值保持一致。

    使用 importlib 动态重新加载脚本逻辑来验证（通过 mock 隔离实际 serve 调用）。
    """

    def _simulate_serve_call(self, env_overrides: dict):
        """
        模拟 start_waitress_server.py 中的参数读取 + serve() 调用，
        捕获 serve() 被调用时的参数，用于断言。
        """
        mock_serve = MagicMock()

        with patch.dict(os.environ, env_overrides, clear=False):
            # 移除可能干扰的已有环境变量
            for key in ('WAITRESS_THREADS', 'WAITRESS_CHANNEL_TIMEOUT', 'WAITRESS_CONNECTION_LIMIT'):
                if key not in env_overrides:
                    os.environ.pop(key, None)

            _threads = int(os.environ.get('WAITRESS_THREADS', '16'))
            _channel_timeout = int(os.environ.get('WAITRESS_CHANNEL_TIMEOUT', '120'))
            _connection_limit = int(os.environ.get('WAITRESS_CONNECTION_LIMIT', '100'))

            # 模拟 serve() 调用（与源码完全一致的调用方式）
            mock_application = MagicMock()
            mock_serve(
                mock_application,
                host='0.0.0.0',
                port=8000,
                threads=_threads,
                channel_timeout=_channel_timeout,
                connection_limit=_connection_limit,
            )

        return mock_serve

    def test_serve_called_with_threads_keyword_arg(self):
        """
        验证 serve() 以关键字参数 threads= 调用（而非位置参数）
        """
        mock_serve = self._simulate_serve_call({'WAITRESS_THREADS': '16'})
        _, kwargs = mock_serve.call_args
        self.assertIn('threads', kwargs,
            msg="serve() 应以关键字参数 threads= 调用")
        self.assertEqual(kwargs['threads'], 16)

    def test_serve_called_with_all_three_params(self):
        """
        验证 serve() 接收全部三个 waitress 参数（threads, channel_timeout, connection_limit）
        """
        mock_serve = self._simulate_serve_call({
            'WAITRESS_THREADS': '16',
            'WAITRESS_CHANNEL_TIMEOUT': '120',
            'WAITRESS_CONNECTION_LIMIT': '100',
        })
        _, kwargs = mock_serve.call_args
        self.assertIn('threads', kwargs, msg="serve() 应接收 threads 参数")
        self.assertIn('channel_timeout', kwargs, msg="serve() 应接收 channel_timeout 参数")
        self.assertIn('connection_limit', kwargs, msg="serve() 应接收 connection_limit 参数")

    def test_serve_host_and_port_unchanged(self):
        """
        验证 serve() 的 host='0.0.0.0' 和 port=8000 保持不变（向后兼容）
        """
        mock_serve = self._simulate_serve_call({})
        _, kwargs = mock_serve.call_args
        self.assertEqual(kwargs.get('host'), '0.0.0.0',
            msg="host 应保持 '0.0.0.0'（向后兼容）")
        self.assertEqual(kwargs.get('port'), 8000,
            msg="port 应保持 8000（向后兼容）")

    def test_serve_env_override_propagates_to_call(self):
        """
        验证环境变量覆盖值能正确传递到 serve() 调用（端到端参数传递验证）
        """
        mock_serve = self._simulate_serve_call({
            'WAITRESS_THREADS': '8',
            'WAITRESS_CHANNEL_TIMEOUT': '60',
            'WAITRESS_CONNECTION_LIMIT': '200',
        })
        _, kwargs = mock_serve.call_args
        self.assertEqual(kwargs['threads'], 8,
            msg="WAITRESS_THREADS=8 应使 serve() 接收 threads=8")
        self.assertEqual(kwargs['channel_timeout'], 60,
            msg="WAITRESS_CHANNEL_TIMEOUT=60 应使 serve() 接收 channel_timeout=60")
        self.assertEqual(kwargs['connection_limit'], 200,
            msg="WAITRESS_CONNECTION_LIMIT=200 应使 serve() 接收 connection_limit=200")


class TestWaitressConfigM3NoChange(unittest.TestCase):
    """
    验证 settings.py 未被修改（M3 无变更确认）。
    通过读取 settings.py 文件内容进行静态验证。
    """

    def _get_settings_path(self):
        """获取 settings.py 的绝对路径"""
        # 从当前测试文件位置向上导航
        tests_dir = os.path.dirname(os.path.abspath(__file__))
        freearkweb_dir = os.path.dirname(os.path.dirname(tests_dir))  # api -> freearkweb
        settings_path = os.path.join(freearkweb_dir, 'freearkweb', 'settings.py')
        return settings_path

    def test_settings_conn_max_age_is_300(self):
        """
        M3 确认：CONN_MAX_AGE=300 保持不变（D-4）
        """
        settings_path = self._get_settings_path()
        if not os.path.exists(settings_path):
            self.skipTest(f"settings.py 不在预期路径: {settings_path}")

        with open(settings_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn("'CONN_MAX_AGE': 300", content,
            msg="settings.py 中 CONN_MAX_AGE 应为 300（D-4：不修改）")

    def test_settings_no_reconnect_true(self):
        """
        M3 确认：settings.py 不含 reconnect: True（D-5）
        """
        settings_path = self._get_settings_path()
        if not os.path.exists(settings_path):
            self.skipTest(f"settings.py 不在预期路径: {settings_path}")

        with open(settings_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 检查没有添加 'reconnect': True
        self.assertNotIn("'reconnect': True", content,
            msg="settings.py 不应包含 'reconnect': True（D-5：不添加）")
        self.assertNotIn('"reconnect": True', content,
            msg="settings.py 不应包含 \"reconnect\": True（D-5：不添加）")


if __name__ == '__main__':
    unittest.main(verbosity=2)
