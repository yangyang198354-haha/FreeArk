**特性**：微信小程序业主端首页 / 房间结构 / 主动刷新 / 缓存
**版本**：v1.11.0_miniprogram_owner_home
**状态**：DRAFT
**日期**：2026-06-27
**作者**：system-architect
**依赖**：`architecture_design.md`（本目录）

---

# 模块设计 — v1.11.0 微信小程序业主端功能迭代

**文档编号**：ARCH-MOD-v1110-001
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-27

---

## 1. 模块总览

| MOD-ID | 模块名 | 层级 | 职责概述 | 依赖于 |
|--------|--------|------|---------|--------|
| MOD-1110-BE-01 | miniapp_owner_realtime_params 视图 | 后端·视图层 | 业主实时参数查询，带归属过滤 + device_sn 下发 | MOD-1110-BE-02, 现有 PLCLatestData, DeviceConfig, DeviceNode, OwnerUserBinding |
| MOD-1110-BE-02 | miniapp_owner_ondemand_refresh 视图 | 后端·视图层 | 业主 PLC 按需采集代理，带归属过滤 | 现有 `device_ondemand_refresh` MQTT publish 逻辑 |
| MOD-1110-FE-01 | useMqttClient.js | 前端·工具层 | MQTT 全局单例 composable，引用计数管理生命周期 | 现有 ScreenMqtt（screenMqtt.js） |
| MOD-1110-FE-02 | param-settings.vue（扩展） | 前端·页面层 | 「我的房产」结构区 + 既有参数设置区一体页 | MOD-1110-FE-01, MOD-1110-FE-03, 现有 api.js |
| MOD-1110-FE-03 | api.js（新增调用） | 前端·工具层 | 新 miniapp 端点的 API 封装 | 现有 http.js |

**不修改的现有模块**（只读）：

| 模块 | 原因 |
|------|------|
| `ScreenMqtt`（screenMqtt.js）| MQTT IO 封装复用，不改变现有类接口 |
| `_owner_rooms()`（views_miniapp_device_settings.py）| 归属查询范式复用 |
| `get_available_sub_types()`（utils_room_filter.py）| 房型过滤+缓存直接调用 |
| `device_settings_config`（现有 config 端点）| broker/topics/writable_attrs 来源不变 |
| `param-settings.vue` 写链路（applyDevice/writeAttrs/waitConfirm）| OOS-02，不改变写命令逻辑 |
| `UserRoleApiGuardMiddleware`（middleware.py）| 不修改 ALLOWLIST，不扩展放行路径 |

---

## 2. 模块详情

---

### MOD-1110-BE-01：miniapp_owner_realtime_params 视图

**职责**：为 role=user 业主提供专属的实时参数查询端点，在 `IsOwnerUser` 权限下严格校验 specific_part 归属，复用 operator 版 `get_device_realtime_params` 的核心数据逻辑（PLCLatestData + DeviceConfig + get_available_sub_types），并追加 device_sn 列表和 screen_mac 用于前端 MQTT 刷新。

**覆盖需求**：REQ-FUNC-001, REQ-FUNC-003（device_sn 来源）, REQ-FUNC-004（后台刷新数据源）, REQ-NFUNC-004
**关联用户故事**：US-OWNER-001 AC-2, US-OWNER-002 AC-1/5, US-OWNER-003 AC-1, US-OWNER-004 AC-1/2

**实现文件**：`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（追加至现有文件）

**公开接口契约**：

```
IFC-1110-BE-01: miniapp_owner_realtime_params(request: Request) → Response

HTTP 方法: GET
路由: /api/miniapp/owner/realtime-params/
权限装饰器: @permission_classes([IsOwnerUser])

Query params:
  specific_part: str (必填) — 专有部分标识符，如 "1-1-2-201"

归属校验（视图内执行）:
  allowed = {b.owner.specific_part for b in OwnerUserBinding.objects.filter(user=request.user, active=True)}
  specific_part not in allowed → HTTP 403 {"detail": "无权访问该专有部分"}

