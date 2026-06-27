<!--
  @module v1.11.0_miniprogram_owner_home
  @author sub_agent_requirement_analyst
  @version 1.11.0
  @status DRAFT
  @created 2026-06-27
  @description FreeArk 微信小程序业主端首页/结构发现/主动刷新/缓存需求规格
-->

# v1.11.0 微信小程序业主端功能迭代 需求规格说明书

## 执行摘要

### 业务背景

FreeArk 微信小程序当前业主端（role=user）仅有"参数设置"（`param-settings.vue`）和"方舟智能体问答"两个功能入口。首页对业主仅显示欢迎文案，无法从统一页面了解名下绑定的专有部分有哪些设备、哪些参数可监控、哪些可控制；现有参数查看路径依赖 MQTT 被动订阅（`DeviceStatusUpdate`），无法主动触发设备上报最新状态；realtime-params 结果当前无缓存，每次进入页面必须等待 API 响应。本次迭代目标为补齐上述三个能力短板。

### 需求总览

- **功能需求**：5 条（REQ-FUNC-001 ~ REQ-FUNC-005）
- **非功能需求**：4 条（REQ-NFUNC-001 ~ REQ-NFUNC-004）
- **推断性需求**：2 处具体参数值标注 [INFERRED]（MQTT 超时时长、缓存 TTL），占总需求数比例 < 10%

---

## 1. 范围说明

> **修订说明（2026-06-27，用户 7 项决策已拍板 + 代码勘察纠偏）**：本节据 PM 决策 D-01~D-07（见第 6 节）与后端实情重写。关键变化：（1）OQ-07 决策为**改造现有页面**而非新建独立页；（2）OQ-01 确认 specific_part **内部有真实房间层级**（书房、儿童房…），结构为 套(specific_part) → 房间 → 设备/面板；（3）OQ-05 引入**后端改动**——本版本不再是纯前端迭代。

### 1.1 本版本包含

**前端**（面向 role=user 业主）：
- **改造现有页面**（非新建独立页，D-07）：在业主端现有页面上呈现"我的房产"结构视图——按 **房间** 分组（书房/儿童房/客厅…）展示每间房的设备/面板及其参数当前值。最终改造哪个现有页面见 D-07 备注。
- 结构展示：套(specific_part) → 房间 → 设备/面板 → 参数（含当前值）。
- 参数可读/可写状态标注（依据 `device-settings/config` 的 `writable_attrs` 白名单），可写参数附"去设置"入口。
- 主动拉取设备最新状态（不干等被动上报）。
- 缓存优先加载（先渲染上次缓存值，后台刷新）。
- 离线/无缓存降级展示。
- MQTT 连接**全局单实例**复用（D-06）：结构视图与 param-settings 共用同一 MQTT 客户端单例，不各自新建连接。

**后端**（本版本新增，D-05 引入）：
- 新增 `/api/miniapp/` 命名空间下的**业主自有设备树/实时参数**端点（`IsOwnerUser` + `OwnerUserBinding` 归属过滤），让 role=user 业主能取到**仅自己绑定**的 套→房间→设备→参数值 及 `device_sn`。
  - 现有 `GET /api/devices/realtime-params/` 与 `GET /api/owners/<pk>/device-tree/` 均为 `IsOperatorOrAbove`（且 role=user 被 `UserRoleApiGuardMiddleware` 拦在 `/api/miniapp/` 之外）——业主**根本无法调用**，故必须走新 miniapp 端点。
  - `device_sn` 来源：`device_node.device_sn`（经 OwnerInfo→floors→rooms→devices 可达，D-02）。
- admin/operator 的"查看全部"诉求（D-05）**已由现有 operator 端点满足**（`OwnerDeviceTreeView`/`realtime-params` 即 `IsOperatorOrAbove`=全量可见），新 miniapp 端点无需再加 admin/operator 分支。

### 1.2 本版本不包含

详见第 4 节"超出范围"。关键排除项：
- 不修改 `param-settings.vue` 的写命令/mode 联动/审计上报等**既有写链路**（仅在 MQTT 连接管理上改为共用单例，D-06）。
- 不修改 `device-panel.vue`（operator 监控子包）的任何现有功能。
- 不修改 web 端 operator 接口的权限与行为。
- 不修改运维/admin/operator 角色在 web 端的功能。

