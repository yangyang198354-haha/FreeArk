# v0.5.2 架构设计文档

```
file_header:
  document_id: ARCH-V052-WAITRESS-DB-TUNING-001
  title: waitress 线程数与数据库连接调优 — 架构设计
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: 1.0
  created_at: 2026-05-20
  status: DRAFT
  references:
    - docs/requirements/v0.5.2_waitress_db_tuning/requirements_spec.md
    - docs/requirements/v0.5.2_waitress_db_tuning/user_stories.md
    - sdlc/perf_analysis_report.md (APPROVED)
    - FreeArkWeb/backend/freearkweb/start_waitress_server.py
    - FreeArkWeb/backend/freearkweb/freearkweb/settings.py
```

---

## 1. 架构决策摘要

v0.5.2 不引入新服务、不变更 DB Schema、不新增 Python 依赖包。所有变更局限于 `start_waitress_server.py` 的启动参数配置，`settings.py` 无需代码修改（CONN_MAX_AGE=300 保持原值）。

---

## 2. 架构决策记录（ADR）

### ADR-01：waitress threads 设置为 16，通过环境变量参数化

**问题**：`start_waitress_server.py` 当前使用 waitress 默认 4 线程，7 个并发看板请求导致排队超时。

**备选方案对比**：

| 方案 | 描述 | 优点 | 缺点 |
|------|------|------|------|
| A：硬编码 threads=16 | 直接写 `serve(..., threads=16)` | 最简单，1 行改动 | 调整需修改代码 |
| B：环境变量参数化（推荐） | `int(os.environ.get('WAITRESS_THREADS', '16'))` | 运维可调，符合 12-factor 原则 | 稍复杂（3 行代码） |
| C：配置文件（waitress.ini） | 使用 waitress-serve CLI + ini 文件 | 配置集中 | 需改变启动方式，与现有 systemd unit 不兼容 |

**决策**：采用方案 B（环境变量参数化）。

**理由**：
- FreeArk 已使用 `python-dotenv` 加载 `.env`（settings.py L17-20），基础设施已就绪。
- 运维人员可在 systemd service 的 `Environment=` 指令中设置，无需 SSH 进去修改代码。
- 回退只需删除环境变量并重启，操作时间 < 30s。
- threads=16 的选择依据：树莓派4B 4核，waitress 官方建议 I/O 密集型场景 `threads = 4~8 × CPU核心数`；看板 API 均为 DB I/O 等待，16 线程（= 4 × CPU核心数）在 I/O 密集型场景下合适，且 16 远低于 MySQL max_connections（151），安全边界充裕。

---

### ADR-02：channel_timeout 设置为 120s，通过环境变量参数化

**问题**：`dashboard_services` 端点在 Linux 上串行调用 9 次 `systemctl`，极端情况下可超过 5s（单个 subprocess timeout 上限），存在线程被长期占用风险。

**备选方案对比**：

| 方案 | timeout 值 | 说明 |
|------|-----------|------|
| A：60s | 与浏览器底层超时对齐 | 若请求本身 59s 完成仍被截断，用户体验差 |
| B：120s（推荐） | 2 倍浏览器超时 | 给所有合理慢请求充足时间，同时防止线程永久阻塞 |
| C：30s | 积极超时 | 可能截断 dashboard_services 在极端场景下的合理请求 |

**决策**：采用方案 B（120s），通过环境变量 `WAITRESS_CHANNEL_TIMEOUT` 覆盖。

**理由**：`dashboard_services` 最坏耗时约 900ms（9 × 100ms D-Bus），即使有 2~3 次卡顿也不超过 15s，120s 绝对安全。同时 120s = waitress 原始默认值，此处仅是显式化（让参数可见可管理），不引入新行为。

---

### ADR-03：connection_limit 设置为 100，通过环境变量参数化

**问题**：16 线程后，若遭遇异常并发（如爬虫、前端 bug 导致请求风暴），waitress 可能积压大量未被处理的 HTTP 连接，消耗内存。

**决策**：显式设置 `connection_limit=100`（waitress 原始默认值为 `100`，此处显式化）。

**理由**：正常使用场景（< 10 并发用户 × 7 请求/页 = < 70 连接）不触及上限。异常情况下保护服务器内存。

---

### ADR-04：CONN_MAX_AGE 保持 300s，不修改 settings.py

**问题**：线程数增加后，持久连接数从 4 增加到 16，需评估 MySQL 连接容量是否安全。

