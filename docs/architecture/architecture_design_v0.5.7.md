# 系统架构设计文档增量 — FreeArk v0.5.7 按房型过滤设备面板与采集点裁剪

```
file_header:
  document_id: ARCH-v0.5.7
  title: FreeArk v0.5.7 — 按房型过滤设备面板、参数设置与 PLC 采集点裁剪 架构设计
  author_agent: sub_agent_system_architect (via PM Orchestrator, incremental revision)
  project: FreeArk 能耗采集平台
  version: v0.5.7-rev1
  created_at: 2026-05-22
  revised_at: 2026-05-22
  status: APPROVED
  revision_note: |
    PM 决策锁定（2026-05-22）：
    - ADR-v0.5.7-04 降级策略：方案 B 已锁定（删除「待 PM 确认」标注）
    - M6 清理命令：本版本不实施（OQ-v0.5.7-03）
    - ADR-v0.5.7-06：决策反转，采集侧裁剪纳入本版本（OQ-v0.5.7-04）
      新增 M7 模块（ondemand_collect_subscriber 改造）、MQTT payload 扩展设计
  references:
    - docs/requirements_spec_v0.5.7.md
    - docs/user_stories_v0.5.7.md
    - docs/architecture/architecture_design.md (v0.4.0-APPROVED)
    - FreeArkWeb/backend/freearkweb/api/models.py
    - FreeArkWeb/backend/freearkweb/api/views.py
    - FreeArkWeb/backend/freearkweb/api/views_device_settings.py
    - FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py
    - FreeArkWeb/backend/freearkweb/api/management/commands/seed_device_config.py
    - datacollection/ondemand_collect_subscriber.py
    - datacollection/resource/plc_config.json
```

---

## 1. 架构概述

### 1.1 变更范围

本次 v0.5.7 在已有 FreeArk 平台（Django 5.2 + Waitress + Vue 3 + Element Plus）之上进行增量修改，**不引入新框架、新数据库表、新 MQTT topic**。变更边界如下：

| 层 | 文件 | 变更类型 |
|----|------|---------|
| 后端 API | `api/views.py` → `get_device_realtime_params()` | 修改：增加房型过滤 |
| 后端 API | `api/views_device_settings.py` → `device_settings_params()` | 修改：增加房型过滤 |
| 后端 MQTT handler | `api/mqtt_handlers.py` → `PLCLatestDataHandler` | 修改：`_bulk_upsert` 和 `_write_history` 增加过滤 |
| 后端工具层 | `api/utils_room_filter.py`（新增） | 新增：房型过滤工具函数，供多处复用 |
| 后端管理命令 | `api/management/commands/cleanup_invalid_device_params.py` | **本版本不实施**（PM OQ-v0.5.7-03）|
| 数据采集侧 | `datacollection/ondemand_collect_subscriber.py` | **修改**：读取 `allowed_params` 白名单，裁剪 PLC 读取点位（见 ADR-v0.5.7-06-rev1，M7）|
| 前端 | 无变更 | 后端过滤后前端渲染逻辑无需改动 |
| 数据模型 | 无变更 | 复用现有 DeviceFloor / DeviceRoom 表 |

### 1.2 核心设计原则

**单一真值来源（SSOT）**：以 `DeviceRoom`（`device_room` 表）中已同步的房间数据作为房型真值，通过 `OwnerInfo → DeviceFloor → DeviceRoom` 关联链查询。

**最小侵入原则**：所有过滤逻辑封装在独立工具函数中，不改动现有业务逻辑的核心路径，降低回归风险。

**降级安全原则**：若某专有部分尚未同步设备树，系统降级为「仅显示系统级面板」，不崩溃，不阻塞。

---

## 2. 架构决策记录（ADR）

### ADR-v0.5.7-01：房型真值来源选择

**问题**：用哪张表作为「该专有部分有哪些房间」的权威来源？

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A（选定）** `device_room` 表 | 由「同步设备树」功能从屏侧 floor-room-device/list 接口同步，已包含各专有部分的楼层-房间-设备树 | 已存在于生产库；包含 `ori_room_name` 精确房间名；与屏侧保持同步 | 需要先完成设备树同步，否则数据为空 |
| B `OwnerInfo.room_count` 字段 | 仅有数量，无法区分具体是哪个房间缺失 | 查询简单 | 无法映射到具体 sub_type，不满足需求 |
| C 新增房型配置表 | 新建 `housing_type` 表存储户型与房间的映射 | 灵活 | 增加维护成本；引入新数据模型 |

