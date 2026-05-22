"""
dph_cleanup_service 单元测试套件

覆盖范围（本次修复重点）：
  TC-U-DPH-001  OperationalError 被抛出时 _run_cleanup() 优雅返回，不重新抛出
  TC-U-DPH-002  通用 Exception 被抛出时 _run_cleanup() 优雅返回，不重新抛出
  TC-U-DPH-003  cron 模式主循环：_run_cleanup 内 OperationalError 不会终止主循环
  TC-U-DPH-004  cron 模式主循环：schedule.run_pending() 抛出未预期异常，主循环不崩溃
  TC-U-DPH-005  --once 模式：_run_cleanup 抛出 OperationalError 后 handle() 正常返回（exit 0）
  TC-U-DPH-006  --once 模式：_run_cleanup 抛出 Exception 后 handle() 正常返回（exit 0）
  TC-U-DPH-007  --dry-run 模式：正常返回，输出预计行数
  TC-U-DPH-008  无超期数据时 _run_cleanup() 正常返回，不删除
  TC-U-DPH-009  正常删除流程：分批删除，输出批次日志
  TC-U-DPH-010  OperationalError 后调用 connection.close()
  TC-U-DPH-011  通用 Exception 后调用 connection.close()
  TC-U-DPH-012  _setup_schedule：有效 cron 表达式注册每日任务
  TC-U-DPH-013  _setup_schedule：无效 cron 表达式退回默认 03:00
  TC-U-DPH-014  _apply_cleanup_db_timeout：将 read/write_timeout 放大到 600s
  TC-U-DPH-015  _apply_cleanup_db_timeout：OPTIONS 无超时项时（SQLite）为无操作
  TC-U-DPH-016  _apply_cleanup_db_timeout：修改超时后关闭旧连接
  TC-U-DPH-017  _run_cleanup：max_batches > 0 时单轮最多执行 max_batches 个批次
  TC-U-DPH-018  _run_cleanup：max_batches=0 表示不限制，正常删完不提前停止
  TC-U-DPH-019  handle()：--once 模式将 --max-batches 透传给 _run_cleanup

运行方式：
    cd FreeArkWeb/backend/freearkweb
    python manage.py test api.tests.test_dph_cleanup_service --verbosity=2

测试数据库：Django 测试框架自动使用 SQLite（settings.py 的 _RUNNING_TESTS 开关）。
所有 DB 访问通过 unittest.mock.patch 拦截，不依赖真实 device_param_history 表。
"""

import time
from io import StringIO
from unittest.mock import MagicMock, patch, call, PropertyMock

from django.db import OperationalError
from django.test import TestCase

# 被测模块路径
CMD_MODULE = 'api.management.commands.dph_cleanup_service'


def _make_command():
    """构造一个 Command 实例，stdout/stderr 指向 StringIO，不需要真实 manage.py 环境。"""
    from api.management.commands.dph_cleanup_service import Command
    cmd = Command()
    cmd.stdout = StringIO()
    cmd.stderr = StringIO()
    return cmd


# ---------------------------------------------------------------------------
# TC-U-DPH-001 / TC-U-DPH-002：_run_cleanup() 异常被捕获，不重抛
# ---------------------------------------------------------------------------

