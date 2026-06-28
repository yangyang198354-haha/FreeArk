<!--
  file: docs/development/v1.11.2_miniapp_room_display/implementation_plan.md
  version: v1.11.2
  feature: miniapp_room_display
  author_agent: sub_agent_software_developer
  created_at: 2026-06-28
  status: DRAFT
  input_refs:
    - docs/development/v1.11.2_miniapp_room_display/requirements_spec.md
    - docs/development/v1.11.2_miniapp_room_display/user_stories.md
    - docs/architecture/v1.11.2_miniapp_room_display/architecture_design.md (ADR-1120-01)
    - docs/architecture/v1.11.2_miniapp_room_display/module_design.md (MOD-1120-BE, IFC-1120-01)
    - docs/architecture/v1.11.2_miniapp_room_display/tech_stack.md
-->

# 实现计划 — v1.11.2 小程序温控面板房间名显示

---

## 1. 实现概述

| 项目 | 内容 |
|------|------|
| 修改文件数 | 1 |
| 变更数量 | 3 处（docstring 更新、常量新增、单行逻辑修改）|
| 新依赖 | 零 |
| 新端点 | 零 |
| DB migration | 零 |
| 前端变更 | 零 |
| 实现依据 | ADR-1120-01（Option A：后端 miniapp 视图内存映射）|

本版本的全部代码变更集中于单个后端文件，按三处独立变更顺序实施，无模块间拓扑依赖（单模块内部变更），无需多步协调。

---

## 2. 模块实现计划

| 序号 | MOD-ID | 模块名 | 文件路径 | 依赖前置模块 | 复杂度 | 状态 |
|------|--------|--------|---------|------------|--------|------|
| 1 | MOD-1120-BE | miniapp_realtime_params_view | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py` | MOD-1120-RO-01（只读，不修改）、MOD-1120-RO-02（只读，不修改）| L | IMPLEMENTED |

---

## 3. 变更清单（变更 1 → 3，按实施顺序）

### 变更 1 — 模块 docstring 更新

| 字段 | 内容 |
|------|------|
| 文件路径 | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py` |
| 变更类型 | 文档更新（docstring） |
| 变更位置 | 文件顶部模块 docstring（原第 1–26 行）|
| 变更摘要 | 1) 标题行追加 `/v1.11.2`；2) 在 v1.11.1 节之后插入 v1.11.2 变更说明段落；3) `@module` 行追加 `MOD-1120-BE`；4) `@implements` 行追加 `REQ-FUNC-001/002（v1.11.2）；REQ-NFUNC-001/002/003/004（v1.11.2）` |
| 实现依据 | MOD-1120-BE 模块标注规范；IFC-1120-01 |

### 变更 2 — 新增 PANEL_DISPLAY_MAP 常量

| 字段 | 内容 |
|------|------|
| 文件路径 | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py` |
| 变更类型 | 新增模块级常量 |
| 变更位置 | `_RESULT_TO_STATUS` 常量之后、`_owner_rooms` 函数之前（原第 55–57 行区间）|
| 变更摘要 | 插入 14 行（含注释 6 行 + 空行 1 行 + 常量定义 7 行）；常量类型注解 `dict[str, str]`，4 个键值对，含 ⚠ 防串房注释 |
| 关键映射（必须精确）| `panel_study_room`→书房、`panel_bedroom`→次卧（非主卧）、`panel_children_room`→主卧（非儿童房）、`panel_fourth_children`→儿童房 |
| 实现依据 | MOD-1120-BE §2.1；ADR-1120-01；REQ-FUNC-002 |

### 变更 3 — 修改 display 字段组装逻辑

| 字段 | 内容 |
|------|------|
| 文件路径 | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py` |
| 变更类型 | 单行逻辑修改 |
| 变更位置 | `miniapp_owner_realtime_params` 函数内，`result[group_key]['sub_types'][sub_key]` dict 初始化处（原第 259 行，变更后行号因变更 2 插入而后移）|
| 变更前 | `'display': cfg.sub_type_display,` |
| 变更后 | `'display': PANEL_DISPLAY_MAP.get(sub_key, cfg.sub_type_display),` |
| 变量关系 | `sub_key = cfg.sub_type`（函数内第 270 行赋值，即循环当前 sub_type 字符串）|
| Fallback 语义 | `sub_key` 不在 map 中时（系统级 sub_type），返回 `cfg.sub_type_display` DB 原值，行为与修改前完全一致 |
| 实现依据 | MOD-1120-BE §2.2；IFC-1120-01；REQ-FUNC-001/002；REQ-NFUNC-002 |

---

## 4. 不变项确认

以下文件和组件经架构确认不受本次变更影响，v1.11.2 一律不修改：

| 不变项 | 路径 / 标识 | 不变原因 |
|--------|-----------|---------|
| Web 端实时参数视图 | `FreeArkWeb/backend/freearkweb/api/views.py:1870` | 独立视图函数，直接读 `cfg.sub_type_display` DB 值，不引用 `PANEL_DISPLAY_MAP` |
| DeviceConfig 模型 | `api/models.py:380` | `sub_type_display` 字段定义不变，不新增字段，不新增 migration |
| 户型过滤工具 | `api/utils_room_filter.py` | `get_available_sub_types()` 已正确过滤 sub_type，不需要修改 |
| 小程序面板页前端 | `miniprogram/subpackages/monitor/pages/device-panel.vue` | 消费 `sub.display` 字段，API 响应结构不变，前端零改动 |
| 参数设置页前端 | `miniprogram/subpackages/control/pages/param-settings.vue` | 不使用 `sub_type_display`（OQ-01 CLOSED），不受影响 |
| DB 数据 | `DeviceConfig.sub_type_display` 字段值 | 映射在 Python 内存层执行，不写回 DB |
| 权限配置 | `IsOwnerUser`、`OwnerUserBinding`、中间件 | 不新增端点，权限配置不变 |
| 所有其他 sub_type | `main_thermostat`、`fresh_air`、`energy_meter`、`hydraulic_module`、`air_quality` | 不在 `PANEL_DISPLAY_MAP` 中，fallback 保持 DB 原值 |

---

## 5. 实现风险

| 风险 | 风险级别 | 缓解措施 | 残余状态 |
|------|---------|---------|---------|
| PANEL_DISPLAY_MAP 映射错误（主要风险：panel_bedroom→次卧 与 panel_children_room→主卧 的反直觉性）| MEDIUM（业务影响高，技术实现简单）| 常量已含 ⚠ 注释，并引用 REQ-FUNC-002 来源；代码评审专项核查映射正确性（AC-02-02/AC-02-03）| 常量注释固化，可接受 |
| 未来新增 panel sub_type 时忘记更新 PANEL_DISPLAY_MAP | LOW | fallback 机制保证新 sub_type 不返回空值（返回 DB 原值），不会崩溃；代码注释说明需同步维护 | 可接受 |
| 代码行号后移导致引用文档中行号偏差 | LOW | 本文档以内容描述为主，不依赖精确行号；生产代码以字符串匹配定位 | 可接受 |

---

## 6. 架构偏差记录

无架构偏差。全部实现严格遵循 ADR-1120-01（Option A），无任何偏离。

---

*文档结束 — 共 1 个修改模块，3 处变更，零新依赖，零架构偏差*