核心逻辑（复用现有，不重复实现）:
  1. available_sub_types = get_available_sub_types(specific_part)      # 带 300s 缓存
  2. latest_data_qs = PLCLatestData.objects.filter(specific_part=specific_part)
  3. configs_qs = DeviceConfig.objects.filter(is_active=True).order_by('id')
  4. 按 group → sub_type → params 聚合（同 get_device_realtime_params 逻辑，可内联或提取共用函数）
  5. screen_mac = OwnerInfo.objects.get(specific_part=specific_part).unique_id  # 或从 OwnerUserBinding JOIN
  6. device_sns = list(DeviceNode.objects.filter(room__floor__owner__specific_part=specific_part)
                       .values_list('device_sn', flat=True).distinct())

Response 200: {
  "success": true,
  "specific_part": str,
  "screen_mac": str | "",           # 空字符串表示无屏端（走路径 B）
  "device_sns": list[int],          # DeviceNode.device_sn（整数），空列表表示设备树未同步
  "data": {
    "<group_key>": {
      "display": str,               # group_display
      "sub_types": {
        "<sub_type_key>": {
          "display": str,           # sub_type_display（panel_* 时即房间名）
          "params": [
            {
              "param_name": str,
              "display_name": str,
              "value": int | null,
              "collected_at": str | null,   # "YYYY-MM-DD HH:MM:SS" 格式
              "is_stale": bool              # collected_at < now - 10min
            }
          ]
        }
      }
    }
  }
}

Response 400: {"success": false, "error": "specific_part 参数为必填项"}
Response 403: {"detail": "无权访问该专有部分"}
```

**依赖模块列表**：

| 依赖 | 用途 |
|------|------|
| `IsOwnerUser`（views.py）| 权限类：仅 role=user 且已登录 |
| `OwnerUserBinding`（models.py）| 归属校验：用户 active 绑定集合 |
| `get_available_sub_types`（utils_room_filter.py）| 房型过滤，panel_* sub_type 可用集合 |
| `PLCLatestData`（models.py）| 实时参数值数据源 |
| `DeviceConfig`（models.py）| 参数名 → group/sub_type/display_name 映射 |
| `DeviceNode`（models.py）| device_sn 列表（room__floor__owner__specific_part 关联路径） |
| `OwnerInfo`（models.py）| screen_mac（unique_id 字段） |

**数据库查询估算**（每次请求）：

| 查询 | 预期行数 | 备注 |
|------|---------|------|
| OwnerUserBinding WHERE user + active | ≤ 10 行 | 用户绑定数上限 |
| get_available_sub_types（含缓存）| DeviceFloor → DeviceRoom，≤ 20 行 | 300s 缓存命中时 0 次 |
| PLCLatestData WHERE specific_part | ≤ 100 行 | 一套设备参数总量 |
| DeviceConfig（is_active=True）| ≤ 200 行 | 全量配置表，可考虑进程缓存 |
| DeviceNode WHERE specific_part（JOIN 路径）| ≤ 50 行 | 一套设备节点数 |
| OwnerInfo WHERE specific_part | 1 行 | 取 screen_mac |

---

### MOD-1110-BE-02：miniapp_owner_ondemand_refresh 视图

**职责**：为 role=user 业主提供 PLC 按需采集的代理端点，校验 specific_part 归属后，执行与 `device_ondemand_refresh` 相同的 MQTT publish 逻辑。

**覆盖需求**：REQ-FUNC-003（路径 B）, REQ-NFUNC-004
**关联用户故事**：US-OWNER-003 AC-1/2, US-OWNER-002 AC-5

**实现文件**：`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（追加）

**公开接口契约**：

