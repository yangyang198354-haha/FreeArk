"""
预测试：Redis 缓存后端验证（perf-P2，ADR-P2-001）

目的
----
在正式全面铺开前，使用实际安装的 redis-py 版本，验证：
1. django.core.cache.backends.redis.RedisCache 在 redis-py 5.x 下正常工作
2. get/set/TTL 生效
3. Redis 宕机时 IGNORE_EXCEPTIONS 使 cache.get 返回 None（不抛异常）
4. cache_dashboard 装饰器在 Redis 后端下功能与 LocMem 一致
5. manage.py test（DummyCache 路径）正常通过（即本文件中的 TestCase 不依赖 Redis）

运行方式
--------
（A）Django TestCase 路径（用 DummyCache，无需 Redis）：
    python manage.py test api.tests.test_redis_cache_pretest

（B）独立预测试脚本（需要 Redis 服务运行）：
    # 在 backend/freearkweb 目录下：
    python -m api.tests.test_redis_cache_pretest --live

注意：
- 所有 TestCase 必须在 DummyCache 下通过（_RUNNING_TESTS=True 时 settings 走 DummyCache）。
- 需要真实 Redis 的测试在 `--live` 模式下通过独立函数运行（不进入 TestCase，不影响 CI）。
"""

import sys
import time
import unittest
import os

# ── Django TestCase（用 DummyCache，始终可通过）──────────────────────────────

from django.test import TestCase, RequestFactory, override_settings, tag
from django.core.cache import cache
from rest_framework.response import Response


@tag('unit')
class DummyCacheBaselineTest(TestCase):
    """
    验证测试路径仍走 DummyCache（settings._RUNNING_TESTS=True）。
    这些测试在 manage.py test 下必须 100% 通过，不依赖 Redis。
    """

    def test_cache_backend_is_dummy_during_test_run(self):
        """测试运行时必须走 DummyCache，不是 RedisCache。"""
        from django.conf import settings
        backend = settings.CACHES['default']['BACKEND']
        self.assertIn(
            'dummy', backend.lower(),
            f"测试路径期望 DummyCache，实际是 {backend}。"
            "若看到此失败，说明 _RUNNING_TESTS 分支被意外修改。"
        )

    def test_cache_get_returns_none_in_dummy(self):
        """DummyCache 下 cache.get 始终返回 None（无操作缓存）。"""
        cache.set('pretest_sentinel', 'hello', 60)
        result = cache.get('pretest_sentinel')
        # DummyCache: set 是 no-op，所以 get 返回默认值 None
        self.assertIsNone(result, "DummyCache 下 cache.get 应返回 None（set 是 no-op）")

    def test_cache_dashboard_decorator_structure(self):
        """
        验证 cache_dashboard 装饰器可以正常导入和应用，
        不依赖任何特定缓存后端。
        """
        from api.views import cache_dashboard

        @cache_dashboard(ttl=10, prefix='pretest_view')
        def mock_view(request):
            return Response({'value': 42})

        factory = RequestFactory()
        request = factory.get('/test/')
        # 给 request 添加 query_params 属性（DRF 的 request 才有，Django 的没有）
        request.query_params = request.GET

        resp = mock_view(request)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['value'], 42)

    def test_cache_dashboard_vary_params(self):
        """验证 vary_params=True 的键生成不会抛异常。"""
        from api.views import cache_dashboard

        @cache_dashboard(ttl=10, prefix='pretest_vary', vary_params=True)
        def mock_view(request):
            return Response({'param': request.query_params.get('x', 'default')})

        factory = RequestFactory()
        req1 = factory.get('/test/?x=1')
        req1.query_params = req1.GET
        req2 = factory.get('/test/?x=2')
        req2.query_params = req2.GET

        resp1 = mock_view(req1)
        resp2 = mock_view(req2)
        self.assertEqual(resp1.data['param'], '1')
        self.assertEqual(resp2.data['param'], '2')


# ── 独立实时预测试（需要 Redis）────────────────────────────────────────────────

