"""
单元/集成测试 —— 副官人格偏好：语义拆分 + 对话内修改 + 首次询问（v1.13.0）

背景（2026-08-22 生产实测确认的三层缺陷）：
  1. **没有写入通路**：`POST /api/miniapp/persona/update/` 全仓零调用方，LangGraph 也
     没有 set_persona 工具 → 生产 126 个用户 persona 非空的为 0，跨会话必然记不住。
  2. **人格块对抗修改**：旧措辞"保持该角色定位贯穿整个对话"让副官答"我必须遵循守则，
     仍以'尊敬的舰长大人'称呼您" → 会话内也不生效。
  3. **字段语义混淆**：tone_style 在默认分支是"称呼"、自定义分支变成"风格"。实测设成
     "胖子熊大人"后模型答"我是胖子熊大人，智能方舟的副官"——把用户的称呼当成了自己的名字。

本套件按三层分别上锁，并覆盖 US-001 AC-001-02（首次对话询问偏好）与
US-003 AC-003-01/02（自然语言改称呼 / 恢复默认）。

全离线：FREEARK_POC_MOCK=1 + LANGGRAPH_USE_FAKE_LLM=True，不连真 DeepSeek。

运行命令：
  cd FreeArkWeb/backend/freearkweb
  python manage.py test api.tests.test_persona_preference \
      --settings=freearkweb.test_settings --verbosity=2
"""

import json
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("FREEARK_POC_MOCK", "1")

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, TestCase, override_settings, tag
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CustomUser
from api.persona import (DEFAULT_ADDRESS, DEFAULT_IDENTITY, effective_persona,
                         has_user_set_address, normalize_persona,
                         persona_payload)
from api.persona_intent import (_parse, apply_persona_change,
                                detect_persona_change,
                                looks_like_persona_change)

try:
    import langgraph  # noqa: F401
    import langchain_core  # noqa: F401
    LANGGRAPH_AVAILABLE = True
except Exception:  # pragma: no cover
    LANGGRAPH_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════════════════
# 第 1 层：字段语义归一
# ═══════════════════════════════════════════════════════════════════════════

@tag('unit')
class PersonaNormalizeTests(SimpleTestCase):
    """缺陷 3 的地基：identity / address / tone 三键语义单一，历史键只读兼容。"""

    def test_legacy_keys_map_to_canonical(self):
        """greeting_style→identity（副官自称）、tone_style→address（称呼用户）。"""
        self.assertEqual(
            normalize_persona({'greeting_style': '副官', 'tone_style': '舰长大人'}),
            {'identity': '副官', 'address': '舰长大人'},
        )

    def test_canonical_wins_over_legacy(self):
        p = normalize_persona({'greeting_style': '旧', 'identity': '新'})
        self.assertEqual(p['identity'], '新')

    def test_unset_keys_absent_not_defaulted(self):
        """未设置的键必须缺席——用于区分「没设过」与「设成了默认值」。"""
        self.assertEqual(normalize_persona({}), {})
        self.assertEqual(normalize_persona(None), {})

    def test_blank_and_non_string_ignored(self):
        self.assertEqual(normalize_persona({'address': '   ', 'tone': 123}), {})

    def test_value_truncated_to_50(self):
        p = normalize_persona({'address': 'x' * 80})
        self.assertEqual(len(p['address']), 50)

    def test_effective_fills_defaults(self):
        eff = effective_persona(None)
        self.assertEqual(eff['identity'], DEFAULT_IDENTITY)
        self.assertEqual(eff['address'], DEFAULT_ADDRESS)
        self.assertIsNone(eff['tone'])

    def test_payload_nulls_unset(self):
        self.assertEqual(persona_payload({}),
                         {'identity': None, 'address': None, 'tone': None})

    def test_has_user_set_address(self):
        self.assertTrue(has_user_set_address({'tone_style': '胖子熊大人'}))
        self.assertFalse(has_user_set_address({}))
        self.assertFalse(has_user_set_address({'identity': '管家'}))


