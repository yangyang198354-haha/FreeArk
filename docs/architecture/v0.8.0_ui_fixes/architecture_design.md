# v0.8.0 UI 修复 — 架构与模块设计

```
file_header:
  document_id: ARCH-v0.8.0-UI
  title: v0.8.0 UI 修复批次 — 架构设计
  author_agent: sub_agent_system_architect (via PM Orchestrator)
  project: FreeArk 住宅能耗/暖通监控平台
  version: v0.8.0-ui-fixes
  created_at: 2026-05-30
  last_updated: 2026-05-30
  status: APPROVED
  references:
    - docs/requirements/v0.8.0_ui_fixes/requirements_spec.md (v0.2.0-APPROVED)
    - FreeArkWeb/frontend/src/views/CondensationWarningView.vue
    - FreeArkWeb/frontend/src/views/FaultManagementView.vue
    - FreeArkWeb/frontend/src/views/DeviceCardsView.vue
```

---

## 1. 变更范围总览

本批次全部为纯前端修改，不涉及后端 API、数据库或 systemd 服务变更。

| 模块 ID | 文件 | 变更类型 | 对应需求 |
|---------|------|---------|---------|
| MOD-CW | CondensationWarningView.vue | 文案 + 新增操作列 + 新增 handleViewDevicePanel | REQ-UI-001, REQ-UI-002, REQ-UI-004 |
| MOD-FM | FaultManagementView.vue | 文案 + 跳转方式 | REQ-UI-003, REQ-UI-004 |
| MOD-DC | DeviceCardsView.vue | goBack 逻辑 + 按钮样式 + 导航栏分行 | REQ-UI-004, REQ-UI-005-A, REQ-UI-005-B |

---

## 2. 架构决策记录（ADR）

### ADR-v080-01：设备面板跳转方式 — 同标签页 router.push（已裁决）

**背景**：从故障管理/结露预警进入设备面板，有两种候选方案：
- 方案1：`window.open('_blank')` 新标签页
- 方案2：`router.push` 同标签页，通过 query `from` 参数携带来源

**裁决（用户，2026-05-30）**：采用方案2。

**理由**：
- 不破坏浏览器单标签页工作流；
- 返回路径明确可控（通过 `from` 参数），无需依赖浏览器历史栈；
- 与设备列表 → 设备面板的现有跳转方式一致。

**影响**：
- `FaultManagementView.handleViewDevicePanel`：删除 `router.resolve` + `window.open`，改为 `router.push({ name: 'DeviceCards', query: { specific_part, from: 'fault-management' } })`
- `CondensationWarningView.handleViewDevicePanel`（新增）：同上，`from: 'condensation-warnings'`
- `DeviceCardsView.goBack()`：读取 `$route.query.from` 做条件跳转

### ADR-v080-02：from 参数路由映射表（固定白名单）

```
from 参数值              → 跳转目标路由
'fault-management'      → /device-management/faults
'condensation-warnings' → /device-management/condensation-warnings
'device-list' / 无值    → router.back() 或 /device-management/device-list（兜底）
其他未知值              → /device-management/device-list（安全兜底）
```

### ADR-v080-03：Tab 导航栏分行 — 静态白名单分类（而非后端字段）

**背景**：当前所有 Tab 通过 `v-for deviceData.sub_types` 单行平铺，无分类。

**方案选择**：
- 方案A：后端在 API 响应中返回分类字段 → 需改后端，超出本批次范围
- 方案B：前端根据已知 `subKey` 白名单静态分类 → 符合约束 C-01（不改后端）

**裁决**：方案B。

**白名单定义**：
```javascript
const THERMOSTAT_KEYS = new Set([
  'panel_living_room', 'panel_study_room', 'panel_bedroom',
  'panel_children_room', 'panel_fourth_children_room'
])
const SYSTEM_KEYS = new Set([
  'fresh_air', 'energy_meter', 'hydraulic_module', 'air_quality'
])
```

**渲染策略**：
- 遍历 `deviceData` 所有 `sub_types`，将 `subKey` 按白名单分入两组
- 第一行（温控）：按 THERMOSTAT_KEYS 枚举顺序渲染（保持固定排序）
- 第二行（系统）：按 SYSTEM_KEYS 枚举顺序渲染
- 温控行保留"历史数据 ›"入口（触发 `goToRoomHistory`），位置为行首分类标签旁
- 系统设备各 Tab 内历史数据链接（`goToHistory`）保留

