<!--
  file: docs/architecture/v1.11.2_miniapp_room_display/architecture_design.md
  version: v1.11.2
  feature: miniapp_room_display
  author_agent: sub_agent_system_architect
  created_at: 2026-06-28
  status: DRAFT
  input_refs:
    - docs/development/v1.11.2_miniapp_room_display/requirements_spec.md (PM confirmed APPROVED)
    - docs/development/v1.11.2_miniapp_room_display/user_stories.md (PM confirmed APPROVED)
-->

# 架构设计说明书 — v1.11.2 小程序温控面板房间名显示

---

## 1. 问题分析

### 1.1 当前缺陷的根因链路

当前小程序设备面板页（`device-panel.vue`）的卡片标题渲染路径如下：

```
device-panel.vue:35  {{ sub.display }}
        ↑
        由后端 API 响应中 sub_types[key].display 字段填充
        ↑
views_miniapp_device_settings.py:259
        'display': cfg.sub_type_display   ← 直接读取 DB 字段
        ↑
DeviceConfig.sub_type_display（CharField, models.py:380）
        ↑
DB 中实际值来自 seed_device_config.py，含"-温控面板"后缀
（如 panel_study_room → "书房-温控面板"，panel_bedroom → "次卧-温控面板"）
```

根因：`views_miniapp_device_settings.py` 第 259 行直接将 `cfg.sub_type_display` 透传给 API 响应，未经任何显示名转换，导致业主看到的是带"-温控面板"后缀的非纯房间名。

[SRC: REQ-FUNC-001, C2]

### 1.2 关键映射陷阱（最高风险项）

需求文档 REQ-FUNC-002 明确记录了 4 个 sub_type 的业务语义与代码命名之间存在反直觉关系：

| sub_type | 代码命名直译 | 正确目标显示名 | 陷阱描述 |
|----------|------------|-------------|---------|
| `panel_study_room` | 书房 | **书房** | 无陷阱 |
| `panel_bedroom` | 卧室/主卧 | **次卧** | 代码名易误读为"主卧"，实为次卧 |
| `panel_children_room` | 儿童房 | **主卧** | 代码名含 children，实为四房户型的主卧 |
| `panel_fourth_children` | 四号儿童房 | **儿童房** | 四房专属 |

权威来源：`utils_room_filter.py:39-44 SUB_TYPE_TO_ROOM_KEYWORDS` 注释 + `RoomHistoryView.vue ROOM_TABS` 定义。

### 1.3 系统数据路径隔离现状

Web 端与小程序端共享 `DeviceConfig` 表，但使用**完全独立的视图函数**：

- Web 端：`views.py:1870` — `'display': cfg.sub_type_display`（读 DB 原始值）
- 小程序端：`views_miniapp_device_settings.py:259` — `'display': cfg.sub_type_display`（当前直读，待改）

这两条路径在 Python 进程层面相互独立。任何仅在 `views_miniapp_device_settings.py` 内的内存层操作，不会影响 `views.py` 的响应。

[SRC: REQ-NFUNC-001, OQ-03 已答复]

---

## 2. 架构概览

- **架构风格**：现有分层 Django/DRF 单体架构，本次在 API 视图层增加轻量内存映射逻辑。
- **修改范围**：单一文件（`views_miniapp_device_settings.py`），一处常量定义 + 一行覆写逻辑。
- **零新依赖**：不引入新模块、新端点、新 migration。
- **选型依据**：REQ-NFUNC-001（Web 零影响）、REQ-NFUNC-004（不新增端点）、REQ-FUNC-002（映射正确性）。

---

## 3. 架构决策记录（ADRs）

---

### ADR-1120-01：显示名映射层的实现位置

**Status**: Accepted

**Context**:

小程序业主端设备面板页（US-01，US-02）的温控面板卡片标题需从含"-温控面板"后缀的 DB 值转换为纯房间名（书房 / 次卧 / 主卧 / 儿童房）。转换逻辑需要在请求-响应链路上的某个位置注入。涉及需求：REQ-FUNC-001（显示具体房间名）、REQ-FUNC-002（4 个 sub_type 强制映射）、REQ-NFUNC-001（Web 端零影响）、REQ-NFUNC-004（不引入新端点）。