```
IFC-1110-BE-02: miniapp_owner_ondemand_refresh(request: Request) → Response

HTTP 方法: POST
路由: /api/miniapp/owner/ondemand-refresh/
权限装饰器: @permission_classes([IsOwnerUser])

Request body: {"specific_part": str}

归属校验:
  allowed = {b.owner.specific_part for b in OwnerUserBinding.objects.filter(user=request.user, active=True)}
  specific_part not in allowed → HTTP 403 {"detail": "无权操作该专有部分"}

核心逻辑:
  复用 device_ondemand_refresh 的 MQTT publish 部分，建议提取为私有工具函数
  _publish_ondemand_mqtt(specific_part: str) → ("accepted"|"duplicate"|"error", detail: str)

Response 202: {"status": "accepted", "specific_part": str}
Response 202: {"status": "duplicate", "specific_part": str}   # 防重入幂等返回
Response 400: {"detail": "specific_part 为必填项"}
Response 403: {"detail": "无权操作该专有部分"}
Response 503: {"detail": "MQTT broker 不可达，无法提交采集请求"}
```

**依赖模块列表**：

| 依赖 | 用途 |
|------|------|
| `IsOwnerUser` | 权限类 |
| `OwnerUserBinding` | 归属校验 |
| `_publish_ondemand_mqtt(specific_part)` | 提取自 `device_ondemand_refresh` 的 MQTT publish 私有工具函数 |

**注意**：`_publish_ondemand_mqtt` 函数提取自 `views.py:device_ondemand_refresh` 的核心逻辑（MQTT client.publish + 防重入计时），提取后两处（operator 版 + miniapp 版）共享同一实现，不存在逻辑分叉。

---

### MOD-1110-FE-01：useMqttClient.js（新建）

**职责**：封装 MQTT 全局单例的生命周期管理（connect/disconnect/subscribe/publish），通过引用计数保证全局只有一个 ScreenMqtt 实例存在，向消费方暴露响应式 `connected` 状态和统一的操作接口。

**覆盖需求**：REQ-NFUNC-002, D-06
**关联用户故事**：US-OWNER-002 AC-1, US-OWNER-003（路径A复用连接）

**实现文件**：`miniprogram/utils/useMqttClient.js`（新建）

**公开接口契约**：

```javascript
// useMqttClient.js — 模块级单例状态（不在函数内，跨调用共享）
// _instance: ScreenMqtt | null       — MQTT 客户端实例
// _refCount: number                  — 活跃引用计数
// _connected: Ref<boolean>           — Vue ref，响应式连接状态
// _updateListeners: Function[]       — DeviceStatusUpdate 全局回调列表
// _activeSubscriptions: Set<string>  — 已订阅的 screenMac 集合（订阅去重）

export function useMqttClient() {
  return {
    // 状态（只读）
    connected: ComputedRef<boolean>,     // 计算属性包装 _connected

    // IFC-1110-FE-01-1: acquire
    // 增加引用计数；若引用计数从 0 升至 1，创建 ScreenMqtt 并 connect()
    // broker/topics: 来自 GET /api/miniapp/device-settings/config/ 响应
    acquire(broker: BrokerConfig, topics: TopicsConfig): Promise<void>,

    // IFC-1110-FE-01-2: release
    // 减少引用计数；若降至 0，调用 _instance.disconnect() 并清空单例
    release(): void,

    // IFC-1110-FE-01-3: subscribe
    // 订阅 screenMac 的上行 topic（幂等：已订阅则跳过）
    subscribe(screenMac: string): void,

    // IFC-1110-FE-01-4: publishRead
    // 向 screenMac 发布 DeviceStatusRead 消息（每个 deviceSn 一条）
    // 复用 screenMqtt.buildDeviceRead()
    publishRead(screenMac: string, deviceSns: string[]): void,

    // IFC-1110-FE-01-5: publishWrite
    // 向 screenMac 发布 DeviceWrite 消息，返回 requestId
    // 对应 param-settings 现有 mqtt.writeAttrs()
    publishWrite(screenMac: string, deviceSn: string, items: WriteItem[]): string,

    // IFC-1110-FE-01-6: waitConfirm
    // 等待 DeviceStatusUpdate 反映目标值；超时 reject
    // 对应 param-settings 现有 mqtt.waitConfirm()
    waitConfirm(deviceSn: string, attrTag: string, target: string, timeoutMs?: number): Promise<boolean>,

    // IFC-1110-FE-01-7: onDeviceUpdate
    // 注册 DeviceStatusUpdate 回调；返回注销函数（调用以取消订阅）
    onDeviceUpdate(cb: (parsed: ParsedUpdate) => void): () => void,
  }
}

// 类型定义
type BrokerConfig = { protocol: string, host: string, port: number, path: string, username: string, password: string }
type TopicsConfig = { value_uplink: string, write_downlink: string }
type WriteItem = { attrTag: string, attrValue: unknown }
type ParsedUpdate = { deviceSn: string, productCode: number | null, attrs: Record<string, unknown> }
```

