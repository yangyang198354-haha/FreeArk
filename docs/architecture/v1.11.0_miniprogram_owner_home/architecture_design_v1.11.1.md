<!--
  @module v1.11.1_structure_enhancement
  @author sub_agent_system_architect
  @version 1.11.1
  @status DRAFT
  @created 2026-06-27
  @input_docs
    - docs/requirements/v1.11.0_miniprogram_owner_home/requirements_spec_v1.11.1_structure_enhancement.md
      (status=DRAFT; PM 已在 agent_invocation 中逐项拍板 OQ-E1~E5，等同于架构阶段授权)
    - docs/requirements/v1.11.0_miniprogram_owner_home/user_stories.md
    - docs/architecture/v1.11.0_miniprogram_owner_home/architecture_design.md (v1.11.0 基线)
    - FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py (代码勘察)
    - FreeArkWeb/backend/freearkweb/api/utils_room_filter.py (代码勘察)
    - FreeArkWeb/backend/freearkweb/api/models.py (代码勘察：DeviceNode/DeviceRoom/DeviceFloor)
    - FreeArkWeb/backend/freearkweb/api/fault_consumer/constants.py (product_code 映射参考)
    - FreeArkWeb/backend/freearkweb/api/device_tree_sync.py (room_name/ori_room_name 赋值来源)
    - miniprogram/subpackages/control/pages/param-settings.vue (connectRoom/probeNeighbors 勘察)
  @amends docs/architecture/v1.11.0_miniprogram_owner_home/architecture_design.md
  @note 需求文件 status=DRAFT；PM 已对全部 OQ-E1~E5 拍板，架构依据视为批准
-->

# 架构设计 — v1.11.1 「我的房产」结构展示增强

**文档编号**：ARCH-DES-v1111-001
**版本**：1.0.0
**状态**：DRAFT
**创建日期**：2026-06-27
**基线**：本文档增补 v1.11.0 架构设计（`architecture_design.md`，同目录），v1.11.0 中未被明确覆盖的 ADR 继续有效。

---

## 1. 架构概览

### 1.1 增量定位

v1.11.0 建立了业主端参数查询（`miniapp_owner_realtime_params`）与参数设置（写链路）的基础架构。v1.11.1 在此基础上叠加以下变更：

| 变更项 | 类型 | 影响层 |
|--------|------|--------|
| 新建结构端点 `/api/miniapp/owner/structure/` | 新增 | 后端视图 + URL 路由 |
| sub_type 从 DeviceNode 推导（两路策略） | 新增 | 后端视图（内联逻辑） |
| "全屋系统"分组规则确定 | 设计决策 | 后端 + 前端 |
| 前端两阶段渲染（结构骨架 → 值叠加） | 改造 | 前端页面逻辑 + 缓存 |
| `partState` 扩展结构层字段 | 改造 | 前端状态管理 |
| `connectRoom` 改为 DB 全量 device_sns 发现 | 改造 | 前端 MQTT 连接管理 |
| `probeNeighbors` 弃用 | 删除 | 前端 |

**不变项（v1.11.0 ADR 完全继承）**：

- `miniapp_owner_realtime_params` 端点保持原有逻辑（含 `if record is None: continue` 过滤），仅用于值叠加，不再承担结构渲染职责。
- `useMqttClient.js` 单例 composable（ADR-1110-04）不变。
- `IsOwnerUser` + `OwnerUserBinding` 归属过滤范式不变。
- 缓存读写机制（`uni.getStorageSync/setStorageSync`，ADR-1110-06）不变，扩展新缓存键。
- 安全边界（middleware 不改、ALLOWLIST 不扩展）不变。

### 1.2 整体架构图（增量）

