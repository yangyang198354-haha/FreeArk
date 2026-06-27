<!--
  @module v1.11.0_miniprogram_owner_home
  @author sub_agent_requirement_analyst
  @version 1.11.0
  @status DRAFT
  @created 2026-06-27
  @description FreeArk 微信小程序业主端首页/结构发现/主动刷新/缓存 用户故事清单
-->

# v1.11.0 微信小程序业主端功能迭代 用户故事清单

> **修订说明（2026-06-27）**：用户已对 7 项决策拍板（见 `requirements_spec.md` §6.1，D-01~D-07），并经代码勘察纠偏。关键变化：
> - **D-01**：specific_part 内部有**真实房间**（书房/儿童房…）→ 结构为 套 → 房间 → 设备/面板；展示按房间分组。
> - **D-05 + 纠偏**：`realtime-params`/`device-tree` 实为 `IsOperatorOrAbove`，role=user 被中间件拦截 → 业主**读不到**；本版本**新增 miniapp 业主端点**（`IsOwnerUser`+归属过滤）。下文 AC 中对 `/api/devices/realtime-params/` 的直接引用一律改为"新 miniapp 业主端点"。
> - **D-02**：deviceSn 来自 DB（`device_node.device_sn`），不再依赖 `ds_sns_{mac}` 前端缓存。
> - **D-06**：MQTT 全局单实例；**D-07**：替换/改造现有页面，不新建独立页。
> - 新增开放问题 **OQ-A**（参数值如何归到房间，影响可行性）/ **OQ-B**（MQTT 单例迁移）/ **OQ-C**（改造哪个页面），详见 spec §6.2。下方部分 AC 在 OQ-A/C 定案后需微调。

---

## 用户角色地图（Actor × Feature Matrix）

| Actor | 专有部分结构展示 | 参数读写标注 | 屏端主动刷新 | PLC路径刷新 | 缓存优先加载 | 离线降级 |
|-------|--------------|------------|------------|-----------|------------|---------|
| 已绑定专有部分的业主（role=user） | US-OWNER-001 | US-OWNER-001 | US-OWNER-002 | US-OWNER-003 | US-OWNER-004 | US-OWNER-005 |

---

## US-OWNER-001：查看我的专有部分结构与设备参数

**来源**：REQ-FUNC-001、REQ-FUNC-002

**角色**：已绑定专有部分的业主

**描述**：As a 已绑定专有部分的业主，I want to 在（改造后的）现有页面按**房间**查看我所有绑定房产的设备/面板及每个参数的可读/可写状态，So that 我能清楚了解名下房产每间房（书房/儿童房…）有哪些设备可监控、哪些参数可控制，不必逐一询问或猜测。

---

### AC-1

**Given** 业主已通过微信小程序登录（role=user），且已绑定至少 1 个专有部分

**When** 业主通过首页快捷入口进入专有部分结构展示页

**Then** 页面展示与 `GET /api/miniapp/bind/status/` 响应一致的专有部分卡片列表，每张卡片显示 `location_name`（若为空则显示 `specific_part`），卡片附有展开/折叠控件，页面不出现空白或错误提示

---

### AC-2

**Given** 业主已进入结构展示页，看到专有部分列表

**When** 业主点击某一专有部分（套）卡片的展开控件

**Then** 卡片展开，显示来自**新 miniapp 业主端点**（归属过滤）的该套**房间分组**：`panel_*` sub_type 即房间（标题用 `sub_type_display`，如"书房""儿童房"），其下列出参数的 `display_name`（或 `param_name` fallback）与当前 `value`；系统级 sub_type 归入"全屋系统"分区
> ✅ **OQ-A 已解决**：复用 `get_available_sub_types`（v0.5.7 房型过滤）+ realtime 分组逻辑，参数已天然按房间(panel_*)归类，无降级（见 spec §6.2 OQ-A）。

---

### AC-3

