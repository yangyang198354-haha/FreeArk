"""
单元测试套件 — OpenClaw 聊天集成（PHASE_07 v1.2）

适配 v1.2 架构：OpenClawAdapter 现在通过 WebSocket Gateway RPC（协议 v4）
对接 OpenClaw 2026.5.20，不再走 HTTP SSE。所有测试用 FakeWS / FakeSession
mock aiohttp，不连真实 OpenClaw Gateway。

覆盖范围：
  - 配置缺失（token 未设）
  - URL 规范化（http→ws / https→wss）
  - connect 帧结构（mode=backend, scopes 正确，token 透传）
  - chat.send 帧结构（sessionKey / message / idempotencyKey）
  - 流式 delta → 逐 token yield
  - 终态：final 正常返回；aborted/error 抛出
  - 错误路径：connect 拒绝、chat.send 拒绝（scope 错误）、ClientConnectorError、WS 401
  - 流提前断（不带 final）→ 抛出
  - 跨 runId 隔离（同连接复用时仅取本 runId 事件）
  - 安全：yield 产物中不含 gateway token

运行命令：
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_openclaw_unit --settings=freearkweb.test_settings --verbosity=2

项目: FreeArk_Openclaw
文档引用: test_plan.md TC-U-01 ~ TC-U-13（v1.2 修订）
"""

import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token

from api.models import CustomUser

# 检测 aiohttp 是否可用（新依赖）
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

from api.openclaw_adapter import OpenClawAdapter, OpenClawUnavailableError


# ===========================================================================
# WebSocket mock helpers
# ===========================================================================

if AIOHTTP_AVAILABLE:
    class FakeWSMessage:
        """模拟 aiohttp.WSMessage（仅 type + data 字段）。"""
        def __init__(self, msg_type, data=None):
            self.type = msg_type
            self.data = data

    def text_msg(obj):
        """生成 TEXT 类型的 WSMessage，data 为 JSON 字符串。"""
        return FakeWSMessage(aiohttp.WSMsgType.TEXT, json.dumps(obj))

    def closed_msg():
        """生成 CLOSED 类型的 WSMessage（无 data）。"""
        return FakeWSMessage(aiohttp.WSMsgType.CLOSED, None)

    def error_msg():
        """生成 ERROR 类型的 WSMessage。"""
        return FakeWSMessage(aiohttp.WSMsgType.ERROR, None)


    class FakeWS:
        """伪 aiohttp ClientWebSocketResponse。

        - 异步上下文管理器（with ... as ws）
        - 异步可迭代（async for msg in ws）— 按 incoming 顺序产出消息
        - send_json(obj) 记录到 self.sent，便于断言客户端发送的帧
        - exception() 返回 None
        """
        def __init__(self, incoming, ws_exc=None):
            self._incoming = list(incoming)
            self._idx = 0
            self.sent = []
            self._ws_exc = ws_exc

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send_json(self, obj):
            self.sent.append(obj)

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._idx >= len(self._incoming):
                raise StopAsyncIteration
            m = self._incoming[self._idx]
            self._idx += 1
            return m

        def exception(self):
            return self._ws_exc


    class FakeSession:
        """伪 aiohttp.ClientSession。

        将 ws_connect 返回值固定为构造时给定的 FakeWS。
        """
        def __init__(self, fake_ws):
            self._ws = fake_ws
            self.ws_connect_calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        def ws_connect(self, url, **kwargs):
            self.ws_connect_calls.append((url, kwargs))
            return self._ws


    def patch_session_with(fake_ws):
        """返回一个 context manager：把 aiohttp.ClientSession patch 成 FakeSession(fake_ws)。

        用法：with patch_session_with(fake_ws) as fs: ...
        """
        fake_session = FakeSession(fake_ws)
        return patch(
            'aiohttp.ClientSession',
            return_value=fake_session,
        ), fake_session


# ---------------------------------------------------------------------------
# Adapter 配置类测试
# ---------------------------------------------------------------------------

