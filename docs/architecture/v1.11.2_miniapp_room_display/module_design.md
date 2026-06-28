<!--
  file: docs/architecture/v1.11.2_miniapp_room_display/module_design.md
  version: v1.11.2
  feature: miniapp_room_display
  author_agent: sub_agent_system_architect
  created_at: 2026-06-28
  status: DRAFT
  input_refs:
    - docs/development/v1.11.2_miniapp_room_display/requirements_spec.md (PM confirmed APPROVED)
    - docs/development/v1.11.2_miniapp_room_display/user_stories.md (PM confirmed APPROVED)
    - ADR-1120-01: 选定 Option A（后端 miniapp 视图内存映射）
-->

# 模块设计说明书 — v1.11.2 小程序温控面板房间名显示

---

## 1. 模块总览

| MOD-ID | 模块名 | 文件路径 | 层级 | 变更类型 | 职责 | 依赖于 |
|--------|------|---------|------|---------|------|------|
| MOD-1120-BE | miniapp_realtime_params_view | `api/views_miniapp_device_settings.py` | API 视图层 | **修改** | 组装小程序业主实时参数 API 响应，新增面板 sub_type 显示名覆写 | MOD-1120-RO-01, MOD-1120-RO-02 |
| MOD-1120-RO-01 | room_filter_util | `api/utils_room_filter.py` | 工具层 | 只读依赖，不修改 | 根据 specific_part 过滤可用 sub_type 集合 | MOD-1120-RO-02 |
| MOD-1120-RO-02 | DeviceConfig model | `api/models.py:380` | 数据模型层 | 只读依赖，不修改 | 提供 DeviceConfig ORM 对象（含 sub_type, sub_type_display 字段）| 无 |
| MOD-1120-RO-03 | device-panel view | `miniprogram/subpackages/monitor/pages/device-panel.vue` | 前端展示层 | 只读依赖，不修改 | 渲染温控面板卡片，消费 sub.display 字段 | MOD-1120-BE（API 端点） |

---

## 2. 修改模块详情

---

### MOD-1120-BE：miniapp 实时参数视图

**文件**：`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`

**职责**：处理 `GET /api/miniapp/owner/realtime-params/?specific_part=X` 请求，过滤并组装业主绑定专有部分的设备实时参数响应。v1.11.2 新增：在响应组装阶段，对 `panel_*` sub_type 的 `display` 字段应用纯房间名覆写。

**覆盖需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-NFUNC-002, US-01, US-02, US-03

---

#### 2.1 新增常量定义规格

**插入位置**：文件顶部导入区之后，视图类/函数定义之前（建议紧接模块级常量区，与文件内其他常量保持风格一致）。

**常量内容**（映射设计规格）：

```python
# 小程序端温控面板 sub_type → 纯房间名（不含"-温控面板"后缀）
# 来源：utils_room_filter.py SUB_TYPE_TO_ROOM_KEYWORDS 注释 +
#        Web RoomHistoryView.vue ROOM_TABS 对照
# ⚠ 注意：panel_bedroom → 次卧（非主卧），panel_children_room → 主卧（非儿童房）
#   此反直觉映射已由业务方最终确认（REQ-FUNC-002 陷阱说明，2026-06-28）
PANEL_DISPLAY_MAP: dict[str, str] = {
    'panel_study_room':      '书房',
    'panel_bedroom':         '次卧',   # ⚠ 非"主卧"
    'panel_children_room':   '主卧',   # ⚠ 非"儿童房"
    'panel_fourth_children': '儿童房',
}
```

**关键约束**：
- 必须严格按上表 4 个键值对定义，不得增删或调换值。
- `panel_bedroom` 的值必须为"次卧"（不是"主卧"）。
- `panel_children_room` 的值必须为"主卧"（不是"儿童房"）。
- 注释必须保留，作为下次维护的防串房提示。

---

#### 2.2 覆写逻辑修改规格

**修改位置**：`views_miniapp_device_settings.py` 第 257-261 行（当前代码）：

当前代码：
```
result[group_key]['sub_types'][sub_key] = {
    'display': cfg.sub_type_display,     ← 第 259 行，待修改
    'params': [],
}
```

修改后（单行变更）：
```
result[group_key]['sub_types'][sub_key] = {
    'display': PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display),   ← 覆写逻辑
    'params': [],
}
```

