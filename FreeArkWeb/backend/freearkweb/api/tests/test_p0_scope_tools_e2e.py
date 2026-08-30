"""
E2E / 集成测试 — v1.13.0 P0 落地回归（Scope 新分类 + owner 自写工具 + get_write_status
跨户信息泄露修补）

共 7 组用例（30 条断言）：
  S1 ScopeEnforcer.check_and_enforce 三分类：
     SCOPED_QUERY_TOOLS（注入 _bound_specific_parts / 校验显式 sp）、
     OWNER_SELF_TOOLS（注入 _user_id / 对 admin 拒绝）、
     SCOPED_SINGLE_PART_TOOLS 新成员 get_device_params（sp 单/多/越权三种行为）。
  S2 UserScope 新字段 user_id：build_user_scope(owner) 正确填 user.pk；
     admin 路径为 None。
  S3 _extract_write_records_from_handler：三种信封形态全解析、
     success=False/格式错安全 fallback 空列表。
  S4 get_write_status 跨户隔离：
     batch 含 2 条 3-1-7-702（自家）+ 1 条 3-1-7-303（邻居），
     走 tier1 handler 全量返回后，_bound_specific_parts=['3-1-7-702']
     过滤后只剩 2 条；邻居身份、admin 不过滤三类行为均正确。
  S5 execute_write 进程内自写（INLINE_SET_PERSONA__）：
     operator_override=user.pk → 直接 ORM 写 user.persona，成功信封包含
     对应 summary；CustomUser 真数据库回读验证持久化。
  S6 工具表一致性：ENERGY_TOOLS 全是 @tool FunctionDef、
     WRITE_TOOLS ⊆ _WRITE_TOOL_TO_HANDLER、
     SCOPED_* / OWNER_SELF 分类条目均有同名 @tool、
     TOOLS_BY_EXPERT["freeark-expert"] 含 5 件新工具。
  S7 orchestrator gate 批准二次校验：
     set_persona 命中 OWNER_SELF_TOOLS → specific_part 校验被跳过，
     不抛 ScopeViolationError；set_device_params 空 sp 时仍拦截。

运行：
  cd FreeArkWeb/backend/freearkweb
  $env:PYTHONDONTWRITEBYTECODE='1'
  python manage.py test api.tests.test_p0_scope_tools_e2e \
      --settings=freearkweb.test_settings --verbosity=2
"""
import os
import unittest
from unittest import mock

from asgiref.sync import async_to_sync

from django.test import TestCase, SimpleTestCase, tag

from api.models import CustomUser, OwnerUserBinding, PLCWriteRecord  # noqa: F401


# =========================================================================
# 共用 mock data / helpers
# =========================================================================

def _owner_scope(*, user_id=1001, parts=('3-1-7-702',)):
    from api.langgraph_chat.user_scope import UserScope
    return UserScope(role='user', user_id=user_id,
                     bound_specific_parts=frozenset(parts))