```
[小程序 param-settings.vue（扩展后 v1.11.1）]
    │
    ├─ 展开某套 ──►  [Phase 1 — 骨架]
    │                uni.getStorageSync('owner_structure_{sp}')
    │                  ├─ 缓存命中：< 100ms 渲染骨架，params 初始值 = "—"
    │                  └─ 缓存缺失：展示"加载中…"
    │                       → GET /api/miniapp/owner/structure/?specific_part=X  【新增】
    │                         └─ 遍历 DeviceFloor → DeviceRoom → DeviceNode
    │                            sub_type 推导：product_code 查表（系统级）
    │                                          _match_panel_sub_types（面板）
    │                         → 写入 owner_structure_{sp} 缓存（24h TTL）
    │
    ├─ 骨架就绪后 ─►  [Phase 2 — 值叠加]（并发执行）
    │                uni.getStorageSync('owner_realtime_{sp}')
    │                  ├─ 缓存命中：立即叠加，< 200ms 完成两层渲染
    │                  └─ 缓存缺失：后台异步
    │                       → GET /api/miniapp/owner/realtime-params/?specific_part=X （现有）
    │                         叠加键：device.sub_type ↔ realtime.data[*].sub_types[sub_type]
    │
    └─ connectRoom ─►  读取 owner_structure_{sp} 缓存 → device_sns 全量
                        → mqttClient.publishRead(mac, allSns)（种入 knownSns）
                        （不再调用 probeNeighbors）
```

### 1.3 架构风格

继承 v1.11.0：**分层单体（Layered Monolith）+ miniapp 命名空间扩展**。本版本无新服务、无新数据库表、无消息队列变更。后端新增一个视图函数，前端改造现有页面逻辑。

---

## 2. 架构决策记录（ADRs）

---

### ADR-1111-01：新建专用结构端点，而非改造现有 realtime-params 端点

**Status**：Accepted（PM 已于 agent_invocation 拍板，OQ-E1 对应决策）

**Context**：
`REQ-FUNC-001-C`（结构完整性）要求所有 `device_room` 记录必须显示，无论是否有 PLCLatestData。当前 `miniapp_owner_realtime_params` 在第 254–273 行对无 PLCLatestData 的 sub_type 整体删除，导致面板丢失（根因代码见需求文档附录）。需决定通过新建端点还是改造现有端点来解决。（REQ-FUNC-006，REQ-FUNC-001-C）

**Options**：

- **Option A（选择）：新建 `GET /api/miniapp/owner/structure/`**
  - 优点：职责清晰（结构 vs 值）；TTL 差异（24h vs 5min）得以独立管理；零回归风险（不触碰现有 realtime-params 逻辑和测试套件）；设备树遍历路径（DeviceFloor → DeviceRoom → DeviceNode）天然包含 room_name，无需强行 JOIN；前端可独立缓存骨架。
  - 缺点：前端展开时需两次 HTTP 请求（structure + realtime），在结构缓存命中时退化为一次（realtime 本身在后台并发，不阻塞骨架渲染）。

- **Option B：改造 `miniapp_owner_realtime_params`，去掉 `if record is None: continue` + 补 room_name JOIN**
  - 优点：只改一处后端函数，URL 不变。
  - 缺点：结构与值耦合在同一响应，TTL 只能取最短（5min）；room_name 需额外 JOIN device_room，破坏现有数据结构语义；影响现有测试 `test_miniapp_owner_v1110.py`；无法实现独立的 24h 结构缓存。

**Decision**：选择 Option A。保持现有 `miniapp_owner_realtime_params` 完全不变（含其过滤逻辑），新建 `miniapp_owner_structure` 视图函数，注册于 `urls_miniapp.py`，路由 `/api/miniapp/owner/structure/`。

**Consequences**：
- 正向：现有 realtime-params 端点零改动，零回归风险；结构缓存（24h）与值缓存（5min）独立生命周期；frontend 骨架渲染与值叠加完全解耦。
- 负向：前端首次展开需两个网络请求（骨架 + 值），结构缓存命中后只需一个（值）；后端新增约 80 行视图代码。

---

### ADR-1111-02：DeviceNode → sub_type 推导策略

**Status**：Accepted