**Given** 业主已展开某专有部分，`GET /api/miniapp/device-settings/config/` 已成功返回 `writable_attrs` 白名单

**When** 业主查看展开后的参数列表

**Then** `param_name` 在 `writable_attrs` 白名单中的参数显示"可设置"标识并附带"去设置"按钮；其余参数仅显示"只读"与当前值，无任何编辑入口

---

### AC-4

**Given** 业主已登录，但未绑定任何专有部分

**When** 业主进入结构展示页

**Then** 页面显示"您还没有绑定专有部分"提示文字以及"去绑定"按钮，点击"去绑定"导航至 `pages/bind/index.vue`；页面不显示空白卡片，不抛出未处理异常

---

### AC-5

**Given** 业主已展开某专有部分，`GET /api/miniapp/device-settings/config/` 请求失败

**When** 页面尝试进行可读/可写标注

**Then** 所有参数均显示"只读"，页面顶部显示"参数配置获取失败，可设置参数标注不可用"提示；参数当前值仍正常展示（来自 realtime-params 响应，不受影响）

---

## US-OWNER-002：主动触发屏端 MQTT 设备状态刷新

**来源**：REQ-FUNC-003（路径 A）、REQ-NFUNC-001

**角色**：已绑定有 screen_mac 专有部分的业主

**描述**：As a 已绑定有 screen_mac 专有部分的业主，I want to 点击刷新按钮主动向屏端发送 DeviceStatusRead 消息触发状态上报，So that 我能立即获取设备当前最新状态，不需要等待设备自发推送。

---

### AC-1

**Given** 业主已展开某专有部分（该专有部分有 screen_mac，`device_sn` 由新 miniapp 端点下发已知），屏端在线

**When** 业主点击该专有部分的"刷新"按钮

**Then** 按钮立即切换为"刷新中…"不可点击状态；系统经**全局 MQTT 单实例**（D-06，复用而非新建连接）向 `/screen/service/cloud/to/screen/{screenMac}` 发布 `DeviceStatusRead`（header.sn 取自 DB 下发的 `device_sn`）；收到 `DeviceStatusUpdate` 响应后，参数值更新为最新值，缓存同步写入（key：`owner_realtime_{specific_part}`），按钮恢复可点击

---

### AC-2

**Given** 业主已点击刷新，屏端在约定超时时间内未返回 `DeviceStatusUpdate`

**When** 超时计时器触发（约 10 秒）

**Then** 按钮恢复可点击，页面在该专有部分卡片内显示"设备未响应，请确认设备在线"提示；当前参数值保留不变，不清空；不弹出全局阻断性弹窗

---

### AC-3

**Given** 业主已点击刷新，按钮处于"刷新中…"锁定状态

**When** 业主在锁定期内再次点击同一专有部分的"刷新"按钮

**Then** 按钮不响应此次点击，不发出新的 `DeviceStatusRead` 消息，保持锁定至当前请求完成或超时；最短锁定时长不低于 3 秒

---

### AC-4

**Given** 业主绑定了多个专有部分，已分别展开

**When** 业主点击专有部分 A 的"刷新"按钮

**Then** 仅专有部分 A 的刷新按钮进入锁定状态，专有部分 B、C 等的刷新按钮不受影响，仍可独立点击

---

### AC-5

**Given** 业主尝试对某专有部分触发屏端刷新，但 DB 中无该套的 `device_node`（device_sn 未知，新端点未返回）

**When** 业主点击"刷新"按钮

**Then** 系统跳过路径 A（不发送 DeviceStatusRead），直接执行路径 B（调用 `POST /api/devices/ondemand-refresh/`）；按钮进入"刷新中…"状态，流程同 US-OWNER-003 AC-1
> 注（D-02）：deviceSn 来源由"前端 `ds_sns_{mac}` 缓存"改为"DB device_node"；只要 DB 有记录即走路径 A，本降级仅在 DB 无 device_node 时触发。

---

