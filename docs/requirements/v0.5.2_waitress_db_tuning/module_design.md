# v0.5.2 模块设计文档

```
file_header:
  document_id: MOD-V052-WAITRESS-DB-TUNING-001
  title: waitress 线程数与数据库连接调优 — 模块设计
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 能耗采集平台
  version: 1.0
  created_at: 2026-05-20
  status: DRAFT
  references:
    - docs/requirements/v0.5.2_waitress_db_tuning/architecture_design.md
    - FreeArkWeb/backend/freearkweb/start_waitress_server.py (当前内容)
    - FreeArkWeb/backend/freearkweb/freearkweb/settings.py (L131 CONN_MAX_AGE=300)
```

---

## 1. 受影响模块清单

| 模块编号 | 文件路径 | 变更类型 | 变更规模 |
|---------|---------|---------|---------|
| M1 | `FreeArkWeb/backend/freearkweb/start_waitress_server.py` | 修改 | 约 5 行新增，0 行删除 |
| M2（可选，运维执行） | `/etc/systemd/system/freeark-backend.service` | 修改 | 追加 1~3 行 `Environment=` |
| M3（无变更） | `FreeArkWeb/backend/freearkweb/freearkweb/settings.py` | 无变更 | 0 行 |

---

## 2. M1：start_waitress_server.py — 变更详情

### 2.1 变更位置

文件：`FreeArkWeb/backend/freearkweb/start_waitress_server.py`

当前代码（L82）：
```python
serve(application, host='0.0.0.0', port=8000)
```

目标代码（替换 L82）：
```python
# 从环境变量读取 waitress 运行时参数（支持运维不改代码调整）
_threads = int(os.environ.get('WAITRESS_THREADS', '16'))
_channel_timeout = int(os.environ.get('WAITRESS_CHANNEL_TIMEOUT', '120'))
_connection_limit = int(os.environ.get('WAITRESS_CONNECTION_LIMIT', '100'))

print(f"Waitress 启动参数: threads={_threads}, channel_timeout={_channel_timeout}s, connection_limit={_connection_limit}")

serve(
    application,
    host='0.0.0.0',
    port=8000,
    threads=_threads,
    channel_timeout=_channel_timeout,
    connection_limit=_connection_limit,
)
```

### 2.2 变更说明

| 变更项 | 旧值 | 新值 | 来源 |
|--------|------|------|------|
| `threads` 参数 | 未传（waitress 默认 4） | 环境变量 `WAITRESS_THREADS`，默认 16 | ADR-01 |
| `channel_timeout` 参数 | 未传（waitress 默认 120） | 环境变量 `WAITRESS_CHANNEL_TIMEOUT`，默认 120 | ADR-02（显式化，无行为变更） |
| `connection_limit` 参数 | 未传（waitress 默认 100） | 环境变量 `WAITRESS_CONNECTION_LIMIT`，默认 100 | ADR-03（显式化，无行为变更） |
| 启动日志 | 无参数打印 | 打印实际运行参数（便于运维确认） | 可观测性 |

### 2.3 依赖项确认

- `os` 模块：已在文件头部导入（L9）。
- `waitress.serve`：已在文件中导入（L76）。
- 无新增 import，无新增依赖包。

### 2.4 参数值域校验

| 参数 | 合法值域 | 异常处理 |
|------|---------|---------|
| `WAITRESS_THREADS` | 正整数（建议 4~64） | 若环境变量非数字，`int()` 抛出 `ValueError`，服务启动失败；运维需检查配置 |
| `WAITRESS_CHANNEL_TIMEOUT` | 正整数（建议 30~300） | 同上 |
| `WAITRESS_CONNECTION_LIMIT` | 正整数（建议 50~500） | 同上 |

> 注：不加额外的 try/except 对 int() 进行容错——若环境变量配置错误（如 `WAITRESS_THREADS=abc`），服务应快速失败（fail-fast），便于运维立即发现配置问题，而不是静默回退到错误值。

---

## 3. M2（可选）：freeark-backend.service — 变更片段

运维人员在树莓派上通过 SSH 执行以下操作（**本阶段不执行，仅提供参考**）：

```bash
sudo systemctl edit freeark-backend
```

在弹出的 override.conf 文件中追加以下内容（推荐使用 override 而不是直接编辑 unit 文件，便于回滚）：

