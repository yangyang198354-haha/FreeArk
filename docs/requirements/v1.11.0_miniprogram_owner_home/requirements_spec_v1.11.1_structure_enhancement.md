<!--
  @module v1.11.1_structure_enhancement (on top of v1.11.0_miniprogram_owner_home)
  @author sub_agent_requirement_analyst
  @version 1.11.1
  @status DRAFT
  @created 2026-06-27
  @description v1.11.0「我的房产」结构展示增强：结构与实时数据解耦、真实房间名、完整性保证、结构缓存
  @amends C:/Users/胖子熊/MyProject/FreeArk/docs/requirements/v1.11.0_miniprogram_owner_home/requirements_spec.md
-->

# v1.11.1 「我的房产」结构展示增强 需求规格说明书（增补文件）

---

## 执行摘要

### 本文件定位

本文件是对 `v1.11.0_miniprogram_owner_home/requirements_spec.md` 的**修正与增补**，不重写 v1.11.0 全部内容。v1.11.0 文档中未被本文件明确标注为"已修订（supersede）"的条目继续有效。

**版本定义**：v1.11.1 = v1.11.0 已上线功能 + 本文件描述的「结构展示增强」修正。

### 修订背景

v1.11.0 上线后，用户实测（2026-06-27）发现：在生产实例 3-1-7-702（4 个温控面板：SN 22552–22555；6 个系统级设备：SN 22153–22158）中，前端展示仅出现一个面板，其余面板消失。后端代码勘察确认根因：`miniapp_owner_realtime_params`（`views_miniapp_device_settings.py` 第 184 行起）对 PLCLatestData 无记录的参数执行 `continue` 跳过，导致无实时数据的 sub_type 整体被移除出响应，前端收不到该"房间"节点。结构完整性依赖实时数据是设计缺陷，本文件予以修正。

### 修订/新增需求概览

| 变更类型 | 需求 ID | 简述 |
|---------|---------|------|
| **修订（supersede）** | REQ-FUNC-001 | 结构数据来源改为设备树，与 PLCLatestData 完全解耦；房间名改用 `device_room.room_name` |
| **修订（supersede）** | REQ-FUNC-001 子需求（新增） | 结构完整性保证：无实时数据的房间仍必须显示 |
| **修订（supersede）** | REQ-FUNC-004 | 新增结构缓存层（独立于值缓存），定义两阶段加载流程 |
| **新增** | REQ-FUNC-006 | 业主专属设备树结构端点（新 API，`/api/miniapp/owner/structure/`） |

**推断性需求**：1 处（REQ-FUNC-004 修订版中的结构缓存 TTL），标注 `[INFERRED — requires PM confirmation]`，占本文件总需求数 < 10%。

### v1.11.0 OQ-A 决策的局部修正说明

v1.11.0 `requirements_spec.md` §6.2 OQ-A 标注为"已勘察解决"，结论为"复用 `get_available_sub_types` + realtime 分组逻辑，参数已天然按房间(panel_*)归类，无需新映射、无降级"。该结论在**参数已有 PLCLatestData 记录**时成立，但遗漏了以下情形：`miniapp_owner_realtime_params` 的 PLCLatestData 过滤逻辑会将无实时数据的整个 sub_type 节点删除。v1.11.0 OQ-A 的其余结论（`panel_*` sub_type 即房间、`SYSTEM_LEVEL_SUB_TYPES` 归"全屋系统"）仍然有效，不撤销。

---

## 已修订需求（supersede v1.11.0 对应条目）

---

### REQ-FUNC-001（v1.11.1 修订版）：专有部分结构展示——数据来源与完整性修订

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-001（v1.11.1 修订版） |
| **supersedes** | v1.11.0 `requirements_spec.md` REQ-FUNC-001 详细行为第 3、4 条 |
| **描述** | 系统应当将专有部分"房间/面板骨架"的数据来源改为设备树（`device_floor → device_room → device_node`），与 PLCLatestData **完全解耦**；在骨架渲染完成后再异步叠加参数值；骨架完整性不依赖任何设备的实时上报状态。 |
| **来源引用** | 用户实测反馈（2026-06-27）："结构展示必须来自后端读取的绑定专有部分结构，不依赖 MQTT 上报的 device 才显示"；"只要业主绑定了某专有部分，就能快速显示其下各个面板、主机、新风等结构骨架" |
| **优先级** | Must Have |
| **备注** | v1.11.0 REQ-FUNC-001 中第 1、2、5 条详细行为（绑定列表、卡片展示、无绑定降级）不受影响，继续有效。第 3、4 条由本修订版取代。 |