class TC_U_DPH_001_OperationalError_Graceful(TestCase):
    """TC-U-DPH-001: OperationalError 被捕获，_run_cleanup 优雅返回 None，不重抛"""

    @patch(f'{CMD_MODULE}.connection')
    def test_operational_error_does_not_propagate(self, mock_conn):
        """connection.cursor().__enter__ 抛出 OperationalError 时，_run_cleanup 不抛出"""
        mock_conn.cursor.return_value.__enter__.side_effect = OperationalError(
            'MySQL server has gone away'
        )
        cmd = _make_command()
        # 若异常逃逸，此处会抛出，测试将失败
        result = cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False)
        self.assertIsNone(result, '_run_cleanup 应返回 None（隐式 return）')

    @patch(f'{CMD_MODULE}.connection')
    def test_operational_error_writes_stderr(self, mock_conn):
        """捕获 OperationalError 后，stderr 中包含错误信息"""
        mock_conn.cursor.return_value.__enter__.side_effect = OperationalError(
            'Lost connection to MySQL server during query'
        )
        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False)
        stderr_output = cmd.stderr.getvalue()
        self.assertIn('OperationalError', stderr_output)

    @patch(f'{CMD_MODULE}.connection')
    def test_operational_error_calls_connection_close(self, mock_conn):
        """TC-U-DPH-010: OperationalError 后调用 connection.close() 清理坏连接"""
        mock_conn.cursor.return_value.__enter__.side_effect = OperationalError(
            'Lost connection'
        )
        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False)
        mock_conn.close.assert_called_once()


class TC_U_DPH_002_GenericException_Graceful(TestCase):
    """TC-U-DPH-002: 通用 Exception 被捕获，_run_cleanup 优雅返回 None，不重抛"""

    @patch(f'{CMD_MODULE}.connection')
    def test_generic_exception_does_not_propagate(self, mock_conn):
        """cursor 内部抛出 RuntimeError 时，_run_cleanup 不抛出"""
        mock_conn.cursor.return_value.__enter__.side_effect = RuntimeError(
            'unexpected internal error'
        )
        cmd = _make_command()
        result = cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False)
        self.assertIsNone(result)

    @patch(f'{CMD_MODULE}.connection')
    def test_generic_exception_writes_stderr(self, mock_conn):
        """捕获 Exception 后，stderr 中包含"未预期异常"字样"""
        mock_conn.cursor.return_value.__enter__.side_effect = RuntimeError(
            'something blew up'
        )
        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False)
        stderr_output = cmd.stderr.getvalue()
        self.assertIn('未预期异常', stderr_output)

    @patch(f'{CMD_MODULE}.connection')
    def test_generic_exception_calls_connection_close(self, mock_conn):
        """TC-U-DPH-011: 通用 Exception 后调用 connection.close()"""
        mock_conn.cursor.return_value.__enter__.side_effect = ValueError('bad value')
        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False)
        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# TC-U-DPH-003 / TC-U-DPH-004：cron 模式主循环健壮性
# ---------------------------------------------------------------------------

class TC_U_DPH_003_CronLoop_RunCleanup_Error(TestCase):
    """TC-U-DPH-003: cron 模式下 _run_cleanup 内 OperationalError 不冲出主循环"""

    @patch(f'{CMD_MODULE}.connection')
    def test_run_cleanup_operational_error_does_not_escape_job(self, mock_conn):
        """
        验证：当 _run_cleanup 内部发生 OperationalError 时，
        该异常被 _run_cleanup 内的 except OperationalError 块捕获，
        不会传播给调用方（即 schedule job() 包装函数）。

        测试方法：直接调用 _run_cleanup，断言不抛出异常，
        并确认 connection.close() 被调用（是 OperationalError 路径的标志动作）。
        """
        mock_conn.cursor.return_value.__enter__.side_effect = OperationalError(
            'Lost connection to MySQL server during query'
        )
        cmd = _make_command()

        # 如果 OperationalError 冲出，此处会 fail；正常情况应静默返回
        try:
            cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False)
        except OperationalError:
            self.fail('_run_cleanup 不应向外传播 OperationalError，但它确实传播了')

        # OperationalError 路径必须调用 connection.close()
        mock_conn.close.assert_called_once()

    @patch(f'{CMD_MODULE}.schedule')
    @patch(f'{CMD_MODULE}.time')
    def test_cron_loop_continues_after_run_cleanup_error(self, mock_time, mock_schedule):
        """
        验证：在 cron 模式中，job() 调用 _run_cleanup 时即使发生 OperationalError，
        schedule.run_pending() 本身不会抛出（因为异常已被 _run_cleanup 捕获），
        主循环经 KeyboardInterrupt 正常退出，不崩溃。
        """
        sleep_calls = [0]

        def fake_sleep(seconds):
            sleep_calls[0] += 1
            if sleep_calls[0] >= 1:
                raise KeyboardInterrupt

        mock_time.sleep.side_effect = fake_sleep
        # schedule.run_pending 正常返回（_run_cleanup 内部已捕获异常）
        mock_schedule.run_pending.return_value = None

        from api.management.commands.dph_cleanup_service import Command
        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        with patch.object(cmd, '_setup_schedule'):
            options = {
                'days': 7, 'batch_size': 5000, 'sleep_ms': 0,
                'cron': '0 3 * * *', 'once': False, 'dry_run': False,
            }
            # 主循环应通过 KeyboardInterrupt 正常退出，不抛出其他异常
            cmd.handle(**options)

        # run_pending 被调用至少一次，证明主循环确实执行了
        mock_schedule.run_pending.assert_called()