---

## 2. 功能需求

---

### REQ-FUNC-001：专有部分结构展示页（新建）

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-001 |
| **描述** | 系统应当为 role=user 的业主在**现有页面**（D-07）上展示其所有已绑定专有部分的**房间级**结构（套 → 房间 → 设备/面板 → 参数），支持展开/折叠查看设备参数列表与当前值。 |
| **来源引用** | "用户绑定其'专有部分'后，可以复用 Web 端已有的逻辑（通过 API 访问数据库）找到自己专有部分的结构——例如有几间房、每间房有哪些设备" [USER-REQ-1]；D-01：specific_part 内部有真实房间层级（书房/儿童房…），每间房有面板 |
| **优先级** | Must Have |
| **备注** | 数据模型已存在：`device_floor → device_room → device_node`（同步自屏端 floor-room-device/list），`OwnerDeviceTreeView` 已实现 operator 版遍历，可作 miniapp 端点蓝本 |

**详细行为：**

1. 页面初始化时调用 `GET /api/miniapp/bind/status/`，获取当前用户所有绑定专有部分列表（含 `specific_part`、`location_name`、`bound_at`）。
2. 每个专有部分（套）以卡片展示，显示 `location_name`（空则 fallback `specific_part`），附展开/折叠控件。
3. 展开某套时，调用**新增的 miniapp 业主设备树端点**（`IsOwnerUser`+归属过滤，见 §1.1 后端），获取该套的 **房间列表**（`device_room.room_name`，如"书房""儿童房"）及每间房的设备/面板（`device_node`）。
4. 展开后**按房间分组**展示：`panel_*` sub_type 即房间（用 `sub_type_display` 作房间名，如"书房""儿童房"），其下列参数（`display_name`/`param_name` + 当前 `value`）；`SYSTEM_LEVEL_SUB_TYPES` 归入"全屋系统"分区。
   - ✅ **OQ-A 已解决**：复用 `get_available_sub_types`（v0.5.7 房型过滤）+ `realtime-params` 分组逻辑，参数已天然归到房间，无需新建 device_node↔value 映射（详见 §6.2 OQ-A）。
5. 若用户无任何绑定，显示"您还没有绑定专有部分"提示及"去绑定"按钮（跳转 `pages/bind/index.vue`）。

---

### REQ-FUNC-002：设备参数可读/可写状态标注

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-002 |
| **描述** | 系统应当在专有部分展开后的参数列表中，依据 writable_attrs 白名单对每个参数标注"只读"或"可设置"，并为可设置参数提供跳转参数设置页的快捷入口。 |
| **来源引用** | "哪些设备可查看、哪些可控制" [USER-REQ-1] |
| **优先级** | Must Have |
| **备注** | 无 |

**详细行为：**

1. 页面初始化时（与 bind/status 并行）调用 `GET /api/miniapp/device-settings/config/`，获取 `config.writable_attrs`（attrTag → 控件配置的白名单映射）。
2. 展开专有部分后，对每个参数的 `param_name` 与 `writable_attrs` 的 key 集合进行比对：
   - `param_name` 在 `writable_attrs` 中 → 标注"可设置"，附带"去设置"按钮；点击跳转 `subpackages/control/pages/param-settings.vue` 并传入对应 `specific_part`。
   - `param_name` 不在 `writable_attrs` 中 → 标注"只读"，仅展示当前值，无编辑入口。
3. 若 `device-settings/config` 请求失败，降级为：所有参数显示"只读"，页面顶部提示"参数配置获取失败，可设置参数标注不可用"。

---

### REQ-FUNC-003：主动拉取设备最新状态

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-003 |
| **描述** | 系统应当在专有部分结构展示页为已展开的专有部分提供"刷新"按钮，支持主动触发设备状态上报，不依赖设备自发推送。根据专有部分是否有 screen_mac，选择不同拉取路径。 |
| **来源引用** | "可以使用 cloud/to/device 或其他已知的 MQTT 下行机制，主动要求 device 上报最新状态，而不是被动干等设备自发上报" [USER-REQ-2] |
| **优先级** | Must Have |
| **备注** | 无 |