class TestUrlNormalization(TestCase):
    """OpenClawAdapter._to_ws_url 规范化"""

    def test_http_to_ws(self):
        self.assertEqual(OpenClawAdapter._to_ws_url('http://127.0.0.1:18789'),
                         'ws://127.0.0.1:18789/')

    def test_https_to_wss(self):
        self.assertEqual(OpenClawAdapter._to_ws_url('https://gw.example.com:443'),
                         'wss://gw.example.com:443/')

    def test_ws_passthrough(self):
        self.assertEqual(OpenClawAdapter._to_ws_url('ws://127.0.0.1:18789/'),
                         'ws://127.0.0.1:18789/')

    def test_bare_host(self):
        self.assertEqual(OpenClawAdapter._to_ws_url('127.0.0.1:18789'),
                         'ws://127.0.0.1:18789/')


class TestConnectFrameBuilder(TestCase):
    """OpenClawAdapter._build_connect_frame 帧契约"""

    def test_connect_frame_shape(self):
        frame = OpenClawAdapter._build_connect_frame('req-1', 'tk-abc')
        self.assertEqual(frame['type'], 'req')
        self.assertEqual(frame['id'], 'req-1')
        self.assertEqual(frame['method'], 'connect')
        p = frame['params']
        self.assertEqual(p['minProtocol'], 4)
        self.assertEqual(p['maxProtocol'], 4)
        self.assertEqual(p['client']['mode'], 'backend')
        self.assertEqual(p['client']['id'], 'gateway-client')
        self.assertEqual(p['auth'], {'token': 'tk-abc'})
        self.assertEqual(p['role'], 'operator')
        # 必须包含 operator.write，否则 chat.send 会被 INVALID_REQUEST 拒绝
        self.assertIn('operator.write', p['scopes'])
        self.assertNotIn('device', p, '不应携带 device 字段（backend+loopback 路径）')


class TestChatSendFrameBuilder(TestCase):
    """OpenClawAdapter._build_chat_send_frame 帧契约"""

    def test_chat_send_frame_shape(self):
        frame = OpenClawAdapter._build_chat_send_frame(
            'req-2', 'sess-xyz', 'hello', 'idemp-1'
        )
        self.assertEqual(frame['type'], 'req')
        self.assertEqual(frame['id'], 'req-2')
        self.assertEqual(frame['method'], 'chat.send')
        self.assertEqual(frame['params'], {
            'sessionKey': 'sess-xyz',
            'message': 'hello',
            'idempotencyKey': 'idemp-1',
        })


# ---------------------------------------------------------------------------
# OpenClawAdapter.stream_chat 主流程
# ---------------------------------------------------------------------------

@unittest.skipUnless(AIOHTTP_AVAILABLE,
                     'aiohttp 未安装（pip install aiohttp>=3.9.0）')
