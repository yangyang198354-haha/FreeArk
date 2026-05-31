# P1-a 架构设计：Redis Channel Layer + 多 Worker 解除串行瓶颈

> ⚠️ **状态：已回滚（2026-05-31）。** 生产部署后发现 **`channels_redis 4.3.0` 与
> `redis-py 8.0.0` 不兼容**：RedisChannelLayer 在 WS consumer 的 receive 循环中触发
> `redis.exceptions.TimeoutError: Timeout reading from 127.0.0.1:6379`（RESP3 读取超时），
> 导致聊天连接报错。已按本文回滚方案退回 `InMemoryChannelLayer` + `--workers 1`（已恢复正常）。
> **重试前置条件**：在 requirements 固定兼容的 redis-py 版本（channels_redis 4.x 实测需
> redis-py 5.x；redis-py 8.x 不兼容），并在装好 Redis 的环境本地验证 WS 收发后再上生产。
> Redis 服务本身已装好可保留。chat_session 修复（commit 独立）不受影响、已保留。

> **版本**: 1.0.0  
> **日期**: 2026-05-31  
> **作者**: claude-sonnet-4-6 (PM Orchestrator / Architect)  
> **关联需求**: perf-P1-a  
> **前置 commit**: c84eb12 (P0 看板缓存 + fetch 超时)

---

## 1. 问题背景

P0 已上线（c84eb12）：看板查询合并 + 30s LocMemCache 缓存 + 前端 fetch 超时。
缓存命中后单次响应从 ~800ms 降至 <5ms，但根因未消除：

**根因**：uvicorn `--workers 1` 单进程串行——一个慢接口（或缓存未命中时的多次 DB 往返）
占住唯一 worker，后续所有请求（含鉴权 401 检查）进入 OS 等待队列，实测排队 10~60s。

**目标**：换 Redis Channel Layer，解锁多 worker，让多个请求可并行处理。

---

## 2. 约束清单

| 编号 | 约束 | 来源 |
|------|------|------|
| C-01 | 不破坏 WebSocket 聊天（/ws/chat/ ChatConsumer）| 用户硬约束 |
| C-02 | 跑通 `manage.py test` 全套（自动 SQLite）| 用户硬约束 |
| C-03 | 生产禁止 Docker | 用户硬约束 |
| C-04 | ARM aarch64（Pi 5）兼容 | 环境约束 |
| C-05 | 不改 .env / package-lock.json / heartbeat_broker_config.json | 用户安全护栏 |
| C-06 | 保留可回滚路径（InMemoryChannelLayer + --workers 1）| 用户明确要求 |
| C-07 | 不擅自 git push，不在未确认时部署生产 | 用户安全护栏 |

---

## 3. 决策汇总（ADR 列表）

### ADR-P1A-001：Channel Layer 选型 — channels_redis（RedisChannelLayer）

**决策**：将 `CHANNEL_LAYERS.default.BACKEND` 从 `channels.layers.InMemoryChannelLayer`
改为 `channels_redis.core.RedisChannelLayer`，hosts 指向 `redis://127.0.0.1:6379`。

**备选方案对比**：

| 方案 | 优点 | 缺点 | 结论 |
|------|------|------|------|
| A. 保留 InMemoryChannelLayer，--workers 1 | 无需新依赖 | 串行瓶颈不消除，P1-a 无意义 | 放弃 |
| B. channels_redis（RedisChannelLayer）| 官方推荐，跨进程共享，pip 可安装 | 需 Redis 服务，多一个依赖点 | **选定** |
| C. 无 Channel Layer（纯 HTTP + SSE）| 不用 channels 基础设施 | 需重写聊天协议，破坏 ADR-001 | 放弃 |

**理由**：
- channels_redis 是 Django Channels 官方推荐的生产 Channel Layer。
- Redis 在 Pi 5 ARM64 (Debian trixie) 上 apt 直接可装，无需 Docker。
- ChatConsumer 是 `AsyncWebsocketConsumer`，连接是长连接（单次握手后的所有消息
  在同一 worker 内处理）。Channel Layer 在本项目的 ChatConsumer 实际上**不做跨
  worker 消息分发**（send/receive 直接走 WebSocket 连接对象），只有 group_send
  才走 Channel Layer。当前代码未使用任何 group_send，故 Channel Layer 对聊天
  功能的影响仅限于初始化阶段引入 Redis 连接——ChatConsumer 本身不依赖 Channel Layer
  的消息路由。换 Redis 后聊天行为完全不变。