**容量计算**（见第 4 节），结论为安全。

**决策**：保持 `CONN_MAX_AGE=300` 不变，不修改 `settings.py`。

**理由**：
- Django 在 waitress 多线程模型中每个线程持有自己的 DB 连接对象（线程本地存储）。CONN_MAX_AGE=300 确保同一线程在 5 分钟内复用连接，避免每次请求重新握手（减少连接建立开销）。
- 线程数增加到 16 后，最大持久连接数 = 16。见第 4 节容量计算，16 << 151（MySQL max_connections），安全余量充裕。
- 当前 settings.py 已有 `connect_timeout=60`、`read_timeout=60`、`write_timeout=60`（L125-128），已覆盖常见超时场景，无需额外配置。

---

### ADR-05：不添加 MySQL `reconnect: True` 选项

**问题**：Q-001：是否在 OPTIONS 中加入 `'reconnect': True`？

**备选方案对比**：

| 方案 | 描述 | 风险 |
|------|------|------|
| A：不加 reconnect（推荐） | 依赖 Django 内置的连接有效性检测与重建机制 | Django 在 CONN_MAX_AGE > 0 时，若连接失效（`OperationalError: (2006, 'MySQL server has gone away')`），会在下一次请求时自动创建新连接；代价是该次请求的第一个查询失败，但 Django 会在同一请求内重试（通过 `close_old_connections()` 机制） |
| B：加 reconnect=True | MySQL Connector/Python 的 reconnect 选项（mysqlclient 可能不支持） | 与 Django 的连接管理层产生冲突（Django 本身已管理重连，双重重连逻辑可能导致不一致行为）；mysqlclient（FreeArk 使用的 MySQL 适配器）的 `reconnect` 选项在 Django 中已被官方文档明确建议**不要使用**（会绕过 Django 的连接管理，导致事务状态丢失） |

**决策**：不加 `reconnect: True`（选方案 A）。