## US-OWNER-003：PLC 路径设备状态刷新（无 screen_mac 或屏端降级）

**来源**：REQ-FUNC-003（路径 B）、REQ-NFUNC-001

**角色**：已绑定专有部分的业主

**描述**：As a 绑定了无 screen_mac 专有部分（或屏端路径超时降级）的业主，I want to 通过 PLC ondemand 采集路径刷新设备参数，So that 即使屏端不可用，我也能获取设备的较新状态快照。

---

### AC-1

**Given** 业主已展开某专有部分（该专有部分无 screen_mac，不在 `device-settings/config` 的 `rooms` 列表中，或屏端路径已超时降级）

**When** 业主点击"刷新"按钮

**Then** 按钮切换为"采集中…"不可点击状态；系统调用 `POST /api/devices/ondemand-refresh/ {"specific_part": "..."}` 获得 202 响应；约 5 秒后系统重新调用 `GET /api/devices/realtime-params/?specific_part={X}`；成功后更新参数值显示并写入缓存，按钮恢复可点击

---

### AC-2

**Given** 业主点击刷新，系统调用 `POST /api/devices/ondemand-refresh/` 时网络错误或服务端返回非 202

**When** 请求失败

**Then** 按钮恢复可点击，在专有部分卡片内显示"刷新失败，请检查网络"提示；若有本地缓存则保留缓存显示；若无缓存则显示"暂无数据"占位提示

---

### AC-3

**Given** 业主点击刷新后 5 秒重取快照，`GET /api/devices/realtime-params/` 返回参数值与上次完全相同

**When** 系统写入缓存并更新显示

**Then** 界面参数值和时间戳正常更新（即使值未变化），时间戳标签显示"刚刚更新"，不提示错误

---

## US-OWNER-004：缓存优先加载设备参数

**来源**：REQ-FUNC-004

**角色**：已绑定专有部分的业主

**描述**：As a 曾经访问过结构展示页的业主，I want to 重新进入页面或展开专有部分时立即看到上次的设备参数值，So that 即使网络较慢或正在加载，也能立即看到有意义的信息而非空白。

---

### AC-1

**Given** 业主曾经展开过某专有部分，本地存在 key=`owner_realtime_{specific_part}` 的缓存数据

**When** 业主重新进入结构展示页并展开该专有部分

**Then** 缓存数据在本地读取完成后（通常 < 100ms）立即渲染参数值；界面同时显示"更新于 {相对时间，如 '3 分钟前'}"时间戳标签；后台同时异步发起 `GET /api/devices/realtime-params/?specific_part={X}` 刷新请求

---

### AC-2

**Given** 页面已展示缓存参数值，后台异步 API 请求成功返回

**When** `GET /api/devices/realtime-params/` 响应到达

**Then** 界面参数值无缝更新为 API 返回的最新值；时间戳标签更新为"刚刚更新"；新数据写入本地缓存 `owner_realtime_{specific_part}` 及时间戳 `owner_realtime_{specific_part}_ts`；页面不出现加载闪烁或布局抖动

---

### AC-3

**Given** 业主首次展开某专有部分，本地不存在该 `specific_part` 的任何缓存

**When** 业主点击展开

**Then** 展开区域立即进入"加载中…"状态（显示 spinner 或文字提示），等待 API 响应；API 成功返回后显示参数值并写入缓存；整个过程不显示空白卡片区域

---

### AC-4

**Given** 业主展开某专有部分，本地缓存存在但时间戳距今超过 5 分钟（TTL 阈值）

**When** 页面读取并渲染缓存值

**Then** 参数值正常显示（不自动清空），时间戳标签显示"数据可能已过时（更新于 N 分钟前）"；后台同时发起 API 刷新，刷新完成后标签更新为"刚刚更新"

---

### AC-5

**Given** 业主完成一次主动刷新（US-OWNER-002 或 US-OWNER-003），获得最新参数值

**When** 系统更新参数值显示

