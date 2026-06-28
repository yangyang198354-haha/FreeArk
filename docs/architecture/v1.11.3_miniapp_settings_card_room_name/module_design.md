<!-- @feature v1.11.3_miniapp_settings_card_room_name @version 1.11.3 @status DRAFT @author_agent sub_agent_system_architect @created 2026-06-28 @description 模块拆分设计：唯一受改动模块为 param-settings.vue，含精确改动点与接口契约 -->

# 模块设计说明书 — v1.11.3 参数设置页设备卡片显示房间名

---

## 1. 模块总览

本次迭代仅涉及一个模块，无新模块引入，无模块间依赖变化。

| MOD-ID | 模块名 | 层级 | 职责 | 依赖于 |
|--------|-------|------|------|-------|
| MOD-1113-01 | `param-settings.vue` | 前端页面组件 | 参数设置页（区域二写链路 + 区域一结构展示），v1.11.3 新增：在区域二 deviceList 中为末端温控设备查找并显示房间名 | `useMqttClient`（单例 composable）、`api.js`（已有接口）、Vue3 `reactive/computed`（运行时） |

---

## 2. 模块详情

---

**MOD-1113-01: `param-settings.vue`**

- **职责**: 微信小程序参数设置页，管理区域二（MQTT 设备参数写链路）与区域一（业主房产结构展示）的数据加载、状态维护与用户交互。v1.11.3 在区域二 `deviceList` computed 中复用区域一的 structure 缓存，为末端温控设备卡片赋予具体房间名。

- **覆盖需求**: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-FUNC-005, REQ-NFUNC-001, REQ-NFUNC-002, REQ-NFUNC-003 / US-001, US-002, US-003, US-004, US-005

- **公开接口契约**: 见第 3 节

- **依赖模块**: 无其他 MOD-NNN（单文件页面组件）

- **外部依赖**:
  - `useMqttClient`（MQTT 单例 composable，IFC-1110-FE-01）— 不变
  - `api.getDeviceSettingsConfig()`（区域二配置加载）— 不变
  - `api.getOwnerStructure(specificPart)`（structure 端点，loadStructure 内部调用）— 不变，不新增端点
  - `uni.getStorageSync / uni.setStorageSync`（本地缓存读写，loadStructure 内部）— 不变

---

## 3. 接口契约定义

以下采用 TypeScript 风格伪代码描述接口语义，不构成真实 `.ts` 文件。

### 3.1 deviceList 输出项类型（IFC-1113-01）

```typescript
interface WritableAttr {
  tag: string            // 属性标识符（如 "target_temp"）
  label: string          // 显示标签
  control: string        // 控件类型（"toggle" | "select" | "number"）
  unit?: string
  step?: number
  min?: number
  max?: number
  options: Array<{ value: unknown; label: string }>
  optionLabels: string[]
}

interface DeviceListItem {
  deviceSn: string          // MQTT devices 对象键，始终为字符串
  productCode: string | null // 设备产品码
  /**
   * 卡片标题字段（v1.11.3 语义变更）：
   *   优先级 1：roomNameMap.get(deviceSn)
   *             ← partState[currentSp].structure.rooms 中找到该 deviceSn 所属房间
   *             ← resolveRoomName(room)：room.room_name || room.ori_room_name || '未知房间'
   *   优先级 2：roleMap[productCode]
   *             ← config.product_code_role（来自 getDeviceSettingsConfig()）
   *   优先级 3：`设备 ${productCode || ''}`
   *             ← 最终 fallback，与 v1.11.2 之前行为一致
   */
  role: string
  writable: WritableAttr[]  // 过滤后的可写属性列表（length > 0 才出现在 deviceList）
}

// computed 返回类型
// deviceList: ComputedRef<DeviceListItem[]>
```

### 3.2 loadStructure 调用约定（IFC-1113-02，函数签名不变，调用方新增）

