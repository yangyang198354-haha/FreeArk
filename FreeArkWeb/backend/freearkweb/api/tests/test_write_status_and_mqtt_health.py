"""
test_write_status_and_mqtt_health.py (v1.4.2 写操作三改进项回归测试)
=====================================================================

三组独立的回归测试，对应本轮的三项改动：

1. TestPlcWriteTimeoutCommand —— P1：plc_write_timeout_service 管理命令
   （把长期 pending 的 PLCWriteRecord 标 timeout，支持 dry-run / once / 分批）

2. TestMqttConsumerHealthMonitor —— P1：MQTT 消费者静默失聪监控
   （mqtt_consumer.health_snapshot() + mqtt_consumer_service._monitor_service
    的失聪自杀判定逻辑，不真正起 MQTT 连接）

3. TestWriteStatusPollingEcho —— P2：写操作后 UX 回显
   （fa_tools._poll_write_status_until_final + _summarize_polled_status
    + get_write_status 工具 + execute_write 自动轮询，不走 HTTP）

注意：
- 测试集不依赖真实 MQTT / tier2_write FreeArkClient，全部在单测里造数据。
- 使用 Django TestCase（走 test_settings 的 SQLite 内存库），不需要外部服务。
- 用 @override_settings 控制 FREEARK_POC_MOCK 等环境变量，避免影响其他用例。
"""

import os
import time as _time
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from api.models import PLCWriteRecord


# =========================================================================
# 辅助：快速造一条 PLCWriteRecord
# =========================================================================
_NEXT_REQ_SEQ = 0


def _mk_write(batch_id: str, *, status: str = 'pending',
              specific_part: str = '3-1-7-702',
              param_name: str = 'study_room_switch',
              created_at_offset_sec: int = 0) -> PLCWriteRecord:
    """构造 PLCWriteRecord 并入库。

    注意：created_at 是 auto_now_add=True，save() 时会覆盖 create 里的赋值；
    因此用 create 建好行，再用 UPDATE 改 created_at（模拟老行），
    避免模型层 auto_now_add 干预。这样能稳定构造「created_at 早于 NOW()-TTL」
    的 pending 行让 mark_write_timeout 命中。
    """
    global _NEXT_REQ_SEQ
    _NEXT_REQ_SEQ += 1
    r = PLCWriteRecord.objects.create(
        request_id=f'test-wr-{os.getpid()}-{_NEXT_REQ_SEQ}',
        batch_request_id=batch_id,
        specific_part=specific_part,
        param_name=param_name,
        old_value='',
        new_value='1',
        operator='energy-agent::tester',
        status=status,
        channel='s7',
        error_message='',
    )
    if created_at_offset_sec:
        then = timezone.now() - timedelta(seconds=created_at_offset_sec)
        # 绕过 auto_now_add，直接在 DB 层改 created_at
        PLCWriteRecord.objects.filter(pk=r.pk).update(created_at=then, acked_at=then if status != 'pending' else None)
        r.refresh_from_db()
    return r


# =========================================================================
# 1. P1 —— plc_write_timeout_service management command
# =========================================================================
class TestPlcWriteTimeoutCommand(TestCase):
    """验证 mark_write_timeout：只标「老 pending」，不碰 young/success/failed。"""

    def _run_once(self, ttl_seconds: int = 90, dry_run: bool = False):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        err = StringIO()
        call_command(
            'plc_write_timeout_service',
            '--once',
            '--ttl-seconds', str(ttl_seconds),
            '--batch-size', '10',
            *(('--dry-run',) if dry_run else ()),
            stdout=out, stderr=err,
        )
        return out.getvalue() + err.getvalue()

    def test_marks_old_pending_and_preserves_young_and_done(self):
        batch = 'bat-t1-old-young-mixed'
        # 4 条：1 条 200s pending（应 timeout）、1 条 10s pending（保留）、
        #       1 条 200s success（保留）、1 条 200s failed（保留）
        r_old_p = _mk_write(batch, status='pending', created_at_offset_sec=200,
                            param_name='study_room_switch')
        r_young_p = _mk_write(batch, status='pending', created_at_offset_sec=10,
                              param_name='living_room_temp_setting')
        r_done_s = _mk_write(batch, status='success', created_at_offset_sec=200,
                             param_name='operation_mode')
        r_done_f = _mk_write(batch, status='failed', created_at_offset_sec=200,
                             param_name='master_bedroom_switch')

        output = self._run_once(ttl_seconds=90, dry_run=False)
        # 输出里要含「候选=4/1」「标记=1」之类的成功信息
        self.assertIn('候选', output)
        self.assertIn('实际标记', output)

        r_old_p.refresh_from_db(); r_young_p.refresh_from_db()
        r_done_s.refresh_from_db(); r_done_f.refresh_from_db()
        self.assertEqual(r_old_p.status, 'timeout',
                         'ttl 过期的 pending 应被标 timeout')
        self.assertIn('marked_timeout', (r_old_p.error_message or ''),
                      'timeout 行 error_message 应写 RCA 提示')
        self.assertEqual(r_young_p.status, 'pending',
                         'ttl 未过期的 pending 不应被动')
        self.assertEqual(r_done_s.status, 'success', 'success 永远不动')
        self.assertEqual(r_done_f.status, 'failed', 'failed 永远不动')

    def test_dry_run_never_writes_db(self):
        batch = 'bat-t2-dryrun'
        r = _mk_write(batch, status='pending', created_at_offset_sec=500,
                      param_name='study_room_switch')
        out = self._run_once(ttl_seconds=90, dry_run=True)
        self.assertIn('dry-run', out)
        r.refresh_from_db()
        self.assertEqual(r.status, 'pending', 'dry-run 不应该改任何行的状态')

    def test_respects_ttl_threshold(self):
        batch = 'bat-t3-ttl-threshold'
        ttl = 60
        # 刚好 TTL-1s = 59s 不标；TTL+1s = 61s 标
        r59 = _mk_write(batch, status='pending', created_at_offset_sec=59,
                        param_name='study_room_switch')
        r61 = _mk_write(batch, status='pending', created_at_offset_sec=61,
                        param_name='living_room_switch')
        self._run_once(ttl_seconds=ttl, dry_run=False)
        r59.refresh_from_db(); r61.refresh_from_db()
        self.assertEqual(r59.status, 'pending')
        self.assertEqual(r61.status, 'timeout')