**Context**：
新结构端点的响应需包含每个设备的 `sub_type` 字段（供前端做参数值叠加的对齐键）。代码勘察确认：`DeviceNode` 模型无 `sub_type` 字段（见 `models.py:506`），`sub_type` 是 `DeviceConfig` 的概念（参数分组），与 `DeviceNode` 之间无直接外键关联。必须设计推导策略。（REQ-FUNC-006，REQ-FUNC-001 修订版）

**代码勘察发现**：
- `fault_consumer/constants.py:SUB_TYPE_ROOM_FILTER` 已实测验证 product_code ↔ 设备类型映射：
  - `260001` → 主温控（客厅，main_thermostat）
  - `130004` → 新风机组（fresh_air）
  - `270001` → 水力模块（hydraulic_module）
  - `250001` → 能耗表（energy_meter）
  - `100007` → 空气品质（air_quality）
  - `120003` → 温控面板（多房型，需结合 ori_room_name 区分）
- `utils_room_filter.py:_match_panel_sub_types([ori_room_name])` 已将 ori_room_name 关键词映射到 panel_* sub_type（含四房/三房区分）。

**Options**：

- **Option A（选择）：product_code 查表（系统级设备）+ `_match_panel_sub_types`（面板设备）**
  - 系统级设备：`product_code != '120003'` 时查 `_PRODUCT_CODE_TO_SUB_TYPE` 字典（product_code 是屏端硬编码的稳定标识符）。
  - 面板设备：`product_code == '120003'` 时调用 `_match_panel_sub_types([room.ori_room_name])` 取首个结果（每个房间唯一对应一个 panel sub_type）。
  - 优点：product_code 是稳定硬件标识，远比设备名称字符串可靠；复用已实测 product_code 数据（fault_consumer constants 验证过生产数据）；panel 推导复用现有 `_match_panel_sub_types`，逻辑一致。
  - 缺点：product_code 与 sub_type 的映射字典需维护，新设备类型引入时需同步更新。[ASSUMPTION — requires PM confirmation: 是否存在生产中 product_code=260001 但不属于 main_thermostat 的设备？勘察数据显示无，但未穷举]

- **Option B：device_name 关键词匹配（系统级设备）**
  - 优点：不依赖 product_code 字典。
  - 缺点：device_name 是屏端配置的用户可见字符串，可能因设备型号、版本或用户重命名而变化，稳定性远低于 product_code；字符串匹配存在歧义（如"温控"可能出现在多类设备名中）。

**Decision**：选择 Option A。在 `views_miniapp_device_settings.py` 中内联定义：

```
_PRODUCT_CODE_TO_SUB_TYPE = {
    '260001': 'main_thermostat',
    '130004': 'fresh_air',
    '270001': 'hydraulic_module',
    '250001': 'energy_meter',
    '100007': 'air_quality',
}
_PANEL_PRODUCT_CODE = '120003'
```

推导逻辑（伪代码，非实现）：
```
def _infer_sub_type(product_code, ori_room_name):
    if product_code == PANEL_PRODUCT_CODE:
        matched = _match_panel_sub_types([ori_room_name])
        return first(matched) or ''          # 每个房间唯一匹配，无歧义
    return PRODUCT_CODE_TO_SUB_TYPE.get(product_code, '')
```

**Consequences**：
- 正向：product_code 稳定可靠；panel sub_type 推导与现有过滤逻辑（utils_room_filter.py）完全一致，不引入新映射逻辑。
- 负向：若未来出现新设备类型（new product_code），需同步更新 `_PRODUCT_CODE_TO_SUB_TYPE`；未知 product_code 的设备 sub_type 返回空字符串（前端叠加时跳过，不影响骨架展示）。

---

### ADR-1111-03："全屋系统"分组规则——以 ori_room_name 面板匹配为判定

**Status**：Accepted（OQ-E4 对应决策）

**Context**：
结构端点需将设备分为两类：panel 房间设备（对应 rooms[] 数组）和系统级设备（对应 system_devices[]，UI 归入"全屋系统"分区）。需确定分组判定规则。（REQ-FUNC-001 修订版 第 4 条，US-OWNER-006）