def _check_redis_py_version():
    """检查 redis-py 版本是否在 5.x 范围内。"""
    import redis
    ver = redis.__version__
    major = int(ver.split('.')[0])
    print(f"[版本检查] redis-py: {ver}")
    assert major == 5, f"期望 redis-py 5.x，实际版本 {ver}。请执行: pip install 'redis>=5.0,<6.0'"
    print("  PASS: redis-py 版本符合 5.x 约束")


def _check_django_redis_cache_import():
    """验证 Django 内置 RedisCache 可正常导入。"""
    from django.core.cache.backends.redis import RedisCache
    print("[导入检查] django.core.cache.backends.redis.RedisCache")
    print("  PASS: 导入成功")


def _test_cache_basic_ops(redis_cache):
    """验证 set/get/TTL 生效。"""
    print("[基础操作] cache set/get/TTL...")

    # set + get
    redis_cache.set('pretest:basic', 'hello_redis', 30)
    val = redis_cache.get('pretest:basic')
    assert val == 'hello_redis', f"get 期望 'hello_redis'，实际 {val!r}"
    print("  PASS: set/get 正确")

    # TTL 过期
    redis_cache.set('pretest:ttl_expire', 'expires_soon', 2)
    val_before = redis_cache.get('pretest:ttl_expire')
    assert val_before == 'expires_soon', "TTL 设置前 get 应返回值"
    print("  等待 TTL 过期（3s）...")
    time.sleep(3)
    val_after = redis_cache.get('pretest:ttl_expire')
    assert val_after is None, f"TTL 过期后 get 期望 None，实际 {val_after!r}"
    print("  PASS: TTL 过期正确")

    # get 不存在的键
    val_missing = redis_cache.get('pretest:nonexistent_key_xyz')
    assert val_missing is None, f"不存在的键期望 None，实际 {val_missing!r}"
    print("  PASS: 不存在键返回 None")

    # 缓存复杂对象（dict，模拟 resp.data）
    test_data = {'success': True, 'data': {'count': 42, 'items': [1, 2, 3]}}
    redis_cache.set('pretest:dict', test_data, 30)
    val_dict = redis_cache.get('pretest:dict')
    assert val_dict == test_data, f"dict get/set 不一致：{val_dict!r}"
    print("  PASS: dict 对象 pickle 序列化/反序列化正确")


def _test_redis_db_isolation(redis_cache):
    """验证缓存使用 db=1，不影响 db=0（channels 用途）。"""
    print("[DB 隔离] 验证 db=1 键隔离...")
    import redis as redis_module

    # 写入一个缓存键
    redis_cache.set('pretest:isolation_test', 'isolated', 30)

    # 用 redis-py 直连 db=0，确认该键不存在
    r_db0 = redis_module.Redis(host='127.0.0.1', port=6379, db=0)
    # Django 内置 RedisCache 的键格式：KEY_PREFIX:VERSION:USER_KEY
    # 实际键名取决于 Django 的 make_key，通常为 "fa_cache:1:pretest:isolation_test"
    # 我们无法直接预测精确键名，但可以通过 keys 扫描验证 db=0 是否存在 fa_cache 前缀键
    keys_in_db0 = r_db0.keys('fa_cache*')
    assert len(keys_in_db0) == 0, \
        f"db=0 中意外出现了 fa_cache 键: {keys_in_db0}。缓存应写入 db=1。"
    print("  PASS: db=0 无 fa_cache 前缀键（db 隔离有效）")

    # 验证 db=1 存在该键
    r_db1 = redis_module.Redis(host='127.0.0.1', port=6379, db=1)
    keys_in_db1 = r_db1.keys('fa_cache*')
    assert len(keys_in_db1) > 0, \
        "db=1 中未找到 fa_cache 前缀键。Django RedisCache KEY_PREFIX 配置可能有误。"
    print(f"  PASS: db=1 存在 {len(keys_in_db1)} 个 fa_cache 键（db 隔离有效）")