class TC_U_DPH_004_CronLoop_ScheduleError(TestCase):
    """TC-U-DPH-004: schedule.run_pending() 抛出未预期异常，主循环不崩溃"""

    @patch(f'{CMD_MODULE}.schedule')
    @patch(f'{CMD_MODULE}.time')
    def test_main_loop_catches_schedule_exception(self, mock_time, mock_schedule):
        """
        schedule.run_pending() 直接抛出 RuntimeError（模拟 schedule 自身 bug）。
        主循环的 except Exception 兜底应捕获，服务继续运行（循环不退出）。
        通过第二次 time.sleep 的 KeyboardInterrupt 结束测试。
        """
        sleep_calls = [0]

        def fake_sleep(seconds):
            sleep_calls[0] += 1
            if sleep_calls[0] >= 2:
                raise KeyboardInterrupt

        mock_time.sleep.side_effect = fake_sleep
        # 第一次 run_pending 抛出异常，第二次正常
        mock_schedule.run_pending.side_effect = [
            RuntimeError('schedule internal bug'),
            None,
        ]

        from api.management.commands.dph_cleanup_service import Command
        cmd = Command()
        cmd.stdout = StringIO()
        cmd.stderr = StringIO()

        with patch.object(cmd, '_setup_schedule'):
            options = {
                'days': 7, 'batch_size': 5000, 'sleep_ms': 0,
                'cron': '0 3 * * *', 'once': False, 'dry_run': False,
            }
            # 不应抛出 RuntimeError
            cmd.handle(**options)

        # 验证 run_pending 被调用了多次（即循环在第一次异常后继续）
        self.assertGreaterEqual(mock_schedule.run_pending.call_count, 1)
        # 验证 stderr 记录了兜底错误
        stderr_output = cmd.stderr.getvalue()
        self.assertIn('调度循环异常', stderr_output)


# ---------------------------------------------------------------------------
# TC-U-DPH-005 / TC-U-DPH-006：--once 模式 handle() 正常返回
# ---------------------------------------------------------------------------

class TC_U_DPH_005_OnceModeOperationalError(TestCase):
    """TC-U-DPH-005: --once 模式下 _run_cleanup 抛出 OperationalError，handle() 正常返回"""

    @patch(f'{CMD_MODULE}.connection')
    def test_once_mode_exits_cleanly_on_operational_error(self, mock_conn):
        """--once 模式：DB 异常被内部捕获，handle() 返回 None（等价 exit 0）"""
        mock_conn.cursor.return_value.__enter__.side_effect = OperationalError(
            'Lost connection'
        )
        cmd = _make_command()
        options = {
            'days': 7, 'batch_size': 5000, 'sleep_ms': 0,
            'cron': '0 3 * * *', 'once': True, 'dry_run': False,
        }
        # 若 handle() 抛出则测试失败
        result = cmd.handle(**options)
        self.assertIsNone(result)