**生产数据（3-1-7-702）确认**：
- "全屋" room 含：自由方舟主机 (260001)、水力模块 (270001)、新风机组 (130004)、能耗表 (250001)、空气品质 (100007)
- "客厅" room 含：主温控-客厅 (260001)
- "书房/次卧/主卧/儿童房" rooms 含：温控面板 (120003) ×4

**Options**：

- **Option A（选择）：`_match_panel_sub_types([room.ori_room_name])` 返回空集 → 系统级设备**
  - 优点：直接复用现有函数，与 `get_available_sub_types` 的房型过滤逻辑完全一致；无需维护额外的房间名白名单（如 "全屋"/"客厅"），对非标准命名亦可正确分组。
  - 缺点：依赖 `_match_panel_sub_types` 关键词匹配准确性（但该函数已在生产 40 个专有部分扫描中验证，100% 准确）。

- **Option B：`room_name in ('全屋', '客厅', ...)` 白名单**
  - 优点：直观易懂。
  - 缺点：依赖 room_name 字符串固定，新设备或不同用房命名方案下脆弱；需维护白名单。

**Decision**：选择 Option A。遍历 DeviceRoom 时：调用 `_match_panel_sub_types([room.ori_room_name])`；若结果非空 → 该 room 的设备进入 `rooms[]`；若结果为空 → 该 room 的设备进入 `system_devices[]`。

**系统设备名来源**：`device_node.device_name`（OQ-E4 拍板），直接从 DB 取值，不使用 `sub_type_display`。

**Consequences**：
- 正向：一套逻辑，无冗余判定；与现有 `utils_room_filter.py` 完全对齐，不引入语义分叉。
- 负向：若 `_match_panel_sub_types` 将来扩展新关键词（新房型），"全屋系统"分组自动跟进，无需额外改动结构端点。

---

### ADR-1111-04：结构骨架与参数值两阶段渲染

**Status**：Accepted（REQ-FUNC-004 修订版，OQ-E3 对应决策）

**Context**：
用户展开专有部分时，既要快速看到完整房间骨架（所有房间可见，REQ-FUNC-001-C），又要尽快看到参数值（REQ-FUNC-004）。两类数据的 TTL 差异大（结构 24h vs 值 5min），需要两套独立缓存层和渲染策略。（US-OWNER-006 AC-1/AC-2/AC-6）

**Options**：

- **Option A（选择）：两阶段渲染——结构骨架先行，值异步叠加**
  - 阶段一（同步，< 100ms）：读结构缓存 → 渲染所有房间（params 初始值 "—"）；若无结构缓存则 loading。
  - 阶段二（并发异步）：读值缓存或调用 realtime-params → 值叠加到骨架（无重绘骨架结构）。
  - 优点：实现 REQ-FUNC-001-C（所有房间可见，不依赖值）；两级缓存独立 TTL；骨架即时可见（< 100ms），值后到（< 200ms 或网络延迟）；骨架与值解耦，值失败不影响骨架显示。
  - 缺点：前端状态管理复杂度增加（partState 需同时持有 structure 和 data 两层）；模板需区分骨架渲染和值叠加逻辑。

- **Option B：单阶段渲染——等 realtime-params 完整响应后一次渲染**
  - 优点：前端逻辑简单。
  - 缺点：realtime-params 有过滤逻辑（bug），无法保证所有房间显示（REQ-FUNC-001-C 不满足）；等待网络响应期间展开区空白（体验差）。

**Decision**：选择 Option A。详细两阶段流程见 §3.1。

**结构缓存 TTL**：24 小时（OQ-E3 拍板）。缓存使用 `owner_structure_{sp}` + `owner_structure_{sp}_ts` 两个 key；TTL 超期后仍可显示（不自动清空），但时间戳标签反映"结构数据较旧"；用户主动下拉刷新时同时强制刷新两层缓存。

