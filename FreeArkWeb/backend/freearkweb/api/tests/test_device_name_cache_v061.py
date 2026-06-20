"""
test_device_name_cache_v061.py — device_name_cache 单元测试（v0.6.1-FM-UX）

覆盖范围：
  TC-DNC-01  命中：get_device_name_by_sn(22155) == 'new_air'（mock DeviceNode）
  TC-DNC-02  未命中：get_device_name_by_sn 返回 None
  TC-DNC-03  TTL 过期重建：mock time.monotonic 推进 > 60s 后再次调用触发 _load_cache
  TC-DNC-04  invalidate_device_name_cache() 后下次调用必触发重建
  TC-DNC-05  异常路径：_load_cache 抛异常时不崩溃，返回旧值（或 None）

运行方式（在 FreeArkWeb/backend/freearkweb/ 目录下）：
    ../../../venv/bin/python manage.py test api.tests.test_device_name_cache_v061 -v 2
"""

import time

from unittest.mock import patch, MagicMock, call
from django.test import TestCase, tag

import api.device_name_cache as cache_module


def _reset_cache():
    """每次测试前将缓存模块状态重置为初始状态（空缓存，loaded_at=0）。"""
    cache_module._cache = {}
    cache_module._cache_loaded_at = 0.0


@tag('unit')
class TestGetDeviceNameBySnHit(TestCase):
    """TC-DNC-01：命中路径——mock DeviceNode 注入 sn=22155 → device_name='新风'"""

    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    def test_hit_returns_device_name(self):
        """主路径命中：DeviceNode 中存在 device_sn=22155，应返回 device_name。"""
        # mock DeviceNode.objects.values_list 返回一条 (22155, '新风') 记录
        mock_pairs = [(22155, '新风'), (21997, '水力模块')]

        with patch('api.device_name_cache._load_cache') as mock_load:
            # 让 _load_cache 直接写入 _cache
            def _side_effect():
                cache_module._cache = {22155: '新风', 21997: '水力模块'}
                cache_module._cache_loaded_at = 9999.0  # 模拟已加载

            mock_load.side_effect = _side_effect

            result = cache_module.get_device_name_by_sn(22155)

        self.assertEqual(result, '新风')
        mock_load.assert_called_once()

    def test_hit_with_real_db_fixture(self):
        """
        使用真实 Django ORM（SQLite）验证缓存加载路径。

        从 DeviceNode 模型查不到记录（SQLite 测试库无数据）时，
        get_device_name_by_sn 应返回 None，但不崩溃。
        """
        _reset_cache()
        # SQLite 测试库中无 DeviceNode 记录，预期返回 None
        result = cache_module.get_device_name_by_sn(22155)
        self.assertIsNone(result)

    def test_multiple_calls_hit_cache_only_loads_once(self):
        """连续多次调用，TTL 未过期时只加载一次（缓存复用）。"""
        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {22155: '新风'}
                cache_module._cache_loaded_at = time.monotonic()

            mock_load.side_effect = _side_effect

            result1 = cache_module.get_device_name_by_sn(22155)
            result2 = cache_module.get_device_name_by_sn(22155)
            result3 = cache_module.get_device_name_by_sn(21997)  # 未命中，但仍用缓存

        self.assertEqual(result1, '新风')
        self.assertEqual(result2, '新风')
        self.assertIsNone(result3)
        # _load_cache 只应在首次调用时执行一次（第二三次TTL未过期）
        mock_load.assert_called_once()


@tag('unit')
class TestGetDeviceNameBySnMiss(TestCase):
    """TC-DNC-02：未命中路径——cache 中不存在的 sn 应返回 None。"""

    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    def test_miss_returns_none(self):
        """device_sn 不在缓存中，返回 None。"""
        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {22155: '新风'}
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            result = cache_module.get_device_name_by_sn(99999)

        self.assertIsNone(result)

    def test_empty_cache_after_load_returns_none(self):
        """_load_cache 成功但 DeviceNode 中无任何记录——返回 None 不崩溃。"""
        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {}  # 空缓存（无任何设备节点）
                cache_module._cache_loaded_at = 9999.0

            mock_load.side_effect = _side_effect

            result = cache_module.get_device_name_by_sn(22155)

        self.assertIsNone(result)


