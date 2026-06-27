<!--
  @module v1.11.1_structure_enhancement
  @author sub_agent_system_architect
  @version 1.11.1
  @status DRAFT
  @created 2026-06-27
  @depends architecture_design_v1.11.1.md (本目录)
  @amends module_design.md (v1.11.0，本目录)
-->

# 模块设计 — v1.11.1 「我的房产」结构展示增强

**文档编号**：ARCH-MOD-v1111-001
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-27

---

## 1. 模块总览

### 1.1 新增 / 改造模块

| MOD-ID | 模块名 | 层级 | 职责概述 | 变更类型 |
|--------|--------|------|---------|---------|
| MOD-1111-BE-01 | miniapp_owner_structure 视图 | 后端·视图层 | 业主设备树结构端点，遍历 DeviceFloor→Room→Node，推导 sub_type，分离 rooms/system_devices | 新增 |
| MOD-1111-FE-01 | param-settings.vue（结构改造）| 前端·页面层 | 两阶段渲染：结构骨架先行 + 值异步叠加；connectRoom 改用 DB 全量 sns；弃用 probeNeighbors | 改造 |
| MOD-1111-FE-02 | api.js（新增 getOwnerStructure）| 前端·工具层 | 新结构端点的 HTTP 封装 | 改造（追加） |

### 1.2 不修改的模块（只读复用）

| 模块 | 理由 |
|------|------|
| `miniapp_owner_realtime_params`（views_miniapp_device_settings.py）| OQ-E1 决策：保持原样，含 PLCLatestData 过滤逻辑，仅用于值叠加 |
| `_match_panel_sub_types`（utils_room_filter.py）| ADR-1111-02 中复用，不修改 |
| `get_available_sub_types`（utils_room_filter.py）| 结构端点内部不调用（直接遍历 DeviceRoom），无需修改 |
| `useMqttClient.js`（MOD-1110-FE-01）| 接口契约不变，connectRoom 调用方式不变 |
| `screenMqtt.js`（ScreenMqtt 类）| 不变 |
| `miniapp_owner_ondemand_refresh`（MOD-1110-BE-02）| 不变 |
| `UserRoleApiGuardMiddleware`（middleware.py）| 不变，`/api/miniapp/` 整体已放行 |

---

## 2. 模块详情

---

### MOD-1111-BE-01：miniapp_owner_structure 视图（新增）

**职责**：为 role=user 业主提供设备树结构骨架端点。归属校验后，遍历 `DeviceFloor → DeviceRoom → DeviceNode`，按 ADR-1111-03 规则将设备分类为 `rooms[]`（面板房间）或 `system_devices[]`（系统级），推导 `sub_type`，返回完整骨架结构。不包含任何 PLCLatestData 字段。

**覆盖需求**：REQ-FUNC-006, REQ-FUNC-001（v1.11.1 修订版 §3/4 条）, REQ-FUNC-001-C, REQ-FUNC-004（v1.11.1 结构缓存 key）, REQ-NFUNC-004
**关联用户故事**：US-OWNER-006 AC-1/2/4/5/7, US-OWNER-001 AC-2（v1.11.1 修订版）

**实现文件**：`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`（追加至现有文件，v1.11.0 已有内容之后）

---

#### 2.1.1 公开接口契约

