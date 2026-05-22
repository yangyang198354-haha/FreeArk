# FreeArkWeb 模块设计

<!-- file_header
author_agent: sub_agent_system_architect
phase: PHASE_04
project: FreeArkWeb
created_at: 2026-04-14
updated_at: 2026-05-22
status: APPROVED
source: reverse_engineering — api/ directory, frontend/src/views/*.vue, frontend/src/router/index.js
change_log: 2026-05-22 — 增量补充前端模块 MOD-FE-01~MOD-FE-05（5项 UI 调整设计）
change_log: 2026-05-22(v2) — 落入用户 OQ-01~OQ-04 最终决策（OQ-01 legend 位置固定、OQ-02 文案沿用现有、OQ-03 设备面板新增设置入口、OQ-04 不动导航）
-->

---

## 1. 模块清单

| 模块 | 文件路径 | 职责 |
|------|---------|------|
| MOD-01 数据模型 | api/models.py | 定义所有 ORM 模型和约束 |
| MOD-02 序列化器 | api/serializers.py | 数据校验与序列化 |
| MOD-03 REST 视图 | api/views.py | HTTP 请求处理、业务逻辑编排 |
| MOD-04 URL 路由 | api/urls.py | URL 到视图函数的映射 |
| MOD-05 日用量计算 | api/daily_usage_calculator.py | PLCData -> UsageQuantityDaily |
| MOD-06 月用量计算 | api/monthly_usage_calculator.py | UsageQuantityDaily -> UsageQuantityMonthly |
| MOD-07 MQTT 处理器 | api/mqtt_handlers.py | MQTT 消息解析与数据库写入 |
| MOD-08 MQTT 消费者 | api/mqtt_consumer.py | MQTT 客户端连接与消息分发 |
| MOD-09 PLC 数据清理 | api/plc_data_cleaner.py | 定期清理过期 PLCData |

---

## 2. 模块接口定义

### MOD-01 数据模型接口

```python
# 关键类型定义
CustomUser.role: Literal['admin', 'user']
PLCData.unique_together: ('specific_part', 'energy_mode', 'usage_date')
PLCConnectionStatus.specific_part: unique CharField
SpecificPartInfo.screenMAC: unique CharField
UsageQuantityDaily.time_period: DateField
UsageQuantityMonthly.usage_month: CharField  # YYYY-MM format
```

### MOD-02 序列化器接口

```python
UserLoginSerializer.validate(attrs) -> {'user': CustomUser, ...}
UserRegistrationSerializer.create(validated_data) -> CustomUser
UserCreateSerializer.create(validated_data) -> CustomUser
UsageQuantityDailySerializer.fields: [id, specific_part, building, unit, room_number,
                                       energy_mode, initial_energy, final_energy,
                                       usage_quantity, time_period]
UsageQuantityMonthlySerializer.fields: [id, specific_part, building, unit, room_number,
                                         energy_mode, initial_energy, final_energy,
                                         usage_quantity, usage_month]
PLCConnectionStatusSerializer.fields: [id, specific_part, connection_status,
                                        last_online_time, building, unit, room_number,
                                        created_at, updated_at]
```

### MOD-03 REST 视图接口

```python
# 认证端点
user_login(request: POST) -> Response({'success': bool, 'token': str, 'user': dict})
user_logout(request: POST) -> Response({'success': bool, 'message': str})
get_current_user(request: GET) -> Response({'success': bool, 'data': dict})
user_register(request: POST) -> Response({'success': bool, 'token': str, 'user': dict}, 201)
change_password(request: POST) -> Response({'success': bool})

# 能耗查询端点
get_usage_quantity(request: GET) -> Response({'success': bool, 'data': list, 'total': int})
get_usage_quantity_specific_time_period(request: GET) -> Response({'success': bool, 'data': list, 'total': int})
get_usage_quantity_monthly(request: GET) -> Response({'success': bool, 'data': list, 'total': int})

# PLC 状态端点
get_plc_connection_status(request: GET) -> Response({'success': bool, 'data': list, 'total': int, 'statistics': dict})
get_plc_connection_status_detail(request: GET, specific_part: str) -> Response({'success': bool, 'data': dict})
get_plc_status_change_history(request: GET, specific_part: str) -> Response({'success': bool, 'data': list, 'total': int})

# 账单端点（screenMAC 从 HTTP_SCREENMAC 请求头获取）
get_bill_list(request: POST) -> Response({'code': int, 'message': str, 'data': list})
```

### MOD-05 日用量计算器接口

```python
DailyUsageCalculator.parse_specific_part(specific_part: str) -> Tuple[str, str, str]  # (building, unit, room_number)
DailyUsageCalculator.calculate_daily_usage(target_date: date) -> dict
# 返回: {'processed_count': int, 'created_count': int, 'updated_count': int, ...}
```

### MOD-06 月用量计算器接口

```python
MonthlyUsageCalculator.calculate_monthly_usage(target_date: date) -> dict
# 返回: {'processed': int, 'created': int, 'updated': int, 'skipped': bool, ...}
# 异常: 非 date 类型返回 {'error': str}
```

### MOD-07 MQTT 处理器接口

```python
PLCDataHandler.batch_save_plc_data(batch: list[dict]) -> None
PLCDataHandler.handle(topic: str, payload: dict) -> None
ConnectionStatusHandler.handle(topic: str, payload: dict) -> None
ConnectionStatusHandler._parse_building_info(specific_part: str) -> Tuple[str, str, str]
```

### MOD-09 PLC 数据清理接口

```python
clean_old_plc_data(days: int) -> dict
# 返回: {'deleted_count': int, 'message': str}
```

---

## 3. 模块依赖关系（无循环依赖）

```
urls.py --> views.py --> serializers.py --> models.py
                     --> models.py
daily_usage_calculator.py --> models.py
monthly_usage_calculator.py --> models.py
mqtt_handlers.py --> models.py
mqtt_consumer.py --> mqtt_handlers.py
plc_data_cleaner.py --> models.py
```

**循环依赖检查**：所有依赖为单向，无循环依赖。

---

## 4. 权限控制矩阵

| 视图 | 匿名用户 | 普通用户 | 管理员 |
|------|---------|---------|-------|
| health_check | 允许 | 允许 | 允许 |
| get_csrf_token | 允许 | 允许 | 允许 |
| user_login | 允许 | 允许 | 允许 |
| user_register | 允许 | 允许 | 允许 |
| user_logout | 拒绝(401) | 允许 | 允许 |
| get_current_user | 拒绝(401) | 允许 | 允许 |
| change_password | 拒绝(401) | 允许 | 允许 |
| UserList | 拒绝(401) | 拒绝(403) | 允许 |
| UserDetail | 拒绝(401) | 拒绝(403) | 允许 |
| AdminUserCreate | 拒绝(401) | 拒绝(403) | 允许 |
| get_usage_quantity* | 允许 | 允许 | 允许 |
| get_plc_connection_status* | 允许 | 允许 | 允许 |
| get_bill_list | screenMAC验证 | screenMAC验证 | screenMAC验证 |

---

## 5. 前端模块增量设计（2026-05-22）

> 本节对应 REQ-FUNC-027~034，记录 5 项 UI 调整的前端模块级设计决策。

### 5.1 MOD-FE-01：近 7 天趋势图 Legend Checkbox（HomeView.vue）

**变更目标文件**：`frontend/src/views/HomeView.vue`

**OQ-01 最终决策（方案 A）**：legend checkbox 放在 `<el-card>` 的 `#header` 插槽内，与"近 7 天用电量趋势图"标题同一行、标题右侧对齐。

**变更点**：

| 项目 | 现状 | 目标 |
|------|------|------|
| Legend 显示方式 | Chart.js 内置 legend（`legend.display: true`，位于 renderChart options.plugins.legend） | 将 Chart.js 内置 `legend.display` 改为 `false`；改在 `<el-card>` 的 `#header` 插槽右侧渲染自定义 Vue checkbox 组 |
| checkbox 位置 | 无 | `<el-card #header>` 插槽内，header div 使用 flex + justify-content: space-between，左侧标题、右侧 checkbox 组 |
| 默认勾选状态 | N/A（无控制） | `checkedSeries = reactive({ total: false, cooling: true, heating: true })` |
| Chart.js dataset 控制 | 不受控 | renderChart 调用时根据 checkedSeries 设置各 dataset.hidden；checkbox 变更时调用 `chartInstance.data.datasets[i].hidden = !checked; chartInstance.update()` |
| Y 轴 `beginAtZero` | `true` | 移除（改为不设置或设 `false`），由 Chart.js 根据数据自动计算 min，支持负数展示 |

**接口约定**：

```javascript
// reactive 状态（script setup 风格，HomeView 当前为 Options API + setup()）
const checkedSeries = reactive({ total: false, cooling: true, heating: true })

// label 与 key 的映射（对应 renderChart datasets 顺序）
// index 0: '总用电量 (kWh)' → key 'total'
// index 1: '制冷 (kWh)'   → key 'cooling'
// index 2: '制热 (kWh)'   → key 'heating'

function toggleSeries(key) {
  checkedSeries[key] = !checkedSeries[key]
  if (!chartInstance) return
  const labelMap = { total: '总用电量 (kWh)', cooling: '制冷 (kWh)', heating: '制热 (kWh)' }
  const ds = chartInstance.data.datasets.find(d => d.label === labelMap[key])
  if (ds) {
    ds.hidden = !checkedSeries[key]
    chartInstance.update()
  }
}
```

**header 插槽模板结构**：

```html
<template #header>
  <div class="card-header trend-header">
    <span>近 7 天用电量趋势图</span>
    <div class="trend-legend-checkboxes">
      <label class="legend-checkbox-item">
        <input type="checkbox" v-model="checkedSeries.cooling" @change="toggleSeries('cooling')" />
        <span class="legend-dot cooling"></span>制冷
      </label>
      <label class="legend-checkbox-item">
        <input type="checkbox" v-model="checkedSeries.heating" @change="toggleSeries('heating')" />
        <span class="legend-dot heating"></span>制热
      </label>
      <label class="legend-checkbox-item">
        <input type="checkbox" v-model="checkedSeries.total" @change="toggleSeries('total')" />
        <span class="legend-dot total"></span>总用电量
      </label>
    </div>
  </div>
</template>
```

**不变约束**：renderChart() 函数仍接受 `data` 参数（API 返回数据），checkedSeries 状态独立于数据加载，重新 fetchTrend 后保留用户的勾选选择（renderChart 调用时读取当前 checkedSeries 设置 hidden）。

---

### 5.2 MOD-FE-02：副标题补齐（6 个 Vue 文件）

**变更目标文件**（6个，均已确认缺失 `.page-subtitle`）：

| 文件 | h2 文案 | 新增 page-subtitle 文案 |
|------|---------|------------------------|
| DeviceManagementDeviceListView.vue | 设备列表 | 查看和管理所有设备的运行状态 |
| OwnerManagementView.vue | 业主管理 | 管理业主信息及设备绑定关系 |
| ServicesView.vue | 服务管理 | 查看和管理系统后台服务运行状态 |
| CreateUserView.vue | 创建用户 | 为员工创建系统登录账号 |
| ChangePasswordView.vue | 修改登录密码 | 修改当前登录账号的密码 |
| PlcWriteRecordView.vue | 设置记录 | 查看 PLC 参数写入操作的历史记录 |

**变更模式**（对每个文件统一执行）：

```html
<!-- 变更前 -->
<div class="page-header">
  <h2>XXX</h2>
</div>

<!-- 变更后 -->
<div class="page-header">
  <h2>XXX</h2>
  <p class="page-subtitle">YYY</p>
</div>
```

**样式约定**：`.page-subtitle` 样式已在 HomeView、DailyUsageReportView、MonthlyUsageReportView 中定义（`margin: 5px 0 0 0; color: #909399; font-size: 13px`）。若各文件已有 scoped 样式块，追加同样的 `.page-subtitle` 规则；若期望统一，可考虑将此规则上移到 global.css（但本次为最小变更，各文件自行定义）。

**特殊情况 — ServicesView.vue**：该页面 `.page-header` 为 flex 布局（含刷新按钮），需确保 `.page-subtitle` 换行显示而非与按钮并排。解决方案：将 `.page-header` 改为 flex-direction: column 或在 h2+subtitle 外包裹 `<div class="page-title-group">`。

---

### 5.3 MOD-FE-03：设备列表列名与宽度（DeviceManagementDeviceListView.vue）

**变更目标文件**：`frontend/src/views/DeviceManagementDeviceListView.vue`

**变更点**：

| 属性 | 现状（L111） | 目标 |
|------|------------|------|
| `label` | `"PLC最后在线时间"` | `"PLC上次心跳"` |
| `min-width` | `"160"` | 移除 min-width |
| `width` | 未设置 | `"150"` |

**变更代码片段**：

```html
<!-- 变更前 -->
<el-table-column label="PLC最后在线时间" min-width="160" align="center">

<!-- 变更后 -->
<el-table-column label="PLC上次心跳" width="150" align="center">
```

**数据绑定**：`row.plc_last_online_time` 字段名及 `formatDateTime()` 格式化函数不变。

---

### 5.4 MOD-FE-04：设备面板返回按钮与设置入口（DeviceCardsView.vue）

**变更目标文件**：`frontend/src/views/DeviceCardsView.vue`

**OQ-03 最终决策**：除设备列表「操作」列的"设置"按钮外，设备面板（DeviceCardsView.vue）也要新增一个进入设置页的入口，入口需携带当前 `specific_part` 参数，跳转到 `/device-management/device-settings?specific_part=...`。

**新增依赖**：`import { useRouter } from 'vue-router'`（DeviceCardsView 是 Options API，使用 `this.$router`，无需额外引入）

**变更设计**：

在 `<template v-else>` 块内、`<div class="panel-nav-bar">` 之前插入页面头部区域：

```html
<div class="panel-page-header">
  <div class="panel-header-left">
    <el-button :icon="ArrowLeft" @click="goBack" size="small">返回</el-button>
    <h2 class="panel-title">设备面板</h2>
    <p class="page-subtitle">专有部分：{{ specificPart }}</p>
  </div>
  <div class="panel-header-right">
    <el-button type="warning" size="small" @click="goToSettings">参数设置</el-button>
  </div>
</div>
```

**goBack 方法实现**（Options API methods 块）：

```javascript
goBack() {
  if (window.history.length > 1) {
    this.$router.back()
  } else {
    this.$router.push('/device-management/device-list')
  }
},
```

**goToSettings 方法实现**（Options API methods 块，OQ-03）：

```javascript
goToSettings() {
  if (this.specificPart) {
    this.$router.push(
      '/device-management/device-settings?specific_part=' +
      encodeURIComponent(this.specificPart)
    )
  }
},
```

**icons 引入**：DeviceCardsView 当前已从 `@element-plus/icons-vue` 引入 `Loading`；需追加引入 `ArrowLeft`：
```javascript
import { Loading, ArrowLeft } from '@element-plus/icons-vue'
```

**样式约定**：`.panel-page-header` 使用 flex 布局（justify-content: space-between），与全站 `.page-header` 结构对齐；`.panel-header-left` 垂直堆叠（column 方向）；h2 样式遵循全站 Design Token。

---

### 5.5 MOD-FE-05：设置面板独立路由页面

**变更范围**：涉及 3 个文件 + 路由配置

#### 5.5.1 新增路由

**文件**：`frontend/src/router/index.js`

```javascript
{
  path: '/device-management/device-settings',
  name: 'DeviceSettings',
  component: () => import('../views/DeviceManagementSettingsView.vue'),
  meta: { requiresAuth: true }
}
```

#### 5.5.2 新增页面组件

**新文件**：`frontend/src/views/DeviceManagementSettingsView.vue`

职责：独立页面容器，从 `route.query.specific_part` 读取参数，嵌入 `DeviceSettingsPanelView`，提供"返回"按钮。

```
DeviceManagementSettingsView
  ├── page-header（标题"参数设置" + subtitle "专有部分：{specific_part}"）
  ├── el-button（返回，点击跳转 /device-management/device-list）
  └── DeviceSettingsPanelView（:specific-part="specificPart"，以内嵌方式渲染）
```

关键约束：
- `specificPart` 从 `useRoute().query.specific_part` 取得；若为空则显示 el-alert 提示并禁止加载 DeviceSettingsPanelView。
- 不引入 el-dialog，无弹窗相关逻辑。
- MQTT WebSocket 生命周期由 DeviceSettingsPanelView 自身的 `onMounted`/`onUnmounted` 管理（现有逻辑不变）。

#### 5.5.3 修改设备列表

**文件**：`frontend/src/views/DeviceManagementDeviceListView.vue`

| 项目 | 现状 | 目标 |
|------|------|------|
| `handleOpenSettings` 方法 | 设置 `settingsSpecificPart` 和 `settingsDialogVisible = true` | 改为 `router.push('/device-management/device-settings?specific_part=' + encodeURIComponent(row.specific_part))` |
| `el-dialog`（L221-L232） | 存在 | 移除整个 el-dialog 块 |
| `settingsDialogVisible` ref | 存在 | 移除 |
| `settingsSpecificPart` ref | 存在 | 移除 |
| `import DeviceSettingsPanelView` | 存在（L244） | 移除（不再在此页面引入） |

#### 5.5.4 ADR-UI-001：设置页弹窗改路由的决策记录

**决策**：将设备设置从 el-dialog 改为独立路由页面

**备选方案**：
- 方案A（现状）：el-dialog 内嵌 DeviceSettingsPanelView；实现简单，但弹窗尺寸受限、无独立 URL、无返回按钮。
- 方案B（采用）：独立路由页面；可利用全页宽度展示参数分组表格，有返回按钮，URL 可复制，与全站导航模型一致。
- 方案C：侧边抽屉（el-drawer）；较弹窗更宽，但仍无独立 URL，不符合用户"内嵌面板"的明确要求。

**理由**：用户明确要求"嵌入在面板内的页面，并带返回按钮"，方案B最直接满足。DeviceSettingsPanelView 本身已接受 `specificPart` prop，改造为路由页面只需新增包装容器，风险低。

---

## 6. 前端路由变更汇总

| 路由路径 | 组件 | 变更类型 | 关联需求 |
|---------|------|---------|---------|
| `/home` | HomeView.vue | 修改（新增 checkbox UI） | REQ-FUNC-027~029 |
| `/device-management/device-list` | DeviceManagementDeviceListView.vue | 修改（移除弹窗、改名列、加副标题） | REQ-FUNC-030~032, 034 |
| `/device-cards` | DeviceCardsView.vue | 修改（新增返回按钮 + 设置入口，OQ-03） | REQ-FUNC-033, REQ-FUNC-034 |
| `/device-management/device-settings` | DeviceManagementSettingsView.vue（新建） | 新增 | REQ-FUNC-034 |
| `/owner-management` | OwnerManagementView.vue | 修改（加副标题） | REQ-FUNC-030 |
| `/services` | ServicesView.vue | 修改（加副标题） | REQ-FUNC-030 |
| `/create-user` | CreateUserView.vue | 修改（加副标题） | REQ-FUNC-030 |
| `/change-password` | ChangePasswordView.vue | 修改（加副标题） | REQ-FUNC-030 |
| `/plc-write-records` | PlcWriteRecordView.vue | 修改（加副标题） | REQ-FUNC-030 |
