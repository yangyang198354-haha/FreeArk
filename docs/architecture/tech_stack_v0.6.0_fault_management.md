# 技术栈说明

```
file_header:
  document_id: TECH-v0.6.0-FM
  title: MQTT 故障事件持久化 + 故障管理页面 — 技术栈
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 楼宇 PLC 数据采集平台
  version: v0.6.0-fault-management
  created_at: 2026-05-27
  status: DRAFT
  references:
    - docs/architecture/architecture_design_v0.6.0_fault_management.md
    - docs/architecture/module_design_v0.6.0_fault_management.md
    - FreeArkWeb/backend/requirements.txt
    - FreeArkWeb/frontend/src/router/index.js
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-27 | 初始草稿 |

---

## 1. 技术栈总览

**v0.6.0 不引入任何新的第三方库或基础设施组件。** 所有技术选型均沿用现有生产栈，新增功能通过现有工具的组合实现。

| 层次 | 技术 | 版本 | v0.6.0 变化 |
|------|------|------|------------|
| 运行平台 | 树莓派 192.168.31.51，物理机，无 Docker | — | 无变化 |
| 操作系统 | Linux（Raspberry Pi OS）| — | 无变化 |
| 服务管理 | systemd | — | 新增 2 个服务单元 + 1 个 timer（见下）|
| 后端语言 | Python 3.x | 同现有生产版本 | 无变化 |
| 后端框架 | Django | >=5.2.0（requirements.txt）| 无版本变更，新增 1 个 Model、2 个视图、1 个包 |
| REST API 框架 | Django REST Framework | 同现有生产版本 | 无版本变更，新增 1 个 Serializer、2 个 API 视图 |
| WSGI/ASGI 服务器 | uvicorn[standard] | >=0.29.0 | 无变化（freeark-backend 进程不变）|
| MQTT 客户端 | paho-mqtt | >=1.6.1（实际运行 2.1.0，兼容 1.x 风格 API）| 无版本变更，fault_consumer 复用相同版本 |
| 数据库（生产）| MySQL 9.4 @ 192.168.31.98:3306 | — | 新增 1 张表（fault_event），通过 Django migration 创建 |
| 数据库（测试）| SQLite | Django 内置 | 无变化，所有 migration 和测试 SQLite 兼容 |
| 调度库（清理服务）| systemd timer（OnCalendar）| — | 新增 timer 单元；不使用 Python schedule 库（fault_cleanup 是 one-shot 命令）|
| 前端框架 | Vue 3 + Vite | 同现有生产版本 | 无版本变更，新增 1 个 Vue 组件 |
| 前端 UI 组件库 | Element Plus | 同现有生产版本 | 无版本变更，新增日期范围选择器、多选下拉（均为 Element Plus 内置组件）|
| 前端 HTTP 客户端 | axios | 同现有生产版本 | 无变化 |
| 前端路由 | Vue Router | 同现有生产版本 | 追加 1 条路由 |

---

## 2. 新增基础设施组件：无

v0.6.0 **不引入** 以下组件（明确排除）：

| 排除项 | 排除原因 |
|--------|---------|
| Redis | 树莓派单机物理部署，进程内 Python dict 状态机满足需求（估算 9 MB，远低于 256 MB 触发阈值）；AB-001 待将来需要时再引入 |
| Docker | 生产环境约束，禁止使用 Docker |
| Celery / APScheduler | 故障清理任务由 systemd timer 驱动（one-shot），无需任务队列基础设施 |
| WebSocket（服务端推送）| 故障管理页面采用轮询/手动刷新模式，无实时推送需求（本期 out of scope）|

---

## 3. 新增 systemd 服务

### 3.1 freeark-fault-consumer.service

| 属性 | 值 |
|------|---|
| 类型 | `Type=simple`（长驻进程）|
| 启动命令 | `python manage.py fault_consumer` |
| 重启策略 | `Restart=on-failure, RestartSec=30s` |
| 日志 | `journald`，标识符 `freeark-fault-consumer` |
| 查看日志 | `journalctl -u freeark-fault-consumer -f` |
| 与心跳服务关系 | 独立进程，独立 MQTT client_id，互不影响 |

### 3.2 freeark-fault-cleanup.service + freeark-fault-cleanup.timer

| 属性 | 值 |
|------|---|
| 类型 | `Type=oneshot`（一次性执行）|
| 启动命令 | `python manage.py fault_cleanup --days=90 --batch-size=1000` |
| 触发方式 | systemd timer `OnCalendar=*-*-* 03:30:00` |
| 持久化 | `Persistent=true`（系统关机期间错过的 timer 在下次启动后补执行一次）|
| 日志 | `journald`，标识符 `freeark-fault-cleanup` |
| 查看日志 | `journalctl -u freeark-fault-cleanup` |

### 3.3 现有服务清单（不修改）

| 服务名 | 状态 | 说明 |
|--------|------|------|
| freeark-backend | 保持不变 | uvicorn/Django 主服务 |
| freeark-screen-heartbeat | 保持不变 | 大屏心跳 MQTT 消费者 |
| freeark-dph-cleanup | 保持不变 | device_param_history 清理（常驻 cron 模式）|
| freeark-plc-connection-monitor | 保持不变 | PLC 连接状态巡检 |

---

## 4. Python 包依赖变化

**requirements.txt 无需修改。** v0.6.0 使用的所有 Python 包均已在现有 requirements.txt 中声明：

| 包 | 现有版本约束 | v0.6.0 使用方式 |
|----|------------|----------------|
| `paho-mqtt` | >=1.6.1（实际 2.1.0）| fault_consumer 使用 1.x 风格 API（与心跳服务相同）|
| `djangorestframework` | 已有 | FaultEventSerializer + 分页 |
| `mysqlclient` | 已有 | fault_event 表 migration + ORM 查询 |
| `django` | >=5.2.0 | FaultEvent Model + Management Command |
| `schedule` | >=1.1.0 | **不使用**（fault_cleanup 是 one-shot，由 systemd timer 调度）|

---

## 5. 数据库变更

### 5.1 新增表：fault_event

通过 Django migration 自动生成 DDL，无需手动执行 SQL。

```
fault_event 表新增到现有 MySQL @ 192.168.31.98:3306
与以下现有表并存（无关联，无 FK 约束）：
- plc_latest_data          （v0.5.3-FCC 数据源，完全不修改）
- device_param_history     （严禁查询，不修改）
- plc_connection_status    （不修改）
- screen_connectivity_status（不修改）
- owner_info               （fault_consumer 只读，获取 MAC→specific_part 映射）
```

### 5.2 migration 执行方式

```bash
# 在生产服务器 192.168.31.51 通过 plink + git pull 部署后执行
python manage.py migrate
# 仅创建 fault_event 表（新表，不影响任何现有表结构）
# migration 执行时间短（CREATE TABLE），无锁表风险
```

### 5.3 回滚方式

```bash
# 如需回滚 fault_event 表
python manage.py migrate api NNNN_migration_before_fault_event
# 或 DROP TABLE fault_event（不影响其他表）
```

---

## 6. 前端依赖变化

**package.json 无需修改。** 新增的 `FaultManagementView.vue` 仅使用已有的 Element Plus 组件：

| Element Plus 组件 | 已在项目中使用 | v0.6.0 使用位置 |
|-------------------|--------------|----------------|
| `ElTable` / `ElTableColumn` | 是（设备列表页）| 故障事件数据表格 |
| `ElPagination` | 是 | 故障事件分页 |
| `ElForm` / `ElFormItem` | 是 | 过滤条件区 |
| `ElInput` | 是 | 房号输入框 |
| `ElDatePicker` (type="daterange") | 是（其他报表页）| 故障时间段选择器 |
| `ElSelect` (multiple) | 是 | 故障类型、设备多选下拉 |
| `ElSwitch` | 是 | 只看未恢复 toggle |
| `ElButton` | 是 | 查询/重置/查看面板按钮 |
| `ElTag` | 是 | severity 标签（error=danger，warning=warning）|

---

## 7. 测试工具栈

| 工具 | 用途 | 版本 |
|------|------|------|
| pytest + pytest-django | 后端单元测试 / 集成测试 | 同现有生产 dev 依赖 |
| Django TestCase | 集成测试（ORM + API 测试）| Django 内置 |
| DRF APIClient | API 接口测试 | DRF 内置 |
| SQLite | 测试数据库（替换 MySQL）| Django 内置 |

**所有自动化测试不依赖生产 MySQL**，使用 SQLite 内存数据库（`TEST: {'NAME': ':memory:'}` 或默认 test_db.sqlite3）。

---

## 8. 部署工具

| 工具 | 用途 |
|------|------|
| plink（PuTTY Link）| SSH 连接到生产服务器 192.168.31.51 |
| git pull | 拉取代码（唯一允许的部署方式，禁 pscp）|
| systemctl | 服务管理（enable / start / restart / status）|
| journalctl | 日志查看 |

---

## 9. 技术风险

| 风险 | 影响 | 缓解 |
|------|------|------|
| paho-mqtt 2.1.0 与 1.x API 的行为差异 | fault_consumer 使用 1.x 风格，实际运行 2.1.0；已知兼容（requirements.txt 注释记录）| 完全复用 screen_heartbeat_consumer.py 的 paho 初始化模式，已在生产验证 |
| systemd timer `Persistent=true` 在树莓派重启时行为 | 重启后可能立即执行一次清理 | 清理任务是幂等的（多次执行结果相同），无副作用 |
| fault_event 表 migration 期间锁表 | 新表 CREATE TABLE，无影响现有表的 ALTER；MySQL 9.4 对新表 DDL 无锁争用 | 在低负载时段（如凌晨）执行 migration |
| SQLite vs MySQL 日期函数行为差异 | fault_cleanup 使用 `< NOW() - INTERVAL 90 DAY`；SQLite 不支持 MySQL 的 INTERVAL 语法 | 测试中使用 Django ORM `first_seen_at__lt=timezone.now() - timedelta(days=90)` 代替原生 SQL，ORM 会自动适配 SQLite/MySQL |
