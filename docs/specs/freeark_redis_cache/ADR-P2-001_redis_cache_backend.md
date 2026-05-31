# ADR-P2-001：Redis 缓存后端替换 LocMemCache

> **状态**: ACCEPTED（实现中）
> **日期**: 2026-05-31
> **版本**: perf-P2（Redis 缓存）
> **前置 ADR**: ADR-P1A-001/008（Redis Channel Layer + 多 worker，已回滚）

---

## 1. 背景与动机

### 1.1 当前状态

P0 引入了进程内 `LocMemCache`（`LOCATION='freeark-dashboard-cache'`），对看板接口提供 30s TTL 缓存。缓存通过 `cache_dashboard` 装饰器应用于以下接口：

| 接口 | 函数 | vary_params |
|---|---|---|
| `GET /api/dashboard/device-fault-summary/` | `dashboard_device_fault_summary` | False |
| `GET /api/dashboard/fault-summary/` | `dashboard_fault_summary` | False |
| `GET /api/dashboard/power-status/` | `dashboard_power_status` | False |
| `GET /api/dashboard/total-energy/` | `dashboard_total_energy` | True |
| `GET /api/dashboard/services/` | `dashboard_services` | False |

`cache_dashboard` 装饰器使用 `django.core.cache.cache`（全局默认 cache alias），与后端无关，换后端对装饰器透明（仅需在装饰器层加 try/except 兜底，见第 6 节）。

### 1.2 LocMemCache 的局限

- **per-process**：每个 uvicorn worker 维护独立的进程内字典。当前 P1-a 已回滚到 `--workers 1`，因此单 worker 下 LocMemCache 功能完全正确，无一致性问题。
- **重启丢失**：worker 重启（包括 `systemctl restart freeark-backend`、代码更新后重启、crash 恢复）立即清空缓存。对于 30s TTL 的看板数据，这是可接受的，但每次部署后的第一批请求会全打到数据库。
- **将来多 worker（P1 重试）的隐患**：若 P1-a 多 worker 需求再次被推进（待 P1-a 依赖问题解决），N 个 worker 会有 N 份独立缓存，Redis 共享缓存可一步到位解决一致性问题。

### 1.3 切换 Redis 缓存的收益

| 维度 | 当前（LocMemCache, --workers 1） | 目标（Redis, --workers 1） |
|---|---|---|
| 进程重启后缓存保留 | 否（立即清空） | 是（Redis 内存持久，除非 Redis 重启） |
| 多 worker 缓存一致 | 不适用（当前单 worker） | 天然满足（P1 重试铺路） |
| 网络跳数 | 0（进程内） | 1（loopback TCP，127.0.0.1:6379） |
| 额外故障点 | 无 | Redis 进程（已在生产运行）|

**当前（单 worker）收益评估**：收益是有限的——主要是"重启后缓存持久化"和"为多 worker 铺路"。TTL=30s 下，重启后最多 30s 内的请求会直打数据库，对树莓派 wlan0 → 远端 MySQL 的链路（单次 DB 往返实测约 24ms）来说可接受。但考虑到：

1. 生产 Redis 已装好（redis-server 8.0.2，bind 127.0.0.1:6379），无额外安装成本。
2. 本次顺带固定 redis-py 版本，解决 channels_redis 4.x 与 redis-py 8.x 的兼容问题（P1-a 回滚根因），为 P1 多 worker 重试清障。
3. 降级策略（见第 5 节）确保 Redis 不可用时看板功能不中断。

结论：**现在切换是值得的**，主要价值在于一举两得（缓存持久化 + 依赖修复 + P1 预铺路），在生产 Redis 已存在的条件下实施成本极低。

---

## 2. 关键约束与已知雷区

### 2.1 redis-py 版本兼容性（核心雷区）

P1-a 回滚根因：`channels_redis 4.3.0` 与 `redis-py 8.0.0` 不兼容，`RedisChannelLayer` 在 WS receive 循环触发 RESP3 `TimeoutError`。

本次缓存走 Django 缓存后端（`django.core.cache.backends.redis.RedisCache`），与 channels 路径不同，但**同样依赖 redis-py**。