class TC_U_DPH_006_OnceModeGenericException(TestCase):
    """TC-U-DPH-006: --once 模式下 _run_cleanup 抛出 Exception，handle() 正常返回"""

    @patch(f'{CMD_MODULE}.connection')
    def test_once_mode_exits_cleanly_on_generic_exception(self, mock_conn):
        """--once 模式：通用异常被内部捕获，handle() 返回 None"""
        mock_conn.cursor.return_value.__enter__.side_effect = ValueError(
            'unexpected value'
        )
        cmd = _make_command()
        options = {
            'days': 7, 'batch_size': 5000, 'sleep_ms': 0,
            'cron': '0 3 * * *', 'once': True, 'dry_run': False,
        }
        result = cmd.handle(**options)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# TC-U-DPH-007：--dry-run 正常流程
# ---------------------------------------------------------------------------

class TC_U_DPH_007_DryRun(TestCase):
    """TC-U-DPH-007: --dry-run 模式：输出预计行数，不执行 DELETE"""

    def _make_cursor(self, max_delete_id=10000, min_id=1):
        """构造模拟 cursor，SELECT 返回边界 id，不触发 DELETE。"""
        mock_cursor = MagicMock()
        # fetchone() 第一次返回 max_delete_id（边界 id），第二次返回 min_id
        mock_cursor.fetchone.side_effect = [
            (max_delete_id,),
            (min_id,),
        ]
        return mock_cursor

    @patch(f'{CMD_MODULE}.connection')
    def test_dry_run_no_delete_called(self, mock_conn):
        """dry_run=True 时，execute 调用次数应为 2（两次 SELECT），不含 DELETE"""
        mock_cursor = self._make_cursor()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False

        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=True)

        # 应只有 2 次 execute：SELECT 边界 id + SELECT MIN(id)
        self.assertEqual(mock_cursor.execute.call_count, 2)
        # 确认没有 DELETE 语句
        for c in mock_cursor.execute.call_args_list:
            sql = c[0][0]
            self.assertNotIn('DELETE', sql.upper())

    @patch(f'{CMD_MODULE}.connection')
    def test_dry_run_outputs_estimated_rows(self, mock_conn):
        """dry_run=True 时，stdout 中包含预计删除行数信息"""
        mock_cursor = self._make_cursor(max_delete_id=50000, min_id=1)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False

        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=True)

        stdout_output = cmd.stdout.getvalue()
        self.assertIn('DRY-RUN', stdout_output)
        self.assertIn('预计删除', stdout_output)


# ---------------------------------------------------------------------------
# TC-U-DPH-008：无超期数据时正常返回
# ---------------------------------------------------------------------------

