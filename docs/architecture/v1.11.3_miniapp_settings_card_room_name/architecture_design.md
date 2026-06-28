<!-- @feature v1.11.3_miniapp_settings_card_room_name @version 1.11.3 @status DRAFT @author_agent sub_agent_system_architect @created 2026-06-28 @description 微信小程序参数设置页区域二末端温控设备卡片标题改为具体房间名，纯前端改动，仅修改 param-settings.vue -->

# 架构设计说明书 — v1.11.3 参数设置页设备卡片显示房间名

---

## 1. 执行摘要

### 1.1 改动范围

本次迭代目标为：将微信小程序参数设置页（`miniprogram/subpackages/control/pages/param-settings.vue`）区域二中 `productCode=120003` 末端温控设备卡片的标题，从统一的"末端温控"改为各设备所属房间的具体名称（主卧 / 书房 / 次卧 / 儿童房等）。

**改动约束（PM 硬性要求）：**

- 纯前端改动，零后端变更（REQ-NFUNC-002）
- 仅修改 `param-settings.vue`，不动其他文件
- 不动已上线的 `views_miniapp_device_settings.py` 与 `device-panel.vue`
- 不改 `PRODUCT_CODE_ROLE` 配置

### 1.2 核心策略

在 `deviceList` 计算属性中复用区域一已有的 `partState[sp].structure.rooms[]` 数据与 `resolveRoomName(room)` 函数，预构建 `Map<string,string>`（deviceSn → roomName）后执行 O(1) 查找。依托 Vue3 `reactive()` 的自动依赖追踪，`structure` 赋值时 `deviceList` 自动重算，无需额外 `watch`。

---

## 2. 系统架构概述

### 2.1 现有架构相关部分

`param-settings.vue` 内存在两个功能区域，各自维护独立的数据层：

```
区域二（参数设置）          区域一（我的房产）
──────────────────          ──────────────────
rooms[]                     partState[sp].structure
  .specific_part               .rooms[].room_name
  .screen_mac                  .rooms[].ori_room_name
  .location_name               .rooms[].devices[].device_sn (number)

devices{}  (reactive)       partState  (reactive)
  [sn] → {productCode,         [sp] → {
           attrs}                 structure: null | StructureData
                                  structureLoading: boolean
config.product_code_role         ...
  [productCode] → "角色名"    }
```

### 2.2 响应式数据流（v1.11.3 新增路径）

```
connectRoom() 末尾
  └─ _initPartState(sp)       ← 幂等，确保 partState[sp] 存在
  └─ loadStructure(sp)
        ├─ 缓存命中            ← owner_structure_{sp}，TTL 24h
        │    └─ ps.structure = cachedStructure  (同步赋值)
        └─ 缓存未命中
             └─ api.getOwnerStructure(sp)  (异步网络请求)
                  └─ ps.structure = responseData (异步赋值)

partState[sp].structure 变化
  └─ Vue3 reactive 追踪 → deviceList computed 触发重算
        └─ 构建 roomNameMap: Map<string,string>
              rooms[].devices[].device_sn → String() → roomName
        └─ 每个 device:
              role = roomNameMap.get(sn)
                   ?? roleMap[productCode]
                   ?? `设备 ${productCode||''}`
        └─ 模板 {{ dev.role }} 自动更新
```

### 2.3 partState 与 deviceList 的响应式连接

`partState` 是 `reactive({})` 对象，`deviceList` 是 `computed()`。当 `deviceList` 在求值过程中访问 `partState[sp]?.structure?.rooms`，Vue3 会自动将这些属性路径注册为依赖。一旦 `loadStructure` 将 `ps.structure` 从 `null` 赋值为结构数据，Vue3 自动失效并重算 `deviceList`，无需手动 `watch`。

前提：`currentRoom` 是另一个 `computed()`，`deviceList` 间接依赖 `roomIndex`，切换房间时 `deviceList` 也会因 `currentRoom.value` 变化而重算。

---

## 3. 架构决策记录（ADRs）

---

### ADR-1113-01：deviceList 中房间名查找策略

**Status**: Accepted

**Context**:

`deviceList` 计算属性（第 321–348 行）需要对每个 deviceSn 查找其所属房间名。房间-设备的对应关系存储于 `partState[sp].structure.rooms[]`，每个 room 含若干 `devices[].device_sn`（数字类型）。映射方式直接影响计算属性的时间复杂度与可读性（REQ-NFUNC-003、REQ-FUNC-001）。