**风险说明（ChatConsumer 多 worker 安全性分析）**：

ChatConsumer 是 `AsyncWebsocketConsumer`。uvicorn 多 worker 的模型是多进程（fork），
每个 WebSocket 连接由建立它的那个 worker 进程独占处理。以下是关键点：

- `connect()` / `receive()` / `disconnect()` 全部在同一个进程内的同一个 Consumer
  实例上执行——不跨进程。
- `self.session_key` / `self.user` / `self._is_streaming` / `self._pending_assistant_content`
  是实例变量，单连接内隔离，无跨进程共享。
- `OpenClawAdapter.stream_chat()` 是 aiohttp WS 调用，loopback 127.0.0.1，
  不依赖进程内全局状态。
- `chat_memory` (DB 操作) 通过 `sync_to_async` + MySQL 走数据库，天然跨进程一致。
- 结论：ChatConsumer 在多 worker 下**功能完全正确**，不会出现跨 worker 消息丢失
  或 session 混乱问题。

---

### ADR-P1A-002：Worker 数量选型 — 2

**决策**：`--workers 2`（从 1 提升到 2）。

**依据**：

Pi 5 有 4 个物理核，4GB RAM。uvicorn 多进程（pre-fork）每个 worker 是独立 Django
进程，内存占用大约 80~120MB（含 Django ORM + Channels + aiohttp 等）。

| 选项 | 内存估算 | 并行度 | 分析 |
|------|----------|--------|------|
| --workers 1 | ~100MB | 1（有瓶颈）| 当前状态，P1-a 前 |
| --workers 2 | ~200MB | 2 | 消除单点排队，余 3.8GB 给 OS/MySQL/OpenClaw |
| --workers 4 | ~400MB | 4 | 并行度提高但收益有限（瓶颈已移至 DB / OpenClaw RTT）|
| --workers 8 | ~800MB | 8 | 超出 4 核，进程切换开销反而上升；内存压力大 |

Pi 5 上还需要预留内存给：
- MySQL 客户端连接（每 worker 有 CONN_MAX_AGE=300 的持久连接）
- OpenClaw Gateway（Node.js，约 150~250MB）
- OS / Nginx / MQTT consumers 等

**选定 2 worker**：兼顾并行收益与内存安全边际，Pi 5 4GB 充足。
如果将来看板并发显著提升，可在不换方案的情况下调 `--workers 3`。

**注意**：uvicorn 的 `--workers` 参数是进程级 fork，不是线程。
每个 worker 内部仍是 asyncio 事件循环，可并发处理多个协程（WebSocket 连接 + HTTP 请求混合）。
实际并行上限 = workers × asyncio 并发能力（远大于 1）。

---

### ADR-P1A-003：看板缓存选型 — 保留 LocMemCache（per-worker），不切 Redis

**决策**：保留 `django.core.cache.backends.locmem.LocMemCache`，不切换到 django-redis。

**背景**：P0 的 `cache_dashboard` 装饰器（views.py）和 `fault_utils.py` 的故障数
缓存都用 Django 默认 cache（`from django.core.cache import cache`）。
多 worker 后每个 worker 各有独立的 LocMemCache 实例。

**影响评估**：
- **功能**：正确。缓存 miss 时 worker 从 DB 读取最新数据，结果正确。
- **一致性**：各 worker 缓存内容可能轻微不一致（各自 TTL 独立计时），但看板接口
  的 30s TTL 本身就允许此范围的数据延迟。不影响用户体验。
- **命中率**：多 worker 下每个 worker 初期缓存为空，命中率略低于单 worker（首次
  请求各 worker 各自打 DB 一次）。但稳态时（同一 worker 重复收到同类请求）命中率
  与单 worker 相同。
- **内存**：每 worker 各自维护最多若干条缓存，总量极小（看板 key 不超过 20 个，
  每条数据 <10KB）。

