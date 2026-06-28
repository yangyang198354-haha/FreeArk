<!--
  file: docs/development/v1.11.2_miniapp_room_display/requirements_spec.md
  version: v1.11.2
  feature: miniapp_room_display
  author_agent: sub_agent_requirement_analyst
  created_at: 2026-06-28
  status: DRAFT
-->

# 需求规格说明书 — v1.11.2 小程序温控面板房间名显示

---

## 1. 背景与问题陈述

FreeArk 楼宇智能化系统（三恒空调）的业主端微信小程序提供设备面板页，供业主查看各温控面板的实时参数。  
[SRC: 用户请求 — "FreeArk 是一套楼宇智能化系统（三恒空调），业主端微信小程序让业主查看自己房间的温控面板实时参数"]

**当前问题**：设备面板页（`miniprogram/subpackages/monitor/pages/device-panel.vue`）的各温控面板卡片标题直接渲染后端字段 `sub.display`（对应 `DeviceConfig.sub_type_display`）。当前生产数据库中，该字段值为通用标签（如"末端面板"），导致业主无法区分哪张卡片对应哪个房间。  
[SRC: 用户请求 — "小程序设备面板页把各个房间的温控面板统一显示为通用标签……导致业主无法区分哪个卡片对应哪个房间"]

**对齐目标**：各面板卡片标题应显示具体房间名（书房 / 次卧 / 主卧 / 儿童房），与 Web 端一致。  
[SRC: 用户请求 — "让各面板卡片标题显示具体房间名（书房 / 次卧 / 主卧 / 儿童房），与 Web 端保持一致"]

---

## 2. 目标与范围

### 2.1 目标

| # | 目标 | 来源 |
|---|------|------|
| G1 | 业主在小程序设备面板页看到各温控面板卡片显示具体房间名，而非通用标签 | [SRC: 用户请求] |
| G2 | 4 个温控面板 sub_type 的显示名与下方映射表严格一致，不出现串房 | [SRC: 用户请求 — 关键陷阱说明] |
| G3 | 修改不影响 Web 端现有功能及其他 sub_type 的显示 | [SRC: 用户请求 — 非功能需求部分] |

### 2.2 范围内

- 小程序设备面板页（`device-panel.vue`）的 4 个温控面板卡片标题显示。
- 涉及端点：`GET /api/miniapp/owner/realtime-params/?specific_part=X`。
- 涉及数据字段：`DeviceConfig.sub_type_display`（或其传递链路上的映射层）。

### 2.3 范围外（详见第 6 节）

- `miniprogram/subpackages/control/pages/param-settings.vue`（参数设置页）：经代码核验，该页面不使用 `sub_type_display` 进行房间名渲染（见 OQ-01 已确认结论）。
- Web 端前后端代码（不属于小程序端改动范围）。
- 系统级 sub_type（`main_thermostat`、`fresh_air`、`energy_meter`、`hydraulic_module`、`air_quality`）。

---

## 3. 功能需求（REQ-FUNC-*）

### REQ-FUNC-001 — 温控面板卡片显示具体房间名

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-001 |
| **描述** | 系统应当在小程序设备面板页的每个温控面板卡片标题处，显示该 sub_type 对应的具体房间名，而非通用标签（如"末端面板"）。 |
| **来源引用** | "让各面板卡片标题显示具体房间名（书房 / 次卧 / 主卧 / 儿童房），与 Web 端保持一致" |
| **优先级** | Must Have |
| **备注** | 卡片标题渲染位置：`device-panel.vue` 第 35 行 `{{ sub.display }}`，值来自 `cfg.sub_type_display`（`views_miniapp_device_settings.py` 第 259 行），修改方式由架构师决定。 |

---

### REQ-FUNC-002 — sub_type 与房间名的强制映射关系

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-002 |
| **描述** | 系统应当确保 4 个温控面板 sub_type 与房间名的对应关系严格符合以下映射表，不得串房。 |
| **来源引用** | "小程序后端 sub_type 命名（带 `panel_` 前缀）" + "关键陷阱（必须在需求文档中明确记录）" |
| **优先级** | Must Have |
| **备注** | 见下方映射表与陷阱说明，这是本版本最高风险需求。 |