# ═══════════════════════════════════════════════════════════════════════════
# 第 2 层：人格提示块
# ═══════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph/langchain-core 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('unit')
class PersonaMessageTests(SimpleTestCase):
    """缺陷 2+3：称呼必须当称呼用；身份不可变但称呼可改。"""

    def _content(self, persona, ask=False):
        from api.langgraph_chat.orchestrator import build_persona_message
        return build_persona_message(persona, ask).content

    def test_address_used_as_form_of_address_not_style(self):
        """核心回归：自定义称呼必须生成「请称呼当前用户为X」，不能是「以X风格交流」。

        旧版对 tone_style 生成的是"请以'胖子熊大人'风格与当前用户交流"，
        实测模型据此自称"我是胖子熊大人"。
        """
        c = self._content({'address': '胖子熊大人'})
        self.assertIn('请称呼当前用户为「胖子熊大人」', c)
        self.assertNotIn("以「胖子熊大人」的语气", c)

    def test_legacy_tone_style_also_treated_as_address(self):
        """历史键 tone_style 走同一条路——正是生产上出错的那个入参形态。"""
        c = self._content({'tone_style': '胖子熊大人'})
        self.assertIn('请称呼当前用户为「胖子熊大人」', c)

    def test_identity_and_address_are_independent(self):
        c = self._content({'identity': '方舟管家', 'address': '老板'})
        self.assertIn('你的身份是「方舟管家」', c)
        self.assertIn('请称呼当前用户为「老板」', c)

    def test_tone_rendered_as_tone(self):
        c = self._content({'tone': '简洁'})
        self.assertIn('以「简洁」的语气', c)

    def test_defaults_when_empty(self):
        c = self._content(None)
        self.assertIn(f'你的身份是「{DEFAULT_IDENTITY}」', c)
        self.assertIn(f'请称呼当前用户为「{DEFAULT_ADDRESS}」', c)

    def test_identity_locked_but_address_changeable(self):
        """缺陷 2：不得再让模型拿「守则」拒绝用户改称呼。"""
        c = self._content(None)
        self.assertIn('不可更改', c)          # 身份锁死
        self.assertIn('不要以「守则」', c)     # 称呼放开
        self.assertIn('直接接受', c)

    def test_ask_preference_flag_controls_the_ask(self):
        """US-001 AC-001-02：仅在置位时追加询问指令，且要求不打断正常回答。"""
        off = self._content(None, ask=False)
        on = self._content(None, ask=True)
        self.assertNotIn('询问', off)
        self.assertIn('询问他希望被如何称呼', on)
        self.assertIn('不得打断', on)


# ═══════════════════════════════════════════════════════════════════════════
# 第 3 层：意图识别与抽取
# ═══════════════════════════════════════════════════════════════════════════

class _StubLLM:
    """录调用次数的假模型——用于验证预筛真的挡住了 LLM 调用。"""

    def __init__(self, reply=''):
        self.reply = reply
        self.calls = 0

    async def ainvoke(self, messages):
        self.calls += 1
        from langchain_core.messages import AIMessage
        return AIMessage(content=self.reply)


class _BoomLLM:
    async def ainvoke(self, messages):
        raise RuntimeError('模型炸了')


@tag('unit')
class PersonaPrefilterTests(SimpleTestCase):
    """一级预筛：宁可漏、不可滥——滥判会莫名其妙改掉用户的称呼。"""

    def test_hits_address_change_phrasings(self):
        for s in ('以后叫我胖子熊大人', '别叫我舰长', '称呼我为老板',
                  '换个称呼吧', '语气随意一点', '恢复默认'):
            with self.subTest(s=s):
                self.assertTrue(looks_like_persona_change(s))

    def test_misses_ordinary_messages(self):
        for s in ('查一下今天的能耗', '3-1-7-702 温度调到 24 度',
                  '新风滤网多久换', '客厅主机不制冷'):
            with self.subTest(s=s):
                self.assertFalse(looks_like_persona_change(s))


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langchain-core 未安装，跳过")
@tag('unit')
class PersonaExtractTests(SimpleTestCase):
    """二级抽取：对脏输出鲁棒，异常一律 fail-open。"""

    def test_parse_json_fence_and_prose(self):
        self.assertEqual(
            _parse('好的```json\n{"action":"set","address":"胖子熊大人"}\n```'),
            {'action': 'set', 'address': '胖子熊大人'})

    def test_parse_none_and_reset(self):
        self.assertIsNone(_parse('{"action":"none"}'))
        self.assertEqual(_parse('{"action":"reset"}'), {'action': 'reset'})

    def test_parse_set_without_fields_is_invalid(self):
        """action=set 却一个字段都没抽到 → 不得改任何东西。"""
        self.assertIsNone(_parse('{"action":"set"}'))

    def test_parse_garbage(self):
        self.assertIsNone(_parse('我不知道'))
        self.assertIsNone(_parse(''))

    def test_prefilter_short_circuits_llm(self):
        """未命中预筛必须一次 LLM 都不调（成本控制的核心）。"""
        llm = _StubLLM('{"action":"set","address":"X"}')
        out = async_to_sync(detect_persona_change)('查一下今天的能耗', llm)
        self.assertIsNone(out)
        self.assertEqual(llm.calls, 0)

    def test_extract_on_hit(self):
        llm = _StubLLM('{"action":"set","address":"胖子熊大人"}')
        out = async_to_sync(detect_persona_change)('以后叫我胖子熊大人', llm)
        self.assertEqual(out, {'action': 'set', 'address': '胖子熊大人'})
        self.assertEqual(llm.calls, 1)

    def test_llm_failure_is_fail_open(self):
        out = async_to_sync(detect_persona_change)('以后叫我胖子熊大人', _BoomLLM())
        self.assertIsNone(out)


