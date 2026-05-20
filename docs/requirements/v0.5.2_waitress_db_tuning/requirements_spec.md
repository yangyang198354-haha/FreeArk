# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-V052-WAITRESS-DB-TUNING-001
  title: waitress 线程数与数据库连接调优 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: 1.0
  created_at: 2026-05-20
  status: DRAFT
  references:
    - sdlc/perf_analysis_report.md (APPROVED)
    - sdlc/perf_test_report.md (APPROVED)
    - FreeArkWeb/backend/freearkweb/start_waitress_server.py (L82)
    - FreeArkWeb/backend/freearkweb/freearkweb/settings.py (L114-131)
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 1.0 | 2026-05-20 | 初始版本，基于 perf_analysis_report.md FIX-01 诊断结论 |

---

## 1. 背景与动因

### 1.1 问题根因（来源：perf_analysis_report.md）

FreeArk 看板首页（`HomeView.vue`）在 `onMounted` 阶段同时触发 7 个 dashboard API 请求。当前 waitress WSGI 服务器以默认参数启动（`start_waitress_server.py` L82：`serve(application, host='0.0.0.0', port=8000)` 未传任何参数），线程池大小为 waitress 默认值 **4 线程**。

7 个并发请求中，`/api/dashboard/services/` 端点在 Linux 生产环境中因串行 `subprocess.run(['systemctl', 'is-active', ...])`（9 次循环）耗时约 500~900ms，持续占用 1 个线程。其余请求的数据库聚合查询耗时约 50~500ms 不等。

**后果**：线程池被占满，后续请求在队列中等待，直至浏览器底层 TCP 连接超时（约 60s），`fetch()` 抛出 `TypeError: Failed to fetch`，前端 catch 块静默归零。用户观察到「面板转圈很久后显示 0」。

### 1.2 本次迭代范围

本次迭代（v0.5.2）仅实施 **FIX-01：waitress 线程数与数据库连接调优**，对应 perf_analysis_report.md 优先级 P1。

FIX-02（前端超时）、FIX-03（services 并发）、FIX-04（缓存）**不在本次范围**，留作后续迭代，已在第 5 节明确标注。

---

## 2. 利益相关者

| 角色 | 关切 |
|------|------|
| 运维人员（主要用户） | 看板面板不再归零；多用户同时刷新不卡顿 |
| 系统管理员 | 参数可配置，生产变更低风险可回滚 |
| 开发者 | 配置改动最小化，不引入新依赖 |

---

## 3. 功能性需求

### REQ-FUNC-001：waitress 线程数可配置

**来源**：perf_analysis_report.md §2.1 + perf_test_report.md FIX-01

`start_waitress_server.py` 中调用 `serve()` 时必须传入 `threads` 参数，支持通过以下方式（优先级从高到低）配置：

1. 环境变量 `WAITRESS_THREADS`（允许运维人员在不修改代码的情况下调整）
2. 代码默认值 `16`

**验收标准**：
- AC-FUNC-001-01：`WAITRESS_THREADS=16` 时，waitress 启动日志中线程数为 16。
- AC-FUNC-001-02：未设置 `WAITRESS_THREADS` 时，线程数回落到代码默认值 16。
- AC-FUNC-001-03：7 个并发请求全部立即获得线程，无排队等待（可通过看板刷新 + Chrome DevTools Network Timing 验证）。

---

### REQ-FUNC-002：waitress channel_timeout 可配置

**来源**：perf_analysis_report.md §2.1（"若占用线程的请求中有慢请求"场景）

`serve()` 调用传入 `channel_timeout` 参数，设定单个请求在线程上允许处理的最长时间（超时后 waitress 强制关闭连接并回收线程），支持通过以下方式配置：

1. 环境变量 `WAITRESS_CHANNEL_TIMEOUT`
2. 代码默认值 `120`（秒）

**验收标准**：
- AC-FUNC-002-01：`WAITRESS_CHANNEL_TIMEOUT=120` 时，单个超时请求在 120s 后连接被关闭，线程被回收，不永久阻塞线程池。
- AC-FUNC-002-02：正常请求（< 10s）不受 channel_timeout 影响，正常返回响应。

---

### REQ-FUNC-003：waitress connection_limit 可配置