**决策**：选择**方案 A**。`device_room` 表已包含精确的房间名称（`ori_room_name`），通过静态映射表将其与 `DeviceConfig.sub_type` 关联即可满足需求，无需新增表。

---

### ADR-v0.5.7-02：DeviceConfig.sub_type 与 DeviceRoom.ori_room_name 的映射策略

**问题**：`DeviceConfig.sub_type`（如 `panel_fourth_children`）与 `DeviceRoom.ori_room_name`（如 `四房儿童房`、`儿童房` 等屏侧返回的中文名）如何对应？

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A（选定）** 静态映射字典 | 在代码中定义 `SUB_TYPE_TO_ROOM_KEYWORDS` 字典，值为 `ori_room_name` 中可能出现的关键词列表，使用包含匹配 | 简单、可测试、无额外查库 | 关键词需人工维护；若屏侧返回的房间名称变化需同步更新 |
| B 数据库配置表 | 在 `DeviceConfig` 中新增 `room_keyword` 字段 | 运行时可修改 | 增加 migration；维护成本高 |
| C 完全精确匹配 | `ori_room_name` 必须完全等于某个预定义字符串 | 最严格 | 屏侧返回的名称可能有变体（如「书房」vs「三房书房」） |

**决策**：选择**方案 A**（关键词包含匹配）。

**映射字典定义**（来源：`seed_device_config.py` 中的 sub_type 注释 + `plc_config.json` 中的 description 字段）：

```python
# 温控面板 sub_type → ori_room_name 中需包含的关键词（任意一个命中即匹配）
SUB_TYPE_TO_ROOM_KEYWORDS: dict[str, list[str]] = {
    'panel_study_room':      ['书房', '次卧'],        # 三房次卧/四房书房
    'panel_bedroom':         ['主卧', '次卧'],        # 三房主卧/四房次卧（次卧优先由 panel_study_room 匹配）
    'panel_children_room':   ['儿童房', '主卧'],      # 三房儿童房/四房主卧
    'panel_fourth_children': ['儿童房'],              # 四房儿童房（专属）
}
# 注意：panel_bedroom 与 panel_study_room 均含「次卧」关键词，需在 get_available_sub_types() 中
# 通过「同时检查专有部分有无书房关键词」区分三房与四房。
# 实际的精确映射策略见 module_design_v0.5.7.md §2.2。

# 不受房型约束的系统级 sub_type（始终显示）
SYSTEM_LEVEL_SUB_TYPES: frozenset[str] = frozenset({
    'main_thermostat',
    'fresh_air',
    'energy_meter',
    'hydraulic_module',
    'air_quality',
})
```

**重要说明**：`plc_config.json` 中的 description 字段明确记录了参数的适用户型，例如：
- `bedroom_*`：描述为「三房主卧四房次卧」
- `study_room_*`：描述为「三房次卧四房书房」
- `children_room_*`：描述为「三房儿童房四房主卧」
- `fourth_children_room_*`：描述为「四房儿童房」

这与 `device_room.ori_room_name` 的屏侧返回值吻合。

---

### ADR-v0.5.7-03：过滤逻辑的架构位置

**问题**：房型过滤逻辑应该放在哪一层？

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A（选定）** 独立工具模块 `api/utils_room_filter.py` | 将「查询有效 sub_type 集合」封装为函数，供 views.py 和 mqtt_handlers.py 复用 | 复用性强；单元测试容易；不污染现有视图函数 | 多一个文件 |
| B 在每个视图函数内分别实现 | 直接在 views.py 和 mqtt_handlers.py 中各写一遍 | 无额外文件 | 重复逻辑；维护困难 |
| C Django model manager 方法 | 在 DeviceRoom model 上添加 class method | ORM 惯用写法 | 与 DeviceConfig/sub_type 的映射逻辑耦合 |

**决策**：选择**方案 A**，新建 `FreeArkWeb/backend/freearkweb/api/utils_room_filter.py`。

---

### ADR-v0.5.7-04：未完成设备树同步时的降级策略

**问题**：若 `device_floor` 表中没有某 specific_part 的记录，应如何处理？

| 方案 | 说明 |
|------|------|
| A 显示全量（保持当前行为） | 安全，但不解决问题 |
| **B（选定）** 仅显示系统级面板，隐藏所有房间面板 | 比 A 更干净；用户可通过同步设备树操作触发数据加载 |
| C 完全隐藏面板 | 过于激进，主温控等始终有效的面板也会消失 |

**决策**：选择**方案 B**：`device_floor` 无该 specific_part 记录时，`available_sub_types` 仅包含 `SYSTEM_LEVEL_SUB_TYPES`，所有 `panel_*` 不可用。