```typescript
/**
 * 为指定 specificPart 加载结构数据（含缓存优先逻辑）。
 *
 * 前置条件（Precondition）：
 *   _initPartState(specificPart) 必须在调用前已执行，
 *   即 partState[specificPart] 对象必须存在。
 *   若 partState[specificPart] 不存在，函数提前返回（无副作用）。
 *
 * 副作用：
 *   - 缓存命中：partState[specificPart].structure = cachedData（同步赋值）
 *   - 缓存未命中：发起网络请求，完成后 partState[specificPart].structure = responseData（异步赋值）
 *   - Vue3 reactive 追踪：structure 赋值触发 deviceList 等依赖此属性的 computed 重算
 *
 * 缓存键：`owner_structure_${specificPart}`，TTL 24h（由 readStructureCache 内部管理）
 */
declare function loadStructure(
  specificPart: string,
  forceRefresh?: boolean   // 默认 false；true 时跳过缓存强制网络请求
): Promise<void>
```

### 3.3 resolveRoomName 调用约定（IFC-1113-03，函数体不变，deviceList 新增调用）

```typescript
/**
 * 从结构数据的 room 对象中提取显示用房间名，fallback 链如下：
 *   room.room_name → room.ori_room_name → '未知房间'
 *
 * 不修改函数体（区域一已在用，REQ-NFUNC-001）。
 * v1.11.3 新增调用方：deviceList computed 中的 roomNameMap 构建步骤。
 */
declare function resolveRoomName(room: {
  room_name?: string
  ori_room_name?: string
  [key: string]: unknown
}): string    // 返回值永不为空字符串，最差返回 '未知房间'
```

### 3.4 _initPartState 调用约定（IFC-1113-04，函数体不变，connectRoom 新增调用）

```typescript
/**
 * 幂等初始化：若 partState[specificPart] 不存在，则创建空初始结构；
 * 若已存在，则不做任何操作（不覆盖现有数据）。
 *
 * 不修改函数体（区域一已在用，REQ-NFUNC-001）。
 * v1.11.3 新增调用方：connectRoom()，在 loadStructure(sp) 之前调用，
 * 确保满足 loadStructure 的前置条件。
 *
 * 注意：initOwnerHome() 中已为所有已绑定的 specificPart 调用过 _initPartState。
 * connectRoom() 中的新增调用是防御性保证，避免极端时序（connectRoom 先于
 * initOwnerHome 完成）下 loadStructure 提前返回。
 */
declare function _initPartState(specificPart: string): void
```

### 3.5 roomNameMap 构建逻辑（deviceList 内部中间结构，IFC-1113-05）

```typescript
/**
 * 在 deviceList computed 求值开始时构建，生命周期等同于本次求值。
 * 构建完成后，每个 device SN 的查找均为 O(1)。
 *
 * 构建步骤：
 *   1. 取 currentSp = currentRoom.value?.specific_part
 *   2. 取 structure = currentSp ? partState[currentSp]?.structure : null
 *   3. 若 structure 为 null：roomNameMap = new Map()（空 Map，所有查找 miss）
 *   4. 若 structure 存在：遍历 structure.rooms[]
 *        对每个 room，遍历 room.devices[]
 *          key = String(device.device_sn)   ← REQ-FUNC-003：类型归一化
 *          value = resolveRoomName(room)    ← REQ-FUNC-001：房间名
 *          roomNameMap.set(key, value)
 *
 * 类型：Map<string, string>  （key = deviceSn 字符串；value = 房间名字符串）
 */
type RoomNameMap = Map<string, string>
```

---

## 4. 改动点精确列表

### 改动 1：`deviceList` computed（第 321–348 行）

**改动性质**：修改现有 `computed` 函数体，在 `Object.keys(devices).sort().map(...)` 之前新增 `roomNameMap` 构建逻辑，并修改 `role` 赋值表达式。

**改动前**（第 344 行）：
```
role: roleMap[d.productCode] || `设备 ${d.productCode || ''}`,
```

