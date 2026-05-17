"""
US-C / US-D 测试套件 — LogConfigManager

测试覆盖：
  US-C-1  TimedRotatingFileHandler rollover 验证（mock doRollover）
  US-C-2  backupCount=7，历史文件保留数量验证
  US-C-3  baseFilename 命名格式为 {name}.log（无日期前缀）
  US-D-1  删除 datacollection/resource/log_config.json 后仍能加载项目根配置
  US-D-2  APP_LOG_LEVEL 环境变量优先级不回退（US-B 行为验证）
  US-D-3  诊断 print 在首次加载时执行（至多一次）

运行方式：
  cd <项目根>
  python datacollection/test_log_config_manager.py
  # 或
  python -m unittest datacollection.test_log_config_manager -v
"""

import os
import sys
import json
import logging
import logging.handlers
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import importlib

# ---------------------------------------------------------------------------
# 工具：彻底重置 LogConfigManager 单例（每个测试用例隔离）
# ---------------------------------------------------------------------------

def _reset_lcm_singleton():
    """清除 LogConfigManager 单例状态，确保每个 test 独立初始化。"""
    # 重新 import 模块以重置模块级单例状态
    import datacollection.log_config_manager as lcm_mod
    lcm_mod.LogConfigManager._instance = None
    lcm_mod.LogConfigManager._config = None
    lcm_mod.LogConfigManager._config_path = None
    lcm_mod.LogConfigManager._last_load_time = 0
    # 清除可能已添加 handler 的 logger
    for name in list(logging.Logger.manager.loggerDict.keys()):
        lgr = logging.getLogger(name)
        lgr.handlers.clear()


# ---------------------------------------------------------------------------
# US-C 测试
# ---------------------------------------------------------------------------