**PM 已锁定**（OQ-v0.5.7-02，2026-05-22）：方案 B 为最终决策，无需条件变更。

---

### ADR-v0.5.7-05：缓存策略

**问题**：`get_available_sub_types(specific_part)` 每次请求都查 DB 性能影响？

**分析**：
- `device_room` 查询：`OwnerInfo.objects.get(specific_part=sp).floors.prefetch_related('rooms')`，涉及 2~3 次查询，在现有 MySQL 上耗时约 5~20ms。
- 设备面板打开频率：通常为用户手动操作，非高并发场景（QPS << 10）。
- MQTT handler 路径：`PLCLatestDataHandler` 每 10 分钟处理一次消息，频率低。

**决策**：v0.5.7 初版使用**进程内字典缓存**，TTL = 300 秒，`_room_filter_cache: dict[str, tuple[frozenset, float]]`。缓存在设备树同步（`device-tree-sync` 接口）后主动清除。不引入 Redis 或 Django cache framework。

---

### ADR-v0.5.7-06-rev1：采集侧（datacollection）按需采集裁剪

**PM 决策**（OQ-v0.5.7-04，2026-05-22）：**纳入本版本**，与初稿决策相反。

**问题**：`OndemandCollectSubscriber._execute_ondemand()` 目前遍历 `plc_config.json` 的全部参数（约 50 条）进行读取，是否裁剪？

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| A 不裁剪（初稿方案） | 采集侧不变，依赖落库侧兜底过滤 | 变更范围小 | 每次按需采集仍向 PLC 发起无效地址读取，BG-04 未彻底闭环 |
| **B（选定）** Django 后端在 MQTT payload 中附带 `allowed_params` 白名单 | 后端计算白名单后注入 ondemand 指令，采集侧读取后裁剪 PLC 读取 | 采集侧无需知道 Django DB；协议扩展清晰；向后兼容（无白名单时全量采集） | MQTT payload 格式需扩展；采集侧需处理新字段 |
| C 采集侧通过 HTTP 轮询 Django API 获取白名单 | 采集侧主动查询后端 | 解耦采集指令与白名单 | 引入 HTTP 依赖；采集侧架构约束（独立进程）复杂化 |

**决策**：选择**方案 B**。

**技术分析**：
- `ondemand_collect_subscriber.py` 是独立 Python 进程，不能直接查 Django DB，方案 B 通过 MQTT payload 传递白名单最小侵入。
- 当前 MQTT ondemand request payload 结构（`views.py` 中触发 ondemand refresh 的接口）为：
  ```json
  {"specific_part": "9-1-10-1002", "requested_at": "2026-05-22 10:00:00"}
  ```
  扩展后增加 `allowed_params` 字段：
  ```json
  {
    "specific_part": "9-1-10-1002",
    "requested_at": "2026-05-22 10:00:00",
    "allowed_params": ["system_switch", "operation_mode", "bedroom_temperature", ...]
  }
  ```
- `OndemandCollectSubscriber._on_request()` 已解析 payload dict，可直接读取 `allowed_params`。
- `_execute_ondemand()` 的 `configs` 列表构建（L226-236）在遍历 `plc_config.json` 时增加白名单过滤即可。

**并发与缓存一致性分析**：
- 白名单由 Django 后端在接收按需采集请求时**实时计算**（调用 `get_available_sub_types()`），计算结果注入当次 MQTT payload，无需采集侧维护缓存，不存在缓存一致性问题。
- 采集侧 `max_workers=1`（单线程串行），不存在并发竞争。
- 若同一 specific_part 的两次按需采集请求之间设备树发生变更（极低概率），由于防重入机制（`_pending` set），第二次请求须等第一次完成后才执行，届时 Django 会重新计算白名单，自然保持一致。

**向后兼容性**：若 payload 无 `allowed_params`（旧版 Django 或手动触发），采集侧降级为全量采集（等同当前行为），不报错，不中断服务。

**与落库侧（FR-v0.5.7-03/04）的关系（双道过滤，不重复不遗漏）**：
- **第一道（采集侧，FR-v0.5.7-05）**：针对**按需采集（ondemand）链路**，`OndemandCollectSubscriber` 依据 `allowed_params`，**不发起**无效 PLC 地址读取，MQTT result 消息中不含无效参数。彻底闭环 BG-04。
- **第二道（落库侧，FR-v0.5.7-03/04）**：针对**所有 MQTT 消息来源**（定时周期采集、按需采集、其他来源），`PLCLatestDataHandler` 依据 `param_blocklist`，**不落库**无效参数。兜底保障，适用于：定时采集场景（采集侧未裁剪）、向后兼容（无 `allowed_params` 的按需采集）、任何边界情况。
- 两道过滤职责不重叠：采集侧仅覆盖按需采集链路，落库侧覆盖所有 MQTT 消息。共同作用使 BG-03 和 BG-04 完全闭环。