经查（channels_redis 4.x releases / PyPI）：
- `channels_redis 4.x` 的依赖声明为 `redis>=4.0.0`（无上限），实际上 4.x 最后版本（4.3.1）在 redis-py 5.x 下通过测试，但 redis-py 8.x 引入了 RESP3 协议变更，导致 TimeoutError。
- **redis-py 5.x** 是当前兼容 channels_redis 4.x 的稳定版本，同时满足 Django 5.2 内置 `RedisCache` 的要求（django.core.cache.backends.redis 要求 redis>=4.x）。
- 固定策略：`redis>=5.0,<6.0`——在 requirements.txt 明确约束，不依赖 channels_redis 的传递依赖解析。

**固定 redis-py 版本的一举两得**：同时解决 channels_redis 的兼容问题（为将来 P1 多 worker 重试扫清依赖障碍）和缓存后端的版本确定性。

### 2.2 测试路径保护

`settings.py` 的 `_RUNNING_TESTS` 分支必须保持 `DummyCache`，确保所有 `manage.py test` 用例走无操作缓存，不受 Redis 服务器状态影响，也不产生用例间缓存串扰。

---

## 3. 选型决策：内置 RedisCache vs django-redis

### 方案 A：Django 5.2 内置 `django.core.cache.backends.redis.RedisCache`

Django 4.0 起内置 Redis 缓存后端，使用 redis-py 同步客户端。

优点：
- 零额外依赖（不需要安装 `django-redis` 包）。
- Django 官方维护，随 Django 版本升级保证兼容性。
- OPTIONS 字段直传 `redis-py ConnectionPool.from_url()`，支持 `socket_connect_timeout`、`socket_timeout`（防止 Redis 慢响应拖垮 worker 线程）。

缺点：
- 功能相对基础（无 `django-redis` 的 `delete_pattern`、`hkeys`、`IGNORE_EXCEPTIONS` 等扩展功能）。
- **没有内置 `IGNORE_EXCEPTIONS`**（实测 Django 5.2.14 源码确认，`RedisCache.__init__` 不处理此 key）：Redis 不可用时会向上抛 `redis.exceptions.RedisError`，需在调用层自行捕获。

### 方案 B：`django-redis`（第三方包）

优点：
- 功能丰富（scan/pattern delete、pipeline 支持等）。
- **原生支持 `IGNORE_EXCEPTIONS`**（Redis 不可用时静默降级，无需装饰器层额外兜底）。

缺点：
- 额外依赖（需安装 `django-redis`）。
- 与 redis-py 的版本兼容矩阵另需单独验证。

### 决策：选方案 A（内置 RedisCache）+ 装饰器层降级兜底

理由：项目当前缓存用法（`cache_dashboard` 装饰器仅用 `cache.get/set`）不需要 django-redis 的扩展功能；内置后端零依赖、官方维护。`IGNORE_EXCEPTIONS` 缺失问题通过在 `cache_dashboard` 装饰器层加 `try/except` 解决——这只需约 10 行代码，实现等价的降级语义（get 失败返回 None，set 失败静默忽略），且降级路径有 WARNING 日志可追踪，比 `IGNORE_EXCEPTIONS` 的静默黑盒更透明。

---

## 4. 配置方案

### 4.1 CACHES 生产配置

```python
# settings.py — 生产分支（_RUNNING_TESTS=False）
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': 'redis://127.0.0.1:6379/1',  # db=1，与 channels（db=0）隔离
        'OPTIONS': {
            # 传给 redis-py ConnectionPool.from_url()（小写，5.x/6.x 均支持）
            'socket_connect_timeout': 1,  # 连接超时 1s
            'socket_timeout': 1,          # 读写超时 1s
        },
        'KEY_PREFIX': 'fa_cache',         # 键隔离前缀，便于 redis-cli 手工排查
        'TIMEOUT': 30,                    # 全局默认 TTL（秒），与 P0 一致
    }
}
```

### 4.2 Redis db 隔离策略