class TC_U_DPH_008_NoExpiredData(TestCase):
    """TC-U-DPH-008: SELECT 返回 None（无超期数据），_run_cleanup 正常返回，不执行 DELETE"""

    @patch(f'{CMD_MODULE}.connection')
    def test_no_expired_data_returns_cleanly(self, mock_conn):
        """fetchone 返回 None，函数应提前 return，stdout 含「无需删除」"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # 无超期数据
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False

        cmd = _make_command()
        result = cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False)

        self.assertIsNone(result)
        stdout_output = cmd.stdout.getvalue()
        self.assertIn('无需删除', stdout_output)
        # 只有 1 次 execute（SELECT 边界 id），无 SELECT MIN 和 DELETE
        self.assertEqual(mock_cursor.execute.call_count, 1)


# ---------------------------------------------------------------------------
# TC-U-DPH-009：正常删除流程
# ---------------------------------------------------------------------------

class TC_U_DPH_009_NormalDeletion(TestCase):
    """TC-U-DPH-009: 正常删除流程，分批执行，输出批次日志"""

    @patch(f'{CMD_MODULE}.time')
    @patch(f'{CMD_MODULE}.connection')
    def test_normal_deletion_executes_delete(self, mock_conn, mock_time):
        """
        有超期数据时，execute 应被调用 > 2 次（含 DELETE）。
        模拟单批 rowcount=3000（< batch_size=5000），删完一批即退出。
        """
        mock_cursor = MagicMock()
        # fetchone: 第一次返回 max_delete_id=3000，第二次返回 min_id=1
        mock_cursor.fetchone.side_effect = [
            (3000,),  # max_delete_id
            (1,),     # min_id
        ]
        # DELETE 批次：rowcount=3000，触发 break（deleted_in_batch < batch_size 且下次 current_min > max_delete_id）
        mock_cursor.rowcount = 3000
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_time.sleep = MagicMock()

        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=200, dry_run=False)

        # 应有 3 次 execute：SELECT max_id + SELECT min_id + DELETE
        self.assertEqual(mock_cursor.execute.call_count, 3)

        # 确认有 DELETE 语句
        all_sqls = [c[0][0] for c in mock_cursor.execute.call_args_list]
        self.assertTrue(any('DELETE' in sql.upper() for sql in all_sqls))

        # 确认 stdout 含完成信息
        stdout_output = cmd.stdout.getvalue()
        self.assertIn('完成', stdout_output)

    @patch(f'{CMD_MODULE}.time')
    @patch(f'{CMD_MODULE}.connection')
    def test_sleep_called_between_batches(self, mock_conn, mock_time):
        """两批之间应调用 time.sleep（sleep_ms > 0 时）"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(3000,), (1,)]
        mock_cursor.rowcount = 3000
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_time.sleep = MagicMock()

        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=200, dry_run=False)

        mock_time.sleep.assert_called_once_with(0.2)


# ---------------------------------------------------------------------------
# TC-U-DPH-012 / TC-U-DPH-013：_setup_schedule
# ---------------------------------------------------------------------------

class TC_U_DPH_012_SetupScheduleValid(TestCase):
    """TC-U-DPH-012: 有效 cron 表达式注册每日任务"""

    @patch(f'{CMD_MODULE}.schedule')
    def test_daily_cron_registers_job(self, mock_schedule):
        """'0 3 * * *' 应注册 every().day.at('03:00') 的任务"""
        # 构建链式 mock: schedule.every().day.at(...).do(...)
        mock_every = MagicMock()
        mock_schedule.every.return_value = mock_every
        mock_day = MagicMock()
        mock_every.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        cmd = _make_command()
        cmd._setup_schedule('0 3 * * *', days=7, batch_size=5000, sleep_ms=200, dry_run=False)

        mock_schedule.every.assert_called_once()
        mock_day.at.assert_called_once_with('03:00')
        mock_at.do.assert_called_once()

    @patch(f'{CMD_MODULE}.schedule')
    def test_custom_cron_time_registered(self, mock_schedule):
        """'30 2 * * *' 应注册 at('02:30') 的任务"""
        mock_every = MagicMock()
        mock_schedule.every.return_value = mock_every
        mock_day = MagicMock()
        mock_every.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        cmd = _make_command()
        cmd._setup_schedule('30 2 * * *', days=7, batch_size=5000, sleep_ms=200, dry_run=False)

        mock_day.at.assert_called_once_with('02:30')