**详细行为（取代 v1.11.0 REQ-FUNC-001 第 3、4 条）：**

3. 展开某套时，调用**新增的结构端点**（`GET /api/miniapp/owner/structure/?specific_part=X`，见 REQ-FUNC-006）获取该套的**完整房间列表及设备节点**（`device_room` + `device_node`）。该端点不包含任何 PLCLatestData 字段，返回结构与实时数据是否存在无关。

4. 展开后按以下规则渲染骨架：
   - **房间分组**：`device_room` 记录对应各房间（含有实时数据和无实时数据的房间均显示）；系统级设备（`device_node.sub_type` 属于 `SYSTEM_LEVEL_SUB_TYPES`）归入"全屋系统"分区（沿用 v1.11.0 分组逻辑）。
   - **房间标题**：优先使用 `device_room.room_name`（如"书房"、"儿童房"、"主卧"），若为空则 fallback 到 `device_room.ori_room_name`，最终 fallback 到 `sub_type_display`。理由：`room_name` 是用户可见的真实名称，`sub_type_display`（如"书房温控"）是技术配置名，不应直接作为 UI 主标题。
   - **参数行骨架**：各设备/面板的参数列表（`display_name`/`param_name`）来自 `DeviceConfig`，参数值字段初始为占位符"—"（或"采集中…"），`is_stale=true`。
   - **参数值叠加**：骨架渲染完成后，后台**异步**调用 `GET /api/miniapp/owner/realtime-params/`（v1.11.0 已有端点），将返回值叠加到对应参数行（无需重绘骨架结构，仅更新值字段）。

#### REQ-FUNC-001 子需求：结构完整性保证

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-001-C（v1.11.1 新增子需求） |
| **描述** | 系统应当保证：已绑定专有部分下的**所有 `device_room` 记录**均出现在 UI 展示中，不得因缺少 PLCLatestData 记录而丢失任何房间或面板节点。 |
| **来源引用** | 用户实测反馈（2026-06-27）："绑定下应展示全部房间/面板，不允许因无实时数据而丢失面板。即使某个面板当前无 PLCLatestData，该面板仍应显示（参数值可为占位符'—'或'采集中…'）" |
| **优先级** | Must Have |
| **备注** | 直接修复根因缺陷（`views_miniapp_device_settings.py` 第 184 行 `if record is None: continue` + 空 sub_type 删除逻辑导致面板丢失）。修复手段由架构阶段决定（改造现有端点 vs 新建结构端点，见 OQ-E1）。 |

**详细约束：**

- 无 PLCLatestData 记录的参数行：`value` 字段显示占位符"—"（前端渲染），`is_stale` 标注为 `true`，但**参数行本身必须存在**于响应中。
- 无 PLCLatestData 记录的房间/面板：显示完整的房间标题 + 参数行（带占位值），不从列表中移除。
- 生产实例 3-1-7-702 的验收基准：4 个温控面板（SN 22552–22555，对应书房/次卧/主卧/儿童房）均应出现在展开后的 UI 中，不论各面板当前是否有 PLCLatestData 记录。

---

### REQ-FUNC-004（v1.11.1 修订版）：缓存策略——新增结构缓存层

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-004（v1.11.1 修订版） |
| **supersedes** | v1.11.0 `requirements_spec.md` REQ-FUNC-004（在其基础上新增结构缓存层，原有值缓存定义继续有效） |
| **描述** | 系统应当在原有值缓存（`owner_realtime_{specific_part}`，v1.11.0 已定）之外，独立维护一套结构缓存（`owner_structure_{specific_part}`），供骨架优先渲染使用；两层缓存 TTL 不同，分别管理，实现骨架先到、值后到的两阶段加载体验。 |
| **来源引用** | 用户实测反馈（2026-06-27）："结构可缓存：不必每次走 HTTP 拉取，不必等 MQTT 上报；缓存命中即可立即渲染骨架" |
| **优先级** | Should Have |
| **备注** | 结构数据变化频率远低于参数值（业主绑定后很少增删房间），故结构缓存可用较长 TTL，减少不必要的结构请求。 |