# =========================================================================
# 2. P1 —— MQTT 消费者静默失聪自杀判定（不连真实 broker）
# =========================================================================
class TestMqttConsumerHealthMonitor(TestCase):
    """用 fake lock/时间，验证 health_snapshot + _monitor_service 判定。"""

    def test_health_snapshot_returns_empty_when_never_started(self):
        """进程刚起、MQTT 未连接时，应返回 is_running=False/conn=False 且不崩溃。"""
        # 直接 new 一个不 start 的 consumer（不连真实 broker）
        from api.mqtt_consumer import MQTTConsumer
        c = MQTTConsumer()
        snap = c.health_snapshot()
        # 未 start → is_running 必 False
        self.assertFalse(snap['is_running'])
        self.assertIn('energy_qsize', snap)
        self.assertIn('general_qsize', snap)
        self.assertIn('ondemand_qsize', snap)
        # 都是 int（含 0），不该是 None
        for k in ('energy_qsize', 'general_qsize', 'ondemand_qsize'):
            self.assertIsInstance(snap[k], int)

    def test_monitor_service_suicide_on_sustained_silence(self):
        """连续 3 轮（默认 SILENCE_SUICIDE_CONSECUTIVE_ROUNDS）静默失聪 → sys.exit(3)。"""
        # 为避免碰 MQTT 连接，直接测试 _monitor_service 的判定分支：
        # 用 mock 掉 get_consumer_health_snapshot 返回固定静默快照
        import sys as _sys
        from io import StringIO
        from django.core.management import CommandParser
        from api.management.commands.mqtt_consumer_service import (
            Command, SILENCE_SUICIDE_CONSECUTIVE_ROUNDS,
        )
        fake_snap = {
            'is_running': True,
            'client_connected': True,
            'seconds_since_last_msg': 500,    # >120s：已经静默
            'seconds_since_connect': 500,
            'seconds_until_idle_deadline': -380,
            'energy_qsize': 0,
            'general_qsize': 0,
            'ondemand_qsize': 0,
        }
        cmd = Command()
        with mock.patch(
            'api.management.commands.mqtt_consumer_service.get_consumer_health_snapshot',
            return_value=fake_snap,
        ):
            # 连续 SILENCE_SUICIDE_CONSECUTIVE_ROUNDS 轮：前 N-1 轮不自杀，第 N 轮 exit(3)
            for i in range(SILENCE_SUICIDE_CONSECUTIVE_ROUNDS - 1):
                try:
                    cmd._monitor_service(interval=60)
                except SystemExit:  # pragma: no cover - 不该发生
                    self.fail(f'第 {i+1} 轮不该触发自杀')
            # 第 N 轮应该 sys.exit(3)
            with self.assertRaises(SystemExit) as ctx:
                cmd._monitor_service(interval=60)
            self.assertEqual(ctx.exception.code, 3)

    def test_monitor_service_clears_counter_when_message_resumes(self):
        """中间有一轮恢复消息后，连续失聪计数应清零。"""
        import sys as _sys
        from api.management.commands.mqtt_consumer_service import (
            Command, SILENCE_SUICIDE_CONSECUTIVE_ROUNDS,
        )
        silent = {
            'is_running': True, 'client_connected': True,
            'seconds_since_last_msg': 500, 'seconds_since_connect': 500,
            'seconds_until_idle_deadline': -380,
            'energy_qsize': 0, 'general_qsize': 0, 'ondemand_qsize': 0,
        }
        recovered = dict(silent)
        recovered['seconds_since_last_msg'] = 1  # 恢复：1 秒前刚有消息

        cmd = Command()
        with mock.patch(
            'api.management.commands.mqtt_consumer_service.get_consumer_health_snapshot',
            side_effect=[silent, silent, recovered, silent, silent],
        ):
            # 2 轮失聪 + 1 轮恢复 + 2 轮失聪 → 还不自杀（第 5 轮是连续第 2 轮，未到 3）
            for i in range(5):
                try:
                    cmd._monitor_service(interval=60)
                except SystemExit:
                    self.fail(f'第 {i+1} 轮不应自杀（中间恢复清零了计数）')

    def test_module_wrapper_get_consumer_health_snapshot_handles_broken_singleton(self):
        """import-time 没启动 MQTT 时，get_consumer_health_snapshot() 至少返回 dict，不抛。"""
        from api.mqtt_consumer import get_consumer_health_snapshot
        snap = get_consumer_health_snapshot()
        self.assertIsInstance(snap, dict)
        self.assertIn('is_running', snap)