**param-settings.vue 迁移映射**（零语义变更）：

| 现有调用 | 迁移后调用 |
|---------|-----------|
| `mqtt = new ScreenMqtt(broker, topics)` | `mqttClient.acquire(broker, topics)` |
| `mqtt.onDeviceUpdate(cb)` | `const off = mqttClient.onDeviceUpdate(cb)` |
| `mqtt.connect()` | （由 acquire 内部执行） |
| `mqtt.subscribeRoom(mac)` | `mqttClient.subscribe(mac)` |
| `mqtt.readStatus(mac, sns)` | `mqttClient.publishRead(mac, sns)` |
| `mqtt.writeAttrs(mac, sn, items)` | `mqttClient.publishWrite(mac, sn, items)` |
| `mqtt.waitConfirm(sn, tag, val, ms)` | `mqttClient.waitConfirm(sn, tag, val, ms)` |
| `mqtt.connected` | `mqttClient.connected.value` |
| `mqtt.disconnect()` / `mqtt = null` | `mqttClient.release()` |

**依赖模块列表**：

| 依赖 | 用途 |
|------|------|
| `ScreenMqtt`（screenMqtt.js）| MQTT IO 底层实现，不修改 |
| `buildDeviceRead`（screenMqtt.js）| 构造 DeviceStatusRead envelope |
| `ref`, `computed`（vue）| 响应式 _connected 状态 |

---

### MOD-1110-FE-02：param-settings.vue（扩展后的一体页）

**职责**：在现有参数设置页（写链路 + MQTT 直连）基础上，在页面顶部追加"我的房产"区，展示套 → 房间 → 参数的层级结构（含可读/可写标注与刷新功能），与既有参数设置区共享 `device-settings/config` 数据和 MQTT 单例连接。

**覆盖需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005, REQ-NFUNC-001, REQ-NFUNC-002
**关联用户故事**：US-OWNER-001 ~ US-OWNER-005（全量）

**实现文件**：`miniprogram/subpackages/control/pages/param-settings.vue`（改造现有文件）

**页面结构（template 布局）**：