**新增缓存 key 规范（追加到 v1.11.0 REQ-FUNC-004 表格）：**

| key | 内容 | 示例 |
|-----|------|------|
| `owner_structure_{specific_part}` | 设备树结构骨架 JSON（房间列表 + 每间房的设备/面板列表，不含参数值） | `owner_structure_3-1-7-702` |
| `owner_structure_{specific_part}_ts` | 结构缓存写入时刻（ISO8601 字符串） | `owner_structure_3-1-7-702_ts` |

**结构缓存 TTL：**

- 建议 TTL = 24 小时 `[INFERRED — requires PM confirmation]`（设备树结构变化极低频，用户绑定后很少增删房间）。
- 备选：与值缓存对齐（5 分钟），代价是每次打开都需要发起一次结构请求，失去"即时骨架"体验。
- TTL 超过后缓存仍可使用（不自动清空），但时间戳标签应提示"结构数据较旧"（不阻断显示）。
- 用户主动下拉刷新时，同时强制刷新结构缓存和值缓存。
- `[INFERRED — requires PM confirmation]` 是否需要后端在结构变更时主动通知前端（如 WebSocket 推送）？若不需要，则仅靠 TTL + 主动刷新。

**两阶段加载流程（取代 v1.11.0 REQ-FUNC-004 "加载流程"第 1~3 步）：**

**阶段一（骨架先到）：**
1. 用户展开某专有部分时，调用 `uni.getStorageSync('owner_structure_{specific_part}')`。
2. **结构缓存命中**：立即（< 100ms）渲染完整房间骨架，参数行初始值为"—"。同时读取 `owner_realtime_{specific_part}` 值缓存，若命中则立即叠加参数值（< 200ms 完成两层渲染）。
3. **结构缓存未命中**：展开区显示"加载中…"，等待 `GET /api/miniapp/owner/structure/` 响应后渲染骨架，随后发起值请求。

**阶段二（值异步叠加）：**
4. 骨架渲染完成（无论来自缓存还是接口）后，后台异步调用 `GET /api/miniapp/owner/realtime-params/`（值缓存未命中或已过期时）。
5. 值返回后叠加到骨架（仅更新值字段，不重绘骨架结构，无闪烁、无布局重绘）。
6. 后台刷新成功：写入 `owner_realtime_{specific_part}` 及时间戳，时间戳标签更新为"刚刚更新"。
7. 后台刷新失败：若有值缓存则保留显示，追加"（刷新失败）"提示；若无值缓存则参数行持续显示"—"，不弹阻断性 toast。

**结构缓存写入时机：**
- `GET /api/miniapp/owner/structure/` 成功响应时写入 `owner_structure_{specific_part}` 及时间戳。
- 主动下拉刷新触发结构重取成功时同步更新。

---

## 新增需求

---

### REQ-FUNC-006：业主专属设备树结构端点

| 字段 | 内容 |
|------|------|
| **ID** | REQ-FUNC-006 |
| **描述** | 系统应当提供一个新的业主专属设备树结构端点，返回业主绑定专有部分下的完整房间-设备树结构（`device_room.room_name` + `device_node`），与 PLCLatestData **完全解耦**，仅表示"这里有什么设备"，不含任何参数当前值信息。 |
| **来源引用** | 用户实测反馈（2026-06-27）："结构展示必须来自后端读取的绑定专有部分结构，不依赖 MQTT 上报的 device 才显示"；"快速显示其下各个面板、主机、新风等结构骨架" |
| **优先级** | Must Have |
| **备注** | 此为新增端点，v1.11.0 无对应需求。是否新建端点或改造现有端点由 OQ-E1 决策（推荐新建）。若 PM 在架构阶段选择改造现有 `miniapp_owner_realtime_params` 端点，则本需求的端点路径相应调整，但行为约束不变。 |

**端点详细行为：**