@tag('unit')
class PersonaApplyTests(SimpleTestCase):
    def test_set_merges_and_normalizes(self):
        self.assertEqual(
            apply_persona_change({'greeting_style': '副官'},
                                 {'action': 'set', 'address': '胖子熊大人'}),
            {'identity': '副官', 'address': '胖子熊大人'})

    def test_reset_clears(self):
        self.assertEqual(
            apply_persona_change({'identity': '管家', 'address': '老板'},
                                 {'action': 'reset'}),
            {})


# ═══════════════════════════════════════════════════════════════════════════
# 第 4 层：consumer 写入通路（缺陷 1）
# ═══════════════════════════════════════════════════════════════════════════

@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('integration')
class ConsumerPersonaWriteTests(TestCase):
    """直接测 consumer 方法（不做完整 WS 握手）：落库 + 本轮生效 + 推帧。"""

    def setUp(self):
        from api.consumers import MiniAppChatConsumer
        self.user = CustomUser.objects.create_user(
            username='persona_owner', password='pass1234', role='user')
        self.c = MiniAppChatConsumer()
        self.c.user = self.user
        self.c.persona = None
        self.sent = []

        async def _send(text):
            self.sent.append(json.loads(text))

        self.c.send = _send

    def _frames(self, ftype):
        return [f for f in self.sent if f.get('type') == ftype]

    @patch('api.consumers.detect_persona_change')
    def test_change_persists_refreshes_and_pushes_frame(self, mock_detect):
        async def _fake(msg, llm):
            return {'action': 'set', 'address': '胖子熊大人'}
        mock_detect.side_effect = _fake

        async_to_sync(self.c._maybe_update_persona)('以后叫我胖子熊大人')

        # 1) 落库 → 跨会话记得住
        self.user.refresh_from_db()
        self.assertEqual(self.user.persona.get('address'), '胖子熊大人')
        # 2) 刷新连接内状态 → 本轮回复就用新称呼
        self.assertEqual(self.c.persona.get('address'), '胖子熊大人')
        # 3) 推帧 → 前端新会话问候语同步
        frames = self._frames('persona_updated')
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0]['persona']['address'], '胖子熊大人')

    @patch('api.consumers.detect_persona_change')
    def test_reset_clears_persona(self, mock_detect):
        self.user.persona = {'address': '胖子熊大人'}
        self.user.save(update_fields=['persona'])
        self.c.persona = {'address': '胖子熊大人'}

        async def _fake(msg, llm):
            return {'action': 'reset'}
        mock_detect.side_effect = _fake

        async_to_sync(self.c._maybe_update_persona)('恢复默认')

        self.user.refresh_from_db()
        self.assertEqual(self.user.persona, {})
        self.assertIsNone(self.c.persona)

    def test_ordinary_message_writes_nothing(self):
        """预筛未命中 → 不落库、不推帧（也不该调 LLM）。"""
        async_to_sync(self.c._maybe_update_persona)('查一下今天的能耗')
        self.user.refresh_from_db()
        self.assertEqual(self.user.persona, {})
        self.assertEqual(self._frames('persona_updated'), [])

    @patch('api.consumers.detect_persona_change')
    def test_detect_exception_does_not_break_chat(self, mock_detect):
        """fail-open：抽取炸了也不能把聊天打挂。"""
        async def _boom(msg, llm):
            raise RuntimeError('炸')
        mock_detect.side_effect = _boom

        async_to_sync(self.c._maybe_update_persona)('以后叫我胖子熊大人')  # 不抛

        self.user.refresh_from_db()
        self.assertEqual(self.user.persona, {})


@unittest.skipUnless(LANGGRAPH_AVAILABLE, "langgraph 未安装，跳过")
@override_settings(LANGGRAPH_USE_FAKE_LLM=True, CHAT_BACKEND="langgraph")
@tag('integration')
class ConsumerAskPreferenceTests(TestCase):
    """US-001 AC-001-02：首次对话且没设过称呼才问，且每连接只问一次。"""

    def setUp(self):
        from api.consumers import MiniAppChatConsumer
        self.user = CustomUser.objects.create_user(
            username='persona_newbie', password='pass1234', role='user')
        self.c = MiniAppChatConsumer()
        self.c.user = self.user
        self.c.persona = None

    def _ask(self):
        return async_to_sync(self.c._should_ask_persona_preference)()

    def test_first_time_user_gets_asked_once(self):
        self.assertTrue(self._ask())
        self.assertFalse(self._ask())   # 同一连接内不再重复追问

    def test_not_asked_when_address_already_set(self):
        self.c.persona = {'address': '胖子熊大人'}
        self.assertFalse(self._ask())

    def test_not_asked_when_user_has_spoken_before(self):
        from api.models import ChatMessage, ChatSession
        s = ChatSession.objects.create(user=self.user, session_key='sess-old')
        ChatMessage.objects.create(session=s, role='user', content='你好')
        self.assertFalse(self._ask())


