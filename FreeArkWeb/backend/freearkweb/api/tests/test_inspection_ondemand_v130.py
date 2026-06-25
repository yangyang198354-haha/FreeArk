"""
test_inspection_ondemand_v130.py — v1.3.0-AOW 按需巡检 + 工作日志

覆盖：
  audit→InspectionLog 双写（WORKORDER_CREATED/WRITE_BLOCKED 映射、脱敏、失败不抛）
  trigger API：202 / 409 重复 / 429 并发 / 404 / 400 / 401 / DONE 可重触发
  status API：返回 inspection_status + work_order_id
  logs API：过滤（event_type/specific_part/result）+ 分页 + 认证
  _run_inspection_thread：调用 process_event + 记 started/completed；异常重置 PENDING

systemctl/LLM/线程全部 mock，不依赖真实 systemd / DeepSeek / 后台线程。
运行：
    python manage.py test api.tests.test_inspection_ondemand_v130 \\
        --settings=freearkweb.test_settings --verbosity=2
"""

from unittest import mock

from django.test import TestCase, tag
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CondensationWarningEvent, FaultEvent, InspectionLog, WorkOrder
from inspection_agent import audit


def _authed_client(username="ond_v130"):
    from api.models import CustomUser
    user = CustomUser.objects.create_user(username=username, password="pass1234", role="operator")
    token, _ = Token.objects.get_or_create(user=user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return c


def _fault(seconds_ago=0, **ov):
    now = timezone.now() - timezone.timedelta(seconds=seconds_ago)
    d = dict(specific_part='3-1-7-702', device_sn='SN-F', product_code='PC', fault_code='E101',
             fault_type='comm', fault_message='通信中断', severity='error',
             first_seen_at=now, last_seen_at=now)
    d.update(ov)
    return FaultEvent.objects.create(**d)


def _cw(seconds_ago=0, **ov):
    now = timezone.now() - timezone.timedelta(seconds=seconds_ago)
    d = dict(specific_part='3-1-8-801', device_sn='SN-C', product_code='PC',
             warning_type='结露预警', warning_message='结露报警',
             first_seen_at=now, last_seen_at=now)
    d.update(ov)
    return CondensationWarningEvent.objects.create(**d)


@tag('integration')
class AuditDoubleWriteTest(TestCase):
    """audit.* → InspectionLog 双写。"""

    def test_workorder_created_persists_row(self):
        audit.log_workorder_created(42, 'fault_event', '3-1-7-702', 'WO-20260616-000001', 'error')
        row = InspectionLog.objects.get()
        self.assertEqual(row.step, 'WORKORDER_CREATED')
        self.assertEqual(row.result, 'SUCCESS')
        self.assertEqual(row.source_event_id, 42)
        self.assertEqual(row.work_order_ticket, 'WO-20260616-000001')
        self.assertEqual(row.event_type_display, '故障事件')

    def test_write_blocked_maps_step(self):
        audit.log_write_blocked(7, 'condensation_warning_event', '3-1-8-801',
                                'set_device_params', {'items': []}, 'POLICY_B_NO_AUTO_WRITE')
        row = InspectionLog.objects.get()
        self.assertEqual(row.step, 'WRITE_BLOCKED')       # 由 POLICY_B 映射
        self.assertEqual(row.result, 'BLOCKED')
        self.assertEqual(row.event_type_display, '结露预警事件')

    def test_lifecycle_steps_persist(self):
        audit.log_process_started(1, 'fault_event', 'x')
        audit.log_event_skipped(1, 'fault_event', 'x')
        audit.log_decision_fallback(1, 'fault_event', 'x', 'TimeoutError', 'boom', timeout=True)
        audit.log_process_completed(1, 'fault_event', 'x', outcome='DONE')
        steps = set(InspectionLog.objects.values_list('step', flat=True))
        self.assertEqual(steps, {'PROCESS_STARTED', 'EVENT_SKIPPED',
                                 'DECISION_TIMEOUT', 'PROCESS_COMPLETED'})

    def test_step_detail_scrubbed(self):
        audit.log_write_executed(1, 'fault_event', 'x', 'set_device_params',
                                 {'设定温度': '24', 'api_key': 'sk-leak'}, 'SUCCESS')
        row = InspectionLog.objects.get()
        self.assertEqual(row.step_detail['args']['api_key'], audit._REDACTED)
        self.assertNotIn('sk-leak', str(row.step_detail))

    def test_persist_failure_does_not_raise(self):
        with mock.patch('api.models.InspectionLog.objects.create', side_effect=RuntimeError('db down')):
            # 不应抛出（REQ-NFR-006）
            rec = audit.log_workorder_created(1, 'fault_event', 'x', 'WO-1', 'error')
        self.assertEqual(rec['event_type'], 'WORKORDER_CREATED')
        self.assertEqual(InspectionLog.objects.count(), 0)


@tag('integration')
class TriggerApiTest(TestCase):
    def setUp(self):
        self.client = _authed_client("trig_v130")
        self.fe = _fault()

    def _url(self, et='fault_event', eid=None):
        return f'/api/inspection/trigger/{et}/{eid or self.fe.pk}/'

    def test_unauth_401(self):
        from rest_framework.test import APIClient as AC
        self.assertEqual(AC().post(self._url()).status_code, 401)

    def test_bad_event_type_400(self):
        resp = self.client.post(self._url(et='bogus'))
        self.assertEqual(resp.status_code, 400)

    def test_missing_event_404(self):
        resp = self.client.post(self._url(eid=999999))
        self.assertEqual(resp.status_code, 404)

    def test_trigger_202_sets_in_progress(self):
        with mock.patch('api.views_inspection.threading.Thread') as T:
            resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()['status'], 'IN_PROGRESS')
        self.fe.refresh_from_db()
        self.assertEqual(self.fe.inspection_status, 'IN_PROGRESS')
        T.assert_called_once()        # 后台线程被启动

    def test_trigger_409_when_in_progress(self):
        self.fe.inspection_status = 'IN_PROGRESS'
        self.fe.inspection_started_at = timezone.now()   # 新鲜在巡，非陈旧
        self.fe.save(update_fields=['inspection_status', 'inspection_started_at'])
        with mock.patch('api.views_inspection.threading.Thread'):
            resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 409)

    def test_trigger_429_when_busy_elsewhere(self):
        # 另一条事件正在巡检（新鲜 started_at，非陈旧）→ 占用全局并发闸门
        _cw(inspection_status='IN_PROGRESS', inspection_started_at=timezone.now())
        with mock.patch('api.views_inspection.threading.Thread'):
            resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 429)
        self.fe.refresh_from_db()
        self.assertEqual(self.fe.inspection_status, 'PENDING')   # 未被认领

    def test_stale_in_progress_reclaimed_then_trigger_succeeds(self):
        # 另一条事件 IN_PROGRESS 但 started_at 远早于阈值（疑似崩溃/旧Agent遗留）
        stale = _cw(inspection_status='IN_PROGRESS',
                    inspection_started_at=timezone.now() - timezone.timedelta(hours=2))
        with mock.patch('api.views_inspection.threading.Thread'):
            resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 202)          # 陈旧被回收，闸门放行
        stale.refresh_from_db()
        self.assertEqual(stale.inspection_status, 'PENDING')   # 陈旧已复位
        self.assertIsNone(stale.inspection_started_at)
        self.fe.refresh_from_db()
        self.assertEqual(self.fe.inspection_status, 'IN_PROGRESS')

    def test_own_stale_in_progress_can_retrigger(self):
        # 本事件自身卡在陈旧 IN_PROGRESS → 应被回收后重新认领，而非永久 409
        self.fe.inspection_status = 'IN_PROGRESS'
        self.fe.inspection_started_at = timezone.now() - timezone.timedelta(hours=2)
        self.fe.save(update_fields=['inspection_status', 'inspection_started_at'])
        with mock.patch('api.views_inspection.threading.Thread'):
            resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 202)
        self.fe.refresh_from_db()
        self.assertEqual(self.fe.inspection_status, 'IN_PROGRESS')

    def test_retrigger_done_allowed(self):
        self.fe.inspection_status = 'DONE'
        self.fe.save(update_fields=['inspection_status'])
        with mock.patch('api.views_inspection.threading.Thread'):
            resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, 202)
        self.fe.refresh_from_db()
        self.assertEqual(self.fe.inspection_status, 'IN_PROGRESS')