def _test_ignore_exceptions_degradation():
    """
    验证 cache_dashboard 的 try/except 降级兜底在 Redis 不可用时生效。

    注意：Django 内置 RedisCache 没有 IGNORE_EXCEPTIONS 选项（Django 5.2 源码确认），
    降级兜底由 cache_dashboard 装饰器的 try/except 实现。
    此测试直接构造一个连接不存在端口的 RedisCache 实例模拟 Redis 宕机，
    然后通过带兜底逻辑的 cache_dashboard 装饰器验证不会 500。
    """
    print("[降级验证] cache_dashboard try/except 兜底，Redis 宕机不抛异常...")
    from django.core.cache.backends.redis import RedisCache
    from api.views import cache_dashboard
    from rest_framework.response import Response
    import django.core.cache as _cache_module

    # 构造一个指向不存在端口的 RedisCache（模拟宕机）
    # Django 5.2 RedisCache.__init__(self, server, params)
    bad_cache = RedisCache(
        'redis://127.0.0.1:16379',  # 不存在的端口，位置参数 server
        {
            'OPTIONS': {
                'socket_connect_timeout': 0.3,
                'socket_timeout': 0.3,
            },
            'KEY_PREFIX': 'fa_pretest_bad',
            'TIMEOUT': 30,
        }
    )

    # 直接测试 bad_cache.get 是否抛出异常（验证 Django 自身确实会抛）
    did_raise = False
    try:
        bad_cache.get('some_key')
    except Exception:
        did_raise = True
    assert did_raise, \
        "警告：Django RedisCache 在 Redis 不可用时没有抛出异常，这与预期不同。" \
        "请确认 redis-py 版本和 socket 超时配置是否生效。"
    print("  已确认：Django RedisCache 在 Redis 不可用时抛出异常（符合预期，无 IGNORE_EXCEPTIONS）")

    # 现在通过 cache_dashboard 装饰器（带 try/except 兜底）验证不会 500
    call_count = [0]

    class FakeRequest:
        query_params = {}
        method = 'GET'

    # 临时把 django.core.cache.cache 替换为 bad_cache 来测试降级
    original_cache = _cache_module.cache
    _cache_module.cache = bad_cache

    # 同时需要替换 views 模块里的 cache 引用
    import api.views as _views_module
    original_views_cache = _views_module.cache
    _views_module.cache = bad_cache

    try:
        @cache_dashboard(ttl=10, prefix='pretest:bad_redis')
        def mock_view_bad(request):
            call_count[0] += 1
            return Response({'ok': True, 'call': call_count[0]})

        req = FakeRequest()

        # 两次调用都应成功返回（Redis 宕机降级为直查，不 500）
        resp1 = mock_view_bad(req)
        assert resp1.status_code == 200, f"期望 200，实际 {resp1.status_code}"
        assert resp1.data['ok'] is True
        assert call_count[0] == 1, "第 1 次应调用原视图"

        resp2 = mock_view_bad(req)
        assert resp2.status_code == 200, f"期望 200，实际 {resp2.status_code}"
        # Redis 宕机下每次都是缓存未命中，call_count 应继续增加
        assert call_count[0] == 2, \
            "Redis 宕机时每次应调用原视图（无缓存），call_count 应为 2"

        print("  PASS: Redis 不可用时 cache_dashboard 降级为直查，HTTP 200 正常返回")
    finally:
        # 恢复原始 cache
        _cache_module.cache = original_cache
        _views_module.cache = original_views_cache


def _test_cache_dashboard_decorator_with_real_redis(redis_cache):
    """验证 cache_dashboard 装饰器在 Redis 后端下命中/未命中行为。"""
    print("[装饰器验证] cache_dashboard + Redis 后端...")

    # 手动清理测试键
    redis_cache.delete('pretest:decorator_view')

    call_count = [0]  # 用列表包裹以在闭包中修改

    from api.views import cache_dashboard
    from rest_framework.response import Response
    from django.test import RequestFactory

    @cache_dashboard(ttl=10, prefix='pretest:decorator_view')
    def mock_view(request):
        call_count[0] += 1
        return Response({'call': call_count[0]})

    factory = RequestFactory()

    # 构造一个有 query_params 属性的 request
    class FakeRequest:
        query_params = {}
        method = 'GET'

    req = FakeRequest()

    # 第 1 次调用：缓存未命中，应调用原始视图
    resp1 = mock_view(req)
    assert call_count[0] == 1, f"第 1 次调用期望 call_count=1，实际 {call_count[0]}"
    assert resp1.data['call'] == 1

    # 第 2 次调用：缓存命中，不应调用原始视图
    resp2 = mock_view(req)
    assert call_count[0] == 1, \
        f"第 2 次调用期望 call_count 仍为 1（缓存命中），实际 {call_count[0]}"
    assert resp2.data['call'] == 1, "缓存命中应返回第 1 次的响应数据"

    print("  PASS: 第 1 次未命中（调用原视图），第 2 次命中（使用缓存数据）")

    # 清理
    redis_cache.delete('pretest:decorator_view')