# ═══════════════════════════════════════════════════════════════════════════
# 第 5 层：REST 接口
# ═══════════════════════════════════════════════════════════════════════════

@tag('integration')
class PersonaRestTests(TestCase):
    """/api/miniapp/persona/ 读写——规范三键 + 历史键入参兼容。"""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='persona_rest', password='pass1234', role='user')
        token, _ = Token.objects.get_or_create(user=self.user)
        self.c = APIClient()
        self.c.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def test_get_returns_canonical_keys(self):
        r = self.c.get('/api/miniapp/persona/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.data.keys()), {'identity', 'address', 'tone'})
        self.assertIsNone(r.data['address'])

    def test_update_with_canonical_keys(self):
        r = self.c.put('/api/miniapp/persona/update/',
                       {'address': '胖子熊大人'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['address'], '胖子熊大人')
        self.user.refresh_from_db()
        self.assertEqual(self.user.persona, {'address': '胖子熊大人'})

    def test_update_accepts_legacy_keys(self):
        """v1.12.0 客户端传旧键仍可用，但落库/响应一律规范键。"""
        r = self.c.put('/api/miniapp/persona/update/',
                       {'tone_style': '老板', 'greeting_style': '管家'},
                       format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['address'], '老板')
        self.assertEqual(r.data['identity'], '管家')
        self.user.refresh_from_db()
        self.assertEqual(set(self.user.persona.keys()), {'identity', 'address'})

    def test_partial_update_preserves_other_keys(self):
        self.user.persona = {'identity': '管家', 'address': '老板'}
        self.user.save(update_fields=['persona'])
        r = self.c.put('/api/miniapp/persona/update/',
                       {'address': '胖子熊大人'}, format='json')
        self.assertEqual(r.data['identity'], '管家')
        self.assertEqual(r.data['address'], '胖子熊大人')

    def test_empty_payload_rejected(self):
        r = self.c.put('/api/miniapp/persona/update/', {}, format='json')
        self.assertEqual(r.status_code, 400)

    # ── v1.13.0 第4步：设置页需要「整体恢复默认」与「单独清空某字段」 ──────
    # 合并式更新（只覆盖非空键）做不到这两件事，故区分三态：
    #   键非空=设置 / 键为空串=清空该字段 / 键缺席=保留原值 / reset=true=全清

    def test_reset_clears_everything(self):
        self.user.persona = {'identity': '管家', 'address': '老板', 'tone': '随意'}
        self.user.save(update_fields=['persona'])
        r = self.c.put('/api/miniapp/persona/update/',
                       {'reset': True}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {'identity': None, 'address': None, 'tone': None})
        self.user.refresh_from_db()
        self.assertEqual(self.user.persona, {})

    def test_blank_value_clears_only_that_field(self):
        """设置页的核心诉求：只清语气、保留称呼——对话里的"恢复默认"做不到。"""
        self.user.persona = {'identity': '管家', 'address': '老板', 'tone': '随意'}
        self.user.save(update_fields=['persona'])
        r = self.c.put('/api/miniapp/persona/update/',
                       {'tone': ''}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.data['tone'])
        self.assertEqual(r.data['address'], '老板')
        self.assertEqual(r.data['identity'], '管家')

    def test_absent_key_still_preserved_not_cleared(self):
        """缺席 ≠ 空串：设置页全量提交才清，部分提交不得误删。"""
        self.user.persona = {'identity': '管家', 'address': '老板'}
        self.user.save(update_fields=['persona'])
        r = self.c.put('/api/miniapp/persona/update/',
                       {'address': '胖子熊大人'}, format='json')
        self.assertEqual(r.data['identity'], '管家')

    def test_full_form_submit_sets_and_clears_in_one_call(self):
        """设置页实际的提交形态：三字段全量，空的即清。"""
        self.user.persona = {'identity': '管家', 'address': '老板', 'tone': '随意'}
        self.user.save(update_fields=['persona'])
        r = self.c.put('/api/miniapp/persona/update/',
                       {'identity': '', 'address': '胖子熊大人', 'tone': ''},
                       format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data,
                         {'identity': None, 'address': '胖子熊大人', 'tone': None})