---

## 3. 数据流设计

### 3.1 设备面板查询数据流（修改后）

```
浏览器 (DeviceCardsView.vue → fetchData())
    │
    │  GET /api/devices/realtime-params/?specific_part=9-1-10-1002
    ▼
views.get_device_realtime_params()
    │
    ├─[Query 1] PLCLatestData.objects.filter(specific_part=sp)
    │           → latest_by_param 字典
    │
    ├─[Query 2] utils_room_filter.get_available_sub_types(sp)  ← 新增
    │           → DeviceFloor.objects.filter(owner__specific_part=sp)
    │             .prefetch_related('rooms')
    │           → 解析 ori_room_name，通过关键词映射得到 available_sub_types
    │           → 缓存 300s
    │
    ├─[Query 3] DeviceConfig.objects.filter(is_active=True).order_by('id')
    │
    └─ 构建响应：
       对每个 cfg in configs_qs:
         IF cfg.sub_type in SYSTEM_LEVEL_SUB_TYPES OR cfg.sub_type in available_sub_types:
           照常构建（原有逻辑）
         ELSE:
           跳过（不渲染该 sub_type）
         ↓
       返回过滤后的嵌套 JSON
```

### 3.2 MQTT 落库数据流（修改后）

```
MQTT broker → PLCLatestDataHandler.handle()
    │
    ├─ 解析 device_id（specific_part）、data_dict
    │
    ├─ 新增：utils_room_filter.get_panel_param_blocklist(specific_part)  ← 新增
    │   → 查询该专有部分不存在的 panel_* sub_type 的全部 param_name 集合
    │   → 缓存 300s
    │
    └─ 遍历 data_dict 中的参数：
       IF param_name in blocklist:
         跳过（不 upsert PLCLatestData，不写 device_param_history）
         记录 debug 日志
       ELSE:
         照常 upsert（原有逻辑）
```

### 3.3 按需采集数据流（修改后，FR-v0.5.7-05）

```
浏览器 (DeviceCardsView.vue → triggerOndemandRefresh())
    │
    │  POST /api/devices/ondemand-refresh/
    ▼
views.ondemand_refresh()  ← Django 后端（修改）
    │
    ├─ 原有：构建 payload = {"specific_part": sp, "requested_at": ...}
    │
    ├─ 新增（v0.5.7）：调用 get_available_sub_types(sp)
    │   → available_sub_types（带缓存，300s TTL）
    │   → 查询 DeviceConfig.objects.filter(sub_type__in=available_sub_types, is_active=True)
    │   → 得到 allowed_params = [param_name list]
    │
    ├─ 将 allowed_params 注入 payload：
    │   payload["allowed_params"] = allowed_params
    │
    └─ 发布 MQTT topic: /datacollection/plc/ondemand/request/{sp}
       payload: {"specific_part": sp, "requested_at": ..., "allowed_params": [...]}

采集侧 OndemandCollectSubscriber._on_request()
    │
    ├─ 解析 data = json.loads(payload)
    ├─ specific_part = data["specific_part"]
    ├─ 新增（v0.5.7）：allowed_params = data.get("allowed_params")
    │   → 若为 None（向后兼容）：allowed_params = None（全量采集）
    │
    └─ 提交 _execute_ondemand(specific_part, allowed_params=allowed_params)

采集侧 OndemandCollectSubscriber._execute_ondemand()
    │
    ├─ 原有：configs = [全量 plc_config.json 参数]
    │
    ├─ 新增（v0.5.7）：
    │   IF allowed_params is not None:
    │     configs = [c for c in configs if c["param_key"] in set(allowed_params)]
    │     记录 debug 日志：f"采集侧裁剪: {len(configs)} / 原 {full_count} 个参数"
    │   ELSE:
    │     全量采集（向后兼容，不变）
    │
    ├─ 仅读取 configs 内的 PLC DB 地址（不发起白名单外的 PLC 读操作）
    └─ 发布 result topic（仅含白名单内参数的 data_dict）
```

**注意**：定时刷新（`startAutoRefresh()`）调用 `fetchData()` 从 DB 读取，采集来自周期性定时采集任务（`task_scheduler.py`），该链路**不使用** ondemand 机制，由落库侧双道过滤（FR-v0.5.7-03/04）兜底，采集侧无需修改。

