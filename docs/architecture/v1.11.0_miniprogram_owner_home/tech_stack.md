**特性**：微信小程序业主端首页 / 房间结构 / 主动刷新 / 缓存
**版本**：v1.11.0_miniprogram_owner_home
**状态**：DRAFT
**日期**：2026-06-27
**作者**：system-architect
**依赖**：`architecture_design.md`（本目录）

---

# 技术选型 — v1.11.0 微信小程序业主端功能迭代

**文档编号**：ARCH-TECH-v1110-001
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-27

---

## 1. 技术选型原则

v1.11.0 为**已有栈内扩展**，不引入新技术类别。所有选型均为现有栈的继承或直接复用，新增 `useMqttClient.js` 模块属于前端工具层扩展，不引入任何新 npm 依赖。

---

## 2. 技术选型表

| 类别 | 选型 | 版本/版次 | Rationale | 关联 REQ-* | 风险 | 备注 |
|------|------|----------|-----------|-----------|------|------|
| **后端语言** | Python | 3.11（生产现有）| 现有栈，无迁移成本 | REQ-NFUNC-004 | 低 | 无变更 |
| **后端框架** | Django + Django REST Framework | 现有版本（4.x / 3.x）| 新视图函数完全沿用 DRF 装饰器范式（`@api_view` / `@permission_classes`） | REQ-NFUNC-004 | 低 | 无版本变更，仅追加视图函数 |
| **权限控制** | `IsOwnerUser`（现有自定义权限类，`api/views.py`）| 现有 | 与全部现有 miniapp 端点一致；`UserRoleApiGuardMiddleware` + `IsOwnerUser` 双层防御 | REQ-NFUNC-004, D-05 | 低 | 不引入新权限类 |
| **归属过滤** | `OwnerUserBinding.objects.filter(user=request.user, active=True)`（ORM 查询，现有范式）| 现有 | 复用 `_owner_rooms()` 范式，维护一致性 | REQ-NFUNC-004, D-05 | 低 | 视图内内联，无新工具类 |
| **房型过滤** | `get_available_sub_types(specific_part)` + `SYSTEM_LEVEL_SUB_TYPES`（`utils_room_filter.py`）| 现有（带 300s 进程缓存）| OQ-A 已确认：panel_* 即房间，此函数已实现分组逻辑，直接复用 | REQ-FUNC-001, D-01 | 低 | 缓存 TTL=300s，设备树同步后 `invalidate_room_filter_cache()` 清缓存；无需修改 |
| **实时参数数据源** | `PLCLatestData`（Django ORM，现有模型）+ `DeviceConfig`（现有）| 现有 | operator 版 `get_device_realtime_params` 已验证该查询路径，新端点直接复用逻辑 | REQ-FUNC-001, REQ-FUNC-004 | 低 | 无新表、无迁移 |
| **device_sn 数据源** | `DeviceNode`（Django ORM，现有模型，`db_table='device_node'`）| 现有 | D-02 确认：`DeviceNode.device_sn`（IntegerField）经 `room__floor__owner__specific_part` 关联路径可达 | REQ-FUNC-003, D-02 | 低 | 额外查询约 ≤50 行，性能可接受 |
| **MQTT broker 连接** | 现有厂端 MQTT broker（`wxs://`），凭证通过 `device-settings/config` 下发 | 现有 | v1.10.0 已建立 MQTT 直连基线（ADR-01/02），本版本仅新增"读"操作，不新增 topic 或权限 | REQ-FUNC-003, REQ-NFUNC-002 | 低 | broker ACL 残余风险已在 OOS-05 接受 |
| **MQTT 客户端库（前端）** | `mqtt.js v4`（现有，`miniprogram/utils/screenMqtt.js` + `uniMqttStream.js`）| 现有 | ScreenMqtt 类已实现 connect/subscribe/publish/waitConfirm，`useMqttClient.js` 在其上封装单例管理层 | REQ-NFUNC-002, D-06 | 低 | 不升级 mqtt.js；uniMqttStream.js 解决了 uni-app 小程序运行环境不兼容问题，无需改动 |
| **前端框架** | uni-app + Vue 3 Composition API | 现有（`@dcloudio/uni-app`）| param-settings.vue 已用 Vue 3 `<script setup>`；新增 composable（useMqttClient.js）为标准 Composition API 模式 | REQ-FUNC-001, REQ-NFUNC-002 | 低 | 无版本变更 |
| **前端状态管理** | Vue `ref/reactive`（组件内）+ 模块级变量（useMqttClient.js MQTT 单例）| 现有 | MQTT 连接对象不可序列化，不适合 Pinia；ADR-1110-04 已评估三种方案，选模块级 | REQ-NFUNC-002, D-06 | 低 | 不引入 Pinia 作为 MQTT 管理层；现有 Pinia auth store 不受影响 |
| **本地缓存** | `uni.getStorageSync` / `uni.setStorageSync`（uni-app 内置 API）| 现有 | 微信小程序原生键值存储；单条 ≤5KB，总量 ≤50KB，远低于 10MB 上限（REQ-NFUNC-003 估算）；同步读写满足即时渲染要求（ADR-1110-06）| REQ-FUNC-004, REQ-NFUNC-003, D-03 | 低 | TTL=5min 仅影响 UI 提示；不实现 LRU（当前绑定数估算不超上限） |
| **HTTP 客户端（前端）** | 现有 `http.js`（封装 uni.request）| 现有 | 所有新 API 调用经 `api.js` 追加项，沿用 `http.get/http.post` | REQ-FUNC-001, REQ-FUNC-003 | 低 | 无变更 |
| **API 认证（前端）** | `Authorization: Token <key>`（DRF Token 认证，现有）| 现有 | 业主登录后 token 存于 Pinia auth store，`http.js` 自动追加 header | REQ-NFUNC-004 | 低 | 无变更 |
| **页面滚动** | `uni.pageScrollTo`（uni-app 内置）| 现有 | "去设置"点击后滚动到参数设置区（`#param-settings-anchor` 选择器），无需第三方库 | REQ-FUNC-002, D-07 | 低 | 需确认 scroll-view 嵌套层级对 pageScrollTo 的兼容性（开发期验证项）|