# =========================================================================
# S1 — ScopeEnforcer.check_and_enforce 三分类行为
# =========================================================================
@tag('unit', 'scope')
class ScopeEnforcerCategoryTests(SimpleTestCase):

    # 1.1 SCOPED_QUERY_TOOLS: get_write_status
    def test_scoped_query_injects_bound_parts_to_owner(self):
        """owner 单绑定 → get_write_status 注入 _bound_specific_parts。"""
        from api.langgraph_chat.scope_enforcer import check_and_enforce
        scope = _owner_scope(user_id=42, parts=('3-1-7-702',))
        args_out, note = check_and_enforce(
            'get_write_status', {'batch_request_id': 'some-uuid'}, scope)
        self.assertIsNotNone(args_out, note or '应通过')
        self.assertEqual(args_out['_bound_specific_parts'], ['3-1-7-702'])
        self.assertNotIn('_user_id', args_out)  # SCOPED_QUERY 不注入 user_id

    def test_scoped_query_rejects_explicit_sp_outside_bound(self):
        """owner 显式传了 sp=邻居 → 返回 None+拒绝提示（防止绕过）。"""
        from api.langgraph_chat.scope_enforcer import check_and_enforce
        scope = _owner_scope(user_id=42, parts=('3-1-7-702',))
        args_out, note = check_and_enforce(
            'get_write_status',
            {'batch_request_id': 'x', 'specific_part': '3-1-7-303'},
            scope)
        self.assertIsNone(args_out)
        self.assertIn('无权查询', note or '')

    def test_scoped_query_bypasses_for_admin(self):
        """admin (scope=None) → 直通，不注入 bound。"""
        from api.langgraph_chat.scope_enforcer import check_and_enforce
        args_in = {'batch_request_id': 'b1'}
        args_out, note = check_and_enforce(
            'get_write_status', dict(args_in), None)
        self.assertIsNotNone(args_out, note or 'admin 应直通')
        self.assertNotIn('_bound_specific_parts', args_out)

    # 1.2 OWNER_SELF_TOOLS: get_persona / set_persona
    def test_owner_self_injects_user_id(self):
        from api.langgraph_chat.scope_enforcer import check_and_enforce
        scope = _owner_scope(user_id=2024, parts=('3-1-7-702',))
        for tool in ('get_persona', 'set_persona'):
            args_out, _ = check_and_enforce(tool, {}, scope)
            self.assertIsNotNone(args_out, f'{tool} 应通过')
            self.assertEqual(args_out['_user_id'], 2024,
                             f'{tool} 应注入 user_id=2024')
            self.assertNotIn('_bound_specific_parts', args_out)

    def test_owner_self_denies_admin(self):
        """admin / operator (scope=None) 调 OWNER_SELF → 直接拒绝。"""
        from api.langgraph_chat.scope_enforcer import check_and_enforce
        args_out, note = check_and_enforce(
            'set_persona', {'address': '老张'}, None)
        # check_and_enforce 返回 (args_out, note) 二元组；拒绝时 args_out=None
        self.assertIsNone(args_out, 'admin 调 OWNER_SELF 必须返回 args=None（语义拒绝）')
        self.assertIn('普通业主', note or '')

    def test_owner_self_denies_operator(self):
        """operator (role != 'user') 走 scope=None → 拒绝。"""
        from api.langgraph_chat.scope_enforcer import check_and_enforce
        args_out, note = check_and_enforce('get_persona', {}, None)
        self.assertIsNone(args_out)
        self.assertIn('普通业主', note or '')

    # 1.3 SCOPED_SINGLE_PART_TOOLS 新成员 get_device_params：注入 / 校验
    def test_get_device_params_single_bound_auto_injects(self):
        """单绑定 owner：不传 sp → ScopeEnforcer 自动填唯一绑定值。"""
        from api.langgraph_chat.scope_enforcer import check_and_enforce
        scope = _owner_scope(parts=('3-1-7-702',))
        args_out, _ = check_and_enforce(
            'get_device_params', {}, scope)
        self.assertIsNotNone(args_out)
        self.assertEqual(args_out['specific_part'], '3-1-7-702')

    def test_get_device_params_multi_bound_requires_explicit(self):
        """多绑定 owner：不传 sp → 返回 args_out=None（要求显式指定）。"""
        from api.langgraph_chat.scope_enforcer import check_and_enforce
        scope = _owner_scope(parts=('3-1-7-702', '3-1-7-801'))
        args_out, _ = check_and_enforce(
            'get_device_params', {}, scope)
        # 只读多绑定无 sp 时返回 (None, 提示)，不抛 ScopeViolationError
        self.assertIsNone(args_out, '多绑定未指定 sp 应拒绝，提示用户选一个')

    def test_get_device_params_rejects_cross_boundary_sp(self):
        from api.langgraph_chat.scope_enforcer import (
            check_and_enforce, ScopeViolationError)
        scope = _owner_scope(parts=('3-1-7-702',))
        # 只读工具填了邻居 sp → 返回 None + 提示（不抛 SVE）；写工具才抛
        args_out, note = check_and_enforce(
            'get_device_params', {'specific_part': '3-1-7-601'}, scope)
        self.assertIsNone(args_out)
        self.assertIn('无权访问', note or '')