```
<view class="ps-page">
  <!-- ── 区域一：我的房产（新增）────────────────────────────── -->
  <view class="owner-home-section">
    <text class="section-title">我的房产</text>

    <!-- 离线横幅 -->
    <view v-if="isOffline" class="offline-banner">当前离线，显示缓存数据</view>

    <!-- 无绑定 -->
    <view v-if="bindStatus.length === 0" class="tip">
      <text>您还没有绑定专有部分</text>
      <view @tap="goBind">去绑定</view>
    </view>

    <!-- 套卡片列表 -->
    <view v-for="part in bindStatus" :key="part.specific_part" class="part-card">
      <!-- 卡片头：location_name + 展开/折叠 + 刷新按钮 -->
      <view class="part-card-header" @tap="toggleExpand(part.specific_part)">
        <text>{{ part.location_name || part.specific_part }}</text>
        <view v-if="partState[part.specific_part].expanded">
          <!-- 刷新按钮 -->
          <view
            :class="{ refreshing: partState[part.specific_part].refreshing }"
            @tap.stop="onRefresh(part.specific_part)"
          >
            {{ partState[part.specific_part].refreshing ? '刷新中…' : '刷新' }}
          </view>
        </view>
      </view>

      <!-- 展开内容 -->
      <view v-if="partState[part.specific_part].expanded">
        <!-- 时间戳标签 -->
        <text class="ts-label">{{ partState[part.specific_part].tsLabel }}</text>

        <!-- loading 状态 -->
        <view v-if="partState[part.specific_part].loading">加载中…</view>

        <!-- 参数分组（group → sub_type → params） -->
        <view v-else-if="partState[part.specific_part].data">
          <view v-for="(group, gKey) in partState[part.specific_part].data" :key="gKey">
            <view v-for="(sub, sKey) in group.sub_types" :key="sKey">
              <!-- 房间标题（panel_* = 房间名；SYSTEM_LEVEL = "全屋系统"归入同一分区） -->
              <text class="room-title">{{ sub.display }}</text>
              <view v-for="param in sub.params" :key="param.param_name" class="param-row">
                <text>{{ param.display_name || param.param_name }}</text>
                <text>{{ param.value }}</text>
                <!-- 可写标注 -->
                <view v-if="isWritable(param.param_name)">
                  <text class="badge-writable">可设置</text>
                  <view @tap="goToSettings(part.specific_part)" class="btn-settings">去设置</view>
                </view>
                <text v-else class="badge-readonly">只读</text>
              </view>
            </view>
          </view>
        </view>

        <!-- 无数据降级 -->
        <view v-else class="tip-error">
          {{ partState[part.specific_part].errorMsg || '获取设备数据失败，请点击重试' }}
          <view @tap="onRefresh(part.specific_part)">重试</view>
        </view>
      </view>
    </view>
  </view>

  <!-- ── 区域二：参数设置（既有，保留）────────────────────────── -->
  <view class="param-settings-section" id="param-settings-anchor">
    <!-- 现有 room-bar + ps-body 内容不变 -->
    ...（既有 template 内容移至此处）
  </view>
</view>
```

**Script 状态扩展（新增 state，现有 state 保留）**：

```javascript
// ── 新增 state ────────────────────────────────────────────────
const bindStatus = ref([])          // GET /api/miniapp/bind/status/ 的 bindings 数组
                                    // [{specific_part, location_name, bound_at}]
const isOffline = ref(false)        // 网络离线横幅开关

// 每个 specific_part 的展开/加载/数据状态
// key = specific_part string
const partState = reactive({})
// partState[sp] 结构:
// {
//   expanded: boolean,
//   loading: boolean,
//   refreshing: boolean,
//   refreshLockUntil: number,      // Date.now() + 3000，最短锁定到期时刻
//   data: RealtimeParamsData | null,
//   screen_mac: string,
//   device_sns: number[],
//   tsLabel: string,               // "更新于 N 分钟前" / "刚刚更新" / "数据可能已过时…"
//   errorMsg: string | null,
// }

const mqttClient = useMqttClient()   // MOD-1110-FE-01

// ── 新增 computed ──────────────────────────────────────────────
// 判断参数是否可写（复用现有 config.writable_attrs）
function isWritable(paramName) {
  return !!(config.value.writable_attrs && config.value.writable_attrs[paramName])
}
```

**关键函数签名**：