def run_live_pretest():
    """
    运行所有需要真实 Redis 的预测试。
    调用：python -m api.tests.test_redis_cache_pretest --live
    """
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'freearkweb.settings')
    # 强制不走测试模式（live 预测试需要 RedisCache 而非 DummyCache）
    # 注意：这里我们直接操作 sys.argv，使 _RUNNING_TESTS 判断为 False
    original_argv = sys.argv[:]
    sys.argv = ['pretest']  # 移除 'test' 关键字
    django.setup()
    sys.argv = original_argv

    from django.conf import settings

    print("=" * 60)
    print("FreeArk perf-P2 Redis 缓存预测试（Live 模式）")
    print("=" * 60)
    print(f"CACHES backend: {settings.CACHES['default']['BACKEND']}")
    print(f"CACHES location: {settings.CACHES['default'].get('LOCATION', 'N/A')}")
    print()

    # 验证当前不是 DummyCache（live 模式需要 RedisCache）
    backend = settings.CACHES['default']['BACKEND']
    if 'dummy' in backend.lower():
        print("WARNING: 当前 CACHES 是 DummyCache。")
        print("  Live 预测试需要 RedisCache 后端。")
        print("  请确认在非测试模式下运行（sys.argv 不含 'test'）。")
        print("  尝试：cd FreeArkWeb/backend/freearkweb && python -m api.tests.test_redis_cache_pretest --live")
        sys.exit(1)

    failures = []

    def run_test(name, fn, *args):
        try:
            fn(*args)
        except Exception as e:
            print(f"  FAIL: {name}: {type(e).__name__}: {e}")
            failures.append((name, e))

    # 获取 Redis cache 实例
    from django.core.cache import cache as django_cache

    print("--- 测试 1: redis-py 版本检查 ---")
    run_test("redis_py_version", _check_redis_py_version)

    print()
    print("--- 测试 2: Django RedisCache 导入检查 ---")
    run_test("django_redis_cache_import", _check_django_redis_cache_import)

    print()
    print("--- 测试 3: 基础 set/get/TTL 操作 ---")
    run_test("cache_basic_ops", _test_cache_basic_ops, django_cache)

    print()
    print("--- 测试 4: Redis db 隔离（缓存 db=1，不污染 db=0）---")
    run_test("redis_db_isolation", _test_redis_db_isolation, django_cache)

    print()
    print("--- 测试 5: IGNORE_EXCEPTIONS 降级验证 ---")
    run_test("ignore_exceptions_degradation", _test_ignore_exceptions_degradation)

    print()
    print("--- 测试 6: cache_dashboard 装饰器命中/未命中 ---")
    run_test("cache_dashboard_decorator", _test_cache_dashboard_decorator_with_real_redis, django_cache)

    print()
    print("=" * 60)
    if failures:
        print(f"预测试结果: FAIL（{len(failures)} 项失败）")
        for name, exc in failures:
            print(f"  - {name}: {exc}")
        sys.exit(1)
    else:
        print("预测试结果: PASS（全部 6 项通过）")
        print()
        print("下一步：")
        print("  1. 运行完整回归测试: python manage.py test api")
        print("  2. 查看预测试报告（见 docs/specs/freeark_redis_cache/pretest_report.md）")
        print("  3. CONFIRM 后执行生产部署")
    print("=" * 60)


if __name__ == '__main__':
    if '--live' in sys.argv:
        run_live_pretest()
    else:
        # 默认走 unittest（DummyCache 路径，可由 manage.py test 驱动）
        unittest.main(argv=[sys.argv[0]])
