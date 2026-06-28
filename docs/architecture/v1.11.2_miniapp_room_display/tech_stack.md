<!--
  file: docs/architecture/v1.11.2_miniapp_room_display/tech_stack.md
  version: v1.11.2
  feature: miniapp_room_display
  author_agent: sub_agent_system_architect
  created_at: 2026-06-28
  status: DRAFT
  input_refs:
    - docs/development/v1.11.2_miniapp_room_display/requirements_spec.md (PM confirmed APPROVED)
    - ADR-1120-01: 选定 Option A（后端 miniapp 视图内存映射）
-->

# 技术选型说明书 — v1.11.2 小程序温控面板房间名显示

---

## 1. 技术选型原则

v1.11.2 是一项局部展示修复，技术策略为：**零新依赖，零新端点，零 DB migration，复用现有技术栈**。

所有下表选型均为现有生产环境的延续性复用，不引入任何新技术或新版本。

---

## 2. 技术选型表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| 后端语言 | Python | 现有生产版本（不变） | 现有技术栈；`PANEL_DISPLAY_MAP` 使用内置 dict 类型，O(1) 查找，无需额外模块 | REQ-FUNC-001, REQ-FUNC-002 | 无 | 不升级不降级 |
| Web 框架 | Django + Django REST Framework (DRF) | 现有生产版本（不变） | 修改发生在现有 DRF APIView 子类内部，API 序列化逻辑不变 | REQ-NFUNC-004 | 无 | 不变更版本，不触及 serializer |
| 映射数据结构 | Python 内置 `dict` | 语言内置，无版本 | 静态常量 dict，O(1) key 查找，无运行时副作用，代码可读性高；无需引入枚举库或 JSON 配置文件 | REQ-FUNC-002 | 无 | 4 个 key，完全静态，维护成本极低 |
| 数据库 | MySQL（生产现有）| 现有版本（不变） | DB 字段 `sub_type_display` 不修改，不新增 migration，DB 层零变更 | REQ-NFUNC-001 | 无 | 无 migration，无 seed 重跑 |
| 小程序前端框架 | Vue 3 + uni-app | 现有版本（不变） | 前端 `device-panel.vue` 不做任何修改；API 响应结构不变，前端零改动即可正确渲染 | REQ-NFUNC-004 | 无 | 前端无任何变更 |
| 权限框架 | DRF IsOwnerUser + OwnerUserBinding | 现有版本（不变） | 现有权限配置完整覆盖业主端读取权限，本次不新增端点，权限配置不变 | REQ-NFUNC-003 | 无 | 不变更权限中间件或权限类 |
| 缓存 | 无新增 | — | `PANEL_DISPLAY_MAP` 是模块级常量，进程启动后驻留内存，无需额外缓存机制；`get_available_sub_types()` 现有进程内缓存逻辑不变 | REQ-FUNC-001 | 无 | 不引入 Redis 新依赖 |

---

## 3. 本次改动技术概要

### 3.1 后端变更

| 变更项 | 详情 |
|--------|------|
| 文件 | `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py` |
| 变更类型 | 新增模块级常量（4 个键值对的 dict）+ 修改第 259 行单行表达式 |
| 新增依赖 | 无 |
| 版本变更 | 无 |
| DB migration | 无 |
| seed 重跑 | 无 |
| API 端点变更 | 无（现有端点 `/api/miniapp/owner/realtime-params/` 不变） |
| 响应结构变更 | 无（仅 panel_* sub_type 的 display 字段值改变） |

### 3.2 前端变更

| 变更项 | 详情 |
|--------|------|
| 文件 | 无任何前端文件变更 |
| 说明 | `device-panel.vue` 不修改；API 响应结构与字段名不变，前端消费逻辑天然兼容 |

### 3.3 数据库变更

| 变更项 | 详情 |
|--------|------|
| Schema 变更 | 无 |
| 数据变更 | 无（`sub_type_display` 字段值保持 DB 原值，映射在 Python 内存层执行）|
| Migration 文件 | 无 |

### 3.4 外部服务/基础设施变更

| 变更项 | 详情 |
|--------|------|
| 新增外部服务 | 无 |
| 新增 API 端点 | 无 |
| 环境变量变更 | 无 |
| systemd/部署配置变更 | 无（代码变更后正常重启 Django 服务即可）|

---

## 4. 技术风险汇总

| 风险等级 | 风险描述 | 影响范围 | 缓解措施 |
|---------|---------|---------|---------|
| Low | `panel_bedroom→次卧`、`panel_children_room→主卧` 的反直觉映射，未来维护者可能误改 | 仅 `PANEL_DISPLAY_MAP` 常量 | 常量注释已标注 ⚠ 警告，并注明来源（REQ-FUNC-002 关键陷阱）；验收测试 AC-02-02/AC-02-03 覆盖此场景 |
| Low | 若未来新增 panel sub_type，需手动维护 `PANEL_DISPLAY_MAP` | `PANEL_DISPLAY_MAP` 常量 | fallback 机制（`cfg.sub_type_display`）保证新 sub_type 不会返回空值；新 sub_type 上线时同步更新 map |
| Low | `PANEL_DISPLAY_MAP` 与 Web 端 `RoomHistoryView.vue ROOM_TABS` 是平行维护的两份映射知识 | 双端展示名一致性 | 本次 4 个值均已与 Web 端 ROOM_TABS 对齐验证；变更映射时须同步检查两处 |
| None | DB 字段 `sub_type_display` | N/A | 不修改，无风险 |
| None | Web 端 `views.py:1870` | N/A | 路径独立，映射不影响该函数 |

**整体风险评估**：Low。本次改动为单文件、单一关注点修复，无新依赖、无结构变更、有 fallback 保护。

---

## 5. 现有技术栈关键版本备案

以下版本信息来自生产环境备案，v1.11.2 不变更这些版本：

| 技术组件 | 在本次改动中的角色 | 版本锁定声明 |
|---------|----------------|-----------|
| Python | 承载 `PANEL_DISPLAY_MAP` dict 常量及覆写逻辑 | 不变更 |
| Django | 提供 ORM（`DeviceConfig.objects.filter`）和视图基类 | 不变更 |
| Django REST Framework | 提供 APIView 及权限类 | 不变更 |
| paho-mqtt 2.1.0 | 与本次改动无直接关联 | 不变更（[存档: freeark-paho-mqtt-version.md]）|
| channels_redis | 与本次改动无直接关联 | 不变更 |
| MySQL | 数据源（`DeviceConfig` 表），只读 | 不变更 |
| uni-app / Vue 3 | 前端小程序框架，零改动 | 不变更 |

---

*文档结束 — 共 7 项技术选型，全部为现有技术栈复用，零新依赖，整体风险 Low*