**路径 A：屏端 MQTT 路径**（适用于专有部分在 `device-settings/config` 的 `rooms` 列表中，即有 `screen_mac`）

1. 建立 MQTT 连接（broker 配置来自 `device-settings/config` 的 `broker` 字段）。
2. 向 `/screen/service/cloud/to/screen/{screenMac}` 发布 `DeviceStatusRead` 消息。
   - header.sn 填写 `deviceSn`，**来源为后端/数据库**（`device_node.device_sn`，经新增 miniapp 业主设备树端点下发，D-02）。撤销原"deviceSn 仅靠 `ds_sns_{mac}` 前端缓存、缓存空就降级路径 B"的假设——只要数据库里有 device_node 记录即可走路径 A。
   - MQTT 连接复用**全局单实例**（D-06），不为本次发布新建连接。
3. 订阅 `/screen/upload/screen/to/cloud/{screenMac}`，等待 `DeviceStatusUpdate` 响应。
4. 收到响应后：解析 `items`，更新对应参数值显示，写入缓存（见 REQ-FUNC-004）。
5. 超时未响应（建议 10 秒 [INFERRED — requires PM confirmation]）：提示"设备未响应，请确认设备在线"，按钮恢复可用，原有显示值保留不清空。

**路径 B：PLC ondemand 路径**（适用于专有部分无 screen_mac，或路径 A 超时后的降级）

1. 调用 `POST /api/devices/ondemand-refresh/ {"specific_part": "..."}`，预期 202 Accepted。
2. 延迟约 5 秒后，调用 `GET /api/devices/realtime-params/?specific_part={specific_part}` 重取快照。
3. 更新参数值显示，写入缓存。

---

### REQ-FUNC-004：缓存优先加载（realtime-params 结果缓存）

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-004 |
| **描述** | 系统应当在展开专有部分时优先从本地缓存（`uni.getStorageSync`）读取并立即渲染上次的参数快照，同时后台发起 API 刷新，刷新完成后无缝更新显示。 |
| **来源引用** | "页面最初加载时可以先使用最新（上一次）的缓存值渲染，提升用户体验（缓存优先 + 后台刷新）" [USER-REQ-3] |
| **优先级** | Should Have |
| **备注** | 无 |

**缓存 key 规范：**

| key | 内容 | 示例 |
|-----|------|------|
| `owner_realtime_{specific_part}` | `realtime-params` 响应的 JSON 字符串 | `owner_realtime_1-1-2-201` |
| `owner_realtime_{specific_part}_ts` | ISO8601 时间戳字符串（写入时刻） | `owner_realtime_1-1-2-201_ts` |

**加载流程：**

1. 用户展开某专有部分时，调用 `uni.getStorageSync('owner_realtime_{specific_part}')`。
2. **有缓存**：立即渲染缓存中的参数值，显示"更新于 {相对时间，如 '3 分钟前'}"时间戳标签；同时后台异步发起 `GET /api/devices/realtime-params/?specific_part={specific_part}`。
3. **无缓存**：进入"加载中…"状态，等待 API 响应。
4. 后台刷新成功：更新显示值，写入新缓存及时间戳，时间戳标签更新为"刚刚更新"。
5. 后台刷新失败（网络错误/超时）：若有缓存则保留显示，时间戳标签旁追加"（刷新失败）"；若无缓存见 REQ-FUNC-005。

**缓存写入时机：**

- `GET /api/devices/realtime-params/` 成功返回时。
- 主动拉取（REQ-FUNC-003）成功收到 `DeviceStatusUpdate` 或 ondemand 重取成功时。

**缓存失效策略（TTL）：**

- 建议 TTL = 5 分钟 [INFERRED — requires PM confirmation]。
- TTL 超过后缓存值不自动清空，仍可显示，但时间戳标签提示"数据可能已过时（更新于 N 分钟前）"。
- 用户点击"刷新"按钮或页面下拉刷新时，总是强制绕过 TTL 检查，直接发起 API 请求。

