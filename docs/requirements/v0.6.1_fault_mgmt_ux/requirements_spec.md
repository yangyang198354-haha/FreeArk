# 需求规格说明书

```
file_header:
  document_id: REQ-SPEC-v0.6.1-FM-UX
  title: 故障管理 UX 调整 — 需求规格说明书
  author_agent: sub_agent_requirement_analyst (via PM Orchestrator, PARTIAL_FLOW)
  project: FreeArk 住宅能耗 / 暖通监控平台
  version: v0.6.1-FM-UX
  created_at: 2026-05-28
  status: DRAFT
  references:
    - docs/requirements/v0.6.0_fault_management/requirements_spec.md
    - FreeArkWeb/frontend/src/components/Layout.vue
    - FreeArkWeb/frontend/src/views/FaultManagementView.vue
    - FreeArkWeb/frontend/src/views/DeviceManagementDeviceListView.vue
    - FreeArkWeb/frontend/src/components/CascadingSelector.vue
    - FreeArkWeb/frontend/src/router/index.js
    - FreeArkWeb/backend/freearkweb/api/views_fault.py
    - FreeArkWeb/backend/freearkweb/api/serializers_fault.py
    - FreeArkWeb/backend/freearkweb/api/models.py (DeviceNode, FaultEvent)
    - FreeArkWeb/backend/freearkweb/api/device_tree_sync.py
    - FreeArkWeb/backend/freearkweb/api/migrations/0022_device_tree_sync.py
    - analysis doc/3-1-702_floor_room_device_list_response分析.md
```

---

## 版本历史

| 版本 | 日期 | 变更摘要 |
|------|------|---------|
| 0.1.0-DRAFT | 2026-05-28 | 初始草稿，基于代码实地调研，含开放问题 OQ-01~OQ-05 |

---

## 1. 背景与动因

### 1.1 版本定位

| 版本 | 主要变更 |
|------|---------|
| v0.6.0-FM | MQTT 故障事件持久化 + 故障管理页面（已生产上线，2026-05-28 BUG-FM-002 修复后数据正常） |
| **v0.6.1-FM-UX** | **故障管理 UX 调整（本版本）** |

### 1.2 需求来源

用户在 v0.6.0-FM 上线后提出 4 条 UX 改进：

1. 故障管理入口从设备列表右上角按钮移入左侧导航"设备管理"子菜单。
2. 故障管理页"房号"搜索控件复用设备列表的 `CascadingSelector`，统一交互。
3. 故障列表"设备SN"列改为显示设备类型名称（如"新风机"）。
4. 页面首次加载默认只看未恢复故障（`is_active=true`）。

### 1.3 约束前提（硬约束，本版本不可突破）

- 不修改 `fault_event` 表 schema（不加列、不加 migration）。
- 不引入新 DB migration，除非需求中明确写明触发条件（见 §3.3 FR-FM-UX-03 中的例外说明）。
- 安全：不引入新权限，所有接口沿用 `IsAuthenticated`。

---

## 2. 代码调研摘要（供架构师参考）

