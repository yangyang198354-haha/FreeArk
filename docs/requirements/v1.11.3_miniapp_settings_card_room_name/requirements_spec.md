<!--
  @feature    v1.11.3_miniapp_settings_card_room_name
  @version    1.11.3
  @author_agent sub_agent_requirement_analyst
  @status     DRAFT
  @created    2026-06-28
  @description 微信小程序参数设置页区域二设备卡片标题显示具体房间名（替换通用角色名"末端温控"）
-->

# v1.11.3 参数设置页设备卡片显示房间名 需求规格说明书

## 执行摘要

### 业务背景

FreeArk 微信小程序业主端参数设置页（`miniprogram/subpackages/control/pages/param-settings.vue`）区域二「参数设置」中，设备卡片通过 `v-for="dev in deviceList"` 循环渲染，卡片标题为 `{{ dev.role }}`（模板第 229 行）。

`role` 字段由 `deviceList` 计算属性（第 321–348 行）中的 `roleMap[d.productCode] || \`设备 ${d.productCode || ''}\`` 决定。由于所有末端温控面板的 `productCode` 均为 `120003`，`PRODUCT_CODE_ROLE` 映射将其统一翻译为"末端温控"，导致同一套房内的每张末端温控卡片显示相同标题，业主无法区分哪张卡片对应哪间房间。

`partState[sp].structure.rooms[]` 已在区域一中使用（经 `resolveRoomName(room)` 取名，第 842–844 行），且每个 `room` 有 `devices[].device_sn` 字段可与 MQTT `devices` 对象中的 `deviceSn` 关联。本次迭代目标为在区域二复用上述已有数据与函数，为末端温控卡片显示具体房间名，同时保持系统设备卡片、区域一现有功能与后端接口均不受影响。

### 需求总览

- **功能需求**：5 条（REQ-FUNC-001 ~ REQ-FUNC-005）
- **非功能需求**：3 条（REQ-NFUNC-001 ~ REQ-NFUNC-003）
- **推断性需求**：0 条（全部需求均有明确业务事实来源，[INFERRED] 占比 0%）

---

## 1. 范围说明

### 1.1 本版本包含

**纯前端改动，仅修改 `param-settings.vue`（区域二 `deviceList` 计算属性）：**

- 在 `deviceList` 计算属性中，为 `productCode=120003` 的末端温控设备构建 `deviceSn → 房间名` 映射，优先显示房间名。
- 复用已有的 `resolveRoomName(room)`（第 842–844 行）与 `partState[sp].structure.rooms[]` 数据，无需新建任何函数或接口。
- 在进入参数设置页及切换房间（`roomIndex` 变化）时，主动为当前 `specific_part` 触发一次 `loadStructure`，确保 structure 数据就绪。
- 对 `deviceSn`（MQTT 字符串）与 `room.devices[].device_sn`（结构数据数字）进行 `String()` 归一化，消除类型不匹配导致的映射失败。

### 1.2 本版本不包含（Out of Scope）

**以下内容明确排除，不在本版本实施：**

1. **任何后端改动**：不修改 `views_miniapp_device_settings.py`、不修改 `PRODUCT_CODE_ROLE`、不新建后端 API 端点、不修改数据库表结构。
2. **device-panel.vue**：设备面板页使用 `sub_type_display` 字段，与本次改动无关，不做修改。
3. **其他小程序页面**：首页、结构展示页（区域一）、绑定页等均不在改动范围内。
4. **区域二写链路的其他行为**：参数提交（`applyDevice`）、toggle/select/number 控件逻辑均不在本次改动范围内。
5. **生产发布流程**：微信开发者工具上传审核由 PM/开发团队负责，本文档不作要求。

---

## 2. 功能需求

---

### REQ-FUNC-001：末端温控设备卡片显示具体房间名

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-001 |
| **描述** | 系统应当在 `deviceList` 计算属性中，为 MQTT `devices` 对象中的每个设备查找其所属房间，若找到则以 `resolveRoomName(room)`（`room.room_name \|\| room.ori_room_name \|\| '未知房间'`）作为该卡片的 `role` 字段，使末端温控卡片标题显示具体房间名（如"主卧""书房"），而非通用的"末端温控"。 |
| **来源引用** | "所有末端温控面板 productCode 均为 120003，导致每张卡片都显示'末端温控'，无法区分房间"；"`partState[sp].structure.rooms[]`：每个 room 有 `room_name`、`ori_room_name`、`devices[]`（每个 device 有 `device_sn`）"；"`resolveRoomName(room)`（第 842–844 行）：`room.room_name \|\| room.ori_room_name \|\| '未知房间'`，区域一已在用且显示正常" |
| **优先级** | Must Have |
| **备注** | 查找逻辑：遍历 `partState[currentSp].structure.rooms`，对每个 room 的 `devices[]`，比较 `String(device.device_sn) === sn`（sn 已为字符串），匹配则取 `resolveRoomName(room)`。 |

