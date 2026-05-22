# FreeArkWeb 系统架构设计

<!-- file_header
author_agent: sub_agent_system_architect
phase: PHASE_03
project: FreeArkWeb
created_at: 2026-04-14
updated_at: 2026-05-22
status: APPROVED
source: reverse_engineering — api/ directory, freearkweb/settings.py, frontend/src/views/*.vue
change_log: 2026-05-22 — 新增前端架构章节（§4 前端整体架构、§5 需求覆盖矩阵补充）
-->

---

## 1. 架构概述

FreeArkWeb 采用单体 Django + Django REST Framework 架构，部署在物理机（树莓派，192.168.31.51）上。系统职责分为数据采集、数据计算和 REST API 三层。

### 1.1 系统边界

```
[外部客户端（Web/屏幕设备）]
         |  HTTP REST
         v
[Django REST API 层（api/views.py）]
         |
[业务逻辑层（calculators / handlers）]
         |
[数据访问层（Django ORM / api/models.py）]
         |
[数据库（SQLite 测试 / MySQL 生产 192.168.31.98:3306）]

[MQTT Broker] --> [mqtt_consumer.py] --> [mqtt_handlers.py] --> [数据访问层]
```

### 1.2 架构决策记录 (ADR)

#### ADR-001 数据库选型

**决策**：测试环境使用 SQLite，生产环境使用 MySQL（192.168.31.98:3306）

**备选方案**：
- 方案A：统一使用 SQLite（轻量，但生产不适合高并发写入）
- 方案B（采用）：测试 SQLite + 生产 MySQL，通过 settings.py 的 USE_SQLITE 开关切换

**理由**：生产数据量随楼宇数量增长，MySQL 性能更优；SQLite 无需额外依赖，适合测试隔离。

#### ADR-002 认证机制

**决策**：采用 DRF Token Authentication

**备选方案**：
- 方案A：JWT（无状态，适合分布式，但增加依赖）
- 方案B（采用）：DRF Token（有状态，Token 存储于数据库，登出时可主动删除，适合当前单体部署规模）

**理由**：当前系统为单体部署，Token 存数据库便于管理和主动失效；无需引入 JWT 依赖。

#### ADR-003 MQTT 数据采集方式

**决策**：以独立 management command 方式运行 MQTT 消费者（mqtt_consumer_service.py）

**备选方案**：
- 方案A：Celery 异步任务（增加 Redis 依赖，部署复杂）
- 方案B（采用）：management command + 后台进程（物理机直接运行，无额外中间件依赖）

**理由**：基础设施约束禁止 Docker，保持依赖最少化。

---

## 2. 数据流

### 2.1 PLC 数据采集流

```
PLC设备 --MQTT--> Broker
    --> mqtt_consumer_service (management command)
    --> mqtt_handlers.PLCDataHandler.handle()
        --> PLCData (upsert by specific_part+energy_mode+usage_date)
    --> mqtt_handlers.ConnectionStatusHandler.handle()
        --> PLCConnectionStatus (get_or_create + update)
        --> PLCStatusChangeHistory (仅状态变更时写入)
```

### 2.2 日用量计算流

```
定时触发 (daily_usage_service management command)
    --> DailyUsageCalculator.calculate_daily_usage(date)
        --> 读取 PLCData 按 (specific_part, energy_mode, usage_date) 分组
        --> 创建/更新 UsageQuantityDaily
        --> 补全前日 final_energy=None 的记录
        --> 预创建次日 initial_energy 记录
```

### 2.3 月用量计算流

```
定时触发 (monthly_usage_service management command)
    --> MonthlyUsageCalculator.calculate_monthly_usage(date)
        --> 读取目标月份 UsageQuantityDaily
        --> 按 (specific_part, energy_mode) 分组聚合 min(initial)/max(final)
        --> 创建/更新 UsageQuantityMonthly
```

### 2.4 账单查询流

```
屏幕设备 --POST screenMAC--> /api/billing/list/
    --> 查 SpecificPartInfo 得 specific_part
    --> 查 UsageQuantityMonthly
    --> 计算 billAmount = usage_quantity * 0.28
    --> 返回账单列表
```

---

## 3. 需求覆盖矩阵

| 需求 ID | 覆盖模块 |
|--------|---------|
| REQ-FUNC-001~006 | api/views.py (认证视图), api/serializers.py |
| REQ-FUNC-007~009 | api/views.py (UserList, UserDetail, AdminUserCreate) |
| REQ-FUNC-010 | api/views.py (get_csrf_token) |
| REQ-FUNC-011 | api/views.py (health_check) |
| REQ-FUNC-012~015 | api/views.py (usage views), api/models.py (UsageQuantityDaily) |
| REQ-FUNC-016~017 | api/views.py (get_usage_quantity_monthly), api/models.py (UsageQuantityMonthly) |
| REQ-FUNC-018~021 | api/views.py (PLC status views), api/models.py (PLCConnectionStatus, PLCStatusChangeHistory) |
| REQ-FUNC-022~026 | api/views.py (get_bill_list), api/models.py (SpecificPartInfo, UsageQuantityMonthly) |

| REQ-FUNC-027~029 | frontend/HomeView.vue（Chart.js legend checkbox、Y轴 beginAtZero 移除） |
| REQ-FUNC-030 | frontend/6个 Vue 文件（副标题补齐） |
| REQ-FUNC-031~032 | frontend/DeviceManagementDeviceListView.vue（列名、列宽变更） |
| REQ-FUNC-033 | frontend/DeviceCardsView.vue（返回按钮） |
| REQ-FUNC-034 | frontend/router/index.js + DeviceManagementSettingsView.vue（新增）+ DeviceManagementDeviceListView.vue（移除弹窗） |

**覆盖状态**：所有 REQ-FUNC-001 ~ REQ-FUNC-034 均有对应模块覆盖，无缺口。

---

## 4. 前端整体架构（2026-05-22 补充）

### 4.1 技术栈

| 层次 | 技术 | 版本约束 |
|------|------|---------|
| 框架 | Vue 3（Composition API） | 已锁定 |
| UI 组件库 | Element Plus | 已锁定 |
| 图表库 | Chart.js + chartjs-plugin-datalabels | 已锁定 |
| 路由 | Vue Router 4（createWebHistory） | 已锁定 |
| HTTP 客户端 | 自封装 api.js（原生 fetch） | 已锁定 |
| MQTT | mqtt.js（WebSocket） + useMqttWebSocket composable | 已锁定 |
| 构建工具 | Vite | 已锁定 |

### 4.2 目录结构（关键部分）

```
frontend/src/
  views/
    HomeView.vue                          — 系统看板（含趋势图）
    DeviceManagementDeviceListView.vue    — 设备列表
    DeviceCardsView.vue                   — 设备面板
    DeviceSettingsPanelView.vue           — 设备设置参数（内嵌组件）
    DeviceManagementSettingsView.vue      — 【新增】设备设置独立页面容器
    ...（其余页面）
  components/
    Layout.vue                            — 整体布局（侧边栏、顶栏、内容区）
    CascadingSelector.vue                 — 楼栋-单元-户号级联选择器
  composables/
    useMqttWebSocket.js                   — MQTT WebSocket 连接 composable
  router/
    index.js                              — 路由配置（含 requiresAuth 守卫）
  utils/
    api.js                                — HTTP 请求封装
```

### 4.3 设计规范约定（Design Token，全站统一）

> 来源：global.css，已在 v0.5.8 科技深蓝主题改造中统一

| Token | 用途 |
|-------|------|
| `--color-primary` | 主色（蓝色系） |
| `--color-text-primary` | 主文字色 |
| `--color-text-placeholder` | 副文字色（用于 .page-subtitle） |
| `--font-size-lg` | 页面标题 h2 |
| `--font-size-sm` | 副标题 .page-subtitle |
| `--font-weight-semibold` | 标题字重 |
| `.page-header` | 页面标题容器 |
| `.page-subtitle` | 标题下方副标题（color: var(--color-text-placeholder), font-size: var(--font-size-sm)） |

### 4.4 本次 UI 调整不变约束

1. 不新增后端 API 接口（纯前端变更）。
2. 不修改 Design Token 定义（仅在新增组件中引用已有 token）。
3. DeviceSettingsPanelView.vue 的内部逻辑（参数加载、批量提交、MQTT ACK 处理）完全不变，仅改变其宿主（从 el-dialog 改为独立路由页面）。
4. 现有已有副标题的页面文案不改动。