- **候选路径**：`GET /api/miniapp/owner/structure/?specific_part={specific_part}`（推荐，见 OQ-E1）
- **权限**：`IsOwnerUser` + `OwnerUserBinding(user=request.user, active=True)` 归属过滤（与现有 miniapp 端点一致）
- **数据链路**：`OwnerInfo → OwnerUserBinding → DeviceFloor → DeviceRoom → DeviceNode`

**响应结构示例：**

```json
{
  "specific_part": "3-1-7-702",
  "rooms": [
    {
      "room_id": 12,
      "room_name": "书房",
      "ori_room_name": "三房书房",
      "devices": [
        {
          "device_sn": "22552",
          "device_name": "温控面板",
          "sub_type": "panel_study_room"
        }
      ]
    },
    {
      "room_id": 13,
      "room_name": "儿童房",
      "ori_room_name": "四房儿童房",
      "devices": [
        {
          "device_sn": "22555",
          "device_name": "温控面板",
          "sub_type": "panel_children_room"
        }
      ]
    }
  ],
  "system_devices": [
    { "device_sn": "22153", "device_name": "自由方舟主机", "sub_type": "main_thermostat" },
    { "device_sn": "22154", "device_name": "水力模块",     "sub_type": "hydraulic_module" },
    { "device_sn": "22155", "device_name": "新风机组",     "sub_type": "fresh_air" }
  ]
}
```

**约束：**
- 响应中**不包含**任何 PLCLatestData 字段（`value`/`collected_at`/`is_stale`）。
- 所有在 `OwnerUserBinding` 链路下可达的 `device_room` 记录均出现在 `rooms` 数组中，无论其下设备是否有 PLCLatestData 记录。
- `sub_type` 字段可选，供前端做参数过滤时用，不作为主要房间标识。
- 越权请求（`specific_part` 不属于当前用户的 active 绑定）返回 403。
- `specific_part` 对应的 `device_floor` 表中无记录时（设备树尚未同步）：返回 `rooms=[]` + 提示字段 `"sync_status": "pending"`，见 OQ-E5。
- 该端点结果适合前端以较长 TTL 缓存（结构变化低频），对应 `owner_structure_{specific_part}` 缓存键。

---

## 待确认问题清单（OQ-E 系列）

以下问题须在进入 v1.11.1 架构阶段前由 PM 拍板。

---

### OQ-E1（核心，必须在架构阶段前确认）：后端实现路径——新建结构端点 vs 改造现有端点

**问题**：`REQ-FUNC-001-C`（结构完整性）和 `REQ-FUNC-006`（结构端点）的后端实现，应选择：

**推荐方案：新建 `/api/miniapp/owner/structure/`**

理由：
1. **职责清晰**：结构（有什么设备）与值（当前读数）天然是两类数据，缓存 TTL 不同（结构 ~24h vs 值 ~5min），分开更合理。
2. **最小改动风险**：改造 `miniapp_owner_realtime_params` 核心过滤逻辑会影响现有测试（`test_miniapp_owner_v1110.py`），新建端点风险隔离。
3. **扩展性**：新端点可独立演化（未来可加楼层信息、设备状态字段），不污染实时参数接口语义。
4. **`room_name` 天然可达**：设备树遍历路径（`DeviceFloor → DeviceRoom → DeviceNode`）自然包含 `room_name`；从 `realtime-params` 强行 JOIN `device_room` 会破坏其数据结构语义。

**备选方案：改造现有 `miniapp_owner_realtime_params` 端点**

- 修改"过滤逻辑"：去掉 `if record is None: continue` + 空 sub_type 删除逻辑，改为保留无数据的 sub_type（参数值为 null）。
- 在每个 sub_type 响应中新增 `room_name` 字段（从 `device_room` 表 JOIN）。
- 缺点：无法实现结构单独缓存（结构和值混在同一响应，TTL 只能取短的）；`room_name` JOIN 增加查询复杂度；改动影响现有测试覆盖面。

**影响范围**：后端架构、前端缓存策略、测试用例。

---

### OQ-E2：房间名优先级策略与 `room_name` 数据质量确认