```
IFC-1111-BE-01: miniapp_owner_structure(request: Request) → Response

HTTP 方法:  GET
路由:       /api/miniapp/owner/structure/
权限:       @permission_classes([IsOwnerUser])

Query params:
  specific_part: str (必填)  — 如 "3-1-7-702"

── 归属校验（视图内执行，REQ-NFUNC-004）──────────────────────────────────
allowed_parts = {b.owner.specific_part
                 for b in OwnerUserBinding.objects.filter(user=request.user, active=True)
                                                  .select_related('owner')}
if specific_part not in allowed_parts → HTTP 403 {"detail": "无权访问该专有部分"}

── 设备树遍历──────────────────────────────────────────────────────────────
floors = DeviceFloor.objects.filter(owner__specific_part=specific_part)
                             .prefetch_related('rooms__devices')

sync_status = "pending" if not floors.exists() else "ok"

── sub_type 推导内联常量（ADR-1111-02）──────────────────────────────────
_PRODUCT_CODE_TO_SUB_TYPE = {
    '260001': 'main_thermostat',
    '130004': 'fresh_air',
    '270001': 'hydraulic_module',
    '250001': 'energy_meter',
    '100007': 'air_quality',
}
_PANEL_PRODUCT_CODE = '120003'

def _infer_sub_type(product_code, ori_room_name):
    if product_code == _PANEL_PRODUCT_CODE:
        matched = _match_panel_sub_types([ori_room_name])
        return next(iter(matched), '')   # 每个房间唯一匹配
    return _PRODUCT_CODE_TO_SUB_TYPE.get(product_code, '')

── 分组规则（ADR-1111-03）───────────────────────────────────────────────
for floor in floors:
    for room in floor.rooms.all():
        panel_sub_types = _match_panel_sub_types([room.ori_room_name])
        is_panel_room = bool(panel_sub_types)
        for device in room.devices.all():
            sub_type = _infer_sub_type(device.product_code, room.ori_room_name)
            entry = {device_sn, device_name, sub_type, product_code}
            if is_panel_room:
                rooms_map[room.id]['devices'].append(entry)
            else:
                system_devices.append(entry)

── device_sns 便利字段──────────────────────────────────────────────────
device_sns = [flat list of all device_sn in rooms + system_devices]

── Response 200 ──────────────────────────────────────────────────────────
{
  "success":        true,
  "specific_part":  str,
  "sync_status":    "ok" | "pending",
  "rooms": [
    {
      "room_id":      int,      -- DeviceRoom.id
      "room_name":    str,      -- DeviceRoom.room_name（OQ-E2：首选 UI 展示名）
      "ori_room_name": str,     -- DeviceRoom.ori_room_name（fallback 用）
      "devices": [
        {
          "device_sn":    int,  -- DeviceNode.device_sn
          "device_name":  str,  -- DeviceNode.device_name（OQ-E4）
          "sub_type":     str,  -- 推导值（空字符串表示未知类型）
          "product_code": str   -- DeviceNode.product_code
        }
      ]
    }
  ],
  "system_devices": [           -- "全屋系统"分区（ADR-1111-03）
    {
      "device_sn":    int,
      "device_name":  str,      -- OQ-E4：使用 device_name，非 sub_type_display
      "sub_type":     str,
      "product_code": str
    }
  ],
  "device_sns": [int],          -- 所有设备 SN 扁平列表（connectRoom 使用，ADR-1111-06）
  "sync_status_detail": str     -- 可选提示文案（sync_status="pending" 时填充）
}

── Response 400 ────────────────────────────────────────────────────────
{"success": false, "error": "specific_part 参数为必填项"}

── Response 403 ────────────────────────────────────────────────────────
{"detail": "无权访问该专有部分"}
```

**sync_status = "pending" 示例**（OQ-E5）：
```json
{
  "success": true,
  "specific_part": "3-1-7-702",
  "sync_status": "pending",
  "sync_status_detail": "设备树尚未同步，请稍后刷新",
  "rooms": [],
  "system_devices": [],
  "device_sns": []
}
```

**生产数据（3-1-7-702）预期输出示例**：
```json
{
  "success": true,
  "specific_part": "3-1-7-702",
  "sync_status": "ok",
  "rooms": [
    {
      "room_id": 12,
      "room_name": "书房",
      "ori_room_name": "三房书房",
      "devices": [{ "device_sn": 22552, "device_name": "温控面板", "sub_type": "panel_study_room", "product_code": "120003" }]
    },
    {
      "room_id": 13,
      "room_name": "次卧",
      "ori_room_name": "三房次卧",
      "devices": [{ "device_sn": 22553, "device_name": "温控面板", "sub_type": "panel_study_room", "product_code": "120003" }]
    },
    {
      "room_id": 14,
      "room_name": "主卧",
      "ori_room_name": "三房主卧",
      "devices": [{ "device_sn": 22554, "device_name": "温控面板", "sub_type": "panel_bedroom", "product_code": "120003" }]
    },
    {
      "room_id": 15,
      "room_name": "儿童房",
      "ori_room_name": "三房儿童房",
      "devices": [{ "device_sn": 22555, "device_name": "温控面板", "sub_type": "panel_children_room", "product_code": "120003" }]
    }
  ],
  "system_devices": [
    { "device_sn": 22153, "device_name": "自由方舟主机", "sub_type": "main_thermostat", "product_code": "260001" },
    { "device_sn": 22154, "device_name": "水力模块",     "sub_type": "hydraulic_module", "product_code": "270001" },
    { "device_sn": 22155, "device_name": "新风机组",     "sub_type": "fresh_air",        "product_code": "130004" },
    { "device_sn": 22156, "device_name": "能耗表",       "sub_type": "energy_meter",     "product_code": "250001" },
    { "device_sn": 22157, "device_name": "空气品质",     "sub_type": "air_quality",      "product_code": "100007" },
    { "device_sn": 22158, "device_name": "主温控-客厅",  "sub_type": "main_thermostat",  "product_code": "260001" }
  ],
  "device_sns": [22552, 22553, 22554, 22555, 22153, 22154, 22155, 22156, 22157, 22158]
}
```