**理由**：
- Django 官方文档在 ["Persistent connections" 章节](https://docs.djangoproject.com/en/5.2/ref/databases/#persistent-connections) 明确说明：若 `CONN_MAX_AGE > 0`，Django 在发现连接断开时会自动重建。
- mysqlclient 的 `reconnect=1` 会静默重连并丢弃当前事务状态，在 Django ORM 事务管理下是危险行为。
- FreeArk 看板 API 均为无事务的只读查询，即使发生 1 次重连失败（用户刷新看板返回 500），用户重试刷新即可恢复。概率低（MySQL 服务器 wait_timeout=28800s，持久连接 300s 远低于此值）。

**Q-003 回答**（MySQL max_connections 确认）：见第 4 节，以 151（默认值）为基准进行容量计算，用户可通过 `SHOW VARIABLES LIKE 'max_connections';` 在生产环境确认实际值。

---

### ADR-06：环境变量注入方式采用 systemd service `Environment=` 指令

**问题**：Q-002：WAITRESS_THREADS 通过 `.env` 文件还是 systemd service `Environment=` 指令注入？

**备选方案对比**：

| 方案 | 描述 | 适合场景 |
|------|------|---------|
| A：.env 文件（python-dotenv） | `start_waitress_server.py` 启动时 `load_dotenv()` 读取 `.env` | 开发环境便捷 |
| B：systemd service `Environment=` 指令（推荐） | 在 `/etc/systemd/system/freeark-backend.service` 中加 `Environment=WAITRESS_THREADS=16` | 生产环境标准做法 |
| C：两者结合（推荐 + 兜底） | systemd `Environment=` 优先；`.env` 文件作为开发环境兜底 | 开发/生产双覆盖 |

**决策**：采用方案 C（两者结合）。

**理由**：
- 生产环境 systemd `Environment=` 指令不需要文件系统上存在 `.env` 文件，更安全（凭证不落盘）。
- `start_waitress_server.py` 已调用 `load_dotenv()`（L18），`.env` 文件在开发机上可覆盖参数，开发者无需修改代码。
- 环境变量优先级：systemd `Environment=` > `.env` 文件（`load_dotenv` 不覆盖已存在的环境变量，即 `load_dotenv(override=False)`，这是 python-dotenv 默认行为）。

---

## 3. 受影响文件清单

| 层次 | 文件 | 变更类型 | 变更内容摘要 |
|------|------|---------|------------|
| 服务启动 | `FreeArkWeb/backend/freearkweb/start_waitress_server.py` | **修改**（约 5 行） | 从环境变量读取 threads、channel_timeout、connection_limit，传入 `serve()` |
| 基础设施（可选） | `/etc/systemd/system/freeark-backend.service` | **修改**（追加 Environment 行） | 注入 `WAITRESS_THREADS=16` 等环境变量 |
| 数据库配置 | `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | **无变更** | CONN_MAX_AGE=300 保持不变，无需修改 |
| 文档 | `docs/requirements/v0.5.2_waitress_db_tuning/` | **新增** | requirements_spec.md、user_stories.md、architecture_design.md、module_design.md |

**注意**：`freeark-backend.service` 文件在树莓派生产机上，需要通过 SSH 执行修改（或在 module_design.md 中提供 systemd unit 片段由运维人员手动添加）。本次 SDLC 仅产出文档，不执行实际修改。

---

## 4. 线程数与 MySQL 连接数容量计算

### 4.1 连接占用来源清单

| 来源 | 连接数估算 | 说明 |
|------|-----------|------|
| waitress freeark-backend（16线程） | 最多 16 | CONN_MAX_AGE=300，每线程 1 连接 |
| freeark-mqtt-consumer（MQTT 消费者） | 1~2 | 独立进程，少量写入连接 |
| freeark-daily-usage（日用量计算定时任务） | 1 | 运行时极短暂，通常为 0 |
| freeark-monthly-usage（月用量计算） | 1 | 同上 |
| freeark-plc-cleanup / freeark-dph-cleanup | 1 | 同上 |
| freeark-task-scheduler | 1~2 | 调度器持有少量连接 |
| MySQL 内部系统连接 | 3~5 | performance_schema、information_schema 等 |
| **合计（估算）** | **25~28** | 远小于 MySQL max_connections = 151 |

### 4.2 安全边界分析

```
安全公式：总连接数 < max_connections × 安全因子（0.8）

max_connections（默认）= 151
安全上限（80%）= 151 × 0.8 = 121

当前估算总连接数 = 25~28
安全余量 = 121 - 28 = 93 个连接余量
安全因子 = 28 / 151 = 18.5%（极低占用）
```

**结论**：16 线程配置下，MySQL 连接数占用远低于安全阈值，不存在连接耗尽风险。

### 4.3 CONN_MAX_AGE 与连接时效分析

```
CONN_MAX_AGE = 300s（5分钟）
MySQL wait_timeout（默认）= 28800s（8小时）
MySQL interactive_timeout（默认）= 28800s

Django 持久连接存活 300s，远小于 MySQL 服务端 8 小时断连时限。
正常情况下，Django 主动在 300s 后关闭连接并在下次请求重新建立，
不会因 MySQL 服务端断开（wait_timeout）触发 "Lost Connection" 错误。

"Lost Connection" 的实际风险场景：
- 网络设备（NAT/防火墙）的 TCP 空闲超时（通常 5~30 分钟）
- MySQL 服务器重启
- 网络故障后恢复

在上述场景下，Django 的重连机制（CONN_MAX_AGE 到期后自动重建）已足够覆盖，
无需额外的 reconnect=True 选项（ADR-05 理由）。
```

---

## 5. waitress 参数技术规格

| 参数 | 环境变量 | 代码默认值 | waitress 原始默认值 | 说明 |
|------|---------|-----------|------------------|------|
| `threads` | `WAITRESS_THREADS` | `16` | `4` | 工作线程数。I/O 密集型应用建议 4~8 × CPU核心数；4核 RPi4B 取 16 |
| `channel_timeout` | `WAITRESS_CHANNEL_TIMEOUT` | `120` | `120` | 单连接最大处理时间（秒）。此处显式化，行为与原始默认一致 |
| `connection_limit` | `WAITRESS_CONNECTION_LIMIT` | `100` | `100` | 最大并发 HTTP 连接数。此处显式化，行为与原始默认一致 |

**关键参数解释**：
- `threads`：waitress 使用预分配线程池（固定大小），每个线程同时处理 1 个 HTTP 请求。线程数越多，可同时处理的请求越多，但内存消耗也线性增加（每线程约 1~2MB 栈内存）。
- `channel_timeout`：单个 HTTP 连接（channel）从建立到完成的最大允许时间。超时后 waitress 强制关闭连接，线程回到池中。**注意**：这是连接级别超时，不是请求处理级别，已经开始处理的请求不会被中途截断（waitress 1.4.x+ 行为）。
- `connection_limit`：waitress 维持的最大同时活跃连接数（含正在处理和队列中等待的连接）。

---

## 6. "Lost Connection" 处理策略

### 6.1 风险评估

在 16 线程 + CONN_MAX_AGE=300s 配置下，"Lost Connection" 的风险来源：

| 风险场景 | 概率 | 影响 | 缓解 |
|---------|------|------|------|
| NAT/防火墙 TCP 空闲超时（< 5min）断开持久连接 | 低（`CONN_MAX_AGE=300s`，连接 5min 后主动关闭，不会空闲太久） | 该次请求第一个查询失败 | Django 自动重连，下一请求正常 |
| MySQL 服务器 wait_timeout 断开（8小时） | 极低（Django 主动在 300s 内关闭连接） | 同上 | 同上 |
| MySQL 服务器重启 | 罕见 | 所有持久连接失效，下次请求全部触发重连 | Django 自动重连，1 次失败后恢复 |

### 6.2 Django 内置重连机制说明

Django 5.2 在 `CONN_MAX_AGE > 0` 时的连接管理流程（`django.db.backends.base.base.py`）：

```
请求进入 → Django 检查当前线程的持久连接是否有效（执行轻量 ping 或使用可关闭标志）
         → 若无效（OperationalError 2006/2013）→ 关闭旧连接 → 创建新连接 → 执行查询
         → 若有效 → 直接复用连接执行查询
```

在 waitress 多线程模型下，每个线程有独立的数据库连接（Django 使用 `threading.local()` 存储连接），一个线程的连接断开不影响其他线程。

### 6.3 与 git 历史中 "Lost Connection" 的关联

commit `c09f41e`（`fix(db-perf): dph_cleanup dry-run 避免重查询触发 Lost connection`）指向的问题是 `dph_cleanup` 管理命令在 dry-run 模式下**批量重查询**导致的长事务/大结果集场景，与看板 API 的短查询不同。该问题已在 v0.5.2 scope 之前通过 `dph_cleanup` 代码修复（commit c09f41e），不需要本次迭代额外处理。

---

## 7. 回滚方案

### 7.1 代码级回滚

如果 v0.5.2 变更（`start_waitress_server.py`）引入问题：

```bash
# 方案1：git 回滚（推荐，30秒内完成）
git revert HEAD  # 或 git checkout <上一commit> -- start_waitress_server.py
sudo systemctl restart freeark-backend

# 方案2：临时通过环境变量恢复 4 线程
# 在 /etc/systemd/system/freeark-backend.service 中修改：
# Environment=WAITRESS_THREADS=4
sudo systemctl daemon-reload
sudo systemctl restart freeark-backend
```

### 7.2 回滚判断标准

如果重启后出现以下任一情况，立即执行回滚：

- `sudo systemctl status freeark-backend` 显示 `Active: failed`
- 看板所有面板返回 502/503
- MySQL `Threads_connected` 突破 80（`SHOW STATUS LIKE 'Threads_connected';`）

### 7.3 回滚后验证

```bash
# 验证服务恢复
curl -s http://192.168.31.51:8000/api/dashboard/summary/ -H "Authorization: Token <token>" | python3 -m json.tool
# 预期：返回 today_kwh、month_kwh 数据，HTTP 200
```

---

## 8. 生产部署注意事项（本阶段不执行）

> 本节记录给部署阶段参考，不在当前 v0.5.2 需求/设计阶段执行。

1. **修改时机**：选择低峰期（夜间或周末）执行，服务重启约需 5~10 秒不可用窗口。
2. **修改范围**：仅 `start_waitress_server.py`（代码改动约 5 行）；可选修改 `freeark-backend.service`（添加 `Environment=WAITRESS_THREADS=16`）。
3. **部署顺序**：git pull → 可选 systemd unit 修改 → `systemctl daemon-reload` → `systemctl restart freeark-backend` → 观察 5 分钟。
4. **部署后验证**：刷新看板，确认 7 个面板均正常显示数据；Chrome DevTools Network 确认无 TTFB 超长等待。
5. **不需要**：数据库迁移（`manage.py migrate`）、静态文件重新收集（`collectstatic` 已在启动脚本中执行）、前端重新构建。

---

*文档版本: 1.0 | 生成时间: 2026-05-20 | 状态: DRAFT（待门控评审）*