```ini
[Service]
Environment=WAITRESS_THREADS=16
Environment=WAITRESS_CHANNEL_TIMEOUT=120
Environment=WAITRESS_CONNECTION_LIMIT=100
```

保存后执行：

```bash
sudo systemctl daemon-reload
sudo systemctl restart freeark-backend
sudo systemctl status freeark-backend
```

验证命令（确认线程数参数已在启动日志中打印）：

```bash
sudo journalctl -u freeark-backend -n 20 --no-pager
# 预期输出中包含：
# Waitress 启动参数: threads=16, channel_timeout=120s, connection_limit=100
```

**不使用 systemd override 的替代方案**：

若不修改 systemd unit，可在项目根目录的 `.env` 文件中添加以下行（仅在服务以 `python start_waitress_server.py` 方式启动时生效，对 systemd 管理的服务需要 unit 文件中的 `EnvironmentFile=` 支持）：

```dotenv
WAITRESS_THREADS=16
WAITRESS_CHANNEL_TIMEOUT=120
WAITRESS_CONNECTION_LIMIT=100
```

**推荐顺序**：优先使用 systemd override（更标准，不依赖 .env 文件权限）；开发环境使用 .env 文件。

---

## 4. M3：settings.py — 无变更确认

以下配置已存在，无需修改：

```python
# settings.py L114-131（当前代码，确认保持不变）
MYSQL_DATABASE = {
    'ENGINE': 'django.db.backends.mysql',
    ...
    'OPTIONS': {
        'charset': 'utf8mb4',
        'use_unicode': True,
        'connect_timeout': 60,   # ✓ 已存在，无需修改
        'read_timeout': 60,      # ✓ 已存在，无需修改
        'write_timeout': 60,     # ✓ 已存在，无需修改
        'autocommit': True,      # ✓ 已存在，无需修改
        # 注意：不添加 'reconnect': True（见 ADR-05）
    },
    'CONN_MAX_AGE': 300,         # ✓ 已存在，无需修改
}
```

---

## 5. 测试设计指引（供后续 test_engineer 参考）

> 本节仅提供测试方向，不是本阶段的产出。测试阶段将由 test_engineer 编写完整测试计划。

### 5.1 单元测试方向

| 测试编号 | 测试内容 | 验证方式 |
|---------|---------|---------|
| UT-V052-01 | 环境变量 `WAITRESS_THREADS=8` 时，start_waitress_server.py 读取正确 | 单元测试 mock `os.environ.get`，断言传入 `serve()` 的 `threads=8` |
| UT-V052-02 | 未设置环境变量时，`threads` 默认为 16 | 单元测试清除环境变量，断言传入 `serve()` 的 `threads=16` |
| UT-V052-03 | 环境变量为非数字时，`int()` 抛出 `ValueError` | 断言服务启动失败（异常传播，不静默忽略） |

### 5.2 集成/性能测试方向

| 测试编号 | 测试内容 | 验证方式 |
|---------|---------|---------|
| IT-V052-01 | 7 个并发请求全部在 5s 内返回 | 参考 perf_test_plan.md PT-008，threads=16 对比 threads=4 |
| IT-V052-02 | `SHOW STATUS LIKE 'Threads_connected';` 显示 ≤ 30 | MySQL 客户端执行，人工验证 |
| IT-V052-03 | waitress 启动日志包含正确参数 | `journalctl -u freeark-backend -n 20` 输出验证 |

---

## 6. 变更影响面分析

| 影响面 | 影响 | 风险等级 |
|--------|------|---------|
| 功能影响 | 无（waitress 参数变化不影响 Django 视图逻辑） | 无 |
| 数据影响 | 无（不修改任何数据库 Schema 或数据） | 无 |
| API 兼容性 | 无（对外 API 接口不变） | 无 |
| 前端影响 | 无（前端代码无需修改） | 无 |
| 内存影响 | 线程从 4 增至 16，内存增加约 24MB（12 个额外线程 × 2MB）；RPi4B 4GB 内存充裕 | 极低 |
| MySQL 连接数 | 从 4 增至 16，总连接数约 25~28，远低于 max_connections=151 | 极低 |
| 服务可用性 | 仅需重启 `freeark-backend`（约 5~10s 不可用） | 低（计划停机） |

---

*文档版本: 1.0 | 生成时间: 2026-05-20 | 状态: DRAFT（待门控评审）*