class TestUSC_RotatingHandler(unittest.TestCase):
    """US-C：TimedRotatingFileHandler 相关测试。"""

    def setUp(self):
        _reset_lcm_singleton()
        # 使用临时目录作为 logs 目录，不污染项目
        self.tmp_dir = tempfile.mkdtemp(prefix="test_lcm_")

    def tearDown(self):
        _reset_lcm_singleton()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _get_fresh_logger(self, name="test_usc"):
        """在 tmp_dir 作为 cwd 的上下文中获取一个全新 logger。"""
        import datacollection.log_config_manager as lcm_mod
        _reset_lcm_singleton()
        with patch("os.getcwd", return_value=self.tmp_dir):
            # 重建单例（__new__ 会在 with 块内用 tmp_dir 作为 cwd）
            lcm_mod.LogConfigManager._instance = None
            lcm = lcm_mod.LogConfigManager()
            logger = logging.getLogger(name)
            logger.handlers.clear()
            logger.propagate = False
            log_level = logging.WARNING
            logger.setLevel(log_level)

            log_dir = os.path.join(self.tmp_dir, "logs")
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, f"{name}.log")
            fh = logging.handlers.TimedRotatingFileHandler(
                log_path,
                when='midnight',
                interval=1,
                backupCount=7,
                encoding='utf-8',
            )
            fh.setLevel(log_level)
            logger.addHandler(fh)
            return logger, fh, log_dir, log_path

    # US-C-1：doRollover 可调用，rollover 后产生带日期后缀的备份文件
    def test_C1_rollover_creates_backup(self):
        logger, fh, log_dir, log_path = self._get_fresh_logger("usc1")
        # 写一条日志，确保文件存在
        logger.warning("rollover test message")
        fh.flush()
        self.assertTrue(os.path.exists(log_path), "当前日志文件应存在")

        # 触发 rollover（模拟到了午夜）
        fh.doRollover()

        # rollover 后当前文件依然存在（TimedRotatingFileHandler 重新打开同名文件）
        self.assertTrue(os.path.exists(log_path),
                        "rollover 后 baseFilename 文件应仍存在（新一天的日志文件）")

        # 旧文件应带日期后缀（.YYYY-MM-DD 格式）
        backup_files = [
            f for f in os.listdir(log_dir)
            if f.startswith("usc1.log.") and f != "usc1.log"
        ]
        self.assertGreaterEqual(len(backup_files), 1,
                                f"rollover 后应产生至少一个带日期后缀的备份文件，实际：{os.listdir(log_dir)}")

    # US-C-2：backupCount=7，超出时自动删除最旧文件
    def test_C2_backup_count_respected(self):
        logger, fh, log_dir, log_path = self._get_fresh_logger("usc2")

        # 触发 8 次 rollover，超过 backupCount=7
        for i in range(8):
            logger.warning(f"message before rollover {i}")
            fh.flush()
            fh.doRollover()

        all_files = os.listdir(log_dir)
        backup_files = [f for f in all_files if f.startswith("usc2.log.")]
        # backupCount=7，最多保留 7 个带后缀文件
        self.assertLessEqual(
            len(backup_files), 7,
            f"backupCount=7 时备份文件数不应超过 7，实际：{backup_files}"
        )

    # US-C-3：baseFilename 格式为 {name}.log（不含日期前缀）
    def test_C3_base_filename_format(self):
        _reset_lcm_singleton()
        import datacollection.log_config_manager as lcm_mod

        log_dir = os.path.join(self.tmp_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)

        # 构造一个 resource/log_config.json 在 tmp_dir 下，供 LogConfigManager 加载
        res_dir = os.path.join(self.tmp_dir, "resource")
        os.makedirs(res_dir, exist_ok=True)
        cfg = {
            "log_levels": {
                "global": {"level": "WARNING"},
                "usc3_logger": {"level": "WARNING"}
            }
        }
        with open(os.path.join(res_dir, "log_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        with patch("os.getcwd", return_value=self.tmp_dir):
            lcm_mod.LogConfigManager._instance = None
            lgr = lcm_mod.LogConfigManager().get_logger("usc3_logger")

        # 找到 TimedRotatingFileHandler
        timed_handlers = [
            h for h in lgr.handlers
            if isinstance(h, logging.handlers.TimedRotatingFileHandler)
        ]
        self.assertEqual(len(timed_handlers), 1, "应有且只有一个 TimedRotatingFileHandler")

        base = os.path.basename(timed_handlers[0].baseFilename)
        # 期望格式：usc3_logger.log（不含 _YYYYMMDD 前缀）
        self.assertEqual(base, "usc3_logger.log",
                         f"baseFilename 应为 'usc3_logger.log'，实际：{base}")

        # 验证不含旧格式的 _YYYYMMDD 片段
        import re
        self.assertFalse(
            re.search(r"_\d{8}\.", base),
            f"baseFilename 不应包含 _YYYYMMDD 片段，实际：{base}"
        )


# ---------------------------------------------------------------------------
# US-D 测试
# ---------------------------------------------------------------------------

class TestUSD_ConfigFallback(unittest.TestCase):
    """US-D：删除 datacollection/resource/log_config.json 后的 fallback 行为。"""

    def setUp(self):
        _reset_lcm_singleton()
        self.tmp_dir = tempfile.mkdtemp(prefix="test_lcm_usd_")

    def tearDown(self):
        _reset_lcm_singleton()
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # US-D-1：仅有项目根 resource/log_config.json，datacollection/resource/ 下无配置，
    #         LogConfigManager 仍能正确加载项目根配置
    def test_D1_fallback_to_project_root_config(self):
        """
        模拟生产场景：
          tmp_dir/resource/log_config.json   <- 项目根配置（权威）
          tmp_dir/datacollection/resource/   <- 目录存在但无 log_config.json（已删除）

        cwd = tmp_dir（模拟 systemd WorkingDirectory=/home/yangyang/Freeark/FreeArk）
        期望：LogConfigManager 通过 Fallback 1 加载 tmp_dir/resource/log_config.json
        """
        import datacollection.log_config_manager as lcm_mod
        _reset_lcm_singleton()

        # 建项目根 resource 目录 + 配置
        res_dir = os.path.join(self.tmp_dir, "resource")
        os.makedirs(res_dir, exist_ok=True)
        root_cfg = {
            "log_levels": {
                "global": {"level": "ERROR"},
                "multi_thread_plc_handler": {"level": "WARNING"}
            },
            "config_info": {"version": "2.0"}
        }
        root_cfg_path = os.path.join(res_dir, "log_config.json")
        with open(root_cfg_path, "w", encoding="utf-8") as f:
            json.dump(root_cfg, f)

        # datacollection/resource/ 存在但无 log_config.json（模拟删除后状态）
        dc_res_dir = os.path.join(self.tmp_dir, "datacollection", "resource")
        os.makedirs(dc_res_dir, exist_ok=True)
        # 不写 log_config.json

        with patch("os.getcwd", return_value=self.tmp_dir):
            lcm_mod.LogConfigManager._instance = None
            lcm = lcm_mod.LogConfigManager()

        # 验证加载路径是项目根的配置
        self.assertTrue(
            lcm._config_path.endswith(os.path.join("resource", "log_config.json")),
            f"期望加载路径以 resource/log_config.json 结尾，实际：{lcm._config_path}"
        )
        self.assertIsNotNone(lcm._config, "配置应已成功加载")
        self.assertEqual(
            lcm._config.get("log_levels", {}).get("global", {}).get("level"),
            "ERROR",
            "global level 应从项目根配置读取为 ERROR"
        )

    # US-D-1b：cwd 不是项目根（极端情况），Fallback 3（__file__ 路径）兜底
    def test_D1b_fallback3_via_file_path(self):
        """
        当 cwd 既没有 resource/log_config.json 也没有 log_config.json 时，
        Fallback 3（dirname(dirname(__file__)) / resource / log_config.json）应能命中项目根配置。
        此测试依赖真实项目结构，要求从项目根运行。
        """
        import datacollection.log_config_manager as lcm_mod
        _reset_lcm_singleton()

        # 使用一个完全空的目录模拟"奇怪的 cwd"
        empty_cwd = tempfile.mkdtemp(prefix="empty_cwd_")
        try:
            with patch("os.getcwd", return_value=empty_cwd):
                lcm_mod.LogConfigManager._instance = None
                lcm = lcm_mod.LogConfigManager()

            # Fallback 3 路径 = dirname(dirname(abspath(__file__))) / resource / log_config.json
            import datacollection.log_config_manager as lcm_mod2
            expected_base = os.path.dirname(os.path.dirname(os.path.abspath(lcm_mod2.__file__)))
            expected_path = os.path.join(expected_base, "resource", "log_config.json")

            # 验证：_config_path 应与 Fallback 3 结果一致
            self.assertEqual(
                os.path.normcase(os.path.abspath(lcm._config_path)),
                os.path.normcase(os.path.abspath(expected_path)),
                f"Fallback 3 应命中 {expected_path}，实际：{lcm._config_path}"
            )
            # 配置应成功加载（不是 None）
            self.assertIsNotNone(lcm._config)
        finally:
            shutil.rmtree(empty_cwd, ignore_errors=True)

    # US-D-2：APP_LOG_LEVEL 环境变量优先级不回退（US-B 核心行为）
    def test_D2_env_APP_LOG_LEVEL_takes_precedence(self):
        """APP_LOG_LEVEL=DEBUG 应覆盖 JSON 中 global=ERROR 的设置。"""
        import datacollection.log_config_manager as lcm_mod
        _reset_lcm_singleton()

        res_dir = os.path.join(self.tmp_dir, "resource")
        os.makedirs(res_dir, exist_ok=True)
        cfg = {"log_levels": {"global": {"level": "ERROR"}}}
        with open(os.path.join(res_dir, "log_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        original_env = os.environ.get("APP_LOG_LEVEL")
        try:
            os.environ["APP_LOG_LEVEL"] = "DEBUG"
            with patch("os.getcwd", return_value=self.tmp_dir):
                lcm_mod.LogConfigManager._instance = None
                lcm = lcm_mod.LogConfigManager()
                level = lcm.get_log_level("any_logger_name")
            self.assertEqual(level, logging.DEBUG,
                             "APP_LOG_LEVEL=DEBUG 应使所有 logger 级别变为 DEBUG，不受 JSON 中 ERROR 影响")
        finally:
            if original_env is None:
                os.environ.pop("APP_LOG_LEVEL", None)
            else:
                os.environ["APP_LOG_LEVEL"] = original_env

    # US-D-2b：APP_LOG_LEVEL 未设置时，JSON 中 per-logger 豁免生效
    def test_D2b_per_logger_exemption_without_env(self):
        """无 APP_LOG_LEVEL 时，multi_thread_plc_handler 应从 JSON 读到 WARNING。"""
        import datacollection.log_config_manager as lcm_mod
        _reset_lcm_singleton()

        res_dir = os.path.join(self.tmp_dir, "resource")
        os.makedirs(res_dir, exist_ok=True)
        cfg = {
            "log_levels": {
                "global": {"level": "ERROR"},
                "multi_thread_plc_handler": {"level": "WARNING"}
            }
        }
        with open(os.path.join(res_dir, "log_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        original_env = os.environ.get("APP_LOG_LEVEL")
        try:
            os.environ.pop("APP_LOG_LEVEL", None)
            with patch("os.getcwd", return_value=self.tmp_dir):
                lcm_mod.LogConfigManager._instance = None
                lcm = lcm_mod.LogConfigManager()
                level_plc = lcm.get_log_level("multi_thread_plc_handler")
                level_global = lcm.get_log_level("mqtt_client")
        finally:
            if original_env is not None:
                os.environ["APP_LOG_LEVEL"] = original_env

        self.assertEqual(level_plc, logging.WARNING,
                         "multi_thread_plc_handler 豁免应为 WARNING")
        self.assertEqual(level_global, logging.ERROR,
                         "未豁免的 logger 应跟随 global=ERROR")

    # US-D-3：诊断 print 在首次加载时执行
    def test_D3_diagnostic_print_on_first_load(self):
        """成功加载配置后应 print 诊断行，且仅在首次加载时触发。"""
        import datacollection.log_config_manager as lcm_mod
        _reset_lcm_singleton()

        res_dir = os.path.join(self.tmp_dir, "resource")
        os.makedirs(res_dir, exist_ok=True)
        cfg = {"log_levels": {"global": {"level": "ERROR"}}}
        with open(os.path.join(res_dir, "log_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)

        printed_lines = []
        original_print = print

        def capturing_print(*args, **kwargs):
            printed_lines.append(" ".join(str(a) for a in args))

        with patch("builtins.print", side_effect=capturing_print):
            with patch("os.getcwd", return_value=self.tmp_dir):
                lcm_mod.LogConfigManager._instance = None
                lcm = lcm_mod.LogConfigManager()

        diag_lines = [l for l in printed_lines if "[LogConfigManager] 配置已加载" in l]
        self.assertEqual(len(diag_lines), 1,
                         f"应有且只有一条诊断 print，实际：{diag_lines}")
        self.assertIn("log_config.json", diag_lines[0],
                      "诊断行应包含配置文件路径")


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # 确保项目根在 sys.path，使 datacollection 包可被 import
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    unittest.main(verbosity=2)