# =========================================================================
# S2 — UserScope 新字段 user_id / build_user_scope 行为
# =========================================================================
@tag('integration', 'scope')
class UserScopeUserIdTests(TestCase):

    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            username='test-owner-p0', role='user',
            password='x', email='owner.p0@test.free-ark.local')
        self.other_owner = CustomUser.objects.create_user(
            username='test-neighbor-p0', role='user',
            password='x', email='neighbor.p0@test.free-ark.local')

    def test_build_user_scope_fills_user_id_and_bound(self):
        from api.models import OwnerInfo
        from api.langgraph_chat.user_scope import build_user_scope
        eo = OwnerInfo.objects.create(
            specific_part='3-1-7-702', building='3栋', unit='1单元',
            floor='7楼', room_number='702')
        OwnerUserBinding.objects.create(
            user=self.owner, owner=eo, active=True)
        scope = build_user_scope(self.owner)
        self.assertIsNotNone(scope)
        self.assertEqual(scope.user_id, self.owner.pk)
        self.assertEqual(scope.role, 'user')
        self.assertTrue(scope.is_owner)
        self.assertEqual(scope.bound_specific_parts, {'3-1-7-702'})

    def test_build_user_scope_admin_returns_none(self):
        from api.langgraph_chat.user_scope import build_user_scope
        admin = CustomUser.objects.create_user(
            username='admin-p0', role='admin', password='x')
        self.assertIsNone(build_user_scope(admin))

    def test_allows_method_still_works_with_new_field(self):
        scope = _owner_scope(user_id=self.owner.pk, parts=('3-1-7-702',))
        self.assertTrue(scope.allows('3-1-7-702'))
        self.assertFalse(scope.allows('3-1-7-303'))


# =========================================================================
# S3 — _extract_write_records_from_handler 信封解析（3 种形态 + 异常）
# =========================================================================
@tag('unit', 'scope')
class WriteRecordEnvelopeParseTests(SimpleTestCase):

    def _parse(self, raw):
        from api.langgraph_chat.fa_tools import _extract_write_records_from_handler
        return _extract_write_records_from_handler(raw)

    def test_standard_data_records_shape(self):
        """{success, data: {records: [...]}} 标准信封。"""
        rows = [{'id': 1, 'specific_part': '3-1-7-702', 'status': 'success'},
                {'id': 2, 'specific_part': '3-1-7-303', 'status': 'pending'}]
        got = self._parse({'success': True,
                           'data': {'records': rows, 'total': 2, 'page': 1}})
        self.assertEqual(got, rows)

    def test_data_direct_list_shape(self):
        """某些 handler 把 data 直接当 records list。"""
        rows = [{'id': 5, 'status': 'failed'}]
        got = self._parse({'success': True, 'data': rows})
        self.assertEqual(got, rows)

    def test_top_level_records_shape(self):
        """兜底：records 直接挂在顶层也能识别。"""
        rows = [{'id': 9, 'status': 'timeout'}]
        got = self._parse({'success': True, 'records': rows})
        self.assertEqual(got, rows)

    def test_success_false_returns_empty(self):
        got = self._parse({'success': False, 'error': '签名过期'})
        self.assertEqual(got, [])

    def test_none_or_bad_shapes_safe_fallback(self):
        self.assertEqual(self._parse(None), [])
        self.assertEqual(self._parse('not a dict'), [])
        self.assertEqual(self._parse({}), [])
        self.assertEqual(self._parse({'success': True}), [])


