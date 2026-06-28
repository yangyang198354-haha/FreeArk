<!--
  @feature    v1.11.3_miniapp_settings_card_room_name
  @version    1.11.3
  @status     DRAFT
  @author_agent sub_agent_software_developer
  @created    2026-06-28
  @description 实现计划：param-settings.vue 两处精确改动，实现设备卡片显示具体房间名
-->

# 实现计划 — v1.11.3 设备卡片显示具体房间名

## 实现概览

- 总改动文件：1（`miniprogram/subpackages/control/pages/param-settings.vue`）
- 总改动点：2
- 实现顺序：改动1（deviceList computed 读 structure）→ 改动2（connectRoom 末尾触发 loadStructure）
- 零新 import，零后端改动，零新文件

---

## 改动一：deviceList computed — 构建 deviceSn→房间名 Map

### 改动位置

文件：`miniprogram/subpackages/control/pages/param-settings.vue`
行号：原 321–348（deviceList computed 函数体），改后约 321–364

### 目的

区域二设备卡片的标题（`dev.role`）对末端温控设备（productCode 在 structure.rooms 里）
显示具体房间名（如"次卧"、"主卧"），而非通用的"末端温控"。
系统级设备（productCode 260001/130004/270001 等，不在任何 room.devices 里）行为不变，
仍显示 roleMap 中的通用名称。

### 实现方式

在 `return Object.keys(devices).sort()` 之前插入 Map 构建逻辑：

1. 读取 `currentRoom.value?.specific_part` 得到当前套房的 specific_part（`currentSp`）。
2. 从 `partState[currentSp]?.structure` 取出结构对象（若 partState 未初始化或 structure
   未加载则为 null，安全兜底）。
3. 若 `structure?.rooms` 存在，遍历每个 room，对每个 room.device 以
   `String(device.device_sn)` 为 key、`resolveRoomName(room)` 为 value 写入 Map。
   `String()` 归一化消除后端可能返回数字型 device_sn 与前端字符串型 key 不匹配的风险。
4. `role` 赋值改为三层优先级：
   - `roomNameMap.get(sn)`：命中则用房间名（末端温控设备）
   - `?? roleMap[d.productCode]`：Map 未命中则用 product_code_role（系统设备）
   - `?? \`设备 ${d.productCode || ''}\``：roleMap 也无则兜底

### 使用 `??` 而非 `||` 的原因

`??` 只对 `null`/`undefined` 触发 fallback，不对空字符串触发。
roleMap 中若某 productCode 的 value 为空字符串（配置错误），`??` 仍会显示该空字符串，
而 `||` 会跳过并显示兜底文本。当前上下文中 `??` 语义更精确，与已有代码风格一致。

### Vue3 响应式追踪

`deviceList` 是 `computed()`，其内部访问了：
- `config.value`（ref，Vue3 自动追踪）
- `currentRoom.value`（computed ref，Vue3 自动追踪）
- `partState[currentSp]?.structure`（partState 是 `reactive({})`，Vue3 自动追踪深层属性）

因此 `loadStructure(sp)` 异步写入 `ps.structure` 后，`deviceList` 会自动重算，
无需手动通知，无需额外的 watch。

### 零新 import 原因

`Map` 是 JS 内置全局类，不需要 import。
`currentRoom`、`partState`、`resolveRoomName` 均是文件内已定义的变量/函数，
均在 `deviceList` computed 的作用域内可直接引用。

---

## 改动二：connectRoom() 函数末尾 — 主动触发 loadStructure

### 改动位置

文件：`miniprogram/subpackages/control/pages/param-settings.vue`
行号：原 407–472（connectRoom 函数），改后在 catch 块结束后追加 2 行，约 489–491

### 目的

`connectRoom()` 在区域二参数设置区切换房间时触发。改动前，`structure` 仅在区域一
"我的房产"展开时通过 `toggleExpand → loadStructure` 加载。若用户直接进入参数设置区
而不展开区域一，`partState[sp].structure` 始终为 null，`deviceList` 的 Map 始终为空，
设备卡片标题不会显示房间名（REQ-FUNC-005 要求两个区域联动）。

通过在 `connectRoom` 末尾追加调用，确保参数设置区连接时同步触发 structure 加载，
使 `deviceList` 的 Map 在 structure 就绪后自动填充，卡片标题自动更新。

### 实现方式

在 catch 块结束之后、函数结束 `}` 之前追加两行：

```javascript
  _initPartState(sp)      // 防御性确保 partState[sp] 存在（_initPartState 是幂等函数）
  loadStructure(sp)       // 缓存命中时同步赋值，缓存未命中时异步更新（不 await，不阻塞 MQTT）
```

### 为什么不加 await

`loadStructure(sp)` 不加 `await` 是有意设计：

1. **不阻塞 MQTT 通道建立**：`connectRoom` 的核心职责是 MQTT acquire + subscribe + publishRead，
   与 structure HTTP 加载是两条独立的 I/O 路径，无依赖关系，应并发执行。
2. **Vue3 响应式自愈**：`loadStructure` 完成后写入 `ps.structure`（reactive），
   `deviceList` computed 自动重算，UI 自动更新，无需 await 等待。
3. **缓存命中路径已同步**：`loadStructure` 内部读取缓存后若命中，会同步赋值 `ps.structure`
   并 `return`，此时 computed 重算实际上是同步完成的，与 `await` 等价。

### `_initPartState(sp)` 的幂等性保证

`_initPartState` 的实现是：
```javascript
function _initPartState(specificPart) {
  if (!partState[specificPart]) {       // 仅在不存在时初始化
    partState[specificPart] = { ... }
  }
}
```
若 `partState[sp]` 已由区域一的 `initOwnerHome` 或 `toggleExpand` 初始化，则本次调用是
无操作（noop），不会覆盖已有数据（包括已加载的 structure、expanded 状态等）。

### 与 v1.11.2 的兼容性

- 系统级设备（productCode 260001/130004/270001 等）不在任何 room.devices 中，
  Map 命中为 `undefined`，`??` 触发 fallback 到 `roleMap[d.productCode]`，行为与 v1.11.2 完全一致。
- `loadStructure` 已在 `toggleExpand` 中调用，`connectRoom` 中再次调用是幂等的
  （缓存命中时 < 100ms 同步返回，缓存未命中时并发 HTTP 请求）。

---

## 验证步骤

| 步骤 | 操作 | 预期结果 | 对应 AC |
|------|------|---------|---------|
| 1 | 以业主身份登录，进入参数设置页 | 页面正常加载，无报错 | AC-001-01 |
| 2 | 等待 MQTT 连接建立，设备数据上报 | 末端温控设备卡片标题显示房间名（如"次卧"、"主卧"）而非"末端温控" | AC-001-02 |
| 3 | 检查系统设备（如全屋新风、主机）卡片标题 | 仍显示 roleMap 中的通用名称，行为不变 | AC-001-03 |
| 4 | 切换房间（多房间时），重新连接 | 新房间的末端温控设备也正确显示对应房间名 | AC-001-04 |
| 5 | 关闭网络后进入页面（structure 缓存命中） | 设备卡片标题仍正确显示（来自缓存的 structure） | AC-001-05 |
| 6 | 关闭网络后进入页面（structure 缓存未命中） | 设备卡片标题降级显示 roleMap（"末端温控"），不崩溃不空白 | AC-001-06 |
| 7 | 检查 import 语句数量 | 与 v1.11.2 完全相同，零新增 import | AC-001-07 |

---

## 架构偏差记录

无架构偏差。所有实现均在 module_design.md 和 architecture_design.md 的已批准范围内。