---

#### 2.1.2 数据库查询估算（每次请求）

| 查询 | 预期行数 | 备注 |
|------|---------|------|
| OwnerUserBinding WHERE user + active | ≤ 10 行 | 归属校验 |
| DeviceFloor WHERE specific_part + prefetch rooms + devices | 一套约 1 楼层 × 6 房间 × 10 设备 = 60 行 | prefetch_related 一次批量查询 |

总计 2 次 DB 往返（1 次归属校验 + 1 次设备树 prefetch）。无 PLCLatestData 查询，响应速度快于 realtime-params。

---

#### 2.1.3 依赖模块列表

| 依赖 | 用途 |
|------|------|
| `IsOwnerUser`（views.py）| 权限类 |
| `OwnerUserBinding`（models.py）| 归属校验 |
| `DeviceFloor`（models.py）| 设备树根节点（通过 owner__specific_part 过滤）|
| `DeviceRoom`（models.py）| 房间节点（含 room_name, ori_room_name）|
| `DeviceNode`（models.py）| 设备节点（device_sn, device_name, product_code）|
| `_match_panel_sub_types`（utils_room_filter.py）| 面板 sub_type 推导（只读，不修改）|
| `_PRODUCT_CODE_TO_SUB_TYPE`（内联常量，本文件）| 系统级设备 sub_type 推导 |

---

### MOD-1111-FE-01：param-settings.vue（结构改造）

**职责**：在现有 v1.11.0 一体页基础上，将"我的房产"区（区域一）的渲染源从 `realtime-params` 响应的 group/sub_type 结构改为独立的结构端点响应（rooms/system_devices）；引入两阶段渲染状态机；改造 `connectRoom` 以使用 DB 全量 device_sns；弃用 `probeNeighbors` 主动调用路径。

**覆盖需求**：REQ-FUNC-001（v1.11.1 修订版）, REQ-FUNC-001-C, REQ-FUNC-004（v1.11.1 修订版）, REQ-FUNC-006（前端侧）
**关联用户故事**：US-OWNER-006 全量（AC-1~7）, US-OWNER-001 AC-2（v1.11.1 修订版）

**实现文件**：`miniprogram/subpackages/control/pages/param-settings.vue`（改造现有文件）

---

#### 2.2.1 partState 扩展（新增字段）

v1.11.0 的 `partState[sp]` 结构新增以下字段（现有字段保留不变）：

```javascript
// 新增于现有 partState[sp] 对象
partState[sp] = {
  // ── [现有 v1.11.0 字段，保持不变] ──
  expanded:          boolean,
  loading:           boolean,       // 值层 loading（realtime-params 请求）
  refreshing:        boolean,
  refreshLockUntil:  number,
  data:              object | null,  // realtime-params data 字段（值层）
  screen_mac:        string,
  device_sns:        number[],       // 来自 realtime-params 或结构端点
  tsLabel:           string,
  errorMsg:          string | null,
  refreshError:      string | null,

  // ── [v1.11.1 新增：结构层] ──
  structureLoading:  boolean,       // 结构骨架 loading（structure 请求）
  structure: {                      // 结构端点响应（来自缓存或接口）
    sync_status:     'ok' | 'pending',
    rooms: Array<{
      room_id:        number,
      room_name:      string,
      ori_room_name:  string,
      devices: Array<{
        device_sn:    number,
        device_name:  string,
        sub_type:     string,
        product_code: string,
      }>,
    }>,
    system_devices: Array<{
      device_sn:    number,
      device_name:  string,
      sub_type:     string,
      product_code: string,
    }>,
    device_sns:      number[],       // 扁平 SN 列表，供 connectRoom 使用
  } | null,
}
```