**为何不切 Redis 缓存**：
1. 引入 django-redis 增加维护复杂度（生产多一个故障点：Redis 宕机影响 HTTP 响应，
   而非只影响 WS）。
2. 看板数据已有 30s TTL 容忍度，per-worker 缓存功能完全满足需求。
3. 省略 django-redis 依赖，requirements.txt 改动最小，ARM pip 安装风险最低。
4. fault_utils.py 已有 TODO(AB-001) 注明"多进程或跨进程共享缓存需求时再迁移 Redis"，
   本次 2 worker 规模未触发该条件。

**结论**：接受 per-worker LocMemCache，不引入 django-redis。

---

### ADR-P1A-004：`_activity_cache` 多 worker 行为 — 功能正确，文档注明退化

**决策**：无需改代码。在文档中注明节流退化行为。

**分析**（`api/authentication.py` 中的 `_activity_cache`）：

`_activity_cache` 是模块级 `dict`，用于节流"每次请求写 DB 更新 last_active_at"。
单 worker 时同一 token 的所有请求在同一进程内，节流字典全局有效。

多 worker 时（2 个进程）：
- **超时判定**：基于 `TokenActivity.last_active_at`（MySQL），不基于进程内缓存。
  两个 worker 读的是同一张表，超时判定**完全正确**。
- **节流退化**：同一 token 的请求分散到两个 worker，每个 worker 各自有独立的
  `_activity_cache`。最坏情况：worker-A 5 分钟内节流 1 次，worker-B 也 5 分钟内
  节流 1 次，即同一 token 在 5 分钟窗口内 DB UPDATE 从 1 次变为最多 2 次（总计
  2 workers × 1 次/300s = 2 次/300s）。
- **实际影响**：每 5 分钟多 1 次极轻量的 MySQL UPDATE（单行更新），在 Pi 5 + 内网
  MySQL 上可忽略。v0.9.0 会话超时功能行为**完全正确**。
- **结论**：接受节流效率略降（最多 N-worker 倍 DB write，N=2 即 2x），功能正确性
  不受影响。

---

### ADR-P1A-005：utils_room_filter._room_filter_cache 多 worker 行为

**分析**（`api/utils_room_filter.py` 中的 `_room_filter_cache`）：

这是进程内 Python dict，缓存"允许的房间/参数类型"查询结果，与 `cache_dashboard`
使用不同的实现（原生 dict，非 Django cache）。

多 worker 后各 worker 各自维护一份。`invalidate_room_filter_cache()` 只清空本
进程内的 dict。如果有缓存失效场景（如配置更新），需要触发所有 worker 的缓存失效。

**本期结论**：该缓存的失效依赖是 DeviceConfig 更新，属于极低频操作（手动配置），
且 TTL 容忍度未定义（实际上 worker 重启即失效）。接受"各 worker 各自失效"的行为，
与 LocMemCache 分析结论相同。不需要额外处理。

---

### ADR-P1A-006：mqtt_handlers._conn_status_cache 等进程内 dict

**分析**：

`mqtt_handlers.py` / `device_name_cache.py` / `fault_consumer` / `screen_heartbeat_consumer`
等多个后台服务有进程内 dict 缓存（`_conn_status_cache`, `_cache` 等）。

**关键**：这些服务以 `management command` 方式启动（独立 systemd 服务进程），
**不是 uvicorn worker 的代码**。uvicorn 多 worker 不影响它们——它们各自是单独进程，
行为与当前完全一致。

**结论**：无需任何改动，不受 P1-a 影响。

---

### ADR-P1A-007：Redis 服务部署方式 — apt redis-server，systemd 开机自启

**决策**：`sudo apt install redis-server`，配置 `bind 127.0.0.1`，
`sudo systemctl enable redis-server`。

**理由**：生产禁止 Docker（C-03）。apt 包在 Debian trixie / aarch64 上可直接安装。
Redis 绑 loopback，不对外暴露（安全）。

**Redis 配置要点**（/etc/redis/redis.conf 默认值确认）：
- `bind 127.0.0.1` —— 默认已是 loopback，确认即可
- `maxmemory` —— 建议显式设为 128mb，防止在 4GB Pi 上意外耗尽（Channel Layer
  的 channel 数据量极小，chatconsumer 长连接无 group broadcast）