**Options**:

**Option A：在 deviceList computed 内联遍历（嵌套循环）**

- 描述：对每个 device（外层循环 D 次），遍历所有 rooms（R 次），再遍历每个 room 的 devices（P 次），找到匹配的 room 后取名。
- 优点：逻辑直接，无额外数据结构。
- 缺点：时间复杂度 O(D × R × P)；在典型场景（D=10, R=5, P=3）下执行 150 次比较，每次 `deviceList` 重算都重复执行；可读性因三层嵌套下降。[ESTIMATE]

**Option B：预构建 Map 后 O(1) 查找（推荐）**

- 描述：在 `deviceList` 求值开始时，先一次性遍历 `structure.rooms`（R×P 次）构建 `Map<string,string>`（deviceSn → roomName），再对每个 device 以 O(1) 查找。总体 O(R×P + D)。
- 优点：
  1. 时间复杂度更优，典型场景仅 25 次遍历（5室×3设备）+ 10 次查找（REQ-NFUNC-003 满足）。
  2. 代码结构分层清晰：Map 构建与设备映射分离。
  3. `String()` 归一化集中在 Map 构建阶段，不重复出现（REQ-FUNC-003 满足）。
- 缺点：引入中间数据结构 `Map`，若 D 极小（1~2 个设备）性能差异可忽略不计。[ESTIMATE]

**Decision**:

选择 **Option B（预构建 Map）**。

理由：Option B 满足 REQ-NFUNC-003（性能不下降）的同时提升了代码可读性。`Map` 是原生 JS API，无外部依赖（REQ-NFUNC-002 满足）。典型场景（D≤20, R≤10, P≤5）下 Option A 最差 1000 次比较，Option B 最多 50+20=70 次操作，差距显著。

**Consequences**:

- 正向：满足 REQ-NFUNC-003（性能不下降）；满足 REQ-FUNC-001（房间名正确查找）；满足 REQ-FUNC-003（String() 归一化）。
- 负向：`deviceList` 内部逻辑行数增加约 8–12 行（从 ~28 行增至 ~40 行）。[ESTIMATE — 可接受]

---

### ADR-1113-02：loadStructure 触发时机

**Status**: Accepted

**Context**:

区域二依赖 `partState[sp].structure` 中的房间-设备映射数据。原有路径中，`loadStructure` 仅在区域一用户手动展开（`toggleExpand`）时被调用。若业主从未展开区域一，`structure` 将永远为 `null`，导致 `deviceList` 中所有末端温控设备回落至"末端温控"（REQ-FUNC-005、REQ-FUNC-004 背景）。需要在区域二的恰当位置主动触发 `loadStructure`。

**Options**:

**Option A：在 connectRoom() 末尾追加 _initPartState + loadStructure（推荐）**

- 描述：在 `connectRoom()` 的 MQTT 订阅逻辑完成后，追加 `_initPartState(sp); loadStructure(sp)`。`connectRoom` 是区域二首次进入（`loadConfig()` → `connectRoom()`）与切换房间（`onRoomChange()` → `connectRoom()`）的统一公共入口。
- 优点：
  1. 单一插入点，首次进入与切换房间两种场景均自动覆盖（REQ-FUNC-005 满足）。
  2. `sp` 变量（`room.specific_part`）在 `connectRoom()` 内已声明（第 421 行），无需重复提取。
  3. 无需新增 `import`，无需新建函数。
- 缺点：`connectRoom()` 职责略微扩展（从纯 MQTT 连接到兼含 structure 触发）。[ESTIMATE — 代价极小]

**Option B：在 onRoomChange() 末尾追加**

- 描述：在 `onRoomChange()` 末尾追加 `_initPartState(sp); loadStructure(sp)`。
- 优点：切换房间的触发逻辑更显式。
- 缺点：
  1. `onRoomChange()` 内部已调用 `connectRoom()`，若 Option A 已在 `connectRoom()` 末尾执行，则 Option B 会重复触发（多余调用）。[ESTIMATE]
  2. 只覆盖"切换房间"场景，不覆盖"首次进入"场景（首次进入走 `loadConfig()` → `connectRoom()`，不经过 `onRoomChange()`），仍需额外处理。
  3. `sp` 需在 `onRoomChange()` 内重新提取 `currentRoom.value?.specific_part`，代码有冗余。