```
IFC-1110-FE-02-1: initOwnerHome(): Promise<void>
  — 并行调用 getBindStatus() + getDeviceSettingsConfig()
  — 初始化 partState 各 specific_part 的空状态结构
  — 在 onShow 中调用（仅 bindStatus.length === 0 时）

IFC-1110-FE-02-2: toggleExpand(specificPart: string): Promise<void>
  — 切换 partState[sp].expanded
  — 展开时：读取缓存 → 若有缓存立即渲染 → 发起后台 API 请求
  — 折叠时：不清空数据（保留缓存渲染）

IFC-1110-FE-02-3: loadRealtimeParams(specificPart: string, forceRefresh?: boolean): Promise<void>
  — forceRefresh=true 时跳过缓存，直接 API 请求
  — 执行缓存先行逻辑（ADR-1110-06）
  — 设置 partState[sp].tsLabel 根据缓存时间戳

IFC-1110-FE-02-4: onRefresh(specificPart: string): Promise<void>
  — 防抖检查（refreshing || Date.now() < refreshLockUntil）
  — 设置 refreshing = true，refreshLockUntil = Date.now() + 3000
  — 根据 screen_mac + device_sns 决定路径 A 或路径 B
  — 完成/超时/失败后置 refreshing = false（不早于 refreshLockUntil）

IFC-1110-FE-02-5: runRefreshPathA(specificPart: string, screenMac: string, deviceSns: number[]): Promise<void>
  — mqttClient.acquire(broker, topics)
  — mqttClient.subscribe(screenMac)
  — mqttClient.publishRead(screenMac, deviceSns.map(String))
  — await DeviceStatusUpdate（timeout = 10s，各 deviceSn 独立超时判定）
  — 收到后更新 partState[sp].data + writeCache(sp)

IFC-1110-FE-02-6: runRefreshPathB(specificPart: string): Promise<void>
  — POST /api/miniapp/owner/ondemand-refresh/（MOD-1110-FE-03）
  — setTimeout 5s
  — GET /api/miniapp/owner/realtime-params/（MOD-1110-FE-03）
  — 更新 partState[sp].data + writeCache(sp)

IFC-1110-FE-02-7: writeCache(specificPart: string, data: object): void
  — uni.setStorageSync('owner_realtime_{sp}', JSON.stringify(data))
  — uni.setStorageSync('owner_realtime_{sp}_ts', new Date().toISOString())

IFC-1110-FE-02-8: readCache(specificPart: string): { data: object | null, ts: Date | null }
  — uni.getStorageSync('owner_realtime_{sp}')
  — uni.getStorageSync('owner_realtime_{sp}_ts')
  — 返回解析后的对象与时间戳

IFC-1110-FE-02-9: goToSettings(specificPart: string): void
  — 在 rooms（现有参数设置区的 rooms state）中找到对应 specific_part 的 index
  — 设置 roomIndex.value = foundIndex
  — uni.pageScrollTo({ selector: '#param-settings-anchor', duration: 300 })
```

**依赖模块列表**：

| 依赖 | 用途 |
|------|------|
| MOD-1110-FE-01（useMqttClient.js）| MQTT 单例：acquire/release/subscribe/publishRead/waitConfirm 等 |
| MOD-1110-FE-03（api.js 新增项）| getBindStatus, getOwnerRealtimeParams, ownerOndemandRefresh |
| 现有 `api.getDeviceSettingsConfig()`（api.js）| broker/topics/writable_attrs/rooms（参数设置区沿用） |
| `buildDeviceRead`（screenMqtt.js）| 构造 DeviceStatusRead 消息（通过 useMqttClient.publishRead 间接调用）|
| `uni.getStorageSync/setStorageSync`（uni-app 内置）| 缓存读写 |
| `uni.pageScrollTo`（uni-app 内置）| 「去设置」页内滚动 |

---

### MOD-1110-FE-03：api.js（新增调用项）

**职责**：在现有 `api.js` 中追加三个新 miniapp 端点的 HTTP 封装，遵循现有 `http.get/post` 调用范式。

**覆盖需求**：REQ-FUNC-001, REQ-FUNC-003（路径 B）
**关联用户故事**：US-OWNER-001 AC-2, US-OWNER-003 AC-1

**实现文件**：`miniprogram/utils/api.js`（追加至现有 `api` 对象）

**公开接口契约**：

```javascript
// IFC-1110-FE-03-1: getOwnerRealtimeParams
// GET /api/miniapp/owner/realtime-params/?specific_part={sp}
// → 200: { success, specific_part, screen_mac, device_sns, data }
// → 400: { success: false, error }
// → 403: { detail }
getOwnerRealtimeParams: (specificPart: string) =>
  http.get('/api/miniapp/owner/realtime-params/', { specific_part: specificPart }),

// IFC-1110-FE-03-2: ownerOndemandRefresh
// POST /api/miniapp/owner/ondemand-refresh/ {specific_part}
// → 202: { status: "accepted"|"duplicate", specific_part }
// → 400/403/503: 错误响应
ownerOndemandRefresh: (specificPart: string) =>
  http.post('/api/miniapp/owner/ondemand-refresh/', { specific_part: specificPart }),
```