**Consequences**：
- 正向：骨架先于值渲染，所有房间保证可见（REQ-FUNC-001-C 满足）；缓存命中时 < 200ms 完成两层渲染（US-OWNER-006 AC-6 满足）。
- 负向：`partState` 需扩展 `structure` 子对象，template 需重构为按 `structure.rooms` 迭代而非按 `data`（现有 realtime-params group 结构）迭代；首次无缓存时需两个串行网络请求（structure 先完成，随后并发 realtime-params）。

---

### ADR-1111-05：骨架与值叠加的对齐键设计

**Status**：Accepted

**Context**：
结构端点返回 `rooms[].devices[].sub_type`；realtime-params 端点返回 `data[group_key].sub_types[sub_type_key].params`。前端叠加时需一个可靠的对齐键将两套响应关联。（REQ-FUNC-001 修订版第 4 条，US-OWNER-006 AC-3）

**Options**：

- **Option A（选择）：以 `sub_type` 字符串为对齐键**
  - 前端叠加逻辑：对结构中每个 `device.sub_type`，扫描 `realtime.data[*].sub_types[sub_type]` 查找匹配的 params 列表。
  - 优点：sub_type 是两个端点共享的语义键，精确唯一（每个 sub_type 在 DeviceConfig 中唯一，对应一套参数定义）；前端无需维护额外映射表；realtime-params 无值时（sub_type 缺失）返回 null，骨架参数行保持 "—" 占位。
  - 缺点：realtime-params 响应的 group_key 结构需要前端线性扫描（O(groups × sub_types)，组数 ≤ 5，sub_type 数 ≤ 10，性能可忽略）；若 sub_type 推导错误（ADR-1111-02 失败），叠加会找不到 params（但骨架仍显示，只是值为 "—"）。

- **Option B：以 `device_sn` 为对齐键**
  - realtime-params 响应当前未包含 device_sn 作为参数行的 key（以 param_name 为叶子节点），重构成本高。

**Decision**：选择 Option A。前端叠加函数签名（接口契约，非实现）：

```
getParamsForSubType(realtimeData: object, subType: string) → ParamEntry[]
  -- 扫描 realtimeData[*].sub_types[subType].params
  -- 未找到 → 返回空数组（骨架参数行保持 "—"，不报错）
```

参数行叠加键：`param_name`（结构端点不返回 param 定义，只返回设备骨架；param 列表来自 realtime-params 或 DeviceConfig）。

[ASSUMPTION — requires PM confirmation]：结构端点仅返回设备节点骨架（device_sn/device_name/sub_type/product_code），不返回参数定义（display_name/param_name 列表）。参数定义由 realtime-params 提供（已包含 display_name/param_name）。若 realtime-params 无数据，骨架只显示房间标题 + 设备行，params 行为空（无 "—" 占位行）——这与 REQ-FUNC-001-C "参数行骨架"（每个参数行均显示 "—"）略有冲突。**解决方案**：结构端点或前端从 DeviceConfig 中预取参数定义（param_name/display_name），供骨架渲染。见 §3.1 开放问题 OQ-1111-A。

**Consequences**：
- 正向：叠加逻辑简单；sub_type 为稳定语义键；realtime-params 无数据时降级优雅（不崩溃，保持 "—"）。
- 负向：若叠加键（sub_type）未命中，该设备参数值无法叠加（仍显示 "—"，不影响骨架可见性，符合 REQ-FUNC-001-C）。

---

### ADR-1111-06：connectRoom 改用 DB 全量 device_sns 发现，弃用 probeNeighbors

**Status**：Accepted

**Context**：
生产实例 3-1-7-702 确认：面板 SN 22552–22555 与主簇 SN 22153–22158 相差约 400，`probeNeighbors(±8)` 的探测范围为 [22145, 22166]，永远无法发现 22552–22555。写入区（区域二"参数设置"）因此只能发现主簇设备，面板设备的写命令入口消失。（已确认事实，PM agent_invocation 中明确指出）

**Options**：