@tag('integration')
class StatusApiTest(TestCase):
    def setUp(self):
        self.client = _authed_client("stat_v130")
        self.fe = _fault(inspection_status='DONE', inspection_started_at=timezone.now())

    def test_status_fields(self):
        WorkOrder.objects.create(
            ticket_id='WO-20260616-000009', severity='error', source_event_type='fault_event',
            source_event_id=self.fe.pk, affected_device='SN-F / 3-1-7-702', symptom='通信中断')
        resp = self.client.get(f'/api/inspection/status/fault_event/{self.fe.pk}/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['inspection_status'], 'DONE')
        self.assertIsNotNone(data['inspection_started_at'])
        self.assertEqual(data['work_order_id'], 'WO-20260616-000009')

    def test_status_missing_404(self):
        self.assertEqual(
            self.client.get('/api/inspection/status/fault_event/888888/').status_code, 404)


@tag('integration')
class LogsApiTest(TestCase):
    def setUp(self):
        self.client = _authed_client("logs_v130")
        # 播种日志
        audit.log_process_started(1, 'fault_event', '3-1-7-702')
        audit.log_workorder_created(1, 'fault_event', '3-1-7-702', 'WO-1', 'error')
        audit.log_write_blocked(2, 'condensation_warning_event', '3-1-8-801',
                                'set_device_params', {'items': []}, 'POLICY_B_NO_AUTO_WRITE')

    def test_unauth_401(self):
        self.assertEqual(APIClient().get('/api/inspection/logs/').status_code, 401)

    def test_list_all(self):
        resp = self.client.get('/api/inspection/logs/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertEqual(body['total'], 3)
        self.assertEqual(len(body['data']), 3)

    def test_filter_event_type(self):
        resp = self.client.get('/api/inspection/logs/?event_type=condensation_warning_event')
        self.assertEqual(resp.json()['total'], 1)

    def test_filter_result(self):
        resp = self.client.get('/api/inspection/logs/?result=BLOCKED')
        body = resp.json()
        self.assertEqual(body['total'], 1)
        self.assertEqual(body['data'][0]['step'], 'WRITE_BLOCKED')

    def test_filter_specific_part(self):
        resp = self.client.get('/api/inspection/logs/?specific_part=3-1-8')
        self.assertEqual(resp.json()['total'], 1)

    def test_pagination(self):
        resp = self.client.get('/api/inspection/logs/?page=1&page_size=2')
        body = resp.json()
        self.assertEqual(body['total'], 3)
        self.assertEqual(len(body['data']), 2)
        self.assertEqual(body['page_size'], 2)


@tag('integration')
class RunThreadTest(TestCase):
    """直接调用 _run_inspection_thread（patch 掉 connection.close 与 InspectionAgent）。"""

    def test_thread_runs_process_event_and_logs(self):
        from api import views_inspection
        fe = _fault()

        class _FakeAgent:
            def process_event(self, event):
                event.inspection_status = 'DONE'
                event.save(update_fields=['inspection_status'])

        with mock.patch('inspection_agent.agent.InspectionAgent', _FakeAgent), \
             mock.patch('django.db.connection.close'):
            views_inspection._run_inspection_thread('fault_event', fe.pk)

        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'DONE')
        steps = set(InspectionLog.objects.values_list('step', flat=True))
        self.assertIn('PROCESS_STARTED', steps)
        self.assertIn('PROCESS_COMPLETED', steps)

    def test_thread_resets_pending_on_exception(self):
        from api import views_inspection
        fe = _fault(inspection_status='IN_PROGRESS', inspection_started_at=timezone.now())

        class _BoomAgent:
            def process_event(self, event):
                raise RuntimeError('llm exploded')

        with mock.patch('inspection_agent.agent.InspectionAgent', _BoomAgent), \
             mock.patch('django.db.connection.close'):
            views_inspection._run_inspection_thread('fault_event', fe.pk)

        fe.refresh_from_db()
        self.assertEqual(fe.inspection_status, 'PENDING')
        self.assertIsNone(fe.inspection_started_at)