# =========================================================================
# 3. P2 —— 写操作后 UX 回显（轮询 + get_write_status + execute_write 自动轮询）
# =========================================================================
class TestWriteStatusPollingEcho(TestCase):
    """验证写操作后 ORM 轮询、摘要、get_write_status 工具、execute_write 自动轮询。"""

    # ------------------------------------------------------------------
    # 3.1 _poll_write_status_until_final 的纯逻辑
    # ------------------------------------------------------------------
    def test_poll_detects_all_success(self):
        batch = 'bat-poll-success'
        _mk_write(batch, status='success', param_name='study_room_switch')
        _mk_write(batch, status='success', param_name='living_room_switch')
        from api.langgraph_chat.fa_tools import _poll_write_status_until_final
        p = _poll_write_status_until_final(batch, total_seconds=1, step_seconds=1)
        self.assertEqual(p['final_status'], 'success')
        self.assertFalse(p['still_pending'])
        self.assertEqual(p['records_total'], 2)
        self.assertEqual(p['records_success'], 2)
        self.assertEqual(p['records_pending'], 0)

    def test_poll_detects_timeout_status(self):
        """由 P1 管理命令标 timeout 的行，也应被轮询层视为「终态」。"""
        batch = 'bat-poll-timeout'
        r = _mk_write(batch, status='pending', created_at_offset_sec=200,
                      param_name='master_bedroom_switch')
        # 手动模拟 P1：标成 timeout
        PLCWriteRecord.objects.filter(pk=r.pk).update(
            status='timeout', error_message='marked_timeout: age>90s ...')
        from api.langgraph_chat.fa_tools import _poll_write_status_until_final
        p = _poll_write_status_until_final(batch, total_seconds=1, step_seconds=1)
        self.assertEqual(p['final_status'], 'timeout')
        self.assertEqual(p['records_timeout'], 1)
        self.assertFalse(p['still_pending'])

    def test_poll_returns_still_pending_when_record_keeps_pending(self):
        """全程一直 pending → still_pending=True，final_status='pending'。"""
        batch = 'bat-poll-pending'
        _mk_write(batch, status='pending', param_name='study_room_switch')
        from api.langgraph_chat.fa_tools import _poll_write_status_until_final
        # 只用 1 轮（total=step=1s），避免测试等 30s
        p = _poll_write_status_until_final(batch, total_seconds=1, step_seconds=1)
        self.assertTrue(p['still_pending'])
        self.assertEqual(p['final_status'], 'pending')
        self.assertEqual(p['polled_rounds'], 1)

    # ------------------------------------------------------------------
    # 3.2 _summarize_polled_status 中文摘要
    # ------------------------------------------------------------------
    def test_summary_success_mentions_all_success_and_no_fail_lines(self):
        from api.langgraph_chat.fa_tools import (
            _poll_write_status_until_final, _summarize_polled_status)
        batch = 'bat-sum-ok'
        _mk_write(batch, status='success', param_name='study_room_switch')
        _mk_write(batch, status='success', param_name='living_room_switch')
        p = _poll_write_status_until_final(batch, total_seconds=1, step_seconds=1)
        s = _summarize_polled_status(p, batch_id=batch)
        self.assertIn('全部写成功', s)
        self.assertNotIn('失败', s.split('写入回执状态')[0])

    def test_summary_failed_mentions_error_message(self):
        from api.langgraph_chat.fa_tools import (
            _poll_write_status_until_final, _summarize_polled_status)
        batch = 'bat-sum-err'
        r = _mk_write(batch, status='failed', param_name='study_room_switch')
        # 模拟 PLC ack：写入失败原因
        PLCWriteRecord.objects.filter(pk=r.pk).update(
            error_message='PLC NACK: 地址未响应, code=0x20')
        p = _poll_write_status_until_final(batch, total_seconds=1, step_seconds=1)
        s = _summarize_polled_status(p, batch_id=batch)
        self.assertIn('全部写失败', s)
        self.assertIn('地址未响应', s)

    def test_summary_pending_hints_use_get_write_status(self):
        from api.langgraph_chat.fa_tools import (
            _poll_write_status_until_final, _summarize_polled_status)
        batch = 'bat-sum-pending'
        _mk_write(batch, status='pending', param_name='study_room_switch')
        p = _poll_write_status_until_final(batch, total_seconds=1, step_seconds=1)
        s = _summarize_polled_status(p, batch_id=batch)
        self.assertIn('仍在等待 PLC 回执', s)
        self.assertIn('get_write_status', s)

    # ------------------------------------------------------------------
    # 3.3 get_write_status 工具（走 ORM，不 HTTP）
    # ------------------------------------------------------------------
    def test_get_write_status_tool_returns_summary_and_data(self):
        from api.langgraph_chat.fa_tools import get_write_status
        batch = 'bat-gws-1'
        r = _mk_write(batch, status='success', param_name='operation_mode')
        # tool.func 是真实的 @tool 包装内部函数
        out = get_write_status.invoke({'batch_request_id': batch})
        self.assertTrue(out.get('success'), f'工具应返回 success=True：{out}')
        self.assertIn('summary', out)
        self.assertIn('全部写成功', out['summary'])
        self.assertIn('data', out)
        self.assertEqual(out['data'].get('records_total'), 1)

    def test_get_write_status_tool_rejects_empty(self):
        from api.langgraph_chat.fa_tools import get_write_status
        out = get_write_status.invoke({'batch_request_id': '   '})
        self.assertFalse(out.get('success'))
        self.assertIn('缺少', out.get('error', ''))

    # ------------------------------------------------------------------
    # 3.4 execute_write 自动轮询：模拟 handler 返回 batch_request_id，
    #     不用 HTTP，用 ORM 直接造一条 PLCWriteRecord（先 pending 再改 success）
    # ------------------------------------------------------------------
    def test_execute_write_auto_poll_appends_final_summary(self):
        batch = 'bat-ew-auto'
        # 先建一条 pending
        r = _mk_write(batch, status='pending', param_name='study_room_switch')

        def fake_handler(params):
            # 模拟 set_device_params handler 返回的 envelope（success + data.batch_request_id）
            return {
                'success': True,
                'summary': '设备参数写操作已下发，状态=pending（mock handler）',
                'data': {'batch_request_id': batch, 'item_count': 1, 'status': 'pending'},
            }

        from api.langgraph_chat import fa_tools
        # mock 三件套：(a) _MOCK=False 不走 canned，(b) TIER2_HANDLERS 有 fake_handler，
        #            (c) 轮询期间把 pending 改成 success（用第 1 轮后回调）
        with mock.patch.object(fa_tools, '_MOCK', False), \
             mock.patch.object(fa_tools, 'TIER2_HANDLERS',
                               {'freeark_write_device_params': fake_handler}), \
             mock.patch.object(fa_tools, 'time', spec=_time):

            # 让轮询在第 1 次 sleep 后把记录改成 success，模拟 MQTT ack 入库
            def fake_sleep(sec):
                nonlocal r
                PLCWriteRecord.objects.filter(pk=r.pk).update(status='success')
            fa_tools.time.sleep.side_effect = fake_sleep
            # time.monotonic / time 也得配，避免 AttributeError
            fa_tools.time.monotonic = lambda: 1.0
            fa_tools.time.side_effect = None

            out = fa_tools.execute_write(
                'set_device_params',
                {'specific_part': '3-1-7-702',
                 'items': [{'param_name': 'study_room_switch', 'new_value': '1'}]},
                operator_override='energy-agent::tester',
            )

        # 返回的 summary 应包含「✅ 全部写成功」——证明自动轮询把终态注入了
        self.assertTrue(out.get('success'), f'execute_write 应 success：{out}')
        self.assertIn('write_status', out)
        self.assertEqual(out['write_status'].get('final_status'), 'success')
        self.assertIn('✅ 全部写成功', out.get('summary', ''))