**Option C：新增 watch(roomIndex)，响应式触发**

- 描述：通过 `watch(roomIndex, (newVal) => { ... loadStructure(sp) ... })` 监听房间索引变化。
- 优点：响应式驱动，无需关注调用链。
- 缺点：
  1. 需新增 `import { watch } from 'vue'`（或确认已导入），增加依赖项。[ESTIMATE — 实际影响极小]
  2. `watch` 不覆盖"首次进入"场景（`roomIndex` 初始化时不触发 `watch`），仍需在 `onLoad/onShow` 额外处理。
  3. 响应链间接，逻辑分散，调试难度高于 Option A。

**Decision**:

选择 **Option A（在 connectRoom() 末尾追加）**。

理由：`connectRoom()` 是区域二唯一的公共连接入口，覆盖"首次进入"与"切换房间"两种场景（REQ-FUNC-005 满足）。Option A 无需新 `import`（REQ-NFUNC-002 精神一致），插入点最小，回滚成本最低。

**Consequences**:

- 正向：满足 REQ-FUNC-005（进入页面及切换房间均主动触发 `loadStructure`）；满足 REQ-FUNC-004（structure 加载完成前兜底到 roleMap，加载后 Vue3 响应式自动更新）。
- 负向：`connectRoom()` 新增 2 行调用，函数体略增。若未来 `connectRoom()` 职责需要拆分，此处需一并迁移。[ESTIMATE — 低频风险，可接受]

---

### ADR-1113-03：partState 与 deviceList 的响应式连接机制

**Status**: Accepted

**Context**:

`loadStructure()` 是异步函数，`partState[sp].structure` 的赋值发生在网络请求回调或同步缓存读取后。`deviceList` 计算属性需要在 `structure` 就绪后自动重算，以驱动模板更新（REQ-FUNC-004 中 AC-003-03 验收标准）。连接机制的选择影响实现复杂度与架构干净度。

**Options**:

**Option A：deviceList computed 直接读取 partState（Vue3 自动追踪，推荐）**

- 描述：在 `deviceList` 计算函数体内直接访问 `partState[currentSp]?.structure?.rooms`。由于 `partState` 是 `reactive({})` 对象，Vue3 会自动将 `partState[currentSp].structure` 纳入 `deviceList` 的依赖图。当 `loadStructure` 赋值 `ps.structure` 时，依赖失效，`deviceList` 自动重算。
- 优点：
  1. 零额外代码：不需要 `watch`、不需要中间 `ref`、不需要手动触发。
  2. 符合 Vue3 "响应式即真源" 设计哲学，响应链最短。
  3. `currentRoom` 也是 `computed()`，`deviceList` 通过访问 `currentRoom.value.specific_part` 同时追踪房间切换，一举两得。
- 缺点：
  1. 依赖追踪是隐式的，初次阅读代码时需要了解 Vue3 响应式机制才能理解更新逻辑。[ESTIMATE — 团队已熟悉 Vue3]
  2. 若 `partState` 某个 `sp` 的键不存在（`_initPartState` 尚未调用），访问 `partState[sp]` 返回 `undefined`，需可选链（`?.`）保护。

**Option B：增加 watch(partState, ...) 手动同步**

- 描述：通过 `watch(() => partState[currentSp]?.structure, (newStructure) => { ... })` 监听 `structure` 变化，手动将房间名同步至中间 `ref`，再由 `deviceList` 读取该 `ref`。
- 优点：依赖关系显式，调试时可打断点。
- 缺点：
  1. 引入冗余中间状态（中间 `ref`），真源变为 `partState[sp].structure`，副本变为中间 `ref`，两者需保持同步，增加出错面。
  2. `watch` 监听路径需随 `currentSp` 动态变化，实现复杂（需要 `watchEffect` 或动态 getter）。
  3. 违反 YAGNI 原则：Vue3 `reactive()` 的自动追踪已完全覆盖此场景。

**Decision**:

选择 **Option A（Vue3 reactive 自动追踪）**。