---

### 3.4 参数设置查询数据流（修改后）

```
浏览器 (DeviceSettingsPanelView.vue)
    │
    │  GET /api/device-settings/params/{specific_part}/
    ▼
views_device_settings.device_settings_params()
    │
    ├─ 原有：DeviceConfig.filter(is_active=True)
    │        DeviceAttrDef、PLCLatestData 查询
    │
    ├─ 新增：utils_room_filter.get_available_sub_types(sp)
    │
    └─ 构建 groups：
       跳过 sub_type 不在 available_sub_types 且不在 SYSTEM_LEVEL_SUB_TYPES 的参数
       (其余逻辑不变)
```

---

## 4. 兼容性与回滚分析

### 4.1 API 兼容性

| 接口 | 响应结构变化 | 兼容性 |
|------|------------|--------|
| `GET /api/devices/realtime-params/` | 过滤后 sub_types 数量可能减少（无 breaking change，前端原有逻辑可处理空 sub_types） | 向后兼容 |
| `GET /api/device-settings/params/{sp}/` | groups 数量可能减少 | 向后兼容 |
| `POST /api/devices/ondemand-refresh/` | 不变 | 无影响 |

### 4.2 数据库影响

| 操作 | 影响 |
|------|------|
| 新的数据不落库 | `plc_latest_data` 和 `device_param_history` 不再写入不存在房间的参数 |
| 已有数据 | 不受影响（除非执行可选的清理命令） |
| 索引/Schema | 无变更 |

### 4.3 回滚方案

若发现回归问题，回滚方式：
1. **仅后端回滚**：通过 `git revert` 回退 `views.py`、`views_device_settings.py`、`mqtt_handlers.py`、`utils_room_filter.py` 的变更，无需数据库操作。
2. **紧急开关**（可选）：在 `utils_room_filter.py` 中定义 `ROOM_FILTER_ENABLED = True` 环境变量开关，设为 `False` 时所有函数返回全量 sub_types，行为退化为当前逻辑。

---

## 5. 受影响模块清单（v0.5.7-rev1，PM 决策锁定后）

| 模块 | 文件路径 | 变更说明 |
|------|---------|---------|
| 设备实时参数 API | `FreeArkWeb/backend/freearkweb/api/views.py` | `get_device_realtime_params()` 增加 available_sub_types 过滤（M2）|
| 按需采集接口 | `FreeArkWeb/backend/freearkweb/api/views.py` → `ondemand_refresh()` | 新增：计算 `allowed_params` 并注入 MQTT payload（M7-Django 侧）|
| 参数设置 API | `FreeArkWeb/backend/freearkweb/api/views_device_settings.py` | `device_settings_params()` 增加 available_sub_types 过滤（M3）|
| MQTT 落库 handler | `FreeArkWeb/backend/freearkweb/api/mqtt_handlers.py` | `PLCLatestDataHandler` 增加 param blocklist 过滤（M4）|
| 房型过滤工具（新增）| `FreeArkWeb/backend/freearkweb/api/utils_room_filter.py` | 新增文件，封装 get_available_sub_types / get_panel_param_blocklist（M1）|
| 设备树同步视图 | `FreeArkWeb/backend/freearkweb/api/views.py` → 设备树同步接口 | 同步成功后主动清除房型过滤缓存（M5）|
| 按需采集订阅器（采集侧）| `datacollection/ondemand_collect_subscriber.py` | 读取 `allowed_params`，裁剪 PLC 读取配置列表（M7-采集侧）|
| 清理管理命令 | `api/management/commands/cleanup_invalid_device_params.py` | **本版本不实施**（PM OQ-v0.5.7-03）|

---

## 6. 待决策项（PM 决策全部锁定）

| 编号 | 问题 | 状态 | PM 决策（2026-05-22） |
|------|------|------|----------------------|
| OQ-v0.5.7-02 | 未同步设备树时的降级策略 | **已锁定** | **方案 B**：仅显示系统级面板，所有 `panel_*` 隐藏 |
| OQ-v0.5.7-03 | 是否纳入存量数据清理命令 | **已锁定** | **不纳入**：v0.5.7 仅保证新数据不落库无效记录，存量保留 |
| OQ-v0.5.7-04 | 采集侧裁剪是否纳入本版本 | **已锁定** | **纳入**：必须实现（与初稿相反），见 ADR-v0.5.7-06-rev1、M7 |

**本架构文档无待决策项，可进入开发阶段。**