---

### REQ-FUNC-002：系统设备卡片保持原 roleMap 角色名

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-002 |
| **描述** | 系统应当对不存在于 `structure.rooms[].devices[]` 中的设备（即 `productCode` 为 260001/130004/270001 等系统级设备），保持原有行为：以 `roleMap[productCode]` 为角色名；若 `roleMap` 也无对应项，则 fallback 至 `\`设备 ${productCode || ''}\``。 |
| **来源引用** | "productCode 260001/130004/270001 等系统设备不在 `structure.rooms` 里（在 `system_devices`），自然落回 `roleMap[productCode]` 角色名，无需特殊处理"；"`role: roleMap[d.productCode] \|\| \`设备 ${d.productCode || ''}\``"（第 344 行） |
| **优先级** | Must Have |
| **备注** | 此需求确保 REQ-FUNC-001 的新映射逻辑仅影响能在 rooms 中找到对应设备的设备，系统设备行为与 v1.11.2 之前完全一致。 |

---

### REQ-FUNC-003：deviceSn 类型归一化（String() 转换）

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-003 |
| **描述** | 系统应当在比较 MQTT `devices` 对象的键（字符串类型 `deviceSn`）与结构数据 `room.devices[].device_sn`（数字类型）时，将后者统一用 `String()` 转换为字符串后再比较，以消除类型不匹配导致的映射失败。 |
| **来源引用** | "MQTT 设备消息中 deviceSn 为字符串；结构数据 `room.devices[].device_sn` 为数字。映射时需 `String()` 归一化。" |
| **优先级** | Must Have |
| **备注** | 比较表达式应为 `String(device.device_sn) === sn`，其中 `sn` 来自 `Object.keys(devices).sort()` 已为字符串。 |

---

### REQ-FUNC-004：structure 不可用时的兜底逻辑

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-004 |
| **描述** | 系统应当在 `partState[sp].structure` 为空（未加载、加载失败、TTL 过期且网络不可达）时，对所有设备回退至 `roleMap[productCode] \|\| \`设备 ${productCode || ''}\`` 作为 `role` 字段，不显示空白、不崩溃、不抛出未捕获异常。 |
| **来源引用** | "需要显式需求：进入参数设置页或切换房间时，主动为当前 `specific_part` 触发一次 `loadStructure`，保证卡片总能显示房间名"；"兜底逻辑：structure 不可用时显示 roleMap 角色名（不崩溃、不显示空白）" |
| **优先级** | Must Have |
| **备注** | `readStructureCache` 返回 `{ data: null }` 时即视为 structure 不可用。兜底值与 v1.11.2 及之前版本的现有行为保持一致，不引入回归。 |

---

### REQ-FUNC-005：进入页面及切换房间时主动触发 loadStructure

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-005 |
| **描述** | 系统应当在以下两种场景下主动为当前 `specific_part` 调用一次 `loadStructure(specificPart)`：（1）业主首次进入参数设置页（`onLoad` / `onShow`）；（2）业主通过 picker 切换房间（`roomIndex` 变化），使得 `specific_part` 发生变化时。若本地缓存（`owner_structure_{sp}`，TTL 24h）有效，`loadStructure` 内部会直接从缓存读取（不发网络请求）；若缓存过期或不存在，则发起异步请求后写入缓存，`deviceList` 在 structure 就绪后响应式自动更新。 |
| **来源引用** | "若业主从未展开区域一、且本地无 structure 缓存，映射取不到房间名会落回'末端温控'。需要显式需求：进入参数设置页或切换房间时，主动为当前 `specific_part` 触发一次 `loadStructure`，保证卡片总能显示房间名。"；"`loadStructure(specificPart)`（第 749 行）：异步拉取并写入结构缓存"；"`readStructureCache(specificPart)`（第 732 行）：从本地缓存 `owner_structure_{sp}` 读取结构数据，TTL 24h" |
| **优先级** | Must Have |
| **备注** | 此需求解决时序问题：区域二依赖 structure 数据，但区域一的展开操作（原本触发 `loadStructure` 的入口）对业主而言不是必须的操作路径。 |