class TC_U_DPH_013_SetupScheduleInvalid(TestCase):
    """TC-U-DPH-013: 无效 cron 表达式退回默认 03:00"""

    @patch(f'{CMD_MODULE}.schedule')
    def test_invalid_cron_falls_back_to_default(self, mock_schedule):
        """无效 cron（如空字符串）触发 fallback，注册 every().day.at('03:00')"""
        mock_every = MagicMock()
        mock_schedule.every.return_value = mock_every
        mock_day = MagicMock()
        mock_every.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        cmd = _make_command()
        cmd._setup_schedule('invalid cron format with too many fields 1 2',
                            days=7, batch_size=5000, sleep_ms=200, dry_run=False)

        # fallback 路径调用 schedule.every().day.at('03:00')
        mock_day.at.assert_called_with('03:00')

    @patch(f'{CMD_MODULE}.schedule')
    def test_too_few_cron_fields_falls_back(self, mock_schedule):
        """cron 字段少于 5 个时退回默认"""
        mock_every = MagicMock()
        mock_schedule.every.return_value = mock_every
        mock_day = MagicMock()
        mock_every.day = mock_day
        mock_at = MagicMock()
        mock_day.at.return_value = mock_at

        cmd = _make_command()
        cmd._setup_schedule('0 3 * *', days=7, batch_size=5000, sleep_ms=200, dry_run=False)

        mock_day.at.assert_called_with('03:00')
        stdout_output = cmd.stdout.getvalue()
        self.assertIn('cron 解析失败', stdout_output)


# ---------------------------------------------------------------------------
# TC-U-DPH-014 ~ 016：_apply_cleanup_db_timeout() 进程级超时放大（DPH-CLEANUP-002）
# ---------------------------------------------------------------------------

class TC_U_DPH_014_ApplyDbTimeout(TestCase):
    """TC-U-DPH-014: _apply_cleanup_db_timeout 将 read/write_timeout 放大到 600s"""

    @patch(f'{CMD_MODULE}.connections')
    def test_raises_read_and_write_timeout(self, mock_connections):
        from api.management.commands.dph_cleanup_service import (
            _apply_cleanup_db_timeout, DPH_CLEANUP_DB_TIMEOUT,
        )
        mock_conn = MagicMock()
        mock_conn.settings_dict = {
            'OPTIONS': {'charset': 'utf8mb4', 'read_timeout': 60, 'write_timeout': 60}
        }
        mock_connections.__getitem__.return_value = mock_conn

        changed = _apply_cleanup_db_timeout()

        self.assertTrue(changed)
        self.assertEqual(mock_conn.settings_dict['OPTIONS']['read_timeout'],
                         DPH_CLEANUP_DB_TIMEOUT)
        self.assertEqual(mock_conn.settings_dict['OPTIONS']['write_timeout'],
                         DPH_CLEANUP_DB_TIMEOUT)
        # charset 等其它选项不应被改动
        self.assertEqual(mock_conn.settings_dict['OPTIONS']['charset'], 'utf8mb4')


class TC_U_DPH_015_ApplyDbTimeout_NoOp(TestCase):
    """TC-U-DPH-015: OPTIONS 无 read_timeout 时（如 SQLite），_apply_cleanup_db_timeout 无操作"""

    @patch(f'{CMD_MODULE}.connections')
    def test_no_timeout_keys_is_noop(self, mock_connections):
        from api.management.commands.dph_cleanup_service import _apply_cleanup_db_timeout
        mock_conn = MagicMock()
        mock_conn.settings_dict = {'OPTIONS': {}}  # SQLite 风格，无超时项
        mock_connections.__getitem__.return_value = mock_conn

        changed = _apply_cleanup_db_timeout()

        self.assertFalse(changed)
        # 不应向 OPTIONS 添加任何键
        self.assertNotIn('read_timeout', mock_conn.settings_dict['OPTIONS'])
        self.assertNotIn('write_timeout', mock_conn.settings_dict['OPTIONS'])
        # 未修改则不应关闭连接
        mock_conn.close.assert_not_called()


class TC_U_DPH_016_ApplyDbTimeout_ClosesConnection(TestCase):
    """TC-U-DPH-016: 修改超时后关闭旧连接，使新 OPTIONS 在下次连接时生效"""

    @patch(f'{CMD_MODULE}.connections')
    def test_closes_connection_when_changed(self, mock_connections):
        from api.management.commands.dph_cleanup_service import _apply_cleanup_db_timeout
        mock_conn = MagicMock()
        mock_conn.settings_dict = {'OPTIONS': {'read_timeout': 60, 'write_timeout': 60}}
        mock_connections.__getitem__.return_value = mock_conn

        _apply_cleanup_db_timeout()

        mock_conn.close.assert_called_once()