**来源**：perf_analysis_report.md §2.1（容量安全边界考量）

`serve()` 调用传入 `connection_limit` 参数，限制 waitress 同时维持的最大 HTTP 连接数（避免线程数提升后因大量慢连接积压消耗内存），支持通过以下方式配置：

1. 环境变量 `WAITRESS_CONNECTION_LIMIT`
2. 代码默认值 `100`

**验收标准**：
- AC-FUNC-003-01：超过 `connection_limit` 的新连接被拒绝，已有连接不受影响。
- AC-FUNC-003-02：正常的看板使用场景（< 10 并发用户）不触及此上限。

---

### REQ-FUNC-004：数据库 CONN_MAX_AGE 配置核实与保持

**来源**：perf_analysis_report.md §2.1（CONN_MAX_AGE 在 waitress 多线程模型下的行为分析）

`settings.py` 中 `CONN_MAX_AGE=300` 已配置（L131），与 waitress 多线程模型兼容（每个线程在 5 分钟内复用连接，连接数等于线程数）。

**本需求要求**：
1. 确认 `CONN_MAX_AGE=300` 的配置保持不变（已有配置，无需新增代码）。
2. 在 architecture_design.md 中记录线程数与 MySQL 连接数的容量计算，确认 16 线程 → 最多 16 个 MySQL 连接 ≤ MySQL `max_connections`（默认 151）安全边界。

**验收标准**：
- AC-FUNC-004-01：设计文档中有明确的容量计算公式：`waitress_threads × 1 ≤ max_connections`，并给出 16 < 151 的安全余量结论。
- AC-FUNC-004-02：不需要对 `settings.py` 的 `CONN_MAX_AGE` 值做任何代码修改。

---

### REQ-FUNC-005：数据库连接健康检查策略

**来源**：git 提交历史中出现过的 "Lost connection" 错误（`fix(db-perf): dph_cleanup dry-run 避免重查询触发 Lost connection`，commit c09f41e）；perf_analysis_report.md §2.1（CONN_MAX_AGE 持久连接的风险）

当 `CONN_MAX_AGE > 0` 时（当前为 300s），持久连接在空闲期间可能被 MySQL 服务端断开（默认 `wait_timeout=28800s`，但网络设备的 NAT/防火墙超时通常更短）。Django 在下次使用该连接时会收到 `(2006, MySQL server has gone away)` 错误，触发重连，但在 waitress 多线程模型下，一个线程的连接断开不影响其他线程。

**本需求要求**：
1. 在 `settings.py` 的 `OPTIONS` 中确认 `connect_timeout` / `read_timeout` / `write_timeout` 已设置（已有配置：三项均为 60s，L125-128）。
2. 评估是否需要在 `OPTIONS` 中增加 `'reconnect': True`（MySQL Connector 的自动重连选项），由 system-architect 在设计阶段决策。
3. 如果设计决策为不加 `reconnect`，记录依赖 Django 默认重连机制的理由（Django 在 `CONN_MAX_AGE > 0` 时，若连接失效会自动在下次请求创建新连接）。

**验收标准**：
- AC-FUNC-005-01：architecture_design.md 中有对 `reconnect` 选项的明确决策记录（采用或不采用，含理由）。
- AC-FUNC-005-02：无论选择哪种策略，生产环境中 "Lost connection" 错误不应导致请求失败超过 1 次重试（即第一次失败后 Django 重连，第二次请求成功）。

---

## 4. 非功能性需求

### REQ-NFR-001：并发能力提升

**来源**：perf_analysis_report.md §2.1 排队分析

在 16 线程配置下，单用户看板（7 个并发请求）所有请求必须立即获得线程，无排队等待。在 2 个用户同时刷新（14 个并发请求）的场景下，仍有 2 个空闲线程，无阻塞。

| 场景 | 并发请求数 | 等待线程的请求数 |
|------|-----------|----------------|
| 当前（4线程，1用户） | 7 | 3（排队） |
| 目标（16线程，1用户） | 7 | 0 |
| 目标（16线程，2用户） | 14 | 0 |

---

### REQ-NFR-002：超时回收，线程不永久阻塞

**来源**：perf_analysis_report.md §2.1（"若占用线程的请求耗时较长"场景）