# =========================================================================
# S4 — get_write_status / _poll_write_status_until_final bound 二次过滤
#      （主风险修复：邻居 batch_id 即使被猜到也只能看到 0 条）
# =========================================================================
@tag('e2e', 'scope')
class WriteStatusBoundFilterTests(TestCase):
    """mock fa_tools._call → 返回 tier1 信封含全量 3 行（2 自家+1 邻居），
    然后校验 bound 过滤是否生效。避免依赖 tier1_readonly skill_dir。"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 造 batch 记录：同一个 batch_request_id 混两家
        cls.BATCH = 'batch-p0-e2e-mixed'
        cls.SP_OWNER = '3-1-7-702'
        cls.SP_NEIGHBOR = '3-1-7-303'

    def _mk_records(self):
        """清旧表 → 建 3 条：2 条 SP_OWNER（success），1 条 SP_NEIGHBOR（pending）。"""
        PLCWriteRecord.objects.filter(batch_request_id=self.BATCH).delete()
        r1 = PLCWriteRecord.objects.create(
            request_id='p0-e2e-1', batch_request_id=self.BATCH,
            specific_part=self.SP_OWNER, param_name='study_room_switch',
            old_value='0', new_value='1', status='success',
            operator='tester', channel='s7')
        r2 = PLCWriteRecord.objects.create(
            request_id='p0-e2e-2', batch_request_id=self.BATCH,
            specific_part=self.SP_OWNER, param_name='living_room_switch',
            old_value='0', new_value='1', status='success',
            operator='tester', channel='s7')
        r3 = PLCWriteRecord.objects.create(
            request_id='p0-e2e-3', batch_request_id=self.BATCH,
            specific_part=self.SP_NEIGHBOR, param_name='master_switch',
            old_value='0', new_value='1', status='success',
            operator='tester', channel='s7')
        return [r1, r2, r3]

    def _build_call_mock(self):
        """返回 side_effect callable：当调的是 freeark_get_write_records，
        就从 ORM 查 batch 并封装成标准 tier1 信封返回（模拟真实 HTTP/direct 行为）。"""
        def _call_stub(tool_name: str, params: dict):
            if tool_name == 'freeark_get_write_records':
                bid = params.get('batch_request_id')
                recs = list(
                    PLCWriteRecord.objects.filter(batch_request_id=bid)
                    .values('id', 'specific_part', 'param_name', 'status',
                            'error_message', 'created_at', 'acked_at')
                )
                for r in recs:
                    r.setdefault('updated_at', r.get('acked_at') or r.get('created_at'))
                return {'success': True,
                        'data': {'records': recs, 'total': len(recs),
                                 'page': 1, 'page_size': 20, 'has_more': False}}
            # 其他工具一律 fallback 空
            return {'success': True, 'summary': f'{tool_name}(stub)', 'data': {}}
        return _call_stub

    # ---- 4.1 _poll_write_status_until_final 的 bound 过滤 -----------------
    def test_poll_filters_out_neighbor_rows_when_bound_given(self):
        """owner 身份：bound=[自家] → 过滤后只剩自家行（邻居不可见）。"""
        from api.langgraph_chat import fa_tools
        self._mk_records()
        with mock.patch.object(fa_tools, '_call',
                               side_effect=self._build_call_mock()):
            from api.langgraph_chat.fa_tools import _poll_write_status_until_final
            p = _poll_write_status_until_final(
                self.BATCH, total_seconds=1, step_seconds=1,
                bound_specific_parts=[self.SP_OWNER])
        self.assertEqual(p['records_total'], 2,
                         '邻居那条应被过滤掉，不能出现在 owner 查询结果')
        self.assertEqual(p['records_success'], 2)
        for r in p['last_records']:
            self.assertEqual(r['specific_part'], self.SP_OWNER)

    def test_poll_reverse_bound_sees_only_neighbor(self):
        """换个 bound=[邻居] → 只剩 1 条（等价「邻居看自己的 batch」）。"""
        from api.langgraph_chat import fa_tools
        self._mk_records()
        with mock.patch.object(fa_tools, '_call',
                               side_effect=self._build_call_mock()):
            from api.langgraph_chat.fa_tools import _poll_write_status_until_final
            p = _poll_write_status_until_final(
                self.BATCH, total_seconds=1, step_seconds=1,
                bound_specific_parts=[self.SP_NEIGHBOR])
        self.assertEqual(p['records_total'], 1)
        self.assertEqual(p['last_records'][0]['specific_part'], self.SP_NEIGHBOR)

    def test_poll_no_bound_sees_all_three(self):
        """admin/operator (bound=None) → 3 条全可见（行为= v1.7.0）。"""
        from api.langgraph_chat import fa_tools
        self._mk_records()
        with mock.patch.object(fa_tools, '_call',
                               side_effect=self._build_call_mock()):
            from api.langgraph_chat.fa_tools import _poll_write_status_until_final
            p = _poll_write_status_until_final(
                self.BATCH, total_seconds=1, step_seconds=1,
                bound_specific_parts=None)
        self.assertEqual(p['records_total'], 3,
                         'admin 路径不做过滤，3 行都可见')

    def test_poll_bound_empty_list_filters_all(self):
        """空绑定集必须过滤全部；只有 None 代表管理员不做过滤。"""
        from api.langgraph_chat import fa_tools
        self._mk_records()
        with mock.patch.object(fa_tools, '_call',
                               side_effect=self._build_call_mock()):
            from api.langgraph_chat.fa_tools import _poll_write_status_until_final
            p = _poll_write_status_until_final(
                self.BATCH, total_seconds=1, step_seconds=1,
                bound_specific_parts=[])
        self.assertEqual(p['records_total'], 0)

    # ---- 4.2 get_write_status @tool 端到端 --------------------------------
    def test_get_write_status_tool_bound_filter_end_to_end(self):
        """生产编排调用辅助函数必须保留 ScopeEnforcer 注入的 bound 参数。"""
        from api.langgraph_chat import fa_tools
        self._mk_records()
        with mock.patch.object(fa_tools, '_call',
                               side_effect=self._build_call_mock()):
            from api.langgraph_chat.fa_tools import get_write_status
            from api.langgraph_chat.orchestrator import _ainvoke_tool_with_scope
            out = async_to_sync(_ainvoke_tool_with_scope)(
                get_write_status, 'get_write_status', {
                    'batch_request_id': self.BATCH,
                    '_bound_specific_parts': [self.SP_OWNER],
                },
            )
        self.assertTrue(out.get('success'))
        self.assertEqual(out['data']['records_total'], 2)
        self.assertEqual(out['data']['records_success'], 2)

    def test_get_write_status_wrong_batch_id_owner_sees_zero_hint_empty(self):
        """猜了个完全不存在的 batch_id → records_total=0，无邻居信息。"""
        from api.langgraph_chat import fa_tools
        self._mk_records()
        with mock.patch.object(fa_tools, '_call',
                               side_effect=self._build_call_mock()):
            from api.langgraph_chat.fa_tools import get_write_status
            from api.langgraph_chat.orchestrator import _ainvoke_tool_with_scope
            out = async_to_sync(_ainvoke_tool_with_scope)(
                get_write_status, 'get_write_status', {
                    'batch_request_id': 'non-existent-batch-xyz',
                    '_bound_specific_parts': [self.SP_OWNER],
                },
            )
        self.assertTrue(out.get('success'))
        self.assertEqual(out['data']['records_total'], 0)


# =========================================================================
# S5 — execute_write inline 分支：set_persona 直接 ORM 写 user.persona
# =========================================================================
@tag('e2e', 'scope')
class InlineSetPersonaExecuteWriteTests(TestCase):

    def setUp(self):
        # 必须用 set_password 才能用 authenticate；这里直接 create_user 即可
        self.user = CustomUser.objects.create_user(
            username='p0-persona-tester', role='user', password='pw',
            email='p0-persona@test.free-ark.local')

    def test_execute_write_set_persona_persists_in_db(self):
        """INLINE_SET_PERSONA__ 只接受 gate 提供的受信任 owner_user_id。"""
        from api.langgraph_chat.fa_tools import execute_write
        out = execute_write(
            "set_persona",
            {"identity": "小管家", "address": "胖子熊", "tone": "幽默"},
            operator_override='energy-agent::p0-persona-tester',
            owner_user_id=self.user.pk)
        self.assertTrue(out.get('success'), f'out={out}')
        self.assertIn('副官人格偏好已更新', out.get('summary', ''))
        self.assertIn('小管家', out['summary'])
        self.assertIn('胖子熊', out['summary'])
        self.user.refresh_from_db()
        persona = getattr(self.user, 'persona', None)
        self.assertIsNotNone(persona)
        self.assertEqual(persona.get('identity'), '小管家')
        self.assertEqual(persona.get('address'), '胖子熊')
        self.assertEqual(persona.get('tone'), '幽默')

    def test_execute_write_set_persona_partial_update_preserves_other_keys(self):
        """只改 address，原 identity / tone 保持不变。"""
        self.user.persona = {'identity': '副官', 'tone': '正式'}  # type: ignore[attr-defined]
        self.user.save(update_fields=['persona'])
        from api.langgraph_chat.fa_tools import execute_write
        out = execute_write(
            "set_persona", {"address": "老张"},
            operator_override='energy-agent::p0-persona-tester',
            owner_user_id=self.user.pk)
        self.assertTrue(out.get('success'))
        self.user.refresh_from_db()
        p = self.user.persona
        self.assertEqual(p.get('address'), '老张')
        self.assertEqual(p.get('identity'), '副官')
        self.assertEqual(p.get('tone'), '正式')

    def test_get_persona_preserves_injected_owner_id_in_real_invocation_path(self):
        """get_persona 通过编排辅助函数调用时必须收到受信任的 _user_id。"""
        self.user.persona = {'identity': '小管家', 'address': '老张'}
        self.user.save(update_fields=['persona'])
        from api.langgraph_chat.fa_tools import get_persona
        from api.langgraph_chat.orchestrator import _ainvoke_tool_with_scope
        out = async_to_sync(_ainvoke_tool_with_scope)(
            get_persona, 'get_persona', {'_user_id': self.user.pk})
        self.assertTrue(out.get('success'), f'out={out}')
        self.assertEqual(out['data']['identity'], '小管家')
        self.assertEqual(out['data']['address'], '老张')

    def test_execute_write_set_persona_without_verified_owner_rejects(self):
        """审计用户名不能被反解析为身份；缺失 gate 身份则必须拒绝。"""
        from api.langgraph_chat.fa_tools import execute_write
        out = execute_write(
            "set_persona", {"identity": "XX"},
            operator_override="energy-agent::not-a-user-id")
        self.assertFalse(out.get('success'),
                         '非数字 operator_override 不应被写入')
        self.assertIn('安全校验失败', out.get('error', '') + out.get('summary', ''))

    def test_execute_write_std_tool_still_routes_tier2_not_inline(self):
        """确保 set_device_params 没被误判成 INLINE：仍走 TIER2_HANDLERS 路由。"""
        from api.langgraph_chat import fa_tools
        hit = {'called': False}

        def fake(params):
            hit['called'] = True
            return {'success': True, 'summary': 'handler-ok',
                    # 本用例只验证路由，不引入 PLC 回执轮询的 30 秒等待。
                    'data': {'item_count': 1, 'status': 'success'}}

        with mock.patch.object(fa_tools, '_MOCK', False), \
             mock.patch.object(fa_tools, 'TIER2_HANDLERS',
                               {'freeark_write_device_params': fake}):
            out = fa_tools.execute_write(
                "set_device_params",
                {"specific_part": "3-1-7-702",
                 "items": [{"param_name": "study_room_switch", "new_value": "1"}]},
                operator_override="42")
        self.assertTrue(hit['called'],
                        'set_device_params 必须走 TIER2_HANDLERS（非 INLINE）')
        self.assertTrue(out.get('success'))


# =========================================================================
# S6 — 工具表一致性（避免工具加了但忘了进分类 / 映射）
# =========================================================================
@tag('unit', 'scope')
class ToolTableConsistencyTests(SimpleTestCase):
    """与我们落地前的 _p0_consistency_check.py 等价，作为回归 guard。"""

    def _fa_src(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[2]
        return (root / 'api' / 'langgraph_chat' / 'fa_tools.py').read_text(encoding='utf-8')

    def _se_src(self):
        import pathlib
        root = pathlib.Path(__file__).resolve().parents[2]
        return (root / 'api' / 'langgraph_chat' /
                'scope_enforcer.py').read_text(encoding='utf-8')

    def test_wtool_subsetof_handler_table(self):
        import re
        se = self._se_src()
        fa = self._fa_src()
        wts = re.findall(r"'([^']+)'",
                         re.search(r'WRITE_TOOLS:\s*frozenset\s*=\s*frozenset\(\s*\{([^}]*)\}',
                                   se, re.S).group(1))
        # parse _WRITE_TOOL_TO_HANDLER keys (brace-depth)
        m = re.search(r'(?m)^\s*_WRITE_TOOL_TO_HANDLER\s*=\s*\{', fa)
        i = m.end()
        depth = 1
        while i < len(fa) and depth > 0:
            c = fa[i]
            if c == '{': depth += 1
            elif c == '}': depth -= 1
            i += 1
        body = re.sub(r'#[^\n]*', '', fa[m.end():i - 1])
        wth_keys = re.findall(r"""['"]([^'"]+)['"]\s*:""", body)
        for w in wts:
            self.assertIn(w, wth_keys,
                          f'WRITE_TOOLS[{w}] 未在 _WRITE_TOOL_TO_HANDLER 中注册')

    def test_category_entries_have_matching_tool_defs(self):
        import ast, re, pathlib
        fa_src = self._fa_src()
        fa_tree = ast.parse(fa_src)
        tool_funcs = {n.name for n in fa_tree.body
                      if isinstance(n, ast.FunctionDef)}
        se_src = self._se_src()
        for cat in ('SCOPED_SINGLE_PART_TOOLS', 'SCOPED_QUERY_TOOLS',
                    'OWNER_SELF_TOOLS'):
            items = re.findall(
                r"'([^']+)'",
                re.search(rf'{cat}:\s*frozenset\s*=\s*frozenset\(\s*\{{([^}}]*)\}}\s*',
                          se_src, re.S).group(1))
            for name in items:
                self.assertIn(name, tool_funcs,
                              f'{cat} 条目 {name} 在 fa_tools 中无对应 @tool')

    def test_freeark_expert_contains_new_p0_tools(self):
        from api.langgraph_chat.fa_tools import TOOLS_BY_EXPERT
        names = {t.name for t in TOOLS_BY_EXPERT['freeark-expert']}
        expected = ('get_device_params', 'get_persona', 'set_persona',
                    'get_write_status', 'set_device_params', 'trigger_refresh')
        for e in expected:
            self.assertIn(e, names,
                          f'freeark-expert 工具集中缺 {e}')


# =========================================================================
# S7 — orchestrator gate sp 二次校验：OWNER_SELF_TOOLS 安全跳过
# =========================================================================
@tag('unit', 'scope')
class OrchestratorGateSpecificPartCheckTests(SimpleTestCase):

    def test_set_persona_in_owner_self_tools_and_skipped_by_gate_logic(self):
        """复刻 orchestrator gate 批准分支：OWNER_SELF_TOOLS 命中则
        _need_sp_check=False，不调 verify_write_scope。"""
        from api.langgraph_chat.scope_enforcer import (
            OWNER_SELF_TOOLS, verify_write_scope, verify_owner_self_scope,
            ScopeViolationError)
        scope = _owner_scope(user_id=77, parts=('3-1-7-702',))

        tool = 'set_persona'
        args = {'address': '老张'}   # 没有 specific_part
        need = tool not in OWNER_SELF_TOOLS
        if need:
            try:
                verify_write_scope(args.get('specific_part', ''), scope)
            except ScopeViolationError:
                self.fail('set_persona 不应触发 sp 校验（已被 OWNER_SELF 跳过）')
        # ↑ need=False，说明走了跳过分支
        self.assertFalse(need, 'set_persona 应跳过 sp 二次校验')
        self.assertEqual(verify_owner_self_scope(scope), 77)

    def test_set_persona_rejects_admin_at_gate(self):
        from api.langgraph_chat.scope_enforcer import (
            verify_owner_self_scope, ScopeViolationError)
        with self.assertRaises(ScopeViolationError):
            verify_owner_self_scope(None)

    def test_set_device_params_empty_sp_owner_still_blocked(self):
        """反例：set_device_params（非 OWNER_SELF）即使 sp 空也必须走 verify。"""
        from api.langgraph_chat.scope_enforcer import (
            OWNER_SELF_TOOLS, verify_write_scope, ScopeViolationError)
        scope = _owner_scope(parts=('3-1-7-702',))
        tool = 'set_device_params'
        args = {'items': [{'param_name': 's', 'new_value': '1'}]}  # sp 缺失
        need = tool not in OWNER_SELF_TOOLS
        self.assertTrue(need)
        with self.assertRaises(ScopeViolationError):
            verify_write_scope(args.get('specific_part', ''), scope)


if __name__ == '__main__':  # pragma: no cover
    # 不通过 manage.py 直跑时的最小启动（仅 SimpleTestCase 子集会跑）
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.test_settings')
    try:
        django.setup()
    except Exception as exc:  # noqa: BLE001
        print('django.setup failed (非 manage.py 直跑可忽略 TestCase 子集):',
              exc)
    unittest.main(verbosity=2)