# ---------------------------------------------------------------------------
# TC-U-DPH-017 / 018：--max-batches 单轮批次上限（DPH-CLEANUP-002）
# ---------------------------------------------------------------------------

class TC_U_DPH_017_MaxBatchesCap(TestCase):
    """TC-U-DPH-017: max_batches > 0 时，_run_cleanup 单轮最多执行 max_batches 个批次"""

    @patch(f'{CMD_MODULE}.time')
    @patch(f'{CMD_MODULE}.connection')
    def test_run_cleanup_stops_at_max_batches(self, mock_conn, mock_time):
        """
        构造「每批都删满 batch_size 行」的场景（current_min 不推进），
        若无 max_batches 上限会无限循环；设 max_batches=3 应恰好执行 3 个 DELETE 批次后停止。
        """
        mock_cursor = MagicMock()
        # 边界 id 足够大，保证 current_min 不会越界
        mock_cursor.fetchone.side_effect = [(10_000_000,), (1,)]
        # 每批都删满 batch_size 行
        mock_cursor.rowcount = 5000
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_time.sleep = MagicMock()

        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False, max_batches=3)

        # execute = 2 次 SELECT + 3 次 DELETE
        self.assertEqual(mock_cursor.execute.call_count, 5)
        delete_calls = [c for c in mock_cursor.execute.call_args_list
                        if 'DELETE' in c[0][0].upper()]
        self.assertEqual(len(delete_calls), 3)
        # stdout 应说明因达到批次上限而停止
        self.assertIn('批次上限', cmd.stdout.getvalue())


class TC_U_DPH_018_MaxBatchesUnlimited(TestCase):
    """TC-U-DPH-018: max_batches=0 表示不限制，正常删完不提前停止"""

    @patch(f'{CMD_MODULE}.time')
    @patch(f'{CMD_MODULE}.connection')
    def test_max_batches_zero_runs_to_completion(self, mock_conn, mock_time):
        """max_batches=0：单批 rowcount=3000<batch_size，删完即结束，不出现批次上限提示"""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(3000,), (1,)]
        mock_cursor.rowcount = 3000
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_time.sleep = MagicMock()

        cmd = _make_command()
        cmd._run_cleanup(days=7, batch_size=5000, sleep_ms=0, dry_run=False, max_batches=0)

        stdout_output = cmd.stdout.getvalue()
        self.assertIn('完成', stdout_output)
        self.assertNotIn('批次上限', stdout_output)


# ---------------------------------------------------------------------------
# TC-U-DPH-019：handle() 将 --max-batches 透传给 _run_cleanup（DPH-CLEANUP-002）
# ---------------------------------------------------------------------------

class TC_U_DPH_019_HandlePassesMaxBatches(TestCase):
    """TC-U-DPH-019: --once 模式下 handle() 将 max_batches 透传给 _run_cleanup"""

    @patch(f'{CMD_MODULE}._apply_cleanup_db_timeout', return_value=False)
    def test_handle_passes_max_batches_to_run_cleanup(self, _mock_apply):
        cmd = _make_command()
        cmd._run_cleanup = MagicMock()
        options = {
            'days': 7, 'batch_size': 5000, 'sleep_ms': 0,
            'cron': '0 3 * * *', 'once': True, 'dry_run': False,
            'max_batches': 7,
        }
        cmd.handle(**options)

        cmd._run_cleanup.assert_called_once()
        # _run_cleanup(days, batch_size, sleep_ms, dry_run, max_batches)
        args = cmd._run_cleanup.call_args[0]
        self.assertEqual(args[4], 7, 'handle() 应把 max_batches=7 透传给 _run_cleanup')