**变量说明**：
- `sub_key`：当前循环中的 `cfg.sub_type`，即 sub_type 字符串（如 `'panel_study_room'`）。
- `PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)`：
  - 若 `sub_key` 在 map 中（4 个 panel sub_type）→ 返回对应纯房间名。
  - 若 `sub_key` 不在 map 中（系统级 sub_type 如 `'main_thermostat'`）→ fallback 返回 `cfg.sub_type_display`（DB 原始值），行为与修改前完全一致。

---

#### 2.3 接口契约

本次修改不变更 API 端点路径、请求参数、响应结构，仅修改响应体中 `display` 字段的值。

**端点**（不变）：`GET /api/miniapp/owner/realtime-params/?specific_part={specific_part}`

**请求（不变）**：
```
Query params: specific_part: string (必填)
Headers: Authorization: Token <owner_token>
```

**响应结构（不变，仅 display 字段值改变）**：

```
Response 200 OK:
{
  "<group_key>": {
    "display": string,           // group 显示名，不变
    "sub_types": {
      "<sub_key>": {
        "display": string,       // ← 本次修改：panel_* sub_type 由 DB 值 → 纯房间名
        "params": [
          {
            "param_name": string,
            "display_name": string,
            "value": number | string | null,
            "collected_at": string | null,
            "is_stale": boolean
          }
        ]
      }
    }
  }
}
```

**display 字段值变化对照（IFC-1120-01）**：

| sub_key | 修改前 display 值（DB 原始值） | 修改后 display 值 | 来源 |
|---------|--------------------------|----------------|------|
| `panel_study_room` | "书房-温控面板" | **"书房"** | PANEL_DISPLAY_MAP |
| `panel_bedroom` | "次卧-温控面板" | **"次卧"** | PANEL_DISPLAY_MAP |
| `panel_children_room` | "主卧-温控面板" | **"主卧"** | PANEL_DISPLAY_MAP |
| `panel_fourth_children` | "儿童房-温控面板" | **"儿童房"** | PANEL_DISPLAY_MAP |
| `main_thermostat` | "主温控"（DB 值） | "主温控"（不变）| fallback: cfg.sub_type_display |
| `fresh_air` | "新风"（DB 值） | "新风"（不变）| fallback: cfg.sub_type_display |
| `energy_meter` | "能耗表"（DB 值） | "能耗表"（不变）| fallback: cfg.sub_type_display |

---

#### 2.4 不变量保证

| 不变量 | 保证机制 |
|--------|---------|
| 系统级 sub_type display 不变 | `PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)` fallback：map 中仅有 4 个 `panel_*` 键，系统级 sub_type 均不在 map 中，自动返回 DB 原值 |
| Web 端不受影响 | `PANEL_DISPLAY_MAP` 定义于 `views_miniapp_device_settings.py`，不被 `views.py` 引用；`views.py:1870` 独立读 `cfg.sub_type_display` |
| 响应结构不变 | 仅 display 字段值变更，JSON 键名和结构不变；前端 `device-panel.vue` 消费逻辑零改动 |
| 户型过滤逻辑不变 | `get_available_sub_types()` 在覆写逻辑之前执行（第 252-253 行），本次不触及 |
| 无新 migration | `DeviceConfig` 表结构不变，DB 字段不变 |

---

## 3. 只读依赖模块说明

### MOD-1120-RO-01：room_filter_util（utils_room_filter.py）

**角色**：只读依赖，v1.11.2 不修改。

该模块提供 `get_available_sub_types(specific_part)` 函数，在 `MOD-1120-BE` 视图中被调用（第 252 行判断），用于根据户型过滤返回哪些 sub_type。`PANEL_DISPLAY_MAP` 的设计与该文件的 `SUB_TYPE_TO_ROOM_KEYWORDS` 保持键集一致（均为 4 个 panel sub_type），但语义独立——`SUB_TYPE_TO_ROOM_KEYWORDS` 用于过滤决策，`PANEL_DISPLAY_MAP` 用于显示名转换。

**引用关系**：MOD-1120-BE 调用 `get_available_sub_types()` → MOD-1120-RO-01（只读）。

---

### MOD-1120-RO-02：DeviceConfig model（models.py:380）

**角色**：只读依赖，v1.11.2 不修改字段定义，不新增 migration。

提供 `sub_type`（CharField）和 `sub_type_display`（CharField, max_length=100）字段。`PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)` 中 `cfg.sub_type_display` 仅在 fallback 路径使用，DB 值不被写入或修改。

---

