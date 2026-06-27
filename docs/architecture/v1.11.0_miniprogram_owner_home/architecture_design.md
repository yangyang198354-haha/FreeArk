**特性**：微信小程序业主端首页 / 房间结构 / 主动刷新 / 缓存
**版本**：v1.11.0_miniprogram_owner_home
**状态**：DRAFT
**日期**：2026-06-27
**作者**：system-architect
**依赖**：
- `docs/requirements/v1.11.0_miniprogram_owner_home/requirements_spec.md`（用户已拍板 D-01~D-07，以 APPROVED 对待）
- `docs/requirements/v1.11.0_miniprogram_owner_home/user_stories.md`

---

# 系统架构设计 — v1.11.0 微信小程序业主端功能迭代

**文档编号**：ARCH-DES-v1110-001
**项目名称**：FreeArk 微信小程序业主端首页 / 房间结构 / 主动刷新 / 缓存（v1.11.0）
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-27
**输入文档**：
- `docs/requirements/v1.11.0_miniprogram_owner_home/requirements_spec.md`（D-01~D-07 已拍板）
- `docs/requirements/v1.11.0_miniprogram_owner_home/user_stories.md`
- `FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（复用范式）
- `FreeArkWeb/backend/freearkweb/api/views.py`（`OwnerDeviceTreeView` 蓝本，`get_device_realtime_params` 逻辑参考）
- `FreeArkWeb/backend/freearkweb/api/utils_room_filter.py`（`get_available_sub_types`，已有 300s 缓存）
- `FreeArkWeb/backend/freearkweb/api/middleware.py`（`UserRoleApiGuardMiddleware`，role=user 仅放行 `/api/miniapp/`）
- `miniprogram/utils/screenMqtt.js`（`ScreenMqtt` 类，现有 MQTT IO 封装）
- `miniprogram/subpackages/control/pages/param-settings.vue`（改造基座）

---

## 1. 架构概览

### 1.1 背景与本期变更定位

v1.10.0 建立了业主端（role=user）的 MQTT 屏端直写链路与参数设置页基线。v1.11.0 以**最小侵入原则**叠加三项能力：

1. **房间结构展示**：业主可查看名下专有部分（套）→ 房间 → 设备参数的完整结构视图，含可读/可写标注。
2. **主动刷新**：通过 MQTT DeviceStatusRead（路径 A）或 PLC ondemand（路径 B）主动触发设备上报，替代被动等待。
3. **缓存优先加载**：`uni.getStorageSync` 本地缓存（TTL=5min）减少首屏等待。

**关键约束（已确认，不重新质疑）**：

| 约束 | 来源 |
|------|------|
| `UserRoleApiGuardMiddleware` 拦截 role=user 对全部 `/api/`（除 `/api/miniapp/`、`/api/memory/` 及白名单）的访问 | 代码勘察 `api/middleware.py` |
| `GET /api/devices/realtime-params/` 权限为 `IsOperatorOrAbove`，业主不可调用 | 代码勘察 `views.py:1812` |
| `POST /api/devices/ondemand-refresh/` 权限为 `IsAuthenticated`，但 middleware 先拦截，业主不可调用 | 代码勘察 `views.py:2427` + middleware |
| `panel_*` sub_type 即房间，`get_available_sub_types` 已完成房型过滤 | 代码勘察 `utils_room_filter.py`，OQ-A 已闭环 |
| 改造点集中在 `param-settings.vue`，不新增页面路由 | D-07 / OQ-C 已定 |

### 1.2 整体架构图（文字）

```
[小程序 param-settings.vue（扩展后）]
    │
    ├─ 初始化并行 ──►  GET /api/miniapp/bind/status/        (IsOwnerUser, 现有)
    │                  GET /api/miniapp/device-settings/config/  (IsOwnerUser, 现有)
    │
    ├─ 展开某套 ──►   GET /api/miniapp/owner/realtime-params/?specific_part=X   【新增】
    │                  └─ 复用: get_available_sub_types() + PLCLatestData + DeviceNode
    │
    ├─ 刷新·路径A ─►  MQTT publish DeviceStatusRead → 等 DeviceStatusUpdate
    │                  └─ 复用: useMqttClient 单例（【新增】utils/useMqttClient.js）
    │
    └─ 刷新·路径B ─►  POST /api/miniapp/owner/ondemand-refresh/                【新增】
                       └─ 代理: device_ondemand_refresh 内核 + 归属过滤
                       然后: GET /api/miniapp/owner/realtime-params/?specific_part=X