| db | 用途 | 配置者 |
|---|---|---|
| db=0 | channels_redis（Channel Layer，WebSocket 消息）| settings.py CHANNEL_LAYERS |
| db=1 | Django 缓存后端（看板接口短期缓存）| settings.py CACHES（本 ADR）|

使用独立 db（`redis://127.0.0.1:6379/1`）+ `KEY_PREFIX='fa_cache'` 双重隔离，确保缓存键与 channels 的键空间完全分离。

### 4.3 TTL 策略

看板缓存的 TTL 保持与 P0 一致的 30s。各接口通过 `cache_dashboard(ttl=30, ...)` 在装饰器层控制，Redis 层的 `TIMEOUT=30` 作为全局默认。

### 4.4 KEY_PREFIX 与键结构

现有 `cache_dashboard` 生成的缓存键格式为 `dash:{prefix}[:params]`，加上 `KEY_PREFIX='fa_cache'`，Redis 中实际键形如 `fa_cache:1:dash:dashboard_power_status`（django 内置 RedisCache 的键格式为 `KEY_PREFIX:VERSION:USER_KEY`）。此格式具有良好可读性，便于 `redis-cli` 手工排查。

---

## 5. 失败降级策略（核心安全网）

### 5.1 实现方式：装饰器层 try/except

Django 内置 `RedisCache` 不支持 `IGNORE_EXCEPTIONS`（Django 5.2.14 源码实测确认），因此降级兜底在 `cache_dashboard` 装饰器层实现：

```python
def cache_dashboard(ttl=30, prefix=None, vary_params=False):
    def decorator(view_fn):
        @functools.wraps(view_fn)
        def wrapper(request, *args, **kwargs):
            key = ...
            try:
                cached = cache.get(key)
            except Exception as _cache_exc:
                _cache_logger.warning('cache_dashboard: Redis get 失败（降级为直查）: %s', _cache_exc)
                cached = None
            if cached is not None:
                return Response(cached)
            resp = view_fn(request, *args, **kwargs)
            if getattr(resp, 'status_code', None) == 200:
                try:
                    cache.set(key, resp.data, ttl)
                except Exception as _cache_exc:
                    _cache_logger.warning('cache_dashboard: Redis set 失败（降级为无缓存）: %s', _cache_exc)
            return resp
        return wrapper
    return decorator
```

降级行为：
- `cache.get` 失败（Redis 不可用/超时）→ 捕获异常，返回 `None`，视为缓存未命中，调用原始视图函数
- `cache.set` 失败 → 静默忽略，本次响应结果不写入缓存
- 不抛出任何异常，不返回 HTTP 500
- WARNING 日志记录降级事件，便于生产排查

完整降级流程：

```
cache.get(key) → Exception（降级）→ None
→ 调用原始视图函数（直接查数据库）
→ cache.set(...) → Exception（降级）→ 忽略
→ 返回正常响应（HTTP 200）
```

结论：**Redis 不可用时，看板接口完全退化为无缓存直查模式，HTTP 响应正常，不会 500**。性能会下降（退回 P0 前状态），但功能完全正确。

### 5.2 Socket 超时配置

`socket_connect_timeout=1` + `socket_timeout=1`（OPTIONS 中，由 redis-py 5.x ConnectionPool 解析）：确保 Redis 连接或响应慢时，最长 1s 后触发 `TimeoutError`，由装饰器 try/except 捕获降级，不会因 Redis 阻塞而拖垮 uvicorn worker 线程。

### 5.3 生产 Redis 可用性假设

生产 Redis（redis-server 8.0.2, bind 127.0.0.1:6379）已稳定运行，是 channels_redis P1-a 遗留的基础设施，有 systemd 开机自启保障。Redis 本身故障的概率低，即便故障，降级策略（5.1）确保看板功能不中断。

---

## 6. cache_dashboard 装饰器改动

**需要改动**（与初始预期不同）：Django 内置 RedisCache 无 `IGNORE_EXCEPTIONS`，需在装饰器层 cache.get 和 cache.set 调用处各加 try/except。