#### 目标映射表（强制执行，不得调换）

| sub_type（小程序/后端） | 目标显示名 | 语义说明 | 当前 seed 值（含后缀）| 验证来源 |
|------------------------|-----------|---------|---------------------|---------|
| `panel_study_room` | **书房** | 三房次卧 / 四房书房 | `'书房-温控面板'` | `seed_device_config.py` 第 131 行 |
| `panel_bedroom` | **次卧** | 三房主卧 / 四房次卧 | `'次卧-温控面板'` | `seed_device_config.py` 第 221 行 |
| `panel_children_room` | **主卧** | 三房儿童房 / 四房主卧 | `'主卧-温控面板'` | `seed_device_config.py` 第 311 行 |
| `panel_fourth_children` | **儿童房** | 四房专属儿童房 | `'儿童房-温控面板'` | `seed_device_config.py` 第 401 行 |

#### ⚠ 关键陷阱说明（开发阶段必须参照，防止串房）

> 以下映射在代码命名层面存在反直觉性，历史上曾引发混淆，须在实现前明确确认：

1. `panel_bedroom` → **次卧**（不是主卧）  
   代码名"bedroom"直译为"卧室/主卧"，但实际 display 值为"次卧"。  
   [SRC: "panel_bedroom → 次卧（不是主卧）"]

2. `panel_children_room` → **主卧**（不是儿童房）  
   语义来自三房户型中"儿童房"在四房户型对应主卧的空间关系；display 值为"主卧"。  
   [SRC: "panel_children_room → 主卧（不是儿童房，语义来自三房户型…）"]

3. `panel_fourth_children` → **儿童房**（四房户型专属，不出现在三房户型）  
   [SRC: "panel_fourth_children → 儿童房（四房户型专属儿童房）"]

4. 映射权威来源：`FreeArkWeb/backend/freearkweb/api/utils_room_filter.py` 顶部注释 + `SUB_TYPE_TO_ROOM_KEYWORDS`。  
   [SRC: "这一映射来源：`utils_room_filter.py` 顶部注释 + `SUB_TYPE_TO_ROOM_KEYWORDS`"]

---

### REQ-FUNC-003 — 户型不含某房间时无需 Fallback 显示

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-003 |
| **描述** | 系统应当在特定专有部分（`specific_part`）不含某个房间时，不返回对应 sub_type 的数据；小程序端无需处理"找不到房间"的 fallback 情况。 |
| **来源引用** | "如果 specific_part 对应的户型不含某个房间，该 sub_type 不会被返回（由 `get_available_sub_types()` 过滤），需求中不需要处理'找不到房间'的 fallback（这是现有逻辑，只需确认）" |
| **优先级** | Must Have |
| **备注** | 这是对现有逻辑（`get_available_sub_types()` 过滤）的确认性需求，非新增功能。v1.11.2 不需要修改该过滤逻辑。 |

---

### REQ-FUNC-004 — 参数设置页不在本次范围内（已确认）

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-004 |
| **描述** | 系统应当确认参数设置页（`param-settings.vue`）不依赖 `sub_type_display` 进行房间名渲染；v1.11.2 无需对该页面进行任何修改。 |
| **来源引用** | "参数设置页 `miniprogram/subpackages/control/pages/param-settings.vue` 也按 sub_type 渲染，可能同样受影响" |
| **优先级** | Must Have（确认性） |
| **备注** | 代码核验结论（见 OQ-01 已确认）：param-settings.vue 区域一（"我的房产"）使用 `resolveRoomName(room)` 读 `device_room.room_name`（第 842 行），区域二（参数设置写链路）使用 `product_code_role` 映射（第 344 行）。两者均不使用 `sub_type_display`，不受本次问题影响，不在 v1.11.2 范围内。 |

---

## 4. 非功能需求（REQ-NFUNC-*）

