"""副官动态推荐问题：能力题库、匿名热门聚合与隐私过滤测试。"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, tag
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.adjutant_recommendations import _popular_questions, is_safe_common_question
from api.models import ChatMessage, ChatSession, CustomUser


def _user(username, role='user'):
    user = CustomUser.objects.create_user(username=username, password='pass1234', role=role)
    token, _ = Token.objects.get_or_create(user=user)
    return user, token.key


def _message(user, content):
    session = ChatSession.objects.create(user=user, session_key=f'{user.username}-{ChatSession.objects.count()}')
    return ChatMessage.objects.create(session=session, role='user', content=content)


@tag('unit')
class AdjutantRecommendationSafetyTest(TestCase):
    def test_generic_question_is_safe(self):
        self.assertTrue(is_safe_common_question('新风滤网多久更换一次？'))

    def test_personal_or_identifying_question_is_not_safe(self):
        for question in (
            '我家 3-1-7-702 的空调为什么不制冷？',
            '手机号 13800138000 绑定失败怎么办？',
            '设备 MAC 地址 00:11:22:33:44:55 连不上怎么办？',
        ):
            with self.subTest(question=question):
                self.assertFalse(is_safe_common_question(question))


@tag('unit')
class AdjutantRecommendationAggregationTest(TestCase):
    def setUp(self):
        cache.clear()
        self.owner_a, _ = _user('resident-a')
        self.owner_b, _ = _user('resident-b')

    def tearDown(self):
        cache.clear()

    def test_merges_equivalent_system_control_questions_by_intent(self):
        for user, question in (
            (self.owner_a, '如何打开系统？'),
            (self.owner_b, '怎样开启系统？'),
            (self.owner_a, '关闭系统的方法是什么？'),
        ):
            _message(user, question)

        self.assertEqual(_popular_questions(), ['如何开启或关闭设备系统？'])

    def test_excludes_internal_and_test_accounts_from_popular_questions(self):
        operator, _ = _user('operations-user', role='operator')
        test_owner, _ = _user('qa-test-account')
        for _ in range(4):
            _message(operator, '如何开启系统？')
            _message(test_owner, '如何开启系统？')

        self.assertEqual(_popular_questions(), [])

    def test_requires_three_messages_from_two_distinct_owners(self):
        for _ in range(3):
            _message(self.owner_a, '新风滤网多久需要更换？')

        self.assertEqual(_popular_questions(), [])


@tag('integration')
class AdjutantRecommendationEndpointTest(TestCase):
    URL = '/api/miniapp/adjutant/recommendations/'

    def setUp(self):
        cache.clear()
        self.owner, self.token = _user('owner')
        self.other, _ = _user('other')
        self.third, _ = _user('third')

    def tearDown(self):
        cache.clear()

    def _client(self, token=None):
        client = APIClient()
        if token:
            client.credentials(HTTP_AUTHORIZATION=f'Token {token}')
        return client

    def test_requires_owner_authentication(self):
        response = self._client().get(self.URL)
        self.assertIn(response.status_code, (401, 403))

    @patch('api.adjutant_recommendations.secrets.choice', return_value='帮我看看今天的能耗情况。')
    def test_returns_capability_and_only_privacy_safe_popular_questions(self, _choice):
        safe_question = '新风滤网多久更换一次？'
        private_question = '我家 3-1-7-702 的设备为什么不制冷？'
        for user in (self.other, self.third, self.other):
            _message(user, safe_question)
            _message(user, private_question)

        response = self._client(self.token).get(self.URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['capability_question'], '帮我看看今天的能耗情况。')
        self.assertEqual(response.data['popular_questions'], ['新风滤网多久需要更换？'])