---

## 3. 不引入的技术（及原因）

| 候选技术 | 不引入原因 |
|---------|-----------|
| 新 npm 依赖（任何）| 本版本为已有栈内扩展，`useMqttClient.js` 仅依赖现有 `screenMqtt.js` 和 Vue 内置 API，无需新包 |
| Pinia（作为 MQTT 状态管理）| MQTT 连接对象不可序列化，ADR-1110-04 已评估并排除 |
| WebSocket 直连（替代 MQTT）| v1.10.0 已确立 MQTT 直连方案（ADR-01/02），本版本继承，不重新评估 |
| IndexedDB / 复杂本地存储方案 | 缓存体积极小（≤50KB），`uni.getStorageSync` 足够；IndexedDB 在小程序环境不可用 |
| 新 Django app 或新数据库表 | 所有变更为现有模型/表的查询，无数据模型变更，无迁移（REQ-NFUNC-004 不需要新表）|
| 后端实时推送（Server-Sent Events / DRF Channels）| 主动刷新路径 A 使用现有 MQTT 直连；路径 B 使用 polling（5s delay + re-fetch），无需后端长连接新机制 |

---

## 4. 技术风险汇总

### 高风险（High）

无高风险项。v1.11.0 为已有栈内扩展，不引入新技术类别。

### 中风险（Medium）

| 风险 | 受影响需求 | 缓解措施 |
|------|-----------|---------|
| **MQTT 单例引用计数误差**：若 acquire/release 调用不配对（如 onUnload 未执行），可能导致连接泄露（_refCount > 0 但无组件在用）或提前断开（_refCount < 0）| REQ-NFUNC-002 | useMqttClient 内加 `_refCount = Math.max(0, _refCount - 1)` 下界保护；开发期需覆盖 onLoad/onUnload 的异常路径测试 |
| **param-settings.vue 迁移回归**：现有写链路（`applyDevice/writeAttrs/waitConfirm`）迁移到 useMqttClient 后，接口语义对等但代码路径变化，可能引入新 bug | OOS-02 约束（写链路不改）| 迁移映射表（module_design.md §2 MOD-1110-FE-01）保证函数签名对等；开发期须实测 DeviceWrite → DeviceStatusUpdate 写确认流程，不仅依靠静态分析 |
| **scroll-view 与 uni.pageScrollTo 兼容性**：当 `ps-body` 使用 `scroll-view` 组件时，`uni.pageScrollTo` 可能不影响内部 scroll-view 的滚动位置 | REQ-FUNC-002（"去设置"滚动）| 开发期验证：若不兼容，改为将 `ps-body` scroll-view 替换为页面级 scroll-y，或用 scroll-view 的 `scroll-into-view` 属性 |

### 低风险（Low）

| 风险 | 受影响需求 | 缓解措施 |
|------|-----------|---------|
| `DeviceNode` 设备树未同步（floors 为空）| REQ-FUNC-003 路径A | device_sns 返回空数组，前端降级路径 B（US-OWNER-002 AC-5 已覆盖此场景）|
| `get_available_sub_types` 300s 缓存与设备树同步时序 | REQ-FUNC-001 | `invalidate_room_filter_cache()` 已在设备树同步后调用（现有机制），无需新增 |
| 本地缓存超预期膨胀 | REQ-NFUNC-003 | 估算上限 50KB（10 套 × 5KB），远低于 10MB；若业务扩展绑定数显著增大，可后续加 LRU（已在 REQ-NFUNC-003 说明） |
| MQTT 路径A 超时（10s）时用户等待感 | REQ-FUNC-003, REQ-NFUNC-001 | 按钮显示"刷新中…"，超时后明确提示"设备未响应"；原有缓存值不清空，用户可接受 |