**问题**：
1. `device_room.room_name` 是否总是有值？是否存在为空的情况？（`device_tree_sync.py` 从屏端同步，若屏端未配置则 `room_name` 可能为空或与 `ori_room_name` 相同）
2. 屏端同步后的 `room_name` 文案格式是否符合用户期望的 UI 展示？（例如：屏端 `room_name` 是"三房书房"还是"书房"？用户期望的是哪种）

**推荐策略**：`device_room.room_name`（首选）→ `device_room.ori_room_name`（备用）→ `sub_type_display`（最后 fallback）

**影响范围**：前端房间标题渲染逻辑，可能影响 REQ-FUNC-001 修订版第 4 条 fallback 链的实现细节。

---

### OQ-E3：结构缓存 TTL（`[INFERRED]`，需 PM 确认）

**问题**：`owner_structure_{specific_part}` 缓存的 TTL 应设为多少？

**推荐**：24 小时（设备树结构变化极低频，用户绑定后很少增删房间）。

**备选**：5 分钟（与值缓存对齐），代价是失去"即时骨架"体验优势。

**附加问题**：除 TTL 外，是否需要后端在设备树结构变更时主动通知前端（如 WebSocket 推送），触发前端主动更新结构缓存？若不需要，则仅靠 TTL + 用户主动刷新失效。

**影响范围**：前端缓存策略，可能影响 REQ-FUNC-004 修订版。

---

### OQ-E4：系统级设备（`SYSTEM_LEVEL_SUB_TYPES`）的设备名数据来源

**问题**："全屋系统"分区中各系统级设备的显示名称，应取自 `device_node.device_name`（如"自由方舟主机"、"新风机组"）还是沿用 v1.11.0 的 `sub_type_display`？

**推荐**：使用 `device_node.device_name`，更语义化，且与结构端点响应中的 `device_name` 字段一致，避免前端维护两套名称映射。

**影响范围**：前端渲染逻辑（"全屋系统"分区标题），以及 REQ-FUNC-006 响应结构中 `system_devices[].device_name` 字段的使用方式。无后端影响（`device_name` 已在结构端点响应中返回）。

---

### OQ-E5：设备树未同步时的降级策略

**问题**：若 `device_floor` 表中无该 `specific_part` 的记录（设备树尚未同步，可能业主刚完成绑定），结构端点应如何响应？

**选项 A（推荐）**：返回 `rooms=[]`、`sync_status="pending"` + 提示文案"设备树尚未同步，请稍后刷新"；前端展开区显示该提示及"刷新"按钮。理由：明确提示优于静默降级，用户知道需要等待初始化。

**选项 B**：降级到现有 `get_available_sub_types` 策略（返回 `SYSTEM_LEVEL_SUB_TYPES` 兜底），不提示设备树未同步。缺点：静默降级可能让用户误以为自己的绑定只有系统级设备。

**影响范围**：后端结构端点异常分支，以及前端"展开区"降级 UI（新增"设备树尚未同步"状态）。

---

## 附录：根因代码引用

以下代码片段为 PM 已勘察确认的根因，记录于此供架构阶段参考，不作为需求内容。

文件：`FreeArkWeb/backend/freearkweb/api/views_miniapp_device_settings.py`，函数 `miniapp_owner_realtime_params`（第 184 行起）：

```python
record = latest_by_param.get(cfg.param_name)
if record is None:
    continue   # ← 无 PLCLatestData 记录的参数直接跳过

# ...
# 移除无参数的 sub_type / group
for group_key in list(result.keys()):
    sub_types = result[group_key]['sub_types']
    for sub_key in [k for k, v in sub_types.items() if not v['params']]:
        del sub_types[sub_key]      # ← 没有任何有实时数据参数的 sub_type 被删掉
    if not sub_types:
        del result[group_key]       # ← 整个 group 也删掉
```

结论：若某个房间面板（如书房温控 `panel_study_room`）当前无 PLCLatestData 记录，其所有参数被跳过 → 该 sub_type 被删除 → 前端收不到这个"房间"节点，UI 消失。这是"只显示一个面板"的直接原因。

生产实例 3-1-7-702 验证：`get_available_sub_types('3-1-7-702')` 返回全部 4 个 panel_* + 5 个系统级，结构完整；问题纯粹是展示层 PLCLatestData 过滤导致。