**改动后语义**（不写具体实现，见接口契约 IFC-1113-01 与 IFC-1113-05）：
- 在 map 循环之前，根据 `currentRoom.value?.specific_part` 从 `partState` 取 `structure`，构建 `roomNameMap: Map<string, string>`
- 将 `role` 赋值改为三层优先级：`roomNameMap.get(sn) ?? roleMap[d.productCode] ?? fallback`

**影响行范围**：原 28 行 computed 体扩展至约 38–42 行（净增约 10–14 行）

**相关需求**：REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-004, REQ-NFUNC-003

---

### 改动 2：`connectRoom()` 末尾追加（第 407 行附近，函数末尾）

**改动性质**：在现有 `connectRoom()` 函数的最后追加 2 行调用。

**追加调用语义**：
1. `_initPartState(sp)` — 防御性确保 `partState[sp]` 已初始化（前置条件满足）
2. `loadStructure(sp)` — 为当前 `specific_part` 触发结构数据加载（缓存优先）

**`sp` 来源**：`connectRoom()` 内已有 `const sp = room.specific_part`（第 421 行），无需新增变量声明。

**影响行范围**：函数末尾新增 2 行

**相关需求**：REQ-FUNC-005, REQ-FUNC-004

---

### 新 import 结论

**无需新增任何 import 语句。**

- `_initPartState`、`loadStructure`、`resolveRoomName`、`partState`、`currentRoom` 均为 `param-settings.vue` 内 `<script setup>` 中已声明的函数/变量，直接可用。
- 原生 `Map` 是 JavaScript 内置对象，无需 import。
- ADR-1113-02 选 Option A（connectRoom 末尾追加）而非 Option C（watch），避免了引入新 `import { watch }`。

---

## 5. 不改动清单

以下内容明确不在本次修改范围内，任何对这些项目的触碰均属越界：

| 不改动项目 | 理由 |
|-----------|------|
| `resolveRoomName(room)` 函数体（第 842–844 行） | 区域一已在用且运行正常，REQ-NFUNC-001 |
| `loadStructure(specificPart)` 函数体（第 749–800 行） | 已实现缓存优先逻辑，无需修改，仅新增调用点 |
| `_initPartState(specificPart)` 函数体（第 613–632 行） | 幂等函数，逻辑完整，仅新增调用点 |
| `readStructureCache(specificPart)` 函数（第 732 行附近） | loadStructure 内部使用，不涉及 |
| `writeStructureCache(specificPart, data)` 函数 | loadStructure 内部使用，不涉及 |
| `toggleExpand(specificPart)` 函数（第 848 行附近） | 区域一展开/折叠逻辑，REQ-NFUNC-001 |
| `partState` 对象结构（structure / device_sns 等字段定义） | v1.11.1 已定型，本次只读取不变更结构 |
| `onRoomChange(e)` 函数体（第 538 行） | ADR-1113-02 选 Option A 不在此处改动 |
| 区域二写链路（`applyDevice`、`setEdit`、`curVal` 等） | 不在改动范围，REQ-NFUNC-001 精神 |
| `views_miniapp_device_settings.py` | 后端文件，REQ-NFUNC-002 |
| `device-panel.vue` | 独立页面，REQ-NFUNC-002 |
| `PRODUCT_CODE_ROLE` 配置 | PM 硬性约束 |

---

## 6. 依赖关系图（文本格式）

本次改动无模块间新依赖引入。`param-settings.vue` 内部：

```
deviceList computed
  → 读取 partState[currentSp].structure   （Vue3 reactive 追踪，无新外部依赖）
  → 调用 resolveRoomName(room)            （内部函数，不变）

connectRoom()
  → 调用 _initPartState(sp)               （内部函数，不变）
  → 调用 loadStructure(sp)                （内部函数，不变）
        → 调用 readStructureCache(sp)      （内部函数，不变）
        → 调用 api.getOwnerStructure(sp)   （已有 API，不变）
```

（无循环依赖，已验证）

---

*文档结束 — 共 1 个受改动模块（MOD-1113-01），5 个接口契约定义，2 处精确改动点，零新 import*