---

### REQ-FUNC-005：离线/无缓存降级展示

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-005 |
| **描述** | 系统应当在无网络连接或 API 请求失败时提供明确的降级展示，确保业主看到有意义的信息而非空白页或未处理异常。 |
| **来源引用** | "页面最初加载时可以先使用最新（上一次）的缓存值渲染" [USER-REQ-3]；任务规格明确约束：离线/设备离线降级展示 |
| **优先级** | Should Have |
| **备注** | 无 |

**降级策略矩阵：**

| 场景 | 本地缓存 | 展示行为 |
|------|---------|---------|
| 无网络 | 有 | 展示缓存值 + 时间戳，页面顶部显示"当前离线，显示缓存数据"横幅，不弹 toast |
| 无网络 | 无 | 显示"暂无数据，请检查网络连接后点击刷新"，提供"重试"按钮 |
| 有网络，API 错误/超时 | 有 | 保留缓存值，时间戳旁追加"（刷新失败）"提示，不弹阻断性 toast |
| 有网络，API 错误/超时 | 无 | 显示"获取设备数据失败，请点击重试"，提供"重试"按钮 |
| MQTT 路径超时（路径 A） | 任意 | 提示"设备未响应，请确认设备在线"，原有显示不清空，按钮恢复可用 |

---

## 3. 非功能需求

---

### REQ-NFUNC-001：主动刷新防抖节流

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-001 |
| **描述** | 系统应当对"刷新"按钮实施防抖/节流，避免业主连续点击引发多次并发请求。 |
| **来源引用** | 任务规格明确约束："主动拉取的防抖/节流（避免连点）" |
| **优先级** | Should Have |
| **备注** | 无 |

**约束细节：**

- 刷新按钮点击后立即进入锁定状态，显示"刷新中…"，设为不可点击。
- 锁定期持续至：收到响应、收到超时或请求失败，三者之一先到为准。
- 最短锁定时间：3 秒（防止极快响应导致按钮状态一闪而过）。
- 各专有部分的刷新按钮**独立**锁定（刷新 A 不影响 B、C 的按钮状态）。

---

### REQ-NFUNC-002：MQTT 连接按需建立与释放

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-002 |
| **描述** | 小程序业主端**全局只维护一个 MQTT 客户端单实例**（D-06），结构视图与 `param-settings.vue` 共用；按需建立、引用计数管理、无引用时断开。 |
| **来源引用** | 任务规格："MQTT 连接生命周期"；D-06：小程序使用一个 MQTT 连接实例 |
| **优先级** | Must Have |
| **备注** | 撤销原"各页面独立管理连接"假设。需要一个全局单例管理器（composable / store），统一 connect/subscribe/publish/引用计数/disconnect |

**约束细节：**

- 全局 MQTT 单例：首个需要 MQTT 的场景触发 connect；以引用计数（或活跃订阅集）跟踪使用方。
- 结构视图触发路径 A 时：复用单例（已连则直接 publish/subscribe，未连则 connect）。
- 引用计数归零（无任何页面/视图在用）时断开；不在与 MQTT 无关的页面预连接。
- broker 连接凭证来源：`GET /api/miniapp/device-settings/config/` 的 `broker` 字段（不硬编码）。
- ⚠️ **待定（OQ-B）**：单例的存放与生命周期边界——挂在 App 级（全程常驻引用计数）还是模块级 composable？param-settings 现有连接逻辑如何无回归地迁移到单例？需架构阶段定。

---

### REQ-NFUNC-003：本地存储配额合规

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-003 |
| **描述** | 系统应当确保缓存设计的总体积不超出微信小程序本地存储上限（10 MB/小程序），且有合理的体积估算依据。 |
| **来源引用** | 任务规格明确约束："小程序本地存储配额（微信 10MB 限制，单条数据体积估算）" |
| **优先级** | Must Have |
| **备注** | 无 |

**估算依据：**