| 调研点 | 实际发现 |
|--------|---------|
| 左侧导航实现 | `Layout.vue`（`FreeArkWeb/frontend/src/components/Layout.vue`），使用 Element Plus `<el-menu>` + `<el-sub-menu>`。"设备管理"子菜单（`index="device-management"`）**已是可展开节点**，当前仅含"设备列表"一个子项（`index="/device-management/device-list"`）。 |
| 设备列表右上角故障管理按钮 | `DeviceManagementDeviceListView.vue` 第 23–29 行，`<el-button type="warning" @click="$router.push({ name: 'FaultManagement' })">故障管理</el-button>`，位于页头右侧。 |
| 路由注册 | `router/index.js`，`/device-management/faults`，名称 `FaultManagement`，已注册，与导航菜单分离，不需要改路由。 |
| 设备列表房号搜索控件 | `CascadingSelector.vue`，楼栋/单元/房号三级联动，数据来自本地静态文件 `building_data.js`（无后端接口）。选中后写入三个 hidden input（`dlBuilding`、`dlUnit`、`dlRoom`）。 |
| 设备列表房号传参方式 | `DeviceManagementDeviceListView.vue` 第 310–319 行：读取 hidden input 拼成 `room_no`，格式为 `{building}` / `{building}-{unit}` / `{building}-{unit}-{room}`（3 段，例 `3-1-702`）。传参键名 `room_no`，调用 `/api/device-management/device-list/`。 |
| 故障 specific_part 格式 | `fault_event.specific_part` 为 4 段格式，例 `3-1-7-702`（楼栋-单元-楼层-房号）。设备列表 `room_no` 为 3 段（楼栋-单元-房号）。**两者格式不同，是本需求最关键的技术差异点**，须在 FR-FM-UX-02 中明确映射规则。 |
| DeviceNode 模型 | 实际模型名为 `DeviceNode`（表 `device_node`），用户简报中称"DeviceTreeNode"系笔误。`DeviceNode.device_sn` 为 `IntegerField`，`FaultEvent.device_sn` 为 `VARCHAR(64)`。JOIN 时需类型转换（`CAST(device_node.device_sn AS CHAR)` 或 Python 层对齐）。`device_name` 字段即设备类型名（"新风机"等）。 |
| DeviceNode 覆盖范围 | `DeviceNode` 数据由 `device_tree_sync.py` 从屏侧 `floor-room-device/list` 接口同步。覆盖度取决于各户是否已执行过同步。**当前生产覆盖度未经实地查证**（见开放问题 OQ-01）。 |
| 故障管理"只看未恢复"当前行为 | `FaultManagementView.vue` 第 196 行：`is_active_only: false`，默认不过滤，显示全部记录（含已恢复）。 |
| 故障管理 API is_active 参数 | `views_fault.py` 第 113–121 行：`is_active` 参数为字符串 `"true"/"false"`，ORM 转布尔，非法值静默忽略。 |

---

## 3. 功能需求

### FR-FM-UX-01：故障管理入口位置变更

**描述**：将"故障管理"从「设备列表」页右上角按钮移除，改为左侧导航栏"设备管理"子菜单的第二个子项。

**当前状态（基于代码调研）**：
- `Layout.vue` 的"设备管理" `<el-sub-menu>` 已是可展开节点，当前仅含`<el-menu-item index="/device-management/device-list">设备列表</el-menu-item>` 一项。
- `DeviceManagementDeviceListView.vue` 页头存在"故障管理"按钮，点击跳转 `FaultManagement` 路由。

**目标状态**：

- `Layout.vue` 的"设备管理" `<el-sub-menu>` 新增子项：
  ```
  设备管理（展开节点，已有）
    ├── 设备列表（已有，index="/device-management/device-list"）
    └── 故障管理（新增，index="/device-management/faults"）
  ```
- `DeviceManagementDeviceListView.vue` 删除页头右侧的"故障管理"按钮（含 `<el-button>` 及其父容器 `justify-content: space-between` 布局，若删除按钮后布局可简化则一并简化）。

**约束**：
- 路由 `/device-management/faults`（名称 `FaultManagement`）**不变**，仅增加导航菜单入口。
- 不修改 `FaultManagementView.vue` 的路由注册。
- 导航菜单的激活高亮逻辑（`activeMenu = router.currentRoute.value.path`）已可正确匹配 `/device-management/faults`，无需改动。

**验收标准**：见 `user_stories.md` US-FM-UX-01。

---

### FR-FM-UX-02：房号搜索控件统一

**描述**：故障管理页的"房号"搜索从独立 `<el-input>` 文本框改为复用 `CascadingSelector` 组件，并在后端实现 3 段 `room_no` 到 4 段 `specific_part` 的映射过滤。

#### 2.1 前端变更

- 移除 `FaultManagementView.vue` 中的 `<el-form-item label="房号"><el-input .../>` 控件及对应的 `filters.specific_part` 文本输入逻辑。
- 引入 `CascadingSelector` 组件（路径 `@/components/CascadingSelector.vue`），配置新的 hidden input id（避免与设备列表的 `dlBuilding/dlUnit/dlRoom` 冲突，建议用 `fmBuilding/fmUnit/fmRoom`）。
- 查询时从 hidden input 读取选中值，构造 `room_no` 参数（格式与设备列表一致：`{building}` / `{building}-{unit}` / `{building}-{unit}-{room}`）。
- 将 `room_no` 传给后端 `fault-events` 接口（新增查询参数 `room_no`，替换原 `specific_part`）。

#### 2.2 后端变更（关键技术点：格式映射）

**背景**：`CascadingSelector` 产生的 `room_no` 为 3 段格式（如 `3-1-702`），而 `fault_event.specific_part` 为 4 段格式（如 `3-1-7-702`，含楼层段）。

**映射规则**：