---

#### 2.2.2 公开接口契约（新增函数签名）

```
IFC-1111-FE-01-1: loadStructure(specificPart: string, forceRefresh?: boolean): Promise<void>
  -- 加载结构骨架（两阶段第一阶段）
  -- 1. 读 owner_structure_{sp} 缓存（同步 getStorageSync）
  -- 2. 命中 → ps.structure = parse(cached)；ps.structureLoading = false
  -- 3. 未命中或 forceRefresh → ps.structureLoading = true
  --    → api.getOwnerStructure(specificPart)
  --    → parse response → ps.structure = response
  --    → writeStructureCache(specificPart, response)
  --    → ps.structureLoading = false
  -- 4. sync_status == "pending" 时，ps.structure.rooms = [] → 显示"设备结构初始化中"UI

IFC-1111-FE-01-2: writeStructureCache(specificPart: string, data: object): void
  -- uni.setStorageSync('owner_structure_{sp}', JSON.stringify(data))
  -- uni.setStorageSync('owner_structure_{sp}_ts', new Date().toISOString())

IFC-1111-FE-01-3: readStructureCache(specificPart: string): { data: object | null, ts: Date | null }
  -- uni.getStorageSync('owner_structure_{sp}')
  -- uni.getStorageSync('owner_structure_{sp}_ts')
  -- 返回解析后的结构对象与时间戳

IFC-1111-FE-01-4: getParamsForSubType(realtimeData: object, subType: string): ParamEntry[]
  -- 叠加对齐函数（ADR-1111-05）
  -- 扫描 realtimeData[groupKey].sub_types[subType].params
  -- 未找到 → 返回 []（骨架参数行保持 "—"）

IFC-1111-FE-01-5: resolveRoomName(room: RoomEntry): string
  -- OQ-E2 fallback 链：room.room_name || room.ori_room_name || '未知房间'
  -- sub_type_display fallback 在此场景下不可用（结构响应无 sub_type_display）
  -- [ASSUMPTION: 若 room_name 与 ori_room_name 均为空，显示 '未知房间'；
  --   若需 sub_type_display 作为第三 fallback，需前端维护 SUB_TYPE_DISPLAY_MAP 常量]
```

---

#### 2.2.3 改造后的 toggleExpand（新流程）

```
IFC-1111-FE-01-1 覆盖 v1.11.0 的 IFC-1110-FE-02-2:

async function toggleExpand(specificPart: string): Promise<void>
  _initPartState(specificPart)
  const ps = partState[specificPart]
  ps.expanded = !ps.expanded

  if (!ps.expanded) return  // 折叠：不清空，保留缓存渲染

  // Phase 1：结构骨架（串行，骨架就绪后才进入 Phase 2）
  await loadStructure(specificPart)                  // IFC-1111-FE-01-1

  // Phase 1.5：值缓存立即叠加（同步，骨架完成后立即执行）
  const { data: cachedVal, ts: cachedVts } = readCache(specificPart)  // 现有 IFC-1110-FE-02-8
  if (cachedVal) {
    ps.data = cachedVal
    ps.tsLabel = buildTsLabel(cachedVts)
  }

  // Phase 2：后台值更新（异步，不阻塞骨架渲染）
  loadRealtimeParams(specificPart)                   // 现有 IFC-1110-FE-02-3（不 await）
```

---

#### 2.2.4 Template 结构改造

区域一"我的房产"展开内容，从 v1.11.0 的"按 data[group][sub_types] 迭代"改为"按 structure.rooms 迭代 + 按 sub_type 叠加值"：