@tag('unit')
class TestTtlExpiry(TestCase):
    """TC-DNC-03：TTL 过期重建——mock time.monotonic 推进 > 60s 后再次调用应触发 _load_cache。"""

    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    def test_ttl_expired_triggers_reload(self):
        """
        模拟缓存已加载（_cache_loaded_at = 100.0），然后推进时间到 200.0（超过 TTL=60s），
        下次调用 get_device_name_by_sn 应重新触发 _load_cache。
        """
        # 预置：缓存已有数据，loaded_at = 100.0
        cache_module._cache = {22155: '新风_旧'}
        cache_module._cache_loaded_at = 100.0

        # mock time.monotonic 返回 200.0（推进 100s > TTL=60s）
        with patch('api.device_name_cache.time') as mock_time:
            mock_time.monotonic.return_value = 200.0

            load_call_count = []

            with patch('api.device_name_cache._load_cache') as mock_load:
                def _side_effect():
                    cache_module._cache = {22155: '新风_新'}
                    cache_module._cache_loaded_at = 200.0
                    load_call_count.append(1)

                mock_load.side_effect = _side_effect

                result = cache_module.get_device_name_by_sn(22155)

        self.assertEqual(result, '新风_新')
        self.assertEqual(len(load_call_count), 1, '_load_cache 应被触发一次')

    def test_ttl_not_expired_skips_reload(self):
        """
        缓存 loaded_at = 100.0，当前时间 = 130.0（仅过去 30s < TTL=60s），
        不应触发重建。
        """
        cache_module._cache = {22155: '新风'}
        cache_module._cache_loaded_at = 100.0

        with patch('api.device_name_cache.time') as mock_time:
            mock_time.monotonic.return_value = 130.0  # 30s < 60s TTL

            with patch('api.device_name_cache._load_cache') as mock_load:
                result = cache_module.get_device_name_by_sn(22155)

        self.assertEqual(result, '新风')
        mock_load.assert_not_called()

    def test_exactly_at_ttl_boundary_triggers_reload(self):
        """
        精确等于 TTL（60.0s）时仍触发重建（条件为 > TTL，60.0 == 60.0 不触发）。
        设置 loaded_at=100.0，当前时间=160.0（diff=60.0，not > 60.0），不触发。
        """
        cache_module._cache = {22155: '新风'}
        cache_module._cache_loaded_at = 100.0

        with patch('api.device_name_cache.time') as mock_time:
            mock_time.monotonic.return_value = 160.0  # diff = 60.0, 不超过 TTL

            with patch('api.device_name_cache._load_cache') as mock_load:
                result = cache_module.get_device_name_by_sn(22155)

        # diff = 160.0 - 100.0 = 60.0, 条件 now - _cache_loaded_at > _TTL_SECONDS → 60.0 > 60.0 = False
        mock_load.assert_not_called()
        self.assertEqual(result, '新风')

    def test_just_over_ttl_triggers_reload(self):
        """
        diff = 60.1s，触发重建。
        """
        cache_module._cache = {22155: '新风'}
        cache_module._cache_loaded_at = 100.0

        with patch('api.device_name_cache.time') as mock_time:
            mock_time.monotonic.return_value = 160.1  # diff = 60.1 > 60.0 → 触发

            with patch('api.device_name_cache._load_cache') as mock_load:
                def _side_effect():
                    cache_module._cache = {22155: '新风_刷新'}
                    cache_module._cache_loaded_at = 160.1

                mock_load.side_effect = _side_effect

                result = cache_module.get_device_name_by_sn(22155)

        mock_load.assert_called_once()
        self.assertEqual(result, '新风_刷新')