- 单条 `owner_realtime_{specific_part}` 体积：`realtime-params` 响应 JSON 序列化后约 2~5 KB（含 4 个 sub_types，每 sub_type 约 5~10 个参数）。
- 单用户最大绑定数量估算：≤ 10 个专有部分（业务上限，PM 可确认）。
- 估算总存储占用：10 × 5 KB = 约 50 KB，远低于 10 MB 上限。
- 当前无需实现 LRU 淘汰策略；若未来业务扩展导致绑定数显著增大，可作后续加固项。

---

### REQ-NFUNC-004：realtime-params 接口前端访问边界

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-004 |
| **描述** | 业主端读取设备数据**必须**经新增的 miniapp 端点，后端以 `OwnerUserBinding` 强制归属过滤——业主只能读自己 active 绑定的 specific_part；越权 specific_part 返回 403/空。 |
| **来源引用** | D-05：普通 owner 有安全检查；admin/operator 可查看全部 |
| **优先级** | Must Have |
| **备注** | **纠偏**：原文称 `realtime-params` 仅 `IsAuthenticated` 有误——实际是 `IsOperatorOrAbove`，且 role=user 被 `UserRoleApiGuardMiddleware` 拦在 `/api/miniapp/` 外。故业主既读不到他人数据、也读不到自己数据，必须建新 miniapp 端点。 |

**约束细节（后端，本版本新增）：**

- 新 miniapp 业主端点（`IsOwnerUser`）服务端按 `OwnerUserBinding(user=request.user, active=True)` 过滤 specific_part 集合；请求中的 specific_part 不在该集合 → 403。复用 `views_miniapp_device_settings._owner_rooms` 的归属判定范式。
- admin/operator"查看全部"无需在新端点实现——其 web 端 `IsOperatorOrAbove` 端点（`OwnerDeviceTreeView`/`realtime-params`）本就全量可见。
- 前端仍遵守：specific_part 仅取自 `bind/status` 响应，不接受 URL/用户输入（纵深防御）。

---

## 4. 超出范围（Out of Scope）

| 序号 | 排除内容 | 排除原因 |
|------|---------|---------|
| ~~OOS-01~~ | ~~新增后端 API~~ | **已撤销**：D-05 决策本版本**新增** miniapp 业主设备树/实时参数端点（含归属过滤），后端改动在范围内 |
| OOS-02 | 修改 `param-settings.vue` 既有**写链路** | 写命令、mode 联动、审计上报已上线（v1.10.0），不改；仅 MQTT 连接改为共用单例（D-06） |
| OOS-03 | 修改 `device-panel.vue` 现有功能 | realtime-params 展示、ondemand-refresh 已上线，不重写需求 |
| OOS-04 | 运维/admin/operator 角色的小程序功能 | v1.10.0 OQ-01 已确认业主端仅面向 role=user |
| OOS-05 | broker ACL 最小权限改造 | v1.10.0 OQ-10 已接受此残余风险，本版本不重新评估 |
| OOS-06 | 参数历史趋势图表 | `device-panel.vue` 已有占位入口，与本版本结构展示页无关 |
| OOS-07 | 参数值单位格式化增强（如 ×10 缩放显示） | 超出本版本范围，可作后续优化 |

---

## 5. 待确认推断项

| 序号 | 推断内容 | 所在位置 | 建议默认值 | 状态 |
|------|---------|---------|-----------|------|
| INF-01 | MQTT DeviceStatusRead 超时时长 | REQ-FUNC-003 路径 A | 10 秒 | 待确认 |
| INF-02 | 缓存 TTL | REQ-FUNC-004 | 5 分钟 | **已定**（D-03：不加清缓存按钮；TTL 取 5 分钟） |
| ~~INF-03~~ | ~~新增"我的房产"入口~~ | — | — | **作废**（D-07 改为替换现有页面） |
| INF-04 | 单用户最大绑定专有部分数（存储估算上限） | REQ-NFUNC-003 | 10 个 | 待确认 |

---

## 6. 决策记录与开放问题

### 6.1 已决策（用户 2026-06-27 拍板）