| 用户选中粒度 | room_no 示例 | 后端过滤逻辑 |
|------------|------------|------------|
| 楼栋级别 | `3` | `specific_part__startswith='3-'` |
| 楼栋+单元 | `3-1` | `specific_part__startswith='3-1-'` |
| 具体房号 | `3-1-702` | `specific_part__endswith='-702'` AND `specific_part__startswith='3-1-'` |

> 说明：`specific_part` 4 段格式为 `{building}-{unit}-{floor}-{room}`。当选中具体房号（`3-1-702`）时，不能直接做 `icontains` 因为 `702` 可能在其他楼层（如 `3-2-7-702`）也存在，需组合前缀 + 后缀匹配以精确定位。架构师可评估是否改用精确等值匹配——如查询 `OwnerInfo` 表获取 `specific_part`（唯一）再做 `specific_part__exact`。

**后端接口变更**：
- 新增查询参数 `room_no`（string，可选），替换原 `specific_part` 参数。
- 保留原 `specific_part` 参数兼容，或在此版本中统一改名（由架构师决策，写入开放问题 OQ-02）。
- 若 `room_no` 未传或为空，不过滤房号（与现有行为一致）。

**约束**：
- `CascadingSelector` 组件本身不修改（复用）。
- 后端过滤逻辑仍使用 Django ORM，不拼接原生 SQL。
- 不依赖后端接口，`building_data.js` 静态数据已包含完整房号树。

**验收标准**：见 `user_stories.md` US-FM-UX-02。

---

### FR-FM-UX-03：设备 SN 替换为设备类型名称

**描述**：故障列表表格中"设备SN"列改为展示设备类型名称（如"新风机"），数据来源于本地 `DeviceNode` 表（实际模型名，对应用户简报中提到的"DeviceTreeNode"）。

#### 3.1 数据来源决策（后端返回 device_name 字段）

**决策**：由后端 API 在响应中直接返回 `device_name` 字段（及兜底字段 `device_type_label`），前端不额外发起请求。

**理由**：
- 故障列表每次查询可返回 20~100 条记录，若前端查设备名则需批量请求设备树接口，增加网络往返和前端复杂度。
- 后端可在序列化时做一次 JOIN（`DeviceNode` 表），直接在响应体注入 `device_name`，前端零改动数据流。
- `DeviceNode` 表已在生产 DB 中存在（migration 0022），JOIN 代价低（小表）。

#### 3.2 JOIN 技术要点

```
DeviceNode.device_sn（IntegerField, int）
FaultEvent.device_sn（CharField, VARCHAR，值如 "21997"）
```

JOIN 时需处理类型差异：
- Python/ORM 层：`DeviceNode.objects.filter(device_sn=int(fault_event.device_sn))`（若 `device_sn` 可安全转 int）。
- 或在 QuerySet 注解中使用 `Cast`。
- 架构师确认最终方案，但需求明确：**JOIN Key 为 device_sn，按值相等匹配（FaultEvent.device_sn 转 int 后等于 DeviceNode.device_sn）**。

注意：`DeviceNode` 的唯一约束是 `(room_id, device_sn)`，而非全局 `device_sn` 唯一。同一 `device_sn` 在不同 `OwnerInfo`（不同住户）下可能存在多条记录。JOIN 时需结合 `FaultEvent.specific_part` 通过以下路径缩小范围：

```
FaultEvent.specific_part
  → OwnerInfo.specific_part（exact match）
  → OwnerInfo.id → DeviceFloor.owner_id → DeviceFloor.id
  → DeviceRoom.floor_id → DeviceRoom.id
  → DeviceNode.room_id + DeviceNode.device_sn = int(FaultEvent.device_sn)
  → DeviceNode.device_name（目标字段）
```

此路径为 4 次关联，建议在序列化层或 SQL 层实现，由架构师确认（开放问题 OQ-03）。

#### 3.3 关于 DB Migration 的例外说明

本版本原则上不引入新 DB migration。但若架构师评估后认为需要在 `FaultEvent` 上增加冗余字段（如 `device_name_cached`）以避免运行时 JOIN，则须在需求变更请求中说明，并更新本文档。**当前需求不要求此方案**，明确以运行时 JOIN 为主路径。

#### 3.4 兜底策略（三级降级）

