<!--
  @feature    v1.11.3_miniapp_settings_card_room_name
  @version    1.11.3
  @author_agent sub_agent_requirement_analyst
  @status     DRAFT
  @created    2026-06-28
  @description 微信小程序参数设置页区域二设备卡片标题显示具体房间名——用户故事与验收标准
-->

# v1.11.3 参数设置页设备卡片显示房间名 用户故事

## 用户角色地图（Actor × Feature Matrix）

| Actor | 末端温控卡片显示房间名 | 系统设备卡片保持角色名 | 兜底降级 | 时序保障 | deviceSn 类型归一化 |
|-------|----------------------|----------------------|---------|---------|-------------------|
| 业主（role=user） | US-001 | US-002 | US-003 | US-004 | US-005 |

---

## 用户故事详情

---

**US-001：末端温控设备卡片显示具体房间名（正常路径）**

- **用户故事**：作为 **业主**，我希望在参数设置页的区域二中，每张末端温控设备卡片的标题显示该设备所在房间的名称（如"主卧""书房"），而不是通用的"末端温控"，以便我能准确识别并操作特定房间的设备参数。
- **关联需求**：REQ-FUNC-001、REQ-FUNC-003
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-001-01**（正常路径：structure 已缓存，deviceSn 均为字符串键）
  - Given 业主进入参数设置页，`partState[sp].structure.rooms` 已含"主卧"（`room_name="主卧"`）、"书房"（`room_name="书房"`）各一个房间，每个房间的 `devices[]` 中分别含一条记录（`device_sn` 为数字类型，如 `1001` 和 `1002`），MQTT `devices` 对象中存在键 `"1001"` 和 `"1002"`（均为末端温控，`productCode=120003`）
  - When `deviceList` 计算属性求值
  - Then `deviceSn="1001"` 的卡片 `role` 字段值为"主卧"，`deviceSn="1002"` 的卡片 `role` 字段值为"书房"；页面渲染的两张卡片标题分别显示"主卧"和"书房"，不显示"末端温控"

- **AC-001-02**（room_name 缺失，fallback 至 ori_room_name）
  - Given 结构数据中某房间 `room_name` 为空字符串，`ori_room_name="次卧"` 有值，该房间含 `device_sn=1003`（数字），MQTT `devices` 存在键 `"1003"`（`productCode=120003`）
  - When `deviceList` 计算属性求值
  - Then `deviceSn="1003"` 的卡片 `role` 字段值为"次卧"（`resolveRoomName` fallback 至 `ori_room_name`），页面显示"次卧"

- **AC-001-03**（room_name 与 ori_room_name 均缺失，最终 fallback）
  - Given 结构数据中某房间 `room_name` 和 `ori_room_name` 均为空，该房间含 `device_sn=1004`（数字），MQTT `devices` 存在键 `"1004"`（`productCode=120003`）
  - When `deviceList` 计算属性求值
  - Then `deviceSn="1004"` 的卡片 `role` 字段值为"未知房间"（`resolveRoomName` 最终 fallback），页面显示"未知房间"而非空白

---

**US-002：系统设备卡片（主温控器/新风机等）保持原角色名不变**

- **用户故事**：作为 **业主**，我希望参数设置页中主温控器、新风机、系统能源主机等系统级设备的卡片标题仍然显示其功能角色名（如"主温控器""新风机"），而不是被误替换为房间名，以便我能正确识别全屋系统设备。
- **关联需求**：REQ-FUNC-002
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-002-01**（系统设备不在 rooms 中，保持 roleMap 角色名）
  - Given `partState[sp].structure.rooms` 中所有房间的 `devices[]` 均不包含 `device_sn=2001`，MQTT `devices` 存在键 `"2001"`（`productCode=260001`），`roleMap["260001"]="主温控器"`
  - When `deviceList` 计算属性求值
  - Then `deviceSn="2001"` 的卡片 `role` 字段值为"主温控器"，页面显示"主温控器"

- **AC-002-02**（系统设备存在于 system_devices 但不在 rooms，角色名不受影响）
  - Given `partState[sp].structure.system_devices[]` 中含 `device_sn=2002`（对应新风机），`structure.rooms` 所有房间均不含该 `device_sn`，MQTT `devices` 存在键 `"2002"`（`productCode=130004`），`roleMap["130004"]="新风机"`
  - When `deviceList` 计算属性求值
  - Then `deviceSn="2002"` 的卡片 `role` 字段值为"新风机"，不显示任何房间名

- **AC-002-03**（同一套房内系统设备与末端温控同时存在，渲染正确）
  - Given MQTT `devices` 中同时存在末端温控（`"1001"`, `productCode=120003`）和主温控器（`"2001"`, `productCode=260001`），structure.rooms 中"主卧"含 `device_sn=1001`
  - When `deviceList` 计算属性求值并渲染
  - Then `"1001"` 卡片显示"主卧"，`"2001"` 卡片显示"主温控器"，两张卡片并列出现，互不干扰

---

**US-003：structure 未加载时的兜底降级（不显示空白，不崩溃）**

- **用户故事**：作为 **业主**，当网络异常或 structure 数据尚未就绪时，我希望参数设置页不因此崩溃或出现空白卡片，而是临时显示通用角色名（如"末端温控"），直到 structure 加载完成后自动更新为具体房间名。
- **关联需求**：REQ-FUNC-004
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-003-01**（structure 为 null，使用 roleMap 兜底）
  - Given `partState[sp].structure` 为 `null`（`readStructureCache` 返回 `{ data: null }`，且 `loadStructure` 尚未完成），MQTT `devices` 存在键 `"1001"`（`productCode=120003`），`roleMap["120003"]="末端温控"`
  - When `deviceList` 计算属性求值
  - Then `deviceSn="1001"` 的卡片 `role` 字段值为"末端温控"，页面正常渲染该卡片，无空白标题、无 JS 异常抛出