改动已提交到 `api/views.py`，详见实现阶段。

```
修改文件：FreeArkWeb/backend/freearkweb/api/views.py
修改函数：cache_dashboard()
改动量：约 +14 行（导入 logging，cache.get/set 各加 try/except 兜底）
向后兼容：是（DummyCache 下 try/except 不影响行为）
```

`cache.set(key, resp.data, ttl)` 存储的是 `resp.data`（Python 可序列化的 dict/list），Redis 序列化使用 `pickle`（django 内置 RedisCache 默认），这些对象完全可序列化。

---

## 7. requirements.txt 变更

```diff
+ # Redis 客户端（Django 缓存后端 + Channel Layer 共用；见 ADR-P2-001）
+ # 固定 5.x：兼容 channels_redis 4.x（P1-a 雷区：redis-py 8.0.0 引入 RESP3 变更，
+ # 与 channels_redis 4.x 的 RedisChannelLayer 不兼容，WS receive 循环抛 TimeoutError）。
+ # Django 5.2 内置 RedisCache 在 redis 5.x 下完全支持。
+ redis>=5.0,<6.0
```

注意：`channels_redis>=4.1.0` 已在 requirements.txt 中。`redis` 包是其传递依赖，本次显式声明并加上限版本，防止 pip 解析时拉取 redis-py 8.x。

---

## 8. 回滚路径

如需回滚，仅需修改 `settings.py` 的生产分支 CACHES（约 5 行）：

```python
# 回滚：恢复 LocMemCache
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'freeark-dashboard-cache',
    }
}
```

回滚不需要：
- 停止 Redis（可继续运行供 channels 使用）
- 修改 requirements.txt 的 redis 版本约束（仍需固定以保障 channels_redis 兼容）
- 重启任何非 freeark-backend 的服务

cache_dashboard 装饰器的 try/except 在 LocMemCache 下无副作用（LocMemCache 不抛异常）。

---

## 9. 实施阶段

| 阶段 | 内容 | 门控 |
|---|---|---|
| P2-1 设计（本 ADR）| 选型、依赖固定、降级策略 | ADR 评审通过 |
| P2-2 实现 | settings.py CACHES 改 Redis；requirements.txt 固定 redis-py；cache_dashboard 加 try/except | 代码变更 + 本地 manage.py test 全绿 |
| P2-3 预测试 | 生产 redis-server + 实际 redis-py 5.x 版本验证 get/set/TTL/降级；全套回归 | 预测试报告 |
| P2-4 文档更新 | SKILL.md 更新 CACHES/Redis db/降级说明 | 文档更新 |
| P2-5 生产部署 | 等用户 CONFIRM 后执行（生产 Redis 已在；主要步骤：pip install redis 5.x + 重启 backend）| 用户 CONFIRM |

---

## 10. 预测试验证矩阵

| 测试项 | 验证方法 | 期望结果 |
|---|---|---|
| redis-py 版本符合约束 | `pip show redis` | 5.x.x |
| Django 内置 RedisCache 可导入 | `python -c "from django.core.cache.backends.redis import RedisCache"` | 无报错 |
| 缓存 set/get | `cache.set('test', 42, 10); cache.get('test')` | 42 |
| TTL 过期 | set TTL=2s, sleep 3s, get | None |
| 缓存命中（装饰器）| 两次调用同一接口，第二次不触发原视图函数 | 第二次 call_count 不增加 |
| Redis 宕机降级 | 连接不存在端口，调用接口 | HTTP 200，WARNING 日志出现 |
| Redis 宕机 cache.get 不抛异常 | 验证装饰器 try/except 生效 | 返回 None，无 Exception 向上传播 |
| manage.py test 全套 | `python manage.py test api` | 全绿（DummyCache 路径）|
| redis db 隔离 | `redis-cli -n 1 keys 'fa_cache*'`; `redis-cli -n 0 keys 'fa_cache*'` | db=1 有键，db=0 无 fa_cache 键 |

---

*本 ADR 由 2026-05-31 perf-P2 任务产出，作者：Claude Code (PM Orchestrator)*
