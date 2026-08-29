"""副官审核期开关：配置读写与小程序安全降级测试。"""

from django.test import TestCase, tag
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from api.models import CustomUser


def authed_client(username, role):
    user = CustomUser.objects.create_user(username=username, password='pass1234', role=role)
    token, _ = Token.objects.get_or_create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
    return client


@tag('integration')
class AdjutantConfigApiTests(TestCase):
    def setUp(self):
        self.admin = authed_client('adjutant_admin', 'admin')
        self.owner = authed_client('adjutant_owner', 'user')

    def test_default_is_disabled(self):
        response = self.admin.get('/api/adjutant-config/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {'enabled': False})

    def test_admin_can_enable_and_owner_reads_enabled_status(self):
        response = self.admin.put('/api/adjutant-config/update/', {'enabled': True}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data'], {'enabled': True})

        response = self.owner.get('/api/miniapp/adjutant/status/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'enabled': True})

    def test_non_admin_cannot_change_config(self):
        response = self.owner.put('/api/adjutant-config/update/', {'enabled': True}, format='json')
        self.assertEqual(response.status_code, 403)

    def test_invalid_value_is_rejected(self):
        response = self.admin.put('/api/adjutant-config/update/', {'enabled': 'true'}, format='json')
        self.assertEqual(response.status_code, 400)