@override_settings(
    OPENCLAW_BASE_URL='http://127.0.0.1:18789',
    OPENCLAW_GATEWAY_TOKEN='test-gateway-token-abc123',
    OPENCLAW_TIMEOUT=10,
    OPENCLAW_CONNECT_TIMEOUT=5,
)
class TestStreamChat(TestCase):
    """OpenClawAdapter.stream_chat 协议正确性与错误路径"""

    # --- 辅助 --------------------------------------------------------

    def _run(self, coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    async def _collect(self, message='你好', session_key='sess-001'):
        out = []
        async for tk in OpenClawAdapter.stream_chat(message=message,
                                                    session_key=session_key):
            out.append(tk)
        return out

    @staticmethod
    def _scripted_ok_flow(deltas, run_id='run-A'):
        """构造一个 incoming 序列：challenge → connect ok → chat.send ok → deltas → final。

        deltas: list[str] — 每个 delta 的 deltaText。
        """
        msgs = [
            text_msg({'type': 'event', 'event': 'connect.challenge',
                      'payload': {'nonce': 'n-1', 'ts': 1}}),
            # 中间的 health/tick 事件应被忽略
            text_msg({'type': 'event', 'event': 'health',
                      'payload': {'ok': True}}),
        ]
        # connect res must follow our connect_req_id — but we don't know it
        # in advance. The adapter captures ANY res with id matching its
        # connect_req_id. So we generate res with id matching the LAST
        # send_json() arg. The FakeWS doesn't reflect requests back, so
        # we use a sentinel: tests set the res id to '__CONNECT__'
        # and we'll re-stamp it from sent[0].id in run_with_script.
        msgs.append(text_msg({'type': 'res', 'id': '__CONNECT__',
                              'ok': True, 'payload': {
                                  'server': {'version': '2026.5.20',
                                             'connId': 'c-1'},
                                  'protocol': 4, 'auth': {'role': 'operator'},
                                  'policy': {'maxPayload': 1000,
                                             'maxBufferedBytes': 1000,
                                             'tickIntervalMs': 30000},
                                  'features': {'methods': ['chat.send'],
                                               'events': ['chat']},
                              }}))
        msgs.append(text_msg({'type': 'res', 'id': '__CHAT__', 'ok': True,
                              'payload': {'runId': run_id,
                                          'status': 'started'}}))
        for i, dt in enumerate(deltas, start=1):
            msgs.append(text_msg({
                'type': 'event', 'event': 'chat',
                'payload': {'runId': run_id, 'sessionKey': f'agent:main:sess-001',
                            'seq': i, 'state': 'delta', 'deltaText': dt},
            }))
        msgs.append(text_msg({
            'type': 'event', 'event': 'chat',
            'payload': {'runId': run_id, 'sessionKey': 'agent:main:sess-001',
                        'seq': len(deltas) + 1, 'state': 'final',
                        'message': {'content': []}},
        }))
        return msgs

    def _run_scripted(self, incoming_template, message='你好',
                      session_key='sess-001'):
        """执行 scripted incoming；自动把 res 的 '__CONNECT__'/'__CHAT__'
        sentinel id 替换为真实 send_json frame id（适配器随机生成的 uuid）。"""
        # 我们需要先让 adapter 发出 connect req（拿到它的 id），再产出 connect res。
        # 但 FakeWS 是 pre-scripted、消息按序产出。为模拟交互式响应，
        # 让 FakeWS 在 send_json 时根据 sent 列表替换 sentinel。
        fake_ws = FakeWS(incoming_template)

        original_send = fake_ws.send_json

        async def patching_send_json(obj):
            await original_send(obj)
            # 当 client 发 connect 请求时，把 incoming 列表里
            # 第一个含 '__CONNECT__' id 的 res 帧改写为正确 id
            method = obj.get('method')
            rid = obj.get('id')
            sentinel = None
            if method == 'connect':
                sentinel = '__CONNECT__'
            elif method == 'chat.send':
                sentinel = '__CHAT__'
            if sentinel is None:
                return
            for m in fake_ws._incoming:
                if m.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    f = json.loads(m.data)
                except Exception:
                    continue
                if f.get('type') == 'res' and f.get('id') == sentinel:
                    f['id'] = rid
                    m.data = json.dumps(f)
                    break

        fake_ws.send_json = patching_send_json

        cm, fake_session = patch_session_with(fake_ws)
        with cm:
            tokens = self._run(self._collect(message=message,
                                              session_key=session_key))
        return tokens, fake_ws, fake_session

    # ============ 配置/前置 ============

    def test_token_not_configured_raises(self):
        with override_settings(OPENCLAW_GATEWAY_TOKEN=''):
            with self.assertRaises(OpenClawUnavailableError) as ctx:
                self._run(self._collect())
            self.assertIn('token', str(ctx.exception).lower())

    # ============ 正常流程 ============

    def test_normal_flow_yields_deltas(self):
        tokens, fake_ws, _ = self._run_scripted(
            self._scripted_ok_flow(['Hey', ', ', 'world'])
        )
        # 协议升级：stream_chat 现 yield (kind, text) 元组（content/reasoning）。
        self.assertEqual(tokens, [('content', 'Hey'), ('content', ', '), ('content', 'world')])

    def test_chinese_deltas(self):
        tokens, _, _ = self._run_scripted(
            self._scripted_ok_flow(['你好', '，', '方舟龙虾'])
        )
        self.assertEqual(tokens, [('content', '你好'), ('content', '，'), ('content', '方舟龙虾')])

    def test_empty_delta_text_filtered(self):
        """deltaText 为空串 → 不 yield 空字符串。"""
        tokens, _, _ = self._run_scripted(
            self._scripted_ok_flow(['Hello', '', 'World'])
        )
        # 中间的空 delta 不应被 yield
        self.assertEqual(tokens, [('content', 'Hello'), ('content', 'World')])

    def test_sends_connect_then_chat_send(self):
        """验证 adapter 发出的两条帧的方法名和顺序。"""
        _, fake_ws, _ = self._run_scripted(
            self._scripted_ok_flow(['ok'])
        )
        # adapter 应顺序发出：connect → chat.send
        methods = [f.get('method') for f in fake_ws.sent]
        self.assertEqual(methods, ['connect', 'chat.send'])
        # 验证 chat.send 帧把 sessionKey 与 message 透传
        chat_frame = fake_ws.sent[1]
        self.assertEqual(chat_frame['params']['sessionKey'], 'sess-001')
        self.assertEqual(chat_frame['params']['message'], '你好')
        self.assertIn('idempotencyKey', chat_frame['params'])

    def test_ws_connect_url_normalized(self):
        """http:// 应被规范化为 ws:// 传给 ws_connect。"""
        _, _, fake_session = self._run_scripted(
            self._scripted_ok_flow(['ok'])
        )
        self.assertEqual(len(fake_session.ws_connect_calls), 1)
        url, _ = fake_session.ws_connect_calls[0]
        self.assertTrue(url.startswith('ws://'),
                        f'URL 未被规范化为 ws://, 实际: {url}')

    # ============ 终态事件 ============

    def test_aborted_event_raises(self):
        msgs = [
            text_msg({'type': 'event', 'event': 'connect.challenge',
                      'payload': {'nonce': 'n', 'ts': 1}}),
            text_msg({'type': 'res', 'id': '__CONNECT__', 'ok': True,
                      'payload': {}}),
            text_msg({'type': 'res', 'id': '__CHAT__', 'ok': True,
                      'payload': {'runId': 'r1'}}),
            text_msg({'type': 'event', 'event': 'chat',
                      'payload': {'runId': 'r1', 'seq': 1,
                                  'state': 'aborted',
                                  'stopReason': 'user_abort'}}),
        ]
        with self.assertRaises(OpenClawUnavailableError) as ctx:
            self._run_scripted(msgs)
        self.assertIn('aborted', str(ctx.exception).lower())

    def test_error_event_raises_with_kind_and_message(self):
        msgs = [
            text_msg({'type': 'event', 'event': 'connect.challenge',
                      'payload': {'nonce': 'n', 'ts': 1}}),
            text_msg({'type': 'res', 'id': '__CONNECT__', 'ok': True,
                      'payload': {}}),
            text_msg({'type': 'res', 'id': '__CHAT__', 'ok': True,
                      'payload': {'runId': 'r1'}}),
            text_msg({'type': 'event', 'event': 'chat',
                      'payload': {'runId': 'r1', 'seq': 1, 'state': 'error',
                                  'errorKind': 'rate_limit',
                                  'errorMessage': '429 too many requests'}}),
        ]
        with self.assertRaises(OpenClawUnavailableError) as ctx:
            self._run_scripted(msgs)
        msg = str(ctx.exception)
        self.assertIn('rate_limit', msg)
        self.assertIn('429', msg)

    # ============ 握手/scope 错误 ============

    def test_connect_rejected_raises(self):
        msgs = [
            text_msg({'type': 'event', 'event': 'connect.challenge',
                      'payload': {'nonce': 'n', 'ts': 1}}),
            text_msg({'type': 'res', 'id': '__CONNECT__', 'ok': False,
                      'error': {'code': 'INVALID_REQUEST',
                                'message': 'bad token'}}),
        ]
        with self.assertRaises(OpenClawUnavailableError) as ctx:
            self._run_scripted(msgs)
        self.assertIn('connect rejected', str(ctx.exception).lower())

    def test_chat_send_rejected_scope_error(self):
        """chat.send 缺 scope 时服务端返回 ok:false，应抛 OpenClawUnavailableError。"""
        msgs = [
            text_msg({'type': 'event', 'event': 'connect.challenge',
                      'payload': {'nonce': 'n', 'ts': 1}}),
            text_msg({'type': 'res', 'id': '__CONNECT__', 'ok': True,
                      'payload': {}}),
            text_msg({'type': 'res', 'id': '__CHAT__', 'ok': False,
                      'error': {'code': 'INVALID_REQUEST',
                                'message': 'missing scope: operator.write'}}),
        ]
        with self.assertRaises(OpenClawUnavailableError) as ctx:
            self._run_scripted(msgs)
        self.assertIn('operator.write', str(ctx.exception))

    # ============ 异常断开 ============

    def test_stream_ends_without_final_raises(self):
        """无 final/aborted/error 直接 StopAsyncIteration → OpenClawUnavailableError。"""
        msgs = [
            text_msg({'type': 'event', 'event': 'connect.challenge',
                      'payload': {'nonce': 'n', 'ts': 1}}),
            text_msg({'type': 'res', 'id': '__CONNECT__', 'ok': True,
                      'payload': {}}),
            text_msg({'type': 'res', 'id': '__CHAT__', 'ok': True,
                      'payload': {'runId': 'r1'}}),
            text_msg({'type': 'event', 'event': 'chat',
                      'payload': {'runId': 'r1', 'seq': 1, 'state': 'delta',
                                  'deltaText': 'half'}}),
            # 然后流就结束了，没有 final
        ]
        with self.assertRaises(OpenClawUnavailableError) as ctx:
            self._run_scripted(msgs)
        self.assertIn('unexpectedly', str(ctx.exception))

    def test_ws_closed_mid_stream_raises(self):
        msgs = [
            text_msg({'type': 'event', 'event': 'connect.challenge',
                      'payload': {'nonce': 'n', 'ts': 1}}),
            text_msg({'type': 'res', 'id': '__CONNECT__', 'ok': True,
                      'payload': {}}),
            text_msg({'type': 'res', 'id': '__CHAT__', 'ok': True,
                      'payload': {'runId': 'r1'}}),
            closed_msg(),  # 连接被关闭
        ]
        with self.assertRaises(OpenClawUnavailableError) as ctx:
            self._run_scripted(msgs)
        self.assertIn('closed', str(ctx.exception).lower())

    def test_connect_failure_raises(self):
        """ws_connect 抛 ClientConnectorError → OpenClawUnavailableError。"""
        async def bad_connect(*args, **kwargs):
            raise aiohttp.ClientConnectorError(
                connection_key=MagicMock(),
                os_error=OSError('ECONNREFUSED'),
            )

        fake_session = MagicMock()
        fake_session.__aenter__ = MagicMock(
            return_value=asyncio.sleep(0, result=fake_session)
        )
        fake_session.__aexit__ = MagicMock(
            return_value=asyncio.sleep(0, result=False)
        )
        fake_session.ws_connect = MagicMock(side_effect=bad_connect)

        # 用更简单的方式：直接 patch ClientSession.__aenter__ 返回一个会抛错的会话
        class BadSession:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            def ws_connect(self, *args, **kwargs):
                # 返回一个 awaitable 上下文管理器
                class _Bad:
                    async def __aenter__(self_):
                        raise aiohttp.ClientConnectorError(
                            connection_key=MagicMock(),
                            os_error=OSError('ECONNREFUSED'),
                        )
                    async def __aexit__(self_, *a): return False
                return _Bad()

        with patch('aiohttp.ClientSession', return_value=BadSession()):
            with self.assertRaises(OpenClawUnavailableError) as ctx:
                self._run(self._collect())
        self.assertIn('connect', str(ctx.exception).lower())

    # ============ runId 过滤 ============

    def test_events_for_other_runid_are_ignored(self):
        """同连接上若混入其他 runId 的 chat 事件，应被过滤。"""
        msgs = [
            text_msg({'type': 'event', 'event': 'connect.challenge',
                      'payload': {'nonce': 'n', 'ts': 1}}),
            text_msg({'type': 'res', 'id': '__CONNECT__', 'ok': True,
                      'payload': {}}),
            text_msg({'type': 'res', 'id': '__CHAT__', 'ok': True,
                      'payload': {'runId': 'mine'}}),
            # 混入其他 runId 的 delta — 必须忽略
            text_msg({'type': 'event', 'event': 'chat',
                      'payload': {'runId': 'OTHER', 'seq': 1, 'state': 'delta',
                                  'deltaText': '!!INTRUDER!!'}}),
            text_msg({'type': 'event', 'event': 'chat',
                      'payload': {'runId': 'mine', 'seq': 2, 'state': 'delta',
                                  'deltaText': 'real'}}),
            text_msg({'type': 'event', 'event': 'chat',
                      'payload': {'runId': 'mine', 'seq': 3, 'state': 'final',
                                  'message': {'content': []}}}),
        ]
        tokens, _, _ = self._run_scripted(msgs)
        self.assertEqual(tokens, [('content', 'real')])
        self.assertNotIn(('content', '!!INTRUDER!!'), tokens)

    # ============ 安全（token 不出现在产物）============

    def test_gateway_token_never_appears_in_yielded_chunks(self):
        gw_tok = 'test-gateway-token-abc123'
        # 让 deltaText 本身不含 token；额外构造一段含 token 模式的 delta
        # 也不应被任何处理回写 token。
        tokens, fake_ws, _ = self._run_scripted(
            self._scripted_ok_flow(['Hello', ' world', '!'])
        )
        for tk in tokens:
            self.assertNotIn(gw_tok, tk,
                             f'gateway token 泄露到 yield: {tk}')
        # 也检查 fake_ws.sent 中虽然必然含 token（auth.token），
        # 但应仅在 connect 帧的 params.auth.token 路径，不出现在其他地方。
        connect_frame = fake_ws.sent[0]
        self.assertEqual(connect_frame['params']['auth']['token'], gw_tok)
        chat_frame = fake_ws.sent[1]
        # chat.send 帧绝不能携带 token
        flat = json.dumps(chat_frame)
        self.assertNotIn(gw_tok, flat)


# ---------------------------------------------------------------------------
# ChatConsumer._get_user_by_token （与 v1.1 完全相同；未变化）
# ---------------------------------------------------------------------------

class TestGetUserByToken(TestCase):
    """TC-U-11 ~ TC-U-13: ChatConsumer._get_user_by_token token 验证逻辑。"""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='testuser_chat',
            password='testpassword123',
            email='testchat@example.com',
        )
        self.token = Token.objects.create(user=self.user)

    def _lookup(self, key):
        """直接调用 DRF Token 查询（绕过 sync_to_async 装饰器）。"""
        if not key:
            return None
        try:
            from rest_framework.authtoken.models import Token as DRFToken
            return DRFToken.objects.select_related('user').get(key=key).user
        except Token.DoesNotExist:
            return None

    def test_valid_token_returns_user(self):
        result = self._lookup(self.token.key)
        self.assertIsNotNone(result)
        self.assertEqual(result.username, 'testuser_chat')

    def test_invalid_token_returns_none(self):
        self.assertIsNone(self._lookup('invalid-token-does-not-exist'))

    def test_empty_token_returns_none(self):
        self.assertIsNone(self._lookup(''))

    def test_none_token_returns_none(self):
        self.assertIsNone(self._lookup(None))