```

### 1.3 架构风格

**分层单体（Layered Monolith）+ miniapp 命名空间扩展**，与现有 v1.x 各版本一致。后端无新服务、无新数据库、无消息队列变更。前端无新页面路由，仅在现有 `param-settings.vue` 内扩展，并引入一个新的共享工具模块（`useMqttClient.js`）。

---

## 2. 架构决策记录（ADRs）

---

### ADR-1110-01：新增 miniapp 业主实时参数端点，而非放开现有 operator 端点

**Status**：Accepted

**Context**：
`GET /api/devices/realtime-params/` 使用 `@permission_classes([IsOperatorOrAbove])`，且 `UserRoleApiGuardMiddleware` 在 DRF 层之前就拦截 role=user 的请求（代码勘察确认）。要让业主读取设备实时参数，必须决定修改现有端点权限或新增端点。（REQ-NFUNC-004，D-05）

**Options**：

- **Option A（选择）：在 `/api/miniapp/` 下新增 `GET /api/miniapp/owner/realtime-params/`**
  - 优点：遵循 miniapp 命名空间隔离原则；`IsOwnerUser` + `OwnerUserBinding` 归属过滤，隔离清晰；不改变现有 operator 端点行为，零回归风险；与 `views_miniapp_device_settings.py` 已有 `_owner_rooms()` 范式完全一致；middleware 已对 `/api/miniapp/` 整体放行，无需改 middleware。
  - 缺点：新增视图函数，代码量略增；前端需更新 API 调用 URL。

- **Option B：修改现有 `GET /api/devices/realtime-params/` 为 `IsAuthenticated`，视图内加归属分支**
  - 优点：复用现有端点 URL，前端改动更少。
  - 缺点：改变已上线 operator 端点的权限类，存在回归风险；middleware 不放行该路径（`/api/devices/`），仍需改 middleware ALLOWLIST，引入更广泛的 user 访问面；"operator 看全量 / owner 看自己" 逻辑耦合在同一视图函数中，职责不清。

**Decision**：选择 Option A。在 `views_miniapp_device_settings.py`（或新建 `views_miniapp_owner_data.py`）中新增视图函数 `miniapp_owner_realtime_params`，注册于 `urls_miniapp.py`。

**Consequences**：
- 正向：零 operator 端点回归；业主数据访问完全受 `OwnerUserBinding` 限制（REQ-NFUNC-004 满足）；新端点职责单一，易于独立测试。
- 负向：前端调用 URL 不同于 web 端 operator 页所用 URL，需区分维护（可接受，已有先例）。

---

### ADR-1110-02：realtime-params 响应内嵌 device_sn，而非独立设备树端点

**Status**：Accepted

**Context**：
REQ-FUNC-003 路径 A 需要 `device_sn` 以构造 `DeviceStatusRead` MQTT 消息（D-02）。`device_sn` 存于 `DeviceNode.device_sn`，可通过 `DeviceNode.room.floor.owner.specific_part` 关联查出。需决定如何将 `device_sn` 下发给前端。（REQ-FUNC-001，D-02，US-OWNER-002 AC-1）

**Options**：

- **Option A（选择）：在 `GET /api/miniapp/owner/realtime-params/` 响应中追加 `device_sns` 字段**
  - 优点：前端展开一套时，一次 HTTP 请求同时获得参数值（用于展示）和 device_sn 列表（用于 MQTT 刷新）；无额外网络往返；参数值与 device_sn 天然同步（同一时刻查询）。
  - 缺点：realtime-params 端点的语义略宽（不只是"参数值"，还含设备元数据）；DeviceNode 查询是一次额外 DB 查询。

- **Option B：独立 `GET /api/miniapp/owner/device-tree/?specific_part=X` 端点下发 device_sn**
  - 优点：职责分离，realtime-params 只返回值，device-tree 只返回结构。
  - 缺点：前端展开时需并发两个请求；D-04 虽接受并发但无谓增加请求数；`device-tree` 数据几乎不变（设备树同步频率低），与 realtime-params（每次刷新都变）混在同一展开动作中显得冗余。

**Decision**：选择 Option A。在响应中追加 `screen_mac`（从 `OwnerInfo.unique_id` 取）和 `device_sns`（从 `DeviceNode` 查询），前端一次请求即可决定走路径 A 还是路径 B。

**Consequences**：
- 正向：前端展开卡片只发一个 API 请求；device_sn 与参数值在同一响应，时序一致。
- 负向：新增一次 `DeviceNode` DB 查询（`SELECT device_sn WHERE room__floor__owner__specific_part=X`，通常只涉及数十条记录，性能可接受）；若 DeviceNode 为空（设备树未同步），`device_sns` 返回空数组，前端降级路径 B（US-OWNER-002 AC-5 已覆盖该场景）。

---

### ADR-1110-03：新增 miniapp ondemand-refresh 代理端点，而非 middleware ALLOWLIST 豁免

**Status**：Accepted

**Context**：
REQ-FUNC-003 路径 B 需要触发 PLC 按需采集。现有 `POST /api/devices/ondemand-refresh/` 虽使用 `IsAuthenticated`，但被 `UserRoleApiGuardMiddleware` 在中间件层先行拦截（因为路径不在 `/api/miniapp/` 下，不在 ALLOWLIST 中）。业主无法调用。（REQ-FUNC-003，US-OWNER-003，REQ-NFUNC-004）

**Options**：

- **Option A（选择）：新增 `POST /api/miniapp/owner/ondemand-refresh/`，带 `IsOwnerUser` + 归属过滤**
  - 优点：自然融入 miniapp 命名空间；归属过滤确保业主只能触发自己绑定的 specific_part 的采集（防越权）；不修改 middleware ALLOWLIST，不扩大现有 operator 端点的访问面；内部可复用 `device_ondemand_refresh` 的核心逻辑（MQTT publish + 防重入）。
  - 缺点：新增视图函数；需把 ondemand 核心逻辑（MQTT publish 部分）抽为可复用函数，或在新视图中重新调用。

- **Option B：将 `/api/devices/ondemand-refresh/` 加入 middleware ALLOWLIST**
  - 优点：无需新增端点，只改 middleware 一行。
  - 缺点：该端点无归属过滤（`IsAuthenticated` 只验证登录，不验证 specific_part 归属），业主可触发任意 specific_part 的采集，违反 REQ-NFUNC-004 的纵深防御要求；将来若其他端点有类似需求，ALLOWLIST 会持续膨胀，增加安全审计负担。

**Decision**：选择 Option A。新增 `miniapp_owner_ondemand_refresh` 视图函数，`POST /api/miniapp/owner/ondemand-refresh/`，在归属过滤通过后执行 ondemand 采集逻辑。

**Consequences**：
- 正向：完整的归属验证链，符合 REQ-NFUNC-004；middleware 安全边界不变。
- 负向：需把 `device_ondemand_refresh` 内部逻辑中的 MQTT publish 部分提取为可在新视图中调用的工具函数（工作量约 30 行，可接受）；或在新视图中直接重实现（同样约 30 行，不存在共享状态的循环依赖问题）。[ASSUMPTION — PM 确认：可将 `_publish_ondemand_mqtt(specific_part)` 提取为 `api/views.py` 内私有函数供两处调用，无需改动数据模型]

---

### ADR-1110-04：MQTT 全局单例 — 模块级 composable，引用计数管理生命周期

**Status**：Accepted

**Context**：
D-06 要求小程序全局只用一个 MQTT 连接实例，结构视图与 `param-settings.vue` 共用。OQ-B 需定方案：存放位置与 param-settings 既有连接逻辑的无回归迁移。（REQ-NFUNC-002，D-06，US-OWNER-002 AC-1）

**Options**：

- **Option A（选择）：模块级 composable `utils/useMqttClient.js`**，单例存于模块作用域变量
  - 优点：Vue Composition API 惯用模式；模块变量（`let _instance`, `let _refCount`）跨组件共享，不依赖 Vue 组件树；引用计数自然实现（`acquire/release`）；`_connected` 以 `ref()` 暴露，组件可响应式消费；测试时可 mock 整个模块；不污染 `getApp()` 全局对象，不依赖 uni-app 生命周期特殊钩子。
  - 缺点：模块变量不受 Vue 响应式系统直接管理，需手动维护 `_connected ref`；多个组件同时调用 `acquire()` 需保证幂等（引用计数保证）。

- **Option B：挂载到 `getApp()` 对象**（`getApp()._mqtt = ...`）
  - 优点：uni-app 原生全局访问；无需 import。
  - 缺点：非 Vue 惯用写法；`getApp()` 在 page setup 阶段调用时序有风险（页面未挂载前 `getApp()` 可能返回 null）；无类型提示；连接状态不是响应式 ref，组件需手动 watch 或轮询。

- **Option C：Pinia store 管理 MQTT 状态**
  - 优点：Pinia 集成 devtools，调试便利。
  - 缺点：MQTT 连接对象（`ScreenMqtt` 实例）本身不是可序列化的状态，放入 store 反模式；connect/disconnect 是副作用，Pinia 不擅长管理带副作用的外部连接资源；引入对 Pinia 的 MQTT 专项依赖，耦合度高。

**Decision**：选择 Option A。在 `miniprogram/utils/useMqttClient.js` 中实现模块级 MQTT 单例 composable。

**迁移策略（param-settings.vue 既有写链路无回归迁移）**：
1. `param-settings.vue` 中的 `let mqtt = null` 实例变量替换为调用 `useMqttClient()`。
2. `loadConfig()` 中的 `connectRoom()` 调用链路：改为先 `acquire(broker, topics)`，再 `subscribe(mac)`，再注册 `onDeviceUpdate` 回调。
3. `onUnload()` 中的 `mqtt.disconnect()` 改为 `release()`。
4. `applyDevice()` 中的 `mqtt.writeAttrs()` 和 `mqtt.waitConfirm()` 通过 composable 暴露的同名方法调用（参数签名不变）。
5. 既有 `persistSns / loadSns / probeNeighbors` 逻辑保留在 `param-settings.vue` 中（不属于 MQTT 连接管理，无需迁移）。

**Consequences**：
- 正向：param-settings 写链路实现"零语义变更"迁移（函数签名对等映射）；结构视图可安全复用同一 MQTT 连接；单例断开时所有订阅方同时受影响（有助于状态一致）。
- 负向：`_connected` 状态的响应性依赖 composable 内手动维护 ref（ScreenMqtt 内部 `_connected` 为普通 boolean，不是 Vue ref）；若未来多页面并发使用 MQTT，引用计数需更严格的测试覆盖。

---

### ADR-1110-05：param-settings.vue 垂直二区布局，「去设置」为页内滚动

**Status**：Accepted（OQ-C 已由 PM 于 2026-06-27 确定，ADR 仅补充实现层决策）

**Context**：
D-07 / OQ-C 已确定：结构视图并入 `param-settings.vue`，一体页。REQ-FUNC-002 中"去设置"入口需决定如何在一体页中实现。（REQ-FUNC-001，REQ-FUNC-002，D-07）

**Options**：

- **Option A（选择）：垂直二区——"我的房产"区在上，参数设置区在下，共享 scroll-y**
  - 优点：最简改造方案，不引入新 UI 组件（如 tab-bar）；"去设置"点击后设置 `roomIndex` 为对应 specific_part 并 `uni.pageScrollTo` 滚动到参数设置区（原生 API，无需第三方）；两区共享 `broker/topics/config` 数据（同一次 `getDeviceSettingsConfig()` 调用）。
  - 缺点：页面内容可能较长（多套展开时），需依赖 scroll-y 自然滚动；无明确的区域分割指示。

- **Option B：标签页（tab-bar 组件），"我的房产" / "参数设置"两 tab**
  - 优点：UI 逻辑分隔清晰。
  - 缺点：引入新 tab 组件（uni-app 无内置 tab-bar 用于页内，需自实现或引入 uni-ui）；"去设置"需切换 tab，视觉跳转不连续；增加 v1.11.0 前端工作量；两 tab 的数据状态共享需额外抽象。

**Decision**：选择 Option A。页面顶部增加"我的房产"区（套卡片列表），下方保留现有参数设置区，页面标题可调整为"我的房产"（开发期确认）。

**Consequences**：
- 正向：改造范围最小，既有参数设置 template 和 script 几乎无需改变；"去设置"只需设置 roomIndex 并调用 `uni.pageScrollTo`。
- 负向：页面 scroll-y 需重新确认滚动容器层级（`ps-body` scroll-view 改为页面级 scroll-y 或维持 scroll-view 内嵌两区）；若套卡片展开多个，顶部房产区可能较长，需 UX 确认是否加折叠手势。

---

### ADR-1110-06：缓存读取使用 uni.getStorageSync（同步），写入使用同步 setStorageSync

**Status**：Accepted

**Context**：
REQ-FUNC-004 要求"展开时优先从缓存读取并立即渲染"（< 100ms）。需决定缓存读写是同步还是异步。（REQ-FUNC-004，D-03，US-OWNER-004 AC-1）

**Options**：

- **Option A（选择）：`uni.getStorageSync` 同步读，`uni.setStorageSync` 同步写**
  - 优点：读取操作在 JS 主线程同步完成，展开动作（onExpand 函数）内可立即判断有无缓存并渲染；无 Promise 链组合复杂度；单条缓存 ≤ 5 KB，同步 IO 耗时在微信小程序中通常 < 5ms（远低于 100ms 要求）。
  - 缺点：同步 IO 阻塞 JS 主线程（< 5ms 可忽略）；多条并发写入（多套同时刷新）时 setStorageSync 串行，可接受（各套独立 key，无争用）。

- **Option B：`uni.getStorage` 异步读，`uni.setStorage` 异步写**
  - 优点：不阻塞主线程。
  - 缺点：展开函数变为 async，需 await；在 await 返回之前 UI 无法立即呈现缓存（失去"立即渲染"的核心价值）；若用 callback 则增加代码复杂度。

**Decision**：选择 Option A。体积约束（单条 ≤ 5KB，总 ≤ 50KB，REQ-NFUNC-003）远低于微信 10MB 限制，同步 IO 安全可用。

**Consequences**：
- 正向：实现简单；展开时缓存读取零延迟渲染；不引入 async 复杂度。
- 负向：若单条缓存数据异常膨胀（超预期），同步 IO 可能引起卡顿——在 REQ-NFUNC-003 约束下（估算上限 50KB）此风险极低。

---

### ADR-1110-07：懒加载实时参数（展开时按需请求），而非页面初始化批量预取

**Status**：Accepted

**Context**：
D-04 接受并行多请求，但业主可能绑定多个专有部分（最多约 10 个，INF-04）。需决定何时调用 `GET /api/miniapp/owner/realtime-params/`。（REQ-FUNC-001，D-04，REQ-FUNC-004）

**Options**：

- **Option A（选择）：用户展开某套卡片时，才发起该套的 realtime-params 请求（懒加载）**
  - 优点：减少页面初始化时的并发请求数；用户可能不展开所有套（避免无效请求）；缓存先行（有缓存立即渲染，API 请求后台刷新）弥补了懒加载的"等待感"；各套展开独立，不互相阻塞。
  - 缺点：展开时需等待 API（无缓存场景有感知延迟）。

- **Option B：页面初始化时并行预取所有绑定套的 realtime-params**
  - 优点：用户展开任一套时，数据已就绪（若请求已完成）。
  - 缺点：10 个套 = 10 个并行请求，页面初始化时瞬时并发高（对服务器和网络有压力）；大部分请求可能是"无效"的（用户只展开 1~2 个套）；与缓存先行机制重叠（有缓存时预取的价值降低）。

**Decision**：选择 Option A。配合 ADR-1110-06 的缓存先行，懒加载在有缓存场景下用户体验无损，在无缓存场景下展开时有明确的 loading 状态（US-OWNER-004 AC-3）。

**Consequences**：
- 正向：页面初始化只需两个并行请求（`bind/status` + `device-settings/config`），快速完成；无效请求为零。
- 负向：首次无缓存展开有 loading 状态（设计已覆盖，US-OWNER-004 AC-3 明确允许）。

---

## 3. 安全架构

### 3.1 归属过滤纵深防御

采用两层防御（REQ-NFUNC-004）：

**第一层（后端强制）**：所有新 miniapp 端点在视图函数内执行：
```
allowed_parts = {b.owner.specific_part for b in OwnerUserBinding.objects.filter(user=request.user, active=True)}
if specific_part not in allowed_parts → HTTP 403
```

**第二层（前端约定，纵深防御）**：`specific_part` 值仅取自 `GET /api/miniapp/bind/status/` 的响应，不接受 URL query string 或用户输入直传（US-OWNER-001 AC-2，spec §3 REQ-NFUNC-004 约束细节）。

### 3.2 越权写残余风险（已接受）

MQTT 直连架构（ADR-01 v1.10.0 继承）中，业主端直连 broker 的写命令（DeviceWrite）在后端不可拦截。该风险在 v1.10.0 OQ-10 中已书面接受（broker ACL 最小权限改造 OOS-05）。本版本不重新评估。

---

## 4. 数据流设计

### 4.1 缓存优先加载 + 离线降级（REQ-FUNC-004 / REQ-FUNC-005）

```
用户点击展开 specific_part
    │
    ├─ [同步] uni.getStorageSync('owner_realtime_{sp}')
    │   ├─ 有缓存 ─► 立即渲染缓存参数值
    │   │            读 '_ts' key → 计算相对时间 → 显示"更新于 N 分钟前"
    │   │            若 (now - ts) > 300000ms → 追加"数据可能已过时"
    │   │
    │   └─ 无缓存 ─► 显示 loading spinner
    │
    ├─ [异步/并行] 发起 GET /api/miniapp/owner/realtime-params/?specific_part=X
    │   ├─ 成功 ─► 更新渲染 → setStorageSync(key, data) + setStorageSync(ts, now.toISOString())
    │   │           时间戳标签更新为"刚刚更新"
    │   │
    │   └─ 失败 ─► 有缓存: 追加"（刷新失败）"到时间戳标签 (不清空缓存值)
    │               无缓存: 显示"获取设备数据失败，请点击重试"
    │
    └─ 网络检测: 离线时顶部显示"当前离线，显示缓存数据"横幅（不弹 toast）