```
<!-- v1.11.1 展开内容（骨架 + 值叠加） -->

<!-- 设备树未同步（OQ-E5）-->
<view v-if="ps.structure && ps.structure.sync_status === 'pending'" class="sync-pending">
  <text>您的房间结构尚未就绪，请等待设备初始化后刷新</text>
  <view @tap="loadStructure(sp, true)">刷新</view>
</view>

<!-- 骨架渲染：面板房间 -->
<view v-else-if="ps.structure && ps.structure.rooms">
  <view v-for="room in ps.structure.rooms" :key="room.room_id" class="room-block">
    <text class="room-title">{{ resolveRoomName(room) }}</text>    <!-- OQ-E2 fallback -->
    <view v-for="device in room.devices" :key="device.device_sn">
      <!-- 值叠加：getParamsForSubType(ps.data, device.sub_type) -->
      <view v-for="param in (getParamsForSubType(ps.data, device.sub_type))" :key="param.param_name" class="param-row">
        <text>{{ param.display_name || param.param_name }}</text>
        <text>{{ param.value != null ? param.value : '—' }}</text>
        <view v-if="isWritable(param.param_name)">
          <text class="badge-writable">可设置</text>
          <view @tap.stop="goToSettings(sp)">去设置</view>
        </view>
        <text v-else class="badge-readonly">只读</text>
      </view>
      <!-- 无 params 时（realtime-params 无数据）：显示占位行 -->
      <view v-if="getParamsForSubType(ps.data, device.sub_type).length === 0" class="no-params-placeholder">
        <text>{{ ps.loading ? '采集中…' : '暂无数据' }}</text>
      </view>
    </view>
  </view>

  <!-- 全屋系统分区 -->
  <view v-if="ps.structure.system_devices && ps.structure.system_devices.length > 0" class="room-block system-block">
    <text class="room-title">全屋系统</text>
    <view v-for="dev in ps.structure.system_devices" :key="dev.device_sn">
      <text class="device-name-system">{{ dev.device_name }}</text>  <!-- OQ-E4 -->
      <view v-for="param in (getParamsForSubType(ps.data, dev.sub_type))" :key="param.param_name" class="param-row">
        <text>{{ param.display_name || param.param_name }}</text>
        <text>{{ param.value != null ? param.value : '—' }}</text>
        <!-- 系统级参数不显示可写标注（由 isWritable 判断，通常为只读）-->
        <text class="badge-readonly">{{ isWritable(param.param_name) ? '可设置' : '只读' }}</text>
      </view>
    </view>
  </view>
</view>

<!-- 骨架加载中 -->
<view v-else-if="ps.structureLoading" class="tip-loading">
  <text>加载中…</text>
</view>
```

---

#### 2.2.5 connectRoom 改造（ADR-1111-06）

改造点集中在 `connectRoom` 函数前段（SN 种入逻辑）：

```
IFC-1111-FE-01-6 (覆盖 v1.11.0 connectRoom 的 SN 发现部分):

async function connectRoom(): void
  ...
  const sp = currentRoom.value.specific_part

  // ── v1.11.1 改造：DB 全量 SN 发现，替代 probeNeighbors（ADR-1111-06）──────

  // 优先级 1：partState 中已有 device_sns（realtime-params 已返回）
  // 优先级 2：结构缓存中的 device_sns（loadStructure 已写入）
  // 优先级 3：遗留 ds_sns_{mac} 缓存（loadSns(mac)）
  // 优先级 4：空列表（不主动 publishRead）

  let allSns: string[] = []

  if (partState[sp] && partState[sp].device_sns && partState[sp].device_sns.length > 0) {
    allSns = partState[sp].device_sns.map(String)
  } else {
    const { data: structCache } = readStructureCache(sp)  // IFC-1111-FE-01-3
    if (structCache && structCache.device_sns && structCache.device_sns.length > 0) {
      allSns = structCache.device_sns.map(String)
    } else {
      allSns = loadSns(mac)  // 遗留缓存（v1.11.0 兼容）
    }
  }

  // 种入 knownSns + 主动拉取
  if (allSns.length > 0) {
    allSns.forEach(s => knownSns.add(s))
    firstProbeDone = true
    mqttClient.publishRead(mac, allSns)          // IFC-1110-FE-01-4
    console.log('[param-settings] connectRoom DB-discovered sns:', allSns.join(','))
  }

  // probeNeighbors: DEPRECATED v1.11.1 — 函数代码保留，调用路径移除
  // 原调用点: if (!firstProbeDone) { firstProbeDone=true; probeNeighbors(mac, p.deviceSn) }
  // 现改为: // probeNeighbors DEPRECATED — noop
  ...
```