- **Option A（选择）：connectRoom 从结构缓存（`owner_structure_{sp}`）提取全量 device_sns，并入 knownSns 后 publishRead；弃用 probeNeighbors**
  - 结构缓存在骨架渲染阶段写入，时序上领先于 connectRoom（loadConfig 时机相近或更早，但 onShow 顺序保证两者均在页面加载时完成）；若结构缓存尚未写入，回退到 `ds_sns_{mac}` 遗留缓存；最终回退到空列表（不发 probeNeighbors）。
  - 优点：覆盖所有 device_sn，无盲区；与 DB 数据完全一致；去除 probeNeighbors 的不可预期 MQTT 流量。
  - 缺点：connectRoom 需读取额外缓存（同步 getStorageSync，< 5ms）；若结构缓存为空（首次打开页面且结构端点尚未响应），无法主动 publishRead（退化为被动等待设备上报）。

- **Option B：扩大 probeNeighbors 探测范围（如 ±500）**
  - 优点：无需改动缓存依赖。
  - 缺点：发出 1000 条 MQTT DeviceStatusRead，绝大多数目标 SN 不存在，MQTT broker 流量激增；且 SN 距离不固定，未来实例可能距离更大。

**Decision**：选择 Option A。fallback 优先级：`partState[sp].device_sns`（realtime-params 已返回）→ 读 `owner_structure_{sp}` 缓存提取 `device_sns` 字段 → `loadSns(mac)` 遗留缓存 → 空列表。`probeNeighbors` 函数保留代码（不物理删除，维持 3 个月观察期），但从 `onDeviceUpdate` 的调用路径中移除（注释为 `// DEPRECATED v1.11.1: replaced by structure-cache DB discovery`）。

**Consequences**：
- 正向：面板设备 SN 22552–22555 在结构缓存写入后立即可被 connectRoom 发现；写入区不再丢面板；MQTT probe 流量归零。
- 负向：首次打开页面（无任何缓存）时，connectRoom 无法主动 publishRead（退化为等待设备自发上报或用户点击"刷新"）；第二次访问时（结构缓存已写入）自动恢复全量发现。[可接受，首次打开本就无缓存，参数设置区的"加载中…"已覆盖此场景]

---

## 3. 数据流设计

### 3.1 两阶段渲染完整流程

```
用户点击展开 specific_part (sp)
    │
    ├─ [Phase 1 — 骨架渲染（同步路径）]
    │   ①  uni.getStorageSync('owner_structure_{sp}')
    │       ├─ 命中 → structure = parse(cached)
    │       │    ps.structure = structure
    │       │    ps.structureLoading = false
    │       │    渲染骨架（所有 rooms + system_devices）
    │       │    params 初始值 = "—"（is_stale=true 样式）
    │       │
    │       └─ 未命中 → ps.structureLoading = true
    │                   → 发起 GET /api/miniapp/owner/structure/?sp=X
    │                     [响应后]
    │                     → parse response → ps.structure
    │                     → 写 owner_structure_{sp} + _ts
    │                     → ps.structureLoading = false
    │                     → 渲染骨架
    │
    ├─ [Phase 1.5 — 值缓存立即叠加（骨架渲染完成后，同步）]
    │   ②  uni.getStorageSync('owner_realtime_{sp}')
    │       ├─ 命中 → 按 sub_type 叠加 params 值到已渲染骨架
    │       │          ps.tsLabel = buildTsLabel(ts)
    │       │
    │       └─ 未命中 → 跳过（骨架保持 "—"）
    │
    └─ [Phase 2 — 后台值更新（异步）]
        ③  GET /api/miniapp/owner/realtime-params/?sp=X（值缓存过期或缺失时）
            ├─ 成功 → 按 sub_type 叠加，写 owner_realtime_{sp} + _ts
            │          ps.tsLabel = "刚刚更新"
            │          （无重绘骨架结构，只更新叶子节点值）
            │
            └─ 失败 → 保留现有值（缓存或 "—"），追加"（刷新失败）"
```

### 3.2 缓存分层架构