```

**缓存 key 规范**：

| key | 内容 | TTL 判定 |
|-----|------|---------|
| `owner_realtime_{specific_part}` | realtime-params 响应 JSON 字符串 | 读 ts key 计算 |
| `owner_realtime_{specific_part}_ts` | ISO8601 时间戳字符串 | > 5min → 显示"可能过时" |

### 4.2 主动刷新双路径（REQ-FUNC-003）

```
用户点击"刷新"按钮（具体套）
    │
    ├─ 检查: screen_mac（来自 realtime-params 响应）是否非空?
    │   ├─ 有 screen_mac
    │   │   ├─ 检查: device_sns（来自 realtime-params 响应）非空?
    │   │   │   ├─ 有 device_sn ─► [路径 A]
    │   │   │   │   1. useMqttClient.acquire(broker, topics)（已连则复用）
    │   │   │   │   2. subscribe(screen_mac)（幂等）
    │   │   │   │   3. publish DeviceStatusRead（每个 device_sn）
    │   │   │   │   4. 等待 DeviceStatusUpdate（timeout 10s）
    │   │   │   │   5. 成功: 更新 UI + 写缓存
    │   │   │   │   6. 超时: 提示"设备未响应"，不清空 UI，执行路径 B 降级 [ASSUMPTION — PM确认: 超时后是否自动降级B，还是仅提示用户手动重试]
    │   │   │   │
    │   │   │   └─ 无 device_sn ─► 直接走路径 B
    │   │   │
    │   └─ 无 screen_mac ─► 直接走路径 B
    │
    └─ [路径 B]
        1. POST /api/miniapp/owner/ondemand-refresh/ {specific_part}
        2. 等 5 秒
        3. GET /api/miniapp/owner/realtime-params/?specific_part=X
        4. 更新 UI + 写缓存
```

**按钮防抖（REQ-NFUNC-001）**：每个套独立 `refreshing_{specific_part}` 状态，点击后立即置 true，完成/超时/失败后置 false，最短持续 3 秒。

---

## 5. 开放问题

以下事项已标注 [ASSUMPTION]，需 PM 确认（均为非阻塞项，有建议默认值）：

| # | 问题 | 建议默认 |
|---|------|---------|
| OQ-D | MQTT 超时时长（INF-01）| 10s，无意见即采用 |
| OQ-D | 单用户最大绑定数（INF-04）| 10，无意见即采用 |
| 路径A超时降级 | 路径A超时后是否自动降级路径B，还是仅提示用户重试 | [ASSUMPTION] 建议仅提示，不自动降级（避免双重请求混淆 UX）|
| 新端点文件归属 | `miniapp_owner_realtime_params` / `miniapp_owner_ondemand_refresh` 放 `views_miniapp_device_settings.py` 还是新建 `views_miniapp_owner_data.py` | [ASSUMPTION] 放现有文件，避免新文件带来的导入配置变动；若 views_miniapp_device_settings.py 超过 300 行后可考虑拆分 |
