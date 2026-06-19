"""
test_fault_event_serializer_v061.py — FaultEventSerializer v0.6.1-FM-UX 新字段测试

覆盖范围：
  TC-SER-01  序列化输出含 device_name 和 device_type_label 字段
  TC-SER-02  主路径：device_sn 命中 cache → device_name = DeviceNode.device_name
  TC-SER-03  兜底一：cache miss + product_code 命中 PRODUCT_CODE_LABELS → device_type_label
  TC-SER-04  兜底二：两者皆 miss → device_name=None, device_type_label=None
  TC-SER-05  device_sn 非整数字符串时 get_device_name 返回 None，不崩溃

运行方式（在 FreeArkWeb/backend/freearkweb/ 目录下）：
    ../../../venv/bin/python manage.py test api.tests.test_fault_event_serializer_v061 -v 2
"""

from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token
from django.contrib.auth import get_user_model

from api.models import FaultEvent
import api.device_name_cache as cache_module

User = get_user_model()


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _make_fault_event(**kwargs):
    """创建 FaultEvent，提供合理默认值。"""
    now = timezone.now()
    defaults = dict(
        specific_part='3-1-7-702',
        device_sn='22155',
        product_code='130004',
        fault_code='fresh_air_unit_stop_error',
        fault_type='fresh_air',
        fault_message='Fresh air unit stop error',
        severity='error',
        first_seen_at=now - timedelta(hours=1),
        last_seen_at=now - timedelta(minutes=30),
        recovered_at=None,
        is_active=True,
    )
    defaults.update(kwargs)
    return FaultEvent.objects.create(**defaults)


def _reset_cache():
    """重置 device_name_cache 状态。"""
    cache_module._cache = {}
    cache_module._cache_loaded_at = 0.0