**注意**：`getBindStatus` 已存在（`api.js:36`），`getDeviceSettingsConfig` 已存在（`api.js:88`），无需重复定义。

**依赖模块列表**：

| 依赖 | 用途 |
|------|------|
| `http`（http.js）| 现有 HTTP 客户端（含 Token 认证头） |

---

## 3. 模块依赖关系图（有向，无循环）

```
MOD-1110-FE-03 (api.js 新增) → [http.js（不变）]

MOD-1110-FE-01 (useMqttClient.js) → [ScreenMqtt（不变）]
MOD-1110-FE-01 → [buildDeviceRead（screenMqtt.js，不变）]

MOD-1110-FE-02 (param-settings.vue 扩展) → MOD-1110-FE-01
MOD-1110-FE-02 → MOD-1110-FE-03
MOD-1110-FE-02 → [api.getDeviceSettingsConfig（不变）]
MOD-1110-FE-02 → [uni.getStorageSync/setStorageSync（不变）]

MOD-1110-BE-01 (miniapp_owner_realtime_params) → [IsOwnerUser（不变）]
MOD-1110-BE-01 → [OwnerUserBinding（不变）]
MOD-1110-BE-01 → [get_available_sub_types（不变）]
MOD-1110-BE-01 → [PLCLatestData（不变）]
MOD-1110-BE-01 → [DeviceConfig（不变）]
MOD-1110-BE-01 → [DeviceNode（不变）]
MOD-1110-BE-01 → [OwnerInfo（不变）]

MOD-1110-BE-02 (miniapp_owner_ondemand_refresh) → [IsOwnerUser（不变）]
MOD-1110-BE-02 → [OwnerUserBinding（不变）]
MOD-1110-BE-02 → [_publish_ondemand_mqtt（提取自 views.py device_ondemand_refresh）]

（验证：无环路，已检查）
```

---

## 4. URL 路由注册（urls_miniapp.py 追加）

现有 `FreeArkWeb/backend/freearkweb/api/urls_miniapp.py` 追加以下两行（在现有 device-settings 路由之后）：

```python
# v1.11.0 业主端设备实时参数 + 按需采集（IsOwnerUser + 归属过滤）
path('owner/realtime-params/', views_ds.miniapp_owner_realtime_params,
     name='miniapp-owner-realtime-params'),
path('owner/ondemand-refresh/', views_ds.miniapp_owner_ondemand_refresh,
     name='miniapp-owner-ondemand-refresh'),
```

---

## 5. 缓存 key 规范一览

| key | 类型 | 内容 | 写入时机 | 读取时机 |
|-----|------|------|---------|---------|
| `owner_realtime_{specific_part}` | string（JSON）| `GET /api/miniapp/owner/realtime-params/` 的 `data` 字段 | API 成功/路径A成功/路径B成功 | toggleExpand |
| `owner_realtime_{specific_part}_ts` | string（ISO8601）| 写入缓存时的时间戳 | 同上 | 计算相对时间和 TTL 判定 |

TTL 阈值：300,000 ms（5 分钟），仅影响 UI 提示（"数据可能已过时"），不自动清空数据。

---

## 6. 可写性判定逻辑（前端）

```
前提: config.writable_attrs 来自 GET /api/miniapp/device-settings/config/
      格式: { attrTag: { label, control, ... }, ... }

isWritable(paramName):
  → paramName 在 Object.keys(config.writable_attrs) 中 → true（显示"可设置"+"去设置"）
  → 否则 → false（显示"只读"）

config 获取失败降级:
  → config.writable_attrs 为空对象 {} → 所有参数 isWritable() 返回 false → 全显"只读"
  → 页面顶部显示"参数配置获取失败，可设置参数标注不可用"（REQ-FUNC-002 详细行为 3）
```