**Then** 系统同步将最新参数值和当前时间戳写入 `owner_realtime_{specific_part}` 和 `owner_realtime_{specific_part}_ts`；下次重入页面时，此次刷新结果作为最新缓存值渲染

---

## US-OWNER-005：离线/无缓存降级展示

**来源**：REQ-FUNC-005

**角色**：已绑定专有部分的业主

**描述**：As a 在无网络或 API 不可用情况下打开小程序的业主，I want to 看到明确的缓存数据或提示信息而非空白页面或崩溃，So that 我能了解当前状态并知道下一步应如何处理（检查网络、等待设备恢复等）。

---

### AC-1

**Given** 业主设备网络不可用，本地存在某专有部分的缓存数据

**When** 业主进入结构展示页并展开该专有部分

**Then** 页面立即显示缓存的设备参数值及时间戳标签；页面顶部出现"当前离线，显示缓存数据"全局横幅（不遮挡主要内容）；不弹出错误 toast；刷新按钮可点击，点击时提示"网络不可用，无法刷新"

---

### AC-2

**Given** 业主设备网络不可用，且本地无该专有部分的任何缓存

**When** 业主展开该专有部分

**Then** 展开区域显示"暂无数据，请检查网络连接后点击刷新"提示文字，并提供"重试"按钮；不显示空白卡片；不抛出未处理异常（如 unhandledrejection）

---

### AC-3

**Given** 业主网络可用，但 `GET /api/devices/realtime-params/` 返回错误（如 5xx 或超时），本地有该专有部分的缓存

**When** 后台刷新请求失败

**Then** 界面继续展示缓存参数值（不清空），时间戳标签旁追加"（刷新失败）"标注；不弹出阻断性全局弹窗；刷新按钮恢复可点击

---

### AC-4

**Given** 业主网络可用，但 `GET /api/devices/realtime-params/` 请求失败，且本地无缓存

**When** API 请求失败

**Then** 展开区域显示"获取设备数据失败，请点击重试"，附带"重试"按钮；刷新按钮也恢复可用；不显示空白区域

---

### AC-5

**Given** 业主点击"重试"或"刷新"按钮，但网络仍不可用

**When** 系统尝试发起 API 请求并失败

**Then** 按钮完成最短锁定时间（3 秒）后恢复可用，保持当前提示文字，不循环弹出多个错误 toast

---

## 决策记录与待确认问题

> 原"待确认问题清单（OQ-01~OQ-07）"已由用户拍板，迁移为决策记录见 `requirements_spec.md` §6.1（D-01~D-07）。下方仅保留**因决策与勘察新产生**、仍需 PM 在进入架构/开发前确认的问题（详见 spec §6.2）。

| # | 待确认问题 | 影响 | 建议默认 |
|---|-----------|------|---------|
| ~~OQ-A~~ | ~~参数值如何归到房间~~ — **已勘察解决**：`panel_*` sub_type 即房间，复用 `get_available_sub_types`+realtime 分组，无需新映射、无降级 | — | 已闭环（见 spec §6.2 OQ-A） |
| **OQ-B** | MQTT 全局单例的存放与 param-settings 既有连接的无回归迁移 | 前端架构 | 模块级 `useMqttClient` composable + 引用计数 |
| ~~OQ-C~~ | **已定**：并入 `param-settings.vue`，扩展为"房间结构 + 参数设置"一体页（2026-06-27） | — | 已闭环 |
| OQ-D | MQTT 超时时长（默认 10s）、单用户最大绑定数（默认 10） | 前端 | 无意见即采用默认 |

**已决策（摘要，全文见 spec §6.1）**：D-01 房间层级真实存在；D-02 deviceSn 取自 DB；D-03 TTL 5min/无清缓存按钮；D-04 性能后置/接受并行；D-05 owner 归属过滤 + admin/operator 由现有 operator 端点全量可见；D-06 MQTT 单实例；D-07 替换现有页面。