| 优先级 | 条件 | 显示内容 |
|--------|------|---------|
| 主路径 | `DeviceNode` 中找到对应 `device_sn` 记录 | `device_name`（如"新风机"） |
| 兜底一 | `DeviceNode` 无记录，但 `product_code` 已知 | `product_code` 的友好名（后端维护映射表，如 `270001 → 水力模块`）|
| 兜底二 | `product_code` 也无友好名 | 原始 `device_sn` + 角标"未识别"（前端渲染）|

**后端接口变更**：
- `FaultEventSerializer` 新增只读字段：`device_name`（string or null）、`device_type_label`（string or null，兜底一的产物）。
- 前端"设备SN"列改为优先显示 `device_name`，其次 `device_type_label`，兜底显示 `device_sn + "（未识别）"`。
- 原 `device_sn` 字段仍在响应中保留（不删除，供调试和历史兼容）。

**现有历史数据兼容**：
- `fault_event` 表中 v0.6.0-FM 上线后已写入的历史记录，其 `device_sn` 值不变。
- 新字段通过运行时 JOIN 计算，与写入时间无关，历史数据同样能正确映射。

**验收标准**：见 `user_stories.md` US-FM-UX-03。

---

### FR-FM-UX-04：默认筛选"只看未恢复"

**描述**：故障管理页首次加载默认过滤 `is_active=true`，仅显示活跃中（未恢复）的故障记录。

**当前状态**：
- `FaultManagementView.vue` 第 196 行 `is_active_only: false`，默认显示全部记录。
- 页面顶部有 `<el-switch>` 控件标注"只看未恢复/显示全部"。

**目标状态**：

1. **默认值变更**：`is_active_only` 初始值改为 `true`（页面加载时 switch 默认处于"只看未恢复"激活态）。
2. **URL 参数优先**：若 URL 中携带 `is_active` 参数（`?is_active=false` 或 `?is_active=true`），以 URL 参数为准，覆盖前端默认值。URL 未携带时默认 `true`。
3. **三态控件（替代现有 toggle）**：现有 `<el-switch>` 为二态（只看未恢复 / 显示全部），不支持"只看已恢复"的查询。用户可能需要"只看已恢复"（如：查历史恢复记录）。

   **建议**将 switch 升级为三态 `<el-radio-group>`：

   | 选项标签 | is_active 传参 |
   |--------|--------------|
   | 未恢复（默认） | `is_active=true` |
   | 已恢复 | `is_active=false` |
   | 全部 | 不传 `is_active` |

   > **开放问题 OQ-04**：三态控件形态（radio-group / segmented / select）由用户最终确认；此处建议 radio-group。

4. **后端接口**：现有 `is_active` 参数已支持 `true/false/不传`，无需改动后端（views_fault.py 第 114–121 行逻辑已正确）。

**约束**：
- 不修改后端 API。
- URL 参数优先原则在前端 `onMounted` 钩子中解析 `route.query.is_active` 实现。

**验收标准**：见 `user_stories.md` US-FM-UX-04。

---

## 4. 非功能需求

### 4.1 性能

| 指标 | 目标值 | 说明 |
|------|--------|------|
| 故障列表接口 P95 响应时间 | ≤ 800ms | 含 device_name JOIN 后的端到端响应（树莓派 MySQL 9.4 @ 192.168.31.98） |
| device_name JOIN 额外开销 | ≤ 200ms（估算） | DeviceNode 表为小表（行数远小于 fault_event），JOIN 代价低 |
| 前端首次加载（含 is_active=true 默认筛选） | ≤ 3s | 与 v0.6.0-FM 指标一致 |

> P95 ≤ 800ms 是硬性指标。若架构阶段评估 JOIN 超过此阈值，需采用缓存（如 Django `LocMemCache`，TTL 建议 5 分钟）或预计算方案（开放问题 OQ-03）。

### 4.2 兼容性

| 要求 | 说明 |
|------|------|
| 历史数据兼容 | v0.6.0-FM 已写入的 `fault_event` 记录，通过运行时 JOIN 可正确显示 `device_name`，不依赖写入时间 |
| fault_event schema 不变 | 不增删 `fault_event` 字段，不新建 migration（见 §3.3 例外说明） |
| CascadingSelector 组件不变 | 仅复用，不修改组件内部逻辑 |

### 4.3 安全

| 要求 | 说明 |
|------|------|
| 权限 | 所有接口沿用 `IsAuthenticated`，不引入新权限 |
| ORM 安全 | `room_no` 拆分后通过 ORM 参数化查询，不拼接原生 SQL |

---

## 5. 依赖与假设

### 5.1 依赖

