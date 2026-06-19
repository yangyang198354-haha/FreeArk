"""
test_workorder_v131.py — v1.3.1-WO 工单查看 + 写提案人工审批执行

覆盖：
  work_order.create_from_event：proposed_tool → write_status=PENDING（无则 NONE）
  agent._handle_write_proposal：被拦截写提案的结构化 tool+args 落库
  list API：认证 / 过滤 / source_active（活跃True/恢复False/已删None）/ 分页
  detail API：全文字段 / 404
  approve-write API：非管理员403 / 无提案400 / 执行成功(EXECUTED+IN_PROGRESS) / 失败(FAILED+502)
  resolve API：管理员收单 / 非管理员403

execute_write 全部 mock，不触发真实 PLC 写。
运行：python manage.py test api.tests.test_workorder_v131 --settings=freearkweb.test_settings
"""

from unittest import mock

from django.test import TestCase, tag
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CustomUser, FaultEvent, WorkOrder
from inspection_agent import work_order


def _client(role='admin', username=None):
    username = username or f'wo_{role}'
    user = CustomUser.objects.create_user(username=username, password='pass1234', role=role)
    token, _ = Token.objects.get_or_create(user=user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return c


def _fault(**ov):
    now = timezone.now()
    d = dict(specific_part='3-1-7-702', device_sn='SN-F', product_code='PC', fault_code='E101',
             fault_type='comm', fault_message='通信中断', severity='error',
             first_seen_at=now, last_seen_at=now)
    d.update(ov)
    return FaultEvent.objects.create(**d)


def _wo(fe, **ov):
    d = dict(ticket_id=f'WO-T-{WorkOrder.objects.count()+1:06d}', severity='error',
             source_event_type='fault_event', source_event_id=fe.pk,
             affected_device=f'{fe.device_sn} / {fe.specific_part}', symptom='通信中断')
    d.update(ov)
    return WorkOrder.objects.create(**d)


@tag('integration')
class CreateWorkOrderProposalTest(TestCase):
    def test_proposed_tool_sets_pending(self):
        fe = _fault()
        wo, created = work_order.create_from_event(
            fe, recommended_action='x', proposed_tool='trigger_refresh',
            proposed_args={'specific_part': '3-1-7-702'})
        self.assertTrue(created)
        self.assertEqual(wo.write_status, 'PENDING')
        self.assertEqual(wo.proposed_tool, 'trigger_refresh')
        self.assertEqual(wo.proposed_args, {'specific_part': '3-1-7-702'})

    def test_no_tool_is_none(self):
        fe = _fault()
        wo, _ = work_order.create_from_event(fe, recommended_action='无需写处置')
        self.assertEqual(wo.write_status, 'NONE')
        self.assertEqual(wo.proposed_tool, '')

    def test_agent_blocked_write_persists_structured_proposal(self):
        from inspection_agent.agent import InspectionAgent
        fe = _fault()
        agent = InspectionAgent()
        meta = agent._event_meta(fe)
        pending = {'pending_write': {'tool': 'trigger_refresh',
                                     'args': {'specific_part': '3-1-7-702'}}}
        agent._handle_write_proposal(fe, meta, pending)   # 策略B 默认拦截
        wo = WorkOrder.objects.get(source_event_id=fe.pk)
        self.assertEqual(wo.write_status, 'PENDING')
        self.assertEqual(wo.proposed_tool, 'trigger_refresh')


@tag('integration')
class ListDetailTest(TestCase):
    def setUp(self):
        self.client = _client('user')

    def test_list_unauth_401(self):
        self.assertEqual(APIClient().get('/api/workorders/').status_code, 401)

    def test_list_source_active_flags(self):
        f_active = _fault(is_active=True)
        f_recovered = _fault(is_active=False, specific_part='3-1-7-703')
        _wo(f_active)
        _wo(f_recovered)
        # 第三条：来源事件已删除 → source_active None
        ghost = _wo(f_active, source_event_id=999999)
        resp = self.client.get('/api/workorders/')
        self.assertEqual(resp.status_code, 200)
        by_id = {r['id']: r for r in resp.json()['data']}
        self.assertIs(by_id[ghost.id]['source_active'], None)
        actives = {r['source_event_id']: r['source_active'] for r in resp.json()['data']
                   if r['source_event_id'] != 999999}
        self.assertTrue(actives[f_active.pk])
        self.assertFalse(actives[f_recovered.pk])
        # 恢复的工单应标 fault_cleared
        rec = next(r for r in resp.json()['data'] if r['source_event_id'] == f_recovered.pk)
        self.assertTrue(rec['fault_cleared'])

    def test_list_filter_status(self):
        fe = _fault()
        _wo(fe, status='OPEN')
        _wo(fe, status='RESOLVED', source_event_id=fe.pk + 1)
        resp = self.client.get('/api/workorders/?status=RESOLVED')
        self.assertEqual(resp.json()['total'], 1)

    def test_detail_fields_and_404(self):
        fe = _fault()
        wo = _wo(fe, diagnosis='诊断X', recommended_action='## 报告\n详情',
                 proposed_tool='trigger_refresh', proposed_args={'specific_part': '3-1-7-702'},
                 write_status='PENDING')
        resp = self.client.get(f'/api/workorders/{wo.id}/')
        self.assertEqual(resp.status_code, 200)
        d = resp.json()['data']
        self.assertEqual(d['recommended_action'], '## 报告\n详情')
        self.assertEqual(d['proposed_args'], {'specific_part': '3-1-7-702'})
        self.assertTrue(d['has_proposed_write'])
        self.assertEqual(self.client.get('/api/workorders/888888/').status_code, 404)


@tag('integration')
class ApproveWriteTest(TestCase):
    def setUp(self):
        self.admin = _client('admin')
        self.user = _client('user')
        self.fe = _fault()
        self.wo = _wo(self.fe, proposed_tool='trigger_refresh',
                      proposed_args={'specific_part': '3-1-7-702'}, write_status='PENDING')

    def _url(self, wo=None):
        return f'/api/workorders/{(wo or self.wo).id}/approve-write/'

    def test_non_admin_403(self):
        self.assertEqual(self.user.post(self._url()).status_code, 403)

    def test_no_proposal_400(self):
        plain = _wo(self.fe, source_event_id=self.fe.pk + 1)   # write_status NONE
        self.assertEqual(self.admin.post(self._url(plain)).status_code, 400)

    def test_execute_success_marks_executed_and_in_progress(self):
        with mock.patch('api.langgraph_chat.fa_tools.execute_write',
                        return_value={'success': True, 'summary': '按需采集刷新已触发'}):
            resp = self.admin.post(self._url())
        self.assertEqual(resp.status_code, 200)
        self.wo.refresh_from_db()
        self.assertEqual(self.wo.write_status, 'EXECUTED')
        self.assertEqual(self.wo.status, 'IN_PROGRESS')
        self.assertEqual(self.wo.write_executed_by, 'wo_admin')
        self.assertIsNotNone(self.wo.write_executed_at)

    def test_execute_failure_marks_failed_502(self):
        with mock.patch('api.langgraph_chat.fa_tools.execute_write',
                        return_value={'success': False, 'error': 'PLC 离线'}):
            resp = self.admin.post(self._url())
        self.assertEqual(resp.status_code, 502)
        self.wo.refresh_from_db()
        self.assertEqual(self.wo.write_status, 'FAILED')
        self.assertIn('PLC 离线', self.wo.write_result)

    def test_double_execute_blocked(self):
        self.wo.write_status = 'EXECUTED'
        self.wo.save(update_fields=['write_status'])
        self.assertEqual(self.admin.post(self._url()).status_code, 400)


@tag('integration')
class ResolveTest(TestCase):
    def setUp(self):
        self.admin = _client('admin')
        self.user = _client('user')
        self.fe = _fault()
        self.wo = _wo(self.fe, status='OPEN')

    def test_user_403(self):
        self.assertEqual(self.user.post(f'/api/workorders/{self.wo.id}/resolve/').status_code, 403)

    def test_admin_resolves(self):
        resp = self.admin.post(f'/api/workorders/{self.wo.id}/resolve/')
        self.assertEqual(resp.status_code, 200)
        self.wo.refresh_from_db()
        self.assertEqual(self.wo.status, 'RESOLVED')
        self.assertEqual(self.wo.resolved_by, 'wo_admin')
        self.assertIsNotNone(self.wo.resolved_at)