| # | 问题 | 决策 |
|---|------|------|
| **D-01** | "房间"语义 | specific_part **内部有真实房间**（书房、儿童房…），每间房有面板。结构：套 → 房间 → 设备/面板。数据在 `device_floor/device_room/device_node`（同步自屏端） |
| **D-02** | deviceSn 来源 | deviceSn 在数据库 device 相关表（`device_node.device_sn`）有记录，由新 miniapp 端点下发；不再依赖前端 MQTT 缓存 |
| **D-03** | 缓存 TTL / 清缓存按钮 | **不要**清除缓存按钮；TTL 取 5 分钟（下拉刷新等效清缓存） |
| **D-04** | 并发多请求 vs 后端聚合 | 性能问题后置；本版本接受并行多请求（若新端点按"套"聚合返回则天然缓解） |
| **D-05** | realtime 归属校验 | **加**归属校验：普通 owner 受 `OwnerUserBinding` 过滤（仅自己）；admin/operator 可查看全部（已由现有 operator 端点满足）。本版本新增 miniapp 业主端点承载该校验 |
| **D-06** | MQTT 连接实例 | 小程序**全局只用一个** MQTT 连接实例（单例共享，结构视图与 param-settings 共用） |
| **D-07** | 页面入口 | **不新建页面**；**并入 `param-settings.vue`**——扩展为"我的房产（房间结构）+ 参数设置"一体页（OQ-C 已定，2026-06-27） |

### 6.2 因决策与勘察新产生的开放问题（需 PM 在架构阶段前拍板）

#### OQ-A：实时参数值如何归到具体房间 — **已勘察解决，非风险**

**结论**：现有架构（v0.5.7 房型过滤）**已把参数归到房间**，无需新建映射：
- `panel_*` sub_type **本身即房间**：`panel_study_room`=书房、`panel_bedroom`=主卧/次卧、`panel_children_room`=儿童房/主卧、`panel_fourth_children`=四房儿童房（见 `seed_device_config.py` 与 `utils_room_filter.py:SUB_TYPE_TO_ROOM_KEYWORDS`）。
- `get_available_sub_types(specific_part)`（`utils_room_filter.py`，带 300s 缓存）已按 `device_room.ori_room_name` 关键词算出该套**实际拥有哪些房间面板**。
- 现有 `realtime-params` 已用 `available_sub_types` 过滤并按 sub_type 分组返回 → **已是房间感知**。

**对设计的影响**：新 miniapp 业主端点**复用** `get_available_sub_types` + `realtime-params` 分组逻辑即可。前端把 `panel_*` sub_type 渲染为"房间"（用 `sub_type_display` 作房间名），把 `SYSTEM_LEVEL_SUB_TYPES`（main_thermostat/fresh_air/energy_meter/hydraulic_module/air_quality）渲染为"全屋系统"分区。**无需 device_node↔PLCLatestData 直连、无需降级、无需推迟 v1.12.0。**

**遗留细节**（开发期处理，非阻塞）：`panel_bedroom` 与 `panel_children_room` 关键词均含"主卧"、可同时激活属正确行为；前端房间标题直接用 `sub_type_display`，不自行二次推断房型。

#### OQ-B：MQTT 单例的存放与迁移

**问题**：全局单例（D-06）挂在 App 级常驻还是模块级 composable？`param-settings.vue` 现有连接逻辑如何无回归迁移到单例（引用计数、订阅去重、断线重连归属）？

**影响范围**：前端架构

**建议默认**：模块级 composable（`useMqttClient`）+ 引用计数；架构阶段产出迁移方案，回归测试覆盖 param-settings 既有写链路。

#### OQ-C：替换/改造哪个现有页面 — **已定（2026-06-27）**

**决策**：并入 `param-settings.vue`——在现有参数设置页顶部增加"我的房产"房间结构区，扩展为"房间结构 + 参数设置"一体页。"去设置"为就地交互（同页），与 D-06 MQTT 单例最自洽。

**影响**：改造点集中在 `subpackages/control/pages/param-settings.vue`；不新增页面路由；首页业主入口仍指向该页（文案可由"参数设置"调整为"我的房产/参数设置"，开发期定）。

#### OQ-D（保留待确认）：MQTT 超时时长（INF-01，默认 10s）、最大绑定数（INF-04，默认 10）。无意见即采用默认。