`channel_timeout=120s` 确保任何异常慢请求（如 `dashboard_services` 的 systemctl 卡死场景）在 120s 内强制回收线程，防止线程池耗尽。

---

### REQ-NFR-003：连接稳定性，不引入 Lost Connection 新风险

**来源**：git commit c09f41e，perf_analysis_report.md §2.1

线程数从 4 增加到 16 后，最多持有 16 个持久 MySQL 连接。所有连接在 `CONN_MAX_AGE=300s` 内有效，超时后 Django 自动重建。设计方案必须确保连接增加后不引入比当前 4 线程更高的 "Lost Connection" 风险。

---

### REQ-NFR-004：生产部署低风险，可回滚

**来源**：用户约束（"确认后再开发"流程）

所有变更必须满足：
1. 代码改动量极小（`start_waitress_server.py` 1~3 行，`settings.py` 0 行）。
2. 部署步骤仅需重启 `freeark-backend` 服务（`sudo systemctl restart freeark-backend`），无需停机。
3. 回滚方案：删除参数/恢复原始 `serve()` 调用后重启，影响 < 30 秒。

---

### REQ-NFR-005：不引入新依赖

waitress 配置参数均为 waitress 官方支持的原生参数（`threads`、`channel_timeout`、`connection_limit`），无需安装新 Python 包。MySQL 连接配置均为 Django 和 mysqlclient 原生支持的选项，无需引入连接池中间件（如 PgBouncer、sqlalchemy-pool 等）。

---

## 5. 范围外项目（Out of Scope）

以下项目明确**不在本次 v0.5.2 范围内**，留作后续迭代：

| 项目 | 原报告引用 | 留后原因 |
|------|----------|---------|
| FIX-02：前端 fetch() 增加 AbortController 15s 超时 | perf_test_report.md P1 FIX-02 | 独立前端改动，与服务端调优可分开迭代 |
| FIX-03：dashboard_services 改为并发 subprocess | perf_test_report.md P2 FIX-03 | 需额外评估 ThreadPoolExecutor 与 waitress 线程模型的交互 |
| FIX-04：看板 API 结果缓存（Django cache / Redis） | perf_test_report.md P2 FIX-04 | 依赖先完成线程调优，避免过度优化 |
| FIX-05：前端分批加载 | perf_test_report.md P3 FIX-05 | 需前端重构，中期规划 |
| FIX-06：innodb_buffer_pool_instances | perf_test_report.md P3 FIX-06 | 日常运维项，与本次需求无强依赖 |

---

## 6. 约束与假设

| 编号 | 类型 | 描述 |
|------|------|------|
| C-001 | 环境约束 | 生产环境：Raspberry Pi 4B，4 核，Linux，systemd；MySQL 8.x，`max_connections` 默认 151 |
| C-002 | 版本约束 | waitress 当前版本支持 `threads`、`channel_timeout`、`connection_limit` 参数（均为 v1.x+ 支持） |
| C-003 | 代码约束 | 不修改任何 Django 视图代码、模型代码、前端代码；仅修改 `start_waitress_server.py` |
| C-004 | 部署约束 | 不修改 `settings.py` 中已有的数据库连接配置，仅在设计文档中记录评估结论 |
| A-001 | 假设 | MySQL `max_connections` 为默认值 151（如实际不同，需在设计阶段确认） |
| A-002 | 假设 | 树莓派4B 内存充足，16 线程（每线程约 1~2MB 栈内存）不构成内存压力（总约 32MB） |

---

## 7. 开放问题

| 编号 | 问题 | 待决策方 | 优先级 |
|------|------|---------|--------|
| Q-001 | 是否在 `settings.py` OPTIONS 中加入 `'reconnect': True`？ | system-architect | P1 |
| Q-002 | `WAITRESS_THREADS` 是否写入 `.env` 文件（已有 python-dotenv 支持）还是作为 systemd service `Environment=` 指令？ | system-architect | P1 |
| Q-003 | 生产环境实际 MySQL `max_connections` 值是多少（可能已被 DBA 调整）？需用户执行 `SHOW VARIABLES LIKE 'max_connections';` 确认 | 用户/运维 | P2 |

---

*文档版本: 1.0 | 生成时间: 2026-05-20 | 状态: DRAFT（待门控评审）*