- **AC-003-02**（structure 为 null 时不崩溃，无未捕获异常）
  - Given `partState[sp].structure` 为 `null`，页面上有多张末端温控卡片
  - When 业主进行参数调整操作（toggle/select/number 步进）
  - Then 所有写操作正常执行，无"Cannot read properties of null"类异常，页面功能完整

- **AC-003-03**（structure 加载完成后响应式自动更新卡片标题）
  - Given 初始进入页面时 `partState[sp].structure` 为 null，卡片显示"末端温控"，随后 `loadStructure` 异步完成，`partState[sp].structure.rooms` 被赋值
  - When Vue 响应式系统触发 `deviceList` 重新计算
  - Then 卡片标题自动更新为对应房间名（如"主卧"），无需业主手动刷新页面

---

**US-004：进入参数设置页及切换房间时自动触发 structure 加载（时序保障）**

- **用户故事**：作为 **业主**，我希望在首次打开参数设置页、或切换到其他房间时，系统自动为当前专有部分加载（或复用缓存的）structure 数据，而不需要我先手动展开区域一，确保区域二的设备卡片在合理时间内能显示具体房间名。
- **关联需求**：REQ-FUNC-005
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-004-01**（进入页面时主动触发 loadStructure，缓存命中不发网络请求）
  - Given 业主本地已有有效缓存 `owner_structure_{sp}`（TTL 24h 未过期），业主**从未**在本次会话中展开过区域一
  - When 业主打开参数设置页（触发 `onLoad` 或 `onShow`）
  - Then 系统自动调用 `loadStructure(specificPart)`，`loadStructure` 从本地缓存读取数据（不发起网络请求），`partState[sp].structure` 被赋值，`deviceList` 计算属性得到房间名数据，卡片显示具体房间名

- **AC-004-02**（进入页面时主动触发 loadStructure，无缓存则发起网络请求）
  - Given 业主本地无 `owner_structure_{sp}` 缓存（或已过期），业主从未展开过区域一
  - When 业主打开参数设置页
  - Then 系统自动调用 `loadStructure(specificPart)`，触发后台网络请求获取 structure，请求完成后 `partState[sp].structure` 被赋值，`deviceList` 响应式更新卡片标题为具体房间名

- **AC-004-03**（切换房间（specific_part 变化）时触发 loadStructure）
  - Given 业主已绑定两个专有部分（`sp-A` 和 `sp-B`），当前选中 `sp-A`，切换到 `sp-B` 时 `sp-B` 无本地 structure 缓存
  - When 业主通过 picker 切换到 `sp-B`（`roomIndex` 变化导致 `specific_part` 变为 `sp-B`）
  - Then 系统自动为 `sp-B` 调用 `loadStructure("sp-B")`，`sp-B` 下的设备卡片在加载完成后显示 `sp-B` 的具体房间名；`sp-A` 的 structure 数据不受影响

---

**US-005：deviceSn 类型归一化（数字与字符串混合场景下映射不失效）**

- **用户故事**：作为 **业主**，当设备 SN 在 MQTT 消息中以字符串形式出现、在结构数据中以数字形式存储时，我希望系统能自动处理类型差异，确保房间名映射能正确命中，而不会因为类型不匹配导致卡片显示回退到"末端温控"。
- **关联需求**：REQ-FUNC-003
- **优先级**：Must Have
- **故事点**：[INFERRED — 待开发团队评估]

**验收标准：**

- **AC-005-01**（MQTT 字符串 deviceSn 与结构数据数字 device_sn 正确匹配）
  - Given MQTT `devices` 对象的键为字符串 `"1001"`，结构数据中对应 `room.devices[0].device_sn` 为数字 `1001`（类型为 number，非字符串）
  - When `deviceList` 计算属性中执行房间名查找，比较条件为 `String(device.device_sn) === sn`
  - Then `"1001"` 对应的 room 被正确找到，卡片 `role` 显示该房间的名称，不回退为"末端温控"

- **AC-005-02**（双重字符串类型场景下不产生冗余转换错误）
  - Given 结构数据中某 `device_sn` 已为字符串类型 `"1002"`（而非数字），MQTT `devices` 键为字符串 `"1002"`
  - When `deviceList` 执行 `String("1002") === "1002"` 比较
  - Then 比较结果为 `true`，映射成功，不抛出类型转换异常

---

## 需求覆盖矩阵

| 需求 ID | 描述摘要 | 覆盖的验收标准 |
|---------|---------|--------------|
| REQ-FUNC-001 | 末端温控卡片显示房间名 | AC-001-01、AC-001-02、AC-001-03 |
| REQ-FUNC-002 | 系统设备卡片保持 roleMap 角色名 | AC-002-01、AC-002-02、AC-002-03 |
| REQ-FUNC-003 | deviceSn 类型归一化 | AC-005-01、AC-005-02 |
| REQ-FUNC-004 | structure 不可用时兜底降级 | AC-003-01、AC-003-02、AC-003-03 |
| REQ-FUNC-005 | 进入页面/切换房间触发 loadStructure | AC-004-01、AC-004-02、AC-004-03 |
| REQ-NFUNC-001 | 不影响区域一现有功能 | AC-002-03（系统设备与末端温控并存）、AC-004-03（切换 sp 不影响另一 sp 数据） |
| REQ-NFUNC-002 | 不引入新后端依赖 | 全部 AC（均基于已有数据与缓存机制） |
| REQ-NFUNC-003 | deviceList 计算性能不下降 | AC-001-01（典型场景 D≤20, R≤10）|