关键约束（PM 已拍板，REQ-NFUNC-001）：禁止修改 `DeviceConfig.sub_type_display` DB 字段，以保证 Web 端天然隔离。

**Options**:

**Option A：后端 miniapp 视图内存映射（推荐）**

- **实现位置**：`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`
- **方式**：在文件顶部定义 `PANEL_DISPLAY_MAP` Python dict 常量，将第 259 行的 `cfg.sub_type_display` 替换为 `PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)`
- **优点**：
  1. DB 字段不变，`views.py:1870` 的 Web 端路径天然不受影响（REQ-NFUNC-001 满足）。
  2. 映射逻辑集中于单一后端文件，前端代码零变更（前端不需要了解 sub_type 语义）。
  3. 通过 fallback 机制（`PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)`），系统级 sub_type（`main_thermostat` 等）自动保持原值（REQ-NFUNC-002 满足）。
  4. 不引入新 API 端点（REQ-NFUNC-004 满足）。
  5. 改动最小（一处常量 + 一行逻辑），回滚成本极低。
- **缺点**：
  1. 映射逻辑存在于后端代码而非前端，若未来有其他客户端消费同一端点，需共同受益（实际上这是优点，但对纯展示逻辑有争议）。
- **风险**：极低。映射 dict 为静态常量，无运行时副作用。

**Option B：前端 device-panel.vue 内 JS 映射**

- **实现位置**：`miniprogram/subpackages/monitor/pages/device-panel.vue`
- **方式**：在 Vue 组件中新增 computed 属性或工具函数，按 sub_type key 对 `sub.display` 进行二次映射。
- **优点**：
  1. 后端不变，前端自主处理展示逻辑，符合"展示逻辑归前端"的 UI 架构风格。
  2. 部署上可独立发布前端包。
- **缺点**：
  1. 业务映射知识（sub_type → 房间名）被分散到前端，与后端 `utils_room_filter.py` 中的 `SUB_TYPE_TO_ROOM_KEYWORDS` 形成知识重复，未来维护时两处需同步变更。[ESTIMATE]
  2. 若未来小程序新增其他使用 sub.display 的页面（如历史查询页），需要再次复制映射逻辑。
  3. `panel_bedroom→次卧`、`panel_children_room→主卧` 的反直觉映射一旦散落前端，Review 时更容易被忽视。
- **风险**：中等。映射知识分散，前后端不一致风险随时间累积。[ESTIMATE]

**Option C：直接更新 DB 中 sub_type_display 字段值（OOS，已排除）**

- **实现位置**：数据库 `DeviceConfig` 表 seed / migration
- **方式**：将 4 个 panel sub_type 的 `sub_type_display` 由"X-温控面板"更新为纯房间名（如"书房"）
- **优点**：
  1. 数据从源头正确，代码层零改动。
- **缺点**：
  1. `views.py:1870` 的 Web 端路径同样读取 `cfg.sub_type_display`，DB 修改会同时影响 Web 端显示名（REQ-NFUNC-001 风险）。需要额外核验 Web 端当前行为是否依赖该后缀格式。
  2. 需要 seed 重跑或手动 SQL，属于数据变更，需要运维操作，变更可逆性差。
  3. PM 已拍板：禁止修改 `sub_type_display` DB 字段（用户约束 C3）。
- **风险**：高。违反 PM 硬约束，OOS。

**Decision**:

选择 **Option A（后端 miniapp 视图内存映射）**。

理由：Option A 是唯一同时满足以下需求的方案：REQ-NFUNC-001（DB 不变 → Web 天然隔离）、REQ-NFUNC-002（fallback 机制 → 系统级 sub_type 自动保持原值）、REQ-NFUNC-004（现有端点内解决）。Option B 的知识分散问题在项目已有 `utils_room_filter.py` 集中管理 sub_type 映射知识的背景下尤其不合适（[KB: KE-ARCH-017]）。Option C 违反 PM 硬约束，直接排除。

**Consequences**:

- **正向**：
  1. 支撑 REQ-FUNC-001：业主看到纯房间名（书房 / 次卧 / 主卧 / 儿童房）。
  2. 支撑 REQ-FUNC-002：4 个 panel sub_type 各自正确，fallback 保护系统级 sub_type（REQ-NFUNC-002）。
  3. 支撑 REQ-NFUNC-001：`views.py` 路径未触及，Web 端天然不受影响。
  4. 支撑 REQ-NFUNC-004：复用现有端点 `/api/miniapp/owner/realtime-params/`，无新端点。
  5. API 响应 JSON 结构不变，前端 `device-panel.vue` 零改动（US-01 至 US-04 均无前端风险）。