| 层 | 缓存键 | 内容 | TTL 判定阈值 | 写入时机 |
|----|--------|------|-------------|---------|
| 结构层 | `owner_structure_{sp}` | 结构端点完整响应 JSON | 24h（展示提示，不清空）| 结构端点成功响应；主动刷新成功 |
| 结构时间戳 | `owner_structure_{sp}_ts` | ISO8601 写入时刻 | — | 同上 |
| 值层 | `owner_realtime_{sp}` | realtime-params `data` 字段 JSON | 5min（超期提示"可能过时"）| realtime-params 成功；路径A/B 刷新成功 |
| 值时间戳 | `owner_realtime_{sp}_ts` | ISO8601 写入时刻 | — | 同上 |

两层缓存完全独立，互不干扰。主动下拉刷新时同步清除并重取两层。

### 3.3 设备树未同步降级（OQ-E5）

`GET /api/miniapp/owner/structure/` 在 `device_floor` 无记录时返回：

```json
{
  "success": true,
  "specific_part": "...",
  "sync_status": "pending",
  "rooms": [],
  "system_devices": [],
  "device_sns": []
}
```

前端收到 `sync_status == "pending"` 时：展开区显示"您的房间结构尚未就绪，请等待设备初始化后刷新"；提供"刷新"按钮；不显示骨架。该响应仍写入结构缓存（避免重复请求），但 TTL 缩短为 5 分钟（[ASSUMPTION — 建议 PM 确认]）。

---

## 4. 安全架构（增量）

新结构端点继承 v1.11.0 安全范式（ADR-1110-01，ADR-1110-03）：

| 防线 | 实现 |
|------|------|
| 权限类 | `IsOwnerUser`（仅 role=user 且已登录） |
| 归属过滤 | `OwnerUserBinding.objects.filter(user=request.user, active=True)` 提取 allowed_parts |
| 越权响应 | `specific_part not in allowed_parts → HTTP 403` |
| 中间件 | `/api/miniapp/` 已在 ALLOWLIST，无需额外改 middleware |

无新安全风险引入。

---

## 5. 开放问题

### OQ-1111-A（架构级）：骨架"参数行"的数据来源

**问题**：REQ-FUNC-001 修订版第 4 条"参数行骨架——各设备/面板的参数列表（display_name/param_name）来自 DeviceConfig，参数值字段初始为 '—'"，但当前结构端点设计不包含参数定义（只返回设备骨架）。若 realtime-params 无数据，前端收到的骨架无参数行，无法显示 "—" 占位。

**影响**：如果业主展开后 realtime-params 也无数据（设备从未上报），房间可见但参数行为空（显示"正在获取设备数据…"），而非 "—"。此行为是否可接受？

**选项**：
- A. 结构端点追加 `params_skeleton` 字段（从 DeviceConfig 查询该 sub_type 的所有参数名/展示名），骨架直接含参数行。代价：结构端点需额外查询 DeviceConfig，数据量增加。
- B. 接受"无 realtime-params 数据时参数行不显示 "—"，只显示房间/设备标题"。代价：与 REQ-FUNC-001-C 的 "—" 占位要求不完全一致，但房间本身仍可见（主要修复目标满足）。

[ASSUMPTION — requires PM confirmation: 建议接受 Option B，简化结构端点语义；若 PM 要求严格满足 "—" 占位，选 Option A。]

---

### OQ-1111-B（已接受假设，列此供 PM 复核）

| # | 假设内容 | 影响 |
|---|---------|------|
| AS-1111-01 | product_code='260001' 在生产中唯一对应 main_thermostat，无同 code 不同用途设备 | sub_type 推导准确性 |
| AS-1111-02 | 结构缓存 pending 时 TTL 缩短为 5min（设备树同步速度未知）| OQ-E5 降级策略 |
| AS-1111-03 | `probeNeighbors` 函数代码保留（注释弃用），3 个月观察期后再物理删除 | 代码库清洁度 |
| AS-1111-04 | 路径A超时后不自动降级路径B（继承 DEV-01 决策，param-settings.vue v1.11.0 已实现）| 刷新 UX |