### REQ-NFUNC-001 — Web 端功能零影响

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-001 |
| **描述** | 系统应当确保 v1.11.2 的改动不影响 Web 端现有的设备卡片显示、历史查询或任何其他功能。 |
| **来源引用** | "非功能需求：显示名更新不应影响 Web 端现有功能" |
| **优先级** | Must Have |
| **备注** | Web 端实时参数使用 `views.py` 第 1870 行的独立视图（`'display': cfg.sub_type_display`），与小程序端视图 `views_miniapp_device_settings.py` 第 259 行分离。实现时需确认两者是否共享同一数据源，若共享则方案需向上评审。 |

### REQ-NFUNC-002 — 其他 sub_type 显示不受影响

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-002 |
| **描述** | 系统应当确保 v1.11.2 的改动仅影响 4 个温控面板 sub_type（`panel_study_room`、`panel_bedroom`、`panel_children_room`、`panel_fourth_children`），不改变系统级 sub_type（`main_thermostat`、`fresh_air`、`energy_meter`、`hydraulic_module`、`air_quality`）的显示名称。 |
| **来源引用** | "非功能需求：不应影响其他 sub_type（如 main_thermostat / fresh_air）" |
| **优先级** | Must Have |
| **备注** | 系统级 sub_type 当前 seed 值分别为"主温控"/"新风"/"能耗表"/"水力模块"/"空气品质"，不在修改范围内。 |

### REQ-NFUNC-003 — 业主权限边界不变

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-003 |
| **描述** | 系统应当确保 v1.11.2 的改动不突破业主用户（`role=user`）的现有权限边界；业主仍仅通过 `/api/miniapp/owner/` 专属端点访问设备数据。 |
| **来源引用** | "小程序业主读数据走 `/api/miniapp/owner/` 专属端点（`IsOwnerUser` + `OwnerUserBinding` 归属过滤）；不可走 `/api/devices/*`" |
| **优先级** | Must Have |
| **备注** | 无需新增或调整权限配置，此为约束性需求。 |

### REQ-NFUNC-004 — 改动不引入新数据端点

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-004 |
| **描述** | 系统应当在现有 `/api/miniapp/owner/realtime-params/` 端点的响应结构内解决显示名问题，不应为此需求新增 API 端点。 |
| **来源引用** | "数据端点：`GET /api/miniapp/owner/realtime-params/?specific_part=X`" + 工作范围约束 |
| **优先级** | Should Have |
| **备注** | [INFERRED — requires PM confirmation] 此为倾向性约束，具体实现方案（DB 更新 vs 后端映射层 vs 前端映射）由架构师决定。 |

---

## 5. 约束与假设

### 5.1 技术约束（已由代码核验确认）

| # | 约束内容 | 来源 |
|---|---------|------|
| C1 | 小程序面板页卡片标题渲染点：`device-panel.vue` 第 35 行 `{{ sub.display }}` | [SRC: `device-panel.vue` 代码核验] |
| C2 | `sub.display` 值来源：后端 `views_miniapp_device_settings.py` 第 259 行 `'display': cfg.sub_type_display` | [SRC: `views_miniapp_device_settings.py` 代码核验] |
| C3 | `sub_type_display` 字段定义：`models.py` 第 380 行 `CharField(max_length=100)` | [SRC: `models.py` 代码核验] |
| C4 | 户型过滤由 `get_available_sub_types()` 在 `utils_room_filter.py` 执行，已有逻辑，v1.11.2 不修改 | [SRC: 用户请求 — 兼容性需求] |
| C5 | 业主端专属端点权限：`IsOwnerUser` + `OwnerUserBinding` 归属过滤，不可走 `/api/devices/*` | [SRC: 用户请求 — 权限背景] |

### 5.2 假设

| # | 假设内容 | 风险 |
|---|---------|------|
| A1 | `panel_study_room`/`panel_bedroom`/`panel_children_room`/`panel_fourth_children` 的目标显示名（书房/次卧/主卧/儿童房）已由 PM 确认，与业务方达成一致 | 若业务方有不同命名，需重新对齐 |
| A2 | 生产环境 `DeviceConfig` 表中存在上述 4 个 sub_type 的记录（或将通过某种方式确保记录存在） | 若记录缺失，任何方案均无法生效 |
| A3 | `specific_part` 对应的户型不含某房间时，后端不返回该 sub_type 数据（已由现有 `get_available_sub_types()` 逻辑保障） | 已确认，无风险 |