---

## 3. 模块详细设计

### MOD-CW — CondensationWarningView.vue

**变更点：**

1. **REQ-UI-001（文案）**
   - 模板第 17-18 行：`未回复` → `未恢复`，`已回复` → `已恢复`
   - 第 190 行注释同步更新

2. **REQ-UI-002（操作列）**
   - 在表格末尾（恢复时间列之后）新增：
     ```html
     <el-table-column label="操作" min-width="120" fixed="right">
       <template #default="{ row }">
         <el-button link type="primary" size="small" @click="handleViewDevicePanel(row)">
           设备面板
         </el-button>
       </template>
     </el-table-column>
     ```
   - script 新增 `useRouter` import 和 `handleViewDevicePanel` 函数：
     ```javascript
     import { useRouter } from 'vue-router'  // 追加到现有 import 行
     const router = useRouter()
     function handleViewDevicePanel(row) {
       router.push({
         name: 'DeviceCards',
         query: { specific_part: row.specific_part, from: 'condensation-warnings' }
       })
     }
     ```

3. **REQ-UI-004（from 参数）**：已包含在上方 `handleViewDevicePanel` 实现中。

---

### MOD-FM — FaultManagementView.vue

**变更点：**

1. **REQ-UI-003（文案）**
   - 第 190 行：`查看设备面板` → `设备面板`

2. **REQ-UI-004（跳转方式）**
   - `handleViewDevicePanel` 函数替换：
     ```javascript
     // 旧（删除）：
     function handleViewDevicePanel(row) {
       const route_resolved = router.resolve({
         name: 'DeviceCards',
         query: { specific_part: row.specific_part },
       })
       window.open(route_resolved.href, '_blank')
     }
     // 新：
     function handleViewDevicePanel(row) {
       router.push({
         name: 'DeviceCards',
         query: { specific_part: row.specific_part, from: 'fault-management' }
       })
     }
     ```

---

### MOD-DC — DeviceCardsView.vue

**变更点：**

1. **REQ-UI-004（goBack 逻辑）**
   - `goBack()` 方法替换：
     ```javascript
     goBack() {
       const from = this.$route.query.from
       if (from === 'fault-management') {
         this.$router.push('/device-management/faults')
       } else if (from === 'condensation-warnings') {
         this.$router.push('/device-management/condensation-warnings')
       } else {
         // from=device-list、无值或未知值：原有逻辑
         if (window.history.length > 1) {
           this.$router.back()
         } else {
           this.$router.push('/device-management/device-list')
         }
       }
     },
     ```

2. **REQ-UI-005-A（按钮样式）**
   - `.panel-page-header` CSS：`padding: 12px 0` → `padding: 12px 16px`
   - 新增 CSS 规则确保两个按钮 min-width:
     ```css
     .panel-header-left .el-button,
     .panel-header-right .el-button {
       min-width: 80px;
     }
     ```

3. **REQ-UI-005-B（Tab 分行）**
   - 计算属性新增 `thermostatTabs` 和 `systemTabs`（从 deviceData 分类）
   - 模板中 `panel-nav-bar` 重构为两行结构：
     ```
     .panel-nav-bar
       .nav-row.nav-row--thermostat   ← 第一行
         .nav-row-header "温控面板" + 历史数据链接
         nav-item × N（4 或 5 个）
       .nav-row-divider
       .nav-row.nav-row--system       ← 第二行
         nav-item × 4（固定）
       加载指示器
     ```
   - 排序逻辑：按白名单数组索引排序，非白名单 subKey 不渲染（保持现有行为）

---

## 4. 接口与路由约定

| 路由名 | path | query 参数 | 说明 |
|--------|------|-----------|------|
| DeviceCards | /device-cards | specific_part（必填）, from（可选） | from 值：fault-management / condensation-warnings |

**from 参数不影响路由匹配**，仅由 `goBack()` 读取，路由定义无需变更。

---

## 5. 约束与风险

| ID | 类型 | 内容 |
|----|------|------|
| C-01 | 约束 | 不改后端，所有分类逻辑在前端白名单实现 |
| R-01 | 风险（低）| 若后端新增非白名单 subKey，该 Tab 在当前分行布局中不会显示；需后续维护白名单 |
| R-02 | 风险（低）| router.push 同标签页跳转会破坏当前页表格过滤状态（返回后重置），与新标签页行为不同；用户已知晓并接受 |