- `maxmemory-policy allkeys-lru` —— Channel Layer 数据是短暂的，LRU 逐出安全

---

### ADR-P1A-008：新增 Python 依赖 — channels_redis

**决策**：requirements.txt 添加 `channels_redis>=4.1.0`（无上限约束）。

**分析**：
- channels_redis 4.x 对应 channels 4.x（当前已用 `channels>=4.0.0`）。
- channels_redis 依赖 `redis` Python 客户端（`redis>=4.0.0`）。
- `redis` 包在 ARM64 上为纯 Python 包（无 C 扩展），安装 100% 可靠。
- `hiredis`（C 加速客户端）是可选依赖，channels_redis 会在 import 时自动检测，
  不可用时自动降级到纯 Python redis 客户端——ARM64 上若 hiredis wheel 不可用
  不会报错。因此**不**在 requirements.txt 单独列 hiredis，由 channels_redis 自动处理。
- 不加任何版本上限，不影响 paho-mqtt / aiohttp 等现有包。

---

## 4. 总体影响矩阵

| 组件 | 多 worker 后行为 | 功能正确？ | 需要改动？ |
|------|-----------------|-----------|-----------|
| ChatConsumer（/ws/chat/）| 每连接独占 worker，Channel Layer 改 Redis | 是 | 仅 settings.py |
| cache_dashboard（看板 LocMemCache）| per-worker 各自缓存，命中率略降 | 是 | 无（文档注明）|
| fault_utils 故障数缓存（LocMemCache）| per-worker 各自缓存 | 是 | 无（文档注明）|
| SlidingWindowTokenAuthentication._activity_cache | 节流 N-worker 倍 DB write，超时判定基于 DB | 是 | 无（文档注明）|
| utils_room_filter._room_filter_cache | per-worker，低频失效场景各自失效 | 是 | 无 |
| mqtt_handlers / fault_consumer 等后台服务 | 独立进程，不受 uvicorn worker 数影响 | 是 | 无 |

---

## 5. 回滚方案

若 Redis 服务异常或 channels_redis 引入问题，可在 5 分钟内回滚：

**回滚步骤**（生产）：
1. `sudo systemctl edit --force freeark-backend` 或直接编辑 unit 文件，
   将 `--workers 2` 改回 `--workers 1`。
2. 在 `settings.py` 将 `CHANNEL_LAYERS` 改回 `InMemoryChannelLayer`（或通过
   `.env` + settings 环境变量分支切换，见 §6）。
3. `sudo systemctl daemon-reload && sudo systemctl restart freeark-backend`。
4. Redis 服务可留运行（无害），或 `sudo systemctl stop redis-server`。

**回滚后状态**：与 P0 commit c84eb12 完全一致，功能无任何退化。

---

## 6. 实现清单

| 文件 | 改动内容 |
|------|----------|
| `FreeArkWeb/backend/requirements.txt` | 添加 `channels_redis>=4.1.0` |
| `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | CHANNEL_LAYERS 改 RedisChannelLayer；CACHES 注释更新 |
| `systemctl/freeark-backend.service` | `--workers 1` 改 `--workers 2` |
| `.claude/skills/freeark-prod-deploy/SKILL.md` | §3/§4/§4.1/§9.1 更新 |
| `docs/architecture/architecture_design_p1a_redis_channel_layer.md` | 本文件（ADR）|

---

## 7. 验证清单

| 项 | 验证方式 |
|----|---------|
| 本地测试套件全部通过 | `python manage.py test`（SQLite，DummyCache 分支）|
| channels_redis import 正常 | `python -c "from channels_redis.core import RedisChannelLayer"` |
| WebSocket 聊天在多 worker 下正确 | 本地 Redis + `uvicorn --workers 2` + wscat 手动测试 |
| 看板接口缓存仍工作 | 测试套件 test_fault_count 通过（DummyCache 分支）|
| 会话超时仍正确 | test_session_timeout 用例通过 |
| 生产部署后健康检查 | `curl http://127.0.0.1:8080/api/health/` |
| 生产 WS 聊天 | 按 SKILL.md §11 排查清单执行 |