**`firstProbeDone` 标志行为变更**：
- v1.11.0：`firstProbeDone` 在第一个 DeviceStatusUpdate 收到时置 true，用于触发一次性 probeNeighbors。
- v1.11.1：`firstProbeDone` 在 connectRoom 有 allSns 时立即置 true（跳过 probeNeighbors）；若 allSns 为空，`firstProbeDone` 保持 false，但 onDeviceUpdate 回调中不再调用 probeNeighbors（改为 noop）。

---

#### 2.2.6 依赖模块列表

| 依赖 | 用途 |
|------|------|
| MOD-1111-FE-02（api.js 新增项）| `api.getOwnerStructure()` HTTP 调用 |
| MOD-1110-FE-01（useMqttClient.js，不变）| MQTT 单例：acquire/release/subscribe/publishRead/waitConfirm |
| `api.getOwnerRealtimeParams()`（api.js，v1.11.0 已有）| 值层数据来源 |
| `api.getDeviceSettingsConfig()`（api.js，不变）| broker/topics/writable_attrs |
| `_match_panel_sub_types`（间接，通过后端推导）| sub_type 推导（前端不直接调用）|
| `uni.getStorageSync/setStorageSync`（uni-app 内置）| 两层缓存读写 |
| `uni.pageScrollTo`（uni-app 内置）| "去设置"页内滚动 |

---

### MOD-1111-FE-02：api.js（新增 getOwnerStructure）

**职责**：在现有 `api.js` 中追加结构端点的 HTTP 封装，遵循现有 `http.get` 调用范式。

**覆盖需求**：REQ-FUNC-006（前端 HTTP 调用层）
**关联用户故事**：US-OWNER-006 AC-1/2

**实现文件**：`miniprogram/utils/api.js`（追加至现有 `api` 对象）

---

#### 2.3.1 公开接口契约

```javascript
// IFC-1111-FE-02-1: getOwnerStructure
// GET /api/miniapp/owner/structure/?specific_part={sp}
//
// Response 200 (sync_status="ok"):
//   { success, specific_part, sync_status, rooms, system_devices, device_sns }
//
// Response 200 (sync_status="pending"):
//   { success, specific_part, sync_status:"pending", sync_status_detail,
//     rooms:[], system_devices:[], device_sns:[] }
//
// Response 400: { success: false, error: "specific_part 参数为必填项" }
// Response 403: { detail: "无权访问该专有部分" }

getOwnerStructure: (specificPart: string) =>
  http.get('/api/miniapp/owner/structure/', { specific_part: specificPart }),
```

**依赖**：

| 依赖 | 用途 |
|------|------|
| `http`（http.js，现有）| HTTP 客户端（含 Token 认证头）|

---

## 3. 模块依赖关系图（有向，无循环）

```
── 后端 ────────────────────────────────────────────────────────────────────────

MOD-1111-BE-01 (miniapp_owner_structure)
  → [IsOwnerUser（views.py，不变）]
  → [OwnerUserBinding（models.py，不变）]
  → [DeviceFloor / DeviceRoom / DeviceNode（models.py，不变）]
  → [_match_panel_sub_types（utils_room_filter.py，只读，不变）]
  → [_PRODUCT_CODE_TO_SUB_TYPE（内联常量，本文件）]

MOD-1110-BE-01 (miniapp_owner_realtime_params，不变)
  → [以上同 v1.11.0 module_design.md §3]

MOD-1110-BE-02 (miniapp_owner_ondemand_refresh，不变)
  → [以上同 v1.11.0 module_design.md §3]

── 前端 ────────────────────────────────────────────────────────────────────────

MOD-1111-FE-02 (api.js 追加)
  → [http.js（不变）]

MOD-1110-FE-01 (useMqttClient.js，不变)
  → [ScreenMqtt（screenMqtt.js，不变）]

MOD-1111-FE-01 (param-settings.vue 改造)
  → MOD-1111-FE-02                      (getOwnerStructure HTTP 调用)
  → MOD-1110-FE-01                      (MQTT 单例，不变)
  → [api.getOwnerRealtimeParams（v1.11.0 已有，不变）]
  → [api.getDeviceSettingsConfig（v1.11.0 已有，不变）]
  → [uni.getStorageSync/setStorageSync（uni-app 内置）]
  → [uni.pageScrollTo（uni-app 内置）]

── 跨层调用（前端 → 后端，HTTP）────────────────────────────────────────────────

MOD-1111-FE-01 → MOD-1111-BE-01       (GET /api/miniapp/owner/structure/)
MOD-1111-FE-01 → MOD-1110-BE-01       (GET /api/miniapp/owner/realtime-params/，不变)
MOD-1111-FE-01 → MOD-1110-BE-02       (POST /api/miniapp/owner/ondemand-refresh/，不变)

（验证：无循环依赖，已检查）
```

