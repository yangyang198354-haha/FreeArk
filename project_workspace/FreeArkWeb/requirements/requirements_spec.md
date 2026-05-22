# FreeArkWeb 需求规格说明书

<!-- file_header
author_agent: sub_agent_requirement_analyst
phase: PHASE_01
project: FreeArkWeb
created_at: 2026-04-14
updated_at: 2026-05-22
status: APPROVED
source: reverse_engineering — api/models.py, api/views.py, api/serializers.py, api/urls.py, frontend/src/views/*.vue
change_log: 2026-05-22 — 增量补充 UI 调整需求 REQ-FUNC-027~034（5项 UI 变更）
-->

---

## 1. 项目概述

**来源**：从现有代码库逆向推导（FreeArkWeb/backend/freearkweb/api/）

FreeArkWeb 是一套面向住宅楼宇集中供暖/供冷管理场景的后端 REST API 服务。系统通过 MQTT 从 PLC 设备采集能耗脉冲数据，经过计算汇聚成日用量和月用量，并提供账单查询等功能。

---

## 2. 功能需求（Functional Requirements）

### 2.1 用户认证与授权

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-001 | 系统支持用户名/密码登录，登录成功后返回 Token | views.py:user_login |
| REQ-FUNC-002 | 系统支持 Token 认证的用户登出，登出时删除 Token | views.py:user_logout |
| REQ-FUNC-003 | 已认证用户可查询自身账号信息（id、username、email、role、department、position） | views.py:get_current_user |
| REQ-FUNC-004 | 系统支持用户自主注册，注册后自动登录并返回 Token，默认角色为 user | views.py:user_register |
| REQ-FUNC-005 | 已认证用户可修改自身密码，须校验旧密码正确性 | views.py:change_password |
| REQ-FUNC-006 | 系统定义两种角色：admin（管理员）和 user（普通用户） | models.py:CustomUser |

### 2.2 管理员用户管理

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-007 | 仅管理员可获取全部用户列表 | views.py:UserList |
| REQ-FUNC-008 | 仅管理员可查询、更新、删除指定用户 | views.py:UserDetail |
| REQ-FUNC-009 | 仅管理员可创建新用户；创建时若用户名重复，返回明确的错误提示 | views.py:AdminUserCreate |

### 2.3 CSRF Token 获取

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-010 | 提供无需认证的 CSRF Token 获取接口，Token 同时写入响应体和 Cookie | views.py:get_csrf_token |

### 2.4 健康检查

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-011 | 提供无需认证的健康检查接口，返回服务运行状态 | views.py:health_check |

### 2.5 能耗日用量查询

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-012 | 提供日用量列表查询接口，支持按专有部分（specific_part）、供能模式（energy_mode）、时间段（start_time/end_time）过滤 | views.py:get_usage_quantity |
| REQ-FUNC-013 | 日用量查询支持分页（page、page_size），结果按 time_period 升序排序 | views.py:get_usage_quantity |
| REQ-FUNC-014 | 提供特定时间段汇总接口，按 (specific_part, energy_mode) 分组聚合，返回 min(initial_energy)、max(final_energy) 及差值 usage_quantity | views.py:get_usage_quantity_specific_time_period |
| REQ-FUNC-015 | 特定时间段汇总接口支持分页，total 字段返回满足条件的组合总数 | views.py:get_usage_quantity_specific_time_period |

### 2.6 能耗月用量查询

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-016 | 提供月度用量查询接口，支持按 specific_part、building、unit、room_number、energy_mode、usage_month、start_month/end_month 过滤 | views.py:get_usage_quantity_monthly |
| REQ-FUNC-017 | 月度用量查询支持分页，结果按 specific_part、energy_mode、usage_month 升序排序 | views.py:get_usage_quantity_monthly |

### 2.7 PLC 设备连接状态

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-018 | 提供 PLC 设备连接状态列表查询，支持按 building、unit、connection_status 过滤，支持分页 | views.py:get_plc_connection_status |
| REQ-FUNC-019 | PLC 连接状态列表接口须返回统计信息：online_count、offline_count、total_devices、online_rate（百分比，保留2位小数） | views.py:get_plc_connection_status |
| REQ-FUNC-020 | 提供单个 PLC 设备连接状态详情查询，按 specific_part 精确匹配，不存在时返回 404 | views.py:get_plc_connection_status_detail |
| REQ-FUNC-021 | 提供 PLC 设备状态变化历史查询，按 specific_part 过滤，结果按 change_time 倒序，支持分页 | views.py:get_plc_status_change_history |

### 2.8 历史用能账单

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-022 | 账单查询接口从请求头 screenMAC 字段识别设备，查找对应 specific_part，screenMAC 缺失返回 400 | views.py:get_bill_list |
| REQ-FUNC-023 | 账单查询接口根据 specific_part 从月用量表查询账单数据，支持按 startDate/endDate（YYYY-MM 或 YYYYMM 格式）和 energyType 过滤 | views.py:get_bill_list |
| REQ-FUNC-024 | 账单计费规则：单价 0.28 元/kWh，billAmount = usage_quantity * 0.28，保留2位小数 | views.py:get_bill_list |
| REQ-FUNC-025 | 账单响应包含 billingCycle（YYYY年MM月格式）、billingDate（月末日期）、familyName（X栋X单元XXX格式） | views.py:get_bill_list |
| REQ-FUNC-026 | screenMAC 在 SpecificPartInfo 表中不存在时返回 404 | views.py:get_bill_list |

---

## 3. 非功能需求（Non-Functional Requirements）

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-NFN-001 | 认证方式：Token 认证（DRF TokenAuthentication）+ Session 认证 | settings.py:REST_FRAMEWORK |
| REQ-NFN-002 | 测试数据库：SQLite（禁止连接生产 MySQL 192.168.31.98） | 基础设施约束 |
| REQ-NFN-003 | 所有需要认证的接口，未认证请求返回 HTTP 401 | views.py 各视图 permission_classes |
| REQ-NFN-004 | 普通用户尝试访问仅限管理员的接口，返回 HTTP 403 | IsAdminUser 权限类 |
| REQ-NFN-005 | 时区：Asia/Shanghai，USE_TZ=False | settings.py |
| REQ-NFN-006 | 平台：物理机直接部署，禁止 Docker | 基础设施约束 |

---

## 4. 数据模型约束

| 模型 | 关键约束 | 来源 |
|------|---------|------|
| CustomUser | role ∈ {admin, user}，默认 user | models.py |
| PLCData | unique_together: (specific_part, energy_mode, usage_date) | models.py |
| PLCConnectionStatus | specific_part 唯一 | models.py |
| SpecificPartInfo | screenMAC 唯一 | models.py |
| UsageQuantityDaily | time_period 为 DateField（YYYY-MM-DD） | models.py |
| UsageQuantityMonthly | usage_month 为 CharField（YYYY-MM） | models.py |

---

## 5. 接口端点汇总

---

## 6. UI 调整功能需求（2026-05-22 增量）

> 背景：已上线的 FreeArkWeb 前端完成了科技深蓝主题统一改造（v0.5.8）。本节记录 5 项 UI 细化调整需求，均为增量变更，不引入新的后端接口。

### 6.1 系统看板 — 近 7 天电量趋势图 legend 控制与负数 Y 轴

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-027 | 近 7 天电量趋势图在图表区上方新增 legend checkbox 控制组：用户可勾选/取消勾选各数据系列（制冷、制热、总用电量）以控制其在图表中的显示与隐藏 | 用户需求第1项 |
| REQ-FUNC-028 | legend checkbox 默认状态：制冷=勾选，制热=勾选，总用电量=不勾选 | 用户需求第1项 |
| REQ-FUNC-029 | 当趋势图数据集包含负值时，Chart.js Y 轴须自动扩展至负数范围，不得裁剪负数部分（即移除 `beginAtZero: true` 约束，改由 Chart.js 自动计算 min） | 用户需求第1项；来源：HomeView.vue L546 `beginAtZero: true` |

### 6.2 全站页面标题副标题补齐

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-030 | 所有主功能页面在 `<h2>` 标题下方应有一行 `.page-subtitle` 简介文案。核查现状：HomeView（已有）、DailyUsageReportView（已有）、MonthlyUsageReportView（已有）、UsageQueryView（已有）、PlcStatusView（已有）、SpecificPartDetailView（已有）、DeviceParamHistoryView（已有，以 specific_part 为副标题）、RoomHistoryView（已有，以 specific_part 为副标题）；**缺失**副标题的页面为：设备列表（DeviceManagementDeviceListView）、业主管理（OwnerManagementView）、服务管理（ServicesView）、创建用户（CreateUserView）、修改密码（ChangePasswordView）、设置记录（PlcWriteRecordView） | 用户需求第2项；来源：各 .vue 文件 page-header 核查 |

### 6.3 设备列表"PLC最后在线时间"列名与宽度

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-031 | 【已核实】`PLCConnectionStatus.last_online_time` 字段的更新机制：由 `mqtt_handlers.py` 中 `_update_connection_status()` 函数在每次收到 MQTT 数据包时（即每次 PLC 设备上报数据，触发 ConnectionStatus 快/慢路径处理）写入 `timezone.now()`。该时间戳表示"PLC 设备最后一次发送 MQTT 数据包的时间"，本质为**最近一次通信/心跳时间**，而非"最近一次从离线恢复为在线的时间"。因此列名应从"PLC最后在线时间"改为"PLC上次心跳" | 用户需求第3项；来源：mqtt_handlers.py `_update_connection_status()` 快路径 L534、慢路径 L607-L622 |
| REQ-FUNC-032 | 设备列表"PLC上次心跳"列宽度收紧，从 `min-width="160"` 改为固定 `width="150"`（显示格式 YYYY-MM-DD HH:MM:SS，150px 可容纳） | 用户需求第3项；来源：DeviceManagementDeviceListView.vue L111 |

### 6.4 设备面板新增返回按钮

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-033 | DeviceCardsView（设备面板，路由 `/device-cards?specific_part=...`）须在页面顶部新增"返回"按钮，点击后执行 `router.back()` 或 `router.push('/device-management/device-list')` 返回上一页（设备列表） | 用户需求第4项；来源：DeviceCardsView.vue、router/index.js |

### 6.5 设置面板从弹窗改为内嵌页面

| ID | 需求描述 | 来源 |
|----|---------|------|
| REQ-FUNC-034 | 当前"设置"功能通过 `el-dialog` 弹窗在设备列表页内渲染 `DeviceSettingsPanelView`（`settingsDialogVisible` 控制），须改为独立路由页面：新增路由 `/device-management/device-settings?specific_part=...`，`DeviceSettingsPanelView` 以全页面内嵌方式呈现，并配有"返回"按钮（返回设备列表）；设备列表中的"设置"按钮改为路由跳转而非弹窗触发；页面风格、配色遵循全站科技深蓝主题设计规范 | 用户需求第5项；来源：DeviceManagementDeviceListView.vue L221-L232（el-dialog），DeviceSettingsPanelView.vue |

### 6.6 约束说明

| ID | 约束描述 |
|----|---------|
| REQ-NFN-007 | 以上5项均为纯前端 UI 调整，不新增后端 API 接口 |
| REQ-NFN-008 | 所有新增页面/组件须遵循已统一的科技深蓝主题设计规范（Design Token、global.css、`.page-header`/`.page-subtitle` 样式约定） |
| REQ-NFN-009 | DeviceSettingsPanelView 改为独立路由页面后，MQTT WebSocket 连接（ackTopic 订阅）的生命周期须由页面 `onMounted`/`onUnmounted` 管理，不受弹窗状态影响 |

| 路径 | 方法 | 认证要求 | 关联需求 |
|------|------|---------|---------|
| /api/get-csrf-token/ | GET | 无 | REQ-FUNC-010 |
| /api/auth/login/ | POST | 无 | REQ-FUNC-001 |
| /api/auth/logout/ | POST | 必须 | REQ-FUNC-002 |
| /api/auth/me/ | GET | 必须 | REQ-FUNC-003 |
| /api/auth/register/ | POST | 无 | REQ-FUNC-004 |
| /api/change-password/ | POST | 必须 | REQ-FUNC-005 |
| /api/users/ | GET | 管理员 | REQ-FUNC-007 |
| /api/users/{pk}/ | GET/PUT/DELETE | 管理员 | REQ-FUNC-008 |
| /api/users/create/ | POST | 管理员 | REQ-FUNC-009 |
| /api/health/ | GET | 无 | REQ-FUNC-011 |
| /api/usage/quantity/ | GET | 无 | REQ-FUNC-012, 013 |
| /api/usage/quantity/specifictimeperiod/ | GET | 无 | REQ-FUNC-014, 015 |
| /api/usage/quantity/monthly/ | GET | 无 | REQ-FUNC-016, 017 |
| /api/plc/connection-status/ | GET | 无 | REQ-FUNC-018, 019 |
| /api/plc/connection-status/{specific_part}/ | GET | 无 | REQ-FUNC-020 |
| /api/plc/status-change-history/{specific_part}/ | GET | 无 | REQ-FUNC-021 |
| /api/billing/list/ | POST | 无（screenMAC 头） | REQ-FUNC-022~026 |