---

## 3. 非功能需求

---

### REQ-NFUNC-001：不影响区域一现有功能

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-001 |
| **描述** | 本次对 `deviceList` 计算属性的修改不得影响区域一（房产结构展示）的 `resolveRoomName`、`toggleExpand`、`loadStructure` 等现有函数的行为，不得引入区域一相关的视觉或功能回归。 |
| **来源引用** | "纯前端改动，仅修改 `param-settings.vue`"；"`resolveRoomName(room)`（第 842–844 行）……区域一已在用且显示正常" |
| **优先级** | Must Have |
| **备注** | 验收标准：在多套房产、多房间场景下，区域一展示与 v1.11.2 行为完全一致。 |

---

### REQ-NFUNC-002：不引入新后端依赖

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-002 |
| **描述** | 本次改动不得新建后端 API 端点、不得修改 `PRODUCT_CODE_ROLE` 配置、不得修改 `views_miniapp_device_settings.py`，所有所需数据（structure、roleMap）均来自已有接口与本地缓存。 |
| **来源引用** | "纯前端改动，仅修改 `param-settings.vue`，不改后端、不改 `PRODUCT_CODE_ROLE`、不改 `views_miniapp_device_settings.py`、不改 `device-panel.vue`" |
| **优先级** | Must Have |
| **备注** | 后端接口层面零变更，部署风险最低。 |

---

### REQ-NFUNC-003：deviceList 计算性能不下降

| 字段 | 内容 |
|------|------|
| **ID** | REQ-NFUNC-003 |
| **描述** | 修改后的 `deviceList` 计算属性所引入的房间名映射逻辑，其时间复杂度应保持在 O(D × R × P) 以内（D=设备数，R=房间数，P=每个房间平均设备数），在典型场景（D≤20，R≤10，P≤5）下不引入可感知的渲染延迟。 |
| **来源引用** | "`deviceList` 计算性能不下降"；"`const deviceList = computed(() => { ... })`（第 321 行）" |
| **优先级** | Should Have |
| **备注** | 可在 `deviceList` 中预构建 `Map<string, string>`（deviceSn→roomName）来优化查找，但不强制要求实现方式，只要求性能不下降。 |

---

## 4. 超出范围（Out of Scope）

| 编号 | 排除内容 | 理由 |
|------|---------|------|
| OOS-01 | 修改后端 `PRODUCT_CODE_ROLE` 或 `views_miniapp_device_settings.py` | PM 明确约束：纯前端改动 |
| OOS-02 | 修改 `device-panel.vue`（设备面板页） | 该页使用 `sub_type_display` 字段，与本次改动无关 |
| OOS-03 | 新建任何后端 API 端点 | 所需数据（structure）已通过现有缓存机制可达 |
| OOS-04 | 修改 `param-settings.vue` 以外的任何前端文件 | PM 明确约束：仅修改 `param-settings.vue` |
| OOS-05 | 系统级设备（productCode 260001/130004/270001 等）角色名显示逻辑 | 此类设备不在 `structure.rooms` 里，原有 roleMap 逻辑已正确处理（REQ-FUNC-002） |
| OOS-06 | 生产发布（微信开发者工具上传审核） | 由 PM/开发团队负责 |

---

## 5. 待确认推断项

无。本文档所有需求均完全溯源至 PM 提供的已确认业务事实，无 [INFERRED] 条目。

---

## 6. 开放问题

无阻塞性开放问题。业务事实与约束条件均由 PM 明确提供。

---

## 附录：受影响代码位置速查

| 位置 | 说明 |
|------|------|
| `param-settings.vue` 第 226–269 行 | 区域二设备卡片模板（`v-for="dev in deviceList"`，第 229 行 `{{ dev.role }}`） |
| `param-settings.vue` 第 321–348 行 | `deviceList` 计算属性（需修改 `role` 赋值逻辑） |
| `param-settings.vue` 第 732 行 | `readStructureCache(specificPart)` |
| `param-settings.vue` 第 749 行 | `loadStructure(specificPart)` |
| `param-settings.vue` 第 842–844 行 | `resolveRoomName(room)` |
| `partState[sp].structure.rooms[]` | 每个 room 含 `room_name`、`ori_room_name`、`devices[].device_sn`（数字） |