class TestSerializerNewFieldsPresent(TestCase):
    """TC-SER-01：序列化输出必须包含 device_name 和 device_type_label 字段。"""

    def setUp(self):
        _reset_cache()
        self.user = User.objects.create_user(username='tester', password='pass123')
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.list_url = '/api/devices/fault-events/'

    def tearDown(self):
        _reset_cache()

    def test_device_name_field_present(self):
        """API 响应中每条记录都应含 device_name 字段（可为 null）。"""
        now = timezone.now()
        _make_fault_event(
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        # 预置空缓存（_load_cache 成功但无数据）
        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        self.assertEqual(resp.status_code, 200)
        results = resp.json()['results']
        self.assertGreater(len(results), 0)
        first = results[0]
        self.assertIn('device_name', first, "响应缺少 device_name 字段")

    def test_device_type_label_field_present(self):
        """API 响应中每条记录都应含 device_type_label 字段（可为 null）。"""
        now = timezone.now()
        _make_fault_event(
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        self.assertEqual(resp.status_code, 200)
        first = resp.json()['results'][0]
        self.assertIn('device_type_label', first, "响应缺少 device_type_label 字段")

    def test_both_new_fields_exist_simultaneously(self):
        """device_name 和 device_type_label 同时存在于响应中。"""
        now = timezone.now()
        _make_fault_event(
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        first = resp.json()['results'][0]
        self.assertIn('device_name', first)
        self.assertIn('device_type_label', first)


class TestSerializerMainPath(TestCase):
    """TC-SER-02：主路径——device_sn 命中 cache → device_name = 缓存中的 device_name。"""

    def setUp(self):
        _reset_cache()
        self.user = User.objects.create_user(username='tester2', password='pass123')
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.list_url = '/api/devices/fault-events/'

    def tearDown(self):
        _reset_cache()

    def test_device_sn_hit_returns_device_name(self):
        """
        device_sn='22155'（整数化后 22155）命中缓存 {22155: '新风'} → device_name='新风'。
        """
        now = timezone.now()
        _make_fault_event(
            device_sn='22155',
            product_code='250001',  # 非 DEVICE_NAME_OVERRIDE 码（130004 会被覆盖为'新风机'），验证缓存值直接返回
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        # 预置缓存命中
        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {22155: '新风'}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        self.assertEqual(resp.status_code, 200)
        first = resp.json()['results'][0]
        self.assertEqual(first['device_name'], '新风',
                         f"预期 device_name='新风'，实际='{first.get('device_name')}'")

    def test_device_sn_hit_supersedes_product_code(self):
        """
        当 device_sn 命中 cache 时，device_name 不为 None，即使 product_code 也命中 PRODUCT_CODE_LABELS。
        前端优先显示 device_name。
        """
        now = timezone.now()
        _make_fault_event(
            device_sn='22155',
            product_code='250001',  # 能耗表：非 DEVICE_NAME_OVERRIDE 码，device_name 应取缓存值而非 product_code
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {22155: '新风'}  # device_name 来自 DeviceNode
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        first = resp.json()['results'][0]
        # device_name 来自缓存（主路径）
        self.assertEqual(first['device_name'], '新风')
        # device_type_label 来自 PRODUCT_CODE_LABELS（兜底一，同时返回）
        self.assertEqual(first['device_type_label'], '能耗表')

    def test_cache_already_warm_no_reload(self):
        """
        缓存已预热（_cache_loaded_at > 0），TTL 未过期时不触发 _load_cache。
        """
        now = timezone.now()
        _make_fault_event(
            device_sn='22155',
            product_code='250001',  # 非 DEVICE_NAME_OVERRIDE 码（默认 130004 会被覆盖），验证缓存命中直接返回
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        # 手动预热缓存
        cache_module._cache = {22155: '水力模块'}
        cache_module._cache_loaded_at = 99999999.0  # 极大值，保证 TTL 未过期

        with patch('api.device_name_cache._load_cache') as mock_load:
            resp = self.client.get(self.list_url)

        # _load_cache 不应被调用（TTL 未过期）
        mock_load.assert_not_called()
        first = resp.json()['results'][0]
        self.assertEqual(first['device_name'], '水力模块')


class TestSerializerFallbackOne(TestCase):
    """TC-SER-03：兜底一——cache miss + product_code 命中 PRODUCT_CODE_LABELS → device_type_label。"""

    def setUp(self):
        _reset_cache()
        self.user = User.objects.create_user(username='tester3', password='pass123')
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.list_url = '/api/devices/fault-events/'

    def tearDown(self):
        _reset_cache()

    def test_cache_miss_product_code_hit_returns_type_label(self):
        """
        device_sn='99999'（cache 中不存在）+ product_code='270001'（水力模块）
        → device_name=None, device_type_label='水力模块'。
        """
        now = timezone.now()
        _make_fault_event(
            device_sn='99999',       # 不在缓存中
            product_code='270001',   # PRODUCT_CODE_LABELS 中的已知 code
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {22155: '新风'}  # 只有 22155，不含 99999
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        first = resp.json()['results'][0]
        self.assertIsNone(first['device_name'],
                          "device_sn 未命中 cache，device_name 应为 null")
        self.assertEqual(first['device_type_label'], '水力模块',
                         f"期望 device_type_label='水力模块'，实际='{first.get('device_type_label')}'")

    def test_various_known_product_codes(self):
        """验证所有 7 条 PRODUCT_CODE_LABELS 映射均可通过序列化器正确返回。"""
        from api.fault_consumer.constants import PRODUCT_CODE_LABELS

        now = timezone.now()

        for pc, expected_label in PRODUCT_CODE_LABELS.items():
            FaultEvent.objects.all().delete()
            _make_fault_event(
                device_sn='0',   # 确保 cache miss
                product_code=pc,
                fault_code='comm_fault_timeout',
                fault_type='comm',
                first_seen_at=now - timedelta(hours=1),
                last_seen_at=now - timedelta(minutes=30),
            )

            # cache 为空（sn=0 不命中）
            with patch('api.device_name_cache._load_cache') as mock_load:
                def _side_effect():
                    cache_module._cache = {}
                    cache_module._cache_loaded_at = 9999.0

                mock_load.side_effect = _side_effect
                cache_module._cache = {}
                cache_module._cache_loaded_at = 9999.0

                resp = self.client.get(self.list_url)

            self.assertEqual(resp.status_code, 200)
            results = resp.json()['results']
            self.assertGreater(len(results), 0, f"product_code={pc} 无结果")
            first = results[0]
            self.assertEqual(
                first['device_type_label'], expected_label,
                f"product_code={pc} 期望 label='{expected_label}'，实际='{first.get('device_type_label')}'"
            )


class TestSerializerFallbackTwo(TestCase):
    """TC-SER-04：兜底二——cache miss + product_code miss → device_name=None, device_type_label=None。"""

    def setUp(self):
        _reset_cache()
        self.user = User.objects.create_user(username='tester4', password='pass123')
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.list_url = '/api/devices/fault-events/'

    def tearDown(self):
        _reset_cache()

    def test_both_miss_returns_null_null(self):
        """
        device_sn='1'（脏数据，cache 无记录）+ product_code='UNKNOWN-CODE'（不在映射表中）
        → device_name=None, device_type_label=None。
        前端走兜底二：显示 device_sn + 角标"未识别"。
        """
        now = timezone.now()
        _make_fault_event(
            device_sn='1',
            product_code='UNKNOWN-CODE',
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}  # 空缓存
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        first = resp.json()['results'][0]
        self.assertIsNone(first['device_name'],
                          "双重 miss 时 device_name 应为 null")
        self.assertIsNone(first['device_type_label'],
                          "双重 miss 时 device_type_label 应为 null")

    def test_null_null_preserves_device_sn_field(self):
        """
        双重 miss 时，原始 device_sn 字段仍在响应中（前端渲染兜底二使用）。
        """
        now = timezone.now()
        _make_fault_event(
            device_sn='3',
            product_code='GARBAGE',
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        first = resp.json()['results'][0]
        # device_sn 字段保留（原始字段不删除，供兜底二使用）
        self.assertIn('device_sn', first)
        self.assertEqual(first['device_sn'], '3')
        self.assertIsNone(first['device_name'])
        self.assertIsNone(first['device_type_label'])


class TestSerializerEdgeCases(TestCase):
    """TC-SER-05：边界情况——device_sn 非整数字符串时 get_device_name 返回 None，不崩溃。"""

    def setUp(self):
        _reset_cache()
        self.user = User.objects.create_user(username='tester5', password='pass123')
        self.token = Token.objects.create(user=self.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        self.list_url = '/api/devices/fault-events/'

    def tearDown(self):
        _reset_cache()

    def test_non_numeric_device_sn_returns_none_gracefully(self):
        """
        device_sn='SN001'（非整数字符串），int('SN001') 会 ValueError。
        get_device_name 内的 try/except 应捕获，返回 None，不崩溃。
        """
        now = timezone.now()
        _make_fault_event(
            device_sn='SN001',
            product_code='130004',
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        self.assertEqual(resp.status_code, 200,
                         f"非整数 device_sn 不应导致 API 返回非 200，实际：{resp.status_code}")
        first = resp.json()['results'][0]
        # device_name 应为 None（int() 转换失败兜底）
        self.assertIsNone(first['device_name'])
        # device_type_label 来自 product_code='130004' → '新风机'
        self.assertEqual(first['device_type_label'], '新风机')

    def test_empty_device_sn_returns_none_gracefully(self):
        """device_sn='' 时，int('') 会 ValueError，应返回 None 不崩溃。"""
        now = timezone.now()
        _make_fault_event(
            device_sn='',
            product_code='NONE',
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        self.assertEqual(resp.status_code, 200)
        first = resp.json()['results'][0]
        self.assertIsNone(first['device_name'])

    def test_all_v061_fields_in_serializer_output(self):
        """
        确认 v0.6.1 新增字段（device_name, device_type_label）与已有全部字段同时出现在响应中。
        """
        EXPECTED_ALL_FIELDS = [
            'id', 'specific_part', 'device_sn', 'product_code',
            'fault_code', 'fault_type', 'fault_message', 'severity',
            'first_seen_at', 'last_seen_at', 'recovered_at',
            'is_active', 'created_at', 'updated_at',
            'device_name',        # v0.6.1 新增
            'device_type_label',  # v0.6.1 新增
        ]

        now = timezone.now()
        _make_fault_event(
            first_seen_at=now - timedelta(hours=1),
            last_seen_at=now - timedelta(minutes=30),
        )

        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            resp = self.client.get(self.list_url)

        self.assertEqual(resp.status_code, 200)
        first = resp.json()['results'][0]
        for field in EXPECTED_ALL_FIELDS:
            self.assertIn(field, first, f"响应缺少字段: {field}")