---

## 4. URL 路由注册（urls_miniapp.py 追加）

在 `FreeArkWeb/backend/freearkweb/api/urls_miniapp.py` 现有 v1.11.0 路由之后追加：

```python
# v1.11.1 业主设备树结构端点（IsOwnerUser + 归属过滤）
# 只返回结构骨架（rooms/system_devices），不含任何 PLCLatestData 字段。
# 结构缓存 TTL = 24h（前端侧），后端每次请求均实时查询设备树。
path('owner/structure/', views_ds.miniapp_owner_structure,
     name='miniapp-owner-structure'),
```

---

## 5. 缓存 key 规范一览（完整版，含 v1.11.0）

| key | 类型 | 内容 | 写入时机 | TTL 判定 | 读取方 |
|-----|------|------|---------|---------|-------|
| `owner_structure_{sp}` | string (JSON) | 结构端点完整响应（含 rooms/system_devices/device_sns）| 结构端点成功响应；主动刷新结构成功 | 24h（提示，不清空）| toggleExpand Phase 1; connectRoom |
| `owner_structure_{sp}_ts` | string (ISO8601) | 结构写入时刻 | 同上 | — | 相对时间标签（可选，低优先） |
| `owner_realtime_{sp}` | string (JSON) | realtime-params `data` 字段 | realtime-params 成功；路径A/B 刷新成功 | 5min（提示"可能过时"）| toggleExpand Phase 1.5/2; onRefresh |
| `owner_realtime_{sp}_ts` | string (ISO8601) | 值写入时刻 | 同上 | — | buildTsLabel |
| `ds_sns_{mac}` | Array (JSON) | 已发现 deviceSn 集合（遗留）| DeviceStatusUpdate 收到时（persistSns）| 无 TTL | connectRoom fallback |

---

## 6. 房间名 fallback 链（OQ-E2，前端实现）

```
resolveRoomName(room):
  1. room.room_name        — DeviceRoom.room_name（短名，如"书房"）
     ↓ 为空时
  2. room.ori_room_name    — DeviceRoom.ori_room_name（长名，如"三房书房"）
     ↓ 均为空时
  3. '未知房间'             — 极端兜底

注：sub_type_display（如"书房温控"）不在此 fallback 链中，
    因结构端点不返回 sub_type_display，且该文字带技术术语不适合作房间标题。
    若需要第三 fallback 改用 sub_type_display，需前端维护 SUB_TYPE_TO_DISPLAY_MAP 常量
    [ASSUMPTION — requires PM confirmation]。
```

---

## 7. 开放问题（架构级，需 PM 确认）

| # | 问题 | 建议 | 影响模块 |
|---|------|------|---------|
| OQ-1111-A | 骨架"参数行 "—" 占位"：结构端点是否需追加 `params_skeleton`（从 DeviceConfig 查参数定义）？ | 接受 Option B（无 params_skeleton，无实时数据时参数行不显示 "—"，只显示房间/设备标题）；若要严格满足 REQ-FUNC-001-C 的 "—" 占位，选 Option A（追加 DeviceConfig 查询）| MOD-1111-BE-01 |
| OQ-1111-B | `sync_status="pending"` 时结构缓存 TTL 是否缩短为 5min（避免长时间缓存"未同步"状态）？ | 建议 TTL 缩短为 5min 仅限 pending 状态 | MOD-1111-FE-01 (writeStructureCache) |
| OQ-1111-C | `room_name` 和 `ori_room_name` 均为空时，是否显示 `sub_type_display` 作第三 fallback？若是，前端需维护 `SUB_TYPE_TO_DISPLAY_MAP`（如 `panel_study_room → '书房温控'`）| 建议显示"未知房间"即可，不引入额外维护负担 | MOD-1111-FE-01 (resolveRoomName) |