| 依赖项 | 类型 | 说明 |
|--------|------|------|
| `DeviceNode` 表（`device_node`） | DB 依赖 | 已存在（migration 0022），含 `device_sn`（int）、`device_name` 字段 |
| `CascadingSelector.vue` | 前端组件依赖 | 已存在，可直接复用 |
| `building_data.js` | 前端静态数据 | 包含楼栋/单元/房号全量数据，CascadingSelector 依赖此文件 |
| `OwnerInfo` 表 | DB 依赖（间接） | JOIN 路径中需要，用于 specific_part → 设备树的关联 |

### 5.2 假设

| 编号 | 假设内容 |
|------|---------|
| A-01 | `DeviceNode.device_sn`（int）与 `FaultEvent.device_sn`（varchar，值为整数字符串如"21997"）在值上一一对应，int 转换安全 |
| A-02 | `building_data.js` 中的房号数据与生产环境 `specific_part` 前三段（楼栋-单元-房号）一致，CascadingSelector 选出的房号可用于 specific_part 过滤 |
| A-03 | 左侧导航"设备管理"已有 `unique-opened` 属性，添加新子项不影响其他子菜单收起行为 |

---

## 6. 开放问题清单（最多 5 条，需用户裁决）

| 编号 | 问题描述 | 影响范围 | 建议选项 |
|------|---------|---------|---------|
| **OQ-01** | `DeviceNode` 表在生产数据库的覆盖度如何？即：有多少个 `device_sn` 已被同步到 `device_node`，占 `fault_event` 中出现的 `device_sn` 集合的比例？若覆盖度低，兜底策略的重要性显著上升。 | FR-FM-UX-03 主路径可用性 | 请在生产 DB 运行 `SELECT COUNT(DISTINCT device_sn) FROM fault_event` vs `SELECT COUNT(DISTINCT device_sn) FROM device_node`，由用户评估接受度 |
| **OQ-02** | 后端 `fault-events` 接口的房号参数：是将 `specific_part` 改名为 `room_no`，还是同时支持两个参数（`room_no` 新增，`specific_part` 保留兼容）？ | FR-FM-UX-02 后端接口设计，API 兼容性 | 建议：新增 `room_no` 参数，保留 `specific_part` 参数兼容（两者均传时 `room_no` 优先）；旧版前端若有直链可能，保留兼容更安全 |
| **OQ-03** | DeviceNode JOIN 路径有 4 次关联（FaultEvent → OwnerInfo → DeviceFloor → DeviceRoom → DeviceNode）。架构师是否建议在序列化层批量 JOIN（一次查询），还是采用 `prefetch_related`，还是引入进程内 `device_sn → device_name` 字典缓存（在 `freeark-backend` 进程启动时预加载，TTL=按需刷新）？ | FR-FM-UX-03 实现性能，P95 达标 | 建议：进程内字典缓存（key=int(device_sn), value=device_name），启动时全量加载 DeviceNode，信号/API 触发刷新；规避运行时 JOIN 开销 |
| **OQ-04** | "只看未恢复/已恢复/全部"三态控件的 UI 形态：`<el-radio-group>`（单行三选一）、`<el-segmented>`（Element Plus Plus 组件）还是 `<el-select>` 下拉？现有 toggle switch 是否保留作为兼容，还是直接替换？ | FR-FM-UX-04 前端 UI 实现 | 建议：`<el-radio-group>` 形态清晰，可直接替换现有 switch，无需保留旧 switch |
| **OQ-05** | 兜底一（`product_code` → 友好名）的映射表由谁维护？是在 `fault_consumer/constants.py` 中硬编码（如现有 `FAULT_TYPE_LABELS`），还是新建 DB 表？现有代码中 `SUB_TYPE_LABELS` 已维护了子类型名（如 `living_room_thermostat → 客厅温控面板`），能否直接复用作为兜底 `product_code` 的友好名？ | FR-FM-UX-03 兜底一实现 | 建议：在 `constants.py` 中新增 `PRODUCT_CODE_LABELS` 字典（硬编码），不引入新 DB 表；常量由开发人员维护 |

---

### 裁决记录（2026-05-28）

> 本小节为只读追加记录，原"开放问题清单"原文完整保留于上方，以供溯源。
> 裁决人：项目负责人（用户）；记录人：PM Orchestrator (PARTIAL_FLOW)；日期：2026-05-28。