- **负向**：
  1. 后端视图文件中引入了显示名映射常量，该常量与 Web 端 `RoomHistoryView.vue ROOM_TABS` 是平行维护的两份知识，未来若房间名需变更，需同步两处。[ESTIMATE — 低频变更，可接受风险]

---

## 4. 系统影响分析

### 4.1 Web 端零影响的技术保证

| 关注点 | 技术机制 | 隔离结论 |
|--------|---------|---------|
| 数据源 | `DeviceConfig` 表 `sub_type_display` 字段不被修改 | Web 端读取到的 DB 值与修改前完全一致 |
| 视图函数 | `views.py:1870` 与 `views_miniapp_device_settings.py:259` 是独立函数，无共享逻辑 | 映射逻辑仅在 miniapp 视图函数的 Python 内存中执行，不影响 Web 视图 |
| API 端点 | Web 端使用 `/api/` 前缀端点，小程序端使用 `/api/miniapp/owner/` 专属端点 | 请求路由相互独立，不存在交叉 |

[SRC: REQ-NFUNC-001, OQ-03 已答复]

### 4.2 参数设置页零影响的技术保证

需求 REQ-FUNC-004 已由代码核验确认（OQ-01 CLOSED）：

- `param-settings.vue` 区域一（我的房产）：读取 `device_room.room_name`（第 842 行），不使用 `sub_type_display`。
- `param-settings.vue` 区域二（参数写链路）：使用 `product_code_role` 配置映射（第 344 行），不使用 `sub_type_display`。

结论：参数设置页与 `sub_type_display` 字段无数据关系，v1.11.2 改动对其零影响。

### 4.3 系统级 sub_type 不受影响的保证

`PANEL_DISPLAY_MAP` 仅包含 4 个 `panel_*` 键。`PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)` 的 fallback 语义保证：对于 `main_thermostat`、`fresh_air`、`energy_meter`、`hydraulic_module`、`air_quality` 等系统级 sub_type（均不以 `panel_` 开头，均不在 map 中），返回值为 `cfg.sub_type_display` 原始 DB 值，行为与修改前完全一致。

[SRC: REQ-NFUNC-002]

---

## 5. 约束验证（REQ-NFUNC-001 ～ REQ-NFUNC-004）

| 需求 ID | 约束描述 | 满足方式 | 满足状态 |
|--------|---------|---------|---------|
| REQ-NFUNC-001 | Web 端功能零影响 | DB 字段不变 + 映射在 miniapp 视图内存层执行，Web 视图路径隔离 | 满足 |
| REQ-NFUNC-002 | 其他 sub_type 显示不受影响 | `PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display)` fallback，系统级 sub_type 不在 map 中 | 满足 |
| REQ-NFUNC-003 | 业主权限边界不变 | 不新增端点，不修改权限配置，`IsOwnerUser + OwnerUserBinding` 过滤保持不变 | 满足 |
| REQ-NFUNC-004 | 不引入新 API 端点 | 在现有 `/api/miniapp/owner/realtime-params/` 端点的响应组装逻辑内修改 | 满足 |

---

## 6. 开放问题

本 ADR 所有决策均有 REQ-* 依据或 PM 拍板约束，无 [ASSUMPTION] 待确认项。

以下条目来自需求文档 OQ-02～OQ-04，PM 已在任务背景中提供最终答复：

| OQ 编号 | 问题 | PM 答复 | 架构影响 |
|--------|------|--------|---------|
| OQ-02 | 生产 DB 实际值 | 不影响方案，映射在 API 响应组装时纯内存覆写 | 无 |
| OQ-03 | Web/小程序是否共用 sub_type_display | Web 端用独立视图，只要不改 DB 字段天然隔离 | 已验证（见 4.1 节）|
| OQ-04 | 是否去后缀 | 确认目标为纯房间名，无"-温控面板"后缀 | 映射值设计为书房/次卧/主卧/儿童房（无后缀）|

---

*文档结束 — 共 1 个 ADR（ADR-1120-01），3 个候选方案，1 个 Accepted 决策*