---

## 6. 范围外（Out of Scope）

| # | 内容 | 原因 |
|---|------|------|
| OOS-1 | `miniprogram/subpackages/control/pages/param-settings.vue` 任何修改 | 代码核验确认该页面不使用 `sub_type_display`（区域一用 `device_room.room_name`，区域二用 `product_code_role`），不受本次问题影响 |
| OOS-2 | Web 端代码修改 | Web 端已正确显示房间名，不在小程序需求范围内 |
| OOS-3 | 系统级 sub_type 的显示名修改（`main_thermostat`、`fresh_air` 等） | 不在本版本范围，当前值已正确 |
| OOS-4 | 新增 `/api/miniapp/owner/` 下的新 API 端点 | 不需要新端点，应在现有端点内解决 |
| OOS-5 | 户型过滤逻辑（`get_available_sub_types()`）修改 | 现有逻辑正确，无需变更 |
| OOS-6 | 历史参数查询页、能耗查询页等其他小程序页面 | 超出本版本范围 |
| OOS-7 | 架构决策：是通过 DB 更新、后端 API 映射层还是前端映射实现 | 留给 system_architect 子代理决定 |

---

## 7. 待确认开放问题（OQ-*）

### OQ-01 — 参数设置页不受影响（已自确认，状态：CLOSED）

**问题**：`param-settings.vue` 是否也使用 `sub.display` 类似字段导致同样问题？  
**确认方式**：代码核验（2026-06-28）  
**结论**：param-settings.vue 不受影响，不在 v1.11.2 范围内。  
- 区域一（我的房产）：`resolveRoomName(room)` → `room.room_name`（来自 `device_room` 表，`param-settings.vue` 第 842 行）
- 区域二（参数设置写链路）：`roleMap[d.productCode]` → `product_code_role` 配置（第 344 行）
**状态**：CLOSED（无需 PM 确认）

---

### OQ-02 — 生产环境 sub_type_display 当前实际值（状态：OPEN）

**问题**：PM 描述生产 DB 中 `sub_type_display` 当前为通用标签"末端面板"，但 seed 代码（`seed_device_config.py`）中已有含房间名的值（如"书房-温控面板"）。两者不一致——请确认：
1. 生产 DB 当前是否真的为"末端面板"（而非 seed 值）？
2. 还是生产 DB 已运行过 seed、当前值为"书房-温控面板"但业主仍反映显示有误？

**影响**：影响架构师设计具体修复路径（seed 重跑 vs DB 直接更新 vs 其他方案）。  
**状态**：OPEN — 请 PM 核实后答复。

---

### OQ-03 — Web 端与小程序端是否共用同一 sub_type_display 数据源（状态：OPEN）

**问题**：Web 端实时参数视图（`views.py` 第 1870 行）和小程序端视图（`views_miniapp_device_settings.py` 第 259 行）均读取 `cfg.sub_type_display`，共享 `DeviceConfig` 同一张表。若修改 DB 字段值，则 Web 端和小程序端将同时受影响——请确认这是否可接受？  
**影响**：若 Web 端已有独立的显示名覆盖机制，则 DB 修改可能无影响；若 Web 端直接使用 DB 值，则需确认 Web 端当前值是否已正确。  
**状态**：OPEN — 请 PM / 架构师确认。

---

### OQ-04 — 目标显示名是否需要保留"-温控面板"后缀（状态：OPEN）

**问题**：seed 代码中 sub_type_display 为"书房-温控面板"（含后缀），目标需求要求显示为"书房"（不含后缀）。是否确认目标为**去掉后缀**，显示纯房间名？  
**影响**：决定修改范围（去后缀 vs 全量替换）。  
**建议**：根据 Web 端 ROOM_TABS 对齐（书房/次卧/主卧/儿童房，无后缀），建议目标为纯房间名。  
**状态**：OPEN — 请 PM 确认。

---

*文档结束 — 共 4 条功能需求，4 条非功能需求，1 条 [INFERRED]（REQ-NFUNC-004），4 条开放问题（1 已关闭，3 待确认）*