| 编号 | 裁决结论 | 裁决依据摘要 |
|------|---------|------------|
| **OQ-01** | **直接开发，不再补同步** | 实测生产 DB：`device_node` 全表 6124 行（19 个 distinct device_sn，覆盖 634 个 specific_part）。`fault_event` 当前活跃 467 条中有效记录的 (specific_part, device_sn) 覆盖率 = 465/465 = 100.0%；全部 1490 条历史记录覆盖率 = 682/692 = 98.6%，未覆盖的 10 条 `device_sn ∈ {1,2,3,4,5,6}` 为早期测试脏数据。`fault_event.specific_part` 全部 221 个在 `device_node` 已同步（100%）。脏数据走"未识别"兜底，不做数据清理。 |
| **OQ-02** | **沿用 `specific_part` 作为后端 API 查询参数名，不改名** | 用户明确选择"查询参数用 specific_part"。前端复用设备列表房号搜索控件（`CascadingSelector.vue`，输出 3 段 `room_no` 如 `3-1-702`）后，在前端组装层做格式适配：把 `room_no="3-1-702"` 与楼层段（来自 CascadingSelector 隐藏字段或后续推导）拼为 4 段 `specific_part="3-1-7-702"` 再传给后端 `/api/devices/fault-events/?specific_part=...`。若 4 段拼装信息不可得，降级为：前端把 `room_no` 直接放到 `specific_part` 字段（后端 icontains 模糊匹配仍能命中 `%3-1-702%`）。**架构师必须在 module_design 里明确决策"前端 3 段→4 段拼装"还是"icontains 容错"，并给出理由。** |
| **OQ-03** | **进程内缓存字典，key 用纯 `device_sn`（不带 specific_part）** | 实测同一 `device_sn` 在不同 `specific_part` 下都映射到同一 `device_name`（业务上是设备型号），无歧义。架构要求：Django 进程启动时一次加载 `DeviceNode.objects.values_list('device_sn', 'device_name')` 去重后写入模块级 dict（量级 19 条 distinct，1 MB 都不到）；提供 `get_device_name_by_sn(sn: int) -> str \| None` 纯函数接口；失效策略：60 秒 TTL 自动过期 + 手动 `invalidate_device_name_cache()` 钩子（供未来 `device_tree_sync` 完成后调用，本期不接钩子）；`FaultEventSerializer` 新增 `device_name` 计算字段，O(1) dict 查表，不引入 ORM JOIN。 |
| **OQ-04** | **`<el-radio-group>` 三按钮，直接替换现有 `<el-switch>`** | 三态语义：`未恢复`（`is_active=true`，默认）/ `已恢复`（`is_active=false`）/ `全部`（不传 `is_active` 参数）。URL 参数优先于默认值（FR-FM-UX-04）。 |
| **OQ-05** | **`product_code → 友好名` 映射硬编码在 `api/fault_consumer/constants.py` 的新字典 `PRODUCT_CODE_LABELS`** | 仅作兜底（主路径走 `device_node.device_name`）。本期手工填入已知映射：`{'10016': '自由方舟（主机）', '270001': '水力模块', '130004': '新风机', '250001': '能耗表', '100007': '空气品质', '260001': '主温控', '120003': '温控面板'}`。兜底优先级：`device_name`（来自缓存）→ `PRODUCT_CODE_LABELS[product_code]` → 原 `device_sn` 字符串 + 角标"未识别"。 |

---

## 7. 风险

| 风险编号 | 描述 | 概率 | 影响 | 缓解措施 |
|----------|------|------|------|---------|
| R-01 | `DeviceNode` 覆盖度不足，导致大量记录无法显示设备名，兜底显示大量"未识别" | 中（未经验证，OQ-01） | 中（用户体验差） | 实地查验覆盖度；若低于 80%，考虑触发批量设备树同步，或降低期望并在 UI 给出说明文字 |
| R-02 | `specific_part`（4段）与 `room_no`（3段）格式映射出现边界情况（如同一 3 段前缀对应多个楼层） | 中（楼层段为第三位，存在同楼栋同单元不同楼层） | 低中（过滤结果范围偏大，不影响正确性，仅增加噪音结果） | `specific_part__startswith='3-1-' AND specific_part__endswith='-702'` 可精确到房号，但不排除极端情况；建议架构师评估后确认精确匹配方案 |
| R-03 | 运行时 JOIN 超过 P95=800ms 阈值 | 低（DeviceNode 小表） | 中（NFR 不达标） | 架构阶段优先评估；若超阈值，采用进程内缓存（OQ-03 建议方案）|