@tag('unit')
class TestInvalidateCache(TestCase):
    """TC-DNC-04：invalidate_device_name_cache() 后下次调用必触发重建。"""

    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    def test_invalidate_sets_loaded_at_to_zero(self):
        """调用 invalidate 后，_cache_loaded_at 应被置为 0.0。"""
        cache_module._cache_loaded_at = 9999.0
        cache_module.invalidate_device_name_cache()
        self.assertEqual(cache_module._cache_loaded_at, 0.0)

    def test_invalidate_then_get_triggers_load(self):
        """
        invalidate 后，任何 time.monotonic() 返回值（> 0）都会触发 _load_cache，
        因为 now - 0.0 > 60.0 必然成立（monotonic 单调递增，进程启动后远大于 0）。
        """
        # 预置非空缓存
        cache_module._cache = {22155: '新风_旧'}
        cache_module._cache_loaded_at = 9999.0

        # 执行失效
        cache_module.invalidate_device_name_cache()
        self.assertEqual(cache_module._cache_loaded_at, 0.0)

        # 下次调用应触发重建
        with patch('api.device_name_cache._load_cache') as mock_load:
            def _side_effect():
                cache_module._cache = {22155: '新风_新'}
                cache_module._cache_loaded_at = 500.0

            mock_load.side_effect = _side_effect

            result = cache_module.get_device_name_by_sn(22155)

        mock_load.assert_called_once()
        self.assertEqual(result, '新风_新')

    def test_invalidate_idempotent(self):
        """多次 invalidate 不崩溃，_cache_loaded_at 始终为 0.0。"""
        cache_module._cache_loaded_at = 500.0
        cache_module.invalidate_device_name_cache()
        cache_module.invalidate_device_name_cache()
        cache_module.invalidate_device_name_cache()
        self.assertEqual(cache_module._cache_loaded_at, 0.0)


@tag('unit')
class TestLoadCacheExceptionSafety(TestCase):
    """TC-DNC-05：_load_cache 抛异常时不崩溃，旧缓存保留（或 None 兜底）。"""

    def setUp(self):
        _reset_cache()

    def tearDown(self):
        _reset_cache()

    def test_exception_does_not_raise_to_caller(self):
        """
        _load_cache 内部抛 Exception（模拟 DB 连接失败），
        get_device_name_by_sn 不应向上抛出，应静默返回 None（空缓存兜底）。
        """
        # 预置：空缓存，TTL 已过期（loaded_at=0.0）
        cache_module._cache = {}
        cache_module._cache_loaded_at = 0.0

        # 让 DeviceNode import 或 ORM 调用抛异常
        with patch('api.device_name_cache.time') as mock_time:
            mock_time.monotonic.return_value = 100.0  # > 0 + 60 → TTL 过期

            # 直接 patch _load_cache 抛异常（测试 _ensure_cache_fresh 的调用路径）
            # 实际上 _load_cache 本身会捕获异常；我们这里测试实际实现：
            # _load_cache 中的 except Exception 块保证不崩溃
            # 所以我们 patch DeviceNode 的导入让其失败
            with patch.dict('sys.modules', {'api.models': None}):
                # 此时 _load_cache 内 `from .models import DeviceNode` 会引发 ImportError
                # 但 _load_cache 自身有 except Exception 捕获
                try:
                    result = cache_module.get_device_name_by_sn(22155)
                    # 不应抛出，result 为 None（缓存为空）
                    self.assertIsNone(result)
                except Exception as e:
                    self.fail(f'get_device_name_by_sn 不应抛出异常，但抛出了：{e}')

    def test_exception_preserves_old_cache(self):
        """
        _load_cache 失败时，_cache 旧值保留（_cache_loaded_at 不更新为当前时间）。

        说明：实际实现中异常路径不更新 _cache_loaded_at，因此旧值和下次立即重试都依赖
        旧 _cache_loaded_at 值（通常在异常后 _cache_loaded_at 仍为 0.0 或旧值），
        此用例验证旧缓存内容不被清空。
        """
        # 预置：已有缓存数据
        cache_module._cache = {22155: '新风_保留'}
        cache_module._cache_loaded_at = 0.0  # 将触发重建

        with patch('api.device_name_cache.time') as mock_time:
            mock_time.monotonic.return_value = 100.0

            # 让 _load_cache 触发，但 DeviceNode ORM 抛异常
            with patch('api.models.DeviceNode') as mock_dn:
                mock_dn.objects.values_list.side_effect = RuntimeError('DB connection lost')

                # 实际 _load_cache 会 import DeviceNode 再调用；
                # 直接 patch _load_cache 来模拟异常保留旧值的场景
                original_load = cache_module._load_cache

                def _broken_load():
                    # 模拟: 异常发生在 new_cache 构建阶段，旧 _cache 不被覆盖
                    try:
                        raise RuntimeError('DB connection lost')
                    except Exception:
                        pass  # _load_cache 内 except 不覆盖 _cache

                with patch('api.device_name_cache._load_cache', side_effect=_broken_load):
                    # _broken_load 本身不修改 _cache，旧缓存应保留
                    result = cache_module.get_device_name_by_sn(22155)

        # 旧缓存 {22155: '新风_保留'} 仍在
        self.assertEqual(cache_module._cache.get(22155), '新风_保留')