理由：`partState` 是 `reactive({})`，Vue3 3.x 对 `reactive` 对象的嵌套属性访问有完整的依赖追踪支持，`ps.structure = ...` 赋值会自动触发所有访问过该属性的 `computed` 重算。Option A 零额外代码量，架构最简洁。Option B 引入冗余状态，违反单一真源原则。

**Consequences**:

- 正向：满足 REQ-FUNC-004（AC-003-03：structure 加载后卡片标题响应式自动更新，无需手动刷新）；满足 REQ-NFUNC-001（不引入新 import，不改动区域一逻辑）。
- 负向：`deviceList` 对 `partState` 的隐式依赖需在代码审查中通过注释说明，否则不熟悉 Vue3 响应式的开发者可能感到困惑。[ESTIMATE — 可通过注释缓解]

---

## 4. 数据流说明（完整时序）

### 4.1 首次进入参数设置页（structure 缓存已有）

```
onShow()
  └─ loadConfig()                     ← 区域二初始化
        └─ api.getDeviceSettingsConfig()
        └─ rooms.value = res.rooms
        └─ connectRoom()
              └─ [MQTT 订阅逻辑]
              └─ _initPartState(sp)   ← 新增：确保 partState[sp] 存在
              └─ loadStructure(sp)    ← 新增：触发 structure 加载
                    └─ readStructureCache(sp) 命中
                    └─ ps.structure = cachedStructure  [同步]
                    └─ Vue3 → deviceList 重算
                          └─ 构建 roomNameMap
                          └─ role = roomNameMap.get(sn) ?? roleMap[pc] ?? fallback
```

### 4.2 首次进入参数设置页（无缓存，需发网络请求）

```
connectRoom()
  └─ loadStructure(sp)
        └─ readStructureCache(sp) 未命中
        └─ ps.structureLoading = true
        └─ [deviceList 求值：structure 为 null → role = roleMap[pc] ?? fallback（兜底）]
        └─ api.getOwnerStructure(sp)  [异步，网络请求]
        └─ ps.structure = responseData  [异步赋值]
        └─ Vue3 → deviceList 重算  [结构就绪后自动更新]
              └─ role = roomNameMap.get(sn) ?? roleMap[pc] ?? fallback
```

### 4.3 切换房间（picker onRoomChange）

```
onRoomChange(e)
  └─ roomIndex.value = e.detail.value
  └─ connectRoom()            ← 已有调用
        └─ const sp = room.specific_part   ← 新 sp
        └─ [MQTT 重订阅]
        └─ _initPartState(sp)   ← 新增
        └─ loadStructure(sp)    ← 新增（新 sp 独立缓存）
```

---

## 5. REQ-FUNC-* 与架构决策覆盖矩阵

| 需求 ID | 描述摘要 | 覆盖架构决策 | 满足状态 |
|---------|---------|------------|---------|
| REQ-FUNC-001 | 末端温控卡片显示具体房间名 | ADR-1113-01 Option B（Map 构建 + resolveRoomName） | 满足 |
| REQ-FUNC-002 | 系统设备卡片保持 roleMap 角色名 | ADR-1113-01（Map miss → roleMap fallback） | 满足 |
| REQ-FUNC-003 | deviceSn 类型归一化 String() | ADR-1113-01（Map 构建时 String(device.device_sn)） | 满足 |
| REQ-FUNC-004 | structure 为 null 时兜底不崩溃 | ADR-1113-03 Option A（null 时 Map 为空，role 取 roleMap） | 满足 |
| REQ-FUNC-005 | 进入页面及切换房间触发 loadStructure | ADR-1113-02 Option A（connectRoom 末尾追加） | 满足 |
| REQ-NFUNC-001 | 不影响区域一现有功能 | 三条 ADR 均不修改区域一函数内部逻辑 | 满足 |
| REQ-NFUNC-002 | 零新后端依赖 | ADR-1113-02 Option A（无新 import）；ADR-1113-01（原生 Map） | 满足 |
| REQ-NFUNC-003 | deviceList 计算性能不下降 | ADR-1113-01 Option B（O(R×P + D) 优于 O(D×R×P)） | 满足 |

---

## 6. 开放问题

本文档所有 ADR 决策均有 REQ-* 依据，无 `[ASSUMPTION — requires PM confirmation]` 待确认项。

---

*文档结束 — 共 3 条 ADR（ADR-1113-01 / 02 / 03），每条 2+ 备选方案，全部 Accepted*