### MOD-1120-RO-03：device-panel.vue（前端展示层）

**角色**：只读依赖，v1.11.2 不修改。

渲染逻辑（第 35 行 `{{ sub.display }}`）消费 API 响应中的 `display` 字段。由于 API 响应结构不变（仅字段值改变），前端代码无需任何改动即可正确显示新的房间名。

---

## 4. 数据流图

```
业主小程序 GET /api/miniapp/owner/realtime-params/?specific_part=X
    │
    ▼
UserRoleApiGuardMiddleware（权限中间件，IsOwnerUser + OwnerUserBinding）
    │ 不变
    ▼
OwnersRealtimeParamsView（views_miniapp_device_settings.py）
    │
    ├─► get_available_sub_types(specific_part)    ← utils_room_filter.py（只读）
    │       └─ 返回 available_sub_types: frozenset（如 {'panel_study_room', 'panel_bedroom', ...}）
    │
    ├─► DeviceConfig.objects.filter(device=owner_device)   ← models.py（只读）
    │       └─ 返回 cfg queryset
    │
    └─► for cfg in queryset:
            sub_key = cfg.sub_type           （如 'panel_bedroom'）
            if sub_key not in available_sub_types: continue
            display_name = PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)
            ┌─ sub_key 在 map 中（panel_*）: 返回纯房间名（如"次卧"）
            └─ sub_key 不在 map 中（系统级）: 返回 cfg.sub_type_display（DB 原值）
            result[group_key]['sub_types'][sub_key] = {
                'display': display_name,   ← v1.11.2 修改点
                'params': [...],
            }
    │
    ▼
Response JSON: { group_key: { sub_types: { 'panel_bedroom': { 'display': '次卧', ... } } } }
    │
    ▼
device-panel.vue  {{ sub.display }}   →  渲染"次卧"
```

---

## 5. 依赖关系图

```
MOD-1120-BE（修改）→ MOD-1120-RO-01（调用 get_available_sub_types()）
MOD-1120-BE（修改）→ MOD-1120-RO-02（读取 DeviceConfig queryset）
MOD-1120-RO-03（前端）→ MOD-1120-BE（消费 API 端点响应）
MOD-1120-RO-01 → MOD-1120-RO-02（读取 device_room 数据，现有逻辑）

无循环依赖（已验证）：
  MOD-1120-BE → MOD-1120-RO-01 → MOD-1120-RO-02（单向有向图，无环）
  MOD-1120-RO-03 → MOD-1120-BE（跨层消费，不构成环路）
```

---

## 6. 需求覆盖矩阵

| 需求 ID | 需求描述摘要 | 覆盖模块 | 覆盖机制 |
|--------|------------|---------|---------|
| REQ-FUNC-001 | 小程序显示具体房间名 | MOD-1120-BE | `PANEL_DISPLAY_MAP.get(sub_key, ...)` 返回纯房间名 |
| REQ-FUNC-002 | 4 个 sub_type 强制映射，不串房 | MOD-1120-BE | `PANEL_DISPLAY_MAP` 静态常量，4 个键值对精确一一对应 |
| REQ-FUNC-003 | 不含该房间时不返回对应 sub_type | MOD-1120-RO-01 | `get_available_sub_types()` 现有逻辑（不修改），本次确认不影响 |
| REQ-FUNC-004 | 参数设置页不在本次范围 | MOD-1120-RO-03（不修改）| 参数设置页不读 sub_type_display，零影响已由代码核验确认 |
| REQ-NFUNC-001 | Web 端功能零影响 | MOD-1120-BE | DB 字段不变；`PANEL_DISPLAY_MAP` 仅在 miniapp 视图内存中使用；`views.py` 路径无变化 |
| REQ-NFUNC-002 | 系统级 sub_type display 不受影响 | MOD-1120-BE | fallback 机制：非 panel_* sub_type 返回 `cfg.sub_type_display` 原值 |
| REQ-NFUNC-003 | 业主权限边界不变 | MOD-1120-BE | 不新增端点，不修改权限配置；`IsOwnerUser + OwnerUserBinding` 保持不变 |
| REQ-NFUNC-004 | 不引入新 API 端点 | MOD-1120-BE | 在现有 `/api/miniapp/owner/realtime-params/` 内修改响应组装逻辑 |

---

*文档结束 — 共 4 个模块（1 修改 + 3 只读），1 个接口契约（IFC-1120-01），无循环依赖*
